"""Closed-form expected results for Crane tees and wyes (design §2.4, §5.4, §12).

Each case is one branch component whose three ports are piped to reservoirs (or a plug). With
q_p the flow *into* the component at port p and E the EGL of the combined-flow port, the
unknowns (q_a, q_b, q_c, E) solve, with scipy.optimize.fsolve,

    q_a + q_b + q_c = 0                                   (continuity)
    H_terminal(p) − h_line,p(q_p) = E + offset_p(q)       (energy, each port to a reservoir)
    q_p = 0                                               (a port piped to a plug)

where offset_p = EGL(p) − EGL(combined) comes from the Crane TP-410 tee functions of
``fluids.fittings`` called directly (the cited source; ``element_laws.branch_losses``): diverging
offsets are −K v_c²/(2g), converging +K v_c²/(2g), v_c the combined flow over the combined port's
pipe area; a tee whose branch carries the combined flow uses Darby 3-K per run leg on the leg's
own velocity (design §5.4 fallback, flag TEE_PATTERN_FALLBACK). Guards check the solved pattern
and keep the flow ratio clear of the steps of the Crane correlations.

Every pipe, elevation and level is a test input. Independence: nothing here imports
``opensolve_pipe.services``.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import fluids.fittings
import numpy as np
from numpy.typing import NDArray
from scipy.optimize import fsolve

from opensolve_pipe.models.components import BranchLossModel, Component
from opensolve_pipe.models.piping import PipeConnection
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    crane_tee,
    custom_fluid,
    make_project,
    plug,
    reservoir,
    wye,
)
from tests.reference.line import Line, require_turbulent

STEP_MARGIN = 0.05
"""Smallest allowed distance of the solved flow ratio from a Crane correlation step."""


def _source(name: str, method: str) -> str:
    return dv.source(name, method, "derivations_branches")


@dataclass(frozen=True)
class Terminal:
    """What one branch port is piped to: a reservoir (z, level) or a plug (z), through a line
    drawn from the terminal to the port (``into_port``) or from the port to the terminal."""

    cid: str
    z: float
    line: Line
    level: float | None = None  # None: a plug
    into_port: bool = True

    def component(self) -> Component:
        if self.level is None:
            return plug(self.cid, self.z)
        return reservoir(self.cid, self.z, self.level)

    def connection(self, cid: str, port_key: str) -> PipeConnection:
        own = f"{self.cid}:port_1"
        if self.into_port:
            return self.line.connect(cid, own, port_key)
        return self.line.connect(cid, port_key, own)


@dataclass(frozen=True)
class BranchSolution:
    flows_in: dict[str, float]
    egl: dict[str, float]
    losses: el.BranchLosses


def ideal_losses(ports: list[str]) -> el.BranchLosses:
    """lossModel 'ideal' (design §2.4): no loss on any path, one EGL at every port (an
    EPANET-style junction)."""
    zero = dict.fromkeys(ports, 0.0)
    return el.BranchLosses("ideal", None, zero, dict(zero), False)


def solve_branch(
    kind: el.BranchKind,
    angle: float,
    terminals: Mapping[str, Terminal],
    nu: float,
    guess: Mapping[str, float],
    loss_model: BranchLossModel = "crane",
) -> BranchSolution:
    """Solve the system in the module docstring; ``guess`` holds q_p per reservoir port and
    'E'. A port piped to a plug has q_p = 0 exactly and no energy equation of its own."""
    ports = list(terminals)
    open_ports = [p for p in ports if terminals[p].level is not None]
    diameters = {p: terminals[p].line.d for p in ports}

    def losses_at(flows: dict[str, float]) -> el.BranchLosses:
        if loss_model == "ideal":
            return ideal_losses(ports)
        return el.branch_losses(kind, angle, flows, diameters, nu)

    def unpack(x: NDArray[np.float64]) -> tuple[dict[str, float], float]:
        flows = dict.fromkeys(ports, 0.0)
        flows.update({p: float(x[i]) for i, p in enumerate(open_ports)})
        return flows, float(x[len(open_ports)])

    def residuals(x: NDArray[np.float64]) -> list[float]:
        flows, e = unpack(x)
        offsets = losses_at(flows).offsets
        out = [sum(flows.values())]
        for p in open_ports:
            t = terminals[p]
            assert t.level is not None
            out.append(t.z + t.level - t.line.head_loss(flows[p], nu) - (e + offsets[p]))
        return out

    x0 = [guess[p] for p in open_ports] + [guess["E"]]
    solution, _, ier, message = fsolve(residuals, x0, xtol=1.0e-13, full_output=True)
    if ier != 1 or max(abs(r) for r in residuals(solution)) > 1.0e-11:
        raise RuntimeError(f"fsolve failed: {message}")
    flows, e = unpack(solution)
    losses = losses_at(flows)
    egl = {p: e + losses.offsets[p] for p in ports}
    return BranchSolution(flows, egl, losses)


def branch_case(
    *,
    name: str,
    title: str,
    description: str,
    method: str,
    kind: el.BranchKind,
    angle: float,
    z_branch: float,
    terminals: Mapping[str, Terminal],
    guess: Mapping[str, float],
    pattern: str,
    loss_model: BranchLossModel = "crane",
    flags: Sequence[dict[str, str]] = (),
) -> ReferenceCase:
    """Solve, guard the pattern and flow regime, and build the case (component id 'T1')."""
    fluid_name, rho, mu = dv.FLUID_A
    nu = mu / rho
    sol = solve_branch(kind, angle, terminals, nu, guess, loss_model)
    if sol.losses.pattern != pattern:
        raise ValueError(f"{name}: solved pattern {sol.losses.pattern!r}, expected {pattern!r}")
    if loss_model == "crane" and not sol.losses.fallback:
        ratio = el.q_ratio(sol.losses, sol.flows_in, kind)
        if ratio not in (0.0, 1.0) and el.crane_step_distance(ratio) < STEP_MARGIN:
            raise ValueError(f"{name}: flow ratio {ratio} too close to a Crane step")
    require_turbulent(nu, [(q, terminals[p].line) for p, q in sol.flows_in.items() if q != 0.0])

    branch = crane_tee("T1", z_branch) if kind == "tee" else wye("T1", z_branch, angle, loss_model)
    components: list[Component] = [branch]
    connections = []
    flows: dict[str, float] = {}
    egl: dict[str, float] = {}
    pressures: dict[str, float] = {}
    for i, (port, t) in enumerate(terminals.items()):
        cid = f"L{i + 1}"
        key = f"T1:{port}"
        components.append(t.component())
        connections.append(t.connection(cid, key))
        q_in = sol.flows_in[port]
        flows[cid] = q_in if t.into_port or q_in == 0.0 else -q_in
        egl[key] = sol.egl[port]
        # The terminal's EGL: a reservoir's head; a plug's port shares the dead leg's EGL.
        egl[f"{t.cid}:port_1"] = sol.egl[port] if t.level is None else t.z + t.level
        pressures[key] = dv.static_pressure(rho, sol.egl[port], z_branch, t.line.velocity(q_in))
        if t.level is None:
            pressures[f"{t.cid}:port_1"] = dv.static_pressure(rho, sol.egl[port], t.z, 0.0)
    flags = list(flags)
    if sol.losses.fallback:
        flags.append({"code": "TEE_PATTERN_FALLBACK", "componentId": "T1"})

    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        custom_fluid(fluid_name, rho, mu),
        components,
        connections,
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows=flows,
        egl=egl,
        pressures=pressures,
        flags=flags,
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=expected,
    )


CRANE_METHOD = (
    "Darcy-Weisbach + Colebrook lines; path K from fluids K_branch_{0}_Crane and "
    "K_run_{0}_Crane at angle {1} on the combined-flow velocity; fsolve"
)

RUN_LINE = 0.1023
"""m; run pipes of every tee and wye case (equal run diameters, as the Crane correlation
assumes)."""


def tee_crane_diverging() -> ReferenceCase:
    """R1 → run_inlet; run_outlet → R2; branch (77.9 mm, β = 0.76) → R3. Diverging from the
    run inlet: EGL(run_outlet) = E − K_run v_c²/2g, EGL(branch) = E − K_branch v_c²/2g."""
    terminals = {
        "run_inlet": Terminal("R1", 15.0, Line(RUN_LINE, 40.0, (("entrance_sharp", 1),)), 5.0),
        "run_outlet": Terminal(
            "R2", 0.0, Line(RUN_LINE, 60.0, (("exit", 1),)), 5.0, into_port=False
        ),
        "branch": Terminal("R3", 4.0, Line(0.0779, 30.0, (("exit", 1),)), 4.0, into_port=False),
    }
    return branch_case(
        name="tee_crane_diverging",
        title="Crane tee, diverging flow",
        description=(
            "A tee splitting flow from its run inlet to the run outlet and the branch, each "
            "piped to a reservoir: verifies the Crane TP-410 diverging tee K (run and branch, "
            "fluids) on the combined-flow velocity and the flow split it produces."
        ),
        method=CRANE_METHOD.format("diverging", 90),
        kind="tee",
        angle=90.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"run_inlet": 0.03, "run_outlet": -0.02, "branch": -0.01, "E": 18.0},
        pattern="diverging from run_inlet",
    )


def tee_crane_converging() -> ReferenceCase:
    """R1 → run_inlet and R3 → branch (102.3 mm, β = 1) join; run_outlet → R2. Converging to
    the run outlet: EGL(run_inlet) = E + K_run v_c²/2g, EGL(branch) = E + K_branch v_c²/2g."""
    terminals = {
        "run_inlet": Terminal("R1", 15.0, Line(RUN_LINE, 50.0, (("entrance_sharp", 1),)), 5.0),
        "branch": Terminal("R3", 14.0, Line(RUN_LINE, 35.0, (("entrance_sharp", 1),)), 1.5),
        "run_outlet": Terminal(
            "R2", 0.0, Line(RUN_LINE, 80.0, (("exit", 1),)), 2.0, into_port=False
        ),
    }
    return branch_case(
        name="tee_crane_converging",
        title="Crane tee, converging flow",
        description=(
            "Two reservoirs feeding a tee through its run inlet and branch, combined flow out of "
            "the run outlet: verifies the Crane TP-410 converging tee K (run and branch, fluids; "
            "the branch K is negative at this split) and the resulting flows."
        ),
        method=CRANE_METHOD.format("converging", 90),
        kind="tee",
        angle=90.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"run_inlet": 0.02, "branch": 0.015, "run_outlet": -0.035, "E": 8.0},
        pattern="converging to run_outlet",
    )


def tee_crane_dead_branch() -> ReferenceCase:
    """Run flow R1 → R2 through a Crane tee whose branch (52.5 mm, β² = 0.26) is piped to a
    plug 2 m above the tee.

    The branch carries no flow, so the run sees K_run(q = 0) = 0 and the dead branch
    EGL(branch) = E − K_branch(q = 0) v_c²/2g with K_branch_diverging(q = 0) = 1: the branch
    port has the run's static head. With β² ≤ 0.35 the converging reading of the same pattern
    (K_branch_converging(q = 0) = −1 on the run outlet) gives the same EGL; a self-check
    compares the two. The plug takes the dead leg's EGL.
    """
    terminals = {
        "run_inlet": Terminal("R1", 10.0, Line(RUN_LINE, 50.0, (("entrance_sharp", 1),)), 2.0),
        "run_outlet": Terminal(
            "R2", 0.0, Line(RUN_LINE, 70.0, (("exit", 1),)), 1.0, into_port=False
        ),
        "branch": Terminal("P1", 4.0, Line(0.0525, 6.0), None, into_port=False),
    }
    return branch_case(
        name="tee_crane_dead_branch",
        title="Crane tee with a plugged branch",
        description=(
            "Run flow through a Crane tee whose branch is piped to a plug: verifies zero branch "
            "flow, no run loss at q = 0, and the dead branch at the run's static head "
            "(K_branch(q = 0) on the combined velocity), passed on to the plug."
        ),
        method=CRANE_METHOD.format("diverging", 90),
        kind="tee",
        angle=90.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"run_inlet": 0.03, "run_outlet": -0.03, "branch": 0.0, "E": 10.0},
        pattern="diverging from run_inlet",
    )


def tee_crane_bullhead_fallback() -> ReferenceCase:
    """R1 → branch; the flow divides into both run legs (77.9 mm each) to R2 and R3: a bullhead
    tee, which the Crane functions do not cover. Design §5.4 fallback: each run leg x loses
    K_x v_x²/2g, K_x = Darby3K(Di = D_x, Re = Re_x, 'Tee, Through-branch, (as elbow), flanged,
    (r/D = 1)') on its own velocity; TEE_PATTERN_FALLBACK (warning) is expected."""
    terminals = {
        "branch": Terminal("R1", 15.0, Line(RUN_LINE, 40.0, (("entrance_sharp", 1),)), 5.0),
        "run_inlet": Terminal("R2", 0.0, Line(0.0779, 50.0, (("exit", 1),)), 4.0, into_port=False),
        "run_outlet": Terminal("R3", 2.0, Line(0.0779, 35.0, (("exit", 1),)), 4.0, into_port=False),
    }
    return branch_case(
        name="tee_crane_bullhead_fallback",
        title="Bullhead tee (Darby 3-K fallback)",
        description=(
            "Flow entering a Crane tee through its branch and dividing into both run legs: "
            "verifies the uncovered-pattern fallback (Darby 3-K 'tee through-branch as elbow' "
            "per run leg on its own velocity and Reynolds number) and the TEE_PATTERN_FALLBACK "
            "flag."
        ),
        method=(
            "Darcy-Weisbach + Colebrook lines; run-leg K from fluids Darby3K(Di, Re, "
            "'Tee, Through-branch, (as elbow), flanged, (r/D = 1)'); fsolve"
        ),
        kind="tee",
        angle=90.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"branch": 0.03, "run_inlet": -0.017, "run_outlet": -0.013, "E": 17.0},
        pattern="diverging from branch",
    )


def wye_crane_diverging_45() -> ReferenceCase:
    """A 45° wye: R1 → inlet; outlet_1 (run) → R2; outlet_2 (77.9 mm lateral) → R3. Diverging
    from the inlet with the Crane functions at angle 45°."""
    terminals = {
        "inlet": Terminal("R1", 14.0, Line(RUN_LINE, 40.0, (("entrance_sharp", 1),)), 4.0),
        "outlet_1": Terminal("R2", 0.0, Line(RUN_LINE, 60.0, (("exit", 1),)), 4.0, into_port=False),
        "outlet_2": Terminal("R3", 4.0, Line(0.0779, 30.0, (("exit", 1),)), 2.0, into_port=False),
    }
    return branch_case(
        name="wye_crane_diverging_45",
        title="Crane 45-degree wye, diverging flow",
        description=(
            "A 45-degree wye dividing flow from its inlet into the straight outlet and the "
            "lateral: verifies the Crane TP-410 diverging K at 45 degrees (fluids) and the "
            "wye's port roles."
        ),
        method=CRANE_METHOD.format("diverging", 45),
        kind="wye",
        angle=45.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"inlet": 0.03, "outlet_1": -0.02, "outlet_2": -0.01, "E": 16.0},
        pattern="diverging from inlet",
    )


def wye_crane_converging_45() -> ReferenceCase:
    """A 45° wye: R1 → outlet_1 (run) and R3 → outlet_2 (the lateral, 102.3 mm) join; inlet →
    R2. Converging to the inlet. The lateral leans toward outlet_1 (the wye's diverging
    orientation, which its port names give), so flow entering through it meets the combined
    flow leaving through the inlet at 45°: the geometry of Crane's converging lateral. (A
    combined flow leaving through outlet_1 would make the lateral flow turn 135°.)"""
    terminals = {
        "outlet_1": Terminal("R1", 15.0, Line(RUN_LINE, 50.0, (("entrance_sharp", 1),)), 5.0),
        "outlet_2": Terminal("R3", 14.0, Line(RUN_LINE, 35.0, (("entrance_sharp", 1),)), 1.0),
        "inlet": Terminal("R2", 0.0, Line(RUN_LINE, 80.0, (("exit", 1),)), 2.0, into_port=False),
    }
    return branch_case(
        name="wye_crane_converging_45",
        title="Crane 45-degree wye, converging flow",
        description=(
            "Two reservoirs feeding a 45-degree wye through its straight outlet and lateral, "
            "combined flow out of the inlet (the lateral meets the combined flow at 45 "
            "degrees): verifies the Crane TP-410 converging K at 45 degrees (fluids), "
            "including a negative lateral K."
        ),
        method=CRANE_METHOD.format("converging", 45),
        kind="wye",
        angle=45.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"outlet_1": 0.02, "outlet_2": 0.015, "inlet": -0.035, "E": 8.0},
        pattern="converging to inlet",
    )


def wye_ideal_junction() -> ReferenceCase:
    """The wye_crane_diverging_45 network with lossModel 'ideal': a junction with one EGL E at
    all three ports (design §2.4), so the split follows from the lines alone:
        q_in + q_1 + q_2 = 0,   H_p − h_line,p(q_p) = E   (fsolve)."""
    terminals = {
        "inlet": Terminal("R1", 14.0, Line(RUN_LINE, 40.0, (("entrance_sharp", 1),)), 4.0),
        "outlet_1": Terminal("R2", 0.0, Line(RUN_LINE, 60.0, (("exit", 1),)), 4.0, into_port=False),
        "outlet_2": Terminal("R3", 4.0, Line(0.0779, 30.0, (("exit", 1),)), 2.0, into_port=False),
    }
    return branch_case(
        name="wye_ideal_junction",
        title="Ideal wye junction",
        description=(
            "A 45-degree wye with lossModel 'ideal' dividing flow from its inlet: verifies that "
            "an ideal branch is a junction with one EGL at all three ports (no path loss, as "
            "EPANET models junctions) and the split the lines alone give."
        ),
        method="Darcy-Weisbach + Colebrook lines; ideal junction (one EGL, design 2.4); fsolve",
        kind="wye",
        angle=45.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"inlet": 0.03, "outlet_1": -0.02, "outlet_2": -0.01, "E": 16.0},
        pattern="ideal",
        loss_model="ideal",
    )


def wye_crane_reversed_lateral() -> ReferenceCase:
    """A 45° wye used against its lean: R1 → outlet_1, dividing into the inlet (→ R2) and the
    lateral outlet_2 (→ R3). The lateral leans toward outlet_1, so its flow turns 135°, which
    Crane's lateral data do not cover; design §5.4 still evaluates the Crane diverging
    functions at the wye's 45° (combined port outlet_1, run port inlet) and flags the wye
    CORRELATION_OUT_OF_RANGE (warning)."""
    terminals = {
        "outlet_1": Terminal("R1", 14.0, Line(RUN_LINE, 40.0, (("entrance_sharp", 1),)), 4.0),
        "inlet": Terminal("R2", 0.0, Line(RUN_LINE, 60.0, (("exit", 1),)), 4.0, into_port=False),
        "outlet_2": Terminal("R3", 4.0, Line(0.0779, 30.0, (("exit", 1),)), 2.0, into_port=False),
    }
    return branch_case(
        name="wye_crane_reversed_lateral",
        title="Crane wye used against its lean",
        description=(
            "A 45-degree wye with the combined flow entering through outlet_1 and dividing "
            "into the inlet and the lateral, whose flow turns 135 degrees: verifies the Crane "
            "diverging K evaluated at the wye's angle and the CORRELATION_OUT_OF_RANGE flag on "
            "the reversed lateral."
        ),
        method=CRANE_METHOD.format("diverging", 45),
        kind="wye",
        angle=45.0,
        z_branch=2.0,
        terminals=terminals,
        guess={"outlet_1": 0.03, "inlet": -0.02, "outlet_2": -0.01, "E": 16.0},
        pattern="diverging from outlet_1",
        flags=[{"code": "CORRELATION_OUT_OF_RANGE", "componentId": "T1"}],
    )


def twin_lines_crane_rung() -> ReferenceCase:
    """Two nearly balanced lines, R1 (H 30 m) → A → TM1 → B → R2 (H 0) and R3 (H 30.05 m) → C →
    TM2 → D → R4 (H 0), identical 102.3 mm pipes, joined by a 20 m rung X between the branches
    of their Crane tees.

    With X carrying no flow each line is a series run through its tee:
        H_in − H_out = h_A(Q) + K_run v²/(2g) + h_B(Q)   (brentq),
    K_run = K_run_diverging_Crane(D, D, Q, 0, 90) (q = 0). At zero branch flow a tee's branch
    port can sit anywhere between the readings with flow just leaving it (diverging, K_branch
    = K_branch_diverging_Crane at q = 0) and just entering it (converging, K_branch_converging_
    Crane at q = 0), so X stays dead while its head lies in both tees' bands
    (``el.zero_flow_limits``). Both rung ports take one head, the middle of the overlap of the
    two bands: the convention the solver reports (design §5.4, held legs); guards check that
    the bands overlap with margin and the middle lies in both.
    """
    fluid_name, rho, mu = dv.FLUID_A
    nu = mu / rho
    run_in = Line(RUN_LINE, 50.0, (("entrance_sharp", 1),))
    run_out = Line(RUN_LINE, 50.0, (("exit", 1),))
    rung = Line(RUN_LINE, 20.0)
    z_tee, z_res = 1.0, 0.0
    lines = {"TM1": ("R1", 30.0, "R2", 0.0), "TM2": ("R3", 30.05, "R4", 0.0)}
    diameters = {"run_inlet": RUN_LINE, "run_outlet": RUN_LINE, "branch": rung.d}
    components: list[Component] = []
    connections = []
    flows: dict[str, float] = {}
    egl: dict[str, float] = {}
    pressures: dict[str, float] = {}
    bands = []
    names = iter("ABCD")
    # q = 0 for any run flow: the Crane run K at zero branch flow (Q_run = 1 m³/s stands in).
    k_run = float(fluids.fittings.K_run_diverging_Crane(RUN_LINE, rung.d, 1.0, 0.0, 90.0))
    for tee_id, (src, h_src, dst, h_dst) in lines.items():

        def loss(q: float) -> float:
            return (
                run_in.head_loss(q, nu)
                + k_run * dv.velocity(q, RUN_LINE) ** 2 / (2.0 * dv.G)
                + run_out.head_loss(q, nu)
            )

        q = dv.solve_flow(loss, h_src - h_dst)
        require_turbulent(nu, [(q, run_in), (q, run_out)])
        e_in = h_src - run_in.head_loss(q, nu)
        e_out = h_dst + run_out.head_loss(q, nu)
        tee_flows = {"run_inlet": q, "run_outlet": -q, "branch": 0.0}
        (c_out, off_out), (c_in, off_in) = el.zero_flow_limits(
            "tee", 90.0, tee_flows, diameters, nu, "branch"
        )
        heads = {"run_inlet": e_in, "run_outlet": e_out}
        limits = (heads[c_out] + off_out, heads[c_in] + off_in)
        bands.append((min(limits), max(limits)))
        a, b = next(names), next(names)
        components += [
            reservoir(src, z_res, h_src - z_res),
            crane_tee(tee_id, z_tee),
            reservoir(dst, z_res, h_dst - z_res),
        ]
        connections += [
            run_in.connect(a, f"{src}:port_1", f"{tee_id}:run_inlet"),
            run_out.connect(b, f"{tee_id}:run_outlet", f"{dst}:port_1"),
        ]
        flows |= {a: q, b: q}
        egl |= {
            f"{src}:port_1": h_src,
            f"{tee_id}:run_inlet": e_in,
            f"{tee_id}:run_outlet": e_out,
            f"{dst}:port_1": h_dst,
        }
        pressures |= {
            f"{tee_id}:run_inlet": dv.static_pressure(rho, e_in, z_tee, run_in.velocity(q)),
            f"{tee_id}:run_outlet": dv.static_pressure(rho, e_out, z_tee, run_out.velocity(q)),
        }
    low, high = max(b[0] for b in bands), min(b[1] for b in bands)
    if not high - low > 2 * STEP_MARGIN * (high - low) + 0.02:
        raise ValueError("the two zero-flow bands must overlap clearly (more than 2 x 0.01 m)")
    h_rung = 0.5 * (low + high)
    if not all(b[0] < h_rung < b[1] for b in bands):
        raise ValueError("the rung head must lie inside both bands")
    connections.append(rung.connect("X", "TM1:branch", "TM2:branch"))
    flows["X"] = 0.0
    egl |= {"TM1:branch": h_rung, "TM2:branch": h_rung}
    pressures |= {
        key: dv.static_pressure(rho, h_rung, z_tee, 0.0) for key in ("TM1:branch", "TM2:branch")
    }
    project = make_project(
        "ref-twin-lines-crane-rung",
        "Twin lines joined by a dead rung",
        custom_fluid(fluid_name, rho, mu),
        components,
        connections,
    )
    expected = Expected(
        density=rho, dynamic_viscosity=mu, flows=flows, egl=egl, pressures=pressures
    )
    return ReferenceCase(
        name="twin_lines_crane_rung",
        description=(
            "Two nearly balanced lines joined by a rung between the branches of their Crane "
            "tees, the rung head inside both tees' zero-flow bands: verifies that the rung "
            "carries no flow (held at zero flow between the diverging and converging Crane "
            "readings at q = 0), each line's series flow with K_run at q = 0, and the rung head "
            "reported at the middle of the two bands' overlap."
        ),
        source=_source(
            "twin_lines_crane_rung",
            "Darcy-Weisbach + Colebrook lines; K_run_diverging_Crane at q = 0; zero-flow band "
            "of each branch from fluids K_branch_diverging_Crane and K_branch_converging_Crane "
            "at q -> 0; rung head = middle of the bands' overlap (design 5.4); brentq",
        ),
        project=project,
        expected=expected,
    )


def dead_branch_converging_reading(d_run: float, d_branch: float, q: float) -> float:
    """EGL(branch) − EGL(run_inlet) of a dead branch read as *converging* to the run outlet
    (combined flow q out of run_outlet, Q_branch = 0), for a self-check of
    tee_crane_dead_branch: EGL(run_outlet) = EGL(run_inlet) − K_run_converging v²/2g and
    EGL(branch) = EGL(run_outlet) + K_branch_converging v²/2g, both K at Q_branch = 0 from
    fluids (Crane TP-410), v on the run pipe."""
    ff = fluids.fittings
    head = dv.velocity(q, d_run) ** 2 / (2.0 * dv.G)
    k_run = float(ff.K_run_converging_Crane(d_run, d_branch, q, 0.0, 90.0))
    k_branch = float(ff.K_branch_converging_Crane(d_run, d_branch, q, 0.0, 90.0))
    return (k_branch - k_run) * head


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    tee_crane_diverging,
    tee_crane_converging,
    tee_crane_dead_branch,
    tee_crane_bullhead_fallback,
    wye_crane_diverging_45,
    wye_crane_converging_45,
    wye_ideal_junction,
    wye_crane_reversed_lateral,
    twin_lines_crane_rung,
)
