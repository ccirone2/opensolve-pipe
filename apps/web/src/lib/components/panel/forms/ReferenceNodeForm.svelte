<script lang="ts">
	import type { IdealReferenceNode } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	let { component }: { component: IdealReferenceNode } = $props();
	const ws = useWorkspace();
</script>

<NumberField
	label="Pressure"
	value={component.pressure}
	category="pressure"
	gauge
	units={ws.units}
	bounds={schemaBounds('IdealReferenceNode', 'pressure')}
	hint="Fixed gauge pressure held at the port, like a large supply main or a closed loop's expansion tank."
	onchange={(v) =>
		v !== null &&
		ws.editComponent<IdealReferenceNode>(component.id, 'change reference pressure', (c) => {
			c.pressure = v;
		})}
/>
