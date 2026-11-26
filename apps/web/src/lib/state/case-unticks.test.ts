/**
 * The remembered unticks and a scenario id taken again (proposals/open-defects-2.md F2, the
 * owner's answer of 2026-11-26): a new scenario that takes a deleted one's id (newScenarioId
 * gives the lowest free S<n>) starts ticked under both charts' lists; Undo of the delete still
 * restores the untick, also after a solve that recorded a new method version.
 *
 * The unticks are made as PumpsView's tickChoice makes them (pump-chart.ts untickCase): the case
 * the user unticked in the one shared list, and each chart's own list holding the cases then past
 * its cap.
 */
import { describe, expect, it } from 'vitest';
import type { Override, Project, Scenario, SolveResponse } from '../api/types';
import { station } from '../testing/lineups';
import { testWorkspace } from '../testing/workspace';
import { MAX_CHART_CASES, untickCase, type CaseChart, type CaseList } from '../utils/pump-chart';
import { MAX_GROUP_CASES } from '../utils/pump-group-one-off';
import { newScenarioId, newScenarioName, scenariosOf, withScenarios } from '../utils/scenarios';

const off = (...ids: string[]): Override[] =>
	ids.map((componentId) => ({ kind: 'component', componentId, field: 'status', value: 'off' }));
const named = (id: string, name: string, overrides: Override[]): Scenario => ({
	id,
	name,
	overrides
});
type Ws = ReturnType<typeof testWorkspace>;

/** Three scenarios, each a pump off. */
const three = () =>
	withScenarios(station(3), [
		named('S1', 'Pump P1 off', off('P1')),
		named('S2', 'Pump P2 off', off('P2')),
		named('S3', 'Pump P3 off', off('P3'))
	]);
/** Seven scenarios: more than either chart draws (five others on the pump chart, six on the card). */
const seven = () =>
	withScenarios(
		station(7),
		Array.from({ length: 7 }, (_, i) => named(`S${i + 1}`, `Pump P${i + 1} off`, off(`P${i + 1}`)))
	);

/** Both charts' lists as a tick reads them: every other case listed, the first ones drawn. */
function listsOf(ws: Ws): Partial<Record<CaseChart, CaseList>> {
	const listed = ws.scenarios.map((s) => s.id);
	const pumpCap = MAX_CHART_CASES - 1;
	return {
		pump: { listed, shown: listed.slice(0, pumpCap), cap: pumpCap },
		group: { listed, shown: listed.slice(0, MAX_GROUP_CASES), cap: MAX_GROUP_CASES }
	};
}
/** The user unticks `key` under a list (PumpsView tickChoice, pump-chart.ts untickCase). */
function untick(ws: Ws, key: string, lists: Partial<Record<CaseChart, CaseList>> = {}) {
	const next = untickCase(
		{ unticked: ws.casesUnticked, pump: ws.pumpChartUnticked, group: ws.pumpGroupUnticked },
		key,
		lists
	);
	ws.casesUnticked = next.unticked;
	ws.pumpChartUnticked = next.pump;
	ws.pumpGroupUnticked = next.group;
}
const sets = (ws: Ws) => ({
	cases: ws.casesUnticked,
	pump: ws.pumpChartUnticked,
	group: ws.pumpGroupUnticked
});
const ids = (ws: Ws) => ws.scenarios.map((s) => s.id);

/** The Scenarios manager's Delete (ScenarioManager.svelte remove()). */
function remove(ws: Ws, id: string) {
	const next = ws.scenarios.filter((s) => s.id !== id);
	expect(ws.updateStoredQuiet((p) => withScenarios(p, next), `delete scenario ${id}`).ok).toBe(
		true
	);
}
/** The Scenarios manager's Add scenario (ScenarioManager.svelte add()): the id newScenarioId. */
function add(ws: Ws): string {
	const id = newScenarioId(ws.store.project);
	const scenario = { id, name: newScenarioName(ws.store.project, id), overrides: [] };
	expect(
		ws.updateStoredQuiet((p) => withScenarios(p, [...scenariosOf(p), scenario]), 'add scenario').ok
	).toBe(true);
	return id;
}

describe('a scenario id taken again (open-defects-2 F2)', () => {
	it('starts a new scenario that takes a deleted one’s id ticked, and keeps every other untick', () => {
		const ws = testWorkspace(three());
		untick(ws, 'S1');
		untick(ws, 'S2');
		remove(ws, 'S2');
		// The deleted case's untick is kept, so its Undo restores it.
		expect(sets(ws)).toEqual({ cases: ['S1', 'S2'], pump: [], group: [] });
		expect(add(ws)).toBe('S2');
		expect(sets(ws)).toEqual({ cases: ['S1'], pump: [], group: [] });
	});

	it('prunes on every commit path: updateStored (Add cases, goal seek’s Apply) as the manager’s', () => {
		const ws = testWorkspace(three());
		untick(ws, 'S3');
		remove(ws, 'S3');
		const scenario = { id: 'S3', name: 'Scenario 3', overrides: off('P1', 'P2') };
		expect(ws.updateStored((p) => withScenarios(p, [...scenariosOf(p), scenario]), 'add')).toBe(
			true
		);
		expect(sets(ws)).toEqual({ cases: [], pump: [], group: [] });
	});

	it('restores the untick when the delete is undone, and keeps it when it is redone (holds already)', () => {
		const ws = testWorkspace(three());
		untick(ws, 'S2');
		remove(ws, 'S2');
		expect(ws.undo()).toBe(true);
		expect(ids(ws)).toEqual(['S1', 'S2', 'S3']);
		expect(sets(ws)).toEqual({ cases: ['S2'], pump: [], group: [] });
		expect(ws.redo()).toBe(true);
		expect(sets(ws)).toEqual({ cases: ['S2'], pump: [], group: [] });
	});

	it('untick, delete, create, Undo twice: the deleted scenario comes back unticked, the new one ticked on Redo twice', () => {
		const ws = testWorkspace(three());
		untick(ws, 'S2');
		remove(ws, 'S2');
		expect(add(ws)).toBe('S2');
		expect(sets(ws).cases).toEqual([]);
		// Undo the creation: the id free again holds the deleted scenario's untick.
		expect(ws.undo()).toBe(true);
		expect(ids(ws)).toEqual(['S1', 'S3']);
		expect(sets(ws).cases).toEqual(['S2']);
		// Undo the delete: it comes back unticked (the owner's answer).
		expect(ws.undo()).toBe(true);
		expect(ws.scenarios.find((s) => s.id === 'S2')?.name).toBe('Pump P2 off');
		expect(sets(ws).cases).toEqual(['S2']);
		// Redo both: the new scenario comes back ticked, as it was made.
		expect(ws.redo()).toBe(true);
		expect(sets(ws).cases).toEqual(['S2']);
		expect(ws.redo()).toBe(true);
		expect(ws.scenarios.find((s) => s.id === 'S2')?.name).toBe('Scenario 2');
		expect(sets(ws).cases).toEqual([]);
	});

	it('prunes a deleted case past a chart’s cap (that chart’s own list only), and gives it back on Undo', () => {
		const ws = testWorkspace(seven());
		// Unticking S1, drawn on both charts, leaves the cases past each cap unticked there only.
		untick(ws, 'S1', listsOf(ws));
		expect(sets(ws)).toEqual({ cases: ['S1'], pump: ['S6', 'S7'], group: ['S7'] });
		// S6 is past the pump chart's cap only: its untick is in that chart's own list alone.
		remove(ws, 'S6');
		expect(add(ws)).toBe('S6');
		expect(sets(ws)).toEqual({ cases: ['S1'], pump: ['S7'], group: ['S7'] });
		expect(ws.undo()).toBe(true);
		expect(ws.undo()).toBe(true);
		expect(ws.scenarios.find((s) => s.id === 'S6')?.name).toBe('Pump P6 off');
		expect(sets(ws)).toEqual({ cases: ['S1'], pump: ['S7', 'S6'], group: ['S7'] });
		expect(ws.redo()).toBe(true);
		expect(ws.redo()).toBe(true);
		expect(sets(ws)).toEqual({ cases: ['S1'], pump: ['S7'], group: ['S7'] });
	});

	it('gives the new scenario its own untick back on Redo, and the deleted one its own on Undo', () => {
		const ws = testWorkspace(seven());
		untick(ws, 'S1', listsOf(ws));
		remove(ws, 'S6');
		add(ws);
		// The new S6 unticked by the user (no chart drew it yet): in the shared list.
		untick(ws, 'S6');
		expect(sets(ws)).toEqual({ cases: ['S1', 'S6'], pump: ['S7'], group: ['S7'] });
		expect(ws.undo()).toBe(true);
		expect(sets(ws)).toEqual({ cases: ['S1'], pump: ['S7', 'S6'], group: ['S7'] });
		expect(ws.redo()).toBe(true);
		expect(sets(ws)).toEqual({ cases: ['S1', 'S6'], pump: ['S7'], group: ['S7'] });
	});

	it('never gives a new scenario’s own untick to the ticked one whose id it took, on Undo', () => {
		const ws = testWorkspace(three());
		// S2 ticked, deleted; the new S2 takes its id and is unticked by the user.
		remove(ws, 'S2');
		expect(add(ws)).toBe('S2');
		untick(ws, 'S2');
		expect(ws.undo()).toBe(true);
		expect(ws.undo()).toBe(true);
		expect(ws.scenarios.find((s) => s.id === 'S2')?.name).toBe('Pump P2 off');
		expect(sets(ws).cases).toEqual([]);
		// Redo both: the new one comes back with its own untick.
		expect(ws.redo()).toBe(true);
		expect(ws.redo()).toBe(true);
		expect(ws.scenarios.find((s) => s.id === 'S2')?.name).toBe('Scenario 2');
		expect(sets(ws).cases).toEqual(['S2']);
	});

	it('keeps the swap over a solve that records a new method version (#recordMethodVersion)', async () => {
		const solved = {
			success: true,
			computeTime: 0,
			solvedState: { methodVersion: '9.9.9' },
			scenario: null
		} as unknown as SolveResponse;
		const project: Project = { ...three(), methodVersion: '1.0.0' };
		const ws = testWorkspace(project, { solver: { solve: async () => solved } });
		untick(ws, 'S2');
		remove(ws, 'S2');
		expect(add(ws)).toBe('S2');
		expect(sets(ws).cases).toEqual([]);
		const made = ws.store.project;
		await ws.store.solve();
		// The store replaced the project with a copy that holds the version (no undo step).
		expect(ws.store.project.methodVersion).toBe('9.9.9');
		expect(ws.store.project).not.toBe(made);
		expect(ws.undo()).toBe(true);
		expect(ids(ws)).toEqual(['S1', 'S3']);
		expect(sets(ws).cases).toEqual(['S2']);
		expect(ws.undo()).toBe(true);
		expect(ws.scenarios.find((s) => s.id === 'S2')?.name).toBe('Pump P2 off');
		expect(sets(ws).cases).toEqual(['S2']);
		expect(ws.redo()).toBe(true);
		expect(ws.redo()).toBe(true);
		expect(ws.scenarios.find((s) => s.id === 'S2')?.name).toBe('Scenario 2');
		expect(sets(ws).cases).toEqual([]);
	});

	it('takes a scenario’s untick away with its creation undone, and gives it back on Redo', () => {
		const ws = testWorkspace(three());
		const id = add(ws);
		expect(id).toBe('S4');
		untick(ws, id);
		expect(ws.undo()).toBe(true);
		expect(ids(ws)).toEqual(['S1', 'S2', 'S3']);
		// Kept for the Redo, so a scenario that takes the id meanwhile never meets it.
		expect(sets(ws).cases).toEqual([]);
		expect(ws.redo()).toBe(true);
		expect(sets(ws).cases).toEqual(['S4']);
	});

	it('changes nothing on a step that creates no scenario, nor on the base case’s key (holds already)', () => {
		const ws = testWorkspace(three());
		untick(ws, '');
		untick(ws, 'S1');
		expect(
			ws.updateStoredQuiet(
				(p) =>
					withScenarios(
						p,
						scenariosOf(p).map((s) => (s.id === 'S1' ? { ...s, name: 'Renamed' } : s))
					),
				'rename scenario S1'
			).ok
		).toBe(true);
		expect(sets(ws)).toEqual({ cases: ['', 'S1'], pump: [], group: [] });
	});
});
