"""Methods-and-assumptions summary of a solve (design §13): the sections, assumptions and
software versions a deliverable needs."""

import CoolProp
import fluids
import numpy as np
import scipy

from opensolve_pipe import __version__
from opensolve_pipe.models.piping import ENTRANCE_TYPES, EXIT_TYPES
from opensolve_pipe.models.results import MethodsSummary
from opensolve_pipe.services.solver import METHOD_CHANGELOG, METHOD_VERSION, solve_project
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


STOP_TEST_ITEM_1_1_0 = (
    "Converged when the largest flow change is at most the project tolerance times the largest "
    "flow (plus 1e-14 m³/s), continuity closes at every node and over every component to 1e-09 "
    "x the largest flow + 1e-14 m³/s, and the energy equation holds on every link to 1e-07 m."
)
"""The Network-solution item that states the stop test, as method 1.1.0 printed it."""
ENERGY_ROUNDOFF_SENTENCE = (
    "On each link, 8.88178e-16 x the largest magnitude among the energy grade lines at its two "
    "ends and its head loss is added to that tolerance (4 x 2.22045e-16, the machine epsilon of "
    "double precision): an allowance for the round-off of the heads that the energy residual "
    "subtracts, larger than 1e-07 m only where that magnitude exceeds 1e-07 m divided by that "
    "factor, about 1.1259e+08 m."
)
"""Method 1.2.0's sentence on the energy stop test (proposal vfd-slice2-discharge-pressure.md
§2.11.10, criterion B5): 4ε with ε = 2⁻⁵², and 1e-7 m / 4ε ≈ 1.1259e8 m."""


def test_the_stop_test_item_states_the_energy_round_off_allowance() -> None:
    """Criterion B5: the stop-test item is 1.1.0's item, one space and the sentence, byte for
    byte, in every solve (the test applies to every link of every network)."""
    items = _methods().sections[0].items
    assert items[1] == STOP_TEST_ITEM_1_1_0 + " " + ENERGY_ROUNDOFF_SENTENCE
    assert sum(ENERGY_ROUNDOFF_SENTENCE in item for item in items) == 1
    # The sentence's numbers, from the definition: 4ε, ε and 1e-7 m / 4ε.
    eps = 2.0**-52
    assert (f"{4 * eps:g}", f"{eps:g}", f"{1.0e-7 / (4 * eps):g}") == (
        "8.88178e-16",
        "2.22045e-16",
        "1.1259e+08",
    )
    # 4ε·x > 1e-7 m exactly where x > 1e-7 m / 4ε = 112,589,990.68 m, which lies below its
    # printed 1.1259e8 m: at 112,589,995 m the allowance already exceeds 1e-7 m, so the sentence
    # states the quotient and gives the printed number as "about", not as the bound.
    assert 1.0e-7 / (4 * eps) < 112_589_995.0 < 1.1259e8
    assert 4 * eps * 112_589_995.0 > 1.0e-7


def test_method_1_2_0_describes_both_fixes() -> None:
    """GOALS §4.3: C0b is method 1.2.0 (the owner's answer Q9 (a) of 2026-10-24), after 1.1.0,
    with one changelog line per fix, each stating what changes and how it was measured."""
    assert [e["version"] for e in METHOD_CHANGELOG][:3] == ["1.0.0", "1.1.0", "1.2.0"]
    [entry] = [e for e in METHOD_CHANGELOG if e["version"] == "1.2.0"]
    assert entry["date"] == "2026-10-24"
    flag, energy = entry["changes"]
    assert flag.startswith("The NOT_CONVERGED flag names where a continuity or energy residual")
    assert "only where that residual exceeds its stop tolerance" in flag
    assert "keep returning to a state whose solve failed" in flag
    assert "Only results that did not converge change" in flag
    assert energy.startswith("The energy stop test allows for the round-off of the heads")
    assert "≤ 1e-7 m + 4ε × the largest of |H_start|, |H_end| and |h(Q)|" in energy
    assert "The methods summary states the test." in energy
    for line in (flag, energy):
        assert line.endswith("(corpus comparison).")


def test_method_1_3_0_adds_the_equipment_element() -> None:
    """GOALS §4.3, proposal equipment-pressure-drop.md decision 17 and §3.5: the equipment
    element is method 1.3.0, after 1.2.0 (deployed), with one changelog line that says projects
    without equipment are unchanged."""
    assert [e["version"] for e in METHOD_CHANGELOG][:4] == ["1.0.0", "1.1.0", "1.2.0", "1.3.0"]
    [entry] = [e for e in METHOD_CHANGELOG if e["version"] == "1.3.0"]
    assert entry["date"] == "2026-10-26"
    assert entry["changes"] == [
        "Adds the equipment element: a loss between two ports from a datasheet pressure drop at a "
        "rated flow and the density of the fluid it is rated for, or from a Cv or Kv (a rated "
        "point on water, converted as for valves), at constant K (scaled with the square of the "
        "flow and with density). Flows, heads, pressures, statuses, traces, messages and system "
        "curves of projects without equipment are unchanged (corpus comparison)."
    ]


def test_method_1_4_0_adds_the_orifice_plate() -> None:
    """GOALS §4.3, proposal orifice-plate.md decision 22 and §3.9: the orifice plate is method
    1.4.0, after 1.3.0 (deployed), with one changelog line that says projects without orifices
    are unchanged."""
    assert [e["version"] for e in METHOD_CHANGELOG][:5] == [
        "1.0.0",
        "1.1.0",
        "1.2.0",
        "1.3.0",
        "1.4.0",
    ]
    [entry] = [e for e in METHOD_CHANGELOG if e["version"] == "1.4.0"]
    assert entry["date"] == "2026-10-28"
    assert entry["changes"] == [
        "Adds the orifice plate: ISO 5167-2's permanent pressure loss from the bore and the "
        "Reader-Harris/Gallagher discharge coefficient at D and D/2 tappings for every plate "
        "(held below ISO's lowest Reynolds number, flagged), or an entered coefficient at the "
        "plate's taps moved to D and D/2 tappings by ISO's ratio of the two tap sets' "
        "coefficients, with the differential pressure at a meter's taps and a flashing check at "
        "the vena contracta; a plate whose coefficient at D and D/2 tappings could exceed 1 is "
        "refused. Flows, heads, pressures, statuses, traces, messages and system curves of "
        "projects without orifices are unchanged (corpus comparison)."
    ]


def test_method_1_5_0_adds_the_project_library() -> None:
    """GOALS §4.3, proposal project-library.md §2.4 and the owner's answer Q5: the project library
    (with its K-at-a-stated-bore conversion) is method 1.5.0, after 1.4.0, with one changelog
    line that says projects without a project library are unchanged."""
    assert METHOD_VERSION == "1.5.0"
    assert [e["version"] for e in METHOD_CHANGELOG] == [
        "1.0.0",
        "1.1.0",
        "1.2.0",
        "1.3.0",
        "1.4.0",
        "1.5.0",
    ]
    entry = METHOD_CHANGELOG[-1]
    assert entry["date"] == "2026-10-28"
    [line] = entry["changes"]
    assert line.startswith("Adds the project library: ")
    assert "K = K₀ (D/d₀)⁴" in line
    assert "A fitting on a Cv or Kv entry in laminar flow is flagged" in line
    assert line.endswith(
        "Flows, heads, pressures, statuses, traces, messages and system curves of projects "
        "without a project library are unchanged (corpus comparison)."
    )


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
