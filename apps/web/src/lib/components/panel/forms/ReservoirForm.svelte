<script lang="ts">
	import type { Reservoir } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	let { component }: { component: Reservoir } = $props();
	const ws = useWorkspace();
</script>

<NumberField
	label="Liquid level"
	value={component.liquidLevel}
	category="length"
	units={ws.units}
	bounds={schemaBounds('Reservoir', 'liquidLevel')}
	hint="Height of the liquid surface above the reservoir's elevation."
	onchange={(v) =>
		v !== null &&
		ws.editComponent<Reservoir>(component.id, 'change liquid level', (c) => {
			c.liquidLevel = v;
		})}
/>
<NumberField
	label="Surface pressure"
	value={component.surfacePressure}
	category="pressure"
	gauge
	units={ws.units}
	bounds={schemaBounds('Reservoir', 'surfacePressure')}
	hint="Gauge pressure on the liquid surface; 0 means open to the atmosphere."
	onchange={(v) =>
		v !== null &&
		ws.editComponent<Reservoir>(component.id, 'change surface pressure', (c) => {
			c.surfacePressure = v;
		})}
/>
