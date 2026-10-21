"""Solver network: nodes (component ports) and links (connections and component internals).

Every node's unknown is the energy grade line H = z + p/(ρg) + v²/(2g) (design §1.1). Every
link has a law h(Q) with h = H_start − H_end for flow Q > 0 from start to end (§2).
"""

from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Protocol

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
    """How a link enters one inner (GGA) solve; set by the outer loop (design §4).

    M3 adds FIXED_FLOW (active FCV), FIXED_DOWNSTREAM_HEAD (active PRV) and
    FIXED_UPSTREAM_HEAD (active PSV); their setpoint travels in ``LinkState.value``.
    """

    NORMAL = "normal"
    """The link's law h(Q) applies."""
    CLOSED = "closed"
    """No flow; the link is left out of the network for this solve."""


@dataclass(frozen=True)
class LinkState:
    mode: LinkMode = LinkMode.NORMAL
    value: float = 0.0
    """Setpoint for the fixed modes (m³/s or m); unused by NORMAL and CLOSED."""


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
