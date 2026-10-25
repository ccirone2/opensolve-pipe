"""The server offers the source of the commit it runs (AGPL-3.0 §13; source.py, TSD §11.2)."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe import __version__, source
from opensolve_pipe.main import app
from opensolve_pipe.middleware import RATE_LIMITED_PATHS
from opensolve_pipe.services.solver import METHOD_VERSION

API_ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/ccirone2/opensolve-pipe"
SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (SHA, SHA),
        (f" {SHA}\n", SHA),
        ("", None),
        (SHA[:12], None),
        (SHA.upper(), None),
        (SHA + "0", None),
        ("not-a-commit", None),
    ],
)
def test_only_a_full_commit_is_recorded(value: str, expected: str | None) -> None:
    assert source.source_commit({"SOURCE_COMMIT": value}) == expected


def test_unset_records_no_commit() -> None:
    assert source.source_commit({}) is None


def test_links_point_at_the_commit_else_the_repository() -> None:
    assert source.source_links(SHA) == (f"{REPO}/tree/{SHA}", f"{REPO}/blob/{SHA}/LICENSE")
    assert source.source_links(None) == (REPO, f"{REPO}/blob/HEAD/LICENSE")


def test_about_names_the_version_commit_and_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source, "COMMIT", SHA)
    monkeypatch.setattr(source, "SOURCE_URL", f"{REPO}/tree/{SHA}")
    monkeypatch.setattr(source, "LICENSE_URL", f"{REPO}/blob/{SHA}/LICENSE")
    response = TestClient(app).get("/api/v1/about")
    assert response.status_code == 200
    assert response.json() == {
        "name": "OpenSolve Pipe API",
        "version": __version__,
        "methodVersion": METHOD_VERSION,
        "commit": SHA,
        "source": f"{REPO}/tree/{SHA}",
        "license": "AGPL-3.0-or-later",
        "licenseUrl": f"{REPO}/blob/{SHA}/LICENSE",
    }


def test_source_redirects_to_the_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source, "SOURCE_URL", f"{REPO}/tree/{SHA}")
    response = TestClient(app).get("/source", follow_redirects=False)
    # Temporary: the next deployment runs another commit.
    assert response.status_code == 302
    assert response.headers["location"] == f"{REPO}/tree/{SHA}"


def test_without_a_commit_both_name_the_repository() -> None:
    client = TestClient(app)
    if source.COMMIT is not None:
        pytest.skip("SOURCE_COMMIT is set in this environment")
    about = client.get("/api/v1/about").json()
    assert about["commit"] is None
    assert about["source"] == REPO
    assert about["licenseUrl"] == f"{REPO}/blob/HEAD/LICENSE"
    assert client.get("/source", follow_redirects=False).headers["location"] == REPO


def test_neither_is_rate_limited() -> None:
    assert "/api/v1/about" not in RATE_LIMITED_PATHS
    assert "/source" not in RATE_LIMITED_PATHS


def test_the_server_reads_the_commit_from_its_environment() -> None:
    """End to end: the image's ENV SOURCE_COMMIT reaches /api/v1/about (a fresh process, since
    the module reads it once at import)."""
    script = (
        "import json\n"
        "from fastapi.testclient import TestClient\n"
        "from opensolve_pipe.main import app\n"
        "c = TestClient(app)\n"
        "print(json.dumps([c.get('/api/v1/about').json(),"
        " c.get('/source', follow_redirects=False).headers['location']]))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        cwd=API_ROOT,
        env={**os.environ, "SOURCE_COMMIT": SHA},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    about, location = json.loads(out.strip().splitlines()[-1])
    assert about["commit"] == SHA
    assert about["source"] == location == f"{REPO}/tree/{SHA}"


def test_the_image_and_its_build_config_record_the_commit() -> None:
    """The Dockerfile's final stage turns the SOURCE_COMMIT build argument into the variable
    the server reads, cloudbuild.yaml passes it from a substitution with no default (Cloud
    Build refuses a build that leaves it out), and the build context leaves that file out."""
    dockerfile = (API_ROOT / "Dockerfile").read_text()
    final_stage = dockerfile.rsplit("\nFROM ", 1)[1]
    assert re.search(r'^ARG SOURCE_COMMIT=""$', final_stage, re.MULTILINE)
    assert re.search(r'^ENV SOURCE_COMMIT="\$\{SOURCE_COMMIT\}"$', final_stage, re.MULTILINE)
    config = "\n".join(
        line
        for line in (API_ROOT / "cloudbuild.yaml").read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    assert '"--build-arg", "SOURCE_COMMIT=${_SOURCE_COMMIT}"' in config
    assert "substitutions:" not in config  # no defaults
    assert "ALLOW_LOOSE" not in config
    ignored = (API_ROOT / ".dockerignore").read_text().splitlines()
    assert "cloudbuild.yaml" in ignored
