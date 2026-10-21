"""One-segment pipe connections for the M3 derivations: geometry, fittings and head loss.

A ``Line`` is one custom pipe segment (inner diameter, length, absolute roughness: test inputs)
with inline fittings on it, all referenced to its own velocity. Its head loss is the Darcy–
Weisbach law of design §2.1 from ``derivations`` (friction factor and fitting K from the cited
fluids functions), so the M3 cases share the M2 cases' pipe physics.
"""

import functools
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from opensolve_pipe.models.piping import FittingType, PipeConnection
from tests.reference import derivations as dv
from tests.reference.case_format import (
    FrictionMethod,
    ReferenceCase,
    connect,
    custom_pipe,
    fitting,
)

_K_FUNCTIONS = {
    "entrance_sharp": lambda d: dv.k_entrance_sharp(),
    "exit": lambda d: dv.k_exit(),
    "elbow_90_lr": dv.k_elbow_90_lr,
    "gate_valve": dv.k_gate_valve,
}
"""The fitting types the M3 lines use, with design §3's fluids function (via derivations)."""

FITTING_SOURCES: dict[FittingType, str] = {
    "entrance_sharp": "entrance_sharp(method='Crane')",
    "exit": "exit_normal()",
    "elbow_90_lr": "bend_rounded_Crane(Di, 90, bend_diameters=1.5)",
    "gate_valve": "K_gate_valve_Crane(Di, Di, 0)",
}
"""The fluids call behind each fitting type in ``_K_FUNCTIONS``, for case sources."""


def cite_line_fittings(
    derive: Callable[[], ReferenceCase],
) -> Callable[[], ReferenceCase]:
    """A case generator whose ``source`` also names the fluids function of every fitting type
    its lines use (as the M2 sources do), unless the method text already names it."""

    @functools.wraps(derive)
    def cited() -> ReferenceCase:
        case = derive()
        used = sorted({f.type for c in case.project.connections for f in c.piping.fittings})
        unknown = [t for t in used if t not in FITTING_SOURCES]
        if unknown:
            raise ValueError(f"{case.name}: no source text for fittings {unknown}")
        calls = [FITTING_SOURCES[t] for t in used]
        missing = [c for c in calls if c.split("(")[0] not in case.source]
        if not missing:
            return case
        if not case.source.endswith(")"):
            raise ValueError(f"{case.name}: unexpected source format")
        return replace(
            case, source=f"{case.source[:-1]}; line fittings: fluids {', '.join(missing)})"
        )

    return cited


ROUGHNESS = 4.5e-5
"""m; the absolute roughness of the M3 lines (a test input, as in the M2 cases)."""


@dataclass(frozen=True)
class Line:
    d: float
    length: float
    fittings: tuple[tuple[FittingType, int], ...] = ()
    eps: float = ROUGHNESS

    @property
    def area(self) -> float:
        return dv.area(self.d)

    def k_total(self) -> float:
        """Σ n_j K_j of the fittings, on this pipe's velocity."""
        return sum(n * float(_K_FUNCTIONS[kind](self.d)) for kind, n in self.fittings)

    def head_loss(self, q: float, nu: float, method: FrictionMethod = "colebrook") -> float:
        """EGL drop along the connection, signed like q: f (L/D) v|v|/2g + ΣK v|v|/2g."""
        return dv.friction_head_loss(
            q, self.d, self.length, self.eps, nu, method
        ) + dv.minor_head_loss(q, self.k_total(), self.d)

    def velocity(self, q: float) -> float:
        return dv.velocity(q, self.d)

    def connect(self, cid: str, from_port: str, to_port: str) -> PipeConnection:
        return connect(
            cid,
            from_port,
            to_port,
            [custom_pipe(self.d, self.length, self.eps)],
            [fitting(kind, quantity=n) for kind, n in self.fittings],
        )


def require_turbulent(nu: float, pairs: Sequence[tuple[float, Line]]) -> None:
    """Guard: every listed (flow, line) is turbulent at the solution (Crane K values are not
    valid in laminar flow, design §2.3)."""
    for q, line in pairs:
        dv.require_regime(q, line.d, nu, "turbulent")
