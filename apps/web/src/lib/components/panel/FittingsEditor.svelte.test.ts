/**
 * Losses where piping meets a reservoir: new piping at a reservoir gets the cited default
 * entrance or exit fitting (told in the Add after hint, labelled in the fittings list and
 * removable), and piping at a reservoir without one says that no such loss is applied and
 * offers the fitting.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { LibraryResponse, PipeConnection, ResistanceSpec } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createEmptyProject } from '$lib/utils/factory';
import { libraryProject } from '$lib/testing/helpers';
import { TEST_LIBRARY } from '$lib/testing/library';

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

	it('Add after a reservoir: a supply runs into it, so the hint and the piping name the exit', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Add after Reservoir R1' }));
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Component' }), {
			target: { value: 'assigned_flow' }
		});
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Direction' }), {
			target: { value: 'supply' }
		});
		const flow = dialog.getByRole('textbox', { name: /^Flow/ });
		await fireEvent.input(flow, { target: { value: '5' } });
		await fireEvent.change(flow);
		expect(
			dialog.getByText(/and a pipe exit fitting \(the default loss where flow enters a reservoir\)/)
		).toBeInTheDocument();
		expect(dialog.queryByText(/entrance fitting/)).toBeNull();
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		const l1 = ws.project.connections.find((c) => c.id === 'L1')!;
		expect([l1.fromComponentId, l1.toComponentId]).toEqual(['AF1', 'R1']);
		expect(l1.piping.fittings).toEqual([{ type: 'exit', quantity: 1, pipeIndex: 0 }]);
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

/**
 * A fitting's loss coefficient (CLAUDE.md D22; proposal project-library.md §6.2): the type's cited
 * K, a K entered here, or a project library entry, which is used by reference (its K, Cv or Kv on
 * the fitting's own pipe) and shown read-only. Test inputs: libraryProject's entries.
 */
describe('a fitting K from the project library', () => {
	function setup(project = libraryProject()) {
		const ws = testWorkspace(project);
		ws.nav.jumpTo('R1');
		ws.nav.showConnection('port_1');
		render(WorkspaceView, { workspace: ws });
		return ws;
	}

	it('shows an entry, switches to a K entered here and back to the cited K', async () => {
		const ws = setup();
		const choice = screen.getByRole('combobox', { name: 'Fitting 1 loss coefficient' });
		expect(choice).toHaveValue('entry:RS2');
		expect(
			[...choice.querySelectorAll('option')].map((o) => [o.value, o.textContent?.trim()])
		).toEqual([
			['cited', 'Cited K of this fitting type'],
			['entered', 'K entered here'],
			['entry:RS1', '“Gate, open” (Cv 900)'],
			['entry:RS2', '“Elbow (K)” (K 0.3 at 90 mm)'],
			['new-entry', 'New entry…']
		]);
		// The K entry on pipe 1's 100 mm bore: K₀ (D/d₀)⁴ = 0.3 × (100/90)⁴.
		expect(screen.getByText(/K = K₀ \(D\/d₀\)⁴: K 0\.4572 at 100 mm\./)).toBeInTheDocument();

		await fireEvent.change(choice, { target: { value: 'entered' } });
		expect(fittingsOf(ws, 'L1')[0]).toEqual({ type: 'elbow_90_lr', quantity: 2, pipeIndex: 0 });
		const k = screen.getByRole('textbox', { name: 'K override' });
		expect(screen.getByText('Enter K to use it; until then the cited K applies.')).toBeVisible();
		await fireEvent.input(k, { target: { value: '0.5' } });
		await fireEvent.change(k);
		expect(fittingsOf(ws, 'L1')[0]).toEqual({
			type: 'elbow_90_lr',
			quantity: 2,
			pipeIndex: 0,
			kOverride: 0.5
		});

		await fireEvent.change(screen.getByRole('combobox', { name: 'Fitting 1 loss coefficient' }), {
			target: { value: 'entry:RS1' }
		});
		expect(fittingsOf(ws, 'L1')[0]).toEqual({
			type: 'elbow_90_lr',
			quantity: 2,
			pipeIndex: 0,
			resistanceId: 'RS1'
		});
		await fireEvent.change(screen.getByRole('combobox', { name: 'Fitting 1 loss coefficient' }), {
			target: { value: 'cited' }
		});
		expect(fittingsOf(ws, 'L1')[0]).toEqual({ type: 'elbow_90_lr', quantity: 2, pipeIndex: 0 });
	});

	it('a full library offers "New entry…" disabled, saying why', async () => {
		// 100 made-up Cv entries, RS1... (RS2 still fitting 1's): as many as a project may hold.
		const project = libraryProject();
		project.resistanceLibrary = Array.from({ length: 100 }, (_, i): ResistanceSpec => ({
			id: `RS${i + 1}`,
			name: `Entry ${i + 1}`,
			source: 'Test input: a made-up Cv',
			kind: 'Cv',
			value: 100
		}));
		const ws = setup(project);
		const choice = screen.getByRole('combobox', { name: 'Fitting 1 loss coefficient' });
		expect(
			within(choice).getByRole('option', { name: 'New entry… (a project holds at most 100)' })
		).toBeDisabled();
		expect(within(choice).queryByRole('option', { name: 'New entry…' })).toBeNull();
		// Chosen all the same (a disabled option can be set from script): nothing opens.
		await fireEvent.change(choice, { target: { value: 'new-entry' } });
		await tick();
		expect(screen.queryByRole('dialog', { name: 'Project library' })).toBeNull();
		expect(fittingsOf(ws, 'L1')[0]?.resistanceId).toBe('RS2');
	});

	it('"K entered here" with no K yet stays with its connection when the panel moves to another port', async () => {
		// V1's two ports: L2 (inlet) given a made-up elbow on its cited K, L3 (outlet) with its own.
		const project = pumpTransferExample();
		const l2 = project.connections.find((c) => c.id === 'L2') as PipeConnection;
		l2.piping.fittings = [{ type: 'elbow_90_lr', quantity: 1, pipeIndex: 0 }];
		const ws = testWorkspace(project);
		ws.nav.jumpTo('V1');
		ws.nav.showConnection('outlet');
		render(WorkspaceView, { workspace: ws });
		const choice = () => screen.getByRole('combobox', { name: 'Fitting 1 loss coefficient' });
		const port = (name: RegExp) =>
			within(screen.getByRole('group', { name: 'Ports of Discharge isolation valve' })).getByRole(
				'button',
				{ name }
			);
		const before = { l2: fittingsOf(ws, 'L2'), l3: fittingsOf(ws, 'L3') };
		expect(screen.getByRole('heading', { name: 'Connection L3' })).toBeInTheDocument();
		expect(choice()).toHaveValue('cited');
		await fireEvent.change(choice(), { target: { value: 'entered' } });
		expect(choice()).toHaveValue('entered');

		// The same editor on L2: its fitting 1 is on its cited K, as nobody chose otherwise there.
		await fireEvent.click(port(/^Inlet/));
		expect(screen.getByRole('heading', { name: 'Connection L2' })).toBeInTheDocument();
		expect(choice()).toHaveValue('cited');
		expect(screen.queryByRole('textbox', { name: 'K override' })).toBeNull();
		expect(screen.queryByText('Enter K to use it; until then the cited K applies.')).toBeNull();

		// Back on L3, the choice made there is still being entered; nothing was stored on either.
		await fireEvent.click(port(/^Outlet/));
		expect(screen.getByRole('heading', { name: 'Connection L3' })).toBeInTheDocument();
		expect(choice()).toHaveValue('entered');
		expect(screen.getByRole('textbox', { name: 'K override' })).toBeInTheDocument();
		expect({ l2: fittingsOf(ws, 'L2'), l3: fittingsOf(ws, 'L3') }).toEqual(before);
	});

	it('a custom fitting has no cited K: an entry or a K entered here', async () => {
		setup();
		const choice = screen.getByRole('combobox', { name: 'Fitting 2 loss coefficient' });
		expect(choice).toHaveValue('entry:RS1');
		expect(within(choice).queryByRole('option', { name: /^Cited K/ })).toBeNull();
		const item = choice.closest('li') as HTMLElement;
		expect(within(item).getByText('Source: test input')).toBeInTheDocument();
		expect(
			within(item).getByText(/^Converted to K at the bore of pipe 2 when solving/)
		).toBeInTheDocument();
	});
});

/**
 * "K source" names the source of the K the solve uses (CLAUDE.md D22 traceability; the server's
 * FittingResult.source): the type's cited K, or user data for a K entered here; a fitting on a
 * library entry shows the entry's own source only, never the type's correlation beside it. Test
 * inputs: libraryProject's entries and a made-up fitting library.
 */
describe("a fitting's K source", () => {
	const CITED = 'test source: the cited correlation of a long-radius elbow';
	const LIBRARY: LibraryResponse = {
		...TEST_LIBRARY,
		fittings: [
			{
				type: 'elbow_90_lr',
				name: 'Elbow, 90° long radius',
				correlation: 'test correlation',
				parameters: [],
				referenceDiameter: 'pipe',
				validInLaminarFlow: false,
				notes: [],
				source: CITED
			}
		]
	};

	it('is the entry, the K entered here or the cited K, whichever the solve uses', async () => {
		const ws = testWorkspace(libraryProject(), {
			library: { getLibrary: () => Promise.resolve(LIBRARY) }
		});
		ws.nav.jumpTo('R1');
		ws.nav.showConnection('port_1');
		render(WorkspaceView, { workspace: ws });
		await vi.waitFor(() => expect(ws.library.libraryStatus).toBe('ready'));
		await tick();
		const choice = () => screen.getByRole('combobox', { name: 'Fitting 1 loss coefficient' });
		const item = within(choice().closest('li') as HTMLElement);

		// On entry RS2: the entry's source, not the elbow's correlation.
		expect(choice()).toHaveValue('entry:RS2');
		expect(item.getByText('Source: test input')).toBeInTheDocument();
		expect(item.queryByText(/^K source/)).toBeNull();
		expect(item.queryByText(new RegExp(CITED))).toBeNull();

		// A K entered here, until one is entered: the cited K applies, and is named.
		await fireEvent.change(choice(), { target: { value: 'entered' } });
		expect(item.getByText(`K source: ${CITED}`)).toBeInTheDocument();
		const k = item.getByRole('textbox', { name: 'K override' });
		await fireEvent.input(k, { target: { value: '0.5' } });
		await fireEvent.change(k);
		expect(item.getByText('K source: the K entered here (user data).')).toBeInTheDocument();
		expect(item.queryByText(new RegExp(CITED))).toBeNull();

		await fireEvent.change(choice(), { target: { value: 'cited' } });
		expect(item.getByText(`K source: ${CITED}`)).toBeInTheDocument();
	});
});
