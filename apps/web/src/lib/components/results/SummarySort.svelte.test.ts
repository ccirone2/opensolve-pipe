/**
 * The Summary answers first, and results tables sort and filter (proposal ui-ux-refinement.md
 * items 8 and 9). The solve results are made-up test inputs (testing/results.ts); the API is
 * replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Project, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, node, pumpResult, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { insertComponentInConnection } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';

const results = () => within(screen.getByRole('region', { name: 'Results' }));

async function solveWith(solved: SolvedState, project: Project = pumpTransferExample()) {
	const solve = vi.fn(() => Promise.resolve(response(solved)));
	const ws = testWorkspace(project, { solver: { solve } });
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

	it('sorts from "Sort by" and its direction, as a phone does (the same sort as a heading)', async () => {
		await solveWith(pumpTransferSolved());
		await fireEvent.click(results().getByRole('tab', { name: 'Links' }));
		const panel = within(
			results()
				.getAllByRole('tabpanel')
				.find((p) => !p.hidden)!
		);
		const original = rowNames();
		const [l1, l2, l3] = original;
		const heading = columnHeading(/^Head loss/);
		const field = panel.getByRole('combobox', { name: 'Sort by, Results per pipe connection' });
		await fireEvent.change(field, { target: { value: 'headLoss' } });
		expect(heading).toHaveAttribute('aria-sort', 'ascending');
		expect(rowNames()).toEqual([l1, l2, l3]);
		await fireEvent.click(panel.getByRole('button', { name: 'Ascending: lowest first' }));
		expect(heading).toHaveAttribute('aria-sort', 'descending');
		expect(rowNames()).toEqual([l3, l1, l2]);
		// A heading's sort shows in the field: one sort, two ways to set it.
		await fireEvent.click(within(columnHeading(/^Flow/)).getByRole('button'));
		expect(field).toHaveValue('flow');
		await fireEvent.change(field, { target: { value: '' } });
		expect(rowNames()).toEqual(original);
		expect(panel.queryByRole('button', { name: /lowest first|highest first/ })).toBeNull();
	});

	it('chooses the fields shown from its Fields menu, remembered in this browser', async () => {
		localStorage.clear();
		await solveWith(pumpTransferSolved());
		await fireEvent.click(results().getByRole('tab', { name: 'Links' }));
		const panel = () =>
			within(
				results()
					.getAllByRole('tabpanel')
					.find((p) => !p.hidden)!
			);
		const fields = panel().getByRole('button', { name: /^Fields/ });
		expect(fields).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(fields);
		const menu = panel().getByRole('group', { name: /^Fields shown in/ });
		const velocity = within(menu).getByRole('checkbox', { name: /^Velocity/ });
		expect(velocity).toBeChecked();
		await fireEvent.click(velocity);
		expect(panel().queryByRole('columnheader', { name: /^Velocity/ })).toBeNull();
		expect(panel().getByRole('columnheader', { name: /^Flow/ })).toBeInTheDocument();
		expect(fields).toHaveTextContent(/of/);
		// Remembered: a per-browser convenience, never in the project or its link.
		expect(
			Object.keys(localStorage).some((k) => k.startsWith('opensolve-pipe:results-fields:'))
		).toBe(true);
		await fireEvent.click(within(menu).getByRole('button', { name: 'Show all' }));
		expect(panel().getByRole('columnheader', { name: /^Velocity/ })).toBeInTheDocument();
		expect(
			Object.keys(localStorage).some((k) => k.startsWith('opensolve-pipe:results-fields:'))
		).toBe(false);
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

describe('a Summary link shows the column it sorts by (docs/proposals/pumps-nits.md item 3)', () => {
	const KEY = 'opensolve-pipe:results-fields:Results per pump';

	it('“Pumps, smallest first” sorts Results per pump by NPSH margin and shows it, though a stored choice hid it; the choice then stored as the box checked', async () => {
		// Made-up results: a booster after the transfer pump, its NPSH margin the smaller.
		const base = pumpTransferExample();
		const booster = createComponent('pump', base, { name: 'Booster pump' });
		const project = insertComponentInConnection(base, 'L3', booster);
		localStorage.setItem(KEY, '["npshMargin"]');
		try {
			await solveWith(
				pumpTransferSolved({
					pumpResults: {
						P1: pumpResult(),
						[booster.id]: pumpResult({ npshAvailable: 8, npshMargin: 5 })
					}
				}),
				project
			);
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			const pumpsTab = results().getByRole('tab', { name: 'Pumps' });
			expect(pumpsTab).toHaveAttribute('aria-selected', 'true');
			const table = within(results().getByRole('table', { name: 'Results per pump' }));
			expect(table.getByRole('columnheader', { name: /^NPSH margin/ })).toHaveAttribute(
				'aria-sort',
				'ascending'
			);
			expect(
				table.getAllByRole('rowheader').map((h) => h.querySelector('span')?.textContent?.trim())
			).toEqual(['Booster pump', 'Transfer pump']);
			// Stored as if its box were checked: no departure from the defaults is left.
			expect(localStorage.getItem(KEY)).toBeNull();
		} finally {
			localStorage.removeItem(KEY);
		}
	});

	/**
	 * A link's request is for the solve it was pressed on (review PUMPS-NITS-A1): a view not shown
	 * when a new solve arrives is drawn anew when its tab is next pressed, and must not take the old
	 * request as new, which would show again a column the user hid after the link, and store that.
	 */
	async function solveEachTime(project: Project, solved: () => SolvedState) {
		// A new solved state from each solve, as the API gives.
		const solve = vi.fn(() => Promise.resolve(response(solved())));
		render(WorkspaceView, { workspace: testWorkspace(project, { solver: { solve } }) });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		return solve;
	}
	/** Uncheck a field in a table's Fields menu, then close the menu. */
	async function hideField(table: string, field: RegExp) {
		await fireEvent.click(
			results().getByRole('button', { name: new RegExp(`^Fields.*, ${table}$`) })
		);
		const menu = results().getByRole('group', { name: `Fields shown in ${table}` });
		await fireEvent.click(within(menu).getByRole('checkbox', { name: field }));
		await fireEvent.keyDown(menu, { key: 'Escape' });
	}
	/** Solve again from the Summary, then press `view`'s tab (not a link). */
	async function solveAgainThenOpen(solve: ReturnType<typeof vi.fn>, view: string) {
		await fireEvent.click(results().getByRole('tab', { name: 'Summary' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await vi.waitFor(() => expect(solve).toHaveBeenCalledTimes(2));
		await results().findByRole('heading', { name: 'Converged' });
		await fireEvent.click(results().getByRole('tab', { name: view }));
		await tick();
	}

	it('keeps a field hidden after the link, through a new solve and its tab pressed again (Nodes)', async () => {
		const NODES = 'opensolve-pipe:results-fields:Results per component port';
		localStorage.removeItem(NODES);
		try {
			const solve = await solveEachTime(pumpTransferExample(), () => pumpTransferSolved());
			await fireEvent.click(results().getByRole('button', { name: 'Nodes, lowest first' }));
			await tick();
			expect(columnHeading(/^Pressure/)).toHaveAttribute('aria-sort', 'ascending');
			await hideField('Results per component port', /^Pressure/);
			expect(localStorage.getItem(NODES)).toBe('["pressure"]');
			await solveAgainThenOpen(solve, 'Nodes');
			expect(results().getByRole('tab', { name: 'Nodes' })).toHaveAttribute(
				'aria-selected',
				'true'
			);
			const table = within(results().getByRole('table', { name: 'Results per component port' }));
			expect(table.queryByRole('columnheader', { name: /^Pressure/ })).toBeNull();
			expect(localStorage.getItem(NODES)).toBe('["pressure"]');
		} finally {
			localStorage.removeItem(NODES);
		}
	});

	it('keeps NPSH margin hidden after “Pumps, smallest first”, through a new solve and the Pumps tab pressed again', async () => {
		const base = pumpTransferExample();
		const booster = createComponent('pump', base, { name: 'Booster pump' });
		const project = insertComponentInConnection(base, 'L3', booster);
		localStorage.removeItem(KEY);
		try {
			const solve = await solveEachTime(project, () =>
				pumpTransferSolved({
					pumpResults: {
						P1: pumpResult(),
						[booster.id]: pumpResult({ npshAvailable: 8, npshMargin: 5 })
					}
				})
			);
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			const table = () => within(results().getByRole('table', { name: 'Results per pump' }));
			expect(table().getByRole('columnheader', { name: /^NPSH margin/ })).toHaveAttribute(
				'aria-sort',
				'ascending'
			);
			await hideField('Results per pump', /^NPSH margin/);
			expect(localStorage.getItem(KEY)).toBe('["npshMargin"]');
			await solveAgainThenOpen(solve, 'Pumps');
			expect(results().getByRole('tab', { name: 'Pumps' })).toHaveAttribute(
				'aria-selected',
				'true'
			);
			expect(table().queryByRole('columnheader', { name: /^NPSH margin/ })).toBeNull();
			expect(localStorage.getItem(KEY)).toBe('["npshMargin"]');
		} finally {
			localStorage.removeItem(KEY);
		}
	});
});
