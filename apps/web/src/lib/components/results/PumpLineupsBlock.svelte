<!--
	Add cases (CLAUDE.md D24, proposal pump-lineups.md §7): the Pumps together card's block, in the
	place of 4d's "One pump off" (CLAUDE.md D21 slice 4d), after the group chart since the Pumps
	tab's S2. Presentation only: the caller (PumpsView) computes the plan (pump-lineups.ts
	lineupPlan) and makes every change.

	The Pumps tab's S4 (pumps-results-layout.md §5.3, §9 S4): a framed, tinted panel, the one part
	of the card that changes the project, its h4 (14 px) with the plain tag "Changes the project"
	beside it, a sibling, so the region is named by the h4 alone. While a gate holds (§7.2), only its
	sentence, Solve all for gates 4 to 6 (with its lasting reason, as below), and the table button.
	Otherwise one structure in every state, so no control in use moves from one branch of the
	markup to another, in D24 §7.11's order: the preset ("Cases to add", label 12 px; By number
	running or Each pump off, page state); one native disclosure, the plan, holding what it makes
	(About), the interchangeability sentence and the stop order (By number running only), the cases
	it would make (each with its kind in words), which group the names count and which pump each id
	is; one row with Add and the one Solve all (the Scenarios menu's reasons, 4d's); Add's refusal;
	Solve all's reason while it lasts (one that passes, while a solve runs, stays visually hidden
	and in `title`); after an Add that ticked it, "Now ticked: …", said by the polite line too and
	gone from both with the Add it reports.

	The fold (§5.3): the plan is drawn closed only when every planned case exists (nothing to add,
	some made), open otherwise, and opens itself when cases come to remain (another preset, a
	scenario deleted, an Undo); it never closes itself, so after the user's own Add it stays as left.

	The stop order (§7.5) is a native disclosure, closed by default, whose summary says what it
	holds: an ordered list with two icon buttons per pump (Stop … earlier, Stop … later; at an end
	they stay focusable, aria-disabled and described), Default order when the order is not the
	default, and a polite status line. Focus is put back explicitly after every move: a keyed each
	moves the focused node on "later" and the browser drops its focus (§7.5).

	At its foot whenever it is drawn, gates included (slice L2, §8.1): the quiet "Pump lineups
	table…", which opens the Scenarios manager on Pump lineups showing the card's pumps.
-->
<script lang="ts" module>
	import type { LineupPlan, LineupPreset } from '$lib/utils/pump-lineups';

	/** Solve all in the block: the Scenarios menu's reasons (solveAllReason; 4d's). */
	export interface SolveAllState {
		count: number;
		canRun: boolean;
		/** Why it is unavailable ('' when it can run). */
		reason: string;
		/** What it does, when it can run. */
		hint: string;
		/**
		 * The reason passes (a solve, Solve all or a goal seek runs): visually hidden and the
		 * button's `title`, so nothing flashes; a reason that lasts is shown (pumps-results-layout.md
		 * §5.3, ui-guide).
		 */
		passing?: boolean;
	}

	export interface LineupsBlockProps {
		/** What the block would make now (lineupPlan), or why not. */
		plan: LineupPlan;
		solveAll: SolveAllState;
		/** Choose the preset (page state). */
		onpreset?: (preset: LineupPreset) => void;
		/** Move a pump one place earlier ('up') or later ('down') in the stop order (page state). */
		onmove?: (pumpId: string, dir: 'up' | 'down') => void;
		/** Set the stop order back to the default. */
		ondefaultorder?: () => void;
		/** Add the cases (one undo step); the focus then moves to the block's Solve all. */
		onadd?: () => void;
		/**
		 * "Also show the other cases' station duties" is ticked (page state, ws.pumpGroupOthers): an
		 * Add that ticks it says so ("Now ticked: …", pumps-results-layout.md §5.3).
		 */
		othersOn?: boolean;
		/** Solve every case not yet solved (the Scenarios menu's Solve all). */
		onsolveall?: () => void;
		/**
		 * Open the Scenarios manager on Pump lineups, showing the card's pumps only (slice L2, §8.1);
		 * the button is drawn when it is given.
		 */
		ontable?: () => void;
	}
</script>

<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { LINEUP_TABLE_WORDS } from '$lib/utils/lineup-table';
	import {
		ADD_CASES_WORDS,
		LINEUP_BLOCK_WORDS,
		LINEUP_PRESET_LABELS,
		STOP_ORDER_WORDS,
		type LineupPreset as Preset
	} from '$lib/utils/pump-lineups';
	import Icon from '$lib/components/ui/Icon.svelte';
	import SegmentedField from '$lib/components/ui/SegmentedField.svelte';
	import { registerSection } from './section-nav.svelte';

	let {
		plan,
		solveAll,
		onpreset,
		onmove,
		ondefaultorder,
		onadd,
		othersOn,
		onsolveall,
		ontable
	}: LineupsBlockProps = $props();
	const id = $props.id();

	const presets = (Object.keys(LINEUP_PRESET_LABELS) as LineupPreset[]).map((value) => ({
		value,
		label: LINEUP_PRESET_LABELS[value]
	}));

	let section: HTMLElement | undefined = $state();
	/** The section nav's "Add cases" (pumps-results-layout.md §5.4): this block's heading. */
	let heading: HTMLElement | undefined = $state();
	registerSection('add-cases', () => heading);
	let solveAllButton: HTMLButtonElement | undefined = $state();
	/**
	 * The block's polite line: what the last move or Default order did, or "Now ticked: …" after
	 * an Add that ticked "Also show …" (pumps-results-layout.md §5.3, §7 Live regions).
	 */
	let status = $state('');

	/** Every planned case exists (nothing to add, some made): the plan is drawn folded (§5.3). */
	const done = $derived(plan.add.length === 0 && plan.existing.length > 0);
	/** The plan disclosure's open state: the user's, but for the fold rule's two moves below. */
	let planOpen = $state(false);
	let planEl: HTMLDetailsElement | undefined = $state();
	/** The last Add ticked "Also show the other cases' station duties" (§5.3 "Now ticked"). */
	let ticked = $state(false);
	/** What the plan was at the last run of the rule below (not reactive). */
	let seen: { drawn: boolean; done: boolean; preset: Preset; others: boolean } | null = null;
	/**
	 * The fold rule (§5.3), before the DOM is updated so the disclosure is drawn as it says: drawn
	 * (the block mounted, or a gate lifted), it is closed only when every planned case exists; when
	 * cases come to remain, it opens itself; it is never closed here. "Now ticked" goes with the
	 * Add it reports: once cases remain again, another preset is chosen or the box is unticked. Its
	 * copy in the polite line goes with it (the same sentence, §5.3), so the line never says what no
	 * longer holds and the next "Now ticked" is written into an empty line; a stop order's message
	 * there is left alone.
	 */
	$effect.pre(() => {
		const now = { drawn: !plan.gate, done, preset: plan.preset, others: !!othersOn };
		const before = seen;
		seen = now;
		if (now.drawn && !before?.drawn) planOpen = !now.done;
		else if (now.drawn && before?.done && !now.done) {
			// The element too: a user's close reaches `planOpen` only with the queued toggle event.
			planOpen = true;
			if (planEl) planEl.open = true;
		}
		if (before && (!now.done || now.preset !== before.preset || !now.others)) {
			ticked = false;
			if (untrack(() => status) === ADD_CASES_WORDS.nowTicked) status = '';
		}
	});
	/** The frame that writes "Now ticked" into the polite line (addCases), until it is written. */
	let frame = 0;
	$effect(() => () => cancelAnimationFrame(frame));

	/**
	 * Solve all's reason drawn: one that lasts, under a gate too (§5.3 item 5; §7 Names and marks:
	 * a lasting reason is visible text, §6.2).
	 */
	const reasonShown = $derived(!!solveAll.reason && !solveAll.passing);

	/** The move button of `pumpId` in `dir` (found by data attributes: ids are any string). */
	function stopButton(pumpId: string, dir: 'up' | 'down'): HTMLButtonElement | undefined {
		const buttons = section?.querySelectorAll<HTMLButtonElement>('[data-stop-id][data-dir]') ?? [];
		return [...buttons].find((b) => b.dataset.stopId === pumpId && b.dataset.dir === dir);
	}

	/**
	 * Move a pump; then say where it is now and put the focus back on the same button of that
	 * pump, also when the move reached an end (the button is then aria-disabled). The keyed list
	 * moves the focused item's node on "later", which loses the focus (§7.5), so it is always put
	 * back. At an end the press does nothing.
	 */
	async function move(pumpId: string, dir: 'up' | 'down') {
		const items = plan.stopOrder?.items ?? [];
		const at = items.findIndex((item) => item.id === pumpId);
		if (at < 0 || (dir === 'up' ? at === 0 : at === items.length - 1)) return;
		onmove?.(pumpId, dir);
		await tick();
		const now = plan.stopOrder?.items ?? [];
		const i = now.findIndex((item) => item.id === pumpId);
		if (i >= 0) status = STOP_ORDER_WORDS.moved(now[i]!.label, i + 1, now.length);
		stopButton(pumpId, dir)?.focus();
	}

	/** Default order removes itself: the focus goes to the first pump's "Stop … later". */
	async function defaultOrder() {
		ondefaultorder?.();
		await tick();
		const first = plan.stopOrder?.items[0];
		if (!first) return;
		status = STOP_ORDER_WORDS.resetDone(first.label);
		stopButton(first.id, 'down')?.focus();
	}

	/**
	 * Add the cases; then the focus is on the block's Solve all (4d's), so an Add that ticked "Also
	 * show …" says so in the block's polite line as well as on screen (§5.3): the focus would not
	 * pass the line. The line is emptied at the press and the words written two frames later, so it
	 * is drawn empty before it speaks (§7 Live regions; S1's rule, §15 item 24): emptied and filled
	 * in one task, the accessibility tree would see no change. They are not written once "Now
	 * ticked" has gone again, or once a stop order's move has written its own message.
	 */
	async function addCases() {
		if (plan.gate || plan.refusal || !plan.add.length) return;
		const wasOn = !!othersOn;
		cancelAnimationFrame(frame);
		status = '';
		onadd?.();
		await tick();
		solveAllButton?.focus();
		if (!wasOn && othersOn) {
			ticked = true;
			frame = requestAnimationFrame(() => {
				frame = requestAnimationFrame(() => {
					if (ticked && !status) status = ADD_CASES_WORDS.nowTicked;
				});
			});
		}
	}
	function solveAllCases(event: MouseEvent) {
		if (solveAll.canRun && event.detail <= 1) onsolveall?.();
	}
</script>

<!-- The panel (pumps-results-layout.md §5.3): framed and tinted, the card's one part that changes
	the project; its header row holds the h4 and, as its sibling, the tag. Every line in it wraps an
	unbroken name inside the frame (a pump's name in the sentence, a case's in the refusal). The
	part before the visually hidden polite line keeps no gap after it, so the frame's padding is
	the same at its foot as at its head. -->
<section
	bind:this={section}
	class="space-y-2 rounded-lg border border-slate-300 bg-slate-50 p-3 wrap-break-word [&>:has(+[data-stop-status])]:mb-0"
	aria-labelledby="{id}-heading"
	data-add-cases
>
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
		<!-- tabindex −1: the section nav's "Add cases" focuses it (pumps-results-layout.md §5.4). -->
		<h4
			bind:this={heading}
			id="{id}-heading"
			class="scroll-mt-[calc(var(--pumps-nav-h,0px)-var(--pumps-nav-pad,0px)+0.5rem)] text-sm font-semibold text-slate-900"
			tabindex="-1"
		>
			{LINEUP_BLOCK_WORDS.heading}
		</h4>
		<span class="text-xs text-slate-600" data-add-cases-tag>{ADD_CASES_WORDS.tag}</span>
	</div>
	{#if plan.gate}
		<p class="text-xs text-slate-700">{plan.gate}</p>
	{:else}
		<!-- 1. The segments, outside any disclosure; their label 12 px, under its 14 px h4 (§5.2). -->
		<div class="[&_.label]:text-xs">
			<SegmentedField
				label={LINEUP_BLOCK_WORDS.preset}
				value={plan.preset}
				options={presets}
				shared
				onchange={(preset) => onpreset?.(preset)}
			/>
		</div>
		<!-- 2. The plan: everything the preset would make, one native disclosure that says what it
			holds, folded once every case exists (§5.3 The fold). -->
		<details bind:this={planEl} bind:open={planOpen} class="group/plan" data-lineup-plan>
			<summary class="more-summary hover:bg-slate-100">
				<Icon
					name="right"
					class="size-4 shrink-0 text-slate-500 transition-transform group-open/plan:rotate-90 motion-reduce:transition-none"
				/>
				<span class="min-w-0 flex-1"
					>{ADD_CASES_WORDS.planLead}<span class="font-normal text-slate-600">: {plan.summary}</span
					></span
				>
			</summary>
			<div class="space-y-2 pb-1">
				{#if plan.about}<p class="text-xs text-slate-700">{plan.about}</p>{/if}
				{#if plan.sentence}<p class="text-xs text-slate-600">{plan.sentence}</p>{/if}
				{#if plan.stopOrder}
					{@const order = plan.stopOrder}
					<details class="group/stop text-xs" data-stop-order>
						<summary
							class="flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-md font-medium break-words text-blue-800 hover:bg-slate-100 [&::-webkit-details-marker]:hidden"
						>
							<Icon
								name="right"
								class="size-3 shrink-0 transition-transform group-open/stop:rotate-90 motion-reduce:transition-none"
							/>
							<span class="min-w-0">{order.summary}</span>
						</summary>
						<div class="space-y-1">
							<p class="text-slate-600">{STOP_ORDER_WORDS.hint}</p>
							<ol
								aria-label={STOP_ORDER_WORDS.list}
								class="list-decimal divide-y divide-slate-200 pl-6 tabular-nums"
							>
								{#each order.items as item, i (item.id)}
									<li>
										<div class="flex min-h-11 items-center gap-1">
											<span class="min-w-0 flex-1 break-words"
												>{item.label}<span class="text-slate-600">{item.note}</span></span
											>
											<button
												type="button"
												class="btn btn-quiet btn-icon min-w-11"
												data-stop-id={item.id}
												data-dir="up"
												aria-disabled={i === 0}
												aria-describedby={i === 0 ? `${id}-at-first` : undefined}
												onclick={() => void move(item.id, 'up')}
											>
												<Icon name="up" class="size-4" /><span class="sr-only"
													>{STOP_ORDER_WORDS.earlier(item.label)}</span
												>
											</button>
											<button
												type="button"
												class="btn btn-quiet btn-icon min-w-11"
												data-stop-id={item.id}
												data-dir="down"
												aria-disabled={i === order.items.length - 1}
												aria-describedby={i === order.items.length - 1
													? `${id}-at-last`
													: undefined}
												onclick={() => void move(item.id, 'down')}
											>
												<Icon name="down" class="size-4" /><span class="sr-only"
													>{STOP_ORDER_WORDS.later(item.label)}</span
												>
											</button>
										</div>
									</li>
								{/each}
							</ol>
							<span id="{id}-at-first" class="sr-only">{STOP_ORDER_WORDS.atFirst}</span>
							<span id="{id}-at-last" class="sr-only">{STOP_ORDER_WORDS.atLast}</span>
							{#if !order.isDefault}
								<button
									type="button"
									class="btn btn-quiet"
									aria-describedby="{id}-default"
									onclick={() => void defaultOrder()}>{STOP_ORDER_WORDS.reset}</button
								>
								<span id="{id}-default" class="sr-only">{STOP_ORDER_WORDS.resetHint}</span>
							{/if}
						</div>
					</details>
				{/if}
				{#if plan.cases.length}
					<p id="{id}-cases" class="text-xs font-medium text-slate-700">
						{LINEUP_BLOCK_WORDS.cases}
					</p>
					<!-- Keyed by index, never by words: a name need not be unique. -->
					<ul
						aria-labelledby="{id}-cases"
						class="list-disc space-y-0.5 pl-5 text-xs text-slate-700"
					>
						{#each plan.cases as item, i (i)}<li class="break-words">{item.words}</li>{/each}
					</ul>
				{/if}
				{#if plan.frame}<p class="text-xs text-slate-600">{plan.frame}</p>{/if}
				{#if plan.ids}<p class="text-xs break-words text-slate-600" data-lineup-ids>
						{plan.ids}
					</p>{/if}
			</div>
		</details>
	{/if}
	{#if !plan.gate || plan.showSolveAll}
		<!-- 3. One row: Add and the one Solve all, in every state, so the focus Add hands to Solve
			all stays on the same button through the run and after (D24 §7.8). -->
		<div class="flex flex-wrap items-center gap-2">
			{#if !plan.gate}
				<button
					type="button"
					class="btn"
					aria-disabled={!!plan.refusal}
					aria-describedby={plan.refusal ? `${id}-refusal` : undefined}
					onclick={() => void addCases()}>{plan.label}</button
				>
			{/if}
			{#if plan.showSolveAll}
				<button
					bind:this={solveAllButton}
					type="button"
					class="btn"
					aria-disabled={!solveAll.canRun}
					aria-describedby="{id}-solve-all"
					title={!reasonShown && solveAll.reason ? solveAll.reason : undefined}
					onclick={solveAllCases}
				>
					<Icon name="play" class="size-4" /> Solve all{solveAll.count
						? ` (${solveAll.count})`
						: ''}
				</button>
			{/if}
		</div>
	{/if}
	<!-- 4. Add's refusal, visible: with every planned case made it is D24's own line, naming them. -->
	{#if !plan.gate && plan.refusal}
		<p id="{id}-refusal" class="hint">{plan.refusal}</p>
	{/if}
	{#if plan.showSolveAll}
		<!-- 5. Solve all's reason while it lasts, visible, under a gate too (§7 Names and marks);
			else its passing reason or what it does, visually hidden. Either is its description. -->
		<p id="{id}-solve-all" class={reasonShown ? 'hint' : 'sr-only'}>
			{solveAll.reason || solveAll.hint}
		</p>
	{/if}
	{#if ticked && othersOn && !plan.gate}
		<p class="hint" data-now-ticked>{ADD_CASES_WORDS.nowTicked}</p>
	{/if}
	{#if ontable}
		<!-- 6. At its foot whenever it is drawn, gates included (D24 slice L2, §8.1). -->
		<button type="button" class="btn btn-quiet text-blue-800" onclick={() => ontable?.()}
			>{LINEUP_TABLE_WORDS.cardButton}</button
		>
	{/if}
	<p class="sr-only" aria-live="polite" data-stop-status>{status}</p>
</section>
