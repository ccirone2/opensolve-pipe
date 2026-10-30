<!-- Every component, to open one directly; the path is rebuilt from the start component. -->
<script lang="ts">
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import { kindLabel } from '$lib/utils/labels';
	import { reachable } from '$lib/utils/graph';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	let { onclose }: { onclose: () => void } = $props();
	const ws = useWorkspace();
	const id = $props.id();
	let filter = $state('');

	const connected = $derived(
		ws.nav.startId ? reachable(ws.project, ws.nav.startId) : new Set<string>()
	);
	const shown = $derived.by(() => {
		const query = filter.trim().toLowerCase();
		return ws.project.components.filter(
			(c) =>
				!query ||
				c.name.toLowerCase().includes(query) ||
				c.id.toLowerCase().includes(query) ||
				kindLabel(c).toLowerCase().includes(query)
		);
	});

	function go(componentId: string) {
		ws.nav.jumpTo(componentId);
		onclose();
	}
</script>

<Dialog title="Jump to a component" {onclose}>
	{#if ws.project.components.length > 6}
		<label for="{id}-filter" class="label mb-1">Filter</label>
		<input
			id="{id}-filter"
			class="input mb-3"
			type="search"
			autocomplete="off"
			placeholder="Name, id or type"
			bind:value={filter}
		/>
	{/if}
	<ul class="divide-y divide-slate-200 rounded-lg border border-slate-200">
		{#each shown as component (component.id)}
			{@const current = component.id === ws.nav.current?.id}
			<li>
				<button
					type="button"
					class="flex min-h-ctl w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-50"
					aria-current={current ? 'true' : undefined}
					onclick={() => go(component.id)}
				>
					<span class="min-w-0 flex-1">
						<span class={['block truncate', current ? 'font-semibold' : 'font-medium']}>
							{component.name}
						</span>
						<span class="block text-sm text-slate-600">
							{kindLabel(component)} · <span class="font-mono">{component.id}</span>
							{#if !connected.has(component.id)}· not connected to the start{/if}
						</span>
					</span>
					{#if current}<span class="text-sm text-slate-600">Current</span>{/if}
				</button>
			</li>
		{:else}
			<li class="px-3 py-3 text-sm text-slate-600">No component matches “{filter}”.</li>
		{/each}
	</ul>
</Dialog>
