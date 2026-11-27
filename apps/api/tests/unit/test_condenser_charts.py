"""The web app's condenser chart fixture (apps/web/src/lib/utils/__fixtures__/condenser-charts.json,
docs/proposals/open-defects-2.md §2 and §3) is what ``tests/fixtures/condenser_charts.py``
generates now with the real API from the project it holds, so the charts' tests read the
responses the server returns today; and it holds the cases they read: the group system curve's
duty on its vertical part (C2), and the Winter case's limit point on P1's own system curve (C3).
"""

import json
from typing import Any

from tests.fixtures.condenser_charts import (
    GENERATED_BY,
    WEB_FIXTURE,
    committed_project,
    generate,
)
from tests.fixtures.round_off import round_off_differences


def _fresh() -> dict[str, Any]:
    fresh: dict[str, Any] = json.loads(json.dumps(generate(committed_project())))
    return fresh


def test_the_web_fixture_is_current_and_holds_the_cases_read() -> None:
    assert WEB_FIXTURE.exists(), (
        f"{WEB_FIXTURE} is missing: run `pnpm gen:types` in apps/web (scripts/gen-api-types.sh "
        "writes it: cd ../api && uv run --quiet python -m tests.fixtures.condenser_charts)"
    )
    web = json.loads(WEB_FIXTURE.read_text(encoding="utf-8"))
    fresh = _fresh()
    # To round-off: the solver's last bits differ between CPUs (round_off_differences).
    assert round_off_differences(fresh, web) == [], (
        f"{WEB_FIXTURE} is out of date: run `pnpm gen:types` in apps/web"
    )
    assert fresh["generatedBy"] == GENERATED_BY
    cases = fresh["cases"]
    assert list(cases) == ["base", "winter", "basin15", "p6off", "single24"]
    # C2: the base case's group system curve is vertical at the duty, which lies on it.
    system = cases["base"]["systemCurve"]
    [at] = [p for p in system["systemPoints"] if p["isDuty"]]
    assert (at["head"], at["reason"], at["openHeadBound"]) == (None, "valve_at_switch", "lower")
    assert (system["systemDutyCheck"]["agrees"], system["systemDutyCheck"]["head"]) == (True, None)
    # C3: P1's own system curve in the Winter case has its limit point at F1's setpoint, between
    # two grid flows; the single-line case's limit is a grid flow, so it has none.
    winter = cases["winter"]["pumpSystemCurve"]
    [limit] = winter["limitPoints"]
    assert limit["flow"] not in [p["flow"] for p in winter["points"]]
    assert (limit["head"], limit["reason"], limit["openHeadBound"]) == (
        None,
        "valve_at_switch",
        "lower",
    )
    assert cases["single24"]["pumpSystemCurve"]["limitPoints"] == []
