"""Small pump stations that hold pressure relief valves (CLAUDE.md D21 and D22), as API JSON
dicts. Test helper, also used by ``tests/differential/test_pump_group_check_smoke.py``.

Every pump has the curve ``CURVE`` (shutoff head 45 m) at full speed; every relief valve is
conventional, rated by an API 526 letter, so its overpressure is ASME's default; the fluid is the
helpers' custom liquid (998 kg/m³, 1 mPa·s)."""

import copy
from typing import Any

from .helpers import connection, project_dict, reservoir, tee

CURVE: dict[str, Any] = {
    "id": "PC-A",
    "name": "Curve PC-A",
    "points": [
        {"flow": q, "head": h}
        for q, h in ((0.0, 45.0), (0.01, 44.0), (0.02, 41.0), (0.03, 35.5), (0.04, 27.0))
    ],
}
"""m³/s and m: shutoff 45 m."""
SHUTOFF = 45.0
"""m: ``CURVE``'s head at zero flow."""
D_MAIN, D_RELIEF = 0.1023, 0.0779
"""m: the bores of the main lines and of the lines to and from a relief valve."""


def _two_ports(names: tuple[str, str], size: float = 0.1) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": size} for p in names]


def pump(cid: str) -> dict[str, Any]:
    return {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "curveId": CURVE["id"],
        "speed": 1.0,
        "status": "on",
        "ports": _two_ports(("suction", "discharge")),
    }


def relief(
    cid: str, set_pressure: float, letter: str = "L", status: str = "active"
) -> dict[str, Any]:
    return {
        "type": "relief_valve",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "setPressure": set_pressure,
        "capacity": {"kind": "api526", "letter": letter},
        "status": status,
        "ports": _two_ports(("inlet", "outlet"), 0.05),
    }


def gate(cid: str, status: str = "isolated") -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": "gate",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "status": status,
        "ports": _two_ports(("inlet", "outlet"), 0.05),
    }


def _project(comps: list[dict[str, Any]], conns: list[dict[str, Any]]) -> dict[str, Any]:
    return project_dict(comps, conns, pump_library=[copy.deepcopy(CURVE)])


def bypass_parallel(
    r2_level: float = 20.0, set_pressure: float = 150_000.0, *, r1_level: float = 2.0
) -> dict[str, Any]:
    """P1 and P2 in parallel between suction tees TS1, TS2 and discharge tees TD1, TD2, with a
    minimum-flow relief valve RV1 from TD2's branch back to TS2's branch (inside the station,
    which it makes mixed: it joins the pumps' two sides); TD2's run → 50 m → R2."""
    comps = [
        reservoir("R1", level=r1_level),
        tee("TS1"),
        tee("TS2"),
        pump("P1"),
        pump("P2"),
        tee("TD1"),
        tee("TD2"),
        relief("RV1", set_pressure),
        reservoir("R2", level=r2_level),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("TS1", "run_inlet"), length=5.0, diameter=D_MAIN),
        connection("L2", ("TS1", "run_outlet"), ("TS2", "run_inlet"), length=5.0, diameter=D_MAIN),
        connection("L3", ("TS1", "branch"), ("P1", "suction"), length=5.0, diameter=D_MAIN),
        connection("L4", ("TS2", "run_outlet"), ("P2", "suction"), length=5.0, diameter=D_MAIN),
        connection("L5", ("RV1", "outlet"), ("TS2", "branch"), length=3.0, diameter=D_RELIEF),
        connection("L6", ("P1", "discharge"), ("TD1", "run_inlet"), length=5.0, diameter=D_MAIN),
        connection("L7", ("P2", "discharge"), ("TD1", "branch"), length=5.0, diameter=D_MAIN),
        connection("L8", ("TD1", "run_outlet"), ("TD2", "run_inlet"), length=5.0, diameter=D_MAIN),
        connection("L9", ("TD2", "branch"), ("RV1", "inlet"), length=3.0, diameter=D_RELIEF),
        connection("L10", ("TD2", "run_outlet"), ("R2", "port_1"), length=50.0, diameter=D_MAIN),
    ]
    return _project(comps, conns)


def deadheaded(r1_level: float, length: float, closed: str) -> dict[str, Any]:
    """``bypass_parallel`` whose bypass and delivery are both shut, so the pumps run at zero flow:
    with ``closed`` 'relief', RV1 and a second relief valve RV2 on the delivery, both set at
    600 kPa (61 m, above the shutoff head); with 'gate', isolated gate valves in their places.
    TD2's run → ``length`` → RV2 → 5 m → R2 (level 10 m)."""
    data = bypass_parallel(10.0, 600_000.0, r1_level=r1_level)
    if closed == "gate":
        data["components"] = [c if c["id"] != "RV1" else gate("RV1") for c in data["components"]]
        data["components"].append(gate("RV2"))
    else:
        data["components"].append(relief("RV2", 600_000.0))
    data["connections"] = [c for c in data["connections"] if c["id"] != "L10"]
    data["connections"] += [
        connection("L10", ("TD2", "run_outlet"), ("RV2", "inlet"), length=length, diameter=D_MAIN),
        connection("L11", ("RV2", "outlet"), ("R2", "port_1"), length=5.0, diameter=D_MAIN),
    ]
    return data


def series_between(r2_level: float = 60.0, set_pressure: float = 150_000.0) -> dict[str, Any]:
    """R1 (2 m) → P1 → RV1 → P2 → 50 m → R2: a relief valve in series between two pumps. Set at
    150 kPa (15.3 m) it relieves; at 500 kPa (51.1 m) it stays closed, since the most the first
    pump can put across it is its shutoff head plus R1's level less R2's level less the second
    pump's shutoff head."""
    comps = [
        reservoir("R1", level=2.0),
        pump("P1"),
        relief("RV1", set_pressure),
        pump("P2"),
        reservoir("R2", level=r2_level),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=5.0, diameter=D_MAIN),
        connection("L2", ("P1", "discharge"), ("RV1", "inlet"), length=3.0, diameter=D_RELIEF),
        connection("L3", ("RV1", "outlet"), ("P2", "suction"), length=3.0, diameter=D_RELIEF),
        connection("L4", ("P2", "discharge"), ("R2", "port_1"), length=50.0, diameter=D_MAIN),
    ]
    return _project(comps, conns)


def parallel_then_closed(r1_level: float = 2.0, closed: str = "relief") -> dict[str, Any]:
    """P1 and P2 in parallel from R1's two nozzles to TD1, then, outside the station, a relief
    valve RV1 (API 526 Q, set 300 kPa, 30.6 m) to R2 (level 30 m), which stays closed: the
    pumps run at zero flow. With ``closed`` 'gate', an isolated gate valve in its place."""
    comps = [
        reservoir("R1", level=r1_level, ports=("port_1", "port_2")),
        pump("P1"),
        pump("P2"),
        tee("TD1"),
        relief("RV1", 300_000.0, letter="Q") if closed == "relief" else gate("RV1"),
        reservoir("R2", level=30.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=5.0, diameter=D_MAIN),
        connection("L2", ("R1", "port_2"), ("P2", "suction"), length=5.0, diameter=D_MAIN),
        connection("L6", ("P1", "discharge"), ("TD1", "run_inlet"), length=5.0, diameter=D_MAIN),
        connection("L7", ("P2", "discharge"), ("TD1", "branch"), length=5.0, diameter=D_MAIN),
        connection("L8", ("TD1", "run_outlet"), ("RV1", "inlet"), length=5.0, diameter=D_MAIN),
        connection("L10", ("RV1", "outlet"), ("R2", "port_1"), length=50.0, diameter=D_MAIN),
    ]
    return _project(comps, conns)


def different_boundaries() -> dict[str, Any]:
    """P1 and P2 from R1's two nozzles, P1 through a relief valve RV1 to RA, P2 straight to RB:
    the pumps deliver to different reservoirs, RV1 one of the two-port elements on P1's chain."""
    comps = [
        reservoir("R1", level=2.0, ports=("port_1", "port_2")),
        pump("P1"),
        pump("P2"),
        relief("RV1", 150_000.0),
        reservoir("RA", level=10.0),
        reservoir("RB", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=5.0, diameter=D_MAIN),
        connection("L2", ("R1", "port_2"), ("P2", "suction"), length=5.0, diameter=D_MAIN),
        connection("L3", ("P1", "discharge"), ("RV1", "inlet"), length=3.0, diameter=D_RELIEF),
        connection("L4", ("RV1", "outlet"), ("RA", "port_1"), length=3.0, diameter=D_RELIEF),
        connection("L5", ("P2", "discharge"), ("RB", "port_1"), length=5.0, diameter=D_MAIN),
    ]
    return _project(comps, conns)
