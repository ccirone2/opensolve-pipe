<script lang="ts">
	import { projectStore } from '$lib/stores';
	import { createDefaultPipingSegment, type PipingSegment } from '$lib/models';
	import { PipeForm, FittingsTable } from '$lib/components/forms';

	interface Props {
		/** The component ID this piping belongs to. */
		componentId: string;
		/** The current piping segment (or undefined if none). */
		piping?: PipingSegment;
	}

	let { componentId, piping }: Props = $props();

	function initializePiping() {
		const newPiping = createDefaultPipingSegment();
		projectStore.updateUpstreamPiping(componentId, newPiping);
	}

	function removePiping() {
		projectStore.updateUpstreamPiping(componentId, undefined);
	}

	function updatePipeField(field: string, value: unknown) {
		if (!piping) return;
		projectStore.updateUpstreamPiping(componentId, {
			...piping,
			pipe: { ...piping.pipe, [field]: value }
		});
	}

	function updateFittings(fittings: PipingSegment['fittings']) {
		if (!piping) return;
		projectStore.updateUpstreamPiping(componentId, {
			...piping,
			fittings
		});
	}
</script>

<div class="space-y-4">
	{#if !piping}
		<!-- No piping configured -->
		<div class="rounded-lg border-2 border-dashed border-gray-300 p-6 text-center">
			<svg
				class="mx-auto h-12 w-12 text-gray-400"
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
			<p class="mt-2 text-sm text-gray-600">No upstream piping configured</p>
			<button
				type="button"
				onclick={initializePiping}
				class="mt-3 inline-flex items-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
			>
				Add Piping
			</button>
		</div>
	{:else}
		<!-- Pipe Configuration -->
		<div class="space-y-3">
			<h4 class="text-sm font-medium text-gray-900">Pipe</h4>
			<PipeForm pipe={piping.pipe} onUpdate={updatePipeField} />
		</div>

		<!-- Fittings -->
		<div class="border-t border-gray-200 pt-4">
			<FittingsTable fittings={piping.fittings} onUpdate={updateFittings} />
		</div>

		<!-- Remove Piping Button -->
		<div class="border-t border-gray-200 pt-4">
			<button
				type="button"
				onclick={removePiping}
				class="text-sm text-red-600 hover:text-red-700 hover:underline"
			>
				Remove piping
			</button>
		</div>
	{/if}
</div>
