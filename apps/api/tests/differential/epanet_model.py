"""OpenSolve project -> EPANET 2.2 model and run (WNTR 1.5.0 INP + toolkit, double precision).

Mapping (as ``tests/reference/generate_epanet_cases.py``, TSD §10.1):

- Reservoir -> EPANET reservoir, head z + level + p_s/(ρg); ideal reference node -> reservoir
  with head z_port + p/(ρg). Ideal tee / wye and plug -> junction (zero demand).
- Assigned-flow node (SDD §4.11) -> junction at its port's elevation whose base demand is its
  flow: EPANET's demand is the flow withdrawn at the junction, positive out of the network as
  ours (TSD §4.8: the node's flow is its port's demand in the GGA), in m³/s in the WNTR model,
  which the INP writes in GPM to 11 significant digits; demand-driven analysis (DDA, EPANET's
  default and WNTR's, set explicitly: the demand is taken whatever the pressure) and the default
  pattern multiplier 1.
- Connection with n segments -> n EPANET pipes in series (intermediate junctions), D-W
  roughness in metres, each segment's 'custom' fittings (K x quantity) as its minor loss.
- Pump -> EPANET pump between its two port junctions, HEAD curve through the same collinear
  points (first point at Q = 0, so EPANET's Hmax = our shutoff), same speed; 'off' -> CLOSED.
- Flow-controlled pump (CLAUDE.md D11; proposal vfd-pump-modes.md §7.4), status on: EPANET has
  no speed control, so it stands for the state our solver reports, given as a pin
  (``control_pins``): active -> the EPANET 2.2 FAQ substitute for "a pump of a specific flow"
  (https://usepa.github.io/EPANET2.2/13_questions.html): the pump CLOSED, a demand of Q_set at
  its suction junction and -Q_set at its discharge junction; max_speed -> OPEN at SPEED = its
  ``speed`` (the maximum); min_speed -> OPEN at SPEED = control.minSpeed; no_flow -> CLOSED.
  EPANET's pump rules (pumpstatus) still apply at a speed limit; our rules for the state are
  checked by ``checks.status_problems``. A pump with no result of ours (isolated) runs at its
  maximum speed, as our solver holds it there (rule A0), unless ``fuzz`` names it no_flow (held
  at no flow with both sides closed off, its flag kept: ``checks.closed_without_result``).
- Isolation valve -> TCV between its port junctions, setting K (= valve K at the inlet pipe's
  diameter: Crane default via fluids, or K/Cv/Kv by definition, element_laws.valve_k),
  diameter = inlet pipe's end segment; 'isolated' -> CLOSED.
- Check valve, status active (cracking pressure 0) -> merged into its inlet connection (one
  segment): an EPANET CV pipe from the far node to the valve's outlet junction with minor
  loss K_pipe + K_valve (same diameter). locked_open -> TCV(K), locked_closed -> TCV CLOSED.
- PRV / PSV / FCV -> EPANET valve between its port junctions, diameter = inlet pipe's end
  segment, minor loss = K_open (0 when ideal); failed_open / failed_closed -> fixed OPEN /
  CLOSED. PRV/PSV setting = p_set/(ρg) + v²/(2g) with v in the pipe on the held port,
  iterated on EPANET's flow until it changes by < 1e-12 m (TSD §10.1).
- Options: D-W, GPM INP units, accuracy 1e-5, headerror 1e-9 ft, flowchange 1e-12 gpm,
  viscosity multiplier 1 (VISCOS = 1.1e-5 ft²/s); looser headerror / flowchange when EPANET
  cannot meet them (``CRITERIA``).

``pins`` override element states: {element id: 'open' | 'closed' | 'active' | 'running'}; a
flow-controlled pump that is on must have one: 'active', 'max_speed', 'min_speed' or 'no_flow'
('isolated', 'open' and 'running' mean max_speed, 'closed' no_flow). A network with an element
that has no exact EPANET equivalent raises ``UnsupportedError``.
"""

import ctypes
import os
import tempfile
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import wntr
from wntr.epanet.io import InpFile
from wntr.epanet.toolkit import ENepanet

from opensolve_pipe.models.components import (
    AssignedFlow,
    CheckValve,
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
from tests.reference import element_laws as el
from tests.reference.derivations import G, area

# Importing wntr installs a process-wide filter that turns scipy's "Matrix is exactly
# singular" MatrixRankWarning into an exception; the production API never imports wntr, so the
# differential test removes that filter to exercise the solver as it runs in production.
warnings.filters[:] = [
    f
    for f in warnings.filters
    if not (f[0] == "error" and "singular" in str(getattr(f[1], "pattern", "")))
]

FOOT = 0.3048
GPM_PER_CFS = 448.831  # EPANET types.h:68 (internal flow-unit constant)
NU_EPANET = 1.1e-5 * FOOT**2

EN_FLOW, EN_HEAD, EN_INITSTATUS, EN_INITSETTING, EN_PUMP_STATE = 8, 10, 4, 5, 16
EN_ITERATIONS, EN_RELATIVEERROR = 0, 1
RAW = {
    0: "XHEAD",
    1: "TEMPCLOSED",
    2: "CLOSED",
    3: "OPEN",
    4: "ACTIVE",
    5: "XFLOW",
    6: "XFCV",
    7: "XPRESSURE",
}
TRIALS = 200  # EPANET default MaxIter


class UnsupportedError(Exception):
    """The network has an element with no exact EPANET equivalent."""


class EpanetError(Exception):
    """An EPANET toolkit call returned an error code."""


@dataclass
class Layout:
    """Where each project item lives in the EPANET model."""

    node_of_port: dict[str, str] = field(default_factory=dict)  # port key -> EPANET node
    # connection id -> (EPANET link of its first segment, sign: our Q = sign * EPANET Q)
    conn_link: dict[str, tuple[str, int]] = field(default_factory=dict)
    element_link: dict[str, tuple[str, int]] = field(default_factory=dict)  # pump/valve id
    merged_cv: dict[str, str] = field(default_factory=dict)  # check valve id -> connection id
    held_pipe: dict[str, tuple[str, str]] = field(default_factory=dict)  # PRV/PSV -> (conn, end)
    control_run: dict[str, str] = field(default_factory=dict)  # flow-controlled pump -> its run
    fixed_flow: dict[str, float] = field(default_factory=dict)  # active ones -> Q_set (FAQ)
    d_in: dict[str, float] = field(default_factory=dict)
    k_open: dict[str, float] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)


def port_conn(project: Project, key: str) -> tuple[PipeConnection, float, str]:
    """(connection, end segment diameter, end) of the connection on a port; end = 'from'/'to'."""
    for c in project.connections:
        if f"{c.from_component_id}:{c.from_port_id}" == key:
            return c, c.piping.pipes[0].inner_diameter, "from"
        if f"{c.to_component_id}:{c.to_port_id}" == key:
            return c, c.piping.pipes[-1].inner_diameter, "to"
    raise KeyError(key)


CONTROL_RUNS = {
    "active": "active",
    "max_speed": "max_speed",
    "min_speed": "min_speed",
    "no_flow": "no_flow",
    "isolated": "max_speed",
    "open": "max_speed",
    "running": "max_speed",
    "closed": "no_flow",
}
"""Pin of a flow-controlled pump -> the EPANET run standing for it (module docstring)."""


def control_pins(project: Project, states: Mapping[str, str]) -> dict[str, str]:
    """The pins of the flow-controlled pumps that are on: each one's state in ``states`` (ours,
    ``checks.our_states``); one we report without a state (isolated, or no result) at its
    maximum speed, where our solver holds it (rule A0)."""
    return {
        c.id: CONTROL_RUNS.get(states.get(c.id, "isolated"), "max_speed")
        for c in project.components
        if isinstance(c, Pump) and c.control is not None and c.status == "on"
    }


def control_runs(project: Project, pins: Mapping[str, str]) -> dict[str, str]:
    """The run of every flow-controlled pump that is on (``CONTROL_RUNS``), from its pin."""
    runs = {}
    for c in project.components:
        if isinstance(c, Pump) and c.control is not None and c.status == "on":
            pin = pins.get(c.id)
            if pin not in CONTROL_RUNS:
                raise ValueError(
                    f"flow-controlled pump {c.id} needs its state as a pin (got {pin!r}): EPANET"
                    " stands for the state our solver reports (control_pins)"
                )
            runs[c.id] = CONTROL_RUNS[pin]
    return runs


def build_wn(
    project: Project, settings: dict[str, float], pins: Mapping[str, str]
) -> tuple[Any, Layout]:
    fluid = project.fluid
    rho = fluid.density
    if abs(fluid.dynamic_viscosity / rho / NU_EPANET - 1.0) > 1e-12:
        raise UnsupportedError("viscosity")
    wn = wntr.network.WaterNetworkModel()
    o = wn.options.hydraulic
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        o.headloss = "D-W"
    o.inpfile_units = "GPM"
    o.accuracy = 1.0e-5
    o.headerror = 1.0e-9
    o.flowchange = 1.0e-12
    o.viscosity = 1.0
    o.specific_gravity = 1.0
    o.demand_model = "DDA"  # demands taken whatever the pressure (assigned flows, the FAQ pair)
    o.trials = TRIALS
    wn.options.time.duration = 0
    lay = Layout()
    lay.control_run = control_runs(project, pins)
    demand: dict[str, float] = {}  # junction -> base demand (the FAQ substitute's pair)
    for c in project.components:
        if isinstance(c, Pump) and lay.control_run.get(c.id) == "active":
            assert c.control is not None
            lay.fixed_flow[c.id] = c.control.setpoint
            demand[f"{c.id}_suction"] = c.control.setpoint
            demand[f"{c.id}_discharge"] = -c.control.setpoint

    merged_inlet_conn: dict[str, str] = {}  # connection id -> check valve id
    for c in project.components:
        if isinstance(c, CheckValve) and c.status == "active" and pins.get(c.id) is None:
            if c.cracking_pressure != 0.0:
                raise UnsupportedError("cracking pressure")
            conn, _, _ = port_conn(project, f"{c.id}:inlet")
            if len(conn.piping.pipes) != 1:
                raise UnsupportedError("check valve inlet connection with several segments")
            if conn.id in merged_inlet_conn:
                raise UnsupportedError("connection is the inlet of two check valves")
            merged_inlet_conn[conn.id] = c.id

    # nodes
    for c in project.components:
        if isinstance(c, Reservoir):
            head = c.elevation + c.liquid_level + c.surface_pressure / (rho * G)
            wn.add_reservoir(c.id, base_head=head)
            for p in c.ports:
                lay.node_of_port[f"{c.id}:{p.id}"] = c.id
        elif isinstance(c, IdealReferenceNode):
            p = c.ports[0]
            z = c.elevation if p.elevation is None else p.elevation
            wn.add_reservoir(c.id, base_head=z + c.pressure / (rho * G))
            lay.node_of_port[f"{c.id}:{p.id}"] = c.id
        elif isinstance(c, TeeBranch | WyeBranch):
            if c.loss_model != "ideal":
                raise UnsupportedError("crane branch")
            wn.add_junction(c.id, base_demand=0.0, elevation=c.elevation)
            for p in c.ports:
                lay.node_of_port[f"{c.id}:{p.id}"] = c.id
        elif isinstance(c, Plug):
            wn.add_junction(c.id, base_demand=0.0, elevation=c.elevation)
            lay.node_of_port[f"{c.id}:port_1"] = c.id
        elif isinstance(c, AssignedFlow):
            p = c.ports[0]
            z = c.elevation if p.elevation is None else p.elevation
            wn.add_junction(c.id, base_demand=c.flow, elevation=z)
            lay.node_of_port[f"{c.id}:{p.id}"] = c.id
        elif isinstance(c, Pump | IsolationValve | CheckValve | ControlValve):
            for p in c.ports:
                key = f"{c.id}:{p.id}"
                if (
                    isinstance(c, CheckValve)
                    and p.id == "inlet"
                    and c.id in merged_inlet_conn.values()
                ):
                    continue  # merged into the CV pipe
                z = c.elevation if p.elevation is None else p.elevation
                name = f"{c.id}_{p.id}"
                wn.add_junction(name, base_demand=demand.get(name, 0.0), elevation=z)
                lay.node_of_port[key] = name
        else:
            raise UnsupportedError(type(c).__name__)

    # pumps and valves
    curves = {cv.id: cv for cv in project.pump_library}
    for c in project.components:
        if isinstance(c, Pump):
            curve = curves[c.curve_id]
            if curve.points[0].flow != 0.0:
                raise UnsupportedError("curve not starting at Q=0")
            if c.curve_id not in wn.curve_name_list:
                wn.add_curve(c.curve_id, "HEAD", [(p.flow, p.head) for p in curve.points])
            pin = pins.get(c.id)
            closed = c.status == "off" or pin in ("closed", "no_flow")
            speed = c.speed
            run = lay.control_run.get(c.id)
            if run is not None:  # flow-controlled: the run standing for our state
                assert c.control is not None
                closed = run in ("active", "no_flow")
                if run == "min_speed":
                    speed = c.control.min_speed
            wn.add_pump(
                c.id,
                lay.node_of_port[f"{c.id}:suction"],
                lay.node_of_port[f"{c.id}:discharge"],
                pump_type="HEAD",
                pump_parameter=c.curve_id,
                speed=speed,
                initial_status="CLOSED" if closed else "OPEN",
            )
            lay.element_link[c.id] = (c.id, 1)
        elif isinstance(c, IsolationValve | CheckValve | ControlValve):
            _, d_in, _ = port_conn(project, f"{c.id}:inlet")
            lay.d_in[c.id] = d_in
            k = el.valve_k(c.valve_type, c.resistance, d_in)
            lay.k_open[c.id] = k
            pin = pins.get(c.id)
            n1, n2 = f"{c.id}_inlet", f"{c.id}_outlet"
            if isinstance(c, IsolationValve) or (
                isinstance(c, CheckValve) and c.id not in merged_inlet_conn.values()
            ):
                if isinstance(c, IsolationValve):
                    closed = c.status == "isolated"
                else:
                    closed = c.status == "locked_closed" or (
                        c.status == "active" and pin == "closed"
                    )
                if pin == "closed":
                    closed = True
                if k <= 0.0:
                    raise UnsupportedError("zero K isolation/check valve")
                wn.add_valve(
                    c.id,
                    n1,
                    n2,
                    diameter=d_in,
                    valve_type="TCV",
                    minor_loss=0.0,
                    initial_setting=k,
                    initial_status="CLOSED" if closed else "ACTIVE",
                )
                lay.element_link[c.id] = (c.id, 1)
            elif isinstance(c, ControlValve):
                status = {"active": "ACTIVE", "failed_open": "OPEN", "failed_closed": "CLOSED"}[
                    c.status
                ]
                if pin == "open":
                    status = "OPEN"
                elif pin == "closed":
                    status = "CLOSED"
                if c.valve_type == "fcv":
                    setting = c.setpoint
                else:
                    setting = settings.get(c.id, c.setpoint / (rho * G))
                    if status == "ACTIVE":
                        if c.setpoint < 0.0:
                            raise UnsupportedError("negative PRV/PSV setting")
                        held = "outlet" if c.valve_type == "prv" else "inlet"
                        conn, _, end = port_conn(project, f"{c.id}:{held}")
                        lay.held_pipe[c.id] = (conn.id, end)
                wn.add_valve(
                    c.id,
                    n1,
                    n2,
                    diameter=d_in,
                    valve_type=c.valve_type.upper(),
                    minor_loss=k,
                    initial_setting=setting,
                    initial_status=status,
                )
                lay.element_link[c.id] = (c.id, 1)

    # connections
    for conn in project.connections:
        a = f"{conn.from_component_id}:{conn.from_port_id}"
        b = f"{conn.to_component_id}:{conn.to_port_id}"
        segs = conn.piping.pipes
        cv_id = merged_inlet_conn.get(conn.id)
        node_a = lay.node_of_port.get(a)
        node_b = lay.node_of_port.get(b)
        sign = 1
        if cv_id is not None:
            # replace the valve inlet end by the valve outlet node; orient towards the valve
            if a == f"{cv_id}:inlet":
                node_a, node_b = node_b, f"{cv_id}_outlet"
                sign = -1
            else:
                node_b = f"{cv_id}_outlet"
            lay.element_link[cv_id] = (conn.id, 1)  # the CV pipe is oriented toward the valve
            lay.merged_cv[cv_id] = conn.id
        names = [conn.id] if len(segs) == 1 else [f"{conn.id}_s{i}" for i in range(len(segs))]
        chain_nodes = [node_a, *[f"{conn.id}_m{i}" for i in range(1, len(segs))], node_b]
        for n in chain_nodes[1:-1]:
            wn.add_junction(n, base_demand=0.0, elevation=0.0)
        for i, (seg, name) in enumerate(zip(segs, names, strict=True)):
            ml = sum(f.k_override * f.quantity for f in conn.piping.fittings if f.pipe_index == i)
            if any(f.type != "custom" or f.k_override is None for f in conn.piping.fittings):
                raise UnsupportedError("non-custom fitting")
            status = "OPEN"
            if cv_id is not None:
                ml += lay.k_open[cv_id]
                status = "CV"
            wn.add_pipe(
                name,
                chain_nodes[i],
                chain_nodes[i + 1],
                length=seg.length,
                diameter=seg.inner_diameter,
                roughness=seg.roughness,
                minor_loss=ml,
                initial_status=status,
            )
        lay.conn_link[conn.id] = (names[0], sign)
    lay.links = list(wn.link_name_list)
    lay.nodes = list(wn.node_name_list)
    return wn, lay


@dataclass
class EpanetResult:
    flows: dict[str, float]  # connection id -> m³/s (our orientation)
    element_flows: dict[str, float]
    heads: dict[str, float]  # port key -> m
    link_flow: dict[str, float]  # EPANET link -> m³/s (EPANET orientation)
    node_head: dict[str, float]
    raw_status: dict[str, str]  # EPANET link -> raw status name
    iterations: int
    relerr: float
    settings: dict[str, float]
    setting_iterations: int
    warnings: list[str]
    criteria: int = 0
    link_nodes: dict[str, tuple[str, str]] = field(default_factory=dict)


def _solve_inp(
    inp: str,
    links: list[str],
    nodes: list[str],
    tmp: str,
    settings_psi: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, str], dict[str, float], int, float, list[str]]:
    tmp = os.path.abspath(tmp)
    inp = os.path.abspath(inp)
    en = ENepanet(version=2.2)
    # EPANET makes its own scratch files (mkstemp "enXXXXXX") in the working directory, from
    # EN_createproject in ENopen until EN_deleteproject in ENclose, so it runs inside tmp.
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        en.ENopen(inp, os.path.join(tmp, "x.rpt"), os.path.join(tmp, "x.bin"))
        lib, prj = en.ENlib, en._project
        d = ctypes.c_double()
        i = ctypes.c_int()
        try:
            if settings_psi:
                for name, val in settings_psi.items():
                    lib.EN_getlinkindex(prj, name.encode(), ctypes.byref(i))
                    rc = lib.EN_setlinkvalue(prj, i.value, EN_INITSETTING, ctypes.c_double(val))
                    if rc:
                        raise EpanetError(f"setlinkvalue rc={rc}")
            rc = lib.EN_openH(prj)
            if rc:
                raise EpanetError(f"openH rc={rc}")
            rc = lib.EN_initH(prj, 0)
            if rc:
                raise EpanetError(f"initH rc={rc}")
            t = ctypes.c_long()
            rc = lib.EN_runH(prj, ctypes.byref(t))
            warn = []
            if rc >= 100:
                raise EpanetError(f"runH error {rc}")
            if rc:
                warn.append(f"warning {rc}")
            lib.EN_getstatistic(prj, EN_ITERATIONS, ctypes.byref(d))
            iters = int(d.value)
            lib.EN_getstatistic(prj, EN_RELATIVEERROR, ctypes.byref(d))
            relerr = d.value
            lf, rs, nh = {}, {}, {}
            for name in links:
                lib.EN_getlinkindex(prj, name.encode(), ctypes.byref(i))
                lib.EN_getlinkvalue(prj, i.value, EN_FLOW, ctypes.byref(d))
                lf[name] = d.value / GPM_PER_CFS * FOOT**3
                lib.EN_getlinkvalue(prj, i.value, EN_PUMP_STATE, ctypes.byref(d))
                rs[name] = RAW.get(int(d.value), str(d.value))
            for name in nodes:
                lib.EN_getnodeindex(prj, name.encode(), ctypes.byref(i))
                lib.EN_getnodevalue(prj, i.value, EN_HEAD, ctypes.byref(d))
                nh[name] = d.value * FOOT
            lib.EN_closeH(prj)
        finally:
            en.ENclose()
    finally:
        os.chdir(cwd)
    return lf, rs, nh, iters, relerr, warn


CRITERIA = ((1.0e-9, 1.0e-12), (1.0e-7, 1.0e-9), (1.0e-5, 1.0e-6), (0.0, 0.0))
"""(headerror ft, flowchange gpm) ladder: the reference generator's strict extras first; EPANET
cannot always meet them in double precision, so looser ones (accuracy 1e-5 always applies)."""


def run_epanet(
    project: Project, pins: Mapping[str, str] | None = None, workdir: str | None = None
) -> tuple[EpanetResult, Layout]:
    """EPANET's solution with the strictest ``CRITERIA`` level it balances at (its last level's
    unbalanced result otherwise). Each run's temporary directory, in ``workdir`` (the system
    temporary directory by default), holds the INP, the report and EPANET's scratch files."""
    last = None
    for level, (he, fc) in enumerate(CRITERIA):
        res, lay = _run_epanet(project, pins, workdir, he, fc)
        res.criteria = level
        last = (res, lay)
        if res.iterations <= TRIALS:
            return res, lay
    assert last is not None
    return last


def _run_epanet(
    project: Project,
    pins: Mapping[str, str] | None,
    workdir: str | None,
    headerror: float,
    flowchange: float,
) -> tuple[EpanetResult, Layout]:
    pins = pins or {}
    rho = project.fluid.density
    wn, lay = build_wn(project, {}, pins)
    wn.options.hydraulic.headerror = headerror
    wn.options.hydraulic.flowchange = flowchange
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        inp = os.path.join(tmp, "net.inp")
        InpFile().write(inp, wn, units="GPM")
        held = dict(lay.held_pipe)
        comps = {c.id: c for c in project.components}
        settings = {vid: comps[vid].setpoint / (rho * G) for vid in held}

        def psi(m: float) -> float:
            return m / FOOT * 0.4333  # EPANET PSIperFT (SpGrav 1), as WNTR converts

        n_set = 0
        while True:
            lf, rs, nh, iters, relerr, warn = _solve_inp(
                inp, lay.links, lay.nodes, tmp, {k: psi(v) for k, v in settings.items()}
            )
            flows = {cid: s * lf[name] for cid, (name, s) in lay.conn_link.items()}
            new = {}
            for vid, (cid, end) in held.items():
                conn = next(c for c in project.connections if c.id == cid)
                d = conn.piping.pipes[0 if end == "from" else -1].inner_diameter
                v = flows[cid] / area(d)
                new[vid] = comps[vid].setpoint / (rho * G) + v * v / (2.0 * G)
            if all(abs(new[k] - settings[k]) < 1e-12 for k in settings) or n_set >= 60:
                break
            settings = new
            n_set += 1
        if settings and n_set >= 60:
            warn.append("setting iteration did not converge")
    if iters > TRIALS:
        warn.append("unbalanced")
    heads = {key: nh[n] for key, n in lay.node_of_port.items()}
    eflows = {eid: s * lf[name] for eid, (name, s) in lay.element_link.items()}
    for pid, q_set in lay.fixed_flow.items():  # the FAQ substitute: Q_set past a closed pump
        eflows[pid] += q_set
    res = EpanetResult(flows, eflows, heads, lf, nh, rs, iters, relerr, settings, n_set, warn)
    res.link_nodes = {
        name: (wn.get_link(name).start_node_name, wn.get_link(name).end_node_name)
        for name in lay.links
    }
    return res, lay


def element_state(project: Project, lay: Layout, res: EpanetResult) -> dict[str, str]:
    """EPANET final state of every pump and valve in our vocabulary (raw status kept in
    'xfcv'/'xpressure' cases). A flow-controlled pump's is the state its run stands for: active
    and no_flow as imposed, max_speed / min_speed while EPANET's pump runs, else no_flow."""
    out = {}
    for c in project.components:
        if isinstance(c, Pump):
            raw = res.raw_status[c.id]
            run = lay.control_run.get(c.id)
            if c.status == "off":
                out[c.id] = "off"
            elif run is not None:
                running = raw in ("OPEN", "XFLOW") and run not in ("active", "no_flow")
                out[c.id] = run if (running or run == "active") else "no_flow"
            else:
                out[c.id] = "running" if raw in ("OPEN", "XFLOW") else "no_flow"
        elif isinstance(c, IsolationValve | CheckValve | ControlValve):
            name, _ = lay.element_link[c.id]
            raw = res.raw_status[name]
            if raw in ("CLOSED", "TEMPCLOSED", "XHEAD"):
                out[c.id] = "closed"
            elif isinstance(c, ControlValve) and raw == "ACTIVE":
                out[c.id] = "active"
            elif raw == "XPRESSURE":
                out[c.id] = "xpressure"
            elif raw == "XFCV":
                out[c.id] = "xfcv"
            else:
                out[c.id] = "open"
    return out
