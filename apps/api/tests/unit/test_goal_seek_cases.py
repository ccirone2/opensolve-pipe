"""The web app's shared goal-seek fixture (apps/web/src/lib/utils/__fixtures__/goal-seek-cases.json,
docs/proposals/goal-seek.md §7.5) is what ``tests/fixtures/goal_seek_cases.py`` generates now with
the real trial builder and goal readers, so the web's mirror (applying the values found, reading
the goals with Compare's readers) is checked against the API's current behaviour; and it covers
what the mirror repeats."""

import json
from pathlib import Path
from typing import Any

from opensolve_pipe.models.goal_seek import GOAL_QUANTITIES
from tests.fixtures.goal_seek_cases import generate

WEB_FIXTURE = (
    Path(__file__).parents[3] / "web" / "src" / "lib" / "utils" / "__fixtures__"
) / "goal-seek-cases.json"


def test_the_fixture_covers_every_kind_of_apply_and_every_quantity() -> None:
    fixture = generate()
    apply: list[dict[str, Any]] = fixture["apply"]
    runs = {"base" if c["scenarioId"] is None else "scenario" for c in apply}
    assert runs == {"base", "scenario"}
    kinds = {(v["kind"], v["field"]) for c in apply for v in c["variables"]}
    assert {("pipe", "length"), ("project", "fluid.temperature")} <= kinds
    assert ("component", "resistance") in kinds
    fields = {o["field"] for c in apply for o in c["overrides"]}
    assert "fluid" in fields  # a temperature inside a whole-fluid override
    replaced = [r for c in apply for r in c["replacedOverrides"]]
    assert any(r is not None for r in replaced)
    assert any(r is None for r in replaced)
    for case in apply:
        assert len(case["overrides"]) == len(case["variables"]) == len(case["values"])
        assert "scenarios" not in case["trial"]
    readings = [r for c in fixture["goals"] for r in c["goals"]]
    assert {r["goal"]["quantity"] for r in readings} == set(GOAL_QUANTITIES)
    assert any(r["value"] is None and r["message"] for r in readings)
    assert all((r["value"] is None) == bool(r["message"]) for r in readings)


def test_the_web_fixture_is_current() -> None:
    assert WEB_FIXTURE.exists(), (
        f"{WEB_FIXTURE} is missing: run `pnpm gen:types` in apps/web (scripts/gen-api-types.sh "
        "writes it: cd ../api && uv run --quiet python -m tests.fixtures.goal_seek_cases)"
    )
    web = json.loads(WEB_FIXTURE.read_text(encoding="utf-8"))
    assert web == json.loads(json.dumps(generate())), (
        f"{WEB_FIXTURE} is out of date: run `pnpm gen:types` in apps/web"
    )
