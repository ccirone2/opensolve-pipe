"""A loss coefficient K on a bore, from a coefficient as entered.

- ``k_from_coefficient``: a K, Cv or Kv entered on a valve, an equipment item's Cv or Kv rating
  and a project library entry's Cv or Kv: K as entered; Cv → ``fluids.fittings.Cv_to_K(Cv, D)``;
  Kv → ``fluids.fittings.Kv_to_K(Kv, D)``. fluids implements ISA-75.01.01-2007 (60534-2-1 Mod):
  Kv is m³/h of water at 1 bar, Cv US gpm of water at 1 psi, water at 999.29744568 kg/m³
  (60 °F, IAPWS-95), K = 1.6e9 D⁴/Kv² with D in m and Kv = Cv/1.1560992283536566 (the
  derivation from the definitions is unit-tested).
- ``k_at_bore``: a K stated at a bore d₀ used on a bore D, K = K₀ (D/d₀)⁴, the same head loss
  at a given flow (K₀ (Q/A₀)²/2g on either basis, proposal project-library.md §3.3); exactly K₀
  when D = d₀. Cv_to_K scales the same way: its K at two bores differ by (D/d₀)⁴ (P3).

It has no other solver import, so valves, fittings and the project library all convert through
it.

It also holds the bound every quadratic loss law's slope sets on its coefficient
(``SLOPE_COEFFICIENT_MAX``), which the topology issues VALVE_RESISTANCE_OUT_OF_RANGE,
FITTING_RESISTANCE_OUT_OF_RANGE, EQUIPMENT_RATING_OUT_OF_RANGE and ORIFICE_OUT_OF_RANGE apply.
"""

import math
import sys

import fluids.fittings

from ...models.components import FlowCoefficient


def k_from_coefficient(resistance: FlowCoefficient, d_ref: float) -> tuple[float, str]:
    """K on d_ref from a K, Cv or Kv as entered, and how it was obtained."""
    if resistance.kind == "K":
        return resistance.value, "user K"
    if resistance.kind == "Cv":
        k = float(fluids.fittings.Cv_to_K(resistance.value, d_ref))
        return k, (
            f"Cv = {resistance.value:g} (US gpm at 1 psi) converted with "
            f"fluids.fittings.Cv_to_K(Cv, D={d_ref:g} m) (ISA-75.01.01-2007)"
        )
    k = float(fluids.fittings.Kv_to_K(resistance.value, d_ref))
    return k, (
        f"Kv = {resistance.value:g} (m³/h at 1 bar) converted with "
        f"fluids.fittings.Kv_to_K(Kv, D={d_ref:g} m) (ISA-75.01.01-2007)"
    )


def k_at_bore(k0: float, d0: float, d: float) -> float:
    """K₀, stated at bore d₀, on bore d: K₀ (d/d₀)⁴ (module docstring). d = d₀ gives K₀ exactly
    ((d/d₀)⁴ = 1.0). Raises OverflowError where the power exceeds the largest double."""
    return k0 * (d / d0) ** 4


SLOPE_COEFFICIENT_MAX = sys.float_info.max / 2.0
"""The largest loss coefficient c whose law has a slope (8.988465674311579e307, half the
largest double, exactly: halving only lowers the exponent). The quadratic loss laws write their
slope dh/dQ = 2c|Q| as (2c)·|Q|, forming 2c first: a valve's 2.0 · K/(2 g A²)
(``elements.ValveLaw``), an equipment item's 2.0 · c (``elements.QuadraticLossLaw``), a pipe
connection's 2.0 · Σ n K/(2 g A²) of its fittings for the flow's direction
(``elements.PipeConnectionLaw``), and an orifice plate's 2.0 · K before its 1/(2 g A²)
(``orifice.OrificeLaw``, so there c is the dimensionless K). Doubling a double is exact unless
it overflows, so 2c is finite exactly when c ≤ SLOPE_COEFFICIENT_MAX; above it the slope is +inf
at every flow but zero and NaN at zero flow (inf · 0), and the GGA stops at the first iterate
that evaluates the law (``gga.DIVERGED``: a slope must be a finite number). So the element is
refused before the solve, named, as one whose c is not a finite number is: its law cannot be
evaluated at any flow (an orifice plate's at any flow but zero), whatever the network, the
starting flows or the iteration limit. An orifice plate's K varies with its C, so the plate is
refused on its K at an upper bound of every C its law takes (``orifice.refusal`` rule (d), a
lower bound of every K it takes); that bound need not be reached, so a plate whose K is past
the bound only at the C its law takes, at some flows or at every flow, is not refused but named
at the iterate that evaluates it (D7, D20). Every c up to the bound is evaluated: from 1 ft/s,
Newton halves the flow at each step towards √(ΔH/c), so a valve, a fitting or an equipment item
of c = 8.988465674311578e307 converged in 505 iterations (within ``maxIterations``' 1000), and
one just above it failed at the first (the item-2 verification of 2026-11-03). The test is
monotone in c, as c is in each value it comes from, like the finiteness tests it extends; so an
orifice plate's builds at a goal-seek variable's bounds still prove every trial between them."""


def slope_overflows(coefficient: float) -> bool:
    """True when the slope factor 2c of a finite c is not a finite double: c above
    ``SLOPE_COEFFICIENT_MAX``, tested as the laws form it."""
    return math.isfinite(coefficient) and not math.isfinite(2.0 * coefficient)


def slope_bound_words(coefficient: float) -> tuple[str, str]:
    """A coefficient above ``SLOPE_COEFFICIENT_MAX`` and the bound, as a refusal quotes them: 6
    significant digits, or as many more (up to 17, enough for any two doubles) as tell them
    apart."""
    digits = 6
    while digits < 17 and f"{coefficient:.{digits}g}" == f"{SLOPE_COEFFICIENT_MAX:.{digits}g}":
        digits += 1
    return f"{coefficient:.{digits}g}", f"{SLOPE_COEFFICIENT_MAX:.{digits}g}"


def slope_bound_text(coefficient: float, symbol: str, unit: str, slope: str) -> str:
    """The words of a refusal at ``SLOPE_COEFFICIENT_MAX``, "a loss coefficient K/(2 g A²) of
    1.68603e+308 s²/m⁵, above 8.98847e+307 s²/m⁵, half the largest floating-point number, so
    the slope of its head loss, 2 K/(2 g A²) |Q|, is not a finite floating-point number at any
    flow", for ``symbol`` "K/(2 g A²)", ``unit`` "s²/m⁵" (empty for none) and ``slope`` the
    words naming the slope ("the slope of its head loss, 2 K/(2 g A²) |Q|")."""
    value, bound = slope_bound_words(coefficient)
    after = f" {unit}" if unit else ""
    return (
        f"a loss coefficient {symbol} of {value}{after}, above {bound}{after}, half the largest "
        f"floating-point number, so {slope}, is not a finite floating-point number at any flow"
    )
