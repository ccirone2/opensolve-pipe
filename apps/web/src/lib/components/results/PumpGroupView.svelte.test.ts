/**
 * The Pumps together card in the Pumps view (CLAUDE.md D20, proposal pump-groups.md §4, §6.1):
 * shown with two pumps or more, closed by default; opening it asks for the group curve of the
 * suggested group for this solve; the members are page state, kept when the case shown changes,
 * and the card asks for the case shown (its scenario id). The solves and group curves are the
 * shared fixture's real API answers, given by a fake solver.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TopologyError } from '$lib/api/client';
import type { Project, PumpGroupCurveResponse, SolveResponse } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { withScenarios } from '$lib/utils/scenarios';
import { formatNumber } from '$lib/utils/units';

// jsdom has no canvas: a stub context lets the chart be "drawn" (Chart.js says it cannot, on the
// console, which these tests silence).
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

interface FixtureCase {
	name: string;
	project: Project;
	solve: SolveResponse;
	groupCurve: { status: number; body: unknown };
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;

interface Call {
	pumpIds: readonly string[];
	scenarioId?: string;
}

function setup(project: Project, c: FixtureCase) {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	const calls: Call[] = [];
	const solver: Solver = {
		solve: async () => structuredClone(c.solve),
		groupCurve: async (_project, pumpIds, options) => {
			calls.push({ pumpIds, ...(options?.scenarioId ? { scenarioId: options.scenarioId } : {}) });
			return structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
		}
	};
	const ws = testWorkspace(project, { solver });
	render(WorkspaceView, { workspace: ws });
	return { ws, calls };
}

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const card = () => results().getByRole('region', { name: /^Pumps together/ }) as HTMLElement;

async function showPumps() {
	await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
}

describe('the Pumps together card in the Pumps view', () => {
	it('is closed by default; opened, it asks for the suggested group’s curve and shows its shares', async () => {
		const c = named('parallel-ideal');
		const { calls } = setup(structuredClone(c.project), c);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		const toggle = within(card()).getByRole('button', { name: /^Pumps together/ });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(calls).toEqual([]);
		await fireEvent.click(toggle);
		await waitFor(() => expect(calls).toEqual([{ pumpIds: ['PA', 'PB'] }]));
		const duty = (c.groupCurve.body as PumpGroupCurveResponse).duty!;
		const table = within(card()).getByRole('table', { name: 'The pumps in the group' });
		await waitFor(() =>
			expect(within(table).getByText(formatNumber(duty.members[0]!.share! * 100, 4))).toBeVisible()
		);
		expect(
			within(card()).getByRole('figure', { name: 'Pump PA and Pump PB in parallel' })
		).toBeVisible();
		// Asked once per solve.
		await fireEvent.click(toggle);
		await fireEvent.click(toggle);
		expect(calls).toHaveLength(1);
	});

	it('keeps the members when the case shown changes, and asks for that case', async () => {
		const c = named('ladder');
		const project = withScenarios(structuredClone(c.project), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const { ws, calls } = setup(project, c);
		await ws.store.solveAll();
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls).toEqual([{ pumpIds: ['P1', 'P2', 'P3'] }]));
		await fireEvent.click(within(card()).getByRole('checkbox', { name: /Pump P1/ }));
		await waitFor(() => expect(calls.at(-1)).toEqual({ pumpIds: ['P2', 'P3'] }));
		ws.setCase('S1');
		await waitFor(() => expect(calls.at(-1)).toEqual({ pumpIds: ['P2', 'P3'], scenarioId: 'S1' }));
		const boxes = within(card()).getAllByRole('checkbox') as HTMLInputElement[];
		expect(boxes.map((b) => [b.closest('label')!.textContent!.trim(), b.checked])).toEqual([
			['Pump P1', false],
			['■ Pump P2', true],
			['★ Pump P3', true]
		]);
		// The case is named on the figure (the fake answers with the fixture's three-pump station).
		expect(
			within(card()).getByRole('figure', { name: /^Pump .* in parallel, Winter$/ })
		).toBeVisible();
	});

	it('shows no values and asks nothing for a solve that did not converge', async () => {
		const c = named('parallel-ideal');
		const notConverged = structuredClone(c);
		notConverged.solve.success = false;
		notConverged.solve.solvedState.converged = false;
		const { calls } = setup(structuredClone(c.project), notConverged);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Did not converge' });
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		expect(
			within(card()).getByText(
				'This solve did not converge: its values are not a solution, so the card shows none.'
			)
		).toBeVisible();
		expect(within(card()).queryByRole('figure')).toBeNull();
		expect(calls).toEqual([]);
	});

	it('uses nothing of the earlier results shown after a failed solve (Compare’s rule)', async () => {
		const c = named('parallel-ideal');
		let solves = 0;
		HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
		const calls: Call[] = [];
		const ws = testWorkspace(structuredClone(c.project), {
			solver: {
				solve: async () => {
					if (++solves === 1) return structuredClone(c.solve);
					throw new TopologyError('The network cannot be solved: 1 topology issue(s).', [
						{
							code: 'UNCONNECTED_PORT',
							message: "port 'T2:run_outlet' is not connected; connect it or add a plug",
							componentIds: ['T2'],
							connectionIds: []
						}
					]);
				},
				groupCurve: async (_p, pumpIds) => {
					calls.push({ pumpIds });
					return structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
				}
			}
		});
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		expect(ws.remove('R2', false)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await fireEvent.click(
			await results().findByRole('button', { name: 'Show the earlier results' })
		);
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		expect(
			within(card()).getByText(
				'The latest solve failed; the card shows nothing from an earlier version of the project.'
			)
		).toBeVisible();
		expect(within(card()).queryByRole('table')).toBeNull();
		expect(calls).toEqual([]);
	});
});
