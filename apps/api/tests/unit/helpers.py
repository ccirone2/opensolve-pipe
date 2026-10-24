"""Small builders for test projects (API JSON dicts validated into ``Project``)."""

from collections.abc import Sequence
from typing import Any

from opensolve_pipe.models.project import Project

Port = tuple[str, str]  # (componentId, portId)


def _ports(ids: Sequence[str], size: float = 0.1) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": size} for p in ids]


def reservoir(
    cid: str,
    *,
    elevation: float = 0.0,
    level: float = 10.0,
    surface_pressure: float = 0.0,
    ports: Sequence[str] = ("port_1",),
    port_elevation: float | None = None,
) -> dict[str, Any]:
    port_list = _ports(ports)
    if port_elevation is not None:
        for port in port_list:
            port["elevation"] = port_elevation
    return {
        "type": "reservoir",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "liquidLevel": level,
        "surfacePressure": surface_pressure,
        "ports": port_list,
    }


def reference_node(cid: str, *, pressure: float, elevation: float = 0.0) -> dict[str, Any]:
    return {
        "type": "reference_node",
        "referenceType": "ideal",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "pressure": pressure,
        "ports": _ports(["port_1"]),
    }


def plug(cid: str, *, elevation: float = 0.0) -> dict[str, Any]:
    return {
        "type": "plug",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "ports": _ports(["port_1"]),
    }


def assigned_flow(cid: str, flow: float, *, elevation: float = 0.0) -> dict[str, Any]:
    """Assigned-flow node: ``flow`` m³/s leaves the network at its port (negative: enters)."""
    return {
        "type": "assigned_flow",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "flow": flow,
        "ports": _ports(["port_1"]),
    }


def tee(cid: str, *, elevation: float = 0.0, loss_model: str = "ideal") -> dict[str, Any]:
    return {
        "type": "branch",
        "branchType": "tee",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "lossModel": loss_model,
        "ports": _ports(["run_inlet", "run_outlet", "branch"]),
    }


def custom_pipe(length: float, diameter: float, roughness: float) -> dict[str, Any]:
    return {
        "materialId": "custom",
        "length": length,
        "innerDiameter": diameter,
        "roughness": roughness,
    }


def connection(
    cid: str,
    a: Port,
    b: Port,
    *,
    length: float = 100.0,
    diameter: float = 0.1,
    roughness: float = 4.5e-5,
    pipes: list[dict[str, Any]] | None = None,
    fittings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": cid,
        "fromComponentId": a[0],
        "fromPortId": a[1],
        "toComponentId": b[0],
        "toPortId": b[1],
        "piping": {
            "pipes": pipes if pipes is not None else [custom_pipe(length, diameter, roughness)],
            "fittings": fittings or [],
        },
    }


def custom_fluid(
    density: float = 998.0, viscosity: float = 1.0e-3, vapor_pressure: float | None = None
) -> dict[str, Any]:
    fluid: dict[str, Any] = {
        "kind": "custom",
        "name": "test liquid",
        "density": density,
        "dynamicViscosity": viscosity,
    }
    if vapor_pressure is not None:
        fluid["vaporPressure"] = vapor_pressure
    return fluid


def project_dict(
    components: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    *,
    fluid: dict[str, Any] | None = None,
    method: str = "colebrook",
    tolerance: float = 1.0e-9,
    max_iterations: int = 100,
    site_elevation: float = 0.0,
    atmospheric_pressure: float | None = None,
    pump_library: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "units": {},
        "siteElevation": site_elevation,
        "solverOptions": {
            "frictionMethod": method,
            "maxIterations": max_iterations,
            "tolerance": tolerance,
        },
    }
    if atmospheric_pressure is not None:
        settings["atmosphericPressure"] = atmospheric_pressure
    return {
        "schemaVersion": 1,
        "id": "test",
        "metadata": {"name": "test", "created": "2026-10-21", "modified": "2026-10-21"},
        "settings": settings,
        "fluid": fluid or custom_fluid(),
        "components": components,
        "connections": connections,
        "pumpLibrary": pump_library or [],
    }


def make_project(
    components: list[dict[str, Any]], connections: list[dict[str, Any]], **kwargs: Any
) -> Project:
    return Project.model_validate(project_dict(components, connections, **kwargs))


def two_reservoirs(
    *, h1: float = 20.0, h2: float = 10.0, **conn: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """R1 (level h1) -- P1 --> R2 (level h2), both at elevation 0."""
    return (
        [reservoir("R1", level=h1), reservoir("R2", level=h2)],
        [connection("P1", ("R1", "port_1"), ("R2", "port_1"), **conn)],
    )
