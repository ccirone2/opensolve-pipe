<!--
	Pump chart (design §5): the pump curve at the operating speed (solid inside its data, dashed
	where extrapolated), the system curve and the operating point, with axes in display units.
	Below the head, on the same flow axis, the panels the pump has data for (proposal
	pump-chart.md §4): efficiency, shaft power, and NPSHr against NPSHa along the system curve,
	each with its duty value and a vertical line at the duty through them all. Chips show or hide
	them (remembered in this browser), and a slider (or the pointer over the chart) reads every
	line shown at one flow. For
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
	import type { PumpResult, UnitPreferences } from '$lib/api/types';
	import type { SystemCurveState } from '$lib/state/project.svelte';
	import type { ChartImageSource } from '$lib/utils/export/chart-image';
	import { DISCLAIMER } from '$lib/components/links';
	import { STALE_CHUNK_MESSAGE } from '$lib/utils/export/load';
	import type { Chart as ChartInstance } from 'chart.js';
	import {
		chartHeightRem,
		chartNotes,
		chartReadout,
		loadHiddenPanels,
		MARKER_SYMBOLS,
		MAX_CHART_CASES,
		otherCasesData,
		CHIP_LABELS,
		PANEL_LABELS,
		pumpChartData,
		pumpLine,
		saveHiddenPanels,
		type ChipKey,
		type OtherCaseInput,
		type PanelKey,
		type SystemCurveNames
	} from '$lib/utils/pump-chart';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
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
		/**
		 * What an image of the chart names and whether one can be made of these results (proposal
		 * export.md §5.5): without it, no Download image is offered.
		 */
		image?: ChartImageSource;
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
		oncanceloverlay,
		image
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

	/**
	 * What the user hid (this browser), and what is shown: the head panel, the other panels with
	 * data, and a speed-controlled pump's speed range.
	 */
	let hidden = $state<ChipKey[]>(loadHiddenPanels());
	const shown = $derived(
		data.panels.filter((p): p is PanelKey => p === 'head' || !hidden.includes(p))
	);
	const speedShown = $derived(!!data.facts.speedRange && !hidden.includes('speed'));
	const chips = $derived([
		...data.panels.filter((p): p is Exclude<PanelKey, 'head'> => p !== 'head'),
		...(data.facts.speedRange ? (['speed'] as const) : [])
	]);
	const isShown = (key: ChipKey) => (key === 'speed' ? speedShown : shown.includes(key));
	function togglePanel(key: ChipKey) {
		hidden = hidden.includes(key) ? hidden.filter((p) => p !== key) : [...hidden, key];
		saveHiddenPanels(hidden);
	}
	const phone = mediaQuery('(max-width: 639px)');
	const heightRem = $derived(chartHeightRem(shown, phone.current));

	/** The flow the readout reads (display unit): the slider's or the pointer's, else the duty. */
	let cursor = $state<number | null>(null);
	const readAt = $derived(cursor ?? data.operating?.x ?? null);
	const readout = $derived(readAt === null ? [] : chartReadout(data, shown, readAt));
	const xMax = $derived(
		Math.max(
			0,
			...pumpLine(data).map((p) => p.x),
			...(data.system ?? []).map((p) => p.x),
			data.operating?.x ?? 0
		)
	);
	const readoutText = $derived(
		readout.map((r) => `${r.label} ${fmt(r.value)} ${r.unit}`).join(', ')
	);
	/** The chart drawn on screen (not reactive): the cursor redraws it, the pointer reads it. */
	let drawnChart: ChartInstance<'line'> | null = null;
	let cursorNow: number | null = null;
	$effect(() => {
		cursorNow = cursor;
		drawnChart?.draw();
	});
	function pointerRead(event: PointerEvent) {
		const chart = drawnChart;
		const scale = chart?.scales.x;
		if (!chart || !scale) return;
		const { left, right } = chart.chartArea;
		if (event.offsetX < left || event.offsetX > right) return;
		const flow = scale.getValueForPixel(event.offsetX);
		if (flow !== undefined) cursor = Math.min(xMax, Math.max(0, flow));
	}
	let figure: HTMLElement | undefined = $state();
	let cancelButton: HTMLButtonElement | undefined = $state();
	/** The button that computes the curve again (failed, cancelled or not computed). */
	let retryButton: HTMLButtonElement | undefined = $state();
	let canvas: HTMLCanvasElement | undefined = $state();
	let unavailable = $state(false);
	let showTable = $state(false);

	/** The chart chunk could not be loaded (a redeploy, or a dropped connection): the table is shown. */
	let loadFailed = $state(false);
	const tableShown = $derived(showTable || unavailable || loadFailed);

	const fmt = (v: number) => formatNumber(v, 4);
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
		const below = shown.filter((p) => p !== 'head').map((p) => PANEL_LABELS[p].toLowerCase());
		const panels = below.length ? `; below, on the same flow axis: ${below.join(', ')}` : '';
		const bep = data.facts.bep;
		const best = bep
			? `; best efficiency point ${fmt(bep.efficiency.y)} % at ${fmt(bep.head.x)} ${data.flowUnit}`
			: '';
		const range = data.facts.speedRange;
		const speeds =
			speedShown && range
				? `; speed range from ${fmt(range.min.speed)} % to ${fmt(range.max.speed)} % speed${
						range.iso.length ? ', with lines of constant efficiency' : ''
					}`
				: '';
		return `${parts.join(' and ')}${at}${extrapolated}${best}${panels}${speeds}${cases}.`;
	});

	/** The panels' curves as tables (the chart's long description), for the panels shown. */
	const curveTables = $derived(
		[
			shown.includes('efficiency') && data.efficiency
				? {
						key: 'efficiency',
						caption: `Efficiency curve at ${speedText}`,
						column: 'Efficiency (%)',
						rows: data.efficiency.curve
					}
				: null,
			shown.includes('power') && data.power
				? {
						key: 'power',
						caption: `Shaft power curve at ${speedText}`,
						column: `Shaft power (${data.powerUnit})`,
						rows: data.power.curve
					}
				: null,
			shown.includes('npsh') && data.npsh?.required
				? {
						key: 'npshr',
						caption: `NPSHr curve at ${speedText}`,
						column: `NPSHr (${data.headUnit})`,
						rows: data.npsh.required
					}
				: null,
			...(speedShown && data.facts.speedRange
				? (['min', 'max'] as const).map((limit) => {
						const line = data.facts.speedRange![limit];
						return {
							key: `speed-${limit}`,
							caption: `Pump curve at ${fmt(line.speed)} % speed (${limit === 'min' ? 'minimum' : 'maximum'})`,
							column: `Head (${data.headUnit})`,
							rows: line.curve
						};
					})
				: [])
		].filter((table) => table !== null)
	);
	/** The figure's sentences under the chart, which the image's footer repeats (export.md §3.4). */
	const notes = $derived(chartNotes({ data, result, system, othersControlled, shown, speedShown }));

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

	/**
	 * The chart chunk: Chart.js and the image renderer, kept once loaded, so the image never waits
	 * for it again (export.md §5.5). Not reactive: `drawn` says when it is there.
	 */
	let chartModule: typeof import('./chart-setup') | null = null;
	/** The chart shown has been drawn: an image can be made of it. */
	let drawn = $state(false);

	$effect(() => {
		const element = canvas;
		const d = data;
		const speed = speedText;
		const cases = otherData;
		const panels = shown;
		const speedRange = speedShown;
		if (!element) return;
		let cancelled = false;
		let chart: ChartInstance<'line'> | null = null;
		drawn = false;
		void import('./chart-setup').then(
			(module) => {
				if (cancelled) return;
				chartModule = module;
				const { Chart, pumpChartConfig } = module;
				const context = element.getContext('2d');
				if (!context) {
					unavailable = true;
					return;
				}
				chart = new Chart(
					context,
					pumpChartConfig(d, cases, {
						speedText: speed,
						legendLabels: Chart.defaults.plugins.legend.labels.generateLabels,
						format: fmt,
						panels,
						speedRange,
						cursor: () => cursorNow
					})
				);
				drawnChart = chart;
				drawn = true;
			},
			() => {
				// A tab opened before a redeploy asks for a chunk the new deployment no longer has, or
				// the connection dropped while it loaded (the browser then keeps the failed module).
				if (!cancelled) loadFailed = true;
			}
		);
		return () => {
			cancelled = true;
			if (drawnChart === chart) drawnChart = null;
			chart?.destroy();
		};
	});

	/** The case shown's other cases' system curves, or this pump's, are being computed. */
	const curvesLoading = $derived(loading || !!overlayProgress);
	/** Why no image can be made now ('' when it can, export.md §5.5). */
	const imageReason = $derived(
		!image
			? ''
			: image.unavailable ||
					(curvesLoading
						? 'Wait until the system curve is computed, or cancel it.'
						: !drawn
							? 'The chart is being drawn.'
							: '')
	);
	let makingImage = false;

	/**
	 * Draw the chart again at a fixed size with its caption (the pump, the case, the solve and its
	 * status, the figure's notes) and save it as a PNG (export.md §3.4), in the chart's chunk.
	 */
	async function downloadImage() {
		const module = chartModule;
		if (!image || !module || imageReason || makingImage) return;
		makingImage = true;
		const { Chart, downloadChartImage, IMAGE_REASONS_IN, pumpChartConfig } = module;
		await downloadChartImage(Chart, {
			config: pumpChartConfig(data, otherData, {
				speedText,
				legendLabels: Chart.defaults.plugins.legend.labels.generateLabels,
				format: fmt,
				forImage: true,
				panels: shown,
				speedRange: speedShown
			}),
			notes: chartNotes({
				data,
				result,
				system,
				othersControlled,
				reasonsIn: IMAGE_REASONS_IN,
				shown,
				speedShown
			}),
			others: otherData,
			markerSymbols: MARKER_SYMBOLS,
			pumpName: name,
			...(caseName ? { caseName } : {}),
			disclaimer: DISCLAIMER,
			source: image
		});
		makingImage = false;
	}
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
	{#if loadFailed}
		<p class="text-sm text-slate-700" role="alert">
			{STALE_CHUNK_MESSAGE} The table below lists its points.
		</p>
	{:else if !unavailable}
		<div
			class="relative w-full"
			style:height="{heightRem}rem"
			role="img"
			aria-label={summary}
			onpointermove={pointerRead}
			onpointerdown={pointerRead}
		>
			<canvas bind:this={canvas} aria-hidden="true"></canvas>
		</div>
		{#if chips.length}
			<div role="group" aria-label="Show" class="flex flex-wrap items-center gap-2">
				<span class="text-xs text-slate-700" aria-hidden="true">Show</span>
				{#each chips as chip (chip)}
					<button
						type="button"
						class={['btn px-3 text-sm', isShown(chip) && 'border-blue-700 bg-blue-50']}
						aria-pressed={isShown(chip)}
						onclick={() => togglePanel(chip)}>{CHIP_LABELS[chip]}</button
					>
				{/each}
			</div>
		{/if}
		{#if xMax > 0}
			<div class="space-y-1">
				<div class="flex flex-wrap items-center gap-x-3">
					<label for="{id}-read" class="text-xs font-medium text-slate-700">Read at flow</label>
					<input
						id="{id}-read"
						type="range"
						class="min-h-11 min-w-40 flex-1 accent-slate-700"
						min="0"
						max={xMax}
						step={xMax / 400}
						value={readAt ?? 0}
						aria-valuetext="{fmt(readAt ?? 0)} {data.flowUnit}{readoutText
							? `: ${readoutText}`
							: ''}"
						oninput={(event) => (cursor = Number(event.currentTarget.value))}
						onkeydown={(event) => {
							if (event.key === 'Escape' && cursor !== null) {
								event.preventDefault();
								cursor = null;
							}
						}}
					/>
					{#if data.operating && cursor !== null}
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							onclick={() => (cursor = null)}>Back to the duty</button
						>
					{/if}
				</div>
				{#if readAt !== null}
					<p class="flex flex-wrap gap-x-3 text-xs text-slate-700 tabular-nums">
						<span class="font-medium"
							>{cursor === null ? 'At the duty' : 'At'} {fmt(readAt)} {data.flowUnit}:</span
						>
						{#each readout as item, i (item.key)}
							<span class="whitespace-nowrap"
								>{#if i}<span class="sr-only">,&nbsp;</span>{/if}{item.label}
								{fmt(item.value)}
								{item.unit}</span
							>
						{:else}
							<span>no line is drawn at this flow</span>
						{/each}
					</p>
				{/if}
			</div>
		{/if}
	{:else}
		<p class="text-sm text-slate-700">
			The chart cannot be drawn in this browser. The table below lists its points.
		</p>
	{/if}
	{#if notes.pump}
		<p class="text-xs text-slate-700">{notes.pump}</p>
	{/if}
	{#if notes.curve?.kind === 'loading'}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p id="{id}-curve-state" class="text-xs text-slate-600">{notes.curve.text}</p>
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
	{:else if notes.curve?.kind === 'error' || notes.curve?.kind === 'cancelled'}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p
				id="{id}-curve-state"
				class={['text-xs', notes.curve.kind === 'error' ? 'text-red-800' : 'text-slate-600']}
			>
				{notes.curve.text}
			</p>
			{#if onretry}
				<button
					bind:this={retryButton}
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-describedby="{id}-curve-state"
					onclick={onretry}
				>
					{notes.curve.kind === 'error' ? 'Try again' : 'Compute the system curve'}
				</button>
			{/if}
		</div>
	{:else if notes.curve}
		<p class="text-xs text-slate-700">{notes.curve.text}</p>
	{/if}
	{#if notes.method}
		<!-- How the curve shown was computed, where it is shown (GOALS §4.2): the request
			(POST /api/v1/system-curve) returns points without a trace; the pump's trace defines it. -->
		<p class="text-xs text-slate-600">
			{notes.method}
			{#if ontrace}
				<button
					type="button"
					class="inline-flex min-h-11 items-center px-1 text-left text-blue-800 underline underline-offset-2"
					onclick={ontrace}>Trace of {name}</button
				>
			{/if}
		</p>
	{/if}
	{#if notes.extrapolated}
		<p class="text-xs text-slate-600">{notes.extrapolated}</p>
	{/if}
	{#each [...notes.facts, ...notes.panels] as note (note)}
		<p class="text-xs text-slate-600">{note}</p>
	{/each}
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
	{#if !unavailable && !loadFailed}
		<div class="flex flex-wrap items-center gap-x-3">
			<button
				type="button"
				class="btn btn-quiet px-2 text-blue-800"
				aria-expanded={tableShown}
				aria-controls="{id}-table"
				onclick={() => (showTable = !showTable)}
			>
				{tableShown ? 'Hide data table' : 'Show data table'}
			</button>
			{#if image}
				<!-- The chart drawn again at a fixed size, with its caption, as a PNG (export.md §5.5). -->
				<button
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					data-chart-image
					aria-label="Download image of the pump and system curves: {name}{caseName
						? `, ${caseName}`
						: ''}"
					aria-disabled={!!imageReason}
					aria-describedby={imageReason ? `${id}-image-reason` : undefined}
					title={imageReason || undefined}
					onclick={() => void downloadImage()}
				>
					<Icon name="download" class="size-4" /> Download image
				</button>
				{#if imageReason}<span id="{id}-image-reason" class="sr-only">{imageReason}</span>{/if}
			{/if}
		</div>
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
									{#if data.npsh?.available}
										<th scope="col" class="px-2 py-1 text-right font-medium"
											>NPSHa ({data.headUnit})</th
										>
									{/if}
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
										{#if data.npsh?.available}
											<td class="px-2 py-1 text-right tabular-nums">{row.npsha}</td>
										{/if}
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
				{#each curveTables as table (table.key)}
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div
						class="max-h-72 overflow-auto rounded-md border border-slate-200 bg-white"
						role="region"
						aria-labelledby="{id}-{table.key}-caption"
						tabindex="0"
					>
						<table class="w-full text-sm">
							<caption
								id="{id}-{table.key}-caption"
								class="px-2 py-1 text-left text-xs font-semibold text-slate-700"
							>
								{table.caption}
							</caption>
							<thead class="sticky top-0 bg-slate-50">
								<tr>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Flow ({data.flowUnit})</th
									>
									<th scope="col" class="px-2 py-1 text-right font-medium">{table.column}</th>
								</tr>
							</thead>
							<tbody>
								{#each table.rows as row, i (i)}
									<tr class="border-t border-slate-100">
										<td class="px-2 py-1 text-right tabular-nums">{fmt(row.x)}</td>
										<td class="px-2 py-1 text-right tabular-nums">{fmt(row.y)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</figure>
