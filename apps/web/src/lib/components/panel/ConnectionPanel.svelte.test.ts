/**
 * Build's Disconnect says what the step did in one notice: its own sentence, then the renames of
 * the names that followed their pumps in the same undo step (CLAUDE.md D24, proposal
 * pump-lineups.md §4.5: every rename is said). The project is a made-up test input
 * (testing/lineups.ts); nothing is solved.
 */
import { fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { station } from '$lib/testing/lineups';
import { testWorkspace } from '$lib/testing/workspace';
import { withScenarios } from '$lib/utils/scenarios';

describe('Disconnect', () => {
	it('says the connection removed, then the rename of a case whose station it changed', async () => {
		const ws = testWorkspace(
			withScenarios(station(4), [
				{
					id: 'S1',
					name: '3 of 4 running (Pump P4 off)',
					overrides: [{ kind: 'component', componentId: 'P4', field: 'status', value: 'off' }]
				}
			])
		);
		ws.nav.jumpTo('P4');
		ws.nav.showConnection('discharge');
		render(WorkspaceView, { workspace: ws });
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: /Disconnect/ }));
		// P4 left the station (the frame changed): its case is named pump by pump.
		expect(ws.scenarios.map((s) => s.name)).toEqual(['Pump P4 off']);
		expect(ws.store.undoLabel).toBe('remove connection DP4');
		const said =
			'Connection DP4 removed. Undo restores it. «3 of 4 running (Pump P4 off)» is now «Pump P4 off»: a name the app made follows its pumps until you rename it.';
		expect(ws.notice).toMatchObject({ kind: 'info', text: said });
		await tick();
		expect(screen.getByText(said)).toBeInTheDocument();
	});
});
