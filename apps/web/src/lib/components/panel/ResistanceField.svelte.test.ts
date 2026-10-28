/**
 * Valve resistance: a number entered as K, Cv or Kv is stored with its kind. Changing the kind
 * never relabels the stored number as a different quantity (K = 5 is not Cv = 5).
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { componentById } from '$lib/utils/graph';
import { pumpTransferExample } from '$lib/utils/examples';
import { SI_UNITS } from '$lib/utils/units';
import type { IsolationValve } from '$lib/api/types';
import ResistanceField from './ResistanceField.svelte';

async function type(input: HTMLElement, text: string) {
	await fireEvent.input(input, { target: { value: text } });
	await fireEvent.change(input);
}

describe('ResistanceField', () => {
	it('never stores the old number under a new kind', async () => {
		const onchange = vi.fn();
		render(ResistanceField, {
			value: { kind: 'K', value: 0.15 },
			defaultLabel: 'Crane',
			units: SI_UNITS,
			onchange
		});
		const select = screen.getByRole('combobox', { name: 'Resistance given as' });
		for (const kind of ['Cv', 'Kv'] as const) {
			await fireEvent.change(select, { target: { value: kind } });
		}
		expect(onchange).not.toHaveBeenCalledWith({ kind: 'Cv', value: 0.15 });
		expect(onchange).not.toHaveBeenCalledWith({ kind: 'Kv', value: 0.15 });
		expect(onchange.mock.calls.every(([v]) => v === null)).toBe(true);
	});

	it('on a valve: K = 5, then Cv clears the value until a Cv is entered', async () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.nav.jumpTo('V1');
		render(WorkspaceView, { workspace: ws });
		const resistance = () => (componentById(ws.project, 'V1') as IsolationValve).resistance;
		const select = screen.getByRole('combobox', { name: 'Resistance given as' });

		await fireEvent.change(select, { target: { value: 'K' } });
		await type(screen.getByRole('textbox', { name: 'K' }), '5');
		expect(resistance()).toEqual({ kind: 'K', value: 5 });

		await fireEvent.change(select, { target: { value: 'Cv' } });
		expect(resistance()).toBeUndefined();
		expect(select).toHaveValue('Cv');
		const cv = screen.getByRole('textbox', { name: 'Cv' });
		expect(cv).toHaveValue('');
		expect(screen.getByText('Enter Cv to use it; until then the default applies.')).toBeVisible();

		await type(cv, '120');
		expect(resistance()).toEqual({ kind: 'Cv', value: 120 });

		// One undo step back to the default, another back to K = 5.
		ws.store.undo();
		expect(resistance()).toBeUndefined();
		ws.store.undo();
		expect(resistance()).toEqual({ kind: 'K', value: 5 });
	});
});

describe('ResistanceField with the project library', () => {
	const entries = [
		{ id: 'RS1', name: 'Gate, open', source: 'test input', kind: 'Cv' as const, value: 900 },
		{
			id: 'RS2',
			name: 'Butterfly (K)',
			source: 'test input: a made-up K',
			kind: 'K' as const,
			value: 0.3,
			referenceDiameter: 0.09
		}
	];

	it('offers the entries; an entry is used by reference and shown with its source', async () => {
		const onchange = vi.fn();
		const onlibrary = vi.fn();
		render(ResistanceField, {
			value: { kind: 'library', id: 'RS2' },
			defaultLabel: 'Crane',
			units: SI_UNITS,
			entries,
			onlibrary,
			onchange
		});
		const select = screen.getByRole('combobox', { name: 'Resistance given as' });
		expect(select).toHaveValue('entry:RS2');
		expect(screen.getByText('K 0.3 at 90 mm')).toBeInTheDocument();
		expect(screen.getByText('Source: test input: a made-up K')).toBeInTheDocument();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Edit Butterfly (K) in the library' })
		);
		expect(onlibrary).toHaveBeenCalledWith('RS2');

		await fireEvent.change(select, { target: { value: 'entry:RS1' } });
		expect(onchange).toHaveBeenLastCalledWith({ kind: 'library', id: 'RS1' });
		// A kind of its own: the reference goes, and the default applies until a number is in.
		await fireEvent.change(select, { target: { value: 'Cv' } });
		expect(onchange).toHaveBeenLastCalledWith(null);
		await fireEvent.change(select, { target: { value: 'new-entry' } });
		expect(onlibrary).toHaveBeenLastCalledWith(null);
	});

	it('says when an entry is not in the library; no new entry where the library is read-only', () => {
		render(ResistanceField, {
			value: { kind: 'library', id: 'RS9' },
			defaultLabel: 'Crane',
			units: SI_UNITS,
			entries,
			onlibrary: () => {},
			editLibrary: false,
			onchange: () => {}
		});
		expect(
			screen.getByRole('option', { name: 'RS9 (not in the project library)' })
		).toBeInTheDocument();
		expect(screen.queryByRole('option', { name: 'New entry…' })).toBeNull();
		expect(
			screen.getByText(/^Resistance entry RS9 is not in the project library/)
		).toBeInTheDocument();
	});
});

describe("a valve's library resistance in a scenario", () => {
	it('is a change of the scenario, marked with the base value and Reset', async () => {
		const project = pumpTransferExample();
		project.resistanceLibrary = [
			{ id: 'RS1', name: 'Gate, open', source: 'test input', kind: 'Cv', value: 900 }
		];
		project.scenarios = [{ id: 'S1', name: 'Vendor B', overrides: [] }];
		const ws = testWorkspace(project);
		ws.nav.jumpTo('V1');
		ws.setCase('S1');
		render(WorkspaceView, { workspace: ws });
		const select = screen.getByRole('combobox', { name: 'Resistance given as' });
		expect(within(select).queryByRole('option', { name: 'New entry…' })).toBeNull();
		await fireEvent.change(select, { target: { value: 'entry:RS1' } });
		expect(ws.store.project.scenarios?.[0]?.overrides).toEqual([
			{
				kind: 'component',
				componentId: 'V1',
				field: 'resistance',
				value: { kind: 'library', id: 'RS1' }
			}
		]);
		expect((componentById(ws.store.project, 'V1') as IsolationValve).resistance).toBeUndefined();
		expect(
			await screen.findByText('Changed in this scenario. Base value Default.')
		).toBeInTheDocument();
		expect(
			screen.getByRole('button', { name: 'Show Gate, open in the library' })
		).toBeInTheDocument();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Reset Resistance to the base value, Default' })
		);
		expect(ws.store.project.scenarios?.[0]?.overrides).toEqual([]);
	});
});
