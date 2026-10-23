<!--
	One results cell: a value, lines, or labelled values (label left, value right). A value with a
	note (e.g. "≈ 0" for round-off) shows the note on hover.
-->
<script lang="ts">
	import type { Cell, CellPart, Value } from '$lib/utils/results';

	let { cell }: { cell: Cell } = $props();

	const parts = $derived(
		Array.isArray(cell) && cell.every((p) => typeof p !== 'string') ? (cell as CellPart[]) : null
	);
	const lines = $derived(Array.isArray(cell) && !parts ? (cell as string[]) : null);
</script>

{#snippet value(v: Value)}
	{#if typeof v === 'string'}{v}{:else}<span title={v.title} class="cursor-help">{v.text}</span
		>{/if}
{/snippet}

{#if parts}
	<span class="inline-grid grid-cols-[auto_auto] gap-x-2 text-left">
		{#each parts as part, i (i)}
			<span class="text-slate-600">{part.label}</span>
			<span class="text-right tabular-nums">{@render value(part.value)}</span>
		{/each}
	</span>
{:else if lines}
	{#each lines as line, i (i)}<span class="block">{line}</span>{/each}
{:else if !Array.isArray(cell)}
	{@render value(cell)}
{/if}
