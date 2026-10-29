"""Project library resolution (CLAUDE.md D22, docs/proposals/project-library.md §3-§5): pipe
specs, valve and fitting resistances from entries, the K moved to another bore, the topology
issues of references that do not resolve, the traces and methods section that name entries, and
scenarios and goal seek on elements that refer to entries.

The central claim (§1.3 decision 4) is checked against a second, independent resolver written
here (``hand_resolved``): it writes each entry's values onto the elements that refer to it, from
the proposal's rules alone (a spec's material, inner diameter and roughness; a Cv or Kv as
entered, or converted by fluids on the element's bore for a fitting's kOverride; a K as
K₀ (D/d₀)⁴), without calling the services. The project with references and the project it gives
solve to the same state bit for bit; only texts differ, and the tests name which.
"""

import copy
import math
from typing import Any

import fluids.fittings
import pytest
from fastapi.testclient import TestClient
from fluids.friction import roughness_Farshad

from opensolve_pipe.main import app
from opensolve_pipe.models.api import GoalSeekRequest, SolveOptions
from opensolve_pipe.models.components import FlowCoefficient, IsolationValve
from opensolve_pipe.models.piping import Fitting, PipeDefinition
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.project_library import PipeSpec, ResistanceSpec
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.goal_seek import goal_seek_case, prepare
from opensolve_pipe.services.scenarios import (
    ScenarioOverrideError,
    ScenarioTopologyError,
    apply_scenario,
    solve_case,
    value_text,
)
from opensolve_pipe.services.solver import TopologyError, solve_project
from opensolve_pipe.services.solver.coefficients import k_at_bore, k_from_coefficient
from opensolve_pipe.services.solver.fittings import resolve_fitting
from opensolve_pipe.services.solver.library import (
    USER_SOURCE,
    LibraryLookupError,
    resolve_pipe,
)
from opensolve_pipe.services.solver.project_library import entry_k
from opensolve_pipe.services.solver.valves import valve_resistance

from .helpers import custom_fluid, custom_pipe, project_dict, reservoir, tee
from .scenario_patch import hand_patched

G = 9.80665
"""m/s², standard gravity (3rd CGPM, 1901): the solver's g."""
WATER = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
CURVE = {
    "id": "C1",
    "name": "curve",
    "points": [
        {"flow": 0.0, "head": 40.0},
        {"flow": 0.02, "head": 35.0},
        {"flow": 0.04, "head": 20.0},
    ],
}
NPS60_STD_BORE = 59.25 * 0.0254
"""m: ASME B36.10M NPS 60 STD, 60 in OD and 0.375 in wall (proposal §1.2, P2)."""

# Test inputs (proposal: "every rating in Appendix A is a made-up input").
PIPE_SPECS: list[dict[str, Any]] = [
    {
        "id": "PS1",
        "name": "Lined 100 mm",
        "source": "test input: lined pipe, measured bore",
        "materialId": "custom",
        "innerDiameter": 0.1,
        "roughness": 4.5e-5,
    },
    {
        "id": "PS2",
        "name": "NPS 4 carbon steel, measured bore",
        "source": "test input: a bore measured on site",
        "materialId": "carbon_steel",
        "innerDiameter": 0.1023,
        "nominalSize": 0.1016,
    },
    {
        "id": "PS3",
        "name": "Carbon steel, stated roughness",
        "source": "test input",
        "materialId": "carbon_steel",
        "innerDiameter": 0.1,
        "roughness": 3.0e-5,
    },
    {
        "id": "PS4",
        "name": "Unused spec",
        "source": "test input, used by nothing",
        "materialId": "custom",
        "innerDiameter": 0.2,
        "roughness": 1.0e-5,
    },
]
RESISTANCES: list[dict[str, Any]] = [
    {
        "id": "RS1",
        "name": "Butterfly valve, open",
        "source": "test input, not a real valve",
        "kind": "K",
        "value": 0.3,
        "referenceDiameter": 0.09,
    },
    {"id": "RS2", "name": "Strainer", "source": "test input", "kind": "Cv", "value": 400.0},
    {"id": "RS3", "name": "Trim", "source": "test input", "kind": "Kv", "value": 300.0},
    {
        "id": "RS4",
        "name": "Elbow at its own bore",
        "source": "test input",
        "kind": "K",
        "value": 0.25,
        "referenceDiameter": 0.12,
    },
    {"id": "RS5", "name": "Unused entry", "source": "test input", "kind": "Kv", "value": 50.0},
]


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": 0.1} for p in ids]


def _component(kind: str, cid: str, ports: tuple[str, ...], **fields: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": _ports(*ports),
        **fields,
    }


def _link(
    cid: str,
    a: tuple[str, str],
    b: tuple[str, str],
    pipes: list[dict[str, Any]],
    fittings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": cid,
        "fromComponentId": a[0],
        "fromPortId": a[1],
        "toComponentId": b[0],
        "toPortId": b[1],
        "piping": {"pipes": pipes, "fittings": fittings or []},
    }


def _spec_pipe(spec_id: str, length: float) -> dict[str, Any]:
    return {"specId": spec_id, "length": length}


def network() -> dict[str, Any]:
    """A pump feeding a loop of two branches (a Crane tee splits them, an ideal tee joins
    them): R1 -> L1 -> P1 -> L2 -> T1; T1's run -> L3 -> V1 (butterfly, RS1's K stated at 0.09
    m, on a 0.1 m pipe) -> L4 -> T2; T1's branch -> L5 -> C1 (check, RS2's Cv) -> L6 -> PRV1
    (RS3's Kv) -> L7 -> T2; T2 -> L8 -> R2. L1's pipes are specs PS1 (custom) and PS2 (carbon
    steel, its roughness Farshad's at the spec's bore), with an elbow on RS4's K (stated at
    0.12 m), a strainer on RS2's Cv and a reducer on RS3's Kv; PS4 and RS5 are used by nothing."""
    comps = [
        reservoir("R1", level=5.0),
        _component("pump", "P1", ("suction", "discharge"), curveId="C1"),
        {**tee("T1", loss_model="crane")},
        _component(
            "valve",
            "V1",
            ("inlet", "outlet"),
            valveType="butterfly",
            resistance={"kind": "library", "id": "RS1"},
        ),
        _component(
            "valve",
            "C1",
            ("inlet", "outlet"),
            valveType="check",
            resistance={"kind": "library", "id": "RS2"},
        ),
        _component(
            "valve",
            "PRV1",
            ("inlet", "outlet"),
            valveType="prv",
            setpoint=4.0e5,
            resistance={"kind": "library", "id": "RS3"},
        ),
        tee("T2"),
        reservoir("R2", level=15.0),
    ]
    conns = [
        _link(
            "L1",
            ("R1", "port_1"),
            ("P1", "suction"),
            [_spec_pipe("PS1", 4.0), _spec_pipe("PS2", 6.0)],
            [
                {"type": "entrance_sharp", "pipeIndex": 0},
                {"type": "elbow_90_lr", "quantity": 2, "pipeIndex": 0, "resistanceId": "RS4"},
                {"type": "custom", "pipeIndex": 1, "resistanceId": "RS2"},
                {"type": "reducer_sudden", "pipeIndex": 0, "resistanceId": "RS3"},
            ],
        ),
        _link("L2", ("P1", "discharge"), ("T1", "run_inlet"), [_spec_pipe("PS3", 20.0)]),
        _link("L3", ("T1", "run_outlet"), ("V1", "inlet"), [_spec_pipe("PS1", 15.0)]),
        _link("L4", ("V1", "outlet"), ("T2", "run_inlet"), [_spec_pipe("PS1", 15.0)]),
        _link("L5", ("T1", "branch"), ("C1", "inlet"), [custom_pipe(10.0, 0.08, 4.5e-5)]),
        _link("L6", ("C1", "outlet"), ("PRV1", "inlet"), [_spec_pipe("PS2", 5.0)]),
        _link("L7", ("PRV1", "outlet"), ("T2", "branch"), [_spec_pipe("PS2", 5.0)]),
        _link(
            "L8",
            ("T2", "run_outlet"),
            ("R2", "port_1"),
            [
                _spec_pipe("PS3", 30.0),
                {
                    "materialId": "carbon_steel",
                    "schedule": "40",
                    "nominalSize": 0.1016,
                    "length": 10.0,
                },
            ],
        ),
    ]
    data = project_dict(comps, conns, fluid=WATER, pump_library=[CURVE])
    data["pipeLibrary"] = copy.deepcopy(PIPE_SPECS)
    data["resistanceLibrary"] = copy.deepcopy(RESISTANCES)
    return data


# --------------------------------------------------------------------------- the second resolver


def _end_bore(data: dict[str, Any], component: str, port: str) -> float:
    """The inner diameter of the end segment of the pipe connected at a port (it must state one:
    a spec's, a custom pipe's or an override)."""
    for conn in data["connections"]:
        pipes = conn["piping"]["pipes"]
        if (conn["fromComponentId"], conn["fromPortId"]) == (component, port):
            return float(pipes[0]["innerDiameter"])
        if (conn["toComponentId"], conn["toPortId"]) == (component, port):
            return float(pipes[-1]["innerDiameter"])
    raise AssertionError(f"{component}:{port} is not connected")


def _k_on(entry: dict[str, Any], d: float) -> float:
    """An entry's K on bore d, from the proposal's rules (§3.1, §3.3)."""
    if entry["kind"] == "K":
        return float(entry["value"] * (d / entry["referenceDiameter"]) ** 4)
    convert = fluids.fittings.Cv_to_K if entry["kind"] == "Cv" else fluids.fittings.Kv_to_K
    return float(convert(entry["value"], d))


def hand_resolved(project: dict[str, Any]) -> dict[str, Any]:
    """The project a user would type with every entry's values on the elements that use it,
    and no library: the independent reference of proposal §7.2."""
    data = copy.deepcopy(project)
    specs = {s["id"]: s for s in data.pop("pipeLibrary", [])}
    entries = {e["id"]: e for e in data.pop("resistanceLibrary", [])}
    for conn in data["connections"]:
        for i, pipe in enumerate(conn["piping"]["pipes"]):
            if "specId" in pipe:
                spec = specs[pipe["specId"]]
                own = {"materialId": spec["materialId"], "innerDiameter": spec["innerDiameter"]}
                if spec.get("roughness") is not None:
                    own["roughness"] = spec["roughness"]
                conn["piping"]["pipes"][i] = {**own, "length": pipe["length"]}
    for conn in data["connections"]:
        for fitting in conn["piping"]["fittings"]:
            if "resistanceId" in fitting:
                entry = entries[fitting.pop("resistanceId")]
                d = conn["piping"]["pipes"][fitting.get("pipeIndex", 0)]["innerDiameter"]
                fitting["kOverride"] = _k_on(entry, d)
    for comp in data["components"]:
        resistance = comp.get("resistance")
        if isinstance(resistance, dict) and resistance.get("kind") == "library":
            entry = entries[resistance["id"]]
            if entry["kind"] == "K":
                d = _end_bore(data, comp["id"], "inlet")
                comp["resistance"] = {"kind": "K", "value": _k_on(entry, d)}
            else:
                comp["resistance"] = {"kind": entry["kind"], "value": entry["value"]}
    return data


def _state(data: dict[str, Any], **options: Any) -> SolvedState:
    return solve_project(Project.model_validate(data), SolveOptions(**options))


def _dump(state: SolvedState) -> dict[str, Any]:
    data = state.model_dump(mode="json", by_alias=True)
    data.pop("timestamp")
    return data


# --------------------------------------------------------------------------- resolution


def _pipe_spec(**fields: Any) -> PipeSpec:
    return PipeSpec.model_validate({**PIPE_SPECS[0], **fields})


def test_a_custom_spec_resolves_to_its_own_values() -> None:
    spec = _pipe_spec()
    pipe = PipeDefinition.model_validate({"specId": "PS1", "length": 7.0})
    resolved = resolve_pipe(pipe, {"PS1": spec})
    assert (resolved.inner_diameter, resolved.roughness, resolved.length) == (0.1, 4.5e-5, 7.0)
    assert resolved.diameter_source == resolved.roughness_source == USER_SOURCE
    assert resolved.material_id == "custom"
    assert resolved.spec is spec


def test_a_spec_on_a_library_material_takes_its_cited_roughness_at_the_bore() -> None:
    """P2: NPS 60 STD carbon steel, roughness left blank: Farshad & Rieke's 'Carbon steel, bare'
    evaluated at the spec's bore (fluids, called here directly), labelled as such."""
    spec = _pipe_spec(materialId="carbon_steel", innerDiameter=NPS60_STD_BORE, roughness=None)
    resolved = resolve_pipe(PipeDefinition(spec_id="PS1", length=10.0), {"PS1": spec})
    assert resolved.inner_diameter == NPS60_STD_BORE
    assert resolved.roughness == float(roughness_Farshad(ID="Carbon steel, bare", D=NPS60_STD_BORE))
    assert resolved.diameter_source == USER_SOURCE
    assert "Farshad" in resolved.roughness_source
    assert resolved.roughness_source.endswith(
        f"evaluated at the user inner diameter {NPS60_STD_BORE:g} m"
    )
    stated = _pipe_spec(materialId="carbon_steel", innerDiameter=0.1, roughness=3.0e-5)
    given = resolve_pipe(PipeDefinition(spec_id="PS1", length=10.0), {"PS1": stated})
    assert (given.roughness, given.roughness_source) == (3.0e-5, USER_SOURCE)


def test_a_spec_that_does_not_resolve_names_itself() -> None:
    pipe = PipeDefinition(spec_id="PS9", length=1.0)
    with pytest.raises(LibraryLookupError) as missing:
        resolve_pipe(pipe, {"PS1": _pipe_spec()})
    assert missing.value.code == "UNKNOWN_PIPE_SPEC"
    assert "'PS9'" in str(missing.value)
    unknown = _pipe_spec(materialId="unobtainium", roughness=None)
    with pytest.raises(LibraryLookupError) as material:
        resolve_pipe(PipeDefinition(spec_id="PS1", length=1.0), {"PS1": unknown})
    assert material.value.code == "UNKNOWN_PIPE_MATERIAL"
    assert str(material.value).startswith("pipe spec 'PS1': unknown pipe material 'unobtainium'")


@pytest.mark.parametrize("k0", [0.3, 1.0e-12, 7.123456789, 9.999e6])
@pytest.mark.parametrize("d0", [0.0254, 0.7366, 1.50495, 10.0])
def test_a_k_used_at_its_stated_bore_is_exactly_k0(k0: float, d0: float) -> None:
    """§3.3: D = d₀ gives K₀ bit for bit, as an inline K would be."""
    assert k_at_bore(k0, d0, d0) == k0
    entry = ResistanceSpec(
        id="RS1", name="n", source="s", kind="K", value=k0, reference_diameter=d0
    )
    assert entry_k(entry, d0).k == k0


def test_a_k_moved_to_another_bore_keeps_its_head_loss() -> None:
    """P3: K₀ = 0.30 at d₀ = 0.7366 m used at D = 0.74294 m: K₀ (D/d₀)⁴, and the head loss at
    0.95 m³/s on either basis, K (Q/A)²/(2g) = K₀ (Q/A₀)²/(2g), to round-off."""
    k0, d0, d, q = 0.30, 0.7366, 0.74294, 0.95
    entry = ResistanceSpec(
        id="RS1", name="n", source="s", kind="K", value=k0, reference_diameter=d0
    )
    use = entry_k(entry, d)
    assert use.k == k0 * (d / d0) ** 4
    area, area0 = math.pi * d * d / 4.0, math.pi * d0 * d0 / 4.0
    h = use.k * (q / area) ** 2 / (2.0 * G)
    h0 = k0 * (q / area0) ** 2 / (2.0 * G)
    assert h == pytest.approx(h0, rel=4e-16, abs=0.0)
    assert use.how == (
        f"K = K₀ (D/d₀)⁴ = 0.3 × (0.74294 m / 0.7366 m)⁴ = {use.k:.6g}, the same head loss at a "
        "given flow"
    )


@pytest.mark.parametrize("kind", ["Cv", "Kv"])
@pytest.mark.parametrize("d", [0.025, 0.1, 0.7366])
def test_a_cv_or_kv_entry_converts_as_one_entered(kind: str, d: float) -> None:
    """§3.1: the same fluids call on the same bore as an inline coefficient (ISA-75.01.01)."""
    entry = ResistanceSpec(id="RS1", name="n", source="s", kind=kind, value=60000.0)  # type: ignore[arg-type]
    convert = fluids.fittings.Cv_to_K if kind == "Cv" else fluids.fittings.Kv_to_K
    assert entry_k(entry, d).k == float(convert(60000.0, d))
    inline = FlowCoefficient(kind=kind, value=60000.0)  # type: ignore[arg-type]
    assert entry_k(entry, d).k == k_from_coefficient(inline, d)[0]


def test_a_valve_and_a_fitting_take_their_entry_on_their_own_bore() -> None:
    entries = {e["id"]: ResistanceSpec.model_validate(e) for e in RESISTANCES}
    fields = _component("valve", "V1", ("inlet", "outlet"), valveType="butterfly")
    valve = IsolationValve.model_validate(
        {**fields, "resistance": {"kind": "library", "id": "RS1"}}
    )
    resistance = valve_resistance(valve, 0.1, entries)
    assert resistance.k == 0.3 * (0.1 / 0.09) ** 4
    assert (resistance.origin, resistance.crane, resistance.range_note) == ("user", False, None)
    assert resistance.coefficient == "K"
    assert resistance.entry is not None
    assert resistance.entry.entry.id == "RS1"
    cv = IsolationValve.model_validate({**fields, "resistance": {"kind": "library", "id": "RS2"}})
    assert valve_resistance(cv, 0.1, entries).coefficient == "Cv"
    assert valve_resistance(cv, 0.1, entries).k == float(fluids.fittings.Cv_to_K(400.0, 0.1))
    # A reducer on an entry: the same K both ways, on pipe pipeIndex, as a kOverride is.
    reducer = Fitting.model_validate(
        {"type": "reducer_sudden", "pipeIndex": 0, "resistanceId": "RS4"}
    )
    fit = resolve_fitting(0, reducer, [0.1, 0.05], entries)
    assert fit.k_forward == fit.k_reverse == 0.25 * (0.1 / 0.12) ** 4
    assert fit.segment_forward == fit.segment_reverse == 0
    assert fit.user_k
    assert fit.valid_in_laminar_flow
    assert fit.range_warning is None
    assert fit.source == 'project library resistance "Elbow at its own bore" (RS4): test input'


# --------------------------------------------------------------------------- the twin


def test_a_library_project_solves_as_its_hand_typed_twin_bit_for_bit() -> None:
    """§1.3 decision 4 and §7.1 items 1, 3 and 4: every value of the solved state, system curves
    included, is the twin's, bit for bit. What differs is text, and only these: each fitting's
    result ``source`` (the entry and its source, where the twin's says 'user'), and the traces of
    the elements that refer to an entry (their inputs, equations, correlations, data sources and
    notes, never their intermediate values), and the methods summary's "Project library"
    section."""
    project = network()
    library = _state(project, include_system_curve=True, system_curve_points=11)
    twin = _state(hand_resolved(project), include_system_curve=True, system_curve_points=11)
    assert library.converged
    assert twin.converged
    assert library.pump_results["P1"].system_curve, "the pump runs and has a system curve"
    a, b = _dump(library), _dump(twin)
    trace_a, trace_b = a.pop("trace"), b.pop("trace")
    sources = {}
    for conn_id, link in a["linkResults"].items():
        for fit, other in zip(link["fittings"], b["linkResults"][conn_id]["fittings"], strict=True):
            sources[(conn_id, fit["index"])] = (fit.pop("source"), other.pop("source"))
    assert a == b
    assert {key: pair for key, pair in sources.items() if pair[0] != pair[1]} == {
        ("L1", 1): ('project library resistance "Elbow at its own bore" (RS4): test input', "user"),
        ("L1", 2): ('project library resistance "Strainer" (RS2): test input', "user"),
        ("L1", 3): ('project library resistance "Trim" (RS3): test input', "user"),
    }
    users = {"L1", "L2", "L3", "L4", "L6", "L7", "L8", "V1", "C1", "PRV1"}
    for element, ea in trace_a["elements"].items():
        eb = trace_b["elements"][element]
        assert ea["intermediates"] == eb["intermediates"], element
        if element not in users:
            assert ea == eb, element
        else:
            assert ea != eb, element
    sections_a = trace_a["methods"].pop("sections")
    sections_b = trace_b["methods"].pop("sections")
    assert trace_a["methods"] == trace_b["methods"]
    assert [s for s in sections_a if s["title"] != "Project library"] == sections_b
    assert [s["title"] for s in sections_a][1:4] == [
        "Pipe friction",
        "Project library",
        "Minor losses",
    ]


def test_the_twin_equality_holds_for_the_api_responses_too() -> None:
    client = TestClient(app, client=("198.51.104.1", 50000))
    options = {"includeSystemCurve": False}
    project = network()
    library = client.post("/api/v1/solve", json={"project": project, "options": options}).json()
    twin = client.post(
        "/api/v1/solve", json={"project": hand_resolved(project), "options": options}
    ).json()
    for body in (library, twin):
        body.pop("computeTime")
        body["solvedState"].pop("timestamp")
        body["solvedState"].pop("trace")
        for link in body["solvedState"]["linkResults"].values():
            for fit in link["fittings"]:
                fit.pop("source")
    assert library == twin
    assert library["solvedState"]["methodVersion"] == "1.5.0"


def test_a_system_curve_through_library_elements_is_the_twins() -> None:
    """POST /system-curve resolves references as /solve does (every point, its reason)."""
    client = TestClient(app, client=("198.51.104.4", 50000))
    project = network()
    body = {"pumpId": "P1", "numPoints": 9}
    library = client.post("/api/v1/system-curve", json={"project": project, **body})
    twin = client.post("/api/v1/system-curve", json={"project": hand_resolved(project), **body})
    assert library.status_code == twin.status_code == 200, library.text
    assert library.json() == twin.json()
    assert any(p["head"] is not None for p in library.json()["points"])


def test_a_project_without_a_library_is_unchanged_by_empty_lists() -> None:
    """§1.3 decision 5: empty lists are omitted, so a project that sends them solves and dumps
    exactly as one that does not; neither has a "Project library" section."""
    plain = network()
    plain = hand_resolved(plain)
    empty = {**copy.deepcopy(plain), "pipeLibrary": [], "resistanceLibrary": []}
    assert (
        Project.model_validate(empty).model_dump_json()
        == Project.model_validate(plain).model_dump_json()
    )
    a, b = (
        _dump(_state(plain, include_system_curve=False)),
        _dump(_state(empty, include_system_curve=False)),
    )
    assert a == b
    assert "Project library" not in [s["title"] for s in a["trace"]["methods"]["sections"]]


def test_the_pipe_velocity_check_reads_a_spec_pipe_as_its_twin() -> None:
    """D19 reads solved results: a spec pipe's velocity is its bore's, so the checks agree."""
    project = network()
    project["settings"]["designChecks"] = {
        "pipeVelocity": {"maximum": 1.0, "source": {"kind": "user"}}
    }
    library = _state(project, include_system_curve=False)
    twin = _state(hand_resolved(project), include_system_curve=False)
    assert library.design_checks
    assert library.design_checks == twin.design_checks
    assert {r.connection_id for r in library.design_checks} >= {"L1", "L3"}


# --------------------------------------------------------------------------- topology issues


def test_dangling_references_are_listed_with_the_other_topology_issues() -> None:
    """§2.3: one 422 listing every issue; each names the element and the id."""
    project = network()
    project["components"][1]["curveId"] = "C9"  # UNKNOWN_PUMP_CURVE too
    project["components"][3]["resistance"] = {"kind": "library", "id": "RS9"}
    project["connections"][2]["piping"]["pipes"][0]["specId"] = "PS9"
    project["connections"][0]["piping"]["fittings"][2]["resistanceId"] = "RS8"
    with pytest.raises(TopologyError) as raised:
        _state(project, include_system_curve=False)
    issues = [(i.code, i.message, i.component_ids, i.connection_ids) for i in raised.value.issues]
    assert issues == [
        (
            "UNKNOWN_PUMP_CURVE",
            "pump 'P1' refers to pump curve 'C9', which is not in the pump library",
            ["P1"],
            [],
        ),
        (
            "UNKNOWN_RESISTANCE",
            "valve 'V1' refers to resistance entry 'RS9', which is not in the project library",
            ["V1"],
            [],
        ),
        (
            "UNKNOWN_RESISTANCE",
            "connection 'L1' fitting 3 (custom) refers to resistance entry 'RS8', which is not in "
            "the project library",
            [],
            ["L1"],
        ),
        (
            "UNKNOWN_PIPE_SPEC",
            "connection 'L3' pipe 1 refers to pipe spec 'PS9', which is not in the project library",
            [],
            ["L3"],
        ),
    ]
    client = TestClient(app, client=("198.51.104.2", 50000))
    response = client.post("/api/v1/solve", json={"project": project})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "TOPOLOGY_ERROR"
    assert [i["code"] for i in body["issues"]] == [code for code, *_ in issues]


def test_a_spec_with_an_unknown_material_is_a_topology_issue_at_each_pipe() -> None:
    project = network()
    project["pipeLibrary"][0]["materialId"] = "unobtainium"
    project["pipeLibrary"][0].pop("roughness")
    with pytest.raises(TopologyError) as raised:
        _state(project, include_system_curve=False)
    found = [(i.code, i.connection_ids) for i in raised.value.issues]
    assert found == [
        ("UNKNOWN_PIPE_MATERIAL", ["L1"]),
        ("UNKNOWN_PIPE_MATERIAL", ["L3"]),
        ("UNKNOWN_PIPE_MATERIAL", ["L4"]),
    ]
    assert raised.value.issues[0].message.startswith(
        "connection 'L1' pipe 1: pipe spec 'PS1': unknown pipe material 'unobtainium'"
    )


FARSHAD_1UM = float(roughness_Farshad(ID="Carbon steel, bare", D=1.0e-6))
"""m: carbon steel's roughness (Farshad & Rieke 2006) at a 1 µm bore, 39.8 times the bore."""


@pytest.mark.parametrize(
    ("spec", "code", "tail"),
    [
        (  # a roughness typed in mm for m: ε/D = 4.5
            {"materialId": "custom", "innerDiameter": 0.01, "roughness": 0.045},
            "ROUGHNESS_OUT_OF_RANGE",
            "roughness 0.045 m is 4.5 times the inner diameter 0.01 m; the Colebrook equation "
            "has no solution for relative roughness of 3.7 or more",
        ),
        (  # a library material's roughness, Farshad's at the spec's bore, not typed by the user
            {"materialId": "carbon_steel", "innerDiameter": 1.0e-6},
            "ROUGHNESS_OUT_OF_RANGE",
            f"roughness {FARSHAD_1UM:g} m is {FARSHAD_1UM / 1.0e-6:.4g} times the inner diameter "
            "1e-06 m; the Colebrook equation has no solution for relative roughness of 3.7 or more",
        ),
        (  # a bore whose resistance underflows
            {"materialId": "custom", "innerDiameter": 1.0e-100, "roughness": 0.0},
            "PIPE_SIZE_OUT_OF_RANGE",
            "an inner diameter of 1e-100 m and a length of 5 m give a pipe resistance that is "
            "not a finite floating-point number; the solver cannot represent this pipe",
        ),
    ],
)
def test_a_range_issue_on_a_spec_pipe_names_the_spec(
    spec: dict[str, Any], code: str, tail: str
) -> None:
    """ROUGHNESS_OUT_OF_RANGE and PIPE_SIZE_OUT_OF_RANGE quote a spec's bore and roughness: on a
    pipe of a spec they name it first, "pipe spec 'PS1': ", as an unknown material does, since
    the values are changed there and not on the pipe (D10: the id at fault, by id only). The
    same values typed on a pipe of its own give the message without it, as before the library."""
    own_pipe = {**{k: v for k, v in spec.items() if k != "materialId"}, "length": 5.0}
    own_pipe["materialId"] = spec["materialId"]
    data = project_dict(
        [reservoir("R1", level=20.0), reservoir("R2", level=10.0)],
        [_link("L1", ("R1", "port_1"), ("R2", "port_1"), [_spec_pipe("PS1", 5.0), own_pipe])],
    )
    data["pipeLibrary"] = [{"id": "PS1", "name": "10 mm tube", "source": "test input", **spec}]
    client = TestClient(app, client=("198.51.104.5", 50000))
    response = client.post("/api/v1/solve", json={"project": data})
    assert response.status_code == 422, response.text
    found = [
        (i["code"], i["message"], i["componentIds"], i["connectionIds"])
        for i in response.json()["issues"]
    ]
    assert [(c, comps, conns) for c, _, comps, conns in found] == [
        (code, [], ["L1"]),
        (code, [], ["L1"]),
    ]
    assert [message for _, message, *_ in found] == [
        f"connection 'L1' pipe 1: pipe spec 'PS1': {tail}",
        f"connection 'L1' pipe 2: {tail}",
    ]


def test_an_entry_the_solver_cannot_represent_is_a_topology_issue() -> None:
    """A schema-valid K stated at a bore 10⁻⁹⁰ of the element's overflows (D/d₀)⁴; one stated at
    a bore 10⁹⁰ times larger underflows a valve's K to 0, which no user could type: each is a
    topology issue (422), not a 500, as VALVE_RESISTANCE_OUT_OF_RANGE is for an inline Cv."""
    client = TestClient(app, client=("198.51.104.3", 50000))
    for d0, code_valve in ((1.0e-91, "VALVE_RESISTANCE_OUT_OF_RANGE"),):
        project = network()
        project["resistanceLibrary"][0]["referenceDiameter"] = d0
        project["resistanceLibrary"][3]["referenceDiameter"] = d0
        response = client.post("/api/v1/solve", json={"project": project})
        assert response.status_code == 422, response.text
        codes = [
            (i["code"], i["componentIds"], i["connectionIds"]) for i in response.json()["issues"]
        ]
        assert codes == [(code_valve, ["V1"], []), ("FITTING_RESISTANCE_OUT_OF_RANGE", [], ["L1"])]
        message = response.json()["issues"][0]["message"]
        assert message.startswith(
            "valve 'V1': its project library resistance entry 'RS1', K 0.3 at"
        )
    project = network()  # 5e-324 × (0.1/0.2)⁴ rounds to 0
    project["resistanceLibrary"][0].update({"value": 5e-324, "referenceDiameter": 0.2})
    response = client.post("/api/v1/solve", json={"project": project})
    assert response.status_code == 422, response.text
    assert [i["code"] for i in response.json()["issues"]] == ["VALVE_RESISTANCE_OUT_OF_RANGE"]


def _valve(cid: str, resistance: dict[str, Any]) -> dict[str, Any]:
    return _component("valve", cid, ("inlet", "outlet"), valveType="gate", resistance=resistance)


ORIFICE = _component("orifice", "O1", ("inlet", "outlet"), boreDiameter=0.08)
"""A plate of 0.08 m bore: β ≥ 1 on a 0.05 m inlet pipe (ORIFICE_OUT_OF_RANGE)."""
LINED = {**PIPE_SPECS[0], "innerDiameter": 0.15}
"""PS1 on a 0.15 m bore (O1's β = 0.533 when its inlet pipe is of this spec)."""


@pytest.mark.parametrize(
    ("unresolved", "issue"),
    [
        ({"specId": "NOPE", "length": 5.0}, "UNKNOWN_PIPE_SPEC"),
        ({"specId": "PS9", "length": 5.0}, "UNKNOWN_PIPE_MATERIAL"),
    ],
)
def test_a_pipe_that_does_not_resolve_leaves_the_others_their_numbers_and_ends(
    unresolved: dict[str, Any], issue: str
) -> None:
    """A pipe whose spec is missing, or whose spec's material is unknown, is left out of the
    other checks without moving the pipes after it: each keeps its number (D10, from 1), and a
    valve or plate whose own end pipe does not resolve is never tested on another pipe."""
    unknown = {**PIPE_SPECS[0], "id": "PS9", "materialId": "unobtainium"}
    unknown.pop("roughness")

    def issues(comps: list[dict[str, Any]], conns: list[dict[str, Any]]) -> list[tuple[str, str]]:
        data = project_dict(comps, conns)
        data["pipeLibrary"] = [LINED, unknown]
        with pytest.raises(TopologyError) as raised:
            _state(data, include_system_curve=False)
        return [(i.code, i.message) for i in raised.value.issues]

    ends = (reservoir("R1", level=20.0), reservoir("R2", level=10.0))
    # The unresolved pipe first: the 1e-100 m pipe after it is pipe 2.
    found = issues(
        [*ends],
        [_link("C1", ("R1", "port_1"), ("R2", "port_1"), [unresolved, custom_pipe(10, 1e-100, 0)])],
    )
    assert [code for code, _ in found] == [issue, "PIPE_SIZE_OUT_OF_RANGE"]
    assert found[0][1].startswith("connection 'C1' pipe 1")
    assert found[1][1].startswith("connection 'C1' pipe 2: an inner diameter of 1e-100 m")
    # The unresolved pipe at a valve's inlet: the valve's K is not tested on pipe 1's bore.
    after = [custom_pipe(10.0, 0.1, 4.5e-5)]
    found = issues(
        [*ends, _valve("V1", {"kind": "K", "value": 1.0e7})],
        [
            _link("C1", ("R1", "port_1"), ("V1", "inlet"), [custom_pipe(10, 1e-80, 0), unresolved]),
            _link("C2", ("V1", "outlet"), ("R2", "port_1"), after),
        ],
    )
    assert [code for code, _ in found] == [issue, "PIPE_SIZE_OUT_OF_RANGE"]
    assert found[0][1].startswith("connection 'C1' pipe 2")
    assert found[1][1].startswith("connection 'C1' pipe 1: an inner diameter of 1e-80 m")
    # ... nor a plate's bore on pipe 1's (β = 1.6 there).
    found = issues(
        [*ends, ORIFICE],
        [
            _link("C1", ("R1", "port_1"), ("O1", "inlet"), [custom_pipe(10, 0.05, 0), unresolved]),
            _link("C2", ("O1", "outlet"), ("R2", "port_1"), [custom_pipe(10.0, 0.15, 4.5e-5)]),
        ],
    )
    assert [code for code, _ in found] == [issue]
    # A valve whose own inlet pipe resolves is still tested on it, with the other issues.
    found = issues(
        [*ends, _valve("V1", {"kind": "Cv", "value": 1.0e-170})],
        [
            _link("C1", ("R1", "port_1"), ("V1", "inlet"), [unresolved, custom_pipe(5, 0.1, 0)]),
            _link("C2", ("V1", "outlet"), ("R2", "port_1"), after),
        ],
    )
    assert [code for code, _ in found] == [issue, "VALVE_RESISTANCE_OUT_OF_RANGE"]
    assert "on the inlet pipe's inner diameter of 0.1 m" in found[1][1]


# --------------------------------------------------------------------------- flags


@pytest.mark.parametrize("kind", ["K", "Cv", "Kv"])
def test_a_fitting_on_a_cv_or_kv_entry_is_flagged_in_laminar_flow_as_a_valve_is(
    kind: str,
) -> None:
    """A Cv or Kv entry on a fitting is the same turbulent-flow conversion (ISA-75.01.01, without
    F_R) as on a valve, so in laminar flow it gets the valve's CORRELATION_OUT_OF_RANGE warning,
    on the connection with the fitting's index; a K entry, as a kOverride, gets none."""
    entry: dict[str, Any] = {"id": "RS1", "name": "Strainer", "source": "test input"}
    entry |= {"kind": kind, "value": 200.0}
    if kind == "K":
        entry |= {"value": 5.0, "referenceDiameter": 0.1}
    fittings = [{"type": "custom", "pipeIndex": 0, "resistanceId": "RS1"}]
    comps = [
        reservoir("R1", level=10.5),
        _valve("V1", {"kind": "library", "id": "RS1"}),
        reservoir("R2", level=10.0),
    ]
    conns = [
        _link("C1", ("R1", "port_1"), ("V1", "inlet"), [custom_pipe(100, 0.1, 4.5e-5)], fittings),
        _link("C2", ("V1", "outlet"), ("R2", "port_1"), [custom_pipe(100, 0.1, 4.5e-5)]),
    ]
    data = project_dict(comps, conns, fluid=custom_fluid(density=900.0, viscosity=0.5))
    data["resistanceLibrary"] = [entry]
    state = _state(data, include_system_curve=False)
    assert state.converged
    re = state.link_results["C1"].segments[0].reynolds_number
    assert 0.0 < re < 2000.0
    flags = [f for f in state.flags if f.code == "CORRELATION_OUT_OF_RANGE"]
    if kind == "K":
        assert flags == []
        return
    on_valve, on_fitting = (
        next(f for f in flags if f.component_id == "V1"),
        next(f for f in flags if f.connection_id == "C1"),
    )
    assert len(flags) == 2
    assert (on_fitting.severity, on_fitting.details) == (
        "warning",
        {"fittingIndex": 0, "reynoldsNumber": re},
    )
    head = "connection 'C1' fitting 1 (custom): "
    assert on_fitting.message.startswith(head)
    assert on_fitting.message.removeprefix(head) == on_valve.message.removeprefix("valve 'V1': ")
    assert f"its {kind} is converted to K with the turbulent-flow valve equation" in (
        on_fitting.message
    )
    # The same entry in turbulent flow (water): no flag on either.
    data["fluid"] = WATER
    turbulent = _state(data, include_system_curve=False)
    assert turbulent.link_results["C1"].segments[0].reynolds_number > 4000.0
    assert [f for f in turbulent.flags if f.code == "CORRELATION_OUT_OF_RANGE"] == []


# --------------------------------------------------------------------------- traces and methods


def test_a_spec_pipe_trace_names_the_spec_and_its_source() -> None:
    state = _state(network(), include_system_curve=False)
    trace = state.trace.elements["L1"]
    inputs = {i.name: (i.value, i.source) for i in trace.inputs}
    assert inputs["Pipe 1 pipe spec"] == ('"Lined 100 mm" (PS1)', "user")
    assert inputs["Pipe 2 pipe spec"] == ('"NPS 4 carbon steel, measured bore" (PS2)', "user")
    assert inputs["Pipe 2 nominal diameter"] == (0.1016, "user")
    assert inputs["Pipe 2 inner diameter D"] == (0.1023, "user")
    assert inputs["Pipe 2 roughness ε"][1] == "library"  # Farshad's, at the spec's bore
    assert inputs["Pipe 1 roughness ε"] == (4.5e-5, "user")
    data = {d.name: d.citation for d in trace.data_sources}
    assert data["Pipe 1 inner diameter"] == (
        'project library pipe spec "Lined 100 mm" (PS1): test input: lined pipe, measured bore'
    )
    assert data["Pipe 1 roughness"] == data["Pipe 1 inner diameter"]
    assert data["Pipe 2 roughness"].startswith("Farshad")
    assert (
        'Pipe 2: project library pipe spec "NPS 4 carbon steel, measured bore" (PS2): test input: '
        "a bore measured on site"
    ) in trace.notes


def test_entry_traces_state_the_value_entered_and_the_conversion() -> None:
    state = _state(network(), include_system_curve=False)
    valve = state.trace.elements["V1"]
    inputs = {i.name: (i.value, i.unit, i.source) for i in valve.inputs}
    assert inputs["Resistance K (project library, as entered)"] == (0.3, "", "user")
    assert inputs["Resistance K stated at bore d₀"] == (0.09, "m", "user")
    k = 0.3 * (0.1 / 0.09) ** 4
    assert valve.notes[:2] == [
        'Resistance: project library resistance "Butterfly valve, open" (RS1): test input, not a '
        "real valve",
        'Resistance: K 0.3 at 0.09 m, project library resistance "Butterfly valve, open" (RS1); '
        f"K = K₀ (D/d₀)⁴ = 0.3 × (0.1 m / 0.09 m)⁴ = {k:.6g}, the same head loss at a given flow.",
    ]
    assert state.valve_results["V1"].k_open == k
    check = state.trace.elements["C1"]
    assert any(c.name == "fluids.fittings.Cv_to_K(Cv, D_ref)" for c in check.correlations)
    link = state.trace.elements["L1"]
    names = [i.name for i in link.inputs]
    assert "Fitting 2 (elbow_90_lr) K (project library, as entered)" in names
    assert "Fitting 2 (elbow_90_lr) K stated at bore d₀" in names
    assert "Fitting 3 (custom) Cv (project library, as entered)" in names
    assert not [n for n in names if n.endswith("K (user)")]


def test_the_methods_section_lists_the_whole_library() -> None:
    state = _state(network(), include_system_curve=False)
    [section] = [s for s in state.trace.methods.sections if s.title == "Project library"]
    items = section.items
    assert items[1].startswith(
        'Project library pipe spec "Lined 100 mm" (PS1): custom, inner diameter 0.1 m'
    )
    assert "used by connection L1 pipe 1, connection L3 pipe 1, connection L4 pipe 1" in items[1]
    assert items[1].endswith("Source: test input: lined pipe, measured bore")
    assert (
        "roughness: the material's cited roughness (Farshad & Rieke 2006) at that inner diameter, "
        in items[2]
    )
    assert items[4] == (
        'Project library pipe spec "Unused spec" (PS4): custom, inner diameter 0.2 m, roughness '
        "1e-05 m; not used by any element. Source: test input, used by nothing"
    )
    k = 0.3 * (0.1 / 0.09) ** 4
    assert items[5] == (
        'Project library resistance "Butterfly valve, open" (RS1): K 0.3 at 0.09 m; used by valve '
        f"V1 (K {k:.6g} on its inlet pipe's 0.1 m bore). Source: test input, not a real valve"
    )
    assert "connection L1 fitting 3" in items[6]
    assert "valve C1" in items[6]
    assert items[9].endswith("not used by any element. Source: test input")
    assert items[10].startswith("K = K₀ (D/d₀)⁴: a K₀ stated at bore d₀ moved to the bore D")
    assert items[11].startswith("A Cv or Kv entry is converted to K on each element's")
    assert items[11].endswith(
        "without the Reynolds number factor F_R), as one entered on that element; on a valve or "
        "a fitting in laminar flow (Re < 2000 in its reference pipe) it is flagged."
    )
    assert len(items) == 12
    assert section.references[0].startswith("OpenSolve Pipe design decision D22")


def test_a_library_nothing_uses_is_listed_as_not_used() -> None:
    project = hand_resolved(network())
    project["pipeLibrary"] = [PIPE_SPECS[3]]
    state = _state(project, include_system_curve=False)
    [section] = [s for s in state.trace.methods.sections if s.title == "Project library"]
    assert len(section.items) == 2
    assert section.items[1].endswith("not used by any element. Source: test input, used by nothing")
    assert section.references == [
        "OpenSolve Pipe design decision D22 (CLAUDE.md), from docs/proposals/project-library.md."
    ]


# --------------------------------------------------------------------------- scenarios


def _with_scenario(project: dict[str, Any], *overrides: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(project)
    data["scenarios"] = [{"id": "S1", "name": "Library case", "overrides": list(overrides)}]
    return data


SWITCH: list[dict[str, Any]] = [
    {
        "kind": "pipe",
        "connectionId": "L5",
        "pipeIndex": 0,
        "field": "spec",
        "value": {"specId": "PS2"},
    },
    {
        "kind": "pipe",
        "connectionId": "L3",
        "pipeIndex": 0,
        "field": "spec",
        "value": {"materialId": "custom", "innerDiameter": 0.1, "roughness": 1e-5},
    },
    {
        "kind": "component",
        "componentId": "V1",
        "field": "resistance",
        "value": {"kind": "library", "id": "RS4"},
    },
    {
        "kind": "component",
        "componentId": "C1",
        "field": "resistance",
        "value": {"kind": "Cv", "value": 380.0},
    },
]
"""A scenario that switches a pipe to a spec and one from it, and a valve to another entry and
one to an inline coefficient (proposal §5.1)."""


def test_a_scenario_switching_references_solves_as_the_hand_edited_project() -> None:
    project = _with_scenario(network(), *SWITCH)
    state, record = solve_case(
        Project.model_validate(project), SolveOptions(include_system_curve=False), "S1"
    )
    patched, states = hand_patched(project, SWITCH)
    assert states == ["applied"] * 4
    hand = _state(patched, include_system_curve=False)
    a, b = _dump(state), _dump(hand)
    for side in (a, b):
        side["trace"]["methods"]["sections"] = [
            s for s in side["trace"]["methods"]["sections"] if s["title"] != "Scenario"
        ]
        for element in side["trace"]["elements"].values():
            element["notes"] = [n for n in element["notes"] if not n.startswith("Scenario '")]
    assert a == b
    # and the hand-edited project solves as its own hand-typed twin
    assert (
        _dump(_state(hand_resolved(patched), include_system_curve=False))["linkResults"]["L5"][
            "flow"
        ]
        == b["linkResults"]["L5"]["flow"]
    )
    assert record is not None
    assert [o.base_value for o in record.overrides] == [
        {"materialId": "custom", "innerDiameter": 0.08, "roughness": 4.5e-5},
        {"specId": "PS1"},
        {"kind": "library", "id": "RS1"},
        {"kind": "library", "id": "RS2"},
    ]
    [scenario] = [s for s in state.trace.methods.sections if s.title == "Scenario"]
    assert scenario.items[1] == (
        'Connection L5, pipe 1: spec project library pipe spec "NPS 4 carbon steel, measured '
        'bore" (PS2) (base: custom, inner diameter 0.08 m, roughness 4.5e-05 m).'
    )
    assert scenario.items[3] == (
        'Component V1 (isolation valve): resistance project library resistance "Elbow at its own '
        'bore" (RS4) (base: project library resistance "Butterfly valve, open" (RS1)).'
    )


def test_value_texts_name_entries_by_name_and_id() -> None:
    project = Project.model_validate(network())
    assert value_text("spec", {"specId": "PS3"}, "", project) == (
        'project library pipe spec "Carbon steel, stated roughness" (PS3)'
    )
    assert value_text("resistance", {"kind": "library", "id": "RS5"}, "", project) == (
        'project library resistance "Unused entry" (RS5)'
    )
    assert value_text("resistance", {"kind": "library", "id": "RS9"}, "", project) == (
        "project library resistance RS9"
    )
    assert value_text("spec", {"specId": "PS1"}, "") == "project library pipe spec PS1"
    assert value_text("resistance", {"kind": "Cv", "value": 120.0}, "", project) == "Cv 120"


def test_a_scenario_referring_to_a_missing_entry_is_the_hand_edited_projects_topology_issue() -> (
    None
):
    change = {
        "kind": "component",
        "componentId": "V1",
        "field": "resistance",
        "value": {"kind": "library", "id": "RS9"},
    }
    project = _with_scenario(network(), change)
    with pytest.raises(ScenarioTopologyError) as raised:
        solve_case(Project.model_validate(project), None, "S1")
    patched, _ = hand_patched(project, [change])
    with pytest.raises(TopologyError) as hand:
        _state(patched)
    assert raised.value.issues == hand.value.issues
    assert raised.value.issues[0].code == "UNKNOWN_RESISTANCE"
    assert raised.value.scenario_id == "S1"


def test_a_spec_change_of_other_keys_says_how_a_spec_is_written() -> None:
    change = {
        "kind": "pipe",
        "connectionId": "L5",
        "pipeIndex": 0,
        "field": "spec",
        "value": {"specId": "PS2", "length": 3.0},
    }
    with pytest.raises(ScenarioOverrideError) as raised:
        apply_scenario(Project.model_validate(_with_scenario(network(), change)), "S1")
    [issue] = raised.value.issues
    assert issue.code == "invalid_pipe_spec"
    assert issue.message == (
        "body.project.scenarios.0.overrides.0.value: a pipe spec is an object with materialId and "
        "optionally schedule, nominalSize, innerDiameter, roughness, or with specId alone (a pipe "
        "spec of the project library), and no other key"
    )


# --------------------------------------------------------------------------- goal seek


def _goal_request(
    project: dict[str, Any], coefficient: str, lower: float, upper: float, target: float
) -> GoalSeekRequest:
    return GoalSeekRequest.model_validate(
        {
            "project": project,
            "variables": [
                {
                    "kind": "component",
                    "componentId": "V1",
                    "field": "resistance",
                    "lower": lower,
                    "upper": upper,
                    "coefficient": coefficient,
                }
            ],
            "goals": [{"quantity": "valve_flow", "elementId": "V1", "target": target}],
        }
    )


def test_a_goal_seek_starts_from_the_k_the_entry_gives_the_valve() -> None:
    """§5.2: a K variable on a valve whose entry is a K stated at another bore starts at that K on
    the valve's bore, K₀ (D/d₀)⁴ (the value the case holds); the trials and the override are
    inline K values in place of the reference."""
    project = network()
    flow = _state(project, include_system_curve=False).valve_results["V1"].flow
    request = _goal_request(project, "K", 0.05, 50.0, round(flow * 0.9, 6))
    [var] = prepare(request).variables
    assert var.case_number == 0.3 * (0.1 / 0.09) ** 4
    assert var.case_value == {"kind": "library", "id": "RS1"}
    assert var.base_value == {"kind": "library", "id": "RS1"}
    outcome = goal_seek_case(request)
    result = outcome.result
    assert result.met, result.message
    [variable] = result.variables
    assert variable.start_source == "case"
    assert variable.start == 0.3 * (0.1 / 0.09) ** 4
    assert variable.override is not None
    assert variable.value is not None
    override = variable.override.model_dump(mode="json")
    assert override["value"] == {"kind": "K", "value": variable.value}
    patched, states = hand_patched(project, [override])
    assert states == ["applied"]
    assert outcome.state is not None
    solved = _dump(_state(patched, include_system_curve=False))
    reported = _dump(outcome.state)
    for side in (solved, reported):
        side.pop("trace")
    assert solved == reported
    item = next(i for i in result.methods.items if i.startswith("Variable 1:"))
    assert (
        'from its project library resistance "Butterfly valve, open" (RS1), K 0.3 at 0.09 m' in item
    )
    assert item.endswith(
        "Each value tried is written on the valve as an inline K, in place of its project library "
        "entry, and so is the override reported."
    )
    note = outcome.state.trace.elements["V1"].notes[0]
    assert note.startswith("Goal seek set the resistance coefficient K here to K ")
    assert "which the value found replaces here" in note


def test_a_goal_seek_on_an_entry_of_another_kind_starts_in_the_middle() -> None:
    project = network()
    request = _goal_request(project, "Cv", 10.0, 1000.0, 0.01)
    [var] = prepare(request).variables
    assert var.case_number is None
    assert (
        var.library_text
        == 'project library resistance "Butterfly valve, open" (RS1), K 0.3 at 0.09 m'
    )
    project["components"][3]["resistance"] = {"kind": "library", "id": "RS2"}
    [cv] = prepare(_goal_request(project, "Cv", 10.0, 1000.0, 0.01)).variables
    assert cv.case_number == 400.0
