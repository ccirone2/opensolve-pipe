"""The condenser example's chart fixture (docs/proposals/open-defects-2.md §2, C1 and X).

    cd apps/api && uv run python ../web/src/lib/utils/__fixtures__/condenser-charts.record.py \
        PROJECT.json ../web/src/lib/utils/__fixtures__/condenser-charts.json
    cd ../web && pnpm exec prettier --write src/lib/utils/__fixtures__/condenser-charts.json

PROJECT.json is the web's condenserWaterExample() as JSON (utils/examples.ts); the web's test
checks the fixture's project against it, so a changed example asks for the fixture again. Every
response is main's API's, through the real app (``POST /api/v1/solve``, ``/pump-group-curve``
with curves ``group`` and ``system``, ``/system-curve``): nothing in it is computed by web code.
Only what the tests read is kept: the members' PumpResults and flags of each solve, the group
curves' and the pump's system curves' bodies whole, and each case's inputs.

Each case is the shipped project with ``edits`` (component fields set, in order), ``scenarios``
(the project's scenarios replaced, when given) and ``scenarioId`` (the case solved):

- ``base``: the example as shipped, its base case.
- ``winter``: its own Winter case, S1 (P1 alone, F2 to F7 failed closed), with P1's system curve.
- ``basin15``: the base case with the basin's level 15.0 m (the photo's 14.4 m lower curve; its
  group curve's point at the shutoff rise falls at -6.08e-15 m3/s).
- ``p6off``: a status-only case S2 "5 of 6 running", P6 off, as D24's lineups make one; only its
  group curve is kept (its ring: the station duty).
- ``single24``: one pump and one chiller line (P2 to P6 off, F2 to F7 failed closed, no
  scenarios), F1's setpoint the 25th flow of /system-curve's grid (np.linspace(0, 1.58987294928,
  41)[24], the API's default range for P1), with P1's system curve.
"""

import copy
import json
import sys
from typing import Any

import numpy as np
from fastapi.testclient import TestClient

from opensolve_pipe.main import app

PUMPS = ["P1", "P2", "P3", "P4", "P5", "P6"]
GRID = [float(q) for q in np.linspace(0.0, 1.58987294928, 41)]


def _edit(component: str, field: str, value: Any) -> dict[str, Any]:
    return {"componentId": component, "field": field, "value": value}


CASES: dict[str, dict[str, Any]] = {
    "base": {"edits": [], "scenarioId": None},
    "winter": {"edits": [], "scenarioId": "S1", "systemCurveOf": "P1"},
    "basin15": {"edits": [_edit("B1", "liquidLevel", 15.0)], "scenarioId": None},
    # Its ring only: the station duty of its group curve.
    "p6off": {"edits": [], "scenarios": "add", "scenarioId": "S2", "keep": ["groupCurve"]},
    "single24": {
        "edits": [
            *[_edit(p, "status", "off") for p in ["P2", "P3", "P4", "P5", "P6"]],
            *[_edit(f, "status", "failed_closed") for f in ["F2", "F3", "F4", "F5", "F6", "F7"]],
            _edit("F1", "setpoint", GRID[24]),
        ],
        "scenarios": [],
        "scenarioId": None,
        "systemCurveOf": "P1",
        "members": ["P1"],
    },
}

# What a case was solved from, kept with whatever else it keeps.
INPUTS = ("edits", "scenarios", "scenarioId", "memberIds")

P6_OFF = {
    "id": "S2",
    "name": "5 of 6 running",
    "description": "",
    "overrides": [{"kind": "component", "componentId": "P6", "field": "status", "value": "off"}],
}


def _project(base: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    project = copy.deepcopy(base)
    for e in case["edits"]:
        next(c for c in project["components"] if c["id"] == e["componentId"])[e["field"]] = e[
            "value"
        ]
    if case.get("scenarios") == "add":
        project["scenarios"] = [*project["scenarios"], P6_OFF]
    elif "scenarios" in case:
        project["scenarios"] = case["scenarios"]
    return project


def main() -> None:
    with open(sys.argv[1]) as source:
        base = json.load(source)
    client = TestClient(app, client=("192.0.2.247", 50000))
    out: dict[str, Any] = {
        "generatedBy": "apps/web/src/lib/utils/__fixtures__/condenser-charts.record.py",
        "project": base,
        "cases": {},
    }
    for name, case in CASES.items():
        project = _project(base, case)
        scenario = {"scenarioId": case["scenarioId"]} if case["scenarioId"] else {}
        members = case.get("members", PUMPS)
        solve = client.post("/api/v1/solve", json={"project": project, **scenario})
        assert solve.status_code == 200, solve.text
        state = solve.json()["solvedState"]
        assert state["converged"], name
        recorded: dict[str, Any] = {
            "edits": case["edits"],
            **({"scenarios": project["scenarios"]} if "scenarios" in case else {}),
            "scenarioId": case["scenarioId"],
            "memberIds": members,
            "pumpResults": {p: state["pumpResults"][p] for p in members},
            "flags": [f for f in state["flags"] if f.get("componentId") in members],
        }
        if len(members) > 1:
            for curve in ("group", "system"):
                answer = client.post(
                    "/api/v1/pump-group-curve",
                    json={"project": project, "pumpIds": members, "curve": curve, **scenario},
                )
                assert answer.status_code == 200, answer.text
                recorded[f"{curve}Curve"] = answer.json()
        pump = case.get("systemCurveOf")
        if pump:
            answer = client.post(
                "/api/v1/system-curve", json={"project": project, "pumpId": pump, **scenario}
            )
            assert answer.status_code == 200, answer.text
            recorded["pumpSystemCurve"] = answer.json()
        keep = case.get("keep")
        if keep:
            recorded = {k: v for k, v in recorded.items() if k in keep or k in INPUTS}
        out["cases"][name] = recorded
    with open(sys.argv[2], "w") as target:
        json.dump(out, target, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    main()
