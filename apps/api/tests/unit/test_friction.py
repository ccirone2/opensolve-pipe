"""Friction factor: laminar, EPANET 2.2 transition, Colebrook / Swamee–Jain turbulent."""

import math

import pytest
from fluids.friction import Colebrook, Swamee_Jain_1976, fmethods

from opensolve_pipe.services.solver.friction import (
    RE_LAMINAR_MAX,
    RE_TURBULENT_MIN,
    FlowRegime,
    FrictionMethod,
    colebrook,
    flow_regime,
    friction_factor,
    laminar,
    range_warning,
    swamee_jain,
    transition,
    turbulent,
)

METHODS: tuple[FrictionMethod, ...] = ("colebrook", "swamee_jain")
ROUGHNESSES = (0.0, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 5e-2)


# EPANET 2.2 src/hydcoeffs.c, constants lines 22-31 and frictionFactor() lines 623-670,
# copied verbatim (as quoted in research/coolprop_wntr_epanet.md §C.1) into Python.
A1 = 3.14159265358979323850e03  # 1000*PI
A2 = 1.57079632679489661930e03  # 500*PI
A8 = 4.61841319859066668690e00  # 5.74*(PI/4)^.9
A9 = -8.68588963806503655300e-01  # -2/ln(10)
AB = 3.28895476345399058690e-03  # 5.74/(4000^.9)
AC = -5.14214965799093883760e-03  # AA*AB


def epanet_friction_factor(q: float, e: float, s: float) -> tuple[float, float]:
    """EPANET 2.2 frictionFactor(q, e, s, &dfdq): returns (f, dfdq)."""
    w = q / s  # Re*Pi/4
    if w >= A1:
        y1 = A8 / math.pow(w, 0.9)
        y2 = e / 3.7 + y1
        y3 = A9 * math.log(y2)
        f = 1.0 / (y3 * y3)
        dfdq = 1.8 * f * y1 * A9 / y2 / y3 / q
    else:
        y2 = e / 3.7 + AB
        y3 = A9 * math.log(y2)
        fa = 1.0 / (y3 * y3)
        fb = (2.0 + AC / (y2 * y3)) * fa
        r = w / A2
        x1 = 7.0 * fa - fb
        x2 = 0.128 - 17.0 * fa + 2.5 * fb
        x3 = -0.128 + 13.0 * fa - (fb + fb)
        x4 = 0.032 - 3.0 * fa + 0.5 * fb
        f = x1 + r * (x2 + r * (x3 + r * x4))
        dfdq = (x2 + r * (2.0 * x3 + r * 3.0 * x4)) / s / A2
    return f, dfdq


def epanet_at_reynolds(re: float, ed: float) -> tuple[float, float]:
    """EPANET's f and df/dRe at a Reynolds number (s = ν·d = 1, so Re = 4q/π)."""
    q = re * math.pi / 4.0
    f, dfdq = epanet_friction_factor(q, ed, 1.0)
    return f, dfdq * math.pi / 4.0


def test_regime_labels() -> None:
    assert flow_regime(0.0) is FlowRegime.NONE
    assert flow_regime(1999.999) is FlowRegime.LAMINAR
    assert flow_regime(2000.0) is FlowRegime.TRANSITIONAL
    assert flow_regime(3999.999) is FlowRegime.TRANSITIONAL
    assert flow_regime(4000.0) is FlowRegime.TURBULENT


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("re", [1e-3, 1.0, 500.0, 1999.0])
def test_laminar_is_hagen_poiseuille(method: FrictionMethod, re: float) -> None:
    f, dfdre = friction_factor(re, 1e-3, method)
    assert f == 64.0 / re
    assert dfdre == pytest.approx(-64.0 / re**2, rel=1e-15)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("ed", ROUGHNESSES)
def test_value_and_slope_continuity_at_2000_and_4000(method: FrictionMethod, ed: float) -> None:
    """The transition cubic meets the laminar law at Re = 2000 and the turbulent formula at
    Re = 4000 in value and slope (evaluated exactly at the end points)."""
    lam_f, lam_d = laminar(RE_LAMINAR_MAX)
    assert (lam_f, lam_d) == (64.0 / RE_LAMINAR_MAX, -64.0 / RE_LAMINAR_MAX**2)
    f, d = transition(RE_LAMINAR_MAX, ed, method)
    assert f == pytest.approx(lam_f, rel=1e-13)
    assert d == pytest.approx(lam_d, rel=1e-12)

    turb_f, turb_d = turbulent(RE_TURBULENT_MIN, ed, method)
    f, d = transition(RE_TURBULENT_MIN, ed, method)
    assert f == pytest.approx(turb_f, rel=1e-13)
    assert d == pytest.approx(turb_d, rel=1e-11)

    # And friction_factor() switches between them there without a jump.
    assert friction_factor(RE_TURBULENT_MIN, ed, method) == (turb_f, turb_d)
    below = friction_factor(math.nextafter(RE_TURBULENT_MIN, 0.0), ed, method)
    assert below[0] == pytest.approx(turb_f, rel=1e-12)
    laminar_end = friction_factor(math.nextafter(RE_LAMINAR_MAX, 0.0), ed, method)
    assert laminar_end[0] == pytest.approx(lam_f, rel=1e-12)


@pytest.mark.parametrize("ed", ROUGHNESSES)
@pytest.mark.parametrize("re", [2000.0, 2001.0, 2500.0, 3000.0, 3500.0, 3999.0, 4000.0, 1e4, 1e6])
def test_swamee_jain_mode_reproduces_epanet(ed: float, re: float) -> None:
    """Transition and turbulent branches equal EPANET 2.2's frictionFactor to round-off."""
    f, d = friction_factor(re, ed, "swamee_jain")
    f_ep, d_ep = epanet_at_reynolds(re, ed)
    assert f == pytest.approx(f_ep, rel=1e-12)
    assert d == pytest.approx(d_ep, rel=1e-12)


@pytest.mark.parametrize("ed", ROUGHNESSES)
@pytest.mark.parametrize("re", [4000.0, 5000.0, 1e4, 1e5, 1e6, 1e7, 1e8])
def test_colebrook_mode_matches_fluids_colebrook(ed: float, re: float) -> None:
    assert friction_factor(re, ed, "colebrook")[0] == pytest.approx(Colebrook(re, ed), rel=1e-12)


@pytest.mark.parametrize("ed", ROUGHNESSES)
@pytest.mark.parametrize("re", [4000.0, 3e4, 1e6, 1e8])
def test_colebrook_derivative_matches_finite_difference(ed: float, re: float) -> None:
    h = re * 1e-6
    fd = (Colebrook(re + h, ed) - Colebrook(re - h, ed)) / (2 * h)
    assert colebrook(re, ed)[1] == pytest.approx(fd, rel=1e-6)


@pytest.mark.parametrize("ed", ROUGHNESSES)
@pytest.mark.parametrize("re", [4000.0, 3e4, 1e6])
def test_swamee_jain_derivative_matches_finite_difference(ed: float, re: float) -> None:
    h = re * 1e-6
    fd = (swamee_jain(re + h, ed)[0] - swamee_jain(re - h, ed)[0]) / (2 * h)
    assert swamee_jain(re, ed)[1] == pytest.approx(fd, rel=1e-6)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("re", [2100.0, 3000.0, 3900.0])
def test_transition_derivative_matches_finite_difference(method: FrictionMethod, re: float) -> None:
    h = 1e-3
    fd = (friction_factor(re + h, 1e-4, method)[0] - friction_factor(re - h, 1e-4, method)[0]) / (
        2 * h
    )
    assert friction_factor(re, 1e-4, method)[1] == pytest.approx(fd, rel=1e-6)


@pytest.mark.parametrize("ed", [1e-6, 1e-4, 1e-2, 5e-2])
@pytest.mark.parametrize("re", [5e3, 1e5, 1e8])
def test_swamee_jain_agrees_with_fluids_form(ed: float, re: float) -> None:
    """fluids writes 5.74/Re^0.9 as (6.97/Re)^0.9 (6.97^0.9 = 5.73997, 5.5e-6 lower), which
    moves f by ~2e-6 (research/coolprop_wntr_epanet.md §B.3.1); same equation otherwise."""
    assert swamee_jain(re, ed)[0] == pytest.approx(Swamee_Jain_1976(re, ed), rel=1e-5)


# --- Validated ranges (fluids 1.3.1 docstrings and fluids.friction.fmethods) ------------------
# Swamee_Jain_1976: "Range is 5E3 <= Re <= 1E8;  1E-6 <= eD <= 5E-2."
# Haaland: "Range is 4E3 <= Re <= 1E8;  1E-6 <= eD <= 5E-2". No range is given for Colebrook.
SJ_RE = (fmethods["Swamee_Jain_1976"][0], fmethods["Swamee_Jain_1976"][1])
SJ_ED = (fmethods["Swamee_Jain_1976"][2], fmethods["Swamee_Jain_1976"][3])


def test_cited_ranges_are_the_documented_ones() -> None:
    assert SJ_RE == (5.0e3, 1.0e8)
    assert SJ_ED == (1.0e-6, 5.0e-2)
    assert fmethods["Haaland"][3] == 5.0e-2


@pytest.mark.parametrize(
    ("re", "ed", "inside"),
    [
        (1.0e5, 1.0e-4, True),
        (5.0e3, 1.0e-6, True),
        (1.0e8, 5.0e-2, True),
        (4.5e3, 1.0e-4, False),  # 4000 <= Re < 5000: turbulent, below the SJ range
        (2.0e8, 1.0e-4, False),
        (1.0e5, 0.0, False),
        (1.0e5, 0.06, False),
        (1.0e5, 0.5, False),
    ],
)
def test_swamee_jain_range(re: float, ed: float, inside: bool) -> None:
    assert (range_warning(re, ed, "swamee_jain") is None) is inside


@pytest.mark.parametrize(
    ("re", "ed", "inside"),
    [
        (1.0e5, 0.0, True),
        (4.5e3, 1.0e-4, True),
        (2.0e8, 1.0e-4, True),
        (1.0e5, 5.0e-2, True),
        (1.0e5, 0.06, False),
        (2.7e4, 0.5, False),
    ],
)
def test_colebrook_roughness_range(re: float, ed: float, inside: bool) -> None:
    assert (range_warning(re, ed, "colebrook") is None) is inside


@pytest.mark.parametrize("method", METHODS)
def test_range_applies_where_the_turbulent_formula_enters(method: FrictionMethod) -> None:
    # Laminar flow does not depend on roughness; the transition interpolates towards the
    # turbulent formula at Re = 4000, so its roughness must be in range.
    assert range_warning(1000.0, 0.5, method) is None
    assert range_warning(3000.0, 0.5, method) is not None
    # The transition's Re (below the SJ range by construction) is flagged as transitional
    # flow instead.
    assert range_warning(3000.0, 1.0e-4, method) is None
