"""Closed-form expected results for assigned-flow nodes (SDD §4.11; TSD §4.8 and the §10.1 plan
row "Assigned-flow node"; PRD §3.1, §3.2.1).

Semantics, from the specs (not from solver code). An assigned-flow node has one port, at which
a flow Q_a leaves the network (a demand, Q_a > 0) or enters it (a supply, Q_a < 0) whatever the
pressure there. Its port is a free node of the network, with no head equation of its own and
the continuity equation

    (flow into the port through its connection) = Q_a

(TSD §4.8: Q_a is the node's demand in the GGA; Q_a = 0 is a plug). It is never a fixed head
(``NO_FIXED_HEAD`` still applies). Its EGL is a result, and its static pressure
p = ρg(H − z − v²/2g) takes v in the connected pipe's end segment, as at any port that is not
a reservoir or reference node (TSD §4.8 "Results"); BELOW_VAPOR_PRESSURE applies to it
(PRD §3.2.1).

A line that ends at an assigned-flow node carries Q_a through every element (continuity), so its
heads follow from the reservoir at its other end without iteration (``DeadEnd``):

    H(next port) = H(port) − h_line(Q_a),   H(outlet) = H(inlet) + rise(Q_a)

with rise = s² H₀(Q_a/s) across a running pump and −(h_c + K Q_a|Q_a|/(2gA²)) across an open
valve. A demand between two reservoirs has one unknown, solved with brentq. Each pump and valve
must be in the state its status rules select at the forced flow (``element_laws``, guarded by
STATE_MARGIN): a fixed-speed pump runs at Q_a; a check valve is open; an FCV whose setpoint is
above Q_a is open (passing less than its setpoint, as in ``fcv_open``); a flow-controlled pump
(CLAUDE.md D11) whose setpoint differs from Q_a cannot be active (Q = Q_set), so it runs at the
speed limit its rules select: maximum speed for Q_a < Q_set (X1 keeps it there), minimum speed
for Q_a > Q_set (N1), as when an FCV in series fixes its flow
(``derivations_pump_control.pump_flow_control_series_fcv_limits``).

Pipe law and fittings as in ``line``; pump and valve laws as in ``element_laws``. Every pipe,
elevation, flow, curve point and setpoint is a test input. Independence: written without reading
``opensolve_pipe.services``; nothing here imports it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from scipy.optimize import brentq

from opensolve_pipe.models.components import (
    AssignedFlow,
    CheckValve,
    Component,
    ControlValve,
    Plug,
    Pump,
)
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    assigned_flow,
    builtin_water,
    check_valve,
    control_valve,
    crane_tee,
    custom_fluid,
    flow_control,
    ideal_tee,
    make_project,
    pump,
    reservoir,
)
from tests.reference.derivations_branches import STEP_MARGIN
from tests.reference.derivations_pump_control import control_flags, pump_expected, require_state
from tests.reference.derivations_pumps import SUCTION_A, curve_a
from tests.reference.line import Line, require_turbulent

MODULE = "derivations_assigned_flow"
MARGIN = el.STATE_MARGIN
SITE_ATMOSPHERE = dv.standard_atmosphere_pressure(0.0)
"""Pa absolute: every case sits at site elevation 0 (fluids ATMOSPHERE_1976(0).P)."""

AF_METHOD = (
    "assigned flow (SDD 4.11, TSD 4.8): a free node whose connection carries Q_a, no head "
    "equation of its own; static pressure with v in the connected pipe"
)
DEAD_END_METHOD = AF_METHOD + "; the line carries Q_a by continuity, heads stepped from R1"

Element = Pump | CheckValve | ControlValve
ELEMENT_PORTS = {"pump": ("suction", "discharge"), "valve": ("inlet", "outlet")}


def _source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def _fluid_a() -> tuple[CustomFluid, float, float, float]:
    name, rho, mu = dv.FLUID_A
    return custom_fluid(name, rho, mu), rho, mu, mu / rho


def require_no_vapor_flag(
    pressures: dict[str, float],
    rho: float,
    p_vap: float | None,
    below: Sequence[str] = (),
) -> None:
    """Guard: BELOW_VAPOR_PRESSURE (invalid, so exhaustive) is raised exactly at the ``below``
    ports: absolute static pressure p + p_atm below the vapor pressure, or ≤ 0 Pa when the fluid
    has none (TSD §5.5), cleared by ρ g STATE_MARGIN either way."""
    threshold = 0.0 if p_vap is None else p_vap
    clear = rho * dv.G * MARGIN
    for key, p in pressures.items():
        absolute = p + SITE_ATMOSPHERE
        if key in below:
            if not absolute < threshold - clear:
                raise ValueError(f"{key} must be clearly below the vapor pressure")
        elif not absolute > threshold + clear:
            raise ValueError(f"{key} is too close to the vapor pressure")


# --- A reservoir and an assigned flow joined in series --------------------------------------------


@dataclass(frozen=True)
class DeadEnd:
    """R1 → line L1 → element 1 → … → line Ln → AF1: a reservoir and an assigned flow at the two
    ends of one series path, connections drawn from R1 towards AF1. Continuity at every node
    of the path gives each connection the flow Q_a of AF1 (negative for a supply)."""

    z1: float
    level1: float
    lines: Sequence[Line]
    elements: Sequence[Element]
    af: AssignedFlow

    def __post_init__(self) -> None:
        if len(self.lines) != len(self.elements) + 1:
            raise ValueError("a dead end alternates lines and elements, starting with a line")

    @property
    def h1(self) -> float:
        return self.z1 + self.level1

    @property
    def q(self) -> float:
        return self.af.flow

    def port_keys(self) -> list[tuple[str, str]]:
        """(from, to) port keys of L1…Ln."""
        ends = ["R1:port_1"]
        for e in self.elements:
            a, b = ELEMENT_PORTS[e.type]
            ends += [f"{e.id}:{a}", f"{e.id}:{b}"]
        ends.append(f"{self.af.id}:port_1")
        return [(ends[2 * i], ends[2 * i + 1]) for i in range(len(self.lines))]

    def connections(self) -> list[PipeConnection]:
        return [
            line.connect(f"L{i + 1}", a, b)
            for i, (line, (a, b)) in enumerate(zip(self.lines, self.port_keys(), strict=True))
        ]

    def components(self) -> list[Component]:
        return [reservoir("R1", self.z1, self.level1), *self.elements, self.af]

    def egl(self, nu: float, rises: Sequence[float]) -> dict[str, float]:
        """EGL at every port: from H_R1, minus each line's loss at Q_a, plus each element's
        EGL rise (a pump's head, minus a valve's drop)."""
        out = {"R1:port_1": self.h1}
        e = self.h1
        for i, (line, (_, b)) in enumerate(zip(self.lines, self.port_keys(), strict=True)):
            e -= line.head_loss(self.q, nu)
            out[b] = e
            if i < len(self.elements):
                a_next = self.port_keys()[i + 1][0]
                e += rises[i]
                out[a_next] = e
        return out

    def pressures(self, rho: float, egl: dict[str, float]) -> dict[str, float]:
        """Static pressure at every port but R1's, v in the line on that port (TSD §5.1)."""
        out = {}
        for i, (a, b) in enumerate(self.port_keys()):
            v = self.lines[i].velocity(self.q)
            for key in (a, b):
                if key == "R1:port_1":
                    continue
                component = key.split(":")[0]
                z = next(c.elevation for c in self.components() if c.id == component)
                out[key] = dv.static_pressure(rho, egl[key], z, v)
        return out


def dead_end_case(
    *,
    name: str,
    title: str,
    description: str,
    method: str,
    chain: DeadEnd,
    fluid: CustomFluid | BuiltinFluid,
    rises: Sequence[float] = (),
    pumps: dict[str, dict[str, float | str]] | None = None,
    valves: dict[str, dict[str, str]] | None = None,
    flags: Sequence[dict[str, str]] = (),
    pump_library: Sequence[PumpCurve] = (),
    below_vapor: Sequence[str] = (),
    record_vapor: bool = False,
) -> ReferenceCase:
    """Build a DeadEnd case: every connection carries Q_a, EGL at every port, static pressure
    at every port but the reservoir's. ``rises``: EGL rise across each element at Q_a.
    ``below_vapor``: ports expected below the vapor pressure (flagged on their component);
    ``record_vapor``: the case records the vapor and atmospheric pressures it relies on."""
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    require_turbulent(nu, [(chain.q, line) for line in chain.lines])
    egl = chain.egl(nu, rises)
    pressures = chain.pressures(rho, egl)
    require_no_vapor_flag(pressures, rho, p_vap, below_vapor)
    all_flags = list(flags) + [
        {"code": "BELOW_VAPOR_PRESSURE", "componentId": cid}
        for cid in sorted({key.split(":")[0] for key in below_vapor})
    ]
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        fluid,
        chain.components(),
        chain.connections(),
        pump_library=pump_library,
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={f"L{i + 1}": chain.q for i in range(len(chain.lines))},
        egl=egl,
        pressures=pressures,
        flags=all_flags,
        vapor_pressure=p_vap if record_vapor else "unchecked",
        atmospheric_pressure=SITE_ATMOSPHERE if record_vapor else None,
        pumps=pumps or {},
        valves=valves or {},
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=expected,
    )


# --- Cases: dead ends ----------------------------------------------------------------------------


def assigned_flow_demand_dead_end() -> ReferenceCase:
    """R1 (H 12 m) → L1 (102.3 mm, 150 m; sharp entrance, two long-radius elbows, a gate
    valve) → AF1, a demand of 12 L/s at z 1 m: the end of a dead-end line.

    Continuity gives L1 the demand, Q = Q_a; the energy equation then gives the node's EGL in
    closed form, H_AF = H_R1 − h_L1(Q_a), and its static pressure ρg(H_AF − z − v²/2g) with v
    the velocity in L1."""
    fluid, *_ = _fluid_a()
    chain = DeadEnd(
        10.0,
        2.0,
        [Line(0.1023, 150.0, (("entrance_sharp", 1), ("elbow_90_lr", 2), ("gate_valve", 1)))],
        [],
        assigned_flow("AF1", 1.0, 0.012),
    )
    return dead_end_case(
        name="assigned_flow_demand_dead_end",
        title="Assigned demand at a dead end",
        description=(
            "A reservoir feeds a 12 L/s assigned demand at the end of a single line: verifies "
            "that the demand fixes the line's flow (a free node with one open link that still "
            "passes flow) and the node's EGL and static pressure (v in the connected pipe)."
        ),
        method=DEAD_END_METHOD + "; Darcy-Weisbach + Colebrook, no iteration",
        chain=chain,
        fluid=fluid,
    )


def assigned_flow_supply_dead_end() -> ReferenceCase:
    """AF1, a supply of 9 L/s (flow −0.009 m³/s) at z 4 m, at the end of L1 (77.9 mm, 80 m;
    three elbows and an exit) drawn from R1 (H 3 m) to AF1.

    The supply enters at AF1 and drains to R1, against the connection's direction: L1 carries
    Q_a = −0.009 m³/s, and the signed energy equation gives H_AF = H_R1 − h_L1(Q_a) =
    H_R1 + h_L1(|Q_a|), above the reservoir."""
    fluid, *_ = _fluid_a()
    chain = DeadEnd(
        0.0,
        3.0,
        [Line(0.0779, 80.0, (("elbow_90_lr", 3), ("exit", 1)))],
        [],
        assigned_flow("AF1", 4.0, -0.009),
    )
    return dead_end_case(
        name="assigned_flow_supply_dead_end",
        title="Assigned supply at a dead end",
        description=(
            "A 9 L/s assigned supply (negative flow) at the end of a line draining to a "
            "reservoir: verifies the sign convention (flow entering the network), the negative "
            "flow in a connection drawn towards the node, and the node's EGL above the "
            "reservoir's by the line loss."
        ),
        method=DEAD_END_METHOD + "; Darcy-Weisbach + Colebrook, signed loss, no iteration",
        chain=chain,
        fluid=fluid,
    )


def assigned_flow_below_vapor_pressure() -> ReferenceCase:
    """Water at 70 °C (CoolProp): R1 (H 3 m) → L1 (77.9 mm, 50 m; sharp entrance, two elbows) →
    AF1, a 12 L/s demand 7 m up, at the site's sea-level atmosphere.

    H_AF = H_R1 − h_L1(Q_a) lies so far below the node that p + p_atm < p_vap: the demand is
    still delivered (it does not depend on pressure) and the node is flagged
    BELOW_VAPOR_PRESSURE (invalid; PRD §3.2.1, TSD §5.5)."""
    fluid = builtin_water(343.15)
    chain = DeadEnd(
        0.0,
        3.0,
        [Line(0.0779, 50.0, (("entrance_sharp", 1), ("elbow_90_lr", 2)))],
        [],
        assigned_flow("AF1", 7.0, 0.012),
    )
    return dead_end_case(
        name="assigned_flow_below_vapor_pressure",
        title="Assigned demand below the vapor pressure",
        description=(
            "A demand drawn 7 m above a reservoir's surface through a long line, in 70 C "
            "water: verifies that the demand is met regardless of pressure, the node's "
            "sub-atmospheric static pressure and the BELOW_VAPOR_PRESSURE flag on the node."
        ),
        method=(
            DEAD_END_METHOD + "; CoolProp water (IAPWS-95) properties and saturation pressure; "
            "fluids ATMOSPHERE_1976(0).P; Darcy-Weisbach + Colebrook"
        ),
        chain=chain,
        fluid=fluid,
        below_vapor=["AF1:port_1"],
        record_vapor=True,
    )


def assigned_flow_check_valve() -> ReferenceCase:
    """R1 (H 10 m) → L1 (102.3 mm, 30 m; sharp entrance) → CV1 (swing check, 5 kPa cracking
    pressure, Crane default K) → L2 (102.3 mm, 60 m; two elbows) → AF1, a 15 L/s demand.

    The check valve passes the demand forwards, so it is open (design §5.2: Q > 0 and
    EGL_in − EGL_out = h_c + K Q²/(2gA²) ≥ h_c, the K term clearing STATE_MARGIN); its drop is
    that law at Q_a, h_c = 5000/(ρg), K = K_swing_check_valve_Crane(D_in)."""
    fluid, rho, _, nu = _fluid_a()
    cv1 = check_valve("CV1", 1.0, "check", cracking_pressure=5000.0)
    chain = DeadEnd(
        8.0,
        2.0,
        [
            Line(0.1023, 30.0, (("entrance_sharp", 1),)),
            Line(0.1023, 60.0, (("elbow_90_lr", 2),)),
        ],
        [cv1],
        assigned_flow("AF1", 0.0, 0.015),
    )
    d_in = chain.lines[0].d
    k = el.valve_k("check", None, d_in)
    drop = cv1.cracking_pressure / (rho * dv.G) + el.valve_loss(k, chain.q, d_in)
    egl = chain.egl(nu, [-drop])
    problem = el.valve_state_problem(
        cv1, "open", chain.q, egl["CV1:inlet"], egl["CV1:outlet"], rho, MARGIN
    )
    if problem:
        raise ValueError(f"CV1 {problem}")
    return dead_end_case(
        name="assigned_flow_check_valve",
        title="Assigned demand through a check valve",
        description=(
            "A 15 L/s demand fed through a swing check valve with a 5 kPa cracking pressure: "
            "verifies that the forced forward flow holds the valve open and the open law "
            "h_c + K v^2/2g at the demand's flow."
        ),
        method=(
            DEAD_END_METHOD + "; h_c = p_crack/(rho g); K from fluids "
            "K_swing_check_valve_Crane (angled)"
        ),
        chain=chain,
        fluid=fluid,
        rises=[-drop],
        valves={"CV1": {"state": "open"}},
    )


def assigned_flow_fcv_open() -> ReferenceCase:
    """The check-valve line with an FCV set to 20 L/s (ideal, K = 0 open) in place of the check
    valve, feeding AF1, a 12 L/s demand.

    The demand fixes the flow below the setpoint, so the FCV cannot be active (Q = Q_set) and
    is open, passing Q_a fully open with no loss (its OPEN rule holds while Q < Q_set and the
    head across it is not reversed): EGL_out = EGL_in. CONTROL_VALVE_SETPOINT_NOT_MET (info)."""
    fluid, rho, _, nu = _fluid_a()
    fcv1 = control_valve("FCV1", 1.0, "fcv", 0.02)
    chain = DeadEnd(
        8.0,
        2.0,
        [
            Line(0.1023, 30.0, (("entrance_sharp", 1),)),
            Line(0.1023, 60.0, (("elbow_90_lr", 2),)),
        ],
        [fcv1],
        assigned_flow("AF1", 0.0, 0.012),
    )
    egl = chain.egl(nu, [0.0])
    d = chain.lines[0].d
    problem = el.valve_state_problem(
        fcv1, "open", chain.q, egl["FCV1:inlet"], egl["FCV1:outlet"], rho, MARGIN, d, d
    )
    if problem:
        raise ValueError(f"FCV1 {problem}")
    if not fcv1.setpoint - chain.q > el.QTOL:
        raise ValueError("the demand must lie clearly below the FCV setpoint")
    return dead_end_case(
        name="assigned_flow_fcv_open",
        title="Assigned demand through an FCV with a larger setpoint",
        description=(
            "A 12 L/s demand fed only through an FCV set to 20 L/s: verifies that the demand "
            "fixes the flow, so the FCV stays fully open below its setpoint (ideal, no loss) "
            "with the CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        method=DEAD_END_METHOD + "; FCV open (ideal, K = 0) at Q_a < Q_set",
        chain=chain,
        fluid=fluid,
        rises=[0.0],
        valves={"FCV1": {"state": "open"}},
        flags=[{"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": "FCV1"}],
    )


PUMP_DISCHARGE = Line(0.1023, 150.0, (("gate_valve", 1), ("elbow_90_lr", 4)))
"""The discharge line of the fixed-speed pump case (test input)."""


def assigned_flow_pump_feeding_demand() -> ReferenceCase:
    """Water at 20 °C: R1 (H 3 m) → SUCTION_A → PU1 (curve_a, rated speed, z 0.5 m) →
    L2 (102.3 mm, 150 m; gate valve, four elbows) → AF1, a 25 L/s demand at z 12 m.

    The demand fixes the pump's flow, so its operating point is on its curve at Q_a, with no
    system curve to intersect: H_s = H_R1 − h_s(Q_a), H_d = H_s + H₀(Q_a) (PCHIP),
    H_AF = H_d − h_L2(Q_a). The pump runs (H₀(Q_a) below its shutoff head by more than
    STATE_MARGIN). NPSHa = (H_s − z_s) + (p_atm − p_vap)/(ρg), NPSHr = NPSHr₀(Q_a), margin =
    NPSHa − NPSHr (TSD §5.5), p_atm = ATMOSPHERE_1976(0).P."""
    fluid = builtin_water(293.15)
    rho, mu, p_vap = dv.fluid_state(fluid)
    assert p_vap is not None
    nu = mu / rho
    curve = curve_a()
    pu1 = pump("PU1", 0.5, curve.id)
    chain = DeadEnd(0.0, 3.0, [SUCTION_A, PUMP_DISCHARGE], [pu1], assigned_flow("AF1", 12.0, 0.025))
    q = chain.q
    head = el.pump_head(curve, pu1.speed, q)
    egl = chain.egl(nu, [head])
    problem = el.pump_state_problem("on", curve, pu1.speed, "running", q, head, MARGIN)
    if problem or not el.pump_in_curve_range(curve, pu1.speed, q):
        raise ValueError(f"PU1 {problem or 'is outside its curve'}")
    npsha = (egl["PU1:suction"] - pu1.elevation) + (SITE_ATMOSPHERE - p_vap) / (rho * dv.G)
    npshr = el.npsh_required(curve, pu1.speed, q)
    return dead_end_case(
        name="assigned_flow_pump_feeding_demand",
        title="Pump feeding an assigned demand",
        description=(
            "A fixed-speed pump whose only outlet is a 25 L/s assigned demand, in water at "
            "20 C: verifies that the demand sets the pump's flow and its head is read from the "
            "PCHIP curve at that flow, the node's EGL downstream, and NPSH available, required "
            "and margin."
        ),
        method=(
            DEAD_END_METHOD + "; pump at Q_a on the scipy PchipInterpolator curve; CoolProp "
            "water (IAPWS-95) properties and saturation pressure; fluids ATMOSPHERE_1976(0).P"
        ),
        chain=chain,
        fluid=fluid,
        rises=[head],
        pumps={
            "PU1": {
                "status": "running",
                "operatingFlow": q,
                "operatingHead": head,
                "npshAvailable": npsha,
                "npshRequired": npshr,
                "npshMargin": npsha - npshr,
            }
        },
        pump_library=[curve],
        record_vapor=True,
    )


FLOW_PUMP_DISCHARGE = Line(0.1023, 60.0, (("gate_valve", 1), ("elbow_90_lr", 2)))
"""The discharge line of the flow-controlled pump cases (test input)."""


def _flow_pump_case(
    name: str,
    title: str,
    description: str,
    q_a: float,
    q_set: float,
    s_min: float,
    s_max: float,
    state: el.ControlState,
) -> ReferenceCase:
    """R1 (H 3 m) → SUCTION_A → PU1 (curve_a, flow-controlled: Q_set, s ∈ [s_min, s_max],
    z 0.5 m) → FLOW_PUMP_DISCHARGE → AF1 (demand q_a, z 5 m). The demand fixes the pump's flow
    at Q_a ≠ Q_set, so the pump runs at the limit speed s of ``state`` on the fixed-speed law
    F(s, Q_a) = s² H₀(Q_a/s) (D11 "Limits"; guarded by ``element_laws``' rules with
    STATE_MARGIN)."""
    fluid, *_ = _fluid_a()
    curve = curve_a()
    control = flow_control(q_set, s_min)
    pu1 = pump("PU1", 0.5, curve.id, speed=s_max, control=control)
    chain = DeadEnd(
        0.0, 3.0, [SUCTION_A, FLOW_PUMP_DISCHARGE], [pu1], assigned_flow("AF1", 5.0, q_a)
    )
    speed = el.control_state_speed(control, s_max, state)
    assert speed is not None
    head = el.pump_head(curve, speed, q_a)
    require_state(curve, control, s_max, state, q_a, head)
    return dead_end_case(
        name=name,
        title=title,
        description=description,
        method=(
            DEAD_END_METHOD + "; flow-controlled pump (D11) at its limit speed s: "
            "rise s^2 H0(Q_a/s) on the scipy PchipInterpolator curve"
        ),
        chain=chain,
        fluid=fluid,
        rises=[head],
        pumps={"PU1": pump_expected(state, q_a, head, speed)},
        flags=control_flags("PU1", curve, control, state, q_a, speed, None),
        pump_library=[curve],
    )


def assigned_flow_flow_pump_max_speed() -> ReferenceCase:
    """A flow-controlled pump (Q_set 20 L/s, s ∈ [0.5, 0.9]) whose only outlet is a 12 L/s
    demand: Q_a < Q_set, so the pump runs at its maximum speed 0.9 (rule X1 keeps it there:
    the flow never reaches the setpoint), rise F(0.9, Q_a)."""
    return _flow_pump_case(
        "assigned_flow_flow_pump_max_speed",
        "Flow-controlled pump feeding a smaller demand",
        "A flow-controlled pump set to 20 L/s whose only outlet is a 12 L/s assigned demand: "
        "verifies that the demand fixes the flow, so the pump runs at its maximum speed below "
        "its setpoint (PUMP_SETPOINT_NOT_MET) rather than the solve failing.",
        0.012,
        0.02,
        0.5,
        0.9,
        "max_speed",
    )


def assigned_flow_flow_pump_min_speed() -> ReferenceCase:
    """A flow-controlled pump (Q_set 8 L/s, s ∈ [0.6, 1]) whose only outlet is a 16 L/s
    demand: Q_a > Q_set, so the pump runs at its minimum speed 0.6 (rule N1 keeps it there:
    the flow stays above the setpoint), rise F(0.6, Q_a)."""
    return _flow_pump_case(
        "assigned_flow_flow_pump_min_speed",
        "Flow-controlled pump feeding a larger demand",
        "A flow-controlled pump set to 8 L/s whose only outlet is a 16 L/s assigned demand: "
        "verifies that the demand fixes the flow, so the pump runs at its minimum speed above "
        "its setpoint (PUMP_SETPOINT_NOT_MET) rather than the solve failing.",
        0.016,
        0.008,
        0.6,
        1.0,
        "min_speed",
    )


# --- Cases: demands between reservoirs and at a tee -----------------------------------------------


@dataclass(frozen=True)
class MidLine:
    """R1 → L1 → T1:run_inlet; T1:run_outlet → L2 → R2; T1:branch → L3 → AF1."""

    z1: float
    level1: float
    z2: float
    level2: float
    l1: Line
    l2: Line
    l3: Line
    z_tee: float
    af: AssignedFlow
    crane: bool
    flags: list[dict[str, str]] = field(default_factory=list)

    def project_parts(self) -> tuple[list[Component], list[PipeConnection]]:
        tee = crane_tee("T1", self.z_tee) if self.crane else ideal_tee("T1", self.z_tee)
        return (
            [
                reservoir("R1", self.z1, self.level1),
                tee,
                reservoir("R2", self.z2, self.level2),
                self.af,
            ],
            [
                self.l1.connect("L1", "R1:port_1", "T1:run_inlet"),
                self.l2.connect("L2", "T1:run_outlet", "R2:port_1"),
                self.l3.connect("L3", "T1:branch", f"{self.af.id}:port_1"),
            ],
        )


def mid_line_case(
    *, name: str, title: str, description: str, method: str, net: MidLine, q1: float, nu: float
) -> ReferenceCase:
    """Expected values of a MidLine from the flow q1 in L1: L2 carries q1 − Q_a, L3 Q_a; the
    tee's port EGLs E + offset_p (ideal: 0; Crane: ``element_laws.branch_losses``), E =
    H_R1 − h_L1(q1); H_AF = EGL(branch) − h_L3(Q_a). The closure EGL(run_outlet) −
    h_L2(q1 − Q_a) = H_R2 is checked."""
    fluid, rho, mu, _ = _fluid_a()
    q_a = net.af.flow
    q2 = q1 - q_a
    flows_in = {"run_inlet": q1, "run_outlet": -q2, "branch": -q_a}
    offsets = _tee_offsets(net, flows_in, nu)
    e = net.z1 + net.level1 - net.l1.head_loss(q1, nu)
    tee = {p: e + offsets[p] for p in flows_in}
    h_af = tee["branch"] - net.l3.head_loss(q_a, nu)
    h2 = net.z2 + net.level2
    if abs(tee["run_outlet"] - net.l2.head_loss(q2, nu) - h2) > 1.0e-9:
        raise RuntimeError("the mid-line energy equation does not close")
    require_turbulent(nu, [(q1, net.l1), (q2, net.l2), (q_a, net.l3)])
    egl = {
        "R1:port_1": net.z1 + net.level1,
        **{f"T1:{p}": h for p, h in tee.items()},
        "R2:port_1": h2,
        f"{net.af.id}:port_1": h_af,
    }
    pressures = {
        "T1:run_inlet": dv.static_pressure(rho, tee["run_inlet"], net.z_tee, net.l1.velocity(q1)),
        "T1:run_outlet": dv.static_pressure(rho, tee["run_outlet"], net.z_tee, net.l2.velocity(q2)),
        "T1:branch": dv.static_pressure(rho, tee["branch"], net.z_tee, net.l3.velocity(q_a)),
        f"{net.af.id}:port_1": dv.static_pressure(
            rho, h_af, net.af.elevation, net.l3.velocity(q_a)
        ),
    }
    require_no_vapor_flag(pressures, rho, None)
    components, connections = net.project_parts()
    project = make_project(f"ref-{name.replace('_', '-')}", title, fluid, components, connections)
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q1, "L2": q2, "L3": q_a},
        egl=egl,
        pressures=pressures,
        flags=net.flags,
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=expected,
    )


def _tee_offsets(net: MidLine, flows_in: dict[str, float], nu: float) -> dict[str, float]:
    if not net.crane:
        return dict.fromkeys(flows_in, 0.0)
    diameters = {"run_inlet": net.l1.d, "run_outlet": net.l2.d, "branch": net.l3.d}
    return el.branch_losses("tee", 90.0, flows_in, diameters, nu).offsets


def assigned_flow_mid_line_crane_tee() -> ReferenceCase:
    """R1 (H 20 m) → L1 (102.3 mm, 40 m; sharp entrance) → Crane tee T1 (run) → L2 (102.3 mm,
    60 m; exit) → R2 (H 5 m), with a 9 L/s demand AF1 on the tee's branch through L3 (77.9 mm,
    25 m; two elbows).

    One unknown, the flow q1 from R1 (brentq): the tee diverges from its run inlet, q = Q_a/q1
    in the branch, and
        H_R1 − h_L1(q1) − K_run(q) v_c²/(2g) − h_L2(q1 − Q_a) = H_R2,   v_c = q1/A_run,
    with K_run, K_branch from fluids K_run_diverging_Crane / K_branch_diverging_Crane at the
    solved split (``element_laws.branch_losses``); H_AF = E − K_branch v_c²/(2g) − h_L3(Q_a).
    Guards: the pattern, the split clear of the Crane steps by STEP_MARGIN."""
    *_, nu = _fluid_a()
    net = MidLine(
        15.0,
        5.0,
        0.0,
        5.0,
        Line(0.1023, 40.0, (("entrance_sharp", 1),)),
        Line(0.1023, 60.0, (("exit", 1),)),
        Line(0.0779, 25.0, (("elbow_90_lr", 2),)),
        2.0,
        assigned_flow("AF1", 3.0, 0.009),
        crane=True,
    )
    q_a = net.af.flow
    h1, h2 = net.z1 + net.level1, net.z2 + net.level2

    def residual(q1: float) -> float:
        flows_in = {"run_inlet": q1, "run_outlet": -(q1 - q_a), "branch": -q_a}
        offsets = _tee_offsets(net, flows_in, nu)
        return (
            h1
            - net.l1.head_loss(q1, nu)
            + offsets["run_outlet"]
            - net.l2.head_loss(q1 - q_a, nu)
            - h2
        )

    q1 = float(brentq(residual, q_a * (1.0 + 1.0e-6), 1.0, xtol=1.0e-18, rtol=1.0e-15))
    flows_in = {"run_inlet": q1, "run_outlet": -(q1 - q_a), "branch": -q_a}
    losses = el.branch_losses(
        "tee",
        90.0,
        flows_in,
        {"run_inlet": net.l1.d, "run_outlet": net.l2.d, "branch": net.l3.d},
        nu,
    )
    if losses.pattern != "diverging from run_inlet":
        raise ValueError(f"unexpected tee pattern {losses.pattern}")
    if el.crane_step_distance(el.q_ratio(losses, flows_in, "tee")) < STEP_MARGIN:
        raise ValueError("the split is too close to a Crane step")
    return mid_line_case(
        name="assigned_flow_mid_line_crane_tee",
        title="Assigned demand on a Crane tee's branch",
        description=(
            "A 9 L/s demand drawn from the branch of a Crane tee on a line between two "
            "reservoirs: verifies a demand mid-line (continuity at the tee with the demand on "
            "its branch), the diverging Crane K at the split the demand sets, and the "
            "node's EGL and pressure."
        ),
        method=(
            AF_METHOD + "; Darcy-Weisbach + Colebrook lines; path K from fluids "
            "K_branch_diverging_Crane and K_run_diverging_Crane at angle 90 on the "
            "combined-flow velocity; brentq on the flow from R1"
        ),
        net=net,
        q1=q1,
        nu=nu,
    )


def assigned_flow_fed_from_both_ends() -> ReferenceCase:
    """R1 (H 8 m) → L1 (102.3 mm, 120 m; sharp entrance) → ideal tee T1 ← L2 (77.9 mm, 90 m;
    one elbow; drawn T1 → R2) ← R2 (H 5.5 m), with a 24 L/s demand AF1 on the branch through
    L3 (102.3 mm, 15 m).

    The demand exceeds what R1 alone can pass with T1 at H_R2, so both reservoirs feed it and
    L2 runs against its drawn direction. One unknown, the flow q1 from R1 (brentq), the tee's
    one EGL E (ideal) shared:
        E = H_R1 − h_L1(q1) = H_R2 − h_L2(Q_a − q1),   L2 carries −(Q_a − q1),
    H_AF = E − h_L3(Q_a)."""
    *_, nu = _fluid_a()
    net = MidLine(
        6.0,
        2.0,
        4.0,
        1.5,
        Line(0.1023, 120.0, (("entrance_sharp", 1),)),
        Line(0.0779, 90.0, (("elbow_90_lr", 1),)),
        Line(0.1023, 15.0),
        1.0,
        assigned_flow("AF1", 0.5, 0.024),
        crane=False,
    )
    q_a = net.af.flow
    h1, h2 = net.z1 + net.level1, net.z2 + net.level2

    def residual(q1: float) -> float:
        return (h1 - net.l1.head_loss(q1, nu)) - (h2 - net.l2.head_loss(q_a - q1, nu))

    if not residual(q_a) < -MARGIN:
        raise ValueError("R1 alone must not be able to supply the demand")
    q1 = float(brentq(residual, 0.0, q_a, xtol=1.0e-18, rtol=1.0e-15))
    return mid_line_case(
        name="assigned_flow_fed_from_both_ends",
        title="Assigned demand fed from two reservoirs",
        description=(
            "A 24 L/s demand on an ideal tee between two reservoirs, larger than the upper "
            "reservoir alone can pass: verifies continuity with the demand fed from both "
            "sides, a reversed connection flow and the shared junction EGL."
        ),
        method=AF_METHOD + "; Darcy-Weisbach + Colebrook lines; ideal tee; brentq on the "
        "flow from R1",
        net=net,
        q1=q1,
        nu=nu,
    )


def assigned_flow_supply_to_demand() -> ReferenceCase:
    """A 10 L/s supply AF1 (z 1 m) → L1 (77.9 mm, 40 m; two elbows) → ideal tee T1 (z 0.5 m)
    → L2 (77.9 mm, 60 m; gate valve) → a 10 L/s demand AF2 (z 0 m), with R1 (H 4 m) on the
    tee's branch through L3 (52.5 mm, 5 m) as the only fixed head.

    The two assigned flows cancel, so the reservoir passes nothing: L3 carries 0 (continuity at
    T1), E = H_R1, and both nodes follow in closed form, H_AF1 = E + h_L1(Q), H_AF2 =
    E − h_L2(Q), Q = 0.010 m³/s. The reservoir only sets the pressure level (the
    pressurization point of PRD §2.1)."""
    fluid, rho, mu, nu = _fluid_a()
    q = 0.010
    l1 = Line(0.0779, 40.0, (("elbow_90_lr", 2),))
    l2 = Line(0.0779, 60.0, (("gate_valve", 1),))
    l3 = Line(0.0525, 5.0)
    z_r, level_r, z_tee, z_s, z_d = 0.0, 4.0, 0.5, 1.0, 0.0
    e = z_r + level_r
    require_turbulent(nu, [(q, l1), (q, l2)])
    egl = {
        "AF1:port_1": e + l1.head_loss(q, nu),
        "T1:run_inlet": e,
        "T1:run_outlet": e,
        "T1:branch": e,
        "AF2:port_1": e - l2.head_loss(q, nu),
        "R1:port_1": e,
    }
    pressures = {
        "AF1:port_1": dv.static_pressure(rho, egl["AF1:port_1"], z_s, l1.velocity(q)),
        "T1:run_inlet": dv.static_pressure(rho, e, z_tee, l1.velocity(q)),
        "T1:run_outlet": dv.static_pressure(rho, e, z_tee, l2.velocity(q)),
        "T1:branch": dv.static_pressure(rho, e, z_tee, 0.0),
        "AF2:port_1": dv.static_pressure(rho, egl["AF2:port_1"], z_d, l2.velocity(q)),
    }
    require_no_vapor_flag(pressures, rho, None)
    project = make_project(
        "ref-assigned-flow-supply-to-demand",
        "Assigned supply to an equal demand",
        fluid,
        [
            assigned_flow("AF1", z_s, -q),
            ideal_tee("T1", z_tee),
            assigned_flow("AF2", z_d, q),
            reservoir("R1", z_r, level_r),
        ],
        [
            l1.connect("L1", "AF1:port_1", "T1:run_inlet"),
            l2.connect("L2", "T1:run_outlet", "AF2:port_1"),
            l3.connect("L3", "R1:port_1", "T1:branch"),
        ],
    )
    return ReferenceCase(
        name="assigned_flow_supply_to_demand",
        description=(
            "A 10 L/s supply feeding an equal demand through a tee whose branch is the only "
            "connection to a reservoir: verifies that equal assigned flows pass between "
            "themselves while the reservoir passes nothing and only sets the pressure level."
        ),
        source=_source(
            "assigned_flow_supply_to_demand",
            AF_METHOD + "; continuity at T1 leaves R1's pipe at zero flow, E = H_R1; "
            "Darcy-Weisbach + Colebrook, no iteration",
        ),
        project=project,
        expected=Expected(
            density=rho,
            dynamic_viscosity=mu,
            flows={"L1": q, "L2": q, "L3": 0.0},
            egl=egl,
            pressures=pressures,
        ),
    )


def assigned_flow_zero_as_plug() -> ReferenceCase:
    """``series_tee_plugged_branch`` with its plug P1 replaced by an assigned-flow node AF1 of
    flow 0 at the same elevation (TSD §4.8: "flow = 0 behaves exactly as a plug").

    The expected values are that case's, derived there (series flow through the tee, the dead
    branch at the tee's EGL with no flow), with P1's port renamed AF1's: the zero-flow node's
    pipe carries nothing, so its port sits at the tee's EGL with v = 0."""
    plug_case = dv.series_tee_plugged_branch()
    project = plug_case.project
    [plug] = [c for c in project.components if isinstance(c, Plug)]
    af = assigned_flow("AF1", plug.elevation, 0.0, plug.ports[0].nominal_size)

    def rename(key: str) -> str:
        return key.replace(f"{plug.id}:", f"{af.id}:")

    components = [af if c.id == plug.id else c for c in project.components]
    connections = [
        c.model_copy(update={"to_component_id": af.id}) if c.to_component_id == plug.id else c
        for c in project.connections
    ]
    expected = plug_case.expected
    return ReferenceCase(
        name="assigned_flow_zero_as_plug",
        description=(
            "The plugged-branch case with the plug replaced by an assigned-flow node of zero "
            "flow: verifies that a zero assigned flow behaves exactly as a plug (the same "
            "flows, EGLs and pressures)."
        ),
        source=_source(
            "assigned_flow_zero_as_plug",
            "the expected values of derivations.py::series_tee_plugged_branch (Darcy-Weisbach "
            "+ Colebrook in series; brentq) with the plug's port renamed; a zero assigned flow "
            "is a plug (TSD 4.8)",
        ),
        project=project.model_copy(
            update={
                "id": "ref-assigned-flow-zero-as-plug",
                "metadata": project.metadata.model_copy(
                    update={"name": "Zero assigned flow on a tee's branch"}
                ),
                "components": components,
                "connections": connections,
            }
        ),
        expected=replace(
            expected,
            egl={rename(k): v for k, v in expected.egl.items()},
            pressures={rename(k): v for k, v in expected.pressures.items()},
        ),
    )


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    assigned_flow_demand_dead_end,
    assigned_flow_supply_dead_end,
    assigned_flow_below_vapor_pressure,
    assigned_flow_check_valve,
    assigned_flow_fcv_open,
    assigned_flow_pump_feeding_demand,
    assigned_flow_flow_pump_max_speed,
    assigned_flow_flow_pump_min_speed,
    assigned_flow_mid_line_crane_tee,
    assigned_flow_fed_from_both_ends,
    assigned_flow_supply_to_demand,
    assigned_flow_zero_as_plug,
)
