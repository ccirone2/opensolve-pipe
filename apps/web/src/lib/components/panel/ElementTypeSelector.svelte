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
		class="absolute left-0 right-0 top-full z-50 mt-2 rounded-lg border border-gray-200 bg-white shadow-lg"
	>
		<div class="p-3">
			<h3 class="mb-3 text-sm font-semibold text-gray-900">Add Component</h3>

			<div class="space-y-4">
				{#each Object.entries(COMPONENT_CATEGORIES) as [category, types]}
					<div>
						<h4 class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
							{category}
						</h4>
						<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
							{#each types as type}
								<button
									type="button"
									onclick={() => handleSelect(type)}
									class="rounded-md border border-gray-200 px-3 py-2 text-left text-sm leading-normal transition-colors hover:border-blue-500 hover:bg-blue-50"
								>
									<span class="block truncate">{COMPONENT_TYPE_LABELS[type]}</span>
								</button>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>
{/if}
