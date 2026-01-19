<script lang="ts">
	import type { Orifice } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The orifice component to edit. */
		component: Orifice;
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

	<NumberInput
		id="orifice_diameter"
		label="Orifice Diameter"
		value={component.orifice_diameter}
		unit="in"
		min={0}
		required
		onchange={(value) => onUpdate('orifice_diameter', value)}
	/>

	<NumberInput
		id="discharge_coefficient"
		label="Discharge Coefficient (Cd)"
		value={component.discharge_coefficient}
		min={0}
		max={1}
		step={0.01}
		onchange={(value) => onUpdate('discharge_coefficient', value)}
		hint="Typically 0.6-0.65 for sharp-edged orifice"
	/>
</div>
