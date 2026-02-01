<script lang="ts">
	/**
	 * Junction symbol - simple dot or circle for connection point.
	 */
	import SymbolBase from './SymbolBase.svelte';

	interface Props {
		x?: number;
		y?: number;
		width?: number;
		height?: number;
		selected?: boolean;
		hovered?: boolean;
		label?: string;
		showLabel?: boolean;
		onclick?: () => void;
		onmouseenter?: () => void;
		onmouseleave?: () => void;
	}

	let {
		x = 0,
		y = 0,
		width = 20,
		height = 20,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	let cx = $derived(width / 2);
	let cy = $derived(height / 2);
	let r = $derived(Math.min(width, height) / 2 - 2);
</script>

<SymbolBase
	{x}
	{y}
	{width}
	{height}
	{selected}
	{hovered}
	{label}
	{showLabel}
	{onclick}
	{onmouseenter}
	{onmouseleave}
>
	<!-- Junction dot -->
	<circle
		{cx}
		{cy}
		{r}
		class="fill-[var(--color-text)] stroke-[var(--color-text)] stroke-1"
	/>
</SymbolBase>
