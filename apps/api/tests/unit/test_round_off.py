"""``round_off_differences`` (``tests/fixtures/round_off.py``), the comparer of the committed
fixtures of solver output with a fresh run: what it leaves out, and that it leaves out nothing
else."""

import json
from pathlib import Path
from typing import Any

from tests.fixtures.round_off import ROUND_OFF_ABS, round_off_differences

EXPORT_INPUT = (
    Path(__file__).parents[3] / "web" / "src" / "lib" / "utils" / "__fixtures__"
) / "export-input.json"


def _member(flow: float, beyond: bool) -> dict[str, Any]:
    """A group curve's member point, as ``/pump-group-curve`` gives it (test input)."""
    return {
        "beyondData": beyond,
        "controlState": None,
        "flow": flow,
        "head": 45.0,
        "pumpId": "PA",
        "speed": 1.0,
        "status": "running",
    }


def test_a_pumps_zero_flow_label_is_left_out() -> None:
    """At a group curve's shutoff rise a running pump's flow is round-off around zero, and
    ``beyondData`` compares it with the curve's first point at zero flow: its value is the sign
    of the round-off, which differs between CPUs (CLAUDE.md D13: zero-flow labels are not
    regressions)."""
    kept = _member(5.0e-15, False)
    fresh = _member(-3.0e-16, True)
    assert round_off_differences(fresh, kept) == []
    assert round_off_differences([{"members": [fresh]}], [{"members": [kept]}]) == []


def test_the_export_fixtures_shutoff_point_as_another_cpu_gives_it() -> None:
    """The committed export fixture's ``pump-groups`` case, its group curve's last point: from
    one commit, a CI runner gave PA ``beyondData`` True where this fixture holds False, with
    the flow equal to round-off. That fresh point, with PA's flow below zero by the same
    amount, is the same answer."""
    case = next(
        c for c in json.loads(EXPORT_INPUT.read_text())["cases"] if c["name"] == "pump-groups"
    )
    curve = next(iter(case["input"]["cases"][0]["groupCurves"].values()))["response"]
    kept = curve["points"][-1]
    pa = next(m for m in kept["members"] if m["pumpId"] == "PA")
    assert pa["status"] == "running"
    assert abs(pa["flow"]) <= ROUND_OFF_ABS, "the shutoff rise: PA runs at zero flow"
    fresh = json.loads(json.dumps(kept))
    for member in fresh["members"]:
        if member["pumpId"] == "PA":
            member["flow"] = -member["flow"]
            member["beyondData"] = not member["beyondData"]
    assert round_off_differences(fresh, kept) == []


def test_beyond_data_is_compared_where_the_flow_is_not_zero() -> None:
    """Away from zero flow the label is an answer: a change in it is reported."""
    assert round_off_differences(_member(0.0097, True), _member(0.0097, False)) == [
        "beyondData: True against False"
    ]


def test_beyond_data_is_compared_where_only_one_flow_is_zero() -> None:
    """Only where both answers' flows are zero to round-off is the label left out; the flow
    itself is always compared."""
    assert round_off_differences(_member(1.0e-3, True), _member(5.0e-15, False)) == [
        "beyondData: True against False",
        "flow: 0.001 against 5e-15",
    ]


def test_a_zero_flow_leaves_out_no_other_value() -> None:
    """The status, head, speed and control state of a pump at zero flow are still compared."""
    fresh = _member(0.0, False) | {"status": "no_flow", "head": 46.0}
    assert round_off_differences(fresh, _member(0.0, False)) == [
        "head: 46.0 against 45.0",
        "status: 'no_flow' against 'running'",
    ]
