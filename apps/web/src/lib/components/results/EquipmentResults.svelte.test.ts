/**
 * Equipment in the results (proposal equipment-pressure-drop.md §5.3, §6.3): a view of its own,
 * shown only when the solve has equipment, with its table and note; the key values beside the item
 * in Build (no flow ratio for a Cv or Kv); the trace's Add to comparison and Use in goal seek; and
 * the goal-seek pickers' Equipment groups. The solve results are made-up test inputs
 * (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { EquipmentRating, Project, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { equipmentProject } from '$lib/testing/helpers';
import { equipmentSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { withScenarios } from '$lib/utils/scenarios';

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const build = () => within(screen.getByRole('region', { name: 'Build' }));

async function solveWith(solved: SolvedState, project: Project = equipmentProject()) {
	const solve = vi.fn(() => Promise.resolve(response(solved)));
	const ws = testWorkspace(project, { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	await ws.solve();
	await results().findByRole('heading', { name: /^(Converged|Did not converge)$/ });
	return ws;
}

function cells(row: HTMLElement): string[] {
	return within(row)
		.getAllByRole('cell')
		.map((c) => c.textContent?.replace(/\s+/g, ' ').trim() ?? '');
}

/** "Label (unit): value" of each value of the Build strip. */
function strip(): string[] {
	const group = build().getAllByRole('group', { name: /^Last solve/ })[0]!;
	return [...group.querySelectorAll('dl > div')].map((d) =>
		`${d.querySelector('dt')?.textContent?.trim()}: ${d.querySelector('dd')?.textContent?.trim()}`.replace(
			/\u00a0/g,
			' '
		)
	);
}

describe('equipment results', () => {
	it('have a view of their own, after Valves, with its table and note', async () => {
		await solveWith(equipmentSolved());
		const tabs = results().getByRole('tablist', { name: 'Results view' });
		expect(
			within(tabs)
				.getAllByRole('tab')
				.map((t) => t.textContent?.trim())
		).toEqual(['Summary', 'Nodes', 'Links', 'Equipment', 'Boundaries', 'Methods']);
		await fireEvent.click(results().getByRole('tab', { name: 'Equipment' }));
		const table = results().getByRole('table', { name: 'Results per equipment item' });
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => h.textContent?.replace(/\s+/g, ' ').trim())
		).toEqual([
			'Equipment',
			'Flow (+ inlet → outlet) L/s',
			'Flow ÷ rated flow %',
			'Pressure loss kPa',
			'Head loss m',
			'Pressure drop (static) kPa'
		]);
		const row = within(table)
			.getByRole('rowheader', { name: /^Strainer/ })
			.closest('tr')!;
		expect(cells(row)).toEqual(['12', '120', '36', '3.675', '36.5']);
		expect(
			results().getByText(/^Pressure loss is the rating scaled to the solved flow and density/)
		).toHaveTextContent(/An element rated by a Cv or Kv has no rated flow\.$/);
	});

	it('are not a view without equipment', async () => {
		await solveWith(equipmentSolved({}, { equipmentResults: {} }));
		expect(results().queryByRole('tab', { name: 'Equipment' })).toBeNull();
	});

	it('beside the item in Build: flow, flow ÷ rated flow and pressure loss (no ratio for a Cv)', async () => {
		const ws = await solveWith(equipmentSolved());
		ws.nav.jumpTo('E1');
		ws.pane = 'build';
		await tick();
		expect(strip()).toEqual([
			'Flow (+ inlet → outlet) (L/s): 12',
			'Flow ÷ rated flow (%): 120',
			'Pressure loss (kPa): 36'
		]);
	});

	it('beside a Cv-rated item in Build: flow and pressure loss (a Cv has no rated flow)', async () => {
		const cv: EquipmentRating = { kind: 'Cv', value: 80 };
		const ws = await solveWith(
			equipmentSolved({ flowRatio: null, rating: cv }),
			equipmentProject(cv)
		);
		ws.nav.jumpTo('E1');
		ws.pane = 'build';
		await tick();
		expect(strip()).toEqual(['Flow (+ inlet → outlet) (L/s): 12', 'Pressure loss (kPa): 36']);
	});

	it("the trace adds the item's flow and pressure loss to Compare cases", async () => {
		const project = withScenarios(equipmentProject(), [
			{ id: 'S1', name: 'Dirty strainer', overrides: [] }
		]);
		const ws = await solveWith(equipmentSolved(), project);
		ws.inspect({ kind: 'component', id: 'E1' });
		await tick();
		const trace = within(await screen.findByRole('dialog', { name: 'Strainer' }));
		expect(trace.getByText(/^Equipment \(rated pressure drop\) · E1/)).toBeInTheDocument();
		await fireEvent.click(trace.getByRole('button', { name: 'Add to comparison' }));
		expect(ws.compareRows).toContainEqual({ quantity: 'equipmentFlow', elementId: 'E1' });
		expect(ws.compareRows).toContainEqual({ quantity: 'equipmentPressureLoss', elementId: 'E1' });
		expect(ws.compareRows).not.toContainEqual({
			quantity: 'equipmentPressureDrop',
			elementId: 'E1'
		});
	});

	it('goal seek offers the item in an Equipment group of results and of variables', async () => {
		const ws = await solveWith(equipmentSolved());
		ws.inspect({ kind: 'component', id: 'E1' });
		await tick();
		const trace = within(await screen.findByRole('dialog', { name: 'Strainer' }));
		await fireEvent.click(
			trace.getByRole('button', { name: 'Use a result of Strainer in goal seek' })
		);
		const dialog = within(await screen.findByRole('dialog', { name: 'Goal seek' }));
		const form = dialog.getByRole('group', { name: 'New goal' });
		const element = within(form).getByRole('combobox', { name: 'Element' }) as HTMLSelectElement;
		expect(element.selectedOptions[0]?.textContent).toBe('Strainer');
		expect(element.selectedOptions[0]?.closest('optgroup')).toHaveAttribute('label', 'Equipment');
		expect(
			within(form)
				.getAllByRole('radio')
				.map((r) => r.closest('label')?.textContent?.trim())
		).toEqual(['Flow', 'Pressure loss', 'Pressure drop']);
		await fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
		await fireEvent.click(dialog.getByRole('button', { name: 'Add variable' }));
		const vform = dialog.getByRole('group', { name: 'New variable' });
		const target = within(vform).getByRole('combobox', { name: 'Element' });
		const option = within(target).getByRole('option', { name: 'Strainer' });
		expect(option.closest('optgroup')).toHaveAttribute('label', 'Equipment');
		await fireEvent.change(target, { target: { value: (option as HTMLOptionElement).value } });
		await waitFor(() =>
			expect(
				within(vform)
					.getAllByRole('radio')
					.map((r) => r.closest('label')?.textContent?.trim())
			).toEqual(['Rated pressure drop', 'Rated flow', 'Rated fluid density'])
		);
	});
});
