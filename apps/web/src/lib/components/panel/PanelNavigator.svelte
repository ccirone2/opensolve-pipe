<script lang="ts">
	import { onMount } from 'svelte';
	import { navigationStore, currentElementId, components, projectStore } from '$lib/stores';
	import NavigationControls from './NavigationControls.svelte';
	import Breadcrumbs from './Breadcrumbs.svelte';
	import ElementPanel from './ElementPanel.svelte';
	import DownstreamPipingPanel from './DownstreamPipingPanel.svelte';
	import ElementTypeSelector from './ElementTypeSelector.svelte';

	type TabId = 'element' | 'upstream' | 'downstream';

	let activeTab: TabId = $state('element');
	let showAddSelector = $state(false);

	// Get current component
	let currentComponent = $derived.by(() => {
		const id = $currentElementId;
		if (!id) return null;
		return $components.find((c) => c.id === id) ?? null;
	});

	// Get upstream component (component that has a downstream connection to current)
	let upstreamComponent = $derived.by(() => {
		if (!currentComponent) return null;
		return $components.find((c) =>
			c.downstream_connections.some((conn) => conn.target_component_id === currentComponent!.id)
		) ?? null;
	});

	// Get current component index for contextual insertion
	let currentComponentIndex = $derived(
		currentComponent ? $components.findIndex((c) => c.id === currentComponent.id) : -1
	);

	// Auto-navigate to first component if none selected
	$effect(() => {
		if (!$currentElementId && $components.length > 0) {
			navigationStore.navigateTo($components[0].id);
		}
	});

	// Keyboard navigation
	function handleKeydown(e: KeyboardEvent) {
		if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) {
			return; // Don't interfere with form inputs
		}

		switch (e.key) {
			case 'ArrowLeft':
				e.preventDefault();
				navigatePrev();
				break;
			case 'ArrowRight':
				e.preventDefault();
				navigateNext();
				break;
		}
	}

	function navigatePrev() {
		const currentIndex = $components.findIndex((c) => c.id === $currentElementId);
		if (currentIndex > 0) {
			navigationStore.navigateTo($components[currentIndex - 1].id);
		}
	}

	function navigateNext() {
		const currentIndex = $components.findIndex((c) => c.id === $currentElementId);
		if (currentIndex < $components.length - 1) {
			navigationStore.navigateTo($components[currentIndex + 1].id);
		}
	}

	const tabs: { id: TabId; label: string }[] = [
		{ id: 'upstream', label: 'Upstream' },
		{ id: 'element', label: 'Element' },
		{ id: 'downstream', label: 'Downstream' }
	];

	onMount(() => {
		window.addEventListener('keydown', handleKeydown);
		return () => {
			window.removeEventListener('keydown', handleKeydown);
		};
	});
</script>

<div class="flex h-full flex-col">
	<!-- Header with Breadcrumbs and Add Button -->
	<div class="border-b border-gray-200 bg-white px-4 py-3">
		<div class="flex items-center justify-between">
			<Breadcrumbs />

			<div class="relative">
				<button
					type="button"
					onclick={() => (showAddSelector = !showAddSelector)}
					aria-label="Add component"
					class="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
					</svg>
					<span class="hidden sm:inline">Add</span>
				</button>

				<ElementTypeSelector
					open={showAddSelector}
					onClose={() => (showAddSelector = false)}
					insertAfterIndex={currentComponentIndex >= 0 ? currentComponentIndex : undefined}
				/>
			</div>
		</div>
	</div>

	{#if $components.length === 0}
		<!-- Empty State -->
		<div class="flex flex-1 flex-col items-center justify-center p-8 text-center">
			<svg class="h-16 w-16 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
				/>
			</svg>
			<h3 class="mt-4 text-lg font-medium text-gray-900">No components yet</h3>
			<p class="mt-2 text-sm text-gray-500">
				Start by adding a reservoir or tank as your water source.
			</p>
			<button
				type="button"
				onclick={() => projectStore.addComponent('reservoir')}
				class="mt-4 inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
			>
				<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
				</svg>
				Add Reservoir
			</button>
		</div>
	{:else if !currentComponent}
		<!-- No component selected -->
		<div class="flex flex-1 flex-col items-center justify-center p-8 text-center">
			<p class="text-gray-500">Select a component to view its properties</p>
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

		<!-- Tab Content - flex container that grows to fill available space -->
		<div class="min-h-0 flex-1 overflow-y-auto p-4">
			{#if activeTab === 'element'}
				<ElementPanel component={currentComponent} />
			{:else if activeTab === 'upstream'}
				<!-- Upstream: Show connections coming into this element -->
				<div class="space-y-4">
					<div class="text-center text-gray-500">
						<p class="text-sm font-medium">Upstream Connection</p>
						<p class="mt-1 text-xs">What feeds into this element</p>
					</div>
					{#if !upstreamComponent}
						<div class="rounded-lg border-2 border-dashed border-gray-300 p-6 text-center">
							<svg
								class="mx-auto h-12 w-12 text-gray-400"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M5 12h14M5 12l4-4m-4 4l4 4"
								/>
							</svg>
							<p class="mt-2 text-sm text-gray-600">No upstream connection</p>
							<p class="mt-1 text-xs text-gray-400">
								This is a source element (reservoir/tank).
							</p>
						</div>
					{:else}
						<div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
							<div class="flex items-center gap-3">
								<div class="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-blue-600">
									<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M11 19l-7-7 7-7m8 14l-7-7 7-7"
										/>
									</svg>
								</div>
								<div>
									<p class="text-sm font-medium text-gray-900">{upstreamComponent.name}</p>
									<p class="text-xs text-gray-500 capitalize">{upstreamComponent.type.replace('_', ' ')}</p>
								</div>
							</div>
							<button
								type="button"
								onclick={() => navigationStore.navigateTo(upstreamComponent!.id)}
								class="mt-3 w-full rounded-md bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
							>
								Go to {upstreamComponent.name}
							</button>
						</div>
					{/if}
				</div>
			{:else if activeTab === 'downstream'}
				<!-- Downstream: Show piping editor for downstream connections -->
				<DownstreamPipingPanel
					componentId={currentComponent.id}
					connections={currentComponent.downstream_connections}
				/>
			{/if}
		</div>

		<!-- Navigation Controls - anchored at bottom -->
		<div class="mt-auto border-t border-gray-200 bg-white">
			<NavigationControls />
		</div>
	{/if}
</div>
