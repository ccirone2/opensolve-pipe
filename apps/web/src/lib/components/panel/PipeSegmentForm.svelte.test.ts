/**
 * A library pipe shows the inner diameter and roughness the solver uses: roughness is per size
 * (Farshad & Rieke at that size's bore), not the material's representative average, and
 * switching the pipe to Custom starts from those same values so the switch changes no result.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it } from 'vitest';
import type { Override, PipeConnection, PipeSpec } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { libraryProject } from '$lib/testing/helpers';
import { TEST_LIBRARY as LIBRARY } from '$lib/testing/library';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';

function setup() {
	const ws = testWorkspace(pumpTransferExample(), {
		library: { getLibrary: () => Promise.resolve(LIBRARY) }
	});
	ws.nav.jumpTo('V1');
	ws.nav.showConnection('outlet');
	render(WorkspaceView, { workspace: ws });
	const l3 = () => ws.project.connections.find((c) => c.id === 'L3') as PipeConnection;
	return { ws, l3 };
}

describe('PipeSegmentForm', () => {
	it('shows the per-size roughness the solver uses, not the material average', async () => {
		setup();
		const roughness = await screen.findByText((_, el) =>
			Boolean(el?.tagName === 'P' && el.textContent?.trim().startsWith('Roughness'))
		);
		expect(roughness).toHaveTextContent(/^Roughness 0\.03512 mm$/);
		expect(screen.queryByText(/0\.036 mm/)).toBeNull();
	});

	it('labels a roughness override against the size value', async () => {
		const { ws } = setup();
		ws.editConnection('L3', 'change roughness', (c) => ({
			...c,
			piping: { ...c.piping, pipes: [{ ...c.piping.pipes[0]!, roughness: 5e-5 }] }
		}));
		const roughness = await screen.findByText((_, el) =>
			Boolean(el?.tagName === 'P' && el.textContent?.trim().startsWith('Roughness'))
		);
		expect(roughness).toHaveTextContent(/Roughness 0\.05 mm\s+\(override; library 0\.03512 mm\)/);
	});

	it('switching to Custom keeps the bore and per-size roughness', async () => {
		const { l3 } = setup();
		await screen.findByText(/^Roughness/);
		await fireEvent.change(screen.getByRole('combobox', { name: 'Material' }), {
			target: { value: 'custom' }
		});
		expect(l3().piping.pipes[0]).toEqual({
			materialId: 'custom',
			length: 60,
			innerDiameter: 0.07792,
			roughness: 3.512e-5
		});
	});
});

/**
 * Pipes of a project library spec (CLAUDE.md D22; proposal project-library.md §6.2): the Material
 * list holds the project's specs; a pipe of a spec shows the spec's values read-only with its
 * source; "Use a pipe spec for…" states the count before one undo step changes those pipes. Test
 * inputs (made up): libraryProject's specs.
 */
describe('PipeSegmentForm with the project library', () => {
	function setupLibrary(project = libraryProject()) {
		const ws = testWorkspace(project, {
			library: { getLibrary: () => Promise.resolve(LIBRARY) }
		});
		ws.nav.jumpTo('R1');
		ws.nav.showConnection('port_1');
		render(WorkspaceView, { workspace: ws });
		const pipes = () =>
			(ws.store.project.connections.find((c) => c.id === 'L1') as PipeConnection).piping.pipes;
		return { ws, pipes };
	}

	it('shows a spec pipe read-only, with its source and a way to the library', async () => {
		const { ws } = setupLibrary();
		const pipe1 = within(screen.getByRole('region', { name: 'Pipe 1 of 2' }));
		const material = pipe1.getByRole('combobox', { name: 'Material' });
		expect(material).toHaveValue('spec:PS1');
		const groups = [...material.querySelectorAll('optgroup')].map((g) => g.label);
		expect(groups).toEqual(['Project specs']);
		expect(pipe1.getByRole('option', { name: 'Lined 80 mm' })).toBeInTheDocument();
		expect(pipe1.getByRole('option', { name: 'New pipe spec…' })).toBeInTheDocument();
		// No schedule, size or overrides of its own: the spec gives them.
		expect(pipe1.queryByRole('combobox', { name: 'Schedule' })).toBeNull();
		expect(pipe1.queryByText('Overrides (optional)')).toBeNull();
		expect(pipe1.getByText('Source: test input: a bore measured on site')).toBeInTheDocument();
		expect(pipe1.getByText('100 mm')).toBeInTheDocument();
		await fireEvent.click(
			pipe1.getByRole('button', { name: 'Edit NPS 4 measured in the library' })
		);
		const dialog = within(await screen.findByRole('dialog', { name: 'Project library' }));
		expect(dialog.getByRole('region', { name: 'Edit pipe spec PS1' })).toBeInTheDocument();
		expect(ws.libraryFocus).toEqual({ list: 'pipe', edit: 'PS1' });
	});

	it('a spec from the Material list keeps the length; a library material starts at the nearest size', async () => {
		const { ws, pipes } = setupLibrary();
		const pipe2 = within(screen.getByRole('region', { name: 'Pipe 2 of 2' }));
		await fireEvent.change(pipe2.getByRole('combobox', { name: 'Material' }), {
			target: { value: 'spec:PS2' }
		});
		expect(pipes()[1]).toEqual({ specId: 'PS2', length: 12 });
		expect(ws.store.undoLabel).toBe('use pipe spec');

		// PS1 (a 100 mm bore on carbon steel, NPS 4) back to the library: NPS 4 schedule 40.
		const pipe1 = within(screen.getByRole('region', { name: 'Pipe 1 of 2' }));
		await fireEvent.change(pipe1.getByRole('combobox', { name: 'Material' }), {
			target: { value: 'carbon_steel' }
		});
		expect(pipes()[0]).toEqual({
			materialId: 'carbon_steel',
			length: 30,
			schedule: '40',
			nominalSize: 0.1016
		});
	});

	it('Use a pipe spec for… states the count, then changes those pipes in one undo step', async () => {
		const project = libraryProject();
		// Both pipes of L2 and pipe 2 of L1: NPS 4 schedule 40 carbon steel.
		const l2 = project.connections.find((c) => c.id === 'L2') as PipeConnection;
		l2.piping.pipes = [
			{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 7 },
			{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 8 }
		];
		const { ws, pipes } = setupLibrary(project);
		const pipe2 = within(screen.getByRole('region', { name: 'Pipe 2 of 2' }));
		await fireEvent.click(pipe2.getByRole('button', { name: /^Use a pipe spec for pipe 2/ }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Use a pipe spec' }));
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Pipe spec' }), {
			target: { value: 'PS2' }
		});
		const same = dialog.getByRole('radio', { name: /^Every pipe of the same material and size/ });
		expect(same).toBeChecked();
		expect(same.closest('label')).toHaveTextContent('(3 pipes)');
		expect(dialog.getByRole('status')).toHaveTextContent(
			/^3 pipes will use “Lined 80 mm”, each keeping its length/
		);
		await fireEvent.click(dialog.getByRole('button', { name: 'Use for 3 pipes' }));
		expect(screen.queryByRole('dialog', { name: 'Use a pipe spec' })).toBeNull();

		const l2Pipes = () =>
			(ws.store.project.connections.find((c) => c.id === 'L2') as PipeConnection).piping.pipes;
		expect(pipes()[1]).toEqual({ specId: 'PS2', length: 12 });
		expect(l2Pipes()).toEqual([
			{ specId: 'PS2', length: 7 },
			{ specId: 'PS2', length: 8 }
		]);
		// The spec pipe already on PS1 is not of that size: it stays.
		expect(pipes()[0]).toEqual({ specId: 'PS1', length: 30 });
		expect(ws.store.undoLabel).toBe('use pipe spec Lined 80 mm for 3 pipes');
		expect(ws.notice?.text).toBe('3 pipes now use “Lined 80 mm”. Undo reverts all of them.');
		ws.undo();
		expect(l2Pipes()[0]).toEqual({
			materialId: 'carbon_steel',
			schedule: '40',
			nominalSize: 0.1016,
			length: 7
		});
	});

	it('a refused Use for… says why in its dialog, which stays open, and changes nothing', async () => {
		// 29 changes (of absent elements: kept, never applied); 3 pipes more pass the limit of 30.
		const project = libraryProject();
		const l2 = project.connections.find((c) => c.id === 'L2') as PipeConnection;
		l2.piping.pipes = [
			{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 7 },
			{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 8 }
		];
		const many: Override[] = Array.from({ length: 29 }, (_, i) => ({
			kind: 'component',
			componentId: `X${i}`,
			field: 'status',
			value: 'off'
		}));
		project.scenarios = [{ id: 'S1', name: 'Many', overrides: many }];
		const { ws } = setupLibrary(project);
		ws.setCase('S1');
		await tick();
		const before = JSON.stringify(ws.store.project);
		const pipe2 = within(screen.getByRole('region', { name: 'Pipe 2 of 2' }));
		await fireEvent.click(pipe2.getByRole('button', { name: /^Use a pipe spec for pipe 2/ }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Use a pipe spec' }));
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Pipe spec' }), {
			target: { value: 'PS2' }
		});
		expect(dialog.queryByRole('alert')).toBeNull();
		await fireEvent.click(dialog.getByRole('button', { name: 'Use for 3 pipes' }));

		// The reason is in the dialog, not in the page's notice behind it (inert under the modal).
		expect(screen.getByRole('dialog', { name: 'Use a pipe spec' })).toBeInTheDocument();
		expect(dialog.getByRole('alert')).toHaveTextContent(
			'Could not use pipe spec Lined 80 mm for 3 pipes: A scenario holds at most 30 changes.'
		);
		expect(ws.notice).toBeNull();
		expect(JSON.stringify(ws.store.project)).toBe(before);
		expect(ws.store.project.scenarios?.[0]?.overrides).toHaveLength(29);

		// A new choice clears it; the press that fits applies, and the dialog closes.
		await fireEvent.click(dialog.getByRole('radio', { name: /^This pipe/ }));
		expect(dialog.queryByRole('alert')).toBeNull();
		await fireEvent.click(dialog.getByRole('button', { name: 'Use for 1 pipe' }));
		expect(screen.queryByRole('dialog', { name: 'Use a pipe spec' })).toBeNull();
		expect(ws.store.project.scenarios?.[0]?.overrides).toHaveLength(30);
	});

	it('a full library offers "New pipe spec…" disabled, saying why, here and in Use a pipe spec for…', async () => {
		// 100 made-up specs, PS1... (PS1 still the one pipe 1 uses): as many as a project may hold.
		const project = libraryProject();
		project.pipeLibrary = Array.from({ length: 100 }, (_, i): PipeSpec => ({
			id: `PS${i + 1}`,
			name: `Spec ${i + 1}`,
			source: 'Test input: a made-up bore',
			materialId: 'custom',
			innerDiameter: 0.05,
			roughness: 1e-5
		}));
		setupLibrary(project);
		const pipe1 = within(screen.getByRole('region', { name: 'Pipe 1 of 2' }));
		const material = pipe1.getByRole('combobox', { name: 'Material' });
		expect(
			pipe1.getByRole('option', { name: 'New pipe spec… (a project holds at most 100)' })
		).toBeDisabled();
		expect(pipe1.queryByRole('option', { name: 'New pipe spec…' })).toBeNull();
		// Chosen all the same (a disabled option can be set from script): nothing opens.
		await fireEvent.change(material, { target: { value: 'new-spec' } });
		await tick();
		expect(screen.queryByRole('dialog', { name: 'Project library' })).toBeNull();
		expect(material).toHaveValue('spec:PS1');

		await fireEvent.click(pipe1.getByRole('button', { name: /^Use a pipe spec for pipe 1/ }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Use a pipe spec' }));
		expect(
			dialog.getByRole('option', { name: 'New pipe spec… (a project holds at most 100)' })
		).toBeDisabled();
		await fireEvent.change(dialog.getByRole('combobox', { name: 'Pipe spec' }), {
			target: { value: 'new-spec' }
		});
		await fireEvent.click(dialog.getByRole('button', { name: 'Define the spec…' }));
		expect(screen.getByRole('dialog', { name: 'Use a pipe spec' })).toBeInTheDocument();
		expect(screen.queryByRole('dialog', { name: 'Project library' })).toBeNull();
	});

	it('in a scenario a spec is a change of the scenario, and no new spec is offered', async () => {
		const project = libraryProject();
		project.scenarios = [{ id: 'S1', name: 'Lined', overrides: [] }];
		const { ws, pipes } = setupLibrary(project);
		ws.setCase('S1');
		await tick();
		const pipe2 = within(screen.getByRole('region', { name: 'Pipe 2 of 2' }));
		const material = pipe2.getByRole('combobox', { name: 'Material' });
		expect(pipe2.queryByRole('option', { name: 'New pipe spec…' })).toBeNull();
		await fireEvent.change(material, { target: { value: 'spec:PS2' } });
		// The base keeps its pipe; the scenario changes it.
		expect(pipes()[1]?.specId).toBeUndefined();
		expect(ws.store.project.scenarios?.[0]?.overrides).toEqual([
			{
				kind: 'pipe',
				connectionId: 'L1',
				pipeIndex: 1,
				field: 'spec',
				value: { specId: 'PS2' }
			}
		]);
	});
});
