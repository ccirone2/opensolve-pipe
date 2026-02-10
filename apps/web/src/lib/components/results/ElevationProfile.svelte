<script lang="ts">
	/**
	 * Elevation Profile Visualization.
	 *
	 * Renders an SVG chart showing physical pipe elevations, component positions,
	 * hydraulic grade lines (HGL), and head losses across the system.
	 * Translated from the React reference in docs/features/viz_elevation_profile/.
	 */
	import type { ElevationElement } from '$lib/utils/elevationProfile';

	interface Props {
		/** Elevation profile data elements (ordered upstream → downstream). */
		data: ElevationElement[];
	}

	let { data }: Props = $props();

	// ---- State ----
	let hoveredItem: {
		type: string;
		index: number;
		data: ElevationElement;
		x: number;
		y: number;
	} | null = $state(null);
	let showMinMax = $state(true);
	let showHGL = $state(true);
	let showFlowingHGL = $state(true);
	let containerElement: HTMLDivElement | undefined = $state();
	let containerWidth = $state(900);

	// ---- Responsive width ----
	$effect(() => {
		if (!containerElement) return;
		const observer = new ResizeObserver((entries) => {
			for (const entry of entries) {
				containerWidth = Math.max(400, entry.contentRect.width);
			}
		});
		observer.observe(containerElement);
		return () => observer.disconnect();
	});

	// ---- Semantic colors ----
	const COLORS = {
		tank: '#2563eb',
		valve: '#059669',
		pump: '#dc2626',
		conn: '#64748b',
		water: '#0ea5e9',
		hgl: '#a855f7',
		hglFlow: '#22c55e',
		accent: '#f59e0b'
	} as const;

	// ---- Layout dimensions ----
	let margin = $derived({
		top: 50,
		right: 30,
		bottom: 70,
		left: 60
	});
	let width = $derived(containerWidth);
	let height = $derived(Math.max(300, Math.min(500, containerWidth * 0.55)));
	let plotWidth = $derived(width - margin.left - margin.right);
	let plotHeight = $derived(height - margin.top - margin.bottom);

	// ---- Data processing ----
	let components = $derived(data.filter((d) => d.type === 'comp'));

	let componentPositions = $derived.by(() => {
		const positions: { component: ElevationElement; cumulativeLength: number }[] = [];
		let cumLen = 0;
		for (const item of data) {
			if (item.type === 'comp') {
				positions.push({ component: item, cumulativeLength: cumLen });
			} else if (item.type === 'conn') {
				cumLen += item.length ?? 0;
			}
		}
		return positions;
	});

	let totalLength = $derived(
		componentPositions.length > 0
			? componentPositions[componentPositions.length - 1].cumulativeLength +
				data
					.filter((d) => d.type === 'conn')
					.reduce((sum, d) => sum + (d.length ?? 0), 0) -
				componentPositions.reduce((sum, p) => sum + 0, 0)
			: 0
	);

	// Recalculate total properly
	let totalPipeLength = $derived(
		data.filter((d) => d.type === 'conn').reduce((sum, d) => sum + (d.length ?? 0), 0)
	);

	// Build segments between components
	let segments = $derived.by(() => {
		const segs: {
			startComp: ElevationElement;
			startCompIndex: number;
			endComp: ElevationElement;
			endCompIndex: number;
			connections: (ElevationElement & { originalIndex: number })[];
			boundaries: { elevation: number; afterConnectionIndex: number }[];
			segmentLength: number;
		}[] = [];

		let current: {
			startComp: ElevationElement;
			startCompIndex: number;
			connections: (ElevationElement & { originalIndex: number })[];
		} | null = null;

		for (let i = 0; i < data.length; i++) {
			const item = data[i];
			if (item.type === 'comp') {
				if (current) {
					const endCompIndex = components.indexOf(item);
					const conns = current.connections;
					const segLen = conns.reduce((sum, c) => sum + (c.length ?? 0), 0);

					const boundaries: { elevation: number; afterConnectionIndex: number }[] = [];
					if (conns.length > 1) {
						for (let j = 0; j < conns.length - 1; j++) {
							boundaries.push({
								elevation: conns[j].p2_el ?? conns[j].p1_el,
								afterConnectionIndex: j
							});
						}
					}

					segs.push({
						startComp: current.startComp,
						startCompIndex: current.startCompIndex,
						endComp: item,
						endCompIndex,
						connections: conns,
						boundaries,
						segmentLength: segLen
					});
				}
				current = {
					startComp: item,
					startCompIndex: components.indexOf(item),
					connections: []
				};
			} else if (item.type === 'conn' && current) {
				current.connections.push({ ...item, originalIndex: i });
			}
		}

		return segs;
	});

	// ---- Scales ----
	let allElevations = $derived(
		data.flatMap((d) => [d.min_el, d.max_el, d.p1_el, d.p2_el].filter((v): v is number => v != null))
	);

	let minEl = $derived(allElevations.length > 0 ? Math.min(...allElevations) - 10 : 0);
	let maxEl = $derived(allElevations.length > 0 ? Math.max(...allElevations) + 10 : 100);

	function xScale(compIndex: number): number {
		if (totalPipeLength === 0 || componentPositions.length === 0) {
			if (components.length <= 1) return margin.left + plotWidth / 2;
			return margin.left + (compIndex * plotWidth) / (components.length - 1);
		}
		const pos = componentPositions[compIndex];
		if (!pos) return margin.left;
		return margin.left + (pos.cumulativeLength / totalPipeLength) * plotWidth;
	}

	function yScale(el: number): number {
		if (maxEl === minEl) return margin.top + plotHeight / 2;
		return margin.top + plotHeight - ((el - minEl) / (maxEl - minEl)) * plotHeight;
	}

	// Grid ticks
	let yTicks = $derived.by(() => {
		const ticks: number[] = [];
		const start = Math.ceil(minEl / 10) * 10;
		for (let el = start; el <= maxEl; el += 10) {
			ticks.push(el);
		}
		return ticks;
	});

	// ---- Color helper ----
	function getComponentColor(name: string): string {
		const lower = name.toLowerCase();
		if (lower.includes('reservoir') || lower.includes('tank') || lower.includes('tnk')) return COLORS.tank;
		if (lower.includes('valve') || lower.includes('vlv')) return COLORS.valve;
		if (lower.includes('pump') || lower.includes('pmp')) return COLORS.pump;
		return COLORS.conn;
	}

	// ---- Flowing HGL ----
	let flowingHGLPoints = $derived.by(() => {
		if (data.length === 0) return [];

		// Find start HGL: first tank/reservoir max_el, or first component p1_el
		const firstWithMax = data.find((d) => d.type === 'comp' && d.max_el != null);
		let currentHGL = firstWithMax?.max_el ?? data[0].p1_el;

		const points: { x: number; y: number; name: string }[] = [];
		let cumLen = 0;

		for (const item of data) {
			if (item.type === 'comp') {
				const compIdx = components.indexOf(item);
				const cx = xScale(compIdx);

				points.push({ x: cx, y: currentHGL, name: item.name });
				currentHGL += item.head_change ?? 0;
				points.push({ x: cx, y: currentHGL, name: item.name + '-out' });
			} else if (item.type === 'conn') {
				const connLen = item.length ?? 0;
				const startX = margin.left + (totalPipeLength > 0 ? (cumLen / totalPipeLength) * plotWidth : 0);
				cumLen += connLen;
				const endX = margin.left + (totalPipeLength > 0 ? (cumLen / totalPipeLength) * plotWidth : 0);

				points.push({ x: startX, y: currentHGL, name: item.name + '-start' });
				currentHGL += item.head_change ?? 0;
				points.push({ x: endX, y: currentHGL, name: item.name + '-end' });
			}
		}

		return points;
	});

	// Clip flowing HGL to visible range and produce path segments
	let hglPathSegments = $derived.by(() => {
		const pts = flowingHGLPoints;
		if (pts.length === 0) return [];

		const pathSegments: { x: number; y: number }[][] = [];
		let current: { x: number; y: number }[] = [];

		for (let i = 0; i < pts.length; i++) {
			const point = pts[i];
			const prev = i > 0 ? pts[i - 1] : null;

			if (prev) {
				const wasIn = prev.y >= minEl && prev.y <= maxEl;
				const isIn = point.y >= minEl && point.y <= maxEl;

				if (wasIn && !isIn) {
					const boundary = point.y > maxEl ? maxEl : minEl;
					const t = (boundary - prev.y) / (point.y - prev.y);
					current.push({ x: prev.x + t * (point.x - prev.x), y: boundary });
					if (current.length > 1) pathSegments.push([...current]);
					current = [];
				} else if (!wasIn && isIn) {
					const boundary = prev.y > maxEl ? maxEl : minEl;
					const t = (boundary - prev.y) / (point.y - prev.y);
					current = [{ x: prev.x + t * (point.x - prev.x), y: boundary }];
				}
			}

			if (point.y >= minEl && point.y <= maxEl) {
				current.push(point);
			}
		}

		if (current.length > 1) pathSegments.push(current);
		return pathSegments;
	});

	// Peak HGL point
	let peakHGL = $derived.by(() => {
		if (flowingHGLPoints.length === 0) return null;
		return flowingHGLPoints.reduce((max, p) => (p.y > max.y ? p : max), flowingHGLPoints[0]);
	});

	// ---- No-flow HGL ----
	let noFlowHGL = $derived.by(() => {
		const firstTank = components.find(
			(c) => c.max_el != null && (c.name.toLowerCase().includes('reservoir') ||
				c.name.toLowerCase().includes('tank') || c.name.toLowerCase().includes('tnk'))
		);
		const lastTank = [...components].reverse().find(
			(c) => c.max_el != null && (c.name.toLowerCase().includes('reservoir') ||
				c.name.toLowerCase().includes('tank') || c.name.toLowerCase().includes('tnk'))
		);
		const pumpIndex = components.findIndex(
			(c) => c.name.toLowerCase().includes('pump') || c.name.toLowerCase().includes('pmp')
		);

		if (!firstTank || pumpIndex === -1) return null;

		return {
			upstreamHGL: firstTank.max_el!,
			downstreamHGL: lastTank?.max_el ?? firstTank.max_el!,
			pumpX: xScale(pumpIndex)
		};
	});

	// ---- Connection paths ----
	function buildConnectionPath(
		segment: (typeof segments)[0]
	): { x: number; y: number }[] {
		const startX = xScale(segment.startCompIndex);
		const endX = xScale(segment.endCompIndex);
		const startEl = segment.startComp.p2_el ?? segment.startComp.p1_el;
		const endEl = segment.endComp.p1_el;
		const totalW = endX - startX;
		const isSeries = segment.connections.length > 1;
		const points: { x: number; y: number }[] = [];

		if (segment.connections.length === 0) {
			return [
				{ x: startX, y: yScale(startEl) },
				{ x: endX, y: yScale(endEl) }
			];
		}

		if (!isSeries) {
			const conn = segment.connections[0];
			const p1El = conn.p1_el;
			const p2El = conn.p2_el ?? conn.p1_el;
			const midX = (startX + endX) / 2;

			points.push({ x: startX, y: yScale(startEl) });
			points.push({ x: midX, y: yScale(startEl) });
			if (startEl !== p1El) points.push({ x: midX, y: yScale(p1El) });
			if (p1El !== p2El) points.push({ x: midX, y: yScale(p2El) });
			if (p2El !== endEl) points.push({ x: midX, y: yScale(endEl) });
			points.push({ x: endX, y: yScale(endEl) });
		} else {
			const segLen = segment.segmentLength || segment.connections.reduce((s, c) => s + (c.length ?? 1), 0);
			let cumX = startX;
			const connXPositions = segment.connections.map((conn) => {
				const w = ((conn.length ?? 1) / segLen) * totalW;
				const sx = cumX;
				cumX += w;
				return { startX: sx, endX: cumX };
			});

			points.push({ x: startX, y: yScale(startEl) });

			segment.connections.forEach((conn, idx) => {
				const p1El = conn.p1_el;
				const p2El = conn.p2_el ?? conn.p1_el;
				const isRising = p2El > p1El || (conn.max_el != null && conn.max_el > p2El && p2El >= p1El);

				if (isRising) {
					points.push({ x: connXPositions[idx].startX, y: yScale(p2El) });
					points.push({ x: connXPositions[idx].endX, y: yScale(p2El) });
				} else {
					points.push({ x: connXPositions[idx].endX, y: yScale(p1El) });
					if (p2El !== p1El) {
						points.push({ x: connXPositions[idx].endX, y: yScale(p2El) });
					}
				}
			});

			const lastConn = segment.connections[segment.connections.length - 1];
			const lastP2 = lastConn.p2_el ?? lastConn.p1_el;
			if (lastP2 !== endEl) {
				points.push({ x: endX, y: yScale(lastP2) });
			}
			points.push({ x: endX, y: yScale(endEl) });
		}

		return points;
	}

	function pointsToPath(pts: { x: number; y: number }[]): string {
		return pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
	}

	// ---- Hover handlers ----
	function handleHover(
		type: string,
		index: number,
		el: ElevationElement,
		x: number,
		y: number
	): void {
		hoveredItem = { type, index, data: el, x, y };
	}

	function handleLeave(): void {
		hoveredItem = null;
	}
</script>

<div bind:this={containerElement} class="flex flex-col gap-4">
	{#if data.length === 0}
		<div class="flex flex-col items-center justify-center py-12 text-center">
			<svg
				class="h-12 w-12 text-[var(--color-text-subtle)]"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"
				/>
			</svg>
			<p class="mt-4 text-sm text-[var(--color-text-muted)]">
				No elevation data available. Add components with elevations and solve the network.
			</p>
		</div>
	{:else}
		<!-- Legend & Toggle Controls -->
		<div class="flex flex-wrap items-center gap-4 text-xs">
			<div class="flex items-center gap-1.5">
				<span class="inline-block h-3 w-3 rounded-full" style="background: {COLORS.tank}"></span>
				<span class="text-[var(--color-text-muted)]">Tank/Reservoir</span>
			</div>
			<div class="flex items-center gap-1.5">
				<span class="inline-block h-3 w-3 rounded-full" style="background: {COLORS.valve}"></span>
				<span class="text-[var(--color-text-muted)]">Valve</span>
			</div>
			<div class="flex items-center gap-1.5">
				<span class="inline-block h-3 w-3 rounded-full" style="background: {COLORS.pump}"></span>
				<span class="text-[var(--color-text-muted)]">Pump</span>
			</div>
			<div class="flex items-center gap-1.5">
				<span class="inline-block h-1 w-4" style="background: {COLORS.conn}"></span>
				<span class="text-[var(--color-text-muted)]">Piping</span>
			</div>

			<div class="ml-auto flex flex-wrap gap-3">
				<label class="flex cursor-pointer items-center gap-1.5">
					<input type="checkbox" bind:checked={showMinMax} class="accent-[#f59e0b]" />
					<span class="text-[var(--color-text-muted)]">Min/Max</span>
				</label>
				<label class="flex cursor-pointer items-center gap-1.5">
					<input type="checkbox" bind:checked={showHGL} class="accent-[#a855f7]" />
					<span class="text-[var(--color-text-muted)]">HGL (No Flow)</span>
				</label>
				<label class="flex cursor-pointer items-center gap-1.5">
					<input type="checkbox" bind:checked={showFlowingHGL} class="accent-[#22c55e]" />
					<span class="text-[var(--color-text-muted)]">HGL (Flowing)</span>
				</label>
			</div>
		</div>

		<!-- SVG Chart -->
		<svg
			viewBox="0 0 {width} {height}"
			class="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]"
			style="max-height: 500px;"
		>
			<!-- Grid lines -->
			{#each yTicks as el}
				<line
					x1={margin.left}
					y1={yScale(el)}
					x2={width - margin.right}
					y2={yScale(el)}
					stroke="var(--color-border)"
					stroke-width="1"
					stroke-dasharray={el % 50 === 0 ? 'none' : '4,4'}
					opacity={el % 50 === 0 ? 0.6 : 0.25}
				/>
				<text
					x={margin.left - 8}
					y={yScale(el)}
					fill="var(--color-text-muted)"
					font-size="10"
					text-anchor="end"
					dominant-baseline="middle"
				>
					{el}
				</text>
			{/each}

			<!-- Y-axis label -->
			<text
				x="16"
				y={height / 2}
				fill="var(--color-text-muted)"
				font-size="11"
				text-anchor="middle"
				transform="rotate(-90, 16, {height / 2})"
			>
				Elevation (ft)
			</text>

			<!-- No-Flow HGL -->
			{#if showHGL && noFlowHGL}
				<line
					x1={margin.left}
					y1={yScale(noFlowHGL.upstreamHGL)}
					x2={noFlowHGL.pumpX}
					y2={yScale(noFlowHGL.upstreamHGL)}
					stroke={COLORS.hgl}
					stroke-width="2"
					stroke-dasharray="8,4"
					opacity="0.8"
				/>
				<line
					x1={noFlowHGL.pumpX}
					y1={yScale(noFlowHGL.upstreamHGL)}
					x2={noFlowHGL.pumpX}
					y2={yScale(noFlowHGL.downstreamHGL)}
					stroke={COLORS.hgl}
					stroke-width="2"
					stroke-dasharray="4,4"
					opacity="0.6"
				/>
				<line
					x1={noFlowHGL.pumpX}
					y1={yScale(noFlowHGL.downstreamHGL)}
					x2={width - margin.right}
					y2={yScale(noFlowHGL.downstreamHGL)}
					stroke={COLORS.hgl}
					stroke-width="2"
					stroke-dasharray="8,4"
					opacity="0.8"
				/>
				<text
					x={margin.left + 4}
					y={yScale(noFlowHGL.upstreamHGL) - 6}
					fill={COLORS.hgl}
					font-size="9"
					opacity="0.8"
				>
					HGL: {noFlowHGL.upstreamHGL}
				</text>
				<text
					x={width - margin.right - 4}
					y={yScale(noFlowHGL.downstreamHGL) - 6}
					fill={COLORS.hgl}
					font-size="9"
					text-anchor="end"
					opacity="0.8"
				>
					HGL: {noFlowHGL.downstreamHGL}
				</text>
			{/if}

			<!-- Flowing HGL -->
			{#if showFlowingHGL && flowingHGLPoints.length > 0}
				{#each hglPathSegments as segment, idx}
					<path
						d={segment.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${yScale(p.y).toFixed(1)}`).join(' ')}
						stroke={COLORS.hglFlow}
						stroke-width="2.5"
						fill="none"
						opacity="0.9"
					/>
				{/each}

				<!-- Clipped HGL regions (dotted line at top) -->
				{#each flowingHGLPoints as point, idx}
					{#if idx > 0}
						{@const prev = flowingHGLPoints[idx - 1]}
						{#if prev.y > maxEl || point.y > maxEl}
							{@const x1 = prev.y <= maxEl
								? prev.x + ((maxEl - prev.y) / (point.y - prev.y)) * (point.x - prev.x)
								: prev.x}
							{@const x2 = point.y <= maxEl
								? prev.x + ((maxEl - prev.y) / (point.y - prev.y)) * (point.x - prev.x)
								: point.x}
							<line
								x1={x1}
								y1={yScale(maxEl)}
								x2={x2}
								y2={yScale(maxEl)}
								stroke={COLORS.hglFlow}
								stroke-width="2.5"
								stroke-dasharray="2,3"
								opacity="0.7"
							/>
						{/if}
					{/if}
				{/each}

				<!-- Peak indicator -->
				{#if peakHGL && peakHGL.y > maxEl}
					<polygon
						points="{peakHGL.x},{margin.top + 5} {peakHGL.x - 5},{margin.top + 13} {peakHGL.x + 5},{margin.top + 13}"
						fill={COLORS.hglFlow}
					/>
					<text
						x={peakHGL.x}
						y={margin.top + 24}
						fill={COLORS.hglFlow}
						font-size="10"
						text-anchor="middle"
						font-weight="600"
					>
						{peakHGL.y.toFixed(0)}
					</text>
				{/if}
			{/if}

			<!-- Connection lines -->
			{#each segments as segment, segIdx}
				{@const pathPoints = buildConnectionPath(segment)}
				{@const pathD = pointsToPath(pathPoints)}
				<path
					d={pathD}
					stroke="var(--color-text-muted)"
					stroke-width="3"
					stroke-linecap="round"
					stroke-linejoin="round"
					fill="none"
					opacity="0.5"
				/>

				<!-- Connection hover areas -->
				{#each segment.connections as conn, connIdx}
					{@const isHovered = hoveredItem?.type === 'conn' && hoveredItem?.data.id === conn.id}
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<path
						d={pathD}
						stroke="transparent"
						stroke-width="16"
						fill="none"
						class="cursor-pointer"
						onmouseenter={() =>
							handleHover('conn', conn.originalIndex, conn, (xScale(segment.startCompIndex) + xScale(segment.endCompIndex)) / 2, yScale((conn.p1_el + (conn.p2_el ?? conn.p1_el)) / 2))}
						onmouseleave={handleLeave}
					/>
					{#if isHovered}
						<path
							d={pathD}
							stroke={COLORS.water}
							stroke-width="5"
							stroke-linecap="round"
							stroke-linejoin="round"
							fill="none"
							style="pointer-events: none;"
						/>
					{/if}

					<!-- Min/Max indicators for connections -->
					{#if showMinMax && (conn.min_el != null || conn.max_el != null)}
						{@const midX = (xScale(segment.startCompIndex) + xScale(segment.endCompIndex)) / 2}
						{#if conn.min_el != null}
							<line
								x1={midX}
								y1={yScale(Math.min(conn.p1_el, conn.p2_el ?? conn.p1_el))}
								x2={midX}
								y2={yScale(conn.min_el)}
								stroke={COLORS.accent}
								stroke-width="2"
								stroke-dasharray="4,2"
								opacity="0.7"
							/>
							<circle cx={midX} cy={yScale(conn.min_el)} r="3.5" fill={COLORS.accent} />
							<text x={midX + 7} y={yScale(conn.min_el)} fill={COLORS.accent} font-size="9" dominant-baseline="middle">
								low: {conn.min_el}
							</text>
						{/if}
						{#if conn.max_el != null}
							<line
								x1={midX}
								y1={yScale(Math.max(conn.p1_el, conn.p2_el ?? conn.p1_el))}
								x2={midX}
								y2={yScale(conn.max_el)}
								stroke={COLORS.accent}
								stroke-width="2"
								stroke-dasharray="4,2"
								opacity="0.7"
							/>
							<circle cx={midX} cy={yScale(conn.max_el)} r="3.5" fill={COLORS.accent} />
							<text x={midX + 7} y={yScale(conn.max_el)} fill={COLORS.accent} font-size="9" dominant-baseline="middle">
								high: {conn.max_el}
							</text>
						{/if}
					{/if}
				{/each}

				<!-- Series boundary markers -->
				{#each segment.boundaries as boundary, bIdx}
					{@const segLen = segment.segmentLength || segment.connections.reduce((s, c) => s + (c.length ?? 1), 0)}
					{@const afterIdx = boundary.afterConnectionIndex}
					{@const cumConnLen = segment.connections.slice(0, afterIdx + 1).reduce((s, c) => s + (c.length ?? 1), 0)}
					{@const totalW = xScale(segment.endCompIndex) - xScale(segment.startCompIndex)}
					{@const bx = xScale(segment.startCompIndex) + (cumConnLen / segLen) * totalW}
					<circle
						cx={bx}
						cy={yScale(boundary.elevation)}
						r="4"
						fill="var(--color-text)"
						stroke="var(--color-surface)"
						stroke-width="1.5"
					/>
				{/each}
			{/each}

			<!-- Tank water level ranges -->
			{#if showMinMax}
				{#each components as comp, i}
					{#if comp.min_el != null && comp.max_el != null}
						{@const cx = xScale(i)}
						<rect
							x={cx - 16}
							y={yScale(comp.max_el)}
							width="32"
							height={yScale(comp.min_el) - yScale(comp.max_el)}
							fill={COLORS.water}
							opacity="0.2"
							rx="3"
							class="animate-pulse"
						/>
						<line
							x1={cx - 16}
							y1={yScale(comp.max_el)}
							x2={cx + 16}
							y2={yScale(comp.max_el)}
							stroke={COLORS.water}
							stroke-width="1.5"
							stroke-dasharray="5,3"
						/>
						<line
							x1={cx - 16}
							y1={yScale(comp.min_el)}
							x2={cx + 16}
							y2={yScale(comp.min_el)}
							stroke={COLORS.water}
							stroke-width="1.5"
							stroke-dasharray="5,3"
						/>
						<text x={cx + 20} y={yScale(comp.max_el)} fill={COLORS.water} font-size="9" dominant-baseline="middle" opacity="0.8">max</text>
						<text x={cx + 20} y={yScale(comp.min_el)} fill={COLORS.water} font-size="9" dominant-baseline="middle" opacity="0.8">min</text>
					{/if}
				{/each}
			{/if}

			<!-- Component markers -->
			{#each components as comp, i}
				{@const cx = xScale(i)}
				{@const color = getComponentColor(comp.name)}
				{@const isHovered = hoveredItem?.type === 'comp' && hoveredItem?.data.id === comp.id}

				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<g
					class="cursor-pointer"
					onmouseenter={() => handleHover('comp', data.indexOf(comp), comp, cx, yScale(comp.p1_el))}
					onmouseleave={handleLeave}
				>
					<!-- P1 marker -->
					<circle
						cx={cx}
						cy={yScale(comp.p1_el)}
						r="7"
						fill={color}
						stroke={isHovered ? 'var(--color-text)' : 'var(--color-surface)'}
						stroke-width={isHovered ? 2.5 : 1.5}
					/>

					<!-- P2 marker (if different from P1) -->
					{#if comp.p2_el != null && comp.p2_el !== comp.p1_el}
						<line
							x1={cx}
							y1={yScale(comp.p1_el)}
							x2={cx}
							y2={yScale(comp.p2_el)}
							stroke={color}
							stroke-width="3"
						/>
						<circle
							cx={cx}
							cy={yScale(comp.p2_el)}
							r="7"
							fill={color}
							stroke={isHovered ? 'var(--color-text)' : 'var(--color-surface)'}
							stroke-width={isHovered ? 2.5 : 1.5}
						/>
					{/if}

					<!-- Component name label -->
					<text
						x={cx}
						y={height - margin.bottom + 16}
						fill="var(--color-text)"
						font-size="11"
						text-anchor="middle"
						font-weight={isHovered ? '600' : '400'}
					>
						{comp.name}
					</text>
				</g>
			{/each}

			<!-- Hover tooltip -->
			{#if hoveredItem}
				{@const tipData = hoveredItem.data}
				{@const tipH = 48 + (tipData.length != null ? 14 : 0) + (tipData.head_change != null ? 14 : 0) + (tipData.min_el != null || tipData.max_el != null ? 14 : 0)}
				{@const tipX = Math.max(margin.left + 70, Math.min(width - margin.right - 70, hoveredItem.x))}
				{@const tipY = Math.max(margin.top + tipH + 5, hoveredItem.y - 10)}
				<g style="pointer-events: none;">
					<rect
						x={tipX - 65}
						y={tipY - tipH}
						width="130"
						height={tipH}
						fill="var(--color-surface-elevated)"
						stroke="var(--color-border)"
						stroke-width="1"
						rx="5"
						filter="drop-shadow(0 2px 4px rgba(0,0,0,0.15))"
					/>
					<text
						x={tipX}
						y={tipY - tipH + 16}
						fill="var(--color-text)"
						font-size="11"
						text-anchor="middle"
						font-weight="600"
					>
						{tipData.name}
					</text>
					<text
						x={tipX}
						y={tipY - tipH + 30}
						fill="var(--color-text-muted)"
						font-size="9"
						text-anchor="middle"
					>
						P1: {tipData.p1_el}{tipData.p2_el != null ? ` | P2: ${tipData.p2_el}` : ''}
					</text>
					{#if tipData.length != null}
						<text
							x={tipX}
							y={tipY - tipH + 44}
							fill="var(--color-text-muted)"
							font-size="9"
							text-anchor="middle"
						>
							Length: {tipData.length} ft
						</text>
					{/if}
					{#if tipData.head_change != null}
						<text
							x={tipX}
							y={tipY - tipH + (tipData.length != null ? 58 : 44)}
							fill={tipData.head_change >= 0 ? COLORS.hglFlow : '#ef4444'}
							font-size="9"
							text-anchor="middle"
						>
							{'\u0394'}H: {tipData.head_change >= 0 ? '+' : ''}{tipData.head_change.toFixed(1)} ft
						</text>
					{/if}
				</g>
			{/if}
		</svg>

		<!-- Data Table -->
		<div class="overflow-x-auto rounded-lg border border-[var(--color-border)]">
			<table class="w-full text-left text-xs">
				<thead>
					<tr class="border-b border-[var(--color-border)] bg-[var(--color-surface-elevated)]">
						<th class="px-3 py-2 font-medium text-[var(--color-text-muted)]">Type</th>
						<th class="px-3 py-2 font-medium text-[var(--color-text-muted)]">Name</th>
						<th class="px-3 py-2 font-medium text-[var(--color-text-muted)]">Length</th>
						<th class="px-3 py-2 font-medium text-[var(--color-text-muted)]">{'\u0394'}H (ft)</th>
						<th class="px-3 py-2 font-medium text-[var(--color-text-muted)]">P1 El</th>
						<th class="px-3 py-2 font-medium text-[var(--color-text-muted)]">P2 El</th>
					</tr>
				</thead>
				<tbody>
					{#each data as item, i}
						{@const isHovered = hoveredItem?.data.id === item.id}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<tr
							class="border-b border-[var(--color-border)] transition-colors {isHovered ? 'bg-[var(--color-accent)]/10' : 'hover:bg-[var(--color-surface-elevated)]'}"
							onmouseenter={() => {
								const cx = item.type === 'comp'
									? xScale(components.indexOf(item))
									: width / 2;
								handleHover(item.type, i, item, cx, yScale(item.p1_el));
							}}
							onmouseleave={handleLeave}
						>
							<td class="px-3 py-1.5 text-[var(--color-text-muted)]">{item.type}</td>
							<td class="px-3 py-1.5 font-medium" style="color: {item.type === 'comp' ? getComponentColor(item.name) : 'var(--color-text)'}">
								{item.name}
							</td>
							<td class="px-3 py-1.5 text-[var(--color-text)]">
								{item.length != null ? item.length : '\u2014'}
							</td>
							<td class="px-3 py-1.5 font-medium"
								style="color: {item.head_change != null && item.head_change > 0 ? COLORS.hglFlow : item.head_change != null && item.head_change < 0 ? '#ef4444' : 'var(--color-text-muted)'}"
							>
								{item.head_change != null ? (item.head_change >= 0 ? '+' : '') + item.head_change.toFixed(1) : '\u2014'}
							</td>
							<td class="px-3 py-1.5 text-[var(--color-text)]">{item.p1_el}</td>
							<td class="px-3 py-1.5 text-[var(--color-text)]">{item.p2_el ?? '\u2014'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
