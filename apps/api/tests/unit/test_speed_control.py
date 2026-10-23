"""Speed-controlled pumps with a flow setpoint (CLAUDE.md D11, docs/proposals/vfd-pump-modes.md
§4, §7.3): the speed-uniqueness test, the speed root, the law override, the fallbacks, the
results mapping and the metamorphic tests M1 and M2.

Expected values are derived here independently of the solver: closed forms for a linear curve
(H₀ = a − b x gives s* = [b Q + √(b² Q² + 4 a H)]/(2 a), ORNL eq. 10 with c = 0), ψ sampled
with a fresh ``scipy.interpolate.PchipInterpolator``, and re-solves of the same network with
the control removed (M1, M2). Every curve point, level and setpoint is a test input.
"""

import math
from itertools import pairwise
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.interpolate import PchipInterpolator

from opensolve_pipe.main import app
from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network, validate_topology
from opensolve_pipe.services.solver.errors import TopologyError
from opensolve_pipe.services.solver.gga import GgaResult, solve_gga
from opensolve_pipe.services.solver.network import NORMAL, LinkMode, LinkState
from opensolve_pipe.services.solver.pumps import (
    PumpCurveModel,
    operating_speed,
    speed_uniqueness,
)
from opensolve_pipe.services.solver.status import (
    HTOL,
    QTOL,
    Status,
    _check_changes,
    _open_bad_valves,
    _vector,
    _warm_start,
    closed_off_sections,
    initial_controls,
    link_states,
    run_outer_loop,
)
from opensolve_pipe.services.solver.system_curve import system_curve_points

from .helpers import connection, custom_fluid, make_project, plug, reservoir, tee

NO_CURVES = SolveOptions(include_system_curve=False)
D6_REL = 0.005
"""CLAUDE.md D6: 0.5 % relative (speed: 0.5 % relative, its implied head within 0.01 m)."""

CURVE_A = [(0.0, 45.0), (0.01, 44.0), (0.02, 41.0), (0.03, 35.5), (0.04, 27.0)]
"""A centrifugal curve: 45 m shutoff, falling to 27 m at 0.04 m³/s (test input)."""
EFFICIENCY_A = [(0.0, 0.2), (0.02, 0.7), (0.04, 0.6)]
NPSHR_A = [(0.005, 1.6), (0.025, 2.7), (0.045, 5.2)]
LINEAR_A, LINEAR_B = 40.0, 500.0
"""H₀ = a − b x, m and s/m² (test inputs): exactly linear through collinear points."""


def curve_dict(
    points: list[tuple[float, float]],
    cid: str = "C1",
    efficiency: list[tuple[float, float]] | None = None,
    npshr: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    curve: dict[str, Any] = {
        "id": cid,
        "name": f"curve {cid}",
        "points": [{"flow": q, "head": h} for q, h in points],
    }
    if efficiency is not None:
        curve["efficiencyCurve"] = [{"flow": q, "efficiency": e} for q, e in efficiency]
    if npshr is not None:
        curve["npshrCurve"] = [{"flow": q, "npshr": n} for q, n in npshr]
    return curve


def linear_points() -> list[tuple[float, float]]:
    return [(x, LINEAR_A - LINEAR_B * x) for x in (0.0, 0.02, 0.04, 0.06)]


def pump(
    cid: str,
    control: dict[str, Any] | None = None,
    *,
    speed: float = 1.0,
    status: str = "on",
    curve: str = "C1",
) -> dict[str, Any]:
    comp: dict[str, Any] = {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "curveId": curve,
        "speed": speed,
        "status": status,
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    if control is not None:
        comp["control"] = control
    return comp


def flow_control(setpoint: float, min_speed: float = 0.4) -> dict[str, Any]:
    return {"mode": "flow", "setpoint": setpoint, "minSpeed": min_speed}


def valve(cid: str, vtype: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kw,
    }


def pump_line(
    h1: float,
    h2: float,
    control: dict[str, Any] | None,
    *,
    speed: float = 1.0,
    status: str = "on",
    points: list[tuple[float, float]] | None = None,
    efficiency: list[tuple[float, float]] | None = None,
    npshr: list[tuple[float, float]] | None = None,
    vapor_pressure: float | None = None,
) -> Project:
    """R1 (level h1) -> L1 (10 m) -> PU -> L2 (200 m) -> R2 (level h2), 0.1 m pipes."""
    comps = [
        reservoir("R1", level=h1),
        pump("PU", control, speed=speed, status=status),
        reservoir("R2", level=h2),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    curve = curve_dict(points or CURVE_A, efficiency=efficiency, npshr=npshr)
    fluid = custom_fluid(vapor_pressure=vapor_pressure)
    return make_project(comps, conns, pump_library=[curve], fluid=fluid)


def build(project: Project) -> BuiltNetwork:
    return build_network(project, fluid_properties(project.fluid))


def without_control(project: Project, speed: float) -> Project:
    """The same project with PU's control removed and its speed set (M1, M2)."""
    data = project.model_dump(mode="json", by_alias=True, exclude_none=True)
    for comp in data["components"]:
        if comp["id"] == "PU":
            comp.pop("control", None)
            comp["speed"] = speed
    return Project.model_validate(data)


def failed_result(built: BuiltNetwork, **fields: Any) -> GgaResult:
    """A failed inner solve (a stub for the fallback tests)."""
    n, m = len(built.network.nodes), len(built.network.links)
    return GgaResult(
        heads=np.full(n, np.nan),
        flows=np.zeros(m),
        iterations=0,
        converged=False,
        max_continuity=0.0,
        max_continuity_node=None,
        max_energy=0.0,
        max_energy_link=None,
        message="failed (test stub)",
        **fields,
    )


# --------------------------------------------------------------------------- uniqueness test


def independent_psi(points: list[tuple[float, float]]) -> Any:
    """ψ(x) = 2 H₀ − x H₀' from a fresh PchipInterpolator with the tangent extensions."""
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    pchip = PchipInterpolator(xs, ys)
    m0, m1 = float(pchip(xs[0], 1)), float(pchip(xs[-1], 1))

    def psi(x: float) -> float:
        if x < xs[0]:
            h, dh = ys[0] + m0 * (x - xs[0]), m0
        elif x > xs[-1]:
            h, dh = ys[-1] + m1 * (x - xs[-1]), m1
        else:
            h, dh = float(pchip(x)), float(pchip(x, 1))
        return float(2.0 * h - x * dh)

    return psi


def random_curve(rng: np.random.Generator) -> list[tuple[float, float]]:
    n = int(rng.integers(3, 9))
    start = 0.0 if rng.random() < 0.5 else float(rng.uniform(0.0, 0.01))
    flows = start + np.cumsum(rng.uniform(0.002, 0.02, n)) - 0.002
    head = float(rng.uniform(5.0, 60.0))
    heads = []
    for _ in range(n):
        heads.append(head)
        head = max(head + float(rng.uniform(-0.5, 0.35)) * head + float(rng.uniform(-3, 3)), 0.0)
    return [(float(q), float(h)) for q, h in zip(flows, heads, strict=True)]


def curve_model(points: list[tuple[float, float]]) -> PumpCurveModel:
    return PumpCurveModel(PumpCurve.model_validate(curve_dict(points)))


@pytest.mark.parametrize("seed", range(40))
def test_uniqueness_test_agrees_with_dense_sampling(seed: int) -> None:
    """§4.3: the exact ψ test (cubic pieces, linear start tangent) against ψ sampled densely on
    [0, x_last] from an independent interpolant: its least value is no larger than any sample
    and within the sampling bound of the least sample; the flows it reports span every clearly
    negative sample, and ψ is not clearly positive at their ends."""
    rng = np.random.default_rng(seed)
    points = random_curve(rng)
    check = speed_uniqueness(curve_model(points))
    psi = independent_psi(points)
    x_last = points[-1][0]
    xs = np.unique(np.concatenate([np.linspace(0.0, x_last, 20001), [p[0] for p in points]]))
    values = np.array([psi(float(x)) for x in xs])
    lipschitz = float(np.max(np.abs(np.diff(values) / np.diff(xs))))
    bound = lipschitz * float(np.max(np.diff(xs))) + 1.0e-9 * max(1.0, float(np.max(values)))
    assert check.psi_min <= float(np.min(values)) + 1.0e-9
    assert check.psi_min >= float(np.min(values)) - bound
    assert check.psi_min == pytest.approx(psi(check.psi_min_flow), abs=1.0e-9)
    negative = xs[values < -bound]
    if check.interval is None:
        assert negative.size == 0
        assert check.psi_min > 0.0
    else:
        low, high = check.interval
        assert check.psi_min <= 0.0
        assert np.all((negative >= low - 1.0e-12) & (negative <= high + 1.0e-12))
        assert psi(low) <= bound
        assert psi(high) <= bound


def test_sampled_curves_cover_both_outcomes() -> None:
    """A guard on the random inputs above: they include curves that pass and that fail."""
    outcomes = {
        speed_uniqueness(curve_model(random_curve(np.random.default_rng(s)))).interval is None
        for s in range(40)
    }
    assert outcomes == {True, False}


@pytest.mark.parametrize("seed", range(40))
def test_x_mono_is_twice_the_end_tangents_zero_head_flow(seed: int) -> None:
    """§4.3: beyond the last point ψ = ψ(x_e) + m (x − x_e) falls to 0 at x_mono = 2 x₀, x₀ the
    end tangent's zero-head flow, when m < 0; it never does when m >= 0. Checked on a grid."""
    points = random_curve(np.random.default_rng(seed))
    check = speed_uniqueness(curve_model(points))
    if check.interval is not None:
        return  # rejected curves: x_mono is not used
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    x_e, h_e = float(xs[-1]), float(ys[-1])
    m = float(PchipInterpolator(xs, ys)(x_e, 1))
    psi = independent_psi(points)
    if m >= 0.0:
        assert math.isinf(check.x_mono)
        assert all(psi(x) > 0.0 for x in np.linspace(x_e, 100 * x_e, 50))
        return
    x0 = x_e + h_e / -m
    assert check.x_mono == pytest.approx(2.0 * x0, rel=1.0e-12)
    grid = np.linspace(x_e, 4.0 * x0, 400)
    assert all(psi(x) > 0.0 for x in grid if x < check.x_mono * (1 - 1e-9))
    assert all(psi(x) < 0.0 for x in grid if x > check.x_mono * (1 + 1e-9))


def test_curve_a_numbers_of_the_proposal() -> None:
    """§4.3's check on the suite's curve_a: x₀ = 0.067, x_mono = 0.134 m³/s, least ψ on the
    points 89.5 m; Q_set = 0.0335 m³/s with s_min = 0.4 is beyond run-out at s_min
    (F_min = −2.68 m), and H = 30 m has the unique speed 0.96817."""
    model = curve_model(CURVE_A)
    check = speed_uniqueness(model)
    assert check.interval is None
    assert check.x_mono == pytest.approx(0.134, rel=1e-12)
    assert check.psi_min == pytest.approx(89.5, rel=1e-12)
    assert model.head(0.0335, 0.4)[0] == pytest.approx(-2.68, rel=1e-12)
    found = operating_speed(model, 0.0335, 30.0, 0.4, 1.0, check.x_mono)
    assert found.lower == 0.4
    assert found.speed == pytest.approx(0.96817, abs=5e-6)
    assert abs(found.residual) < 1e-12


@pytest.mark.parametrize(
    ("points", "unique"),
    [
        ([(0.0, 40.0), (0.01, 42.0), (0.02, 41.0), (0.03, 35.0)], True),  # drooping, ψ > 0
        ([(0.0, 0.5), (0.01, 0.6), (0.02, 30.0), (0.03, 25.0)], False),  # steep rise: ψ < 0
        ([(0.0, 0.0), (0.01, 20.0), (0.02, 15.0)], False),  # H₀(0) = 0: ψ(0) = 0
        ([(0.01, 1.0), (0.02, 20.0), (0.03, 15.0)], False),  # start tangent: H₀(0) < 0
    ],
)
def test_controlled_pump_curve_topology_issue(
    points: list[tuple[float, float]], unique: bool
) -> None:
    """§3.4: a speed-controlled pump whose curve fails the ψ test is a topology issue naming
    the pump, the curve and the flow interval; a drooping curve with ψ > 0 is accepted; a
    fixed-speed pump on the same curve is not concerned."""
    controlled = pump_line(2.0, 20.0, flow_control(0.02), points=points)
    issues = [i for i in validate_topology(controlled) if i.code == "CONTROLLED_PUMP_CURVE"]
    check = speed_uniqueness(curve_model(points))
    if unique:
        assert not issues
        assert check.interval is None
    else:
        [found] = issues
        assert check.interval is not None
        low, high = check.interval
        assert found.component_ids == ["PU"]
        assert "pump 'PU'" in found.message
        assert "curve 'C1'" in found.message
        assert f"from {low:.6g} to {high:.6g} m³/s" in found.message
        # ψ ≤ 0 needs x H₀' ≥ 2 H₀ ≥ 0 (heads are ≥ 0): the head rises steeply with flow there.
        assert "head rises less steeply with flow there" in found.message
        assert "falls" not in found.message
    fixed = pump_line(2.0, 20.0, None, points=points)
    assert not [i for i in validate_topology(fixed) if i.code == "CONTROLLED_PUMP_CURVE"]


# --------------------------------------------------------------------------- the setpoint bound


def end_tangent_x_mono(points: list[tuple[float, float]]) -> float:
    """x_mono from a fresh PchipInterpolator's end tangent (§4.3): beyond the last point
    ψ = 2 h_e + m (x − 2 x_e), zero at 2 (x_e + h_e/|m|), twice the tangent's zero-head flow,
    when m < 0; ψ never reaches 0 there when m >= 0."""
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    x_e, h_e = float(xs[-1]), float(ys[-1])
    m = float(PchipInterpolator(xs, ys)(x_e, 1))
    return 2.0 * (x_e + h_e / -m) if m < 0.0 else math.inf


def setpoint_message(q_set: float, speed: float, x_mono: float) -> str:
    """CONTROLLED_PUMP_SETPOINT in the owner's words (decision of 2026-10-23), for pump PU on
    curve C1 ('curve C1'), with the expected values."""
    return (
        f"pump 'PU' is speed-controlled to hold {q_set:.6g} m³/s, but no speed up to its "
        f"maximum speed {speed:.6g} can hold it on its curve 'C1' (curve C1): at that flow the "
        "head s² H₀(Q/s) falls as the speed s rises, at every speed, because Q/s lies beyond "
        f"x_mono = {x_mono:.6g} m³/s, twice the flow at which the curve's end tangent reaches "
        f"zero head; setpoints must be below {speed * x_mono:.6g} m³/s (the maximum speed × "
        "x_mono), so use a smaller setpoint or a curve that extends to higher flows"
    )


@pytest.mark.parametrize("shape", ["linear", "pchip"])
@pytest.mark.parametrize("speed", [1.0, 0.8])
@pytest.mark.parametrize("margin", [-1.0e-6, -1.0e-9, 1.0e-9, 1.0e-6])
def test_setpoint_beyond_the_curve_at_maximum_speed_is_a_topology_issue(
    shape: str, speed: float, margin: float
) -> None:
    """Owner's decision (2026-10-23, TSD §12): Q_set >= s_max x_mono puts Q_set/s beyond x_mono
    at every s <= s_max, where F(s, Q_set) = s² H₀(Q_set/s) falls as s rises, so no speed in
    the drive's range controls it: a topology issue naming the pump. Just below the bound the
    pump is built and F(·, Q_set) rises on [s_lo, s_max] with s_lo < s_max. x_mono: 2a/b for
    H₀ = a − b x (ψ = 2a − b x), and from the end tangent of a fresh PCHIP for curve_a."""
    points = linear_points() if shape == "linear" else CURVE_A
    x_mono = 2.0 * LINEAR_A / LINEAR_B if shape == "linear" else end_tangent_x_mono(points)
    q_set = speed * x_mono * (1.0 + margin)
    project = pump_line(2.0, 20.0, flow_control(q_set, 0.3), speed=speed, points=points)
    issues = [i for i in validate_topology(project) if i.code == "CONTROLLED_PUMP_SETPOINT"]
    if margin < 0.0:
        assert not issues
        control = build(project).pumps["PU"].control
        assert control is not None
        assert control.uniqueness.x_mono == pytest.approx(x_mono, rel=1e-12)
        assert control.low_speed == pytest.approx(q_set / x_mono, rel=1e-12)
        assert control.low_speed < control.max_speed == speed
    else:
        [found] = issues
        assert found.component_ids == ["PU"]
        assert found.connection_ids == []
        assert found.message == setpoint_message(q_set, speed, x_mono)
        with pytest.raises(TopologyError) as raised:
            build(project)
        assert [i.code for i in raised.value.issues] == ["CONTROLLED_PUMP_SETPOINT"]
    # a fixed-speed pump on the same curve has no setpoint to hold
    fixed = pump_line(2.0, 20.0, None, speed=speed, points=points)
    assert not [i for i in validate_topology(fixed) if i.code == "CONTROLLED_PUMP_SETPOINT"]


def test_every_accepted_setpoint_leaves_a_bracket_below_the_maximum_speed() -> None:
    """Rounding: a setpoint one ulp below s_max x_mono can still give Q_set/x_mono >= s_max in
    floating point, which would put s_lo = max(s_min, Q_set/x_mono) at s_max (no band for the
    active state). Such a setpoint is rejected too, so every accepted one builds with
    s_lo < s_max. The inputs are made from the curve's x_mono as the solver computes it, since
    the case lies within an ulp of it; the test asserts the invariant, not a value."""
    x_mono = speed_uniqueness(curve_model(linear_points())).x_mono
    below = [
        (float(speed), math.nextafter(float(speed) * x_mono, 0.0))
        for speed in np.round(np.linspace(0.3, 1.0, 2001), 6)
    ]
    rounding = [(s, q) for s, q in below if q / x_mono >= s]
    plain = [(s, q) for s, q in below if q / x_mono < s]
    assert rounding  # the rounding case is among the inputs
    for speed, q_set in rounding[:8] + plain[:8]:
        project = pump_line(
            2.0, 20.0, flow_control(q_set, 0.2), speed=speed, points=linear_points()
        )
        issues = [i.code for i in validate_topology(project)]
        if (speed, q_set) in rounding:
            assert issues == ["CONTROLLED_PUMP_SETPOINT"]
            continue
        assert not issues
        control = build(project).pumps["PU"].control
        assert control is not None
        assert control.low_speed < control.max_speed, (speed, q_set)


def test_a_rising_end_tangent_never_bounds_the_setpoint() -> None:
    """A curve whose end tangent does not fall keeps ψ > 0 beyond its last point (x_mono = ∞):
    no setpoint is beyond it, however large (here 100 m³/s, the model's largest)."""
    points = [(0.0, 40.0), (0.01, 42.0), (0.02, 45.0)]  # rising, ψ = 2 H₀ − x H₀' > 0 on it
    assert math.isinf(end_tangent_x_mono(points))
    project = pump_line(2.0, 20.0, flow_control(100.0, 0.3), points=points)
    assert not validate_topology(project)
    control = build(project).pumps["PU"].control
    assert control is not None
    assert math.isinf(control.uniqueness.x_mono)


def test_a_curve_that_fails_the_uniqueness_test_gets_no_setpoint_issue() -> None:
    """The setpoint bound is tested only on curves that pass the ψ test (CONTROLLED_PUMP_CURVE
    comes first): a failing curve with a setpoint far beyond its end tangent has that issue
    alone."""
    points = [(0.0, 0.5), (0.01, 0.6), (0.02, 30.0), (0.03, 25.0)]  # ψ < 0 on the steep rise
    assert end_tangent_x_mono(points) < 10.0
    project = pump_line(2.0, 20.0, flow_control(10.0, 0.3), points=points)
    assert [i.code for i in validate_topology(project)] == ["CONTROLLED_PUMP_CURVE"]


def test_setpoint_issue_is_listed_with_every_other_issue() -> None:
    """The API's 422 lists every topology issue together (design §1.2): the setpoint bound of PU
    (curve C1), the uniqueness test of PB (curve C2), an unknown curve and an unconnected port."""
    q_set = 1.25 * 2.0 * LINEAR_A / LINEAR_B
    steep = [(0.0, 0.5), (0.01, 0.6), (0.02, 30.0), (0.03, 25.0)]
    comps = [
        reservoir("R1", level=2.0),
        pump("PU", flow_control(q_set, 0.3)),
        pump("PB", flow_control(0.01, 0.3), curve="C2"),
        pump("PC", curve="NONE"),
        reservoir("R2", level=20.0),
        plug("X"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("PB", "suction"), length=10.0),
        connection("L3", ("PB", "discharge"), ("PC", "suction"), length=10.0),
        connection("L4", ("PC", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    library = [curve_dict(linear_points()), curve_dict(steep, "C2")]
    project = make_project(comps, conns, pump_library=library)
    body = project.model_dump(mode="json", by_alias=True, exclude_none=True)
    response = TestClient(app).post("/api/v1/solve", json={"project": body})
    assert response.status_code == 422
    found = response.json()
    assert found["error"] == "TOPOLOGY_ERROR"
    codes = sorted(i["code"] for i in found["issues"])
    assert codes == [
        "CONTROLLED_PUMP_CURVE",
        "CONTROLLED_PUMP_SETPOINT",
        "UNCONNECTED_PORT",
        "UNKNOWN_PUMP_CURVE",
    ]
    [setpoint] = [i for i in found["issues"] if i["code"] == "CONTROLLED_PUMP_SETPOINT"]
    assert setpoint["componentIds"] == ["PU"]
    assert setpoint["message"] == setpoint_message(q_set, 1.0, 2.0 * LINEAR_A / LINEAR_B)
    [curve] = [i for i in found["issues"] if i["code"] == "CONTROLLED_PUMP_CURVE"]
    assert curve["componentIds"] == ["PB"]


# --------------------------------------------------------------------------- the speed root


def closed_form_speed(q: float, head: float) -> float:
    """H₀ = a − b x: s² H₀(Q/s) = a s² − b Q s = H, the positive root (ORNL eq. 10, c = 0)."""
    a, b = LINEAR_A, LINEAR_B
    return (b * q + math.sqrt(b * b * q * q + 4.0 * a * head)) / (2.0 * a)


@pytest.mark.parametrize("q", [0.005, 0.02, 0.04])
@pytest.mark.parametrize("head", [2.0, 10.0, 25.0, 35.0])
def test_operating_speed_matches_the_closed_form(q: float, head: float) -> None:
    model = curve_model(linear_points())
    check = speed_uniqueness(model)
    s_min, s_max = 0.3, 1.0
    found = operating_speed(model, q, head, s_min, s_max, check.x_mono)
    expected = closed_form_speed(q, head)
    lo = max(s_min, q / check.x_mono)
    f_lo, f_hi = model.head(q, lo)[0], model.head(q, s_max)[0]
    if f_lo <= head <= f_hi:
        assert found.speed == pytest.approx(expected, rel=1e-12)
        assert abs(found.residual) < 1e-10
    else:  # clamped to the end of the bracket nearer the head
        assert found.speed == (s_max if head > f_hi else lo)
    assert s_min <= found.speed <= s_max


@pytest.mark.parametrize("seed", range(20))
def test_operating_speed_stays_within_the_speed_range(seed: int) -> None:
    """s* ∈ [s_min, s_max] whatever the head, and |F(s*) − H| is the clamp only."""
    rng = np.random.default_rng(seed)
    model = curve_model(CURVE_A)
    check = speed_uniqueness(model)
    q = float(rng.uniform(0.001, 0.06))
    s_min = float(rng.uniform(0.1, 0.8))
    s_max = float(rng.uniform(s_min + 0.05, 1.0))
    head = float(rng.uniform(-20.0, 60.0))
    found = operating_speed(model, q, head, s_min, s_max, check.x_mono)
    assert s_min <= found.speed <= s_max
    lo = found.lower
    f_lo, f_hi = model.head(q, lo)[0], model.head(q, s_max)[0]
    clamp = max(f_lo - head, head - f_hi, 0.0)
    assert abs(found.residual) == pytest.approx(clamp, abs=1e-9)


# --------------------------------------------------------------------------- law override


def test_law_override_equal_to_the_links_own_law_is_bit_identical() -> None:
    """§4.4: LinkState.law replaces a NORMAL link's law for one solve; overriding with the
    link's own law object, or with a new law of the same curve and speed, changes nothing."""
    built = build(pump_line(2.0, 20.0, None))
    link = built.pumps["PU"].link_index
    law = built.network.links[link].law
    base = solve_gga(
        built.network, [NORMAL] * len(built.network.links), tolerance=1e-9, max_iterations=100
    )
    for override in (law, type(law)(built.pumps["PU"].curve, 1.0)):
        states = [NORMAL] * len(built.network.links)
        states[link] = LinkState(LinkMode.NORMAL, law=override)
        again = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
        assert again.iterations == base.iterations
        assert np.array_equal(again.flows, base.flows)
        assert np.array_equal(again.heads, base.heads, equal_nan=True)


def test_minimum_speed_law_equals_a_fixed_pump_at_that_speed() -> None:
    """The Newton site (gga.py) reads the override: the controlled pump at MIN_SPEED solves
    bit-identically to a fixed-speed pump at s_min from the same starting flows."""
    controlled = build(pump_line(30.0, 2.0, flow_control(0.005, 0.4)))
    fixed = build(pump_line(30.0, 2.0, None, speed=0.4))
    controls = initial_controls(controlled)
    controls["PU"].status = Status.MIN_SPEED
    states = link_states(controlled, controls)
    assert states[controlled.pumps["PU"].link_index].law is controlled.pumps["PU"].min_law
    start = np.array([0.01, 0.01, 0.01])
    a = solve_gga(
        controlled.network, states, tolerance=1e-9, max_iterations=100, initial_flows=start
    )
    b = solve_gga(
        fixed.network, [NORMAL] * 3, tolerance=1e-9, max_iterations=100, initial_flows=start
    )
    assert a.converged
    assert np.array_equal(a.flows, b.flows)
    assert np.array_equal(a.heads, b.heads, equal_nan=True)


def isolated_pump() -> Project:
    """R1 -> isolated gate V1 -> PU (flow control) -> isolated gate V2 -> R2."""
    comps = [
        reservoir("R1", level=2.0),
        valve("V1", "gate", status="isolated"),
        pump("PU", flow_control(0.02)),
        valve("V2", "gate", status="isolated"),
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L2", ("V1", "outlet"), ("PU", "suction"), length=10.0),
        connection("L3", ("PU", "discharge"), ("V2", "inlet"), length=10.0),
        connection("L4", ("V2", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    return make_project(comps, conns, pump_library=[curve_dict(CURVE_A)])


@pytest.mark.parametrize("status", [Status.OPEN, Status.MIN_SPEED])
def test_closed_off_section_heads_read_the_override(status: Status) -> None:
    """status.closed_off_sections reads the law in force: a pump at minimum speed puts its
    shutoff head at s_min across a closed-off section, at maximum speed the one at s_max."""
    built = build(isolated_pump())
    controls = initial_controls(built)
    controls["PU"].status = status
    states = link_states(built, controls)
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    section, shift = closed_off_sections(built, result, states)
    data = built.pumps["PU"]
    assert data.control is not None
    s, d = built.network.node_index[data.suction], built.network.node_index[data.discharge]
    assert section[s] == section[d]
    expected = data.control.shutoff_min if status is Status.MIN_SPEED else data.control.shutoff_max
    assert shift[d] - shift[s] == pytest.approx(expected, rel=1e-14)


class ZeroShutoffLaw:
    """A law with no head at zero flow (a stand-in to show which law a site reads)."""

    def evaluate(self, flow: float) -> tuple[float, float]:
        return 1000.0 * flow, 1000.0


def floating_loop(control: dict[str, Any] | None) -> Project:
    """R1 -> isolated gate V -> T1; loop T1 -> PU -> T2 -> T1 with a plugged stub at T2."""
    comps = [
        reservoir("R1", level=10.0),
        valve("V", "gate", status="isolated"),
        tee("T1"),
        pump("PU", control),
        tee("T2"),
        plug("P"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("T1", "run_inlet")),
        connection("L3", ("T1", "run_outlet"), ("PU", "suction"), length=50.0),
        connection("L4", ("PU", "discharge"), ("T2", "run_inlet"), length=50.0),
        connection("L5", ("T2", "run_outlet"), ("P", "port_1")),
        connection("L6", ("T2", "branch"), ("T1", "branch"), length=400.0),
    ]
    return make_project(comps, conns, pump_library=[curve_dict(CURVE_A)])


def test_floating_section_test_reads_the_override() -> None:
    """gga.circulating_parts reads the law in force: a loop whose pump puts a head around it at
    zero flow circulates (floating), one whose law has no zero-flow head can rest (isolated)."""
    built = build(floating_loop(flow_control(0.02)))
    controls = initial_controls(built)
    controls["PU"].status = Status.MIN_SPEED
    states = link_states(built, controls)
    floating = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    assert floating.converged
    assert floating.floating_sections
    link = built.pumps["PU"].link_index
    states[link] = LinkState(LinkMode.NORMAL, law=ZeroShutoffLaw())
    resting = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    assert not resting.floating_sections
    assert built.network.node_index["PU:suction"] in resting.isolated_nodes


# --------------------------------------------------------------------------- fallbacks


def three_valves(with_pump: bool) -> Project:
    """R1 -> [PU flow control ->] V1 (PRV) -> V2 (PSV) -> V3 (FCV) -> R2 (statuses only)."""
    comps = [reservoir("R1", level=30.0)]
    if with_pump:
        comps.append(pump("PU", flow_control(0.02)))
    comps += [
        valve("V1", "prv", setpoint=1.0e5),
        valve("V2", "psv", setpoint=1.0e5),
        valve("V3", "fcv", setpoint=0.01),
        reservoir("R2", level=2.0),
    ]
    chain = [c["id"] for c in comps]
    ports = {"R1": ("port_1", "port_1"), "R2": ("port_1", "port_1"), "PU": ("suction", "discharge")}
    conns = []
    for i, (a, b) in enumerate(pairwise(chain)):
        out = ports.get(a, ("inlet", "outlet"))[1]
        into = ports.get(b, ("inlet", "outlet"))[0]
        conns.append(connection(f"L{i + 1}", (a, out), (b, into), length=10.0))
    return make_project(comps, conns, pump_library=[curve_dict(CURVE_A)])


def fallback_sequence(built: BuiltNetwork, result: GgaResult) -> list[Any]:
    """Every option ``_open_bad_valves`` takes, in order, each solve sending the network back
    to the failed (all active) state."""
    controls = initial_controls(built)
    active = {cid: c.status for cid, c in controls.items()}
    history = [_vector(controls, {})]
    taken: list[Any] = []
    for _ in range(40):
        outcome = _open_bad_valves(built, controls, {}, history, result)
        assert outcome is not None
        if not outcome[0]:
            taken.append(("none", outcome[1]))
            return taken
        taken.append(
            (
                outcome[1],
                {cid: c.status.value for cid, c in controls.items() if c.status is not active[cid]},
            )
        )
        history.append(_vector(controls, {}))
        for cid, status in active.items():
            controls[cid].status = status
    raise AssertionError("the fallbacks did not end")


def test_valve_only_fallbacks_take_the_v1_options_in_order() -> None:
    """§4.5: a network without speed-controlled pumps takes exactly the v1 options: all active
    valves open, then each alone, then the same closed (EPANET 2.2 badvalve)."""
    built = build(three_valves(with_pump=False))
    every = ["V1", "V2", "V3"]
    expected: list[Any] = []
    for state in ("open", "closed"):
        expected.append((every, dict.fromkeys(every, state)))
        expected += [([v], {v: state}) for v in every]
    expected.append(("none", every))
    assert fallback_sequence(built, failed_result(built)) == expected


def test_valve_only_fallbacks_for_undetermined_valves() -> None:
    """With valves named undetermined, each of them alone, open then closed (v1)."""
    built = build(three_valves(with_pump=False))
    v2 = built.valves["V2"].link_index
    expected = [(["V2"], {"V2": "open"}), (["V2"], {"V2": "closed"}), ("none", ["V2"])]
    assert fallback_sequence(built, failed_result(built, undetermined_links=[v2])) == expected


def test_fallbacks_with_a_speed_controlled_pump_add_a_minimum_speed_step() -> None:
    """A speed-controlled pump takes part as the valves do (open: maximum speed); between the
    open and closed options, the options holding it are tried at its minimum speed."""
    built = build(three_valves(with_pump=True))
    every = ["PU", "V1", "V2", "V3"]
    expected: list[Any] = [
        (every, dict.fromkeys(every, "open")),
        *[([c], {c: "open"}) for c in every],
        (["PU"], {"PU": "min_speed"}),  # the all-option at minimum speed: its pump only
        (every, dict.fromkeys(every, "closed")),
        *[([c], {c: "closed"}) for c in every],
        ("none", every),
    ]
    assert fallback_sequence(built, failed_result(built)) == expected


@pytest.mark.parametrize(
    ("gain_offset", "expected"),
    [(1.0, Status.OPEN), (-1.0, Status.MIN_SPEED), (0.0, None)],
)
def test_check_changes_apply_a1_and_a2_to_active_pumps(
    gain_offset: float, expected: Status | None
) -> None:
    """_check_changes: an active pump at the failed solve's early iterate takes A1 (above
    F(s_max, Q_set) + Htol: maximum speed) or A2 (below F(s_lo, Q_set) − Htol: minimum; here
    s_lo = s_min, Q_set/s_min being within x_mono)."""
    built = build(pump_line(2.0, 20.0, flow_control(0.02)))
    data = built.pumps["PU"]
    assert data.control is not None
    assert data.control.low_speed == data.control.min_speed
    gain = {
        1.0: data.control.head_at_max + 1.0,
        -1.0: data.control.head_at_low - 1.0,
        0.0: 0.5 * (data.control.head_at_low + data.control.head_at_max),
    }[gain_offset]
    heads = np.full(len(built.network.nodes), 10.0)
    heads[built.network.node_index[data.discharge]] = 10.0 + gain
    flows = np.zeros(len(built.network.links))
    flows[data.link_index] = 0.02
    result = failed_result(built, check_heads=heads, check_flows=flows)
    controls = initial_controls(built)
    changes = _check_changes(built, result, [controls["PU"]])
    assert changes == ({} if expected is None else {"PU": expected})


def test_gga_names_controls_between_two_active_pumps() -> None:
    """Two flow pumps in series, both active: the pressure between them is undetermined; the
    message says 'controls' once a pump is named, and keeps its v1 words for valves."""
    comps = [
        reservoir("R1", level=2.0),
        pump("P1", flow_control(0.02)),
        pump("P2", flow_control(0.03)),
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=10.0),
        connection("L2", ("P1", "discharge"), ("P2", "suction"), length=10.0),
        connection("L3", ("P2", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    built = build(make_project(comps, conns, pump_library=[curve_dict(CURVE_A)]))
    states = link_states(built, initial_controls(built))
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    assert not result.converged
    assert result.message.startswith("the pressure between controls P1, P2 is undetermined")
    valves = [
        reservoir("R1", level=20.0),
        valve("V1", "fcv", setpoint=0.01),
        valve("V2", "fcv", setpoint=0.02),
        reservoir("R2", level=2.0),
    ]
    links = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L2", ("V1", "outlet"), ("V2", "inlet"), length=10.0),
        connection("L3", ("V2", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    built = build(make_project(valves, links))
    states = link_states(built, initial_controls(built))
    result = solve_gga(built.network, states, tolerance=1e-9, max_iterations=100)
    assert result.message == (
        "the pressure between control valves V1, V2 is undetermined: no reservoir or reference "
        "node fixes it, so the valves cannot all hold their setpoints"
    )


# --------------------------------------------------------------------------- the A2 bound


def linear_head(s: float, q: float) -> float:
    """F(s, Q) = s² H₀(Q/s) = a s² − b Q s for the linear test curve."""
    return LINEAR_A * s * s - LINEAR_B * q * s


def test_bracket_low_speed_and_head_of_a_built_pump() -> None:
    """D11: s_lo = max(s_min, Q_set/x_mono), below s_max, and F(s_lo, Q_set), the bound of
    rule A2. For H₀ = a − b x, ψ = 2a − b x, so x_mono = 2a/b; dF/ds = 2a s − b Q is zero at
    s = b Q/(2a) = Q/x_mono, where F is least. A setpoint beyond x_mono at every speed (Q_set =
    0.2 > s_max x_mono = 0.16) was held at s_lo = s_max; since the owner's decision of
    2026-10-23 it is rejected (CONTROLLED_PUMP_SETPOINT)."""
    x_mono = 2.0 * LINEAR_A / LINEAR_B
    cases = [
        (0.02, 0.3, 1.0, 0.3),  # Q_set/s_min within x_mono: s_lo = s_min
        (0.04, 0.1, 1.0, 0.04 / x_mono),  # beyond it: s_lo = Q_set/x_mono
    ]
    beyond = pump_line(2.0, 10.0, flow_control(0.2, 0.1), points=linear_points())
    with pytest.raises(TopologyError) as raised:
        build(beyond)  # beyond it at every speed
    assert [i.code for i in raised.value.issues] == ["CONTROLLED_PUMP_SETPOINT"]
    for q_set, s_min, s_max, s_lo in cases:
        project = pump_line(2.0, 10.0, flow_control(q_set, s_min), points=linear_points())
        control = build(project).pumps["PU"].control
        assert control is not None
        assert control.uniqueness.x_mono == pytest.approx(x_mono, rel=1e-12)
        assert control.low_speed == pytest.approx(s_lo, rel=1e-12)
        assert control.head_at_low == pytest.approx(linear_head(s_lo, q_set), rel=1e-12)
        assert control.head_at_min == pytest.approx(linear_head(s_min, q_set), rel=1e-12)
        assert control.head_at_low <= min(control.head_at_min, control.head_at_max)
        assert control.head_at_low == pytest.approx(
            min(linear_head(s, q_set) for s in np.linspace(s_min, s_max, 2001)), abs=1e-6
        )


def test_a_head_between_f_lo_and_f_min_is_held_on_the_rising_stretch() -> None:
    """Findings 2 and 8 of the slice-1 review (D11): with Q_set/s_min beyond x_mono, F(·,
    Q_set) falls on [s_min, s_lo] and rises on [s_lo, s_max], so F(s_lo, Q_set) < F(s_min,
    Q_set). A head at Q_set between them is held by a speed in (s_lo, s_max], the root on the
    stretch a flow controller can regulate on: the pump is active there (rule A2 tests
    F(s_lo, Q_set)), not at minimum speed passing more than its setpoint. Before, A2 tested
    F(s_min, Q_set) and reported minimum speed with PUMP_SETPOINT_NOT_MET."""
    q_set, s_min = 0.04, 0.1
    s_lo = q_set * LINEAR_B / (2.0 * LINEAR_A)  # Q_set/x_mono = 0.25
    f_lo, f_min = linear_head(s_lo, q_set), linear_head(s_min, q_set)  # −2.5 m, −1.6 m
    target = 0.5 * (f_lo + f_min)  # the head at Q_set the network is set to need
    assert f_lo + HTOL < target < f_min - HTOL
    # At a fixed flow the head across the pump moves one for one with R2's level.
    probe = pump_line(100.0, 100.0, flow_control(q_set, s_min), points=linear_points())
    [point] = system_curve_points(build(probe), "PU", [q_set], tolerance=1e-9, max_iterations=100)
    assert point.converged
    assert point.head is not None
    project = pump_line(
        100.0, 100.0 + target - point.head, flow_control(q_set, s_min), points=linear_points()
    )
    result = solve_project(project, NO_CURVES)
    assert result.converged
    pr = result.pump_results["PU"]
    assert pr.control is not None
    assert (pr.control.state, pr.control.setpoint_achieved) == ("active", True)
    assert pr.operating_flow == q_set
    assert pr.operating_head == pytest.approx(target, abs=1e-6)
    assert pr.speed == pytest.approx(closed_form_speed(q_set, pr.operating_head), rel=1e-9)
    assert s_lo < pr.speed <= 1.0
    assert not [f for f in result.flags if f.code == "PUMP_SETPOINT_NOT_MET"]
    # M2: the fixed pump at that speed delivers the setpoint.
    fixed = solve_project(without_control(project, pr.speed), NO_CURVES)
    assert fixed.pump_results["PU"].operating_flow == pytest.approx(q_set, rel=1e-6)
    notes = result.trace.elements["PU"].notes
    assert any(
        n.startswith("Active, holding its flow setpoint: F(s_lo, Q_set) − Htol = -2.5001 m")
        for n in notes
    ), notes


# --------------------------------------------------------------------------- results


def test_active_pump_results_at_the_solved_speed() -> None:
    """§2.6, §4.7: an active pump carries Q_set; its speed is the closed-form root at the solved
    head (linear curve); curve, efficiency, NPSHr and range are at that speed."""
    efficiency = [(0.0, 0.3), (0.03, 0.75), (0.06, 0.5)]
    npshr = [(0.0, 1.0), (0.03, 2.0), (0.06, 4.0)]
    project = pump_line(
        2.0,
        10.0,
        flow_control(0.02, 0.3),
        points=linear_points(),
        efficiency=efficiency,
        npshr=npshr,
        vapor_pressure=2339.0,
    )
    result = solve_project(project, NO_CURVES)
    assert result.converged
    pr = result.pump_results["PU"]
    assert pr.status == "running"
    assert pr.control is not None
    assert (pr.control.mode, pr.control.state, pr.control.setpoint) == ("flow", "active", 0.02)
    assert pr.control.setpoint_achieved is True
    assert pr.operating_flow == 0.02
    egl_s = result.node_results["PU:suction"].egl
    egl_d = result.node_results["PU:discharge"].egl
    assert pr.operating_head == pytest.approx(egl_d - egl_s, abs=1e-12)
    s = closed_form_speed(0.02, pr.operating_head)
    assert pr.speed == pytest.approx(s, rel=1e-12)
    x = 0.02 / s
    assert pr.efficiency == pytest.approx(
        float(PchipInterpolator(*zip(*efficiency, strict=True))(x)), rel=1e-12
    )
    assert pr.npsh_required == pytest.approx(
        s * s * float(PchipInterpolator(*zip(*npshr, strict=True))(x)), rel=1e-12
    )
    assert pr.in_curve_range
    assert pr.curve[0].flow == 0.0
    assert pr.curve[-1].flow == pytest.approx(0.06 * s, rel=1e-14)
    for point in pr.curve:
        expected = s * s * (LINEAR_A - LINEAR_B * point.flow / s)
        assert point.head == pytest.approx(expected, rel=1e-9, abs=1e-9)
    assert not [f for f in result.flags if f.code == "PUMP_SETPOINT_NOT_MET"]


def test_limit_states_report_the_limit_speed_and_the_flag() -> None:
    """max_speed and min_speed run at the limit speed, with PUMP_SETPOINT_NOT_MET (info) and
    its details; the curve is sampled at that speed."""
    high = solve_project(pump_line(2.0, 20.0, flow_control(0.05), speed=0.9), NO_CURVES)
    pr = high.pump_results["PU"]
    assert pr.control is not None
    assert (pr.control.state, pr.speed, pr.status) == ("max_speed", 0.9, "running")
    assert pr.control.setpoint_achieved is False
    assert pr.operating_flow < 0.05
    assert pr.curve[-1].flow == pytest.approx(0.04 * 0.9, rel=1e-14)
    [flag] = [f for f in high.flags if f.code == "PUMP_SETPOINT_NOT_MET"]
    assert (flag.severity, flag.component_id) == ("info", "PU")
    assert flag.details == {
        "state": "max_speed",
        "setpoint": 0.05,
        "flow": pr.operating_flow,
        "speed": 0.9,
        "minSpeed": 0.4,
        "maxSpeed": 0.9,
    }
    assert "maximum speed 0.9" in flag.message

    low = solve_project(pump_line(30.0, 2.0, flow_control(0.005, 0.4)), NO_CURVES)
    pr = low.pump_results["PU"]
    assert pr.control is not None
    assert (pr.control.state, pr.speed) == ("min_speed", 0.4)
    assert pr.operating_flow > 0.005
    [flag] = [f for f in low.flags if f.code == "PUMP_SETPOINT_NOT_MET"]
    assert flag.details["state"] == "min_speed"
    assert "minimum speed 0.4" in flag.message


def test_no_flow_off_dead_end_and_isolated_controlled_pumps() -> None:
    """§5: no flow at s_max (reversal flag and setpoint flag); off (control not applied, no
    flag); a dead end at s_max, exactly the fixed pump; isolated: no result and no flag."""
    no_flow = solve_project(pump_line(2.0, 60.0, flow_control(0.02)), NO_CURVES)
    pr = no_flow.pump_results["PU"]
    assert pr.control is not None
    assert (pr.status, pr.control.state, pr.speed, pr.operating_flow) == (
        "no_flow",
        "no_flow",
        1.0,
        0.0,
    )
    codes = {f.code for f in no_flow.flags}
    assert {"PUMP_FLOW_REVERSAL", "PUMP_SETPOINT_NOT_MET"} <= codes

    off = solve_project(pump_line(2.0, 20.0, flow_control(0.02), status="off"), NO_CURVES)
    pr = off.pump_results["PU"]
    assert pr.control is not None
    assert (pr.status, pr.control.state, pr.control.setpoint_achieved) == ("off", "off", None)
    assert not [f for f in off.flags if f.code == "PUMP_SETPOINT_NOT_MET"]
    assert "Its speed control is not applied: status off." in off.trace.elements["PU"].notes

    def dead_end(control: dict[str, Any] | None) -> SolvedState:
        comps = [reservoir("R1", level=2.0), pump("PU", control), plug("X")]
        conns = [
            connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
            connection("L2", ("PU", "discharge"), ("X", "port_1"), length=10.0),
        ]
        project = make_project(comps, conns, pump_library=[curve_dict(CURVE_A)])
        return solve_project(project, NO_CURVES)

    controlled, fixed = dead_end(flow_control(0.02)), dead_end(None)
    a, b = controlled.pump_results["PU"], fixed.pump_results["PU"]
    assert a.control is not None
    assert a.control.state == "max_speed"
    assert (a.status, a.operating_flow, a.operating_head) == (b.status, 0.0, b.operating_head)
    assert a.operating_head == 45.0
    assert controlled.node_results == fixed.node_results

    isolated = solve_project(isolated_pump(), NO_CURVES)
    assert isolated.converged
    assert "PU" not in isolated.pump_results
    assert {f.code for f in isolated.flags if f.component_id == "PU"} == {"ISOLATED_SECTION"}


def check_valve_line(foot: bool) -> Project:
    """R1 (2 m) -> [foot check valve F] -> PU (flow control) -> check valve CV -> R2 (60 m):
    the 58 m lift exceeds the 45 m shutoff head, so the check valve closes the discharge."""
    comps: list[dict[str, Any]] = [reservoir("R1", level=2.0)]
    conns: list[dict[str, Any]] = []
    upstream = ("R1", "port_1")
    if foot:
        comps.append(valve("F", "check"))
        conns.append(connection("L0", upstream, ("F", "inlet"), length=5.0))
        upstream = ("F", "outlet")
    comps += [pump("PU", flow_control(0.02)), valve("CV", "check"), reservoir("R2", level=60.0)]
    conns += [
        connection("L1", upstream, ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("CV", "inlet"), length=10.0),
        connection("L3", ("CV", "outlet"), ("R2", "port_1"), length=200.0),
    ]
    return make_project(comps, conns, pump_library=[curve_dict(CURVE_A)])


def test_no_flow_setpoint_flag_states_why_there_is_no_flow() -> None:
    """PUMP_SETPOINT_NOT_MET at no flow says the head across the pump exceeds its shutoff head
    only when it does (finding 4 of the slice-1 review), as the trace note does: a pump whose
    discharge a closed check valve closes off runs dead-headed at exactly its shutoff head, and
    one closed off on both sides has no head across it at all. ``closedOff`` in the details
    names the closed-off side(s)."""

    def flag(result: SolvedState) -> Any:
        [found] = [f for f in result.flags if f.code == "PUMP_SETPOINT_NOT_MET"]
        return found

    lifted = flag(solve_project(pump_line(2.0, 60.0, flow_control(0.02)), NO_CURVES))
    assert "the head across it (58 m) exceeds its shutoff head at its maximum speed 1 (45 m)" in (
        lifted.message
    )
    assert "closedOff" not in lifted.details

    result = solve_project(check_valve_line(foot=False), NO_CURVES)
    pr = result.pump_results["PU"]
    assert pr.control is not None
    assert (pr.status, pr.control.state, pr.operating_head) == ("no_flow", "no_flow", 45.0)
    dead = flag(result)
    assert "exceeds" not in dead.message
    assert "its discharge is closed off, so it runs dead-headed at its shutoff head" in (
        dead.message
    )
    assert dead.details["closedOff"] == "discharge"

    result = solve_project(check_valve_line(foot=True), NO_CURVES)
    assert "PU" not in result.pump_results
    both = flag(result)
    assert "exceeds" not in both.message
    assert "both its sides are closed off" in both.message
    assert both.details["closedOff"] == "both"


def test_floating_loop_with_an_active_pump() -> None:
    """§5: a sealed loop circulates the setpoint; the head across the pump is exact, so is s*;
    UNDETERMINED_PRESSURE names the pump as its driver; NPSH available is not computed."""
    result = solve_project(floating_loop(flow_control(0.02)), NO_CURVES)
    assert result.converged
    pr = result.pump_results["PU"]
    assert pr.control is not None
    assert pr.control.state == "active"
    assert result.link_results["L6"].flow == pytest.approx(0.02, rel=1e-12)
    [flag] = [f for f in result.flags if f.code == "UNDETERMINED_PRESSURE"]
    assert flag.component_id == "PU"
    assert pr.npsh_available is None
    model = curve_model(CURVE_A)
    assert model.head(0.02, pr.speed)[0] == pytest.approx(pr.operating_head, abs=1e-9)
    loop = sum(result.link_results[c].head_loss for c in ("L3", "L4", "L6"))
    assert pr.operating_head == pytest.approx(loop, rel=1e-9)


def test_trace_notes_per_state_and_conditional_methods() -> None:
    """§6: the state note states the inequality with its values; the control inputs, the
    uniqueness values and the speed-control methods appear only with a control."""
    active = solve_project(pump_line(2.0, 20.0, flow_control(0.02)), NO_CURVES)
    trace = active.trace.elements["PU"]
    names = {i.name: i for i in trace.inputs}
    assert names["Flow setpoint Q_set"].source == "user"
    assert names["Minimum speed s_min"].source == "user"
    assert names["Maximum speed s_max (field speed)"].source == "default"
    assert "Speed ratio s" not in names
    assert any(
        n.startswith("Active, holding its flow setpoint: F(s_lo, Q_set) − Htol")
        for n in trace.notes
    )
    values = {v.name for v in trace.intermediates}
    assert {"Speed it runs at s", "Residual F(s, Q) − H", "x_mono (2 H₀ − x H₀' > 0 below it)"} <= (
        values
    )
    assert any("Brent" in c.name for c in trace.correlations)
    pumps = next(s for s in active.trace.methods.sections if s.title == "Pumps")
    assert any(i.startswith("Speed-controlled pumps (flow setpoint)") for i in pumps.items)

    high = solve_project(pump_line(2.0, 20.0, flow_control(0.05), speed=0.9), NO_CURVES)
    assert any(
        n.startswith("At maximum speed, the setpoint not held: Q = ")
        for n in high.trace.elements["PU"].notes
    )
    low = solve_project(pump_line(30.0, 2.0, flow_control(0.005)), NO_CURVES)
    assert any(
        n.startswith("At minimum speed, passing more than the setpoint: Q = ")
        for n in low.trace.elements["PU"].notes
    )
    none = solve_project(pump_line(2.0, 60.0, flow_control(0.02)), NO_CURVES)
    assert any(
        n.startswith("No flow: H = 58 m > s_max² H₀(0) = 45 m; its controller sees no flow")
        for n in none.trace.elements["PU"].notes
    )

    fixed = solve_project(pump_line(2.0, 20.0, None), NO_CURVES)
    pumps = next(s for s in fixed.trace.methods.sections if s.title == "Pumps")
    assert not any("Speed-controlled" in i or "speed-controlled" in i for i in pumps.items)
    assert not any("Brent" in c.name for c in fixed.trace.elements["PU"].correlations)
    assert any(
        n.startswith("Running: the head across the pump") for n in fixed.trace.elements["PU"].notes
    )


def test_an_off_controlled_pump_regulates_nothing_in_the_traces() -> None:
    """Finding 9 of the slice-1 review: an off speed-controlled pump is closed in the solve and
    at every system-curve point, so another pump's trace does not say it keeps regulating, and
    its own trace gives no speed it runs at and no reduced-speed efficiency note."""

    def joined(pb_status: str) -> Project:
        data = joined_pumps().model_dump(mode="json", by_alias=True, exclude_none=True)
        for comp in data["components"]:
            if comp["id"] == "PB":
                comp["status"] = pb_status
        return Project.model_validate(data)

    regulating = "The other speed-controlled pumps keep regulating"
    on = solve_project(joined("on"), NO_CURVES).trace.elements
    assert any(e.startswith(regulating) for e in on["PA"].equations)
    assert "Speed it runs at s" in {v.name for v in on["PB"].intermediates}
    assert any(n.startswith("Efficiency and NPSHr at the speed it runs at") for n in on["PB"].notes)

    result = solve_project(joined("off"), NO_CURVES)
    assert result.pump_results["PB"].status == "off"
    traces = result.trace.elements
    assert not any(e.startswith(regulating) for e in traces["PA"].equations)
    assert "Speed it runs at s" not in {v.name for v in traces["PB"].intermediates}
    assert not any(n.startswith("Efficiency and NPSHr at the speed") for n in traces["PB"].notes)
    assert "Its speed control is not applied: status off." in traces["PB"].notes


# --------------------------------------------------------------------------- equal setpoints


def series_pumps(h2: float, q1: float, q2: float) -> Project:
    comps = [
        reservoir("R1", level=2.0),
        pump("P1", flow_control(q1, 0.5)),
        pump("P2", flow_control(q2, 0.5)),
        reservoir("R2", level=h2),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=10.0),
        connection("L2", ("P1", "discharge"), ("P2", "suction"), length=10.0),
        connection("L3", ("P2", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    return make_project(comps, conns, pump_library=[curve_dict(CURVE_A)])


@pytest.mark.parametrize("h2", [5.0, 20.0, 30.0, 40.0, 60.0])
def test_equal_setpoints_in_series_do_not_converge(h2: float) -> None:
    """§4.6, §5: two flow pumps in series holding the same flow leave the pressure between them
    undetermined: not converged, naming both, wherever rounding leaves the iteration, and the
    message says why (over-controlled), whether the iteration ends converged at a limit
    (``_over_controlled``) or with statuses cycling (``_equal_setpoints_note``)."""
    result = solve_project(series_pumps(h2, 0.02, 0.02), NO_CURVES)
    assert not result.converged
    assert result.convergence.oscillating_components == ["P1", "P2"]
    message = result.convergence.message
    assert message.startswith("the controls P1, P2 are in series"), message
    assert "pressure between them" in message
    assert "over-controlled" in message


def test_unequal_setpoints_in_series_converge_to_one_state() -> None:
    """§4.6: with Q1 < Q2 the upstream pump at minimum speed and the downstream one at maximum
    pass a flow between the setpoints (at a 20 m lift); at 60 m the smaller setpoint holds."""
    low_lift = solve_project(series_pumps(20.0, 0.02, 0.03), NO_CURVES)
    states = {k: v.control.state for k, v in low_lift.pump_results.items() if v.control}
    assert states == {"P1": "min_speed", "P2": "max_speed"}
    assert 0.02 < low_lift.pump_results["P1"].operating_flow < 0.03
    lift = solve_project(series_pumps(60.0, 0.02, 0.03), NO_CURVES)
    states = {k: v.control.state for k, v in lift.pump_results.items() if v.control}
    assert states == {"P1": "active", "P2": "max_speed"}


def test_flow_pump_and_fcv_with_equal_setpoints_do_not_converge() -> None:
    comps = [
        reservoir("R1", level=2.0),
        pump("PU", flow_control(0.02, 0.5)),
        valve("V", "fcv", setpoint=0.02),
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("V", "inlet"), length=10.0),
        connection("L3", ("V", "outlet"), ("R2", "port_1"), length=200.0),
    ]
    result = solve_project(
        make_project(comps, conns, pump_library=[curve_dict(CURVE_A)]), NO_CURVES
    )
    assert not result.converged
    assert result.convergence.oscillating_components == ["PU", "V"]
    assert result.convergence.message.startswith("the controls PU, V are in series")
    assert "over-controlled" in result.convergence.message


def test_fcvs_without_speed_control_keep_their_v1_result() -> None:
    """The over-control test concerns speed-controlled pumps only: two FCVs in series with
    equal setpoints converge as in v1, one active and one open at its setpoint."""
    comps = [
        reservoir("R1", level=30.0),
        valve("V1", "fcv", setpoint=0.02),
        valve("V2", "fcv", setpoint=0.02),
        reservoir("R2", level=2.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L2", ("V1", "outlet"), ("V2", "inlet"), length=10.0),
        connection("L3", ("V2", "outlet"), ("R2", "port_1"), length=200.0),
    ]
    result = solve_project(make_project(comps, conns), NO_CURVES)
    assert result.converged
    assert {v.state for v in result.valve_results.values()} == {"active", "open"}


# --------------------------------------------------------------------------- metamorphic


@pytest.mark.parametrize(
    ("h1", "h2", "control", "speed", "state"),
    [
        (2.0, 20.0, flow_control(0.05), 0.9, "max_speed"),
        (30.0, 2.0, flow_control(0.005, 0.4), 1.0, "min_speed"),
    ],
)
def test_m1_a_pump_at_a_limit_is_the_fixed_pump_at_that_speed(
    h1: float, h2: float, control: dict[str, Any], speed: float, state: str
) -> None:
    """M1 (§7.3): re-solved with the control removed and the speed at its limit, the flows,
    heads and statuses are those of the controlled solve (to the solver's tolerance: the two
    solves start from different flows); from the same flows and states, bit-identical.

    M1 holds where the network has one steady state that satisfies every element's rule, as
    this line does. Where several do (a section closed off at zero flow, whose free level lets
    the closed elements around it stay closed while another state runs flow there, D9: v1's
    zero-flow multiplicity), each solve returns the state its iteration reaches, and the two
    iterations differ: the controlled pump starts active and follows its own rules (A0-C1) on
    the way, the fixed pump starts open. In flow_control seeds 10,236, 10,647 and 11,214 of the
    differential test both final states pass the independent checks; they differ in statuses
    at zero flow (a dead-ended pump running at no flow or held closed) or, in 11,214, in
    whether a pump loop behind closed valves circulates."""
    project = pump_line(h1, h2, control, speed=speed)
    controlled = solve_project(project, NO_CURVES)
    pr = controlled.pump_results["PU"]
    assert pr.control is not None
    assert pr.control.state == state
    fixed = solve_project(without_control(project, pr.speed), NO_CURVES)
    assert fixed.pump_results["PU"].status == pr.status
    for conn_id, link in controlled.link_results.items():
        assert link.flow == pytest.approx(fixed.link_results[conn_id].flow, rel=1e-9)
    for key, node in controlled.node_results.items():
        assert node.egl == pytest.approx(fixed.node_results[key].egl, abs=1e-7)

    built_c = build(project)
    built_f = build(without_control(project, pr.speed))
    outer_c = run_outer_loop(built_c, tolerance=1e-9, max_iterations=100)
    outer_f = run_outer_loop(built_f, tolerance=1e-9, max_iterations=100)
    start = np.full(len(built_c.network.links), 0.01)
    a = solve_gga(
        built_c.network, outer_c.states, tolerance=1e-9, max_iterations=100, initial_flows=start
    )
    b = solve_gga(
        built_f.network, outer_f.states, tolerance=1e-9, max_iterations=100, initial_flows=start
    )
    assert np.array_equal(a.flows, b.flows)
    assert np.array_equal(a.heads, b.heads, equal_nan=True)


@pytest.mark.parametrize(("h2", "setpoint"), [(20.0, 0.02), (10.0, 0.01), (2.0, 0.03)])
def test_m2_fixed_at_the_solved_speed_the_pump_delivers_its_setpoint(
    h2: float, setpoint: float
) -> None:
    """M2 (§7.3): re-solved as a fixed-speed pump at s*, the flow is Q_set (within D6, and in
    fact to the solver's tolerance), and its head is the controlled solve's within 0.01 m."""
    project = pump_line(2.0, h2, flow_control(setpoint, 0.4))
    controlled = solve_project(project, NO_CURVES)
    pr = controlled.pump_results["PU"]
    assert pr.control is not None
    assert pr.control.state == "active"
    fixed = solve_project(without_control(project, pr.speed), NO_CURVES)
    q = fixed.pump_results["PU"].operating_flow
    assert q == pytest.approx(setpoint, rel=D6_REL)
    assert q == pytest.approx(setpoint, rel=1e-6)
    assert fixed.pump_results["PU"].operating_head == pytest.approx(pr.operating_head, abs=0.01)


# --------------------------------------------------------------------------- system curves


def joined_pumps() -> Project:
    """R1 (30 m) -> flow-controlled PB -> tee T; R3 (2 m) -> fixed PA -> T; T -> R2 (2 m).
    Gravity drives more than PB's setpoint through it even at its minimum speed, until PA's
    flow raises the head at T."""
    comps = [
        reservoir("R1", level=30.0),
        pump("PB", flow_control(0.005, 0.4)),
        tee("T"),
        reservoir("R3", level=2.0),
        pump("PA"),
        reservoir("R2", level=2.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PB", "suction"), length=10.0),
        connection("L2", ("PB", "discharge"), ("T", "run_inlet"), length=10.0),
        connection("L3", ("R3", "port_1"), ("PA", "suction"), length=10.0),
        connection("L4", ("PA", "discharge"), ("T", "branch"), length=10.0),
        connection("L5", ("T", "run_outlet"), ("R2", "port_1"), length=200.0),
    ]
    return make_project(comps, conns, pump_library=[curve_dict(CURVE_A)])


def test_system_curve_warm_start_carries_minimum_speed() -> None:
    """§4.8: the viewed pump is replaced by the fixed flow; another speed-controlled pump keeps
    regulating, and a warm start copies its MIN_SPEED status, whose law follows from it. The
    warm-started curve agrees with one solved cold at every point."""
    built = build(joined_pumps())
    outer = run_outer_loop(built, tolerance=1e-9, max_iterations=100)
    assert outer.converged
    assert outer.controls["PB"].status is Status.MIN_SPEED
    controls = initial_controls(built, {"PA": 0.01})
    _warm_start(built, controls, {}, outer)
    assert controls["PB"].status is Status.MIN_SPEED
    states = link_states(built, controls, {}, {"PA": 0.01})
    assert states[built.pumps["PB"].link_index].law is built.pumps["PB"].min_law
    assert states[built.pumps["PA"].link_index] == LinkState(LinkMode.FIXED_FLOW, 0.01)

    flows = [0.0, 0.01, 0.02, 0.03, 0.04]
    warm = system_curve_points(built, "PA", flows, tolerance=1e-9, max_iterations=100, warm=outer)
    cold = system_curve_points(
        build(joined_pumps()), "PA", flows, tolerance=1e-9, max_iterations=100
    )
    for a, b in zip(warm, cold, strict=True):
        assert a.converged
        assert b.converged
        assert a.head == pytest.approx(b.head, abs=1e-6)


def test_viewed_pumps_control_is_replaced_by_the_fixed_flow() -> None:
    """§4.8: a speed-controlled pump's own system curve is defined as any pump's: with its
    control replaced by the fixed flow, H_sys at its setpoint is its solved head, so the
    operating point lies on the curve at s*."""
    project = pump_line(2.0, 20.0, flow_control(0.02))
    result = solve_project(project, NO_CURVES)
    pr = result.pump_results["PU"]
    built = build(project)
    [point] = system_curve_points(built, "PU", [0.02], tolerance=1e-9, max_iterations=100)
    assert point.head == pytest.approx(pr.operating_head, abs=1e-7)
    assert curve_model(CURVE_A).head(0.02, pr.speed)[0] == pytest.approx(point.head, abs=1e-7)


def test_controlled_pump_needs_no_new_tolerance() -> None:
    """The rules use EPANET's Htol and Qtol (status.py) and nothing else (§4.1)."""
    assert (HTOL, QTOL) == (1.0e-4, 1.0e-8)
