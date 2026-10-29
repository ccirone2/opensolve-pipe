"""Scenarios through the public API, tested independently of their implementation (PRD §3.8,
docs/proposals/scenario-manager.md §7.2).

Written from the proposal and the specs alone, by a tester who did not read ``services/``. The
overrides are applied here by an independent JSON patcher (``scenario_patch.by_hand``), never by
``apply_scenario``, so the two implementations check each other.

1. **Metamorphic.** The networks are every reference case and a sample of corpus-like networks:
   generator seeds of the three fuzz profiles, the unit-test data networks and a library-pipe
   ladder. Each network carries seeded scenarios: every kind of allow-list value it has, three
   kinds to a scenario; a mixed one of 1-6 overrides with 0-2 ignored ones, solved with the
   system curves /solve embeds; one of ignored overrides only; and one that restates base values.
   ``POST /api/v1/solve`` with a scenario must equal, value for value (bit for bit), the solve of
   the project edited by hand. Only these may differ:
   - ``computeTime`` and the timestamp;
   - the response's ``scenario`` record (§3.2), checked against the patcher: each override's
     state, the value used, the base value, the unit and the message;
   - the scenario's own text (§5.2-5.3): a first methods section titled "Scenario" (it names the
     scenario, has one item with "(base: " per applied override and one "Not applied (...)" item
     per ignored override), and one first note in the trace of each element an applied override
     targets.

   The restating scenario must equal the base solve itself (§7.2 item 3). Errors must be the
   hand-edited project's errors, with the scenario's id in the message (§3.3). Another test
   checks that each kind of value, overridden, moves some reference case's solution beyond D6.
   Without that check, a value that never reached the solver could pass.
2. **System curves.** ``POST /api/v1/system-curve`` with a scenario must equal the hand-edited
   project's curve, point for point, apart from the record.
3. **Ignored and invalid overrides** (§2.4, §3.3).
   - Orphaned and not-applicable overrides are reported, with a message, and ignored, whatever
     their value.
   - An invalid value is a 400 for that scenario only. Its issues sit at the override and match
     the hand-edited project's validation errors. No submitted value, scenario name or
     description is echoed.
   - A malformed scenario is a 400 for every request on the project.
   - An unknown scenario id is a 404.
   - The checks run in the order scenario, override, pump.
4. **Base invariance** (§4.3). A project without scenarios, with an empty list, or with
   scenarios but no ``scenarioId`` (omitted or null) gives the same response, system curves
   included, with ``scenario`` null and no scenario section.

The allow-list as the design states it (``scenario_patch``) must also be the one the API
publishes in ``x-override-fields``.

5. **Equipment** (docs/proposals/equipment-pressure-drop.md §5.1, §7.3): a dirty strainer (its
   rated pressure drop), another vendor's datasheet as a whole rating of each kind (a point on
   another fluid, a Cv, a Kv), parts of a rating, and parts the base element's kind does not
   hold (not applicable) each solve as the hand-edited project; a rating and a part of it in one
   scenario are rejected; bad rating values are a 400 at the override, never echoed; ratings
   whose coefficient cannot be represented fail as the hand-edited project does (422).
6. **Orifice plates** (docs/proposals/orifice-plate.md §5.1, §7.3): a bore change, an entered
   C, and a C set back to null (ISO 5167-2's) on a base that enters one each solve as the
   hand-edited project and move the solution beyond D6, the result echoing the bore and C used;
   bad values are a 400 at the override, never echoed; a bore the plate's inlet pipe cannot hold
   (β ≥ 1) fails as the hand-edited project does (422 ORIFICE_OUT_OF_RANGE).
7. **Pressure relief valves** (docs/proposals/pressure-relief-valve.md §5, §7.3, decision 18): a
   lower set, a smaller valve (a letter), a gagged valve (locked closed), a kind change (a
   certified capacity on a letter's valve), an opened discharge beside it, a null
   ``capacity.overpressure`` (ASME's default) and a certified valve's coefficient and area each
   solve as the hand-edited project and move the solution beyond D6, the result echoing the set,
   capacity and overpressure used; values the base valve's capacity kind does not hold are not
   applicable; a capacity and a part of it in one scenario are rejected; bad values are a 400 at
   the override, never echoed; a set below ASME's 15 psi on a capacity that takes ASME's
   overpressure fails as the hand-edited project does (422 RELIEF_VALVE_OUT_OF_RANGE).
"""

import functools
import itertools
import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import opensolve_pipe
from opensolve_pipe.main import app
from opensolve_pipe.models.components import (
    CheckValve,
    ControlValve,
    Equipment,
    IsolationValve,
    Orifice,
    Pump,
    RatedPoint,
    ReliefValve,
)
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.models.piping import CUSTOM_MATERIAL_ID, MAX_PIPES, PipeDefinition
from opensolve_pipe.models.project import Project
from tests.differential import networks
from tests.differential.generator import ASSIGNED_FLOW, DEFAULT, FLOW_CONTROL, generate
from tests.reference import element_laws as el
from tests.reference.case_format import case_files
from tests.reference.derivations import G
from tests.reference.scenario_patch import (
    CAPACITY_PARTS,
    COMPONENT_FIELD_NAMES,
    COMPONENT_FIELDS,
    PIPE_FIELDS,
    PROJECT_FIELDS,
    RATING_PARTS,
    HandApplied,
    State,
    by_hand,
    expected_records,
    note_elements,
    read,
    resolve,
    same_json,
    without_scenarios,
)

API_ROOT = Path(__file__).resolve().parents[2]
RELATIVE = 0.005  # D6
FLOW_FLOOR = 1.0e-9  # m³/s
HEAD_FLOOR = 0.01  # m
PLAIN = {"includeSystemCurve": False}
WITH_CURVES = {"includeSystemCurve": True, "systemCurvePoints": 5}
"""Solve options. The mixed scenarios and the base-invariance checks also fill the running pumps'
system curves (5 points each, to keep them quick), so the curves /solve embeds are compared too;
the other solves leave them out."""
CURVE_POINTS = 5
"""Points per /system-curve request (its minimum): the comparison is point for point."""
GROUP = 3
"""Values of different kinds per drawn scenario (module docstring, item 1)."""
SCENARIO_SECTION = "Scenario"
MAX_SCENARIOS = 20
SENTINEL = "SENTINEL-7d1c"
"""Text that must never come back in an error (D10: errors never echo submitted values, and name
a scenario by id only, proposal decision 32)."""
SENTINEL_DIGITS = "1234567"
"""Digits every sentinel number carries."""

# --------------------------------------------------------------------------- the networks

CORPUS_SAMPLE = {
    "fuzz": (DEFAULT, range(0, 3000, 1000)),
    "fuzzfc": (FLOW_CONTROL, range(10_000, 11_000, 333)),
    "fuzzaf": (ASSIGNED_FLOW, range(20_000, 21_000, 333)),
}
"""Corpus-like networks (TSD §10.4): seeds of each profile's corpus range (3 default, 4
flow_control and 4 assigned_flow seeds: the ranges' steps of 1000 and 333), with every third
unit-test data network (5) and a ladder of library pipes, 17 networks in all (the corpus tool,
``tests/differential/scenario_check.py``, covers the whole corpus)."""


def _api_json(project: Project) -> dict[str, Any]:
    data: dict[str, Any] = project.model_dump(mode="json", exclude_unset=True)
    return without_scenarios(data)


def _file_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    return without_scenarios(data.get("project", data))


def _generated(seed: int, profile: str) -> dict[str, Any]:
    return _api_json(generate(seed, profile))


def _ladder() -> dict[str, Any]:
    return _api_json(networks.ladder(7, 1, "crane", True))


def _sources() -> dict[str, Callable[[], dict[str, Any]]]:
    """Each network's loader: a fresh copy of its API JSON on every call."""
    out: dict[str, Callable[[], dict[str, Any]]] = {}
    for path in case_files():
        out[f"ref_{path.stem}"] = functools.partial(_file_json, path)
    for prefix, (profile, seeds) in CORPUS_SAMPLE.items():
        for seed in seeds:
            out[f"{prefix}_{seed}"] = functools.partial(_generated, seed, profile)
    for path in sorted(API_ROOT.glob("tests/unit/data/*/*.json"))[::3]:
        out[f"unit_{path.stem}"] = functools.partial(_file_json, path)
    out["ladder_7_library"] = _ladder
    return out


NETWORKS = _sources()
REFERENCE = [name for name in NETWORKS if name.startswith("ref_")]


def _pump_ids(project: Project) -> list[str]:
    return [c.id for c in project.components if isinstance(c, Pump)]


# --------------------------------------------------------------------------- the API


_addresses = itertools.count(1)


class Api:
    """POST through the app from a client address of its own, changed every 50 requests: the
    rate limit (60 a minute per client) is never reached, and no bucket is shared with the rest
    of the suite."""

    def __init__(self) -> None:
        self._client = self._new()
        self._sent = 0

    @staticmethod
    def _new() -> TestClient:
        n = next(_addresses)
        return TestClient(app, client=(f"10.73.{n // 256 % 256}.{n % 256}", 50000))

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self._sent == 50:
            self._client, self._sent = self._new(), 0
        self._sent += 1
        response: httpx.Response = self._client.post(path, json=body)
        return response

    def solve(
        self, project: dict[str, Any], scenario_id: str | None = None, *, curves: bool = False
    ) -> httpx.Response:
        body: dict[str, Any] = {"project": project, "options": WITH_CURVES if curves else PLAIN}
        if scenario_id is not None:
            body["scenarioId"] = scenario_id
        return self.post("/api/v1/solve", body)

    def curve(
        self, project: dict[str, Any], pump_id: str, scenario_id: str | None = None
    ) -> httpx.Response:
        body: dict[str, Any] = {"project": project, "pumpId": pump_id, "numPoints": CURVE_POINTS}
        if scenario_id is not None:
            body["scenarioId"] = scenario_id
        return self.post("/api/v1/system-curve", body)


# --------------------------------------------------------------------------- drawing scenarios


def _library() -> dict[tuple[str, str], list[dict[str, Any]]]:
    data = json.loads(
        (Path(opensolve_pipe.__file__).parent / "data" / "pipe_materials.json").read_text()
    )
    return {(m["id"], s["id"]): s["sizes"] for m in data["materials"] for s in m["schedules"]}


SIZES = _library()
LIBRARY_SCHEDULES = [
    ("carbon_steel", "40"),
    ("carbon_steel", "80"),
    ("stainless_steel", "40S"),
    ("pvc", "40D1785"),
]
STATUSES: dict[type[Any], tuple[str, ...]] = {
    Pump: ("on", "off"),
    IsolationValve: ("active", "isolated"),
    CheckValve: ("active", "locked_open", "locked_closed"),
    ControlValve: ("active", "failed_open", "failed_closed"),
    ReliefValve: ("active", "locked_closed"),
}


@dataclass(frozen=True)
class Slot:
    """One overridable value of a project: an override without its value."""

    kind: str
    """'<target type>.<field>': 'Pump.speed', 'PipeDefinition.spec', 'Project.fluid', ..."""
    key: tuple[Any, ...]
    """A scenario sets each key once (a fluid and its temperature share one, and an equipment
    item's rating and its parts: a value and a part of it are rejected, proposal decision 9)."""
    target: dict[str, Any]
    field: str
    model: Any

    def override(self, value: Any) -> dict[str, Any]:
        return {**self.target, "field": self.field, "value": value}


def slots(project: Project) -> list[Slot]:
    out = []
    for c in project.components:
        for field in COMPONENT_FIELDS[type(c)]:
            if field == "control.setpoint" and getattr(c, "control", None) is None:
                continue
            if isinstance(c, Equipment) and c.rating.kind not in RATING_PARTS.get(
                field, (c.rating.kind,)
            ):
                continue  # a part the element's rating kind does not hold
            if isinstance(c, ReliefValve) and c.capacity.kind not in CAPACITY_PARTS.get(
                field, (c.capacity.kind,)
            ):
                continue  # a value the valve's capacity kind does not hold
            whole = field.split(".")[0]
            key = ("c", c.id, whole if whole in ("rating", "capacity") else field)
            target: dict[str, Any] = {"kind": "component", "componentId": c.id}
            out.append(Slot(f"{type(c).__name__}.{field}", key, target, field, c))
    for conn in project.connections:
        for i, pipe in enumerate(conn.piping.pipes):
            for field in PIPE_FIELDS:
                target = {"kind": "pipe", "connectionId": conn.id, "pipeIndex": i}
                kind = f"PipeDefinition.{field}"
                out.append(Slot(kind, ("p", conn.id, i, field), target, field, pipe))
    for field in PROJECT_FIELDS:
        if field == "fluid.temperature" and not isinstance(project.fluid, BuiltinFluid):
            continue
        out.append(Slot(f"Project.{field}", ("fluid",), {"kind": "project"}, field, project))
    return out


def _inner_diameter(pipe: PipeDefinition) -> float:
    if pipe.inner_diameter is not None:
        return pipe.inner_diameter
    assert pipe.schedule is not None
    assert pipe.nominal_size is not None
    nominal = pipe.nominal_size  # as written (0.0762), not always the data's float
    size = min(
        SIZES[(pipe.material_id, pipe.schedule)], key=lambda s: abs(s["nominalSize"] - nominal)
    )
    assert abs(size["nominalSize"] - nominal) <= 1.0e-9 * nominal, pipe
    diameter: float = size["innerDiameter"]
    return diameter


def _draw_spec(rng: random.Random, pipe: PipeDefinition) -> dict[str, Any]:
    """Another pipe of about the same bore: a library pipe (sometimes with a roughness or bore
    override) or a custom one."""
    diameter = _inner_diameter(pipe)
    if rng.random() < 0.5:
        own = (pipe.material_id, pipe.schedule or "")
        material, schedule = (
            own if own in SIZES and rng.random() < 0.5 else rng.choice(LIBRARY_SCHEDULES)
        )
        wanted = diameter * rng.choice([0.8, 1.0, 1.25])
        size = min(SIZES[(material, schedule)], key=lambda s: abs(s["innerDiameter"] - wanted))
        spec: dict[str, Any] = {
            "materialId": material,
            "schedule": schedule,
            "nominalSize": size["nominalSize"],
        }
        if rng.random() < 0.2:
            spec["roughness"] = rng.uniform(1.0e-5, 1.0e-4)
        if rng.random() < 0.1:
            spec["innerDiameter"] = size["innerDiameter"] * 0.98
        return spec
    roughness = pipe.roughness if pipe.roughness else rng.uniform(1.0e-5, 1.0e-4)
    return {
        "materialId": CUSTOM_MATERIAL_ID,
        "innerDiameter": min(10.0, diameter * rng.uniform(0.8, 1.25)),
        "roughness": min(0.1, roughness * rng.uniform(0.5, 2.0)),
    }


def _draw_fluid(rng: random.Random) -> dict[str, Any]:
    choice = rng.randrange(3)
    if choice == 0:
        fluid: dict[str, Any] = {
            "kind": "custom",
            "name": "Scenario liquid",
            "density": rng.uniform(950.0, 1100.0),
            "dynamicViscosity": rng.uniform(0.6e-3, 2.5e-3),
        }
        if rng.random() < 0.5:
            fluid["vaporPressure"] = rng.uniform(1.5e3, 6.0e3)
        return fluid
    if choice == 1:
        return {"kind": "builtin", "fluidId": "water", "temperature": rng.uniform(280.0, 340.0)}
    return {
        "kind": "builtin",
        "fluidId": rng.choice(["ethylene_glycol", "propylene_glycol"]),
        "temperature": rng.uniform(285.0, 320.0),
        "concentration": rng.uniform(0.2, 0.4),
    }


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


RATING_BOUNDS = {
    "pressureLoss": 1.0e8,
    "flow": 100.0,
    "density": 3.0e4,
    "value": 1.0e7,
}
"""Upper bounds of the rating values (proposal §2.1); each is > 0."""


def _factor(rng: random.Random) -> float:
    """A factor that moves a rating value well beyond D6 either way."""
    return rng.uniform(0.4, 0.8) if rng.random() < 0.5 else rng.uniform(1.25, 2.5)


def _factor_small(rng: random.Random) -> float:
    """A factor that moves a discharge coefficient by 10-25 % either way."""
    return rng.uniform(0.75, 0.9) if rng.random() < 0.5 else rng.uniform(1.1, 1.25)


def _draw_rating(rng: random.Random, rating: Any) -> dict[str, Any]:
    """Another datasheet: a rated point (on a fluid of 800-1200 kg/m³), a Cv or a Kv, whose
    coefficient c is the base rating's times a drawn factor (c from the definitions,
    ``element_laws``: c = ΔP_ref/(ρ_ref g Q_ref²))."""
    c = el.equipment_coefficient(rating) * _factor(rng)
    _, q_ref, _ = el.rated_reference(rating)
    kind = rng.choice(["point", "Cv", "Kv"])
    if kind == "point":
        density = rng.uniform(800.0, 1200.0)
        flow = _clip(q_ref * rng.uniform(0.5, 2.0), 1.0e-6, 100.0)
        loss = _clip(c * density * G * flow * flow, 1.0, 1.0e8)
        return {"kind": "point", "pressureLoss": loss, "flow": flow, "density": density}
    if kind == "Cv":
        dp, q_unit = el.CV_PRESSURE_DROP, el.CV_FLOW
    else:
        dp, q_unit = el.KV_PRESSURE_DROP, el.KV_FLOW
    value = (dp / (el.REFERENCE_WATER_DENSITY * G * c)) ** 0.5 / q_unit
    return {"kind": kind, "value": _clip(value, 1.0e-3, 1.0e7)}


RELIEF_LETTERS = list(el.API526_AREAS)
RELIEF_AREA_MAX = 78.5
"""m²: just inside a relief area's bound, π × 10²/4 (proposal §2.1)."""


def _draw_capacity(rng: random.Random, valve: ReliefValve) -> dict[str, Any]:
    """Another relief valve's capacity, of any kind (decision 18): another API 526 letter, an
    effective area, or a certified area, coefficient and (half the time) overpressure, the
    areas the base's times a factor that moves the flow beyond D6."""
    values = el.relief_capacity(valve.capacity, valve.set_pressure)
    kind = rng.choice(["api526", "effective", "certified"])
    area = _clip(values.area * _factor(rng), 1.0e-6, RELIEF_AREA_MAX)
    if kind == "api526":
        own = getattr(valve.capacity, "letter", None)
        return {"kind": "api526", "letter": rng.choice([x for x in RELIEF_LETTERS if x != own])}
    if kind == "effective":
        return {"kind": "effective", "area": area}
    out: dict[str, Any] = {
        "kind": "certified",
        "area": area,
        "dischargeCoefficient": rng.uniform(0.6, 0.9),
    }
    if rng.random() < 0.5:
        out["overpressure"] = rng.uniform(0.05, 0.3)
    return out


def _draw_relief(rng: random.Random, valve: ReliefValve, field: str) -> Any:
    """A relief valve's value (decision 18): the set times 0.75-0.9 or 1.1-1.25 (every case's set
    stays above ASME's 15 psi), a whole capacity, another letter, an area, coefficient or
    overpressure moved beyond D6 (an overpressure set back to ASME's default, null, a third of
    the time when the base enters one)."""
    if field == "setPressure":
        return valve.set_pressure * _factor_small(rng)
    if field == "capacity":
        return _draw_capacity(rng, valve)
    capacity: Any = valve.capacity
    if field == "capacity.letter":
        return rng.choice([x for x in RELIEF_LETTERS if x != capacity.letter])
    if field == "capacity.area":
        return _clip(capacity.area * _factor(rng), 1.0e-9 * capacity.area, RELIEF_AREA_MAX)
    if field == "capacity.dischargeCoefficient":
        return min(1.0, capacity.discharge_coefficient * _factor_small(rng))
    assert field == "capacity.overpressure"
    if capacity.overpressure is None:
        return rng.uniform(0.05, 0.3)
    if rng.random() < 1.0 / 3.0:
        return None
    return min(1.0, capacity.overpressure * _factor(rng))


def draw(rng: random.Random, slot: Slot) -> Any:
    """A value of the slot's field, within its bounds, other than the base value."""
    m, field = slot.model, slot.field
    if isinstance(m, ReliefValve) and field != "status":
        return _draw_relief(rng, m, field)
    if field == "status":
        return rng.choice([s for s in STATUSES[type(m)] if s != m.status])
    if field == "speed":
        low = m.control.min_speed if m.control is not None else 0.6
        return rng.uniform(low + 0.25 * (1.0 - low), 1.0)
    if field == "control.setpoint":
        return _clip(m.control.setpoint * rng.uniform(0.7, 1.3), 1.0e-6, 100.0)
    if field == "setpoint":
        if m.valve_type == "fcv":
            return _clip(m.setpoint * rng.uniform(0.7, 1.3), 0.0, 100.0)
        return _clip(m.setpoint + rng.uniform(-40.0e3, 40.0e3), -1.0e5, 1.0e8)
    if field == "resistance":
        return rng.choice(
            [
                None,
                {"kind": "K", "value": rng.uniform(0.1, 20.0)},
                {"kind": "Cv", "value": rng.uniform(20.0, 2000.0)},
                {"kind": "Kv", "value": rng.uniform(20.0, 2000.0)},
            ]
        )
    if field == "liquidLevel":
        return _clip(m.liquid_level + rng.uniform(-1.0, 3.0), 0.0, 1.0e3)
    if field == "surfacePressure":
        return _clip(m.surface_pressure + rng.uniform(-20.0e3, 60.0e3), -1.0e5, 1.0e8)
    if field == "pressure":
        return _clip(m.pressure + rng.uniform(-30.0e3, 60.0e3), -1.0e5, 1.0e8)
    if field == "rating":
        return _draw_rating(rng, m.rating)
    if field.startswith("rating."):
        part = field.split(".")[1]
        value = m.rating.model_dump(by_alias=True)[part]
        return _clip(value * _factor(rng), 1.0e-9 * value, RATING_BOUNDS[part])
    if field == "boreDiameter":
        # A smaller plate: the base's β < 1 holds, and the loss moves beyond D6.
        return m.bore_diameter * rng.uniform(0.7, 0.92)
    if field == "dischargeCoefficient":
        # ISO's C is about 0.6: an entered C at least 8 % from it, or back to ISO's (null); at
        # most 0.95, so C_e r_max ≤ 1 at corner or flange taps (decision 17 (c), r ≤ 1.0225).
        if m.discharge_coefficient is None:
            return rng.uniform(0.45, 0.55) if rng.random() < 0.5 else rng.uniform(0.66, 0.8)
        if rng.random() < 0.4:
            return None
        return min(0.95, m.discharge_coefficient * _factor_small(rng))
    if field == "flow":
        return 0.0 if rng.random() < 0.15 else _clip(m.flow * rng.uniform(0.6, 1.4), -100, 100)
    if field == "length":
        return _clip(m.length * rng.uniform(0.5, 2.0), 1.0e-3, 1.0e6)
    if field == "spec":
        return _draw_spec(rng, m)
    if field == "fluid":
        return _draw_fluid(rng)
    assert field == "fluid.temperature"
    fluid = m.fluid
    if fluid.fluid_id == "water":
        return _clip(fluid.temperature + rng.uniform(-15.0, 15.0), 275.0, 360.0)
    return fluid.temperature + rng.uniform(-3.0, 8.0)


def _garbage(rng: random.Random) -> Any:
    """A value for an ignored override, mostly one its field would reject: an ignored override
    is never validated, so its value cannot matter."""
    return rng.choice([-1.0e9, f"not a value {SENTINEL}", {"nested": [1, 2]}, None, True])


def ignored(rng: random.Random, project: Project, n: int, keys: set[Any]) -> list[dict[str, Any]]:
    """Up to n overrides the scenario must keep and ignore, mostly with values their fields would
    reject: orphaned (no such component, connection or pipe) or not applicable (no such value
    on the target). ``keys`` are the values the scenario already sets."""
    candidates = [
        {
            "kind": "component",
            "componentId": "gone_P9",
            "field": rng.choice(COMPONENT_FIELD_NAMES),
            "value": _garbage(rng),
        },
        {
            "kind": "pipe",
            "connectionId": "gone_L9",
            "pipeIndex": rng.randrange(3),
            "field": rng.choice(list(PIPE_FIELDS)),
            "value": _garbage(rng),
        },
    ]
    conn = rng.choice(project.connections)
    n_pipes = len(conn.piping.pipes)
    if n_pipes < MAX_PIPES:
        index = rng.randint(n_pipes, min(MAX_PIPES - 1, n_pipes + 2))
        candidates.append(
            {
                "kind": "pipe",
                "connectionId": conn.id,
                "pipeIndex": index,
                "field": rng.choice(list(PIPE_FIELDS)),
                "value": _garbage(rng),
            }
        )
    component = rng.choice(project.components)
    lacking = [f for f in COMPONENT_FIELD_NAMES if f not in COMPONENT_FIELDS[type(component)]]
    candidates.append(
        {
            "kind": "component",
            "componentId": component.id,
            "field": rng.choice(lacking),
            "value": _garbage(rng),
        }
    )
    fixed = [c for c in project.components if isinstance(c, Pump) and c.control is None]
    if fixed:
        candidates.append(
            {
                "kind": "component",
                "componentId": rng.choice(fixed).id,
                "field": "control.setpoint",
                "value": _garbage(rng),
            }
        )
    if isinstance(project.fluid, CustomFluid) and ("fluid",) not in keys:
        candidates.append({"kind": "project", "field": "fluid.temperature", "value": _garbage(rng)})
    rated = [
        c
        for c in project.components
        if isinstance(c, Equipment) and ("c", c.id, "rating") not in keys
    ]
    if rated:
        # A part the element's rating kind does not hold (never beside its whole rating, which
        # would be a value and a part of it).
        e = rng.choice(rated)
        other = [f for f, kinds in RATING_PARTS.items() if e.rating.kind not in kinds]
        candidates.append(
            {
                "kind": "component",
                "componentId": e.id,
                "field": rng.choice(other),
                "value": _garbage(rng),
            }
        )
    reliefs = [
        c
        for c in project.components
        if isinstance(c, ReliefValve) and ("c", c.id, "capacity") not in keys
    ]
    if reliefs:
        # A capacity value the valve's kind does not hold (never beside its whole capacity).
        rv = rng.choice(reliefs)
        other = [f for f, kinds in CAPACITY_PARTS.items() if rv.capacity.kind not in kinds]
        candidates.append(
            {
                "kind": "component",
                "componentId": rv.id,
                "field": rng.choice(other),
                "value": _garbage(rng),
            }
        )
    return rng.sample(candidates, min(n, len(candidates)))


@dataclass(frozen=True)
class Drawn:
    scenarios: list[dict[str, Any]]
    mixing: str
    """The id of the mixed scenario (solved with system curves)."""
    restating: str
    """The id of the scenario that restates base values."""
    ignoring: str
    """The id of the scenario of ignored overrides only."""


def _scenario(
    sid: str, label: str, overrides: list[dict[str, Any]], description: str | None = None
) -> dict[str, Any]:
    scenario: dict[str, Any] = {"id": sid, "name": f"{label} ({sid})", "overrides": overrides}
    if description is not None:
        scenario["description"] = description
    return scenario


def scenarios_for(name: str, project: Project) -> Drawn:
    """The seeded scenarios of a network (module docstring, item 1): every kind of value it has,
    GROUP kinds to a scenario, then the mixed, ignoring and restating scenarios."""
    rng = random.Random(f"scenarios:{name}")
    every = slots(project)
    by_kind: dict[str, list[Slot]] = defaultdict(list)
    for slot in every:
        by_kind[slot.kind].append(slot)
    groups: list[list[Slot]] = []
    for kind in rng.sample(sorted(by_kind), len(by_kind)):
        slot = rng.choice(by_kind[kind])
        room = (g for g in groups if len(g) < GROUP and all(s.key != slot.key for s in g))
        group = next(room, None)
        if group is None:
            groups.append([slot])
        else:
            group.append(slot)
    out: list[dict[str, Any]] = []
    for group in groups:
        label = " + ".join(slot.kind for slot in group)
        overrides = [slot.override(draw(rng, slot)) for slot in group]
        out.append(_scenario(f"S{len(out) + 1}", label, overrides))

    wanted = rng.randint(1, 6)
    keys: set[Any] = set()
    mixed: list[dict[str, Any]] = []
    for slot in rng.sample(every, len(every)):
        if len(mixed) == wanted:
            break
        if slot.key not in keys:
            keys.add(slot.key)
            mixed.append(slot.override(draw(rng, slot)))
    mixed += ignored(rng, project, rng.randint(0, 2), keys)
    rng.shuffle(mixed)
    description = "A seeded draw of values from the allow-list."
    mixing = f"S{len(out) + 1}"
    out.append(_scenario(mixing, "Mixed", mixed, description))

    ignoring = f"S{len(out) + 1}"
    out.append(_scenario(ignoring, "Ignored", ignored(rng, project, 6, set())))

    restate: list[dict[str, Any]] = []
    keys = set()
    for slot in rng.sample(every, len(every)):
        if len(restate) == 4:
            break
        if slot.key not in keys:
            keys.add(slot.key)
            _, where, _ = resolve(project, slot.override(None))
            assert where is not None
            restate.append(slot.override(read(project, where)))
    restating = f"S{len(out) + 1}"
    out.append(_scenario(restating, "Base values restated", restate))
    assert len(out) <= MAX_SCENARIOS
    return Drawn(out, mixing, restating, ignoring)


# --------------------------------------------------------------------------- comparing


def comparable(body: dict[str, Any]) -> dict[str, Any]:
    """A response without what may differ between two solves of one project: computeTime, the
    timestamp, and the scenario record (checked on its own)."""
    out = {k: v for k, v in body.items() if k not in ("computeTime", "scenario")}
    if "solvedState" in out:
        out["solvedState"] = {k: v for k, v in out["solvedState"].items() if k != "timestamp"}
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


def _message_problems(
    where: str, message: str, override: dict[str, Any], state: str, base: Project
) -> list[str]:
    """An ignored override's message says why (§3.3): an orphaned one names its missing target,
    and a pipe beyond its connection's pipes is numbered from 1."""
    if not message:
        return [f"{where}: {state} without a message"]
    wanted: list[str] = []
    if state == "orphaned":
        wanted.append(override.get("componentId") or override["connectionId"])
        connections = {c.id for c in base.connections}
        if override["kind"] == "pipe" and override["connectionId"] in connections:
            wanted.append(f"pipe {override['pipeIndex'] + 1}")
    elif override["field"] == "control.setpoint":
        wanted.append(override["componentId"])
    return [f"{where}: message {message!r} does not name {w!r}" for w in wanted if w not in message]


def record_problems(
    record: dict[str, Any] | None, scenario: dict[str, Any], hand: HandApplied
) -> list[str]:
    """The response's scenario record against the patcher's (proposal §3.2)."""
    sid = scenario["id"]
    if record is None:
        return [f"{sid}: the response's scenario is null"]
    problems = [
        f"{sid}: record {key} {record.get(key)!r}, expected {want!r}"
        for key, want in (
            ("id", sid),
            ("name", scenario["name"]),
            ("description", scenario.get("description")),
        )
        if record.get(key) != want
    ]
    expected = expected_records(hand)
    if len(record["overrides"]) != len(expected):
        return [*problems, f"{sid}: {len(record['overrides'])} override records"]
    for got, want in zip(record["overrides"], expected, strict=True):
        at = f"{sid} override {want['index']}"
        if got["index"] != want["index"] or not same_json(got["override"], want["override"]):
            problems.append(f"{at}: recorded as {got['index']} {got['override']}")
        if got["state"] != want["state"]:
            problems.append(f"{at}: state {got['state']}, expected {want['state']}")
        elif want["state"] == "applied":
            for key in ("value", "baseValue"):
                if not same_json(got[key], want[key]):
                    problems.append(f"{at}: {key} {got[key]!r}, expected {want[key]!r}")
            if want["unit"] is not None and got["unit"] != want["unit"]:
                problems.append(f"{at}: unit {got['unit']!r}, expected {want['unit']!r}")
            if got["message"] != "":
                problems.append(f"{at}: applied, with the message {got['message']!r}")
        else:
            if got["value"] is not None or got["baseValue"] is not None:
                problems.append(f"{at}: {got['state']} with a value or base value")
            override, state = want["override"], got["state"]
            problems += _message_problems(at, got["message"], override, state, hand.base)
    return problems


def _section_problems(
    section: dict[str, Any], scenario: dict[str, Any], hand: HandApplied
) -> list[str]:
    """The methods summary's Scenario section (§5.3)."""
    sid, items = scenario["id"], section["items"]
    problems = []
    if not items or f"(id {sid})" not in items[0] or scenario["name"] not in items[0]:
        problems.append(f"{sid}: the Scenario section does not open with the scenario: {items}")
    applied = sum("(base: " in item for item in items)
    if applied != len(hand.applied()):
        problems.append(f"{sid}: {applied} applied items, expected {len(hand.applied())}")
    labels: tuple[tuple[State, str], ...] = (
        ("orphaned", "Not applied (orphaned)"),
        ("not_applicable", "Not applied (not applicable)"),
    )
    for state, label in labels:
        n = sum(item.startswith(label) for item in items)
        if n != hand.count(state):
            problems.append(f"{sid}: {n} items '{label}', expected {hand.count(state)}")
    description = scenario.get("description")
    if description and not any(description in item for item in items):
        problems.append(f"{sid}: the Scenario section does not give the description")
    return problems


def without_scenario_text(
    state: dict[str, Any], scenario: dict[str, Any], hand: HandApplied
) -> tuple[dict[str, Any], list[str]]:
    """The solved state without the scenario's own text (§5.2-5.3), and what is wrong with that
    text: the first methods section, and the first note of each element an applied override
    targets (one note per element, giving each of its overrides with its base value)."""
    sid = scenario["id"]
    state = json.loads(json.dumps(state))
    sections = state["trace"]["methods"]["sections"]
    if not sections or sections[0]["title"] != SCENARIO_SECTION:
        return state, [f"{sid}: no first methods section titled {SCENARIO_SECTION!r}"]
    problems = _section_problems(sections.pop(0), scenario, hand)
    for element, n in note_elements(hand).items():
        trace = state["trace"]["elements"].get(element)
        if trace is None:
            continue
        if not trace["notes"]:
            problems.append(f"{sid}: no scenario note on {element}")
            continue
        note = trace["notes"].pop(0)
        if not note.startswith("Scenario ") or f"(id {sid})" not in note:
            problems.append(f"{sid}: the first note of {element} is not the scenario's: {note!r}")
        elif scenario["name"] not in note or note.count("(base: ") != n:
            problems.append(f"{sid}: {element}'s note does not give its {n} override(s): {note!r}")
    return state, problems


def _validation_problems(
    sid: str, s_index: int, hand: HandApplied, got: dict[str, Any], want: dict[str, Any]
) -> list[str]:
    """A scenario's invalid values (§4.1 step 4): one issue per error, at the override
    (``body.project.scenarios.{s}.overrides.{j}``, then ``.value...`` or the object-level
    message), with the hand-edited project's error codes and messages, and the override's target
    in componentIds or connectionIds."""
    problems = []
    issues = got["issues"]
    if got["message"] != f"Invalid input: {len(issues)} problem(s).":
        problems.append(f"{sid}: message {got['message']!r}")
    prefix = f"body.project.scenarios.{s_index}.overrides."
    applied = {o.index: o.override for o in hand.applied()}
    for issue in issues:
        location = issue["message"].split(": ", 1)[0]
        head, _, rest = location.removeprefix(prefix).partition(".")
        if not location.startswith(prefix) or not head.isdigit() or int(head) not in applied:
            problems.append(f"{sid}: issue not at an applied override: {issue['message']!r}")
            continue
        if rest and not rest.startswith("value"):
            problems.append(f"{sid}: issue below the override but not its value: {location!r}")
        override = applied[int(head)]
        if override["kind"] == "component" and override["componentId"] not in issue["componentIds"]:
            problems.append(f"{sid}: {issue['message']!r} does not name its component")
        if override["kind"] == "pipe" and override["connectionId"] not in issue["connectionIds"]:
            problems.append(f"{sid}: {issue['message']!r} does not name its connection")

    def errors(body: dict[str, Any]) -> Counter[tuple[str, str]]:
        return Counter((i["code"], i["message"].split(": ", 1)[1]) for i in body["issues"])

    if errors(got) != errors(want):
        problems.append(f"{sid}: issues {errors(got)}, the hand-edited project's {errors(want)}")
    return problems


def error_problems(
    sid: str, s_index: int, hand: HandApplied, got: httpx.Response, want: httpx.Response
) -> list[str]:
    """A scenario's error against the hand-edited project's (§3.3): the same status, code and
    issues; a topology error's message says which scenario cannot be solved, and a fluid error's
    message is the fluid's, after the scenario's id."""
    g, w = got.json(), want.json()
    if got.status_code != want.status_code or g.get("error") != w.get("error"):
        return [
            f"{sid}: {got.status_code} {g.get('error')} {g.get('message')!r}; the hand-edited "
            f"project gives {want.status_code} {w.get('error')} {w.get('message')!r}"
        ]
    if w["error"] == "TOPOLOGY_ERROR":
        message = f"Scenario {sid} cannot be solved: {len(w['issues'])} topology issue(s)."
        problems = [] if g["message"] == message else [f"{sid}: message {g['message']!r}"]
        return problems + differences(g["issues"], w["issues"], f"{sid} issues")
    if w["error"] == "FLUID_ERROR":
        message = f"Scenario {sid}: {w['message']}"
        return [] if g["message"] == message else [f"{sid}: {g['message']!r}, not {message!r}"]
    if w["error"] == "VALIDATION_ERROR":
        return _validation_problems(sid, s_index, hand, g, w)
    if w["error"] == "NOT_FOUND":
        return [] if g["message"] == w["message"] else [f"{sid}: {g['message']!r}"]
    return [f"{sid}: unexpected error {w['error']} for the hand-edited project: {w['message']}"]


def solve_problems(
    scenario: dict[str, Any],
    s_index: int,
    hand: HandApplied,
    got: httpx.Response,
    want: httpx.Response,
) -> list[str]:
    """A scenario's /solve response against the hand-edited project's (module docstring)."""
    sid = scenario["id"]
    if want.status_code != 200:
        return error_problems(sid, s_index, hand, got, want)
    if got.status_code != 200:
        return [f"{sid}: {got.status_code} {got.text[:400]}; the hand-edited project solves"]
    body = got.json()
    problems = record_problems(body["scenario"], scenario, hand)
    state, text_problems = without_scenario_text(body["solvedState"], scenario, hand)
    problems += text_problems
    stripped = comparable({**body, "solvedState": state})
    return problems + differences(stripped, comparable(want.json()), sid)


def curve_problems(
    scenario: dict[str, Any],
    s_index: int,
    hand: HandApplied,
    got: httpx.Response,
    want: httpx.Response,
) -> list[str]:
    """A scenario's /system-curve response against the hand-edited project's."""
    sid = scenario["id"]
    if want.status_code != 200:
        return error_problems(sid, s_index, hand, got, want)
    if got.status_code != 200:
        return [f"{sid}: {got.status_code} {got.text[:400]}; the hand-edited project's curve"]
    body = got.json()
    problems = record_problems(body["scenario"], scenario, hand)
    return problems + differences(comparable(body), comparable(want.json()), sid)


def _setup(name: str) -> tuple[dict[str, Any], Project, Drawn, dict[str, Any]]:
    base = NETWORKS[name]()
    project = Project.model_validate(base)
    drawn = scenarios_for(name, project)
    return base, project, drawn, {**base, "scenarios": drawn.scenarios}


# --------------------------------------------------------------------------- 1. metamorphic


@pytest.mark.parametrize("name", list(NETWORKS))
def test_a_scenario_solves_as_the_project_edited_by_hand(name: str) -> None:
    """Every drawn scenario of the network solves as its hand-edited project, apart from the
    scenario's record and text; the restating scenario solves as the base project itself."""
    base, _, drawn, project = _setup(name)
    api = Api()
    base_response = api.solve(base)
    assert base_response.status_code == 200, base_response.text
    problems = []
    for s_index, scenario in enumerate(drawn.scenarios):
        hand = by_hand(project, scenario)
        curves = scenario["id"] == drawn.mixing
        got = api.solve(project, scenario["id"], curves=curves)
        if scenario["id"] == drawn.ignoring:
            assert hand.project == base, "an ignored override was applied by the patcher"
        same_as_base = scenario["id"] in (drawn.ignoring, drawn.restating)
        want = base_response if same_as_base else api.solve(hand.project, curves=curves)
        problems += solve_problems(scenario, s_index, hand, got, want)
    assert not problems, "\n".join(problems)


def _moved(base: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether a solution differs from the base's beyond D6 anywhere (flows, EGL, pressures,
    fluid properties, pump statuses and speeds, valve states)."""
    rho = base["fluid"]["density"]

    def beyond(a: float, b: float, floor: float) -> bool:
        return abs(a - b) > max(RELATIVE * abs(b), floor)

    for key, link in base["linkResults"].items():
        if key not in other["linkResults"]:
            return True
        if beyond(other["linkResults"][key]["flow"], link["flow"], FLOW_FLOOR):
            return True
    for key, node in base["nodeResults"].items():
        mine = other["nodeResults"].get(key)
        if mine is None or beyond(mine["egl"], node["egl"], HEAD_FLOOR):
            return True
        if beyond(mine["pressure"], node["pressure"], rho * G * HEAD_FLOOR):
            return True
    if base["fluid"] != other["fluid"]:
        return True
    pumps = {k: (p["status"], p["speed"]) for k, p in base["pumpResults"].items()}
    valves = {k: v["state"] for k, v in base["valveResults"].items()}
    return pumps != {k: (p["status"], p["speed"]) for k, p in other["pumpResults"].items()} or (
        valves != {k: v["state"] for k, v in other["valveResults"].items()}
    )


ALL_KINDS = sorted(
    [f"{cls.__name__}.{field}" for cls, fields in COMPONENT_FIELDS.items() for field in fields]
    + [f"PipeDefinition.{field}" for field in PIPE_FIELDS]
    + [f"Project.{field}" for field in PROJECT_FIELDS]
)


def test_every_overridable_value_moves_some_solution() -> None:
    """Each allow-list value, overridden in a reference case, changes that case's converged
    solution beyond D6, and the scenario still solves as the hand-edited project: the
    metamorphic test compares solutions the overrides really changed."""
    api = Api()
    rng = random.Random("every value")
    pending = set(ALL_KINDS)
    for name in REFERENCE:
        base = NETWORKS[name]()
        here = [s for s in slots(Project.model_validate(base)) if s.kind in pending]
        if not here:
            continue
        chosen = {s.kind: s for s in reversed(here)}  # the first slot of each kind
        scenarios = [
            _scenario(f"S{i + 1}", kind, [slot.override(draw(rng, slot))])
            for i, (kind, slot) in enumerate(sorted(chosen.items()))
        ]
        project = {**base, "scenarios": scenarios}
        base_state = api.solve(base).json()["solvedState"]
        for s_index, (scenario, kind) in enumerate(zip(scenarios, sorted(chosen), strict=True)):
            got = api.solve(project, scenario["id"])
            if got.status_code != 200 or not got.json()["success"]:
                continue
            if not _moved(base_state, got.json()["solvedState"]):
                continue
            hand = by_hand(project, scenario)
            problems = solve_problems(scenario, s_index, hand, got, api.solve(hand.project))
            assert not problems, f"{name}: " + "\n".join(problems)
            pending.discard(kind)
        if not pending:
            break
    assert not pending, f"no reference case where these overrides move the solution: {pending}"


# --------------------------------------------------------------------------- 2. system curves

PUMP_NETWORKS = [name for name in NETWORKS if _pump_ids(Project.model_validate(NETWORKS[name]()))]


@pytest.mark.parametrize("name", PUMP_NETWORKS)
def test_a_scenario_system_curve_is_the_hand_edited_projects(name: str) -> None:
    """The system curve of a pump in a scenario is that of the hand-edited project, point for
    point (the mixed scenario, and the first other that changes a pump or the fluid); without
    scenarioId, a project with scenarios has the curve of the project without them."""
    base, plain, drawn, project = _setup(name)
    rng = random.Random(f"system curve:{name}")
    pumps = _pump_ids(plain)
    api = Api()
    mixed = next(i for i, s in enumerate(drawn.scenarios) if s["id"] == drawn.mixing)
    pumped = [
        i
        for i, s in enumerate(drawn.scenarios)
        if s["id"] != drawn.mixing and ("Pump." in s["name"] or "Project." in s["name"])
    ]
    chosen = [(i, drawn.scenarios[i]) for i in [mixed, *pumped[:1]]]
    problems = []
    for s_index, scenario in chosen:
        pump_id = rng.choice(pumps)
        hand = by_hand(project, scenario)
        got = api.curve(project, pump_id, scenario["id"])
        problems += curve_problems(scenario, s_index, hand, got, api.curve(hand.project, pump_id))

    pump_id = rng.choice(pumps)
    plain_curve, with_scenarios = api.curve(base, pump_id), api.curve(project, pump_id)
    assert plain_curve.status_code == with_scenarios.status_code == 200, with_scenarios.text
    assert plain_curve.json()["scenario"] is None
    assert with_scenarios.json()["scenario"] is None
    problems += differences(with_scenarios.json(), plain_curve.json(), "base curve")
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- 3. ignored, invalid


def _case(name: str) -> dict[str, Any]:
    return NETWORKS[f"ref_{name}"]()


def test_orphaned_and_not_applicable_overrides_are_kept_reported_and_ignored() -> None:
    """Each way an override can fail to apply (proposal §3.3), some with values that would be
    invalid if applied: the scenario solves as the base project (or, beside an applied override,
    as the project with that one value edited by hand), and every ignored override is recorded
    with its state and a message that says why."""
    base = _case("pump_flow_control_parallel_fixed")  # PA fixed, PB speed-controlled, custom fluid
    gone: list[dict[str, Any]] = [
        {"kind": "component", "componentId": "P9", "field": "status", "value": "off"},
        {"kind": "pipe", "connectionId": "L9", "pipeIndex": 0, "field": "length", "value": -1.0},
        {"kind": "pipe", "connectionId": "L1", "pipeIndex": 1, "field": "spec", "value": "x"},
        {"kind": "pipe", "connectionId": "LA1", "pipeIndex": 99, "field": "length", "value": 5},
    ]
    lacking: list[dict[str, Any]] = [
        {"kind": "component", "componentId": "R1", "field": "status", "value": "off"},
        {"kind": "component", "componentId": "T1", "field": "liquidLevel", "value": 2.0},
        {"kind": "component", "componentId": "R2", "field": "speed", "value": SENTINEL},
        {"kind": "component", "componentId": "PA", "field": "setpoint", "value": 0.01},
        {"kind": "component", "componentId": "PA", "field": "control.setpoint", "value": -3},
        {"kind": "project", "field": "fluid.temperature", "value": {"nested": True}},
    ]
    applied = {"kind": "component", "componentId": "PB", "field": "speed", "value": 0.95}
    scenarios = [
        _scenario("S1", "Only ignored", gone + lacking, "Nothing here applies."),
        _scenario("S2", "One applied", [*gone[:2], applied, *lacking[3:5]]),
    ]
    project = {**base, "scenarios": scenarios}
    api = Api()
    base_response = api.solve(base)
    problems = []
    for s_index, scenario in enumerate(scenarios):
        hand = by_hand(project, scenario)
        states = Counter(o.state for o in hand.outcomes)
        assert states["applied"] == (1 if s_index == 1 else 0), states  # the patcher's reading
        got = api.solve(project, scenario["id"])
        want = base_response if s_index == 0 else api.solve(hand.project)
        problems += solve_problems(scenario, s_index, hand, got, want)
        curve = api.curve(project, "PA", scenario["id"])
        problems += curve_problems(scenario, s_index, hand, curve, api.curve(hand.project, "PA"))
    assert not problems, "\n".join(problems)


def _invalid_base() -> dict[str, Any]:
    """R1 -> FCV1 (setpoint 0.03 m³/s) -> PU1 (flow-controlled, minSpeed 0.5) -> R2, in water at
    20 °C, so that each kind of value has a target."""
    base = _case("pump_flow_control_series_fcv_open")
    base["fluid"] = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    return base


def _component(cid: str, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": field, "value": value}


def _pipe(cid: str, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "pipe", "connectionId": cid, "pipeIndex": 0, "field": field, "value": value}


def _fluid(field: str, value: Any) -> dict[str, Any]:
    return {"kind": "project", "field": field, "value": value}


INVALID_VALUES = [
    ("speed above 1", [_component("PU1", "speed", 1.001234567)]),
    ("speed at the minimum speed", [_component("PU1", "speed", 0.25001234567)]),
    ("isolated pump", [_component("PU1", "status", f"isolated {SENTINEL}")]),
    ("FCV setpoint above 100", [_component("FCV1", "setpoint", 123.4567891)]),
    ("custom pipe without a bore", [_pipe("L2", "spec", {"materialId": "custom"})]),
    ("temperature as an object", [_fluid("fluid.temperature", {SENTINEL: 293.1234567})]),
    (
        "invalid whole fluid",
        [
            _fluid(
                "fluid",
                {"kind": "custom", "name": SENTINEL, "density": -9.1234567, "dynamicViscosity": 1},
            )
        ],
    ),
    (
        "unknown fluid kind",
        [_fluid("fluid", {"kind": SENTINEL, "temperature": 293.1234567})],
    ),
    (
        "four invalid values",
        [
            _component("PU1", "speed", 1.001234567),
            _component("FCV1", "setpoint", 123.4567891),
            _pipe("L1", "length", -5.1234567),
            _fluid("fluid.temperature", f"warm {SENTINEL}"),
        ],
    ),
]
"""Scenarios whose values fail their field or their target's validators (proposal §7.1's set):
each is a 400 for that scenario, with every problem listed."""

INVALID_BESIDE_VALID = [
    (
        "custom pipe without a bore, beside a valid length of that pipe",
        [_pipe("L2", "spec", {"materialId": "custom"}), _pipe("L2", "length", 50.0)],
        {0},
    ),
    (
        "speed at the minimum speed, beside a valid setpoint of that pump",
        [_component("PU1", "control.setpoint", 0.02), _component("PU1", "speed", 0.25001234567)],
        {1},
    ),
    (
        "FCV setpoint above 100, beside a valid status of that valve",
        [_component("FCV1", "setpoint", 123.4567891), _component("FCV1", "status", "failed_open")],
        {0},
    ),
]
"""An invalid value beside a valid value of the same element, each with the indices of its
invalid overrides: a rule of the whole element fails once in the hand-edited project, so it is
one issue, at the override whose value it rejects (§4.1 step 4), never at the valid one."""


def _no_echo(response: httpx.Response) -> list[str]:
    return [
        f"the response echoes {text!r}: {response.text[:300]}"
        for text in (SENTINEL, SENTINEL_DIGITS)
        if text in response.text
    ]


def test_invalid_values_are_400_for_their_scenario_only() -> None:
    """An invalid value makes its scenario a 400 (VALIDATION_ERROR), its issues at the
    override, with the errors the hand-edited project's validation gives and no submitted value,
    name or description echoed; the base project and a valid scenario of the same project solve
    as before (proposal §2.4: a scenario with a bad value never blocks the base or another)."""
    base = _invalid_base()
    good = _scenario("OK", "Valid", [_pipe("L3", "length", 240.0)])
    cases = [(label, o, set(range(len(o)))) for label, o in INVALID_VALUES] + INVALID_BESIDE_VALID
    scenarios = [
        _scenario(f"B{i + 1}", f"{label} {SENTINEL}", overrides, f"Described {SENTINEL}")
        for i, (label, overrides, _) in enumerate(cases)
    ] + [good]
    project = {**base, "scenarios": scenarios}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios[:-1]):
        sid = scenario["id"]
        hand = by_hand(project, scenario)
        with pytest.raises(ValidationError):  # the patcher's project is invalid too
            Project.model_validate(hand.project)
        for got, want in (
            (api.solve(project, sid), api.solve(hand.project)),
            (api.curve(project, "PU1", sid), api.curve(hand.project, "PU1")),
        ):
            assert want.status_code == 400, want.text
            problems += error_problems(sid, s_index, hand, got, want) + _no_echo(got)
            if got.status_code == 400:
                prefix = re.compile(rf"body\.project\.scenarios\.{s_index}\.overrides\.(\d+)")
                located = {
                    int(match[1])
                    for issue in got.json()["issues"]
                    if (match := prefix.match(issue["message"]))
                }
                if located != cases[s_index][2]:
                    problems.append(
                        f"{sid}: issues at overrides {located}, expected {cases[s_index][2]}"
                    )

    plain = api.solve(base)
    with_scenarios = api.solve(project)
    assert with_scenarios.status_code == 200, with_scenarios.text
    problems += differences(comparable(with_scenarios.json()), comparable(plain.json()), "base")
    hand = by_hand(project, good)
    got = api.solve(project, "OK")
    problems += solve_problems(good, len(scenarios) - 1, hand, got, api.solve(hand.project))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "spec",
    [
        {"materialId": "custom", "innerDiameter": 0.1, "roughness": 4.5e-5, SENTINEL: 1},
        {"materialId": "custom", "innerDiameter": 0.1, "roughness": 4.5e-5, "length": 9.1234567},
        f"carbon steel {SENTINEL}",
    ],
    ids=["unknown key", "length in a spec", "not an object"],
)
def test_a_spec_takes_only_its_five_keys(spec: Any) -> None:
    """A pipe spec is an object of materialId, schedule, nominalSize, innerDiameter and
    roughness only (§2.2): anything else is a 400 at the override (invalid_pipe_spec for a key
    it does not take), which never names the key or echoes the value."""
    project = {
        **_invalid_base(),
        "scenarios": [_scenario("S1", "Spec", [_pipe("L2", "spec", spec)])],
    }
    api = Api()
    response = api.solve(project, "S1")
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert not _no_echo(response), _no_echo(response)
    assert body["issues"], body
    for issue in body["issues"]:
        assert issue["message"].startswith("body.project.scenarios.0.overrides.0"), issue
        assert "L2" in issue["connectionIds"], issue
    if isinstance(spec, dict):
        assert [i["code"] for i in body["issues"]] == ["invalid_pipe_spec"], body
    assert api.solve(project).status_code == 200


MALFORMED: list[tuple[str, list[dict[str, Any]]]] = [
    (
        "one value twice",
        [_scenario("S1", "x", [_component("PU1", "speed", 0.9), _component("PU1", "speed", 0.8)])],
    ),
    (
        "a value and a part of it",
        [
            _scenario(
                "S1", "x", [_fluid("fluid", {"kind": "builtin"}), _fluid("fluid.temperature", 1)]
            )
        ],
    ),
    ("two scenarios with one id", [_scenario("S1", "x", []), _scenario("S1", "y", [])]),
    (
        "an unknown kind",
        [_scenario("S1", "x", [{"kind": SENTINEL, "field": "status", "value": 1.1234567}])],
    ),
    (
        "a field of another kind",
        [_scenario("S1", "x", [_pipe("L1", "status", "off"), _component("PU1", "spec", {})])],
    ),
    ("a field outside the allow-list", [_scenario("S1", "x", [_component("PU1", "elevation", 1)])]),
    (
        "a rating and a part of it",
        [
            _scenario(
                "S1",
                "x",
                [
                    _component("E1", "rating", {"kind": "Cv", "value": 90.1234567}),
                    _component("E1", "rating.flow", 0.01234567),
                ],
            )
        ],
    ),
    (
        "a capacity and a part of it",
        [
            _scenario(
                "S1",
                "x",
                [
                    _component("RV1", "capacity", {"kind": "effective", "area": 0.001234567}),
                    _component("RV1", "capacity.area", 0.002234567),
                ],
            )
        ],
    ),
    ("pipe index 100", [_scenario("S1", "x", [{**_pipe("L1", "length", 1.0), "pipeIndex": 100}])]),
    ("an unknown key", [_scenario("S1", "x", [{**_pipe("L1", "length", 1.0), SENTINEL: 1}])]),
    ("21 scenarios", [_scenario(f"S{i}", "x", []) for i in range(21)]),
    ("31 overrides", [_scenario("S1", "x", [_pipe(f"Q{i}", "length", 1.0) for i in range(31)])]),
    ("a description over 500 characters", [{**_scenario("S1", "x", []), "description": "d" * 501}]),
    ("no name", [{"id": "S1", "overrides": []}]),
]
"""Scenario structures the request validation rejects (proposal §2.4); each also carries the
sentinel as its name where it has one."""


@pytest.mark.parametrize(("label", "scenarios"), MALFORMED, ids=[m[0] for m in MALFORMED])
def test_a_malformed_scenario_is_rejected_with_the_project(
    label: str, scenarios: list[dict[str, Any]]
) -> None:
    """A malformed scenario is a request-validation error (400, VALIDATION_ERROR) for every
    request on the project, the base included, and the error echoes nothing submitted;
    duplicates are named by index."""
    scenarios = [{**s, "name": f"{s['name']} {SENTINEL}"} if "name" in s else s for s in scenarios]
    project = {**_invalid_base(), "scenarios": scenarios}
    api = Api()
    for response in (
        api.solve(project),
        api.solve(project, "S1"),
        api.curve(project, "PU1", "S1"),
    ):
        assert response.status_code == 400, response.text
        assert response.json()["error"] == "VALIDATION_ERROR"
        assert not _no_echo(response), _no_echo(response)
        if label in (
            "one value twice",
            "a value and a part of it",
            "a rating and a part of it",
            "a capacity and a part of it",
        ):
            assert "overrides 0 and 1" in response.text, response.text
        if label == "two scenarios with one id":
            assert "scenarios 0 and 1" in response.text, response.text


def test_an_unknown_scenario_is_not_found_and_checks_run_in_order() -> None:
    """An unknown scenarioId is a 404 that names it, on /solve and /system-curve; the system
    curve checks the scenario, then its values, then the pump (§3.3)."""
    bad = _scenario("BAD", "Bad", [_component("PU1", "speed", 1.5)])
    good = _scenario("OK", "Good", [_pipe("L3", "length", 240.0)])
    project = {**_invalid_base(), "scenarios": [bad, good]}
    api = Api()
    for response in (api.solve(project, "S99"), api.curve(project, "NOPE", "S99")):
        assert response.status_code == 404, response.text
        body = response.json()
        assert body["error"] == "NOT_FOUND"
        assert "S99" in body["message"], body
        assert "scenario" in body["message"], body
    response = api.curve(project, "NOPE", "BAD")
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "VALIDATION_ERROR"
    response, plain = api.curve(project, "NOPE", "OK"), api.curve(_invalid_base(), "NOPE")
    assert response.status_code == plain.status_code == 404, response.text
    assert response.json()["message"] == plain.json()["message"]


ERRORS = [
    (
        "an unknown pipe size",
        [
            _pipe(
                "L1",
                "spec",
                {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.0999},
            )
        ],
    ),
    ("a setpoint no speed holds", [_component("PU1", "control.setpoint", 99.0)]),
    (
        "an unknown material",
        [_pipe("L2", "spec", {"materialId": "unobtainium", "innerDiameter": 0.1})],
    ),
    ("water below its range", [_fluid("fluid.temperature", 250.0)]),
    (
        "glycol below its freezing point",
        [
            _fluid(
                "fluid",
                {
                    "kind": "builtin",
                    "fluidId": "propylene_glycol",
                    "temperature": 240.0,
                    "concentration": 0.3,
                },
            )
        ],
    ),
]
"""Scenarios whose values pass their fields but leave a project that cannot be solved: topology
issues (422) and fluids out of their property source's range (400 FLUID_ERROR)."""


def test_a_scenario_that_cannot_be_solved_fails_as_the_hand_edited_project() -> None:
    """Topology and fluid errors in a scenario are the hand-edited project's, with the
    scenario's id in the message (§3.3), on /solve and /system-curve; the base still solves."""
    base = _invalid_base()
    scenarios = [_scenario(f"E{i + 1}", label, o) for i, (label, o) in enumerate(ERRORS)]
    project = {**base, "scenarios": scenarios}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios):
        hand = by_hand(project, scenario)
        for got, want in (
            (api.solve(project, scenario["id"]), api.solve(hand.project)),
            (api.curve(project, "PU1", scenario["id"]), api.curve(hand.project, "PU1")),
        ):
            assert want.status_code in (400, 422), want.text
            problems += error_problems(scenario["id"], s_index, hand, got, want)
    assert api.solve(project).status_code == 200
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- 4. base invariance


@pytest.mark.parametrize("name", list(NETWORKS))
def test_a_project_without_a_scenario_solves_as_before(name: str) -> None:
    """The base solve does not depend on the project's scenarios (§4.3). The project without
    scenarios and with them (scenarioId omitted; for every tenth reference case also null, and an
    empty list) give the same response, system curves included, with scenario null and no
    Scenario methods section."""
    base, _, _, project = _setup(name)
    api = Api()
    plain = api.solve(base, curves=True)
    assert plain.status_code == 200, plain.text
    body = plain.json()
    assert set(body) == {"success", "solvedState", "computeTime", "scenario"}
    assert body["scenario"] is None
    titles = [s["title"] for s in body["solvedState"]["trace"]["methods"]["sections"]]
    assert SCENARIO_SECTION not in titles
    variants = [("scenarios, no scenarioId", api.solve(project, curves=True))]
    if name in REFERENCE[::10]:  # the same request to the model: a sample is enough
        null = {"project": project, "scenarioId": None, "options": WITH_CURVES}
        variants += [
            ("an empty list", api.solve({**base, "scenarios": []}, curves=True)),
            ("scenarios, scenarioId null", api.post("/api/v1/solve", null)),
        ]
    problems = []
    for label, response in variants:
        assert response.status_code == 200, f"{label}: {response.text}"
        assert response.json()["scenario"] is None, label
        problems += differences(comparable(response.json()), comparable(body), label)
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- the allow-list


def test_the_published_allow_list_is_the_designs() -> None:
    """x-override-fields (proposal §2.3) names, for each target schema, exactly the fields the
    design's allow-list (§2.2) gives it, which is what these tests draw from."""
    schemas = TestClient(app).get("/openapi.json").json()["components"]["schemas"]
    published = schemas["Scenario"]["x-override-fields"]
    mine = {cls.__name__: set(fields) for cls, fields in COMPONENT_FIELDS.items()}
    mine["PipeDefinition"] = set(PIPE_FIELDS)
    mine["Project"] = set(PROJECT_FIELDS)
    assert {k: set(v) for k, v in published.items()} == mine
    literals = schemas["ComponentOverride"]["properties"]["field"]
    assert set(literals["enum"]) == set(COMPONENT_FIELD_NAMES)


# --------------------------------------------------------------------------- 5. equipment

MEG_30_AT_5C_DENSITY = 1043.4700187522
"""kg/m³: a vendor's rating fluid, 30 % MEG at 5 °C as CoolProp gives it (proposal §7.1;
a test input here, written as the datasheet prints it)."""

EQUIPMENT_SCENARIOS: list[tuple[str, list[tuple[dict[str, Any], tuple[State, ...]]]]] = [
    (
        "equipment_line",
        [
            (
                _scenario("S1", "Dirty strainer", [_component("E1", "rating.pressureLoss", 7.0e4)]),
                ("applied",),
            ),
            (
                _scenario(
                    "S2",
                    "Vendor B",
                    [
                        _component(
                            "E1",
                            "rating",
                            {
                                "kind": "point",
                                "pressureLoss": 42_000.0,
                                "flow": 0.012,
                                "density": MEG_30_AT_5C_DENSITY,
                            },
                        )
                    ],
                ),
                ("applied",),
            ),
            (
                _scenario(
                    "S3", "Vendor C", [_component("E1", "rating", {"kind": "Cv", "value": 120.0})]
                ),
                ("applied",),
            ),
            (
                _scenario(
                    "S4", "Vendor D", [_component("E1", "rating", {"kind": "Kv", "value": 75.0})]
                ),
                ("applied",),
            ),
            (
                _scenario(
                    "S5",
                    "Rated flow and fluid",
                    [
                        _component("E1", "rating.flow", 0.02),
                        _component("E1", "rating.density", 870.0),
                    ],
                ),
                ("applied", "applied"),
            ),
            (
                _scenario(
                    "S6",
                    "A Cv on a rated point",
                    [
                        _component("E1", "rating.value", 80.0),
                        _component("E1", "rating.density", 1.2e3),
                    ],
                ),
                ("not_applicable", "applied"),
            ),
        ],
    ),
    (
        "equipment_cv_glycol",
        [
            (
                _scenario("S1", "Cv 90 to 80", [_component("E1", "rating.value", 80.0)]),
                ("applied",),
            ),
            (
                _scenario(
                    "S2",
                    "Points on a Cv",
                    [
                        _component("E1", "rating.pressureLoss", 6.0e4),
                        _component("E1", "rating.flow", 0.02),
                        _component("E1", "rating.density", 999.0),
                    ],
                ),
                ("not_applicable", "not_applicable", "not_applicable"),
            ),
            (
                _scenario(
                    "S3",
                    "Rated on its own fluid",
                    [
                        _component(
                            "E1",
                            "rating",
                            {
                                "kind": "point",
                                "pressureLoss": 35_000.0,
                                "flow": 0.015,
                                "density": MEG_30_AT_5C_DENSITY,
                            },
                        )
                    ],
                ),
                ("applied",),
            ),
        ],
    ),
]
"""Proposal §5.1's use cases on a point-rated and a Cv-rated element (test inputs), with the
state the design gives each override: a part the base element's rating kind does not hold is
not applicable (kept, reported, ignored)."""


@pytest.mark.parametrize("name", [n for n, _ in EQUIPMENT_SCENARIOS])
def test_equipment_scenarios_solve_as_the_hand_edited_project(name: str) -> None:
    """Each scenario solves as its hand-edited project (bit for bit, apart from its record and
    text), with the states the design gives; one that applies a value moves the solution beyond
    D6, and the element's result echoes the rating used (proposal §2.2)."""
    scenarios = dict(EQUIPMENT_SCENARIOS)[name]
    base = _case(name)
    project = {**base, "scenarios": [s for s, _ in scenarios]}
    api = Api()
    base_response = api.solve(base)
    assert base_response.status_code == 200, base_response.text
    base_state = base_response.json()["solvedState"]
    problems = []
    for s_index, (scenario, states) in enumerate(scenarios):
        hand = by_hand(project, scenario)
        assert tuple(o.state for o in hand.outcomes) == states, scenario["id"]
        got = api.solve(project, scenario["id"])
        applied = "applied" in states
        want = api.solve(hand.project) if applied else base_response
        problems += solve_problems(scenario, s_index, hand, got, want)
        if got.status_code != 200:
            continue
        state = got.json()["solvedState"]
        if applied and not _moved(base_state, state):
            problems.append(f"{scenario['id']}: the solution did not move beyond D6")
        components = Project.model_validate(hand.project).components
        [e1] = [c for c in components if c.id == "E1"]
        assert isinstance(e1, Equipment)
        echoed = state["equipmentResults"]["E1"]["rating"]
        if not same_json(echoed, e1.rating.model_dump(mode="json", by_alias=True)):
            problems.append(f"{scenario['id']}: equipmentResults.E1.rating {echoed}")
        if isinstance(e1.rating, RatedPoint) != (
            state["equipmentResults"]["E1"]["flowRatio"] is not None
        ):
            problems.append(f"{scenario['id']}: flowRatio is null exactly for a Cv or Kv")
    assert not problems, "\n".join(problems)


EQUIPMENT_INVALID = [
    ("rated pressure drop above 1e8", [_component("E1", "rating.pressureLoss", 1.01234567e8)]),
    ("negative rated density", [_component("E1", "rating.density", -9.1234567)]),
    ("zero rated flow", [_component("E1", "rating.flow", 0.0)]),
    (
        "a whole rating of kind K",
        [_component("E1", "rating", {"kind": "K", "value": 1.1234567})],
    ),
    (
        "an unknown rating kind",
        [_component("E1", "rating", {"kind": SENTINEL, "value": 1.1234567})],
    ),
    (
        "a rated point without its flow",
        [
            _component(
                "E1", "rating", {"kind": "point", "pressureLoss": 5.0e4, "density": 1000.1234567}
            )
        ],
    ),
    ("a Cv above 1e7", [_component("E1", "rating", {"kind": "Cv", "value": 1.01234567e7})]),
]
"""Rating values the model rejects (proposal §2.1): a value out of its bounds, a missing value,
and a kind that is not point, Cv or Kv (a K included): each a 400 at the override."""


def test_invalid_equipment_ratings_are_400_at_the_override() -> None:
    """Each invalid rating value makes its scenario a 400 (VALIDATION_ERROR), its issues at the
    override with the hand-edited project's error codes and messages (the union's tag dropped
    from the location, proposal §2.1), and no submitted value or name echoed; the base solves."""
    base = _case("equipment_line")
    scenarios = [
        _scenario(f"B{i + 1}", f"{label} {SENTINEL}", overrides)
        for i, (label, overrides) in enumerate(EQUIPMENT_INVALID)
    ]
    project = {**base, "scenarios": scenarios}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios):
        sid = scenario["id"]
        hand = by_hand(project, scenario)
        with pytest.raises(ValidationError):
            Project.model_validate(hand.project)
        got, want = api.solve(project, sid), api.solve(hand.project)
        assert want.status_code == 400, want.text
        problems += error_problems(sid, s_index, hand, got, want) + _no_echo(got)
    assert api.solve(project).status_code == 200
    assert not problems, "\n".join(problems)


def test_unrepresentable_equipment_ratings_fail_as_the_hand_edited_project() -> None:
    """Ratings inside the bounds whose coefficient c is not a finite positive double (proposal
    decision 10: ρ_r = Q_r = 10⁻³⁰⁰, whose Q_r² underflows to 0; a Cv of 10⁻¹⁷⁰) are a topology
    issue (422) in a scenario as in the hand-edited project, with the scenario's id in the
    message; the base still solves."""
    base = _case("equipment_line")
    tiny_point = {"kind": "point", "pressureLoss": 5.0e4, "flow": 1.0e-300, "density": 1.0e-300}
    scenarios = [
        _scenario("U1", "Tiny point", [_component("E1", "rating", tiny_point)]),
        _scenario("U2", "Tiny Cv", [_component("E1", "rating", {"kind": "Cv", "value": 1.0e-170})]),
        _scenario(
            "U3", "Tiny Kv value", [_component("E1", "rating", {"kind": "Kv", "value": 1.0e-160})]
        ),
    ]
    project = {**base, "scenarios": scenarios}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios):
        hand = by_hand(project, scenario)
        got, want = api.solve(project, scenario["id"]), api.solve(hand.project)
        assert want.status_code == 422, want.text
        codes = {i["code"] for i in want.json()["issues"]}
        assert codes == {"EQUIPMENT_RATING_OUT_OF_RANGE"}, want.text
        assert all("E1" in i["componentIds"] for i in want.json()["issues"]), want.text
        problems += error_problems(scenario["id"], s_index, hand, got, want)
    assert api.solve(project).status_code == 200
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- 6. orifice plates

ORIFICE_SCENARIOS: list[tuple[str, list[tuple[dict[str, Any], tuple[State, ...], bool]]]] = [
    (
        "orifice_line",
        [
            (
                _scenario("S1", "Second plate", [_component("OR1", "boreDiameter", 0.04)]),
                ("applied",),
                True,
            ),
            (
                _scenario(
                    "S2", "Calibrated plate", [_component("OR1", "dischargeCoefficient", 0.66)]
                ),
                ("applied",),
                True,
            ),
            (
                _scenario(
                    "S3",
                    "Both, and a rating it does not have",
                    [
                        _component("OR1", "boreDiameter", 0.045),
                        _component("OR1", "dischargeCoefficient", 0.55),
                        _component("OR1", "rating.flow", 0.02),
                    ],
                ),
                ("applied", "applied", "not_applicable"),
                True,
            ),
        ],
    ),
    (
        "orifice_entered_c",
        [
            (
                _scenario(
                    "S1", "ISO 5167-2's C", [_component("OR1", "dischargeCoefficient", None)]
                ),
                ("applied",),
                True,
            ),
        ],
    ),
    (
        "orifice_entered_c_at_taps",
        [
            (
                _scenario(
                    "S1", "ISO 5167-2's C", [_component("OR1", "dischargeCoefficient", None)]
                ),
                ("applied",),
                False,
            ),
            (
                _scenario(
                    "S2", "Another calibration", [_component("OR1", "dischargeCoefficient", 0.5)]
                ),
                ("applied",),
                True,
            ),
            (
                _scenario("S3", "A bore on a reservoir", [_component("R1", "boreDiameter", 0.05)]),
                ("not_applicable",),
                False,
            ),
        ],
    ),
]
"""Proposal §5.1's use cases (test inputs): a second plate (one bore change), a calibrated plate
(one C), ISO's C against a vendor's (null on a base that enters one), with the state the design
gives each override (an orifice field on another type, or another type's field on a plate, is
not applicable, D15) and whether the solution moves beyond D6. Null on orifice_entered_c moves
the flow by +0.58 % (its 0.6 against ISO's 0.6048 at D and D/2); on orifice_entered_c_at_taps
by +0.17 % only (its 0.6 against ISO's 0.6008 at the corner taps, the derivation's numbers), so
there the test checks the coefficient changed instead."""


@pytest.mark.parametrize("name", [n for n, _ in ORIFICE_SCENARIOS])
def test_orifice_scenarios_solve_as_the_hand_edited_project(name: str) -> None:
    """Each scenario solves as its hand-edited project (bit for bit, apart from its record and
    text), with the states the design gives; one marked so moves the solution beyond D6 (the
    other applied one changes the plate's coefficient), and the plate's result echoes the bore
    and the source of C used (proposal §2.2)."""
    scenarios = dict(ORIFICE_SCENARIOS)[name]
    base = _case(name)
    project = {**base, "scenarios": [s for s, _, _ in scenarios]}
    api = Api()
    base_response = api.solve(base)
    assert base_response.status_code == 200, base_response.text
    base_state = base_response.json()["solvedState"]
    problems = []
    for s_index, (scenario, states, moves) in enumerate(scenarios):
        hand = by_hand(project, scenario)
        assert tuple(o.state for o in hand.outcomes) == states, scenario["id"]
        got = api.solve(project, scenario["id"])
        applied = "applied" in states
        want = api.solve(hand.project) if applied else base_response
        problems += solve_problems(scenario, s_index, hand, got, want)
        if got.status_code != 200:
            problems.append(f"{scenario['id']}: {got.status_code} {got.text[:300]}")
            continue
        state = got.json()["solvedState"]
        if moves and not _moved(base_state, state):
            problems.append(f"{scenario['id']}: the solution did not move beyond D6")
        [plate] = [
            c for c in Project.model_validate(hand.project).components if isinstance(c, Orifice)
        ]
        result = state["orificeResults"][plate.id]
        base_c = base_state["orificeResults"][plate.id]["dischargeCoefficient"]
        if applied and result["dischargeCoefficient"] == base_c and not moves:
            problems.append(f"{scenario['id']}: the plate's coefficient did not change")
        if result["boreDiameter"] != plate.bore_diameter:
            problems.append(f"{scenario['id']}: boreDiameter {result['boreDiameter']}")
        source = "iso_5167_2" if plate.discharge_coefficient is None else "entered"
        if result["coefficientSource"] != source:
            problems.append(f"{scenario['id']}: coefficientSource {result['coefficientSource']}")
    assert not problems, "\n".join(problems)


ORIFICE_INVALID = [
    ("a bore of zero", [_component("OR1", "boreDiameter", 0.0)]),
    ("a bore above 10 m", [_component("OR1", "boreDiameter", 11.1234567)]),
    ("a discharge coefficient of zero", [_component("OR1", "dischargeCoefficient", 0.0)]),
    ("a discharge coefficient above 1", [_component("OR1", "dischargeCoefficient", 1.51234567)]),
    ("a discharge coefficient as text", [_component("OR1", "dischargeCoefficient", SENTINEL)]),
]
"""Values the model rejects (proposal §2.1: d in (0, 10] m, C in (0, 1]): each a 400 at the
override."""


def test_invalid_orifice_values_are_400_at_the_override() -> None:
    """Each invalid value makes its scenario a 400 (VALIDATION_ERROR), its issues at the override
    with the hand-edited project's error codes and messages, and no submitted value or name
    echoed; the base solves."""
    base = _case("orifice_line")
    scenarios = [
        _scenario(f"B{i + 1}", f"{label} {SENTINEL}", overrides)
        for i, (label, overrides) in enumerate(ORIFICE_INVALID)
    ]
    project = {**base, "scenarios": scenarios}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios):
        sid = scenario["id"]
        hand = by_hand(project, scenario)
        with pytest.raises(ValidationError):
            Project.model_validate(hand.project)
        got, want = api.solve(project, sid), api.solve(hand.project)
        assert want.status_code == 400, want.text
        problems += error_problems(sid, s_index, hand, got, want) + _no_echo(got)
    assert api.solve(project).status_code == 200
    assert not problems, "\n".join(problems)


def test_an_unrepresentable_orifice_fails_as_the_hand_edited_project() -> None:
    """A bore inside its bounds but not smaller than the inlet pipe's inner diameter (β ≥ 1,
    decision 17 (a)) is a topology issue (422 ORIFICE_OUT_OF_RANGE) in a scenario as in the
    hand-edited project, naming the plate, with the scenario's id in the message; the base still
    solves."""
    base = _case("orifice_line")
    scenarios = [
        _scenario("U1", "A bore the pipe's size", [_component("OR1", "boreDiameter", 0.1023)]),
        _scenario("U2", "A bore above the pipe's", [_component("OR1", "boreDiameter", 0.11)]),
    ]
    project = {**base, "scenarios": scenarios}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios):
        hand = by_hand(project, scenario)
        got, want = api.solve(project, scenario["id"]), api.solve(hand.project)
        assert want.status_code == 422, want.text
        codes = {i["code"] for i in want.json()["issues"]}
        assert codes == {"ORIFICE_OUT_OF_RANGE"}, want.text
        assert all("OR1" in i["componentIds"] for i in want.json()["issues"]), want.text
        problems += error_problems(scenario["id"], s_index, hand, got, want)
    assert api.solve(project).status_code == 200
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- 7. relief valves

RELIEF_SCENARIOS: list[tuple[str, list[tuple[dict[str, Any], tuple[State, ...], bool]]]] = [
    (
        "relief_pump_bypass",
        [
            (
                _scenario("S1", "A lower set", [_component("RV1", "setPressure", 3.0e5)]),
                ("applied",),
                True,
            ),
            (
                _scenario("S2", "A smaller valve", [_component("RV1", "capacity.letter", "J")]),
                ("applied",),
                True,
            ),
            (
                _scenario("S3", "Gagged", [_component("RV1", "status", "locked_closed")]),
                ("applied",),
                True,
            ),
            (
                _scenario(
                    "S4",
                    "The selected valve",
                    [
                        _component(
                            "RV1",
                            "capacity",
                            {"kind": "certified", "area": 1.6e-3, "dischargeCoefficient": 0.85},
                        )
                    ],
                ),
                ("applied",),
                True,
            ),
            (
                _scenario(
                    "S5",
                    "Discharge open, and values a letter does not hold",
                    [
                        _component("IV1", "status", "active"),
                        _component("RV1", "capacity.area", 1.0e-3),
                        _component("RV1", "capacity.overpressure", 0.1),
                        _component("RV1", "capacity.dischargeCoefficient", 0.8),
                    ],
                ),
                ("applied", "not_applicable", "not_applicable", "not_applicable"),
                True,
            ),
        ],
    ),
    (
        "relief_certified",
        [
            (
                _scenario(
                    "S1", "ASME's overpressure", [_component("RV1", "capacity.overpressure", None)]
                ),
                ("applied",),
                True,
            ),
            (
                _scenario(
                    "S2",
                    "Recertified",
                    [
                        _component("RV1", "capacity.dischargeCoefficient", 0.6),
                        _component("RV1", "capacity.area", 2.0e-4),
                    ],
                ),
                ("applied", "applied"),
                True,
            ),
            (
                _scenario(
                    "S3",
                    "A letter on a certified valve",
                    [_component("RV1", "capacity.letter", "G")],
                ),
                ("not_applicable",),
                False,
            ),
            (
                _scenario(
                    "S4",
                    "An API 526 letter",
                    [_component("RV1", "capacity", {"kind": "api526", "letter": "G"})],
                ),
                ("applied",),
                True,
            ),
        ],
    ),
]
"""Proposal §5's use cases (test inputs): a lower set, a smaller valve (a letter), a gagged
valve, the selected valve's certified values in place of a letter (a kind change), the
discharge opened beside values a letter does not hold, ASME's default overpressure (null) on a
certified valve, its coefficient and area recertified, a letter on it (not applicable), and a
letter in place of it; with the state the design gives each override and whether the solution
moves beyond D6."""


@pytest.mark.parametrize("name", [n for n, _ in RELIEF_SCENARIOS])
def test_relief_scenarios_solve_as_the_hand_edited_project(name: str) -> None:
    """Each scenario solves as its hand-edited project (bit for bit, apart from its record and
    text), with the states the design gives; one marked so moves the solution beyond D6, and the
    valve's result echoes the set, capacity kind, area and overpressure used (proposal §2.2)."""
    scenarios = dict(RELIEF_SCENARIOS)[name]
    base = _case(name)
    project = {**base, "scenarios": [s for s, _, _ in scenarios]}
    api = Api()
    base_response = api.solve(base)
    assert base_response.status_code == 200, base_response.text
    base_state = base_response.json()["solvedState"]
    problems = []
    for s_index, (scenario, states, moves) in enumerate(scenarios):
        hand = by_hand(project, scenario)
        assert tuple(o.state for o in hand.outcomes) == states, scenario["id"]
        got = api.solve(project, scenario["id"])
        applied = "applied" in states
        want = api.solve(hand.project) if applied else base_response
        problems += solve_problems(scenario, s_index, hand, got, want)
        if got.status_code != 200:
            problems.append(f"{scenario['id']}: {got.status_code} {got.text[:300]}")
            continue
        state = got.json()["solvedState"]
        if moves and not _moved(base_state, state):
            problems.append(f"{scenario['id']}: the solution did not move beyond D6")
        [valve] = [
            c for c in Project.model_validate(hand.project).components if isinstance(c, ReliefValve)
        ]
        result = state["reliefValveResults"][valve.id]
        values = el.relief_capacity(valve.capacity, valve.set_pressure)
        if result["setPressure"] != valve.set_pressure:
            problems.append(f"{scenario['id']}: setPressure {result['setPressure']}")
        if result["capacity"]["kind"] != valve.capacity.kind:
            problems.append(f"{scenario['id']}: capacity kind {result['capacity']['kind']}")
        if result["capacity"]["area"] != values.area:
            problems.append(f"{scenario['id']}: capacity area {result['capacity']['area']}")
        if result["overpressure"] != values.overpressure:
            problems.append(f"{scenario['id']}: overpressure {result['overpressure']}")
        if result["overpressureSource"] != values.source:
            problems.append(f"{scenario['id']}: overpressureSource {result['overpressureSource']}")
        if valve.status == "locked_closed" and result["flow"] != 0.0:
            problems.append(f"{scenario['id']}: a gagged valve passes {result['flow']}")
    assert not problems, "\n".join(problems)


RELIEF_INVALID = [
    ("a set of zero", [_component("RV1", "setPressure", 0.0)]),
    ("a set above 1e8 Pa", [_component("RV1", "setPressure", 2.01234567e8)]),
    ("a set as text", [_component("RV1", "setPressure", SENTINEL)]),
    ("an unknown letter", [_component("RV1", "capacity.letter", "Z1234567")]),
    (
        "an unknown capacity kind",
        [_component("RV1", "capacity", {"kind": SENTINEL, "area": 1.01234567e-3})],
    ),
    (
        "a certified capacity without its coefficient",
        [_component("RV1", "capacity", {"kind": "certified", "area": 1.01234567e-3})],
    ),
    ("a gagged-open status", [_component("RV1", "status", f"failed_open {SENTINEL}")]),
]
"""Values the model rejects on a letter's valve (proposal §2.1: the set in (0, 10⁸] Pa, letters
D to T, a capacity of one of three kinds with its values, statuses active and locked_closed):
each a 400 at the override."""

RELIEF_CERTIFIED_INVALID = [
    ("an overpressure of zero", [_component("RV1", "capacity.overpressure", 0.0)]),
    ("an overpressure above 1", [_component("RV1", "capacity.overpressure", 2.01234567)]),
    ("an area of zero", [_component("RV1", "capacity.area", 0.0)]),
    ("an area above its bound", [_component("RV1", "capacity.area", 81.1234567)]),
    ("a coefficient above 1", [_component("RV1", "capacity.dischargeCoefficient", 1.51234567)]),
]
"""Values a certified capacity rejects (overpressure and coefficient in (0, 1], the area in (0,
π × 10²/4] m²): each a 400 at the override."""


@pytest.mark.parametrize(
    ("name", "invalid"),
    [("relief_pump_bypass", RELIEF_INVALID), ("relief_certified", RELIEF_CERTIFIED_INVALID)],
    ids=["letter", "certified"],
)
def test_invalid_relief_values_are_400_at_the_override(
    name: str, invalid: list[tuple[str, list[dict[str, Any]]]]
) -> None:
    """Each invalid value makes its scenario a 400 (VALIDATION_ERROR), its issues at the override
    with the hand-edited project's error codes and messages, and no submitted value or name
    echoed; the base solves."""
    base = _case(name)
    scenarios = [
        _scenario(f"B{i + 1}", f"{label} {SENTINEL}", overrides)
        for i, (label, overrides) in enumerate(invalid)
    ]
    project = {**base, "scenarios": scenarios}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios):
        sid = scenario["id"]
        hand = by_hand(project, scenario)
        with pytest.raises(ValidationError):
            Project.model_validate(hand.project)
        got, want = api.solve(project, sid), api.solve(hand.project)
        assert want.status_code == 400, want.text
        problems += error_problems(sid, s_index, hand, got, want) + _no_echo(got)
    assert api.solve(project).status_code == 200
    assert not problems, "\n".join(problems)


def test_a_relief_set_below_asmes_scope_fails_as_the_hand_edited_project() -> None:
    """A set inside its bounds but below ASME's 15 psi (103,421.36 Pa) on a capacity that takes
    ASME's overpressure (a letter, or a certified one set back to the default) is a topology issue
    (422 RELIEF_VALVE_OUT_OF_RANGE, decision 14) in a scenario as in the hand-edited project,
    naming the valve, with the scenario's id in the message; the same set with a certified
    overpressure solves; the base still solves."""
    base = _case("relief_certified")
    scenarios = [
        _scenario(
            "U1",
            "Below ASME's scope on a letter",
            [
                _component("RV1", "capacity", {"kind": "api526", "letter": "F"}),
                _component("RV1", "setPressure", 9.0e4),
            ],
        ),
        _scenario(
            "U2",
            "Below ASME's scope on ASME's default",
            [
                _component("RV1", "capacity.overpressure", None),
                _component("RV1", "setPressure", 9.0e4),
            ],
        ),
    ]
    fine = _scenario("OK", "Below 15 psi, certified", [_component("RV1", "setPressure", 9.0e4)])
    project = {**base, "scenarios": [*scenarios, fine]}
    api = Api()
    problems = []
    for s_index, scenario in enumerate(scenarios):
        hand = by_hand(project, scenario)
        got, want = api.solve(project, scenario["id"]), api.solve(hand.project)
        assert want.status_code == 422, want.text
        codes = {i["code"] for i in want.json()["issues"]}
        assert codes == {"RELIEF_VALVE_OUT_OF_RANGE"}, want.text
        assert all("RV1" in i["componentIds"] for i in want.json()["issues"]), want.text
        problems += error_problems(scenario["id"], s_index, hand, got, want)
    hand = by_hand(project, fine)
    got = api.solve(project, "OK")
    assert got.status_code == 200, got.text
    problems += solve_problems(fine, len(scenarios), hand, got, api.solve(hand.project))
    assert api.solve(project).status_code == 200
    assert not problems, "\n".join(problems)
