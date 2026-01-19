# Getting Started with OpenSolve Pipe

OpenSolve Pipe is a free, browser-based tool for hydraulic network analysis. This guide walks you through your first hydraulic calculation.

## Quick Start

1. **Go to** [OpenSolve Pipe](https://opensolve-pipe.vercel.app/)
2. **Click** "New Project" to start
3. **Add components** using the panel navigator
4. **Click "Solve"** to calculate results

## Your First Project: Simple Pump System

Let's create a basic pump system with a reservoir, pump, pipe, and tank.

### Step 1: Add a Reservoir

1. Click "Add Component"
2. Select "Reservoir" from the list
3. Set the water level (e.g., 10 ft elevation)

### Step 2: Add a Pump

1. Click "Next" or "Add Component"
2. Select "Pump"
3. Enter pump curve data (flow vs. head points):
   - Point 1: 0 GPM @ 100 ft
   - Point 2: 50 GPM @ 95 ft
   - Point 3: 100 GPM @ 85 ft
   - Point 4: 150 GPM @ 70 ft
   - Point 5: 200 GPM @ 50 ft

### Step 3: Add a Pipe

1. Add upstream piping to the pump
2. Configure:
   - Material: Steel
   - Schedule: 40
   - Diameter: 4 inches
   - Length: 100 ft
   - Fittings: 2x 90° elbows

### Step 4: Add a Tank

1. Click "Add Component"
2. Select "Tank"
3. Set the elevation (e.g., 50 ft)

### Step 5: Solve

1. Click the blue "Solve" button (or press Ctrl+Enter)
2. View results:
   - Operating flow rate
   - Operating head
   - Velocities
   - Head losses
   - NPSH available

## Understanding Results

### Convergence Status

- **Green checkmark**: Solution converged successfully
- **Red X**: Solution failed (check warnings)

### Node Results

- **Pressure (psi)**: Gage pressure at each node
- **HGL (ft)**: Hydraulic Grade Line elevation
- **EGL (ft)**: Energy Grade Line elevation

### Link Results

- **Flow (GPM)**: Volume flow rate
- **Velocity (fps)**: Fluid velocity
- **Head Loss (ft)**: Friction and minor losses
- **Reynolds Number**: Flow regime indicator

### Pump Results

- **Operating Point**: Flow and head at intersection
- **System Curve**: Head required vs. flow
- **NPSH Available**: Cavitation margin

## Saving and Sharing

Projects are automatically encoded in the URL. To share:

1. Copy the URL from your browser
2. Send it to anyone
3. They'll see your exact project state

No account required!

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Enter | Solve network |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |

## Next Steps

- Try different pump curves
- Add fittings (elbows, tees, valves)
- Change fluid properties
- Explore multi-path networks (coming soon!)
