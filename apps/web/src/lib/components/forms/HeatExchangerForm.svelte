<script lang="ts">
	import type { HeatExchanger } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The heat exchanger component to edit. */
		component: HeatExchanger;
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
		id="pressure_drop"
		label="Pressure Drop"
		value={component.pressure_drop}
		unit="psi"
		min={0}
		required
		onchange={(value) => onUpdate('pressure_drop', value)}
		hint="Pressure drop at design flow rate"
	/>

	<NumberInput
		id="design_flow"
		label="Design Flow"
		value={component.design_flow}
		unit="GPM"
		min={0}
		required
		onchange={(value) => onUpdate('design_flow', value)}
		hint="Flow rate at which pressure drop was measured"
	/>
</div>
