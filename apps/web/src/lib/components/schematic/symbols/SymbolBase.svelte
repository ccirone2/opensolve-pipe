<script lang="ts">
	/**
	 * Base component for schematic symbols.
	 * Provides common styling and positioning.
	 */

	interface Props {
		/** X position of the symbol center. */
		x?: number;
		/** Y position of the symbol center. */
		y?: number;
		/** Width of the symbol. */
		width?: number;
		/** Height of the symbol. */
		height?: number;
		/** Whether the symbol is selected. */
		selected?: boolean;
		/** Whether the symbol is hovered. */
		hovered?: boolean;
		/** Display label (component name). */
		label?: string;
		/** Whether to show the label. */
		showLabel?: boolean;
		/** Click handler. */
		onclick?: () => void;
		/** Mouse enter handler. */
		onmouseenter?: () => void;
		/** Mouse leave handler. */
		onmouseleave?: () => void;
		/** Children (the actual symbol graphics). */
		children?: import('svelte').Snippet;
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
		onmouseleave,
		children
	}: Props = $props();

	// Calculate the top-left corner from center position
	let left = $derived(x - width / 2);
	let top = $derived(y - height / 2);
</script>

<g
	class="schematic-symbol"
	class:selected
	class:hovered
	transform="translate({left}, {top})"
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
	<!-- Selection/hover highlight -->
	{#if selected || hovered}
		<rect
			x="-4"
			y="-4"
			width={width + 8}
			height={height + 8}
			rx="4"
			class="fill-none stroke-2 {selected ? 'stroke-[var(--color-accent)]' : 'stroke-[var(--color-text-muted)]'}"
			stroke-dasharray={hovered && !selected ? '4 2' : 'none'}
		/>
	{/if}

	<!-- Symbol content (passed as children) -->
	{@render children?.()}

	<!-- Label -->
	{#if showLabel && label}
		<text
			x={width / 2}
			y={height + 16}
			text-anchor="middle"
			class="fill-[var(--color-text)] text-xs font-medium"
		>
			{label}
		</text>
	{/if}
</g>
