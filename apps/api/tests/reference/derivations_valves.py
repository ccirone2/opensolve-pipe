"""Closed-form expected results for valve cases (design §2.3, §5.2, §5.3, §12).

Valve laws (written out in ``element_laws``), with v_ref the velocity in the pipe on the valve's
inlet port, the valve's reference diameter:

- open isolation or check valve: EGL_in − EGL_out = h_c + K v_ref|v_ref|/(2g), h_c =
  crackingPressure/(ρg) for a check valve (0 otherwise); K the Crane TP-410 default, a K as
  entered, or K from Cv (US gpm at 1 psi) or Kv (m³/h at 1 bar) by definition;
- closed (isolated, locked closed, or closed by the status rules): Q = 0;
- PRV active: EGL_out = z + p_set/(ρg) + v_out²/(2g) (the outlet *static* pressure is p_set);
  PSV active: EGL_in = z + p_set/(ρg) + v_in²/(2g); FCV active: Q = q_set;
- control valve open: the fully open law (ideal K = 0 by default).

Each case solves its series line for the state it is named for, then a guard checks that state
against the status rules of design §5.2/§5.3 (EPANET 2.2 hydstatus.c rules in EGL form) with a
clear margin, so the expected state is the one the rules select. Our FCV closes on reverse head
(design §12, "closed (reverse)"); EPANET's would pass reverse flow as XFCV.

Every pipe, elevation, setpoint and flow coefficient is a test input. Independence: nothing here
imports ``opensolve_pipe.services``.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from opensolve_pipe.models.components import (
    CheckValve,
    Component,
    ControlValve,
    IsolationValve,
)
from opensolve_pipe.models.fluids import CustomFluid
from opensolve_pipe.models.piping import PipeConnection
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    check_valve,
    control_valve,
    custom_fluid,
    flow_coefficient,
    ideal_tee,
    isolation_valve,
    make_project,
    reservoir,
)
from tests.reference.derivations_pumps import solve_decreasing
from tests.reference.line import Line, require_turbulent

Valve = IsolationValve | CheckValve | ControlValve
ValveState = Literal["open", "closed", "active"]

STATE_MARGIN = el.STATE_MARGIN


def _source(name: str, method: str) -> str:
    return dv.source(name, method, "derivations_valves")


def _fluid_a() -> tuple[CustomFluid, float, float, float]:
    name, rho, mu = dv.FLUID_A
    return custom_fluid(name, rho, mu), rho, mu, mu / rho


def cracking_head(valve: Valve, rho: float) -> float:
    """h_c = crackingPressure/(ρg) for an active check valve, 0 for any other valve and for a
    locked check valve, whose disc is held (design §5.2: locked_open is always open, "no check
    action")."""
    if isinstance(valve, CheckValve) and valve.status == "active":
        return valve.cracking_pressure / (rho * dv.G)
    return 0.0


def open_valve_loss(valve: Valve, q: float, d_in: float, rho: float) -> float:
    """EGL drop of a fully open valve: h_c + K Q|Q|/(2gA²) at the inlet pipe diameter."""
    k = el.valve_k(valve.valve_type, valve.resistance, d_in)
    return cracking_head(valve, rho) + el.valve_loss(k, q, d_in)


@dataclass(frozen=True)
class Chain:
    """R1 → line 0 → valve 0 → line 1 → valve 1 → … → line n → R2 (all connections L1…)."""

    z1: float
    level1: float
    z2: float
    level2: float
    lines: Sequence[Line]
    valves: Sequence[Valve]

    def __post_init__(self) -> None:
        if len(self.lines) != len(self.valves) + 1:
            raise ValueError("a chain alternates lines and valves, starting and ending on a line")

    @property
    def h1(self) -> float:
        return self.z1 + self.level1

    @property
    def h2(self) -> float:
        return self.z2 + self.level2

    def connections(self) -> list[PipeConnection]:
        ports = ["R1:port_1"]
        for v in self.valves:
            ports += [f"{v.id}:inlet", f"{v.id}:outlet"]
        ports.append("R2:port_1")
        return [
            line.connect(f"L{i + 1}", ports[2 * i], ports[2 * i + 1])
            for i, line in enumerate(self.lines)
        ]

    def components(self) -> list[Component]:
        return [
            reservoir("R1", self.z1, self.level1),
            *self.valves,
            reservoir("R2", self.z2, self.level2),
        ]


def chain_egl(
    chain: Chain, q: float, nu: float, rho: float, valve_drops: Sequence[float]
) -> dict[str, float]:
    """EGL at every port, stepping from R1 with each line's loss and each valve's drop; the
    last step must land on H_R2 (closure checked)."""
    egl = {"R1:port_1": chain.h1}
    e = chain.h1
    for i, line in enumerate(chain.lines):
        e -= line.head_loss(q, nu)
        if i < len(chain.valves):
            v = chain.valves[i]
            egl[f"{v.id}:inlet"] = e
            e -= valve_drops[i]
            egl[f"{v.id}:outlet"] = e
    if abs(e - chain.h2) > 1.0e-9:
        raise RuntimeError(f"chain EGL does not close: {e} vs {chain.h2}")
    egl["R2:port_1"] = chain.h2
    return egl


def chain_pressures(chain: Chain, q: float, rho: float, egl: dict[str, float]) -> dict[str, float]:
    """Static pressure at every valve port: v in the line on that port (design §1.1)."""
    out = {}
    for i, v in enumerate(chain.valves):
        before, after = chain.lines[i], chain.lines[i + 1]
        out[f"{v.id}:inlet"] = dv.static_pressure(
            rho, egl[f"{v.id}:inlet"], v.elevation, before.velocity(q)
        )
        out[f"{v.id}:outlet"] = dv.static_pressure(
            rho, egl[f"{v.id}:outlet"], v.elevation, after.velocity(q)
        )
    return out


def chain_case(
    *,
    name: str,
    title: str,
    description: str,
    method: str,
    chain: Chain,
    states: dict[str, ValveState],
    flags: Sequence[dict[str, str]] = (),
) -> ReferenceCase:
    """A chain of isolation and check valves, each open or closed as given.

    Open everywhere: one flow through the series,
        H_R1 − H_R2 = Σ h_line(Q) + Σ (h_c + K v_ref²/(2g))   (brentq);
    any valve closed: Q = 0 and every port takes the EGL of the reservoir on its side.
    Guard: the derived flow and port EGLs satisfy each valve's status rule (design §5.2).
    """
    fluid, rho, mu, nu = _fluid_a()
    d_in = [chain.lines[i].d for i in range(len(chain.valves))]
    if all(states[v.id] == "open" for v in chain.valves):

        def residual(q: float) -> float:
            return (
                chain.h1
                - chain.h2
                - sum(line.head_loss(q, nu) for line in chain.lines)
                - sum(
                    open_valve_loss(v, q, d, rho) for v, d in zip(chain.valves, d_in, strict=True)
                )
            )

        q = solve_decreasing(residual)
        require_turbulent(nu, [(q, line) for line in chain.lines])
        drops = [open_valve_loss(v, q, d, rho) for v, d in zip(chain.valves, d_in, strict=True)]
        egl = chain_egl(chain, q, nu, rho, drops)
    else:
        q = 0.0
        closed = [i for i, v in enumerate(chain.valves) if states[v.id] == "closed"]
        if len(closed) != 1:
            raise ValueError("chain_case supports one closed valve")
        drops = [0.0] * len(chain.valves)
        drops[closed[0]] = chain.h1 - chain.h2
        egl = chain_egl(chain, q, nu, rho, drops)
    for v in chain.valves:
        problem = el.valve_state_problem(
            v, states[v.id], q, egl[f"{v.id}:inlet"], egl[f"{v.id}:outlet"], rho, STATE_MARGIN
        )
        if problem:
            raise ValueError(f"{name}: {v.id} {problem}")

    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        fluid,
        chain.components(),
        chain.connections(),
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={f"L{i + 1}": q for i in range(len(chain.lines))},
        egl=egl,
        pressures=chain_pressures(chain, q, rho, egl),
        valves={v.id: {"state": states[v.id]} for v in chain.valves},
        flags=list(flags),
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=expected,
    )


# --- Isolation valves ---------------------------------------------------------------------------


def isolation_valves_crane_default_k() -> ReferenceCase:
    """Gate, globe, butterfly and ball valves in series, each with no resistance given.

    K is the Crane TP-410 full-bore default at each valve's inlet-pipe diameter (design §2.3):
    K_gate_valve_Crane(D, D, 0), K_globe_valve_Crane(D, D), K_butterfly_valve_Crane(D, style=0),
    K_ball_valve_Crane(D, D, 0). The globe valve sits between a 77.9 mm inlet pipe and a
    102.3 mm outlet pipe, so its K and v_ref are on 77.9 mm (and the gate valve, between 102.3 and
    77.9 mm, references 102.3 mm).
    """
    lines = [
        Line(0.1023, 30.0, (("entrance_sharp", 1),)),
        Line(0.0779, 25.0),
        Line(0.1023, 20.0),
        Line(0.1023, 20.0),
        Line(0.1023, 40.0, (("exit", 1),)),
    ]
    valves: list[Valve] = [
        isolation_valve("GV1", 4.0, "gate"),
        isolation_valve("GL1", 3.5, "globe"),
        isolation_valve("BF1", 3.0, "butterfly"),
        isolation_valve("BV1", 2.5, "ball"),
    ]
    return chain_case(
        name="isolation_valves_crane_default_k",
        title="Isolation valves with Crane default K",
        description=(
            "Gate, globe, butterfly and ball isolation valves in series with no resistance "
            "entered: verifies each type's Crane TP-410 full-bore K (fluids), the valve law "
            "K v^2/2g referenced to the inlet pipe, and port pressures where inlet and outlet "
            "pipes differ in size."
        ),
        method=(
            "Darcy-Weisbach + Colebrook lines; valve K from fluids K_gate_valve_Crane, "
            "K_globe_valve_Crane, K_butterfly_valve_Crane(style 0), K_ball_valve_Crane at the "
            "inlet pipe diameter; brentq"
        ),
        chain=Chain(9.0, 3.0, 0.0, 1.0, lines, valves),
        states=dict.fromkeys(("GV1", "GL1", "BF1", "BV1"), "open"),
    )


def isolation_valve_cv() -> ReferenceCase:
    """One globe valve with a user Cv = 110 (US gpm at 1 psi) on a 77.9 mm line.

    K from the Cv definition (design §12): Q_ref = 110 gal/min of reference water passes at
    ΔP_ref = 1 psi, so K = 2 ΔP_ref A²/(ρ_ref Q_ref²), ρ_ref = CoolProp IAPWS-95 water at 60 °F,
    703572 Pa (the conditions fluids.fittings.Kv_to_K documents).
    """
    lines = [
        Line(0.0779, 40.0, (("entrance_sharp", 1),)),
        Line(0.0779, 60.0, (("elbow_90_lr", 2), ("exit", 1))),
    ]
    valves: list[Valve] = [
        isolation_valve("GL1", 2.0, "globe", resistance=flow_coefficient("Cv", 110.0))
    ]
    return chain_case(
        name="isolation_valve_cv",
        title="Globe valve with a Cv",
        description=(
            "A globe valve whose resistance is entered as Cv = 110: verifies the Cv to K "
            "conversion (from the Cv definition and the reference water density) at the inlet "
            "pipe diameter."
        ),
        method=(
            "Darcy-Weisbach + Colebrook lines; K = 2 dP A^2/(rho Q^2) from the Cv definition "
            "(1 US gpm at 1 psi, scipy.constants; rho = CoolProp water at 60 F, 703572 Pa); "
            "brentq"
        ),
        chain=Chain(10.0, 2.0, 0.0, 1.5, lines, valves),
        states={"GL1": "open"},
    )


def isolation_valves_kv_and_k() -> ReferenceCase:
    """A butterfly valve with Kv = 320 (m³/h at 1 bar) and a ball valve with K = 0.35 as
    entered, in series on 102.3 mm lines. Kv → K by definition, like Cv (isolation_valve_cv)."""
    lines = [
        Line(0.1023, 35.0, (("entrance_sharp", 1),)),
        Line(0.1023, 15.0),
        Line(0.1023, 50.0, (("exit", 1),)),
    ]
    valves: list[Valve] = [
        isolation_valve("BF1", 1.0, "butterfly", resistance=flow_coefficient("Kv", 320.0)),
        isolation_valve("BV1", 1.0, "ball", resistance=flow_coefficient("K", 0.35)),
    ]
    return chain_case(
        name="isolation_valves_kv_and_k",
        title="Isolation valves with Kv and K",
        description=(
            "A butterfly valve with Kv = 320 and a ball valve with K = 0.35 entered by the "
            "user: verifies the Kv to K conversion (from the Kv definition) and a K used as "
            "entered."
        ),
        method=(
            "Darcy-Weisbach + Colebrook lines; K = 2 dP A^2/(rho Q^2) from the Kv definition "
            "(1 m3/h at 1 bar; rho = CoolProp water at 60 F, 703572 Pa); K as entered; brentq"
        ),
        chain=Chain(6.0, 2.0, 0.0, 1.0, lines, valves),
        states={"BF1": "open", "BV1": "open"},
    )


def isolation_valves_isolated_section() -> ReferenceCase:
    """R1 → L1 → T1 → LA → T2 → L4 → R2, with a bypass T1:branch → LB1 → V1 → LB2 → V2 → LB3 →
    T2:branch whose two gate valves are both isolated (closed).

    LB2, between the closed valves, touches no fixed head: an isolated section (design §4): zero
    flow, no EGL at V1:outlet and V2:inlet, flag ISOLATED_SECTION. LB1 and LB3 are dead ends
    (zero flow, the EGL of their tee). The main line is a series flow:
        H_R1 − H_R2 = h_L1(Q) + h_LA(Q) + h_L4(Q)   (brentq), ideal tees (one EGL each).
    """
    fluid, rho, mu, nu = _fluid_a()
    l1 = Line(0.1023, 50.0, (("entrance_sharp", 1),))
    la = Line(0.0779, 80.0)
    l4 = Line(0.1023, 60.0, (("exit", 1),))
    lb = Line(0.0525, 10.0)
    z1, level1, z2, level2 = 8.0, 2.0, 0.0, 1.0
    z_t1, z_t2, z_v = 2.0, 1.5, 1.8
    h1, h2 = z1 + level1, z2 + level2
    q = dv.solve_flow(
        lambda q: l1.head_loss(q, nu) + la.head_loss(q, nu) + l4.head_loss(q, nu), h1 - h2
    )
    require_turbulent(nu, [(q, l1), (q, la), (q, l4)])
    h_t1 = h1 - l1.head_loss(q, nu)
    h_t2 = h2 + l4.head_loss(q, nu)
    project = make_project(
        "ref-isolation-valves-isolated-section",
        "Bypass isolated between two closed valves",
        fluid,
        [
            reservoir("R1", z1, level1),
            ideal_tee("T1", z_t1),
            isolation_valve("V1", z_v, "gate", status="isolated"),
            isolation_valve("V2", z_v, "gate", status="isolated"),
            ideal_tee("T2", z_t2),
            reservoir("R2", z2, level2),
        ],
        [
            l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            la.connect("LA", "T1:run_outlet", "T2:run_inlet"),
            l4.connect("L4", "T2:run_outlet", "R2:port_1"),
            lb.connect("LB1", "T1:branch", "V1:inlet"),
            lb.connect("LB2", "V1:outlet", "V2:inlet"),
            lb.connect("LB3", "V2:outlet", "T2:branch"),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "LA": q, "L4": q, "LB1": 0.0, "LB2": 0.0, "LB3": 0.0},
        egl={
            "R1:port_1": h1,
            "T1:run_inlet": h_t1,
            "T1:run_outlet": h_t1,
            "T1:branch": h_t1,
            "V1:inlet": h_t1,
            "V2:outlet": h_t2,
            "T2:run_inlet": h_t2,
            "T2:branch": h_t2,
            "T2:run_outlet": h_t2,
            "R2:port_1": h2,
        },
        pressures={
            "V1:inlet": dv.static_pressure(rho, h_t1, z_v, 0.0),
            "V2:outlet": dv.static_pressure(rho, h_t2, z_v, 0.0),
            "T1:branch": dv.static_pressure(rho, h_t1, z_t1, 0.0),
            "T2:branch": dv.static_pressure(rho, h_t2, z_t2, 0.0),
        },
        valves={"V1": {"state": "closed"}, "V2": {"state": "closed"}},
        # One flag per isolated section, on the first of its components (by id): V1 and V2.
        flags=[{"code": "ISOLATED_SECTION", "componentId": min("V1", "V2")}],
    )
    return ReferenceCase(
        name="isolation_valves_isolated_section",
        description=(
            "A bypass closed by two isolated gate valves beside a main line: verifies zero flow "
            "through closed valves, dead-end legs at their tee's EGL, the isolated pipe between "
            "the valves (no head, ISOLATED_SECTION) and the main-line flow."
        ),
        source=_source(
            "isolation_valves_isolated_section",
            "Darcy-Weisbach + Colebrook series flow on the main line; brentq",
        ),
        project=project,
        expected=expected,
    )


# --- Check valves -------------------------------------------------------------------------------

CV_LINES = (
    Line(0.1023, 30.0, (("entrance_sharp", 1),)),
    Line(0.1023, 60.0, (("elbow_90_lr", 2), ("exit", 1))),
)


def check_valve_cracking_pressure() -> ReferenceCase:
    """Swing check valve, cracking pressure 7 kPa, forward head 13 m: open.

    Law (design §5.2): EGL_in − EGL_out = h_c + K v²/(2g), h_c = 7000/(ρg), K =
    K_swing_check_valve_Crane(D) (angled, the library default) at the inlet pipe diameter.
    """
    valves: list[Valve] = [check_valve("CV1", 1.0, "check", cracking_pressure=7000.0)]
    return chain_case(
        name="check_valve_cracking_pressure",
        title="Check valve open against its cracking pressure",
        description=(
            "A swing check valve with a 7 kPa cracking pressure in forward flow: verifies the "
            "open check-valve law h_c + K v^2/2g with h_c = cracking pressure/(rho g) and the "
            "Crane swing-check K."
        ),
        method=(
            "Darcy-Weisbach + Colebrook lines; h_c = p_crack/(rho g); K from fluids "
            "K_swing_check_valve_Crane (angled); brentq"
        ),
        chain=Chain(12.0, 3.0, 0.0, 2.0, list(CV_LINES), valves),
        states={"CV1": "open"},
    )


def check_valve_reverse_closed() -> ReferenceCase:
    """The same line with the outlet reservoir 13 m higher: the check valve closes, Q = 0,
    EGL_in = H_R1, EGL_out = H_R2; CHECK_VALVE_CLOSED (info) is expected."""
    valves: list[Valve] = [check_valve("CV1", 1.0, "check", cracking_pressure=7000.0)]
    return chain_case(
        name="check_valve_reverse_closed",
        title="Check valve closed by reverse head",
        description=(
            "A check valve whose outlet side holds the higher head: verifies that it closes "
            "(zero flow, each side at its reservoir's EGL) and the CHECK_VALVE_CLOSED flag."
        ),
        method="check-valve status rule of design 5.2; no flow, so no losses",
        chain=Chain(0.0, 2.0, 12.0, 3.0, list(CV_LINES), valves),
        states={"CV1": "closed"},
        flags=[{"code": "CHECK_VALVE_CLOSED", "componentId": "CV1"}],
    )


def check_valve_below_cracking_pressure() -> ReferenceCase:
    """Forward head 3 m but a 50 kPa cracking pressure (h_c ≈ 5.1 m): the valve stays shut,
    Q = 0 (design §5.2: CLOSED → OPEN only when EGL_in − EGL_out > h_c + htol)."""
    valves: list[Valve] = [check_valve("CV1", 1.0, "check", cracking_pressure=50000.0)]
    return chain_case(
        name="check_valve_below_cracking_pressure",
        title="Check valve below its cracking pressure",
        description=(
            "A check valve with forward head smaller than its cracking head: verifies that it "
            "stays closed with zero flow and the CHECK_VALVE_CLOSED flag."
        ),
        method="check-valve status rule of design 5.2 (forward head < h_c); no flow",
        chain=Chain(3.0, 2.0, 0.0, 2.0, list(CV_LINES), valves),
        states={"CV1": "closed"},
        flags=[{"code": "CHECK_VALVE_CLOSED", "componentId": "CV1"}],
    )


def check_valve_locked_open_reverse() -> ReferenceCase:
    """The check-valve line with R2 13 m above R1 and the valve locked open (its 7 kPa
    cracking pressure entered but not in force): it passes the reverse flow as a plain open
    valve (design §5.2: locked_open is always open, no check action):
        H_R2 − H_R1 = h_L2(Q_r) + K Q_r²/(2gA_in²) + h_L1(Q_r),   Q = −Q_r   (brentq),
    K = K_swing_check_valve_Crane(D) at the inlet pipe's diameter (the law is odd in Q). The
    lines carry only elbows, whose loss does not depend on the flow direction (an entrance or
    exit fitting would describe the forward direction)."""
    fluid, rho, mu, nu = _fluid_a()
    cv1 = check_valve("CV1", 1.0, "check", status="locked_open", cracking_pressure=7000.0)
    lines = [Line(0.1023, 30.0), Line(0.1023, 60.0, (("elbow_90_lr", 2),))]
    chain = Chain(0.0, 2.0, 12.0, 3.0, lines, [cv1])
    d_in = chain.lines[0].d
    k = el.valve_k(cv1.valve_type, cv1.resistance, d_in)
    if cracking_head(cv1, rho) != 0.0:
        raise ValueError("a locked-open check valve has no cracking head")

    def loss(q: float) -> float:
        return sum(line.head_loss(q, nu) for line in chain.lines) + el.valve_loss(k, q, d_in)

    q = -dv.solve_flow(loss, chain.h2 - chain.h1)
    require_turbulent(nu, [(q, line) for line in chain.lines])
    egl = chain_egl(chain, q, nu, rho, [el.valve_loss(k, q, d_in)])
    problem = el.valve_state_problem(
        cv1, "open", q, egl["CV1:inlet"], egl["CV1:outlet"], rho, STATE_MARGIN
    )
    if problem:
        raise ValueError(f"CV1 {problem}")
    project = make_project(
        "ref-check-valve-locked-open-reverse",
        "Check valve locked open, reverse flow",
        fluid,
        chain.components(),
        chain.connections(),
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q},
        egl=egl,
        pressures=chain_pressures(chain, q, rho, egl),
        valves={"CV1": {"state": "open"}},
    )
    return ReferenceCase(
        name="check_valve_locked_open_reverse",
        description=(
            "A swing check valve locked open with the higher head on its outlet side: verifies "
            "that it passes reverse flow as an open valve (K v^2/2g on the inlet pipe, no "
            "cracking head, no check action)."
        ),
        source=_source(
            "check_valve_locked_open_reverse",
            "Darcy-Weisbach + Colebrook lines; K from fluids K_swing_check_valve_Crane "
            "(angled); locked_open: open law without cracking head (design 5.2); brentq",
        ),
        project=project,
        expected=expected,
    )


def stop_check_valves_locked_closed() -> ReferenceCase:
    """R1 → L1 → T1, two parallel legs to T2 → L4 → R2: leg A with an active stop-check valve
    SC1 (forward flow, Crane default K_globe_stop_check_valve_Crane(D, D, style=0)), leg B with
    a stop-check SC2 locked closed. Leg B carries no flow; the series flow is
        H_R1 − H_R2 = h_L1 + h_LA1 + K_SC1 v_LA1²/(2g) + h_LA2 + h_L4   (brentq).
    """
    fluid, rho, mu, nu = _fluid_a()
    l1 = Line(0.1023, 40.0, (("entrance_sharp", 1),))
    la1, la2 = Line(0.0779, 10.0), Line(0.0779, 12.0)
    lb1, lb2 = Line(0.0779, 10.0), Line(0.0779, 12.0)
    l4 = Line(0.1023, 50.0, (("exit", 1),))
    z1, level1, z2, level2 = 10.0, 2.0, 0.0, 1.0
    z_t1, z_t2, z_v = 2.0, 1.0, 1.5
    h1, h2 = z1 + level1, z2 + level2
    sc1 = check_valve("SC1", z_v, "stop_check")
    sc2 = check_valve("SC2", z_v, "stop_check", status="locked_closed")

    def path_loss(q: float) -> float:
        return (
            l1.head_loss(q, nu)
            + la1.head_loss(q, nu)
            + open_valve_loss(sc1, q, la1.d, rho)
            + la2.head_loss(q, nu)
            + l4.head_loss(q, nu)
        )

    q = dv.solve_flow(path_loss, h1 - h2)
    require_turbulent(nu, [(q, l1), (q, la1), (q, la2), (q, l4)])
    h_t1 = h1 - l1.head_loss(q, nu)
    h_t2 = h2 + l4.head_loss(q, nu)
    e_sc1_in = h_t1 - la1.head_loss(q, nu)
    e_sc1_out = h_t2 + la2.head_loss(q, nu)
    if abs(e_sc1_in - e_sc1_out - open_valve_loss(sc1, q, la1.d, rho)) > 1.0e-9:
        raise RuntimeError("stop-check leg does not close")
    for v, state, qq, a, b in (
        (sc1, "open", q, e_sc1_in, e_sc1_out),
        (sc2, "closed", 0.0, h_t1, h_t2),
    ):
        problem = el.valve_state_problem(v, state, qq, a, b, rho, STATE_MARGIN)
        if problem:
            raise ValueError(f"{v.id} {problem}")

    project = make_project(
        "ref-stop-check-valves-locked-closed",
        "Stop-check valves, one locked closed",
        fluid,
        [
            reservoir("R1", z1, level1),
            ideal_tee("T1", z_t1),
            sc1,
            sc2,
            ideal_tee("T2", z_t2),
            reservoir("R2", z2, level2),
        ],
        [
            l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            la1.connect("LA1", "T1:run_outlet", "SC1:inlet"),
            la2.connect("LA2", "SC1:outlet", "T2:run_inlet"),
            lb1.connect("LB1", "T1:branch", "SC2:inlet"),
            lb2.connect("LB2", "SC2:outlet", "T2:branch"),
            l4.connect("L4", "T2:run_outlet", "R2:port_1"),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "LA1": q, "LA2": q, "LB1": 0.0, "LB2": 0.0, "L4": q},
        egl={
            "R1:port_1": h1,
            "T1:run_inlet": h_t1,
            "T1:run_outlet": h_t1,
            "T1:branch": h_t1,
            "SC1:inlet": e_sc1_in,
            "SC1:outlet": e_sc1_out,
            "SC2:inlet": h_t1,
            "SC2:outlet": h_t2,
            "T2:run_inlet": h_t2,
            "T2:branch": h_t2,
            "T2:run_outlet": h_t2,
            "R2:port_1": h2,
        },
        pressures={
            "SC1:inlet": dv.static_pressure(rho, e_sc1_in, z_v, la1.velocity(q)),
            "SC1:outlet": dv.static_pressure(rho, e_sc1_out, z_v, la2.velocity(q)),
            "SC2:inlet": dv.static_pressure(rho, h_t1, z_v, 0.0),
            "SC2:outlet": dv.static_pressure(rho, h_t2, z_v, 0.0),
        },
        valves={"SC1": {"state": "open"}, "SC2": {"state": "closed"}},
    )
    return ReferenceCase(
        name="stop_check_valves_locked_closed",
        description=(
            "Two parallel legs with stop-check valves, one active in forward flow and one "
            "locked closed: verifies the Crane globe stop-check K, a locked-closed valve holding "
            "zero flow, and each closed-valve port at its own side's EGL."
        ),
        source=_source(
            "stop_check_valves_locked_closed",
            "Darcy-Weisbach + Colebrook; K from fluids K_globe_stop_check_valve_Crane(style 0); "
            "brentq",
        ),
        project=project,
        expected=expected,
    )


# --- Control valves (PRV, PSV, FCV) -----------------------------------------------------------

CONTROL_IN = Line(0.1023, 80.0, (("entrance_sharp", 1), ("elbow_90_lr", 2)))
CONTROL_OUT = Line(0.0779, 120.0, (("elbow_90_lr", 2), ("exit", 1)))
CONTROL_Z = 5.0
"""m; the control valves' elevation (both ports)."""


def control_valve_case(
    *,
    name: str,
    title: str,
    description: str,
    valve: ControlValve,
    state: ValveState,
    h1_parts: tuple[float, float],
    h2_parts: tuple[float, float],
) -> ReferenceCase:
    """R1 → L1 (102.3 mm) → control valve → L2 (77.9 mm) → R2, solved in the given state.

    - PRV active: H_R2 + h_L2(Q) = z + p_set/(ρg) + v_out(Q)²/(2g), v_out in L2 (brentq);
    - PSV active: H_R1 − h_L1(Q) = z + p_set/(ρg) + v_in(Q)²/(2g), v_in in L1 (brentq);
    - FCV active: Q = q_set;
    - open: H_R1 − H_R2 = h_L1 + K_open v_in²/(2g) + h_L2 (brentq);
    - closed: Q = 0.
    Then EGL_in = H_R1 − h_L1(Q), EGL_out = H_R2 + h_L2(Q), and the guard checks the state
    against design §5.3's rules with STATE_MARGIN.
    """
    fluid, rho, mu, nu = _fluid_a()
    (z1, level1), (z2, level2) = h1_parts, h2_parts
    h1, h2 = z1 + level1, z2 + level2
    l1, l2 = CONTROL_IN, CONTROL_OUT
    k_open = el.valve_k(valve.valve_type, valve.resistance, l1.d)
    z = valve.elevation

    if state == "closed":
        q = 0.0
    elif state == "open":
        q = dv.solve_flow(
            lambda q: l1.head_loss(q, nu) + el.valve_loss(k_open, q, l1.d) + l2.head_loss(q, nu),
            h1 - h2,
        )
    elif valve.valve_type == "prv":
        q = solve_decreasing(
            lambda q: el.setpoint_head(z, valve.setpoint, rho, q, l2.d) - h2 - l2.head_loss(q, nu)
        )
    elif valve.valve_type == "psv":
        q = solve_decreasing(
            lambda q: h1 - l1.head_loss(q, nu) - el.setpoint_head(z, valve.setpoint, rho, q, l1.d)
        )
    else:
        q = valve.setpoint
    if q != 0.0:
        require_turbulent(nu, [(q, l1), (q, l2)])
    e_in, e_out = h1 - l1.head_loss(q, nu), h2 + l2.head_loss(q, nu)
    problem = el.valve_state_problem(valve, state, q, e_in, e_out, rho, STATE_MARGIN, l1.d, l2.d)
    if problem:
        raise ValueError(f"{name}: {problem}")
    if state == "active" and valve.valve_type == "prv":
        # By construction the outlet static pressure is the setpoint.
        p_out = dv.static_pressure(rho, e_out, z, l2.velocity(q))
        if abs(p_out - valve.setpoint) > 1.0e-6:
            raise RuntimeError("PRV outlet pressure is not the setpoint")

    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        fluid,
        [reservoir("R1", z1, level1), valve, reservoir("R2", z2, level2)],
        [
            l1.connect("L1", "R1:port_1", f"{valve.id}:inlet"),
            l2.connect("L2", f"{valve.id}:outlet", "R2:port_1"),
        ],
    )
    flags = []
    if state != "active" and valve.status == "active":
        flags.append({"code": "CONTROL_VALVE_SETPOINT_NOT_MET", "componentId": valve.id})
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q},
        egl={
            "R1:port_1": h1,
            f"{valve.id}:inlet": e_in,
            f"{valve.id}:outlet": e_out,
            "R2:port_1": h2,
        },
        pressures={
            f"{valve.id}:inlet": dv.static_pressure(rho, e_in, z, l1.velocity(q)),
            f"{valve.id}:outlet": dv.static_pressure(rho, e_out, z, l2.velocity(q)),
        },
        valves={valve.id: {"state": state}},
        flags=flags,
    )
    method = {
        ("prv", "active"): "PRV outlet EGL = z + p_set/(rho g) + v_out^2/2g; brentq",
        ("psv", "active"): "PSV inlet EGL = z + p_set/(rho g) + v_in^2/2g; brentq",
        ("fcv", "active"): "FCV flow = setpoint",
        ("fcv", "closed"): (
            "FCV closes on reverse head (design 12; EPANET would give XFCV, passing reverse flow)"
        ),
    }.get((valve.valve_type, state), f"control valve {state} (design 5.3 status rules)")
    if valve.status != "active":
        method = f"control valve {valve.status}: {state} whatever its setpoint (design 5.3)"
    elif state == "open" and valve.resistance is not None:
        method += "; fully open law K v_in^2/2g, K from the entered resistance by definition"
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, "Darcy-Weisbach + Colebrook lines; " + method),
        project=project,
        expected=expected,
    )


def prv_active() -> ReferenceCase:
    """PRV holding 150 kPa gauge static at its outlet (z = 5 m) from a 60 m supply to a 10 m
    reservoir: active, EGL_out = 5 + 150000/(ρg) + v_out²/(2g)."""
    return control_valve_case(
        name="prv_active",
        title="PRV active",
        description=(
            "A pressure-reducing valve throttling to 150 kPa static pressure at its outlet: "
            "verifies the static-pressure setpoint (EGL_out = z + p/(rho g) + v_out^2/2g with "
            "the outlet pipe velocity) and the active state."
        ),
        valve=control_valve("PRV1", CONTROL_Z, "prv", 150000.0),
        state="active",
        h1_parts=(50.0, 10.0),
        h2_parts=(8.0, 2.0),
    )


def prv_open() -> ReferenceCase:
    """PRV set to 500 kPa, more than the 40 m supply can give: fully open with K = 4 as
    entered (design §5.3 rule: OPEN stays open while EGL_out < h_set)."""
    return control_valve_case(
        name="prv_open",
        title="PRV open, setpoint not reachable",
        description=(
            "A PRV whose setpoint exceeds what the supply can deliver: verifies that it runs "
            "fully open with its entered K, and the CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        valve=control_valve(
            "PRV1", CONTROL_Z, "prv", 500000.0, resistance=flow_coefficient("K", 4.0)
        ),
        state="open",
        h1_parts=(32.0, 8.0),
        h2_parts=(0.0, 2.0),
    )


def prv_closed() -> ReferenceCase:
    """PRV set to 150 kPa (h_set ≈ 20.3 m) with a 40 m reservoir downstream of it: active flow
    would reverse, so it closes, Q = 0 (design §5.3)."""
    return control_valve_case(
        name="prv_closed",
        title="PRV closed by downstream head",
        description=(
            "A PRV whose downstream reservoir head exceeds its setpoint head: verifies that it "
            "closes (no reverse flow, each side at its reservoir's EGL) and the "
            "CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        valve=control_valve("PRV1", CONTROL_Z, "prv", 150000.0),
        state="closed",
        h1_parts=(50.0, 10.0),
        h2_parts=(38.0, 2.0),
    )


def psv_active() -> ReferenceCase:
    """PSV holding 200 kPa gauge static at its inlet from a 28 m supply, discharging to a 2 m
    reservoir: active, EGL_in = 5 + 200000/(ρg) + v_in²/(2g)."""
    return control_valve_case(
        name="psv_active",
        title="PSV active",
        description=(
            "A pressure-sustaining valve throttling to keep 200 kPa static pressure at its "
            "inlet: verifies the static-pressure setpoint on the inlet side (with the inlet "
            "pipe velocity) and the active state."
        ),
        valve=control_valve("PSV1", CONTROL_Z, "psv", 200000.0),
        state="active",
        h1_parts=(24.0, 4.0),
        h2_parts=(0.0, 2.0),
    )


def psv_open() -> ReferenceCase:
    """PSV set to 60 kPa, below the inlet pressure it sees fully open: open, ideal (K = 0), so
    EGL_in = EGL_out."""
    return control_valve_case(
        name="psv_open",
        title="PSV open above its setpoint",
        description=(
            "A PSV whose inlet pressure stays above its setpoint with the valve fully open: "
            "verifies the open state of an ideal control valve (no loss) and the "
            "CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        valve=control_valve("PSV1", CONTROL_Z, "psv", 60000.0),
        state="open",
        h1_parts=(36.0, 4.0),
        h2_parts=(0.0, 2.0),
    )


def psv_closed() -> ReferenceCase:
    """PSV set to 250 kPa (h_set ≈ 30.5 m) fed by a 22 m reservoir: it cannot sustain the
    setpoint and closes, Q = 0 (design §5.3)."""
    return control_valve_case(
        name="psv_closed",
        title="PSV closed below its setpoint",
        description=(
            "A PSV whose supply head is below its setpoint head: verifies that it closes (zero "
            "flow; active flow would reverse) and the CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        valve=control_valve("PSV1", CONTROL_Z, "psv", 250000.0),
        state="closed",
        h1_parts=(18.0, 4.0),
        h2_parts=(0.0, 2.0),
    )


def fcv_active() -> ReferenceCase:
    """FCV limiting the flow to 0.012 m³/s between a 40 m supply and a 2 m reservoir."""
    return control_valve_case(
        name="fcv_active",
        title="FCV active",
        description=(
            "A flow-control valve holding 12 L/s: verifies the fixed-flow state and the EGLs "
            "on both sides of the throttling valve."
        ),
        valve=control_valve("FCV1", CONTROL_Z, "fcv", 0.012),
        state="active",
        h1_parts=(36.0, 4.0),
        h2_parts=(0.0, 2.0),
    )


def fcv_open() -> ReferenceCase:
    """FCV set to 0.08 m³/s, more than the line passes fully open (Cv = 250 entered): open."""
    return control_valve_case(
        name="fcv_open",
        title="FCV open, setpoint not reachable",
        description=(
            "An FCV whose flow setpoint exceeds what the line can pass: verifies that it runs "
            "fully open with K from its Cv, and the CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        valve=control_valve(
            "FCV1", CONTROL_Z, "fcv", 0.08, resistance=flow_coefficient("Cv", 250.0)
        ),
        state="open",
        h1_parts=(36.0, 4.0),
        h2_parts=(0.0, 2.0),
    )


def fcv_open_loss_limits() -> ReferenceCase:
    """FCV with Cv = 30 entered, set to 0.018 m³/s on the 38 m line: the pipes alone would pass
    about 0.022 m³/s, so the head across the valve at the setpoint is positive, but it is
    smaller than the valve's own fully open loss K_open v²/(2g) at 0.018 m³/s. The valve
    cannot pass its setpoint even fully open: open at the fully open flow (design §5.3, FCV
    rule with hml, the fully open loss at the setpoint; EPANET's fcvstatus, which opens only
    on a reverse head, would report it throttling with a K below K_open)."""
    _, _, _, nu = _fluid_a()
    valve = control_valve("FCV1", CONTROL_Z, "fcv", 0.018, resistance=flow_coefficient("Cv", 30.0))
    h1, h2 = 36.0 + 4.0, 0.0 + 2.0
    l1, l2 = CONTROL_IN, CONTROL_OUT
    q_pipes = dv.solve_flow(lambda q: l1.head_loss(q, nu) + l2.head_loss(q, nu), h1 - h2)
    head_at_setpoint = (
        h1 - l1.head_loss(valve.setpoint, nu) - (h2 + l2.head_loss(valve.setpoint, nu))
    )
    k_open = el.valve_k(valve.valve_type, valve.resistance, l1.d)
    open_loss = el.valve_loss(k_open, valve.setpoint, l1.d)
    if not (q_pipes > valve.setpoint and 0.0 < head_at_setpoint < open_loss - STATE_MARGIN):
        raise ValueError("the case needs 0 < head across the valve at Q_set < its open loss")
    return control_valve_case(
        name="fcv_open_loss_limits",
        title="FCV open, limited by its own loss",
        description=(
            "An FCV with Cv = 30 whose setpoint the pipes alone could pass, but not with the "
            "valve's own fully open loss: verifies that it runs fully open at the flow its Cv "
            "allows (not throttling with a K below its fully open K), and the "
            "CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        valve=valve,
        state="open",
        h1_parts=(36.0, 4.0),
        h2_parts=(0.0, 2.0),
    )


def prv_failed_open() -> ReferenceCase:
    """The prv_active line (150 kPa setting, 60 m supply, 10 m outlet reservoir) with the
    valve failed open and K = 4 entered: it follows the fully open law whatever its setting,
        H_R1 − H_R2 = h_L1(Q) + 4 v_in²/(2g) + h_L2(Q)   (brentq)."""
    return control_valve_case(
        name="prv_failed_open",
        title="PRV failed open",
        description=(
            "A PRV whose status is failed_open on a line where it would otherwise throttle: "
            "verifies the fully open law with its entered K and that its setpoint is ignored "
            "(no CONTROL_VALVE_SETPOINT_NOT_MET flag)."
        ),
        valve=control_valve(
            "PRV1",
            CONTROL_Z,
            "prv",
            150000.0,
            status="failed_open",
            resistance=flow_coefficient("K", 4.0),
        ),
        state="open",
        h1_parts=(50.0, 10.0),
        h2_parts=(8.0, 2.0),
    )


def fcv_failed_closed() -> ReferenceCase:
    """The fcv_active line (0.012 m³/s setting, 40 m to 2 m) with the valve failed closed:
    Q = 0, each side at its reservoir's EGL."""
    return control_valve_case(
        name="fcv_failed_closed",
        title="FCV failed closed",
        description=(
            "An FCV whose status is failed_closed on a line where it would otherwise hold its "
            "flow: verifies zero flow, each side at its reservoir's EGL, and that its setpoint "
            "is ignored (no CONTROL_VALVE_SETPOINT_NOT_MET flag)."
        ),
        valve=control_valve("FCV1", CONTROL_Z, "fcv", 0.012, status="failed_closed"),
        state="closed",
        h1_parts=(36.0, 4.0),
        h2_parts=(0.0, 2.0),
    )


def fcv_closed_reverse() -> ReferenceCase:
    """FCV with the higher head on its outlet side: closed (our semantics, design §12), Q = 0."""
    return control_valve_case(
        name="fcv_closed_reverse",
        title="FCV closed by reverse head",
        description=(
            "An FCV with reverse head across it: verifies that it closes (zero flow; unlike "
            "EPANET's FCV, ours does not pass reverse flow) and the "
            "CONTROL_VALVE_SETPOINT_NOT_MET flag."
        ),
        valve=control_valve("FCV1", CONTROL_Z, "fcv", 0.012),
        state="closed",
        h1_parts=(6.0, 4.0),
        h2_parts=(22.0, 3.0),
    )


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    isolation_valves_crane_default_k,
    isolation_valve_cv,
    isolation_valves_kv_and_k,
    isolation_valves_isolated_section,
    check_valve_cracking_pressure,
    check_valve_reverse_closed,
    check_valve_below_cracking_pressure,
    check_valve_locked_open_reverse,
    stop_check_valves_locked_closed,
    prv_active,
    prv_open,
    prv_closed,
    psv_active,
    psv_open,
    psv_closed,
    fcv_active,
    fcv_open,
    fcv_open_loss_limits,
    fcv_closed_reverse,
    prv_failed_open,
    fcv_failed_closed,
)
