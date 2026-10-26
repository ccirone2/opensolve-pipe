/**
 * The Pumps view's chart and the export's rule (proposal export.md §2.1, §3.4, §5.5): the other
 * cases drawn on the chart are those Compare shows (a case whose latest solve failed, that a
 * stopped run did not reach, or whose solve did not converge is not drawn), and Download image
 * says why no image can be made of results that are not a solution, of the earlier results shown
 * after a failed solve, or while a calculation runs. The solved states are made-up test inputs.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { NetworkError, TopologyError } from '$lib/api/client';
import type { Component, Project, SolveResponse } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { updateComponent } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { withScenarios } from '$lib/utils/scenarios';

// The chart: jsdom has no canvas. A stub context lets the chart be "drawn" (Chart.js cannot draw on
// it and says so on the console, which these tests silence); Download image then needs only the
// reasons the results give. (A mock of './chart-setup' does not reach the chart through the
// workspace in this test runner; PumpChart.svelte.test.ts mocks it for the chart itself.)
const getContext = HTMLCanvasElement.prototype.getContext;
const consoleError = console.error;
beforeEach(() => {
	console.error = (...args: unknown[]) => {
		if (String(args[0]).startsWith('Failed to create chart')) return;
		consoleError(...args);
	};
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	console.error = consoleError;
});

function setup(project: Project, solver: Solver) {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	const ws = testWorkspace(project, { solver });
	render(WorkspaceView, { workspace: ws });
	return ws;
}

const results = () => within(screen.getByRole('region', { name: 'Results' }));

async function showPumps() {
	await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
}

const imageButton = () =>
	results().getByRole('button', { name: /^Download image of the pump and system curves/ });

const notConverged = () => response(pumpTransferSolved({ converged: false }), { success: false });

describe('other cases on the pump chart (Compare’s rule)', () => {
	it('draws only cases whose last solve of the project converged', async () => {
		let stop = false;
		const ws = setup(
			withScenarios(pumpTransferExample(), [
				{ id: 'S1', name: 'Converged', overrides: [] },
				{ id: 'S2', name: 'Not converged', overrides: [] },
				{ id: 'S3', name: 'Failed', overrides: [] },
				{ id: 'S4', name: 'Not reached', overrides: [] }
			]),
			{
				solve: async (_p, _o, request) => {
					if (stop && request?.scenarioId === 'S3')
						throw new NetworkError('The server is busy.', 503, 'SERVER_BUSY');
					return request?.scenarioId === 'S2' ? notConverged() : response(pumpTransferSolved());
				}
			}
		);
		await ws.solveAll();
		// Every case out of date, then a run that stops at S3: S3 failed, S4 not reached, both
		// keeping an earlier converged response.
		ws.store.update(
			(p) => updateComponent(p, 'R1', (c) => ({ ...c, liquidLevel: 3.4 }) as Component),
			'change level'
		);
		stop = true;
		await ws.solveAll();
		await tick();
		expect(['S1', 'S2', 'S3', 'S4'].map((c) => ws.store.caseStatus(c))).toEqual([
			'solved',
			'not_converged',
			'failed',
			'not_reached'
		]);
		await showPumps();
		const cases = await results().findByRole('group', { name: 'Cases on the chart' });
		expect(
			within(cases)
				.getAllByRole('checkbox')
				.map((c) => c.closest('label')!.textContent!.trim())
		).toEqual(['△ Converged']);
	});
});

describe('Download image under the chart', () => {
	it('is available for a converged solve once the chart is drawn', async () => {
		setup(pumpTransferExample(), { solve: async () => response(pumpTransferSolved()) });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		await waitFor(() => expect(imageButton()).not.toHaveAttribute('aria-disabled', 'true'));
	});

	it('is unavailable for a solve that did not converge, current or out of date', async () => {
		const ws = setup(pumpTransferExample(), { solve: async () => notConverged() });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Did not converge' });
		await showPumps();
		const reason =
			'This solve did not converge: its values are not a solution, so no image is made.';
		await waitFor(() => expect(imageButton()).toHaveAccessibleDescription(reason));
		expect(imageButton()).toHaveAttribute('aria-disabled', 'true');
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		await waitFor(() => expect(ws.store.results.stale).toBe(true));
		expect(ws.store.caseStatus(null)).toBe('stale');
		expect(imageButton()).toHaveAccessibleDescription(reason);
	});

	it('is unavailable for the earlier results shown after a failed solve', async () => {
		let calls = 0;
		const ws = setup(pumpTransferExample(), {
			solve: async () => {
				if (++calls === 1) return response(pumpTransferSolved());
				throw new TopologyError('The network cannot be solved: 1 topology issue(s).', [
					{
						code: 'UNCONNECTED_PORT',
						message: "port 'V1:outlet' is not connected; connect it or add a plug",
						componentIds: ['V1'],
						connectionIds: []
					}
				]);
			}
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		expect(ws.remove('R2', false)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await fireEvent.click(
			await results().findByRole('button', { name: 'Show the earlier results' })
		);
		await showPumps();
		await waitFor(() =>
			expect(imageButton()).toHaveAccessibleDescription(
				'The latest solve failed; the chart shows results from an earlier version of the project, so no image is made.'
			)
		);
	});

	it('is unavailable while a solve runs', async () => {
		let release: (r: SolveResponse) => void = () => {};
		let calls = 0;
		const ws = setup(pumpTransferExample(), {
			solve: () =>
				++calls === 1
					? Promise.resolve(response(pumpTransferSolved()))
					: new Promise<SolveResponse>((resolve) => (release = resolve))
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		await waitFor(() => expect(imageButton()).not.toHaveAttribute('aria-disabled', 'true'));
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		void ws.solve();
		await waitFor(() =>
			expect(imageButton()).toHaveAccessibleDescription(
				'A solve is running; export when it finishes, or Cancel in the header stops it.'
			)
		);
		release(response(pumpTransferSolved()));
		await waitFor(() => expect(imageButton()).not.toHaveAttribute('aria-disabled', 'true'));
	});
});
