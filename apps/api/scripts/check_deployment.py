"""The checks a deployed API must pass before it serves (CLAUDE.md D25; TSD §11.4 items 1 and 2).

    python3 scripts/check_deployment.py URL --commit SHA [--origin ORIGIN ...]

Run from ``apps/api`` with the standard library only: the deploy workflow
(``.github/workflows/deploy-api.yml``) runs it against the candidate revision's tag URL before
giving it any traffic, and against the service's URL after. By hand it checks any deployment.
Each check prints one line, and the exit status is 1 if any failed:

- ``/health`` answers ``{"status": "healthy"}``, and ``/docs`` is 404 (``API_DOCS`` unset);
- ``/api/v1/about`` names the commit built and the calculation-method version of this checkout
  (``services/solver/version.py``), with its source at that commit (AGPL-3.0 §13);
- ``/source`` redirects (302) to the repository at that commit;
- each ``--origin`` passes the CORS preflight of ``POST /api/v1/solve`` (the site and a preview,
  TSD §11.3);
- a two-reservoir network solves and converges, with that method version.

TSD §11.4's other checks (the client address under the rate limit, the logs, the site in a
browser) need a second network or a person, and stay by hand.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

REPOSITORY = "https://github.com/ccirone2/opensolve-pipe"
"""The source the server links (``opensolve_pipe.source``)."""

VERSION_FILE = Path(__file__).resolve().parents[1] / "src/opensolve_pipe/services/solver/version.py"

SOLVE_PROJECT: dict[str, Any] = {
    "schemaVersion": 1,
    "id": "deployment-check",
    "metadata": {"name": "deployment check", "created": "2026-11-27", "modified": "2026-11-27"},
    "settings": {
        "units": {},
        "siteElevation": 0.0,
        "solverOptions": {"frictionMethod": "colebrook", "maxIterations": 100, "tolerance": 1e-09},
    },
    "fluid": {
        "kind": "custom",
        "name": "check liquid",
        "density": 998.0,
        "dynamicViscosity": 0.001,
    },
    "components": [
        {
            "type": "reservoir",
            "id": "R1",
            "name": "R1",
            "elevation": 0.0,
            "liquidLevel": 10.0,
            "surfacePressure": 0.0,
            "ports": [{"id": "port_1", "nominalSize": 0.1}],
        },
        {
            "type": "reservoir",
            "id": "R2",
            "name": "R2",
            "elevation": 0.0,
            "liquidLevel": 0.0,
            "surfacePressure": 0.0,
            "ports": [{"id": "port_1", "nominalSize": 0.1}],
        },
    ],
    "connections": [
        {
            "id": "L1",
            "fromComponentId": "R1",
            "fromPortId": "port_1",
            "toComponentId": "R2",
            "toPortId": "port_1",
            "piping": {
                "pipes": [
                    {
                        "materialId": "custom",
                        "length": 100.0,
                        "innerDiameter": 0.1,
                        "roughness": 4.5e-05,
                    }
                ],
                "fittings": [],
            },
        }
    ],
    "pumpLibrary": [],
}
"""Two reservoirs 10 m apart joined by 100 m of 0.1 m pipe: the smallest network that solves."""

Response = tuple[int, dict[str, str], bytes]
"""Status, headers (names lowercased) and body."""

Request = Callable[[str, str, dict[str, str], bytes | None], Response]
"""(method, path, headers, body) -> Response: urllib for a URL (``http_request``), or a test
client in the tests."""


def method_version(path: Path = VERSION_FILE) -> str:
    """``METHOD_VERSION`` as this checkout's ``version.py`` writes it."""
    found = re.search(r'^METHOD_VERSION = "([^"]+)"$', path.read_text(encoding="utf-8"), re.M)
    if found is None:
        raise ValueError(f"no METHOD_VERSION in {path}")
    return found.group(1)


def checks(request: Request, commit: str, origins: Sequence[str], version: str) -> list[str]:
    """Run every check against one deployment; one line per check, each ``ok:`` or ``FAIL:``."""
    lines: list[str] = []

    def check(name: str, problem: str | None) -> None:
        lines.append(f"{'FAIL' if problem else 'ok'}: {name}" + (f": {problem}" if problem else ""))

    def get_json(path: str) -> tuple[int, Any]:
        status, _, body = request("GET", path, {}, None)
        try:
            return status, json.loads(body)
        except ValueError:
            return status, None

    status, body = get_json("/health")
    check("/health", None if (status, body) == (200, {"status": "healthy"}) else f"{status} {body}")
    status = request("GET", "/docs", {}, None)[0]
    check("/docs is off", None if status == 404 else f"{status}, not 404")

    status, about = get_json("/api/v1/about")
    expected = {
        "commit": commit,
        "methodVersion": version,
        "source": f"{REPOSITORY}/tree/{commit}",
    }
    got = {k: about.get(k) for k in expected} if isinstance(about, dict) else about
    check("/api/v1/about", None if status == 200 and got == expected else f"{status} {got}")

    status, headers, _ = request("GET", "/source", {}, None)
    location = headers.get("location")
    want = f"{REPOSITORY}/tree/{commit}"
    check("/source", None if (status, location) == (302, want) else f"{status} {location}")

    for origin in origins:
        status, headers, _ = request(
            "OPTIONS",
            "/api/v1/solve",
            {
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            None,
        )
        allowed = headers.get("access-control-allow-origin")
        check(
            f"CORS preflight from {origin}",
            None if (status, allowed) == (200, origin) else f"{status} {allowed}",
        )

    body_bytes = json.dumps({"project": SOLVE_PROJECT}).encode()
    status, _, raw = request(
        "POST", "/api/v1/solve", {"Content-Type": "application/json"}, body_bytes
    )
    try:
        state = json.loads(raw).get("solvedState", {})
    except (ValueError, AttributeError):
        state = {}
    solved = (status, state.get("converged"), state.get("methodVersion"))
    check("a solve", None if solved == (200, True, version) else f"{solved}")
    return lines


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Return a redirect as it is (``/source``'s 302), never follow it."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def http_request(base: str, timeout: float = 60.0) -> Request:
    """A ``Request`` for the deployment at ``base`` (https://…), redirects not followed."""
    opener = urllib.request.build_opener(_NoRedirect)

    def request(method: str, path: str, headers: dict[str, str], body: bytes | None) -> Response:
        req = urllib.request.Request(base.rstrip("/") + path, data=body, method=method)
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with opener.open(req, timeout=timeout) as response:
                return response.status, _lower(response.headers.items()), response.read()
        except urllib.error.HTTPError as error:
            return error.code, _lower(error.headers.items()), error.read()

    return request


def _lower(items: Any) -> dict[str, str]:
    return {key.lower(): value for key, value in items}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url", help="the deployment's base URL, e.g. a Cloud Run tag URL")
    parser.add_argument("--commit", required=True, help="the full commit hash it was built from")
    parser.add_argument("--origin", action="append", default=[], help="a site origin (repeat)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("--commit must be a full 40-character commit hash")
    lines = checks(http_request(args.url), args.commit, args.origin, method_version())
    print("\n".join(lines))
    return 1 if any(line.startswith("FAIL") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
