<script lang="ts">
	/**
	 * Reference Node symbol - boundary condition marker per P&ID standards.
	 * Diamond shape with "P" or "PQ" indicator for ideal/non-ideal nodes.
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
		/** Whether this is an ideal (fixed P) or non-ideal (P-Q curve) reference. */
		isIdeal?: boolean;
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
		isIdeal = true,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	let cx = $derived(width / 2);
	let cy = $derived(height / 2);
	let halfW = $derived(width / 2 - 4);
	let halfH = $derived(height / 2 - 4);
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
	<!-- Diamond shape (boundary marker) -->
	<polygon
		points="{cx},{cy - halfH}
		        {cx + halfW},{cy}
		        {cx},{cy + halfH}
		        {cx - halfW},{cy}"
		class="fill-[var(--color-surface-elevated)] stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Label inside diamond -->
	<text
		x={cx}
		y={cy + 4}
		text-anchor="middle"
		class="fill-[var(--color-text)] text-[10px] font-bold"
	>
		{isIdeal ? 'P' : 'PQ'}
	</text>

	<!-- Connection line (to the left) -->
	<line
		x1="0"
		y1={cy}
		x2={cx - halfW}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>

	<!-- Connection point -->
	<circle cx="0" cy={cy} r="3" class="fill-[var(--color-text)]" />

	<!-- Ground symbol for ideal reference (fixed pressure) -->
	{#if isIdeal}
		<line
			x1={cx - 8}
			y1={cy + halfH + 4}
			x2={cx + 8}
			y2={cy + halfH + 4}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<line
			x1={cx - 5}
			y1={cy + halfH + 8}
			x2={cx + 5}
			y2={cy + halfH + 8}
			class="stroke-[var(--color-text)] stroke-1.5"
		/>
		<line
			x1={cx - 2}
			y1={cy + halfH + 12}
			x2={cx + 2}
			y2={cy + halfH + 12}
			class="stroke-[var(--color-text)] stroke-1"
		/>
	{/if}
</SymbolBase>
