"""The project library through the public API, tested independently of its implementation
(docs/proposals/project-library.md §7.1; CLAUDE.md D6, D13, D22).

Written from the proposal, the specs and the models by a tester who did not read ``services/``
or the API builder's tests. Every project goes through ``POST /api/v1/solve``, ``/system-curve``
or ``/goal-seek``; the closed forms are ``derivations_project_library``'s. A library entry is a
reference (owner's answer Q1): resolving it must give exactly the values a user could have typed
by hand (proposal §1.3 decision 4, §3.1), so most checks are metamorphic, bit for bit: two
projects that differ only in whether a value comes from the library or is typed inline give
the same ``solvedState`` apart from its ``timestamp`` and ``trace`` (the trace names the entry
and its source, §4), and apart from the ``source`` text of a fitting whose K comes from an entry
(the fitting's label, §3.2). "Bit for bit" compares the response JSON, whose floats round-trip
exactly.

1. **A spec equals the pipe it stands for** (§7.1 item 1). Every reference case, the unit-test
   data networks, three seeds of each fuzz profile and a ladder of library pipes are solved as
   they are and with every distinct pipe lifted into a pipe spec, every valve resistance and
   fitting K into a resistance entry (a K at the bore of its element: (D/d₀)⁴ = 1 exactly), each
   segment, valve and fitting referring to its entry: bit for bit. A library pipe is lifted as a
   spec on its material holding its bore and roughness, as a custom spec holding them, and as a
   spec on its material with its bore alone (the material's Farshad roughness at that bore, which
   is the data file's roughness for every cited size, bit for bit:
   ``test_the_cited_roughness_is_farshad_at_its_bore``). The ladder's system curve, too, and its
   D19 pipe velocity checks.
2. **NPS 60 by hand** (item 2): the flow through one pipe on an NPS 60 STD spec, from
   Darcy–Weisbach and Colebrook solved exactly for v, within D6 and within 10⁻⁶ (the material's
   average roughness instead of Farshad at the bore moves it 0.28 %, inside D6); the spec's
   outer diameter and nominal size change nothing.
3. **K at a stated bore** (item 3): a valve on K₀ = 0.30 at d₀ = 0.7366 m used on 0.74295 m; its
   K is K₀ (D/d₀)⁴ and its loss K₀ (Q/A₀)²/2g; the same valve with that K typed inline gives the
   same state, bit for bit with the K the API reports and within 10⁻¹² with the K computed here.
   Entries on two reducers, a custom fitting and a valve whose ports have different bores, in
   reverse flow, meet the bore-free closed form (an entry's loss at a flow does not depend on the
   bore it is converted on); a K entry above kOverride's 10⁴ on its fitting is used as it is;
   an entry on a valve beyond Crane's table takes the place of the default and its range flag.
4. **Cv and Kv entries** (item 4) on an isolation, a check and a failed-open control valve and on
   inline fittings equal the coefficients typed inline, bit for bit; an edit to a shared entry,
   or to a spec, reaches every element that uses it (Q1).
5. **Errors** (item 5): dangling references are 422 with the other topology issues
   (UNKNOWN_PIPE_SPEC, UNKNOWN_RESISTANCE, naming the ids); entries that break their rules are
   400 VALIDATION_ERROR; neither echoes an entry's name, source or value (D10, §2.3). What the
   slice leaves out (an entry as a scenario target or goal-seek variable, a rating from the
   library, a 101st entry) is 400; an id in both lists resolves in its own list, or is refused.
6. **Scenarios and goal seek** (item 6, §5): a scenario that switches a pipe to a spec, a spec
   pipe back to the cited library or to another spec, or a valve to an entry equals the
   hand-edited project bit for bit, and one that names a missing entry fails as it does; a goal
   seek on a valve that refers to an entry (starting at the case's value, a K entry's being its K
   on the valve's bore, clipped into the bounds; or in the middle), in a scenario that points the
   valve at an entry, and on the length of a spec pipe, reports an override that, applied by
   hand or as a scenario and solved, gives its state bit for bit; a case that already meets the
   goal stops at its start.
7. **No library, no change**: a project without library fields round-trips without them, and
   empty lists are dropped (§1.3 decision 5); its methods summary has no "Project library"
   section, which a project with a library has, listing its entries with their sources (§4.2).
"""

import copy
import functools
import itertools
import json
import math
import re
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

import fluids.friction
import httpx
import pytest
from fastapi.testclient import TestClient

import opensolve_pipe
from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from tests.differential import networks
from tests.differential.generator import ASSIGNED_FLOW, DEFAULT, FLOW_CONTROL, generate
from tests.reference import derivations_project_library as dl
from tests.reference.case_format import (
    case_files,
    equipment,
    isolation_valve,
    rated_coefficient,
    reservoir,
)

SOLVE = "/api/v1/solve"
CURVE = "/api/v1/system-curve"
GOAL_SEEK = "/api/v1/goal-seek"
PLAIN = {"includeSystemCurve": False}
RELATIVE = 0.005  # D6
FLOW_FLOOR = 1.0e-9  # m³/s
HEAD_FLOOR = 0.01  # m
TIGHT = 1.0e-6
"""Relative agreement of a closed-form flow where D6 cannot tell a wrong value apart (NPS 60's
roughness, a K moved to the wrong bore). The solver stops at 10⁻⁷ m of energy residual (D7),
about 10⁻⁷ of these lines' heads, so 10⁻⁶ leaves a margin of ten."""
ROUND_OFF = 1.0e-14
"""Relative agreement of two evaluations of one formula (a K moved by (D/d₀)⁴, Farshad at a bore)
that may group their operations differently: a few units in the last place."""
CONVERSION = 1.0e-12
"""Relative agreement of a converted K with fluids' ``Cv_to_K`` / ``Kv_to_K``, the conversion
TSD §5.3 names (written out differently, it may differ by round-off)."""
TWIN = 1.0e-12
"""Relative agreement of every number of two solves whose inputs differ by round-off (a K typed
here against the one the API derives): far above the solver's response to a last-bit change of
one K, far below any difference a wrong conversion makes."""
ENERGY_STOP_ABSOLUTE = 1.0e-7
ENERGY_STOP_ROUND_OFF = 4.0 * 2.0**-52
"""The energy stop test (CLAUDE.md D7): 10⁻⁷ m + 4ε·max(|H|)."""
LIBRARY_SECTION = "project library"
SENTINEL = "SENTINEL-9c4e"
SENTINEL_DIGITS = "1234567"
"""Text and digits that must never come back in an error (D10; proposal §2.3)."""
GOAL_SEEK_SECTION = "Goal seek"
SCENARIO_SECTION = "Scenario"

# --------------------------------------------------------------------------- the API

_addresses = itertools.count(1)


class Api:
    """POST through the app from a client address of its own, changed every 40 requests: the
    rate limit (60 a minute per client) is never reached, and no bucket is shared with the rest
    of the suite."""

    def __init__(self) -> None:
        self._client = self._new()
        self._sent = 0

    @staticmethod
    def _new() -> TestClient:
        n = next(_addresses)
        return TestClient(app, client=(f"10.77.{n // 256 % 256}.{n % 256}", 50000))

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self._sent == 40:
            self._client, self._sent = self._new(), 0
        self._sent += 1
        response: httpx.Response = self._client.post(path, json=body)
        return response

    def solve(self, project: dict[str, Any], scenario_id: str | None = None) -> httpx.Response:
        body: dict[str, Any] = {"project": project, "options": PLAIN}
        if scenario_id is not None:
            body["scenarioId"] = scenario_id
        return self.post(SOLVE, body)

    def solved(self, project: dict[str, Any], scenario_id: str | None = None) -> dict[str, Any]:
        """The solvedState of a solve that must succeed."""
        response = self.solve(project, scenario_id)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        state: dict[str, Any] = response.json()["solvedState"]
        return state


@pytest.fixture(scope="module")
def api() -> Api:
    return Api()


# --------------------------------------------------------------------------- comparing


def values(state: dict[str, Any], labelled: Collection[tuple[str, int]] = ()) -> dict[str, Any]:
    """A solved state without what may differ between a project that takes a value from the
    library and the same project with it typed inline: the timestamp, the trace (which names
    the entry, §4.1-§4.2) and the source label of each fitting in ``labelled`` (§3.2)."""
    out = {k: v for k, v in copy.deepcopy(state).items() if k not in ("timestamp", "trace")}
    for cid, index in labelled:
        link = out["linkResults"].get(cid)  # none for a connection a failed solve leaves out
        if link is not None:
            link["fittings"][index].pop("source", None)
    return out


def differences(got: Any, want: Any, path: str = "", limit: int = 12) -> list[str]:
    """Where ``got`` differs from ``want``, bit for bit (a float equals only the same float)."""
    out: list[str] = []

    def walk(a: Any, b: Any, at: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                if key not in a:
                    out.append(f"{at}.{key}: missing")
                elif key not in b:
                    out.append(f"{at}.{key}: unexpected {a[key]!r:.200}")
                else:
                    walk(a[key], b[key], f"{at}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                out.append(f"{at}: {len(a)} items, expected {len(b)}")
            for i, (x, y) in enumerate(zip(a, b, strict=False)):
                walk(x, y, f"{at}[{i}]")
        elif type(a) is not type(b) or a != b:
            out.append(f"{at}: {a!r:.200} != {b!r:.200}")

    walk(got, want, path)
    return out


def near_differences(got: Any, want: Any, rel: float, path: str = "") -> list[str]:
    """Where ``got`` differs from ``want`` by more than ``rel`` of the larger magnitude in a
    number (texts, flags and booleans exactly)."""
    out: list[str] = []

    def walk(a: Any, b: Any, at: str) -> None:
        if len(out) >= 12:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            if a.keys() != b.keys():
                out.append(f"{at}: keys {sorted(a.keys() ^ b.keys())}")
            for key in sorted(a.keys() & b.keys()):
                walk(a[key], b[key], f"{at}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                out.append(f"{at}: {len(a)} items, expected {len(b)}")
            for i, (x, y) in enumerate(zip(a, b, strict=False)):
                walk(x, y, f"{at}[{i}]")
        elif isinstance(a, float | int) and isinstance(b, float | int) and not isinstance(a, bool):
            if abs(a - b) > rel * max(abs(a), abs(b)):
                out.append(f"{at}: {a!r} != {b!r}")
        elif a != b:
            out.append(f"{at}: {a!r:.200} != {b!r:.200}")

    walk(got, want, path)
    return out


def within_d6(got: float, want: float, floor: float) -> bool:
    return abs(got - want) <= max(RELATIVE * abs(want), floor)


def text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def library_section(state: dict[str, Any]) -> dict[str, Any] | None:
    """The methods summary's "Project library" section (§4.2), or None."""
    found = [
        s
        for s in state["trace"]["methods"]["sections"]
        if s["title"].lower().startswith(LIBRARY_SECTION)
    ]
    assert len(found) <= 1, [s["title"] for s in found]
    return found[0] if found else None


def mentions_entry(trace: Any, entry: dict[str, Any]) -> bool:
    """The trace names the entry (by id) and gives its source (§4.1)."""
    body = text(trace)
    return entry["id"] in body and entry["source"] in body


def mentions_number(trace: Any, x: float) -> bool:
    """A trace states x: as a number among its inputs or intermediates, or written in its text
    with 3 to 6 significant digits (not as the start of a longer number)."""
    numbers = [
        item["value"]
        for key in ("inputs", "intermediates")
        for item in trace.get(key, [])
        if isinstance(item["value"], float | int) and not isinstance(item["value"], bool)
    ]
    if any(abs(n - x) <= ROUND_OFF * abs(x) for n in numbers):
        return True
    body = text(trace)
    return any(
        re.search(rf"(?<![0-9.]){re.escape(f'{x:.{digits}g}')}(?![0-9])", body)
        for digits in range(3, 7)
    )


def method_version(state: dict[str, Any]) -> tuple[int, ...]:
    return tuple(int(part) for part in state["methodVersion"].split("."))


def entry_json(project: dict[str, Any], entry_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        e
        for e in project.get("pipeLibrary", []) + project.get("resistanceLibrary", [])
        if e["id"] == entry_id
    )
    return found


def library_problems(
    state: dict[str, Any], project: dict[str, Any], users: dict[str, list[str]]
) -> list[str]:
    """§4.1-§4.2: each element that uses an entry (``users``: element id -> entry ids) names it
    with its source in its trace; the "Project library" section gives every entry used with its
    source, and every entry nobody uses under "not used"."""
    problems = []
    for element, entry_ids in users.items():
        trace = state["trace"]["elements"].get(element)
        if trace is None:
            problems.append(f"{element}: no trace")
            continue
        for entry_id in entry_ids:
            if not mentions_entry(trace, entry_json(project, entry_id)):
                problems.append(f"{element}'s trace does not name {entry_id} with its source")
    section = library_section(state)
    if section is None:
        return [*problems, "no Project library section in the methods summary"]
    used = {e for ids in users.values() for e in ids}
    for entry in project.get("pipeLibrary", []) + project.get("resistanceLibrary", []):
        if entry["id"] in used and not mentions_entry(section, entry):
            problems.append(f"the Project library section does not give {entry['id']}'s source")
        if entry["id"] not in used:
            if entry["id"] not in text(section):
                problems.append(f"the Project library section omits {entry['id']} (not used)")
            if "not used" not in text(section).lower():
                problems.append("the Project library section has no entry under 'not used'")
    return problems


# --------------------------------------------------------------------------- lifting values


def _materials() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (Path(opensolve_pipe.__file__).parent / "data" / "pipe_materials.json").read_text()
    )
    return {m["id"]: m for m in data["materials"]}


MATERIALS = _materials()


def cited_size(pipe: dict[str, Any]) -> dict[str, Any]:
    """The data file's size of a library pipe (material, schedule, nominal size as written)."""
    schedule = next(
        s for s in MATERIALS[pipe["materialId"]]["schedules"] if s["id"] == pipe["schedule"]
    )
    nominal = pipe["nominalSize"]
    size: dict[str, Any] = min(schedule["sizes"], key=lambda s: abs(s["nominalSize"] - nominal))
    assert abs(size["nominalSize"] - nominal) <= 1.0e-9 * nominal, pipe
    return size


def resolved(pipe: dict[str, Any]) -> tuple[float, float]:
    """(inner diameter, roughness) a pipe is solved with (SDD §4.3, proposal §1.2): a custom
    pipe's own; a library pipe's bore and roughness overrides, else the data file's per-size
    values, or the material's Farshad roughness at an overridden bore."""
    if pipe["materialId"] == "custom":
        return pipe["innerDiameter"], pipe["roughness"]
    if pipe.get("innerDiameter") is not None:
        d = pipe["innerDiameter"]
        surface = MATERIALS[pipe["materialId"]]["roughnessModel"]["ID"]
        farshad = float(fluids.friction.roughness_Farshad(ID=surface, D=d))
        return d, pipe["roughness"] if pipe.get("roughness") is not None else farshad
    size = cited_size(pipe)
    roughness = pipe.get("roughness")
    return size["innerDiameter"], size["roughness"] if roughness is None else roughness


def end_pipe(project: dict[str, Any], component_id: str, port_id: str) -> dict[str, Any] | None:
    """The pipe segment at a port: the end segment of the connection on it."""
    for c in project["connections"]:
        pipes = c["piping"]["pipes"]
        if (c["toComponentId"], c["toPortId"]) == (component_id, port_id):
            last: dict[str, Any] = pipes[-1]
            return last
        if (c["fromComponentId"], c["fromPortId"]) == (component_id, port_id):
            first: dict[str, Any] = pipes[0]
            return first
    return None


MAX_ENTRIES = 100
"""Entries per list (proposal §2.1-§2.2)."""
LIFTS = ("material", "custom", "farshad")
"""How a library pipe becomes a spec: on its material with its bore and roughness, as a custom
spec with them, or on its material with its bore alone (Farshad at that bore). A custom pipe
becomes a custom spec in every lift."""


class Lifted:
    """A project with its pipes, valve resistances and fitting K values moved into the project
    library (§7.1 item 1; the lift of §7.2's corpus check, written independently): one entry per
    distinct value set, each element referring to its entry. A K becomes a K entry at the bore it
    is used on (the valve's inlet pipe, the fitting's pipe pipeIndex), so (D/d₀)⁴ = 1 exactly:
    x/x is 1 in IEEE 754 for every finite nonzero x."""

    def __init__(self, base: dict[str, Any], lift: str) -> None:
        self.project = copy.deepcopy(base)
        self.specs: dict[str, dict[str, Any]] = {}
        self.entries: dict[str, dict[str, Any]] = {}
        self.users: dict[str, list[str]] = {}
        """Element id -> the ids of the entries it uses."""
        self.labelled: set[tuple[str, int]] = set()
        """(connection id, fitting index) of every fitting whose K comes from an entry."""
        for component in self.project["components"]:
            resistance = component.get("resistance")
            if resistance is None:
                continue
            coefficient = {"kind": resistance["kind"], "value": resistance["value"]}
            if resistance["kind"] == "K":
                pipe = end_pipe(base, component["id"], "inlet")
                if pipe is None:
                    continue
                coefficient["referenceDiameter"] = resolved(pipe)[0]
            entry_id = self._add(self.entries, "RS", coefficient, f"valve {component['id']}")
            if entry_id is not None:
                component["resistance"] = {"kind": "library", "id": entry_id}
                self._use(component["id"], entry_id)
        for c in self.project["connections"]:
            pipes = c["piping"]["pipes"]
            for j, fitting in enumerate(c["piping"]["fittings"]):
                if fitting.get("kOverride") is None:
                    continue
                d = resolved(pipes[fitting.get("pipeIndex", 0)])[0]
                k = {"kind": "K", "value": fitting["kOverride"], "referenceDiameter": d}
                entry_id = self._add(self.entries, "RS", k, f"fitting {j + 1} of {c['id']}")
                if entry_id is not None:
                    del fitting["kOverride"]
                    fitting["resistanceId"] = entry_id
                    self.labelled.add((c["id"], j))
                    self._use(c["id"], entry_id)
        for c in self.project["connections"]:
            pipes = c["piping"]["pipes"]
            for i, pipe in enumerate(pipes):
                spec = self._spec(pipe, lift)
                spec_id = self._add(self.specs, "PS", spec, f"pipe {i + 1} of {c['id']}")
                if spec_id is not None:
                    pipes[i] = {"specId": spec_id, "length": pipe["length"]}
                    self._use(c["id"], spec_id)
        if self.specs:
            self.project["pipeLibrary"] = list(self.specs.values())
        if self.entries:
            self.project["resistanceLibrary"] = list(self.entries.values())

    def _use(self, element: str, entry_id: str) -> None:
        ids = self.users.setdefault(element, [])
        if entry_id not in ids:
            ids.append(entry_id)

    @staticmethod
    def _spec(pipe: dict[str, Any], lift: str) -> dict[str, Any]:
        d, roughness = resolved(pipe)
        material = pipe["materialId"]
        if material == "custom" or lift == "custom":
            return {"materialId": "custom", "innerDiameter": d, "roughness": roughness}
        if lift == "farshad" and pipe.get("roughness") is None:
            return {"materialId": material, "innerDiameter": d}
        return {"materialId": material, "innerDiameter": d, "roughness": roughness}

    @staticmethod
    def _add(
        table: dict[str, dict[str, Any]], prefix: str, held: dict[str, Any], where: str
    ) -> str | None:
        """The id of the entry of ``table`` holding exactly ``held`` (added when new), or None
        when the list is full (100 entries, proposal §2.1): the element keeps its own value."""
        for entry_id, entry in table.items():
            if {k: v for k, v in entry.items() if k not in ("id", "name", "source")} == held:
                return entry_id
        if len(table) == MAX_ENTRIES:
            return None
        entry_id = f"{prefix}{len(table) + 1}"
        table[entry_id] = {
            "id": entry_id,
            "name": f"Lifted {entry_id}",
            "source": f"Test: lifted from {where} (proposal 7.1 item 1)",
            **held,
        }
        return entry_id


def _file_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    project: dict[str, Any] = data.get("project", data)
    return {k: v for k, v in project.items() if k != "scenarios"}


def _generated(seed: int, profile: str) -> dict[str, Any]:
    data: dict[str, Any] = generate(seed, profile).model_dump(mode="json", exclude_unset=True)
    return data


def _ladder() -> dict[str, Any]:
    data: dict[str, Any] = networks.ladder(7, 1, "crane", True).model_dump(
        mode="json", exclude_unset=True
    )
    return data


def _networks() -> dict[str, Callable[[], dict[str, Any]]]:
    out: dict[str, Callable[[], dict[str, Any]]] = {}
    for path in case_files():
        out[f"ref_{path.stem}"] = functools.partial(_file_json, path)
    api_root = Path(__file__).resolve().parents[2]
    for path in sorted(api_root.glob("tests/unit/data/*/*.json")):
        out[f"unit_{path.stem}"] = functools.partial(_file_json, path)
    for prefix, profile, seeds in (
        ("fuzz", DEFAULT, (0, 1000, 2000)),
        ("fuzzfc", FLOW_CONTROL, (10_000, 10_333, 10_666)),
        ("fuzzaf", ASSIGNED_FLOW, (20_000, 20_333, 20_666)),
    ):
        for seed in seeds:
            out[f"{prefix}_{seed}"] = functools.partial(_generated, seed, profile)
    out["ladder_7_library"] = _ladder
    return out


NETWORKS = _networks()


def _has_library_pipes(project: dict[str, Any]) -> bool:
    return any(
        p["materialId"] != "custom" for c in project["connections"] for p in c["piping"]["pipes"]
    )


LIFT_RUNS = [
    (name, lift)
    for name, load in NETWORKS.items()
    for lift in (LIFTS if _has_library_pipes(load()) else LIFTS[:1])
]


def test_the_cited_roughness_is_farshad_at_its_bore() -> None:
    """Every cited size's roughness in data/pipe_materials.json is its material's Farshad
    roughness at the size's inner diameter, bit for bit (the data's own "per size: evaluated at
    the inner diameter"), so a spec on that material with the bore alone must solve as the cited
    pipe, bit for bit (§2.1)."""
    for material in MATERIALS.values():
        surface = material["roughnessModel"]["ID"]
        for schedule in material["schedules"]:
            for size in schedule["sizes"]:
                d = size["innerDiameter"]
                assert fluids.friction.roughness_Farshad(ID=surface, D=d) == size["roughness"]


@pytest.mark.parametrize(("network", "lift"), LIFT_RUNS, ids=[f"{n}-{x}" for n, x in LIFT_RUNS])
def test_entries_equal_the_values_they_stand_for(api: Api, network: str, lift: str) -> None:
    """§7.1 items 1 and 4 (module docstring, item 1): the lifted project solves as the project
    with its values inline, bit for bit, and its traces and methods name the entries with their
    sources (§4)."""
    base = NETWORKS[network]()
    lifted = Lifted(base, lift)
    assert lifted.specs, "every network has pipes"
    Project.model_validate(lifted.project)
    want = api.solve(base)
    got = api.solve(lifted.project)
    assert got.status_code == want.status_code, got.text[:2000]
    if want.status_code != 200:  # an error of the network itself: the same error
        assert got.json()["error"] == want.json()["error"], got.text[:2000]
        return
    state, base_state = got.json()["solvedState"], want.json()["solvedState"]
    assert not differences(
        values(state, lifted.labelled), values(base_state, lifted.labelled), network
    ), differences(values(state, lifted.labelled), values(base_state, lifted.labelled), network)
    if base_state["converged"]:
        problems = library_problems(state, lifted.project, lifted.users)
        assert not problems, problems


def test_the_system_curve_of_a_lifted_network(api: Api) -> None:
    """§3.1: /system-curve resolves the library as /solve does: the ladder's pump curve point for
    point, lifted as cited specs and as custom ones."""
    base = _ladder()
    pump = next(c["id"] for c in base["components"] if c["type"] == "pump")
    body = {"pumpId": pump, "numPoints": 7}
    want = api.post(CURVE, {"project": base, **body})
    assert want.status_code == 200, want.text[:2000]
    for lift in ("material", "custom"):
        got = api.post(CURVE, {"project": Lifted(base, lift).project, **body})
        assert got.status_code == 200, got.text[:2000]
        assert not differences(got.json(), want.json(), lift), differences(
            got.json(), want.json(), lift
        )


def test_design_checks_on_spec_pipes(api: Api) -> None:
    """D19's pipe velocity check reads solved values only, so it gives the same results on spec
    pipes as on the pipes they stand for: the ladder with the check on, lifted, bit for bit
    (``designChecks`` included), with some pipes passing and some failing."""
    base = _ladder()
    base["settings"]["designChecks"] = {
        "pipeVelocity": {"minimum": 0.3, "maximum": 1.2, "source": {"kind": "user"}}
    }
    want = api.solved(base)
    statuses = {c["outcome"] for c in want["designChecks"]}
    assert {"pass", "fail"} <= statuses, statuses
    for lift in ("material", "custom", "farshad"):
        lifted = Lifted(base, lift)
        got = api.solved(lifted.project)
        assert not differences(values(got, lifted.labelled), values(want, lifted.labelled)), (
            lift,
            differences(values(got, lifted.labelled), values(want, lifted.labelled)),
        )


# --------------------------------------------------------------------------- NPS 60 (item 2)


def test_nps60_spec_by_hand(api: Api) -> None:
    """§7.1 item 2 (``derivations_project_library.nps60_line``): the flow within D6 and 10⁻⁶ of
    Colebrook solved exactly, the segment solved on the spec's bore and Farshad's roughness at
    it (§1.2: 3.397×10⁻⁵ m), and the trace and methods naming the spec and its source, the bore
    labelled user data and the nominal size stated (§4.1)."""
    case = dl.nps60_line()
    state = api.solved(case.project)
    assert state["converged"], state["convergence"]
    link = state["linkResults"]["L1"]
    q, want = link["flow"], case.flows["L1"]
    d, eps = case.segments[("L1", 0)]
    segment = link["segments"][0]
    assert segment["innerDiameter"] == d
    assert abs(segment["roughness"] - eps) <= ROUND_OFF * eps, (segment["roughness"], eps)
    assert within_d6(q, want, FLOW_FLOOR), (q, want)
    assert abs(q - want) <= TIGHT * want, f"flow {q!r}, closed form {want!r}: {q / want - 1:.3e}"
    for key, h in (("R1:port_1", 12.0), ("R2:port_1", 10.5)):
        assert state["nodeResults"][key]["egl"] == pytest.approx(h, abs=1.0e-12)
    problems = library_problems(state, case.project, {"L1": ["PS60"]})
    assert not problems, problems
    # §4.1: the spec's values are user data in the trace (D10's labels unchanged), and the trace
    # states the spec's nominal size.
    trace = state["trace"]["elements"]["L1"]
    bores = [i for i in trace["inputs"] if i["value"] == d]
    assert bores, trace["inputs"]
    assert all(i["source"] == "user" for i in bores), bores
    assert mentions_number(trace, dl.NPS60_OD), trace


def test_nps60_tight_check_tells_the_roughness_apart() -> None:
    """Why item 2 checks 10⁻⁶ besides D6: the carbon-steel average roughness (3.6×10⁻⁵ m) in
    place of Farshad at the 59.25 in bore moves the closed-form flow by 0.28 %, which D6 accepts,
    and by far more than 10⁻⁶."""
    case = dl.nps60_line()
    other = dl.nps60_flow_with_roughness(case.data["material_roughness"])
    change = abs(other / case.flows["L1"] - 1.0)
    assert 1.0e3 * TIGHT < change < RELATIVE, change


def test_a_spec_s_display_fields_change_nothing(api: Api) -> None:
    """§2.1: a spec's outerDiameter and nominalSize are for display (and the web's port sizes)
    only: the NPS 60 spec without them solves bit for bit as with them."""
    case = dl.nps60_line()
    bare = copy.deepcopy(case.project)
    spec = bare["pipeLibrary"][0]
    del spec["outerDiameter"], spec["nominalSize"]
    assert not differences(values(api.solved(bare)), values(api.solved(case.project)))


# --------------------------------------------------------------------------- K at a bore (item 3)


def _inline(project: dict[str, Any], resistances: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The project with the valves' resistances typed inline and no resistance library."""
    out = copy.deepcopy(project)
    out.pop("resistanceLibrary", None)
    for component in out["components"]:
        if component["id"] in resistances:
            component["resistance"] = resistances[component["id"]]
    return out


def test_k_entry_at_its_stated_bore(api: Api) -> None:
    """§7.1 item 3 (``derivations_project_library.k_entry_valve``, §3.3): K = K₀ (D/d₀)⁴ on the
    valve's inlet pipe, its loss K₀ (Q/A₀)²/2g at the solved flow (to the energy stop
    tolerance), the flow within D6 and 10⁻⁶ of the closed form; the same valve with that K
    inline gives the same state, bit for bit with the K the API reports (the project the solver
    sees), and within 10⁻¹² with K₀·(D/d₀)**4 computed here, bit for bit when that double is the
    API's."""
    case = dl.k_entry_valve()
    state = api.solved(case.project)
    assert state["converged"], state["convergence"]
    valve = state["valveResults"]["V1"]
    k, d = case.valves["V1"]
    assert valve["state"] == "open"
    assert valve["referenceDiameter"] == d
    assert abs(valve["kOpen"] - k) <= ROUND_OFF * k, (valve["kOpen"], k)
    q = state["linkResults"]["L1"]["flow"]
    for cid, want in case.flows.items():
        got = state["linkResults"][cid]["flow"]
        assert within_d6(got, want, FLOW_FLOOR), (cid, got, want)
        assert abs(got - want) <= TIGHT * want, (cid, got, want, got / want - 1)
    a0 = math.pi * case.data["d0"] ** 2 / 4.0
    loss = case.data["k0"] * (q / a0) ** 2 / (2.0 * dl.G)
    h_in, h_out = (state["nodeResults"][f"V1:{p}"]["egl"] for p in ("inlet", "outlet"))
    stop = ENERGY_STOP_ABSOLUTE + ENERGY_STOP_ROUND_OFF * max(abs(h_in), abs(h_out))
    assert abs(valve["headLoss"] - loss) <= stop, (valve["headLoss"], loss)
    assert abs(h_in - h_out - loss) <= stop, (h_in - h_out, loss)
    assert within_d6(valve["headLoss"], case.valve_head_loss["V1"], HEAD_FLOOR)

    reported = _inline(case.project, {"V1": {"kind": "K", "value": valve["kOpen"]}})
    twin = api.solved(reported)
    assert not differences(values(twin), values(state)), differences(values(twin), values(state))

    mine = case.data["k0"] * (case.data["d"] / case.data["d0"]) ** 4
    by_hand = api.solved(_inline(case.project, {"V1": {"kind": "K", "value": mine}}))
    if mine == valve["kOpen"]:
        assert not differences(values(by_hand), values(state))
    else:
        assert not near_differences(values(by_hand), values(state), TWIN)

    trace = state["trace"]["elements"]["V1"]
    entry = entry_json(case.project, "RS30")
    assert mentions_entry(trace, entry), trace["notes"]
    for x in (case.data["k0"], case.data["d0"], d, k):
        assert mentions_number(trace, x), (x, trace)
    problems = library_problems(state, case.project, {"V1": ["RS30"], "L1": ["PS30"]})
    assert not problems, problems
    assert method_version(state) >= (1, 5, 0), state["methodVersion"]


def test_an_entry_replaces_the_crane_default_and_its_flag(api: Api) -> None:
    """§1.1-§1.2 (P5): Crane's butterfly valve K is tabulated up to NPS 24, so the 0.74295 m valve
    on its Crane default is flagged CORRELATION_OUT_OF_RANGE; on a library entry it takes the
    entry's K in place of the default, and the flag, which is about the default's correlation,
    goes with it, as with an inline resistance."""
    case = dl.k_entry_valve()
    on_entry = api.solved(case.project)
    crane = copy.deepcopy(case.project)
    del next(c for c in crane["components"] if c["id"] == "V1")["resistance"]
    del crane["resistanceLibrary"]
    on_default = api.solved(crane)

    def range_flags(state: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            f
            for f in state["flags"]
            if f["code"] == "CORRELATION_OUT_OF_RANGE" and f["componentId"] == "V1"
        ]

    assert range_flags(on_default), on_default["flags"]
    assert not range_flags(on_entry), on_entry["flags"]
    assert on_default["valveResults"]["V1"]["kOpen"] != on_entry["valveResults"]["V1"]["kOpen"]


# --------------------------------------------------------------------------- Cv and Kv (item 4)

ENTRY_OF = {"V1": dl.CV900, "CV1": dl.KV700, "V2": dl.CV900, "PRV1": dl.K08}
FITTING_ENTRY = {0: dl.CV900, 1: dl.KV700, 2: dl.K08}


def _inline_fittings(project: dict[str, Any], ks: dict[int, float]) -> dict[str, Any]:
    """L2's fittings with kOverride = ks[index] in place of their resistanceId."""
    out = copy.deepcopy(project)
    l2 = next(c for c in out["connections"] if c["id"] == "L2")
    for j, k in ks.items():
        fitting = l2["piping"]["fittings"][j]
        del fitting["resistanceId"]
        fitting["kOverride"] = k
    return out


def test_coefficient_entries_equal_inline_values(api: Api) -> None:
    """§7.1 item 4 (``derivations_project_library.coefficient_entries``): each valve and fitting
    takes its entry's K on its own bore (a Cv or Kv by fluids' conversion, TSD §5.3, and by its
    definition; a K moved by (D/d₀)⁴), the flow is the closed form's; the valves with their Cv
    and Kv typed inline (the K entry's K as reported) and the fittings with their reported K as
    kOverride give the same state bit for bit; so do the fittings with the K converted here, or
    within 10⁻¹² where that double is not the API's."""
    case = dl.coefficient_entries()
    state = api.solved(case.project)
    assert state["converged"], state["convergence"]
    for cid, want in case.flows.items():
        got = state["linkResults"][cid]["flow"]
        assert within_d6(got, want, FLOW_FLOOR), (cid, got, want)
        assert abs(got - want) <= TIGHT * want, (cid, got, want, got / want - 1)
    for vid, (k, d) in case.valves.items():
        valve = state["valveResults"][vid]
        entry = ENTRY_OF[vid]
        assert valve["state"] == "open", (vid, valve["state"])
        assert valve["referenceDiameter"] == d, vid
        assert abs(valve["kOpen"] - k) <= dl.CONVERSION_AGREEMENT * k, (vid, valve["kOpen"], k)
        if entry.kind != "K":
            exact = dl.fluids_k(entry.kind, entry.value, d)
            assert abs(valve["kOpen"] - exact) <= CONVERSION * exact, (vid, valve["kOpen"], exact)
        else:
            assert abs(valve["kOpen"] - k) <= ROUND_OFF * k, (vid, valve["kOpen"], k)
        assert within_d6(valve["headLoss"], case.valve_head_loss[vid], HEAD_FLOOR), vid
    reported_fittings = state["linkResults"]["L2"]["fittings"]
    for (cid, j), (k, d) in case.fittings.items():
        fitting = reported_fittings[j]
        assert fitting["referenceDiameter"] == d, (cid, j)
        assert fitting["quantity"] == case.data["quantities"][(cid, j)]
        entry = FITTING_ENTRY[j]
        exact = dl.fluids_k(entry.kind, entry.value, d) if entry.kind != "K" else k
        assert abs(fitting["k"] - exact) <= CONVERSION * exact, (j, fitting["k"], exact)
        assert abs(fitting["k"] - k) <= dl.CONVERSION_AGREEMENT * k, (j, fitting["k"], k)

    labelled = {("L2", j) for j in FITTING_ENTRY}
    inline: dict[str, dict[str, Any]] = {
        vid: {"kind": e.kind, "value": e.value} for vid, e in ENTRY_OF.items() if e.kind != "K"
    }
    inline["PRV1"] = {"kind": "K", "value": state["valveResults"]["PRV1"]["kOpen"]}
    twin = _inline_fittings(
        _inline(case.project, inline), {j: f["k"] for j, f in enumerate(reported_fittings)}
    )
    got = values(api.solved(twin), labelled)
    assert not differences(got, values(state, labelled)), differences(got, values(state, labelled))

    mine = {
        j: dl.fluids_k(e.kind, e.value, case.fittings[("L2", j)][1])
        if e.kind != "K"
        else case.fittings[("L2", j)][0]
        for j, e in FITTING_ENTRY.items()
    }
    by_hand = values(api.solved(_inline_fittings(_inline(case.project, inline), mine)), labelled)
    if all(mine[j] == f["k"] for j, f in enumerate(reported_fittings)):
        assert not differences(by_hand, values(state, labelled))
    else:
        assert not near_differences(by_hand, values(state, labelled), TWIN)

    users = {
        "V1": ["RSCV"],
        "CV1": ["RSKV"],
        "V2": ["RSCV"],
        "PRV1": ["RSK"],
        "L2": ["RSCV", "RSKV", "RSK", "PSA", "PSB"],
        "L1": ["PSA"],
        "L3": ["PSB"],
    }
    problems = library_problems(state, case.project, users)
    assert not problems, problems


def test_an_edit_to_an_entry_reaches_every_user(api: Api) -> None:
    """Q1 (references): RSCV edited from Cv 900 to Cv 600 changes V1, V2 and L2's first fitting
    together: each K is the new Cv's on its own bore."""
    case = dl.coefficient_entries()
    project = copy.deepcopy(case.project)
    entry = next(e for e in project["resistanceLibrary"] if e["id"] == "RSCV")
    entry["value"] = 600.0
    state = api.solved(project)
    assert state["converged"], state["convergence"]
    for vid in ("V1", "V2"):
        d = case.valves[vid][1]
        exact = dl.fluids_k("Cv", 600.0, d)
        assert abs(state["valveResults"][vid]["kOpen"] - exact) <= CONVERSION * exact, vid
    first = state["linkResults"]["L2"]["fittings"][0]
    exact = dl.fluids_k("Cv", 600.0, first["referenceDiameter"])
    assert abs(first["k"] - exact) <= CONVERSION * exact


def test_a_spec_edit_reaches_every_pipe(api: Api) -> None:
    """Q1 (references), for a pipe spec: PSB's bore edited from 0.1282 m to 0.13 m changes every
    segment on it (L2's second pipe, L3, L4) and every entry used on them (CV1's Kv, V2's Cv,
    PRV1's K and L2's last two fittings move to the new bore), as the project with those pipes
    typed in as custom pipes of the new bore, bit for bit."""
    case = dl.coefficient_entries()
    edited = copy.deepcopy(case.project)
    spec = next(s for s in edited["pipeLibrary"] if s["id"] == "PSB")
    spec["innerDiameter"] = 0.13
    state = api.solved(edited)
    assert state["converged"], state["convergence"]
    inline = copy.deepcopy(edited)
    users = 0
    for c in inline["connections"]:
        for i, pipe in enumerate(c["piping"]["pipes"]):
            if pipe.get("specId") == "PSB":
                c["piping"]["pipes"][i] = {
                    "materialId": "custom",
                    "innerDiameter": 0.13,
                    "roughness": spec["roughness"],
                    "length": pipe["length"],
                }
                users += 1
    assert users == 3
    labelled = {("L2", j) for j in FITTING_ENTRY}
    want = values(api.solved(inline), labelled)
    assert not differences(values(state, labelled), want), differences(
        values(state, labelled), want
    )
    for cid, index in (("L2", 1), ("L3", 0), ("L4", 0), ("L5", 0)):
        segment = state["linkResults"][cid]["segments"][index]
        assert segment["innerDiameter"] == (0.13 if cid != "L5" else dl.SPEC_A.inner_diameter)
    kv = dl.fluids_k("Kv", dl.KV700.value, 0.13)
    assert abs(state["valveResults"]["CV1"]["kOpen"] - kv) <= CONVERSION * kv
    k = dl.k_at_bore(dl.K08.value, 0.1023, 0.13)
    assert abs(state["valveResults"]["PRV1"]["kOpen"] - k) <= ROUND_OFF * k
    flow = state["linkResults"]["L1"]["flow"]
    assert abs(flow / case.flows["L1"] - 1.0) > 1.0e3 * TIGHT, "the edit changed nothing"


def test_entries_on_reducers_and_in_reverse_flow(api: Api) -> None:
    """§3.1, §3.3 (``derivations_project_library.reverse_reducer_line``): K, Cv and Kv entries on
    two reducers and a custom fitting, and a K entry on a valve whose inlet and outlet pipes
    have different bores, with the flow running against every element's direction. Each
    entry's loss at a flow does not depend on the bore it is used on, so the flow (within D6 and
    10⁻⁶), the valve's EGL drop (to the energy stop tolerance) and each fitting's head loss (to
    the conversion's agreement) are checked against the bore-free closed form; the K is moved to
    the reported bore, the valve's inlet pipe (D9) and the fitting's pipe pipeIndex (the model);
    and the elements with the reported K typed inline give the same state, bit for bit."""
    case = dl.reverse_reducer_line()
    state = api.solved(case.project)
    assert state["converged"], state["convergence"]
    for cid, want in case.flows.items():
        got = state["linkResults"][cid]["flow"]
        assert got < 0.0, (cid, got)
        assert within_d6(got, want, FLOW_FLOOR), (cid, got, want)
        assert abs(got - want) <= TIGHT * abs(want), (cid, got, want, got / want - 1)
    q = state["linkResults"]["L1"]["flow"]
    valve = state["valveResults"]["V1"]
    k, d = case.valves["V1"]
    assert valve["referenceDiameter"] == d
    assert abs(valve["kOpen"] - k) <= ROUND_OFF * k, (valve["kOpen"], k)
    h_in, h_out = (state["nodeResults"][f"V1:{p}"]["egl"] for p in ("inlet", "outlet"))
    stop = ENERGY_STOP_ABSOLUTE + ENERGY_STOP_ROUND_OFF * max(abs(h_in), abs(h_out))
    loss = dl.RSV.head_loss(q)
    assert loss < 0.0
    assert abs(h_in - h_out - loss) <= stop, (h_in - h_out, loss)
    assert within_d6(h_in - h_out, case.valve_head_loss["V1"], HEAD_FLOOR)
    fittings = state["linkResults"]["L1"]["fittings"]
    entries = case.data["entries"]
    for (cid, j), (k, d) in case.fittings.items():
        fitting = fittings[j]
        entry = entries[f"{cid}/{j}"]
        assert fitting["referenceDiameter"] == d, (j, fitting)
        exact = dl.fluids_k(entry.kind, entry.value, d) if entry.kind != "K" else k
        assert abs(fitting["k"] - exact) <= CONVERSION * exact, (j, fitting["k"], exact)
        n = case.data["quantities"][(cid, j)]
        bore_free = n * entry.head_loss(q)
        assert bore_free < 0.0
        assert abs(fitting["headLoss"] - bore_free) <= dl.CONVERSION_AGREEMENT * abs(bore_free), (
            j,
            fitting["headLoss"],
            bore_free,
        )
        want = case.data["fitting_head_loss"][(cid, j)]
        assert within_d6(fitting["headLoss"], want, HEAD_FLOOR), (j, fitting["headLoss"], want)
    labelled = {("L1", j) for j in range(len(fittings))}
    twin = _inline(case.project, {"V1": {"kind": "K", "value": valve["kOpen"]}})
    l1 = next(c for c in twin["connections"] if c["id"] == "L1")
    for j, fitting in enumerate(l1["piping"]["fittings"]):
        del fitting["resistanceId"]
        fitting["kOverride"] = fittings[j]["k"]
    got = values(api.solved(twin), labelled)
    assert not differences(got, values(state, labelled)), differences(got, values(state, labelled))
    users = {"V1": ["RSV"], "L1": ["RSR", "RSRC", "RSRK", "PSA", "PSB"], "L2": ["PSB"]}
    problems = library_problems(state, case.project, users)
    assert not problems, problems


def test_a_fitting_entry_above_the_k_override_bound(api: Api) -> None:
    """``derivations_project_library.high_k_fitting``: a K entry is bounded as a FlowCoefficient,
    (0, 10⁷] (proposal §2.2), so a fitting may take a K above kOverride's 10⁴ from it; the moved K
    (≈ 5.3×10⁴) is used as it is, never cut to 10⁴: the fitting's K, its head loss K₀ (Q/A₀)²/2g
    and the flow are the closed form's."""
    case = dl.high_k_fitting()
    state = api.solved(case.project)
    assert state["converged"], state["convergence"]
    q, want = state["linkResults"]["L1"]["flow"], case.flows["L1"]
    assert within_d6(q, want, FLOW_FLOOR), (q, want)
    assert abs(q - want) <= TIGHT * want, (q, want, q / want - 1)
    [fitting] = state["linkResults"]["L1"]["fittings"]
    k, d = case.fittings[("L1", 0)]
    assert fitting["referenceDiameter"] == d
    assert abs(fitting["k"] - k) <= ROUND_OFF * k, (fitting["k"], k)
    assert fitting["k"] > 1.0e4
    loss = dl.RSBIG.head_loss(q)
    assert abs(fitting["headLoss"] - loss) <= 1.0e-12 * loss, (fitting["headLoss"], loss)


# --------------------------------------------------------------------------- errors (item 5)


def _no_echo(response: httpx.Response) -> list[str]:
    return [
        f"the response echoes {t!r}: {response.text[:400]}"
        for t in (SENTINEL, SENTINEL_DIGITS)
        if t in response.text
    ]


def _sentinel_entry(entry_id: str, **values: Any) -> dict[str, Any]:
    return {
        "id": entry_id,
        "name": f"Entry {SENTINEL}",
        "source": f"Datasheet {SENTINEL} rev {SENTINEL_DIGITS}",
        **values,
    }


def test_dangling_references_are_topology_issues(api: Api) -> None:
    """§2.3: a specId, a valve's library id and a fitting's resistanceId that name no entry are
    422 TOPOLOGY_ERROR, each an issue naming its element and the id (UNKNOWN_PIPE_SPEC,
    UNKNOWN_RESISTANCE), listed with the project's other topology issues (an unknown pipe
    material, here also on a spec); no entry's name or source comes back (D10)."""
    case = dl.coefficient_entries()
    project = copy.deepcopy(case.project)
    by_id = {c["id"]: c for c in project["connections"]}
    by_id["L1"]["piping"]["pipes"][0] = {"specId": "PSMISSING", "length": 20.0}
    next(c for c in project["components"] if c["id"] == "V1")["resistance"] = {
        "kind": "library",
        "id": "RSMISSING",
    }
    by_id["L2"]["piping"]["fittings"][1]["resistanceId"] = "RSGHOST"
    by_id["L3"]["piping"]["pipes"][0] = {
        "materialId": "copper",
        "schedule": "40",
        "nominalSize": 0.1016,
        "length": 15.0,
    }
    project["pipeLibrary"].append(
        _sentinel_entry("PSBAD", materialId="copper", innerDiameter=0.1, roughness=1.0e-5)
    )
    by_id["L4"]["piping"]["pipes"][0] = {"specId": "PSBAD", "length": 10.0}
    for entry in project["resistanceLibrary"]:
        entry["name"], entry["source"] = f"Entry {SENTINEL}", f"Datasheet {SENTINEL}"
    response = api.solve(project)
    assert response.status_code == 422, response.text[:2000]
    body = response.json()
    assert body["error"] == "TOPOLOGY_ERROR"
    assert not _no_echo(response), _no_echo(response)
    issues = body["issues"]

    def find(code: str, ref: str) -> list[dict[str, Any]]:
        return [i for i in issues if i["code"] == code and ref in i["message"]]

    [spec] = find("UNKNOWN_PIPE_SPEC", "PSMISSING")
    assert spec["connectionIds"] == ["L1"], spec
    [valve] = find("UNKNOWN_RESISTANCE", "RSMISSING")
    assert "V1" in valve["componentIds"], valve
    [fitting] = find("UNKNOWN_RESISTANCE", "RSGHOST")
    assert "L2" in fitting["connectionIds"], fitting
    materials = [i for i in issues if i["code"] == "UNKNOWN_PIPE_MATERIAL"]
    assert {c for i in materials for c in i["connectionIds"]} == {"L3", "L4"}, materials
    assert len(issues) == 5, [i["code"] for i in issues]


INVALID_ENTRIES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "K without its bore",
        "resistanceLibrary",
        _sentinel_entry("RS1", kind="K", value=0.001234567),
    ),
    (
        "Cv with a bore",
        "resistanceLibrary",
        _sentinel_entry("RS1", kind="Cv", value=0.001234567, referenceDiameter=0.01234567),
    ),
    (
        "Kv with a bore",
        "resistanceLibrary",
        _sentinel_entry("RS1", kind="Kv", value=0.001234567, referenceDiameter=0.01234567),
    ),
    (
        "K bore out of bounds",
        "resistanceLibrary",
        _sentinel_entry("RS1", kind="K", value=0.5, referenceDiameter=10.1234567),
    ),
    (
        "unknown kind",
        "resistanceLibrary",
        _sentinel_entry("RS1", kind=f"Cv{SENTINEL}", value=0.001234567),
    ),
    (
        "custom spec without roughness",
        "pipeLibrary",
        _sentinel_entry("PS1", materialId="custom", innerDiameter=0.01234567),
    ),
    (
        "blank source",
        "pipeLibrary",
        {
            **_sentinel_entry("PS1", materialId="custom", innerDiameter=0.1, roughness=1.0e-5),
            "source": "   ",
        },
    ),
    (
        "outer diameter below the bore",
        "pipeLibrary",
        _sentinel_entry(
            "PS1", materialId="carbon_steel", innerDiameter=0.1, outerDiameter=0.01234567
        ),
    ),
]
"""Entries that break their own rules (§2.1-§2.2 and the contract): 400 at the entry."""


@pytest.mark.parametrize(
    ("list_name", "entry"), [x[1:] for x in INVALID_ENTRIES], ids=[x[0] for x in INVALID_ENTRIES]
)
def test_invalid_entries_are_400_and_never_echoed(
    api: Api, list_name: str, entry: dict[str, Any]
) -> None:
    """§2.3: an entry that breaks its rules is 400 VALIDATION_ERROR located at the entry, and the
    response gives none of its name, source or values (D10)."""
    project = copy.deepcopy(dl.k_entry_valve().project)
    project[list_name] = [entry]
    if list_name == "pipeLibrary":
        for c in project["connections"]:
            c["piping"]["pipes"] = [{"specId": "PS1", "length": 15.0}]
    else:
        valve = next(c for c in project["components"] if c["id"] == "V1")
        valve["resistance"] = {"kind": "library", "id": "RS1"}
    response = api.solve(project)
    assert response.status_code == 400, response.text[:2000]
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert not _no_echo(response), _no_echo(response)
    assert body["issues"]
    assert all(i["message"].startswith(f"body.project.{list_name}.0") for i in body["issues"]), (
        body["issues"]
    )


INVALID_REFERENCES: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
    (
        "materialId beside specId",
        lambda p: p["connections"][0]["piping"]["pipes"][0].update(materialId="carbon_steel"),
    ),
    (
        "innerDiameter beside specId",
        lambda p: p["connections"][0]["piping"]["pipes"][0].update(innerDiameter=0.01234567),
    ),
    (
        "kOverride beside resistanceId",
        lambda p: p["connections"][0]["piping"]["fittings"].append(
            {"type": "custom", "resistanceId": "RS30", "kOverride": 0.001234567}
        ),
    ),
    (
        "duplicate entry ids",
        lambda p: p["resistanceLibrary"].append({**p["resistanceLibrary"][0], "name": SENTINEL}),
    ),
]


@pytest.mark.parametrize(
    "edit", [x[1] for x in INVALID_REFERENCES], ids=[x[0] for x in INVALID_REFERENCES]
)
def test_invalid_references_are_400(api: Api, edit: Callable[[dict[str, Any]], None]) -> None:
    """The contract's reference rules (x-reference-fields; ids unique within each list): a
    pipe on a spec takes nothing but its length, a fitting takes a resistanceId or a kOverride,
    never both; each is 400 VALIDATION_ERROR, never echoed."""
    project = copy.deepcopy(dl.k_entry_valve().project)
    edit(project)
    response = api.solve(project)
    assert response.status_code == 400, response.text[:2000]
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert not _no_echo(response), _no_echo(response)


def _out_of_slice_scenario(p: dict[str, Any]) -> None:
    p["scenarios"] = [
        {
            "id": "S1",
            "name": "An entry as a target",
            "overrides": [
                {"kind": "library", "entryId": "RS30", "field": "value", "value": 0.4},
            ],
        }
    ]


def _equipment_on_an_entry(p: dict[str, Any]) -> None:
    item = dl.component_json(equipment("E1", 0.0, rated_coefficient("Cv", 100.0)))
    item["rating"] = {"kind": "library", "id": "RS30"}
    p["components"].append(item)


def _too_many_specs(p: dict[str, Any]) -> None:
    p["pipeLibrary"] = [{**p["pipeLibrary"][0], "id": f"PS{i}"} for i in range(1, MAX_ENTRIES + 2)]
    for c in p["connections"]:
        c["piping"]["pipes"] = [{"specId": "PS1", "length": 15.0}]


OUT_OF_SLICE: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
    (
        "an entry as a scenario target",
        _out_of_slice_scenario,
        "body.project.scenarios.0.overrides.0",
    ),
    ("an equipment rating from the library", _equipment_on_an_entry, "body.project.components.3"),
    ("101 pipe specs", _too_many_specs, "body.project.pipeLibrary"),
]
"""What this slice does not take (§2.1-§2.2, §5.1, Q4; D18: a rating is the element's own):
an override that targets an entry, an equipment rating that refers to one, more than 100
entries in a list. Each is 400 VALIDATION_ERROR at that value, never accepted and ignored."""


@pytest.mark.parametrize(
    ("edit", "location"), [x[1:] for x in OUT_OF_SLICE], ids=[x[0] for x in OUT_OF_SLICE]
)
def test_what_the_slice_does_not_take_is_400(
    api: Api, edit: Callable[[dict[str, Any]], None], location: str
) -> None:
    project = copy.deepcopy(dl.k_entry_valve().project)
    edit(project)
    response = api.solve(project)
    assert response.status_code == 400, response.text[:2000]
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert [i["message"].startswith(location) for i in body["issues"]] == [True], body["issues"]


def test_an_entry_is_not_a_goal_seek_variable(api: Api) -> None:
    """§5.2, §9.4: entries are not goal-seek variables in this slice: a variable that names one
    is 400, never searched."""
    setup = dl.goal_seek_cv_on_cv_entry()
    request = setup.request()
    request["variables"] = [
        {"kind": "library", "entryId": "RSG", "field": "value", "lower": 10.0, "upper": 500.0}
    ]
    response = api.post(GOAL_SEEK, request)
    assert response.status_code == 400, response.text[:2000]
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert [i["message"].startswith("body.variables.0") for i in body["issues"]] == [True], body


def test_an_id_in_both_lists_resolves_in_its_own(api: Api) -> None:
    """A pipe spec and a resistance entry with the same id: the proposal (§2.1) asks for ids
    unique across the project, the contract checks each list on its own (every reference names
    its list). Either the project is refused (400), or each reference resolves in its own list:
    the pipes take the spec, the valve the entry, bit for bit as typed inline."""
    case = dl.k_entry_valve()
    project = copy.deepcopy(case.project)
    project["pipeLibrary"][0]["id"] = "X1"
    project["resistanceLibrary"][0]["id"] = "X1"
    for c in project["connections"]:
        for pipe in c["piping"]["pipes"]:
            pipe["specId"] = "X1"
    next(c for c in project["components"] if c["id"] == "V1")["resistance"]["id"] = "X1"
    response = api.solve(project)
    if response.status_code == 400:
        assert response.json()["error"] == "VALIDATION_ERROR"
        return
    assert response.status_code == 200, response.text[:2000]
    state = response.json()["solvedState"]
    assert not differences(values(state), values(api.solved(case.project)))


# --------------------------------------------------------------------------- scenarios (item 6)


def scenario_base() -> dict[str, Any]:
    """R1 (H 12) → L1 [carbon steel 40, NPS 4, 30 m] → V1 gate (Crane default) → L2 [PSS2, 40 m]
    → R2 (H 2), liquid A; specs PSS1 (custom 0.1 m) and PSS2 (custom 0.0779 m), entry RSS1
    (Cv 150), and the scenarios of ``test_a_scenario_switches_to_and_from_the_library``."""
    fluid, _, _ = dl.liquid_a()
    pss1 = dl.Spec("PSS1", 0.1, roughness=3.0e-5, name="Scenario spec 1")
    pss2 = dl.Spec("PSS2", 0.0779, name="Scenario spec 2")
    rss1 = dl.Entry("RSS1", "Cv", 150.0, name="Scenario valve Cv 150")
    components = [
        reservoir("R1", 0.0, 12.0).model_dump(mode="json", exclude_none=True),
        dl.component_json(isolation_valve("V1", 0.0, "gate")),
        reservoir("R2", 0.0, 2.0).model_dump(mode="json", exclude_none=True),
    ]
    cited = {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.1016}
    connections = [
        dl.connection("L1", "R1:port_1", "V1:inlet", [{**cited, "length": 30.0}]),
        dl.connection("L2", "V1:outlet", "R2:port_1", [dl.spec_pipe(pss2, 40.0)]),
    ]
    project = dl.project_json(
        "ref-library-scenarios",
        "Scenarios with the project library",
        fluid,
        components,
        connections,
        specs=[pss1, pss2],
        entries=[rss1],
    )
    pipe = {"kind": "pipe", "pipeIndex": 0, "field": "spec"}
    project["scenarios"] = [
        {
            "id": "S1",
            "name": "To the library",
            "overrides": [
                {**pipe, "connectionId": "L1", "value": {"specId": "PSS1"}},
                {
                    "kind": "component",
                    "componentId": "V1",
                    "field": "resistance",
                    "value": {"kind": "library", "id": "RSS1"},
                },
            ],
        },
        {
            "id": "S2",
            "name": "Back to the cited library",
            "overrides": [
                {
                    **pipe,
                    "connectionId": "L2",
                    "value": {
                        "materialId": "carbon_steel",
                        "schedule": "40",
                        "nominalSize": 0.0762,
                    },
                }
            ],
        },
        {
            "id": "S5",
            "name": "From one spec to another",
            "overrides": [{**pipe, "connectionId": "L2", "value": {"specId": "PSS1"}}],
        },
        {
            "id": "S3",
            "name": "A spec that is not there",
            "overrides": [{**pipe, "connectionId": "L1", "value": {"specId": "PSGONE"}}],
        },
        {
            "id": "S4",
            "name": "An entry that is not there",
            "overrides": [
                {
                    "kind": "component",
                    "componentId": "V1",
                    "field": "resistance",
                    "value": {"kind": "library", "id": "RSGONE"},
                }
            ],
        },
    ]
    return project


def by_hand(project: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    """The project edited by hand as the scenario says (§5.1: a pipe's spec replaces its spec
    keys, specId among them; a resistance replaces the valve's), without scenarios."""
    out = copy.deepcopy({k: v for k, v in project.items() if k != "scenarios"})
    scenario = next(s for s in project["scenarios"] if s["id"] == scenario_id)
    for o in scenario["overrides"]:
        if o["kind"] == "pipe":
            c = next(c for c in out["connections"] if c["id"] == o["connectionId"])
            old = c["piping"]["pipes"][o["pipeIndex"]]
            c["piping"]["pipes"][o["pipeIndex"]] = {**o["value"], "length": old["length"]}
        else:
            component = next(c for c in out["components"] if c["id"] == o["componentId"])
            component[o["field"]] = o["value"]
    return out


@pytest.mark.parametrize("scenario_id", ["S1", "S2", "S5"])
def test_a_scenario_switches_to_and_from_the_library(api: Api, scenario_id: str) -> None:
    """§5.1: a pipe's spec switched to a library spec ({specId}) and a valve to an entry (S1), a
    spec pipe switched back to a cited pipe (S2) and a spec pipe switched to another spec (S5)
    solve as the hand-edited project, bit for bit, each override applied."""
    project = scenario_base()
    response = api.solve(project, scenario_id)
    assert response.status_code == 200, response.text[:2000]
    body = response.json()
    states = [o["state"] for o in body["scenario"]["overrides"]]
    assert states == ["applied"] * len(states), body["scenario"]
    want = api.solved(by_hand(project, scenario_id))
    got = body["solvedState"]
    assert not differences(values(got), values(want)), differences(values(got), values(want))
    base = api.solved({k: v for k, v in project.items() if k != "scenarios"})
    assert differences(values(got), values(base)), "the scenario changed nothing"


@pytest.mark.parametrize("scenario_id", ["S3", "S4"])
def test_a_scenario_naming_a_missing_entry_fails_as_by_hand(api: Api, scenario_id: str) -> None:
    """§5.1: a scenario reference to an entry the base does not have is the topology issue of
    §2.3, as for the hand-edited project: 422 with the same issues, the message naming the
    scenario."""
    project = scenario_base()
    got = api.solve(project, scenario_id)
    want = api.solve(by_hand(project, scenario_id))
    assert want.status_code == 422, want.text[:2000]
    assert got.status_code == 422, got.text[:2000]
    g, w = got.json(), want.json()
    assert g["error"] == w["error"] == "TOPOLOGY_ERROR"
    assert scenario_id in g["message"], g["message"]
    assert not differences(g["issues"], w["issues"]), differences(g["issues"], w["issues"])
    code = "UNKNOWN_PIPE_SPEC" if scenario_id == "S3" else "UNKNOWN_RESISTANCE"
    assert [i["code"] for i in w["issues"]] == [code], w["issues"]


# --------------------------------------------------------------------------- goal seek (item 6)


def without_annotation(state: dict[str, Any]) -> dict[str, Any]:
    """A solved state without what may differ between a goal seek's state and the solve of its
    applied values (D16): the timestamp, the "Goal seek" and "Scenario" methods sections and
    the element notes they add."""
    out = copy.deepcopy(state)
    out.pop("timestamp", None)
    methods = out["trace"]["methods"]
    methods["sections"] = [
        s for s in methods["sections"] if s["title"] not in (GOAL_SEEK_SECTION, SCENARIO_SECTION)
    ]
    for trace in out["trace"]["elements"].values():
        trace["notes"] = [n for n in trace["notes"] if not n.startswith(("Goal seek", "Scenario "))]
    return out


def apply_override(project: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """The override written into the project by hand: a valve's resistance, or a pipe's
    length (the rest of a spec pipe stays its specId)."""
    out = copy.deepcopy(project)
    if override["kind"] == "component":
        component = next(c for c in out["components"] if c["id"] == override["componentId"])
        component[override["field"]] = override["value"]
    else:
        c = next(c for c in out["connections"] if c["id"] == override["connectionId"])
        c["piping"]["pipes"][override["pipeIndex"]][override["field"]] = override["value"]
    return out


GOAL_SEEKS = {
    "cv_on_cv_entry": dl.goal_seek_cv_on_cv_entry,
    "cv_on_k_entry": dl.goal_seek_cv_on_k_entry,
    "length_of_spec_pipe": dl.goal_seek_length_of_spec_pipe,
    "k_on_k_entry_met_at_start": dl.goal_seek_k_on_k_entry_met_at_start,
    "cv_entry_clipped": dl.goal_seek_cv_entry_clipped,
    "in_a_scenario": dl.goal_seek_in_a_scenario,
}


def case_resistance(setup: dl.GoalSeekSetup) -> Any:
    """V1's resistance in the case the goal seek runs on: the scenario's override, if any, else
    the base's."""
    base = next(c for c in setup.project["components"] if c["id"] == "V1")["resistance"]
    if setup.scenario_id is None:
        return base
    scenario = next(s for s in setup.project["scenarios"] if s["id"] == setup.scenario_id)
    for o in scenario["overrides"]:
        if o.get("componentId") == "V1" and o["field"] == "resistance":
            return o["value"]
    return base


def with_override(setup: dl.GoalSeekSetup, override: dict[str, Any]) -> dict[str, Any]:
    """The scenario of a scenario run with its replaced override changed to ``override``
    (D16: upserted by target and field)."""
    project = copy.deepcopy(setup.project)
    scenario = next(s for s in project["scenarios"] if s["id"] == setup.scenario_id)
    assert setup.replaced_override is not None
    scenario["overrides"][setup.replaced_override] = override
    return project


@pytest.mark.parametrize("name", list(GOAL_SEEKS))
def test_goal_seek_on_library_values(api: Api, name: str) -> None:
    """§5.2 and D16: a goal seek on a valve that refers to an entry starts at the case's value
    when the entry is of the variable's kind (a K entry: its K on the valve's bore, K₀ (D/d₀)⁴,
    which is the case's K), clipped into the bounds, else in the middle of the bounds on the log
    scale; a case that already meets the goal stops at its start with the case's own state; it
    meets the target, the closed-form flow at the value found is within the tolerance plus D6 of
    it; its override is an inline coefficient of the variable's kind (or the spec pipe's length),
    and the result names the entry it replaces; written by hand into the project or put in a new
    scenario (in a scenario run: in place of the scenario's override it replaced) and solved, it
    gives the reported state bit for bit (apart from the goal seek's annotation)."""
    setup = GOAL_SEEKS[name]()
    response = api.post(GOAL_SEEK, setup.request())
    assert response.status_code == 200, response.text[:2000]
    body = response.json()
    result = body["result"]
    assert result["met"], result["message"]
    [variable] = result["variables"]
    assert variable["startSource"] == setup.start_source, variable
    assert variable["start"] == pytest.approx(setup.start, rel=1.0e-12), variable
    assert variable["replacedOverride"] == setup.replaced_override, variable
    value = variable["value"]
    [goal] = result["goals"]
    target = setup.goal["target"]
    assert abs(setup.forward(value) - target) <= goal["tolerance"] + max(
        RELATIVE * target, FLOW_FLOOR
    ), (value, setup.inverse)
    want = without_annotation(body["solvedState"])
    if setup.met_at_start:
        assert result["stopReason"] == "met_at_start", result["message"]
        assert result["reportedEvaluation"] == 0
        assert len(result["evaluations"]) == 1, len(result["evaluations"])
        assert value == variable["start"]
        # The case's own state, but for the trace: the valve's names its entry (§4.1), the
        # goal seek's an inline K.
        case = values(api.solved(setup.project, setup.scenario_id))
        assert not differences(case, values(want)), differences(case, values(want))
    override = variable["override"]
    if setup.variable["field"] == "resistance":
        assert override == {
            "kind": "component",
            "componentId": "V1",
            "field": "resistance",
            "value": {"kind": setup.variable["coefficient"], "value": value},
        }, override
        reference = case_resistance(setup)
        assert variable["caseValue"] == reference, variable
        base = next(c for c in setup.project["components"] if c["id"] == "V1")["resistance"]
        assert variable["baseValue"] == base, variable
        assert reference["id"] in text(result), "the result does not name the entry replaced"
    else:
        assert override == {
            "kind": "pipe",
            "connectionId": "L2",
            "pipeIndex": 0,
            "field": "length",
            "value": value,
        }, override
    if setup.scenario_id is not None:
        applied = api.solved(with_override(setup, override), setup.scenario_id)
        assert not differences(without_annotation(applied), want), differences(
            without_annotation(applied), want
        )
        return
    applied = api.solved(apply_override(setup.project, override))
    assert not differences(without_annotation(applied), want), differences(
        without_annotation(applied), want
    )
    scenario = {"id": "GS1", "name": "Goal seek 1", "overrides": [override]}
    as_scenario = api.solved({**setup.project, "scenarios": [scenario]}, "GS1")
    assert not differences(without_annotation(as_scenario), want), differences(
        without_annotation(as_scenario), want
    )


# --------------------------------------------------------------------------- no library (item 7)


def library_keys(data: Any) -> list[str]:
    """Paths of every library key in a project's JSON."""
    found: list[str] = []

    def walk(value: Any, at: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("pipeLibrary", "resistanceLibrary", "specId", "resistanceId"):
                    found.append(f"{at}.{key}")
                walk(item, f"{at}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{at}[{i}]")

    walk(data, "project")
    return found


@pytest.mark.parametrize(
    "case", ["library_pipe_builtin_water", "isolation_valves_kv_and_k", "isolation_valve_cv"]
)
def test_a_project_without_a_library_round_trips_without_it(api: Api, case: str) -> None:
    """§1.3 decision 5: a project without library fields dumps without them (every dump mode),
    explicit empty lists are dropped and serialize exactly as the project without them, and both
    solve bit for bit alike (trace included) with no "Project library" methods section."""
    path = next(p for p in case_files() if p.stem == case)
    data = _file_json(path)
    assert not library_keys(data)
    model = Project.model_validate(data)
    dumps = [
        model.model_dump(mode="json"),
        model.model_dump(mode="json", exclude_unset=True),
        json.loads(model.model_dump_json()),
    ]
    for dumped in dumps:
        assert not library_keys(dumped), library_keys(dumped)
    empty = Project.model_validate({**data, "pipeLibrary": [], "resistanceLibrary": []})
    assert empty.model_dump_json() == model.model_dump_json()
    assert not library_keys(empty.model_dump(mode="json"))
    plain = api.solved(data)
    with_empty = api.solved({**data, "pipeLibrary": [], "resistanceLibrary": []})
    for state in (plain, with_empty):
        state.pop("timestamp")
    assert not differences(with_empty, plain), differences(with_empty, plain)
    assert library_section(plain) is None
