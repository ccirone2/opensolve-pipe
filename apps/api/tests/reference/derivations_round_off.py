"""Closed-form reference cases for the round-off floor of the energy stop test (change set C0b,
METHOD_VERSION 1.2.0: proposal vfd-slice2-discharge-pressure.md §2.11.10, fix (b), approved as
the owner's answer Q9 (a) of 2026-10-24).

The stop test, from the specs (not from solver code). An inner solve converges only when every
link's energy residual r = H_from − H_to − h(Q) is small enough (TSD §5.2). Up to 1.1.0 the
bound is absolute, |r| ≤ ENERGY_TOL = 10⁻⁷ m; from 1.2.0 it allows the round-off of the heads
the residual subtracts, |r| ≤ ENERGY_TOL + 4ε·max(|H_from|, |H_to|, |h(Q)|), ε = 2⁻⁵² (§2.11.10
fix (b)). The two bounds differ by 4ε·max: under 10⁻¹³ m at the ordinary heads of
``round_off_ordinary_heads`` (below 100 m), and about 36 times ENERGY_TOL at the 4·10⁹ m of
``round_off_large_heads``, where 1.1.0's bound is below one unit in the last place (ulp) of
the heads.

Network (both cases): a supply AF1 (Q_a = −q) → L1 → ideal tee T1, which drains through L2
(drawn T1 → R1) to R1 and through L3 (drawn R2 → T1, so it carries −q3) to R2. Continuity:
L1 carries q, q2 + q3 = q. The tee has one EGL E at its three ports (ideal) and the two
drains close on it:

    E = H_R1 + h_L2(q2) = H_R2 + h_L3(q − q2),   H_AF1 = E + h_L1(q),

one unknown, q2 (brentq on the closure, then the float64 q2 around its root with the smallest
closure, ``TwoDrains.split``). Pipe law as in ``line`` (Darcy–Weisbach, Colebrook via fluids'
Lambert-W solution); custom fluid A; static pressures p = ρg(H − z − v²/2g) with v in the
connected pipe (boundaries v = 0). The expected state closes every link to 4ε·max(|H_from|,
|H_to|, |h|) (guarded): it passes 1.2.0's energy test even without its ENERGY_TOL.

Why 1.1.0's absolute bound cannot be met at the large heads (IEEE 754 binary64: a 53-bit
significand, so every float64 in the binade [2ᵏ, 2ᵏ⁺¹) is a multiple of its ulp u = 2ᵏ⁻⁵²;
Sterbenz's lemma, the difference of two floats within a factor 2 of each other is exact:
Sterbenz 1974, *Floating-Point Computation*; Goldberg 1991, "What every computer scientist
should know about floating-point arithmetic", ACM Computing Surveys 23(1), Theorem 11). The
case puts H_AF1, E, h_L2 and |h_L3| in one binade, so every float64 head near the solution at
AF1 and T1 is a multiple of u (uZ below), and whatever order the three terms of r are summed
in, one link's computed residual is bounded below by a number fixed by the inputs:

- the two heads first (H_from − H_to exact): L1's residual is k·u − h_L1 for an integer k, at
  least dist(h_L1(q), uZ) less what L1's flow may differ from q within the continuity stop
  test (TSD §5.2: 10⁻⁹·max|Q| + 10⁻¹⁴ m³/s, through dh/dQ ≤ 2h/Q, since Colebrook's f falls
  as Re rises) and less the 10⁻¹² relative by which the solver's Colebrook solution may
  differ from this file's (``test_colebrook_lambert_w_agrees_with_clamond``);
- the loss with the from-head first (H_from − h exact): L2's residual is k·u − H_R1, at least
  dist(H_R1, uZ);
- the loss with the to-head first (h + H_to exact, h_L3 < 0): L3's residual is H_R2 − k·u, at
  least dist(H_R2, uZ).

The inputs make all three bounds exceed ENERGY_TOL (``require_unattainable``), so no float64
state passes 1.1.0's test and its inner solve can only end at its iteration limit, not
converged. 1.2.0's bound on every link is at least ENERGY_TOL + 4u (ε·x ≥ u for x in the
binade), eight times the half-ulp by which the nearest float64 heads miss the exact solution.

The model bounds a boundary's head (elevation ≤ 10⁴ m, level ≤ 10³ m, gauge pressure ≤ 10⁸
Pa: about 2·10⁴ m for a water-like fluid) and a pump's (curve heads ≤ 10⁴ m), so the large
heads come from flow alone: a fixed supply pushed through long, narrow lines. Every pipe,
elevation and flow is a test input. Independence: written without reading
``opensolve_pipe.services``; nothing here imports it.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from scipy.optimize import brentq

from tests.reference import derivations as dv
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    assigned_flow,
    custom_fluid,
    ideal_tee,
    make_project,
    reservoir,
)
from tests.reference.derivations_assigned_flow import require_no_vapor_flag
from tests.reference.line import Line, require_turbulent

MODULE = "derivations_round_off"

ENERGY_TOL = 1.0e-7
"""m: 1.1.0's energy stop test, |r| ≤ 10⁻⁷ m on every link (TSD §5.2)."""
CONTINUITY_RTOL = 1.0e-9
CONTINUITY_ATOL = 1.0e-14
"""Continuity stop test, 10⁻⁹ × max|Q| + 10⁻¹⁴ m³/s at every node (TSD §5.2)."""
EPS = 2.0**-52
"""Machine epsilon of IEEE 754 binary64 (``sys.float_info.epsilon``)."""
ROUND_OFF_ULPS = 4.0
"""The 4ε of 1.2.0's energy stop test (proposal §2.11.10 fix (b), owner's answer Q9 (a))."""
COLEBROOK_AGREEMENT = 1.0e-12
"""Relative: Colebrook by Lambert W (here) against Clamond (the solver), the tolerance of
``test_colebrook_lambert_w_agrees_with_clamond``."""
CLOSURE_SEARCH = 64
"""Floats on each side of brentq's q2 searched for the smallest closure residual: brentq stops
within rtol = 4ε of the root, a few ulps of q2 (``TwoDrains.split``)."""

METHOD = (
    "assigned supply into an ideal tee drained to two reservoirs: one EGL at the tee, "
    "Darcy-Weisbach + Colebrook lines, brentq on the split, then the float64 split with the "
    "smallest closure"
)


def _source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def grid_distance(x: float, u: float) -> float:
    """dist(x, uZ): how far x lies from the nearest multiple of u (u a power of 2, so x/u and
    n·u are exact and the difference is exact by Sterbenz's lemma)."""
    n = round(x / u)
    return abs(x - n * u)


def binade_ulp(values: Sequence[float]) -> float:
    """The ulp u = 2ᵏ⁻⁵² of the one binade [2ᵏ, 2ᵏ⁺¹) holding every |value| (``math.frexp``);
    an error if they straddle a power of 2."""
    exponents = {math.frexp(abs(v))[1] for v in values}
    if len(exponents) != 1:
        raise ValueError(f"the heads span several binades (frexp exponents {exponents})")
    return math.ldexp(1.0, exponents.pop() - 53)


@dataclass(frozen=True)
class TwoDrains:
    """AF1 (supply q) → L1 → T1; T1 → L2 → R1; R2 → L3 → T1:branch."""

    q: float
    l1: Line
    l2: Line
    l3: Line
    z1: float
    level1: float
    z2: float
    level2: float
    z_tee: float
    z_af: float

    @property
    def h_r1(self) -> float:
        return self.z1 + self.level1

    @property
    def h_r2(self) -> float:
        return self.z2 + self.level2

    def closure(self, q2: float, nu: float) -> float:
        """(H_R1 + h_L2(q2)) − (H_R2 + h_L3(q − q2)): zero at the split."""
        return (self.h_r1 + self.l2.head_loss(q2, nu)) - (
            self.h_r2 + self.l3.head_loss(self.q - q2, nu)
        )

    def split(self, nu: float) -> float:
        """q2: brentq's root of the closure, then, of the 2·CLOSURE_SEARCH + 1 floats around it
        (``math.nextafter``), the one with the smallest |closure| (at 10⁹ m of head one ulp of
        q2 moves the closure by about 2 ulps of E, more than brentq's rtol resolves)."""
        if not (self.closure(0.0, nu) < 0.0 < self.closure(self.q, nu)):
            raise ValueError("both reservoirs must drain the supply")
        root = float(
            brentq(
                lambda q2: self.closure(q2, nu),
                0.0,
                self.q,
                xtol=1.0e-18,
                rtol=4.0 * EPS,
                maxiter=500,
            )
        )
        candidates = [root]
        below = above = root
        for _ in range(CLOSURE_SEARCH):
            below, above = math.nextafter(below, 0.0), math.nextafter(above, self.q)
            candidates += [below, above]
        return min(candidates, key=lambda q2: (abs(self.closure(q2, nu)), q2))


def _round_off_case(
    *, name: str, title: str, description: str, method: str, net: TwoDrains, large: bool
) -> ReferenceCase:
    """Expected flows, EGLs and pressures of a TwoDrains network. ``large``: the heads must make
    1.1.0's absolute energy test unattainable (the three distances of the module docstring
    exceed ENERGY_TOL); otherwise they must be ordinary, with 4ε·max(head, loss) ≤ 10⁻⁶ of
    ENERGY_TOL."""
    name_a, rho, mu = dv.FLUID_A
    nu = mu / rho
    q, q2 = net.q, net.split(nu)
    q3 = q - q2
    require_turbulent(nu, [(q, net.l1), (q2, net.l2), (q3, net.l3)])
    h1, h2, h3 = net.l1.head_loss(q, nu), net.l2.head_loss(q2, nu), net.l3.head_loss(q3, nu)
    e = net.h_r1 + h2
    h_af = e + h1
    # (H_from, H_to, h) of L1, L2 and L3 (drawn R2 → T1, so its loss at −q3 is −h3).
    links = {"L1": (h_af, e, h1), "L2": (e, net.h_r1, h2), "L3": (net.h_r2, e, -h3)}
    for cid, (h_from, h_to, loss) in links.items():
        allowance = ROUND_OFF_ULPS * EPS * max(abs(h_from), abs(h_to), abs(loss))
        if abs(h_from - h_to - loss) > allowance:
            raise RuntimeError(f"{cid}: the expected state does not close to 4ε·max")
    scale = max(abs(h_af), abs(e), abs(h2), abs(h3))
    if large:
        require_unattainable(net, h_af, e, h1, h2, h3)
    elif not ROUND_OFF_ULPS * EPS * scale <= 1.0e-6 * ENERGY_TOL:
        raise ValueError("the ordinary case's heads must keep 4ε·max at most 1e-6 of ENERGY_TOL")
    egl = {
        "AF1:port_1": h_af,
        "T1:run_inlet": e,
        "T1:run_outlet": e,
        "T1:branch": e,
        "R1:port_1": net.h_r1,
        "R2:port_1": net.h_r2,
    }
    pressures = {
        "AF1:port_1": dv.static_pressure(rho, h_af, net.z_af, net.l1.velocity(q)),
        "T1:run_inlet": dv.static_pressure(rho, e, net.z_tee, net.l1.velocity(q)),
        "T1:run_outlet": dv.static_pressure(rho, e, net.z_tee, net.l2.velocity(q2)),
        "T1:branch": dv.static_pressure(rho, e, net.z_tee, net.l3.velocity(q3)),
        "R1:port_1": dv.static_pressure(rho, net.h_r1, net.z1, 0.0),
        "R2:port_1": dv.static_pressure(rho, net.h_r2, net.z2, 0.0),
    }
    require_no_vapor_flag(pressures, rho, None)
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        custom_fluid(name_a, rho, mu),
        [
            assigned_flow("AF1", net.z_af, -q),
            ideal_tee("T1", net.z_tee),
            reservoir("R1", net.z1, net.level1),
            reservoir("R2", net.z2, net.level2),
        ],
        [
            net.l1.connect("L1", "AF1:port_1", "T1:run_inlet"),
            net.l2.connect("L2", "T1:run_outlet", "R1:port_1"),
            net.l3.connect("L3", "R2:port_1", "T1:branch"),
        ],
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=Expected(
            density=rho,
            dynamic_viscosity=mu,
            flows={"L1": q, "L2": q2, "L3": -q3},
            egl=egl,
            pressures=pressures,
        ),
    )


def require_off_grid(label: str, distance: float, slack: float = 0.0) -> None:
    """Guard: a residual bounded below by ``distance`` − ``slack`` still exceeds ENERGY_TOL."""
    if not distance - slack > ENERGY_TOL:
        raise ValueError(
            f"{label}: {distance:.3e} m from the grid (slack {slack:.1e} m) does not exceed "
            f"ENERGY_TOL"
        )


def require_unattainable(
    net: TwoDrains, h_af: float, e: float, h1: float, h2: float, h3: float
) -> None:
    """Guards of the module docstring's argument: H_AF1, E, h_L2 and h_L3 in one binade of ulp
    u; L1's loss, H_R1 and H_R2 each more than ENERGY_TOL from uZ, L1's by more than the
    continuity stop test (dh/dQ ≤ 2h/Q) and the agreement of two Colebrook solutions can move
    it."""
    u = binade_ulp([h_af, e, h2, h3])
    if not u / 2.0 > ENERGY_TOL:
        raise ValueError("the heads' half-ulp must exceed ENERGY_TOL")
    continuity = 2.0 * h1 / net.q * (CONTINUITY_RTOL * net.q + CONTINUITY_ATOL)
    slack = continuity + COLEBROOK_AGREEMENT * h1
    require_off_grid("h_L1(q)", grid_distance(h1, u), slack)
    require_off_grid("H_R1", grid_distance(net.h_r1, u))
    require_off_grid("H_R2", grid_distance(net.h_r2, u))


def round_off_large_heads() -> ReferenceCase:
    """A 36 L/s supply AF1 (z 0) → L1 (100 mm, 15 m) → ideal tee T1 (z 0), drained by two
    narrow lines (L2, 10 mm and 1,000 km, to R1 at H 12.3 m; L3, 12 mm and 800 km, from R2 at
    H 8.7 m): E ≈ 4.0·10⁹ m.

    Every head at AF1 and T1, and both drains' losses, lie in [2³¹, 2³²) m, u = 2⁻²¹ m ≈
    4.77·10⁻⁷ m. The guards' distances: h_L1(q) ≈ 2.80 m lies 0.45 u ≈ 2.16·10⁻⁷ m from uZ
    (the continuity stop test and the Colebrook agreement move it by at most 5.6·10⁻⁹ m),
    H_R1 = 12.3 m and H_R2 = 8.7 m each 0.4 u ≈ 1.91·10⁻⁷ m: every float64 state leaves a link
    residual above 10⁻⁷ m, so 1.1.0's test is never met, while 1.2.0's admits 10⁻⁷ m +
    4ε·4.0·10⁹ m ≈ 3.6·10⁻⁶ m (7.7 u) per link. The lines are absurd as hardware (163 and
    205 m/s) but valid inputs."""
    net = TwoDrains(
        q=0.036,
        l1=Line(0.1, 15.0),
        l2=Line(0.01, 1.0e6),
        l3=Line(0.012, 8.0e5),
        z1=10.0,
        level1=2.3,
        z2=5.0,
        level2=3.7,
        z_tee=0.0,
        z_af=0.0,
    )
    return _round_off_case(
        name="round_off_large_heads",
        title="Supply drained through narrow lines at 4e9 m of head",
        description=(
            "A supply on an ideal tee drained to two reservoirs through narrow lines 800 and "
            "1,000 km long, so that the tee and the supply sit near 4e9 m of head, where float64 "
            "heads are 4.8e-7 m apart: verifies that the energy stop test allows the round-off "
            "of the heads it subtracts (a 1e-7 m absolute bound cannot be met by any float64 "
            "state) and that the split, heads and pressures are still the closed form's."
        ),
        method=METHOD + "; float64 grid distances guarded (Sterbenz)",
        net=net,
        large=True,
    )


def round_off_ordinary_heads() -> ReferenceCase:
    """The same network at ordinary heads: AF1 (36 L/s, z 0) → L1 (100 mm, 15 m) → ideal tee
    T1 (z 0), drained by L2 (102.3 mm, 400 m) to R1 (H 12.3 m) and by L3 (77.9 mm, 150 m) from
    R2 (H 8.7 m).

    Every head is below 100 m, so 4ε·max(head, loss) < 10⁻¹³ m: the bounds of 1.1.0 and 1.2.0
    differ by less than 10⁻⁶ of ENERGY_TOL (guarded), and the stop test's verdict can differ
    only on a residual within that of ENERGY_TOL."""
    net = TwoDrains(
        q=0.036,
        l1=Line(0.1, 15.0),
        l2=Line(0.1023, 400.0),
        l3=Line(0.0779, 150.0),
        z1=10.0,
        level1=2.3,
        z2=5.0,
        level2=3.7,
        z_tee=0.0,
        z_af=0.0,
    )
    return _round_off_case(
        name="round_off_ordinary_heads",
        title="Supply drained to two reservoirs at ordinary heads",
        description=(
            "The large-head network's twin with ordinary drains (heads below 100 m): verifies "
            "the split between the two reservoirs, the shared tee EGL and the supply's EGL "
            "where the round-off allowance of the energy stop test is below 1e-13 m, so the "
            "stop test is the absolute 1e-7 m bound it was."
        ),
        method=METHOD,
        net=net,
        large=False,
    )


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    round_off_large_heads,
    round_off_ordinary_heads,
)
