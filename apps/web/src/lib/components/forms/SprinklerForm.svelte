<script lang="ts">
	import type { Sprinkler } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The sprinkler component to edit. */
		component: Sprinkler;
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
		id="k_factor"
		label="K-Factor"
		value={component.k_factor}
		min={0}
		step={0.1}
		required
		onchange={(value) => onUpdate('k_factor', value)}
		hint="Q = K x sqrt(P), where Q is GPM and P is psi"
	/>

	<NumberInput
		id="design_pressure"
		label="Design Pressure"
		value={component.design_pressure}
		unit="psi"
		min={0}
		onchange={(value) => onUpdate('design_pressure', value)}
		hint="Optional target pressure at sprinkler"
	/>
</div>
