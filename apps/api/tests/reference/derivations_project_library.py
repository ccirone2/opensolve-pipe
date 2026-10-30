"""Closed-form expected results for the project library (docs/proposals/project-library.md §3.3,
§7.1 items 2, 3, 4 and 6; CLAUDE.md D6, D7, D22).

Written from the proposal (§1.3 decisions 3-4, §2, §3, §4, §5.2), the models and the cited
libraries by a tester who did not read ``opensolve_pipe.services``; nothing here imports it. Every
bore, length, level, roughness, coefficient and fluid is a test input, except the NPS 60 STD bore,
ASME B36.10M-2004's 60 in outer diameter less two 0.375 in walls (59.25 in), and its roughness,
Farshad & Rieke (2006) 'Carbon steel, bare' at that bore (``farshad_carbon_steel``). The K of 0.30
stated at 0.7366 m, the Cv of 900 and the other coefficients are made-up inputs, not data for a
real valve (proposal, "Test inputs").

What a library entry means (proposal §1.3, §3.1, §3.3):

- **A pipe spec** gives every pipe segment that refers to it its material, inner diameter and
  roughness; the segment keeps its own length. A spec on a library material without a roughness
  takes that material's Farshad roughness evaluated at the spec's inner diameter.
- **A K entry** is stated at a bore d₀ (``referenceDiameter``). Used on an element of bore D (a
  valve's inlet pipe, a fitting's pipe ``pipeIndex``) it is the same loss at the same flow:

      K₀ (Q/A₀)²/2g = K (Q/A)²/2g   ⇒   K = K₀ (A/A₀)² = K₀ (D/d₀)⁴          (``k_at_bore``)

- **A Cv or Kv entry** needs no bore: it is the coefficient as entered, converted to K on the
  element's own bore as an inline coefficient is. The conversion is the definition (ISA-75.01.01:
  Cv US gpm of water at 1 psi, Kv m³/h of water at 1 bar), K = 2 ΔP_ref A²/(ρ_w Q_ref²), with the
  reference water ρ_w = CoolProp IAPWS-95 at 60 °F and 703572 Pa, the conditions
  ``fluids.fittings.Kv_to_K`` documents, 999.29744568 kg/m³ (``element_laws.k_from_definition``).
  TSD §5.3 says the solver converts with ``fluids.fittings.Cv_to_K`` / ``Kv_to_K``;
  ``k_from_coefficient`` checks the two agree to 1e-9 (TSD: 7×10⁻¹¹ measured), so the flows
  derived here from the definition are independent of the solver's conversion and equal to it
  far inside D6.

Pipes: Darcy–Weisbach h_f = f (L/D) v|v|/(2g) with the Colebrook (1939) friction factor

    1/√f = −2 log10( (ε/D)/3.7 + 2.51/(Re √f) )

solved here by a fixed-point iteration on x = 1/√f (``colebrook``): neither the solver's Clamond
nor the suite's Lambert-W solution (``derivations.colebrook``), which a self-check compares it
with. Every case keeps every pipe turbulent (Re ≥ 4000, ``require_turbulent``). Boundaries add no
entrance or exit loss unless the connection has an entrance or exit fitting (CLAUDE.md D10), and
these lines have none. Valves: EGL_in − EGL_out = K v_ref|v_ref|/(2g), v_ref in the pipe on the
valve's inlet port, its end segment (TSD §5.3, ``element_laws.valve_loss``); fittings:
K v|v|/(2g) on the velocity in pipe ``pipeIndex``, times the quantity.

Fluid: the suite's liquid A (998 kg/m³, 1 mPa·s; ``derivations.FLUID_A``), a custom fluid, so no
property lookup enters the expected values.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import fluids.fittings
import fluids.friction
from scipy.optimize import brentq

from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    check_valve,
    control_valve,
    custom_fluid,
    isolation_valve,
    make_project,
    reservoir,
)

MODULE = "derivations_project_library"
G = dv.G
INCH = dv.INCH
ROUGHNESS = 4.5e-5
"""m: the roughness of the custom test specs (a test input, as ``line.ROUGHNESS``)."""

CoefficientKind = Literal["K", "Cv", "Kv"]


def source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def liquid_a() -> tuple[dict[str, Any], float, float]:
    """The suite's water-like custom test liquid A: (fluid JSON, ρ kg/m³, ν m²/s)."""
    name, rho, mu = dv.FLUID_A
    fluid = custom_fluid(name, rho, mu).model_dump(mode="json", exclude_none=True)
    return fluid, rho, mu / rho


# --- Friction ----------------------------------------------------------------------------------

COLEBROOK_ITERATIONS = 60
"""Fixed-point steps on x = 1/√f. The map x ↦ −2 log10(ε/(3.7D) + 2.51 x/Re) has slope
(2/ln 10)·(2.51/Re)/(ε/(3.7D) + 2.51x/Re) ≤ (2/ln 10)/x ≈ 0.11 at x ≈ 8 (f ≈ 0.016), so 60 steps
contract the starting error by 10⁻⁵⁷: the iterate is the root to round-off."""


def colebrook(re: float, ed: float) -> float:
    """Darcy f from the Colebrook (1939) equation, 1/√f = −2 log10(ed/3.7 + 2.51/(Re √f)), by
    fixed-point iteration on x = 1/√f from x = 8 (turbulent flow only, Re ≥ 4000)."""
    if re < dv.RE_TURBULENT:
        raise ValueError(f"the library cases keep every pipe turbulent, got Re = {re:.1f}")
    x = 8.0
    for _ in range(COLEBROOK_ITERATIONS):
        x = -2.0 * math.log10(ed / dv.COLEBROOK_A + dv.COLEBROOK_B * x / re)
    return 1.0 / (x * x)


def friction_head_loss(q: float, d: float, length: float, eps: float, nu: float) -> float:
    """h_f = f (L/D) v|v|/(2g), f from ``colebrook`` at Re = |v| D/ν (q ≠ 0)."""
    v = dv.velocity(q, d)
    f = colebrook(abs(v) * d / nu, eps / d)
    return f * length / d * v * abs(v) / (2.0 * G)


def solve_flow(head_loss: Callable[[float], float], dh: float, q_low: float) -> float:
    """The flow Q > q_low with head_loss(Q) = dh, head_loss increasing, by brentq on a bracket
    from q_low (a turbulent flow with head_loss(q_low) < dh: ``colebrook`` takes no laminar flow)
    doubled until it passes dh."""
    if not head_loss(q_low) < dh:
        raise ValueError("q_low is not below the solution")
    q_hi = 2.0 * q_low
    while head_loss(q_hi) < dh:
        q_hi *= 2.0
    root: float = brentq(
        lambda q: head_loss(q) - dh, q_low, q_hi, xtol=1.0e-18, rtol=1.0e-15, maxiter=500
    )
    return root


def turbulent_flow(d: float, nu: float) -> float:
    """The flow at Re = 4000 in a pipe of bore d, a lower bracket for ``solve_flow``."""
    return dv.RE_TURBULENT * nu / d * dv.area(d)


def colebrook_velocity(h: float, d: float, length: float, eps: float, nu: float) -> float:
    """The mean velocity of a pipe whose friction loss is h > 0, from the Colebrook equation
    solved exactly for v (no iteration on f).

    With h = f (L/D) v²/(2g), √f · v = S, S = √(2 g h D/L), is known; so is Re √f = (vD/ν) √f =
    S D/ν. The Colebrook equation then gives 1/√f explicitly, and v = S/√f:

        v = −2 S log10( (ε/D)/3.7 + 2.51 ν/(S D) )
    """
    s = math.sqrt(2.0 * G * h * d / length)
    return -2.0 * s * math.log10(eps / d / dv.COLEBROOK_A + dv.COLEBROOK_B * nu / (s * d))


# --- Library entries ----------------------------------------------------------------------------


def farshad_carbon_steel(d: float) -> float:
    """ε of carbon steel at inner diameter d (m): Farshad & Rieke (2006) ε = A·D^(B+1), A and D in
    inches, for 'Carbon steel, bare' A = 0.0014 in, B = −1.0112, as fluids 1.3.1 tabulates them
    (``fluids.friction.roughness_Farshad``, the library's cited source, D8). Written out and
    checked against fluids' function to round-off."""
    a, b = 0.0014, -1.0112
    eps = a * (d / INCH) ** (b + 1.0) * INCH
    cited = float(fluids.friction.roughness_Farshad(ID="Carbon steel, bare", D=d))
    if abs(eps - cited) > 1.0e-15 * cited:
        raise RuntimeError(f"Farshad's form gives {eps!r}, fluids {cited!r}")
    return cited


def k_at_bore(k0: float, d0: float, d: float) -> float:
    """A K stated at bore d0, moved to bore d: the same head loss at the same flow, K0 (d/d0)⁴
    (module docstring; proposal §3.3)."""
    return k0 * (d / d0) ** 4


FLOW_UNITS: dict[str, tuple[float, float]] = {
    "Cv": (el.CV_FLOW, el.CV_PRESSURE_DROP),
    "Kv": (el.KV_FLOW, el.KV_PRESSURE_DROP),
}
"""A flow coefficient's flow unit (m³/s) and pressure drop (Pa) (ISA-75.01.01; scipy.constants)."""
CONVERSION_AGREEMENT = 1.0e-9
"""The definition against fluids' rounded constants (1.6×10⁹, 1.1560992283536566): TSD §5.3
measured 7×10⁻¹¹."""


def k_from_coefficient(kind: CoefficientKind, value: float, d: float) -> float:
    """K on bore d of a coefficient as entered: K as given; a Cv or Kv by its definition
    (``element_laws.k_from_definition``), checked against fluids' ``Cv_to_K`` / ``Kv_to_K``."""
    if kind == "K":
        return value
    q_unit, dp = FLOW_UNITS[kind]
    k = el.k_from_definition(value * q_unit, dp, d)
    converted = float(
        fluids.fittings.Cv_to_K(value, d) if kind == "Cv" else fluids.fittings.Kv_to_K(value, d)
    )
    if abs(k - converted) > CONVERSION_AGREEMENT * converted:
        raise RuntimeError(f"{kind} {value}: the definition gives K {k!r}, fluids {converted!r}")
    return k


def fluids_k(kind: CoefficientKind, value: float, d: float) -> float:
    """K on bore d by the conversion TSD §5.3 names for the solver: a K as entered, fluids'
    ``Cv_to_K`` / ``Kv_to_K`` (ISA-75.01.01) for a Cv or Kv."""
    if kind == "K":
        return value
    if kind == "Cv":
        return float(fluids.fittings.Cv_to_K(value, d))
    return float(fluids.fittings.Kv_to_K(value, d))


def coefficient_head_loss(kind: Literal["Cv", "Kv"], value: float, q: float) -> float:
    """The head loss of a Cv or Kv at flow q, signed like q, on any bore. By the definition,
    K = 2 ΔP_ref A²/(ρ_w Q_ref²) on the bore of area A, so

        h = K (q/A)|q/A|/(2g) = ΔP_ref q|q| / (ρ_w g Q_ref²),   Q_ref = value × the flow unit

    in which A cancels: the loss at a flow does not depend on the bore the coefficient is
    converted on, provided the velocity is taken on the same bore (proposal §1.3 decision 3)."""
    q_unit, dp = FLOW_UNITS[kind]
    q_ref = value * q_unit
    return dp * q * abs(q) / (el.REFERENCE_WATER_DENSITY * G * q_ref * q_ref)


def cv_from_k(k: float, d: float) -> float:
    """The Cv whose definition gives K on bore d: K = 2 ΔP A²/(ρ_w Q²) ⇒ Q = A √(2 ΔP/(ρ_w K)),
    Cv = Q / (1 US gpm), ΔP = 1 psi."""
    q = dv.area(d) * math.sqrt(2.0 * el.CV_PRESSURE_DROP / (el.REFERENCE_WATER_DENSITY * k))
    return q / el.CV_FLOW


@dataclass(frozen=True)
class Entry:
    """A resistance entry (proposal §2.2)."""

    id: str
    kind: CoefficientKind
    value: float
    reference_diameter: float | None = None
    name: str = ""
    source: str = ""

    def json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "name": self.name or f"Entry {self.id}",
            "source": self.source or f"Made-up test datasheet for {self.id}",
            "kind": self.kind,
            "value": self.value,
        }
        if self.reference_diameter is not None:
            out["referenceDiameter"] = self.reference_diameter
        return out

    def k(self, d: float) -> float:
        """The entry's K on an element of bore d (module docstring)."""
        if self.kind == "K":
            assert self.reference_diameter is not None
            return k_at_bore(self.value, self.reference_diameter, d)
        return k_from_coefficient(self.kind, self.value, d)

    def head_loss(self, q: float) -> float:
        """The entry's head loss at flow q, signed like q, on whatever bore it is used: a K as
        stated, K₀ (q/A₀)|q/A₀|/(2g) on its own d₀; a Cv or Kv by ``coefficient_head_loss``."""
        if self.kind == "K":
            assert self.reference_diameter is not None
            return el.valve_loss(self.value, q, self.reference_diameter)
        return coefficient_head_loss(self.kind, self.value, q)


@dataclass(frozen=True)
class Spec:
    """A pipe spec (proposal §2.1): a custom one unless ``material_id`` names a library
    material; ``roughness`` None takes that material's Farshad roughness at the bore."""

    id: str
    inner_diameter: float
    roughness: float | None = ROUGHNESS
    material_id: str = "custom"
    name: str = ""
    source: str = ""
    outer_diameter: float | None = None
    nominal_size: float | None = None

    def json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "name": self.name or f"Spec {self.id}",
            "source": self.source or f"Test input for spec {self.id}",
            "materialId": self.material_id,
            "innerDiameter": self.inner_diameter,
        }
        for key, value in (
            ("roughness", self.roughness),
            ("outerDiameter", self.outer_diameter),
            ("nominalSize", self.nominal_size),
        ):
            if value is not None:
                out[key] = value
        return out

    @property
    def eps(self) -> float:
        if self.roughness is not None:
            return self.roughness
        if self.material_id != "carbon_steel":
            raise ValueError("only carbon steel's Farshad surface is written out here")
        return farshad_carbon_steel(self.inner_diameter)


def spec_pipe(spec: Spec, length: float) -> dict[str, Any]:
    """A pipe segment that refers to a spec: its id and its own length, nothing else (§2.1)."""
    return {"specId": spec.id, "length": length}


def library_ref(entry_id: str) -> dict[str, Any]:
    """A valve resistance taken from the library (proposal §2.2)."""
    return {"kind": "library", "id": entry_id}


def connection(
    cid: str,
    from_port: str,
    to_port: str,
    pipes: Sequence[dict[str, Any]],
    fittings: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """A connection between two "componentId:portId" keys, as API JSON."""
    from_component, from_port_id = from_port.split(":")
    to_component, to_port_id = to_port.split(":")
    return {
        "id": cid,
        "fromComponentId": from_component,
        "fromPortId": from_port_id,
        "toComponentId": to_component,
        "toPortId": to_port_id,
        "piping": {"pipes": list(pipes), "fittings": list(fittings)},
    }


def project_json(
    pid: str,
    name: str,
    fluid: dict[str, Any],
    components: Sequence[dict[str, Any]],
    connections: Sequence[dict[str, Any]],
    specs: Sequence[Spec] = (),
    entries: Sequence[Entry] = (),
) -> dict[str, Any]:
    """API JSON of a project with its library, validated by the model (the contract)."""
    shell = make_project(pid, name, custom_fluid("placeholder", 1000.0, 1.0e-3), [], [])
    out: dict[str, Any] = shell.model_dump(mode="json", exclude_none=True)
    out["fluid"] = fluid
    out["components"] = list(components)
    out["connections"] = list(connections)
    if specs:
        out["pipeLibrary"] = [s.json() for s in specs]
    if entries:
        out["resistanceLibrary"] = [e.json() for e in entries]
    Project.model_validate(out)
    return out


def component_json(model: Any, resistance: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = model.model_dump(mode="json", exclude_none=True)
    if resistance is not None:
        out["resistance"] = resistance
    return out


def require_turbulent(nu: float, pairs: Sequence[tuple[float, float]]) -> None:
    """Guard: every (flow, bore) is turbulent at the solution."""
    for q, d in pairs:
        dv.require_regime(q, d, nu, "turbulent")


# --- The cases ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class LibraryCase:
    """One closed-form case: its project (API JSON, with its library) and expected values."""

    name: str
    description: str
    source: str
    project: dict[str, Any]
    flows: dict[str, float]
    """Expected connection flows, m³/s."""
    density: float
    valves: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Valve id -> (K on its reference bore, that bore D)."""
    fittings: dict[tuple[str, int], tuple[float, float]] = field(default_factory=dict)
    """(connection id, fitting index) -> (K of one fitting, its reference bore)."""
    valve_head_loss: dict[str, float] = field(default_factory=dict)
    """Valve id -> EGL_in − EGL_out at the expected flow, m (closed form)."""
    segments: dict[tuple[str, int], tuple[float, float]] = field(default_factory=dict)
    """(connection id, pipe index) -> (inner diameter, roughness) the segment must be solved
    with."""
    data: dict[str, Any] = field(default_factory=dict)


NPS60_BORE = 59.25 * INCH
"""m: ASME B36.10M-2004 NPS 60 STD, 60 in OD less two 0.375 in walls (proposal §1.2, P2)."""
NPS60_OD = 60.0 * INCH


def nps60_spec() -> Spec:
    """The NPS 60 STD carbon-steel spec of proposal §1.2: a library material with its bore and
    no roughness, so the material's Farshad roughness at that bore applies (§2.1)."""
    return Spec(
        "PS60",
        NPS60_BORE,
        roughness=None,
        material_id="carbon_steel",
        name="NPS 60 STD carbon steel",
        source="ASME B36.10M-2004, NPS 60 STD: 60 in OD, 0.375 in wall",
        outer_diameter=NPS60_OD,
        nominal_size=NPS60_OD,
    )


def nps60_line() -> LibraryCase:
    """§7.1 item 2: R1 (H 12 m) → L1, 400 m of the NPS 60 STD spec → R2 (H 10.5 m); no fittings,
    so the boundaries add no loss (D10) and the whole head is pipe friction:

        H1 − H2 = h = f (L/D) v²/(2g),   v = −2 S log10(ε/(3.7D) + 2.51 ν/(S D)),  S = √(2ghD/L)

    (``colebrook_velocity``), ε = Farshad 'Carbon steel, bare' at D = 59.25 in, Q = v π D²/4."""
    fluid, rho, nu = liquid_a()
    spec = nps60_spec()
    length = 400.0
    h1_parts, h2_parts = (2.0, 10.0), (0.5, 10.0)
    h = sum(h1_parts) - sum(h2_parts)
    d, eps = spec.inner_diameter, spec.eps
    v = colebrook_velocity(h, d, length, eps, nu)
    q = v * dv.area(d)
    re = v * d / nu
    # Self-checks: the explicit velocity satisfies Colebrook as fluids' Lambert-W solution and the
    # fixed point here give it, and gives back the head.
    for f in (dv.colebrook(re, eps / d), colebrook(re, eps / d)):
        back = f * length / d * v * v / (2.0 * G)
        if abs(back - h) > 1.0e-12 * h:
            raise RuntimeError(f"the explicit Colebrook velocity gives back {back!r} m, not {h} m")
    require_turbulent(nu, [(q, d)])
    components = [
        reservoir("R1", h1_parts[0], h1_parts[1], nominal_size=NPS60_OD).model_dump(
            mode="json", exclude_none=True
        ),
        reservoir("R2", h2_parts[0], h2_parts[1], nominal_size=NPS60_OD).model_dump(
            mode="json", exclude_none=True
        ),
    ]
    project = project_json(
        "ref-library-nps60",
        "NPS 60 STD spec between two reservoirs",
        fluid,
        components,
        [connection("L1", "R1:port_1", "R2:port_1", [spec_pipe(spec, length)])],
        specs=[spec],
    )
    return LibraryCase(
        name="library_nps60_line",
        description=(
            "One 400 m pipe on an NPS 60 STD carbon-steel spec (59.25 in bore, roughness blank: "
            "Farshad at that bore) between reservoirs 1.5 m apart."
        ),
        source=source(
            "nps60_line",
            "Darcy-Weisbach + Colebrook solved exactly for v given h; eps = fluids "
            "roughness_Farshad('Carbon steel, bare', 59.25 in)",
        ),
        project=project,
        flows={"L1": q},
        density=rho,
        segments={("L1", 0): (d, eps)},
        data={"velocity": v, "reynolds": re, "head": h, "material_roughness": 3.6e-5},
    )


def nps60_flow_with_roughness(eps: float) -> float:
    """``nps60_line``'s flow on another roughness (the sensitivity check of the test)."""
    _, _, nu = liquid_a()
    v = colebrook_velocity(1.5, NPS60_BORE, 400.0, eps, nu)
    return v * dv.area(NPS60_BORE)


K30 = Entry(
    "RS30",
    "K",
    0.30,
    reference_diameter=0.7366,
    name="30 in butterfly valve, fully open",
    source="Made-up test datasheet: K 0.30 stated at a 29.0 in (0.7366 m) bore",
)
"""Proposal P3's K₀ = 0.30 at d₀ = 0.7366 m (a made-up input)."""
SPEC30 = Spec(
    "PS30",
    29.25 * INCH,
    name="NPS 30 STD bore, custom",
    source="Test input: a 29.25 in bore with 45 micrometre roughness",
)
"""The 0.74295 m pipe the K entry is used on (D ≠ d₀)."""


def _two_line_valve(
    name: str,
    title: str,
    spec: Spec,
    lengths: tuple[float, float],
    h1_parts: tuple[float, float],
    h2_parts: tuple[float, float],
    resistance: dict[str, Any],
    entries: Sequence[Entry],
    valve_type: Literal["gate", "ball", "butterfly", "globe"] = "butterfly",
    valve_z: float = 0.0,
) -> dict[str, Any]:
    """R1 → L1 (spec, lengths[0]) → V1 (isolation valve) → L2 (spec, lengths[1]) → R2."""
    fluid, _, _ = liquid_a()
    components = [
        reservoir("R1", *h1_parts).model_dump(mode="json", exclude_none=True),
        component_json(isolation_valve("V1", valve_z, valve_type), resistance),
        reservoir("R2", *h2_parts).model_dump(mode="json", exclude_none=True),
    ]
    connections = [
        connection("L1", "R1:port_1", "V1:inlet", [spec_pipe(spec, lengths[0])]),
        connection("L2", "V1:outlet", "R2:port_1", [spec_pipe(spec, lengths[1])]),
    ]
    return project_json(
        f"ref-{name}", title, fluid, components, connections, specs=[spec], entries=entries
    )


def k_entry_valve() -> LibraryCase:
    """§7.1 item 3: R1 (H 10.25 m) → L1 (15 m of PS30, D = 0.74295 m) → V1, a butterfly valve on
    the K entry RS30 (K₀ = 0.30 at d₀ = 0.7366 m) → L2 (15 m of PS30) → R2 (H 10.0 m):

        H1 − H2 = h_f(L1) + K₀ (Q/A₀)²/(2g) + h_f(L2)

    and the valve's loss K₀ (Q/A₀)²/(2g) = K (Q/A)²/(2g), K = K₀ (D/d₀)⁴ on its inlet pipe."""
    _, rho, nu = liquid_a()
    d, eps = SPEC30.inner_diameter, SPEC30.eps
    assert K30.reference_diameter is not None
    d0 = K30.reference_diameter
    lengths = (15.0, 15.0)
    h1_parts, h2_parts = (0.0, 10.25), (0.0, 10.0)
    dh = sum(h1_parts) - sum(h2_parts)
    a0 = dv.area(d0)

    def valve(q: float) -> float:
        return K30.value * (q / a0) * abs(q / a0) / (2.0 * G)

    def head_loss(q: float) -> float:
        return sum(friction_head_loss(q, d, x, eps, nu) for x in lengths) + valve(q)

    q = solve_flow(head_loss, dh, turbulent_flow(d, nu))
    require_turbulent(nu, [(q, d)])
    k = k_at_bore(K30.value, d0, d)
    # The same loss on either basis (proposal §3.3, P3): K (Q/A)²/2g equals K₀ (Q/A₀)²/2g.
    if abs(el.valve_loss(k, q, d) - valve(q)) > 1.0e-14 * valve(q):
        raise RuntimeError("K0 (D/d0)^4 does not give the stated loss")
    project = _two_line_valve(
        "library-k-entry",
        "A K entry stated at another bore",
        SPEC30,
        lengths,
        h1_parts,
        h2_parts,
        library_ref(K30.id),
        [K30],
    )
    return LibraryCase(
        name="library_k_entry_valve",
        description=(
            "A butterfly valve whose resistance is a library K of 0.30 stated at 0.7366 m, used "
            "on a 0.74295 m pipe: K = K0 (D/d0)^4."
        ),
        source=source(
            "k_entry_valve",
            "K0 (Q/A0)^2/2g; K = K0 (D/d0)^4; Darcy-Weisbach + Colebrook (fixed point); brentq",
        ),
        project=project,
        flows={"L1": q, "L2": q},
        density=rho,
        valves={"V1": (k, d)},
        valve_head_loss={"V1": valve(q)},
        data={"k0": K30.value, "d0": d0, "d": d},
    )


SPEC_A = Spec("PSA", 0.1541, name="6 in line, custom")
SPEC_B = Spec("PSB", 0.1282, name="5 in line, custom")
CV900 = Entry("RSCV", "Cv", 900.0, name="Butterfly valve Cv 900")
KV700 = Entry("RSKV", "Kv", 700.0, name="Check valve Kv 700")
K08 = Entry("RSK", "K", 0.8, reference_diameter=0.1023, name="Strainer K 0.8 at 0.1023 m")
UNUSED = Entry("RSUNUSED", "Cv", 50.0, name="Spare entry, used by nothing")
"""The entries of ``coefficient_entries`` (made-up inputs)."""


def coefficient_entries() -> LibraryCase:
    """§7.1 item 4: Cv, Kv and K entries on three kinds of valve and on inline fittings, one entry
    used by several elements. A series line, liquid A, every element open:

        R1 (H 25) → L1 [PSA 20 m] → V1 butterfly, RSCV (Cv 900)
          → L2 [PSA 10 m, PSB 10 m; fittings: custom RSCV on pipe 1, 2 × gate_valve RSKV on
                pipe 2, custom RSK on pipe 2] → CV1 check valve, RSKV (Kv 700)
          → L3 [PSB 15 m] → V2 gate, RSCV → L4 [PSB 10 m] → PRV1, failed open, RSK (K 0.8 at
            0.1023 m) → L5 [PSA 20 m] → R2 (H 5)

        H1 − H2 = Σ h_f + Σ_valves K v_in²/2g + Σ_fittings n K v²/2g

    each K the entry's on the element's bore: a Cv or Kv by its definition, a K moved by
    (D/d₀)⁴. RSUNUSED is used by nothing (the methods summary lists it as not used, §4.2)."""
    fluid, rho, nu = liquid_a()
    da, db = SPEC_A.inner_diameter, SPEC_B.inner_diameter
    valves = {
        "V1": (CV900.k(da), da),
        "CV1": (KV700.k(db), db),
        "V2": (CV900.k(db), db),
        "PRV1": (K08.k(db), db),
    }
    fittings = {
        ("L2", 0): (CV900.k(da), da),
        ("L2", 1): (KV700.k(db), db),
        ("L2", 2): (K08.k(db), db),
    }
    quantities = {("L2", 0): 1, ("L2", 1): 2, ("L2", 2): 1}
    pipes = {
        "L1": [(SPEC_A, 20.0)],
        "L2": [(SPEC_A, 10.0), (SPEC_B, 10.0)],
        "L3": [(SPEC_B, 15.0)],
        "L4": [(SPEC_B, 10.0)],
        "L5": [(SPEC_A, 20.0)],
    }
    h1_parts, h2_parts = (0.0, 25.0), (0.0, 5.0)

    def head_loss(q: float) -> float:
        h = sum(
            friction_head_loss(q, s.inner_diameter, length, s.eps, nu)
            for line in pipes.values()
            for s, length in line
        )
        h += sum(el.valve_loss(k, q, d) for k, d in valves.values())
        h += sum(quantities[key] * dv.minor_head_loss(q, k, d) for key, (k, d) in fittings.items())
        return h

    q = solve_flow(head_loss, sum(h1_parts) - sum(h2_parts), turbulent_flow(da, nu))
    require_turbulent(nu, [(q, da), (q, db)])
    components = [
        reservoir("R1", *h1_parts).model_dump(mode="json", exclude_none=True),
        component_json(isolation_valve("V1", 0.0, "butterfly"), library_ref(CV900.id)),
        component_json(check_valve("CV1", 0.0, "check"), library_ref(KV700.id)),
        component_json(isolation_valve("V2", 0.0, "gate"), library_ref(CV900.id)),
        component_json(
            control_valve("PRV1", 0.0, "prv", 2.0e5, status="failed_open"), library_ref(K08.id)
        ),
        reservoir("R2", *h2_parts).model_dump(mode="json", exclude_none=True),
    ]
    ends = {
        "L1": ("R1:port_1", "V1:inlet"),
        "L2": ("V1:outlet", "CV1:inlet"),
        "L3": ("CV1:outlet", "V2:inlet"),
        "L4": ("V2:outlet", "PRV1:inlet"),
        "L5": ("PRV1:outlet", "R2:port_1"),
    }
    l2_fittings = [
        {"type": "custom", "quantity": 1, "pipeIndex": 0, "resistanceId": CV900.id},
        {"type": "gate_valve", "quantity": 2, "pipeIndex": 1, "resistanceId": KV700.id},
        {"type": "custom", "quantity": 1, "pipeIndex": 1, "resistanceId": K08.id},
    ]
    connections = [
        connection(
            cid,
            *ends[cid],
            [spec_pipe(s, length) for s, length in line],
            l2_fittings if cid == "L2" else (),
        )
        for cid, line in pipes.items()
    ]
    project = project_json(
        "ref-library-coefficients",
        "Cv, Kv and K entries on valves and fittings",
        fluid,
        components,
        connections,
        specs=[SPEC_A, SPEC_B],
        entries=[CV900, KV700, K08, UNUSED],
    )
    return LibraryCase(
        name="library_coefficient_entries",
        description=(
            "Cv, Kv and K library entries on an isolation, a check and a failed-open control "
            "valve and on inline fittings, one entry shared by two valves and a fitting."
        ),
        source=source(
            "coefficient_entries",
            "K from Cv/Kv by definition (ISA-75.01.01, element_laws), K = K0 (D/d0)^4; "
            "Darcy-Weisbach + Colebrook (fixed point); brentq",
        ),
        project=project,
        flows=dict.fromkeys(pipes, q),
        density=rho,
        valves=valves,
        fittings=fittings,
        valve_head_loss={vid: el.valve_loss(k, q, d) for vid, (k, d) in valves.items()},
        segments={
            (cid, i): (s.inner_diameter, s.eps)
            for cid, line in pipes.items()
            for i, (s, _) in enumerate(line)
        },
        data={"quantities": quantities},
    )


RSV = Entry("RSV", "K", 0.45, reference_diameter=0.2, name="Butterfly valve K 0.45 at 0.2 m")
RSR = Entry("RSR", "K", 0.3, reference_diameter=0.1023, name="Reducer K 0.3 at 0.1023 m")
RSRC = Entry("RSRC", "Cv", 1200.0, name="Conical reducer Cv 1200")
RSRK = Entry("RSRK", "Kv", 400.0, name="Strainer Kv 400")
"""The entries of ``reverse_reducer_line`` (made-up inputs)."""


def reverse_reducer_line() -> LibraryCase:
    """Entries on reducers and on a valve whose ports have different bores, in reverse flow. The
    flow runs from R2 to R1, against both connections' from → to and the valve's inlet → outlet:

        R1 (H 4) ← L1 [PSA 12 m, PSB 8 m, PSA 6 m; fittings: reducer_sudden on pipe 1 (between
        PSA and PSB) RSR (K 0.3 at 0.1023 m), reducer_conical 30° on pipe 2 (between PSB and
        PSA) RSRC (Cv 1200), 3 × custom on pipe 3 RSRK (Kv 400)] ← V1 butterfly, RSV (K 0.45 at
        0.2 m; inlet on L1's PSA, outlet on L2's PSB) ← L2 [PSB 15 m] ← R2 (H 20)

        H2 − H1 = Σ h_f(|Q|) + Σ_entries n · h_entry(|Q|)

    with each entry's loss ``Entry.head_loss``, which does not depend on the bore it is used on
    (a K moved by (D/d₀)⁴ and taken on D, a Cv or Kv converted on D and taken on D): the flow is
    the same whichever bore the solver takes for each element, as long as it takes the velocity
    on that bore; the reported bores are checked separately (a valve's inlet pipe, D9; a fitting's
    pipe ``pipeIndex``, the model's ``Fitting.pipeIndex`` and ``kOverride``). A reducer with a
    user K has that K in both directions (TSD §4.5: a user K always wins)."""
    fluid, rho, nu = liquid_a()
    da, db = SPEC_A.inner_diameter, SPEC_B.inner_diameter
    h1_parts, h2_parts = (0.0, 4.0), (0.0, 20.0)
    l1 = [(SPEC_A, 12.0), (SPEC_B, 8.0), (SPEC_A, 6.0)]
    l2 = [(SPEC_B, 15.0)]
    l1_fittings: list[dict[str, Any]] = [
        {"type": "reducer_sudden", "quantity": 1, "pipeIndex": 0, "resistanceId": RSR.id},
        {
            "type": "reducer_conical",
            "quantity": 1,
            "pipeIndex": 1,
            "angle": 30.0,
            "resistanceId": RSRC.id,
        },
        {"type": "custom", "quantity": 3, "pipeIndex": 2, "resistanceId": RSRK.id},
    ]
    fitting_entries = {0: RSR, 1: RSRC, 2: RSRK}
    quantities: dict[tuple[str, int], int] = {
        ("L1", j): f["quantity"] for j, f in enumerate(l1_fittings)
    }
    fitting_bores = {0: da, 1: db, 2: da}

    def head_loss(q: float) -> float:
        h = sum(friction_head_loss(q, s.inner_diameter, length, s.eps, nu) for s, length in l1 + l2)
        h += RSV.head_loss(q)
        h += sum(quantities[("L1", j)] * entry.head_loss(q) for j, entry in fitting_entries.items())
        return h

    q = solve_flow(head_loss, sum(h2_parts) - sum(h1_parts), turbulent_flow(da, nu))
    require_turbulent(nu, [(q, da), (q, db)])
    # Self-check: each entry's bore-free loss equals its K on the bore it is used on, taken with
    # that bore's velocity (to round-off for a K, to the definition's agreement with itself for
    # a Cv or Kv, whose K here is the definition's).
    for entry, d in [(RSV, da), *((fitting_entries[j], fitting_bores[j]) for j in range(3))]:
        on_bore = dv.minor_head_loss(q, entry.k(d), d)
        if abs(on_bore - entry.head_loss(q)) > 1.0e-13 * abs(on_bore):
            raise RuntimeError(f"{entry.id}: {on_bore!r} on its bore, {entry.head_loss(q)!r}")
    components = [
        reservoir("R1", *h1_parts).model_dump(mode="json", exclude_none=True),
        component_json(isolation_valve("V1", 0.0, "butterfly"), library_ref(RSV.id)),
        reservoir("R2", *h2_parts).model_dump(mode="json", exclude_none=True),
    ]
    connections = [
        connection("L1", "R1:port_1", "V1:inlet", [spec_pipe(s, x) for s, x in l1], l1_fittings),
        connection("L2", "V1:outlet", "R2:port_1", [spec_pipe(s, x) for s, x in l2]),
    ]
    project = project_json(
        "ref-library-reverse-reducers",
        "Entries on reducers and on a valve of two bores, in reverse flow",
        fluid,
        components,
        connections,
        specs=[SPEC_A, SPEC_B],
        entries=[RSV, RSR, RSRC, RSRK],
    )
    return LibraryCase(
        name="library_reverse_reducer_line",
        description=(
            "K, Cv and Kv library entries on reducers and a custom fitting, and a K entry on a "
            "butterfly valve whose ports have different bores, all in reverse flow."
        ),
        source=source(
            "reverse_reducer_line",
            "K0 (Q/A0)^2/2g; Cv/Kv: dP_ref Q^2/(rho_w g Q_ref^2) (ISA-75.01.01 definition); "
            "Darcy-Weisbach + Colebrook (fixed point); brentq",
        ),
        project=project,
        flows={"L1": -q, "L2": -q},
        density=rho,
        valves={"V1": (RSV.k(da), da)},
        fittings={("L1", j): (fitting_entries[j].k(d), d) for j, d in fitting_bores.items()},
        valve_head_loss={"V1": -RSV.head_loss(q)},
        data={
            "quantities": quantities,
            "fitting_head_loss": {
                ("L1", j): -quantities[("L1", j)] * e.head_loss(q)
                for j, e in fitting_entries.items()
            },
            "entries": {"V1": RSV, **{f"L1/{j}": e for j, e in fitting_entries.items()}},
        },
    )


SPEC_C = Spec("PSC", 0.0779, name="3 in line, custom")
RSBIG = Entry("RSBIG", "K", 9000.0, reference_diameter=0.05, name="Restriction K 9000 at 0.05 m")
"""A K entry whose K on the 0.0779 m pipe, 9000 (0.0779/0.05)⁴ ≈ 5.3×10⁴, exceeds the 10⁴ bound
of a fitting's kOverride: the entry's own bound is FlowCoefficient's (0, 10⁷] (proposal §2.2),
so the moved K is used as it is."""


def high_k_fitting() -> LibraryCase:
    """A custom fitting on a K entry whose K on its pipe is above kOverride's 10⁴: R1 (H 60) →
    L1 [PSC 10 m; custom RSBIG] → R2 (H 10):

        H1 − H2 = h_f + K₀ (Q/A₀)²/(2g)"""
    fluid, rho, nu = liquid_a()
    d, eps = SPEC_C.inner_diameter, SPEC_C.eps
    length = 10.0
    h1_parts, h2_parts = (0.0, 60.0), (0.0, 10.0)

    def head_loss(q: float) -> float:
        return friction_head_loss(q, d, length, eps, nu) + RSBIG.head_loss(q)

    q = solve_flow(head_loss, sum(h1_parts) - sum(h2_parts), turbulent_flow(d, nu))
    require_turbulent(nu, [(q, d)])
    k = RSBIG.k(d)
    if not k > 1.0e4:
        raise ValueError("the case needs a K above kOverride's bound")
    components = [
        reservoir("R1", *h1_parts).model_dump(mode="json", exclude_none=True),
        reservoir("R2", *h2_parts).model_dump(mode="json", exclude_none=True),
    ]
    fittings = [{"type": "custom", "quantity": 1, "pipeIndex": 0, "resistanceId": RSBIG.id}]
    project = project_json(
        "ref-library-high-k",
        "A fitting entry above kOverride's bound",
        fluid,
        components,
        [connection("L1", "R1:port_1", "R2:port_1", [spec_pipe(SPEC_C, length)], fittings)],
        specs=[SPEC_C],
        entries=[RSBIG],
    )
    return LibraryCase(
        name="library_high_k_fitting",
        description="A custom fitting on a K entry that is about 5.3e4 on its pipe.",
        source=source("high_k_fitting", "K0 (Q/A0)^2/2g; Darcy-Weisbach + Colebrook; brentq"),
        project=project,
        flows={"L1": q},
        density=rho,
        fittings={("L1", 0): (k, d)},
        data={"fitting_head_loss": {("L1", 0): RSBIG.head_loss(q)}},
    )


# --- Goal seek (§5.2) ---------------------------------------------------------------------------

SPEC_G = Spec("PSG", 0.1023, name="4 in line, custom")
CV200 = Entry("RSG", "Cv", 200.0, name="Gate valve Cv 200")
K5 = Entry("RSGK", "K", 5.0, reference_diameter=0.09, name="Gate valve K 5 at 0.09 m")
GOAL_LENGTHS = (40.0, 60.0)
GOAL_H1, GOAL_H2 = (10.0, 2.0), (0.0, 2.0)
GOAL_FLOW = 0.02
"""m³/s: the valve flow the goal seeks (a test input)."""
CV_BOUNDS = (10.0, 5000.0)
LENGTH_BOUNDS = (10.0, 500.0)


@dataclass(frozen=True)
class GoalSeekSetup:
    """A goal seek on a valve that refers to a library entry: the request and its closed form."""

    name: str
    project: dict[str, Any]
    variable: dict[str, Any]
    goal: dict[str, Any]
    inverse: float
    """The variable value whose closed-form flow is the target."""
    start: float
    start_source: Literal["case", "clipped", "middle"]
    density: float
    met_at_start: bool = False
    """The case already meets the goal: the search stops at its start (D16)."""
    scenario_id: str | None = None
    """The scenario the goal seek runs on (None: the base)."""
    replaced_override: int | None = None
    """Scenario run: the index of the scenario override the variable takes the place of."""

    def request(self) -> dict[str, Any]:
        out = {"project": self.project, "variables": [self.variable], "goals": [self.goal]}
        if self.scenario_id is not None:
            out["scenarioId"] = self.scenario_id
        return out

    def forward(self, x: float) -> float:
        """The closed-form valve flow at variable value x."""
        return goal_flow(self.variable, x, self.project)


def _goal_project(name: str, entry: Entry) -> dict[str, Any]:
    return _two_line_valve(
        name,
        f"Goal seek on a library valve ({entry.kind})",
        SPEC_G,
        GOAL_LENGTHS,
        GOAL_H1,
        GOAL_H2,
        library_ref(entry.id),
        [CV200, K5],
        valve_type="gate",
        valve_z=1.0,
    )


def _goal_line_flow(k: float, lengths: tuple[float, float]) -> float:
    """R1 → L1 → V1 (K on PSG's bore) → L2 → R2's flow."""
    _, _, nu = liquid_a()
    d, eps = SPEC_G.inner_diameter, SPEC_G.eps

    def head_loss(q: float) -> float:
        return sum(friction_head_loss(q, d, x, eps, nu) for x in lengths) + el.valve_loss(k, q, d)

    return solve_flow(head_loss, sum(GOAL_H1) - sum(GOAL_H2), turbulent_flow(d, nu))


def goal_flow(variable: dict[str, Any], x: float, project: dict[str, Any]) -> float:
    """The valve flow with the variable at x: V1's coefficient of the variable's kind, or L2's
    length with V1 on its entry."""
    if variable["field"] == "resistance":
        kind = variable["coefficient"]
        return _goal_line_flow(k_from_coefficient(kind, x, SPEC_G.inner_diameter), GOAL_LENGTHS)
    valve = next(c for c in project["components"] if c["id"] == "V1")
    entry = {CV200.id: CV200, K5.id: K5}[valve["resistance"]["id"]]
    return _goal_line_flow(entry.k(SPEC_G.inner_diameter), (GOAL_LENGTHS[0], x))


def _goal(target: float) -> dict[str, Any]:
    return {"quantity": "valve_flow", "elementId": "V1", "target": target}


def goal_seek_cv_on_cv_entry() -> GoalSeekSetup:
    """V1 on the Cv entry RSG (Cv 200), its Cv sought for 20 L/s: the search starts at the entry's
    value, which is of the variable's kind (§5.2). Inverse: K* = [H1 − H2 − h_L1 − h_L2]·2g/v² at
    Q = 20 L/s, v in PSG; Cv* from K* by the Cv definition (``cv_from_k``)."""
    _, rho, nu = liquid_a()
    d, eps = SPEC_G.inner_diameter, SPEC_G.eps
    q = GOAL_FLOW
    v = dv.velocity(q, d)
    h_pipes = sum(friction_head_loss(q, d, x, eps, nu) for x in GOAL_LENGTHS)
    k = (sum(GOAL_H1) - sum(GOAL_H2) - h_pipes) * 2.0 * G / (v * v)
    cv = cv_from_k(k, d)
    if abs(k_from_coefficient("Cv", cv, d) - k) > 1.0e-12 * k:
        raise RuntimeError("cv_from_k does not invert the Cv definition")
    if not CV_BOUNDS[0] < cv < CV_BOUNDS[1]:
        raise ValueError("the inverse Cv is outside the bounds")
    variable = {
        "kind": "component",
        "componentId": "V1",
        "field": "resistance",
        "coefficient": "Cv",
        "lower": CV_BOUNDS[0],
        "upper": CV_BOUNDS[1],
    }
    return GoalSeekSetup(
        "goal_seek_cv_entry",
        _goal_project("library-goal-seek-cv", CV200),
        variable,
        _goal(q),
        cv,
        CV200.value,
        "case",
        rho,
    )


def goal_seek_cv_on_k_entry() -> GoalSeekSetup:
    """V1 on the K entry RSGK, a Cv sought: the entry is of another kind, so the search starts in
    the middle of the bounds on the log scale, √(10 × 5000) (§5.2, today's rule)."""
    base = goal_seek_cv_on_cv_entry()
    middle = CV_BOUNDS[0] * math.sqrt(CV_BOUNDS[1] / CV_BOUNDS[0])
    return GoalSeekSetup(
        "goal_seek_k_entry",
        _goal_project("library-goal-seek-k", K5),
        base.variable,
        base.goal,
        base.inverse,
        middle,
        "middle",
        base.density,
    )


def goal_seek_length_of_spec_pipe() -> GoalSeekSetup:
    """V1 on RSG (Cv 200), the length of L2 (a pipe on spec PSG) sought for 20 L/s: L2* from
    h_L2 = H1 − H2 − h_L1 − h_V at the target, h_L2 = f (L/D) v²/2g."""
    _, rho, nu = liquid_a()
    d, eps = SPEC_G.inner_diameter, SPEC_G.eps
    q = GOAL_FLOW
    h_l2 = (
        sum(GOAL_H1)
        - sum(GOAL_H2)
        - friction_head_loss(q, d, GOAL_LENGTHS[0], eps, nu)
        - el.valve_loss(CV200.k(d), q, d)
    )
    length = h_l2 / friction_head_loss(q, d, 1.0, eps, nu)
    if not LENGTH_BOUNDS[0] < length < LENGTH_BOUNDS[1]:
        raise ValueError("the inverse length is outside the bounds")
    variable = {
        "kind": "pipe",
        "connectionId": "L2",
        "pipeIndex": 0,
        "field": "length",
        "lower": LENGTH_BOUNDS[0],
        "upper": LENGTH_BOUNDS[1],
    }
    return GoalSeekSetup(
        "goal_seek_spec_length",
        _goal_project("library-goal-seek-length", CV200),
        variable,
        _goal(q),
        length,
        GOAL_LENGTHS[1],
        "case",
        rho,
    )


K_BOUNDS = (0.5, 500.0)


def goal_seek_k_on_k_entry_met_at_start() -> GoalSeekSetup:
    """V1 on the K entry RSGK (K₀ 5 at d₀ 0.09 m) on PSG (D 0.1023 m), its K sought for the
    flow the case already gives: the case's K is the K on the valve's bore, K₀ (D/d₀)⁴ ≈ 8.35,
    not the K₀ it is stated as (D16: the search starts at the case's value; §5.2: the entry's
    value when its kind matches, which for a K is that value on the element's bore, §3.1). The
    target is the closed-form flow at that K, so the case meets it and the search stops at its
    start; a start at K₀ would solve another flow (the K 40 % lower) and not stop there."""
    _, rho, _ = liquid_a()
    k_case = K5.k(SPEC_G.inner_diameter)
    target = _goal_line_flow(k_case, GOAL_LENGTHS)
    if not K_BOUNDS[0] < K5.value < k_case < K_BOUNDS[1]:
        raise ValueError("the case's K and K0 must both lie inside the bounds")
    variable = {
        "kind": "component",
        "componentId": "V1",
        "field": "resistance",
        "coefficient": "K",
        "lower": K_BOUNDS[0],
        "upper": K_BOUNDS[1],
    }
    return GoalSeekSetup(
        "goal_seek_k_entry_met_at_start",
        _goal_project("library-goal-seek-k-start", K5),
        variable,
        _goal(target),
        k_case,
        k_case,
        "case",
        rho,
        met_at_start=True,
    )


CLIPPED_CV_BOUNDS = (10.0, 150.0)
CLIPPED_TARGET_CV = 100.0


def goal_seek_cv_entry_clipped() -> GoalSeekSetup:
    """V1 on the Cv entry RSG (Cv 200), its Cv sought in [10, 150] for the flow at Cv 100: the
    case's value lies above the bounds, so the search starts at the upper bound (D16: clipped)."""
    base = goal_seek_cv_on_cv_entry()
    variable = {**base.variable, "lower": CLIPPED_CV_BOUNDS[0], "upper": CLIPPED_CV_BOUNDS[1]}
    target = _goal_line_flow(
        k_from_coefficient("Cv", CLIPPED_TARGET_CV, SPEC_G.inner_diameter), GOAL_LENGTHS
    )
    return GoalSeekSetup(
        "goal_seek_cv_entry_clipped",
        _goal_project("library-goal-seek-clipped", CV200),
        variable,
        _goal(target),
        CLIPPED_TARGET_CV,
        CLIPPED_CV_BOUNDS[1],
        "clipped",
        base.density,
    )


def goal_seek_in_a_scenario() -> GoalSeekSetup:
    """A scenario run (D16): the base has V1 on the K entry RSGK; scenario S1 points it at the Cv
    entry RSG (Cv 200), its override 0. A Cv is sought in S1 for 20 L/s: the case's value is the
    scenario's entry, of the variable's kind, so the search starts at 200; the value found takes
    the place of override 0 (``replacedOverride``), and the inverse is
    ``goal_seek_cv_on_cv_entry``'s."""
    base = goal_seek_cv_on_cv_entry()
    project = _goal_project("library-goal-seek-scenario", K5)
    project["scenarios"] = [
        {
            "id": "S1",
            "name": "On the Cv entry",
            "overrides": [
                {
                    "kind": "component",
                    "componentId": "V1",
                    "field": "resistance",
                    "value": library_ref(CV200.id),
                }
            ],
        }
    ]
    Project.model_validate(project)
    return GoalSeekSetup(
        "goal_seek_in_a_scenario",
        project,
        base.variable,
        base.goal,
        base.inverse,
        CV200.value,
        "case",
        base.density,
        scenario_id="S1",
        replaced_override=0,
    )
