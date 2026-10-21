<!--
	Shown when the project was last solved with a different calculation-method version than these
	results: values may differ from the ones the link was shared with. Lists what changed between
	the two versions (GET /api/v1/method-versions).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { compareVersions, versionsBetween } from '$lib/utils/results';

	interface Props {
		/** Version the project carried when it was opened. */
		previous: string;
		/** Version of these results. */
		current: string;
	}

	let { previous, current }: Props = $props();
	const ws = useWorkspace();
	const library = ws.library;
	const id = $props.id();

	// Once, when the notice appears (not an effect: a failed load must not retry by itself).
	onMount(() => {
		void library.loadMethodVersions();
	});

	const newer = $derived(compareVersions(current, previous) > 0);
	let heading: HTMLHeadingElement | undefined = $state();

	/** The button goes away while loading: keep focus in the notice, on its heading. */
	function retry() {
		heading?.focus();
		void library.loadMethodVersions(true);
	}
	const changes = $derived(
		library.methodVersions
			? versionsBetween(library.methodVersions.versions, previous, current)
			: []
	);
</script>

<section
	class="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950"
	aria-labelledby="{id}-title"
>
	<h3
		bind:this={heading}
		id="{id}-title"
		tabindex="-1"
		class="flex items-center gap-2 font-semibold"
	>
		<Icon name="alert" class="size-4 shrink-0" /> Calculation methods changed
	</h3>
	<p>
		This project was last solved with calculation methods version {previous}. These results use
		version {current}{newer ? '' : ', an older version'}, so some values may differ from the ones it
		was shared with.
	</p>
	<!-- The outcome of loading the list is announced; the list itself is not read out. -->
	<p role="status" class="empty:hidden">
		{#if library.methodVersionsStatus === 'ready'}
			{changes.length
				? 'What changed:'
				: 'The calculation server lists no changes between these versions.'}
		{:else if library.methodVersionsStatus === 'unavailable'}
			The list of changes could not be loaded: {library.methodVersionsMessage}
		{:else}
			Loading the list of changes…
		{/if}
	</p>
	{#if library.methodVersionsStatus === 'ready' && changes.length}
		<ul class="space-y-2">
			{#each changes as version (version.version)}
				<li>
					<p class="font-medium">Version {version.version} ({version.date})</p>
					<ul class="list-disc pl-5">
						{#each version.changes as change, i (i)}
							<li>{change}</li>
						{/each}
					</ul>
				</li>
			{/each}
		</ul>
	{:else if library.methodVersionsStatus === 'unavailable'}
		<button type="button" class="btn" onclick={retry}>Try again</button>
	{/if}
</section>
