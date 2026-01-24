<script lang="ts">
	import type { Plug } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The plug component to edit. */
		component: Plug;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();

	function updatePortSize(size: number) {
		if (component.ports.length > 0) {
			const newPorts = [...component.ports];
			newPorts[0] = { ...newPorts[0], nominal_size: size };
			onUpdate('ports', newPorts);
		}
	}
</script>

<div class="space-y-4">
	<div class="rounded-md bg-gray-50 p-3">
		<p class="text-sm text-gray-700">
			<strong>Plug/Cap:</strong> Dead-end boundary condition. Flow is zero at this point.
		</p>
	</div>

	<NumberInput
		id="elevation"
		label="Elevation"
		value={component.elevation}
		unit="ft"
		onchange={(value) => onUpdate('elevation', value)}
	/>

	<NumberInput
		id="port_size"
		label="Port Size"
		value={component.ports[0]?.nominal_size ?? 4}
		unit="in"
		min={0.5}
		hint="Nominal pipe size for connection"
		onchange={updatePortSize}
	/>
</div>
