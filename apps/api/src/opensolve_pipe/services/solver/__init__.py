"""Hydraulic network solver (Global Gradient Algorithm, D1).

``solve_project`` is the entry point (solver design §10): project -> fluid properties ->
validated solver network -> outer loop around the GGA inner solve -> ``SolvedState``.
It raises ``TopologyError`` for an unsolvable port graph and ``FluidError`` for fluid input
outside the property source's range. Non-convergence is a result (``converged = False``),
not an exception.
"""

from ...models.api import SolveOptions
from ...models.project import Project
from ...models.results import CurvePoint, SolvedState
from .. import design_checks
from ..fluids import FluidError, fluid_properties
from .builder import build_network
from .errors import TopologyError
from .npsh import atmospheric_pressure
from .results import build_solved_state
from .status import run_outer_loop
from .system_curve import (
    FlowRangeError,
    PumpNotFoundError,
    curve_flows,
    default_flow_max,
    system_curve,
    system_curve_points,
)
from .version import METHOD_CHANGELOG, METHOD_VERSION


def _with_design_checks(project: Project, state: SolvedState) -> SolvedState:
    """The project's opt-in design checks on its solved state, and their methods section
    (CLAUDE.md D19); the state itself unchanged without checks."""
    section = design_checks.methods_section(project)
    if section is None:
        return state
    methods = state.trace.methods
    return state.model_copy(
        update={
            "design_checks": design_checks.evaluate(project, state),
            "trace": state.trace.model_copy(
                update={
                    "methods": methods.model_copy(update={"sections": [*methods.sections, section]})
                }
            ),
        }
    )


def solve_project(project: Project, options: SolveOptions | None = None) -> SolvedState:
    """Solve a project. With ``options.include_system_curve`` (the API default; None here
    means no options), every running pump's result also carries its system curve
    (design §13): ``options.system_curve_points`` flows from 0 to 1.2 × its curve's largest
    flow × its speed (a speed-controlled pump's maximum speed), the points whose solve
    converged."""
    fluid = fluid_properties(project.fluid)
    built = build_network(project, fluid)
    p_atm, p_atm_source = atmospheric_pressure(project)
    solver_options = project.settings.solver_options
    outer = run_outer_loop(
        built,
        tolerance=solver_options.tolerance,
        max_iterations=solver_options.max_iterations,
    )
    state = _with_design_checks(project, build_solved_state(built, outer, p_atm, p_atm_source))
    if options is None or not options.include_system_curve or not state.converged:
        return state
    running = [pid for pid, pr in state.pump_results.items() if pr.status == "running"]
    if not running:
        return state
    # A fresh network: the curves' solves reset and reuse its branch laws.
    curve_net = build_network(project, fluid)
    pumps = dict(state.pump_results)
    traces = dict(state.trace.elements)
    for pid in running:
        upper = default_flow_max(curve_net, pid)
        count = options.system_curve_points
        flows = curve_flows(0.0, upper, count)
        points = system_curve_points(
            curve_net,
            pid,
            flows,
            tolerance=solver_options.tolerance,
            max_iterations=solver_options.max_iterations,
            warm=outer,
        )
        curve = [CurvePoint(flow=p.flow, head=p.head) for p in points if p.head is not None]
        skipped = [p.message for p in points if p.message.startswith("not computed")]
        failed = count - len(curve) - len(skipped)
        missing = (
            f"; {failed} have no head (POST /api/v1/system-curve gives each point's reason)"
            if failed
            else ""
        )
        if skipped:  # the request's time budget ran out (budget.py)
            missing += f"; {len(skipped)} were {skipped[0]}"
        pumps[pid] = pumps[pid].model_copy(update={"system_curve": curve})
        trace = traces[pid]
        # The pump's trace defines the curve in any case (trace.SYSTEM_CURVE_EQUATION).
        speed = "s_max" if curve_net.pumps[pid].control is not None else "s"
        traces[pid] = trace.model_copy(
            update={
                "notes": [
                    *trace.notes,
                    f"System curve: {len(curve)} of {count} flows from 0 to {upper:.6g} m³/s "
                    f"(1.2 × the curve's largest flow × {speed}) solved, each starting from the "
                    "solution at the neighbouring flow (the first from this solve; a point "
                    "without a head is solved again from other starts, as the methods summary "
                    f"states){missing}.",
                ],
            }
        )
    return state.model_copy(
        update={
            "pump_results": pumps,
            "trace": state.trace.model_copy(update={"elements": traces}),
        }
    )


__all__ = [
    "METHOD_CHANGELOG",
    "METHOD_VERSION",
    "FlowRangeError",
    "FluidError",
    "PumpNotFoundError",
    "TopologyError",
    "atmospheric_pressure",
    "solve_project",
    "system_curve",
]
