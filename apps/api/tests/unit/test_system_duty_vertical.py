"""The system duty check on the group system curve's vertical part (docs/proposals/open-defects-2.md
§3 C2; CLAUDE.md D21, D6).

At the duty's flow a control valve outside the station may sit at its switch: an FCV passing
exactly its setpoint holds that flow with any rise across the station on one side of the rise
with it fully open (the point's ``valve_at_switch``, ``openHead`` and ``openHeadBound``, D10).
There the group system curve is vertical, and the duty's rise is one of the rises that hold when
it lies on the bound's side of ``openHead`` within D6's allowance (0.5 % of the rise or 0.01 m,
whichever is looser): the check agrees, its ``head`` stays null (the rise is undetermined at that
flow), and its message says so. A rise on the other side disagrees, and the message says that.

The networks: ``fcv_outside_project`` (the shared fixture's ``fcv-outside``: PA and PB in parallel
with an FCV on the delivery pipe) with the FCV's setpoint lowered from 0.06 to 0.03 m³/s, below
the flow the pumps deliver with it open, so that it throttles at the duty; and the condenser
example as shipped, whose seven FCVs hold the six pumps' flow (the photo of open-defects-2.md §1).
Every number compared is the API's own (the duty's rise, the point's ``openHead``) or a test input;
the rule's edges are probed on the check itself with rises placed half and twice the allowance
past ``openHead``.
"""

import dataclasses
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pump_groups import PumpGroupDuty
from opensolve_pipe.services import pump_groups
from opensolve_pipe.services.pump_groups import DUTY_HEAD_FLOOR, DUTY_RTOL, group_system_curve
from opensolve_pipe.services.solver.system_curve import PointReason, SystemCurvePointResult
from tests.fixtures import condenser_charts
from tests.fixtures import pump_groups_input as pgi

SETPOINT = 0.03
"""m³/s: the FCV's setpoint, below the 0.0456 m³/s the station passes with it at 0.06 (test
input; the fixture's ``fcv-outside`` duty)."""
CONDENSER_PUMPS = ["P1", "P2", "P3", "P4", "P5", "P6"]
"""The condenser example's pumps, its one station."""


def _throttling() -> dict[str, Any]:
    data = pgi.fcv_outside_project()
    fcv = next(c for c in data["components"] if c["id"] == "FC")
    fcv["setpoint"] = SETPOINT
    return data


def _allowance(rise: float) -> float:
    """D6's allowance on a rise, as the check states it: 0.5 % or 0.01 m, whichever is looser."""
    return max(DUTY_RTOL * abs(rise), DUTY_HEAD_FLOOR)


def test_the_tolerances_are_d6s() -> None:
    assert (DUTY_RTOL, DUTY_HEAD_FLOOR) == (0.005, 0.01)


def test_a_duty_on_the_vertical_part_agrees_with_no_rise() -> None:
    """The FCV holds the station's flow at its setpoint, so the duty's flow is its setpoint and
    the duty's point is at its switch: any rise at or above the open valve's holds there, and the
    solve's rise, with the valve throttling, is above it."""
    sc = group_system_curve(Project.model_validate(_throttling()), ["PA", "PB"])
    assert sc.duty is not None
    assert sc.duty.flow == pytest.approx(SETPOINT, rel=1e-9)
    [at] = [p for p in sc.system_points if p.is_duty]
    assert (at.head, at.reason, at.component_ids, at.open_head_bound) == (
        None,
        "valve_at_switch",
        ["FC"],
        "lower",
    )
    assert at.open_head is not None
    assert math.isfinite(at.open_head)
    assert sc.duty.head > at.open_head + _allowance(sc.duty.head)  # well inside, not at an edge
    check = sc.system_duty_check
    assert check is not None
    assert (check.agrees, check.head) == (True, None)
    message = check.message
    assert message.startswith(
        f"the rest of the network with the station's flow {sc.duty.flow:.6g} m³/s forced from S "
        f"to D leaves the rise undetermined at this flow ({at.message}): "
    )
    assert message.endswith(
        f"any rise at or above {at.open_head:.6g} m holds there, and the solve's rise "
        f"{sc.duty.head:.6g} m is one of them, within 0.5 % or 0.01 m: the group system curve "
        "passes through the duty on its vertical part"
    )
    # The methods summary words the check with the same message.
    assert f"System duty check: {message}." in sc.methods.items


def test_the_api_sends_the_vertical_agreement() -> None:
    """POST /api/v1/pump-group-curve, curve 'system': the same check, its head null."""
    data = _throttling()
    client = TestClient(app, client=("198.51.117.1", 50000))
    response = client.post(
        "/api/v1/pump-group-curve",
        json={"project": data, "pumpIds": ["PA", "PB"], "curve": "system"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    check = body["systemDutyCheck"]
    assert (check["agrees"], check["head"]) == (True, None)
    assert check["message"].endswith(
        "the group system curve passes through the duty on its vertical part"
    )
    [at] = [p for p in body["systemPoints"] if p["isDuty"]]
    assert at["reason"] == "valve_at_switch"
    assert body["duty"]["head"] >= at["openHead"]


def test_the_condenser_example_crosses_on_its_vertical_part() -> None:
    """The example as shipped (open-defects-2.md §1, the photo): its seven FCVs hold the six pumps'
    flow, the duty's point is at F2's switch, and the duty's rise is above the open valves' rise,
    so both checks agree and the Group point is the crossing (D21's rule)."""
    project = Project.model_validate(condenser_charts.committed_project())
    sc = group_system_curve(project, CONDENSER_PUMPS)
    assert sc.duty is not None
    [at] = [p for p in sc.system_points if p.is_duty]
    assert (at.head, at.reason, at.open_head_bound) == (None, "valve_at_switch", "lower")
    assert at.open_head is not None
    assert sc.duty.head >= at.open_head - _allowance(sc.duty.head)
    check = sc.system_duty_check
    assert check is not None
    assert (check.agrees, check.head) == (True, None)
    assert f"any rise at or above {at.open_head:.6g} m holds there" in check.message
    assert f"the solve's rise {sc.duty.head:.6g} m is one of them" in check.message


# ---------------------------------------------------------------- the rule at its edges


def _duty(rise: float) -> PumpGroupDuty:
    return PumpGroupDuty(
        flow=SETPOINT, head=rise, inlet_egl=0.0, members=[], interstage_head_loss=None
    )


def _switch(open_head: float, bound: Any) -> SystemCurvePointResult:
    reason = PointReason("valve_at_switch", ("FC",), open_head=open_head, open_head_bound=bound)
    side = "above" if bound == "lower" else "below"
    message = (
        "the rise across the station is undetermined: at this flow FCV 'FC' passes exactly its "
        "setpoint flow, so the valve could also hold it throttled, with any rise across the "
        f"station at or {side} {open_head:.6g} m (with the valve fully open), and no reservoir or "
        "reference node fixes the pressure between the valve and the station"
    )
    return SystemCurvePointResult(SETPOINT, None, False, message, reason)


RISE = 30.0
"""m: a duty's rise for the edge cases (test input); its allowance is 0.15 m."""


@pytest.mark.parametrize(
    ("bound", "past", "agrees"),
    [
        # 'lower': any rise at or above openHead holds; the rise this far above (+) or below (-)
        ("lower", +5.0, True),
        ("lower", 0.0, True),
        ("lower", -0.5, True),
        ("lower", -2.0, False),
        # 'upper': any rise at or below openHead holds
        ("upper", -5.0, True),
        ("upper", 0.0, True),
        ("upper", +0.5, True),
        ("upper", +2.0, False),
    ],
)
def test_the_side_of_the_open_head_within_d6(bound: str, past: float, agrees: bool) -> None:
    """``past``: how far the duty's rise lies from openHead, in allowances (+: above it)."""
    allowance = _allowance(RISE)
    open_head = RISE - past * allowance
    check = pump_groups._system_duty_check(_duty(RISE), _switch(open_head, bound))
    assert (check.agrees, check.head) == (agrees, None)
    side, other = ("above", "below") if bound == "lower" else ("below", "above")
    holds = f"any rise at or {side} {open_head:.6g} m holds there"
    assert holds in check.message
    if agrees:
        assert check.message.endswith(
            f"{holds}, and the solve's rise {RISE:.6g} m is one of them, within 0.5 % or 0.01 m: "
            "the group system curve passes through the duty on its vertical part"
        )
    else:
        assert check.message.endswith(
            f"{holds}, but the solve's rise {RISE:.6g} m is {other} it by more than 0.5 % or "
            "0.01 m: the duty does not lie on the group system curve's vertical part"
        )


@pytest.mark.parametrize(
    "reason",
    [
        PointReason("valve_at_switch", ("FC",), open_head=math.nan, open_head_bound="lower"),
        PointReason("valve_at_switch", ("FC",), open_head=math.inf, open_head_bound="lower"),
        PointReason("valve_at_switch", ("FC",), open_head=None, open_head_bound="lower"),
        PointReason("valve_at_switch", ("FC",), open_head=20.0, open_head_bound=None),
        PointReason("beyond_limit", ("FC",), limit_flow=SETPOINT, passed_flow=SETPOINT),
    ],
)
def test_no_vertical_part_without_a_finite_open_head_and_a_bound(reason: PointReason) -> None:
    """Without a finite openHead and a bound the point states no range: no rise, as before."""
    point = SystemCurvePointResult(SETPOINT, None, False, "why", reason)
    check = pump_groups._system_duty_check(_duty(RISE), point)
    assert (check.agrees, check.head) == (False, None)
    assert check.message == (
        f"the rest of the network with the station's flow {SETPOINT:.6g} m³/s forced from S to D "
        "has no rise (why), so the group system curve is not shown to pass through the duty"
    )


def test_a_point_with_a_rise_is_compared_as_before() -> None:
    """A rise at the duty's flow is compared with the duty's (a rise 1 m away disagrees)."""
    point = dataclasses.replace(_switch(RISE, "lower"), head=RISE + 1.0, converged=True)
    point = dataclasses.replace(point, message="", reason=None)
    check = pump_groups._system_duty_check(_duty(RISE), point)
    assert (check.agrees, check.head) == (False, RISE + 1.0)
    assert "more than one steady state at this flow" in check.message
