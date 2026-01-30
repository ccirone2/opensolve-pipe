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
		/** Index at which to insert the new component (inserts after this index). */
		insertAfterIndex?: number;
	}

	let { onSelect, open = false, onClose, insertAfterIndex }: Props = $props();

	function handleSelect(type: ComponentType) {
		// If insertAfterIndex is provided, insert after that position
		// Otherwise, append to end (default behavior)
		const atIndex = insertAfterIndex !== undefined ? insertAfterIndex + 1 : undefined;
		projectStore.addComponent(type, atIndex);
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
		class="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg"
	>
		<div class="p-4">
			<h3 class="mb-3 text-sm font-semibold text-[var(--color-text)]">Add Component</h3>

			<div class="space-y-4">
				{#each Object.entries(COMPONENT_CATEGORIES) as [category, types]}
					<div>
						<h4 class="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
							{category}
						</h4>
						<div class="flex flex-wrap gap-2">
							{#each types as type}
								<button
									type="button"
									onclick={() => handleSelect(type)}
									class="whitespace-nowrap rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] transition-colors hover:border-[var(--color-accent)] hover:bg-[var(--color-accent-muted)]"
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
