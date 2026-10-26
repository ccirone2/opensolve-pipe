/**
 * The Summary answers first, and results tables sort and filter (proposal ui-ux-refinement.md
 * items 8 and 9). The solve results are made-up test inputs (testing/results.ts); the API is
 * replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, node, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';

const results = () => within(screen.getByRole('region', { name: 'Results' }));

async function solveWith(solved: SolvedState) {
	const solve = vi.fn(() => Promise.resolve(response(solved)));
	const ws = testWorkspace(pumpTransferExample(), { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
	await results().findByRole('heading', { name: 'Converged' });
	return ws;
}

/** The row headers of the table in the view shown, in order. */
function rowNames(): string[] {
	const panel = results()
		.getAllByRole('tabpanel')
		.find((p) => !p.hidden)!;
	return within(panel)
		.getAllByRole('rowheader')
		.map((h) => h.querySelector('span')?.textContent?.trim() ?? '');
}

function columnHeading(name: RegExp): HTMLElement {
	const panel = results()
		.getAllByRole('tabpanel')
		.find((p) => !p.hidden)!;
	return within(panel).getByRole('columnheader', { name });
}

describe('the Summary answers first', () => {
	it('gives each pump’s operating point and NPSH margin, then the extremes with where they are', async () => {
		await solveWith(pumpTransferSolved());
		const pumps = results().getByRole('region', { name: 'Pumps' });
		expect(pumps).toHaveTextContent('Transfer pump 20 L/s at 22 m · NPSH margin 9 m');
		const extremes = within(results().getByRole('region', { name: 'Extremes' }));
		for (const label of [
			'Lowest static pressure',
			'Highest static pressure',
			'Highest velocity',
			'Smallest NPSH margin'
		]) {
			expect(extremes.getByText(label)).toBeInTheDocument();
		}
		// The fluid is one closed disclosure below the answers.
		const fluid = results().getByRole('heading', { name: 'Fluid: Water' }).closest('details')!;
		expect(fluid.open).toBe(false);
		expect(fluid).toHaveTextContent('20 °C');
	});

	it('links each extreme to its table, sorted on it, with the focus on that view', async () => {
		await solveWith(pumpTransferSolved());
		await fireEvent.click(results().getByRole('button', { name: 'Nodes, lowest first' }));
		await tick();
		const nodesTab = results().getByRole('tab', { name: 'Nodes' });
		expect(nodesTab).toHaveAttribute('aria-selected', 'true');
		expect(document.activeElement).toBe(nodesTab);
		expect(columnHeading(/^Pressure/)).toHaveAttribute('aria-sort', 'ascending');
		// The fixture's lowest static pressure is at the discharge tank (19.6 kPa).
		expect(rowNames()[0]).toBe('Discharge tank');

		await fireEvent.click(results().getByRole('tab', { name: 'Summary' }));
		await fireEvent.click(results().getByRole('button', { name: 'Nodes, highest first' }));
		await tick();
		expect(columnHeading(/^Pressure/)).toHaveAttribute('aria-sort', 'descending');
		expect(rowNames()[0]).toBe('Transfer pump');
	});

	it('names the fastest connection as the Links row it opens, after a reversal since the solve', async () => {
		const ws = await solveWith(pumpTransferSolved());
		const fastest = () =>
			within(results().getByRole('region', { name: 'Extremes' }))
				.getByText('Highest velocity')
				.closest('div')!;
		expect(fastest()).toHaveTextContent('Transfer pump → Discharge isolation valve');
		ws.store.update((p) => {
			const c = p.connections.find((x) => x.id === 'L2')!;
			[c.fromComponentId, c.toComponentId] = [c.toComponentId, c.fromComponentId];
			[c.fromPortId, c.toPortId] = [c.toPortId, c.fromPortId];
		}, 'Reverse');
		await tick();
		// Out of date, the results are named by the ends they were solved with, as Links names
		// them, so the name and the row it opens agree (and the flow's sign refers to those ends).
		expect(ws.store.results.stale).toBe(true);
		expect(fastest()).toHaveTextContent('Transfer pump → Discharge isolation valve');
		await fireEvent.click(results().getByRole('button', { name: 'Links, highest first' }));
		await tick();
		expect(rowNames()[0]).toBe('Transfer pump → Discharge isolation valve');
	});
});

describe('results tables sort and filter', () => {
	it('sorts by a column, ascending, descending, then back to the table’s order', async () => {
		await solveWith(pumpTransferSolved());
		await fireEvent.click(results().getByRole('tab', { name: 'Links' }));
		const original = rowNames();
		const heading = columnHeading(/^Head loss/);
		const button = within(heading).getByRole('button');
		await fireEvent.click(button);
		expect(heading).toHaveAttribute('aria-sort', 'ascending');
		// The fixture's head losses: L1 and L2 1 m (a tie, kept in the table's order), L3 8 m.
		const [l1, l2, l3] = original;
		expect(rowNames()).toEqual([l1, l2, l3]);
		await fireEvent.click(button);
		expect(heading).toHaveAttribute('aria-sort', 'descending');
		expect(rowNames()).toEqual([l3, l1, l2]);
		await fireEvent.click(button);
		expect(heading).not.toHaveAttribute('aria-sort');
		expect(rowNames()).toEqual(original);
	});

	it('offers Flagged only when some rows have flags and some do not', async () => {
		await solveWith(
			pumpTransferSolved({
				flags: [
					flag({
						code: 'TRANSITIONAL_FLOW',
						severity: 'warning',
						message: 'Transitional flow',
						connectionId: 'L2'
					})
				]
			})
		);
		await fireEvent.click(results().getByRole('tab', { name: 'Links' }));
		const toggle = results().getByRole('checkbox', { name: 'Flagged only (1 of 3)' });
		expect(rowNames()).toHaveLength(3);
		await fireEvent.click(toggle);
		expect(rowNames()).toEqual(['Transfer pump → Discharge isolation valve']);
		// No flags in the Pumps table: nothing to filter.
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		expect(results().queryByRole('checkbox', { name: /^Flagged only/ })).toBeNull();
	});

	it('leaves a column of no values unsortable, and rows without a value last', async () => {
		const solved = pumpTransferSolved();
		solved.nodeResults['R1:port_1'] = node('R1', 'port_1', { pressure: Number.NaN });
		await solveWith(solved);
		await fireEvent.click(results().getByRole('tab', { name: 'Nodes' }));
		const pressure = within(columnHeading(/^Pressure/)).getByRole('button');
		await fireEvent.click(pressure);
		await fireEvent.click(pressure);
		expect(rowNames().at(-1)).toBe('Suction tank');
	});
});
