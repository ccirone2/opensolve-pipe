"""Calculation-method version (GOALS §4.3).

Bump METHOD_VERSION whenever a change could alter any solved result (equations, correlations,
data, tolerances), and describe the change in METHOD_CHANGELOG so that a user reopening an old
link is told what changed and why. Never remove changelog entries.
"""

from typing import TypedDict


class MethodChange(TypedDict):
    version: str
    date: str
    changes: list[str]


METHOD_VERSION = "1.0.0"

METHOD_CHANGELOG: list[MethodChange] = [
    {
        "version": "1.0.0",
        "date": "2026-10-21",
        "changes": ["First release of the calculation methods."],
    },
]
