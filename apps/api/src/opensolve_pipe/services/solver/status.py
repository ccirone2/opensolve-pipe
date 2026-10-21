"""Outer loop: link statuses and branch head offsets around the GGA inner solve (design §5).

repeat (at most 30 times, build-v1.md §3):
    inner GGA solve with the current link modes and branch offsets
    update pump / check-valve / control-valve statuses and branch offsets from Q and H
until nothing changed

In M2 nothing changes: there are no status-driven elements yet, and the only branch loss
model is 'ideal' (zero offsets), so the loop runs once. M3 adds the status logic, the
Crane branch offsets and oscillation detection.
"""

from dataclasses import dataclass

from ...models.components import TeeBranch, WyeBranch
from .builder import BuiltNetwork
from .gga import GgaResult, solve_gga
from .network import NORMAL, LinkState

MAX_OUTER_ITERATIONS = 30
"""Cap on status / branch-offset iterations (build-v1.md §3 decision table)."""


@dataclass
class OuterLoopResult:
    gga: GgaResult
    states: list[LinkState]
    outer_iterations: int
    inner_iterations: int
    converged: bool
    oscillating_components: list[str]
    message: str


def _check_supported(built: BuiltNetwork) -> None:
    crane = sorted(
        c.id
        for c in built.components.values()
        if isinstance(c, TeeBranch | WyeBranch) and c.loss_model == "crane"
    )
    if crane:
        raise NotImplementedError(
            f"branch component(s) {', '.join(crane)} use lossModel 'crane', whose flow-split "
            "K-factors arrive in milestone M3; use lossModel 'ideal' until then"
        )


def initial_states(built: BuiltNetwork) -> list[LinkState]:
    """Every link starts NORMAL. (M3: pumps 'off', isolated and locked-closed valves CLOSED.)"""
    return [NORMAL for _ in built.network.links]


def _update_statuses(built: BuiltNetwork, result: GgaResult, states: list[LinkState]) -> bool:
    """Apply the status rules (design §5.1-5.3); True if any status changed. None in M2."""
    return False


def _update_branch_offsets(built: BuiltNetwork, result: GgaResult) -> bool:
    """Recompute branch head offsets (design §5.4); True if any changed. 'ideal' keeps 0."""
    return False


def run_outer_loop(
    built: BuiltNetwork, *, tolerance: float, max_iterations: int
) -> OuterLoopResult:
    _check_supported(built)
    states = initial_states(built)
    flows = None
    inner = 0
    result: GgaResult | None = None
    for outer in range(1, MAX_OUTER_ITERATIONS + 1):
        result = solve_gga(
            built.network,
            states,
            tolerance=tolerance,
            max_iterations=max_iterations,
            initial_flows=flows,
        )
        inner += result.iterations
        if not result.converged:
            return OuterLoopResult(result, states, outer, inner, False, [], result.message)
        changed = _update_statuses(built, result, states)
        changed = _update_branch_offsets(built, result) or changed
        if not changed:
            message = f"converged: {inner} Newton iterations in {outer} outer iteration(s)"
            return OuterLoopResult(result, states, outer, inner, True, [], message)
        flows = result.flows
    assert result is not None
    return OuterLoopResult(
        result,
        states,
        MAX_OUTER_ITERATIONS,
        inner,
        False,
        [],
        f"statuses still changing after {MAX_OUTER_ITERATIONS} outer iterations",
    )
