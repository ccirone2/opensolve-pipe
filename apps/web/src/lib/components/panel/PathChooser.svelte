<!--
	Asked when Next has more than one way forward (a tee, a multi-port reservoir) or a loop:
	lists each connection with the ports at both ends; loops are offered as a jump back.
-->
<script lang="ts">
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { componentById, type NextOption } from '$lib/utils/graph';
	import { kindLabel, portLabel } from '$lib/utils/labels';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	interface Props {
		options: readonly NextOption[];
		onchoose: (option: NextOption) => void;
		onclose: () => void;
	}

	let { options, onchoose, onclose }: Props = $props();
	const ws = useWorkspace();
	const forward = $derived(options.filter((o) => !o.loop));
	const loops = $derived(options.filter((o) => o.loop));
	const here = $derived(ws.nav.current?.name ?? '');
</script>

<Dialog title="Which way from {here}?" {onclose}>
	{#if forward.length}
		<ul class="space-y-2">
			{#each forward as option (option.connection.id)}
				{@const other = componentById(ws.project, option.otherId)}
				<li>
					<button
						type="button"
						class="card flex min-h-11 w-full items-center gap-3 px-3 py-2 text-left hover:border-blue-400 hover:bg-blue-50"
						onclick={() => onchoose(option)}
					>
						<span class="min-w-0 flex-1">
							<span class="block font-medium">{other?.name ?? option.otherId}</span>
							<span class="block text-sm text-slate-600">
								{other ? kindLabel(other) : ''} · {portLabel(option.portId)} → {portLabel(
									option.otherPortId
								)} · connection {option.connection.id}
							</span>
						</span>
						<Icon name="right" class="size-5 shrink-0 text-slate-500" />
					</button>
				</li>
			{/each}
		</ul>
	{/if}
	{#if loops.length}
		<h3 class="section-title mt-4 mb-2">Loops back to the path</h3>
		<ul class="space-y-2">
			{#each loops as option (option.connection.id)}
				{@const other = componentById(ws.project, option.otherId)}
				<li>
					<button
						type="button"
						class="card flex min-h-11 w-full items-center gap-3 border-dashed px-3 py-2 text-left hover:border-blue-400 hover:bg-blue-50"
						onclick={() => onchoose(option)}
					>
						<Icon name="undo" class="size-5 shrink-0 text-slate-500" />
						<span class="min-w-0 flex-1">
							<span class="block font-medium">Jump back to {other?.name ?? option.otherId}</span>
							<span class="block text-sm text-slate-600">
								{portLabel(option.portId)} → {portLabel(option.otherPortId)} · connection {option
									.connection.id} closes a loop
							</span>
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</Dialog>
