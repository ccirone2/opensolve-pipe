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

from fluids.constants import psi
from fluids.safety_valve import API526_A, API526_letters

SPEC_KEYS = ("materialId", "schedule", "nominalSize", "innerDiameter", "roughness", "specId")
"""A pipe's spec: its five values, or a project library pipe spec (CLAUDE.md D22), replaced
together."""

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
    "equipment": {"rating", "rating.pressureLoss", "rating.flow", "rating.density", "rating.value"},
    "orifice": {"boreDiameter", "dischargeCoefficient"},
    "relief_valve": {
        "status",
        "setPressure",
        "capacity",
        "capacity.letter",
        "capacity.area",
        "capacity.dischargeCoefficient",
        "capacity.overpressure",
    },
}
"""The overridable fields of each component kind, restated from the proposal's table (§2.2),
equipment-pressure-drop.md §5.1, orifice-plate.md §5.1 and pressure-relief-valve.md decision
18."""

RATING_VALUES = {
    "point": ("pressureLoss", "flow", "density"),
    "Cv": ("value",),
    "Kv": ("value",),
}
"""The values an equipment item's rating holds, by its kind (equipment-pressure-drop.md decision
22): a part of the other kind does not apply."""


CAPACITY_VALUES = {
    "api526": ("letter",),
    "effective": ("area",),
    "certified": ("area", "dischargeCoefficient", "overpressure"),
}
"""The values a relief valve's capacity holds, by its kind (pressure-relief-valve.md decisions 7
and 18): a value of another kind does not apply."""
ASME_SCOPE = 15.0 * psi
"""Pa: ASME VIII's scope, the lowest set at which ASME's default overpressure is cited
(pressure-relief-valve.md decision 6); fluids' psi."""


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
            if parents == ["rating"] and leaf not in RATING_VALUES[holder["rating"]["kind"]]:
                states.append("not_applicable")  # a value the base rating's kind does not hold
                continue
            if parents == ["capacity"] and leaf not in CAPACITY_VALUES[holder["capacity"]["kind"]]:
                states.append("not_applicable")  # a value the base capacity's kind does not hold
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
    "relief": ("active", "locked_closed"),
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


def _family(component: dict[str, Any]) -> str:
    if component["type"] in ("pump", "relief_valve"):
        return "pump" if component["type"] == "pump" else "relief"
    return _FAMILY[component["valveType"]]


def _status(component: dict[str, Any]) -> str:
    current = component.get("status", STATUSES[_family(component)][0])
    return str(current)


def _other_status(rng: random.Random, component: dict[str, Any]) -> str:
    return rng.choice([s for s in STATUSES[_family(component)] if s != _status(component)])


def _spec(rng: random.Random, pipe: dict[str, Any]) -> dict[str, Any]:
    """A neighbouring library size in the same schedule, or a custom bore 0.8-1.25 times; a pipe
    of a project library spec keeps it."""
    if pipe.get("specId") is not None:
        return {"specId": pipe["specId"]}
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
    if field == "rating":
        return _rating(rng, c["rating"])
    if field.startswith("rating."):  # a dirty strainer's drop, or another rated flow or fluid
        part = field.split(".", 1)[1]
        low, high = (0.5, 2.0) if part == "pressureLoss" else (0.8, 1.25)
        return min(c["rating"][part] * rng.uniform(low, high), RATING_MAX[part])
    if field == "boreDiameter":  # a second plate (orifice-plate.md §5.1)
        return min(c["boreDiameter"] * rng.uniform(0.8, 1.2), ORIFICE_BORE_MAX)
    if field == "dischargeCoefficient":  # ISO 5167-2's (null), or a calibrated or vendor's C
        held = c.get("dischargeCoefficient")
        entered = held * rng.uniform(0.95, 1.05) if held is not None else rng.uniform(0.58, 0.66)
        return rng.choice([None, min(entered, 1.0)])
    if field == "setPressure" or field == "capacity" or field.startswith("capacity."):
        return _relief_value(rng, c, field)
    raise ValueError(field)


def _relief_area(capacity: dict[str, Any]) -> float:
    """m²: a capacity's area, a letter's from fluids' API 526 table."""
    if capacity["kind"] == "api526":
        return float(API526_A[API526_letters.index(capacity["letter"])])
    return float(capacity["area"])


def _defaulted(capacity: dict[str, Any]) -> bool:
    """Whether a capacity takes ASME's default overpressure (cited only from ASME_SCOPE on)."""
    return capacity["kind"] != "certified" or capacity.get("overpressure") is None


def _relief_value(rng: random.Random, c: dict[str, Any], field: str) -> Any:
    """Another set, valve or certification near the base one (pressure-relief-valve.md decision
    18), never a defaulted overpressure below ASME_SCOPE (decision 14's refusal)."""
    capacity = c["capacity"]
    if field == "setPressure":
        value = c["setPressure"] * rng.uniform(0.9, 1.1)
        return max(value, ASME_SCOPE) if _defaulted(capacity) else value
    if field == "capacity.letter":
        return rng.choice([letter for letter in API526_letters if letter != capacity["letter"]])
    if field == "capacity.area":
        return min(capacity["area"] * rng.uniform(0.8, 1.25), RELIEF_AREA_MAX)
    if field == "capacity.dischargeCoefficient":
        return min(capacity["dischargeCoefficient"] * rng.uniform(0.9, 1.1), 1.0)
    if field == "capacity.overpressure":
        drawn = rng.uniform(0.05, 0.3)
        return rng.choice([None, drawn]) if c["setPressure"] >= ASME_SCOPE else drawn
    area = _relief_area(capacity) * rng.uniform(0.8, 1.25)  # a whole capacity, of any kind
    kind = rng.choice(("api526", "effective", "certified"))
    if c["setPressure"] < ASME_SCOPE:  # below the scope only a certified overpressure is cited
        kind = "certified"
    if kind == "api526":
        return {"kind": kind, "letter": rng.choice(API526_letters)}
    if kind == "effective":
        return {"kind": kind, "area": min(area, RELIEF_AREA_MAX)}
    return {
        "kind": kind,
        "area": min(area, RELIEF_AREA_MAX),
        "dischargeCoefficient": rng.uniform(0.6, 0.9),
        "overpressure": rng.uniform(0.05, 0.3),
    }


GRAVITY = 9.80665
"""m/s², standard gravity (the solver's g)."""
COEFFICIENT_C = {"Cv": 1.76758281804e8, "Kv": 1.32248132708e8}
"""c × Cv² and c × Kv², s²/m⁵, for the loss c·Q|Q| (equipment-pressure-drop.md §3.1, fluids'
Cv_to_K and Kv_to_K): used only to draw another datasheet's rating near the base one."""
RATING_MAX = {"pressureLoss": 1.0e8, "flow": 100.0, "density": 3.0e4, "value": 1.0e7}
"""Upper bounds of the rating's values (equipment-pressure-drop.md §2.1)."""
ORIFICE_BORE_MAX = 10.0
"""m: the upper bound of an orifice plate's bore (orifice-plate.md §2.1)."""
RELIEF_AREA_MAX = 3.141592653589793 * 10.0**2 / 4
"""m²: the upper bound of a relief valve's orifice area (pressure-relief-valve.md §2.1)."""


def _rating(rng: random.Random, rating: dict[str, Any]) -> dict[str, Any]:
    """Another datasheet's whole rating, of any kind, whose c is 0.8-1.25 times the base's."""
    if rating["kind"] == "point":
        c = rating["pressureLoss"] / (rating["density"] * GRAVITY * rating["flow"] ** 2)
    else:
        c = COEFFICIENT_C[rating["kind"]] / rating["value"] ** 2
    c *= rng.uniform(0.8, 1.25)
    kind = rng.choice(("point", "Cv", "Kv"))
    if kind != "point":
        return {"kind": kind, "value": min((COEFFICIENT_C[kind] / c) ** 0.5, RATING_MAX["value"])}
    density = rng.uniform(800.0, 1200.0)
    flow = min((rng.uniform(1.0e4, 1.0e5) / (density * GRAVITY * c)) ** 0.5, RATING_MAX["flow"])
    loss = density * GRAVITY * c * flow**2
    return {"kind": "point", "pressureLoss": loss, "flow": flow, "density": density}


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
        fields = sorted(FIELDS[_kind(c)])
        if c["type"] == "equipment":  # never the whole rating and a part of it; parts of its kind
            parts = [f"rating.{value}" for value in RATING_VALUES[c["rating"]["kind"]]]
            fields = rng.choice([["rating"], parts])
        if c["type"] == "relief_valve":  # likewise its capacity, and its set and status
            parts = [f"capacity.{value}" for value in CAPACITY_VALUES[c["capacity"]["kind"]]]
            fields = ["setPressure", "status", *rng.choice([["capacity"], parts])]
        for field in fields:
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
        if not _clashes(_key(extra), keys):  # one override per value (Scenario's rule)
            keys.add(_key(extra))
            overrides.append(extra)
    rng.shuffle(overrides)
    return overrides


def _key(override: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("kind", "componentId", "connectionId", "pipeIndex", "field")
    return tuple(override.get(k) for k in keys)


def _clashes(key: tuple[Any, ...], keys: set[tuple[Any, ...]]) -> bool:
    """Whether an override with this key would set a value one of ``keys`` sets, or a value and
    a part of it (a rating and rating.value): Scenario's rule, whether or not either applies."""
    *target, field = key
    for *other, other_field in keys:
        if other == target and (
            field == other_field
            or field.startswith(f"{other_field}.")
            or other_field.startswith(f"{field}.")
        ):
            return True
    return False


def _ignored(rng: random.Random, project: dict[str, Any], n: int) -> dict[str, Any]:
    """An orphaned or not-applicable override (a value it never applies); ``n`` makes a missing
    component's id distinct. On an equipment item, a value of the other rating kind."""
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
    if c["type"] == "equipment":  # a value its rating's kind does not hold (the holder rule)
        held = RATING_VALUES[c["rating"]["kind"]]
        other = sorted({v for values in RATING_VALUES.values() for v in values} - set(held))
        field = f"rating.{rng.choice(other)}"
    elif c["type"] == "relief_valve":  # a value its capacity's kind does not hold
        held = CAPACITY_VALUES[c["capacity"]["kind"]]
        other = sorted({v for values in CAPACITY_VALUES.values() for v in values} - set(held))
        field = f"capacity.{rng.choice(other)}"
    else:
        field = next(
            f for f in ("status", "liquidLevel", "pressure", "flow") if f not in FIELDS[_kind(c)]
        )
    return {"kind": "component", "componentId": c["id"], "field": field, "value": 1.0}
