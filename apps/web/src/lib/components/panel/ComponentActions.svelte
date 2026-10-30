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

<div role="group" aria-label="Component actions" class="grid grid-cols-4 gap-1 sm:flex sm:gap-1">
	<button type="button" class="btn action" onclick={() => (adding = 'after')}>
		<Icon name="plus" class="size-4 shrink-0" /> Add after
	</button>
	<button
		type="button"
		class="btn action"
		disabled={!connected}
		aria-describedby={connected ? undefined : `${id}-why`}
		onclick={() => (adding = 'insert')}
	>
		<Icon name="insert" class="size-4 shrink-0" /> Add before
	</button>
	<button
		type="button"
		class="btn action"
		disabled={!connected}
		aria-describedby={connected ? undefined : `${id}-why`}
		onclick={() => (adding = 'branch')}
	>
		<Icon name="branch" class="size-4 shrink-0" /> Add branch
	</button>
	<button type="button" class="btn btn-quiet action text-red-800" onclick={() => (deleting = true)}>
		<Icon name="trash" class="size-4 shrink-0" /> Delete
	</button>
</div>
{#if !connected}
	<p id="{id}-why" class="hint basis-full">
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
	/*
	 * One row of icon and label, the control height (build-density.md §6): four in a row on
	 * phones, beside the Properties and Piping tabs on wider screens.
	 */
	.action {
		gap: 0.25rem;
		padding: 0 0.25rem;
		font-size: 0.75rem;
		line-height: 0.875rem;
		/* Below 360 px a label wraps inside its button rather than running past it. */
		white-space: normal;
		text-align: left;
	}

	@media (min-width: 40rem) {
		.action {
			gap: 0.375rem;
			padding: 0 0.5rem;
			font-size: 0.875rem;
			line-height: 1.25rem;
			white-space: nowrap;
		}
	}
</style>
