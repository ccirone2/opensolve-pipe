/**
 * Share copies the current link (D3): the project is in the fragment, the link opens the same
 * project, a pending edit is included, and links over 8,000 characters carry a warning.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '$lib/api/types';
import { testWorkspace } from '$lib/testing/workspace';
import { decodeProject, fragmentOf, URL_LENGTH_WARNING } from '$lib/utils/encoding';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';
import WorkspaceView from './Workspace.svelte';

function mockClipboard(writeText: ((text: string) => Promise<void>) | undefined) {
	Object.defineProperty(navigator, 'clipboard', {
		configurable: true,
		value: writeText ? { writeText } : undefined
	});
}

afterEach(() => mockClipboard(undefined));

/** A project whose link is long: many components with incompressible (random) names. */
function bigProject(): Project {
	let seed = 12345;
	const random = () => {
		seed = (seed * 1103515245 + 12345) % 2 ** 31;
		return seed / 2 ** 31;
	};
	const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
	const project = pumpTransferExample();
	for (let i = 0; i < 80; i++) {
		const name = Array.from({ length: 100 }, () => alphabet[Math.floor(random() * 62)]).join('');
		project.components.push(createComponent('reservoir', project, { name }));
	}
	return project;
}

describe('Share', () => {
	it('copies the link to the current project', async () => {
		const writeText = vi.fn((text: string) => {
			void text;
			return Promise.resolve();
		});
		mockClipboard(writeText);
		const project = pumpTransferExample();
		const ws = testWorkspace(project, { origin: 'https://opensolve-pipe.app' });
		render(WorkspaceView, { workspace: ws });

		await fireEvent.click(screen.getByRole('button', { name: 'Share' }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
		const link = writeText.mock.calls[0]?.[0] ?? '';
		expect(link).toMatch(/^https:\/\/opensolve-pipe\.app\/p#[A-Za-z0-9_-]+$/);
		expect(decodeProject(fragmentOf(link))).toEqual(project);

		const dialog = within(await screen.findByRole('dialog', { name: 'Share this project' }));
		expect(dialog.getByRole('status')).toHaveTextContent('Link copied to the clipboard.');
		expect(dialog.getByRole('textbox', { name: /Link to this version/ })).toHaveValue(link);
		expect(
			dialog.getByText(`${link.length.toLocaleString('en-US')} characters`)
		).toBeInTheDocument();
		expect(dialog.queryByText(/longer than 8,000 characters/)).toBeNull();
	});

	it('includes an edit that has not reached the address bar yet', async () => {
		const writeText = vi.fn((text: string) => {
			void text;
			return Promise.resolve();
		});
		mockClipboard(writeText);
		const urls: string[] = [];
		const ws = testWorkspace(pumpTransferExample(), { writeUrl: (path) => urls.push(path) });
		render(WorkspaceView, { workspace: ws });
		ws.store.update((p) => {
			p.metadata.name = 'Edited just now';
		}, 'rename project');
		expect(ws.store.syncPending).toBe(true);

		await fireEvent.click(screen.getByRole('button', { name: 'Share' }));
		await waitFor(() => expect(writeText).toHaveBeenCalled());
		const link = writeText.mock.calls[0]?.[0] ?? '';
		expect(decodeProject(fragmentOf(link)).metadata.name).toBe('Edited just now');
		// The address bar was brought up to date too (copy-on-write: this is the new link).
		expect(urls.at(-1)).toBe(`/p#${fragmentOf(link)}`);
	});

	it('shows the link to copy by hand when the clipboard cannot be used', async () => {
		mockClipboard(() => Promise.reject(new Error('denied')));
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Share' }));

		const dialog = within(await screen.findByRole('dialog', { name: 'Share this project' }));
		expect(dialog.getByRole('status')).toHaveTextContent('Copy the link below.');
		const field = dialog.getByRole('textbox', { name: /Link to this version/ });
		expect(field).toHaveValue(ws.store.url);
		await waitFor(() => expect(field).toHaveFocus());
	});

	it('warns when the link is longer than 8,000 characters', async () => {
		mockClipboard(() => Promise.resolve());
		const ws = testWorkspace(bigProject());
		expect(ws.store.urlLength).toBeGreaterThan(URL_LENGTH_WARNING);
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Share' }));

		const dialog = within(await screen.findByRole('dialog', { name: 'Share this project' }));
		expect(dialog.getByText(/This link is longer than 8,000 characters/)).toBeInTheDocument();
		expect(dialog.getByText(/Some email\s+and chat apps cut long links short/)).toBeInTheDocument();
	});
});
