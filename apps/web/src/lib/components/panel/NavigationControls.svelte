<script lang="ts">
	import { navigationStore, canGoBack, canGoForward, components } from '$lib/stores';
	import { COMPONENT_TYPE_LABELS } from '$lib/models';

	interface Props {
		/** Callback when navigation changes (for keyboard support). */
		onNavigate?: (direction: 'prev' | 'next') => void;
	}

	let { onNavigate }: Props = $props();

	// Get current component info
	let currentIndex = $derived.by(() => {
		const navState = $navigationStore;
		if (!navState.currentElementId) return -1;
		return $components.findIndex((c) => c.id === navState.currentElementId);
	});

	let currentComponent = $derived($components[currentIndex] ?? null);
	let totalComponents = $derived($components.length);

	function handlePrev() {
		// Navigate to previous component in the chain
		if (currentIndex > 0) {
			const prevComponent = $components[currentIndex - 1];
			navigationStore.navigateTo(prevComponent.id);
			onNavigate?.('prev');
		} else if ($canGoBack) {
			navigationStore.goBack();
			onNavigate?.('prev');
		}
	}

	function handleNext() {
		// Navigate to next component in the chain
		if (currentIndex < totalComponents - 1) {
			const nextComponent = $components[currentIndex + 1];
			navigationStore.navigateTo(nextComponent.id);
			onNavigate?.('next');
		} else if ($canGoForward) {
			navigationStore.goForward();
			onNavigate?.('next');
		}
	}

	let canNavigatePrev = $derived(currentIndex > 0 || $canGoBack);
	let canNavigateNext = $derived(currentIndex < totalComponents - 1 || $canGoForward);
</script>

<div class="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-4 py-3">
	<!-- Previous Button -->
	<button
		type="button"
		onclick={handlePrev}
		disabled={!canNavigatePrev}
		aria-label="Previous component"
		class="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors
			{canNavigatePrev
			? 'bg-white text-gray-700 shadow-sm hover:bg-gray-50 border border-gray-300'
			: 'bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200'}"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
		</svg>
		<span class="hidden sm:inline">Previous</span>
	</button>

	<!-- Position Indicator -->
	<div class="text-center">
		{#if currentComponent}
			<p class="text-sm font-medium text-gray-700">
				{COMPONENT_TYPE_LABELS[currentComponent.type]}
			</p>
			<p class="text-xs text-gray-500">
				{currentIndex + 1} of {totalComponents}
			</p>
		{:else if totalComponents === 0}
			<p class="text-sm text-gray-500">No components</p>
		{:else}
			<p class="text-sm text-gray-500">Select a component</p>
		{/if}
	</div>

	<!-- Next Button -->
	<button
		type="button"
		onclick={handleNext}
		disabled={!canNavigateNext}
		aria-label="Next component"
		class="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors
			{canNavigateNext
			? 'bg-white text-gray-700 shadow-sm hover:bg-gray-50 border border-gray-300'
			: 'bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200'}"
	>
		<span class="hidden sm:inline">Next</span>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
		</svg>
	</button>
</div>
