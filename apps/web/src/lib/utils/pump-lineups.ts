/**
 * Pump lineups (CLAUDE.md D24, proposal pump-lineups.md §4): the one reader of a case's pumps and
 * the one naming rule, for the Pumps together card, the Pump lineups table and the chart. A lineup
 * is an ordinary D15 scenario whose changes are pump statuses (decision 1): nothing here changes a
 * model, a request or a solved value.
 *
 * - pumpLineup (§4.1): a case read as the pumps it switches on and off, whatever the order of its
 *   changes (a map from pump to status, every list in component order).
 * - lineupGroups and frameKey (§4.2): the frame names count over, the station finder's
 *   suggestions on the base case over every pump, partitioned largest first: 'series', 'mixed' (a
 *   group the finder calls parallel that holds a series chain), 'parallel', and every other pump
 *   in one 'other' group, last. It reads the base only, never the card's page state, so a name is
 *   the same whether made on the card, in Build or in the table, and after a reload (decision 7).
 * - effectiveChanges and sameCase (§4.3): equal effective changes give the same project after D15's
 *   apply, so the same solve bit for bit; a change equal to the base value or one that no longer
 *   applies changes nothing.
 * - lineupName (§4.4): "2 of 4 running (Pump P3, Pump P4 off)", within LINEUP_NAME_BUDGET so that
 *   Duplicate's " (copy)" never cuts one; it never lists only some of the pumps off in a group
 *   (tiers by ids, then counts), names pumps in series or in a mixed group one by one (decision
 *   24) and ends " + n other changes" when the case has other effective changes.
 * - followLineupNames and renameNotice (§4.5): a name the app made follows its pumps until the
 *   user renames it, by a stateless rule (no flag in the model), in the same undo step as the edit
 *   (the project store runs it inside every update), and every rename is said.
 * - solvedCaseWords (§5): a case named by its stored name where the server's record of a solve
 *   names it, with the name it was solved under when they differ.
 *
 * Pure: imports no store and never modifies a project.
 */
import type { Override, Project, Scenario } from '../api/types';
import { canonicalJson } from './json';
import { memberLabels, offName } from './pump-group-one-off';
import { suggestGroups } from './pump-groups';
import {
	changeTarget,
	copyName,
	findScenario,
	makeOverride,
	newScenarioName,
	overridesOf,
	sameValue,
	SCENARIO_NAME_LIMIT,
	scenariosOf,
	valueOf,
	withScenarios
} from './scenarios';

// ---------------------------------------------------------------------------------------------
// Pumps of a project
// ---------------------------------------------------------------------------------------------

type PumpStatus = 'on' | 'off';

/** Component index by id (the project's order). */
function componentOrder(project: Project): Map<string, number> {
	return new Map(project.components.map((c, i) => [c.id, i]));
}

function isPump(project: Project, id: string): boolean {
	return project.components.some((c) => c.id === id && c.type === 'pump');
}

/** The pumps among `ids`, each once, in component order. */
function pumpsInOrder(project: Project, ids: readonly string[]): string[] {
	const order = componentOrder(project);
	return [...new Set(ids)]
		.filter((id) => isPump(project, id))
		.sort((a, b) => (order.get(a) ?? Infinity) - (order.get(b) ?? Infinity));
}

/** A pump's status in the base ('on' unless it is off). */
function baseStatus(project: Project, id: string): PumpStatus {
	const pump = project.components.find((c) => c.id === id);
	return pump?.type === 'pump' && pump.status === 'off' ? 'off' : 'on';
}

/** A status value as the API reads it: 'off', else 'on'. */
const statusValue = (value: unknown): PumpStatus => (value === 'off' ? 'off' : 'on');

/** A change of a pump's status (a pump of `project`). */
function isPumpStatus(
	project: Project,
	o: Override
): o is Extract<Override, { kind: 'component' }> {
	return o.kind === 'component' && o.field === 'status' && isPump(project, o.componentId);
}

/** The scenario's changes of pumps' statuses, by pump (the last wins), in component order. */
function pumpStatusChanges(
	project: Project,
	scenario: Scenario | undefined
): { id: string; value: PumpStatus }[] {
	const set = new Map<string, PumpStatus>();
	for (const o of overridesOf(scenario)) {
		if (isPumpStatus(project, o)) set.set(o.componentId, statusValue(o.value));
	}
	return pumpsInOrder(project, [...set.keys()]).map((id) => ({ id, value: set.get(id)! }));
}

/** A pump's status in a case: the scenario's change where it sets one, else the base's. */
function caseStatus(project: Project, scenario: Scenario | undefined): (id: string) => PumpStatus {
	const set = new Map(pumpStatusChanges(project, scenario).map((c) => [c.id, c.value]));
	return (id) => set.get(id) ?? baseStatus(project, id);
}

/**
 * Every pump's label, project-wide (decision 8): its name, or "Name (id)" where another pump has
 * the same name (memberLabels over every pump).
 */
function pumpLabels(project: Project): Map<string, string> {
	const pumps = project.components.filter((c) => c.type === 'pump');
	const labels = memberLabels(pumps.map((c) => ({ id: c.id, name: c.name })));
	return new Map([...labels].map(([id, label]) => [id, label.name]));
}

// ---------------------------------------------------------------------------------------------
// §4.1 A case's pumps
// ---------------------------------------------------------------------------------------------

export interface PumpLineup {
	/** The pumps read (`pumpIds` that are pumps of `project`), in component order. */
	members: readonly string[];
	/** Members switched off / on in the case: the scenario's status where it sets one, else the base's. */
	off: readonly string[];
	on: readonly string[];
	/** The member statuses the scenario sets, by value (component order). */
	setOff: readonly string[];
	setOn: readonly string[];
	/** Every other change: another pump's status, any other value, a change that no longer applies. */
	other: readonly Override[];
	/** Every change is a member's status, and there is one at least. */
	statusOnly: boolean;
}

/**
 * `scenario` (undefined: the base) read as a lineup of the pumps `pumpIds` (§4.1). It reads a map
 * from pump to status, so the order of the changes does not matter. To read a case as solved, pass
 * that case's project (the store's caseInputs) with `scenario` undefined.
 */
export function pumpLineup(
	scenario: Scenario | undefined,
	project: Project,
	pumpIds: readonly string[]
): PumpLineup {
	const members = pumpsInOrder(project, pumpIds);
	const inside = new Set(members);
	const set = new Map<string, PumpStatus>();
	const other: Override[] = [];
	for (const o of overridesOf(scenario)) {
		if (o.kind === 'component' && o.field === 'status' && inside.has(o.componentId)) {
			set.set(o.componentId, statusValue(o.value));
		} else other.push(o);
	}
	const status = (id: string) => set.get(id) ?? baseStatus(project, id);
	return {
		members,
		off: members.filter((id) => status(id) === 'off'),
		on: members.filter((id) => status(id) === 'on'),
		setOff: members.filter((id) => set.get(id) === 'off'),
		setOn: members.filter((id) => set.get(id) === 'on'),
		other,
		statusOnly: other.length === 0 && overridesOf(scenario).length > 0
	};
}

// ---------------------------------------------------------------------------------------------
// §4.2 The frame
// ---------------------------------------------------------------------------------------------

export interface LineupGroup {
	kind: 'parallel' | 'series' | 'mixed' | 'other';
	pumpIds: readonly string[];
}

/** The frame of the projects seen last, by what the finder reads (a few kept: before and after). */
const framesByInputs = new Map<string, readonly LineupGroup[]>();
const FRAMES_KEPT = 8;
/** The frame of a stored (frozen) project, by the object itself. */
const framesByProject = new WeakMap<Project, readonly LineupGroup[]>();

/**
 * What the finder reads: the components without their names, and the connections. Names only
 * label a group, and a scenario never changes these (D15), so every case has the base's frame.
 */
function finderInputs(project: Project): string {
	return JSON.stringify([
		project.components.map((c) => ({ ...c, name: undefined })),
		project.connections
	]);
}

function findFrame(project: Project): LineupGroup[] {
	const order = componentOrder(project);
	const pumps = project.components.filter((c) => c.type === 'pump').map((c) => c.id);
	const suggestions = suggestGroups(project, pumps);
	const series = suggestions.filter((s) => s.kind === 'series');
	const taken = new Set<string>();
	const groups: LineupGroup[] = [];
	// The finder's order is the largest first: a suggestion is kept when none of its pumps is.
	for (const s of suggestions) {
		if (s.pumpIds.some((id) => taken.has(id))) continue;
		for (const id of s.pumpIds) taken.add(id);
		const holdsChain = series.some((c) => c.pumpIds.every((id) => s.pumpIds.includes(id)));
		groups.push({
			kind: s.kind === 'series' ? 'series' : holdsChain ? 'mixed' : 'parallel',
			pumpIds: s.pumpIds
		});
	}
	groups.sort((a, b) => (order.get(a.pumpIds[0]!) ?? 0) - (order.get(b.pumpIds[0]!) ?? 0));
	const rest = pumps.filter((id) => !taken.has(id));
	if (rest.length) groups.push({ kind: 'other', pumpIds: rest });
	return groups;
}

/**
 * The frame of pump groups (§4.2): the station finder (suggestGroups) on the base case over every
 * pump, each suggestion kept in the finder's order (largest first) when none of its pumps is
 * already taken; a kept series suggestion is 'series', a kept parallel one that holds a series
 * chain of its pumps 'mixed' (the finder calls a 2 × 2 station parallel, the API mixed), any other
 * 'parallel'. Groups go by their first pump's component order; every pump in none (a lone pump, a
 * station the finder does not suggest, one of more than MAX_GROUP_PUMPS) goes last, in one 'other'
 * group. The finder reads values too (an active PRV or PSV ends a station), so a base edit of a
 * valve's status can change the frame.
 *
 * Memoised on what the finder reads (the components without their names, and the connections, a
 * part of the base's hydraulic fingerprint), so a scenario edit or a rename never runs it again.
 */
export function lineupGroups(project: Project): readonly LineupGroup[] {
	const known = framesByProject.get(project);
	if (known) return known;
	const key = finderInputs(project);
	let groups = framesByInputs.get(key);
	if (groups) framesByInputs.delete(key);
	else groups = findFrame(project);
	framesByInputs.set(key, groups);
	if (framesByInputs.size > FRAMES_KEPT) {
		framesByInputs.delete(framesByInputs.keys().next().value as string);
	}
	// Only a frozen project (the store's) is kept by object: a draft may still change.
	if (Object.isFrozen(project)) framesByProject.set(project, groups);
	return groups;
}

/** A short key of the frame (each group's kind and pumps), compared before and after an edit (§4.5). */
export function frameKey(groups: readonly LineupGroup[]): string {
	return groups.map((g) => `${g.kind}:${g.pumpIds.join(',')}`).join(';');
}

// ---------------------------------------------------------------------------------------------
// §4.3 The same case
// ---------------------------------------------------------------------------------------------

/** The scenario's changes that change the project: each applies and differs from the base value. */
function effective(project: Project, scenario: Scenario | undefined): Override[] {
	return overridesOf(scenario).filter((o) => {
		const base = valueOf(project, changeTarget(o), o.field);
		// undefined: the change no longer applies (orphaned or not applicable, D15).
		return base !== undefined && !sameValue(o.value, base);
	});
}

/** The effective changes of a case: each applied change whose value differs from the base's, as canonical JSON. */
export function effectiveChanges(
	project: Project,
	scenario: Scenario | undefined
): ReadonlySet<string> {
	return new Set(
		effective(project, scenario).map((o) =>
			canonicalJson(makeOverride(changeTarget(o), o.field, o.value))
		)
	);
}

function sameSet(a: ReadonlySet<string>, b: ReadonlySet<string>): boolean {
	return a.size === b.size && [...a].every((x) => b.has(x));
}

/**
 * Two cases (undefined: the base) are the same case: their effective changes are equal, so D15's
 * apply gives the same project and the same solve bit for bit (§4.3, decision 13). A change that no
 * longer applies or equals the base value changes nothing, and order does not matter.
 */
export function sameCase(
	project: Project,
	a: Scenario | undefined,
	b: Scenario | undefined
): boolean {
	return sameSet(effectiveChanges(project, a), effectiveChanges(project, b));
}

// ---------------------------------------------------------------------------------------------
// §4.4 The name
// ---------------------------------------------------------------------------------------------

/** Lineup names fit this, the name limit less Duplicate's " (copy)" (decision 11): 93. */
export const LINEUP_NAME_BUDGET = SCENARIO_NAME_LIMIT - ' (copy)'.length;

type NamePart =
	/** A parallel group holding a named pump: its members off in the case (component order). */
	| { kind: 'group'; pumpIds: readonly string[]; off: readonly string[] }
	/** A named pump of a series, mixed or other group, with its status in the case. */
	| { kind: 'pump'; id: string; status: PumpStatus };

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/**
 * The name of `scenario`'s pumps (§4.4), or null when it changes no pump's status. The pumps named
 * are those it sets a status for, whatever the value; the parts follow the frame (lineupGroups):
 * a parallel group holding one gives `{k} of {N} running ({list} off)` (every member off in the
 * case, base-off ones included, or `{N} of {N} running`), each named pump of a series, mixed or
 * other group `{label} off` / `{label} on`, joined by "; ". Other effective changes end it with
 * ` + {n} other change(s)`. Within LINEUP_NAME_BUDGET, the first tier whose whole name fits:
 * 1. per part, a parallel group by its labels when its longest part (every member off) fits, else
 *    by ids; a pump on its own by its label when `{label} off` fits, else by its id;
 * 2. every part by ids;
 * 3. counts per part (the pumps named on their own as one part, last);
 * 4. one count over every pump of the groups named and every pump named on its own.
 * No tier lists only some of the pumps off in a group, or calls a pump that is on off (§5).
 */
export function lineupName(project: Project, scenario: Scenario): string | null {
	const named = new Set(pumpStatusChanges(project, scenario).map((c) => c.id));
	if (!named.size) return null;
	const status = caseStatus(project, scenario);
	const parts: NamePart[] = [];
	for (const group of lineupGroups(project)) {
		if (group.kind === 'parallel') {
			if (group.pumpIds.some((id) => named.has(id))) {
				parts.push({
					kind: 'group',
					pumpIds: group.pumpIds,
					off: group.pumpIds.filter((id) => status(id) === 'off')
				});
			}
			continue;
		}
		// Series and mixed groups, and the other pumps: in series a stopped pump stops its partner
		// (D21), so "k of N running" would name a case where nothing flows (decision 24).
		for (const id of group.pumpIds) {
			if (named.has(id)) parts.push({ kind: 'pump', id, status: status(id) });
		}
	}
	const others = effective(project, scenario).filter((o) => !isPumpStatus(project, o)).length;
	const suffix = others ? ` + ${others} other ${plural(others, 'change', 'changes')}` : '';
	// The suffix is kept whole; the pump parts fit the rest.
	const room = LINEUP_NAME_BUDGET - suffix.length;
	const labels = pumpLabels(project);
	const label = (id: string) => labels.get(id) ?? id;
	const byId = (id: string) => id;
	const groupText = (part: Extract<NamePart, { kind: 'group' }>, name: (id: string) => string) => {
		const n = part.pumpIds.length;
		const k = n - part.off.length;
		return part.off.length
			? `${k} of ${n} running (${part.off.map(name).join(', ')} off)`
			: `${n} of ${n} running`;
	};
	const pumpText = (part: Extract<NamePart, { kind: 'pump' }>, name: (id: string) => string) =>
		`${name(part.id)} ${part.status}`;
	const fits = (text: string) => text.length <= room;

	// 1. Per part: a group by its labels when its longest possible part fits.
	const tier1 = parts
		.map((part) => {
			if (part.kind === 'pump') {
				return pumpText(part, fits(`${label(part.id)} off`) ? label : byId);
			}
			const longest = groupText({ ...part, off: part.pumpIds }, label);
			return groupText(part, fits(longest) ? label : byId);
		})
		.join('; ');
	if (fits(tier1)) return `${tier1}${suffix}`;

	// 2. Every part by ids.
	const tier2 = parts
		.map((part) => (part.kind === 'pump' ? pumpText(part, byId) : groupText(part, byId)))
		.join('; ');
	if (fits(tier2)) return `${tier2}${suffix}`;

	// 3. Counts per part; the pumps named on their own as one part.
	const groups = parts.filter((p): p is Extract<NamePart, { kind: 'group' }> => p.kind === 'group');
	const own = parts.filter((p): p is Extract<NamePart, { kind: 'pump' }> => p.kind === 'pump');
	const ownOff = own.filter((p) => p.status === 'off').length;
	const ownOn = own.length - ownOff;
	const ownText = [
		...(ownOff ? [`${ownOff} other ${plural(ownOff, 'pump', 'pumps')} off`] : []),
		...(ownOn ? [`${ownOn} other ${plural(ownOn, 'pump', 'pumps')} on`] : [])
	].join(', ');
	const tier3 = [
		...groups.map((g) => {
			const n = g.pumpIds.length;
			return g.off.length
				? `${n - g.off.length} of ${n} running (${g.off.length} off)`
				: `${n} of ${n} running`;
		}),
		...(ownText ? [ownText] : [])
	].join('; ');
	if (fits(tier3)) return `${tier3}${suffix}`;

	// 4. One count.
	const total = groups.reduce((n, g) => n + g.pumpIds.length, 0) + own.length;
	const off = groups.reduce((n, g) => n + g.off.length, 0) + ownOff;
	const tier4 = off
		? `${total - off} of ${total} pumps running (${off} off)`
		: `${total} of ${total} pumps running`;
	return `${tier4}${suffix}`;
}

// ---------------------------------------------------------------------------------------------
// §4.5 Names that follow
// ---------------------------------------------------------------------------------------------

export interface Rename {
	from: string;
	to: string;
}

/**
 * A necessary test for a name the app made (§4.5's cost): "Scenario n", or a name with " running"
 * or ending in " off", " on", " change(s)" or " (copy)". Every app-made form passes it.
 */
const APP_NAME_PATTERN = /^Scenario \d+$| running| (?:off|on|changes?|\(copy\))$/;

/** How a name is the app's: its form, its pump (4d's form) and its copy levels. */
interface AppMade {
	form: 'empty' | 'off' | 'lineup';
	/** The number of copyName applications (0: not a copy). */
	levels: number;
	/** 4d's form: the pump X it names, and whether with its id ("Booster pump (PA) off"). */
	pump?: string;
	withId?: boolean;
}

/** The levels of copyName that turn `base` into `name` (0: itself), or null when none does. */
function copyLevels(base: string, name: string): number | null {
	let x = base;
	for (let c = 0; ; c++) {
		if (x === name) return c;
		const next = copyName(x);
		// copyName stops changing at the name limit, where it cuts and so drops an earlier copy.
		if (next === x) return null;
		x = next;
	}
}

/** `name` with `levels` applications of copyName. */
function copies(name: string, levels: number): string {
	let x = name;
	for (let c = 0; c < levels; c++) x = copyName(x);
	return x;
}

/**
 * Whether `scenario`'s name is one the app made, on `project` (§4.5's appNames):
 * 1. "Scenario n" (newScenarioName of its own id) while it has no changes;
 * 2. its lineupName, while it changes a pump's status;
 * 3. while its pump status changes are exactly one, a pump X off (other changes allowed), 4d's
 *    offName of X, without or with its id;
 * 4. a copy of form 2 or 3, any number deep ("Scenario n (copy)" is not one: n is its own id's).
 */
function appMade(project: Project, scenario: Scenario): AppMade | null {
	if (!overridesOf(scenario).length) {
		return scenario.name === newScenarioName(project, scenario.id)
			? { form: 'empty', levels: 0 }
			: null;
	}
	const forms: [string, AppMade][] = [];
	const statuses = pumpStatusChanges(project, scenario);
	const only = statuses.length === 1 ? statuses[0]! : null;
	if (only?.value === 'off') {
		const name = project.components.find((c) => c.id === only.id)?.name ?? only.id;
		forms.push([offName(name), { form: 'off', levels: 0, pump: only.id, withId: false }]);
		forms.push([offName(name, only.id), { form: 'off', levels: 0, pump: only.id, withId: true }]);
	}
	const lineup = lineupName(project, scenario);
	if (lineup !== null) forms.push([lineup, { form: 'lineup', levels: 0 }]);
	for (const [base, made] of forms) {
		const levels = copyLevels(base, scenario.name);
		if (levels !== null) return { ...made, levels };
	}
	return null;
}

const statusKey = (changes: readonly { id: string; value: PumpStatus }[]) =>
	changes.map((c) => `${c.id}=${c.value}`).join(',');

/**
 * The name an app-made name takes after the edit (§4.5's rule), for the scenario `before`'s `old`,
 * now `now` in `after`:
 * 1. "Scenario n" when it changes no pump's status (it claims nothing);
 * 2. 4d's form for X while its pump status changes are still exactly X off: the same form with X's
 *    name after (only status changes are compared, and a base edit never renames it: it names its
 *    own change against the base, which stays true);
 * 3. otherwise its lineupName after;
 * 4. a copy keeps its levels only while its own pump status changes are as they were (a pump's
 *    rename, a base edit, a change of the frame): the copy still copies the same case.
 */
function followedName(
	made: AppMade,
	before: Project,
	old: Scenario,
	after: Project,
	now: Scenario
): string {
	const statuses = pumpStatusChanges(after, now);
	if (!statuses.length) return newScenarioName(after, now.id);
	const kept = statusKey(pumpStatusChanges(before, old)) === statusKey(statuses);
	const only = statuses.length === 1 ? statuses[0]! : null;
	if (made.form === 'off' && only && only.id === made.pump && only.value === 'off') {
		const name = after.components.find((c) => c.id === only.id)?.name ?? only.id;
		return copies(offName(name, made.withId ? only.id : undefined), made.levels);
	}
	const name = lineupName(after, now) ?? newScenarioName(after, now.id);
	return kept ? copies(name, made.levels) : name;
}

/** The pumps' ids, names and statuses: the labels and base statuses names read. */
function pumpsKey(project: Project): string {
	return JSON.stringify(
		project.components.filter((c) => c.type === 'pump').map((c) => [c.id, c.name, c.status])
	);
}

/**
 * Names that follow (§4.5, decision 12): each scenario of `after` that was in `before` with the
 * same name (a rename in the same edit is the user's and wins), whose name the app made on
 * `before`, takes the name the rule gives on `after` when it differs. New scenarios (an add, a
 * duplicate) are not followed. Stateless: no flag is stored, and a name the user typed is never
 * touched unless it is one of these very names.
 *
 * It does nothing unless some scenario's name passes the app-made pattern and the edit changed a
 * pump's status, name or presence in the base, that scenario's changes or which of them are
 * effective (a base value they set, or whether they still apply: the ` + n other changes` count),
 * or the frame.
 */
export function followLineupNames(
	before: Project,
	after: Project
): { project: Project; renamed: Rename[] } {
	const unchanged = { project: after, renamed: [] };
	const candidates = new Map<string, Scenario>();
	for (const s of scenariosOf(after)) {
		const old = findScenario(before, s.id);
		if (old && old.name === s.name && APP_NAME_PATTERN.test(s.name)) candidates.set(s.id, old);
	}
	if (!candidates.size) return unchanged;
	const touched =
		pumpsKey(before) !== pumpsKey(after) ||
		[...candidates].some(([id, old]) => {
			const now = findScenario(after, id);
			return (
				canonicalJson(overridesOf(old)) !== canonicalJson(overridesOf(now)) ||
				!sameSet(effectiveChanges(before, old), effectiveChanges(after, now))
			);
		}) ||
		frameKey(lineupGroups(before)) !== frameKey(lineupGroups(after));
	if (!touched) return unchanged;
	const renamed: Rename[] = [];
	const scenarios = scenariosOf(after).map((s) => {
		const old = candidates.get(s.id);
		const made = old ? appMade(before, old) : null;
		if (!old || !made) return s;
		const name = followedName(made, before, old, after, s);
		if (name === s.name) return s;
		renamed.push({ from: s.name, to: name });
		return { ...s, name };
	});
	return renamed.length ? { project: withScenarios(after, scenarios), renamed } : unchanged;
}

/**
 * A solved scenario named as it is stored, with the name it was solved under when a rename came
 * after the solve (§5): the Methods text's case, "scenario {name} ({id})" and ", solved as «{old}»".
 * A rename leaves a case current (names are not hydraulic inputs), and a name the app made follows
 * its pumps without the user's hand, so the response's own name can be an older one.
 */
export function solvedCaseWords(stored: string, solved: { id: string; name: string }): string {
	const under = stored === solved.name ? '' : `, solved as «${solved.name}»`;
	return `scenario ${stored} (${solved.id})${under}`;
}

/**
 * What the renames say (§4.5), with «» around names, which hold commas and parentheses
 * (decision 22): one rename in full, two each in full, more than two by count with one example.
 * Empty when there is none.
 */
export function renameNotice(renamed: readonly Rename[]): string {
	const pair = (r: Rename) => `«${r.from}» is now «${r.to}»`;
	const rule = 'A name the app made follows its pumps until you rename it.';
	const [first, second] = renamed;
	if (!first) return '';
	if (!second) {
		return `${pair(first)}: a name the app made follows its pumps until you rename it.`;
	}
	if (renamed.length === 2) {
		return `Renamed 2 scenarios to match their pumps: ${pair(first)}; ${pair(second)}. ${rule}`;
	}
	return `Renamed ${renamed.length} scenarios to match their pumps, for example ${pair(first)}. ${rule}`;
}
