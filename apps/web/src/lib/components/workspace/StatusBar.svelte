<script lang="ts">
	import { components, solvedState, isSolved } from '$lib/stores';

	interface Props {
		isSolving?: boolean;
		solveError?: string | null;
	}

	let { isSolving = false, solveError = null }: Props = $props();

	let componentCount = $derived($components.length);
	let connectionCount = $derived(
		$components.reduce((sum, c) => sum + c.downstream_connections.length, 0)
	);

	function formatDuration(seconds: number | undefined): string {
		if (seconds === undefined) return '';
		if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
		return `${seconds.toFixed(2)}s`;
	}
</script>

<div class="flex h-full items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-[0.625rem]">
	<!-- Left: Status -->
	<div class="flex items-center gap-3">
		{#if isSolving}
			<span class="flex items-center gap-1 text-[var(--color-accent)]">
				<svg class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
				</svg>
				Solving...
			</span>
		{:else if solveError}
			<span class="flex items-center gap-1 text-[var(--color-error)]">
				<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				{solveError}
			</span>
		{:else if $isSolved && $solvedState?.converged}
			<span class="flex items-center gap-1 text-[var(--color-success)]">
				<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
				</svg>
				Converged
				{#if $solvedState?.solve_time_seconds}
					<span class="text-[var(--color-text-subtle)]">({formatDuration($solvedState.solve_time_seconds)})</span>
				{/if}
			</span>
		{:else if $isSolved && !$solvedState?.converged}
			<span class="flex items-center gap-1 text-[var(--color-error)]">
				<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
				Failed to converge
			</span>
		{:else}
			<span class="text-[var(--color-text-subtle)]">Ready</span>
		{/if}
	</div>

	<!-- Right: Stats -->
	<div class="flex items-center gap-3 text-[var(--color-text-subtle)]">
		<span>{componentCount} component{componentCount !== 1 ? 's' : ''}</span>
		<span>{connectionCount} connection{connectionCount !== 1 ? 's' : ''}</span>
		{#if $isSolved && $solvedState?.warnings?.length}
			<span class="text-[var(--color-warning)]">
				{$solvedState.warnings.length} warning{$solvedState.warnings.length !== 1 ? 's' : ''}
			</span>
		{/if}
	</div>
</div>
