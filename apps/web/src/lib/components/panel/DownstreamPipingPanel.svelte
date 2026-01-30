<script lang="ts">
	import { projectStore, components } from '$lib/stores';
	import { createDefaultPipingSegment, type PipingSegment, type Connection } from '$lib/models';
	import { PipeForm, FittingsTable } from '$lib/components/forms';

	interface Props {
		/** The component ID this piping originates from. */
		componentId: string;
		/** The downstream connections for this component. */
		connections: Connection[];
	}

	let { componentId, connections }: Props = $props();

	// For now, we only support editing the first downstream connection's piping
	let firstConnection = $derived(connections[0]);
	let piping = $derived(firstConnection?.piping);

	// Get target component name for display
	let targetComponent = $derived.by(() => {
		if (!firstConnection) return null;
		return $components.find((c) => c.id === firstConnection.target_component_id);
	});

	function initializePiping() {
		if (!firstConnection) return;
		const newPiping = createDefaultPipingSegment();
		projectStore.updateDownstreamPiping(componentId, firstConnection.target_component_id, newPiping);
	}

	function removePiping() {
		if (!firstConnection) return;
		projectStore.updateDownstreamPiping(
			componentId,
			firstConnection.target_component_id,
			undefined
		);
	}

	function updatePipeField(field: string, value: unknown) {
		if (!piping || !firstConnection) return;
		projectStore.updateDownstreamPiping(componentId, firstConnection.target_component_id, {
			...piping,
			pipe: { ...piping.pipe, [field]: value }
		});
	}

	function updateFittings(fittings: PipingSegment['fittings']) {
		if (!piping || !firstConnection) return;
		projectStore.updateDownstreamPiping(componentId, firstConnection.target_component_id, {
			...piping,
			fittings
		});
	}
</script>

<div class="space-y-4">
	{#if !firstConnection}
		<!-- No downstream connection -->
		<div class="rounded-lg border-2 border-dashed border-[var(--color-border)] p-6 text-center">
			<svg
				class="mx-auto h-12 w-12 text-[var(--color-text-subtle)]"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M13 7l5 5m0 0l-5 5m5-5H6"
				/>
			</svg>
			<p class="mt-2 text-sm text-[var(--color-text-muted)]">No downstream connection</p>
			<p class="mt-1 text-xs text-[var(--color-text-subtle)]">
				Add a component after this element to configure piping.
			</p>
		</div>
	{:else if !piping}
		<!-- Connection exists but no piping configured -->
		<div class="rounded-lg border-2 border-dashed border-[var(--color-border)] p-6 text-center">
			<svg
				class="mx-auto h-12 w-12 text-[var(--color-text-subtle)]"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M12 6v6m0 0v6m0-6h6m-6 0H6"
				/>
			</svg>
			<p class="mt-2 text-sm text-[var(--color-text-muted)]">
				No piping to {targetComponent?.name ?? 'downstream'}
			</p>
			<button
				type="button"
				onclick={initializePiping}
				class="mt-3 inline-flex items-center rounded-md bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-[var(--color-accent-text)] hover:bg-[var(--color-accent-hover)]"
			>
				Add Piping
			</button>
		</div>
	{:else}
		<!-- Target label -->
		<div class="rounded-md bg-[var(--color-surface-elevated)] px-3 py-2 text-sm text-[var(--color-text-muted)]">
			Piping to: <span class="font-medium text-[var(--color-text)]">{targetComponent?.name ?? 'downstream'}</span>
		</div>

		<!-- Pipe Configuration -->
		<div class="space-y-3">
			<h4 class="text-sm font-medium text-[var(--color-text)]">Pipe</h4>
			<PipeForm pipe={piping.pipe} onUpdate={updatePipeField} />
		</div>

		<!-- Fittings -->
		<div class="border-t border-[var(--color-border)] pt-4">
			<FittingsTable fittings={piping.fittings} onUpdate={updateFittings} />
		</div>

		<!-- Remove Piping Button -->
		<div class="border-t border-[var(--color-border)] pt-4">
			<button
				type="button"
				onclick={removePiping}
				class="text-sm text-[var(--color-error)] hover:opacity-80 hover:underline"
			>
				Remove piping
			</button>
		</div>
	{/if}
</div>
