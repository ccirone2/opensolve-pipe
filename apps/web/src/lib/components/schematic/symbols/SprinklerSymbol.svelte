<script lang="ts">
	/**
	 * Sprinkler symbol - spray nozzle pattern per P&ID standards.
	 * Circle with downward spray lines representing water distribution.
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
		height = 40,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	let cx = $derived(width / 2);
	let nozzleY = $derived(height * 0.35);
	let nozzleR = $derived(6);
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
	<!-- Inlet pipe (from left) -->
	<line
		x1="0"
		y1={nozzleY}
		x2={cx - nozzleR}
		y2={nozzleY}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Nozzle body -->
	<circle
		{cx}
		cy={nozzleY}
		r={nozzleR}
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Deflector plate -->
	<line
		x1={cx - 8}
		y1={nozzleY + nozzleR + 3}
		x2={cx + 8}
		y2={nozzleY + nozzleR + 3}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Spray pattern (fanning lines) -->
	<line
		x1={cx - 8}
		y1={nozzleY + nozzleR + 3}
		x2={cx - 14}
		y2={height}
		class="stroke-[var(--color-accent)] stroke-1"
		stroke-dasharray="2 2"
	/>
	<line
		x1={cx - 4}
		y1={nozzleY + nozzleR + 3}
		x2={cx - 6}
		y2={height}
		class="stroke-[var(--color-accent)] stroke-1"
		stroke-dasharray="2 2"
	/>
	<line
		x1={cx}
		y1={nozzleY + nozzleR + 3}
		x2={cx}
		y2={height}
		class="stroke-[var(--color-accent)] stroke-1"
		stroke-dasharray="2 2"
	/>
	<line
		x1={cx + 4}
		y1={nozzleY + nozzleR + 3}
		x2={cx + 6}
		y2={height}
		class="stroke-[var(--color-accent)] stroke-1"
		stroke-dasharray="2 2"
	/>
	<line
		x1={cx + 8}
		y1={nozzleY + nozzleR + 3}
		x2={cx + 14}
		y2={height}
		class="stroke-[var(--color-accent)] stroke-1"
		stroke-dasharray="2 2"
	/>

	<!-- Connection point (inlet only - single port) -->
	<circle cx="0" cy={nozzleY} r="3" class="fill-[var(--color-text)]" />
</SymbolBase>
