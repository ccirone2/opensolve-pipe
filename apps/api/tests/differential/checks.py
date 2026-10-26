"""Comparison (D6) and independent checks for the EPANET differential test.

Independent of the solver: link laws from ``tests/reference/network_check.py`` (EPANET's
5.74/Re^0.9 Swamee-Jain, which our 'swamee_jain' mode evaluates exactly, TSD §5.2), pump curve
and valve K from ``tests/reference/element_laws.py``, and the status rules re-written here from
status.py's documented rules (EPANET 2.2 hydstatus.c in EGL form, plus the documented FCV
departures). Only the solver's *results* are read (``ours_solution``, ``our_states``).

Flow-controlled pumps (CLAUDE.md D11): their state is the reported control state (active,
max_speed, min_speed, no_flow, off); the rules (``rule_flow_pump``) are written from the state
machine of proposal vfd-pump-modes.md §4.5 alone, the laws from §4.4 (active: Q = Q_set; at a
speed limit the fixed-speed pump at that speed), and the reported speed, setpoint flag and
control fields from §2.4-2.5 and §4.7 (``control_problems``); the speed is compared with the one
EPANET's head implies (closed form for a linear curve, ``implied_speed``).

Assigned-flow nodes (SDD §4.11, TSD §4.8): continuity at the node's port takes its flow as a
demand (``network_check.net_inflow``, so ``law_problems`` checks it, ours and EPANET's); the
networks that have no steady state because of them follow from the project alone
(``assigned_flow_expectations``): assigned flows that no pattern of flows can carry through the
elements' one-way rules and FCV setpoints (a minimum cut, ``_short_side``), or that force flow
controls to their setpoints with nothing fixing the pressure behind them; and the node's
reported results are checked against their definitions (``assigned_flow_problems``). Every head
we report must be determined (``undetermined_heads``, for every network: nodes with demands are
where a head could be reported that nothing fixes).

Pumps and valves without a result (state 'isolated' in ``our_states``), which the checks above
skip, are held to the rule for when one has none (SDD §4.10, TSD §5.4;
``missing_result_problems``), so a result dropped where its values are determined is caught;
``missing_result_check`` measures that by deleting each result of the fuzz networks in turn.
``self_check`` runs every check of a converged result of ours.
"""

import itertools
import math
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from opensolve_pipe.models.components import (
    AssignedFlow,
    CheckValve,
    Component,
    ControlValve,
    IdealReferenceNode,
    IsolationValve,
    Plug,
    Pump,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from opensolve_pipe.models.results import SolvedState
from tests.differential.epanet_model import EpanetResult, Layout
from tests.reference import element_laws as el
from tests.reference import network_check as nc
from tests.reference.derivations import G, area

RELATIVE = 0.005
HEAD_FLOOR = 0.01
FLOW_FLOOR = 1.0e-9
HTOL = 1.0e-4
QTOL = 1.0e-8
STRICT_FLOW_FLOOR = 1.0e-7
"""Strict flow comparison (``compare(strict=True)``): 0.5 % or 1e-7 m³/s (plus EPANET's
closed-link leak), without the D6 head-equivalent floor (0.01 m / dh/dQ), which accepts almost
any flow in a short, large pipe."""

OUR_MODEL = nc.Model(friction=nc.epanet_friction_factor, g=G)
"""Our 'swamee_jain' mode: EPANET's f formula (5.74/Re^0.9), our g, exact minor-loss constant."""
EP_MODEL = nc.EPANET_MODEL

Flows = Mapping[str, float]
Heads = Mapping[str, float]
States = Mapping[str, str]
Record = tuple[str, str, float, float, float]  # (category, kind, |Δ|, tolerance, reference)
Mismatch = tuple[str, str, float, float, float]  # (category, id, ours, EPANET, tolerance)
Edge = tuple[str, str, float, str]  # (u, v, w, label): H_v - H_u <= w


def keys(c: PipeConnection) -> tuple[str, str]:
    return f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"


def conn_slope(conn: PipeConnection, q: float, nu: float, model: nc.Model = OUR_MODEL) -> float:
    """dh/dQ of a connection at q (central difference; laminar slope near 0)."""
    dq = max(abs(q) * 1e-6, 1e-12)
    h_plus = nc.connection_head_loss(conn, q + dq, nu, model)
    h_minus = nc.connection_head_loss(conn, q - dq, nu, model)
    return (h_plus - h_minus) / (2 * dq)


def element_kind(c: Component) -> str:
    if isinstance(c, Pump):
        return "pump" if c.control is None else "flow_pump"
    if isinstance(c, IsolationValve):
        return "isolation"
    if isinstance(c, CheckValve):
        return "check"
    if isinstance(c, ControlValve):
        return c.valve_type
    if isinstance(c, Reservoir | IdealReferenceNode):
        return "boundary"
    if isinstance(c, TeeBranch | WyeBranch):
        return "junction"
    if isinstance(c, Plug):
        return "plug"
    if isinstance(c, AssignedFlow):
        return "assigned_flow"
    return type(c).__name__


def our_states(project: Project, result: SolvedState) -> dict[str, str]:
    """State per pump and valve: a pump's status, a flow-controlled pump's control state;
    'isolated' without a result."""
    out = {}
    for c in project.components:
        if isinstance(c, Pump):
            pr = result.pump_results.get(c.id)
            if pr is None:
                out[c.id] = "isolated"
            elif c.control is not None and pr.control is not None:
                out[c.id] = pr.control.state
            else:
                out[c.id] = pr.status
        elif isinstance(c, IsolationValve | CheckValve | ControlValve):
            vr = result.valve_results.get(c.id)
            out[c.id] = vr.state if vr else "isolated"
    return out


def ours_solution(
    project: Project, result: SolvedState
) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    """(flows per connection, EGL per port key, state per pump and valve) of our result."""
    flows = {cid: link.flow for cid, link in result.link_results.items()}
    egl = {key: node.egl for key, node in result.node_results.items()}
    return flows, egl, our_states(project, result)


def closed_without_result(project: Project, result: SolvedState) -> set[str]:
    """Flow-controlled pumps with no result that are held at no flow: both sides closed off,
    their flags kept (state no_flow), as a fixed-speed pump's (TSD §5.4)."""
    return {
        f.component_id
        for f in result.flags
        if f.code == "PUMP_SETPOINT_NOT_MET"
        and f.details.get("state") == "no_flow"
        and f.component_id is not None
        and f.component_id not in result.pump_results
        and any(c.id == f.component_id for c in project.components)
    }


def our_speeds(project: Project, result: SolvedState) -> dict[str, float]:
    """The reported speed of every flow-controlled pump with a result."""
    return {
        c.id: result.pump_results[c.id].speed
        for c in project.components
        if isinstance(c, Pump) and c.control is not None and c.id in result.pump_results
    }


def regime(re: float) -> str:
    return "laminar" if re < 2000 else ("transitional" if re < 4000 else "turbulent")


# --------------------------------------------------------------------------- comparison


CBIG = 1.0e8  # EPANET hydcoeffs.c:35: a closed link keeps conductance 1/CBIG (ft, cfs)


def epanet_leak(ep: EpanetResult) -> float:
    """Upper bound of the flow EPANET's closed links leak: Σ |ΔH|·(0.3048 m)²/CBIG over every
    closed EPANET link (m³/s), from EPANET's heads at the link's end nodes."""
    total = 0.0
    for name, (n1, n2) in ep.link_nodes.items():
        if ep.raw_status.get(name) in ("CLOSED", "XHEAD", "TEMPCLOSED"):
            total += abs(ep.node_head[n1] - ep.node_head[n2]) * 0.3048**2 / CBIG
    return total


def compare(
    project: Project,
    flows_o: Flows,
    egl_o: Heads,
    states_o: States,
    ep: EpanetResult,
    lay: Layout,
    *,
    strict: bool = False,
    speeds_o: Mapping[str, float] | None = None,
) -> tuple[list[Mismatch], list[Record]]:
    """D6 comparison of our solution with EPANET's. Returns (mismatches, records).
    records: (category, kind, |Δ|, tolerance, reference) for statistics. Flows are also
    allowed EPANET's closed-link leak (``epanet_leak``, twice the bound), and a head loss the
    head that leak flow makes in that connection. ``strict``: the strict flow floor
    (``STRICT_FLOW_FLOOR``) instead of the D6 head-equivalent floor. ``speeds_o``: our speeds
    of the flow-controlled pumps (``our_speeds``), compared by ``speed_comparison``."""
    nu = nc.kinematic_viscosity(project)
    leak = 2.0 * epanet_leak(ep)
    mism: list[Mismatch] = []
    rec: list[Record] = []
    port_kind = {}
    for c in project.components:
        for p in c.ports:
            port_kind[f"{c.id}:{p.id}"] = element_kind(c)
    for conn in project.connections:
        qe, qo = ep.flows[conn.id], flows_o[conn.id]
        s = conn_slope(conn, qe, nu)
        if strict:
            floor = max(STRICT_FLOW_FLOOR, leak)
        else:
            floor = max(FLOW_FLOOR, HEAD_FLOOR / s if s > 0 else FLOW_FLOOR, leak)
        tol = max(RELATIVE * abs(qe), floor)
        leak_head = (
            abs(
                nc.connection_head_loss(conn, abs(qe) + leak, nu, OUR_MODEL)
                - nc.connection_head_loss(conn, abs(qe), nu, OUR_MODEL)
            )
            if leak
            else 0.0
        )
        d0 = conn.piping.pipes[0].inner_diameter
        re = abs(qe) / area(d0) * d0 / nu
        a, b = keys(conn)
        kinds = {port_kind[a], port_kind[b]} - {"junction", "boundary", "plug"}
        cat = "pipe:" + regime(re)
        rec.append(("flow", cat, abs(qo - qe), tol, qe))
        for k in sorted(kinds):  # a fixed order, whatever PYTHONHASHSEED
            rec.append(("flow", k, abs(qo - qe), tol, qe))
        if abs(qo - qe) > tol:
            mism.append(("flow", conn.id, qo, qe, tol))
        if a in egl_o and b in egl_o and a in ep.heads and b in ep.heads:
            dho, dhe = egl_o[a] - egl_o[b], ep.heads[a] - ep.heads[b]
            tolh = max(RELATIVE * abs(dhe), HEAD_FLOOR, 2.0 * leak_head)
            rec.append(("headloss", cat, abs(dho - dhe), tolh, dhe))
            if abs(dho - dhe) > tolh:
                mism.append(("headloss", conn.id, dho, dhe, tolh))
    for key, he in ep.heads.items():
        if key not in egl_o:
            continue
        tol = max(RELATIVE * abs(he), HEAD_FLOOR)
        rec.append(("egl", port_kind[key], abs(egl_o[key] - he), tol, he))
        if abs(egl_o[key] - he) > tol:
            mism.append(("egl", key, egl_o[key], he, tol))
    if speeds_o:
        m2, r2 = speed_comparison(project, speeds_o, states_o, ep, lay)
        mism += m2
        rec += r2
    return mism, rec


def collinear_curve(curve: PumpCurve) -> tuple[float, float]:
    """(a, b) of a curve whose points lie on H₀ = a − b·x from x = 0 (the generator's)."""
    pts = curve.points
    if pts[0].flow != 0.0:
        raise ValueError(f"curve {curve.id} does not start at Q = 0")
    a = pts[0].head
    b = (a - pts[-1].head) / pts[-1].flow
    if any(abs(a - b * p.flow - p.head) > 1e-9 * max(1.0, a) for p in pts):
        raise ValueError(f"curve {curve.id} is not collinear")
    return a, b


def implied_speed(curve: PumpCurve, q: float, h: float, s_min: float, s_max: float) -> float:
    """The speed at which the pump passes q against EGL rise h, s²H₀(q/s) = h, for a linear
    curve H₀ = a − b·x: s = [bq + √(b²q² + 4ah)]/(2a) (ORNL eq. 10 with c = 0,
    https://www.osti.gov/servlets/purl/1649114; the root on the rising branch, where
    d/ds[s²H₀(q/s)] = 2as − bq > 0), clamped to [s_min, s_max]; at the vertex when h is below
    every head of the branch."""
    a, b = collinear_curve(curve)
    disc = max(b * b * q * q + 4.0 * a * h, 0.0)
    return min(max((b * q + disc**0.5) / (2.0 * a), s_min), s_max)


def speed_comparison(
    project: Project,
    speeds_o: Mapping[str, float],
    states_o: States,
    ep: EpanetResult,
    lay: Layout,
) -> tuple[list[Mismatch], list[Record]]:
    """Each flow-controlled pump that is active in our result and in EPANET's run (the FAQ
    substitute): our speed against the one EPANET's head rise H_e implies (``implied_speed``),
    within 0.5 % (owner's answer Q6, proposal vfd-pump-modes.md §10), and the head our speed
    implies at Q_set, s²H₀(Q_set/s), against H_e by the D6 head criterion, 0.5 % or 0.01 m,
    whichever is looser, as every head loss here. Q6's 0.01 m alone is the reference suite's
    test against a derived head. Here H_e carries EPANET's constants (``nc.EPANET_MODEL``):
    at the flows the setpoint fixes, its friction losses are 8.1e-4 lower (g = 32.2 ft/s²,
    hydcoeffs.c:98) and its minor losses 9.2e-4 lower (0.02517, input1.c:618) than ours, so
    H_e differs from ours by 8.1e-4 to 9.2e-4 of those losses, whatever H is, plus the effect
    of the Δh/CBIG the substitute's closed pump leaks past Q_set. A flat 0.01 m fails once those
    losses pass 11-12 m (TSD §10.4 gives the run's figures). Criticality does not rest on this
    comparison: ``control_problems`` holds our speed to Htol against our own head rise."""
    curves = {cv.id: cv for cv in project.pump_library}
    mism: list[Mismatch] = []
    rec: list[Record] = []
    for c in project.components:
        if not (isinstance(c, Pump) and c.control is not None and c.id in speeds_o):
            continue
        if states_o.get(c.id) != "active" or lay.control_run.get(c.id) != "active":
            continue
        a, b = f"{c.id}:suction", f"{c.id}:discharge"
        if a not in ep.heads or b not in ep.heads:
            continue
        curve = curves[c.curve_id]
        h_e = ep.heads[b] - ep.heads[a]
        q_set = c.control.setpoint
        s_ref = implied_speed(curve, q_set, h_e, c.control.min_speed, c.speed)
        s_o = speeds_o[c.id]
        tol = RELATIVE * s_ref
        rec.append(("speed", "flow_pump", abs(s_o - s_ref), tol, s_ref))
        if abs(s_o - s_ref) > tol:
            mism.append(("speed", c.id, s_o, s_ref, tol))
        h_o = el.pump_head(curve, s_o, q_set)
        tolh = max(RELATIVE * abs(h_e), HEAD_FLOOR)
        rec.append(("speed_head", "flow_pump", abs(h_o - h_e), tolh, h_e))
        if abs(h_o - h_e) > tolh:
            mism.append(("speed_head", c.id, h_o, h_e, tolh))
    return mism, rec


# --------------------------------------------------------------------------- status rules


def rule_pump(status: str, gain: float, q: float, shutoff: float) -> str:
    if status == "running":
        return "no_flow" if (gain > shutoff + HTOL or q < -QTOL) else "running"
    return "running" if gain <= shutoff else "no_flow"


def rule_flow_pump(
    state: str, gain: float, q: float, pump: Pump, curve: PumpCurve, q_slack: float = 0.0
) -> str:
    """The next state of a flow-controlled pump that is on, from the state machine of proposal
    vfd-pump-modes.md §4.5 (the first rule that holds wins), with gain = EGL_d − EGL_s, F(s, Q) =
    s²H₀(Q/s), F_lo/F_max = F(s_lo/s_max, Q_set), s_lo = max(s_min, Q_set/x_mono) at most s_max
    (§4.3, ``element_laws.stable_min_speed``: F(·, Q_set) rises on [s_lo, s_max], and F_lo =
    F(s_min, Q_set) when s_lo = s_min), S_min/S_max = F(s_min/s_max, 0):

    - active: A1 max_speed if gain > F_max + Htol; A2 min_speed if gain < F_lo − Htol; else
      active (A0, a side with no fixed head, cannot be seen in a result with both heads);
    - max_speed: X1 active if Q ≥ Q_set; X2 the v1 pump rule at S_max (``rule_pump``);
    - min_speed: N1 active if Q ≤ Q_set; N2 the v1 pump rule at S_min, no_flow if it closes;
    - no_flow: C1 the v1 pump rule at S_max, max_speed if it opens.

    q_slack widens X1 and N1 (a flow within it of Q_set keeps the limit state): EPANET's Qtol
    for its solution. Ours take −``FLOW_ROUNDING``·Q_set, so that a flow equal to Q_set but for
    rounding is Q_set: a pump at a limit carrying its setpoint, as in series with another flow
    control holding the same flow, is not a fixed point (X1/N1 make it active), the case the
    solver reports not converged (proposal §4.6)."""
    assert pump.control is not None
    q_set, s_min, s_max = pump.control.setpoint, pump.control.min_speed, pump.speed
    if state == "active":
        if gain > el.pump_head(curve, s_max, q_set) + HTOL:
            return "max_speed"
        s_lo = el.stable_min_speed(curve, pump.control, s_max)
        if gain < el.pump_head(curve, s_lo, q_set) - HTOL:
            return "min_speed"
        return "active"
    if state == "max_speed":
        if q >= q_set + q_slack:
            return "active"
        running = rule_pump("running", gain, q, el.shutoff_head(curve, s_max)) == "running"
        return "max_speed" if running else "no_flow"
    if state == "min_speed":
        if q <= q_set - q_slack:
            return "active"
        running = rule_pump("running", gain, q, el.shutoff_head(curve, s_min)) == "running"
        return "min_speed" if running else "no_flow"
    if state == "no_flow":
        opens = rule_pump("no_flow", gain, q, el.shutoff_head(curve, s_max)) == "running"
        return "max_speed" if opens else "no_flow"
    return f"a flow-controlled pump that is on cannot be {state}"


FLOW_ROUNDING = 1.0e-9
"""Relative rounding of a flow-controlled pump's flow against its setpoint in X1 and N1 (ours,
``rule_flow_pump``): a flow carried through a fixed flow elsewhere in series differs from Q_set
by 1e-17 to 1e-12 relative in the fuzz networks."""


def rule_check(status: str, dh: float, q: float, hc: float) -> str:
    ex = dh - hc
    if abs(ex) > HTOL:
        return "closed" if (ex < -HTOL or q < -QTOL) else "open"
    return "closed" if q < -QTOL else status


def rule_prv(status: str, h1: float, h2: float, hset: float, hml: float, q: float) -> str:
    if status == "active":
        if q < -QTOL:
            return "closed"
        return "open" if h1 - hml < hset - HTOL else "active"
    if status == "open":
        if q < -QTOL:
            return "closed"
        return "active" if h2 >= hset + HTOL else "open"
    if h1 >= hset + HTOL and h2 < hset - HTOL:
        return "active"
    if h1 < hset - HTOL and h1 > h2 + HTOL:
        return "open"
    return "closed"


def rule_psv(status: str, h1: float, h2: float, hset: float, hml: float, q: float) -> str:
    if status == "active":
        if q < -QTOL:
            return "closed"
        return "open" if h2 + hml > hset + HTOL else "active"
    if status == "open":
        if q < -QTOL:
            return "closed"
        return "active" if h1 < hset - HTOL else "open"
    if h2 > hset + HTOL and h1 > h2 + HTOL:
        return "open"
    if h1 >= hset + HTOL and h1 > h2 + HTOL:
        return "active"
    return "closed"


def rule_fcv(status: str, h1: float, h2: float, q: float, qset: float, hml: float) -> str:
    if status == "active":
        return "open" if h1 - h2 < hml - HTOL else "active"
    if status == "open":
        if q < -QTOL:
            return "closed"
        return "active" if q >= qset else "open"
    return "open" if h1 - h2 > HTOL else "closed"


def port_d(project: Project, key: str) -> float:
    return nc.port_diameter(project, key)


def element_law(
    project: Project,
    c: Pump | IsolationValve | CheckValve | ControlValve,
    state: str,
    q: float,
    h_in: float,
    h_out: float,
    model: nc.Model,
) -> tuple[str, float]:
    """``network_check.element_law``, with a flow-controlled pump's law in its state (proposal
    vfd-pump-modes.md §4.4): active Q − Q_set (a fixed flow); max_speed / min_speed the
    fixed-speed pump's head law at s_max (its ``speed``) / s_min; no_flow, off Q."""
    if not (isinstance(c, Pump) and c.control is not None):
        return nc.element_law(project, c, state, q, h_in, h_out, model)
    if state == "active":
        return "flow", q - c.control.setpoint
    if state not in ("max_speed", "min_speed"):
        return "flow", q
    curve = next(cv for cv in project.pump_library if cv.id == c.curve_id)
    speed = c.control.min_speed if state == "min_speed" else c.speed
    return "head", h_out - h_in - el.pump_head(curve, speed, q)


def connects_heads(c: Pump | IsolationValve | CheckValve | ControlValve, state: str) -> bool:
    """``network_check.connects_heads``; a flow-controlled pump ties its port heads at a speed
    limit (a fixed-speed pump), not while active (a fixed flow) or closed."""
    if isinstance(c, Pump) and c.control is not None:
        return state in ("max_speed", "min_speed")
    return nc.connects_heads(c, state)


def status_problems(
    project: Project,
    flows: Flows,
    egl: Heads,
    states: States,
    model: nc.Model = OUR_MODEL,
    tol_h: float = 0.0,
    qtol: float | None = None,
) -> list[str]:
    """Elements whose state is not a fixed point of the status rules (heads known at both
    ports). tol_h: extra head slack (m) — a rule is re-evaluated with the heads shifted by
    ±tol_h and the state accepted if any shift keeps it."""
    rho = nc.density(project)
    curves = {c.id: c for c in project.pump_library}
    out = []
    if qtol is not None:  # flows below qtol (EPANET's Qtol / closed-link leaks) count as zero
        flows = {k: (0.0 if abs(v) <= qtol else v) for k, v in flows.items()}
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        st = states.get(c.id)
        if st in (None, "isolated", "off"):
            continue
        a, b = nc.two_port_ends(c)
        if a not in egl or b not in egl:
            continue
        h1, h2 = egl[a], egl[b]
        q = nc.port_inflow(project, a, flows)
        # the rule holds if it keeps the state at any of the head shifts
        shifts = [0.0] if tol_h == 0 else [0.0, tol_h, -tol_h]

        if isinstance(c, Pump):
            if c.status == "off":
                continue
            if c.control is not None:
                slack = qtol if qtol is not None else -FLOW_ROUNDING * c.control.setpoint
                curve = curves[c.curve_id]
                good = any(
                    rule_flow_pump(st, h2 - h1 + s, q, c, curve, slack) == st for s in shifts
                )
            else:
                shutoff = el.shutoff_head(curves[c.curve_id], c.speed)
                good = any(rule_pump(st, h2 - h1 + s, q, shutoff) == st for s in shifts)
        elif isinstance(c, IsolationValve):
            good = st == ("closed" if c.status == "isolated" else "open")
        elif isinstance(c, CheckValve):
            if c.status != "active":
                good = st == ("closed" if c.status == "locked_closed" else "open")
            else:
                hc = c.cracking_pressure / (rho * G)
                good = any(rule_check(st, h1 - h2 + s, q, hc) == st for s in shifts)
        elif c.status != "active":
            good = st == ("closed" if c.status == "failed_closed" else "open")
        else:
            d_in = port_d(project, a)
            k = el.valve_k(c.valve_type, c.resistance, d_in)
            if c.valve_type == "fcv":
                hml = el.valve_loss(k, c.setpoint, d_in, model.g) * model.k_scale
                qset = c.setpoint * (1 - 1e-9) - model.fcv_leak * (h1 - h2)
                good = any(rule_fcv(st, h1 + s, h2, q, qset, hml) == st for s in shifts)
            else:
                hml = el.valve_loss(k, q, d_in, model.g) * model.k_scale
                rule = rule_prv if c.valve_type == "prv" else rule_psv
                held = b if c.valve_type == "prv" else a
                held_d = port_d(project, b) if c.valve_type == "prv" else d_in
                hset = el.setpoint_head(
                    nc.port_elevation(project, held), c.setpoint, rho, q, held_d
                )
                good = any(rule(st, h1 + s, h2 - s, hset, hml, q) == st for s in shifts) or any(
                    rule(st, h1 - s, h2 + s, hset, hml, q) == st for s in shifts
                )
        if not good:
            out.append(f"{c.id} ({st})")
    return out


def law_problems(
    project: Project,
    flows: Flows,
    egl: Heads,
    states: States,
    model: nc.Model = OUR_MODEL,
    rel: float = 1e-6,
    abs_h: float = 1e-6,
    abs_q: float | None = None,
) -> list[str]:
    """Mass balance at every non-boundary component, energy on every connection with both
    heads, each pump/valve law in its state. Returns a list of problems."""
    out = []
    qmax = max((abs(q) for q in flows.values()), default=0.0)
    abs_q = abs_q if abs_q is not None else 1e-9 * qmax + 1e-14
    for cid, net in nc.net_inflow(project, flows).items():
        if abs(net) > abs_q:
            out.append(f"mass {cid}: {net:.3e}")
    nu = nc.kinematic_viscosity(project)
    for conn in project.connections:
        a, b = keys(conn)
        if a in egl and b in egl:
            h = nc.connection_head_loss(conn, flows[conn.id], nu, model)
            r = egl[a] - egl[b] - h
            if abs(r) > abs_h + rel * abs(h):
                out.append(f"energy {conn.id}: {r:.3e} (h={h:.4g})")
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        st = states.get(c.id)
        if st in (None, "isolated"):
            continue
        a, b = nc.two_port_ends(c)
        q = nc.port_inflow(project, a, flows)
        st2 = {"xfcv": "open", "xpressure": "open"}.get(st, st)
        if st2 in ("off", "no_flow"):
            kind, r = "flow", q
        else:
            if a not in egl or b not in egl:
                continue
            kind, r = element_law(project, c, st2, q, egl[a], egl[b], model)
        if kind == "head":
            if abs(r) > abs_h + rel * max(abs(egl[a] - egl[b]), 1.0):
                out.append(f"law {c.id} ({st}): head residual {r:.3e}")
        elif abs(r) > abs_q + rel * abs(q):
            out.append(f"law {c.id} ({st}): flow residual {r:.3e}")
    return out


def epanet_egl(project: Project, ep: EpanetResult, lay: Layout) -> dict[str, float]:
    """EPANET heads per port key, with merged check-valve inlets reconstructed from the
    merged pipe (EPANET's own constants)."""
    egl = dict(ep.heads)
    nu = nc.kinematic_viscosity(project)
    for cv, cid in lay.merged_cv.items():
        conn = next(c for c in project.connections if c.id == cid)
        a, b = keys(conn)
        q = ep.flows[cid]
        h = nc.connection_head_loss(conn, q, nu, EP_MODEL)
        if a == f"{cv}:inlet":
            egl[a] = egl[b] + h
        else:
            egl[b] = egl[a] - h
    return egl


def active_band(pump: Pump, curve: PumpCurve, s: str, d: str) -> list[Edge]:
    """Difference constraints (H_v − H_u ≤ w) of an active flow-controlled pump between suction
    node s and discharge node d: F_lo − Htol ≤ H_d − H_s ≤ F_max + Htol (rules A1, A2; F_lo =
    F(s_lo, Q_set), ``rule_flow_pump``)."""
    assert pump.control is not None
    q_set = pump.control.setpoint
    s_lo = el.stable_min_speed(curve, pump.control, pump.speed)
    f_lo = el.pump_head(curve, s_lo, q_set)
    f_max = el.pump_head(curve, pump.speed, q_set)
    return [(s, d, f_max + HTOL, pump.id), (d, s, -(f_lo - HTOL), pump.id)]


def zero_flow_infeasible(
    project: Project, egl: Heads, states: States, exclude: Collection[str] = frozenset()
) -> list[str]:
    """Ports without a head (an isolated or closed-off section, reported at zero flow) must
    admit heads under which every element there is consistent with zero flow. Conservative
    difference constraints at Q = 0 (H_v - H_u <= w): a connection, an open isolation valve, a
    locked-open check valve, a failed-open control valve and an ideal junction tie heads
    (zero loss at zero flow); a pump that is on needs H_dis - H_suc >= s^2 H0(0) (dead-headed
    or no flow; a flow-controlled pump at its maximum speed, proposal vfd-pump-modes.md §4.5,
    or, reported active, the band of rules A1/A2, ``active_band``); an active check valve or
    FCV needs H_in - H_out <= HTOL (closed or open at no flow); PRV/PSV and closed elements are
    left free. Known heads (ours) are fixed. Returns the components on a negative cycle (no
    head assignment exists) or []."""
    rho = nc.density(project)
    curves = {c.id: c for c in project.pump_library}
    # ports of flowing headless regions (``exclude``) are checked by flowing_headless;
    # elements touching them add no zero-flow constraint here.
    exclude = set(exclude)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl) - exclude
    if not unknown:
        return []
    nodes = nc.node_of_port(project)  # ideal junction ports share a node
    edges: list[Edge] = []

    def eq(a: str, b: str, label: str) -> None:
        edges.append((nodes[a], nodes[b], 0.0, label))
        edges.append((nodes[b], nodes[a], 0.0, label))

    involved = set()
    for conn in project.connections:
        a, b = keys(conn)
        if (a in unknown or b in unknown) and not ({a, b} & exclude):
            eq(a, b, conn.id)
            involved |= {a, b}
    for c in project.components:
        ports = [f"{c.id}:{p.id}" for p in c.ports]
        if not any(k in unknown for k in ports) or set(ports) & exclude:
            continue
        involved |= set(ports)
        if isinstance(c, Pump):
            if c.status == "on":
                s, d = f"{c.id}:suction", f"{c.id}:discharge"
                if states.get(c.id) == "active" and c.control is not None:
                    edges += active_band(c, curves[c.curve_id], nodes[s], nodes[d])
                else:  # a flow-controlled pump at zero flow: the fixed pump at s_max (§4.5)
                    sh = el.shutoff_head(curves[c.curve_id], c.speed)
                    edges.append((nodes[d], nodes[s], -sh, c.id))  # H_s - H_d <= -sh
        elif isinstance(c, IsolationValve):
            if c.status != "isolated":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
        elif isinstance(c, CheckValve):
            if c.status == "locked_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active":
                hc = c.cracking_pressure / (rho * G)
                edges.append((nodes[f"{c.id}:outlet"], nodes[f"{c.id}:inlet"], hc + HTOL, c.id))
        elif isinstance(c, ControlValve):
            if c.status == "failed_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active" and c.valve_type == "fcv":
                edges.append((nodes[f"{c.id}:outlet"], nodes[f"{c.id}:inlet"], HTOL, c.id))
    ref = "__REF__"
    for k in involved:
        if k in egl:
            edges.append((ref, nodes[k], egl[k], "known"))
            edges.append((nodes[k], ref, -egl[k], "known"))
    verts = {u for u, _, _, _ in edges} | {v for _, v, _, _ in edges}
    dist = dict.fromkeys(verts, 0.0)
    pred: dict[str, tuple[str, str] | None] = dict.fromkeys(verts)
    x = None
    for _ in range(len(verts)):
        x = None
        for u, v, w, label in edges:
            if dist[u] + w < dist[v] - 1e-9:
                dist[v] = dist[u] + w
                pred[v] = (u, label)
                x = v
        if x is None:
            return []
    # negative cycle: walk back
    for _ in range(len(verts)):
        x = pred[x][0]
    cyc, y = [], x
    while True:
        u, label = pred[y]
        cyc.append(label)
        y = u
        if y == x or len(cyc) > len(verts):
            break
    return sorted(set(cyc) - {"known"})


# --------------------------------------------------------------------------- floating sections
# The solver reports a section that no fixed head reaches but that cannot sit at zero flow (a pump
# loop behind a closed valve) with its flows and no heads, and an UNDETERMINED_PRESSURE warning
# naming its components. Checked independently here: energy must close around every loop of such
# a section with the independent laws at the reported flows, mass balance holds (law_problems),
# the pump / check-valve / FCV rules hold with the relative heads that gives, and the section
# must be flagged.


def flowing_headless(
    project: Project,
    flows: Flows,
    egl: Heads,
    states: States,
    flagged_ids: Collection[str] = frozenset(),
) -> tuple[list[str], set[str]]:
    """(problems, ports of headless regions that carry flow)."""
    nodes = nc.node_of_port(project)
    nu = nc.kinematic_viscosity(project)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []  # (node a, node b, H_a - H_b, label, flow)
    for conn in project.connections:
        a, b = keys(conn)
        if a in unknown and b in unknown:
            q = flows[conn.id]
            drop = nc.connection_head_loss(conn, q, nu, OUR_MODEL)
            edges.append((nodes[a], nodes[b], drop, conn.id, q))
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        a, b = nc.two_port_ends(c)
        st = states.get(c.id)
        if a not in unknown or b not in unknown or st is None or st == "isolated":
            continue
        st2 = {"xfcv": "open", "xpressure": "open"}.get(st, st)
        if not connects_heads(c, st2):
            continue
        q = nc.port_inflow(project, a, flows)
        kind, r = element_law(project, c, st2, q, 0.0, 0.0, OUR_MODEL)
        assert kind == "head"
        drop = r if isinstance(c, Pump) else -r  # H_in - H_out of the law at q
        edges.append((nodes[a], nodes[b], drop, c.id, q))
    for k in unknown:
        find(nodes[k])
    for a, b, _, _, _ in edges:
        parent[find(a)] = find(b)
    flowing = {find(a) for a, b, _, _, q in edges if q != 0.0}
    ports = {k for k in unknown if find(nodes[k]) in flowing}
    problems: list[str] = []
    if not flowing:
        return problems, ports
    # relative heads by BFS over the edges of flowing regions
    adj = defaultdict(list)
    for a, b, drop, label, _ in edges:
        if find(a) in flowing:
            adj[a].append((b, drop, label))
            adj[b].append((a, -drop, label))
    level: dict[str, float] = {}
    for root in sorted(adj):
        if root in level:
            continue
        level[root] = 0.0
        stack = [root]
        while stack:
            u = stack.pop()
            for v, drop, label in adj[u]:
                if v not in level:
                    level[v] = level[u] - drop
                    stack.append(v)
                elif abs(level[u] - drop - level[v]) > 1e-6 + 1e-6 * abs(drop):
                    problems.append(f"floating energy {label}: {level[u] - drop - level[v]:.3e}")
    comp_of = {k: k.split(":")[0] for k in ports}
    unflagged = sorted({comp_of[k] for k in ports} - set(flagged_ids))
    if unflagged:
        problems.append(f"flowing headless section not flagged UNDETERMINED_PRESSURE: {unflagged}")
    # status rules with relative heads (not PRV/PSV: they compare with absolute setpoints)
    rel = {k: level[nodes[k]] for k in ports if nodes[k] in level}
    sub: dict[str, str | None] = {}
    for c in project.components:
        if isinstance(c, ControlValve) and c.valve_type != "fcv":
            continue
        if isinstance(c, Pump | CheckValve | ControlValve):
            a, b = nc.two_port_ends(c)
            if a in rel and b in rel:
                sub[c.id] = states.get(c.id)
    if sub:
        problems += ["floating status " + s for s in status_problems(project, flows, rel, sub)]
    return problems, ports


# --------------------------------------------------------------------------- headless sections
# One feasibility check for every port without a reported head: closed-off sections (zero flow,
# free level) and flowing headless (floating) sections (heads = a free level + the relative heads
# that the independent laws give at the reported flows). Elements between such sections, or
# between one and a known head, are constrained as before, and a PRV/PSV there (it must be closed:
# open it would join the sections, active it would hold a head in them) must satisfy its CLOSED
# rule (rule_prv / rule_psv), a union of difference-constraint regions enumerated exactly.


def _floating_rel(
    project: Project, flows: Flows, egl: Heads, states: States
) -> dict[str, tuple[str, float]]:
    """port -> (region, relative EGL) for ports of flowing headless regions."""
    nodes = nc.node_of_port(project)
    nu = nc.kinematic_viscosity(project)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []
    for conn in project.connections:
        a, b = keys(conn)
        if a in unknown and b in unknown:
            q = flows[conn.id]
            edges.append((nodes[a], nodes[b], nc.connection_head_loss(conn, q, nu, OUR_MODEL), q))
    for c in project.components:
        if not isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            continue
        a, b = nc.two_port_ends(c)
        st = states.get(c.id)
        if a not in unknown or b not in unknown or st is None or st == "isolated":
            continue
        st2 = {"xfcv": "open", "xpressure": "open"}.get(st, st)
        if not connects_heads(c, st2):
            continue
        q = nc.port_inflow(project, a, flows)
        _, r = element_law(project, c, st2, q, 0.0, 0.0, OUR_MODEL)
        drop = r if isinstance(c, Pump) else -r
        edges.append((nodes[a], nodes[b], drop, q))
    for k in unknown:
        find(nodes[k])
    for a, b, _, _ in edges:
        parent[find(a)] = find(b)
    flowing = {find(a) for a, b, _, q in edges if q != 0.0}
    adj = defaultdict(list)
    for a, b, drop, _ in edges:
        if find(a) in flowing:
            adj[a].append((b, drop))
            adj[b].append((a, -drop))
    level: dict[str, float] = {}
    for r0 in sorted(adj):
        if r0 in level:
            continue
        level[r0] = 0.0
        stack = [r0]
        while stack:
            u = stack.pop()
            for v, drop in adj[u]:
                if v not in level:
                    level[v] = level[u] - drop
                    stack.append(v)
    return {
        k: (find(nodes[k]), level.get(nodes[k], 0.0)) for k in unknown if find(nodes[k]) in flowing
    }


def _border_regions(
    valve_type: str, st: str, i: str, o: str, ref: str, hset: float
) -> list[list[tuple[str, str, float]]]:
    """Difference-constraint regions (u, v, w: H_v - H_u <= w) in which a PRV/PSV between
    inlet node i and outlet node o keeps state st ('open' or 'closed') with setpoint head hset;
    the CLOSED rule is a union of regions (rule_prv / rule_psv)."""
    if valve_type == "prv":
        if st == "open":
            return [[(ref, o, hset + HTOL)]]
        return [
            [(ref, i, hset + HTOL), (i, ref, -(hset - HTOL))],
            [(i, ref, -(hset + HTOL)), (o, ref, -(hset - HTOL))],
            [(ref, i, hset - HTOL), (o, i, HTOL)],
        ]
    if st == "open":
        return [[(i, ref, -(hset - HTOL))]]
    return [[(o, i, HTOL)], [(ref, i, hset + HTOL), (ref, o, hset + HTOL)]]


def headless_infeasible(project: Project, flows: Flows, egl: Heads, states: States) -> list[str]:
    """[] if heads exist for every headless port (closed-off: free; floating: free level +
    relative heads) under which every element touching them keeps its reported state, else a
    description."""
    rho = nc.density(project)
    curves = {c.id: c for c in project.pump_library}
    floating = _floating_rel(project, flows, egl, states)
    unknown = {f"{c.id}:{p.id}" for c in project.components for p in c.ports} - set(egl)
    if not unknown:
        return []
    nodes = nc.node_of_port(project)
    ref = "__REF__"
    base: list[Edge] = []
    involved = set()

    def eq(a: str, b: str, label: str) -> None:
        base.append((nodes[a], nodes[b], 0.0, label))
        base.append((nodes[b], nodes[a], 0.0, label))

    def category(k: str) -> tuple[str, ...]:
        if k in egl:
            return ("known",)
        if k in floating:
            return ("float", floating[k][0])
        return ("off",)

    for conn in project.connections:
        a, b = keys(conn)
        if not ({a, b} & unknown):
            continue
        involved |= {a, b}
        if a in floating and b in floating:
            continue  # internal to a floating region: relative heads
        eq(a, b, conn.id)
    disj: list[tuple[str, list[list[Edge]]]] = []  # (label, [region edge lists])
    for c in project.components:
        ports = [f"{c.id}:{p.id}" for p in c.ports]
        if not any(k in unknown for k in ports):
            continue
        involved |= set(ports)
        cats = {category(k) for k in ports}
        if len(cats) == 1 and next(iter(cats))[0] == "float":
            # inside one floating region (flowing_headless checks it), except a PRV/PSV's
            # setpoint rule, which compares with the region's free level: its reported state
            # must hold at the level chosen for every element at once.
            st = states.get(c.id)
            if (
                isinstance(c, ControlValve)
                and c.valve_type in ("prv", "psv")
                and c.status == "active"
                and st in ("open", "closed")
            ):
                assert st is not None
                i, o = nodes[f"{c.id}:inlet"], nodes[f"{c.id}:outlet"]
                q = nc.port_inflow(project, f"{c.id}:inlet", flows)
                held = f"{c.id}:outlet" if c.valve_type == "prv" else f"{c.id}:inlet"
                hset = el.setpoint_head(
                    nc.port_elevation(project, held),
                    c.setpoint,
                    rho,
                    q if st == "open" else 0.0,
                    port_d(project, held),
                )
                if st == "open" and q < -QTOL:
                    disj.append((c.id, []))
                else:
                    regions = _border_regions(c.valve_type, st, i, o, ref, hset)
                    disj.append((c.id, [[(u, v, w, c.id) for u, v, w in r] for r in regions]))
            continue
        if isinstance(c, Pump):
            if c.status == "on":
                s, d = f"{c.id}:suction", f"{c.id}:discharge"
                if states.get(c.id) == "active" and c.control is not None:
                    base += active_band(c, curves[c.curve_id], nodes[s], nodes[d])
                else:  # a flow-controlled pump at zero flow: the fixed pump at s_max (§4.5)
                    sh = el.shutoff_head(curves[c.curve_id], c.speed)
                    base.append((nodes[d], nodes[s], -sh, c.id))
        elif isinstance(c, IsolationValve):
            if c.status != "isolated":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
        elif isinstance(c, CheckValve):
            if c.status == "locked_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active":
                hc = c.cracking_pressure / (rho * G)
                base.append((nodes[f"{c.id}:outlet"], nodes[f"{c.id}:inlet"], hc + HTOL, c.id))
        elif isinstance(c, ControlValve):
            i, o = nodes[f"{c.id}:inlet"], nodes[f"{c.id}:outlet"]
            if c.status == "failed_open":
                eq(f"{c.id}:inlet", f"{c.id}:outlet", c.id)
            elif c.status == "active" and c.valve_type == "fcv":
                base.append((o, i, HTOL, c.id))
            elif c.status == "active" and len(cats) > 1:
                held = f"{c.id}:outlet" if c.valve_type == "prv" else f"{c.id}:inlet"
                hset = nc.port_elevation(project, held) + c.setpoint / (rho * G)
                regions = _border_regions(c.valve_type, "closed", i, o, ref, hset)
                disj.append((c.id, [[(u, v, w, c.id) for u, v, w in r] for r in regions]))
    for k in involved:
        if k in egl:
            base.append((ref, nodes[k], egl[k], "known"))
            base.append((nodes[k], ref, -egl[k], "known"))
        elif k in floating:
            reg, rel = floating[k]
            fv = f"__F{reg}__"
            base.append((fv, nodes[k], rel, "float"))
            base.append((nodes[k], fv, -rel, "float"))

    def feasible(edges: list[Edge]) -> bool:
        verts = {u for u, _, _, _ in edges} | {v for _, v, _, _ in edges}
        dist = dict.fromkeys(verts, 0.0)
        for _ in range(len(verts) + 1):
            changed = False
            for u, v, w, _ in edges:
                if dist[u] + w < dist[v] - 1e-9:
                    dist[v] = dist[u] + w
                    changed = True
            if not changed:
                return True
        return False

    if len(disj) > 10:
        return [f"too many border PRV/PSVs to enumerate ({len(disj)})"]
    for combo in itertools.product(*[regs for _, regs in disj]):
        if feasible(base + [e for r in combo for e in r]):
            return []
    border = [d for d, _ in disj]
    return [
        f"no heads keep the headless sections' borders in their states (border PRV/PSV: {border})"
    ]


# --------------------------------------------------------------------------- our result, together


def section_flagged(result: SolvedState, *codes: str) -> set[str]:
    """Components named (``details.componentIds``) by the flags of the given codes."""
    return {
        cid.strip()
        for f in result.flags
        if f.code in codes
        for cid in str(f.details.get("componentIds", "")).split(",")
        if cid.strip()
    }


def floating_flagged(result: SolvedState) -> set[str]:
    """Components named by UNDETERMINED_PRESSURE flags."""
    return section_flagged(result, "UNDETERMINED_PRESSURE")


CONTROL_STATUS = {
    "active": "running",
    "max_speed": "running",
    "min_speed": "running",
    "no_flow": "no_flow",
    "off": "off",
}
"""PumpResult.status of each control state (proposal vfd-pump-modes.md §2.4)."""


SPEED_ROUNDING = 1.0e-12
"""Relative rounding allowed below s_lo when an active pump's speed is checked: ours computes
x_mono = x_e + ψ(x_e)/(−m), ``element_laws.x_mono`` the same closed form as 2x_e − 2h_e/m, so the
two s_lo differ by a few ulps; a speed held at s_lo (a head clamped to F(s_lo, Q_set)) must not
fail on that."""


def control_problems(
    project: Project, result: SolvedState, flows: Flows, egl: Heads, states: States
) -> list[str]:
    """Each flow-controlled pump's reported control against its definition (proposal
    vfd-pump-modes.md §2.4-2.6, §4.7): mode and setpoint as given; status as its state's
    (``CONTROL_STATUS``); off exactly when the pump is off; the speed s_max at max_speed and
    no_flow (and off: the field), s_min at min_speed, and, active, within [s_lo, s_max] (§4.3,
    s_lo = max(s_min, Q_set/x_mono) at most s_max: the stretch where F(·, Q_set) rises, which
    holds one root; ``SPEED_ROUNDING`` below s_lo is rounding) with |s²H₀(Q_set/s) − H| ≤ Htol
    at the head rise H (from the EGLs, or the relative heads of a floating section);
    ``PUMP_SETPOINT_NOT_MET`` exactly when the state is a limit or no_flow with |Q − Q_set| >
    Qtol (§2.5), and setpointAchieved its negation (None when off). A pump
    without a result (isolated) has no such flag, unless it is a no-flow pump with both sides
    closed off, which keeps its flags as a fixed-speed pump does (state no_flow, with
    PUMP_FLOW_REVERSAL; TSD §5.4). [] for a project without one."""
    pumps = [c for c in project.components if isinstance(c, Pump) and c.control is not None]
    if not pumps:
        return []
    curves = {cv.id: cv for cv in project.pump_library}
    floating = _floating_rel(project, flows, egl, states)
    out = []
    for c in pumps:
        assert c.control is not None
        flagged = any(
            f.code == "PUMP_SETPOINT_NOT_MET" and f.component_id == c.id for f in result.flags
        )
        pr = result.pump_results.get(c.id)
        if pr is None:  # flagged only as a v1 no-flow pump with both sides closed off is
            no_flow = [  # (TSD §5.4: no result, its PUMP_FLOW_REVERSAL kept)
                f.details.get("state") == "no_flow"
                for f in result.flags
                if f.code == "PUMP_SETPOINT_NOT_MET" and f.component_id == c.id
            ]
            reversal = any(
                f.code == "PUMP_FLOW_REVERSAL" and f.component_id == c.id for f in result.flags
            )
            if flagged and not (all(no_flow) and reversal):
                out.append(f"control {c.id}: no result, PUMP_SETPOINT_NOT_MET but not no_flow")
            continue
        ctl = pr.control
        if ctl is None:
            out.append(f"control {c.id}: no control in its result")
            continue
        st = ctl.state
        if ctl.mode != c.control.mode or ctl.setpoint != c.control.setpoint:
            out.append(f"control {c.id}: mode/setpoint {ctl.mode} {ctl.setpoint!r} not as given")
        if pr.status != CONTROL_STATUS[st]:
            out.append(f"control {c.id}: status {pr.status} in state {st}")
        if (c.status == "off") != (st == "off"):
            out.append(f"control {c.id}: state {st} with the pump {c.status}")
        q_set, s_min, s_max = c.control.setpoint, c.control.min_speed, c.speed
        if st == "active":
            s_lo = el.stable_min_speed(curves[c.curve_id], c.control, s_max)
            if not s_lo * (1.0 - SPEED_ROUNDING) <= pr.speed <= s_max:
                out.append(f"control {c.id}: active at {pr.speed!r} outside [{s_lo}, {s_max}]")
            a, b = f"{c.id}:suction", f"{c.id}:discharge"
            gain = None
            if a in egl and b in egl:
                gain = egl[b] - egl[a]
            elif a in floating and b in floating and floating[a][0] == floating[b][0]:
                gain = floating[b][1] - floating[a][1]
            if gain is not None:
                residual = el.pump_head(curves[c.curve_id], pr.speed, q_set) - gain
                if abs(residual) > HTOL * (1.0 + 1e-6) + 1e-9 * max(1.0, abs(gain)):
                    out.append(f"control {c.id}: speed {pr.speed!r} residual {residual:.3e} m")
        elif pr.speed != (s_min if st == "min_speed" else s_max):
            out.append(f"control {c.id}: speed {pr.speed!r} in state {st}")
        if st == "off":
            if ctl.setpoint_achieved is not None or flagged:
                out.append(f"control {c.id}: off with setpointAchieved/flag")
            continue
        missed = st != "active" and abs(pr.operating_flow - q_set) > QTOL
        if flagged != missed:
            out.append(f"control {c.id}: PUMP_SETPOINT_NOT_MET {flagged} in state {st}")
        if ctl.setpoint_achieved is not (not missed):
            out.append(f"control {c.id}: setpointAchieved {ctl.setpoint_achieved} in state {st}")
    return out


def zero_flow_and_floating(
    project: Project, flows_o: Flows, egl_o: Heads, states_o: States, result: SolvedState
) -> list[str]:
    """Zero-flow feasibility of headless regions without flow, the independent checks of
    flowing headless regions (``flowing_headless``) and the exact feasibility of every headless
    section with its borders (``headless_infeasible``)."""
    fprob, fports = flowing_headless(project, flows_o, egl_o, states_o, floating_flagged(result))
    zf = zero_flow_infeasible(project, egl_o, states_o, fports)
    hb = headless_infeasible(project, flows_o, egl_o, states_o)
    return ([f"zero flow impossible in a headless section: {zf}"] if zf else []) + fprob + hb


# --------------------------------------------------------------------------- missing results
# Written from the specs alone (SDD §4.10, TSD §5.4): a pump or valve has no result only where its
# head difference is not determined, and every check above skips it there (state 'isolated',
# ``our_states``). ``missing_result_problems`` holds each such element to that rule.


def headless_sections(
    project: Project, flows: Flows, egl: Heads, states: States, abs_q: float
) -> tuple[dict[str, str], set[str]]:
    """(section per port without a head, the sections that carry flow). Headless ports are
    joined through connections, ideal junctions and plugs (one node, ``nc.node_of_port``),
    Crane branches (as ``nc.isolated_ports`` joins them) and the pumps and valves whose reported
    state ties their two port heads (``connects_heads``); a section carries flow when one of
    those connections or elements carries more than abs_q (a floating section, SDD §4.10: its
    flows determined, its pressure level not; one without flow is closed off)."""
    nodes = nc.node_of_port(project)
    unknown = {k for k in nodes if k not in egl}
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(nodes[a])] = find(nodes[b])

    carried: list[tuple[str, float]] = []  # (a port, |flow| through the edge it joins)
    for conn in project.connections:
        a, b = keys(conn)
        if a in unknown and b in unknown:
            union(a, b)
            carried.append((a, abs(flows[conn.id])))
    for c in project.components:
        if nc.is_crane_branch(c):
            ports = [k for k in (f"{c.id}:{p.id}" for p in c.ports) if k in unknown]
            for k in ports[1:]:
                union(ports[0], k)
        elif isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            a, b = nc.two_port_ends(c)
            st = states.get(c.id)
            joined = st not in (None, "isolated") and connects_heads(c, st)
            if a in unknown and b in unknown and joined:
                union(a, b)
                carried.append((a, abs(nc.port_inflow(project, a, flows))))
    flowing = {find(nodes[a]) for a, q in carried if q > abs_q}
    return {k: find(nodes[k]) for k in unknown}, flowing


def missing_result_problems(
    project: Project, result: SolvedState, flows: Flows, egl: Heads, states: States
) -> list[str]:
    """Every pump and valve without a result held to the rule for when one has none (SDD
    §4.10, TSD §5.4). An element in a section closed off from every fixed-pressure boundary
    carries no flow and has no head and no result (flagged ISOLATED_SECTION); in a floating
    section (flows determined, pressure level not, ``headless_sections``) its result is
    reported, and an element between it and another head has none (flagged
    UNDETERMINED_PRESSURE); a pump held at no flow with one side closed off is reported
    dead-headed, and with both sides closed off has no result. So an element without a result
    must:

    - carry no flow: |flow| at both ports within the continuity tolerance of ``law_problems``;
    - have a port without a head (none where both ports have heads, a solved section);
    - not have both ports in one floating section (there its result is reported): not in one
      section that carries flow, nor in two such sections that one UNDETERMINED_PRESSURE flag
      names together (that flag is one section of the solve's, which the element joins: a
      component with every port in each of the two is among its names);
    - if it is a pump that is on with one side at a head, have its other side in a floating
      section, not closed off (closed off, the rules hold it at no flow, a running pump would
      tie the heads, and it is reported dead-headed);
    - be named, for each port without a head, by the flag that says why: UNDETERMINED_PRESSURE
      where that port's section carries flow, ISOLATED_SECTION where it carries none (so a
      section without flow that the element joins to a floating one, at zero flow, is not
      taken for a closed-off one: the flag would not name the element).

    Every other check skips such an element, so a result dropped where its values are
    determined shows only here. [] when every missing result is accounted for."""
    qmax = max((abs(q) for q in flows.values()), default=0.0)
    abs_q = 1e-9 * qmax + 1e-14  # as law_problems
    section, flowing = headless_sections(project, flows, egl, states, abs_q)
    closed_off = section_flagged(result, "ISOLATED_SECTION")
    in_floating = section_flagged(result, "UNDETERMINED_PRESSURE")
    floats = [  # the components each UNDETERMINED_PRESSURE flag names: one floating section
        {i.strip() for i in str(f.details.get("componentIds", "")).split(",") if i.strip()}
        for f in result.flags
        if f.code == "UNDETERMINED_PRESSURE"
    ]
    inside: dict[str, set[str]] = defaultdict(set)  # section -> components with every port in it
    for c in project.components:
        of_ports = [section.get(f"{c.id}:{p.id}") for p in c.ports]
        if of_ports[0] is not None and all(s == of_ports[0] for s in of_ports):
            inside[of_ports[0]].add(c.id)
    out = []
    for c in project.components:
        if isinstance(c, Pump):
            if c.id in result.pump_results:
                continue
        elif isinstance(c, IsolationValve | CheckValve | ControlValve):
            if c.id in result.valve_results:
                continue
        else:
            continue
        ends = nc.two_port_ends(c)
        q = max(abs(nc.port_inflow(project, k, flows)) for k in ends)
        headless = [k for k in ends if k not in egl]
        why = []
        if q > abs_q:
            why.append(f"it carries {q:.6g} m³/s")
        if not headless:
            why.append("both its ports have heads")
        elif len(headless) == 2:
            s, t = section[ends[0]], section[ends[1]]
            joined = any(inside[s] & f and inside[t] & f for f in floats)
            if s == t and s in flowing:
                why.append("both its ports are in one floating section")
            elif s in flowing and t in flowing and joined:
                why.append("one UNDETERMINED_PRESSURE flag names both its sides: one section")
        elif isinstance(c, Pump) and c.status == "on" and section[headless[0]] not in flowing:
            why.append(f"it is on with {headless[0]} closed off and its other side at a head")
        for k in headless:
            floating = section[k] in flowing
            if c.id not in (in_floating if floating else closed_off):
                code = "UNDETERMINED_PRESSURE" if floating else "ISOLATED_SECTION"
                kind = "a floating section" if floating else "a section without flow"
                why.append(f"{k} is in {kind}, and no {code} flag names it")
        if why:
            out.append(f"no result for {c.id}: {'; '.join(why)}")
    return out


# --------------------------------------------------------------------------- assigned flows
# Written from the specs alone (TSD §4.8, PRD §3.1, §3.2.1, SDD §4.11): an assigned-flow node
# withdraws its flow at its port (positive, a demand) or injects it (negative, a supply)
# whatever the pressure there, and is never a fixed head.


@dataclass(frozen=True)
class Expectation:
    """A reason why a network has no steady state (``assigned_flow_expectations``)."""

    kind: str
    every: tuple[str, ...]  # ids a message must name
    any_of: tuple[str, ...]  # ids it must name at least one of (the assigned-flow nodes)
    text: str
    word: str | None = None  # a word it must say

    def named(self, message: str) -> bool:
        """Whether a not-converged message states this reason: it names (quoted, as the
        solver's messages quote ids) every id of ``every`` and one of ``any_of``, and says
        ``word``."""
        return (
            all(f"'{i}'" in message for i in self.every)
            and any(f"'{i}'" in message for i in self.any_of)
            and (self.word is None or self.word in message.lower())
        )


def statically_closed(c: Component) -> bool:
    """A pump or valve closed whatever the heads, so at zero flow: an isolated isolation valve,
    a locked-closed check valve, a failed-closed control valve, a pump that is off."""
    if isinstance(c, IsolationValve):
        return c.status == "isolated"
    if isinstance(c, CheckValve):
        return c.status == "locked_closed"
    if isinstance(c, ControlValve):
        return c.status == "failed_closed"
    if isinstance(c, Pump):
        return c.status == "off"
    return False


def two_way(c: Component) -> bool:
    """A pump or valve that passes flow either way in every state: an isolation valve that is
    not isolated, a locked-open check valve, a failed-open control valve."""
    if isinstance(c, IsolationValve):
        return c.status != "isolated"
    if isinstance(c, CheckValve):
        return c.status == "locked_open"
    if isinstance(c, ControlValve):
        return c.status == "failed_open"
    return False


def one_way_capacity(c: Component) -> float | None:
    """The most a pump or valve that passes no reverse flow under its rules can pass forwards
    (inlet to outlet, suction to discharge) in any of its states; None for any other element.
    An active check valve (``rule_check``), PRV or PSV (``rule_prv``, ``rule_psv``) and a pump
    that is on (``rule_pump``; a flow-controlled one the same rule at a speed limit, X2/N2, and
    Q_set > 0 active) pass no reverse flow open or running and none closed, any forward flow
    (at its minimum speed a flow-controlled pump passes more than Q_set, N1); an active FCV
    (``rule_fcv`` with the departure of D9) at most its setpoint: active it passes Q_set, open
    its rule makes it active at Q ≥ Q_set, closed nothing."""
    if isinstance(c, ControlValve) and c.status == "active":
        return c.setpoint if c.valve_type == "fcv" else math.inf
    if isinstance(c, CheckValve) and c.status == "active":
        return math.inf
    if isinstance(c, Pump) and c.status == "on":
        return math.inf
    return None


def flow_setpoint(c: Component) -> float | None:
    """The flow a flow control fixes while it regulates: an active FCV's setpoint, a
    flow-controlled pump's Q_set when it is on (D11); None for any other element."""
    if isinstance(c, ControlValve) and c.status == "active" and c.valve_type == "fcv":
        return c.setpoint
    if isinstance(c, Pump) and c.status == "on" and c.control is not None:
        return c.control.setpoint
    return None


@dataclass
class FlowGraph:
    """The network for flow feasibility (``flow_graph``): blocks of nodes joined by connections,
    ideal junctions and two-way elements (``two_way``), and the one-way elements between them."""

    block: dict[str, str]  # port key -> block
    fixed: set[str]  # blocks with a reservoir or reference node port
    demand: dict[str, float]  # block -> net assigned flow out of the network there, m³/s
    magnitude: dict[str, float]  # block -> sum of the magnitudes of its assigned flows
    nodes: dict[str, tuple[str, ...]]  # block -> its assigned-flow nodes with a nonzero flow
    one_way: list[tuple[str, str, str, float]]  # (id, block in, block out, ``one_way_capacity``)
    closed: list[tuple[str, str, str]]  # statically closed elements: (id, block, block)


def flow_graph(project: Project) -> FlowGraph:
    """``FlowGraph`` of a project (nodes: ``network_check.node_of_port``)."""
    nodes = nc.node_of_port(project)
    parent = {n: n for n in nodes.values()}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(nodes[a])] = find(nodes[b])

    for conn in project.connections:
        union(*keys(conn))
    elements = [
        c
        for c in project.components
        if isinstance(c, Pump | IsolationValve | CheckValve | ControlValve)
    ]
    for c in elements:
        if two_way(c):
            union(*nc.two_port_ends(c))
    block = {k: find(n) for k, n in nodes.items()}
    fixed = {
        block[f"{c.id}:{p.id}"]
        for c in project.components
        if isinstance(c, Reservoir | IdealReferenceNode)
        for p in c.ports
    }
    demand: dict[str, float] = defaultdict(float)
    magnitude: dict[str, float] = defaultdict(float)
    ids: dict[str, tuple[str, ...]] = defaultdict(tuple)
    for key, q in nc.assigned_flows(project).items():
        b = block[key]
        demand[b] += q
        magnitude[b] += abs(q)
        if q != 0.0:
            ids[b] += (key.split(":")[0],)
    one_way, closed = [], []
    for c in elements:
        a, b = nc.two_port_ends(c)
        cap = one_way_capacity(c)
        if cap is not None:
            one_way.append((c.id, block[a], block[b], cap))
        elif statically_closed(c):
            closed.append((c.id, block[a], block[b]))
    return FlowGraph(block, fixed, dict(demand), dict(magnitude), dict(ids), one_way, closed)


def _short_side(g: FlowGraph) -> set[str]:
    """The blocks without a fixed head on one side of a minimum cut of the flow network whose
    maximum flow tells whether the assigned flows have a flow pattern at all: a source feeding
    every block's net supply, a sink taking every block's net demand, the fixed-head blocks
    merged into one node whose net demand is minus the others' total (continuity over the whole
    network), and each one-way element an arc of its capacity. Every pattern of flows that
    keeps continuity and each element's rule (``one_way_capacity``; statically closed
    elements carry nothing, connections and two-way elements anything inside a block) is such
    a flow, so one that does not saturate the source has none (max-flow min-cut theorem, Ford
    and Fulkerson 1956; Edmonds-Karp augmenting paths). set() when it saturates."""
    src, sink, fix = "__source__", "__sink__", "__fixed__"
    cap: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def node(b: str) -> str:
        return fix if b in g.fixed else b

    for _, a, b, c in g.one_way:
        if node(a) != node(b):
            cap[node(a)][node(b)] += c
            cap[node(b)][node(a)] += 0.0  # the residual arc
    free = {b: d for b, d in g.demand.items() if b not in g.fixed}
    free[fix] = -sum(free.values())
    for b, d in free.items():
        if d > 0.0:
            cap[b][sink] += d
            cap[sink][b] += 0.0
        elif d < 0.0:
            cap[src][b] += -d
            cap[b][src] += 0.0
    total = sum(cap[src].values())
    if total == 0.0:
        return set()
    eps = 1.0e-12 * total  # rounding of the augmenting flows
    flow: dict[tuple[str, str], float] = defaultdict(float)

    def residual(u: str, v: str) -> float:
        return cap[u][v] - flow[(u, v)] + flow[(v, u)]

    def reached() -> dict[str, str | None]:
        pred: dict[str, str | None] = {src: None}
        queue = [src]
        for u in queue:
            for v in sorted(cap[u]):
                if v not in pred and residual(u, v) > eps:
                    pred[v] = u
                    queue.append(v)
        return pred

    sent = 0.0
    while True:
        pred = reached()
        if sink not in pred:
            break
        path, v = [], sink
        while (u := pred[v]) is not None:
            path.append((u, v))
            v = u
        push = min(residual(u, v) for u, v in path)
        for u, v in path:
            back = min(push, flow[(v, u)])  # cancel reverse flow first
            flow[(v, u)] -= back
            flow[(u, v)] += push - back
        sent += push
    if sent >= total - eps:
        return set()
    side = set(pred) - {src}
    if fix in side:
        side = set(cap) - side - {src, sink}
    return side - {fix}


def assigned_flow_expectations(project: Project) -> list[Expectation]:
    """Why the network has no steady state because of its assigned flows, from the project alone
    (TSD §4.8, PRD §3.1; [] when nothing says so, and for a project without a nonzero assigned
    flow). Each is a part P of the network that no fixed head reaches (blocks of ``flow_graph``)
    with a net assigned flow d out of the network, whose crossing elements are one-way elements
    (``one_way_capacity``) and statically closed ones:

    - ``disconnected``: no one-way element crosses P's boundary (it is closed off by statically
      closed elements, PRD §3.1) and d ≠ 0: continuity over P fails;
    - ``no_flow_path``: d exceeds what the one-way elements into P can pass forwards, or −d
      what those out of it can (they pass nothing backwards): continuity over P fails whatever
      the heads. P is found from a minimum cut (``_short_side``) and checked on its own, with a
      margin of Qtol per crossing element and 1e-9 of the flows concerned;
    - ``over_controlled``: P's crossing elements other than statically closed ones are flow
      controls (``flow_setpoint``), P holds no active PRV or PSV (which would hold a head in
      it), and continuity forces each to its setpoint: one control passing d (into P) or −d
      (out of it) equal to its Q_set, or several FCVs all into P (or all out of it) with |d|
      the sum of their setpoints. Each control then regulates (an open FCV at Q_set turns
      active, rule_fcv; a flow-controlled pump at a limit carrying Q_set too, X1/N1), fixing a
      flow and no head, so nothing fixes the pressure in P (TSD §4.8 "Flow controls in
      series"; equal within ``FLOW_ROUNDING``). The message names the controls and says the
      pressure is undetermined.

    A not-converged message states an expectation when it names one of P's assigned-flow nodes
    and, for ``over_controlled``, the controls and that the pressure is undetermined
    (``Expectation.named``)."""
    afs = nc.assigned_flows(project)
    if not any(afs.values()):
        return []
    g = flow_graph(project)
    out: list[Expectation] = []

    def components(blocks: set[str], arcs: list[tuple[str, str, str, float]]) -> list[set[str]]:
        parent = {b: b for b in blocks}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for _, a, b, _ in arcs:
            if a in parent and b in parent:
                parent[find(a)] = find(b)
        groups: dict[str, set[str]] = defaultdict(set)
        for b in blocks:
            groups[find(b)].add(b)
        return sorted(groups.values(), key=sorted)

    def crossing(part: set[str]) -> tuple[list[tuple[str, float, bool]], list[str]]:
        """(one-way elements crossing: id, capacity, whether forwards into the part; closed)."""
        arcs = [(i, c, b in part) for i, a, b, c in g.one_way if (a in part) != (b in part)]
        shut = [i for i, a, b in g.closed if (a in part) != (b in part)]
        return arcs, shut

    def assigned(part: set[str]) -> tuple[float, float, tuple[str, ...]]:
        d = sum(g.demand.get(b, 0.0) for b in sorted(part))  # a fixed order of the sums
        mag = sum(g.magnitude.get(b, 0.0) for b in sorted(part))
        ids = tuple(sorted(i for b in part for i in g.nodes.get(b, ())))
        return d, mag, ids

    short = _short_side(g)
    for part in components(short, g.one_way):
        d, mag, ids = assigned(part)
        arcs, shut = crossing(part)
        cap_in = sum(c for _, c, into in arcs if into)
        cap_out = sum(c for _, c, into in arcs if not into)
        finite = sum(c for _, c, _ in arcs if math.isfinite(c))
        margin = QTOL * (len(arcs) + 1) + 1.0e-9 * (mag + finite)
        if d - cap_in <= margin and -d - cap_out <= margin:
            continue
        where = f"assigned flows {list(ids)} (net {d:.6g} m³/s out of the network)"
        if not arcs:
            out.append(Expectation("disconnected", (), ids, f"{where} closed off by {shut}"))
        else:
            text = (
                f"{where} in a part no fixed head reaches, which one-way elements"
                f" {[i for i, _, _ in arcs]} can feed at most {cap_in:.6g} and drain at most"
                f" {cap_out:.6g} m³/s ({shut} closed)"
            )
            out.append(Expectation("no_flow_path", (), ids, text))
    # parts joined by every one-way element but the flow controls
    controls = {c.id: q for c in project.components if (q := flow_setpoint(c)) is not None}
    fcvs = {c.id for c in project.components if isinstance(c, ControlValve) and c.id in controls}
    held = {
        c.id
        for c in project.components
        if isinstance(c, ControlValve) and c.status == "active" and c.valve_type != "fcv"
    }
    others = [arc for arc in g.one_way if arc[0] not in controls]
    for part in components(set(g.block.values()) - g.fixed, others):
        d, _, ids = assigned(part)
        arcs, _ = crossing(part)
        if not ids or not arcs or any(i not in controls for i, _, _ in arcs):
            continue  # reached through an element that is not a flow control, or none at all
        if any(i in held and a in part for i, a, _, _ in others):
            continue  # an active PRV or PSV in it may hold a head
        if len(arcs) > 1 and not (
            all(i in fcvs for i, _, _ in arcs) and len({into for _, _, into in arcs}) == 1
        ):
            continue  # the flows are not forced
        forced = d if arcs[0][2] else -d
        total = sum(controls[i] for i, _, _ in arcs)
        if abs(forced - total) <= FLOW_ROUNDING * total:
            names = tuple(i for i, _, _ in arcs)
            text = (
                f"assigned flows {list(ids)} force {list(names)} to their setpoints"
                f" ({forced:.6g} m³/s): the pressure between them is undetermined"
            )
            out.append(Expectation("over_controlled", names, ids, text, "undetermined"))
    return out


def undetermined_heads(project: Project, egl: Heads, states: States) -> list[str]:
    """Ports we report a head at whose head nothing determines (TSD §4.8 "Flow controls in
    series": a node fed only through a fixed flow). Each must reach a fixed head through
    connections, ideal junctions and pumps and valves that tie their two port heads in their
    reported state (a running pump or a flow-controlled pump at a speed limit, ``connects_heads``;
    an open valve), or the port whose head an active PRV (outlet) or PSV (inlet) holds at its
    setpoint. An active FCV or flow-controlled pump fixes a flow, not a head, and an active PRV
    or PSV does not tie its other port. [] when every reported head is determined."""
    nodes = nc.node_of_port(project)
    parent = {n: n for n in nodes.values()}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(nodes[a])] = find(nodes[b])

    held = set()
    for conn in project.connections:
        union(*keys(conn))
    for c in project.components:
        if isinstance(c, Reservoir | IdealReferenceNode):
            held |= {f"{c.id}:{p.id}" for p in c.ports}
        elif isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            st = states.get(c.id)
            a, b = nc.two_port_ends(c)
            if isinstance(c, Pump):
                if st is not None and connects_heads(c, st):
                    union(a, b)
            elif st == "open":
                union(a, b)
            elif st == "active" and isinstance(c, ControlValve) and c.valve_type != "fcv":
                held.add(b if c.valve_type == "prv" else a)
    determined = {find(nodes[k]) for k in held}
    loose = sorted(k for k in egl if k in nodes and find(nodes[k]) not in determined)
    if not loose:
        return []
    return [f"undetermined heads reported at {loose[:6]}{' ...' if len(loose) > 6 else ''}"]


VAPOR_MARGIN = 1.0
"""Pa: an absolute pressure this close to the vapor pressure (or to 0) is not checked against
BELOW_VAPOR_PRESSURE (either is right at the threshold)."""


def assigned_flow_problems(project: Project, result: SolvedState, flows: Flows) -> list[str]:
    """A converged result with assigned-flow nodes against the specs: no
    ``assigned_flow_expectations`` (each says there is no steady state); a node whose port has
    a head has a boundary result (PRD §3.2.1), and a boundary result is of type assigned_flow,
    has the flow its connection carries into the network as its outflow, minus the node's flow
    within the continuity tolerance (TSD §5.2, as ``law_problems``), and its port's EGL (a node
    without a head is at rest in a closed-off section, a plug's case, or in a floating section,
    which ``flowing_headless`` checks); at a port with a head (PRD §3.2.1, TSD §4.8 "Results"):
    the port's elevation, the speed |Q|/A of the connection's end segment, HGL = EGL − v²/(2g),
    static pressure ρg(EGL − z − v²/(2g)) (TSD §5.1), absolute pressure = static +
    atmospheric, and BELOW_VAPOR_PRESSURE on the node exactly when the absolute pressure is
    below the vapor pressure, or at most 0 Pa when the fluid has none (TSD §5.5;
    ``VAPOR_MARGIN``). [] for a project without one."""
    afs = [c for c in project.components if isinstance(c, AssignedFlow)]
    if not afs:
        return []
    out = [f"converged although {e.text}" for e in assigned_flow_expectations(project)]
    abs_q = 1e-9 * max((abs(q) for q in flows.values()), default=0.0) + 1e-14  # as law_problems
    rho, _, p_vap = nc.fluid_state(project)
    threshold = 0.0 if p_vap is None else p_vap
    for c in afs:
        key = f"{c.id}:{c.ports[0].id}"
        node = result.node_results.get(key)
        br = result.boundary_results.get(c.id)
        if br is not None:
            if br.type != "assigned_flow":
                out.append(f"assigned flow {c.id}: boundary result of type {br.type}")
            sent = -nc.port_inflow(project, key, flows)  # into the network through its pipe
            if abs(br.outflow - sent) > 1e-12 * abs(sent) or abs(br.outflow + c.flow) > abs_q:
                out.append(
                    f"assigned flow {c.id}: outflow {br.outflow!r}, its connection {sent!r},"
                    f" flow {c.flow!r}"
                )
            if node is not None and abs(br.egl - node.egl) > 1e-9 * max(1.0, abs(node.egl)):
                out.append(f"assigned flow {c.id}: boundary EGL {br.egl!r}, port {node.egl!r}")
        if node is None:
            continue
        if br is None:
            out.append(f"assigned flow {c.id}: a head at its port and no boundary result")
        z = nc.port_elevation(project, key)
        _, d, _ = nc.port_connection(project, key)
        v = abs(nc.port_inflow(project, key, flows)) / area(d)
        hv = v * v / (2.0 * G)
        p = rho * G * (node.egl - z - hv)
        flagged = any(
            f.code == "BELOW_VAPOR_PRESSURE" and f.component_id == c.id for f in result.flags
        )
        below = (
            node.absolute_pressure < threshold
            if p_vap is not None
            else (node.absolute_pressure <= 0.0)
        )
        bad = []
        if abs(node.elevation - z) > 1e-12 * max(1.0, abs(z)):
            bad.append(f"elevation {node.elevation!r} (port {z!r})")
        if abs(abs(node.velocity) - v) > 1e-9 * v + 1e-12:
            bad.append(f"velocity {node.velocity!r} (|Q|/A {v!r})")
        if abs(node.hgl - (node.egl - hv)) > 1e-9 * max(1.0, abs(node.egl)):
            bad.append(f"HGL {node.hgl!r} (EGL − v²/2g {node.egl - hv!r})")
        if abs(node.pressure - p) > 1e-6 + 1e-9 * abs(p):
            bad.append(f"pressure {node.pressure!r} (ρg(H − z − v²/2g) {p!r})")
        p_abs = node.pressure + result.atmospheric_pressure
        if abs(node.absolute_pressure - p_abs) > 1e-6 + 1e-12 * abs(p_abs):
            bad.append(f"absolute pressure {node.absolute_pressure!r} (p + p_atm {p_abs!r})")
        if abs(node.absolute_pressure - threshold) > VAPOR_MARGIN and flagged != below:
            bad.append(
                f"BELOW_VAPOR_PRESSURE {flagged} at absolute {node.absolute_pressure:.6g} Pa"
            )
        out += [f"assigned flow {c.id}: {b}" for b in bad]
    return out


# --------------------------------------------------------------------------- our result, checked


def self_check(project: Project, result: SolvedState) -> list[str]:
    """Every independent check of a converged result of ours, as ``fuzz`` records it in
    ``self_check`` (with the plug twin's, ``fuzz.plug_twin_problems``): the laws, the status
    rules, the headless sections, the flow controls, determined heads, the assigned-flow nodes
    and the pumps and valves without a result. [] when the result passes them all."""
    flows, egl, states = ours_solution(project, result)
    return (
        law_problems(project, flows, egl, states)
        + ["status " + s for s in status_problems(project, flows, egl, states)]
        + zero_flow_and_floating(project, flows, egl, states, result)
        + control_problems(project, result, flows, egl, states)
        + undetermined_heads(project, egl, states)
        + assigned_flow_problems(project, result, flows)
        + missing_result_problems(project, result, flows, egl, states)
    )
