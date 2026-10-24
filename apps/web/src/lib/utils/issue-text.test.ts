/**
 * Topology issues as people read them. Issues are made-up test inputs shaped like the API's
 * (codes, component ids and message wording of apps/api solver/builder.py); expected
 * conversions are computed here from the unit definitions.
 */
import { describe, expect, it } from 'vitest';
import type { Pump, TopologyIssue } from '../api/types';
import { assignedFlowProject } from '../testing/helpers';
import { pumpTransferExample } from './examples';
import { topologyIssueViews } from './issue-text';
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
		const [view] = topologyIssueViews([noHeadIssue(['AF1', 'PL1'], true)], project, true);
		expect(view).toEqual({
			text:
				'This part of the network has no fixed-pressure boundary: add a reservoir or reference ' +
				'node to it. Assigned-flow nodes fix a flow, not a pressure, so they do not count as one.',
			links: [{ componentId: 'AF1' }, { componentId: 'PL1' }]
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
