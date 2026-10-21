"""Run every reference case through the solver (CLAUDE.md D6, design §9).

Pass criteria (D6): flows, heads and pressures within 0.5 % of the reference, or the absolute
floor, whichever is looser: 1e-9 m³/s for flows (the solver's flow tolerance scale), 0.01 m for
EGL, ρ·g·0.01 m for pressures. Mass balance must close at every non-boundary component, checked
here from the link results alone, independently of the solver's own residual report.

An EGL tolerance of 0.5 % of the head itself depends on the datum and can exceed a connection's
loss, so the head loss of every connection whose two ports have expected EGLs is also checked,
EGL(from) − EGL(to) within 0.5 % of the expected difference or 0.01 m (still D6, datum-free).
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from tests.reference.case_format import case_files, read_case
from tests.reference.derivations import G

RELATIVE = 0.005
FLOW_FLOOR = 1.0e-9  # m³/s
HEAD_FLOOR = 0.01  # m
PROPERTY_RELATIVE = 1.0e-6  # fluid properties are inputs or CoolProp lookups, not iterated
MASS_BALANCE_RELATIVE = 1.0e-9  # of the largest flow
BOUNDARY_TYPES = ("reservoir", "reference_node")

CASES = case_files()


def _within(actual: float, expected: float, floor: float) -> bool:
    return abs(actual - expected) <= max(RELATIVE * abs(expected), floor)


def _failures(
    label: str, actual: dict[str, float], expected: dict[str, float], floor: float
) -> list[str]:
    return [
        f"{label} {key}: got {actual[key]!r}, expected {value!r}"
        for key, value in expected.items()
        if not _within(actual[key], value, floor)
    ]


def _head_loss_failures(
    project: Project, actual: dict[str, float], expected: dict[str, float]
) -> list[str]:
    failures = []
    for c in project.connections:
        a, b = f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"
        if a in expected and b in expected:
            got, want = actual[a] - actual[b], expected[a] - expected[b]
            if not _within(got, want, HEAD_FLOOR):
                failures.append(f"head loss {c.id}: got {got!r}, expected {want!r}")
    return failures


def _check_flags(result: SolvedState, expected: list[dict[str, str]]) -> list[str]:
    """Every expected flag must be present (design §12); other flags are allowed."""
    missing = []
    for want in expected:
        if not any(
            flag.code == want["code"]
            and want.get("componentId") in (None, flag.component_id)
            and want.get("connectionId") in (None, flag.connection_id)
            for flag in result.flags
        ):
            missing.append(f"missing flag {want}")
    return missing


def test_cases_exist() -> None:
    assert CASES, "no reference cases found in tests/reference/cases"


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_reference_case(case_path: Path) -> None:
    # Imported here so that a missing or broken solver fails these cases, not test collection.
    from opensolve_pipe.services.solver import solve_project

    case: dict[str, Any] = read_case(case_path)
    project = Project.model_validate(case["project"])
    expected = case["expected"]

    result = solve_project(project)

    assert result.converged, result.convergence.message

    fluid = expected["fluid"]
    assert result.fluid.density == pytest.approx(fluid["density"], rel=PROPERTY_RELATIVE)
    assert result.fluid.dynamic_viscosity == pytest.approx(
        fluid["dynamicViscosity"], rel=PROPERTY_RELATIVE
    )

    flows = {cid: link.flow for cid, link in result.link_results.items()}
    assert set(flows) == {c.id for c in project.connections}
    egl = {key: node.egl for key, node in result.node_results.items()}
    pressures = {key: node.pressure for key, node in result.node_results.items()}
    assert set(expected["egl"]) <= set(egl)
    assert set(expected.get("pressures", {})) <= set(pressures)

    failures = (
        _failures("flow", flows, expected["flows"], FLOW_FLOOR)
        + _failures("egl", egl, expected["egl"], HEAD_FLOOR)
        + _failures(
            "pressure",
            pressures,
            expected.get("pressures", {}),
            fluid["density"] * G * HEAD_FLOOR,
        )
        + _head_loss_failures(project, egl, expected["egl"])
        + _check_flags(result, expected.get("flags", []))
    )
    assert not failures, "\n".join(failures)

    # Mass balance from the link results only: net flow into every non-boundary component.
    net: dict[str, float] = defaultdict(float)
    for c in project.connections:
        net[c.to_component_id] += flows[c.id]
        net[c.from_component_id] -= flows[c.id]
    q_max = max(abs(q) for q in flows.values())
    for component in project.components:
        if component.type not in BOUNDARY_TYPES:
            assert abs(net[component.id]) <= MASS_BALANCE_RELATIVE * q_max, component.id

    # The solver's own continuity report must agree (design §4 convergence criterion).
    residual = result.convergence.max_continuity_residual.value
    assert abs(residual) <= MASS_BALANCE_RELATIVE * q_max + 1.0e-14
