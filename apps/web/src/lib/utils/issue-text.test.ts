/**
 * Topology issues as people read them. Issues are made-up test inputs shaped like the API's
 * (codes, component ids and message wording of apps/api solver/builder.py); expected
 * conversions are computed here from the unit definitions.
 */
import { describe, expect, it } from 'vitest';
import type { Pump, TopologyIssue } from '../api/types';
import { assignedFlowProject } from '../testing/helpers';
import { pumpTransferExample } from './examples';
import { issueTextOptions, topologyIssueViews, type IssueTextOptions } from './issue-text';
import { IMPERIAL_UNITS } from './units';

const IN = 0.0254;
const GPM = (231 * IN ** 3) / 60; // m³/s, US gallon = 231 in³
const sig4 = (v: number) => String(Number(v.toPrecision(4)));
/** Rounded toward zero to 4 significant digits: how a bound a value must stay below is shown. */
const down4 = (v: number) => {
	const scale = 10 ** (3 - Math.floor(Math.log10(Math.abs(v))));
	return String(Math.trunc(v * scale) / scale);
};

function controlledProject() {
	const project = pumpTransferExample();
	(project.components[1] as Pump).control = { mode: 'flow', setpoint: 0.01, minSpeed: 0.4 };
	return project;
}

/** The API's CONTROLLED_PUMP_CURVE issue for pump P1 and curve C1 (made-up interval). */
function curveIssue(message?: string): TopologyIssue {
	return {
		code: 'CONTROLLED_PUMP_CURVE',
		message:
			message ??
			"pump 'P1' is speed-controlled, but its curve 'C1' (Made-up curve) does not give one " +
				'speed for each head: the head at a fixed flow, s² H₀(Q/s), does not rise with speed s ' +
				"where 2 H₀(x) − x H₀'(x) ≤ 0, which holds for rated-speed flows x from 0.0125 to " +
				'0.0315 m³/s; use a curve whose head rises less steeply with flow there ' +
				"(2 H₀(x) > x H₀'(x)), or a fixed speed",
		componentIds: ['P1'],
		connectionIds: []
	};
}

describe('CONTROLLED_PUMP_CURVE', () => {
	it('names the pump and its curve, with the flows in the display unit', () => {
		const project = controlledProject();
		const curve = project.pumpLibrary[0]!.name;
		const [view] = topologyIssueViews([curveIssue()], project, true, IMPERIAL_UNITS);
		expect(view!.text).toBe(
			`Transfer pump is speed-controlled, but its pump curve “${curve}” does not give one speed ` +
				'for each head: at a fixed flow the head s²·H₀(Q/s) must rise with the speed s, and it ' +
				'does not where 2·H₀(x) − x·H₀′(x) ≤ 0, for rated-speed flows x from ' +
				`${sig4(0.0125 / GPM)} to ${sig4(0.0315 / GPM)} gpm. Use a curve whose head rises less ` +
				'steeply with flow there (2·H₀(x) > x·H₀′(x)), or a fixed speed.'
		);
		expect(view!.text).not.toMatch(/'P1'|'C1'|m³\/s/);
		expect(view!.links).toEqual([{ componentId: 'P1' }]);
		// SI by default.
		expect(topologyIssueViews([curveIssue()], project, true)[0]!.text).toContain(
			'from 12.5 to 31.5 L/s'
		);
	});

	it('advises a head that rises less steeply: ψ ≤ 0 needs x·H₀′ ≥ 2·H₀ ≥ 0, a rising head', () => {
		// Pump heads are not negative (the schema's bound), so where the head falls (H₀′ < 0),
		// 2·H₀ − x·H₀′ > 0: the curve fails only where its head rises steeply with flow.
		const [view] = topologyIssueViews([curveIssue()], controlledProject(), true);
		expect(view!.text).toMatch(/Use a curve whose head rises less steeply with flow there/);
		expect(view!.text).not.toMatch(/falls/);
	});

	it("keeps the server's message when the error is not for the project as it is now", () => {
		// The solve was sent with curve C1; the pump was given curve C2 while it was solving.
		const project = controlledProject();
		project.pumpLibrary = [
			...project.pumpLibrary,
			{ ...project.pumpLibrary[0]!, id: 'C2', name: 'Other curve' }
		];
		(project.components[1] as Pump).curveId = 'C2';
		const stale = topologyIssueViews([curveIssue()], project, false)[0]!;
		expect(stale).toEqual({ text: curveIssue().message, links: [{ componentId: 'P1' }] });
		expect(stale.text).not.toContain('Other curve');
		// A message about another curve than the pump's is never told as about the pump's curve.
		expect(topologyIssueViews([curveIssue()], project, true)[0]!.text).toBe(curveIssue().message);
	});

	it("keeps the server's message when it does not state the interval as expected", () => {
		const project = controlledProject();
		const other = curveIssue("pump 'P1' is speed-controlled, but its curve 'C1' is not accepted");
		expect(topologyIssueViews([other], project, true)[0]).toEqual({
			text: other.message,
			links: [{ componentId: 'P1' }]
		});
		// A pump that no longer exists, or a curve the project does not have.
		const gone = { ...curveIssue(), componentIds: ['P9'] };
		expect(topologyIssueViews([gone], project, true)[0]!.text).toBe(gone.message);
		const noCurve = { ...project, pumpLibrary: [] };
		expect(topologyIssueViews([curveIssue()], noCurve, true)[0]!.text).toBe(curveIssue().message);
	});
});

/**
 * The API's CONTROLLED_PUMP_SETPOINT issue for pump P1 on curve C1, in the wording of
 * solver/builder.py (made-up values, as Python's :.6g prints them).
 */
function setpointMessage(
	values: { setpoint?: string; speed?: string; curve?: string; xMono?: string; bound?: string } = {}
): string {
	const {
		setpoint = '0.045',
		speed = '0.9',
		curve = "'C1' (Made-up curve)",
		xMono = '0.0402',
		bound = '0.03618'
	} = values;
	return (
		`pump 'P1' is speed-controlled to hold ${setpoint} m³/s, but no speed up to its maximum ` +
		`speed ${speed} can hold it on its curve ${curve}: at that flow the head s² H₀(Q/s) falls ` +
		'as the speed s rises, at every speed, because Q/s lies beyond x_mono = ' +
		`${xMono} m³/s, twice the flow at which the curve's end tangent reaches zero head; ` +
		`setpoints must be below ${bound} m³/s (the maximum speed × x_mono), so use a smaller ` +
		'setpoint or a curve that extends to higher flows'
	);
}

function setpointIssue(message = setpointMessage()): TopologyIssue {
	return { code: 'CONTROLLED_PUMP_SETPOINT', message, componentIds: ['P1'], connectionIds: [] };
}

/** The pump-transfer example with P1 under flow control at 90 % maximum speed (made-up). */
function setpointProject() {
	const project = pumpTransferExample();
	const pump = project.components[1] as Pump;
	pump.speed = 0.9;
	pump.control = { mode: 'flow', setpoint: 0.045, minSpeed: 0.4 };
	return project;
}

describe('CONTROLLED_PUMP_SETPOINT', () => {
	it('names the pump and its curve, with the setpoint and the bound in the display unit', () => {
		const project = setpointProject();
		const curve = project.pumpLibrary[0]!.name;
		const [view] = topologyIssueViews([setpointIssue()], project, true, IMPERIAL_UNITS);
		expect(view!.text).toBe(
			`Transfer pump is speed-controlled to hold ${sig4(0.045 / GPM)} gpm, but no speed up to ` +
				`its maximum speed (90 %) can hold that flow on its pump curve “${curve}”: at that ` +
				'flow the head s²·H₀(Q/s) falls as the speed s rises, at every speed, because Q/s lies ' +
				"beyond x_mono, twice the flow at which the curve's end tangent reaches zero head. Use " +
				`a setpoint below ${down4(0.03618 / GPM)} gpm (the maximum speed × x_mono), or a curve ` +
				'that extends to higher flows.'
		);
		// 0.03618 m³/s is 573.46 gpm: rounded to the nearest it would read 573.5 gpm, and a
		// setpoint of 573.48 gpm, below that, is above the bound and rejected again.
		expect(down4(0.03618 / GPM)).toBe('573.4');
		expect(573.48 * GPM).toBeGreaterThan(0.03618);
		expect(view!.text).not.toMatch(/'P1'|'C1'|m³\/s/);
		expect(view!.links).toEqual([{ componentId: 'P1' }]);
		// SI by default.
		const si = topologyIssueViews([setpointIssue()], project, true)[0]!.text;
		expect(si).toContain('to hold 45 L/s, but no speed up to its maximum speed (90 %)');
		expect(si).toContain('Use a setpoint below 36.18 L/s (the maximum speed × x_mono)');
	});

	it('reads a bound printed with an exponent', () => {
		const message = setpointMessage({ setpoint: '2e-05', xMono: '1.5e-05', bound: '1.35e-05' });
		const project = setpointProject();
		(project.components[1] as Pump).control!.setpoint = 2e-5;
		expect(topologyIssueViews([setpointIssue(message)], project, true)[0]!.text).toContain(
			'Use a setpoint below 0.0135 L/s'
		);
	});

	it("takes the bound from the message's end, whatever the curve's name says", () => {
		const message = setpointMessage({
			curve:
				"'C1' (setpoints must be below 9 m³/s (the maximum speed × x_mono), so use a smaller setpoint or a curve that extends to higher flows)"
		});
		const text = topologyIssueViews([setpointIssue(message)], setpointProject(), true)[0]!.text;
		expect(text).toContain('Use a setpoint below 36.18 L/s');
	});

	it("keeps the server's message when the error is not for the project as it is now", () => {
		// The solve was sent with curve C1; the pump was given curve C2 while it was solving.
		const project = setpointProject();
		project.pumpLibrary = [
			...project.pumpLibrary,
			{ ...project.pumpLibrary[0]!, id: 'C2', name: 'Other curve' }
		];
		(project.components[1] as Pump).curveId = 'C2';
		const stale = topologyIssueViews([setpointIssue()], project, false)[0]!;
		expect(stale).toEqual({ text: setpointMessage(), links: [{ componentId: 'P1' }] });
		// A message about another curve than the pump's is never told as about the pump's curve.
		expect(topologyIssueViews([setpointIssue()], project, true)[0]!.text).toBe(setpointMessage());
		// Nor is a current one told from the project once it is not (stale = false is the rule).
		expect(topologyIssueViews([setpointIssue()], setpointProject(), false)[0]!.text).toBe(
			setpointMessage()
		);
	});

	it("keeps the server's message when it does not state the curve and bound as expected", () => {
		const project = setpointProject();
		for (const message of [
			"pump 'P1' is speed-controlled to hold 0.045 m³/s, but no speed can hold it",
			setpointMessage().replace('setpoints must be below 0.03618', 'setpoints must be below about'),
			setpointMessage().replace(' (the maximum speed × x_mono)', ''),
			`${setpointMessage()}.`,
			setpointMessage({ curve: 'C1 (Made-up curve)' })
		]) {
			expect(topologyIssueViews([setpointIssue(message)], project, true)[0]).toEqual({
				text: message,
				links: [{ componentId: 'P1' }]
			});
		}
		// A pump that no longer exists, a curve the project does not have, or a pump without flow
		// control.
		const gone = { ...setpointIssue(), componentIds: ['P9'] };
		expect(topologyIssueViews([gone], project, true)[0]!.text).toBe(gone.message);
		const noCurve = { ...project, pumpLibrary: [] };
		expect(topologyIssueViews([setpointIssue()], noCurve, true)[0]!.text).toBe(setpointMessage());
		const fixed = setpointProject();
		delete (fixed.components[1] as Pump).control;
		expect(topologyIssueViews([setpointIssue()], fixed, true)[0]!.text).toBe(setpointMessage());
	});
});

describe('NO_FIXED_HEAD', () => {
	/** The API's issue for a part without a reservoir or reference node (solver/builder.py). */
	function noHeadIssue(componentIds: string[], assigned: boolean): TopologyIssue {
		return {
			code: 'NO_FIXED_HEAD',
			message:
				'this part of the network has no fixed-pressure boundary; add a reservoir or reference ' +
				`node (components: ${componentIds.join(', ')})` +
				(assigned ? '; assigned-flow nodes fix a flow, not a pressure, so they are not one' : ''),
			componentIds,
			connectionIds: ['L1']
		};
	}

	it('says that an assigned-flow node in the part is not a fixed-pressure boundary', () => {
		// Its reservoir replaced by a reference-less end: the part holds only AF1 and a plug.
		const project = assignedFlowProject(0.004);
		project.components[0] = {
			id: 'PL1',
			name: 'End cap',
			elevation: 0,
			type: 'plug',
			ports: [{ id: 'port_1', nominalSize: 0.1016, direction: 'bidirectional' }]
		};
		project.connections[0]!.fromComponentId = 'PL1';
		const issue = noHeadIssue(['AF1', 'PL1'], true);
		const [view] = topologyIssueViews([issue], project, true);
		expect(view).toEqual({
			text:
				'This part of the network has no fixed-pressure boundary: add a reservoir or reference ' +
				'node to it. Assigned-flow nodes fix a flow, not a pressure, so they do not count as one.',
			links: [{ componentId: 'AF1' }, { componentId: 'PL1' }],
			detail: issue.message
		});
	});

	it('says nothing of assigned-flow nodes in a part without one', () => {
		const project = pumpTransferExample();
		const [view] = topologyIssueViews([noHeadIssue(['P1', 'V1'], false)], project, true);
		expect(view!.text).toBe(
			'This part of the network has no fixed-pressure boundary: add a reservoir or reference node to it.'
		);
	});
});

/**
 * The other codes the API's builder raises (solver/builder.py, solver/library.py). Each message
 * is the API's wording for a change to the pump-transfer example (made-up values, printed as
 * Python's :g prints them); expected conversions are computed here from the unit definitions.
 */
describe('the other builder codes', () => {
	const MM = 1e-3;
	const FT = 0.3048;
	const sig = (v: number, digits = 4) => String(Number(v.toPrecision(digits)));
	const issue = (
		code: string,
		message: string,
		componentIds: string[] = [],
		connectionIds: string[] = []
	): TopologyIssue => ({ code, message, componentIds, connectionIds });
	const one = (
		i: TopologyIssue,
		project = pumpTransferExample(),
		current = true,
		...rest: [] | [typeof IMPERIAL_UNITS] | [typeof IMPERIAL_UNITS, IssueTextOptions]
	) => topologyIssueViews([i], project, current, ...(rest as [])).at(0)!;
	/** The link that opens piping L2 at its from end (Transfer pump's discharge). */
	const L2_LINK = {
		componentId: 'P1',
		portId: 'discharge',
		label: 'Transfer pump → Discharge isolation valve'
	};

	it('DUPLICATE_COMPONENT_ID names the components that share the id', () => {
		const project = pumpTransferExample();
		project.components.push({ ...project.components[2]!, name: 'Second valve' });
		const i = issue('DUPLICATE_COMPONENT_ID', "component id 'V1' is used more than once", ['V1']);
		expect(one(i, project)).toEqual({
			text:
				'More than one component has the id “V1” (Discharge isolation valve and Second valve): ' +
				'every component needs its own id.',
			links: [{ componentId: 'V1' }],
			detail: i.message
		});
		// Out of date: the names are not those the server found.
		expect(one(i, project, false).text).toBe(
			'More than one component has the id “V1”: every component needs its own id.'
		);
	});

	it('DUPLICATE_CONNECTION_ID names each piping with the id, and links to each', () => {
		const project = pumpTransferExample();
		project.connections[2]!.id = 'L2';
		const i = issue(
			'DUPLICATE_CONNECTION_ID',
			"connection id 'L2' is used more than once",
			[],
			['L2']
		);
		expect(one(i, project)).toEqual({
			text:
				'More than one pipe connection has the id “L2” (Transfer pump → Discharge isolation valve ' +
				'and Discharge isolation valve → Discharge tank): every pipe connection needs its own id.',
			links: [
				L2_LINK,
				{
					componentId: 'V1',
					portId: 'outlet',
					label: 'Discharge isolation valve → Discharge tank'
				}
			],
			detail: i.message
		});
	});

	it('DUPLICATE_ID names the component and the piping', () => {
		const project = pumpTransferExample();
		project.connections[2]!.id = 'V1';
		const i = issue(
			'DUPLICATE_ID',
			"id 'V1' names both a component and a connection; every element needs its own id",
			['V1'],
			['V1']
		);
		expect(one(i, project)).toEqual({
			text:
				'The id “V1” names both a component (Discharge isolation valve) and a pipe connection ' +
				'(Discharge isolation valve → Discharge tank): every element needs its own id.',
			links: [
				{ componentId: 'V1' },
				{
					componentId: 'V1',
					portId: 'outlet',
					label: 'Discharge isolation valve → Discharge tank'
				}
			],
			detail: i.message
		});
	});

	it('DUPLICATE_PUMP_CURVE_ID names the curves that share the id', () => {
		const project = pumpTransferExample();
		project.pumpLibrary.push({ ...project.pumpLibrary[0]!, name: 'Other curve' });
		const i = issue('DUPLICATE_PUMP_CURVE_ID', "pump curve id 'C1' is used more than once");
		expect(one(i, project)).toEqual({
			text:
				"More than one pump curve in the project's pump library has the id “C1” " +
				'(“Example transfer pump curve (illustrative)” and “Other curve”): every pump curve ' +
				'needs its own id.',
			links: [],
			detail: i.message
		});
	});

	it('UNKNOWN_COMPONENT says which end names it, and links to the piping at its other end', () => {
		const project = pumpTransferExample();
		project.connections[2]!.toComponentId = 'X9';
		const i = issue(
			'UNKNOWN_COMPONENT',
			"connection 'L3' (to end) refers to unknown component 'X9'",
			[],
			['L3']
		);
		expect(one(i, project)).toEqual({
			text:
				'Piping Discharge isolation valve → “X9” ends at component “X9”, which the project does ' +
				'not have.',
			links: [{ componentId: 'V1', portId: 'outlet', label: 'Discharge isolation valve → “X9”' }],
			detail: i.message
		});
		// The from end: "starts at"; its other end (R2) is linked.
		const from = pumpTransferExample();
		from.connections[2]!.fromComponentId = 'X8';
		const j = issue(
			'UNKNOWN_COMPONENT',
			"connection 'L3' (from end) refers to unknown component 'X8'",
			[],
			['L3']
		);
		expect(one(j, from)).toEqual({
			text: 'Piping “X8” → Discharge tank starts at component “X8”, which the project does not have.',
			links: [{ componentId: 'R2', portId: 'port_1', label: '“X8” → Discharge tank' }],
			detail: j.message
		});
	});

	it('UNKNOWN_PORT names the component and lists its ports', () => {
		const project = pumpTransferExample();
		project.connections[2]!.toPortId = 'port_7';
		const i = issue(
			'UNKNOWN_PORT',
			"connection 'L3' (to end) refers to port 'port_7', which component 'R2' does not have",
			['R2'],
			['L3']
		);
		expect(one(i, project)).toEqual({
			text:
				'Piping Discharge isolation valve → Discharge tank ends at a port “port_7” of Discharge ' +
				'tank, which has no such port (its ports: Port 1).',
			links: [{ componentId: 'R2' }],
			detail: i.message
		});
		expect(one(i, project, false).text).toBe(
			'Piping Discharge isolation valve → Discharge tank ends at a port “port_7” of Discharge ' +
				'tank, which has no such port.'
		);
	});

	it('SELF_CONNECTION names the port, and links to it', () => {
		const project = pumpTransferExample();
		project.connections[2]!.toComponentId = 'V1';
		project.connections[2]!.toPortId = 'outlet';
		const i = issue(
			'SELF_CONNECTION',
			"connection 'L3' connects port 'V1:outlet' to itself",
			['V1'],
			['L3']
		);
		expect(one(i, project)).toEqual({
			text:
				'Outlet of Discharge isolation valve is connected to itself (piping Discharge isolation ' +
				'valve → Discharge isolation valve): a pipe connection joins two different ports.',
			links: [{ componentId: 'V1', portId: 'outlet' }],
			detail: i.message
		});
	});

	it('PORT_CONNECTED_TWICE names the port and its pipings, and links to the port', () => {
		const project = pumpTransferExample();
		project.connections[2]!.fromPortId = 'inlet';
		const i = issue(
			'PORT_CONNECTED_TWICE',
			"port 'V1:inlet' has 2 connections; a port takes exactly one",
			['V1'],
			['L2', 'L3']
		);
		expect(one(i, project)).toEqual({
			text:
				'Inlet of Discharge isolation valve has 2 pipe connections (Transfer pump → Discharge ' +
				'isolation valve and Discharge isolation valve → Discharge tank): a port takes exactly ' +
				'one. To branch the flow, use a tee or wye.',
			links: [{ componentId: 'V1', portId: 'inlet' }],
			detail: i.message
		});
	});

	it('UNKNOWN_PIPE_MATERIAL, _SCHEDULE and _SIZE name the piping, its pipe and the material', () => {
		const material = issue(
			'UNKNOWN_PIPE_MATERIAL',
			"connection 'L2' pipe 1: unknown pipe material 'unobtainium'; available: carbon_steel, " +
				'stainless_steel, pvc, custom',
			[],
			['L2']
		);
		expect(one(material)).toEqual({
			text:
				'Piping Transfer pump → Discharge isolation valve, pipe 1: the pipe library has no ' +
				'material “unobtainium”: choose a material from the library, or enter a custom pipe.',
			links: [L2_LINK],
			detail: material.message
		});
		const schedule = issue(
			'UNKNOWN_PIPE_SCHEDULE',
			"connection 'L2' pipe 1: pipe material 'carbon_steel' has no schedule '999'; available: " +
				'10, 20, 30, 40, STD, 60, 80, XS, 100, 120, 140, 160, XXS',
			[],
			['L2']
		);
		const names: IssueTextOptions = {
			materialName: (id) => (id === 'carbon_steel' ? 'Carbon steel' : undefined),
			nominalSizes: [{ nominalSize: 2.5 * IN, nps: '2-1/2' }]
		};
		const project = pumpTransferExample();
		expect(one(schedule, project, true, IMPERIAL_UNITS, names).text).toBe(
			'Piping Transfer pump → Discharge isolation valve, pipe 1: the pipe library has no ' +
				'schedule “999” for Carbon steel: choose one of its schedules, or enter a custom pipe.'
		);
		// Without the library's names, the material's id.
		expect(one(schedule).text).toContain('has no schedule “999” for material “carbon_steel”:');
		const size = issue(
			'UNKNOWN_PIPE_SIZE',
			"connection 'L2' pipe 1: pipe material 'carbon_steel' schedule '40' has no nominal size " +
				'0.0635 m (NPS 2.5 in); available NPS: 0.125, 0.25, 3, 4',
			[],
			['L2']
		);
		expect(one(size, project, true, IMPERIAL_UNITS, names)).toEqual({
			text:
				'Piping Transfer pump → Discharge isolation valve, pipe 1: the pipe library has no NPS ' +
				'2-1/2 in schedule 40 of Carbon steel: choose one of its sizes, or enter a custom pipe.',
			links: [L2_LINK],
			detail: size.message
		});
		// A size the library does not designate: its NPS in inches (0.08382 m = 3.3 in).
		const odd = issue(
			'UNKNOWN_PIPE_SIZE',
			"connection 'L2' pipe 1: pipe material 'carbon_steel' schedule '40' has no nominal size " +
				'0.08382 m (NPS 3.3 in); available NPS: 3, 4',
			[],
			['L2']
		);
		expect(one(odd).text).toContain('the pipe library has no NPS 3.3 in schedule 40 of');
	});

	it('UNKNOWN_PIPE_SIZE never rounds the size onto one the library has', () => {
		// The server's messages (solver/library.py, sizes within 1e-6 m of a library size are
		// found), with carbon steel's real schedule 40 and STD lists, for hand-edited sizes.
		const SCH40 =
			'0.125, 0.25, 0.375, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 8, 10, 12, 14, 16, ' +
			'18, 20, 24, 32, 34, 36';
		const STD =
			'0.125, 0.25, 0.375, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 8, 10, 12, 14, 16, ' +
			'18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48';
		const size = (schedule: string, figures: string, available: string) =>
			issue(
				'UNKNOWN_PIPE_SIZE',
				`connection 'L2' pipe 1: pipe material 'carbon_steel' schedule '${schedule}' has no ` +
					`nominal size ${figures}; available NPS: ${available}`,
				[],
				['L2']
			);
		const names: IssueTextOptions = {
			materialName: (id) => (id === 'carbon_steel' ? 'Carbon steel' : undefined),
			nominalSizes: [2, 36, 40].map((nps) => ({ nominalSize: nps * IN, nps: String(nps) }))
		};
		const told = (i: TopologyIssue, options?: IssueTextOptions) =>
			options ? one(i, pumpTransferExample(), true, IMPERIAL_UNITS, options) : one(i);
		const sentence = (nps: string, schedule: string) =>
			'Piping Transfer pump → Discharge isolation valve, pipe 1: the pipe library has no ' +
			`NPS ${nps} in schedule ${schedule} of Carbon steel: choose one of its sizes, or enter a ` +
			'custom pipe.';

		// 0.050802 m = 2.0000787 in: "2" to 4 significant digits, schedule 40's NPS 2; 5 digits
		// tell it apart. With or without the library's sizes (the schedule's list has NPS 2).
		const two = size('40', '0.050802 m (NPS 2.00008 in)', SCH40);
		expect(told(two, names)).toEqual({
			text: sentence('2.0001', '40'),
			links: [L2_LINK],
			detail: two.message
		});
		expect(told(two).text).toContain('the pipe library has no NPS 2.0001 in schedule 40 of');
		// 0.914401 m = 36.0000394 in: "36" up to 6 digits, which the server's own NPS figure is.
		const big = size('40', '0.914401 m (NPS 36 in)', SCH40);
		expect(told(big, names).text).toBe(sentence('36.00004', '40'));
		// 1.016002 m: the message's metre figure, 1.016 m, is NPS 40 exactly, which STD has; its
		// NPS figure, 40.0001 (40.0000787 in), is not.
		const above = size('STD', '1.016 m (NPS 40.0001 in)', STD);
		expect(told(above, names).text).toBe(sentence('40.0001', 'STD'));
		// 1.0160011 m: both figures are NPS 40 (40.0000433 in to 6 digits): the browser cannot
		// tell the size from STD's NPS 40, so the server's message is kept.
		const same = size('STD', '1.016 m (NPS 40 in)', STD);
		expect(told(same, names)).toEqual({ text: same.message, links: [] });
	});

	it('ROUGHNESS_OUT_OF_RANGE gives the roughness and diameter in the display unit', () => {
		const i = issue(
			'ROUGHNESS_OUT_OF_RANGE',
			"connection 'L2' pipe 1: roughness 0.008 m is 4 times the inner diameter 0.002 m; the " +
				'Colebrook equation has no solution for relative roughness of 3.7 or more',
			[],
			['L2']
		);
		const told = (units?: typeof IMPERIAL_UNITS) =>
			units ? one(i, pumpTransferExample(), true, units) : one(i);
		expect(told()).toEqual({
			text:
				'Piping Transfer pump → Discharge isolation valve, pipe 1: its roughness (8 mm) is 4 ' +
				'times its inner diameter (2 mm), and the Colebrook equation has no solution for a ' +
				'relative roughness (roughness ÷ inner diameter) of 3.7 or more. Use a smaller ' +
				'roughness or a larger inner diameter.',
			links: [L2_LINK],
			detail: i.message
		});
		expect(told(IMPERIAL_UNITS).text).toContain(
			`its roughness (${sig(0.008 / IN)} in) is 4 times its inner diameter (${sig(0.002 / IN)} in)`
		);
		expect(told(IMPERIAL_UNITS).text).not.toMatch(/ m[;,)]/);
	});

	it('PIPE_SIZE_OUT_OF_RANGE gives the diameter and length in the display units', () => {
		const i = issue(
			'PIPE_SIZE_OUT_OF_RANGE',
			"connection 'L2' pipe 1: an inner diameter of 1e-100 m and a length of 3 m give a pipe " +
				'resistance that is not a finite floating-point number; the solver cannot represent this pipe',
			[],
			['L2']
		);
		expect(one(i)).toEqual({
			text:
				'Piping Transfer pump → Discharge isolation valve, pipe 1: an inner diameter of ' +
				`${1e-100 / MM} mm and a length of 3 m give a pipe resistance that is not a finite ` +
				'floating-point number, so the solver cannot represent this pipe. Check its inner ' +
				'diameter and length.',
			links: [L2_LINK],
			detail: i.message
		});
		expect(1e-100 / MM).toBe(1e-97);
		expect(one(i, pumpTransferExample(), true, IMPERIAL_UNITS).text).toContain(
			`an inner diameter of 3.937e-99 in and a length of ${sig(3 / FT)} ft`
		);
		expect(1e-100 / IN).toBeCloseTo(3.937e-99, 102);
	});

	it('VALVE_RESISTANCE_OUT_OF_RANGE names the valve, with its inlet diameter in the display unit', () => {
		const i = issue(
			'VALVE_RESISTANCE_OUT_OF_RANGE',
			"valve 'V1': a Cv of 1e-170 on the inlet pipe's inner diameter of 0.07792 m gives a loss " +
				'coefficient that is not a finite floating-point number; the solver cannot represent ' +
				'this valve',
			['V1']
		);
		expect(one(i)).toEqual({
			text:
				"Discharge isolation valve: a Cv of 1e-170 on its inlet pipe's inner diameter (77.92 mm) " +
				'gives a loss coefficient that is not a finite floating-point number, so the solver ' +
				'cannot represent this valve. Check its resistance.',
			links: [{ componentId: 'V1' }],
			detail: i.message
		});
		expect(one(i, pumpTransferExample(), true, IMPERIAL_UNITS).text).toContain(
			`inner diameter (${sig(0.07792 / IN)} in)`
		);
	});

	it("keeps the server's message, with no detail, when it is not in the form expected", () => {
		const project = pumpTransferExample();
		const kept = [
			// Not the builder's wording, or about another element than the issue's ids.
			issue('DUPLICATE_COMPONENT_ID', "component id 'V1' is used twice", ['V1']),
			issue('DUPLICATE_COMPONENT_ID', "component id 'V2' is used more than once", ['V1']),
			issue(
				'DUPLICATE_ID',
				"id 'V1' names both a component and a connection; every element needs its own id",
				['V1'],
				['L3']
			),
			issue(
				'UNKNOWN_COMPONENT',
				"connection 'L2' (to end) refers to unknown component 'X9'",
				[],
				['L3']
			),
			issue(
				'UNKNOWN_PORT',
				"connection 'L3' (to end) refers to port 'p', which component 'V1' does not have",
				['R2'],
				['L3']
			),
			issue(
				'SELF_CONNECTION',
				"connection 'L3' connects port 'R2:port_1' to itself",
				['V1'],
				['L3']
			),
			issue(
				'PORT_CONNECTED_TWICE',
				"port 'R2:port_1' has 2 connections; a port takes exactly one",
				['V1'],
				['L2', 'L3']
			),
			// The pragma-no-cover form of UNKNOWN_PIPE_SIZE, and a pipe message of another code.
			issue('UNKNOWN_PIPE_SIZE', "connection 'L2' pipe 1: a library pipe needs a size", [], ['L2']),
			issue(
				'ROUGHNESS_OUT_OF_RANGE',
				"connection 'L2' pipe 1: unknown pipe material 'x'; available: pvc",
				[],
				['L2']
			),
			// A number Python prints as inf, and a connection or component the project does not have.
			issue(
				'PIPE_SIZE_OUT_OF_RANGE',
				"connection 'L2' pipe 1: an inner diameter of inf m and a length of 3 m give a pipe resistance that is not a finite floating-point number; the solver cannot represent this pipe",
				[],
				['L2']
			),
			issue(
				'UNKNOWN_PIPE_MATERIAL',
				"connection 'L9' pipe 1: unknown pipe material 'x'; available: pvc",
				[],
				['L9']
			),
			issue(
				'VALVE_RESISTANCE_OUT_OF_RANGE',
				"valve 'V9': a Cv of 1e-170 on the inlet pipe's inner diameter of 0.07792 m gives a loss coefficient that is not a finite floating-point number; the solver cannot represent this valve",
				['V9']
			),
			issue('SOME_NEW_CODE', 'a message this browser does not know', ['V1'])
		];
		for (const i of kept) {
			expect(one(i, project), i.message).toEqual({
				text: i.message,
				links: i.componentIds.map((componentId) => ({ componentId }))
			});
		}
	});

	it('takes the material names and NPS designations from the pipe library', () => {
		const library = {
			material: (id: string) => (id === 'pvc' ? { name: 'PVC' } : undefined),
			nominalSizes: [{ nominalSize: 0.0635, nps: '2-1/2' }]
		};
		const options = issueTextOptions(library);
		expect(options.materialName?.('pvc')).toBe('PVC');
		expect(options.materialName?.('steel')).toBeUndefined();
		expect(options.nominalSizes).toEqual([{ nominalSize: 0.0635, nps: '2-1/2' }]);
	});
});

describe('the codes told before', () => {
	it("keep the server's message as a detail", () => {
		const project = pumpTransferExample();
		project.pumpLibrary = [];
		const i: TopologyIssue = {
			code: 'UNKNOWN_PUMP_CURVE',
			message: "pump 'P1' refers to pump curve 'C1', which is not in the pump library",
			componentIds: ['P1'],
			connectionIds: []
		};
		expect(topologyIssueViews([i], project, true)[0]!.detail).toBe(i.message);
		expect(topologyIssueViews([curveIssue()], controlledProject(), true)[0]!.detail).toBe(
			curveIssue().message
		);
		expect(topologyIssueViews([setpointIssue()], setpointProject(), true)[0]!.detail).toBe(
			setpointMessage()
		);
		const port: TopologyIssue = {
			code: 'UNCONNECTED_PORT',
			message: "port 'V1:outlet' is not connected; connect it or add a plug",
			componentIds: ['V1'],
			connectionIds: []
		};
		const open = pumpTransferExample();
		open.connections = open.connections.filter((c) => c.id !== 'L3');
		expect(topologyIssueViews([port], open, true)[0]).toEqual({
			text: 'Outlet of Discharge isolation valve is not connected: connect it or add a plug.',
			links: [{ componentId: 'V1', portId: 'outlet' }],
			detail: port.message
		});
	});
});
