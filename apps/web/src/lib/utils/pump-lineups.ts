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
 * - lineupPlan and withLineupCases (§7, slice L1b): what the Pumps together card's "Add cases"
 *   block makes, By number running (one case per number of the station's pumps running, the
 *   pumps that stop first by the stop order switched off) or Each pump off (4d's cases), from
 *   the base case's solve, with its gates, words, preview, refusals, notice and undo label; the
 *   stop order (defaultStopOrder, effectiveStopOrder, movedStopOrder: page state, derived and
 *   clamped to the pumps on, decision 26) and its words.
 * - lineupChartPriority (§4.6): the order the group chart takes other cases in, one lineup of
 *   each number running first.
 * - 4d's words for one pump (memberLabels, offName, offOverride; CLAUDE.md D21 slice 4d), kept
 *   here so that pump-group-one-off.ts, which re-exports them, can use this module without the
 *   two importing each other.
 *
 * Pure: imports no store and never modifies a project.
 */
import type {
	Override,
	Project,
	PumpGroupStation,
	PumpResult,
	Scenario,
	SolveResponse
} from '../api/types';
import { componentById } from './graph';
import { canonicalJson } from './json';
import { andList, DUTY_CHECK_FLOOR } from './pump-group-chart';
import { MAX_GROUP_PUMPS, suggestGroups } from './pump-groups';
import {
	changeTarget,
	copyName,
	findScenario,
	makeOverride,
	MAX_SCENARIOS,
	newScenarioId,
	newScenarioName,
	overridesOf,
	sameValue,
	SCENARIO_NAME_LIMIT,
	scenariosOf,
	valueOf,
	withScenarios,
	type CaseId
} from './scenarios';

// ---------------------------------------------------------------------------------------------
// 4d's words for one pump (CLAUDE.md D21 slice 4d; re-exported by pump-group-one-off.ts)
// ---------------------------------------------------------------------------------------------

/** The one change of a case with one pump off: that pump's status off. */
export function offOverride(pumpId: string): Override {
	return makeOverride({ kind: 'component', componentId: pumpId }, 'status', 'off');
}

/**
 * "Pump PA off", or with the pump's id when another member has its name ("Booster pump (PA)
 * off"), the name cut to the scenario name limit as copyName cuts (never the id).
 */
export function offName(pumpName: string, id?: string): string {
	const suffix = id === undefined ? ' off' : ` (${id}) off`;
	return pumpName.length + suffix.length <= SCENARIO_NAME_LIMIT
		? `${pumpName}${suffix}`
		: `${pumpName.slice(0, SCENARIO_NAME_LIMIT - suffix.length)}${suffix}`;
}

/**
 * Each member's name in words, by id: its name, with its id after it where another member has the
 * same name ("Booster pump (PA)"), since names need not be unique (a duty and a standby unit often
 * share one).
 */
export function memberLabels(
	members: readonly { id: string; name: string }[]
): Map<string, { name: string; shared: boolean }> {
	const count = new Map<string, number>();
	for (const m of members) count.set(m.name, (count.get(m.name) ?? 0) + 1);
	return new Map(
		members.map((m) => {
			const shared = (count.get(m.name) ?? 0) > 1;
			return [m.id, { name: shared ? `${m.name} (${m.id})` : m.name, shared }];
		})
	);
}

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
	// The finder without its size limit, run once: a station of more than MAX_GROUP_PUMPS pumps is
	// found whole, and every suggestion that shares a pump with one is dropped, so its inner
	// stations (a tee ladder's) never stand for it and all its pumps go to Other (§4.2 item 5).
	// What is left is the finder's own suggestions (2 to MAX_GROUP_PUMPS pumps, its order).
	const found = suggestGroups(project, pumps, Infinity);
	const over = new Set(
		found.filter((s) => s.pumpIds.length > MAX_GROUP_PUMPS).flatMap((s) => s.pumpIds)
	);
	const suggestions = found.filter(
		(s) => s.pumpIds.length <= MAX_GROUP_PUMPS && !s.pumpIds.some((id) => over.has(id))
	);
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
 * station the finder does not suggest, one of more than MAX_GROUP_PUMPS with every station nested
 * inside it) goes last, in one 'other' group. The finder reads values too (an active PRV or PSV
 * ends a station), so a base edit of a valve's status can change the frame.
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

/** A parallel group's part: `{k} of {N} running ({list} off)`, or `{N} of {N} running`. */
function groupText(part: { pumpIds: readonly string[]; off: readonly string[] }, name: Namer) {
	const n = part.pumpIds.length;
	const k = n - part.off.length;
	return part.off.length
		? `${k} of ${n} running (${part.off.map(name).join(', ')} off)`
		: `${n} of ${n} running`;
}

/** A pump named on its own: `{label} off` or `{label} on`. */
const pumpText = (part: { id: string; status: PumpStatus }, name: Namer) =>
	`${name(part.id)} ${part.status}`;

type Namer = (id: string) => string;

/**
 * Tier 1's choice for a pump (§4.4), within `room` characters: a member of a parallel group is
 * named by its label when the group's longest possible part (every member off) fits, a pump named
 * on its own when `{label} off` fits; else by its id.
 */
function namedByLabel(
	project: Project,
	id: string,
	label: Namer,
	room: number = LINEUP_NAME_BUDGET
): boolean {
	const group = lineupGroups(project).find((g) => g.pumpIds.includes(id));
	if (group?.kind === 'parallel') {
		return groupText({ pumpIds: group.pumpIds, off: group.pumpIds }, label).length <= room;
	}
	return pumpText({ id, status: 'off' }, label).length <= room;
}

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
	const fits = (text: string) => text.length <= room;

	// 1. Per part: a group by its labels when its longest possible part fits.
	const tier1 = parts
		.map((part) => {
			if (part.kind === 'pump') {
				return pumpText(part, fits(pumpText({ ...part, status: 'off' }, label)) ? label : byId);
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
	/**
	 * 4d's form that is also the case's pure lineup name (pureLineupName): X is named on its own (a
	 * series, mixed or other group), where the template rule gives "{label} off" too.
	 */
	alsoLineup?: boolean;
}

/**
 * The case's pure lineup name: lineupName of its pump status changes alone, without
 * ` + n other changes` (§4.4). A 4d form equal to it names X as the template does, whatever the
 * case's other changes.
 */
function pureLineupName(project: Project, scenario: Scenario): string | null {
	const overrides = overridesOf(scenario).filter((o) => isPumpStatus(project, o));
	return lineupName(project, { ...scenario, overrides });
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
 *    offName of X, without or with its id (marked when it is the pure lineup name too, decided by
 *    the pumps: its other changes left out);
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
	const lineup = lineupName(project, scenario);
	if (only?.value === 'off') {
		const name = project.components.find((c) => c.id === only.id)?.name ?? only.id;
		const pure = pureLineupName(project, scenario);
		for (const withId of [false, true]) {
			const form = offName(name, withId ? only.id : undefined);
			forms.push([
				form,
				{ form: 'off', levels: 0, pump: only.id, withId, alsoLineup: form === pure }
			]);
		}
	}
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
 *    own change against the base, which stays true). A name that is the pure lineup name too (X
 *    named on its own) takes rule 3 while X is still named on its own after the edit, and so does
 *    a name whose form after is the pure lineup name after (an edit that takes X out of a parallel
 *    group), so that its other changes are counted (§4.4: a case with other changes never wears a
 *    pure lineup's name) whatever the order of the edits; it keeps 4d's form while X is in a
 *    parallel group (§15 items 2 and 5);
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
	const ownAfter = (id: string) =>
		lineupGroups(after).some((g) => g.kind !== 'parallel' && g.pumpIds.includes(id));
	if (made.form === 'off' && only && only.id === made.pump && only.value === 'off') {
		const name = after.components.find((c) => c.id === only.id)?.name ?? only.id;
		const form = offName(name, made.withId ? only.id : undefined);
		const alsoLineup =
			(made.alsoLineup && ownAfter(only.id)) || form === pureLineupName(after, now);
		if (!alsoLineup) return copies(form, made.levels);
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

// ---------------------------------------------------------------------------------------------
// §7 The Add cases block (slice L1b)
// ---------------------------------------------------------------------------------------------

/** The presets (§7.3): By number running (the default) and Each pump off (4d's cases). */
export type LineupPreset = 'running' | 'each';

/** The block's words (§7.12): its heading and region name, the preset control, the preview's label. */
export const LINEUP_BLOCK_WORDS = {
	heading: 'Add cases',
	preset: 'Cases to add',
	cases: 'Cases:'
} as const;

/** The preset control's options (§7.3). */
export const LINEUP_PRESET_LABELS: Readonly<Record<LineupPreset, string>> = {
	running: 'By number running',
	each: 'Each pump off'
};

/** The add's undo label (§7.8): By number running's, and 4d's. */
export const LINEUP_UNDO_LABELS: Readonly<Record<LineupPreset, string>> = {
	running: 'add cases by number running',
	each: 'add cases with one pump off'
};

/**
 * A pump carries flow in a solve (§3.5, decision 14): not off, its |operatingFlow| above
 * DUTY_CHECK_FLOOR, whatever its state word. A pump that is on and carries no flow is idle,
 * whether its status reads `no_flow` or `running` (on behind a closed valve: the solver keeps its
 * link open at zero flow).
 */
export function carriesFlow(
	result: Pick<PumpResult, 'status' | 'operatingFlow'> | undefined
): boolean {
	return !!result && result.status !== 'off' && Math.abs(result.operatingFlow) > DUTY_CHECK_FLOOR;
}

/** 4d's notice after Each pump off's add (unchanged). */
export function addedNotice(names: readonly string[]): string {
	return `Added ${names.length} ${plural(names.length, 'case', 'cases')} with one pump off: ${andList(names)}. Solve all solves every case not yet solved; Undo removes them.`;
}

/** The notice after the add (§7.8): By number running's, names in «», or 4d's addedNotice. */
export function lineupNotice(preset: LineupPreset, names: readonly string[]): string {
	if (preset === 'each') return addedNotice(names);
	return `Added ${names.length} ${plural(names.length, 'case', 'cases')} by number running: ${quotedList(names)}. Solve all solves every case not yet solved; Undo removes them.`;
}

/** "«A», «B» and «C»": names hold commas and parentheses (decision 22). */
const quotedList = (names: readonly string[]) => andList(names.map((n) => `«${n}»`));

// ---- The stop order (§7.5) --------------------------------------------------------------------

/** The stop order's words (§7.12): its hint, list name, item notes, buttons and status line. */
export const STOP_ORDER_WORDS = {
	hint: 'The first in this list stops first. The cases below change as you move pumps.',
	list: 'Stop order',
	first: ' (stops first)',
	last: ' (stays on in every case)',
	idle: ' (carries no flow in the base case)',
	earlier: (name: string) => `Stop ${name} earlier`,
	later: (name: string) => `Stop ${name} later`,
	atFirst: 'Already the first to stop.',
	atLast: 'Already the last to stop.',
	reset: 'Default order',
	resetHint: "The default: the last pump in the group's list stops first.",
	moved: (name: string, i: number, n: number) => `${name} is now number ${i} of ${n} to stop.`,
	resetDone: (name: string) => `Default order: ${name} stops first.`
} as const;

/** The default stop order (§7.5): the pumps on, reversed, so the last listed stops first. */
export function defaultStopOrder(on: readonly string[]): string[] {
	return [...on].reverse();
}

/** `order` holds exactly the pumps `on`, each once. */
function sameMembers(order: readonly string[], on: readonly string[]): boolean {
	return (
		order.length === on.length &&
		new Set(order).size === order.length &&
		on.every((id) => order.includes(id))
	);
}

/**
 * The stop order used (§7.5, decision 26), derived and never written by an effect: the saved one
 * (page state, written only by the move buttons and Default order) while it holds exactly the
 * pumps on, else the default, nothing merged. A saved order comes back when the same pumps are on
 * again (after an Undo, say): it is the user's last choice for that set.
 */
export function effectiveStopOrder(saved: readonly string[], on: readonly string[]): string[] {
	return sameMembers(saved, on) ? [...saved] : defaultStopOrder(on);
}

/** `order` with `id` one place earlier ('up') or later ('down'); unchanged at an end. */
export function movedStopOrder(order: readonly string[], id: string, dir: 'up' | 'down'): string[] {
	const next = [...order];
	const i = next.indexOf(id);
	const j = dir === 'up' ? i - 1 : i + 1;
	if (i < 0 || j < 0 || j >= next.length) return next;
	[next[i], next[j]] = [next[j]!, next[i]!];
	return next;
}

/**
 * The stop order's summary (§7.5), the pumps named as the group's names name them (§4.4, tier
 * 1): by their labels, or by their ids where those names use ids ("Stop order: P6 first, then
 * P5, P4, P3 and P2; P1 stays on in every case" on the condenser example).
 */
export function stopOrderSummary(project: Project, order: readonly string[]): string {
	const labels = pumpLabels(project);
	const label = (id: string) => labels.get(id) ?? id;
	const name = (id: string) => (namedByLabel(project, id, label) ? label(id) : id);
	const first = name(order[0] ?? '');
	const last = name(order.at(-1) ?? '');
	if (order.length <= 2) return `Stop order: ${first} stops; ${last} stays on in every case`;
	const middle = andList(order.slice(1, -1).map(name));
	return `Stop order: ${first} first, then ${middle}; ${last} stays on in every case`;
}

/** The stop order as the block shows it (By number running only). */
export interface StopOrderView {
	/** The order used: the first stops first. */
	order: readonly string[];
	/** It is the default: "Default order" is not shown. */
	isDefault: boolean;
	/** The disclosure's summary. */
	summary: string;
	/** One per pump, in order: its full label (project-wide) and its muted note. */
	items: readonly { id: string; label: string; note: string }[];
}

// ---- The plan (§7.2, §7.4 to §7.8) ------------------------------------------------------------

export interface LineupPlanInput {
	/** The stored project (its scenarios, names and component order). */
	project: Project;
	/** The case shown (ws.store.activeCase). */
	shownCase: CaseId;
	/** The station the card shows; null: no block. */
	station: PumpGroupStation | null;
	/** The card's members. */
	memberIds: readonly string[];
	/** The base case's response by Compare's rule, and whether it is out of date. */
	base: { response: SolveResponse; stale: boolean } | null;
	preset: LineupPreset;
	/** The saved stop order (page state, ws.pumpStopOrder); used while it holds exactly the pumps on. */
	savedOrder: readonly string[];
}

/** Which gate holds (§7.2), in 4d's order. */
export type LineupGate = 'series' | 'mixed' | 'scenario' | 'stale' | 'fewer_on' | 'no_flow';

/** One case of the plan, in plan order: one preview item. */
export interface LineupPlanCase {
	/**
	 * 'add': the add makes it; 'existing': a scenario is the same case (sameCase), the first in
	 * case order; 'base_state': every pump it stops carries no flow in the base case, so it would
	 * repeat the base (§3.5) and is not made.
	 */
	kind: 'add' | 'existing' | 'base_state';
	/** The members it switches off, its changes (status off), in component order. */
	stopped: readonly string[];
	/** Its name: lineupName of the case as written, or 4d's offName under Each pump off. */
	name: string;
	/** add: the id it takes; existing: that scenario's id; base_state: null. */
	id: string | null;
	/** existing: that scenario's name. */
	existingName: string | null;
	/** add: the first scenario in case order with exactly its name (another case), else null. */
	sameNameId: string | null;
	/** The preview item. */
	words: string;
}

/** A case the add makes: `{id, name, overrides}`, its overrides `stopped`'s statuses off. */
export interface LineupCaseToAdd {
	id: string;
	name: string;
	stopped: readonly string[];
}

export interface LineupPlan {
	preset: LineupPreset;
	/** Why nothing is offered (null: offered), and which gate. */
	gate: string | null;
	gateKind: LineupGate | null;
	/** The block's Solve all is drawn: offered, or gates 4 to 6. */
	showSolveAll: boolean;
	/** What the preset makes (null under a gate). */
	about: string | null;
	/** The interchangeability sentence (§7.6; By number running only). */
	sentence: string | null;
	/** The stop order (By number running only). */
	stopOrder: StopOrderView | null;
	cases: readonly LineupPlanCase[];
	/** The cases to add, in plan order (withLineupCases). */
	add: readonly LineupCaseToAdd[];
	/** The cases that exist, with the scenario that is each. */
	existing: readonly { stopped: readonly string[]; scenarioId: string; scenarioName: string }[];
	/** The members on and carrying no flow in the base case (component order). */
	idle: readonly string[];
	/** Which group the names count, when the members are not one parallel group of the frame (§7.7). */
	frame: string | null;
	/** Why the add is refused: nothing to add, or past the scenario limit (null: it can be made). */
	refusal: string | null;
	/** "Add 3 cases"; "Add cases" when there is nothing to add. */
	label: string;
	undoLabel: string;
	/** The notice after the add (null when there is nothing to add). */
	notice: string | null;
}

/** The ids `count` new scenarios take, each the first free one on the growing project (4d's). */
function newIds(project: Project, count: number): string[] {
	const ids: string[] = [];
	let next = project;
	for (let i = 0; i < count; i++) {
		const id = newScenarioId(next);
		ids.push(id);
		next = withScenarios(next, [...scenariosOf(next), { id, name: id, overrides: [] }]);
	}
	return ids;
}

/**
 * The interchangeability sentence (§7.6), from the base as solved: a fact of the inputs (one
 * curve id, one speed as equal doubles, no speed control), never a claim that the pumps give the
 * same answer, nor that they differ.
 */
function curveSentence(
	project: Project,
	on: readonly string[],
	results: SolveResponse['solvedState']['pumpResults'],
	label: Namer
): string {
	const curveOf = (id: string) => {
		const pump = componentById(project, id);
		return pump?.type === 'pump' ? pump.curveId : null;
	};
	const first = on[0];
	const shared =
		first !== undefined &&
		curveOf(first) !== null &&
		on.every((id) => {
			const r = results[id];
			return (
				!!r && !r.control && curveOf(id) === curveOf(first) && r.speed === results[first]!.speed
			);
		});
	return shared
		? `${andList(on.map(label))} have the same pump curve and speed. Which of them run can still change the answer, through the tees and each pump's own piping, most when few run: change the stop order to compare which run at each count; Each pump off compares them with one off.`
		: 'Not all of these pumps have the same pump curve and speed without a speed control, so which of them run can change the answer: the stop order decides which stop first.';
}

/**
 * Which group the names count (§7.7, §1.5 item 1), when the card's members are not one parallel
 * group of the frame: a subset ticked by hand, or a station the finder does not suggest.
 */
function frameWords(project: Project, members: readonly string[], label: Namer): string | null {
	const groups = lineupGroups(project).filter(
		(g) => g.kind === 'parallel' && g.pumpIds.some((id) => members.includes(id))
	);
	if (!groups.length) return 'Names list each pump on its own.';
	const [only] = groups;
	if (groups.length === 1 && only && sameMembers(only.pumpIds, members)) return null;
	return groups
		.map((g) => `Names count every pump of the group ${andList(g.pumpIds.map(label))}.`)
		.join(' ');
}

/**
 * What the Add cases block would make now (§7.4), or why it is not offered (§7.2, gates in 4d's
 * order: a parallel station; the base case shown; its results current; two members or more on;
 * one carrying flow). Every term is read from the base case's current results: a member is on
 * when its status is not 'off', carries flow when on with |operatingFlow| above
 * DUTY_CHECK_FLOOR, is idle when on without (carriesFlow).
 *
 * - By number running: for k = |On| − 1 down to 1, the first |On| − k pumps of the stop order
 *   (effectiveStopOrder) stopped, written as `status: off` for those pumps only, in component
 *   order whatever the stop order (base-off pumps get no change and stay off), named by
 *   lineupName; a case whose stopped pumps are all idle is the base case's state and not made.
 * - Each pump off: 4d's cases, one per member carrying flow, named by offName (memberLabels over
 *   the members); an idle member gets none.
 *
 * A planned case is existing when a scenario is the same case (sameCase: equal effective
 * changes), the first in case order named with its id; one added while another case has its name
 * says so. Ids are the first free on the growing project. Without a station, nothing (no block).
 */
export function lineupPlan(input: LineupPlanInput): LineupPlan {
	const { project, shownCase, station, base, preset } = input;
	const plan = (
		gateKind: LineupGate | null,
		gate: string | null,
		showSolveAll: boolean
	): LineupPlan => ({
		preset,
		gate,
		gateKind,
		showSolveAll,
		about: null,
		sentence: null,
		stopOrder: null,
		cases: [],
		add: [],
		existing: [],
		idle: [],
		frame: null,
		refusal: null,
		label: 'Add cases',
		undoLabel: LINEUP_UNDO_LABELS[preset],
		notice: null
	});
	if (!station) return plan(null, null, false);
	if (station.arrangement === 'series') {
		return plan(
			'series',
			'Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.',
			false
		);
	}
	if (station.arrangement === 'mixed') {
		return plan(
			'mixed',
			'Cases are added here for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.',
			false
		);
	}
	if (shownCase !== null) {
		const shown = findScenario(project, shownCase)?.name ?? shownCase;
		return plan(
			'scenario',
			`Cases are made from the base case: show the base case to add them. To study ${shown} with pumps off, duplicate it in Scenarios and set those pumps off there.`,
			false
		);
	}
	if (!base || base.stale) {
		return plan(
			'stale',
			"The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now.",
			true
		);
	}
	const members = pumpsInOrder(project, input.memberIds);
	// 4d's labels, over the card's members: Each pump off's names and About, and gate 5.
	const ownLabels = memberLabels(
		members.map((id) => ({ id, name: componentById(project, id)?.name ?? id }))
	);
	const own = (id: string) => ownLabels.get(id)?.name ?? id;
	// Project-wide labels (decision 8): every other text of the block that names a pump.
	const labels = pumpLabels(project);
	const label = (id: string) => labels.get(id) ?? id;
	const results = base.response.solvedState.pumpResults;
	const on = members.filter((id) => results[id] && results[id].status !== 'off');
	const off = members.filter((id) => results[id]?.status === 'off');
	if (on.length < 2) {
		return plan(
			'fewer_on',
			`Needs two or more of these pumps switched on in the base case: ${andList(off.map(own))} ${off.length === 1 ? 'is' : 'are'} off.`,
			true
		);
	}
	const carrying = on.filter((id) => carriesFlow(results[id]));
	const idle = on.filter((id) => !carriesFlow(results[id]));
	if (!carrying.length) {
		return plan(
			'no_flow',
			'No pump of the group carries flow in the base case, so switching pumps off changes nothing.',
			true
		);
	}

	// The cases wanted, in plan order: the pumps each stops and its name.
	const wanted: { stopped: string[]; name: string }[] = [];
	const ordered = (ids: Iterable<string>) => {
		const set = new Set(ids);
		return members.filter((id) => set.has(id));
	};
	const caseOf = (stopped: readonly string[]): Scenario => ({
		id: '',
		name: '',
		overrides: stopped.map(offOverride)
	});
	let stopView: StopOrderView | null = null;
	if (preset === 'running') {
		const order = effectiveStopOrder(input.savedOrder, on);
		for (let k = on.length - 1; k >= 1; k--) {
			const stopped = ordered(order.slice(0, on.length - k));
			wanted.push({ stopped, name: lineupName(project, caseOf(stopped)) ?? '' });
		}
		stopView = {
			order,
			isDefault: order.join('\u0000') === defaultStopOrder(on).join('\u0000'),
			summary: stopOrderSummary(project, order),
			items: order.map((id, i) => ({
				id,
				label: label(id),
				note:
					(i === 0 ? STOP_ORDER_WORDS.first : '') +
					(i === order.length - 1 ? STOP_ORDER_WORDS.last : '') +
					(idle.includes(id) ? STOP_ORDER_WORDS.idle : '')
			}))
		};
	} else {
		for (const id of on) {
			const plain = componentById(project, id)?.name ?? id;
			wanted.push({
				stopped: [id],
				name: offName(plain, ownLabels.get(id)?.shared ? id : undefined)
			});
		}
	}

	const scenarios = scenariosOf(project);
	const cases: LineupPlanCase[] = [];
	for (const w of wanted) {
		const item = { stopped: w.stopped, name: w.name, existingName: null, sameNameId: null };
		if (w.stopped.every((id) => idle.includes(id))) {
			const which = w.stopped.map(label);
			cases.push({
				...item,
				kind: 'base_state',
				id: null,
				words: `${w.name}: not made, the base case's state (${andList(which)} ${plural(which.length, 'carries', 'carry')} no flow in the base case)`
			});
			continue;
		}
		const planned = caseOf(w.stopped);
		const found = scenarios.find((s) => sameCase(project, planned, s));
		if (found) {
			cases.push({
				...item,
				kind: 'existing',
				id: found.id,
				existingName: found.name,
				words:
					found.name === w.name
						? `${w.name}: already a scenario (${found.id})`
						: `${w.name}: already a scenario, «${found.name}» (${found.id})`
			});
			continue;
		}
		const named = scenarios.find((s) => s.name === w.name);
		cases.push({
			...item,
			kind: 'add',
			id: null,
			sameNameId: named?.id ?? null,
			words: named
				? `${w.name}: scenario ${named.id} has this name too but is another case`
				: w.name
		});
	}
	const adding = cases.filter((c) => c.kind === 'add');
	const ids = newIds(project, adding.length);
	adding.forEach((c, i) => (c.id = ids[i]!));
	const add = adding.map((c) => ({ id: c.id!, name: c.name, stopped: c.stopped }));
	const existing = cases
		.filter((c) => c.kind === 'existing')
		.map((c) => ({ stopped: c.stopped, scenarioId: c.id!, scenarioName: c.existingName! }));

	const total = scenarios.length + add.length;
	let refusal: string | null = null;
	if (!add.length) {
		const names = existing.map((e) => e.scenarioName);
		refusal =
			preset === 'each'
				? `Every case with one pump off already exists: ${andList(names)}.`
				: cases.some((c) => c.kind === 'base_state')
					? "Nothing to add: each case by number running already exists or is the base case's state."
					: `Every case by number running already exists: ${quotedList(names)}.`;
	} else if (total > MAX_SCENARIOS) {
		refusal = `Adding ${add.length} ${plural(add.length, 'case', 'cases')} would make ${total} scenarios; a project holds at most ${MAX_SCENARIOS} scenarios.`;
	}

	const about =
		preset === 'each'
			? `Makes one scenario per pump running in the base case (${andList(carrying.map(own))}): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.`
			: [
					on.length >= 3
						? `Makes one scenario for each number of these pumps running, from ${on.length - 1} down to 1: the base case with the pumps that stop first switched off and nothing else changed.`
						: 'Makes one scenario with one of these pumps running: the base case with the pump that stops first switched off and nothing else changed.',
					...(off.length
						? [
								`${andList(off.map(label))} ${plural(off.length, 'is', 'are')} off in the base case and ${plural(off.length, 'stays', 'stay')} off in every case.`
							]
						: []),
					"In a case's name, running means switched on; Running combinations shows whether each pump carries flow. Other sets of the same number of pumps are not made: change the stop order and add again to compare them."
				].join(' ');

	return {
		preset,
		gate: null,
		gateKind: null,
		showSolveAll: true,
		about,
		sentence: preset === 'running' ? curveSentence(project, on, results, label) : null,
		stopOrder: stopView,
		cases,
		add,
		existing,
		idle,
		frame: preset === 'running' ? frameWords(project, members, label) : null,
		refusal,
		label: add.length ? `Add ${add.length} ${plural(add.length, 'case', 'cases')}` : 'Add cases',
		undoLabel: LINEUP_UNDO_LABELS[preset],
		notice: add.length
			? lineupNotice(
					preset,
					add.map((a) => a.name)
				)
			: null
	};
}

/**
 * The project with the cases added, in order (§7.8, one undo step): `{id, name, overrides}`, each
 * id the first free one on the growing project (S1, S2, …), its overrides the stopped pumps'
 * statuses off in component order, no description.
 */
export function withLineupCases(
	project: Project,
	cases: readonly { name: string; stopped: readonly string[] }[]
): Project {
	let next = project;
	for (const c of cases) {
		const scenario: Scenario = {
			id: newScenarioId(next),
			name: c.name,
			overrides: pumpsInOrder(project, c.stopped).map(offOverride)
		};
		next = withScenarios(next, [...scenariosOf(next), scenario]);
	}
	return next;
}

// ---------------------------------------------------------------------------------------------
// §4.6 The chart's order
// ---------------------------------------------------------------------------------------------

/**
 * The order the group chart takes the other cases in (§4.6, decision 16; chartKeys keeps the first
 * MAX_GROUP_CASES ticked). This station's lineups are the base (key '') when it is another case,
 * and every scenario that is status-only over the card's members and whose members off differ
 * from the base's; each counts its members on. First the first lineup of each count, most running
 * first; then the other lineups, most running first; then every other case; ties in case order
 * (the order of `keys`). With six pumps and both presets the six places hold the whole 5-to-1
 * family.
 */
export function lineupChartPriority(
	keys: readonly { key: string; caseId: CaseId }[],
	project: Project,
	memberIds: readonly string[]
): string[] {
	const base = pumpLineup(undefined, project, memberIds);
	const running = (caseId: CaseId): number | null => {
		if (caseId === null) return base.on.length;
		const lineup = pumpLineup(findScenario(project, caseId), project, memberIds);
		const differs = lineup.off.join('\u0000') !== base.off.join('\u0000');
		return lineup.statusOnly && differs ? lineup.on.length : null;
	};
	const lineups = keys
		.map((k, i) => ({ key: k.key, i, on: running(k.caseId) }))
		.flatMap((k) => (k.on === null ? [] : [{ ...k, on: k.on }]))
		.sort((a, b) => b.on - a.on || a.i - b.i);
	const counted = new Set<number>();
	const firsts = lineups.filter((k) => {
		if (counted.has(k.on)) return false;
		counted.add(k.on);
		return true;
	});
	const others = lineups.filter((k) => !firsts.includes(k));
	const listed = new Set(lineups.map((k) => k.key));
	return [
		...firsts.map((k) => k.key),
		...others.map((k) => k.key),
		...keys.filter((k) => !listed.has(k.key)).map((k) => k.key)
	];
}
