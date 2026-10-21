/**
 * Losses where piping meets a reservoir: new piping at a reservoir gets the cited default
 * entrance or exit fitting (told in the Add after hint, labelled in the fittings list and
 * removable), and piping at a reservoir without one says that no such loss is applied and
 * offers the fitting.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { PipeConnection } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createEmptyProject } from '$lib/utils/factory';

const fittingsOf = (ws: ReturnType<typeof testWorkspace>, id: string) =>
	(ws.project.connections.find((c) => c.id === id) as PipeConnection).piping.fittings;

describe('reservoir entrance and exit losses', () => {
	it('Add after a reservoir says it adds an entrance, and the piping shows it as the default', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Add after Reservoir R1' }));
		expect(
			dialog.getByText(
				/^Connected at its port 1 with 10 m of carbon steel schedule 40 pipe of the port's size and a sharp-edged pipe entrance fitting \(the default loss where flow leaves a reservoir\)\. Change it under Piping\.$/
			)
		).toBeInTheDocument();
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Component' }), {
			target: { value: 'gate' }
		});
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(fittingsOf(ws, 'L1')).toEqual([{ type: 'entrance_sharp', quantity: 1, pipeIndex: 0 }]);

		// Adding a reservoir after the valve: the hint names the exit.
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const next = within(await screen.findByRole('dialog', { name: /^Add after Gate valve/ }));
		await fireEvent.change(next.getByRole('combobox', { name: 'Component' }), {
			target: { value: 'reservoir' }
		});
		expect(
			next.getByText(/and a pipe exit fitting \(the default loss where flow enters a reservoir\)/)
		).toBeInTheDocument();
		await fireEvent.click(next.getByRole('button', { name: 'Add' }));
		expect(fittingsOf(ws, 'L2')).toEqual([{ type: 'exit', quantity: 1, pipeIndex: 0 }]);

		ws.nav.jumpTo('R1');
		ws.nav.showConnection('port_1');
		expect(
			await screen.findByText(/^Entrance loss where flow leaves Reservoir R1 into this pipe/)
		).toBeInTheDocument();
		expect(screen.queryByText(/No entrance or exit loss is applied/)).toBeNull();
	});

	it('piping at a reservoir without an entrance or exit says so and offers the fitting', async () => {
		const project = pumpTransferExample();
		const l3 = project.connections.find((c) => c.id === 'L3')!;
		l3.piping.fittings = l3.piping.fittings.filter((f) => f.type !== 'exit');
		const ws = testWorkspace(project);
		ws.nav.jumpTo('R2');
		ws.nav.showConnection('port_1');
		render(WorkspaceView, { workspace: ws });

		expect(
			await screen.findByText(
				/No entrance or exit loss is applied where this piping meets Discharge tank/
			)
		).toBeInTheDocument();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Exit (flow enters Discharge tank)' })
		);
		expect(fittingsOf(ws, 'L3').filter((f) => f.type === 'exit')).toEqual([
			{ type: 'exit', quantity: 1, pipeIndex: 0 }
		]);
		expect(screen.queryByText(/No entrance or exit loss is applied/)).toBeNull();
		expect(
			screen.getByText(/^Exit loss where flow leaves this pipe into Discharge tank/)
		).toBeInTheDocument();
	});
});
