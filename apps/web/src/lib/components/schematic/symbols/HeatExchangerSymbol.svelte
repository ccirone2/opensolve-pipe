<script lang="ts">
	/**
	 * Heat Exchanger symbol - shell-and-tube pattern per P&ID standards.
	 * Two concentric circles representing shell and tube sides.
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
		height = 40,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	// Center point
	let cx = $derived(width / 2);
	let cy = $derived(height / 2);

	// Outer circle (shell)
	let outerRx = $derived(width / 2 - 4);
	let outerRy = $derived(height / 2 - 2);

	// Inner pattern - tube bundle
	let tubeSpacing = $derived(height / 5);
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
	<!-- Shell (outer ellipse) -->
	<ellipse
		{cx}
		{cy}
		rx={outerRx}
		ry={outerRy}
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Tube bundle (horizontal lines inside) -->
	{#each [-1, 0, 1] as offset}
		<line
			x1={cx - outerRx * 0.7}
			y1={cy + offset * tubeSpacing}
			x2={cx + outerRx * 0.7}
			y2={cy + offset * tubeSpacing}
			class="stroke-[var(--color-text)] stroke-1"
		/>
	{/each}

	<!-- Inlet connection (left) -->
	<line
		x1="0"
		y1={cy}
		x2={cx - outerRx}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Outlet connection (right) -->
	<line
		x1={cx + outerRx}
		y1={cy}
		x2={width}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Connection points -->
	<circle cx="0" cy={cy} r="3" class="fill-[var(--color-text)]" />
	<circle cx={width} cy={cy} r="3" class="fill-[var(--color-text)]" />
</SymbolBase>
