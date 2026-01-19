<script lang="ts">
	import type { Strainer } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The strainer component to edit. */
		component: Strainer;
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
		onchange={(value) => onUpdate('k_factor', value)}
		hint="Resistance coefficient (leave blank for default)"
	/>
</div>
