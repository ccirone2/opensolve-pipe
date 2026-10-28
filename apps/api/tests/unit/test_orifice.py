"""The orifice plate (docs/proposals/orifice-plate.md §3, §4, §5.1-§5.2, §7.6): fluids' functions
and the transcription of ISO 5167-2 eq. (4), the cancellation-free K, the hold, the slope, the
move of an entered C, decision 17's bounds, the builder, the solve (zero, reverse and floating
flow, closed-off plates), the reading and the vena contracta, the flags, the trace, the methods
summary, scenarios and goal seek.

Expected values come from fluids' functions called directly, from closed forms written out here
(Borda-Carnot, ISO eq. (1), Skelton et al.'s worked ratio, a 60-digit evaluation of the loss
relation), from the proposal's measured cases (§7.1, by its prototypes), and from the same
network with the plate replaced by a gate valve of the same K, never from the orifice code
itself. Every bore, pipe, level and fluid below is a made-up test input.
"""

import math
from decimal import Decimal, localcontext
from itertools import pairwise
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from fluids.constants import g
from fluids.fittings import diffuser_sharp
from fluids.flow_meter import (
    C_Reader_Harris_Gallagher,
    K_to_discharge_coefficient,
    discharge_coefficient_to_K,
    dP_orifice,
    flow_meter_discharge,
)
from scipy.constants import foot

from opensolve_pipe.main import app
from opensolve_pipe.models.api import GoalSeekRequest
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services import goal_seek as gs
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.scenarios import solve_case, value_text
from opensolve_pipe.services.solver import orifice as orifice_module
from opensolve_pipe.services.solver import solve_project, system_curve
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.elements import PipeSegment, segment_state
from opensolve_pipe.services.solver.errors import TopologyError
from opensolve_pipe.services.solver.methods import (
    ORIFICE_ASSUMPTION,
    methods_summary,
)
from opensolve_pipe.services.solver.network import LinkKind
from opensolve_pipe.services.solver.orifice import (
    OrificeLaw,
    c_iso,
    dk_dc,
    k_of_c,
    ratio_range,
    re_lo,
    refusal,
    rhg_terms,
    s_of_c,
)

from .helpers import (
    assigned_flow,
    connection,
    custom_fluid,
    make_project,
    plug,
    project_dict,
    reservoir,
    tee,
)

D = 0.1023
"""m: the pipes' inner diameter (test input), as in the proposal's cases."""
RHO, MU = 998.0, 1.0e-3
"""Liquid A of the proposal's cases (the helpers' default custom fluid)."""
TAPS = ("corner", "flange", "d_and_d_2")
_clients = iter(range(1, 250))


def _client() -> TestClient:
    """A client of its own address, so the API's per-client limits never meet another test's."""
    return TestClient(app, client=(f"198.51.106.{next(_clients)}", 50000))


def _flags(state: SolvedState, code: str, element: str | None = "O1") -> list[Flag]:
    return [
        f for f in state.flags if f.code == code and (element is None or f.component_id == element)
    ]


def _limits(state: SolvedState) -> list[str]:
    return [str(f.details.get("limit")) for f in _flags(state, "CORRELATION_OUT_OF_RANGE")]


def _area(d: float) -> float:
    return math.pi * d * d / 4.0


def plate(
    cid: str = "O1",
    bore: float = 0.05115,
    *,
    taps: str | None = None,
    c: float | None = None,
    elevation: float = 3.0,
    inlet: float | None = None,
    outlet: float | None = None,
) -> dict[str, Any]:
    ports: list[dict[str, Any]] = [
        {"id": "inlet", "nominalSize": 0.1},
        {"id": "outlet", "nominalSize": 0.1},
    ]
    if inlet is not None:
        ports[0]["elevation"] = inlet
    if outlet is not None:
        ports[1]["elevation"] = outlet
    data: dict[str, Any] = {
        "type": "orifice",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "ports": ports,
        "boreDiameter": bore,
    }
    if taps is not None:
        data["taps"] = taps
    if c is not None:
        data["dischargeCoefficient"] = c
    return data


def gate(cid: str, k: float, *, elevation: float = 3.0, status: str = "active") -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": "gate",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "status": status,
        "resistance": {"kind": "K", "value": k},
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }


def line_dict(
    element: dict[str, Any],
    *,
    z1: float = 10.0,
    level1: float = 2.0,
    z2: float = 0.0,
    level2: float = 1.0,
    d_in: float = D,
    d_out: float = D,
    lengths: tuple[float, float] = (60.0, 40.0),
    **kw: Any,
) -> dict[str, Any]:
    """The proposal's C1 line: R1 (z 10, level 2 m) -> 60 m -> element -> 40 m -> R2 (z 0,
    level 1 m), 102.3 mm pipes with ε = 4.5e-5 m, liquid A."""
    eid = element["id"]
    comps = [
        reservoir("R1", elevation=z1, level=level1),
        element,
        reservoir("R2", elevation=z2, level=level2),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), (eid, "inlet"), length=lengths[0], diameter=d_in),
        connection("L2", (eid, "outlet"), ("R2", "port_1"), length=lengths[1], diameter=d_out),
    ]
    return project_dict(comps, conns, **kw)


def line(element: dict[str, Any], **kw: Any) -> Project:
    return Project.model_validate(line_dict(element, **kw))


# --------------------------------------------------------------------------- fluids and eq. (4)


def test_fluids_docstring_examples() -> None:
    """§7.6: the five fluids 1.3.1 functions the design rests on reproduce their docstrings, and
    the cancellation-free K gives discharge_coefficient_to_K's example."""
    c = C_Reader_Harris_Gallagher(
        D=0.07391, Do=0.0222, rho=1.165, mu=1.85e-5, m=0.12, taps="flange"
    )
    assert c == pytest.approx(0.5990326277163659, rel=1e-15)
    k = discharge_coefficient_to_K(D=0.07366, Do=0.05, C=0.61512)
    assert k == pytest.approx(5.2314291729754, rel=1e-13)
    assert K_to_discharge_coefficient(D=0.07366, Do=0.05, K=5.2314291729754) == pytest.approx(
        0.61512, rel=1e-13
    )
    assert dP_orifice(D=0.07366, Do=0.05, P1=200000.0, P2=183000.0, C=0.61512) == pytest.approx(
        9069.474705745388, rel=1e-13
    )
    m = flow_meter_discharge(
        D=0.0739, Do=0.0222, P1=1e5, P2=9.9e4, rho=1.1646, C=0.5988, expansibility=0.9975
    )
    assert m == pytest.approx(0.01120390943807026, rel=1e-13)
    assert k_of_c(0.07366, 0.05, 0.61512) == pytest.approx(5.2314291729754, rel=4e-15)


def _fluids_re(d_pipe: float, rho: float, mu: float, m: float) -> float:
    """The Re_D fluids computes inside C_Reader_Harris_Gallagher from a mass flow."""
    v = m / (0.25 * math.pi * d_pipe * d_pipe * rho)
    return rho * v * d_pipe / mu


@pytest.mark.parametrize("taps", TAPS)
def test_the_transcription_equals_fluids(taps: str) -> None:
    """§7.6: eq. (4) term by term (the trace's terms, the slope's source and decision 17's
    bounds) sums to fluids' C to 2e-15 over ISO's range and beyond it, and ``c_iso`` is fluids
    called with the mass flow whose Re_D is the one asked for."""
    worst = 0.0
    for d_pipe in (0.0525, 0.07, D, 0.3, 1.0):
        for beta in np.linspace(0.05, 0.9, 18):
            d = float(beta) * d_pipe
            for re in (5000.0, 7316.0, 1.0e5, 2.2e6, 1.0e8):
                m = 0.25 * math.pi * d_pipe * MU * re
                fluid_c = C_Reader_Harris_Gallagher(d_pipe, d, RHO, MU, m, {
                    "corner": "corner", "flange": "flange", "d_and_d_2": "D and D/2"
                }[taps])  # fmt: skip
                terms = rhg_terms(d_pipe, d, _fluids_re(d_pipe, RHO, MU, m), taps)
                worst = max(worst, abs(terms.total - fluid_c))
                assert c_iso(d_pipe, d, RHO, MU, re, taps) == fluid_c
    assert worst <= 2.0e-15


def test_k_times_the_velocity_head_is_isos_pressure_loss() -> None:
    """§7.6: K ρ v²/2 is fluids' dP_orifice of the eq. (1) differential pressure at the same
    flow and C; eq. (1) read back with fluids gives the mass flow; the C <-> K round trip."""
    for beta in (0.1, 0.3, 0.5, 0.65, 0.75, 0.9):
        d = beta * D
        for c in (0.3, 0.6, 0.62, 0.95):
            q = 0.012
            v = q / _area(D)
            dp = (1.0 - beta**4) / (c * c * beta**4) * RHO * v * v / 2.0
            loss = k_of_c(D, d, c) * RHO * v * v / 2.0
            assert loss == pytest.approx(dP_orifice(D, d, dp, 0.0, c), rel=1e-12)
            assert flow_meter_discharge(D, d, dp, 0.0, RHO, c) == pytest.approx(RHO * q, rel=1e-13)
            assert K_to_discharge_coefficient(D, d, k_of_c(D, d, c)) == pytest.approx(c, rel=1e-12)


def test_borda_carnot_at_c_1_and_skeltons_worked_ratio() -> None:
    """§7.6: at C = 1 the loss is the sudden expansion from the bore, fluids' diffuser_sharp on
    the bore's velocity times (D/d)⁴; Skelton et al. (NSFMW 2010) work β 0.4, C 0.602 to a
    pressure-loss ratio of 0.823 (fluids gives 0.82296)."""
    for beta in (0.1, 0.4, 0.7, 0.9):
        d = beta * D
        assert k_of_c(D, d, 1.0) == pytest.approx(
            diffuser_sharp(Di1=d, Di2=D) * (D / d) ** 4, rel=1e-13
        )
    d = 0.4 * D
    ratio = dP_orifice(D, d, 1.0, 0.0, 0.602)
    assert round(ratio, 3) == 0.823
    assert ratio == pytest.approx(0.82296, abs=5e-6)
    s = s_of_c(D, d, 0.602)
    cb2 = 0.602 * 0.4 * 0.4
    assert (s - cb2) / (s + cb2) == pytest.approx(ratio, rel=1e-14)


def _k_exact(d_pipe: float, d_bore: float, c: float) -> float:
    """K of the loss relation, (√(1 − β⁴(1 − C²))/(C β²) − 1)², in 60-digit decimals from the
    exact binary inputs: an independent reference where fluids' double form cancels."""
    with localcontext() as ctx:
        ctx.prec = 60
        beta = Decimal(d_bore) / Decimal(d_pipe)
        cc = Decimal(c)
        b4 = beta**4
        root = ((1 - b4 * (1 - cc * cc)).sqrt() / (cc * beta * beta)) - 1
        return float(root * root)


def test_the_cancellation_free_k() -> None:
    """Decision 8, §7.6: the cancellation-free K equals fluids' discharge_coefficient_to_K to
    4e-15 for β 0.02-0.97; as β -> 1 it keeps every digit (against a 60-digit evaluation), where
    fluids' form loses them, and stays positive and strictly decreasing in β for 1 − β from 1e-3
    to 1e-12."""
    worst = 0.0
    for beta in np.linspace(0.02, 0.97, 200):
        for c in (0.3, 0.6, 0.62, 0.9, 1.0):
            d = float(beta) * D
            worst = max(worst, abs(k_of_c(D, d, c) / discharge_coefficient_to_K(D, d, c) - 1.0))
    assert worst <= 4.0e-15
    fluids_worst = 0.0
    for c in (0.6, 1.0):
        previous = math.inf
        for e in np.geomspace(1.0e-3, 1.0e-12, 300):
            d = D * (1.0 - float(e))
            k = k_of_c(D, d, c)
            assert 0.0 < k < previous
            previous = k
            exact = _k_exact(D, d, c)
            assert k == pytest.approx(exact, rel=1e-12)
            fluids_worst = max(fluids_worst, abs(discharge_coefficient_to_K(D, d, c) / exact - 1))
    assert fluids_worst > 1.0e-6  # what the cancellation-free form avoids


@pytest.mark.parametrize("taps", TAPS)
def test_c_falls_with_re_and_the_held_k_falls_with_beta(taps: str) -> None:
    """§3.1: over ISO's range C strictly decreases with Re, so h(Q) strictly increases; with the
    continuous Re_lo the held K strictly decreases in β, across β 0.56 too (decision 7)."""
    for d_pipe in (0.0525, D, 0.3, 1.0):
        for beta in (0.1, 0.3, 0.5, 0.6, 0.75):
            d = beta * d_pipe
            res = np.geomspace(re_lo(beta, d_pipe, taps), 1.0e8, 40)
            cs = [c_iso(d_pipe, d, RHO, MU, float(r), taps) for r in res]
            assert all(b < a for a, b in pairwise(cs)), (d_pipe, beta)
    held = []
    for beta in np.linspace(0.5585, 0.5615, 3001):
        d = float(beta) * D
        held.append(k_of_c(D, d, c_iso(D, d, RHO, MU, re_lo(float(beta), D, taps), taps)))
    assert all(b < a for a, b in pairwise(held))
    law = OrificeLaw(D, 0.6 * D, 900.0, 0.06, None, taps, g)
    flows = np.geomspace(1.0e-5, 0.5, 400)
    heads = [law.evaluate(float(q))[0] for q in flows]
    assert all(b > a for a, b in pairwise(heads))


def test_re_lo_is_isos_limit_made_continuous() -> None:
    """Decision 7: max(5000, 16000 β²) at corner and D and D/2 tappings and max(5000,
    170000 β² D) at flange tappings; ISO's written 16000 β² applies from β 0.56, and the max
    differs from it only for 0.559 < β < 0.56, by at most 17.6."""
    assert re_lo(0.5, D, "corner") == re_lo(0.5, D, "d_and_d_2") == 5000.0
    assert re_lo(0.56, D, "corner") == pytest.approx(16000.0 * 0.56**2, rel=1e-15)
    assert re_lo(0.5595, D, "d_and_d_2") == 16000.0 * 0.5595**2
    assert re_lo(0.5595, D, "d_and_d_2") > 5000.0
    written = [(b, 5000.0 if b < 0.56 else 16000.0 * b * b) for b in np.linspace(0.5, 0.6, 10001)]
    gaps = [re_lo(float(b), D, "corner") - iso for b, iso in written]
    assert min(gaps) == 0.0
    assert max(gaps) <= 17.6
    assert all(
        gap == 0.0 for (b, _), gap in zip(written, gaps, strict=True) if not 0.559 < b < 0.56
    )
    assert re_lo(0.75, 0.3, "flange") == pytest.approx(170000.0 * 0.75**2 * 0.3, rel=1e-15)
    assert re_lo(0.2, 0.3, "flange") == 5000.0


# --------------------------------------------------------------------------- the law


def test_the_hold_is_continuous_and_fluids_never_sees_a_low_re(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision 7: below Re_lo C is held at its value there, so K is continuous at Re_lo and the
    law is exactly c Q|Q| near zero flow; fluids is never called below Re_lo (of D and D/2
    tappings), at Q = 0, or below Re 3700, whatever the solve does."""
    calls: list[tuple[float, float, float, float]] = []
    original = orifice_module.flow_meter.C_Reader_Harris_Gallagher

    def spy(d_pipe: float, d: float, rho: float, mu: float, m: float, taps: str) -> float:
        calls.append((d_pipe, d, _fluids_re(d_pipe, rho, mu, m), m))
        return float(original(d_pipe, d, rho, mu, m, taps))

    monkeypatch.setattr(orifice_module.flow_meter, "C_Reader_Harris_Gallagher", spy)
    law = OrificeLaw(D, 0.5 * D, 900.0, 0.06, None, "flange", g)
    q_lo = law.re_lo / law.reynolds(1.0)
    below, above = law.state(q_lo * (1 - 1e-9)), law.state(q_lo * (1 + 1e-9))
    assert below.held
    assert not above.held
    assert above.loss_c == pytest.approx(below.loss_c, rel=1e-9)
    assert law.state(0.0).loss_c == below.loss_c == law.state(1e-6).loss_c
    c_low = law.low_k / (2.0 * g * _area(D) ** 2)
    for q in (1e-7, -1e-6, 1e-4):
        h, slope = law.evaluate(q)
        assert h == pytest.approx(c_low * q * abs(q), rel=1e-15)
        assert slope == pytest.approx(2.0 * c_low * abs(q), rel=1e-15)
    calls.clear()
    assert law.evaluate(0.0) == (0.0, 0.0)
    assert calls == []
    # Real solves: the proposal's low-Re line (C6, held), and a dead end at zero flow.
    oil = custom_fluid(900.0, 0.06)
    held = solve_project(line(plate(taps="flange"), z1=1.0, level1=2.0, fluid=oil))
    assert held.converged
    comps = [reservoir("R1", level=5.0), plate(taps="corner", elevation=0.0), plug("P1")]
    conns = [
        connection("L1", ("R1", "port_1"), ("O1", "inlet"), diameter=D),
        connection("L2", ("O1", "outlet"), ("P1", "port_1"), diameter=D),
    ]
    assert solve_project(make_project(comps, conns)).converged
    assert calls
    for d_pipe, d, re, m in calls:
        assert m > 0.0
        assert re >= re_lo(d / d_pipe, d_pipe, "d_and_d_2") * (1 - 1e-12) > 3700.0


def _central(f: Any, x: float, h: float) -> float:
    return float((f(x + h) - f(x - h)) / (2.0 * h))


def test_the_derivatives_match_central_differences() -> None:
    """Decision 8, §7.6: dC/dRe of eq. (4) (every tap set), dK/dC = −2K(1/C + β²/S), the move's
    dC_L/dRe and the law's slope against central differences."""
    for taps in TAPS:
        for d_pipe in (0.0525, D, 0.6):
            for beta in (0.2, 0.5, 0.74):
                d = beta * d_pipe
                for re in (6000.0, 3.0e4, 4.0e5, 5.0e7):
                    terms = rhg_terms(d_pipe, d, re, taps)
                    fd = _central(
                        lambda r, d_pipe=d_pipe, d=d, taps=taps: (
                            rhg_terms(d_pipe, d, r, taps).total
                        ),
                        re,
                        re * 1e-5,
                    )
                    assert terms.d_re == pytest.approx(fd, rel=1e-6, abs=1e-18)
    for beta in (0.1, 0.5, 0.9, 0.97):
        for c in (0.3, 0.6, 1.0):
            d = beta * D
            k = k_of_c(D, d, c)
            fd = _central(lambda x, d=d: k_of_c(D, d, x), c, 1e-6)
            assert dk_dc(D, d, c, k) == pytest.approx(fd, rel=1e-7)
    moved = OrificeLaw(D, 0.7 * D, RHO, MU, 0.6, "corner", g)
    for re in (2.0e4, 3.0e5):
        c, dc, _ = moved._loss(re)
        assert dc == pytest.approx(_central(lambda r: moved._loss(r)[0], re, re * 1e-5), rel=1e-6)
    for law in (
        OrificeLaw(D, 0.5 * D, RHO, MU, None, "flange", g),
        OrificeLaw(0.0525, 0.3 * 0.0525, 870.0, 0.012, None, None, g),
        moved,
        OrificeLaw(D, 0.5 * D, RHO, MU, 0.61, None, g),
    ):
        for q in (-0.02, 3.0e-4, 0.0174, 0.2):
            slope = law.evaluate(q)[1]
            fd = _central(lambda x, law=law: law.evaluate(x)[0], q, abs(q) * 1e-6)
            assert slope == pytest.approx(fd, rel=1e-6)


def test_the_move_of_an_entered_coefficient() -> None:
    """Decision 13: an entered C is held as entered without taps or at D and D/2 taps (r = 1);
    from corner or flange taps C_L = C_e r, r = C_ISO(D and D/2)/C_ISO(taps) at Re_eff; an
    entered C equal to ISO's C at the taps gives ISO's C_L, K and reading."""
    q = 0.02131227740861  # the proposal's C12 flow
    for taps in (None, "d_and_d_2"):
        law = OrificeLaw(D, 0.0767, RHO, MU, 0.6, taps, g)  # type: ignore[arg-type]
        state = law.state(q)
        assert (state.loss_c, state.ratio, state.coefficient_reynolds) == (0.6, None, None)
        assert state.meter_c == (0.6 if taps else None)
    for taps in ("corner", "flange"):
        law = OrificeLaw(D, 0.0767, RHO, MU, 0.6, taps, g)  # type: ignore[arg-type]
        state = law.state(q)
        re = law.reynolds(q)
        r = c_iso(D, 0.0767, RHO, MU, re, "d_and_d_2") / c_iso(D, 0.0767, RHO, MU, re, taps)
        assert state.ratio == r
        assert state.loss_c == 0.6 * r
        assert state.meter_c == 0.6
        iso = OrificeLaw(D, 0.0767, RHO, MU, None, taps, g).state(q)  # type: ignore[arg-type]
        assert iso.meter_c is not None
        calibrated = OrificeLaw(D, 0.0767, RHO, MU, iso.meter_c, taps, g).state(q)  # type: ignore[arg-type]
        assert calibrated.loss_c == pytest.approx(iso.loss_c, rel=4e-16)
        assert calibrated.k == pytest.approx(iso.k, rel=4e-15)
        assert calibrated.differential == pytest.approx(iso.differential, rel=4e-16)
    # The proposal's C12 at its flow: r 1.021059944023, C_L 0.6126359664, K 2.564521099.
    state = OrificeLaw(D, 0.0767, RHO, MU, 0.6, "corner", g).state(q)
    assert state.ratio == pytest.approx(1.021059944023, rel=1e-11)
    assert state.loss_c == pytest.approx(0.6126359664, rel=1e-9)
    assert state.k == pytest.approx(2.564521099, rel=1e-9)
    assert state.differential == pytest.approx(20172.34651, rel=1e-9)


# --------------------------------------------------------------------------- decision 17


def test_decision_17s_bounds_at_their_edges() -> None:
    """(a) β ≥ 1; (b) eq. (4) can exceed 1 (ISO's C reaches 1 at β 0.97025 for D ≥ 71.12 mm);
    (c) an entered C moved from corner taps with C_e r_max > 1 (0.978575 accepted at β 0.75 on
    102.3 mm, R8); (d) a tiny bore or C whose K/(2 g A²) is not a finite positive double."""
    assert refusal(D, D, None, None, g).rule == "beta"  # type: ignore[union-attr]
    assert refusal(D, D * 1.2, 0.6, "corner", g).rule == "beta"  # type: ignore[union-attr]
    for taps in (None, "corner", "flange", "d_and_d_2"):
        assert refusal(D, 0.9702 * D, None, taps, g) is None  # type: ignore[arg-type]
        found = refusal(D, 0.9703 * D, None, taps, g)  # type: ignore[arg-type]
        assert found is not None
        assert found.rule == "iso_coefficient"
        assert found.where == "D and D/2 tappings"
        assert found.coefficient is not None
        assert found.coefficient > 1.0
    # An entered C without a move uses no eq. (4): only K's representability bounds it.
    assert refusal(D, 0.99 * D, 0.6, None, g) is None
    assert refusal(D, 0.75 * D, 0.9785, "corner", g) is None
    moved = refusal(D, 0.75 * D, 0.9786, "corner", g)
    assert moved is not None
    assert moved.rule == "moved_coefficient"
    assert moved.ratio == pytest.approx(1.021894, rel=1e-6)
    assert refusal(D, 0.75 * D, 0.9900, "flange", g) is None
    assert refusal(D, 0.75 * D, 0.9901, "flange", g).rule == "moved_coefficient"  # type: ignore[union-attr]
    for bore, c in ((1.0e-100, None), (1.0e-100, 0.6)):
        found = refusal(D, bore, c, None, g)
        assert found is not None
        assert found.rule == "coefficient"
    assert refusal(D, 0.5 * D, 1.0e-150, None, g) is None
    assert refusal(D, 0.5 * D, 1.0e-160, None, g).rule == "coefficient"  # type: ignore[union-attr]
    # r_min <= r <= r_max on a Re grid, every plate (§7.6).
    for taps in ("corner", "flange"):
        for d_pipe in (0.02, 0.0525, D, 0.3, 1.0):
            for beta in (0.05, 0.3, 0.6, 0.75, 0.9, 0.97):
                d = beta * d_pipe
                low = re_lo(beta, d_pipe, "d_and_d_2")
                r_min, r_max = ratio_range(d_pipe, d, taps, low)
                for re in np.geomspace(low, 1.0e12, 60):
                    r = c_iso(d_pipe, d, RHO, MU, float(re), "d_and_d_2") / c_iso(
                        d_pipe, d, RHO, MU, float(re), taps
                    )
                    assert r_min * (1 - 1e-15) <= r <= r_max * (1 + 1e-15)


def _issues(project: Project) -> list[Any]:
    with pytest.raises(TopologyError) as caught:
        solve_project(project)
    return caught.value.issues


def test_a_plate_the_law_cannot_represent_is_a_topology_issue_listed_last() -> None:
    """Decision 17, §2.1: ORIFICE_OUT_OF_RANGE, one per plate naming the first rule it breaks,
    after the other issues (an unconnected plug, an equipment rating), quoting d, D, β and the C
    bound (D10)."""
    equipment = {
        "type": "equipment",
        "id": "E1",
        "name": "E1",
        "elevation": 3.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        "rating": {"kind": "Kv", "value": 1.0e-160},
    }
    comps = [
        reservoir("R1", level=12.0),
        plate("O1", 0.11),
        equipment,
        plate("O2", 0.0995),
        reservoir("R2", level=1.0),
        plug("P9"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("O1", "inlet"), diameter=D),
        connection("L2", ("O1", "outlet"), ("E1", "inlet"), diameter=D),
        connection("L3", ("E1", "outlet"), ("O2", "inlet"), diameter=D),
        connection("L4", ("O2", "outlet"), ("R2", "port_1"), diameter=D),
    ]
    issues = _issues(make_project(comps, conns))
    assert [(i.code, i.component_ids) for i in issues] == [
        ("UNCONNECTED_PORT", ["P9"]),
        ("EQUIPMENT_RATING_OUT_OF_RANGE", ["E1"]),
        ("ORIFICE_OUT_OF_RANGE", ["O1"]),
        ("ORIFICE_OUT_OF_RANGE", ["O2"]),
    ]
    beta = issues[2].message
    assert beta.startswith(
        "orifice 'O1': a bore diameter of 0.11 m in an inlet pipe of inner diameter 0.1023 m "
        "(β = d/D = 1.07527): the bore is not smaller than the pipe"
    )
    iso = issues[3].message
    assert iso.startswith(
        "orifice 'O2': a bore diameter of 0.0995 m in an inlet pipe of inner diameter 0.1023 m "
        "(β = d/D = 0.97263): ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher) at D "
        "and D/2 tappings can reach "
    )
    assert "above 1" in iso
    moved = _issues(line(plate(bore=0.75 * D, taps="corner", c=0.99)))
    assert [i.code for i in moved] == ["ORIFICE_OUT_OF_RANGE"]
    assert "its entered discharge coefficient 0.99 at its corner tappings" in moved[0].message
    tiny = _issues(line(plate(bore=1.0e-100)))
    assert "is not a finite positive floating-point number" in tiny[0].message


# --------------------------------------------------------------------------- the builder


def _built(project: Project) -> Any:
    return build_network(project, fluid_properties(project.fluid))


def test_the_builder_adds_one_orifice_link_on_the_inlet_pipes_bore() -> None:
    """§3.8, decisions 3 and 9: LinkKind.ORIFICE inlet -> outlet, D the inlet pipe's end segment
    (here a 102.3 mm pipe after a 154.1 mm one), an initial flow of 1 ft/s there."""
    pipes = [
        {"materialId": "custom", "length": 30.0, "innerDiameter": 0.1541, "roughness": 4.5e-5},
        {"materialId": "custom", "length": 30.0, "innerDiameter": D, "roughness": 4.5e-5},
    ]
    data = line_dict(plate(taps="flange", c=0.6))
    data["connections"][0]["piping"]["pipes"] = pipes
    built = _built(Project.model_validate(data))
    item = built.orifices["O1"]
    link = built.network.links[item.link_index]
    assert link.kind is LinkKind.ORIFICE
    assert (link.component_id, link.port_id) == ("O1", None)
    assert built.network.nodes[link.start].key == "O1:inlet" == item.inlet
    assert built.network.nodes[link.end].key == "O1:outlet" == item.outlet
    assert link.law is item.law
    law = item.law
    assert (law.pipe_diameter, law.bore_diameter, law.entered, law.taps) == (
        D,
        0.05115,
        0.6,
        "flange",
    )
    assert (law.density, law.viscosity) == (RHO, MU)
    assert link.initial_flow == pytest.approx(foot * _area(D), rel=1e-15)
    assert _built(line(gate("V1", 1.0))).orifices == {}


# --------------------------------------------------------------------------- solving


def test_the_proposals_c1_line_and_its_taps() -> None:
    """§7.1 C1 (flange taps): the solved flow, C_L, K, loss, reading, EGLs, port pressures and
    vena contracta; without taps, at corner or D and D/2 taps the flow is the same, only the
    reading changes (one loss per plate, decision 5)."""
    state = solve_project(line(plate(taps="flange")))
    assert state.converged
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(0.01742501098029, rel=1e-11)
    assert r.reynolds_number == pytest.approx(216440.28, rel=1e-8)
    assert r.discharge_coefficient == pytest.approx(0.6047534222, rel=1e-9)
    assert r.loss_coefficient == pytest.approx(30.05055523, rel=1e-9)
    assert r.head_loss == pytest.approx(6.885978346, rel=1e-9)
    assert r.pressure_loss == RHO * g * r.head_loss
    assert r.pressure_loss == pytest.approx(67393.32279, rel=1e-9)
    assert r.meter_discharge_coefficient == pytest.approx(0.6047651385, rel=1e-9)
    assert r.differential_pressure == pytest.approx(91977.61225, rel=1e-9)
    assert r.vena_contracta_pressure == pytest.approx(-30298.95924, rel=1e-9)
    assert (r.coefficient_source, r.taps, r.tap_coefficient_ratio) == ("iso_5167_2", "flange", None)
    assert r.coefficient_reynolds_number == r.reynolds_number
    assert (r.beta, r.pipe_diameter, r.bore_diameter) == (0.05115 / D, D, 0.05115)
    nodes = state.node_results
    assert nodes["O1:inlet"].egl == pytest.approx(9.531587007, rel=1e-9)
    assert nodes["O1:outlet"].egl == pytest.approx(2.645608662, rel=1e-9)
    assert nodes["O1:inlet"].pressure == pytest.approx(61682.21694, rel=1e-9)
    assert nodes["O1:outlet"].pressure == pytest.approx(-5711.105846, rel=1e-9)
    assert r.pressure_drop == pytest.approx(r.pressure_loss, rel=1e-12)
    assert _limits(state) == []
    readings = {}
    for taps in (None, "corner", "d_and_d_2"):
        other = solve_project(line(plate(taps=taps))).orifice_results["O1"]
        assert other.flow == pytest.approx(r.flow, rel=1e-13)
        assert other.loss_coefficient == pytest.approx(r.loss_coefficient, rel=1e-13)
        readings[taps] = other.differential_pressure
    assert readings[None] is None
    assert readings["corner"] == pytest.approx(91778.82, rel=1e-7)
    assert readings["d_and_d_2"] == pytest.approx(91981.18, rel=1e-7)


def test_an_entered_coefficient_solves_as_a_gate_valve_of_its_k() -> None:
    """§7.6: an entered C without taps is a constant K (C3 of §7.1); the same network with a
    gate valve of K = discharge_coefficient_to_K(D, d, C) gives the same flows and heads."""
    state = solve_project(line(plate(c=0.6)))
    k = discharge_coefficient_to_K(D, 0.05115, 0.6)
    valve = solve_project(line(gate("O1", k)))
    r, v = state.orifice_results["O1"], valve.valve_results["O1"]
    assert r.flow == pytest.approx(0.01732389858578, rel=1e-11)
    assert r.loss_coefficient == pytest.approx(30.60272137, rel=1e-9)
    assert r.pressure_loss == pytest.approx(67837.45736, rel=1e-9)
    assert (r.differential_pressure, r.meter_discharge_coefficient) == (None, None)
    assert (r.coefficient_source, r.coefficient_reynolds_number) == ("entered", None)
    assert r.flow == pytest.approx(v.flow, rel=1e-12)
    assert r.head_loss == pytest.approx(v.head_loss, rel=1e-12)
    for key, node in valve.node_results.items():
        assert state.node_results[key].egl == pytest.approx(node.egl, rel=1e-12)


def test_isos_coefficient_is_the_fixed_point_of_a_gate_valve() -> None:
    """A gate valve of K = K(C_L(Q*)) at the plate's solved flow Q* reproduces Q* (§7.1's check
    of the network around the law), on a Re-dependent low-Re line (C7)."""
    oil = custom_fluid(870.0, 0.012)
    element = plate(bore=0.65 * D, taps="flange")
    state = solve_project(line(element, z1=1.0, level1=3.0, lengths=(30.0, 20.0), fluid=oil))
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(0.01373313452249, rel=1e-10)
    assert r.discharge_coefficient == pytest.approx(0.6320436773, rel=1e-9)
    assert r.meter_discharge_coefficient == pytest.approx(0.6304237957, rel=1e-9)
    assert _limits(state) == []
    valve = line(
        gate("O1", r.loss_coefficient), z1=1.0, level1=3.0, lengths=(30.0, 20.0), fluid=oil
    )
    assert solve_project(valve).valve_results["O1"].flow == pytest.approx(r.flow, rel=1e-12)


def test_reverse_flow_the_reading_and_the_vena_contracta_on_the_inlet_side() -> None:
    """Decision 10, §7.1 C4: the symmetric law, the reading signed as the flow, the vena
    contracta on the inlet side, and a reverse-flow flag."""
    state = solve_project(line(plate(taps="flange"), z1=0.0, level1=1.0, z2=10.0, level2=2.0))
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(-0.01742501098029, rel=1e-11)
    assert r.differential_pressure == pytest.approx(-91977.61225, rel=1e-9)
    assert r.vena_contracta_pressure == pytest.approx(-22246.14305, rel=1e-9)
    assert state.node_results["O1:inlet"].egl == pytest.approx(3.468412993, rel=1e-9)
    [flag] = _flags(state, "CORRELATION_OUT_OF_RANGE")
    assert flag.details == {"limit": "reverseFlow", "flow": r.flow}
    assert flag.message == (
        "orifice 'O1': the flow runs from outlet to inlet; ISO 5167-2's coefficient is for flow "
        "onto the plate's upstream face, and the loss is taken as for forward flow at the same "
        "flow rate"
    )


@pytest.mark.parametrize("forward", [True, False])
def test_the_vena_contracta_is_at_the_elevation_of_the_port_the_flow_leaves_by(
    forward: bool,
) -> None:
    """Decision 15: p_vc = p_up + ρ g (z_up − z_down) − (1 − β⁴)/(C_L² β⁴) ρ v²/2, with ports at
    3 m and 5 m."""
    element = plate(taps="corner", inlet=3.0, outlet=5.0)
    kw: dict[str, Any] = (
        {"z1": 20.0, "level1": 2.0} if forward else {"z1": 0.0, "level1": 1.0, "z2": 20.0}
    )
    state = solve_project(line(element, **kw))
    r = state.orifice_results["O1"]
    assert (r.flow > 0.0) is forward
    up, down = ("inlet", "outlet") if forward else ("outlet", "inlet")
    z = {"inlet": 3.0, "outlet": 5.0}
    beta = 0.05115 / D
    v = r.flow / _area(D)
    drop = (1 - beta**4) / (r.discharge_coefficient**2 * beta**4) * RHO * v * v / 2.0
    expected = state.node_results[f"O1:{up}"].pressure + RHO * g * (z[up] - z[down]) - drop
    assert r.vena_contracta_pressure == pytest.approx(expected, rel=1e-12)


def test_flashing_at_the_vena_contracta_is_flagged() -> None:
    """§7.1 C10: both ports far above the vapor pressure, the vena contracta below it ->
    BELOW_VAPOR_PRESSURE (invalid) on the component, no port, with the absolute pressure."""
    water = custom_fluid(998.2071505, 1.0015961e-3, vapor_pressure=2339.3182)
    comps = [
        reservoir("R1", level=2.0, surface_pressure=1.8e6),
        plate(bore=0.25 * 0.0525, elevation=0.0),
        reservoir("R2", level=1.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("O1", "inlet"), length=5.0, diameter=0.0525),
        connection("L2", ("O1", "outlet"), ("R2", "port_1"), length=5.0, diameter=0.0525),
    ]
    state = solve_project(make_project(comps, conns, fluid=water))
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(0.005086337361782, rel=1e-9)
    assert r.pressure_loss == pytest.approx(1798635.117, rel=1e-9)
    [flag] = _flags(state, "BELOW_VAPOR_PRESSURE")
    assert (flag.severity, flag.port_id) == ("invalid", None)
    p_abs = flag.details["venaContractaAbsolutePressure"]
    assert p_abs == pytest.approx(-26861.40, rel=1e-6)
    assert p_abs == pytest.approx(r.vena_contracta_pressure + state.atmospheric_pressure, rel=1e-15)  # type: ignore[operator]
    assert flag.details["vaporPressure"] == 2339.3182
    for port in ("inlet", "outlet"):
        assert state.node_results[f"O1:{port}"].absolute_pressure > 1.0e5
    # The plate is inside ISO's bore limit? 13.1 mm > 12.5 mm, but D 52.5 mm and β 0.25: no
    # geometric flag either.
    assert _limits(state) == []


def test_the_static_drop_holds_the_velocity_terms_and_an_outlet_bore_is_flagged() -> None:
    """Decisions 12 and 16, §7.1 C11: a 154.1 mm outlet pipe; the static drop is the loss less
    the velocity heads, and the outlet bore is flagged quoting both bores."""
    state = solve_project(line(plate(taps="flange"), d_out=0.1541))
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(0.01869908683627, rel=1e-10)
    assert r.pressure_loss == pytest.approx(77639.78156, rel=1e-9)
    assert r.pressure_drop == pytest.approx(75558.76276, rel=1e-9)
    v_in, v_out = r.flow / _area(D), r.flow / _area(0.1541)
    identity = r.pressure_loss + 0.5 * RHO * (v_out**2 - v_in**2)
    assert r.pressure_drop == pytest.approx(identity, rel=1e-12)
    [flag] = _flags(state, "CORRELATION_OUT_OF_RANGE")
    assert flag.details == {"limit": "outletDiameter", "value": 0.1541, "inlet": D}
    assert flag.message.startswith(
        "orifice 'O1': its outlet pipe diameter 0.1541 m differs from its inlet pipe diameter "
        "0.1023 m"
    )


def test_zero_flow_between_equal_heads_and_at_a_dead_end() -> None:
    """Decision 9: h(0) = 0 with the valve path's Jacobian floor; C_L is held at Re_lo, no
    vena contracta pressure, and nothing is flagged."""
    still = solve_project(line(plate(taps="flange"), z1=0.0, level1=5.0, z2=0.0, level2=5.0))
    assert still.converged
    r = still.orifice_results["O1"]
    assert r.flow == 0.0
    assert abs(r.head_loss) < 1e-9
    assert (r.vena_contracta_pressure, r.reynolds_number) == (None, 0.0)
    assert r.differential_pressure == 0.0
    beta = 0.05115 / D
    assert r.coefficient_reynolds_number == re_lo(beta, D, "d_and_d_2")
    assert r.discharge_coefficient == c_iso(D, 0.05115, RHO, MU, 5000.0, "d_and_d_2")
    assert _limits(still) == []
    comps = [reservoir("R1", level=5.0), plate(c=0.6, elevation=0.0), plug("P1")]
    conns = [
        connection("L1", ("R1", "port_1"), ("O1", "inlet"), diameter=D),
        connection("L2", ("O1", "outlet"), ("P1", "port_1"), diameter=D),
    ]
    dead = solve_project(make_project(comps, conns))
    assert dead.converged
    assert dead.orifice_results["O1"].flow == 0.0
    assert dead.orifice_results["O1"].vena_contracta_pressure is None
    assert _limits(dead) == []


def test_a_closed_off_plate_has_no_result() -> None:
    comps = [
        reservoir("R1", level=12.0),
        gate("V1", 0.2, status="isolated"),
        plate(),
        gate("V2", 0.2, status="isolated"),
        reservoir("R2", level=1.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet"), diameter=D),
        connection("L2", ("V1", "outlet"), ("O1", "inlet"), diameter=D),
        connection("L3", ("O1", "outlet"), ("V2", "inlet"), diameter=D),
        connection("L4", ("V2", "outlet"), ("R2", "port_1"), diameter=D),
    ]
    state = solve_project(make_project(comps, conns))
    assert state.converged
    assert state.orifice_results == {}
    notes = state.trace.elements["O1"].notes
    assert any(
        n.startswith("No result values: this element lies in a section closed off") for n in notes
    )


def test_a_plate_in_a_floating_pump_loop_has_its_flow_but_no_vena_contracta_pressure() -> None:
    """§2.2: flow, head differences, the reading, K and C; no p_vc and no flashing check where
    the pressure level is undetermined."""
    pump = {
        "type": "pump",
        "id": "PU",
        "name": "PU",
        "elevation": 0.0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    comps = [
        reservoir("R1", level=10.0),
        gate("V", 0.2, elevation=0.0, status="isolated"),
        tee("T1"),
        pump,
        plate(taps="corner", elevation=0.0),
        tee("T2"),
        plug("P"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("T1", "run_inlet")),
        connection("L3", ("T1", "run_outlet"), ("PU", "suction"), length=50.0),
        connection("L4", ("PU", "discharge"), ("O1", "inlet"), length=25.0),
        connection("L7", ("O1", "outlet"), ("T2", "run_inlet"), length=25.0),
        connection("L5", ("T2", "run_outlet"), ("P", "port_1")),
        connection("L6", ("T2", "branch"), ("T1", "branch"), length=400.0),
    ]
    curve = {
        "id": "C1",
        "name": "test pump",
        "points": [{"flow": q, "head": h} for q, h in ((0.0, 30.0), (0.01, 25.0), (0.02, 20.0))],
    }
    state = solve_project(make_project(comps, conns, pump_library=[curve]))
    assert state.converged
    [flag] = _flags(state, "UNDETERMINED_PRESSURE", None)
    assert "O1" in str(flag.details["componentIds"])
    r = state.orifice_results["O1"]
    q = state.pump_results["PU"].operating_flow
    assert q > 0.0
    assert r.flow == pytest.approx(q, rel=1e-12)
    k = r.loss_coefficient
    assert r.head_loss == pytest.approx(k * (q / _area(0.1)) ** 2 / (2 * g), rel=1e-9)
    assert r.differential_pressure is not None
    assert r.vena_contracta_pressure is None
    assert _flags(state, "BELOW_VAPOR_PRESSURE") == []
    assert "O1:inlet" not in state.node_results


def test_a_system_curve_through_a_plate_holds_its_re_dependent_loss() -> None:
    """§7.1: pump -> plate -> reservoir gives H_sys(Q) = Δz + Σ h_pipes(Q) + h_or(Q), with C(Re)
    varying along the curve (the law evaluated with fluids' C at each point's flow)."""
    pump = {
        "type": "pump",
        "id": "P1",
        "name": "P1",
        "elevation": 0.0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    curve = {
        "id": "C1",
        "name": "test pump",
        "points": [{"flow": q, "head": h} for q, h in ((0.0, 60.0), (0.02, 50.0), (0.04, 30.0))],
    }
    comps = [reservoir("R1", level=2.0), pump, plate(bore=0.06, taps="corner", elevation=0.0)]
    comps.append(reservoir("R2", level=12.0))
    lengths = (5.0, 30.0, 20.0)
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=lengths[0]),
        connection("L2", ("P1", "discharge"), ("O1", "inlet"), length=lengths[1]),
        connection("L3", ("O1", "outlet"), ("R2", "port_1"), length=lengths[2]),
    ]
    project = make_project(comps, conns, pump_library=[curve])
    points = system_curve(project, "P1", flow_min=0.0, flow_max=0.03, num_points=5).points
    nu = MU / RHO
    for point in points:
        q = point.flow
        lines = sum(
            segment_state(PipeSegment(n, 0.1, 4.5e-5, _area(0.1), nu, g), q, "colebrook").head_loss
            for n in lengths
        )
        re = max(4 * RHO * q / (math.pi * 0.1 * MU), re_lo(0.6, 0.1, "d_and_d_2"))
        k = discharge_coefficient_to_K(0.1, 0.06, c_iso(0.1, 0.06, RHO, MU, re, "d_and_d_2"))
        h_or = k * (q / _area(0.1)) ** 2 / (2 * g)
        assert point.head == pytest.approx(10.0 + lines + h_or, rel=1e-11)


# --------------------------------------------------------------------------- flags


def test_isos_geometric_limits_are_flagged_where_eq_4_is_used() -> None:
    """Decision 11 (§7.1 C5): d < 12.5 mm and D < 50 mm, one flag per inequality, in SI; β
    outside 0.1-0.75 and D above 1 m; none with an entered C without a move."""
    comps = [reservoir("R1", level=30.0), plate(bore=0.01, taps="corner", elevation=0.0)]
    comps.append(reservoir("R2", level=0.0))
    conns = [
        connection("L1", ("R1", "port_1"), ("O1", "inlet"), length=20.0, diameter=0.0409),
        connection("L2", ("O1", "outlet"), ("R2", "port_1"), length=10.0, diameter=0.0409),
    ]
    state = solve_project(make_project(comps, conns))
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(0.00118312543162, rel=1e-9)
    assert r.discharge_coefficient == pytest.approx(0.6056492608, rel=1e-9)
    flags = {f.details["limit"]: f.details for f in _flags(state, "CORRELATION_OUT_OF_RANGE")}
    assert flags == {
        "boreDiameter": {"limit": "boreDiameter", "value": 0.01, "lower": 0.0125},
        "pipeDiameter": {"limit": "pipeDiameter", "value": 0.0409, "lower": 0.05},
    }
    entered = solve_project(
        make_project([comps[0], plate(bore=0.01, c=0.6, elevation=0.0), comps[2]], conns)
    )
    assert _limits(entered) == []
    edge = solve_project(line(plate(bore=0.0125)))  # β 0.122 on 102.3 mm: inside every limit
    assert _limits(edge) == []
    small = make_project(
        [reservoir("R1", level=2.0), plate(bore=0.02, elevation=0.0), reservoir("R2", level=1.0)],
        [
            connection("L1", ("R1", "port_1"), ("O1", "inlet"), length=10.0, diameter=0.05),
            connection("L2", ("O1", "outlet"), ("R2", "port_1"), length=10.0, diameter=0.05),
        ],
    )
    assert _limits(solve_project(small)) == []  # D = 50 mm, β 0.4: at ISO's smallest pipe
    for bore, side, bound in ((0.0102, "lower", 0.1), (0.0775, "upper", 0.75)):
        found = solve_project(line(plate(bore=bore)))
        [flag] = [
            f for f in _flags(found, "CORRELATION_OUT_OF_RANGE") if f.details["limit"] == "beta"
        ]
        assert flag.details == {"limit": "beta", "value": bore / D, side: bound}
    big = make_project(
        [reservoir("R1", level=2.0), plate(bore=0.6, elevation=0.0), reservoir("R2", level=1.0)],
        [
            connection("L1", ("R1", "port_1"), ("O1", "inlet"), length=50.0, diameter=1.2),
            connection("L2", ("O1", "outlet"), ("R2", "port_1"), length=50.0, diameter=1.2),
        ],
    )
    flags = [f.details for f in _flags(solve_project(big), "CORRELATION_OUT_OF_RANGE")]
    assert flags == [{"limit": "pipeDiameter", "value": 1.2, "upper": 1.0}]


def test_the_hold_below_re_lo_is_flagged_with_both_limits() -> None:
    """Decision 7, §3.5 (§7.1 C6): Re 1,018 on oil; C_L and the flange meter's C_M are held at
    their own Re_lo, and one flag gives Re and both limits."""
    oil = custom_fluid(900.0, 0.06)
    state = solve_project(line(plate(taps="flange"), z1=1.0, level1=2.0, fluid=oil))
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(0.005451562364008, rel=1e-10)
    assert r.discharge_coefficient == pytest.approx(0.6264073608, rel=1e-9)
    assert r.meter_discharge_coefficient == pytest.approx(0.6265920474, rel=1e-9)
    assert r.coefficient_reynolds_number == 5000.0
    [flag] = _flags(state, "CORRELATION_OUT_OF_RANGE")
    beta = 0.05115 / D
    assert flag.details == {
        "limit": "reynoldsNumber",
        "value": r.reynolds_number,
        "lower": 5000.0,
        "meterLower": max(5000.0, 170000.0 * beta**2 * D),
    }
    assert flag.message.startswith("orifice 'O1': Re = 1018 in its inlet pipe is below ISO")
    # Above Re_lo there is no flag (C1 on liquid A).
    assert _limits(solve_project(line(plate(taps="flange")))) == []


def test_laminar_flow_with_an_entered_coefficient_is_flagged() -> None:
    """Decision 13: an entered C is the turbulent square law; Re_D < 2000 in the inlet pipe is
    flagged (no Reynolds hold applies to it)."""
    oil = custom_fluid(900.0, 0.2)
    state = solve_project(line(plate(c=0.6), z1=1.0, level1=2.0, fluid=oil))
    r = state.orifice_results["O1"]
    assert 0.0 < r.reynolds_number < 2000.0
    [flag] = _flags(state, "CORRELATION_OUT_OF_RANGE")
    assert flag.details == {"limit": "laminar", "value": r.reynolds_number, "upper": 2000.0}


# --------------------------------------------------------------------------- traceability


def _inputs(state: SolvedState) -> dict[str, tuple[Any, str]]:
    return {i.name: (i.value, i.source) for i in state.trace.elements["O1"].inputs}


def _values(state: SolvedState) -> dict[str, float]:
    return {v.name: v.value for v in state.trace.elements["O1"].intermediates}


def test_the_trace_labels_isos_coefficient_and_no_taps_as_defaults() -> None:
    """§4.1: every input with its source, 'default' for ISO's C and for no taps; eq. (4)'s terms
    sum to C_L; K; the named departures and assumptions as notes."""
    state = solve_project(line(plate()))
    trace = state.trace.elements["O1"]
    assert trace.element_type == "orifice"
    inputs = _inputs(state)
    assert inputs["Bore diameter d (at the flowing temperature)"] == (0.05115, "user")
    assert inputs["Discharge coefficient C"] == (
        "ISO 5167-2 (Reader-Harris/Gallagher) at the solved flow",
        "default",
    )
    assert inputs["Pressure taps"] == ("none: a plate without taps, no reading", "default")
    key = "Pipe diameter D (inner diameter of the inlet pipe's end segment at the inlet port)"
    assert inputs[key] == (D, "user")  # a custom pipe
    assert inputs["Fluid density ρ"][1] == "user"
    assert "Vapor pressure p_vap" in inputs
    r = state.orifice_results["O1"]
    values = _values(state)
    assert values["eq. (4), the sum of its terms (D and D/2 tappings)"] == pytest.approx(
        r.discharge_coefficient, abs=2e-15
    )
    assert values["Loss coefficient K (on the inlet pipe's velocity)"] == r.loss_coefficient
    assert values["Head loss by the law K v|v|/(2g)"] == pytest.approx(r.head_loss, rel=1e-9)
    assert values["Diameter ratio β = d/D"] == r.beta
    assert "Differential pressure Δp at the taps (the reading)" not in values
    assert {c.name for c in trace.correlations} >= {
        "ISO 5167-2:2003 Reader-Harris/Gallagher equation "
        "(fluids.flow_meter.C_Reader_Harris_Gallagher)",
        "ISO 5167-2 pressure-loss relation (fluids.flow_meter.discharge_coefficient_to_K)",
    }
    assert any(n.startswith("One loss per plate: ") for n in trace.notes)
    assert any(n.startswith("Reader-Harris et al. 2019 take the downstream") for n in trace.notes)
    assert any("ε = 1" in n for n in trace.notes)
    alternative = values["C at L1 = 1, L2' = 0.125 (Reader-Harris et al. 2019; not used)"]
    assert alternative > r.discharge_coefficient  # a lower K (S1: 0.06-1.2 %)
    assert not any(n.startswith("Entered C") for n in trace.notes)


def test_the_trace_of_an_entered_coefficient_at_corner_taps() -> None:
    """§4.1: the entered C is user data with its definition; the move's ratio and the K the C as
    entered would give (not used); the reading at the taps."""
    state = solve_project(
        line(
            plate(bore=0.0767, taps="corner", c=0.6),
            z1=0.0,
            level1=1.0,
            z2=0.0,
            level2=0.0,
            lengths=(1.0, 1.0),
        )
    )
    inputs = _inputs(state)
    entered = next(k for k in inputs if k.startswith("Discharge coefficient C (entered"))
    assert inputs[entered] == (0.6, "user")
    assert "not the flow coefficient α = C/√(1 − β⁴)" in entered
    assert inputs["Pressure taps"] == ("corner tappings", "user")
    r = state.orifice_results["O1"]
    assert r.flow == pytest.approx(0.02131227740861, rel=1e-10)  # §7.1 C12
    assert r.tap_coefficient_ratio == pytest.approx(1.021059944023, rel=1e-10)
    assert r.discharge_coefficient == r.tap_coefficient_ratio * 0.6
    values = _values(state)
    assert values["Move ratio r = C_ISO(D and D/2)/C_ISO(taps)"] == r.tap_coefficient_ratio
    assert values["K with the entered C as entered (not moved; not used)"] == k_of_c(D, 0.0767, 0.6)
    assert values["Differential pressure Δp at the taps (the reading)"] == r.differential_pressure
    assert _limits(state) == []  # β 0.74976 on 102.3 mm: inside ISO's range, turbulent
    notes = state.trace.elements["O1"].notes
    assert any(
        n.startswith("Entered C: the reading uses it as entered; the loss uses it moved")
        for n in notes
    )


def test_the_methods_summary_has_an_orifices_section_only_with_a_plate() -> None:
    """§4.2: "Orifices" after "Equipment" and one assumption, only with a plate; the entered-C
    items only with an entered C; a summary without plates is the gate valve's, unchanged."""
    built = _built(line(plate()))
    summary = methods_summary(built, "test atmosphere")
    titles = [s.title for s in summary.sections]
    assert "Orifices" in titles
    section = summary.sections[titles.index("Orifices")]
    assert not any(item.startswith("An entered discharge coefficient") for item in section.items)
    assert ORIFICE_ASSUMPTION in summary.assumptions
    entered = methods_summary(_built(line(plate(c=0.6, taps="flange"))), "test atmosphere")
    section = next(s for s in entered.sections if s.title == "Orifices")
    assert any(item.startswith("An entered discharge coefficient") for item in section.items)
    valve = methods_summary(_built(line(gate("O1", 30.0))), "test atmosphere")
    assert "Orifices" not in [s.title for s in valve.sections]
    assert ORIFICE_ASSUMPTION not in valve.assumptions
    with_plate = [s for s in summary.sections if s.title != "Orifices"]
    assert [s.title for s in with_plate] == [s.title for s in valve.sections]
    assert [a for a in summary.assumptions if a != ORIFICE_ASSUMPTION] == valve.assumptions


def test_the_api_solves_a_plate_and_refuses_one_it_cannot_represent() -> None:
    """SDD §5: orificeResults in camelCase, always present; the issue is 422 TOPOLOGY_ERROR
    naming the plate."""
    client = _client()
    response = client.post("/api/v1/solve", json={"project": line_dict(plate(taps="flange"))})
    assert response.status_code == 200, response.text
    state = response.json()["solvedState"]
    assert state["methodVersion"] == "1.4.0"
    assert list(state["orificeResults"]["O1"]) == [
        "flow",
        "headLoss",
        "pressureLoss",
        "pressureDrop",
        "differentialPressure",
        "venaContractaPressure",
        "beta",
        "pipeDiameter",
        "boreDiameter",
        "reynoldsNumber",
        "dischargeCoefficient",
        "coefficientSource",
        "coefficientReynoldsNumber",
        "tapCoefficientRatio",
        "lossCoefficient",
        "taps",
        "meterDischargeCoefficient",
    ]
    bad = client.post("/api/v1/solve", json={"project": line_dict(plate(bore=0.2))})
    assert bad.status_code == 422
    body = bad.json()
    assert body["error"] == "TOPOLOGY_ERROR"
    assert [(i["code"], i["componentIds"]) for i in body["issues"]] == [
        ("ORIFICE_OUT_OF_RANGE", ["O1"])
    ]


# --------------------------------------------------------------------------- scenarios


def test_a_null_coefficient_reads_as_isos_default() -> None:
    """§5.1: value_text writes a null discharge coefficient as ISO 5167-2's, other nulls as
    before."""
    assert value_text("dischargeCoefficient", None, "") == "ISO 5167-2's (the default)"
    assert value_text("resistance", None, "") == "none (the default)"
    assert value_text("boreDiameter", 0.06, "m") == "0.06 m"


def test_a_scenario_bore_solves_as_the_hand_edited_project() -> None:
    """D15: a bore change and a C set back to ISO's give the hand-edited project's solve; the
    note and methods text name ISO's default."""
    base = line_dict(plate(taps="flange", c=0.6))
    base["scenarios"] = [
        {
            "id": "S1",
            "name": "S1",
            "overrides": [
                {"kind": "component", "componentId": "O1", "field": "boreDiameter", "value": 0.06},
                {
                    "kind": "component",
                    "componentId": "O1",
                    "field": "dischargeCoefficient",
                    "value": None,
                },
            ],
        }
    ]
    solved, _ = solve_case(Project.model_validate(base), None, "S1")
    hand = solve_project(line(plate(bore=0.06, taps="flange")))
    assert solved.orifice_results["O1"].flow == pytest.approx(
        hand.orifice_results["O1"].flow, rel=1e-14
    )
    section = solved.trace.methods.sections[0]
    assert section.title == "Scenario"
    assert any(
        "discharge coefficient ISO 5167-2's (the default) (base: 0.6)" in i for i in section.items
    )


# --------------------------------------------------------------------------- goal seek


def _request(project: dict[str, Any], variables: list[Any], goals: list[Any]) -> GoalSeekRequest:
    return GoalSeekRequest.model_validate(
        {"project": project, "variables": variables, "goals": goals}
    )


def _bore(lower: float, upper: float) -> dict[str, Any]:
    return {
        "kind": "component",
        "componentId": "O1",
        "field": "boreDiameter",
        "lower": lower,
        "upper": upper,
    }


def _goal(quantity: str, target: float) -> dict[str, Any]:
    return {"quantity": quantity, "elementId": "O1", "target": target}


def test_goal_values_read_the_plates_result() -> None:
    """§5.2: the four goals read flow, pressureLoss, differentialPressure and pressureDrop; a
    plate without taps has no reading."""
    state = solve_project(line(plate(taps="flange"), d_out=0.1541))
    r = state.orifice_results["O1"]
    for quantity, value in (
        ("orifice_flow", r.flow),
        ("orifice_pressure_loss", r.pressure_loss),
        ("orifice_differential_pressure", r.differential_pressure),
        ("orifice_pressure_drop", r.pressure_drop),
    ):
        goal = GoalSeekRequest.model_validate(
            {
                "project": line_dict(plate()),
                "variables": [_bore(0.02, 0.06)],
                "goals": [_goal(quantity, 1.0)],
            }
        ).goals[0]
        assert gs.goal_value(state, goal, "orifice O1") == (value, "")
    bare = solve_project(line(plate()))
    goal = _request(
        line_dict(plate()), [_bore(0.02, 0.06)], [_goal("orifice_differential_pressure", 1.0)]
    ).goals[0]
    assert gs.goal_value(bare, goal, "orifice O1") == (
        None,
        "orifice O1 has no pressure taps, so no differential pressure",
    )


def test_a_reading_goal_needs_taps() -> None:
    """§5.2 (needs: ['taps']): 400 GOAL_NOT_APPLICABLE on a plate without taps, located by
    index, the plate in componentIds."""
    request = _request(
        line_dict(plate()), [_bore(0.02, 0.06)], [_goal("orifice_differential_pressure", 5.0e4)]
    )
    with pytest.raises(gs.GoalSeekInputError) as caught:
        gs.prepare(request)
    [issue] = caught.value.issues
    assert issue.code == "GOAL_NOT_APPLICABLE"
    assert issue.message == (
        "body.goals.0: the orifice has no pressure taps; set its taps to read a differential "
        "pressure"
    )
    assert issue.component_ids == ["O1"]


@pytest.mark.parametrize(
    ("element", "variable", "text"),
    [
        (
            plate(),
            _bore(0.02, 0.2),
            "body.variables.0.upper: the orifice's bore is not smaller than its inlet pipe's "
            "inner diameter",
        ),
        (
            plate(),
            _bore(0.02, 0.0995),
            "body.variables.0.upper: ISO 5167-2's discharge coefficient at this bore could "
            "exceed 1",
        ),
        (
            plate(bore=0.75 * D, taps="corner", c=0.6),
            {
                "kind": "component",
                "componentId": "O1",
                "field": "dischargeCoefficient",
                "lower": 0.5,
                "upper": 0.99,
            },
            "body.variables.0.upper: the orifice's discharge coefficient, moved from its taps "
            "to D and D/2 tappings, could exceed 1 at this discharge coefficient",
        ),
        (
            plate(),
            _bore(1.0e-100, 0.05),
            "body.variables.0.lower: the orifice's loss coefficient is not a finite positive "
            "floating-point number at this bore",
        ),
    ],
)
def test_a_bound_the_solve_would_refuse_is_a_400_without_values(
    element: dict[str, Any], variable: dict[str, Any], text: str
) -> None:
    """Decision 21: the network is built at each bound of an orifice's bore or C; decision 17's
    issue there is an input problem located by index, with no id or value in its text."""
    request = _request(line_dict(element), [variable], [_goal("orifice_flow", 0.015)])
    with pytest.raises(gs.GoalSeekInputError) as caught:
        gs.prepare(request)
    [issue] = caught.value.issues
    assert (issue.code, issue.message, issue.component_ids) == (
        "ORIFICE_OUT_OF_RANGE",
        text,
        ["O1"],
    )
    for value in (variable["lower"], variable["upper"]):
        assert f"{value:g}" not in issue.message
    assert "O1" not in issue.message


def test_a_bore_is_sized_for_a_flow() -> None:
    """§5.2 (G33's shape, on C1): the bore for 15 L/s is met, within the default tolerance, and
    its override solves to the reported state."""
    request = _request(
        line_dict(plate(taps="flange")), [_bore(0.02, 0.09)], [_goal("orifice_flow", 0.015)]
    )
    outcome = gs.goal_seek_case(request)
    assert outcome.result.met
    [goal] = outcome.result.goals
    assert goal.value is not None
    assert abs(goal.value - 0.015) <= goal.tolerance
    [variable] = outcome.result.variables
    assert variable.value is not None
    assert variable.value == pytest.approx(0.0467639723052, rel=2e-3)  # G33: d* 46.7640 mm
    assert outcome.state is not None
    assert outcome.state.orifice_results["O1"].bore_diameter == variable.value


def test_projects_without_plates_build_without_orifice_paths() -> None:
    """§3.9: a project without a plate builds no orifice data, adds no orifice flag, issue or
    methods text, and assigned flows elsewhere are untouched."""
    comps = [reservoir("R1", level=5.0), gate("V1", 1.0), assigned_flow("A1", 0.002)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet"), diameter=D),
        connection("L2", ("V1", "outlet"), ("A1", "port_1"), diameter=D),
    ]
    project = make_project(comps, conns)
    built = _built(project)
    assert built.orifices == {}
    state = solve_project(project)
    assert state.orifice_results == {}
    assert "Orifices" not in [s.title for s in state.trace.methods.sections]


def test_no_design_check_applies_to_a_plate() -> None:
    """D19's checks are a pump's NPSH margin and operating region and a pipe's velocity: none
    is a plate's, and the velocity check still covers the pipes on both sides of it."""
    data = line_dict(plate(taps="flange"))
    data["settings"]["designChecks"] = {
        "pipeVelocity": {"maximum": 1.0, "source": {"kind": "user"}}
    }
    state = solve_project(Project.model_validate(data))
    checks = state.design_checks
    assert [(c.check, c.connection_id, c.component_id) for c in checks] == [
        ("pipe_velocity", "L1", None),
        ("pipe_velocity", "L2", None),
    ]
    assert {c.outcome for c in checks} == {"fail"}  # 2.12 m/s in both pipes


def test_the_api_answers_a_refused_bound_with_400_without_values() -> None:
    """Decision 21 through the API: 400 VALIDATION_ERROR, the issue located by index, the plate
    in componentIds, neither its id nor the bound in the text (D10)."""
    body = {
        "project": line_dict(plate()),
        "variables": [_bore(0.02, 0.2)],
        "goals": [_goal("orifice_flow", 0.015)],
    }
    response = _client().post("/api/v1/goal-seek", json=body)
    assert response.status_code == 400, response.text
    data = response.json()
    assert data["error"] == "VALIDATION_ERROR"
    assert [(i["code"], i["componentIds"], i["message"]) for i in data["issues"]] == [
        (
            "ORIFICE_OUT_OF_RANGE",
            ["O1"],
            "body.variables.0.upper: the orifice's bore is not smaller than its inlet pipe's "
            "inner diameter",
        )
    ]
