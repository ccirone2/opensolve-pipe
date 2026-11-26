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


METHOD_VERSION = "1.6.2"

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
    {
        "version": "1.4.0",
        "date": "2026-10-28",
        "changes": [
            "Adds the orifice plate: ISO 5167-2's permanent pressure loss from the bore and the "
            "Reader-Harris/Gallagher discharge coefficient at D and D/2 tappings for every plate "
            "(held below ISO's lowest Reynolds number, flagged), or an entered coefficient at the "
            "plate's taps moved to D and D/2 tappings by ISO's ratio of the two tap sets' "
            "coefficients, with the differential pressure at a meter's taps and a flashing check "
            "at the vena contracta; a plate whose coefficient at D and D/2 tappings could exceed "
            "1 is refused. Flows, heads, pressures, statuses, traces, messages and system curves "
            "of projects without orifices are unchanged (corpus comparison).",
        ],
    },
    {
        "version": "1.5.0",
        "date": "2026-10-28",
        "changes": [
            "Adds the project library: pipe specs (a material, an inner diameter and an optional "
            "roughness) and loss coefficients (a K at the bore it is stated at, a Cv or a Kv), "
            "each with its source, defined once and referred to by pipe segments, valves and "
            "inline fittings. An element that refers to an entry is solved with exactly the "
            "values it would have with them entered on it: a spec's material, inner diameter and "
            "roughness (a library material without one takes its cited roughness at that inner "
            "diameter), a Cv or Kv converted as one entered there, and a K moved to the element's "
            "bore by K = K₀ (D/d₀)⁴, the same head loss at a given flow. A fitting on a Cv or Kv "
            "entry in laminar flow is flagged, as a valve's Cv or Kv is. Traces name each entry "
            "and its source, and the methods summary lists the library. Flows, heads, pressures, "
            "statuses, traces, messages and system curves of projects without a project library "
            "are unchanged (corpus comparison).",
        ],
    },
    {
        "version": "1.6.0",
        "date": "2026-10-29",
        "changes": [
            "Adds the liquid pressure relief valve: a conventional spring-loaded valve closed "
            "below its set pressure difference, its lift rising linearly with the overpressure (a "
            "convention, flagged; not the typical characteristic's surge and blowdown) to full "
            "lift at set plus overpressure (ASME's 10 % or 3 psi by default, for sets of at least "
            "15 psi), with API 520's liquid equation Q = Kd·A·√(2Δp/ρ) at its lift on the "
            "total-pressure difference between its ports; API 526 letters and effective areas at "
            "API 520's preliminary coefficient 0.65, or a certified area and rated coefficient. "
            "Flows, heads, pressures, statuses, traces, messages and system curves of projects "
            "without relief valves are unchanged (corpus comparison).",
        ],
    },
    {
        "version": "1.6.1",
        "date": "2026-11-03",
        "changes": [
            "A valve, an equipment item, a fitting entry, a connection's fittings or an orifice "
            "plate whose loss coefficient (c of h = cQ|Q|; for a plate, its K at the upper bound "
            "of its discharge coefficient over every flow, so that its K is at least that at "
            "every flow up to rounding) is above half the largest floating-point number, "
            "8.988465674311579·10³⁰⁷, is refused as a topology issue: the slope of its head loss, "
            "2c|Q|, is not a finite number at any flow but zero (for a plate whose K rounding "
            "leaves just below the bound, the slope's term in the change of K with its "
            "discharge coefficient is not), so a solve that evaluates it could only fail. A plate "
            "whose K is past the bound only at the discharge coefficients its law takes, which "
            "need not reach that upper bound, is not refused: a solve that stops on it names it "
            "(below). The refusal holds wherever the element is, as it already did for a "
            "coefficient that is not a finite number, so a project holding one whose slope the "
            "solve never evaluates (for example a valve isolated, locked closed or failed closed, "
            "a PRV or PSV its status rules keep from opening, or an element in a section that "
            "closed valves close off), which solved before, is now refused.",
            "A solve that stops on a value that is not a finite number names in its message each "
            "element whose law gave one, with the flow and its loss coefficient. Inputs at the "
            "schema's bounds that ended in an internal error are now refused (a pipe or an "
            "orifice plate whose size and fluid make its Reynolds number unrepresentable), "
            "reported as not converged (a law that cannot be computed at an iterate) or, in a "
            "converged solve, left out of the trace (a velocity whose square overflows). The "
            "orifice plate's refusal also holds wherever the plate is: a plate on which ISO "
            "5167-2's discharge coefficient is evaluated, in a fluid that makes its Reynolds "
            "number per unit flow, 4ρ/(πDμ), not a finite number, which solved before where the "
            "solve never evaluated the plate, is now refused. So is a plate on ISO 5167-2's "
            "discharge coefficient at corner or flange taps whose meter coefficient fluids cannot "
            "evaluate at those taps' own lowest Reynolds number (at flange tappings 170000 β² D, "
            "which can be far above the loss's): it ended in an internal error wherever the "
            "results gave its reading, and solved before where they did not (a plate closed off), "
            "as a system curve through it did. A relief valve whose trace's slope at zero flow "
            "divided by a product that underflows to zero (a tiny set in a very light liquid) is "
            "solved, with that slope in its trace. Apart from these, flows, heads, pressures, "
            "statuses, traces, messages and system curves are unchanged (corpus comparison).",
        ],
    },
    {
        "version": "1.6.2",
        "date": "2026-11-26",
        "changes": [
            "A pump group's system duty check agrees where the group system curve is vertical at "
            "the duty's flow: where its point there has no rise because a control valve sits at "
            "its switch (valve_at_switch, with the rise with the valve fully open and the side of "
            "it that holds), every rise on that side holds at that flow, and the check agrees "
            "when the duty's rise lies on that side, within 0.5 % of the rise or 0.01 m, "
            "whichever is looser. Its head stays null, and its message says that the curve "
            "passes through the duty on its vertical part, or, for a rise on the other side, "
            "that it does not. Where both duty checks agree, the Group point is the two curves' "
            "crossing, as at the flow control valves' setpoints of the condenser water example. "
            "Apart from a point at a flow where a flow control valve is held open above its "
            "setpoint (the next item), every flow, rise and point of every group curve and group "
            "system curve is unchanged.",
            "A system curve also gives its limit points: one at its flow limit, above which no "
            "steady state carries the forced flow, and one at its floor, below which none does, "
            "where either is positive and finite, lies inside the curve's range, above its least "
            "flow, and inside the window between the floor and the limit, and is at none of its "
            "evenly spaced flows (a floor equal to the limit is one point), each solved alone "
            "after them from the network's initial state. "
            "There a flow control valve across the cut often sits at its switch, where the curve "
            "is vertical from the rise with the valve fully open; where the cut is not the "
            "least, no steady state carries that flow either, and the point has no head and says "
            "why. A flow control valve held open while it passes more than its setpoint is no "
            "longer read as another valve's switch, so a point at such a flow, on the evenly "
            "spaced flows (a group system curve's too) or at a limit, has no head and says why; "
            "on 1.6.1 an evenly spaced flow exactly at such a limit could show a false vertical. "
            "Apart from that, every point at the evenly spaced flows is unchanged, bit for bit; "
            "the group system curve gets no limit points.",
            "An orifice plate's coefficient test (ORIFICE_OUT_OF_RANGE: K/(2gA²) a finite "
            "positive number at every flow) is taken again, where its closed-form bound refuses "
            "the plate, at the least discharge coefficient the plate's law takes at any flow: "
            "the entered value where it is used as entered; for a value entered at corner or "
            "flange taps, that value times the least ratio of the two tap sets' ISO 5167-2 "
            "coefficients over every Reynolds number from the lowest; for ISO 5167-2's own "
            "coefficient, its value at D and D/2 tappings at infinite Reynolds number. A "
            "coefficient entered at corner or flange taps in a band just above where the refusal "
            "began (coefficients of about 10⁻¹⁵⁵ to 10⁻¹⁴⁷ on pipes of 1 mm to 1 m) was "
            "refused and is now accepted, or refused by the slope test instead; no plate is "
            "newly refused. A plate still refused quotes the least coefficient its law takes.",
            "A reservoir or reference node whose fixed head, its surface or port elevation plus "
            "its gauge pressure over ρg, is not a finite number (a density near the least the "
            "schema allows) is refused as a topology issue (BOUNDARY_HEAD_OUT_OF_RANGE), "
            "wherever it is: every solve of such a project diverged at its first iteration, "
            "naming nothing. A goal seek whose bound on such a pressure gives such a head is "
            "refused. An iteration that diverges where every law gives a finite value now names "
            "each element whose energy balance is not a finite number, with the EGLs at its ends "
            "and the component that fixes the head there (nonFiniteBalanceAt).",
            "Where a Newton step's matrix is singular in floating point, the message and the "
            "not-converged flag name each link whose weight 1/(dh/dQ) is lost in rounding where "
            "it alone joins free nodes to every fixed head (for example a valve with a loss "
            "coefficient above about 3·10¹⁹ s²/m⁵ before an assigned flow or a dead end), with "
            "its slope, flow and loss coefficient, and say which iteration's flows they are. The "
            "step is unchanged, so such a solve still does not converge. Apart from these, "
            "flows, heads, pressures, statuses, traces, messages and system curves are "
            "unchanged (corpus comparison).",
        ],
    },
]
