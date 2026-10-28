/**
 * Orifice plates in the results (proposal orifice-plate.md §5.3, §6 W4-W6): a view of their own,
 * shown only when the solve has plates, with its table and note; the key values beside the plate
 * in Build (no reading without taps); the trace's Add to comparison and Use in goal seek; Choose
 * results' Orifice plates group; and the goal-seek pickers' groups, with the bore's default
 * bounds from the inlet pipe as it is now (else the current solve's pipe bore, never an
 * out-of-date one's) and a C on ISO 5167-2's that starts at the middle of the bounds. The solve
 * results are made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Project, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { orificeProject } from '$lib/testing/helpers';
import { TEST_LIBRARY } from '$lib/testing/library';
import { INCH } from '$lib/utils/units';
import { orificeSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { withScenarios } from '$lib/utils/scenarios';

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const build = () => within(screen.getByRole('region', { name: 'Build' }));

async function solveWith(solved: SolvedState, project: Project = orificeProject()) {
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

describe('orifice plate results', () => {
	it('have a view of their own, with its ten columns and note', async () => {
		await solveWith(orificeSolved({ taps: 'flange', differentialPressure: 57100 }));
		const tabs = results().getByRole('tablist', { name: 'Results view' });
		expect(
			within(tabs)
				.getAllByRole('tab')
				.map((t) => t.textContent?.trim())
		).toEqual(['Summary', 'Nodes', 'Links', 'Orifices', 'Boundaries', 'Methods']);
		await fireEvent.click(results().getByRole('tab', { name: 'Orifices' }));
		const table = results().getByRole('table', { name: 'Results per orifice plate' });
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => h.textContent?.replace(/\s+/g, ' ').trim())
		).toEqual([
			'Orifice plate',
			'Flow (+ inlet → outlet) L/s',
			'Permanent loss kPa',
			'Differential pressure (taps) kPa',
			'β',
			'C',
			'C from',
			'Re (inlet pipe)',
			'Vena contracta pressure kPa(g)',
			'Pressure drop (static) kPa',
			'Head loss m'
		]);
		const row = within(table)
			.getByRole('rowheader', { name: /^Bypass orifice/ })
			.closest('tr')!;
		expect(cells(row)).toEqual([
			'13',
			'42.1',
			'57.1',
			'0.489',
			'0.6047',
			'ISO 5167-2',
			'160000',
			'-20',
			'42.1',
			'4.3'
		]);
		expect(results().getByText(/^Permanent loss is ISO 5167-2's pressure loss/)).toHaveTextContent(
			/Flow, the losses and the differential pressure are negative when the flow runs from outlet to inlet\.$/
		);
	});

	it('are not a view without plates', async () => {
		await solveWith(orificeSolved({}, { orificeResults: {} }));
		expect(results().queryByRole('tab', { name: 'Orifices' })).toBeNull();
	});

	it('beside the plate in Build: flow and permanent loss, and the reading with taps', async () => {
		const ws = await solveWith(orificeSolved());
		ws.nav.jumpTo('O1');
		ws.pane = 'build';
		await tick();
		expect(strip()).toEqual(['Flow (+ inlet → outlet) (L/s): 13', 'Permanent loss (kPa): 42.1']);
	});

	it('beside a meter in Build: flow, permanent loss and the differential pressure', async () => {
		const ws = await solveWith(
			orificeSolved({ taps: 'flange', differentialPressure: 57100 }),
			orificeProject({ taps: 'flange' })
		);
		ws.nav.jumpTo('O1');
		ws.pane = 'build';
		await tick();
		expect(strip()).toEqual([
			'Flow (+ inlet → outlet) (L/s): 13',
			'Permanent loss (kPa): 42.1',
			'Differential pressure (taps) (kPa): 57.1'
		]);
	});

	it("the trace adds the plate's flow and permanent loss to Compare cases", async () => {
		const project = withScenarios(orificeProject(), [
			{ id: 'S1', name: 'Bigger bore', overrides: [] }
		]);
		const ws = await solveWith(orificeSolved(), project);
		ws.inspect({ kind: 'component', id: 'O1' });
		await tick();
		const trace = within(await screen.findByRole('dialog', { name: 'Bypass orifice' }));
		expect(trace.getByText(/^Orifice plate \(ISO 5167-2\) · O1/)).toBeInTheDocument();
		await fireEvent.click(trace.getByRole('button', { name: 'Add to comparison' }));
		expect(ws.compareRows).toContainEqual({ quantity: 'orificeFlow', elementId: 'O1' });
		expect(ws.compareRows).toContainEqual({ quantity: 'orificePressureLoss', elementId: 'O1' });
		expect(ws.compareRows).not.toContainEqual({
			quantity: 'orificeDifferentialPressure',
			elementId: 'O1'
		});
	});

	it('Choose results offers the plate in an Orifice plates group with its four results', async () => {
		const project = withScenarios(orificeProject(), [
			{ id: 'S1', name: 'Bigger bore', overrides: [] }
		]);
		const ws = await solveWith(orificeSolved(), project);
		ws.comparing = true;
		await tick();
		await fireEvent.click(await results().findByRole('button', { name: 'Choose results…' }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Choose results to compare' }));
		const element = dialog.getByRole('combobox', { name: 'Element' });
		const option = within(element).getByRole('option', { name: 'Bypass orifice' });
		expect(option.closest('optgroup')).toHaveAttribute('label', 'Orifice plates');
		await fireEvent.change(element, { target: { value: (option as HTMLOptionElement).value } });
		const group = dialog.getByRole('group', { name: 'Results of Bypass orifice' });
		expect(
			within(group)
				.getAllByRole('checkbox')
				.map((c) => c.closest('label')?.textContent?.trim())
		).toEqual(['Flow', 'Permanent loss', 'Differential pressure (taps)', 'Pressure drop']);
		await fireEvent.click(within(group).getByRole('checkbox', { name: 'Pressure drop' }));
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(ws.compareRows).toContainEqual({ quantity: 'orificePressureDrop', elementId: 'O1' });
	});

	it('goal seek offers the plate in Orifice plates groups of results and of variables', async () => {
		const ws = await solveWith(orificeSolved());
		ws.inspect({ kind: 'component', id: 'O1' });
		await tick();
		const trace = within(await screen.findByRole('dialog', { name: 'Bypass orifice' }));
		await fireEvent.click(
			trace.getByRole('button', { name: 'Use a result of Bypass orifice in goal seek' })
		);
		const dialog = within(await screen.findByRole('dialog', { name: 'Goal seek' }));
		const form = dialog.getByRole('group', { name: 'New goal' });
		const element = within(form).getByRole('combobox', { name: 'Element' }) as HTMLSelectElement;
		expect(element.selectedOptions[0]?.textContent).toBe('Bypass orifice');
		expect(element.selectedOptions[0]?.closest('optgroup')).toHaveAttribute(
			'label',
			'Orifice plates'
		);
		// A plate without taps has no reading: the published need says why, and the choice is off.
		expect(radios(form)).toEqual([
			'Flow',
			'Permanent loss',
			'Differential pressure (taps) (the orifice plate has no pressure taps, so it has no reading)',
			'Pressure drop'
		]);
		expect(
			within(form).getByRole('radio', { name: /^Differential pressure \(taps\)/ })
		).toHaveAttribute('aria-disabled', 'true');
		await fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
		await fireEvent.click(dialog.getByRole('button', { name: 'Add variable' }));
		const vform = dialog.getByRole('group', { name: 'New variable' });
		const target = within(vform).getByRole('combobox', { name: 'Element' });
		const option = within(target).getByRole('option', { name: 'Bypass orifice' });
		expect(option.closest('optgroup')).toHaveAttribute('label', 'Orifice plates');
		await fireEvent.change(target, { target: { value: (option as HTMLOptionElement).value } });
		await waitFor(() => expect(radios(vform)).toEqual(['Bore diameter', 'Discharge coefficient']));
		// The bore: ISO 5167-2's β range on the current solve's pipe bore (0.1023 m, made up): the
		// pipe library is not loaded here, so the form cannot resolve D.
		await fireEvent.click(within(vform).getByRole('radio', { name: 'Bore diameter' }));
		await fireEvent.click(within(vform).getByRole('button', { name: 'Add variable' }));
		const card = within(
			await dialog.findByRole('group', { name: /Bypass orifice · Bore diameter$/ })
		);
		expect(card.getByText('Now 50 mm')).toBeInTheDocument();
		expect(card.getByRole('textbox', { name: /^From/ })).toHaveValue('10.23');
		expect(card.getByRole('textbox', { name: /^To/ })).toHaveValue('76.725');
		// The C on ISO 5167-2's: the search starts at the middle of the bounds.
		await fireEvent.click(dialog.getByRole('button', { name: 'Add variable' }));
		const again = dialog.getByRole('group', { name: 'New variable' });
		const plate = within(again).getByRole('combobox', { name: 'Element' });
		await fireEvent.change(plate, {
			target: {
				value: (within(plate).getByRole('option', { name: 'Bypass orifice' }) as HTMLOptionElement)
					.value
			}
		});
		await fireEvent.click(within(again).getByRole('radio', { name: 'Discharge coefficient' }));
		await fireEvent.click(within(again).getByRole('button', { name: 'Add variable' }));
		const c = within(
			await dialog.findByRole('group', { name: /Bypass orifice · Discharge coefficient$/ })
		);
		expect(
			c.getByText(
				"Now ISO 5167-2's discharge coefficient, the default (0.6047 at D and D/2 tappings in the last solve); the search starts at the middle of the bounds"
			)
		).toBeInTheDocument();
		expect(c.getByRole('textbox', { name: /^From/ })).toHaveValue('0.30235');
		expect(c.getByRole('textbox', { name: /^To/ })).toHaveValue('1');
	});

	it("goal seek's defaults follow the inlet pipe as it is now, never an out-of-date solve", async () => {
		// The solve's pipe bore is 0.1023 m (made up); the inlet pipe then becomes NPS 3 Sch 40,
		// TEST_LIBRARY's 77.92 mm, so the solve is out of date.
		const solve = vi.fn(() => Promise.resolve(response(orificeSolved())));
		const ws = testWorkspace(orificeProject(), {
			solver: { solve },
			library: { getLibrary: () => Promise.resolve(TEST_LIBRARY) }
		});
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		await waitFor(() => expect(ws.library.libraryStatus).toBe('ready'));
		ws.editConnection('L1', 'NPS 3', (c) => ({
			...c,
			piping: { ...c.piping, pipes: [{ ...c.piping.pipes[0]!, nominalSize: 3 * INCH }] }
		}));
		await tick();
		expect(ws.store.results.stale).toBe(true);
		ws.openGoalSeek();
		const dialog = within(await screen.findByRole('dialog', { name: 'Goal seek' }));
		const add = async (field: string) => {
			await fireEvent.click(dialog.getByRole('button', { name: 'Add variable' }));
			const form = dialog.getByRole('group', { name: 'New variable' });
			const target = within(form).getByRole('combobox', { name: 'Element' });
			const option = within(target).getByRole('option', { name: 'Bypass orifice' });
			await fireEvent.change(target, { target: { value: (option as HTMLOptionElement).value } });
			await waitFor(() => within(form).getByRole('radio', { name: field }));
			await fireEvent.click(within(form).getByRole('radio', { name: field }));
			await fireEvent.click(within(form).getByRole('button', { name: 'Add variable' }));
			return within(
				await dialog.findByRole('group', { name: new RegExp(`Bypass orifice · ${field}$`) })
			);
		};
		// ISO's β range on the current D, 0.1 × 77.92 mm to 0.75 × 77.92 mm.
		const bore = await add('Bore diameter');
		expect(bore.getByRole('textbox', { name: /^From/ })).toHaveValue('7.792');
		expect(bore.getByRole('textbox', { name: /^To/ })).toHaveValue('58.44');
		// The out-of-date solve's C is not read: "Now" has no number and the box is 0.5 to 1.
		const c = await add('Discharge coefficient');
		expect(
			c.getByText(
				"Now ISO 5167-2's discharge coefficient, the default; the search starts at the middle of the bounds"
			)
		).toBeInTheDocument();
		expect(c.getByRole('textbox', { name: /^From/ })).toHaveValue('0.5');
		expect(c.getByRole('textbox', { name: /^To/ })).toHaveValue('1');
	});
});
