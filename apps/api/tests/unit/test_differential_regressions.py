"""Regressions from the M4 differential test against EPANET 2.2 (random networks).

The project JSON in tests/unit/data/differential is the only input; no expected number comes from
the solver. Each result is checked independently with the reference suite's laws
(tests/reference/network_check): the energy equation of every connection with both heads and the
law of every pump and valve in its reported state, to 1e-6 m, and continuity at every component
to 1e-9 of the largest flow (the reference-case criterion). The networks run in 'swamee_jain'
mode, EPANET's friction formula (CLAUDE.md D7), which ``network_check.epanet_friction_factor``
writes out from EPANET 2.2's source; the status rules themselves are covered by
test_status_rules.py, and the 1915 case's states are compared with EPANET's. Where a section
reports no heads (closed off, or floating: a pump loop that no fixed head reaches), the states
around and inside it are checked with ``tests/reference/free_levels.py``: one set of section
levels must hold them all.
"""

import json
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import scipy.sparse as sp

from opensolve_pipe.models.components import CheckValve, ControlValve, IsolationValve, Pump
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.gga import _solve_linear
from tests.reference import network_check as nc
from tests.reference.free_levels import free_level_problems

DATA = Path(__file__).parent / "data" / "differential"
HEAD_TOL = 1.0e-6  # m, energy and element-law residuals
MASS_RELATIVE = 1.0e-9  # of the largest flow


def _load(seed: int) -> tuple[dict[str, Any], Project]:
    record: dict[str, Any] = json.loads((DATA / f"seed{seed}.json").read_text())
    return record, Project.model_validate(record["project"])


def _states(project: Project, result: SolvedState) -> dict[str, str]:
    """Reported pump statuses and valve states (elements without a result are left out)."""
    states: dict[str, str] = {}
    for c in project.components:
        if isinstance(c, Pump) and c.id in result.pump_results:
            states[c.id] = result.pump_results[c.id].status
        elif c.id in result.valve_results:
            states[c.id] = result.valve_results[c.id].state
    return states


def independent_problems(project: Project, result: SolvedState) -> list[str]:
    assert project.settings.solver_options.friction_method == "swamee_jain"
    model = nc.Model(friction=nc.epanet_friction_factor)
    flows = {cid: link.flow for cid, link in result.link_results.items()}
    egl = {key: node.egl for key, node in result.node_results.items()}
    states = _states(project, result)
    problems = [
        f"energy {cid}: {r:.3g} m"
        for cid, r in nc.energy_residuals(project, flows, egl, model).items()
        if abs(r) > HEAD_TOL
    ]
    for c in project.components:
        if c.id not in states or not isinstance(
            c, Pump | IsolationValve | CheckValve | ControlValve
        ):
            continue
        key_in, key_out = nc.two_port_ends(c)
        if key_in not in egl or key_out not in egl:
            continue
        q = nc.port_inflow(project, key_in, flows)
        h_in, h_out = egl[key_in], egl[key_out]
        kind, r = nc.element_law(project, c, states[c.id], q, h_in, h_out, model)
        if abs(r) > (HEAD_TOL if kind == "head" else MASS_RELATIVE * max(abs(q), 1.0e-12)):
            problems.append(f"law {c.id} ({states[c.id]}): {r:.3g}")
    q_max = max(abs(q) for q in flows.values())
    problems += [
        f"continuity {cid}: {net:.3g} m³/s"
        for cid, net in nc.net_inflow(project, flows).items()
        if abs(net) > MASS_RELATIVE * q_max
    ]
    return problems


def test_a_singular_step_is_detected_without_warnings() -> None:
    """splu raises on an exactly singular matrix, so the step fails the same way whatever the
    warning filters (spsolve only warned, and wntr turns that warning into an error)."""
    singular = sp.csc_matrix(np.array([[1.0, 1.0], [1.0, 1.0]]))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _solve_linear(singular, np.array([1.0, 2.0])) is None
        solved = _solve_linear(sp.csc_matrix(np.array([[2.0, 1.0], [1.0, 3.0]])), np.ones(2))
    assert solved is not None
    assert solved == pytest.approx([0.4, 0.2])


def test_singular_step_falls_back_whatever_the_warning_filters() -> None:
    _, project = _load(712)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = solve_project(project)
    assert result.converged, result.convergence.message
    assert not independent_problems(project, result)


def test_continuity_closes_at_every_component() -> None:
    """Continuity is tested per component as well as per node: a valve's two port residuals
    of opposite sign once left its net inflow at twice the node tolerance."""
    _, project = _load(1771)
    result = solve_project(project)
    assert result.converged, result.convergence.message
    assert not independent_problems(project, result)
    q_max = max(abs(link.flow) for link in result.link_results.values())
    assert result.convergence.max_continuity_residual.value <= MASS_RELATIVE * q_max


def test_a_diverging_active_state_falls_back_to_the_states_its_rules_give() -> None:
    """The first active solve of PSV6 and PRV7 diverges; the rules at its early iterate take
    PSV6 to closed (reverse flow) and PRV7 to open (its inlet below its setting), the state
    EPANET 2.2 settles in. Before, opening the valves one by one in a fixed order returned to
    states already tried and the solve gave up."""
    record, project = _load(1915)
    result = solve_project(project)
    assert result.converged, result.convergence.message
    assert _states(project, result) == record["epanetStates"]
    assert not independent_problems(project, result)


def test_two_prvs_that_flip_together_settle_one_change_at_a_time() -> None:
    _, project = _load(2219)
    result = solve_project(project)
    assert result.converged, result.convergence.message
    assert not independent_problems(project, result)
    assert math.isfinite(result.convergence.max_energy_residual.value)


@pytest.mark.parametrize("seed", [1878, 1966, 2237, 2258, 2313])
def test_prv_and_psv_states_hold_at_some_level_of_the_sections_without_heads(seed: int) -> None:
    """A PRV or PSV inside a floating section, or closed between such a section and another,
    compares its setpoint with the section's free level; the closed elements around the section
    bound that level. Before, such a valve kept whatever state it had, and these networks
    converged in states that no level satisfies (``free_level_problems``)."""
    _, project = _load(seed)
    result = solve_project(project)
    assert result.converged, result.convergence.message
    assert not independent_problems(project, result)
    flows = {cid: link.flow for cid, link in result.link_results.items()}
    egl = {key: node.egl for key, node in result.node_results.items()}
    model = nc.Model(friction=nc.epanet_friction_factor)
    assert not free_level_problems(project, flows, egl, _states(project, result), model)
