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

	// Scrollable list ref for scroll-to-selected
	let listEl: HTMLDivElement | undefined = $state();

	// Auto-scroll to selected component when selection changes
	$effect(() => {
		const id = $currentElementId;
		if (!id || !listEl) return;
		const el = listEl.querySelector(`[data-component-id="${id}"]`);
		el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
	});

	function handleSelect(component: Component) {
		navigationStore.navigateTo(component.id);
	}

	// Delete confirmation state
	let pendingDeleteId = $state<string | null>(null);

	function handleDelete(e: Event, componentId: string) {
		e.stopPropagation();
		pendingDeleteId = componentId;
	}

	function confirmDelete(e: Event) {
		e.stopPropagation();
		if (pendingDeleteId) {
			projectStore.removeComponent(pendingDeleteId);
			pendingDeleteId = null;
		}
	}

	function cancelDelete(e: Event) {
		e.stopPropagation();
		pendingDeleteId = null;
	}

	// Drag-and-drop reorder state
	let draggedId = $state<string | null>(null);
	let dropTargetIndex = $state<number | null>(null);

	function handleDragStart(e: DragEvent, componentId: string) {
		draggedId = componentId;
		if (e.dataTransfer) {
			e.dataTransfer.effectAllowed = 'move';
			e.dataTransfer.setData('text/plain', componentId);
		}
	}

	function handleDragOver(e: DragEvent, index: number) {
		e.preventDefault();
		if (e.dataTransfer) {
			e.dataTransfer.dropEffect = 'move';
		}
		dropTargetIndex = index;
	}

	function handleDragLeave() {
		dropTargetIndex = null;
	}

	function handleDrop(e: DragEvent, targetIndex: number) {
		e.preventDefault();
		if (draggedId) {
			projectStore.moveComponent(draggedId, targetIndex);
		}
		draggedId = null;
		dropTargetIndex = null;
	}

	function handleDragEnd() {
		draggedId = null;
		dropTargetIndex = null;
	}

	// Context menu state
	let contextMenuId = $state<string | null>(null);
	let contextMenuPos = $state<{ x: number; y: number }>({ x: 0, y: 0 });

	function handleContextMenu(e: MouseEvent, componentId: string) {
		e.preventDefault();
		e.stopPropagation();
		contextMenuId = componentId;
		contextMenuPos = { x: e.clientX, y: e.clientY };
	}

	function closeContextMenu() {
		contextMenuId = null;
	}

	function handleCopySeries(e: Event) {
		e.stopPropagation();
		if (contextMenuId) {
			projectStore.copyComponentInSeries(contextMenuId);
		}
		closeContextMenu();
	}

	function handleCopyParallel(e: Event) {
		e.stopPropagation();
		if (contextMenuId) {
			projectStore.copyComponentInParallel(contextMenuId);
		}
		closeContextMenu();
	}

	// Close context menu on any click
	function handleWindowClick() {
		closeContextMenu();
	}
</script>

<svelte:window onclick={handleWindowClick} />

<div class="flex h-full flex-col bg-[var(--color-surface)]">
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
	<div bind:this={listEl} class="flex-1 overflow-y-auto py-1">
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
				{@const isDragging = draggedId === component.id}
				{@const isDropTarget = dropTargetIndex === i}
				{@const isLinked = !!component.parent_id}

				<!-- Drop indicator line (before this item) -->
				{#if isDropTarget && draggedId !== component.id}
					<div class="mx-2 h-[2px] rounded bg-[var(--color-accent)]"></div>
				{/if}

				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					data-component-id={component.id}
					draggable="true"
					ondragstart={(e) => handleDragStart(e, component.id)}
					ondragover={(e) => handleDragOver(e, i)}
					ondragleave={handleDragLeave}
					ondrop={(e) => handleDrop(e, i)}
					ondragend={handleDragEnd}
					oncontextmenu={(e) => handleContextMenu(e, component.id)}
					class="group flex w-full cursor-grab items-center gap-2 px-3 py-1.5 text-left transition-colors
						{isDragging ? 'opacity-40' : ''}
						{isSelected
						? 'bg-[var(--color-tree-selected)] text-[var(--color-text)]'
						: 'text-[var(--color-text-muted)] hover:bg-[var(--color-tree-hover)] hover:text-[var(--color-text)]'}"
					onclick={() => handleSelect(component)}
					onkeydown={(e) => e.key === 'Enter' && handleSelect(component)}
					role="button"
					tabindex="0"
				>
					<!-- Drag handle -->
					<span class="flex-shrink-0 text-[var(--color-text-subtle)] opacity-0 transition-opacity group-hover:opacity-60" aria-hidden="true">
						<svg class="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
							<circle cx="5" cy="4" r="1.2" /><circle cx="11" cy="4" r="1.2" />
							<circle cx="5" cy="8" r="1.2" /><circle cx="11" cy="8" r="1.2" />
							<circle cx="5" cy="12" r="1.2" /><circle cx="11" cy="12" r="1.2" />
						</svg>
					</span>

					<!-- Index -->
					<span class="w-4 flex-shrink-0 text-center mono-value text-[0.625rem] text-[var(--color-text-subtle)]">
						{i + 1}
					</span>

					<!-- Linked indicator -->
					{#if isLinked}
						<span class="flex-shrink-0 text-[var(--color-info)]" title="Linked to parent (edits will break link)">
							<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
							</svg>
						</span>
					{/if}

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

					<!-- Delete button with confirmation -->
					{#if pendingDeleteId === component.id}
						<div class="flex flex-shrink-0 items-center gap-1">
							<button
								type="button"
								onclick={confirmDelete}
								class="flex h-4 items-center rounded bg-[var(--color-error)] px-1.5 text-[0.5625rem] font-semibold text-white"
								title="Confirm delete"
							>Del</button>
							<button
								type="button"
								onclick={cancelDelete}
								class="flex h-4 items-center rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-1 text-[0.5625rem] text-[var(--color-text-muted)]"
								title="Cancel"
							>
								<svg class="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
								</svg>
							</button>
						</div>
					{:else}
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
					{/if}
				</div>

				<!-- Connection line between components -->
				{#if i < $components.length - 1 && !isDropTarget}
					<div class="ml-[1.375rem] h-2 border-l border-dashed border-[var(--color-border)]"></div>
				{/if}
			{/each}
		{/if}
	</div>
</div>

<!-- Context Menu -->
{#if contextMenuId}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed z-[200] min-w-[140px] rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] py-1 shadow-lg"
		style="left: {contextMenuPos.x}px; top: {contextMenuPos.y}px;"
		onclick={(e) => e.stopPropagation()}
		onkeydown={() => {}}
	>
		<button
			type="button"
			onclick={handleCopySeries}
			class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-[var(--color-text)] transition-colors hover:bg-[var(--color-tree-hover)]"
		>
			<svg class="h-3.5 w-3.5 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m0 0a2.625 2.625 0 115.25 0" />
			</svg>
			Copy in Series
		</button>
		<button
			type="button"
			onclick={handleCopyParallel}
			class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-[var(--color-text)] transition-colors hover:bg-[var(--color-tree-hover)]"
		>
			<svg class="h-3.5 w-3.5 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M3 7.5L7.5 3m0 0L12 7.5M7.5 3v13.5m13.5-13.5L16.5 7.5m0 0L12 3m4.5 4.5V21" />
			</svg>
			Copy in Parallel
		</button>
	</div>
{/if}
