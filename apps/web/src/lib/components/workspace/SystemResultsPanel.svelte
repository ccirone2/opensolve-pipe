<script lang="ts">
	import { components, solvedState, isSolved } from '$lib/stores';
	import { COMPONENT_CATEGORIES } from '$lib/models';

	interface Props {
		onSolve?: () => void;
	}

	let { onSolve }: Props = $props();

	// Component count by category
	let categoryCounts = $derived.by(() => {
		const counts = { sources: 0, equipment: 0, connections: 0 };
		for (const c of $components) {
			if ((COMPONENT_CATEGORIES.Sources as string[]).includes(c.type)) counts.sources++;
			else if ((COMPONENT_CATEGORIES.Equipment as string[]).includes(c.type)) counts.equipment++;
			else counts.connections++;
		}
		return counts;
	});

	// Warnings
	let warnings = $derived($solvedState?.warnings ?? []);

	function formatDuration(seconds: number | undefined): string {
		if (seconds === undefined) return '-';
		if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
		return `${seconds.toFixed(2)}s`;
	}

	function formatNumber(val: number | null | undefined, decimals = 2): string {
		if (val === null || val === undefined) return '-';
		return val.toFixed(decimals);
	}
</script>

<div class="flex flex-col gap-2 p-2">
	{#if !$isSolved}
		<!-- Not solved state -->
		<div class="flex flex-col items-center gap-3 py-8 text-center">
			<svg class="h-10 w-10 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1">
				<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
			</svg>
			<div>
				<p class="text-xs font-medium text-[var(--color-text)]">Not yet solved</p>
				<p class="mt-0.5 text-[0.625rem] text-[var(--color-text-subtle)]">
					{$components.length} component{$components.length !== 1 ? 's' : ''} in network
				</p>
			</div>
			{#if $components.length > 0}
				<button
					type="button"
					onclick={onSolve}
					class="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-accent)] px-4 py-1.5 text-xs font-semibold text-[var(--color-accent-text)] transition-colors hover:bg-[var(--color-accent-hover)]"
				>
					<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728M9.172 15.172a4 4 0 010-5.656m5.656 0a4 4 0 010 5.656M12 12h.01" />
					</svg>
					Solve Network
				</button>
			{/if}
		</div>
	{:else}
		<!-- Solve Status -->
		<div class="card p-2.5">
			<div class="flex items-center justify-between">
				<span class="section-heading">
					Status
				</span>
				{#if $solvedState?.converged}
					<span class="flex items-center gap-1 text-xs font-medium text-[var(--color-success)]">
						<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
						</svg>
						Converged
					</span>
				{:else}
					<span class="flex items-center gap-1 text-xs font-medium text-[var(--color-error)]">
						<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
						Failed
					</span>
				{/if}
			</div>
			{#if $solvedState?.solve_time_seconds}
				<p class="mt-1 text-[0.625rem] text-[var(--color-text-subtle)]">
					Solve time: {formatDuration($solvedState.solve_time_seconds)}
				</p>
			{/if}
		</div>

		<!-- Component Summary -->
		<div class="card p-2.5">
			<h4 class="mb-2 section-heading">
				Components
			</h4>
			<div class="grid grid-cols-3 gap-2 text-center">
				<div>
					<p class="mono-value text-sm font-semibold text-[var(--color-badge-source-text)]">{categoryCounts.sources}</p>
					<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Sources</p>
				</div>
				<div>
					<p class="mono-value text-sm font-semibold text-[var(--color-badge-equipment-text)]">{categoryCounts.equipment}</p>
					<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Equipment</p>
				</div>
				<div>
					<p class="mono-value text-sm font-semibold text-[var(--color-badge-connection-text)]">{categoryCounts.connections}</p>
					<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Connections</p>
				</div>
			</div>
		</div>

		<!-- Per-Component Results Table -->
		{#if $solvedState?.component_results}
			<div class="card p-2.5">
				<h4 class="mb-2 section-heading">
					Node Results
				</h4>
				<div class="overflow-x-auto">
					<table class="w-full text-[0.625rem]">
						<thead>
							<tr class="text-left text-[var(--color-text-subtle)]">
								<th class="pb-1 pr-2 font-medium">Name</th>
								<th class="pb-1 pr-2 font-medium">Pressure</th>
								<th class="pb-1 font-medium">HGL</th>
							</tr>
						</thead>
						<tbody>
							{#each $components as comp}
								{@const result = $solvedState?.component_results?.[comp.id]}
								{#if result}
									<tr class="border-t border-[var(--color-border-subtle)]">
										<td class="truncate py-1 pr-2 text-[var(--color-text)]">{comp.name}</td>
										<td class="py-1 pr-2 mono-value text-[var(--color-text)]">
											{formatNumber(result.pressure)}
										</td>
										<td class="py-1 mono-value text-[var(--color-text)]">
											{formatNumber(result.hgl)}
										</td>
									</tr>
								{/if}
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}

		<!-- Piping Results -->
		{#if $solvedState?.piping_results}
			<div class="card p-2.5">
				<h4 class="mb-2 section-heading">
					Flow Results
				</h4>
				<div class="overflow-x-auto">
					<table class="w-full text-[0.625rem]">
						<thead>
							<tr class="text-left text-[var(--color-text-subtle)]">
								<th class="pb-1 pr-2 font-medium">Name</th>
								<th class="pb-1 pr-2 font-medium">Flow</th>
								<th class="pb-1 font-medium">Velocity</th>
							</tr>
						</thead>
						<tbody>
							{#each $components as comp}
								{@const result = $solvedState?.piping_results?.[comp.id]}
								{#if result}
									<tr class="border-t border-[var(--color-border-subtle)]">
										<td class="truncate py-1 pr-2 text-[var(--color-text)]">{comp.name}</td>
										<td class="py-1 pr-2 mono-value text-[var(--color-text)]">
											{formatNumber(result.flow)}
										</td>
										<td class="py-1 mono-value text-[var(--color-text)]">
											{formatNumber(result.velocity)}
										</td>
									</tr>
								{/if}
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}

		<!-- Warnings -->
		{#if warnings.length > 0}
			<div class="rounded border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5 p-2.5">
				<h4 class="mb-2 section-heading text-[var(--color-warning)]">
					Warnings ({warnings.length})
				</h4>
				<div class="space-y-1">
					{#each warnings as warning}
						<p class="text-[0.625rem] text-[var(--color-text-muted)]">
							{warning.message ?? JSON.stringify(warning)}
						</p>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Re-solve button -->
		<button
			type="button"
			onclick={onSolve}
			class="mt-1 w-full rounded bg-[var(--color-surface-elevated)] py-1.5 text-xs font-medium text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-muted)] hover:text-[var(--color-accent)]"
		>
			Re-solve Network
		</button>
	{/if}
</div>
