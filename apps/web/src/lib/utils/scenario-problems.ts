/**
 * Problems of a scenario's case, found in the browser (proposal scenario-manager.md §6.4, §6.11):
 * the case's project (the base with the scenario's changes) checked as any project is, by the
 * schema and the model rules, each problem traced to the change that set the value. A base edit
 * can make a scenario's value invalid (a minimum speed raised above the speed a scenario sets);
 * that is reported here, never refused (GOALS §4.6), and the API rejects the scenario's solve
 * with the same problem (400, located at the change). A rule of a whole element (a minimum speed
 * below the speed, a custom pipe's bore) is put, as the API puts it, at the changes of that
 * element whose base value clears it, or at all of them when no single one does: never at a
 * valid change beside the invalid one.
 */
import type { Override, Project, Scenario, UnitPreferences } from '../api/types';
import { componentById, connectionById } from './graph';
import { componentOverrideFields, pipeOverrideFields, projectOverrideFields } from './model-rules';
import { applyScenario, overridesOf, withScenarios } from './scenarios';
import { SI_UNITS } from './units';
import { modelRuleIssues, schemaIssues } from './validate';

export interface ScenarioProblem {
	/** The change it is about (0-based index into the scenario's changes), or null: the case. */
	index: number | null;
	/** What is wrong, in people's words. */
	text: string;
}

/** JSON pointers of where a change's value is in the project (several for a pipe's spec). */
function pointers(project: Project, override: Override): string[] {
	if (override.kind === 'component') {
		const index = project.components.findIndex((c) => c.id === override.componentId);
		const component = project.components[index];
		const entry = component ? componentOverrideFields(component)[override.field] : undefined;
		return entry ? [`/components/${index}/${entry.path.join('/')}`] : [];
	}
	if (override.kind === 'pipe') {
		const index = project.connections.findIndex((c) => c.id === override.connectionId);
		const entry = pipeOverrideFields()[override.field];
		if (index === -1 || !entry) return [];
		const pipe = `/connections/${index}/piping/pipes/${override.pipeIndex}`;
		return entry.keys.length
			? entry.keys.map((k) => `${pipe}/${k}`)
			: [`${pipe}/${entry.path.join('/')}`];
	}
	const entry = projectOverrideFields()[override.field];
	return entry ? [`/${entry.path.join('/')}`] : [];
}

/** Whether `a` and `b` are the same place, or one lies inside the other. */
function overlaps(a: string, b: string): boolean {
	return a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
}

/** The schema's sentence without its location ('components[3] "P1" › speed: must be <= 1'). */
function detail(text: string): string {
	const at = text.indexOf(': ');
	return at === -1 ? text : text.slice(at + 2);
}

/**
 * Of the changes a problem is about, those that cause it: each whose base value clears it (the
 * case's project with that change left out no longer has it), or all of them when none does
 * alone (proposal scenario-manager.md §4.1 step 4).
 */
function causes<T extends { index: number }>(
	owners: T[],
	stillThere: (project: Project) => boolean,
	without: (index: number) => Project
): T[] {
	if (owners.length < 2) return owners;
	const found = owners.filter((owner) => !stillThere(without(owner.index)));
	return found.length ? found : owners;
}

/**
 * The problems of scenario `scenarioId`'s case: values that are not a pipe specification, schema
 * problems of the values it sets, and model-rule problems the base does not have (each with the
 * changes on the element it names that cause it, or the case as a whole).
 */
export function scenarioProblems(
	base: Project,
	scenarioId: string,
	units: UnitPreferences = SI_UNITS
): ScenarioProblem[] {
	const applied = applyScenario(base, scenarioId);
	if (!applied.scenario) return [];
	const scenario: Scenario = applied.scenario;
	const problems: ScenarioProblem[] = [];
	/** The case's project with change `index` left out (its base value applies). */
	const cache = new Map<number, Project>();
	const without = (index: number): Project => {
		let project = cache.get(index);
		if (!project) {
			const fewer = { ...scenario, overrides: overridesOf(scenario).filter((_, i) => i !== index) };
			const others = (base.scenarios ?? []).map((s) => (s.id === scenario.id ? fewer : s));
			project = applyScenario(withScenarios(base, others), scenarioId).project;
			cache.set(index, project);
		}
		return project;
	};
	const rulesOf = (project: Project): ReturnType<typeof modelRuleIssues> => {
		try {
			return modelRuleIssues(project, units);
		} catch {
			return []; // a value of the wrong type (reported as a schema problem) stops a rule
		}
	};
	const live = applied.changes.filter((c) => c.state === 'applied');
	for (const change of live) {
		if (change.invalid) {
			problems.push({
				index: change.index,
				text: 'a pipe specification has a material and optionally a schedule, a nominal size, an inner diameter and a roughness, or a pipe spec of the project library alone, and nothing else'
			});
		}
	}
	const located = live
		.filter((c) => !c.invalid)
		.map((c) => ({ index: c.index, at: pointers(applied.project, c.override) }));
	for (const issue of schemaIssues(applied.project)) {
		const found = located.filter((l) => l.at.some((p) => overlaps(p, issue.pointer)));
		const owners = causes(
			found,
			(project) =>
				schemaIssues(project).some((i) => i.pointer === issue.pointer && i.text === issue.text),
			without
		);
		if (!owners.length) problems.push({ index: null, text: detail(issue.text) });
		for (const owner of owners) problems.push({ index: owner.index, text: detail(issue.text) });
	}
	const known = new Set(modelRuleIssues(base, units).map((i) => i.text));
	for (const issue of rulesOf(applied.project)) {
		if (known.has(issue.text)) continue;
		const found = live.filter(({ override: o }) =>
			o.kind === 'component'
				? issue.componentId === o.componentId && !issue.connectionId
				: o.kind === 'pipe'
					? issue.connectionId === o.connectionId &&
						(issue.pipeIndex === undefined || issue.pipeIndex === o.pipeIndex)
					: false
		);
		const owners = causes(
			found,
			(project) => rulesOf(project).some((i) => i.text === issue.text),
			without
		);
		if (!owners.length) problems.push({ index: null, text: issue.message });
		for (const owner of owners) problems.push({ index: owner.index, text: issue.message });
	}
	return problems;
}

/** Whether the change's target still has a name in `project` (for "Show"). */
export function changeElement(
	project: Project,
	override: Override
): { kind: 'component' | 'connection'; id: string } | null {
	if (override.kind === 'component') {
		return componentById(project, override.componentId)
			? { kind: 'component', id: override.componentId }
			: null;
	}
	if (override.kind === 'pipe') {
		return connectionById(project, override.connectionId)
			? { kind: 'connection', id: override.connectionId }
			: null;
	}
	return null;
}
