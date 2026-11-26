/**
 * The condenser example's chart fixture (__fixtures__/condenser-charts.json, written by
 * __fixtures__/condenser-charts.record.py from main's API; docs/proposals/open-defects-2.md §2,
 * C1 and X): each case's project, its members as the Pumps together card takes them, and its
 * recorded answers. Nothing here computes a value: the responses are the API's.
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

/** The cases recorded (condenser-charts.record.py's CASES). */
export type CondenserCase = 'base' | 'winter' | 'basin15' | 'p6off' | 'single24';

interface Recorded {
	edits: { componentId: string; field: string; value: unknown }[];
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

/** The case's project: the shipped one with the case's edits and scenarios. */
export function condenserCaseProject(name: CondenserCase): Project {
	const c = cases[name];
	const project = condenserProject();
	for (const e of c.edits) {
		const component = project.components.find((x) => x.id === e.componentId)!;
		(component as unknown as Record<string, unknown>)[e.field] = e.value;
	}
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
