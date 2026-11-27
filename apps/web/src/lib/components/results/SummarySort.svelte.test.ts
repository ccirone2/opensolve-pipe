/**
 * The Summary answers first, and results tables sort and filter (proposal ui-ux-refinement.md
 * items 8 and 9). The solve results are made-up test inputs (testing/results.ts); the API is
 * replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Flag, Project, PumpResult, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, link, node, pumpResult, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { insertComponentInConnection } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';
import { IMPERIAL_UNITS, SI_UNITS } from '$lib/utils/units';

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
	it('gives each pump’s operating point and NPSH margin ratio, then the extremes with where they are', async () => {
		await solveWith(pumpTransferSolved());
		const pumps = results().getByRole('region', { name: 'Pumps' });
		// The ratio, NPSHa ÷ NPSHr, in place of the margin (the owner's Q3, 2026-11-12: "Ratio
		// everywhere"; docs/proposals/pumps-nits.md item 4).
		expect(pumps).toHaveTextContent('Transfer pump 20 L/s at 22 m · NPSH margin ratio 4');
		expect(pumps).not.toHaveTextContent('NPSH margin 9 m');
		const extremes = within(results().getByRole('region', { name: 'Extremes' }));
		for (const label of [
			'Lowest static pressure',
			'Highest static pressure',
			'Highest velocity',
			'Smallest NPSH margin ratio'
		]) {
			expect(extremes.getByText(label)).toBeInTheDocument();
		}
		expect(extremes.queryByText('Smallest NPSH margin')).toBeNull();
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

// proposals/open-defects.md S1. The owner (2026-11-25): "Use absolute value of velocity": Links'
// Velocity column ranks by speed |v|, its cells still signed; a tie of the text shown breaks by the
// value the API returned; and each extreme is the first row of the table its link sorts.
describe('each extreme names the first row of the table its link sorts (proposals/open-defects.md S1)', () => {
	const { nodeResults } = pumpTransferSolved();
	const sig4 = (v: number) => String(Number(v.toPrecision(4)));
	/** Made-up values: a connection of one pipe at `velocity`, its flow signed alike. */
	const pipeAt = (velocity: number) =>
		link({ flow: velocity / 200, velocity, segments: [{ ...link().segments[0]!, velocity }] });

	/** The extreme `label`: its whole entry, and where it is (its link's words). */
	function extreme(label: string) {
		const entry = within(results().getByRole('region', { name: 'Extremes' }))
			.getByText(label)
			.closest('div')!;
		const [where] = within(entry).getAllByRole('button');
		return { entry, where: where!.textContent!.trim() };
	}

	/** The first row of the table shown, as the Summary names it: "Port of name" for a node. */
	function firstRow(kind: 'node' | 'connection'): string {
		const panel = results()
			.getAllByRole('tabpanel')
			.find((p) => !p.hidden)!;
		const header = within(panel).getAllByRole('rowheader')[0]!;
		const [name, detail] = [...header.querySelectorAll('span')].map((s) => s.textContent!.trim());
		return kind === 'node' ? `${detail} of ${name}` : name!;
	}

	/** Follow an extreme's "sorted" link; the first row of the table it opens. */
	async function follow(button: string, kind: 'node' | 'connection'): Promise<string> {
		await fireEvent.click(results().getByRole('button', { name: button }));
		await tick();
		return firstRow(kind);
	}

	for (const [units, prefs] of [
		['SI', SI_UNITS],
		['US', IMPERIAL_UNITS]
	] as const) {
		const project = () => {
			const p = pumpTransferExample();
			p.settings.units = { ...prefs };
			return p;
		};

		it(`Lowest static pressure, of two shown alike, names the port "Nodes, lowest first" puts first (${units} units)`, async () => {
			// Made-up results: 19601 Pa at the pump's suction, 19600 Pa at the discharge tank: 19.6
			// kPa(g) and 2.843 psig each.
			await solveWith(
				pumpTransferSolved({
					nodeResults: {
						...nodeResults,
						'P1:suction': node('P1', 'suction', {
							pressure: 19601,
							absolutePressure: 19601 + 101325,
							velocity: 2
						})
					}
				}),
				project()
			);
			const { where } = extreme('Lowest static pressure');
			expect(where).toBe('Port 1 of Discharge tank');
			expect(await follow('Nodes, lowest first', 'node')).toBe(where);
		});

		it(`Highest static pressure, of two shown alike, names the port "Nodes, highest first" puts first (${units} units)`, async () => {
			// Made-up results: 100000 Pa at the pump's discharge, 100004 Pa at the valve's inlet: 100
			// kPa(g) and 14.5 psig each.
			await solveWith(
				pumpTransferSolved({
					nodeResults: {
						...nodeResults,
						'V1:inlet': node('V1', 'inlet', {
							pressure: 100004,
							absolutePressure: 100004 + 101325,
							velocity: 4
						})
					}
				}),
				project()
			);
			const { where } = extreme('Highest static pressure');
			expect(where).toBe('Inlet of Discharge isolation valve');
			expect(await follow('Nodes, highest first', 'node')).toBe(where);
		});

		it(`Highest velocity, of two shown alike, names the connection "Links, highest first" puts first (${units} units)`, async () => {
			// Made-up results: 4 m/s in L2, 4.0004 m/s in L3: 4 m/s and 13.12 ft/s each.
			await solveWith(
				pumpTransferSolved({ linkResults: { L1: pipeAt(2), L2: pipeAt(4), L3: pipeAt(4.0004) } }),
				project()
			);
			const { where } = extreme('Highest velocity');
			expect(where).toBe('Discharge isolation valve → Discharge tank');
			expect(await follow('Links, highest first', 'connection')).toBe(where);
		});

		it(`Highest velocity names a connection whose flow runs against its drawn direction, at its speed, and "Links, highest first" puts it first, its cell signed (${units} units)`, async () => {
			// Made-up results: L1's flow from the pump to the suction tank at 4.893 m/s, the fastest;
			// L2 4.378 m/s, L3 2 m/s.
			await solveWith(
				pumpTransferSolved({
					linkResults: { L1: pipeAt(-4.893), L2: pipeAt(4.378), L3: pipeAt(2) }
				}),
				project()
			);
			const { entry, where } = extreme('Highest velocity');
			expect(where).toBe('Suction tank → Transfer pump');
			// 1 ft = 0.3048 m.
			const speed = prefs === SI_UNITS ? '4.893 m/s' : `${sig4(4.893 / 0.3048)} ft/s`;
			expect(entry).toHaveTextContent(speed);
			expect(await follow('Links, highest first', 'connection')).toBe(where);
			expect(columnHeading(/^Velocity/)).toHaveAttribute('aria-sort', 'descending');
			const row = within(
				results()
					.getAllByRole('tabpanel')
					.find((p) => !p.hidden)!
			).getAllByRole('row')[1]!;
			const signed = prefs === SI_UNITS ? '-4.893' : sig4(-4.893 / 0.3048);
			expect(
				within(row)
					.getAllByRole('cell')
					.map((c) => c.textContent?.trim())
			).toContain(signed);
		});
	}

	it('sorting Links by Velocity, highest first, puts the connection whose flow runs against its drawn direction first', async () => {
		// The same made-up results.
		await solveWith(
			pumpTransferSolved({ linkResults: { L1: pipeAt(-4.893), L2: pipeAt(4.378), L3: pipeAt(2) } })
		);
		await fireEvent.click(results().getByRole('tab', { name: 'Links' }));
		const original = rowNames();
		const reversed = 'Suction tank → Transfer pump';
		expect(original[0]).toBe(reversed);
		const heading = columnHeading(/^Velocity/);
		const button = within(heading).getByRole('button');
		await fireEvent.click(button);
		expect(heading).toHaveAttribute('aria-sort', 'ascending');
		expect(rowNames()).toEqual([original[2], original[1], reversed]);
		await fireEvent.click(button);
		expect(heading).toHaveAttribute('aria-sort', 'descending');
		expect(rowNames()).toEqual([reversed, original[1], original[2]]);
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

describe('the Summary’s NPSH reading is the margin ratio (docs/proposals/pumps-nits.md item 4, the owner’s Q3)', () => {
	const KEY = 'opensolve-pipe:results-fields:Results per pump';
	const sig4 = (v: number) => String(Number(v.toPrecision(4)));

	/** The extreme "Smallest NPSH margin ratio": its whole entry, and the pump it names. */
	function smallestRatio() {
		const entry = within(results().getByRole('region', { name: 'Extremes' }))
			.getByText('Smallest NPSH margin ratio')
			.closest('div')!;
		const named = within(entry)
			.getAllByRole('button')
			.filter((b) => b.textContent?.trim() !== 'Pumps, smallest first');
		expect(named).toHaveLength(1);
		return { entry, pump: named[0]!.textContent!.trim() };
	}

	/** The transfer pump and a booster after it, solved with these made-up results. */
	async function twoPumps(
		transfer: PumpResult,
		boosterResult: PumpResult,
		flags: (boosterId: string) => Flag[] = () => []
	) {
		const base = pumpTransferExample();
		const booster = createComponent('pump', base, { name: 'Booster pump' });
		const project = insertComponentInConnection(base, 'L3', booster);
		localStorage.removeItem(KEY);
		await solveWith(
			pumpTransferSolved({
				pumpResults: { P1: transfer, [booster.id]: boosterResult },
				flags: flags(booster.id)
			}),
			project
		);
	}

	/** Each pump's line under Pumps, by its name. */
	function pumpLine(name: string): HTMLElement {
		const pumps = within(results().getByRole('region', { name: 'Pumps' }));
		return pumps.getByRole('button', { name }).closest('li') as HTMLElement;
	}

	it('names the pump of the smallest ratio and links to Results per pump sorted by the ratio, its first row that pump, where the smallest margin is another pump’s', async () => {
		// Made-up results: the transfer pump NPSHa 4 m, NPSHr 2 m (margin 2 m, ratio 2); the
		// booster NPSHa 20 m, NPSHr 15 m (margin 5 m, ratio 20 ÷ 15). The smallest margin is the
		// transfer pump's, the smallest ratio the booster's: value and link move together.
		try {
			await twoPumps(
				pumpResult({ npshAvailable: 4, npshRequired: 2, npshMargin: 2, npshMarginRatio: 2 }),
				pumpResult({
					npshAvailable: 20,
					npshRequired: 15,
					npshMargin: 5,
					npshMarginRatio: 20 / 15
				})
			);
			expect(pumpLine('Transfer pump')).toHaveTextContent(
				'Transfer pump 20 L/s at 22 m · NPSH margin ratio 2'
			);
			expect(pumpLine('Booster pump')).toHaveTextContent(
				`Booster pump 20 L/s at 22 m · NPSH margin ratio ${sig4(20 / 15)}`
			);
			const { entry, pump } = smallestRatio();
			expect(pump).toBe('Booster pump');
			expect(entry).toHaveTextContent(sig4(20 / 15));
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			expect(results().getByRole('tab', { name: 'Pumps' })).toHaveAttribute(
				'aria-selected',
				'true'
			);
			expect(columnHeading(/^NPSH margin ratio/)).toHaveAttribute('aria-sort', 'ascending');
			expect(rowNames()).toEqual(['Booster pump', 'Transfer pump']);
			expect(rowNames()[0]).toBe(pump);
		} finally {
			localStorage.removeItem(KEY);
		}
	});

	it('names the cavitation and the margin of a pump with no ratio whose margin is negative; the extreme and its link still name one pump', async () => {
		// Made-up results: the booster's NPSHr is 0 at its flow and its NPSHa −2.521 m, so its
		// margin is −2.521 m, it has no ratio and CAVITATION is raised (corpus unit_rich1090 PU2):
		// a null ratio is no sign of a safe margin (API review A1/B1).
		try {
			await twoPumps(
				pumpResult(),
				pumpResult({
					npshAvailable: -2.521,
					npshRequired: 0,
					npshMargin: -2.521,
					npshMarginRatio: null
				}),
				(booster) => [
					flag({
						code: 'CAVITATION',
						severity: 'invalid',
						message: 'made-up',
						componentId: booster
					})
				]
			);
			expect(pumpLine('Transfer pump')).toHaveTextContent('· NPSH margin ratio 4');
			const line = pumpLine('Booster pump');
			expect(line).toHaveTextContent(/cavitat/i);
			expect(line.textContent).toMatch(/[-−]2\.521\s?m\b/);
			// The extreme is the booster, whose NPSHa ÷ NPSHr tends to −∞, below the transfer pump's
			// ratio of 4: it names the cavitation and the margin in place of a number (review E-0-1,
			// E-1-1). On main 407dbc4 "Smallest NPSH margin" named it too.
			const { entry, pump } = smallestRatio();
			expect(pump).toBe('Booster pump');
			expect(entry).toHaveTextContent(/cavitat/i);
			expect(entry.textContent).toMatch(/[-−]2\.521\s?m\b/);
			expect(entry).not.toHaveTextContent(/\b4\b/);
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			expect(columnHeading(/^NPSH margin ratio/)).toHaveAttribute('aria-sort', 'ascending');
			expect(rowNames()).toEqual(['Booster pump', 'Transfer pump']);
			expect(rowNames()[0]).toBe(pump);
		} finally {
			localStorage.removeItem(KEY);
		}
	});

	it('keeps the NPSH extreme for a lone pump that cavitates with no ratio, naming it with the cavitation and its margin', async () => {
		// Made-up results: the transfer pump alone, NPSHr 0 at its flow and NPSHa −2.521 m (review
		// E-0-1, E-1-1: on main 407dbc4 the Summary read "Smallest NPSH margin -2.521 m").
		try {
			localStorage.removeItem(KEY);
			await solveWith(
				pumpTransferSolved({
					pumpResults: {
						P1: pumpResult({
							npshAvailable: -2.521,
							npshRequired: 0,
							npshMargin: -2.521,
							npshMarginRatio: null
						})
					},
					flags: [
						flag({
							code: 'CAVITATION',
							severity: 'invalid',
							message: 'made-up',
							componentId: 'P1'
						})
					]
				})
			);
			const { entry, pump } = smallestRatio();
			expect(pump).toBe('Transfer pump');
			expect(within(entry).getByRole('term')).toHaveTextContent(/^Smallest NPSH margin ratio$/);
			expect(within(entry).getByRole('definition')).toHaveTextContent(
				/^Cavitates \(NPSHr 0\): NPSH margin -2\.521 m\s*Transfer pump$/
			);
			// One pump: no sorted link, as for every lone pump.
			expect(within(entry).queryByRole('button', { name: 'Pumps, smallest first' })).toBeNull();
		} finally {
			localStorage.removeItem(KEY);
		}
	});

	// pumps-nits.md §11, leftovers L1 and L2.
	/** NPSHr 0 at its flow: its margin is its NPSHa, and the API gives no ratio. */
	const npshrZero = (margin: number) =>
		pumpResult({
			npshAvailable: margin,
			npshRequired: 0,
			npshMargin: margin,
			npshMarginRatio: null
		});

	it('gives the NPSH margin of a pump with NPSHr 0 that does not cavitate in its line and, where it is the lone pump, as the extreme (leftover L1)', async () => {
		// Made-up results: NPSHr 0 at its flow and NPSHa 5 m: a margin of 5 m, no ratio, no flag.
		try {
			localStorage.removeItem(KEY);
			await solveWith(pumpTransferSolved({ pumpResults: { P1: npshrZero(5) } }));
			const pumps = results().getByRole('region', { name: 'Pumps' });
			expect(pumps.querySelector('li')!.textContent!.replace(/\s+/g, ' ').trim()).toBe(
				'Transfer pump 20 L/s at 22 m · NPSHr 0: NPSH margin 5 m'
			);
			const { entry, pump } = smallestRatio();
			expect(pump).toBe('Transfer pump');
			expect(within(entry).getByRole('definition')).toHaveTextContent(
				/^NPSHr 0: NPSH margin 5 m\s*Transfer pump$/
			);
		} finally {
			localStorage.removeItem(KEY);
		}
	});

	it('names, of two pumps that cavitate with no ratio, the one with the more negative margin, and its link’s first row is that pump (critique CR-OWNER-3)', async () => {
		// Made-up results: the transfer pump −0.5 m, the booster after it −8 m; both NPSHr 0.
		try {
			await twoPumps(npshrZero(-0.5), npshrZero(-8), (booster) => [
				flag({ code: 'CAVITATION', severity: 'invalid', message: 'made-up', componentId: 'P1' }),
				flag({ code: 'CAVITATION', severity: 'invalid', message: 'made-up', componentId: booster })
			]);
			const { entry, pump } = smallestRatio();
			expect(pump).toBe('Booster pump');
			expect(within(entry).getByRole('definition')).toHaveTextContent(
				/^Cavitates \(NPSHr 0\): NPSH margin -8 m\s*Booster pump\s*Pumps, smallest first$/
			);
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			expect(columnHeading(/^NPSH margin ratio/)).toHaveAttribute('aria-sort', 'ascending');
			expect(rowNames()).toEqual(['Booster pump', 'Transfer pump']);
			expect(rowNames()[0]).toBe(pump);
		} finally {
			localStorage.removeItem(KEY);
		}
	});

	it('names, where two ratios show alike (1.282), the pump its link’s sorted table puts first: the values shown, then the table’s order (leftover L2)', async () => {
		// Made-up results: 1.28204 and 1.28196, both 1.282 to 4 significant figures; the API's
		// smaller is the booster's, after the transfer pump in the table.
		expect([sig4(1.28204), sig4(1.28196)]).toEqual(['1.282', '1.282']);
		try {
			await twoPumps(
				pumpResult({ npshMarginRatio: 1.28204 }),
				pumpResult({ npshMarginRatio: 1.28196 })
			);
			const { entry, pump } = smallestRatio();
			expect(entry).toHaveTextContent('1.282');
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			expect(columnHeading(/^NPSH margin ratio/)).toHaveAttribute('aria-sort', 'ascending');
			expect(rowNames()).toEqual(['Transfer pump', 'Booster pump']);
			expect(pump).toBe(rowNames()[0]);
		} finally {
			localStorage.removeItem(KEY);
		}
	});
});

describe('a Summary link shows the column it sorts by (docs/proposals/pumps-nits.md item 3)', () => {
	const KEY = 'opensolve-pipe:results-fields:Results per pump';

	it('“Pumps, smallest first” sorts Results per pump by NPSH margin ratio and shows it, though a stored choice hid it; the choice then stored as the box checked', async () => {
		// Made-up results: a booster after the transfer pump, its NPSH margin ratio the smaller
		// (NPSHa 8 m ÷ NPSHr 3 m against 12 m ÷ 3 m).
		const base = pumpTransferExample();
		const booster = createComponent('pump', base, { name: 'Booster pump' });
		const project = insertComponentInConnection(base, 'L3', booster);
		localStorage.setItem(KEY, '["npshMarginRatio"]');
		try {
			await solveWith(
				pumpTransferSolved({
					pumpResults: {
						P1: pumpResult(),
						[booster.id]: pumpResult({ npshAvailable: 8, npshMargin: 5, npshMarginRatio: 8 / 3 })
					}
				}),
				project
			);
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			const pumpsTab = results().getByRole('tab', { name: 'Pumps' });
			expect(pumpsTab).toHaveAttribute('aria-selected', 'true');
			const table = within(results().getByRole('table', { name: 'Results per pump' }));
			expect(table.getByRole('columnheader', { name: /^NPSH margin ratio/ })).toHaveAttribute(
				'aria-sort',
				'ascending'
			);
			// The absolute margin stays hidden by default: the link shows only the column it sorts by.
			expect(table.queryByRole('columnheader', { name: /^NPSH margin m/ })).toBeNull();
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
		const ws = testWorkspace(project, { solver: { solve } });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		return { solve, ws };
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
	/**
	 * Solve again from the Summary, then press `view`'s tab (not a link). Solve waits while the
	 * results are current (the owner, 2026-11-27): an edit puts them out of date first.
	 */
	async function solveAgainThenOpen(
		{ solve, ws }: Awaited<ReturnType<typeof solveEachTime>>,
		view: string
	) {
		await fireEvent.click(results().getByRole('tab', { name: 'Summary' }));
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change length');
		await tick();
		expect(ws.store.results.stale).toBe(true);
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
			const solved = await solveEachTime(pumpTransferExample(), () => pumpTransferSolved());
			await fireEvent.click(results().getByRole('button', { name: 'Nodes, lowest first' }));
			await tick();
			expect(columnHeading(/^Pressure/)).toHaveAttribute('aria-sort', 'ascending');
			await hideField('Results per component port', /^Pressure/);
			expect(localStorage.getItem(NODES)).toBe('["pressure"]');
			await solveAgainThenOpen(solved, 'Nodes');
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

	it('keeps NPSH margin ratio hidden after “Pumps, smallest first”, through a new solve and the Pumps tab pressed again', async () => {
		const base = pumpTransferExample();
		const booster = createComponent('pump', base, { name: 'Booster pump' });
		const project = insertComponentInConnection(base, 'L3', booster);
		localStorage.removeItem(KEY);
		try {
			const solved = await solveEachTime(project, () =>
				pumpTransferSolved({
					pumpResults: {
						P1: pumpResult(),
						[booster.id]: pumpResult({ npshAvailable: 8, npshMargin: 5, npshMarginRatio: 8 / 3 })
					}
				})
			);
			await fireEvent.click(results().getByRole('button', { name: 'Pumps, smallest first' }));
			await tick();
			const table = () => within(results().getByRole('table', { name: 'Results per pump' }));
			expect(table().getByRole('columnheader', { name: /^NPSH margin ratio/ })).toHaveAttribute(
				'aria-sort',
				'ascending'
			);
			await hideField('Results per pump', /^NPSH margin ratio/);
			expect(localStorage.getItem(KEY)).toBe('["npshMarginRatio"]');
			await solveAgainThenOpen(solved, 'Pumps');
			expect(results().getByRole('tab', { name: 'Pumps' })).toHaveAttribute(
				'aria-selected',
				'true'
			);
			expect(table().queryByRole('columnheader', { name: /^NPSH margin ratio/ })).toBeNull();
			expect(localStorage.getItem(KEY)).toBe('["npshMarginRatio"]');
		} finally {
			localStorage.removeItem(KEY);
		}
	});
});
