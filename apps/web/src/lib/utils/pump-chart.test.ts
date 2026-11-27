/**
 * Pump chart data: the curve inside its data is solid, the extrapolated part dashed, and every
 * point is a reported value in display units. Pump results are made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import { designators } from '../testing/helpers';
import { pumpResult, systemCurvePoint, systemCurveResponse } from '../testing/results';
import { imageNoteLines } from './export/chart-image';
import { pumpTransferExample } from './examples';
import {
	caseNamed,
	caseTagOf,
	chartReadout,
	caseTags,
	caseTagText,
	caseTagWords,
	chartNotes,
	compareCaseTags,
	inCaseOrder,
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
import { MAX_SCENARIOS, scenariosOf, withScenarios } from './scenarios';
import { formatNumber, fromSI, IMPERIAL_UNITS, SI_UNITS } from './units';
import { condenserCase, condenserCaseProject, condenserMembers } from './condenser-charts.testing';
import { systemPointNote } from './system-curve-text';
import { groupChartData } from './pump-group-chart';
import { pumpChartConfig } from './pump-chart-config';

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
			names,
			{ S1: 1 }
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
			1,
			null,
			{ S1: 1, S2: 2, S3: 3 }
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

	it('never holds off the other chart a case the user did not untick: a tick unticks nothing', () => {
		// S7 past the card's cap at the untick of S1, never unticked by the user; ticked on the card
		// into S1's place. The pump chart is full and lists S7 past its cap by order: it stays so,
		// not one of its own, so another pump's chart with room draws it.
		const choice: CaseChoice = { unticked: ['S1'], pump: [], group: ['S7'] };
		const lists = {
			pump: {
				listed: ['S2', 'S3', 'S4', 'S5', 'S6', 'S7'],
				shown: ['S2', 'S3', 'S4', 'S5', 'S6'],
				cap: 5
			},
			group: group(['S6', 'S5', 'S4', 'S3', 'S2'])
		};
		expect(tickCase(choice, 'S7', 'group', lists)).toEqual({
			unticked: ['S1'],
			pump: [],
			group: []
		});
	});

	it('never holds off the other chart a case it does not list (its pump off there), though it is full', () => {
		// S1 unticked and ticked again on the card; the pump chart, full, does not list S1 (this
		// pump is off in it, the other cases' system curves off): another pump's chart draws it.
		const choice: CaseChoice = { unticked: ['S1'], pump: [], group: ['S7'] };
		const lists = {
			pump: {
				listed: ['S2', 'S3', 'S4', 'S5', 'S6', 'S7'],
				shown: ['S2', 'S3', 'S4', 'S5', 'S6'],
				cap: 5
			},
			group: group(['S6', 'S5', 'S4', 'S3', 'S2'])
		};
		expect(tickCase(choice, 'S1', 'group', lists)).toEqual({
			unticked: [],
			pump: [],
			group: ['S7']
		});
	});
});

describe('the pump chart’s cases: slots (pumps-results-layout.md §9 S8)', () => {
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

	// The five hollow markers (caseMarkers, MARKER_SYMBOLS) went with nit 5 (owner, 2026-11-12;
	// Q1 "Shapes go too", Q2 "By list place"; docs/proposals/pumps-nits.md item 5, slice 5b): the
	// tests that pinned them (S8 MARK-1/2/3, the five-case boundary, a marker kept past five, the
	// off line by name and otherCasesData's markers) are replaced by the number tests below
	// ("case numbers: caseTags and caseTagWords"), which hold each case's number fixed by case for
	// any count, with no fallback.
});

// Case numbers (owner, 2026-11-12, nit 5: "I don't like the use of special characters to
// designate pumps and groups"; Q2 "By list place"; docs/proposals/pumps-nits.md item 5, slice
// 5b): one number per case for the whole Pumps tab, "Base" for the base case, then 1 to n by the
// scenario's place in the Scenarios list. They replace the five hollow markers (caseMarkers,
// MARKER_SYMBOLS, the S8 tests MARK-1/2/3 and the five-case boundary): numbers never run out, so
// nothing falls back and nothing is remembered.
describe('case numbers: caseTags and caseTagWords (nit 5, slice 5b)', () => {
	const scenario = (id: string, name = `Scenario ${id}`) => ({ id, name, overrides: [] });
	const withCases = (ids: readonly string[]) =>
		withScenarios(
			pumpTransferExample(),
			ids.map((id) => scenario(id))
		);

	it('numbers the base case "Base", then each scenario 1 to n in the Scenarios list’s order', () => {
		expect(caseTags(withCases(['S1', 'S2', 'S3', 'S4']))).toEqual({
			'': 'Base',
			S1: 1,
			S2: 2,
			S3: 3,
			S4: 4
		});
		// A project without scenarios: the base case alone.
		expect(caseTags(pumpTransferExample())).toEqual({ '': 'Base' });
	});

	it('numbers by place alone: the ids play no part', () => {
		// S1, S3, S2 in the list: 1, 2, 3 (by id it would read 1, 3, 2).
		expect(caseTags(withCases(['S1', 'S3', 'S2']))).toEqual({ '': 'Base', S1: 1, S3: 2, S2: 3 });
		// Ids that are not "S" and a number (an imported project's): by place too.
		expect(caseTags(withCases(['winter', 'X9', 'S7']))).toEqual({
			'': 'Base',
			winter: 1,
			X9: 2,
			S7: 3
		});
	});

	it('renumbers the scenarios after a deleted one, and only those', () => {
		const project = withCases(['S1', 'S2', 'S3', 'S4']);
		const deleted = withScenarios(
			project,
			scenariosOf(project).filter((s) => s.id !== 'S2')
		);
		expect(caseTags(deleted)).toEqual({ '': 'Base', S1: 1, S3: 2, S4: 3 });
		// One added at the end moves no number.
		const added = withScenarios(project, [...scenariosOf(project), scenario('S5')]);
		expect(caseTags(added)).toEqual({ ...caseTags(project), S5: 5 });
	});

	it('numbers eight cases 1 to 8, and the most a project holds, with no fallback: every number its own', () => {
		const eight = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'];
		expect(caseTags(withCases(eight))).toEqual({
			'': 'Base',
			...Object.fromEntries(eight.map((id, i) => [id, i + 1]))
		});
		const ids = Array.from({ length: MAX_SCENARIOS }, (_, i) => `S${i + 1}`);
		const all = caseTags(withCases(ids));
		expect(ids.map((id) => all[id])).toEqual(ids.map((_, i) => i + 1));
		expect(new Set(Object.values(all)).size).toBe(MAX_SCENARIOS + 1);
	});

	it('reads the Scenarios list alone: no value, override, name or description changed moves a number', () => {
		// Ticks, unticks, the case shown, the pump shown and the card's members are page state, never
		// in the project; a solve changes no project. What a lineup or member change writes into the
		// project (a pump's status override, a name that follows its pumps, D24 §4.5) moves none.
		const project = withCases(['S1', 'S2', 'S3']);
		const tags = caseTags(project);
		const [s1, s2, s3] = scenariosOf(project);
		const edited = withScenarios(structuredClone(project), [
			{
				...s1!,
				name: 'Pump P1 off',
				overrides: [{ kind: 'component', componentId: 'P1', field: 'status', value: 'off' }]
			},
			{ ...s2!, name: 'Renamed', description: 'A note' },
			s3!
		]);
		const pump = edited.components.find((c) => c.id === 'P1')!;
		edited.components = edited.components.map((c) =>
			c === pump ? { ...c, name: 'Transfer pump, renamed' } : c
		);
		expect(caseTags(edited)).toEqual(tags);
		// The same project, again: the same numbers.
		expect(caseTags(structuredClone(project))).toEqual(tags);
	});

	it('words a tag for a screen reader: "Case 3:", "Cases 4, 5 and 6:", in number order', () => {
		expect(caseTagWords([3])).toBe('Case 3:');
		expect(caseTagWords([1, 5])).toBe('Cases 1 and 5:');
		expect(caseTagWords([4, 5, 6])).toBe('Cases 4, 5 and 6:');
		expect(caseTagWords([6, 4, 5])).toBe('Cases 4, 5 and 6:');
	});

	it('gives otherCasesData each case’s tag, fixed by case, never by its place among those given', () => {
		const input = ['', 'S1', 'S2'].map((key) => ({
			key,
			name: key ? `Case ${key}` : 'Base case',
			result: pumpResult(),
			stale: false,
			system: null
		}));
		const tags = { '': 'Base', S1: 3, S2: 1 } as const;
		expect(otherCasesData(input, SI_UNITS, null, 1, null, tags).map((o) => o.tag)).toEqual([
			'Base',
			3,
			1
		]);
		// One case alone: its own tag, not the first place's.
		expect(otherCasesData(input.slice(2), SI_UNITS, null, 1, null, tags).map((o) => o.tag)).toEqual(
			[1]
		);
	});

	// Review CASE-NUMBERS-A2 and B3 (rule 4: a case is its number in every list and image): the
	// pump curve another case draws at another speed names each case at that speed with its number,
	// as its ring ("Case 2: Winter") and its system curve ("System curve, case 2") do, so the
	// legend, the tooltips and the image's legend name one case one way. It named them by name
	// alone, "Pump curve at 90 % speed (Winter; Summer)", beside "System curve, case 2".
	it('names each case of a pump curve at another speed with its number, the base case by its name', () => {
		const at = (key: string, name: string, speed: number, stale = false) => ({
			key,
			name,
			result: pumpResult({ speed }),
			stale,
			system: null
		});
		const tags = { '': 'Base', S1: 1, S2: 2, S3: 3 } as const;
		const input = [
			at('S2', 'Winter', 0.9),
			at('S3', 'Summer', 0.9, true),
			at('', 'Base case', 0.8),
			at('S1', 'Higher tank', 0.8)
		];
		expect(otherCasesData(input, SI_UNITS, null, 1, null, tags).map((o) => o.curveLabel)).toEqual([
			'Pump curve at 90 % speed (case 2: Winter; case 3: Summer, out of date)',
			'Pump curve at 90 % speed (case 2: Winter; case 3: Summer, out of date)',
			'Pump curve at 80 % speed (Base case; case 1: Higher tank)',
			'Pump curve at 80 % speed (Base case; case 1: Higher tank)'
		]);
	});

	it('names the cases off in this case with their numbers, the screen’s line and the image’s', () => {
		expect(
			offCasesNote([
				{ tag: 1, label: 'Pump PA off' },
				{ tag: 4, label: 'Both pumps off (out of date)' }
			])
		).toEqual(
			'Off in this case (no operating point): case 1: Pump PA off; case 4: Both pumps off (out of date).'
		);
		// The base case is its name: "Base" adds nothing to "Base case".
		expect(
			offCasesNote([
				{ tag: 'Base', label: 'Base case' },
				{ tag: 2, label: 'Pump PB off' }
			])
		).toEqual('Off in this case (no operating point): Base case; case 2: Pump PB off.');
		expect(offCasesNote([])).toBeNull();
		for (const line of [
			offCasesNote([{ tag: 1, label: 'Pump PA off' }])!,
			offCasesNote([{ tag: 'Base', label: 'Base case' }])!
		]) {
			expect(designators(line), line).toEqual([]);
		}
	});
});

// The helpers the lists, the rings and the labels share (nit 5, slice 5b): a case's number from
// caseTags, their order ("Base" first, then ascending), the box's text and a case in words.
describe('case numbers: order, the box and the words (nit 5, slice 5b)', () => {
	const tags = { '': 'Base', S1: 1, S2: 2, S3: 3, S10: 10 } as const;

	it('reads a case’s number from caseTags, the base case’s "Base" always, and refuses a case it has none for', () => {
		expect(caseTagOf(tags, 'S2')).toBe(2);
		expect(caseTagOf(tags, '')).toBe('Base');
		expect(caseTagOf({}, '')).toBe('Base');
		// Never a place among those given: a case without a number is a bug, not a case to number.
		expect(() => caseTagOf(tags, 'S9')).toThrow('No case number for case S9.');
	});

	it('orders "Base" first, then ascending as numbers (10 after 3), and lists items in that order', () => {
		const all: ('Base' | number)[] = [10, 3, 'Base', 1];
		expect([...all].sort(compareCaseTags)).toEqual(['Base', 1, 3, 10]);
		expect(compareCaseTags(2, 2)).toBe(0);
		expect(compareCaseTags('Base', 'Base')).toBe(0);
		const items = ['S10', 'S3', '', 'S1'].map((key) => ({ key }));
		expect(inCaseOrder(items, tags).map((i) => i.key)).toEqual(['', 'S1', 'S3', 'S10']);
		// A copy: the items given keep their order.
		expect(items.map((i) => i.key)).toEqual(['S10', 'S3', '', 'S1']);
	});

	it('writes the box’s text in that order, and a case in words with its number, the base case by its name', () => {
		expect(caseTagText([6, 1, 5, 4])).toBe('1, 4, 5, 6');
		expect(caseTagText([3, 'Base'])).toBe('Base, 3');
		expect(caseTagText(['Base'])).toBe('Base');
		expect(caseNamed(2, 'Winter (out of date)')).toBe('case 2: Winter (out of date)');
		expect(caseNamed(2, 'Winter', true)).toBe('Case 2: Winter');
		expect(caseNamed('Base', 'Base case', true)).toBe('Base case');
		for (const words of [caseNamed(2, 'Winter'), caseTagText([1, 2]), caseTagWords([1, 2])]) {
			expect(designators(words), words).toEqual([]);
		}
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
		// Nit 5 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5): the shutoff head's dash
		// named in words, not "(–)"; the same 20 characters read.
		expect(v.facts.map((n) => n.slice(0, 20))).toEqual([
			'Best efficiency poin',
			'Shutoff head (the da'
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
		const image = imageNoteLines(notes, []).filter(
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

// docs/proposals/open-defects-2.md §2 C1 and §3 C3, on the condenser example's recorded answers
// (__fixtures__/condenser-charts.json, apps/api/tests/fixtures/condenser_charts.py): one pump and
// one chiller line, F1's setpoint on /system-curve's grid, so a sampled flow lands on the FCV's
// limit and states its openHead; and the example's Winter case, F1's setpoint between two grid
// flows, where /system-curve's limit point states it (C3).
describe('a pump’s system curve’s vertical part at its FCV’s limit (open-defects-2.md C1)', () => {
	const pumpCard = (name: 'single24' | 'winter') => {
		const c = condenserCase(name);
		const project = condenserCaseProject(name);
		const prefs = project.settings.units;
		const result = c.pumpResults!.P1!;
		const curve = c.pumpSystemCurve!;
		const data = pumpChartData(result, prefs, ratedCurveRange(project, 'P1'), curve, {
			project
		});
		return { project, prefs, result, curve, data };
	};
	const f4 = (v: number) => formatNumber(v, 4);

	it('draws the point at the limit as its foot and a ray up, and says why in each place', () => {
		const { data, curve, result } = pumpCard('single24');
		const at = curve.points.find((p) => p.reason === 'valve_at_switch')!;
		expect(at).toMatchObject({ head: null, openHeadBound: 'lower' });
		const x = fromSI(at.flow, 'L/s');
		expect(data.systemRays).toEqual([{ x, from: at.openHead, bound: 'lower' }]);
		expect(data.system!.find((p) => p.x === x)).toEqual({ x, y: at.openHead, bound: 'lower' });
		// The pump runs at F1's setpoint, on the vertical part.
		expect(data.operating!.x).toBeCloseTo(x, 9);
		expect(data.operating!.y).toBeGreaterThan(at.openHead!);
		// The data table: the range that holds, its reason unchanged; every other gap a dash.
		const row = data.systemRows.find((r) => r.flow === f4(x))!;
		expect(row.head).toBe('≥ 20.72');
		expect(row.note).toMatch(/^The head across the pump is undetermined: at this flow /);
		expect(data.systemRows.filter((r) => r.head === '—')).toHaveLength(16);
		const past = curve.points.filter((p) => p.reason === 'beyond_limit');
		expect(new Set(past.map((p) => p.limitFlow))).toEqual(new Set([at.flow]));
		const notes = chartNotes({ data, result, system: { status: 'ready', curve } });
		expect(notes.curve).toEqual({
			kind: 'missing',
			text:
				`17 of 41 system-curve points have no head: at ${f4(x)} L/s it is undetermined, any head at or above ${f4(at.openHead!)} m holding, drawn as the curve's vertical part from there to the top of the head axis; at the ${past.length} flows sampled beyond ${f4(x)} L/s no steady state carries the flow; ` +
				'the data table says why for each (no steady state carries the flow, its head is undetermined, its solve did not converge, or it was not computed).'
		});
		expect(notes.curve!.text).toMatch(
			/^17 of 41 system-curve points have no head: at 953\.9 L\/s it is undetermined, any head at or above 20\.72 m holding/
		);
		// The readout at that flow: the range, never a bare head.
		expect(chartReadout(data, ['head'], x).find((i) => i.key === 'system')).toEqual({
			key: 'system',
			label: 'System head',
			value: at.openHead,
			unit: 'm',
			bound: 'lower'
		});
		expect(
			chartReadout(data, ['head'], data.system![1]!.x).find((i) => i.key === 'system')
		).not.toHaveProperty('bound');
	});

	// The review of open defects round two, WC-1: P1 runs at F1's setpoint only to round-off, so the
	// readout's default flow (the operating point's) need not be the foot's but lies within the
	// chart's flow floor of it. There the system head is the foot's range, never a bare head (a hair
	// below the foot, Winter on d101793: "System head 21.9 m") nor nothing (a hair above, single24
	// on d101793). Winter's duty is a hair below its foot. single24 is solved to 1e-12 (the
	// recorder's solverOptions, so its fixture is the same on every CPU), which puts its duty
	// exactly at the foot, so its reading is also taken a hair above and a hair below, inside the
	// floor: the two sides d101793 got wrong.
	for (const [name, metric, imperial] of [
		['winter', '≥ 21.9 m', '≥ 71.84 ft'],
		['single24', '≥ 20.72 m', '≥ 67.99 ft']
	] as const) {
		it(`reads the ${name} case’s system head at the duty as its vertical part’s range (${metric}, ${imperial})`, () => {
			const { data, curve, result, project } = pumpCard(name);
			const us = pumpChartData(result, IMPERIAL_UNITS, ratedCurveRange(project, 'P1'), curve, {
				project
			});
			for (const d of [data, us]) {
				const foot = d.system!.find((p) => p.bound)!;
				const at = d.operating!.x;
				if (name === 'winter') expect(at).not.toBe(foot.x);
				else expect(at).toBe(foot.x);
				expect(Math.abs(at - foot.x)).toBeLessThanOrEqual(d.flowFloor);
				// A hair is a millionth of the floor: far past round-off, well inside the floor.
				const hair = d.flowFloor * 1e-6;
				const flows = name === 'winter' ? [at] : [at, foot.x + hair, foot.x - hair];
				for (const flow of flows) {
					expect(
						chartReadout(d, ['head'], flow).find((i) => i.key === 'system'),
						`at ${flow}`
					).toEqual({
						key: 'system',
						label: 'System head',
						value: foot.y,
						unit: d.headUnit,
						bound: 'lower'
					});
				}
				const read = chartReadout(d, ['head'], at);
				// Once, after the pump's head.
				expect(read.map((i) => i.key)).toEqual(['pump', 'system']);
				// Beyond the floor below the foot, the line's own head there, no range.
				expect(
					chartReadout(d, ['head'], foot.x - 2 * d.flowFloor).find((i) => i.key === 'system')
				).not.toHaveProperty('bound');
			}
			const words = (d: typeof data) => {
				const item = chartReadout(d, ['head'], d.operating!.x).find((i) => i.key === 'system')!;
				return `${item.bound === 'lower' ? '≥ ' : ''}${f4(item.value)} ${item.unit}`;
			};
			expect([words(data), words(us)]).toEqual([metric, imperial]);
		});
	}

	it('gives another case’s dotted system curve its vertical part too', () => {
		const { curve, result, project, prefs } = pumpCard('single24');
		const [other] = otherCasesData(
			[{ key: 'S1', name: 'One line', result, stale: false, system: curve }],
			prefs,
			ratedCurveRange(project, 'P1'),
			1,
			{ project },
			{ S1: 1 }
		);
		expect(other!.systemRays).toEqual(pumpCard('single24').data.systemRays);
		expect(other!.system).toEqual(pumpCard('single24').data.system);
		expect(other!.systemRows.find((r) => r.head.startsWith('≥'))!.head).toBe('≥ 20.72');
	});

	it('draws the vertical at the Winter case’s limit point, through P1’s operating point (C3)', () => {
		// P1 runs at F1's setpoint, between two grid flows: /system-curve's limit point there is at
		// F1's switch, so the line turns vertical where P1 runs, as the group chart of the same case
		// does at the duty (D21 4b; open-defects-2.md §1 call 2).
		const { data, result, curve, project } = pumpCard('winter');
		expect(curve.limitPoints).toHaveLength(1);
		const limit = curve.limitPoints[0]!;
		expect(limit).toMatchObject({ head: null, reason: 'valve_at_switch', openHeadBound: 'lower' });
		expect(curve.points.map((p) => p.flow)).not.toContain(limit.flow);
		const x = fromSI(limit.flow, 'L/s');
		expect(data.systemRays).toEqual([{ x, from: limit.openHead, bound: 'lower' }]);
		expect(data.system).toHaveLength(curve.points.length + 1);
		const i = data.system!.findIndex((p) => p.x === x);
		expect(data.system![i]).toEqual({ x, y: limit.openHead, bound: 'lower' });
		expect(data.system!.map((p) => p.x)).toEqual(
			[...curve.points, limit].map((p) => fromSI(p.flow, 'L/s')).sort((a, b) => a - b)
		);
		// The line reaches it from the last grid flow with a head, and P1 runs on its vertical part.
		expect(data.system![i - 1]!.y).not.toBeNull();
		expect(f4(data.system![i - 1]!.x)).toBe('914.2');
		expect(f4(x)).toBe('946.4');
		expect(data.operating!.x).toBeCloseTo(x, 9);
		expect(data.operating!.y).toBeGreaterThan(limit.openHead!);
		// The data table lists it in flow order, marked, with the range that holds.
		expect(data.systemRows[i]).toMatchObject({
			flow: '946.4',
			head: `≥ ${f4(limit.openHead!)}`,
			atLimit: true
		});
		expect(data.systemRows[i]!.head).toBe('≥ 21.9');
		expect(data.systemRows.filter((r) => r.atLimit)).toEqual([data.systemRows[i]]);
		expect(data.systemRows[i]!.note).toBe(
			systemPointNote(limit, { project, units: project.settings.units }).text
		);
		// The notes: one more point without a head, its vertical part, and how it was solved.
		const missing = curve.points.filter((p) => p.head === null).length + 1;
		const notes = chartNotes({ data, result, system: { status: 'ready', curve } });
		expect(notes.curve!.text).toMatch(
			new RegExp(
				`^${missing} of ${curve.points.length + 1} system-curve points have no head: at 946\\.4 L/s it is undetermined, any head at or above 21\\.9 m holding, drawn as the curve's vertical part from there to the top of the head axis; at the ${curve.points.filter((p) => p.reason === 'beyond_limit').length} flows sampled beyond 946\\.4 L/s no steady state carries the flow; the data table says why`
			)
		);
		expect(notes.method).toBe(
			"System curve: the network of this solve, solved again with the pump replaced by each of 41 evenly spaced flows from 0 to 1590 L/s, then by 946.4 L/s, the flow limit, above which no steady state carries the flow, solved alone from the network's initial state (other pumps running, valves following their rules); the system head at each flow is the EGL at the discharge minus the EGL at the suction."
		);
		// The readout at that flow: the range, never a bare head.
		expect(chartReadout(data, ['head'], x).find((r) => r.key === 'system')).toMatchObject({
			value: limit.openHead,
			bound: 'lower'
		});
		// The group chart of the same case draws its vertical at the same flow.
		const group = condenserCase('winter');
		const groupData = groupChartData(
			condenserMembers('winter'),
			project.settings.units,
			group.groupCurve!,
			group.systemCurve!
		);
		expect(groupData.systemRays).toHaveLength(1);
		expect(f4(groupData.systemRays[0]!.x)).toBe('946.4');
		expect(f4(groupData.systemRays[0]!.from)).toBe('20.31');
	});

	it('takes the limit points into another case’s dotted curve and its table (C3)', () => {
		const { curve, result, project, prefs, data } = pumpCard('winter');
		const [other] = otherCasesData(
			[{ key: 'S1', name: 'Winter', result, stale: false, system: curve }],
			prefs,
			ratedCurveRange(project, 'P1'),
			1,
			{ project },
			{ S1: 1 }
		);
		expect(other!.systemRays).toEqual(data.systemRays);
		expect(other!.system).toEqual(data.system);
		expect(other!.systemRows).toEqual(data.systemRows);
		expect(other!.systemRows.filter((r) => r.atLimit).map((r) => r.flow)).toEqual(['946.4']);
	});

	it('draws a response without limitPoints (an API deployed before C3) as its grid alone', () => {
		// The Winter answer as an API before C3 gives it: the same grid, no limitPoints field.
		const { curve, result, project, prefs } = pumpCard('winter');
		const old = structuredClone(curve) as Partial<typeof curve>;
		delete old.limitPoints;
		const data = pumpChartData(result, prefs, ratedCurveRange(project, 'P1'), old as typeof curve, {
			project
		});
		expect(data.systemRays).toEqual([]);
		expect(data.system).toHaveLength(curve.points.length);
		const drawn = data.system!.filter((p) => p.y !== null);
		expect(f4(drawn.at(-1)!.x)).toBe('914.2');
		expect(data.systemRows.some((r) => r.atLimit)).toBe(false);
		const notes = chartNotes({
			data,
			result,
			system: { status: 'ready', curve: old as typeof curve }
		});
		expect(notes.method).toContain(
			'each of 41 evenly spaced flows from 0 to 1590 L/s (other pumps'
		);
		// The single-line case's limit is a grid flow: no limit point, its grid point the foot.
		expect(pumpCard('single24').curve.limitPoints).toEqual([]);
	});

	// The review of open defects round two, AC-1: a limit point is the bound one cut gives, not
	// always reached (FCVs in series on parallel paths with crossed setpoints: the limit 11 L/s, the
	// most any steady state carries 2 L/s), so the method sentence says what holds on its far side
	// whether or not it is reached: no steady state carries the flow above the flow limit, nor below
	// the floor. Made-up shapes: a floor at 5 L/s (the below_floor points' limitFlow) and a flow
	// limit at 25 L/s (the beyond_limit points'), its point without a head (not converged), as the
	// fixed API answers where the cut is not the least.
	it('names each limit point by what holds past it, the flow floor and the flow limit, whether or not it is reached (AC-1)', () => {
		const curve = systemCurveResponse();
		curve.points[0] = systemCurvePoint({
			flow: 0,
			reason: 'below_floor',
			limitFlow: 0.005,
			message: 'made-up'
		});
		curve.points[3] = systemCurvePoint({
			flow: 0.03,
			reason: 'beyond_limit',
			limitFlow: 0.025,
			message: 'made-up'
		});
		curve.converged = curve.points.map((p) => p.converged);
		curve.limitPoints = [
			systemCurvePoint({ flow: 0.005, head: 13, converged: true }),
			systemCurvePoint({
				flow: 0.025,
				reason: 'not_converged',
				componentIds: ['A1', 'B1'],
				message: 'made-up'
			})
		];
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], curve);
		expect(data.systemLimits.map((l) => l.kind)).toEqual(['least', 'most']);
		const method = chartNotes({
			data,
			result: pumpResult(),
			system: { status: 'ready', curve }
		}).method;
		expect(method).toBe(
			"System curve: the network of this solve, solved again with the pump replaced by each of 4 evenly spaced flows from 0 to 30 L/s, then by 5 L/s, the flow floor, below which no steady state carries the flow, and by 25 L/s, the flow limit, above which no steady state carries the flow, each solved alone from the network's initial state (other pumps running, valves following their rules); the system head at each flow is the EGL at the discharge minus the EGL at the suction."
		);
		// Never the most or the least flow, which a bound from one cut need not be.
		expect(method).not.toMatch(/the most|the least|can pass|must pass/);
		// Neither side's points saying which: a flow limit.
		curve.points[0] = systemCurvePoint({ flow: 0, head: 12, converged: true });
		curve.points[3] = systemCurvePoint({ flow: 0.03, head: 34.5, converged: true });
		const plain = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], curve);
		expect(chartNotes({ data: plain, result: pumpResult(), system: undefined }).method).toContain(
			'then by 5 L/s, a flow limit, and by 25 L/s, a flow limit, each solved alone'
		);
	});
});

// docs/proposals/open-defects-2.md §2 X: the flow axis starts at zero; what lies further below
// than the floor (10⁻⁶ m³/s) is not drawn and is named with its values. Synthetic: no answer of
// the API gives a pump chart such a flow (a system curve's flows start at 0, a pump's are not
// negative); the shapes are the API's, the flows moved below zero.
describe('the pump chart below zero flow (open-defects-2.md X)', () => {
	it('names a line’s points and a mark below the floor, in the notes and the image', () => {
		const curve = systemCurveResponse();
		const first = [...curve.points].sort((a, b) => a.flow - b.flow)[0]!;
		first.flow = -0.001;
		const result = pumpResult({ operatingFlow: -0.002 });
		const data = pumpChartData(result, SI_UNITS, [0, 0.03], curve);
		expect(data.flowFloor).toBeCloseTo(0.001, 12);
		const notes = chartNotes({ data, result, system: { status: 'ready', curve } });
		// The pump curve's dashed extrapolation runs to the operating point, below zero too.
		expect(notes.belowZero).toBe(
			`Below zero flow, not drawn: the pump curve's point at -2 L/s and 22 m; the system curve's point at -1 L/s and ${formatNumber(first.head!, 4)} m; the operating point at -2 L/s and 22 m; the data tables list them.`
		);
		const cfg = pumpChartConfig(data, [], {
			speedText: '100 % speed',
			legendLabels: () => [],
			format: (v) => formatNumber(v, 4)
		});
		expect(cfg.data.datasets.map((d) => d.label)).not.toContain('Operating point');
		expect(cfg.data.datasets.map((d) => d.label)).toContain('System curve');
		expect(imageNoteLines(notes, [])).toContain(notes.belowZero);
		// Within the floor: drawn at the edge, nothing named.
		first.flow = -1e-7;
		const near = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], curve);
		expect(near.belowZero).toEqual([]);
		expect(
			chartNotes({ data: near, result: pumpResult(), system: undefined }).belowZero
		).toBeNull();
	});
});
