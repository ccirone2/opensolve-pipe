<script lang="ts">
	/**
	 * Generic symbol - placeholder for component types without specific symbols.
	 * Displays as a rounded rectangle with type label.
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
		/** Component type abbreviation to display. */
		typeLabel?: string;
		onclick?: () => void;
		onmouseenter?: () => void;
		onmouseleave?: () => void;
	}

	let {
		x = 0,
		y = 0,
		width = 50,
		height = 30,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		typeLabel = '?',
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();
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
	<!-- Generic box -->
	<rect
		x="0"
		y="0"
		{width}
		{height}
		rx="4"
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Type label in center -->
	<text
		x={width / 2}
		y={height / 2 + 4}
		text-anchor="middle"
		class="fill-[var(--color-text)] text-xs font-bold"
	>
		{typeLabel}
	</text>

	<!-- Connection points (left and right) -->
	<circle
		cx="0"
		cy={height / 2}
		r="3"
		class="fill-[var(--color-text)]"
	/>
	<circle
		cx={width}
		cy={height / 2}
		r="3"
		class="fill-[var(--color-text)]"
	/>
</SymbolBase>
