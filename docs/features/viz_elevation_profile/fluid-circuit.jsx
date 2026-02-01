import React, { useState } from 'react';

const data = [
  { type: 'comp', name: 'tnk-1', min_el: 650, max_el: 675, p1_el: 655, p2_el: null, head_change: -2 },
  { type: 'conn', name: 'cx-1', min_el: null, max_el: null, p1_el: 655, p2_el: 655, length: 50, head_change: -1 },
  { type: 'comp', name: 'vlv-1', min_el: null, max_el: null, p1_el: 655, p2_el: 655, head_change: -5 },
  { type: 'conn', name: 'cx-2', min_el: null, max_el: null, p1_el: 655, p2_el: 645, length: 120, head_change: -3 },
  { type: 'comp', name: 'pmp-1', min_el: null, max_el: null, p1_el: 645, p2_el: 655, head_change: 85 },
  { type: 'conn', name: 'cx-3', min_el: 640, max_el: null, p1_el: 655, p2_el: 660, length: 200, head_change: -4 },
  { type: 'conn', name: 'cx-4', min_el: null, max_el: 700, p1_el: 660, p2_el: 675, length: 350, head_change: -50 },
  { type: 'comp', name: 'tank-2', min_el: 680, max_el: 690, p1_el: 675, p2_el: null, head_change: -5 },
];

const COLORS = {
  tank: { fill: '#2563eb', stroke: '#1d4ed8', light: '#93c5fd' },
  valve: { fill: '#059669', stroke: '#047857', light: '#6ee7b7' },
  pump: { fill: '#dc2626', stroke: '#b91c1c', light: '#fca5a5' },
  conn: { fill: '#64748b', stroke: '#475569', light: '#cbd5e1' },
  water: { fill: '#0ea5e9', stroke: '#0284c7', light: '#7dd3fc' },
  hgl: { fill: '#a855f7', stroke: '#9333ea', light: '#d8b4fe' },
  hglFlow: { fill: '#22c55e', stroke: '#16a34a', light: '#86efac' },
  grid: '#334155',
  text: '#f1f5f9',
  bg: '#0f172a',
  accent: '#f59e0b',
};

export default function FluidCircuitViz() {
  const [hoveredItem, setHoveredItem] = useState(null);
  const [showMinMax, setShowMinMax] = useState(true);
  const [showHGL, setShowHGL] = useState(true);
  const [showFlowingHGL, setShowFlowingHGL] = useState(true);

  // Filter to only components for x-axis positioning
  const components = data.filter(d => d.type === 'comp');

  // Calculate cumulative lengths for positioning components
  // Each component's x position is based on the total length of connections before it
  const componentPositions = [];
  let cumulativeLength = 0;
  let currentSegmentConnections = [];

  for (let i = 0; i < data.length; i++) {
    const item = data[i];
    if (item.type === 'comp') {
      componentPositions.push({
        component: item,
        cumulativeLength: cumulativeLength,
        precedingConnections: [...currentSegmentConnections],
      });
      currentSegmentConnections = [];
    } else if (item.type === 'conn') {
      cumulativeLength += item.length || 0;
      currentSegmentConnections.push(item);
    }
  }

  const totalLength = cumulativeLength;

  // Build segments: each segment connects two adjacent components
  // Consecutive connections are merged into a single "pipe run" with boundary markers
  const segments = [];
  let currentSegment = null;

  for (let i = 0; i < data.length; i++) {
    const item = data[i];
    if (item.type === 'comp') {
      if (currentSegment) {
        currentSegment.endComp = item;
        currentSegment.endCompIndex = components.indexOf(item);
        segments.push(currentSegment);
      }
      currentSegment = {
        startComp: item,
        startCompIndex: components.indexOf(item),
        connections: [],
      };
    } else if (item.type === 'conn' && currentSegment) {
      currentSegment.connections.push({ ...item, originalIndex: i });
    }
  }

  // Process segments to identify boundaries between consecutive connections
  const processedSegments = segments.map(segment => {
    const { connections } = segment;

    // Calculate total length of this segment
    const segmentLength = connections.reduce((sum, c) => sum + (c.length || 0), 0);

    if (connections.length <= 1) {
      return { ...segment, boundaries: [], segmentLength };
    }

    // Boundaries occur between consecutive connections
    const boundaries = [];
    for (let i = 0; i < connections.length - 1; i++) {
      const currConn = connections[i];
      // The boundary elevation is where they meet (p2 of current = p1 of next)
      const boundaryEl = currConn.p2_el || currConn.p1_el;
      boundaries.push({
        elevation: boundaryEl,
        afterConnectionIndex: i,
      });
    }

    return { ...segment, boundaries, segmentLength };
  });

  // Calculate layout dimensions
  const margin = { top: 60, right: 40, bottom: 80, left: 70 };
  const width = 900;
  const height = 500;
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;

  // Find elevation range
  const allElevations = data.flatMap(d => [d.min_el, d.max_el, d.p1_el, d.p2_el].filter(v => v !== null));
  const minEl = Math.min(...allElevations) - 10;
  const maxEl = Math.max(...allElevations) + 10;

  // Scale functions - x based on cumulative pipe lengths
  const xScale = (compIndex) => {
    if (totalLength === 0) {
      // Fallback to even spacing if no lengths
      return margin.left + (compIndex * plotWidth) / (components.length - 1);
    }
    const position = componentPositions[compIndex];
    return margin.left + (position.cumulativeLength / totalLength) * plotWidth;
  };
  const yScale = (el) => margin.top + plotHeight - ((el - minEl) / (maxEl - minEl)) * plotHeight;

  // Generate grid lines
  const yTicks = [];
  for (let el = Math.ceil(minEl / 10) * 10; el <= maxEl; el += 10) {
    yTicks.push(el);
  }

  const getComponentColor = (name) => {
    if (name.includes('tnk') || name.includes('tank')) return COLORS.tank;
    if (name.includes('vlv')) return COLORS.valve;
    if (name.includes('pmp')) return COLORS.pump;
    return COLORS.conn;
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: `linear-gradient(135deg, ${COLORS.bg} 0%, #1e293b 100%)`,
      padding: '24px',
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');

        .connection-line {
          transition: stroke-width 0.2s ease, opacity 0.2s ease;
          cursor: pointer;
        }
        .connection-line:hover {
          stroke-width: 5;
          opacity: 1;
        }
        .connection-hitbox {
          cursor: pointer;
        }
        .component-marker {
          transition: transform 0.2s ease, filter 0.2s ease;
          cursor: pointer;
        }
        .component-marker:hover {
          filter: brightness(1.3) drop-shadow(0 0 8px currentColor);
        }
        .tooltip {
          animation: fadeIn 0.15s ease-out;
          pointer-events: none;
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(5px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .pulse {
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 0.8; }
        }
        .pump-flow-arrow {
          animation: pumpFlowLinear 3s infinite linear;
        }
        @keyframes pumpFlowLinear {
          0% { opacity: 0; transform: translateY(100%); }
          20% { opacity: 1; }
          80% { opacity: 1; }
          100% { opacity: 0; transform: translateY(-100%); }
        }
      `}</style>

      <div style={{
        maxWidth: '960px',
        margin: '0 auto',
      }}>
        {/* Header */}
        <div style={{
          marginBottom: '24px',
          borderBottom: `2px solid ${COLORS.accent}`,
          paddingBottom: '16px',
        }}>
          <h1 style={{
            color: COLORS.text,
            fontSize: '28px',
            fontWeight: 700,
            margin: 0,
            letterSpacing: '-0.5px',
          }}>
            Fluid Circuit Elevation Profile
          </h1>
          <p style={{
            color: '#94a3b8',
            fontSize: '14px',
            margin: '8px 0 0 0',
          }}>
            Component and connection elevations along the flow path
          </p>
        </div>

        {/* Legend */}
        <div style={{
          display: 'flex',
          gap: '24px',
          marginBottom: '20px',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}>
          {[
            { label: 'Tank', color: COLORS.tank, icon: '⬡' },
            { label: 'Valve', color: COLORS.valve, icon: '◈' },
            { label: 'Pump', color: COLORS.pump, icon: '⬢' },
            { label: 'Piping', color: COLORS.conn, icon: '—' },
            { label: 'HGL (No Flow)', color: COLORS.hgl, icon: '┄' },
            { label: 'HGL (Flowing)', color: COLORS.hglFlow, icon: '─' },
          ].map(item => (
            <div key={item.label} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              <span style={{ color: item.color.fill, fontSize: '18px' }}>{item.icon}</span>
              <span style={{ color: COLORS.text, fontSize: '13px' }}>{item.label}</span>
            </div>
          ))}

          <div style={{ marginLeft: 'auto', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              color: COLORS.text,
              fontSize: '13px',
              cursor: 'pointer',
            }}>
              <input
                type="checkbox"
                checked={showMinMax}
                onChange={(e) => setShowMinMax(e.target.checked)}
                style={{ accentColor: COLORS.accent }}
              />
              Min/Max
            </label>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              color: COLORS.text,
              fontSize: '13px',
              cursor: 'pointer',
            }}>
              <input
                type="checkbox"
                checked={showHGL}
                onChange={(e) => setShowHGL(e.target.checked)}
                style={{ accentColor: COLORS.hgl.fill }}
              />
              HGL (No Flow)
            </label>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              color: COLORS.text,
              fontSize: '13px',
              cursor: 'pointer',
            }}>
              <input
                type="checkbox"
                checked={showFlowingHGL}
                onChange={(e) => setShowFlowingHGL(e.target.checked)}
                style={{ accentColor: COLORS.hglFlow.fill }}
              />
              HGL (Flowing)
            </label>
          </div>
        </div>

        {/* SVG Chart */}
        <svg
          width={width}
          height={height}
          style={{
            background: 'rgba(30, 41, 59, 0.5)',
            borderRadius: '12px',
            border: '1px solid rgba(148, 163, 184, 0.2)',
          }}
        >
          {/* Grid lines */}
          {yTicks.map(el => (
            <g key={el}>
              <line
                x1={margin.left}
                y1={yScale(el)}
                x2={width - margin.right}
                y2={yScale(el)}
                stroke={COLORS.grid}
                strokeWidth={1}
                strokeDasharray={el % 50 === 0 ? "none" : "4,4"}
                opacity={el % 50 === 0 ? 0.5 : 0.2}
              />
              <text
                x={margin.left - 10}
                y={yScale(el)}
                fill="#94a3b8"
                fontSize="11"
                textAnchor="end"
                dominantBaseline="middle"
              >
                {el}
              </text>
            </g>
          ))}

          {/* Y-axis label */}
          <text
            x={20}
            y={height / 2}
            fill={COLORS.text}
            fontSize="12"
            textAnchor="middle"
            transform={`rotate(-90, 20, ${height / 2})`}
          >
            Elevation (ft)
          </text>

          {/* No-Flow Hydraulic Grade Line (HGL) */}
          {showHGL && (() => {
            // Find the first tank's max_el for upstream HGL
            const firstTank = components.find(c => c.name.includes('tnk') || c.name.includes('tank'));
            const lastTank = [...components].reverse().find(c => c.name.includes('tnk') || c.name.includes('tank'));
            const upstreamHGL = firstTank?.max_el;
            const downstreamHGL = lastTank?.max_el;

            // Find pump location (with check valve - causes HGL jump)
            const pumpIndex = components.findIndex(c => c.name.includes('pmp'));

            if (!upstreamHGL || pumpIndex === -1) return null;

            const pumpX = xScale(pumpIndex);
            const pump = components[pumpIndex];
            // Jump occurs at pump discharge (p2 side)
            const jumpX = pumpX;

            return (
              <g>
                {/* Upstream HGL - from start to pump suction */}
                <line
                  x1={margin.left}
                  y1={yScale(upstreamHGL)}
                  x2={jumpX}
                  y2={yScale(upstreamHGL)}
                  stroke={COLORS.hgl.fill}
                  strokeWidth={2}
                  strokeDasharray="8,4"
                  opacity={0.8}
                />

                {/* HGL jump at pump (vertical dashed line) */}
                <line
                  x1={jumpX}
                  y1={yScale(upstreamHGL)}
                  x2={jumpX}
                  y2={yScale(downstreamHGL)}
                  stroke={COLORS.hgl.fill}
                  strokeWidth={2}
                  strokeDasharray="4,4"
                  opacity={0.6}
                />

                {/* Downstream HGL - from pump discharge to end */}
                <line
                  x1={jumpX}
                  y1={yScale(downstreamHGL)}
                  x2={width - margin.right}
                  y2={yScale(downstreamHGL)}
                  stroke={COLORS.hgl.fill}
                  strokeWidth={2}
                  strokeDasharray="8,4"
                  opacity={0.8}
                />

                {/* HGL labels */}
                <text
                  x={margin.left + 5}
                  y={yScale(upstreamHGL) - 8}
                  fill={COLORS.hgl.light}
                  fontSize="10"
                >
                  HGL: {upstreamHGL}
                </text>
                <text
                  x={width - margin.right - 5}
                  y={yScale(downstreamHGL) - 8}
                  fill={COLORS.hgl.light}
                  fontSize="10"
                  textAnchor="end"
                >
                  HGL: {downstreamHGL}
                </text>

                {/* Jump indicator */}
                <circle
                  cx={jumpX}
                  cy={yScale((upstreamHGL + downstreamHGL) / 2)}
                  r={4}
                  fill={COLORS.hgl.fill}
                />
              </g>
            );
          })()}

          {/* Flowing HGL - calculated from head changes, clipped to y-axis */}
          {showFlowingHGL && (() => {
            // Calculate HGL points based on cumulative head changes
            // Start at first tank's max_el (water surface)
            const firstTank = data.find(d => d.type === 'comp' && (d.name.includes('tnk') || d.name.includes('tank')));
            if (!firstTank) return null;

            let currentHGL = firstTank.max_el;
            const hglPoints = [];

            // Track x position based on cumulative length
            let cumLength = 0;

            data.forEach((item, idx) => {
              if (item.type === 'comp') {
                const compIdx = components.indexOf(item);
                const compX = xScale(compIdx);

                // Add point at start of component
                hglPoints.push({ x: compX, y: currentHGL, name: item.name });

                // Apply head change
                currentHGL += (item.head_change || 0);

                // Add point at end of component (same x, new HGL)
                hglPoints.push({ x: compX, y: currentHGL, name: item.name + '-out' });
              } else if (item.type === 'conn') {
                // For connections, we need start and end x positions
                const connLength = item.length || 0;
                const startX = margin.left + (cumLength / totalLength) * plotWidth;
                cumLength += connLength;
                const endX = margin.left + (cumLength / totalLength) * plotWidth;

                // Add point at start
                hglPoints.push({ x: startX, y: currentHGL, name: item.name + '-start' });

                // Apply head change (loss) linearly across the pipe
                currentHGL += (item.head_change || 0);

                // Add point at end
                hglPoints.push({ x: endX, y: currentHGL, name: item.name + '-end' });
              }
            });

            // Find points that exceed the y-axis range
            const outOfRangePoints = hglPoints.filter(p => p.y > maxEl || p.y < minEl);

            // Clip HGL values to y-axis range for drawing, but track original values
            const clippedPoints = hglPoints.map(p => ({
              ...p,
              originalY: p.y,
              y: Math.max(minEl, Math.min(maxEl, p.y)),
              isClipped: p.y > maxEl || p.y < minEl
            }));

            // Create path segments, breaking at clipped sections
            const pathSegments = [];
            let currentSegment = [];

            for (let i = 0; i < clippedPoints.length; i++) {
              const point = clippedPoints[i];
              const prevPoint = i > 0 ? clippedPoints[i - 1] : null;

              // If transitioning from in-range to out-of-range or vice versa,
              // we need to find the intersection point
              if (prevPoint && ((prevPoint.originalY <= maxEl && point.originalY > maxEl) ||
                               (prevPoint.originalY >= minEl && point.originalY < minEl) ||
                               (prevPoint.originalY > maxEl && point.originalY <= maxEl) ||
                               (prevPoint.originalY < minEl && point.originalY >= minEl))) {
                // Calculate intersection with boundary
                const boundary = point.originalY > maxEl || prevPoint.originalY > maxEl ? maxEl : minEl;
                const t = (boundary - prevPoint.originalY) / (point.originalY - prevPoint.originalY);
                const intersectX = prevPoint.x + t * (point.x - prevPoint.x);

                if (prevPoint.originalY >= minEl && prevPoint.originalY <= maxEl) {
                  // Going out of range - end current segment at intersection
                  currentSegment.push({ x: intersectX, y: boundary });
                  if (currentSegment.length > 1) {
                    pathSegments.push([...currentSegment]);
                  }
                  currentSegment = [];
                } else {
                  // Coming back in range - start new segment at intersection
                  currentSegment = [{ x: intersectX, y: boundary }];
                }
              }

              if (point.originalY >= minEl && point.originalY <= maxEl) {
                currentSegment.push(point);
              }
            }

            if (currentSegment.length > 1) {
              pathSegments.push(currentSegment);
            }

            // Find peak HGL value and its location for the indicator
            const peakPoint = hglPoints.reduce((max, p) => p.y > max.y ? p : max, hglPoints[0]);
            const minPoint = hglPoints.reduce((min, p) => p.y < min.y ? p : min, hglPoints[0]);

            return (
              <g>
                {/* Draw each visible segment */}
                {pathSegments.map((segment, idx) => {
                  const pathD = segment.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${yScale(p.y)}`).join(' ');
                  return (
                    <path
                      key={`hgl-segment-${idx}`}
                      d={pathD}
                      stroke={COLORS.hglFlow.fill}
                      strokeWidth={2.5}
                      fill="none"
                      opacity={0.9}
                    />
                  );
                })}

                {/* Draw dashed lines at clipped regions to show continuation */}
                {hglPoints.map((point, idx) => {
                  if (idx === 0) return null;
                  const prevPoint = hglPoints[idx - 1];

                  // If either point is above maxEl, draw dashed line segment at top
                  if (prevPoint.y > maxEl || point.y > maxEl) {
                    // Calculate the x positions, clipping to where line is above maxEl
                    let x1 = prevPoint.x;
                    let x2 = point.x;

                    // If previous point is in range but current is out, find intersection
                    if (prevPoint.y <= maxEl && point.y > maxEl) {
                      const t = (maxEl - prevPoint.y) / (point.y - prevPoint.y);
                      x1 = prevPoint.x + t * (point.x - prevPoint.x);
                    }
                    // If previous point is out but current is in range, find intersection
                    if (prevPoint.y > maxEl && point.y <= maxEl) {
                      const t = (maxEl - prevPoint.y) / (point.y - prevPoint.y);
                      x2 = prevPoint.x + t * (point.x - prevPoint.x);
                    }

                    return (
                      <line
                        key={`hgl-clipped-${idx}`}
                        x1={x1}
                        y1={yScale(maxEl)}
                        x2={x2}
                        y2={yScale(maxEl)}
                        stroke={COLORS.hglFlow.fill}
                        strokeWidth={2.5}
                        strokeDasharray="2,3"
                        opacity={0.7}
                      />
                    );
                  }
                  return null;
                })}

                {/* Peak indicator when HGL exceeds plot area */}
                {peakPoint.y > maxEl && (
                  <g>
                    {/* Arrow pointing up */}
                    <polygon
                      points={`${peakPoint.x},${margin.top + 5} ${peakPoint.x - 6},${margin.top + 15} ${peakPoint.x + 6},${margin.top + 15}`}
                      fill={COLORS.hglFlow.fill}
                    />
                    {/* Peak value label */}
                    <text
                      x={peakPoint.x}
                      y={margin.top + 28}
                      fill={COLORS.hglFlow.light}
                      fontSize="11"
                      textAnchor="middle"
                      fontWeight={600}
                    >
                      ↑ {peakPoint.y.toFixed(0)}
                    </text>
                  </g>
                )}

                {/* Start and end labels */}
                <text
                  x={hglPoints[0].x + 5}
                  y={yScale(Math.min(hglPoints[0].y, maxEl)) - 8}
                  fill={COLORS.hglFlow.light}
                  fontSize="10"
                >
                  HGL: {hglPoints[0].y.toFixed(0)}
                </text>
                <text
                  x={hglPoints[hglPoints.length - 1].x - 5}
                  y={yScale(Math.min(hglPoints[hglPoints.length - 1].y, maxEl)) - 8}
                  fill={COLORS.hglFlow.light}
                  fontSize="10"
                  textAnchor="end"
                >
                  HGL: {hglPoints[hglPoints.length - 1].y.toFixed(0)}
                </text>
              </g>
            );
          })()}

          {/* Connection lines between components */}
          {processedSegments.map((segment, segIdx) => {
            const startX = xScale(segment.startCompIndex);
            const endX = xScale(segment.endCompIndex);
            const startEl = segment.startComp.p2_el || segment.startComp.p1_el;
            const endEl = segment.endComp.p1_el;
            const totalWidth = endX - startX;

            if (segment.connections.length === 0) {
              // Direct line if no connections
              return (
                <line
                  key={`direct-${segIdx}`}
                  x1={startX}
                  y1={yScale(startEl)}
                  x2={endX}
                  y2={yScale(endEl)}
                  stroke={COLORS.conn.fill}
                  strokeWidth={3}
                  strokeLinecap="round"
                  opacity={0.7}
                />
              );
            }

            const numConns = segment.connections.length;
            const isSeries = numConns > 1;
            const connElements = [];
            const allPathPoints = [];

            // Calculate proportional widths for each connection based on length
            const segmentTotalLength = segment.segmentLength || segment.connections.reduce((sum, c) => sum + (c.length || 1), 0);
            const getConnWidth = (conn) => ((conn.length || 1) / segmentTotalLength) * totalWidth;

            // Calculate cumulative x positions for each connection
            const connXPositions = [];
            let cumX = startX;
            segment.connections.forEach((conn, i) => {
              connXPositions.push({
                startX: cumX,
                endX: cumX + getConnWidth(conn),
              });
              cumX += getConnWidth(conn);
            });

            if (!isSeries) {
              // SINGLE CONNECTION: 3-piece (horiz-vert-horiz)
              const conn = segment.connections[0];
              const p1El = conn.p1_el;
              const p2El = conn.p2_el || conn.p1_el;
              const midX = (startX + endX) / 2;

              // Start from component
              allPathPoints.push({ x: startX, y: yScale(startEl) });
              // Horizontal to mid at start elevation
              allPathPoints.push({ x: midX, y: yScale(startEl) });
              // If start != p1, vertical to p1
              if (startEl !== p1El) {
                allPathPoints.push({ x: midX, y: yScale(p1El) });
              }
              // If p1 != p2, vertical to p2
              if (p1El !== p2El) {
                allPathPoints.push({ x: midX, y: yScale(p2El) });
              }
              // If p2 != end, need to get to end elevation
              if (p2El !== endEl) {
                allPathPoints.push({ x: midX, y: yScale(endEl) });
              }
              // Horizontal to end component
              allPathPoints.push({ x: endX, y: yScale(endEl) });

              // Hover and min/max for single connection
              const isHovered = hoveredItem?.type === 'conn' && hoveredItem?.index === conn.originalIndex;
              const horizY = yScale((p1El + p2El) / 2);

              connElements.push(
                <g key={`conn-hover-${segIdx}-0`}>
                  <path
                    d={allPathPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')}
                    stroke="transparent"
                    strokeWidth={20}
                    fill="none"
                    className="connection-hitbox"
                    onMouseEnter={() => setHoveredItem({
                      type: 'conn',
                      index: conn.originalIndex,
                      data: conn,
                      x: midX,
                      y: horizY
                    })}
                    onMouseLeave={() => setHoveredItem(null)}
                  />
                  {isHovered && (
                    <path
                      d={allPathPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')}
                      stroke={COLORS.water.fill}
                      strokeWidth={5}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                      opacity={1}
                      style={{ pointerEvents: 'none' }}
                    />
                  )}
                  {showMinMax && (conn.min_el || conn.max_el) && (
                    <g>
                      {conn.min_el && (
                        <>
                          <line
                            x1={midX}
                            y1={yScale(Math.min(p1El, p2El))}
                            x2={midX}
                            y2={yScale(conn.min_el)}
                            stroke={COLORS.accent}
                            strokeWidth={2}
                            strokeDasharray="4,2"
                            opacity={0.7}
                          />
                          <circle cx={midX} cy={yScale(conn.min_el)} r={4} fill={COLORS.accent} />
                          <text x={midX + 8} y={yScale(conn.min_el)} fill={COLORS.accent} fontSize="10" dominantBaseline="middle">
                            low: {conn.min_el}
                          </text>
                        </>
                      )}
                      {conn.max_el && (
                        <>
                          <line
                            x1={midX}
                            y1={yScale(Math.max(p1El, p2El))}
                            x2={midX}
                            y2={yScale(conn.max_el)}
                            stroke={COLORS.accent}
                            strokeWidth={2}
                            strokeDasharray="4,2"
                            opacity={0.7}
                          />
                          <circle cx={midX} cy={yScale(conn.max_el)} r={4} fill={COLORS.accent} />
                          <text x={midX + 8} y={yScale(conn.max_el)} fill={COLORS.accent} fontSize="10" dominantBaseline="middle">
                            high: {conn.max_el}
                          </text>
                        </>
                      )}
                    </g>
                  )}
                </g>
              );
            } else {
              // SERIES CONNECTIONS: 2-piece composition for each
              // Direction based on: if rising (max_el > p2_el > p1_el or just p2 > p1), use vert-horiz
              // Otherwise use horiz-vert

              // Start point
              allPathPoints.push({ x: startX, y: yScale(startEl) });

              segment.connections.forEach((conn, connIdx) => {
                const { startX: connStartX, endX: connEndX } = connXPositions[connIdx];
                const p1El = conn.p1_el;
                const p2El = conn.p2_el || conn.p1_el;

                // Determine if this connection is "rising"
                // Rising: p2 > p1 (and optionally max_el > p2 if exists)
                const isRising = p2El > p1El || (conn.max_el && conn.max_el > p2El && p2El >= p1El);

                if (isRising) {
                  // Vertical-Horizontal: go up first, then horizontal at p2
                  // Vertical from current position to p2
                  allPathPoints.push({ x: connStartX, y: yScale(p2El) });
                  // Horizontal at p2 elevation to end of this connection's region
                  allPathPoints.push({ x: connEndX, y: yScale(p2El) });
                } else {
                  // Horizontal-Vertical: horizontal at p1, then down
                  // Horizontal at p1 elevation
                  allPathPoints.push({ x: connEndX, y: yScale(p1El) });
                  // Vertical to p2
                  if (p2El !== p1El) {
                    allPathPoints.push({ x: connEndX, y: yScale(p2El) });
                  }
                }
              });

              // Final connection to end component
              const lastConn = segment.connections[numConns - 1];
              const lastP2 = lastConn.p2_el || lastConn.p1_el;
              if (lastP2 !== endEl) {
                allPathPoints.push({ x: endX, y: yScale(lastP2) });
                allPathPoints.push({ x: endX, y: yScale(endEl) });
              } else {
                allPathPoints.push({ x: endX, y: yScale(endEl) });
              }

              // Create hover areas for each connection in series
              segment.connections.forEach((conn, connIdx) => {
                const isHovered = hoveredItem?.type === 'conn' && hoveredItem?.index === conn.originalIndex;
                const { startX: connStartX, endX: connEndX } = connXPositions[connIdx];
                const p1El = conn.p1_el;
                const p2El = conn.p2_el || conn.p1_el;
                const isRising = p2El > p1El || (conn.max_el && conn.max_el > p2El && p2El >= p1El);

                // Build hover path for this connection
                const hoverPoints = [];
                const prevEl = connIdx === 0 ? startEl : (segment.connections[connIdx - 1].p2_el || segment.connections[connIdx - 1].p1_el);

                if (isRising) {
                  // Vert-Horiz
                  hoverPoints.push({ x: connStartX, y: yScale(prevEl) });
                  hoverPoints.push({ x: connStartX, y: yScale(p2El) });
                  hoverPoints.push({ x: connEndX, y: yScale(p2El) });
                } else {
                  // Horiz-Vert
                  hoverPoints.push({ x: connStartX, y: yScale(prevEl) });
                  hoverPoints.push({ x: connEndX, y: yScale(p1El) });
                  if (p2El !== p1El) {
                    hoverPoints.push({ x: connEndX, y: yScale(p2El) });
                  }
                }

                const hoverPathD = hoverPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

                // Min/max indicator position: on the horizontal segment
                const horizMidX = (connStartX + connEndX) / 2;
                const horizEl = isRising ? p2El : p1El;

                connElements.push(
                  <g key={`conn-hover-${segIdx}-${connIdx}`}>
                    <path
                      d={hoverPathD}
                      stroke="transparent"
                      strokeWidth={20}
                      fill="none"
                      className="connection-hitbox"
                      onMouseEnter={() => setHoveredItem({
                        type: 'conn',
                        index: conn.originalIndex,
                        data: conn,
                        x: horizMidX,
                        y: yScale(horizEl)
                      })}
                      onMouseLeave={() => setHoveredItem(null)}
                    />
                    {isHovered && (
                      <path
                        d={hoverPathD}
                        stroke={COLORS.water.fill}
                        strokeWidth={5}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        fill="none"
                        opacity={1}
                        style={{ pointerEvents: 'none' }}
                      />
                    )}
                    {showMinMax && (conn.min_el || conn.max_el) && (
                      <g>
                        {conn.min_el && (
                          <>
                            <line
                              x1={horizMidX}
                              y1={yScale(horizEl)}
                              x2={horizMidX}
                              y2={yScale(conn.min_el)}
                              stroke={COLORS.accent}
                              strokeWidth={2}
                              strokeDasharray="4,2"
                              opacity={0.7}
                            />
                            <circle cx={horizMidX} cy={yScale(conn.min_el)} r={4} fill={COLORS.accent} />
                            <text x={horizMidX + 8} y={yScale(conn.min_el)} fill={COLORS.accent} fontSize="10" dominantBaseline="middle">
                              low: {conn.min_el}
                            </text>
                          </>
                        )}
                        {conn.max_el && (
                          <>
                            <line
                              x1={horizMidX}
                              y1={yScale(horizEl)}
                              x2={horizMidX}
                              y2={yScale(conn.max_el)}
                              stroke={COLORS.accent}
                              strokeWidth={2}
                              strokeDasharray="4,2"
                              opacity={0.7}
                            />
                            <circle cx={horizMidX} cy={yScale(conn.max_el)} r={4} fill={COLORS.accent} />
                            <text x={horizMidX + 8} y={yScale(conn.max_el)} fill={COLORS.accent} fontSize="10" dominantBaseline="middle">
                              high: {conn.max_el}
                            </text>
                          </>
                        )}
                      </g>
                    )}
                  </g>
                );
              });
            }

            const fullPathD = allPathPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

            // Boundary markers for series connections - positioned proportionally
            const boundaryMarkers = segment.boundaries.map((boundary, bIdx) => {
              const afterIdx = boundary.afterConnectionIndex;
              const boundaryX = connXPositions[afterIdx].endX;

              return (
                <circle
                  key={`boundary-${segIdx}-${bIdx}`}
                  cx={boundaryX}
                  cy={yScale(boundary.elevation)}
                  r={5}
                  fill="#000"
                  stroke="#fff"
                  strokeWidth={1.5}
                />
              );
            });

            return (
              <g key={`segment-${segIdx}`}>
                <path
                  d={fullPathD}
                  stroke={COLORS.conn.fill}
                  strokeWidth={3}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                  opacity={0.7}
                  style={{ pointerEvents: 'none' }}
                />
                {connElements}
                {boundaryMarkers}
              </g>
            );
          })}

          {/* Min/Max ranges for components (tanks) */}
          {showMinMax && components.map((item, i) => {
            const x = xScale(i);

            if (item.min_el && item.max_el) {
              // For destination tanks, show losses bar from port to min
              const isDestTank = i > 0 && item.p1_el;
              // In elevation terms: higher elevation = smaller y pixel value
              // So we need the higher elevation for y (top of rect) and calculate height to lower elevation
              const lossesBarTopEl = isDestTank ? Math.max(item.p1_el, item.min_el) : null;
              const lossesBarBottomEl = isDestTank ? Math.min(item.p1_el, item.min_el) : null;

              return (
                <g key={`range-${i}`}>
                  <rect
                    x={x - 20}
                    y={yScale(item.max_el)}
                    width={40}
                    height={yScale(item.min_el) - yScale(item.max_el)}
                    fill={COLORS.water.fill}
                    opacity={0.25}
                    rx={4}
                    className="pulse"
                  />
                  <line
                    x1={x - 20}
                    y1={yScale(item.max_el)}
                    x2={x + 20}
                    y2={yScale(item.max_el)}
                    stroke={COLORS.water.stroke}
                    strokeWidth={2}
                    strokeDasharray="6,3"
                  />
                  <line
                    x1={x - 20}
                    y1={yScale(item.min_el)}
                    x2={x + 20}
                    y2={yScale(item.min_el)}
                    stroke={COLORS.water.stroke}
                    strokeWidth={2}
                    strokeDasharray="6,3"
                  />
                  <text x={x + 25} y={yScale(item.max_el)} fill="#7dd3fc" fontSize="10" dominantBaseline="middle">max</text>
                  <text x={x + 25} y={yScale(item.min_el)} fill="#7dd3fc" fontSize="10" dominantBaseline="middle">min</text>

                  {/* Narrow vertical losses bar from port to min elevation for destination tanks */}
                  {isDestTank && lossesBarTopEl !== lossesBarBottomEl && (
                    <rect
                      x={x - 4}
                      y={yScale(lossesBarTopEl)}
                      width={8}
                      height={yScale(lossesBarBottomEl) - yScale(lossesBarTopEl)}
                      fill={COLORS.hglFlow.fill}
                      opacity={0.5}
                      rx={2}
                    />
                  )}
                </g>
              );
            }
            return null;
          })}

          {/* Component markers */}
          {components.map((item, i) => {
            const colors = getComponentColor(item.name);
            const x = xScale(i);
            const originalIndex = data.indexOf(item);
            const isHovered = hoveredItem?.type === 'comp' && hoveredItem?.index === originalIndex;
            const isPump = item.name.includes('pmp');
            const p1Y = yScale(item.p1_el);
            const p2Y = item.p2_el ? yScale(item.p2_el) : p1Y;

            return (
              <g
                key={`comp-${i}`}
                className="component-marker"
                onMouseEnter={() => setHoveredItem({ type: 'comp', index: originalIndex, data: item, x, y: yScale(item.p1_el) })}
                onMouseLeave={() => setHoveredItem(null)}
                style={{ color: colors.fill }}
              >
                {/* Pump linear flow arrows */}
                {isPump && (
                  <g>
                    <defs>
                      <clipPath id={`pump-clip-${i}`}>
                        <rect x={x - 12} y={p2Y - 5} width={24} height={p1Y - p2Y + 10} />
                      </clipPath>
                    </defs>
                    <g clipPath={`url(#pump-clip-${i})`}>
                      {[0, 0.33, 0.66].map((delay, arrowIdx) => (
                        <g
                          key={arrowIdx}
                          className="pump-flow-arrow"
                          style={{ animationDelay: `${delay}s` }}
                        >
                          <path
                            d={`M ${x - 5} ${p1Y + 5} L ${x} ${p1Y - 2} L ${x + 5} ${p1Y + 5}`}
                            fill="none"
                            stroke={colors.light}
                            strokeWidth={2}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </g>
                      ))}
                    </g>
                  </g>
                )}

                {/* P1 marker */}
                {item.p1_el && (
                  <circle
                    cx={x}
                    cy={yScale(item.p1_el)}
                    r={8}
                    fill={colors.fill}
                    stroke={isHovered ? '#fff' : colors.stroke}
                    strokeWidth={isHovered ? 3 : 2}
                  />
                )}

                {/* P2 marker (if different from P1) */}
                {item.p2_el && item.p2_el !== item.p1_el && (
                  <>
                    <line
                      x1={x}
                      y1={yScale(item.p1_el)}
                      x2={x}
                      y2={yScale(item.p2_el)}
                      stroke={colors.fill}
                      strokeWidth={3}
                    />
                    <circle
                      cx={x}
                      cy={yScale(item.p2_el)}
                      r={8}
                      fill={colors.fill}
                      stroke={isHovered ? '#fff' : colors.stroke}
                      strokeWidth={isHovered ? 3 : 2}
                    />
                  </>
                )}

                {/* Item name label */}
                <text
                  x={x}
                  y={height - margin.bottom + 20}
                  fill={COLORS.text}
                  fontSize="12"
                  textAnchor="middle"
                  fontWeight={isHovered ? 700 : 500}
                >
                  {item.name}
                </text>
                <text
                  x={x}
                  y={height - margin.bottom + 36}
                  fill="#64748b"
                  fontSize="10"
                  textAnchor="middle"
                >
                  {item.type}
                </text>
              </g>
            );
          })}

          {/* Hover tooltip */}
          {hoveredItem && (
            <g className="tooltip">
              <rect
                x={hoveredItem.x - 70}
                y={hoveredItem.y - 75}
                width={140}
                height={
                  (hoveredItem.data.min_el || hoveredItem.data.max_el ? 16 : 0) +
                  (hoveredItem.data.length ? 16 : 0) +
                  (hoveredItem.data.head_change !== undefined ? 16 : 0) +
                  46
                }
                fill="#1e293b"
                stroke={hoveredItem.type === 'comp' ? getComponentColor(hoveredItem.data.name).fill : COLORS.water.fill}
                strokeWidth={2}
                rx={6}
              />
              <text
                x={hoveredItem.x}
                y={hoveredItem.y - 57}
                fill={COLORS.text}
                fontSize="12"
                textAnchor="middle"
                fontWeight={600}
              >
                {hoveredItem.data.name}
              </text>
              <text
                x={hoveredItem.x}
                y={hoveredItem.y - 41}
                fill="#94a3b8"
                fontSize="10"
                textAnchor="middle"
              >
                P1: {hoveredItem.data.p1_el} {hoveredItem.data.p2_el ? `| P2: ${hoveredItem.data.p2_el}` : ''}
              </text>
              {hoveredItem.data.length && (
                <text
                  x={hoveredItem.x}
                  y={hoveredItem.y - 25}
                  fill="#94a3b8"
                  fontSize="10"
                  textAnchor="middle"
                >
                  Length: {hoveredItem.data.length} ft
                </text>
              )}
              {hoveredItem.data.head_change !== undefined && (
                <text
                  x={hoveredItem.x}
                  y={hoveredItem.y - (hoveredItem.data.length ? 9 : 25)}
                  fill={hoveredItem.data.head_change >= 0 ? COLORS.hglFlow.light : '#f87171'}
                  fontSize="10"
                  textAnchor="middle"
                >
                  ΔH: {hoveredItem.data.head_change >= 0 ? '+' : ''}{hoveredItem.data.head_change} ft
                </text>
              )}
              {(hoveredItem.data.min_el || hoveredItem.data.max_el) && (
                <text
                  x={hoveredItem.x}
                  y={hoveredItem.y - (hoveredItem.data.length && hoveredItem.data.head_change !== undefined ? -7 : (hoveredItem.data.length || hoveredItem.data.head_change !== undefined ? 9 : 25))}
                  fill={COLORS.accent}
                  fontSize="10"
                  textAnchor="middle"
                >
                  {hoveredItem.data.min_el ? `Min: ${hoveredItem.data.min_el}` : ''} {hoveredItem.data.max_el ? `Max: ${hoveredItem.data.max_el}` : ''}
                </text>
              )}
            </g>
          )}

          {/* Flow direction arrow removed */}
        </svg>

        {/* Data table */}
        <div style={{
          marginTop: '24px',
          overflowX: 'auto',
        }}>
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '13px',
          }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
                {['Type', 'Name', 'Length', 'ΔH (ft)', 'Min El', 'Max El', 'P1 El', 'P2 El'].map(h => (
                  <th key={h} style={{
                    padding: '12px 16px',
                    textAlign: 'left',
                    color: COLORS.text,
                    fontWeight: 600,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((item, i) => {
                const colors = getComponentColor(item.name);
                const isHovered = hoveredItem?.index === i;
                return (
                  <tr
                    key={i}
                    style={{
                      borderBottom: '1px solid rgba(148, 163, 184, 0.1)',
                      background: isHovered ? 'rgba(148, 163, 184, 0.1)' : 'transparent',
                    }}
                    onMouseEnter={() => setHoveredItem({
                      type: item.type,
                      index: i,
                      data: item,
                      x: item.type === 'comp' ? xScale(components.indexOf(item)) : width / 2,
                      y: yScale(item.p1_el)
                    })}
                    onMouseLeave={() => setHoveredItem(null)}
                  >
                    <td style={{ padding: '10px 16px', color: '#94a3b8' }}>{item.type}</td>
                    <td style={{ padding: '10px 16px', color: colors.fill, fontWeight: 600 }}>{item.name}</td>
                    <td style={{ padding: '10px 16px', color: item.length ? COLORS.text : '#475569' }}>
                      {item.length ?? '—'}
                    </td>
                    <td style={{
                      padding: '10px 16px',
                      color: item.head_change > 0 ? COLORS.hglFlow.fill : (item.head_change < 0 ? '#f87171' : '#475569'),
                      fontWeight: item.head_change !== 0 ? 600 : 400
                    }}>
                      {item.head_change !== undefined ? (item.head_change >= 0 ? '+' : '') + item.head_change : '—'}
                    </td>
                    <td style={{ padding: '10px 16px', color: item.min_el ? COLORS.accent : '#475569' }}>
                      {item.min_el ?? '—'}
                    </td>
                    <td style={{ padding: '10px 16px', color: item.max_el ? COLORS.accent : '#475569' }}>
                      {item.max_el ?? '—'}
                    </td>
                    <td style={{ padding: '10px 16px', color: COLORS.text }}>{item.p1_el ?? '—'}</td>
                    <td style={{ padding: '10px 16px', color: COLORS.text }}>{item.p2_el ?? '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
