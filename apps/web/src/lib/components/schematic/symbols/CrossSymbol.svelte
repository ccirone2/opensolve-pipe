<script lang="ts">
	/**
	 * Cross symbol - four-way junction per P&ID standards.
	 * Four-way fitting with perpendicular branches.
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
		height = 50,
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
	let pipeHalfWidth = $derived(5);
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
	<!-- Horizontal pipe (left to right) -->
	<rect
		x="0"
		y={cy - pipeHalfWidth}
		{width}
		height={pipeHalfWidth * 2}
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Vertical pipe (top to bottom) -->
	<rect
		x={cx - pipeHalfWidth}
		y="0"
		width={pipeHalfWidth * 2}
		{height}
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Center intersection (hide internal lines) -->
	<rect
		x={cx - pipeHalfWidth + 1}
		y={cy - pipeHalfWidth + 1}
		width={pipeHalfWidth * 2 - 2}
		height={pipeHalfWidth * 2 - 2}
		class="fill-[var(--color-surface-elevated)]"
	/>

	<!-- Connection points (4 corners) -->
	<circle cx="0" cy={cy} r="3" class="fill-[var(--color-text)]" />
	<circle cx={width} cy={cy} r="3" class="fill-[var(--color-text)]" />
	<circle cx={cx} cy="0" r="3" class="fill-[var(--color-text)]" />
	<circle cx={cx} cy={height} r="3" class="fill-[var(--color-text)]" />
</SymbolBase>
