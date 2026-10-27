"""Opt-in design checks (CLAUDE.md D19; proposal design-checks.md): each check's pass, fail
and not-evaluated cases at its boundary, the presets and their citations, the methods section,
and that a project without checks solves and serializes exactly as before.

Limits are set relative to the solve's own values (NPSHa, NPSHr, the flow, the BEP flow, shaft
power, segment velocities), so each boundary is tested exactly: a check is an inequality on
values the solve reports, never a new calculation.
"""

import math
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.design_checks import PRESETS
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services import design_checks
from opensolve_pipe.services.solver import solve_project

from .helpers import connection, custom_fluid, custom_pipe, make_project, reservoir
from .test_m3_solve import P_VAP, RHO, pump, pump_curve

USER = {"kind": "user"}


def line(
    checks: dict[str, Any] | None = None,
    *,
    speed: float = 1.0,
    status: str = "on",
    curve: dict[str, Any] | None = None,
    p_vap: float | None = P_VAP,
) -> Project:
    """R1 (level 2 m) -> L1 (10 m) -> PU -> L2 (200 m) -> R2 (level 20 m)."""
    project = make_project(
        [reservoir("R1", level=2.0), pump(speed=speed, status=status), reservoir("R2", level=20.0)],
        [
            connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
            connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=200.0),
        ],
        pump_library=[curve or pump_curve()],
        fluid=custom_fluid(RHO, 1.0e-3, vapor_pressure=p_vap),
        site_elevation=1200.0,
    )
    if checks is None:
        return project
    data = project.model_dump(mode="json", by_alias=True, exclude_none=True)
    data["settings"]["designChecks"] = checks
    return Project.model_validate(data)


def checks_of(state: SolvedState, check: str) -> list[Any]:
    return [r for r in state.design_checks if r.check == check]


def test_a_project_without_checks_is_unchanged() -> None:
    project = line()
    state = solve_project(project)
    assert state.design_checks == []
    assert "designChecks" not in project.model_dump(mode="json", by_alias=True)["settings"]
    assert [s.title for s in state.trace.methods.sections][-1] != "Design checks"


def test_npsh_margin_at_its_boundary() -> None:
    base = solve_project(line()).pump_results["PU"]
    npsha, npshr = base.npsh_available, base.npsh_required
    assert npsha is not None
    assert npshr is not None
    margin = npsha - npshr  # exactly the available margin: passes (≥)

    def run(**limits: Any) -> Any:
        state = solve_project(line({"npshMargin": {**limits, "source": USER}}))
        [result] = checks_of(state, "npsh_margin")
        return result

    at = run(minimumMargin=margin)
    assert at.outcome == "pass"
    assert at.limits.min == pytest.approx(npshr + margin, rel=1e-15)
    above = run(minimumMargin=math.nextafter(margin, math.inf) * (1 + 1e-12))
    assert above.outcome == "fail"
    ratio = run(minimumRatio=npsha / npshr * (1 + 1e-9))
    assert ratio.outcome == "fail"
    assert "×" in ratio.message
    both = run(minimumMargin=0.1, minimumRatio=1.0)
    assert both.outcome == "pass"
    assert both.limits.min == pytest.approx(max(npshr + 0.1, npshr), rel=1e-15)
    assert both.message.startswith(f"NPSHa {npsha:.6g} m ≥")
    assert run().outcome == "not_evaluated"


def test_npsh_margin_is_not_evaluated_without_its_values() -> None:
    check = {"npshMargin": {"minimumMargin": 1.0, "source": USER}}
    bare = {k: v for k, v in pump_curve().items() if k != "npshrCurve"}
    reasons = {
        "no NPSHr": solve_project(line(check, curve=bare)),
        "no p_vap": solve_project(line(check, p_vap=None)),
        "off": solve_project(line(check, status="off")),
    }
    messages = {k: checks_of(v, "npsh_margin")[0].message for k, v in reasons.items()}
    assert "no NPSHr curve" in messages["no NPSHr"]
    assert "no NPSHa" in messages["no p_vap"]
    assert messages["off"] == "not evaluated: the pump is off"
    assert all(checks_of(v, "npsh_margin")[0].outcome == "not_evaluated" for v in reasons.values())


@pytest.mark.parametrize("speed", [1.0, 0.8])
def test_operating_region_is_the_flow_over_the_bep_flow_at_speed(speed: float) -> None:
    base = solve_project(line(speed=speed)).pump_results["PU"]
    bep = base.best_efficiency_point
    assert bep is not None
    ratio = base.operating_flow / bep.flow

    def outcome(low: float, high: float) -> Any:
        region = {"preferredMin": low, "preferredMax": high, "source": USER}
        [result] = checks_of(
            solve_project(line({"operatingRegion": region}, speed=speed)), "operating_region"
        )
        return result

    inside = outcome(ratio, ratio * 1.5)
    assert inside.outcome == "pass"  # the bound itself passes
    assert inside.value == pytest.approx(ratio, rel=1e-15)
    assert outcome(ratio * (1 + 1e-9), ratio * 2).outcome == "fail"
    assert outcome(ratio * 0.5, ratio * (1 - 1e-9)).outcome == "fail"
    assert f"running speed {speed:g}" in inside.message


def test_manufacturer_data_is_checked_with_the_operating_region() -> None:
    region = {"operatingRegion": {"preferredMin": 0.1, "preferredMax": 5.0, "source": USER}}
    base = solve_project(line(speed=0.8)).pump_results["PU"]
    rated = base.operating_flow / 0.8
    assert base.shaft_power is not None
    curve = {
        **pump_curve(),
        "allowableOperatingRegion": {"flowMin": rated, "flowMax": rated * 1.2},
        "minimumContinuousStableFlow": rated * 0.5,
        "minimumThermalFlow": rated * (1 + 1e-9),
        "motorRatedPower": base.shaft_power,
    }
    state = solve_project(line(region, speed=0.8, curve=curve))
    by_check = {r.check: r for r in state.design_checks}
    assert by_check["allowable_region"].outcome == "pass"  # flowMin itself passes
    assert by_check["minimum_flow"].outcome == "fail"  # the larger minimum, the thermal one
    assert by_check["minimum_flow"].limits.min == pytest.approx(rated * (1 + 1e-9), rel=1e-15)
    assert "minimum thermal flow" in by_check["minimum_flow"].message
    assert by_check["motor_power"].outcome == "pass"  # equal to the rating passes
    assert by_check["motor_power"].source == "manufacturer data (user)"
    # Without the manufacturer data, those checks are not listed.
    plain = solve_project(line(region, speed=0.8))
    assert {r.check for r in plain.design_checks} == {"operating_region"}


def test_operating_region_without_a_bep_says_why() -> None:
    region = {"operatingRegion": {"preferredMin": 0.7, "preferredMax": 1.2, "source": USER}}
    rising = {
        **pump_curve(),
        "efficiencyCurve": [{"flow": 0.0, "efficiency": 0.2}, {"flow": 0.03, "efficiency": 0.7}],
    }
    [result] = checks_of(solve_project(line(region, curve=rising)), "operating_region")
    assert result.outcome == "not_evaluated"
    assert "highest point is at an end" in result.message


def test_pipe_velocity_names_the_pipes_outside() -> None:
    base = solve_project(line())
    v1 = abs(base.link_results["L1"].segments[0].velocity)

    def run(**limits: Any) -> dict[str, Any]:
        state = solve_project(line({"pipeVelocity": {**limits, "source": USER}}))
        return {r.connection_id: r for r in checks_of(state, "pipe_velocity")}

    ok = run(maximum=v1)
    assert ok["L1"].outcome == "pass"  # equal to the maximum passes
    fast = run(maximum=v1 * (1 - 1e-9))
    assert fast["L1"].outcome == "fail"
    # Just past the limit: as many digits as tell the two apart (never "2.13301 above 2.13301").
    shown = re.fullmatch(r"\|v\| (\S+) m/s in pipe 1 above (\S+) m/s", fast["L1"].message)
    assert shown is not None
    assert shown[1] != shown[2]
    assert float(shown[1]) == pytest.approx(v1, rel=2e-10)
    assert float(shown[2]) == pytest.approx(v1 * (1 - 1e-9), rel=2e-10)
    assert (fast["L1"].pipe_index, fast["L1"].pipes_outside) == (0, [0])
    assert ok["L1"].pipes_outside == []
    slow = run(minimum=v1 * (1 + 1e-9))
    assert slow["L1"].outcome == "fail"
    assert "below" in slow["L1"].message
    assert list(run()) == ["L1", "L2"]  # connection order; no limit: not evaluated
    assert run()["L1"].outcome == "not_evaluated"


def test_pipe_velocity_names_each_pipe_of_a_connection() -> None:
    """L2 as two pipes, the second at half the bore (four times the velocity): the result is
    the connection's, with the pipes outside as data (0-based) and words (from 1)."""
    two = [custom_pipe(100.0, 0.1, 4.5e-5), custom_pipe(100.0, 0.05, 4.5e-5)]
    base = line()
    data = base.model_dump(mode="json", by_alias=True, exclude_none=True)
    data["connections"][1]["piping"]["pipes"] = two
    v = [
        abs(s.velocity)
        for s in solve_project(Project.model_validate(data)).link_results["L2"].segments
    ]
    assert v[1] == pytest.approx(4 * v[0], rel=1e-12)

    def run(**limits: Any) -> Any:
        data["settings"]["designChecks"] = {"pipeVelocity": {**limits, "source": USER}}
        state = solve_project(Project.model_validate(data))
        return {r.connection_id: r for r in checks_of(state, "pipe_velocity")}["L2"]

    one = run(maximum=(v[0] + v[1]) / 2)
    assert (one.outcome, one.pipe_index, one.pipes_outside) == ("fail", 1, [1])
    assert one.message == f"|v| {v[1]:.6g} m/s in pipe 2 above {(v[0] + v[1]) / 2:.6g} m/s"
    both = run(maximum=v[0] / 2)
    assert (both.pipe_index, both.pipes_outside) == (1, [0, 1])
    assert both.message.endswith("(pipes outside: 1, 2)")
    slow = run(minimum=(v[0] + v[1]) / 2)
    assert (slow.value, slow.pipe_index, slow.pipes_outside) == (v[0], 0, [0])
    within = run(minimum=v[0], maximum=v[1])
    assert within.outcome == "pass"
    assert (
        within.message
        == f"|v| from {v[0]:.6g} to {v[1]:.6g} m/s, within [{v[0]:.6g}, {v[1]:.6g}] m/s"
    )
    low_only = run(minimum=v[0])
    assert low_only.message.endswith(f"≥ {v[0]:.6g} m/s")
    assert (low_only.value, low_only.pipe_index) == (v[0], 0)  # the slowest, against a minimum
    assert (within.value, within.pipe_index) == (v[1], 1)  # the fastest, against a maximum


def test_presets_are_published_with_their_citations() -> None:
    client = TestClient(app, client=("198.51.100.242", 50000))
    schema = client.get("/openapi.json").json()["components"]["schemas"]["DesignChecks"]
    presets = {p["id"]: p for p in schema["x-design-check-presets"]}
    assert presets["api610_por"]["values"] == {"preferredMin": 0.7, "preferredMax": 1.2}
    assert presets["hi961_2012_general"]["values"] == {"minimumRatio": 1.1, "minimumMargin": 1.0}
    assert all("as quoted by" in p.citation or "as reproduced by" in p.citation for p in PRESETS)
    preset = {"kind": "preset", "preset": "api610_por"}
    project = line(
        {"operatingRegion": {"preferredMin": 0.7, "preferredMax": 1.2, "source": preset}}
    )
    state = solve_project(project)
    assert checks_of(state, "operating_region")[0].source == presets["api610_por"]["citation"]
    section = state.trace.methods.sections[-1]
    assert section.title == "Design checks"
    assert section.references == [presets["api610_por"]["citation"]]


def test_no_checks_when_the_solve_did_not_converge() -> None:
    project = line({"pipeVelocity": {"maximum": 1.0, "source": USER}})
    state = solve_project(project)
    assert state.design_checks
    assert design_checks.evaluate(project, state.model_copy(update={"converged": False})) == []


def test_the_endpoint_returns_checks_and_never_echoes_a_bad_limit() -> None:
    client = TestClient(app, client=("198.51.100.243", 50000))
    project = line({"npshMargin": {"minimumMargin": 1.0, "source": USER}})
    body = project.model_dump(mode="json", by_alias=True, exclude_none=True)
    solved = client.post("/api/v1/solve", json={"project": body}).json()["solvedState"]
    [result] = solved["designChecks"]
    assert set(result) == {
        "check", "componentId", "connectionId", "outcome", "value", "pipeIndex", "pipesOutside",
        "limits", "unit", "source", "message",
    }  # fmt: skip
    body["settings"]["designChecks"] = {
        "operatingRegion": {"preferredMin": 1.3, "preferredMax": 1.2, "source": USER}
    }
    bad = client.post("/api/v1/solve", json={"project": body})
    assert bad.status_code == 400
    assert "1.3" not in bad.text


def _settings_error(checks: dict[str, Any]) -> str:
    body = line().model_dump(mode="json", by_alias=True, exclude_none=True)
    body["settings"]["designChecks"] = checks
    client = TestClient(app, client=("198.51.100.244", 50000))
    response = client.post("/api/v1/solve", json={"project": body})
    assert response.status_code == 400, response.text
    return response.text


def test_a_preset_source_labels_only_its_own_check_and_values() -> None:
    """D19: a preset only fills limits in. A preset of another check, a preset's source on
    limits that are not its own, and any preset on the velocity check (none exists) are 400,
    never quoting the values sent."""
    api610 = {"kind": "preset", "preset": "api610_por"}
    hi = {"kind": "preset", "preset": "hi961_2012_general"}
    _settings_error({"npshMargin": {"minimumMargin": 9.25, "source": api610}})
    _settings_error({"operatingRegion": {"preferredMin": 0.7, "preferredMax": 1.2, "source": hi}})
    _settings_error({"pipeVelocity": {"maximum": 2.75, "source": api610}})
    changed = _settings_error(
        {"operatingRegion": {"preferredMin": 0.65, "preferredMax": 1.2, "source": api610}}
    )
    assert "0.65" not in changed
    _settings_error({"npshMargin": {"minimumRatio": 1.1, "source": hi}})  # one value missing
    # Exactly the preset's values: accepted, and cited.
    exact = {"preferredMin": 0.7, "preferredMax": 1.2, "source": api610}
    [result] = checks_of(solve_project(line({"operatingRegion": exact})), "operating_region")
    assert result.source == PRESETS[0].citation


def test_no_check_present_is_no_design_checks() -> None:
    project = line({})
    assert project.settings.design_checks is None
    assert "designChecks" not in project.model_dump(mode="json", by_alias=True)["settings"]
    state = solve_project(project)
    assert state.design_checks == []
    assert all(s.title != "Design checks" for s in state.trace.methods.sections)


def test_a_check_without_limits_says_so_in_the_methods() -> None:
    project = line({k: {"source": USER} for k in ("npshMargin", "operatingRegion", "pipeVelocity")})
    items = solve_project(project).trace.methods.sections[-1].items
    assert items[1] == (
        "NPSH margin: on, with no limit set, so each pump is listed as not evaluated."
    )
    assert items[2].startswith(
        "Operating region: on, with no limit set, so each pump's Q/Q_BEP is listed as not "
        "evaluated; with it, the curve's manufacturer data"
    )
    assert items[3] == (
        "Pipe velocity: on, with no limit set, so each connection is listed as not evaluated."
    )
    assert not any("no limit set." in i and "≥" in i for i in items)


def test_equal_minimum_flows_name_the_stable_flow() -> None:
    region = {"operatingRegion": {"preferredMin": 0.1, "preferredMax": 5.0, "source": USER}}
    curve = {**pump_curve(), "minimumContinuousStableFlow": 0.004, "minimumThermalFlow": 0.004}
    [result] = checks_of(solve_project(line(region, curve=curve)), "minimum_flow")
    assert "minimum continuous stable flow" in result.message
