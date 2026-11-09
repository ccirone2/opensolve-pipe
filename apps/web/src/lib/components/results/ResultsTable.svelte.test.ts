/**
 * ResultsTable's props for a table in a card that reads no workspace (proposal
 * pumps-results-layout.md §5.3 Station, §9 S6a): the flag line drawn by the caller in place of
 * FlagBadge, the row header's content, the box a named region and a Tab stop, the Fields choice
 * kept under a key of its own. Each is drawn only where given: every other table keeps its
 * FlagBadges, its name buttons and its box as before (the Links view, mounted with its workspace).
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { createRawSnippet, tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import type { Row, Table } from '$lib/utils/results';
import ResultsTable from './ResultsTable.svelte';

afterEach(() => localStorage.clear());

const warning = flag({ code: 'CAVITATION', severity: 'warning', message: 'NPSH margin is low' });
const invalid = flag({
	code: 'PUMP_FLOW_REVERSAL',
	severity: 'invalid',
	message: 'Flow runs backwards'
});

/** Three pumps, two of them flagged; no workspace anywhere (as the card's tests mount none). */
function table(): Table {
	const row = (key: string, name: string, flow: string, flags: Row['flags']): Row => ({
		key,
		element: { kind: 'component', id: key },
		name,
		detail: '',
		cells: { flow, head: '40' },
		flags
	});
	return {
		columns: [
			{ key: 'flow', label: 'Flow', unit: 'L/s', numeric: true },
			{ key: 'head', label: 'Head', unit: 'm', numeric: true }
		],
		rows: [
			row('PA', 'Pump PA', '21.5', [warning]),
			row('PB', 'Pump PB', '19.2', []),
			row('PC', 'Pump PC', '20.1', [warning, invalid])
		]
	};
}

/** The same rows without flags: a table that draws no FlagBadge, so it needs no workspace. */
const unflagged = (): Table => {
	const t = table();
	return { ...t, rows: t.rows.map((r) => ({ ...r, flags: [] })) };
};

/** The caller's flag line: one element per flag, its words in sight (no workspace read). */
const flagLine = createRawSnippet((row: () => Row) => ({
	render: () =>
		`<ul data-test-flag-line>${row()
			.flags.map((f) => `<li>${f.severity} ${f.message}</li>`)
			.join('')}</ul>`
}));

/** The caller's name: its own button, with a marker. */
const name = createRawSnippet((row: () => Row) => ({
	render: () => `<span data-test-name>▲ ${row().name}</span>`
}));

const body = () => screen.getAllByRole('rowgroup')[1]!;
const rowOf = (pump: string) =>
	within(body())
		.getAllByRole('row')
		.find((r) => within(r).queryByRole('rowheader', { name: new RegExp(pump) }))!;

describe('ResultsTable: a flag line, a name and a region of the caller’s (pumps-results-layout.md §9 S6a)', () => {
	it('draws the flag line given under each flagged row, labelled Flags, in place of FlagBadge (no workspace)', () => {
		render(ResultsTable, {
			table: table(),
			caption: 'The pumps in the group',
			first: 'Pump',
			flagLine
		});
		for (const [pump, flags] of [
			['PA', 1],
			['PC', 2]
		] as const) {
			const notes = rowOf(`Pump ${pump}`).nextElementSibling!.querySelector<HTMLElement>(
				`[data-row-notes="${pump}"]`
			)!;
			expect(notes).toHaveAttribute('data-label', 'Flags');
			// At the box's visible width, a block of its own (no badge row).
			expect(notes).toHaveClass('sticky', 'left-0', 'w-[100cqw]');
			expect(notes).not.toHaveClass('flex');
			const line = notes.querySelector('[data-test-flag-line]')!;
			expect(line.querySelectorAll('li')).toHaveLength(flags);
			// No FlagBadge: no tooltip and no hidden copy of the words.
			expect(notes.querySelector('[title]')).toBeNull();
			expect(notes.querySelector('.sr-only')).toBeNull();
			// Its one cell spans the row.
			expect(notes.closest('td')).toHaveAttribute('colspan', '3');
		}
		// A row without flags has no line.
		expect(rowOf('Pump PB').nextElementSibling).toBe(rowOf('Pump PC'));
	});

	it('draws the name given in the row header, the column then as wide as the name; else its own button', () => {
		const onselect = vi.fn();
		render(ResultsTable, { table: unflagged(), caption: 'Results', first: 'Pump', name, onselect });
		const header = within(rowOf('Pump PA')).getByRole('rowheader');
		expect(header.querySelector('[data-test-name]')).toHaveTextContent('▲ Pump PA');
		expect(within(header).queryByRole('button')).toBeNull();
		expect(header).toHaveClass('sticky', 'left-0', 'sm:w-auto');
		expect(header).not.toHaveClass('sm:min-w-[11rem]');
		expect(header).not.toHaveClass('sm:max-w-[16rem]');
		cleanup();
		render(ResultsTable, { table: unflagged(), caption: 'Results', first: 'Pump', onselect });
		const own = within(rowOf('Pump PA')).getByRole('rowheader');
		expect(own).toHaveClass('sm:min-w-[11rem]', 'sm:max-w-[16rem]');
		expect(own.querySelector('[data-test-name]')).toBeNull();
		within(own).getByRole('button', { name: 'Pump PA' }).click();
		expect(onselect).toHaveBeenCalledWith(expect.objectContaining({ key: 'PA' }));
	});

	it('makes its box a region named by the element given and a Tab stop; else neither', () => {
		const label = document.createElement('p');
		label.id = 'made-up-title';
		label.textContent = 'The pumps in the group, Winter';
		document.body.append(label);
		render(ResultsTable, {
			table: table(),
			caption: 'The pumps in the group, Winter',
			first: 'Pump',
			labelledby: 'made-up-title',
			flagLine
		});
		const region = screen.getByRole('region', { name: 'The pumps in the group, Winter' });
		expect(region).toHaveAttribute('tabindex', '0');
		expect(region).toHaveClass('@container', 'scroll-shadow-x', 'overflow-auto', 'relative');
		expect(within(region).getByRole('table', { name: 'The pumps in the group, Winter' })).toBe(
			screen.getByRole('table')
		);
		label.remove();
		cleanup();
		render(ResultsTable, { table: table(), caption: 'Results', first: 'Pump', flagLine });
		const box = screen.getByRole('table').parentElement!;
		expect(box).not.toHaveAttribute('role');
		expect(box).not.toHaveAttribute('tabindex');
		expect(box).not.toHaveClass('relative');
		expect(box).toHaveClass('@container', 'scroll-shadow-x', 'overflow-auto');
	});

	it('keeps the Fields choice under the key given, whatever the caption (it names the case)', async () => {
		const view = render(ResultsTable, {
			table: table(),
			caption: 'The pumps in the group, Base case',
			first: 'Pump',
			fieldsKey: 'The pumps in the group',
			flagLine
		});
		await fireEvent.click(screen.getByRole('button', { name: /^Fields/ }));
		const menu = screen.getByRole('group', {
			name: 'Fields shown in The pumps in the group, Base case'
		});
		await fireEvent.click(within(menu).getByRole('checkbox', { name: /^Head/ }));
		expect(screen.queryByRole('columnheader', { name: /^Head/ })).toBeNull();
		expect(localStorage.getItem('opensolve-pipe:results-fields:The pumps in the group')).toBe(
			'["head"]'
		);
		// Another case shown: the same choice.
		await view.rerender({ caption: 'The pumps in the group, Winter' });
		await tick();
		expect(screen.queryByRole('columnheader', { name: /^Head/ })).toBeNull();
		expect(screen.getByRole('columnheader', { name: /^Flow/ })).toBeInTheDocument();
		// The flag line still spans the row: the name and the one column shown.
		const notes = rowOf('Pump PA').nextElementSibling!.querySelector('[data-row-notes]')!;
		expect(notes.closest('td')).toHaveAttribute('colspan', '2');
	});

	it('keeps each flagged row with its flag line under Flagged only and under a sort', async () => {
		render(ResultsTable, { table: table(), caption: 'Results', first: 'Pump', flagLine });
		const order = () =>
			within(body())
				.getAllByRole('row')
				.map(
					(r) =>
						within(r).queryByRole('rowheader')?.textContent?.trim() ??
						`flags of ${r.querySelector('[data-row-notes]')?.getAttribute('data-row-notes')}`
				);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Flagged only (2 of 3)' }));
		expect(order()).toEqual(['Pump PA', 'flags of PA', 'Pump PC', 'flags of PC']);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Flagged only (2 of 3)' }));
		await fireEvent.click(
			within(screen.getByRole('columnheader', { name: /^Flow/ })).getByRole('button')
		);
		expect(screen.getByRole('columnheader', { name: /^Flow/ })).toHaveAttribute(
			'aria-sort',
			'ascending'
		);
		expect(order()).toEqual(['Pump PB', 'Pump PC', 'flags of PC', 'Pump PA', 'flags of PA']);
	});
});

describe('below 640 px the headings’ sort buttons leave the Tab order (§9 S6a; WCAG 2.4.7, 2.4.11)', () => {
	afterEach(() => vi.unstubAllGlobals());
	/** A window as wide as a phone's, or not: matchMedia answers the phone's query so. */
	const width = (phone: boolean) =>
		vi.stubGlobal('matchMedia', (media: string) => ({
			matches: phone && media === '(max-width: 639px)',
			media,
			onchange: null,
			addEventListener: () => {},
			removeEventListener: () => {},
			addListener: () => {},
			removeListener: () => {},
			dispatchEvent: () => false
		}));
	const buttons = () =>
		screen.getAllByRole('columnheader').map((h) => within(h).getByRole('button'));

	it('on a phone, where they are hidden and "Sort by" sorts: still buttons, out of the Tab order', () => {
		width(true);
		render(ResultsTable, { table: table(), caption: 'Results', first: 'Pump', flagLine });
		expect(buttons()).toHaveLength(3);
		for (const button of buttons()) expect(button).toHaveAttribute('tabindex', '-1');
		// "Sort by" and Fields stay Tab stops: the list's sort and its fields.
		expect(screen.getByRole('combobox', { name: 'Sort by' })).not.toHaveAttribute('tabindex');
		expect(screen.getByRole('button', { name: /^Fields/ })).not.toHaveAttribute('tabindex');
	});

	it('from 640 px, where they show: each a Tab stop', () => {
		width(false);
		render(ResultsTable, { table: table(), caption: 'Results', first: 'Pump', flagLine });
		for (const button of buttons()) expect(button).not.toHaveAttribute('tabindex');
	});
});

describe('every other ResultsTable keeps its FlagBadges, its name buttons and its box (§9 S6a)', () => {
	it('the Links view: a FlagBadge with its words as a tooltip and hidden text, no Flags label, no region', async () => {
		const solve = vi.fn(() =>
			Promise.resolve(
				response(
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
				)
			)
		);
		render(WorkspaceView, {
			workspace: testWorkspace(pumpTransferExample(), { solver: { solve } })
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		const results = within(screen.getByRole('region', { name: 'Results' }));
		await results.findByRole('heading', { name: 'Converged' });
		await fireEvent.click(results.getByRole('tab', { name: 'Links' }));
		const panel = results.getAllByRole('tabpanel').find((p) => !p.hidden)!;
		const notes = panel.querySelector<HTMLElement>('[data-row-notes="L2"]')!;
		expect(notes).not.toHaveAttribute('data-label');
		expect(notes).toHaveClass('sticky', 'flex', 'flex-wrap', 'items-center', 'gap-1');
		const badge = notes.querySelector('[title]')!;
		expect(badge.getAttribute('title')).toMatch(/Transitional flow/);
		expect(badge).toHaveTextContent(/^Warning: .*Transitional flow/);
		expect(badge.querySelector('.sr-only')!.textContent).toMatch(/^: .*Transitional flow/);
		// Its name a button (the element's results and trace); its column 11 to 16 rem.
		const header = within(panel).getAllByRole('rowheader')[0]!;
		expect(within(header).getByRole('button')).toBeInTheDocument();
		expect(header).toHaveClass('sm:min-w-[11rem]', 'sm:max-w-[16rem]');
		// Its box: no region, no Tab stop.
		const box = within(panel).getByRole('table').parentElement!;
		expect(box).not.toHaveAttribute('role');
		expect(box).not.toHaveAttribute('tabindex');
	});
});
