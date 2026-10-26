/**
 * Compare cases (utils/compare.ts): the default rows, differences from the base case in display
 * units with a true minus sign, "Same" only when the values display the same, a relative
 * difference only for quantities with a true zero, no values from a case that did not converge,
 * and every result key treated as optional. Values are made-up solved states (testing/results.ts).
 */
import { describe, expect, it } from 'vitest';
import type { Override, PipeConnection, Project, SolvedState } from '../api/types';
import { flag, link, pumpResult, pumpTransferSolved, response } from '../testing/results';
import type { ResultsState } from '../state/project.svelte';
import {
	caseResponse,
	compareCells,
	defaultRows,
	DEFAULT_ROW_LIMIT,
	rowLabel,
	rowUnit,
	type CompareColumn
} from './compare';
import { createComponent } from './factory';
import { insertComponentInConnection, reversePiping, updateConnection } from './edit';
import { pumpTransferExample } from './examples';
import { lastSolveText } from './goal-seek';
import { markProjectCopy } from './identity';
import { addPipe, removePipe } from './piping';
import { withScenarios } from './scenarios';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

function project(overrides: Override[] = []): Project {
	return withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Winter', overrides }]);
}

const column = (solved: SolvedState | null, converged = true): CompareColumn => ({
	solved,
	converged
});

describe('default rows', () => {
	it('status, the pumps, changed elements, assigned flows, then the network extremes', () => {
		const rows = defaultRows(
			project([
				{ kind: 'component', componentId: 'V1', field: 'status', value: 'isolated' },
				{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 },
				{ kind: 'pipe', connectionId: 'L3', pipeIndex: 0, field: 'length', value: 80 },
				{ kind: 'project', field: 'fluid.temperature', value: 280 },
				{ kind: 'component', componentId: 'P1', field: 'speed', value: 0.9 }
			]),
			[pumpTransferSolved(), null]
		);
		expect(rows.map((r) => [r.quantity, r.elementId ?? ''])).toEqual([
			['status', ''],
			['pumpFlow', 'P1'],
			['pumpHead', 'P1'],
			['pumpNpshMargin', 'P1'],
			['pumpSpeed', 'P1'],
			['valveFlow', 'V1'],
			['valveState', 'V1'],
			['boundaryOutflow', 'R2'],
			['linkFlow', 'L3'],
			['linkHeadLoss', 'L3'],
			['fluidDensity', ''],
			['fluidVaporPressure', ''],
			['lowestPressure', ''],
			['highestVelocity', '']
		]);
	});

	it('leave out a pump’s speed when no case controls or changes it, and NPSH margin without one', () => {
		const solved = pumpTransferSolved({ pumpResults: { P1: pumpResult({ npshMargin: null }) } });
		const rows = defaultRows(project(), [solved]);
		expect(rows.map((r) => r.quantity)).toEqual([
			'status',
			'pumpFlow',
			'pumpHead',
			'lowestPressure',
			'highestVelocity'
		]);
	});

	it(`are at most ${DEFAULT_ROW_LIMIT}, each once`, () => {
		const base = project([
			{ kind: 'pipe', connectionId: 'L3', pipeIndex: 0, field: 'length', value: 80 },
			{
				kind: 'pipe',
				connectionId: 'L3',
				pipeIndex: 0,
				field: 'spec',
				value: { materialId: 'custom' }
			}
		]);
		const port = { id: 'port_1', nominalSize: 0.1016, direction: 'bidirectional' } as const;
		const many: Project = {
			...base,
			components: [
				...base.components,
				...Array.from({ length: 50 }, (_, i) => ({
					type: 'assigned_flow' as const,
					id: `AF${i + 1}`,
					name: `Demand ${i + 1}`,
					elevation: 0,
					flow: 0.001,
					ports: [{ ...port }]
				}))
			]
		};
		const rows = defaultRows(many, [pumpTransferSolved()]);
		expect(rows).toHaveLength(DEFAULT_ROW_LIMIT);
		expect(rows.filter((r) => r.quantity === 'linkFlow')).toHaveLength(1);
		// The network's extremes end the list; the assigned flows are cut to fit.
		expect(rows.slice(-3)).toEqual([
			{ quantity: 'assignedPressure', elementId: 'AF32' },
			{ quantity: 'lowestPressure' },
			{ quantity: 'highestVelocity' }
		]);
	});
});

describe('cells and differences', () => {
	const base = pumpTransferSolved();
	const lower = pumpTransferSolved({
		pumpResults: { P1: pumpResult({ operatingFlow: 0.0178, operatingHead: 24.5 }) }
	});

	it('give values in display units and differences with a true minus sign', () => {
		const flow = compareCells(
			{ quantity: 'pumpFlow', elementId: 'P1' },
			[column(base), column(lower)],
			project(),
			SI_UNITS
		);
		expect(flow[0]).toEqual({ text: '20', invalid: false });
		expect(flow[1]!.text).toBe('17.8');
		expect(flow[1]!.diff).toMatchObject({ text: '−2.2 (−11 %)', same: false });
		const head = compareCells(
			{ quantity: 'pumpHead', elementId: 'P1' },
			[column(base), column(lower)],
			project(),
			SI_UNITS
		);
		expect(head[1]!.diff?.text).toBe('+2.5 (+11.4 %)');
		// In other units: the difference is in those units.
		const gpm = compareCells(
			{ quantity: 'pumpFlow', elementId: 'P1' },
			[column(base), column(lower)],
			project(),
			IMPERIAL_UNITS
		);
		expect(gpm[1]!.diff?.text).toMatch(/^−34\.8\d* \(−11 %\)$/);
	});

	it('give no relative difference for pressures, grade lines or NPSH margins', () => {
		const higher = pumpTransferSolved({
			pumpResults: { P1: pumpResult({ npshMargin: 10 }) }
		});
		const margin = compareCells(
			{ quantity: 'pumpNpshMargin', elementId: 'P1' },
			[column(base), column(higher)],
			project(),
			SI_UNITS
		);
		expect(margin[1]!.diff?.text).toBe('+1');
		const pressure = compareCells(
			{ quantity: 'portPressure', elementId: 'P1', portId: 'suction' },
			[column(base), column(pumpTransferSolved())],
			project(),
			SI_UNITS
		);
		expect(pressure[1]!.diff).toMatchObject({ text: 'Same', same: true });
	});

	it('say Same only when the values display the same, with the exact difference in the title', () => {
		const close = pumpTransferSolved({
			pumpResults: { P1: pumpResult({ operatingFlow: 0.0200001 }) }
		});
		const cells = compareCells(
			{ quantity: 'pumpFlow', elementId: 'P1' },
			[column(base), column(close)],
			project(),
			SI_UNITS
		);
		expect(cells[1]!.diff).toMatchObject({ text: 'Same', same: true });
		expect(cells[1]!.diff!.title).toMatch(/^Difference: 1×10⁻⁴ L\/s$/);
	});

	it('show text, and the base text where it differs', () => {
		const closed = pumpTransferSolved({
			valveResults: { V1: { ...base.valveResults.V1!, state: 'closed', flow: 0 } }
		});
		const cells = compareCells(
			{ quantity: 'valveState', elementId: 'V1' },
			[column(base), column(closed)],
			project(),
			SI_UNITS
		);
		expect(cells.map((c) => [c.text, c.baseText])).toEqual([
			['Open', undefined],
			['Closed', 'Open']
		]);
	});

	it('show no values of a case that did not converge, but its status; missing results are —', () => {
		const failed = pumpTransferSolved({ converged: false });
		const flow = compareCells(
			{ quantity: 'pumpFlow', elementId: 'P1' },
			[column(base), column(failed, false), column(null)],
			project(),
			SI_UNITS
		);
		expect(flow.map((c) => c.text)).toEqual(['20', '—', '—']);
		expect(flow[1]!.diff).toBeUndefined();
		const status = compareCells(
			{ quantity: 'status' },
			[column(base), column(failed, false)],
			project(),
			SI_UNITS
		);
		expect(status.map((c) => c.text)).toEqual([
			'Converged, 0 physically invalid',
			'Did not converge'
		]);
		// A closed pump without a result, a deleted element: no value, no error.
		const gone = compareCells(
			{ quantity: 'pumpFlow', elementId: 'P9' },
			[column(base), column(lower)],
			project(),
			SI_UNITS
		);
		expect(gone.map((c) => c.text)).toEqual(['—', '—']);
	});

	it('mark an element with a physically invalid flag in that case, and say where extremes are', () => {
		const flagged = pumpTransferSolved({
			flags: [
				flag({ code: 'CAVITATION', severity: 'invalid', message: 'Made-up.', componentId: 'P1' })
			]
		});
		const cells = compareCells(
			{ quantity: 'pumpFlow', elementId: 'P1' },
			[column(base), column(flagged)],
			project(),
			SI_UNITS
		);
		expect(cells.map((c) => c.invalid)).toEqual([false, true]);
		const lowest = compareCells(
			{ quantity: 'lowestPressure' },
			[column(base)],
			project(),
			SI_UNITS
		);
		// The lowest absolute pressure (closest to the vapor pressure).
		expect(lowest[0]!.where).toBe('Port 1 of Discharge tank');
		const fastest = compareCells(
			{ quantity: 'highestVelocity' },
			[column(base)],
			project(),
			SI_UNITS
		);
		expect(fastest[0]!.where).toMatch(/→/);
	});

	it('label rows with their element and unit', () => {
		const p = project();
		expect(rowLabel(p, { quantity: 'pumpFlow', elementId: 'P1' })).toBe('Transfer pump · Flow');
		expect(rowLabel(p, { quantity: 'linkHeadLoss', elementId: 'L3' })).toBe(
			'Discharge isolation valve → Discharge tank · Head loss'
		);
		expect(rowLabel(p, { quantity: 'portPressure', elementId: 'P1', portId: 'suction' })).toBe(
			'Suction of Transfer pump · Pressure'
		);
		expect(rowLabel(p, { quantity: 'status' })).toBe('Network · Status');
		expect(
			rowUnit({ quantity: 'portPressure', elementId: 'P1', portId: 'suction' }, SI_UNITS)
		).toBe('kPa(g)');
		expect(rowUnit({ quantity: 'valveState', elementId: 'V1' }, SI_UNITS)).toBe('');
	});
});

describe("a case's response (Compare's rule, export.md §2.1)", () => {
	const results = (stale: boolean): ResultsState => ({
		response: response(pumpTransferSolved()),
		stale,
		solving: false,
		error: null,
		cancelled: false,
		errorStale: false
	});

	it('keeps the response of a solved, not converged, out-of-date or cancelled case', () => {
		for (const status of ['solved', 'not_converged', 'stale', 'cancelled'] as const) {
			const r = results(status === 'stale');
			expect(caseResponse(status, r)).toBe(r.response);
		}
	});

	it('drops the response a failed case or one a stopped run did not reach kept', () => {
		expect(caseResponse('failed', results(true))).toBeNull();
		expect(caseResponse('not_reached', results(true))).toBeNull();
	});

	it('has none without a response', () => {
		expect(caseResponse('not_solved', { ...results(false), response: null })).toBeNull();
	});
});

describe('connection rows after a structural edit since a case was solved', () => {
	/**
	 * `solvedAs` with connection `id` reversed (ends swapped, pipes in the other order), copied as
	 * the store copies a project for an edit: each pipe the pipe it was (identity.ts).
	 */
	function turned(solvedAs: Project, id: string): Project {
		const now = structuredClone(solvedAs);
		markProjectCopy(now, solvedAs);
		const c = now.connections.find((x) => x.id === id)!;
		[c.fromComponentId, c.toComponentId] = [c.toComponentId, c.fromComponentId];
		[c.fromPortId, c.toPortId] = [c.toPortId, c.fromPortId];
		c.piping = reversePiping(c.piping);
		return now;
	}
	/** L3 as it runs now: from the discharge tank to the valve (a reversal since `solvedAs`). */
	const reversed = (solvedAs: Project) => turned(solvedAs, 'L3');
	const l3 = (quantity: 'linkFlow' | 'linkHeadLoss' | 'linkVelocity') => ({
		quantity,
		elementId: 'L3'
	});
	const shown = (cells: ReturnType<typeof compareCells>) =>
		cells.map((c) => [c.text, c.diff?.text ?? '', c.note ?? '']);

	it('give a case solved before a reversal in the direction the row names now', () => {
		const before = project();
		const now = reversed(before);
		// The base, solved after the reversal: L3 runs from the tank, so its values are negative.
		const base = pumpTransferSolved({
			linkResults: {
				...pumpTransferSolved().linkResults,
				L3: link({ flow: -0.02, velocity: -4, headLoss: -8 })
			}
		});
		// The scenario, solved before it (out of date): the same flow, signed the old way.
		const winter = pumpTransferSolved();
		const columns = [column(base), { ...column(winter), sent: before }];
		expect(rowLabel(now, l3('linkFlow'))).toBe('Discharge tank → Discharge isolation valve · Flow');
		expect(shown(compareCells(l3('linkFlow'), columns, now, SI_UNITS))).toEqual([
			['-20', '', ''],
			['-20', 'Same', 'Reversed since solved']
		]);
		expect(shown(compareCells(l3('linkHeadLoss'), columns, now, SI_UNITS))).toEqual([
			['-8', '', ''],
			['-8', 'Same', 'Reversed since solved']
		]);
	});

	it('give none for a case solved before the connection’s ends changed, and say why', () => {
		const before = project();
		const valve = createComponent('gate', before);
		// L3 now ends at the new valve, with all its pipes: its flow is known, its head loss is not.
		const now = insertComponentInConnection(before, 'L3', valve);
		const base = pumpTransferSolved();
		const columns = [column(base), { ...column(pumpTransferSolved()), sent: before }];
		expect(shown(compareCells(l3('linkFlow'), columns, now, SI_UNITS))).toEqual([
			['20', '', ''],
			['20', 'Same', '']
		]);
		expect(shown(compareCells(l3('linkHeadLoss'), columns, now, SI_UNITS))).toEqual([
			['8', '', ''],
			['—', '', 'Ends changed since solved']
		]);
	});

	/** L2 of two pipes, A (4 m/s, the fastest) then B (2.25 m/s), solved; the case, out of date. */
	function twoPipes() {
		const before = project();
		const l2 = before.connections.find((c) => c.id === 'L2')!;
		const a = l2.piping.pipes[0]!;
		l2.piping.pipes = [a, { ...a, length: 2 }];
		const one = link().segments[0]!;
		const solved = pumpTransferSolved({
			linkResults: {
				...pumpTransferSolved().linkResults,
				L2: link({
					flow: 0.02,
					velocity: 4,
					segments: [
						{ ...one, index: 0, velocity: 4 },
						{ ...one, index: 1, velocity: 2.25 }
					]
				})
			}
		});
		return { before, solved, column: { ...column(solved), sent: before } };
	}
	const l2Velocity = { quantity: 'linkVelocity', elementId: 'L2' } as const;

	it('give no largest velocity once the pipes of a connection changed since its case was solved', () => {
		const { before, solved, column: stale } = twoPipes();
		const edits = {
			'pipe A removed': (c: PipeConnection) => removePipe(c.piping, 0),
			'pipe A replaced by a new pipe': (c: PipeConnection) => removePipe(addPipe(c.piping), 0),
			'a pipe added': (c: PipeConnection) => addPipe(c.piping)
		};
		for (const [what, edit] of Object.entries(edits)) {
			const now = updateConnection(before, 'L2', (c) => ({ ...c, piping: edit(c) }));
			// The largest velocity solved was pipe A's, or the pipe added has none: no value refers
			// to its pipes now.
			expect(shown(compareCells(l2Velocity, [stale], now, SI_UNITS)), what).toEqual([
				['—', '', 'Pipes changed since solved']
			]);
			// Its flow and head loss are still between the ports it was solved between, out of date.
			expect(
				shown(compareCells({ quantity: 'linkFlow', elementId: 'L2' }, [stale], now, SI_UNITS)),
				what
			).toEqual([['20', '', '']]);
			// The goal card's last-solve hint reads the value as Compare does.
			expect(
				lastSolveText(
					{ quantity: 'link_velocity', elementId: 'L2' },
					response(solved),
					true,
					SI_UNITS,
					{
						structure: now,
						sent: before
					}
				),
				what
			).toBe('Last solve (out of date): none, its pipes changed since.');
		}
		expect(shown(compareCells(l2Velocity, [column(solved)], before, SI_UNITS))).toEqual([
			['4', '', '']
		]);
	});

	it('give the largest velocity while the pipes are the ones solved: after a reversal or an insertion', () => {
		const { before, column: stale } = twoPipes();
		const inserted = insertComponentInConnection(before, 'L2', createComponent('gate', before));
		for (const now of [turned(before, 'L2'), inserted]) {
			expect(shown(compareCells(l2Velocity, [stale], now, SI_UNITS))).toEqual([['4', '', '']]);
		}
	});
});
