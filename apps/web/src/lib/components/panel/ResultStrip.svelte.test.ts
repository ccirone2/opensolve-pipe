/**
 * Results in context (proposal ui-ux-refinement.md item 6): the current element's key results
 * from the last solve, in Build. The solve results are made-up test inputs (testing/results.ts);
 * the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import { TopologyError } from '$lib/api/client';
import type { Component, SolveResponse } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { updateComponent } from '$lib/utils/edit';

const build = () => within(screen.getByRole('region', { name: 'Build' }));
const strips = () => build().queryAllByRole('group', { name: /^Last solve/ });

/** "Label (unit): value" of each value shown, with the label's no-break space as a space. */
function values(strip: HTMLElement): string[] {
	return [...strip.querySelectorAll('dl > div')].map((d) =>
		`${d.querySelector('dt')?.textContent?.trim()}: ${d.querySelector('dd')?.textContent?.trim()}`.replace(
			/\u00a0/g,
			' '
		)
	);
}

function mount(
	answer: () => Promise<SolveResponse> = () => Promise.resolve(response(pumpTransferSolved()))
) {
	const solve = vi.fn(answer);
	const ws = testWorkspace(pumpTransferExample(), { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	return { ws, solve };
}

describe('results in context', () => {
	it('shows nothing before a first solve, then the key values of the element shown', async () => {
		const { ws } = mount();
		ws.nav.jumpTo('P1');
		await tick();
		expect(strips()).toHaveLength(0);
		await ws.solve();
		ws.pane = 'build';
		await tick();
		const [strip] = strips();
		expect(values(strip!)).toEqual([
			'Status: Running',
			'Flow (L/s): 20',
			'Head (m): 22',
			'NPSH margin (m): 9'
		]);
		expect(within(strip!).queryByText(/Out of date/)).toBeNull();
	});

	it('shows a connection’s flow, velocity and head loss in Piping', async () => {
		const { ws } = mount();
		await ws.solve();
		ws.nav.jumpTo('V1');
		ws.nav.showConnection('outlet');
		ws.pane = 'build';
		await tick();
		const connection = strips().at(-1)!;
		expect(values(connection)).toEqual(['Flow (L/s): 20', 'Velocity (m/s): 4', 'Head loss (m): 8']);
	});

	it('marks the values out of date after an edit, and says when the element was not solved', async () => {
		const { ws } = mount();
		await ws.solve();
		ws.nav.jumpTo('P1');
		ws.pane = 'build';
		ws.edit(
			(p) => updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.9 }) as Component),
			'change speed'
		);
		await tick();
		const [strip] = strips();
		expect(within(strip!).getByText('Out of date: solve again')).toBeInTheDocument();
		expect(values(strip!)).toContain('Flow (L/s): 20');

		await fireEvent.click(build().getByRole('button', { name: 'Add after' }));
		const dialog = await screen.findByRole('dialog', { name: /^Add after/ });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		await tick();
		expect(within(strips()[0]!).getByText(/^Not in the last solve/)).toBeInTheDocument();
	});

	it('gives no values for a solve that did not converge, and nothing after a failed solve', async () => {
		let answer: Promise<SolveResponse> = Promise.resolve(
			response(pumpTransferSolved({ converged: false }))
		);
		const { ws } = mount(() => answer);
		ws.nav.jumpTo('P1');
		await ws.solve();
		ws.pane = 'build';
		await tick();
		const [strip] = strips();
		expect(within(strip!).getByText(/^The last solve did not converge/)).toBeInTheDocument();
		expect(strip!.querySelector('dl')).toBeNull();

		answer = Promise.reject(
			new TopologyError('The network cannot be solved.', [
				{ code: 'NO_FIXED_HEAD', message: 'no fixed head', componentIds: [], connectionIds: [] }
			])
		);
		await ws.solve();
		ws.pane = 'build';
		await tick();
		expect(strips()).toHaveLength(0);
	});

	it('lists the element’s flags, and Trace opens its trace without moving Build', async () => {
		const flags = [
			flag({
				code: 'CAVITATION',
				severity: 'invalid',
				message: 'The pump would cavitate',
				componentId: 'P1'
			}),
			flag({
				code: 'PUMP_OUTSIDE_CURVE',
				severity: 'warning',
				message: 'Outside the curve',
				componentId: 'P1'
			}),
			flag({ code: 'NPSH_NOT_CHECKED', severity: 'info', message: 'A third', componentId: 'P1' })
		];
		const { ws } = mount(() => Promise.resolve(response(pumpTransferSolved({ flags }))));
		await ws.solve();
		ws.nav.jumpTo('P1');
		ws.pane = 'build';
		await tick();
		const [strip] = strips();
		expect(within(strip!).getByText(/The pump would cavitate/)).toBeInTheDocument();
		expect(within(strip!).getByText(/Outside the curve/)).toBeInTheDocument();
		expect(within(strip!).getByText('1 more in the trace.')).toBeInTheDocument();

		const path = ws.nav.path;
		await fireEvent.click(within(strip!).getByRole('button', { name: 'Trace of Transfer pump' }));
		expect(ws.inspected).toEqual({ kind: 'component', id: 'P1' });
		expect(ws.nav.path).toEqual(path);
	});

	it('gives each pipe its velocity beside its size, out of date after edits, gone when pipes change', async () => {
		const { ws } = mount();
		await ws.solve();
		ws.nav.jumpTo('P1');
		ws.nav.showConnection('discharge');
		ws.pane = 'build';
		await tick();
		// A size select with the pipe library, a number field without it (as in these tests).
		const size = () => build().getByLabelText(/^Size/);
		// The fixture's pipe in L2 runs at 2 m/s.
		expect(size()).toHaveAccessibleDescription('Velocity at the last solve: 2 m/s.');
		ws.edit(
			(p) => updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.9 }) as Component),
			'change speed'
		);
		await tick();
		expect(size()).toHaveAccessibleDescription('Velocity at the last solve: 2 m/s (out of date).');
		await fireEvent.click(build().getByRole('button', { name: /^Add pipe/ }));
		await tick();
		for (const field of build().getAllByLabelText(/^Size/)) {
			expect(field).not.toHaveAccessibleDescription(/Velocity/);
		}
	});
});
