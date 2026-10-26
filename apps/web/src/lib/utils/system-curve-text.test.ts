/**
 * Why a system-curve point has no head, told with names and display units. The points are
 * made-up test inputs shaped like the API's (POST /api/v1/system-curve): each message is the
 * API's wording for its case (solver/system_curve.py, as its tests write them out), with the
 * reason data that message quotes. Expected conversions are computed here from the unit
 * definitions.
 */
import { describe, expect, it } from 'vitest';
import type { Component, Port } from '../api/types';
import { projectWith } from '../testing/helpers';
import { systemCurvePoint } from '../testing/results';
import { systemPointNote, type SystemCurveTextContext } from './system-curve-text';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

const IN = 0.0254;
const FT = 0.3048;
const GPM = (231 * IN ** 3) / 60; // m³/s
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

const port = (id: string): Port => ({ id, nominalSize: 0.1, direction: 'bidirectional' });
const valve = (id: string, name: string, valveType: string): Component =>
	({
		type: 'valve',
		valveType,
		id,
		name,
		elevation: 0,
		status: 'active',
		...(['fcv', 'prv', 'psv'].includes(valveType) ? { setpoint: 0.02 } : {}),
		ports: [port('inlet'), port('outlet')]
	}) as Component;

/** Made-up names, so that every id told is visibly replaced by its name. */
const project = projectWith([
	{
		type: 'pump',
		id: 'PU',
		name: 'Booster pump',
		elevation: 0,
		curveId: 'C1',
		speed: 1,
		status: 'on',
		ports: [port('suction'), port('discharge')]
	},
	{
		type: 'pump',
		id: 'P2',
		name: 'Loop pump',
		elevation: 0,
		curveId: 'C1',
		speed: 1,
		status: 'on',
		ports: [port('suction'), port('discharge')]
	},
	valve('V', 'Flow limiter', 'fcv'),
	valve('V1', 'Second limiter', 'fcv'),
	valve('CV', 'Non-return valve', 'check'),
	valve('SC', 'Stop check', 'stop_check'),
	valve('PR', 'Pressure reducer', 'prv'),
	valve('PS', 'Back-pressure valve', 'psv'),
	valve('G', 'Isolation gate', 'gate'),
	{
		type: 'assigned_flow',
		id: 'D1',
		name: 'Process user',
		elevation: 0,
		flow: 0.004,
		ports: [port('port_1')]
	},
	{
		type: 'assigned_flow',
		id: 'D2',
		name: 'Wash bay',
		elevation: 0,
		flow: 0.002,
		ports: [port('port_1')]
	}
]);
const SI: SystemCurveTextContext = { project, units: SI_UNITS };
const US: SystemCurveTextContext = { project, units: IMPERIAL_UNITS };

const FCV_RULE = 'an FCV passes neither reverse flow nor more than its flow setpoint';
const CHECK_RULE = 'a check valve passes no reverse flow';
const PRV_RULE =
	'a PRV passes no reverse flow, and no flow while the pressure its outlet side needs is above its setting';
const NO_WAY =
	"the flow has no way through: a side of the pump reaches no reservoir or reference node, nor the pump's other side, through elements that can open (every element but those closed by a status the user set)";

describe('a point with a head, or without a reason', () => {
	it('a point with a head has no note', () => {
		expect(
			systemPointNote(systemCurvePoint({ flow: 0.01, head: 12, converged: true }), SI)
		).toEqual({ text: '' });
	});

	it("keeps the API's sentence when the reason is null or not known here", () => {
		const message = 'made-up reason with V and 0.01 m³/s';
		for (const reason of [null, 'some_new_reason']) {
			const point = systemCurvePoint({
				flow: 0.01,
				message,
				reason: reason as never,
				componentIds: ['V']
			});
			expect(systemPointNote(point, SI)).toEqual({ text: message });
		}
	});
});

describe('no way through', () => {
	it('at zero flow: the head is undetermined; at any other flow: no steady state', () => {
		const zero = systemCurvePoint({
			flow: 0,
			reason: 'no_way_through',
			message: `${NO_WAY}; at zero flow the head across the pump is undetermined`
		});
		expect(systemPointNote(zero, SI)).toEqual({
			text: "At zero flow the head across the pump is undetermined: a side of the pump reaches no reservoir or reference node, nor the pump's other side, through elements that can open (every element but those closed by a status you set).",
			detail: zero.message
		});
		const flowing = systemCurvePoint({
			flow: 0.01,
			reason: 'no_way_through',
			message: `${NO_WAY}, so no steady state carries it`
		});
		expect(systemPointNote(flowing, SI).text).toMatch(
			/^No steady state carries this flow: a side of the pump reaches no reservoir/
		);
	});
});

describe('beyond the limit', () => {
	it('a check valve facing the pump passes no flow that way', () => {
		const point = systemCurvePoint({
			flow: 0.01,
			reason: 'beyond_limit',
			componentIds: ['CV'],
			limitFlow: 0,
			passedFlow: 0,
			message:
				"no steady state carries this flow: every way from the pump's discharge back to its suction, through the network or a reservoir or reference node, passes check valve 'CV', " +
				`which passes no flow that way (${CHECK_RULE})`
		});
		expect(systemPointNote(point, SI)).toEqual({
			text:
				"No steady state carries this flow: every way from the pump's discharge back to its suction, through the network or a reservoir or reference node, passes Non-return valve, " +
				`which passes no flow that way (${CHECK_RULE}).`,
			detail: point.message
		});
	});

	it('a series FCV: at most its setpoint, in the display unit', () => {
		const point = systemCurvePoint({
			flow: 0.03,
			reason: 'beyond_limit',
			componentIds: ['V'],
			limitFlow: 0.02,
			passedFlow: 0.02,
			message: `made-up: passes FCV 'V', which passes at most 0.02 m³/s that way (${FCV_RULE})`
		});
		expect(systemPointNote(point, SI).text).toContain(
			`passes Flow limiter, which passes at most 20 L/s that way (${FCV_RULE}).`
		);
		expect(systemPointNote(point, US).text).toContain(
			`which passes at most ${sig4(0.02 / GPM)} gpm that way`
		);
	});

	it('several elements, in the rules order of the API (FCV, PRV, PSV, check valve, pump)', () => {
		const point = systemCurvePoint({
			flow: 0.03,
			reason: 'beyond_limit',
			componentIds: ['SC', 'V', 'P2'],
			limitFlow: 0.02,
			passedFlow: 0.02,
			message: 'made-up'
		});
		expect(systemPointNote(point, SI).text).toContain(
			'passes Stop check, Flow limiter and Loop pump, which together pass at most 20 L/s that way ' +
				`(${FCV_RULE}; ${CHECK_RULE}; a pump passes no reverse flow, nor any flow against more than its shutoff head).`
		);
	});

	it('counting an assigned flow: what the cut passes and what the pump can pass', () => {
		const point = systemCurvePoint({
			flow: 0.016,
			reason: 'beyond_limit',
			componentIds: ['V1'],
			assignedFlowNodeIds: ['D1'],
			limitFlow: 0.014,
			passedFlow: 0.01,
			message: 'made-up'
		});
		expect(systemPointNote(point, SI).text).toBe(
			"No steady state carries this flow: every way from the pump's discharge back to its suction, through the network or a reservoir or reference node, passes Second limiter, " +
				`which passes at most 10 L/s that way (${FCV_RULE}), and with the flows of the assigned-flow node Process user, which takes or supplies its flow whatever the pressure, ` +
				'the pump can pass at most 14 L/s.'
		);
		// Both flows in the display unit.
		const us = systemPointNote(point, US).text;
		expect(us).toContain(`which passes at most ${sig4(0.01 / GPM)} gpm that way`);
		expect(us).toContain(`the pump can pass at most ${sig4(0.014 / GPM)} gpm.`);
		expect(us).not.toMatch(/L\/s|m³\/s/);
	});

	it('a negative limit: the reverse flow the pump would have to pass', () => {
		const point = systemCurvePoint({
			flow: 0,
			reason: 'beyond_limit',
			componentIds: ['V1'],
			assignedFlowNodeIds: ['D1', 'D2'],
			limitFlow: -0.005,
			passedFlow: 0.01,
			message: 'made-up'
		});
		expect(systemPointNote(point, US).text).toContain(
			'and with the flows of the assigned-flow nodes Process user and Wash bay, which take or supply ' +
				`their flows whatever the pressure, the pump would have to pass ${sig4(0.005 / GPM)} gpm in reverse: ` +
				'no forced flow from its suction to its discharge, zero included, has a steady state.'
		);
	});
});

describe('below the floor', () => {
	it('what only the pump can feed: the least it must pass', () => {
		const point = systemCurvePoint({
			flow: 0.006,
			reason: 'below_floor',
			componentIds: ['CV'],
			assignedFlowNodeIds: ['D1'],
			limitFlow: 0.0125,
			passedFlow: 0,
			message: 'made-up'
		});
		expect(systemPointNote(point, SI).text).toBe(
			"No steady state carries this flow: every way from the pump's suction to its discharge, through the network or a reservoir or reference node, passes Non-return valve, " +
				`which passes no flow that way (${CHECK_RULE}), and with the flows of the assigned-flow node Process user, which takes or supplies its flow whatever the pressure, ` +
				'the pump must pass at least 12.5 L/s.'
		);
		// The least flow in the display unit.
		const us = systemPointNote(point, US).text;
		expect(us).toContain(`the pump must pass at least ${sig4(0.0125 / GPM)} gpm.`);
		expect(us).not.toMatch(/L\/s|m³\/s/);
	});
});

describe('no steady state found', () => {
	it('names the elements the rules close and the starts tried, in order', () => {
		const point = systemCurvePoint({
			flow: 0.02,
			reason: 'no_steady_state_found',
			componentIds: ['PR'],
			startsTried: ['previous_point', 'initial', 'initial_open'],
			message: 'made-up'
		});
		expect(systemPointNote(point, SI).text).toBe(
			'No steady state found that carries this flow: the status rules close Pressure reducer, which leaves a side of the pump with no way to a reservoir or reference node ' +
				`(${PRV_RULE}); none is found from the last converged point's solution, the network's initial state or that state with its control valves open.`
		);
	});

	it('with no element named, and from one start', () => {
		const point = systemCurvePoint({
			flow: 0.02,
			reason: 'no_steady_state_found',
			startsTried: ['initial'],
			message: 'made-up'
		});
		expect(systemPointNote(point, SI).text).toBe(
			"No steady state found that carries this flow: the status rules leave a side of the pump with no way to a reservoir or reference node; none is found from the network's initial state."
		);
	});
});

describe('an undetermined head', () => {
	it('closed off (at zero flow) and on a free level', () => {
		const closed = systemCurvePoint({
			flow: 0,
			reason: 'closed_off',
			componentIds: ['PR'],
			message: 'made-up'
		});
		expect(systemPointNote(closed, SI).text).toBe(
			'The head across the pump is undetermined at zero flow: Pressure reducer closes off a side of the pump, and no reservoir or reference node fixes the pressure in the part closed off.'
		);
		const two = systemCurvePoint({
			flow: 0.01,
			reason: 'closed_off',
			componentIds: ['PR', 'CV'],
			message: 'made-up'
		});
		expect(systemPointNote(two, SI).text).toBe(
			'The head across the pump is undetermined: Pressure reducer and Non-return valve close off a side of the pump, and no reservoir or reference node fixes the pressure in the part closed off.'
		);
		const none = systemCurvePoint({ flow: 0.01, reason: 'closed_off', message: 'made-up' });
		expect(systemPointNote(none, SI).text).toContain(
			'undetermined: a side of the pump is closed off, and'
		);
		const free = systemCurvePoint({
			flow: 0,
			reason: 'free_level',
			componentIds: ['PR'],
			message: 'made-up'
		});
		expect(systemPointNote(free, SI).text).toBe(
			'The head across the pump is undetermined: a side of the pump, closed off by Pressure reducer, is in a part of the network that carries flow but reaches no reservoir or reference node, so nothing fixes its pressure level.'
		);
		const freeNone = systemCurvePoint({ flow: 0, reason: 'free_level', message: 'made-up' });
		expect(systemPointNote(freeNone, SI).text).toContain(
			'undetermined: a side of the pump is in a part'
		);
	});

	it('a control valve at its switch: the open head and its side, in the display unit', () => {
		const head = 12.3456;
		const message =
			"the head across the pump is undetermined: at this flow FCV 'V' passes exactly its setpoint flow, so the valve could also hold it throttled, with any head across the pump at or above 12.3456 m (with the valve fully open), and no reservoir or reference node fixes the pressure between the valve and the pump";
		const point = systemCurvePoint({
			flow: 0.02,
			reason: 'valve_at_switch',
			componentIds: ['V'],
			openHead: head,
			openHeadBound: 'lower',
			message
		});
		expect(systemPointNote(point, SI)).toEqual({
			text:
				'The head across the pump is undetermined: at this flow Flow limiter passes exactly its flow setpoint, so it could also hold the flow throttled, ' +
				'with any head across the pump at or above 12.35 m (its head with the valve fully open), and no reservoir or reference node fixes the pressure between the valve and the pump.',
			detail: message
		});
		expect(systemPointNote(point, US).text).toContain(`at or above ${sig4(head / FT)} ft`);
		const below = { ...point, openHeadBound: 'upper' as const, componentIds: ['PR'] };
		expect(systemPointNote(below, SI).text).toContain(
			'at this flow Pressure reducer has the pressure at its outlet at its setting, so it could also hold the flow throttled, with any head across the pump at or below 12.35 m'
		);
		const psv = { ...point, componentIds: ['PS'] };
		expect(systemPointNote(psv, SI).text).toContain(
			'Back-pressure valve has the pressure at its inlet at its setting'
		);
	});
});

describe('not converged, not computed', () => {
	it("tells the outer loop's words with names and display units", () => {
		const point = systemCurvePoint({
			flow: 0.01,
			reason: 'not_converged',
			componentIds: ['V1'],
			message:
				"not converged: in these statuses only FCV 'V1' can connect assigned-flow node(s) 'D1' to a reservoir or reference node, and they take 0.01 m³/s through it, more than its setpoint (0.005 m³/s)"
		});
		expect(systemPointNote(point, SI)).toEqual({
			text: 'Its solve did not converge. In these statuses only FCV “Second limiter” can connect assigned-flow node(s) “Process user” to a reservoir or reference node, and they take 10 L/s through it, more than its setpoint (5 L/s).',
			detail: point.message
		});
		expect(systemPointNote(point, US).text).toContain(
			`they take ${sig4(0.01 / GPM)} gpm through it, more than its setpoint (${sig4(0.005 / GPM)} gpm).`
		);
	});

	it('not computed: the time ran out', () => {
		const point = systemCurvePoint({
			flow: 0.01,
			reason: 'not_computed',
			message: "not computed: the request's time budget of 45 s ran out"
		});
		expect(systemPointNote(point, SI)).toEqual({
			text: 'Not computed: the time allowed for the calculation ran out before this point was solved.',
			detail: point.message
		});
	});
});

describe("the API's sentence is kept when the data is not as its code needs", () => {
	const kept = [
		// No element across the cut, or one this project does not have (no kind, so no rule).
		{ reason: 'beyond_limit', limitFlow: 0.02, passedFlow: 0.02 },
		{ reason: 'beyond_limit', componentIds: ['X9'], limitFlow: 0.02, passedFlow: 0.02 },
		// An element whose kind has no closing rule (an isolation valve), or a missing number.
		{ reason: 'beyond_limit', componentIds: ['G'], limitFlow: 0.02, passedFlow: 0.02 },
		{ reason: 'beyond_limit', componentIds: ['V'], limitFlow: null, passedFlow: 0.02 },
		// A floor without assigned flows (the API's floors always count some).
		{ reason: 'below_floor', componentIds: ['CV'], limitFlow: 0.01, passedFlow: 0 },
		{ reason: 'no_steady_state_found', componentIds: ['PR'], startsTried: [] },
		{ reason: 'no_steady_state_found', componentIds: ['PR'], startsTried: ['somewhere'] },
		{ reason: 'no_steady_state_found', componentIds: ['G'], startsTried: ['initial'] },
		{ reason: 'valve_at_switch', componentIds: ['G'], openHead: 1, openHeadBound: 'lower' },
		{ reason: 'valve_at_switch', componentIds: ['V'], openHead: null, openHeadBound: 'lower' },
		{ reason: 'valve_at_switch', componentIds: ['V'], openHead: 1, openHeadBound: null },
		{ reason: 'valve_at_switch', componentIds: ['V', 'V1'], openHead: 1, openHeadBound: 'upper' },
		// A not-converged message not in the API's form.
		{ reason: 'not_converged', componentIds: ['V1'] }
	] as const;
	for (const fields of kept) {
		it(JSON.stringify(fields), () => {
			const point = systemCurvePoint({
				flow: 0.01,
				message: 'made-up: the reason in words',
				...(fields as object)
			});
			expect(systemPointNote(point, SI)).toEqual({ text: 'made-up: the reason in words' });
		});
	}
});

describe('kinds from the project as solved', () => {
	it("each element's rule is chosen by its kind in the project solved, names from the labels", () => {
		// Solved as a check valve; renamed since (names are the labels' project).
		const solved = projectWith([valve('CV', 'Old name', 'check')]);
		const renamed = projectWith([valve('CV', 'New name', 'fcv')]);
		const point = systemCurvePoint({
			flow: 0.01,
			reason: 'beyond_limit',
			componentIds: ['CV'],
			limitFlow: 0,
			passedFlow: 0,
			message: 'made-up'
		});
		const text = systemPointNote(point, { project: renamed, solved, units: SI_UNITS }).text;
		expect(text).toContain(`passes New name, which passes no flow that way (${CHECK_RULE}).`);
		expect(text).not.toContain('Old name');
	});
});
