<!--
	Pumps: status, operating point, speed, efficiency, power and NPSH per pump, then the pump and
	system curves of the pump being viewed (one at a time, chosen when there are several). Its
	system curve is computed on demand for the exact project of this solve and cached with it
	(D10; ProjectStore.loadSystemCurve).
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import type { SolvedState } from '$lib/api/types';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { ratedCurveRange } from '$lib/utils/pump-chart';
	import { pumpTable } from '$lib/utils/results';
	import PumpChart from './PumpChart.svelte';
	import ResultsTable from './ResultsTable.svelte';

	let { solved }: { solved: SolvedState } = $props();
	const ws = useWorkspace();
	const table = $derived(pumpTable(ws.labelsProject, solved, ws.displayUnits));
	/** Pumps with a result, in table order. */
	const pumps = $derived(table.rows.filter((row) => solved.pumpResults[row.key]));
	let chosen = $state<string | null>(null);
	const viewed = $derived(pumps.find((row) => row.key === chosen) ?? pumps[0] ?? null);
	const result = $derived(viewed ? solved.pumpResults[viewed.key] : undefined);
	/** A pump of the solve is speed-controlled (CLAUDE.md D11). */
	const anyControlled = $derived(Object.values(solved.pumpResults).some((r) => r?.control));
	/** Another pump than the one viewed is speed-controlled and on: it regulates in its system curve. */
	const othersControlled = $derived(
		Object.entries(solved.pumpResults).some(
			([id, r]) => id !== viewed?.key && r?.control && r.control.state !== 'off'
		)
	);
	/** The solve response these results come from (a curve is only shown with its own solve). */
	const response = $derived(
		ws.store.results.response?.solvedState === solved ? ws.store.results.response : null
	);
	const system = $derived(viewed ? ws.store.systemCurve(response, viewed.key) : undefined);
	// The curve's data range, from the project exactly as solved (the curve that was solved).
	const ratedRange = $derived(
		viewed && ws.store.solvedProject && response
			? ratedCurveRange(ws.store.solvedProject, viewed.key)
			: null
	);

	// Compute the system curve of the pump being viewed, once per solve (a new solve resets the
	// cache; a failure or cancellation waits for "Try again").
	$effect(() => {
		const id = viewed?.key;
		if (!id || !response) return;
		untrack(() => ws.store.loadSystemCurve(id));
	});
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
		the fluid has no vapor pressure. An off pump has no speed.{#if anyControlled}
			A speed-controlled pump's speed is the one it runs at: solved to hold its setpoint, or its
			minimum or maximum speed when the setpoint is out of its drive's range.{/if}
	</p>
	{#if viewed && result}
		<div class="card space-y-3 p-3">
			{#if pumps.length > 1}
				<SelectField
					label="Pump chart"
					hint="The pump and system curves of one pump at a time; each system curve is computed when its pump is shown."
					value={viewed.key}
					options={pumps.map((row) => ({ value: row.key, label: row.name }))}
					onchange={(id) => (chosen = id)}
				/>
			{/if}
			{#key viewed.key}
				<PumpChart
					{result}
					name={viewed.name}
					prefs={ws.displayUnits}
					{ratedRange}
					{system}
					onretry={response
						? () => ws.store.loadSystemCurve(viewed.key, { retry: true })
						: undefined}
					ontrace={() => ws.inspect(viewed.element)}
					{othersControlled}
				/>
			{/key}
		</div>
	{/if}
</div>
