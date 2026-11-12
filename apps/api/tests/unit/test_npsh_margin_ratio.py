"""The NPSH margin ratio (docs/proposals/pumps-nits.md, item 4): PumpResult.npsh_margin_ratio is
NPSHa / NPSHr where both are known, NPSHr > 0 and the quotient is finite, and None otherwise; the
pump's trace states its equation and value, and a note where NPSHr is 0; the methods summary
states it.

Expected values are derived here, independently of solver code, as test_m3_solve does: the
operating flow from Darcy–Weisbach with fluids' Colebrook against s² H₀(Q/s) through SciPy's
PchipInterpolator; NPSHa = (EGL_s − z_s) + (p_atm − p_vap)/(ρg) with p_atm the 1976 standard
atmosphere at the site; NPSHr = s² NPSHr₀(Q/s), NPSHr₀ the PCHIP through the curve's points; and
the ratio NPSHa / NPSHr.
"""

import math
import random
from typing import Any

import pytest
from fluids.atmosphere import ATMOSPHERE_1976
from fluids.constants import g
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

from opensolve_pipe.models.results import ElementTrace, PumpResult, SolvedState
from opensolve_pipe.services.solver import solve_project

from .helpers import connection, custom_fluid, make_project, plug, reservoir, tee
from .test_m3_solve import (
    EFF,
    FLOWS,
    HEADS,
    L1,
    L2,
    NPSHR,
    P_VAP,
    Q_LOW,
    RHO,
    D,
    curve_head,
    flags,
    pipe_head,
    pump,
    valve,
)

SITE = 1200.0
P_ATM = float(ATMOSPHERE_1976(SITE).P)
"""Pa: the 1976 standard atmosphere at the site, as test_m3_solve.pump_line."""
EQUATION = "NPSH margin ratio = NPSHa / NPSHr (below 1: cavitation; not given where NPSHr is 0)"
VALUE = "NPSH margin ratio NPSHa/NPSHr"


def curve(npshr: list[tuple[float, float]] | None = NPSHR) -> dict[str, Any]:
    """test_m3_solve's curve, with ``npshr`` as its NPSHr points (None: no NPSHr curve)."""
    data: dict[str, Any] = {
        "id": "C1",
        "name": "test pump",
        "points": [{"flow": q, "head": h} for q, h in zip(FLOWS, HEADS, strict=True)],
        "efficiencyCurve": [{"flow": q, "efficiency": e} for q, e in EFF],
    }
    if npshr is not None:
        data["npshrCurve"] = [{"flow": q, "npshr": n} for q, n in npshr]
    return data


def line(
    *,
    elevation: float = 0.0,
    level: float = 2.0,
    surface_pressure: float = 0.0,
    h2: float = 20.0,
    speed: float = 1.0,
    status: str = "on",
    npshr: list[tuple[float, float]] | None = NPSHR,
    p_vap: float | None = P_VAP,
) -> SolvedState:
    """R1 (at ``elevation``, ``level`` above it, ``surface_pressure`` gauge) -> L1 -> PU (at 0)
    -> L2 -> R2 (level h2, at 0), at a 1200 m site."""
    comps = [
        reservoir("R1", elevation=elevation, level=level, surface_pressure=surface_pressure),
        pump(speed=speed, status=status),
        reservoir("R2", level=h2),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=L1),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=L2),
    ]
    project = make_project(
        comps,
        conns,
        pump_library=[curve(npshr)],
        fluid=custom_fluid(RHO, 1.0e-3, vapor_pressure=p_vap),
        site_elevation=SITE,
    )
    return solve_project(project)


def closed_form(
    *,
    elevation: float = 0.0,
    level: float = 2.0,
    surface_pressure: float = 0.0,
    h2: float = 20.0,
    speed: float = 1.0,
    npshr: list[tuple[float, float]] = NPSHR,
) -> tuple[float, float, float]:
    """(Q, NPSHa, NPSHr) of ``line`` by the closed form, inside the NPSHr curve's points."""
    h1 = elevation + level + surface_pressure / (RHO * g)  # the suction reservoir's EGL
    q = brentq(
        lambda q: curve_head(q, speed) - (h2 - h1 + pipe_head(q, L1, D) + pipe_head(q, L2, D)),
        Q_LOW,
        speed * FLOWS[-1],
        xtol=1e-15,
    )
    assert npshr[0][0] <= q / speed <= npshr[-1][0], "inside the NPSHr points"
    z_s = 0.0  # the pump's suction port, at the pump's elevation
    npsha = (h1 - pipe_head(q, L1, D) - z_s) + (P_ATM - P_VAP) / (RHO * g)
    required = speed**2 * float(PchipInterpolator(*zip(*npshr, strict=True))(q / speed))
    return q, npsha, required


def pump_trace(state: SolvedState) -> ElementTrace:
    return state.trace.elements["PU"]


def values(state: SolvedState) -> dict[str, float]:
    return {v.name: v.value for v in pump_trace(state).intermediates}


def ratio_json(state: SolvedState) -> Any:
    return state.model_dump(mode="json")["pumpResults"]["PU"]["npshMarginRatio"]


@pytest.mark.parametrize("speed", [1.0, 0.8])
def test_the_ratio_is_npsha_over_npshr(speed: float) -> None:
    state = line(speed=speed)
    q, npsha, npshr = closed_form(speed=speed)
    pr = state.pump_results["PU"]
    assert pr.status == "running"
    assert pr.operating_flow == pytest.approx(q, rel=1e-9)
    assert pr.npsh_margin_ratio == pytest.approx(npsha / npshr, rel=1e-9)
    # The quotient of the result's own NPSHa and NPSHr, bit for bit.
    assert pr.npsh_available is not None
    assert pr.npsh_required is not None
    assert pr.npsh_margin_ratio == pr.npsh_available / pr.npsh_required
    assert ratio_json(state) == pr.npsh_margin_ratio
    trace = pump_trace(state)
    assert EQUATION in trace.equations
    assert trace.equations.index(EQUATION) == (
        trace.equations.index("NPSH margin = NPSHa − NPSHr (negative: cavitation)") + 1
    )
    assert values(state)[VALUE] == pr.npsh_margin_ratio
    [ratio] = [v for v in trace.intermediates if v.name == VALUE]
    assert ratio.unit == ""
    names = [v.name for v in trace.intermediates]
    assert names.index(VALUE) == names.index("NPSH margin") + 1
    assert not [n for n in trace.notes if "NPSH margin ratio" in n]


def test_a_negative_npsha_gives_a_negative_ratio() -> None:
    """A vacuum tank 5 m below the pump: NPSHa < 0; the ratio is kept as it is, below 0."""
    case = {"elevation": -5.0, "level": 0.5, "surface_pressure": -80000.0, "h2": 10.0}
    state = line(**case)
    q, npsha, npshr = closed_form(**case)
    pr = state.pump_results["PU"]
    assert npsha < 0.0
    assert pr.operating_flow == pytest.approx(q, rel=1e-9)
    assert pr.npsh_margin_ratio == pytest.approx(npsha / npshr, rel=1e-9)
    assert pr.npsh_margin_ratio is not None
    assert pr.npsh_margin_ratio < 0.0
    assert flags(state, "CAVITATION") == ["PU"]


@pytest.mark.parametrize(
    "npshr",
    [
        [(0.005, 0.0), (0.02, 0.0), (0.03, 0.0)],  # zero throughout
        [(0.025, 0.0), (0.03, 4.0)],  # the tangent below the first point, held at 0
    ],
    ids=["zero-curve", "held-at-zero"],
)
def test_npshr_of_zero_gives_no_ratio_and_a_note(npshr: list[tuple[float, float]]) -> None:
    state = line(npshr=npshr)
    pr = state.pump_results["PU"]
    assert pr.status == "running"
    assert pr.npsh_required == 0.0
    assert pr.npsh_available is not None
    assert pr.npsh_margin == pr.npsh_available  # NPSHa − 0
    assert pr.npsh_margin_ratio is None
    assert ratio_json(state) is None
    assert not flags(state, "CAVITATION")
    trace = pump_trace(state)
    assert EQUATION in trace.equations
    assert VALUE not in values(state)
    [note] = [n for n in trace.notes if "NPSH margin ratio" in n]
    assert note.startswith("NPSH margin ratio is not given: NPSHr is 0 at the operating flow")


def test_a_quotient_too_large_to_represent_gives_no_ratio_and_a_note() -> None:
    """NPSHr of 1e-320 m (a subnormal float): NPSHa / NPSHr overflows to infinity."""
    tiny = 1.0e-320
    state = line(npshr=[(0.005, tiny), (0.02, tiny), (0.03, tiny)])
    pr = state.pump_results["PU"]
    assert pr.npsh_required == tiny
    assert pr.npsh_available is not None
    assert math.isinf(pr.npsh_available / tiny)
    assert pr.npsh_margin_ratio is None
    assert ratio_json(state) is None
    assert VALUE not in values(state)
    [note] = [n for n in pump_trace(state).notes if "NPSH margin ratio" in n]
    assert note.startswith("NPSH margin ratio is not given:")
    assert "not a finite number" in note


def _floating_loop() -> SolvedState:
    """R0 -> IV1 (isolated) -> T1; a loop T1 -> PU -> T2 -> T1 with a plugged stub off T2: the
    loop's flow is determined, its pressure level is not (UNDETERMINED_PRESSURE)."""
    comps = [
        reservoir("R0", level=10.0),
        valve("IV1", "gate", status="isolated"),
        tee("T1"),
        pump(),
        tee("T2"),
        plug("PL1"),
    ]
    conns = [
        connection("L1", ("R0", "port_1"), ("IV1", "inlet")),
        connection("L2", ("IV1", "outlet"), ("T1", "run_inlet")),
        connection("L3", ("T1", "run_outlet"), ("PU", "suction")),
        connection("L4", ("PU", "discharge"), ("T2", "run_inlet")),
        connection("L5", ("T2", "run_outlet"), ("PL1", "port_1")),
        connection("L6", ("T2", "branch"), ("T1", "branch"), length=300.0),
    ]
    project = make_project(
        comps,
        conns,
        pump_library=[curve()],
        fluid=custom_fluid(RHO, 1.0e-3, vapor_pressure=P_VAP),
        site_elevation=SITE,
    )
    return solve_project(project)


def _no_ratio(state: SolvedState) -> PumpResult:
    pr = state.pump_results["PU"]
    assert pr.npsh_margin_ratio is None
    assert ratio_json(state) is None
    assert VALUE not in values(state)
    assert not [n for n in pump_trace(state).notes if "NPSH margin ratio" in n]
    return pr


def test_no_npshr_curve_gives_no_ratio_and_no_equation() -> None:
    state = line(npshr=None)
    pr = _no_ratio(state)
    assert pr.status == "running"
    assert pr.npsh_available is not None
    assert pr.npsh_required is None
    assert EQUATION not in pump_trace(state).equations


@pytest.mark.parametrize(("status", "h2"), [("off", 20.0), ("on", 40.0)], ids=["off", "no_flow"])
def test_a_pump_not_running_gives_no_ratio(status: str, h2: float) -> None:
    state = line(status=status, h2=h2)  # 38 m of static head > the 32 m shutoff: no flow
    pr = _no_ratio(state)
    assert pr.status == ("off" if status == "off" else "no_flow")
    assert pr.npsh_available is not None
    assert pr.npsh_required is None
    assert EQUATION in pump_trace(state).equations


def test_no_vapor_pressure_gives_no_ratio() -> None:
    state = line(p_vap=None)
    pr = _no_ratio(state)
    assert pr.status == "running"
    assert pr.npsh_available is None
    assert pr.npsh_required is not None
    assert flags(state, "NPSH_NOT_CHECKED") == ["PU"]


def test_a_floating_suction_gives_no_ratio() -> None:
    state = _floating_loop()
    assert state.converged
    pr = _no_ratio(state)
    assert pr.status == "running"
    assert pr.suction_absolute_pressure is None
    assert pr.npsh_available is None
    assert pr.npsh_required is not None
    assert flags(state, "UNDETERMINED_PRESSURE")


def test_ratio_below_one_margin_below_zero_and_cavitation_are_the_same_cases() -> None:
    """Seeded cases on both sides of NPSHa = NPSHr: the three statements hold together."""
    rng = random.Random(20261112)
    below = 0
    cases = 24
    for _ in range(cases):
        scale = rng.uniform(0.5, 6.0)
        npshr = [(q, n * scale) for q, n in NPSHR]
        case: dict[str, Any] = {
            "level": rng.uniform(1.5, 4.0),
            "surface_pressure": rng.uniform(-30000.0, 0.0),
            "speed": rng.uniform(0.95, 1.0),
            "npshr": npshr,
        }
        state = line(**case)
        _, npsha, required = closed_form(**case)
        pr = state.pump_results["PU"]
        assert pr.status == "running"
        assert pr.npsh_margin_ratio == pytest.approx(npsha / required, rel=1e-9), case
        assert pr.npsh_margin_ratio is not None
        assert pr.npsh_margin is not None
        cavitates = flags(state, "CAVITATION") == ["PU"]
        assert (pr.npsh_margin_ratio < 1.0) == (pr.npsh_margin < 0.0) == cavitates, case
        below += cavitates
    assert 0 < below < cases, "both sides of NPSHa = NPSHr are drawn"


def test_the_methods_summary_states_the_ratio() -> None:
    state = line()
    section = next(s for s in state.trace.methods.sections if s.title == "Atmosphere and NPSH")
    assert "margin ratio = NPSHa / NPSHr, not given where NPSHr is 0" in " ".join(section.items)
