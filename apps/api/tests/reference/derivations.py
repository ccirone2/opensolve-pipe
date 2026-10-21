"""Closed-form expected results for the reference suite (design §9, CLAUDE.md D6).

Each case function builds one reference case: the project, from the parameters written at the
top of the function, and the expected results, derived from first principles. The derivation is
the documentation of the expected values, so each one writes out its energy equation.

Independence (build-v1.md §5): nothing here imports ``opensolve_pipe.services`` or reads
``opensolve_pipe/data``; only the Pydantic models are used, to build valid project JSON.

Ingredients, all cited at the point of use:

- Energy equation in energy-grade-line (EGL) form on every connection (design §1.1, §2.1)::

      H_from − H_to = Σ_k f_k (L_k/D_k) v_k|v_k|/(2g) + Σ_j n_j K_j v_j|v_j|/(2g)

  with H = z + p/(ρg) + v²/(2g); a reservoir holds H = z + level + p_surface/(ρg), an ideal
  reference node H = z_port + p/(ρg), and an ideal tee has one EGL at all three ports.
- g = ``fluids.constants.g`` (standard gravity, the solver's g, design §1.3).
- Darcy friction factor f(Re, ε/D):
  laminar Re < 2000: f = 64/Re (Hagen–Poiseuille); turbulent Re ≥ 4000:
  ``fluids.friction.Colebrook`` with ``tol=None``, the closed-form Lambert-W solution of the
  Colebrook (1939) equation — deliberately a different code path from the solver's
  ``fluids.friction.Clamond``; transition 2000 ≤ Re < 4000: a cubic Hermite interpolation in
  R = Re/2000 between the laminar value and slope at Re = 2000 and the turbulent value and slope at
  Re = 4000 (design §2.1, EPANET 2.2's Dunlop method), implemented here from that definition, with
  the analytic Colebrook slope.
- Fitting K from the ``fluids.fittings`` functions named in design §3 (Crane TP-410 via fluids).
- Fluid properties: custom fluids are user inputs; built-in water from CoolProp ``PropsSI``.
- Library pipes: ``fluids.piping.nearest_pipe`` and ``fluids.friction.roughness_Farshad``.
- Roots: ``scipy.optimize.brentq`` (one unknown) and ``scipy.optimize.fsolve`` (two unknowns).
- Static pressure at a port: p = ρ g (H − z − v²/2g), v in the connected pipe's end segment;
  boundary ports (reservoir, reference node) report v = 0 (design §1.1).
"""

import math
from collections.abc import Callable
from typing import Literal

import fluids.constants
import fluids.fittings
import fluids.friction
import fluids.piping
import numpy as np
from CoolProp.CoolProp import PropsSI
from numpy.typing import NDArray
from scipy.optimize import brentq, fsolve

from tests.reference.case_format import (
    Expected,
    FrictionMethod,
    ReferenceCase,
    builtin_water,
    connect,
    custom_fluid,
    custom_pipe,
    fitting,
    ideal_tee,
    library_pipe,
    make_project,
    plug,
    reference_node,
    reservoir,
)

G: float = float(fluids.constants.g)
"""Standard gravity, m/s² (fluids.constants.g), the g the solver uses (design §1.3)."""

RE_LAMINAR = 2000.0
"""Laminar below this Reynolds number; the transition interpolation starts here (design §2.1)."""
RE_TURBULENT = 4000.0
"""The turbulent formula applies at and above this Reynolds number (design §2.1)."""

# Colebrook (1939) exactly as the fluids.friction.Colebrook docstring writes it:
#     1/√f = −2 log10( (ε/D)/3.7 + 2.51/(Re √f) )
# test_derivation_checks verifies that fluids' Colebrook output satisfies it with these constants.
COLEBROOK_A = 3.7
COLEBROOK_B = 2.51

# Swamee & Jain (1976) as fluids.friction.Swamee_Jain_1976 implements it (research notes §4.5):
#     f = 0.25 / log10( (6.97/Re)^0.9 + (ε/D)/3.7 )²
SWAMEE_JAIN_C = 6.97
SWAMEE_JAIN_N = 0.9
SWAMEE_JAIN_A = 3.7

WATER_REFERENCE_PRESSURE = 101325.0
"""Pa absolute. Built-in water is evaluated at 101325 Pa (design §7, §10)."""

INCH = 0.0254
"""m per inch (exact by definition); nominal sizes are stored as NPS·0.0254 (design §10)."""

FLUID_A = ("Test liquid A (custom input)", 998.0, 1.0e-3)
"""A water-like custom fluid: name, density kg/m³, dynamic viscosity Pa·s (test inputs)."""

Regime = Literal["laminar", "transitional", "turbulent"]


# --- Friction factor ---------------------------------------------------------------------------


def colebrook(re: float, ed: float) -> float:
    """Colebrook f from fluids' closed-form Lambert-W solution (``tol=None``).

    Colebrook, C. F. (1939), J. ICE 11(4), 133-156; solution method as in fluids 1.3.1.
    """
    return float(fluids.friction.Colebrook(re, ed))


def colebrook_dfdre(re: float, ed: float) -> float:
    """df/dRe of the Colebrook equation by implicit differentiation.

    With x = 1/√f, F(x, Re) = x + 2 log10(ε/D/3.7 + 2.51 x/Re) = 0, so
    dx/dRe = −(∂F/∂Re)/(∂F/∂x) and, from f = x⁻², df/dRe = −2 x⁻³ dx/dRe.
    """
    x = 1.0 / math.sqrt(colebrook(re, ed))
    s = ed / COLEBROOK_A + COLEBROOK_B * x / re
    dfdx = 1.0 + 2.0 / math.log(10.0) * (COLEBROOK_B / re) / s
    dfdre_partial = 2.0 / math.log(10.0) * (-COLEBROOK_B * x / re**2) / s
    dxdre = -dfdre_partial / dfdx
    return float(-2.0 * x**-3 * dxdre)


def swamee_jain(re: float, ed: float) -> float:
    """Swamee & Jain (1976) f via ``fluids.friction.Swamee_Jain_1976`` (EPANET comparisons)."""
    return float(fluids.friction.Swamee_Jain_1976(re, ed))


def swamee_jain_dfdre(re: float, ed: float) -> float:
    """Analytic df/dRe of the Swamee–Jain form above: with y = (6.97/Re)^0.9 + ε/D/3.7 and
    f = 0.25/log10(y)², df/dRe = −0.5 log10(y)⁻³ (dy/dRe)/(y ln 10), dy/dRe = −0.9 (6.97/Re)^0.9/Re.
    """
    t = (SWAMEE_JAIN_C / re) ** SWAMEE_JAIN_N
    y = t + ed / SWAMEE_JAIN_A
    dydre = -SWAMEE_JAIN_N * t / re
    return float(-0.5 * math.log10(y) ** -3 * dydre / (y * math.log(10.0)))


def transition_friction_factor(re: float, f_turbulent: float, dfdre_turbulent: float) -> float:
    """Cubic Hermite interpolation of f in R = Re/2000 on 1 ≤ R ≤ 2 (design §2.1).

    End conditions: at R = 1 the laminar law f = 64/Re = 64/(2000 R), value 64/2000 and slope
    df/dR = −64/2000; at R = 2 the turbulent formula's value and slope at Re = 4000, with
    df/dR = 2000 df/dRe. With t = R − 1 on the unit interval, the Hermite basis is
    h00 = (1 + 2t)(1 − t)², h10 = t(1 − t)², h01 = t²(3 − 2t), h11 = t²(t − 1).
    """
    r = re / RE_LAMINAR
    t = r - 1.0
    f_start = 64.0 / RE_LAMINAR
    slope_start = -64.0 / RE_LAMINAR
    f_end = f_turbulent
    slope_end = dfdre_turbulent * RE_LAMINAR
    h00 = (1.0 + 2.0 * t) * (1.0 - t) ** 2
    h10 = t * (1.0 - t) ** 2
    h01 = t * t * (3.0 - 2.0 * t)
    h11 = t * t * (t - 1.0)
    return h00 * f_start + h10 * slope_start + h01 * f_end + h11 * slope_end


def friction_factor(re: float, ed: float, method: FrictionMethod = "colebrook") -> float:
    """Darcy friction factor in every regime (design §2.1)."""
    if re <= 0.0:
        raise ValueError("friction factor needs Re > 0")
    if re < RE_LAMINAR:
        return 64.0 / re
    turbulent, slope = (
        (colebrook, colebrook_dfdre) if method == "colebrook" else (swamee_jain, swamee_jain_dfdre)
    )
    if re >= RE_TURBULENT:
        return turbulent(re, ed)
    return transition_friction_factor(re, turbulent(RE_TURBULENT, ed), slope(RE_TURBULENT, ed))


def regime(re: float) -> Regime:
    if re < RE_LAMINAR:
        return "laminar"
    return "transitional" if re < RE_TURBULENT else "turbulent"


# --- Element head losses (signed like the flow) ------------------------------------------------


def area(d: float) -> float:
    return math.pi * d * d / 4.0


def velocity(q: float, d: float) -> float:
    return q / area(d)


def reynolds(q: float, d: float, nu: float) -> float:
    return abs(velocity(q, d)) * d / nu


def friction_head_loss(
    q: float,
    d: float,
    length: float,
    roughness: float,
    nu: float,
    method: FrictionMethod = "colebrook",
    g: float = G,
) -> float:
    """Darcy–Weisbach h_f = f (L/D) v|v|/(2g). In laminar flow this equals 128 ν L Q/(g π D⁴)."""
    if q == 0.0:
        return 0.0
    v = velocity(q, d)
    f = friction_factor(reynolds(q, d, nu), roughness / d, method)
    return f * length / d * v * abs(v) / (2.0 * g)


def minor_head_loss(q: float, k: float, d: float, g: float = G) -> float:
    """Fitting loss K v|v|/(2g) with v in the reference diameter d."""
    v = velocity(q, d)
    return k * v * abs(v) / (2.0 * g)


def static_pressure(rho: float, egl: float, z: float, v: float, g: float = G) -> float:
    """Static gauge pressure p = ρ g (H − z − v²/2g) (design §1.1)."""
    return rho * g * (egl - z - v * v / (2.0 * g))


def solve_flow(head_loss: Callable[[float], float], dh: float) -> float:
    """The flow Q > 0 with head_loss(Q) = dh (head_loss increasing, zero at Q = 0), by brentq."""
    if dh <= 0.0:
        raise ValueError("solve_flow needs a positive head difference")
    q_hi = 1.0e-3
    while head_loss(q_hi) < dh:
        q_hi *= 2.0
    root: float = brentq(
        lambda q: head_loss(q) - dh, 0.0, q_hi, xtol=1.0e-18, rtol=1.0e-15, maxiter=500
    )
    return root


def require_regime(q: float, d: float, nu: float, expected: Regime) -> None:
    """Guard: a derivation's regime assumption must hold at the solution."""
    re = reynolds(q, d, nu)
    if regime(re) != expected:
        raise ValueError(f"expected {expected} flow, got Re = {re:.1f}")


# --- Fitting K (design §3; Crane TP-410 (2009) via fluids 1.3.1 unless stated) -----------------


def k_entrance_sharp() -> float:
    """``fluids.fittings.entrance_sharp(method='Crane')``."""
    return float(fluids.fittings.entrance_sharp(method="Crane"))


def k_exit() -> float:
    """``fluids.fittings.exit_normal()`` (Rennels & Hudson 2012)."""
    return float(fluids.fittings.exit_normal())


def k_elbow_90_lr(d: float) -> float:
    """Long-radius 90° elbow: ``bend_rounded_Crane(Di, 90, bend_diameters=1.5)``."""
    return float(fluids.fittings.bend_rounded_Crane(Di=d, angle=90.0, bend_diameters=1.5))


def k_gate_valve(d: float) -> float:
    """Full-bore gate valve: ``K_gate_valve_Crane(Di, Di, 0)``."""
    return float(fluids.fittings.K_gate_valve_Crane(D1=d, D2=d, angle=0.0))


def k_sudden_contraction(d_large: float, d_small: float) -> float:
    """Flow large → small: ``contraction_sharp(D_large, D_small, method='Crane')``; K is on the
    following (small) pipe's velocity (fluids docstring)."""
    return float(fluids.fittings.contraction_sharp(Di1=d_large, Di2=d_small, method="Crane"))


def k_sudden_expansion(d_small: float, d_large: float) -> float:
    """Flow small → large: ``diffuser_sharp(D_small, D_large)`` (Rennels); K is on the original
    (small) pipe's velocity (fluids docstring)."""
    return float(fluids.fittings.diffuser_sharp(Di1=d_small, Di2=d_large))


def k_conical_contraction(d_large: float, d_small: float, angle: float) -> float:
    """Flow large → small through a conical reducer of included angle θ:
    ``contraction_conical_Crane(D_large, D_small, angle=θ)``; K on the following (smaller) pipe
    (fluids docstring)."""
    return float(fluids.fittings.contraction_conical_Crane(Di1=d_large, Di2=d_small, angle=angle))


def k_conical_expansion(d_small: float, d_large: float, angle: float) -> float:
    """Flow small → large through a conical reducer: ``diffuser_conical(D_small, D_large,
    angle=θ, method='Crane')``; K on the smaller, upstream pipe (fluids docstring)."""
    return float(
        fluids.fittings.diffuser_conical(Di1=d_small, Di2=d_large, angle=angle, method="Crane")
    )


def k_entrance_rounded(d: float, radius_ratio: float) -> float:
    """Rounded entrance, rounding radius r = ratio · D: ``entrance_rounded(Di, rc, 'Crane')``."""
    return float(fluids.fittings.entrance_rounded(Di=d, rc=radius_ratio * d, method="Crane"))


def k_entrance_projecting(d: float) -> float:
    """Projecting (re-entrant) entrance: ``entrance_distance(Di, method='Crane')``."""
    return float(fluids.fittings.entrance_distance(Di=d, method="Crane"))


def k_bend(d: float, angle: float, radius_ratio: float) -> float:
    """Welded or flanged bend of r/D = ratio: ``bend_rounded_Crane(Di, angle, bend_diameters)``
    (elbow_90_sr: 90°, r/D 1; elbow_45_lr: 45°, 1.5; elbow_45_sr: 45°, 1; bend: as given)."""
    return float(fluids.fittings.bend_rounded_Crane(Di=d, angle=angle, bend_diameters=radius_ratio))


def k_threaded_elbow(d: float, angle: float) -> float:
    """Standard threaded elbow: ``bend_rounded(Di, angle, method='Crane standard')``."""
    return float(fluids.fittings.bend_rounded(Di=d, angle=angle, method="Crane standard"))


def k_crane_valves(d: float) -> dict[str, float]:
    """Full-bore, fully open Crane valves on a pipe of inner diameter d (design §3):
    ``K_ball_valve_Crane(D, D, 0)``, ``K_globe_valve_Crane(D, D)``,
    ``K_butterfly_valve_Crane(D, style=0)`` (centric), ``K_plug_valve_Crane(D, D, 0, style=0)``
    (straight-through), ``K_swing_check_valve_Crane(D, angled=True)`` and
    ``K_lift_check_valve_Crane(D, D, angled=True)`` (angled patterns)."""
    ff = fluids.fittings
    return {
        "ball_valve": float(ff.K_ball_valve_Crane(D1=d, D2=d, angle=0.0)),
        "globe_valve": float(ff.K_globe_valve_Crane(D1=d, D2=d)),
        "butterfly_valve": float(ff.K_butterfly_valve_Crane(D=d, style=0)),
        "plug_valve": float(ff.K_plug_valve_Crane(D1=d, D2=d, angle=0.0, style=0)),
        "swing_check_valve": float(ff.K_swing_check_valve_Crane(D=d, angled=True)),
        "lift_check_valve": float(ff.K_lift_check_valve_Crane(D1=d, D2=d, angled=True)),
    }


# --- Property sources -------------------------------------------------------------------------


def water_properties(temperature: float) -> tuple[float, float]:
    """Density and dynamic viscosity of liquid water from CoolProp 'Water' (HEOS: IAPWS-95 EOS,
    Wagner & Pruß 2002; viscosity Huber et al. 2009) at 101325 Pa (design §7, §10)."""
    t_sat = PropsSI("T", "P", WATER_REFERENCE_PRESSURE, "Q", 0, "Water")
    if not temperature < t_sat:
        raise ValueError("this derivation assumes liquid water below Tsat(101325 Pa)")
    rho = float(PropsSI("D", "T", temperature, "P", WATER_REFERENCE_PRESSURE, "Water"))
    mu = float(PropsSI("V", "T", temperature, "P", WATER_REFERENCE_PRESSURE, "Water"))
    return rho, mu


def carbon_steel_schedule_40(nps: float) -> tuple[float, float]:
    """Inner diameter (``fluids.piping.nearest_pipe``, ASME B36.10M-2004) and roughness
    (``fluids.friction.roughness_Farshad('Carbon steel, bare', D)``, Farshad & Rieke 2006, at the
    inner diameter) of a carbon-steel schedule 40 pipe, as design §10 specifies the library."""
    # fluids annotates NPS as int, but its NPS tables hold floats (e.g. 2.5).
    _, inner_diameter, _, _ = fluids.piping.nearest_pipe(NPS=nps, schedule="40")  # type: ignore[arg-type]
    roughness = fluids.friction.roughness_Farshad(ID="Carbon steel, bare", D=inner_diameter)
    return float(inner_diameter), float(roughness)


def _source(name: str, method: str) -> str:
    return f"closed-form: tests/reference/derivations.py::{name} ({method})"


# --- Cases -------------------------------------------------------------------------------------


def single_pipe_turbulent() -> ReferenceCase:
    """Open reservoir → one pipe → open reservoir, turbulent, friction only.

    Energy equation (no fittings):  H1 − H2 = f(Re, ε/D) (L/D) v²/(2g),  v = Q/A,  Re = vD/ν,
    with H = z + level for each reservoir. One unknown Q (brentq); Colebrook f.
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d, length, eps = 0.1, 250.0, 4.5e-5
    z1, level1, z2, level2 = 10.0, 2.0, 0.0, 1.5
    h1, h2 = z1 + level1, z2 + level2

    q = solve_flow(lambda q: friction_head_loss(q, d, length, eps, nu), h1 - h2)
    require_regime(q, d, nu, "turbulent")

    project = make_project(
        "ref-single-pipe-turbulent",
        "Single pipe between reservoirs (turbulent)",
        custom_fluid(name, rho, mu),
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [connect("L1", "R1:port_1", "R2:port_1", [custom_pipe(d, length, eps)])],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
        # Boundary ports are quiescent (v = 0): p = ρ g (H − z_port) = ρ g · level.
        pressures={
            "R1:port_1": static_pressure(rho, h1, z1, 0.0),
            "R2:port_1": static_pressure(rho, h2, z2, 0.0),
        },
    )
    return ReferenceCase(
        name="single_pipe_turbulent",
        description=(
            "Reservoir to reservoir through one custom pipe in turbulent flow, friction only: "
            "verifies the Darcy-Weisbach/Colebrook pipe law, reservoir heads and boundary "
            "port pressures."
        ),
        source=_source(
            "single_pipe_turbulent",
            "Darcy-Weisbach, Colebrook via fluids.friction.Colebrook Lambert-W, brentq",
        ),
        project=project,
        expected=expected,
    )


def single_pipe_laminar() -> ReferenceCase:
    """Open reservoir → one pipe → open reservoir, laminar (Hagen–Poiseuille), no iteration.

    With f = 64/Re the Darcy–Weisbach loss is linear in Q:
        H1 − H2 = (64 ν/(v D)) (L/D) v²/(2g) = 32 ν L v/(g D²) = 128 ν L Q/(g π D⁴)
    so  Q = (H1 − H2) g π D⁴ / (128 ν L)  in closed form.
    """
    name, rho, mu = "Viscous oil (custom input)", 870.0, 1.74e-2
    nu = mu / rho
    d, length, eps = 0.05, 80.0, 4.5e-5
    z1, level1, z2, level2 = 1.2, 0.8, 0.0, 1.15
    h1, h2 = z1 + level1, z2 + level2

    q = (h1 - h2) * G * math.pi * d**4 / (128.0 * nu * length)
    require_regime(q, d, nu, "laminar")

    project = make_project(
        "ref-single-pipe-laminar",
        "Single pipe between reservoirs (laminar)",
        custom_fluid(name, rho, mu),
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [connect("L1", "R1:port_1", "R2:port_1", [custom_pipe(d, length, eps)])],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
    )
    return ReferenceCase(
        name="single_pipe_laminar",
        description=(
            "Reservoir to reservoir through one pipe in laminar flow (Re about 1000): verifies "
            "the Hagen-Poiseuille law f = 64/Re against its closed-form flow."
        ),
        source=_source("single_pipe_laminar", "Hagen-Poiseuille closed form, no iteration"),
        project=project,
        expected=expected,
    )


def single_pipe_fittings() -> ReferenceCase:
    """Reservoir → pipe with fittings → reservoir.

    Fittings on the one segment (reference velocity v = Q/A of that pipe):
    sharp entrance, 3 long-radius 90° elbows, a full-bore gate valve and an exit. Energy equation:
        H1 − H2 = [f (L/D) + K_entrance + 3 K_elbow + K_gate + K_exit] v²/(2g)
    with each K from fluids (Crane TP-410 functions named in design §3).
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d, length, eps = 0.0779, 60.0, 4.6e-5
    z1, level1, z2, level2 = 5.0, 3.0, 0.0, 2.0
    h1, h2 = z1 + level1, z2 + level2
    k_total = k_entrance_sharp() + 3 * k_elbow_90_lr(d) + k_gate_valve(d) + k_exit()

    q = solve_flow(
        lambda q: friction_head_loss(q, d, length, eps, nu) + minor_head_loss(q, k_total, d),
        h1 - h2,
    )
    require_regime(q, d, nu, "turbulent")

    project = make_project(
        "ref-single-pipe-fittings",
        "Single pipe with fittings",
        custom_fluid(name, rho, mu),
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [
            connect(
                "L1",
                "R1:port_1",
                "R2:port_1",
                [custom_pipe(d, length, eps)],
                [
                    fitting("entrance_sharp"),
                    fitting("elbow_90_lr", quantity=3),
                    fitting("gate_valve"),
                    fitting("exit"),
                ],
            )
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
    )
    return ReferenceCase(
        name="single_pipe_fittings",
        description=(
            "One pipe with a sharp entrance, three long-radius 90-degree elbows, a gate valve "
            "and an exit: verifies the fitting K correlations (Crane via fluids), quantities "
            "and the K v^2/2g law."
        ),
        source=_source(
            "single_pipe_fittings",
            "Darcy-Weisbach + Colebrook; K from fluids entrance_sharp(Crane), "
            "bend_rounded_Crane(r/D 1.5), K_gate_valve_Crane, exit_normal; brentq",
        ),
        project=project,
        expected=expected,
    )


def series_reducer_contraction() -> ReferenceCase:
    """Two segments in series in one connection, large → small, with a sudden reducer.

    Flow is positive (from the large segment 0 into the small segment 1), so the reducer is a
    sudden contraction with K on the small (downstream) pipe velocity v1; the exit sits on
    segment 1 (pipeIndex 1). Energy equation:
        H1 − H2 = f0 (L0/D0) v0²/(2g) + f1 (L1/D1) v1²/(2g) + (K_contraction + K_exit) v1²/(2g)
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d0, l0, e0 = 0.1023, 40.0, 4.5e-5
    d1, l1, e1 = 0.0525, 25.0, 4.5e-5
    z1, level1, z2, level2 = 6.0, 2.0, 0.0, 1.0
    h1, h2 = z1 + level1, z2 + level2
    k_small = k_sudden_contraction(d0, d1) + k_exit()

    def head_loss(q: float) -> float:
        return (
            friction_head_loss(q, d0, l0, e0, nu)
            + friction_head_loss(q, d1, l1, e1, nu)
            + minor_head_loss(q, k_small, d1)
        )

    q = solve_flow(head_loss, h1 - h2)
    require_regime(q, d0, nu, "turbulent")
    require_regime(q, d1, nu, "turbulent")

    project = make_project(
        "ref-series-reducer-contraction",
        "Series pipes with a sudden contraction",
        custom_fluid(name, rho, mu),
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [
            connect(
                "L1",
                "R1:port_1",
                "R2:port_1",
                [custom_pipe(d0, l0, e0), custom_pipe(d1, l1, e1)],
                [fitting("reducer_sudden", pipe_index=0), fitting("exit", pipe_index=1)],
            )
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
    )
    return ReferenceCase(
        name="series_reducer_contraction",
        description=(
            "One connection with two segments (102.3 mm then 52.5 mm) and a sudden reducer, "
            "flow large to small: verifies segments in series, the sudden-contraction K on the "
            "small pipe and a fitting referenced to pipeIndex 1."
        ),
        source=_source(
            "series_reducer_contraction",
            "Darcy-Weisbach + Colebrook per segment; fluids contraction_sharp(Crane), "
            "exit_normal; brentq",
        ),
        project=project,
        expected=expected,
    )


def series_reducer_expansion_reverse_flow() -> ReferenceCase:
    """The same two-segment geometry, but the 'to' reservoir is higher, so Q < 0.

    Flow runs from RB through the small segment 1, then the reducer acts as a sudden expansion
    into the large segment 0 (K on the small, upstream pipe velocity v1), then exits into RA.
    In the flow direction (magnitude q = |Q|):
        HB − HA = f1 (L1/D1) v1²/(2g) + f0 (L0/D0) v0²/(2g)
                  + (K_expansion + K_entrance) v1²/(2g) + K_exit v0²/(2g)
    and the connection flow (positive from RA to RB) is Q = −q.
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d0, l0, e0 = 0.1023, 40.0, 4.5e-5
    d1, l1, e1 = 0.0525, 25.0, 4.5e-5
    za, level_a, zb, level_b = 0.0, 1.0, 6.0, 1.5
    ha, hb = za + level_a, zb + level_b
    k_small = k_sudden_expansion(d1, d0) + k_entrance_sharp()
    k_large = k_exit()

    def head_loss(q: float) -> float:
        return (
            friction_head_loss(q, d1, l1, e1, nu)
            + friction_head_loss(q, d0, l0, e0, nu)
            + minor_head_loss(q, k_small, d1)
            + minor_head_loss(q, k_large, d0)
        )

    q = solve_flow(head_loss, hb - ha)
    require_regime(q, d0, nu, "turbulent")
    require_regime(q, d1, nu, "turbulent")

    project = make_project(
        "ref-series-reducer-expansion",
        "Series pipes with a sudden expansion (reverse flow)",
        custom_fluid(name, rho, mu),
        [reservoir("RA", za, level_a), reservoir("RB", zb, level_b)],
        [
            connect(
                "L1",
                "RA:port_1",
                "RB:port_1",
                [custom_pipe(d0, l0, e0), custom_pipe(d1, l1, e1)],
                [
                    fitting("exit", pipe_index=0),
                    fitting("reducer_sudden", pipe_index=0),
                    fitting("entrance_sharp", pipe_index=1),
                ],
            )
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": -q},
        egl={"RA:port_1": ha, "RB:port_1": hb},
    )
    return ReferenceCase(
        name="series_reducer_expansion_reverse_flow",
        description=(
            "Two segments and a sudden reducer with flow against the connection direction "
            "(small to large): verifies negative flow, signed losses and that the reducer acts "
            "as an expansion (fluids diffuser_sharp on the small pipe) when the flow reverses."
        ),
        source=_source(
            "series_reducer_expansion_reverse_flow",
            "Darcy-Weisbach + Colebrook per segment; fluids diffuser_sharp (Rennels), "
            "entrance_sharp(Crane), exit_normal; brentq",
        ),
        project=project,
        expected=expected,
    )


def series_tee_plugged_branch() -> ReferenceCase:
    """R1 → L1 → ideal tee (run) → L2 → R2, with the tee's branch piped to a plug.

    The plugged branch is a dead end, so its flow is zero and its EGL equals the tee's: an ideal
    tee has one EGL at every port, and a pipe with Q = 0 has no loss. Series energy equation:
        H1 − H2 = h_L1(Q) + h_L2(Q),   H_tee = H1 − h_L1(Q)
    Static pressures (design §1.1): at the run ports p = ρ g (H_tee − z_tee − v²/2g) with v in
    the connected pipe; at the branch port and the plug v = 0, so p = ρ g (H_tee − z).
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d1, l1, e1 = 0.0779, 120.0, 4.5e-5
    d2, l2, e2 = 0.0627, 80.0, 4.5e-5
    d3, l3, e3 = 0.0409, 15.0, 4.5e-5
    z1, level1, z2, level2 = 8.0, 2.0, 0.0, 1.0
    z_tee, z_plug = 2.0, 5.0
    h1, h2 = z1 + level1, z2 + level2

    q = solve_flow(
        lambda q: friction_head_loss(q, d1, l1, e1, nu) + friction_head_loss(q, d2, l2, e2, nu),
        h1 - h2,
    )
    require_regime(q, d1, nu, "turbulent")
    require_regime(q, d2, nu, "turbulent")
    h_tee = h1 - friction_head_loss(q, d1, l1, e1, nu)

    project = make_project(
        "ref-series-tee-plugged",
        "Series pipes through a tee with a plugged branch",
        custom_fluid(name, rho, mu),
        [
            reservoir("R1", z1, level1),
            ideal_tee("T1", z_tee),
            plug("P1", z_plug),
            reservoir("R2", z2, level2),
        ],
        [
            connect("L1", "R1:port_1", "T1:run_inlet", [custom_pipe(d1, l1, e1)]),
            connect("L2", "T1:run_outlet", "R2:port_1", [custom_pipe(d2, l2, e2)]),
            connect("L3", "T1:branch", "P1:port_1", [custom_pipe(d3, l3, e3)]),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q, "L3": 0.0},
        egl={
            "R1:port_1": h1,
            "T1:run_inlet": h_tee,
            "T1:run_outlet": h_tee,
            "T1:branch": h_tee,
            "P1:port_1": h_tee,
            "R2:port_1": h2,
        },
        pressures={
            "T1:run_inlet": static_pressure(rho, h_tee, z_tee, velocity(q, d1)),
            "T1:run_outlet": static_pressure(rho, h_tee, z_tee, velocity(q, d2)),
            "T1:branch": static_pressure(rho, h_tee, z_tee, 0.0),
            "P1:port_1": static_pressure(rho, h_tee, z_plug, 0.0),
        },
    )
    return ReferenceCase(
        name="series_tee_plugged_branch",
        description=(
            "Series flow through the run of an ideal tee whose branch is piped to a plug 3 m "
            "above it: the dead end carries zero flow, the plugged branch has the run's EGL, and "
            "port static pressures account for elevation and velocity head."
        ),
        source=_source("series_tee_plugged_branch", "Darcy-Weisbach + Colebrook in series; brentq"),
        project=project,
        expected=expected,
    )


def parallel_pipes_ideal_tees() -> ReferenceCase:
    """R1 → L_in → T1, two parallel pipes T1 → T2 (run: LA, branch: LB), T2 → L_out → R2.

    Unknowns QA, QB (Q = QA + QB). Ideal tees hold one EGL each, so the two parallel paths share
    the head drop H_T1 − H_T2. Two equations, solved together with fsolve:
        H1 − H2 = h_in(Q) + h_A(QA) + h_out(Q)
        h_A(QA) = h_B(QB)
    LB also carries two custom fittings, K = 2.5 each (user input), on its own velocity.
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d_in, l_in, e_in = 0.1541, 50.0, 4.5e-5
    da, la, ea = 0.1023, 300.0, 4.5e-5
    db, lb, eb = 0.0779, 180.0, 1.5e-4
    k_b, n_b = 2.5, 2
    d_out, l_out, e_out = 0.1541, 60.0, 4.5e-5
    z1, level1, z2, level2 = 12.0, 3.0, 0.0, 2.0
    z_t1, z_t2 = 3.0, 1.0
    h1, h2 = z1 + level1, z2 + level2

    def h_in(q: float) -> float:
        return friction_head_loss(q, d_in, l_in, e_in, nu)

    def h_a(q: float) -> float:
        return friction_head_loss(q, da, la, ea, nu)

    def h_b(q: float) -> float:
        return friction_head_loss(q, db, lb, eb, nu) + minor_head_loss(q, n_b * k_b, db)

    def h_out(q: float) -> float:
        return friction_head_loss(q, d_out, l_out, e_out, nu)

    def residuals(x: NDArray[np.float64]) -> list[float]:
        qa, qb = float(x[0]), float(x[1])
        return [h1 - h2 - (h_in(qa + qb) + h_a(qa) + h_out(qa + qb)), h_a(qa) - h_b(qb)]

    # xtol = 1e-12 (relative step) already reaches machine-precision residuals; tighter values
    # make MINPACK report "not making good progress" at the same answer.
    solution, _, ier, message = fsolve(residuals, [0.02, 0.01], xtol=1.0e-12, full_output=True)
    if ier != 1 or max(abs(r) for r in residuals(solution)) > 1.0e-12:
        raise RuntimeError(f"fsolve failed: {message}")
    qa, qb = float(solution[0]), float(solution[1])
    q = qa + qb
    for flow, d in ((q, d_in), (qa, da), (qb, db), (q, d_out)):
        require_regime(flow, d, nu, "turbulent")
    h_t1 = h1 - h_in(q)
    h_t2 = h2 + h_out(q)

    project = make_project(
        "ref-parallel-pipes",
        "Parallel pipes between two ideal tees",
        custom_fluid(name, rho, mu),
        [
            reservoir("R1", z1, level1),
            ideal_tee("T1", z_t1),
            ideal_tee("T2", z_t2),
            reservoir("R2", z2, level2),
        ],
        [
            connect("LIN", "R1:port_1", "T1:run_inlet", [custom_pipe(d_in, l_in, e_in)]),
            connect("LA", "T1:run_outlet", "T2:run_inlet", [custom_pipe(da, la, ea)]),
            connect(
                "LB",
                "T1:branch",
                "T2:branch",
                [custom_pipe(db, lb, eb)],
                [fitting("custom", quantity=n_b, k_override=k_b)],
            ),
            connect("LOUT", "T2:run_outlet", "R2:port_1", [custom_pipe(d_out, l_out, e_out)]),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"LIN": q, "LA": qa, "LB": qb, "LOUT": q},
        egl={
            "R1:port_1": h1,
            "T1:run_inlet": h_t1,
            "T1:run_outlet": h_t1,
            "T1:branch": h_t1,
            "T2:run_inlet": h_t2,
            "T2:branch": h_t2,
            "T2:run_outlet": h_t2,
            "R2:port_1": h2,
        },
        # v at a port = flow / area of the connected pipe's end segment at that port.
        pressures={
            "T1:run_inlet": static_pressure(rho, h_t1, z_t1, velocity(q, d_in)),
            "T1:run_outlet": static_pressure(rho, h_t1, z_t1, velocity(qa, da)),
            "T1:branch": static_pressure(rho, h_t1, z_t1, velocity(qb, db)),
            "T2:run_inlet": static_pressure(rho, h_t2, z_t2, velocity(qa, da)),
            "T2:branch": static_pressure(rho, h_t2, z_t2, velocity(qb, db)),
            "T2:run_outlet": static_pressure(rho, h_t2, z_t2, velocity(q, d_out)),
        },
    )
    return ReferenceCase(
        name="parallel_pipes_ideal_tees",
        description=(
            "Two dissimilar parallel pipes (one with custom K fittings) between two ideal tees: "
            "verifies the flow split, ideal-tee junctions (one EGL per tee, flow entering through "
            "a branch port) and port pressures at different pipe velocities."
        ),
        source=_source(
            "parallel_pipes_ideal_tees",
            "Darcy-Weisbach + Colebrook; parallel split solved with scipy.optimize.fsolve",
        ),
        project=project,
        expected=expected,
    )


def pressurized_reservoir_to_reference_node() -> ReferenceCase:
    """Pressurized reservoir → L1 → ideal tee (branch plugged) → L2 → ideal reference node.

    Boundaries (design §1.2): reservoir H_R = z + level + p_surface/(ρg); reference node
    H_N = z_N + p_set/(ρg). Series energy equation, fittings on each pipe's own velocity:
        H_R − H_N = [f1 L1/D1 + K_ent + 2 K_elbow(D1)] v1²/(2g)
                    + [f2 L2/D2 + K_elbow(D2) + K_gate(D2)] v2²/(2g)
    Pressures: the reservoir port (set at 0.4 m) is a quiescent boundary, p = ρ g (H_R − 0.4);
    the reference node's port reports p_set; tee ports and the plug as in
    series_tee_plugged_branch. The fluid is denser than water (ρ = 1050) so ρ enters each
    pressure-to-head conversion visibly.
    """
    name, rho, mu = "Brine (custom input)", 1050.0, 1.3e-3
    nu = mu / rho
    d1, l1, e1 = 0.0627, 35.0, 4.5e-5
    d2, l2, e2 = 0.0525, 50.0, 4.5e-5
    d3, l3, e3 = 0.0266, 4.0, 4.5e-5
    z_r, level_r, p_surface, z_port_r = 0.0, 2.0, 2.5e5, 0.4
    z_tee, z_plug = 6.0, 9.5
    z_n, p_set = 12.0, 1.2e5
    h_r = z_r + level_r + p_surface / (rho * G)
    h_n = z_n + p_set / (rho * G)
    k1 = k_entrance_sharp() + 2 * k_elbow_90_lr(d1)
    k2 = k_elbow_90_lr(d2) + k_gate_valve(d2)

    def h_l1(q: float) -> float:
        return friction_head_loss(q, d1, l1, e1, nu) + minor_head_loss(q, k1, d1)

    def h_l2(q: float) -> float:
        return friction_head_loss(q, d2, l2, e2, nu) + minor_head_loss(q, k2, d2)

    q = solve_flow(lambda q: h_l1(q) + h_l2(q), h_r - h_n)
    require_regime(q, d1, nu, "turbulent")
    require_regime(q, d2, nu, "turbulent")
    h_tee = h_r - h_l1(q)

    project = make_project(
        "ref-pressurized-reservoir",
        "Pressurized reservoir feeding a fixed-pressure main",
        custom_fluid(name, rho, mu),
        [
            reservoir("R1", z_r, level_r, surface_pressure=p_surface, port_elevation=z_port_r),
            ideal_tee("T1", z_tee),
            plug("P1", z_plug),
            reference_node("N1", z_n, p_set),
        ],
        [
            connect(
                "L1",
                "R1:port_1",
                "T1:run_inlet",
                [custom_pipe(d1, l1, e1)],
                [fitting("entrance_sharp"), fitting("elbow_90_lr", quantity=2)],
            ),
            connect(
                "L2",
                "T1:run_outlet",
                "N1:port_1",
                [custom_pipe(d2, l2, e2)],
                [fitting("elbow_90_lr"), fitting("gate_valve")],
            ),
            connect("L3", "T1:branch", "P1:port_1", [custom_pipe(d3, l3, e3)]),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q, "L3": 0.0},
        egl={
            "R1:port_1": h_r,
            "T1:run_inlet": h_tee,
            "T1:run_outlet": h_tee,
            "T1:branch": h_tee,
            "P1:port_1": h_tee,
            "N1:port_1": h_n,
        },
        pressures={
            "R1:port_1": static_pressure(rho, h_r, z_port_r, 0.0),
            "T1:run_inlet": static_pressure(rho, h_tee, z_tee, velocity(q, d1)),
            "T1:run_outlet": static_pressure(rho, h_tee, z_tee, velocity(q, d2)),
            "T1:branch": static_pressure(rho, h_tee, z_tee, 0.0),
            "P1:port_1": static_pressure(rho, h_tee, z_plug, 0.0),
            "N1:port_1": static_pressure(rho, h_n, z_n, 0.0),
        },
    )
    return ReferenceCase(
        name="pressurized_reservoir_to_reference_node",
        description=(
            "A reservoir under 250 kPa gauge surface pressure supplies an ideal reference node "
            "held at 120 kPa gauge, 12 m higher, through a tee with a plugged branch: verifies "
            "surfacePressure and reference-node heads (p/(rho g) with rho = 1050), an explicit "
            "port elevation, and static pressures at boundary, run, branch and plug ports."
        ),
        source=_source(
            "pressurized_reservoir_to_reference_node",
            "Darcy-Weisbach + Colebrook; K from fluids entrance_sharp(Crane), "
            "bend_rounded_Crane(r/D 1.5), K_gate_valve_Crane; brentq",
        ),
        project=project,
        expected=expected,
    )


def library_pipe_builtin_water() -> ReferenceCase:
    """Built-in water and library pipes: carbon steel schedule 40 NPS 4 then NPS 3.

    Water at 293.15 K: ρ and μ from CoolProp at 101325 Pa. Pipe inner diameters and roughness
    from fluids (nearest_pipe; roughness_Farshad 'Carbon steel, bare' at the inner diameter).
    Energy equation (contraction and exit on the NPS 3 velocity v1, entrance on v0):
        H1 − H2 = [f0 L0/D0 + K_ent] v0²/(2g) + [f1 L1/D1 + K_contraction + K_exit] v1²/(2g)
    """
    temperature = 293.15
    rho, mu = water_properties(temperature)
    nu = mu / rho
    nps0, l0 = 4.0, 100.0
    nps1, l1 = 3.0, 50.0
    d0, e0 = carbon_steel_schedule_40(nps0)
    d1, e1 = carbon_steel_schedule_40(nps1)
    z1, level1, z2, level2 = 4.0, 2.0, 0.0, 0.5
    h1, h2 = z1 + level1, z2 + level2
    k0 = k_entrance_sharp()
    k1 = k_sudden_contraction(d0, d1) + k_exit()

    def head_loss(q: float) -> float:
        return (
            friction_head_loss(q, d0, l0, e0, nu)
            + minor_head_loss(q, k0, d0)
            + friction_head_loss(q, d1, l1, e1, nu)
            + minor_head_loss(q, k1, d1)
        )

    q = solve_flow(head_loss, h1 - h2)
    require_regime(q, d0, nu, "turbulent")
    require_regime(q, d1, nu, "turbulent")

    project = make_project(
        "ref-library-pipe-water",
        "Library pipes with built-in water",
        builtin_water(temperature),
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [
            connect(
                "L1",
                "R1:port_1",
                "R2:port_1",
                [
                    # Nominal sizes are stored as NPS · 0.0254 m (design §10), rounded so the
                    # JSON shows 0.1016 and 0.0762 rather than binary noise.
                    library_pipe("carbon_steel", "40", round(nps0 * INCH, 10), l0),
                    library_pipe("carbon_steel", "40", round(nps1 * INCH, 10), l1),
                ],
                [
                    fitting("entrance_sharp", pipe_index=0),
                    fitting("reducer_sudden", pipe_index=0),
                    fitting("exit", pipe_index=1),
                ],
            )
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
    )
    return ReferenceCase(
        name="library_pipe_builtin_water",
        description=(
            "Built-in water at 20 C through carbon steel schedule 40 NPS 4 and NPS 3 library "
            "pipes with a sudden reducer: verifies water properties (CoolProp), library inner "
            "diameters (ASME B36.10M via fluids) and Farshad roughness."
        ),
        source=_source(
            "library_pipe_builtin_water",
            "CoolProp PropsSI('Water') at 101325 Pa; fluids nearest_pipe and "
            "roughness_Farshad('Carbon steel, bare', Di); Darcy-Weisbach + Colebrook; K from "
            "fluids entrance_sharp(Crane), contraction_sharp(Crane), exit_normal; brentq",
        ),
        project=project,
        expected=expected,
    )


def transitional_flow_colebrook() -> ReferenceCase:
    """Reservoir → one pipe → reservoir with 2000 < Re < 4000, 'colebrook' mode.

    f(Re) is the cubic Hermite interpolation (transition_friction_factor) between the laminar
    law at Re = 2000 and Colebrook at Re = 4000. Energy equation as in single_pipe_turbulent:
        H1 − H2 = f(Re) (L/D) v²/(2g); one unknown Q (brentq).
    """
    name, rho, mu = "Light oil (custom input)", 900.0, 9.0e-3
    nu = mu / rho
    d, length, eps = 0.05, 100.0, 4.5e-5
    z1, level1, z2, level2 = 1.0, 1.0, 0.0, 0.5
    h1, h2 = z1 + level1, z2 + level2

    q = solve_flow(lambda q: friction_head_loss(q, d, length, eps, nu), h1 - h2)
    require_regime(q, d, nu, "transitional")

    project = make_project(
        "ref-transitional",
        "Single pipe in transitional flow",
        custom_fluid(name, rho, mu),
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [connect("L1", "R1:port_1", "R2:port_1", [custom_pipe(d, length, eps)])],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
        # Design §2.1: every segment with 2000 ≤ Re < 4000 is flagged.
        flags=[{"code": "TRANSITIONAL_FLOW", "connectionId": "L1"}],
    )
    return ReferenceCase(
        name="transitional_flow_colebrook",
        description=(
            "Single pipe at Re about 3200 in 'colebrook' mode: verifies the transition-zone "
            "friction factor (cubic Hermite in Re/2000 between 64/Re at 2000 and Colebrook at "
            "4000, design 2.1) and the TRANSITIONAL_FLOW flag."
        ),
        source=_source(
            "transitional_flow_colebrook",
            "Hermite cubic transition between Hagen-Poiseuille and Colebrook "
            "(analytic Colebrook slope); brentq",
        ),
        project=project,
        expected=expected,
    )


def series_reducer_conical_both_directions() -> ReferenceCase:
    """R1 → L1 → ideal tee (branch plugged) → L2 → R2, a conical reducer in each connection.

    L1 runs 0.1023 m → 0.0525 m with flow along it: a conical contraction (30°) with K on the
    small, downstream velocity v1; a rounded entrance (r/D = 0.06) on the large pipe. L2 is drawn
    from R2 to the tee, 0.1023 m (at R2) → 0.0525 m (at the tee); R2 is lower, so its flow is
    negative: from the tee's small pipe into the large one, a conical expansion (20°) with K on
    the small, upstream velocity, then an exit from the large pipe into R2. Series energy
    equation (q = |Q|, all four segments turbulent):
        H1 − H2 = f(L/D)v²/2g over the four segments + K_ent v_L1,0²/2g + K_con v_L1,1²/2g
                  + K_exp v_L2,1²/2g + K_exit v_L2,0²/2g
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d_large, d_small = 0.1023, 0.0525
    eps = 4.5e-5
    l1_large, l1_small = 30.0, 20.0
    l2_large, l2_small = 45.0, 15.0
    angle_contraction, angle_expansion = 30.0, 20.0
    entrance_ratio = 0.06
    z1, level1, z2, level2 = 9.0, 2.0, 0.0, 1.5
    z_tee, z_plug = 3.0, 4.0
    d_stub, l_stub = 0.0409, 3.0
    h1, h2 = z1 + level1, z2 + level2
    k_entrance = k_entrance_rounded(d_large, entrance_ratio)
    k_contraction = k_conical_contraction(d_large, d_small, angle_contraction)
    k_expansion = k_conical_expansion(d_small, d_large, angle_expansion)

    def h_l1(q: float) -> float:
        return (
            friction_head_loss(q, d_large, l1_large, eps, nu)
            + friction_head_loss(q, d_small, l1_small, eps, nu)
            + minor_head_loss(q, k_entrance, d_large)
            + minor_head_loss(q, k_contraction, d_small)
        )

    def h_l2(q: float) -> float:  # in the flow direction, tee → R2
        return (
            friction_head_loss(q, d_small, l2_small, eps, nu)
            + friction_head_loss(q, d_large, l2_large, eps, nu)
            + minor_head_loss(q, k_expansion, d_small)
            + minor_head_loss(q, k_exit(), d_large)
        )

    q = solve_flow(lambda q: h_l1(q) + h_l2(q), h1 - h2)
    require_regime(q, d_large, nu, "turbulent")
    require_regime(q, d_small, nu, "turbulent")
    h_tee = h1 - h_l1(q)

    project = make_project(
        "ref-series-reducer-conical",
        "Conical reducers in both flow directions",
        custom_fluid(name, rho, mu),
        [
            reservoir("R1", z1, level1),
            ideal_tee("T1", z_tee),
            plug("P1", z_plug),
            reservoir("R2", z2, level2),
        ],
        [
            connect(
                "L1",
                "R1:port_1",
                "T1:run_inlet",
                [custom_pipe(d_large, l1_large, eps), custom_pipe(d_small, l1_small, eps)],
                [
                    fitting("entrance_rounded", radius_ratio=entrance_ratio),
                    fitting("reducer_conical", angle=angle_contraction),
                ],
            ),
            connect(
                "L2",
                "R2:port_1",
                "T1:run_outlet",
                [custom_pipe(d_large, l2_large, eps), custom_pipe(d_small, l2_small, eps)],
                [fitting("exit"), fitting("reducer_conical", angle=angle_expansion)],
            ),
            connect("L3", "T1:branch", "P1:port_1", [custom_pipe(d_stub, l_stub, eps)]),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": -q, "L3": 0.0},
        egl={
            "R1:port_1": h1,
            "T1:run_inlet": h_tee,
            "T1:run_outlet": h_tee,
            "T1:branch": h_tee,
            "P1:port_1": h_tee,
            "R2:port_1": h2,
        },
        # Both run ports meet the 0.0525 m end segments (L1's last, L2's last).
        pressures={
            "T1:run_inlet": static_pressure(rho, h_tee, z_tee, velocity(q, d_small)),
            "T1:run_outlet": static_pressure(rho, h_tee, z_tee, velocity(q, d_small)),
            "T1:branch": static_pressure(rho, h_tee, z_tee, 0.0),
            "P1:port_1": static_pressure(rho, h_tee, z_plug, 0.0),
        },
    )
    return ReferenceCase(
        name="series_reducer_conical_both_directions",
        description=(
            "A conical contraction with forward flow and a conical expansion with reverse flow "
            "(connection drawn against the flow), plus a rounded entrance and an exit: verifies "
            "the direction-dependent conical reducer correlations, their small-pipe reference "
            "velocity and the cone angle input."
        ),
        source=_source(
            "series_reducer_conical_both_directions",
            "Darcy-Weisbach + Colebrook per segment; K from fluids "
            "contraction_conical_Crane(angle), diffuser_conical(angle, method='Crane'), "
            "entrance_rounded(Crane), exit_normal; brentq",
        ),
        project=project,
        expected=expected,
    )


def single_pipe_crane_valves_and_elbows() -> ReferenceCase:
    """Reservoir → one pipe carrying every remaining Crane fitting → reservoir.

    On the one segment (reference velocity v = Q/A): a projecting entrance, two short-radius 90°
    elbows, long- and short-radius 45° elbows, threaded 90° and 45° elbows, a 60° bend of
    r/D = 3, the fully open ball, globe, butterfly, plug, swing-check and lift-check valves, and
    an exit. Energy equation:
        H1 − H2 = [f (L/D) + Σ n_j K_j] v²/(2g)
    with each K from the fluids function design §3 names for that fitting type.
    """
    name, rho, mu = FLUID_A
    nu = mu / rho
    d, length, eps = 0.1023, 80.0, 4.5e-5
    z1, level1, z2, level2 = 12.0, 3.0, 0.0, 2.0
    h1, h2 = z1 + level1, z2 + level2
    bend_angle, bend_ratio = 60.0, 3.0
    valves = k_crane_valves(d)
    k_total = (
        k_entrance_projecting(d)
        + 2 * k_bend(d, 90.0, 1.0)
        + k_bend(d, 45.0, 1.5)
        + k_bend(d, 45.0, 1.0)
        + k_threaded_elbow(d, 90.0)
        + k_threaded_elbow(d, 45.0)
        + k_bend(d, bend_angle, bend_ratio)
        + sum(valves.values())
        + k_exit()
    )

    q = solve_flow(
        lambda q: friction_head_loss(q, d, length, eps, nu) + minor_head_loss(q, k_total, d),
        h1 - h2,
    )
    require_regime(q, d, nu, "turbulent")

    project = make_project(
        "ref-single-pipe-crane-fittings",
        "Single pipe with Crane valves, elbows and bends",
        custom_fluid(name, rho, mu),
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [
            connect(
                "L1",
                "R1:port_1",
                "R2:port_1",
                [custom_pipe(d, length, eps)],
                [
                    fitting("entrance_projecting"),
                    fitting("elbow_90_sr", quantity=2),
                    fitting("elbow_45_lr"),
                    fitting("elbow_45_sr"),
                    fitting("elbow_90_threaded"),
                    fitting("elbow_45_threaded"),
                    fitting("bend", angle=bend_angle, radius_ratio=bend_ratio),
                    fitting("ball_valve"),
                    fitting("globe_valve"),
                    fitting("butterfly_valve"),
                    fitting("plug_valve"),
                    fitting("swing_check_valve"),
                    fitting("lift_check_valve"),
                    fitting("exit"),
                ],
            )
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
    )
    return ReferenceCase(
        name="single_pipe_crane_valves_and_elbows",
        description=(
            "One pipe with a projecting entrance, short- and long-radius and threaded elbows, a "
            "60-degree bend and fully open ball, globe, butterfly, plug, swing-check and "
            "lift-check valves: verifies each library fitting's K correlation and fixed "
            "arguments end to end."
        ),
        source=_source(
            "single_pipe_crane_valves_and_elbows",
            "Darcy-Weisbach + Colebrook; K from fluids entrance_distance(Crane), "
            "bend_rounded_Crane (r/D 1, 1.5, 3), bend_rounded(Crane standard), "
            "K_ball_valve_Crane, K_globe_valve_Crane, K_butterfly_valve_Crane(style 0), "
            "K_plug_valve_Crane(style 0), K_swing_check_valve_Crane(angled), "
            "K_lift_check_valve_Crane(angled), exit_normal; brentq",
        ),
        project=project,
        expected=expected,
    )


CLOSED_FORM_CASES: tuple[Callable[[], ReferenceCase], ...] = (
    single_pipe_turbulent,
    single_pipe_laminar,
    single_pipe_fittings,
    series_reducer_contraction,
    series_reducer_expansion_reverse_flow,
    series_tee_plugged_branch,
    parallel_pipes_ideal_tees,
    pressurized_reservoir_to_reference_node,
    library_pipe_builtin_water,
    transitional_flow_colebrook,
    series_reducer_conical_both_directions,
    single_pipe_crane_valves_and_elbows,
)
