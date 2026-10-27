<!--
	Results → Checks (CLAUDE.md D19; proposal design-checks.md §5): the opt-in design checks of a
	solve, not met first, then met, then not evaluated with the reason. Each names its element (a
	link to its results and trace; a connection as solved, as the flags name it), says the value
	against its limits in display units (utils/design-checks.ts), where the limit came from, and
	keeps the API's own words (SI) under Details. Checks are design practice, not flags: they
	never mark the Results tab and never change a value.
-->
<script lang="ts">
	import type { DesignCheckResult, SolvedState } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		CHECK_TITLES,
		checkElement,
		checkText,
		groupChecks,
		OUTCOME_TITLES,
		sourceLabel
	} from '$lib/utils/design-checks';
	import { designCheckPresets } from '$lib/utils/model-rules';
	import { elementName, resultsProject, type ElementRef } from '$lib/utils/results';

	interface Props {
		solved: SolvedState;
	}

	let { solved }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const results = $derived<readonly DesignCheckResult[]>(solved.designChecks ?? []);
	const groups = $derived(groupChecks(results));
	const nameOf = (element: ElementRef) =>
		element.kind === 'connection'
			? elementName(resultsProject(ws.labelsProject, solved), element)
			: elementName(ws.project, element);
	/** The presets these results used, with their citations, listed once below. */
	const presets = $derived(
		designCheckPresets().filter((p) => results.some((r) => r.source === p.citation))
	);

	const MARKS = { fail: '✕', pass: '✓', not_evaluated: '–' } as const;
</script>

<div class="space-y-3 text-sm">
	<p class="text-slate-700">
		Design practice you turned on (Settings → Design checks), not physics: a check never changes a
		result or raises a flag.
	</p>
	{#each groups as group (group.outcome)}
		<section
			class={[
				'rounded-lg border p-2',
				group.outcome === 'fail' ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-white'
			]}
			aria-labelledby="{id}-{group.outcome}"
		>
			<h3 id="{id}-{group.outcome}" class="flex items-center gap-2 px-1 font-semibold">
				<span
					aria-hidden="true"
					class={group.outcome === 'fail'
						? 'text-amber-800'
						: group.outcome === 'pass'
							? 'text-green-800'
							: 'text-slate-500'}>{MARKS[group.outcome]}</span
				>
				{OUTCOME_TITLES[group.outcome]} ({group.results.length})
			</h3>
			<ul class="mt-1 space-y-1">
				{#each group.results as result, i (i)}
					{@const element = checkElement(result)}
					{@const text = checkText(result, ws.displayUnits)}
					<li class="rounded px-1 py-1.5">
						<div class="flex flex-wrap items-baseline gap-x-2">
							{#if element}
								<button
									type="button"
									class="min-h-11 text-left font-medium break-words text-blue-800 underline underline-offset-2"
									onclick={() => ws.inspect(element)}>{nameOf(element)}</button
								>
							{/if}
							<span class="text-slate-600">{CHECK_TITLES[result.check]}</span>
						</div>
						<p class="break-words text-slate-800">{text}</p>
						<details class="text-xs text-slate-600">
							<!-- 16 px line + 2 × 14 px padding: a 44 px target. -->
							<summary class="cursor-pointer py-3.5">
								Limits: {sourceLabel(result.source)} · Details
							</summary>
							<p class="pb-1 break-words">{result.message}</p>
						</details>
					</li>
				{/each}
			</ul>
		</section>
	{/each}
	{#if presets.length}
		<section class="text-xs text-slate-700" aria-labelledby="{id}-sources">
			<h3 id="{id}-sources" class="font-medium">Sources of the presets</h3>
			<ul class="mt-1 list-disc space-y-1 pl-5">
				{#each presets as preset (preset.id)}
					<li class="break-words">{preset.citation}</li>
				{/each}
			</ul>
		</section>
	{/if}
	<p class="text-xs text-slate-600">
		The operating region compares the flow with the best efficiency flow at the running speed. The
		pump curve's manufacturer data are at rated speed, so the flow is compared as its rated-speed
		equivalent, flow ÷ speed (affinity laws). Velocity is checked in every pipe of a connection.
	</p>
</div>
