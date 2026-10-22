"""Element laws h(Q), dh/dQ at Q > 0, Q = 0 and Q < 0 in every flow regime (design §2).

Expected head losses are written out from Darcy–Weisbach with fluids' own friction factor
(``fluids.friction.Colebrook``) and fitting functions, never from solver code.
"""

import math
import random
from collections.abc import Callable

import numpy as np
import pytest
from fluids.constants import g
from fluids.fittings import contraction_sharp, diffuser_sharp
from fluids.friction import Colebrook

from opensolve_pipe.models.piping import Fitting
from opensolve_pipe.services.solver.elements import (
    HeadOffsetArrays,
    HeadOffsetLaw,
    KTangent,
    PipeConnectionLaw,
    PipeSegment,
    segment_state,
)
from opensolve_pipe.services.solver.fittings import resolve_fitting
from opensolve_pipe.services.solver.friction import FlowRegime, FrictionMethod

NU = 1.0e-6  # m²/s, test input
L, D, EPS = 50.0, 0.08, 4.5e-5


def segment(length: float = L, diameter: float = D, roughness: float = EPS) -> PipeSegment:
    return PipeSegment(
        length=length,
        diameter=diameter,
        roughness=roughness,
        area=math.pi * diameter**2 / 4,
        kinematic_viscosity=NU,
        g=g,
    )


def flow_at(re: float, diameter: float = D) -> float:
    return re * NU * math.pi * diameter / 4  # Re = 4Q/(π D ν)


def law(*segments: PipeSegment, fittings: tuple[Fitting, ...] = ()) -> PipeConnectionLaw:
    diameters = [s.diameter for s in segments]
    resolved = [resolve_fitting(i, f, diameters) for i, f in enumerate(fittings)]
    return PipeConnectionLaw(list(segments), resolved, "colebrook", g)


def numeric_slope(pl: PipeConnectionLaw, q: float) -> float:
    h = abs(q) * 1e-6
    return (pl.evaluate(q + h)[0] - pl.evaluate(q - h)[0]) / (2 * h)


def turbulent_friction(q: float, s: PipeSegment) -> float:
    """Darcy–Weisbach f (L/D) v|v|/(2g) with f from fluids.friction.Colebrook (turbulent only)."""
    v = q / (math.pi * s.diameter**2 / 4)
    re = abs(v) * s.diameter / NU
    assert re >= 4000.0  # the expectation below is the turbulent law
    return Colebrook(re, s.roughness / s.diameter) * s.length / s.diameter * v * abs(v) / (2 * g)


def central_difference(h: Callable[[float], float], q: float) -> float:
    step = abs(q) * 1e-6
    return (h(q + step) - h(q - step)) / (2 * step)


@pytest.mark.parametrize("re", [10.0, 500.0, 1999.0])
def test_laminar_law_is_hagen_poiseuille(re: float) -> None:
    q = flow_at(re)
    h, slope = law(segment()).evaluate(q)
    # Hagen–Poiseuille: Δh = 128 ν L Q / (g π D⁴)
    expected = 128 * NU * L * q / (g * math.pi * D**4)
    assert h == pytest.approx(expected, rel=1e-12)
    assert slope == pytest.approx(expected / q, rel=1e-12)
    assert segment_state(segment(), q, "colebrook").regime is FlowRegime.LAMINAR


@pytest.mark.parametrize("re", [4001.0, 2.0e4, 5.0e5])
def test_turbulent_law_is_darcy_weisbach_with_colebrook(re: float) -> None:
    q = flow_at(re)
    pl = law(segment())
    h, slope = pl.evaluate(q)
    v = q / (math.pi * D**2 / 4)
    expected = Colebrook(re, EPS / D) * L / D * v * v / (2 * g)
    assert h == pytest.approx(expected, rel=1e-12)
    assert slope == pytest.approx(numeric_slope(pl, q), rel=1e-6)
    assert segment_state(segment(), q, "colebrook").regime is FlowRegime.TURBULENT


@pytest.mark.parametrize("re", [2000.0, 2500.0, 3500.0])
def test_transition_slope_is_exact(re: float) -> None:
    pl = law(segment())
    q = flow_at(re)
    assert pl.evaluate(q)[1] == pytest.approx(numeric_slope(pl, q), rel=1e-6)
    assert segment_state(segment(), q, "colebrook").regime is FlowRegime.TRANSITIONAL


@pytest.mark.parametrize("re", [2000.0, 4000.0])
def test_head_loss_and_slope_are_continuous_at_regime_boundaries(re: float) -> None:
    pl = law(segment())
    q = flow_at(re)
    below, above = pl.evaluate(q * (1 - 1e-12)), pl.evaluate(q * (1 + 1e-12))
    assert below[0] == pytest.approx(above[0], rel=1e-9)
    assert below[1] == pytest.approx(above[1], rel=1e-9)


def test_zero_flow_has_zero_loss_and_the_laminar_slope() -> None:
    a, b = segment(), segment(length=20.0, diameter=0.05)
    h, slope = law(a, b, fittings=(Fitting(type="exit", pipe_index=1),)).evaluate(0.0)
    assert h == 0.0
    r_lam = sum(128 * NU * s.length / (g * math.pi * s.diameter**4) for s in (a, b))
    assert slope == pytest.approx(r_lam, rel=1e-12)
    assert slope > 0
    state = segment_state(a, 0.0, "colebrook")
    assert (state.regime, state.reynolds, state.friction_factor) == (FlowRegime.NONE, 0.0, 0.0)


@pytest.mark.parametrize("re", [100.0, 3000.0, 1.0e5])
def test_reverse_flow_is_antisymmetric_without_reducers(re: float) -> None:
    pl = law(segment(), fittings=(Fitting(type="elbow_90_lr", quantity=3),))
    q = flow_at(re)
    h_pos, d_pos = pl.evaluate(q)
    h_neg, d_neg = pl.evaluate(-q)
    assert h_neg == -h_pos
    assert d_neg == d_pos
    assert h_pos > 0


def test_fittings_add_k_velocity_heads() -> None:
    fitting = Fitting(type="custom", k_override=2.0, quantity=3)
    q = flow_at(1.0e5)
    a = math.pi * D**2 / 4

    def expected(flow: float) -> float:  # h = f (L/D) v|v|/(2g) + n K v|v|/(2g)
        v = flow / a
        return turbulent_friction(flow, segment()) + 3 * 2.0 * v * abs(v) / (2 * g)

    h, d = law(segment(), fittings=(fitting,)).evaluate(q)
    assert h == pytest.approx(expected(q), rel=1e-12)
    assert d == pytest.approx(central_difference(expected, q), rel=1e-6)
    # The fitting's own increment, exactly: n K v²/(2g) and its slope 2 n K |Q|/(2 g A²).
    v = q / a
    h_plain, d_plain = law(segment()).evaluate(q)
    assert h - h_plain == pytest.approx(3 * 2.0 * v * v / (2 * g), rel=1e-12)
    assert d - d_plain == pytest.approx(2 * 3 * 2.0 * v / (2 * g) / a, rel=1e-12)


def test_reducer_loss_depends_on_flow_direction() -> None:
    big, small = segment(diameter=0.1), segment(diameter=0.05)
    pl = law(big, small, fittings=(Fitting(type="reducer_sudden"),))
    q = flow_at(1.0e5, 0.05)
    v_small = q / (math.pi * 0.05**2 / 4)
    friction_fwd = turbulent_friction(q, big) + turbulent_friction(q, small)
    friction_rev = turbulent_friction(-q, big) + turbulent_friction(-q, small)
    # Forward: large -> small, contraction (Crane), K on the small pipe.
    k_c = contraction_sharp(0.1, 0.05, method="Crane")
    assert pl.evaluate(q)[0] == pytest.approx(friction_fwd + k_c * v_small**2 / (2 * g), rel=1e-12)
    # Reverse: small -> large, expansion (1 − β²)², K on the small pipe.
    k_e = diffuser_sharp(0.05, 0.1)
    assert pl.evaluate(-q)[0] == pytest.approx(friction_rev - k_e * v_small**2 / (2 * g), rel=1e-12)
    assert k_c != k_e
    # The reducer's own increment, exactly, against the same segments without it.
    plain = law(big, small)
    assert pl.evaluate(q)[0] - plain.evaluate(q)[0] == pytest.approx(
        k_c * v_small**2 / (2 * g), rel=1e-12
    )
    assert pl.evaluate(-q)[0] - plain.evaluate(-q)[0] == pytest.approx(
        -k_e * v_small**2 / (2 * g), rel=1e-12
    )
    assert pl.evaluate(q)[1] == pytest.approx(numeric_slope(pl, q), rel=1e-6)
    assert pl.evaluate(-q)[1] == pytest.approx(numeric_slope(pl, -q), rel=1e-6)


def test_head_offset_law() -> None:
    offset = HeadOffsetLaw()
    assert offset.evaluate(0.3) == (0.0, 0.0)
    offset.offset = 1.25
    assert offset.evaluate(-2.0) == (1.25, 0.0)


def test_connection_needs_a_segment() -> None:
    with pytest.raises(ValueError, match="at least one segment"):
        PipeConnectionLaw([], [], "colebrook", g)


def _random_offset_laws(rng: random.Random, n_links: int) -> list[HeadOffsetLaw]:
    """Offset laws of every kind the builder makes: constants (valves with K = 0, ideal legs),
    Darby legs (no tangent, the leg its own reference), Crane legs with tangents whose range
    the iterate leaves on either side, and references and own flows of either sign or zero."""
    laws = []
    for i in range(200):
        law = HeadOffsetLaw(offset=rng.choice([0.0, rng.uniform(-3.0, 3.0)]))
        kind = i % 4
        if kind:
            law.own = rng.randrange(n_links)
            reference = law.own if kind == 1 else rng.randrange(n_links)
            tangent = None
            if kind >= 2:
                k0 = rng.uniform(-1.0, 2.0)
                tangent = KTangent(
                    k0,
                    rng.choice([0.0, rng.uniform(-5.0, 5.0)]),
                    rng.uniform(0.0, 1.0),
                    kind == 3,
                    k0 - rng.choice([0.0, rng.uniform(0.0, 0.3)]),
                    k0 + rng.choice([0.0, rng.uniform(0.0, 0.3)]),
                )
            law.set(law.offset, rng.choice([0.0, rng.uniform(-50.0, 50.0)]), reference, tangent)
        laws.append(law)
    return laws


def test_head_offset_arrays_are_bit_identical_to_the_scalar_laws() -> None:
    """The GGA evaluates every offset law at once (``HeadOffsetArrays``); each value must be the
    scalar law's to the last bit, so the vectorized inner loop gives the same results."""
    rng = random.Random(20261022)
    n_links = 12
    laws = _random_offset_laws(rng, n_links)
    arrays = HeadOffsetArrays(laws)
    for _ in range(50):
        flows = np.array(
            [rng.choice([0.0, -0.0, rng.uniform(-0.05, 0.05)]) for _ in range(n_links)]
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            heads, slopes = arrays.heads(flows), arrays.own_slopes(flows)
        expected_heads = np.array([law.head(flows) for law in laws])
        expected_slopes = np.array([law.own_slope(flows) for law in laws])
        assert heads.tobytes() == expected_heads.tobytes()
        assert slopes.tobytes() == expected_slopes.tobytes()


@pytest.mark.parametrize("method", ["colebrook", "swamee_jain"])
def test_connection_law_is_the_sum_of_its_segment_states_to_the_bit(method: FrictionMethod) -> None:
    """``PipeConnectionLaw.evaluate`` precomputes the segment constants for the GGA's inner
    loop; its values must be those of ``segment_state`` (which the results report) summed over
    the segments, plus the fittings, to the last bit, in every regime and both directions."""
    segments = [segment(), segment(30.0, 0.05, 1.0e-4), segment(5.0, 0.1023, 4.6e-5)]
    diameters = [s.diameter for s in segments]
    fittings = [resolve_fitting(0, Fitting(type="elbow_90_lr", quantity=2), diameters)]
    law = PipeConnectionLaw(segments, fittings, method, g)
    for re in (0.0, 1.0e-3, 500.0, 1999.9, 2000.0, 3000.0, 3999.9, 4000.0, 1.0e5, 3.0e6):
        for sign in (1.0, -1.0):
            q = sign * flow_at(re)
            h, slope = 0.0, 0.0
            for s in segments:
                state = segment_state(s, q, method)
                h += state.head_loss
                slope += state.slope
            minor = law._minor_reverse if q < 0 else law._minor_forward
            expected = (h + minor * q * abs(q), slope + 2.0 * minor * abs(q))
            assert law.evaluate(q) == expected
