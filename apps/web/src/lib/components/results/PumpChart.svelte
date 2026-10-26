<!--
	Pump chart (design §5): the pump curve at the operating speed (solid inside its data, dashed
	where extrapolated), the system curve and the operating point, with axes in display units. For
	a speed-controlled pump (CLAUDE.md D11) the operating speed is the one it was solved to run at,
	and the labels say so.
	The system curve is computed on demand for the same solve (D10): while it is computed (with
	Cancel), when it fails or was cancelled and where points have no head (no steady state, an
	undetermined head, no convergence, not computed), the chart says so; once shown, it says how it
	was computed and links to the pump's trace, which defines it. A data table under the chart lists
	the same points, and why each without a head has none, told with element names and in display
	units (with the server's sentence under Details) when `names` are given. The focus follows the control a keyboard
	user pressed from Cancel to the button that computes the curve again, and back. Chart.js is
	loaded only when a chart is shown.

	Other cases (proposal scenario-manager.md §6.13): the case shown keeps this encoding; every
	other solved case with a result for this pump is drawn in slate, each with its own hollow
	marker and a direct label: its operating point and, where the pump runs at another speed, its
	pump curve. Their system curves are computed only on request (each costs about 41 solves), one
	at a time, with Cancel. Checkboxes choose the cases shown (at most six at once); the data table
	lists the operating points by case.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import type { Plugin } from 'chart.js';
	import type { PumpResult, UnitPreferences } from '$lib/api/types';
	import type { SystemCurveState } from '$lib/state/project.svelte';
	import {
		MAX_CHART_CASES,
		otherCasesData,
		pumpChartData,
		type ChartPoint,
		type OtherCaseInput,
		type SystemCurveNames
	} from '$lib/utils/pump-chart';
	import IssueDetail from './IssueDetail.svelte';
	import { formatNumber } from '$lib/utils/units';

	interface Props {
		result: PumpResult;
		/** Pump name, for the chart's title and accessible description. */
		name: string;
		prefs: UnitPreferences;
		/** Flow range of the curve's points at rated speed (m³/s), from the solved project. */
		ratedRange?: [number, number] | null;
		/** Names (and kinds as solved) to tell why a system-curve point has no head. */
		names?: SystemCurveNames | null;
		/** The pump's system curve for the same solve (undefined: not requested). */
		system?: SystemCurveState;
		/** Compute the system curve (again, after a failure or a cancellation). */
		onretry?: () => void;
		/** Cancel the system curve while it is computed. */
		oncancel?: () => void;
		/** Open the pump's trace, which defines the system curve (H_sys) among its equations. */
		ontrace?: () => void;
		/** Another pump of the solve is speed-controlled and on: it keeps regulating in the system curve. */
		othersControlled?: boolean;
		/** The case shown, in a project with scenarios ("Winter"): the caption names it. */
		caseName?: string;
		/** Other cases with a result for this pump (their system curve when computed). */
		others?: readonly OtherCaseInput[];
		/** The other cases' system curves: requested (true) or not. */
		overlayCurves?: boolean;
		/**
		 * Request or drop the other cases' system curves, for the other cases the chart shows: all but
		 * `unticked` (their keys), whichever cases are other.
		 */
		onoverlay?: (on: boolean, unticked: readonly string[]) => void;
		/** Overlay curves being computed: how many of how many (null: none). */
		overlayProgress?: { done: number; total: number } | null;
		/** Cancel the overlay curves still being computed. */
		oncanceloverlay?: () => void;
	}

	let {
		result,
		name,
		prefs,
		ratedRange = null,
		names = null,
		system,
		onretry,
		oncancel,
		ontrace,
		othersControlled = false,
		caseName,
		others = [],
		overlayCurves = false,
		onoverlay,
		overlayProgress = null,
		oncanceloverlay
	}: Props = $props();
	const id = $props.id();

	/** Other cases the user unticked. At most MAX_CHART_CASES - 1 others are shown. */
	let unticked = $state<string[]>([]);
	const shownOthers = $derived(
		others.filter((o) => !unticked.includes(o.key)).slice(0, MAX_CHART_CASES - 1)
	);
	const shownKeys = $derived(new Set(shownOthers.map((o) => o.key)));
	const otherData = $derived(
		otherCasesData(
			shownOthers,
			prefs,
			ratedRange?.[0] != null && ratedRange?.[1] != null ? [ratedRange[0], ratedRange[1]] : null,
			result.speed,
			names
		)
	);

	/** Tick or untick another case; with its system curves asked for, they follow the cases shown. */
	function setShown(key: string, on: boolean) {
		const next = on ? unticked.filter((k) => k !== key) : [...unticked, key];
		unticked = next;
		if (overlayCurves) onoverlay?.(true, next);
	}

	// The range as numbers, so a new array with the same values does not rebuild the chart.
	const low = $derived(ratedRange?.[0] ?? null);
	const high = $derived(ratedRange?.[1] ?? null);
	const curve = $derived(system?.status === 'ready' ? system.curve : null);
	const data = $derived(
		pumpChartData(result, prefs, low !== null && high !== null ? [low, high] : null, curve, names)
	);
	const loading = $derived(system?.status === 'loading');
	let figure: HTMLElement | undefined = $state();
	let cancelButton: HTMLButtonElement | undefined = $state();
	/** The button that computes the curve again (failed, cancelled or not computed). */
	let retryButton: HTMLButtonElement | undefined = $state();
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
	/** Other cases: neutral slate (7.6:1 on white), told apart by marker and label. */
	const SLATE = '#475569';
	const GRID = '#e2e8f0';
	const TEXT = '#475569';

	const fmt = (v: number) => formatNumber(v, 4);
	/** The markers as text, for the case checkboxes and the table. */
	const MARKER_SYMBOLS: Readonly<Record<string, string>> = {
		triangle: '△',
		rect: '□',
		star: '☆',
		crossRot: '×',
		rectRounded: '▢'
	};
	const markerOf = (key: string) => otherData.find((o) => o.key === key)?.marker;
	const off = $derived(result.status === 'off');
	const controlled = $derived(!!result.control);
	/** How a speed-controlled pump's speed was set: solved for its setpoint, or a drive limit. */
	const controlNote = $derived.by(() => {
		switch (result.control?.state) {
			case 'active':
				return ' (flow control)';
			case 'max_speed':
			case 'no_flow':
				return ' (flow control, at maximum speed)';
			case 'min_speed':
				return ' (flow control, at minimum speed)';
			default:
				return '';
		}
	});
	/**
	 * "100 % speed", "87.32 % speed (flow control)", or for an off pump "its set speed (100 %)"
	 * ("its maximum speed" for a speed-controlled one).
	 */
	const speedText = $derived(
		off
			? `its ${controlled ? 'maximum' : 'set'} speed (${formatNumber(result.speed * 100, 4)} %)`
			: `${formatNumber(result.speed * 100, 4)} % speed${controlNote}`
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
		const cases = otherData.length
			? `; other cases' operating points: ${otherData
					.map((o) =>
						o.operating
							? `${o.label} ${fmt(o.operating.x)} ${data.flowUnit} at ${fmt(o.operating.y)} ${data.headUnit}`
							: `${o.label} ${o.row.state.toLowerCase()}`
					)
					.join('; ')}`
			: '';
		return `${parts.join(' and ')}${at}${extrapolated}${cases}.`;
	});

	/** "41 evenly spaced flows from 0 to 36 L/s": the flows the system curve was solved at. */
	const systemFlows = $derived(
		data.system && data.systemSpan
			? `${data.system.length} evenly spaced flows from ${fmt(data.systemSpan[0])} to ` +
					`${fmt(data.systemSpan[1])} ${data.flowUnit}`
			: null
	);

	const HELD = 'Held at zero flow';
	/** Why a system-curve point has no head, as the API's messages say (TSD §5.6). */
	const NO_HEAD_REASONS =
		'(no steady state carries the flow, its head is undetermined, its solve did not converge, ' +
		'or it was not computed)';

	// Before the DOM drops Cancel when the curve stops loading (cancelled, computed or failed): if
	// it has the focus, what replaces it takes it: the button to compute it again, else the chart.
	$effect.pre(() => {
		if (loading) return;
		const cancel = untrack(() => cancelButton);
		if (!cancel || document.activeElement !== cancel) return;
		void tick().then(() => (retryButton ?? figure)?.focus());
	});

	// And back: before the DOM drops the button that computes the curve again (Compute the system
	// curve, Try again) as the curve starts loading, if it has the focus, Cancel takes it, else the
	// chart.
	$effect.pre(() => {
		if (!loading) return;
		const retry = untrack(() => retryButton);
		if (!retry || document.activeElement !== retry) return;
		void tick().then(() => (cancelButton ?? figure)?.focus());
	});

	/** Legend markers: curves as a line (dashed where dashed), points as their marker. */
	function legendStyle(dataset: { label?: string; showLine?: boolean; pointStyle?: unknown }) {
		if (dataset.label === 'Operating point') return 'circle';
		if (dataset.label === HELD) return 'rectRot';
		return dataset.showLine === false && typeof dataset.pointStyle === 'string'
			? dataset.pointStyle
			: 'line';
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
		const cases = otherData;
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
					: []),
				...cases.flatMap((c) => [
					...(c.curve
						? [
								{
									label: c.curveLabel,
									data: c.curve,
									borderColor: SLATE,
									backgroundColor: SLATE,
									borderWidth: 1,
									pointRadius: 0,
									pointHitRadius: 4
								}
							]
						: []),
					...(c.system && c.system.some((p) => p.y !== null)
						? [
								{
									label: `System curve, ${c.label}`,
									data: c.system,
									borderColor: SLATE,
									backgroundColor: SLATE,
									borderWidth: 1.5,
									borderDash: [2, 3],
									pointRadius: 0,
									pointHitRadius: 4,
									spanGaps: false
								}
							]
						: []),
					...(c.operating || c.held
						? [
								{
									label: c.label,
									caseLabel: c.label,
									data: [(c.operating ?? c.held) as ChartPoint],
									borderColor: SLATE,
									backgroundColor: '#ffffff',
									borderWidth: 2,
									pointStyle: c.marker,
									pointRadius: 7,
									pointHoverRadius: 9,
									pointHitRadius: 12,
									showLine: false
								}
							]
						: [])
				])
			];
			// Direct labels next to the other cases' operating points.
			const caseLabels: Plugin<'line'> = {
				id: 'caseLabels',
				afterDatasetsDraw(chart) {
					const ctx = chart.ctx;
					ctx.save();
					ctx.fillStyle = SLATE;
					ctx.font = '12px system-ui, sans-serif';
					// Above and below in turn, so the labels of close points do not overlap.
					let n = 0;
					chart.data.datasets.forEach((dataset, i) => {
						const label = (dataset as { caseLabel?: string }).caseLabel;
						const point = chart.getDatasetMeta(i).data[0];
						if (!label || !point || !chart.isDatasetVisible(i)) return;
						ctx.fillText(label, point.x + 9, n++ % 2 === 0 ? point.y - 9 : point.y + 19);
					});
					ctx.restore();
				}
			};
			chart = new Chart(context, {
				type: 'line',
				plugins: [caseLabels],
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
										pointStyle: legendStyle(c.data.datasets[item.datasetIndex ?? -1] ?? {}) as
											'circle' | 'line'
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

<figure
	bind:this={figure}
	class="space-y-2"
	aria-labelledby="{id}-caption"
	aria-busy={loading}
	tabindex="-1"
>
	<figcaption id="{id}-caption" class="text-sm font-medium">
		Pump and system curves: {name}{caseName ? `, ${caseName}` : ''}
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
			This pump is off: it carries no flow. Its curve is shown at its {controlled
				? 'maximum'
				: 'set'} speed, for reference{controlled ? '; its flow control is not applied' : ''}.
		</p>
	{:else if data.held}
		<p class="text-xs text-slate-700">
			This pump is held at zero flow by its check (see its flag). The diamond marks zero flow at the
			head across the pump.
		</p>
	{/if}
	{#if system?.status === 'loading'}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p id="{id}-curve-state" class="text-xs text-slate-600">
				Computing the system curve for this solve…
			</p>
			{#if oncancel}
				<button
					bind:this={cancelButton}
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-label="Cancel the system curve"
					onclick={oncancel}
				>
					Cancel
				</button>
			{/if}
		</div>
	{:else if system?.status === 'error'}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p id="{id}-curve-state" class="text-xs text-red-800">
				The system curve could not be computed: {system.message}
			</p>
			{#if onretry}
				<button
					bind:this={retryButton}
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-describedby="{id}-curve-state"
					onclick={onretry}
				>
					Try again
				</button>
			{/if}
		</div>
	{:else if system?.status === 'cancelled' || system === undefined}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p id="{id}-curve-state" class="text-xs text-slate-600">
				{!system
					? 'The system curve has not been computed for this solve.'
					: system.by === 'user'
						? 'The system curve was not computed: you cancelled it.'
						: system.by === 'goalSeek'
							? 'The system curve was not computed: a goal seek was started.'
							: 'The system curve was not computed: a new solve was started.'}
			</p>
			{#if onretry}
				<button
					bind:this={retryButton}
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-describedby="{id}-curve-state"
					onclick={onretry}
				>
					Compute the system curve
				</button>
			{/if}
		</div>
	{:else if data.system && data.systemMissing === data.system.length}
		<p class="text-xs text-slate-700">
			No point of the system curve has a head, so it is not drawn; the data table says why for each
			{NO_HEAD_REASONS}.
		</p>
	{:else if data.systemMissing}
		<p class="text-xs text-slate-700">
			{data.systemMissing} of {data.system?.length} system-curve points have no head: the line has gaps
			there, and the data table says why for each {NO_HEAD_REASONS}.
		</p>
	{/if}
	{#if systemFlows}
		<!-- How the curve shown was computed, where it is shown (GOALS §4.2): the request
			(POST /api/v1/system-curve) returns points without a trace; the pump's trace defines it. -->
		<p class="text-xs text-slate-600">
			System curve: the network of this solve, solved again with the pump replaced by each of
			{systemFlows} ({controlled ? 'its flow control replaced by that fixed flow; ' : ''}other pumps
			running{othersControlled ? ', speed-controlled ones regulating to their setpoints' : ''},
			valves following their rules); the system head at each flow is the EGL at the discharge minus
			the EGL at the suction.
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
	{#if others.length}
		<fieldset class="space-y-1">
			<legend class="text-xs font-medium text-slate-700">Cases on the chart</legend>
			<div class="flex flex-wrap gap-x-4">
				<span class="flex min-h-11 items-center gap-2 text-sm">
					<span aria-hidden="true">●</span>{caseName ?? 'This case'} (shown)
				</span>
				{#each others as other (other.key)}
					{@const on = shownKeys.has(other.key)}
					{@const full = !on && shownOthers.length >= MAX_CHART_CASES - 1}
					{@const marker = markerOf(other.key)}
					<label class="flex min-h-11 items-center gap-2 text-sm">
						<input
							type="checkbox"
							class="size-4"
							checked={on}
							aria-disabled={full}
							aria-describedby={full ? `${id}-full` : undefined}
							onclick={(event) => {
								if (full) {
									event.preventDefault();
									return;
								}
								setShown(other.key, event.currentTarget.checked);
							}}
						/>
						{#if marker}<span aria-hidden="true" class="text-slate-600"
								>{MARKER_SYMBOLS[marker]}</span
							>{/if}
						{other.name}{other.stale ? ' (out of date)' : ''}
					</label>
				{/each}
			</div>
			{#if others.length > MAX_CHART_CASES - 1}
				<p id="{id}-full" class="hint">At most {MAX_CHART_CASES} cases at once.</p>
			{/if}
		</fieldset>
		{#if onoverlay}
			<div>
				<label class="flex min-h-11 items-center gap-2 text-sm">
					<input
						type="checkbox"
						class="size-4"
						checked={overlayCurves}
						aria-describedby="{id}-overlay-hint"
						onchange={(event) => onoverlay(event.currentTarget.checked, unticked)}
					/>
					Also show the other cases' system curves
				</label>
				<p id="{id}-overlay-hint" class="hint">
					Each is computed on request, one at a time, for that case's last solve; a curve costs
					about 41 solves of the network.
				</p>
			</div>
			{#if overlayProgress}
				<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
					<p class="text-xs text-slate-600" role="status">
						Computing system curves: {Math.min(overlayProgress.done + 1, overlayProgress.total)} of
						{overlayProgress.total}…
					</p>
					{#if oncanceloverlay}
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							aria-label="Cancel the other cases' system curves"
							onclick={oncanceloverlay}>Cancel</button
						>
					{/if}
				</div>
			{/if}
		{/if}
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
			{#if otherData.length}
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div
					class="overflow-auto rounded-md border border-slate-200 bg-white"
					role="region"
					aria-labelledby="{id}-cases-caption"
					tabindex="0"
				>
					<table class="w-full text-sm">
						<caption
							id="{id}-cases-caption"
							class="px-2 py-1 text-left text-xs font-semibold text-slate-700"
						>
							Operating points by case
						</caption>
						<thead class="bg-slate-50">
							<tr>
								<th scope="col" class="px-2 py-1 text-left font-medium">Case</th>
								<th scope="col" class="px-2 py-1 text-right font-medium">Flow ({data.flowUnit})</th>
								<th scope="col" class="px-2 py-1 text-right font-medium">Head ({data.headUnit})</th>
								<th scope="col" class="px-2 py-1 text-right font-medium">Speed</th>
								<th scope="col" class="px-2 py-1 text-left font-medium">State</th>
							</tr>
						</thead>
						<tbody>
							<tr class="border-t border-slate-100">
								<th scope="row" class="px-2 py-1 text-left font-normal"
									>{caseName ?? 'This case'} (shown)</th
								>
								<td class="px-2 py-1 text-right tabular-nums"
									>{data.operating ? fmt(data.operating.x) : data.held ? '0' : '—'}</td
								>
								<td class="px-2 py-1 text-right tabular-nums"
									>{data.operating ? fmt(data.operating.y) : data.held ? fmt(data.held.y) : '—'}</td
								>
								<td class="px-2 py-1 text-right tabular-nums"
									>{off ? '—' : `${formatNumber(result.speed * 100, 4)} %`}</td
								>
								<td class="px-2 py-1 text-xs text-slate-600"
									>{off ? 'Off' : data.held ? 'Held at zero flow' : 'Running'}</td
								>
							</tr>
							{#each otherData as other (other.key)}
								<tr class="border-t border-slate-100">
									<th scope="row" class="px-2 py-1 text-left font-normal"
										><span aria-hidden="true" class="text-slate-600"
											>{MARKER_SYMBOLS[other.marker]}</span
										>
										{other.label}</th
									>
									<td class="px-2 py-1 text-right tabular-nums">{other.row.flow}</td>
									<td class="px-2 py-1 text-right tabular-nums">{other.row.head}</td>
									<td class="px-2 py-1 text-right tabular-nums">{other.row.speed}</td>
									<td class="px-2 py-1 text-xs text-slate-600">{other.row.state}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
			{#each otherData.filter((o) => o.system) as other (other.key)}
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div
					class="max-h-72 overflow-auto rounded-md border border-slate-200 bg-white"
					role="region"
					aria-labelledby="{id}-system-{other.key || 'base'}"
					tabindex="0"
				>
					<table class="w-full text-sm">
						<caption
							id="{id}-system-{other.key || 'base'}"
							class="px-2 py-1 text-left text-xs font-semibold text-slate-700"
						>
							System curve, {other.label}
						</caption>
						<thead class="sticky top-0 bg-slate-50">
							<tr>
								<th scope="col" class="px-2 py-1 text-right font-medium">Flow ({data.flowUnit})</th>
								<th scope="col" class="px-2 py-1 text-right font-medium">Head ({data.headUnit})</th>
								<th scope="col" class="px-2 py-1 text-left font-medium">Why no head</th>
							</tr>
						</thead>
						<tbody>
							{#each other.systemRows as row, i (i)}
								<tr class="border-t border-slate-100">
									<td class="px-2 py-1 text-right tabular-nums">{row.flow}</td>
									<td class="px-2 py-1 text-right tabular-nums">{row.head}</td>
									<td class="px-2 py-1 text-xs text-slate-600"
										>{row.note}{#if row.detail}<IssueDetail detail={row.detail} />{/if}</td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/each}
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
										<th scope="col" class="px-2 py-1 text-left font-medium">Why no head</th>
									{/if}
								</tr>
							</thead>
							<tbody>
								{#each data.systemRows as row, i (i)}
									<tr class="border-t border-slate-100">
										<td class="px-2 py-1 text-right tabular-nums">{row.flow}</td>
										<td class="px-2 py-1 text-right tabular-nums">{row.head}</td>
										{#if data.systemMissing}
											<td class="px-2 py-1 text-xs text-slate-600"
												>{row.note}{#if row.detail}<IssueDetail detail={row.detail} />{/if}</td
											>
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
