<script lang="ts">
	import { components, currentElementId, navigationStore, projectStore, solvedState, pumpLibrary } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		isPump,
		isValve,
		type Component,
		type ValveComponent
	} from '$lib/models';
	import ElementPanel from '../panel/ElementPanel.svelte';
	import DownstreamPipingPanel from '../panel/DownstreamPipingPanel.svelte';
	import PumpResultsCard from '../results/PumpResultsCard.svelte';
	import ControlValveResultsCard from '../results/ControlValveResultsCard.svelte';

	type InspectorTab = 'properties' | 'piping' | 'results';
	let activeTab: InspectorTab = $state('properties');

	// Get current component
	let currentComponent = $derived.by(() => {
		const id = $currentElementId;
		if (!id) return null;
		return $components.find((c) => c.id === id) ?? null;
	});

	// Get pump data for results
	let pumpResult = $derived.by(() => {
		if (!currentComponent || !isPump(currentComponent)) return null;
		return {
			pump: currentComponent,
			curve: $pumpLibrary.find((c) => c.id === currentComponent!.curve_id),
			result: $solvedState?.pump_results?.[currentComponent.id]
		};
	});

	// Get control valve data for results
	let valveResult = $derived.by(() => {
		if (!currentComponent || !isValve(currentComponent)) return null;
		const controlValveTypes = ['prv', 'psv', 'fcv', 'tcv'];
		if (!controlValveTypes.includes((currentComponent as ValveComponent).valve_type)) return null;
		return {
			valve: currentComponent as ValveComponent,
			result: $solvedState?.control_valve_results?.[currentComponent.id]
		};
	});

	// Node/link result for current component
	let componentResult = $derived.by(() => {
		if (!currentComponent || !$solvedState) return null;
		return $solvedState.component_results?.[currentComponent.id] ?? null;
	});

	let pipingResult = $derived.by(() => {
		if (!currentComponent || !$solvedState) return null;
		return $solvedState.piping_results?.[currentComponent.id] ?? null;
	});

	function formatNumber(val: number | null | undefined, decimals = 2): string {
		if (val === null || val === undefined) return '-';
		return val.toFixed(decimals);
	}

	// Auto-switch to properties tab when component changes
	$effect(() => {
		if ($currentElementId) {
			activeTab = 'properties';
		}
	});

	const tabs: { id: InspectorTab; label: string }[] = [
		{ id: 'properties', label: 'Properties' },
		{ id: 'piping', label: 'Piping' },
		{ id: 'results', label: 'Results' }
	];
</script>

<div class="flex h-full flex-col border-l border-[var(--color-border)] bg-[var(--color-surface)]">
	{#if !currentComponent}
		<!-- No selection -->
		<div class="flex flex-1 flex-col items-center justify-center gap-2 p-4 text-center">
			<svg class="h-10 w-10 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
			</svg>
			<p class="text-xs text-[var(--color-text-subtle)]">Select a component<br />from the tree or schematic</p>
		</div>
	{:else}
		<!-- Component Header -->
		<div class="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-2">
			<span class="text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-accent)]">
				{COMPONENT_TYPE_LABELS[currentComponent.type]}
			</span>
			<span class="flex-1 truncate text-xs font-medium text-[var(--color-text)]">
				{currentComponent.name}
			</span>
		</div>

		<!-- Tab Navigation -->
		<div class="flex border-b border-[var(--color-border)] bg-[var(--color-surface)]">
			{#each tabs as tab}
				<button
					type="button"
					onclick={() => (activeTab = tab.id)}
					class="flex-1 border-b-2 py-1.5 text-center text-[0.6875rem] font-medium transition-colors
						{activeTab === tab.id
						? 'border-[var(--color-accent)] text-[var(--color-accent)]'
						: 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]'}"
				>
					{tab.label}
					{#if tab.id === 'results' && $solvedState}
						<span class="ml-1 inline-flex h-1.5 w-1.5 rounded-full bg-[var(--color-success)]"></span>
					{/if}
				</button>
			{/each}
		</div>

		<!-- Tab Content -->
		<div class="flex-1 overflow-y-auto p-3">
			{#if activeTab === 'properties'}
				<ElementPanel component={currentComponent} />

			{:else if activeTab === 'piping'}
				<DownstreamPipingPanel
					componentId={currentComponent.id}
					connections={currentComponent.downstream_connections}
				/>

			{:else if activeTab === 'results'}
				{#if !$solvedState}
					<div class="flex flex-col items-center justify-center gap-2 py-8 text-center">
						<svg class="h-8 w-8 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
						</svg>
						<p class="text-xs text-[var(--color-text-subtle)]">Solve network to see results</p>
					</div>
				{:else}
					<div class="space-y-3">
						<!-- Component Result (Node data) -->
						{#if componentResult}
							<div class="rounded border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-2.5">
								<h4 class="mb-2 text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
									Hydraulic State
								</h4>
								<div class="grid grid-cols-2 gap-2">
									{#if componentResult.pressure !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Pressure</span>
											<p class="font-[var(--font-mono)] text-xs font-medium text-[var(--color-text)]">
												{formatNumber(componentResult.pressure)} psi
											</p>
										</div>
									{/if}
									{#if componentResult.hgl !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">HGL</span>
											<p class="font-[var(--font-mono)] text-xs font-medium text-[var(--color-text)]">
												{formatNumber(componentResult.hgl)} ft
											</p>
										</div>
									{/if}
									{#if componentResult.egl !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">EGL</span>
											<p class="font-[var(--font-mono)] text-xs font-medium text-[var(--color-text)]">
												{formatNumber(componentResult.egl)} ft
											</p>
										</div>
									{/if}
								</div>
							</div>
						{/if}

						<!-- Piping Result -->
						{#if pipingResult}
							<div class="rounded border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-2.5">
								<h4 class="mb-2 text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
									Flow Data
								</h4>
								<div class="grid grid-cols-2 gap-2">
									{#if pipingResult.flow !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Flow</span>
											<p class="font-[var(--font-mono)] text-xs font-medium text-[var(--color-text)]">
												{formatNumber(pipingResult.flow)} GPM
											</p>
										</div>
									{/if}
									{#if pipingResult.velocity !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Velocity</span>
											<p class="font-[var(--font-mono)] text-xs font-medium text-[var(--color-text)]">
												{formatNumber(pipingResult.velocity)} ft/s
											</p>
										</div>
									{/if}
									{#if pipingResult.head_loss !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Head Loss</span>
											<p class="font-[var(--font-mono)] text-xs font-medium text-[var(--color-text)]">
												{formatNumber(pipingResult.head_loss)} ft
											</p>
										</div>
									{/if}
									{#if pipingResult.reynolds_number !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Reynolds</span>
											<p class="font-[var(--font-mono)] text-xs font-medium text-[var(--color-text)]">
												{formatNumber(pipingResult.reynolds_number, 0)}
											</p>
										</div>
									{/if}
								</div>
							</div>
						{/if}

						<!-- Pump Results -->
						{#if pumpResult?.result}
							<PumpResultsCard
								pump={pumpResult.pump}
								curve={pumpResult.curve}
								result={pumpResult.result}
							/>
						{/if}

						<!-- Control Valve Results -->
						{#if valveResult?.result}
							<ControlValveResultsCard
								valve={valveResult.valve}
								result={valveResult.result}
							/>
						{/if}

						<!-- No results for this component -->
						{#if !componentResult && !pipingResult && !pumpResult?.result && !valveResult?.result}
							<div class="py-4 text-center">
								<p class="text-xs text-[var(--color-text-subtle)]">No results for this component</p>
							</div>
						{/if}
					</div>
				{/if}
			{/if}
		</div>
	{/if}
</div>
