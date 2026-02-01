<script lang="ts">
	/**
	 * Wye symbol - Y-junction per P&ID standards.
	 * Three-way fitting with angled branch (typically 45 degrees).
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
		/** Branch orientation: 'up' or 'down'. */
		branchDirection?: 'up' | 'down';
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
		branchDirection = 'down',
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	let cx = $derived(width / 2);
	let runY = $derived(branchDirection === 'down' ? height * 0.3 : height * 0.7);
	let branchEndY = $derived(branchDirection === 'down' ? height : 0);
	let branchEndX = $derived(branchDirection === 'down' ? width * 0.75 : width * 0.75);
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
	<!-- Main run (horizontal pipe) -->
	<rect
		x="0"
		y={runY - pipeHalfWidth}
		{width}
		height={pipeHalfWidth * 2}
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Angled branch (Y shape) -->
	<polygon
		points="{cx - pipeHalfWidth},{runY}
		        {cx + pipeHalfWidth},{runY}
		        {branchEndX + pipeHalfWidth},{branchEndY}
		        {branchEndX - pipeHalfWidth},{branchEndY}"
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Hide internal line at junction -->
	<line
		x1={cx - pipeHalfWidth + 1}
		y1={runY}
		x2={cx + pipeHalfWidth - 1}
		y2={runY}
		class="stroke-[var(--color-surface-elevated)] stroke-3"
	/>

	<!-- Connection points -->
	<circle cx="0" cy={runY} r="3" class="fill-[var(--color-text)]" />
	<circle cx={width} cy={runY} r="3" class="fill-[var(--color-text)]" />
	<circle cx={branchEndX} cy={branchEndY} r="3" class="fill-[var(--color-text)]" />
</SymbolBase>
