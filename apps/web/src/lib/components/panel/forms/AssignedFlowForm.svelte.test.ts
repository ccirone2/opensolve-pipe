/**
 * The assigned-flow node in the Build panel (SDD §4.11): it has no default flow, so the user
 * enters one where it is added; the flow is a direction (demand or supply) and a magnitude in
 * the display flow unit, stored as one signed SI value; it has one port and ends a walk like a
 * plug. Flows are made-up test inputs; unit factors are computed by units.ts toSI, whose
 * definitions units.test.ts checks.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { AssignedFlow, Project } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { assignedFlowProject } from '$lib/testing/helpers';
import { testWorkspace } from '$lib/testing/workspace';
import { createComponent, createEmptyProject } from '$lib/utils/factory';
import { IMPERIAL_UNITS, toSI } from '$lib/utils/units';

const LABEL = 'Assigned flow (demand or supply)';
const REQUIRED = 'Enter the flow: an assigned-flow node has no default flow.';

function current(): string {
	const build = screen.getByRole('region', { name: 'Build' });
	return within(build).getAllByRole('heading', { level: 2 })[0]?.textContent?.trim() ?? '';
}

async function type(input: HTMLElement, text: string) {
	await fireEvent.input(input, { target: { value: text } });
	await fireEvent.change(input);
}

function flowOf(project: Project, id = 'AF1'): number | undefined {
	const node = project.components.find((c) => c.id === id);
	return node?.type === 'assigned_flow' ? node.flow : undefined;
}

describe('adding an assigned-flow node', () => {
	it('after a reservoir: asks for the flow first, then adds it as a supply, exactly', async () => {
		const empty = createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' });
		const ws = testWorkspace({ ...empty, components: [createComponent('reservoir', empty)] });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const dialog = await screen.findByRole('dialog', { name: 'Add after Reservoir R1' });
		const kinds = within(dialog).getByRole('combobox', { name: 'Component' });
		// Not with the boundaries: a group of its own.
		const option = within(kinds).getByRole('option', { name: LABEL });
		expect(option.closest('optgroup')).toHaveAttribute('label', 'Flows in and out');
		await fireEvent.change(kinds, { target: { value: 'assigned_flow' } });
		const flow = within(dialog).getByRole('textbox', { name: 'Flow (L/s)' });
		expect(flow).toHaveValue('');

		// No flow is cited as a default, so none is invented: Add asks for it.
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(within(dialog).getByRole('alert')).toHaveTextContent(REQUIRED);
		expect(flow).toHaveAttribute('aria-invalid', 'true');
		expect(ws.project.components).toHaveLength(1);

		await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Direction' }), {
			target: { value: 'supply' }
		});
		await type(flow, '5');
		expect(within(dialog).queryByRole('alert')).toBeNull();
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Assigned flow AF1');
		expect(flowOf(ws.project)).toBe(-toSI(5, 'L/s'));
		// The supply's flow runs into the reservoir: the connection runs that way, with the exit
		// loss where it arrives (edit.ts addsUpstream).
		expect(ws.project.connections).toMatchObject([
			{ fromComponentId: 'AF1', fromPortId: 'port_1', toComponentId: 'R1', toPortId: 'port_1' }
		]);
		expect(ws.project.connections[0]!.piping.fittings).toEqual([
			{ type: 'exit', quantity: 1, pipeIndex: 0 }
		]);
		// One port, connected: the walk ends here, as at a plug.
		const next = screen.getByRole('button', { name: /^Next/ });
		expect(next).toHaveAccessibleName('Next: end of path');
		expect(next).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Undo add Assigned flow AF1' })).toBeEnabled();
	});

	it('as the first component, and at a free port: the flow is asked for in both', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'First component' }), {
			target: { value: 'assigned_flow' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getByRole('alert')).toHaveTextContent(REQUIRED);
		expect(ws.project.components).toEqual([]);
		await type(build.getByRole('textbox', { name: 'Flow (L/s)' }), '2');
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Assigned flow AF1');
		expect(flowOf(ws.project)).toBe(toSI(2, 'L/s'));
		// Not a fixed-pressure boundary: the network still needs one, and the results pane says so.
		const results = within(screen.getByRole('region', { name: 'Results' }));
		expect(
			results.getByText(
				'The network needs at least one reservoir or reference node (a fixed-pressure boundary). Assigned-flow nodes fix a flow, not a pressure, so they do not count.'
			)
		).toBeInTheDocument();

		// Its free port: another assigned-flow node is added there only with its flow.
		await fireEvent.click(build.getByRole('button', { name: 'Next: connect port 1' }));
		expect(build.getByRole('heading', { name: 'Port 1 is not connected' })).toBeInTheDocument();
		await fireEvent.change(build.getByRole('combobox', { name: 'Add a component here' }), {
			target: { value: 'assigned_flow' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getByRole('alert')).toHaveTextContent(REQUIRED);
		expect(ws.project.components).toHaveLength(1);
		await type(build.getByRole('textbox', { name: 'Flow (L/s)' }), '2');
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Assigned flow AF2');
		expect(flowOf(ws.project, 'AF2')).toBe(toSI(2, 'L/s'));
	});
});

describe('AssignedFlowForm', () => {
	it('edits a direction and a magnitude in the display unit, stored signed in SI', async () => {
		const project = assignedFlowProject(toSI(150, 'gpm'));
		project.settings.units = { ...IMPERIAL_UNITS };
		const ws = testWorkspace(project);
		ws.nav.jumpTo('AF1');
		render(WorkspaceView, { workspace: ws });
		expect(current()).toBe('Process user');
		const direction = screen.getByRole('combobox', { name: 'Direction' });
		const flow = screen.getByRole('textbox', { name: 'Flow (gpm)' });
		expect(direction).toHaveValue('demand');
		expect(flow).toHaveValue('150');
		expect(flow).toHaveAccessibleDescription(/Leaves the network at the port/);

		// The direction changes only the sign: the magnitude round-trips exactly.
		await fireEvent.change(direction, { target: { value: 'supply' } });
		expect(flowOf(ws.project)).toBe(-toSI(150, 'gpm'));
		expect(flow).toHaveValue('150');
		expect(flow).toHaveAccessibleDescription(/Enters the network at the port/);
		expect(screen.getByRole('button', { name: 'Undo change flow direction' })).toBeEnabled();

		await type(flow, '37.5');
		expect(flowOf(ws.project)).toBe(-toSI(37.5, 'gpm'));
		expect(screen.getByRole('button', { name: 'Undo change assigned flow' })).toBeEnabled();

		// 0 has no direction: the node is a closed end, and a supply stays one in the form.
		await type(flow, '0');
		expect(flowOf(ws.project)).toBe(0);
		expect(flow).toHaveAccessibleDescription(/At 0 the node passes no flow/);
		expect(direction).toHaveValue('supply');
		await type(flow, '20');
		expect(flowOf(ws.project)).toBe(-toSI(20, 'gpm'));
	});

	it('takes the magnitude only: a negative or too large value is refused, not stored', async () => {
		const ws = testWorkspace(assignedFlowProject(-0.004));
		ws.nav.jumpTo('AF1');
		render(WorkspaceView, { workspace: ws });
		const flow = screen.getByRole('textbox', { name: 'Flow (L/s)' });
		expect(flow).toHaveValue('4');
		await type(flow, '-4');
		expect(flow).toHaveAttribute('aria-invalid', 'true');
		await type(flow, '1e9');
		expect(flow).toHaveAttribute('aria-invalid', 'true');
		expect(flowOf(ws.project)).toBe(-0.004);

		// A stored supply set to 0 and back keeps its direction.
		await type(flow, '0');
		expect(screen.getByRole('combobox', { name: 'Direction' })).toHaveValue('supply');
		await type(flow, '3');
		expect(flowOf(ws.project)).toBe(-toSI(3, 'L/s'));
	});

	it('has one port and no way to add another, and a hint that it is not a boundary', () => {
		const ws = testWorkspace(assignedFlowProject(0.004));
		ws.nav.jumpTo('AF1');
		render(WorkspaceView, { workspace: ws });
		const ports = within(screen.getByRole('region', { name: 'Ports' }));
		expect(ports.getAllByRole('listitem')).toHaveLength(1);
		expect(ports.getByText('Port 1')).toBeInTheDocument();
		expect(ports.queryByRole('button', { name: 'Add port' })).toBeNull();
		expect(screen.getByText(/It fixes a flow, not a pressure/)).toBeInTheDocument();
		const node = ws.project.components.find((c): c is AssignedFlow => c.id === 'AF1');
		expect(node?.ports.map((p) => p.id)).toEqual(['port_1']);
	});
});
