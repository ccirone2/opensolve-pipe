<script lang="ts">
	import type { Junction } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The junction component to edit. */
		component: Junction;
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
		id="demand"
		label="Demand"
		value={component.demand}
		unit="GPM"
		min={0}
		onchange={(value) => onUpdate('demand', value)}
		hint="Flow rate demand at this junction"
	/>
</div>
