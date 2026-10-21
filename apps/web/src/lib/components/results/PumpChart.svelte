<!--
	Pump chart (design §5): the pump curve at the operating speed (solid inside its data, dashed
	where extrapolated), the system curve and the operating point, with axes in display units.
	The system curve is computed on demand for the same solve (D10): while it is computed, when it
	fails and where points have no solution, the chart says so; once shown, it says how it was
	computed and links to the pump's trace, which defines it. A data table under the chart lists
	the same points. Chart.js is loaded only when a chart is shown.
-->
<script lang="ts">
	import type { PumpResult, UnitPreferences } from '$lib/api/types';
	import type { SystemCurveState } from '$lib/state/project.svelte';
	import { pumpChartData, type ChartPoint } from '$lib/utils/pump-chart';
	import { formatNumber } from '$lib/utils/units';

	interface Props {
		result: PumpResult;
		/** Pump name, for the chart's title and accessible description. */
		name: string;
		prefs: UnitPreferences;
		/** Flow range of the curve's points at rated speed (m³/s), from the solved project. */
		ratedRange?: [number, number] | null;
		/** The pump's system curve for the same solve (undefined: not requested). */
		system?: SystemCurveState;
		/** Compute the system curve (again, after a failure or a cancellation). */
		onretry?: () => void;
		/** Open the pump's trace, which defines the system curve (H_sys) among its equations. */
		ontrace?: () => void;
	}

	let { result, name, prefs, ratedRange = null, system, onretry, ontrace }: Props = $props();
	const id = $props.id();

	// The range as numbers, so a new array with the same values does not rebuild the chart.
	const low = $derived(ratedRange?.[0] ?? null);
	const high = $derived(ratedRange?.[1] ?? null);
	const curve = $derived(system?.status === 'ready' ? system.curve : null);
	const data = $derived(
		pumpChartData(result, prefs, low !== null && high !== null ? [low, high] : null, curve)
	);
	const loading = $derived(system?.status === 'loading');
	let canvas: HTMLCanvasElement | undefined = $state();
	let unavailable = $state(false);
	let showTable = $state(false);
	const tableShown = $derived(showTable || unavailable);

	// Categorical slots 1 and 2 of the dataviz reference palette (validated light-mode pair);
	// the operating point is drawn in the primary ink. Identity is also given by the legend,
	// the dash pattern and the point marker, and by the data table.
	const PUMP = '#2a78d6';
	const SYSTEM = '#eb6834';
	const INK = '#0f172a';
	const GRID = '#e2e8f0';
	const TEXT = '#475569';

	const fmt = (v: number) => formatNumber(v, 4);
	const off = $derived(result.status === 'off');
	/** "100 % speed", or for an off pump "its set speed (100 %)". */
	const speedText = $derived(
		off
			? `its set speed (${formatNumber(result.speed * 100, 4)} %)`
			: `${formatNumber(result.speed * 100, 4)} % speed`
	);

	const summary = $derived.by(() => {
		const parts = [
			`Pump curve of ${name} at ${speedText}${off ? ', for reference: the pump is off' : ''}`
		];
		if (data.system && data.systemMissing < data.system.length) parts.push('system curve');
		const op = data.operating;
		const held = data.held;
		const at = op
			? `; operating point ${fmt(op.x)} ${data.flowUnit} at ${fmt(op.y)} ${data.headUnit}`
			: held
				? `; held at zero flow, ${fmt(held.y)} ${data.headUnit} across the pump`
				: '';
		const extrapolated = data.extrapolated.length
			? '; dashed: extrapolated beyond the curve data'
			: '';
		return `${parts.join(' and ')}${at}${extrapolated}.`;
	});

	/** "41 evenly spaced flows from 0 to 36 L/s": the flows the system curve was solved at. */
	const systemFlows = $derived(
		data.system && data.systemSpan
			? `${data.system.length} evenly spaced flows from ${fmt(data.systemSpan[0])} to ` +
					`${fmt(data.systemSpan[1])} ${data.flowUnit}`
			: null
	);

	const HELD = 'Held at zero flow';

	/** Legend markers: curves as a line (dashed where dashed), points as their marker. */
	function legendStyle(label: string | undefined): 'circle' | 'rectRot' | 'line' {
		return label === 'Operating point' ? 'circle' : label === HELD ? 'rectRot' : 'line';
	}

	/** Dashed segments as one dataset, separated by gaps. */
	function joinSegments(segments: ChartPoint[][]): { x: number; y: number | null }[] {
		const points: { x: number; y: number | null }[] = [];
		segments.forEach((segment, i) => {
			if (i > 0 && segment[0]) points.push({ x: segment[0].x, y: null });
			points.push(...segment);
		});
		return points;
	}

	$effect(() => {
		const element = canvas;
		const d = data;
		const speed = speedText;
		if (!element) return;
		let cancelled = false;
		let chart: { destroy(): void } | null = null;
		void import('./chart-setup').then(({ Chart }) => {
			if (cancelled) return;
			const context = element.getContext('2d');
			if (!context) {
				unavailable = true;
				return;
			}
			const datasets = [
				{
					label: `Pump curve at ${speed}`,
					data: d.curve,
					borderColor: PUMP,
					backgroundColor: PUMP,
					borderWidth: 2,
					pointRadius: 0,
					pointHitRadius: 6
				},
				...(d.extrapolated.length
					? [
							{
								label: 'Pump curve, extrapolated (dashed)',
								data: joinSegments(d.extrapolated),
								borderColor: PUMP,
								backgroundColor: PUMP,
								borderWidth: 2,
								borderDash: [6, 4],
								pointRadius: 0,
								pointHitRadius: 6,
								spanGaps: false
							}
						]
					: []),
				...(d.system && d.systemMissing < d.system.length
					? [
							{
								label: 'System curve',
								data: d.system,
								borderColor: SYSTEM,
								backgroundColor: SYSTEM,
								borderWidth: 2,
								pointRadius: 0,
								pointHitRadius: 6,
								// A point without a solution is a gap, never bridged.
								spanGaps: false
							}
						]
					: []),
				...(d.operating
					? [
							{
								label: 'Operating point',
								data: [d.operating],
								borderColor: '#ffffff',
								backgroundColor: INK,
								borderWidth: 2,
								pointRadius: 6,
								pointHoverRadius: 8,
								pointHitRadius: 12,
								showLine: false
							}
						]
					: []),
				...(d.held
					? [
							{
								label: HELD,
								data: [d.held],
								borderColor: INK,
								backgroundColor: '#ffffff',
								borderWidth: 2,
								pointStyle: 'rectRot' as const,
								pointRadius: 7,
								pointHoverRadius: 9,
								pointHitRadius: 12,
								showLine: false
							}
						]
					: [])
			];
			chart = new Chart(context, {
				type: 'line',
				data: { datasets },
				options: {
					animation: false,
					responsive: true,
					maintainAspectRatio: false,
					parsing: false,
					interaction: { mode: 'nearest', intersect: false },
					scales: {
						x: {
							type: 'linear',
							beginAtZero: true,
							title: { display: true, text: `Flow (${d.flowUnit})`, color: TEXT },
							grid: { color: GRID },
							ticks: { color: TEXT }
						},
						y: {
							type: 'linear',
							beginAtZero: true,
							title: { display: true, text: `Head (${d.headUnit})`, color: TEXT },
							grid: { color: GRID },
							ticks: { color: TEXT }
						}
					},
					plugins: {
						legend: {
							position: 'bottom',
							labels: {
								color: '#1e293b',
								usePointStyle: true,
								boxHeight: 12,
								// Curves as a line (dashed where dashed), the operating point as a dot.
								generateLabels: (c) =>
									Chart.defaults.plugins.legend.labels.generateLabels(c).map((item) => ({
										...item,
										pointStyle: legendStyle(c.data.datasets[item.datasetIndex ?? -1]?.label)
									}))
							}
						},
						tooltip: {
							callbacks: {
								label: (item) => {
									const p = item.raw as { x: number; y: number | null };
									if (p.y === null) return '';
									return `${item.dataset.label}: ${fmt(p.x)} ${d.flowUnit}, ${fmt(p.y)} ${d.headUnit}`;
								}
							}
						}
					}
				}
			});
		});
		return () => {
			cancelled = true;
			chart?.destroy();
		};
	});
</script>

<figure class="space-y-2" aria-labelledby="{id}-caption" aria-busy={loading}>
	<figcaption id="{id}-caption" class="text-sm font-medium">
		Pump and system curves: {name}
	</figcaption>
	{#if !unavailable}
		<div class="relative h-64 w-full sm:h-72" role="img" aria-label={summary}>
			<canvas bind:this={canvas} aria-hidden="true"></canvas>
		</div>
	{:else}
		<p class="text-sm text-slate-700">
			The chart cannot be drawn in this browser. The table below lists its points.
		</p>
	{/if}
	{#if off}
		<p class="text-xs text-slate-700">
			This pump is off: it carries no flow. Its curve is shown at its set speed, for reference.
		</p>
	{:else if data.held}
		<p class="text-xs text-slate-700">
			This pump is held at zero flow by its check (see its flag). The diamond marks zero flow at the
			head across the pump.
		</p>
	{/if}
	{#if system?.status === 'loading'}
		<p class="text-xs text-slate-600">Computing the system curve for this solve…</p>
	{:else if system?.status === 'error'}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p class="text-xs text-red-800">The system curve could not be computed: {system.message}</p>
			{#if onretry}
				<button type="button" class="btn btn-quiet px-2 text-blue-800" onclick={onretry}>
					Try again
				</button>
			{/if}
		</div>
	{:else if system?.status === 'cancelled' || system === undefined}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p class="text-xs text-slate-600">
				{system
					? 'The system curve was not computed: a new solve was started.'
					: 'The system curve has not been computed for this solve.'}
			</p>
			{#if onretry}
				<button type="button" class="btn btn-quiet px-2 text-blue-800" onclick={onretry}>
					Compute the system curve
				</button>
			{/if}
		</div>
	{:else if data.system && data.systemMissing === data.system.length}
		<p class="text-xs text-slate-700">
			No point of the system curve has a solution, so it is not drawn; the data table says why.
		</p>
	{:else if data.systemMissing}
		<p class="text-xs text-slate-700">
			{data.systemMissing} of {data.system?.length} system-curve points have no solution: the line has
			gaps there, and the data table says why.
		</p>
	{/if}
	{#if systemFlows}
		<!-- How the curve shown was computed, where it is shown (GOALS §4.2): the request
			(POST /api/v1/system-curve) returns points without a trace; the pump's trace defines it. -->
		<p class="text-xs text-slate-600">
			System curve: the network of this solve, solved again with the pump replaced by each of
			{systemFlows} (other pumps running, valves following their rules); the system head at each flow
			is the EGL at the discharge minus the EGL at the suction.
			{#if ontrace}
				<button
					type="button"
					class="inline-flex min-h-11 items-center px-1 text-left text-blue-800 underline underline-offset-2"
					onclick={ontrace}>Trace of {name}</button
				>
			{/if}
		</p>
	{/if}
	{#if data.extrapolated.length}
		<p class="text-xs text-slate-600">
			Dashed: the pump curve extrapolated beyond its data{data.range
				? ` (${fmt(data.range[0])} to ${fmt(data.range[1])} ${data.flowUnit} at this speed)`
				: ''}, along the curve's end slope, as the solver does.
		</p>
	{/if}
	{#if !unavailable}
		<button
			type="button"
			class="btn btn-quiet px-2 text-blue-800"
			aria-expanded={tableShown}
			aria-controls="{id}-table"
			onclick={() => (showTable = !showTable)}
		>
			{tableShown ? 'Hide data table' : 'Show data table'}
		</button>
	{/if}
	{#if tableShown}
		<div id="{id}-table" class="space-y-3">
			{#if data.operating}
				<p class="text-sm">
					Operating point: <span class="tabular-nums">{fmt(data.operating.x)} {data.flowUnit}</span>
					at <span class="tabular-nums">{fmt(data.operating.y)} {data.headUnit}</span>
					{#if !data.inCurveRange}(extrapolated){/if}
				</p>
			{:else if data.held}
				<p class="text-sm">
					Held at zero flow: <span class="tabular-nums">{fmt(data.held.y)} {data.headUnit}</span>
					across the pump
				</p>
			{/if}
			<div class="grid gap-3 sm:grid-cols-2">
				<!-- A scroll box keyboard users can reach and scroll; its headings stay in view. -->
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div
					class="max-h-72 overflow-auto rounded-md border border-slate-200 bg-white"
					role="region"
					aria-labelledby="{id}-curve-caption"
					tabindex="0"
				>
					<table class="w-full text-sm">
						<caption
							id="{id}-curve-caption"
							class="px-2 py-1 text-left text-xs font-semibold text-slate-700"
						>
							Pump curve at {speedText}
						</caption>
						<thead class="sticky top-0 bg-slate-50">
							<tr>
								<th scope="col" class="px-2 py-1 text-right font-medium">Flow ({data.flowUnit})</th>
								<th scope="col" class="px-2 py-1 text-right font-medium">Head ({data.headUnit})</th>
								<th scope="col" class="px-2 py-1 text-left font-medium">Data</th>
							</tr>
						</thead>
						<tbody>
							{#each data.curveRows as row, i (i)}
								<tr class="border-t border-slate-100">
									<td class="px-2 py-1 text-right tabular-nums">{row.flow}</td>
									<td class="px-2 py-1 text-right tabular-nums">{row.head}</td>
									<td class="px-2 py-1 text-xs text-slate-600"
										>{row.extrapolated ? 'Extrapolated' : 'Curve'}</td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if data.system}
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div
						class="max-h-72 overflow-auto rounded-md border border-slate-200 bg-white"
						role="region"
						aria-labelledby="{id}-system-caption"
						tabindex="0"
					>
						<table class="w-full text-sm">
							<caption
								id="{id}-system-caption"
								class="px-2 py-1 text-left text-xs font-semibold text-slate-700"
							>
								System curve
							</caption>
							<thead class="sticky top-0 bg-slate-50">
								<tr>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Flow ({data.flowUnit})</th
									>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Head ({data.headUnit})</th
									>
									{#if data.systemMissing}
										<th scope="col" class="px-2 py-1 text-left font-medium">No solution</th>
									{/if}
								</tr>
							</thead>
							<tbody>
								{#each data.systemRows as row, i (i)}
									<tr class="border-t border-slate-100">
										<td class="px-2 py-1 text-right tabular-nums">{row.flow}</td>
										<td class="px-2 py-1 text-right tabular-nums">{row.head}</td>
										{#if data.systemMissing}
											<td class="px-2 py-1 text-xs text-slate-600">{row.note}</td>
										{/if}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</figure>
