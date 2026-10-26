<!--
	Pumps: status, operating point, speed, efficiency, power and NPSH per pump, then the pump and
	system curves of the pump being viewed (one at a time, chosen when there are several). Its
	system curve is computed on demand for the exact project of this solve and cached with it
	(D10; ProjectStore.loadSystemCurve), and can be cancelled while it is computed. With scenarios,
	the chart also shows the other cases' operating points (and, on request, their system curves on
	this chart's flow grid; proposal scenario-manager.md §6.13): those of every case other than the
	one shown that the chart shows, whichever case is shown. A pump the scenario of these results
	changed says so in the table (`changed`).
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import type { SolvedState } from '$lib/api/types';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import type { FlowRange } from '$lib/state/project.svelte';
	import { MAX_CHART_CASES, ratedCurveRange, type OtherCaseInput } from '$lib/utils/pump-chart';
	import { markChanged, pumpTable, type TableSort } from '$lib/utils/results';
	import PumpChart from './PumpChart.svelte';
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
		markChanged(pumpTable(ws.labelsProject, solved, ws.displayUnits), changed)
	);
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

	/**
	 * Why a system-curve point has no head is told with the results' names and each element's
	 * kind in the project as solved (its rule), as the curve was computed for that project.
	 */
	const curveNames = $derived({ project: ws.labelsProject, solved: ws.store.solvedProject });

	// Compute the system curve of the pump being viewed, once per solve (a new solve resets the
	// cache; a failure or cancellation waits for "Try again").
	$effect(() => {
		const id = viewed?.key;
		if (!id || !response) return;
		untrack(() => ws.store.loadSystemCurve(id));
	});

	const hasScenarios = $derived(ws.scenarios.length > 0);
	/** The flow grid of the curve shown: other cases' curves are computed on it. */
	const grid = $derived<FlowRange | null>(
		system?.status === 'ready'
			? { flowMin: system.curve.flowRange.min, flowMax: system.curve.flowRange.max }
			: null
	);
	/**
	 * The other cases' system curves are asked for (`overlay`), for the other cases the chart shows:
	 * all but those the user unticked (keys: '' is the base), derived from the cases that are other
	 * now, so a case switch asks for the case that became another, never for the case shown.
	 */
	let overlay = $state(false);
	let unticked = $state<readonly string[]>([]);
	/** Counts the times the box was ticked: asking again computes the curves cancelled or failed. */
	let asked = $state(0);
	let retried = 0;
	const caseOf = (key: string) => (key === '' ? null : key);

	/** Other cases whose last solve converged with a result for this pump. */
	const others = $derived.by((): OtherCaseInput[] => {
		const pumpId = viewed?.key;
		if (!pumpId || !hasScenarios) return [];
		return ws.store.caseIds
			.filter((c) => c !== ws.store.activeCase)
			.flatMap((c) => {
				const r = ws.store.resultsFor(c);
				const pump = r.response?.solvedState.pumpResults[pumpId];
				if (!r.response || !pump || !(r.response.success && r.response.solvedState.converged)) {
					return [];
				}
				const curve = overlay && grid ? ws.store.systemCurve(r.response, pumpId, grid) : undefined;
				return [
					{
						key: c ?? '',
						name: ws.caseName(c),
						result: pump,
						stale: r.stale,
						system: curve?.status === 'ready' ? curve.curve : null
					}
				];
			});
	});

	const overlayKeys = $derived(
		others
			.filter((o) => !unticked.includes(o.key))
			.slice(0, MAX_CHART_CASES - 1)
			.map((o) => o.key)
	);
	/** The keys as one value: the requests below are made again only when the cases change. */
	const overlayList = $derived(overlayKeys.join('\u0000'));

	const overlayStates = $derived(
		viewed && overlay && grid
			? overlayKeys.map((key) => {
					const response = ws.store.resultsFor(caseOf(key)).response;
					return ws.store.systemCurve(response, viewed.key, grid);
				})
			: []
	);
	const overlayProgress = $derived(
		overlayStates.some((s) => s?.status === 'loading')
			? {
					done: overlayStates.filter((s) => s && s.status !== 'loading').length,
					total: overlayStates.length
				}
			: null
	);

	// Asked for: compute each case's curve on the grid of the curve shown, once it is known.
	$effect(() => {
		const pumpId = viewed?.key;
		const range = grid;
		if (!overlay || !pumpId || !range) return;
		const keys = overlayList ? overlayList.split('\u0000') : [];
		const ask = asked;
		untrack(() => {
			// Asking again (ticking the box again) computes the ones cancelled or failed.
			const retry = ask !== retried;
			retried = ask;
			for (const key of keys) {
				ws.store.loadSystemCurve(pumpId, { caseId: caseOf(key), range, retry });
			}
		});
	});

	function setOverlay(on: boolean, untickedKeys: readonly string[]) {
		if (on && !overlay) asked++;
		overlay = on;
		unticked = [...untickedKeys];
	}

	function cancelOverlay() {
		const pumpId = viewed?.key;
		if (!pumpId || !grid) return;
		for (const key of overlayKeys) {
			ws.store.cancelSystemCurve(pumpId, { caseId: caseOf(key), range: grid });
		}
	}
</script>

<div class="space-y-4">
	<ResultsTable
		{table}
		{sortRequest}
		caption="Results per pump"
		first="Pump"
		onselect={(row) => ws.inspect(row.element)}
	/>
	<p class="text-xs text-slate-600">
		Head is the rise in the energy grade line across the pump; for a pump held at zero flow it is
		the head across it (its shutoff head when its discharge is closed off). NPSH available is
		computed from the absolute suction pressure and the fluid's vapor pressure; it is not shown when
		the fluid has no vapor pressure. An off pump has no speed.
		{#if anyControlled}A speed-controlled pump's speed is the one it runs at: solved to hold its
			setpoint, or its minimum or maximum speed when its drive is at a limit (its trace states the
			rule that put it there).{/if}
	</p>
	{#if viewed && result}
		<div class="card space-y-3 p-3">
			{#if pumps.length > 1}
				<SelectField
					label="Pump chart"
					hint="The pump and system curves of one pump at a time; each system curve is computed when its pump is shown."
					value={viewed.key}
					options={pumps.map((row) => ({ value: row.key, label: row.name }))}
					shared
					onchange={(id) => {
						chosen = id;
						unticked = []; // the new pump's chart starts with every case ticked
					}}
				/>
			{/if}
			{#key viewed.key}
				<PumpChart
					{result}
					name={viewed.name}
					prefs={ws.displayUnits}
					{ratedRange}
					names={curveNames}
					{system}
					onretry={response
						? () => ws.store.loadSystemCurve(viewed.key, { retry: true })
						: undefined}
					oncancel={response ? () => ws.store.cancelSystemCurve(viewed.key) : undefined}
					ontrace={() => ws.inspect(viewed.element)}
					{othersControlled}
					{...hasScenarios ? { caseName: ws.caseName(ws.store.activeCase) } : {}}
					{others}
					overlayCurves={overlay}
					onoverlay={setOverlay}
					{overlayProgress}
					oncanceloverlay={cancelOverlay}
				/>
			{/key}
		</div>
	{/if}
</div>
