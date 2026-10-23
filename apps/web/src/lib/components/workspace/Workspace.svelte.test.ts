/**
 * The workspace page structure: landmarks and headings, the Build / Results tabs on narrow
 * screens, and the header's buttons that keep focus while unavailable.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
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
});
