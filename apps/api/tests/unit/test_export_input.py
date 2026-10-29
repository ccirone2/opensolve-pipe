"""The web app's shared export fixture (apps/web/src/lib/utils/__fixtures__/export-input.json,
docs/proposals/export.md §7.2) is what ``tests/fixtures/export_input.py`` generates now with the
real API, so the web's export model and its committed workbook are built from the responses the
server returns today; and it holds what the export's tests need."""

import json
from pathlib import Path
from typing import Any

from tests.fixtures.export_input import generate
from tests.fixtures.round_off import round_off_differences

WEB_FIXTURE = (
    Path(__file__).parents[3] / "web" / "src" / "lib" / "utils" / "__fixtures__"
) / "export-input.json"


def _cases(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["name"]: case["input"] for case in fixture["cases"]}


def test_the_fixture_holds_the_cases_the_export_design_names() -> None:
    cases = _cases(generate())
    assert list(cases) == [
        "pump-transfer",
        "scenarios",
        "tee-fallback",
        "design-checks",
        "project-library",
    ]
    for case in cases.values():
        assert case["utcOffsetMinutes"] != 0
        assert len(case["appVersion"]) == 40
        for exported in case["cases"]:
            assert exported["response"]["solvedState"]["converged"]
    pump = cases["pump-transfer"]
    assert pump["cases"][0]["systemCurves"]["P1"]["status"] == "ready"
    assert pump["goalSeek"]["status"] == "done"
    scenarios = cases["scenarios"]
    assert [c["id"] for c in scenarios["cases"]] == [None, "S1", "S2"]
    overrides = [
        record["override"]
        for c in scenarios["cases"]
        for record in (c["response"]["scenario"] or {"overrides": []})["overrides"]
    ]
    assert {"kind": "Cv", "value": 120} in [o["value"] for o in overrides]
    assert any(o["field"] == "flow" and o["value"] < 0 for o in overrides)
    names = [c["name"] for c in scenarios["project"]["components"]]
    assert any("_x0041_" in n and "\r" in n for n in names)
    assert any(n.startswith("=") for n in names)
    ports = {c["id"]: len(c["ports"]) for c in scenarios["project"]["components"]}
    assert ports["R1"] == 2
    tee = cases["tee-fallback"]["cases"][0]["response"]["solvedState"]
    flags = [f["code"] for f in tee["flags"]]
    assert "TEE_PATTERN_FALLBACK" in flags
    checked = cases["design-checks"]["cases"][0]["response"]["solvedState"]["designChecks"]
    assert {r["outcome"] for r in checked} == {"pass", "fail", "not_evaluated"}
    assert {r["check"] for r in checked} == {
        "npsh_margin", "operating_region", "allowable_region", "minimum_flow", "motor_power",
        "pipe_velocity",
    }  # fmt: skip
    # CLAUDE.md D22: pipes, a valve and fittings from the project library, an entry of each list
    # unused, and a scenario that changes a reference
    library = cases["project-library"]
    assert [c["id"] for c in library["cases"]] == [None, "S1"]
    project = library["project"]
    used_specs = {p.get("specId") for c in project["connections"] for p in c["piping"]["pipes"]}
    assert {s["id"] for s in project["pipeLibrary"]} - used_specs == {"PS3"}
    kinds = {e["kind"] for e in project["resistanceLibrary"]}
    assert kinds == {"K", "Cv", "Kv"}
    fittings = [f for c in project["connections"] for f in c["piping"]["fittings"]]
    assert {f.get("resistanceId") for f in fittings} >= {"RS2", "RS3"}
    for exported in library["cases"]:
        sections = exported["response"]["solvedState"]["trace"]["methods"]["sections"]
        assert "Project library" in [s["title"] for s in sections]
    changed = library["cases"][1]["response"]["scenario"]["overrides"]
    assert changed[0]["value"] == {"kind": "library", "id": "RS3"}


def test_the_web_fixture_is_current() -> None:
    assert WEB_FIXTURE.exists(), (
        f"{WEB_FIXTURE} is missing: run `pnpm gen:types` in apps/web (scripts/gen-api-types.sh "
        "writes it)"
    )
    web = json.loads(WEB_FIXTURE.read_text(encoding="utf-8"))
    # To round-off: the solver's last bits differ between CPUs (round_off_differences).
    assert round_off_differences(json.loads(json.dumps(generate())), web) == [], (
        f"{WEB_FIXTURE} is out of date: run `pnpm gen:types` in apps/web"
    )
