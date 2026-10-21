<script lang="ts">
	import type { Component } from '$lib/api/types';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import { joinPlan } from '$lib/utils/edit';
	import { connectionAtPort, connectionsOf, otherEnd } from '$lib/utils/graph';
	import { componentName } from '$lib/utils/labels';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { focusCurrentHeading } from './focus';

	let { component, onclose }: { component: Component; onclose: () => void } = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const plan = $derived(joinPlan(ws.project, component.id));
	const joinable = $derived(plan !== null);
	const attached = $derived(connectionsOf(ws.project, component.id));
	/** The two components a join connects. */
	const ends = $derived(
		(plan?.ports ?? []).map((port) => {
			const connection = connectionAtPort(ws.project, component.id, port.id);
			return connection
				? componentName(
						ws.project,
						otherEnd(connection, { componentId: component.id, portId: port.id }).componentId
					)
				: '';
		})
	);
	const plugNote = $derived(
		!plan?.plugIds.length
			? ''
			: plan.plugIds.length === 1
				? 'The plug on its other port is removed too.'
				: 'The plugs on its other ports are removed too.'
	);
	let join = $state(true);

	async function confirm() {
		if (!ws.remove(component.id, joinable && join)) return;
		onclose();
		// The Delete button now belongs to the next component: continue from its heading.
		await focusCurrentHeading();
	}
</script>

<Dialog title="Delete {component.name}?" {onclose}>
	<div class="space-y-3 text-sm text-slate-700">
		{#if joinable}
			<label class="flex items-start gap-3 rounded-md border border-slate-200 p-3">
				<input id="{id}-join" type="checkbox" class="mt-1 size-4" bind:checked={join} />
				<span>
					<span class="block font-medium text-slate-900">Join {ends[0]} and {ends[1]}</span>
					Keep them connected with one connection: the pipes and fittings of both sides in series.
					{plugNote}
				</span>
			</label>
			{#if !join}
				<p>
					Its {attached.length} connections are removed and the ports at their other ends become free.
				</p>
			{/if}
		{:else if attached.length}
			<p>
				Its {attached.length === 1 ? 'connection is' : `${attached.length} connections are`} removed too,
				and the ports at the other end{attached.length === 1 ? '' : 's'} become free.
			</p>
		{/if}
		<p>You can undo this.</p>
	</div>
	{#snippet footer()}
		<button type="button" class="btn" onclick={onclose}>Cancel</button>
		<button type="button" class="btn btn-danger" onclick={confirm}>Delete</button>
	{/snippet}
</Dialog>
