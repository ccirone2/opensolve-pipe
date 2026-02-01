<script lang="ts">
	/**
	 * Valve symbols - various valve types per P&ID standards.
	 * Gate, ball, check, PRV, PSV, FCV.
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
		/** Valve type. */
		valveType?: 'gate' | 'ball' | 'check' | 'prv' | 'psv' | 'fcv' | 'butterfly';
		/** Valve status. */
		status?: 'active' | 'isolated' | 'failed_open' | 'failed_closed' | 'locked_open';
		onclick?: () => void;
		onmouseenter?: () => void;
		onmouseleave?: () => void;
	}

	let {
		x = 0,
		y = 0,
		width = 40,
		height = 30,
		selected = false,
		hovered = false,
		label = '',
		showLabel = true,
		valveType = 'gate',
		status = 'active',
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	let cy = $derived(height / 2);

	// Status-based fill
	let fillColor = $derived.by(() => {
		switch (status) {
			case 'active':
				return 'var(--color-surface)';
			case 'isolated':
			case 'failed_closed':
				return 'var(--color-error)';
			case 'failed_open':
				return 'var(--color-warning)';
			case 'locked_open':
				return 'var(--color-accent)';
			default:
				return 'var(--color-surface)';
		}
	});

	let fillOpacity = $derived(status === 'active' ? 0.1 : 0.3);
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
	{#if valveType === 'gate' || valveType === 'ball' || valveType === 'butterfly'}
		<!-- Gate/Ball/Butterfly valve: two triangles meeting at center -->
		<polygon
			points="0,0 {width / 2},{cy} 0,{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<polygon
			points="{width},0 {width / 2},{cy} {width},{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<!-- Stem (actuator) -->
		<line
			x1={width / 2}
			y1="0"
			x2={width / 2}
			y2="-8"
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<rect
			x={width / 2 - 4}
			y="-14"
			width="8"
			height="6"
			class="fill-[var(--color-surface)] stroke-[var(--color-text)] stroke-1"
		/>
	{:else if valveType === 'check'}
		<!-- Check valve: triangle with barrier -->
		<polygon
			points="0,0 {width * 0.7},{cy} 0,{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<line
			x1={width * 0.7}
			y1="2"
			x2={width * 0.7}
			y2={height - 2}
			class="stroke-[var(--color-text)] stroke-3"
		/>
		<!-- Flow direction indicator -->
		<line
			x1={width * 0.8}
			y1={cy}
			x2={width}
			y2={cy}
			class="stroke-[var(--color-text)] stroke-2"
		/>
	{:else if valveType === 'prv'}
		<!-- PRV (Pressure Reducing Valve): triangle with arrow pointing downstream -->
		<polygon
			points="0,0 {width / 2},{cy} 0,{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<polygon
			points="{width},0 {width / 2},{cy} {width},{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<!-- Arrow pointing right (downstream pressure control) -->
		<line
			x1={width / 2}
			y1="-8"
			x2={width / 2}
			y2="-2"
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<polygon
			points="{width / 2 - 4},-8 {width / 2},-14 {width / 2 + 4},-8"
			class="fill-[var(--color-text)]"
		/>
		<text
			x={width / 2}
			y="-16"
			text-anchor="middle"
			class="fill-[var(--color-text-muted)] text-[8px]"
		>
			P↓
		</text>
	{:else if valveType === 'psv'}
		<!-- PSV (Pressure Relief/Safety Valve): angled body -->
		<polygon
			points="0,{cy} {width / 2},0 {width},{cy} {width / 2},{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<!-- Relief arrow pointing up -->
		<line
			x1={width / 2}
			y1="0"
			x2={width / 2}
			y2="-10"
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<polygon
			points="{width / 2 - 4},-10 {width / 2},-16 {width / 2 + 4},-10"
			class="fill-[var(--color-text)]"
		/>
	{:else if valveType === 'fcv'}
		<!-- FCV (Flow Control Valve): triangles with flow indicator -->
		<polygon
			points="0,0 {width / 2},{cy} 0,{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<polygon
			points="{width},0 {width / 2},{cy} {width},{height}"
			fill={fillColor}
			fill-opacity={fillOpacity}
			class="stroke-[var(--color-text)] stroke-2"
		/>
		<!-- Flow indicator (F) -->
		<text
			x={width / 2}
			y="-6"
			text-anchor="middle"
			class="fill-[var(--color-text)] text-[10px] font-bold"
		>
			F
		</text>
	{/if}

	<!-- Connection lines -->
	<line
		x1="0"
		y1={cy}
		x2="-5"
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>
	<line
		x1={width}
		y1={cy}
		x2={width + 5}
		y2={cy}
		class="stroke-[var(--color-text)] stroke-2"
	/>
</SymbolBase>
