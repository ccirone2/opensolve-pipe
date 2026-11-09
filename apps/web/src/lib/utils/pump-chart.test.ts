/**
 * Pump chart data: the curve inside its data is solid, the extrapolated part dashed, and every
 * point is a reported value in display units. Pump results are made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import { pumpResult, systemCurvePoint, systemCurveResponse } from '../testing/results';
import { imageNoteLines } from './export/chart-image';
import { pumpTransferExample } from './examples';
import {
	CASE_MARKERS,
	caseMarkers,
	chartNotes,
	MARKER_SYMBOLS,
	offCasesNote,
	otherCasesData,
	pumpChartCases,
	pumpChartData,
	ratedCurveRange,
	tickCase,
	untickCase,
	untickedAfter,
	valueNotes,
	type CaseChoice,
	type CaseList,
	type PanelKey,
	type PumpChecksInput
} from './pump-chart';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

const GPM = (231 * 0.0254 ** 3) / 60; // m³/s, US gallon = 231 in³
const FT = 0.3048;

describe('pump chart data', () => {
	it('reads the curve’s flow range at rated speed from the project', () => {
		expect(ratedCurveRange(pumpTransferExample(), 'P1')).toEqual([0, 0.03]);
		expect(ratedCurveRange(pumpTransferExample(), 'V1')).toBeNull();
	});

	it('maps the curve, system curve and operating point to display units', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], systemCurveResponse());
		expect(data.flowUnit).toBe('L/s');
		expect(data.headUnit).toBe('m');
		expect(data.curve.map((p) => [Number(p.x.toFixed(9)), p.y])).toEqual([
			[0, 30],
			[10, 28],
			[20, 22],
			[30, 12]
		]);
		expect(data.extrapolated).toEqual([]);
		expect(data.system?.map((p) => Number(p.x.toFixed(9)))).toEqual([0, 10, 20, 30]);
		expect(data.system?.map((p) => p.y)).toEqual([12, 14.5, 22, 34.5]);
		expect(data.systemMissing).toBe(0);
		// The flows the curve was requested over (SystemCurveResponse.flowRange), in L/s.
		expect(data.systemSpan?.map((v) => Number(v.toFixed(9)))).toEqual([0, 30]);
		expect(data.operating).toEqual({ x: expect.closeTo(20, 9), y: 22 });
		expect(data.range?.map((v) => Number(v.toFixed(9)))).toEqual([0, 30]);

		const us = pumpChartData(pumpResult(), IMPERIAL_UNITS, [0, 0.03]);
		expect(us.systemSpan).toBeNull();
		expect(us.flowUnit).toBe('gpm');
		expect(us.headUnit).toBe('ft');
		expect(us.operating?.x).toBeCloseTo(0.02 / GPM, 9);
		expect(us.operating?.y).toBeCloseTo(22 / FT, 9);
	});

	it('dashes the extrapolation from the curve’s end to an operating point beyond it', () => {
		const data = pumpChartData(
			pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(data.curve).toHaveLength(4);
		expect(data.extrapolated).toHaveLength(1);
		const [from, to] = data.extrapolated[0]!;
		expect([from!.x, from!.y]).toEqual([expect.closeTo(30, 9), 12]);
		expect([to!.x, to!.y]).toEqual([expect.closeTo(34, 9), 7.5]);
		expect(data.inCurveRange).toBe(false);
	});

	it('dashes an operating point below a curve that starts above zero flow', () => {
		const data = pumpChartData(
			pumpResult({
				curve: [
					{ flow: 0.01, head: 28 },
					{ flow: 0.03, head: 12 }
				],
				operatingFlow: 0.005,
				operatingHead: 29,
				inCurveRange: false
			}),
			SI_UNITS,
			[0.01, 0.03]
		);
		expect(data.extrapolated).toEqual([
			[
				{ x: expect.closeTo(5, 9), y: 29 },
				{ x: expect.closeTo(10, 9), y: 28 }
			]
		]);
	});

	it('dashes sampled points outside the data range at the operating speed', () => {
		// A curve sampled beyond its data (made-up): data 0–0.03 m³/s at rated speed, 80 % speed.
		const data = pumpChartData(
			pumpResult({
				speed: 0.8,
				curve: [
					{ flow: 0, head: 19.2 },
					{ flow: 0.012, head: 17 },
					{ flow: 0.024, head: 7.7 },
					{ flow: 0.03, head: 3 }
				],
				operatingFlow: 0.012,
				operatingHead: 17
			}),
			SI_UNITS,
			[0, 0.03]
		);
		expect(data.range?.map((v) => Number(v.toFixed(9)))).toEqual([0, 24]);
		expect(data.curve.map((p) => p.y)).toEqual([19.2, 17, 7.7]);
		expect(data.extrapolated.map((line) => line.map((p) => p.y))).toEqual([[7.7, 3]]);
		expect(data.curveRows.map((r) => r.extrapolated)).toEqual([false, false, false, true]);
	});

	it('takes the sampled curve’s span as the data range when the curve definition is unknown', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS);
		expect(data.range?.map((v) => Number(v.toFixed(9)))).toEqual([0, 30]);
		expect(data.extrapolated).toEqual([]);
	});

	it('has no operating point when the pump is off, and no system curve when none is given', () => {
		const data = pumpChartData(
			pumpResult({ status: 'off', operatingFlow: 0, operatingHead: -5 }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(data.operating).toBeNull();
		expect(data.extrapolated).toEqual([]);
		expect(data.system).toBeNull();
		expect(data.systemRows).toEqual([]);
	});

	it('leaves system-curve points without a solution as gaps, with the API’s reason', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], systemCurveResponse('P1', [1]));
		expect(data.system?.map((p) => p.y)).toEqual([12, null, 22, 34.5]);
		expect(data.systemMissing).toBe(1);
		expect(data.systemRows).toEqual([
			{ flow: '0', head: '12', npsha: '—', note: '' },
			{ flow: '10', head: '—', npsha: '—', note: 'made-up reason: not converged' },
			{ flow: '20', head: '22', npsha: '—', note: '' },
			{ flow: '30', head: '34.5', npsha: '—', note: '' }
		]);
	});

	it('tells a point’s reason with names and display units, keeping the API’s sentence', () => {
		// The pump-transfer example's V1 made an FCV set to 0.02 m³/s (made-up test input): the
		// point at 0.03 m³/s is beyond what it passes.
		const project = pumpTransferExample();
		project.components[2] = {
			type: 'valve',
			valveType: 'fcv',
			id: 'V1',
			name: 'Flow limiter',
			elevation: 0,
			status: 'active',
			setpoint: 0.02,
			ports: project.components[2]!.ports
		};
		const curve = systemCurveResponse('P1', [3]);
		const message =
			"no steady state carries this flow: every way from the pump's discharge back to its " +
			"suction, through the network or a reservoir or reference node, passes FCV 'V1', which " +
			'passes at most 0.02 m³/s that way (an FCV passes neither reverse flow nor more than its setpoint)';
		curve.points[3] = systemCurvePoint({
			flow: 0.03,
			message,
			reason: 'beyond_limit',
			componentIds: ['V1'],
			limitFlow: 0.02,
			passedFlow: 0.02
		});
		const names = { project, solved: project };
		const row = pumpChartData(pumpResult(), IMPERIAL_UNITS, [0, 0.03], curve, names).systemRows[3];
		expect(row).toEqual({
			flow: String(Number((0.03 / GPM).toPrecision(4))),
			head: '—',
			npsha: '—',
			note:
				"No steady state carries this flow: every way from the pump's discharge back to its " +
				'suction, through the network or a reservoir or reference node, passes Flow limiter, ' +
				`which passes at most ${Number((0.02 / GPM).toPrecision(4))} gpm that way (an FCV ` +
				'passes neither reverse flow nor more than its flow setpoint).',
			detail: message
		});
		// Without names, the API's sentence, with no detail; a point with a head has neither.
		const plain = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], curve).systemRows;
		expect(plain[3]).toEqual({ flow: '30', head: '—', npsha: '—', note: message });
		expect(pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], curve, names).systemRows[0]).toEqual({
			flow: '0',
			head: '12',
			npsha: '—',
			note: ''
		});
		// Other cases' curves are told the same way.
		const [other] = otherCasesData(
			[{ key: 'S1', name: 'Winter', result: pumpResult(), stale: false, system: curve }],
			SI_UNITS,
			[0, 0.03],
			1,
			names
		);
		expect(other!.systemRows[3]!.note).toContain(
			'passes Flow limiter, which passes at most 20 L/s'
		);
		expect(other!.systemRows[3]!.detail).toBe(message);
	});

	it('formats data-table rows to 4 significant figures', () => {
		const data = pumpChartData(pumpResult(), IMPERIAL_UNITS, [0, 0.03]);
		expect(data.curveRows[1]).toEqual({
			flow: String(Number((0.01 / GPM).toPrecision(4))),
			head: String(Number((28 / FT).toPrecision(4))),
			extrapolated: false
		});
	});
});

describe('pumps not running', () => {
	it('marks a pump held at zero flow at the head the API reports, and an off pump not at all', () => {
		const held = pumpChartData(
			pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 30 }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(held.operating).toBeNull();
		expect(held.held).toEqual({ x: 0, y: 30 });
		const off = pumpChartData(
			pumpResult({ status: 'off', operatingFlow: 0, operatingHead: 0 }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(off.operating).toBeNull();
		expect(off.held).toBeNull();
	});

	it('gives other cases’ table rows a bare speed, for "Speed (%)", and none for an off pump', () => {
		// pumps-results-layout.md §5.3, the data region: bare numbers under "Speed (%)".
		const rows = otherCasesData(
			[
				{
					key: 'S1',
					name: 'Slower',
					result: pumpResult({ speed: 0.873214 }),
					stale: false,
					system: null
				},
				{
					key: 'S2',
					name: 'Off',
					result: pumpResult({ status: 'off', operatingFlow: 0, operatingHead: 0 }),
					stale: false,
					system: null
				},
				{
					key: 'S3',
					name: 'Held',
					result: pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 30 }),
					stale: true,
					system: null
				}
			],
			SI_UNITS,
			[0, 0.03],
			1
		).map((o) => o.row);
		expect(rows).toEqual([
			{ flow: '20', head: '22', speed: '87.32', state: 'Running' },
			{ flow: '—', head: '—', speed: '—', state: 'Off' },
			{ flow: '0', head: '30', speed: '100', state: 'Held at zero flow' }
		]);
	});
});

// The notes the screen and the image both use (proposal export.md §3.4).
describe('chart notes', () => {
	it('tells the pump, the system curve, how it was computed and the extrapolation', () => {
		const data = pumpChartData(
			pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false }),
			SI_UNITS,
			[0, 0.03],
			systemCurveResponse('P1', [1])
		);
		const notes = chartNotes({
			data,
			result: pumpResult(),
			system: { status: 'ready', curve: systemCurveResponse('P1', [1]) }
		});
		expect(notes.pump).toBeNull();
		expect(notes.curve).toEqual({
			kind: 'missing',
			text:
				'1 of 4 system-curve points have no head: the line has gaps there, and the data table ' +
				'says why for each (no steady state carries the flow, its head is undetermined, its ' +
				'solve did not converge, or it was not computed).'
		});
		expect(notes.method).toBe(
			'System curve: the network of this solve, solved again with the pump replaced by each of ' +
				'4 evenly spaced flows from 0 to 30 L/s (other pumps running, valves following their ' +
				'rules); the system head at each flow is the EGL at the discharge minus the EGL at the ' +
				'suction.'
		);
		expect(notes.extrapolated).toBe(
			"Dashed: the pump curve extrapolated beyond its data (0 to 30 L/s at this speed), along the curve's end slope, as the solver does."
		);
		// The image has no data table: it says where the reasons are instead.
		const image = chartNotes({
			data,
			result: pumpResult(),
			system: { status: 'ready', curve: systemCurveResponse('P1', [1]) },
			reasonsIn: 'the workbook says'
		});
		expect(image.curve?.text).toBe(
			'1 of 4 system-curve points have no head: the line has gaps there, and the workbook says ' +
				'why for each (no steady state carries the flow, its head is undetermined, its solve did ' +
				'not converge, or it was not computed).'
		);
		expect({ ...image, curve: null }).toEqual({ ...notes, curve: null });
	});

	it('says why the system curve is not shown, and when the pump is off or held', () => {
		const result = pumpResult();
		const data = pumpChartData(result, SI_UNITS);
		const curve = (system: Parameters<typeof chartNotes>[0]['system']) =>
			chartNotes({ data, result, system }).curve;
		expect(curve(undefined)).toEqual({
			kind: 'cancelled',
			text: 'The system curve has not been computed for this solve.'
		});
		expect(curve({ status: 'loading' })?.kind).toBe('loading');
		expect(curve({ status: 'error', message: 'Made-up message.' })).toEqual({
			kind: 'error',
			text: 'The system curve could not be computed: Made-up message.'
		});
		expect(curve({ status: 'cancelled', by: 'user' })?.text).toBe(
			'The system curve was not computed: you cancelled it.'
		);
		expect(curve({ status: 'cancelled', by: 'goalSeek' })?.text).toBe(
			'The system curve was not computed: a goal seek was started.'
		);
		expect(curve({ status: 'cancelled', by: 'solve' })?.text).toBe(
			'The system curve was not computed: a new solve was started.'
		);
		const allMissing = systemCurveResponse('P1', [0, 1, 2, 3]);
		expect(
			chartNotes({
				data: pumpChartData(result, SI_UNITS, null, allMissing),
				result,
				system: { status: 'ready', curve: allMissing }
			}).curve?.text
		).toMatch(/^No point of the system curve has a head, so it is not drawn; the data table/);

		const off = pumpResult({ status: 'off', operatingFlow: 0 });
		expect(
			chartNotes({ data: pumpChartData(off, SI_UNITS), result: off, system: undefined }).pump
		).toBe(
			'This pump is off: it carries no flow. Its curve is shown at its set speed, for reference.'
		);
		const held = pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 31 });
		expect(
			chartNotes({ data: pumpChartData(held, SI_UNITS), result: held, system: undefined }).pump
		).toBe(
			'This pump is held at zero flow by its check (see its flag). The diamond marks zero flow at the head across the pump.'
		);
	});
});

describe('untickedAfter: unticking a case in a capped list', () => {
	const listed = ['', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6'];
	it('unticks the case and every case not shown now, so the place it leaves stays free', () => {
		// Five shown ('' to S4), S5 and S6 past the cap: both read as unticked and stay so.
		expect(untickedAfter([], 'S2', listed, ['', 'S1', 'S2', 'S3', 'S4'])).toEqual([
			'S2',
			'S5',
			'S6'
		]);
	});
	it('keeps the cases unticked before, first and once each', () => {
		expect(untickedAfter(['S1'], 'S3', listed, ['', 'S2', 'S3', 'S4', 'S5'])).toEqual([
			'S1',
			'S3',
			'S6'
		]);
		expect(untickedAfter(['S6'], 'S6', listed, ['', 'S1', 'S2', 'S3', 'S4'])).toEqual(['S6', 'S5']);
	});
	it('adds only the case when every case is shown', () => {
		expect(untickedAfter([], '', ['', 'S1'], ['', 'S1'])).toEqual(['']);
	});
});

// One choice of cases for both charts (proposal pumps-results-layout.md §9 S8, the owner's answer
// 2): the user's unticks one set, each chart's cases past its cap its own.
describe('one choice of cases: untickCase and tickCase', () => {
	const none: CaseChoice = { unticked: [], pump: [], group: [] };
	/** The pump chart's list: five drawn of six (S6 past its cap). */
	const pump = (shown = ['S1', 'S2', 'S3', 'S4', 'S5']): CaseList => ({
		listed: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
		shown,
		cap: 5
	});
	/** The card's list, in its own order: six drawn of seven (S7 past its cap). */
	const group = (shown = ['S6', 'S5', 'S4', 'S3', 'S2', 'S1']): CaseList => ({
		listed: ['S6', 'S5', 'S4', 'S3', 'S2', 'S1', 'S7'],
		shown,
		cap: 6
	});

	it('unticks a case under both lists, and on each chart that drew it keeps the cases past its cap off there only', () => {
		const next = untickCase(none, 'S2', { pump: pump(), group: group() });
		expect(next).toEqual({ unticked: ['S2'], pump: ['S6'], group: ['S7'] });
		// From the card's list, the same: one set, each chart's own past its own cap.
		expect(untickCase(none, 'S2', { pump: pump(), group: group() })).toEqual(
			untickCase(none, 'S2', { group: group(), pump: pump() })
		);
	});

	it('leaves a chart that did not draw the case as it was', () => {
		// S6 is past the pump chart's cap: only the card frees a place.
		expect(untickCase(none, 'S6', { pump: pump(), group: group() })).toEqual({
			unticked: ['S6'],
			pump: [],
			group: ['S7']
		});
		// A chart with no list (the card without a station) is left alone.
		expect(untickCase(none, 'S2', { pump: pump() })).toEqual({
			unticked: ['S2'],
			pump: ['S6'],
			group: []
		});
	});

	it('never makes a case the user unticked one of a chart’s own, and keeps each set once', () => {
		const first = untickCase(none, 'S2', { pump: pump(), group: group() });
		// S2 unticked: not drawn, but the user's, so not past a cap.
		const second = untickCase(first, 'S3', {
			pump: pump(['S1', 'S3', 'S4', 'S5']),
			group: group(['S6', 'S5', 'S4', 'S3', 'S1'])
		});
		expect(second).toEqual({ unticked: ['S2', 'S3'], pump: ['S6'], group: ['S7'] });
		// Unticked again (the card's list after the pump chart's): each set holds it once.
		expect(untickCase(second, 'S3', { group: group(['S6', 'S5', 'S4', 'S1']) })).toEqual(second);
	});

	it('ticks a case again under both lists, where each chart has room', () => {
		const off = untickCase(none, 'S2', { pump: pump(), group: group() });
		const lists = {
			pump: pump(['S1', 'S3', 'S4', 'S5']),
			group: group(['S6', 'S5', 'S4', 'S3', 'S1'])
		};
		// Under the pump chart's list or the card's: ticked on both, each chart's own unchanged.
		expect(tickCase(off, 'S2', 'pump', lists)).toEqual({
			unticked: [],
			pump: ['S6'],
			group: ['S7']
		});
		expect(tickCase(off, 'S2', 'group', lists)).toEqual({
			unticked: [],
			pump: ['S6'],
			group: ['S7']
		});
	});

	it('ticks a case past its chart’s cap into the place left free, on that chart alone', () => {
		const off = untickCase(none, 'S2', { pump: pump(), group: group() });
		const lists = {
			pump: pump(['S1', 'S3', 'S4', 'S5']),
			group: group(['S6', 'S5', 'S4', 'S3', 'S1'])
		};
		expect(tickCase(off, 'S6', 'pump', lists)).toEqual({
			unticked: ['S2'],
			pump: [],
			group: ['S7']
		});
	});

	it('brings a case ticked under one list back on the other only into a free place: a full chart keeps every case it draws', () => {
		// The card drew S2 and lost it; S7 was then ticked into its place, so the card is full.
		const off = untickCase(none, 'S2', { pump: pump(), group: group() });
		const full = tickCase(off, 'S7', 'group', {
			pump: pump(['S1', 'S3', 'S4', 'S5']),
			group: group(['S6', 'S5', 'S4', 'S3', 'S1'])
		});
		expect(full).toEqual({ unticked: ['S2'], pump: ['S6'], group: [] });
		// S2 ticked again under the pump chart's list: drawn there, past the cap on the card.
		expect(
			tickCase(full, 'S2', 'pump', {
				pump: pump(['S1', 'S3', 'S4', 'S5']),
				group: group(['S6', 'S5', 'S4', 'S3', 'S1', 'S7'])
			})
		).toEqual({ unticked: [], pump: ['S6'], group: ['S2'] });
	});
});

describe('the pump chart’s cases: slots and markers (pumps-results-layout.md §9 S8)', () => {
	const other = (key: string, status: 'running' | 'off' | 'no_flow' = 'running') => ({
		key,
		result: { status }
	});
	const others = [
		other('A', 'off'),
		other('B'),
		other('C', 'no_flow'),
		other('D'),
		other('E'),
		other('F'),
		other('G', 'off')
	];
	const keys = (list: readonly { key: string }[]) => list.map((o) => o.key);

	it('gives a case in which the pump is off no slot while the other cases’ system curves are off', () => {
		const cases = pumpChartCases(others, [], false);
		expect(keys(cases.listed)).toEqual(['B', 'C', 'D', 'E', 'F']);
		expect(keys(cases.shown)).toEqual(['B', 'C', 'D', 'E', 'F']);
		expect(keys(cases.off)).toEqual(['A', 'G']);
		// A pump held at zero flow has its point drawn: it keeps its slot.
		expect(keys(cases.listed)).toContain('C');
	});

	it('gives it its slot while they are on, which can put a case drawn before past the cap', () => {
		const cases = pumpChartCases(others, [], true);
		expect(keys(cases.listed)).toEqual(['A', 'B', 'C', 'D', 'E', 'F', 'G']);
		expect(keys(cases.shown)).toEqual(['A', 'B', 'C', 'D', 'E']);
		expect(keys(cases.off)).toEqual([]);
	});

	it('draws the first listed the choice leaves ticked, five at most', () => {
		expect(keys(pumpChartCases(others, ['B', 'A'], false).shown)).toEqual(['C', 'D', 'E', 'F']);
		expect(keys(pumpChartCases(others, ['B'], true).shown)).toEqual(['A', 'C', 'D', 'E', 'F']);
		// An unticked case in which the pump is off still takes no slot, and is still named.
		expect(keys(pumpChartCases(others, ['A'], false).off)).toEqual(['A', 'G']);
	});

	it('gives each case drawn its place’s marker, five shapes, the glyphs Chart.js draws', () => {
		expect(CASE_MARKERS).toEqual(['triangle', 'rect', 'star', 'crossRot', 'triangleDown']);
		expect(CASE_MARKERS.map((m) => MARKER_SYMBOLS[m])).toEqual(['△', '□', '✳\uFE0E', '×', '▽']);
		expect(caseMarkers(['B', 'C', 'D'], ['B', 'C', 'D', 'E'])).toEqual({
			B: 'triangle',
			C: 'rect',
			D: 'star'
		});
	});

	it('keeps each case’s marker while five cases or fewer are listed, whatever is ticked', () => {
		const listed = ['B', 'C', 'D', 'E', 'F'];
		const all = caseMarkers(listed, listed);
		// C unticked: no other case's marker changes; ticked again, it has its own back.
		const without = caseMarkers(['B', 'D', 'E', 'F'], listed, all);
		expect(without).toEqual({ B: all.B, D: all.D, E: all.E, F: all.F });
		expect(caseMarkers(listed, listed, without)).toEqual(all);
		// From nothing remembered, the same: each its place's.
		expect(caseMarkers(['F', 'C'], listed)).toEqual({ C: all.C, F: all.F });
	});

	it('keeps the marker of a case that stays drawn past five listed, through an untick, the curves switched and a tick', () => {
		const off = pumpChartCases(others, [], false);
		const first = caseMarkers(keys(off.shown), keys(off.listed));
		expect(first).toEqual({
			B: 'triangle',
			C: 'rect',
			D: 'star',
			E: 'crossRot',
			F: 'triangleDown'
		});
		// The curves switched on: A and B drawn again before them, F past the cap. Those that
		// stay keep theirs; A takes the one F left.
		const on = pumpChartCases(others, [], true);
		const second = caseMarkers(keys(on.shown), keys(on.listed), first);
		expect(second).toEqual({
			A: 'triangleDown',
			B: 'triangle',
			C: 'rect',
			D: 'star',
			E: 'crossRot'
		});
		// D unticked, then G ticked into its place: the others keep theirs, G takes D's.
		const third = caseMarkers(['A', 'B', 'C', 'E'], keys(on.listed), second);
		expect(third).toEqual({ A: 'triangleDown', B: 'triangle', C: 'rect', E: 'crossRot' });
		const fourth = caseMarkers(['A', 'B', 'C', 'E', 'G'], keys(on.listed), third);
		expect(fourth).toEqual({ ...third, G: 'star' });
		// Never two cases one marker.
		for (const set of [first, second, third, fourth]) {
			expect(new Set(Object.values(set)).size).toBe(Object.keys(set).length);
		}
	});

	it('names the cases that take no slot in one line, the screen’s and the image’s', () => {
		expect(offCasesNote(['Pump PA off', 'Both pumps off (out of date)'])).toBe(
			'Off in this case (no operating point): Pump PA off; Both pumps off (out of date).'
		);
		expect(offCasesNote([])).toBeNull();
	});

	it('gives otherCasesData the markers by case, by default each its place’s', () => {
		const input = ['S1', 'S2'].map((key) => ({
			key,
			name: key,
			result: pumpResult(),
			stale: false,
			system: null
		}));
		expect(otherCasesData(input, SI_UNITS, null, 1).map((o) => o.marker)).toEqual([
			'triangle',
			'rect'
		]);
		expect(
			otherCasesData(input, SI_UNITS, null, 1, null, { S1: 'star', S2: 'triangleDown' }).map(
				(o) => o.marker
			)
		).toEqual(['star', 'triangleDown']);
	});
});

// The notes about the values in the screen's order (proposal pumps-results-layout.md §5.3):
// chartNotes' own sentences, each once, the image's footer in chartNotes' order.
describe('valueNotes: the notes about the values, in the screen’s order', () => {
	/** Every panel, a rising stretch and an extrapolated duty (made-up test input). */
	const result = pumpResult({
		operatingFlow: 0.034,
		operatingHead: 7.5,
		inCurveRange: false,
		efficiencyCurve: [
			{ flow: 0.004, efficiency: 0.4 },
			{ flow: 0.012, efficiency: 0.7 },
			{ flow: 0.02, efficiency: 0.6 }
		],
		bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false },
		powerCurve: [
			{ flow: 0.004, shaftPower: 2000 },
			{ flow: 0.02, shaftPower: 5000 }
		],
		npshrCurve: [
			{ flow: 0, npshr: 1 },
			{ flow: 0.03, npshr: 4 }
		],
		risingHeadRanges: [
			{ flowMin: 0, flowMax: 0.005 },
			{ flowMin: 0.007, flowMax: 0.009 }
		]
	});
	// NPSHa 10, 8, 4, 1 m against NPSHr 1, 2, 3, 4 m at 0, 10, 20, 30 L/s: NPSHa − NPSHr is +1 m
	// at 20 L/s and −3 m at 30 L/s, so the lines cross at 20 + 10 × 1 / (1 + 3) = 22.5 L/s.
	const curve = systemCurveResponse();
	[10, 8, 4, 1].forEach((npsha, i) => (curve.points[i]!.npshAvailable = npsha));
	const limits: PumpChecksInput = {
		checks: { operatingRegion: { preferredMin: 0.7, preferredMax: 1.2, source: { kind: 'user' } } },
		curve: null,
		sources: { npshMargin: null, operatingRegion: 'your values' }
	};
	const data = pumpChartData(result, SI_UNITS, [0, 0.03], curve, null, limits);
	const shown: PanelKey[] = ['head', 'efficiency', 'power', 'npsh'];
	const notes = chartNotes({
		data,
		result,
		system: { status: 'ready', curve },
		shown,
		checksShown: true
	});
	const rising = [
		'The head rises with flow from 0 to 5 L/s (amber): a system curve can cross the pump curve more than once there.',
		'The head rises with flow from 7 to 9 L/s (amber): a system curve can cross the pump curve more than once there.'
	];
	const crossing =
		'NPSHa falls below NPSHr at about 22.5 L/s (read from the drawn lines): the pump would cavitate beyond that flow.';

	it('puts the facts that qualify a reading first: each rising range, then the NPSHa crossing', () => {
		const v = valueNotes(notes, data);
		expect(v.first).toEqual([...rising, crossing]);
		expect(v.facts.map((n) => n.slice(0, 20))).toEqual([
			'Best efficiency poin',
			'Shutoff head (–): 30'
		]);
		expect(v.panels.map((n) => n.slice(0, 20))).toEqual([
			'Efficiency: the duty',
			'Shaft power ρgQH/η o'
		]);
		expect(v.extrapolated).toBe(notes.extrapolated);
		expect(v.method).toBe(notes.method);
		expect(v.checks).toEqual(notes.checks);
		expect(v.checks.at(-1)).toMatch(/^These are the limits of the design checks/);
	});

	it('keeps every sentence of the figure’s notes once, in the words the image gives', () => {
		const v = valueNotes(notes, data);
		const screen = [
			...v.first,
			...v.facts,
			...v.panels,
			...(v.extrapolated ? [v.extrapolated] : []),
			...(v.method ? [v.method] : []),
			...v.checks
		];
		// The image's footer, less what the strip shows (the pump's and the curve's state).
		const image = imageNoteLines(notes, [], {}).filter(
			(line) => line !== notes.pump && line !== notes.curve?.text
		);
		expect([...screen].sort()).toEqual([...image].sort());
		expect(new Set(screen).size).toBe(screen.length);
		// The image keeps chartNotes' order: method, extrapolation, panels, facts, checks.
		expect(image[0]).toBe(notes.method);
		expect(image.indexOf(crossing)).toBeLessThan(image.indexOf(rising[0]!));
	});

	it('has no first notes without a rising range or a crossing shown', () => {
		const plain = pumpChartData(pumpResult(), SI_UNITS, null, systemCurveResponse());
		const v = valueNotes(
			chartNotes({ data: plain, result: pumpResult(), system: undefined }),
			plain
		);
		expect(v.first).toEqual([]);
		// The NPSH panel hidden: its crossing is not a note, so not a first one.
		const hidden = chartNotes({
			data,
			result,
			system: { status: 'ready', curve },
			shown: ['head', 'efficiency', 'power']
		});
		expect(valueNotes(hidden, data).first).toEqual(rising);
	});
});
