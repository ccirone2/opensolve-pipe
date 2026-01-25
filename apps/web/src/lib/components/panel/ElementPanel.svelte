<script lang="ts">
	import { projectStore } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		isReservoir,
		isTank,
		isJunction,
		isPump,
		isValve,
		isHeatExchanger,
		isStrainer,
		isOrifice,
		isSprinkler,
		isIdealReferenceNode,
		isNonIdealReferenceNode,
		isPlug,
		isTeeBranch,
		isWyeBranch,
		isCrossBranch,
		type Component,
		type IdealReferenceNode,
		type NonIdealReferenceNode
	} from '$lib/models';
	import {
		ReservoirForm,
		TankForm,
		JunctionForm,
		PumpForm,
		ValveForm,
		HeatExchangerForm,
		StrainerForm,
		OrificeForm,
		SprinklerForm,
		ReferenceNodeForm,
		PlugForm,
		TeeBranchForm,
		WyeBranchForm,
		CrossBranchForm
	} from '$lib/components/forms';

	interface Props {
		/** The component to display/edit. */
		component: Component;
	}

	let { component }: Props = $props();

	// Delete confirmation state
	let showDeleteConfirm = $state(false);

	function updateField(field: string, value: unknown) {
		projectStore.updateComponent(component.id, { [field]: value });
	}

	/**
	 * Handle switching reference node type between ideal and non-ideal.
	 * Converts the component data structure appropriately.
	 */
	function handleReferenceNodeTypeChange(newType: 'ideal_reference_node' | 'non_ideal_reference_node') {
		if (newType === 'ideal_reference_node') {
			// Convert from non-ideal to ideal
			const nonIdeal = component as NonIdealReferenceNode;
			// Use the first point's pressure as the fixed pressure, or default to 50
			const pressure = nonIdeal.pressure_flow_curve?.[0]?.pressure ?? 50;
			projectStore.updateComponent(component.id, {
				type: 'ideal_reference_node',
				pressure,
				// Remove non-ideal specific fields
				pressure_flow_curve: undefined,
				max_flow: undefined
			} as Partial<IdealReferenceNode>);
		} else {
			// Convert from ideal to non-ideal
			const ideal = component as IdealReferenceNode;
			projectStore.updateComponent(component.id, {
				type: 'non_ideal_reference_node',
				pressure_flow_curve: [
					{ flow: 0, pressure: ideal.pressure ?? 60 },
					{ flow: 100, pressure: (ideal.pressure ?? 60) - 10 }
				],
				// Remove ideal specific field
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
	<div class="border-b border-gray-200 pb-3">
		<span class="text-xs font-medium uppercase tracking-wide text-gray-500">
			{COMPONENT_TYPE_LABELS[component.type]}
		</span>
	</div>

	<!-- Common Fields -->
	<div>
		<label for="name" class="block text-sm font-medium text-gray-700">Name</label>
		<input
			type="text"
			id="name"
			value={component.name}
			oninput={(e) => handleTextInput('name', e)}
			class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		/>
	</div>

	<!-- Type-specific Fields -->
	<div class="border-t border-gray-200 pt-4">
		{#if isReservoir(component)}
			<ReservoirForm {component} onUpdate={updateField} />
		{:else if isTank(component)}
			<TankForm {component} onUpdate={updateField} />
		{:else if isJunction(component)}
			<JunctionForm {component} onUpdate={updateField} />
		{:else if isPump(component)}
			<PumpForm {component} onUpdate={updateField} />
		{:else if isValve(component)}
			<ValveForm {component} onUpdate={updateField} />
		{:else if isHeatExchanger(component)}
			<HeatExchangerForm {component} onUpdate={updateField} />
		{:else if isStrainer(component)}
			<StrainerForm {component} onUpdate={updateField} />
		{:else if isOrifice(component)}
			<OrificeForm {component} onUpdate={updateField} />
		{:else if isSprinkler(component)}
			<SprinklerForm {component} onUpdate={updateField} />
		{:else if isIdealReferenceNode(component) || isNonIdealReferenceNode(component)}
			<ReferenceNodeForm {component} onUpdate={updateField} onTypeChange={handleReferenceNodeTypeChange} />
		{:else if isPlug(component)}
			<PlugForm {component} onUpdate={updateField} />
		{:else if isTeeBranch(component)}
			<TeeBranchForm {component} onUpdate={updateField} />
		{:else if isWyeBranch(component)}
			<WyeBranchForm {component} onUpdate={updateField} />
		{:else if isCrossBranch(component)}
			<CrossBranchForm {component} onUpdate={updateField} />
		{/if}
	</div>

	<!-- Delete Button -->
	<div class="border-t border-gray-200 pt-4">
		{#if showDeleteConfirm}
			<div class="rounded-md border border-red-200 bg-red-50 p-3">
				<p class="text-sm font-medium text-red-800">Delete "{component.name}"?</p>
				<p class="mt-1 text-xs text-red-600">This action cannot be undone.</p>
				<div class="mt-3 flex gap-2">
					<button
						type="button"
						onclick={confirmDelete}
						class="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
					>
						Delete
					</button>
					<button
						type="button"
						onclick={cancelDelete}
						class="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
					>
						Cancel
					</button>
				</div>
			</div>
		{:else}
			<button
				type="button"
				onclick={handleDeleteClick}
				class="text-sm text-red-600 hover:text-red-700 hover:underline"
			>
				Delete this component
			</button>
		{/if}
	</div>
</div>
