<!--
	The Pumps together card's "Group chart" section (CLAUDE.md D21; proposal pump-groups.md §6, §7;
	pumps-results-layout.md §5.1, §5.3, §9 S2, S3), in the pump chart's anatomy: the figure, its
	caption the image's title; the canvas (the head panel only: each member's curve and point, the
	group curve, the group system curve, the other cases' rings and curves), `aria-busy` while any
	of its curves loads; "Read along the curves" and its readout as pairs; the strip (the group
	system curve's live line with its button, then the lines about the curves' coverage, plain);
	the actions (Show data table, Download image, a lasting reason shown); the legend, its marker
	entries two-up where they fit; the notes about the values, the duty checks first (✓ when they
	agree); the reference, three disclosures ("How to read this chart" with the axes, the group
	system curve and each pump's own system curve, then how each curve is computed); and, after
	it, the data region (§5.1: so a table never pushes a note away from its chart). The group
	curve's line and the refusal head Station (PumpGroupStation) since S3. Then the other cases'
	controls (PumpGroupOthers), their progress and their notes, at the figure's end, where S3's
	second half gives them their heading. Presentation only: PumpGroupChart gives every value and
	PumpsView makes every request.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import type {
		Project,
		PumpGroupCurveResponse,
		TopologyIssue,
		UnitPreferences
	} from '$lib/api/types';
	import type { ChartImageSource } from '$lib/utils/export/chart-image';
	import type { CurveLabelsDrawn } from '$lib/utils/pump-chart-config';
	import { DISCLAIMER } from '$lib/components/links';
	import { STALE_CHUNK_MESSAGE } from '$lib/utils/export/load';
	import type { Chart as ChartInstance } from 'chart.js';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import { chartHeightRem } from '$lib/utils/pump-chart';
	import {
		ARRANGEMENT_WORDS,
		curveAnchor,
		groupCaption,
		groupImageTitle,
		groupLegend,
		groupMethodsHeading,
		groupNoteLines,
		groupReadout,
		groupSampleRows,
		groupSummary,
		groupSystemRows,
		GROUP_OTHER,
		dutyCheckState,
		dutyCheckWords,
		HELD_SYMBOL,
		OTHER_CURVE_COLUMN,
		OTHER_CURVES_CAPTION,
		OTHER_SYMBOL,
		otherCurveRows,
		placeCurveLabels,
		STATION_SYMBOL,
		systemDutyCheckState,
		type GroupChartData,
		type GroupMemberInput,
		type GroupNotes,
		type GroupReadoutMark,
		type GroupTable
	} from '$lib/utils/pump-group-chart';
	import { wordsText, type Words } from '$lib/utils/pump-groups';
	import type { OtherGroupCase } from '$lib/utils/pump-group-one-off';
	import { formatNumber } from '$lib/utils/units';
	import { sectionMark } from '$lib/utils/section-nav';
	import Icon from '$lib/components/ui/Icon.svelte';
	import IssueDetail from './IssueDetail.svelte';
	import PumpGroupOthers from './PumpGroupOthers.svelte';
	import { registerSection, useSectionNav } from './section-nav.svelte';

	/** Why the pumps are not a station, for one issue: the issue, and its words with names. */
	interface Refusal {
		issue: TopologyIssue;
		words: Words;
	}

	interface Props {
		/** The figure (bindable): the focus falls back to it. */
		figure?: HTMLElement;
		/** The data table is shown (bindable: the card keeps it while the section is redrawn). */
		showTable?: boolean;
		/**
		 * The sample the user moved "Read along the curves" to, for a response (bindable, as
		 * `showTable`); compared by identity, so the card keeps it raw.
		 */
		reading?: { response: unknown; index: number } | null;
		/**
		 * A drawing of the chart on screen placed its curve labels: how many it left out for space
		 * (D24 §9.3), which the card's notes count.
		 */
		onlabels?: (leftOut: number) => void;
		/** The members, each with its slot. */
		members: readonly GroupMemberInput[];
		/** What is drawn (groupChartData). */
		data: GroupChartData;
		/** The group curve's response shown (null: none). */
		shown: PumpGroupCurveResponse | null;
		/** The group system curve's response shown (null: none). */
		systemShown: PumpGroupCurveResponse | null;
		/** The station and its duty: the group curve's response, else the group system curve's. */
		stationShown: PumpGroupCurveResponse | null;
		/** The notes under the chart (groupNotes), and the same for a count of labels left out. */
		notes: GroupNotes;
		notesWith: (leftOut: number) => GroupNotes;
		/** Why the pumps are not a station, or their group curve not defined: the image's reasons. */
		refusals: readonly Refusal[];
		/** The members' names, in the station's order once known; and its arrangement. */
		memberNames: readonly string[];
		arrangement: string | null;
		/** The group table: its rows give "Each pump's point". */
		table: GroupTable;
		/** Names (the labels project, with those as solved of elements deleted since). */
		project: Project;
		/** The project as solved: each element's kind, for the rule a reason names. */
		solved: Project;
		prefs: UnitPreferences;
		/** A pump's name by its id. */
		nameOf: (pumpId: string) => string;
		/** The case shown, in a project with scenarios. */
		caseName?: string;
		/** The results are out of date. */
		stale?: boolean;
		/** What an image names and whether one can be made (as the pump chart's). */
		image?: ChartImageSource;
		/** The group curve, the group system curve and the other cases' duties being computed. */
		loading: boolean;
		systemLoading: boolean;
		othersLoading: boolean;
		/** Some case on the chart was cancelled by the user or failed: "Compute them again". */
		othersRetry: boolean;
		onretrysystem?: () => void;
		oncancelsystem?: () => void;
		/** The other cases with values, each in its state, while the card shows a station. */
		others: readonly OtherGroupCase[];
		othersOn: boolean;
		/** Tick or untick "Also show …" (absent: the project has no scenarios, no box). */
		onothers?: (on: boolean) => void;
		onotherstick?: (key: string, on: boolean) => void;
		othersProgress: { done: number; total: number } | null;
		oncancelothers?: () => void;
		onretryothers?: () => void;
		/** Why "Compute them again" is unavailable ('' when it can run). */
		othersRetryReason: string;
	}

	let {
		figure = $bindable(),
		showTable = $bindable(false),
		reading = $bindable(null),
		onlabels,
		members,
		data,
		shown,
		systemShown,
		stationShown,
		notes,
		notesWith,
		refusals,
		memberNames,
		arrangement,
		table,
		project,
		solved,
		prefs,
		nameOf,
		caseName,
		stale = false,
		image,
		loading,
		systemLoading,
		othersLoading,
		othersRetry,
		onretrysystem,
		oncancelsystem,
		others,
		othersOn,
		onothers,
		onotherstick,
		othersProgress,
		oncancelothers,
		onretryothers,
		othersRetryReason
	}: Props = $props();
	const id = $props.id();

	/**
	 * The section nav's "Group chart" (§5.4): its mark, the group system curve's refusal, else a
	 * request drawn here that failed (the group system curve, or a case's station duty on the
	 * chart). The group curve's refusal and line head Station since S3, and mark it there.
	 */
	let heading: HTMLElement | undefined = $state();
	registerSection(
		'group-chart',
		() => heading,
		() =>
			sectionMark({
				refused: notes.systemCurve?.kind === 'refused',
				failed:
					notes.systemCurve?.kind === 'error' ||
					others.some((o) => o.onChart && o.state === 'error')
			})
	);
	/** The section nav, for "Go to the pump chart" (§6.2); none in the card's own tests. */
	const nav = useSectionNav();

	const caption = $derived(
		`${groupCaption(memberNames, arrangement)}${caseName ? `, ${caseName}` : ''}${stale ? ' (out of date)' : ''}`
	);
	const summary = $derived(groupSummary(data, members, shown, project, systemShown));
	const legend = $derived(groupLegend(data));
	const samples = $derived(
		shown ? groupSampleRows(shown, shown.station.memberIds, prefs, project) : []
	);
	/** The group system curve's rows: its reasons told with names and each element's rule. */
	const systemRows = $derived(
		systemShown ? groupSystemRows(systemShown, prefs, { project, solved }) : []
	);
	/** A case's ring, as drawn (its duty in display units, its claim in words). */
	const ringCase = (n: number | null) =>
		n === null ? null : (data.others.flatMap((r) => r.cases).find((c) => c.number === n) ?? null);
	/** The rings' own curves are judged (D24 §9.6): "Its group curve" is a column. */
	const curveColumn = $derived(data.others.some((r) => r.cases.some((c) => c.curveCell !== null)));
	/** "Other cases' group curves": every point of each other case's curve drawn (§9.6). */
	const curveRows = $derived(otherCurveRows(others, prefs, project));
	/**
	 * A cell of "Other cases' group curves": a table cell, below 640 px a label and value pair
	 * (Running combinations' list), "—" and an empty note out of sight there.
	 */
	const listCell = (value: string, numeric: boolean) => [
		'border-b border-slate-100 px-2 py-1',
		numeric ? 'text-right whitespace-nowrap tabular-nums' : 'text-xs text-slate-600',
		'max-sm:flex max-sm:max-w-full max-sm:min-w-0 max-sm:items-baseline max-sm:gap-1 max-sm:border-0 max-sm:p-0 max-sm:text-left max-sm:whitespace-normal',
		'max-sm:before:text-xs max-sm:before:text-slate-600 max-sm:before:content-[attr(data-label)]',
		(value === '—' || value === '') && 'max-sm:sr-only'
	];
	/** The labels on the curves: the page's pure placement, run by the chart's plugin. */
	const curveLabels = { place: placeCurveLabels, anchor: curveAnchor };

	/** "Read along the curves": the group curve's samples, in rise order. */
	const readout = $derived(shown ? groupReadout(shown, nameOf, prefs) : []);
	const dutyIndex = $derived(readout.findIndex((r) => r.duty));
	/** The sample the user moved to, for this response (else the duty's, else the first). */
	const moved = $derived(reading !== null && reading.response === shown);
	const readIndex = $derived(
		moved ? Math.min(reading!.index, readout.length - 1) : dutyIndex >= 0 ? dutyIndex : 0
	);
	const readSample = $derived(readout[readIndex] ?? null);
	/** What the readout adds at the duty's sample, after the station's flow. */
	const DUTY_RISE = " (the duty's rise)";
	const readText = $derived(
		readSample ? `${readSample.text}${readSample.duty ? DUTY_RISE : ''}` : ''
	);
	/** Marked on the chart once the user reads along (the duty's points are drawn already). */
	const mark = $derived<GroupReadoutMark | null>(moved ? (readSample?.mark ?? null) : null);
	const fmt = (v: number) => formatNumber(v, 4);

	const phone = mediaQuery('(max-width: 639px)');
	const heightRem = $derived(chartHeightRem(['head'], phone.current));

	/** "Read along the curves": focus returns here from "Back to the duty", which then goes. */
	let readSlider: HTMLInputElement | undefined = $state();
	let systemCancelButton: HTMLButtonElement | undefined = $state();
	let systemRetryButton: HTMLButtonElement | undefined = $state();
	let othersCancelButton: HTMLButtonElement | undefined = $state();
	let othersRetryButton: HTMLButtonElement | undefined = $state();
	let canvas: HTMLCanvasElement | undefined = $state();
	let noCanvas = $state(false);
	let loadFailed = $state(false);
	const tableShown = $derived(showTable || noCanvas || loadFailed);

	// From the group system curve's Cancel to the button that computes it again (or the figure),
	// and back (the group curve's handovers are Station's since S3, unchanged).
	$effect.pre(() => {
		if (systemLoading) return;
		const cancel = untrack(() => systemCancelButton);
		if (!cancel || document.activeElement !== cancel) return;
		void tick().then(() => (systemRetryButton ?? figure)?.focus());
	});
	$effect.pre(() => {
		if (!systemLoading) return;
		const retry = untrack(() => systemRetryButton);
		if (!retry || document.activeElement !== retry) return;
		void tick().then(() => (systemCancelButton ?? figure)?.focus());
	});
	// The same for the other cases' Cancel and "Compute them again" (slice 4d). "Compute them
	// again" also goes without a progress line, when it is pressed while a calculation runs (the
	// Pumps view gives none then: nothing is computed for the other cases until it ends).
	$effect.pre(() => {
		if (othersLoading) return;
		const cancel = untrack(() => othersCancelButton);
		if (!cancel || document.activeElement !== cancel) return;
		void tick().then(() => (othersRetryButton ?? figure)?.focus());
	});
	$effect.pre(() => {
		if (othersRetry && !othersLoading) return;
		const retry = untrack(() => othersRetryButton);
		if (!retry || document.activeElement !== retry) return;
		void tick().then(() => (othersCancelButton ?? figure)?.focus());
	});

	/** The chart chunk, kept once loaded (the image never waits for it again). */
	let chartModule: typeof import('./chart-setup') | null = null;
	let drawn = $state(false);
	/** The chart drawn on screen (not reactive): the readout's mark redraws it. */
	let drawnChart: ChartInstance<'line'> | null = null;
	let markNow: GroupReadoutMark | null = null;
	$effect(() => {
		markNow = mark;
		drawnChart?.draw();
	});

	$effect(() => {
		const element = canvas;
		const d = data;
		// A phone's screen labels the other cases' rings by number only (slice 4d).
		const compact = phone.current;
		if (!element) return;
		let cancelled = false;
		let chart: ChartInstance<'line'> | null = null;
		drawn = false;
		void import('./chart-setup').then(
			(module) => {
				if (cancelled) return;
				chartModule = module;
				const { Chart, pumpGroupConfig } = module;
				const context = element.getContext('2d');
				if (!context) {
					noCanvas = true;
					return;
				}
				chart = new Chart(
					context,
					pumpGroupConfig(d, {
						legendLabels: Chart.defaults.plugins.legend.labels.generateLabels,
						format: fmt,
						htmlLegend: true,
						readout: () => markNow,
						compactLabels: compact,
						curveLabels,
						onlabels: (placed) => labelsDrawn(element, placed)
					})
				);
				drawnChart = chart;
				drawn = true;
			},
			() => {
				if (!cancelled) loadFailed = true;
			}
		);
		return () => {
			cancelled = true;
			if (drawnChart === chart) drawnChart = null;
			chart?.destroy();
		};
	});

	/**
	 * A drawing of the chart on screen placed its curve labels: the notes count those left out,
	 * and the canvas keeps the placement for measuring the layout (`data-curve-labels`).
	 */
	function labelsDrawn(element: HTMLCanvasElement, placed: CurveLabelsDrawn) {
		element.dataset.curveLabels = JSON.stringify(placed);
		onlabels?.(placed.leftOut);
	}

	/** Why no image can be made now ('' when it can). */
	const imageReason = $derived(
		!image
			? ''
			: image.unavailable ||
					(loading
						? 'Wait until the group curve is computed, or cancel it.'
						: systemLoading
							? 'Wait until the group system curve is computed, or cancel it.'
							: othersLoading
								? "Wait until the other cases' station duties are computed, or cancel them."
								: !drawn
									? 'The chart is being drawn.'
									: '')
	);
	/**
	 * A reason that lasts while the results stand (the image's own `unavailable`) is shown beside
	 * Download image; the passing ones (a curve being computed, the chart being drawn) stay hidden
	 * and in its title, so nothing flashes on every redraw (§5.3 Actions, §15 item 27).
	 */
	const imageLasting = $derived(!!image?.unavailable);
	let makingImage = false;

	/** The group system curve's request: being computed, failed or cancelled (not computed). */
	const systemRequest = $derived(
		notes.systemCurve?.kind === 'loading' ||
			notes.systemCurve?.kind === 'error' ||
			notes.systemCurve?.kind === 'cancelled'
			? notes.systemCurve
			: null
	);
	/**
	 * The strip's live line is drawn empty before its progress is said (§7 Live regions, F17; S1's
	 * rule, §15 item 24), as Station's: a polite line inserted already speaking is not announced.
	 */
	let lineDrawn = $state(false);
	$effect(() => {
		let frame = requestAnimationFrame(() => {
			frame = requestAnimationFrame(() => (lineDrawn = true));
		});
		return () => cancelAnimationFrame(frame);
	});
	const systemLine = $derived(
		systemRequest?.kind === 'loading' && !lineDrawn ? null : systemRequest
	);
	/**
	 * The lines about the curves' coverage, plain, after the request's line (§5.3 The strip; §5.2:
	 * no mark on a fact): points without a flow or a rise, a case with no duty, a solve that did
	 * not converge, no group system curve, one member only.
	 */
	const coverage = $derived(
		[
			notes.curve && !['loading', 'error', 'cancelled', 'refused'].includes(notes.curve.kind)
				? notes.curve.text
				: null,
			notes.systemCurve && !systemRequest ? notes.systemCurve.text : null
		].filter((line): line is string => !!line)
	);
	/** The strip has nothing to show: it takes no room (its live line stays, empty). */
	const stripIdle = $derived(!systemLine && !coverage.length);
	/** The duty checks agree: each its ✓ (§5.2: a check that agrees; none otherwise). */
	const dutyAgrees = $derived(!!shown?.dutyCheck?.agrees);
	const systemDutyAgrees = $derived(!!systemShown?.systemDutyCheck?.agrees);
	/**
	 * "How to read this chart": what it holds, said in its summary (ui-guide: a disclosure says
	 * what it holds), the group system curve's note only while there is one.
	 */
	const readingHolds = $derived(
		notes.system
			? "the axes, the group system curve, each pump's own system curve"
			: "the axes, each pump's own system curve"
	);
	/** A marker entry of the legend is a member's (two-up from 18 rem; the others from 26 rem). */
	const memberEntry = (key: string) => key.startsWith('point-');

	/** The chart drawn again at a fixed size with its caption and notes, as a PNG. */
	async function downloadImage() {
		const module = chartModule;
		if (!image || !module || imageReason || makingImage) return;
		makingImage = true;
		const { Chart, downloadChartImage, pumpGroupConfig } = module;
		const reasons = refusals.map((r) => wordsText(r.words));
		/** The image's own count of curve labels left out (D24 §9.3), told as it is drawn. */
		let imageLeftOut = 0;
		await downloadChartImage(Chart, {
			config: pumpGroupConfig(data, {
				legendLabels: Chart.defaults.plugins.legend.labels.generateLabels,
				format: fmt,
				forImage: true,
				curveLabels,
				onlabels: (placed) => (imageLeftOut = placed.leftOut)
			}),
			title: groupImageTitle(memberNames, arrangement),
			lines: groupNoteLines(notes, reasons),
			// With other cases' curves labelled, the notes count the image's own labels left out.
			...(data.otherCurves.length
				? { drawnLines: () => groupNoteLines(notesWith(imageLeftOut), reasons) }
				: {}),
			content: `Pumps together ${memberNames.join(', ')}`,
			...(caseName ? { caseName } : {}),
			disclaimer: DISCLAIMER,
			source: image
		});
		makingImage = false;
	}
</script>

<!-- A plain div with its heading, not a landmark (§7); tabindex −1, the section nav's target. -->
<div class="space-y-2 border-t border-slate-200 pt-3" data-group-chart>
	<h4
		bind:this={heading}
		id="{id}-heading"
		class="scroll-mt-[calc(var(--pumps-nav-h,0px)-var(--pumps-nav-pad,0px)+0.5rem)] text-sm font-semibold text-slate-900"
		tabindex="-1"
	>
		Group chart
	</h4>
	<!--
		One anatomy (§5.1, §5.3 Group chart), as the pump chart's: the caption, the canvas, the
		reading, the strip, the actions, the legend, the notes, the reference, the data region.
		`aria-busy` is the canvas's, the part that is redrawn, so no live line below has a busy
		ancestor (§5.3 markup rules, §7).
	-->
	<figure bind:this={figure} class="space-y-2" aria-labelledby="{id}-caption" tabindex="-1">
		<figcaption id="{id}-caption" class="text-sm font-medium">{caption}</figcaption>
		{#if loadFailed}
			<p class="text-sm text-slate-700" role="alert">
				{STALE_CHUNK_MESSAGE} The tables below list its points.
			</p>
		{:else if !noCanvas}
			<div
				class="relative w-full"
				style:height="{heightRem}rem"
				role="img"
				aria-label={summary}
				aria-busy={loading || systemLoading || othersLoading}
			>
				<canvas bind:this={canvas} aria-hidden="true"></canvas>
			</div>
		{:else}
			<p class="text-sm text-slate-700">
				The chart cannot be drawn in this browser. The tables below list its points.
			</p>
		{/if}
		{#if readSample}
			<!-- Read along the curves: the group curve's samples, each read from the response. A
				container: the readout's pairs go two-up from 26 rem, one per line below (§5.5). -->
			<div class="@container space-y-1">
				<div class="flex flex-wrap items-center gap-x-3">
					<label for="{id}-read" class="text-xs font-medium text-slate-700"
						>Read along the curves</label
					>
					<input
						bind:this={readSlider}
						id="{id}-read"
						type="range"
						class="min-h-11 min-w-40 flex-1 accent-slate-700"
						min="0"
						max={readout.length - 1}
						step="1"
						value={readIndex}
						aria-valuetext={readText}
						aria-describedby="{id}-read-hint"
						oninput={(event) =>
							(reading = { response: shown, index: Number(event.currentTarget.value) })}
						onkeydown={(event) => {
							if (event.key === 'Escape' && moved) {
								event.preventDefault();
								reading = null;
							}
						}}
					/>
					{#if moved && dutyIndex >= 0 && readIndex !== dutyIndex}
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							onclick={() => {
								reading = null;
								void tick().then(() => readSlider?.focus());
							}}>Back to the duty</button
						>
					{/if}
				</div>
				<!-- One paragraph, not live: each pump and value a pair, from the sample's parts, the
					separators visually hidden, so its text is the slider's value text (§5.3 Reading). -->
				<p
					class="grid grid-cols-1 gap-x-4 text-sm tabular-nums @min-[26rem]:grid-cols-2"
					data-group-readout
				>
					<span class="col-span-full font-medium">{readSample.parts.at}:</span>
					{#if readSample.parts.none}<span class="col-span-full">{readSample.parts.none}</span
						>{:else}{#each readSample.parts.pairs as pair, i (i)}<span class="min-w-0"
								>{#if i}<span class="sr-only">,&nbsp;</span>{/if}<span
									class="wrap-break-word text-slate-600">{pair.name}</span
								>
								<span class="font-medium whitespace-nowrap">{pair.value}</span
								>{#if readSample.duty && i === readSample.parts.pairs.length - 1}<span
										>{DUTY_RISE}</span
									>{/if}</span
							>{/each}{/if}
				</p>
				<p id="{id}-read-hint" class="hint">
					Steps over the group curve's samples, each pump's flow and the station's as computed at
					that rise (nothing between samples is read).
				</p>
			</div>
		{/if}
		<!--
			The strip (§5.3 The strip): the group system curve's request, one row: an always-present
			polite line, empty when idle and never role=status, drawn empty before its first progress,
			its mark at its first line, its button after it and described by it; then the lines about
			the curves' coverage, plain. Out of sight while it has nothing to say, so it takes no room,
			its line still in the accessibility tree.
		-->
		<div class={['space-y-1', stripIdle && 'sr-only']} data-group-strip>
			<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
				<span
					id="{id}-system-state"
					data-group-system-state
					aria-live="polite"
					aria-atomic="true"
					class={[
						'inline-flex items-start gap-1.5 text-xs',
						systemLine?.kind === 'error' ? 'text-red-800' : 'text-slate-700'
					]}
					>{#if systemLine?.kind === 'loading'}<Icon
							name="spinner"
							class="mt-px size-3.5 shrink-0 text-slate-500 motion-safe:animate-spin"
						/>{:else if systemLine?.kind === 'error'}<Icon
							name="octagon"
							class="mt-px size-3.5 shrink-0 text-red-700"
						/>{/if}{systemLine?.text ?? ''}</span
				>
				{#if systemRequest?.kind === 'loading' && oncancelsystem}
					<button
						bind:this={systemCancelButton}
						type="button"
						class="btn btn-quiet px-2 text-blue-800"
						aria-label="Cancel the group system curve"
						aria-describedby="{id}-system-state"
						onclick={oncancelsystem}>Cancel</button
					>
				{:else if (systemRequest?.kind === 'error' || systemRequest?.kind === 'cancelled') && onretrysystem}
					<button
						bind:this={systemRetryButton}
						type="button"
						class="btn btn-quiet px-2 text-blue-800"
						aria-describedby="{id}-system-state"
						onclick={onretrysystem}
					>
						{systemRequest.kind === 'error'
							? 'Try the group system curve again'
							: 'Compute the group system curve'}
					</button>
				{/if}
			</div>
			{#each coverage as line, i (i)}
				<p class="text-xs text-slate-700">{line}</p>
			{/each}
		</div>
		{#if !loadFailed && !noCanvas}
			<!-- The actions right after the strip, as on the pump chart (§5.1 item 6; F3: they sat at
				the card's foot), then the legend: a departure from §5.1's order (legend, then actions),
				since with the reading and the strip above it the condenser's legend put Show data table
				676 px below the canvas at 1280×800, over §5.7 row 3's 600. The data table opens after
				the reference, below; the names told apart from the pump chart's by a hidden suffix. -->
			<div class="flex flex-wrap items-center gap-x-3 gap-y-1" data-group-actions>
				<button
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-expanded={tableShown}
					aria-controls="{id}-data"
					onclick={() => (showTable = !showTable)}
				>
					<!-- The space outside the hidden suffix, so every name computation keeps it. -->
					{tableShown ? 'Hide data table' : 'Show data table'}
					<span class="sr-only">of the group chart</span>
				</button>
				{#if image}
					<!-- Download image and its reason, one item (§5.3 Actions, §15 item 27): a lasting
						reason beside the button where the row has room, under it where not, never under
						Show data table. -->
					<div class="flex flex-1 flex-wrap items-center gap-x-3 gap-y-1">
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							data-chart-image
							aria-label="Download image of the pumps together: {memberNames.join(', ')}{caseName
								? `, ${caseName}`
								: ''}"
							aria-disabled={!!imageReason}
							aria-describedby={imageReason ? `${id}-image-reason` : undefined}
							title={(!imageLasting && imageReason) || undefined}
							onclick={() => void downloadImage()}
						>
							<Icon name="download" class="size-4" /> Download image
						</button>
						{#if imageReason}<span
								id="{id}-image-reason"
								class={imageLasting ? 'text-xs text-slate-700' : 'sr-only'}>{imageReason}</span
							>{/if}
					</div>
				{/if}
			</div>
			<!-- The legend after the reading, the strip and the actions, so the readout sits under its
				canvas (§6.1, F12, F27): a container, its marker entries two-up where they fit (the
				members' from 18 rem, every one's from 26 rem), its lines one per row. -->
			<div class="@container">
				<ul
					class="grid grid-cols-1 gap-x-3.5 gap-y-1 text-xs text-slate-800 @min-[18rem]:grid-cols-2"
					aria-label="Legend"
				>
					{#each legend as item (item.key)}
						<li
							class={[
								'flex min-w-0 items-start gap-1.5',
								item.kind === 'line'
									? 'col-span-full'
									: !memberEntry(item.key) && '@min-[18rem]:col-span-full @min-[26rem]:col-span-1'
							]}
						>
							{#if item.kind === 'line'}
								<svg width="24" height="8" aria-hidden="true" class="mt-1 shrink-0"
									><line
										x1="0"
										y1="4"
										x2="24"
										y2="4"
										stroke={item.color}
										stroke-width="2"
										stroke-dasharray={item.dash?.join(' ') || undefined}
									/></svg
								>
							{:else}
								<span aria-hidden="true" style:color={item.color}>{item.symbol}</span>
							{/if}
							{item.label}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
		<!--
			Notes about the values (§5.3), groupNotes' words: the duty checks first, each with a ✓ when
			it agrees (an element of its own before its sentence, §5.2 Placement) and none otherwise,
			its Details and "Several steady states can exist …" when it disagrees; then the frame, the
			members' notes and the dashed note.
		-->
		<div class="space-y-1" data-group-notes>
			{#each notes.duty as note, i (i)}
				{#if i === 0 && dutyAgrees}
					<div class="flex items-start gap-1.5" data-group-check>
						<Icon name="check" class="mt-px size-3.5 shrink-0 text-emerald-700" />
						<p class="text-xs text-slate-700">{note}</p>
					</div>
				{:else}
					<p class="text-xs text-slate-700">
						{note}{#if i === 0 && shown?.dutyCheck && !shown.dutyCheck.agrees}<IssueDetail
								detail={shown.dutyCheck.message}
								subject="the duty check"
							/>{/if}
					</p>
				{/if}
			{/each}
			{#each notes.systemDuty as note, i (i)}
				{#if i === 0 && systemDutyAgrees}
					<div class="flex items-start gap-1.5" data-group-check>
						<Icon name="check" class="mt-px size-3.5 shrink-0 text-emerald-700" />
						<p class="text-xs text-slate-700">{note}</p>
					</div>
				{:else}
					<p class="text-xs text-slate-700">
						{note}{#if i === 0 && systemShown?.systemDutyCheck && !systemShown.systemDutyCheck.agrees}<IssueDetail
								detail={systemShown.systemDutyCheck.message}
								subject="the system duty check"
							/>{/if}
					</p>
				{/if}
			{/each}
			{#if notes.frame}<p class="text-xs text-slate-700">{notes.frame}</p>{/if}
			<!-- Keyed by index, never by words: a pump's name need not be unique. -->
			{#each notes.members as note, i (i)}
				<p class="text-xs text-slate-700">{note}</p>
			{/each}
			{#if notes.dashed}<p class="text-xs text-slate-700">{notes.dashed}</p>{/if}
		</div>
		<!--
			The reference (§5.3), three native disclosures, closed, each saying what it holds: how to
			read this chart (the axes, the group system curve, each pump's own system curve, with the
			way to the pump chart), then how each curve is computed.
		-->
		<details class="group" data-group-reading>
			<summary class="more-summary">
				<Icon
					name="right"
					class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
				/>
				<span class="min-w-0 flex-1"
					>How to read this chart<span class="font-normal text-slate-600">: {readingHolds}</span
					></span
				>
			</summary>
			<div class="space-y-1 pb-1">
				<p class="text-xs text-slate-700">{notes.axes}</p>
				{#if notes.system}<p class="text-xs text-slate-700">{notes.system}</p>{/if}
				<p class="text-xs text-slate-700">{notes.systemCurves}</p>
				{#if nav?.shown}
					<!-- A button, never a link: the URL fragment is the project (D3, §6.2). -->
					<button
						type="button"
						class="btn btn-quiet px-2 text-blue-800"
						onclick={() => nav.go('pump-chart')}>Go to the pump chart</button
					>
				{/if}
			</div>
		</details>
		{#if shown}
			<details class="group">
				<summary class="more-summary">
					<Icon
						name="right"
						class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
					/>
					{systemShown ? 'How the group curve is computed' : 'How this curve is computed'}
				</summary>
				<div class="space-y-1 pb-1 text-xs text-slate-700">
					<p class="font-medium">
						{groupMethodsHeading(shown)}
					</p>
					{#each shown.methods.items as item, i (i)}<p class="break-words">{item}</p>{/each}
					{#if shown.methods.references.length}
						<p class="font-medium">References</p>
						<ul class="list-disc pl-5">
							{#each shown.methods.references as reference, i (i)}<li class="break-words">
									{reference}
								</li>{/each}
						</ul>
					{/if}
				</div>
			</details>
		{/if}
		{#if systemShown}
			<details class="group">
				<summary class="more-summary">
					<Icon
						name="right"
						class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
					/>
					How the group system curve is computed
				</summary>
				<div class="space-y-1 pb-1 text-xs text-slate-700">
					<p class="font-medium">
						{groupMethodsHeading(systemShown)}
					</p>
					{#each systemShown.methods.items as item, i (i)}<p class="break-words">
							{item}
						</p>{/each}
					{#if systemShown.methods.references.length}
						<p class="font-medium">References</p>
						<ul class="list-disc pl-5">
							{#each systemShown.methods.references as reference, i (i)}<li class="break-words">
									{reference}
								</li>{/each}
						</ul>
					{/if}
				</div>
			</details>
		{/if}
		<!-- The data region after the reference (§5.1 item 9, §9 S2; F3: it opened at the card's
			foot), so opening it never pushes a note or a check away from the chart. -->
		{#if tableShown}
			<div id="{id}-data" class="space-y-3" data-group-data>
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div
					class="relative overflow-auto rounded-md border border-slate-200 bg-white"
					role="region"
					aria-labelledby="{id}-points-caption"
					tabindex="0"
				>
					<table class="w-full text-sm">
						<caption
							id="{id}-points-caption"
							class="px-2 py-1 text-left text-xs font-semibold text-slate-700"
						>
							Each pump's point (flow through it)
						</caption>
						<thead class="bg-slate-50">
							<tr>
								<th scope="col" class="px-2 py-1 text-left font-medium">Pump</th>
								<th scope="col" class="px-2 py-1 text-right font-medium">Flow ({data.flowUnit})</th>
								<th scope="col" class="px-2 py-1 text-right font-medium">Head ({data.headUnit})</th>
								<th scope="col" class="px-2 py-1 text-left font-medium">State</th>
							</tr>
						</thead>
						<tbody>
							{#each table.rows as row (row.id)}
								{@const point = data.points.find((p) => p.id === row.id)}
								<tr class="border-t border-slate-100">
									<th scope="row" class="px-2 py-1 text-left font-normal"
										><span aria-hidden="true" style:color={row.style.color}
											>{point?.held ? HELD_SYMBOL : row.style.symbol}</span
										>
										{row.name}</th
									>
									<td class="px-2 py-1 text-right tabular-nums"
										>{point ? fmt(point.point.x) : '—'}</td
									>
									<td class="px-2 py-1 text-right tabular-nums"
										>{point ? fmt(point.point.y) : '—'}</td
									>
									<td class="px-2 py-1 text-xs text-slate-600">{row.cells.state}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if stationShown?.duty && data.station}
					<p class="text-sm">
						<span aria-hidden="true">{STATION_SYMBOL}</span> Group duty (station's flow):
						<span class="tabular-nums">{fmt(data.station.flow)} {data.flowUnit}</span> at a rise of
						<span class="tabular-nums">{fmt(data.station.point.y)} {data.headUnit}</span>; {ARRANGEMENT_WORDS[
							stationShown.station.arrangement
						]}.
						{#if shown?.dutyCheck}
							Duty check: {dutyCheckState(shown)}{shown.dutyCheck.flow === null
								? ''
								: `; ${dutyCheckWords(shown, nameOf, prefs)}`}.<IssueDetail
								detail={shown.dutyCheck.message}
								subject="the duty check"
							/>
						{/if}
						{#if systemShown?.systemDutyCheck}
							System duty check: {systemDutyCheckState(systemShown)}.<IssueDetail
								detail={systemShown.systemDutyCheck.message}
								subject="the system duty check"
							/>
						{/if}
					</p>
				{/if}
				{#if othersOn && others.length}
					<!-- The other cases' station duties (slice 4d): the rings, and why a case has none;
						none while they are not asked for (the notes' one line says so). -->
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div
						class="relative overflow-auto rounded-md border border-slate-200 bg-white"
						role="region"
						aria-labelledby="{id}-others-caption"
						tabindex="0"
					>
						<table class="w-full text-sm">
							<caption
								id="{id}-others-caption"
								class="px-2 py-1 text-left text-xs font-semibold text-slate-700"
							>
								Other cases' station duties
							</caption>
							<thead class="bg-slate-50">
								<tr>
									<th scope="col" class="px-2 py-1 text-left font-medium">Case</th>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Station flow ({data.flowUnit})</th
									>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Rise ({data.headUnit})</th
									>
									<th scope="col" class="px-2 py-1 text-left font-medium"
										>On the group system curve shown</th
									>
									{#if curveColumn}
										<th scope="col" class="px-2 py-1 text-left font-medium">{OTHER_CURVE_COLUMN}</th
										>
									{/if}
								</tr>
							</thead>
							<tbody>
								{#each others as other (other.key)}
									{@const ring = ringCase(other.number)}
									<tr class="border-t border-slate-100">
										<th scope="row" class="px-2 py-1 text-left font-normal"
											>{#if ring}<span aria-hidden="true" style:color={GROUP_OTHER}
													>{`${OTHER_SYMBOL} `}</span
												>{/if}{ring ? `${ring.number} · ` : ''}{other.name}{other.stale
												? ' (out of date)'
												: ''}</th
										>
										{#if ring}
											<td class="px-2 py-1 text-right tabular-nums">{fmt(ring.flow)}</td>
											<td class="px-2 py-1 text-right tabular-nums">{fmt(ring.rise)}</td>
											<td class="px-2 py-1 text-xs text-slate-600">{ring.claim}</td>
											{#if curveColumn}
												<td class="px-2 py-1 text-xs text-slate-600">{ring.curveCell ?? '—'}</td>
											{/if}
										{:else}
											<td colspan={curveColumn ? 4 : 3} class="px-2 py-1 text-xs text-slate-600"
												>{other.words}</td
											>
										{/if}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
				{#if curveRows.length}
					<!-- Other cases' own group curves (D24 §9.6): every point, those cut from the chart
						included, one row group per case; a list below 640 px, as Running combinations. -->
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div
						class="relative max-h-72 overflow-auto rounded-md border border-slate-200 bg-white"
						role="region"
						aria-labelledby="{id}-curves-caption"
						tabindex="0"
						data-other-curves
					>
						<!-- svelte-ignore a11y_no_redundant_roles -->
						<table
							role="table"
							class="w-full border-separate border-spacing-0 text-sm max-sm:block"
						>
							<caption
								id="{id}-curves-caption"
								class="sticky left-0 px-2 py-1 text-left text-xs font-semibold text-slate-700 max-sm:block"
							>
								{OTHER_CURVES_CAPTION}
							</caption>
							<!-- svelte-ignore a11y_no_redundant_roles -->
							<thead role="rowgroup" class="sticky top-0 bg-slate-50 max-sm:sr-only">
								<!-- svelte-ignore a11y_no_redundant_roles -->
								<tr role="row">
									<th role="columnheader" scope="col" class="px-2 py-1 text-right font-medium"
										>Rise ({data.headUnit})</th
									>
									<th role="columnheader" scope="col" class="px-2 py-1 text-right font-medium"
										>Flow ({data.flowUnit})</th
									>
									<th role="columnheader" scope="col" class="px-2 py-1 text-left font-medium"
										>Note</th
									>
								</tr>
							</thead>
							{#each curveRows as group (group.key)}
								{@const outOfDate = others.find((o) => o.key === group.key)?.stale ?? false}
								<!-- svelte-ignore a11y_no_redundant_roles -->
								<tbody role="rowgroup" class="max-sm:block">
									<!-- svelte-ignore a11y_no_redundant_roles -->
									<tr role="row" class="max-sm:block">
										<th
											role="rowheader"
											scope="rowgroup"
											colspan="3"
											class={[
												'border-y border-slate-200 px-2 py-1 text-left font-medium break-words max-sm:block',
												outOfDate ? 'bg-amber-50/60' : 'bg-slate-50/60'
											]}
										>
											<span aria-hidden="true" style:color={GROUP_OTHER}>{`${OTHER_SYMBOL} `}</span
											>{group.header}
										</th>
									</tr>
									{#each group.rows as row, i (i)}
										<!-- svelte-ignore a11y_no_redundant_roles -->
										<tr
											role="row"
											class="max-sm:flex max-sm:flex-wrap max-sm:items-baseline max-sm:gap-x-3 max-sm:gap-y-0.5 max-sm:px-2 max-sm:pb-1.5"
										>
											<td
												role="cell"
												data-label="Rise ({data.headUnit})"
												class={listCell(row.rise, true)}>{row.rise}</td
											>
											<td
												role="cell"
												data-label="Flow ({data.flowUnit})"
												class={listCell(row.flow, true)}>{row.flow}</td
											>
											<td role="cell" data-label="Note" class={listCell(row.note, false)}
												>{row.note}</td
											>
										</tr>
									{/each}
								</tbody>
							{/each}
						</table>
					</div>
				{/if}
				{#if samples.length}
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div
						class="relative max-h-72 overflow-auto rounded-md border border-slate-200 bg-white"
						role="region"
						aria-labelledby="{id}-samples-caption"
						tabindex="0"
					>
						<table class="w-full text-sm">
							<caption
								id="{id}-samples-caption"
								class="sticky left-0 px-2 py-1 text-left text-xs font-semibold text-slate-700"
							>
								Group curve (station's flow at each rise)
							</caption>
							<thead class="sticky top-0 bg-slate-50">
								<tr>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Rise ({data.headUnit})</th
									>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Flow ({data.flowUnit})</th
									>
									{#each shown!.station.memberIds as memberId (memberId)}
										<th scope="col" class="px-2 py-1 text-right font-medium whitespace-nowrap"
											>{nameOf(memberId)} flow ({data.flowUnit})</th
										>
										<th scope="col" class="px-2 py-1 text-right font-medium whitespace-nowrap"
											>{nameOf(memberId)} head ({data.headUnit})</th
										>
										<th scope="col" class="px-2 py-1 text-left font-medium whitespace-nowrap"
											>{nameOf(memberId)} state</th
										>
									{/each}
									<th scope="col" class="px-2 py-1 text-left font-medium">Note</th>
								</tr>
							</thead>
							<tbody>
								{#each samples as sample, i (i)}
									<tr class="border-t border-slate-100">
										<td class="px-2 py-1 text-right tabular-nums">{sample.rise}</td>
										<td class="px-2 py-1 text-right tabular-nums">{sample.flow}</td>
										{#each sample.members as m, k (k)}
											<td class="px-2 py-1 text-right tabular-nums">{m.flow}</td>
											<td class="px-2 py-1 text-right tabular-nums">{m.head}</td>
											<td class="px-2 py-1 text-xs whitespace-nowrap text-slate-600">{m.state}</td>
										{/each}
										<td class="px-2 py-1 text-xs text-slate-600"
											>{[sample.duty ? "The duty's rise (the duty check)." : '', sample.note]
												.filter(Boolean)
												.join(' ')}</td
										>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
				{#if systemRows.length}
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<div
						class="relative max-h-72 overflow-auto rounded-md border border-slate-200 bg-white"
						role="region"
						aria-labelledby="{id}-system-caption"
						tabindex="0"
					>
						<table class="w-full text-sm">
							<caption
								id="{id}-system-caption"
								class="sticky left-0 px-2 py-1 text-left text-xs font-semibold text-slate-700"
							>
								Group system curve (rise the rest of the network needs at each station's flow)
							</caption>
							<thead class="sticky top-0 bg-slate-50">
								<tr>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Flow ({data.flowUnit})</th
									>
									<th scope="col" class="px-2 py-1 text-right font-medium"
										>Rise ({data.headUnit})</th
									>
									<th scope="col" class="px-2 py-1 text-left font-medium">Note</th>
								</tr>
							</thead>
							<tbody>
								{#each systemRows as row, i (i)}
									<tr class="border-t border-slate-100">
										<td class="px-2 py-1 text-right tabular-nums">{row.flow}</td>
										<td class="px-2 py-1 text-right tabular-nums">{row.rise}</td>
										<td class="px-2 py-1 text-xs text-slate-600"
											>{[row.duty ? "The duty's flow (the system duty check)." : '', row.note]
												.filter(Boolean)
												.join(' ')}{#if row.detail}<IssueDetail
													detail={row.detail}
													subject="the point at {row.flow} {data.flowUnit}"
												/>{/if}</td
										>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		{/if}
		{#if onothers || notes.others.length}
			<!--
				The other cases on the group chart (slice 4d), at the figure's end (§5.1 item 10): their
				controls (PumpGroupOthers), their progress with its Cancel or "Compute them again", and
				their notes. S3's second half gives them their heading, their own live line and the ring
				notes' cut (§5.3 "Other cases on the group chart"); until then their progress keeps its
				status region, the card's last, drawn with scenarios only.
			-->
			<div class="space-y-2" data-group-others>
				{#if onothers && stationShown}
					<PumpGroupOthers {others} {othersOn} {onothers} {onotherstick} {caseName} />
				{/if}
				{#if onothers}
					<div role="status" class="text-xs text-slate-600">
						{#if othersLoading && othersProgress && !loading && !systemLoading}
							<span
								>Computing the other cases' station duties: {Math.min(
									othersProgress.done + 1,
									othersProgress.total
								)} of {othersProgress.total}…</span
							>
						{/if}
					</div>
				{/if}
				{#if othersLoading && !loading && !systemLoading && oncancelothers}
					<button
						bind:this={othersCancelButton}
						type="button"
						class="btn btn-quiet px-2 text-blue-800"
						aria-label="Cancel the other cases' station duties"
						onclick={oncancelothers}>Cancel</button
					>
				{:else if othersRetry && !othersLoading}
					<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
						<p id="{id}-others-state" class="text-xs text-slate-600">
							Not every other case's station duty was computed: see Running combinations.
						</p>
						{#if onretryothers}
							<button
								bind:this={othersRetryButton}
								type="button"
								class="btn btn-quiet px-2 text-blue-800"
								aria-disabled={!!othersRetryReason}
								aria-describedby={othersRetryReason
									? `${id}-others-retry-reason ${id}-others-state`
									: `${id}-others-state`}
								title={othersRetryReason || undefined}
								onclick={() => {
									if (!othersRetryReason) onretryothers?.();
								}}>Compute them again</button
							>
							{#if othersRetryReason}<span id="{id}-others-retry-reason" class="sr-only"
									>{othersRetryReason}</span
								>{/if}
						{/if}
					</div>
				{/if}
				<!-- Keyed by index, never by words: a pump's name need not be unique. -->
				{#each notes.others as note, i (i)}
					<p class="text-xs text-slate-700">{note}</p>
				{/each}
			</div>
		{/if}
	</figure>
</div>
