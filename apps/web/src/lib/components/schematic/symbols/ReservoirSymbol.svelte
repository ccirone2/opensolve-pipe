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
	<!-- Water fill (behind walls) -->
	{@const waterTop = height * (1 - waterLevel)}
	<rect
		x="3"
		y={waterTop}
		width={width - 6}
		height={height - waterTop - 3}
		class="fill-blue-300/50"
	/>

	<!-- Water surface wavy line -->
	<path
		d="M 3 {waterTop}
		   Q {width * 0.25} {waterTop - 3}, {width * 0.5} {waterTop}
		   Q {width * 0.75} {waterTop + 3}, {width - 3} {waterTop}"
		class="fill-none stroke-blue-500"
		stroke-width="1.5"
	/>

	<!-- Open-top reservoir walls (left, bottom, right — no top) -->
	<path
		d="M 0 0 L 0 {height} L {width} {height} L {width} 0"
		fill="none"
		stroke="var(--color-text)"
		stroke-width="2"
		stroke-linecap="square"
		stroke-linejoin="miter"
	/>
</SymbolBase>
