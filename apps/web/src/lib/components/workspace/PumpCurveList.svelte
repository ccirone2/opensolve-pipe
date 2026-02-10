<script lang="ts">
	import { pumpLibrary, projectStore } from '$lib/stores';
	import { createDefaultPumpCurve } from '$lib/models';
	import type { PumpCurve } from '$lib/models';
	import PumpCurveEditor from './PumpCurveEditor.svelte';

	let editingCurveId = $state<string | null>(null);
	let pendingDeleteId = $state<string | null>(null);

	function handleAdd() {
		const id = `curve_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
		const curve = createDefaultPumpCurve(id);
		projectStore.addPumpCurve(curve);
		editingCurveId = id;
	}

	function handleEdit(curveId: string) {
		editingCurveId = editingCurveId === curveId ? null : curveId;
		pendingDeleteId = null;
	}

	function handleSave(updated: PumpCurve) {
		projectStore.updatePumpCurve(updated.id, updated);
		editingCurveId = null;
	}

	function handleCancelEdit() {
		editingCurveId = null;
	}

	function handleDelete(e: Event, curveId: string) {
		e.stopPropagation();
		pendingDeleteId = curveId;
	}

	function confirmDelete(e: Event) {
		e.stopPropagation();
		if (pendingDeleteId) {
			projectStore.removePumpCurve(pendingDeleteId);
			if (editingCurveId === pendingDeleteId) {
				editingCurveId = null;
			}
			pendingDeleteId = null;
		}
	}

	function cancelDelete(e: Event) {
		e.stopPropagation();
		pendingDeleteId = null;
	}
</script>

<div class="flex flex-col gap-1">
	{#if $pumpLibrary.length === 0}
		<p class="px-1 py-2 text-center text-[0.6875rem] text-[var(--color-text-subtle)]">
			No pump curves defined
		</p>
	{:else}
		{#each $pumpLibrary as curve}
			<div class="flex flex-col">
				<!-- Curve Row -->
				<div
					onclick={() => handleEdit(curve.id)}
					onkeydown={(e) => e.key === 'Enter' && handleEdit(curve.id)}
					role="button"
					tabindex="0"
					class="group flex w-full cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors
						{editingCurveId === curve.id
						? 'bg-[var(--color-tree-selected)] text-[var(--color-text)]'
						: 'text-[var(--color-text-muted)] hover:bg-[var(--color-tree-hover)] hover:text-[var(--color-text)]'}"
				>
					<!-- Icon -->
					<svg class="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
					</svg>

					<!-- Name + Details -->
					<div class="min-w-0 flex-1">
						<span class="block truncate">{curve.name}</span>
						<span class="block text-[0.625rem] text-[var(--color-text-subtle)]">
							{curve.points.length} pts{curve.manufacturer ? ` - ${curve.manufacturer}` : ''}
						</span>
					</div>

					<!-- Delete -->
					{#if pendingDeleteId === curve.id}
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
							onclick={(e) => handleDelete(e, curve.id)}
							class="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded opacity-0 transition-opacity group-hover:opacity-100 hover:text-[var(--color-error)]"
							title="Delete pump curve"
						>
							<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
							</svg>
						</button>
					{/if}
				</div>

				<!-- Inline Editor -->
				{#if editingCurveId === curve.id}
					<div class="mt-1 px-1">
						<PumpCurveEditor {curve} onSave={handleSave} onCancel={handleCancelEdit} />
					</div>
				{/if}
			</div>
		{/each}
	{/if}

	<!-- Add Button -->
	<button
		type="button"
		onclick={handleAdd}
		class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-muted)]"
	>
		<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
		</svg>
		Add Pump Curve
	</button>
</div>
