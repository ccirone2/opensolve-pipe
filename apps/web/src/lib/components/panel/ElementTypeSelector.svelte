<script lang="ts">
	import { projectStore } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		COMPONENT_CATEGORIES,
		type ComponentType
	} from '$lib/models';

	interface Props {
		/** Callback when a component type is selected. */
		onSelect?: (type: ComponentType) => void;
		/** Whether to show the selector. */
		open?: boolean;
		/** Callback when the selector is closed. */
		onClose?: () => void;
	}

	let { onSelect, open = false, onClose }: Props = $props();

	function handleSelect(type: ComponentType) {
		projectStore.addComponent(type);
		onSelect?.(type);
		onClose?.();
	}
</script>

{#if open}
	<!-- Backdrop -->
	<button
		type="button"
		class="fixed inset-0 z-40 bg-black/20"
		onclick={onClose}
		aria-label="Close menu"
	></button>

	<!-- Dropdown -->
	<div
		class="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border border-gray-200 bg-white shadow-lg"
	>
		<div class="p-4">
			<h3 class="mb-3 text-sm font-semibold text-gray-900">Add Component</h3>

			<div class="space-y-4">
				{#each Object.entries(COMPONENT_CATEGORIES) as [category, types]}
					<div>
						<h4 class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
							{category}
						</h4>
						<div class="flex flex-wrap gap-2">
							{#each types as type}
								<button
									type="button"
									onclick={() => handleSelect(type)}
									class="whitespace-nowrap rounded-md border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 transition-colors hover:border-blue-500 hover:bg-blue-50"
								>
									{COMPONENT_TYPE_LABELS[type]}
								</button>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>
{/if}
