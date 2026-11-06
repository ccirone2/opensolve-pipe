<!--
	Add cases (CLAUDE.md D24, proposal pump-lineups.md §7): the Pumps together card's block under
	the group table, in the place of 4d's "One pump off" (CLAUDE.md D21 slice 4d). Presentation only:
	the caller (PumpsView) computes the plan (pump-lineups.ts lineupPlan) and makes every change.

	While a gate holds (§7.2), only its sentence and, for gates 4 to 6, Solve all. Otherwise, in
	order: the preset ("Cases to add": By number running or Each pump off, page state), what it makes
	(About), the interchangeability sentence and the stop order (By number running only), the cases
	it would make (each with its kind in words), which group the names count, then Add with its
	refusal and Solve all with the Scenarios menu's reasons (4d's).

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
	import { tick } from 'svelte';
	import { LINEUP_TABLE_WORDS } from '$lib/utils/lineup-table';
	import {
		LINEUP_BLOCK_WORDS,
		LINEUP_PRESET_LABELS,
		STOP_ORDER_WORDS
	} from '$lib/utils/pump-lineups';
	import Icon from '$lib/components/ui/Icon.svelte';
	import SegmentedField from '$lib/components/ui/SegmentedField.svelte';

	let {
		plan,
		solveAll,
		onpreset,
		onmove,
		ondefaultorder,
		onadd,
		onsolveall,
		ontable
	}: LineupsBlockProps = $props();
	const id = $props.id();

	const presets = (Object.keys(LINEUP_PRESET_LABELS) as LineupPreset[]).map((value) => ({
		value,
		label: LINEUP_PRESET_LABELS[value]
	}));

	let section: HTMLElement | undefined = $state();
	let solveAllButton: HTMLButtonElement | undefined = $state();
	/** The stop order's status line (polite): what the last move or Default order did. */
	let status = $state('');

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

	/** Add the cases; then the focus is on the block's Solve all (4d's). */
	function addCases() {
		if (plan.gate || plan.refusal || !plan.add.length) return;
		onadd?.();
		void tick().then(() => solveAllButton?.focus());
	}
	function solveAllCases(event: MouseEvent) {
		if (solveAll.canRun && event.detail <= 1) onsolveall?.();
	}
</script>

<section bind:this={section} class="space-y-2" aria-labelledby="{id}-heading" data-add-cases>
	<h4 id="{id}-heading" class="text-xs font-semibold">{LINEUP_BLOCK_WORDS.heading}</h4>
	{#if plan.gate}
		<p class="text-xs text-slate-700">{plan.gate}</p>
	{:else}
		<SegmentedField
			label={LINEUP_BLOCK_WORDS.preset}
			value={plan.preset}
			options={presets}
			shared
			onchange={(preset) => onpreset?.(preset)}
		/>
		{#if plan.about}<p class="text-xs text-slate-700">{plan.about}</p>{/if}
		{#if plan.sentence}<p class="text-xs text-slate-600">{plan.sentence}</p>{/if}
		{#if plan.stopOrder}
			{@const order = plan.stopOrder}
			<details class="group text-xs">
				<summary
					class="flex min-h-11 cursor-pointer list-none items-center gap-1 font-medium break-words text-blue-800 [&::-webkit-details-marker]:hidden"
				>
					<Icon name="right" class="size-3 shrink-0 transition-transform group-open:rotate-90" />
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
										aria-describedby={i === order.items.length - 1 ? `${id}-at-last` : undefined}
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
			<p id="{id}-cases" class="text-xs font-medium text-slate-700">{LINEUP_BLOCK_WORDS.cases}</p>
			<!-- Keyed by index, never by words: a name need not be unique. -->
			<ul aria-labelledby="{id}-cases" class="list-disc space-y-0.5 pl-5 text-xs text-slate-700">
				{#each plan.cases as item, i (i)}<li class="break-words">{item.words}</li>{/each}
			</ul>
		{/if}
		{#if plan.frame}<p class="text-xs text-slate-600">{plan.frame}</p>{/if}
	{/if}
	{#if !plan.gate || plan.showSolveAll}
		<div class="flex flex-wrap items-center gap-2">
			{#if !plan.gate}
				<button
					type="button"
					class="btn"
					aria-disabled={!!plan.refusal}
					aria-describedby={plan.refusal ? `${id}-refusal` : undefined}
					onclick={addCases}>{plan.label}</button
				>
			{/if}
			{#if plan.showSolveAll}
				<button
					bind:this={solveAllButton}
					type="button"
					class="btn"
					aria-disabled={!solveAll.canRun}
					aria-describedby="{id}-solve-all"
					title={solveAll.reason || undefined}
					onclick={solveAllCases}
				>
					<Icon name="play" class="size-4" /> Solve all{solveAll.count
						? ` (${solveAll.count})`
						: ''}
				</button>
				<span id="{id}-solve-all" class="sr-only">{solveAll.reason || solveAll.hint}</span>
			{/if}
		</div>
	{/if}
	{#if !plan.gate && plan.refusal}
		<p id="{id}-refusal" class="hint">{plan.refusal}</p>
	{/if}
	{#if ontable}
		<button type="button" class="btn btn-quiet text-blue-800" onclick={() => ontable?.()}
			>{LINEUP_TABLE_WORDS.cardButton}</button
		>
	{/if}
	<p class="sr-only" aria-live="polite" data-stop-status>{status}</p>
</section>
