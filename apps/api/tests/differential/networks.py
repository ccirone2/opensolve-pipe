"""Fixed networks of the solver-comparison corpus (``corpus.py``), as validated ``Project``s.

- ``ladder``: a looped ladder of Crane (or ideal) tees fed by pumps in series, the
  performance probe of M4 (many Crane tees, so many outer iterations).
- ``step_hold_wye``: a step-hold probe, a 45° Crane wye with a small lateral (β² = 0.25)
  between three reservoirs; scanning the third reservoir's level moves the diverging split
  across q = 0.4, where ``K_branch_diverging_Crane`` steps. It is not the network of the
  reference case ``wye_crane_step_hold`` (other levels, pipes and β²), which the corpus holds
  as ``ref_wye_crane_step_hold``.

All numbers are test inputs (SI); none is a reference value.
"""

from typing import Any

from opensolve_pipe.models.project import Project
from tests.unit import helpers

PUMP_CURVE: dict[str, Any] = {
    "id": "C1",
    "name": "curve",
    "points": [
        {"flow": 0.0, "head": 40.0},
        {"flow": 0.02, "head": 35.0},
        {"flow": 0.04, "head": 20.0},
    ],
    "npshrCurve": [{"flow": 0.0, "npshr": 1.0}, {"flow": 0.04, "npshr": 4.0}],
}

Port = tuple[str, str]  # (component id, port id)


def _ports(ids: list[str], size: float = 0.1) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": size} for p in ids]


def _reservoir(cid: str, level: float = 10.0, elevation: float = 0.0) -> dict[str, Any]:
    return {
        "type": "reservoir",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "liquidLevel": level,
        "ports": _ports(["port_1"]),
    }


def _tee(cid: str, loss: str = "crane") -> dict[str, Any]:
    return {
        "type": "branch",
        "branchType": "tee",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "lossModel": loss,
        "ports": _ports(["run_inlet", "run_outlet", "branch"]),
    }


def _pump(cid: str, curve: str = "C1") -> dict[str, Any]:
    return {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "curveId": curve,
        "ports": _ports(["suction", "discharge"]),
    }


def _conn(
    cid: str, a: Port, b: Port, length: float = 50.0, d: float = 0.1, rough: float = 4.5e-5
) -> dict[str, Any]:
    """A custom-pipe connection."""
    return {
        "id": cid,
        "fromComponentId": a[0],
        "fromPortId": a[1],
        "toComponentId": b[0],
        "toPortId": b[1],
        "piping": {
            "pipes": [
                {"materialId": "custom", "length": length, "innerDiameter": d, "roughness": rough}
            ],
            "fittings": [],
        },
    }


def _library_conn(cid: str, a: Port, b: Port) -> dict[str, Any]:
    """A 4" schedule 40 carbon-steel connection, 30 m with two long-radius elbows."""
    return {
        "id": cid,
        "fromComponentId": a[0],
        "fromPortId": a[1],
        "toComponentId": b[0],
        "toPortId": b[1],
        "piping": {
            "pipes": [
                {
                    "materialId": "carbon_steel",
                    "schedule": "40",
                    "nominalSize": 0.1016,
                    "length": 30.0,
                }
            ],
            "fittings": [{"type": "elbow_90_lr", "quantity": 2}],
        },
    }


def _project(components: list[dict[str, Any]], connections: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "id": "probe",
        "metadata": {"name": "probe", "created": "2026-10-21", "modified": "2026-10-21"},
        "settings": {
            "units": {},
            "siteElevation": 0.0,
            "solverOptions": {
                "frictionMethod": "colebrook",
                "maxIterations": 100,
                "tolerance": 1e-9,
            },
        },
        "fluid": {"kind": "builtin", "fluidId": "water", "temperature": 293.15},
        "components": components,
        "connections": connections,
        "pumpLibrary": [PUMP_CURVE],
    }


def ladder(n_rungs: int, n_pumps: int = 1, loss: str = "crane", library: bool = False) -> Project:
    """A looped ladder: supply reservoir R0 -> pumps in series on the feed, two rails of tees
    joined by rung pipes, ending in a reservoir on each rail (RA, RB) plus a second supply RBin
    on rail B. Components = 4 + n_pumps + 2*n_rungs. ``library``: 4" schedule 40 steel with
    elbows instead of custom pipes. A connection id that repeats a component id (the rung R0)
    gets an X prefix."""
    mk = _library_conn if library else _conn
    comps: list[dict[str, Any]] = [_reservoir("R0", 5.0)]
    conns: list[dict[str, Any]] = []
    prev = ("R0", "port_1")
    for i in range(n_pumps):
        comps.append(_pump(f"PU{i}"))
        conns.append(mk(f"F{i}", prev, (f"PU{i}", "suction")))
        prev = (f"PU{i}", "discharge")
    # rail A: TA0..TA{n-1}; rail B: TB0..TB{n-1}; rung i connects TA_i.branch -> TB_i.branch
    for i in range(n_rungs):
        comps.append(_tee(f"TA{i}", loss))
        comps.append(_tee(f"TB{i}", loss))
    conns.append(mk("FA", prev, ("TA0", "run_inlet")))
    for i in range(n_rungs - 1):
        conns.append(mk(f"A{i}", (f"TA{i}", "run_outlet"), (f"TA{i + 1}", "run_inlet")))
        conns.append(mk(f"B{i}", (f"TB{i}", "run_outlet"), (f"TB{i + 1}", "run_inlet")))
    for i in range(n_rungs):
        conns.append(mk(f"R{i}", (f"TA{i}", "branch"), (f"TB{i}", "branch")))
    comps.append(_reservoir("RA", 10.0))
    comps.append(_reservoir("RB", 12.0))
    comps.append(_reservoir("RBin", 8.0))
    conns.append(mk("EA", (f"TA{n_rungs - 1}", "run_outlet"), ("RA", "port_1")))
    conns.append(mk("EB", (f"TB{n_rungs - 1}", "run_outlet"), ("RB", "port_1")))
    conns.append(mk("SB", ("RBin", "port_1"), ("TB0", "run_inlet")))
    ids = {c["id"] for c in comps}
    for c in conns:
        if c["id"] in ids:
            c["id"] = "X" + c["id"]
    return Project.model_validate(_project(comps, conns))


def step_hold_wye(level3: float, l3: float = 5.0) -> Project:
    """R1 (level 20 m) -> 45° Crane wye W -> R2 (10 m) on outlet_1 (100 mm) and R3 (level3) on
    outlet_2 (50 mm, length l3)."""
    comps = [
        helpers.reservoir("R1", level=20.0),
        {
            "type": "branch",
            "branchType": "wye",
            "id": "W",
            "name": "W",
            "elevation": 0.0,
            "angle": 45.0,
            "lossModel": "crane",
            "ports": [{"id": p, "nominalSize": 0.1} for p in ("inlet", "outlet_1", "outlet_2")],
        },
        helpers.reservoir("R2", level=10.0),
        helpers.reservoir("R3", level=level3),
    ]
    conns = [
        helpers.connection("L1", ("R1", "port_1"), ("W", "inlet"), diameter=0.1),
        helpers.connection("L2", ("W", "outlet_1"), ("R2", "port_1"), diameter=0.1),
        helpers.connection("L3", ("W", "outlet_2"), ("R3", "port_1"), diameter=0.05, length=l3),
    ]
    return helpers.make_project(comps, conns)
