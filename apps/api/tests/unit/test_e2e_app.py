"""The e2e suite's API (``tests/e2e_app.py``) differs from the shipped app only in its rate limit.

Checked in a subprocess: importing ``tests.e2e_app`` changes the middleware of the shared
``opensolve_pipe.main.app`` object, which the other tests use as shipped.
"""

import json
import subprocess
import sys
from pathlib import Path

from opensolve_pipe.middleware import RATE_LIMIT_REQUESTS

API_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT = """
import json
from opensolve_pipe.main import app
shipped = [(m.cls.__name__, m.args, m.kwargs) for m in app.user_middleware]
from tests.e2e_app import E2E_RATE_LIMIT_REQUESTS, app as e2e
changed = [(m.cls.__name__, m.args, m.kwargs) for m in e2e.user_middleware]
print(json.dumps({"same_app": e2e is app, "shipped": shipped, "changed": changed,
                  "limit": E2E_RATE_LIMIT_REQUESTS, "built": e2e.middleware_stack is not None}))
"""


def test_only_the_rate_limit_is_raised() -> None:
    out = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    result = json.loads(out.strip().splitlines()[-1])
    assert result["same_app"] is True
    assert result["built"] is False
    shipped, changed = result["shipped"], result["changed"]
    assert [m[0] for m in changed] == [m[0] for m in shipped]
    assert ["RateLimit", [], {}] in shipped
    for before, after in zip(shipped, changed, strict=True):
        if before[0] == "RateLimit":
            assert after == ["RateLimit", [], {"requests": result["limit"]}]
        else:
            assert after == before
    assert result["limit"] > RATE_LIMIT_REQUESTS
