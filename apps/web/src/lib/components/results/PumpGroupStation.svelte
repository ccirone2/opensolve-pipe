<!--
	The Pumps together card's first section, "Station" (proposal pumps-results-layout.md §5.3, §9
	S2): the group table (from the solve, with the shares and losses from the duty) and its footer,
	the station as a whole. Presentation only: PumpGroupChart gives every value (CLAUDE.md D21).
	S2 moves the section ahead of the group chart and gives it its heading (§6.4 item 1); its order
	inside (the group curve's line at its head, the answer before the table) is S3's.
-->
<script lang="ts">
	import type { Flag } from '$lib/api/types';
	import type { GroupTable } from '$lib/utils/pump-group-chart';
	import { SEVERITY_LABELS } from '$lib/utils/results';
	import { flagSeverities, sectionMark } from '$lib/utils/section-nav';
	import FlagIcon from './FlagIcon.svelte';
	import { registerSection } from './section-nav.svelte';

	interface Props {
		/** The group table (groupTable): its columns, a row per member and the station's footer. */
		table: GroupTable;
		/** The case shown, in a project with scenarios: named in the table's caption. */
		caseName?: string;
		/** Open an element's results and trace. */
		oninspect?: (componentId: string) => void;
		/** A flag's words (names, display units). */
		flagText: (flag: Flag) => string;
		/** The shares and losses wait for the group curve: say so. */
		sharesPending?: boolean;
	}

	let { table, caseName, oninspect, flagText, sharesPending = false }: Props = $props();
	const id = $props.id();

	/** The section nav's "Station" (§5.4): its mark, the members' worst flag in this table. */
	let heading: HTMLElement | undefined = $state();
	registerSection(
		'station',
		() => heading,
		() => sectionMark(flagSeverities(table.rows.flatMap((row) => row.flags)))
	);
</script>

<!-- A plain div with its heading, not a landmark (§7); tabindex −1, the section nav's target. -->
<div class="space-y-3 border-t border-slate-200 pt-3" data-group-station>
	<h4
		bind:this={heading}
		id="{id}-heading"
		class="scroll-mt-[calc(var(--pumps-nav-h,0px)-var(--pumps-nav-pad,0px)+0.5rem)] text-sm font-semibold text-slate-900"
		tabindex="-1"
	>
		Station
	</h4>
	<!-- The group table: from the solve, with the shares and losses from the duty. Positioned,
		so the flags' screen-reader text (absolutely placed) scrolls with it, never the page. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="scroll-shadow-x relative max-w-full overflow-auto rounded-md border border-slate-200 bg-white"
		role="region"
		aria-labelledby="{id}-table-caption"
		tabindex="0"
	>
		<table class="min-w-full border-separate border-spacing-0 text-sm">
			<caption
				id="{id}-table-caption"
				class="sticky left-0 px-2 py-1 text-left text-xs font-semibold text-slate-700"
			>
				The pumps in the group{caseName ? `, ${caseName}` : ''}
			</caption>
			<thead class="bg-slate-50">
				<tr>
					<th
						scope="col"
						class="sticky left-0 z-10 border-r border-b border-slate-300 bg-slate-50 px-2 py-1 text-left font-medium"
						>Pump</th
					>
					{#each table.columns as column (column.key)}
						<th
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
						scope="col"
						class="border-b border-slate-300 px-2 py-1 text-left align-bottom font-medium">Flags</th
					>
				</tr>
			</thead>
			<tbody>
				{#each table.rows as row (row.id)}
					<tr>
						<th
							scope="row"
							class="sticky left-0 z-10 border-r border-b border-slate-200 bg-white px-1 py-0.5 text-left font-normal"
						>
							{#if oninspect}
								<button
									type="button"
									class="inline-flex min-h-11 items-center gap-1 px-1 text-left font-medium whitespace-nowrap text-blue-800 underline underline-offset-2"
									onclick={() => oninspect(row.id)}
								>
									<span aria-hidden="true" class="no-underline" style:color={row.style.color}
										>{row.style.symbol}</span
									>{row.name}
								</button>
							{:else}
								<span
									class="inline-flex min-h-11 items-center gap-1 px-1 font-medium whitespace-nowrap"
									><span aria-hidden="true" style:color={row.style.color}>{row.style.symbol}</span
									>{row.name}</span
								>
							{/if}
						</th>
						{#each table.columns as column (column.key)}
							<td
								class={[
									'border-b border-slate-200 px-2 py-1 whitespace-nowrap',
									column.numeric && 'text-right tabular-nums'
								]}>{row.cells[column.key] ?? '—'}</td
							>
						{/each}
						<td class="border-b border-slate-200 px-2 py-1">
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
		</table>
	</div>
	{#if table.footer.length}
		<!-- The table's footer: the station as a whole, with its two ports named. -->
		<dl class="space-y-0.5 text-xs text-slate-700" aria-label="The station">
			{#each table.footer as line, i (i)}
				<div>
					<dt class="inline">{line.label}:</dt>
					<dd class="inline font-medium tabular-nums">{line.value}</dd>
				</div>
			{/each}
		</dl>
	{/if}
	{#if sharesPending}
		<p class="text-xs text-slate-600">
			The share of each pump and its loss on the way come with the group curve.
		</p>
	{/if}
</div>
