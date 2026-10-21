"""Darcy friction factor f(Re, ε/D) for every flow regime, with its derivative df/dRe.

- Laminar, Re < 2000: Hagen–Poiseuille, f = 64/Re. For fully developed laminar flow the
  velocity profile is parabolic and Δp = 32 μ L v / D²; equating with Δp = f (L/D) ρ v²/2
  gives f = 64 μ/(ρ v D) = 64/Re. The 2000 threshold is EPANET 2.2's (``hydcoeffs.c`` line
  600: laminar when q <= A2·s with A2 = 500π, i.e. Re <= 2000), not fluids' 2040.
- Turbulent, Re >= 4000 (EPANET 2.2 ``hydcoeffs.c`` line 644: w >= A1 with A1 = 1000π):
  ``colebrook``: the Colebrook (1939) equation, solved exactly with
  ``fluids.friction.Clamond`` (Clamond 2009). ``swamee_jain``: the Swamee & Jain (1976)
  explicit approximation in the exact form EPANET 2.2 evaluates (``hydcoeffs.c`` lines 22-31
  and 644-651), so that EPANET comparisons test the network algorithm, not the friction
  formula.
- Transition, 2000 <= Re < 4000: the cubic Hermite interpolation in R = Re/2000 between the
  laminar value and slope at Re = 2000 and the turbulent formula's value and slope at
  Re = 4000. This is EPANET 2.2's Dunlop interpolating polynomial (``hydcoeffs.c`` lines
  653-667), written in Hermite form; with ``swamee_jain`` it reproduces EPANET's polynomial
  (unit-tested against the source).

Never use ``fluids.friction.friction_factor`` here: it switches hard to 64/Re at Re = 2040.

Validated ranges (``range_warning``, flagged CORRELATION_OUT_OF_RANGE): ``swamee_jain`` is
documented for 5e3 <= Re <= 1e8 and 1e-6 <= ε/D <= 5e-2 (fluids ``Swamee_Jain_1976``
docstring, ``fluids.friction.fmethods``). fluids gives no range for the Colebrook equation;
its explicit approximations Swamee–Jain and Haaland (fitted to it) are documented up to
ε/D = 5e-2, so ``colebrook`` flags ε/D beyond that. ε/D >= 3.7 has no Colebrook solution at all
(``COLEBROOK_ED_LIMIT``) and is rejected as input by the builder.

References: Colebrook, C. F., J. ICE 11(4), 1939, 133-156, doi:10.1680/ijoti.1939.13150.
Clamond, D., Ind. Eng. Chem. Res. 48(7), 2009, 3665-3671, doi:10.1021/ie801626g.
Swamee, P. K., and A. K. Jain, J. Hydraulics Div. ASCE 102(5), 1976, 657-664.
Rossman, L. A., et al., EPANET 2.2 (US EPA, 2020), src/hydcoeffs.c (frictionFactor).
"""

import math
from enum import StrEnum
from typing import Literal

from fluids.friction import Clamond, fmethods

FrictionMethod = Literal["colebrook", "swamee_jain"]

RE_LAMINAR_MAX = 2000.0
"""Upper Reynolds number of the laminar law (EPANET 2.2 hydcoeffs.c:600, A2 = 500π)."""
RE_TURBULENT_MIN = 4000.0
"""Lower Reynolds number of the turbulent formulas (EPANET 2.2 hydcoeffs.c:644, A1 = 1000π)."""
LAMINAR_F_RE = 64.0
"""f·Re in fully developed laminar pipe flow (Hagen–Poiseuille, derived in the module docstring)."""

_LN10 = math.log(10.0)

COLEBROOK_ED_LIMIT = 3.7
"""ε/D at and above which the Colebrook equation has no solution. Written as the fluids
``Colebrook`` docstring gives it, with x = 1/√f > 0: x = −2 log10(ε/D/3.7 + 2.51 x/Re). The
right side is positive only while the log argument is below 1, and the 2.51 x/Re term vanishes
only as f → ∞ (x → 0), so a root exists exactly when ε/D/3.7 < 1."""


def _documented_range(method: str) -> tuple[float, float, float, float]:
    """(Re min, Re max, ε/D min, ε/D max) of a fluids correlation (``fluids.friction.fmethods``)."""
    bounds = fmethods[method]
    if any(b is None for b in bounds):
        raise ValueError(f"fluids documents no complete range for {method}")
    re_lo, re_hi, ed_lo, ed_hi = (float(b) for b in bounds if b is not None)
    return re_lo, re_hi, ed_lo, ed_hi


_SJ = _documented_range("Swamee_Jain_1976")
SWAMEE_JAIN_RE_RANGE = (_SJ[0], _SJ[1])
"""Documented Reynolds number range of Swamee & Jain (1976): "Range is 5E3 <= Re <= 1E8"
(fluids ``Swamee_Jain_1976`` docstring; ``fluids.friction.fmethods``)."""
SWAMEE_JAIN_ED_RANGE = (_SJ[2], _SJ[3])
"""Documented relative roughness range of Swamee & Jain (1976): "1E-6 <= eD <= 5E-2"."""
COLEBROOK_ED_DOCUMENTED_MAX = max(_SJ[3], _documented_range("Haaland")[3])
"""Largest ε/D in the documented ranges of fluids' explicit Colebrook approximations,
Swamee_Jain_1976 and Haaland (both 5e-2; fluids.friction.fmethods, after Winning & Coole,
Flow Turbulence Combust. 90, 2013, 1-27). fluids documents no range for Colebrook itself."""


class FlowRegime(StrEnum):
    NONE = "none"
    LAMINAR = "laminar"
    TRANSITIONAL = "transitional"
    TURBULENT = "turbulent"


def flow_regime(re: float) -> FlowRegime:
    """Regime label for a Reynolds number (0 means no flow)."""
    if re <= 0.0:
        return FlowRegime.NONE
    if re < RE_LAMINAR_MAX:
        return FlowRegime.LAMINAR
    if re < RE_TURBULENT_MIN:
        return FlowRegime.TRANSITIONAL
    return FlowRegime.TURBULENT


def laminar(re: float) -> tuple[float, float]:
    """f = 64/Re and df/dRe."""
    f = LAMINAR_F_RE / re
    return f, -f / re


def colebrook(re: float, ed: float) -> tuple[float, float]:
    """Exact Colebrook friction factor (``fluids.friction.Clamond``) and df/dRe.

    The derivative is implicit differentiation of the Colebrook equation exactly as the
    fluids docstring writes it, 1/√f = −2 log10(ε/D/3.7 + 2.51/(Re √f)). With x = 1/√f,
    a = ε/D/3.7 and b = 2.51/Re: x = −(2/ln10) ln(a + b x), so
    dx/dRe = [2 b x / (ln10 · Re · (a + b x))] / [1 + 2 b / (ln10 · (a + b x))] and
    df/dRe = −2 x⁻³ dx/dRe. (Unit-tested against a finite difference of
    ``fluids.friction.Colebrook``.)
    """
    f = float(Clamond(re, ed))
    x = 1.0 / math.sqrt(f)
    b = 2.51 / re
    s = ed / 3.7 + b * x
    dx_dre = (2.0 * b * x / (_LN10 * re * s)) / (1.0 + 2.0 * b / (_LN10 * s))
    return f, -2.0 * dx_dre / x**3


def swamee_jain(re: float, ed: float) -> tuple[float, float]:
    """Swamee–Jain friction factor and df/dRe in EPANET 2.2's form.

    EPANET 2.2 ``hydcoeffs.c`` lines 644-650, with w = Re·π/4 and A8 = 5.74·(π/4)^0.9 so that
    A8/w^0.9 = 5.74/Re^0.9, and A9 = −2/ln10::

        y1 = 5.74 / Re^0.9;  y2 = ε/D / 3.7 + y1;  y3 = A9 ln(y2);  f = 1 / y3²
        df/dRe = 1.8 f y1 A9 / (y2 y3 Re)

    (EPANET's dfdq = 1.8 f y1 A9 / y2 / y3 / q, and Re ∝ q.) fluids'
    ``Swamee_Jain_1976`` writes the same equation with (6.97/Re)^0.9, i.e. 5.73997 for 5.74,
    which differs from EPANET by about 2e-6 in f; this form matches EPANET exactly.
    """
    y1 = 5.74 / re**0.9
    y2 = ed / 3.7 + y1
    y3 = -2.0 / _LN10 * math.log(y2)
    f = 1.0 / (y3 * y3)
    return f, 1.8 * f * y1 * (-2.0 / _LN10) / (y2 * y3 * re)


def turbulent(re: float, ed: float, method: FrictionMethod) -> tuple[float, float]:
    return colebrook(re, ed) if method == "colebrook" else swamee_jain(re, ed)


def transition(re: float, ed: float, method: FrictionMethod) -> tuple[float, float]:
    """Hermite cubic in R = Re/2000 on [1, 2] (EPANET 2.2 Dunlop polynomial) and df/dRe.

    End conditions: at R = 1, f = 64/2000 and df/dR = −64/2000 (the laminar law); at R = 2,
    the turbulent formula's f and df/dR = 2000·df/dRe at Re = 4000.
    """
    f1, d1 = laminar(RE_LAMINAR_MAX)
    f2, d2 = turbulent(RE_TURBULENT_MIN, ed, method)
    s1, s2 = d1 * RE_LAMINAR_MAX, d2 * RE_LAMINAR_MAX  # slopes in R
    t = re / RE_LAMINAR_MAX - 1.0
    t2, t3 = t * t, t * t * t
    f = (
        (2 * t3 - 3 * t2 + 1) * f1
        + (t3 - 2 * t2 + t) * s1
        + (-2 * t3 + 3 * t2) * f2
        + (t3 - t2) * s2
    )
    df_dt = (
        (6 * t2 - 6 * t) * f1
        + (3 * t2 - 4 * t + 1) * s1
        + (-6 * t2 + 6 * t) * f2
        + (3 * t2 - 2 * t) * s2
    )
    return f, df_dt / RE_LAMINAR_MAX


def friction_factor(re: float, ed: float, method: FrictionMethod) -> tuple[float, float]:
    """Darcy friction factor and df/dRe for Re > 0 in any regime."""
    if re < RE_LAMINAR_MAX:
        return laminar(re)
    if re < RE_TURBULENT_MIN:
        return transition(re, ed, method)
    return turbulent(re, ed, method)


def range_warning(re: float, ed: float, method: FrictionMethod) -> str | None:
    """Why the friction inputs leave the cited range of the formula in use, or None.

    Laminar flow (64/Re) does not depend on ε/D. In the transition the turbulent formula enters
    through its value at Re = 4000, so ε/D is checked there; the transition's Re is flagged as
    TRANSITIONAL_FLOW instead. In turbulent flow ``swamee_jain`` is also checked against its
    documented Re range.
    """
    if re < RE_LAMINAR_MAX:
        return None
    if method == "colebrook":
        if ed > COLEBROOK_ED_DOCUMENTED_MAX:
            return (
                f"relative roughness ε/D = {ed:.4g} is above {COLEBROOK_ED_DOCUMENTED_MAX:g}, "
                "the upper end of the ranges fluids documents for the explicit approximations "
                "of the Colebrook equation (Swamee_Jain_1976, Haaland); no cited source covers "
                "the Colebrook friction factor there"
            )
        return None
    (re_lo, re_hi), (ed_lo, ed_hi) = SWAMEE_JAIN_RE_RANGE, SWAMEE_JAIN_ED_RANGE
    problems = []
    if re >= RE_TURBULENT_MIN and not re_lo <= re <= re_hi:
        problems.append(f"Re = {re:.4g}")
    if not ed_lo <= ed <= ed_hi:
        problems.append(f"ε/D = {ed:.4g}")
    if not problems:
        return None
    return (
        f"{' and '.join(problems)} {'is' if len(problems) == 1 else 'are'} outside the "
        "documented range of Swamee & Jain (1976), "
        f"{re_lo:g} <= Re <= {re_hi:g} and {ed_lo:g} <= ε/D <= {ed_hi:g} "
        "(fluids.friction.Swamee_Jain_1976)"
    )
