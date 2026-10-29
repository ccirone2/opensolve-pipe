/**
 * Relief valves in the results (proposal pressure-relief-valve.md §5, §6 W4-W6): a view of their
 * own after Valves, shown only when the solve has relief valves (with a result, or listed by their
 * RELIEF_VALVE_CLOSED flag), with its table and note, "—" for the pressures of a valve in a
 * floating section; the key values beside the valve in Build, the table's own cells; the trace's
 * Add to comparison and Use in goal seek; Choose results' Relief valves group; and the goal-seek
 * pickers' Relief valves groups, with the set's default box raised to ASME VIII's 15 psi where
 * the overpressure is ASME's, and a certified overpressure on ASME's default that starts at the
 * middle of the bounds. The solve results are made-up test inputs (testing/results.ts); the API
 * is replaced by fakes.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Project, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { reliefProject } from '$lib/testing/helpers';
import { flag, reliefSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { withScenarios } from '$lib/utils/scenarios';

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const build = () => within(screen.getByRole('region', { name: 'Build' }));

async function solveWith(solved: SolvedState, project: Project = reliefProject()) {
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

const radios = (form: HTMLElement) =>
	within(form)
		.getAllByRole('radio')
		.map((r) => r.closest('label')?.textContent?.replace(/\s+/g, ' ').trim());

async function openReliefView() {
	await fireEvent.click(results().getByRole('tab', { name: 'Relief valves' }));
	return results().getByRole('table', { name: 'Results per relief valve' });
}

describe('relief valve results', () => {
	it('have a view of their own after Valves, with its ten columns and note', async () => {
		await solveWith(reliefSolved());
		const tabs = results().getByRole('tablist', { name: 'Results view' });
		expect(
			within(tabs)
				.getAllByRole('tab')
				.map((t) => t.textContent?.trim())
		).toEqual(['Summary', 'Nodes', 'Links', 'Relief valves', 'Boundaries', 'Methods']);
		const table = await openReliefView();
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => h.textContent?.replace(/\s+/g, ' ').trim())
		).toEqual([
			'Relief valve',
			'State',
			'Flow (+ inlet → outlet) L/s',
			'Capacity (full lift) L/s',
			'Flow ÷ capacity %',
			'Inlet pressure kPa(g)',
			'Δp ÷ set %',
			'Lift %',
			'Back pressure kPa(g)',
			'Pressure drop (static) kPa',
			'Head loss m'
		]);
		const row = within(table)
			.getByRole('rowheader', { name: /^Discharge relief/ })
			.closest('tr')!;
		expect(cells(row)).toEqual([
			'Partial lift',
			'2.22',
			'4.27',
			'52',
			'526.1',
			'105.3',
			'53.1',
			'-0.008',
			'526.1',
			'53.8'
		]);
		expect(results().getByText(/^Δp ÷ set is the total-pressure difference/)).toHaveTextContent(
			/Partial lift, between set and full lift, is a linear convention, not a cited law, and is flagged\./
		);
	});

	it('show "—" for the pressures of a valve in a floating section', async () => {
		await solveWith(reliefSolved({ inletPressure: null, backPressure: null }));
		const table = await openReliefView();
		const row = within(table)
			.getByRole('rowheader', { name: /^Discharge relief/ })
			.closest('tr')!;
		const values = cells(row);
		expect(values[4]).toBe('—');
		expect(values[7]).toBe('—');
	});

	it('list a valve with no result by its RELIEF_VALVE_CLOSED flag', async () => {
		const closed = flag({
			code: 'RELIEF_VALVE_CLOSED',
			severity: 'info',
			message:
				"relief valve 'RV1' is closed and has no result: the section on its inlet side has no fixed pressure level (UNDETERMINED_PRESSURE), so the pressure difference across it is undetermined; every level of that section at which the difference does not exceed its set pressure (500000 Pa) is a steady state",
			componentId: 'RV1',
			details: { side: 'inlet', section: 'floating', setHead: 51.09, setPressure: 500000 }
		});
		await solveWith(reliefSolved({}, { reliefValveResults: {}, flags: [closed] }));
		const table = await openReliefView();
		const row = within(table)
			.getByRole('rowheader', { name: /^Discharge relief/ })
			.closest('tr')!;
		expect(cells(row)).toEqual(['Closed (no result)', ...Array(9).fill('—')]);
	});

	it('are not a view without relief valves', async () => {
		await solveWith(reliefSolved({}, { reliefValveResults: {}, flags: [] }));
		expect(results().queryByRole('tab', { name: 'Relief valves' })).toBeNull();
	});

	it("beside the valve in Build: state, flow, inlet pressure and Δp ÷ set, the table's cells", async () => {
		const ws = await solveWith(reliefSolved());
		ws.nav.jumpTo('RV1');
		ws.pane = 'build';
		await tick();
		expect(strip()).toEqual([
			'State: Partial lift',
			'Flow (+ inlet → outlet) (L/s): 2.22',
			'Inlet pressure (kPa(g)): 526.1',
			'Δp ÷ set (%): 105.3'
		]);
	});

	it("the trace adds the valve's flow and state to Compare cases", async () => {
		const project = withScenarios(reliefProject(), [
			{ id: 'S1', name: 'Blocked discharge', overrides: [] }
		]);
		const ws = await solveWith(reliefSolved(), project);
		ws.inspect({ kind: 'component', id: 'RV1' });
		await tick();
		const trace = within(await screen.findByRole('dialog', { name: 'Discharge relief' }));
		expect(
			trace.getByText(/^Pressure relief valve \(API 520, liquids\) · RV1/)
		).toBeInTheDocument();
		await fireEvent.click(trace.getByRole('button', { name: 'Add to comparison' }));
		expect(ws.compareRows).toContainEqual({ quantity: 'reliefFlow', elementId: 'RV1' });
		expect(ws.compareRows).toContainEqual({ quantity: 'reliefState', elementId: 'RV1' });
	});

	it('Choose results offers the valve in a Relief valves group with its five results', async () => {
		const project = withScenarios(reliefProject(), [
			{ id: 'S1', name: 'Blocked discharge', overrides: [] }
		]);
		const ws = await solveWith(reliefSolved(), project);
		ws.comparing = true;
		await tick();
		await fireEvent.click(await results().findByRole('button', { name: 'Choose results…' }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Choose results to compare' }));
		const element = dialog.getByRole('combobox', { name: 'Element' });
		const option = within(element).getByRole('option', { name: 'Discharge relief' });
		expect(option.closest('optgroup')).toHaveAttribute('label', 'Relief valves');
		await fireEvent.change(element, { target: { value: (option as HTMLOptionElement).value } });
		const group = dialog.getByRole('group', { name: 'Results of Discharge relief' });
		expect(
			within(group)
				.getAllByRole('checkbox')
				.map((c) => c.closest('label')?.textContent?.trim())
		).toEqual(['Flow', 'State', 'Inlet pressure', 'Δp ÷ set', 'Pressure drop']);
		await fireEvent.click(within(group).getByRole('checkbox', { name: 'Δp ÷ set' }));
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(ws.compareRows).toContainEqual({ quantity: 'reliefSetRatio', elementId: 'RV1' });
	});

	it('goal seek offers the valve in Relief valves groups: its goals, and its set with a 15 psi floor', async () => {
		const ws = await solveWith(reliefSolved(), reliefProject({ setPressure: 150000 }));
		ws.inspect({ kind: 'component', id: 'RV1' });
		await tick();
		const trace = within(await screen.findByRole('dialog', { name: 'Discharge relief' }));
		await fireEvent.click(
			trace.getByRole('button', { name: 'Use a result of Discharge relief in goal seek' })
		);
		const dialog = within(await screen.findByRole('dialog', { name: 'Goal seek' }));
		const form = dialog.getByRole('group', { name: 'New goal' });
		const element = within(form).getByRole('combobox', { name: 'Element' }) as HTMLSelectElement;
		expect(element.selectedOptions[0]?.textContent).toBe('Discharge relief');
		expect(element.selectedOptions[0]?.closest('optgroup')).toHaveAttribute(
			'label',
			'Relief valves'
		);
		expect(radios(form)).toEqual(['Flow', 'Pressure drop']);
		await fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
		// A letter's capacity is API 520's preliminary values: only its set is a variable.
		await fireEvent.click(dialog.getByRole('button', { name: 'Add variable' }));
		const vform = dialog.getByRole('group', { name: 'New variable' });
		const target = within(vform).getByRole('combobox', { name: 'Element' });
		const option = within(target).getByRole('option', { name: 'Discharge relief' });
		expect(option.closest('optgroup')).toHaveAttribute('label', 'Relief valves');
		await fireEvent.change(target, { target: { value: (option as HTMLOptionElement).value } });
		await waitFor(() => expect(radios(vform)).toEqual(['Set pressure']));
		await fireEvent.click(within(vform).getByRole('radio', { name: 'Set pressure' }));
		await fireEvent.click(within(vform).getByRole('button', { name: 'Add variable' }));
		const card = within(
			await dialog.findByRole('group', { name: /Discharge relief · Set pressure$/ })
		);
		expect(card.getByText('Now 150 kPa')).toBeInTheDocument();
		// Half to twice the set, its lower bound raised to ASME VIII's 15 psi (103.421 kPa): below
		// it a letter's default overpressure has no source, and the API refuses the valve.
		expect(card.getByRole('textbox', { name: /^From/ })).toHaveValue('103.421');
		expect(card.getByRole('textbox', { name: /^To/ })).toHaveValue('300');
	});

	it("goal seek varies a certified capacity's values; on ASME's overpressure it starts in the middle", async () => {
		const ws = await solveWith(
			reliefSolved(),
			reliefProject({ capacity: { kind: 'certified', area: 0.00025, dischargeCoefficient: 0.7 } })
		);
		ws.openGoalSeek();
		const dialog = within(await screen.findByRole('dialog', { name: 'Goal seek' }));
		const add = async (field: string) => {
			await fireEvent.click(dialog.getByRole('button', { name: 'Add variable' }));
			const form = dialog.getByRole('group', { name: 'New variable' });
			const target = within(form).getByRole('combobox', { name: 'Element' });
			const option = within(target).getByRole('option', { name: 'Discharge relief' });
			await fireEvent.change(target, { target: { value: (option as HTMLOptionElement).value } });
			await waitFor(() => within(form).getByRole('radio', { name: field }));
			// Every value of a certified capacity (one already chosen says so).
			expect(radios(form).map((r) => r?.replace(' (already a variable)', ''))).toEqual([
				'Set pressure',
				'Actual orifice area',
				'Rated coefficient of discharge (K)',
				'Overpressure at full lift'
			]);
			await fireEvent.click(within(form).getByRole('radio', { name: field }));
			await fireEvent.click(within(form).getByRole('button', { name: 'Add variable' }));
			return within(
				await dialog.findByRole('group', {
					name: new RegExp(`Discharge relief · ${field.replace(/[()]/g, '\\$&')}$`)
				})
			);
		};
		// The area: API 526's effective areas, D to T (made up for nothing: x-relief-data's).
		const area = await add('Actual orifice area');
		expect(area.getByText('Now 250 mm²')).toBeInTheDocument();
		expect(area.getByRole('textbox', { name: /^From/ })).toHaveValue('70.9676');
		expect(area.getByRole('textbox', { name: /^To/ })).toHaveValue('16774.2');
		const k = await add('Rated coefficient of discharge (K)');
		expect(k.getByRole('textbox', { name: /^From/ })).toHaveValue('0.35');
		expect(k.getByRole('textbox', { name: /^To/ })).toHaveValue('1');
		// ASME's default at a 500 kPa set is 10 %: the box is half to twice it, the start its middle.
		const op = await add('Overpressure at full lift');
		expect(
			op.getByText(
				"Now ASME's 10 % or 3 psi (20.68 kPa), the default (10 % at this set); the search starts at the middle of the bounds"
			)
		).toBeInTheDocument();
		expect(op.getByRole('textbox', { name: /^From/ })).toHaveValue('5');
		expect(op.getByRole('textbox', { name: /^To/ })).toHaveValue('20');
	});
});
