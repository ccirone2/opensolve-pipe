"""The pump chart's curve facts (proposal pump-chart.md §6, slice 2): the best efficiency point,
the shutoff head, the flows where the head rises, and a speed-controlled pump's curves at its
speed limits and its iso-efficiency lines.

Expected values are derived here, independently of solver code: SciPy's PchipInterpolator
through the curve points, its derivative's roots, brentq, and the affinity laws (Q ∝ s,
H ∝ s², η at Q/s).
"""

from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project

from .helpers import connection, custom_fluid, make_project, reservoir
from .test_m3_solve import EFF, FLOWS, HEADS, P_VAP, RHO, pump, pump_curve


def line(
    *, speed: float = 1.0, curve: dict[str, Any] | None = None, control: Any = None
) -> Project:
    """R1 (level 2 m) -> L1 (10 m) -> PU -> L2 (200 m) -> R2 (level 20 m)."""
    p = pump(speed=speed)
    if control is not None:
        p["control"] = control
    comps = [reservoir("R1", level=2.0), p, reservoir("R2", level=20.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    return make_project(
        comps,
        conns,
        pump_library=[curve or pump_curve()],
        fluid=custom_fluid(RHO, 1.0e-3, vapor_pressure=P_VAP),
        site_elevation=1200.0,
    )


def curve_with(**fields: Any) -> dict[str, Any]:
    return {**pump_curve(), **fields}


def points(xs: list[float], ys: list[float], key: str) -> list[dict[str, float]]:
    return [{"flow": x, key: y} for x, y in zip(xs, ys, strict=True)]


def best_of(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """The interpolant's largest value inside (xs[0], xs[-1]): derivative roots and knots."""
    p = PchipInterpolator(xs, ys)
    candidates = [float(r) for r in p.derivative().roots() if xs[0] < r < xs[-1]]
    candidates += list(xs[1:-1])
    x = max(candidates, key=lambda c: float(p(c)))
    return x, float(p(x))


@pytest.mark.parametrize("speed", [1.0, 0.8])
def test_the_best_efficiency_point_is_the_largest_efficiency_inside_the_points(
    speed: float,
) -> None:
    effs = [0.3, 0.68, 0.74, 0.62]
    xs = [0.002, 0.012, 0.022, 0.03]
    curve = curve_with(efficiencyCurve=points(xs, effs, "efficiency"))
    pr = solve_project(line(speed=speed, curve=curve)).pump_results["PU"]
    x, eta = best_of(xs, effs)
    bep = pr.best_efficiency_point
    assert bep is not None
    assert bep.flow == pytest.approx(speed * x, rel=1e-12)
    assert bep.efficiency == pytest.approx(eta, rel=1e-12)
    h0 = float(PchipInterpolator(FLOWS, HEADS)(x))
    assert bep.head == pytest.approx(speed**2 * h0, rel=1e-12)
    assert not bep.head_extrapolated
    # A dense scan finds no larger efficiency inside the points.
    grid = np.linspace(xs[0], xs[-1], 20001)
    assert float(np.max(PchipInterpolator(xs, effs)(grid))) <= eta + 1e-12


def test_no_best_efficiency_point_when_the_largest_efficiency_is_at_an_end() -> None:
    rising = curve_with(efficiencyCurve=points([0.0, 0.015, 0.03], [0.2, 0.5, 0.7], "efficiency"))
    assert solve_project(line(curve=rising)).pump_results["PU"].best_efficiency_point is None
    bare = {k: v for k, v in pump_curve().items() if k != "efficiencyCurve"}
    assert solve_project(line(curve=bare)).pump_results["PU"].best_efficiency_point is None
    # EFF peaks at its middle point (0.02 m³/s, 75 %): a knot is a candidate too.
    bep = solve_project(line()).pump_results["PU"].best_efficiency_point
    assert bep is not None
    assert (bep.flow, bep.efficiency) == (0.02, 0.75)
    assert EFF[1] == (0.02, 0.75)


def test_the_shutoff_head_is_the_curve_at_zero_flow() -> None:
    pr = solve_project(line(speed=0.9)).pump_results["PU"]
    assert pr.shutoff_head.head == pytest.approx(0.81 * HEADS[0], rel=1e-14)
    assert pr.shutoff_head.extrapolated is False
    # Points from 0.005 m³/s: the start tangent reaches zero flow.
    xs, hs = [0.005, 0.015, 0.025, 0.03], [31.0, 28.0, 20.0, 15.0]
    p = PchipInterpolator(xs, hs)
    expected = hs[0] - float(p.derivative()(xs[0])) * xs[0]
    pr = solve_project(line(curve=curve_with(points=points(xs, hs, "head")))).pump_results["PU"]
    assert pr.shutoff_head.head == pytest.approx(expected, rel=1e-12)
    assert pr.shutoff_head.extrapolated is True


def test_rising_head_ranges_are_where_the_curve_climbs() -> None:
    assert solve_project(line()).pump_results["PU"].rising_head_ranges == []
    # A drooping curve: up from 30 m at shutoff to 31 m, then down.
    hs = [30.0, 31.0, 26.0, 16.0]
    pr = solve_project(line(speed=0.9, curve=curve_with(points=points(FLOWS, hs, "head"))))
    ranges = pr.pump_results["PU"].rising_head_ranges
    p = PchipInterpolator(FLOWS, hs)
    grid = np.linspace(FLOWS[0], FLOWS[-1], 30001)
    rising = grid[p.derivative()(grid) > 0]
    assert len(ranges) == 1
    assert ranges[0].flow_min == pytest.approx(0.9 * rising[0], abs=1e-6)
    assert ranges[0].flow_max == pytest.approx(0.9 * rising[-1], abs=2e-6)


CONTROL = {"mode": "flow", "setpoint": 0.015, "minSpeed": 0.5}


def test_a_speed_controlled_pump_has_its_limit_curves_and_iso_efficiency_lines() -> None:
    pr = solve_project(line(control=CONTROL)).pump_results["PU"]
    h0 = PchipInterpolator(FLOWS, HEADS)
    assert [(c.limit, c.speed) for c in pr.speed_curves] == [("min", 0.5), ("max", 1.0)]
    for c in pr.speed_curves:
        flows = np.linspace(FLOWS[0] * c.speed, FLOWS[-1] * c.speed, 41)
        assert [p.flow for p in c.curve] == pytest.approx(list(flows), rel=1e-14, abs=1e-18)
        for p in c.curve:
            assert p.head == pytest.approx(c.speed**2 * float(h0(p.flow / c.speed)), rel=1e-12)

    lines = pr.iso_efficiency_lines
    eta0 = PchipInterpolator(*zip(*EFF, strict=True))
    best = [x for x in lines if x.best]
    assert len(best) == 1
    assert (best[0].rated_flow, best[0].efficiency) == (0.02, 0.75)
    speeds = np.linspace(0.5, 1.0, 11)
    # Levels below 75 %: 70, 65 and 60 %. Each on the rising side of EFF (0 to 0.02); 70 % also
    # at the last point (0.03 m³/s, exactly 70 %).
    expected: list[tuple[float, float]] = []
    for level in (0.70, 0.65, 0.60):
        crossing = brentq(lambda x, lv=level: float(eta0(x)) - lv, 0.0, 0.02, xtol=1e-15)
        expected.append((level, crossing))
    expected.append((0.70, 0.03))
    got = sorted((x.efficiency, x.rated_flow) for x in lines if not x.best)
    assert len(got) == len(expected)
    for (level, flow), (want_level, want_flow) in zip(got, sorted(expected), strict=True):
        assert level == pytest.approx(want_level, abs=1e-12)
        assert flow == pytest.approx(want_flow, rel=1e-9)
    for iso in lines:
        assert float(eta0(iso.rated_flow)) == pytest.approx(iso.efficiency, abs=1e-12)
        h = float(h0(iso.rated_flow))
        assert [p.flow for p in iso.points] == pytest.approx(
            [s * iso.rated_flow for s in speeds], rel=1e-14
        )
        assert [p.head for p in iso.points] == pytest.approx([s * s * h for s in speeds], rel=1e-12)


def test_a_fixed_speed_pump_has_no_speed_range() -> None:
    pr = solve_project(line(speed=0.9)).pump_results["PU"]
    assert pr.speed_curves == []
    assert pr.iso_efficiency_lines == []


def test_the_solve_and_its_trace_report_the_facts() -> None:
    client = TestClient(app, client=("198.51.100.241", 50000))
    project = line(control=CONTROL).model_dump(mode="json", by_alias=True, exclude_none=True)
    solved = client.post("/api/v1/solve", json={"project": project}).json()["solvedState"]
    pr = solved["pumpResults"]["PU"]
    assert set(pr["bestEfficiencyPoint"]) == {"flow", "efficiency", "head", "headExtrapolated"}
    assert set(pr["shutoffHead"]) == {"head", "extrapolated"}
    assert pr["risingHeadRanges"] == []
    assert [c["limit"] for c in pr["speedCurves"]] == ["min", "max"]
    assert set(pr["isoEfficiencyLines"][0]) == {"efficiency", "best", "ratedFlow", "points"}
    trace = solved["trace"]["elements"]["PU"]
    names = [v["name"] for v in trace["intermediates"]]
    assert "Best efficiency flow s Q₀*" in names
    assert any(e.startswith("Best efficiency point:") for e in trace["equations"])
    assert any(e.startswith("Iso-efficiency line") for e in trace["equations"])


def random_curve(rng: np.random.Generator) -> dict[str, Any]:
    """A random pump curve: 4-8 head points (some drooping) and 3-7 efficiency points."""
    n = int(rng.integers(4, 9))
    xs = np.sort(rng.uniform(0.0, 0.05, n))
    xs[0] = 0.0 if rng.random() < 0.6 else xs[0]
    xs = np.unique(np.round(xs, 6))
    heads = np.sort(rng.uniform(5.0, 60.0, len(xs)))[::-1].copy()
    if rng.random() < 0.4 and len(heads) > 2:  # a hump: the second point above the first
        heads[1] = heads[0] + rng.uniform(0.1, 5.0)
    m = int(rng.integers(3, 8))
    ex = np.unique(np.round(np.sort(rng.uniform(0.0, 0.05, m)), 6))
    eff = rng.uniform(0.2, 0.85, len(ex))
    return {
        "id": "C1",
        "name": "random",
        "points": points(list(map(float, xs)), list(map(float, heads)), "head"),
        "efficiencyCurve": points(list(map(float, ex)), list(map(float, eff)), "efficiency"),
    }


def test_curve_facts_agree_with_a_dense_scan_on_random_curves() -> None:
    """Property check against an independent dense scan of SciPy's PCHIP (300 seeded curves)."""
    from opensolve_pipe.models.pumps import PumpCurve
    from opensolve_pipe.services.solver import curve_facts
    from opensolve_pipe.services.solver.pumps import PumpCurveModel

    rng = np.random.default_rng(20261026)
    checked_bep = checked_rising = checked_iso = 0
    for _ in range(300):
        raw = random_curve(rng)
        model = PumpCurveModel(PumpCurve.model_validate(raw))
        ex = [p["flow"] for p in raw["efficiencyCurve"]]
        ey = [p["efficiency"] for p in raw["efficiencyCurve"]]
        eta = PchipInterpolator(ex, ey)
        grid = np.linspace(ex[0], ex[-1], 200001)
        values = eta(grid)
        i = int(np.argmax(values))
        bep = curve_facts.best_efficiency(model)
        interior = values[i] > max(ey[0], ey[-1]) + 1e-9
        if bep is None:
            assert not interior
        else:
            checked_bep += 1
            assert bep.efficiency == pytest.approx(values[i], abs=1e-9)
            assert bep.efficiency >= values.max() - 1e-12
            assert float(eta(bep.flow)) == pytest.approx(bep.efficiency, abs=1e-12)
            # Iso-efficiency crossings sit on their level.
            for line in curve_facts.iso_lines(model, 0.5, 1.0):
                checked_iso += 1
                assert float(eta(line.rated_flow)) == pytest.approx(line.efficiency, abs=1e-9)
        hx = [p["flow"] for p in raw["points"]]
        hy = [p["head"] for p in raw["points"]]
        head = PchipInterpolator(hx, hy)
        hgrid = np.linspace(hx[0], hx[-1], 200001)
        slope = head.derivative()(hgrid)
        ranges = curve_facts.rising_ranges(model, 1.0)
        inside = np.zeros_like(hgrid, dtype=bool)
        for lo, hi in ranges:
            checked_rising += 1
            inside |= (hgrid > lo + 1e-9) & (hgrid < hi - 1e-9)
            assert hi > lo
        # Inside a reported range the head rises; well outside every range it does not.
        assert np.all(slope[inside] > 0)
        margin = np.ones_like(hgrid, dtype=bool)
        for lo, hi in ranges:
            margin &= (hgrid < lo - 1e-6) | (hgrid > hi + 1e-6)
        assert np.all(slope[margin] <= 1e-6)
    assert checked_bep > 50
    assert checked_rising > 20
    assert checked_iso > 50
