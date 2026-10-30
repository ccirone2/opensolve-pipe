<script lang="ts">
	import type { AssignedFlow } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import AssignedFlowFields from '../AssignedFlowFields.svelte';
	import FieldSections from '../FieldSections.svelte';

	let { component }: { component: AssignedFlow } = $props();
	const ws = useWorkspace();
</script>

<FieldSections {component}>
	{#snippet field(path)}
		{#if path === 'flow'}
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
		{/if}
	{/snippet}
	{#snippet about()}
		A known flow drawn from the network (a process user, a coil, a fire-flow demand) or put into it
		(a metered make-up). It fixes a flow, not a pressure: the pressure at the port is a result, and
		its part of the network still needs a reservoir or reference node.
	{/snippet}
</FieldSections>
