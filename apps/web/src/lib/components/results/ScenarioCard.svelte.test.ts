/**
 * The scenario card's heading after a rename that leaves the case current (CLAUDE.md D24, proposal
 * pump-lineups.md §5, §10.1 "L1a, workspace"): names are not in the hydraulic fingerprint, so a
 * pump's rename keeps the solve current while the app-made name follows it; the heading names the
 * case by its stored name and the name it was solved under, and the Methods view by its stored name. The solves are the shared fixture's
 * real API answers for the `one-off` case and its scenarios, given by a fake solver by scenario id.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it } from 'vitest';
import type { Project, SolveResponse } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';

interface FixtureCase {
	name: string;
	project: Project;
	solve: SolveResponse;
	scenarioCases: Record<string, { solve: SolveResponse }>;
}
const oneOff = (fixture.cases as unknown as FixtureCase[]).find((c) => c.name === 'one-off')!;

function setup() {
	const solver: Solver = {
		solve: async (_p, _o, request) =>
			structuredClone(
				(request?.scenarioId && oneOff.scenarioCases[request.scenarioId]?.solve) || oneOff.solve
			)
	};
	const ws = testWorkspace(structuredClone(oneOff.project), { solver });
	render(WorkspaceView, { workspace: ws });
	return ws;
}

const card = () =>
	within(screen.getByRole('region', { name: 'Results' })).getByRole('region', {
		name: /^Scenario: /
	});

describe('the scenario card’s heading', () => {
	it('names the case by its stored name, as solved when they are the same', async () => {
		const ws = setup();
		ws.setCase('S1');
		await ws.solve();
		await tick();
		const heading = within(card()).getByRole('heading', { level: 3 });
		expect(heading.textContent?.replace(/\s+/g, ' ').trim()).toBe('Scenario: Pump PA off (S1)');
		expect(card()).toHaveAccessibleName('Scenario: Pump PA off (S1)');
	});

	it('after a pump’s rename the name follows, and the heading adds the name solved under', async () => {
		const ws = setup();
		ws.setCase('S1');
		await ws.solve();
		ws.editComponent('PA', 'rename pump', (c) => {
			c.name = 'Duty pump';
		});
		await tick();
		expect(ws.scenarios.map((s) => s.name)).toEqual([
			'Duty pump off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off'
		]);
		// Still current: a name is not a hydraulic input.
		expect(ws.store.results.stale).toBe(false);
		expect(ws.store.undoLabel).toBe('rename pump in Duty pump off');
		const heading = within(card()).getByRole('heading', { level: 3 });
		expect(heading.textContent?.replace(/\s+/g, ' ').trim()).toBe(
			'Scenario: Duty pump off (S1) (solved as «Pump PA off»)'
		);
		expect(card()).toHaveAccessibleName('Scenario: Duty pump off (S1) (solved as «Pump PA off»)');
		// The Methods view names it the same way as the export's Methods text (solvedCaseWords).
		const results = within(screen.getByRole('region', { name: 'Results' }));
		await fireEvent.click(results.getByRole('tab', { name: 'Methods' }));
		expect(
			results.getByRole('heading', {
				name: 'Calculation methods and assumptions for scenario Duty pump off'
			})
		).toBeInTheDocument();
	});
});
