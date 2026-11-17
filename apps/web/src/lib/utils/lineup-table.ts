/**
 * The Pump lineups table (CLAUDE.md D24, proposal pump-lineups.md §8, slice L2): the model of the
 * Scenarios manager's "Pump lineups" tab, every case × every pump, and every word it says. The
 * panel (components/workspace/PumpLineups.svelte) draws it; a press is Build's own edit through
 * ws.editScenario (§8.6).
 *
 * - lineupTable (§8.3 to §8.5): the columns are the frame (pump-lineups.ts lineupGroups, on the
 *   base case) cut to the card's pumps when filtered, empty groups dropped; each group's header
 *   words; each pump's label (project-wide, memberLabels over every pump) and id; the rows, the
 *   base case first (read-only), then each scenario in the project's order, with its notes ("{n}
 *   other changes": pumpLineup's `other` over the columns shown; "Same case as …": the first
 *   earlier row, the base first, that is the same case by sameCase's rule); each cell's value, its
 *   base value and whether it is the case's own value (a change equal to the base value is still
 *   the case's own, as Build's Changed is).
 * - lineupPress (§8.6): what a press writes, Build's Status segment's change, with its undo label
 *   ("turn {pump label} {on|off}"; editScenario adds " in {scenario name}"); lineupReset (§8.10):
 *   the phone's Reset of a change equal to the base value, which removes it as Build's Reset does.
 * - activeCell (§8.7, decision 26): the cell holding the grid's one Tab stop, derived from the
 *   cell the user last wanted and clamped to the table as it is now.
 * - pickedCase, pickerOptions and pickedLine (§8.10, decision 26): the phone's one case at a time.
 * - newLineup (§8.8), shownManagerTab (§8.1) and LINEUP_TABLE_WORDS (§8.12, word for word).
 *
 * It says only inputs: each case's status of each pump, which value is the case's own, and which
 * cases are the same case (§8.11). Pure: imports no store and never modifies a project.
 */
import type { Component, Override, Project } from '../api/types';
import { updateComponent } from './edit';
import { entryFor } from './field-registry';
import { schemaChoices } from './model-rules';
import { andList } from './pump-group-chart';
import {
	effectiveChanges,
	lineupGroups,
	memberLabels,
	pumpLineup,
	type LineupGroup,
	type PumpLineup
} from './pump-lineups';
import {
	changesText,
	LIMIT_TEXT,
	MAX_CHANGES,
	MAX_SCENARIOS,
	newScenarioId,
	newScenarioName,
	overridesOf,
	scenariosOf,
	withScenarios,
	type CaseId
} from './scenarios';

/** A pump's status, as the schema's values (`schemaChoices('Pump', 'status')`). */
export type PumpStatus = 'on' | 'off';

// ---------------------------------------------------------------------------------------------
// §8.12 Every new UI string, word for word
// ---------------------------------------------------------------------------------------------

/** The Pump lineups tab's words (§8.12). Functions fill in names, counts and labels. */
export const LINEUP_TABLE_WORDS = {
	// Tabs and table
	casesTab: (n: number) => `Cases (${n})`,
	lineupsTab: 'Pump lineups',
	tablist: 'Scenarios view',
	caption: 'Pumps on or off in each case',
	// Intros and lines
	/** The desktop intro before the corner mark (the mark itself is aria-hidden). */
	intro:
		"Each case's pumps, on or off; in a name, running means switched on. Pressing a cell turns that pump on or off in that case only, the same change as in Build, one undo step each; the base case is changed in Build.",
	/** The desktop intro after the corner mark. */
	introMark: "A corner mark is the case's own value; unmarked cells follow the base case.",
	phoneIntro:
		'Pick a case, then turn its pumps on or off: the same change as in Build, one undo step each; in a name, running means switched on. The base case is changed in Build.',
	filter: (labels: readonly string[]) =>
		`Only the pumps on the Pumps together card are shown: ${andList(labels)}.`,
	showEvery: 'Show every pump',
	series:
		'Pumps in series: one off stops the flow through their line (an off pump passes no flow).',
	full: LIMIT_TEXT,
	// Headers and rows
	parallel: (ids: string) => `Pumps together, ${ids}`,
	inSeries: (ids: string) => `Pumps together, in series, ${ids}`,
	someInSeries: (ids: string) => `Pumps together, some in series, ${ids}`,
	otherPumps: 'Other pumps',
	caseHeader: 'Case',
	baseCase: 'Base case',
	setInBuild: 'Set in Build',
	shown: 'Shown',
	otherChanges: (n: number) => `${n} other ${n === 1 ? 'change' : 'changes'}`,
	sameCase: (other: { name: string; id: string } | null) =>
		other ? `Same case as «${other.name}» (${other.id})` : 'Same case as the base case',
	// Cells
	/** A switch's accessible name: its visible headers, never its state word (§8.5). */
	cellName: (pumpLabel: string, caseName: string) => `${pumpLabel} ${caseName}`,
	changed: (baseWord: string) => `Changed in this scenario. Base value ${baseWord}.`,
	// Footer
	undo: 'Undo',
	undoNamed: (label: string) => `Undo ${label}`,
	redo: 'Redo',
	redoNamed: (label: string) => `Redo ${label}`,
	newLineup: 'New lineup',
	done: 'Done',
	// The manager's status and alert lines
	added: (name: string) => `Added «${name}», its pumps as in the base case.`,
	undid: (label: string) => `Undid ${label}.`,
	redid: (label: string) => `Redid ${label}.`,
	nowShowing: (caseWords: string) => ` Now showing ${caseWords}.`,
	couldNot: (label: string, scenarioName: string, message: string) =>
		`Could not ${label} in ${scenarioName}: ${message}`,
	// The undo label (editScenario adds " in {scenario name}", the name after the step)
	turn: (pumpLabel: string, next: PumpStatus) => `turn ${pumpLabel} ${next}`,
	/** The phone's Reset of a change equal to the base value: Build's Reset label of its field. */
	reset: (pumpLabel: string) => `reset ${pumpLabel}`,
	// Phone
	caseToEdit: 'Case to edit',
	option: (name: string, changes: string) => `${name} (${changes})`,
	scenarioLine: (name: string, n: number) =>
		`Changes go to «${name}» only: ${n} of at most ${MAX_CHANGES} changes.`,
	baseLine: "The base case's pumps: change them in Build.",
	baseItem: (pumpLabel: string, word: string) => `${pumpLabel}: ${word}`,
	// The Pumps together card's button
	cardButton: 'Pump lineups table…'
} as const;

/** New lineup's undo label: New scenario's (§8.8). */
export const NEW_LINEUP_LABEL = 'add scenario';

// ---------------------------------------------------------------------------------------------
// The state words: the schema's values, the registry's labels (§8.5)
// ---------------------------------------------------------------------------------------------

/** A pump's status values and their words: `schemaChoices('Pump', 'status')`, labelled by the registry. */
export function statusChoices(): { value: string; label: string }[] {
	const input = entryFor('Pump', 'status')?.input;
	const labels: Readonly<Record<string, string>> = input?.kind === 'choice' ? input.labels : {};
	return schemaChoices('Pump', 'status').map((value) => ({ value, label: labels[value] ?? value }));
}

/** The state word of a status ('On', 'Off'), the registry's. */
export function statusWord(value: PumpStatus): string {
	return statusChoices().find((c) => c.value === value)?.label ?? value;
}

// ---------------------------------------------------------------------------------------------
// §8.3 to §8.5 The table
// ---------------------------------------------------------------------------------------------

/** A group of columns: a group of the frame cut to the pumps shown (§8.3). */
export interface LineupColumnGroup {
	kind: LineupGroup['kind'];
	/** Its pumps shown, in the frame's order. */
	pumpIds: readonly string[];
	/** Its header in the group row: "Pumps together, P1 to P3", …, "Other pumps". */
	header: string;
}

/** A column: one pump (§8.3). */
export interface LineupColumn {
	/** The pump's id, shown under its label. */
	id: string;
	/** Its label, project-wide: its name, or "Name (id)" where another pump has that name. */
	label: string;
	/** The index of its group in `groups`. */
	group: number;
	/** The first column of its group (the 2 px divider goes before it, from the second group). */
	first: boolean;
}

/**
 * A cell (§8.5): `base`, the case follows the base case (unmarked); `changed`, the case's own value,
 * which differs from the base's; `same`, the case's own value equal to the base's, still marked (as
 * Build's Changed is).
 */
export type CellState = 'base' | 'changed' | 'same';

export interface LineupCell {
	pumpId: string;
	/** The pump's status in the case (the switch's aria-checked: on). */
	value: PumpStatus;
	/** Its status in the base case. */
	base: PumpStatus;
	state: CellState;
	/** The case sets its own value (changed or same): the ring, the corner mark and `description`. */
	marked: boolean;
	/** A pump off in the base case that the case turns on: a standby put in service. */
	standbyOn: boolean;
	/** The state word shown ("On", "Off"; the switch's value, never its name). */
	word: string;
	/** For a marked cell: "Changed in this scenario. Base value Off." (its description and title). */
	description: string | null;
}

export interface LineupRow {
	/** The case: null, the base case (read-only); else the scenario's id. */
	caseId: CaseId;
	/** "Base case" or the scenario's name. */
	name: string;
	/** The scenario's id (null for the base case). */
	id: string | null;
	/** A scenario that is the case shown ("Shown", §8.4); never the base row. */
	shown: boolean;
	/** A scenario's stored changes (of at most MAX_CHANGES); 0 for the base row. */
	changes: number;
	/** One per line: the base row's "Set in Build"; a scenario's other changes and same case. */
	notes: readonly string[];
	/** One per column, in column order. */
	cells: readonly LineupCell[];
}

export interface LineupTable {
	groups: readonly LineupColumnGroup[];
	/** Every column, group after group. */
	columns: readonly LineupColumn[];
	/** The group header row is shown: two groups or more (§8.3). */
	groupRow: boolean;
	/** The base case, then each scenario in the project's order (§8.4). */
	rows: readonly LineupRow[];
	/** The pumps of the filter that exist (null: every pump shown). */
	filter: readonly string[] | null;
	/** The filter's sentence (null without one): "Only the pumps on the Pumps together card …". */
	filterText: string | null;
	/** A series or mixed group is shown: the intro ends with the series sentence. */
	series: boolean;
}

export interface LineupTableInput {
	/** The stored project: the base case and its scenarios (ws.store.project). */
	project: Project;
	/** The case shown (ws.store.activeCase). */
	shownCase: CaseId;
	/** The card's pumps (ws.managerPumps), or null: every pump. */
	filter: readonly string[] | null;
}

/** "PA", "PA and PB", "P1 to P3": a group's first and last columns, by id (§8.3). */
function idsText(ids: readonly string[]): string {
	if (ids.length <= 1) return ids.join('');
	if (ids.length === 2) return `${ids[0]} and ${ids[1]}`;
	return `${ids[0]} to ${ids[ids.length - 1]}`;
}

/**
 * A group's header (§8.3): it names its first and last columns, so two stations never read alike,
 * and never says "in parallel" (the API names the arrangement, D21) or "station".
 */
export function groupHeader(kind: LineupGroup['kind'], pumpIds: readonly string[]): string {
	const words = LINEUP_TABLE_WORDS;
	const ids = idsText(pumpIds);
	switch (kind) {
		case 'parallel':
			return words.parallel(ids);
		case 'series':
			return words.inSeries(ids);
		case 'mixed':
			return words.someInSeries(ids);
		default:
			return words.otherPumps;
	}
}

/** Every pump's label, project-wide (decision 8): memberLabels over every pump. */
function pumpLabels(project: Project): Map<string, string> {
	const pumps = project.components.filter((c) => c.type === 'pump');
	const labels = memberLabels(pumps.map((c) => ({ id: c.id, name: c.name })));
	return new Map([...labels].map(([id, label]) => [id, label.name]));
}

/** The pumps of the frame shown, cut to `filter` (null: every pump), empty groups dropped. */
function shownGroups(project: Project, filter: ReadonlySet<string> | null): LineupColumnGroup[] {
	return lineupGroups(project)
		.map((g) => ({
			kind: g.kind,
			pumpIds: filter ? g.pumpIds.filter((id) => filter.has(id)) : g.pumpIds
		}))
		.filter((g) => g.pumpIds.length > 0)
		.map((g) => ({ ...g, header: groupHeader(g.kind, g.pumpIds) }));
}

/** The cells of a case's lineup over the pumps shown, against the base case's lineup. */
function cellsOf(
	lineup: PumpLineup,
	base: PumpLineup,
	ids: readonly string[],
	words: Readonly<Record<PumpStatus, string>>
): LineupCell[] {
	return ids.map((pumpId) => {
		const value: PumpStatus = lineup.on.includes(pumpId) ? 'on' : 'off';
		const baseValue: PumpStatus = base.on.includes(pumpId) ? 'on' : 'off';
		const marked = lineup.setOn.includes(pumpId) || lineup.setOff.includes(pumpId);
		const state: CellState = !marked ? 'base' : value === baseValue ? 'same' : 'changed';
		return {
			pumpId,
			value,
			base: baseValue,
			state,
			marked,
			standbyOn: marked && value === 'on' && baseValue === 'off',
			word: words[value],
			description: marked ? LINEUP_TABLE_WORDS.changed(words[baseValue]) : null
		};
	});
}

/**
 * The table (§8.3 to §8.5): the frame's groups cut to the filter's pumps (empty groups dropped;
 * a filter none of whose pumps exists any more shows every pump, so the table never loses its
 * columns), the base row and one row per scenario. A row's notes:
 * - `{n} other change(s)`, n = pumpLineup(S, base, columns shown).other.length: the stored changes
 *   other than the statuses of the pumps shown (statuses of pumps the filter hides and changes
 *   that no longer apply included; a name's " + n other changes" counts only effective ones);
 * - `Same case as «{name}» ({id})` or `Same case as the base case`: the first earlier row, the base
 *   first, with equal effective changes (sameCase's rule, effectiveChanges compared once per row).
 */
export function lineupTable(input: LineupTableInput): LineupTable {
	const { project, shownCase } = input;
	const pumps = new Set(project.components.filter((c) => c.type === 'pump').map((c) => c.id));
	const kept = input.filter ? input.filter.filter((id) => pumps.has(id)) : [];
	const filter = kept.length ? new Set(kept) : null;
	const groups = shownGroups(project, filter);
	const labels = pumpLabels(project);
	const columns: LineupColumn[] = groups.flatMap((g, group) =>
		g.pumpIds.map((id, i) => ({ id, label: labels.get(id) ?? id, group, first: i === 0 }))
	);
	const ids = columns.map((c) => c.id);
	const words = { on: statusWord('on'), off: statusWord('off') };
	const base = pumpLineup(undefined, project, ids);
	const scenarios = scenariosOf(project);
	const effective = [undefined, ...scenarios].map((s) => effectiveChanges(project, s));
	const sameSet = (a: ReadonlySet<string>, b: ReadonlySet<string>) =>
		a.size === b.size && [...a].every((x) => b.has(x));

	const rows: LineupRow[] = [
		{
			caseId: null,
			name: LINEUP_TABLE_WORDS.baseCase,
			id: null,
			shown: false,
			changes: 0,
			notes: [LINEUP_TABLE_WORDS.setInBuild],
			cells: cellsOf(base, base, ids, words)
		},
		...scenarios.map((s, i) => {
			const notes: string[] = [];
			const lineup = pumpLineup(s, project, ids);
			const other = lineup.other.length;
			if (other) notes.push(LINEUP_TABLE_WORDS.otherChanges(other));
			const mine = effective[i + 1]!;
			const earlier = effective.slice(0, i + 1).findIndex((e) => sameSet(e, mine));
			if (earlier === 0) notes.push(LINEUP_TABLE_WORDS.sameCase(null));
			else if (earlier > 0) {
				const twin = scenarios[earlier - 1]!;
				notes.push(LINEUP_TABLE_WORDS.sameCase({ name: twin.name, id: twin.id }));
			}
			return {
				caseId: s.id,
				name: s.name,
				id: s.id,
				shown: s.id === shownCase,
				changes: overridesOf(s).length,
				notes,
				cells: cellsOf(lineup, base, ids, words)
			};
		})
	];

	return {
		groups,
		columns,
		groupRow: groups.length >= 2,
		rows,
		filter: filter ? [...ids] : null,
		filterText: filter ? LINEUP_TABLE_WORDS.filter(columns.map((c) => c.label)) : null,
		series: groups.some((g) => g.kind === 'series' || g.kind === 'mixed')
	};
}

// ---------------------------------------------------------------------------------------------
// §8.6 A press
// ---------------------------------------------------------------------------------------------

export interface LineupPress {
	pumpId: string;
	/** The status written. */
	next: PumpStatus;
	/** The undo label before editScenario adds " in {scenario name}": "turn Pump PA off". */
	label: string;
	/**
	 * The edit, the same as Build's Status segment (RegistryField through ws.editComponent): the
	 * pump's status set to `next`, in a copy of the case's project.
	 */
	change: (draft: Project) => Project;
}

/**
 * What setting `column`'s pump to `next` writes (§8.6): a press gives the other value; the phone's
 * Reset gives the base value. Through ws.editScenario(scenarioId, change, label, { quiet: true }).
 */
export function lineupPress(column: LineupColumn, next: PumpStatus): LineupPress {
	return {
		pumpId: column.id,
		next,
		label: LINEUP_TABLE_WORDS.turn(column.label, next),
		change: (draft) =>
			updateComponent(draft, column.id, (c) => ({ ...c, status: next }) as Component)
	};
}

/** A press of a cell: its other value. */
export function cellPress(column: LineupColumn, cell: LineupCell): LineupPress {
	return lineupPress(column, cell.value === 'on' ? 'off' : 'on');
}

/**
 * The phone's Reset of a case's own status of `column`'s pump that equals the base value (cell
 * state 'same', §8.10): pressing the base value would leave the case as it is, so the change is
 * removed, as Build's Reset removes it (workspace fieldChange().reset). One stored step
 * (ws.updateStoredQuiet, the commit path, so the name rule applies), labelled as Build's Reset of
 * the phone's field, which the pump's label names: "reset {pump label} in {scenario name}", the
 * name after the step.
 */
export function lineupReset(
	caseId: string,
	column: LineupColumn
): {
	caseId: string;
	/** The undo label, given the scenario's name after the step. */
	label: (scenarioName: string) => string;
	change: (draft: Project) => Project;
} {
	const own = (o: Override) =>
		o.kind === 'component' && o.componentId === column.id && o.field === 'status';
	return {
		caseId,
		label: (name) => `${LINEUP_TABLE_WORDS.reset(column.label)} in ${name}`,
		change: (draft) =>
			withScenarios(
				draft,
				scenariosOf(draft).map((s) =>
					s.id === caseId ? { ...s, overrides: overridesOf(s).filter((o) => !own(o)) } : s
				)
			)
	};
}

/**
 * The alert line when editScenario refuses a press (§8.6): "Could not turn Pump PA off in
 * Scenario 2: A scenario holds at most 30 changes.", from the refusal's own words (LIMIT_MESSAGE),
 * in ws.edit's "Could not {label}: " pattern; the scenario named as it is (nothing changed).
 */
export function refusalText(press: LineupPress, scenarioName: string, message: string): string {
	return LINEUP_TABLE_WORDS.couldNot(press.label, scenarioName, message);
}

// ---------------------------------------------------------------------------------------------
// §8.7 The active cell (decision 26)
// ---------------------------------------------------------------------------------------------

/**
 * The cell the user last wanted (page state of the panel, written only by the keys, a press and
 * New lineup): its case, its pump and the index its row had then (the base row is 0).
 */
export interface WantedCell {
	caseId: CaseId;
	pumpId: string;
	rowIndex: number;
}

/** The cell that holds the grid's one Tab stop: its row and column indexes, case and pump. */
export interface ActiveCell {
	row: number;
	column: number;
	caseId: CaseId;
	pumpId: string;
}

/**
 * The active cell (§8.7), derived and clamped to the table as it is: the wanted row while it
 * exists, else the nearest remaining row (the next, the row now in its place; then the previous),
 * else the base row; the wanted column while it is shown, else the first. With none wanted, the
 * first scenario's first pump, or the base row's when there is no scenario. Null only without a
 * column. A Tab stop thus never outlives its row or its column.
 */
export function activeCell(table: LineupTable, wanted: WantedCell | null): ActiveCell | null {
	const { rows, columns } = table;
	if (!columns.length || !rows.length) return null;
	let row: number;
	if (!wanted) row = rows.length > 1 ? 1 : 0;
	else {
		const at = rows.findIndex((r) => r.caseId === wanted.caseId);
		row = at !== -1 ? at : Math.max(0, Math.min(wanted.rowIndex, rows.length - 1));
	}
	const found = wanted ? columns.findIndex((c) => c.id === wanted.pumpId) : -1;
	const column = found === -1 ? 0 : found;
	return { row, column, caseId: rows[row]!.caseId, pumpId: columns[column]!.id };
}

// ---------------------------------------------------------------------------------------------
// §8.8 New lineup
// ---------------------------------------------------------------------------------------------

/**
 * New lineup (§8.8): `{ id: newScenarioId, name: newScenarioName, overrides: [] }`, its pumps the
 * base's, and `add`, which appends it to a draft of `project` (ws.updateStored(add,
 * NEW_LINEUP_LABEL): one undo step, the case shown unchanged); "Scenario n" is app-made, so its
 * first press renames it (§4.5). Null when the project is full (MAX_SCENARIOS): the button is
 * aria-disabled and a press does nothing.
 */
export function newLineup(project: Project): {
	id: string;
	name: string;
	/** The manager's status line after the add. */
	status: string;
	add: (draft: Project) => Project;
} | null {
	if (scenariosOf(project).length >= MAX_SCENARIOS) return null;
	const id = newScenarioId(project);
	const name = newScenarioName(project, id);
	return {
		id,
		name,
		status: LINEUP_TABLE_WORDS.added(name),
		add: (draft) => withScenarios(draft, [...scenariosOf(draft), { id, name, overrides: [] }])
	};
}

// ---------------------------------------------------------------------------------------------
// §8.9 Undo in the panel
// ---------------------------------------------------------------------------------------------

/**
 * What an undo or redo did, in words (§8.9): "Undid {label}." or "Redid {label}.", with " Now
 * showing {case words}." when the case shown changed (`nowShowing`, ws.caseWords of the case shown
 * after; null when it did not). With a case change these are the workspace notice's own words.
 */
export function historyText(
	step: 'undo' | 'redo',
	label: string,
	nowShowing: string | null
): string {
	const did = step === 'undo' ? LINEUP_TABLE_WORDS.undid(label) : LINEUP_TABLE_WORDS.redid(label);
	return nowShowing === null ? did : `${did}${LINEUP_TABLE_WORDS.nowShowing(nowShowing)}`;
}

// ---------------------------------------------------------------------------------------------
// §8.1 The manager's tabs (decision 26)
// ---------------------------------------------------------------------------------------------

export type ManagerTab = 'cases' | 'lineups';

/** The project has the Pump lineups tab: two pumps or more (§8.1). */
export function hasLineupsTab(project: Project): boolean {
	return project.components.filter((c) => c.type === 'pump').length >= 2;
}

/** The tab shown, derived (§8.1): the one last used while the project has two pumps, else Cases. */
export function shownManagerTab(project: Project, tab: ManagerTab): ManagerTab {
	return hasLineupsTab(project) ? tab : 'cases';
}

// ---------------------------------------------------------------------------------------------
// §8.10 Phone: one case at a time (decision 26)
// ---------------------------------------------------------------------------------------------

/**
 * The phone's picked case (§8.10), derived: the stored pick (undefined: none; null: the base case)
 * while that case exists, else the default: the case shown if it is a scenario, else the first
 * scenario, else the base case. An Undo that removes the picked scenario thus falls back.
 */
export function pickedCase(project: Project, shownCase: CaseId, pick: CaseId | undefined): CaseId {
	const scenarios = scenariosOf(project);
	const exists = (id: CaseId) => id === null || scenarios.some((s) => s.id === id);
	if (pick !== undefined && exists(pick)) return pick;
	if (shownCase !== null && exists(shownCase)) return shownCase;
	return scenarios[0]?.id ?? null;
}

/** An option of "Case to edit": its value ('' for the base case), its case and its words. */
export interface CaseOption {
	value: string;
	caseId: CaseId;
	text: string;
}

/** The value of the base case's option in "Case to edit" (a scenario's is its id). */
export const BASE_OPTION = '';

/**
 * "Case to edit"'s options (§8.10): "Base case", then each scenario as "{name} ({changes text})",
 * the Scenarios menu's format.
 */
export function pickerOptions(project: Project): CaseOption[] {
	return [
		{ value: BASE_OPTION, caseId: null, text: LINEUP_TABLE_WORDS.baseCase },
		...scenariosOf(project).map((s) => ({
			value: s.id,
			caseId: s.id,
			text: LINEUP_TABLE_WORDS.option(s.name, changesText(project, s))
		}))
	];
}

/**
 * The picked case's line (§8.10): a scenario's "Changes go to «{name}» only: {n} of at most 30
 * changes." (n its stored changes), then its notes (the table's row); the base case's "The base
 * case's pumps: change them in Build."
 */
export function pickedLine(table: LineupTable, caseId: CaseId): readonly string[] {
	if (caseId === null) return [LINEUP_TABLE_WORDS.baseLine];
	const row = table.rows.find((r) => r.caseId === caseId);
	if (!row) return [];
	return [LINEUP_TABLE_WORDS.scenarioLine(row.name, row.changes), ...row.notes];
}
