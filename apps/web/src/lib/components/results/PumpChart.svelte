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
	lists the operating points by case. The choice is the page's, one for this list and the Pumps
	together card's (proposal pumps-results-layout.md §9 S8): `unticked` and `ontick`. A case in
	which this pump is off takes no slot while their system curves are not asked for: it has no box,
	and a line under the list names it. Each marker is fixed by case (`markers`).

	Design checks (CLAUDE.md D19): with checks on, a chip shows their limits: the preferred and
	allowable operating regions shaded under the curves, the minimum flow, the NPSHa the NPSH margin
	check requires and the motor's rating, each told in a note. Never the verdicts: Results →
	Checks has those.
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
		checksDrawn,
		loadHiddenPanels,
		loadTableShown,
		caseMarkers,
		MARKER_SYMBOLS,
		MAX_CHART_CASES,
		offCasesNote,
		otherCasesData,
		pumpChartCases,
		CHIP_LABELS,
		PANEL_LABELS,
		pumpChartData,
		pumpLine,
		saveHiddenPanels,
		saveTableShown,
		valueNotes,
		type CaseMarker,
		type ChipKey,
		type OtherCaseInput,
		type PanelKey,
		type PumpChecksInput,
		type SystemCurveNames
	} from '$lib/utils/pump-chart';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import { scrollRegion } from '$lib/utils/scroll-focus';
	import Icon from '$lib/components/ui/Icon.svelte';
	import CurveTable from './CurveTable.svelte';
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
		/** The design checks as solved (D19), whose limits the chart can show. */
		checks?: PumpChecksInput | null;
		/** The pump's system curve for the same solve (undefined: not requested). */
		system?: SystemCurveState;
		/** Compute the system curve (again, after a failure or a cancellation). */
		onretry?: () => void;
		/** Cancel the system curve while it is computed. */
		oncancel?: () => void;
		/** Open the pump's trace, which defines the system curve (H_sys) among its equations. */
		ontrace?: () => void;
		/**
		 * Show the Results view Checks, with the focus on its tab: the verdicts of the design
		 * checks whose limits the chart draws (pumps-results-layout.md §5.3, D19).
		 */
		onchecks?: () => void;
		/** Another pump of the solve is speed-controlled and on: it keeps regulating in the system curve. */
		othersControlled?: boolean;
		/** The case shown, in a project with scenarios ("Winter"): the caption names it. */
		caseName?: string;
		/** Other cases with a result for this pump (their system curve when computed). */
		others?: readonly OtherCaseInput[];
		/**
		 * The other cases not to draw (keys): those the user unticked, under this list or the card's,
		 * and those past this chart's cap at an untick (pumps-results-layout.md §9 S8, page state).
		 */
		unticked?: readonly string[];
		/** Each case drawn's marker, fixed by case (pump-chart.ts caseMarkers); by default its place's. */
		markers?: Readonly<Record<string, CaseMarker>>;
		/** Tick or untick another case: the page's one choice of cases (§9 S8). */
		ontick?: (key: string, on: boolean) => void;
		/** The other cases' system curves: requested (true) or not. */
		overlayCurves?: boolean;
		/** Request or drop the other cases' system curves, for the other cases the chart draws. */
		onoverlay?: (on: boolean) => void;
		/** Overlay curves being computed: how many of how many (null: none). */
		overlayProgress?: { done: number; total: number } | null;
		/** Cancel the overlay curves still being computed. */
		oncanceloverlay?: () => void;
		/**
		 * What an image of the chart names and whether one can be made of these results (proposal
		 * export.md §5.5): without it, no Download image is offered.
		 */
		image?: ChartImageSource;
		/**
		 * The canvas, or what stands in its place (bindable): the Pumps tab's section nav pins only
		 * once it has scrolled out (proposal pumps-results-layout.md §5.4 Place).
		 */
		canvasArea?: HTMLElement | null;
	}

	let {
		result,
		name,
		prefs,
		ratedRange = null,
		names = null,
		checks = null,
		system,
		onretry,
		oncancel,
		ontrace,
		onchecks,
		othersControlled = false,
		caseName,
		others = [],
		unticked = [],
		markers,
		ontick,
		overlayCurves = false,
		onoverlay,
		overlayProgress = null,
		oncanceloverlay,
		image,
		canvasArea = $bindable(null)
	}: Props = $props();
	const id = $props.id();

	/**
	 * The cases with a box, those drawn (at most MAX_CHART_CASES - 1) and those that take no slot,
	 * by the page's choice (pumps-results-layout.md §9 S8 Slots).
	 */
	const cases = $derived(pumpChartCases(others, unticked, overlayCurves));
	const shownOthers = $derived(cases.shown);
	const shownKeys = $derived(new Set(shownOthers.map((o) => o.key)));
	/**
	 * Each case drawn's marker: the page's, else each its place's among the cases with a result
	 * while they are five or fewer, else among those listed (§9 S8 Markers, caseMarkers).
	 */
	const caseMarker = $derived(
		markers ??
			caseMarkers(
				shownOthers.map((o) => o.key),
				cases.listed.map((o) => o.key),
				{},
				others.map((o) => o.key)
			)
	);
	const otherData = $derived(
		otherCasesData(
			shownOthers,
			prefs,
			ratedRange?.[0] != null && ratedRange?.[1] != null ? [ratedRange[0], ratedRange[1]] : null,
			result.speed,
			names,
			caseMarker
		)
	);
	/**
	 * "Off in this case (no operating point): …", for the cases that take no slot (§6.2 S8): under
	 * the list on screen, and in the image's footer.
	 */
	const offNote = $derived(
		offCasesNote(cases.off.map((o) => (o.stale ? `${o.name} (out of date)` : o.name)))
	);

	/** The nearest ancestor that scrolls down (the Results pane's scroller), else the page's. */
	function scrollerOf(node: HTMLElement): Element {
		for (let el = node.parentElement; el; el = el.parentElement) {
			const y = getComputedStyle(el).overflowY;
			if ((y === 'auto' || y === 'scroll') && el.scrollHeight > el.clientHeight) return el;
		}
		return document.scrollingElement ?? document.documentElement;
	}
	/**
	 * The switch held at the place it was pressed while the curves that press asked for arrive
	 * (S8 second check LAYOUT-2): `keep` scrolls it back, `end` lets it go. Not reactive.
	 */
	let held: { keep: () => void; end: () => void } | null = null;
	/** The user's own next step, whatever it is: a press, a key, a wheel or a touch ends a hold. */
	const OWN_STEPS = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const;
	/**
	 * "Also show the other cases' system curves" keeps its place under the pointer (ui-guide, a
	 * press moves nothing under the pointer; S8 review LAYOUT-1): switching the curves changes the
	 * boxes above it, since a case in which this pump is off has a box and a slot only while they
	 * are on (pumps-results-layout.md §9 S8 Slots). So its scroller scrolls by what it moved, as a
	 * pressed heading's box does (ResultsTable pressHeading); where the browser already kept it in
	 * place (scroll anchoring) it moved nothing, and nothing scrolls. With the data table shown,
	 * each curve the press asked for adds its table above the switch as it answers (§5.3 The data
	 * region), so while they are computed the switch is held (S8 second check LAYOUT-2): each
	 * change of the figure's size scrolls it back, before it is painted, until the last curve
	 * has answered or the user takes a step of their own (then a press lands where they aim).
	 */
	async function switchOverlay(input: HTMLInputElement) {
		const before = input.getBoundingClientRect().top;
		const keep = () => {
			if (!input.isConnected) return;
			const moved = input.getBoundingClientRect().top - before;
			if (Math.abs(moved) > 0.5) scrollerOf(input).scrollTop += moved;
		};
		onoverlay?.(input.checked);
		await tick();
		keep();
		const figure = input.closest('figure');
		if (!input.checked || !overlayProgress || !figure || !input.isConnected) return;
		if (typeof ResizeObserver === 'undefined') return;
		const observer = new ResizeObserver(keep);
		observer.observe(figure);
		const end = () => {
			observer.disconnect();
			for (const type of OWN_STEPS) window.removeEventListener(type, end, true);
			if (held?.end === end) held = null;
		};
		for (const type of OWN_STEPS)
			window.addEventListener(type, end, { capture: true, passive: true });
		held = { keep, end };
	}
	// The last curve answered (or the rest cancelled): its table is drawn, so keep the switch in
	// place once more and let it go.
	$effect(() => {
		if (overlayProgress) return;
		untrack(() => {
			held?.keep();
			held?.end();
		});
	});
	// Another pump shown, or the chart gone: nothing more to hold.
	$effect(() => () => held?.end());

	// The range as numbers, so a new array with the same values does not rebuild the chart.
	const low = $derived(ratedRange?.[0] ?? null);
	const high = $derived(ratedRange?.[1] ?? null);
	const curve = $derived(system?.status === 'ready' ? system.curve : null);
	const data = $derived(
		pumpChartData(
			result,
			prefs,
			low !== null && high !== null ? [low, high] : null,
			curve,
			names,
			checks
		)
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
	const checksShown = $derived(!!data.checks && !hidden.includes('checks'));
	const chips = $derived([
		...data.panels.filter((p): p is Exclude<PanelKey, 'head'> => p !== 'head'),
		...(data.facts.speedRange ? (['speed'] as const) : []),
		...(data.checks ? (['checks'] as const) : [])
	]);
	const isShown = (key: ChipKey) =>
		key === 'speed' ? speedShown : key === 'checks' ? checksShown : shown.includes(key as PanelKey);
	function togglePanel(key: ChipKey) {
		hidden = hidden.includes(key) ? hidden.filter((p) => p !== key) : [...hidden, key];
		saveHiddenPanels(hidden);
	}
	/**
	 * A chip stays under the pointer (ui-guide, a press moves nothing under the pointer; the owner's
	 * nits of 2026-11-12, item 1, docs/proposals/pumps-nits.md): a panel's chip makes the canvas
	 * above it a panel taller or shorter (chartHeightRem), so once the press is drawn its scroller
	 * scrolls by what the chip moved, as switchOverlay does; a press from the keyboard too. Where the
	 * browser already kept it in place (scroll anchoring) it moved nothing, and nothing scrolls.
	 */
	async function pressChip(button: HTMLButtonElement, key: ChipKey) {
		const before = button.getBoundingClientRect().top;
		togglePanel(key);
		await tick();
		if (!button.isConnected) return;
		const moved = button.getBoundingClientRect().top - before;
		if (Math.abs(moved) > 0.5) scrollerOf(button).scrollTop += moved;
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
	let readSlider: HTMLInputElement | undefined = $state();
	/**
	 * Back to the duty: the button goes as it is pressed, so the focus moves to the slider it
	 * belongs to (pumps-results-layout.md F40, §7 Focus), as on the group chart.
	 */
	function backToDuty() {
		cursor = null;
		void tick().then(() => readSlider?.focus());
	}
	let cancelButton: HTMLButtonElement | undefined = $state();
	/** The button that computes the curve again (failed, cancelled or not computed). */
	let retryButton: HTMLButtonElement | undefined = $state();
	let canvas: HTMLCanvasElement | undefined = $state();
	let unavailable = $state(false);
	/** The data table shown: remembered in this browser (pumps-results-layout.md §9 S7). */
	let showTable = $state(loadTableShown('pump'));
	function toggleTable() {
		showTable = !showTable;
		saveTableShown('pump', showTable);
	}

	/** The chart chunk could not be loaded (a redeploy, or a dropped connection): the table is shown. */
	let loadFailed = $state(false);
	/** No chart: the data region is shown, and every curve table in it open (§9 S7). */
	const cannotDraw = $derived(unavailable || loadFailed);
	const tableShown = $derived(showTable || cannotDraw);
	/**
	 * The curve tables the user opened or closed, by table: kept while the data region is hidden
	 * and shown again (§9 S7).
	 */
	let tablesOpen = $state<Record<string, boolean | undefined>>({});

	const fmt = (v: number) => formatNumber(v, 4);
	const markerOf = (key: string) => otherData.find((o) => o.key === key)?.marker;
	const off = $derived(result.status === 'off');
	/**
	 * "Operating points by case" (pumps-results-layout.md §5.3, the data region): the case shown
	 * first, then the other cases drawn, each with its marker; the speed a bare number under
	 * "Speed (%)" ("—" for an off pump).
	 */
	const caseRows = $derived([
		{
			key: '',
			shown: true,
			marker: null,
			label: `${caseName ?? 'This case'} (shown)`,
			flow: data.operating ? fmt(data.operating.x) : data.held ? '0' : '—',
			head: data.operating ? fmt(data.operating.y) : data.held ? fmt(data.held.y) : '—',
			speed: off ? '—' : formatNumber(result.speed * 100, 4),
			state: off ? 'Off' : data.held ? 'Held at zero flow' : 'Running'
		},
		...otherData.map((o) => ({
			key: o.key,
			shown: false,
			marker: MARKER_SYMBOLS[o.marker],
			label: o.label,
			...o.row
		}))
	]);
	/** An element id for another case ('' is the base case). */
	const caseId = (key: string) => key || 'base';
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
		const otherPoints = otherData.length
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
		const limits =
			checksShown && checksDrawn(data, shown)
				? "; with the design checks' limits, which the notes below list"
				: '';
		return `${parts.join(' and ')}${at}${extrapolated}${best}${panels}${speeds}${limits}${otherPoints}.`;
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
	const notes = $derived(
		chartNotes({ data, result, system, othersControlled, shown, speedShown, checksShown })
	);
	/** The notes about the values, in the screen's order (pumps-results-layout.md §5.3). */
	const valued = $derived(valueNotes(notes, data));
	/** The system curve's request line: being computed, failed, or not computed (the strip's). */
	const curveState = $derived(notes.curve?.kind === 'missing' ? null : notes.curve);
	/**
	 * The live lines are drawn empty before their progress is said (pumps-results-layout.md §7 Live
	 * regions, F17): PumpsView mounts the chart in the flush that starts its system curve (the
	 * Pumps tab opened, a pump chosen), and a polite line inserted already holding its words is not
	 * announced. Two frames: the first one's callbacks run before it draws the empty lines.
	 */
	let linesDrawn = $state(false);
	$effect(() => {
		let frame = requestAnimationFrame(() => {
			frame = requestAnimationFrame(() => (linesDrawn = true));
		});
		return () => cancelAnimationFrame(frame);
	});
	/** What the system curve's line says: its progress once the line has been drawn empty. */
	const curveLine = $derived(curveState?.kind === 'loading' && !linesDrawn ? null : curveState);
	/** What the other cases' line says, on the same rule. */
	const overlayLine = $derived(linesDrawn ? overlayProgress : null);
	/** The points without a head, a plain line after the request's (§5.2: no mark on a fact). */
	const coverage = $derived(notes.curve?.kind === 'missing' ? notes.curve.text : null);
	/** The strip has nothing to show: it takes no room (its live line stays, empty). */
	const stripIdle = $derived(!notes.pump && !curveLine && !coverage);

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
		const drawnCases = otherData;
		const panels = shown;
		const speedRange = speedShown;
		const checkLimits = checksShown;
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
					pumpChartConfig(d, drawnCases, {
						speedText: speed,
						legendLabels: Chart.defaults.plugins.legend.labels.generateLabels,
						format: fmt,
						panels,
						speedRange,
						checks: checkLimits,
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
	/**
	 * The results' own reason (not converged, a failed solve shown, a calculation), which lasts:
	 * shown beside the button. A passing one (a curve computed, the chart drawn) changes on every
	 * redraw, so it stays visually hidden and in the title (pumps-results-layout.md §5.3, Actions).
	 */
	const imageLasting = $derived(!!image?.unavailable);
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
				speedRange: speedShown,
				checks: checksShown
			}),
			notes: chartNotes({
				data,
				result,
				system,
				othersControlled,
				reasonsIn: IMAGE_REASONS_IN,
				shown,
				speedShown,
				checksShown
			}),
			others: otherData,
			markerSymbols: MARKER_SYMBOLS,
			offCases: offNote,
			pumpName: name,
			...(caseName ? { caseName } : {}),
			disclaimer: DISCLAIMER,
			source: image
		});
		makingImage = false;
	}
</script>

<!--
	One anatomy (proposal pumps-results-layout.md §5.1, §5.3 item 2): the caption, the canvas, the
	reading controls, the strip of the system curve's request, the actions, the notes about the
	values, the data region, then the other cases under their own heading. `aria-busy` is the
	canvas's, the part that is redrawn, so no live line below has a busy ancestor (§5.3 markup
	rules, §7).
-->
<figure bind:this={figure} class="space-y-2" aria-labelledby="{id}-caption" tabindex="-1">
	<!-- Its words wrap, a 40-character unbroken name too, as the group chart's figcaption (§7
		Targets: text reflows at 320 px; S7 review LAYOUT-5). -->
	<figcaption id="{id}-caption" class="text-sm font-medium wrap-break-word">
		Pump and system curves: {name}{caseName ? `, ${caseName}` : ''}
	</figcaption>
	{#if loadFailed}
		<p bind:this={canvasArea} class="text-sm text-slate-700" role="alert">
			{STALE_CHUNK_MESSAGE} The table below lists its points.
		</p>
	{:else if !unavailable}
		<div
			bind:this={canvasArea}
			class="relative w-full"
			style:height="{heightRem}rem"
			role="img"
			aria-label={summary}
			aria-busy={loading}
			onpointermove={pointerRead}
			onpointerdown={pointerRead}
		>
			<canvas bind:this={canvas} aria-hidden="true"></canvas>
		</div>
		{#if chips.length}
			<!-- Toggle chips (§5.3, Reading): filled with a checked box when on, outlined with an empty
				box when off, the 16 px mark first in both, so a press changes no chip's width and the
				row never rewraps (pumps-nits.md item 1). -->
			<div role="group" aria-label="Show" class="flex flex-wrap items-center gap-2">
				<span class="text-xs font-medium text-slate-700" aria-hidden="true">Show</span>
				{#each chips as chip (chip)}
					{@const on = isShown(chip)}
					<button
						type="button"
						class={['btn px-3', on && 'border-blue-700 bg-blue-50 text-blue-900 hover:bg-blue-100']}
						aria-pressed={on}
						onclick={(event) => void pressChip(event.currentTarget, chip)}
						><Icon
							name={on ? 'box-check' : 'box'}
							class={['size-4 shrink-0', on ? 'text-blue-700' : 'text-slate-500']}
						/>{CHIP_LABELS[chip]}</button
					>
				{/each}
			</div>
		{/if}
		{#if xMax > 0}
			<!-- A container: the readout's pairs go two-up from 26 rem, one per line below (§5.5). -->
			<div class="@container space-y-1">
				<div class="flex flex-wrap items-center gap-x-3">
					<label for="{id}-read" class="text-xs font-medium text-slate-700">Read at flow</label>
					<input
						bind:this={readSlider}
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
						<button type="button" class="btn btn-quiet px-2 text-blue-800" onclick={backToDuty}
							>Back to the duty</button
						>
					{/if}
				</div>
				{#if readAt !== null}
					<!-- One paragraph, not live (pump-chart.md §4.3): each pair kept on one line, the
						separators visually hidden, so its text reads as one sentence (§5.3, Reading). -->
					<p
						data-pump-readout
						class="grid grid-cols-1 gap-x-4 text-sm tabular-nums @min-[26rem]:grid-cols-2"
					>
						<span class="col-span-full font-medium"
							>{cursor === null ? 'At the duty' : 'At'} {fmt(readAt)} {data.flowUnit}:</span
						>
						{#each readout as item, i (item.key)}<span class="whitespace-nowrap"
								>{#if i}<span class="sr-only">,&nbsp;</span>{/if}<span class="text-slate-600"
									>{item.label}</span
								>
								<span class="font-medium">{fmt(item.value)} {item.unit}</span></span
							>{:else}<span>no line is drawn at this flow</span>{/each}
					</p>
				{/if}
			</div>
		{/if}
	{:else}
		<p bind:this={canvasArea} class="text-sm text-slate-700">
			The chart cannot be drawn in this browser. The table below lists its points.
		</p>
	{/if}
	<!--
		The strip (§5.3, The strip): the pump's state, then the system curve's request, one row: an
		always-present polite line, empty when idle and never role=status (a pane-wide status query
		finds the Results header's alone, §5.3 markup rules), drawn empty before its first progress
		(linesDrawn, §7), its mark at its first line however its sentence wraps (§5.2), its button
		after it and described by it; then the points' coverage, plain. Visually hidden while it has
		nothing to say, so it takes no room, its line still in the accessibility tree.
	-->
	<div data-pump-strip class={['space-y-1', stripIdle && 'sr-only']}>
		{#if notes.pump}
			<p class="text-xs text-slate-700">{notes.pump}</p>
		{/if}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<span
				id="{id}-curve-state"
				aria-live="polite"
				aria-atomic="true"
				class={[
					'inline-flex items-start gap-1.5 text-xs',
					curveLine?.kind === 'error' ? 'text-red-800' : 'text-slate-700'
				]}
				>{#if curveLine?.kind === 'loading'}<Icon
						name="spinner"
						class="mt-px size-3.5 shrink-0 text-slate-500 motion-safe:animate-spin"
					/>{:else if curveLine?.kind === 'error'}<Icon
						name="octagon"
						class="mt-px size-3.5 shrink-0 text-red-700"
					/>{/if}{curveLine?.text ?? ''}</span
			>
			{#if curveState?.kind === 'loading' && oncancel}
				<button
					bind:this={cancelButton}
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-label="Cancel the system curve"
					aria-describedby="{id}-curve-state"
					onclick={oncancel}
				>
					Cancel
				</button>
			{:else if (curveState?.kind === 'error' || curveState?.kind === 'cancelled') && onretry}
				<button
					bind:this={retryButton}
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-describedby="{id}-curve-state"
					onclick={onretry}
				>
					{curveState.kind === 'error' ? 'Try again' : 'Compute the system curve'}
				</button>
			{/if}
		</div>
		{#if coverage}
			<p class="text-xs text-slate-700">{coverage}</p>
		{/if}
	</div>
	{#if !unavailable && !loadFailed}
		<!-- Actions (§5.3): the names told apart from the group chart's by a visually hidden
			suffix; a lasting reason why no image can be made shown, a passing one hidden. -->
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<button
				type="button"
				class="btn btn-quiet px-2 text-blue-800"
				aria-expanded={tableShown}
				aria-controls="{id}-table"
				onclick={toggleTable}
			>
				<!-- One width for both words (pumps-nits.md item 1): Show and Hide stacked in one
					grid cell, the one not said invisible and aria-hidden, so the swap moves nothing beside
					it (it moved Download image 6.5 px at 390 and 1280 px). The space outside the hidden
					suffix, so every name computation keeps it. -->
				<span class="grid" data-table-words>
					<span
						class={['col-start-1 row-start-1', tableShown && 'invisible']}
						aria-hidden={tableShown || undefined}>Show data table</span
					>
					<span
						class={['col-start-1 row-start-1', !tableShown && 'invisible']}
						aria-hidden={!tableShown || undefined}>Hide data table</span
					>
				</span>
				<span class="sr-only">of the pump chart</span>
			</button>
			{#if image}
				<!-- Download image and its reason, one item (§5.3 Actions, §5.5): a lasting reason beside
					the button where the row has room for it, under it where not, never under Show data
					table. Its least width is the button's, so the item drops under as the button did. -->
				<div class="flex flex-1 flex-wrap items-center gap-x-3 gap-y-1">
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
	{/if}
	<!-- Notes about the values (§5.3): facts first, unmarked (§5.2), chartNotes' words. -->
	<div class="space-y-1" data-pump-notes>
		{#each [...valued.first, ...valued.facts, ...valued.panels] as note (note)}
			<p class="text-xs text-slate-700">{note}</p>
		{/each}
		{#if valued.extrapolated}
			<p class="text-xs text-slate-700">{valued.extrapolated}</p>
		{/if}
		{#if valued.method}
			<!-- How the curve shown was computed, where it is shown (GOALS §4.2): the request
				(POST /api/v1/system-curve) returns points without a trace; the pump's trace defines it.
				The link is inline in its sentence (WCAG 2.5.8's inline exception, §5.3). -->
			<p class="text-xs text-slate-700" data-pump-method>
				{valued.method}
				{#if ontrace}
					<button
						type="button"
						class="text-left text-blue-800 underline underline-offset-2 hover:text-blue-900"
						onclick={ontrace}>Trace of {name}</button
					>
				{/if}
			</p>
		{/if}
		{#if valued.checks.length}
			<!-- The design checks' limits drawn (D19), never a verdict: Checks has those. The limits
				a list named by its label, as the group chart's ring list is named by its lead
				(pumps-results-layout.md §5.3, S3), so the notes are no wall: §5.7 row 7's longest run
				(S1's 9 paragraphs in the one-off, §15 item 43). The closing sentence after the list. -->
			<div class="space-y-1 pt-1" data-pump-checks>
				<p id="{id}-limits" class="text-xs font-medium text-slate-700">Design-check limits drawn</p>
				<ul class="space-y-1" aria-labelledby="{id}-limits">
					{#each valued.checks.slice(0, -1) as note (note)}
						<li><p class="text-xs text-slate-700">{note}</p></li>
					{/each}
				</ul>
				<p class="text-xs text-slate-700">{valued.checks.at(-1)}</p>
				{#if onchecks}
					<button type="button" class="btn btn-quiet px-2 text-blue-800" onclick={onchecks}
						>Go to Checks</button
					>
				{/if}
			</div>
		{/if}
	</div>
	<!--
		The data region (pumps-results-layout.md §5.1 item 9, §5.3 The data region), after the
		notes, so a table shown never pushes a note away from its chart. The case shown first: its
		operating point at the top (the table is the chart's long description, pump-chart.md §4.4),
		"Operating points by case", then its curves, two-up only from a 40 rem container (§5.5); the
		other cases' system curves last. Each curve table is a disclosure, "{caption} ({n} points)",
		full height when open, and open by default where the chart cannot be drawn or its Why no
		head column has entries (§9 S7: CurveTable). Every box shades its edges when it scrolls
		sideways, and is a Tab stop and a named region only while it overflows (scrollRegion, §5.7).
	-->
	{#if tableShown}
		<div id="{id}-table" class="space-y-3" data-pump-data>
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
			{#if otherData.length}
				<!-- A list below 640 px (ui-guide, Phones): explicit roles, so CSS never unmakes the
					table for screen readers; each row its case, then "Flow (L/s) 21.58" pairs. -->
				<div
					class="scroll-shadow-x relative max-w-full overflow-auto rounded-md border border-slate-200 bg-white max-sm:overflow-visible"
					use:scrollRegion={`${id}-cases-caption`}
				>
					<!-- svelte-ignore a11y_no_redundant_roles -->
					<table role="table" class="w-full text-sm max-sm:block">
						<caption
							id="{id}-cases-caption"
							class="px-2 py-1 text-left text-xs font-semibold text-slate-700 max-sm:block"
						>
							Operating points by case
						</caption>
						<!-- svelte-ignore a11y_no_redundant_roles -->
						<thead role="rowgroup" class="bg-slate-50 max-sm:sr-only">
							<!-- svelte-ignore a11y_no_redundant_roles -->
							<tr role="row">
								<th role="columnheader" scope="col" class="px-2 py-1 text-left font-medium">Case</th
								>
								<th role="columnheader" scope="col" class="px-2 py-1 text-right font-medium"
									>Flow ({data.flowUnit})</th
								>
								<th role="columnheader" scope="col" class="px-2 py-1 text-right font-medium"
									>Head ({data.headUnit})</th
								>
								<th role="columnheader" scope="col" class="px-2 py-1 text-right font-medium"
									>Speed (%)</th
								>
								<th role="columnheader" scope="col" class="px-2 py-1 text-left font-medium"
									>State</th
								>
							</tr>
						</thead>
						<!-- svelte-ignore a11y_no_redundant_roles -->
						<tbody role="rowgroup" class="max-sm:block">
							{#each caseRows as row (row.shown ? '\u0000shown' : row.key)}
								{@const cells = [
									{ label: `Flow (${data.flowUnit})`, value: row.flow, numeric: true },
									{ label: `Head (${data.headUnit})`, value: row.head, numeric: true },
									{ label: 'Speed (%)', value: row.speed, numeric: true },
									{ label: 'State', value: row.state, numeric: false }
								]}
								<!-- svelte-ignore a11y_no_redundant_roles -->
								<tr
									role="row"
									class="border-t border-slate-100 max-sm:flex max-sm:flex-wrap max-sm:items-baseline max-sm:gap-x-3 max-sm:gap-y-0.5 max-sm:px-2 max-sm:pb-1.5"
								>
									<!-- Below 640 px the case's name heads its block, wrapping anywhere (a name
										with no space too), as "Other cases' station duties" (S7 review
										PRE-OPPOINTS-LONGCASE). -->
									<th
										role="rowheader"
										scope="row"
										class="px-2 py-1 text-left font-normal max-sm:block max-sm:w-full max-sm:px-0 max-sm:pt-1 max-sm:font-medium max-sm:wrap-anywhere"
										>{#if row.marker}<span aria-hidden="true" class="text-slate-600"
												>{row.marker}</span
											>
											{row.label}{:else}{row.label}{/if}</th
									>
									{#each cells as cell (cell.label)}
										<td
											role="cell"
											data-label={cell.label}
											class={[
												'px-2 py-1',
												cell.numeric ? 'text-right tabular-nums' : 'text-xs text-slate-600',
												'max-sm:flex max-sm:items-baseline max-sm:gap-1 max-sm:p-0 max-sm:text-left',
												'max-sm:before:text-xs max-sm:before:text-slate-600 max-sm:before:content-[attr(data-label)]',
												// A phone's row leaves out what it has no value for, out of sight only.
												cell.value === '—' && 'max-sm:sr-only'
											]}>{cell.value}</td
										>
									{/each}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
			<!-- A container (§5.5): the shown case's tables two-up only where two fit, from 40 rem. -->
			<div class="@container">
				<div class="grid items-start gap-3 @min-[40rem]:grid-cols-2">
					<CurveTable
						key="pump"
						caption="Pump curve at {speedText}"
						points={data.curveRows.length}
						openByDefault={cannotDraw}
						bind:choice={tablesOpen.pump}
					>
						<thead class="bg-slate-50">
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
					</CurveTable>
					{#if data.system}
						<!-- Open by default when a point has no head: the reasons the strip's line points
							to ("the data table says why") one press away (§5.3, D10's owner rule). -->
						<CurveTable
							key="system"
							caption="System curve"
							points={data.systemRows.length}
							openByDefault={cannotDraw || data.systemMissing > 0}
							bind:choice={tablesOpen.system}
						>
							<thead class="bg-slate-50">
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
												>{row.note}{#if row.detail}<IssueDetail
														detail={row.detail}
														subject="the point at {row.flow} {data.flowUnit}"
													/>{/if}</td
											>
										{/if}
									</tr>
								{/each}
							</tbody>
						</CurveTable>
					{/if}
					{#each curveTables as table (table.key)}
						<CurveTable
							key={table.key}
							caption={table.caption}
							points={table.rows.length}
							openByDefault={cannotDraw}
							bind:choice={tablesOpen[table.key]}
						>
							<thead class="bg-slate-50">
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
						</CurveTable>
					{/each}
				</div>
			</div>
			<!-- The other cases' system curves, on this chart's flow grid, last (§5.3, F33); each open
				by default when one of its points has no head (§9 S7). -->
			{#each otherData.filter((o) => o.system) as other (other.key)}
				<CurveTable
					key="system-{caseId(other.key)}"
					caption="System curve, {other.label}"
					points={other.systemRows.length}
					openByDefault={cannotDraw || other.systemRows.some((row) => row.head === '—')}
					bind:choice={tablesOpen[`system-${caseId(other.key)}`]}
				>
					<thead class="bg-slate-50">
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
									>{row.note}{#if row.detail}<IssueDetail
											detail={row.detail}
											subject="the point at {row.flow} {data.flowUnit}, {other.label}"
										/>{/if}</td
								>
							</tr>
						{/each}
					</tbody>
				</CurveTable>
			{/each}
		</div>
	{/if}
	<!--
		Other cases (§5.3, "Other cases on the pump chart"), under their own heading at the figure's
		end, so every figure-scoped test still finds them: the cases drawn, then the switch for
		their system curves with its cost kept visible (§6.4 item 8), then its live line.
	-->
	{#if others.length}
		<div class="space-y-2 border-t border-slate-200 pt-3" data-pump-others>
			<h4 class="text-sm font-semibold text-slate-900">Other cases on the pump chart</h4>
			<!-- The legend the fieldset's first child, so the group keeps its name (§5.3 markup). -->
			<fieldset>
				<legend class="text-xs font-medium text-slate-700">Cases on the chart</legend>
				<!-- An auto-fill grid, 13 rem at least: two columns in a 480 px pane, one on a phone. -->
				<div class="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-x-3">
					<!-- The case shown: a tag, not a control (§5.2 Tags). -->
					<span
						class="col-span-full mt-1 justify-self-start rounded bg-slate-100 px-1.5 text-xs text-slate-700"
						><span aria-hidden="true">●</span> {caseName ?? 'This case'} (shown)</span
					>
					{#each cases.listed as other (other.key)}
						{@const on = shownKeys.has(other.key)}
						{@const full = !on && shownOthers.length >= MAX_CHART_CASES - 1}
						{@const marker = markerOf(other.key)}
						{@const offHere = other.result.status === 'off'}
						{@const described = [offHere && `${id}-off-${caseId(other.key)}`, full && `${id}-full`]
							.filter(Boolean)
							.join(' ')}
						<div>
							<!-- Capped (§5.3): the box greyed, the name kept readable (slate-600). -->
							<label
								class={[
									'flex min-h-11 items-start gap-2 py-3 text-sm',
									full && 'cursor-not-allowed text-slate-600'
								]}
							>
								<input
									type="checkbox"
									class={['mt-0.5 size-4 shrink-0', full && 'opacity-45']}
									checked={on}
									aria-disabled={full}
									aria-describedby={described || undefined}
									onclick={(event) => {
										if (full) {
											event.preventDefault();
											return;
										}
										ontick?.(other.key, event.currentTarget.checked);
									}}
								/>
								<!-- The marker's column is kept, so a name never moves on tick. -->
								<span aria-hidden="true" class="w-4 shrink-0 text-center text-slate-600"
									>{marker ? MARKER_SYMBOLS[marker] : ''}</span
								>
								<span class="min-w-0 break-words"
									>{other.name}{other.stale ? ' (out of date)' : ''}</span
								>
							</label>
							{#if offHere}
								<!-- Beside its box, outside its label, and in its description (§5.3). -->
								<p
									id="{id}-off-{caseId(other.key)}"
									class="-mt-2 pb-2 pl-12 text-xs text-slate-600"
								>
									(off in this case: no operating point)
								</p>
							{/if}
						</div>
					{/each}
				</div>
				{#if offNote}
					<!-- The cases that take no slot, named under the list (§9 S8, §6.2): no box. An
						unbroken name wraps inside the card. -->
					<p class="hint wrap-break-word" data-pump-off-cases>{offNote}</p>
				{/if}
				{#if cases.listed.length > MAX_CHART_CASES - 1}
					<p id="{id}-full" class="hint">At most {MAX_CHART_CASES} cases at once.</p>
				{/if}
			</fieldset>
			{#if onoverlay}
				<div>
					<label class="flex min-h-11 items-center gap-2 text-sm">
						<input
							type="checkbox"
							class="size-4 shrink-0"
							checked={overlayCurves}
							aria-describedby="{id}-overlay-hint"
							onchange={(event) => switchOverlay(event.currentTarget)}
						/>
						Also show the other cases' system curves
					</label>
					<!-- A cost: kept visible, since on touch the tap that focuses it starts the solves. -->
					<p id="{id}-overlay-hint" class="-mt-1 pl-6 text-xs text-slate-600">
						Each is computed on request, one at a time, for that case's last solve; a curve costs
						about 41 solves of the network.
					</p>
				</div>
				<!-- Its live line (§5.3 markup rules, §7 Live regions): always there, polite, never
					role=status, empty while idle (and then out of sight); Cancel after it, outside it,
					described by it. -->
				<div
					class={['flex flex-wrap items-center gap-x-3 gap-y-1', !overlayLine && 'sr-only']}
					data-overlay-row
				>
					<span
						id="{id}-overlay-state"
						data-overlay-state
						aria-live="polite"
						aria-atomic="true"
						class="inline-flex items-start gap-1.5 text-xs text-slate-700"
						>{#if overlayLine}<Icon
								name="spinner"
								class="mt-px size-3.5 shrink-0 text-slate-500 motion-safe:animate-spin"
							/>Computing system curves: {Math.min(overlayLine.done + 1, overlayLine.total)}
							of
							{overlayLine.total}…{/if}</span
					>
					{#if overlayProgress && oncanceloverlay}
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							aria-label="Cancel the other cases' system curves"
							aria-describedby="{id}-overlay-state"
							onclick={oncanceloverlay}>Cancel</button
						>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</figure>
