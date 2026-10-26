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


METHOD_VERSION = "1.3.0"

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
            "Adds the assigned-flow node: a fixed flow out of (a demand) or into (a supply) the "
            "network at a port, a nodal demand in the network solve, never a fixed-pressure "
            "boundary. A node with a nonzero flow in a part that no reservoir or reference node "
            "reaches through open elements, where the assigned flows do not balance, is reported "
            "as not converged, naming it (balanced flows there are solved, with an undetermined "
            "pressure level; a zero flow is a plug), as is a flow control that alone feeds "
            "assigned flows equal to its setpoint (an undetermined pressure); system curves "
            "count assigned flows in their flow bounds, above and below. Flows, heads, pressures, "
            "statuses and system curves of projects without assigned-flow nodes are unchanged by "
            "it (corpus comparison).",
        ],
    },
    {
        "version": "1.2.0",
        "date": "2026-10-24",
        "changes": [
            "The NOT_CONVERGED flag names where a continuity or energy residual lies "
            "(maxContinuityResidualAt, maxEnergyResidualAt) only where that residual exceeds its "
            "stop tolerance (a residual that is not finite always does), and then the largest "
            "such one; before, it named the node and the link of the largest residuals even when "
            "every residual was within its tolerance or exactly 0 (then the first node or link), "
            "which said nothing about why the solve failed. Where the status and branch-loss "
            "updates keep returning to a state whose solve failed, the convergence report and "
            "the flag give the residuals of that solve, which the message describes; before, "
            "they gave those of the last solve. Only results that did not converge change: in "
            "the corpus of 5,136 projects, the 384 that converge in neither version have no "
            "residual beyond its tolerance, so the 379 of their flags that named a location name "
            "none (the other 5 named none before), and the 17 that end in a failed state report "
            "that state's residuals; their messages are unchanged (corpus comparison).",
            "The energy stop test allows for the round-off of the heads it subtracts: a link "
            "passes when |h(Q) − (H_start − H_end)| ≤ 1e-7 m + 4ε × the largest of |H_start|, "
            "|H_end| and |h(Q)| (ε = 2⁻⁵², the machine epsilon of double precision), where it "
            "was 1e-7 m, less than one unit in the last place of heads from 2²⁹ m (about "
            "5.4e8 m): an inner solve whose iterates reached such heads could stall at that "
            "floor until its iteration limit and be treated as failed (27 main solves and 57 "
            "system-curve solves of the corpus did). The methods summary states the test. A "
            "solve changes only where an iterate passes the new test and failed the old one; in "
            "the corpus of 5,136 projects (system curves included) that happens in 75 projects, "
            "at iterates whose largest head or loss was at least 1.6e7 m, and every other "
            "project is identical but for the methods summary and the flags and reports above. "
            "In those 75, the main solves of 55 take fewer Newton iterations (116,092 in the "
            "corpus, from 118,333; none takes more); 9 end in another valid state, the elements "
            "that change carrying exactly 0 m³/s on each side (fuzz_1446, fuzz_2522, fuzz_586, "
            "fuzzaf_20131, fuzzfc_10302, fuzzfc_10535, fuzzfc_10660, fuzzfc_10775 and "
            "fuzzfc_10931; both states pass the differential test's independent self-check); "
            "the reference case round_off_large_heads, whose heads near 4e9 m no float64 state "
            "brings within 1e-7 m, converges in 5 iterations, to its closed form, where it did "
            "not converge in 100 (the only change in convergence); 3 system-curve points gain a "
            "head (fuzz_2530 and fuzz_686) and none loses one; and every flow and head present "
            "in both is within 4.0e-13 of the project's largest flow and 3.7e-12 m, and every "
            "system-curve head within 3.4e-9 relative, but one of 3.6e-15 m at zero flow that is "
            "now 0 (corpus comparison).",
        ],
    },
    {
        "version": "1.3.0",
        "date": "2026-10-26",
        "changes": [
            "Adds the equipment element: a loss between two ports from a datasheet pressure drop "
            "at a rated flow and the density of the fluid it is rated for, or from a Cv or Kv (a "
            "rated point on water, converted as for valves), at constant K (scaled with the "
            "square of the flow and with density). Flows, heads, pressures, statuses, traces, "
            "messages and system curves of projects without equipment are unchanged (corpus "
            "comparison).",
        ],
    },
]
