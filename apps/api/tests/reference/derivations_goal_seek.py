"""Closed-form reference cases for goal seek (docs/proposals/goal-seek.md §7.2; PRD §3.9).

Written from the design (§1-§8, §11), the specs and the models by a tester who did not read
``opensolve_pipe.services``; nothing here imports it. Each case builds one network from the
parameters at the top of its function, one goal-seek request (variables with their bounds, goals
with their targets), and from first principles:

- ``forward(x)``: the goals' values at variable values x, the network solved in closed form (or by
  this module's own brentq/fsolve on the closed-form laws);
- ``inverse``: the variable values that meet the targets exactly (None: the target is not
  reachable inside the bounds).

The laws are the reference suite's, in EGL form (CLAUDE.md D7), with no entrance or exit loss at a
boundary without a fitting (D10):

- pipes: Darcy–Weisbach, ``fluids.friction.Colebrook`` (Lambert-W) or 64/Re (``derivations``,
  ``line``); fittings: the Crane TP-410 functions of ``fluids.fittings`` (``derivations``);
- pumps: ``scipy.interpolate.PchipInterpolator`` through the points, affinity laws
  H = s² H₀(Q/s) (``element_laws``); a straight curve H₀ = a − b x gives the speed in closed
  form, s = [bQ + √(b²Q² + 4aH)]/(2a) (``derivations_pump_control.speed_linear``);
- valves: K from Cv or Kv by definition (``element_laws.k_from_flow_coefficient``), its inverse
  ``cv_from_k`` below (checked against ``fluids.fittings.K_to_Cv``); a PRV holds the static
  pressure at its outlet, an FCV its flow; a check valve opens above h_c =
  crackingPressure/(ρg) (``element_laws``);
- water: CoolProp ``PropsSI`` at 101325 Pa (``derivations.water_properties``); NPSHa =
  EGL_s − z_s + (p_atm − p_vap)/(ρg), p_atm = ATMOSPHERE_1976(0).P (``derivations_pumps``);
- static pressure at a port p = ρg(H − z − v²/2g), v in the connected pipe; v = 0 at a
  reservoir's or reference node's port;
- equipment (docs/proposals/equipment-pressure-drop.md §5.2, §7.3): EGL_in − EGL_out = c Q|Q|,
  c = ΔP_ref/(ρ_ref g Q_ref²) from the rating (``element_laws.equipment_coefficient``; a Cv or Kv
  the rated point 1 psi at Cv US gpm or 1 bar at Kv m³/h of the suite's reference water); its
  goals read the flow, the loss ρ g (EGL_in − EGL_out) and the static drop p_in − p_out
  (``derivations_equipment``);
- orifice plates (docs/proposals/orifice-plate.md §5.2, §7.3): EGL_in − EGL_out = K(C_L) v|v|/2g
  on the inlet pipe's velocity, C_L ISO 5167-2's at D and D/2 tappings or an entered C (moved by
  eq. (4)'s ratio from corner or flange taps), ``element_laws.OrificeLaw``; K strictly decreases
  in β and in C, so each inverse is one brentq on the plate's own law (``derivations_orifice``);
  its goals read the flow, the loss ρg (EGL_in − EGL_out), the reading at the taps and the static
  drop p_in − p_out;
- pressure relief valves (docs/proposals/pressure-relief-valve.md §5, §7.3): the linear lift on
  the total-pressure difference with API 520's equation at its lift (``element_laws.ReliefLaw``,
  ``derivations_relief``); at a known flow and Δp_t the lift x = Q/(Kd·A·√(2Δp_t/ρ)) fixes the
  set (Δp_s = Δp_t/(1 + op·x)), the overpressure (op = (Δp_t − Δp_s)/(x·Δp_s)) or, beyond full
  lift, the area or coefficient (Kd·A = Q/√(2Δp_t/ρ)) in closed form; its goals read the flow
  and the static drop p_in − p_out.

The request follows design §2.1-§2.3: a variable ``{kind, componentId | connectionId +
pipeIndex, field, coefficient?, lower, upper}`` and a goal ``{quantity, elementId, portId?,
target, tolerance?}``. Goals here carry no tolerance; ``test_goal_seek`` adds the default
(omitted) or the smallest allowed one (§2.2).

The case files of design §7.2 (``cases/goal_seek_*.json``) are not written: registering them is
``build_closed_form_cases``' and ``test_derivations_current``' job, outside this tester's files.
Every derivation here is deterministic and runs in well under a second, so the test derives it
each time.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import fluids.fittings
import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq, fsolve

from opensolve_pipe.models.components import API526Letter
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import derivations as dv
from tests.reference import derivations_equipment as de
from tests.reference import derivations_orifice as do
from tests.reference import derivations_relief as dr
from tests.reference import element_laws as el
from tests.reference.case_format import (
    FrictionMethod,
    assigned_flow,
    builtin_water,
    certified_capacity,
    check_valve,
    connect,
    control_valve,
    custom_fluid,
    custom_pipe,
    effective_capacity,
    fitting,
    flow_coefficient,
    flow_control,
    ideal_tee,
    isolation_valve,
    make_project,
    orifice,
    pump,
    pump_curve,
    rated_coefficient,
    rated_point,
    reference_node,
    relief_valve,
    reservoir,
)
from tests.reference.derivations_assigned_flow import FLOW_PUMP_DISCHARGE
from tests.reference.derivations_pump_control import (
    ParallelPumps,
    collinear_coefficients,
    curve_straight,
    speed_linear,
)
from tests.reference.derivations_pumps import DISCHARGE_A, SUCTION_A, curve_a, solve_decreasing
from tests.reference.derivations_valves import CONTROL_IN, CONTROL_OUT, CV_LINES
from tests.reference.line import Line, require_turbulent

MODULE = "derivations_goal_seek"
G = dv.G
SITE_ATMOSPHERE = dv.standard_atmosphere_pressure(0.0)
"""Pa absolute: every case sits at site elevation 0 (fluids ATMOSPHERE_1976(0).P)."""

Quantity = Literal[
    "port_pressure",
    "link_flow",
    "link_velocity",
    "link_head_loss",
    "pump_flow",
    "pump_head",
    "pump_npsh_available",
    "pump_npsh_margin",
    "valve_flow",
    "valve_pressure_drop",
    "equipment_flow",
    "equipment_pressure_loss",
    "equipment_pressure_drop",
    "orifice_flow",
    "orifice_pressure_loss",
    "orifice_differential_pressure",
    "orifice_pressure_drop",
    "relief_valve_flow",
    "relief_valve_pressure_drop",
    "boundary_outflow",
]
Dimension = Literal["pressure", "head", "flow", "velocity"]
DIMENSION: dict[str, Dimension] = {
    "port_pressure": "pressure",
    "valve_pressure_drop": "pressure",
    "link_head_loss": "head",
    "pump_head": "head",
    "pump_npsh_available": "head",
    "pump_npsh_margin": "head",
    "link_flow": "flow",
    "pump_flow": "flow",
    "valve_flow": "flow",
    "boundary_outflow": "flow",
    "link_velocity": "velocity",
    "equipment_flow": "flow",
    "equipment_pressure_loss": "pressure",
    "equipment_pressure_drop": "pressure",
    "orifice_flow": "flow",
    "orifice_pressure_loss": "pressure",
    "orifice_differential_pressure": "pressure",
    "orifice_pressure_drop": "pressure",
    "relief_valve_flow": "flow",
    "relief_valve_pressure_drop": "pressure",
}
"""What each goal quantity measures (design §2.2's unit column; the equipment goals' units are
equipment-pressure-drop.md §5.2's: m³/s and Pa (difference); the orifice goals' orifice-plate.md
§5.2's, likewise)."""

# --- Tolerances, as design §2.2 and decision 9 state them --------------------------------------

RELATIVE_TOLERANCE = 0.005
"""The default tolerance's relative part: D6's 0.5 %."""
HEAD_FLOOR = 0.01
"""m: D6's head floor; pressures use ρg × 0.01 m."""
FLOW_FLOOR = 1.0e-6
"""m³/s: the designers' flow floor (D16, not in D6)."""
VELOCITY_FLOOR = 1.0e-3
"""m/s: the designers' velocity floor (D16, not in D6)."""
MINIMUM_RELATIVE = 1.0e-6
MINIMUM_ABSOLUTE: dict[Dimension, float] = {
    "pressure": 0.1,
    "head": 1.0e-5,
    "flow": 1.0e-9,
    "velocity": 1.0e-6,
}
"""The smallest user tolerance, max(10⁻⁶ |target|, this), fixed per quantity (design §2.2)."""

D6_FLOW_FLOOR = 1.0e-9
"""m³/s: the reference suite's flow floor (``test_reference_cases.FLOW_FLOOR``); D6 has none."""
D6_VELOCITY_FLOOR = 1.0e-9
"""m/s: the same floor for velocities (D6 has none)."""


def default_tolerance(quantity: str, target: float, rho: float) -> float:
    """max(0.5 % |target|, floor): ρg × 0.01 m for pressures (ρ of the case fluid at the case's
    temperature), 0.01 m for heads, 10⁻⁶ m³/s for flows, 10⁻³ m/s for velocities (§2.2)."""
    floor = {
        "pressure": rho * G * HEAD_FLOOR,
        "head": HEAD_FLOOR,
        "flow": FLOW_FLOOR,
        "velocity": VELOCITY_FLOOR,
    }[DIMENSION[quantity]]
    return max(RELATIVE_TOLERANCE * abs(target), floor)


def smallest_tolerance(quantity: str, target: float) -> float:
    """max(10⁻⁶ |target|, the quantity's minimum): the tightest tolerance a request may give."""
    return max(MINIMUM_RELATIVE * abs(target), MINIMUM_ABSOLUTE[DIMENSION[quantity]])


def d6(quantity: str, reference: float, rho: float) -> float:
    """D6's allowance for a goal value: 0.5 % of the reference or 0.01 m of head (ρg × 0.01 m
    for a pressure), whichever is looser; flows and velocities take the reference suite's tiny
    floor (D6 has no flow floor)."""
    floor = {
        "pressure": rho * G * HEAD_FLOOR,
        "head": HEAD_FLOOR,
        "flow": D6_FLOW_FLOOR,
        "velocity": D6_VELOCITY_FLOOR,
    }[DIMENSION[quantity]]
    return max(RELATIVE_TOLERANCE * abs(reference), floor)


VariableCheck = Literal["level", "pressure", "speed", "flow", "forward"]
"""How D6 judges a found variable value against the closed-form inverse (design §7.2): a level
within 0.5 % or 0.01 m, a pressure within 0.5 % or ρg × 0.01 m, a speed within 0.5 % (D6's speed
rule), a flow within 0.5 %; a length, a flow coefficient or a temperature has no D6 quantity, so
the forward model at the value found must be within D6 of the target ('forward')."""


def variable_within_d6(check: VariableCheck, found: float, inverse: float, rho: float) -> bool:
    if check == "level":
        return abs(found - inverse) <= max(RELATIVE_TOLERANCE * abs(inverse), HEAD_FLOOR)
    if check == "pressure":
        return abs(found - inverse) <= max(RELATIVE_TOLERANCE * abs(inverse), rho * G * HEAD_FLOOR)
    if check in ("speed", "flow"):
        return abs(found - inverse) <= RELATIVE_TOLERANCE * abs(inverse)
    raise ValueError("a 'forward' variable is judged by its goals")


Stop = Literal["met_at_start", "met", "not_reachable", "jump", "unsolved_crossing", "no_progress"]


@dataclass(frozen=True)
class GoalSeekCase:
    """One reference case: the project, the request and its closed-form answer."""

    name: str
    description: str
    source: str
    project: dict[str, Any]
    """API JSON of the project (with its scenarios, if any)."""
    variables: tuple[dict[str, Any], ...]
    goals: tuple[dict[str, Any], ...]
    """Without tolerances: the test adds the default (omitted) or the smallest allowed."""
    forward: Callable[[Sequence[float]], list[float]]
    """The goals' closed-form values at variable values x (SI, in the request's order)."""
    inverse: tuple[float, ...] | None
    """The closed-form variable values that meet every target exactly (None: unreachable)."""
    checks: tuple[VariableCheck, ...]
    density: float
    """ρ of the case fluid at the case's own temperature, kg/m³ (pressure tolerance floors)."""
    stop: Stop = "met"
    """The stop reason expected with the default tolerance."""
    tight: bool = True
    """Also run with the smallest allowed tolerance (§7.2's tight-tolerance criterion)."""
    scenario_id: str | None = None
    start: tuple[float, ...] | None = None
    """The expected start of each variable (None: the case's value, read by the test)."""
    start_source: tuple[str, ...] | None = None
    """'case', 'clipped' or 'middle' per variable (None: 'case')."""
    data: dict[str, Any] = field(default_factory=dict)
    """Case-specific facts the test checks (state changes, bounds, the setpoint, ...)."""

    def request(self, tolerances: Sequence[float | None] | None = None) -> dict[str, Any]:
        goals = []
        for j, goal in enumerate(self.goals):
            g = dict(goal)
            if tolerances is not None and tolerances[j] is not None:
                g["tolerance"] = tolerances[j]
            goals.append(g)
        body: dict[str, Any] = {
            "project": self.project,
            "variables": [dict(v) for v in self.variables],
            "goals": goals,
        }
        if self.scenario_id is not None:
            body["scenarioId"] = self.scenario_id
        return body


def _source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def _json(project: Project) -> dict[str, Any]:
    data: dict[str, Any] = project.model_dump(mode="json", exclude_none=True)
    return data


def _fluid_a() -> tuple[CustomFluid, float, float]:
    """The water-like custom test liquid A: (fluid, ρ, ν)."""
    name, rho, mu = dv.FLUID_A
    return custom_fluid(name, rho, mu), rho, mu / rho


def _water(temperature: float) -> tuple[BuiltinFluid, float, float, float]:
    """Built-in water at T: (fluid, ρ, ν, p_vap) from CoolProp (``derivations``)."""
    rho, mu = dv.water_properties(temperature)
    return builtin_water(temperature), rho, mu / rho, dv.water_vapor_pressure(temperature)


def component_variable(
    cid: str, field_name: str, lower: float, upper: float, coefficient: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kind": "component",
        "componentId": cid,
        "field": field_name,
        "lower": lower,
        "upper": upper,
    }
    if coefficient is not None:
        out["coefficient"] = coefficient
    return out


def pipe_variable(
    connection_id: str, pipe_index: int, lower: float, upper: float
) -> dict[str, Any]:
    return {
        "kind": "pipe",
        "connectionId": connection_id,
        "pipeIndex": pipe_index,
        "field": "length",
        "lower": lower,
        "upper": upper,
    }


def project_variable(lower: float, upper: float) -> dict[str, Any]:
    return {"kind": "project", "field": "fluid.temperature", "lower": lower, "upper": upper}


def goal(
    quantity: Quantity, element_id: str, target: float, port_id: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {"quantity": quantity, "elementId": element_id, "target": target}
    if port_id is not None:
        out["portId"] = port_id
    return out


def signed_flow(head_loss: Callable[[float], float], dh: float) -> float:
    """The flow Q, signed like dh, whose loss is dh, for a law odd in Q (friction and inline
    fittings only, no entrance or exit): brentq on |dh| (``derivations.solve_flow``)."""
    if dh == 0.0:
        return 0.0
    q = dv.solve_flow(head_loss, abs(dh))
    return q if dh > 0.0 else -q


def cv_from_k(k: float, d: float) -> float:
    """The Cv whose K on inner diameter d is k: the inverse of ``element_laws.k_from_definition``,
    K = 2 ΔP_ref A²/(ρ_ref Q_ref²) with Q_ref = Cv × 1 US gpm and ΔP_ref = 1 psi (reference water
    at 60 °F), so Cv = A √(2 ΔP_ref/(ρ_ref K)) / (1 US gpm)."""
    q_ref = dv.area(d) * math.sqrt(2.0 * el.CV_PRESSURE_DROP / (el.REFERENCE_WATER_DENSITY * k))
    return q_ref / el.CV_FLOW


def pump_line_flow(
    h1: float,
    h2: float,
    suction: Line,
    discharge: Line,
    curve: PumpCurve,
    speed: float,
    nu: float,
) -> float:
    """Operating flow of R1 → suction → pump → discharge → R2 at speed s (design §2.2, §5.1):
    0 when the static lift H_R2 − H_R1 is at or above the shutoff head s² H₀(0), else the root
    of H_R1 − h_s(Q) + s² H₀(Q/s) − h_d(Q) = H_R2 (brentq)."""
    if el.shutoff_head(curve, speed) <= h2 - h1:
        return 0.0
    return solve_decreasing(
        lambda q: (
            h1
            - suction.head_loss(q, nu)
            + el.pump_head(curve, speed, q)
            - discharge.head_loss(q, nu)
            - h2
        )
    )


def bisect(fn: Callable[[float], float], lo: float, hi: float) -> float:
    """brentq at the derivations' precision."""
    root: float = brentq(fn, lo, hi, xtol=1.0e-15, rtol=4.0 * 2.0**-52, maxiter=500)
    return root


# --- G1-G3, G9, G15, G18: one pipe between reservoirs ------------------------------------------

G1_PIPE = (0.1, 250.0, 4.5e-5)
"""Inner diameter, length and roughness of single_pipe_turbulent's pipe (test inputs)."""
G1_Z1, G1_LEVEL1, G1_Z2, G1_LEVEL2 = 10.0, 2.0, 0.0, 1.5
G1_BOUNDS = (0.0, 20.5)
"""m: R1's level bounds (the design's measured range, §3.11)."""
G1_TARGET = 0.02
"""m³/s: the flow target in L1."""


def _single_pipe(
    name: str,
    *,
    fluid: CustomFluid | BuiltinFluid,
    pipe: tuple[float, float, float],
    level1: float,
    fittings: Sequence[str] = (),
    z1: float = G1_Z1,
    level2: float = G1_LEVEL2,
) -> dict[str, Any]:
    d, length, eps = pipe
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        name.replace("_", " "),
        fluid,
        [reservoir("R1", z1, level1), reservoir("R2", G1_Z2, level2)],
        [
            connect(
                "L1",
                "R1:port_1",
                "R2:port_1",
                [custom_pipe(d, length, eps)],
                [fitting(f) for f in fittings],  # type: ignore[arg-type]
            )
        ],
    )
    return _json(project)


def _level_case(
    name: str,
    description: str,
    method: str,
    *,
    fluid: CustomFluid | BuiltinFluid,
    rho: float,
    nu: float,
    pipe: tuple[float, float, float],
    k_total: float,
    target: float,
    regime: dv.Regime,
    level1: float = G1_LEVEL1,
    bounds: tuple[float, float] = G1_BOUNDS,
    fittings: Sequence[str] = (),
    reachable: bool = True,
    stop: Stop = "met",
    tight: bool = True,
    z1: float = G1_Z1,
    level2: float = G1_LEVEL2,
) -> GoalSeekCase:
    """R1 (z₁, level x) → L1 → R2 (z 0, H₂); R1's liquidLevel → flow in L1 (G1: z₁ 10 m,
    H₂ 1.5 m).

    Energy equation:  z₁ + x − H₂ = f(Re)(L/D) v²/2g + ΣK v²/2g,  v = 4Q/(πD²), so the level that
    passes Q is  x = H₂ − z₁ + h(Q)  in closed form, and the flow at a level is the root of
    h(Q) = z₁ + x − H₂ (signed: reverse below H₂ − z₁)."""
    d, length, eps = pipe

    def loss(q: float) -> float:
        return dv.friction_head_loss(q, d, length, eps, nu) + dv.minor_head_loss(q, k_total, d)

    h2 = G1_Z2 + level2

    def forward(x: Sequence[float]) -> list[float]:
        return [signed_flow(loss, z1 + x[0] - h2)]

    level = h2 - z1 + loss(target)
    dv.require_regime(target, d, nu, regime)
    if reachable and not bounds[0] < level < bounds[1]:
        raise ValueError(f"{name}: the level {level} is outside the bounds")
    if not reachable and bounds[0] <= level <= bounds[1]:
        raise ValueError(f"{name}: the target is reachable")
    return GoalSeekCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=_single_pipe(
            name, fluid=fluid, pipe=pipe, level1=level1, fittings=fittings, z1=z1, level2=level2
        ),
        variables=(component_variable("R1", "liquidLevel", *bounds),),
        goals=(goal("link_flow", "L1", target),),
        forward=forward,
        inverse=(level,) if reachable else None,
        checks=("level",),
        density=rho,
        stop=stop,
        tight=tight,
    )


def goal_seek_level_turbulent() -> GoalSeekCase:
    """G1: R1's level for 20 L/s through 250 m of 100 mm pipe, turbulent (Colebrook)."""
    fluid, rho, nu = _fluid_a()
    return _level_case(
        "goal_seek_level_turbulent",
        "G1: the reservoir level that passes 20 L/s through one turbulent pipe "
        "(Darcy-Weisbach, Colebrook), custom fluid.",
        "level = H2 - z1 + f(Re)(L/D) v^2/2g, Colebrook via fluids Lambert-W",
        fluid=fluid,
        rho=rho,
        nu=nu,
        pipe=G1_PIPE,
        k_total=0.0,
        target=G1_TARGET,
        regime="turbulent",
    )


def goal_seek_level_laminar() -> GoalSeekCase:
    """G2: a viscous oil (870 kg/m³, 17.4 mPa·s) through 80 m of 50 mm pipe at 0.7 L/s
    (Re ≈ 890), R1 at z 1.2 m, R2 at H 1.15 m (single_pipe_laminar's): f = 64/Re, so the level
    is linear in Q, x = H₂ − z₁ + 128 ν L Q/(g π D⁴)."""
    rho, mu = 870.0, 1.74e-2
    nu = mu / rho
    d, length, eps = 0.05, 80.0, 4.5e-5
    z1, level2 = 1.2, 1.15
    target = 7.0e-4
    case = _level_case(
        "goal_seek_level_laminar",
        "G2: the reservoir level that passes 0.7 L/s of a viscous oil through one laminar pipe "
        "(Hagen-Poiseuille, f = 64/Re: the level is linear in the flow).",
        "level = H2 - z1 + 128 nu L Q/(g pi D^4) (f = 64/Re)",
        fluid=custom_fluid("Viscous oil (custom input)", rho, mu),
        rho=rho,
        nu=nu,
        pipe=(d, length, eps),
        k_total=0.0,
        target=target,
        regime="laminar",
        bounds=(0.0, 3.0),
        level1=0.4,
        z1=z1,
        level2=level2,
    )
    closed = G1_Z2 + level2 - z1 + 128.0 * nu * length * target / (G * math.pi * d**4)
    assert case.inverse is not None
    if abs(case.inverse[0] - closed) > 1.0e-12 * abs(closed) + 1.0e-12:
        raise RuntimeError("the laminar law does not give the Hagen-Poiseuille closed form")
    return case


def goal_seek_level_fittings_water() -> GoalSeekCase:
    """G3: G1 with a sharp entrance and an exit (Crane via fluids), water at 20 °C (CoolProp):
    x = H₂ − z₁ + [f(Re)(L/D) + K_entrance + K_exit] v²/2g."""
    fluid, rho, nu, _ = _water(293.15)
    return _level_case(
        "goal_seek_level_fittings_water",
        "G3: G1 with a sharp entrance and an exit fitting, built-in water at 20 C: the level "
        "includes the Crane entrance and exit losses (D10: none without the fittings).",
        "level = H2 - z1 + [f (L/D) + K_entrance + K_exit] v^2/2g; fluids entrance_sharp(Crane), "
        "exit_normal; water from CoolProp at 101325 Pa",
        fluid=fluid,
        rho=rho,
        nu=nu,
        pipe=G1_PIPE,
        k_total=dv.k_entrance_sharp() + dv.k_exit(),
        target=G1_TARGET,
        regime="turbulent",
        fittings=("entrance_sharp", "exit"),
    )


def goal_seek_length() -> GoalSeekCase:
    """G9: G1's length that passes 30 L/s with R1 at its case level (log scale):
    L = (H₁ − H₂) · 2gD/(f v²), f = Colebrook at Q (closed form)."""
    fluid, rho, nu = _fluid_a()
    d, _, eps = G1_PIPE
    target = 0.03
    h1, h2 = G1_Z1 + G1_LEVEL1, G1_Z2 + G1_LEVEL2
    v = dv.velocity(target, d)
    f = dv.friction_factor(dv.reynolds(target, d, nu), eps / d)
    length = (h1 - h2) * 2.0 * G * d / (f * v * v)
    bounds = (10.0, 2000.0)
    if not bounds[0] < length < bounds[1]:
        raise ValueError("G9's length is outside its bounds")

    def forward(x: Sequence[float]) -> list[float]:
        return [dv.solve_flow(lambda q: dv.friction_head_loss(q, d, x[0], eps, nu), h1 - h2)]

    name = "goal_seek_length"
    return GoalSeekCase(
        name=name,
        description="G9: the pipe length that passes 30 L/s between G1's reservoirs (a log-scale "
        "variable).",
        source=_source(name, "L = (H1 - H2) 2 g D/(f v^2), Colebrook via fluids at Q"),
        project=_single_pipe(name, fluid=fluid, pipe=G1_PIPE, level1=G1_LEVEL1),
        variables=(pipe_variable("L1", 0, *bounds),),
        goals=(goal("link_flow", "L1", target),),
        forward=forward,
        inverse=(length,),
        checks=("forward",),
        density=rho,
    )


def goal_seek_level_unreachable() -> GoalSeekCase:
    """G15: G1 with a target 1.5 times the flow at the upper bound (20.5 m): no level in the
    bounds meets it; the closest is the upper bound, where the flow is the closed form's."""
    fluid, rho, nu = _fluid_a()
    d, length, eps = G1_PIPE
    h_top = G1_Z1 + G1_BOUNDS[1] - (G1_Z2 + G1_LEVEL2)
    q_top = dv.solve_flow(lambda q: dv.friction_head_loss(q, d, length, eps, nu), h_top)
    case = _level_case(
        "goal_seek_level_unreachable",
        "G15: G1 with a flow target above what the upper level bound passes: not met, the "
        "closest value at the upper bound (not_reachable, closest_at_bound), after the start "
        "and the 9-point scan.",
        "the flow at the upper bound, level 20.5 m, by Colebrook; the target is 1.5 times it",
        fluid=fluid,
        rho=rho,
        nu=nu,
        pipe=G1_PIPE,
        k_total=0.0,
        target=1.5 * q_top,
        regime="turbulent",
        reachable=False,
        stop="not_reachable",
        tight=False,
    )
    return replace(case, data={"closest": G1_BOUNDS[1], "evaluations": 10})


def goal_seek_met_at_start() -> GoalSeekCase:
    """G18: G1 with R1's case level set to the closed-form level for 20 L/s: the start meets
    the goal, so the search stops after 1 evaluation (met_at_start)."""
    fluid, rho, nu = _fluid_a()
    d, length, eps = G1_PIPE
    level = G1_Z2 + G1_LEVEL2 - G1_Z1 + dv.friction_head_loss(G1_TARGET, d, length, eps, nu)
    case = _level_case(
        "goal_seek_met_at_start",
        "G18: G1 whose case level is already the closed-form level for its target: one "
        "evaluation, met_at_start, nothing to change.",
        "level = H2 - z1 + f(Re)(L/D) v^2/2g at the target, written as the case's level",
        fluid=fluid,
        rho=rho,
        nu=nu,
        pipe=G1_PIPE,
        k_total=0.0,
        target=G1_TARGET,
        regime="turbulent",
        level1=level,
        stop="met_at_start",
        tight=False,
    )
    return replace(case, start=(level,), data={"evaluations": 1})


G19_OVERRIDES: tuple[dict[str, Any], ...] = (
    {"kind": "component", "componentId": "R2", "field": "liquidLevel", "value": 2.5},
    {"kind": "pipe", "connectionId": "L1", "pipeIndex": 0, "field": "length", "value": 300.0},
    {"kind": "component", "componentId": "R1", "field": "liquidLevel", "value": 3.0},
)
"""Scenario S1 of G19 (test inputs): R2's level, L1's length and R1's level."""


def goal_seek_scenario() -> GoalSeekCase:
    """G19: G1 with scenario S1 (R2's level 2.5 m, L1 300 m long, R1's level 3 m); R1's level →
    20 L/s in L1, on S1: x = H₂(S1) − z₁ + f(Re)(L_S1/D) v²/2g. The search starts at S1's level
    (3 m, the base's is 2 m) and its value takes the place of S1's override 2."""
    fluid, rho, nu = _fluid_a()
    d, _, eps = G1_PIPE
    level2, length, level1 = (o["value"] for o in G19_OVERRIDES)
    h2 = G1_Z2 + level2

    def loss(q: float) -> float:
        return dv.friction_head_loss(q, d, length, eps, nu)

    def forward(x: Sequence[float]) -> list[float]:
        return [signed_flow(loss, G1_Z1 + x[0] - h2)]

    level = h2 - G1_Z1 + loss(G1_TARGET)
    if not G1_BOUNDS[0] < level < G1_BOUNDS[1]:
        raise ValueError("G19's level is outside its bounds")
    name = "goal_seek_scenario"
    project = _single_pipe(name, fluid=fluid, pipe=G1_PIPE, level1=G1_LEVEL1)
    project["scenarios"] = [
        {
            "id": "S1",
            "name": "Higher outlet",
            "description": "R2 raised, a longer line, R1 raised.",
            "overrides": [dict(o) for o in G19_OVERRIDES],
        }
    ]
    return GoalSeekCase(
        name=name,
        description="G19: G1 on scenario S1, which overrides R2's level, L1's length and R1's "
        "level: the closed form with S1's values; the search starts at S1's R1 level and its "
        "override replaces S1's (replacedOverride 2).",
        source=_source(name, "level = H2(S1) - z1 + f(Re)(L_S1/D) v^2/2g, Colebrook via fluids"),
        project=project,
        variables=(component_variable("R1", "liquidLevel", *G1_BOUNDS),),
        goals=(goal("link_flow", "L1", G1_TARGET),),
        forward=forward,
        inverse=(level,),
        checks=("level",),
        density=rho,
        tight=True,
        scenario_id="S1",
        start=(level1,),
        data={"caseValue": level1, "baseValue": G1_LEVEL1, "replacedOverride": 2},
    )


# --- G4, G5, G14, G21, G22: pump lines ----------------------------------------------------------

PUMP_Z1, PUMP_LEVEL1, PUMP_Z, PUMP_Z2, PUMP_LEVEL2 = 0.0, 3.0, 0.5, 18.0, 2.0
"""R1 (H 3 m) → SUCTION_A → PU1 (z 0.5 m) → DISCHARGE_A → R2 (H 20 m), as
pump_flow_control_active_linear (test inputs)."""


def _pump_line_project(
    name: str,
    fluid: CustomFluid | BuiltinFluid,
    curve: PumpCurve,
    *,
    speed: float = 1.0,
    control: Any = None,
    level1: float = PUMP_LEVEL1,
    z_pump: float = PUMP_Z,
    suction: Line = SUCTION_A,
) -> dict[str, Any]:
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        name.replace("_", " "),
        fluid,
        [
            reservoir("R1", PUMP_Z1, level1),
            pump("PU1", z_pump, curve.id, speed=speed, control=control),
            reservoir("R2", PUMP_Z2, PUMP_LEVEL2),
        ],
        [
            suction.connect("L1", "R1:port_1", "PU1:suction"),
            DISCHARGE_A.connect("L2", "PU1:discharge", "R2:port_1"),
        ],
        pump_library=[curve],
    )
    return _json(project)


def goal_seek_pump_speed_flow() -> GoalSeekCase:
    """G4: the speed of a pump with a straight curve (H₀ = 40 − 400x, collinear points, so the
    PCHIP is that line) for a duty flow of 15 L/s: H = H₂ − H₁ + h_s(Q) + h_d(Q), and the
    affinity law s² (a − bQ/s) = H gives s = [bQ + √(b²Q² + 4aH)]/(2a)."""
    fluid, rho, nu = _fluid_a()
    curve = curve_straight()
    a, b = collinear_coefficients(curve)
    target = 0.015
    h1, h2 = PUMP_Z1 + PUMP_LEVEL1, PUMP_Z2 + PUMP_LEVEL2
    lift = h2 - h1 + SUCTION_A.head_loss(target, nu) + DISCHARGE_A.head_loss(target, nu)
    s = speed_linear(a, b, target, lift)
    require_turbulent(nu, [(target, SUCTION_A), (target, DISCHARGE_A)])
    bounds = (0.5, 1.0)
    if not (bounds[0] < s < bounds[1] and el.pump_in_curve_range(curve, s, target)):
        raise ValueError("G4's speed is outside its bounds or its curve")
    if abs(el.pump_head(curve, s, target) - lift) > 1.0e-9:
        raise RuntimeError("the PCHIP of collinear points is not the straight line")

    def forward(x: Sequence[float]) -> list[float]:
        return [pump_line_flow(h1, h2, SUCTION_A, DISCHARGE_A, curve, x[0], nu)]

    name = "goal_seek_pump_speed_flow"
    return GoalSeekCase(
        name=name,
        description="G4: the speed of a straight-curve pump for a 15 L/s duty point (affinity "
        "laws, closed form).",
        source=_source(name, "s = [bQ + sqrt(b^2 Q^2 + 4aH)]/(2a), H = H2 - H1 + h_s(Q) + h_d(Q)"),
        project=_pump_line_project(name, fluid, curve),
        variables=(component_variable("PU1", "speed", *bounds),),
        goals=(goal("pump_flow", "PU1", target),),
        forward=forward,
        inverse=(s,),
        checks=("speed",),
        density=rho,
    )


def goal_seek_pump_speed_pressure() -> GoalSeekCase:
    """G5: G4's pump speed for 210 kPa(g) static at its discharge port (z 0.5 m, v in L2):
    Q from ρg(H₂ + h_d(Q) − v_d²/2g − z_d) = p (brentq), then s as in G4."""
    fluid, rho, nu = _fluid_a()
    curve = curve_straight()
    a, b = collinear_coefficients(curve)
    target = 210.0e3
    h1, h2 = PUMP_Z1 + PUMP_LEVEL1, PUMP_Z2 + PUMP_LEVEL2

    def discharge_pressure(q: float) -> float:
        egl = h2 + DISCHARGE_A.head_loss(q, nu)
        return dv.static_pressure(rho, egl, PUMP_Z, DISCHARGE_A.velocity(q))

    q = bisect(lambda q: discharge_pressure(q) - target, 1.0e-4, 0.04)
    lift = h2 - h1 + SUCTION_A.head_loss(q, nu) + DISCHARGE_A.head_loss(q, nu)
    s = speed_linear(a, b, q, lift)
    require_turbulent(nu, [(q, SUCTION_A), (q, DISCHARGE_A)])
    bounds = (0.5, 1.0)
    if not bounds[0] < s < bounds[1]:
        raise ValueError("G5's speed is outside its bounds")

    def forward(x: Sequence[float]) -> list[float]:
        return [discharge_pressure(pump_line_flow(h1, h2, SUCTION_A, DISCHARGE_A, curve, x[0], nu))]

    name = "goal_seek_pump_speed_pressure"
    return GoalSeekCase(
        name=name,
        description="G5: the speed of G4's pump for 210 kPa(g) static pressure at its "
        "discharge port.",
        source=_source(
            name,
            "Q from rho g (H2 + h_d(Q) - v_d^2/2g - z_d) = p by brentq; "
            "s = [bQ + sqrt(b^2 Q^2 + 4aH)]/(2a)",
        ),
        project=_pump_line_project(name, fluid, curve),
        variables=(component_variable("PU1", "speed", *bounds),),
        goals=(goal("port_pressure", "PU1", target, "discharge"),),
        forward=forward,
        inverse=(s,),
        checks=("speed",),
        density=rho,
    )


def goal_seek_pump_speed_head_loss() -> GoalSeekCase:
    """G24 (link_head_loss): G4's pump speed for a 3 m head loss in its discharge connection L2,
    EGL(PU1:discharge) − EGL(R2) = h_d(Q): Q from h_d(Q) = 3 m (brentq), then s as in G4."""
    fluid, rho, nu = _fluid_a()
    curve = curve_straight()
    a, b = collinear_coefficients(curve)
    target = 3.0
    h1, h2 = PUMP_Z1 + PUMP_LEVEL1, PUMP_Z2 + PUMP_LEVEL2
    q = bisect(lambda q: DISCHARGE_A.head_loss(q, nu) - target, 1.0e-4, 0.04)
    lift = h2 - h1 + SUCTION_A.head_loss(q, nu) + DISCHARGE_A.head_loss(q, nu)
    s = speed_linear(a, b, q, lift)
    require_turbulent(nu, [(q, SUCTION_A), (q, DISCHARGE_A)])
    bounds = (0.5, 1.0)
    if not bounds[0] < s < bounds[1]:
        raise ValueError("G24's speed is outside its bounds")

    def forward(x: Sequence[float]) -> list[float]:
        flow = pump_line_flow(h1, h2, SUCTION_A, DISCHARGE_A, curve, x[0], nu)
        return [DISCHARGE_A.head_loss(flow, nu)]

    name = "goal_seek_pump_speed_head_loss"
    return GoalSeekCase(
        name=name,
        description="G24: the speed of G4's pump for a 3 m head loss in its discharge "
        "connection (link_head_loss, EGL(from) - EGL(to)).",
        source=_source(name, "Q from h_d(Q) = 3 m by brentq; s = [bQ + sqrt(b^2 Q^2 + 4aH)]/(2a)"),
        project=_pump_line_project(name, fluid, curve),
        variables=(component_variable("PU1", "speed", *bounds),),
        goals=(goal("link_head_loss", "L2", target),),
        forward=forward,
        inverse=(s,),
        checks=("speed",),
        density=rho,
    )


def curve_straight_b() -> PumpCurve:
    """A second straight rated curve (test input): H₀ = 30 − 250x through five points."""
    return pump_curve("PC-T", [(0.0, 30.0), (0.01, 27.5), (0.02, 25.0), (0.03, 22.5), (0.04, 20.0)])


G14_NET = ParallelPumps(
    3.0,
    20.0,
    Line(0.2027, 10.0, (("entrance_sharp", 1),)),
    Line(0.1023, 4.0, (("elbow_90_lr", 1),)),
    Line(0.1023, 6.0, (("gate_valve", 1),)),
    Line(0.1023, 4.0, (("elbow_90_lr", 1),)),
    Line(0.1023, 6.0, (("gate_valve", 1),)),
    Line(0.1541, 60.0, (("elbow_90_lr", 2), ("exit", 1))),
)
"""R1 (H 3 m) → L1 → ideal tee T1, two pump legs to ideal tee T2, → L2 → R2 (H 20 m) (the
parallel layout of ``derivations_pump_control``; test inputs)."""


def goal_seek_parallel_pump_speeds() -> GoalSeekCase:
    """G14 (n = 2): the speeds of two parallel straight-curve pumps (PA: 40 − 400x, PB:
    30 − 250x) for leg flows 14 and 10 L/s. With the tee heads H_T1 = H_R1 − h_L1(Q),
    H_T2 = H_R2 + h_L2(Q), Q = Q_A + Q_B, each pump's head is
    H_i = (H_T2 + h_out,i(Q_i)) − (H_T1 − h_in,i(Q_i)) and its speed s_i = [b_i Q_i +
    √(b_i² Q_i² + 4 a_i H_i)]/(2 a_i)."""
    fluid, rho, nu = _fluid_a()
    net = G14_NET
    ca, cb = curve_straight(), curve_straight_b()
    (aa, ba), (ab, bb) = collinear_coefficients(ca), collinear_coefficients(cb)
    qa, qb = 0.014, 0.010
    ha, hb = net.head_needed_a(qa, qb, nu), net.head_needed_b(qa, qb, nu)
    sa, sb = speed_linear(aa, ba, qa, ha), speed_linear(ab, bb, qb, hb)
    require_turbulent(
        nu,
        [
            (qa + qb, net.l1),
            (qa, net.la1),
            (qa, net.la2),
            (qb, net.lb1),
            (qb, net.lb2),
            (qa + qb, net.l2),
        ],
    )
    bounds = (0.5, 1.0)
    for s, c, q in ((sa, ca, qa), (sb, cb, qb)):
        if not (bounds[0] < s < bounds[1] and el.pump_in_curve_range(c, s, q)):
            raise ValueError("G14's speeds are outside their bounds or curves")

    def forward(x: Sequence[float]) -> list[float]:
        def residuals(v: NDArray[np.float64]) -> list[float]:
            q1, q2 = float(v[0]), float(v[1])
            return [
                net.head_needed_a(q1, q2, nu) - el.pump_head(ca, x[0], q1),
                net.head_needed_b(q1, q2, nu) - el.pump_head(cb, x[1], q2),
            ]

        sol, _, ier, message = fsolve(residuals, [qa, qb], xtol=1.0e-13, full_output=True)
        if ier != 1 or max(abs(r) for r in residuals(sol)) > 1.0e-10:
            raise RuntimeError(f"G14's forward model did not solve: {message}")
        return [float(sol[0]), float(sol[1])]

    name = "goal_seek_parallel_pump_speeds"
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        "goal seek parallel pump speeds",
        fluid,
        [
            reservoir("R1", 0.0, net.h1),
            ideal_tee("T1", 0.5),
            pump("PA", 0.5, ca.id, speed=1.0),
            pump("PB", 0.5, cb.id, speed=1.0),
            ideal_tee("T2", 1.0),
            reservoir("R2", net.h2 - 2.0, 2.0),
        ],
        [
            net.l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            net.la1.connect("LA1", "T1:run_outlet", "PA:suction"),
            net.la2.connect("LA2", "PA:discharge", "T2:run_inlet"),
            net.lb1.connect("LB1", "T1:branch", "PB:suction"),
            net.lb2.connect("LB2", "PB:discharge", "T2:branch"),
            net.l2.connect("L2", "T2:run_outlet", "R2:port_1"),
        ],
        pump_library=[ca, cb],
    )
    return GoalSeekCase(
        name=name,
        description="G14: two parallel pumps' speeds for two leg flows (n = 2, least squares).",
        source=_source(
            name,
            "tee heads from the shared lines; each s_i = [b_i Q_i + sqrt(b_i^2 Q_i^2 + "
            "4 a_i H_i)]/(2 a_i); forward model by fsolve",
        ),
        project=_json(project),
        variables=(
            component_variable("PA", "speed", *bounds),
            component_variable("PB", "speed", *bounds),
        ),
        goals=(goal("pump_flow", "PA", qa), goal("pump_flow", "PB", qb)),
        forward=forward,
        inverse=(sa, sb),
        checks=("speed", "speed"),
        density=rho,
    )


def goal_seek_pump_setpoint_head() -> GoalSeekCase:
    """G21 (control.setpoint): the flow setpoint of G4's pump, speed-controlled (s ∈ [0.5, 1]),
    for a pump head of 19 m. Active, the pump passes Q = Q_set and its head is the system's,
    H(Q) = H₂ − H₁ + h_s(Q) + h_d(Q) (D11: a fixed-flow link), so Q_set solves H(Q) = 19 m
    (brentq), with the active band F(s_lo, Q) ≤ H ≤ F(1, Q) checked (``element_laws``)."""
    fluid, rho, nu = _fluid_a()
    curve = curve_straight()
    target = 19.0
    h1, h2 = PUMP_Z1 + PUMP_LEVEL1, PUMP_Z2 + PUMP_LEVEL2
    min_speed = 0.5

    def system_head(q: float) -> float:
        return h2 - h1 + SUCTION_A.head_loss(q, nu) + DISCHARGE_A.head_loss(q, nu)

    q_set = bisect(lambda q: system_head(q) - target, 1.0e-4, 0.03)
    require_turbulent(nu, [(q_set, SUCTION_A), (q_set, DISCHARGE_A)])
    control = flow_control(q_set, min_speed)
    problem = el.controlled_pump_state_problem(
        "on", curve, control, 1.0, "active", q_set, target, el.STATE_MARGIN
    )
    if problem:
        raise ValueError(f"G21's pump {problem}")
    bounds = (0.004, 0.03)

    def forward(x: Sequence[float]) -> list[float]:
        return [system_head(x[0])]

    name = "goal_seek_pump_setpoint_head"
    return GoalSeekCase(
        name=name,
        description="G21: the flow setpoint of a speed-controlled pump for a 19 m pump head "
        "(control.setpoint; active: the pump passes its setpoint, its head is the system's).",
        source=_source(
            name,
            "Q_set from H2 - H1 + h_s(Q) + h_d(Q) = H by brentq; active band F(s_lo, Q) <= H "
            "<= F(s_max, Q) checked",
        ),
        project=_pump_line_project(name, fluid, curve, control=flow_control(0.012, min_speed)),
        variables=(component_variable("PU1", "control.setpoint", *bounds),),
        goals=(goal("pump_head", "PU1", target),),
        forward=forward,
        inverse=(q_set,),
        checks=("flow",),
        density=rho,
    )


NPSH_SUCTION = Line(0.1023, 8.0, (("entrance_sharp", 1), ("elbow_90_lr", 2)))
"""The suction line of the NPSH cases (test input)."""
NPSH_Z = 3.0
"""m: the pump above R1's surface in the NPSH cases (a suction lift; test input)."""


def curve_straight_npshr() -> PumpCurve:
    """The straight rated curve H₀ = 40 − 400x with a straight NPSHr curve, NPSHr₀ = 1.5 +
    100x through three collinear points (test inputs; the PCHIP of collinear points is the
    line)."""
    return pump_curve(
        "PC-N",
        [(0.0, 40.0), (0.01, 36.0), (0.02, 32.0), (0.03, 28.0), (0.04, 24.0)],
        npshr=[(0.005, 2.0), (0.025, 4.0), (0.045, 6.0)],
    )


def npsh_available(egl_suction: float, z: float, rho: float, p_vap: float) -> float:
    """NPSHa = (EGL_s − z_s) + (p_atm − p_vap)/(ρg), p_atm at site elevation 0 (design §8)."""
    return egl_suction - z + (SITE_ATMOSPHERE - p_vap) / (rho * G)


def goal_seek_temperature_npsh_margin() -> GoalSeekCase:
    """G12: the water temperature at which a pump lifting from 1 m below its suction (R1 H 2 m,
    pump z 3 m) has an NPSH margin of 0. At T: ρ, ν and p_vap from CoolProp; Q(T) from the pump
    law H₁ − h_s(Q) + H₀(Q) − h_d(Q) = H₂ (brentq; heads in m do not depend on ρ, ν does);
    NPSHa(T) = H₁ − h_s(Q) − z_s + (p_atm − p_vap(T))/(ρ(T)g); NPSHr(Q) = 1.5 + 100Q; and T by
    brentq on NPSHa − NPSHr = 0."""
    temperature = 293.15
    fluid, rho, _, _ = _water(temperature)
    curve = curve_straight_npshr()
    h1, h2 = PUMP_Z1 + 2.0, PUMP_Z2 + PUMP_LEVEL2

    def margin(t: float) -> float:
        rho_t, mu_t = dv.water_properties(t)
        nu_t = mu_t / rho_t
        q = pump_line_flow(h1, h2, NPSH_SUCTION, DISCHARGE_A, curve, 1.0, nu_t)
        egl_s = h1 - NPSH_SUCTION.head_loss(q, nu_t)
        npsha = npsh_available(egl_s, NPSH_Z, rho_t, dv.water_vapor_pressure(t))
        return npsha - el.npsh_required(curve, 1.0, q)

    bounds = (290.0, 370.0)
    t_star = bisect(margin, 320.0, 365.0)
    rho_s, mu_s = dv.water_properties(t_star)
    q_star = pump_line_flow(h1, h2, NPSH_SUCTION, DISCHARGE_A, curve, 1.0, mu_s / rho_s)
    require_turbulent(mu_s / rho_s, [(q_star, NPSH_SUCTION), (q_star, DISCHARGE_A)])
    if not el.pump_in_curve_range(curve, 1.0, q_star):
        raise ValueError("G12's pump runs off its curve")

    def forward(x: Sequence[float]) -> list[float]:
        return [margin(x[0])]

    name = "goal_seek_temperature_npsh_margin"
    return GoalSeekCase(
        name=name,
        description="G12: the water temperature at which a suction-lift pump's NPSH margin is "
        "zero (fluid.temperature; CoolProp density, viscosity and vapor pressure).",
        source=_source(
            name,
            "NPSHa(T) = H1 - h_s(Q) - z_s + (p_atm - p_vap(T))/(rho(T) g), Q(T) from the pump "
            "law with nu(T), NPSHr linear; CoolProp IAPWS-95; brentq on T",
        ),
        project=_pump_line_project(
            name, fluid, curve, level1=2.0, z_pump=NPSH_Z, suction=NPSH_SUCTION
        ),
        variables=(project_variable(*bounds),),
        goals=(goal("pump_npsh_margin", "PU1", 0.0),),
        forward=forward,
        inverse=(t_star,),
        checks=("forward",),
        density=rho,
    )


def goal_seek_level_npsh_available() -> GoalSeekCase:
    """G22 (pump_npsh_available): the suction reservoir level that gives 9 m of NPSH available
    to curve_a's pump 3 m above R1's base, water at 20 °C: Q(x) from the pump law, NPSHa(x) =
    x − h_s(Q) − z_s + (p_atm − p_vap)/(ρg), and x by brentq."""
    temperature = 293.15
    fluid, rho, nu, p_vap = _water(temperature)
    curve = curve_a()
    h2 = PUMP_Z2 + PUMP_LEVEL2
    target = 9.0

    def npsha(level: float) -> float:
        h1 = PUMP_Z1 + level
        q = pump_line_flow(h1, h2, NPSH_SUCTION, DISCHARGE_A, curve, 1.0, nu)
        return npsh_available(h1 - NPSH_SUCTION.head_loss(q, nu), NPSH_Z, rho, p_vap)

    bounds = (0.0, 10.0)
    level = bisect(lambda x: npsha(x) - target, *bounds)
    q = pump_line_flow(PUMP_Z1 + level, h2, NPSH_SUCTION, DISCHARGE_A, curve, 1.0, nu)
    require_turbulent(nu, [(q, NPSH_SUCTION), (q, DISCHARGE_A)])

    def forward(x: Sequence[float]) -> list[float]:
        return [npsha(x[0])]

    name = "goal_seek_level_npsh_available"
    return GoalSeekCase(
        name=name,
        description="G22: the suction reservoir level that gives a pump 9 m of NPSH available "
        "(pump_npsh_available), water at 20 C.",
        source=_source(
            name,
            "NPSHa = H1 - h_s(Q) - z_s + (p_atm - p_vap)/(rho g), Q from the PCHIP pump law; "
            "CoolProp IAPWS-95; brentq on the level",
        ),
        project=_pump_line_project(
            name, fluid, curve, level1=2.0, z_pump=NPSH_Z, suction=NPSH_SUCTION
        ),
        variables=(component_variable("R1", "liquidLevel", *bounds),),
        goals=(goal("pump_npsh_available", "PU1", target),),
        forward=forward,
        inverse=(level,),
        checks=("level",),
        density=rho,
    )


# --- G6, G10, G13, G17, G23: valve lines ---------------------------------------------------------

VALVE_Z = 5.0
"""m: the control valves' elevation (``derivations_valves.CONTROL_Z``)."""


def _two_line_project(
    name: str,
    fluid: CustomFluid | BuiltinFluid,
    h1_parts: tuple[float, float],
    h2_parts: tuple[float, float],
    lines: tuple[Line, Line],
    element: Any,
) -> dict[str, Any]:
    """R1 → lines[0] → element (inlet/outlet) → lines[1] → R2."""
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        name.replace("_", " "),
        fluid,
        [reservoir("R1", *h1_parts), element, reservoir("R2", *h2_parts)],
        [
            lines[0].connect("L1", "R1:port_1", f"{element.id}:inlet"),
            lines[1].connect("L2", f"{element.id}:outlet", "R2:port_1"),
        ],
    )
    return _json(project)


def goal_seek_prv_setpoint_flow() -> GoalSeekCase:
    """G6: the PRV setting (static pressure at its outlet, z 5 m) that passes 12 L/s from a 60 m
    supply to a 10 m reservoir: active, EGL_out = H₂ + h_L2(Q), so p_set = ρg(H₂ + h_L2(Q) −
    v_out²/2g − z_v), with the PRV active (H₁ − h_L1(Q) above its setpoint head)."""
    fluid, rho, nu = _fluid_a()
    l1, l2 = CONTROL_IN, CONTROL_OUT
    h1_parts, h2_parts = (55.0, 5.0), (8.0, 2.0)
    h1, h2 = sum(h1_parts), sum(h2_parts)
    target = 0.012
    egl_out = h2 + l2.head_loss(target, nu)
    p_set = dv.static_pressure(rho, egl_out, VALVE_Z, l2.velocity(target))
    require_turbulent(nu, [(target, l1), (target, l2)])
    prv = control_valve("PRV1", VALVE_Z, "prv", 150.0e3)
    check = control_valve("PRV1", VALVE_Z, "prv", p_set)
    problem = el.valve_state_problem(
        check,
        "active",
        target,
        h1 - l1.head_loss(target, nu),
        egl_out,
        rho,
        el.STATE_MARGIN,
        l1.d,
        l2.d,
    )
    if problem:
        raise ValueError(f"G6's PRV {problem}")
    bounds = (60.0e3, 450.0e3)
    if not bounds[0] < p_set < bounds[1]:
        raise ValueError("G6's setpoint is outside its bounds")

    def forward(x: Sequence[float]) -> list[float]:
        # Active at x: the flow puts p_set at the outlet; the guard keeps x in the active state.
        def residual(q: float) -> float:
            return el.setpoint_head(VALVE_Z, x[0], rho, q, l2.d) - h2 - l2.head_loss(q, nu)

        q = solve_decreasing(residual)
        e_in = h1 - l1.head_loss(q, nu)
        valve = control_valve("PRV1", VALVE_Z, "prv", x[0])
        state = el.valve_state_problem(
            valve, "active", q, e_in, h2 + l2.head_loss(q, nu), rho, el.STATE_MARGIN, l1.d, l2.d
        )
        if state:
            raise ValueError(f"G6's forward model: the PRV {state}")
        return [q]

    name = "goal_seek_prv_setpoint_flow"
    return GoalSeekCase(
        name=name,
        description="G6: the PRV setpoint that passes 12 L/s (active PRV, static outlet pressure).",
        source=_source(name, "p_set = rho g (H2 + h_L2(Q) - v_out^2/2g - z_v); PRV active checked"),
        project=_two_line_project(name, fluid, h1_parts, h2_parts, (l1, l2), prv),
        variables=(component_variable("PRV1", "setpoint", *bounds),),
        goals=(goal("link_flow", "L2", target),),
        forward=forward,
        inverse=(p_set,),
        checks=("pressure",),
        density=rho,
    )


VALVE_LINES = (
    Line(0.1023, 30.0, (("entrance_sharp", 1),)),
    Line(0.1023, 60.0, (("elbow_90_lr", 2), ("exit", 1))),
)
"""The lines either side of G10's gate valve (``derivations_valves.CV_LINES``)."""


def _gate_valve_case(name: str, description: str, resistance: float | None) -> GoalSeekCase:
    """G10: R1 (H 12 m) → L1 → gate valve V1 (z 1 m) → L2 → R2 (H 2 m); V1's Cv → 20 L/s.
    K = [H₁ − H₂ − h_L1(Q) − h_L2(Q)] · 2g/v_ref², v_ref = Q/A in L1 (the valve's inlet
    pipe), then Cv from K by definition (``cv_from_k``)."""
    fluid, rho, nu = _fluid_a()
    l1, l2 = VALVE_LINES
    h1_parts, h2_parts = (10.0, 2.0), (0.0, 2.0)
    h1, h2 = sum(h1_parts), sum(h2_parts)
    target = 0.02
    v_ref = l1.velocity(target)
    k = (h1 - h2 - l1.head_loss(target, nu) - l2.head_loss(target, nu)) * 2.0 * G / v_ref**2
    cv = cv_from_k(k, l1.d)
    if abs(el.k_from_flow_coefficient(flow_coefficient("Cv", cv), l1.d) - k) > 1.0e-9 * k:
        raise RuntimeError("cv_from_k does not invert the Cv definition")
    if abs(cv - float(fluids.fittings.K_to_Cv(k, l1.d))) > 2.0e-6 * cv:
        raise RuntimeError("the Cv definition disagrees with fluids.fittings.K_to_Cv")
    require_turbulent(nu, [(target, l1), (target, l2)])
    bounds = (10.0, 5000.0)
    if not (k > 0.0 and bounds[0] < cv < bounds[1]):
        raise ValueError("G10's Cv is outside its bounds")

    def forward(x: Sequence[float]) -> list[float]:
        kx = el.k_from_flow_coefficient(flow_coefficient("Cv", x[0]), l1.d)
        return [
            dv.solve_flow(
                lambda q: l1.head_loss(q, nu) + el.valve_loss(kx, q, l1.d) + l2.head_loss(q, nu),
                h1 - h2,
            )
        ]

    valve = isolation_valve(
        "V1",
        1.0,
        "gate",
        resistance=None if resistance is None else flow_coefficient("Cv", resistance),
    )
    lower, upper = bounds
    middle = lower * math.sqrt(upper / lower)
    return GoalSeekCase(
        name=name,
        description=description,
        source=_source(
            name,
            "K = [H1 - H2 - h_L1(Q) - h_L2(Q)] 2g/v_ref^2; Cv = A sqrt(2 psi/(rho_60F K))/gpm "
            "(the Cv definition, element_laws)",
        ),
        project=_two_line_project(name, fluid, h1_parts, h2_parts, (l1, l2), valve),
        variables=(component_variable("V1", "resistance", *bounds, coefficient="Cv"),),
        goals=(goal("valve_flow", "V1", target),),
        forward=forward,
        inverse=(cv,),
        checks=("forward",),
        density=rho,
        start=None if resistance is not None else (middle,),
        start_source=None if resistance is not None else ("middle",),
        data={"k": k},
    )


def goal_seek_valve_cv_flow() -> GoalSeekCase:
    """G10 with V1 holding Cv 200: the search starts at the case's Cv."""
    return _gate_valve_case(
        "goal_seek_valve_cv_flow",
        "G10: the gate valve Cv that passes 20 L/s (a log-scale resistance; the case holds "
        "Cv 200).",
        200.0,
    )


def goal_seek_valve_cv_from_default() -> GoalSeekCase:
    """G10b: G10 with V1 on its Crane default (no resistance): the search starts at the middle
    of the bounds on the log scale, √(10 × 5000) (design §3.2, ``middle``)."""
    return _gate_valve_case(
        "goal_seek_valve_cv_from_default",
        "G10b: G10 with the valve on its Crane TP-410 default: a resistance of another form "
        "starts at the geometric middle of its bounds.",
        None,
    )


def goal_seek_fcv_setpoint_pressure() -> GoalSeekCase:
    """G13: the FCV setpoint that gives 100 kPa(g) static at its outlet (z 5 m, v in L2) on the
    fcv_active line (H₁ 40 m, H₂ 2 m): active, Q = Q_set, so Q from ρg(H₂ + h_L2(Q) − v²/2g −
    z) = p (brentq), with the FCV active (H₁ − h_L1(Q) − H₂ − h_L2(Q) above its open loss)."""
    fluid, rho, nu = _fluid_a()
    l1, l2 = CONTROL_IN, CONTROL_OUT
    h1_parts, h2_parts = (36.0, 4.0), (0.0, 2.0)
    h1, h2 = sum(h1_parts), sum(h2_parts)
    target = 100.0e3

    def outlet_pressure(q: float) -> float:
        return dv.static_pressure(rho, h2 + l2.head_loss(q, nu), VALVE_Z, l2.velocity(q))

    q = bisect(lambda q: outlet_pressure(q) - target, 1.0e-3, 0.03)
    require_turbulent(nu, [(q, l1), (q, l2)])
    check = control_valve("FCV1", VALVE_Z, "fcv", q)
    problem = el.valve_state_problem(
        check,
        "active",
        q,
        h1 - l1.head_loss(q, nu),
        h2 + l2.head_loss(q, nu),
        rho,
        el.STATE_MARGIN,
        l1.d,
        l2.d,
    )
    if problem:
        raise ValueError(f"G13's FCV {problem}")
    bounds = (0.002, 0.03)

    def forward(x: Sequence[float]) -> list[float]:
        valve = control_valve("FCV1", VALVE_Z, "fcv", x[0])
        state = el.valve_state_problem(
            valve,
            "active",
            x[0],
            h1 - l1.head_loss(x[0], nu),
            h2 + l2.head_loss(x[0], nu),
            rho,
            el.STATE_MARGIN,
            l1.d,
            l2.d,
        )
        if state:
            raise ValueError(f"G13's forward model: the FCV {state}")
        return [outlet_pressure(x[0])]

    name = "goal_seek_fcv_setpoint_pressure"
    return GoalSeekCase(
        name=name,
        description="G13: the FCV setpoint that gives 100 kPa(g) at its outlet (active FCV: "
        "the flow is the setpoint).",
        source=_source(
            name, "Q from rho g (H2 + h_L2(Q) - v^2/2g - z) = p by brentq; setpoint = Q"
        ),
        project=_two_line_project(
            name, fluid, h1_parts, h2_parts, (l1, l2), control_valve("FCV1", VALVE_Z, "fcv", 0.006)
        ),
        variables=(component_variable("FCV1", "setpoint", *bounds),),
        goals=(goal("port_pressure", "FCV1", target, "outlet"),),
        forward=forward,
        inverse=(q,),
        checks=("flow",),
        density=rho,
    )


G17_CRACKING = 2000.0
"""Pa: CV1's cracking pressure (test input)."""
G17_Z2, G17_LEVEL2 = 0.0, 2.0
G17_BOUNDS = (0.0, 10.0)


def goal_seek_check_valve_opening() -> GoalSeekCase:
    """G17: R1 (z 0, level x; case 1.5 m) → CV_LINES[0] → swing check valve CV1 (cracking 2 kPa,
    z 1 m) → CV_LINES[1] → R2 (H 2 m); R1's level → 20 L/s. Closed while x ≤ H₂ + h_c (h_c =
    2000/(ρg)); open above it: x = H₂ + h_c + h_L1(Q) + K v²/2g + h_L2(Q), K =
    K_swing_check_valve_Crane(D) at the inlet pipe (``element_laws``). The case's level keeps
    the valve closed, so the met state differs from the start's: CV1 closed → open."""
    fluid, rho, nu = _fluid_a()
    l1, l2 = CV_LINES
    valve = check_valve("CV1", 1.0, "check", cracking_pressure=G17_CRACKING)
    k = el.valve_k("check", None, l1.d)
    h_c = G17_CRACKING / (rho * G)
    h2 = G17_Z2 + G17_LEVEL2
    target = 0.02
    level = h2 + h_c + l1.head_loss(target, nu) + el.valve_loss(k, target, l1.d)
    level += l2.head_loss(target, nu)
    require_turbulent(nu, [(target, l1), (target, l2)])
    e_in, e_out = level - l1.head_loss(target, nu), h2 + l2.head_loss(target, nu)
    problem = el.valve_state_problem(valve, "open", target, e_in, e_out, rho, el.STATE_MARGIN)
    if problem:
        raise ValueError(f"G17's check valve {problem}")
    case_level = 1.5
    if not (case_level < h2 + h_c - el.STATE_MARGIN and G17_BOUNDS[0] < level < G17_BOUNDS[1]):
        raise ValueError("G17 needs a closed start and a level inside the bounds")

    def forward(x: Sequence[float]) -> list[float]:
        dh = x[0] - h2
        if dh <= h_c:
            return [0.0]
        return [
            dv.solve_flow(
                lambda q: l1.head_loss(q, nu) + el.valve_loss(k, q, l1.d) + l2.head_loss(q, nu),
                dh - h_c,
            )
        ]

    name = "goal_seek_check_valve_opening"
    return GoalSeekCase(
        name=name,
        description="G17: the reservoir level that opens a check valve (2 kPa cracking "
        "pressure) and passes 20 L/s; the start is closed, so the met state names CV1 "
        "closed -> open.",
        source=_source(
            name,
            "closed below H2 + p_crack/(rho g); open: level = H2 + h_c + h_L1 + K v^2/2g + "
            "h_L2, K from fluids K_swing_check_valve_Crane",
        ),
        project=_two_line_project(
            name, fluid, (0.0, case_level), (G17_Z2, G17_LEVEL2), (l1, l2), valve
        ),
        variables=(component_variable("R1", "liquidLevel", *G17_BOUNDS),),
        goals=(goal("link_flow", "L1", target),),
        forward=forward,
        inverse=(level,),
        checks=("level",),
        density=rho,
        data={"stateChanges": [("CV1", "valve_state", "closed", "open")]},
    )


G23_LINES = (
    Line(0.1023, 30.0, (("entrance_sharp", 1),)),
    Line(0.0779, 60.0, (("elbow_90_lr", 2), ("exit", 1))),
)
"""A 102.3 mm inlet and a 77.9 mm outlet line, so the static pressure drop across the valve
differs from ρg × its EGL drop by the velocity heads (test inputs)."""


def goal_seek_valve_k_pressure_drop() -> GoalSeekCase:
    """G23 (valve_pressure_drop, resistance K): the K of a gate valve (z 1 m) between a 102.3 mm
    and a 77.9 mm line for a 40 kPa static pressure drop. At K: Q(K) from H₁ − H₂ = h_L1 +
    K v_in²/2g + h_L2 (brentq); Δp = p_in − p_out = ρg[K v_in²/2g − v_in²/2g + v_out²/2g]
    (same elevation); K by brentq on Δp(K) = 40 kPa (Δp rises with K)."""
    fluid, rho, nu = _fluid_a()
    l1, l2 = G23_LINES
    h1_parts, h2_parts = (10.0, 2.0), (0.0, 2.0)
    h1, h2 = sum(h1_parts), sum(h2_parts)
    target = 40.0e3

    def drop(k: float) -> float:
        q = dv.solve_flow(
            lambda q: l1.head_loss(q, nu) + el.valve_loss(k, q, l1.d) + l2.head_loss(q, nu),
            h1 - h2,
        )
        v_in, v_out = l1.velocity(q), l2.velocity(q)
        return rho * G * (el.valve_loss(k, q, l1.d) - v_in * v_in / (2 * G) + v_out**2 / (2 * G))

    bounds = (0.1, 1000.0)
    k = bisect(lambda x: drop(x) - target, *bounds)
    q = dv.solve_flow(
        lambda q: l1.head_loss(q, nu) + el.valve_loss(k, q, l1.d) + l2.head_loss(q, nu), h1 - h2
    )
    require_turbulent(nu, [(q, l1), (q, l2)])

    def forward(x: Sequence[float]) -> list[float]:
        return [drop(x[0])]

    name = "goal_seek_valve_k_pressure_drop"
    return GoalSeekCase(
        name=name,
        description="G23: the K of a gate valve for a 40 kPa static pressure drop "
        "(valve_pressure_drop; coefficient K, log scale), different pipes either side.",
        source=_source(
            name,
            "Q(K) from H1 - H2 = h_L1 + K v_in^2/2g + h_L2; dp = rho g (K v_in^2/2g - "
            "v_in^2/2g + v_out^2/2g); brentq on K",
        ),
        project=_two_line_project(
            name,
            fluid,
            h1_parts,
            h2_parts,
            (l1, l2),
            isolation_valve("V1", 1.0, "gate", resistance=flow_coefficient("K", 5.0)),
        ),
        variables=(component_variable("V1", "resistance", *bounds, coefficient="K"),),
        goals=(goal("valve_pressure_drop", "V1", target),),
        forward=forward,
        inverse=(k,),
        checks=("forward",),
        density=rho,
    )


# --- G7, G8, G11, G20: other boundaries ---------------------------------------------------------


def goal_seek_assigned_flow_pressure() -> GoalSeekCase:
    """G7: the demand of an assigned-flow node (z 2 m) fed from R1 (H 25 m) through 150 m of
    102.3 mm pipe (a sharp entrance, two elbows) for 150 kPa(g) at its port: the line carries
    the demand (D12), p = ρg(H₁ − h(Q) − z − v²/2g), v in the pipe; Q by brentq."""
    fluid, rho, nu = _fluid_a()
    line = Line(0.1023, 150.0, (("entrance_sharp", 1), ("elbow_90_lr", 2)))
    h1, z = 25.0, 2.0
    target = 150.0e3

    def port_pressure(q: float) -> float:
        return dv.static_pressure(rho, h1 - line.head_loss(q, nu), z, line.velocity(q))

    bounds = (0.002, 0.035)
    q = bisect(lambda q: port_pressure(q) - target, *bounds)
    require_turbulent(nu, [(q, line)])
    project = make_project(
        "ref-goal-seek-assigned-flow-pressure",
        "goal seek assigned flow pressure",
        fluid,
        [reservoir("R1", 20.0, 5.0), assigned_flow("AF1", z, 0.01)],
        [line.connect("L1", "R1:port_1", "AF1:port_1")],
    )

    def forward(x: Sequence[float]) -> list[float]:
        return [port_pressure(x[0])]

    name = "goal_seek_assigned_flow_pressure"
    return GoalSeekCase(
        name=name,
        description="G7: the assigned demand that leaves 150 kPa(g) at its port.",
        source=_source(name, "p = rho g (H1 - h(Q) - z - v^2/2g); brentq on Q"),
        project=_json(project),
        variables=(component_variable("AF1", "flow", *bounds),),
        goals=(goal("port_pressure", "AF1", target, "port_1"),),
        forward=forward,
        inverse=(q,),
        checks=("flow",),
        density=rho,
    )


G8_LINES = (Line(0.0779, 60.0), Line(0.0627, 40.0), Line(0.1023, 100.0))
"""L1 (R1 → T1), L2 (R2 → T1 branch), L3 (T1 → R3): friction only, so each law is odd in Q
(test inputs)."""
G8_Z = {"R1": 5.0, "R2": 4.0, "T1": 1.0}


def goal_seek_two_levels_two_flows() -> GoalSeekCase:
    """G8 (n = 2): the levels of R1 and R2, feeding an ideal tee T1 that drains to R3 (H 2 m),
    for 10 L/s in L1 and 6 L/s in L2. An ideal tee holds one EGL (D9), H_T = H₃ + h_L3(Q₁ + Q₂),
    so level_i = H_T + h_Li(Q_i) − z_i in closed form. The forward model solves H_T from
    continuity, q₁(H₁ − H_T) + q₂(H₂ − H_T) = q₃(H_T − H₃) (brentq, signed flows)."""
    fluid, rho, nu = _fluid_a()
    l1, l2, l3 = G8_LINES
    h3 = 2.0
    q1, q2 = 0.010, 0.006
    h_t = h3 + l3.head_loss(q1 + q2, nu)
    levels = (h_t + l1.head_loss(q1, nu) - G8_Z["R1"], h_t + l2.head_loss(q2, nu) - G8_Z["R2"])
    require_turbulent(nu, [(q1, l1), (q2, l2), (q1 + q2, l3)])
    bounds = (0.0, 30.0)
    if not all(bounds[0] < x < bounds[1] for x in levels):
        raise ValueError("G8's levels are outside their bounds")

    def flows(x: Sequence[float]) -> tuple[float, float]:
        h1, h2 = G8_Z["R1"] + x[0], G8_Z["R2"] + x[1]

        def net(h: float) -> float:
            return (
                signed_flow(lambda q: l1.head_loss(q, nu), h1 - h)
                + signed_flow(lambda q: l2.head_loss(q, nu), h2 - h)
                - signed_flow(lambda q: l3.head_loss(q, nu), h - h3)
            )

        lo, hi = min(h1, h2, h3), max(h1, h2, h3)
        h = bisect(net, lo, hi)
        return (
            signed_flow(lambda q: l1.head_loss(q, nu), h1 - h),
            signed_flow(lambda q: l2.head_loss(q, nu), h2 - h),
        )

    def forward(x: Sequence[float]) -> list[float]:
        return list(flows(x))

    project = make_project(
        "ref-goal-seek-two-levels-two-flows",
        "goal seek two levels two flows",
        fluid,
        [
            reservoir("R1", G8_Z["R1"], 3.0),
            reservoir("R2", G8_Z["R2"], 2.0),
            ideal_tee("T1", G8_Z["T1"]),
            reservoir("R3", 0.0, h3),
        ],
        [
            l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            l2.connect("L2", "R2:port_1", "T1:branch"),
            l3.connect("L3", "T1:run_outlet", "R3:port_1"),
        ],
    )
    name = "goal_seek_two_levels_two_flows"
    return GoalSeekCase(
        name=name,
        description="G8: two reservoir levels for two flows into an ideal tee (n = 2, least "
        "squares).",
        source=_source(name, "H_T = H3 + h_L3(Q1 + Q2); level_i = H_T + h_Li(Q_i) - z_i"),
        project=_json(project),
        variables=(
            component_variable("R1", "liquidLevel", *bounds),
            component_variable("R2", "liquidLevel", *bounds),
        ),
        goals=(goal("link_flow", "L1", q1), goal("link_flow", "L2", q2)),
        forward=forward,
        inverse=levels,
        checks=("level", "level"),
        density=rho,
    )


def goal_seek_reference_pressure_outflow() -> GoalSeekCase:
    """G11 (boundary_outflow): the pressure of an ideal reference node (z 5 m) that sends 10 L/s
    through 200 m of 77.9 mm pipe to R2 (H 3 m): H_N = z + p/(ρg), so p = ρg(H₂ + h(Q) − z);
    the node's outflow into the network is the pipe's flow."""
    fluid, rho, nu = _fluid_a()
    line = Line(0.0779, 200.0)
    z, h2 = 5.0, 3.0
    target = 0.01
    p = rho * G * (h2 + line.head_loss(target, nu) - z)
    require_turbulent(nu, [(target, line)])
    bounds = (0.0, 600.0e3)
    if not bounds[0] < p < bounds[1]:
        raise ValueError("G11's pressure is outside its bounds")
    project = make_project(
        "ref-goal-seek-reference-pressure-outflow",
        "goal seek reference pressure outflow",
        fluid,
        [reference_node("RN1", z, 150.0e3), reservoir("R2", 0.0, h2)],
        [line.connect("L1", "RN1:port_1", "R2:port_1")],
    )

    def forward(x: Sequence[float]) -> list[float]:
        return [signed_flow(lambda q: line.head_loss(q, nu), z + x[0] / (rho * G) - h2)]

    name = "goal_seek_reference_pressure_outflow"
    return GoalSeekCase(
        name=name,
        description="G11: the reference-node pressure that sends 10 L/s into the network "
        "(boundary_outflow).",
        source=_source(name, "p = rho g (H2 + h(Q) - z_N)"),
        project=_json(project),
        variables=(component_variable("RN1", "pressure", *bounds),),
        goals=(goal("boundary_outflow", "RN1", target),),
        forward=forward,
        inverse=(p,),
        checks=("pressure",),
        density=rho,
    )


def goal_seek_surface_pressure_velocity() -> GoalSeekCase:
    """G20 (surfacePressure, link_velocity): the surface pressure of R1 (z 10 m, level 2 m)
    that drives 3 m/s through the smaller of two pipes in series in L1 (102.3 mm then 77.9 mm, a
    sudden reducer between them) to R2 (H 1.5 m). The largest velocity is the small pipe's,
    Q = 3 A₁; H₁ = z + level + p_s/(ρg), so p_s = ρg(H₂ + h(Q) − z − level), h = f₀(L₀/D₀)
    v₀²/2g + [f₁(L₁/D₁) + K_contraction] v₁²/2g (fluids contraction_sharp, Crane, on v₁)."""
    fluid, rho, nu = _fluid_a()
    (d0, l0), (d1, l1) = (0.1023, 40.0), (0.0779, 60.0)
    eps = 4.5e-5
    k_c = dv.k_sudden_contraction(d0, d1)
    z1, level1, h2 = 10.0, 2.0, 1.5

    def loss(q: float) -> float:
        return (
            dv.friction_head_loss(q, d0, l0, eps, nu)
            + dv.friction_head_loss(q, d1, l1, eps, nu)
            + dv.minor_head_loss(q, k_c, d1)
        )

    target = 3.0
    q = target * dv.area(d1)
    p_s = rho * G * (h2 + loss(q) - z1 - level1)
    dv.require_regime(q, d0, nu, "turbulent")
    bounds = (-50.0e3, 500.0e3)
    if not bounds[0] < p_s < bounds[1]:
        raise ValueError("G20's surface pressure is outside its bounds")
    project = make_project(
        "ref-goal-seek-surface-pressure-velocity",
        "goal seek surface pressure velocity",
        fluid,
        [reservoir("R1", z1, level1), reservoir("R2", 0.0, h2)],
        [
            connect(
                "L1",
                "R1:port_1",
                "R2:port_1",
                [custom_pipe(d0, l0, eps), custom_pipe(d1, l1, eps)],
                [fitting("reducer_sudden", pipe_index=0)],
            )
        ],
    )

    def forward(x: Sequence[float]) -> list[float]:
        qx = signed_flow(loss, z1 + level1 + x[0] / (rho * G) - h2)
        return [abs(qx) / dv.area(d1)]

    name = "goal_seek_surface_pressure_velocity"
    return GoalSeekCase(
        name=name,
        description="G20: the reservoir surface pressure that drives 3 m/s through the smaller "
        "pipe of a two-pipe connection (surfacePressure; link_velocity, the largest).",
        source=_source(
            name,
            "Q = v A_small; p_s = rho g (H2 + h(Q) - z - level), Colebrook per pipe, fluids "
            "contraction_sharp(Crane)",
        ),
        project=_json(project),
        variables=(component_variable("R1", "surfacePressure", *bounds),),
        goals=(goal("link_velocity", "L1", target),),
        forward=forward,
        inverse=(p_s,),
        checks=("pressure",),
        density=rho,
    )


# --- G16: a flow-controlled pump feeding a demand across its setpoint ---------------------------

G16_Q_SET, G16_MIN_SPEED, G16_MAX_SPEED = 0.02, 0.5, 0.9
G16_BOUNDS = (0.010, 0.032)
G16_Z_AF = 5.0
G16_H1 = 3.0


def goal_seek_controlled_pump_crossing() -> GoalSeekCase:
    """G16: the network of assigned_flow_flow_pump_max_speed (R1 H 3 m → SUCTION_A → PU1,
    curve_a, flow-controlled Q_set 20 L/s, s ∈ [0.5, 0.9], z 0.5 m → FLOW_PUMP_DISCHARGE → AF1,
    z 5 m). AF1's demand Q_a fixes the pump's flow (D12): below Q_set the pump runs at its maximum
    speed (X1), above it at its minimum (N1), and at Q_set both an active pump and the demand fix
    one flow: the pressure between them is undetermined (over-controlled, no steady state). The
    port pressure p(Q_a, s) = ρg(H₁ − h_s(Q_a) + s² H₀(Q_a/s) − h_d(Q_a) − z − v²/2g) jumps from
    p(Q_set, 0.9) down to p(Q_set, 0.5) there. With the target a third of the way from the
    min-speed value to the max-speed value at Q_set, no demand in [10, 32] L/s meets it: an
    unsolved crossing between a < Q_set < b, the closest value on the min-speed side."""
    fluid, rho, nu = _fluid_a()
    curve = curve_a()
    control = flow_control(G16_Q_SET, G16_MIN_SPEED)
    lines = (SUCTION_A, FLOW_PUMP_DISCHARGE)

    def pressure(q: float, s: float) -> float:
        egl = G16_H1 - lines[0].head_loss(q, nu) + el.pump_head(curve, s, q)
        egl -= lines[1].head_loss(q, nu)
        return dv.static_pressure(rho, egl, G16_Z_AF, lines[1].velocity(q))

    p_max, p_min = pressure(G16_Q_SET, G16_MAX_SPEED), pressure(G16_Q_SET, G16_MIN_SPEED)
    target = p_min + (p_max - p_min) / 3.0
    for state, q in (("max_speed", 0.999 * G16_Q_SET), ("min_speed", 1.001 * G16_Q_SET)):
        speed = el.control_state_speed(control, G16_MAX_SPEED, state)
        assert speed is not None
        lift = el.pump_head(curve, speed, q)
        problem = el.controlled_pump_state_problem(
            "on", curve, control, G16_MAX_SPEED, state, q, lift, -el.HTOL
        )
        if problem:
            raise ValueError(f"G16's pump {problem} at {q}")

    def forward(x: Sequence[float]) -> list[float]:
        if x[0] == G16_Q_SET:
            raise ValueError("no steady state at the setpoint")
        return [pressure(x[0], G16_MAX_SPEED if x[0] < G16_Q_SET else G16_MIN_SPEED)]

    name = "goal_seek_controlled_pump_crossing"
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        "goal seek controlled pump crossing",
        fluid,
        [
            reservoir("R1", 0.0, G16_H1),
            pump("PU1", 0.5, curve.id, speed=G16_MAX_SPEED, control=control),
            assigned_flow("AF1", G16_Z_AF, 0.012),
        ],
        [
            lines[0].connect("L1", "R1:port_1", "PU1:suction"),
            lines[1].connect("L2", "PU1:discharge", "AF1:port_1"),
        ],
        pump_library=[curve],
    )
    return GoalSeekCase(
        name=name,
        description="G16: a demand fed by a flow-controlled pump, whose port pressure jumps "
        "across the pump's setpoint, where no steady state exists (over-controlled): not met, "
        "unsolved_crossing, the closest value on the min-speed side.",
        source=_source(
            name,
            "p = rho g (H1 - h_s + s^2 H0(Q/s) - h_d - z - v^2/2g) at s = 0.9 below Q_set and "
            "s = 0.5 above (D11, D12); PCHIP curve",
        ),
        project=_json(project),
        variables=(component_variable("AF1", "flow", *G16_BOUNDS),),
        goals=(goal("port_pressure", "AF1", target, "port_1"),),
        forward=forward,
        inverse=None,
        checks=("flow",),
        density=rho,
        stop="unsolved_crossing",
        tight=False,
        data={"setpoint": G16_Q_SET, "pMax": p_max, "pMin": p_min},
    )


# --- G25-G32: equipment (docs/proposals/equipment-pressure-drop.md §7.3) -----------------------
#
# Every case's network is a closed-form equipment case (``derivations_equipment``) and its
# inverse the closed form §7.3 states. On the equipment line (EPANET water, Swamee-Jain, H₁ 12 m,
# H₂ 1 m) the flow Q* through E1 leaves the element the head h_E = H₁ − H₂ − h_lines(Q*), so the
# rating's coefficient there is c* = h_E/Q*², and each rating value that gives c* follows from
# c = ΔP_r/(ρ_r g Q_r²) with the other two held. A Cv or Kv gives c = c₁/value², c₁ = c of the
# coefficient 1 from its definition with the suite's reference water (``element_laws``):
# c₁ = 1.76758281860e8 s²/m⁵ for a Cv and 1.32248132749e8 for a Kv, which is 3.1e-10 above
# fluids' constants 1.76758281804e8 and 1.32248132708e8 (the solver's conversion, proposal
# §3.1). The inverse is 1.56e-10 higher with the suite's c₁: G30's Cv* = 81.0723929515 here
# against 81.0723929388 with fluids', G31's Kv* = 84.1004736267 against 84.1004736136 (the
# proposal prints both), far inside every goal tolerance. The Swamee-Jain cases differ from the
# proposal's prints, through h_line: the rating inverses (G25-G27, G32's values) by up to 3e-7
# (relative; G32's loss target by 3.3e-7) and the level inverses (G28, G29) by up to 5e-6 (about
# 5.4e-6 m): the suite's Swamee-Jain is fluids' (6.97/Re)^0.9 form, the solver's EPANET's
# 5.74/Re^0.9 (CLAUDE.md D7).

EQUIPMENT_FLOW_TARGET = 0.016
"""m³/s: G25-G27, G30 and G32's flow through E1 (test input)."""
EQUIPMENT_LINE_NU = de.NU_EPANET
"""m²/s: the equipment line's fluid (EPANET water)."""


def _equipment_line_head(q: float) -> float:
    """h_E = H₁ − H₂ − h_L1(Q) − h_L2(Q) on the equipment line (Swamee-Jain): the head the
    element takes at flow Q."""
    series = de.line_series(de.e1_rating())
    method: FrictionMethod = "swamee_jain"
    return (
        series.h1
        - series.h2
        - series.inlet.head_loss(q, EQUIPMENT_LINE_NU, method)
        - series.outlet.head_loss(q, EQUIPMENT_LINE_NU, method)
    )


def _equipment_line_flow(rating: el.EquipmentRating) -> float:
    return de.line_series(rating).flow(EQUIPMENT_LINE_NU, "swamee_jain")


def _equipment_line_project() -> dict[str, Any]:
    return _json(de.equipment_line().project)


def _rated(values: dict[str, float]) -> el.EquipmentRating:
    return rated_point(values["pressureLoss"], values["flow"], values["density"])


E1_VALUES = {
    "pressureLoss": de.E1_POINT[0],
    "flow": de.E1_POINT[1],
    "density": de.rating_water_density(),
}
"""E1's rated point as the case holds it (proposal §7.1)."""
RATED_BOUNDS = {
    "pressureLoss": (5.0e3, 5.0e5),
    "flow": (1.5e-3, 0.15),
    "density": (500.0, 2000.0),
}
"""The bounds of each rating variable: the web's default ranges about E1's values, [v/10, 10v]
for the rated drop and flow, about [v/2, 2v] for the density (proposal §6.4; test inputs)."""
RATED_CHECKS: dict[str, VariableCheck] = {
    "pressureLoss": "pressure",
    "flow": "flow",
    "density": "forward",
}
"""A rated pressure drop is judged as a pressure (D6), a rated flow as a flow; a rated density
has no D6 quantity, so the forward model at the value found is judged."""


def _rated_inverse(part: str) -> float:
    """The value of E1's rating part that passes EQUIPMENT_FLOW_TARGET (proposal §7.3): c* =
    h_E/Q*², then ΔP_r* = ρ_r g c* Q_r², Q_r* = √(ΔP_r/(ρ_r g c*)), ρ_r* = ΔP_r/(g c* Q_r²)."""
    q = EQUIPMENT_FLOW_TARGET
    c = _equipment_line_head(q) / (q * q)
    dp, q_r, rho_r = (E1_VALUES[k] for k in ("pressureLoss", "flow", "density"))
    if part == "pressureLoss":
        return rho_r * G * c * q_r * q_r
    if part == "flow":
        return math.sqrt(dp / (rho_r * G * c))
    return dp / (G * c * q_r * q_r)


def _goal_seek_rated(part: str, label: str) -> GoalSeekCase:
    """E1's rating.{part} → E1's flow 16 L/s on the equipment line (§7.3)."""
    name = f"goal_seek_equipment_rated_{label}"
    inverse = _rated_inverse(part)
    lower, upper = RATED_BOUNDS[part]
    if not lower < inverse < upper:
        raise ValueError(f"{name}: the inverse {inverse} is outside its bounds")

    def forward(x: Sequence[float]) -> list[float]:
        return [_equipment_line_flow(_rated({**E1_VALUES, part: x[0]}))]

    return GoalSeekCase(
        name=name,
        description=(
            f"The rated {label.replace('_', ' ')} of an equipment item that passes 16 L/s on "
            "the equipment line (one value of a rated point; the other two held)."
        ),
        source=_source(
            name,
            "c* = h_E/Q*^2, h_E = H1 - H2 - h_lines(Q*) (Darcy-Weisbach + Swamee-Jain), then "
            "the rating value from c = dP_r/(rho_r g Q_r^2)",
        ),
        project=_equipment_line_project(),
        variables=(component_variable("E1", f"rating.{part}", lower, upper),),
        goals=(goal("equipment_flow", "E1", EQUIPMENT_FLOW_TARGET),),
        forward=forward,
        inverse=(inverse,),
        checks=(RATED_CHECKS[part],),
        density=de.EPANET_DENSITY,
        data={"c": _equipment_line_head(EQUIPMENT_FLOW_TARGET) / EQUIPMENT_FLOW_TARGET**2},
    )


def goal_seek_equipment_rated_pressure_loss() -> GoalSeekCase:
    """G25: ΔP_r* = ρ_r g c* Q_r² (proposal §7.3: 64,383.9587021 Pa)."""
    return _goal_seek_rated("pressureLoss", "pressure_loss")


def goal_seek_equipment_rated_flow() -> GoalSeekCase:
    """G26: Q_r* = √(ΔP_r/(ρ_r g c*)) (proposal §7.3: 0.0132186597 m³/s)."""
    return _goal_seek_rated("flow", "flow")


def goal_seek_equipment_rated_density() -> GoalSeekCase:
    """G27: ρ_r* = ΔP_r/(g c* Q_r²) (proposal §7.3: 775.8940593 kg/m³)."""
    return _goal_seek_rated("density", "density")


PORTS_LEVEL_BOUNDS = (0.0, 10.0)
"""m: R1's level on equipment_ports_differ (base 5 m; test input)."""


def _ports_state(level: float) -> tuple[float, dict[str, float | None]]:
    """(Q, E1's result) on equipment_ports_differ with R1's level ``level`` (brentq)."""
    series = de.ports_series(level)
    q = series.flow(EQUIPMENT_LINE_NU, "swamee_jain")
    at = series.ports(q, EQUIPMENT_LINE_NU, "swamee_jain")
    return q, de.equipment_result(series.element, at, de.EPANET_DENSITY)


def _ports_level(q: float) -> float:
    """R1's level that passes Q: H₂ + h_L1(Q) + c Q² + h_L2(Q) − z_R1."""
    series = de.ports_series()
    return series.h2 + series.loss(q, EQUIPMENT_LINE_NU, "swamee_jain") - series.z1


def _goal_seek_ports(quantity: Literal["pressure_drop", "pressure_loss"]) -> GoalSeekCase:
    """R1's level → E1's static pressure drop 130 kPa (G28), or its pressure loss 100 kPa (G29),
    on equipment_ports_differ (outlet port 2 m up, a 77.9 mm outlet pipe after 102.3 mm). With
    c from E1's rating, ρ = 1000 kg/m³ and A_in, A_out the pipes' areas:

        drop(Q) = Q² [ρ g c + ρ (1/A_out² − 1/A_in²)/2] + ρ g (z_out − z_in)
        loss(Q) = ρ g c Q² = ΔP_r (ρ/ρ_r)(Q/Q_r)²

    so Q* in closed form from the target and the level = H₂ + h_line(Q*) − z_R1 (proposal §7.3:
    1.91286791 m and 1.06637058 m). A reader of the wrong field misses either by 20 %."""
    rho = de.EPANET_DENSITY
    e1 = de.ports_series().element
    c = el.equipment_coefficient(e1.rating)
    a_in, a_out = de.PORTS_IN.area, de.PORTS_OUT.area
    if quantity == "pressure_drop":
        target = 130_000.0
        dz = de.PORTS_OUTLET_Z - de.PORTS_Z
        q = math.sqrt(
            (target - rho * G * dz) / (rho * G * c + rho * (1.0 / a_out**2 - 1.0 / a_in**2) / 2.0)
        )
        field_name = "pressureDrop"
    else:
        target = 100_000.0
        q = math.sqrt(target / (rho * G * c))
        field_name = "pressureLoss"
    level = _ports_level(q)
    name = f"goal_seek_equipment_{quantity}_level"

    def forward(x: Sequence[float]) -> list[float]:
        value = _ports_state(x[0])[1][field_name]
        assert value is not None
        return [value]

    if not PORTS_LEVEL_BOUNDS[0] < level < PORTS_LEVEL_BOUNDS[1]:
        raise ValueError(f"{name}: the level {level} is outside its bounds")
    other = "pressureLoss" if field_name == "pressureDrop" else "pressureDrop"
    other_value = _ports_state(level)[1][other]
    assert other_value is not None
    if not abs(other_value - target) > 0.2 * target:
        raise ValueError(f"{name}: the two goals must differ by more than 20 %")
    return GoalSeekCase(
        name=name,
        description=(
            f"R1's level that gives an equipment item a static pressure "
            f"{'drop' if quantity == 'pressure_drop' else 'loss'} target, its outlet port 2 m "
            "above its inlet and its outlet pipe smaller: the static drop holds the elevation "
            "and velocity-head terms, the loss does not."
        ),
        source=_source(
            name,
            "drop(Q) = Q^2 [rho g c + rho (1/A_out^2 - 1/A_in^2)/2] + rho g dz; loss(Q) = rho g "
            "c Q^2; level = H2 + h_line(Q*) - z1, Darcy-Weisbach + Swamee-Jain",
        ),
        project=_json(de.equipment_ports_differ().project),
        variables=(component_variable("R1", "liquidLevel", *PORTS_LEVEL_BOUNDS),),
        goals=(goal(f"equipment_{quantity}", "E1", target),),
        forward=forward,
        inverse=(level,),
        checks=("level",),
        density=rho,
        data={"flow": q, "otherValue": other_value},
    )


def goal_seek_equipment_pressure_drop_level() -> GoalSeekCase:
    """G28: R1's level → E1's static pressure drop 130 kPa."""
    return _goal_seek_ports("pressure_drop")


def goal_seek_equipment_pressure_loss_level() -> GoalSeekCase:
    """G29: R1's level → E1's pressure loss 100 kPa."""
    return _goal_seek_ports("pressure_loss")


def coefficient_c1(kind: Literal["Cv", "Kv"]) -> float:
    """c₁ = c · value², s²/m⁵ (c ∝ 1/value²): the suite's, from the definition with its
    reference water (``element_laws.equipment_coefficient`` of the coefficient 1)."""
    return el.equipment_coefficient(rated_coefficient(kind, 1.0))


def goal_seek_equipment_cv() -> GoalSeekCase:
    """G30: E1's Cv → 16 L/s on equipment_cv_glycol (30 % MEG at 5 °C, Colebrook):
    h_E = H₁ − H₂ − h_lines(Q*), Cv* = Q* √(c₁/h_E) (proposal §7.3: 81.0723929515 with the
    suite's c₁)."""
    case = de.equipment_cv_glycol()
    rho, mu, _ = dv.fluid_state(case.project.fluid)
    nu = mu / rho
    q = EQUIPMENT_FLOW_TARGET
    series = de.line_series(rated_coefficient("Cv", de.E1_CV))
    h_e = (
        series.h1
        - series.h2
        - series.inlet.head_loss(q, nu, "colebrook")
        - series.outlet.head_loss(q, nu, "colebrook")
    )
    cv = q * math.sqrt(coefficient_c1("Cv") / h_e)
    bounds = (9.0, 900.0)
    name = "goal_seek_equipment_cv"

    def forward(x: Sequence[float]) -> list[float]:
        return [de.line_series(rated_coefficient("Cv", x[0])).flow(nu, "colebrook")]

    return GoalSeekCase(
        name=name,
        description=(
            "The Cv of an equipment item that passes 16 L/s of 30 % ethylene glycol on the "
            "equipment line (a Cv rating is a rated point on water: c = c1/Cv^2)."
        ),
        source=_source(
            name,
            "h_E = H1 - H2 - h_lines(Q*) (Darcy-Weisbach + Colebrook, CoolProp MEG); Cv* = Q* "
            "sqrt(c1/h_E), c1 = 1 psi/(rho_w g (1 US gpm)^2)",
        ),
        project=_json(case.project),
        variables=(component_variable("E1", "rating.value", *bounds),),
        goals=(goal("equipment_flow", "E1", q),),
        forward=forward,
        inverse=(cv,),
        checks=("forward",),
        density=rho,
        data={"c1": coefficient_c1("Cv")},
    )


def goal_seek_equipment_kv() -> GoalSeekCase:
    """G31: E1's Kv → its pressure loss 80 kPa on equipment_kv_definition (reference water,
    Colebrook): h* = Δp*/(ρg), Q* from H₁ − H₂ − h* = h_lines(Q*) (brentq), Kv* = Q* √(c₁/h*)
    (proposal §7.3: 84.1004736267 with the suite's c₁)."""
    case = de.equipment_kv_definition()
    project = case.project
    rho, mu, _ = dv.fluid_state(project.fluid)
    nu = mu / rho
    level1 = de.kv_definition_level()
    series = de.kv_series(rated_coefficient("Kv", de.E1_KV), level1)
    target = 80_000.0
    h_star = target / (rho * G)
    q = dv.solve_flow(
        lambda q: series.inlet.head_loss(q, nu) + series.outlet.head_loss(q, nu),
        series.h1 - series.h2 - h_star,
    )
    kv = q * math.sqrt(coefficient_c1("Kv") / h_star)
    bounds = (6.0, 600.0)
    name = "goal_seek_equipment_kv"

    def forward(x: Sequence[float]) -> list[float]:
        trial = de.kv_series(rated_coefficient("Kv", x[0]), level1)
        qx = trial.flow(nu, "colebrook")
        return [rho * G * el.equipment_head(trial.element.rating, qx)]

    return GoalSeekCase(
        name=name,
        description=(
            "The Kv of an equipment item whose pressure loss is 80 kPa on the Kv definition "
            "line (a Kv rating is a rated point on water: c = c1/Kv^2)."
        ),
        source=_source(
            name,
            "h* = dp*/(rho g); Q* from H1 - H2 - h* = h_lines(Q*) (Darcy-Weisbach + Colebrook, "
            "brentq); Kv* = Q* sqrt(c1/h*), c1 = 1 bar/(rho_w g (1 m3/h)^2)",
        ),
        project=_json(project),
        variables=(component_variable("E1", "rating.value", *bounds),),
        goals=(goal("equipment_pressure_loss", "E1", target),),
        forward=forward,
        inverse=(kv,),
        checks=("forward",),
        density=rho,
        data={"c1": coefficient_c1("Kv"), "flow": q},
    )


G32_SCENARIO_LOSS = 60_000.0
"""Pa: S1's whole rating of E1 is its own at this rated pressure drop (test input)."""


def goal_seek_equipment_scenario_parts() -> GoalSeekCase:
    """G32 (proposal §5.2, §7.3): the equipment line on scenario S1, whose one override is E1's
    whole rating (its own at 60 kPa); variables rating.pressureLoss and rating.flow, goals E1's
    flow 16 L/s and its pressure loss at that flow, ρ g h_E = ρ g c* Q*² (73,320.43 Pa), so the
    targets agree. The two variables act together through c alone (decision 15): every pair
    with ΔP_r/Q_r² = ρ_r g c* meets both, so the values found need not be unique; ``inverse``
    is the one at Q_r = 15 L/s. Not in MET_CASES: the test checks what the design fixes
    whatever the values found (both overrides one whole rating holding both found values)."""
    q = EQUIPMENT_FLOW_TARGET
    c = _equipment_line_head(q) / (q * q)
    loss = de.EPANET_DENSITY * G * c * q * q
    project = _equipment_line_project()
    whole = {**E1_VALUES, "kind": "point", "pressureLoss": G32_SCENARIO_LOSS}
    project["scenarios"] = [
        {
            "id": "S1",
            "name": "Another datasheet",
            "overrides": [
                {"kind": "component", "componentId": "E1", "field": "rating", "value": whole}
            ],
        }
    ]

    def forward(x: Sequence[float]) -> list[float]:
        rating = _rated({**E1_VALUES, "pressureLoss": x[0], "flow": x[1]})
        qx = _equipment_line_flow(rating)
        return [qx, de.EPANET_DENSITY * G * el.equipment_head(rating, qx)]

    name = "goal_seek_equipment_scenario_parts"
    return GoalSeekCase(
        name=name,
        description=(
            "Two values of one rating that a scenario sets whole, varied together: both "
            "variables' overrides are the scenario's whole rating holding both values found."
        ),
        source=_source(name, "c* = h_E/Q*^2 on the equipment line; dP_r/Q_r^2 = rho_r g c*"),
        project=project,
        variables=(
            component_variable("E1", "rating.pressureLoss", *RATED_BOUNDS["pressureLoss"]),
            component_variable("E1", "rating.flow", *RATED_BOUNDS["flow"]),
        ),
        goals=(
            goal("equipment_flow", "E1", q),
            goal("equipment_pressure_loss", "E1", loss),
        ),
        forward=forward,
        inverse=(_rated_inverse("pressureLoss"), E1_VALUES["flow"]),
        checks=("forward", "forward"),
        density=de.EPANET_DENSITY,
        tight=False,
        scenario_id="S1",
        start=(G32_SCENARIO_LOSS, E1_VALUES["flow"]),
        data={"whole": whole, "replacedOverride": 0},
    )


# --- G33-G39: orifice plates (docs/proposals/orifice-plate.md §5.2, §7.3) ----------------------


def _liquid_a_state() -> tuple[float, float]:
    rho, mu, _ = dv.fluid_state(do.liquid_a())
    return rho, mu


def bore_for_head(template: el.OrificeLaw, q: float, h: float, lower: float, upper: float) -> float:
    """The bore d whose plate takes h at flow q on the template's pipe and fluid: K(C_L(d))
    strictly decreases in d at a fixed flow (proposal §3.1, R4), so one brentq in [lower,
    upper]."""

    def excess(d: float) -> float:
        return replace(template, d_bore=d).head(q) - h

    return bisect(excess, lower, upper)


def bore_bounds(d_pipe: float) -> tuple[float, float]:
    """[0.1D, 0.75D], ISO 5167-2's β range: the web's default bounds of a bore (proposal §6 W6)."""
    return 0.1 * d_pipe, 0.75 * d_pipe


def _line_head(series: do.Series, q: float, rho: float, mu: float) -> float:
    """The head the plate takes on a series line at flow q: H₁ − H₂ − h_L1(q) − h_L2(q)."""
    nu = mu / rho
    return (
        series.h1(rho)
        - series.h2
        - series.inlet.head_loss(q, nu, "colebrook")
        - series.outlet.head_loss(q, nu, "colebrook")
    )


ORIFICE_FLOW_TARGET = 0.015
"""m³/s: G33 and G34's flow through OR1 on the orifice line (test input)."""


def goal_seek_orifice_bore_flow() -> GoalSeekCase:
    """G33: OR1's boreDiameter → its flow 15 L/s on orifice_line (ISO's C, flange taps):
    h* = H₁ − H₂ − h_lines(Q*), then d* with K(C_L(d*, Re*)) v*²/2g = h* (brentq; Re* fixed by
    Q* and D). Proposal §7.3: h* 7.90629233124 m, K* 46.5611093191, d* 46.7639723052 mm."""
    rho, mu = _liquid_a_state()
    series = do.line_series()
    q = ORIFICE_FLOW_TARGET
    h = _line_head(series, q, rho, mu)
    bounds = bore_bounds(series.inlet.d)
    bore = bore_for_head(series.law(rho, mu), q, h, *bounds)
    name = "goal_seek_orifice_bore_flow"

    def forward(x: Sequence[float]) -> list[float]:
        trial = do.line_series(do.line_orifice(bore=x[0]))
        return [trial.flow(rho, mu, "colebrook")]

    return GoalSeekCase(
        name=name,
        description=(
            "The bore of an orifice plate on ISO 5167-2's coefficient that passes 15 L/s on "
            "the orifice line (sizing a restriction orifice)."
        ),
        source=_source(
            name,
            "h* = H1 - H2 - h_lines(Q*) (Darcy-Weisbach + Colebrook); d* by brentq on "
            "K(C_L(d, Re*)) v*^2/2g = h*, C_L ISO 5167-2 eq. (4) at D and D/2",
        ),
        project=_json(do.orifice_line().project),
        variables=(component_variable("OR1", "boreDiameter", *bounds),),
        goals=(goal("orifice_flow", "OR1", q),),
        forward=forward,
        inverse=(bore,),
        checks=("forward",),
        density=rho,
        data={"head": h, "k": h * 2.0 * G / dv.velocity(q, series.inlet.d) ** 2},
    )


ENTERED_C_BOUNDS = (0.3, 1.0)
"""G34: [v/2, min(2v, 1)] about the case's entered C 0.6, the web's default (proposal §6 W6)."""


def goal_seek_orifice_entered_c_flow() -> GoalSeekCase:
    """G34: OR1's dischargeCoefficient → its flow 15 L/s on orifice_entered_c (no taps, so C_L =
    C): K* as G33's, C* = the C whose K is K* (``element_laws.orifice_c_from_k``, fluids'
    K_to_discharge_coefficient). Proposal §7.3: C* 0.499134545651."""
    rho, mu = _liquid_a_state()
    element = do.line_orifice(taps=None, entered=do.ENTERED_C)
    series = do.line_series(element)
    q = ORIFICE_FLOW_TARGET
    d_pipe = series.inlet.d
    k = _line_head(series, q, rho, mu) * 2.0 * G / dv.velocity(q, d_pipe) ** 2
    c = el.orifice_c_from_k(d_pipe, element.bore_diameter, k)
    name = "goal_seek_orifice_entered_c_flow"

    def forward(x: Sequence[float]) -> list[float]:
        trial = do.line_series(do.line_orifice(taps=None, entered=x[0]))
        return [trial.flow(rho, mu, "colebrook")]

    return GoalSeekCase(
        name=name,
        description=(
            "The entered discharge coefficient of a restriction orifice (no taps) that passes "
            "15 L/s on the orifice line (the C a calibration must show)."
        ),
        source=_source(
            name,
            "K* = 2g h*/v*^2, h* = H1 - H2 - h_lines(Q*) (Darcy-Weisbach + Colebrook); C* = "
            "sqrt((1 - b^4)/(b^4 ((1 + sqrt K*)^2 - 1)))",
        ),
        project=_json(do.orifice_entered_c().project),
        variables=(component_variable("OR1", "dischargeCoefficient", *ENTERED_C_BOUNDS),),
        goals=(goal("orifice_flow", "OR1", q),),
        forward=forward,
        inverse=(c,),
        checks=("forward",),
        density=rho,
        data={"k": k},
    )


METER_LINES = (Line(0.1023, 20.0), Line(0.1023, 20.0))
METER_DEMAND = 0.012
"""m³/s: G35's assigned demand (D12; test input)."""
METER_TARGET = 50_000.0
"""Pa: G35's reading at the flange taps (test input)."""
METER_START_BORE = 0.06
"""m: G35's plate as the case holds it (β 0.587; test input)."""


def meter_project(bore: float = METER_START_BORE) -> dict[str, Any]:
    """R1 (z 20 m, level 10 m) → 102.3 mm × 20 m → OR1 (z 0, flange taps, ISO's C) → 102.3 mm ×
    20 m → D, an assigned demand of 12 L/s at z 0 (D12); liquid A."""
    project = make_project(
        "ref-goal-seek-orifice-meter",
        "Sizing an orifice meter",
        do.liquid_a(),
        [
            reservoir("R1", 20.0, 10.0),
            orifice("OR1", 0.0, bore, taps="flange"),
            assigned_flow("D", 0.0, METER_DEMAND),
        ],
        [
            METER_LINES[0].connect("L1", "R1:port_1", "OR1:inlet"),
            METER_LINES[1].connect("L2", "OR1:outlet", "D:port_1"),
        ],
    )
    return _json(project)


def meter_law(bore: float) -> el.OrificeLaw:
    rho, mu = _liquid_a_state()
    return el.OrificeLaw(METER_LINES[0].d, bore, rho, mu, None, "flange")


def meter_bore() -> float:
    """d* with the reading (1 − β⁴)/(C_M² β⁴) ρ v|v|/2 = 50 kPa at the demand's 12 L/s, C_M ISO's
    at the flange taps (brentq: the reading falls as the bore grows)."""

    def excess(d: float) -> float:
        reading = meter_law(d).differential(METER_DEMAND)
        assert reading is not None
        return reading - METER_TARGET

    return bisect(excess, *bore_bounds(METER_LINES[0].d))


def goal_seek_orifice_meter_bore() -> GoalSeekCase:
    """G35: OR1's boreDiameter → its reading 50 kPa at the flange taps, the flow fixed by an
    assigned demand of 12 L/s (sizing a meter): ISO eq. (1) solved for d at Q = 12 L/s. Proposal
    §7.3: d* 49.5345909038 mm; fluids' differential_pressure_meter_solver gives the same bore
    (test_goal_seek)."""
    rho, _ = _liquid_a_state()
    bore = meter_bore()
    name = "goal_seek_orifice_meter_bore"

    def forward(x: Sequence[float]) -> list[float]:
        reading = meter_law(x[0]).differential(METER_DEMAND)
        assert reading is not None
        return [reading]

    return GoalSeekCase(
        name=name,
        description=(
            "The bore of a flange-tapped orifice meter that reads 50 kPa at a design flow of "
            "12 L/s, the flow fixed by an assigned demand."
        ),
        source=_source(
            name,
            "dp = (1 - b^4)/(C_M^2 b^4) rho v^2/2 (ISO 5167-2 eq. (1), eps = 1) at Q = 12 L/s, "
            "C_M ISO 5167-2 eq. (4) at flange taps; d* by brentq",
        ),
        project=meter_project(),
        variables=(component_variable("OR1", "boreDiameter", *bore_bounds(METER_LINES[0].d)),),
        goals=(goal("orifice_differential_pressure", "OR1", METER_TARGET),),
        forward=forward,
        inverse=(bore,),
        checks=("forward",),
        density=rho,
    )


BYPASS_TARGET = 0.003
"""m³/s: G36's bypass flow through RO (test input)."""


def bypass_state(q_b: float) -> tuple[float, float]:
    """(H_T1, h_RO) with a bypass flow q_b on orifice_min_flow_bypass: the pump's flow Q_p from
    H_R1 − h_L1(Q_p) + H₀(Q_p) − h_L2(Q_p) = H_R2 + h_L3(Q_p − q_b) (brentq, decreasing), then
    h_RO = H_T1 − H_R1 − h_LB1(q_b) − h_LB2(q_b)."""
    rho, mu = _liquid_a_state()
    nu = mu / rho

    def residual(q_p: float) -> float:
        return do.bypass_pump_side(q_p, nu) - (
            do.BYPASS_H2 + do.BYPASS_PROCESS.head_loss(q_p - q_b, nu)
        )

    q_p = bisect(residual, q_b, 0.2)
    h_t1 = do.bypass_pump_side(q_p, nu)
    h_ro = (
        h_t1
        - do.BYPASS_H1
        - do.BYPASS_TO_RO.head_loss(q_b, nu)
        - do.BYPASS_FROM_RO.head_loss(q_b, nu)
    )
    return h_t1, h_ro


def goal_seek_orifice_bypass_bore() -> GoalSeekCase:
    """G36: RO's boreDiameter → a bypass flow of 3 L/s on orifice_min_flow_bypass (sizing a
    pump's minimum-flow orifice): ``bypass_state``, then d* from h_RO* (brentq). Proposal §7.3:
    EGL T1 28.4660973619 m, h_RO* 25.83728685 m, K* 263.8590807, d* 16.2563444213 mm."""
    rho, mu = _liquid_a_state()
    h_t1, h_ro = bypass_state(BYPASS_TARGET)
    d_pipe = do.BYPASS_TO_RO.d
    bounds = bore_bounds(d_pipe)
    template = el.OrificeLaw(d_pipe, do.BYPASS_BORE, rho, mu)
    bore = bore_for_head(template, BYPASS_TARGET, h_ro, *bounds)
    name = "goal_seek_orifice_bypass_bore"

    def forward(x: Sequence[float]) -> list[float]:
        project = do.bypass_project("ref-trial", "trial", bore=x[0])
        return [do.solve_bypass(project).q_bypass]

    return GoalSeekCase(
        name=name,
        description=(
            "The bore of a pump's minimum-flow restriction orifice that passes 3 L/s back to "
            "the suction reservoir."
        ),
        source=_source(
            name,
            "Q_p from the pump side against H_R2 + h_L3(Q_p - Q_b*) (brentq, PCHIP curve); h_RO* "
            "= H_T1 - H_R1 - h_bypass_lines(Q_b*); d* by brentq on the plate's law",
        ),
        project=_json(do.orifice_min_flow_bypass().project),
        variables=(component_variable("RO", "boreDiameter", *bounds),),
        goals=(goal("orifice_flow", "RO", BYPASS_TARGET),),
        forward=forward,
        inverse=(bore,),
        checks=("forward",),
        density=rho,
        data={"egl": h_t1, "head": h_ro},
    )


CORNER_C_BOUNDS = (0.3, 0.95)
"""G37: C's bounds, inside decision 17 (c) at the upper bound (0.95 r_max < 1 for r_max about
1.0225 at β 0.75; test input)."""
CORNER_FLOW_TARGET = 0.018
"""m³/s: G37's flow (test input)."""


def goal_seek_orifice_c_at_corner_taps() -> GoalSeekCase:
    """G37: OR1's dischargeCoefficient on C12's network on ISO's C (corner taps) → its flow
    18 L/s: the case holds no C, so the search starts in the middle of the bounds (0.625, linear,
    decision 21); the C found is the C at the corner taps, C* = C_L*/r, C_L* the C whose K is
    K* = 2g h*/v*² and r = C_ISO(D and D/2)/C_ISO(corner) at Re* (decision 13). Proposal §7.3:
    h* 0.912464598857 m, K* 3.73167645722, C_L* 0.533852485837, r 1.020983626357 at Re
    223,582.36, C* 0.522880555629 (C_L* itself would be 2.1 % off)."""
    rho, mu = _liquid_a_state()
    series = do.corner_series(entered=None)
    q = CORNER_FLOW_TARGET
    d_pipe = series.inlet.d
    h = _line_head(series, q, rho, mu)
    k = h * 2.0 * G / dv.velocity(q, d_pipe) ** 2
    c_l = el.orifice_c_from_k(d_pipe, do.CORNER_BORE, k)
    ratio = replace(series.law(rho, mu), entered=1.0).ratio(q)
    assert ratio is not None
    c = c_l / ratio
    lower, upper = CORNER_C_BOUNDS
    name = "goal_seek_orifice_c_at_corner_taps"

    def forward(x: Sequence[float]) -> list[float]:
        return [do.corner_series(entered=x[0]).flow(rho, mu, "colebrook")]

    return GoalSeekCase(
        name=name,
        description=(
            "The discharge coefficient at the corner taps of a beta 0.75 meter on ISO 5167-2's "
            "coefficient that passes 18 L/s: the search starts in the middle of its bounds, and "
            "the value found is moved to D and D/2 tappings for the loss."
        ),
        source=_source(
            name,
            "K* = 2g h*/v*^2, h* = H1 - H2 - h_lines(Q*) (Darcy-Weisbach + Colebrook); C_L* from "
            "K*; C* = C_L*/r, r = C_ISO(D and D/2)/C_ISO(corner) at Re*, eq. (4)",
        ),
        project=_json(
            series.project(
                "ref-goal-seek-orifice-corner",
                "Calibrating a corner-tapped meter",
                do.liquid_a(),
                "colebrook",
            )
        ),
        variables=(component_variable("OR1", "dischargeCoefficient", lower, upper),),
        goals=(goal("orifice_flow", "OR1", q),),
        forward=forward,
        inverse=(c,),
        checks=("forward",),
        density=rho,
        start=(0.5 * (lower + upper),),
        start_source=("middle",),
        data={"head": h, "k": k, "cLoss": c_l, "ratio": ratio},
    )


ORIFICE_LEVEL_BOUNDS = (0.0, 5.0)
"""m: R1's level on the orifice line (base 2 m; test input)."""
WHAT = {"pressureLoss": "permanent pressure loss", "pressureDrop": "static pressure drop"}


def _orifice_level_case(
    quantity: Literal["orifice_pressure_loss", "orifice_pressure_drop"],
) -> GoalSeekCase:
    """G38: R1's level → OR1's pressure loss 60 kPa on orifice_line: h* = Δϖ/(ρg), Q* from the
    plate's law alone (brentq), level* = H₂ + h_L1(Q*) + h* + h_L2(Q*) − z₁ (proposal §7.3:
    h* 6.13055839466 m, Q* 0.01644422884743, level* 0.814811461525 m).
    G39: R1's level → OR1's static pressure drop 70 kPa on orifice_outlet_bore_differs (the
    outlet pipe a size up, ports at one elevation): Q* from ρg h(Q) + ρ(v_out² − v_in²)/2 =
    70 kPa (brentq), level* = H₂ + loss(Q*) − z₁ (proposal §7.3: Q* 0.01800008371611, level*
    1.20165988673 m; the loss there 71,928.34287 Pa, so a swapped reader misses by 2.8 %)."""
    rho, mu = _liquid_a_state()
    if quantity == "orifice_pressure_loss":
        series = do.line_series()
        case = do.orifice_line()
        target = 60_000.0
        q = el.orifice_flow_at_head(series.law(rho, mu), target / (rho * G))
        field_name, other = "pressureLoss", "pressureDrop"
        name = "goal_seek_orifice_pressure_loss_level"
    else:
        series = do.line_series(outlet=do.LINE_OUT_WIDE)
        case = do.orifice_outlet_bore_differs()
        target = 70_000.0
        law = series.law(rho, mu)
        a_in, a_out = series.inlet.area, series.outlet.area

        def drop(q: float) -> float:
            return rho * G * law.head(q) + rho * (q * q) * (1.0 / a_out**2 - 1.0 / a_in**2) / 2.0

        q = bisect(lambda x: drop(x) - target, 1.0e-6, 1.0)
        field_name, other = "pressureDrop", "pressureLoss"
        name = "goal_seek_orifice_pressure_drop_level"
    level = series.h2 + series.loss(q, rho, mu, "colebrook") - series.z1

    def state(level1: float) -> dict[str, float | str | None]:
        trial = replace(series, level1=level1)
        qx = trial.flow(rho, mu, "colebrook")
        at = trial.ports(qx, rho, mu, "colebrook")
        return do.orifice_result(trial.element, at, rho, mu)

    def forward(x: Sequence[float]) -> list[float]:
        value = state(x[0])[field_name]
        assert isinstance(value, float)
        return [value]

    if not ORIFICE_LEVEL_BOUNDS[0] < level < ORIFICE_LEVEL_BOUNDS[1]:
        raise ValueError(f"{name}: the level {level} is outside its bounds")
    other_value = state(level)[other]
    assert isinstance(other_value, float)
    return GoalSeekCase(
        name=name,
        description=(
            f"R1's level that gives an orifice plate a {WHAT[field_name]} target on the "
            "orifice line."
        ),
        source=_source(
            name,
            "Q* from the plate's law (loss) or rho g h(Q) + rho (v_out^2 - v_in^2)/2 (static "
            "drop), brentq; level* = H2 + h_lines(Q*) + h_or(Q*) - z1, Darcy-Weisbach + Colebrook",
        ),
        project=_json(case.project),
        variables=(component_variable("R1", "liquidLevel", *ORIFICE_LEVEL_BOUNDS),),
        goals=(goal(quantity, "OR1", target),),
        forward=forward,
        inverse=(level,),
        checks=("level",),
        density=rho,
        data={"flow": q, "otherValue": other_value},
    )


def goal_seek_orifice_pressure_loss_level() -> GoalSeekCase:
    """G38: R1's level → OR1's permanent pressure loss 60 kPa (``_orifice_level_case``)."""
    return _orifice_level_case("orifice_pressure_loss")


def goal_seek_orifice_pressure_drop_level() -> GoalSeekCase:
    """G39: R1's level → OR1's static pressure drop 70 kPa (``_orifice_level_case``)."""
    return _orifice_level_case("orifice_pressure_drop")


# --- G40-G44: pressure relief valves (pressure-relief-valve.md §5, §7.3) -------------------------


def _relief_fluid() -> tuple[float, float]:
    rho, mu, _ = dv.fluid_state(dr.liquid_a())
    return rho, mu


def _b_json(name: str, element: Any) -> dict[str, Any]:
    return _json(dr.b_project(f"ref-{name.replace('_', '-')}", name.replace("_", " "), element))


def _b_relief_head(q: float, nu: float) -> float:
    """Network B at loop flow q: the head the relief valve takes, H(q) less the loop's pipes."""
    return el.pump_head(curve_a(), 1.0, q) - sum(
        line.head_loss(q, nu) for line in (dr.B_SUCTION, dr.B_DISCHARGE, dr.B_TO_RV, dr.B_FROM_RV)
    )


G40_TARGET = 0.020
"""m³/s: the relief flow G40 asks of network B (proposal §7.3)."""


def goal_seek_relief_set_flow() -> GoalSeekCase:
    """G40: RV1's setPressure → its flow 20 L/s on relief_pump_bypass (network B, API 526 L,
    ASME's overpressure). At the loop flow Q* the valve takes h* = H(Q*) − Σh(Q*), Δp_t* = ρg h*;
    its lift x* = Q*/(C√(2Δp_t*/ρ)) and the linear lift give Δp_s* = Δp_t*/(1 + 0.1 x*) (op 0.1:
    the set stays above the 3 psi crossover). Proposal §7.3: set* 366,924.6494 Pa, x 0.5987988.
    Bounds [v/2, 2v] about the case's set (the web's default, proposal §6 W6), above 15 psi."""
    rho, mu = _relief_fluid()
    nu = mu / rho
    q = G40_TARGET
    dp_t = rho * G * _b_relief_head(q, nu)
    c = el.API520_EFFECTIVE_KD * el.API526_AREAS[dr.B_LETTER]
    x = q / (c * math.sqrt(2.0 * dp_t / rho))
    dp_s = dp_t / (1.0 + el.ASME_OVERPRESSURE * x)
    if not (0.0 < x < 1.0 and dp_s * el.ASME_OVERPRESSURE > el.ASME_OVERPRESSURE_FLOOR):
        raise ValueError("G40 is in the band, on ASME's 10 %")
    base = dr.bench_set(dr.B_GAUGE_SET)
    bounds = (base / 2.0, 2.0 * base)

    def forward(xs: Sequence[float]) -> list[float]:
        return [dr.solve_b(dr.b_valve(set_pressure=xs[0]), rho, mu).q]

    name = "goal_seek_relief_set_flow"
    return GoalSeekCase(
        name=name,
        description="G40: the set pressure at which a pump's relief valve passes 20 L/s back "
        "to its suction tank (setPressure; relief_valve_flow).",
        source=_source(
            name,
            "h* = H(Q*) - sum h(Q*) around the loop (pump curve PCHIP, Darcy-Weisbach + "
            "Colebrook); dp_t* = rho g h*; x* = Q*/(Kd A sqrt(2 dp_t*/rho)); dp_s* = dp_t*/(1 + "
            "op x*), op = 0.1 (ASME)",
        ),
        project=_b_json(name, dr.b_valve()),
        variables=(component_variable("RV1", "setPressure", *bounds),),
        goals=(goal("relief_valve_flow", "RV1", q),),
        forward=forward,
        inverse=(dp_s,),
        checks=("pressure",),
        density=rho,
        data={"lift": x},
    )


G41_TARGET = 385_000.0
"""Pa(g): the relieving pressure G41 sizes for, the gauge set 350 kPa(g) plus ASME's 10 %
(proposal §7.3)."""
G41_START_LETTER: API526Letter = "L"


def g41_valve(area: float) -> Any:
    """RV1 of network B with an API 520 effective area (Kd 0.65, ASME's overpressure)."""
    return relief_valve("RV1", 0.0, dr.bench_set(dr.B_GAUGE_SET), effective_capacity(area))


def g41_inlet_pressure(sol: dr.BSolution, rho: float) -> float:
    """RV1's inlet static pressure, Pa(g): ρg(EGL_in − z) − ρv_in²/2 (D7)."""
    return dv.static_pressure(rho, sol.at.egl_in, 0.0, sol.at.v_in)


def g41_state() -> tuple[float, float, float]:
    """(Q*, Δp_t*, A*) of G41: the loop flow whose inlet static pressure is 385 kPa(g) on the
    pump side alone, p_in(Q) = ρg(H₁ − h_L1 + H(Q) − h_L2 − h_LB1) − ρv_in²/2, decreasing in Q
    (brentq); Δp_t* = ρg(EGL_in − EGL_out), EGL_out = H₁ + h_LB2(Q*); beyond full lift the area is
    A* = Q*/(Kd√(2Δp_t*/ρ)) (API 520's equation, the valve sized by it)."""
    rho, mu = _relief_fluid()
    nu = mu / rho
    curve = curve_a()

    def egl_in(q: float) -> float:
        return (
            dr.B_LEVEL1
            - dr.B_SUCTION.head_loss(q, nu)
            + el.pump_head(curve, 1.0, q)
            - dr.B_DISCHARGE.head_loss(q, nu)
            - dr.B_TO_RV.head_loss(q, nu)
        )

    def excess(q: float) -> float:
        return dv.static_pressure(rho, egl_in(q), 0.0, dr.B_TO_RV.velocity(q)) - G41_TARGET

    q = solve_decreasing(excess)
    dp_t = rho * G * (egl_in(q) - dr.B_LEVEL1 - dr.B_FROM_RV.head_loss(q, nu))
    area = q / (el.API520_EFFECTIVE_KD * math.sqrt(2.0 * dp_t / rho))
    full = dr.bench_set(dr.B_GAUGE_SET) * (1.0 + el.ASME_OVERPRESSURE)
    if not dp_t > full * (1.0 + 2.0 * dr.FLOW_CLEARANCE):
        raise ValueError("G41's valve is clearly beyond full lift")
    return q, dp_t, area


def goal_seek_relief_effective_area() -> GoalSeekCase:
    """G41 (sizing, decision 19): RV1 as an API 520 effective area (Kd 0.65, ASME's 10 %) in
    relief_pump_bypass's place, starting at API 526 L's area; capacity.area → RV1's inlet static
    pressure 385 kPa(g), set plus 10 % (``g41_state``). Beyond full lift A* is API 520's area at
    the solved flow and Δp_t: fluids' API520_A_l there gives A* × (1 + 6.0921×10⁻⁵), and the
    covering letter is L. Proposal §7.3: A* 1.2866259342×10⁻³ m², Q/Q_f 1.0128157. Bounds: API
    526 D's to T's effective areas (the web's default, proposal §6 W6)."""
    rho, mu = _relief_fluid()
    q, dp_t, area = g41_state()
    bounds = (el.API526_AREAS["D"], el.API526_AREAS["T"])

    def forward(xs: Sequence[float]) -> list[float]:
        return [g41_inlet_pressure(dr.solve_b(g41_valve(xs[0]), rho, mu), rho)]

    name = "goal_seek_relief_effective_area"
    return GoalSeekCase(
        name=name,
        description="G41: the API 520 effective area that holds a pump's relief valve inlet at "
        "its relieving pressure, set plus 10 % (sizing; capacity.area; port_pressure).",
        source=_source(
            name,
            "Q* by brentq on the pump side's inlet static pressure p_in(Q) = 385 kPa(g) "
            "(pump curve PCHIP, Darcy-Weisbach + Colebrook, D7); dp_t* = rho g (EGL_in - "
            "EGL_out); A* = Q*/(0.65 sqrt(2 dp_t*/rho)) beyond full lift",
        ),
        project=_b_json(name, g41_valve(el.API526_AREAS[G41_START_LETTER])),
        variables=(component_variable("RV1", "capacity.area", *bounds),),
        goals=(goal("port_pressure", "RV1", G41_TARGET, "inlet"),),
        forward=forward,
        inverse=(area,),
        checks=("forward",),
        density=rho,
        data={
            "flow": q,
            "totalPressureDifference": dp_t,
            "coveringLetter": el.covering_letter(area),
        },
    )


def _m_state_at_relief_flow(p_r: float, q: float, rho: float, mu: float) -> tuple[float, float]:
    """Network M at R1's surface pressure p_r with a relief flow q: T1's EGL H from continuity,
    h_L1⁻¹(H₁ − H) = h_L2⁻¹(H − H₂) + q (brentq), and the valve's Δp_t = ρg(H − h_LB1(q) −
    h_LB2(q) − H₃) (its ports level)."""
    nu = mu / rho
    h1 = dr.M_LEVEL1 + p_r / (rho * G)

    def continuity(h: float) -> float:
        main_in = dv.solve_flow(lambda x: dr.M_MAIN_IN.head_loss(x, nu), h1 - h)
        main_out = dv.solve_flow(lambda x: dr.M_MAIN_OUT.head_loss(x, nu), h - dr.M_LEVEL2)
        return main_in - main_out - q

    h = bisect(continuity, dr.M_LEVEL2 + 1.0e-9, h1 - 1.0e-9)
    head = h - dr.M_TO_RV.head_loss(q, nu) - dr.M_FROM_RV.head_loss(q, nu) - dr.M_LEVEL3
    return h, rho * G * head


G42_TARGET = 0.0025
"""m³/s: the relief flow G42 asks of C15's network."""


def goal_seek_relief_overpressure_flow() -> GoalSeekCase:
    """G42: the certified valve of relief_certified (area 2.5×10⁻⁴ m², K 0.70, op 0.08), its
    capacity.overpressure → relief flow 2.5 L/s at p_R 1.05 MPa. With the relief flow known T1's
    EGL follows from continuity (``_m_state_at_relief_flow``), then x* = Q*/(K A √(2Δp_t*/ρ)) and
    op* = (Δp_t* − Δp_s)/(x* Δp_s). Proposal §7.3 (R6): op* 0.1099375341, x 0.44075. Bounds
    [v/2, min(2v, 1)] about the case's 0.08 (the web's default)."""
    rho, mu = _relief_fluid()
    q = G42_TARGET
    _, dp_t = _m_state_at_relief_flow(1.05e6, q, rho, mu)
    c = dr.C15_KD * dr.C15_AREA
    x = q / (c * math.sqrt(2.0 * dp_t / rho))
    op = (dp_t - dr.M_SET) / (x * dr.M_SET)
    if not 0.0 < x < 1.0:
        raise ValueError("G42 is in the band")
    bounds = (dr.C15_OP / 2.0, min(2.0 * dr.C15_OP, 1.0))

    def forward(xs: Sequence[float]) -> list[float]:
        capacity = certified_capacity(dr.C15_AREA, dr.C15_KD, xs[0])
        net = dr.NetworkM(1.05e6, dr.m_valve(capacity=capacity))
        return [net.solve(rho, mu).q_relief]

    name = "goal_seek_relief_overpressure_flow"
    return GoalSeekCase(
        name=name,
        description="G42: the full-lift overpressure a certified relief valve must have to "
        "pass 2.5 L/s (the overpressure a calibration must show; capacity.overpressure).",
        source=_source(
            name,
            "T1's EGL by brentq on continuity at the relief flow (Darcy-Weisbach + Colebrook); "
            "dp_t* = rho g h*; x* = Q*/(K A sqrt(2 dp_t*/rho)); op* = (dp_t* - dp_s)/(x* dp_s)",
        ),
        project=_json(dr.relief_certified().project),
        variables=(component_variable("RV1", "capacity.overpressure", *bounds),),
        goals=(goal("relief_valve_flow", "RV1", q),),
        forward=forward,
        inverse=(op,),
        checks=("forward",),
        density=rho,
        data={"lift": x},
    )


G43_TARGET = 0.0045
"""m³/s: the relief flow G43 asks of C3's network."""
G43_START = 0.65
"""G43's certified coefficient (a test input; the area is API 526 F's)."""


def g43_valve(kd: float) -> Any:
    return dr.m_valve(capacity=certified_capacity(el.API526_AREAS["F"], kd))


def goal_seek_relief_coefficient_flow() -> GoalSeekCase:
    """G43: C3's network (p_R 1.4 MPa) with RV1 certified (API 526 F's area as the actual area,
    K 0.65, ASME's overpressure), its capacity.dischargeCoefficient → relief flow 4.5 L/s. T1's
    EGL from continuity at the relief flow, then beyond full lift K* = Q*/(A√(2Δp_t*/ρ)).
    Proposal §7.3: K* 0.6169863575. Bounds [v/2, min(2v, 1)] (the web's default)."""
    rho, mu = _relief_fluid()
    q = G43_TARGET
    _, dp_t = _m_state_at_relief_flow(1.4e6, q, rho, mu)
    area = el.API526_AREAS["F"]
    kd = q / (area * math.sqrt(2.0 * dp_t / rho))
    full = dr.M_SET * (1.0 + el.asme_overpressure(dr.M_SET))
    if not dp_t > full * (1.0 + 2.0 * dr.FLOW_CLEARANCE):
        raise ValueError("G43's valve is clearly beyond full lift")
    bounds = (G43_START / 2.0, min(2.0 * G43_START, 1.0))

    def forward(xs: Sequence[float]) -> list[float]:
        return [dr.NetworkM(1.4e6, g43_valve(xs[0])).solve(rho, mu).q_relief]

    name = "goal_seek_relief_coefficient_flow"
    return GoalSeekCase(
        name=name,
        description="G43: the rated coefficient of discharge at which a certified relief "
        "valve passes 4.5 L/s at full lift (capacity.dischargeCoefficient).",
        source=_source(
            name,
            "T1's EGL by brentq on continuity at the relief flow (Darcy-Weisbach + Colebrook); "
            "dp_t* = rho g h*; K* = Q*/(A sqrt(2 dp_t*/rho)) beyond full lift",
        ),
        project=_json(
            dr.NetworkM(1.4e6, g43_valve(G43_START)).project(
                "ref-goal-seek-relief-coefficient-flow",
                "goal seek relief coefficient flow",
                dr.liquid_a(),
                "colebrook",
            )
        ),
        variables=(component_variable("RV1", "capacity.dischargeCoefficient", *bounds),),
        goals=(goal("relief_valve_flow", "RV1", q),),
        forward=forward,
        inverse=(kd,),
        checks=("forward",),
        density=rho,
    )


G44_TARGET = 520_000.0
"""Pa: the static pressure drop across RV1 G44 asks of C4's network."""
G44_BOUNDS = (9.0e5, 1.3e6)
"""Pa(g): R1's surface pressure bounds about C4's 1.05 MPa (test inputs)."""


def _c4_drop(q: float, rho: float, nu: float) -> float:
    """C4's valve at flow q (outlet port 0.5 m up): the static drop Δp_t(q) − ρ(v_in² −
    v_out²)/2, Δp_t = ρg(h(q) − (z_in − z_out))."""
    law = el.relief_law(dr.m_valve(outlet_elevation=dr.C4_OUTLET_ELEVATION), rho)
    dp_t = rho * G * (law.head(q) - law.dz)
    return dp_t - rho * (dr.M_TO_RV.velocity(q) ** 2 - dr.M_FROM_RV.velocity(q) ** 2) / 2.0


def goal_seek_relief_supply_pressure_drop() -> GoalSeekCase:
    """G44: R1's surfacePressure → RV1's static pressure drop 520 kPa on relief_port_elevations
    (outlet port 0.5 m above the inlet). The drop rises with the relief flow, so Q* by brentq on
    ``_c4_drop``; then T1's EGL H = H₃ + h_LB2 + h(Q*) + h_LB1, the main's flows from H and
    continuity, H₁ = H + h_L1(Q_in) and p_R* = ρg(H₁ − 2 m). The law reads Δp_t, which differs
    from the static drop by the velocity heads and 0.5 m of elevation: a goal read on the wrong
    one misses (proposal §7.3: p_R* 1,018,261.857 Pa, Δp_t 520,239.30 Pa)."""
    rho, mu = _relief_fluid()
    nu = mu / rho
    element = dr.m_valve(outlet_elevation=dr.C4_OUTLET_ELEVATION)
    law = el.relief_law(element, rho)
    full = law.q_full
    q = bisect(lambda x: _c4_drop(x, rho, nu) - G44_TARGET, 1.0e-12, full)
    h_t1 = dr.M_LEVEL3 + dr.M_FROM_RV.head_loss(q, nu) + law.head(q) + dr.M_TO_RV.head_loss(q, nu)
    main_out = dv.solve_flow(lambda x: dr.M_MAIN_OUT.head_loss(x, nu), h_t1 - dr.M_LEVEL2)
    h1 = h_t1 + dr.M_MAIN_IN.head_loss(main_out + q, nu)
    p_r = rho * G * (h1 - dr.M_LEVEL1)
    if not G44_BOUNDS[0] < p_r < G44_BOUNDS[1]:
        raise ValueError("G44's surface pressure is outside its bounds")

    def forward(xs: Sequence[float]) -> list[float]:
        net = dr.NetworkM(xs[0], element)
        sol = net.solve(rho, mu)
        at = net.ports(sol, nu)
        p = dr.port_pressures(element, at, rho)
        return [p["RV1:inlet"] - p["RV1:outlet"]]

    name = "goal_seek_relief_supply_pressure_drop"
    return GoalSeekCase(
        name=name,
        description="G44: the supply tank's surface pressure that puts 520 kPa of static "
        "pressure drop across a relief valve whose outlet port sits 0.5 m above its inlet "
        "(surfacePressure; relief_valve_pressure_drop).",
        source=_source(
            name,
            "Q* by brentq on the static drop dp_t(Q) - rho (v_in^2 - v_out^2)/2, dp_t = rho g "
            "(h(Q) - (z_in - z_out)); T1's EGL, the main's flows (Darcy-Weisbach + Colebrook) "
            "and p_R* = rho g (H1 - level)",
        ),
        project=_json(dr.relief_port_elevations().project),
        variables=(component_variable("R1", "surfacePressure", *G44_BOUNDS),),
        goals=(goal("relief_valve_pressure_drop", "RV1", G44_TARGET),),
        forward=forward,
        inverse=(p_r,),
        checks=("pressure",),
        density=rho,
        data={"flow": q, "totalPressureDifference": rho * G * (law.head(q) - law.dz)},
    )


MET_CASES: tuple[Callable[[], GoalSeekCase], ...] = (
    goal_seek_level_turbulent,
    goal_seek_level_laminar,
    goal_seek_level_fittings_water,
    goal_seek_pump_speed_flow,
    goal_seek_pump_speed_pressure,
    goal_seek_prv_setpoint_flow,
    goal_seek_assigned_flow_pressure,
    goal_seek_two_levels_two_flows,
    goal_seek_length,
    goal_seek_valve_cv_flow,
    goal_seek_valve_cv_from_default,
    goal_seek_reference_pressure_outflow,
    goal_seek_temperature_npsh_margin,
    goal_seek_fcv_setpoint_pressure,
    goal_seek_parallel_pump_speeds,
    goal_seek_check_valve_opening,
    goal_seek_scenario,
    goal_seek_surface_pressure_velocity,
    goal_seek_pump_setpoint_head,
    goal_seek_level_npsh_available,
    goal_seek_valve_k_pressure_drop,
    goal_seek_pump_speed_head_loss,
    goal_seek_equipment_rated_pressure_loss,
    goal_seek_equipment_rated_flow,
    goal_seek_equipment_rated_density,
    goal_seek_equipment_pressure_drop_level,
    goal_seek_equipment_pressure_loss_level,
    goal_seek_equipment_cv,
    goal_seek_equipment_kv,
    goal_seek_orifice_bore_flow,
    goal_seek_orifice_entered_c_flow,
    goal_seek_orifice_meter_bore,
    goal_seek_orifice_bypass_bore,
    goal_seek_orifice_c_at_corner_taps,
    goal_seek_orifice_pressure_loss_level,
    goal_seek_orifice_pressure_drop_level,
    goal_seek_relief_set_flow,
    goal_seek_relief_effective_area,
    goal_seek_relief_overpressure_flow,
    goal_seek_relief_coefficient_flow,
    goal_seek_relief_supply_pressure_drop,
)
"""Cases whose targets the closed form reaches inside the bounds (G1-G14, G17, G19, and
G20-G24, which give the variables and quantities §7.2 leaves without a case one each: D6, "a new
variable field or goal quantity ships with a reference case"; G25-G31, the equipment variables
and goals, equipment-pressure-drop.md §7.3; G33-G39, the orifice variables and goals,
orifice-plate.md §7.3; G40-G44, the relief valve's variables and goals and sizing,
pressure-relief-valve.md §7.3)."""
LABELS = {
    "goal_seek_level_turbulent": "G1",
    "goal_seek_level_laminar": "G2",
    "goal_seek_level_fittings_water": "G3",
    "goal_seek_pump_speed_flow": "G4",
    "goal_seek_pump_speed_pressure": "G5",
    "goal_seek_prv_setpoint_flow": "G6",
    "goal_seek_assigned_flow_pressure": "G7",
    "goal_seek_two_levels_two_flows": "G8",
    "goal_seek_length": "G9",
    "goal_seek_valve_cv_flow": "G10",
    "goal_seek_valve_cv_from_default": "G10b",
    "goal_seek_reference_pressure_outflow": "G11",
    "goal_seek_temperature_npsh_margin": "G12",
    "goal_seek_fcv_setpoint_pressure": "G13",
    "goal_seek_parallel_pump_speeds": "G14",
    "goal_seek_level_unreachable": "G15",
    "goal_seek_controlled_pump_crossing": "G16",
    "goal_seek_check_valve_opening": "G17",
    "goal_seek_met_at_start": "G18",
    "goal_seek_scenario": "G19",
    "goal_seek_surface_pressure_velocity": "G20",
    "goal_seek_pump_setpoint_head": "G21",
    "goal_seek_level_npsh_available": "G22",
    "goal_seek_valve_k_pressure_drop": "G23",
    "goal_seek_pump_speed_head_loss": "G24",
    "goal_seek_equipment_rated_pressure_loss": "G25",
    "goal_seek_equipment_rated_flow": "G26",
    "goal_seek_equipment_rated_density": "G27",
    "goal_seek_equipment_pressure_drop_level": "G28",
    "goal_seek_equipment_pressure_loss_level": "G29",
    "goal_seek_equipment_cv": "G30",
    "goal_seek_equipment_kv": "G31",
    "goal_seek_equipment_scenario_parts": "G32",
    "goal_seek_orifice_bore_flow": "G33",
    "goal_seek_orifice_entered_c_flow": "G34",
    "goal_seek_orifice_meter_bore": "G35",
    "goal_seek_orifice_bypass_bore": "G36",
    "goal_seek_orifice_c_at_corner_taps": "G37",
    "goal_seek_orifice_pressure_loss_level": "G38",
    "goal_seek_orifice_pressure_drop_level": "G39",
    "goal_seek_relief_set_flow": "G40",
    "goal_seek_relief_effective_area": "G41",
    "goal_seek_relief_overpressure_flow": "G42",
    "goal_seek_relief_coefficient_flow": "G43",
    "goal_seek_relief_supply_pressure_drop": "G44",
}
"""Design §7.2's numbers (G10b, G20-G24 are this module's additions)."""
