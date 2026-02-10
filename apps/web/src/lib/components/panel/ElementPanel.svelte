<script lang="ts">
	import { projectStore } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		isIdealReferenceNode,
		isNonIdealReferenceNode,
		type Component,
		type IdealReferenceNode,
		type NonIdealReferenceNode
	} from '$lib/models';
	import { FORM_REGISTRY, ReferenceNodeForm } from '$lib/components/forms';

	interface Props {
		/** The component to display/edit. */
		component: Component;
	}

	let { component }: Props = $props();

	// Delete confirmation state
	let showDeleteConfirm = $state(false);

	// Look up the form component from the registry
	let FormComponent = $derived(FORM_REGISTRY[component.type]);

	// Whether this is a reference node (needs special onTypeChange prop)
	let isReferenceNode = $derived(
		isIdealReferenceNode(component) || isNonIdealReferenceNode(component)
	);

	function updateField(field: string, value: unknown) {
		projectStore.updateComponent(component.id, { [field]: value });
	}

	/**
	 * Handle switching reference node type between ideal and non-ideal.
	 * Converts the component data structure appropriately.
	 */
	function handleReferenceNodeTypeChange(newType: 'ideal_reference_node' | 'non_ideal_reference_node') {
		if (newType === 'ideal_reference_node') {
			const nonIdeal = component as NonIdealReferenceNode;
			const pressure = nonIdeal.pressure_flow_curve?.[0]?.pressure ?? 50;
			projectStore.updateComponent(component.id, {
				type: 'ideal_reference_node',
				pressure,
				pressure_flow_curve: undefined,
				max_flow: undefined
			} as Partial<IdealReferenceNode>);
		} else {
			const ideal = component as IdealReferenceNode;
			projectStore.updateComponent(component.id, {
				type: 'non_ideal_reference_node',
				pressure_flow_curve: [
					{ flow: 0, pressure: ideal.pressure ?? 60 },
					{ flow: 100, pressure: (ideal.pressure ?? 60) - 10 }
				],
				pressure: undefined
			} as Partial<NonIdealReferenceNode>);
		}
	}

	function handleTextInput(field: string, e: Event) {
		const input = e.target as HTMLInputElement;
		updateField(field, input.value);
	}

	function handleDeleteClick() {
		showDeleteConfirm = true;
	}

	function confirmDelete() {
		projectStore.removeComponent(component.id);
		showDeleteConfirm = false;
	}

	function cancelDelete() {
		showDeleteConfirm = false;
	}
</script>

<div class="space-y-4">
	<!-- Component Header -->
	<div class="border-b border-[var(--color-border)] pb-3">
		<span class="section-heading">
			{COMPONENT_TYPE_LABELS[component.type]}
		</span>
	</div>

	<!-- Common Fields -->
	<div>
		<label for="name" class="block text-sm font-medium text-[var(--color-text)]">Name</label>
		<input
			type="text"
			id="name"
			value={component.name}
			oninput={(e) => handleTextInput('name', e)}
			class="form-input"
		/>
	</div>

	<!-- Type-specific Fields (registry-based) -->
	<div class="border-t border-[var(--color-border)] pt-4">
		{#if isReferenceNode}
			{@const refComponent = component as import('$lib/models').IdealReferenceNode | import('$lib/models').NonIdealReferenceNode}
			<ReferenceNodeForm component={refComponent} onUpdate={updateField} onTypeChange={handleReferenceNodeTypeChange} />
		{:else if FormComponent}
			<FormComponent {component} onUpdate={updateField} />
		{/if}
	</div>

	<!-- Delete Button -->
	<div class="border-t border-[var(--color-border)] pt-4">
		{#if showDeleteConfirm}
			<div class="rounded-md border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 p-3">
				<p class="text-sm font-medium text-[var(--color-error)]">Delete "{component.name}"?</p>
				<p class="mt-1 text-xs text-[var(--color-error)]/80">This action cannot be undone.</p>
				<div class="mt-3 flex gap-2">
					<button
						type="button"
						onclick={confirmDelete}
						class="rounded-md bg-[var(--color-error)] px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
					>
						Delete
					</button>
					<button
						type="button"
						onclick={cancelDelete}
						class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-elevated)]"
					>
						Cancel
					</button>
				</div>
			</div>
		{:else}
			<button
				type="button"
				onclick={handleDeleteClick}
				class="text-sm text-[var(--color-error)] hover:opacity-80 hover:underline"
			>
				Delete this component
			</button>
		{/if}
	</div>
</div>
