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

Valve (open, design §2.3): h = h_c + K Q|Q| / (2 g A_ref²), slope 2 K |Q| / (2 g A_ref²), with
K at the reference (inlet pipe) area and h_c the check valve's cracking head (0 otherwise).

Equipment (proposal equipment-pressure-drop.md §3.1): h = c Q|Q|, slope 2 c |Q|, with c from
the element's rating (a rated point, or a Cv or Kv).

Pump (running, design §2.2): h = −H(Q) with H the curve at speed (``pumps.PumpCurveModel``),
slope −dH/dQ (positive on a falling curve).

Head offsets (``HeadOffsetLaw``) have slope 0 and are not Newton links: branch legs, valves
with K = 0 (an ideal control valve fully open). The GGA imposes them exactly by merging their
nodes (``gga.merge_offset_links``), so they never enter its Jacobian. A branch leg's offset
depends on flows (K v²/2g of a reference leg); the GGA re-evaluates it after every Newton step
with the current flows, and the outer loop updates K.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .fittings import ResolvedFitting
from .friction import (
    RE_LAMINAR_MAX,
    FlowRegime,
    FrictionMethod,
    flow_regime,
    friction_factor,
)
from .library import ResolvedPipe
from .pumps import PumpCurveModel


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
        # Per segment, the constants ``segment_state`` computes from it, each the same
        # expression: (D, A ν, r_lam, ε/D, L / (2 g D A²)).
        self._terms = tuple(
            (
                s.diameter,
                s.area * s.kinematic_viscosity,
                s.laminar_resistance,
                s.relative_roughness,
                s.length / (s.diameter * 2.0 * s.g * s.area**2),
            )
            for s in self.segments
        )

    def _minor_coefficient(self, fitting: ResolvedFitting, flow: float) -> float:
        area = self.segments[fitting.segment(flow)].area
        return fitting.quantity * fitting.k(flow) / (2.0 * self.g * area**2)

    def fitting_head_loss(self, fitting: ResolvedFitting, flow: float) -> float:
        """Head loss of all units of one fitting, signed like the flow, m."""
        return self._minor_coefficient(fitting, flow) * flow * abs(flow)

    def evaluate(self, flow: float) -> tuple[float, float]:
        """h and dh/dQ: the sums of ``segment_state``'s head losses and slopes over the
        segments, written out with its constants precomputed (the GGA's inner loop calls this
        for every pipe at every iterate), plus the fittings."""
        h = 0.0
        slope = 0.0
        q_abs = abs(flow)
        for diameter, area_nu, r_lam, ed, c in self._terms:
            re = q_abs * diameter / area_nu
            if re < RE_LAMINAR_MAX:  # laminar, or no flow (``flow_regime``)
                h += r_lam * flow
                slope += r_lam
                continue
            f, df_dre = friction_factor(re, ed, self.method)
            df_dq = df_dre * diameter / area_nu
            h += f * c * flow * q_abs
            slope += c * (2.0 * f * q_abs + df_dq * flow * flow)
        minor = self._minor_reverse if flow < 0 else self._minor_forward
        return h + minor * flow * q_abs, slope + 2.0 * minor * q_abs


@dataclass(frozen=True)
class KTangent:
    """A branch path's K as a tangent line in the flow fraction q (design §5.4):
    K(q) = k0 + dk_dq (q − q0), with q = −Q_own/Q_ref for the branch path and
    q = 1 + Q_own/Q_ref for the run path (q is always the branch's share of the combined flow,
    as the Crane functions define it; in the pattern the leg's flow runs opposite to the
    combined leg's, both drawn from the center). The outer loop re-centres it on the solved
    split."""

    k0: float
    dk_dq: float
    q0: float
    run_path: bool
    k_min: float = -math.inf
    k_max: float = math.inf
    """The range of the correlation's K over 0 <= q <= 1: the tangent is held inside it, so an
    iterate far from q0 never sees a K the correlation cannot give."""


class HeadOffsetLaw:
    """A head offset, imposed exactly by merging nodes (branch legs, valves with K = 0).

    h = offset + coefficient · Q_ref|Q_ref| · K, with Q_ref the flow of link ``reference`` in
    the current iterate and K = 1, or K(q) from ``tangent`` (a Crane path, design §2.4 and
    §5.4); ``coefficient`` = 0 gives a constant (lossModel 'ideal' keeps every leg at 0, an
    EPANET-style junction). The GGA does not iterate on these links: it merges their end nodes
    with head shifts (``gga.merge_offset_links``) and re-evaluates the offsets after every step.
    ``own_slope`` (dh/dQ of the leg's own flow, link ``own``) enters the Jacobian of the pipe
    in series with the leg, so a loss that grows with the leg's own flow (a branch's velocity
    head inside its Crane K, a Darby fallback leg) is part of Newton's step.
    """

    def __init__(self, offset: float = 0.0, coefficient: float = 0.0, reference: int = -1):
        self.offset = offset
        self.coefficient = coefficient
        self.reference = reference
        self.own = -1
        """This leg's own link index (set by the builder for branch legs; -1 otherwise)."""
        self.tangent: KTangent | None = None

    def set(
        self,
        offset: float = 0.0,
        coefficient: float = 0.0,
        reference: int = -1,
        tangent: KTangent | None = None,
    ) -> None:
        self.offset, self.coefficient, self.reference = offset, coefficient, reference
        self.tangent = tangent

    def fraction(self, flows: NDArray[np.float64]) -> float | None:
        """The branch flow fraction q of the current iterate (tangent laws), None at Q_ref = 0.
        Signed: an iterate whose leg flow has reversed gets q < 0 (branch path) or q > 1 (run
        path), on the same tangent line, so the law stays continuous and monotone through a
        zero leg flow; mirroring it about zero (|Q_own|) made Newton creep or stall there."""
        assert self.tangent is not None
        q_ref = float(flows[self.reference])
        if q_ref == 0.0:
            return None
        ratio = -float(flows[self.own]) / q_ref
        return 1.0 - ratio if self.tangent.run_path else ratio

    def k(self, flows: NDArray[np.float64]) -> float:
        """The K factor multiplying coefficient · Q_ref|Q_ref| (1 without a tangent): the
        tangent at the iterate's split, held inside the range of K the correlation gives over
        0 <= q <= 1, so an iterate whose split has left the pattern the tangent was built for
        never sees a K the correlation cannot give."""
        if self.tangent is None:
            return 1.0
        q = self.fraction(flows)
        t = self.tangent
        if q is None:
            return t.k0
        k = t.k0 + t.dk_dq * (q - t.q0)
        return min(max(k, t.k_min), t.k_max)

    def head(self, flows: NDArray[np.float64]) -> float:
        """The offset at the given link flows, m."""
        if self.coefficient == 0.0:
            return self.offset
        q = float(flows[self.reference])
        return self.offset + self.coefficient * q * abs(q) * self.k(flows)

    def own_slope(self, flows: NDArray[np.float64]) -> float:
        """d(head)/dQ_own at the given flows, Q_own the flow of link ``own`` (0 if none)."""
        if self.coefficient == 0.0 or self.own < 0:
            return 0.0
        q_ref = float(flows[self.reference])
        if self.tangent is None:
            return 2.0 * self.coefficient * abs(q_ref) if self.reference == self.own else 0.0
        q = self.fraction(flows)
        if q is None:
            return 0.0  # no combined flow
        t = self.tangent
        k = t.k0 + t.dk_dq * (q - t.q0)
        if k < t.k_min or k > t.k_max:
            return 0.0  # K held at a bound of the correlation's range
        dq = -1.0 / q_ref  # dq/dQ_own of the branch path; the run path's is the opposite
        if self.tangent.run_path:
            dq = -dq
        return self.coefficient * q_ref * abs(q_ref) * self.tangent.dk_dq * dq

    def evaluate(self, flow: float) -> tuple[float, float]:
        """(h, 0) for a flow-independent offset; a flow-dependent one needs ``head(flows)``."""
        if self.coefficient != 0.0:
            raise ValueError("a flow-dependent head offset is evaluated with head(flows)")
        return self.offset, 0.0


class HeadOffsetArrays:
    """``HeadOffsetLaw.head`` and ``own_slope`` of many laws at once, for the GGA's inner loop.

    Every value is the scalar method's, operation for operation (IEEE arithmetic only, in the
    same order, and the same comparisons for the branches and for ``min``/``max``), so the
    results are bit-identical (``tests/unit/test_elements.py``). The laws must not change
    while the arrays are in use: the outer loop sets them only between inner solves."""

    def __init__(self, laws: Sequence[HeadOffsetLaw]) -> None:
        self.offset = np.array([law.offset for law in laws], dtype=np.float64)
        self.coefficient = np.array([law.coefficient for law in laws], dtype=np.float64)
        self.reference = np.array([law.reference for law in laws], dtype=np.int64)
        self.own = np.array([law.own for law in laws], dtype=np.int64)
        tangents = [law.tangent for law in laws]
        self.has_tangent = np.array([t is not None for t in tangents], dtype=bool)
        self.k0 = np.array([t.k0 if t else 0.0 for t in tangents], dtype=np.float64)
        self.dk_dq = np.array([t.dk_dq if t else 0.0 for t in tangents], dtype=np.float64)
        self.q0 = np.array([t.q0 if t else 0.0 for t in tangents], dtype=np.float64)
        self.run_path = np.array([bool(t and t.run_path) for t in tangents], dtype=bool)
        self.k_min = np.array([t.k_min if t else -math.inf for t in tangents], dtype=np.float64)
        self.k_max = np.array([t.k_max if t else math.inf for t in tangents], dtype=np.float64)
        self.constant = self.coefficient == 0.0
        self.size = len(laws)

    def _tangent(self, flows: NDArray[np.float64]) -> tuple[NDArray[np.float64], ...]:
        """(Q_ref, q, unclipped tangent K) per law (``HeadOffsetLaw.fraction`` and ``k``)."""
        q_ref = flows[self.reference]
        ratio = -flows[self.own] / q_ref
        q = np.where(self.run_path, 1.0 - ratio, ratio)
        return q_ref, q, self.k0 + self.dk_dq * (q - self.q0)

    def heads(self, flows: NDArray[np.float64]) -> NDArray[np.float64]:
        """``HeadOffsetLaw.head`` of every law at the given link flows, m."""
        if self.size == 0:
            return np.zeros(0)
        q_ref, _, k = self._tangent(flows)
        k = np.where(self.k_min > k, self.k_min, k)  # max(k, k_min)
        k = np.where(self.k_max < k, self.k_max, k)  # min(..., k_max)
        k = np.where(q_ref == 0.0, self.k0, k)  # no combined flow: k0
        k = np.where(self.has_tangent, k, 1.0)
        return np.where(
            self.constant, self.offset, self.offset + self.coefficient * q_ref * np.abs(q_ref) * k
        )

    def own_slopes(self, flows: NDArray[np.float64]) -> NDArray[np.float64]:
        """``HeadOffsetLaw.own_slope`` of every law at the given link flows."""
        if self.size == 0:
            return np.zeros(0)
        q_ref, _, k = self._tangent(flows)
        dq = -1.0 / q_ref
        dq = np.where(self.run_path, -dq, dq)
        tangent = self.coefficient * q_ref * np.abs(q_ref) * self.dk_dq * dq
        tangent = np.where((k < self.k_min) | (k > self.k_max) | (q_ref == 0.0), 0.0, tangent)
        own_flow = np.where(self.reference == self.own, 2.0 * self.coefficient * np.abs(q_ref), 0.0)
        slope = np.where(self.has_tangent, tangent, own_flow)
        return np.where(self.constant | (self.own < 0), 0.0, slope)


class ValveLaw:
    """Open valve: h = h_c + K Q|Q| / (2 g A²) (design §2.3, §5.2), K > 0 at area A.

    ``cracking_head`` h_c = cracking pressure / (ρ g) for an active check valve (0 otherwise):
    the disc opens once the head difference exceeds it. The law is continuous through Q = 0
    (Newton may pass there); the status logic closes the valve on reverse flow.
    """

    def __init__(self, k: float, area: float, g: float, cracking_head: float = 0.0) -> None:
        if k <= 0.0:
            raise ValueError("a valve law needs K > 0; K = 0 is a head offset")
        self.k = k
        self.area = area
        self.cracking_head = cracking_head
        self._c = k / (2.0 * g * area * area)

    def loss(self, flow: float) -> float:
        """K Q|Q| / (2 g A²) alone (the fully open loss, without the cracking head)."""
        return self._c * flow * abs(flow)

    def evaluate(self, flow: float) -> tuple[float, float]:
        return self.cracking_head + self._c * flow * abs(flow), 2.0 * self._c * abs(flow)


class QuadraticLossLaw:
    """Equipment (proposal equipment-pressure-drop.md §3.1, §3.4): h = c Q|Q|, dh/dQ = 2 c |Q|,
    c > 0 in s²/m⁵ from the element's rating (``equipment.equipment_law``).

    ``ValveLaw``'s form without a cracking head, taking c itself rather than K and an area, so
    that the valves' arithmetic stays exactly as it is. The slope is 0 at Q = 0: the GGA floors
    it in its Jacobian only, as for every Newton link that is not a pipe
    (``gga.JACOBIAN_FLOOR_RELATIVE``), and the law itself stays exact.
    """

    def __init__(self, coefficient: float) -> None:
        if not (math.isfinite(coefficient) and coefficient > 0.0):
            raise ValueError("an equipment law needs a finite c > 0")
        self.coefficient = coefficient

    def evaluate(self, flow: float) -> tuple[float, float]:
        c = self.coefficient
        return c * flow * abs(flow), 2.0 * c * abs(flow)


class PumpLaw:
    """Running pump: h = −H(Q), dh/dQ = −dH/dQ, H from the curve at speed ratio s."""

    def __init__(self, curve: PumpCurveModel, speed: float) -> None:
        self.curve = curve
        self.speed = speed

    def evaluate(self, flow: float) -> tuple[float, float]:
        head, slope = self.curve.head(flow, self.speed)
        return -head, -slope
