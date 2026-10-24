"""Compare two corpus dumps (``corpus.py``), exactly or within tolerances.

    uv run python -m tests.differential.compare A B [--ignore PATH ...] [--ignore-null PATH ...]
                                                    [--within-tolerance [--fixed-point]]
                                                    [--group NAME=VALUE[,NAME=VALUE ...]]

For every A/<project>.json (files starting with '_' are skipped) the JSON of B/<project>.json
must be equal, ignoring ``timestamp``; numbers compare with ==, NaN equal to NaN. Prints
"identical N, different M", the projects missing from either side, and up to 25 different
projects with their number of numeric differences, the largest relative one and the first three
other differences (keys, list lengths, values). A file that cannot be read or parsed (a dump cut
short, for example) is listed as unreadable and counts as different. Exit status 1 when a
project differs.

``--ignore PATH`` (repeatable) leaves out the values at a path of the dump, whatever they are:
its dict keys and list indices from the root, separated by '.', each segment matched as an
``fnmatch`` pattern (``*`` matches any one key or index), the whole path at the same depth. A key
present on one side only is also left out there. ``--ignore-null PATH`` (repeatable, the same
paths) leaves out a value only where it is null or absent on both sides; anywhere else the path
is compared as usual, so a key that one side lacks and the other holds with a value that is not
null is a difference. For example, a solver change that adds the new field ``control`` (null
unless the pump is speed-controlled) to every pump result and changes the method version
(proposal vfd-pump-modes.md §7.5) is compared with ``--ignore-null 'pumpResults.*.control'
--ignore methodVersion --ignore trace.methods.methodVersion``: a pump of the old corpus that
gained a control result shows. Each path's count of values left out, and in how many projects,
is printed after the totals, so that an ignore broader than intended shows.

``--within-tolerance`` compares the numbers of each project within tolerances instead, for a
solver change that moves results by its convergence error (proposal
vfd-slice2-discharge-pressure.md §2.7, the acceptance criteria of its change set C1, approved by
the owner as Q5 (a)). Keys and list lengths compare as in the exact mode, and so do booleans,
nulls, integers (indexes, counts), numbers under a key ending in 'Index' (a flag's
``segmentIndex`` and ``fittingIndex``, floats in the dumps since ``Flag.details`` holds floats)
and strings without whitespace (ids, statuses, states, flag codes, port keys); a string with
whitespace (a message, note, equation or methods item) compares
exactly once every number in it is masked (``mask``). A float compares by the quantity its key
names (``Judge.quantity``), within the tolerances of §2.7's table (``DEFAULT_SETTINGS``):

- flow (``flow``, ``outflow``, ``operatingFlow``, ``portFlows.*``, ``portOutflows.*``, the flows
  of pump and system curves, flag details' ``flow``, trace values in m³/s):
  10⁻⁸ × the project's largest |flow| + 10⁻¹⁴ m³/s, the largest flow being that of a connection,
  valve, pump, or branch or boundary port of the main solve, on either side (``element_flows``);
- head (EGL, HGL, head losses, head rises, NPSH, pump-curve heads, the heads of flag details,
  trace values in m but for diameters, roughnesses, lengths, elevations and levels): 10⁻⁶ m;
- pressure (static, absolute, dynamic and total pressures, pressure drops, the atmospheric and
  vapor pressure, trace values in Pa): ρg·10⁻⁶ m, with the dump's fluid density and
  g = 9.80665 m/s² (``G``);
- speed (``speed``, ``maxSpeed``, ``minSpeed``, dimensionless trace values named for a speed):
  10⁻⁹ relative;
- system-curve head: 10⁻⁸ relative or 10⁻⁶ m, whichever is looser;
- every other number: 10⁻⁶ relative, where its element (the connection, component or port the
  value belongs to: the result it is in, the trace element, or a flag's connection, port or
  component; a branch or boundary component by the least of its port flows) carries more than
  10⁻⁹ × the largest flow on both sides. Where it carries no more on a side, the number is
  round-off and excluded (K_eff of a valve that is all but closed, f = 64/Re at Re ≈ 10⁻⁷, the
  K of a tee path while a leg is dead): such a flow lies within the converged solve's flow
  resolution, its continuity tolerance of 10⁻⁹ × the largest flow + 10⁻¹⁴ m³/s (TSD §5.2), and
  one below ``ZERO_FLOW_RTOL`` × the largest flow + 10⁻¹⁴ m³/s is reported as exactly 0. The
  excluded numbers are counted, those of an element whose flow is reported as 0 on a side apart
  from the others, with the largest relative difference among them. A number of no element (the
  fluid's properties) is always compared.

``--fixed-point`` (with ``--within-tolerance``) uses the tolerances of §2.7 criterion 7 instead,
for two dumps solved at a tight solver tolerance (``corpus.py --solver-options
tolerance=1e-13,max_iterations=1000``): flows 10⁻¹¹ × the largest flow; heads, system-curve heads
among them, 10⁻⁸ m or 10⁻¹¹ relative, whichever is looser; pressures the same as heads of ρg;
speeds 10⁻¹¹ relative (``FIXED_POINT``). Criterion 7 names no other quantity, so every other
number keeps the table's 10⁻⁶ relative and its round-off exclusion.

The within-tolerance report prints "identical N, within tolerance M, different K" (different: a
number out of tolerance, any other difference, or an unreadable file; exit status 1 when K > 0),
the ignore counts as above, the tolerances in use, the largest |Δ|/tolerance of each quantity
over the numbers that differ (with its project and path), the round-off exclusions, every
project that did not converge or did not solve on a side (each side's convergence message or
error and its largest energy residual, so that a stall at the solver's energy tolerance shows),
and every different project, in name order, with its numbers out of tolerance (their count and
the worst) and its first ten other differences (a text as its masked form from just before its
first difference; a value of an element with that element's |flow| on each side, for §2.7
criterion 4).

``--group NAME=VALUE[,NAME=VALUE ...]`` (either mode) also prints these counts for the projects
whose dump, on either side, traces an element with all of these inputs (the ``name`` and the
``value`` as text of ``trace.elements.*.inputs``) and for the others: ``--group 'Valve type=prv,
Status=active'`` counts apart the projects with a PRV whose status is ``active`` (§2.7
criterion 1).
"""

import argparse
import fnmatch
import json
import math
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

IGNORE = {"timestamp"}
"""Keys left out at any depth."""

MISSING = object()
"""The value of a key one side does not have."""

Difference = tuple[Any, ...]  # (kind, path, a, b[, relative difference or ratio, quantity])
Pattern = tuple[str, ...]  # an --ignore or --ignore-null path, split on '.'
Leaf = Callable[[tuple[str, ...], str, Any, Any, list[Difference]], None]


class Ignore(NamedTuple):
    """A path left out of the comparison (module docstring)."""

    pattern: Pattern
    null: bool = False
    """--ignore-null: left out only where the value is null or absent on both sides."""

    def __str__(self) -> str:
        return ".".join(self.pattern) + (" (null or absent)" if self.null else "")


def ignored(segments: tuple[str, ...], rules: Sequence[Ignore], a: Any, b: Any) -> Ignore | None:
    """The first rule that leaves out the values a and b (``MISSING`` when a side does not have
    the key) at this path: its pattern matches the whole path, and for --ignore-null both are
    null or absent. None: compare them."""
    for rule in rules:
        if rule.null and not all(v is None or v is MISSING for v in (a, b)):
            continue
        if len(rule.pattern) == len(segments) and all(
            fnmatch.fnmatchcase(seg, pat) for seg, pat in zip(segments, rule.pattern, strict=True)
        ):
            return rule
    return None


def exact_leaf(segments: tuple[str, ...], path: str, a: Any, b: Any, out: list[Difference]) -> None:
    """The exact comparison of two values that are not both dicts or both lists."""
    if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        if a != b and not (isinstance(a, float) and math.isnan(a) and math.isnan(b)):
            rel = abs(a - b) / max(abs(a), abs(b), 1e-300)
            out.append(("num", path, a, b, rel))
    elif a != b:
        out.append(("val", path, a, b))


def walk(
    a: Any,
    b: Any,
    path: str,
    out: list[Difference],
    segments: tuple[str, ...] = (),
    rules: Sequence[Ignore] = (),
    hits: dict[Ignore, int] | None = None,
    leaf: Leaf = exact_leaf,
) -> None:
    """Differences between a and b (``path`` for display); values that one of ``rules`` leaves
    out (``ignored``) are counted in ``hits``; ``leaf`` compares two values that are not both
    dicts or both lists."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in IGNORE:
                continue
            rule = ignored((*segments, k), rules, a.get(k, MISSING), b.get(k, MISSING))
            if rule is not None:
                if hits is not None:
                    hits[rule] = hits.get(rule, 0) + 1
                continue
            if k not in a or k not in b:
                out.append(("key", path + "/" + k, a.get(k, "<missing>"), b.get(k, "<missing>")))
                continue
            walk(a[k], b[k], path + "/" + k, out, (*segments, k), rules, hits, leaf)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(("len", path, len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            rule = ignored((*segments, str(i)), rules, x, y)
            if rule is not None:
                if hits is not None:
                    hits[rule] = hits.get(rule, 0) + 1
                continue
            walk(x, y, f"{path}[{i}]", out, (*segments, str(i)), rules, hits, leaf)
    else:
        leaf(segments, path, a, b, out)


# --------------------------------------------------------------------------- within tolerance

ZERO_FLOW_RTOL = 1.0e-12
"""The solver's reported zero flow: a flow below ZERO_FLOW_RTOL × the largest flow + 10⁻¹⁴ m³/s
is reported as exactly 0 (TSD §5.2 "Reported zero flow", and every dump's methods summary; the
solver's ``ZERO_FLOW_RTOL``, which this module does not import, since it compares the dumps of
two trees). The round-off exclusion counts apart the numbers of an element reported as 0 on a
side, that is below this scale (``Judge.leaf``)."""

G = 9.80665
"""Standard gravity, m/s² (a defined value, 3rd CGPM, 1901): the g of every trace
("Gravitational acceleration g", fluids.constants.g)."""


@dataclass(frozen=True)
class Tolerances:
    """The within-tolerance mode's tolerances, by quantity (module docstring)."""

    flow: float
    """× the project's largest |flow|."""
    flow_floor: float
    """m³/s, added to the flow tolerance."""
    head: float
    """m."""
    head_rel: float
    """Relative; a head's tolerance is the looser of ``head`` and this, a pressure's ρg times."""
    speed: float
    """Relative."""
    curve_head: float
    """m, of a system-curve head."""
    curve_head_rel: float
    """Relative; a system-curve head's tolerance is the looser of the two."""
    other: float
    """Relative, of every other number."""
    round_off: float
    """× the largest flow: an element carrying at most this has its other numbers excluded."""

    def describe(self) -> list[str]:
        def looser(atol: float, rtol: float) -> str:
            return (
                f"{atol:g} m or {rtol:g} relative, whichever is looser" if rtol else f"{atol:g} m"
            )

        return [
            f"flow {self.flow:g} × the project's largest |flow| + {self.flow_floor:g} m³/s",
            f"head {looser(self.head, self.head_rel)}",
            f"pressure ρg × (head {looser(self.head, self.head_rel)})",
            f"speed {self.speed:g} relative",
            f"system-curve head {looser(self.curve_head, self.curve_head_rel)}",
            f"other {self.other:g} relative where its element carries more than"
            f" {self.round_off:g} × the largest flow on both sides, else excluded as round-off",
        ]


DEFAULT_SETTINGS = Tolerances(
    flow=1.0e-8,
    flow_floor=1.0e-14,
    head=1.0e-6,
    head_rel=0.0,
    speed=1.0e-9,
    curve_head=1.0e-6,
    curve_head_rel=1.0e-8,
    other=1.0e-6,
    round_off=1.0e-9,
)
"""Proposal vfd-slice2-discharge-pressure.md §2.7's table (criterion 3, default solver settings):
flows 10⁻⁸ × the largest flow + 10⁻¹⁴ m³/s, heads 10⁻⁶ m (10 × the solver's energy tolerance),
pressures ρg·10⁻⁶ m, speeds 10⁻⁹ relative, system-curve heads 10⁻⁸ relative or 10⁻⁶ m, every
other number 10⁻⁶ relative where its element's flow exceeds 10⁻⁹ × the largest flow."""

FIXED_POINT = Tolerances(
    flow=1.0e-11,
    flow_floor=0.0,
    head=1.0e-8,
    head_rel=1.0e-11,
    speed=1.0e-11,
    curve_head=1.0e-8,
    curve_head_rel=1.0e-11,
    other=DEFAULT_SETTINGS.other,
    round_off=DEFAULT_SETTINGS.round_off,
)
"""§2.7 criterion 7 (both trees at solver tolerance 10⁻¹³ and 1,000 iterations): flows
10⁻¹¹ × the largest flow, heads (system-curve heads among them) 10⁻⁸ m or 10⁻¹¹ relative,
whichever is looser, pressures the same as heads of ρg, speeds 10⁻¹¹ relative; every other number
as ``DEFAULT_SETTINGS``, since the criterion names none."""

QUANTITIES = ("flow", "head", "pressure", "speed", "curve_head", "other")

KEYS = {
    **dict.fromkeys(("flow", "outflow", "operatingFlow"), "flow"),
    **dict.fromkeys(
        (
            "egl",
            "hgl",
            "headLoss",
            "frictionHeadLoss",
            "fittingsHeadLoss",
            "operatingHead",
            "npshAvailable",
            "npshRequired",
            "npshMargin",
            "crackingHead",  # flag details
            "headDifference",
            "headRise",
            "shutoffHead",
        ),
        "head",
    ),
    **dict.fromkeys(
        (
            "pressure",
            "absolutePressure",
            "dynamicPressure",
            "totalPressure",
            "pressureDrop",
            "suctionAbsolutePressure",
            "atmosphericPressure",
            "vaporPressure",
        ),
        "pressure",
    ),
    **dict.fromkeys(("speed", "maxSpeed", "minSpeed"), "speed"),
}
"""The quantity of a float by its key (``models/results.py``); any other key is "other"."""

INDEX_SUFFIX = "Index"
"""A number under a key ending so is an index and compares exactly, as an integer does: a flag's
``segmentIndex`` and ``fittingIndex`` (``Flag.details`` is ``dict[str, float | str]``)."""

MAPS = {"portFlows": "flow", "portOutflows": "flow", "pathHeadLosses": "head"}
"""Branch and boundary result fields keyed by port id, by the quantity of their values."""

LENGTH_WORDS = ("diameter", "roughness", "length", "elevation", "level")
"""A trace value in m whose name has one of these is a length ("other"), not a head."""

NUMBER = re.compile(r"(?<![\w.\-−])[-+−]?(?:\d+(?:\.\d+)*|\.\d+)(?:[eE][-+]?\d+)?(?!\w)")
"""A number in a text: an optional sign, digits with any '.'-separated groups (1.25, 1.3.1) and
an exponent, not part of a word (PU4, port_1, H1 and PU-1 keep their digits)."""


def mask(text: str) -> str:
    """``text`` with every number in it replaced by '#' if it has whitespace (a message, note,
    equation or methods item); a string without (an id, status, state or code) as it is."""
    if not any(c.isspace() for c in text):
        return text
    return NUMBER.sub("#", text)


def excerpt(a: str, b: str, width: int = 80) -> tuple[str, str]:
    """The masked texts of a and b from just before their first difference."""
    ma, mb = mask(a), mask(b)
    first = next(
        (i for i, (x, y) in enumerate(zip(ma, mb, strict=False)) if x != y), min(len(ma), len(mb))
    )
    start = max(0, first - 20)
    lead = "…" if start else ""
    return lead + ma[start : start + width], lead + mb[start : start + width]


def at(doc: Any, segments: Sequence[str]) -> Any:
    """The value at these keys and list indices of a dump, or None."""
    for seg in segments:
        if isinstance(doc, dict):
            doc = doc.get(seg)
        elif isinstance(doc, list) and seg.isdigit() and int(seg) < len(doc):
            doc = doc[int(seg)]
        else:
            return None
    return doc


def _number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def element_flows(doc: Any) -> dict[str, float]:
    """|flow| of each element of a dump's main solve: connections, valves and pumps by id; each
    port of a branch or boundary by 'id:port', and the branch or boundary by id with the least
    of its port flows (a tee's K factors, flow ratio and port velocities are round-off where one
    of its ports carries a round-off flow; a boundary without port flows by its outflow)."""
    flows: dict[str, float] = {}

    def results(field: str) -> dict[str, Any]:
        d = at(doc, (field,))
        return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}

    for field, key in (("linkResults", "flow"), ("valveResults", "flow")):
        for eid, r in results(field).items():
            if _number(r.get(key)):
                flows[eid] = abs(r[key])
    for eid, r in results("pumpResults").items():
        if _number(r.get("operatingFlow")):
            flows[eid] = abs(r["operatingFlow"])
    for field, ports_key in (("branchResults", "portFlows"), ("boundaryResults", "portOutflows")):
        for eid, r in results(field).items():
            ports = r.get(ports_key)
            values = []
            if isinstance(ports, dict):
                for port, q in ports.items():
                    if _number(q):
                        flows[f"{eid}:{port}"] = abs(q)
                        values.append(abs(q))
            if values:
                flows[eid] = min(values)
            elif _number(r.get("outflow")):
                flows[eid] = abs(r["outflow"])
    return flows


def trace_quantity(item: Any) -> str:
    """The quantity of a trace input's or intermediate's value, by its unit (and name)."""
    if not isinstance(item, dict):
        return "other"
    unit, name = str(item.get("unit", "")), str(item.get("name", "")).lower()
    if unit == "m³/s":
        return "flow"
    if unit == "m":
        return "other" if any(w in name for w in LENGTH_WORDS) else "head"
    if unit == "Pa" or unit.startswith(("Pa(", "Pa (")):
        return "pressure"
    if unit == "" and "speed" in name:
        return "speed"
    return "other"


class Judge:
    """Compares the values of one project's two dumps within tolerances (module docstring)."""

    def __init__(self, a: Any, b: Any, tolerances: Tolerances) -> None:
        self.docs = (a, b)
        self.tol = tolerances
        self.flows = (element_flows(a), element_flows(b))
        self.q_max = max((q for f in self.flows for q in f.values()), default=0.0)
        densities = [r for r in (at(d, ("fluid", "density")) for d in self.docs) if _number(r)]
        self.rho_g = densities[0] * G if densities else 0.0
        """0 without a fluid density: pressures then compare exactly."""

    def item(self, segments: Sequence[str]) -> Any:
        return next((v for v in (at(d, segments) for d in self.docs) if v is not None), None)

    def quantity(self, segments: tuple[str, ...]) -> str:
        top, key, n = segments[0], segments[-1], len(segments)
        if top == "trace":
            if n == 6 and segments[1] == "elements" and segments[3] in ("inputs", "intermediates"):
                return trace_quantity(self.item(segments[:-1]))
            return "other"
        if n == 4 and segments[2] in MAPS and top in ("branchResults", "boundaryResults"):
            return MAPS[segments[2]]
        if top == "pumpResults" and n == 5 and segments[2] in ("curve", "systemCurve"):
            if key == "flow":
                return "flow"
            return "curve_head" if segments[2] == "systemCurve" else "head"
        return KEYS.get(key, "other")

    def element(self, side: int, segments: tuple[str, ...]) -> float | None:
        """|flow| of the element a value belongs to, on one side; None without one."""
        top, flows, keys = segments[0], self.flows[side], []
        if len(segments) > 1 and top in (
            "linkResults",
            "valveResults",
            "pumpResults",
            "branchResults",
            "boundaryResults",
        ):
            keys = [segments[1]]
        elif len(segments) > 1 and top == "nodeResults":
            keys = [segments[1], segments[1].partition(":")[0]]
        elif len(segments) > 2 and top == "trace" and segments[1] == "elements":
            keys = [segments[2]]
        elif len(segments) > 1 and top == "flags":
            flag = at(self.docs[side], segments[:2])
            if isinstance(flag, dict):
                conn, comp, port = (flag.get(k) for k in ("connectionId", "componentId", "portId"))
                if conn:
                    keys = [str(conn)]
                elif comp:
                    keys = [f"{comp}:{port}", str(comp)] if port else [str(comp)]
        return next((flows[k] for k in keys if k in flows), None)

    def flows_note(self, segments: tuple[str, ...]) -> tuple[str, ...]:
        """("element |Q| A / B m³/s",) for a value of an element, () for another, so that a
        state that changes shows the flows it changes at (§2.7 criterion 4)."""
        sides = [self.element(s, segments) for s in (0, 1)]
        if all(q is None for q in sides):
            return ()
        return ("element |Q| " + " / ".join("-" if q is None else f"{q:.3g}" for q in sides),)

    def tolerance(self, quantity: str, a: float, b: float) -> float:
        t, big = self.tol, max(abs(a), abs(b))
        if quantity == "flow":
            return t.flow * self.q_max + t.flow_floor
        if quantity == "head":
            return max(t.head, t.head_rel * big)
        if quantity == "pressure":
            return max(self.rho_g * t.head, t.head_rel * big)
        if quantity == "speed":
            return t.speed * big
        if quantity == "curve_head":
            return max(t.curve_head, t.curve_head_rel * big)
        return t.other * big

    def leaf(
        self, segments: tuple[str, ...], path: str, a: Any, b: Any, out: list[Difference]
    ) -> None:
        """Records ("val", path, a, b[, the element's flows]) for a difference that compares
        exactly (a text as ``excerpt``); for a float ("in" or "out", path, a, b, |Δ|/tolerance,
        quantity), or ("round-off", path, a, b, relative difference, whether the element's flow
        is 0 on a side)."""
        if isinstance(a, str) and isinstance(b, str):
            if a != b and mask(a) != mask(b):
                out.append(("val", path, *excerpt(a, b), *self.flows_note(segments)))
            return
        if not (_number(a) and _number(b)) or (isinstance(a, int) and isinstance(b, int)):
            if a != b:
                out.append(("val", path, a, b, *self.flows_note(segments)))
            return
        if a == b or (math.isnan(a) and math.isnan(b)):
            return
        if segments[-1].endswith(INDEX_SUFFIX):  # an index held as a float: exact
            out.append(("val", path, a, b, *self.flows_note(segments)))
            return
        quantity = self.quantity(segments)
        if quantity == "other":
            sides = [q for q in (self.element(s, segments) for s in (0, 1)) if q is not None]
            if sides and min(sides) <= self.tol.round_off * self.q_max:
                rel = abs(a - b) / max(abs(a), abs(b), 1e-300)
                out.append(("round-off", path, a, b, rel, min(sides) == 0.0))
                return
        tolerance = self.tolerance(quantity, a, b)
        ratio = abs(a - b) / tolerance if tolerance > 0.0 else math.inf
        if math.isnan(ratio):
            ratio = math.inf
        out.append(("in" if ratio <= 1.0 else "out", path, a, b, ratio, quantity))


def traces_inputs(doc: Any, wanted: dict[str, str]) -> bool:
    """Whether a dump traces an element with all these inputs (name -> value as text)."""
    elements = at(doc, ("trace", "elements"))
    if not isinstance(elements, dict):
        return False
    for element in elements.values():
        inputs = element.get("inputs") if isinstance(element, dict) else None
        given = {
            str(i.get("name")): str(i.get("value"))
            for i in (inputs if isinstance(inputs, list) else [])
            if isinstance(i, dict)
        }
        if all(given.get(name) == value for name, value in wanted.items()):
            return True
    return False


def parse_group(text: str) -> dict[str, str]:
    """'Valve type=prv,Status=active' -> {'Valve type': 'prv', 'Status': 'active'}."""
    wanted: dict[str, str] = {}
    for part in text.split(","):
        name, sep, value = (s.strip() for s in part.partition("="))
        if not sep or not name:
            raise ValueError(f"expected NAME=VALUE, got {part.strip()!r}")
        wanted[name] = value
    return wanted


# --------------------------------------------------------------------------- the comparison


def read(path: Path) -> tuple[Any, str | None]:
    """(parsed JSON, None), or (None, the error) when the file cannot be read or parsed."""
    try:
        return json.loads(path.read_text()), None
    except (OSError, ValueError) as ex:  # ValueError: JSONDecodeError, UnicodeDecodeError
        return None, f"{type(ex).__name__}: {ex}"


def pairs(a_dir: Path, b_dir: Path, lines: list[str]) -> Iterator[tuple[str, Any, Any, bool]]:
    """(name, A, B, readable) for every project of A that B has, in name order; the projects
    missing from either side and the unreadable files are reported in ``lines`` as met."""
    for fa in sorted(a_dir.glob("*.json")):
        name = fa.name
        if name.startswith("_"):
            continue
        fb = b_dir / name
        if not fb.exists():
            lines.append(f"missing in B: {name}")
            continue
        (a, err_a), (b, err_b) = read(fa), read(fb)
        if err_a or err_b:
            errs = [f"{side} {err}" for side, err in (("A", err_a), ("B", err_b)) if err]
            lines.append(f"unreadable: {name}: {'; '.join(errs)}")
            yield name, None, None, False
            continue
        yield name, a, b, True
    for fb in sorted(b_dir.glob("*.json")):
        if not fb.name.startswith("_") and not (a_dir / fb.name).exists():
            lines.append(f"missing in A: {fb.name}")


def solve_note(doc: Any) -> str | None:
    """None for a converged solve; else that it did not converge, with its largest energy
    residual and message, or that it did not solve, with the error."""
    if isinstance(doc, dict) and doc.get("converged") is True:
        return None
    if not isinstance(doc, dict) or "converged" not in doc:
        error = doc.get("error", doc.get("load_error")) if isinstance(doc, dict) else doc
        return f"not solved: {str(error)[:160]}"
    message = at(doc, ("convergence", "message"))
    residual = at(doc, ("convergence", "maxEnergyResidual", "value"))
    shown = f"{residual:.3g} m" if _number(residual) else str(residual)
    return f"not converged (energy residual {shown}): {str(message)[:160]}"


def compare_dirs(
    a_dir: Path,
    b_dir: Path,
    ignore: Sequence[str] = (),
    ignore_null: Sequence[str] = (),
    tolerances: Tolerances | None = None,
    group: dict[str, str] | None = None,
) -> tuple[list[str], int]:
    """(report lines, number of different projects); ``ignore``: paths left out whatever their
    values, ``ignore_null``: paths left out where null or absent on both sides; ``tolerances``:
    the within-tolerance mode, None for the exact one; ``group``: the trace inputs of the
    projects counted apart (module docstring)."""
    lines: list[str] = []
    same = within = diff = 0
    worst: list[tuple[float, str, int, list[Difference]]] = []  # exact mode
    reports: list[tuple[str, str]] = []  # within tolerance: (project, its line)
    rules = [Ignore(tuple(p.split("."))) for p in ignore]
    rules += [Ignore(tuple(p.split(".")), null=True) for p in ignore_null]
    left_out: dict[Ignore, tuple[int, int]] = {}  # rule -> (values, projects)
    counts: dict[bool, dict[str, int]] = {True: {}, False: {}}  # in the group -> outcome -> n
    largest: dict[str, tuple[float, str, str]] = {}  # quantity -> (ratio, project, path)
    compared = compared_in = 0  # floats that differ and were compared, and their projects
    round_off = [0, 0, 0]  # excluded at a zero flow, at a round-off flow; their projects
    round_off_max: tuple[float, str, str] | None = None
    unsolved: list[str] = []
    for name, a, b, readable in pairs(a_dir, b_dir, lines):
        member = group is not None and any(traces_inputs(d, group) for d in (a, b))
        if not readable:
            diff += 1
            counts[member]["different"] = counts[member].get("different", 0) + 1
            continue
        out: list[Difference] = []
        hits: dict[Ignore, int] = {}
        if tolerances is None:
            walk(a, b, "", out, (), rules, hits)
        else:
            walk(a, b, "", out, (), rules, hits, Judge(a, b, tolerances).leaf)
            notes = [(side, solve_note(d)) for side, d in (("A", a), ("B", b))]
            if any(note for _, note in notes):
                sides = "; ".join(f"{side} {note or 'converged'}" for side, note in notes)
                unsolved.append(f"  {name}: {sides}")
        for rule, n in hits.items():
            values, projects = left_out.get(rule, (0, 0))
            left_out[rule] = (values + n, projects + 1)
        if tolerances is None:
            outcome = "different" if out else "identical"
        else:
            numeric = [o for o in out if o[0] in ("in", "out")]
            for o in numeric:
                if o[4] > largest.get(o[5], (-1.0, "", ""))[0]:
                    largest[o[5]] = (o[4], name, o[1])
            compared += len(numeric)
            compared_in += bool(numeric)
            excluded = [o for o in out if o[0] == "round-off"]
            round_off[0] += sum(1 for o in excluded if o[5])
            round_off[1] += sum(1 for o in excluded if not o[5])
            round_off[2] += bool(excluded)
            for o in excluded:
                if round_off_max is None or o[4] > round_off_max[0]:
                    round_off_max = (o[4], name, o[1])
            bad = [o for o in out if o[0] not in ("in", "round-off")]
            outcome = "different" if bad else "within tolerance" if out else "identical"
        counts[member][outcome] = counts[member].get(outcome, 0) + 1
        if outcome == "identical":
            same += 1
            continue
        if outcome == "within tolerance":
            within += 1
            continue
        diff += 1
        if tolerances is None:
            nums = [o for o in out if o[0] == "num"]
            others = [o for o in out if o[0] != "num"]
            mx = max((o[4] for o in nums), default=0.0)
            worst.append((mx, name, len(nums), others[:3]))
        else:
            beyond = [o for o in out if o[0] == "out"]
            rest = [o for o in out if o[0] in ("key", "len", "val")]
            listed = [(o[0], o[1], str(o[2])[:80], str(o[3])[:80], *o[4:]) for o in rest[:10]]
            line = f"  {name}: {len(beyond)} numbers out of tolerance"
            if beyond:
                o = max(beyond, key=lambda x: x[4])
                line += f", worst |Δ|/tolerance {o[4]:.3g} ({o[5]} {o[1]}: {o[2]!r} vs {o[3]!r})"
            reports.append((name, f"{line}; {len(rest)} other differences: {listed}"))
    if tolerances is None:
        lines.append(f"identical {same}, different {diff}")
    else:
        lines.append(f"identical {same}, within tolerance {within}, different {diff}")
    for rule in rules:
        values, projects = left_out.get(rule, (0, 0))
        lines.append(f"ignored {rule}: {values} values in {projects} projects")
    if group is not None:
        kinds = ["identical", "different"]
        if tolerances is not None:
            kinds.insert(1, "within tolerance")
        spec = ",".join(f"{k}={v}" for k, v in group.items())
        for member, label in ((True, f"group '{spec}'"), (False, "others")):
            tally = ", ".join(f"{k} {counts[member].get(k, 0)}" for k in kinds)
            lines.append(f"{label}: {tally}")
    if tolerances is None:
        for mx, name, n, others in sorted(worst, key=lambda x: -x[0])[:25]:
            shown = [(o[0], o[1], str(o[2])[:80], str(o[3])[:80]) for o in others]
            lines.append(f"  {name}: {n} numeric diffs, max rel {mx:.3g}; other: {shown}")
        return lines, diff
    lines.append("tolerances: " + "; ".join(tolerances.describe()))
    lines.append(
        f"largest |Δ|/tolerance of the {compared} numbers that differ, in {compared_in} projects:"
    )
    for quantity in QUANTITIES:
        if quantity in largest:
            ratio, name, path = largest[quantity]
            lines.append(f"  {quantity} {ratio:.3g}: {name} {path}")
        else:
            lines.append(f"  {quantity}: no difference")
    n_zero, n_small, n_projects = round_off
    excluded_line = (
        f"excluded as round-off: {n_zero + n_small} numbers in {n_projects} projects ({n_zero} of"
        f" an element whose flow is reported as 0 on a side, {n_small} of one carrying at most"
        f" {tolerances.round_off:g} × the largest flow)"
    )
    if round_off_max is not None:
        rel, name, path = round_off_max
        excluded_line += f"; largest relative difference {rel:.3g}: {name} {path}"
    lines.append(excluded_line)
    lines.append(f"not converged or not solved on a side: {len(unsolved)}")
    lines.extend(unsolved)
    lines.append(f"different: {diff}")
    lines.extend(line for _, line in sorted(reports))
    return lines, diff


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.compare",
        description="Compare two corpus dumps exactly, or within tolerances (TSD §10.4).",
    )
    parser.add_argument("a", type=Path, help="first dump directory")
    parser.add_argument("b", type=Path, help="second dump directory")
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="PATH",
        help="leave out the values at this path, whatever they are ('.'-separated keys and"
        " indices, fnmatch patterns per segment, e.g. methodVersion); repeatable",
    )
    parser.add_argument(
        "--ignore-null",
        action="append",
        default=[],
        metavar="PATH",
        help="leave out the values at this path only where they are null or absent on both"
        " sides, and compare them elsewhere (e.g. 'pumpResults.*.control'); repeatable",
    )
    parser.add_argument(
        "--within-tolerance",
        action="store_true",
        help="compare numbers within the tolerances of proposal vfd-slice2-discharge-pressure.md"
        " §2.7 by quantity, and texts with their numbers masked",
    )
    parser.add_argument(
        "--fixed-point",
        action="store_true",
        help="with --within-tolerance: the tolerances of §2.7 criterion 7, for dumps at solver"
        " tolerance 1e-13",
    )
    parser.add_argument(
        "--group",
        metavar="NAME=VALUE,...",
        help="also count apart the projects that trace an element with all these inputs, e.g."
        " 'Valve type=prv,Status=active'",
    )
    args = parser.parse_args(argv)
    if args.fixed_point and not args.within_tolerance:
        parser.error("--fixed-point needs --within-tolerance")
    try:
        group = parse_group(args.group) if args.group is not None else None
    except ValueError as ex:
        parser.error(f"--group: {ex}")
    tolerances = None
    if args.within_tolerance:
        tolerances = FIXED_POINT if args.fixed_point else DEFAULT_SETTINGS
    lines, diff = compare_dirs(args.a, args.b, args.ignore, args.ignore_null, tolerances, group)
    print("\n".join(lines))
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
