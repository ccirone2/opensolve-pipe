"""Unit checks of the differential test's own pieces (TSD §10.4) for flow-controlled pumps and the
corpus comparison: the rule checker written from proposal vfd-pump-modes.md §4.5 at its
tolerance edges, the closed-form implied speed, the 'flow_control' generator profile, the EPANET
substitutes, the control search's split of distinct valid states into multiple states and
alternatives at rest, and ``compare --ignore`` and ``--ignore-null``. Fast; no EPANET run (the
WNTR model build is skipped where WNTR is not installed).
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("wntr")  # checks reads EPANET results (a dev dependency, so CI runs this)

from opensolve_pipe.models.components import Pump, PumpControl
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver.builder import validate_topology
from tests.differential import checks as ck
from tests.differential import compare
from tests.differential import epanet_model as em
from tests.differential import state_search as ss
from tests.differential.generator import DEFAULT, FLOW_CONTROL, generate
from tests.reference import element_laws as el
from tests.reference.case_format import pump, pump_curve

A, B = 40.0, 2000.0  # test curve H₀ = A − B·x (m, m per m³/s): random test inputs
CURVE = pump_curve("PC", [(0.0, A), (0.005, A - B * 0.005), (0.01, A - B * 0.01)])
Q_SET, S_MIN, S_MAX = 0.004, 0.5, 0.9
PUMP = pump("PU", 0.0, "PC", speed=S_MAX).model_copy(
    update={"control": PumpControl(mode="flow", setpoint=Q_SET, min_speed=S_MIN)}
)
HTOL, QTOL = ck.HTOL, ck.QTOL


def head(speed: float, q: float) -> float:
    return el.pump_head(CURVE, speed, q)


F_MIN, F_MAX = head(S_MIN, Q_SET), head(S_MAX, Q_SET)
S_MIN_SHUT, S_MAX_SHUT = head(S_MIN, 0.0), head(S_MAX, 0.0)


@pytest.mark.parametrize(
    ("state", "gain", "q", "expected"),
    [
        # active: A1, A2; a boundary point keeps the state (proposal §4.6)
        ("active", F_MAX + HTOL, Q_SET, "active"),
        ("active", F_MAX + 2 * HTOL, Q_SET, "max_speed"),
        ("active", F_MIN - HTOL, Q_SET, "active"),
        ("active", F_MIN - 2 * HTOL, Q_SET, "min_speed"),
        # max_speed: X1 (Q ≥ Q_set), X2 (v1 pumpstatus at S_max)
        ("max_speed", F_MAX, Q_SET, "active"),
        ("max_speed", F_MAX, 0.9 * Q_SET, "max_speed"),
        ("max_speed", S_MAX_SHUT + HTOL, 0.0, "max_speed"),
        ("max_speed", S_MAX_SHUT + 2 * HTOL, 0.0, "no_flow"),
        ("max_speed", F_MAX, -2 * QTOL, "no_flow"),
        # min_speed: N1 (Q ≤ Q_set), N2 (v1 pumpstatus at S_min)
        ("min_speed", F_MIN, Q_SET, "active"),
        ("min_speed", F_MIN, 1.1 * Q_SET, "min_speed"),
        ("min_speed", S_MIN_SHUT + 2 * HTOL, 1.1 * Q_SET, "no_flow"),
        # no_flow: C1 (re-opens at maximum speed once H ≤ S_max)
        ("no_flow", S_MAX_SHUT, 0.0, "max_speed"),
        ("no_flow", S_MAX_SHUT + HTOL / 2, 0.0, "no_flow"),
    ],
)
def test_rule_flow_pump(state: str, gain: float, q: float, expected: str) -> None:
    assert ck.rule_flow_pump(state, gain, q, PUMP, CURVE) == expected


def _pump_with(q_set: float, s_min: float, s_max: float = S_MAX) -> Pump:
    return pump("PU", 0.0, "PC", speed=s_max).model_copy(
        update={"control": PumpControl(mode="flow", setpoint=q_set, min_speed=s_min)}
    )


def test_rule_a2_tests_the_lowest_head_of_the_stable_bracket() -> None:
    """A2 bounds by F(s_lo, Q_set), s_lo = max(s_min, Q_set/x_mono) (proposal §4.3, §4.5). On
    the test curve x_mono = 2A/B = 0.04 m³/s; Q_set = 0.004 with s_min = 0.05 gives s_lo = 0.1,
    F(s_lo, Q_set) = 0.01 (40 − 80) = −0.4 m below F(s_min, Q_set) = 0.0025 (40 − 160) = −0.3 m.
    A head between them is held by a speed on [s_lo, s_max]: active, not min_speed."""
    low = _pump_with(0.004, 0.05)
    f_lo, f_min = head(0.1, 0.004), head(0.05, 0.004)
    assert f_lo == pytest.approx(-0.4, rel=1e-12)
    assert f_min == pytest.approx(-0.3, rel=1e-12)
    assert ck.rule_flow_pump("active", -0.35, 0.004, low, CURVE) == "active"
    assert ck.rule_flow_pump("active", f_lo - HTOL, 0.004, low, CURVE) == "active"
    assert ck.rule_flow_pump("active", f_lo - 2 * HTOL, 0.004, low, CURVE) == "min_speed"
    band = ck.active_band(low, CURVE, "s", "d")
    assert band == [("s", "d", head(S_MAX, 0.004) + HTOL, "PU"), ("d", "s", -(f_lo - HTOL), "PU")]


def test_rule_a2_with_the_bracket_capped_at_the_maximum_speed() -> None:
    """s_lo is at most s_max: Q_set = 0.04 at s_max = 0.9 puts Q_set/s_max = 0.0444 beyond
    x_mono = 0.04, so F(·, Q_set) falls on the whole range and only F(s_max, Q_set) ± Htol is
    active. The uncapped Q_set/x_mono = 1.0 would give F(1, Q_set) = 40 − 80 = −40 m, below
    F(s_max, Q_set) = 0.81 (40 − 2000 · 0.04/0.9) = −39.6 m, and accept a head between them.
    The API rejects such a setpoint (Q_set >= s_max x_mono, CONTROLLED_PUMP_SETPOINT) since the
    owner's decision of 2026-10-23, so no fuzz network has one; this checks the checker's rule
    on its own."""
    capped = _pump_with(0.04, 0.5)
    f_max = head(S_MAX, 0.04)
    assert head(1.0, 0.04) == pytest.approx(-40.0, rel=1e-12)
    assert f_max == pytest.approx(-39.6, rel=1e-12)
    assert ck.rule_flow_pump("active", f_max, 0.04, capped, CURVE) == "active"
    assert ck.rule_flow_pump("active", -39.8, 0.04, capped, CURVE) == "min_speed"
    assert ck.rule_flow_pump("active", f_max + 2 * HTOL, 0.04, capped, CURVE) == "max_speed"


def test_rule_flow_pump_slack_widens_x1_and_n1() -> None:
    assert ck.rule_flow_pump("max_speed", F_MAX, Q_SET, PUMP, CURVE, q_slack=1e-9) == "max_speed"
    assert ck.rule_flow_pump("min_speed", F_MIN, Q_SET, PUMP, CURVE, q_slack=1e-9) == "min_speed"


def test_our_flow_at_the_setpoint_but_for_rounding_is_the_setpoint() -> None:
    """A limit state whose flow is Q_set but for rounding is not a fixed point (ours)."""
    slack = -ck.FLOW_ROUNDING * Q_SET
    below, above = Q_SET * (1 - 1e-12), Q_SET * (1 + 1e-12)
    assert ck.rule_flow_pump("max_speed", F_MAX, below, PUMP, CURVE, slack) == "active"
    assert ck.rule_flow_pump("min_speed", F_MIN, above, PUMP, CURVE, slack) == "active"
    assert ck.rule_flow_pump("max_speed", F_MAX, 0.99 * Q_SET, PUMP, CURVE, slack) == "max_speed"
    assert ck.rule_flow_pump("min_speed", F_MIN, 1.01 * Q_SET, PUMP, CURVE, slack) == "min_speed"


@pytest.mark.parametrize("gain", [F_MIN + 0.1, 0.5 * (F_MIN + F_MAX), F_MAX - 0.1])
def test_implied_speed_closed_form(gain: float) -> None:
    s = ck.implied_speed(CURVE, Q_SET, gain, S_MIN, S_MAX)
    assert S_MIN <= s <= S_MAX
    assert head(s, Q_SET) == pytest.approx(gain, abs=1e-9)


def test_implied_speed_clamps() -> None:
    assert ck.implied_speed(CURVE, Q_SET, F_MAX + 1.0, S_MIN, S_MAX) == S_MAX
    assert ck.implied_speed(CURVE, Q_SET, F_MIN - 1.0, S_MIN, S_MAX) == S_MIN


def test_implied_speed_needs_a_collinear_curve() -> None:
    bent = pump_curve("PB", [(0.0, 40.0), (0.005, 39.0), (0.01, 30.0)])
    with pytest.raises(ValueError, match="collinear"):
        ck.implied_speed(bent, Q_SET, 20.0, S_MIN, S_MAX)


def controlled(project: Project) -> list[Pump]:
    return [c for c in project.components if isinstance(c, Pump) and c.control is not None]


@pytest.mark.parametrize("seed", range(10_000, 10_040))
def test_flow_control_profile_adds_to_the_default_network(seed: int) -> None:
    base, fc = generate(seed), generate(seed, FLOW_CONTROL)
    assert generate(seed, DEFAULT) == base
    # every default component is there (a pump may have gained a control), the curves too
    fc_ids = {c.id: c for c in fc.components}
    for c in base.components:
        assert c.id in fc_ids
        assert c == fc_ids[c.id].model_copy(update={"control": None})
    assert fc.pump_library[: len(base.pump_library)] == base.pump_library
    pumps = controlled(fc)
    assert len(pumps) <= 2
    inserted = [p for p in pumps if p.id not in {c.id for c in base.components}]
    assert len(fc.connections) == len(base.connections) + len(inserted)
    curves = {cv.id: cv for cv in fc.pump_library}
    for p in pumps:
        assert p.control is not None
        assert 0.0 < p.control.min_speed < p.speed <= 1.0
        ck.collinear_curve(curves[p.curve_id])  # the closed-form speed applies
    # through the API JSON, as the corpus loads it
    assert Project.model_validate(fc.model_dump(mode="json", by_alias=True)) == fc


REJECTED_BEFORE = (10_443, 10_532, 11_131, 11_253, 12_108)
"""flow_control seeds whose equal-setpoint copy drew a setpoint at or beyond the new pump's
s_max x_mono (an independent scan with element_laws.x_mono), which the API rejects since the
owner's decision of 2026-10-23 (CONTROLLED_PUMP_SETPOINT). The generator now keeps that pump's
own drawn setpoint there, decided after the draws, so every other seed's network is unchanged
(all 3,000 seeds of both profiles compared as canonical JSON)."""


@pytest.mark.parametrize("seed", REJECTED_BEFORE)
def test_flow_control_profile_draws_no_rejected_setpoint(seed: int) -> None:
    project = generate(seed, FLOW_CONTROL)
    curves = {cv.id: cv for cv in project.pump_library}
    pumps = controlled(project)
    assert pumps
    for p in pumps:
        assert p.control is not None
        assert p.control.setpoint < p.speed * el.x_mono(curves[p.curve_id])
    assert validate_topology(project) == []


def test_control_pins_and_runs() -> None:
    project = generate(10_011, FLOW_CONTROL)
    on = [p.id for p in controlled(project) if p.status == "on"]
    assert on
    pins = em.control_pins(project, {})  # no state reported: at maximum speed (rule A0)
    assert pins == dict.fromkeys(on, "max_speed")
    states = dict.fromkeys(on, "active")
    assert em.control_runs(project, em.control_pins(project, states)) == states
    with pytest.raises(ValueError, match="needs its state"):
        em.control_runs(project, {})


def test_active_substitute_is_the_faq_demand_pair() -> None:
    project = generate(10_011, FLOW_CONTROL)
    on = [p for p in controlled(project) if p.status == "on"]
    p = on[0]
    assert p.control is not None
    others = {o.id: "max_speed" for o in on[1:]}
    wn, lay = em.build_wn(project, {}, {**others, p.id: "active"})
    q = p.control.setpoint
    demand = wn.get_node(f"{p.id}_suction").demand_timeseries_list[0].base_value
    assert demand == q
    assert wn.get_node(f"{p.id}_discharge").demand_timeseries_list[0].base_value == -q
    assert str(wn.get_link(p.id).initial_status).upper().endswith("CLOSED")
    assert lay.fixed_flow == {p.id: q}
    wn2, _ = em.build_wn(project, {}, {**others, p.id: "min_speed"})
    assert wn2.get_link(p.id).base_speed == p.control.min_speed
    assert str(wn2.get_link(p.id).initial_status).upper().endswith("OPEN")


@pytest.mark.parametrize(
    ("seed", "multiple"),
    [
        # a pump at its minimum speed carrying flow, or closed: the closed one's solution has
        # flow in a subset of the other's connections, with other flows there
        (11_285, True),
        # the closed pump's solution has the other's flows where it has flow
        (10_065, False),
    ],
)
def test_control_search_multiple_compares_shared_flows(seed: int, multiple: bool) -> None:
    project = generate(seed, FLOW_CONTROL)
    _, valid = ss.control_search(project)
    a, b = ss.distinct(project, valid)
    assert ss.flowing(b) < ss.flowing(a) or ss.flowing(a) < ss.flowing(b)
    assert ss.multiple(project, [a, b]) is multiple


def write(directory: Path, name: str, data: object) -> None:
    directory.mkdir(exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(data))


def test_compare_ignore(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    before = {"methodVersion": "1.0.0", "pumpResults": {"P1": {"speed": 1.0}}, "x": [1, 2]}
    after = {
        "methodVersion": "1.1.0",
        "pumpResults": {"P1": {"speed": 1.0, "control": None}},
        "x": [1, 2],
    }
    write(a, "p", before)
    write(b, "p", after)
    _, diff = compare.compare_dirs(a, b)
    assert diff == 1
    lines, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "methodVersion"])
    assert diff == 0
    assert "ignored pumpResults.*.control: 1 values in 1 projects" in lines
    # an ignore names whole paths at their depth: a change elsewhere still shows
    write(b, "p", {**after, "x": [1, 3]})
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "methodVersion", "*.1"])
    assert diff == 0
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "methodVersion", "x.0"])
    assert diff == 1
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "version"])
    assert diff == 1


def test_compare_ignore_null(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    before = {"pumpResults": {"P1": {"speed": 1.0}, "P2": {"speed": 1.0, "control": None}}}
    control = {"mode": "flow", "setpoint": 0.01, "state": "max_speed", "setpointAchieved": False}
    write(a, "p", before)
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": None}, "P2": {"speed": 1.0}}})
    lines, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 0
    assert "ignored pumpResults.*.control (null or absent): 2 values in 1 projects" in lines
    # a control result where the old dump has none is a difference (--ignore would hide it)
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": control}, "P2": {"speed": 1.0}}})
    lines, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 1
    assert "ignored pumpResults.*.control (null or absent): 1 values in 1 projects" in lines
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control"])
    assert diff == 0
    # null on one side, a value on the other; and equal values, compared as usual
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0}, "P2": {"speed": 1.0, "control": control}}})
    _, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 1
    write(a, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": control}}})
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": control}}})
    lines, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 0
    assert "ignored pumpResults.*.control (null or absent): 0 values in 0 projects" in lines
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": {**control, "setpoint": 0.02}}}})
    _, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 1
    # list items too
    write(a, "p", {"x": [1, None]})
    write(b, "p", {"x": [1, None]})
    _, diff = compare.compare_dirs(a, b, ignore_null=["x.*"])
    assert diff == 0
    write(b, "p", {"x": [1, 2]})
    _, diff = compare.compare_dirs(a, b, ignore_null=["x.*"])
    assert diff == 1
