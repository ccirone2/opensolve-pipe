<script lang="ts">
	/**
	 * BranchSelector - UI for managing branches from tee/wye/cross components.
	 *
	 * Shows all downstream connections and allows:
	 * - Adding new branches
	 * - Connecting branches to existing components (loop closure)
	 * - Navigating to branch targets
	 */
	import { projectStore, components, navigationStore } from '$lib/stores';
	import type { Component, ComponentType } from '$lib/models';
	import { isTeeBranch, isWyeBranch, isCrossBranch } from '$lib/models';

	interface Props {
		/** The branch component (tee, wye, or cross). */
		component: Component;
	}

	let { component }: Props = $props();

	// Determine max branches based on component type
	let maxBranches = $derived.by(() => {
		if (isCrossBranch(component)) return 4; // Cross has 4 outlets
		if (isTeeBranch(component) || isWyeBranch(component)) return 3; // Tee/Wye have 3 outlets
		return 1; // Default for non-branch components
	});

	// Check if this is a branch component
	let isBranchComponent = $derived(
		isTeeBranch(component) || isWyeBranch(component) || isCrossBranch(component)
	);

	// Get current downstream connections
	let downstreamConnections = $derived(component.downstream_connections);

	// Can add more branches?
	let canAddBranch = $derived(
		isBranchComponent && downstreamConnections.length < maxBranches
	);

	// Get available components for loop closure (excluding self and already connected)
	let availableTargets = $derived.by(() => {
		const connectedIds = new Set(downstreamConnections.map((c) => c.target_component_id));
		return $components.filter(
			(c) => c.id !== component.id && !connectedIds.has(c.id)
		);
	});

	// UI state
	let showLoopSelector = $state(false);
	let selectedTargetId = $state<string | null>(null);

	/**
	 * Add a new inline component on this branch.
	 */
	function addInlineBranch(type: ComponentType) {
		const componentIndex = $components.findIndex((c) => c.id === component.id);
		// Add after the current component
		projectStore.addComponent(type, componentIndex + 1);
	}

	/**
	 * Connect to an existing component (loop closure).
	 */
	function connectToExisting() {
		if (!selectedTargetId) return;

		projectStore.addConnection(component.id, selectedTargetId);
		showLoopSelector = false;
		selectedTargetId = null;
	}

	/**
	 * Remove a branch connection.
	 */
	function removeBranch(targetId: string) {
		projectStore.removeConnection(component.id, targetId);
	}

	/**
	 * Navigate to a downstream component.
	 */
	function navigateTo(targetId: string) {
		navigationStore.navigateTo(targetId);
	}

	/**
	 * Get the target component by ID.
	 */
	function getTargetComponent(targetId: string): Component | undefined {
		return $components.find((c) => c.id === targetId);
	}

	/** Branch type label. */
	let branchTypeLabel = $derived.by(() => {
		if (isTeeBranch(component)) return 'Tee';
		if (isWyeBranch(component)) return 'Wye';
		if (isCrossBranch(component)) return 'Cross';
		return 'Branch';
	});

	/** Component type options for new branches. */
	const branchComponentTypes: { type: ComponentType; label: string; icon: string }[] = [
		{ type: 'junction', label: 'Junction', icon: '●' },
		{ type: 'valve', label: 'Valve', icon: '⊗' },
		{ type: 'pump', label: 'Pump', icon: '◉' },
		{ type: 'sprinkler', label: 'Sprinkler', icon: '✱' },
		{ type: 'plug', label: 'Dead End', icon: '■' }
	];
</script>

{#if isBranchComponent}
	<div class="space-y-4">
		<!-- Header -->
		<div class="flex items-center justify-between">
			<h4 class="text-sm font-medium text-[var(--color-text)]">
				{branchTypeLabel} Branches ({downstreamConnections.length}/{maxBranches})
			</h4>
			{#if canAddBranch}
				<span class="text-xs text-[var(--color-text-muted)]">
					{maxBranches - downstreamConnections.length} available
				</span>
			{/if}
		</div>

		<!-- Existing Branches -->
		{#if downstreamConnections.length > 0}
			<div class="space-y-2">
				{#each downstreamConnections as connection, index}
					{@const target = getTargetComponent(connection.target_component_id)}
					<div
						class="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
					>
						<div class="flex items-center gap-3">
							<div
								class="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-accent-muted)] text-sm font-medium text-[var(--color-accent)]"
							>
								{index + 1}
							</div>
							<div>
								<p class="text-sm font-medium text-[var(--color-text)]">
									{target?.name ?? 'Unknown'}
								</p>
								<p class="text-xs text-[var(--color-text-muted)] capitalize">
									{target?.type.replace(/_/g, ' ') ?? 'Unknown type'}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<button
								type="button"
								onclick={() => navigateTo(connection.target_component_id)}
								class="rounded px-2 py-1 text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent-muted)]"
							>
								Go to
							</button>
							<button
								type="button"
								onclick={() => removeBranch(connection.target_component_id)}
								class="rounded px-2 py-1 text-xs font-medium text-[var(--color-error)] hover:bg-red-50 dark:hover:bg-red-900/20"
								title="Remove branch"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M6 18L18 6M6 6l12 12"
									/>
								</svg>
							</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="rounded-lg border-2 border-dashed border-[var(--color-border)] p-4 text-center">
				<p class="text-sm text-[var(--color-text-muted)]">No branches configured</p>
				<p class="mt-1 text-xs text-[var(--color-text-subtle)]">
					Add downstream connections for this {branchTypeLabel.toLowerCase()}
				</p>
			</div>
		{/if}

		<!-- Add Branch Section -->
		{#if canAddBranch}
			<div class="border-t border-[var(--color-border)] pt-4">
				<p class="mb-3 text-sm font-medium text-[var(--color-text)]">Add Branch</p>

				<!-- Quick Add Buttons -->
				<div class="mb-3 flex flex-wrap gap-2">
					{#each branchComponentTypes as { type, label, icon }}
						<button
							type="button"
							onclick={() => addInlineBranch(type)}
							class="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-elevated)]"
						>
							<span class="text-xs">{icon}</span>
							{label}
						</button>
					{/each}
				</div>

				<!-- Loop Closure -->
				<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
					<button
						type="button"
						onclick={() => (showLoopSelector = !showLoopSelector)}
						class="flex w-full items-center justify-between text-sm text-[var(--color-text)]"
					>
						<span class="font-medium">Connect to existing component</span>
						<svg
							class="h-4 w-4 transition-transform {showLoopSelector ? 'rotate-180' : ''}"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
						</svg>
					</button>

					{#if showLoopSelector}
						<div class="mt-3 space-y-3">
							{#if availableTargets.length === 0}
								<p class="text-xs text-[var(--color-text-muted)]">
									No available components for loop closure
								</p>
							{:else}
								<select
									bind:value={selectedTargetId}
									class="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)]"
								>
									<option value={null}>Select a component...</option>
									{#each availableTargets as target}
										<option value={target.id}>
											{target.name} ({target.type.replace(/_/g, ' ')})
										</option>
									{/each}
								</select>

								<button
									type="button"
									onclick={connectToExisting}
									disabled={!selectedTargetId}
									class="w-full rounded-md bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-[var(--color-accent-text)] hover:bg-[var(--color-accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
								>
									Create Loop Connection
								</button>
							{/if}

							<p class="text-xs text-[var(--color-text-subtle)]">
								Loop closure connects this branch to an existing component, creating a closed network loop.
							</p>
						</div>
					{/if}
				</div>
			</div>
		{:else if isBranchComponent}
			<div class="rounded-lg bg-[var(--color-warning-muted)] p-3 text-sm text-[var(--color-warning)]">
				All {maxBranches} branch connections are in use.
			</div>
		{/if}
	</div>
{:else}
	<!-- Not a branch component -->
	<div class="rounded-lg border-2 border-dashed border-[var(--color-border)] p-4 text-center">
		<p class="text-sm text-[var(--color-text-muted)]">
			Branch management is only available for tee, wye, and cross components.
		</p>
	</div>
{/if}
