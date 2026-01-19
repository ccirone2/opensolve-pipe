<script lang="ts">
	import type { ValveComponent } from '$lib/models';
	import { VALVE_TYPE_LABELS } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The valve component to edit. */
		component: ValveComponent;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();
</script>

<div class="space-y-4">
	<NumberInput
		id="elevation"
		label="Elevation"
		value={component.elevation}
		unit="ft"
		onchange={(value) => onUpdate('elevation', value)}
	/>

	<div>
		<label for="valve_type" class="block text-sm font-medium text-gray-700">Valve Type</label>
		<select
			id="valve_type"
			value={component.valve_type}
			onchange={(e) => onUpdate('valve_type', (e.target as HTMLSelectElement).value)}
			class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		>
			{#each Object.entries(VALVE_TYPE_LABELS) as [value, label]}
				<option {value}>{label}</option>
			{/each}
		</select>
	</div>

	<NumberInput
		id="position"
		label="Position"
		value={(component.position ?? 1) * 100}
		unit="%"
		min={0}
		max={100}
		step={1}
		onchange={(value) => onUpdate('position', value / 100)}
		hint="0% = fully closed, 100% = fully open"
	/>

	{#if component.valve_type === 'prv' || component.valve_type === 'psv'}
		<NumberInput
			id="setpoint"
			label={component.valve_type === 'prv' ? 'Downstream Pressure Setting' : 'Relief Pressure Setting'}
			value={component.setpoint}
			unit="psi"
			min={0}
			required
			onchange={(value) => onUpdate('setpoint', value)}
		/>
	{:else if component.valve_type === 'fcv'}
		<NumberInput
			id="setpoint"
			label="Flow Setting"
			value={component.setpoint}
			unit="GPM"
			min={0}
			required
			onchange={(value) => onUpdate('setpoint', value)}
		/>
	{/if}
</div>
