"""Closed-form reference case at the finite edge of a boundary's head (proposal
open-defects-2.md §3 A2a and §5; CLAUDE.md D6, D7).

A reservoir holds H = z + level + p_s/(ρg) at its ports, an ideal reference node H = z_port +
p/(ρg) (TSD §5.1 step 3, design §1.1), with g = ``fluids.constants.g`` (design §1.3). In IEEE
754 binary64 the quotient p/(ρg) is p / fl(ρ·g), the product rounded first, as the specs group
it (and as ``network_check.fixed_heads`` evaluates it). For a gauge pressure p ≠ 0 it is finite
exactly when ρ is at least an edge density ρ_edge(p), the smallest double for which it is:

- **Monotone.** For ρ > 0, ρ ↦ fl(ρ·g) is non-decreasing (rounding to nearest is monotone) and
  x ↦ fl(|p|/x) non-increasing, so "|p|/fl(ρ·g) is finite" is false below one double and true
  from it on, and p/fl(ρ·g) = ±|p|/fl(ρ·g) (rounding is symmetric in sign).
- **Bisection over the doubles.** Positive binary64 values are ordered as their bit patterns
  read as integers (IEEE 754-2019 §3.4: the biased exponent precedes the significand), so a
  bisection over those integers finds that double exactly (``finite_head_edge``).
- **Where it starts.** The real edge is |p|/(g·DBL_MAX) with DBL_MAX = ``sys.float_info.max``,
  but g·DBL_MAX overflows (g > 1), so the start is |p|/g/DBL_MAX, rounded twice, and the
  bracket [start/2, 2·start] (exact: powers of 2 in the normal range) is checked to hold the
  edge before the bisection.

Measured with fluids' g = 9.80665 m/s²: ρ_edge(10⁸ Pa) = 5.672359721482876·10⁻³⁰² kg/m³, the
start itself (0 ulps from it), where 10⁸/(ρg) is DBL_MAX exactly, and at the next double below
it, 5.672359721482875·10⁻³⁰², the quotient is inf; ρ_edge(−10⁵ Pa) = 5.672359721482876·10⁻³⁰⁵,
where −10⁵/(ρg) is −DBL_MAX. 10⁸ Pa and −10⁵ Pa are the schema's bounds on a gauge pressure
(``GaugePressure``), so at a density from ρ_edge(10⁸) up every boundary head the schema admits
is finite (an elevation of at most 10⁴ m and a level of at most 10³ m add to it without
overflow: 10 is less than half an ulp of DBL_MAX, 2⁹⁷⁰, so DBL_MAX + 10 rounds to DBL_MAX).

The case (``boundary_head_at_largest_double``): a reservoir R1 (z 0, level 10 m, 10⁸ Pa(g) on
its surface) in a custom fluid of density ρ_edge(10⁸) → L1 (0.1 m, 10 m) → a plug P1 (z 0).
Closed form: the plug passes nothing, so continuity at P1 gives Q_L1 = 0; Darcy–Weisbach has
h(0) = 0, so L1's energy equation gives H_P1 = H_R1 = 10 + 10⁸/(ρg) = DBL_MAX (guarded:
``require_largest_double``); with no flow v = 0 at both ports and the static pressure p = ρg(H
− z) is p_s + ρg(z_R + level − z_P) = 10⁸ Pa + 10ρg, where 10ρg ≈ 5.6·10⁻³⁰⁰ Pa vanishes in
binary64: 10⁸ Pa at both ports (guarded against the definition's ρg(H − z), the suite's
``static_pressure``, which gives 10⁸ Pa exactly here). The fluid's viscosity is FLUID_A's
1.0·10⁻³ Pa·s (a test input), so ν = μ/ρ ≈ 1.8·10²⁹⁸ m²/s; with no flow the case claims
nothing of the pipe law but h(0) = 0.

Measured on a clean ``593378d`` (``solve_project`` through the reference runner, and ``POST
/api/v1/solve``): converged, "3 Newton iterations in 1 outer iteration(s)", no flow, both EGLs
1.7976931348623157e+308 and 10⁸ Pa(g) at both ports. The proposal refuses a head that is not
finite (``BOUNDARY_HEAD_OUT_OF_RANGE``); this case is the side it must keep solving. The
infinite side is ``test_boundary_head_bounds.py``, through the API, with this module's
networks and edges.
Independence: written without reading ``opensolve_pipe.services``; nothing here imports it.
"""

import math
import struct
import sys
from collections.abc import Callable

from opensolve_pipe.models.components import IdealReferenceNode, Reservoir
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    custom_fluid,
    make_project,
    plug,
    reservoir,
)
from tests.reference.line import Line

MODULE = "derivations_boundary_heads"

DBL_MAX: float = sys.float_info.max
"""The largest finite binary64 value, (2 − 2⁻⁵²)·2¹⁰²³ (``sys.float_info.max``)."""
G = dv.G
"""Standard gravity, m/s² (``fluids.constants.g``), the g the solver uses (design §1.3)."""
PRESSURE_MAX = 1.0e8
"""Pa(g): the schema's largest gauge pressure (``GaugePressure``, le=1e8)."""
PRESSURE_MIN = -1.0e5
"""Pa(g): the schema's least gauge pressure (``GaugePressure``, ge=-1e5)."""
LEVEL = 10.0
"""m: R1's liquid level above its elevation (test input)."""
LINE = Line(0.1, 10.0)
"""L1: 0.1 m bore, 10 m long, ``line.ROUGHNESS`` (test inputs)."""
VISCOSITY = dv.FLUID_A[2]
"""Pa·s: FLUID_A's dynamic viscosity (test input)."""
FLUID_NAME = "Test liquid at the finite-head edge (custom input)"
PRESSURE_RELATIVE = 1.0e-12
"""The guard on the static pressure: ρg(H − z) against the closed form p_s + ρg(z + level − z)."""

METHOD = (
    "dead end: no flow, every EGL the reservoir's z + level + p/(rho g) = DBL_MAX at the "
    "smallest density whose p/(rho g) is finite (bisection over the doubles' bit patterns), "
    "static pressure p_s + rho g (z + level - z_plug)"
)


def _bits(x: float) -> int:
    """The binary64 bit pattern of x ≥ 0 as an integer (ordered like x, IEEE 754-2019 §3.4)."""
    value: int = struct.unpack("<q", struct.pack("<d", x))[0]
    return value


def _double(n: int) -> float:
    value: float = struct.unpack("<d", struct.pack("<q", n))[0]
    return value


def head_term(pressure: float, density: float) -> float:
    """p/(ρg) as the specs group it: p / fl(ρ·g), m (may be ±inf)."""
    return pressure / (density * G)


def finite_head_edge(pressure: float) -> float:
    """ρ_edge(p): the smallest positive double ρ for which p/(ρg) is finite (module docstring),
    by bisection over the doubles' bit patterns from the bracket [start/2, 2·start] around
    start = |p|/g/DBL_MAX."""
    if pressure == 0.0:
        raise ValueError("a zero pressure has a finite head at every density")

    def finite(density: float) -> bool:
        return math.isfinite(head_term(pressure, density))

    start = abs(pressure) / G / DBL_MAX
    low, high = start / 2.0, start * 2.0
    if finite(low) or not finite(high):
        raise ValueError("the bracket around |p|/g/DBL_MAX does not hold the edge")
    a, b = _bits(low), _bits(high)
    while b - a > 1:
        mid = (a + b) // 2
        if finite(_double(mid)):
            b = mid
        else:
            a = mid
    edge = _double(b)
    if not (finite(edge) and not finite(math.nextafter(edge, 0.0))):
        raise RuntimeError("the bisection did not end at the edge")
    return edge


def infinite_side(pressure: float) -> float:
    """The next double below ρ_edge(p): the largest density whose p/(ρg) is not finite."""
    return math.nextafter(finite_head_edge(pressure), 0.0)


def port_elevation(component: Reservoir | IdealReferenceNode) -> float:
    """The elevation of the boundary's one port: its own, else the component's (design §1.1)."""
    z = component.ports[0].elevation
    return component.elevation if z is None else z


def boundary_pressure(component: Reservoir | IdealReferenceNode) -> float:
    """The gauge pressure the boundary holds, Pa: a reservoir's on its surface, a reference
    node's at its port."""
    return component.surface_pressure if isinstance(component, Reservoir) else component.pressure


def still_head(component: Reservoir | IdealReferenceNode) -> float:
    """The boundary's head without its p/(ρg), m: a reservoir's z + level, a reference node's
    z_port."""
    if isinstance(component, Reservoir):
        return component.elevation + component.liquid_level
    return port_elevation(component)


def fixed_head(component: Reservoir | IdealReferenceNode, density: float) -> float:
    """A boundary's head by the specs' expressions (TSD §5.1 step 3): a reservoir's z + level +
    p_s/(ρg), a reference node's z_port + p/(ρg); ±inf past the edge."""
    return still_head(component) + head_term(boundary_pressure(component), density)


def require_largest_double(head: float) -> None:
    """Guard: the head is DBL_MAX itself (the case's purpose: the largest finite head)."""
    if head != DBL_MAX:
        raise ValueError(f"the head is {head!r}, not DBL_MAX")


def dead_end_project(
    pid: str, title: str, boundary: Reservoir | IdealReferenceNode, density: float
) -> Project:
    """``boundary`` (port port_1) → L1 → plug P1 at z 0: the case's network, and the API
    test's, in a custom fluid of ``density`` and FLUID_A's viscosity."""
    return make_project(
        pid,
        title,
        custom_fluid(FLUID_NAME, density, VISCOSITY),
        [boundary, plug("P1", 0.0)],
        [LINE.connect("L1", f"{boundary.id}:port_1", "P1:port_1")],
    )


def dead_end_state(
    boundary: Reservoir | IdealReferenceNode, density: float
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """(flows, EGLs, static pressures) of ``dead_end_project``: the plug passes nothing, so L1
    carries no flow and has no loss (h(0) = 0), every EGL is the boundary's head H_b, and with
    v = 0 at both ports p = p_b + ρg(H_b,still − z) at a port of elevation z (H_b,still the head
    without p_b/(ρg)), checked against the definition ρg(H − z) to ``PRESSURE_RELATIVE``."""
    head = fixed_head(boundary, density)
    if not math.isfinite(head):
        raise ValueError("the boundary's head is not finite")
    ports = {f"{boundary.id}:port_1": port_elevation(boundary), "P1:port_1": 0.0}
    pressures: dict[str, float] = {}
    for key, z in ports.items():
        closed = boundary_pressure(boundary) + density * G * (still_head(boundary) - z)
        definition = dv.static_pressure(density, head, z, 0.0)
        if not math.isclose(closed, definition, rel_tol=PRESSURE_RELATIVE):
            raise RuntimeError(
                f"{key}: p_b + ρg(H_still − z) = {closed!r}, ρg(H − z) = {definition!r}"
            )
        pressures[key] = closed
    return {"L1": 0.0}, dict.fromkeys(ports, head), pressures


def boundary_head_at_largest_double() -> ReferenceCase:
    """R1 (z 0, level 10 m, 10⁸ Pa(g)) → L1 (0.1 m, 10 m) → plug P1 (z 0), in a custom fluid of
    the smallest density whose 10⁸/(ρg) is finite: no flow, every EGL = DBL_MAX, 10⁸ Pa(g) at
    both ports (module docstring)."""
    name = "boundary_head_at_largest_double"
    rho = finite_head_edge(PRESSURE_MAX)
    r1 = reservoir("R1", 0.0, LEVEL, surface_pressure=PRESSURE_MAX)
    project = dead_end_project(
        f"ref-{name.replace('_', '-')}",
        "Plugged line from a reservoir whose head is the largest double",
        r1,
        rho,
    )
    flows, egl, pressures = dead_end_state(r1, rho)
    require_largest_double(fixed_head(r1, rho))
    if not all(p == PRESSURE_MAX for p in pressures.values()):
        raise ValueError(f"the static pressures {pressures} are not 1e8 Pa")
    return ReferenceCase(
        name=name,
        description=(
            "A reservoir 10 m deep under 1e8 Pa(g), in a custom fluid of the smallest density "
            f"({rho!r} kg/m3) for which 1e8/(rho g) is finite, feeding a plugged "
            "line: verifies that the largest finite boundary head (DBL_MAX) solves, with no "
            "flow, every EGL equal to the reservoir's head and 1e8 Pa(g) at the plug, rather "
            "than being refused as a head that is not finite."
        ),
        source=dv.source(name, METHOD, MODULE),
        project=project,
        expected=Expected(
            density=rho,
            dynamic_viscosity=VISCOSITY,
            flows=flows,
            egl=egl,
            pressures=pressures,
        ),
    )


CASES: tuple[Callable[[], ReferenceCase], ...] = (boundary_head_at_largest_double,)
