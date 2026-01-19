# Component Reference

OpenSolve Pipe supports various hydraulic components. This reference describes each type and its properties.

## Nodes

Nodes are points in your network where pressure and elevation are defined.

### Reservoir

An infinite source of fluid at a fixed head.

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Elevation | Surface elevation | ft |
| Water Level | Level above datum | ft |

**Use when:** Modeling a water supply, large tank, or open-to-atmosphere source.

### Tank

A storage vessel with defined geometry.

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Elevation | Tank base elevation | ft |
| Initial Level | Starting water level | ft |
| Min Level | Minimum allowed level | ft |
| Max Level | Maximum allowed level | ft |
| Diameter | Tank diameter | ft |

**Use when:** Modeling storage tanks, pressure vessels, or accumulation points.

### Junction

A connection point with no associated equipment.

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Elevation | Junction elevation | ft |

**Use when:** Connecting multiple pipes or as a measurement point.

### Sprinkler

A discharge point with a K-factor relationship.

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Elevation | Sprinkler elevation | ft |
| K-Factor | Discharge coefficient | GPM/psi^0.5 |

**Use when:** Modeling sprinkler heads, nozzles, or pressure-dependent discharges.

### Orifice

A fixed opening with known flow characteristics.

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Elevation | Orifice elevation | ft |
| Diameter | Opening diameter | in |
| Cd | Discharge coefficient | - |

**Use when:** Modeling flow restrictions, calibration orifices, or sharp-edged openings.

## Links

Links are components that connect nodes and have flow through them.

### Pump

A device that adds energy to the fluid.

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Pump Curve | Flow vs. head relationship | GPM, ft |
| Speed Ratio | Fraction of rated speed | - |
| Efficiency Curve | Flow vs. efficiency (optional) | GPM, % |

**Pump Curve:** Enter at least 3 points of flow (GPM) vs. head (ft). The solver interpolates between points.

**Use when:** Modeling centrifugal pumps, boosters, or any head-adding device.

### Valves

Control devices that regulate flow or pressure.

#### Gate Valve

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Position | Open percentage | % |

#### Ball Valve

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Position | Open percentage | % |

#### Check Valve

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| K-Factor | Loss coefficient when open | - |

#### Pressure Reducing Valve (PRV)

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Setting | Downstream pressure setpoint | psi |

#### Pressure Sustaining Valve (PSV)

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Setting | Upstream pressure setpoint | psi |

#### Flow Control Valve (FCV)

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| Setting | Target flow rate | GPM |

### Heat Exchanger

A device for heat transfer (modeled as pressure drop only in MVP).

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| K-Factor | Total loss coefficient | - |

### Strainer

A filter element that causes pressure drop.

| Property | Description | Unit |
|----------|-------------|------|
| Name | Component identifier | - |
| K-Factor | Clean strainer loss coefficient | - |

## Piping

Piping connects components and can include fittings.

### Pipe Properties

| Property | Description | Unit |
|----------|-------------|------|
| Material | Pipe material (steel, PVC, etc.) | - |
| Schedule | Pipe schedule (40, 80, etc.) | - |
| Nominal Diameter | Pipe size | in |
| Length | Straight pipe length | ft |
| Roughness | Absolute roughness (auto from material) | in |

### Common Fittings

| Fitting | Typical K-Factor |
|---------|-----------------|
| 90° Elbow (LR) | 0.3 |
| 90° Elbow (SR) | 0.9 |
| 45° Elbow | 0.2 |
| Tee (through) | 0.4 |
| Tee (branch) | 1.0 |
| Reducer (gradual) | 0.1 |
| Expansion (sudden) | 1.0 |
| Gate Valve (full open) | 0.15 |
| Ball Valve (full open) | 0.05 |
| Check Valve (swing) | 2.0 |

## Fluid Properties

### Pre-defined Fluids

- **Water**: Pure water at specified temperature
- **Propylene Glycol**: Various concentrations (25%, 50%)
- **Ethylene Glycol**: Various concentrations (25%, 50%)

### Custom Fluids

You can define custom fluids with:

- Density (lb/ft³)
- Kinematic viscosity (cSt)
- Vapor pressure (psi)

Temperature affects properties for pre-defined fluids. Specify temperature when selecting a fluid.
