<script lang="ts">
	import { onMount } from 'svelte';
	import { projectStore, components, navigationStore } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		COMPONENT_CATEGORIES,
		type ComponentType,
		type Component
	} from '$lib/models';

	interface Props {
		open?: boolean;
		onClose?: () => void;
	}

	let { open = false, onClose }: Props = $props();

	let query = $state('');
	let activeIndex = $state(0);
	let inputEl: HTMLInputElement | undefined = $state();

	// Build searchable items
	interface PaletteItem {
		id: string;
		label: string;
		category: string;
		action: () => void;
		badge?: string;
		badgeColor?: 'source' | 'equipment' | 'connection';
	}

	let items = $derived.by(() => {
		const results: PaletteItem[] = [];
		const q = query.toLowerCase().trim();

		// Add component types
		for (const [category, types] of Object.entries(COMPONENT_CATEGORIES)) {
			for (const type of types) {
				const label = COMPONENT_TYPE_LABELS[type];
				if (q && !label.toLowerCase().includes(q) && !type.toLowerCase().includes(q)) continue;
				results.push({
					id: `add-${type}`,
					label: `Add ${label}`,
					category: 'Add Component',
					action: () => {
						projectStore.addComponent(type);
						onClose?.();
					},
					badge: category === 'Sources' ? 'SRC' : category === 'Equipment' ? 'EQP' : 'CON',
					badgeColor: category === 'Sources' ? 'source' : category === 'Equipment' ? 'equipment' : 'connection'
				});
			}
		}

		// Navigate to existing components
		const comps = $components;
		for (const comp of comps) {
			const label = `${comp.name} (${COMPONENT_TYPE_LABELS[comp.type]})`;
			if (q && !label.toLowerCase().includes(q) && !comp.id.toLowerCase().includes(q)) continue;
			results.push({
				id: `nav-${comp.id}`,
				label: comp.name,
				category: 'Navigate To',
				action: () => {
					navigationStore.navigateTo(comp.id);
					onClose?.();
				},
				badge: COMPONENT_TYPE_LABELS[comp.type],
				badgeColor: undefined
			});
		}

		return results;
	});

	// Group items by category
	let groupedItems = $derived.by(() => {
		const groups = new Map<string, PaletteItem[]>();
		for (const item of items) {
			const group = groups.get(item.category) ?? [];
			group.push(item);
			groups.set(item.category, group);
		}
		return groups;
	});

	// Flat list for keyboard navigation
	let flatItems = $derived(items);

	// Reset active index when query changes
	$effect(() => {
		query;
		activeIndex = 0;
	});

	// Focus input when opened
	$effect(() => {
		if (open && inputEl) {
			query = '';
			activeIndex = 0;
			// Slight delay to ensure DOM is ready
			setTimeout(() => inputEl?.focus(), 10);
		}
	});

	function handleKeydown(e: KeyboardEvent) {
		switch (e.key) {
			case 'ArrowDown':
				e.preventDefault();
				activeIndex = Math.min(activeIndex + 1, flatItems.length - 1);
				break;
			case 'ArrowUp':
				e.preventDefault();
				activeIndex = Math.max(activeIndex - 1, 0);
				break;
			case 'Enter':
				e.preventDefault();
				if (flatItems[activeIndex]) {
					flatItems[activeIndex].action();
				}
				break;
			case 'Escape':
				e.preventDefault();
				onClose?.();
				break;
		}
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			onClose?.();
		}
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="command-palette-backdrop"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
	>
		<div class="command-palette" role="dialog" aria-modal="true" aria-label="Command palette">
			<input
				bind:this={inputEl}
				type="text"
				bind:value={query}
				class="command-palette-input"
				placeholder="Type to search components..."
				onkeydown={handleKeydown}
			/>

			<div class="command-palette-results">
				{#if flatItems.length === 0}
					<div class="px-4 py-6 text-center text-xs text-[var(--color-text-subtle)]">
						No matching components
					</div>
				{:else}
					{@const seen = new Set<string>()}
					{#each flatItems as item, i}
						{@const showGroup = !seen.has(item.category) && (seen.add(item.category), true)}
						{#if showGroup}
							<div class="command-palette-group">
								{item.category}
							</div>
						{/if}
						<button
							type="button"
							class="command-palette-item {i === activeIndex ? 'active' : ''}"
							onclick={item.action}
							onmouseenter={() => (activeIndex = i)}
						>
							<span class="flex-1">{item.label}</span>
							{#if item.badge}
								<span
									class="item-badge
										{item.badgeColor === 'source'
										? 'bg-[var(--color-badge-source)] text-[var(--color-badge-source-text)]'
										: item.badgeColor === 'equipment'
											? 'bg-[var(--color-badge-equipment)] text-[var(--color-badge-equipment-text)]'
											: item.badgeColor === 'connection'
												? 'bg-[var(--color-badge-connection)] text-[var(--color-badge-connection-text)]'
												: 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'}"
								>
									{item.badge}
								</span>
							{/if}
						</button>
					{/each}
				{/if}
			</div>

			<!-- Footer hint -->
			<div class="flex items-center justify-between border-t border-[var(--color-border)] px-3 py-1.5 text-[0.625rem] text-[var(--color-text-subtle)]">
				<span>
					<span class="kbd">&uarr;</span>
					<span class="kbd">&darr;</span>
					navigate
				</span>
				<span>
					<span class="kbd">Enter</span>
					select
				</span>
				<span>
					<span class="kbd">Esc</span>
					close
				</span>
			</div>
		</div>
	</div>
{/if}
