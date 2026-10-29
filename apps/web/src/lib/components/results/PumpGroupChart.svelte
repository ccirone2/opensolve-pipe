<!--
	Pumps together (CLAUDE.md D21, proposal pump-groups.md §6): a card under the pump chart, shown
	when two or more pumps have results; a disclosure, closed by default. Its members are chosen
	with checkboxes (page state, at most six), defaulting to the group suggested for the pump
	viewed, with the other suggested groups one button away. Opening it with two members or more
	asks for their group curve (POST /api/v1/pump-group-curve, for this solve and case), with
	progress and Cancel.

	The chart (the head panel only) draws each member's curve and solved point from its own result
	(exact, no request), the group curve from the API (the station solved alone between its two
	ports held a rise apart: ink, dashed where a pump runs beyond its data, gaps where a point has
	no flow) and the station's duty, an ink dot labelled "Group". The plain combined curve is not
	drawn (owner), and each pump's own system curve stays on its pump chart. When the API says the
	pumps do not form a station, the card says why in words with the elements named and linked,
	and still draws the members. Under the chart: the notes, how the curve is computed, the group
	table (from the solve, then the shares and losses from the duty) and the data table.

	Slice 4b (proposal §7): after the group curve's answer, the group system curve (the same
	request with curve 'system': the rest of the network between the station's inlet and outlet,
	at each station's flow), with its own progress, Cancel, failure and retry, drawn in the system
	orange with gaps where a point has no rise (the data table says why). The Group point is the
	two curves' crossing only when both duty checks agree. Where the group curve is refused only
	for an active PRV or PSV inside, the card says so and draws the group system curve all the
	same. "Read along the curves" steps over the group curve's samples, giving each member's flow
	and the station's at that rise exactly as the response does, and marks them on the chart.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import type { Flag, NodeResult, Project, UnitPreferences } from '$lib/api/types';
	import type { GroupCurveState, GroupSystemCurveState } from '$lib/state/project.svelte';
	import type { ChartImageSource } from '$lib/utils/export/chart-image';
	import { DISCLAIMER } from '$lib/components/links';
	import { STALE_CHUNK_MESSAGE } from '$lib/utils/export/load';
	import type { Chart as ChartInstance } from 'chart.js';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import { chartHeightRem } from '$lib/utils/pump-chart';
	import {
		andList,
		ARRANGEMENT_WORDS,
		groupCaption,
		groupChartData,
		groupImageTitle,
		groupLegend,
		groupNoteLines,
		groupNotes,
		groupReadout,
		groupSampleRows,
		groupSummary,
		groupSystemRows,
		groupTable,
		dutyCheckState,
		dutyCheckWords,
		HELD_SYMBOL,
		namesProject,
		slotStyle,
		STATION_SYMBOL,
		systemDutyCheckState,
		type GroupMemberInput,
		type GroupReadoutMark
	} from '$lib/utils/pump-group-chart';
	import {
		MAX_GROUP_PUMPS,
		pressureControlOnly,
		refusalWords,
		wordsText,
		type GroupSuggestion
	} from '$lib/utils/pump-groups';
	import { SEVERITY_LABELS } from '$lib/utils/results';
	import { formatNumber } from '$lib/utils/units';
	import Icon from '$lib/components/ui/Icon.svelte';
	import FlagIcon from './FlagIcon.svelte';
	import IssueDetail from './IssueDetail.svelte';

	interface Props {
		/** Pumps with a result, in table order: each a box. */
		pumps: readonly Omit<GroupMemberInput, 'slot'>[];
		/** The boxes ticked by slot (null: a free slot); a slot is a member's colour and marker. */
		slots: readonly (string | null)[];
		/** Tick or untick: the new slots. */
		onslots?: (slots: (string | null)[]) => void;
		/** The groups suggested on the topology as solved. */
		suggestions?: readonly GroupSuggestion[];
		/** The card is open (bindable: page state the caller keeps). */
		open?: boolean;
		/** The group curve of the members for this solve (undefined: not requested). */
		curve?: GroupCurveState;
		/** Compute it again (after a failure or a cancellation). */
		onretry?: () => void;
		/** Cancel it while it is computed. */
		oncancel?: () => void;
		/**
		 * The group system curve of the members for this solve (undefined: not requested; it is asked
		 * for after the group curve's answer).
		 */
		system?: GroupSystemCurveState;
		/** Compute the group system curve again (after a failure or a cancellation). */
		onretrysystem?: () => void;
		/** Cancel the group system curve while it is computed. */
		oncancelsystem?: () => void;
		prefs: UnitPreferences;
		/** Names (the labels project). */
		project: Project;
		/**
		 * The project the results belong to (as solved while they are out of date): topology
		 * (DIFFERENT_BOUNDARIES' side) and the names of elements deleted since. Default: `project`.
		 */
		solvedProject?: Project;
		/** Node results of the solve: the series inlet and discharge pressures. */
		nodes?: Readonly<Record<string, NodeResult>>;
		/** Why these results give no values (not converged, a failed or not reached case). */
		unavailable?: string | null;
		/** The results are out of date. */
		stale?: boolean;
		/** The case shown, in a project with scenarios. */
		caseName?: string;
		/** Open an element's results and trace. */
		oninspect?: (componentId: string) => void;
		/** A flag's words (names, display units). */
		flagText?: (flag: Flag) => string;
		/** What an image names and whether one can be made (as the pump chart's). */
		image?: ChartImageSource;
	}

	let {
		pumps,
		slots,
		onslots,
		suggestions = [],
		open = $bindable(false),
		curve: groupCurve,
		onretry,
		oncancel,
		system: systemCurve,
		onretrysystem,
		oncancelsystem,
		prefs,
		project: labels,
		solvedProject,
		nodes = {},
		unavailable = null,
		stale = false,
		caseName,
		oninspect,
		flagText = (flag) => flag.message,
		image
	}: Props = $props();
	const id = $props.id();

	/** The members: each ticked pump with a result, with its slot. */
	const members = $derived(
		slots.flatMap((pumpId, slot) => {
			const pump = pumpId === null ? undefined : pumps.find((p) => p.id === pumpId);
			return pump ? [{ ...pump, slot }] : [];
		})
	);
	const memberIds = $derived(members.map((m) => m.id));
	const ticked = (pumpId: string) => slots.includes(pumpId);
	const full = $derived(members.length >= MAX_GROUP_PUMPS);

	function setTicked(pumpId: string, on: boolean) {
		const next = [...slots];
		if (on) {
			// The first free slot: a member keeps its colour while it stays ticked.
			const free = next.indexOf(null);
			if (free >= 0) next[free] = pumpId;
			else next.push(pumpId);
		} else {
			const at = next.indexOf(pumpId);
			if (at >= 0) next[at] = null;
			while (next.length && next[next.length - 1] === null) next.pop();
		}
		onslots?.(next);
	}

	let alsoFound: HTMLElement | undefined = $state();
	let fieldset: HTMLElement | undefined = $state();

	/**
	 * Show a group found: its button goes (the group shown is not offered), so the focus moves on
	 * to the next group offered (often the one shown before), else the chart, else a ticked box.
	 */
	function showSuggestion(pumpIds: readonly string[]) {
		onslots?.([...pumpIds]);
		void tick().then(() => {
			const next =
				alsoFound?.querySelector<HTMLElement>('button') ??
				figure ??
				fieldset?.querySelector<HTMLElement>('input:checked');
			next?.focus();
		});
	}

	const sameGroup = (ids: readonly string[]) =>
		ids.length === memberIds.length && ids.every((x) => memberIds.includes(x));
	const others = $derived(suggestions.filter((s) => !sameGroup(s.pumpIds)));
	const nameOf = (pumpId: string) => pumps.find((p) => p.id === pumpId)?.name ?? pumpId;

	/** Names: current ones, and those as solved of elements deleted since. */
	const project = $derived(namesProject(labels, solvedProject));

	const response = $derived(groupCurve?.status === 'ready' ? groupCurve.response : null);
	const shown = $derived(unavailable ? null : response);
	const systemResponse = $derived(systemCurve?.status === 'ready' ? systemCurve.response : null);
	const systemShown = $derived(unavailable ? null : systemResponse);
	/**
	 * The station and its duty: the group curve's response, else the group system curve's (the
	 * same station and the same duty, from the case's own solve), when the group curve is refused
	 * for an active PRV or PSV inside only.
	 */
	const stationShown = $derived(shown ?? (systemShown?.duty ? systemShown : null));
	const data = $derived(groupChartData(members, prefs, shown, systemShown));
	const notes = $derived(
		groupNotes({
			data,
			members,
			state: unavailable ? undefined : groupCurve,
			system: unavailable ? undefined : systemCurve,
			project,
			solved: solvedProject ?? labels,
			prefs
		})
	);
	/** Refused only for an active PRV or PSV inside: a station, whose group curve is not defined. */
	const undefinedThere = $derived(
		groupCurve?.status === 'refused' && pressureControlOnly(groupCurve.issues)
	);
	const refusals = $derived(
		groupCurve?.status === 'refused' && !unavailable
			? groupCurve.issues.map((issue) => ({
					issue,
					words: refusalWords(issue, memberIds, project, {
						solved: solvedProject ?? labels,
						boxes: pumps.map((p) => p.id)
					})
				}))
			: []
	);
	const arrangement = $derived(stationShown?.station.arrangement ?? null);
	const memberNames = $derived(
		(stationShown ? stationShown.station.memberIds : [...memberIds].sort(byTable)).map(nameOf)
	);
	function byTable(a: string, b: string) {
		return pumps.findIndex((p) => p.id === a) - pumps.findIndex((p) => p.id === b);
	}
	const caption = $derived(
		`${groupCaption(memberNames, arrangement)}${caseName ? `, ${caseName}` : ''}${stale ? ' (out of date)' : ''}`
	);
	const summary = $derived(groupSummary(data, members, shown, project, systemShown));
	const legend = $derived(groupLegend(data));
	const table = $derived(groupTable(members, nodes, stationShown, prefs, project));
	const samples = $derived(
		shown ? groupSampleRows(shown, shown.station.memberIds, prefs, project) : []
	);
	/** The group system curve's rows: its reasons told with names and each element's rule. */
	const systemRows = $derived(
		systemShown
			? groupSystemRows(systemShown, prefs, { project, solved: solvedProject ?? labels })
			: []
	);
	const loading = $derived(groupCurve?.status === 'loading' && !unavailable);
	const systemLoading = $derived(systemCurve?.status === 'loading' && !unavailable);

	/** "Read along the curves": the group curve's samples, in rise order. */
	const readout = $derived(shown ? groupReadout(shown, nameOf, prefs) : []);
	const dutyIndex = $derived(readout.findIndex((r) => r.duty));
	/** The sample the user moved to, for this response (else the duty's, else the first). */
	// Raw: the response is compared by identity (a deep proxy would never equal it).
	let reading = $state.raw<{ response: unknown; index: number } | null>(null);
	const moved = $derived(reading !== null && reading.response === shown);
	const readIndex = $derived(
		moved ? Math.min(reading!.index, readout.length - 1) : dutyIndex >= 0 ? dutyIndex : 0
	);
	const readSample = $derived(readout[readIndex] ?? null);
	const readText = $derived(
		readSample ? `${readSample.text}${readSample.duty ? " (the duty's rise)" : ''}` : ''
	);
	/** Marked on the chart once the user reads along (the duty's points are drawn already). */
	const mark = $derived<GroupReadoutMark | null>(moved ? (readSample?.mark ?? null) : null);
	const fmt = (v: number) => formatNumber(v, 4);

	const phone = mediaQuery('(max-width: 639px)');
	const heightRem = $derived(chartHeightRem(['head'], phone.current));

	let figure: HTMLElement | undefined = $state();
	/** "Read along the curves": focus returns here from "Back to the duty", which then goes. */
	let readSlider: HTMLInputElement | undefined = $state();
	let cancelButton: HTMLButtonElement | undefined = $state();
	let retryButton: HTMLButtonElement | undefined = $state();
	let systemCancelButton: HTMLButtonElement | undefined = $state();
	let systemRetryButton: HTMLButtonElement | undefined = $state();
	let canvas: HTMLCanvasElement | undefined = $state();
	let noCanvas = $state(false);
	let showTable = $state(false);
	let loadFailed = $state(false);
	const tableShown = $derived(showTable || noCanvas || loadFailed);

	// From Cancel to the button that computes the curve again (or the figure), and back.
	$effect.pre(() => {
		if (loading) return;
		const cancel = untrack(() => cancelButton);
		if (!cancel || document.activeElement !== cancel) return;
		void tick().then(() => (retryButton ?? figure)?.focus());
	});
	$effect.pre(() => {
		if (!loading) return;
		const retry = untrack(() => retryButton);
		if (!retry || document.activeElement !== retry) return;
		void tick().then(() => (cancelButton ?? figure)?.focus());
	});
	// The same for the group system curve's Cancel and retry.
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
						readout: () => markNow
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

	/** Why no image can be made now ('' when it can). */
	const imageReason = $derived(
		!image
			? ''
			: image.unavailable ||
					(loading
						? 'Wait until the group curve is computed, or cancel it.'
						: systemLoading
							? 'Wait until the group system curve is computed, or cancel it.'
							: !drawn
								? 'The chart is being drawn.'
								: '')
	);
	let makingImage = false;

	/** The chart drawn again at a fixed size with its caption and notes, as a PNG. */
	async function downloadImage() {
		const module = chartModule;
		if (!image || !module || imageReason || makingImage) return;
		makingImage = true;
		const { Chart, downloadChartImage, pumpGroupConfig } = module;
		await downloadChartImage(Chart, {
			config: pumpGroupConfig(data, {
				legendLabels: Chart.defaults.plugins.legend.labels.generateLabels,
				format: fmt,
				forImage: true
			}),
			title: groupImageTitle(memberNames, arrangement),
			lines: groupNoteLines(
				notes,
				refusals.map((r) => wordsText(r.words))
			),
			content: `Pumps together ${memberNames.join(', ')}`,
			...(caseName ? { caseName } : {}),
			disclaimer: DISCLAIMER,
			source: image
		});
		makingImage = false;
	}
</script>

{#snippet words(list: ReturnType<typeof refusalWords>)}
	{#each list as word, i (i)}{#if typeof word === 'string'}{word}{:else if oninspect}<button
				type="button"
				class="inline min-h-0 px-0.5 text-blue-800 underline underline-offset-2"
				onclick={() => oninspect(word.id)}>{word.name}</button
			>{:else}{word.name}{/if}{/each}
{/snippet}

<section class="card space-y-3 p-3" aria-labelledby="{id}-heading">
	<h3 id="{id}-heading" class="text-sm font-semibold">
		<button
			type="button"
			class="flex min-h-11 w-full items-center gap-2 text-left"
			aria-expanded={open}
			aria-controls="{id}-body"
			onclick={() => (open = !open)}
		>
			<Icon name="right" class={['size-4 shrink-0 transition-transform', open && 'rotate-90']} />
			Pumps together
			{#if !open && memberNames.length}<span class="text-xs font-normal text-slate-600"
					>({memberNames.join(', ')})</span
				>{/if}
		</button>
	</h3>
	{#if open}
		<div id="{id}-body" class="space-y-3">
			<fieldset bind:this={fieldset} class="space-y-1">
				<legend class="text-xs font-medium text-slate-700">Pumps in the group</legend>
				<div class="flex flex-wrap gap-x-4">
					{#each pumps as pump (pump.id)}
						{@const on = ticked(pump.id)}
						{@const capped = !on && full}
						{@const slot = slots.indexOf(pump.id)}
						<label class="flex min-h-11 items-center gap-2 text-sm">
							<input
								type="checkbox"
								class="size-4"
								checked={on}
								aria-disabled={capped}
								aria-describedby={capped ? `${id}-full` : undefined}
								onclick={(event) => {
									if (capped) {
										event.preventDefault();
										return;
									}
									setTicked(pump.id, event.currentTarget.checked);
								}}
							/>
							{#if on}<span aria-hidden="true" style:color={slotStyle(slot).color}
									>{slotStyle(slot).symbol}</span
								>{/if}
							{pump.name}
						</label>
					{/each}
				</div>
				{#if full && pumps.length > MAX_GROUP_PUMPS}
					<p id="{id}-full" class="hint">At most {MAX_GROUP_PUMPS} pumps in a group.</p>
				{/if}
				<p class="hint">
					The calculation server finds the part of the network that holds them, between two places
					(its inlet and outlet), and whether they are in parallel or in series.
				</p>
			</fieldset>
			{#if others.length}
				<div bind:this={alsoFound} class="flex flex-wrap items-center gap-x-2">
					{#each others as other (other.pumpIds.join('\u0000'))}
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							onclick={() => showSuggestion(other.pumpIds)}
							>Also found: {andList(other.pumpIds.map(nameOf))}</button
						>
					{/each}
				</div>
			{/if}

			{#if unavailable}
				<p class="text-sm text-slate-700">{unavailable}</p>
			{:else if members.length}
				<figure
					bind:this={figure}
					class="space-y-2"
					aria-labelledby="{id}-caption"
					aria-busy={loading || systemLoading}
					tabindex="-1"
				>
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
						>
							<canvas bind:this={canvas} aria-hidden="true"></canvas>
						</div>
						<!-- The legend under the chart, so the plot keeps the panel's height on a phone. -->
						<ul class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-800" aria-label="Legend">
							{#each legend as item (item.key)}
								<li class="flex items-center gap-1.5">
									{#if item.kind === 'line'}
										<svg width="24" height="8" aria-hidden="true" class="shrink-0"
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
					{:else}
						<p class="text-sm text-slate-700">
							The chart cannot be drawn in this browser. The tables below list its points.
						</p>
					{/if}
					{#if readSample}
						<!-- Read along the curves: the group curve's samples, each read from the response. -->
						<div class="space-y-1">
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
							<p class="text-xs text-slate-700 tabular-nums" data-group-readout>{readText}</p>
							<p id="{id}-read-hint" class="hint">
								Steps over the group curve's samples, each pump's flow and the station's as computed
								at that rise (nothing between samples is read).
							</p>
						</div>
					{/if}
					<!-- One live region for both curves' progress (never computed at once). -->
					<div role="status" class="text-xs text-slate-600">
						{#if notes.curve?.kind === 'loading'}
							<span id="{id}-curve-state">{notes.curve.text}</span>
						{:else if notes.systemCurve?.kind === 'loading'}
							<span id="{id}-system-state">{notes.systemCurve.text}</span>
						{/if}
					</div>
					{#if notes.curve?.kind === 'loading' && oncancel}
						<button
							bind:this={cancelButton}
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							aria-label="Cancel the group curve"
							onclick={oncancel}>Cancel</button
						>
					{:else if notes.curve?.kind === 'error' || notes.curve?.kind === 'cancelled'}
						<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
							<p
								id="{id}-curve-state"
								class={[
									'text-xs',
									notes.curve.kind === 'error' ? 'text-red-800' : 'text-slate-600'
								]}
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
									{notes.curve.kind === 'error' ? 'Try again' : 'Compute the group curve'}
								</button>
							{/if}
						</div>
					{:else if notes.curve?.kind === 'refused'}
						<div class="space-y-1 text-sm" data-group-refusal>
							<p class="font-medium">{notes.curve.text}</p>
							<ul
								class="list-disc space-y-1 pl-5"
								aria-label={undefinedThere
									? 'Why the group curve is not defined'
									: 'Why they do not form a station'}
							>
								{#each refusals as refusal, i (i)}
									<li>
										{@render words(refusal.words)}
										<IssueDetail detail={refusal.issue.message} />
									</li>
								{/each}
							</ul>
						</div>
					{:else if notes.curve}
						<p class="text-xs text-slate-700">{notes.curve.text}</p>
					{/if}
					<!-- The group system curve's state: asked for after the group curve's answer. -->
					{#if notes.systemCurve?.kind === 'loading' && oncancelsystem}
						<button
							bind:this={systemCancelButton}
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							aria-label="Cancel the group system curve"
							onclick={oncancelsystem}>Cancel</button
						>
					{:else if notes.systemCurve?.kind === 'error' || notes.systemCurve?.kind === 'cancelled'}
						<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
							<p
								id="{id}-system-state"
								class={[
									'text-xs',
									notes.systemCurve.kind === 'error' ? 'text-red-800' : 'text-slate-600'
								]}
							>
								{notes.systemCurve.text}
							</p>
							{#if onretrysystem}
								<button
									bind:this={systemRetryButton}
									type="button"
									class="btn btn-quiet px-2 text-blue-800"
									aria-describedby="{id}-system-state"
									onclick={onretrysystem}
								>
									{notes.systemCurve.kind === 'error'
										? 'Try the group system curve again'
										: 'Compute the group system curve'}
								</button>
							{/if}
						</div>
					{:else if notes.systemCurve}
						<p class="text-xs text-slate-700">{notes.systemCurve.text}</p>
					{/if}
					{#if notes.frame}<p class="text-xs text-slate-700">{notes.frame}</p>{/if}
					{#if notes.system}<p class="text-xs text-slate-700">{notes.system}</p>{/if}
					<p class="text-xs text-slate-600">{notes.axes}</p>
					{#each notes.duty as note, i (note)}
						<p class="text-xs text-slate-600">
							{note}{#if i === 0 && shown?.dutyCheck && !shown.dutyCheck.agrees}<IssueDetail
									detail={shown.dutyCheck.message}
								/>{/if}
						</p>
					{/each}
					{#each notes.systemDuty as note, i (note)}
						<p class="text-xs text-slate-600">
							{note}{#if i === 0 && systemShown?.systemDutyCheck && !systemShown.systemDutyCheck.agrees}<IssueDetail
									detail={systemShown.systemDutyCheck.message}
								/>{/if}
						</p>
					{/each}
					{#each notes.members as note (note)}
						<p class="text-xs text-slate-600">{note}</p>
					{/each}
					{#if notes.dashed}<p class="text-xs text-slate-600">{notes.dashed}</p>{/if}
					<p class="text-xs text-slate-600">{notes.systemCurves}</p>
					{#if shown}
						<details class="group text-xs">
							<summary
								class="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
							>
								<Icon
									name="right"
									class="size-3 shrink-0 transition-transform group-open:rotate-90"
								/>
								{systemShown ? 'How the group curve is computed' : 'How this curve is computed'}
							</summary>
							<div class="space-y-1 text-slate-700">
								<p class="font-medium">
									{shown.methods.title} (calculation methods {shown.methodVersion})
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
						<details class="group text-xs">
							<summary
								class="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
							>
								<Icon
									name="right"
									class="size-3 shrink-0 transition-transform group-open:rotate-90"
								/>
								How the group system curve is computed
							</summary>
							<div class="space-y-1 text-slate-700">
								<p class="font-medium">
									{systemShown.methods.title} (calculation methods {systemShown.methodVersion})
								</p>
								{#each systemShown.methods.items as item, i (i)}<p class="break-words">
										{item}
									</p>{/each}
								{#if systemShown.methods.references.length}
									<p class="font-medium">References</p>
									<ul class="list-disc pl-5">
										{#each systemShown.methods.references as reference, i (i)}<li
												class="break-words"
											>
												{reference}
											</li>{/each}
									</ul>
								{/if}
							</div>
						</details>
					{/if}
				</figure>

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
									class="border-b border-slate-300 px-2 py-1 text-left align-bottom font-medium"
									>Flags</th
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
												><span aria-hidden="true" style:color={row.style.color}
													>{row.style.symbol}</span
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
						{#each table.footer as line (line.label)}
							<div>
								<dt class="inline">{line.label}:</dt>
								<dd class="inline font-medium tabular-nums">{line.value}</dd>
							</div>
						{/each}
					</dl>
				{/if}
				{#if !shown && groupCurve?.status !== 'refused' && members.length > 1}
					<p class="text-xs text-slate-600">
						The share of each pump and its loss on the way come with the group curve.
					</p>
				{/if}

				{#if !noCanvas && !loadFailed}
					<div class="flex flex-wrap items-center gap-x-3">
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							aria-expanded={tableShown}
							aria-controls="{id}-data"
							onclick={() => (showTable = !showTable)}
						>
							{tableShown ? 'Hide data table' : 'Show data table'}
						</button>
						{#if image}
							<button
								type="button"
								class="btn btn-quiet px-2 text-blue-800"
								data-chart-image
								aria-label="Download image of the pumps together: {memberNames.join(', ')}{caseName
									? `, ${caseName}`
									: ''}"
								aria-disabled={!!imageReason}
								aria-describedby={imageReason ? `${id}-image-reason` : undefined}
								title={imageReason || undefined}
								onclick={() => void downloadImage()}
							>
								<Icon name="download" class="size-4" /> Download image
							</button>
							{#if imageReason}<span id="{id}-image-reason" class="sr-only">{imageReason}</span
								>{/if}
						{/if}
					</div>
				{/if}
				{#if tableShown}
					<div id="{id}-data" class="space-y-3">
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
										<th scope="col" class="px-2 py-1 text-right font-medium"
											>Flow ({data.flowUnit})</th
										>
										<th scope="col" class="px-2 py-1 text-right font-medium"
											>Head ({data.headUnit})</th
										>
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
								<span class="tabular-nums">{fmt(data.station.flow)} {data.flowUnit}</span> at a rise
								of
								<span class="tabular-nums">{fmt(data.station.point.y)} {data.headUnit}</span>; {ARRANGEMENT_WORDS[
									stationShown.station.arrangement
								]}.
								{#if shown?.dutyCheck}
									Duty check: {dutyCheckState(shown)}{shown.dutyCheck.flow === null
										? ''
										: `; ${dutyCheckWords(shown, nameOf, prefs)}`}.<IssueDetail
										detail={shown.dutyCheck.message}
									/>
								{/if}
								{#if systemShown?.systemDutyCheck}
									System duty check: {systemDutyCheckState(systemShown)}.<IssueDetail
										detail={systemShown.systemDutyCheck.message}
									/>
								{/if}
							</p>
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
													<td class="px-2 py-1 text-xs whitespace-nowrap text-slate-600"
														>{m.state}</td
													>
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
														.join(' ')}{#if row.detail}<IssueDetail detail={row.detail} />{/if}</td
												>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
					</div>
				{/if}
			{:else}
				<p class="text-sm text-slate-700">Tick the pumps to see together.</p>
			{/if}
		</div>
	{/if}
</section>
