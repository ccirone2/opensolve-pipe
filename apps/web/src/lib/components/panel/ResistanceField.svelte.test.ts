/**
 * Valve resistance: a number entered as K, Cv or Kv is stored with its kind. Changing the kind
 * never relabels the stored number as a different quantity (K = 5 is not Cv = 5).
 */
import { fireEvent, render, screen } from '@testing-library/svelte';
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
