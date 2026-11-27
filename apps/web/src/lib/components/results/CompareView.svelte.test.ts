/**
 * Compare cases (proposal scenario-manager.md §6.12): the mark on a physically invalid value.
 * The solve results are made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Project } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, link, pumpResult, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { withScenarios } from '$lib/utils/scenarios';

const results = () => within(screen.getByRole('region', { name: 'Results' }));

/** FlagIcon's shapes (Icon.svelte): the invalid octagon, and the warning's triangle. */
const OCTAGON = 'M8 3h8l5 5v8l-5 5H8l-5-5V8z';
const TRIANGLE = 'M12 3 2 20h20z';
/** The icon shapes drawn inside an element, by their outline's path. */
const shapes = (el: Element) =>
	[...el.querySelectorAll('svg')].map((svg) => svg.querySelector('path')!.getAttribute('d'));

describe('Compare cases', () => {
	// docs/proposals/open-defects.md S2: Compare marked a physically invalid value with the red
	// triangle where the Pumps tab marks it with the octagon (ui-guide "No value is not a safe
	// value"; pumps-results-layout.md §5.2: the triangle never stands for an invalid value).
	it('marks each physically invalid value with the octagon, beside its first line, in the table and the cards', async () => {
		const project: Project = withScenarios(pumpTransferExample(), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		// Made-up: the pump cavitates in both cases (an invalid flag on P1), and in Winter a
		// connection has an invalid flag of its own (L2, no component; the API raises none there,
		// and Compare marks by the severity, so any code the schema has will do). The rows take a
		// number (P1's flow) and words (its state, which can wrap in a narrow column).
		const cavitation = flag({
			code: 'CAVITATION',
			severity: 'invalid',
			message: 'Made-up: the pump cavitates.',
			componentId: 'P1'
		});
		const base = pumpTransferSolved({ flags: [cavitation] });
		const winter = pumpTransferSolved({
			pumpResults: { P1: pumpResult({ operatingFlow: 0.018 }) },
			linkResults: {
				...base.linkResults,
				L2: link({ flow: 0.018, velocity: 3.6 })
			},
			flags: [
				cavitation,
				flag({
					code: 'BELOW_VAPOR_PRESSURE',
					severity: 'invalid',
					message: 'Made-up: an invalid flag on a connection.',
					connectionId: 'L2'
				})
			]
		});
		const solve = vi
			.fn()
			.mockResolvedValueOnce(response(base))
			.mockResolvedValueOnce(response(winter));
		const ws = testWorkspace(project, { solver: { solve } });
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		ws.setCase('S1');
		await ws.solve();
		ws.setCase(null);
		ws.compareRows = [
			{ quantity: 'status' },
			{ quantity: 'pumpFlow', elementId: 'P1' },
			{ quantity: 'pumpStatus', elementId: 'P1' },
			{ quantity: 'linkVelocity', elementId: 'L2' },
			{ quantity: 'linkVelocity', elementId: 'L3' }
		];
		ws.comparing = true;
		const compare = await results().findByRole('region', { name: 'Compare cases' });

		// The table's value cells, then the phone's cards' values (one dd per case).
		const tableCells = [...compare.querySelectorAll('table td')];
		const cardValues = [...compare.querySelectorAll('dl dd')];
		for (const [where, cells, marks] of [
			// Per row, base then Winter: status none; P1's flow and status both; L2 Winter's only;
			// L3 none.
			['table', tableCells, [false, false, true, true, true, true, false, true, false, false]],
			['cards', cardValues, [false, false, true, true, true, true, false, true, false, false]]
		] as const) {
			expect(cells, where).toHaveLength(marks.length);
			cells.forEach((cell, i) => {
				const what = `${where} cell ${i}: ${cell.textContent?.replace(/\s+/g, ' ').trim()}`;
				const marked = marks[i]!;
				expect(cell.textContent!.includes('physically invalid:'), what).toBe(marked);
				expect(shapes(cell), what).toEqual(marked ? [OCTAGON] : []);
				expect(shapes(cell), what).not.toContain(TRIANGLE);
				if (!marked) return;
				// FlagIcon's invalid octagon, red, at the Pumps tab's table size, its words for a
				// screen reader kept.
				const icon = cell.querySelector('svg')!;
				expect(icon, what).toHaveClass('size-3.5', 'shrink-0', 'text-red-700');
				expect(within(cell as HTMLElement).getByText('physically invalid:'), what).toHaveClass(
					'sr-only'
				);
				// Beside the value's first line however it wraps (a status's words in a narrow
				// column): in a box one line tall at the top, out of the baseline alignment the words
				// keep (ui-guide "No value is not a safe value"; Running combinations' octagon).
				expect(icon.parentElement, what).toHaveClass(
					'flex',
					'h-lh',
					'shrink-0',
					'items-center',
					'self-start'
				);
				expect(icon.parentElement!.parentElement, what).toHaveClass(
					'inline-flex',
					'items-baseline'
				);
			});
		}
	});
});
