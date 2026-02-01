<script lang="ts">
	/**
	 * Pipe/connection line symbol.
	 * Renders a path between two points with optional flow direction.
	 */

	interface Props {
		/** Path points. */
		points: Array<{ x: number; y: number }>;
		/** Whether the pipe is selected. */
		selected?: boolean;
		/** Whether the pipe is hovered. */
		hovered?: boolean;
		/** Flow rate for display (optional). */
		flowRate?: number;
		/** Show flow direction arrow. */
		showFlowArrow?: boolean;
		/** Click handler. */
		onclick?: () => void;
		/** Mouse enter handler. */
		onmouseenter?: () => void;
		/** Mouse leave handler. */
		onmouseleave?: () => void;
	}

	let {
		points,
		selected = false,
		hovered = false,
		flowRate,
		showFlowArrow = false,
		onclick,
		onmouseenter,
		onmouseleave
	}: Props = $props();

	// Generate SVG path string
	let pathD = $derived.by(() => {
		if (points.length < 2) return '';

		let d = `M ${points[0].x} ${points[0].y}`;
		for (let i = 1; i < points.length; i++) {
			d += ` L ${points[i].x} ${points[i].y}`;
		}
		return d;
	});

	// Calculate midpoint for flow arrow
	let midpoint = $derived.by(() => {
		if (points.length < 2) return { x: 0, y: 0, angle: 0 };

		// Find midpoint along path
		const totalIdx = Math.floor((points.length - 1) / 2);
		const p1 = points[totalIdx];
		const p2 = points[totalIdx + 1] || p1;

		const x = (p1.x + p2.x) / 2;
		const y = (p1.y + p2.y) / 2;
		const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * (180 / Math.PI);

		return { x, y, angle };
	});
</script>

<g
	class="pipe-connection"
	class:selected
	class:hovered
	role="button"
	tabindex="0"
	{onclick}
	{onmouseenter}
	{onmouseleave}
	onkeydown={(e) => {
		if (e.key === 'Enter' || e.key === ' ') {
			onclick?.();
		}
	}}
>
	<!-- Pipe highlight (wider, for hover/selection) -->
	{#if selected || hovered}
		<path
			d={pathD}
			class="fill-none stroke-8 {selected ? 'stroke-[var(--color-accent)]/20' : 'stroke-[var(--color-text-muted)]/10'}"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	{/if}

	<!-- Pipe line -->
	<path
		d={pathD}
		class="fill-none stroke-2 stroke-[var(--color-text)]"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>

	<!-- Flow direction arrow -->
	{#if showFlowArrow && points.length >= 2}
		<g transform="translate({midpoint.x}, {midpoint.y}) rotate({midpoint.angle})">
			<polygon
				points="-6,-4 6,0 -6,4"
				class="fill-[var(--color-accent)]"
			/>
		</g>
	{/if}

	<!-- Flow rate label (if provided) -->
	{#if flowRate !== undefined && (selected || hovered)}
		<text
			x={midpoint.x}
			y={midpoint.y - 10}
			text-anchor="middle"
			class="fill-[var(--color-text)] text-xs font-medium"
		>
			{flowRate.toFixed(1)} GPM
		</text>
	{/if}
</g>
