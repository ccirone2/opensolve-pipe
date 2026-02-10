<script lang="ts">
	import { page } from '$app/stores';

	let encoded = $derived($page.params.encoded || '');
</script>

<svelte:head>
	<title>Cost Estimation - OpenSolve Pipe</title>
</svelte:head>

<div class="flex h-screen flex-col items-center justify-center gap-6 bg-[var(--color-bg)] p-8">
	<div class="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-10 text-center">
		<svg class="mx-auto h-12 w-12 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1">
			<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
		</svg>
		<h2 class="mt-4 text-lg font-semibold text-[var(--color-text)]">Cost Estimation</h2>
		<p class="mt-2 text-sm text-[var(--color-text-muted)]">
			Material costs, labor estimates, and project budgeting. Coming soon.
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
