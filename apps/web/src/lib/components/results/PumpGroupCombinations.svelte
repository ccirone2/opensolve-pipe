<!--
	The Pumps together card's last section, "Running combinations" (CLAUDE.md D21 slice 4d, D24
	§7.10; proposal pumps-results-layout.md §5.3, §9 S2): every case's members, a row group per
	case with its lineup and station lines, invalid values marked, a list below 640 px; then the
	extremes over the current cases (on screen only), their h5 now nested under the section they
	summarise (F13). Presentation only: PumpsView computes every value. S2 gives it its heading,
	the table's caption visually hidden beside it and still its name (§5.3).

	S5 (§5.3, §9 S5): the lead first, "{n} cases: {v} with current results (…)", 14 px, its mark the
	worst severity among the current cases (combinationsLead); then the extremes, before the table,
	as a table of their own (the owner's answer 1, §12): a row per pump and a column per measure,
	each value on its cell's first line, the red octagon before an invalid one, in an inline-size
	box that reads as a list below 26 rem (each line's header its cell's data-label, as ::before
	content, so a cell's text is the same at every width). Running combinations' marked cells take
	the same octagon (§6.4 item 15).

	S5's order, lines and names (§5.3, §9 S5): the cases in the table's order (PumpsView's: the case
	shown, then the chart's lineupChartPriority order, then the cases without values), which no
	untick and no "Also show …" moves; the box a size container (§5.5), so each line of a group's
	heading is sticky at the box's visible width and wraps in view; a flag line under each flagged
	pump's row in place of the Flags column, as the group table's (§15 item 92), so a phone's list
	has no "Flags None" line; the names wrap at 12 rem, trace buttons in the shown case's group
	only, since a trace opens for the case shown.

	S6b (§9 S6b; the owner's answer 3, §12): the table is a ResultsTable, so it follows the owner's
	table rules (build-density.md §14 to §18) as the group table does since S6a: Flagged only and
	Fields in its grouped form; a sort by any column (its headings, or "Sort by" on a phone) makes
	it one flat table with a Case column, and clearing the sort brings the cases back in S5's
	order. Its flag lines through ResultsTable's snippet (FlagLine), its names and their trace
	buttons (the shown case's rows only, in either form) through the name's, its marked values
	through the cell's; the heading lines are its group heading's. The lead and the extremes are
	S5's, unchanged.
-->
<script lang="ts">
	import type { Flag } from '$lib/api/types';
	import { andList } from '$lib/utils/pump-group-chart';
	import {
		combinationsLead,
		INVALID_MARKED,
		LEAD_MARK_NAMES,
		type CombinationExtremes,
		type CombinationGroup,
		type CombinationRow,
		type CombinationsTable
	} from '$lib/utils/pump-group-one-off';
	import type { Row, RowGroup, Table } from '$lib/utils/results';
	import { sectionMark } from '$lib/utils/section-nav';
	import FlagIcon from './FlagIcon.svelte';
	import FlagLine from './FlagLine.svelte';
	import ResultsTable from './ResultsTable.svelte';
	import { registerSection } from './section-nav.svelte';

	interface Props {
		/** "Running combinations": every case's members. */
		combinations: CombinationsTable;
		/** The extremes over the current cases (screen only): their lines and their table. */
		extremes?: CombinationExtremes | null;
		/** A flag's words (names, display units). */
		flagText: (flag: Flag) => string;
		/** Open an element's results and trace: from the shown case's group only (§5.3 Pump names). */
		oninspect?: (componentId: string) => void;
	}

	let { combinations, extremes = null, flagText, oninspect }: Props = $props();
	const id = $props.id();

	/**
	 * A line of a group's heading (§5.3 Group heading lines): sticky at the box's visible width
	 * (the box a size container, §5.5), so it wraps in view rather than at the table's width, an
	 * unbroken name inside it; a list's line below 640 px.
	 */
	const GROUP_LINE =
		'sticky left-0 block w-[100cqw] px-2 wrap-break-word max-sm:static max-sm:w-auto';

	/**
	 * Running combinations as a results table (§9 S6b): a row group per case, in the table's order,
	 * named by its heading (the flat form's Case); a row per member, keyed by its id within its
	 * case. Every cell the group table's rule on that case's own solve (runningCombinations).
	 */
	const resultsTable = $derived<Table>({
		columns: combinations.columns,
		groups: combinations.groups.map((g): RowGroup => ({
			key: g.key,
			label: g.heading,
			stale: g.stale
		})),
		rows: combinations.groups.flatMap((g) =>
			g.rows.map((r): Row => ({
				key: r.id,
				group: g.key,
				element: { kind: 'component', id: r.id },
				name: r.name,
				detail: '',
				cells: r.cells,
				flags: [...r.flags]
			}))
		)
	});
	/** Each case's own lines, and each member's slot and marks, by the table's keys. */
	const groups = $derived(
		new Map<string, CombinationGroup>(combinations.groups.map((g) => [g.key, g]))
	);
	const rowKey = (row: Row) => `${row.group ?? ''}\u0000${row.key}`;
	const members = $derived(
		new Map<string, CombinationRow>(
			combinations.groups.flatMap((g) => g.rows.map((r) => [`${g.key}\u0000${r.id}`, r] as const))
		)
	);

	/** The lead (§5.3, §9 S5): the cases counted, its mark the worst severity among the current. */
	const lead = $derived(combinationsLead(combinations));

	/**
	 * The section nav's "Running combinations" (§5.4): its mark over the cases with current
	 * results, the lead's (§5.3): a member invalid in one, else one with a warning flag.
	 */
	let heading: HTMLElement | undefined = $state();
	registerSection(
		'combinations',
		() => heading,
		() => {
			// The nav may read it in the flush that takes this section away, its table already gone.
			const groups = (combinations as CombinationsTable | null)?.groups ?? [];
			const counted = combinationsLead({ columns: [], groups });
			return sectionMark({ invalid: counted.invalid > 0, warning: counted.warnings > 0 });
		}
	);
</script>

<!-- A case's heading (§5.3 Group heading lines): its name with "(shown)", "(out of date)" and its
	ring, its lineup line and its station line, each sticky at the box's visible width (the box a
	size container, §5.5), so it wraps in view, an unbroken name inside it; a list's line on a
	phone. -->
{#snippet caseHeading(rowGroup: RowGroup)}
	{@const group = groups.get(rowGroup.key)}
	<span class={[GROUP_LINE, 'font-medium']}>{rowGroup.label}</span>
	{#if group?.lineup}<span class={[GROUP_LINE, 'text-xs text-slate-700']}>{group.lineup}</span>{/if}
	{#if group?.detail}<span class={[GROUP_LINE, 'text-xs text-slate-600']}>{group.detail}</span>{/if}
{/snippet}

<!-- A member's name (§5.3 Pump names): its slot symbol, not underlined, in a column of its own
	(1 rem), so every name starts at one edge whatever the symbol's width (§15 item 157), as in the
	group table; a trace button only in the shown case's rows, in either form, since a trace opens
	for the case shown (§13 Later); plain words in every other. Its own width its one line up to
	12 rem, so the column is that wide; below 640 px it takes the line's width and wraps anywhere,
	a name with no space too. -->
{#snippet memberName(row: Row)}
	{@const member = members.get(rowKey(row))}
	{#if groups.get(row.group ?? '')?.shown && oninspect}
		<button
			type="button"
			class="flex min-h-11 w-max max-w-48 items-center gap-1 px-1 text-left font-medium wrap-break-word text-blue-800 underline underline-offset-2 max-sm:w-auto max-sm:max-w-none max-sm:wrap-anywhere"
			onclick={() => oninspect(row.element.id)}
		>
			<span
				aria-hidden="true"
				class="w-4 shrink-0 text-center no-underline"
				style:color={member?.style.color}>{member?.style.symbol}</span
			><span class="min-w-0">{row.name}</span>
		</button>
	{:else}
		<span
			class="flex w-max max-w-48 items-center gap-1 px-1 py-0.5 font-medium wrap-break-word max-sm:w-auto max-sm:max-w-none max-sm:wrap-anywhere"
			><span aria-hidden="true" class="w-4 shrink-0 text-center" style:color={member?.style.color}
				>{member?.style.symbol}</span
			><span class="min-w-0">{row.name}</span></span
		>
	{/if}
{/snippet}

<!-- A flagged member's flag line (§5.3 Flags): the pills and their text, read once (FlagLine). -->
{#snippet memberFlags(row: Row)}
	<FlagLine name={row.name} flags={row.flags} {flagText} />
{/snippet}

<!-- A value, marked where the pump is physically invalid in that case (§5.2): the red octagon
	before it, then "physically invalid:" for a screen reader. On the value's baseline by its text,
	the octagon centred beside it, so a phone's line keeps one baseline (§15 item 157; EXT-2). -->
{#snippet markedCell(row: Row, key: string)}
	{@const value = row.cells[key] ?? '—'}
	{@const text = typeof value === 'string' ? value : ''}
	{#if members.get(rowKey(row))?.invalid && text !== '—' && (INVALID_MARKED as readonly string[]).includes(key)}<span
			class="inline-flex items-baseline gap-1"
			><FlagIcon severity="invalid" class="size-3.5 self-center" /><span class="sr-only"
				>physically invalid:</span
			>{text}</span
		>{:else}{text}{/if}
{/snippet}

<!-- A plain div with its heading, not a landmark (§7); tabindex −1, the section nav's target. -->
<div class="space-y-3 border-t border-slate-200 pt-3" data-group-combinations>
	<h4
		bind:this={heading}
		id="{id}-heading"
		class="scroll-mt-[calc(var(--pumps-nav-h,0px)-var(--pumps-nav-pad,0px)+0.5rem)] text-sm font-semibold text-slate-900"
		tabindex="-1"
	>
		Running combinations
	</h4>
	<!-- The lead (§5.2 Answers: 14 px, tabular figures): its mark its own element before its <p>
		(§5.2 Placement), an image named by the worst severity among the current cases. -->
	<div class="flex items-start gap-1.5">
		{#if lead.mark}<span
				role="img"
				aria-label={LEAD_MARK_NAMES[lead.mark]}
				class="mt-0.5 inline-flex shrink-0"
				data-combinations-mark><FlagIcon severity={lead.mark} class="size-4" /></span
			>{/if}
		<p class="text-sm text-slate-900 tabular-nums" data-combinations-lead>{lead.text}</p>
	</div>
	{#if extremes?.table.rows.length}
		{@const table = extremes.table}
		<!-- Extremes over the current cases: on screen only (never the image or the export). Its h5
			a section title (§5.2), under the h4 of the section it summarises, before its table
			(§6.1). A table of a row per pump and a column per measure (the owner's answer 1, §12). -->
		<!-- An inline-size container, the box's own width, so below 26 rem the table reads as a list
			(§5.5) and the box drops its frame, as the mock draws the list (§5.7: 834 px). -->
		<div class="@container space-y-1" data-combination-extremes>
			<h5 class="section-title">Extremes over these cases (current results)</h5>
			<!-- Sideways shadows, and no tabindex in S5: from 26 rem it does not overflow, a long
				unbroken name in a cell breaking inside it (§5.3; S7's measured rule then covers it). -->
			<div
				class="scroll-shadow-x relative max-w-full overflow-x-auto rounded-md border border-slate-200 bg-white @max-[26rem]:rounded-none @max-[26rem]:border-0"
				data-extremes
			>
				<!-- Explicit roles: below 26 rem CSS lays the table out as a list (§5.3). -->
				<!-- svelte-ignore a11y_no_redundant_roles -->
				<table
					role="table"
					class="min-w-full border-separate border-spacing-0 text-xs text-slate-700 @max-[26rem]:block"
				>
					<!-- The table's name, the dl's aria-label words; the visible h5 heads it. -->
					<caption class="sr-only">Extremes over these cases</caption>
					<!-- svelte-ignore a11y_no_redundant_roles -->
					<thead role="rowgroup" class="bg-slate-50 @max-[26rem]:sr-only">
						<!-- svelte-ignore a11y_no_redundant_roles -->
						<tr role="row">
							<th
								role="columnheader"
								scope="col"
								class="sticky left-0 z-10 border-r border-b border-slate-300 bg-slate-50 px-1.5 py-1 text-left align-bottom font-medium text-slate-800"
								>Pump</th
							>
							{#each table.columns as column (column.key)}
								<th
									role="columnheader"
									scope="col"
									class="border-b border-slate-300 px-1.5 py-1 text-left align-bottom font-medium text-slate-800"
									>{column.label}</th
								>
							{/each}
						</tr>
					</thead>
					<!-- svelte-ignore a11y_no_redundant_roles -->
					<tbody role="rowgroup" class="@max-[26rem]:block">
						{#each table.rows as row, index (row.id)}
							<!-- Below 26 rem a block per pump, headed by its name in semibold. -->
							<!-- svelte-ignore a11y_no_redundant_roles -->
							<tr
								role="row"
								class={[
									'@max-[26rem]:block @max-[26rem]:pt-1 @max-[26rem]:pb-1.5',
									index > 0 && '@max-[26rem]:border-t @max-[26rem]:border-slate-200'
								]}
							>
								<!-- Sticky, wrapping at 12 rem, an unbroken name inside it (§5.3). -->
								<th
									role="rowheader"
									scope="row"
									class="sticky left-0 z-10 max-w-48 border-r border-b border-slate-200 bg-white px-1.5 py-1 text-left align-top font-medium wrap-break-word text-slate-900 @max-[26rem]:static @max-[26rem]:block @max-[26rem]:max-w-none @max-[26rem]:border-0 @max-[26rem]:p-0 @max-[26rem]:font-semibold"
									>{row.name}</th
								>
								{#each row.cells as cell, i (cell.key)}
									<!-- The value on its cell's first line, medium; the rest under it (§5.3).
										A long unbroken word (a case's name) breaks inside its cell, so the
										table never runs past its box, which has no Tab stop. Below 26 rem one
										line, headed by the column's words and a space as ::before content
										(the mock's `attr(data-label) " "`), never an element: the cell's text
										is its words at every width, and its accessible name its header, a
										space, then its words, "no case gives one" too (§5.3, §7). There the
										value sits on the line's baseline by its text, the octagon centred
										beside it (§5.3: the cell's words after it on the same line). -->
									<td
										role="cell"
										data-label={table.columns[i]!.label}
										class="border-b border-slate-200 px-1.5 py-1 align-top wrap-anywhere tabular-nums @max-[26rem]:block @max-[26rem]:border-0 @max-[26rem]:p-0 @max-[26rem]:pt-0.5 @max-[26rem]:before:text-slate-600 @max-[26rem]:before:content-[attr(data-label)_'_']"
										>{#if cell.amount !== null}<span
												class="flex items-center gap-1 font-medium text-slate-900 @max-[26rem]:inline-flex @max-[26rem]:items-baseline"
												>{#if cell.invalid}<FlagIcon
														severity="invalid"
														class="inline size-3.5 self-center"
													/>{/if}{cell.amount}</span
											> <span class="text-slate-600">{cell.rest}</span>{:else}<span
												class="text-slate-600">{cell.rest}</span
											>{/if}</td
									>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{#if extremes.notCounted.length}
				<p class="text-xs text-slate-600">
					Not counted (out of date): {andList(extremes.notCounted)}.
				</p>
			{/if}
		</div>
	{/if}
	<!-- Running combinations (slice 4d), a ResultsTable since S6b (§9 S6b; the owner's answer 3,
		§12): every case's members, a row group per case in the table's order (§5.3), its heading's
		lines sticky at the box's visible width; Flagged only and Fields in that form; a sort makes
		it one flat table with a Case column, and clearing the sort brings the cases back; a list
		below 640 px. Its box a region named by the h4 and a Tab stop, its table's caption the same
		words, visually hidden (§5.3); each flagged pump's flag line (FlagLine); the names trace
		buttons in the shown case's rows only, in either form. -->
	<div data-running-combinations>
		<ResultsTable
			table={resultsTable}
			caption="Running combinations"
			first="Pump"
			labelledby="{id}-heading"
			groupColumn="Case"
			name={memberName}
			flagLine={memberFlags}
			groupHeading={caseHeading}
			cellContent={markedCell}
		/>
	</div>
</div>
