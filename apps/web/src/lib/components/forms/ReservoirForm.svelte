<script lang="ts">
	import type { Reservoir } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The reservoir component to edit. */
		component: Reservoir;
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
		id="water_level"
		label="Water Level"
		value={component.water_level}
		unit="ft"
		min={0}
		onchange={(value) => onUpdate('water_level', value)}
	/>
</div>
