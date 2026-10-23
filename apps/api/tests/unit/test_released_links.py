"""Released share links keep solving (D2: shared URLs live forever).

The web app keeps one fixture link per released project schema version
(apps/web/src/lib/utils/__fixtures__/schema-vN.txt, never edited) with its JSON
(schema-vN.json); its tests pin the link and check it decodes to that JSON. Here the JSON of
the current schema version is solved, so a solver, topology or model change that stops a
released link from solving fails the API suite. Older versions are upgraded by the web app's
migrations before they reach the API; tests/examples.e2e.ts opens every fixture link in the
browser and solves it.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.project import SCHEMA_VERSION

FIXTURES = Path(__file__).parents[3] / "web" / "src" / "lib" / "utils" / "__fixtures__"
CURRENT = FIXTURES / f"schema-v{SCHEMA_VERSION}.json"


def test_the_current_schema_version_has_a_fixture_link() -> None:
    assert CURRENT.is_file()
    assert (FIXTURES / f"schema-v{SCHEMA_VERSION}.txt").is_file()


def test_the_current_fixture_link_solves() -> None:
    """As the web app solves an opened link: without system curves, then the curve of each
    running pump from POST /system-curve (D10)."""
    project = json.loads(CURRENT.read_text())
    assert project["schemaVersion"] == SCHEMA_VERSION
    client = TestClient(app, client=("198.51.100.250", 50000))
    options = {"includeSystemCurve": False}
    response = client.post("/api/v1/solve", json={"project": project, "options": options})
    assert response.status_code == 200, response.text[:500]
    body = response.json()
    assert body["success"] is True
    assert body["solvedState"]["converged"] is True
    running = [k for k, v in body["solvedState"]["pumpResults"].items() if v["status"] == "running"]
    for pump_id in running:
        curve = client.post("/api/v1/system-curve", json={"project": project, "pumpId": pump_id})
        assert curve.status_code == 200, curve.text[:500]
        assert any(p["head"] is not None for p in curve.json()["points"]), pump_id
