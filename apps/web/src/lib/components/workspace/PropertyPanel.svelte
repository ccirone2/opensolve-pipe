<script lang="ts">
	import { components, currentElementId, projectStore, solvedState, pumpLibrary, workspaceStore, activeInspectorTab } from '$lib/stores';
	import type { InspectorTab } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		isPump,
		isValve,
		type ValveComponent
	} from '$lib/models';
	import ElementPanel from '../panel/ElementPanel.svelte';
	import DownstreamPipingPanel from '../panel/DownstreamPipingPanel.svelte';
	import PumpResultsCard from '../results/PumpResultsCard.svelte';
	import ControlValveResultsCard from '../results/ControlValveResultsCard.svelte';
	import MetricsStrip from './MetricsStrip.svelte';
	import ProjectSummary from './ProjectSummary.svelte';

	interface Props {
		onSolve?: () => void;
	}

	let { onSolve }: Props = $props();

	// Track if this is the first selection to auto-switch tab
	let hasSelectedBefore = $state(false);

	// Get current component
	let currentComponent = $derived.by(() => {
		const id = $currentElementId;
		if (!id) return null;
		return $components.find((c) => c.id === id) ?? null;
	});

	// Get the current component's index for move actions
	let currentIndex = $derived.by(() => {
		if (!currentComponent) return -1;
		return $components.findIndex((c) => c.id === currentComponent!.id);
	});

	let canMoveUp = $derived(currentIndex > 0);
	let canMoveDown = $derived(currentIndex >= 0 && currentIndex < $components.length - 1);

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

	// Only auto-switch to properties on the first selection
	$effect(() => {
		if ($currentElementId) {
			if (!hasSelectedBefore) {
				hasSelectedBefore = true;
				workspaceStore.setInspectorTab('properties');
			}
		}
	});

	function setTab(tab: InspectorTab) {
		workspaceStore.setInspectorTab(tab);
	}

	// Inline actions
	function handleDuplicate() {
		if (!currentComponent) return;
		projectStore.addComponent(currentComponent.type, currentIndex + 1);
	}

	function handleMoveUp() {
		if (!currentComponent || !canMoveUp) return;
		projectStore.moveComponent(currentComponent.id, currentIndex - 1);
	}

	function handleMoveDown() {
		if (!currentComponent || !canMoveDown) return;
		projectStore.moveComponent(currentComponent.id, currentIndex + 1);
	}

	function handleDelete() {
		if (!currentComponent) return;
		projectStore.removeComponent(currentComponent.id);
	}

	const tabs: { id: InspectorTab; label: string }[] = [
		{ id: 'properties', label: 'Properties' },
		{ id: 'piping', label: 'Piping' },
		{ id: 'results', label: 'Results' }
	];
</script>

<div class="flex h-full flex-col border-l border-[var(--color-border)] bg-[var(--color-surface)]">
	{#if !currentComponent}
		<!-- No selection: Project Summary -->
		<ProjectSummary {onSolve} />
	{:else}
		<!-- Component Header with Inline Actions -->
		<div class="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-2">
			<span class="section-heading text-[var(--color-accent)]">
				{COMPONENT_TYPE_LABELS[currentComponent.type]}
			</span>
			<span class="min-w-0 flex-1 truncate text-xs font-medium text-[var(--color-text)]">
				{currentComponent.name}
			</span>
			<!-- Inline Actions -->
			<div class="flex items-center gap-0.5">
				<button
					type="button"
					onclick={handleDuplicate}
					class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
					title="Duplicate"
				>
					<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75" />
					</svg>
				</button>
				<button
					type="button"
					onclick={handleMoveUp}
					disabled={!canMoveUp}
					class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)] disabled:opacity-30"
					title="Move up"
				>
					<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
					</svg>
				</button>
				<button
					type="button"
					onclick={handleMoveDown}
					disabled={!canMoveDown}
					class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)] disabled:opacity-30"
					title="Move down"
				>
					<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
					</svg>
				</button>
				<button
					type="button"
					onclick={handleDelete}
					class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)]"
					title="Delete"
				>
					<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Metrics Strip (pinned key values) -->
		<MetricsStrip component={currentComponent} />

		<!-- Tab Navigation -->
		<div class="flex border-b border-[var(--color-border)] bg-[var(--color-surface)]">
			{#each tabs as tab}
				<button
					type="button"
					onclick={() => setTab(tab.id)}
					class="flex-1 border-b-2 py-1.5 text-center text-[0.6875rem] font-medium transition-colors
						{$activeInspectorTab === tab.id
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
			{#if $activeInspectorTab === 'properties'}
				<ElementPanel component={currentComponent} />

			{:else if $activeInspectorTab === 'piping'}
				<DownstreamPipingPanel
					componentId={currentComponent.id}
					connections={currentComponent.downstream_connections}
				/>

			{:else if $activeInspectorTab === 'results'}
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
							<div class="card p-2.5">
								<h4 class="mb-2 section-heading">
									Hydraulic State
								</h4>
								<div class="grid grid-cols-2 gap-2">
									{#if componentResult.pressure !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Pressure</span>
											<p class="mono-value text-xs font-medium text-[var(--color-text)]">
												{formatNumber(componentResult.pressure)} psi
											</p>
										</div>
									{/if}
									{#if componentResult.hgl !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">HGL</span>
											<p class="mono-value text-xs font-medium text-[var(--color-text)]">
												{formatNumber(componentResult.hgl)} ft
											</p>
										</div>
									{/if}
									{#if componentResult.egl !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">EGL</span>
											<p class="mono-value text-xs font-medium text-[var(--color-text)]">
												{formatNumber(componentResult.egl)} ft
											</p>
										</div>
									{/if}
								</div>
							</div>
						{/if}

						<!-- Piping Result -->
						{#if pipingResult}
							<div class="card p-2.5">
								<h4 class="mb-2 section-heading">
									Flow Data
								</h4>
								<div class="grid grid-cols-2 gap-2">
									{#if pipingResult.flow !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Flow</span>
											<p class="mono-value text-xs font-medium text-[var(--color-text)]">
												{formatNumber(pipingResult.flow)} GPM
											</p>
										</div>
									{/if}
									{#if pipingResult.velocity !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Velocity</span>
											<p class="mono-value text-xs font-medium text-[var(--color-text)]">
												{formatNumber(pipingResult.velocity)} ft/s
											</p>
										</div>
									{/if}
									{#if pipingResult.head_loss !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Head Loss</span>
											<p class="mono-value text-xs font-medium text-[var(--color-text)]">
												{formatNumber(pipingResult.head_loss)} ft
											</p>
										</div>
									{/if}
									{#if pipingResult.reynolds_number !== undefined}
										<div>
											<span class="text-[0.625rem] text-[var(--color-text-subtle)]">Reynolds</span>
											<p class="mono-value text-xs font-medium text-[var(--color-text)]">
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
