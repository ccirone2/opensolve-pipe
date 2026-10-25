<script lang="ts">
	import type { AssignedFlow } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import AssignedFlowFields from '../AssignedFlowFields.svelte';

	let { component }: { component: AssignedFlow } = $props();
	const ws = useWorkspace();
</script>

<AssignedFlowFields
	flow={component.flow}
	units={ws.units}
	change={ws.componentChange(component.id, 'flow')}
	onchange={(flow, changed) =>
		ws.editComponent<AssignedFlow>(
			component.id,
			changed === 'direction' ? 'change flow direction' : 'change assigned flow',
			(c) => {
				c.flow = flow;
			}
		)}
/>
<p class="hint sm:col-span-2">
	A known flow drawn from the network (a process user, a coil, a fire-flow demand) or put into it (a
	metered make-up). It fixes a flow, not a pressure: the pressure at the port is a result, and its
	part of the network still needs a reservoir or reference node.
</p>
