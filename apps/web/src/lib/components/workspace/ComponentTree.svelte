<script lang="ts">
	import { components, navigationStore, currentElementId, projectStore } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		COMPONENT_CATEGORIES,
		type Component,
		type ComponentType
	} from '$lib/models';

	interface Props {
		onOpenCommandPalette?: () => void;
	}

	let { onOpenCommandPalette }: Props = $props();

	// Category badge colors
	function getCategoryForType(type: ComponentType): 'source' | 'equipment' | 'connection' {
		if ((COMPONENT_CATEGORIES.Sources as string[]).includes(type)) return 'source';
		if ((COMPONENT_CATEGORIES.Equipment as string[]).includes(type)) return 'equipment';
		return 'connection';
	}

	// Abbreviations for component types
	const TYPE_ABBREVS: Record<string, string> = {
		reservoir: 'RSV',
		tank: 'TNK',
		junction: 'JCT',
		pump: 'PMP',
		valve: 'VLV',
		heat_exchanger: 'HX',
		strainer: 'STR',
		orifice: 'ORF',
		sprinkler: 'SPK',
		ideal_reference_node: 'REF',
		non_ideal_reference_node: 'REF',
		plug: 'PLG',
		tee_branch: 'TEE',
		wye_branch: 'WYE',
		cross_branch: 'CRS'
	};

	function handleSelect(component: Component) {
		navigationStore.navigateTo(component.id);
	}

	function handleDelete(e: Event, componentId: string) {
		e.stopPropagation();
		projectStore.removeComponent(componentId);
	}
</script>

<div class="flex h-full flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
		<span class="text-[0.6875rem] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
			Components
		</span>
		<button
			type="button"
			onclick={onOpenCommandPalette}
			class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-accent-muted)] hover:text-[var(--color-accent)]"
			title="Add component (Ctrl+K)"
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
		</button>
	</div>

	<!-- Component List -->
	<div class="flex-1 overflow-y-auto py-1">
		{#if $components.length === 0}
			<div class="flex flex-col items-center gap-2 px-3 py-6 text-center">
				<svg class="h-8 w-8 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<p class="text-xs text-[var(--color-text-subtle)]">No components</p>
				<button
					type="button"
					onclick={onOpenCommandPalette}
					class="rounded bg-[var(--color-accent-muted)] px-2.5 py-1 text-xs font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-[var(--color-accent-text)]"
				>
					Add First
				</button>
			</div>
		{:else}
			{#each $components as component, i}
				{@const isSelected = $currentElementId === component.id}
				{@const category = getCategoryForType(component.type)}
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					class="group flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left transition-colors
						{isSelected
						? 'bg-[var(--color-tree-selected)] text-[var(--color-text)]'
						: 'text-[var(--color-text-muted)] hover:bg-[var(--color-tree-hover)] hover:text-[var(--color-text)]'}"
					onclick={() => handleSelect(component)}
					onkeydown={(e) => e.key === 'Enter' && handleSelect(component)}
					role="button"
					tabindex="0"
				>
					<!-- Index -->
					<span class="w-4 flex-shrink-0 text-center mono-value text-[0.625rem] text-[var(--color-text-subtle)]">
						{i + 1}
					</span>

					<!-- Type badge -->
					<span
						class="flex-shrink-0 rounded px-1 py-0.5 mono-value text-[0.5625rem] font-semibold
							{category === 'source'
							? 'bg-[var(--color-badge-source)] text-[var(--color-badge-source-text)]'
							: category === 'equipment'
								? 'bg-[var(--color-badge-equipment)] text-[var(--color-badge-equipment-text)]'
								: 'bg-[var(--color-badge-connection)] text-[var(--color-badge-connection-text)]'}"
					>
						{TYPE_ABBREVS[component.type] || '???'}
					</span>

					<!-- Name -->
					<span class="min-w-0 flex-1 truncate text-xs">
						{component.name}
					</span>

					<!-- Delete button (on hover) -->
					<button
						type="button"
						onclick={(e) => handleDelete(e, component.id)}
						class="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded opacity-0 transition-opacity group-hover:opacity-100 hover:bg-[var(--color-error)]/20 hover:text-[var(--color-error)]"
						title="Remove component"
					>
						<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>

				<!-- Connection line between components -->
				{#if i < $components.length - 1}
					<div class="ml-[1.375rem] h-2 border-l border-dashed border-[var(--color-border)]"></div>
				{/if}
			{/each}
		{/if}
	</div>

	<!-- Footer: Quick add -->
	<div class="border-t border-[var(--color-border)] px-2 py-1.5">
		<button
			type="button"
			onclick={() => projectStore.addComponent('reservoir')}
			class="flex w-full items-center gap-1.5 rounded px-2 py-1 text-xs text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
		>
			<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			Quick add reservoir
		</button>
	</div>
</div>
