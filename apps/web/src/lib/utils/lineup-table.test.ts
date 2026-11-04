/**
 * The Pump lineups table's model (CLAUDE.md D24, proposal pump-lineups.md §8 and §10.2 "Unit"):
 * the columns (the frame cut to the filter, the group header row and its words), the cell states
 * (the base value, a case's own value, a change equal to the base still marked, a standby turned
 * on), the notes ("{n} other changes", "Same case as …"), the schema guard on the status values,
 * a press, the active cell and the phone's picked case (decision 26), New lineup, the undo words
 * and every string of §8.12, word for word. The projects are the shared fixture's `two-systems`
 * (__fixtures__/pump-groups-input.json: the API's own project and its answers for each case), the
 * examples' and made-up test inputs (testing/lineups.ts).
 */
import { describe, expect, it } from 'vitest';
import type { Override, Project, Scenario, SolveResponse } from '$lib/api/types';
import { series, station, twoByTwo } from '$lib/testing/lineups';
import fixture from './__fixtures__/pump-groups-input.json';
import { condenserWaterExample } from './examples';
import { entryFor } from './field-registry';
import { PUMP_STATUS_LABELS } from './labels';
import {
	activeCell,
	BASE_OPTION,
	cellPress,
	groupHeader,
	hasLineupsTab,
	historyText,
	LINEUP_TABLE_WORDS,
	lineupPress,
	lineupReset,
	lineupTable,
	NEW_LINEUP_LABEL,
	newLineup,
	pickedCase,
	pickedLine,
	pickerOptions,
	refusalText,
	shownManagerTab,
	statusChoices,
	statusWord,
	type LineupTable,
	type LineupTableInput
} from './lineup-table';
import { schemaChoices } from './model-rules';
import { lineupName, sameCase } from './pump-lineups';
import { LIMIT_MESSAGE, MAX_SCENARIOS, scenariosOf, withScenarios, type CaseId } from './scenarios';

interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse;
	scenarioCases: Record<string, { solve: SolveResponse }>;
}
/** `two-systems`: PA and PB (PB off in the base, a standby), the P1–P3 ladder, a lone P9. */
const two = (fixture.cases as unknown as FixtureCase[]).find((c) => c.name === 'two-systems')!;
const twoProject = () => structuredClone(two.project);

const status = (componentId: string, value: 'on' | 'off'): Override => ({
	kind: 'component',
	componentId,
	field: 'status',
	value
});
const level = (componentId: string, value: number): Override => ({
	kind: 'component',
	componentId,
	field: 'liquidLevel',
	value
});
const scenario = (id: string, name: string, overrides: Override[]): Scenario => ({
	id,
	name,
	overrides
});
/** `two-systems` with these scenarios after its own. */
const withMore = (...more: Scenario[]) =>
	withScenarios(twoProject(), [...scenariosOf(twoProject()), ...more]);

const table = (project: Project, values: Partial<Omit<LineupTableInput, 'project'>> = {}) =>
	lineupTable({ project, shownCase: null, filter: null, ...values });
/** A row by its case. */
const row = (t: LineupTable, caseId: CaseId) => t.rows.find((r) => r.caseId === caseId)!;
/** A row's cell by pump. */
const cell = (t: LineupTable, caseId: CaseId, pumpId: string) =>
	row(t, caseId).cells.find((c) => c.pumpId === pumpId)!;
/** Each row's cells as "id value" with "*" for a marked cell. */
const grid = (t: LineupTable) =>
	t.rows.map((r) => r.cells.map((c) => `${c.pumpId} ${c.value}${c.marked ? '*' : ''}`).join(' '));

// ---------------------------------------------------------------------------------------------
// The fixture's own scenarios
// ---------------------------------------------------------------------------------------------

describe('the two-systems fixture', () => {
	it('holds the scenarios §10.2 lists, the crossed lineup named as the app names it', () => {
		const scenarios = scenariosOf(two.project);
		expect(scenarios.map((s) => [s.id, s.name])).toEqual([
			['S1', 'PB in service, PA off'],
			['S2', '2 of 2 running; 2 of 3 running (Pump P3 off)'],
			['S3', 'Aged pipe']
		]);
		expect(lineupName(two.project, scenarios[1]!)).toBe(scenarios[1]!.name);
		// A name the user typed is not the app's (§4.5): S1's lineup name differs.
		expect(lineupName(two.project, scenarios[0]!)).toBe('1 of 2 running (Pump PA off)');
		expect(lineupName(two.project, scenarios[2]!)).toBe(
			'2 of 3 running (Pump P2 off) + 1 other change'
		);
	});
});

// ---------------------------------------------------------------------------------------------
// §8.3 Columns
// ---------------------------------------------------------------------------------------------

describe('columns (§8.3)', () => {
	it('two-systems gives [PA, PB], [P1, P2, P3] and Other [P9], with the group row', () => {
		const t = table(twoProject());
		expect(t.groups).toEqual([
			{ kind: 'parallel', pumpIds: ['PA', 'PB'], header: 'Pumps together, PA and PB' },
			{ kind: 'parallel', pumpIds: ['P1', 'P2', 'P3'], header: 'Pumps together, P1 to P3' },
			{ kind: 'other', pumpIds: ['P9'], header: 'Other pumps' }
		]);
		expect(t.groupRow).toBe(true);
		expect(t.columns).toEqual([
			{ id: 'PA', label: 'Pump PA', group: 0, first: true },
			{ id: 'PB', label: 'Pump PB', group: 0, first: false },
			{ id: 'P1', label: 'Pump P1', group: 1, first: true },
			{ id: 'P2', label: 'Pump P2', group: 1, first: false },
			{ id: 'P3', label: 'Pump P3', group: 1, first: false },
			{ id: 'P9', label: 'Pump P9', group: 2, first: true }
		]);
		expect(t.filter).toBeNull();
		expect(t.filterText).toBeNull();
		expect(t.series).toBe(false);
	});

	it('shows the group header row only with two or more groups', () => {
		const one = table(station(3));
		expect(one.groups).toEqual([
			{ kind: 'parallel', pumpIds: ['P1', 'P2', 'P3'], header: 'Pumps together, P1 to P3' }
		]);
		expect(one.groupRow).toBe(false);
		expect(table(twoProject()).groupRow).toBe(true);
		// Filtered to one station: one group, no group row.
		expect(table(twoProject(), { filter: ['PA', 'PB'] }).groupRow).toBe(false);
	});

	it('cuts the groups to the filter, drops empty groups and says so', () => {
		const t = table(twoProject(), { filter: ['P3', 'PB', 'P2'] });
		expect(t.groups).toEqual([
			{ kind: 'parallel', pumpIds: ['PB'], header: 'Pumps together, PB' },
			{ kind: 'parallel', pumpIds: ['P2', 'P3'], header: 'Pumps together, P2 and P3' }
		]);
		expect(t.columns.map((c) => c.id)).toEqual(['PB', 'P2', 'P3']);
		expect(t.groupRow).toBe(true);
		expect(t.filter).toEqual(['PB', 'P2', 'P3']);
		expect(t.filterText).toBe(
			'Only the pumps on the Pumps together card are shown: Pump PB, Pump P2 and Pump P3.'
		);
		// Every cell row follows the columns.
		expect(t.rows.every((r) => r.cells.map((c) => c.pumpId).join() === 'PB,P2,P3')).toBe(true);
	});

	it('keeps only the filter’s pumps that exist, and shows every pump when none does', () => {
		const t = table(twoProject(), { filter: ['P7', 'P1', 'P2'] });
		expect(t.columns.map((c) => c.id)).toEqual(['P1', 'P2']);
		expect(t.filterText).toBe(
			'Only the pumps on the Pumps together card are shown: Pump P1 and Pump P2.'
		);
		const gone = table(twoProject(), { filter: ['P7', 'P8'] });
		expect(gone.columns.map((c) => c.id)).toEqual(['PA', 'PB', 'P1', 'P2', 'P3', 'P9']);
		expect(gone.filter).toBeNull();
		expect(gone.filterText).toBeNull();
	});

	it('words each kind of group by its first and last columns, by id', () => {
		expect(groupHeader('parallel', ['P1', 'P2', 'P3', 'P4'])).toBe('Pumps together, P1 to P4');
		expect(groupHeader('parallel', ['PA', 'PB'])).toBe('Pumps together, PA and PB');
		expect(groupHeader('series', ['PA', 'PB'])).toBe('Pumps together, in series, PA and PB');
		expect(groupHeader('mixed', ['A1', 'A2', 'B1', 'B2'])).toBe(
			'Pumps together, some in series, A1 to B2'
		);
		expect(groupHeader('other', ['P9'])).toBe('Other pumps');
		const pair = table(series());
		expect(pair.groups).toEqual([
			{ kind: 'series', pumpIds: ['PA', 'PB'], header: 'Pumps together, in series, PA and PB' }
		]);
		expect(pair.series).toBe(true);
		const mixed = table(twoByTwo());
		expect(mixed.groups).toEqual([
			{
				kind: 'mixed',
				pumpIds: ['A1', 'A2', 'B1', 'B2'],
				header: 'Pumps together, some in series, A1 to B2'
			}
		]);
		expect(mixed.series).toBe(true);
	});

	it('labels pumps project-wide: "Name (id)" where another pump has the name', () => {
		const p = station(3, { names: ['Duty pump', 'Standby', 'Standby'] });
		expect(table(p).columns.map((c) => [c.id, c.label])).toEqual([
			['P1', 'Duty pump'],
			['P2', 'Standby (P2)'],
			['P3', 'Standby (P3)']
		]);
	});

	it('keeps the condenser example’s six columns; its winter case’s statuses are marked Off', () => {
		const t = table(condenserWaterExample());
		expect(t.columns.map((c) => c.id)).toEqual(['P1', 'P2', 'P3', 'P4', 'P5', 'P6']);
		expect(t.groupRow).toBe(false);
		expect(t.rows.map((r) => r.name)).toEqual(['Base case', 'Winter: tower bypassed']);
		expect(grid(t)[1]).toBe('P1 on P2 off* P3 off* P4 off* P5 off* P6 off*');
		expect(row(t, 'S1').notes).toEqual(['14 other changes']);
	});
});

// ---------------------------------------------------------------------------------------------
// §8.4, §8.5 Rows and cells
// ---------------------------------------------------------------------------------------------

describe('rows and cells (§8.4, §8.5)', () => {
	it('gives the base row first, read as the base case, then each scenario in order', () => {
		const t = table(twoProject(), { shownCase: 'S2' });
		expect(t.rows.map((r) => [r.caseId, r.name, r.id, r.shown, r.changes])).toEqual([
			[null, 'Base case', null, false, 0],
			['S1', 'PB in service, PA off', 'S1', false, 2],
			['S2', '2 of 2 running; 2 of 3 running (Pump P3 off)', 'S2', true, 2],
			['S3', 'Aged pipe', 'S3', false, 2]
		]);
		expect(row(t, null).notes).toEqual(['Set in Build']);
		expect(grid(t)).toEqual([
			'PA on PB off P1 on P2 on P3 on P9 on',
			'PA off* PB on* P1 on P2 on P3 on P9 on',
			'PA on PB on* P1 on P2 on P3 off* P9 on',
			'PA on PB off P1 on P2 off* P3 on P9 on'
		]);
		// The base case shown: no row is "Shown" (the badge is a scenario's, §8.4).
		expect(table(twoProject()).rows.some((r) => r.shown)).toBe(false);
	});

	it('the base value: the base row and a case that leaves the pump alone', () => {
		const t = table(twoProject());
		expect(cell(t, null, 'PB')).toEqual({
			pumpId: 'PB',
			value: 'off',
			base: 'off',
			state: 'base',
			marked: false,
			standbyOn: false,
			word: 'Off',
			description: null
		});
		expect(cell(t, 'S3', 'PA')).toEqual({
			pumpId: 'PA',
			value: 'on',
			base: 'on',
			state: 'base',
			marked: false,
			standbyOn: false,
			word: 'On',
			description: null
		});
	});

	it('a case’s own value: marked, described with the base value', () => {
		expect(cell(table(twoProject()), 'S1', 'PA')).toEqual({
			pumpId: 'PA',
			value: 'off',
			base: 'on',
			state: 'changed',
			marked: true,
			standbyOn: false,
			word: 'Off',
			description: 'Changed in this scenario. Base value On.'
		});
	});

	it('a change equal to the base value is still the case’s own, marked', () => {
		const t = table(withMore(scenario('S4', 'PA kept on', [status('PA', 'on')])));
		expect(cell(t, 'S4', 'PA')).toEqual({
			pumpId: 'PA',
			value: 'on',
			base: 'on',
			state: 'same',
			marked: true,
			standbyOn: false,
			word: 'On',
			description: 'Changed in this scenario. Base value On.'
		});
		expect(row(t, 'S4').notes).toEqual(['Same case as the base case']);
	});

	it('a standby turned on: On, marked, described "Base value Off."', () => {
		expect(cell(table(twoProject()), 'S1', 'PB')).toEqual({
			pumpId: 'PB',
			value: 'on',
			base: 'off',
			state: 'changed',
			marked: true,
			standbyOn: true,
			word: 'On',
			description: 'Changed in this scenario. Base value Off.'
		});
	});

	it('says what the API applied: each marked cell is a status change the server applied', () => {
		const t = table(twoProject());
		for (const [id, { solve }] of Object.entries(two.scenarioCases)) {
			const applied = solve
				.scenario!.overrides.filter((o) => o.state === 'applied' && o.override.field === 'status')
				.map((o) => {
					const target = o.override as Extract<Override, { kind: 'component' }>;
					return [target.componentId, o.value, o.baseValue];
				})
				.sort();
			const marked = row(t, id)
				.cells.filter((c) => c.marked)
				.map((c) => [c.pumpId, c.value, c.base])
				.sort();
			expect(marked, id).toEqual(applied);
			// And each cell's value is the pump's state in that case's solve: off, or not off.
			const pumps = solve.solvedState.pumpResults;
			for (const c of row(t, id).cells) {
				expect(pumps[c.pumpId]!.status === 'off', `${id} ${c.pumpId}`).toBe(c.value === 'off');
			}
		}
		const base = two.solve.solvedState.pumpResults;
		for (const c of row(t, null).cells) {
			expect(base[c.pumpId]!.status === 'off', c.pumpId).toBe(c.value === 'off');
		}
	});
});

// ---------------------------------------------------------------------------------------------
// §8.4 Notes
// ---------------------------------------------------------------------------------------------

describe('notes (§8.4)', () => {
	it('"{n} other changes" counts what is stored besides the statuses of the pumps shown', () => {
		const t = table(twoProject());
		expect(row(t, 'S1').notes).toEqual([]);
		expect(row(t, 'S2').notes).toEqual([]);
		// The aged pipe: one other change.
		expect(row(t, 'S3').notes).toEqual(['1 other change']);
	});

	it('counts the statuses of pumps the filter hides', () => {
		const t = table(twoProject(), { filter: ['PA', 'PB'] });
		expect(row(t, 'S1').notes).toEqual([]);
		// P3's status, hidden.
		expect(row(t, 'S2').notes).toEqual(['1 other change']);
		// The pipe and P2's status, hidden.
		expect(row(t, 'S3').notes).toEqual(['2 other changes']);
	});

	it('counts changes that no longer apply, where a name counts only effective ones', () => {
		const gone = status('P7', 'off');
		const lapsed = scenario('S4', 'With a lapsed change', [status('P1', 'off'), gone]);
		const p = withMore(lapsed);
		expect(row(table(p), 'S4').notes).toEqual(['1 other change']);
		// The name counts none: the change changes nothing (§4.4).
		expect(lineupName(p, lapsed)).toBe('2 of 3 running (Pump P1 off)');
		const both = scenario('S4', 'Lapsed and a level', [status('P1', 'off'), gone, level('R4', 3)]);
		expect(row(table(withMore(both)), 'S4').notes).toEqual(['2 other changes']);
	});

	it('"Same case as …" names the first earlier row with the same effective changes', () => {
		const two1 = scenariosOf(twoProject());
		const p = withMore(
			// A copy of S1 and S2's changes reversed: the same cases.
			scenario('S4', 'PB in service, PA off (copy)', two1[0]!.overrides!),
			scenario('S5', 'Reversed', [status('P3', 'off'), status('PB', 'on')]),
			// A fresh New lineup, and a case whose only change equals the base value.
			scenario('S6', 'Scenario 6', []),
			scenario('S7', 'Kept', [status('P9', 'on')]),
			// A second copy of S1: the first earlier row is still S1.
			scenario('S8', 'Again', [status('PA', 'off'), status('PB', 'on')])
		);
		const t = table(p);
		expect(t.rows.map((r) => r.notes)).toEqual([
			['Set in Build'],
			[],
			[],
			['1 other change'],
			['Same case as «PB in service, PA off» (S1)'],
			['Same case as «2 of 2 running; 2 of 3 running (Pump P3 off)» (S2)'],
			['Same case as the base case'],
			['Same case as the base case'],
			['Same case as «PB in service, PA off» (S1)']
		]);
	});

	it('agrees with sameCase on every pair of rows', () => {
		const p = withMore(
			scenario('S4', 'Copy', [status('PB', 'on'), status('PA', 'off')]),
			scenario('S5', 'Empty', []),
			scenario('S6', 'Level', [level('R4', 3)]),
			scenario('S7', 'Level again', [level('R4', 3), status('P2', 'on')])
		);
		const cases = [undefined, ...scenariosOf(p)];
		const t = table(p);
		cases.forEach((s, i) => {
			if (!s) return;
			const first = cases.findIndex((e, j) => j < i && sameCase(p, e, s));
			const note = t.rows[i]!.notes.find((n) => n.startsWith('Same case as'));
			if (first === -1) expect(note, s.id).toBeUndefined();
			else if (first === 0) expect(note, s.id).toBe('Same case as the base case');
			else expect(note, s.id).toBe(`Same case as «${cases[first]!.name}» (${cases[first]!.id})`);
		});
		expect(row(t, 'S7').notes).toEqual(['1 other change', 'Same case as «Level» (S6)']);
	});
});

// ---------------------------------------------------------------------------------------------
// §8.5 The schema guard and the state words
// ---------------------------------------------------------------------------------------------

describe('the status values (§8.5)', () => {
	it('are exactly the schema’s on and off, labelled On and Off by the registry', () => {
		expect(schemaChoices('Pump', 'status')).toEqual(['on', 'off']);
		const input = entryFor('Pump', 'status')?.input;
		expect(input).toEqual({ kind: 'choice', labels: PUMP_STATUS_LABELS });
		expect(PUMP_STATUS_LABELS).toEqual({ on: 'On', off: 'Off' });
		expect(statusChoices()).toEqual([
			{ value: 'on', label: 'On' },
			{ value: 'off', label: 'Off' }
		]);
		expect([statusWord('on'), statusWord('off')]).toEqual(['On', 'Off']);
	});

	it('names a switch by its headers, never by its state word', () => {
		const t = table(twoProject());
		for (const r of t.rows) {
			for (const [i, c] of r.cells.entries()) {
				const name = LINEUP_TABLE_WORDS.cellName(t.columns[i]!.label, r.name);
				expect(name).not.toMatch(/\b(On|Off)\b/);
				expect(c.word).toMatch(/^(On|Off)$/);
			}
		}
		expect(LINEUP_TABLE_WORDS.cellName('Pump PA', 'Scenario 2')).toBe('Pump PA Scenario 2');
	});
});

// ---------------------------------------------------------------------------------------------
// §8.6 A press
// ---------------------------------------------------------------------------------------------

describe('a press (§8.6)', () => {
	it('writes the other value with the undo label "turn {pump label} {on|off}"', () => {
		const t = table(twoProject());
		const [pa, pb] = t.columns;
		const off = cellPress(pa!, cell(t, 'S2', 'PA'));
		expect([off.pumpId, off.next, off.label]).toEqual(['PA', 'off', 'turn Pump PA off']);
		const on = cellPress(pb!, cell(t, null, 'PB'));
		expect([on.next, on.label]).toEqual(['on', 'turn Pump PB on']);
		// The phone's Reset: the base value.
		expect(lineupPress(pb!, cell(t, 'S1', 'PB').base).label).toBe('turn Pump PB off');
	});

	it('sets only that pump’s status, as Build’s Status segment does', () => {
		const p = twoProject();
		const after = cellPress(table(p).columns[1]!, cell(table(p), null, 'PB')).change(
			structuredClone(p)
		);
		expect(after.components.find((c) => c.id === 'PB')).toEqual({
			...p.components.find((c) => c.id === 'PB'),
			status: 'on'
		});
		expect(after.components.filter((c) => c.id !== 'PB')).toEqual(
			p.components.filter((c) => c.id !== 'PB')
		);
	});

	it('the phone’s Reset of a change equal to the base value removes that change only', () => {
		// PB on in the base: S1's own "PB on" now equals it (state 'same').
		const p = twoProject();
		const pb = p.components.find((c) => c.id === 'PB') as Project['components'][number] & {
			status: string;
		};
		pb.status = 'on';
		const t = table(p);
		expect(cell(t, 'S1', 'PB').state).toBe('same');
		const reset = lineupReset('S1', t.columns[1]!);
		expect(reset.caseId).toBe('S1');
		expect(reset.label('PB in service, PA off')).toBe('reset Pump PB in PB in service, PA off');
		const after = reset.change(structuredClone(p));
		expect(scenariosOf(after).map((s) => s.overrides)).toEqual([
			[status('PA', 'off')],
			scenariosOf(p)[1]!.overrides,
			scenariosOf(p)[2]!.overrides
		]);
		expect(after.components).toEqual(p.components);
		expect(cell(table(after), 'S1', 'PB')).toMatchObject({ state: 'base', marked: false });
	});

	it('words a refusal in ws.edit’s pattern with the scenario’s name', () => {
		const t = table(twoProject());
		const press = cellPress(t.columns[0]!, cell(t, 'S3', 'PA'));
		expect(refusalText(press, 'Aged pipe', LIMIT_MESSAGE)).toBe(
			'Could not turn Pump PA off in Aged pipe: A scenario holds at most 30 changes.'
		);
	});
});

// ---------------------------------------------------------------------------------------------
// §8.7 The active cell
// ---------------------------------------------------------------------------------------------

describe('the active cell (§8.7, decision 26)', () => {
	const t = table(twoProject());
	const at = (wanted: Parameters<typeof activeCell>[1], tab = t) => activeCell(tab, wanted);

	it('is the first scenario’s first pump with none wanted, or the base row’s', () => {
		expect(at(null)).toEqual({ row: 1, column: 0, caseId: 'S1', pumpId: 'PA' });
		const bare = table(withScenarios(twoProject(), []));
		expect(at(null, bare)).toEqual({ row: 0, column: 0, caseId: null, pumpId: 'PA' });
	});

	it('is the wanted cell while its row and column exist', () => {
		expect(at({ caseId: 'S2', pumpId: 'P3', rowIndex: 2 })).toEqual({
			row: 2,
			column: 4,
			caseId: 'S2',
			pumpId: 'P3'
		});
		expect(at({ caseId: null, pumpId: 'P9', rowIndex: 0 })).toEqual({
			row: 0,
			column: 5,
			caseId: null,
			pumpId: 'P9'
		});
		// A row moved since: found by its case.
		expect(at({ caseId: 'S3', pumpId: 'PB', rowIndex: 1 })?.row).toBe(3);
	});

	it('moves to the next row when its row is gone, else the previous, else the base row', () => {
		const without = (id: string) =>
			table(
				withScenarios(
					twoProject(),
					scenariosOf(twoProject()).filter((s) => s.id !== id)
				)
			);
		// S2 removed: the next row (S3) took its place.
		expect(at({ caseId: 'S2', pumpId: 'P1', rowIndex: 2 }, without('S2'))).toEqual({
			row: 2,
			column: 2,
			caseId: 'S3',
			pumpId: 'P1'
		});
		// The last row removed (an undone New lineup): the previous.
		expect(at({ caseId: 'S3', pumpId: 'P1', rowIndex: 3 }, without('S3'))?.caseId).toBe('S2');
		// Every scenario gone: the base row.
		const bare = table(withScenarios(twoProject(), []));
		expect(at({ caseId: 'S2', pumpId: 'P2', rowIndex: 2 }, bare)).toEqual({
			row: 0,
			column: 3,
			caseId: null,
			pumpId: 'P2'
		});
	});

	it('moves to the first column when its column is not shown', () => {
		const filtered = table(twoProject(), { filter: ['P1', 'P2', 'P3'] });
		expect(at({ caseId: 'S1', pumpId: 'PB', rowIndex: 1 }, filtered)).toEqual({
			row: 1,
			column: 0,
			caseId: 'S1',
			pumpId: 'P1'
		});
	});

	it('is null without a column', () => {
		const empty = table(withScenarios(series(), []), {});
		expect(empty.columns).toHaveLength(2);
		const none = lineupTable({
			project: { ...series(), components: series().components.filter((c) => c.type !== 'pump') },
			shownCase: null,
			filter: null
		});
		expect(none.columns).toEqual([]);
		expect(activeCell(none, null)).toBeNull();
	});
});

// ---------------------------------------------------------------------------------------------
// §8.8 New lineup, §8.9 Undo, §8.1 the tabs
// ---------------------------------------------------------------------------------------------

describe('New lineup (§8.8)', () => {
	it('appends "Scenario n" with no changes, its pumps the base’s, and says so', () => {
		const added = newLineup(twoProject())!;
		const project = added.add(twoProject());
		expect([added.id, added.name, added.status]).toEqual([
			'S4',
			'Scenario 4',
			'Added «Scenario 4», its pumps as in the base case.'
		]);
		expect(scenariosOf(project).at(-1)).toEqual({
			id: 'S4',
			name: 'Scenario 4',
			overrides: []
		});
		expect(scenariosOf(project).slice(0, 3)).toEqual(scenariosOf(twoProject()));
		const t = table(project);
		expect(grid(t).at(-1)).toBe(grid(t)[0]);
		expect(row(t, 'S4').notes).toEqual(['Same case as the base case']);
		expect(NEW_LINEUP_LABEL).toBe('add scenario');
	});

	it('adds nothing when the project holds the most scenarios', () => {
		const full = withScenarios(
			twoProject(),
			Array.from({ length: MAX_SCENARIOS }, (_, i) => scenario(`S${i + 1}`, `Case ${i + 1}`, []))
		);
		expect(newLineup(full)).toBeNull();
		expect(LINEUP_TABLE_WORDS.full).toBe('A project holds at most 20 scenarios.');
	});
});

describe('undo words (§8.9) and the tabs (§8.1)', () => {
	it('says what an undo or redo did, and the case shown after when it changed', () => {
		expect(historyText('undo', 'turn Pump PA off in Aged pipe', null)).toBe(
			'Undid turn Pump PA off in Aged pipe.'
		);
		expect(historyText('redo', 'add scenario', null)).toBe('Redid add scenario.');
		expect(historyText('undo', 'change pump status in Night', 'scenario Night')).toBe(
			'Undid change pump status in Night. Now showing scenario Night.'
		);
		expect(historyText('redo', 'change pump status', 'the base case')).toBe(
			'Redid change pump status. Now showing the base case.'
		);
	});

	it('shows Pump lineups only with two pumps or more', () => {
		expect(hasLineupsTab(twoProject())).toBe(true);
		const one = {
			...series(),
			components: series().components.filter((c) => c.id !== 'PB')
		};
		expect(hasLineupsTab(one)).toBe(false);
		expect(shownManagerTab(one, 'lineups')).toBe('cases');
		expect(shownManagerTab(twoProject(), 'lineups')).toBe('lineups');
		expect(shownManagerTab(twoProject(), 'cases')).toBe('cases');
	});
});

// ---------------------------------------------------------------------------------------------
// §8.10 Phone
// ---------------------------------------------------------------------------------------------

describe('the phone’s case (§8.10, decision 26)', () => {
	it('is the stored pick while it exists, else the case shown, the first scenario, the base', () => {
		const p = twoProject();
		expect(pickedCase(p, null, 'S2')).toBe('S2');
		expect(pickedCase(p, 'S2', null)).toBeNull();
		// No pick: the case shown if a scenario, else the first scenario.
		expect(pickedCase(p, 'S3', undefined)).toBe('S3');
		expect(pickedCase(p, null, undefined)).toBe('S1');
		// The pick removed (an Undo): the default.
		expect(pickedCase(p, 'S3', 'S9')).toBe('S3');
		expect(pickedCase(p, null, 'S9')).toBe('S1');
		expect(pickedCase(withScenarios(p, []), null, 'S1')).toBeNull();
	});

	it('offers "Base case", then each scenario in the menu’s format', () => {
		const p = withMore(scenario('S4', 'Lapsed', [status('P7', 'off')]));
		expect(pickerOptions(p)).toEqual([
			{ value: BASE_OPTION, caseId: null, text: 'Base case' },
			{ value: 'S1', caseId: 'S1', text: 'PB in service, PA off (2 changes)' },
			{
				value: 'S2',
				caseId: 'S2',
				text: '2 of 2 running; 2 of 3 running (Pump P3 off) (2 changes)'
			},
			{ value: 'S3', caseId: 'S3', text: 'Aged pipe (2 changes)' },
			{ value: 'S4', caseId: 'S4', text: 'Lapsed (1 change, 1 no longer applies)' }
		]);
		expect(BASE_OPTION).toBe('');
	});

	it('says where changes go, then the row’s notes; the base case’s line', () => {
		const t = table(withMore(scenario('S4', 'Scenario 4', [])));
		expect(pickedLine(t, 'S3')).toEqual([
			'Changes go to «Aged pipe» only: 2 of at most 30 changes.',
			'1 other change'
		]);
		expect(pickedLine(t, 'S4')).toEqual([
			'Changes go to «Scenario 4» only: 0 of at most 30 changes.',
			'Same case as the base case'
		]);
		expect(pickedLine(t, null)).toEqual(["The base case's pumps: change them in Build."]);
		expect(LINEUP_TABLE_WORDS.baseItem('Pump PB', statusWord('off'))).toBe('Pump PB: Off');
	});
});

// ---------------------------------------------------------------------------------------------
// §8.12 Every new UI string
// ---------------------------------------------------------------------------------------------

describe('every string of §8.12, word for word', () => {
	const w = LINEUP_TABLE_WORDS;

	it('tabs, table, intros and lines', () => {
		expect(w.casesTab(3)).toBe('Cases (3)');
		expect(w.lineupsTab).toBe('Pump lineups');
		expect(w.tablist).toBe('Scenarios view');
		expect(w.caption).toBe('Pumps on or off in each case');
		expect(`${w.intro} {mark} ${w.introMark}`).toBe(
			"Each case's pumps, on or off; in a name, running means switched on. Pressing a cell turns that pump on or off in that case only, the same change as in Build, one undo step each; the base case is changed in Build. {mark} A corner mark is the case's own value; unmarked cells follow the base case."
		);
		expect(w.phoneIntro).toBe(
			'Pick a case, then turn its pumps on or off: the same change as in Build, one undo step each; in a name, running means switched on. The base case is changed in Build.'
		);
		expect(w.filter(['A', 'B', 'C'])).toBe(
			'Only the pumps on the Pumps together card are shown: A, B and C.'
		);
		expect(w.showEvery).toBe('Show every pump');
		expect(w.series).toBe(
			'Pumps in series: one off stops the flow through their line (an off pump passes no flow).'
		);
		expect(w.full).toBe('A project holds at most 20 scenarios.');
	});

	it('headers, rows and cells', () => {
		expect(w.parallel('A and B')).toBe('Pumps together, A and B');
		expect(w.parallel('P1 to P3')).toBe('Pumps together, P1 to P3');
		expect(w.inSeries('PA and PB')).toBe('Pumps together, in series, PA and PB');
		expect(w.someInSeries('A1 to B2')).toBe('Pumps together, some in series, A1 to B2');
		expect([w.otherPumps, w.caseHeader]).toEqual(['Other pumps', 'Case']);
		expect([w.baseCase, w.setInBuild, w.shown]).toEqual(['Base case', 'Set in Build', 'Shown']);
		expect([w.otherChanges(1), w.otherChanges(14)]).toEqual(['1 other change', '14 other changes']);
		expect(w.sameCase({ name: 'Night', id: 'S2' })).toBe('Same case as «Night» (S2)');
		expect(w.sameCase(null)).toBe('Same case as the base case');
		expect(w.changed('Off')).toBe('Changed in this scenario. Base value Off.');
	});

	it('the footer, the status and alert lines, the undo label', () => {
		expect([w.undo, w.undoNamed('add scenario'), w.redo, w.redoNamed('add scenario')]).toEqual([
			'Undo',
			'Undo add scenario',
			'Redo',
			'Redo add scenario'
		]);
		expect([w.newLineup, w.done]).toEqual(['New lineup', 'Done']);
		expect(w.added('Scenario 2')).toBe('Added «Scenario 2», its pumps as in the base case.');
		expect(w.undid('x')).toBe('Undid x.');
		expect(w.redid('x')).toBe('Redid x.');
		expect(w.nowShowing('the base case')).toBe(' Now showing the base case.');
		expect(w.couldNot('turn Pump PA on', 'Night', LIMIT_MESSAGE)).toBe(
			'Could not turn Pump PA on in Night: A scenario holds at most 30 changes.'
		);
		expect([w.turn('Pump PA', 'on'), w.turn('Pump PA', 'off')]).toEqual([
			'turn Pump PA on',
			'turn Pump PA off'
		]);
		expect(w.reset('Pump PA')).toBe('reset Pump PA');
	});

	it('the phone and the card', () => {
		expect(w.caseToEdit).toBe('Case to edit');
		expect(w.option('Night', '3 changes')).toBe('Night (3 changes)');
		expect(w.scenarioLine('Night', 3)).toBe('Changes go to «Night» only: 3 of at most 30 changes.');
		expect(w.baseLine).toBe("The base case's pumps: change them in Build.");
		expect(w.baseItem('Pump PA', 'On')).toBe('Pump PA: On');
		expect(w.cardButton).toBe('Pump lineups table…');
	});
});
