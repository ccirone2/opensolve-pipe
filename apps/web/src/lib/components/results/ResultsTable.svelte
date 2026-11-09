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

	On phones (below 640 px) the same table reads as a list, as the Summary does (owner,
	2026-10-31; proposal build-density.md §14): each row a block headed by the element's name, its
	values as label and value pairs that wrap, its flags under them; the column headings stay for
	screen readers, and a "Sort by" field and a direction button sort it by any column (the
	headings' sort buttons, out of sight there, leave the Tab order: pumps-results-layout.md §9
	S6a). The table keeps explicit ARIA roles, so CSS that unmakes its layout never unmakes its
	semantics. A value the row has none of ("—") is left out of a phone's row.

	Fields (owner, 2026-10-31; proposal build-density.md §15): a menu of the table's columns, each a
	checkbox, chooses which are shown, in the table and in the phone's list; the element's name
	always is. The choice is remembered in this browser per table (localStorage: a per-viewer
	convenience, never project data, never in the link); "Show all" forgets it.

	A table in a card that reads no workspace (proposal pumps-results-layout.md §5.3 Station, §9
	S6a: the Pumps together card's group table, and Running combinations in S6b) draws its own
	flag line (`flagLine`: each flag's pill and its text, visible and read once, in place of the
	FlagBadges, whose words are a tooltip and hidden text) and its own row header's content
	(`name`: the slot symbol, a trace button only where one fits, the name wrapping at 12 rem);
	its box may be a named region and a Tab stop (`labelledby`), as the card's boxes are, so the
	keyboard can scroll it sideways. Every other table draws as before.

	Row groups (`table.groups`; §9 S6b, the owner's answer 3: Running combinations, a group per
	case): in the table's own order each group is a row group headed by its lines (`groupHeading`,
	in one cell across the row), its rows under it; Flagged only keeps the groups with a flagged
	row, Fields hides a column in every group. A sort flattens them into one table with a column
	(`groupColumn`, "Case") naming each row's group, not sortable itself, since the groups are that
	order; clearing the sort brings the groups back. A group out of date is amber, whole in either
	form. A cell's content may be the caller's (`cellContent`: a mark before an invalid value).
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import {
		NAME_SORT_KEY,
		sortableColumn,
		sortRows,
		type Row,
		type RowGroup,
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
		/**
		 * A flagged row's flags, drawn on the line under it in place of the FlagBadges (which read
		 * the workspace): the Pumps together card's pills and their visible text (proposal
		 * pumps-results-layout.md §5.3 Station, §9 S6a). The line is then `data-label="Flags"`.
		 */
		flagLine?: Snippet<[Row]>;
		/**
		 * A row header's content in place of the name's button (or words): the card's tables, whose
		 * names carry their slot symbol and wrap at 12 rem (§5.3; ui-guide). The column then takes
		 * its width from the name, not ResultsTable's 11 to 16 rem.
		 */
		name?: Snippet<[Row]>;
		/**
		 * The id of the element naming the box: the box is then a region by that name and a Tab
		 * stop, so the keyboard can scroll it (the card's tables, §15 item 92; S7 makes that
		 * conditional on overflow).
		 */
		labelledby?: string;
		/** Where the Fields choice is remembered, when the caption changes (it names the case). */
		fieldsKey?: string;
		/**
		 * A row group's heading (`table.groups`; §9 S6b): its lines, each a block, in one cell
		 * across the row. Else its label.
		 */
		groupHeading?: Snippet<[RowGroup]>;
		/** The heading of the column a sort adds to a table of row groups, naming each row's. */
		groupColumn?: string;
		/** A cell's content, by its row and column, in place of its text (a mark before a value). */
		cellContent?: Snippet<[Row, string]>;
	}

	let {
		table,
		caption,
		first,
		onselect,
		detail,
		detailLabel = 'Details',
		hasDetail = () => true,
		sortRequest = null,
		flagLine,
		name,
		labelledby,
		fieldsKey,
		groupHeading,
		groupColumn = 'Group',
		cellContent
	}: Props = $props();

	const id = $props.id();
	let expanded = $state<string[]>([]);

	/** The columns hidden in this browser for this table (by its caption), read and written safely. */
	const storageKey = $derived(`opensolve-pipe:results-fields:${fieldsKey ?? caption}`);
	function readHidden(key: string): string[] {
		try {
			const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]');
			return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
		} catch {
			return [];
		}
	}
	let hidden = $derived(readHidden(storageKey));
	function setHidden(next: string[]) {
		hidden = next;
		try {
			if (next.length) localStorage.setItem(storageKey, JSON.stringify(next));
			else localStorage.removeItem(storageKey);
		} catch {
			// Storage refused (a private window): the choice holds for this page only.
		}
	}
	const visibleColumns = $derived(table.columns.filter((c) => !hidden.includes(c.key)));
	let fieldsOpen = $state(false);
	let fieldsButton: HTMLElement | undefined = $state();
	let fieldsPanel: HTMLElement | undefined = $state();
	// Closed by a press outside it (on a phone, on the dimmed page around the sheet).
	$effect(() => {
		if (!fieldsOpen) return;
		const outside = (event: PointerEvent) => {
			const target = event.target as Node;
			if (!fieldsPanel?.contains(target) && !fieldsButton?.contains(target)) fieldsOpen = false;
		};
		document.addEventListener('pointerdown', outside);
		return () => document.removeEventListener('pointerdown', outside);
	});

	function toggle(key: string) {
		expanded = expanded.includes(key) ? expanded.filter((k) => k !== key) : [...expanded, key];
	}

	/** A row's own key in the table: in a table of row groups, its group's and its own. */
	const rowKey = (row: Row) =>
		row.group === undefined ? row.key : JSON.stringify([row.group, row.key]);

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

	/**
	 * Below 640 px the headings are visually hidden (the list) and "Sort by" sorts: their buttons
	 * leave the Tab order there, since a focus on one would be unseen (WCAG 2.4.7) and, under the
	 * Pumps tab's pinned nav, covered (WCAG 2.4.11; proposal pumps-results-layout.md §9 S6a). They
	 * stay buttons for a screen reader, whose table navigation reads them.
	 */
	const phone = mediaQuery('(max-width: 639px)');

	/** Ascending, then descending, then the table's own order. */
	function toggleSort(key: string) {
		sort =
			sort?.key !== key
				? { key, direction: 'ascending' }
				: sort.direction === 'ascending'
					? { key, direction: 'descending' }
					: null;
	}

	/** The columns a phone's "Sort by" offers: those a heading sorts by, named with their unit. */
	const sortChoices = $derived(
		[
			{ key: NAME_SORT_KEY, label: first },
			...visibleColumns.map((c) => ({
				key: c.key,
				label: c.unit ? `${c.label} (${c.unit})` : c.label
			}))
		].filter((c) => sortable.has(c.key))
	);

	/** A field chosen sorts ascending first, as a heading does; the button then reverses it. */
	function sortBy(key: string) {
		sort = key ? { key, direction: 'ascending' } : null;
	}

	const rows = $derived(limit >= shown.length ? shown : shown.slice(0, limit));

	/**
	 * Row groups (§9 S6b): in the table's own order, a row group each, in the groups' order, its
	 * rows in the table's; a sort flattens them, with the group column. Flagged only leaves out a
	 * group with no flagged row; the rows drawn so far (`limit`) fill the groups in order.
	 */
	const groupOf = $derived(new Map((table.groups ?? []).map((g) => [g.key, g])));
	const flat = $derived(!!table.groups && !!sort);
	const blocks = $derived.by(() => {
		if (!table.groups || sort) return [];
		const filtering = canFilter && flaggedOnly;
		const drawn: { group: RowGroup; rows: Row[] }[] = [];
		let start = 0;
		for (const group of table.groups) {
			const all = shown.filter((row) => row.group === group.key);
			if (filtering && !all.length) continue;
			if (start > limit || (all.length && start >= limit)) break;
			drawn.push({ group, rows: all.slice(0, Math.max(0, limit - start)) });
			start += all.length;
		}
		return drawn;
	});
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
	const columns = $derived(visibleColumns.length + 1 + (flat ? 1 : 0));
	// A sort on a column hidden since goes back to the table's order.
	$effect.pre(() => {
		if (sort && sort.key !== NAME_SORT_KEY && hidden.includes(sort.key)) sort = null;
	});

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
			tabindex={phone.current ? -1 : undefined}
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

<!-- A row of the body, with its flag line and its details under it: in the table's one row
	group, or in its group's (§9 S6b), where every row has a divider above it (its heading's over
	the first). A row out of date is amber (`stale`); on a phone the block that holds it is, its
	group's or, flattened, the row's own (`tintRow`), so it reads as one tone. -->
{#snippet bodyRow(row: Row, index: number, divided: boolean, stale: boolean, tintRow: boolean)}
	{@const key = rowKey(row)}
	{@const open = expanded.includes(key)}
	{@const expandable = !!detail && hasDetail(row)}
	{@const annotated = row.flags.length > 0 || expandable}
	{@const divider = (divided || index > 0) && 'border-t border-slate-200'}
	<!-- svelte-ignore a11y_no_redundant_roles -->
	<tr
		role="row"
		class={[
			'max-sm:flex max-sm:flex-wrap max-sm:items-baseline max-sm:gap-x-3 max-sm:gap-y-0.5 max-sm:px-2 max-sm:pb-1.5',
			index > 0 && 'max-sm:border-t max-sm:border-slate-200',
			tintRow && 'max-sm:bg-amber-50/60'
		]}
	>
		<th
			role="rowheader"
			scope="row"
			class={[
				FIXED,
				divider,
				'z-10 px-1 py-0.5 text-left align-top font-normal sm:w-auto',
				stale ? 'bg-amber-50 max-sm:bg-transparent' : 'bg-white',
				!name && 'sm:max-w-[16rem] sm:min-w-[11rem]',
				'max-sm:static max-sm:-mx-1 max-sm:block max-sm:w-full max-sm:border-0 max-sm:shadow-none'
			]}
		>
			{#if name}
				{@render name(row)}
			{:else if onselect}
				<button
					type="button"
					class="flex min-h-11 w-full flex-col items-start justify-center rounded px-1 text-left hover:bg-slate-100"
					onclick={() => onselect(row)}
				>
					<span class="font-medium break-words text-blue-800 underline underline-offset-2"
						>{row.name}</span
					>
					{#if row.detail}<span class="text-xs break-words text-slate-600">{row.detail}</span>{/if}
				</button>
			{:else}
				<span class="block px-1 py-2">
					<span class="block font-medium break-words">{row.name}</span>
					{#if row.detail}<span class="block text-xs text-slate-600">{row.detail}</span>{/if}
				</span>
			{/if}
		</th>
		{#if flat}
			<!-- A sort flattens the groups (§9 S6b): the row's group named in a column of its own,
				after the name. Its words' own width is their one line up to 12 rem, as a name's, so
				the column is that wide rather than its longest word, and a long name wraps inside it.
				A phone's pair, "Case Base case (shown)", its header kept whole beside the words. -->
			<td
				role="cell"
				data-label={groupColumn}
				class={[
					divider,
					'px-2 py-2 align-top',
					stale && 'bg-amber-50/60 max-sm:bg-transparent',
					'max-sm:flex max-sm:max-w-full max-sm:min-w-0 max-sm:items-baseline max-sm:gap-1 max-sm:border-0 max-sm:p-0 max-sm:text-left',
					'max-sm:before:shrink-0 max-sm:before:text-xs max-sm:before:text-slate-600 max-sm:before:content-[attr(data-label)]'
				]}
				><span
					class="block w-max max-w-48 wrap-break-word max-sm:w-auto max-sm:max-w-none max-sm:min-w-0 max-sm:wrap-anywhere"
					>{groupOf.get(row.group ?? '')?.label ?? ''}</span
				></td
			>
		{/if}
		{#each visibleColumns as column (column.key)}
			{@const cell = row.cells[column.key] ?? '—'}
			<td
				role="cell"
				data-label={column.unit ? `${column.label} (${column.unit})` : column.label}
				class={[
					divider,
					'px-2 py-2 align-top',
					column.numeric && 'text-right tabular-nums',
					column.wrap ? 'max-w-[22rem] min-w-[14rem] text-xs break-words' : 'whitespace-nowrap',
					stale && 'bg-amber-50/60 max-sm:bg-transparent',
					// A phone: "Flow (L/s) 18.98", its label from the column (not in its text).
					'max-sm:flex max-sm:max-w-full max-sm:min-w-0 max-sm:items-baseline max-sm:gap-1 max-sm:border-0 max-sm:p-0 max-sm:text-left max-sm:whitespace-normal',
					'max-sm:before:text-xs max-sm:before:text-slate-600 max-sm:before:content-[attr(data-label)]',
					// A phone's row leaves out what it has no value for: out of sight only, so the
					// row keeps its cells, in order, for screen readers.
					cell === '—' && 'max-sm:sr-only'
				]}
			>
				<!-- Plain text inline: a component per cell is slow on tables of hundreds of rows. -->
				{#if cellContent}{@render cellContent(
						row,
						column.key
					)}{:else if typeof cell === 'string'}{cell}{:else}<CellValue {cell} />{/if}
			</td>
		{/each}
	</tr>
	{#if annotated}
		<!-- svelte-ignore a11y_no_redundant_roles -->
		<tr role="row" class={['max-sm:block', tintRow && 'max-sm:bg-amber-50/60']}>
			<td
				role="cell"
				colspan={columns}
				class={['p-0 max-sm:block', stale && 'bg-amber-50/60 max-sm:bg-transparent']}
			>
				<!-- With `flagLine`, the card's flag line (§5.3 Station): its own block of flags
					at the box's visible width, labelled Flags, after the row's values on a
					phone; else the badges in a wrapping row. -->
				<div
					class={flagLine
						? 'sticky left-0 w-[100cqw] px-2 pt-1 pb-1.5 max-sm:static max-sm:w-auto'
						: 'sticky left-0 flex w-[100cqw] flex-wrap items-center gap-1 px-2 pb-1 max-sm:static max-sm:w-auto'}
					data-row-notes={row.key}
					data-label={flagLine ? 'Flags' : undefined}
				>
					{#if flagLine}
						{#if row.flags.length}{@render flagLine(row)}{/if}
					{:else}
						{#each row.flags as flag, i (i)}
							<FlagBadge {flag} />
						{/each}
					{/if}
					{#if expandable}
						<button
							type="button"
							class="inline-flex min-h-11 items-center gap-1 rounded px-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
							aria-expanded={open}
							aria-controls={open ? domId(key) : undefined}
							onclick={() => toggle(key)}
						>
							<Icon name="down" class={['size-4 transition-transform', open && 'rotate-180']} />
							{detailLabel}<span class="sr-only">: {row.name}</span>
						</button>
					{/if}
				</div>
			</td>
		</tr>
	{/if}
	{#if open && detail}
		<!-- svelte-ignore a11y_no_redundant_roles -->
		<tr role="row" class="bg-slate-50/60 max-sm:block">
			<td role="cell" colspan={columns} class="border-t border-slate-100 p-0 max-sm:block">
				<div id={domId(key)} class="sticky left-0 w-[100cqw] px-2 py-2 max-sm:static max-sm:w-auto">
					{@render detail(row)}
				</div>
			</td>
		</tr>
	{/if}
{/snippet}

<!-- One line on a phone: Sort (it takes what is left), its direction and Fields; Flagged only, when
	offered, goes on the next (owner, 2026-10-31; proposal build-density.md §18). -->
<div class="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1">
	{#if sortChoices.length > 1}
		<!-- Phones: the headings are not shown, so a field sorts the list (the same sort). -->
		<div class="flex min-w-0 grow basis-0 items-center gap-1 sm:hidden">
			<label for="{id}-sort" class="text-sm whitespace-nowrap text-slate-700">Sort</label>
			<!-- Named "Sort by" (its visible label, Sort, is part of the name: WCAG 2.5.3). -->
			<select
				id="{id}-sort"
				aria-label="Sort by"
				class="input w-full min-w-0 py-0 pr-8 text-sm"
				value={sort?.key ?? ''}
				onchange={(event) => sortBy(event.currentTarget.value)}
			>
				<option value="">Table order</option>
				{#each sortChoices as choice (choice.key)}
					<option value={choice.key}>{choice.label}</option>
				{/each}
			</select>
			{#if sort}
				{@const descending = sort.direction === 'descending'}
				<button
					type="button"
					class="btn btn-icon shrink-0"
					aria-label={descending ? 'Descending: highest first' : 'Ascending: lowest first'}
					title={descending ? 'Highest first' : 'Lowest first'}
					onclick={() => {
						if (sort) sort = { key: sort.key, direction: descending ? 'ascending' : 'descending' };
					}}
				>
					<Icon name={descending ? 'down' : 'up'} class="size-5" />
				</button>
			{/if}
		</div>
	{/if}
	{#if table.columns.length > 1}
		<div class="relative shrink-0">
			<button
				bind:this={fieldsButton}
				type="button"
				class="btn btn-quiet gap-1 px-2 text-sm"
				aria-expanded={fieldsOpen}
				aria-controls="{id}-fields"
				onclick={() => (fieldsOpen = !fieldsOpen)}
				onkeydown={(event) => {
					if (event.key === 'Escape') fieldsOpen = false;
				}}
			>
				<Icon name="list" class="size-4" />
				<!-- Below 360 px its icon and count carry it, so Sort keeps its room. -->
				<span class="max-[22.5rem]:sr-only">Fields</span><span class="text-slate-600"
					>{hidden.length ? ` (${visibleColumns.length} of ${table.columns.length})` : ''}</span
				>
			</button>
			<!-- A phone: a sheet across the screen's width from its foot, over a dimmed page, as the
				native Sort by picker opens (owner, 2026-10-31; proposal build-density.md §16); a
				press on the dimmed page closes it. From 640 px: a menu under the button. -->
			{#if fieldsOpen}
				<div class="fixed inset-0 z-40 bg-slate-900/40 sm:hidden" aria-hidden="true"></div>
			{/if}
			<!-- Escape inside the menu closes it (as from its button). -->
			<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
			<div
				bind:this={fieldsPanel}
				id="{id}-fields"
				hidden={!fieldsOpen}
				role="group"
				aria-label="Fields shown in {caption}"
				class={[
					'z-50 overflow-y-auto border border-slate-200 bg-white shadow-lg',
					'absolute left-0 mt-1 max-h-80 w-64 rounded-lg p-2',
					'max-sm:fixed max-sm:inset-x-0 max-sm:top-auto max-sm:bottom-0 max-sm:mt-0 max-sm:max-h-[75dvh] max-sm:w-full max-sm:rounded-t-xl max-sm:rounded-b-none max-sm:px-3 max-sm:pt-2 max-sm:pb-[max(0.75rem,env(safe-area-inset-bottom))] max-sm:shadow-2xl'
				]}
				onkeydown={(event) => {
					if (event.key === 'Escape') {
						event.stopPropagation();
						fieldsOpen = false;
					}
				}}
			>
				<div
					class="sticky -top-2 -mx-3 mb-1 flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-1 sm:hidden"
				>
					<span class="min-w-0 flex-1 text-base font-semibold">Fields shown</span>
					<button type="button" class="btn btn-primary" onclick={() => (fieldsOpen = false)}
						>Done</button
					>
				</div>
				{#each table.columns as column (column.key)}
					<label
						class="flex min-h-9 items-center gap-2 px-1 text-sm text-slate-800 max-sm:min-h-11 max-sm:border-b max-sm:border-slate-100 max-sm:text-base"
					>
						<input
							type="checkbox"
							class="size-4 max-sm:size-5"
							checked={!hidden.includes(column.key)}
							onchange={(event) =>
								setHidden(
									event.currentTarget.checked
										? hidden.filter((k) => k !== column.key)
										: [...hidden, column.key]
								)}
						/>
						<span
							>{column.label}{#if column.unit}<span class="text-slate-600"
									>&nbsp;({column.unit})</span
								>{/if}</span
						>
					</label>
				{/each}
				{#if hidden.length}
					<button
						type="button"
						class="btn btn-quiet mt-1 w-full text-sm text-blue-800"
						onclick={() => setHidden([])}>Show all</button
					>
				{/if}
			</div>
		</div>
	{/if}
	{#if canFilter}
		<label class="inline-flex min-h-11 items-center gap-2 text-sm text-slate-800 max-sm:basis-full">
			<input type="checkbox" class="size-4" bind:checked={flaggedOnly} />
			Flagged only ({flaggedCount} of {table.rows.length})
		</label>
	{/if}
</div>

<!-- A size container, so the lines under a row can be exactly as wide as the visible box. Named by
	`labelledby`, a region and a Tab stop, positioned so the flag lines' hidden words (absolutely
	placed) scroll with it (§15 item 92). -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class={[
		'scroll-shadow-x @container max-h-[max(16rem,calc(100dvh-12rem))] max-w-full overflow-auto overscroll-x-contain rounded-lg border border-slate-200 max-sm:max-h-none max-sm:overflow-visible',
		labelledby && 'relative'
	]}
	role={labelledby ? 'region' : undefined}
	aria-labelledby={labelledby}
	tabindex={labelledby ? 0 : undefined}
>
	<!-- Explicit roles: below 640 px CSS lays the table out as a list (see the header comment). -->
	<!-- svelte-ignore a11y_no_redundant_roles -->
	<table role="table" class="min-w-full border-separate border-spacing-0 text-sm max-sm:block">
		<caption class="sr-only">{caption}</caption>
		<!-- svelte-ignore a11y_no_redundant_roles -->
		<thead role="rowgroup" class="max-sm:sr-only">
			<!-- svelte-ignore a11y_no_redundant_roles -->
			<tr role="row" class="text-slate-700">
				<th
					role="columnheader"
					scope="col"
					aria-sort={sort?.key === NAME_SORT_KEY ? sort.direction : undefined}
					class={[
						FIXED,
						'top-0 z-30 border-b bg-slate-50 px-1 py-1 text-left align-bottom font-medium'
					]}
				>
					{@render heading(NAME_SORT_KEY, first, undefined, false)}
				</th>
				{#if flat}
					<!-- The group column a sort adds (§9 S6b): not a sort of its own, since the groups,
						brought back by clearing the sort, are its order. -->
					<th
						role="columnheader"
						scope="col"
						class="sticky top-0 z-20 border-b border-slate-300 bg-slate-50 px-1 py-1 text-left align-bottom font-medium"
					>
						<span class="block px-1">{groupColumn}</span>
					</th>
				{/if}
				{#each visibleColumns as column (column.key)}
					<th
						role="columnheader"
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
		{#if table.groups && !sort}
			<!-- Row groups in the table's own order (§9 S6b): a row group each, headed by its lines in
				one cell across the row, a rule above it but the first's; no fill, so the box's
				sideways shadow runs down its edge unbroken (§15 item 157), but a group out of date,
				amber whole (§5.3 Invalid and stale), on a phone its block. -->
			{#each blocks as block, g (block.group.key)}
				<!-- svelte-ignore a11y_no_redundant_roles -->
				<tbody
					role="rowgroup"
					class={['max-sm:block', block.group.stale && 'max-sm:bg-amber-50/60']}
				>
					<!-- svelte-ignore a11y_no_redundant_roles -->
					<tr role="row" class="max-sm:block">
						<th
							role="rowheader"
							scope="rowgroup"
							colspan={columns}
							class={[
								'px-0 pt-2 pb-1 text-left align-top font-normal max-sm:block',
								g > 0 && 'border-t border-slate-300',
								block.group.stale && 'bg-amber-50/60 max-sm:bg-transparent'
							]}
						>
							{#if groupHeading}{@render groupHeading(block.group)}{:else}<span
									class="sticky left-0 block w-[100cqw] px-2 font-medium wrap-break-word max-sm:static max-sm:w-auto"
									>{block.group.label}</span
								>{/if}
						</th>
					</tr>
					{#each block.rows as row, index (row.key)}
						{@render bodyRow(row, index, true, !!block.group.stale, false)}
					{/each}
				</tbody>
			{/each}
		{:else}
			<!-- svelte-ignore a11y_no_redundant_roles -->
			<tbody role="rowgroup" class="max-sm:block">
				{#each rows as row, index (rowKey(row))}
					{@const stale = !!groupOf.get(row.group ?? '')?.stale}
					{@render bodyRow(row, index, false, stale, stale)}
				{/each}
			</tbody>
		{/if}
	</table>
</div>
