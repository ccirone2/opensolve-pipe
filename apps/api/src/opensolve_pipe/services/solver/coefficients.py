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
"""

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
