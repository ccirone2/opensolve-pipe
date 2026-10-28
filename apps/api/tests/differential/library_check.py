"""Check the project library against the values it stands for, over the corpus (CLAUDE.md D21,
proposal project-library.md §7.2), in two modes with an expected answer each.

    uv run python -m tests.differential.library_check [--mode exact|rebased] [--workers N]
                                                       [--only PREFIX] [--out FILE]

An element that refers to a project library entry is solved with exactly the values it would
have with them entered on it (proposal §1.3 decision 4): a pipe spec's material, inner diameter
and roughness, a Cv or Kv converted as one entered on the element, and a K stated at a bore d₀
moved to the element's bore D by K = K₀ (D/d₀)⁴ (§3.3). So for every corpus project
(``corpus.items()``), the project (API JSON, without scenarios: the base is solved) is solved
(A), then, in each mode, its values are lifted into the library and it is solved again (B):

- every distinct pipe definition (its fields but the length, as dumped) that resolves becomes a
  pipe spec (``pipeLibrary``) holding the bore and roughness the solver resolves it to
  (``library.resolve_pipe``), and every segment with that definition refers to it by ``specId``
  with only its own length. The spec keeps the pipe's own material: a custom pipe gives a
  custom spec with its roughness ('custom'); a library material gives a spec on that material
  with the resolved roughness stated ('explicit': the tabulated value, or the user's), except
  where the solver itself evaluated Farshad's roughness at a user bore (a library pipe with an
  inner diameter and no roughness), which gives a spec with no roughness, so that the solver
  evaluates the same function on the same bore again ('farshad', proposal §1.2 P2). Either way
  the numbers are bit-exact by construction: ``resolve_pipe`` takes a user inner diameter and
  roughness as given, with no arithmetic, and the Farshad call has the same two arguments. A
  custom spec would hold the same two numbers, but it would drop the material, so a spec on a
  library material and its blank-roughness branch would never be solved; keeping the material
  is also what a user would enter (proposal §2.1). (The corpus has no 'farshad' pipe: the smoke
  test makes some.) The definition's nominal size, when it has one, goes on the spec too
  (display only). A definition that does not resolve (an unknown material, schedule or size: a
  topology issue) is not lifted ('unresolved');
- every valve resistance becomes a resistance entry (``resistanceLibrary``) and the valve's
  ``resistance`` the reference ``{kind: 'library', id}``: a Cv or Kv as entered ('Cv', 'Kv'); a
  K, and the Crane default K of an isolation or check valve without one (A's ``kOpen``, so only
  where A has a result: 'crane', else 'no_result'), as a K entry stated at the valve's
  reference bore D, the inner diameter of its inlet pipe's end segment at its inlet port, as
  resolved (D9; checked against A's ``referenceDiameter`` where A has the valve, (x)). A
  control valve without a resistance is ideal, K = 0, which no entry can hold ('ideal');
- every fitting ``kOverride`` becomes a K entry stated at the bore of its pipe ``pipeIndex``,
  and the fitting refers to it by ``resistanceId`` ('fittings'; a kOverride of 0, which no entry
  can hold: 'zero_k').

Entries with the same kind, value and bore are one entry, so one entry may serve many elements
(valves and fittings alike). Ids are ``PS<n>`` and ``RS<n>``, skipping every id the project
already uses; names and sources are fixed test texts. A list holds at most
``MAX_LIBRARY_ENTRIES`` (100) entries: an element whose entry would be the 101st stays inline
('over_limit'). Elements that already refer to the library are left as they are ('already').

- mode ``exact``: every K entry is stated at the element's own bore, d₀ = D, so (D/d₀)⁴ = 1.0
  and the K the solver uses is the K entered, bit for bit. B must then equal A bit for bit:
  (b) the solved states' JSON texts are identical, with three paths left out, each by design:
  ``timestamp``; ``trace``, whose notes and data sources name the entries and their sources
  (proposal §4.1, §4.2); and the ``source`` of each lifted fitting's result, which names its
  entry instead of 'user'. The flags are compared too, with one expected change: a valve whose
  Crane default was lifted into a K entry no longer has the Crane flags
  (``CORRELATION_OUT_OF_RANGE`` on that valve: its size outside Crane's table, and laminar flow
  for a Crane K), since its K is now user data; A's flags without those must be B's, in order.
  This holds for every outcome: a solve that did not converge too;
- mode ``rebased``: every K entry is stated at d₀ = 1.1 D with K₀ = K (d₀/D)⁴ (``REBASE``), so
  that the K the solver moves back to D, K₀ (D/d₀)⁴, is K analytically and differs from it by
  round-off only (d₀ = D/1.1 where 1.1 D would pass the 10 m bound of a bore or K₀ the 10⁷ bound
  of a coefficient: 'down'). Cv and Kv entries and pipe specs are lifted as in mode exact. Then
  (b) every connection's flow, and every port's EGL and static pressure, within D6 of A's
  (``equipment_check.network_problems``: a value different only at zero flow is listed, not a
  difference, CLAUDE.md D13); (c) each lifted valve's flow and head loss within D6 of A's (one
  that has a result in only one solve, only at zero flow); (d) each lifted K, a valve's
  ``kOpen`` and a fitting's ``k``, within ``ROUND_OFF`` (relative) of A's; and (y) B equals its
  inline twin bit for bit, for every outcome (``inline_twin``: B's project with every reference
  typed on its element as a user would, a spec's values on each of its segments, a Cv or Kv as
  entered and a K entry as K₀ (D/d₀)⁴ computed here; mode exact's paths left out). So whatever
  differs between A and B in this mode is the round-off of the K moved between bores, not the
  library (proposal §1.3 decision 4, §7.1 case 3).

In both modes: (a) the same outcome: both solved and converged, both solved and not converged
(then, in mode rebased, nothing else is compared), both raised the same topology issues (codes
and the elements they name: a lifted pipe's message names its spec), or both raised the same
other error; (v) the lifted project validates; (x) the reference bore the check computed for a
valve is A's ``referenceDiameter``; (t) in a converged B, the trace of every element that refers
to an entry made here (a valve's; a connection's for its pipes and fittings) names each of
those entries by its id, with its source, and the methods summary names every entry made, with
its source (proposal §4.1, §4.2).

Solves run without system curves. The report counts, per mode and profile (the name's prefix:
ref, unit, ladder, wye, fuzz, fuzzfc, fuzzaf), the projects checked, the pipe specs made and
the segments that refer to them (by kind: custom, explicit, farshad), the resistance entries
made and the elements that refer to them (valves by kind: K, Cv, Kv, crane; fittings), the
entries that serve more than one element ('shared'), the Crane flags left out in mode exact
('crane_flags'), the elements left inline (unresolved, ideal, no_result, no_bore, zero_k,
over_limit, already), the K entries stated below the bore ('down'), the projects whose solves
did not converge or raised a topology issue or another error (alike in A and B), the values
different only at zero flow, the projects compared with their inline twin ('twin'), and the
projects with differences, each listed. In mode rebased it also records, with no threshold, the
largest differences over the projects (``largest_differences``): flows relative to the largest
flow, heads in m (pressures as heads) and K relative. Exit status 1 on any difference; ``--out``
writes every project's record as JSON. ``test_library_check_smoke.py`` runs the reference cases,
the unit-test data networks and a few seeds of each fuzz profile.
"""

import argparse
import copy
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from multiprocessing import Pool
from typing import Any

from pydantic import ValidationError

from opensolve_pipe.models.base import FLOW_COEFFICIENT_MAX
from opensolve_pipe.models.piping import CUSTOM_MATERIAL_ID
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.project_library import DIAMETER_MAX, MAX_LIBRARY_ENTRIES
from opensolve_pipe.services.solver import TopologyError, solve_project
from opensolve_pipe.services.solver.library import LibraryLookupError, ResolvedPipe, resolve_pipe
from tests.differential.corpus import Item, items, load
from tests.differential.equipment_check import (
    NO_CURVES,
    PROFILES,
    G,
    _dump,
    d6,
    network_problems,
    profile,
)

MODES = ("exact", "rebased")
"""Mode 1, every K at its element's own bore; mode 2, every K at 1.1 times it (docstring)."""
REBASE = 1.1
"""Mode rebased: d₀ = REBASE × D (D / REBASE where that would pass a bound)."""
ROUND_OFF = 1.0e-12
"""(d): a K moved from 1.1 D back to D, relative to A's K (about 4,500 ε; it takes a few)."""
SOURCE = (
    "tests/differential/library_check.py: the project's own value, lifted into the project "
    "library (a test input)"
)
"""Every lifted entry's source (required, 1-300 characters)."""
VALVE_TYPES = ("valve",)
"""The component type of isolation, check and control valves (``components.Component``)."""
CONTROL_VALVES = ("prv", "psv", "fcv")
"""A control valve's types: without a resistance it is ideal (K = 0)."""
CRANE_FLAG = "CORRELATION_OUT_OF_RANGE"
"""The code of the Crane default's flags (size and laminar flow), which a lifted K has not."""


# --------------------------------------------------------------------------- the lifting


@dataclass
class Lifted:
    """What one mode's lifting did to a project: B's API JSON and what the checks need."""

    data: dict[str, Any]
    counts: Counter[str] = field(default_factory=Counter)
    crane: set[str] = field(default_factory=set)
    """Valves whose Crane default became a K entry: their Crane flags go (mode exact)."""
    valves: dict[str, str] = field(default_factory=dict)
    """Each lifted valve's id -> how: 'K', 'Cv', 'Kv' or 'crane'."""
    fittings: dict[str, list[int]] = field(default_factory=dict)
    """Each connection's lifted fittings (indexes into its fittings), whose results' source
    names the entry."""
    bores: dict[str, float] = field(default_factory=dict)
    """Each valve's reference bore as computed here, m, for (x)."""
    uses: Counter[str] = field(default_factory=Counter)
    """How many elements refer to each resistance entry made."""


def _pipe_key(pipe: dict[str, Any]) -> str:
    """A pipe definition without its length, as text: equal definitions, one spec."""
    return json.dumps({k: v for k, v in pipe.items() if k != "length"}, sort_keys=True)


def _new_id(prefix: str, used: set[str]) -> str:
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    used.add(f"{prefix}{n}")
    return f"{prefix}{n}"


def _used_ids(data: dict[str, Any]) -> set[str]:
    used = {c["id"] for c in data["components"]} | {c["id"] for c in data["connections"]}
    used |= {c["id"] for c in data.get("pumpLibrary", [])}
    used |= {e["id"] for e in data.get("pipeLibrary", [])}
    used |= {e["id"] for e in data.get("resistanceLibrary", [])}
    return used


def resolved_pipes(project: Project) -> dict[str, list[ResolvedPipe | None]]:
    """Each connection's segments as the solver resolves them (None: one that does not)."""
    specs = {s.id: s for s in project.pipe_library}
    out: dict[str, list[ResolvedPipe | None]] = {}
    for conn in project.connections:
        segments: list[ResolvedPipe | None] = []
        for pipe in conn.piping.pipes:
            try:
                segments.append(resolve_pipe(pipe, specs))
            except LibraryLookupError:
                segments.append(None)
        out[conn.id] = segments
    return out


def inlet_bores(
    data: dict[str, Any], pipes: dict[str, list[ResolvedPipe | None]]
) -> dict[str, float]:
    """Each valve's reference bore D, m: the inner diameter of its inlet pipe's end segment at
    its inlet port (D9), where that segment resolves."""
    ends: dict[str, tuple[str, str]] = {}
    for conn in data["connections"]:
        ends[f"{conn['fromComponentId']}:{conn['fromPortId']}"] = (conn["id"], "from")
        ends[f"{conn['toComponentId']}:{conn['toPortId']}"] = (conn["id"], "to")
    bores: dict[str, float] = {}
    for comp in data["components"]:
        if comp["type"] not in VALVE_TYPES or f"{comp['id']}:inlet" not in ends:
            continue
        conn_id, end = ends[f"{comp['id']}:inlet"]
        segments = pipes.get(conn_id) or [None]
        segment = segments[0 if end == "from" else -1]
        if segment is not None:
            bores[comp["id"]] = segment.inner_diameter
    return bores


def stated_bore(k: float, bore: float, mode: str) -> tuple[float, float, bool]:
    """(K₀, d₀, stated below the bore) for a K on bore D in ``mode`` (module docstring)."""
    if mode == "exact":
        return k, bore, False
    d0 = REBASE * bore
    k0 = k * (d0 / bore) ** 4
    if d0 <= DIAMETER_MAX and k0 <= FLOW_COEFFICIENT_MAX:
        return k0, d0, False
    d0 = bore / REBASE
    return k * (d0 / bore) ** 4, d0, True


class _Entries:
    """The resistance entries made for one project: one per (kind, value, bore)."""

    def __init__(self, data: dict[str, Any], used: set[str], counts: Counter[str]) -> None:
        self.data, self.used, self.counts = data, used, counts
        self.ids: dict[tuple[str, float, float | None], str] = {}

    def id_for(self, kind: str, value: float, bore: float | None) -> str | None:
        key = (kind, value, bore)
        if key in self.ids:
            return self.ids[key]
        entries = self.data.setdefault("resistanceLibrary", [])
        if len(entries) >= MAX_LIBRARY_ENTRIES:
            return None
        eid = _new_id("RS", self.used)
        entry: dict[str, Any] = {
            "id": eid,
            "name": f"{kind} {value:.6g}" + (f" at {bore:.6g} m" if bore is not None else ""),
            "source": SOURCE,
            "kind": kind,
            "value": value,
        }
        if bore is not None:
            entry["referenceDiameter"] = bore
        entries.append(entry)
        self.ids[key] = eid
        self.counts["entries"] += 1
        return eid


def lifted(
    project: Project,
    state: dict[str, Any] | None,
    mode: str,
    k_scale: float = 1.0,
    bore_scale: float = 1.0,
) -> Lifted:
    """B's project in ``mode`` (module docstring). ``project`` is A's project (no scenarios),
    ``state`` A's solved state (API JSON; None: A did not solve). ``k_scale`` multiplies every
    lifted K (a Cv or Kv by 1/√k_scale, the same change of loss) and ``bore_scale`` every
    spec's inner diameter (1: the values themselves; a test of the check uses others)."""
    data = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    out = Lifted(data)
    counts = out.counts
    used = _used_ids(data)
    pipes = resolved_pipes(project)
    valve_results = (state or {}).get("valveResults", {})

    # pipe specs
    specs: dict[str, str] = {}
    library = data.setdefault("pipeLibrary", [])
    for conn, model in zip(data["connections"], project.connections, strict=True):
        for j, pipe in enumerate(conn["piping"]["pipes"]):
            defn = model.piping.pipes[j]
            resolved = pipes[conn["id"]][j]
            if defn.spec_id is not None:
                counts["already"] += 1
                continue
            if resolved is None:
                counts["unresolved"] += 1
                continue
            key = _pipe_key(pipe)
            if key not in specs:
                if len(library) >= MAX_LIBRARY_ENTRIES:
                    counts["over_limit"] += 1
                    continue
                assert defn.material_id is not None  # the model requires it without specId
                d = resolved.inner_diameter * bore_scale
                spec: dict[str, Any] = {
                    "id": _new_id("PS", used),
                    "name": f"{defn.material_id} {d:.6g} m",
                    "source": SOURCE,
                    "materialId": defn.material_id,
                    "innerDiameter": d,
                }
                if defn.material_id == CUSTOM_MATERIAL_ID:
                    kind = "custom"
                elif defn.roughness is None and defn.inner_diameter is not None:
                    kind = "farshad"  # Farshad at the user bore (resolve_pipe's last branch)
                else:
                    kind = "explicit"
                if kind != "farshad":
                    spec["roughness"] = resolved.roughness
                if defn.nominal_size is not None:
                    spec["nominalSize"] = defn.nominal_size
                library.append(spec)
                specs[key] = spec["id"]
                counts["specs"] += 1
                counts[kind] += 1
            conn["piping"]["pipes"][j] = {"specId": specs[key], "length": pipe["length"]}
            counts["segments"] += 1

    # valves
    entries = _Entries(data, used, counts)
    out.bores = inlet_bores(data, pipes)
    for comp in data["components"]:
        if comp["type"] not in VALVE_TYPES:
            continue
        vid = comp["id"]
        resistance = comp.get("resistance")
        bore = out.bores.get(vid)
        if resistance is None and comp["valveType"] in CONTROL_VALVES:
            counts["ideal"] += 1
            continue
        if resistance is not None and resistance["kind"] == "library":
            counts["already"] += 1
            continue
        if resistance is not None and resistance["kind"] in ("Cv", "Kv"):
            how = resistance["kind"]
            eid = entries.id_for(how, resistance["value"] / math.sqrt(k_scale), None)
        else:
            if resistance is not None:
                how, k = "K", float(resistance["value"])
            elif vid in valve_results:
                how, k = "crane", float(valve_results[vid]["kOpen"])
            else:
                counts["no_result"] += 1
                continue
            if bore is None:
                counts["no_bore"] += 1
                continue
            k0, d0, down = stated_bore(k * k_scale, bore, mode)
            if not 0.0 < k0 <= FLOW_COEFFICIENT_MAX:
                counts["over_limit"] += 1
                continue
            eid = entries.id_for("K", k0, d0)
            counts["down"] += int(down and eid is not None)
        if eid is None:
            counts["over_limit"] += 1
            continue
        comp["resistance"] = {"kind": "library", "id": eid}
        out.uses[eid] += 1
        out.valves[vid] = how
        counts[how] += 1
        if how == "crane":
            out.crane.add(vid)

    # fittings
    for conn in data["connections"]:
        for j, fitting in enumerate(conn["piping"].get("fittings", [])):
            k = fitting.get("kOverride")
            if fitting.get("resistanceId") is not None:
                counts["already"] += 1
                continue
            if k is None:
                continue
            if k == 0.0:
                counts["zero_k"] += 1
                continue
            index = fitting.get("pipeIndex", 0)
            segments = pipes[conn["id"]]
            segment = segments[index] if 0 <= index < len(segments) else None
            if segment is None:
                counts["no_bore"] += 1
                continue
            k0, d0, down = stated_bore(k * k_scale, segment.inner_diameter, mode)
            eid = entries.id_for("K", k0, d0) if 0.0 < k0 <= FLOW_COEFFICIENT_MAX else None
            if eid is None:
                counts["over_limit"] += 1
                continue
            del fitting["kOverride"]
            fitting["resistanceId"] = eid
            out.uses[eid] += 1
            out.fittings.setdefault(conn["id"], []).append(j)
            counts["fittings"] += 1
            counts["down"] += int(down)

    counts["shared"] = sum(n > 1 for n in out.uses.values())
    if not data["pipeLibrary"]:
        del data["pipeLibrary"]
    if not data.get("resistanceLibrary"):
        data.pop("resistanceLibrary", None)
    return out


def anything_lifted(lift: Lifted) -> bool:
    return bool(lift.counts["segments"] or lift.valves or lift.fittings)


def inline_twin(lift: Lifted) -> dict[str, Any] | None:
    """(y): B's project with every library reference replaced by what it stands for, typed on
    the element as a user would type it (proposal §1.3 decision 4, §7.1 case 3): a spec's
    material, inner diameter, roughness (where it states one) and nominal size on each segment
    that refers to it, with the segment's length; a Cv or Kv entry on a valve as entered; a K
    entry as the K it gives on the element's bore D, K₀ (D/d₀)⁴, computed here. D is the twin's
    own pipe as resolved: a valve's inlet end segment, a fitting's segment ``pipeIndex``. None
    where a reference has no inline form here (a missing entry or bore, which B reports as a
    topology issue, or a Cv or Kv on a fitting, which the lifting never makes)."""
    data = copy.deepcopy(lift.data)
    specs = {s["id"]: s for s in data.pop("pipeLibrary", [])}
    entries = {e["id"]: e for e in data.pop("resistanceLibrary", [])}
    keys = ("materialId", "innerDiameter", "roughness", "nominalSize")
    for conn in data["connections"]:
        pipes = conn["piping"]["pipes"]
        for j, pipe in enumerate(pipes):
            if "specId" in pipe:
                if pipe["specId"] not in specs:
                    return None
                spec = specs[pipe["specId"]]
                pipes[j] = {k: spec[k] for k in keys if k in spec} | {"length": pipe["length"]}
    pipes = resolved_pipes(Project.model_validate(data))
    bores = inlet_bores(data, pipes)

    def k_on(entry: dict[str, Any], bore: float | None) -> float | None:
        if bore is None:
            return None
        return float(entry["value"] * (bore / entry["referenceDiameter"]) ** 4)

    for comp in data["components"]:
        resistance = comp.get("resistance") or {}
        if resistance.get("kind") != "library":
            continue
        entry = entries.get(resistance["id"])
        if entry is None:
            return None
        if entry["kind"] != "K":
            comp["resistance"] = {"kind": entry["kind"], "value": entry["value"]}
            continue
        k = k_on(entry, bores.get(comp["id"]))
        if k is None:
            return None
        comp["resistance"] = {"kind": "K", "value": k}
    for conn in data["connections"]:
        segments = pipes[conn["id"]]
        for fitting in conn["piping"].get("fittings", []):
            if fitting.get("resistanceId") is None:
                continue
            entry = entries.get(fitting["resistanceId"])
            index = fitting.get("pipeIndex", 0)
            segment = segments[index] if 0 <= index < len(segments) else None
            if entry is None or entry["kind"] != "K" or segment is None:
                return None
            del fitting["resistanceId"]
            fitting["kOverride"] = k_on(entry, segment.inner_diameter)
    return data


# --------------------------------------------------------------------------- the solves


@dataclass(frozen=True)
class Outcome:
    """A solve's outcome: its state (API JSON), or the topology issues or error it raised."""

    state: dict[str, Any] | None = None
    issues: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] | None = None
    """Sorted (code, component ids, connection ids): a topology issue's message names a lifted
    pipe's spec, so only these are compared."""
    error: str | None = None

    @property
    def kind(self) -> str:
        if self.state is not None:
            return "converged" if self.state["converged"] else "not_converged"
        return "topology_error" if self.issues is not None else "error"


def solve(project: Project) -> Outcome:
    try:
        return Outcome(state=_dump(solve_project(project, NO_CURVES)))
    except TopologyError as exc:
        issues = sorted(
            (i.code, tuple(i.component_ids), tuple(i.connection_ids)) for i in exc.issues
        )
        return Outcome(issues=tuple(issues))
    except Exception as exc:  # a fluid out of range, ...: B must raise the same
        return Outcome(error=f"{type(exc).__name__}: {exc}")


def outcome_problems(a: Outcome, b: Outcome) -> list[str]:
    """(a): the same outcome (module docstring)."""
    if a.kind != b.kind:
        return [f"(a) {a.kind} in A, {b.kind} in B"]
    if a.issues != b.issues:
        return [f"(a) topology issues {a.issues} in A, {b.issues} in B"]
    if a.error != b.error:
        return [f"(a) {a.error} in A, {b.error} in B"]
    return []


def bore_problems(lift: Lifted, a: dict[str, Any]) -> list[str]:
    """(x): the reference bore computed here is the solver's, where A has the valve."""
    return [
        f"(x) {vid}: reference bore {lift.bores.get(vid)!r} here, {r['referenceDiameter']!r} in A"
        for vid, r in a["valveResults"].items()
        if vid in lift.valves and lift.bores.get(vid) != r["referenceDiameter"]
    ]


def references(lift: Lifted) -> dict[str, set[str]]:
    """Each element that refers to an entry made here -> those entries' ids: a valve's own, a
    connection's for its pipes and fittings."""
    made = {e["id"] for e in lift.data.get("pipeLibrary", []) if e["source"] == SOURCE}
    made |= {e["id"] for e in lift.data.get("resistanceLibrary", []) if e["source"] == SOURCE}
    out: dict[str, set[str]] = defaultdict(set)
    for comp in lift.data["components"]:
        resistance = comp.get("resistance") or {}
        if resistance.get("kind") == "library" and resistance["id"] in made:
            out[comp["id"]].add(resistance["id"])
    for conn in lift.data["connections"]:
        ids = {p.get("specId") for p in conn["piping"]["pipes"]}
        ids |= {f.get("resistanceId") for f in conn["piping"].get("fittings", [])}
        if ids & made:
            out[conn["id"]] |= ids & made
    return out


def trace_problems(b: dict[str, Any], lift: Lifted) -> list[str]:
    """(t): in a converged B, each element that refers to an entry made here names it in its
    trace, by id, with its source, and the methods summary names every entry made, with its
    source (proposal §4.1, §4.2)."""
    if not b["converged"]:
        return []
    out: list[str] = []
    elements = b["trace"]["elements"]
    for element, ids in references(lift).items():
        text = json.dumps(elements.get(element), ensure_ascii=False)
        missing = sorted(i for i in ids if f"({i})" not in text)
        if missing or SOURCE not in text:
            out.append(f"(t) the trace of {element} does not name {missing or 'its source'}")
    methods = json.dumps(b["trace"]["methods"], ensure_ascii=False)
    made = [e["id"] for e in lift.data.get("pipeLibrary", []) if e["source"] == SOURCE]
    made += [e["id"] for e in lift.data.get("resistanceLibrary", []) if e["source"] == SOURCE]
    missing = [i for i in made if f"({i})" not in methods]
    if missing or SOURCE not in methods:
        out.append(f"(t) the methods summary does not name {missing or 'the source'}")
    return out


# --------------------------------------------------------------------------- mode exact


def masked(state: dict[str, Any], lift: Lifted, side: str) -> dict[str, Any]:
    """A solved state without the paths mode exact leaves out (module docstring); on side A,
    without the Crane flags of the valves whose Crane default was lifted."""
    out = {k: v for k, v in state.items() if k not in ("timestamp", "trace")}
    out["linkResults"] = copy.deepcopy(state["linkResults"])
    for conn, indexes in lift.fittings.items():
        link = out["linkResults"].get(conn)
        if link is None:
            continue
        for fitting in link["fittings"]:
            if fitting["index"] in indexes:
                del fitting["source"]
    if side == "A":
        out["flags"] = [
            f
            for f in state["flags"]
            if not (f["code"] == CRANE_FLAG and f["componentId"] in lift.crane)
        ]
    return out


def differing_paths(
    a: Any, b: Any, path: str = "", limit: int = 10, names: tuple[str, str] = ("A", "B")
) -> list[str]:
    """Where two JSON values differ, as text (at most ``limit``), naming them ``names``;
    numbers compared by their JSON text, so bit for bit (-0.0 is not 0.0)."""
    out: list[str] = []
    first, second = names

    def walk(x: Any, y: Any, where: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for key in sorted(x.keys() | y.keys()):
                if key not in x or key not in y:
                    out.append(f"{where}.{key}: only in {first if key in x else second}")
                else:
                    walk(x[key], y[key], f"{where}.{key}")
        elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
            for i, (u, v) in enumerate(zip(x, y, strict=True)):
                walk(u, v, f"{where}[{i}]")
        elif json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True):
            out.append(
                f"{where}: {json.dumps(x)[:120]} in {first}, {json.dumps(y)[:120]} in {second}"
            )

    walk(a, b, path)
    return out


def exact_problems(a: dict[str, Any], b: dict[str, Any], lift: Lifted) -> list[str]:
    """(b) of mode exact: the masked states' JSON texts are identical."""
    ma, mb = masked(a, lift, "A"), masked(b, lift, "B")
    if json.dumps(ma, sort_keys=True) == json.dumps(mb, sort_keys=True):
        return []
    found = differing_paths(ma, mb)
    return [f"(b) {p}" for p in found] or ["(b) the states' JSON texts differ"]


# --------------------------------------------------------------------------- mode rebased


def twin_problems(b: dict[str, Any], lift: Lifted) -> list[str] | None:
    """(y) of mode rebased: B's solved state is its inline twin's (``inline_twin``) bit for bit,
    for every outcome, with the paths mode exact leaves out: the timestamp, the trace and the
    source of each fitting result that names an entry (None: the twin has no inline form)."""
    data = inline_twin(lift)
    if data is None:
        return None
    try:
        twin = solve(Project.model_validate(data))
    except ValidationError as exc:
        return [f"(y) the inline twin does not validate: {exc.errors()[:3]}"]
    if twin.state is None:
        return [f"(y) {twin.kind} in the inline twin, a solved state in B"]
    referring = {
        conn["id"]: [
            j for j, f in enumerate(conn["piping"].get("fittings", [])) if f.get("resistanceId")
        ]
        for conn in lift.data["connections"]
    }
    mask = replace(lift, fittings=referring)
    mt, mb = masked(twin.state, mask, "B"), masked(b, mask, "B")
    if json.dumps(mt, sort_keys=True) == json.dumps(mb, sort_keys=True):
        return []
    found = differing_paths(mt, mb, names=("the twin", "B"))
    return [f"(y) {p}" for p in found] or ["(y) the states' JSON texts differ"]


def valve_problems(
    a: dict[str, Any], b: dict[str, Any], lift: Lifted
) -> tuple[list[str], list[str]]:
    """(c) and (d) of mode rebased: (differences, values different only at zero flow)."""
    rho = float(a["fluid"]["density"])
    differences: list[str] = []
    at_zero: list[str] = []
    for vid in lift.valves:
        va, vb = a["valveResults"].get(vid), b["valveResults"].get(vid)
        if va is None or vb is None:
            if va is not None or vb is not None:
                flow = (va or vb or {})["flow"]
                text = f"(c) {vid}: a result in {'A' if va is not None else 'B'} only"
                (at_zero if flow == 0.0 else differences).append(text)
            continue
        for key, quantity in (("flow", "flow"), ("headLoss", "head")):
            if abs(vb[key] - va[key]) > d6(quantity, va[key], rho):
                text = f"(c) {key} of {vid}: {va[key]!r} in A, {vb[key]!r} in B"
                (at_zero if 0.0 in (va["flow"], vb["flow"]) else differences).append(text)
        if not abs(vb["kOpen"] - va["kOpen"]) <= ROUND_OFF * abs(va["kOpen"]):
            differences.append(f"(d) kOpen of {vid}: {va['kOpen']!r} in A, {vb['kOpen']!r} in B")
    for conn, indexes in lift.fittings.items():
        la, lb = a["linkResults"].get(conn), b["linkResults"].get(conn)
        if la is None or lb is None:
            continue
        ka = {f["index"]: f["k"] for f in la["fittings"]}
        kb = {f["index"]: f["k"] for f in lb["fittings"]}
        for j in indexes:
            if j in ka and not abs(kb.get(j, math.inf) - ka[j]) <= ROUND_OFF * abs(ka[j]):
                differences.append(
                    f"(d) k of {conn} fitting {j + 1}: {ka[j]!r} in A, {kb.get(j)!r} in B"
                )
    return differences, at_zero


def k_differences(a: dict[str, Any], b: dict[str, Any], lift: Lifted) -> list[float]:
    """The relative differences of the lifted K (valves' kOpen, fittings' k), B against A."""
    out = [
        abs(b["valveResults"][v]["kOpen"] - a["valveResults"][v]["kOpen"])
        / a["valveResults"][v]["kOpen"]
        for v in lift.valves
        if v in a["valveResults"] and v in b["valveResults"] and a["valveResults"][v]["kOpen"]
    ]
    for conn, indexes in lift.fittings.items():
        la, lb = a["linkResults"].get(conn), b["linkResults"].get(conn)
        if la is None or lb is None:
            continue
        ka = {f["index"]: f["k"] for f in la["fittings"]}
        kb = {f["index"]: f["k"] for f in lb["fittings"]}
        out += [abs(kb[j] - ka[j]) / ka[j] for j in indexes if j in ka and j in kb and ka[j]]
    return out


def largest_differences(a: dict[str, Any], b: dict[str, Any], lift: Lifted) -> dict[str, float]:
    """The largest differences between A's and B's values that both have, recorded with no
    threshold: 'flow', of the connections and the lifted valves, relative to the largest flow
    of A; 'head', m, of the port EGLs, the static pressures as heads (÷ ρg) and the lifted
    valves' head losses; 'k', of the lifted K, relative."""
    rho_g = float(a["fluid"]["density"]) * G
    q_max = max((abs(link["flow"]) for link in a["linkResults"].values()), default=0.0)
    flows = [
        abs(b["linkResults"][k]["flow"] - link["flow"])
        for k, link in a["linkResults"].items()
        if k in b["linkResults"]
    ]
    heads = []
    for key, node in a["nodeResults"].items():
        other = b["nodeResults"].get(key)
        if other is not None:
            heads += [abs(other["egl"] - node["egl"]), abs(other["pressure"] - node["pressure"])]
            heads[-1] /= rho_g
    for vid in lift.valves:
        va, vb = a["valveResults"].get(vid), b["valveResults"].get(vid)
        if va is not None and vb is not None:
            flows.append(abs(vb["flow"] - va["flow"]))
            heads.append(abs(vb["headLoss"] - va["headLoss"]))
    return {
        "flow": max(flows, default=0.0) / q_max if q_max > 0.0 else max(flows, default=0.0),
        "head": max(heads, default=0.0),
        "k": max(k_differences(a, b, lift), default=0.0),
    }


# --------------------------------------------------------------------------- one project


def check_mode(
    project: Project,
    a: Outcome,
    mode: str,
    k_scale: float = 1.0,
    bore_scale: float = 1.0,
) -> dict[str, Any]:
    """One mode's record for a project whose solve A gave ``a``."""
    lift = lifted(project, a.state, mode, k_scale, bore_scale)
    record: dict[str, Any] = {"counts": dict(lift.counts), "differences": [], "atZeroFlow": []}
    if not anything_lifted(lift):
        record["outcome"] = "none_lifted"
        return record
    differences: list[str] = record["differences"]
    try:
        b_project = Project.model_validate(lift.data)
    except ValidationError as exc:
        record["outcome"] = "different"
        differences.append(f"(v) the lifted project does not validate: {exc.errors()[:3]}")
        return record
    b = solve(b_project)
    record["outcome"] = "checked"
    record["solved"] = a.kind
    differences += outcome_problems(a, b)
    if a.state is not None and b.state is not None:
        differences += bore_problems(lift, a.state)
        differences += trace_problems(b.state, lift)
        if mode == "exact":
            differences += exact_problems(a.state, b.state, lift)
            record["craneFlags"] = len(a.state["flags"]) - len(masked(a.state, lift, "A")["flags"])
        elif a.state["converged"] and b.state["converged"]:
            found, at_zero = network_problems(lift.data, a.state, b.state)
            differences += found
            record["atZeroFlow"] += at_zero
            found, at_zero = valve_problems(a.state, b.state, lift)
            differences += found
            record["atZeroFlow"] += at_zero
            record["largest"] = largest_differences(a.state, b.state, lift)
    if mode == "rebased" and b.state is not None:
        found_twin = twin_problems(b.state, lift)
        record["twin"] = found_twin is not None
        differences += found_twin or []
    if differences:
        record["outcome"] = "different"
    return record


def check(
    name: str,
    project: Project,
    modes: tuple[str, ...] = MODES,
    k_scale: float = 1.0,
    bore_scale: float = 1.0,
) -> dict[str, Any]:
    """The record of one project: its outcome, each mode's record, and every difference found,
    named by its mode (none: passed). ``k_scale`` and ``bore_scale`` falsify the lifting (1:
    the project's own values)."""
    record: dict[str, Any] = {
        "name": name,
        "profile": profile(name),
        "differences": [],
        "atZeroFlow": [],
        "modes": {},
    }
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    base.pop("scenarios", None)
    project = Project.model_validate(base)  # A and B both through the API JSON, without scenarios
    a = solve(project)
    record["outcome"] = "checked"
    for mode in modes:
        sub = check_mode(project, a, mode, k_scale, bore_scale)
        record["modes"][mode] = sub
        record["differences"] += [f"[{mode}] {d}" for d in sub["differences"]]
        record["atZeroFlow"] += [f"[{mode}] {t}" for t in sub["atZeroFlow"]]
    if record["differences"]:
        record["outcome"] = "different"
    return record


# --------------------------------------------------------------------------- the corpus


def run(work: tuple[tuple[str, ...], Item]) -> dict[str, Any]:
    modes, (name, spec) = work
    try:
        project = load(spec)
    except Exception as ex:  # a corpus file that does not load is not a library finding
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "load_error",
            "error": repr(ex),
            "differences": [],
            "atZeroFlow": [],
            "modes": {},
        }
    try:
        return check(name, project, modes)
    except Exception as ex:
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "crash",
            "differences": [f"crash: {ex!r}"],
            "atZeroFlow": [],
            "modes": {},
        }


def check_all(
    selection: list[Item], workers: int = 1, modes: tuple[str, ...] = MODES
) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order."""
    work = [(modes, item) for item in selection]
    if workers <= 1:
        return [run(w) for w in work]
    with Pool(workers) as pool:
        return pool.map(run, work, chunksize=4)


COLUMNS = (
    "projects",
    "checked",
    "different",
    "specs",
    "segments",
    "custom",
    "explicit",
    "farshad",
    "entries",
    "K",
    "Cv",
    "Kv",
    "crane",
    "fittings",
    "shared",
    "crane_flags",
    "down",
    "unresolved",
    "ideal",
    "no_result",
    "no_bore",
    "zero_k",
    "over_limit",
    "already",
    "not_converged",
    "topology_error",
    "error",
    "at_zero_flow",
    "twin",
    "none_lifted",
    "load_error",
    "crash",
)
"""The report's columns, per mode and profile (module docstring)."""


def summarize(records: list[dict[str, Any]], modes: tuple[str, ...] = MODES) -> list[str]:
    """The report's lines (module docstring)."""
    lines: list[str] = []
    for mode in modes:
        by_profile: dict[str, Counter[str]] = defaultdict(Counter)
        for r in records:
            tally = by_profile[r["profile"]]
            tally["projects"] += 1
            sub = r["modes"].get(mode)
            if sub is None:
                tally[r["outcome"]] += 1
                continue
            tally[sub["outcome"]] += 1
            for kind, n in sub["counts"].items():
                tally[kind] += n
            if sub.get("solved") in ("not_converged", "topology_error", "error"):
                tally[sub["solved"]] += 1
            tally["crane_flags"] += sub.get("craneFlags", 0)
            tally["at_zero_flow"] += len(sub["atZeroFlow"])
            tally["twin"] += int(sub.get("twin", False))
        lines.append(f"mode {mode}")
        lines.append("profile " + " ".join(COLUMNS))
        total: Counter[str] = Counter()
        for name in sorted(by_profile, key=lambda p: (*PROFILES, p).index(p)):
            tally = by_profile[name]
            total += tally
            lines.append(f"{name} " + " ".join(str(tally[c]) for c in COLUMNS))
        lines.append("all " + " ".join(str(total[c]) for c in COLUMNS))
        compared = [(r["name"], r["modes"][mode]) for r in records if mode in r["modes"]]
        compared = [(n, sub) for n, sub in compared if "largest" in sub]
        for quantity, unit in (
            ("flow", "× the largest flow"),
            ("head", "m (pressures as heads)"),
            ("k", "relative"),
        ):
            worst = max(compared, key=lambda t: t[1]["largest"][quantity], default=None)
            if worst is not None:
                lines.append(
                    f"largest {quantity} difference ({mode}):"
                    f" {worst[1]['largest'][quantity]:.3g} {unit} ({worst[0]})"
                )
    for r in records:
        for text in r["atZeroFlow"]:
            lines.append(f"at zero flow: {r['name']} {text}")
    different = [r for r in records if r["differences"]]
    for r in different:
        lines.append(f"{r['name']}: " + "; ".join(r["differences"][:10]))
    lines.append(f"different: {len(different)}")
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.library_check",
        description="Check the project library against the values it stands for over the"
        " corpus (proposal project-library.md §7.2).",
    )
    parser.add_argument(
        "--mode", choices=MODES, action="append", help="a mode to run (default: both)"
    )
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument("--out", default="", help="write every project's record to this file")
    args = parser.parse_args(argv)
    modes = tuple(args.mode) if args.mode else MODES
    selection = [t for t in items() if t[0].startswith(args.only)]
    print(f"projects: {len(selection)}", flush=True)
    records = check_all(selection, args.workers, modes)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1, sort_keys=True)
    print("\n".join(summarize(records, modes)))
    sys.exit(1 if any(r["differences"] for r in records) else 0)


if __name__ == "__main__":
    main()
