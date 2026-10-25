/**
 * The workspace page structure: landmarks and headings, the Build / Results tabs on narrow
 * screens, the header's buttons that keep focus while unavailable, and Cancel while a solve runs.
 * The solve results are made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Project, SolveResponse } from '$lib/api/types';
import { pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createEmptyProject } from '$lib/utils/factory';
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
		// Inside a dialog the keys belong to the dialog.
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
		const dialog = await screen.findByRole('dialog', { name: 'Project settings' });
		await fireEvent.keyDown(within(dialog).getByRole('button', { name: 'Done' }), {
			key: 'Enter',
			ctrlKey: true
		});
		expect(solveFn).toHaveBeenCalledTimes(2);
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
