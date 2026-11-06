/**
 * Made-up pump stations for the pump lineups' tests (CLAUDE.md D24, proposal pump-lineups.md
 * §10.1): only the components' kinds, ports, statuses, names and connections matter, and each
 * project is valid (the store loads it). Not used by the app.
 */
import type { Component, PipeConnection, Project } from '../api/types';
import { pumpTransferExample } from '../utils/examples';
import { link, projectWith } from './helpers';

const port = (id: string, direction: 'inlet' | 'outlet' | 'bidirectional' = 'bidirectional') => ({
	id,
	nominalSize: 0.1016,
	direction
});
export const pump = (id: string, name = `Pump ${id}`, status: 'on' | 'off' = 'on'): Component => ({
	type: 'pump',
	id,
	name,
	elevation: 0,
	curveId: 'C1',
	speed: 1,
	status,
	ports: [port('suction', 'inlet'), port('discharge', 'outlet')]
});
export const tank = (id: string, ports: number): Component => ({
	type: 'reservoir',
	id,
	name: `Tank ${id}`,
	elevation: 0,
	liquidLevel: 2,
	surfacePressure: 0,
	ports: Array.from({ length: ports }, (_, i) => port(`port_${i + 1}`))
});
export const tee = (id: string): Component =>
	({
		type: 'branch',
		branchType: 'tee',
		id,
		name: `Tee ${id}`,
		elevation: 0,
		lossModel: 'crane',
		ports: ['run_inlet', 'run_outlet', 'branch'].map((p) => port(p))
	}) as Component;
export const prv = (id: string, status: 'active' | 'failed_open'): Component => ({
	type: 'valve',
	valveType: 'prv',
	id,
	name: `PRV ${id}`,
	elevation: 0,
	status,
	setpoint: 100000,
	ports: [port('inlet', 'inlet'), port('outlet', 'outlet')]
});
/** A pipe "A:port" → "B:port". */
export const pipe = (id: string, from: string, to: string): PipeConnection =>
	link(id, from.split(':') as [string, string], to.split(':') as [string, string]);

export interface StationSpec {
	/** The pumps' ids (default P1 … Pn). */
	ids: readonly string[];
	/** Their names (default "Pump {id}"). */
	names?: readonly string[];
	/** Pumps off in the base. */
	off?: readonly string[];
}

/**
 * Stations of pumps in parallel, each between two tanks of its own and each pump through its own
 * ports (the finder's "between two reservoirs" group), one station after another in component
 * order: tanks A{s} and B{s}, connections S{id} and D{id}.
 */
export function stations(...specs: StationSpec[]): Project {
	const components: Component[] = [];
	const connections: PipeConnection[] = [];
	specs.forEach((spec, s) => {
		const a = `A${s + 1}`;
		const b = `B${s + 1}`;
		components.push(tank(a, spec.ids.length));
		spec.ids.forEach((id, i) => {
			components.push(
				pump(id, spec.names?.[i] ?? `Pump ${id}`, spec.off?.includes(id) ? 'off' : 'on')
			);
			connections.push(pipe(`S${id}`, `${a}:port_${i + 1}`, `${id}:suction`));
			connections.push(pipe(`D${id}`, `${id}:discharge`, `${b}:port_${i + 1}`));
		});
		components.push(tank(b, spec.ids.length));
	});
	return projectWith(components, connections, pumpTransferExample().pumpLibrary);
}

export const pumpIds = (n: number, prefix = 'P') =>
	Array.from({ length: n }, (_, i) => `${prefix}${i + 1}`);
/** One station of `n` pumps P1 … Pn named "Pump Pi". */
export const station = (n: number, spec: Partial<StationSpec> = {}) =>
	stations({ ids: pumpIds(n), ...spec });

/**
 * A tee ladder of `n` pumps P1 … Pn (the condenser example's header layout, and the shared
 * fixture's 'ladder'): R1 → suction tees TS1 … TSn, pump Pi from TSi's branch to TDi's, discharge
 * tees TDn … TD1 → R2. Each inner ladder (TSi … TDi, pumps Pi … Pn) is a station of its own.
 */
export function ladder(n: number, spec: Partial<StationSpec> = {}): Project {
	const ids = spec.ids ?? pumpIds(n);
	const components: Component[] = [tank('R1', 1)];
	const connections: PipeConnection[] = [pipe('L0', 'R1:port_1', 'TS1:run_inlet')];
	for (let i = 1; i <= n; i++) components.push(tee(`TS${i}`));
	ids.forEach((id, i) =>
		components.push(
			pump(id, spec.names?.[i] ?? `Pump ${id}`, spec.off?.includes(id) ? 'off' : 'on')
		)
	);
	for (let i = n; i >= 1; i--) components.push(tee(`TD${i}`));
	components.push(tank('R2', 1));
	ids.forEach((id, k) => {
		const i = k + 1;
		connections.push(pipe(`S${id}`, `TS${i}:branch`, `${id}:suction`));
		connections.push(pipe(`D${id}`, `${id}:discharge`, `TD${i}:branch`));
		if (i < n) {
			connections.push(pipe(`HS${i}`, `TS${i}:run_outlet`, `TS${i + 1}:run_inlet`));
			connections.push(pipe(`HD${i}`, `TD${i + 1}:run_outlet`, `TD${i}:run_inlet`));
		}
	});
	connections.push(pipe('L1', 'TD1:run_outlet', 'R2:port_1'));
	return projectWith(components, connections, pumpTransferExample().pumpLibrary);
}

/** PA and PB in parallel, a PRV in PB's discharge line: inside the station. */
export function prvStation(status: 'active' | 'failed_open'): Project {
	return projectWith(
		[tank('A1', 2), pump('PA'), pump('PB'), prv('V1', status), tank('B1', 2)],
		[
			pipe('SA', 'A1:port_1', 'PA:suction'),
			pipe('DA', 'PA:discharge', 'B1:port_1'),
			pipe('SB', 'A1:port_2', 'PB:suction'),
			pipe('DB', 'PB:discharge', 'V1:inlet'),
			pipe('VB', 'V1:outlet', 'B1:port_2')
		],
		pumpTransferExample().pumpLibrary
	);
}

/** A1 and A2 in series beside B1 and B2 in series, between two tees (the finder: parallel). */
export function twoByTwo(): Project {
	return projectWith(
		[
			tank('R1', 1),
			tee('T1'),
			pump('A1'),
			pump('A2'),
			pump('B1'),
			pump('B2'),
			tee('T2'),
			tank('R2', 1)
		],
		[
			pipe('L1', 'R1:port_1', 'T1:run_inlet'),
			pipe('a1', 'T1:run_outlet', 'A1:suction'),
			pipe('a2', 'A1:discharge', 'A2:suction'),
			pipe('a3', 'A2:discharge', 'T2:run_inlet'),
			pipe('b1', 'T1:branch', 'B1:suction'),
			pipe('b2', 'B1:discharge', 'B2:suction'),
			pipe('b3', 'B2:discharge', 'T2:branch'),
			pipe('L2', 'T2:run_outlet', 'R2:port_1')
		],
		pumpTransferExample().pumpLibrary
	);
}

/** PA then PB on one line between two tanks. */
export function series(): Project {
	return projectWith(
		[tank('R1', 1), pump('PA'), pump('PB'), tank('R2', 1)],
		[
			pipe('L1', 'R1:port_1', 'PA:suction'),
			pipe('L2', 'PA:discharge', 'PB:suction'),
			pipe('L3', 'PB:discharge', 'R2:port_1')
		],
		pumpTransferExample().pumpLibrary
	);
}
