<script lang="ts">
	import { solvedState, components, connections, pumpLibrary, workspaceStore, type ResultsView } from '$lib/stores';
	import { isPump, isValve, WARNING_CATEGORY_LABELS, type Warning, type ValveComponent } from '$lib/models';
	import ComponentTable from './ComponentTable.svelte';
	import PipingTable from './PipingTable.svelte';
	import PumpResultsCard from './PumpResultsCard.svelte';
	import ControlValveResultsCard from './ControlValveResultsCard.svelte';
	import ElevationProfile from './ElevationProfile.svelte';
	import { buildElevationData } from '$lib/utils/elevationProfile';

	interface Props {
		view: ResultsView;
	}

	let { view }: Props = $props();

	// View labels for breadcrumb
	const viewLabels: Record<ResultsView, string> = {
		summary: 'Summary',
		nodes: 'Components',
		links: 'Piping',
		pumps: 'Pumps',
		valves: 'Control Valves',
		elevation: 'Elevation Profile'
	};

	// Pump data
	let pumpData = $derived.by(() => {
		const pumps = $components.filter(isPump);
		return pumps.map((pump) => {
			const curve = $pumpLibrary.find((c) => c.id === pump.curve_id);
			const result = $solvedState?.pump_results?.[pump.id];
			return { pump, curve, result };
		});
	});

	// Control valve data
	let controlValveData = $derived.by(() => {
		const controlValveTypes = ['prv', 'psv', 'fcv', 'tcv'];
		const valves = $components.filter(
			(c): c is ValveComponent =>
				isValve(c) && controlValveTypes.includes(c.valve_type)
		);
		return valves.map((valve) => {
			const result = $solvedState?.control_valve_results?.[valve.id];
			return { valve, result };
		});
	});

	// Elevation profile data
	let elevationData = $derived(buildElevationData($components, $connections, $solvedState));

	// Warnings grouped by severity
	let errorWarnings = $derived(
		$solvedState?.warnings?.filter((w) => w.severity === 'error') ?? []
	);
	let warningWarnings = $derived(
		$solvedState?.warnings?.filter((w) => w.severity === 'warning') ?? []
	);
	let infoWarnings = $derived(
		$solvedState?.warnings?.filter((w) => w.severity === 'info') ?? []
	);

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

	function handleClose() {
		workspaceStore.setActiveResultsView(null);
	}
</script>

<div class="flex h-full flex-col bg-[var(--color-surface)]">
	<!-- Top Bar: Breadcrumb + Close -->
	<div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2">
		<!-- Breadcrumb -->
		<div class="flex items-center gap-1 text-xs">
			<button
				type="button"
				onclick={handleClose}
				class="text-[var(--color-accent)] hover:underline"
			>Results</button>
			<span class="text-[var(--color-text-subtle)]">/</span>
			<span class="font-medium text-[var(--color-text)]">{viewLabels[view]}</span>
		</div>

		<!-- Close Button -->
		<button
			type="button"
			onclick={handleClose}
			class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
			title="Close"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
			</svg>
		</button>
	</div>

	<!-- View Content -->
	<div class="min-h-0 flex-1 overflow-y-auto p-4">
		{#if !$solvedState}
			<div class="flex flex-col items-center justify-center py-12 text-center">
				<p class="text-sm text-[var(--color-text-muted)]">No results available</p>
			</div>
		{:else if view === 'summary'}
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
			{#if ($solvedState.warnings ?? []).length > 0}
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
							{Object.keys($solvedState.component_results ?? {}).length}
						</p>
					</div>
					<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Piping</p>
						<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
							{Object.keys($solvedState.piping_results ?? {}).length}
						</p>
					</div>
					<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Pumps</p>
						<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
							{Object.keys($solvedState.pump_results ?? {}).length}
						</p>
					</div>
					<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Ctrl Valves</p>
						<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
							{Object.keys($solvedState.control_valve_results ?? {}).length}
						</p>
					</div>
					<div class="rounded-lg bg-[var(--color-surface-elevated)] p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Warnings</p>
						<p class="mt-1 text-2xl font-semibold text-[var(--color-text)]">
							{($solvedState.warnings ?? []).length}
						</p>
					</div>
				</div>
			{/if}

		{:else if view === 'nodes'}
			<ComponentTable results={$solvedState} />

		{:else if view === 'links'}
			<PipingTable results={$solvedState} />

		{:else if view === 'pumps'}
			{#if pumpData.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-sm text-[var(--color-text-muted)]">No pumps in this network</p>
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

		{:else if view === 'valves'}
			{#if controlValveData.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-sm text-[var(--color-text-muted)]">No control valves in this network</p>
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

		{:else if view === 'elevation'}
			<ElevationProfile data={elevationData} />
		{/if}
	</div>
</div>
