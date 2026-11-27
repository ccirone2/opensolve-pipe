"""``scripts/check_deployment.py``, the checks the deploy workflow runs before a revision serves
(CLAUDE.md D25; TSD §11.4), run against the app itself through a test client: a deployment of
the commit passes every check, and each thing a wrong deployment gets wrong fails its own."""

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe import source
from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver.version import METHOD_VERSION

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_deployment.py"
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
REPO = "https://github.com/ccirone2/opensolve-pipe"
SITE = "http://localhost:5173"
"""The origin the app allows without CORS settings (``main.cors_settings``'s default)."""


@pytest.fixture(scope="module")
def check() -> Iterator[ModuleType]:
    # A script, not a package: loaded from its path (as test_record_history does).
    spec = importlib.util.spec_from_file_location("check_deployment", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@pytest.fixture
def deployed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app as an image built from SHA serves it (test_source.py's way)."""
    monkeypatch.setattr(source, "COMMIT", SHA)
    monkeypatch.setattr(source, "SOURCE_URL", f"{REPO}/tree/{SHA}")
    monkeypatch.setattr(source, "LICENSE_URL", f"{REPO}/blob/{SHA}/LICENSE")


def run(check: ModuleType, commit: str, origins: list[str], version: str) -> list[str]:
    client = TestClient(app, client=("198.51.119.1", 50000))

    def request(
        method: str, path: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, dict[str, str], bytes]:
        response = client.request(
            method, path, headers=headers, content=body, follow_redirects=False
        )
        return (
            response.status_code,
            {k.lower(): v for k, v in response.headers.items()},
            response.content,
        )

    lines: list[str] = check.checks(request, commit, origins, version)
    return lines


def failed(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("FAIL")]


def test_a_deployment_of_the_commit_passes_every_check(check: ModuleType, deployed: None) -> None:
    lines = run(check, SHA, [SITE], METHOD_VERSION)
    assert lines == [
        "ok: /health",
        "ok: /docs is off",
        "ok: /api/v1/about",
        "ok: /source",
        f"ok: CORS preflight from {SITE}",
        "ok: a solve",
    ]


def names(lines: list[str]) -> list[str]:
    """The names of the checks that failed."""
    return [line.split(":")[1].strip() for line in failed(lines)]


def test_another_commit_fails_about_and_source(check: ModuleType, deployed: None) -> None:
    assert names(run(check, OTHER, [], METHOD_VERSION)) == ["/api/v1/about", "/source"]


def test_an_image_that_records_no_commit_fails_them_too(check: ModuleType) -> None:
    if source.COMMIT is not None:
        pytest.skip("SOURCE_COMMIT is set in this environment")
    assert len(failed(run(check, SHA, [], METHOD_VERSION))) == 2


def test_an_origin_the_api_does_not_allow_fails_its_preflight(
    check: ModuleType, deployed: None
) -> None:
    lines = run(check, SHA, [SITE, "https://elsewhere.example"], METHOD_VERSION)
    assert failed(lines) == ["FAIL: CORS preflight from https://elsewhere.example: 400 None"]


def test_another_method_version_fails_about_and_the_solve(
    check: ModuleType, deployed: None
) -> None:
    assert names(run(check, SHA, [], "0.0.0")) == ["/api/v1/about", "a solve"]


def test_the_method_version_is_this_checkouts(check: ModuleType) -> None:
    assert check.method_version() == METHOD_VERSION


def test_the_solve_check_sends_a_valid_project(check: ModuleType) -> None:
    """The script is standard library only, so its project is written out: the model must still
    take it (a model change that breaks it fails here, not on a deployment)."""
    Project.model_validate(check.SOLVE_PROJECT)


def test_the_script_refuses_a_commit_that_is_not_a_full_hash(check: ModuleType) -> None:
    with pytest.raises(SystemExit) as raised:
        check.main(["https://example.invalid", "--commit", SHA[:7]])
    assert raised.value.code == 2


def test_a_deployment_that_does_not_answer_fails_every_check_without_stopping(
    check: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refused connection (nothing listens on 127.0.0.1:9, the discard port) is status 0 for
    every request, so each check prints its FAIL line and the run exits 1, never a traceback."""
    status, headers, _ = check.http_request("http://127.0.0.1:9", timeout=5)(
        "GET", "/health", {}, None
    )
    assert (status, headers) == (0, {})
    assert check.main(["http://127.0.0.1:9", "--commit", SHA, "--origin", SITE]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines] == ["FAIL"] * 6
