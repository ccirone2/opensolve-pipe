<!--
	A results table: one row per element, its name (a button that opens the element's results and
	trace) in a first column that stays in view while the table scrolls sideways, unit labels under
	the column headings and right-aligned numbers. The table scrolls inside its own box, never the
	page: sideways, and down when it is long, with the column headings kept in view. The fixed
	first column has a divider and a shadow so cut-off values are seen to run under it, and on
	narrow screens columns snap to its edge.

	Long tables render in chunks of rows, one chunk per frame.

	A row's flag badges and its "details" toggle (a connection's pipes and fittings) sit on a line
	of their own under the row, so the row header a screen reader repeats with every cell is just
	the element's name and detail.

	Sorting and filtering (proposal ui-ux-refinement.md item 9): a column heading is a button that
	sorts by the values shown in that column, ascending, then descending, then back to the table's
	order (the sorted column carries aria-sort); rows without a value stay last. "Flagged only"
	shows the rows with flags, offered when some rows have flags and some do not. A `sortRequest`
	(the Summary's links to a sorted table) sets the sort and shows every row.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import {
		NAME_SORT_KEY,
		sortableColumn,
		sortRows,
		type Row,
		type Table,
		type TableSort
	} from '$lib/utils/results';
	import CellValue from './CellValue.svelte';
	import FlagBadge from './FlagBadge.svelte';

	interface Props {
		table: Table;
		/** Accessible name of the table (a visually hidden caption). */
		caption: string;
		/** Heading of the first column. */
		first: string;
		onselect?: (row: Row) => void;
		/** Details shown under a row when it is expanded. */
		detail?: Snippet<[Row]>;
		/** Label of the expand button (e.g. "Pipes and fittings"). */
		detailLabel?: string;
		hasDetail?: (row: Row) => boolean;
		/** A sort to apply (a new `id` applies it again), e.g. from the Summary's links. */
		sortRequest?: (TableSort & { id: number }) | null;
	}

	let {
		table,
		caption,
		first,
		onselect,
		detail,
		detailLabel = 'Details',
		hasDetail = () => true,
		sortRequest = null
	}: Props = $props();

	const id = $props.id();
	let expanded = $state<string[]>([]);

	function toggle(key: string) {
		expanded = expanded.includes(key) ? expanded.filter((k) => k !== key) : [...expanded, key];
	}

	const domId = (key: string) => `${id}-detail-${key.replace(/[^A-Za-z0-9_-]/g, '_')}`;

	/**
	 * Long tables render their rows in chunks, one per frame, so a view of hundreds of rows shows
	 * its first rows at once instead of blocking the page until every row is built.
	 */
	const CHUNK = 60;
	let limit = $state(CHUNK);
	let sort = $state<TableSort | null>(null);
	let flaggedOnly = $state(false);
	let appliedRequest = 0;
	$effect.pre(() => {
		const request = sortRequest;
		if (!request || request.id === appliedRequest) return;
		appliedRequest = request.id;
		sort = { key: request.key, direction: request.direction };
		flaggedOnly = false;
	});
	const flaggedCount = $derived(table.rows.filter((row) => row.flags.length > 0).length);
	/** Offered when it would change what is shown: some rows have flags and some do not. */
	const canFilter = $derived(flaggedCount > 0 && flaggedCount < table.rows.length);
	const shown = $derived(
		sortRows(
			canFilter && flaggedOnly ? table.rows.filter((row) => row.flags.length > 0) : table.rows,
			sort
		)
	);
	const sortable = $derived(
		new Set(
			[NAME_SORT_KEY, ...table.columns.map((c) => c.key)].filter((key) =>
				sortableColumn(table.rows, key)
			)
		)
	);

	/** Ascending, then descending, then the table's own order. */
	function toggleSort(key: string) {
		sort =
			sort?.key !== key
				? { key, direction: 'ascending' }
				: sort.direction === 'ascending'
					? { key, direction: 'descending' }
					: null;
	}

	const rows = $derived(limit >= shown.length ? shown : shown.slice(0, limit));
	$effect(() => {
		if (limit >= shown.length) return;
		const grow = () => (limit += CHUNK);
		if (typeof requestAnimationFrame === 'function') {
			const frame = requestAnimationFrame(grow);
			return () => cancelAnimationFrame(frame);
		}
		const timer = setTimeout(grow, 16);
		return () => clearTimeout(timer);
	});
	const columns = $derived(table.columns.length + 1);

	// The fixed first column: a divider and a shadow on its right edge.
	const FIXED =
		'sticky left-0 border-r border-slate-300 shadow-[6px_0_6px_-6px_rgb(15_23_42/0.35)]';
</script>

{#snippet heading(key: string, label: string, unit: string | undefined, numeric: boolean)}
	{@const active = sort?.key === key}
	{#if sortable.has(key)}
		<button
			type="button"
			class={[
				'inline-flex min-h-11 items-end gap-1 rounded px-1 font-medium hover:bg-slate-200/70',
				numeric ? 'flex-row-reverse text-right' : 'text-left'
			]}
			onclick={() => toggleSort(key)}
		>
			<span>
				<!-- The first column's heading wraps: that column keeps its fixed width on phones. -->
				<span class={['block', key !== NAME_SORT_KEY && 'whitespace-nowrap']}>{label}</span>
				{#if unit}
					<span class="block text-xs font-normal whitespace-nowrap text-slate-600">{unit}</span>
				{/if}
			</span>
			{#if active}
				<Icon
					name={sort?.direction === 'descending' ? 'down' : 'up'}
					class="mb-0.5 size-4 shrink-0 text-blue-800"
				/>
			{/if}
		</button>
	{:else}
		<span class={['block px-1', key !== NAME_SORT_KEY && 'whitespace-nowrap']}>{label}</span>
		{#if unit}
			<span class="block px-1 text-xs font-normal whitespace-nowrap text-slate-600">{unit}</span>
		{/if}
	{/if}
{/snippet}

{#if canFilter}
	<label class="mb-1 inline-flex min-h-11 items-center gap-2 text-sm text-slate-800">
		<input type="checkbox" class="size-4" bind:checked={flaggedOnly} />
		Flagged only ({flaggedCount} of {table.rows.length})
	</label>
{/if}

<!-- A size container, so the lines under a row can be exactly as wide as the visible box. -->
<div
	class="scroll-shadow-x @container max-h-[max(16rem,calc(100dvh-12rem))] max-w-full snap-x snap-proximity scroll-pl-[9.5rem] overflow-auto overscroll-x-contain rounded-lg border border-slate-200 sm:snap-none"
>
	<table class="min-w-full border-separate border-spacing-0 text-sm">
		<caption class="sr-only">{caption}</caption>
		<thead>
			<tr class="text-slate-700">
				<th
					scope="col"
					aria-sort={sort?.key === NAME_SORT_KEY ? sort.direction : undefined}
					class={[
						FIXED,
						'top-0 z-30 border-b bg-slate-50 px-1 py-1 text-left align-bottom font-medium'
					]}
				>
					{@render heading(NAME_SORT_KEY, first, undefined, false)}
				</th>
				{#each table.columns as column (column.key)}
					<th
						scope="col"
						aria-sort={sort?.key === column.key ? sort.direction : undefined}
						class={[
							'sticky top-0 z-20 border-b border-slate-300 bg-slate-50 px-1 py-1 align-bottom font-medium',
							column.numeric ? 'text-right' : 'text-left'
						]}
					>
						{@render heading(column.key, column.label, column.unit, !!column.numeric)}
					</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as row, index (row.key)}
				{@const open = expanded.includes(row.key)}
				{@const expandable = !!detail && hasDetail(row)}
				{@const annotated = row.flags.length > 0 || expandable}
				{@const divider = index > 0 && 'border-t border-slate-200'}
				<tr>
					<th
						scope="row"
						class={[
							FIXED,
							divider,
							'z-10 w-[9.5rem] max-w-[9.5rem] min-w-[9.5rem] bg-white px-1 py-0.5 text-left align-top font-normal sm:w-auto sm:max-w-[16rem] sm:min-w-[11rem]'
						]}
					>
						{#if onselect}
							<button
								type="button"
								class="flex min-h-11 w-full flex-col items-start justify-center rounded px-1 text-left hover:bg-slate-100"
								onclick={() => onselect(row)}
							>
								<span class="font-medium break-words text-blue-800 underline underline-offset-2"
									>{row.name}</span
								>
								{#if row.detail}<span class="text-xs break-words text-slate-600">{row.detail}</span
									>{/if}
							</button>
						{:else}
							<span class="block px-1 py-2">
								<span class="block font-medium break-words">{row.name}</span>
								{#if row.detail}<span class="block text-xs text-slate-600">{row.detail}</span>{/if}
							</span>
						{/if}
					</th>
					{#each table.columns as column (column.key)}
						{@const cell = row.cells[column.key] ?? '—'}
						<td
							class={[
								divider,
								'snap-start px-2 py-2 align-top',
								column.numeric && 'text-right tabular-nums',
								column.wrap
									? 'max-w-[22rem] min-w-[14rem] text-xs break-words'
									: 'whitespace-nowrap'
							]}
						>
							<!-- Plain text inline: a component per cell is slow on tables of hundreds of rows. -->
							{#if typeof cell === 'string'}{cell}{:else}<CellValue {cell} />{/if}
						</td>
					{/each}
				</tr>
				{#if annotated}
					<tr>
						<td colspan={columns} class="p-0">
							<div
								class="sticky left-0 flex w-[100cqw] flex-wrap items-center gap-1 px-2 pb-1"
								data-row-notes={row.key}
							>
								{#each row.flags as flag, i (i)}
									<FlagBadge {flag} />
								{/each}
								{#if expandable}
									<button
										type="button"
										class="inline-flex min-h-11 items-center gap-1 rounded px-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
										aria-expanded={open}
										aria-controls={open ? domId(row.key) : undefined}
										onclick={() => toggle(row.key)}
									>
										<Icon
											name="down"
											class={['size-4 transition-transform', open && 'rotate-180']}
										/>
										{detailLabel}<span class="sr-only">: {row.name}</span>
									</button>
								{/if}
							</div>
						</td>
					</tr>
				{/if}
				{#if open && detail}
					<tr class="bg-slate-50/60">
						<td colspan={columns} class="border-t border-slate-100 p-0">
							<div id={domId(row.key)} class="sticky left-0 w-[100cqw] px-2 py-2">
								{@render detail(row)}
							</div>
						</td>
					</tr>
				{/if}
			{/each}
		</tbody>
	</table>
</div>
