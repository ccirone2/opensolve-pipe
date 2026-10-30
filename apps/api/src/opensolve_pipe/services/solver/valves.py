"""Valve loss coefficients at the reference diameter (design §2.3).

The reference diameter D_ref is the inner diameter of the pipe connected to the valve's
inlet port (the end segment at that port); K is referenced to the velocity there.

- ``resistance`` given: K as entered; Cv → ``fluids.fittings.Cv_to_K(Cv, D_ref)``;
  Kv → ``fluids.fittings.Kv_to_K(Kv, D_ref)`` (``coefficients.k_from_coefficient``,
  ISA-75.01.01-2007).
- ``resistance`` a project library entry (``{kind: 'library', id}``, CLAUDE.md D22): its Cv or
  Kv converted as one entered on the valve, its K moved from the bore it is stated at to D_ref,
  K₀ (D_ref/d₀)⁴ (``project_library.entry_k``): the K of the same coefficient typed on the valve.
- No resistance: the Crane TP-410 (2009) full-bore, fully open K for the valve type at D_ref,
  via the fluids Crane functions with their default fully turbulent friction factor
  fd = ft_Crane(D_ref). Crane's K values are "not valid in the laminar regime" (fluids
  docstrings), so a Crane default in laminar flow is flagged, and so is one evaluated outside
  the sizes its table covers (the butterfly valve's 2"-24", the ``sizeRange`` of the inline
  fitting with the same correlation in data/fittings.json).
- Control valves (PRV, PSV, FCV) without a resistance are ideal: K = 0 when fully open, an
  assumption stated in the results (EPANET's valves are ideal unless given a minor loss).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import fluids.fittings

from ...models.components import CheckValve, ControlValve, IsolationValve, ReliefValve
from ...models.project_library import ResistanceRef
from .coefficients import k_from_coefficient
from .fittings import load_fittings, size_warning
from .project_library import EntryK, ResistanceEntries, entry_k

ResistanceValve = IsolationValve | CheckValve | ControlValve
"""The valves with a resistance (a K, Cv or Kv, or a default)."""
Valve = ResistanceValve | ReliefValve
"""Every element in ``BuiltNetwork.valves``: a relief valve is a valve link too, whose status
rule is the check valve's (proposal pressure-relief-valve.md decision 10)."""

_CRANE = "Crane Co. TP-410 Flow of Fluids Through Valves, Fittings, and Pipe (2009), via fluids"


@dataclass(frozen=True)
class CraneDefault:
    call: str
    """The fluids call, written out for the trace."""
    k: Callable[[float], float]
    fitting: str | None = None
    """The inline fitting type (data/fittings.json) with the same correlation, whose size
    range, if it has one, applies to the default as well."""


CRANE_DEFAULTS: dict[str, CraneDefault] = {
    "gate": CraneDefault(
        "fluids.fittings.K_gate_valve_Crane(D1=D, D2=D, angle=0)",
        lambda d: float(fluids.fittings.K_gate_valve_Crane(D1=d, D2=d, angle=0.0)),
        "gate_valve",
    ),
    "ball": CraneDefault(
        "fluids.fittings.K_ball_valve_Crane(D1=D, D2=D, angle=0)",
        lambda d: float(fluids.fittings.K_ball_valve_Crane(D1=d, D2=d, angle=0.0)),
        "ball_valve",
    ),
    "globe": CraneDefault(
        "fluids.fittings.K_globe_valve_Crane(D1=D, D2=D)",
        lambda d: float(fluids.fittings.K_globe_valve_Crane(D1=d, D2=d)),
        "globe_valve",
    ),
    "butterfly": CraneDefault(
        "fluids.fittings.K_butterfly_valve_Crane(D, style=0) (centric)",
        lambda d: float(fluids.fittings.K_butterfly_valve_Crane(D=d, style=0)),
        "butterfly_valve",
    ),
    "check": CraneDefault(
        "fluids.fittings.K_swing_check_valve_Crane(D, angled=True) (swing check, angled)",
        lambda d: float(fluids.fittings.K_swing_check_valve_Crane(D=d, angled=True)),
        "swing_check_valve",
    ),
    "stop_check": CraneDefault(
        "fluids.fittings.K_globe_stop_check_valve_Crane(D1=D, D2=D, style=0)",
        lambda d: float(fluids.fittings.K_globe_stop_check_valve_Crane(D1=d, D2=d, style=0)),
    ),
}
"""Default K per valve type (design §2.3), each a fluids 1.3.1 Crane function at D_ref."""

IDEAL_CONTROL_VALVE = (
    "ideal control valve: no loss when fully open (K = 0); give a resistance for a real valve"
)


@dataclass(frozen=True)
class ValveResistance:
    k: float
    """Fully open K on the reference diameter."""
    source: str
    origin: Literal["user", "library", "default"]
    """'user': K, Cv or Kv entered; 'library': Crane default; 'default': ideal control valve."""
    crane: bool
    """True for a Crane default (not valid in laminar flow)."""
    range_note: str | None = None
    """A Crane default evaluated outside the sizes its table covers (flagged)."""
    coefficient: Literal["K", "Cv", "Kv"] | None = None
    """The kind of the coefficient entered, on the valve or in its project library entry (None:
    a Crane default or an ideal control valve)."""
    entry: EntryK | None = None
    """The project library entry the K comes from (None: none)."""


def valve_resistance(
    valve: ResistanceValve, d_ref: float, entries: ResistanceEntries | None = None
) -> ValveResistance:
    """Fully open K of a valve on its reference diameter d_ref (design §2.3). ``entries``: the
    project's resistance entries by id, for a valve that refers to one (every reference
    resolves: a dangling one is a topology issue, ``builder.validate_topology``)."""
    resistance = valve.resistance
    if isinstance(resistance, ResistanceRef):
        use = entry_k((entries or {})[resistance.id], d_ref)
        return ValveResistance(use.k, use.how, "user", False, coefficient=use.entry.kind, entry=use)
    if resistance is not None:
        k, source = k_from_coefficient(resistance, d_ref)
        return ValveResistance(k, source, "user", False, coefficient=resistance.kind)
    if isinstance(valve, ControlValve):
        return ValveResistance(0.0, IDEAL_CONTROL_VALVE, "default", False)
    default = CRANE_DEFAULTS[valve.valve_type]
    note = (
        size_warning(load_fittings()[default.fitting], d_ref)
        if default.fitting is not None
        else None
    )
    return ValveResistance(
        default.k(d_ref), f"{_CRANE} {default.call}, D = {d_ref:g} m", "library", True, note
    )
