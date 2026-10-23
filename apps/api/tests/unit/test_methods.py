"""Methods-and-assumptions summary of a solve (design §13): the sections, assumptions and
software versions a deliverable needs."""

import CoolProp
import fluids
import numpy as np
import scipy

from opensolve_pipe import __version__
from opensolve_pipe.models.piping import ENTRANCE_TYPES, EXIT_TYPES
from opensolve_pipe.models.results import MethodsSummary
from opensolve_pipe.services.solver import METHOD_VERSION, solve_project
from opensolve_pipe.services.solver.gga import CONTINUITY_RTOL, ENERGY_TOL
from opensolve_pipe.services.solver.status import HTOL, MAX_OUTER_ITERATIONS, QTOL

from .helpers import make_project, two_reservoirs

REQUIRED_SECTIONS = [
    "Network solution",
    "Pipe friction",
    "Minor losses",
    "Branches",
    "Pumps",
    "Valves",
    "Fluid properties",
    "Atmosphere and NPSH",
    "Conventions",
]


def _methods(method: str = "colebrook", **kwargs: object) -> MethodsSummary:
    comps, conns = two_reservoirs()
    return solve_project(make_project(comps, conns, method=method, **kwargs)).trace.methods


def _text(section_title: str, method: str = "colebrook") -> str:
    methods = _methods(method)
    section = next(s for s in methods.sections if s.title == section_title)
    return " ".join(section.items)


def test_sections_versions_and_method_version() -> None:
    methods = _methods()
    assert [s.title for s in methods.sections] == REQUIRED_SECTIONS
    assert methods.method_version == METHOD_VERSION
    assert methods.libraries == {
        "opensolve-pipe": __version__,
        "fluids": fluids.__version__,
        "CoolProp": CoolProp.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }
    for section in methods.sections:
        assert section.items, section.title
    cited = {s.title for s in methods.sections if s.references}
    assert {"Network solution", "Pipe friction", "Minor losses", "Pumps", "Valves"} <= cited


def test_assumptions_cover_the_global_model() -> None:
    text = " ".join(_methods().assumptions).lower()
    for word in (
        "steady",
        "incompressible",
        "isothermal",
        "single-phase",
        "quiescent",
        "check valves",
        "control valves without an entered resistance are ideal",
    ):
        assert word in text, word


def test_assumptions_disclose_entrance_and_exit_losses_at_boundaries() -> None:
    """GOALS §4.2: no loss is added where a pipe meets a reservoir or reference node unless the
    piping has an entrance or exit fitting, and the web app's default fittings are stated."""
    [item] = [a for a in _methods().assumptions if "entrance or exit loss" in a]
    assert item.startswith(
        "No entrance or exit loss is applied where a pipe meets a reservoir or reference node "
        "unless the connection's piping has an entrance fitting ("
    )
    for kind in (*ENTRANCE_TYPES, *EXIT_TYPES):
        assert kind in item
    assert (
        "The web app adds a sharp-edged entrance where new piping leaves a reservoir and an "
        "exit where it enters one (removable), and none at a reference node"
    ) in item


def test_network_section_states_the_tolerances_and_iterations() -> None:
    text = _text("Network solution")
    assert "Todini & Pilati" in text
    assert f"{CONTINUITY_RTOL:g}" in text
    assert f"{ENERGY_TOL:g}" in text
    assert f"at most {MAX_OUTER_ITERATIONS}" in text
    assert "flow tolerance 1e-09" in text
    assert "at most 100 Newton iterations per network solve" in text
    assert "This solve:" in text
    assert "converged." in text


def test_friction_section_follows_the_method() -> None:
    assert "Clamond" in _text("Pipe friction", "colebrook")
    assert "Swamee & Jain" in _text("Pipe friction", "swamee_jain")


def test_pump_valve_and_convention_sections() -> None:
    pumps = _text("Pumps")
    assert "PchipInterpolator" in pumps
    assert "No viscosity correction" in pumps
    assert "affinity laws" in pumps
    assert "System curve" in pumps
    valves = _text("Valves")
    assert f"{HTOL:g} m in head, {QTOL:g} m³/s" in valves
    assert "Cv_to_K" in valves
    conventions = _text("Conventions")
    assert "gauge" in conventions
    assert "datum" in conventions
    assert "HGL" in conventions
    npsh = _text("Atmosphere and NPSH")
    assert "ATMOSPHERE_1976" in npsh
    assert "NPSH" in npsh
    fluid = _text("Fluid properties")
    assert "density 998 kg/m³" in fluid
