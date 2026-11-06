<!--
	The Pumps together card's last section, "Running combinations" (CLAUDE.md D21 slice 4d, D24
	§7.10; proposal pumps-results-layout.md §5.3, §9 S2): every case's members, a row group per
	case with its lineup and station lines, invalid values marked, a list below 640 px; then the
	extremes over the current cases (on screen only), their h5 now nested under the section they
	summarise (F13). Presentation only: PumpsView computes every value. S2 gives it its heading,
	the table's caption visually hidden beside it and still its name (§5.3); the lead, the order and
	the extremes as a table are S5's.
-->
<script lang="ts">
	import type { Flag } from '$lib/api/types';
	import { andList } from '$lib/utils/pump-group-chart';
	import {
		INVALID_MARKED,
		type CombinationsTable,
		type ExtremeLine
	} from '$lib/utils/pump-group-one-off';
	import { SEVERITY_LABELS } from '$lib/utils/results';
	import Icon from '$lib/components/ui/Icon.svelte';
	import FlagIcon from './FlagIcon.svelte';

	interface Props {
		/** "Running combinations": every case's members. */
		combinations: CombinationsTable;
		/** The extremes over the current cases (screen only). */
		extremes?: { lines: ExtremeLine[]; notCounted: string[] } | null;
		/** A flag's words (names, display units). */
		flagText: (flag: Flag) => string;
	}

	let { combinations, extremes = null, flagText }: Props = $props();
	const id = $props.id();
</script>

<!-- A plain div with its heading, not a landmark (§7); tabindex −1, the section nav's target. -->
<div class="space-y-3 border-t border-slate-200 pt-3" data-group-combinations>
	<h4 id="{id}-heading" class="text-sm font-semibold text-slate-900" tabindex="-1">
		Running combinations
	</h4>
	<!-- Running combinations (slice 4d): every case's members; a list below 640 px. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="scroll-shadow-x relative max-w-full overflow-auto rounded-md border border-slate-200 bg-white"
		role="region"
		aria-labelledby="{id}-combinations-caption"
		tabindex="0"
		data-running-combinations
	>
		<!-- svelte-ignore a11y_no_redundant_roles -->
		<table role="table" class="min-w-full border-separate border-spacing-0 text-sm max-sm:block">
			<!-- Visually hidden: the h4 above says it; still the table's and the region's name. -->
			<caption id="{id}-combinations-caption" class="sr-only">Running combinations</caption>
			<!-- svelte-ignore a11y_no_redundant_roles -->
			<thead role="rowgroup" class="bg-slate-50 max-sm:sr-only">
				<!-- svelte-ignore a11y_no_redundant_roles -->
				<tr role="row">
					<th
						role="columnheader"
						scope="col"
						class="sticky left-0 z-10 border-r border-b border-slate-300 bg-slate-50 px-2 py-1 text-left font-medium"
						>Pump</th
					>
					{#each combinations.columns as column (column.key)}
						<th
							role="columnheader"
							scope="col"
							class={[
								'border-b border-slate-300 px-2 py-1 align-bottom font-medium whitespace-nowrap',
								column.numeric ? 'text-right' : 'text-left'
							]}
						>
							{column.label}
							{#if column.unit}<span class="block text-xs font-normal text-slate-600"
									>{column.unit}</span
								>{/if}
						</th>
					{/each}
					<th
						role="columnheader"
						scope="col"
						class="border-b border-slate-300 px-2 py-1 text-left align-bottom font-medium">Flags</th
					>
				</tr>
			</thead>
			{#each combinations.groups as group (group.key)}
				<!-- svelte-ignore a11y_no_redundant_roles -->
				<tbody role="rowgroup" class="max-sm:block">
					<!-- svelte-ignore a11y_no_redundant_roles -->
					<tr role="row" class="max-sm:block">
						<th
							role="rowheader"
							scope="rowgroup"
							colspan={combinations.columns.length + 2}
							class={[
								'border-b border-slate-200 px-2 py-1 text-left font-normal break-words max-sm:block',
								group.stale ? 'bg-amber-50/60' : 'bg-slate-50/60'
							]}
						>
							<span class="block font-medium">{group.heading}</span>
							{#if group.lineup}<span class="block text-xs text-slate-700">{group.lineup}</span
								>{/if}
							{#if group.detail}<span class="block text-xs text-slate-600">{group.detail}</span
								>{/if}
						</th>
					</tr>
					{#each group.rows as row (row.id)}
						<!-- svelte-ignore a11y_no_redundant_roles -->
						<tr
							role="row"
							class="max-sm:flex max-sm:flex-wrap max-sm:items-baseline max-sm:gap-x-3 max-sm:gap-y-0.5 max-sm:px-2 max-sm:pb-1.5"
						>
							<th
								role="rowheader"
								scope="row"
								class={[
									'sticky left-0 z-10 border-r border-b border-slate-200 px-2 py-1 text-left font-medium whitespace-nowrap',
									'max-sm:static max-sm:block max-sm:w-full max-sm:border-0 max-sm:px-0 max-sm:break-words max-sm:whitespace-normal',
									group.stale ? 'bg-amber-50' : 'bg-white'
								]}
								><span aria-hidden="true" style:color={row.style.color}>{row.style.symbol}</span>
								{row.name}</th
							>
							{#each combinations.columns as column (column.key)}
								{@const cell = row.cells[column.key] ?? '—'}
								{@const marked =
									row.invalid &&
									cell !== '—' &&
									(INVALID_MARKED as readonly string[]).includes(column.key)}
								<td
									role="cell"
									data-label={column.unit ? `${column.label} (${column.unit})` : column.label}
									class={[
										'border-b border-slate-200 px-2 py-1 whitespace-nowrap',
										column.numeric && 'text-right tabular-nums',
										group.stale && 'bg-amber-50/60',
										'max-sm:flex max-sm:max-w-full max-sm:min-w-0 max-sm:items-baseline max-sm:gap-1 max-sm:border-0 max-sm:bg-transparent max-sm:p-0 max-sm:text-left max-sm:whitespace-normal',
										'max-sm:before:text-xs max-sm:before:text-slate-600 max-sm:before:content-[attr(data-label)]',
										cell === '—' && 'max-sm:sr-only'
									]}
									>{#if marked}<span class="inline-flex items-center gap-1"
											><Icon name="alert" class="size-3.5 text-red-700" /><span class="sr-only"
												>physically invalid:</span
											>{cell}</span
										>{:else}{cell}{/if}</td
								>
							{/each}
							<td
								role="cell"
								data-label="Flags"
								class={[
									'border-b border-slate-200 px-2 py-1',
									group.stale && 'bg-amber-50/60',
									'max-sm:flex max-sm:items-baseline max-sm:gap-1 max-sm:border-0 max-sm:bg-transparent max-sm:p-0',
									'max-sm:before:text-xs max-sm:before:text-slate-600 max-sm:before:content-[attr(data-label)]'
								]}
							>
								<span class="flex flex-wrap gap-1">
									{#each row.flags as flag, i (i)}
										<span
											class="inline-flex items-center gap-1 rounded-full border border-slate-300 px-1.5 py-0.5 text-xs whitespace-nowrap"
											title={flagText(flag)}
											><FlagIcon severity={flag.severity} class="size-3.5" />{SEVERITY_LABELS[
												flag.severity
											]}<span class="sr-only">: {flagText(flag)}</span></span
										>
									{:else}<span class="text-xs text-slate-600">None</span>{/each}
								</span>
							</td>
						</tr>
					{/each}
				</tbody>
			{/each}
		</table>
	</div>
	{#if extremes?.lines.length}
		<!-- Extremes over the current cases: on screen only (never the image or the export). Its h5
			a section title (§5.2), now under the h4 of the section it summarises. -->
		<div class="space-y-1">
			<h5 class="section-title">Extremes over these cases (current results)</h5>
			<dl class="space-y-0.5 text-xs text-slate-700" aria-label="Extremes over these cases">
				{#each extremes.lines as line (line.key)}
					<div>
						<dt class="inline">{line.term}:</dt>
						<dd class="inline font-medium tabular-nums">
							{#if line.invalid}<Icon
									name="alert"
									class="inline size-3.5 align-text-bottom text-red-700"
								/>{/if}{line.value}
						</dd>
					</div>
				{/each}
			</dl>
			{#if extremes.notCounted.length}
				<p class="text-xs text-slate-600">
					Not counted (out of date): {andList(extremes.notCounted)}.
				</p>
			{/if}
		</div>
	{/if}
</div>
