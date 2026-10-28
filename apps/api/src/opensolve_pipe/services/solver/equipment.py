"""Equipment: a loss from a datasheet rating (proposal equipment-pressure-drop.md §3.1, §3.4).

The element's law is h = EGL_inlet − EGL_outlet = c Q|Q| (``elements.QuadraticLossLaw``), with
c computed once from its rating, in this order:

- a rated point, the datasheet's pressure drop ΔP_r at the rated flow Q_r for a fluid of
  density ρ_r: h_r = ΔP_r/(ρ_r g), then c = h_r/Q_r², so h(Q_r) = h_r and the pressure loss at
  the operating density ρ is ρ g h = ΔP_r (ρ/ρ_r)(Q/Q_r)|Q/Q_r|: the square law of
  ISA-75.01.01-2007 eq. (1) for non-choked, turbulent liquid flow at constant C, and the
  high-Re limit of Darby's 3-K method (a constant K);
- a Cv or Kv, a rated point on water by definition (1 psi at Cv US gpm, 1 bar at Kv m³/h):
  c = K/(2 g A²) with K = ``coefficients.k_from_coefficient(rating, 1 m)`` (fluids'
  ``Cv_to_K`` / ``Kv_to_K``, K = 1.6e9 D⁴/Kv², Kv = Cv/1.1560992283536566) and A = π (1 m)²/4.
  K ∝ D⁴ ∝ A², so K/(2 g A²) is the same on every bore and a Cv or Kv needs no pipe: the 1 m
  bore's c equals a valve's (K on its inlet bore, then ``ValveLaw``'s K/(2 g A²)) to round-off,
  not bit for bit (proposal §3.1: at most 6 ulp over 300,000 draws). Its equivalent rated point
  is ΔP₁ = 1 psi (1 bar) at Q₁ = Cv US gpm (Kv m³/h) on water of density
  ρ_w = ΔP₁/(g c Q₁²), computed from that c, so no fluids constant is copied here: fluids'
  999.29744568 kg/m³ (60 °F, IAPWS-95) comes out of its conversion.

The operating density cancels out of the head law; it only converts head to pressure. A
computation that divides by zero or overflows inside the schema's bounds (ρ_r = Q_r = 1e-300, a
Cv of 1e-170) raises here; ``builder._unrepresentable_equipment`` reports it as the topology
issue EQUIPMENT_RATING_OUT_OF_RANGE, with a c that is not a finite positive double.
"""

import math
from dataclasses import dataclass
from typing import Literal

from fluids.constants import bar, gallon, hour, minute, psi

from ...models.components import Equipment, RatedFlowCoefficient, RatedPoint
from .coefficients import k_from_coefficient

UNIT_BORE = 1.0
"""m: the bore a Cv's or Kv's K is evaluated on; any bore gives the same c (module docstring)."""

COEFFICIENT_POINT: dict[str, tuple[float, float, str, str]] = {
    "Cv": (psi, gallon / minute, "1 psi", "US gpm"),
    "Kv": (bar, 1.0 / hour, "1 bar", "m³/h"),
}
"""A flow coefficient's definition as a rated point on water: (ΔP₁ in Pa, m³/s per unit of the
coefficient, ΔP₁ in words, the coefficient's flow unit). psi, gallon, minute, bar and hour are
fluids.constants' (scipy.constants'), the units fluids' Cv_to_K and Kv_to_K are defined in."""

COEFFICIENT_UNITS = {"Cv": "US gpm/psi^0.5", "Kv": "m³/h/bar^0.5"}
"""A coefficient's unit as entered, as a valve's trace writes it."""

LAW = (
    "Constant-K square law with density scaling: the form of ISA-75.01.01-2007 eq. (1) for "
    "non-choked, turbulent liquid flow. A constant K is the high-Re limit of the 3-K method "
    "(Silverberg & Darby 1999)."
)
"""The correlation an element's trace names (proposal §4.1)."""

RATING_SOURCE = "user data (equipment datasheet)"
"""Where a rating comes from (proposal §4.1)."""

COEFFICIENT_SOURCE = (
    "fluids.fittings.Cv_to_K / Kv_to_K (ISA-75.01.01-2007), water at 999.29744568 kg/m³ (60 °F, "
    "IAPWS-95, the fluids docstring), via valves.k_from_coefficient, as a valve's Cv or Kv"
)
"""The conversion a Cv or Kv rating uses, as a valve's trace cites it (D9)."""

EquipmentRatingModel = RatedPoint | RatedFlowCoefficient


@dataclass(frozen=True)
class EquipmentLaw:
    """An element's loss coefficient c and the rated point it comes from."""

    kind: Literal["point", "Cv", "Kv"]
    coefficient: float
    """c, s²/m⁵: h = c Q|Q|."""
    rated_pressure: float
    """ΔP_r, Pa (a difference); for a Cv or Kv its ΔP₁, 1 psi or 1 bar."""
    rated_flow: float
    """Q_r, m³/s; for a Cv or Kv its Q₁, Cv US gpm or Kv m³/h in m³/s."""
    rated_head: float
    """h_r = ΔP_r/(ρ_r g), m; for a Cv or Kv c Q₁², the head of its rated point."""
    rating_density: float
    """ρ_r, kg/m³; for a Cv or Kv ρ_w = ΔP₁/(g c Q₁²), the water of its definition."""
    source: str
    """How c was obtained, for the trace."""

    def head(self, flow: float) -> float:
        """c Q|Q|, m: the law's head loss at ``flow`` (inlet -> outlet)."""
        return self.coefficient * flow * abs(flow)


def equipment_law(rating: EquipmentRatingModel, g: float) -> EquipmentLaw:
    """The element's c and rated point (module docstring). Raises ZeroDivisionError or
    OverflowError where the computation does (``builder._unrepresentable_equipment``)."""
    if isinstance(rating, RatedPoint):
        rated_head = rating.pressure_loss / (rating.density * g)
        c = rated_head / (rating.flow * rating.flow)
        return EquipmentLaw(
            kind="point",
            coefficient=c,
            rated_pressure=rating.pressure_loss,
            rated_flow=rating.flow,
            rated_head=rated_head,
            rating_density=rating.density,
            source=(
                f"{RATING_SOURCE}: rated pressure drop ΔP_r, rated flow Q_r and rated fluid "
                "density ρ_r as entered; h_r = ΔP_r/(ρ_r g), c = h_r/Q_r²"
            ),
        )
    k, how = k_from_coefficient(rating, UNIT_BORE)
    area = 0.25 * math.pi * UNIT_BORE * UNIT_BORE
    c = k / (2.0 * g * area * area)
    dp1, per_unit, _, _ = COEFFICIENT_POINT[rating.kind]
    q1 = rating.value * per_unit
    rated_head = c * q1 * q1
    return EquipmentLaw(
        kind=rating.kind,
        coefficient=c,
        rated_pressure=dp1,
        rated_flow=q1,
        rated_head=rated_head,
        rating_density=dp1 / (g * rated_head),
        source=f"{how}; c = K/(2 g A²) with A = π D²/4 at D = {UNIT_BORE:g} m",
    )


def unrepresentable(component: Equipment, g: float) -> bool:
    """True when the element's c is not a finite positive double, or computing it divides by
    zero or overflows (proposal decision 10)."""
    try:
        c = equipment_law(component.rating, g).coefficient
    except (ZeroDivisionError, OverflowError):
        return True
    return not (math.isfinite(c) and c > 0.0)


def rating_text(rating: EquipmentRatingModel) -> str:
    """The rating as entered, SI, for messages: '50000 Pa at 0.015 m³/s for a fluid of 999.1
    kg/m³', or 'Cv 90'."""
    if isinstance(rating, RatedPoint):
        return (
            f"{rating.pressure_loss:g} Pa at {rating.flow:g} m³/s for a fluid of "
            f"{rating.density:g} kg/m³"
        )
    return f"{rating.kind} {rating.value:g}"
