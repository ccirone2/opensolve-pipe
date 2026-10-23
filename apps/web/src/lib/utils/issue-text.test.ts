/**
 * Topology issues as people read them. Issues are made-up test inputs shaped like the API's
 * (codes, component ids and message wording of apps/api solver/builder.py); expected
 * conversions are computed here from the unit definitions.
 */
import { describe, expect, it } from 'vitest';
import type { Pump, TopologyIssue } from '../api/types';
import { pumpTransferExample } from './examples';
import { topologyIssueViews } from './issue-text';
import { IMPERIAL_UNITS } from './units';

const IN = 0.0254;
const GPM = (231 * IN ** 3) / 60; // m³/s, US gallon = 231 in³
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

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
