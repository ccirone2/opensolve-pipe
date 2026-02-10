<script lang="ts">
	import { solvedState, components, pumpLibrary, workspaceStore, activeResultsView, type ResultsView } from '$lib/stores';
	import { isPump, isValve, type ValveComponent } from '$lib/models';

	// Counts for each category
	let componentCount = $derived(
		Object.keys($solvedState?.component_results ?? {}).length
	);
	let pipingCount = $derived(
		Object.keys($solvedState?.piping_results ?? {}).length
	);
	let pumpCount = $derived(
		Object.keys($solvedState?.pump_results ?? {}).length
	);
	let controlValveCount = $derived(
		Object.keys($solvedState?.control_valve_results ?? {}).length
	);
	let warningCount = $derived(
		($solvedState?.warnings ?? []).length
	);

	interface CategoryDef {
		id: ResultsView;
		label: string;
		icon: string;
		count: () => number;
		alwaysShow: boolean;
	}

	let categories = $derived.by((): CategoryDef[] => {
		const base: CategoryDef[] = [
			{
				id: 'summary',
				label: 'Summary',
				icon: 'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z',
				count: () => warningCount,
				alwaysShow: true
			},
			{
				id: 'nodes',
				label: 'Components',
				icon: 'M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6z',
				count: () => componentCount,
				alwaysShow: true
			},
			{
				id: 'links',
				label: 'Piping',
				icon: 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z',
				count: () => pipingCount,
				alwaysShow: true
			}
		];

		if (pumpCount > 0) {
			base.push({
				id: 'pumps',
				label: 'Pumps',
				icon: 'M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941',
				count: () => pumpCount,
				alwaysShow: false
			});
		}

		if (controlValveCount > 0) {
			base.push({
				id: 'valves',
				label: 'Control Valves',
				icon: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4',
				count: () => controlValveCount,
				alwaysShow: false
			});
		}

		base.push({
			id: 'elevation',
			label: 'Elevation Profile',
			icon: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z',
			count: () => $components.length,
			alwaysShow: true
		});

		return base;
	});

	function handleCategoryClick(id: ResultsView) {
		workspaceStore.setActiveResultsView(id);
	}
</script>

<div class="flex h-full flex-col bg-[var(--color-surface)]">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
		<span class="text-[0.6875rem] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
			Results
		</span>
	</div>

	<!-- Content -->
	<div class="flex-1 overflow-y-auto">
		{#if !$solvedState}
			<!-- No Results State -->
			<div class="flex flex-col items-center justify-center px-4 py-12 text-center">
				<svg class="h-10 w-10 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
					/>
				</svg>
				<p class="mt-3 text-xs text-[var(--color-text-muted)]">No results yet</p>
				<p class="mt-1 text-[0.6875rem] text-[var(--color-text-subtle)]">
					Solve the network to view results
				</p>
			</div>
		{:else}
			<!-- Convergence indicator -->
			<div class="border-b border-[var(--color-border)] px-3 py-2">
				{#if $solvedState.converged}
					<div class="flex items-center gap-2">
						<svg class="h-3.5 w-3.5 text-[var(--color-success)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
						</svg>
						<span class="text-xs font-medium text-[var(--color-success)]">Converged</span>
						<span class="ml-auto text-[0.625rem] text-[var(--color-text-subtle)]">
							{$solvedState.iterations} iter
						</span>
					</div>
				{:else}
					<div class="flex items-center gap-2">
						<svg class="h-3.5 w-3.5 text-[var(--color-error)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
						<span class="text-xs font-medium text-[var(--color-error)]">Failed</span>
					</div>
				{/if}
			</div>

			<!-- Category List -->
			{#each categories as cat}
				<button
					type="button"
					onclick={() => handleCategoryClick(cat.id)}
					class="flex w-full items-center gap-2 border-b border-[var(--color-border)] px-3 py-2 text-left transition-colors hover:bg-[var(--color-tree-hover)]
						{$activeResultsView === cat.id ? 'bg-[var(--color-tree-hover)]' : ''}"
				>
					<svg class="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d={cat.icon} />
					</svg>
					<span class="text-xs font-medium text-[var(--color-text)]">{cat.label}</span>
					<span class="ml-auto text-[0.625rem] text-[var(--color-text-subtle)]">
						{cat.count()}
					</span>
				</button>
			{/each}
		{/if}
	</div>
</div>
