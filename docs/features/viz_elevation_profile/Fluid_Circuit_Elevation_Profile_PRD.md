# Fluid Circuit Elevation Profile Visualization

## Product Requirements Document (PRD)

Version 1.0 | February 2025

---

## 1. Executive Summary

This document describes a visualization component for displaying fluid circuit elevation profiles. The visualization renders hydraulic system schematics showing physical pipe elevations, component positions, hydraulic grade lines (HGL), and head losses across a pumping system. It is designed to integrate with pump operating point calculation tools to provide visual feedback on system hydraulics.

---

## 2. Purpose and Scope

### 2.1 Primary Objectives

- Visualize physical elevations of pipes, tanks, valves, and pumps in a fluid system
- Display hydraulic grade lines for both static (no-flow) and flowing conditions
- Show head losses and gains across each system component
- Provide interactive hover tooltips with detailed component information
- Scale horizontal positioning proportionally to pipe lengths

### 2.2 Target Integration

This visualization is intended to integrate with pump system analysis software that calculates operating points and head losses. The host application provides the data model; this component renders the visual representation.

---

## 3. Data Model

### 3.1 Element Types

The system consists of two primary element types:

| Type | Examples | Description |
|------|----------|-------------|
| `comp` | tank, valve, pump | Physical components with discrete locations |
| `conn` | pipe, conduit | Connections (piping) between components |

### 3.2 Data Structure

Each element in the system is represented as an object with the following properties:

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `type` | string | Yes | `'comp'` or `'conn'` |
| `name` | string | Yes | Unique identifier (e.g., `'tnk-1'`, `'pmp-1'`, `'cx-3'`) |
| `p1_el` | number | Yes | Elevation at port 1 (upstream connection point) |
| `p2_el` | number | No | Elevation at port 2 (downstream connection point) |
| `min_el` | number | No | Minimum elevation (tank level or pipe low point) |
| `max_el` | number | No | Maximum elevation (tank level or pipe high point) |
| `length` | number | Conn only | Pipe length (determines x-axis scaling) |
| `head_change` | number | No | Head loss (negative) or gain (positive) across element |

### 3.3 Example Data

```javascript
const data = [
  { type: 'comp', name: 'tnk-1', min_el: 650, max_el: 675,
    p1_el: 655, p2_el: null, head_change: -2 },
  { type: 'conn', name: 'cx-1', p1_el: 655, p2_el: 655,
    length: 50, head_change: -1 },
  { type: 'comp', name: 'vlv-1', p1_el: 655, p2_el: 655,
    head_change: -5 },
  { type: 'conn', name: 'cx-2', p1_el: 655, p2_el: 645,
    length: 120, head_change: -3 },
  { type: 'comp', name: 'pmp-1', p1_el: 645, p2_el: 655,
    head_change: 85 },
  { type: 'conn', name: 'cx-3', min_el: 640, p1_el: 655,
    p2_el: 660, length: 200, head_change: -4 },
  { type: 'conn', name: 'cx-4', max_el: 700, p1_el: 660,
    p2_el: 675, length: 350, head_change: -50 },
  { type: 'comp', name: 'tank-2', min_el: 680, max_el: 690,
    p1_el: 675, p2_el: null, head_change: -5 }
];
```

---

## 4. Visual Elements

### 4.1 Component Markers

Components are displayed as circular markers at their port elevations:

| Component | Color | Visual Behavior |
|-----------|-------|-----------------|
| Tank (`tnk-`, `tank-`) | Blue (`#2563eb`) | Pulsing rectangle showing min/max water levels |
| Valve (`vlv-`) | Green (`#059669`) | Static circular marker at port elevation |
| Pump (`pmp-`) | Red (`#dc2626`) | Animated arrows indicating flow direction |

**Marker Sizes:**

- Component port markers: radius = 8px
- Connection boundary markers: radius = 5px (black with white stroke)

### 4.2 Connection Lines

Pipe connections are rendered as gray lines (`#64748b`) between components. The rendering logic differs based on whether connections are single or in series:

#### Single Connection (between two components)

- **3-piece composition:** horizontal → vertical → horizontal
- Vertical transition occurs at the midpoint between components
- Min/max elevation indicators shown at the vertical section

#### Series Connections (multiple pipes between components)

- **2-piece composition** for each connection segment
- Direction determined by elevation change:
  - **Rising** (`p2 > p1` or `max_el` exists above `p2`): vertical-first → horizontal
  - **Falling** (`p2 < p1`): horizontal-first → vertical
- Black circular markers at boundaries between series connections

### 4.3 Hydraulic Grade Lines (HGL)

#### No-Flow HGL (Purple, dashed - `#a855f7`)

- Horizontal line at source tank `max_el` on upstream side
- Vertical jump at check valves, closed valves, or pumps with check valves
- Horizontal line at destination tank `max_el` on downstream side

#### Flowing HGL (Green, solid - `#22c55e`)

- Starts at source tank `max_el` (water surface)
- Decreases through losses (negative `head_change` values)
- Increases through pump (positive `head_change` value)
- **When HGL exceeds y-axis range:**
  - Dotted line appears along top of plot area
  - Arrow indicator shows peak value with numeric label

### 4.4 Tank Visualizations

#### Water Level Range

- Pulsing blue rectangle between `min_el` and `max_el`
- Dashed lines at min and max elevations with labels

#### Destination Tank Losses Bar

- Narrow green vertical bar at destination tanks (width = 8px)
- **If port below `min_el`:** extends from port elevation up to `min_el`
- **If port above `max_el`:** extends from `max_el` up to port elevation
- Represents entry/exit losses at the tank connection

### 4.5 Min/Max Elevation Indicators

- Amber/orange color (`#f59e0b`)
- Dashed line from pipe elevation to extreme point
- Small circle marker (radius = 4px) at the extreme elevation
- Label showing `"low: [value]"` or `"high: [value]"`

---

## 5. User Interactions

### 5.1 Hover Tooltips

Hovering over any component or connection displays a tooltip containing:

- Element name
- Port elevations (P1, P2)
- Length (for connections)
- Head change (ΔH) with color coding:
  - Green for gains (positive)
  - Red for losses (negative)
- Min/max elevations (if applicable)

### 5.2 Toggle Controls

Checkbox controls allow users to show/hide:

- Min/Max elevation indicators
- No-Flow HGL
- Flowing HGL

### 5.3 Visual Feedback

- Hovered components show increased brightness and glow effect
- Hovered connections highlight in blue with increased stroke width
- Data table rows highlight when corresponding element is hovered

---

## 6. Scaling and Layout

### 6.1 X-Axis (Horizontal Position)

- Components positioned based on **cumulative pipe lengths**
- X-axis labels appear only for components (not connections)
- Within series connections, segments sized proportionally to individual lengths

**Pseudo-code:**

```text
xScale(componentIndex) =
    marginLeft + (cumulativeLength / totalLength) * plotWidth
```

### 6.2 Y-Axis (Elevation)

- Auto-scaled based on all elevation values in dataset
- Padding of ±10 units added to min/max range
- Grid lines at intervals of 10 units
- Major grid lines (solid) at multiples of 50
- Minor grid lines (dashed) at other intervals

### 6.3 HGL Clipping Behavior

When the flowing HGL exceeds the visible y-axis range:

1. Solid line segments are clipped at the plot boundary
2. A **dotted line** appears along the top edge where HGL is out of range
3. An **upward-pointing arrow** indicates the peak location
4. The actual **peak value** is displayed numerically

---

## 7. Implementation Pseudo-code

### 7.1 Data Processing

```text
FUNCTION processSystemData(data):
    components = FILTER data WHERE type == 'comp'

    // Calculate cumulative lengths for x-positioning
    componentPositions = []
    cumulativeLength = 0

    FOR each item IN data:
        IF item.type == 'comp':
            componentPositions.APPEND({
                component: item,
                cumulativeLength: cumulativeLength
            })
        ELSE IF item.type == 'conn':
            cumulativeLength += item.length OR 0

    totalLength = cumulativeLength

    // Build segments between components
    segments = []
    currentSegment = null

    FOR each item IN data:
        IF item.type == 'comp':
            IF currentSegment != null:
                currentSegment.endComp = item
                segments.APPEND(currentSegment)
            currentSegment = {
                startComp: item,
                connections: []
            }
        ELSE IF item.type == 'conn':
            currentSegment.connections.APPEND(item)

    // Identify boundaries in series connections
    FOR each segment IN segments:
        IF segment.connections.length > 1:
            segment.boundaries = []
            FOR i = 0 TO segment.connections.length - 2:
                boundaryEl = segment.connections[i].p2_el
                segment.boundaries.APPEND({
                    elevation: boundaryEl,
                    afterIndex: i
                })

    RETURN { components, segments, totalLength, componentPositions }
```

### 7.2 Connection Line Rendering

```text
FUNCTION renderConnectionSegment(segment):
    startX = xScale(segment.startCompIndex)
    endX = xScale(segment.endCompIndex)
    startEl = segment.startComp.p2_el OR segment.startComp.p1_el
    endEl = segment.endComp.p1_el
    isSeries = segment.connections.length > 1

    IF NOT isSeries:
        // Single connection: 3-piece (horiz-vert-horiz)
        midX = (startX + endX) / 2

        path = [
            POINT(startX, startEl),
            POINT(midX, startEl),
            POINT(midX, conn.p1_el),      // if different
            POINT(midX, conn.p2_el),      // if different
            POINT(midX, endEl),           // if different
            POINT(endX, endEl)
        ]

    ELSE:
        // Series connections: 2-piece each
        path = [POINT(startX, startEl)]

        FOR each conn IN segment.connections:
            isRising = conn.p2_el > conn.p1_el OR
                      (conn.max_el EXISTS AND conn.max_el > conn.p2_el)

            IF isRising:
                // Vertical first, then horizontal
                path.APPEND(POINT(connStartX, conn.p2_el))
                path.APPEND(POINT(connEndX, conn.p2_el))
            ELSE:
                // Horizontal first, then vertical
                path.APPEND(POINT(connEndX, conn.p1_el))
                IF conn.p2_el != conn.p1_el:
                    path.APPEND(POINT(connEndX, conn.p2_el))

        path.APPEND(POINT(endX, endEl))

    RETURN path
```

### 7.3 Flowing HGL Calculation

```text
FUNCTION calculateFlowingHGL(data, components):
    firstTank = FIND IN data WHERE name CONTAINS 'tnk' OR 'tank'
    currentHGL = firstTank.max_el
    hglPoints = []
    cumulativeLength = 0

    FOR each item IN data:
        IF item.type == 'comp':
            x = xScale(componentIndex)

            // Point before head change
            hglPoints.APPEND({ x: x, y: currentHGL })

            // Apply head change
            currentHGL += item.head_change OR 0

            // Point after head change
            hglPoints.APPEND({ x: x, y: currentHGL })

        ELSE IF item.type == 'conn':
            startX = calculateX(cumulativeLength)
            cumulativeLength += item.length
            endX = calculateX(cumulativeLength)

            hglPoints.APPEND({ x: startX, y: currentHGL })
            currentHGL += item.head_change OR 0
            hglPoints.APPEND({ x: endX, y: currentHGL })

    RETURN hglPoints
```

### 7.4 HGL Clipping Logic

```text
FUNCTION renderClippedHGL(hglPoints, maxEl, minEl):
    visibleSegments = []
    currentSegment = []

    FOR i = 0 TO hglPoints.length - 1:
        point = hglPoints[i]
        prevPoint = hglPoints[i - 1] IF i > 0

        IF prevPoint EXISTS:
            wasInRange = prevPoint.y >= minEl AND prevPoint.y <= maxEl
            isInRange = point.y >= minEl AND point.y <= maxEl

            IF wasInRange AND NOT isInRange:
                // Leaving visible range - find intersection
                intersection = calculateIntersection(prevPoint, point, maxEl)
                currentSegment.APPEND(intersection)
                visibleSegments.APPEND(currentSegment)
                currentSegment = []

            ELSE IF NOT wasInRange AND isInRange:
                // Entering visible range - find intersection
                intersection = calculateIntersection(prevPoint, point, maxEl)
                currentSegment = [intersection]

        IF isInRange:
            currentSegment.APPEND(point)

    // Render dotted line where HGL exceeds range
    FOR i = 1 TO hglPoints.length - 1:
        IF hglPoints[i-1].y > maxEl OR hglPoints[i].y > maxEl:
            RENDER dottedLine FROM hglPoints[i-1].x TO hglPoints[i].x AT y = maxEl

    RETURN visibleSegments
```

---

## 8. Animations

### 8.1 Tank Water Level Pulse

```css
@keyframes pulse {
    0%, 100% { opacity: 0.4; }
    50%      { opacity: 0.8; }
}

.tank-water {
    animation: pulse 2s infinite;
}
```

### 8.2 Pump Flow Arrows

```css
@keyframes pumpFlowLinear {
    0%   { opacity: 0; transform: translateY(100%); }
    20%  { opacity: 1; }
    80%  { opacity: 1; }
    100% { opacity: 0; transform: translateY(-100%); }
}

.pump-flow-arrow {
    animation: pumpFlowLinear 3s infinite linear;
}

/* Three arrows staggered at 0s, 1s, 2s delays */
/* Creates continuous upward flow effect */
```

---

## 9. Color Palette

| Element | Hex Code | Usage |
|---------|----------|-------|
| Tank | `#2563eb` | Tank markers, water level range |
| Valve | `#059669` | Valve markers |
| Pump | `#dc2626` | Pump markers, flow arrows |
| Connection/Pipe | `#64748b` | Pipe lines |
| HGL (No Flow) | `#a855f7` | Static hydraulic grade line |
| HGL (Flowing) | `#22c55e` | Dynamic hydraulic grade line |
| Min/Max Indicator | `#f59e0b` | Elevation extremes |
| Boundary Marker | `#000000` | Series connection boundaries |
| Background | `#0f172a` | Dark theme background |
| Text | `#f1f5f9` | Labels, axis text |
| Grid (major) | `#334155` | 50-unit grid lines |
| Grid (minor) | `#334155` | 10-unit grid lines (dashed, 20% opacity) |

---

## 10. Edge Cases and Special Conditions

### 10.1 Tank Port Position

| Condition | Behavior |
|-----------|----------|
| Port below tank `min_el` | Show losses bar from port up to `min_el` |
| Port above tank `max_el` | Show losses bar from `max_el` up to port |
| Port within tank range | No losses bar needed |

### 10.2 HGL Jump Conditions

The no-flow HGL jumps at:

- Pumps (assumed to have check valves)
- Check valves (if explicitly modeled)
- Closed valves (if state is tracked)

### 10.3 Missing Data Handling

| Missing Property | Default Behavior |
|------------------|------------------|
| `p2_el` | Use `p1_el` for both ports |
| `length` | Use 0 (component positioned at same x as previous) |
| `head_change` | Treat as 0 (no change) |
| `min_el` / `max_el` | Don't render range indicators |

### 10.4 Series vs Single Connection Detection

```text
isSeries = segment.connections.length > 1
```

- **Single:** Use 3-piece horizontal-vertical-horizontal rendering
- **Series:** Use 2-piece rendering per connection with boundary markers

---

## 11. Integration Guidelines

### 11.1 Required Inputs

- Array of element objects following the data model schema
- Elements must be ordered from upstream to downstream
- First element should be source tank, last should be destination tank

### 11.2 Optional Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `width` | number | 900 | Canvas width in pixels |
| `height` | number | 500 | Canvas height in pixels |
| `margin` | object | `{top:60, right:40, bottom:80, left:70}` | Plot margins |
| `showMinMax` | boolean | `true` | Initial state of min/max toggle |
| `showHGL` | boolean | `true` | Initial state of no-flow HGL toggle |
| `showFlowingHGL` | boolean | `true` | Initial state of flowing HGL toggle |
| `elevationUnit` | string | `"ft"` | Unit label for y-axis |

### 11.3 Events/Callbacks

| Event | Payload | Description |
|-------|---------|-------------|
| `onElementHover` | `element` object | Triggered when hovering over an element |
| `onElementLeave` | `element` object | Triggered when leaving an element |
| `onElementClick` | `element` object | Triggered when clicking an element |
| `onToggleChange` | `{name, state}` | Triggered when display option changes |

### 11.4 Technology-Agnostic Implementation Notes

This visualization can be implemented in any framework/library that supports:

- SVG or Canvas rendering
- CSS animations (or equivalent)
- Mouse/touch event handling

Key rendering requirements:

- Coordinate system with inverted y-axis (higher elevation = lower pixel value)
- Path/polyline support for connection lines
- Circle/rectangle primitives for markers
- Text rendering with custom fonts
- Clipping or masking for HGL bounds

---

## Appendix A: Visual Layout Reference

```text
┌─────────────────────────────────────────────────────────────────┐
│  Legend: ⬡ Tank  ◈ Valve  ⬢ Pump  ─ Piping  ┄ HGL             │
│                                [✓] Min/Max [✓] HGL [✓] Flowing │
├─────────────────────────────────────────────────────────────────┤
│ 710 ┤                                                           │
│     │              ↑ 749 (peak HGL indicator)                   │
│ 700 ┤         ·····●·····························               │
│     │        ╱    (dotted line = HGL off scale)  ╲              │
│ 690 ┤  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄█max         │
│     │  (purple dashed = no-flow HGL)               █ █          │
│ 680 ┤                                              █min         │
│     │  ┌───┐max                                    █            │
│ 675 ┤  │   │────────────────────────────────●──────█ (green)    │
│     │  │ █ │                               ╱       ●            │
│ 670 ┤  │   │                              ╱                     │
│     │  └───┘min                   ●──────╱                      │
│ 660 ┤        ●                   ╱ ╲                            │
│     │        │                  ╱   (black dot = boundary)      │
│ 655 ┤  ●─────●──●──────●───────╱                                │
│     │  │        │      │      ╱                                 │
│ 650 ┤  │        │      │     ●                                  │
│     │  │        │      │     │                                  │
│ 645 ┤  │        │      ●─────●                                  │
│     │  │        │     (pump with animated arrows ↑)             │
│ 640 ┤  │        │      ▼ low                                    │
│     │                                                           │
├─────┴────────┬────────┬────────┬────────────────────────┬───────┤
│            tnk-1    vlv-1    pmp-1                    tank-2    │
│            comp     comp     comp                     comp      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Type │ Name   │ Length │ ΔH (ft) │ Min El │ Max El │ P1  │ P2  │
├──────┼────────┼────────┼─────────┼────────┼────────┼─────┼─────┤
│ comp │ tnk-1  │   —    │   -2    │  650   │  675   │ 655 │  —  │
│ conn │ cx-1   │   50   │   -1    │   —    │   —    │ 655 │ 655 │
│ comp │ vlv-1  │   —    │   -5    │   —    │   —    │ 655 │ 655 │
│ conn │ cx-2   │  120   │   -3    │   —    │   —    │ 655 │ 645 │
│ comp │ pmp-1  │   —    │  +85    │   —    │   —    │ 645 │ 655 │
│ conn │ cx-3   │  200   │   -4    │  640   │   —    │ 655 │ 660 │
│ conn │ cx-4   │  350   │  -50    │   —    │  700   │ 660 │ 675 │
│ comp │ tank-2 │   —    │   -5    │  680   │  690   │ 675 │  —  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix B: HGL Calculation Trace

For the example data, the flowing HGL progresses as follows:

| Location | HGL Before | ΔH | HGL After |
|----------|------------|-----|-----------|
| tnk-1 (start) | 675 | -2 | 673 |
| cx-1 | 673 | -1 | 672 |
| vlv-1 | 672 | -5 | 667 |
| cx-2 | 667 | -3 | 664 |
| pmp-1 | 664 | +85 | **749** ← Peak (off scale) |
| cx-3 | 749 | -4 | 745 |
| cx-4 | 745 | -50 | 695 |
| tank-2 | 695 | -5 | **690** ← Final (matches tank max) |

**Total head change:** -2 -1 -5 -3 +85 -4 -50 -5 = **+15 ft** (net gain from 675 to 690)

---

End of Document
