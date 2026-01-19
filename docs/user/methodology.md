# Calculation Methodology

This document describes the engineering methods used by OpenSolve Pipe for hydraulic calculations.

## Overview

OpenSolve Pipe solves steady-state, incompressible flow problems using industry-standard methods. All calculations follow established hydraulic engineering principles.

## Fundamental Equations

### Energy Equation (Bernoulli)

For flow between points 1 and 2:

```text
z₁ + P₁/γ + V₁²/2g + Hp = z₂ + P₂/γ + V₂²/2g + hf + hm
```

Where:

- z = elevation (ft)
- P = pressure (lb/ft²)
- γ = specific weight (lb/ft³)
- V = velocity (ft/s)
- g = gravitational acceleration (32.174 ft/s²)
- Hp = pump head added (ft)
- hf = friction head loss (ft)
- hm = minor head loss (ft)

### Darcy-Weisbach Equation

Friction head loss in pipes:

```text
hf = f × (L/D) × (V²/2g)
```

Where:

- f = Darcy friction factor (dimensionless)
- L = pipe length (ft)
- D = pipe internal diameter (ft)
- V = average velocity (ft/s)

### Colebrook-White Equation

For the Darcy friction factor in turbulent flow:

```text
1/√f = -2.0 × log₁₀(ε/3.7D + 2.51/(Re×√f))
```

Where:

- ε = absolute roughness (ft)
- D = pipe diameter (ft)
- Re = Reynolds number

This implicit equation is solved iteratively.

### Reynolds Number

```text
Re = V × D / ν
```

Where:

- V = velocity (ft/s)
- D = diameter (ft)
- ν = kinematic viscosity (ft²/s)

Flow regimes:

- Laminar: Re < 2,300
- Transitional: 2,300 < Re < 4,000
- Turbulent: Re > 4,000

### Minor Losses

Minor (local) losses from fittings:

```text
hm = K × V²/2g
```

Where K is the loss coefficient from Crane TP-410.

## Pump Modeling

### Pump Curves

Pump performance is defined by head-flow curves. We use cubic spline interpolation for smooth transitions between data points.

### Affinity Laws

For variable speed operation:

```text
Q₂/Q₁ = N₂/N₁
H₂/H₁ = (N₂/N₁)²
P₂/P₁ = (N₂/N₁)³
```

### NPSH Calculation

Net Positive Suction Head Available:

```text
NPSHa = (Ps + Patm - Pv)/γ + Vs²/2g
```

Where:

- Ps = suction pressure
- Patm = atmospheric pressure (14.7 psi default)
- Pv = vapor pressure at fluid temperature

## Fluid Properties

### Water

Properties calculated using standard correlations:

- Density: ~62.4 lb/ft³ at 68°F
- Viscosity: Temperature-dependent
- Vapor pressure: Temperature-dependent

### Glycol Solutions

Properties from manufacturer data for propylene and ethylene glycol solutions at various concentrations.

## Solver Algorithm

### Simple Networks (MVP)

For single-path systems:

1. Generate system curve (head vs. flow)
2. Interpolate pump curve
3. Find intersection (Newton-Raphson)
4. Calculate all pressures and head losses

### Complex Networks (Future)

For branching/looped networks:

- Uses EPANET algorithm (gradient method)
- Solves continuity and energy equations simultaneously

## Units and Conversions

### Default Units (US)

| Quantity | Unit |
|----------|------|
| Length | ft |
| Diameter | in |
| Flow | GPM |
| Pressure | psi |
| Head | ft |
| Velocity | ft/s |
| Temperature | °F |

### Conversion Factors

| From | To | Factor |
|------|-----|--------|
| GPM | ft³/s | 0.002228 |
| psi | ft H₂O | 2.31 (at 60°F) |
| cSt | ft²/s | 1.076×10⁻⁵ |

## References

1. Crane Co., "Flow of Fluids Through Valves, Fittings, and Pipe", Technical Paper No. 410M
2. Colebrook, C.F. (1939), "Turbulent Flow in Pipes, with particular reference to the Transition Region between the Smooth and Rough Pipe Laws"
3. Rossman, L.A. (2000), "EPANET 2 Users Manual", EPA/600/R-00/057
4. Karassik, I.J. et al. (2001), "Pump Handbook", McGraw-Hill

## Limitations

### Current MVP Limitations

- Single-path networks only (no branching)
- Steady-state only (no transients)
- Incompressible liquids only (no gas)
- Isothermal flow (no heat transfer calculations)
- No water hammer / surge analysis

### Accuracy Considerations

- Results typically within 1% of EPANET
- K-factors are approximate (±10-20% typical)
- Pump curve interpolation smooths data
- Roughness values are nominal

For critical applications, verify results with independent calculations.
