<script lang="ts">
	import { page } from '$app/stores';

	let encoded = $derived($page.params.encoded || '');
</script>

<svelte:head>
	<title>Results - OpenSolve Pipe</title>
</svelte:head>

<div class="flex h-screen flex-col items-center justify-center gap-6 bg-[var(--color-bg)] p-8">
	<div class="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-10 text-center">
		<svg class="mx-auto h-12 w-12 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1">
			<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
		</svg>
		<h2 class="mt-4 text-lg font-semibold text-[var(--color-text)]">Detailed Results View</h2>
		<p class="mt-2 text-sm text-[var(--color-text-muted)]">
			Full-screen results analysis with charts and tables. Coming soon.
		</p>
		<a
			href="/p/{encoded}"
			class="mt-6 inline-flex items-center gap-2 rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-accent-text)] transition-colors hover:bg-[var(--color-accent-hover)]"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
			</svg>
			Back to Workspace
		</a>
	</div>
</div>
