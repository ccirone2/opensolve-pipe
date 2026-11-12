<!--
	The other cases on the group chart (CLAUDE.md D21 slice 4d, D24; proposal
	pumps-results-layout.md §5.1 item 10, §5.3 "Other cases on the group chart", §9 S3): the group
	chart's last part, under its own h5, at the figure's end so every figure-scoped test still
	finds it. In order:

	- the switch first, "Also show the other cases' station duties", its cost kept visible (§6.4
	  item 8); while it is off, the one line saying the duties are not on the chart;
	- while it is on, "Cases on this chart" (at most six): the case shown a tag, then a box per
	  other case in number order, its case's number in a box (CaseTag) in a reserved column, drawn
	  or not, capped boxes greyed with their names readable (owner, 2026-11-12, nit 5; Q2 "By list
	  place"; docs/proposals/pumps-nits.md item 5, slice 5b);
	- its own live line (§5.3 markup rules, §7 Live regions): always there, polite, never
	  role=status, empty while idle and drawn empty before its first progress; Cancel after it, or,
	  when some duty was not computed, "Compute them again" with its lasting reason shown and "Go to
	  Running combinations";
	- the ring notes, cut (the owner's answer 1, §12): the clip note; "How to read the rings",
	  closed, holding the frame and the rule, before the ring list the frame introduces ("The list
	  below says, for each ring, which"); the ring list, named by its lead, one line per ring; "Not
	  on the chart"; the count of labels left out. The words are groupNotes' parts (otherParts),
	  which otherNoteLines joins into the image's footer, unchanged.

	Presentation only: PumpGroupChart gives every value and PumpsView makes every request.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { caseTagOf, type CaseNumber } from '$lib/utils/pump-chart';
	import type { OtherNoteParts } from '$lib/utils/pump-group-chart';
	import { MAX_GROUP_CASES, type OtherGroupCase } from '$lib/utils/pump-group-one-off';
	import CaseTag from '$lib/components/ui/CaseTag.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useSectionNav } from './section-nav.svelte';

	interface Props {
		/** The other cases with values, each in its state, while the card shows a station. */
		others: readonly OtherGroupCase[];
		/** Every case's number (pump-chart.ts caseTags): each case's box, drawn or not. */
		tags: Readonly<Record<string, CaseNumber>>;
		/** The case shown's number: its "(shown)" tag. */
		caseTag: CaseNumber;
		/** "Also show the other cases' station duties" is ticked. */
		othersOn: boolean;
		/** Tick or untick it (absent: the project has no scenarios, no box). */
		onothers?: (on: boolean) => void;
		/** Tick or untick a case under "Cases on this chart". */
		onotherstick?: (key: string, on: boolean) => void;
		/** The case shown. */
		caseName?: string;
		/** The card shows a station: the switch and the list are drawn only then. */
		station: boolean;
		/** The notes on the other cases' station duties, as parts (groupNotes' otherParts). */
		parts: OtherNoteParts;
		/** The other cases' duties are being computed. */
		othersLoading: boolean;
		/** The group curve or the group system curve is being computed: the others wait for it. */
		curvesLoading: boolean;
		/** Settled of all on the chart (null: none). */
		othersProgress: { done: number; total: number } | null;
		oncancelothers?: () => void;
		/** Some case on the chart was cancelled by the user or failed: "Compute them again". */
		othersRetry: boolean;
		onretryothers?: () => void;
		/** Why "Compute them again" is unavailable ('' when it can run). */
		othersRetryReason: string;
		/** Running combinations is drawn: "Go to Running combinations" can go there. */
		combinations?: boolean;
		/** The group chart's figure: the focus falls back to it. */
		figure?: HTMLElement;
	}

	let {
		others,
		tags,
		caseTag,
		othersOn,
		onothers,
		onotherstick,
		caseName,
		station,
		parts,
		othersLoading,
		curvesLoading,
		othersProgress,
		oncancelothers,
		othersRetry,
		onretryothers,
		othersRetryReason,
		combinations = false,
		figure
	}: Props = $props();
	const id = $props.id();
	/** The section nav, for "Go to Running combinations" (§6.2); none in the card's own tests. */
	const nav = useSectionNav();

	const othersFull = $derived(others.filter((o) => o.onChart).length >= MAX_GROUP_CASES);

	/**
	 * The live line is drawn empty before its progress is said (§7 Live regions, F17; S1's rule,
	 * §15 item 24), as Station's and the strip's: a polite line inserted already speaking is not
	 * announced. Two frames: the first one's callbacks run before it draws the empty line.
	 */
	let lineDrawn = $state(false);
	$effect(() => {
		let frame = requestAnimationFrame(() => {
			frame = requestAnimationFrame(() => (lineDrawn = true));
		});
		return () => cancelAnimationFrame(frame);
	});
	/** Their progress, while nothing on the card comes before them (the others wait for it). */
	const progress = $derived(othersLoading && !curvesLoading ? othersProgress : null);
	/** Some duty on the chart was not computed (cancelled or failed), and none is computed now. */
	const notAll = $derived(othersRetry && !othersLoading);
	/** What the line says: the progress once drawn empty, else that some were not computed. */
	const line = $derived(
		progress && lineDrawn
			? `Computing the other cases' station duties: ${Math.min(progress.done + 1, progress.total)} of ${progress.total}…`
			: notAll
				? "Not every other case's station duty was computed: see Running combinations."
				: ''
	);

	let cancelButton: HTMLButtonElement | undefined = $state();
	let retryButton: HTMLButtonElement | undefined = $state();
	// From Cancel to "Compute them again" (or the figure), and back (slice 4d). "Compute them
	// again" also goes without a progress line, when it is pressed while a calculation runs (the
	// Pumps view gives none then: nothing is computed for the other cases until it ends).
	$effect.pre(() => {
		if (othersLoading) return;
		const cancel = untrack(() => cancelButton);
		if (!cancel || document.activeElement !== cancel) return;
		void tick().then(() => (retryButton ?? figure)?.focus());
	});
	$effect.pre(() => {
		if (othersRetry && !othersLoading) return;
		const retry = untrack(() => retryButton);
		if (!retry || document.activeElement !== retry) return;
		void tick().then(() => (cancelButton ?? figure)?.focus());
	});
</script>

<!-- A plain div with its heading, not a landmark (§7): the figure's last part (§5.1 item 10). -->
<div class="space-y-2 pt-1" data-group-others>
	<h5 class="section-title">Other cases on the group chart</h5>
	{#if onothers && station}
		<!-- The switch first (§6.4 item 10), its cost kept visible (§6.4 item 8): on touch, the tap
			that would focus it starts the solves. -->
		<div>
			<!-- The box at the label's first line where the label wraps (a phone's), as the cases'. -->
			<label class="flex min-h-11 items-start gap-2 py-3 text-sm">
				<input
					type="checkbox"
					class="mt-0.5 size-4 shrink-0"
					checked={othersOn}
					aria-describedby="{id}-others-hint"
					onchange={(event) => onothers(event.currentTarget.checked)}
				/>
				Also show the other cases' station duties
			</label>
			<p id="{id}-others-hint" class="-mt-1 pl-6 text-xs text-slate-600">
				Each case's station duty is computed on request, one case at a time, for that case's last
				solve: a solve of that case and about 41 solves of the station (its group curve, which the
				card shows when that case is shown).
			</p>
		</div>
	{/if}
	{#if parts.off}
		<!-- While it is off: one line, never a list (slice 4d). -->
		<p class="text-xs text-slate-700" data-group-others-off>{parts.off}</p>
	{/if}
	{#if onothers && station && othersOn && others.length}
		<!-- The legend the fieldset's first child, so the group keeps its name (§5.3 markup). -->
		<fieldset>
			<legend class="text-xs font-medium text-slate-700">Cases on this chart</legend>
			<!-- An auto-fill grid, 13 rem at least, as the pump chart's (§5.3, §15 item 35). -->
			<div class="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-x-3">
				<!-- The case shown: a tag, not a control (§5.2 Tags); its number in a box, then its words,
					no ● before them (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md item 5). -->
				<span
					class="col-span-full mt-1 justify-self-start rounded bg-slate-100 px-1.5 text-xs text-slate-700"
					><CaseTag tag={caseTag} /> {caseName ?? 'This case'} (shown)</span
				>
				{#each others as other (other.key)}
					{@const capped = !other.onChart && othersFull}
					<!-- Capped (§5.3): the box greyed, the name kept readable (slate-600). -->
					<label
						class={[
							'flex min-h-11 items-start gap-2 py-3 text-sm',
							capped && 'cursor-not-allowed text-slate-600'
						]}
					>
						<input
							type="checkbox"
							class={['mt-0.5 size-4 shrink-0', capped && 'opacity-45']}
							checked={other.onChart}
							aria-disabled={capped}
							aria-describedby={capped ? `${id}-cases-full` : undefined}
							onclick={(event) => {
								if (capped) {
									event.preventDefault();
									return;
								}
								onotherstick?.(other.key, event.currentTarget.checked);
							}}
						/>
						<!-- Its case's number in a reserved column (2.5 rem, §5.3), the same drawn or not,
							ticked or not, so a name never moves (nit 5, slice 5b); its words heard before
							the name (CaseTag). -->
						<span class="w-10 shrink-0"><CaseTag tag={caseTagOf(tags, other.key)} /></span>
						<span class="min-w-0 wrap-break-word"
							>{other.name}{other.stale ? ' (out of date)' : ''}</span
						>
					</label>
				{/each}
			</div>
			{#if othersFull && others.some((o) => !o.onChart)}
				<p id="{id}-cases-full" class="hint">
					At most {MAX_GROUP_CASES} other cases at once.
				</p>
			{/if}
		</fieldset>
	{/if}
	<!--
		Its live line (§5.3 markup rules, §7 Live regions): the row's first child, always there,
		polite, never role=status, empty while idle (and then out of sight, still in the
		accessibility tree); its buttons after it, outside it, described by it.
	-->
	<div
		class={['flex flex-wrap items-center gap-x-3 gap-y-1', !line && 'sr-only']}
		data-group-others-row
	>
		<span
			id="{id}-others-state"
			data-group-others-state
			aria-live="polite"
			aria-atomic="true"
			class="inline-flex items-start gap-1.5 text-xs text-slate-700"
			>{#if progress && lineDrawn}<Icon
					name="spinner"
					class="mt-px size-3.5 shrink-0 text-slate-500 motion-safe:animate-spin"
				/>{/if}{line}</span
		>
		{#if othersLoading && !curvesLoading && oncancelothers}
			<button
				bind:this={cancelButton}
				type="button"
				class="btn btn-quiet px-2 text-blue-800"
				aria-label="Cancel the other cases' station duties"
				aria-describedby="{id}-others-state"
				onclick={oncancelothers}>Cancel</button
			>
		{:else if notAll}
			{#if onretryothers}
				<!-- "Compute them again" and its lasting reason, one item (§5.3, §15 item 27): the
					reason beside the button where the row has room, under it where not. -->
				<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
					<button
						bind:this={retryButton}
						type="button"
						class="btn btn-quiet px-2 text-blue-800"
						aria-disabled={!!othersRetryReason}
						aria-describedby={othersRetryReason
							? `${id}-others-retry-reason ${id}-others-state`
							: `${id}-others-state`}
						onclick={() => {
							if (!othersRetryReason) onretryothers?.();
						}}>Compute them again</button
					>
					{#if othersRetryReason}<span
							id="{id}-others-retry-reason"
							class="text-xs text-slate-700"
							data-others-retry-reason>{othersRetryReason}</span
						>{/if}
				</div>
			{/if}
			{#if nav?.shown && combinations}
				<!-- A button, never a link: the URL fragment is the project (D3, §6.2). -->
				<button
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					onclick={() => nav.go('combinations')}>Go to Running combinations</button
				>
			{/if}
		{/if}
	</div>
	{#if parts.clip}
		<!-- Visible: what is drawn is not every point (§5.3 The ring notes). -->
		<p class="text-xs text-slate-700">{parts.clip}</p>
	{/if}
	{#if parts.frame}
		<!--
			What a ring is, one step away (§6.4 item 17): closed, never opened by code, drawn only
			while a ring is on the chart (the frame exists exactly then), before the list its frame
			introduces; its summary names what it holds, the rule only while the rule is there.
		-->
		<details class="group" data-group-rings-how>
			<summary class="more-summary">
				<Icon
					name="right"
					class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
				/>
				<span class="min-w-0 flex-1"
					>How to read the rings<span class="font-normal text-slate-600"
						>: what a ring is, which curve it lies on{parts.claim
							? ', when it is called a point of the group system curve'
							: ''}</span
					></span
				>
			</summary>
			<div class="space-y-1 pb-1">
				<p class="text-xs text-slate-700">{parts.frame}</p>
				{#if parts.claim}<p class="text-xs text-slate-700">{parts.claim}</p>{/if}
			</div>
		</details>
	{/if}
	{#if parts.rings}
		<!-- The ring list (§5.3): a list named by its lead, so it is told apart from the legend; one
			line per ring's case, in number order, its case's number in a box in a reserved column
			(2.5 rem: nit 5, slice 5b) so every line's words start at one edge, the case's name in
			medium weight. Each line as heard (the box's words, "Case 2:", then the rest) is the
			ring's entry in the image's sentence, word for word. -->
		<div data-group-rings>
			<p id="{id}-rings-lead" class="text-xs text-slate-700">{parts.rings.lead}</p>
			<ul class="mt-0.5 space-y-1 text-xs text-slate-700" aria-labelledby="{id}-rings-lead">
				{#each parts.rings.items as item (item.number)}
					<li class="flex gap-1">
						<span class="w-10 shrink-0"><CaseTag tag={item.number} /></span>
						<span class="min-w-0 wrap-break-word"
							><span class="font-medium text-slate-900">{item.name}</span>, {item.at}: {item.words}</span
						>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
	{#if parts.notOn}<p class="text-xs text-slate-700">{parts.notOn}</p>{/if}
	{#if parts.leftOut}<p class="text-xs text-slate-700">{parts.leftOut}</p>{/if}
</div>
