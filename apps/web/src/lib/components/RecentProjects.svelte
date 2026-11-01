<!--
	Recent projects on this device (utils/recent.ts; the owner's decision of 2026-11-01, proposal
	landing-page.md §3). Read after the page loads: the home page is prerendered, and the list is
	only in this browser. Nothing is shown while it is empty. Each entry opens its link; Forget
	removes one, Forget all removes the list.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { forgetAll, forgetProject, readRecent, type RecentProject } from '$lib/utils/recent';
	import Icon from './ui/Icon.svelte';
	import { projectHref } from './links';

	let entries = $state.raw<RecentProject[]>([]);
	let heading: HTMLElement | undefined = $state();

	onMount(() => {
		entries = readRecent();
	});

	const when = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
	function saved(entry: RecentProject): string {
		const date = new Date(entry.savedAt);
		return Number.isNaN(date.getTime()) ? '' : when.format(date);
	}

	function forget(entry: RecentProject) {
		entries = forgetProject(entry.id);
		// The button pressed is gone: keep focus in the section, or at its place.
		heading?.focus();
	}

	function forgetEvery() {
		forgetAll();
		entries = [];
	}
</script>

{#if entries.length}
	<section class="mt-8" aria-labelledby="recent-title">
		<div class="flex flex-wrap items-baseline justify-between gap-x-4">
			<h2 id="recent-title" class="text-lg font-semibold" tabindex="-1" bind:this={heading}>
				Recent on this device
			</h2>
			<button type="button" class="btn btn-quiet btn-tight text-sm" onclick={forgetEvery}>
				Forget all
			</button>
		</div>
		<p class="text-sm text-slate-600">Kept only in this browser, never sent anywhere.</p>
		<ul class="mt-2 divide-y divide-slate-200 rounded-md border border-slate-200">
			{#each entries as entry (entry.id)}
				<li class="flex items-center gap-2 pl-3">
					<a
						href={projectHref(entry.encoded)}
						class="flex min-h-11 min-w-0 flex-1 flex-col justify-center py-1.5 hover:text-blue-800"
					>
						<span class="truncate font-medium text-blue-800">{entry.name}</span>
						{#if saved(entry)}<span class="text-xs text-slate-600">{saved(entry)}</span>{/if}
					</a>
					<button
						type="button"
						class="btn btn-quiet btn-icon shrink-0"
						aria-label="Forget {entry.name}"
						title="Forget"
						onclick={() => forget(entry)}
					>
						<Icon name="close" />
					</button>
				</li>
			{/each}
		</ul>
	</section>
{/if}
