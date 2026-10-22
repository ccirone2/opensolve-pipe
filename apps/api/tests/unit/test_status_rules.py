"""Status rules (design §5.1-5.3), one test per transition of each EPANET 2.2 rule.

The rules are EPANET 2.2's ``src/hydstatus.c`` (tag v2.2, quoted in the research notes §C.3,
§C.4) written for EGL heads: cvstatus lines 177-202, pumpstatus 205-239 (with linkstatus
re-opening XHEAD pumps, 131-136), prvstatus 242-299, psvstatus 302-359, fcvstatus 362-398.
Every head is a test input, set a clear margin (D = 10 htol) from each threshold. The
speed-controlled pump's rules (CLAUDE.md D11, ``flow_pump_status``) are tested at the
tolerance edges themselves: a value on an edge stays, the next double past it changes.
"""

import math

import pytest

from opensolve_pipe.services.solver.status import (
    HTOL,
    QTOL,
    Status,
    check_valve_status,
    fcv_status,
    flow_pump_status,
    prv_status,
    psv_status,
    pump_status,
)

OPEN, CLOSED, ACTIVE = Status.OPEN, Status.CLOSED, Status.ACTIVE
D = 10 * HTOL  # margin past a head threshold
Q = 1.0e-3  # a clearly positive flow, m³/s
QR = -10 * QTOL  # a clearly reverse flow
NAN = math.nan


# --- check valve: cvstatus (hydstatus.c:177-202) with dh above the cracking head h_c ---------
@pytest.mark.parametrize("h_c", [0.0, 0.5])
@pytest.mark.parametrize(
    ("status", "excess", "q", "expected"),
    [
        # |dh − h_c| > Htol (lines 191-196)
        (OPEN, -D, 0.0, CLOSED),  # reverse head (line 193)
        (OPEN, D, QR, CLOSED),  # forward head but reverse flow (line 194)
        (OPEN, D, Q, OPEN),  # line 195
        (CLOSED, D, 0.0, OPEN),  # head above cracking opens it (line 195)
        (CLOSED, -D, 0.0, CLOSED),
        # |dh − h_c| <= Htol (lines 197-201): unchanged unless the flow reverses
        (OPEN, 0.5 * HTOL, QR, CLOSED),  # line 199
        (OPEN, 0.5 * HTOL, 0.0, OPEN),  # line 200
        (CLOSED, -0.5 * HTOL, 0.0, CLOSED),  # line 200
        (CLOSED, 0.5 * HTOL, 0.0, CLOSED),
    ],
)
def test_check_valve_status(
    h_c: float, status: Status, excess: float, q: float, expected: Status
) -> None:
    assert check_valve_status(status, h_c + excess, q, h_c) is expected


def test_check_valve_without_heads_keeps_its_status() -> None:
    """An isolated check valve (no heads) is not switched by NaN comparisons."""
    assert check_valve_status(OPEN, NAN, 0.0, 0.0) is OPEN
    assert check_valve_status(CLOSED, NAN, 0.0, 0.0) is CLOSED


# --- pump: pumpstatus (hydstatus.c:234-235) and linkstatus re-opening (131-136) ------------
SHUTOFF = 30.0


@pytest.mark.parametrize(
    ("status", "gain", "q", "expected"),
    [
        (OPEN, SHUTOFF + D, Q, CLOSED),  # gain > s²Hmax + Htol: XHEAD (line 235)
        (OPEN, SHUTOFF + 0.5 * HTOL, Q, OPEN),  # within Htol: stays open (line 238)
        (OPEN, SHUTOFF - D, QR, CLOSED),  # reverse flow (design §5.1)
        (OPEN, SHUTOFF - D, Q, OPEN),
        (CLOSED, SHUTOFF, 0.0, OPEN),  # re-opened when gain <= shutoff (design §5.1)
        (CLOSED, SHUTOFF - D, 0.0, OPEN),
        (CLOSED, SHUTOFF + 0.5 * HTOL, 0.0, CLOSED),
        (CLOSED, SHUTOFF + D, 0.0, CLOSED),
    ],
)
def test_pump_status(status: Status, gain: float, q: float, expected: Status) -> None:
    assert pump_status(status, gain, q, SHUTOFF) is expected


# --- PRV: prvstatus (hydstatus.c:242-299) ---------------------------------------------------
HSET = 20.0
HML = 0.3  # fully open loss at the current flow


@pytest.mark.parametrize(
    ("status", "h1", "h2", "q", "expected"),
    [
        (ACTIVE, HSET + 5, HSET, QR, CLOSED),  # line 274
        (ACTIVE, HSET + HML - D, HSET, Q, OPEN),  # H1 − hml < Hset − Htol (line 275)
        (ACTIVE, HSET + HML + D, HSET, Q, ACTIVE),  # line 276
        (OPEN, HSET + 5, HSET - 1, QR, CLOSED),  # line 280
        (OPEN, HSET + 5, HSET + D, Q, ACTIVE),  # H2 >= Hset + Htol (line 281)
        (OPEN, HSET - 1, HSET - 1.3, Q, OPEN),  # line 282
        (CLOSED, HSET + D, HSET - D, 0.0, ACTIVE),  # line 286
        (CLOSED, HSET - D, HSET - 1, 0.0, OPEN),  # H1 < Hset − Htol, H1 > H2 + Htol (287)
        (CLOSED, HSET + D, HSET + 1, 0.0, CLOSED),  # downstream head above the setting (288)
        (CLOSED, HSET - 1, HSET - 1 + 0.5 * HTOL, 0.0, CLOSED),  # no forward head (288)
    ],
)
def test_prv_status(status: Status, h1: float, h2: float, q: float, expected: Status) -> None:
    assert prv_status(status, h1, h2, HSET, HML, q) is expected


# --- PSV: psvstatus (hydstatus.c:302-359) ---------------------------------------------------
@pytest.mark.parametrize(
    ("status", "h1", "h2", "q", "expected"),
    [
        (ACTIVE, HSET, HSET - 5, QR, CLOSED),  # line 334
        (ACTIVE, HSET, HSET - HML + D, Q, OPEN),  # H2 + hml > Hset + Htol (line 335)
        (ACTIVE, HSET, HSET - HML - D, Q, ACTIVE),  # line 336
        (OPEN, HSET + 5, HSET + 4, QR, CLOSED),  # line 340
        (OPEN, HSET - D, HSET - 1, Q, ACTIVE),  # H1 < Hset − Htol (line 341)
        (OPEN, HSET + 1, HSET + 0.5, Q, OPEN),  # line 342
        (CLOSED, HSET + 2, HSET + 1, 0.0, OPEN),  # H2 > Hset + Htol, H1 > H2 + Htol (346)
        (CLOSED, HSET + D, HSET - 1, 0.0, ACTIVE),  # H1 >= Hset + Htol, H1 > H2 + Htol (347)
        (CLOSED, HSET - D, HSET - 1, 0.0, CLOSED),  # upstream head below the setting (348)
        (CLOSED, HSET + 2, HSET + 2 + D, 0.0, CLOSED),  # reverse head (348)
    ],
)
def test_psv_status(status: Status, h1: float, h2: float, q: float, expected: Status) -> None:
    assert psv_status(status, h1, h2, HSET, HML, q) is expected


# --- FCV: fcvstatus (hydstatus.c:362-398), XFCV as OPEN, closed on reverse flow (§12) -------
QSET = 0.01


@pytest.mark.parametrize(
    ("status", "h1", "h2", "q", "expected"),
    [
        (ACTIVE, 10.0, 10.0 + D, QSET, OPEN),  # H1 − H2 < −Htol: XFCV (lines 385-388)
        (ACTIVE, 10.0 + D, 10.0, QSET, ACTIVE),  # unchanged (line 397)
        (OPEN, 10.0, 10.0, QSET, ACTIVE),  # XFCV and Q >= setting: ACTIVE (lines 393-396)
        (OPEN, 10.0, 9.0, 2 * QSET, ACTIVE),
        (OPEN, 10.0, 9.0, 0.5 * QSET, OPEN),  # still below the setting (line 397)
        (OPEN, 10.0, 10.0 + D, QR, CLOSED),  # reverse flow: closed (design §12)
        (CLOSED, 10.0 + D, 10.0, 0.0, OPEN),  # forward head across the closed valve
        (CLOSED, 10.0, 10.0 + D, 0.0, CLOSED),
        (CLOSED, NAN, 10.0, 0.0, CLOSED),  # a starved valve with no upstream head stays shut
    ],
)
def test_fcv_status(status: Status, h1: float, h2: float, q: float, expected: Status) -> None:
    assert fcv_status(status, h1, h2, q, QSET) is expected


FCV_HML = 3.0  # m, fully open loss at the setpoint (test input)


@pytest.mark.parametrize(
    ("h1", "expected"),
    [
        (10.0 + FCV_HML - D, OPEN),  # forward head below the open loss: cannot pass Q_set
        (10.0 + FCV_HML + D, ACTIVE),  # enough head to throttle
        (10.0 + FCV_HML - 0.5 * HTOL, ACTIVE),  # within Htol: unchanged
    ],
)
def test_active_fcv_opens_when_the_head_is_below_its_open_loss(h1: float, expected: Status) -> None:
    """Departure from fcvstatus (status module docstring): an active FCV opens once H1 − H2 <
    hml − Htol, hml its fully open loss at Q_set, as prvstatus and psvstatus test H1 − hml and
    H2 + hml. With hml = 0 (an ideal valve) this is EPANET's H1 − H2 < −Htol."""
    assert fcv_status(ACTIVE, h1, 10.0, QSET, QSET, FCV_HML) is expected


@pytest.mark.parametrize("rule", [prv_status, psv_status])
def test_closed_pressure_valves_without_heads_stay_closed(rule: object) -> None:
    """A starved (closed) PRV/PSV whose side has no head is not re-opened by NaN tests."""
    assert callable(rule)
    assert rule(CLOSED, NAN, 10.0, HSET, 0.0, 0.0) is CLOSED
    assert rule(CLOSED, 30.0, NAN, HSET, 0.0, 0.0) is CLOSED


# --- speed-controlled pump, flow setpoint (CLAUDE.md D11): rules A1-C1 ----------------------
MIN = Status.MIN_SPEED
F_MIN, F_MAX = 5.0, 40.0  # F(s_lo, Q_set) (A2's bound; F(s_min, Q_set) when s_lo = s_min),
# F(s_max, Q_set), m (test inputs)
S_MIN, S_MAX = 8.0, 45.0  # shutoff heads at s_min and s_max, m
QS = 0.02  # setpoint, m³/s
UP, DOWN = math.inf, -math.inf


def flow_rule(status: Status, gain: float, q: float) -> Status:
    return flow_pump_status(status, gain, q, QS, F_MIN, F_MAX, S_MIN, S_MAX)


@pytest.mark.parametrize(
    ("status", "gain", "q", "expected"),
    [
        # ACTIVE: A1 (gain > F_max + Htol), A2 (gain < F_lo − Htol), else A3
        (ACTIVE, F_MAX + HTOL, QS, ACTIVE),  # on the edge: stays
        (ACTIVE, math.nextafter(F_MAX + HTOL, UP), QS, OPEN),  # A1
        (ACTIVE, F_MIN - HTOL, QS, ACTIVE),  # on the edge: stays
        (ACTIVE, math.nextafter(F_MIN - HTOL, DOWN), QS, MIN),  # A2
        (ACTIVE, 0.5 * (F_MIN + F_MAX), QS, ACTIVE),  # A3
        # OPEN (maximum speed): X1 once Q >= Q_set, else pumpstatus at s_max (X2)
        (OPEN, F_MAX, QS, ACTIVE),  # X1 on the edge
        (OPEN, F_MAX, math.nextafter(QS, DOWN), OPEN),  # X2: stays at maximum speed
        (OPEN, S_MAX + HTOL, 0.5 * QS, OPEN),  # X2: within the shutoff head + Htol
        (OPEN, math.nextafter(S_MAX + HTOL, UP), 0.5 * QS, CLOSED),  # X2: above it
        (OPEN, F_MAX, -QTOL, OPEN),  # reverse flow on the edge
        (OPEN, F_MAX, math.nextafter(-QTOL, DOWN), CLOSED),  # reverse flow: closed (X2)
        # MIN_SPEED: N1 once Q <= Q_set, else pumpstatus at s_min (N2)
        (MIN, F_MIN, QS, ACTIVE),  # N1 on the edge
        (MIN, F_MIN, math.nextafter(QS, UP), MIN),  # N2: stays at minimum speed
        (MIN, S_MIN + HTOL, 2 * QS, MIN),  # N2: within its shutoff head + Htol
        (MIN, math.nextafter(S_MIN + HTOL, UP), 2 * QS, CLOSED),  # N2: above it (rising curve)
        # CLOSED: C1, pumpstatus at s_max
        (CLOSED, S_MAX, 0.0, OPEN),  # re-opens at maximum speed once gain <= S_max
        (CLOSED, math.nextafter(S_MAX, UP), 0.0, CLOSED),
    ],
)
def test_flow_pump_status(status: Status, gain: float, q: float, expected: Status) -> None:
    assert flow_rule(status, gain, q) is expected


def test_flow_pump_band_points_are_kept_by_both_neighbours() -> None:
    """Inside the Htol band at a limit, a point holds in either state (EPANET's band): an active
    pump whose head is within Htol above F(s_max, Q_set) stays active, and the same pump at
    maximum speed, a hair below its setpoint, stays at maximum speed. Likewise at s_min."""
    above = F_MAX + 0.5 * HTOL
    assert flow_rule(ACTIVE, above, QS) is ACTIVE
    assert flow_rule(OPEN, above, QS * (1.0 - 1.0e-12)) is OPEN
    below = F_MIN - 0.5 * HTOL
    assert flow_rule(ACTIVE, below, QS) is ACTIVE
    assert flow_rule(MIN, below, QS * (1.0 + 1.0e-12)) is MIN


def test_flow_pump_rules_test_a1_before_a2() -> None:
    """Given a lower bound above F(s_max, Q_set), a head can satisfy A1 and A2 together: the
    first test that holds wins. (A built pump's bound F(s_lo, Q_set) is at most F(s_max,
    Q_set), F rising on [s_lo, s_max]; the rule does not rely on it.)"""
    rule = flow_pump_status(ACTIVE, 10.0, QS, QS, 20.0, 0.0, S_MIN, S_MAX)
    assert rule is OPEN


def test_flow_pump_rules_without_heads_keep_the_state() -> None:
    """A pump whose heads are not known (NaN) is not switched by the head tests."""
    assert flow_rule(ACTIVE, NAN, QS) is ACTIVE
    assert flow_rule(CLOSED, NAN, 0.0) is CLOSED
