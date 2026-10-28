"""Smoke test of the project-library corpus check (``library_check``, proposal project-library.md
§7.2): the reference cases, the unit-test data networks and a few seeds of each fuzz profile go
through the same checks as ``python -m tests.differential.library_check``, in both modes, and
none may differ. The selection must reach every lifting the check makes (a custom pipe spec and
one on a library material; valves with a K, a Cv, a Kv and a Crane default; fittings; an entry
shared by several elements; a Crane flag that goes with its default) and solves that did not
converge, so that a check that compared nothing would fail here. A spec with no roughness
(Farshad's at its bore), the 100-entry limit, a topology issue and a project that already refers
to the library are made here, since the corpus has none. And the checks themselves must catch a
lifted value one unit in the last place off in mode exact, a K 21 % or one part in 10⁹ off in
mode rebased, any change outside the paths mode exact leaves out, and a trace or methods summary
that does not name an entry; and in mode rebased B must equal its inline twin bit for bit, which
must catch a value one unit in the last place off. The full corpus run is the command-line
tool."""

import copy
import json
import math
from collections import Counter
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver.library import resolve_pipe
from tests.differential.corpus import items, load
from tests.differential.library_check import (
    CRANE_FLAG,
    MODES,
    REBASE,
    Lifted,
    check,
    check_all,
    differing_paths,
    exact_problems,
    lifted,
    references,
    solve,
    stated_bore,
    summarize,
    trace_problems,
    twin_problems,
)

SMOKE_FUZZ = (
    [f"fuzz_{s}" for s in range(60)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_050)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_050)]
)
ULP = 1.0 + 2.0**-52
"""A factor that moves a double by about one unit in the last place."""


def _item(name: str) -> Any:
    return next(spec for n, spec in items() if n == name)


def _json(name: str) -> dict[str, Any]:
    return load(_item(name)).model_dump(mode="json", by_alias=True, exclude_unset=True)


def test_library_over_the_reference_cases_unit_networks_and_fuzz_seeds() -> None:
    selection = [t for t in items() if t[0].startswith(("ref_", "unit_")) or t[0] in SMOKE_FUZZ]
    assert len([t for t in selection if t[0].startswith("fuzz")]) == len(SMOKE_FUZZ)
    records = check_all(selection)
    different = [f"{r['name']}: {'; '.join(r['differences'])}" for r in records if r["differences"]]
    assert not different, "\n".join(different)
    outcomes = Counter(r["outcome"] for r in records)
    assert outcomes["load_error"] == outcomes["crash"] == 0, outcomes
    for mode in MODES:
        tally: dict[str, Counter[str]] = {}
        for r in records:
            sub = r["modes"][mode]
            counted = tally.setdefault(r["profile"], Counter())
            counted.update(sub["counts"])
            counted[sub["outcome"]] += 1
            counted[sub.get("solved", "")] += 1
            counted["crane_flags"] += sub.get("craneFlags", 0)
            counted["twin"] += int(sub.get("twin", False))
        for profile in ("ref", "fuzz", "fuzzfc", "fuzzaf"):
            for kind in ("custom", "K", "Cv", "Kv", "crane", "fittings"):
                assert tally[profile][kind] >= 1, (mode, profile, kind, tally[profile])
        total: Counter[str] = sum(tally.values(), Counter())
        assert total["checked"] >= 250, (mode, total)
        assert total["explicit"] >= 1, total  # a spec on a library material (unit_rich*)
        assert total["segments"] > total["specs"], total  # specs shared by segments
        assert total["shared"] >= 1, total  # an entry shared by elements
        assert total["ideal"] >= 1, total  # control valves without a resistance stay inline
        assert total["not_converged"] >= 1, total  # mode exact: bit for bit there too
        if mode == "exact":
            assert total["crane_flags"] >= 1, total
        else:  # (y): every project B solved, converged or not, against its inline twin
            assert total["twin"] == total["converged"] + total["not_converged"], total
    lines = summarize(records)
    assert lines[-1] == "different: 0"
    assert lines[:2] == [
        "mode exact",
        "profile projects checked different specs segments custom explicit farshad entries K Cv"
        " Kv crane fittings shared crane_flags down unresolved ideal no_result no_bore zero_k"
        " over_limit already not_converged topology_error error at_zero_flow twin none_lifted"
        " load_error crash",
    ]
    assert any(line.startswith("largest k difference (rebased)") for line in lines)


@pytest.mark.parametrize(
    "name",
    [
        "ref_isolation_valves_kv_and_k",
        "ref_isolation_valves_crane_default_k",
        "unit_rich1090",
        "fuzz_25",
        "fuzzaf_20014",
    ],
)
def test_a_value_one_unit_in_the_last_place_off_is_reported_in_mode_exact(name: str) -> None:
    """Every lifted K × (1 + 2⁻⁵²), or every spec's bore: mode exact reports (b), and mode
    rebased, whose tolerance is D6 and round-off, does not."""
    project = load(_item(name))
    for k_scale, bore_scale in ((ULP, 1.0), (1.0, ULP)):
        record = check(name, project, k_scale=k_scale, bore_scale=bore_scale)
        assert record["outcome"] == "different", (k_scale, bore_scale, record)
        assert all(d.startswith("[exact] (b)") for d in record["differences"]), record
        assert record["modes"]["rebased"]["differences"] == [], record
    assert check(name, project)["differences"] == []


@pytest.mark.parametrize(
    "name",
    [
        "ref_isolation_valve_cv",
        "ref_isolation_valves_kv_and_k",
        "ref_isolation_valves_crane_default_k",
        "fuzzaf_20014",
    ],
)
def test_a_falsified_k_is_reported_in_mode_rebased(name: str) -> None:
    """Every lifted K × 1.21 (a Cv or Kv ÷ 1.1, the same change of loss) where the valves' loss
    matters: flows and head losses beyond D6, (b) and (c), and the K itself, (d); K × (1 +
    10⁻⁹): (d) alone, a change D6 cannot see."""
    project = load(_item(name))

    def letters(k_scale: float) -> set[str]:
        record = check(name, project, ("rebased",), k_scale=k_scale)
        return {d.split(" ", 2)[1] for d in record["differences"]}

    assert {"(b)", "(c)", "(d)"} <= letters(1.21)
    assert letters(1.0 + 1.0e-9) == {"(d)"}
    assert letters(1.0) == set()


def test_the_lifting() -> None:
    """Every segment refers to a spec holding the bore and roughness the solver resolves it to,
    with only its length beside it; a Kv valve to a Kv entry as entered; a K valve to a K entry
    at its reference bore (mode exact) or at 1.1 times it with K₀ = K·1.1⁴ (mode rebased); and
    no new id is one the project uses."""
    name = "ref_isolation_valves_kv_and_k"
    project = load(_item(name))
    base = _json(name)
    a = solve(project).state
    assert a is not None
    used = {c["id"] for c in base["components"]} | {c["id"] for c in base["connections"]}
    for mode in MODES:
        lift = lifted(project, a, mode)
        data = lift.data
        Project.model_validate(data)
        specs = {s["id"]: s for s in data["pipeLibrary"]}
        entries = {e["id"]: e for e in data["resistanceLibrary"]}
        assert not (specs.keys() | entries.keys()) & used
        for conn, model in zip(data["connections"], project.connections, strict=True):
            for pipe, defn in zip(conn["piping"]["pipes"], model.piping.pipes, strict=True):
                assert pipe.keys() == {"specId", "length"}
                assert pipe["length"] == defn.length
                spec, resolved = specs[pipe["specId"]], resolve_pipe(defn)
                assert spec["materialId"] == defn.material_id
                assert spec["innerDiameter"] == resolved.inner_diameter
                assert spec["roughness"] == resolved.roughness
                assert spec["source"]
        valves = {c["id"]: c for c in base["components"] if c["type"] == "valve"}
        assert lift.valves == {v: c["resistance"]["kind"] for v, c in valves.items()}
        for vid, valve in valves.items():
            ref = next(c for c in data["components"] if c["id"] == vid)["resistance"]
            assert ref["kind"] == "library"
            entry, own = entries[ref["id"]], valve["resistance"]
            assert entry["kind"] == own["kind"]
            d = a["valveResults"][vid]["referenceDiameter"]
            if own["kind"] != "K":
                assert entry["value"] == own["value"]
                assert "referenceDiameter" not in entry
            elif mode == "exact":
                assert (entry["value"], entry["referenceDiameter"]) == (own["value"], d)
            else:
                assert entry["referenceDiameter"] == REBASE * d
                assert entry["value"] == pytest.approx(own["value"] * REBASE**4, rel=1e-14)
                moved = entry["value"] * (d / entry["referenceDiameter"]) ** 4
                assert moved == pytest.approx(own["value"], rel=1e-14)


def test_stated_bore() -> None:
    """Mode exact states a K at the element's bore; mode rebased at 1.1 times it, or at the bore
    ÷ 1.1 where 1.1 times would pass a bore's 10 m or K₀ a coefficient's 10⁷."""
    assert stated_bore(0.3, 0.2, "exact") == (0.3, 0.2, False)
    k0, d0, down = stated_bore(0.3, 0.2, "rebased")
    assert (d0, down) == (REBASE * 0.2, False)
    assert k0 * (0.2 / d0) ** 4 == pytest.approx(0.3, rel=1e-15)
    for k, d in ((0.3, 9.5), (9.0e6, 0.2)):
        k0, d0, down = stated_bore(k, d, "rebased")
        assert (d0, down) == (d / REBASE, True)
        assert k0 * (d / d0) ** 4 == pytest.approx(k, rel=1e-15)
        assert k0 < k


def test_a_spec_with_no_roughness_takes_farshad_at_its_bore() -> None:
    """A library pipe with its own inner diameter and no roughness takes Farshad's roughness at
    that bore (resolve_pipe's last branch); its spec states no roughness, so the solver
    evaluates the same function at the same bore again, bit for bit (proposal §1.2 P2). The
    corpus has no such pipe."""
    name = "ref_library_pipe_builtin_water"
    data = _json(name)
    pipes = data["connections"][0]["piping"]["pipes"]
    pipes[0]["innerDiameter"] = 0.1031  # with its schedule and size, which it overrides
    pipes[1] = {"materialId": pipes[1]["materialId"], "innerDiameter": 0.0791, "length": 50.0}
    project = Project.model_validate(data)
    record = check(name, project)
    assert record["differences"] == [], record
    for mode in MODES:
        assert record["modes"][mode]["counts"]["farshad"] == 2, record
    lift = lifted(project, solve(project).state, "exact")
    assert all("roughness" not in s for s in lift.data["pipeLibrary"])
    # and the check sees a spec that states another roughness (Farshad's at another bore)
    record = check(name, project, ("exact",), bore_scale=1.001)
    assert record["outcome"] == "different", record


def test_at_most_100_entries() -> None:
    """A project with more distinct pipe definitions than a library holds: 100 specs, the other
    segments stay inline (over_limit), and the solve is still bit for bit."""
    name = "ladder_100_1_crane_True"
    data = _json(name)
    n = 0
    for conn in data["connections"]:
        for pipe in conn["piping"]["pipes"]:
            pipe["roughness"] = 4.5e-5 * (1.0 + n * 1.0e-3)  # one definition per segment
            n += 1
    assert n > 100
    project = Project.model_validate(data)
    record = check(name, project, ("exact",))
    assert record["differences"] == [], record
    counts = record["modes"]["exact"]["counts"]
    assert (counts["specs"], counts["explicit"], counts["segments"]) == (100, 100, 100)
    assert counts["over_limit"] == n - 100


def test_topology_issues_are_compared_by_code_and_element() -> None:
    """A project that does not solve (an unknown pipe material): the pipes that resolve are
    lifted, the other stays inline, and B must raise the same topology issues, whose messages
    may differ (a lifted pipe's names its spec)."""
    name = "ref_isolation_valves_kv_and_k"
    data = _json(name)
    data["connections"][-1]["piping"]["pipes"][-1]["materialId"] = "unobtainium"
    record = check(name, Project.model_validate(data))
    assert record["differences"] == [], record
    for mode in MODES:
        sub = record["modes"][mode]
        assert sub["solved"] == "topology_error", sub
        assert sub["counts"]["unresolved"] == 1, sub
        assert sub["counts"]["segments"] >= 1, sub


def test_a_project_that_refers_to_the_library_is_left_as_it_is() -> None:
    """Lifted once, a project has nothing left to lift: every element already refers to an
    entry ('already'), and its own solve is the original's (mode exact)."""
    name = "ref_isolation_valves_kv_and_k"
    project = load(_item(name))
    lift = lifted(project, solve(project).state, "exact")
    again = check(name, Project.model_validate(lift.data))
    assert again["differences"] == []
    for mode in MODES:
        sub = again["modes"][mode]
        assert sub["outcome"] == "none_lifted", sub
        lifts = lift.counts["segments"] + len(lift.valves) + sum(map(len, lift.fittings.values()))
        assert sub["counts"]["already"] == lifts, (sub, lift.counts)


def _solved_pair(name: str) -> tuple[dict[str, Any], dict[str, Any], Lifted]:
    project = load(_item(name))
    a = solve(project).state
    assert a is not None
    lift = lifted(project, a, "exact")
    b = solve(Project.model_validate(lift.data)).state
    assert b is not None
    return a, b, lift


def test_the_paths_left_out_are_only_those_named() -> None:
    """Mode exact leaves out the timestamp, the trace, a lifted fitting's source and the Crane
    flags of a lifted Crane default, nothing else: A's Crane flags on such valves are left out,
    but one in B, one on another element, a flag B lost, the source of a fitting not lifted, a
    value one unit in the last place off or a sign of zero is reported."""
    a, b, lift = _solved_pair("unit_rich1090")
    assert exact_problems(a, b, lift) == []
    masked = [f for f in a["flags"] if f["code"] == CRANE_FLAG and f["componentId"] in lift.crane]
    assert masked, a["flags"]  # A's Crane flags, left out
    changed = copy.deepcopy(b)
    changed["timestamp"], changed["trace"] = "then", {}
    assert exact_problems(a, changed, lift) == []
    for conn, indexes in lift.fittings.items():
        for j in indexes:
            changed["linkResults"][conn]["fittings"][j]["source"] = "x"
    assert exact_problems(a, changed, lift) == []
    in_b = copy.deepcopy(b)
    in_b["flags"].append(masked[0])
    assert exact_problems(a, in_b, lift)[0].startswith("(b) .flags"), in_b["flags"]
    elsewhere = copy.deepcopy(a)
    elsewhere["flags"].append({**masked[0], "componentId": "another"})
    assert exact_problems(elsewhere, b, lift)[0].startswith("(b) .flags")
    lost = copy.deepcopy(a)
    lost["flags"].append({**masked[0], "code": "TRANSITIONAL_FLOW"})
    assert exact_problems(lost, b, lift)[0].startswith("(b) .flags")
    kept = [
        (conn, f["index"])
        for conn, link in b["linkResults"].items()
        for f in link["fittings"]
        if f["index"] not in lift.fittings.get(conn, [])
    ]
    assert kept  # Crane fittings, not lifted
    for conn, j in kept:
        changed = copy.deepcopy(b)
        changed["linkResults"][conn]["fittings"][j]["source"] = "x"
        (found,) = exact_problems(a, changed, lift)
        assert found.startswith(f"(b) .linkResults.{conn}.fittings[{j}].source"), found
    key = next(iter(b["nodeResults"]))
    changed = copy.deepcopy(b)
    egl = b["nodeResults"][key]["egl"]
    changed["nodeResults"][key]["egl"] = math.nextafter(egl, math.inf)
    (found,) = exact_problems(a, changed, lift)
    assert found.startswith(f"(b) .nodeResults.{key}.egl: {json.dumps(egl)} in A"), found
    assert differing_paths({"x": 0.0}, {"x": -0.0}) == [".x: 0.0 in A, -0.0 in B"]


def test_the_trace_names_every_entry() -> None:
    """(t): the trace of an element that refers to an entry made by the check names it by id,
    with its source, and the methods summary names every entry made; an element's trace or a
    methods summary without them is reported."""
    _, b, lift = _solved_pair("unit_rich1090")
    assert trace_problems(b, lift) == []
    refs = references(lift)
    assert {"valve", "pipe", "fitting"} <= {
        "valve" if e in lift.valves else "fitting" if e in lift.fittings else "pipe" for e in refs
    }
    for element in refs:
        changed = copy.deepcopy(b)
        del changed["trace"]["elements"][element]
        assert trace_problems(changed, lift) == [
            f"(t) the trace of {element} does not name {sorted(refs[element])}"
        ]
    changed = copy.deepcopy(b)
    changed["trace"]["methods"]["sections"] = []
    (found,) = trace_problems(changed, lift)
    assert found.startswith("(t) the methods summary does not name ['PS1'"), found


def test_b_is_its_inline_twin_bit_for_bit() -> None:
    """(y) of mode rebased: B's solved state is that of B's project with every reference typed on
    its element (a K entry as K₀ (D/d₀)⁴ on the element's bore), bit for bit; the source of a
    fitting result that names an entry is left out, but the source of another fitting, or a
    value one unit in the last place off, is reported."""
    name = "unit_rich1090"
    project = load(_item(name))
    a = solve(project).state
    assert a is not None
    lift = lifted(project, a, "rebased")
    b = solve(Project.model_validate(lift.data)).state
    assert b is not None
    assert lift.fittings  # K entries on fittings
    assert {"crane", "Cv"} <= set(lift.valves.values())  # K and Cv entries on valves
    assert twin_problems(b, lift) == []
    changed = copy.deepcopy(b)
    for conn, indexes in lift.fittings.items():
        for j in indexes:
            changed["linkResults"][conn]["fittings"][j]["source"] = "x"
    changed["timestamp"], changed["trace"] = "then", {}
    assert twin_problems(changed, lift) == []
    conn, j = next(
        (conn, f["index"])
        for conn, link in b["linkResults"].items()
        for f in link["fittings"]
        if f["index"] not in lift.fittings.get(conn, [])
    )
    changed = copy.deepcopy(b)
    changed["linkResults"][conn]["fittings"][j]["source"] = "x"
    (found,) = twin_problems(changed, lift) or ["none"]
    assert found.startswith(f"(y) .linkResults.{conn}.fittings[{j}].source"), found
    key = next(iter(b["nodeResults"]))
    changed = copy.deepcopy(b)
    egl = b["nodeResults"][key]["egl"]
    changed["nodeResults"][key]["egl"] = math.nextafter(egl, math.inf)
    (found,) = twin_problems(changed, lift) or ["none"]
    assert found.startswith(f"(y) .nodeResults.{key}.egl: {json.dumps(egl)} in the twin"), found
