"""Request-validation locations under a valve's resistance (CLAUDE.md D22). The resistance is a
union of an inline coefficient and a project library reference, and pydantic puts the union's
tag in every location under it; the API leaves it out (main._without_resistance_tag, with the
tags services/scenarios drops from a scenario value's location). So an invalid inline value is
reported exactly as before the union, byte for byte, and a reference's id at ``resistance.id``.
An equipment rating keeps its tag, as it always has."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import _without_resistance_tag, app

from .helpers import connection, project_dict, reservoir

_clients = iter(range(1, 250))

VALVES: dict[str, dict[str, Any]] = {
    "isolation": {"type": "valve", "valveType": "gate"},
    "check": {"type": "valve", "valveType": "check"},
    "control": {"type": "valve", "valveType": "fcv", "setpoint": 0.01},
}


def _client() -> TestClient:
    return TestClient(app, client=(f"198.51.107.{next(_clients)}", 50000))


def _project(element: dict[str, Any]) -> dict[str, Any]:
    """R1 -- P1 --> V1 -- P2 --> R2, V1 the element given (component index 1)."""
    v1 = {
        **element,
        "id": "V1",
        "name": "V1",
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }
    return project_dict(
        [reservoir("R1", level=20.0), v1, reservoir("R2", level=10.0)],
        [
            connection("P1", ("R1", "port_1"), ("V1", "inlet"), length=10.0),
            connection("P2", ("V1", "outlet"), ("R2", "port_1"), length=10.0),
        ],
    )


def _body(code: str, message: str) -> bytes:
    """A 400 VALIDATION_ERROR body with one issue, as the API writes it."""
    return (
        '{"success":false,"error":"VALIDATION_ERROR","message":"Invalid input: 1 problem(s).",'
        f'"issues":[{{"code":"{code}","message":"{message}","componentIds":[],'
        '"connectionIds":[]}]}'
    ).encode()


# The bodies 2723d3c (before the union) returned, each checked against that commit's API.
INLINE = [
    ({"kind": "K", "value": 0}, "greater_than", "value: Input should be greater than 0"),
    (
        {"kind": "Cv", "value": 2.0e7},
        "less_than_equal",
        "value: Input should be less than or equal to 10000000",
    ),
    ({"kind": "Kv"}, "missing", "value: Field required"),
    (
        {"kind": "Kv", "value": "abc"},
        "float_parsing",
        "value: Input should be a valid number, unable to parse string as a number",
    ),
    (
        {"kind": "K", "value": 1.0, "SECRET9x7": 2},
        "extra_forbidden",
        "(unknown field): Extra inputs are not permitted",
    ),
]


@pytest.mark.parametrize("family", list(VALVES))
@pytest.mark.parametrize(("resistance", "code", "tail"), INLINE)
def test_an_invalid_inline_resistance_is_located_as_before_the_union(
    family: str, resistance: dict[str, Any], code: str, tail: str
) -> None:
    project = _project({**VALVES[family], "resistance": resistance})
    message = f"body.project.components.1.valve:{family}.resistance.{tail}"
    for path, body in (
        ("/api/v1/solve", {"project": project}),
        ("/api/v1/system-curve", {"project": project, "pumpId": "PU1"}),
    ):
        response = _client().post(path, json=body)
        assert response.status_code == 400
        assert response.content == _body(code, message)
        assert "SECRET9x7" not in response.text


@pytest.mark.parametrize(
    ("reference", "code", "tail"),
    [
        ({"kind": "library", "id": ""}, "string_too_short", "id: String should have at least 1"),
        ({"kind": "library"}, "missing", "id: Field required"),
        ({"kind": "library", "id": "R S1"}, "string_pattern_mismatch", "id: String should match"),
        (
            {"kind": "library", "id": "RS1", "SECRET9x7": 1},
            "extra_forbidden",
            "(unknown field): Extra inputs are not permitted",
        ),
    ],
)
def test_an_invalid_library_reference_is_located_at_its_own_field(
    reference: dict[str, Any], code: str, tail: str
) -> None:
    response = _client().post(
        "/api/v1/solve", json={"project": _project({**VALVES["check"], "resistance": reference})}
    )
    assert response.status_code == 400
    [issue] = response.json()["issues"]
    assert issue["code"] == code
    assert issue["message"].startswith(f"body.project.components.1.valve:check.resistance.{tail}")
    assert "SECRET9x7" not in response.text


def test_an_equipment_rating_keeps_its_tag() -> None:
    project = _project({"type": "equipment", "rating": {"kind": "Cv", "value": 0}})
    response = _client().post("/api/v1/solve", json={"project": project})
    assert response.status_code == 400
    assert response.content == _body(
        "greater_than",
        "body.project.components.1.equipment.rating.coefficient.value: Input should be greater "
        "than 0",
    )


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        (
            ("body", "project", "components", 3, "valve:control", "resistance", "coefficient"),
            ["body", "project", "components", 3, "valve:control", "resistance"],
        ),
        (
            ("body", "project", "components", 0, "valve:check", "resistance", "library", "id"),
            ["body", "project", "components", 0, "valve:check", "resistance", "id"],
        ),
        # Not a valve's resistance: unchanged.
        (
            ("body", "project", "components", 0, "equipment", "rating", "coefficient", "value"),
            ["body", "project", "components", 0, "equipment", "rating", "coefficient", "value"],
        ),
        (
            ("body", "project", "components", 0, "valve:check", "resistance", "kind"),
            ["body", "project", "components", 0, "valve:check", "resistance", "kind"],
        ),
        (
            ("body", "project", "scenarios", 0, "overrides", 2, "value"),
            ["body", "project", "scenarios", 0, "overrides", 2, "value"],
        ),
    ],
)
def test_only_a_valve_resistances_tag_is_left_out(
    loc: tuple[str | int, ...], expected: list[str | int]
) -> None:
    assert _without_resistance_tag(loc) == expected
