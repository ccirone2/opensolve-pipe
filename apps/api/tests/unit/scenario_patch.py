"""An independent reference for applying a scenario (proposal scenario-manager.md §7.2): the base
project's JSON with the scenario's overrides written by hand, P_hand. It never calls
``services.scenarios``, so the two implementations check each other; it states the rules again
from the proposal (§2.2, §3.3) in its own, simpler form. Test helper, also used by
``tests/differential/scenario_check.py``."""

import copy
import json
import random
from pathlib import Path
from typing import Any

SPEC_KEYS = ("materialId", "schedule", "nominalSize", "innerDiameter", "roughness")

_ISOLATION = {"status", "resistance"}
FIELDS = {
    "reservoir": {"liquidLevel", "surfacePressure"},
    "reference_node": {"pressure"},
    "assigned_flow": {"flow"},
    "plug": set(),
    "branch": set(),
    "pump": {"status", "speed", "control.setpoint"},
    "valve:gate": _ISOLATION,
    "valve:ball": _ISOLATION,
    "valve:butterfly": _ISOLATION,
    "valve:globe": _ISOLATION,
    "valve:check": _ISOLATION,
    "valve:stop_check": _ISOLATION,
    "valve:prv": _ISOLATION | {"setpoint"},
    "valve:psv": _ISOLATION | {"setpoint"},
    "valve:fcv": _ISOLATION | {"setpoint"},
}
"""The overridable fields of each component kind, restated from the proposal's table (§2.2)."""


def _kind(component: dict[str, Any]) -> str:
    if component["type"] == "valve":
        return f"valve:{component['valveType']}"
    return str(component["type"])


def hand_patched(
    project: dict[str, Any], overrides: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """(P_hand's JSON, each override's state): ``project`` (API JSON) without its scenarios and
    with every applicable override's value written where it belongs; a spec replaces the
    pipe's five spec keys. Values are written as given (the models check them)."""
    data = copy.deepcopy(project)
    data.pop("scenarios", None)
    states: list[str] = []
    for override in overrides:
        kind, field, value = override["kind"], override["field"], override["value"]
        if kind == "component":
            found = [c for c in data["components"] if c["id"] == override["componentId"]]
            if not found:
                states.append("orphaned")
                continue
            holder: dict[str, Any] = found[0]
            if field not in FIELDS[_kind(holder)]:
                states.append("not_applicable")
                continue
            *parents, leaf = field.split(".")
            if parents and holder.get(parents[0]) is None:  # no speed control in the base
                states.append("not_applicable")
                continue
            for name in parents:
                holder = holder[name]
            holder[leaf] = copy.deepcopy(value)
        elif kind == "pipe":
            conns = [c for c in data["connections"] if c["id"] == override["connectionId"]]
            pipes = conns[0]["piping"]["pipes"] if conns else []
            if override["pipeIndex"] >= len(pipes):
                states.append("orphaned")
                continue
            pipe = pipes[override["pipeIndex"]]
            if field == "length":
                pipe["length"] = value
            else:
                for key in SPEC_KEYS:
                    pipe.pop(key, None)
                pipe.update(copy.deepcopy(value))
        elif field == "fluid":
            data["fluid"] = copy.deepcopy(value)
        else:  # fluid.temperature
            if data["fluid"]["kind"] != "builtin":
                states.append("not_applicable")
                continue
            data["fluid"]["temperature"] = value
        states.append("applied")
    return data, states


# --------------------------------------------------------------------------- seeded scenarios

STATUSES = {
    "pump": ("on", "off"),
    "isolation": ("active", "isolated"),
    "check": ("active", "locked_open", "locked_closed"),
    "control": ("active", "failed_open", "failed_closed"),
}
_FAMILY = {"gate": "isolation", "ball": "isolation", "butterfly": "isolation", "globe": "isolation"}
_FAMILY |= {"check": "check", "stop_check": "check", "prv": "control", "psv": "control"}
_FAMILY |= {"fcv": "control"}


def _library_sizes() -> dict[tuple[str, str], list[float]]:
    """Nominal sizes, m, by (material, schedule), from data/pipe_materials.json."""
    path = Path(__file__).parents[2] / "src" / "opensolve_pipe" / "data" / "pipe_materials.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        (m["id"], s["id"]): [size["nominalSize"] for size in s["sizes"]]
        for m in data["materials"]
        for s in m["schedules"]
    }


LIBRARY_SIZES = _library_sizes()


def _status(component: dict[str, Any]) -> str:
    family = "pump" if component["type"] == "pump" else _FAMILY[component["valveType"]]
    current = component.get("status", STATUSES[family][0])
    return str(current)


def _other_status(rng: random.Random, component: dict[str, Any]) -> str:
    family = "pump" if component["type"] == "pump" else _FAMILY[component["valveType"]]
    return rng.choice([s for s in STATUSES[family] if s != _status(component)])


def _spec(rng: random.Random, pipe: dict[str, Any]) -> dict[str, Any]:
    """A neighbouring library size in the same schedule, or a custom bore 0.8-1.25 times."""
    if pipe["materialId"] == "custom":
        bore = pipe["innerDiameter"] * rng.uniform(0.8, 1.25)
        return {"materialId": "custom", "innerDiameter": bore, "roughness": pipe["roughness"]}
    sizes = LIBRARY_SIZES.get((pipe["materialId"], pipe.get("schedule") or ""), [])
    if pipe.get("nominalSize") not in sizes:
        return {key: pipe[key] for key in SPEC_KEYS if pipe.get(key) is not None}
    i = sizes.index(pipe["nominalSize"])
    j = min(max(i + rng.choice((-1, 1)), 0), len(sizes) - 1)
    return {"materialId": pipe["materialId"], "schedule": pipe["schedule"], "nominalSize": sizes[j]}


def _component_value(rng: random.Random, c: dict[str, Any], field: str) -> Any:
    if field == "status":
        return _other_status(rng, c)
    if field == "speed":
        low = c["control"]["minSpeed"] + 0.02 if c.get("control") else 0.7
        return rng.uniform(min(low, 0.99), 1.0)
    if field == "control.setpoint":
        return c["control"]["setpoint"] * rng.uniform(0.8, 1.2)
    if field == "setpoint":
        if c["valveType"] == "fcv":
            return c["setpoint"] * rng.uniform(0.8, 1.2)
        return c["setpoint"] * rng.uniform(0.9, 1.1) + rng.uniform(-1.0e4, 1.0e4)
    if field == "resistance":
        return rng.choice([None, {"kind": "K", "value": rng.uniform(0.1, 10.0)}])
    if field == "liquidLevel":
        return max(0.0, c["liquidLevel"] + rng.uniform(-1.0, 1.0))
    if field == "surfacePressure":
        return c.get("surfacePressure", 0.0) + rng.uniform(-1.0e4, 5.0e4)
    if field == "pressure":
        return c["pressure"] * rng.uniform(0.9, 1.1) + rng.uniform(-1.0e4, 1.0e4)
    if field == "flow":
        return c["flow"] * rng.uniform(0.8, 1.2)
    raise ValueError(field)


def _whole_fluid(rng: random.Random, fluid: dict[str, Any]) -> dict[str, Any]:
    changed = copy.deepcopy(fluid)
    if fluid["kind"] == "custom":
        changed["density"] = fluid["density"] * rng.uniform(0.95, 1.05)
    else:
        changed["temperature"] = fluid["temperature"] + rng.uniform(-5.0, 5.0)
    return changed


def draw_overrides(
    project: dict[str, Any], rng: random.Random, *, ignored: int = 0
) -> list[dict[str, Any]]:
    """1-6 overrides drawn uniformly over the (target, field) pairs ``project`` (API JSON) has,
    with values near the base ones (proposal §7.3), then ``ignored`` orphaned or not-applicable
    ones; in random order."""
    pairs: list[tuple[dict[str, Any], Any]] = []
    for c in project["components"]:
        for field in sorted(FIELDS[_kind(c)]):
            if field == "control.setpoint" and not c.get("control"):
                continue
            target = {"kind": "component", "componentId": c["id"], "field": field}
            pairs.append((target, lambda c=c, f=field: _component_value(rng, c, f)))
    for conn in project["connections"]:
        for i, p in enumerate(conn["piping"]["pipes"]):
            target = {"kind": "pipe", "connectionId": conn["id"], "pipeIndex": i}
            pairs.append(({**target, "field": "spec"}, lambda p=p: _spec(rng, p)))
            pairs.append(
                ({**target, "field": "length"}, lambda p=p: p["length"] * rng.uniform(0.5, 2.0))
            )
    fluid = project["fluid"]
    fluid_pairs = [({"kind": "project", "field": "fluid"}, lambda: _whole_fluid(rng, fluid))]
    if fluid["kind"] == "builtin":
        temperature = fluid["temperature"]
        fluid_pairs.append(
            (
                {"kind": "project", "field": "fluid.temperature"},
                lambda: temperature + rng.uniform(-10.0, 10.0),
            )
        )
    pairs.append(rng.choice(fluid_pairs))  # never the whole fluid and a part of it
    chosen = rng.sample(pairs, min(len(pairs), rng.randint(1, 6)))
    overrides = [{**target, "value": draw()} for target, draw in chosen]
    keys = {_key(o) for o in overrides}
    while len(overrides) < len(chosen) + ignored:
        extra = _ignored(rng, project, len(overrides))
        if _key(extra) not in keys:  # one override per value (Scenario's rule)
            keys.add(_key(extra))
            overrides.append(extra)
    rng.shuffle(overrides)
    return overrides


def _key(override: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("kind", "componentId", "connectionId", "pipeIndex", "field")
    return tuple(override.get(k) for k in keys)


def _ignored(rng: random.Random, project: dict[str, Any], n: int) -> dict[str, Any]:
    """An orphaned or not-applicable override (a value it never applies); ``n`` makes a missing
    component's id distinct."""
    ids = {c["id"] for c in project["components"]} | {c["id"] for c in project["connections"]}
    choice = rng.randrange(3)
    if choice == 0:
        missing = next(f"ZZ{n}_{i}" for i in range(1000) if f"ZZ{n}_{i}" not in ids)
        return {"kind": "component", "componentId": missing, "field": "status", "value": "off"}
    if choice == 1:
        conn = rng.choice(project["connections"])
        index = len(conn["piping"]["pipes"]) + rng.randrange(3)
        return {
            "kind": "pipe",
            "connectionId": conn["id"],
            "pipeIndex": index,
            "field": "length",
            "value": 1.0,
        }
    c = rng.choice(project["components"])
    field = next(
        f for f in ("status", "liquidLevel", "pressure", "flow") if f not in FIELDS[_kind(c)]
    )
    return {"kind": "component", "componentId": c["id"], "field": field, "value": 1.0}
