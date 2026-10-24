"""Random network generator for the EPANET differential test.

``generate(seed)`` produces a ``Project`` meant to have an exact EPANET equivalent (see
``epanet_model``) for every element: reservoirs and ideal reference nodes, ideal tees and wyes
(EPANET junctions), plugs (dead-end junctions), custom pipes in 1-3 series segments with 'custom'
K fittings, pumps with collinear 4-point curves from Q = 0, isolation valves (TCV), check valves
(CV pipe, cracking pressure 0), and PRV / PSV / FCV (EPANET valves). A connection can still end
up as the inlet of two active check valves, which ``epanet_model`` rejects (class
``unsupported``). The networks run in 'swamee_jain' mode with a custom fluid of EPANET's water
viscosity.

All numbers drawn here are random *test inputs*; no reference value is invented. A network
depends only on its seed and profile (``random.Random(seed)``), so they reproduce it.

Profiles (``PROFILES``):

- ``default``: the network above. Its draws are frozen: the 3,000-seed baseline of TSD §10.4,
  the corpus and the smoke test's pinned classes depend on every seed's network.
- ``flow_control``: the default network of the same seed with 0-2 flow-controlled pumps
  (CLAUDE.md D11, proposal vfd-pump-modes.md §7.4) added by a second generator,
  ``random.Random(f"flow_control:{seed}")``, so the default draws are untouched. An existing
  pump gets a control, or a new pump (its own collinear curve) is inserted in a connection,
  which keeps the original connection's segments on one side and gets one new segment on the
  other: mostly a connection left when dead ends are pruned, so that it can carry flow, half
  the time one between tees, wyes and boundaries only; sometimes in series with the previous
  one, then sometimes with an equal setpoint (no determined state, proposal §4.6), unless that
  setpoint is at or beyond the new pump's maximum speed × x_mono, which the API rejects
  (CONTROLLED_PUMP_SETPOINT). The setpoint is a log-uniform fraction of the curve's largest
  flow at the maximum speed, the minimum speed a uniform fraction of the maximum, so that every
  state (active, max_speed, min_speed, no_flow, off) occurs. Its documented seed range is
  ``FLOW_CONTROL_SEEDS`` (10,000-12,999), disjoint from the default baseline's 0-2,999.
- ``assigned_flow``: the default network of the same seed with 0-4 assigned-flow nodes (SDD
  §4.11, TSD §4.8) added by a third generator, ``random.Random(f"assigned_flow:{seed}")``, so
  the default draws are untouched (and no ``flow_control`` draw is made). A node takes the
  place of a plug at a free tee or wye port, whose dead-end connection it keeps (45 %), or ends
  a new dead-end connection from the free port of a new ideal tee inserted in a connection
  (mostly one left when dead ends are pruned, so that the node's flow passes through the
  network's loops and elements; the connection keeps its segments on one side and gets one new
  segment on the other). One node in four is fed through a flow control in its dead end: an
  FCV (``Gen.element``) or a flow-controlled pump (as in ``flow_control``), facing the node's
  flow four times in five; its flow is then the control's setpoint (two times in five: the
  control and the node fix the same flow, no determined pressure between them, TSD §4.8 "Flow
  controls in series") or a log-uniform 0.3-3 times it, a supply three times in ten.
  Otherwise (a free node) the flow is a log-uniform 0.02-2 m/s in the narrowest segment of the
  node's connection; a demand (out of the network) two times in three, a supply one time in
  four, and 0 (a plug, TSD §4.8) one time in twelve; one free node in five takes minus the
  previous free node's flow, a balanced pair that a closed valve can leave in a floating
  section. Flows are rounded to 6 significant digits (EPANET's INP carries a demand in GPM to
  11). Many of these networks have no steady state by construction (demands behind elements
  that pass no flow towards them, flow controls in series), which the differential test
  expects (``checks.assigned_flow_expectations``). Its documented seed range is
  ``ASSIGNED_FLOW_SEEDS`` (20,000-22,999), disjoint from the other profiles'.

    uv run python -m tests.differential.generator SEED [--profile P]   # print the project JSON
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, field
from typing import Literal

from opensolve_pipe.models.components import (
    Component,
    ControlValve,
    FlowCoefficient,
    IdealReferenceNode,
    Plug,
    Pump,
    PumpControl,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from opensolve_pipe.models.piping import PipeConnection, PipeDefinition
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import element_laws as el
from tests.reference.case_format import (
    assigned_flow,
    check_valve,
    connect,
    control_valve,
    custom_fluid,
    custom_pipe,
    fitting,
    flow_coefficient,
    ideal_tee,
    isolation_valve,
    make_project,
    plug,
    pump,
    pump_curve,
    reference_node,
    reservoir,
    wye,
)
from tests.reference.derivations import G

FOOT = 0.3048
NU_EPANET = 1.1e-5 * FOOT**2  # EPANET VISCOS, types.h:53 (m²/s)

DEFAULT = "default"
FLOW_CONTROL = "flow_control"
ASSIGNED_FLOW = "assigned_flow"
PROFILES = (DEFAULT, FLOW_CONTROL, ASSIGNED_FLOW)
FLOW_CONTROL_SEEDS = range(10_000, 13_000)
"""The documented seed range of the ``flow_control`` profile (TSD §10.4)."""
ASSIGNED_FLOW_SEEDS = range(20_000, 23_000)
"""The documented seed range of the ``assigned_flow`` profile (TSD §10.4)."""

Slot = tuple[str, str, float]  # (component id, port id, elevation)


@dataclass
class Gen:
    rng: random.Random
    components: list[Component] = field(default_factory=list)
    connections: list[PipeConnection] = field(default_factory=list)
    curves: list[PumpCurve] = field(default_factory=list)
    n_conn: int = 0
    n_el: int = 0
    heads: list[float] = field(default_factory=list)  # boundary heads (for setpoints)
    rho: float = 1000.0
    tags: set[str] = field(default_factory=set)
    shutoff_mode: bool = False

    # ------------------------------------------------------------------ pieces
    def pipe_size(self) -> float:
        r = self.rng.random()
        if r < 0.15:
            return self.rng.uniform(0.006, 0.025)  # small bore: laminar / transitional
        if r < 0.55:
            return self.rng.uniform(0.025, 0.1)
        return self.rng.uniform(0.1, 0.4)

    def segments(self, n: int | None = None, d0: float | None = None) -> list[PipeDefinition]:
        n = n or (1 if self.rng.random() < 0.8 else self.rng.randint(2, 3))
        segs = []
        for i in range(n):
            d = d0 if (i == 0 and d0 is not None) else self.pipe_size()
            length = math.exp(self.rng.uniform(math.log(1.0), math.log(1500.0)))
            # roughness: ε/D inside Swamee-Jain's documented 1e-6 .. 5e-2 (mostly)
            ed = math.exp(self.rng.uniform(math.log(2e-6), math.log(2e-2)))
            segs.append(custom_pipe(d, length, ed * d))
        return segs

    def conn(self, a: str, b: str, *, single: bool = False) -> PipeConnection:
        self.n_conn += 1
        cid = f"C{self.n_conn}"
        segs = self.segments(1 if single else None)
        fits = []
        if self.rng.random() < 0.3:
            for _ in range(self.rng.randint(1, 2)):
                fits.append(
                    fitting(
                        "custom",
                        quantity=self.rng.randint(1, 3),
                        pipe_index=self.rng.randrange(len(segs)),
                        k_override=round(self.rng.uniform(0.1, 5.0), 3),
                    )
                )
        c = connect(cid, a, b, segs, fits)
        self.connections.append(c)
        return c

    def resistance(self, p_none: float) -> FlowCoefficient | None:
        if self.rng.random() < p_none:
            return None
        kind = self.rng.choice(["K", "K", "Cv", "Kv"])
        if kind == "K":
            return flow_coefficient("K", round(self.rng.uniform(0.2, 12.0), 3))
        # Cv / Kv sized against a typical pipe: K between ~0.3 and ~30 at d ~ 0.05-0.3 m
        if kind == "Cv":
            cv = math.exp(self.rng.uniform(math.log(5), math.log(5000)))
            return flow_coefficient("Cv", round(cv, 2))
        kv = math.exp(self.rng.uniform(math.log(4), math.log(4300)))
        return flow_coefficient("Kv", round(kv, 2))

    def new_curve(self) -> str:
        cid = f"PC{len(self.curves) + 1}"
        if self.shutoff_mode and self.heads:
            lift = max(self.heads) - min(self.heads)
            h0 = max(1.0, lift * self.rng.uniform(0.85, 1.15))
        else:
            h0 = self.rng.uniform(3.0, 80.0)
        q_end = math.exp(self.rng.uniform(math.log(0.001), math.log(0.25)))
        h_end = h0 * self.rng.uniform(0.0, 0.6)
        slope = (h0 - h_end) / q_end
        pts = [(q_end * i / 3.0, h0 - slope * q_end * i / 3.0) for i in range(4)]
        pts[-1] = (q_end, max(h_end, 0.0))
        self.curves.append(pump_curve(cid, pts))
        return cid

    # ------------------------------------------------------------------ inline elements
    def element(self, kind: str, z: float) -> tuple[str, str, str]:
        """Create an inline two-port element; returns (component id, in port, out port)."""
        self.n_el += 1
        rng = self.rng
        if kind == "pump":
            cid = f"PU{self.n_el}"
            self.tags.add("pump")
            speed = 1.0 if rng.random() < 0.5 else round(rng.uniform(0.6, 1.0), 3)
            status = "off" if rng.random() < 0.08 else "on"
            self.components.append(pump(cid, z, self.new_curve(), speed=speed, status=status))
            return cid, "suction", "discharge"
        if kind == "iso":
            cid = f"IV{self.n_el}"
            self.tags.add("isolation")
            vt = rng.choice(["gate", "ball", "butterfly", "globe"])
            status = "isolated" if rng.random() < 0.12 else "active"
            self.components.append(
                isolation_valve(cid, z, vt, status=status, resistance=self.resistance(0.5))
            )
            return cid, "inlet", "outlet"
        if kind == "check":
            cid = f"CV{self.n_el}"
            self.tags.add("check")
            vt = rng.choice(["check", "stop_check"])
            r = rng.random()
            status = "active" if r < 0.84 else ("locked_open" if r < 0.92 else "locked_closed")
            self.components.append(
                check_valve(cid, z, vt, status=status, resistance=self.resistance(0.6))
            )
            return cid, "inlet", "outlet"
        # control valves
        cid = f"{kind.upper()}{self.n_el}"
        self.tags.add(kind)
        r = rng.random()
        status = "active" if r < 0.86 else ("failed_open" if r < 0.93 else "failed_closed")
        if kind == "fcv":
            d = rng.uniform(0.03, 0.3)
            setpoint = round(rng.uniform(0.1, 2.5) * math.pi * d * d / 4.0, 6)
            setpoint = max(setpoint, 1e-5)
        else:
            lo, hi = (min(self.heads), max(self.heads)) if self.heads else (0.0, 50.0)
            h_target = rng.uniform(lo - 5.0, hi + 5.0)
            p = self.rho * G * (h_target - z)
            setpoint = round(min(max(p, 0.0), 9e5), 1)
        self.components.append(
            control_valve(cid, z, kind, setpoint, status=status, resistance=self.resistance(0.6))
        )
        return cid, "inlet", "outlet"

    def chain(self, a: str, b: str, za: float, zb: float) -> None:
        """Connect port a to port b, possibly through inline elements."""
        rng = self.rng
        r = rng.random()
        kinds: list[str] = []
        if r < 0.5:
            kinds = []
        else:
            pool = ["pump", "pump", "iso", "check", "check", "prv", "prv", "psv", "fcv", "fcv"]
            kinds = [rng.choice(pool)]
            if kinds[0] == "pump" and rng.random() < 0.5:
                kinds.append("check")  # discharge check valve
            elif rng.random() < 0.15:
                kinds.append(rng.choice(pool))
        if not kinds:
            self.conn(a, b)
            return
        cur = a
        prev_kind = None
        for k in kinds:
            z = rng.uniform(min(za, zb) - 2.0, max(za, zb) + 2.0)
            cid, pin, pout = self.element(k, z)
            reverse = rng.random() < 0.3
            first, second = (pout, pin) if reverse else (pin, pout)
            # a check valve's inlet connection is one segment (merged into an EPANET CV pipe);
            # it must not also be another active check valve's inlet connection.
            single = (k == "check") or (prev_kind == "check")
            if rng.random() < 0.5:
                self.conn(cur, f"{cid}:{first}", single=single)
            else:
                self.conn(f"{cid}:{first}", cur, single=single)
            cur = f"{cid}:{second}"
            prev_kind = k
        single = prev_kind == "check"
        if rng.random() < 0.5:
            self.conn(cur, b, single=single)
        else:
            self.conn(b, cur, single=single)


def generate(seed: int, profile: str = DEFAULT) -> Project:
    """The network of ``seed`` in ``profile`` (``PROFILES``; module docstring)."""
    if profile not in PROFILES:
        raise ValueError(f"unknown generator profile {profile!r}; one of {PROFILES}")
    rng = random.Random(seed)
    g = Gen(rng)
    g.rho = round(rng.uniform(800.0, 1200.0), 3) if rng.random() < 0.5 else 1000.0
    g.shutoff_mode = rng.random() < 0.15

    n_tee = rng.randint(1, 9)
    tees: list[tuple[str, float, list[str]]] = []
    for i in range(n_tee):
        z = round(rng.uniform(0.0, 30.0), 3)
        if rng.random() < 0.8:
            t: Component = ideal_tee(f"T{i}", z)
            ports = ["run_inlet", "run_outlet", "branch"]
        else:
            t = wye(f"T{i}", z, rng.choice([30.0, 45.0, 60.0]), loss_model="ideal")
            ports = ["inlet", "outlet_1", "outlet_2"]
        g.components.append(t)
        tees.append((t.id, z, ports))

    # boundaries
    n_bnd = rng.randint(1, min(4, n_tee + 2))
    bnds: list[tuple[str, float, list[str]]] = []
    for i in range(n_bnd):
        if rng.random() < 0.12:
            z = round(rng.uniform(-5.0, 50.0), 3)
            p = round(rng.uniform(-3e4, 4e5), 1)
            rn = reference_node(f"RN{i}", z, p)
            g.heads.append(z + p / (g.rho * G))
            g.components.append(rn)
            bnds.append((rn.id, z, ["port_1"]))
        else:
            z = round(rng.uniform(-5.0, 50.0), 3)
            level = round(rng.uniform(0.5, 10.0), 3)
            sp = 0.0 if rng.random() < 0.75 else round(rng.uniform(-3e4, 3e5), 1)
            used = sum(len(b[2]) for b in bnds)
            nports = 2 if (rng.random() < 0.1 and used + 2 <= n_tee + 2 - (n_bnd - i - 1)) else 1
            ports = [f"port_{k + 1}" for k in range(nports)]
            rv = reservoir(f"R{i}", z, level, surface_pressure=sp, ports=ports)
            g.heads.append(z + level + sp / (g.rho * G))
            g.components.append(rv)
            bnds.append((rv.id, z, ports))

    # slots: grow a tree of tees, then attach the boundaries, then close loops and plug the rest
    free: list[Slot] = []
    order = list(tees)
    rng.shuffle(order)
    free += [(order[0][0], p, order[0][1]) for p in order[0][2]]
    edges: list[tuple[Slot, Slot]] = []
    for t_id, t_z, t_ports in order[1:]:
        # attach one port of the new tee to a free slot of a placed tee
        idx = rng.randrange(len(free))
        slot = free.pop(idx)
        ports = list(t_ports)
        rng.shuffle(ports)
        edges.append((slot, (t_id, ports[0], t_z)))
        free += [(t_id, p, t_z) for p in ports[1:]]
    bnd_slots = [(b[0], p, b[1]) for b in bnds for p in b[2]]
    for bs in bnd_slots:
        if free:
            slot = free.pop(rng.randrange(len(free)))
            edges.append((bs, slot))
        else:  # no free tee port
            raise ValueError("ran out of slots")
    # remaining tee slots: pair (no self loops), dead ends -> plugs
    rng.shuffle(free)
    while len(free) >= 2:
        a = free.pop()
        partner = next((i for i, s in enumerate(free) if s[0] != a[0]), None)
        if partner is None or rng.random() < 0.12:
            pid = f"PL{len(g.components)}"
            g.components.append(plug(pid, a[2]))
            edges.append((a, (pid, "port_1", a[2])))
            continue
        b = free.pop(partner)
        edges.append((a, b))
    for a in free:
        pid = f"PL{len(g.components)}"
        g.components.append(plug(pid, a[2]))
        edges.append((a, (pid, "port_1", a[2])))

    for a, b in edges:
        ka, kb = f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}"
        if b[0].startswith("PL"):
            g.conn(ka, kb)  # plain dead-end pipe to a plug
        elif rng.random() < 0.5:
            g.chain(ka, kb, a[2], b[2])
        else:
            g.chain(kb, ka, b[2], a[2])

    pid, name = f"fuzz-{seed}", f"Fuzz network {seed}"
    if profile == FLOW_CONTROL:  # every default draw is made above: the default is unchanged
        add_flow_controls(g, seed)
        pid, name = f"fuzz-flow-control-{seed}", f"Fuzz network {seed} (flow control)"
    elif profile == ASSIGNED_FLOW:  # likewise
        add_assigned_flows(g, seed)
        pid, name = f"fuzz-assigned-flow-{seed}", f"Fuzz network {seed} (assigned flow)"
    fluid = custom_fluid("EPANET water nu", g.rho, NU_EPANET * g.rho)
    return make_project(
        pid,
        name,
        fluid,
        g.components,
        g.connections,
        friction_method="swamee_jain",
        pump_library=g.curves,
    )


# --------------------------------------------------------------------------- flow_control profile


def with_control(p: Pump, control: PumpControl) -> Pump:
    """``p`` speed-controlled, validated (control.minSpeed < speed)."""
    return Pump.model_validate({**p.model_dump(), "control": control.model_dump()})


def flow_control(rng: random.Random, curve: PumpCurve, speed: float) -> PumpControl:
    """A flow control for a pump on ``curve`` at maximum speed ``speed``: setpoint a
    log-uniform fraction (0.001-1.2) of the curve's largest flow at that speed (the fuzz
    networks' pumps mostly run far below it), to 6 significant digits, which the EPANET INP
    writes exactly; minimum speed a uniform fraction (0.1-0.9) of the maximum, to 3 decimals.
    Random test inputs, as everything here."""
    q_end = curve.points[-1].flow
    q_set = speed * q_end * math.exp(rng.uniform(math.log(0.001), math.log(1.2)))
    q_set = float(f"{max(q_set, 1.0e-6):.6g}")
    min_speed = round(speed * rng.uniform(0.1, 0.9), 3)
    return PumpControl(mode="flow", setpoint=q_set, min_speed=min_speed)


def through_connections(g: Gen) -> tuple[list[int], list[int]]:
    """(core, free): indices of the connections left when dead ends are pruned (repeatedly
    removing a component other than a reservoir or reference node with one connection), where
    a pump can carry flow between fixed heads unless valves close the way; and those of them
    between tees, wyes and boundaries only (no pump or valve at either end)."""
    boundaries = {c.id for c in g.components if isinstance(c, Reservoir | IdealReferenceNode)}
    alive = set(range(len(g.connections)))
    while True:
        degree: dict[str, int] = {}
        for i in alive:
            c = g.connections[i]
            for cid in (c.from_component_id, c.to_component_id):
                degree[cid] = degree.get(cid, 0) + 1
        leaves = {cid for cid, n in degree.items() if n == 1 and cid not in boundaries}
        dead = {
            i
            for i in alive
            if {g.connections[i].from_component_id, g.connections[i].to_component_id} & leaves
        }
        if not dead:
            break
        alive -= dead
    inline = {c.id for c in g.components if not isinstance(c, TeeBranch | WyeBranch)} - boundaries
    core = sorted(alive)
    free = [
        i
        for i in core
        if not {g.connections[i].from_component_id, g.connections[i].to_component_id} & inline
    ]
    return core, free


def add_flow_controls(g: Gen, seed: int) -> None:
    """The ``flow_control`` profile (module docstring): 0-2 flow-controlled pumps drawn from
    ``random.Random(f"flow_control:{seed}")``, after every draw of the default network."""
    rng = random.Random(f"{FLOW_CONTROL}:{seed}")
    g.rng = rng  # new curves and connections draw from the profile's generator
    curves = {c.id: c for c in g.curves}
    elevation = {c.id: c.elevation for c in g.components}
    # the last inserted pump: (its id, its port on the new connection, that connection's id)
    last: tuple[str, str, str] | None = None
    last_setpoint = 0.0
    for _ in range(rng.choices([0, 1, 2], weights=[1, 5, 4])[0]):
        fixed = [i for i, c in enumerate(g.components) if isinstance(c, Pump) and c.control is None]
        if fixed and rng.random() < 0.4:  # an existing pump gets a control
            i = rng.choice(fixed)
            p = g.components[i]
            assert isinstance(p, Pump)
            g.components[i] = with_control(p, flow_control(rng, curves[p.curve_id], p.speed))
            last = None
            continue
        g.n_el += 1
        cid = f"PU{g.n_el}"
        g.tags.add("pump")
        speed = 1.0 if rng.random() < 0.5 else round(rng.uniform(0.6, 1.0), 3)
        status = "off" if rng.random() < 0.08 else "on"
        curve_id = g.new_curve()
        curves[curve_id] = g.curves[-1]
        control = flow_control(rng, curves[curve_id], speed)
        if last is not None and rng.random() < 0.3:
            # in series with the last one, through the connection on its second port; the same
            # flow direction (four in five), its port facing the last pump the other kind
            prev_id, prev_port, conn_id = last
            idx = next(i for i, c in enumerate(g.connections) if c.id == conn_id)
            facing = "suction" if prev_port == "discharge" else "discharge"
            if g.connections[idx].from_component_id == prev_id:
                reverse = facing == "discharge"  # the new pump's first port faces it
            else:
                reverse = facing == "suction"  # its second port faces it
            if rng.random() < 0.2:
                reverse = not reverse
            elif rng.random() < 0.3 and last_setpoint < speed * el.x_mono(curves[curve_id]):
                # equal setpoints: no determined state (proposal §4.6); the pump keeps its own
                # drawn setpoint where the copy would be at or beyond s_max x_mono, which the
                # API rejects (CONTROLLED_PUMP_SETPOINT), decided after the draws so that every
                # other seed's network is unchanged
                control = control.model_copy(update={"setpoint": last_setpoint})
        else:
            # mostly where it can carry flow; next to other elements too (status interactions)
            core, free = through_connections(g)
            r = rng.random()
            pool = free if (r < 0.5 and free) else core if (r < 0.85 and core) else []
            idx = pool[rng.randrange(len(pool))] if pool else rng.randrange(len(g.connections))
            reverse = rng.random() < 0.3
        conn = g.connections[idx]
        za, zb = elevation[conn.from_component_id], elevation[conn.to_component_id]
        z = rng.uniform(min(za, zb) - 2.0, max(za, zb) + 2.0)
        new_pump = pump(cid, z, curve_id, speed=speed, status=status)
        g.components.append(with_control(new_pump, control))
        elevation[cid] = z
        first, second = ("discharge", "suction") if reverse else ("suction", "discharge")
        # the connection keeps its 'from' end and its segments and now ends at the pump; one
        # new single-segment connection joins the pump's other port to the old 'to' end (a
        # check valve's inlet connection stays one segment, as epanet_model needs)
        far = f"{conn.to_component_id}:{conn.to_port_id}"
        g.connections[idx] = conn.model_copy(update={"to_component_id": cid, "to_port_id": first})
        if rng.random() < 0.5:
            new = g.conn(f"{cid}:{second}", far, single=True)
        else:
            new = g.conn(far, f"{cid}:{second}", single=True)
        last, last_setpoint = (cid, second, new.id), control.setpoint


# --------------------------------------------------------------------------- assigned_flow profile


def free_flow(rng: random.Random, d: float) -> float:
    """A free node's flow (module docstring): a log-uniform 0.02-2 m/s in diameter d, to 6
    significant digits, out of the network (positive) two times in three, into it (negative)
    one time in four, and 0 one time in twelve. Random test inputs, as everything here."""
    r = rng.random()
    if r < 1.0 / 12.0:
        return 0.0
    v = math.exp(rng.uniform(math.log(0.02), math.log(2.0)))
    q = float(f"{v * math.pi * d * d / 4.0:.6g}")
    return q if r < 0.75 else -q


def controlled_flow(rng: random.Random, setpoint: float) -> float:
    """The magnitude of a node's flow behind a flow control of this setpoint: the setpoint two
    times in five (over-controlled), else a log-uniform 0.3-3 times it, to 6 significant
    digits."""
    if rng.random() < 0.4:
        return setpoint
    return float(f"{setpoint * math.exp(rng.uniform(math.log(0.3), math.log(3.0))):.6g}")


def add_assigned_flows(g: Gen, seed: int) -> None:
    """The ``assigned_flow`` profile (module docstring): 0-4 assigned-flow nodes drawn from
    ``random.Random(f"assigned_flow:{seed}")``, after every draw of the default network."""
    rng = random.Random(f"{ASSIGNED_FLOW}:{seed}")
    g.rng = rng  # new curves, elements and connections draw from the profile's generator
    elevation = {c.id: c.elevation for c in g.components}
    previous = 0.0  # the last free node's flow (for a balanced pair)

    def link(a: str, b: str) -> PipeConnection:
        return g.conn(a, b) if rng.random() < 0.5 else g.conn(b, a)

    for k in range(1, rng.choices([0, 1, 2, 3, 4], weights=[1, 4, 4, 2, 1])[0] + 1):
        af = f"AF{k}"
        plugs = [i for i, c in enumerate(g.components) if isinstance(c, Plug)]
        dead_end: PipeConnection | None = None  # the connection kept from a plug
        if plugs and rng.random() < 0.45:  # in a plug's place, its dead-end connection kept
            i = rng.choice(plugs)
            plug_id, z = g.components[i].id, g.components[i].elevation
            g.components.pop(i)
            ci = next(
                j
                for j, c in enumerate(g.connections)
                if plug_id in (c.from_component_id, c.to_component_id)
            )
            dead_end = g.connections[ci]
            end = "to" if dead_end.to_component_id == plug_id else "from"
        else:  # a new ideal tee in a connection, mostly one left when dead ends are pruned
            core, _ = through_connections(g)
            if core and rng.random() < 0.8:
                ci = core[rng.randrange(len(core))]
            else:
                ci = rng.randrange(len(g.connections))
            conn = g.connections[ci]
            za, zb = elevation[conn.from_component_id], elevation[conn.to_component_id]
            z = round(rng.uniform(min(za, zb), max(za, zb)), 3)
            tee = f"TA{k}"
            ports = ["run_inlet", "run_outlet", "branch"]
            rng.shuffle(ports)
            g.components.append(ideal_tee(tee, z))
            elevation[tee] = z
            far = f"{conn.to_component_id}:{conn.to_port_id}"
            g.connections[ci] = conn.model_copy(
                update={"to_component_id": tee, "to_port_id": ports[0]}
            )
            if rng.random() < 0.5:  # one segment: a check valve's inlet connection stays one
                g.conn(f"{tee}:{ports[1]}", far, single=True)
            else:
                g.conn(far, f"{tee}:{ports[1]}", single=True)
            attach = f"{tee}:{ports[2]}"
        r = rng.random()
        if r < 0.25:  # fed through a flow control: an FCV or a flow-controlled pump
            zc = rng.uniform(z - 2.0, z + 2.0)
            if r < 0.125:
                cid, first, second = g.element("fcv", zc)
                fcv = g.components[-1]
                assert isinstance(fcv, ControlValve)
                setpoint = fcv.setpoint
            else:
                g.n_el += 1
                cid, first, second = f"PU{g.n_el}", "suction", "discharge"
                g.tags.add("pump")
                speed = 1.0 if rng.random() < 0.5 else round(rng.uniform(0.6, 1.0), 3)
                status: Literal["on", "off"] = "off" if rng.random() < 0.08 else "on"
                curve_id = g.new_curve()
                control = flow_control(rng, g.curves[-1], speed)
                new_pump = pump(cid, zc, curve_id, speed=speed, status=status)
                g.components.append(with_control(new_pump, control))
                setpoint = control.setpoint
            elevation[cid] = zc
            q = controlled_flow(rng, setpoint)
            supply = rng.random() < 0.3
            facing = rng.random() < 0.8  # its forward direction is the node's flow
            if supply == facing:  # forward away from the node: its second port on the network
                first, second = second, first
            near = f"{cid}:{first}"  # the control's port on the network side
            if dead_end is not None:
                g.connections[ci] = dead_end.model_copy(
                    update={f"{end}_component_id": cid, f"{end}_port_id": first}
                )
            else:
                link(attach, near)
            link(f"{cid}:{second}", f"{af}:port_1")
            flow = -q if supply else q
        else:  # a free node
            if dead_end is not None:
                g.connections[ci] = dead_end.model_copy(
                    update={f"{end}_component_id": af, f"{end}_port_id": "port_1"}
                )
                pipes = dead_end.piping.pipes
            else:
                pipes = link(attach, f"{af}:port_1").piping.pipes
            if previous != 0.0 and rng.random() < 0.2:
                flow = -previous  # a balanced pair
            else:
                d = min(p.inner_diameter for p in pipes if p.inner_diameter is not None)
                flow = free_flow(rng, d)
            previous = flow
        g.components.append(assigned_flow(af, z, flow))
        elevation[af] = z


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.generator",
        description="Print one differential-test network's project JSON (TSD §10.4).",
    )
    parser.add_argument("seed", type=int, nargs="?", default=0, help="generator seed")
    parser.add_argument(
        "--profile", choices=PROFILES, default=DEFAULT, help="generator profile (default: default)"
    )
    args = parser.parse_args(argv)
    project = generate(args.seed, args.profile)
    print(json.dumps(project.model_dump(mode="json", by_alias=True, exclude_none=True), indent=1))


if __name__ == "__main__":
    main()
