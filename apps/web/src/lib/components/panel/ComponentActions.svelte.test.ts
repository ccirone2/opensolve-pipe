/**
 * Component actions update the port graph and move the navigator to the change: add after (at a
 * free port), add before (inserted into the arriving connection), add branch (a tee inserted,
 * branch port free) and delete (optionally joining the neighbors).
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createEmptyProject } from '$lib/utils/factory';
import { connectionAtPort } from '$lib/utils/graph';
import { referenceProblems, schemaProblems } from '$lib/utils/validate';
import type { Workspace } from '$lib/state/workspace.svelte';

function build() {
	return within(screen.getByRole('region', { name: 'Build' }));
}

function current(): string {
	return build().getAllByRole('heading', { level: 2 })[0]?.textContent?.trim() ?? '';
}

function breadcrumb(): string[] {
	const nav = screen.getByRole('navigation', { name: 'Path' });
	return within(nav)
		.getAllByRole('button')
		.map((b) => b.textContent?.trim() ?? '');
}

async function next(times = 1) {
	for (let i = 0; i < times; i++) {
		await fireEvent.click(screen.getByRole('button', { name: /^Next/ }));
	}
}

async function openDialog(action: string, title: string | RegExp) {
	await fireEvent.click(screen.getByRole('button', { name: action }));
	return within(await screen.findByRole('dialog', { name: title }));
}

function expectValid(ws: Workspace) {
	expect(schemaProblems(ws.project)).toEqual([]);
	expect(referenceProblems(ws.project)).toEqual([]);
}

describe('component actions', () => {
	it('adds the first component, then one after it at its free port', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		expect(screen.getByRole('heading', { name: 'Start the network' })).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Reservoir R1');

		const dialog = await openDialog('Add after', 'Add after Reservoir R1');
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Component' }), {
			target: { value: 'pump' }
		});
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Pump P1');
		expect(breadcrumb()).toEqual(['Reservoir R1', 'Pump P1']);
		const connection = ws.project.connections[0];
		expect(ws.project.connections).toHaveLength(1);
		// A reservoir port is a source: the pump is downstream, connected by its suction.
		expect(connection).toMatchObject({
			fromComponentId: 'R1',
			fromPortId: 'port_1',
			toComponentId: 'P1',
			toPortId: 'suction'
		});
		expect(ws.store.undoLabel).toBe('add Pump P1');
		expectValid(ws);
	});

	it('adds after a valve that starts the network downstream, at its outlet', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		await fireEvent.change(screen.getByRole('combobox', { name: 'First component' }), {
			target: { value: 'gate' }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Gate valve V1');

		// Both ports are free: "after" is the outlet, not the inlet (which would be before it).
		const dialog = await openDialog('Add after', 'Add after Gate valve V1');
		expect(dialog.getByRole('combobox', { name: 'Port' })).toHaveValue('outlet');
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Component' }), {
			target: { value: 'reservoir' }
		});
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));

		expect(current()).toBe('Reservoir R1');
		expect(ws.project.connections).toEqual([
			expect.objectContaining({
				fromComponentId: 'V1',
				fromPortId: 'outlet',
				toComponentId: 'R1',
				toPortId: 'port_1'
			})
		]);
		expectValid(ws);
	});

	it('adds before: inserts into the connection the walk arrived by', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		await next(2);
		expect(current()).toBe('Discharge isolation valve');

		const dialog = await openDialog('Add before', 'Add before Discharge isolation valve');
		expect(dialog.getByRole('combobox', { name: 'Connection' })).toHaveValue('L2');
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Component' }), {
			target: { value: 'check' }
		});
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));

		expect(current()).toBe('Check valve V2');
		expect(breadcrumb()).toEqual(['Suction tank', 'Transfer pump', 'Check valve V2']);
		// L2 now ends at the check valve; a new connection joins it to the gate valve.
		expect(connectionAtPort(ws.project, 'P1', 'discharge')).toMatchObject({
			id: 'L2',
			toComponentId: 'V2',
			toPortId: 'inlet'
		});
		expect(connectionAtPort(ws.project, 'V1', 'inlet')).toMatchObject({
			fromComponentId: 'V2',
			fromPortId: 'outlet'
		});
		expectValid(ws);

		await next();
		expect(current()).toBe('Discharge isolation valve');
	});

	it('adds a branch: a tee in the connection, showing its free branch port', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		await next();
		expect(current()).toBe('Transfer pump');

		const dialog = await openDialog('Add branch', 'Add a branch at Transfer pump');
		expect(dialog.getByRole('combobox', { name: 'Connection' })).toHaveValue('L1');
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));

		expect(current()).toBe('Tee T1');
		expect(breadcrumb()).toEqual(['Suction tank', 'Tee T1']);
		expect(build().getByRole('tab', { name: 'Piping' })).toHaveAttribute('aria-selected', 'true');
		expect(build().getByRole('heading', { name: 'Branch is not connected' })).toBeInTheDocument();
		expect(connectionAtPort(ws.project, 'T1', 'run_inlet')?.fromComponentId).toBe('R1');
		expect(connectionAtPort(ws.project, 'T1', 'run_outlet')?.toComponentId).toBe('P1');
		expect(connectionAtPort(ws.project, 'T1', 'branch')).toBeUndefined();
		expectValid(ws);

		// The free branch port takes a new component right away.
		await fireEvent.change(build().getByRole('combobox', { name: 'Add a component here' }), {
			target: { value: 'reservoir' }
		});
		await fireEvent.click(build().getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Reservoir R3');
		expect(connectionAtPort(ws.project, 'T1', 'branch')?.toComponentId).toBe('R3');
		expectValid(ws);
	});

	it('deletes a component and joins its neighbors', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		await next(2);
		const dialog = await openDialog('Delete', 'Delete Discharge isolation valve?');
		const join = dialog.getByRole('checkbox', { name: /Join Transfer pump and Discharge tank/ });
		expect(join).toBeChecked();
		await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));

		expect(ws.project.components.map((c) => c.id)).toEqual(['R1', 'P1', 'R2']);
		const merged = connectionAtPort(ws.project, 'P1', 'discharge');
		expect(merged).toMatchObject({ id: 'L2', toComponentId: 'R2', toPortId: 'port_1' });
		expect(merged?.piping.pipes.map((p) => p.length)).toEqual([3, 60]);
		// The downstream connection's fittings now sit on the second pipe.
		expect(merged?.piping.fittings.map((f) => [f.type, f.pipeIndex])).toEqual([
			['elbow_90_lr', 1],
			['exit', 1]
		]);
		expect(current()).toBe('Transfer pump');
		expect(breadcrumb()).toEqual(['Suction tank', 'Transfer pump']);
		expectValid(ws);
		await next();
		expect(current()).toBe('Discharge tank');
	});

	it('deletes a component without joining, freeing the neighbors’ ports', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		await next(2);
		const dialog = await openDialog('Delete', 'Delete Discharge isolation valve?');
		await fireEvent.click(dialog.getByRole('checkbox', { name: /Join/ }));
		await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));

		expect(ws.project.connections.map((c) => c.id)).toEqual(['L1']);
		expect(connectionAtPort(ws.project, 'P1', 'discharge')).toBeUndefined();
		expect(current()).toBe('Transfer pump');
		expectValid(ws);

		await fireEvent.click(screen.getByRole('button', { name: /^Undo delete/ }));
		expect(ws.project.components).toHaveLength(4);
		expect(ws.project.connections).toHaveLength(3);
	});

	it('deleting the start component restarts the walk at a former neighbor', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		const dialog = await openDialog('Delete', 'Delete Suction tank?');
		await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
		expect(current()).toBe('Transfer pump');
		expect(breadcrumb()).toEqual(['Transfer pump']);
	});

	it('rejoins the line when a tee added as a branch is deleted', async () => {
		const ws = testWorkspace(pumpTransferExample());
		render(WorkspaceView, { workspace: ws });
		await next();
		const add = await openDialog('Add branch', 'Add a branch at Transfer pump');
		await fireEvent.change(add.getByRole('combobox', { name: 'Connection' }), {
			target: { value: 'L2' }
		});
		await fireEvent.click(add.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Tee T1');

		const dialog = await openDialog('Delete', 'Delete Tee T1?');
		const join = dialog.getByRole('checkbox', {
			name: /Join Transfer pump and Discharge isolation valve/
		});
		expect(join).toBeChecked();
		await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
		expect(ws.project.components.map((c) => c.id)).toEqual(['R1', 'P1', 'V1', 'R2']);
		expect(connectionAtPort(ws.project, 'P1', 'discharge')).toMatchObject({
			toComponentId: 'V1',
			toPortId: 'inlet'
		});
		expectValid(ws);
	});

	it('after a delete, focus moves to the heading of the component shown', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		await next(2);
		const button = screen.getByRole('button', { name: 'Delete' });
		button.focus();
		const dialog = await openDialog('Delete', 'Delete Discharge isolation valve?');
		await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
		await vi.waitFor(() =>
			expect(document.activeElement).toBe(build().getByRole('heading', { name: 'Transfer pump' }))
		);
	});

	it('at the start of the walk, Add before inserts next to the component', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		const dialog = await openDialog('Add before', 'Insert next to Suction tank');
		expect(dialog.getByRole('radio', { name: 'Into one of its connections' })).toBeChecked();
		// Every port of the tank is connected: adding after is not possible, and it says why.
		expect(
			dialog.getByRole('radio', { name: 'At a free port (after it) (every port is connected)' })
		).toBeDisabled();
	});

	it('says why Add before and Add branch are unavailable', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		const before = screen.getByRole('button', { name: 'Add before' });
		expect(before).toBeDisabled();
		expect(before).toHaveAccessibleDescription(/go into a connection; Reservoir R1 has none yet/);
		expect(screen.getByRole('button', { name: 'Add branch' })).toHaveAccessibleDescription(
			/Use Add after/
		);
	});
});
