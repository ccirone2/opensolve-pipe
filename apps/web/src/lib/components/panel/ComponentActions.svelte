<!-- Add after / add before / add branch / delete (SDD §3.1.1 ComponentActions). -->
<script lang="ts">
	import type { Component } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { connectionsOf } from '$lib/utils/graph';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import AddComponentDialog, { type AddMode } from './AddComponentDialog.svelte';
	import DeleteDialog from './DeleteDialog.svelte';

	let { component }: { component: Component } = $props();
	const ws = useWorkspace();

	let adding = $state<AddMode | null>(null);
	let deleting = $state(false);
	const connected = $derived(connectionsOf(ws.project, component.id).length > 0);
	const id = $props.id();
</script>

<div
	role="group"
	aria-label="Component actions"
	class="grid grid-cols-4 gap-1.5 sm:flex sm:flex-wrap sm:gap-2"
>
	<button type="button" class="btn action" onclick={() => (adding = 'after')}>
		<Icon name="plus" class="size-5 sm:size-4" /> Add after
	</button>
	<button
		type="button"
		class="btn action"
		disabled={!connected}
		aria-describedby={connected ? undefined : `${id}-why`}
		onclick={() => (adding = 'insert')}
	>
		<Icon name="insert" class="size-5 sm:size-4" /> Add before
	</button>
	<button
		type="button"
		class="btn action"
		disabled={!connected}
		aria-describedby={connected ? undefined : `${id}-why`}
		onclick={() => (adding = 'branch')}
	>
		<Icon name="branch" class="size-5 sm:size-4" /> Add branch
	</button>
	<button type="button" class="btn action text-red-800" onclick={() => (deleting = true)}>
		<Icon name="trash" class="size-5 sm:size-4" /> Delete
	</button>
</div>
{#if !connected}
	<p id="{id}-why" class="hint -mt-2">
		Add before and Add branch go into a connection; {component.name} has none yet. Use Add after to connect
		a first component.
	</p>
{/if}

{#if adding}
	<AddComponentDialog {component} mode={adding} onclose={() => (adding = null)} />
{/if}
{#if deleting}
	<DeleteDialog {component} onclose={() => (deleting = false)} />
{/if}

<style>
	/* Phones: icon above a short label, four in a row; wider screens: icon and label in a line. */
	.action {
		flex-direction: column;
		gap: 0.25rem;
		min-height: 3.5rem;
		padding: 0.375rem 0.25rem;
		font-size: 0.75rem;
		line-height: 1rem;
		white-space: normal;
	}

	@media (min-width: 40rem) {
		.action {
			flex-direction: row;
			gap: 0.5rem;
			min-height: 2.75rem;
			padding: 0 0.75rem;
			font-size: 0.875rem;
			line-height: 1.25rem;
			white-space: nowrap;
		}
	}
</style>
