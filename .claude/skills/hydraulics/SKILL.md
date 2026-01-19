---
name: hydraulics
description: Hydraulic engineering domain knowledge for OpenSolve Pipe development. Use when implementing solvers, adding components, or reviewing hydraulic calculations.
---

# Hydraulics Engineering Skill

## Friction Factor Calculations

- Always use Darcy-Weisbach with Colebrook equation
- Never use Hazen-Williams (project decision per PRD)
- Friction factor function: `fluids.friction.friction_factor(Re, eD)`

### Colebrook Equation

```
1/√f = -2.0 × log₁₀((ε/D)/3.7 + 2.51/(Re×√f))
```

- Implicit equation solved iteratively
- `ε` = absolute roughness (ft or m)
- `D` = pipe inner diameter (ft or m)
- `Re` = Reynolds number (dimensionless)

## K-Factor Resolution Order

1. User-specified value (if provided)
2. Crane TP-410 correlation (preferred)
3. Fluids library default
4. Error if no value available

## Standard L/D Values (Crane TP-410)

| Fitting | L/D |
|---------|-----|
| 90° LR Elbow | 20 |
| 90° SR Elbow | 30 |
| 45° Elbow | 16 |
| Gate Valve (open) | 8 |
| Ball Valve (open) | 3 |
| Swing Check | 50 |
| Tee (through) | 20 |
| Tee (branch) | 60 |

**K-Factor Calculation from L/D:**
```
K = f × (L/D)
```
where `f` is the Darcy friction factor

## Pipe Material Roughness (ft)

| Material | Roughness (ft) | Roughness (mm) |
|----------|----------------|----------------|
| Carbon Steel | 0.00015 | 0.046 |
| Stainless Steel | 0.00005 | 0.015 |
| PVC | 0.000005 | 0.0015 |
| HDPE | 0.000023 | 0.007 |
| Ductile Iron | 0.00083 | 0.25 |
| GRP (Fiberglass) | 0.000033 | 0.01 |

## Unit Conversions

### Flow
- 1 GPM = 6.309e-5 m³/s
- 1 GPM = 1/448.831 ft³/s
- 1 GPM = 0.227 m³/h
- 1 GPM = 0.0631 L/s

### Pressure
- 1 psi = 6894.76 Pa
- 1 psi = 2.31 ft H₂O
- 1 psi = 0.703 m H₂O
- 1 bar = 14.504 psi

### Length
- 1 ft = 0.3048 m
- 1 in = 0.0254 m = 25.4 mm

### Velocity
- 1 ft/s = 0.3048 m/s

## Darcy-Weisbach Head Loss

### Pipe Friction Loss
```
h_f = f × (L/D) × (v²/2g)
```

where:
- `h_f` = head loss (ft or m)
- `f` = Darcy friction factor
- `L` = pipe length (ft or m)
- `D` = pipe inner diameter (ft or m)
- `v` = flow velocity (ft/s or m/s)
- `g` = gravitational acceleration (32.174 ft/s² or 9.807 m/s²)

### Minor Losses
```
h_m = K × (v²/2g)
```

where:
- `h_m` = minor head loss (ft or m)
- `K` = loss coefficient (dimensionless)
- Sum all K-factors for all fittings in series

### Total Head Loss
```
h_total = h_pipe + Σh_fittings + Σh_components
```

## Reynolds Number

```
Re = (ρ × v × D) / μ = (v × D) / ν
```

where:
- `ρ` = density (lb/ft³ or kg/m³)
- `μ` = dynamic viscosity (lb/(ft·s) or Pa·s)
- `ν` = kinematic viscosity (ft²/s or m²/s)

### Flow Regimes
- **Laminar:** Re < 2,300
- **Transition:** 2,300 ≤ Re ≤ 4,000
- **Turbulent:** Re > 4,000

Most hydraulic systems operate in turbulent flow.

## NPSH Calculations

### NPSH Available
```
NPSH_a = (P_atm - P_vapor) / (ρ×g) + h_static - h_friction_suction
```

where:
- `P_atm` = atmospheric pressure (absolute)
- `P_vapor` = vapor pressure of fluid at operating temperature
- `h_static` = static height of fluid above pump centerline (positive if above, negative if below)
- `h_friction_suction` = friction loss in suction piping

### NPSH Margin
```
NPSH_margin = NPSH_a - NPSH_r
```

- **Minimum margin:** 3 ft (0.91 m) for most applications
- **Recommended margin:** 5 ft (1.52 m) for continuous operation
- Warn if margin < 3 ft (configurable)

## Pump Curve Handling

### Interpolation
- Use cubic spline for smooth curve
- Scipy: `scipy.interpolate.CubicSpline`
- Ensure curve is monotonically decreasing (head decreases as flow increases)

### Extrapolation
- Use with warning only
- Linear extrapolation acceptable for small extensions (< 10%)
- Flag to user if operating point is outside curve range

### Operating Point
- Find intersection of pump curve and system curve
- Use root-finding: `scipy.optimize.brentq` or `scipy.optimize.fsolve`
- System curve: total head loss vs flow

### Affinity Laws (Variable Speed)
```
Q₂/Q₁ = N₂/N₁
H₂/H₁ = (N₂/N₁)²
P₂/P₁ = (N₂/N₁)³
```

where:
- `Q` = flow rate
- `H` = head
- `P` = power
- `N` = pump speed (RPM)

## Velocity Limits (Design Guidelines)

| Service | Typical Velocity Range |
|---------|------------------------|
| Suction piping | 3-5 ft/s (0.9-1.5 m/s) |
| Discharge piping | 5-10 ft/s (1.5-3 m/s) |
| General service | 4-8 ft/s (1.2-2.4 m/s) |
| Low noise requirement | < 6 ft/s (< 1.8 m/s) |

**Note:** These are guidelines. User can override in project settings.

## Pressure Drop Limits

- **Suction line:** Minimize pressure drop to avoid cavitation
- **Discharge line:** Typically < 5 psi per 100 ft (11.3 kPa per 30 m)

## Common Gotchas

1. **Units consistency:** Always convert to consistent unit system before calculations
2. **Absolute vs gauge pressure:** NPSH calculations require absolute pressure
3. **Temperature effects:** Fluid properties vary with temperature
4. **Closed valve:** Treat as infinite K-factor or broken connection
5. **Zero flow:** Avoid division by zero; handle as special case
6. **Reverse flow:** Friction calculations still use absolute velocity

## Reference Standards

- **Crane TP-410:** Flow of Fluids Through Valves, Fittings, and Pipe
- **ASME B31.3:** Process Piping
- **HI Standards:** Hydraulic Institute Standards for Centrifugal Pumps

## Validation Checklist

When reviewing hydraulic calculations:

- [ ] Units are consistent throughout
- [ ] Darcy-Weisbach equation used (not Hazen-Williams)
- [ ] Friction factor from Colebrook equation
- [ ] K-factors follow resolution order
- [ ] Reynolds number calculated correctly
- [ ] NPSH available calculated at pump suction
- [ ] Operating point within pump curve range (or warning issued)
- [ ] Velocity within reasonable range (warning if excessive)
- [ ] Temperature-dependent properties used if applicable
- [ ] Absolute pressure used for vapor pressure calculations
