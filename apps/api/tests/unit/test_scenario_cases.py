"""The web app's shared scenario fixture (apps/web/src/lib/utils/__fixtures__/scenario-cases.json,
proposal scenario-manager.md §6.16) is what ``tests/fixtures/scenario_cases.py`` generates now
with the real ``apply_scenario`` and request validation, so the client mirror
(``utils/scenarios.ts``) is checked against the API's current behaviour; and it covers every
rule the mirror repeats."""

import json
from pathlib import Path
from typing import Any

from opensolve_pipe.models.scenarios import COMPONENT_FIELDS, PIPE_FIELDS, PROJECT_FIELDS
from tests.fixtures.round_off import round_off_differences
from tests.fixtures.scenario_cases import generate

WEB_FIXTURE = (
    Path(__file__).parents[3] / "web" / "src" / "lib" / "utils" / "__fixtures__"
) / "scenario-cases.json"


def test_the_fixture_covers_every_value_state_and_rule() -> None:
    cases: list[dict[str, Any]] = generate()["cases"]
    kinds = {c["kind"] for c in cases}
    assert kinds == {"applied", "invalid", "not_found", "rejected"}
    fields: set[tuple[str, str]] = set()
    states: set[str] = set()
    for case in cases:
        if case["kind"] != "applied":
            continue
        scenario = next(s for s in case["project"]["scenarios"] if s["id"] == case["scenarioId"])
        for override, record in zip(
            scenario["overrides"], case["expected"]["overrides"], strict=True
        ):
            states.add(record["state"])
            if record["state"] == "applied":
                fields.add((override["kind"], override["field"]))
    names = {f for entries in COMPONENT_FIELDS.values() for f in entries}
    expected = {("component", f) for f in names}
    expected |= {("pipe", f) for f in PIPE_FIELDS} | {("project", f) for f in PROJECT_FIELDS}
    assert fields == expected
    assert states == {"applied", "orphaned", "not_applicable"}
    rejected = " ".join(i["message"] for c in cases if c["kind"] == "rejected" for i in c["issues"])
    for rule in ("set the same value", "a part of it", "have the same id", "at most 30 items"):
        assert rule in rejected, rule


def test_the_web_fixture_is_current() -> None:
    assert WEB_FIXTURE.exists(), (
        f"{WEB_FIXTURE} is missing: run `pnpm gen:types` in apps/web (scripts/gen-api-types.sh "
        "writes it: cd ../api && uv run --quiet python -m tests.fixtures.scenario_cases)"
    )
    web = json.loads(WEB_FIXTURE.read_text(encoding="utf-8"))
    # To round-off: the solver's last bits differ between CPUs (round_off_differences).
    assert round_off_differences(json.loads(json.dumps(generate())), web) == [], (
        f"{WEB_FIXTURE} is out of date: run `pnpm gen:types` in apps/web"
    )
