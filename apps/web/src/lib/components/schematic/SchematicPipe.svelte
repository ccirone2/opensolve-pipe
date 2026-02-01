<script lang="ts">
	/**
	 * Renders a piping connection between two components.
	 */
	import type { PipingResult } from '$lib/models';
	import { PipeSymbol } from './symbols';

	interface Props {
		/** Connection ID. */
		id: string;
		/** Path points. */
		points: Array<{ x: number; y: number }>;
		/** Whether this pipe is selected. */
		selected?: boolean;
		/** Piping result (for tooltip and flow arrow). */
		result?: PipingResult;
		/** Click handler. */
		onclick?: (connectionId: string) => void;
		/** Selection change handler. */
		onselect?: (connectionId: string) => void;
	}

	let {
		id,
		points,
		selected = false,
		result,
		onclick,
		onselect
	}: Props = $props();

	let hovered = $state(false);
	let showTooltip = $state(false);

	function handleClick(): void {
		onclick?.(id);
		onselect?.(id);
	}

	function handleMouseEnter(): void {
		hovered = true;
		showTooltip = true;
	}

	function handleMouseLeave(): void {
		hovered = false;
		showTooltip = false;
	}

	// Calculate midpoint for tooltip positioning
	let midpoint = $derived.by(() => {
		if (points.length < 2) return { x: 0, y: 0 };
		const midIdx = Math.floor((points.length - 1) / 2);
		const p1 = points[midIdx];
		const p2 = points[midIdx + 1] || p1;
		return {
			x: (p1.x + p2.x) / 2,
			y: (p1.y + p2.y) / 2
		};
	});

	// Format result for tooltip
	let tooltipContent = $derived.by(() => {
		if (!result) return null;
		const lines: string[] = [];
		if (result.flow !== undefined) {
			lines.push(`Flow: ${result.flow.toFixed(1)} GPM`);
		}
		if (result.velocity !== undefined) {
			lines.push(`Velocity: ${result.velocity.toFixed(2)} ft/s`);
		}
		if (result.head_loss !== undefined) {
			lines.push(`Head Loss: ${result.head_loss.toFixed(2)} ft`);
		}
		return lines.length > 0 ? lines : null;
	});
</script>

<g class="schematic-pipe" data-connection-id={id}>
	<PipeSymbol
		{points}
		{selected}
		{hovered}
		flowRate={result?.flow}
		showFlowArrow={!!result?.flow && result.flow > 0}
		onclick={handleClick}
		onmouseenter={handleMouseEnter}
		onmouseleave={handleMouseLeave}
	/>

	<!-- Tooltip -->
	{#if showTooltip && tooltipContent}
		<g transform="translate({midpoint.x}, {midpoint.y - 30})">
			<rect
				x="-70"
				y="-10"
				width="140"
				height={20 + tooltipContent.length * 14}
				rx="4"
				class="fill-[var(--color-surface-elevated)] stroke-[var(--color-border)]"
				filter="drop-shadow(0 2px 4px rgba(0,0,0,0.1))"
			/>
			{#each tooltipContent as line, i}
				<text
					x="0"
					y={6 + i * 14}
					text-anchor="middle"
					class="fill-[var(--color-text-muted)] text-[10px]"
				>
					{line}
				</text>
			{/each}
		</g>
	{/if}
</g>
