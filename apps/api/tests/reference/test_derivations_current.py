"""Case files must match their generators, so expected values never go stale (design §9).

Closed-form cases are re-derived (tight tolerance: same arithmetic, any platform). EPANET cases are
re-run through WNTR and must agree to float32 precision (EPANET writes REAL4 results). Regenerate
with ``python -m tests.reference.build_closed_form_cases`` or
``python -m tests.reference.generate_epanet_cases`` after an intended change.
"""

import math
from typing import Any

import pytest

from tests.reference.case_format import ReferenceCase, case_files, case_path, read_case
from tests.reference.closed_form import CLOSED_FORM_CASES

EPANET_CASE_NAMES = (
    "epanet_looped_network_a",
    "epanet_looped_network_b",
    "epanet_pump_network",
    "epanet_prv_network",
    "epanet_psv_network",
    "epanet_fcv_network",
    "epanet_pump_flow_control",
    "epanet_pump_flow_control_speed",
    "epanet_pump_flow_control_max",
    "epanet_pump_flow_control_min",
    "epanet_assigned_flow_network",
    "epanet_assigned_flow_pump_network",
    "epanet_equipment_line",
    "epanet_equipment_loop",
    "epanet_equipment_cv_line",
    "epanet_orifice_line",
    "epanet_orifice_balancing",
    "epanet_orifice_low_re",
    "epanet_relief_partial",
    "epanet_relief_full",
    "epanet_relief_near_set",
)
DERIVATION_REL = 1.0e-10
EPANET_REL = 8 * 2.0**-23  # a few float32 ulps


def _assert_same_numbers(stored: Any, fresh: Any, rel: float, path: str = "expected") -> None:
    if isinstance(fresh, dict):
        assert isinstance(stored, dict), path
        assert stored.keys() == fresh.keys(), path
        for key in fresh:
            _assert_same_numbers(stored[key], fresh[key], rel, f"{path}.{key}")
    elif isinstance(fresh, list):
        assert isinstance(stored, list), path
        assert len(stored) == len(fresh), path
        for i, (a, b) in enumerate(zip(stored, fresh, strict=True)):
            _assert_same_numbers(a, b, rel, f"{path}[{i}]")
    elif isinstance(fresh, float):
        assert isinstance(stored, int | float), path
        assert math.isclose(stored, fresh, rel_tol=rel, abs_tol=1.0e-15), (
            f"{path}: stored {stored!r}, fresh {fresh!r}"
        )
    else:
        assert stored == fresh, path


def _assert_current(case: ReferenceCase, rel: float) -> None:
    stored = read_case(case_path(case.name))
    fresh = case.to_json()
    assert stored.keys() == fresh.keys()
    for key in ("name", "description", "source", "project"):
        assert stored[key] == fresh[key], f"{case.name}: '{key}' is stale"
    _assert_same_numbers(stored["expected"], fresh["expected"], rel)


def test_every_case_file_has_a_generator() -> None:
    generated = {derive.__name__ for derive in CLOSED_FORM_CASES} | set(EPANET_CASE_NAMES)
    assert {p.stem for p in case_files()} == generated


@pytest.mark.parametrize("derive", CLOSED_FORM_CASES, ids=lambda f: f.__name__)
def test_closed_form_case_is_current(derive: Any) -> None:
    case = derive()
    assert case.name == derive.__name__
    _assert_current(case, DERIVATION_REL)


@pytest.mark.parametrize("name", EPANET_CASE_NAMES)
def test_epanet_case_is_current(name: str) -> None:
    # WNTR is a dev dependency, so this runs in CI; skip only where it is not installed.
    pytest.importorskip("wntr")
    from tests.reference.generate_epanet_cases import EPANET_NETWORKS, build_case

    assert set(EPANET_NETWORKS) == set(EPANET_CASE_NAMES)
    _assert_current(build_case(name), EPANET_REL)
