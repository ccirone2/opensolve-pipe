"""Rule (d)'s first test at the least C the law takes, through the public API
(docs/proposals/open-defects-2.md §3 A1; CLAUDE.md D6, D20).

Written from D20, TSD §4.10, open-defects-2.md §3 A1, the models and the source of fluids 1.3.1's
``C_Reader_Harris_Gallagher`` by a writer who did not read ``services/``. The plates and every
expected number are ``derivations_orifice``'s C15-C18, derived in 60-digit decimal arithmetic:
eq. (4) term by term, the least tap ratio by a log grid and golden-section refinement, and C*,
the C whose K(C)/(2gA²) is the largest double, in closed form. Each plate's C_e stands 10⁻⁶
relative from its edge (C17's window plate, 1.5×10⁻⁷), so the rounding of eq. (4) and of
K/(2gA²) in doubles cannot decide a case.

- C15 (RA): flange taps, D 0.2 m, bore 0.1 m; least r at Re_lo. Accepted at C*/r_least (1 + 10⁻⁶),
  refused at (1 − 10⁻⁶) quoting C_e r_least.
- C16 (RB): corner taps, D 0.1 m, bore 0.01 m; least r at infinite Re. Refused at C*/r(∞)
  (1 − 10⁻⁶), quoting C_e r(∞), although the C its law holds at Re_lo gives a finite K/(2gA²).
- C17 (RC): flange taps, D 21.7 mm, β 0.5525; least r near Re 46,437, inside the range. Refused in
  the window between C*/min(r(Re_lo), r(∞)) and C*/r_least, which a rule on the ends alone would
  accept; accepted at C*/r_least (1 + 10⁻⁶).
- C18 (RD, the control): C15's plate without taps, an entered C used as entered, at C*(1 ± 10⁻⁶).

The suite has no refusal format, and these plates cannot be D6 cases: every flow a head of metres
drives through K/(2gA²) ≈ 1.8×10³⁰⁸ s²/m⁵ is about 2.4×10⁻¹⁵⁴ m³/s, which the solver reports as 0,
while the suite's own-state check compares the head loss (10 m) with K v|v|/2g at the reported
flow (0). So an accepted plate is checked here for what its law fixes, within 10⁻¹² relative: C_L
held at Re_lo (the reported flow's Re_eff), its tap ratio and K(C_L). Its head and flow checks are
vacuous and say so: both heads are fixed by the reservoirs, so the plate's head loss is 10 m
whatever its law, and D6's flow floor (10⁻⁹ m³/s) is about 4×10¹⁴⁴ times the flow.
"""

import decimal
import itertools
import math
from decimal import Decimal
from typing import Any

import fluids.flow_meter
import httpx
import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.models.components import OrificeTaps
from tests.reference import derivations_orifice as do

SOLVE = "/api/v1/solve"
COEFFICIENT_RELATIVE = 1.0e-12
"""The law's own values against the exact ones: far above the doubles' rounding (~10⁻¹⁵), far
below the 10⁻⁶ that separates a case from its edge."""
TRANSCRIPTION_RELATIVE = 1.0e-13
"""The exact eq. (4) against fluids' (as ``test_rhg_transcription_equals_fluids`` pins
``element_laws``')."""
FLOW_FLOOR = 1.0e-9  # m³/s, D6
HEAD_FLOOR = 0.01  # m, D6
RELATIVE = 0.005  # D6
ACCEPTED = ("c15-accepted", "c17-accepted", "c18-accepted")
REFUSED = ("c15-refused", "c16-refused", "c17-window", "c18-refused")
TAP_SETS: tuple[OrificeTaps, ...] = ("corner", "flange", "d_and_d_2")
FLUIDS_TAPS = {"corner": "corner", "flange": "flange", "d_and_d_2": "D"}
"""The fluids ``taps`` argument of each tap set."""

_addresses = itertools.count(1)


def _post_solve(edge: do.CoefficientEdge) -> httpx.Response:
    """POST the edge's line from a client address of its own (the rate limit is per client)."""
    from opensolve_pipe.main import app

    n = next(_addresses)
    body = {
        "project": edge.project().model_dump(mode="json", exclude_none=True),
        "options": {"includeSystemCurve": False},
    }
    with TestClient(app, client=(f"10.79.{n // 256 % 256}.{n % 256}", 50000)) as client:
        response: httpx.Response = client.post(SOLVE, json=body)
    return response


def _relative(got: float | None, want: float) -> float:
    assert got is not None
    return abs(got - want) / abs(want)


# --------------------------------------------------------------------------- the derivation


@pytest.mark.parametrize("plate", [do.C15_PLATE, do.C16_PLATE, do.C17_PLATE])
@pytest.mark.parametrize("taps", TAP_SETS)
def test_the_exact_eq4_is_fluids_eq4(plate: tuple[float, float, Any], taps: OrificeTaps) -> None:
    """``ExactEq4`` (60 digits) against fluids.flow_meter.C_Reader_Harris_Gallagher, the cited
    law, on each plate at Re_lo, at C17's interior minimum, and up to 10¹², called with the mass
    flow whose Re_D is that Re (Re_D = 4ṁ/(πDμ))."""
    d_pipe, d_bore, _ = plate
    eq4 = do.ExactEq4(d_pipe, d_bore)
    rho, mu = 1000.0, 1.0e-3
    for re in (float(do.exact_re_lo(d_pipe, d_bore)), 46437.12, 1.0e6, 1.0e12):
        m = math.pi * d_pipe * mu / 4.0 * re
        theirs = fluids.flow_meter.C_Reader_Harris_Gallagher(
            d_pipe, d_bore, rho, mu, m, FLUIDS_TAPS[taps]
        )
        ours = float(eq4.c(taps, do.reynolds_powers(Decimal(re))))
        assert ours == pytest.approx(theirs, rel=TRANSCRIPTION_RELATIVE), (re, taps)


def test_the_least_ratios_fall_where_stated() -> None:
    """C15's least r is at Re_lo, C16's at infinite Re, C17's inside the range near Re 46,437,
    about 3×10⁻⁷ below both ends (the window C17 tests); r on either side of C17's minimum (Re
    ×(1 ± 10⁻³)) is above it; and C* gives K/(2gA²) equal to the largest double."""
    c15 = do.least_ratio(*do.C15_PLATE)
    c16 = do.least_ratio(*do.C16_PLATE)
    c17 = do.least_ratio(*do.C17_PLATE)
    assert c15.where == "re_lo"
    assert c15.value == c15.at_re_lo < c15.at_infinity
    assert c16.where == "infinite"
    assert c16.value == c16.at_infinity < c16.at_re_lo
    assert c17.where == "interior"
    assert c17.reynolds is not None
    assert 46437 < c17.reynolds < 46438
    eq4 = do.ExactEq4(*do.C17_PLATE[:2])
    with decimal.localcontext(do.EXACT):
        for end in (c17.at_re_lo, c17.at_infinity):
            assert Decimal("2.9e-7") < (end - c17.value) / c17.value < Decimal("3.6e-7")
        for s in (Decimal("0.999"), Decimal("1.001")):
            assert eq4.ratio("flange", do.reynolds_powers(c17.reynolds * s)) > c17.value
        for d_pipe, d_bore, _ in (do.C15_PLATE, do.C16_PLATE, do.C17_PLATE):
            star = do.c_star(d_pipe, d_bore)
            factor = do.loss_factor(d_pipe, d_bore, star) / do.LARGEST_DOUBLE
            assert abs(factor - 1) < Decimal("1e-50")


# --------------------------------------------------------------------------- through the API


@pytest.mark.parametrize("label", ACCEPTED)
def test_a_plate_just_above_its_edge_is_accepted_and_solves(label: str) -> None:
    """The accepted halves of C15, C17 and C18: HTTP 200, converged (in EDGE_MAX_ITERATIONS), and
    the plate's result holds C_L = C_e r(Re_lo) (C_e as entered without taps), r(Re_lo) and
    Re_lo, K(C_L) and the entered C as the meter's, each within 10⁻¹² of the exact values. The
    head loss and flow checks are vacuous (module docstring): the reservoirs fix the 10 m, and
    the flow, about 2.4×10⁻¹⁵⁴ m³/s, is reported as 0, within D6's floor of either."""
    edge = do.coefficient_edge(label)

    response = _post_solve(edge)

    assert response.status_code == 200, response.text
    body = response.json()
    state = body["solvedState"]
    assert body["success"] is True, state["convergence"]
    assert state["converged"] is True
    plate = state["orificeResults"]["O1"]
    assert plate["coefficientSource"] == "entered"
    assert _relative(plate["dischargeCoefficient"], float(edge.held)) <= COEFFICIENT_RELATIVE
    assert _relative(plate["lossCoefficient"], float(edge.loss_coefficient)) <= (
        COEFFICIENT_RELATIVE
    )
    lr = edge.least_ratio
    if lr is None:
        assert plate["tapCoefficientRatio"] is None
        assert plate["coefficientReynoldsNumber"] is None
        assert plate["meterDischargeCoefficient"] is None
    else:
        re_lo = float(do.exact_re_lo(edge.d_pipe, edge.d_bore))
        assert _relative(plate["tapCoefficientRatio"], float(lr.at_re_lo)) <= COEFFICIENT_RELATIVE
        assert _relative(plate["coefficientReynoldsNumber"], re_lo) <= COEFFICIENT_RELATIVE
        assert plate["meterDischargeCoefficient"] == edge.entered
    # Vacuous here (module docstring), kept so a gross failure still shows.
    assert abs(plate["headLoss"] - do.EDGE_LINE_HEAD) <= max(
        RELATIVE * do.EDGE_LINE_HEAD, HEAD_FLOOR
    )
    assert abs(plate["flow"] - float(edge.flow)) <= FLOW_FLOOR


@pytest.mark.parametrize("label", REFUSED)
def test_a_plate_below_its_edge_is_refused_quoting_its_least_coefficient(label: str) -> None:
    """The refused halves of C15 and C18, C16 and C17's window plate: HTTP 422 TOPOLOGY_ERROR
    with one issue, ORIFICE_OUT_OF_RANGE naming O1, whose message quotes the least C_L the
    plate's law takes, to 6 significant digits (C_e r_least; C_e for C18). C16's C held at Re_lo
    and C17's at both ends give finite K/(2gA²) (``derivations_orifice`` guards both)."""
    edge = do.coefficient_edge(label)
    quote = do.quoted(edge.least)

    response = _post_solve(edge)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "TOPOLOGY_ERROR"
    assert [(i["code"], i["componentIds"]) for i in body["issues"]] == [
        ("ORIFICE_OUT_OF_RANGE", ["O1"])
    ]
    assert quote in body["issues"][0]["message"], (quote, body["issues"][0]["message"])
