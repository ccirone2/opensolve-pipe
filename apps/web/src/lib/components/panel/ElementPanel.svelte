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
		type Component
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
		SprinklerForm
	} from '$lib/components/forms';

	interface Props {
		/** The component to display/edit. */
		component: Component;
	}

	let { component }: Props = $props();

	function updateField(field: string, value: unknown) {
		projectStore.updateComponent(component.id, { [field]: value });
	}

	function handleTextInput(field: string, e: Event) {
		const input = e.target as HTMLInputElement;
		updateField(field, input.value);
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
		{/if}
	</div>

	<!-- Delete Button -->
	<div class="border-t border-gray-200 pt-4">
		<button
			type="button"
			onclick={() => projectStore.removeComponent(component.id)}
			class="text-sm text-red-600 hover:text-red-700 hover:underline"
		>
			Delete this component
		</button>
	</div>
</div>
