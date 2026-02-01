<script lang="ts">
	/**
	 * Orifice symbol - restriction plate per P&ID standards.
	 * Two vertical lines with a gap representing the orifice opening.
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
		width = 40,
		height = 30,
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
	let gapSize = $derived(height * 0.3);
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
	<!-- Inlet pipe -->
	<line
		x1="0"
		y1={cy}
		x2={midX - 4}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Outlet pipe -->
	<line
		x1={midX + 4}
		y1={cy}
		x2={width}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Left restriction plate -->
	<line
		x1={midX - 2}
		y1="0"
		x2={midX - 2}
		y2={cy - gapSize / 2}
		class="stroke-[var(--color-text)] stroke-3"
	/>
	<line
		x1={midX - 2}
		y1={cy + gapSize / 2}
		x2={midX - 2}
		y2={height}
		class="stroke-[var(--color-text)] stroke-3"
	/>

	<!-- Right restriction plate -->
	<line
		x1={midX + 2}
		y1="0"
		x2={midX + 2}
		y2={cy - gapSize / 2}
		class="stroke-[var(--color-text)] stroke-3"
	/>
	<line
		x1={midX + 2}
		y1={cy + gapSize / 2}
		x2={midX + 2}
		y2={height}
		class="stroke-[var(--color-text)] stroke-3"
	/>

	<!-- Connection points -->
	<circle cx="0" cy={cy} r="3" class="fill-[var(--color-text)]" />
	<circle cx={width} cy={cy} r="3" class="fill-[var(--color-text)]" />
</SymbolBase>
