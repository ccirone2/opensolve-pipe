<script lang="ts">
	import { projectStore, components } from '$lib/stores';
	import { createDefaultPipingSegment, type PipingSegment, type Connection } from '$lib/models';
	import { isTeeBranch, isWyeBranch, isCrossBranch } from '$lib/models';
	import { PipeForm, FittingsTable } from '$lib/components/forms';
	import BranchSelector from './BranchSelector.svelte';

	interface Props {
		/** The component ID this piping originates from. */
		componentId: string;
		/** The downstream connections for this component. */
		connections: Connection[];
	}

	let { componentId, connections }: Props = $props();

	// Get the current component
	let currentComponent = $derived($components.find((c) => c.id === componentId));

	// Check if this is a branch component
	let isBranchComponent = $derived(
		currentComponent &&
			(isTeeBranch(currentComponent) ||
				isWyeBranch(currentComponent) ||
				isCrossBranch(currentComponent))
	);

	// Track which connection is expanded for editing
	let expandedConnectionIndex = $state<number | null>(null);

	// Auto-expand single connection
	$effect(() => {
		if (connections.length === 1 && expandedConnectionIndex === null) {
			expandedConnectionIndex = 0;
		}
	});

	// Get target component name for display
	function getTargetComponent(targetId: string) {
		return $components.find((c) => c.id === targetId);
	}

	function initializePiping(targetId: string) {
		const newPiping = createDefaultPipingSegment();
		projectStore.updateDownstreamPiping(componentId, targetId, newPiping);
	}

	function removePiping(targetId: string) {
		projectStore.updateDownstreamPiping(componentId, targetId, undefined);
	}

	function updatePipeField(targetId: string, piping: PipingSegment, field: string, value: unknown) {
		projectStore.updateDownstreamPiping(componentId, targetId, {
			...piping,
			pipe: { ...piping.pipe, [field]: value }
		});
	}

	function updateFittings(targetId: string, piping: PipingSegment, fittings: PipingSegment['fittings']) {
		projectStore.updateDownstreamPiping(componentId, targetId, {
			...piping,
			fittings
		});
	}

	function toggleExpanded(index: number) {
		expandedConnectionIndex = expandedConnectionIndex === index ? null : index;
	}
</script>

<div class="space-y-4">
	{#if isBranchComponent && currentComponent}
		<!-- Branch component: Show branch selector -->
		<BranchSelector component={currentComponent} />

		{#if connections.length > 0}
			<div class="border-t border-[var(--color-border)] pt-4">
				<h4 class="mb-3 text-sm font-medium text-[var(--color-text)]">Branch Piping</h4>
			</div>
		{/if}
	{/if}

	{#if connections.length === 0}
		{#if !isBranchComponent}
			<!-- No downstream connection for regular component -->
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
		{/if}
	{:else if connections.length === 1}
		<!-- Single connection: show piping editor directly -->
		{@const connection = connections[0]}
		{@const target = getTargetComponent(connection.target_component_id)}
		{@const piping = connection.piping}

		{#if !piping}
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
					No piping to {target?.name ?? 'downstream'}
				</p>
				<button
					type="button"
					onclick={() => initializePiping(connection.target_component_id)}
					class="mt-3 inline-flex items-center rounded-md bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-[var(--color-accent-text)] hover:bg-[var(--color-accent-hover)]"
				>
					Add Piping
				</button>
			</div>
		{:else}
			<!-- Target label -->
			<div class="rounded-md bg-[var(--color-surface-elevated)] px-3 py-2 text-sm text-[var(--color-text-muted)]">
				Piping to: <span class="font-medium text-[var(--color-text)]">{target?.name ?? 'downstream'}</span>
			</div>

			<!-- Pipe Configuration -->
			<div class="space-y-3">
				<h4 class="text-sm font-medium text-[var(--color-text)]">Pipe</h4>
				<PipeForm
					pipe={piping.pipe}
					onUpdate={(field, value) => updatePipeField(connection.target_component_id, piping, field, value)}
				/>
			</div>

			<!-- Fittings -->
			<div class="border-t border-[var(--color-border)] pt-4">
				<FittingsTable
					fittings={piping.fittings}
					onUpdate={(fittings) => updateFittings(connection.target_component_id, piping, fittings)}
				/>
			</div>

			<!-- Remove Piping Button -->
			<div class="border-t border-[var(--color-border)] pt-4">
				<button
					type="button"
					onclick={() => removePiping(connection.target_component_id)}
					class="text-sm text-[var(--color-error)] hover:opacity-80 hover:underline"
				>
					Remove piping
				</button>
			</div>
		{/if}
	{:else}
		<!-- Multiple connections: show accordion -->
		<div class="space-y-2">
			{#each connections as connection, index}
				{@const target = getTargetComponent(connection.target_component_id)}
				{@const piping = connection.piping}
				{@const isExpanded = expandedConnectionIndex === index}

				<div class="rounded-lg border border-[var(--color-border)] overflow-hidden">
					<!-- Accordion Header -->
					<button
						type="button"
						onclick={() => toggleExpanded(index)}
						class="flex w-full items-center justify-between bg-[var(--color-surface)] px-4 py-3 text-left hover:bg-[var(--color-surface-elevated)]"
					>
						<div class="flex items-center gap-3">
							<div
								class="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--color-accent-muted)] text-xs font-medium text-[var(--color-accent)]"
							>
								{index + 1}
							</div>
							<div>
								<span class="text-sm font-medium text-[var(--color-text)]">
									{target?.name ?? 'Unknown'}
								</span>
								{#if piping}
									<span class="ml-2 text-xs text-[var(--color-text-muted)]">
										{piping.pipe.length} ft
									</span>
								{:else}
									<span class="ml-2 text-xs text-[var(--color-warning)]">No piping</span>
								{/if}
							</div>
						</div>
						<svg
							class="h-5 w-5 text-[var(--color-text-muted)] transition-transform {isExpanded
								? 'rotate-180'
								: ''}"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
						</svg>
					</button>

					<!-- Accordion Content -->
					{#if isExpanded}
						<div class="border-t border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-4">
							{#if !piping}
								<div class="text-center">
									<p class="text-sm text-[var(--color-text-muted)]">
										No piping configured for this branch
									</p>
									<button
										type="button"
										onclick={() => initializePiping(connection.target_component_id)}
										class="mt-2 inline-flex items-center rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-[var(--color-accent-text)] hover:bg-[var(--color-accent-hover)]"
									>
										Add Piping
									</button>
								</div>
							{:else}
								<div class="space-y-4">
									<!-- Pipe Configuration -->
									<div class="space-y-3">
										<h5 class="text-sm font-medium text-[var(--color-text)]">Pipe</h5>
										<PipeForm
											pipe={piping.pipe}
											onUpdate={(field, value) =>
												updatePipeField(connection.target_component_id, piping, field, value)}
										/>
									</div>

									<!-- Fittings -->
									<div class="border-t border-[var(--color-border)] pt-4">
										<FittingsTable
											fittings={piping.fittings}
											onUpdate={(fittings) =>
												updateFittings(connection.target_component_id, piping, fittings)}
										/>
									</div>

									<!-- Remove Piping -->
									<div class="border-t border-[var(--color-border)] pt-4">
										<button
											type="button"
											onclick={() => removePiping(connection.target_component_id)}
											class="text-sm text-[var(--color-error)] hover:opacity-80 hover:underline"
										>
											Remove piping
										</button>
									</div>
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
