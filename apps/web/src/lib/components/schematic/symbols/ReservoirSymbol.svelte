<script lang="ts">
	/**
	 * Reservoir symbol - tank with water level indicator.
	 * Per P&ID standards (ISA-5.1).
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
		width = 60,
		height = 50,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	// Water level (percentage of height)
	const waterLevel = 0.6;
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
	<!-- Tank outline -->
	<rect
		x="0"
		y="0"
		{width}
		{height}
		rx="2"
		class="fill-[var(--color-surface)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Water fill -->
	<rect
		x="2"
		y={height * (1 - waterLevel)}
		width={width - 4}
		height={height * waterLevel - 2}
		class="fill-blue-400/40"
	/>

	<!-- Water level line (wavy) -->
	<path
		d="M 2 {height * (1 - waterLevel)}
		   Q {width * 0.25} {height * (1 - waterLevel) - 3}, {width * 0.5} {height * (1 - waterLevel)}
		   Q {width * 0.75} {height * (1 - waterLevel) + 3}, {width - 2} {height * (1 - waterLevel)}"
		class="fill-none stroke-blue-500 stroke-1"
	/>

	<!-- Ground symbol below (reservoir is typically at ground level) -->
	<line
		x1="0"
		y1={height + 2}
		x2={width}
		y2={height + 2}
		class="stroke-[var(--color-text)] stroke-2"
	/>
	<line
		x1="5"
		y1={height + 6}
		x2={width - 5}
		y2={height + 6}
		class="stroke-[var(--color-text)] stroke-1"
	/>
	<line
		x1="12"
		y1={height + 10}
		x2={width - 12}
		y2={height + 10}
		class="stroke-[var(--color-text)] stroke-1"
	/>
</SymbolBase>
