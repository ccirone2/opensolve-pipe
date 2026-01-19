<script lang="ts">
	import type { Tank } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The tank component to edit. */
		component: Tank;
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
		id="diameter"
		label="Diameter"
		value={component.diameter}
		unit="ft"
		min={0}
		required
		onchange={(value) => onUpdate('diameter', value)}
	/>

	<div class="grid grid-cols-3 gap-3">
		<NumberInput
			id="min_level"
			label="Min Level"
			value={component.min_level}
			unit="ft"
			min={0}
			required
			onchange={(value) => onUpdate('min_level', value)}
		/>

		<NumberInput
			id="max_level"
			label="Max Level"
			value={component.max_level}
			unit="ft"
			min={0}
			required
			onchange={(value) => onUpdate('max_level', value)}
		/>

		<NumberInput
			id="initial_level"
			label="Initial Level"
			value={component.initial_level}
			unit="ft"
			min={0}
			required
			onchange={(value) => onUpdate('initial_level', value)}
		/>
	</div>
</div>
