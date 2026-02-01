<script lang="ts">
	/**
	 * Strainer symbol - Y-strainer pattern per P&ID standards.
	 * Y-shape with mesh pattern representing the straining element.
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
		width = 50,
		height = 40,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	let cy = $derived(height / 2);
	let midX = $derived(width / 2);
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
	<!-- Main pipe body (horizontal) -->
	<rect
		x="0"
		y={cy - 6}
		width={width}
		height="12"
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Y-strainer basket (angled downward) -->
	<polygon
		points="{midX - 8},{cy + 6}
		        {midX + 8},{cy + 6}
		        {midX + 4},{height}
		        {midX - 4},{height}"
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Mesh pattern in basket -->
	<line
		x1={midX - 4}
		y1={cy + 10}
		x2={midX + 4}
		y2={cy + 10}
		class="stroke-[var(--color-text)] stroke-1"
	/>
	<line
		x1={midX - 3}
		y1={cy + 16}
		x2={midX + 3}
		y2={cy + 16}
		class="stroke-[var(--color-text)] stroke-1"
	/>
	<line
		x1={midX}
		y1={cy + 6}
		x2={midX}
		y2={height - 2}
		class="stroke-[var(--color-text)] stroke-1"
	/>

	<!-- Connection points -->
	<circle cx="0" cy={cy} r="3" class="fill-[var(--color-text)]" />
	<circle cx={width} cy={cy} r="3" class="fill-[var(--color-text)]" />
</SymbolBase>
