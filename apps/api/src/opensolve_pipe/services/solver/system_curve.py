"""System curve seen by one pump (design §13, SDD §5.1).

At each flow Q the pump is replaced by a fixed-flow link that carries Q from its suction port to
its discharge port, whatever its own control (a speed-controlled pump's control is replaced
too, CLAUDE.md D11); every other element keeps its own law and status rules (other pumps keep
running, other speed-controlled pumps keep regulating, check and control valves open, close or
throttle as the network drives them), and the network is solved with the usual outer loop.
The system head at Q is the head the pump would have to add there:

    H_sys(Q) = EGL(discharge) − EGL(suction)

which is the pump's operating head where the system curve meets the pump curve. A point whose
solve does not converge, or where the forced flow has no way through (a side of the pump with no
fixed-pressure boundary, so the flow cannot be delivered), has no head. At zero flow with both
sides of the pump in one closed-off section (a pump in a loop behind a closed valve), the head is
the difference of that section's zero-flow heads (``status.closed_off_sections``).

Points not reached before a request's time budget runs out (``budget.py``) have no head
either, and say so.

Default flow range: 0 to 1.2 × the largest flow of the pump curve's points × the speed ratio s
(the curve's flow range at the operating speed, by the affinity laws, plus 20 %); for a
speed-controlled pump, s is its ``speed`` field, its maximum speed.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ...models.components import Pump
from ...models.project import Project
from ..fluids import fluid_properties
from .budget import SolveDeadlineError
from .builder import BuiltNetwork, build_network
from .status import OuterLoopResult, closed_off_sections, run_outer_loop

DEFAULT_RANGE_FACTOR = 1.2
"""The default system curve spans 0 to this × the pump curve's largest flow × s (design §13)."""


class PumpNotFoundError(LookupError):
    """The requested pump id is not a pump of the project (HTTP 404, NOT_FOUND)."""


class FlowRangeError(ValueError):
    """The requested flow range is empty (HTTP 400, VALIDATION_ERROR)."""


@dataclass(frozen=True)
class SystemCurvePointResult:
    flow: float
    """m³/s through the pump, suction -> discharge."""
    head: float | None
    """EGL(discharge) − EGL(suction), m; None when the point has no solution."""
    converged: bool
    message: str
    """Why the point has no head ('' when it converged)."""


def find_pump(project: Project, pump_id: str) -> Pump:
    for comp in project.components:
        if comp.id == pump_id and isinstance(comp, Pump):
            return comp
    raise PumpNotFoundError(f"no pump with id '{pump_id}' in the project")


def default_flow_max(built: BuiltNetwork, pump_id: str) -> float:
    """1.2 × the curve's largest flow × the speed ratio (a speed-controlled pump's maximum
    speed), m³/s (module docstring)."""
    data = built.pumps[pump_id]
    return DEFAULT_RANGE_FACTOR * data.curve.flow_range[1] * data.component.speed


def curve_flows(flow_min: float, flow_max: float, count: int) -> list[float]:
    """``count`` evenly spaced flows from flow_min to flow_max inclusive, m³/s."""
    return [float(q) for q in np.linspace(flow_min, flow_max, count)]


def system_curve_points(
    built: BuiltNetwork,
    pump_id: str,
    flows: Sequence[float],
    *,
    tolerance: float,
    max_iterations: int,
    warm: OuterLoopResult | None = None,
) -> list[SystemCurvePointResult]:
    """Solve the network with pump ``pump_id`` replaced by each fixed flow (module docstring).

    Each point starts from the last converged point (or from ``warm``, a converged solve of
    the same network, for the first): its flows, statuses and branch losses (continuation
    along the curve, ``status._warm_start``). A point that does not converge from there is
    solved again from the network's initial state. The outer loop applies its own branch laws
    to the network, so one built network serves every point."""
    data = built.pumps[pump_id]
    net = built.network
    suction, discharge = net.node_index[data.suction], net.node_index[data.discharge]
    points: list[SystemCurvePointResult] = []
    previous = warm
    for i, q in enumerate(flows):
        try:
            outer = run_outer_loop(
                built,
                tolerance=tolerance,
                max_iterations=max_iterations,
                forced_flows={pump_id: float(q)},
                warm=previous,
            )
            if not outer.converged and previous is not None:
                outer = run_outer_loop(
                    built,
                    tolerance=tolerance,
                    max_iterations=max_iterations,
                    forced_flows={pump_id: float(q)},
                )
        except SolveDeadlineError as exc:
            # The request's time budget ran out: the remaining points are not computed (a
            # client disconnect, SolveCancelledError, stops the whole request instead).
            points += [
                SystemCurvePointResult(float(r), None, False, f"not computed: {exc}")
                for r in flows[i:]
            ]
            break
        if outer.converged:
            previous = outer
        head = float(outer.gga.heads[discharge] - outer.gga.heads[suction])
        if outer.converged and not math.isfinite(head) and q == 0.0:
            section, shift = closed_off_sections(built, outer.gga, outer.states)
            if suction in section and section[suction] == section.get(discharge):
                head = shift[discharge] - shift[suction]
        if not outer.converged:
            points.append(
                SystemCurvePointResult(float(q), None, False, f"not converged: {outer.message}")
            )
        elif data.link_index in outer.gga.starved_links or not math.isfinite(head):
            points.append(
                SystemCurvePointResult(
                    float(q),
                    None,
                    False,
                    "the flow has no way through: a side of the pump reaches no reservoir or "
                    "reference node through open elements",
                )
            )
        else:
            points.append(SystemCurvePointResult(float(q), head, True, ""))
    return points


@dataclass(frozen=True)
class SystemCurve:
    pump_id: str
    points: list[SystemCurvePointResult]
    flow_min: float
    flow_max: float


def system_curve(
    project: Project,
    pump_id: str,
    *,
    flow_min: float = 0.0,
    flow_max: float | None = None,
    num_points: int = 41,
) -> SystemCurve:
    """The system curve of one pump at ``num_points`` evenly spaced flows.

    Raises ``PumpNotFoundError`` for an unknown pump id (checked first), then ``TopologyError``
    / ``FluidError`` as a solve would, and ``FlowRangeError`` when flow_max <= flow_min."""
    find_pump(project, pump_id)
    built = build_network(project, fluid_properties(project.fluid))
    upper = flow_max if flow_max is not None else default_flow_max(built, pump_id)
    if not upper > flow_min:
        raise FlowRangeError(
            "the flow range is empty: flowMax (given, or 1.2 x the pump curve's largest flow x "
            "the speed ratio by default) must be above flowMin"
        )
    options = project.settings.solver_options
    flows = curve_flows(flow_min, upper, num_points)
    points = system_curve_points(
        built,
        pump_id,
        flows,
        tolerance=options.tolerance,
        max_iterations=options.max_iterations,
    )
    return SystemCurve(pump_id, points, flow_min, upper)
