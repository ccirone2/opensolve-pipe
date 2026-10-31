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
	Override,
	Project,
	ScenarioResult,
	SolveResponse,
	SystemCurveResponse
} from '$lib/api/types';
import type { Solver } from '$lib/state/project.svelte';
import { pumpTransferSolved, response, systemCurveResponse } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { insertComponentInConnection, updateComponent } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';
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
		const button = within(bar).getByRole('button', { name: 'Solve all' });
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
		const results = screen.getByRole('region', { name: 'Results' });
		const button = within(results).getByRole('button', { name: `Solve ${name}` });
		const visible = [...button.childNodes]
			.filter((n) => !(n instanceof HTMLElement && n.classList.contains('sr-only')))
			.map((n) => n.textContent)
			.join('')
			.trim();
		expect(visible).toBe('Solve');
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
