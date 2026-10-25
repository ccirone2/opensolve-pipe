<!--
	Methods and assumptions of a solve (trace.methods), as a block that reads well on screen and in
	print, with "Copy as text" for pasting into a report. Without clipboard access the text is shown
	selected, to copy by hand.
-->
<script lang="ts">
	import type { MethodsSummary } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { methodsText } from '$lib/utils/trace';

	interface Props {
		methods: MethodsSummary;
		projectName?: string;
		/** When the solve ran (ISO 8601). */
		timestamp?: string;
		/** Whether the solve converged: the copied text says so either way. */
		converged?: boolean;
		/** True when the project changed after the solve: the copied text says so. */
		stale?: boolean;
		/**
		 * The case solved, for a project with scenarios ("scenario Winter (S2)", "base case"): the
		 * heading and the copied text name it.
		 */
		caseName?: string;
		/** The scenario's name, for the heading ("for scenario Winter"). */
		scenarioName?: string;
	}

	let {
		methods,
		projectName,
		timestamp,
		converged,
		stale = false,
		caseName,
		scenarioName
	}: Props = $props();
	const id = $props.id();
	let status = $state<'idle' | 'copied' | 'manual'>('idle');
	let area: HTMLTextAreaElement | undefined = $state();

	const text = $derived(
		methodsText(methods, {
			projectName,
			...(caseName ? { caseName } : {}),
			timestamp,
			stale,
			...(converged === undefined ? {} : { converged })
		})
	);
	const libraries = $derived(Object.entries(methods.libraries));

	async function copy() {
		try {
			if (!navigator.clipboard?.writeText) throw new Error('no clipboard');
			await navigator.clipboard.writeText(text);
			status = 'copied';
		} catch {
			status = 'manual';
		}
	}

	$effect(() => {
		if (status === 'manual' && area) {
			area.focus();
			area.select();
		}
	});
</script>

<article class="card space-y-4 p-3 sm:p-4" aria-labelledby="{id}-title">
	<div class="flex flex-wrap items-start gap-2">
		<div class="min-w-0 flex-1 basis-48">
			<h3 id="{id}-title" class="font-semibold">
				Calculation methods and assumptions{scenarioName ? ` for scenario ${scenarioName}` : ''}
			</h3>
			<p class="text-sm text-slate-600">
				OpenSolve Pipe calculation methods version {methods.methodVersion}
			</p>
		</div>
		<button type="button" class="btn shrink-0 print:hidden" onclick={copy}>
			<Icon name="copy" class="size-4" /> Copy as text
		</button>
	</div>
	{#if converged === false}
		<p class="rounded-md border border-red-300 bg-red-50 p-2 text-sm font-medium text-red-900">
			This solve did not converge: its values are not a solution of the network. The copied text
			says so.
		</p>
	{/if}
	{#if stale}
		<p class="rounded-md border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900">
			The project changed after this solve. The copied text says so; solve again before using it.
		</p>
	{/if}
	<p role="status" class="text-sm empty:hidden print:hidden">
		{#if status === 'copied'}Copied to the clipboard.{:else if status === 'manual'}Copy the text
			below.{/if}
	</p>
	{#if status === 'manual'}
		<label class="block print:hidden">
			<span class="label mb-1">Methods as text</span>
			<textarea bind:this={area} class="input h-48 font-mono text-xs" readonly value={text}
			></textarea>
		</label>
	{/if}

	{#if !methods.sections.length && !methods.assumptions.length}
		<p class="text-sm text-slate-700">This solve did not return a methods summary.</p>
	{/if}

	{#each methods.sections as section, i (i)}
		<section class="space-y-1" aria-labelledby="{id}-s{i}">
			<h4 id="{id}-s{i}" class="text-sm font-semibold">{section.title}</h4>
			<ul class="list-disc space-y-1 pl-5 text-sm text-slate-800">
				{#each section.items as item, j (j)}
					<li class="break-words">{item}</li>
				{/each}
			</ul>
			{#if section.references.length}
				<p class="pt-1 text-xs font-medium text-slate-600">References</p>
				<ul class="space-y-0.5 pl-5 text-xs break-words text-slate-600">
					{#each section.references as reference, j (j)}
						<li class="list-[square]">{reference}</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}

	{#if methods.assumptions.length}
		<section class="space-y-1" aria-labelledby="{id}-assumptions">
			<h4 id="{id}-assumptions" class="text-sm font-semibold">Assumptions</h4>
			<ul class="list-disc space-y-1 pl-5 text-sm text-slate-800">
				{#each methods.assumptions as item, j (j)}
					<li>{item}</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if libraries.length}
		<section class="space-y-1" aria-labelledby="{id}-libraries">
			<h4 id="{id}-libraries" class="text-sm font-semibold">Software</h4>
			<dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-sm">
				{#each libraries as [name, version] (name)}
					<dt class="text-slate-700">{name}</dt>
					<dd class="tabular-nums">{version}</dd>
				{/each}
			</dl>
		</section>
	{/if}
</article>
