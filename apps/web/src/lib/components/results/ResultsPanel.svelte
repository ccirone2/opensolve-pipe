<script lang="ts">
	import { solvedState, components, pumpLibrary } from '$lib/stores';
	import { isPump, WARNING_CATEGORY_LABELS, type Warning } from '$lib/models';
	import NodeTable from './NodeTable.svelte';
	import LinkTable from './LinkTable.svelte';
	import PumpCurveChart from './PumpCurveChart.svelte';

	interface Props {
		/** Whether a solve is currently in progress. */
		isLoading?: boolean;
	}

	let { isLoading = false }: Props = $props();

	type TabId = 'summary' | 'nodes' | 'links' | 'pumps';
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

	const tabs: { id: TabId; label: string }[] = [
		{ id: 'summary', label: 'Summary' },
		{ id: 'nodes', label: 'Nodes' },
		{ id: 'links', label: 'Links' },
		{ id: 'pumps', label: 'Pumps' }
	];

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
			<div class="h-12 w-12 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
			<p class="mt-4 text-sm text-gray-600">Solving network...</p>
		</div>
	{:else if !$solvedState}
		<!-- No Results State -->
		<div class="flex flex-1 flex-col items-center justify-center p-8 text-center">
			<svg class="h-16 w-16 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
				/>
			</svg>
			<h3 class="mt-4 text-lg font-medium text-gray-900">No results yet</h3>
			<p class="mt-2 text-sm text-gray-500">
				Click "Solve" to calculate pressures and flows in your network.
			</p>
		</div>
	{:else}
		<!-- Tab Navigation -->
		<div class="border-b border-gray-200 bg-gray-50">
			<nav class="flex -mb-px" aria-label="Tabs">
				{#each tabs as tab}
					<button
						type="button"
						onclick={() => (activeTab = tab.id)}
						class="flex-1 border-b-2 py-3 text-center text-sm font-medium transition-colors
							{activeTab === tab.id
							? 'border-blue-500 text-blue-600'
							: 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'}"
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
						{$solvedState.converged ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}"
				>
					<div class="flex items-center gap-3">
						{#if $solvedState.converged}
							<svg class="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
							</svg>
							<div>
								<p class="font-medium text-green-800">Solution Converged</p>
								<p class="text-sm text-green-600">
									{$solvedState.iterations} iterations in {formatDuration($solvedState.solve_time_seconds)}
								</p>
							</div>
						{:else}
							<svg class="h-6 w-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
							</svg>
							<div>
								<p class="font-medium text-red-800">Solution Failed</p>
								<p class="text-sm text-red-600">
									{$solvedState.error || 'Unknown error'}
								</p>
							</div>
						{/if}
					</div>
				</div>

				<!-- Warnings -->
				{#if $solvedState.warnings.length > 0}
					<div class="mt-4 space-y-3">
						<h4 class="text-sm font-medium text-gray-900">Warnings & Messages</h4>

						{#each errorWarnings as warning}
							<div class="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-3">
								<svg class="h-5 w-5 flex-shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={getWarningIcon('error')} />
								</svg>
								<div>
									<p class="text-sm font-medium text-red-800">{warning.message}</p>
									<p class="text-xs text-red-600">{WARNING_CATEGORY_LABELS[warning.category]}</p>
								</div>
							</div>
						{/each}

						{#each warningWarnings as warning}
							<div class="flex items-start gap-3 rounded-lg border border-yellow-200 bg-yellow-50 p-3">
								<svg class="h-5 w-5 flex-shrink-0 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={getWarningIcon('warning')} />
								</svg>
								<div>
									<p class="text-sm font-medium text-yellow-800">{warning.message}</p>
									<p class="text-xs text-yellow-600">{WARNING_CATEGORY_LABELS[warning.category]}</p>
								</div>
							</div>
						{/each}

						{#each infoWarnings as warning}
							<div class="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-3">
								<svg class="h-5 w-5 flex-shrink-0 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={getWarningIcon('info')} />
								</svg>
								<div>
									<p class="text-sm font-medium text-blue-800">{warning.message}</p>
									<p class="text-xs text-blue-600">{WARNING_CATEGORY_LABELS[warning.category]}</p>
								</div>
							</div>
						{/each}
					</div>
				{/if}

				<!-- Quick Stats -->
				{#if $solvedState.converged}
					<div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
						<div class="rounded-lg bg-gray-50 p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Nodes</p>
							<p class="mt-1 text-2xl font-semibold text-gray-900">
								{Object.keys($solvedState.node_results).length}
							</p>
						</div>
						<div class="rounded-lg bg-gray-50 p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Links</p>
							<p class="mt-1 text-2xl font-semibold text-gray-900">
								{Object.keys($solvedState.link_results).length}
							</p>
						</div>
						<div class="rounded-lg bg-gray-50 p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Pumps</p>
							<p class="mt-1 text-2xl font-semibold text-gray-900">
								{Object.keys($solvedState.pump_results).length}
							</p>
						</div>
						<div class="rounded-lg bg-gray-50 p-3">
							<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Warnings</p>
							<p class="mt-1 text-2xl font-semibold text-gray-900">
								{$solvedState.warnings.length}
							</p>
						</div>
					</div>
				{/if}
			{:else if activeTab === 'nodes'}
				<NodeTable results={$solvedState} />
			{:else if activeTab === 'links'}
				<LinkTable results={$solvedState} />
			{:else if activeTab === 'pumps'}
				{#if pumpData.length === 0}
					<div class="flex flex-col items-center justify-center py-12 text-center">
						<svg class="h-12 w-12 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
							/>
						</svg>
						<p class="mt-4 text-sm text-gray-500">No pumps in this network</p>
					</div>
				{:else}
					<div class="space-y-6">
						{#each pumpData as { pump, curve, result }}
							<div class="rounded-lg border border-gray-200 p-4">
								<h4 class="text-sm font-medium text-gray-900">{pump.name}</h4>
								{#if curve}
									<p class="text-xs text-gray-500">{curve.name}</p>
									<div class="mt-4">
										<PumpCurveChart {curve} {result} />
									</div>
								{:else}
									<p class="mt-2 text-sm text-yellow-600">No pump curve assigned</p>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			{/if}
		</div>
	{/if}
</div>
