/**
 * Results → Checks and the Summary's Design checks card (CLAUDE.md D19; proposal
 * design-checks.md §5), on the real API's response of the shared fixture's `design-checks` case
 * (export_input.py: every check on, US display units): a view after Summary only when the solve
 * has checks; not met, then met, then not evaluated; each naming its element (a link to its
 * trace), its value against its limits and its limits' source, with the server's words under
 * Details; the Summary counts them and names those not met. Checks never mark the Results tab.
 * The API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { SolveResponse } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { fixtureInput } from '$lib/utils/export/export-testing.testing';

const results = () => within(screen.getByRole('region', { name: 'Results' }));

async function solveFixture(withChecks = true) {
	const input = fixtureInput('design-checks');
	const answer = structuredClone(input.cases[0]!.response!) as SolveResponse;
	if (!withChecks) answer.solvedState.designChecks = [];
	const solve = vi.fn(() => Promise.resolve(answer));
	const ws = testWorkspace(input.project, { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	await ws.solve();
	await results().findByRole('heading', { name: 'Converged' });
	return { ws, answer };
}

const tabNames = () =>
	within(results().getByRole('tablist', { name: 'Results view' }))
		.getAllByRole('tab')
		.map((t) => t.textContent?.trim());

describe('the Checks view', () => {
	it('follows Summary only when the solve has checks', async () => {
		await solveFixture();
		expect(tabNames().slice(0, 2)).toEqual(['Summary', 'Checks']);
	});

	it('is not a view without checks', async () => {
		await solveFixture(false);
		expect(tabNames()).not.toContain('Checks');
		expect(results().queryByRole('region', { name: 'Design checks' })).toBeNull();
	});

	it('lists not met, met and not evaluated, each with its element, words and source', async () => {
		const { ws } = await solveFixture();
		await fireEvent.click(results().getByRole('tab', { name: 'Checks' }));
		const view = within(results().getByRole('tabpanel', { name: 'Checks' }));
		const groups = view.getAllByRole('region').map((r) => r.getAttribute('aria-labelledby'));
		expect(groups).toHaveLength(4); // three outcomes and the presets' sources
		const headings = view
			.getAllByRole('heading', { level: 3 })
			.map((h) => h.textContent?.replace(/\s+/g, ' ').trim());
		expect(headings).toEqual([
			'✕ Not met (3)',
			'✓ Met (4)',
			'– Not evaluated (1)',
			'Sources of the presets'
		]);
		const notMet = within(view.getByRole('region', { name: 'Not met (3)' }));
		const items = notMet.getAllByRole('listitem');
		expect(items[0]).toHaveTextContent(
			/^Transfer pump\s*Motor power\s*Shaft power [\d.]+ hp, above the motor's rated 5\.364 hp/
		);
		expect(items[1]).toHaveTextContent(/Velocity 11\.11 ft\/s in pipe 1, above 9\.843 ft\/s/);
		expect(items[1]).toHaveTextContent('Limits: your values · Details');
		const notEvaluated = view.getByRole('region', { name: /Not evaluated/ });
		expect(notEvaluated).toHaveTextContent('The pump curve has no NPSHr curve');
		expect(view.getByText(/as quoted by Datacor/)).toBeInTheDocument();
		// The element opens its trace.
		await fireEvent.click(within(items[0]!).getByRole('button', { name: 'Transfer pump' }));
		expect(ws.inspected).toEqual({ kind: 'component', id: 'P1' });
	});

	it("keeps the server's words under Details", async () => {
		const { answer } = await solveFixture();
		await fireEvent.click(results().getByRole('tab', { name: 'Checks' }));
		const view = within(results().getByRole('tabpanel', { name: 'Checks' }));
		for (const r of answer.solvedState.designChecks)
			expect(view.getAllByText(r.message, { exact: true }).length).toBeGreaterThan(0);
	});
});

describe('staleness', () => {
	it('a changed limit or manufacturer datum puts the results out of date', async () => {
		const { ws } = await solveFixture();
		expect(ws.store.results.stale).toBe(false);
		ws.edit((p) => {
			p.settings.designChecks!.pipeVelocity!.maximum = 4;
		}, 'change the pipe velocity check');
		expect(ws.store.results.stale).toBe(true);
		ws.undo();
		expect(ws.store.results.stale).toBe(false);
		ws.edit((p) => {
			p.pumpLibrary[0]!.motorRatedPower = 6000;
		}, 'change motor rated power');
		expect(ws.store.results.stale).toBe(true);
	});
});

describe("the Summary's design checks card", () => {
	it('counts them, names those not met, and leads to the view', async () => {
		await solveFixture();
		const card = within(results().getByRole('region', { name: 'Design checks' }));
		expect(card.getByText('3 not met · 4 met · 1 not evaluated')).toBeInTheDocument();
		const items = card.getAllByRole('listitem');
		expect(items).toHaveLength(3);
		expect(items[0]).toHaveTextContent(/^Transfer pump\s*Motor power: Shaft power/);
		await fireEvent.click(card.getByRole('button', { name: 'All checks' }));
		expect(results().getByRole('tab', { name: 'Checks' })).toHaveAttribute('aria-selected', 'true');
	});

	it('never marks the Results tab, with checks not met', async () => {
		const { answer } = await solveFixture();
		expect(answer.solvedState.designChecks.some((r) => r.outcome === 'fail')).toBe(true);
		expect(answer.solvedState.flags.some((f) => f.severity === 'invalid')).toBe(false);
		expect(screen.getByRole('tab', { name: /^Results/ })).toHaveAccessibleName('Results');
	});
});
