<script lang="ts">
	/**
	 * Plug/Cap symbol - dead end per P&ID standards.
	 * Filled cap at the end of a pipe representing a closed boundary.
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
		width = 30,
		height = 24,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	let cy = $derived(height / 2);
	let capWidth = $derived(10);
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
	<!-- Pipe stub -->
	<line
		x1="0"
		y1={cy}
		x2={width - capWidth}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Cap (filled rectangle) -->
	<rect
		x={width - capWidth}
		y={cy - 8}
		width={capWidth}
		height="16"
		class="fill-[var(--color-text)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Highlight line on cap -->
	<line
		x1={width - capWidth + 3}
		y1={cy - 5}
		x2={width - capWidth + 3}
		y2={cy + 5}
		class="stroke-[var(--color-surface)] stroke-1"
	/>

	<!-- Connection point (inlet only - single port) -->
	<circle cx="0" cy={cy} r="3" class="fill-[var(--color-text)]" />
</SymbolBase>
