/**
 * The Pump lineups table in the workspace (CLAUDE.md D24, proposal pump-lineups.md §8.6 to §8.9,
 * §10.2 "Workspace"): a press is Build's own edit (two workspaces, one pressing the table through
 * ws.editScenario as the panel does, one by setCase and Build's Status segment, give the same
 * project and the same link, also where an app-made name follows); a press back to the base value
 * removes the change; one undo step per press, labelled with the case's name after the step, and
 * Undo never switches case for it; the 31st change is refused with the table's exact words and
 * nothing changes; a press makes only its case out of date, Undo makes it current again, and a
 * round trip without Undo leaves it out of date (the documented cost, §6); the manager's tab and
 * filter are page state, reset on load. The projects are made-up test inputs (testing/lineups.ts)
 * and the shared fixture's `two-systems`; the solver is a fake that answers at once.
 */
import { describe, expect, it, vi } from 'vitest';
import type { Override, Project, Scenario, SolveResponse } from '../api/types';
import { station, stations } from '../testing/lineups';
import { testWorkspace } from '../testing/workspace';
import fixture from '../utils/__fixtures__/pump-groups-input.json';
import { encodeProject } from '../utils/encoding';
import { canonicalJson } from '../utils/json';
import {
	cellPress,
	lineupTable,
	NEW_LINEUP_LABEL,
	newLineup,
	refusalText
} from '../utils/lineup-table';
import { LIMIT_MESSAGE, MAX_CHANGES, scenariosOf, withScenarios } from '../utils/scenarios';
import type { Solver } from './project.svelte';
import type { Workspace } from './workspace.svelte';

/** A fixed clock: two workspaces stamp the same metadata.modified. */
const NOW = () => '2026-11-04T10:00:00.000Z';

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
const named = (id: string, name: string, overrides: Override[]): Scenario => ({
	id,
	name,
	overrides
});
const names = (ws: Workspace) => ws.scenarios.map((s) => s.name);
const overrides = (ws: Workspace, id: string) =>
	ws.scenarios.find((s) => s.id === id)?.overrides ?? [];

/** P1 to P4, Q1 and Q2, PA and PB (PB off in the base: a standby), each station of its own. */
const threeStations = (scenarios: Scenario[]) =>
	withScenarios(
		stations(
			{ ids: ['P1', 'P2', 'P3', 'P4'] },
			{ ids: ['Q1', 'Q2'] },
			{ ids: ['PA', 'PB'], off: ['PB'] }
		),
		scenarios
	);

/** A press of `pumpId` in scenario `scenarioId`, as the panel makes it (§8.6). */
function press(ws: Workspace, scenarioId: string, pumpId: string) {
	const table = lineupTable({
		project: ws.store.project,
		shownCase: ws.store.activeCase,
		filter: ws.managerPumps
	});
	const column = table.columns.find((c) => c.id === pumpId)!;
	const row = table.rows.find((r) => r.caseId === scenarioId)!;
	const p = cellPress(
		column,
		row.cells.find((c) => c.pumpId === pumpId)!
	);
	return { press: p, result: ws.editScenario(scenarioId, p.change, p.label, { quiet: true }) };
}

/** Build's Status segment in the case shown: RegistryField's edit (field-registry's label). */
const setStatus = (ws: Workspace, id: string, value: string) =>
	ws.editComponent(id, 'change pump status', (c) => {
		(c as unknown as Record<string, unknown>).status = value;
	});

/** The pump's status in the case shown, as Build's form shows it. */
function shownStatus(ws: Workspace, id: string): 'on' | 'off' {
	const pump = ws.project.components.find((c) => c.id === id);
	return pump?.type === 'pump' && pump.status === 'off' ? 'off' : 'on';
}

describe('a press is Build’s own edit (§8.6 item 1)', () => {
	const SEQUENCE = ['P3', 'P1', 'Q2', 'P3', 'PB'];

	/** The sequence through the table in one workspace, through Build in another. */
	function both(project: Project, scenarioId: string) {
		const table = testWorkspace(project, { now: NOW });
		const build = testWorkspace(project, { now: NOW });
		build.setCase(scenarioId);
		const steps = SEQUENCE.map((pumpId) => {
			const { result } = press(table, scenarioId, pumpId);
			expect(result.ok, pumpId).toBe(true);
			build.dismissNotice();
			expect(setStatus(build, pumpId, shownStatus(build, pumpId) === 'on' ? 'off' : 'on')).toBe(
				true
			);
			expect(canonicalJson(table.store.project), pumpId).toBe(canonicalJson(build.store.project));
			return { result, notice: build.notice };
		});
		return { table, build, steps };
	}

	it('gives the same project and the same link, step by step', () => {
		const project = threeStations([named('S1', 'Night', [level('A1', 3)])]);
		const { table, build, steps } = both(project, 'S1');
		expect(overrides(table, 'S1')).toEqual([
			level('A1', 3),
			status('P1', 'off'),
			status('Q2', 'off'),
			status('PB', 'on')
		]);
		expect(canonicalJson(table.store.project)).toBe(canonicalJson(build.store.project));
		expect(encodeProject(table.store.project)).toBe(encodeProject(build.store.project));
		// A name the user typed: never renamed, nothing said.
		expect(names(table)).toEqual(['Night']);
		expect(steps.every((s) => s.result.ok && s.result.renamed === '' && !s.notice)).toBe(true);
		// The table's workspace was never notified (quiet), and its case shown never changed.
		expect(table.notice).toBeNull();
		expect(table.store.activeCase).toBeNull();
	});

	it('gives the same project with an app-made name, both renaming with the same words', () => {
		const project = threeStations([named('S1', 'Night', []), named('S2', 'Scenario 2', [])]);
		const { table, build, steps } = both(project, 'S2');
		expect(names(table)).toEqual([
			'Night',
			'3 of 4 running (Pump P1 off); 1 of 2 running (Pump Q2 off); 2 of 2 running'
		]);
		expect(names(build)).toEqual(names(table));
		expect(encodeProject(table.store.project)).toBe(encodeProject(build.store.project));
		// Each step renamed, and the table's words are Build's notice (§4.5).
		expect(steps.map((s) => (s.result.ok ? s.result.renamed : null))).toEqual([
			'«Scenario 2» is now «3 of 4 running (Pump P3 off)»: a name the app made follows its pumps until you rename it.',
			'«3 of 4 running (Pump P3 off)» is now «2 of 4 running (Pump P1, Pump P3 off)»: a name the app made follows its pumps until you rename it.',
			'«2 of 4 running (Pump P1, Pump P3 off)» is now «2 of 4 running (Pump P1, Pump P3 off); 1 of 2 running (Pump Q2 off)»: a name the app made follows its pumps until you rename it.',
			'«2 of 4 running (Pump P1, Pump P3 off); 1 of 2 running (Pump Q2 off)» is now «3 of 4 running (Pump P1 off); 1 of 2 running (Pump Q2 off)»: a name the app made follows its pumps until you rename it.',
			'«3 of 4 running (Pump P1 off); 1 of 2 running (Pump Q2 off)» is now «3 of 4 running (Pump P1 off); 1 of 2 running (Pump Q2 off); 2 of 2 running»: a name the app made follows its pumps until you rename it.'
		]);
		expect(steps.map((s) => s.notice?.text)).toEqual(
			steps.map((s) => (s.result.ok ? s.result.renamed : null))
		);
		expect(table.notice).toBeNull();
	});

	it('is the same on the fixture’s two-systems, a standby put in service included', () => {
		const cases = fixture.cases as unknown as { name: string; project: Project }[];
		const project = cases.find((c) => c.name === 'two-systems')!.project;
		const table = testWorkspace(project, { now: NOW });
		const build = testWorkspace(project, { now: NOW });
		build.setCase('S3');
		for (const pumpId of ['PB', 'P2', 'P9', 'PA']) {
			expect(press(table, 'S3', pumpId).result.ok).toBe(true);
			setStatus(build, pumpId, shownStatus(build, pumpId) === 'on' ? 'off' : 'on');
		}
		expect(encodeProject(table.store.project)).toBe(encodeProject(build.store.project));
		// P2 back on removed its change; PB on, P9 off and PA off appended.
		expect(overrides(table, 'S3').slice(1)).toEqual([
			status('PB', 'on'),
			status('P9', 'off'),
			status('PA', 'off')
		]);
		expect(names(table)[2]).toBe('Aged pipe');
	});
});

describe('back to the base value (§8.6 item 2)', () => {
	it('removes the change: the case reads as the base case again', () => {
		const ws = testWorkspace(threeStations([named('S1', 'Night', [])]), { now: NOW });
		press(ws, 'S1', 'PB');
		press(ws, 'S1', 'P2');
		expect(overrides(ws, 'S1')).toEqual([status('PB', 'on'), status('P2', 'off')]);
		press(ws, 'S1', 'PB');
		expect(overrides(ws, 'S1')).toEqual([status('P2', 'off')]);
		press(ws, 'S1', 'P2');
		expect(overrides(ws, 'S1')).toEqual([]);
		const table = lineupTable({ project: ws.store.project, shownCase: null, filter: null });
		const row = table.rows[1]!;
		expect(row.cells.some((c) => c.marked)).toBe(false);
		expect(row.notes).toEqual(['Same case as the base case']);
	});
});

describe('one undo step per press (§8.6 item 3, §8.9)', () => {
	it('is labelled with the name after the step; Undo leaves the case shown', () => {
		const ws = testWorkspace(
			withScenarios(station(4), [named('S1', 'Scenario 1', []), named('S2', 'Night', [])]),
			{ now: NOW }
		);
		ws.setCase('S2');
		const before = ws.store.project;
		const depth = ws.store.undoDepth;
		const { result } = press(ws, 'S1', 'P3');
		expect(result).toEqual({
			ok: true,
			changed: true,
			renamed:
				'«Scenario 1» is now «3 of 4 running (Pump P3 off)»: a name the app made follows its pumps until you rename it.'
		});
		expect(ws.store.undoDepth).toBe(depth + 1);
		expect(ws.store.undoLabel).toBe('turn Pump P3 off in 3 of 4 running (Pump P3 off)');
		// The case shown is not changed by a press in another case.
		expect(ws.store.activeCase).toBe('S2');
		const undone = ws.undoStep();
		expect(undone).toEqual({
			step: 'undo',
			label: 'turn Pump P3 off in 3 of 4 running (Pump P3 off)',
			caseChanged: false,
			text: 'Undid turn Pump P3 off in 3 of 4 running (Pump P3 off).'
		});
		expect(ws.store.project).toEqual(before);
		expect(ws.store.activeCase).toBe('S2');
		// Nothing for the workspace notice: the case shown did not change.
		expect(ws.notice).toBeNull();
		expect(ws.redoStep()).toEqual({
			step: 'redo',
			label: 'turn Pump P3 off in 3 of 4 running (Pump P3 off)',
			caseChanged: false,
			text: 'Redid turn Pump P3 off in 3 of 4 running (Pump P3 off).'
		});
		expect(names(ws)).toEqual(['3 of 4 running (Pump P3 off)', 'Night']);
		expect(ws.store.activeCase).toBe('S2');
		expect(ws.undoStep()?.text).toBe('Undid turn Pump P3 off in 3 of 4 running (Pump P3 off).');
		expect(ws.undoStep()).toBeNull();
	});

	it('a press in the case shown updates Build’s forms at once', () => {
		const ws = testWorkspace(withScenarios(station(4), [named('S1', 'Night', [])]), { now: NOW });
		ws.setCase('S1');
		press(ws, 'S1', 'P2');
		expect(shownStatus(ws, 'P2')).toBe('off');
		expect(ws.componentChange('P2', 'status')).toMatchObject({ changed: true, baseText: 'On' });
		expect(ws.store.undoLabel).toBe('turn Pump P2 off in Night');
	});

	it('says the case shown when an undo or redo changes it, as the workspace notice does', () => {
		const ws = testWorkspace(withScenarios(station(4), [named('S1', 'Night', [])]), { now: NOW });
		ws.setCase('S1');
		setStatus(ws, 'P2', 'off');
		ws.setCase(null);
		const undone = ws.undoStep()!;
		expect(undone).toEqual({
			step: 'undo',
			label: 'change pump status in Night',
			caseChanged: true,
			text: 'Undid change pump status in Night. Now showing scenario Night.'
		});
		expect(ws.notice?.text).toBe(undone.text);
		ws.setCase(null);
		const redone = ws.redoStep()!;
		expect(redone.text).toBe('Redid change pump status in Night. Now showing scenario Night.');
		expect(ws.notice?.text).toBe(redone.text);
		// undo() and redo() keep their answer.
		expect(ws.undo()).toBe(true);
		expect(ws.redo()).toBe(true);
		expect(testWorkspace(station(2)).undo()).toBe(false);
	});

	it('New lineup is one step labelled as New scenario, the case shown unchanged', () => {
		const ws = testWorkspace(withScenarios(station(4), [named('S1', 'Night', [])]), { now: NOW });
		const added = newLineup(ws.store.project)!;
		expect(ws.updateStored(added.add, NEW_LINEUP_LABEL)).toBe(true);
		expect(ws.store.undoLabel).toBe('add scenario');
		expect(names(ws)).toEqual(['Night', 'Scenario 2']);
		expect(ws.store.activeCase).toBeNull();
		// Its first press renames it (§8.8).
		press(ws, 'S2', 'P4');
		expect(names(ws)).toEqual(['Night', '3 of 4 running (Pump P4 off)']);
	});
});

describe('the 31st change (§8.6 item 5)', () => {
	/** Fifteen pumps (thirty pipes): a scenario of thirty pipe lengths, and P1 off in the base. */
	function full(): Project {
		const project = station(15);
		const lengths: Override[] = project.connections.map((c) => ({
			kind: 'pipe',
			connectionId: c.id,
			pipeIndex: 0,
			field: 'length',
			value: 25
		}));
		expect(lengths).toHaveLength(MAX_CHANGES);
		return withScenarios(project, [named('S1', 'Full', lengths)]);
	}

	it('is refused with the table’s exact words, and nothing changes or is said', () => {
		const ws = testWorkspace(full(), { now: NOW });
		const before = canonicalJson(ws.store.project);
		const depth = ws.store.undoDepth;
		const { press: p, result } = press(ws, 'S1', 'P1');
		expect(result).toEqual({ ok: false, reason: 'limit', message: LIMIT_MESSAGE });
		expect(result.ok ? null : refusalText(p, 'Full', result.message)).toBe(
			'Could not turn Pump P1 off in Full: A scenario holds at most 30 changes.'
		);
		expect(canonicalJson(ws.store.project)).toBe(before);
		expect(ws.store.undoDepth).toBe(depth);
		expect(ws.notice).toBeNull();
	});

	it('leaves Build’s own refusal words unchanged', () => {
		const ws = testWorkspace(full(), { now: NOW });
		ws.setCase('S1');
		const before = canonicalJson(ws.store.project);
		expect(setStatus(ws, 'P1', 'off')).toBe(false);
		expect(ws.notice).toMatchObject({
			kind: 'error',
			text: 'Could not change pump status: A scenario holds at most 30 changes.'
		});
		expect(canonicalJson(ws.store.project)).toBe(before);
	});

	it('still lets a press change or remove a change the full case holds', () => {
		const project = full();
		const [first, ...rest] = scenariosOf(project)[0]!.overrides!;
		const ws = testWorkspace(
			withScenarios(project, [
				named('S1', 'Full', [first!, ...rest.slice(1), status('P1', 'off')])
			]),
			{ now: NOW }
		);
		expect(overrides(ws, 'S1')).toHaveLength(MAX_CHANGES);
		expect(press(ws, 'S1', 'P1').result.ok).toBe(true);
		expect(overrides(ws, 'S1')).toHaveLength(MAX_CHANGES - 1);
	});
});

describe('staleness (§6, fake solver)', () => {
	function solved() {
		const solve = vi.fn(async (): Promise<SolveResponse> => {
			return {
				success: true,
				computeTime: 0.01,
				solvedState: { converged: true } as unknown as SolveResponse['solvedState'],
				scenario: null
			};
		});
		const ws = testWorkspace(
			withScenarios(station(4), [
				named('S1', 'Two off', [status('P3', 'off'), status('P4', 'off')]),
				named('S2', 'Level', [level('A1', 3)])
			]),
			{ now: NOW, solver: { solve } satisfies Solver }
		);
		return { ws, solve };
	}
	const statuses = (ws: Workspace) => ws.store.caseIds.map((id) => ws.store.caseStatus(id));

	it('a press makes only its case out of date; Undo makes it current again', async () => {
		const { ws, solve } = solved();
		await ws.solveAll();
		expect(solve).toHaveBeenCalledTimes(3);
		expect(statuses(ws)).toEqual(['solved', 'solved', 'solved']);
		press(ws, 'S1', 'P2');
		expect(statuses(ws)).toEqual(['solved', 'stale', 'solved']);
		ws.undoStep();
		expect(statuses(ws)).toEqual(['solved', 'solved', 'solved']);
	});

	it('a round trip without Undo leaves its case out of date: the same changes, a new order', async () => {
		const { ws } = solved();
		await ws.solveAll();
		press(ws, 'S1', 'P3');
		expect(overrides(ws, 'S1')).toEqual([status('P4', 'off')]);
		press(ws, 'S1', 'P3');
		expect(overrides(ws, 'S1')).toEqual([status('P4', 'off'), status('P3', 'off')]);
		// The same case (§4.3), read as out of date: D15's key is conservative.
		expect(statuses(ws)).toEqual(['solved', 'stale', 'solved']);
		ws.undoStep();
		ws.undoStep();
		expect(overrides(ws, 'S1')).toEqual([status('P3', 'off'), status('P4', 'off')]);
		expect(statuses(ws)).toEqual(['solved', 'solved', 'solved']);
	});
});

describe('the manager’s tab and filter (§8.1)', () => {
	it('are page state, reset when another project is loaded', () => {
		const ws = testWorkspace(station(4));
		expect([ws.managerTab, ws.managerPumps]).toEqual(['cases', null]);
		ws.managerTab = 'lineups';
		ws.managerPumps = ['P1', 'P2'];
		ws.store.load(station(3));
		expect([ws.managerTab, ws.managerPumps]).toEqual(['cases', null]);
	});
});
