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


METHOD_VERSION = "1.1.0"

METHOD_CHANGELOG: list[MethodChange] = [
    {
        "version": "1.0.0",
        "date": "2026-10-21",
        "changes": ["First release of the calculation methods."],
    },
    {
        "version": "1.1.0",
        "date": "2026-10-22",
        "changes": [
            "Adds speed-controlled pumps (flow setpoint): the setpoint flow is imposed in the "
            "network solve and the speed recovered from the affinity laws, within a minimum and "
            "maximum speed. Flows, heads, pressures and statuses of projects without speed "
            "control are unchanged (corpus comparison).",
            "A solve whose pump and valve statuses cycle after a step that changed several of "
            "them at once now changes one status at a time, and goes back to take another change "
            "when it reaches a state again, before it reports that it did not converge. Solves "
            "that converged before give the same results; the methods summary describes the "
            "fallback.",
        ],
    },
]
