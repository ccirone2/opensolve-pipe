"""The API the web app's Playwright suite runs against (``apps/web/playwright.config.ts``).

It is the app as shipped (``opensolve_pipe.main.app``) with one change: the per-client rate limit
on solves and system curves (``middleware.RATE_LIMIT_REQUESTS`` a minute) is raised. Every test's
browser reaches the API from the same address, and the suite sends more solve and system-curve
requests a minute than one person does: on a fast runner it went over 60 and its last tests got
429 RATE_LIMITED (CI run 40004435327). The one-solve-per-client rule stays as shipped; the suite
runs in one worker for it. The rate limit itself is tested in ``tests/unit``.

This module replaces the middleware entry of the imported app object, before its middleware
stack is built (on the first request), so it is meant to be the server's entry point
(``uvicorn tests.e2e_app:app``), never imported where the shipped app is under test.
"""

from starlette.middleware import Middleware

from opensolve_pipe.main import app
from opensolve_pipe.middleware import RateLimit

E2E_RATE_LIMIT_REQUESTS = 100_000
"""Solve and system-curve requests a minute per client for the e2e suite."""

app.user_middleware = [
    Middleware(RateLimit, requests=E2E_RATE_LIMIT_REQUESTS) if m.cls is RateLimit else m
    for m in app.user_middleware
]

__all__ = ["E2E_RATE_LIMIT_REQUESTS", "app"]
