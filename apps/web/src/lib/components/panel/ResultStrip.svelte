<!--
	Results in context (proposal ui-ux-refinement.md item 6): the current element's key results
	from the last solve of the case shown, beside its inputs in Build, so checking what an edit did
	needs no trip to the Results pane. The values are the results tables' own cells
	(utils/results.ts elementSummary), with their units and notes; the element's flags follow, and
	Trace opens its full results and trace (on narrow screens in the Results pane, where the trace
	is shown).

	Nothing is shown before a first solve, or after a solve of the current project that failed (the
	Results pane has the error). After edits the values stay, marked out of date. A solve that did
	not converge has no values here, only that statement: its numbers are not a solution.

	A labelled group ("Last solve: <element>"), not a region: two per panel would add landmarks.
-->
<script lang="ts">
	import FlagIcon from '$lib/components/results/FlagIcon.svelte';
	import CellValue from '$lib/components/results/CellValue.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { mediaQuery, WIDE_SCREEN } from '$lib/utils/media.svelte';
	import { elementName, elementSummary, type ElementRef } from '$lib/utils/results';

	let { element }: { element: ElementRef } = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const wide = mediaQuery(WIDE_SCREEN);

	/** Flags listed here; the rest are in the trace. */
	const SHOWN_FLAGS = 2;

	const results = $derived(ws.store.results);
	const solved = $derived(results.response?.solvedState);
	/** The latest solve was of the current project and failed: the Results pane says why. */
	const failedNow = $derived(!!results.error && !results.errorStale);
	const converged = $derived(!!results.response?.success && !!solved?.converged);
	const summary = $derived(
		solved && converged
			? elementSummary(ws.labelsProject, solved, ws.displayUnits, element, ws.store.caseInputs())
			: null
	);
	const name = $derived(elementName(ws.labelsProject, element));

	function openTrace() {
		// On narrow screens the trace is shown from the Results pane.
		if (!wide.current) ws.pane = 'results';
		ws.inspected = element;
	}
</script>

{#if solved && !failedNow}
	<div
		role="group"
		aria-labelledby="{id}-title"
		class={[
			'rounded-md border px-3 py-1 text-sm',
			results.stale ? 'border-dashed border-slate-300' : 'border-slate-200 bg-slate-50'
		]}
	>
		<div class="flex flex-wrap items-center gap-x-2">
			<h3 id="{id}-title" class="text-xs font-semibold tracking-wide text-slate-600 uppercase">
				Last solve<span class="sr-only">: {name}</span>
			</h3>
			{#if results.stale}
				<span class="rounded-full bg-amber-100 px-2 text-xs font-medium text-amber-900">
					Out of date: solve again
				</span>
			{/if}
			<span class="flex-1"></span>
			{#if summary}
				<button
					type="button"
					class="btn btn-quiet px-2 text-blue-800"
					aria-label="Trace of {name}"
					onclick={openTrace}
				>
					Trace
				</button>
			{/if}
		</div>
		{#if !converged}
			<p class="pb-2 text-slate-700">
				The last solve did not converge, so it has no values to show here: the Results pane says
				where to look.
			</p>
		{:else if !summary}
			<p class="pb-2 text-slate-700">Not in the last solve: solve again to see its results.</p>
		{:else}
			<dl
				class={[
					'grid grid-cols-2 gap-x-4 gap-y-1 pb-2 sm:grid-cols-4',
					results.stale && 'text-slate-500'
				]}
			>
				{#each summary.items as item (item.key)}
					<div class="min-w-0">
						<dt class="text-xs text-slate-600">
							{item.label}{#if item.unit}&nbsp;({item.unit}){/if}
						</dt>
						<dd class="font-medium break-words tabular-nums"><CellValue cell={item.cell} /></dd>
					</div>
				{/each}
			</dl>
			{#if summary.flags.length}
				<ul class="space-y-1 pb-2">
					{#each summary.flags.slice(0, SHOWN_FLAGS) as flag, i (i)}
						<li class="flex items-start gap-2">
							<FlagIcon severity={flag.severity} class="mt-0.5 size-4" />
							<span class="min-w-0 flex-1 break-words">{ws.flagText(flag)}</span>
						</li>
					{/each}
					{#if summary.flags.length > SHOWN_FLAGS}
						<li class="text-slate-600">
							{summary.flags.length - SHOWN_FLAGS} more in the trace.
						</li>
					{/if}
				</ul>
			{/if}
		{/if}
	</div>
{/if}
