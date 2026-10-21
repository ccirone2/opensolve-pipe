"""REST API (SDD §5.1, design §13): POST /system-curve, system curves in /solve, GET /fluids,
and the trace in the solve response."""

import itertools
from typing import Any

import CoolProp
import pytest
from CoolProp.CoolProp import AbstractState, PropsSI
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.services.fluids import WATER_T_MAX
from opensolve_pipe.services.solver.trace import SYSTEM_CURVE_EQUATION
from tests.reference import derivations_pumps as dp

_addresses = itertools.count(1)


@pytest.fixture
def client() -> TestClient:
    """A client with its own address, so the rate limit (60 solves a minute per address) of
    the shared app never trips across tests."""
    return TestClient(app, client=(f"198.51.100.{next(_addresses)}", 50000))


def _pump_project() -> dict[str, Any]:
    """The reference case 'pump_single_pipe': R1 -> L1 -> PU1 -> L2 -> R2."""
    project: dict[str, Any] = dp.pump_single_pipe().project.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return project


def _system_curve(client: TestClient, **body: Any) -> Any:
    return client.post("/api/v1/system-curve", json={"project": _pump_project(), **body})


def test_system_curve_defaults_to_the_pump_curve_range(client: TestClient) -> None:
    response = _system_curve(client, pumpId="PU1")
    assert response.status_code == 200
    body = response.json()
    assert body["pumpId"] == "PU1"
    assert body["flowRange"] == {"min": 0.0, "max": pytest.approx(1.2 * 0.04), "unit": "m³/s"}
    points = body["points"]
    assert len(points) == 41
    assert body["converged"] == [p["converged"] for p in points] == [True] * 41
    assert points[0]["flow"] == 0.0
    assert points[-1]["flow"] == pytest.approx(1.2 * 0.04)
    heads = [p["head"] for p in points]
    assert heads[0] == pytest.approx(20.0 - 3.0, abs=1e-9)  # static head at zero flow
    assert all(b > a for a, b in itertools.pairwise(heads))  # losses grow with the flow
    assert all(p["message"] == "" for p in points)


def test_system_curve_takes_a_flow_range(client: TestClient) -> None:
    body = _system_curve(client, pumpId="PU1", flowMin=0.01, flowMax=0.02, numPoints=5).json()
    assert [p["flow"] for p in body["points"]] == pytest.approx([0.01, 0.0125, 0.015, 0.0175, 0.02])
    assert body["flowRange"]["min"] == 0.01
    assert body["flowRange"]["max"] == 0.02


def test_system_curve_errors(client: TestClient) -> None:
    for pump_id in ("NOPE", "R1"):  # unknown id, and a component that is not a pump
        response = _system_curve(client, pumpId=pump_id)
        assert response.status_code == 404
        assert response.json()["error"] == "NOT_FOUND"
    empty = _system_curve(client, pumpId="PU1", flowMin=0.05)  # default max is 0.048
    assert empty.status_code == 400
    assert empty.json()["error"] == "VALIDATION_ERROR"
    assert _system_curve(client, pumpId="PU1", flowMin=0.02, flowMax=0.01).status_code == 400
    assert _system_curve(client, pumpId="PU1", numPoints=2).status_code == 400
    broken = _pump_project()
    broken["connections"].pop()  # PU1:discharge and R2:port_1 left unconnected
    response = client.post("/api/v1/system-curve", json={"project": broken, "pumpId": "PU1"})
    assert response.status_code == 422
    assert response.json()["error"] == "TOPOLOGY_ERROR"


def test_system_curve_points_without_a_way_through_have_no_head(client: TestClient) -> None:
    """A closed (isolated) valve on the discharge line: the forced flow has nowhere to go, so
    no point has a head, and each says why."""
    project = _pump_project()
    project["components"].append(
        {
            "type": "valve",
            "valveType": "gate",
            "id": "V",
            "name": "V",
            "elevation": 18.0,
            "status": "isolated",
            "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        }
    )
    l2 = project["connections"][1]
    l3 = {**l2, "id": "L3", "fromComponentId": "V", "fromPortId": "outlet"}
    l2 |= {"toComponentId": "V", "toPortId": "inlet"}
    project["connections"].append(l3)
    body = client.post(
        "/api/v1/system-curve", json={"project": project, "pumpId": "PU1", "numPoints": 5}
    ).json()
    assert body["converged"] == [False] * 5
    assert all(p["head"] is None and "no way through" in p["message"] for p in body["points"])


def test_solve_fills_the_system_curve_of_running_pumps(client: TestClient) -> None:
    project = _pump_project()
    options = {"includeSystemCurve": True, "systemCurvePoints": 11}
    state = client.post("/api/v1/solve", json={"project": project, "options": options}).json()
    curve = state["solvedState"]["pumpResults"]["PU1"]["systemCurve"]
    reference = _system_curve(client, pumpId="PU1", numPoints=11).json()["points"]
    assert len(curve) == 11
    for got, want in zip(curve, reference, strict=True):
        assert got["flow"] == want["flow"]
        assert got["head"] == pytest.approx(want["head"], rel=1e-12, abs=1e-12)
    # The operating point lies on the system curve: H_pump(Q_op) = H_sys(Q_op).
    pump = state["solvedState"]["pumpResults"]["PU1"]
    below = max((p for p in curve if p["flow"] <= pump["operatingFlow"]), key=lambda p: p["flow"])
    above = min((p for p in curve if p["flow"] >= pump["operatingFlow"]), key=lambda p: p["flow"])
    assert below["head"] <= pump["operatingHead"] <= above["head"]
    notes = state["solvedState"]["trace"]["elements"]["PU1"]["notes"]
    assert any(n.startswith("System curve: 11 of 11 flows") for n in notes)

    equations = state["solvedState"]["trace"]["elements"]["PU1"]["equations"]
    assert [e for e in equations if e.startswith("H_sys(Q) = ")] == [SYSTEM_CURVE_EQUATION]

    off = client.post(
        "/api/v1/solve",
        json={"project": project, "options": {**options, "includeSystemCurve": False}},
    )
    assert off.json()["solvedState"]["pumpResults"]["PU1"]["systemCurve"] is None
    project["components"][1]["status"] = "off"
    stopped = client.post("/api/v1/solve", json={"project": project, "options": options}).json()
    assert stopped["solvedState"]["pumpResults"]["PU1"]["systemCurve"] is None


def test_the_pump_trace_defines_the_system_curve_when_the_solve_computes_none(
    client: TestClient,
) -> None:
    """The web app solves without system curves and fetches the shown one from
    /system-curve (D10), whose response has no trace: the pump's trace still defines the curve
    it draws (GOALS §4.2), while the note on how many points were solved comes only with a
    curve computed by the solve."""
    options = {"includeSystemCurve": False}
    state = client.post(
        "/api/v1/solve", json={"project": _pump_project(), "options": options}
    ).json()["solvedState"]
    trace = state["trace"]["elements"]["PU1"]
    assert SYSTEM_CURVE_EQUATION in trace["equations"]
    assert "POST /api/v1/system-curve" in SYSTEM_CURVE_EQUATION
    assert not any(n.startswith("System curve:") for n in trace["notes"])


def test_solve_response_carries_the_trace_and_methods(client: TestClient) -> None:
    state = client.post("/api/v1/solve", json={"project": _pump_project()}).json()["solvedState"]
    elements = state["trace"]["elements"]
    assert set(elements) == {"R1", "PU1", "R2", "L1", "L2"}
    l1 = elements["L1"]
    assert l1["elementType"] == "pipe_connection"
    assert {"inputs", "equations", "correlations", "dataSources", "intermediates", "notes"} <= set(
        l1
    )
    flow = next(v for v in l1["intermediates"] if v["name"] == "Flow Q")
    assert flow["value"] == state["linkResults"]["L1"]["flow"]
    assert flow["unit"] == "m³/s"
    assert state["trace"]["methods"]["methodVersion"] == state["methodVersion"]


def test_fluid_list_reports_coolprop_ranges(client: TestClient) -> None:
    response = client.get("/api/v1/fluids")
    assert response.status_code == 200
    fluids = {f["id"]: f for f in response.json()["fluids"]}
    assert set(fluids) == {"water", "ethylene_glycol", "propylene_glycol"}

    water = fluids["water"]
    assert water["temperatureRange"] == {
        "min": PropsSI("Ttriple", "Water"),
        "max": WATER_T_MAX,
        "unit": "K",
    }
    assert water["concentrationRange"] is None
    assert water["freezingPoints"] is None
    assert water["vaporPressureAvailable"] is True
    assert "IAPWS-95" in water["source"]

    for fid, name in (("ethylene_glycol", "MEG"), ("propylene_glycol", "MPG")):
        info = fluids[fid]
        incomp = f"INCOMP::{name}"
        assert info["concentrationRange"]["min"] == PropsSI("fraction_min", incomp)
        assert info["concentrationRange"]["max"] == PropsSI("fraction_max", incomp)
        assert info["temperatureRange"]["max"] == PropsSI("Tmax", incomp)
        assert info["vaporPressureAvailable"] is False
        assert "Melinder" in info["source"]
        points = info["freezingPoints"]
        assert points[0]["concentration"] == info["concentrationRange"]["min"]
        assert points[-1]["concentration"] == info["concentrationRange"]["max"]
        for point in points:
            state = AbstractState("INCOMP", name)
            state.set_mass_fractions([point["concentration"]])
            assert point["temperature"] == state.keyed_output(CoolProp.iT_freeze)
        lowest = min(p["temperature"] for p in points)
        assert info["temperatureRange"]["min"] == max(lowest, PropsSI("Tmin", incomp))
        assert any("freezing point" in n for n in info["notes"])


@pytest.mark.parametrize("fid", ["ethylene_glycol", "propylene_glycol"])
def test_the_freezing_point_is_the_lower_bound_at_a_concentration(
    client: TestClient, fid: str
) -> None:
    info = next(f for f in client.get("/api/v1/fluids").json()["fluids"] if f["id"] == fid)
    point = next(p for p in info["freezingPoints"] if p["concentration"] == 0.3)
    url = f"/api/v1/fluids/{fid}/properties"
    above = client.get(
        url, params={"temperature": point["temperature"] + 0.5, "concentration": 0.3}
    )
    assert above.status_code == 200
    below = client.get(
        url, params={"temperature": point["temperature"] - 0.5, "concentration": 0.3}
    )
    assert below.status_code == 400
    assert below.json()["error"] == "FLUID_ERROR"
