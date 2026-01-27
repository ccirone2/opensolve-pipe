<script lang="ts">
	import { navigationStore, components } from '$lib/stores';
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
		// Navigate to previous component in the chain (linear navigation)
		if (currentIndex > 0) {
			const prevComponent = $components[currentIndex - 1];
			navigationStore.navigateTo(prevComponent.id);
			onNavigate?.('prev');
		}
	}

	function handleNext() {
		// Navigate to next component in the chain (linear navigation)
		if (currentIndex < totalComponents - 1) {
			const nextComponent = $components[currentIndex + 1];
			navigationStore.navigateTo(nextComponent.id);
			onNavigate?.('next');
		}
	}

	// Previous/Next are purely linear through component chain
	// (not affected by visit history)
	let canNavigatePrev = $derived(currentIndex > 0);
	let canNavigateNext = $derived(currentIndex < totalComponents - 1);
</script>

<div class="flex items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-4 py-3">
	<!-- Previous Button -->
	<button
		type="button"
		onclick={handlePrev}
		disabled={!canNavigatePrev}
		aria-label="Previous component"
		class="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors
			{canNavigatePrev
			? 'bg-[var(--color-surface)] text-[var(--color-text)] shadow-sm hover:bg-[var(--color-surface-elevated)] border border-[var(--color-border)]'
			: 'bg-[var(--color-surface-elevated)] text-[var(--color-text-subtle)] cursor-not-allowed border border-[var(--color-border-subtle)]'}"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
		</svg>
		<span class="hidden sm:inline">Previous</span>
	</button>

	<!-- Position Indicator -->
	<div class="text-center">
		{#if currentComponent}
			<p class="text-sm font-medium text-[var(--color-text)]">
				{COMPONENT_TYPE_LABELS[currentComponent.type]}
			</p>
			<p class="text-xs text-[var(--color-text-muted)]">
				{currentIndex + 1} of {totalComponents}
			</p>
		{:else if totalComponents === 0}
			<p class="text-sm text-[var(--color-text-muted)]">No components</p>
		{:else}
			<p class="text-sm text-[var(--color-text-muted)]">Select a component</p>
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
			? 'bg-[var(--color-surface)] text-[var(--color-text)] shadow-sm hover:bg-[var(--color-surface-elevated)] border border-[var(--color-border)]'
			: 'bg-[var(--color-surface-elevated)] text-[var(--color-text-subtle)] cursor-not-allowed border border-[var(--color-border-subtle)]'}"
	>
		<span class="hidden sm:inline">Next</span>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
		</svg>
	</button>
</div>
