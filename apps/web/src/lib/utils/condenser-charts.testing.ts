/**
 * The condenser example's chart fixture (__fixtures__/condenser-charts.json, written by
 * apps/api/tests/fixtures/condenser_charts.py through the real API, `pnpm gen:types`;
 * docs/proposals/open-defects-2.md §2 C1 and X, §3 C2 and C3): each case's project, its members
 * as the Pumps together card takes them, and its recorded answers. Nothing here computes a value:
 * the responses are the API's.
 */
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	Scenario,
	SystemCurveResponse
} from '$lib/api/types';
import fixture from './__fixtures__/condenser-charts.json';
import { ratedCurveRange } from './pump-chart';
import type { GroupMemberInput } from './pump-group-chart';

/** The cases recorded (condenser_charts.py's CASES). */
export type CondenserCase = 'base' | 'winter' | 'basin15' | 'p6off' | 'single24';

interface Recorded {
	edits: { componentId: string; field: string; value: unknown }[];
	/** The case's solver options over the example's (single24: tolerance 1e-12, the recorder's). */
	solverOptions?: Partial<Project['settings']['solverOptions']>;
	scenarios?: Scenario[];
	scenarioId: string | null;
	memberIds: string[];
	pumpResults?: Record<string, PumpResult>;
	flags?: Flag[];
	groupCurve?: PumpGroupCurveResponse;
	systemCurve?: PumpGroupCurveResponse;
	pumpSystemCurve?: SystemCurveResponse;
}

const cases = fixture.cases as unknown as Record<CondenserCase, Recorded>;

/** The example as shipped, as the fixture was recorded from it (utils/examples.ts). */
export const condenserProject = (): Project => structuredClone(fixture.project) as Project;

/** The case's project: the shipped one with the case's edits, solver options and scenarios. */
export function condenserCaseProject(name: CondenserCase): Project {
	const c = cases[name];
	const project = condenserProject();
	for (const e of c.edits) {
		const component = project.components.find((x) => x.id === e.componentId)!;
		(component as unknown as Record<string, unknown>)[e.field] = e.value;
	}
	if (c.solverOptions)
		project.settings.solverOptions = { ...project.settings.solverOptions, ...c.solverOptions };
	if (c.scenarios) project.scenarios = structuredClone(c.scenarios);
	return project;
}

/** The case as recorded: its scenario solved, members and answers. */
export function condenserCase(name: CondenserCase): Recorded {
	return structuredClone(cases[name]);
}

/** The case's members as the card takes them (its PumpResults and flags as solved), in slots. */
export function condenserMembers(name: CondenserCase): GroupMemberInput[] {
	const c = cases[name];
	const project = condenserCaseProject(name);
	return c.memberIds.map((id, slot) => {
		const pump = project.components.find((x) => x.id === id)!;
		return {
			id,
			name: pump.name,
			result: structuredClone(c.pumpResults![id]!),
			ratedRange: ratedCurveRange(project, id),
			curveId: pump.type === 'pump' ? pump.curveId : null,
			slot,
			flags: (c.flags ?? []).filter((f) => f.componentId === id)
		};
	});
}

/**
 * The base case's group system curve as an API deployed before C2 (open-defects-2.md §3) answers
 * it: the same points, its system duty check not agreeing on the vertical part, in that API's
 * words (this fixture as recorded from 593378d's API, at 63184ca). The web relays whichever
 * verdict the API gives, so its words for this one stay tested.
 */
export function baseBeforeC2(): PumpGroupCurveResponse {
	const system = structuredClone(cases.base.systemCurve!);
	system.systemDutyCheck = {
		agrees: false,
		head: null,
		message:
			"the rest of the network with the station's flow 5.67812 m³/s forced from S to D has no rise (the rise across the station is undetermined: at this flow FCV 'F2' passes exactly its setpoint flow, so the valve could also hold it throttled, with any rise across the station at or above 24.6265 m (with the valve fully open), and no reservoir or reference node fixes the pressure between the valve and the station), so the group system curve is not shown to pass through the duty"
	};
	return system;
}
