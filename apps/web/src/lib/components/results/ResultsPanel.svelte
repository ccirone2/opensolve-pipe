<script lang="ts">
	import { solvedState, components, pumpLibrary } from '$lib/stores';
	import { isPump, isValve, WARNING_CATEGORY_LABELS, type Warning, type ValveComponent } from '$lib/models';
	import ComponentTable from './ComponentTable.svelte';
	import PipingTable from './PipingTable.svelte';
	import PumpResultsCard from './PumpResultsCard.svelte';
	import ControlValveResultsCard from './ControlValveResultsCard.svelte';

	interface Props {
		/** Whether a solve is currently in progress. */
		isLoading?: boolean;
	}

	let { isLoading = false }: Props = $props();

	type TabId = 'summary' | 'nodes' | 'links' | 'pumps' | 'valves';
	let activeTab: TabId = $state('summary');

	// Get pumps with their curves and results
	let pumpData = $derived.by(() => {
		const pumps = $components.filter(isPump);
		return pumps.map((pump) => {
			const curve = $pumpLibrary.find((c) => c.id === pump.curve_id);
			const result = $solvedState?.pump_results[pump.id];
			return { pump, curve, result };
		});
	});

	// Get control valves (PRV, PSV, FCV, TCV) with results
	let controlValveData = $derived.by(() => {
		const controlValveTypes = ['prv', 'psv', 'fcv', 'tcv'];
		const valves = $components.filter(
			(c): c is ValveComponent =>
				isValve(c) && controlValveTypes.includes(c.valve_type)
		);
		return valves.map((valve) => {
			const result = $solvedState?.control_valve_results[valve.id];
			return { valve, result };
		});
	});

	// Group warnings by severity
	let errorWarnings = $derived(
		$solvedState?.warnings.filter((w) => w.severity === 'error') ?? []
	);
	let warningWarnings = $derived(
		$solvedState?.warnings.filter((w) => w.severity === 'warning') ?? []
	);
	let infoWarnings = $derived(
		$solvedState?.warnings.filter((w) => w.severity === 'info') ?? []
	);

	// Dynamically build tabs based on what exists
	let tabs = $derived.by(() => {
		const baseTabs: { id: TabId; label: string }[] = [
			{ id: 'summary', label: 'Summary' },
			{ id: 'nodes', label: 'Components' },
			{ id: 'links', label: 'Piping' }
		];

		// Only show Pumps tab if there are pumps
		if (pumpData.length > 0) {
			baseTabs.push({ id: 'pumps', label: 'Pumps' });
		}

		// Only show Valves tab if there are control valves
		if (controlValveData.length > 0) {
			baseTabs.push({ id: 'valves', label: 'Valves' });
		}

		return baseTabs;
	});

	function formatDuration(seconds: number | undefined): string {
		if (seconds === undefined) return '-';
		if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`;
		return `${seconds.toFixed(2)} s`;
	}

	function getWarningIcon(severity: Warning['severity']): string {
		switch (severity) {
			case 'error':
				return 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';
			case 'warning':
				return 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z';
			default:
				return 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';
		}
	}
</script>

<div class="flex h-full flex-col">
	{#if isLoading}
		<!-- Loading State -->
		<div class="flex flex-1 flex-col items-center justify-center p-8">
			<div class="h-12 w-12 animate-spin rounded-full border-4 border-[var(--color-accent)] border-t-transparent"></div>
			<p class="mt-4 text-sm text-[var(--color-text-muted)]">Solving network...</p>
		</div>
	{:else if !$solvedState}
		<!-- No Results State -->
		<div class="flex flex-1 flex-col items-center justify-center p-8 text-center">
			<svg class="h-16 w-16 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
				/>
			</svg>
			<h3 class="mt-4 text-lg font-medium text-[var(--color-text)]">No results yet</h3>
			<p class="mt-2 text-sm text-[var(--color-text-muted)]">
				Click "Solve" to calculate pressures and flows in your network.
			</p>
		</div>
	{:else}
		<!-- Tab Navigation -->
		<div class="border-b border-[var(--color-border)] bg-[var(--color-surface-elevated)]">
			<nav class="flex -mb-px" aria-label="Tabs">
				{#each tabs as tab}
					<button
						type="button"
						onclick={() => (activeTab = tab.id)}
						class="flex-1 border-b-2 py-3 text-center text-sm font-medium transition-colors
							{activeTab === tab.id
							? 'border-[var(--color-accent)] text-[var(--color-accent)]'
							: 'border-transparent text-[var(--color-text-muted)] hover:border-[var(--color-border)] hover:text-[var(--color-text)]'}"
					>
						{tab.label}
					</button>
				{/each}
			</nav>
		</div>

		<!-- Tab Content -->
		<div class="flex-1 overflow-y-auto p-4">
			{#if activeTab === 'summary'}
				<!-- Convergence Status -->
				<div
					class="rounded-lg border p-4
						{$solvedState.converged ? 'border-[var(--color-success)]/30 bg-[var(--color-success)]/10' : 'border-[var(--color-error)]/30 bg-[var(--color-error)]/10'}"
				>
					<div class="flex items-center gap-3">
						{#if $solvedState.converged}
							<svg class="h-6 w-6 text-[var(--color-success)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
							</svg>
							<div>
								<p class="font-medium text-[var(--color-success)]">Solution Converged</p>
								<p class="text-sm text-[var(--color-success)]/80">
									{$solvedState.iterations} iterations in {formatDuration($solvedState.solve_time_seconds)}
								</p>
							</div>
						{:else}
							<svg class="h-6 w-6 text-[var(--color-error)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
							</svg>
							<div>
								<p class="font-medium text-[var(--color-error)]">Solution Failed</p>
								<p class="text-sm text-[var(--color-error)]/80">
									{$solvedState.error || 'Unknown error'}
								</p>
							</div>
						{/if}
					</div>
				</div>

				<!-- Warnings -->
				{#if $solvedState.warnings.length > 0}
					<div class="mt-4 space-y-3">
						<h4 class="text-sm font-medium text-[var(--color-text)]">Warnings & Messages</h4>

						{#each errorWarnings as warning}
							<div class="flex items-start gap-3 rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 p-3">
								<svg class="h-5 w-5 flex-shrink-0 text-[var(--color-error)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={getWarningIcon('error')} />
								</svg>
								<div>
									<p class="text-sm font-medium text-[var(--color-error)]">{warning.message}</p>
									<p class="text-xs text-[var(--color-error)]/80">{WARNING_CATEGORY_LABELS[warning.category]}</p>
								</div>
							</div>
						{/each}

						{#each warningWarnings as warning}
							<div class="flex items-start gap-3 rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 p-3">
								<svg class="h-5 w-5 flex-shrink-0 text-[var(--color-warning)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={getWarningIcon('warning')} />
								</svg>
								<div>
									<p class="text-sm font-medium text-[var(--color-warning)]">{warning.message}</p>
									<p class="text-xs text-[var(--color-warning)]/80">{WARNING_CATEGORY_LABELS[warning.category]}</p>
								</div>
							</div>
						{/each}

						{#each infoWarnings as warning}
							<div class="flex items-start gap-3 rounded-lg border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10 p-3">
								<svg class="h-5 w-5 flex-shrink-0 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={getWarningIcon('info')} />
								</svg>
								<div>
									<p class="text-sm font-medium text-[var(--color-accent)]">{warning.message}</p>
									<p class="text-xs text-[var(--color-accent)]/80">{WARNING_CATEGORY_LABELS[warning.category]}</p>
								</div>
							</div>
						{/each}
					</div>
				{/if}

				<!-- Quick Stats -->
				{#if $solvedState.converged}
					<div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
						<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Components</p>
							<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
								{Object.keys($solvedState.component_results).length}
							</p>
						</div>
						<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Piping</p>
							<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
								{Object.keys($solvedState.piping_results).length}
							</p>
						</div>
						<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Pumps</p>
							<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
								{Object.keys($solvedState.pump_results).length}
							</p>
						</div>
						<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Ctrl Valves</p>
							<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
								{Object.keys($solvedState.control_valve_results).length}
							</p>
						</div>
						<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Warnings</p>
							<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
								{$solvedState.warnings.length}
							</p>
						</div>
					</div>
				{/if}
			{:else if activeTab === 'nodes'}
				<ComponentTable results={$solvedState} />
			{:else if activeTab === 'links'}
				<PipingTable results={$solvedState} />
			{:else if activeTab === 'pumps'}
				{#if pumpData.length === 0}
					<div class="flex flex-col items-center justify-center py-12 text-center">
						<svg class="h-12 w-12 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
							/>
						</svg>
						<p class="mt-4 text-sm text-[var(--color-text-muted)]">No pumps in this network</p>
					</div>
				{:else}
					<div class="space-y-6">
						{#each pumpData as { pump, curve, result }}
							{#if result}
								<PumpResultsCard {pump} {curve} {result} />
							{:else}
								<div class="rounded-lg border border-[var(--color-border)] p-4">
									<h4 class="text-sm font-medium text-[var(--color-text)]">{pump.name}</h4>
									<p class="mt-2 text-sm text-[var(--color-text-muted)]">No results available</p>
								</div>
							{/if}
						{/each}
					</div>
				{/if}
			{:else if activeTab === 'valves'}
				{#if controlValveData.length === 0}
					<div class="flex flex-col items-center justify-center py-12 text-center">
						<svg class="h-12 w-12 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
							/>
						</svg>
						<p class="mt-4 text-sm text-[var(--color-text-muted)]">No control valves in this network</p>
					</div>
				{:else}
					<div class="space-y-4">
						{#each controlValveData as { valve, result }}
							{#if result}
								<ControlValveResultsCard {valve} {result} />
							{:else}
								<div class="rounded-lg border border-[var(--color-border)] p-4">
									<h4 class="text-sm font-medium text-[var(--color-text)]">{valve.name}</h4>
									<p class="mt-2 text-sm text-[var(--color-text-muted)]">No results available</p>
								</div>
							{/if}
						{/each}
					</div>
				{/if}
			{/if}
		</div>
	{/if}
</div>
