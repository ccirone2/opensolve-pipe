<script lang="ts">
	/**
	 * Tank symbol - cylindrical tank with level indicator.
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
		/** Water level as fraction (0-1). Default: 0.5 */
		level?: number;
		onclick?: () => void;
		onmouseenter?: () => void;
		onmouseleave?: () => void;
	}

	let {
		x = 0,
		y = 0,
		width = 50,
		height = 45,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		level = 0.5,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	// Ellipse radius for top/bottom caps
	let rx = $derived(width / 2);
	const ry = 6;
	let bodyHeight = $derived(height - ry * 2);
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
	<!-- Tank body (vertical cylinder) -->
	<!-- Left side -->
	<line
		x1="0"
		y1={ry}
		x2="0"
		y2={height - ry}
		class="stroke-[var(--color-text)] stroke-2"
	/>
	<!-- Right side -->
	<line
		x1={width}
		y1={ry}
		x2={width}
		y2={height - ry}
		class="stroke-[var(--color-text)] stroke-2"
	/>
	<!-- Top ellipse -->
	<ellipse
		cx={rx}
		cy={ry}
		{rx}
		{ry}
		class="fill-[var(--color-surface)] stroke-[var(--color-text)] stroke-2"
	/>
	<!-- Bottom ellipse (full) -->
	<ellipse
		cx={rx}
		cy={height - ry}
		{rx}
		{ry}
		class="fill-[var(--color-surface)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Water fill (clipped to body) -->
	{#if level > 0}
		<clipPath id="tank-body-{x}-{y}">
			<rect x="1" y={ry} width={width - 2} height={bodyHeight} />
		</clipPath>
		<rect
			x="1"
			y={ry + bodyHeight * (1 - level)}
			width={width - 2}
			height={bodyHeight * level}
			class="fill-blue-400/40"
			clip-path="url(#tank-body-{x}-{y})"
		/>
	{/if}

	<!-- Level indicator line -->
	<line
		x1="2"
		y1={ry + bodyHeight * (1 - level)}
		x2={width - 2}
		y2={ry + bodyHeight * (1 - level)}
		class="stroke-blue-500 stroke-1"
		stroke-dasharray="4 2"
	/>
</SymbolBase>
