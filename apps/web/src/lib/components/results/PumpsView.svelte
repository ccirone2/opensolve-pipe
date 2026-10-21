<!--
	Pumps: status, operating point, speed, efficiency, power and NPSH per pump, then the pump and
	system curves of each pump.
-->
<script lang="ts">
	import type { SolvedState } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { ratedCurveRange } from '$lib/utils/pump-chart';
	import { pumpTable } from '$lib/utils/results';
	import PumpChart from './PumpChart.svelte';
	import ResultsTable from './ResultsTable.svelte';

	let { solved }: { solved: SolvedState } = $props();
	const ws = useWorkspace();
	const table = $derived(pumpTable(ws.labelsProject, solved, ws.displayUnits));
	// The curve's data range comes from the project's pump curve while the results are current;
	// after an edit it may no longer be the curve that was solved, so the sampled curve's own
	// span (which the API reports over exactly that range) is used instead.
</script>

<div class="space-y-4">
	<ResultsTable
		{table}
		caption="Results per pump"
		first="Pump"
		onselect={(row) => ws.inspect(row.element)}
	/>
	<p class="text-xs text-slate-600">
		Head is the rise in the energy grade line across the pump; for a pump held at zero flow it is
		the head across it (its shutoff head when its discharge is closed off). NPSH available is
		computed from the absolute suction pressure and the fluid's vapor pressure; it is not shown when
		the fluid has no vapor pressure. An off pump has no speed.
	</p>
	{#each table.rows as row (row.key)}
		{@const result = solved.pumpResults[row.key]}
		{#if result}
			<div class="card p-3">
				<PumpChart
					{result}
					name={row.name}
					prefs={ws.displayUnits}
					ratedRange={ws.store.results.stale ? null : ratedCurveRange(ws.project, row.key)}
				/>
			</div>
		{/if}
	{/each}
</div>
