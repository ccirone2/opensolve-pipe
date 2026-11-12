/**
 * Results across the cases of a project with scenarios (proposal scenario-manager.md §6.10-§6.15):
 * Compare's defaults and columns, a solve of another case, the chart's other cases, focus and
 * live regions during Solve all, which cases Solve all solves, long case names, page state on
 * opening another project, the description of composite scenario values, and the server's record
 * of a solve shown as it was solved. Values typed here and the solved states are made-up test
 * inputs.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import { NetworkError, ValidationError } from '$lib/api/client';
import type {
	Component,
	GoalSeekResponse,
	Override,
	Project,
	ScenarioResult,
	SolveResponse,
	SystemCurveResponse
} from '$lib/api/types';
import type { Solver } from '$lib/state/project.svelte';
import { outOfSight, wordsInSight } from '$lib/testing/helpers';
import { pumpTransferSolved, response, systemCurveResponse } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { insertComponentInConnection, updateComponent } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent, createEmptyProject } from '$lib/utils/factory';
import { newGoal, newVariable, toRequest } from '$lib/utils/goal-seek';
import { withScenarios } from '$lib/utils/scenarios';
import WorkspaceView from './Workspace.svelte';

const level6: Override = { kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 };
const isolated: Override = {
	kind: 'component',
	componentId: 'V1',
	field: 'status',
	value: 'isolated'
};
const slower: Override = { kind: 'component', componentId: 'P1', field: 'speed', value: 0.9 };

function twoCases(scenarios = [{ id: 'S1', name: 'Higher tank', overrides: [level6] }]): Project {
	return withScenarios(pumpTransferExample(), scenarios);
}

function setup(project: Project, solver?: Solver) {
	const ws = testWorkspace(project, solver ? { solver } : {});
	render(WorkspaceView, { workspace: ws });
	return ws;
}

const solvesOk: Solver = { solve: async () => response(pumpTransferSolved()) };

/** A solver whose requests wait until `release()` answers the latest one. */
function heldSolver() {
	let answer: (() => void) | null = null;
	const signals: AbortSignal[] = [];
	const solve = vi.fn(
		(_p: Project, _o?: unknown, request?: { signal?: AbortSignal }) =>
			new Promise<SolveResponse>((resolve) => {
				if (request?.signal) signals.push(request.signal);
				answer = () => resolve(response(pumpTransferSolved()));
			})
	);
	return { solver: { solve } satisfies Solver, solve, signals, release: () => answer?.() };
}

async function openCompare() {
	await fireEvent.click(screen.getByRole('tab', { name: 'Compare cases' }));
	return screen.getByRole('region', { name: 'Compare cases' });
}

/** The Scenarios menu (build-density.md §13), opened from the header: the case shown, Solve all. */
async function caseMenu(): Promise<HTMLElement> {
	const group = screen.queryByRole('group', { name: 'Case' });
	if (group) return group;
	await fireEvent.click(screen.getByRole('button', { name: /^Scenarios/ }));
	return screen.getByRole('group', { name: 'Case' });
}

describe('Compare cases', () => {
	it('builds its default rows from the scenarios as they are, also after results were shown', async () => {
		const ws = setup(pumpTransferExample(), solvesOk);
		await ws.solve();
		await tick();
		await fireEvent.click(screen.getByRole('tab', { name: 'Nodes' }));
		ws.updateStored(
			(p) => withScenarios(p, [{ id: 'S1', name: 'Higher tank', overrides: [level6, isolated] }]),
			'add scenario'
		);
		await ws.solveAll();
		await tick();
		const compare = await openCompare();
		const table = within(compare).getByRole('table', { name: 'Results by case' });
		for (const name of [
			/Discharge tank · Outflow/,
			/Discharge isolation valve · Flow/,
			/Discharge isolation valve · State/
		]) {
			expect(within(table).getByRole('row', { name })).toBeInTheDocument();
		}
	});

	it('shows no values for a case whose latest solve failed, or that a stopped run did not reach', async () => {
		let busy = false;
		const ws = setup(
			twoCases([
				{ id: 'S1', name: 'Higher tank', overrides: [level6] },
				{ id: 'S2', name: 'Copy', overrides: [] }
			]),
			{
				solve: async (_p, _o, request) => {
					if (busy && request?.scenarioId === 'S1')
						throw new NetworkError('The server is busy.', 503, 'SERVER_BUSY');
					return response(pumpTransferSolved());
				}
			}
		);
		await ws.solveAll();
		ws.store.update(
			(p) => updateComponent(p, 'R1', (c) => ({ ...c, liquidLevel: 3.4 }) as Component),
			'change level'
		);
		busy = true;
		await ws.solveAll();
		await tick();
		expect([ws.store.caseStatus('S1'), ws.store.caseStatus('S2')]).toEqual([
			'failed',
			'not_reached'
		]);
		const compare = await openCompare();
		const table = within(compare).getByRole('table', { name: 'Results by case' });
		const cells = within(
			within(table).getByRole('row', { name: /Transfer pump · Flow/ })
		).getAllByRole('cell');
		expect(cells[0]).not.toHaveTextContent('—');
		for (const cell of cells.slice(1)) {
			expect(cell).toHaveTextContent(/^—$/);
			expect(cell).not.toHaveTextContent('difference from base');
		}
		// A long status has a short form in the column header, its full words for screen readers.
		const headers = within(table).getAllByRole('columnheader');
		expect(headers[3]).toHaveTextContent('Not reached');
		expect(headers[3]).toHaveTextContent('Not solved: the run stopped after a network error');
	});

	it('says which cases Solve all solves, and which have an error to fix first', async () => {
		const ws = setup(twoCases([{ id: 'S1', name: 'Winter', overrides: [slower] }]), {
			solve: async (_p, _o, request) => {
				if (request?.scenarioId === 'S1') {
					throw new ValidationError(
						'Invalid input: 1 problem(s).',
						['body.project.scenarios.0.overrides.0: made-up rule'],
						400,
						'VALIDATION_ERROR'
					);
				}
				return response(pumpTransferSolved());
			}
		});
		// Before the run both cases are to solve: the amber line says so and names the Scenarios
		// menu's Solve all (build-density.md §19), so the check below that it has gone tests a line
		// that is drawn otherwise.
		expect(await openCompare()).toHaveTextContent(
			'2 of 2 cases have results that are missing or out of date: Solve all, in the Scenarios menu at the top (Ctrl+Shift+Enter or ⌘+Shift+Enter), solves them one after another.'
		);
		await ws.solveAll();
		await tick();
		expect(ws.store.caseStatus('S1')).toBe('failed');
		const compare = await openCompare();
		expect(compare).not.toHaveTextContent('missing or out of date');
		expect(compare).toHaveTextContent(
			'Winter failed with an error to fix first: Solve all skips it until its inputs change.'
		);
		const bar = await caseMenu();
		const solveAll = within(bar).getByRole('button', { name: 'Solve all' });
		expect(solveAll).toHaveAttribute('aria-disabled', 'true');
		expect(solveAll).toHaveAccessibleDescription(
			'Every case is solved except Winter, which has an error to fix first.'
		);
	});

	it('row headers of a case without results say so and open nothing; a column header focuses its case', async () => {
		const ws = setup(twoCases([{ id: 'S1', name: 'Winter', overrides: [level6] }]), solvesOk);
		await ws.solveAll();
		ws.updateStored(
			(p) =>
				withScenarios(p, [...(p.scenarios ?? []), { id: 'S2', name: 'New case', overrides: [] }]),
			'add scenario'
		);
		ws.setCase('S2');
		await tick();
		const compare = await openCompare();
		const table = within(compare).getByRole('table', { name: 'Results by case' });
		const row = within(table).getByRole('button', { name: 'Transfer pump · Flow' });
		expect(row).toHaveAttribute('aria-disabled', 'true');
		expect(row).toHaveAccessibleDescription('Solve New case to open its traces.');
		await fireEvent.click(row);
		expect(ws.inspected).toBeNull();
		const column = within(table).getByRole('button', { name: 'Winter' });
		column.focus();
		await fireEvent.click(column);
		await tick();
		expect(ws.store.activeCase).toBe('S1');
		expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Winter' }));
	});

	it('the base case has no card of its own: its tab and Compare cases beside it say it', async () => {
		// The base case's line and its Compare cases button repeated the case tabs right above
		// them (proposal build-density.md §15); the tab is the way to compare.
		const ws = setup(twoCases(), solvesOk);
		await ws.solveAll();
		await tick();
		const results = screen.getByRole('region', { name: 'Results' });
		expect(within(results).queryByText(/the network as built/)).toBeNull();
		expect(within(results).getByRole('tab', { name: 'Base case' })).toHaveAttribute(
			'aria-selected',
			'true'
		);
		const compare = within(results).getByRole('tab', { name: 'Compare cases' });
		await fireEvent.click(compare);
		await tick();
		expect(ws.comparing).toBe(true);
		expect(compare).toHaveAttribute('aria-selected', 'true');
	});
});

describe('solving cases', () => {
	it('a solve of another case stays in view and can be cancelled after a case switch', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		ws.setCase('S1');
		void ws.solve();
		await tick();
		ws.setCase(null);
		await tick();
		const header = screen.getByRole('toolbar', { name: 'Project' });
		expect(within(header).getByRole('button', { name: /^Solving…/ })).toHaveAttribute(
			'aria-disabled',
			'true'
		);
		const bar = await caseMenu();
		expect(within(bar).getByRole('status')).toHaveTextContent('Solving Higher tank…');
		expect(within(bar).getByRole('button', { name: 'Solve all' })).toHaveAttribute(
			'aria-disabled',
			'true'
		);
		await fireEvent.click(
			within(header).getByRole('button', { name: 'Cancel solving Higher tank' })
		);
		expect(held.signals[0]?.aborted).toBe(true);
		expect(ws.store.resultsFor('S1').cancelled).toBe(true);
	});

	it('Solve all from the case bar keeps the focus there, and gives it to Solve when it ends', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		const bar = await caseMenu();
		// Its name counts the cases while it can run (build-density.md §19).
		const button = within(bar).getByRole('button', { name: 'Solve all (2)' });
		button.focus();
		await fireEvent.click(button);
		await tick();
		expect(ws.store.run).not.toBeNull();
		expect(document.activeElement).toBe(button);
		expect(button).toHaveAttribute('aria-disabled', 'true');
		held.release();
		await vi.waitFor(() => expect(held.solve).toHaveBeenCalledTimes(2));
		held.release();
		await vi.waitFor(() => expect(ws.store.run).toBeNull());
		await tick();
		await vi.waitFor(() =>
			expect(document.activeElement).toBe(
				within(screen.getByRole('toolbar', { name: 'Project' })).getByRole('button', {
					name: /^Solve /
				})
			)
		);
	});

	it('announces the progress of Solve all in one live region', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		await openCompare();
		void ws.solveAll();
		await tick();
		const live = screen
			.getAllByRole('status')
			.filter((s) => /Solving 1 of 2/.test(s.textContent ?? ''));
		expect(live).toHaveLength(1);
		expect(screen.getByRole('region', { name: 'Compare cases' })).toHaveTextContent(
			'Solving 1 of 2: Base case…'
		);
	});

	it('a case switch replaces the results status line instead of updating it', async () => {
		const ws = setup(twoCases(), solvesOk);
		await ws.solveAll();
		await tick();
		const results = screen.getByRole('region', { name: 'Results' });
		const before = within(results).getByRole('status');
		ws.setCase('S1');
		await tick();
		const after = within(results).getByRole('status');
		expect(after).toHaveTextContent('Last solve of Higher tank: converged');
		expect(after).not.toBe(before);
	});

	it('keeps a long case name out of the visible label of Solve', async () => {
		const name = 'A rather long scenario name for the winter peak case of the plant';
		const ws = setup(twoCases([{ id: 'S1', name, overrides: [] }]));
		ws.setCase('S1');
		await tick();
		// The header's Solve, the one Solve (build-density.md §19; the Results pane has none). Its
		// visible label is read, not the button's text: the button also holds "Solving…", drawn
		// invisible in the same place, and the case's name for screen readers only.
		const header = screen.getByRole('toolbar', { name: 'Project' });
		const button = within(header).getByRole('button', { name: `Solve ${name}` });
		const walker = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
		let visible = '';
		for (let n = walker.nextNode(); n; n = walker.nextNode()) {
			if (!n.parentElement?.closest('.sr-only, .invisible')) visible += n.textContent ?? '';
		}
		expect(visible.trim()).toBe('Solve');
	});
});

describe('the pump chart with other cases', () => {
	it('asks for the other cases’ system curves after a case switch', async () => {
		const curves: { scenarioId?: string; overlay: boolean }[] = [];
		const ws = setup(
			twoCases([
				{ id: 'S1', name: 'Higher tank', overrides: [level6] },
				{ id: 'S2', name: 'Slower pump', overrides: [slower] }
			]),
			{
				solve: async () => response(pumpTransferSolved()),
				systemCurve: async (_p, pumpId, options): Promise<SystemCurveResponse> => {
					curves.push({
						...(options?.scenarioId ? { scenarioId: options.scenarioId } : {}),
						overlay: options?.flowMin !== undefined
					});
					return systemCurveResponse(pumpId);
				}
			}
		);
		await ws.solveAll();
		ws.setCase('S2');
		await tick();
		await fireEvent.click(screen.getByRole('tab', { name: 'Pumps' }));
		await waitFor(() => expect(curves).toEqual([{ scenarioId: 'S2', overlay: false }]));
		await fireEvent.click(
			await screen.findByRole('checkbox', { name: "Also show the other cases' system curves" })
		);
		await waitFor(() => expect(curves.filter((c) => c.overlay)).toHaveLength(2));
		curves.length = 0;
		ws.setCase(null);
		await tick();
		await waitFor(() =>
			expect(curves).toEqual([{ overlay: false }, { scenarioId: 'S2', overlay: true }])
		);
	});
});

describe('page state', () => {
	it('is reset when another project is opened in the page', () => {
		const ws = testWorkspace(twoCases());
		ws.comparing = true;
		ws.compareRows = [{ quantity: 'valveHeadLoss', elementId: 'V1' }];
		ws.managerOpen = true;
		ws.managerFocus = 'S1';
		ws.settingsOpen = true;
		ws.inspected = { kind: 'component', id: 'V1' };
		ws.store.load(twoCases([{ id: 'S9', name: 'Other', overrides: [] }]));
		expect([
			ws.comparing,
			ws.compareRows,
			ws.managerOpen,
			ws.managerFocus,
			ws.settingsOpen,
			ws.inspected
		]).toEqual([false, null, false, null, false, null]);
	});
});

describe('composite scenario values', () => {
	const spec: Override = {
		kind: 'pipe',
		connectionId: 'L2',
		pipeIndex: 0,
		field: 'spec',
		value: { materialId: 'carbon_steel', schedule: '80', nominalSize: 3 * 0.0254 }
	};

	it('describe every input of a pipe’s size and material with the group’s note', async () => {
		const ws = setup(twoCases([{ id: 'S1', name: 'Winter', overrides: [spec] }]));
		ws.show('P1', 'discharge');
		await tick();
		const build = screen.getByRole('region', { name: 'Build' });
		const fields = () => [
			within(build).getByRole('combobox', { name: 'Material' }),
			within(build).getByRole('textbox', { name: /^Size \(NPS\)/ }),
			within(build).getByRole('textbox', { name: /^Inner diameter override/ })
		];
		for (const field of fields()) {
			expect(field).toHaveAccessibleDescription(/Winter sets its own value\./);
		}
		ws.setCase('S1');
		await tick();
		for (const field of fields()) {
			expect(field).toHaveAccessibleDescription(/Changed in this scenario\. Base value /);
		}
	});

	it('describe the kind and the number of a valve’s resistance with the group’s note', async () => {
		const ws = setup(
			twoCases([
				{
					id: 'S1',
					name: 'Winter',
					overrides: [
						{
							kind: 'component',
							componentId: 'V1',
							field: 'resistance',
							value: { kind: 'K', value: 2 }
						}
					]
				}
			])
		);
		ws.setCase('S1');
		ws.nav.jumpTo('V1');
		await tick();
		const build = screen.getByRole('region', { name: 'Build' });
		for (const field of [
			within(build).getByRole('combobox', { name: 'Resistance given as' }),
			within(build).getByRole('textbox', { name: /^K/ })
		]) {
			expect(field).toHaveAccessibleDescription(/Changed in this scenario\. Base value /);
		}
	});

	it('describe every input of the fluid with the fluid’s note', async () => {
		const ws = setup(
			twoCases([
				{
					id: 'S1',
					name: 'Winter',
					overrides: [{ kind: 'project', field: 'fluid.temperature', value: 278.15 }]
				}
			])
		);
		ws.setCase('S1');
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
		const dialog = await screen.findByRole('dialog', { name: 'Project settings' });
		for (const field of [
			within(dialog).getByRole('combobox', { name: 'Fluid' }),
			within(dialog).getByRole('textbox', { name: /^Operating temperature/ }),
			within(dialog).getByRole('textbox', { name: /^Density override/ })
		]) {
			expect(field).toHaveAccessibleDescription(/Changed in this scenario\. Base value /);
		}
	});
});

describe('the record of a scenario’s solve', () => {
	function withPrv() {
		const base = pumpTransferExample();
		const prv = { ...createComponent('prv', base), setpoint: 300000 };
		const project = insertComponentInConnection(base, 'L3', prv);
		const overrides: Override[] = [
			{ kind: 'component', componentId: prv.id, field: 'setpoint', value: 350000 },
			{ kind: 'component', componentId: 'P1', field: 'speed', value: 0.9 },
			{ kind: 'pipe', connectionId: 'L2', pipeIndex: 0, field: 'length', value: 7 }
		];
		const scenario: ScenarioResult = {
			id: 'S1',
			name: 'Winter',
			description: null,
			overrides: [
				{
					index: 0,
					override: overrides[0]!,
					state: 'applied',
					value: 350000,
					baseValue: 300000,
					unit: 'Pa(g)',
					message: ''
				},
				{
					index: 1,
					override: overrides[1]!,
					state: 'applied',
					value: 0.9,
					baseValue: 1,
					unit: '',
					message: ''
				},
				{
					index: 2,
					override: overrides[2]!,
					state: 'applied',
					value: 7,
					baseValue: 3,
					unit: 'm',
					message: ''
				}
			]
		};
		const solver: Solver = {
			solve: async (_p, _o, request) =>
				response(pumpTransferSolved(), request?.scenarioId ? { scenario } : {})
		};
		const ws = setup(withScenarios(project, [{ id: 'S1', name: 'Winter', overrides }]), solver);
		return { ws, prv };
	}

	it('keeps the units of the solve shown after the valve type changes in the base', async () => {
		const { ws, prv } = withPrv();
		ws.setCase('S1');
		await ws.solve();
		await tick();
		ws.store.update(
			(p) =>
				updateComponent(
					p,
					prv.id,
					(c) => ({ ...c, valveType: 'fcv', setpoint: 0.01 }) as Component
				),
			'make it an FCV'
		);
		await tick();
		const card = screen.getByRole('region', { name: /^Scenario: Winter/ });
		expect(card).toHaveTextContent('Outlet pressure setpoint: 350 kPa(g) (base: 300 kPa(g))');
		expect(card).not.toHaveTextContent('L/s');
		await fireEvent.click(within(card).getByRole('button', { name: prv.name }));
		const trace = await screen.findByRole('dialog', { name: prv.name });
		const block = within(trace).getByRole('region', { name: 'Changed by this scenario' });
		expect(block).toHaveTextContent('Outlet pressure setpoint: 350 kPa(g) (base: 300 kPa(g))');
	});

	it('names the pipe of a pipe change in the trace', async () => {
		const { ws } = withPrv();
		ws.setCase('S1');
		await ws.solve();
		await tick();
		ws.inspect({ kind: 'connection', id: 'L2' });
		await tick();
		const block = screen.getByRole('region', { name: 'Changed by this scenario' });
		expect(block).toHaveTextContent('Pipe 1 length: 7 m (base: 3 m)');
	});

	it('marks the changed pump and connection in the Pumps and Links tables', async () => {
		const { ws } = withPrv();
		ws.setCase('S1');
		await ws.solve();
		await tick();
		await fireEvent.click(screen.getByRole('tab', { name: 'Pumps' }));
		const pumps = screen.getByRole('table', { name: 'Results per pump' });
		expect(within(pumps).getByRole('row', { name: /Transfer pump/ })).toHaveTextContent(
			'changed in this scenario'
		);
		await fireEvent.click(screen.getByRole('tab', { name: 'Links' }));
		const links = screen.getByRole('table', { name: 'Results per pipe connection' });
		const rows = within(links).getAllByRole('row');
		const marked = rows.filter((r) => /changed in this scenario/.test(r.textContent ?? ''));
		expect(marked).toHaveLength(1);
		expect(marked[0]).toHaveTextContent('Transfer pump → ');
	});
});

// ---- One Solve, one Solve all (build-density.md §19) -------------------------------------------

const SOLVE_ALL = /^Solve all( \(\d+\))?$/;
const FOLLOWING = Node.DOCUMENT_POSITION_FOLLOWING;
/** Solve all's title when no reason passes: its shortcut (Solve's wording). */
const ALL_KEYS = 'Solve all (Ctrl+Shift+Enter or ⌘+Shift+Enter)';
const hint = (n: string) =>
	`Solves each case whose results are missing or out of date, one after another: up to ${n}.`;
const words = (text: string | null | undefined) => (text ?? '').replace(/\s+/g, ' ').trim();
const scenariosButton = () => screen.getByRole('button', { name: /^Scenarios/ });
const menuPanel = () => document.getElementById(scenariosButton().getAttribute('aria-controls')!)!;
const header = () => screen.getByRole('toolbar', { name: 'Project' }).closest('header')!;
const solveAllOf = (group: HTMLElement) =>
	within(group).getByRole('button', { name: /^Solve all/ });
const CANCELLED_TEXT = 'Solve all was cancelled: the cases not solved keep what they had.';
const CANCELLED = /^Solve all was cancelled: the cases not solved keep what they had\.$/;
/** The header's screen-reader line (the menu's own status line is in the header too). */
const headerTwin = () => header().querySelector<HTMLElement>(':scope > p[role="status"]')!;
/** Every update, and the end of a step that waits a tick (the header's focus handoff). */
async function settled() {
	await tick();
	await new Promise((resolve) => setTimeout(resolve, 0));
	await tick();
}
/** The texts a live region takes, one per change: what a screen reader says (none for ''). */
function sayings(region: HTMLElement): string[] & { stop: () => void } {
	const said: string[] = [];
	const observer = new MutationObserver(() => {
		const text = words(region.textContent);
		if (text) said.push(text);
	});
	observer.observe(region, { childList: true, characterData: true, subtree: true });
	return Object.assign(said, { stop: () => observer.disconnect() });
}
/** Solve all's line: always its description. */
const lineOf = (button: HTMLElement) =>
	document.getElementById(button.getAttribute('aria-describedby') ?? '')!;
/** A held solver that also answers a goal seek never (it runs until cancelled). */
function heldWithGoalSeek() {
	const held = heldSolver();
	const solver: Solver = {
		...held.solver,
		goalSeek: () => new Promise<GoalSeekResponse>(() => {})
	};
	return { ...held, solver };
}
/** Start a goal seek on the base case (made-up setup: L2's flow by P1's speed). */
function startGoalSeek(ws: ReturnType<typeof setup>) {
	const project = ws.store.project;
	void ws.store.runGoalSeek(
		toRequest(
			{
				goals: [{ ...newGoal({ elementId: 'L2' }, 'link_flow'), target: 0.015 }],
				variables: [
					newVariable(project, { target: { kind: 'component', componentId: 'P1' }, field: 'speed' })
				]
			},
			project,
			null
		)
	);
}

describe('the Scenarios menu: Solve all leads it (build-density.md §19)', () => {
	it('holds, in order: Solve all, its line, the status, a rule, the Case select, its note, Manage scenarios…', async () => {
		setup(twoCases());
		const group = await caseMenu();
		const button = solveAllOf(group);
		const line = lineOf(button);
		const status = within(group).getByRole('status');
		const select = within(group).getByRole('combobox', { name: 'Case' });
		const label = group.querySelector(`label[for="${select.id}"]`)!;
		const note = within(group).getByText(
			'Edits change the base case and every scenario that does not set its own value.'
		);
		const manage = within(group).getByRole('button', { name: 'Manage scenarios…' });
		// Read by nodes, text included: the words in that order and nothing else (the status is
		// empty while nothing runs).
		const parts: [string, Element[]][] = [
			['Solve all', [button]],
			['line', [line]],
			['status', [status]],
			['select', [label, select]],
			['note', [note]],
			['manage', [manage]]
		];
		const seen: string[] = [];
		const walker = document.createTreeWalker(group, NodeFilter.SHOW_TEXT);
		for (let n = walker.nextNode(); n; n = walker.nextNode()) {
			const text = n.textContent?.trim();
			if (!text) continue;
			const part = parts.find(([, els]) => els.some((el) => el.contains(n)))?.[0] ?? `“${text}”`;
			if (seen.at(-1) !== part) seen.push(part);
		}
		expect(seen).toEqual(['Solve all', 'line', 'select', 'note', 'manage']);
		// Each element after the one before, the empty status and the rule included.
		const rule = group.querySelector<HTMLElement>('.border-t');
		expect(rule).not.toBeNull();
		expect(rule).toHaveClass('border-slate-200', 'pt-2');
		const order = [button, line, status, rule!, label, select, note, manage];
		for (let i = 1; i < order.length; i++) {
			expect(
				order[i - 1]!.compareDocumentPosition(order[i]!) & FOLLOWING,
				`part ${i}`
			).toBeTruthy();
		}
	});

	it('Solve all is the primary button with its count while it can run; none when current, during a run or a goal seek', async () => {
		const held = heldWithGoalSeek();
		const ws = setup(twoCases(), held.solver);
		let group = await caseMenu();
		const button = within(group).getByRole('button', { name: 'Solve all (2)' });
		expect(button).toHaveClass('btn', 'btn-primary');
		expect(button).toHaveAttribute('data-solve-all');
		expect(button).toHaveAttribute('aria-keyshortcuts', 'Control+Shift+Enter Meta+Shift+Enter');
		expect(button).toHaveAttribute('title', ALL_KEYS);
		expect(button).not.toHaveAttribute('aria-disabled', 'true');
		expect(button.querySelector('svg')).toHaveClass('size-4');
		// A run: no count beside its progress (the badge counts down).
		await fireEvent.click(button);
		await tick();
		expect(ws.store.run).not.toBeNull();
		expect(button).toHaveAccessibleName('Solve all');
		expect(button).toHaveAttribute('aria-disabled', 'true');
		expect(within(group).getByRole('status')).toHaveTextContent('Solving 1 of 2: Base case…');
		held.release();
		await vi.waitFor(() => expect(held.solve).toHaveBeenCalledTimes(2));
		held.release();
		await vi.waitFor(() => expect(ws.store.run).toBeNull());
		await tick();
		// Every case current.
		group = await caseMenu();
		expect(solveAllOf(group)).toHaveAccessibleName('Solve all');
		expect(solveAllOf(group)).toHaveAttribute('aria-disabled', 'true');
		// Out of date again: counted; then a goal seek: not.
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		await tick();
		expect(solveAllOf(group)).toHaveAccessibleName('Solve all (2)');
		startGoalSeek(ws);
		await tick();
		expect(ws.store.calculating).toBe('goalSeek');
		expect(solveAllOf(group)).toHaveAccessibleName('Solve all');
		expect(solveAllOf(group)).toHaveAttribute('aria-disabled', 'true');
	});

	it('shows its line while it can run and while a reason lasts; a passing reason is hidden and its title; always the description', async () => {
		const held = heldWithGoalSeek();
		const ws = setup(twoCases(), held.solver);
		const group = await caseMenu();
		const line = (text: string, form: 'shown' | 'passing') => {
			const button = solveAllOf(group);
			const el = lineOf(button);
			expect(el, text).not.toBeNull();
			expect(words(el.textContent), text).toBe(text);
			expect(button, text).toHaveAccessibleDescription(text);
			if (form === 'shown') {
				expect(outOfSight(el), text).toBe(false);
				// 12 px slate-600: the utilities, or the `hint` class that applies them.
				const small =
					el.classList.contains('hint') ||
					['text-xs', 'text-slate-600'].every((c) => el.classList.contains(c));
				expect(small, `${text}: ${el.className}`).toBe(true);
				expect(button, text).toHaveAttribute('title', ALL_KEYS);
			} else {
				expect(el, text).toHaveClass('sr-only');
				expect(outOfSight(el), text).toBe(true);
				expect(button, text).toHaveAttribute('title', text);
			}
		};
		line(hint('2 solves'), 'shown');
		// A solve of the base case: passing.
		const base = ws.solve();
		await tick();
		line('A solve of Base case is running; Cancel in the header stops it.', 'passing');
		held.release();
		await base;
		await tick();
		line(hint('1 solve'), 'shown');
		// A solve of another case than the one shown: passing, named.
		ws.setCase('S1');
		const other = ws.solve();
		ws.setCase(null);
		await tick();
		line('A solve of Higher tank is running; Cancel in the header stops it.', 'passing');
		held.release();
		await other;
		await tick();
		line("Every case's results are current.", 'shown');
		// A goal seek: passing; cancelled, the lasting reason again.
		startGoalSeek(ws);
		await tick();
		line('A goal seek is running; Cancel in the header stops it.', 'passing');
		ws.store.cancelSolve();
		await tick();
		line("Every case's results are current.", 'shown');
		// Solve all running: passing.
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		const run = ws.solveAll();
		await tick();
		line('Solve all is running; Cancel in the header stops it.', 'passing');
		held.release();
		await vi.waitFor(() => expect(held.solve).toHaveBeenCalledTimes(4));
		held.release();
		await run;
	});

	it('shows the lasting reasons on screen: an error to fix first, an empty network', async () => {
		const ws = setup(twoCases([{ id: 'S1', name: 'Winter', overrides: [slower] }]), {
			solve: async (_p, _o, request) => {
				if (request?.scenarioId === 'S1') {
					throw new ValidationError(
						'Invalid input: 1 problem(s).',
						['body.project.scenarios.0.overrides.0: made-up rule'],
						400,
						'VALIDATION_ERROR'
					);
				}
				return response(pumpTransferSolved());
			}
		});
		await ws.solveAll();
		await tick();
		const group = await caseMenu();
		const button = solveAllOf(group);
		const text = 'Every case is solved except Winter, which has an error to fix first.';
		expect(button).toHaveAccessibleName('Solve all');
		expect(button).toHaveAccessibleDescription(text);
		expect(words(lineOf(button).textContent)).toBe(text);
		expect(outOfSight(lineOf(button))).toBe(false);
		document.body.innerHTML = '';
		setup(
			withScenarios(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }), [
				{ id: 'S1', name: 'Winter', overrides: [] }
			])
		);
		const empty = solveAllOf(await caseMenu());
		expect(empty).toHaveAccessibleName('Solve all');
		expect(empty).toHaveAttribute('aria-disabled', 'true');
		expect(empty).toHaveAccessibleDescription('Add a component to the network first.');
		expect(outOfSight(lineOf(empty))).toBe(false);
	});

	it('gives the focus on open to Solve all when it can run, else to the Case select', async () => {
		const ws = setup(twoCases(), solvesOk);
		await fireEvent.click(scenariosButton());
		const group = screen.getByRole('group', { name: 'Case' });
		await vi.waitFor(() => expect(document.activeElement).toBe(solveAllOf(group)));
		expect(solveAllOf(group)).not.toHaveAttribute('aria-disabled', 'true');
		await fireEvent.keyDown(group, { key: 'Escape' });
		expect(document.activeElement).toBe(scenariosButton());
		await ws.solveAll();
		await tick();
		await fireEvent.click(scenariosButton());
		const select = within(screen.getByRole('group', { name: 'Case' })).getByRole('combobox', {
			name: 'Case'
		});
		await vi.waitFor(() => expect(document.activeElement).toBe(select));
	});

	it('ignores a held Enter on Solve all: its repeated keydown is prevented, so no click follows', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		const button = solveAllOf(await caseMenu());
		button.focus();
		/** Enter's keydown on a focused button: a browser clicks it unless the keydown is prevented. */
		const enter = async (repeat: boolean) => {
			const proceed = await fireEvent.keyDown(button, { key: 'Enter', repeat });
			if (proceed) await fireEvent.click(button, { detail: 0 });
			return proceed;
		};
		// The Enter that opened the menu, held: its repeats reach Solve all.
		expect(await enter(true)).toBe(false);
		expect(held.solve).not.toHaveBeenCalled();
		expect(ws.store.run).toBeNull();
		// A press of its own runs it.
		expect(await enter(false)).toBe(true);
		expect(held.solve).toHaveBeenCalledTimes(1);
		expect(ws.store.run).not.toBeNull();
	});

	it('sits right after its button, both in one wrapper, before the Project toolbar', () => {
		setup(twoCases());
		const button = scenariosButton();
		const panel = menuPanel();
		const toolbar = screen.getByRole('toolbar', { name: 'Project' });
		expect(button.nextElementSibling).toBe(panel);
		expect(button.compareDocumentPosition(panel) & FOLLOWING).toBeTruthy();
		expect(panel.compareDocumentPosition(toolbar) & FOLLOWING).toBeTruthy();
		expect(panel.parentElement).toBe(button.parentElement);
		expect(panel.parentElement).toHaveClass('shrink-0', 'sm:relative');
	});

	it('closes when the focus leaves it and its button (to Undo); not on a focusout to nowhere or within', async () => {
		setup(twoCases());
		const group = await caseMenu();
		const button = solveAllOf(group);
		const open = () => expect(scenariosButton()).toHaveAttribute('aria-expanded', 'true');
		button.focus();
		// A window switch, or the panel hidden: no relatedTarget.
		await fireEvent.focusOut(button, { relatedTarget: null });
		open();
		expect(menuPanel()).not.toHaveAttribute('hidden');
		// Within the menu, and to its own button.
		within(group).getByRole('combobox', { name: 'Case' }).focus();
		await tick();
		open();
		scenariosButton().focus();
		await tick();
		open();
		button.focus();
		// Tab past it, or a press elsewhere that takes the focus.
		const undo = screen.getByRole('button', { name: 'Undo' });
		undo.focus();
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		expect(menuPanel()).toHaveAttribute('hidden');
		expect(document.activeElement).toBe(undo);
	});

	it('stays open after a pointer press on Cancel during a run, its line saying the run was cancelled', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		const group = await caseMenu();
		const button = solveAllOf(group);
		// As a browser does it: the press focuses the button pressed.
		button.focus();
		await fireEvent.click(button, { detail: 1 });
		expect(ws.store.run).not.toBeNull();
		const cancel = screen.getByRole('button', { name: 'Cancel solving all cases' });
		await fireEvent.pointerDown(cancel);
		cancel.focus();
		await fireEvent.click(cancel, { detail: 1 });
		await tick();
		expect(held.signals[0]?.aborted).toBe(true);
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'true');
		expect(menuPanel()).not.toHaveAttribute('hidden');
		const status = within(screen.getByRole('group', { name: 'Case' })).getByRole('status');
		expect(status).toHaveTextContent(
			/^Solve all was cancelled: the cases not solved keep what they had\.$/
		);
		expect(outOfSight(status)).toBe(false);
	});

	it('with the menu closed, the header says the progress, then the cancel line', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		void ws.solveAll();
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		// The closed menu's own line is hidden with it: the header's twin is the one live line.
		const twin = () => within(header()).getByRole('status');
		expect(twin()).toHaveClass('sr-only');
		expect(twin()).toHaveTextContent(/^Solving 1 of 2: Base case…$/);
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel solving all cases' }));
		await tick();
		expect(ws.store.run).toBeNull();
		expect(twin()).toHaveTextContent(
			/^Solve all was cancelled: the cases not solved keep what they had\.$/
		);
	});

	it('after a pointer Cancel the focus stays in the open menu, on Solve all: Escape closes it', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		const group = await caseMenu();
		const button = solveAllOf(group);
		button.focus();
		await fireEvent.click(button, { detail: 1 });
		expect(ws.store.run).not.toBeNull();
		// As Chromium does it: the press focuses Cancel, outside the menu, which stays open.
		const cancel = screen.getByRole('button', { name: 'Cancel solving all cases' });
		await fireEvent.pointerDown(cancel);
		cancel.focus();
		await fireEvent.click(cancel, { detail: 1 });
		await settled();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'true');
		// Cancel gone, the focus goes back into the menu it shows, to Solve all (which resumes
		// the run), not to the header's Solve under it: Escape and a Tab past it close it again
		// (WCAG 2.4.11).
		expect(document.activeElement).toBe(solveAllOf(group));
		await fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		expect(menuPanel()).toHaveAttribute('hidden');
		expect(document.activeElement).toBe(scenariosButton());
	});

	it('after a pointer Cancel of a single solve the focus stays in the open menu; leaving it closes it', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		const group = await caseMenu();
		solveAllOf(group).focus();
		// Ctrl/⌘+Enter with the focus in the menu: a solve of the case shown.
		void ws.solve();
		await tick();
		const cancel = screen.getByRole('button', { name: 'Cancel solve' });
		await fireEvent.pointerDown(cancel);
		cancel.focus();
		await fireEvent.click(cancel, { detail: 1 });
		await settled();
		expect(held.signals[0]?.aborted).toBe(true);
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'true');
		expect(document.activeElement).toBe(solveAllOf(group));
		// A Tab past it, to Share: closed.
		const share = within(header()).getByRole('button', { name: 'Share' });
		share.focus();
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		expect(document.activeElement).toBe(share);
	});

	it('closes on Escape with the focus on its button (Shift+Tab from Solve all)', async () => {
		setup(twoCases());
		const group = await caseMenu();
		await vi.waitFor(() => expect(document.activeElement).toBe(solveAllOf(group)));
		scenariosButton().focus();
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'true');
		await fireEvent.keyDown(scenariosButton(), { key: 'Escape' });
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		expect(menuPanel()).toHaveAttribute('hidden');
		expect(document.activeElement).toBe(scenariosButton());
	});

	it('closes when the focus leaves Cancel for the page, Cancel pressed but not clicked', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		const group = await caseMenu();
		solveAllOf(group).focus();
		await fireEvent.click(solveAllOf(group), { detail: 1 });
		expect(ws.store.run).not.toBeNull();
		// The press focuses Cancel and keeps the menu open; the pointer leaves before the click.
		const cancel = screen.getByRole('button', { name: 'Cancel solving all cases' });
		await fireEvent.pointerDown(cancel);
		cancel.focus();
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'true');
		// Tab from Cancel to Solve: the focus has left the menu, its button and Cancel.
		const solve = header().querySelector<HTMLElement>('[data-solve-button]')!;
		solve.focus();
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		expect(menuPanel()).toHaveAttribute('hidden');
		expect(ws.store.run).not.toBeNull();
	});

	it('the header says a cancel once: closing the menu after it does not say it again', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		void ws.solveAll();
		await tick();
		const twin = headerTwin;
		const said = sayings(twin());
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel solving all cases' }));
		await tick();
		expect(twin()).toHaveTextContent(CANCELLED);
		// Opened (its line says it) and closed, twice: the twin stays quiet.
		for (let i = 0; i < 2; i++) {
			await fireEvent.click(scenariosButton());
			await tick();
			expect(within(menuPanel()).getByRole('status')).toHaveTextContent(CANCELLED);
			await fireEvent.keyDown(menuPanel(), { key: 'Escape' });
			await tick();
			expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
			expect(words(twin().textContent), `close ${i + 1}`).toBe('');
		}
		await Promise.resolve();
		expect(said.filter((t) => t === CANCELLED_TEXT)).toHaveLength(1);
		said.stop();
	});

	it('the header says a cancel once: not again after a solve and a case chosen', async () => {
		const held = heldSolver();
		const ws = setup(twoCases(), held.solver);
		void ws.solveAll();
		await tick();
		const twin = headerTwin;
		const said = sayings(twin());
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel solving all cases' }));
		await tick();
		expect(twin()).toHaveTextContent(CANCELLED);
		// A solve of the case shown, with the menu never opened: the cancel is old news.
		const base = ws.solve();
		await tick();
		held.release();
		await base;
		await tick();
		expect(words(twin().textContent)).toBe('');
		// A case chosen from the menu, which closes it.
		const group = await caseMenu();
		await fireEvent.change(within(group).getByRole('combobox', { name: 'Case' }), {
			target: { value: 'S1' }
		});
		await tick();
		expect(ws.store.activeCase).toBe('S1');
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		expect(words(twin().textContent)).toBe('');
		await Promise.resolve();
		expect(said.filter((t) => t === CANCELLED_TEXT)).toHaveLength(1);
		said.stop();
	});

	it('a cancel made with the menu open is said by its line, not again by the header when it closes', async () => {
		const held = heldSolver();
		setup(twoCases(), held.solver);
		const group = await caseMenu();
		solveAllOf(group).focus();
		await fireEvent.click(solveAllOf(group), { detail: 1 });
		const twin = headerTwin;
		const said = sayings(twin());
		const cancel = screen.getByRole('button', { name: 'Cancel solving all cases' });
		await fireEvent.pointerDown(cancel);
		cancel.focus();
		await fireEvent.click(cancel, { detail: 1 });
		await settled();
		expect(within(group).getByRole('status')).toHaveTextContent(CANCELLED);
		await fireEvent.click(scenariosButton());
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'false');
		expect(words(twin().textContent)).toBe('');
		await Promise.resolve();
		expect(said).not.toContain(CANCELLED_TEXT);
		said.stop();
	});

	it('raises an alert when a network error stops Solve all with the menu closed, naming the cases left; none with it open', async () => {
		const ws = setup(
			twoCases([
				{ id: 'S1', name: 'Higher tank', overrides: [level6] },
				{ id: 'S2', name: 'Copy', overrides: [] }
			]),
			{
				solve: async (_p, _o, request) => {
					if (request?.scenarioId === 'S1')
						throw new NetworkError('The server is busy.', 503, 'SERVER_BUSY');
					return response(pumpTransferSolved());
				}
			}
		);
		await ws.solveAll();
		await tick();
		const text =
			'Solve all stopped after a network error: The server is busy. Solve all, in the Scenarios menu, solves the 2 cases left.';
		expect(ws.notice).toMatchObject({ kind: 'error', text });
		expect(screen.getByRole('alert')).toHaveTextContent(text);
		// The badge keeps that count.
		expect(scenariosButton()).toHaveAccessibleName('Scenarios (2), 2 cases to solve');
		ws.dismissNotice();
		await tick();
		// From the open menu: its line says it; no notice.
		const group = await caseMenu();
		await fireEvent.click(within(group).getByRole('button', { name: 'Solve all (2)' }));
		await vi.waitFor(() => expect(ws.store.runStop?.reason).toBe('network'));
		await tick();
		expect(scenariosButton()).toHaveAttribute('aria-expanded', 'true');
		expect(within(group).getByRole('status')).toHaveTextContent(
			'Solve all stopped after a network error: The server is busy.'
		);
		expect(ws.notice).toBeNull();
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('ends a message without a full stop with one, and names the one case left', async () => {
		const ws = setup(twoCases(), {
			solve: async (_p, _o, request) => {
				if (request?.scenarioId === 'S1')
					throw new NetworkError('No answer from the calculation server', 0);
				return response(pumpTransferSolved());
			}
		});
		await ws.solveAll();
		await tick();
		const text =
			'Solve all stopped after a network error: No answer from the calculation server. Solve all, in the Scenarios menu, solves the case left.';
		expect(ws.notice).toMatchObject({ kind: 'error', text });
		expect(screen.getByRole('alert')).toHaveTextContent(text);
		expect(scenariosButton()).toHaveAccessibleName('Scenarios (1), 1 case to solve');
	});

	/** S1's first solve fails at the network; every later one is answered. */
	function failsOnce(): Solver {
		let failed = false;
		return {
			solve: async (_p, _o, request) => {
				if (request?.scenarioId === 'S1' && !failed) {
					failed = true;
					throw new NetworkError('No answer from the calculation server', 0);
				}
				return response(pumpTransferSolved());
			}
		};
	}

	it('takes the alert away when Solve all resumes, by its keys or by the menu', async () => {
		for (const by of ['keys', 'menu'] as const) {
			document.body.innerHTML = '';
			const ws = setup(twoCases(), failsOnce());
			await ws.solveAll();
			await tick();
			expect(screen.getByRole('alert'), by).toHaveTextContent(/solves the case left\.$/);
			if (by === 'keys') {
				await ws.solveAll();
			} else {
				const group = await caseMenu();
				await fireEvent.click(within(group).getByRole('button', { name: 'Solve all (1)' }));
				await vi.waitFor(() => expect(ws.store.run).toBeNull());
			}
			await tick();
			expect(ws.store.casesToSolve(), by).toEqual([]);
			expect(scenariosButton(), by).toHaveAccessibleName('Scenarios (1)');
			expect(ws.notice, by).toBeNull();
			expect(screen.queryByRole('alert'), by).toBeNull();
		}
	});

	it('takes the alert away when Solve solves the cases it names; never another notice', async () => {
		const ws = setup(twoCases(), failsOnce());
		await ws.solveAll();
		await tick();
		expect(screen.getByRole('alert')).toHaveTextContent(/solves the case left\.$/);
		// The case left, solved by the header's Solve: nothing is left to solve.
		ws.setCase('S1');
		await ws.solve();
		await tick();
		expect(ws.store.casesToSolve()).toEqual([]);
		expect(ws.notice).toBeNull();
		expect(screen.queryByRole('alert')).toBeNull();
		// A notice of another kind shown in its place stays when Solve all runs again.
		document.body.innerHTML = '';
		const other = setup(twoCases(), failsOnce());
		await other.solveAll();
		await tick();
		other.notify('error', 'Could not rename the scenario: made-up problem.');
		await other.solveAll();
		await tick();
		expect(other.store.casesToSolve()).toEqual([]);
		expect(other.notice).toMatchObject({
			kind: 'error',
			text: 'Could not rename the scenario: made-up problem.'
		});
	});
});

describe('Compare cases names the Scenarios menu’s Solve all (build-density.md §19)', () => {
	it('has no Solve all; its amber line names the menu’s, plural then singular; the empty line alone', async () => {
		const ws = setup(twoCases(), solvesOk);
		// The Results tab shown (on a phone the pane is a tab; its words are read in sight).
		ws.pane = 'results';
		let compare = await openCompare();
		const solveAlls = () =>
			within(compare).queryAllByRole('button', { name: SOLVE_ALL, hidden: true });
		const amber = () =>
			[...compare.querySelectorAll('p')].find((p) =>
				/missing or out of date/.test(p.textContent ?? '')
			)!;
		expect(solveAlls()).toHaveLength(0);
		expect(words(amber().textContent)).toBe(
			'2 of 2 cases have results that are missing or out of date: Solve all, in the Scenarios menu at the top (Ctrl+Shift+Enter or ⌘+Shift+Enter), solves them one after another.'
		);
		// On a touch screen the shortcut is not drawn.
		expect(words(wordsInSight(amber()))).toBe(
			'2 of 2 cases have results that are missing or out of date: Solve all, in the Scenarios menu at the top, solves them one after another.'
		);
		// The menu named with the Scenarios button's own icon, in one unbroken span with its word.
		const named = [...amber().querySelectorAll('span')].find(
			(s) => s.textContent?.trim() === 'Scenarios'
		)!;
		expect(named).toHaveClass('whitespace-nowrap');
		expect(named.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
		expect(named.querySelector('svg')!.innerHTML).toBe(
			scenariosButton().querySelector(':scope > svg')!.innerHTML
		);
		// No results yet: the line alone (the amber line above says how), and no Solve all.
		expect(words(within(compare).getByText(/^No case has results yet/).textContent)).toBe(
			'No case has results yet.'
		);
		// The base solved: one case left, the singular.
		await ws.solve();
		await tick();
		compare = await openCompare();
		expect(solveAlls()).toHaveLength(0);
		expect(words(amber().textContent)).toBe(
			'1 of 2 cases has results that are missing or out of date: Solve all, in the Scenarios menu at the top (Ctrl+Shift+Enter or ⌘+Shift+Enter), solves it.'
		);
	});
});
