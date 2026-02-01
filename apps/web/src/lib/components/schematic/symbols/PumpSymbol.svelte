<script lang="ts">
	/**
	 * Pump symbol - circle with directional arrow.
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
		/** Pump status (affects color). */
		status?: 'running' | 'off_check' | 'off_no_check' | 'locked_out';
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
		status = 'running',
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	// Circle center and radius
	let cx = $derived(width / 2);
	let cy = $derived(height / 2);
	let r = $derived(Math.min(width, height) / 2 - 2);

	// Status-based styling
	let fillColor = $derived.by(() => {
		switch (status) {
			case 'running':
				return 'var(--color-success)';
			case 'off_check':
			case 'off_no_check':
				return 'var(--color-surface-elevated)';
			case 'locked_out':
				return 'var(--color-error)';
			default:
				return 'var(--color-surface)';
		}
	});
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
	<!-- Pump body (circle) -->
	<circle
		{cx}
		{cy}
		{r}
		fill={fillColor}
		class="stroke-[var(--color-text)] stroke-2"
		fill-opacity="0.3"
	/>

	<!-- Flow direction arrow (pointing right/discharge direction) -->
	<polygon
		points="{cx - r * 0.3},{cy - r * 0.4}
		        {cx + r * 0.5},{cy}
		        {cx - r * 0.3},{cy + r * 0.4}"
		class="fill-[var(--color-text)]"
	/>

	<!-- Inlet/suction line (left) -->
	<line
		x1="0"
		y1={cy}
		x2={cx - r}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Outlet/discharge line (right) -->
	<line
		x1={cx + r}
		y1={cy}
		x2={width}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>
</SymbolBase>
