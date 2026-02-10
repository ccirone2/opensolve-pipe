<script lang="ts">
	import { select } from 'd3-selection';
	import { zoom, zoomIdentity, type ZoomBehavior, type D3ZoomEvent } from 'd3-zoom';
	import 'd3-transition'; // Augments Selection with .transition()

	interface Props {
		/** Minimum zoom scale. Default: 0.33 */
		minZoom?: number;
		/** Maximum zoom scale. Default: 1.25 */
		maxZoom?: number;
		/** Current zoom level (read-only, for display). */
		zoomLevel?: number;
		/** Callback when zoom level changes. */
		onZoomChange?: (level: number) => void;
		/** Children to render inside the zoomed/panned group. */
		children?: import('svelte').Snippet;
	}

	let {
		minZoom = 0.33,
		maxZoom = 1.25,
		zoomLevel = $bindable(1),
		onZoomChange,
		children
	}: Props = $props();

	let svgElement: SVGSVGElement | undefined = $state();
	let contentGroup: SVGGElement | undefined = $state();
	let zoomBehavior: ZoomBehavior<SVGSVGElement, unknown> | null = $state(null);
	let currentTransform = $state({ x: 0, y: 0, k: 1 });

	// Initialize zoom behavior when SVG element is available
	$effect(() => {
		if (!svgElement) return;

		const svg = select(svgElement);

		// Create zoom behavior
		const newZoomBehavior = zoom<SVGSVGElement, unknown>()
			.scaleExtent([minZoom, maxZoom])
			.on('zoom', (event: D3ZoomEvent<SVGSVGElement, unknown>) => {
				const { x, y, k } = event.transform;
				currentTransform = { x, y, k };
				zoomLevel = k;
				onZoomChange?.(k);
			});

		zoomBehavior = newZoomBehavior;

		// Apply zoom behavior to SVG
		svg.call(newZoomBehavior);

		// Enable touch support for mobile pinch-to-zoom
		svg.on('touchstart.zoom', null); // Let d3-zoom handle touch events

		// Cleanup function
		return () => {
			svg.on('.zoom', null);
			zoomBehavior = null;
		};
	});

	/**
	 * Reset zoom to identity (1:1 scale, no pan).
	 */
	export function resetZoom(): void {
		if (!svgElement || !zoomBehavior) return;
		select(svgElement)
			.transition()
			.duration(300)
			.call(zoomBehavior.transform, zoomIdentity);
	}

	/**
	 * Zoom to fit content within the viewport.
	 * @param contentBounds - The bounding box of the content to fit.
	 * @param padding - Padding around the content (default: 40px).
	 */
	export function fitToView(
		contentBounds: { x: number; y: number; width: number; height: number },
		padding = 40
	): void {
		if (!svgElement || !zoomBehavior) return;

		const svgRect = svgElement.getBoundingClientRect();
		const viewWidth = svgRect.width - padding * 2;
		const viewHeight = svgRect.height - padding * 2;

		if (viewWidth <= 0 || viewHeight <= 0) return;
		if (contentBounds.width <= 0 || contentBounds.height <= 0) return;

		// Calculate scale to fit content
		const scale = Math.min(
			viewWidth / contentBounds.width,
			viewHeight / contentBounds.height,
			maxZoom
		);

		// Calculate center offset
		const centerX = (svgRect.width - contentBounds.width * scale) / 2 - contentBounds.x * scale;
		const centerY = (svgRect.height - contentBounds.height * scale) / 2 - contentBounds.y * scale;

		const transform = zoomIdentity.translate(centerX, centerY).scale(scale);

		select(svgElement)
			.transition()
			.duration(300)
			.call(zoomBehavior.transform, transform);
	}

	/**
	 * Set zoom level programmatically.
	 * @param level - The zoom level to set.
	 */
	export function setZoom(level: number): void {
		if (!svgElement || !zoomBehavior) return;
		const clampedLevel = Math.max(minZoom, Math.min(maxZoom, level));
		select(svgElement)
			.transition()
			.duration(200)
			.call(zoomBehavior.scaleTo, clampedLevel);
	}

	/**
	 * Zoom in by a factor.
	 */
	export function zoomIn(): void {
		setZoom(currentTransform.k * 1.25);
	}

	/**
	 * Zoom out by a factor.
	 */
	export function zoomOut(): void {
		setZoom(currentTransform.k / 1.25);
	}
</script>

<svg
	bind:this={svgElement}
	class="h-full w-full touch-none"
	style="background: var(--color-surface);"
>
	<g
		bind:this={contentGroup}
		transform="translate({currentTransform.x}, {currentTransform.y}) scale({currentTransform.k})"
	>
		{@render children?.()}
	</g>
</svg>
