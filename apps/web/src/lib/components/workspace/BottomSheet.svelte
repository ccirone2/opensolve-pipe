<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		sheetState?: 'collapsed' | 'half' | 'full';
		onStateChange?: (state: 'collapsed' | 'half' | 'full') => void;
		children: Snippet;
	}

	let { sheetState = 'collapsed', onStateChange, children }: Props = $props();

	let sheetEl: HTMLDivElement | undefined = $state();
	let startY = $state(0);
	let currentY = $state(0);
	let isDragging = $state(false);

	// Heights for each state
	const COLLAPSED_HEIGHT = 48; // Just the handle bar
	const HALF_HEIGHT_VH = 50;
	const FULL_HEIGHT_VH = 90;

	let sheetHeight = $derived(
		sheetState === 'collapsed' ? `${COLLAPSED_HEIGHT}px` :
		sheetState === 'half' ? `${HALF_HEIGHT_VH}vh` : `${FULL_HEIGHT_VH}vh`
	);

	let showBackdrop = $derived(sheetState === 'full');

	function handleTouchStart(e: TouchEvent) {
		startY = e.touches[0].clientY;
		currentY = startY;
		isDragging = true;
	}

	function handleTouchMove(e: TouchEvent) {
		if (!isDragging) return;
		currentY = e.touches[0].clientY;
	}

	function handleTouchEnd() {
		if (!isDragging) return;
		isDragging = false;

		const deltaY = startY - currentY;
		const threshold = 50;

		if (deltaY > threshold) {
			// Swiped up
			if (sheetState === 'collapsed') onStateChange?.('half');
			else if (sheetState === 'half') onStateChange?.('full');
		} else if (deltaY < -threshold) {
			// Swiped down
			if (sheetState === 'full') onStateChange?.('half');
			else if (sheetState === 'half') onStateChange?.('collapsed');
		}
	}

	function handleBackdropClick() {
		onStateChange?.('half');
	}
</script>

<!-- Backdrop for full-screen state -->
{#if showBackdrop}
	<button
		type="button"
		class="bottom-sheet-backdrop"
		onclick={handleBackdropClick}
		aria-label="Close full-screen panel"
	></button>
{/if}

<!-- Sheet -->
<div
	bind:this={sheetEl}
	class="bottom-sheet"
	class:bottom-sheet-dragging={isDragging}
	style="height: {sheetHeight}"
>
	<!-- Drag handle -->
	<div
		class="bottom-sheet-handle"
		ontouchstart={handleTouchStart}
		ontouchmove={handleTouchMove}
		ontouchend={handleTouchEnd}
	>
		<div class="bottom-sheet-handle-bar"></div>
	</div>

	<!-- Content -->
	<div class="bottom-sheet-content">
		{@render children()}
	</div>
</div>

<style>
	.bottom-sheet-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.4);
		z-index: 40;
		border: none;
		cursor: pointer;
	}

	.bottom-sheet {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		z-index: 50;
		background: var(--color-surface);
		border-top: 1px solid var(--color-border);
		border-radius: 12px 12px 0 0;
		box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.15);
		transition: height 0.25s cubic-bezier(0.33, 1, 0.68, 1);
		display: flex;
		flex-direction: column;
		touch-action: none;
	}

	.bottom-sheet-dragging {
		transition: none;
	}

	.bottom-sheet-handle {
		display: flex;
		justify-content: center;
		padding: 10px 0 6px;
		cursor: grab;
		flex-shrink: 0;
	}

	.bottom-sheet-handle-bar {
		width: 36px;
		height: 4px;
		border-radius: 2px;
		background: var(--color-border);
	}

	.bottom-sheet-content {
		flex: 1;
		overflow-y: auto;
		overflow-x: hidden;
		min-height: 0;
	}

	@media (prefers-reduced-motion: reduce) {
		.bottom-sheet {
			transition: none;
		}
	}
</style>
