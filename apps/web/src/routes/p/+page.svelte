<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { encodeProject } from '$lib/utils';
	import { projectStore } from '$lib/stores';
	import { get } from 'svelte/store';

	// /p/ with no encoded data = new project.
	// Generate an empty project URL and redirect.
	onMount(() => {
		const project = get(projectStore);
		const result = encodeProject(project);
		goto(`/p/${result.encoded}`, { replaceState: true });
	});
</script>

<div class="flex h-screen items-center justify-center bg-[var(--color-bg)]">
	<div class="flex flex-col items-center gap-3">
		<svg class="h-8 w-8 animate-spin text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
		</svg>
		<p class="text-xs text-[var(--color-text-muted)]">Creating new project...</p>
	</div>
</div>
