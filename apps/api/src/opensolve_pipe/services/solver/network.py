"""Solver network: nodes (component ports) and links (connections and component internals).

Every node's unknown is the energy grade line H = z + p/(ρg) + v²/(2g) (design §1.1). Every
link has a law h(Q) with h = H_start − H_end for flow Q > 0 from start to end (§2).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from ...models.results import Flag


class LinkLaw(Protocol):
    """Head loss h(Q) [m] and its slope dh/dQ [s/m²], h positive in the direction of Q."""

    def evaluate(self, flow: float) -> tuple[float, float]: ...


class LinkKind(StrEnum):
    CONNECTION = "connection"
    PUMP = "pump"
    VALVE = "valve"
    BRANCH_LEG = "branch_leg"


class LinkMode(Enum):
    """How a link enters one inner (GGA) solve; set by the outer loop (design §4)."""

    NORMAL = "normal"
    """The link's law h(Q) applies (or the state's override, ``LinkState.law``)."""
    CLOSED = "closed"
    """No flow; the link is left out of the network for this solve."""
    FIXED_FLOW = "fixed_flow"
    """Active FCV, or a speed-controlled pump holding its flow setpoint (CLAUDE.md D11): the
    flow is ``value`` (m³/s), a demand at the start node and a supply at the end node; the link
    carries no energy equation and does not connect heads."""
    FIXED_DOWNSTREAM_HEAD = "fixed_downstream_head"
    """Active PRV: the end node is held at the setpoint head (see ``LinkState.head``) for this
    solve, and the link passes whatever flow leaves the end node through its other links."""
    FIXED_UPSTREAM_HEAD = "fixed_upstream_head"
    """Active PSV: the start node is held at the setpoint head, and the link passes whatever
    flow reaches the start node through its other links."""


HEAD_FIXING_MODES = (LinkMode.FIXED_DOWNSTREAM_HEAD, LinkMode.FIXED_UPSTREAM_HEAD)
SPECIAL_MODES = (LinkMode.FIXED_FLOW, *HEAD_FIXING_MODES)
"""Modes in which a link is not a Newton unknown: its flow follows from the setpoint."""


@dataclass(frozen=True)
class LinkState:
    mode: LinkMode = LinkMode.NORMAL
    value: float = 0.0
    """FIXED_FLOW: the flow, m³/s. FIXED_*_HEAD: the static part of the setpoint head,
    z + p_set/(ρg), m. Unused by NORMAL and CLOSED."""
    reference_link: int = -1
    """FIXED_*_HEAD: the link whose flow Q_ref sets the velocity head at the held port."""
    coefficient: float = 0.0
    """FIXED_*_HEAD: 1/(2 g A²) of the held port's connected pipe end segment, s²/m⁵."""
    law: LinkLaw | None = None
    """NORMAL only: the law that applies for this solve in place of the link's own
    (``law_of``), e.g. a speed-controlled pump at its minimum speed (CLAUDE.md D11). None: the
    link's own law. The network itself is never changed, so a solve's states carry everything
    that differs between solves."""

    def head(self, flows: Sequence[float] | NDArray[np.float64]) -> float:
        """Setpoint head H_set = value + coefficient · Q_ref² (EGL, so it includes the port's
        velocity head; design §5.3), with Q_ref from ``flows`` (lagged by the caller)."""
        if self.reference_link < 0 or self.coefficient == 0.0:
            return self.value
        q = float(flows[self.reference_link])
        return self.value + self.coefficient * q * q


NORMAL = LinkState()
CLOSED = LinkState(LinkMode.CLOSED)


@dataclass
class SolverNode:
    index: int
    key: str
    """'componentId:portId', or 'componentId:#center' for a branch's internal node."""
    component_id: str
    port_id: str | None
    """None for internal nodes, which never appear in results."""
    elevation: float
    fixed_head: float | None = None
    """EGL held by a boundary (reservoir or reference-node port), m; None for free nodes."""
    demand: float = 0.0
    """Flow leaving the network at this node, m³/s (negative: entering): an assigned-flow
    node's port (TSD §4.8); 0 at every other node. Never set on a fixed-head node."""


@dataclass
class SolverLink:
    index: int
    key: str
    kind: LinkKind
    start: int
    end: int
    law: LinkLaw
    initial_flow: float = 0.0
    connection_id: str | None = None
    component_id: str | None = None
    port_id: str | None = None
    """For a branch leg: the port the leg runs to (legs run center -> port)."""


@dataclass
class SolverNetwork:
    nodes: list[SolverNode]
    links: list[SolverLink]
    node_index: dict[str, int]
    flags: list[Flag] = field(default_factory=list)
    """Flags known before solving (e.g. a reservoir port above the liquid level)."""


def law_of(link: SolverLink, state: LinkState) -> LinkLaw:
    """The law a NORMAL link follows in a solve: the state's override, else its own."""
    return state.law if state.law is not None else link.law
