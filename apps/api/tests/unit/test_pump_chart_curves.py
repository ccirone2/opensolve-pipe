"""The pump chart's curves (proposal pump-chart.md §6, slice 1): PumpResult's efficiency, NPSHr
and shaft-power curves at the operating speed, and NPSHa at each system-curve point.

Expected values are derived here, independently of solver code: SciPy's PchipInterpolator
through the curve points, the affinity laws (Q ∝ s, H and NPSHr ∝ s², η at Q/s), P = ρgQH/η,
and NPSHa = (EGL_s − z_s) + (p_atm − p_vap)/(ρg) with the suction EGL from Darcy–Weisbach and
fluids' Colebrook (test_m3_solve's helpers).
"""

from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from fluids.atmosphere import ATMOSPHERE_1976
from fluids.constants import g
from scipy.interpolate import PchipInterpolator

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project, system_curve

from .helpers import connection, custom_fluid, make_project, reservoir
from .test_m3_solve import (
    EFF,
    FLOWS,
    L1,
    NPSHR,
    P_VAP,
    RHO,
    D,
    curve_head,
    pipe_head,
    pump,
    pump_curve,
)

SITE = 1200.0
LEVEL = 2.0
"""m: the suction reservoir's level, at elevation 0 (as test_m3_solve.pump_line)."""


def line(
    *, speed: float = 1.0, curve: dict[str, Any] | None = None, p_vap: float | None = P_VAP
) -> Project:
    """R1 (level 2 m) -> L1 -> PU -> L2 (200 m) -> R2 (level 20 m), all at elevation 0."""
    comps = [reservoir("R1", level=LEVEL), pump(speed=speed), reservoir("R2", level=20.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=L1),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    return make_project(
        comps,
        conns,
        pump_library=[curve or pump_curve()],
        fluid=custom_fluid(RHO, 1.0e-3, vapor_pressure=p_vap),
        site_elevation=SITE,
    )


def efficiency0(x: float) -> float:
    return float(PchipInterpolator(*zip(*EFF, strict=True))(x))


def npshr0(x: float) -> float:
    return float(PchipInterpolator(*zip(*NPSHR, strict=True))(x))


@pytest.mark.parametrize("speed", [1.0, 0.8])
def test_efficiency_npshr_and_power_curves_are_sampled_at_the_operating_speed(
    speed: float,
) -> None:
    pr = solve_project(line(speed=speed)).pump_results["PU"]
    assert pr.status == "running"

    eff = pr.efficiency_curve
    assert eff is not None
    assert len(eff) == 41
    flows = np.linspace(EFF[0][0] * speed, EFF[-1][0] * speed, 41)
    for p, q in zip(eff, flows, strict=True):
        assert p.flow == pytest.approx(q, rel=1e-15, abs=1e-18)
        assert p.efficiency == pytest.approx(efficiency0(q / speed), rel=1e-12)

    npshr = pr.npshr_curve
    assert npshr is not None
    assert len(npshr) == 41
    flows = np.linspace(NPSHR[0][0] * speed, NPSHR[-1][0] * speed, 41)
    for p, q in zip(npshr, flows, strict=True):
        assert p.flow == pytest.approx(q, rel=1e-15)
        assert p.npshr == pytest.approx(speed**2 * npshr0(q / speed), rel=1e-12)

    # Power where both the head and efficiency points reach: here both span 0 to 0.03 m³/s.
    power = pr.power_curve
    assert power is not None
    assert len(power) == 41
    flows = np.linspace(max(FLOWS[0], EFF[0][0]) * speed, min(FLOWS[-1], EFF[-1][0]) * speed, 41)
    for p, q in zip(power, flows, strict=True):
        expected = RHO * g * q * curve_head(q, speed) / efficiency0(q / speed)
        assert p.flow == pytest.approx(q, rel=1e-15, abs=1e-18)
        assert p.shaft_power == pytest.approx(expected, rel=1e-12, abs=1e-9)


def test_the_duty_lies_on_the_sampled_curves() -> None:
    """The duty's η, NPSHr and shaft power are the curves' values at the operating flow (the
    head across the pump is the curve's head to the solver's tolerance)."""
    pr = solve_project(line()).pump_results["PU"]
    q = pr.operating_flow
    assert pr.efficiency == pytest.approx(efficiency0(q), rel=1e-12)
    assert pr.npsh_required == pytest.approx(npshr0(q), rel=1e-12)
    assert pr.shaft_power == pytest.approx(RHO * g * q * curve_head(q, 1.0) / efficiency0(q), 1e-6)
    for name, attr in (
        ("efficiency_curve", "efficiency"),
        ("npshr_curve", "npshr"),
        ("power_curve", "shaft_power"),
    ):
        samples = getattr(pr, name)
        xs = [p.flow for p in samples]
        ys = [getattr(p, attr) for p in samples]
        duty = {"efficiency": pr.efficiency, "npshr": pr.npsh_required}.get(attr, pr.shaft_power)
        # Between its neighbouring samples: a smooth curve, 41 samples over its range.
        assert float(np.interp(q, xs, ys)) == pytest.approx(duty, rel=2e-3)


def test_curves_are_null_without_their_data_or_an_overlap() -> None:
    bare = {k: v for k, v in pump_curve().items() if k not in ("npshrCurve", "efficiencyCurve")}
    pr = solve_project(line(curve=bare)).pump_results["PU"]
    assert pr.efficiency_curve is None
    assert pr.npshr_curve is None
    assert pr.power_curve is None
    assert len(pr.curve) == 41

    # Efficiency points beyond the head points: no flow has both, so no power curve.
    beyond = [{"flow": 0.04, "efficiency": 0.6}, {"flow": 0.05, "efficiency": 0.5}]
    apart = {**pump_curve(), "efficiencyCurve": beyond}
    pr = solve_project(line(curve=apart)).pump_results["PU"]
    assert pr.efficiency_curve is not None
    assert pr.power_curve is None


def test_an_off_pump_has_its_curves_at_its_set_speed() -> None:
    project = line(speed=0.9)
    project.components[1].status = "off"  # type: ignore[union-attr]
    pr = solve_project(project).pump_results["PU"]
    assert pr.status == "off"
    assert pr.efficiency_curve is not None
    assert pr.efficiency_curve[-1].flow == pytest.approx(EFF[-1][0] * 0.9, rel=1e-15)


def npsha(q: float) -> float:
    """NPSHa at the suction for flow q through L1 from R1 (no entrance fitting)."""
    p_atm = float(ATMOSPHERE_1976(SITE).P)
    return (LEVEL - pipe_head(q, L1, D)) + (p_atm - P_VAP) / (RHO * g)


def test_each_system_curve_point_with_a_head_has_its_npsha() -> None:
    curve = system_curve(line(), "PU", flow_min=0.004, flow_max=0.036, num_points=9)
    assert all(p.head is not None for p in curve.points)
    for p in curve.points:
        assert p.npsh_available == pytest.approx(npsha(p.flow), rel=1e-9)


def test_npsha_at_the_duty_flow_is_the_solves() -> None:
    project = line()
    pr = solve_project(project).pump_results["PU"]
    q = pr.operating_flow
    curve = system_curve(project, "PU", flow_min=0.5 * q, flow_max=1.5 * q, num_points=3)
    mid = curve.points[1]
    assert mid.flow == pytest.approx(q, rel=1e-15)
    assert pr.npsh_available is not None
    assert mid.npsh_available == pytest.approx(pr.npsh_available, abs=1e-6)


def test_npsha_is_null_without_a_vapor_pressure() -> None:
    curve = system_curve(line(p_vap=None), "PU", num_points=5)
    assert any(p.head is not None for p in curve.points)
    assert all(p.npsh_available is None for p in curve.points)


def test_the_endpoint_returns_npsha_and_the_solve_the_curves() -> None:
    client = TestClient(app, client=("198.51.100.240", 50000))
    project = line().model_dump(mode="json", by_alias=True, exclude_none=True)
    body = client.post(
        "/api/v1/system-curve", json={"project": project, "pumpId": "PU", "numPoints": 5}
    ).json()
    points = body["points"]
    assert [p["npshAvailable"] is not None for p in points] == [
        p["head"] is not None for p in points
    ]
    for p in points:
        if p["npshAvailable"] is not None:
            assert p["npshAvailable"] == pytest.approx(npsha(p["flow"]), rel=1e-9)
    solved = client.post("/api/v1/solve", json={"project": project}).json()["solvedState"]
    pr = solved["pumpResults"]["PU"]
    assert len(pr["efficiencyCurve"]) == len(pr["npshrCurve"]) == len(pr["powerCurve"]) == 41
    assert set(pr["powerCurve"][0]) == {"flow", "shaftPower"}
