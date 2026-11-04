<!--
	The Pump lineups table (CLAUDE.md D24, proposal pump-lineups.md §8, slice L2): the Scenarios
	manager's second tab, every case × every pump, on or off. Presentation and focus only: the model
	and every word are utils/lineup-table.ts's, and a press is Build's own Status edit through
	ws.editScenario (quiet: the manager's status and alert lines say what it did, §8.6).

	Desktop and tablet (≥ 640 px, §8.2 to §8.9): the intro, then the table in a scroll box whose
	header rows stick to its top and case column to its left (scroll padding keeps a focused cell's
	focus ring clear of them, and of the box's bottom edge). A grid with explicit roles: the group
	header row only with two groups or more, the base case read-only (gridcells, aria-readonly), a
	switch per scenario cell named by its visible headers (aria-labelledby, never its state word),
	the case's own value marked three ways (a teal ring and corner, the description, the title). One
	Tab stop, roving tabindex: the active cell is derived from the cell last wanted (decision 26), so
	it never outlives its row or column; the arrows, Home, End, Ctrl+Home and Ctrl+End move it, and
	the focus is put back on it after a press, an undo or redo, a rename or a filter change made
	with the focus in the grid (a keyed reorder moves the focused node, which loses the focus).

	Phone (< 640 px, §8.10): one case at a time, only one of the two layouts in the DOM. "Case to
	edit" (derived: the pick while it exists, else the default), its line, then each group's pumps:
	Build's segments with ChangeNote's Changed · Base · Reset, every one through the same
	editScenario (a Reset of a change equal to the base value removes it, as Build's Reset does);
	the base case a plain list.

	New lineup and the focus after an undo or redo are the manager's footer's: it calls addLineup,
	hasFocus and focusActive.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import type { FieldChange } from '$lib/components/ui/field-mode';
	import SegmentedField from '$lib/components/ui/SegmentedField.svelte';
	import { caseNameIn, useWorkspace } from '$lib/state/workspace.svelte';
	import {
		activeCell,
		BASE_OPTION,
		cellPress,
		LINEUP_TABLE_WORDS as WORDS,
		lineupPress,
		lineupReset,
		lineupTable,
		NEW_LINEUP_LABEL,
		newLineup,
		pickedCase,
		pickedLine,
		pickerOptions,
		refusalText,
		statusChoices,
		statusWord,
		type LineupCell,
		type LineupColumn,
		type LineupPress,
		type LineupRow,
		type WantedCell
	} from '$lib/utils/lineup-table';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import type { CaseId } from '$lib/utils/scenarios';

	let {
		onstatus,
		onalert
	}: {
		/** Say what a step did on the manager's polite status line ('' clears it). */
		onstatus: (text: string) => void;
		/** Say a refusal on the manager's alert line. */
		onalert: (text: string) => void;
	} = $props();
	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();
	const phone = mediaQuery('(max-width: 639px)');

	const table = $derived(
		lineupTable({ project: store.project, shownCase: store.activeCase, filter: ws.managerPumps })
	);
	/** The cell last wanted (the keys, a press, New lineup); the Tab stop is derived from it. */
	let wanted = $state<WantedCell | null>(null);
	const active = $derived(activeCell(table, wanted));
	const choices = statusChoices();

	/** The phone's stored pick (undefined: none); the case edited is derived from it. */
	let pick = $state<CaseId | undefined>(undefined);
	const picked = $derived(pickedCase(store.project, store.activeCase, pick));
	const pickedRow = $derived(table.rows.find((r) => r.caseId === picked) ?? table.rows[0]!);
	const options = $derived(pickerOptions(store.project));

	let grid: HTMLElement | undefined = $state();
	let box: HTMLElement | undefined = $state();
	let picker: HTMLSelectElement | undefined = $state();
	let phoneList: HTMLElement | undefined = $state();

	/** The element of the cell at (row, column): a switch, or a base case's gridcell. */
	function cellElement(row: number, column: number): HTMLElement | null {
		return grid?.querySelector<HTMLElement>(`[data-cell="${row},${column}"]`) ?? null;
	}

	/**
	 * The focus ring's room past a gridcell's edge, in px (§8.2): a switch sits 5 px inside its
	 * gridcell's top (its border and padding) and its ring reaches 6 px past it (a 2 px outline,
	 * focus-visible:outline-offset-4), 1 px past the gridcell; 8 px keeps it clear with room.
	 */
	const RING = 8;
	/**
	 * The same room at the box's bottom: the switch sits 4 px inside its gridcell's bottom (its
	 * padding), so the ring reaches 2 px past it; 3 px keeps it clear, and no more, since the box
	 * scrolled to its end (after a press on the last row) still holds six rows at 1280×800 (§8.2).
	 */
	const RING_BOTTOM = 3;

	/**
	 * The scroll box's padding: the sticky header rows' height and the case column's width, and
	 * the focus ring's reach beyond them; at the bottom the ring's reach, with as much room after
	 * the last row (the box's own padding). So the whole indicator of a focused cell stays in view,
	 * the last row's too, with the box then scrolled to its end (§8.7).
	 */
	function padSticky(node: HTMLElement) {
		const head = node.querySelector('thead');
		const corner = node.querySelector<HTMLElement>('[data-corner]');
		node.style.scrollPaddingTop = `${(head?.offsetHeight ?? 0) + RING}px`;
		node.style.scrollPaddingLeft = `${(corner?.offsetWidth ?? 0) + RING}px`;
		node.style.scrollPaddingBottom = `${RING_BOTTOM}px`;
		node.style.paddingBottom = `${RING_BOTTOM}px`;
	}

	/**
	 * Keep a focused cell clear of the sticky header rows and case column (§8.2): the scroll box's
	 * padding is their size, read again as the table changes.
	 */
	function stickyPadding(node: HTMLElement) {
		const update = () => padSticky(node);
		update();
		if (typeof ResizeObserver === 'undefined') return { update };
		const observer = new ResizeObserver(update);
		observer.observe(node);
		const table = node.querySelector('table');
		if (table) observer.observe(table);
		return {
			update,
			destroy() {
				observer.disconnect();
			}
		};
	}

	/** The focus is in the grid (an undo or redo then puts it back on the active cell, §8.9). */
	export function hasFocus(): boolean {
		return !!grid && grid.contains(document.activeElement);
	}

	/**
	 * Focus the derived active cell once the DOM has caught up (§8.7), scrolled into view: after a
	 * press, an undo or redo, a rename or a filter change, and a move of the keys. The gridcell is
	 * what is scrolled, not the switch centred in it: a cell of the last row or column then leaves
	 * the box scrolled to its end, so an arrow at that edge (not prevented, §8.7) has nothing left
	 * to scroll, and no animated scroll of the box runs on after the next key has placed its cell.
	 */
	export async function focusActive(): Promise<void> {
		await tick();
		const cell = active;
		if (!cell || !box) return;
		const element = cellElement(cell.row, cell.column);
		if (!element) return;
		padSticky(box);
		element.focus({ preventScroll: true });
		const gridcell = element.closest<HTMLElement>('[role="gridcell"]') ?? element;
		gridcell.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
	}

	/**
	 * New lineup (§8.8): an empty scenario at the end, one undo step labelled "add scenario"; the
	 * case shown unchanged. The status line says it; the focus goes to the new row's first switch
	 * (on a phone the new case is picked and the focus goes to the picker). Full: nothing.
	 */
	export async function addLineup(): Promise<void> {
		const added = newLineup(store.project);
		if (!added) return;
		const result = ws.updateStoredQuiet(added.add, NEW_LINEUP_LABEL);
		if (!result.ok) {
			onalert(result.text);
			return;
		}
		onstatus([added.status, result.renamed].filter(Boolean).join(' '));
		if (phone.current) {
			pick = added.id;
			await tick();
			picker?.focus();
			picker?.scrollIntoView?.({ block: 'nearest' });
			return;
		}
		const rowIndex = table.rows.findIndex((r) => r.caseId === added.id);
		const first = table.columns[0];
		if (rowIndex < 0 || !first) return;
		wanted = { caseId: added.id, pumpId: first.id, rowIndex };
		await focusActive();
	}

	/**
	 * Set a pump in a scenario (§8.6): Build's Status edit, one undo step "turn {pump} {on|off} in
	 * {case}", the case shown unchanged. The status line says the renames (nothing when the name
	 * stays: the switch announces its state); a refusal goes to the alert line.
	 */
	function apply(row: LineupRow, press: LineupPress): boolean {
		if (row.caseId === null) return false;
		const result = ws.editScenario(row.caseId, press.change, press.label, { quiet: true });
		if (!result.ok) {
			onalert(refusalText(press, row.name, result.message));
			return false;
		}
		onstatus(result.renamed);
		return true;
	}

	/** A press of a switch: its other value; the focus put back on it (§8.7). */
	async function pressCell(
		row: LineupRow,
		rowIndex: number,
		column: LineupColumn,
		cell: LineupCell
	) {
		if (row.caseId === null) return;
		wanted = { caseId: row.caseId, pumpId: column.id, rowIndex };
		apply(row, cellPress(column, cell));
		await focusActive();
	}

	/** The cell at (row, column) is wanted and focused (the keys). */
	function moveTo(row: number, column: number) {
		const r = table.rows[row];
		const c = table.columns[column];
		if (!r || !c) return;
		wanted = { caseId: r.caseId, pumpId: c.id, rowIndex: row };
		void focusActive();
	}

	/** A cell focused by a press of the pointer is the one wanted, so the Tab stop follows it. */
	function focusin(event: FocusEvent) {
		const at = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-cell]');
		if (!at?.dataset.cell) return;
		const [row, column] = at.dataset.cell.split(',').map(Number) as [number, number];
		const r = table.rows[row];
		const c = table.columns[column];
		if (!r || !c) return;
		if (wanted?.caseId === r.caseId && wanted.pumpId === c.id && wanted.rowIndex === row) return;
		wanted = { caseId: r.caseId, pumpId: c.id, rowIndex: row };
	}

	/**
	 * The grid's keys (§8.7): the arrows between cells with no wrap (at an edge nothing, and the key
	 * is not prevented, so the box can still scroll); Home and End along the row; Ctrl+Home and
	 * Ctrl+End to the grid's first and last. Space and Enter press a switch (its own button's).
	 */
	function keydown(event: KeyboardEvent) {
		if (event.altKey) return;
		const at = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-cell]');
		if (!at?.dataset.cell) return;
		const [row, column] = at.dataset.cell.split(',').map(Number) as [number, number];
		const lastRow = table.rows.length - 1;
		const lastColumn = table.columns.length - 1;
		const ctrl = event.ctrlKey || event.metaKey;
		let to: [number, number] | null = null;
		switch (event.key) {
			case 'ArrowRight':
				if (column < lastColumn) to = [row, column + 1];
				break;
			case 'ArrowLeft':
				if (column > 0) to = [row, column - 1];
				break;
			case 'ArrowDown':
				if (row < lastRow) to = [row + 1, column];
				break;
			case 'ArrowUp':
				if (row > 0) to = [row - 1, column];
				break;
			case 'Home':
				to = ctrl ? [0, 0] : [row, 0];
				break;
			case 'End':
				to = ctrl ? [lastRow, lastColumn] : [row, lastColumn];
				break;
			case ' ':
				// A base case's cell presses nothing; the box does not jump either.
				if (row === 0) event.preventDefault();
				return;
			default:
				return;
		}
		if (!to) return;
		event.preventDefault();
		moveTo(to[0], to[1]);
	}

	/** "Show every pump": the filter cleared, the focus on the table's active cell (§8.2). */
	async function showEvery() {
		ws.managerPumps = null;
		if (phone.current) {
			await tick();
			picker?.focus();
			return;
		}
		await focusActive();
	}

	/** The phone's segments (§8.10): Build's, their change ChangeNote's, Reset to the base value. */
	function changeOf(row: LineupRow, column: LineupColumn, cell: LineupCell): FieldChange {
		return {
			inScenario: true,
			changed: cell.marked,
			baseText: statusWord(cell.base),
			label: column.label,
			reset: () => void resetPump(row, column, cell),
			setBy: []
		};
	}

	/** A segment chosen on a phone. */
	function choose(row: LineupRow, column: LineupColumn, value: string) {
		if (value !== 'on' && value !== 'off') return;
		apply(row, lineupPress(column, value));
	}

	/**
	 * Reset removes the case's own value, as Build's Reset does: a value that differs from the base
	 * by pressing the base value through the same editScenario; one equal to it (state 'same',
	 * which pressing the base value would leave as it is) by removing the change in one step
	 * through the commit path (updateStoredQuiet). Either way the name rule applies. The focus,
	 * whose Reset is gone, goes to the pump's chosen segment.
	 */
	async function resetPump(row: LineupRow, column: LineupColumn, cell: LineupCell) {
		if (cell.state === 'same') removeOwn(row, column);
		else apply(row, lineupPress(column, cell.base));
		await tick();
		const fields = phoneList?.querySelectorAll<HTMLElement>('[data-phone-pump]') ?? [];
		const field = [...fields].find((f) => f.dataset.phonePump === column.id);
		field?.querySelector<HTMLInputElement>('input:checked')?.focus();
	}

	/** Remove the case's own status change of `column`'s pump (the phone's Reset of a 'same'). */
	function removeOwn(row: LineupRow, column: LineupColumn) {
		if (row.caseId === null) return;
		const reset = lineupReset(row.caseId, column);
		const result = ws.updateStoredQuiet(reset.change, (after) =>
			reset.label(caseNameIn(after, reset.caseId))
		);
		if (!result.ok) {
			onalert(result.text);
			return;
		}
		onstatus(result.renamed);
	}

	function pickCase(value: string) {
		pick = value === BASE_OPTION ? null : value;
	}

	const dividerClass = (column: LineupColumn) =>
		column.first && column.group > 0 ? 'border-l-2 border-l-slate-400' : '';
</script>

<!-- The intro (§8.2, §8.10): on desktop the corner mark (aria-hidden) between its two parts; the
	series sentence with a series or mixed group shown; the card's filter and Show every pump. A
	long name with no spaces in the filter sentence wraps (on a phone too, §8.10). -->
{#snippet intro(text: string, mark: boolean)}
	<p class="break-words text-slate-700">
		{text}
		{#if mark}
			<span
				aria-hidden="true"
				class="inline-block size-2.5 bg-teal-600 align-middle [clip-path:polygon(0_0,100%_0,100%_100%)]"
			></span>
			{WORDS.introMark}
		{/if}
		{#if table.series}{WORDS.series}{/if}
		{#if table.filterText}
			{table.filterText}
			<button
				type="button"
				class="btn btn-quiet -my-1 px-2 text-blue-800"
				onclick={() => void showEvery()}>{WORDS.showEvery}</button
			>
		{/if}
	</p>
{/snippet}

<div class="dense space-y-3" data-pump-lineups>
	{#if phone.current}
		{@render intro(WORDS.phoneIntro, false)}
		<div class="field">
			<label for="{id}-pick" class="label">{WORDS.caseToEdit}</label>
			<select
				bind:this={picker}
				id="{id}-pick"
				class="input pr-8"
				value={picked ?? BASE_OPTION}
				onchange={(event) => pickCase(event.currentTarget.value)}
			>
				{#each options as option (option.value)}
					<option value={option.value}>{option.text}</option>
				{/each}
			</select>
		</div>
		<div class="space-y-0.5" data-picked-line>
			{#each pickedLine(table, picked) as line, i (i)}
				<p class={['break-words', i === 0 ? 'text-slate-700' : 'text-xs text-slate-600']}>
					{line}
				</p>
			{/each}
		</div>
		<!-- A long name with no spaces wraps (a pump's label too, in its 10 rem column). -->
		<div bind:this={phoneList} class="space-y-3 [&_.label]:wrap-anywhere">
			{#each table.groups as group, g (g)}
				{@const columns = table.columns.filter((c) => c.group === g)}
				<fieldset class="min-w-0 space-y-2">
					{#if table.groupRow}<legend class="section-title mb-1">{group.header}</legend>{/if}
					{#if pickedRow.caseId === null}
						<dl class="space-y-0.5">
							{#each columns as column (column.id)}
								{@const cell = pickedRow.cells[table.columns.indexOf(column)]!}
								<div class="break-words">
									<dt class="inline">{column.label}:</dt>
									<dd class="inline font-medium">{cell.word}</dd>
								</div>
							{/each}
						</dl>
					{:else}
						{#each columns as column (column.id)}
							{@const cell = pickedRow.cells[table.columns.indexOf(column)]!}
							{@const row = pickedRow}
							<div data-phone-pump={column.id}>
								<SegmentedField
									label={column.label}
									value={cell.value}
									options={choices}
									change={changeOf(row, column, cell)}
									onchange={(value) => choose(row, column, value)}
								/>
							</div>
						{/each}
					{/if}
				</fieldset>
			{/each}
		</div>
	{:else}
		{@render intro(WORDS.intro, true)}
		<div
			bind:this={box}
			use:stickyPadding
			class="scroll-shadow-x relative max-h-[max(16rem,calc(85dvh_-_20rem))] max-w-full overflow-auto overscroll-x-contain rounded-md border border-slate-200"
			data-lineups-box
		>
			<table
				bind:this={grid}
				role="grid"
				aria-labelledby="{id}-caption"
				class="border-separate border-spacing-0 text-sm"
				onkeydown={keydown}
				onfocusin={focusin}
			>
				<caption id="{id}-caption" class="sr-only">{WORDS.caption}</caption>
				<!-- svelte-ignore a11y_no_redundant_roles -->
				<thead role="rowgroup" class="sticky top-0 z-20">
					{#if table.groupRow}
						<!-- svelte-ignore a11y_no_redundant_roles -->
						<tr role="row">
							<th
								role="columnheader"
								rowspan="2"
								data-corner
								class="sticky left-0 z-30 min-w-44 border-r border-b border-slate-300 bg-slate-50 px-2 py-1 text-left align-bottom text-xs font-medium"
								>{WORDS.caseHeader}</th
							>
							{#each table.groups as group, g (g)}
								<th
									role="columnheader"
									colspan={group.pumpIds.length}
									class={[
										'border-b border-slate-200 bg-slate-50 px-2 py-1 text-left text-xs font-medium break-words text-slate-700',
										g > 0 && 'border-l-2 border-l-slate-400'
									]}>{group.header}</th
								>
							{/each}
						</tr>
					{/if}
					<!-- svelte-ignore a11y_no_redundant_roles -->
					<tr role="row">
						{#if !table.groupRow}
							<th
								role="columnheader"
								data-corner
								class="sticky left-0 z-30 min-w-44 border-r border-b border-slate-300 bg-slate-50 px-2 py-1 text-left align-bottom text-xs font-medium"
								>{WORDS.caseHeader}</th
							>
						{/if}
						{#each table.columns as column, c (column.id)}
							<th
								role="columnheader"
								class={[
									'w-20 max-w-28 min-w-20 border-b border-slate-300 bg-slate-50 px-1 py-1 text-center align-bottom font-normal',
									dividerClass(column)
								]}
							>
								<span id="{id}-p{c}" class="block text-xs font-medium wrap-anywhere"
									>{column.label}</span
								>
								<span class="block font-mono text-[11px] text-slate-600">{column.id}</span>
							</th>
						{/each}
					</tr>
				</thead>
				<!-- svelte-ignore a11y_no_redundant_roles -->
				<tbody role="rowgroup">
					{#each table.rows as row, r (row.caseId ?? '')}
						<!-- svelte-ignore a11y_no_redundant_roles -->
						<tr role="row">
							<th
								role="rowheader"
								class={[
									'sticky left-0 z-10 max-w-64 min-w-44 border-r border-slate-300 bg-white px-2 py-1 text-left align-middle font-normal',
									r > 0 && 'border-t border-t-slate-200'
								]}
							>
								<span id="{id}-n{r}" class="font-semibold break-words">{row.name}</span>
								{#if row.id}<span class="ml-1 font-mono text-xs text-slate-600">{row.id}</span>{/if}
								{#if row.shown}<span
										class="ml-1 rounded bg-teal-700 px-1.5 py-0.5 text-xs font-semibold text-white"
										>{WORDS.shown}</span
									>{/if}
								{#each row.notes as note, i (i)}
									<span class="block text-xs text-slate-600">{note}</span>
								{/each}
							</th>
							{#each row.cells as cell, c (cell.pumpId)}
								{@const column = table.columns[c]!}
								{@const stop = active?.row === r && active.column === c}
								{#if row.caseId === null}
									<td
										role="gridcell"
										aria-readonly="true"
										tabindex={stop ? 0 : -1}
										data-cell="{r},{c}"
										class={[
											'px-1 py-1 text-center align-middle focus-visible:-outline-offset-2',
											r > 0 && 'border-t border-t-slate-200',
											dividerClass(column)
										]}
									>
										<span
											class={[
												'inline-block min-w-10 rounded px-1.5 py-0.5 text-xs font-medium',
												cell.value === 'on'
													? 'border border-slate-300 bg-white text-slate-900'
													: 'border border-slate-700 bg-slate-700 text-white'
											]}>{cell.word}</span
										>
									</td>
								{:else}
									<td
										role="gridcell"
										class={[
											'px-1 py-1 text-center align-middle',
											r > 0 && 'border-t border-t-slate-200',
											dividerClass(column)
										]}
									>
										<button
											type="button"
											role="switch"
											aria-checked={cell.value === 'on'}
											aria-labelledby="{id}-p{c} {id}-n{r}"
											aria-describedby={cell.marked ? `${id}-d${r}-${c}` : undefined}
											title={cell.description ?? undefined}
											tabindex={stop ? 0 : -1}
											data-cell="{r},{c}"
											class={[
												'relative inline-flex h-ctl w-14 items-center justify-center overflow-hidden rounded-md border text-sm font-medium focus-visible:outline-offset-4',
												cell.value === 'on'
													? 'border-slate-400 bg-white text-slate-900 hover:bg-slate-50'
													: 'border-slate-700 bg-slate-700 text-white hover:bg-slate-800',
												cell.marked && 'ring-2 ring-teal-600 ring-offset-1'
											]}
											onclick={() => void pressCell(row, r, column, cell)}
										>
											<span aria-hidden="true">{cell.word}</span>
											{#if cell.marked}
												<span
													aria-hidden="true"
													class="absolute top-0 right-0 size-2.5 bg-teal-600 [clip-path:polygon(0_0,100%_0,100%_100%)]"
												></span>
											{/if}
										</button>
										{#if cell.marked}
											<span id="{id}-d{r}-{c}" class="sr-only">{cell.description}</span>
										{/if}
									</td>
								{/if}
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
