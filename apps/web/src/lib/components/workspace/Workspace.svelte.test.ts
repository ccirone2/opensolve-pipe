/**
 * The workspace page structure: landmarks and headings, the Build / Results tabs on narrow
 * screens, the header's buttons that keep focus while unavailable, and Cancel while a solve runs.
 * The solve results are made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NetworkError, TopologyError, ValidationError } from '$lib/api/client';
import type {
	GoalSeekResponse,
	Project,
	PumpGroupCurveResponse,
	SolveResponse
} from '$lib/api/types';
import type { Workspace } from '$lib/state/workspace.svelte';
import { pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { pumpTransferExample } from '$lib/utils/examples';
import { createEmptyProject } from '$lib/utils/factory';
import { newGoal, newVariable, toRequest } from '$lib/utils/goal-seek';
import { withScenarios } from '$lib/utils/scenarios';
import WorkspaceView from './Workspace.svelte';

describe('workspace', () => {
	it('has one banner, a main landmark and the project name as its level 1 heading', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		// (A <header> inside an <article> is not a banner; the role query here does not know.)
		const banners = () =>
			screen.getAllByRole('banner', { hidden: true }).filter((el) => !el.closest('article'));
		expect(banners()).toHaveLength(1);
		const main = within(screen.getByRole('main'));
		expect(main.getByRole('heading', { level: 1 })).toHaveTextContent(
			'Pump transfer between two tanks'
		);
		expect(main.getByRole('tablist', { name: 'View' })).toBeInTheDocument();
		// Dialogs do not add a second banner.
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
		const dialog = await screen.findByRole('dialog', { name: 'Project settings' });
		expect(banners()).toHaveLength(1);
		expect(dialog.querySelector('header')).toBeNull();
	});

	it('switches between Build and Results with the arrow keys', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		const build = screen.getByRole('tab', { name: 'Build' });
		const results = screen.getByRole('tab', { name: 'Results' });
		expect(build).toHaveAttribute('tabindex', '0');
		expect(results).toHaveAttribute('tabindex', '-1');
		build.focus();
		await fireEvent.keyDown(build, { key: 'ArrowRight' });
		expect(ws.pane).toBe('results');
		expect(document.activeElement).toBe(results);
		expect(results).toHaveAttribute('tabindex', '0');
		await fireEvent.keyDown(results, { key: 'Home' });
		expect(ws.pane).toBe('build');
		expect(document.activeElement).toBe(build);
	});

	it('keeps Undo and Solve focusable when they are unavailable, and says why Solve is', async () => {
		render(WorkspaceView, {
			workspace: testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }))
		});
		const solve = screen.getByRole('button', { name: 'Solve' });
		expect(solve).not.toBeDisabled();
		expect(solve).toHaveAttribute('aria-disabled', 'true');
		expect(solve).toHaveAccessibleDescription('Add a component to the network first.');
		const undo = screen.getByRole('button', { name: 'Undo' });
		expect(undo).toHaveAttribute('aria-disabled', 'true');
		undo.focus();
		await fireEvent.click(undo);
		expect(document.activeElement).toBe(undo);
		expect(screen.getByText(/Add a component in Build to start the network/)).toBeInTheDocument();
	});

	it('offers Scenarios and Goal seek once the network has a component', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		expect(screen.queryByRole('button', { name: 'Scenarios' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Goal seek' })).toBeNull();
		ws.addStandalone('reservoir');
		await tick();
		expect(screen.getByRole('button', { name: 'Scenarios' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Goal seek' })).toBeInTheDocument();
	});

	it('names the fluid in the header and opens its settings on the Fluid section', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		const chip = screen.getByRole('button', { name: 'Fluid: Water · 20 °C' });
		await fireEvent.click(chip);
		const dialog = await screen.findByRole('dialog', { name: 'Project settings' });
		await tick();
		await tick();
		const fluid = within(dialog).getByRole('region', { name: 'Fluid' });
		expect(fluid.contains(document.activeElement)).toBe(true);
	});

	it('solves with Ctrl/⌘+Enter, also from a field, but not from inside a dialog', async () => {
		const solveFn = vi.fn(() => Promise.resolve(response(pumpTransferSolved())));
		const ws = testWorkspace(pumpTransferExample(), { solver: { solve: solveFn } });
		render(WorkspaceView, { workspace: ws });
		const solveButton = screen.getByRole('button', { name: 'Solve' });
		expect(solveButton).toHaveAttribute('aria-keyshortcuts', 'Control+Enter Meta+Enter');
		await fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true });
		expect(solveFn).toHaveBeenCalledTimes(1);
		await tick();
		// From a number field: its Enter stores the typed value, then the solve sends it.
		ws.pane = 'build';
		await tick();
		const level = screen.getByRole('textbox', { name: /^Liquid level/ });
		await fireEvent.input(level, { target: { value: '4' } });
		await fireEvent.keyDown(level, { key: 'Enter', metaKey: true });
		expect(solveFn).toHaveBeenCalledTimes(2);
		const sent = (solveFn.mock.calls[1] as unknown as [Project])[0];
		expect(sent.components.find((c) => c.id === 'R1')).toMatchObject({ liquidLevel: 4 });
		// Inside a dialog the keys belong to the dialog: not solved, nothing said, with the results
		// out of date (current, they would not solve anywhere: the owner, 2026-11-27).
		await vi.waitFor(() => expect(ws.store.results.response).not.toBeNull());
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change length');
		expect(ws.store.results.stale).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
		const dialog = await screen.findByRole('dialog', { name: 'Project settings' });
		await fireEvent.keyDown(within(dialog).getByRole('button', { name: 'Done' }), {
			key: 'Enter',
			ctrlKey: true
		});
		expect(solveFn).toHaveBeenCalledTimes(2);
		expect(ws.notice).toBeNull();
	});
});

describe('the splitter between Build and Results', () => {
	it('resizes with the arrow keys, Home and End, remembers it, and Enter restores the default', async () => {
		localStorage.clear();
		const view = render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		const splitter = screen.getByRole('separator', { name: 'Resize Build and Results' });
		expect(splitter).toHaveAttribute('tabindex', '0');
		expect(splitter).toHaveAttribute('aria-orientation', 'vertical');
		expect(splitter).toHaveAttribute('aria-valuenow', '60');
		expect(splitter).toHaveAttribute('aria-valuetext', 'Build 60 %, Results 40 %');
		await fireEvent.keyDown(splitter, { key: 'ArrowLeft' });
		expect(splitter).toHaveAttribute('aria-valuenow', '55');
		expect(localStorage.getItem('opensolve-pipe:results-share')).toBe('0.45');
		await fireEvent.keyDown(splitter, { key: 'Home' });
		expect(splitter).toHaveAttribute('aria-valuenow', '25');
		await fireEvent.keyDown(splitter, { key: 'End' });
		expect(splitter).toHaveAttribute('aria-valuenow', '75');
		await fireEvent.keyDown(splitter, { key: 'ArrowRight' });
		expect(splitter).toHaveAttribute('aria-valuenow', '75');
		view.unmount();

		// Remembered for the next workspace in this browser.
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		const again = screen.getByRole('separator', { name: 'Resize Build and Results' });
		expect(again).toHaveAttribute('aria-valuenow', '75');
		await fireEvent.keyDown(again, { key: 'Enter' });
		expect(again).toHaveAttribute('aria-valuenow', '60');
		expect(localStorage.getItem('opensolve-pipe:results-share')).toBeNull();
	});
});

describe('cancelling a solve (PRD §4.2)', () => {
	/** A solve endpoint whose answers the test gives, recording each request's signal. */
	function heldSolve() {
		const signals: (AbortSignal | undefined)[] = [];
		const answers: ((answer: SolveResponse) => void)[] = [];
		const solve = vi.fn(
			(_project: Project, _options?: unknown, request?: { signal?: AbortSignal }) => {
				signals.push(request?.signal);
				return new Promise<SolveResponse>((resolve) => answers.push(resolve));
			}
		);
		return { solve, signals, answers };
	}

	const results = () => within(screen.getByRole('region', { name: 'Results' }));

	it('shows Cancel while a solve runs; it aborts the solve, says so, and Solve takes the focus', async () => {
		const { solve, signals, answers } = heldSolve();
		const ws = testWorkspace(pumpTransferExample(), { solver: { solve } });
		render(WorkspaceView, { workspace: ws });
		expect(screen.queryByRole('button', { name: 'Cancel solve' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		expect(screen.getByRole('button', { name: 'Solving…' })).toHaveAttribute(
			'aria-disabled',
			'true'
		);
		expect(results().getByRole('status')).toHaveTextContent(/^Solving…$/);
		const cancel = screen.getByRole('button', { name: 'Cancel solve' });
		// Inside the Project toolbar, right before Solve (so that Solve keeps its place).
		expect(cancel.closest('[role="toolbar"]')).toHaveAccessibleName('Project');
		expect(cancel.nextElementSibling).toHaveAccessibleName('Solving…');
		// A keyboard user presses it.
		cancel.focus();
		await fireEvent.click(cancel);
		await tick();
		expect(signals[0]?.aborted).toBe(true);
		expect(screen.queryByRole('button', { name: 'Cancel solve' })).toBeNull();
		const solveButton = screen.getByRole('button', { name: 'Solve' });
		expect(document.activeElement).toBe(solveButton);
		expect(solveButton).toHaveAttribute('aria-disabled', 'false');
		// Said in the live status line, and in the pane.
		expect(results().getByRole('status')).toHaveTextContent(/^Solve cancelled$/);
		expect(
			results().getByText(
				'The solve was cancelled before it finished, so there are no results yet.'
			)
		).toBeInTheDocument();
		// Its answer arrives anyway: it is dropped.
		answers[0]!(response(pumpTransferSolved()));
		await tick();
		expect(ws.store.results.response).toBeNull();
		expect(results().queryByRole('heading', { name: 'Converged' })).toBeNull();
		// Solving again works, and the note goes.
		await fireEvent.click(solveButton);
		expect(results().queryByText(/The solve was cancelled/)).toBeNull();
		answers[1]!(response(pumpTransferSolved()));
		expect(await results().findByRole('heading', { name: 'Converged' })).toBeInTheDocument();
		expect(results().getByRole('status')).toHaveTextContent(/^Last solve: converged$/);
		expect(signals[1]?.aborted).toBe(false);
	});

	it('ignores the second click of a double click on Solve and on Cancel, not a keyboard press', async () => {
		const { solve, signals } = heldSolve();
		render(WorkspaceView, {
			workspace: testWorkspace(pumpTransferExample(), { solver: { solve } })
		});
		const solveButton = screen.getByRole('button', { name: 'Solve' });
		await fireEvent.click(solveButton, { detail: 1 });
		expect(signals).toHaveLength(1);
		// Cancel comes in before Solve, which stays the same button in the same place.
		const cancel = screen.getByRole('button', { name: 'Cancel solve' });
		expect(cancel.nextElementSibling).toBe(solveButton);
		expect(solveButton).toHaveAccessibleName('Solving…');
		// A double click's second click (detail 2) does nothing, on Cancel as on Solve.
		await fireEvent.click(cancel, { detail: 2 });
		expect(signals[0]?.aborted).toBe(false);
		await fireEvent.click(cancel, { detail: 1 });
		expect(signals[0]?.aborted).toBe(true);
		expect(solveButton).toHaveAccessibleName('Solve');
		await fireEvent.click(solveButton, { detail: 2 });
		expect(signals).toHaveLength(1);
		// A keyboard press (detail 0) solves.
		await fireEvent.click(solveButton, { detail: 0 });
		expect(signals).toHaveLength(2);
		expect(signals[1]?.aborted).toBe(false);
	});

	it('gives Solve the focus when the solve answers while Cancel has it', async () => {
		const { solve, answers } = heldSolve();
		render(WorkspaceView, {
			workspace: testWorkspace(pumpTransferExample(), { solver: { solve } })
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		screen.getByRole('button', { name: 'Cancel solve' }).focus();
		answers[0]!(response(pumpTransferSolved()));
		await results().findByRole('heading', { name: 'Converged' });
		await tick();
		expect(screen.queryByRole('button', { name: 'Cancel solve' })).toBeNull();
		expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Solve' }));
	});

	it('leaves the focus where it is when Cancel did not have it', async () => {
		const { solve, answers } = heldSolve();
		render(WorkspaceView, {
			workspace: testWorkspace(pumpTransferExample(), { solver: { solve } })
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		const name = screen.getByRole('textbox', { name: 'Project name' });
		name.focus();
		answers[0]!(response(pumpTransferSolved()));
		await results().findByRole('heading', { name: 'Converged' });
		await tick();
		expect(document.activeElement).toBe(name);
	});
});

describe('Ctrl/⌘+Shift+Enter: Solve all (build-density.md §19)', () => {
	/** The transfer example with two scenarios that change nothing (made-up names). */
	const withCases = () =>
		withScenarios(pumpTransferExample(), [
			{ id: 'S1', name: 'Winter', overrides: [] },
			{ id: 'S2', name: 'Summer', overrides: [] }
		]);
	/** A solver recording each request's case; held until `release()` when `hold` is set. */
	function recordingSolver(hold = false) {
		const cases: (string | null)[] = [];
		const sent: Project[] = [];
		const answers: (() => void)[] = [];
		const solve = vi.fn((project: Project, _o?: unknown, request?: { scenarioId?: string }) => {
			cases.push(request?.scenarioId ?? null);
			sent.push(project);
			const answer = response(pumpTransferSolved());
			return hold
				? new Promise<SolveResponse>((resolve) => answers.push(() => resolve(answer)))
				: Promise.resolve(answer);
		});
		const goalSeek = () => new Promise<GoalSeekResponse>(() => {});
		return { solver: { solve, goalSeek }, solve, cases, sent, release: () => answers.shift()?.() };
	}
	const keys = { key: 'Enter', ctrlKey: true, shiftKey: true };
	const metaKeys = { key: 'Enter', metaKey: true, shiftKey: true };
	const longer = (ws: Workspace) =>
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change length');

	it('runs Solve all from a Build field, in casesToSolve() order; Ctrl+Enter still solves the case shown; not inside a dialog', async () => {
		const rec = recordingSolver();
		const ws = testWorkspace(withCases(), { solver: rec.solver });
		render(WorkspaceView, { workspace: ws });
		// Ctrl+Enter, unchanged: the case shown only.
		await fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true });
		await vi.waitFor(() => expect(rec.cases).toEqual([null]));
		expect(ws.store.run).toBeNull();
		// From a number field: its Enter stores the typed value whatever the modifiers, then Solve
		// all sends it, every case whose results are missing or out of date, in order.
		ws.pane = 'build';
		await tick();
		const level = screen.getByRole('textbox', { name: /^Liquid level/ });
		await fireEvent.input(level, { target: { value: '4' } });
		expect(ws.store.casesToSolve()).toEqual(['S1', 'S2']);
		await fireEvent.keyDown(level, keys);
		// The stored value put the base case out of date: it is solved again, first.
		await vi.waitFor(() => expect(rec.cases).toEqual([null, null, 'S1', 'S2']));
		for (const sent of rec.sent.slice(1)) {
			expect(sent.components.find((c) => c.id === 'R1')).toMatchObject({ liquidLevel: 4 });
		}
		// On a phone the results show.
		expect(ws.pane).toBe('results');
		await vi.waitFor(() => expect(ws.store.run).toBeNull());
		// ⌘+Shift+Enter, from the field again.
		ws.pane = 'build';
		await tick();
		const again = screen.getByRole('textbox', { name: /^Liquid level/ });
		await fireEvent.input(again, { target: { value: '5' } });
		await fireEvent.keyDown(again, metaKeys);
		await vi.waitFor(() => expect(rec.cases.slice(4)).toEqual([null, 'S1', 'S2']));
		for (const sent of rec.sent.slice(4)) {
			expect(sent.components.find((c) => c.id === 'R1')).toMatchObject({ liquidLevel: 5 });
		}
		await vi.waitFor(() => expect(ws.store.run).toBeNull());
		// From outside a field too, and handled: the browser's own use of the keys is prevented.
		longer(ws);
		expect(await fireEvent.keyDown(window, metaKeys)).toBe(false);
		await vi.waitFor(() => expect(rec.cases.slice(7)).toEqual([null, 'S1', 'S2']));
		await vi.waitFor(() => expect(ws.store.run).toBeNull());
		// Inside a dialog the keys belong to the dialog: not handled, not prevented.
		longer(ws);
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
		const dialog = await screen.findByRole('dialog', { name: 'Project settings' });
		expect(
			await fireEvent.keyDown(within(dialog).getByRole('button', { name: 'Done' }), keys)
		).toBe(true);
		await tick();
		expect(rec.cases).toHaveLength(10);
		expect(ws.store.run).toBeNull();
	});

	it('starts one run for a held key: its repeats are prevented and ignored, before and after the run ends', async () => {
		const rec = recordingSolver(true);
		const ws = testWorkspace(withCases(), { solver: rec.solver });
		render(WorkspaceView, { workspace: ws });
		expect(await fireEvent.keyDown(window, keys)).toBe(false);
		await tick();
		expect(ws.store.run).not.toBeNull();
		expect(rec.solve).toHaveBeenCalledTimes(1);
		for (let i = 0; i < 3; i++) {
			expect(await fireEvent.keyDown(window, { ...keys, repeat: true })).toBe(false);
		}
		// Ignored, not refused: no notice says Solve all is running.
		expect(ws.notice).toBeNull();
		rec.release();
		await vi.waitFor(() => expect(rec.solve).toHaveBeenCalledTimes(2));
		rec.release();
		await vi.waitFor(() => expect(rec.solve).toHaveBeenCalledTimes(3));
		rec.release();
		await vi.waitFor(() => expect(ws.store.run).toBeNull());
		// Still held after the run, with cases out of date again: nothing starts, nothing is said.
		longer(ws);
		expect(await fireEvent.keyDown(window, { ...keys, repeat: true })).toBe(false);
		await tick();
		expect(ws.store.run).toBeNull();
		expect(rec.solve).toHaveBeenCalledTimes(3);
		expect(ws.notice).toBeNull();
	});

	it('says why when it cannot run (current, running, a goal seek) and sends nothing; without scenarios the keys are not handled', async () => {
		const rec = recordingSolver(true);
		const ws = testWorkspace(withCases(), { solver: rec.solver });
		const view = render(WorkspaceView, { workspace: ws });
		// Solve all running.
		const run = ws.solveAll();
		await tick();
		expect(await fireEvent.keyDown(window, keys)).toBe(false);
		expect(ws.notice).toMatchObject({
			kind: 'info',
			text: 'Solve all is running; Cancel in the header stops it.'
		});
		expect(rec.solve).toHaveBeenCalledTimes(1);
		for (let n = 1; n <= 3; n++) {
			await vi.waitFor(() => expect(rec.solve).toHaveBeenCalledTimes(n));
			rec.release();
		}
		await run;
		ws.dismissNotice();
		// Every case current.
		expect(await fireEvent.keyDown(window, keys)).toBe(false);
		expect(ws.notice).toMatchObject({ kind: 'info', text: "Every case's results are current." });
		expect(rec.solve).toHaveBeenCalledTimes(3);
		ws.dismissNotice();
		// A goal seek running (one request at a time).
		longer(ws);
		const project = ws.store.project;
		void ws.store.runGoalSeek(
			toRequest(
				{
					goals: [{ ...newGoal({ elementId: 'L2' }, 'link_flow'), target: 0.015 }],
					variables: [
						newVariable(project, {
							target: { kind: 'component', componentId: 'P1' },
							field: 'speed'
						})
					]
				},
				project,
				null
			)
		);
		await tick();
		expect(ws.store.calculating).toBe('goalSeek');
		expect(await fireEvent.keyDown(window, metaKeys)).toBe(false);
		expect(ws.notice).toMatchObject({
			kind: 'info',
			text: 'A goal seek is running; Cancel in the header stops it.'
		});
		expect(rec.solve).toHaveBeenCalledTimes(3);
		view.unmount();
		// Without scenarios: not Solve all's keys; nothing prevented, sent or said.
		const plain = recordingSolver();
		const single = testWorkspace(pumpTransferExample(), { solver: plain.solver });
		render(WorkspaceView, { workspace: single });
		expect(await fireEvent.keyDown(window, keys)).toBe(true);
		await tick();
		expect(plain.solve).not.toHaveBeenCalled();
		expect(single.notice).toBeNull();
	});
});

describe("the owner's rule: one Solve, one Solve all, at the top (build-density.md §19)", () => {
	/** Solve, Solve {case}, Solve now and Solve again. */
	const SOLVE_ONE = /^Solve($| (?!all\b))/;
	const SOLVE_ALL = /^Solve all( \(\d+\))?$/;
	/** Buttons in the accessibility tree outside a dialog: a closed menu's are hidden with it. */
	const outside = (name: RegExp) =>
		screen.queryAllByRole('button', { name }).filter((b) => !b.closest('dialog'));
	const named = (buttons: HTMLElement[]) =>
		buttons.map((b) => b.getAttribute('aria-label') ?? b.textContent?.replace(/\s+/g, ' ').trim());

	/** One Solve, the header's; no Solve all with the menu closed, one (the menu's) with it open. */
	async function oneOfEach(what: string, scenarios = true) {
		const solves = outside(SOLVE_ONE);
		expect(named(solves), what).toHaveLength(1);
		expect(solves[0], what).toHaveAttribute('data-solve-button');
		expect(named(outside(SOLVE_ALL)), `${what}, the menu closed`).toEqual([]);
		if (!scenarios) return;
		await fireEvent.click(screen.getByRole('button', { name: /^Scenarios/ }));
		const group = screen.getByRole('group', { name: 'Case' });
		const all = outside(SOLVE_ALL);
		expect(named(all), `${what}, the menu open`).toHaveLength(1);
		expect(group.contains(all[0]!), what).toBe(true);
		expect(named(outside(SOLVE_ONE)), `${what}, the menu open`).toHaveLength(1);
		await fireEvent.keyDown(group, { key: 'Escape' });
		expect(named(outside(SOLVE_ALL)), `${what}, the menu closed again`).toEqual([]);
	}

	const withCases = () =>
		withScenarios(pumpTransferExample(), [
			{ id: 'S1', name: 'Winter', overrides: [] },
			{ id: 'S2', name: 'Summer', overrides: [] }
		]);
	const longer = (ws: Workspace) =>
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change length');
	/** A solver answering, failing with a network error, or holding, as the test sets it. */
	function programmedSolver() {
		let mode: 'ok' | 'network' | 'hold' = 'ok';
		const solve = vi.fn(() =>
			mode === 'network'
				? Promise.reject(new NetworkError('The calculation server could not be reached.', 0))
				: mode === 'hold'
					? new Promise<SolveResponse>(() => {})
					: Promise.resolve(response(pumpTransferSolved()))
		);
		return { solver: { solve }, set: (next: typeof mode) => (mode = next) };
	}
	function screenWidth(wide: boolean) {
		vi.stubGlobal('matchMedia', (query: string) => ({
			matches: wide,
			media: query,
			onchange: null,
			addEventListener() {},
			removeEventListener() {},
			addListener() {},
			removeListener() {},
			dispatchEvent: () => false
		}));
	}
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('holds in each Results state of a project with scenarios', async () => {
		const s = programmedSolver();
		const ws = testWorkspace(withCases(), { solver: s.solver });
		render(WorkspaceView, { workspace: ws });
		await oneOfEach('unsolved, on the Base case tab');
		await fireEvent.click(screen.getByRole('tab', { name: 'Compare cases' }));
		await oneOfEach('unsolved, on Compare cases');
		await fireEvent.click(screen.getByRole('tab', { name: 'Base case' }));
		// Cancelled.
		s.set('hold');
		void ws.solve();
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel solve' }));
		expect(ws.store.results.cancelled).toBe(true);
		await oneOfEach('cancelled');
		// After one solve.
		s.set('ok');
		await ws.solve();
		await tick();
		await oneOfEach('after one solve');
		// Out of date.
		longer(ws);
		await tick();
		expect(ws.store.results.stale).toBe(true);
		await oneOfEach('out of date');
		// Failed by network, the earlier response kept.
		await ws.solve();
		s.set('network');
		await ws.solve();
		await tick();
		expect(ws.store.results.error?.kind).toBe('network');
		expect(ws.store.results.response).not.toBeNull();
		await oneOfEach('failed by network, the earlier results kept');
	}, 20_000);

	it('holds with the side-panel trace open (from 1024 px)', async () => {
		screenWidth(true);
		const ws = testWorkspace(withCases(), {
			solver: { solve: async () => response(pumpTransferSolved()) }
		});
		render(WorkspaceView, { workspace: ws });
		await ws.solveAll();
		longer(ws);
		ws.inspect({ kind: 'component', id: 'P1' });
		const panel = await screen.findByRole('region', { name: 'Transfer pump' });
		expect(panel).toHaveTextContent(/Results are out of date/);
		await oneOfEach('the side-panel trace open, out of date');
	});

	it('holds on the Pumps together card: before Add, after Add, at gate 4', async () => {
		interface FixtureCase {
			name: string;
			project: Project;
			solve: SolveResponse;
			groupCurve: { body: unknown };
			systemCurve: { body: unknown } | null;
			scenarioCases: Record<
				string,
				{
					solve: SolveResponse;
					groupCurve: { body: unknown };
					systemCurve: { body: unknown } | null;
				}
			>;
		}
		const lineups = (fixture.cases as unknown as FixtureCase[]).find((c) => c.name === 'lineups')!;
		const answers = (id: string | undefined) => (id && lineups.scenarioCases[id]) || lineups;
		const groupCalls: (string | null)[] = [];
		const ws = testWorkspace(
			// One scenario that is no lineup (Delivery tank 5 m higher), so the Scenarios menu is there.
			withScenarios(structuredClone(lineups.project), [lineups.project.scenarios![7]!]),
			{
				solver: {
					solve: async (_p, _o, request) => structuredClone(answers(request?.scenarioId).solve),
					groupCurve: async (_p, _ids, request) => {
						groupCalls.push(request?.scenarioId ?? null);
						const answer = answers(request?.scenarioId);
						const sent = request?.curve === 'system' ? answer.systemCurve! : answer.groupCurve;
						return structuredClone(sent.body as PumpGroupCurveResponse);
					}
				}
			}
		);
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		const results = within(screen.getByRole('region', { name: 'Results' }));
		await fireEvent.click(results.getByRole('tab', { name: 'Pumps' }));
		const card = () => results.getByRole('region', { name: /^Pumps together/ });
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await vi.waitFor(() => expect(groupCalls.filter((c) => c === null)).toHaveLength(2));
		const block = () => within(card()).getByRole('region', { name: 'Add cases' });
		await oneOfEach('the Pumps card, before Add');
		await fireEvent.click(within(block()).getByRole('button', { name: 'Add 3 cases' }));
		await tick();
		expect(ws.scenarios).toHaveLength(4);
		await oneOfEach('the Pumps card, after Add');
		// Gate 4: the base case's results out of date.
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change length');
		await tick();
		expect(block()).toHaveTextContent(/^Add cases.*The base case's results are out of date/);
		await oneOfEach('the Pumps card at gate 4');
	}, 20_000);

	it('holds on a link opened without results, without scenarios: one Solve', async () => {
		render(WorkspaceView, {
			workspace: testWorkspace({ ...pumpTransferExample(), methodVersion: '1.0.0' })
		});
		expect(screen.getByText(/^This project was opened without results/)).toBeInTheDocument();
		await oneOfEach('a link opened without results', false);
	});
});

describe('Solve while the results shown are current (the owner, 2026-11-27)', () => {
	/** The reason, Solve's description and title while the results shown are current. */
	const CURRENT = 'The results are current; solve again after an edit that can change them.';
	/** The reason while the last solve of the project as it is failed with its own error. */
	const ERROR =
		'The last solve failed with an error to fix first; solve again after an edit that can fix it.';
	const TITLE = 'Solve (Ctrl+Enter or ⌘+Enter)';
	const solveButton = () => document.querySelector<HTMLButtonElement>('[data-solve-button]')!;
	/** Unavailable as Solve all is while every case is current: aria-disabled, focusable, said. */
	function unavailable(what: string, reason = CURRENT) {
		const solve = solveButton();
		expect(solve, what).toHaveAttribute('aria-disabled', 'true');
		expect(solve, what).not.toBeDisabled();
		expect(solve, what).toHaveAccessibleDescription(reason);
		expect(solve, what).toHaveAttribute('title', reason);
	}
	function available(what: string) {
		const solve = solveButton();
		expect(solve, what).toHaveAttribute('aria-disabled', 'false');
		expect(solve, what).not.toHaveAttribute('aria-describedby');
		expect(solve, what).toHaveAttribute('title', TITLE);
	}
	const longer = (ws: Workspace) =>
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change length');
	/** A solver answering, failing (each kind of error), or holding, as the test sets it. */
	function programmedSolver() {
		let mode: 'ok' | 'network' | 'topology' | 'validation' | 'hold' = 'ok';
		const signals: (AbortSignal | undefined)[] = [];
		const solve = vi.fn(
			(_project: Project, _options?: unknown, request?: { signal?: AbortSignal }) => {
				signals.push(request?.signal);
				switch (mode) {
					case 'network':
						return Promise.reject(
							new NetworkError('The calculation server could not be reached.', 0)
						);
					case 'topology':
						return Promise.reject(new TopologyError('The network has a problem.', []));
					case 'validation':
						return Promise.reject(new ValidationError('A value is out of range.', [], 400));
					case 'hold':
						return new Promise<SolveResponse>(() => {});
					default:
						return Promise.resolve(response(pumpTransferSolved()));
				}
			}
		);
		return { solver: { solve }, solve, signals, set: (next: typeof mode) => (mode = next) };
	}

	it('is unavailable after a solve, focusable, with its reason; an edit that can change the results makes it available; an undo back to the project solved does not', async () => {
		const s = programmedSolver();
		const ws = testWorkspace(pumpTransferExample(), { solver: s.solver });
		render(WorkspaceView, { workspace: ws });
		available('not solved');
		await fireEvent.click(solveButton());
		await vi.waitFor(() => expect(ws.store.results.response).not.toBeNull());
		await tick();
		unavailable('after a solve');
		expect(solveButton()).toHaveAccessibleName('Solve');
		expect(solveButton()).toHaveAttribute('aria-keyshortcuts', 'Control+Enter Meta+Enter');
		// The focus stays on it; a press, by pointer or key, sends nothing.
		solveButton().focus();
		await fireEvent.click(solveButton(), { detail: 1 });
		await fireEvent.click(solveButton(), { detail: 0 });
		await tick();
		expect(s.solve).toHaveBeenCalledTimes(1);
		expect(document.activeElement).toBe(solveButton());
		// A rename cannot change the results: still current.
		ws.edit((p) => {
			p.metadata.name = 'Renamed transfer';
		}, 'rename project');
		await tick();
		expect(ws.store.results.stale).toBe(false);
		unavailable('after a rename');
		// An edit that can: out of date, Solve available.
		longer(ws);
		await tick();
		expect(ws.store.results.stale).toBe(true);
		available('out of date');
		// Undone to the project solved: its results are current again.
		ws.undo();
		await tick();
		expect(ws.store.results.stale).toBe(false);
		unavailable('undone to the project solved');
		ws.redo();
		await tick();
		available('redone');
		await fireEvent.click(solveButton());
		await vi.waitFor(() => expect(s.solve).toHaveBeenCalledTimes(2));
		await vi.waitFor(() => expect(ws.store.results.stale).toBe(false));
		await tick();
		unavailable('solved again');
	});

	it('a press on it while it waits, by pointer, touch or key, says why in a notice and sends nothing; the second click of a double click says nothing more', async () => {
		const s = programmedSolver();
		const ws = testWorkspace(pumpTransferExample(), { solver: s.solver });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(solveButton());
		await vi.waitFor(() => expect(ws.store.results.response).not.toBeNull());
		await tick();
		unavailable('after a solve');
		expect(ws.notice).toBeNull();
		// A pointer or touch press (detail 1) and a key's (detail 0): each says why, as Ctrl/⌘+Enter
		// does, since a touch screen shows no title.
		for (const detail of [1, 0]) {
			ws.dismissNotice();
			await fireEvent.click(solveButton(), { detail });
			expect(ws.notice, `a click with detail ${detail}`).toMatchObject({
				kind: 'info',
				text: CURRENT
			});
		}
		const said = ws.notice!.id;
		await fireEvent.click(solveButton(), { detail: 2 });
		expect(ws.notice!.id, 'the second click of a double click').toBe(said);
		expect(s.solve).toHaveBeenCalledTimes(1);
		// A calculation running: its spinner and Cancel say it; a press says nothing more, as before.
		ws.dismissNotice();
		longer(ws);
		s.set('hold');
		await fireEvent.click(solveButton());
		expect(s.solve).toHaveBeenCalledTimes(2);
		await fireEvent.click(solveButton(), { detail: 1 });
		expect(ws.notice, 'a press while a solve runs').toBeNull();
		expect(s.solve).toHaveBeenCalledTimes(2);
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel solve' }));
	});

	it('an empty network: a press says nothing, as before (its reason is with it, and Build says it)', async () => {
		const s = programmedSolver();
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }), {
			solver: s.solver
		});
		render(WorkspaceView, { workspace: ws });
		expect(solveButton()).toHaveAttribute('aria-disabled', 'true');
		expect(solveButton()).toHaveAccessibleDescription('Add a component to the network first.');
		await fireEvent.click(solveButton(), { detail: 1 });
		await fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true });
		expect(ws.notice).toBeNull();
		expect(s.solve).not.toHaveBeenCalled();
	});

	it("after a failed solve: available after a network error or a cancel; unavailable after the project's own error, as Solve all, until an edit that can fix it; available with this project's earlier results kept", async () => {
		const s = programmedSolver();
		const ws = testWorkspace(pumpTransferExample(), { solver: s.solver });
		render(WorkspaceView, { workspace: ws });
		// No results yet. A network error: available, a press retries.
		let calls = 0;
		s.set('network');
		await fireEvent.click(solveButton());
		calls++;
		await vi.waitFor(() => expect(ws.store.results.error?.kind).toBe('network'));
		await tick();
		expect(ws.store.results.response).toBeNull();
		available('a network error, no results');
		// The project's own error: the same project gives it again, so Solve waits, as Solve all
		// skips the case, its reason with it and said by a press and the keys, nothing sent. A rename
		// cannot fix it; an edit that can makes it available; an undo back waits again.
		for (const kind of ['topology', 'validation'] as const) {
			s.set(kind);
			await fireEvent.click(solveButton());
			calls++;
			await vi.waitFor(() => expect(ws.store.results.error?.kind).toBe(kind));
			await tick();
			expect(s.solve).toHaveBeenCalledTimes(calls);
			expect(ws.store.results.response).toBeNull();
			unavailable(`a ${kind} error, no results`, ERROR);
			ws.dismissNotice();
			await fireEvent.click(solveButton(), { detail: 1 });
			expect(ws.notice, `a press, a ${kind} error`).toMatchObject({ kind: 'info', text: ERROR });
			ws.dismissNotice();
			expect(await fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })).toBe(false);
			expect(ws.notice, `Ctrl+Enter, a ${kind} error`).toMatchObject({
				kind: 'info',
				text: ERROR
			});
			expect(s.solve).toHaveBeenCalledTimes(calls);
			ws.edit((p) => {
				p.metadata.name = `Renamed after a ${kind} error`;
			}, 'rename project');
			await tick();
			unavailable(`a ${kind} error, renamed`, ERROR);
			longer(ws);
			await tick();
			available(`a ${kind} error, an edit since`);
			ws.undo();
			await tick();
			unavailable(`a ${kind} error, undone to the project that failed`, ERROR);
			longer(ws);
			await tick();
		}
		s.set('hold');
		await fireEvent.click(solveButton());
		calls++;
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel solve' }));
		await tick();
		expect(ws.store.results.cancelled).toBe(true);
		available('cancelled, no results');
		// Solved; then the same project's solve fails (started by the store: Solve is unavailable),
		// the earlier results kept: the latest solve failed, so a retry is offered.
		s.set('ok');
		await fireEvent.click(solveButton());
		calls++;
		await vi.waitFor(() => expect(ws.store.results.response).not.toBeNull());
		await tick();
		unavailable('solved');
		for (const kind of ['network', 'topology', 'validation'] as const) {
			s.set(kind);
			await ws.solve();
			calls++;
			await tick();
			expect(ws.store.results.error?.kind).toBe(kind);
			expect(ws.store.results.response).not.toBeNull();
			expect(ws.store.results.stale).toBe(false);
			available(`a ${kind} error, the earlier results of this project kept`);
		}
		s.set('ok');
		await fireEvent.click(solveButton());
		calls++;
		await vi.waitFor(() => expect(ws.store.results.error).toBeNull());
		await tick();
		expect(s.solve).toHaveBeenCalledTimes(calls);
		unavailable('solved after the retry');
		// Out of date, a solve cancelled: available; an undo back to the project solved makes its
		// results current again, the cancel notwithstanding.
		longer(ws);
		await tick();
		s.set('hold');
		await fireEvent.click(solveButton());
		calls++;
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel solve' }));
		await tick();
		expect(ws.store.results.cancelled).toBe(true);
		expect(ws.store.results.stale).toBe(true);
		available('out of date, cancelled');
		ws.undo();
		await tick();
		expect(ws.store.results.cancelled).toBe(true);
		unavailable('cancelled, undone to the project solved');
		expect(s.solve).toHaveBeenCalledTimes(calls);
	});

	it('after a failed solve of an edited project and an undo back to the one solved, stays available: a press replaces the error the pane still shows', async () => {
		const s = programmedSolver();
		const ws = testWorkspace(pumpTransferExample(), { solver: s.solver });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(solveButton());
		await vi.waitFor(() => expect(ws.store.results.response).not.toBeNull());
		await tick();
		unavailable('solved');
		for (const kind of ['network', 'topology'] as const) {
			longer(ws);
			await tick();
			s.set(kind);
			await fireEvent.click(solveButton());
			await vi.waitFor(() => expect(ws.store.results.error?.kind).toBe(kind));
			ws.undo();
			await tick();
			expect(ws.store.results.stale).toBe(false);
			expect(ws.store.results.errorStale).toBe(true);
			// The pane still shows that error, marked out of date ...
			const heading = kind === 'network' ? 'No results' : 'The network cannot be solved yet';
			expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
			expect(screen.getAllByText(/Last solve: no results, out of date/).length).toBeGreaterThan(0);
			// ... so Solve is available, and its press solves the project shown again, replacing it.
			available(`a ${kind} error of an edited project, undone`);
			s.set('ok');
			const before = s.solve.mock.calls.length;
			await fireEvent.click(solveButton());
			expect(s.solve).toHaveBeenCalledTimes(before + 1);
			await vi.waitFor(() => expect(ws.store.results.error).toBeNull());
			await tick();
			expect(screen.queryByRole('heading', { name: heading })).not.toBeInTheDocument();
			unavailable(`solved again after the ${kind} error`);
		}
	});

	it('follows the case shown: unavailable on a case with current results, available on one out of date or never solved', async () => {
		const s = programmedSolver();
		const ws = testWorkspace(
			withScenarios(pumpTransferExample(), [
				{ id: 'S1', name: 'Winter', overrides: [] },
				{ id: 'S2', name: 'Summer', overrides: [] }
			]),
			{ solver: s.solver }
		);
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(solveButton());
		await vi.waitFor(() => expect(ws.store.results.response).not.toBeNull());
		await tick();
		unavailable('the base case solved');
		ws.setCase('S1');
		await tick();
		expect(solveButton()).toHaveAccessibleName('Solve Winter');
		available('Winter, never solved');
		await ws.solveAll();
		await tick();
		unavailable('Winter after Solve all');
		ws.setCase('S2');
		await tick();
		unavailable('Summer after Solve all');
		// Every case out of date; Summer solved again.
		longer(ws);
		await tick();
		available('Summer out of date');
		await fireEvent.click(solveButton());
		await vi.waitFor(() => expect(ws.store.results.stale).toBe(false));
		await tick();
		unavailable('Summer solved again');
		// Switched to a scenario still out of date: available; back: unavailable.
		ws.setCase('S1');
		await tick();
		expect(ws.store.results.stale).toBe(true);
		available('Winter out of date');
		ws.setCase('S2');
		await tick();
		unavailable('back on Summer');
		ws.setCase(null);
		await tick();
		available('the base case out of date');
	});

	it('Ctrl/⌘+Enter on current results says why and sends nothing; after an edit it solves', async () => {
		const s = programmedSolver();
		const ws = testWorkspace(pumpTransferExample(), { solver: s.solver });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true });
		await vi.waitFor(() => expect(ws.store.results.response).not.toBeNull());
		await tick();
		expect(s.solve).toHaveBeenCalledTimes(1);
		// Current: handled (the browser's own use prevented), said in Solve's words, nothing sent.
		for (const keys of [
			{ key: 'Enter', ctrlKey: true },
			{ key: 'Enter', metaKey: true }
		]) {
			ws.dismissNotice();
			expect(await fireEvent.keyDown(window, keys)).toBe(false);
			expect(ws.notice).toMatchObject({ kind: 'info', text: CURRENT });
			expect(s.solve).toHaveBeenCalledTimes(1);
		}
		ws.dismissNotice();
		// A held key's repeats are ignored, not refused: nothing said.
		expect(await fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true, repeat: true })).toBe(
			false
		);
		expect(ws.notice).toBeNull();
		// From a field with no new value: still current, said.
		ws.pane = 'build';
		await tick();
		const level = screen.getByRole('textbox', { name: /^Liquid level/ });
		await fireEvent.keyDown(level, { key: 'Enter', ctrlKey: true });
		expect(ws.notice).toMatchObject({ kind: 'info', text: CURRENT });
		expect(s.solve).toHaveBeenCalledTimes(1);
		ws.dismissNotice();
		// From a field with a new value: its Enter stores it, the results go out of date, the keys
		// solve it.
		await fireEvent.input(level, { target: { value: '4' } });
		await fireEvent.keyDown(level, { key: 'Enter', metaKey: true });
		expect(s.solve).toHaveBeenCalledTimes(2);
		const sent = (s.solve.mock.calls[1] as unknown as [Project])[0];
		expect(sent.components.find((c) => c.id === 'R1')).toMatchObject({ liquidLevel: 4 });
		expect(ws.notice).toBeNull();
	});
});
