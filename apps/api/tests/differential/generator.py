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
depends only on its seed (``random.Random(seed)``), so a seed reproduces it.

    uv run python -m tests.differential.generator SEED     # print the project JSON
"""

import json
import math
import random
import sys
from dataclasses import dataclass, field

from opensolve_pipe.models.components import Component, FlowCoefficient
from opensolve_pipe.models.piping import PipeConnection, PipeDefinition
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference.case_format import (
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


def generate(seed: int) -> Project:
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

    fluid = custom_fluid("EPANET water nu", g.rho, NU_EPANET * g.rho)
    return make_project(
        f"fuzz-{seed}",
        f"Fuzz network {seed}",
        fluid,
        g.components,
        g.connections,
        friction_method="swamee_jain",
        pump_library=g.curves,
    )


if __name__ == "__main__":
    project = generate(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    print(json.dumps(project.model_dump(mode="json", by_alias=True, exclude_none=True), indent=1))
