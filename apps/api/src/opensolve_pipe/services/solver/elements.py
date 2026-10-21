"""Link laws h(Q) and dh/dQ (design §2). h is positive in the direction of positive Q.

Pipe connection (segments in series, plus inline fittings), Darcy–Weisbach:

- segment k, Re_k = |Q| D_k / (A_k ν):
  laminar (Re < 2000): h = r_lam Q with r_lam = 32 ν L / (g D² A), which is
  f (L/D) v|v|/(2g) with f = 64/Re written out (= 128 ν L / (g π D⁴)); slope r_lam > 0, so
  the law stays regular at Q = 0;
  otherwise: h = f (L/D) Q|Q| / (2 g A²) and the exact slope
  dh/dQ = L/(2 g D A²) · (2 f |Q| + Q² df/d|Q|), df/d|Q| = df/dRe · D/(A ν).
- fitting j: h = n_j K_j Q|Q| / (2 g A_j²), slope 2 n_j K_j |Q| / (2 g A_j²), with K_j and the
  reference area A_j for the current flow direction (reducers differ by direction).

Branch legs are pure head offsets within one inner solve (slope 0); the GGA imposes them
exactly by merging the branch's nodes, so they never enter its Jacobian.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .fittings import ResolvedFitting
from .friction import FlowRegime, FrictionMethod, flow_regime, friction_factor
from .library import ResolvedPipe


@dataclass(frozen=True)
class PipeSegment:
    """Geometry and fluid of one segment, with the constants of its loss law."""

    length: float
    diameter: float
    roughness: float
    area: float
    kinematic_viscosity: float
    g: float

    @classmethod
    def from_resolved(
        cls, pipe: ResolvedPipe, kinematic_viscosity: float, g: float
    ) -> "PipeSegment":
        area = 0.25 * math.pi * pipe.inner_diameter**2
        return cls(
            length=pipe.length,
            diameter=pipe.inner_diameter,
            roughness=pipe.roughness,
            area=area,
            kinematic_viscosity=kinematic_viscosity,
            g=g,
        )

    @property
    def relative_roughness(self) -> float:
        return self.roughness / self.diameter

    @property
    def laminar_resistance(self) -> float:
        """r_lam = 32 ν L / (g D² A), s/m²."""
        return (
            32.0 * self.kinematic_viscosity * self.length / (self.g * self.diameter**2 * self.area)
        )

    def reynolds(self, flow: float) -> float:
        return abs(flow) * self.diameter / (self.area * self.kinematic_viscosity)


@dataclass(frozen=True)
class SegmentState:
    velocity: float
    reynolds: float
    friction_factor: float
    """Darcy f; 0 when there is no flow (f = 64/Re is unbounded there)."""
    regime: FlowRegime
    head_loss: float
    slope: float


def segment_state(segment: PipeSegment, flow: float, method: FrictionMethod) -> SegmentState:
    """Friction loss, its slope, and the intermediate values for one segment at flow Q."""
    re = segment.reynolds(flow)
    regime = flow_regime(re)
    velocity = flow / segment.area
    if regime in (FlowRegime.NONE, FlowRegime.LAMINAR):
        r_lam = segment.laminar_resistance
        f = friction_factor(re, segment.relative_roughness, method)[0] if re > 0 else 0.0
        return SegmentState(velocity, re, f, regime, r_lam * flow, r_lam)
    f, df_dre = friction_factor(re, segment.relative_roughness, method)
    c = segment.length / (segment.diameter * 2.0 * segment.g * segment.area**2)
    df_dq = df_dre * segment.diameter / (segment.area * segment.kinematic_viscosity)
    h = f * c * flow * abs(flow)
    slope = c * (2.0 * f * abs(flow) + df_dq * flow * flow)
    return SegmentState(velocity, re, f, regime, h, slope)


class PipeConnectionLaw:
    """Law of one pipe connection: segments in series plus inline fittings."""

    def __init__(
        self,
        segments: Sequence[PipeSegment],
        fittings: Sequence[ResolvedFitting],
        method: FrictionMethod,
        g: float,
    ) -> None:
        if not segments:
            raise ValueError("a pipe connection needs at least one segment")
        self.segments = tuple(segments)
        self.fittings = tuple(fittings)
        self.method: FrictionMethod = method
        self.g = g
        # Σ n K / (2 g A²) for each flow direction [s²/m⁵].
        self._minor_forward = sum(self._minor_coefficient(f, 1.0) for f in self.fittings)
        self._minor_reverse = sum(self._minor_coefficient(f, -1.0) for f in self.fittings)

    def _minor_coefficient(self, fitting: ResolvedFitting, flow: float) -> float:
        area = self.segments[fitting.segment(flow)].area
        return fitting.quantity * fitting.k(flow) / (2.0 * self.g * area**2)

    def fitting_head_loss(self, fitting: ResolvedFitting, flow: float) -> float:
        """Head loss of all units of one fitting, signed like the flow, m."""
        return self._minor_coefficient(fitting, flow) * flow * abs(flow)

    def evaluate(self, flow: float) -> tuple[float, float]:
        h = 0.0
        slope = 0.0
        for segment in self.segments:
            state = segment_state(segment, flow, self.method)
            h += state.head_loss
            slope += state.slope
        minor = self._minor_reverse if flow < 0 else self._minor_forward
        return h + minor * flow * abs(flow), slope + 2.0 * minor * abs(flow)


class HeadOffsetLaw:
    """A head offset that does not depend on the flow within one inner solve (branch legs).

    The outer loop sets ``offset`` (design §2.4, §5.4); lossModel 'ideal' keeps it at 0, an
    EPANET-style junction. The slope is 0, so the GGA does not iterate on these links: it
    merges their end nodes with fixed head shifts (``gga.merge_offset_links``).
    """

    def __init__(self, offset: float = 0.0) -> None:
        self.offset = offset

    def evaluate(self, flow: float) -> tuple[float, float]:
        return self.offset, 0.0


@dataclass(frozen=True)
class PendingLaw:
    """Placeholder for element laws that arrive in milestone M3 (pumps and valves)."""

    element: str

    def evaluate(self, flow: float) -> tuple[float, float]:
        raise NotImplementedError(
            f"{self.element}: this element's hydraulic law is not implemented yet "
            "(pumps and valves arrive in milestone M3)"
        )
