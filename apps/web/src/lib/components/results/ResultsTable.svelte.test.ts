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
import type { Row, RowGroup, Table } from '$lib/utils/results';
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

describe('ResultsTable: row groups, flattened by a sort (pumps-results-layout.md §9 S6b)', () => {
	/**
	 * Two pumps in each of three cases: "Base case (shown)", "Winter (out of date)" and "Failed",
	 * which has no rows; Pump PA flagged in the base case, Pump PB in Winter.
	 */
	function grouped(): Table {
		const row = (group: string, key: string, flow: string, flags: Row['flags']): Row => ({
			key,
			group,
			element: { kind: 'component', id: key },
			name: `Pump ${key}`,
			detail: '',
			cells: { flow, head: flow === '—' ? '—' : '40' },
			flags
		});
		return {
			columns: [
				{ key: 'flow', label: 'Flow', unit: 'L/s', numeric: true },
				{ key: 'head', label: 'Head', unit: 'm', numeric: true }
			],
			groups: [
				{ key: '', label: 'Base case (shown)' },
				{ key: 'S1', label: 'Winter (out of date)', stale: true },
				{ key: 'S2', label: 'Failed' }
			],
			rows: [
				row('', 'PA', '21.5', [warning]),
				row('', 'PB', '19.2', []),
				row('S1', 'PA', '—', []),
				row('S1', 'PB', '17.4', [invalid])
			]
		};
	}
	/** The caller's heading: its label and a second line. */
	const groupHeading = createRawSnippet((group: () => RowGroup) => ({
		render: () =>
			`<span data-test-heading>${group().label}<span class="block">line of ${group().key || 'base'}</span></span>`
	}));
	const props = () => ({
		table: grouped(),
		caption: 'Running combinations',
		first: 'Pump',
		groupColumn: 'Case',
		flagLine,
		groupHeading
	});
	const squash = (t: string | null | undefined) => (t ?? '').replace(/\s+/g, ' ').trim();
	/** Each body row group: its heading's words (null in the flat form) and its rows. */
	const read = () =>
		screen
			.getAllByRole('rowgroup')
			.slice(1)
			.map((g) => {
				const heading = g.querySelector('th[scope="rowgroup"]');
				return {
					heading: heading ? squash(heading.textContent) : null,
					rows: within(g)
						.getAllByRole('row')
						.filter((r) => !r.querySelector('th[scope="rowgroup"]'))
						.map((r) => {
							const header = within(r).queryByRole('rowheader');
							if (!header)
								return `flags of ${r.querySelector('[data-row-notes]')!.getAttribute('data-row-notes')}`;
							const cells = within(r)
								.getAllByRole('cell')
								.map((c) => squash(c.textContent));
							return [squash(header.textContent), ...cells].join(' | ');
						})
				};
			});
	const columns = () => screen.getAllByRole('columnheader').map((h) => squash(h.textContent));
	const flow = () => screen.getByRole('columnheader', { name: /^Flow/ });

	it('in the table’s order a row group each, headed by its lines in one cell across the row, a group with no row too; no group column', () => {
		render(ResultsTable, props());
		expect(read()).toEqual([
			{
				heading: 'Base case (shown)line of base',
				rows: ['Pump PA | 21.5 | 40', 'flags of PA', 'Pump PB | 19.2 | 40']
			},
			{
				heading: 'Winter (out of date)line of S1',
				rows: ['Pump PA | — | —', 'Pump PB | 17.4 | 40', 'flags of PB']
			},
			{ heading: 'Failedline of S2', rows: [] }
		]);
		expect(columns()).toEqual(['Pump', 'Flow L/s', 'Head m']);
		for (const th of document.querySelectorAll('th[scope="rowgroup"]')) {
			expect(th).toHaveAttribute('role', 'rowheader');
			expect(th).toHaveAttribute('colspan', '3');
			expect(th.querySelector('[data-test-heading]')).not.toBeNull();
		}
		// No fill on a current group's heading, so the box's sideways shadow runs past it (§15
		// item 157); a rule above each but the first.
		const [first, second, third] = [...document.querySelectorAll('th[scope="rowgroup"]')];
		expect(first!.className).not.toMatch(/(^|\s)bg-/);
		expect(third!.className).not.toMatch(/(^|\s)bg-/);
		expect(first).not.toHaveClass('border-t');
		expect(second).toHaveClass('border-t');
		expect(third).toHaveClass('border-t');
		// Without a heading of the caller's, the group's label, sticky at the box's visible width.
		cleanup();
		render(ResultsTable, { ...props(), groupHeading: undefined });
		const label = document.querySelector('th[scope="rowgroup"] > span')!;
		expect(label).toHaveTextContent('Base case (shown)');
		expect(label).toHaveClass('sticky', 'left-0', 'w-[100cqw]');
	});

	it('a sort flattens them into one table, its group column after the name and no sort of its own, the smallest first; clearing the sort brings the groups back in order', async () => {
		render(ResultsTable, props());
		const before = read();
		await fireEvent.click(within(flow()).getByRole('button'));
		expect(flow()).toHaveAttribute('aria-sort', 'ascending');
		expect(columns()).toEqual(['Pump', 'Case', 'Flow L/s', 'Head m']);
		// The group column: a plain heading, not a sort.
		const caseHeading = screen.getByRole('columnheader', { name: 'Case' });
		expect(within(caseHeading).queryByRole('button')).toBeNull();
		expect(
			[...(screen.getByRole('combobox', { name: 'Sort by' }) as HTMLSelectElement).options].map(
				(o) => o.text
			)
		).toEqual(['Table order', 'Pump', 'Flow (L/s)', 'Head (m)']);
		// One row group, the rows by flow, the one with none last; each row's case named.
		expect(read()).toEqual([
			{
				heading: null,
				rows: [
					'Pump PB | Winter (out of date) | 17.4 | 40',
					'flags of PB',
					'Pump PB | Base case (shown) | 19.2 | 40',
					'Pump PA | Base case (shown) | 21.5 | 40',
					'flags of PA',
					'Pump PA | Winter (out of date) | — | —'
				]
			}
		]);
		for (const cell of document.querySelectorAll('td[data-label="Case"]')) {
			// A phone's pair: its header whole beside its words (::before content).
			expect(cell).toHaveClass(
				'max-sm:before:content-[attr(data-label)]',
				'max-sm:before:shrink-0'
			);
			// Its words wrap at 12 rem, their own width the column's (a name's rule).
			expect(cell.firstElementChild).toHaveClass('w-max', 'max-w-48', 'wrap-break-word');
			expect(cell.firstElementChild).toHaveTextContent(cell.textContent!);
		}
		// The flag lines span the row, the group column with it.
		for (const notes of document.querySelectorAll('[data-row-notes]')) {
			expect(notes.closest('td')).toHaveAttribute('colspan', '4');
		}
		// Descending, then the table's order: the groups again, as before.
		await fireEvent.click(within(flow()).getByRole('button'));
		expect(read()[0]!.rows[0]).toBe('Pump PA | Base case (shown) | 21.5 | 40');
		await fireEvent.click(within(flow()).getByRole('button'));
		expect(flow()).not.toHaveAttribute('aria-sort');
		expect(read()).toEqual(before);
		expect(columns()).toEqual(['Pump', 'Flow L/s', 'Head m']);
		// A phone's "Sort by" does the same: a field flattens, "Table order" groups again.
		const field = screen.getByRole('combobox', { name: 'Sort by' });
		await fireEvent.change(field, { target: { value: 'flow' } });
		expect(read()).toHaveLength(1);
		expect(columns()).toContain('Case');
		await fireEvent.change(field, { target: { value: '' } });
		expect(read()).toEqual(before);
	});

	it('Fields hides a column in both forms, the headings and flag lines spanning what is shown', async () => {
		render(ResultsTable, props());
		await fireEvent.click(screen.getByRole('button', { name: /^Fields/ }));
		const menu = screen.getByRole('group', { name: 'Fields shown in Running combinations' });
		// The group column is no field: it names the row, as the name does.
		expect(
			within(menu)
				.getAllByRole('checkbox')
				.map((b) => squash(b.closest('label')!.textContent))
		).toEqual(['Flow (L/s)', 'Head (m)']);
		await fireEvent.click(within(menu).getByRole('checkbox', { name: /^Head/ }));
		expect(columns()).toEqual(['Pump', 'Flow L/s']);
		expect(document.querySelectorAll('td[data-label^="Head"]')).toHaveLength(0);
		for (const th of document.querySelectorAll('th[scope="rowgroup"]')) {
			expect(th).toHaveAttribute('colspan', '2');
		}
		await fireEvent.click(within(flow()).getByRole('button'));
		expect(columns()).toEqual(['Pump', 'Case', 'Flow L/s']);
		expect(document.querySelectorAll('td[data-label^="Head"]')).toHaveLength(0);
		for (const notes of document.querySelectorAll('[data-row-notes]')) {
			expect(notes.closest('td')).toHaveAttribute('colspan', '3');
		}
	});

	it('Flagged only keeps the flagged rows with their flag lines in both forms, and only the groups with one', async () => {
		render(ResultsTable, props());
		const toggle = screen.getByRole('checkbox', { name: 'Flagged only (2 of 4)' });
		await fireEvent.click(toggle);
		expect(read()).toEqual([
			{ heading: 'Base case (shown)line of base', rows: ['Pump PA | 21.5 | 40', 'flags of PA'] },
			{ heading: 'Winter (out of date)line of S1', rows: ['Pump PB | 17.4 | 40', 'flags of PB'] }
		]);
		await fireEvent.click(within(flow()).getByRole('button'));
		expect(read()).toEqual([
			{
				heading: null,
				rows: [
					'Pump PB | Winter (out of date) | 17.4 | 40',
					'flags of PB',
					'Pump PA | Base case (shown) | 21.5 | 40',
					'flags of PA'
				]
			}
		]);
		await fireEvent.click(toggle);
		expect(read()[0]!.rows).toHaveLength(6);
	});

	it('a group out of date amber whole in both forms: in the table each cell, below 640 px its block, flattened each row', async () => {
		render(ResultsTable, props());
		const cells = (el: Element) => [...el.querySelectorAll(':scope > tr > th, :scope > tr > td')];
		const [current, stale] = screen.getAllByRole('rowgroup').slice(1);
		expect(stale).toHaveClass('max-sm:block', 'max-sm:bg-amber-50/60');
		for (const cell of cells(stale!)) {
			expect(cell.className).toMatch(/(^|\s)bg-amber-50(\/60)?(\s|$)/);
			expect(cell).toHaveClass('max-sm:bg-transparent');
		}
		expect(current!.className).not.toMatch(/amber/);
		for (const cell of cells(current!)) expect(cell.className).not.toMatch(/amber/);
		// Flattened, each of its rows (and its flag line) amber, on a phone the row's block.
		await fireEvent.click(within(flow()).getByRole('button'));
		const body = screen.getAllByRole('rowgroup')[1]!;
		expect(body.className).not.toMatch(/amber/);
		for (const tr of body.querySelectorAll(':scope > tr')) {
			const winter =
				squash(tr.querySelector('td[data-label="Case"]')?.textContent) === 'Winter (out of date)' ||
				(tr.querySelector('[data-row-notes]') !== null &&
					squash(tr.previousElementSibling!.querySelector('td[data-label="Case"]')!.textContent) ===
						'Winter (out of date)');
			expect(tr.className.includes('max-sm:bg-amber-50/60'), squash(tr.textContent)).toBe(winter);
			for (const cell of tr.querySelectorAll(':scope > th, :scope > td')) {
				expect(/(^|\s)bg-amber-50(\/60)?(\s|$)/.test(cell.className), squash(tr.textContent)).toBe(
					winter
				);
			}
		}
	});

	it('draws a cell’s content of the caller’s, by its row and column', () => {
		const cellContent = createRawSnippet((row: () => Row, key: () => string) => ({
			render: () => `<span data-test-cell>${key()} of ${row().group || 'base'}:${row().key}</span>`
		}));
		render(ResultsTable, { ...props(), cellContent });
		// Winter's group, its first row: Pump PA's flow, by its row and its column.
		const winter = screen.getAllByRole('rowgroup')[2]!;
		const cells = within(winter)
			.getAllByRole('cell')
			.filter((c) => c.dataset.label === 'Flow (L/s)');
		expect(cells.map((c) => c.querySelector('[data-test-cell]')?.textContent)).toEqual([
			'flow of S1:PA',
			'flow of S1:PB'
		]);
		// Without it, the cell's own text.
		cleanup();
		render(ResultsTable, props());
		expect(document.querySelector('[data-test-cell]')).toBeNull();
		expect(
			screen.getAllByRole('cell').find((c) => c.dataset.label === 'Flow (L/s)')
		).toHaveTextContent(/^21\.5$/);
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
