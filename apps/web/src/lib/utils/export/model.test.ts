/**
 * The export model against oracles, not snapshots (proposal export.md §7.1, items 1–3, 10, 12, 13
 * and 15 here; the states of items 4–9, 11 and 14 in states.test.ts), over the shared fixture:
 * real API responses (export-input.json).
 *
 * Every oracle reads the API field itself, through a column-to-field map written here: in SI mode
 * a number cell is the API's double, bit for bit; in display mode it is `fromSI` of that field in
 * the display unit of the category written here; and the screen's tables read the same field in
 * the same category (their text equals the Formatter's text of the field), with the departures
 * the design names checked on their own.
 */
import { describe, expect, it } from 'vitest';
import type { Flag, OverrideResult, Project, SolvedState, UnitPreferences } from '../../api/types';
import { DISCLAIMER } from '../../components/links';
import { goalSeekReport } from '../goal-seek';
import { flagText } from '../flag-text';
import { canonicalJson } from '../json';
import { fittingFallbackName, portLabel } from '../labels';
import { pumpChartData } from '../pump-chart';
import {
	assignedFlowTable,
	boundaryTable,
	branchTable,
	fittingTable,
	Formatter,
	HEAD_NOISE,
	linkTable,
	nodeTable,
	pumpTable,
	segmentTable,
	valueText,
	valveTable,
	type Cell
} from '../results';
import { methodsText } from '../trace';
import {
	displayUnit,
	fromSI,
	STANDARD_GRAVITY,
	toSI,
	type UnitCategory,
	type UnitId
} from '../units';
import { csvField } from './csv';
import { fixtureInput, FIXTURE_NAMES, readSheet, type ReadSheet } from './export-testing.testing';
import { buildExport, type CellValue, type ExportInput } from './model';

/** SI base units, as the test states them (§2.3). */
const SI: Readonly<Record<string, UnitId>> = {
	length: 'm',
	diameter: 'm',
	head: 'm',
	pressure: 'Pa',
	flow: 'm3/s',
	velocity: 'm/s',
	power: 'W',
	fraction: '',
	dimensionless: ''
};

/** A column: the API value it holds and its unit category (none: a pure number). */
type Field<T> = [
	label: string,
	value: (x: T) => number | null | undefined,
	category?: UnitCategory
];

const solvedOf = (input: ExportInput, caseId: string | null): SolvedState => {
	const c = input.cases.find((x) => x.id === caseId);
	if (!c?.response) throw new Error(`no response for ${caseId}`);
	return c.response.solvedState;
};

/** The case of a row (its Case id cell, or the only case). */
function caseOf(input: ExportInput, t: ReadSheet, row: readonly CellValue[]): string | null {
	return t.labels.includes('Case id')
		? (t.get(row, 'Case id') as string | null)
		: input.cases[0]!.id;
}

/** Assert every number cell of `t` against its field: SI bit for bit, or fromSI(display unit). */
function checkFields<T>(
	input: ExportInput,
	t: ReadSheet,
	find: (solved: SolvedState, row: readonly CellValue[], caseId: string | null) => T,
	fields: readonly Field<T>[]
): number {
	const si = input.options.units === 'si';
	let checked = 0;
	for (const row of t.rows) {
		const caseId = caseOf(input, t, row);
		const target = find(solvedOf(input, caseId), row, caseId);
		for (const [label, value, category] of fields) {
			const api = value(target);
			const cell = t.get(row, label);
			if (api === null || api === undefined) {
				expect(cell, `${t.sheet.id} ${label}`).toBeNull();
				continue;
			}
			if (si || !category) {
				// SI mode (or a pure number): the API's own double.
				expect(Object.is(cell, api), `${t.sheet.id} ${label}: ${cell} vs ${api}`).toBe(true);
			} else {
				const unit = displayUnit(category, input.prefs);
				expect(cell, `${t.sheet.id} ${label}`).toBe(fromSI(api, unit));
			}
			if (si && category) {
				// …whose unit label is the base unit's (none for a pure number or a 0–1 fraction).
				// A pressure's marker, (g) or (a), aside.
				const column = t.sheet.columns[t.labels.indexOf(label)]!;
				const base = { m: 'm', Pa: 'Pa', 'm3/s': 'm³/s', 'm/s': 'm/s', W: 'W', '': '' };
				expect((column.unit ?? '').replace(/\((g|a)\)$/, ''), `${t.sheet.id} ${label}`).toBe(
					base[SI[category] as keyof typeof base]
				);
			}
			checked++;
		}
	}
	return checked;
}

const nodeFields: Field<SolvedState['nodeResults'][string]>[] = [
	['Elevation', (n) => n.elevation, 'length'],
	['Pressure', (n) => n.pressure, 'pressure'],
	['Dynamic pressure', (n) => n.dynamicPressure, 'pressure'],
	['Total pressure', (n) => n.totalPressure, 'pressure'],
	['Absolute pressure', (n) => n.absolutePressure, 'pressure'],
	['Velocity', (n) => n.velocity, 'velocity'],
	['HGL', (n) => n.hgl, 'head'],
	['EGL', (n) => n.egl, 'head']
];

type Link = SolvedState['linkResults'][string];
const linkFields: Field<Link>[] = [
	['Flow (+ from → to)', (l) => l.flow, 'flow'],
	[
		'Largest velocity',
		(l) => Math.max(Math.abs(l.velocity), ...l.segments.map((s) => Math.abs(s.velocity))),
		'velocity'
	],
	['Head loss (EGL from − to)', (l) => l.headLoss, 'head'],
	['Friction loss (+ with the flow)', (l) => l.frictionHeadLoss, 'head'],
	['Fittings loss (+ with the flow)', (l) => l.fittingsHeadLoss, 'head'],
	['Pipes', (l) => l.segments.length],
	['Fittings', (l) => l.fittings.length]
];

type Segment = Link['segments'][number];
const pipeFields: Field<Segment>[] = [
	['Inner diameter', (s) => s.innerDiameter, 'diameter'],
	['Length', (s) => s.length, 'length'],
	['Roughness', (s) => s.roughness, 'diameter'],
	['Velocity (signed as the flow)', (s) => s.velocity, 'velocity'],
	['Re', (s) => s.reynoldsNumber],
	['f (Darcy)', (s) => s.frictionFactor],
	['Friction loss (+ with the flow)', (s) => s.headLoss, 'head']
];

type FittingResult = Link['fittings'][number];
const fittingFields: Field<FittingResult>[] = [
	['Quantity', (f) => f.quantity],
	['K (each)', (f) => f.k],
	['K referred to diameter', (f) => f.referenceDiameter, 'diameter'],
	['Head loss, all (+ with the flow)', (f) => f.headLoss, 'head']
];

type Pump = SolvedState['pumpResults'][string];
const pumpFields: Field<Pump>[] = [
	['Speed', (p) => (p.status === 'off' ? null : p.speed), 'fraction'],
	['Flow setpoint', (p) => p.control?.setpoint, 'flow'],
	['Flow', (p) => p.operatingFlow, 'flow'],
	['Head', (p) => p.operatingHead, 'head'],
	['Efficiency', (p) => p.efficiency, 'fraction'],
	['Hydraulic power', (p) => p.hydraulicPower, 'power'],
	['Shaft power', (p) => p.shaftPower, 'power'],
	['NPSHa', (p) => p.npshAvailable, 'head'],
	['NPSHr', (p) => p.npshRequired, 'head'],
	['NPSH margin', (p) => p.npshMargin, 'head'],
	['Suction absolute pressure', (p) => p.suctionAbsolutePressure, 'pressure']
];

type Valve = SolvedState['valveResults'][string];
const valveFields: Field<Valve>[] = [
	['Flow (+ inlet → outlet)', (v) => v.flow, 'flow'],
	['Head loss', (v) => v.headLoss, 'head'],
	['Pressure drop, static', (v) => v.pressureDrop, 'pressure'],
	['K (open)', (v) => v.kOpen],
	['K referred to diameter', (v) => v.referenceDiameter, 'diameter'],
	['K effective', (v) => v.kEffective],
	['Cv effective', (v) => v.cvEffective],
	[
		'Pressure setpoint',
		(v) => (['prv', 'psv'].includes(v.valveType) ? v.setpoint : null),
		'pressure'
	],
	['Flow setpoint', (v) => (v.valveType === 'fcv' ? v.setpoint : null), 'flow']
];

type Branch = SolvedState['branchResults'][string];
type Boundary = SolvedState['boundaryResults'][string];

const exportOf = (input: ExportInput) => buildExport(input);

/** Every fixture case in both unit systems. */
const RUNS = FIXTURE_NAMES.flatMap((name) =>
	(['si', 'display'] as const).map((units) => ({ name, units }))
);

describe('number cells are the API values (items 1 and 2)', () => {
	it.each(RUNS)('$name in $units units', ({ name, units }) => {
		const input = fixtureInput(name, { units });
		const bundle = exportOf(input);
		const ids = new Set(bundle.sheets.map((s) => s.id));
		let checked = 0;
		const key = (t: ReadSheet, row: readonly CellValue[], label: string) =>
			String(t.get(row, label));
		if (ids.has('nodes')) {
			const t = readSheet(bundle, 'nodes');
			checked += checkFields(
				input,
				t,
				(s, r) => s.nodeResults[`${key(t, r, 'Component id')}:${key(t, r, 'Port id')}`]!,
				nodeFields
			);
		}
		if (ids.has('links')) {
			const t = readSheet(bundle, 'links');
			checked += checkFields(
				input,
				t,
				(s, r) => s.linkResults[key(t, r, 'Connection id')]!,
				linkFields
			);
		}
		if (ids.has('pipes')) {
			const t = readSheet(bundle, 'pipes');
			checked += checkFields(
				input,
				t,
				(s, r) =>
					s.linkResults[key(t, r, 'Connection id')]!.segments[(t.get(r, 'Pipe #') as number) - 1]!,
				pipeFields
			);
		}
		if (ids.has('fittings')) {
			const t = readSheet(bundle, 'fittings');
			checked += checkFields(
				input,
				t,
				(s, r) =>
					s.linkResults[key(t, r, 'Connection id')]!.fittings.find(
						(f) => f.index === (t.get(r, 'Fitting #') as number) - 1
					)!,
				fittingFields
			);
		}
		if (ids.has('pumps')) {
			const t = readSheet(bundle, 'pumps');
			checked += checkFields(input, t, (s, r) => s.pumpResults[key(t, r, 'Pump id')]!, pumpFields);
		}
		if (ids.has('pump-curves')) {
			const t = readSheet(bundle, 'pump-curves');
			checked += checkFields(
				input,
				t,
				(s, r) => s.pumpResults[key(t, r, 'Pump id')]!.curve[(t.get(r, 'Point #') as number) - 1]!,
				[
					['Flow', (p) => p.flow, 'flow'],
					['Head', (p) => p.head, 'head']
				]
			);
		}
		if (ids.has('valves')) {
			const t = readSheet(bundle, 'valves');
			checked += checkFields(
				input,
				t,
				(s, r) => s.valveResults[key(t, r, 'Valve id')]!,
				valveFields
			);
		}
		if (ids.has('branches')) {
			const t = readSheet(bundle, 'branches');
			checked += checkFields<Branch>(input, t, (s, r) => s.branchResults[key(t, r, 'Branch id')]!, [
				['Combined-flow velocity', (b) => b.referenceVelocity, 'velocity']
			]);
		}
		if (ids.has('branch-ports')) {
			const t = readSheet(bundle, 'branch-ports');
			checked += checkFields<{ b: Branch; port: string }>(
				input,
				t,
				(s, r) => ({ b: s.branchResults[key(t, r, 'Branch id')]!, port: key(t, r, 'Port id') }),
				[
					['Flow (+ into the branch)', ({ b, port }) => b.portFlows[port], 'flow'],
					[
						'K of the path from the combined port',
						({ b, port }) => (port === b.combinedPortId ? null : b.kFactors[port])
					],
					[
						'Velocity K is on',
						({ b, port }) =>
							port === b.combinedPortId || b.lossModel === 'ideal' || b.combinedPortId === null
								? null
								: Math.abs(b.referenceVelocity),
						'velocity'
					],
					[
						'Path head loss (+ in the flow direction)',
						({ b, port }) => b.pathHeadLosses[port],
						'head'
					]
				]
			);
		}
		if (ids.has('boundaries')) {
			const t = readSheet(bundle, 'boundaries');
			checked += checkFields<Boundary>(
				input,
				t,
				(s, r) => s.boundaryResults[key(t, r, 'Boundary id')]!,
				[
					['EGL', (b) => b.egl, 'head'],
					['Net outflow (+ into the network)', (b) => b.outflow, 'flow'],
					['Ports', (b) => Object.keys(b.portOutflows).length]
				]
			);
		}
		if (ids.has('boundary-ports')) {
			const t = readSheet(bundle, 'boundary-ports');
			checked += checkFields<number>(
				input,
				t,
				(s, r) => s.boundaryResults[key(t, r, 'Boundary id')]!.portOutflows[key(t, r, 'Port id')]!,
				[['Outflow (+ into the network)', (v) => v, 'flow']]
			);
		}
		if (ids.has('assigned-flows')) {
			const t = readSheet(bundle, 'assigned-flows');
			checked += checkFields<{
				b: Boundary;
				node: SolvedState['nodeResults'][string];
				flow: number;
			}>(
				input,
				t,
				(s, r, caseId) => {
					const id = key(t, r, 'Node id');
					const c = input.cases.find((x) => x.id === caseId)!;
					const af = c.inputs!.components.find((x) => x.id === id);
					return {
						b: s.boundaryResults[id]!,
						node: s.nodeResults[`${id}:${key(t, r, 'Port id')}`]!,
						flow: af?.type === 'assigned_flow' ? af.flow : NaN
					};
				},
				[
					['Assigned flow (+ demand, − supply)', (x) => x.flow, 'flow'],
					['Net outflow (+ into the network)', (x) => x.b.outflow, 'flow'],
					['Elevation', (x) => x.node.elevation, 'length'],
					['Pressure', (x) => x.node.pressure, 'pressure'],
					['Absolute pressure', (x) => x.node.absolutePressure, 'pressure'],
					['HGL', (x) => x.node.hgl, 'head']
				]
			);
		}
		if (ids.has('system-curves')) {
			const t = readSheet(bundle, 'system-curves');
			checked += checkFields(
				input,
				t,
				(_s, r) => {
					const curve = input.cases[0]!.systemCurves[key(t, r, 'Pump id')]!;
					if (curve.status !== 'ready') throw new Error('not ready');
					const points = [...curve.curve.points].sort((a, b) => a.flow - b.flow);
					return {
						point: points[(t.get(r, 'Point #') as number) - 1]!,
						range: curve.curve.flowRange
					};
				},
				[
					['Flow from', (x) => x.range.min, 'flow'],
					['Flow to', (x) => x.range.max, 'flow'],
					['Flow', (x) => x.point.flow, 'flow'],
					['Head', (x) => x.point.head, 'head']
				]
			);
		}
		expect(checked).toBeGreaterThan(50);
	});
});

/** A screen cell's text (its value text; the note's exact value for "≈ 0"). */
const screenText = (cell: Cell | undefined) => valueText(cell as string);

describe('the screen and the file read one field in one category (item 3)', () => {
	it.each(FIXTURE_NAMES)('%s', (name) => {
		const input = fixtureInput(name, { units: 'display' });
		const bundle = exportOf(input);
		const prefs: UnitPreferences = input.prefs;
		const f = new Formatter(prefs);
		const ids = new Set(bundle.sheets.map((s) => s.id));
		for (const c of input.cases) {
			const solved = c.response!.solvedState;
			const project: Project = input.project;
			const mine = (t: ReadSheet) =>
				t.rows.filter((r) => !t.labels.includes('Case id') || t.get(r, 'Case id') === c.id);

			// Nodes: the same keys in the same order; each shown column the field's num text.
			const nodes = readSheet(bundle, 'nodes');
			const screenNodes = nodeTable(project, solved, prefs);
			const nodeRows = mine(nodes);
			expect(
				nodeRows.map((r) => `${nodes.get(r, 'Component id')}:${nodes.get(r, 'Port id')}`)
			).toEqual(screenNodes.rows.map((r) => r.key));
			for (const row of screenNodes.rows) {
				const node = solved.nodeResults[row.key]!;
				for (const [key, , category] of [
					['elevation', 0, 'length'],
					['pressure', 0, 'pressure'],
					['dynamicPressure', 0, 'pressure'],
					['totalPressure', 0, 'pressure'],
					['absolutePressure', 0, 'pressure'],
					['velocity', 0, 'velocity'],
					['hgl', 0, 'head'],
					['egl', 0, 'head']
				] as const) {
					expect(screenText(row.cells[key])).toBe(f.num(node[key], category));
				}
			}

			// Links: keys and order; flow and head loss (≈ 0 below the head noise).
			const links = readSheet(bundle, 'links');
			const screenLinks = linkTable(project, solved, prefs);
			expect(mine(links).map((r) => links.get(r, 'Connection id'))).toEqual(
				screenLinks.rows.map((r) => r.key)
			);
			for (const row of screenLinks.rows) {
				const link = solved.linkResults[row.key]!;
				expect(screenText(row.cells.flow)).toBe(f.num(link.flow, 'flow'));
				expect(screenText(row.cells.headLoss)).toBe(
					valueText(f.diff(link.headLoss, 'head', HEAD_NOISE))
				);
				// Departure: the screen packs several pipes in one cell; the file has a Pipes row each.
				const pipes = readSheet(bundle, 'pipes');
				const segments = segmentTable(row.key, link, prefs, solved.flags);
				expect(
					mine(pipes)
						.filter((r) => pipes.get(r, 'Connection id') === row.key)
						.map((r) => `${row.key}:segment:${(pipes.get(r, 'Pipe #') as number) - 1}`)
				).toEqual(segments.rows.map((r) => r.key));
				for (const s of segments.rows) {
					const seg = link.segments.find((x) => `${row.key}:segment:${x.index}` === s.key)!;
					expect(screenText(s.cells.innerDiameter)).toBe(f.num(seg.innerDiameter, 'diameter'));
					expect(screenText(s.cells.length)).toBe(f.num(seg.length, 'length'));
					expect(screenText(s.cells.roughness)).toBe(f.num(seg.roughness, 'diameter'));
					expect(screenText(s.cells.velocity)).toBe(f.num(seg.velocity, 'velocity'));
					expect(screenText(s.cells.headLoss)).toBe(
						valueText(f.diff(seg.headLoss, 'head', HEAD_NOISE))
					);
				}
				if (ids.has('fittings')) {
					const fittings = readSheet(bundle, 'fittings');
					const screenFittings = fittingTable(
						row.key,
						link,
						prefs,
						fittingFallbackName,
						solved.flags
					);
					expect(
						mine(fittings)
							.filter((r) => fittings.get(r, 'Connection id') === row.key)
							.map((r) => `${row.key}:fitting:${(fittings.get(r, 'Fitting #') as number) - 1}`)
					).toEqual(screenFittings.rows.map((r) => r.key));
					for (const s of screenFittings.rows) {
						const fit = link.fittings.find((x) => `${row.key}:fitting:${x.index}` === s.key)!;
						expect(screenText(s.cells.referenceDiameter)).toBe(
							f.num(fit.referenceDiameter, 'diameter')
						);
						expect(screenText(s.cells.headLoss)).toBe(
							valueText(f.diff(fit.headLoss, 'head', HEAD_NOISE))
						);
					}
				}
			}

			if (ids.has('pumps')) {
				const pumps = readSheet(bundle, 'pumps');
				const screen = pumpTable(project, solved, prefs);
				expect(mine(pumps).map((r) => pumps.get(r, 'Pump id'))).toEqual(
					screen.rows.map((r) => r.key)
				);
				for (const row of screen.rows) {
					const p = solved.pumpResults[row.key]!;
					expect(screenText(row.cells.flow)).toBe(f.num(p.operatingFlow, 'flow'));
					expect(screenText(row.cells.head)).toBe(f.num(p.operatingHead, 'head'));
					expect(screenText(row.cells.efficiency)).toBe(f.num(p.efficiency, 'fraction'));
					expect(screenText(row.cells.shaftPower)).toBe(f.num(p.shaftPower, 'power'));
					expect(screenText(row.cells.hydraulicPower)).toBe(f.num(p.hydraulicPower, 'power'));
					expect(screenText(row.cells.npshAvailable)).toBe(f.num(p.npshAvailable, 'head'));
				}
			}
			if (ids.has('valves')) {
				const valves = readSheet(bundle, 'valves');
				const screen = valveTable(project, solved, prefs);
				expect(mine(valves).map((r) => valves.get(r, 'Valve id'))).toEqual(
					screen.rows.map((r) => r.key)
				);
				for (const row of screen.rows) {
					const v = solved.valveResults[row.key]!;
					expect(screenText(row.cells.flow)).toBe(f.num(v.flow, 'flow'));
					expect(screenText(row.cells.headLoss)).toBe(
						valueText(f.diff(v.headLoss, 'head', HEAD_NOISE))
					);
					// Departure: one Setpoint column whose unit depends on the type; two in the file.
					const exported = mine(valves).find((r) => valves.get(r, 'Valve id') === row.key)!;
					if (v.valveType === 'prv' || v.valveType === 'psv') {
						expect(valves.get(exported, 'Pressure setpoint')).toBe(
							fromSI(v.setpoint!, displayUnit('pressure', prefs))
						);
						expect(valves.get(exported, 'Flow setpoint')).toBeNull();
						expect(screenText(row.cells.setpoint)).toBe(
							f.value(v.setpoint, 'pressure', { gauge: true })
						);
					}
				}
			}
			if (ids.has('branches')) {
				const branches = readSheet(bundle, 'branches');
				const screen = branchTable(project, solved, prefs);
				expect(mine(branches).map((r) => branches.get(r, 'Branch id'))).toEqual(
					screen.rows.map((r) => r.key)
				);
			}
			if (ids.has('boundaries')) {
				const boundaries = readSheet(bundle, 'boundaries');
				const screen = boundaryTable(project, solved, prefs);
				expect(mine(boundaries).map((r) => boundaries.get(r, 'Boundary id'))).toEqual(
					screen.rows.map((r) => r.key)
				);
				for (const row of screen.rows) {
					const b = solved.boundaryResults[row.key]!;
					expect(screenText(row.cells.egl)).toBe(f.num(b.egl, 'head'));
					expect(screenText(row.cells.outflow)).toBe(f.num(b.outflow, 'flow'));
					expect(
						mine(boundaries).find((r) => boundaries.get(r, 'Boundary id') === row.key)![
							boundaries.labels.indexOf('Type')
						]
					).toBe(row.cells.type);
				}
			}
			if (ids.has('assigned-flows')) {
				const af = readSheet(bundle, 'assigned-flows');
				const screen = assignedFlowTable(project, solved, prefs, c.inputs);
				expect(mine(af).map((r) => af.get(r, 'Node id'))).toEqual(screen.rows.map((r) => r.key));
				for (const row of screen.rows) {
					const input = c.inputs!.components.find((x) => x.id === row.key)!;
					const flow = input.type === 'assigned_flow' ? input.flow : NaN;
					const exported = mine(af).find((r) => af.get(r, 'Node id') === row.key)!;
					// Departure: the screen shows |flow| with its direction; the file the signed flow.
					expect(screenText(row.cells.flow)).toBe(f.num(Math.abs(flow), 'flow'));
					expect(af.get(exported, 'Assigned flow (+ demand, − supply)')).toBe(
						fromSI(flow, displayUnit('flow', prefs))
					);
					expect(af.get(exported, 'Direction')).toBe(row.cells.direction);
				}
			}
		}
	});

	it('names the departures: heads to 0.01 m and "≈ 0" on screen, the value in the file', () => {
		const f = new Formatter({ ...fixtureInput('pump-transfer').prefs });
		expect(f.num(123.456, 'head')).toBe('123.46');
		expect(valueText(f.diff(5e-8, 'head', HEAD_NOISE))).toBe('≈ 0');
	});
});

describe('branch K is on the combined-flow velocity (item 13, decision 29)', () => {
	it.each(RUNS)('K·v²/(2g) is the path head loss: $name, $units', ({ name, units }) => {
		const input = fixtureInput(name, { units });
		const bundle = exportOf(input);
		if (!bundle.sheets.some((s) => s.id === 'branch-ports'))
			return expect(name).toBe('pump-transfer');
		const t = readSheet(bundle, 'branch-ports');
		const si = units === 'si';
		const toSi = (v: number, category: UnitCategory) =>
			si ? v : toSI(v, displayUnit(category, input.prefs));
		let checked = 0;
		for (const row of t.rows) {
			const k = t.get(row, 'K of the path from the combined port');
			const v = t.get(row, 'Velocity K is on');
			const loss = t.get(row, 'Path head loss (+ in the flow direction)');
			if (typeof k !== 'number' || typeof v !== 'number') continue;
			const lossSi = toSi(loss as number, 'head');
			const vSi = toSi(v, 'velocity');
			expect(Math.abs((k * vSi * vSi) / (2 * STANDARD_GRAVITY) - lossSi)).toBeLessThanOrEqual(
				1e-6 + 1e-6 * Math.abs(lossSi)
			);
			checked++;
		}
		expect(checked).toBeGreaterThan(0);
	});

	it('on the Darby fallback too, where each leg’s own velocity would be 24–28 % low', () => {
		const input = fixtureInput('tee-fallback', { units: 'si' });
		const t = readSheet(exportOf(input), 'branch-ports');
		const solved = input.cases[0]!.response!.solvedState;
		expect(solved.flags.some((f) => f.code === 'TEE_PATTERN_FALLBACK')).toBe(true);
		expect(readSheet(exportOf(input), 'branches').column('K is on')).toEqual([
			'Combined-flow velocity'
		]);
		for (const row of t.rows) {
			if (t.get(row, 'Combined port') === true) continue;
			const port = t.get(row, 'Port id') as string;
			const k = t.get(row, 'K of the path from the combined port') as number;
			const loss = t.get(row, 'Path head loss (+ in the flow direction)') as number;
			// The leg's own velocity, from its connection (same diameter): far from the loss.
			const leg = Object.entries(solved.linkResults).find(([id]) =>
				input.project.connections.some(
					(c) =>
						c.id === id &&
						((c.fromComponentId === 'T1' && c.fromPortId === port) ||
							(c.toComponentId === 'T1' && c.toPortId === port))
				)
			)![1];
			const own = (k * leg.velocity ** 2) / (2 * STANDARD_GRAVITY);
			expect(Math.abs(own - loss) / loss).toBeGreaterThan(0.2);
		}
	});
});

describe('documents (item 10)', () => {
	it("Methods is methodsText's lines; methods.txt the cases' texts", () => {
		const input = fixtureInput('scenarios');
		const bundle = exportOf(input);
		const t = readSheet(bundle, 'methods');
		const expected = input.cases.flatMap((c) => {
			const r = c.response!;
			const text = methodsText(r.solvedState.trace.methods, {
				projectName: input.project.metadata.name,
				caseName: r.scenario ? `scenario ${r.scenario.name} (${r.scenario.id})` : 'base case',
				timestamp: r.solvedState.timestamp,
				converged: r.success && r.solvedState.converged,
				stale: false
			});
			return text.replace(/\n$/, '').split('\n');
		});
		expect(t.column('Text')).toEqual(expected);
		const sheet = bundle.sheets.find((s) => s.id === 'methods')!;
		const lines = [...sheet.text!()];
		expect(lines.filter((l) => l === 'Calculation methods and assumptions')).toHaveLength(3);
	});

	it('Goal seek is goalSeekReport, tab parts in cells, in the file’s units and offset', () => {
		for (const units of ['display', 'si'] as const) {
			const input = fixtureInput('pump-transfer', { units });
			const t = readSheet(exportOf(input), 'goal-seek');
			const gs = input.goalSeek!;
			const prefs = units === 'si' ? { ...SI_PREFS } : input.prefs;
			const report = goalSeekReport(gs.response!, gs.run.request, {
				labels: input.project,
				sent: gs.run.project,
				prefs,
				caseWords: 'the base case',
				projectName: input.project.metadata.name,
				caseText: 'base case',
				startedAt: gs.run.startedAt,
				utcOffsetMinutes: 120,
				stale: false,
				invalidFlags: (gs.response!.solvedState?.flags ?? [])
					.filter((x) => x.severity === 'invalid')
					.map((x) => flagText(x, { project: input.project, prefs })),
				converged: !!gs.response!.solvedState?.converged
			});
			expect(t.rows.map((r) => r.filter((c) => c !== null && c !== undefined).join('\t'))).toEqual(
				report.split('\n')
			);
			expect(report).toContain('Run: 2026-10-25 14:31;');
		}
	});

	it('About holds the disclaimer verbatim', () => {
		for (const name of FIXTURE_NAMES) {
			const about = readSheet(exportOf(fixtureInput(name)), 'about');
			expect(about.rows.some((r) => r[2] === DISCLAIMER)).toBe(true);
		}
	});

	it('a link points to the Case choice only where the app has one (a project with scenarios)', () => {
		const note = 'It opens on the base case; choose the case under Case.';
		const values = (name: string) =>
			readSheet(exportOf(fixtureInput(name)), 'about').rows.map((r) => r[2]);
		expect(values('scenarios')).toContain(note);
		expect(values('pump-transfer')).not.toContain(note);
		expect(values('pump-transfer')).toContain(
			'It holds the whole project: every input and every scenario.'
		);
	});
});

const SI_PREFS: UnitPreferences = {
	length: 'm',
	diameter: 'm',
	pressure: 'Pa',
	head: 'm',
	flow: 'm3/s',
	velocity: 'm/s',
	temperature: 'K',
	density: 'kg/m3',
	viscosity: 'Pa.s'
};

describe('system curves (item 12)', () => {
	it("give each point's reason as the chart's data table does", () => {
		const input = fixtureInput('pump-transfer');
		const t = readSheet(exportOf(input), 'system-curves');
		const state = input.cases[0]!.systemCurves.P1!;
		if (state.status !== 'ready') throw new Error('not ready');
		const rows = pumpChartData(
			input.cases[0]!.response!.solvedState.pumpResults.P1!,
			input.prefs,
			null,
			state.curve,
			{ project: input.project, solved: input.project }
		).systemRows;
		expect(t.column('Reason')).toEqual(rows.map((r) => r.note || null));
		expect(t.rows).toHaveLength(state.curve.points.length);
	});
});

describe('scenario changes (item 15)', () => {
	it('write a resistance as exact text with no unit, and its object in the JSON columns', () => {
		const t = readSheet(exportOf(fixtureInput('scenarios')), 'scenario-changes');
		const resistance = t.rows.find((r) => t.get(r, 'Field id') === 'resistance')!;
		expect(t.get(resistance, 'Value')).toBe('Cv 120');
		expect(t.get(resistance, 'Base value')).toBe('Default');
		expect(t.get(resistance, 'Unit')).toBeNull();
		expect(JSON.parse(t.get(resistance, 'Value (SI, JSON)') as string)).toEqual({
			kind: 'Cv',
			value: 120
		});
		expect(t.get(resistance, 'Base value (SI, JSON)')).toBe('null');
	});

	it('write a negative assigned flow as a signed number, in the file’s unit', () => {
		for (const units of ['si', 'display'] as const) {
			const input = fixtureInput('scenarios', { units });
			const t = readSheet(exportOf(input), 'scenario-changes');
			const flow = t.rows.find((r) => t.get(r, 'Field id') === 'flow')!;
			const unit: UnitId = units === 'si' ? 'm3/s' : displayUnit('flow', input.prefs);
			expect(t.get(flow, 'Value')).toBe(fromSI(-0.002, unit));
			expect(t.get(flow, 'Base value')).toBe(fromSI(0.003, unit));
			expect(t.get(flow, 'Unit')).toBe(units === 'si' ? 'm³/s' : 'L/s');
			expect(t.get(flow, 'Value (SI, JSON)')).toBe('-0.002');
			expect(t.get(flow, 'Target')).toBe('=HYPERLINK("https://example.com","Demand")');
		}
	});

	it('come from the server’s record, one row per override, in order', () => {
		const input = fixtureInput('scenarios');
		const t = readSheet(exportOf(input), 'scenario-changes');
		const records = input.cases.flatMap((c) =>
			(c.response!.scenario?.overrides ?? []).map((o) => [c.id, o.index + 1, o.override.field])
		);
		expect(
			t.rows.map((r) => [t.get(r, 'Case id'), t.get(r, 'Change #'), t.get(r, 'Field id')])
		).toEqual(records);
	});
});

describe('the fixture itself', () => {
	it('has the cases the design names', () => {
		expect(FIXTURE_NAMES).toEqual(['pump-transfer', 'scenarios', 'tee-fallback']);
		const tee = fixtureInput('tee-fallback');
		expect(tee.cases[0]!.response!.solvedState.flags.map((f) => f.code)).toContain(
			'TEE_PATTERN_FALLBACK'
		);
		expect(fixtureInput('pump-transfer').utcOffsetMinutes).toBe(120);
	});
});

/** The display preferences of `input`, or SI base units in SI mode (§2.3). */
const prefsOf = (input: ExportInput): UnitPreferences =>
	input.options.units === 'si' ? SI_PREFS : input.prefs;

describe('flags: every column of the Flags sheet is the API flag’s (review V1)', () => {
	const SEVERITY: Readonly<Record<string, string>> = {
		invalid: 'Invalid',
		warning: 'Warning',
		info: 'Info'
	};
	const RANK: Readonly<Record<string, number>> = { invalid: 0, warning: 1, info: 2 };

	/** Each flag's row, by §2.6: invalid, then warning, then info, in API order within each. */
	function checkFlags(input: ExportInput): number {
		const t = readSheet(exportOf(input), 'flags');
		const expected = input.cases.flatMap((c) =>
			(c.response?.solvedState.flags ?? [])
				.map((flag, i) => ({ flag, i, c }))
				.sort((a, b) => RANK[a.flag.severity]! - RANK[b.flag.severity]! || a.i - b.i)
		);
		expect(t.rows).toHaveLength(expected.length);
		const prefs = prefsOf(input);
		const name = (id: string) => input.project.components.find((x) => x.id === id)?.name ?? id;
		for (const [n, { flag, c }] of expected.entries()) {
			const row = t.rows[n]!;
			const at = `${flag.code} (row ${n + 1})`;
			const solved = c.response!.solvedState;
			const connection = flag.connectionId
				? input.project.connections.find((x) => x.id === flag.connectionId)
				: undefined;
			const index = (key: string) => {
				const v = flag.details[key];
				return typeof v === 'number' ? v + 1 : null;
			};
			expect(t.get(row, 'Severity'), at).toBe(SEVERITY[flag.severity]);
			expect(t.get(row, 'Code'), at).toBe(flag.code);
			expect(t.get(row, 'Element kind'), at).toBe(
				flag.componentId ? 'Component' : flag.connectionId ? 'Connection' : 'Network'
			);
			expect(t.get(row, 'Element id'), at).toBe(flag.componentId ?? flag.connectionId ?? null);
			expect(t.get(row, 'Element'), at).toBe(
				flag.componentId
					? name(flag.componentId)
					: connection
						? `${name(connection.fromComponentId)} → ${name(connection.toComponentId)}`
						: null
			);
			expect(t.get(row, 'Port id'), at).toBe(flag.portId);
			expect(t.get(row, 'Port'), at).toBe(flag.portId ? portLabel(flag.portId) : null);
			expect(t.get(row, 'Pipe #'), at).toBe(index('segmentIndex'));
			expect(t.get(row, 'Fitting #'), at).toBe(index('fittingIndex'));
			expect(t.get(row, 'Message'), at).toBe(
				flagText(flag, {
					project: input.project,
					prefs,
					fittingName: (type) => input.library.fittings[type] ?? fittingFallbackName(type),
					valveTypes: Object.fromEntries(
						Object.entries(solved.valveResults).map(([id, v]) => [id, v.valveType])
					)
				})
			);
			expect(t.get(row, 'Message (as reported, SI)'), at).toBe(flag.message);
			expect(t.get(row, 'Details (SI, JSON)'), at).toBe(canonicalJson(flag.details));
			expect(JSON.parse(t.get(row, 'Details (SI, JSON)') as string), at).toEqual(flag.details);
		}
		return expected.length;
	}

	it.each(RUNS)('$name in $units units', ({ name, units }) => {
		const n = checkFlags(fixtureInput(name, { units }));
		if (name === 'tee-fallback') expect(n).toBe(2);
	});

	it('with a port, a pipe and a fitting number, and the severities out of order', () => {
		const input = fixtureInput('pump-transfer');
		const solved = input.cases[0]!.response!.solvedState;
		const flags: Flag[] = [
			{
				code: 'TRANSITIONAL_FLOW',
				severity: 'info',
				message: 'pipe 2 of L3 is transitional',
				componentId: null,
				connectionId: 'L3',
				portId: null,
				details: { segmentIndex: 1, reynoldsNumber: 2500 }
			},
			{
				code: 'BELOW_VAPOR_PRESSURE',
				severity: 'invalid',
				message: 'below the vapor pressure at the suction',
				componentId: 'P1',
				connectionId: null,
				portId: 'suction',
				details: { absolutePressure: 1500, vaporPressure: 2339 }
			},
			{
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message: 'fitting 1 of L1 is outside its range',
				componentId: null,
				connectionId: 'L1',
				portId: null,
				details: { segmentIndex: 0, fittingIndex: 0 }
			},
			{
				code: 'NO_VAPOR_PRESSURE',
				severity: 'info',
				message: 'no vapor pressure',
				componentId: null,
				connectionId: null,
				portId: null,
				details: {}
			}
		];
		const changed = { ...input.cases[0]!, response: structuredClone(input.cases[0]!.response!) };
		changed.response.solvedState = { ...solved, flags };
		for (const units of ['si', 'display'] as const) {
			const run = { ...input, options: { ...input.options, units }, cases: [changed] };
			expect(checkFlags(run)).toBe(4);
			const t = readSheet(exportOf(run), 'flags');
			expect(t.column('Code')).toEqual([
				'BELOW_VAPOR_PRESSURE',
				'CORRELATION_OUT_OF_RANGE',
				'TRANSITIONAL_FLOW',
				'NO_VAPOR_PRESSURE'
			]);
			expect(t.column('Port id')).toEqual(['suction', null, null, null]);
			expect(t.column('Pipe #')).toEqual([null, 1, 2, null]);
			expect(t.column('Fitting #')).toEqual([null, 1, null, null]);
		}
	});
});

describe('trace: every row of the Trace sheet is the API trace’s (review V2)', () => {
	/** The rows of one trace element, by §2.6: each part in the trace view's order and words. */
	function partRows(e: SolvedState['trace']['elements'][string]): CellValue[][] {
		return [
			...e.inputs.map((x, i) => ['Inputs', i + 1, x.name, x.value, x.unit || null, x.source, null]),
			...e.equations.map((x, i) => ['Equations', i + 1, null, null, null, null, x]),
			...e.correlations.map((x, i) => [
				'Correlations',
				i + 1,
				x.name,
				null,
				null,
				null,
				x.citation
			]),
			...e.dataSources.map((x, i) => ['Data sources', i + 1, x.name, null, null, null, x.citation]),
			...e.intermediates.map((x, i) => [
				'Intermediate values',
				i + 1,
				x.name,
				x.value,
				x.unit || null,
				null,
				null
			]),
			...e.notes.map((x, i) => ['Notes', i + 1, null, null, null, null, x])
		] as CellValue[][];
	}

	it.each(['pump-transfer', 'tee-fallback'])('%s, in both unit systems', (name) => {
		for (const units of ['si', 'display'] as const) {
			const input = fixtureInput(name, { units });
			const t = readSheet(exportOf(input), 'trace');
			const elements = input.cases[0]!.response!.solvedState.trace.elements;
			const project = input.project;
			const label = (id: string) => project.components.find((x) => x.id === id)?.name ?? id;
			// Components in project order, then connections in project order (§2.6).
			const order = [
				...project.components.map((x) => x.id),
				...project.connections.map((x) => x.id)
			].filter((id) => elements[id]);
			expect(new Set(order)).toEqual(new Set(Object.keys(elements)));
			const expected = order.flatMap((id) => {
				const e = elements[id]!;
				const connection = project.connections.find((x) => x.id === id);
				const element = connection
					? `${label(connection.fromComponentId)} → ${label(connection.toComponentId)}`
					: label(id);
				return partRows(e).map((r) => [id, element, e.elementType, ...r]);
			});
			const lead = ['Element id', 'Element', 'Element type', 'Part', '#', 'Name'];
			const tail = ['Unit', 'Source', 'Text'];
			expect(t.rows).toHaveLength(expected.length);
			expect(t.rows.length).toBeGreaterThan(100);
			for (const [n, want] of expected.entries()) {
				const row = t.rows[n]!;
				const at = `${want[0]} ${want[3]} ${want[4]}`;
				expect(
					lead.map((l) => t.get(row, l)),
					at
				).toEqual(want.slice(0, 6));
				// A value as reported: the API's own double (SI, whatever the file's units), text or boolean.
				expect(Object.is(t.get(row, 'Value'), want[6]), `${at}: Value`).toBe(true);
				expect(
					tail.map((l) => t.get(row, l)),
					at
				).toEqual(want.slice(7));
			}
			expect(t.column('Unit').filter((u) => u !== null).length).toBeGreaterThan(0);
		}
	});
});

describe('scenario changes not applied have no Value or Base value (review V2)', () => {
	it('orphaned and not applicable records leave both cells empty; the JSON columns say null', () => {
		const input = fixtureInput('scenarios');
		const s1 = input.cases.find((c) => c.id === 'S1')!;
		const scenario = s1.response!.scenario!;
		const unapplied: OverrideResult[] = [
			{
				index: 2,
				override: { kind: 'component', componentId: 'R2', field: 'status', value: 'closed' },
				state: 'not_applicable',
				value: null,
				baseValue: null,
				unit: '',
				message: 'a reservoir has no status'
			},
			{
				index: 3,
				override: {
					kind: 'component',
					componentId: 'V9',
					field: 'resistance',
					value: { kind: 'K', value: 3 }
				},
				state: 'orphaned',
				value: null,
				baseValue: null,
				unit: '',
				message: 'V9 is not in the project'
			},
			{
				index: 4,
				override: { kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 7 },
				state: 'not_applicable',
				value: null,
				baseValue: null,
				unit: '',
				message: 'not applicable'
			},
			{
				index: 5,
				override: {
					kind: 'pipe',
					connectionId: 'L99',
					pipeIndex: 0,
					field: 'length',
					value: 30
				},
				state: 'orphaned',
				value: null,
				baseValue: null,
				unit: '',
				message: 'L99 is not in the project'
			},
			{
				index: 6,
				override: {
					kind: 'pipe',
					connectionId: 'L99',
					pipeIndex: 0,
					field: 'spec',
					value: { material: 'carbon_steel', schedule: '40', nominalSize: 2 }
				},
				state: 'orphaned',
				value: null,
				baseValue: null,
				unit: '',
				message: 'L99 is not in the project'
			}
		] as OverrideResult[];
		const changed = {
			...s1,
			response: {
				...s1.response!,
				scenario: { ...scenario, overrides: [...scenario.overrides, ...unapplied] }
			}
		};
		for (const format of ['xlsx', 'csv'] as const) {
			const run = {
				...input,
				options: { ...input.options, format },
				cases: input.cases.map((c) => (c.id === 'S1' ? changed : c))
			};
			const t = readSheet(exportOf(run), 'scenario-changes');
			const rows = t.rows.filter((r) => t.get(r, 'Case id') === 'S1');
			expect(rows).toHaveLength(scenario.overrides.length + unapplied.length);
			for (const row of rows.slice(scenario.overrides.length)) {
				const at = String(t.get(row, 'Field id'));
				expect(t.get(row, 'State'), at).not.toBe('Applied');
				expect(t.get(row, 'Value'), at).toBeNull();
				expect(t.get(row, 'Base value'), at).toBeNull();
				expect(t.get(row, 'Unit'), at).toBeNull();
				expect(t.get(row, 'Value (SI, JSON)'), at).toBe('null');
				expect(t.get(row, 'Base value (SI, JSON)'), at).toBe('null');
			}
			// An applied resistance whose base is the default still reads "Default".
			const applied = rows.find((r) => t.get(r, 'Field id') === 'resistance')!;
			expect(t.get(applied, 'State')).toBe('Applied');
			expect(t.get(applied, 'Base value')).toBe('Default');
		}
	});
});

describe('captions name what each sheet holds (review V3)', () => {
	it('the Goal seek sheet names its run, its methods and its own staleness, not the case’s solve', () => {
		const input = fixtureInput('pump-transfer');
		const gs = input.goalSeek!;
		const project = input.project.metadata.name;
		const goalSeekCaption = (run: ExportInput) =>
			exportOf(run).sheets.find((s) => s.id === 'goal-seek')!.caption;
		const head = `Goal seek — ${project} — goal seek run 2026-10-25T14:31:00+02:00 — calculation methods ${gs.response!.result.methodVersion}`;
		// The case out of date, the goal seek current (it ran on the edited project).
		const staleCase = { ...input, cases: [{ ...input.cases[0]!, stale: true }] };
		expect(goalSeekCaption(staleCase)).toBe(head);
		// The other way round.
		const staleSeek = { ...input, goalSeek: { ...gs, stale: true } };
		expect(goalSeekCaption(staleSeek)).toBe(
			`${head} — OUT OF DATE: the project changed after this goal seek`
		);
		// Other sheets keep the case's solve.
		const nodes = exportOf(staleCase).sheets.find((s) => s.id === 'nodes')!.caption;
		expect(nodes).toContain('— OUT OF DATE: the project changed after this solve');
		expect(goalSeekCaption({ ...input, options: { ...input.options, units: 'si' } })).toBe(
			`${head} — SI base units`
		);
	});

	it('All cases: About and Compare cases point to where each case’s solve is, not to columns', () => {
		const input = fixtureInput('scenarios');
		const project = input.project.metadata.name;
		const captions = Object.fromEntries(exportOf(input).sheets.map((s) => [s.id, s.caption]));
		expect(captions.about).toBe(
			`About — ${project} — all cases (each case's solve and state: its Case block in this sheet) — SI base units`
		);
		expect(captions['compare-cases']).toBe(
			`Compare cases — ${project} — all cases (each case's solve and state: the Status and Solved at rows) — SI base units`
		);
		expect(captions.nodes).toBe(
			`Nodes — ${project} — all cases (each row's case and solve: Case, Solved at, Results) — SI base units`
		);
	});
});

describe('an out-of-date case mentions the link only when the file holds it (review V5)', () => {
	it('in the dialog’s warning and in About', () => {
		const input = fixtureInput('pump-transfer');
		const stale = { ...input, cases: [{ ...input.cases[0]!, stale: true }] };
		const outOfDate = (run: ExportInput) =>
			readSheet(exportOf(run), 'about').rows.find((r) => r[1] === 'Out of date')![2];
		const warning = (run: ExportInput) =>
			exportOf(run).warnings.find((w) => w.kind === 'stale')!.text;
		expect(warning(stale)).toBe(
			'The project changed after this solve. The file holds the results, names and link of the project as it was solved, and says so in every row. Solve again for current results.'
		);
		expect(outOfDate(stale)).toMatch(
			/ This file holds the results, names the elements and links the project, as solved\.$/
		);
		const noLink = { ...stale, options: { ...stale.options, link: false } };
		expect(warning(noLink)).toBe(
			'The project changed after this solve. The file holds the results and names of the project as it was solved (the project link was left out), and says so in every row. Solve again for current results.'
		);
		expect(outOfDate(noLink)).toMatch(
			/ This file holds the results and names the elements as solved \(the project link was left out\)\.$/
		);
		expect(String(outOfDate(noLink))).not.toContain('links the project');
	});
});

describe('the CSV reading note names every guarded character (review F4)', () => {
	it('= + - @, a tab and a carriage return, as the writer guards them', () => {
		const note =
			"A text cell that begins with =, +, -, @, a tab or a carriage return is written with a leading '; numbers and the JSON columns never are.";
		const input = fixtureInput('pump-transfer', { format: 'csv' });
		const bundle = exportOf(input);
		expect(bundle.readme.some((l) => l.endsWith(note))).toBe(true);
		const about = readSheet(bundle, 'about');
		expect(about.rows.some((r) => r[1] === 'Scripts' && String(r[2]).endsWith(note))).toBe(true);
		// The writer guards exactly these first characters of a text cell.
		for (const first of ['=', '+', '-', '@', '\t', '\r']) {
			expect(csvField(`${first}x`).replace(/^"/, '')).toMatch(/^'/);
		}
		for (const first of ['a', ' ', '{', '(', '#']) {
			expect(csvField(`${first}x`)).toBe(`${first}x`);
		}
	});
});
