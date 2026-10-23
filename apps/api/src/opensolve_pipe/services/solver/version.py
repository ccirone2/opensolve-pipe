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
            "control are unchanged by it (corpus comparison).",
            "A solve whose pump and valve statuses cycle after a step that changed several of "
            "them at once now changes one status at a time, and goes back to take another change "
            "when it reaches a state again, before it reports that it did not converge. Solves "
            "that converged before give the same results; the methods summary describes the "
            "fallback.",
            "A speed-controlled pump whose flow setpoint is at or above its maximum speed × "
            "x_mono (twice the flow at which its curve's end tangent reaches zero head) is "
            "rejected as a topology issue (CONTROLLED_PUMP_SETPOINT): no speed in its range can "
            "hold that flow, and two limit states would both satisfy the rules.",
            "System curves: a point with no head while the flow has a way through is solved "
            "again from the initial state and then with the control valves open (unless its "
            "flow exceeds what every way between the pump's sides can pass that way, a cut of "
            "FCVs at their setpoints and one-way elements against the flow, where no steady "
            "state carries it), and the first solve with a head is used, so a pump whose way "
            "out is an FCV, PRV or PSV in series "
            "gets a head at every flow the valve passes fully open (before, the zero-flow point "
            "closed the valve and every later point reported no way through), as does a "
            "zero-flow point whose starting state closed a check valve or another pump around a "
            "side of the pump (at zero flow it may also be open, and that state determines the "
            "head; before, the point reported no way through). A point whose "
            "head is undetermined (a side of the pump on a free pressure level, or a control "
            "valve in series at its switch) now has no head, and each point without one says "
            "whether there is no way through, no steady state, an undetermined head or no "
            "convergence; a zero-flow point that had a head against the solver's arbitrary "
            "reference level (a side of the pump on a free level) now has the head another "
            "start determines, or none. Every other point that had a head is unchanged.",
            "System curves: a point at a series FCV's setpoint flow (exactly, or within the "
            "status rules' Qtol, as an evenly spaced range can sample a setpoint) reports its "
            "undetermined head, the FCV being at its switch: a retry that finds a control valve "
            "at its switch is used, as one that finds a head is, and a point whose flow is the "
            "limit of a cut of FCVs is solved with each FCV of the cut held open; before, such "
            "a point could report that no steady state was found, depending on rounding and on "
            "the points before it.",
        ],
    },
]
