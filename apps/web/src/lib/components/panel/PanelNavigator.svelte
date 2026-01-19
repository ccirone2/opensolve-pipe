<script lang="ts">
	import { onMount } from 'svelte';
	import { navigationStore, currentElementId, components, projectStore } from '$lib/stores';
	import NavigationControls from './NavigationControls.svelte';
	import Breadcrumbs from './Breadcrumbs.svelte';
	import ElementPanel from './ElementPanel.svelte';
	import PipingPanel from './PipingPanel.svelte';
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
		{ id: 'element', label: 'Element' },
		{ id: 'upstream', label: 'Upstream' },
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

		<!-- Tab Content -->
		<div class="flex-1 overflow-y-auto p-4">
			{#if activeTab === 'element'}
				<ElementPanel component={currentComponent} />
			{:else if activeTab === 'upstream'}
				<PipingPanel
					componentId={currentComponent.id}
					piping={currentComponent.upstream_piping}
				/>
			{:else if activeTab === 'downstream'}
				<div class="text-center text-gray-500">
					<p class="text-sm">Downstream connections</p>
					<p class="mt-2 text-xs">
						{currentComponent.downstream_connections.length} connection(s)
					</p>
					<!-- TODO: Add downstream connection management UI -->
				</div>
			{/if}
		</div>

		<!-- Navigation Controls -->
		<NavigationControls />
	{/if}
</div>
