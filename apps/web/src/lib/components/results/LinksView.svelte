<!--
	Links: flow, velocity, head loss, Re, f and regime per connection (per pipe when a connection
	has several); each row expands to its pipe segments and fittings, with the K the solver used
	for each fitting, that K's source, and the flags about that pipe or fitting. A connection whose
	pipes the scenario of these results changed says so (`changed`).
-->
<script lang="ts">
	import type { LinkResult, SolvedState } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { fittingFallbackName } from '$lib/utils/labels';
	import {
		fittingTable,
		linkTable,
		markChanged,
		segmentTable,
		type Row,
		type TableSort
	} from '$lib/utils/results';
	import CellValue from './CellValue.svelte';
	import FlagBadge from './FlagBadge.svelte';
	import ResultsTable from './ResultsTable.svelte';

	interface Props {
		solved: SolvedState;
		changed?: ReadonlySet<string>;
		/** A sort for the table (the Summary's links). */
		sortRequest?: (TableSort & { id: number }) | null;
	}

	let { solved, changed = new Set(), sortRequest = null }: Props = $props();
	const ws = useWorkspace();

	const table = $derived(
		markChanged(linkTable(ws.labelsProject, solved, ws.displayUnits), changed)
	);
	const fittingName = (type: string) => ws.library.fitting(type)?.name ?? fittingFallbackName(type);

	function linkOf(row: Row): LinkResult | undefined {
		return solved.linkResults[row.element.id];
	}
</script>

<ResultsTable
	{table}
	{sortRequest}
	caption="Results per pipe connection"
	first="Connection (from → to)"
	onselect={(row) => ws.inspect(row.element)}
	detailLabel="Pipes and fittings"
	hasDetail={(row) => {
		const link = linkOf(row);
		return !!link && link.segments.length + link.fittings.length > 0;
	}}
>
	{#snippet detail(row)}
		{@const link = linkOf(row)}
		{#if link}
			{@const segments = segmentTable(row.element.id, link, ws.displayUnits, solved.flags)}
			{@const fittings = fittingTable(
				row.element.id,
				link,
				ws.displayUnits,
				fittingName,
				solved.flags
			)}
			<div class="space-y-3 text-sm">
				{#each segments.rows as segment (segment.key)}
					<section aria-label="{segment.name} of {row.name}">
						<h4 class="flex flex-wrap items-center gap-2 font-medium">
							{segment.name}
							{#each segment.flags as flag, i (i)}<FlagBadge {flag} />{/each}
						</h4>
						<dl class="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
							{#each segments.columns as column (column.key)}
								<div class="min-w-0">
									<dt class="text-xs text-slate-600">
										{column.label}{#if column.unit}&nbsp;({column.unit}){/if}
									</dt>
									<dd class="tabular-nums">
										<CellValue cell={segment.cells[column.key] ?? '—'} />
									</dd>
								</div>
							{/each}
						</dl>
					</section>
				{/each}
				{#if fittings.rows.length}
					<section aria-label="Fittings of {row.name}">
						<h4 class="font-medium">Fittings</h4>
						<ul class="mt-1 space-y-2">
							{#each fittings.rows as fitting (fitting.key)}
								<li class="rounded-md border border-slate-200 bg-white p-2">
									<p class="flex flex-wrap items-center gap-2">
										<span class="font-medium">{fitting.name}</span>
										<span class="text-xs text-slate-600">{fitting.detail}</span>
										{#each fitting.flags as flag, i (i)}<FlagBadge {flag} />{/each}
									</p>
									<dl class="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
										{#each fittings.columns.filter((c) => c.key !== 'source') as column (column.key)}
											<div class="min-w-0">
												<dt class="text-xs text-slate-600">
													{column.label}{#if column.unit}&nbsp;({column.unit}){/if}
												</dt>
												<dd class="tabular-nums">
													<CellValue cell={fitting.cells[column.key] ?? '—'} />
												</dd>
											</div>
										{/each}
									</dl>
									<p class="mt-1 text-xs break-words text-slate-700">
										<span class="font-medium">Source:</span>
										<CellValue cell={fitting.cells.source ?? '—'} />
									</p>
								</li>
							{/each}
						</ul>
					</section>
				{/if}
			</div>
		{/if}
	{/snippet}
</ResultsTable>
<p class="mt-2 text-xs text-slate-600">
	Flow is positive from the first-named end of a connection to the second. Head loss is the drop in
	the energy grade line along the connection, pipes and fittings together. Velocity, Re, f and
	regime are given per pipe when a connection has several.
</p>
