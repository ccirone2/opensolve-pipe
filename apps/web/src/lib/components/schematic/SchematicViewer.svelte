<script lang="ts">
	import { components } from '$lib/stores';
	import SchematicCanvas from './SchematicCanvas.svelte';

	interface Props {
		/** Called when a component is clicked. */
		onComponentClick?: (componentId: string) => void;
		/** Custom content to render (for now, placeholder). */
		children?: import('svelte').Snippet;
	}

	// eslint-disable-next-line @typescript-eslint/no-unused-vars -- Will be used when component interaction is fully wired
	let { onComponentClick, children }: Props = $props();

	let canvas: SchematicCanvas | undefined = $state();
	let zoomLevel = $state(1);
	let containerElement: HTMLDivElement | undefined = $state();

	// Format zoom level for display
	let zoomPercent = $derived(Math.round(zoomLevel * 100));

	/**
	 * Fit the schematic to the viewport.
	 */
	function handleFitToView(): void {
		// For now, use a default content area since we don't have actual components yet
		// This will be updated when we add component symbols
		const defaultBounds = { x: 0, y: 0, width: 800, height: 400 };
		canvas?.fitToView(defaultBounds);
	}

	/**
	 * Reset zoom to 100%.
	 */
	function handleResetZoom(): void {
		canvas?.resetZoom();
	}

	/**
	 * Zoom in.
	 */
	function handleZoomIn(): void {
		canvas?.zoomIn();
	}

	/**
	 * Zoom out.
	 */
	function handleZoomOut(): void {
		canvas?.zoomOut();
	}

	// Handle resize observer to auto-fit on container size change
	$effect(() => {
		if (!containerElement) return;

		const resizeObserver = new ResizeObserver(() => {
			// Optionally auto-fit on resize
			// handleFitToView();
		});

		resizeObserver.observe(containerElement);

		return () => {
			resizeObserver.disconnect();
		};
	});
</script>

<div
	bind:this={containerElement}
	class="relative h-full w-full overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]"
>
	<!-- Canvas -->
	<SchematicCanvas
		bind:this={canvas}
		bind:zoomLevel
		minZoom={0.1}
		maxZoom={4}
	>
		{#if children}
			{@render children()}
		{:else}
			<!-- Default placeholder content -->
			<g class="schematic-content">
				{#if $components.length === 0}
					<!-- Empty state placeholder -->
					<text
						x="400"
						y="200"
						text-anchor="middle"
						class="fill-[var(--color-text-muted)] text-sm"
					>
						Add components to see the schematic
					</text>
				{:else}
					<!-- Placeholder: show component count -->
					<text
						x="400"
						y="180"
						text-anchor="middle"
						class="fill-[var(--color-text)] text-lg font-medium"
					>
						Schematic View
					</text>
					<text
						x="400"
						y="210"
						text-anchor="middle"
						class="fill-[var(--color-text-muted)] text-sm"
					>
						{$components.length} components
					</text>
					<text
						x="400"
						y="240"
						text-anchor="middle"
						class="fill-[var(--color-text-subtle)] text-xs"
					>
						Component symbols coming soon
					</text>
				{/if}
			</g>
		{/if}
	</SchematicCanvas>

	<!-- Zoom Controls -->
	<div class="absolute bottom-4 right-4 flex items-center gap-2">
		<!-- Zoom level indicator -->
		<span class="rounded bg-[var(--color-surface-elevated)] px-2 py-1 text-xs font-medium text-[var(--color-text-muted)]">
			{zoomPercent}%
		</span>

		<!-- Zoom buttons -->
		<div class="flex rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] shadow-sm">
			<button
				type="button"
				onclick={handleZoomOut}
				class="px-3 py-2 text-[var(--color-text)] hover:bg-[var(--color-surface)] transition-colors"
				title="Zoom out"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4" />
				</svg>
			</button>
			<button
				type="button"
				onclick={handleResetZoom}
				class="border-x border-[var(--color-border)] px-3 py-2 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface)] transition-colors"
				title="Reset to 100%"
			>
				100%
			</button>
			<button
				type="button"
				onclick={handleZoomIn}
				class="px-3 py-2 text-[var(--color-text)] hover:bg-[var(--color-surface)] transition-colors"
				title="Zoom in"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
				</svg>
			</button>
		</div>
	</div>

	<!-- Fit to View button -->
	<div class="absolute left-4 bottom-4">
		<button
			type="button"
			onclick={handleFitToView}
			class="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2 text-sm font-medium text-[var(--color-text)] shadow-sm hover:bg-[var(--color-surface)] transition-colors"
			title="Fit schematic to view"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
				/>
			</svg>
			Fit
		</button>
	</div>

	<!-- Keyboard shortcuts hint (optional, can be removed) -->
	<div class="absolute left-4 top-4 hidden lg:block">
		<div class="rounded bg-[var(--color-surface-elevated)]/80 px-2 py-1 text-xs text-[var(--color-text-muted)]">
			Scroll to zoom • Drag to pan
		</div>
	</div>
</div>
