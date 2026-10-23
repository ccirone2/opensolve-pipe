"""Status notes in the trace state what keeps each pump and valve in its final state (M4 review).

A note that gives a rule must be true for the solved values: a closed PRV whose outlet head is
above its setpoint, an open ideal FCV (no head across it) and a dead-headed pump were explained by
rules that did not hold. Every note now writes the inequality that holds with its values,
'lhs = a unit op rhs = b unit'. Over the reference suite, the differential seeds and the review's
networks: every such inequality holds, and its left-hand side restates the reported result.
"""

import json
import re
from pathlib import Path

import pytest

from opensolve_pipe.models.components import CheckValve, ControlValve, Pump
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.solver import solve_project
from tests.reference.case_format import case_files, read_case

DATA = Path(__file__).parent / "data"
PROJECTS = (
    [(p.stem, read_case(p)["project"]) for p in case_files()]
    + [
        (p.stem, json.loads(p.read_text())["project"])
        for p in sorted((DATA / "differential").glob("*.json"))
    ]
    + [(p.stem, json.loads(p.read_text())) for p in sorted((DATA / "review").glob("*.json"))]
)
NUMBER = r"(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)"
INEQUALITY = re.compile(
    rf"([^,:=(]+?) = {NUMBER} (m³/s|m) (≥|>|≤|<) ([^=]+?) = {NUMBER} (m³/s|m)\b"
)
OPS = {
    "≥": lambda a, b, tol: a >= b - tol,
    ">": lambda a, b, tol: a > b - tol,
    "≤": lambda a, b, tol: a <= b + tol,
    "<": lambda a, b, tol: a < b + tol,
}


def _inequalities(note: str) -> list[tuple[str, float, str, str, float]]:
    return [
        (lhs.strip(), float(a), op, rhs.strip(), float(b))
        for lhs, a, _, op, rhs, b, _ in INEQUALITY.findall(note)
    ]


def _restated(project: Project, state: SolvedState, cid: str) -> dict[str, float]:
    """The reported values a state note's left-hand side may restate."""
    comp = next(c for c in project.components if c.id == cid)
    values: dict[str, float] = {}
    if isinstance(comp, Pump):
        pump = state.pump_results[cid]
        values["EGL_d − EGL_s"] = pump.operating_head
        values["Q"] = pump.operating_flow
        return values
    valve = state.valve_results[cid]
    values |= {"Q": valve.flow, "EGL_in − EGL_out": valve.head_loss, "H1 − H2": valve.head_loss}
    inlet, outlet = state.node_results.get(f"{cid}:inlet"), state.node_results.get(f"{cid}:outlet")
    if inlet is not None and outlet is not None:  # absent in a floating section
        values |= {"H1": inlet.egl, "H2": outlet.egl}
    return values


@pytest.mark.parametrize(("name", "data"), PROJECTS, ids=[n for n, _ in PROJECTS])
def test_state_notes_state_inequalities_that_hold(name: str, data: dict[str, object]) -> None:
    project = Project.model_validate(data)
    state = solve_project(project)
    if not state.converged:
        return
    for comp in project.components:
        if not isinstance(comp, Pump | CheckValve | ControlValve):
            continue
        has_result = comp.id in (
            state.pump_results if isinstance(comp, Pump) else state.valve_results
        )
        for note in state.trace.elements[comp.id].notes:
            found = _inequalities(note)
            if not found:
                continue
            assert has_result, (comp.id, note)
            restated = _restated(project, state, comp.id)
            for lhs, a, op, rhs, b in found:
                tol = 1e-9 * max(1.0, abs(a), abs(b))  # 10 significant digits printed
                assert OPS[op](a, b, tol), f"{name}/{comp.id}: {lhs} {a} {op} {rhs} {b}: {note}"
                if lhs in restated:
                    assert a == pytest.approx(restated[lhs], rel=1e-9, abs=1e-9), (comp.id, lhs)


def _notes(name: str, cid: str) -> list[str]:
    path = next(p for p in case_files() if p.stem == name)
    state = solve_project(Project.model_validate(read_case(path)["project"]))
    return state.trace.elements[cid].notes


def test_closed_prv_note_names_the_back_pressure() -> None:
    """prv_closed: H1 = 60 m is above the setpoint head and the outlet head, yet the PRV stays
    closed because the head beyond its outlet (40 m) is above its setpoint head."""
    note = next(n for n in _notes("prv_closed", "PRV1") if n.startswith("State closed"))
    assert "the head beyond its outlet is at or above the setpoint, H2 = 40 m ≥" in note


def test_open_ideal_fcv_note_states_the_flow_below_its_setpoint() -> None:
    project = Project.model_validate(json.loads((DATA / "review" / "rich308.json").read_text()))
    state = solve_project(project)
    note = next(n for n in state.trace.elements["FCV1"].notes if n.startswith("State open"))
    assert "Q = " in note
    assert "< Q_set = " in note
    assert "hml(Q_set)" not in note  # an ideal FCV has no fully open loss to compare with


def test_dead_headed_pump_note_names_the_closed_off_side() -> None:
    project = Project.model_validate(json.loads((DATA / "review" / "rich37.json").read_text()))
    state = solve_project(project)
    trace = state.trace.elements["PU3"]
    note = next(n for n in trace.notes if n.startswith("Held at no flow"))
    assert "dead-headed: its discharge side is closed off" in note
    assert "the suction side's + s² H₀(0)" in note
    assert "exceeds its shutoff head" not in note
    values = {v.name: v.value for v in trace.intermediates}
    shutoff = values["Shutoff head s² H₀(0)"]
    assert values["EGL at the discharge port (closed off: EGL_s + s² H₀(0))"] == pytest.approx(
        values["EGL at the suction port"] + shutoff, rel=1e-15
    )
