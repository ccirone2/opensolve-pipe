/**
 * A new control valve's setpoint is 0, for the user to set; until it is set the form says what
 * 0 means (an FCV at 0 shuts the line).
 */
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { insertComponentInConnection } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';

describe('ControlValveForm', () => {
	it('warns about the untouched 0 setpoint of a new PRV, and of an FCV after a switch', async () => {
		const base = pumpTransferExample();
		const prv = createComponent('prv', base);
		const ws = testWorkspace(insertComponentInConnection(base, 'L3', prv));
		ws.nav.jumpTo(prv.id);
		render(WorkspaceView, { workspace: ws });

		const setpoint = screen.getByRole('textbox', { name: 'Outlet pressure setpoint (kPa(g))' });
		expect(setpoint).toHaveValue('0');
		expect(setpoint).toHaveAccessibleDescription(/Set the pressure to hold/);

		await fireEvent.change(screen.getByRole('combobox', { name: 'Valve type' }), {
			target: { value: 'fcv' }
		});
		const flow = screen.getByRole('textbox', { name: 'Flow setpoint (L/s)' });
		expect(flow).toHaveAccessibleDescription(/at 0 the valve shuts the line/);

		await fireEvent.input(flow, { target: { value: '5' } });
		await fireEvent.change(flow);
		expect(flow).not.toHaveAccessibleDescription(/shuts the line/);
	});
});
