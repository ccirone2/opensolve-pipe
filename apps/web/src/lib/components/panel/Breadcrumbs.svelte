<script lang="ts">
	import { navigationStore, components } from '$lib/stores';
	import { COMPONENT_TYPE_LABELS } from '$lib/models';

	// Get breadcrumb path based on component order
	let breadcrumbs = $derived.by(() => {
		const navState = $navigationStore;
		if (!navState.currentElementId) return [];

		const currentIndex = $components.findIndex((c) => c.id === navState.currentElementId);
		if (currentIndex === -1) return [];

		// Return first few + current for compact display
		const maxVisible = 4;
		const path = $components.slice(0, currentIndex + 1);

		if (path.length <= maxVisible) {
			return path.map((c, i) => ({ ...c, isLast: i === path.length - 1 }));
		}

		// Show first, ellipsis, last few
		return [
			{ ...path[0], isLast: false },
			{ id: '...', type: 'ellipsis' as const, name: '...', isLast: false },
			...path.slice(-2).map((c, i, arr) => ({ ...c, isLast: i === arr.length - 1 }))
		];
	});

	function handleClick(id: string) {
		if (id !== '...') {
			navigationStore.navigateTo(id);
		}
	}
</script>

{#if breadcrumbs.length > 0}
	<nav class="flex items-center space-x-1 text-sm" aria-label="Breadcrumb">
		<ol class="flex items-center space-x-1">
			{#each breadcrumbs as crumb, index}
				<li class="flex items-center">
					{#if index > 0}
						<svg class="h-4 w-4 flex-shrink-0 text-[var(--color-text-subtle)]" fill="currentColor" viewBox="0 0 20 20">
							<path
								fill-rule="evenodd"
								d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
								clip-rule="evenodd"
							/>
						</svg>
					{/if}

					{#if crumb.type === 'ellipsis'}
						<span class="px-2 text-[var(--color-text-subtle)]" aria-label="More components">...</span>
					{:else if crumb.isLast}
						<span class="px-2 font-medium text-[var(--color-text)]">
							{crumb.name || COMPONENT_TYPE_LABELS[crumb.type]}
						</span>
					{:else}
						<button
							type="button"
							onclick={() => handleClick(crumb.id)}
							class="px-2 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:underline"
						>
							{crumb.name || COMPONENT_TYPE_LABELS[crumb.type]}
						</button>
					{/if}
				</li>
			{/each}
		</ol>
	</nav>
{:else if $components.length === 0}
	<span class="text-sm text-[var(--color-text-subtle)]">No components added yet</span>
{/if}
