/**
 * The panel navigator walks the port graph (SDD §3.1.1): Next asks which way at a branch, the
 * breadcrumb records the path taken, loops are offered as a jump back, and Previous and the
 * breadcrumb step back.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { closedLoopExample, gravityBranchExample, pumpTransferExample } from '$lib/utils/examples';
import { createComponent, createEmptyProject } from '$lib/utils/factory';

function breadcrumb(): string[] {
	const nav = screen.getByRole('navigation', { name: 'Path' });
	return within(nav)
		.getAllByRole('button')
		.map((b) => b.textContent?.trim() ?? '');
}

function current(): string {
	const build = screen.getByRole('region', { name: 'Build' });
	return within(build).getAllByRole('heading', { level: 2 })[0]?.textContent?.trim() ?? '';
}

async function next(times = 1) {
	for (let i = 0; i < times; i++) {
		await fireEvent.click(screen.getByRole('button', { name: /^Next/ }));
	}
}

describe('PanelNavigator', () => {
	it('starts at the first boundary and walks a chain with Next and Previous', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		expect(current()).toBe('Suction tank');
		expect(screen.getByRole('button', { name: /^Previous/ })).toBeDisabled();
		expect(screen.getByRole('button', { name: /^Next/ })).toHaveAccessibleName(
			'Next: Transfer pump'
		);

		await next();
		await next();
		await next();
		expect(current()).toBe('Discharge tank');
		expect(breadcrumb()).toEqual([
			'Suction tank',
			'Transfer pump',
			'Discharge isolation valve',
			'Discharge tank'
		]);
		expect(screen.getByRole('button', { name: /^Next/ })).toBeDisabled();

		await fireEvent.click(screen.getByRole('button', { name: /^Previous/ }));
		expect(current()).toBe('Discharge isolation valve');
		expect(breadcrumb()).toHaveLength(3);
	});

	it('edits the name in place, and names it once at the start of a walk', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		// No breadcrumb of one step, and one Name field: the heading's, not one in Properties.
		expect(screen.queryByRole('navigation', { name: 'Path' })).toBeNull();
		const names = build.getAllByRole('textbox', { name: 'Name' });
		expect(names).toHaveLength(1);
		expect(within(build.getByRole('tabpanel')).queryByRole('textbox', { name: 'Name' })).toBeNull();
		await fireEvent.input(names[0]!, { target: { value: 'Feed tank' } });
		await fireEvent.keyDown(names[0]!, { key: 'Enter' });
		expect(ws.project.components.find((c) => c.id === 'R1')?.name).toBe('Feed tank');
		expect(current()).toBe('Feed tank');
		expect(ws.store.undoLabel).toBe('rename component');
		await next();
		expect(breadcrumb()).toEqual(['Feed tank', 'Transfer pump']);
	});

	it('asks which way at a tee, and the breadcrumb records the path taken', async () => {
		const ws = testWorkspace(gravityBranchExample());
		render(WorkspaceView, { workspace: ws });
		await next();
		expect(current()).toBe('Distribution tee');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.getByRole('button', { name: /^Next/ })).toHaveAccessibleName('Next: choose');

		await next();
		const chooser = await screen.findByRole('dialog', { name: 'Which way from Distribution tee?' });
		const choices = within(chooser)
			.getAllByRole('button')
			.map((b) => b.textContent ?? '')
			.filter((t) => t.trim());
		expect(choices).toHaveLength(2);
		expect(choices[0]).toMatch(/Branch A globe valve.*Run outlet → Inlet.*L2/);
		expect(choices[1]).toMatch(/Lower tank B.*Branch → Port 1.*L4/);

		await fireEvent.click(within(chooser).getByRole('button', { name: /Lower tank B/ }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Lower tank B');
		expect(breadcrumb()).toEqual(['Elevated tank', 'Distribution tee', 'Lower tank B']);
		expect(ws.nav.path).toEqual([
			{ componentId: 'R1' },
			{ componentId: 'T1', viaConnectionId: 'L1' },
			{ componentId: 'R3', viaConnectionId: 'L4' }
		]);

		// Back to the tee from the breadcrumb, then the other way.
		const nav = screen.getByRole('navigation', { name: 'Path' });
		await fireEvent.click(within(nav).getByRole('button', { name: 'Distribution tee' }));
		expect(breadcrumb()).toEqual(['Elevated tank', 'Distribution tee']);
		await next();
		const again = await screen.findByRole('dialog', { name: /Which way/ });
		await fireEvent.click(within(again).getByRole('button', { name: /Branch A globe valve/ }));
		await next();
		expect(breadcrumb()).toEqual([
			'Elevated tank',
			'Distribution tee',
			'Branch A globe valve',
			'Lower tank A'
		]);
	});

	it('closing the chooser stays put', async () => {
		render(WorkspaceView, { workspace: testWorkspace(gravityBranchExample()) });
		await next();
		await next();
		const chooser = await screen.findByRole('dialog', { name: /Which way/ });
		await fireEvent.click(within(chooser).getByRole('button', { name: 'Close' }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Distribution tee');
	});

	it('offers a loop as a jump back to the component already on the path', async () => {
		const ws = testWorkspace(closedLoopExample());
		render(WorkspaceView, { workspace: ws });
		expect(current()).toBe('Expansion tank (pressurization point)');
		await next();
		await next();
		await fireEvent.click(
			within(await screen.findByRole('dialog')).getByRole('button', { name: /Circulation pump/ })
		);
		await next();
		expect(current()).toBe('Pump check valve');

		await next();
		const chooser = await screen.findByRole('dialog', { name: 'Which way from Pump check valve?' });
		expect(within(chooser).getByText('Loops back to the path')).toBeInTheDocument();
		await fireEvent.click(
			within(chooser).getByRole('button', { name: /Jump back to Pressurization tee/ })
		);
		expect(current()).toBe('Pressurization tee');
		expect(breadcrumb()).toEqual(['Expansion tank (pressurization point)', 'Pressurization tee']);
	});

	it('jumps to any component from the list, rebuilding the path from the start', async () => {
		const ws = testWorkspace(gravityBranchExample());
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Jump to a component' }));
		const list = await screen.findByRole('dialog', { name: 'Jump to a component' });
		await fireEvent.click(within(list).getByRole('button', { name: /Lower tank A/ }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Lower tank A');
		expect(breadcrumb()).toEqual([
			'Elevated tank',
			'Distribution tee',
			'Branch A globe valve',
			'Lower tank A'
		]);
	});

	it('cuts the path back after an undo removes the current component', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		await next();
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const dialog = await screen.findByRole('dialog', { name: 'Add after Transfer pump' });
		// Every pump port is connected, so it is inserted into the way onward (L2).
		expect(
			within(dialog).getByText(/Every port of Transfer pump is connected/)
		).toBeInTheDocument();
		expect(within(dialog).getByRole('combobox', { name: 'Connection' })).toHaveValue('L2');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Gate valve V2');
		expect(breadcrumb()).toEqual(['Suction tank', 'Transfer pump', 'Gate valve V2']);

		await fireEvent.click(screen.getByRole('button', { name: /^Undo add Gate valve V2/ }));
		expect(current()).toBe('Transfer pump');
		expect(breadcrumb()).toEqual(['Suction tank', 'Transfer pump']);
		expect(ws.store.canRedo).toBe(true);
	});

	it('at a port that is not connected, Next opens it to connect it; at the end it says so', async () => {
		const project = pumpTransferExample();
		project.connections = project.connections.filter((c) => c.id !== 'L3');
		const ws = testWorkspace(project);
		render(WorkspaceView, { workspace: ws });
		await next();
		await next();
		expect(current()).toBe('Discharge isolation valve');
		const button = screen.getByRole('button', { name: /^Next/ });
		expect(button).toHaveAccessibleName('Next: connect outlet');
		expect(button).toBeEnabled();
		await fireEvent.click(button);
		expect(ws.nav.mode).toBe('connection');
		expect(ws.nav.activePortId).toBe('outlet');
		expect(screen.getByRole('heading', { name: 'Outlet is not connected' })).toBeInTheDocument();
	});

	it('at a valve that starts the network, Next opens its outlet (the way onward)', async () => {
		const project = createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' });
		project.components = [createComponent('gate', project)];
		const ws = testWorkspace(project);
		render(WorkspaceView, { workspace: ws });
		expect(current()).toBe('Gate valve V1');
		const button = screen.getByRole('button', { name: /^Next/ });
		expect(button).toHaveAccessibleName('Next: connect outlet');
		await fireEvent.click(button);
		expect(ws.nav.activePortId).toBe('outlet');
		expect(screen.getByRole('heading', { name: 'Outlet is not connected' })).toBeInTheDocument();
	});

	it('says when the walk has reached its end', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		await next(3);
		expect(current()).toBe('Discharge tank');
		const button = screen.getByRole('button', { name: /^Next/ });
		expect(button).toHaveAccessibleName('Next: end of path');
		expect(button).toBeDisabled();
	});
});
