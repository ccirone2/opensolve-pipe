"""Inline fitting loss coefficients from ``data/fittings.json`` (design §3, SDD §6.2).

Each fitting type names one fluids 1.3.1 function and its arguments in the JSON; this module
evaluates that call with the pipe's inner diameter and the fitting's own fields. K is
independent of the flow rate for every library correlation (the Crane functions use the
fully turbulent ``ft_Crane(D)``), so it is resolved once per solve. A reducer's K depends on
the flow direction (contraction or expansion), so each fitting carries a K and a reference
segment for each direction.

Precedence (SDD §6.2): a user ``kOverride`` always wins (labeled "user") and is referenced to
pipe ``pipeIndex``; so does a project library entry (``resistanceId``, CLAUDE.md D21), its K
moved to that pipe's inner diameter or its Cv or Kv converted on it
(``project_library.entry_k``), exactly the kOverride a user could type there; otherwise the
cited correlation is used.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any

import fluids.fittings
from scipy.constants import inch

from ...models.piping import REDUCER_TYPES, Fitting
from .library import read_data_json
from .project_library import EntryK, ResistanceEntries, entry_k, provenance

ArgumentValue = float | int | str

_SYMBOLS = ("$D", "$angle", "$radiusRatio", "$rc", "$D_small", "$D_large")


@dataclass(frozen=True)
class CallSpec:
    """One fluids.fittings call: function name and keyword arguments ('$' = solver input)."""

    function: str
    arguments: Mapping[str, ArgumentValue]

    def describe(self) -> str:
        args = ", ".join(
            f"{k}={v[1:] if isinstance(v, str) and v.startswith('$') else repr(v)}"
            for k, v in self.arguments.items()
        )
        return f"fluids.fittings.{self.function}({args})"


@dataclass(frozen=True)
class FittingSpec:
    type: str
    name: str
    calls: Mapping[str, CallSpec]
    """'k' for ordinary fittings; 'expansion' and 'contraction' for reducers; none for custom."""
    parameters: tuple[str, ...]
    reference_diameter: str
    valid_in_laminar_flow: bool
    source: str
    size_range: tuple[float, float] | None = None
    """m. The reference diameters the correlation's table covers (``sizeRange`` in the JSON,
    tabulated in inches and converted with scipy.constants.inch); None: no size limit."""
    size_range_note: str = ""

    @property
    def correlation(self) -> str:
        if not self.calls:
            return "user K (kOverride)"
        return "; ".join(f"{key}: {call.describe()}" for key, call in self.calls.items())


def _call_spec(raw: dict[str, Any]) -> CallSpec:
    function = raw["function"]
    if not callable(getattr(fluids.fittings, function, None)):
        raise ValueError(f"fittings.json names unknown fluids.fittings function {function!r}")
    arguments: dict[str, ArgumentValue] = raw["arguments"]
    for value in arguments.values():
        if isinstance(value, str) and value.startswith("$") and value not in _SYMBOLS:
            raise ValueError(f"fittings.json uses unknown argument symbol {value!r}")
    return CallSpec(function=function, arguments=arguments)


@cache
def load_fittings() -> dict[str, FittingSpec]:
    """The fitting library, keyed by fitting type."""
    specs: dict[str, FittingSpec] = {}
    for raw in read_data_json("fittings.json")["fittings"]:
        calls = {
            key: _call_spec(raw[key]) for key in ("k", "expansion", "contraction") if key in raw
        }
        size = raw.get("sizeRange")
        specs[raw["type"]] = FittingSpec(
            type=raw["type"],
            name=raw["name"],
            calls=calls,
            parameters=tuple(raw["parameters"]),
            reference_diameter=raw["referenceDiameter"],
            valid_in_laminar_flow=raw["validInLaminarFlow"],
            source=raw["source"],
            size_range=(
                None if size is None else (size["minInches"] * inch, size["maxInches"] * inch)
            ),
            size_range_note="" if size is None else size["note"],
        )
    return specs


def size_warning(spec: FittingSpec, d: float) -> str | None:
    """A reference diameter outside the sizes a correlation is tabulated for."""
    if spec.size_range is None:
        return None
    lo, hi = spec.size_range
    if lo <= d <= hi:
        return None
    return (
        f"diameter {d:g} m is outside the sizes the Crane table covers ({lo:g} to {hi:g} m; "
        f"{spec.size_range_note}); K evaluated with the nearest size class"
    )


def evaluate_call(call: CallSpec, symbols: Mapping[str, float]) -> float:
    """Evaluate one fluids.fittings call, substituting '$' symbols."""
    kwargs = {
        key: symbols[value] if isinstance(value, str) and value.startswith("$") else value
        for key, value in call.arguments.items()
    }
    return float(getattr(fluids.fittings, call.function)(**kwargs))


@dataclass(frozen=True)
class ResolvedFitting:
    """K of one fitting (multiply by ``quantity``) for each flow direction, and its basis."""

    index: int
    type: str
    quantity: int
    k_forward: float
    """K for flow from -> to (Q > 0), on the velocity in segment ``segment_forward``."""
    k_reverse: float
    segment_forward: int
    segment_reverse: int
    correlation_forward: str
    correlation_reverse: str
    source: str
    user_k: bool
    valid_in_laminar_flow: bool
    range_warning: str | None
    entry: EntryK | None = None
    """The project library entry the K comes from (None: none); ``user_k`` is then True."""

    def k(self, flow: float) -> float:
        return self.k_reverse if flow < 0 else self.k_forward

    def segment(self, flow: float) -> int:
        return self.segment_reverse if flow < 0 else self.segment_forward

    def correlation(self, flow: float) -> str:
        return self.correlation_reverse if flow < 0 else self.correlation_forward


def _range_warning(fitting: Fitting, spec: FittingSpec, d: float) -> str | None:
    """Inputs outside the table a correlation interpolates (fluids clamps silently), and
    reference diameters outside the sizes it is tabulated for."""
    if (size := size_warning(spec, d)) is not None:
        return size
    if fitting.type == "bend" and fitting.radius_ratio is not None:
        table = fluids.fittings.bend_rounded_Crane_ratios
        lo, hi = float(min(table)), float(max(table))
        if not lo <= fitting.radius_ratio <= hi:
            return (
                f"bend radius ratio {fitting.radius_ratio:g} is outside the Crane r/D table "
                f"({lo:g} to {hi:g}); fluids evaluates K at the nearest table end"
            )
    if fitting.type == "entrance_rounded" and fitting.radius_ratio is not None:
        table = fluids.fittings.entrance_rounded_ratios_Crane
        hi = float(max(table))
        if fitting.radius_ratio > hi:
            return (
                f"entrance rounding ratio {fitting.radius_ratio:g} is beyond the Crane table "
                f"(up to {hi:g}); fluids holds K at the table's last value"
            )
    return None


def _reducer_direction(
    spec: FittingSpec, d_up: float, d_down: float, seg_up: int, seg_down: int, angle: float | None
) -> tuple[float, int, str]:
    """K, reference segment and correlation text for flow from d_up into d_down."""
    if d_up == d_down:
        return 0.0, seg_up, "equal diameters: no loss"
    symbols = {"$D_small": min(d_up, d_down), "$D_large": max(d_up, d_down)}
    if angle is not None:
        symbols["$angle"] = angle
    if d_up < d_down:
        call, segment = spec.calls["expansion"], seg_up  # K on the smaller, upstream pipe
    else:
        call, segment = spec.calls["contraction"], seg_down  # K on the smaller, downstream pipe
    return evaluate_call(call, symbols), segment, call.describe()


LIBRARY_K = "K from the project library (resistanceId)"
"""The correlation text of a fitting whose K comes from a project library entry."""


def resolve_fitting(
    index: int,
    fitting: Fitting,
    diameters: Sequence[float],
    entries: ResistanceEntries | None = None,
) -> ResolvedFitting:
    """K for one fitting in a connection whose segments have the given inner diameters.
    ``entries``: the project's resistance entries by id, for a fitting that refers to one (every
    reference resolves: a dangling one is a topology issue, ``builder.validate_topology``)."""
    spec = load_fittings()[fitting.type]
    i = fitting.pipe_index
    common: dict[str, Any] = {
        "index": index,
        "type": fitting.type,
        "quantity": fitting.quantity,
        "range_warning": None,
    }
    if fitting.resistance_id is not None:
        use = entry_k((entries or {})[fitting.resistance_id], diameters[i])
        return ResolvedFitting(
            **common,
            k_forward=use.k,
            k_reverse=use.k,
            segment_forward=i,
            segment_reverse=i,
            correlation_forward=LIBRARY_K,
            correlation_reverse=LIBRARY_K,
            source=provenance(use.entry),
            user_k=True,
            valid_in_laminar_flow=True,
            entry=use,
        )
    if fitting.k_override is not None:
        return ResolvedFitting(
            **common,
            k_forward=fitting.k_override,
            k_reverse=fitting.k_override,
            segment_forward=i,
            segment_reverse=i,
            correlation_forward="user K (kOverride)",
            correlation_reverse="user K (kOverride)",
            source="user",
            user_k=True,
            valid_in_laminar_flow=True,
        )
    common["range_warning"] = _range_warning(fitting, spec, diameters[i])
    if fitting.type in REDUCER_TYPES:
        d_a, d_b = diameters[i], diameters[i + 1]
        kf, sf, cf = _reducer_direction(spec, d_a, d_b, i, i + 1, fitting.angle)
        kr, sr, cr = _reducer_direction(spec, d_b, d_a, i + 1, i, fitting.angle)
        return ResolvedFitting(
            **common,
            k_forward=kf,
            k_reverse=kr,
            segment_forward=sf,
            segment_reverse=sr,
            correlation_forward=cf,
            correlation_reverse=cr,
            source=spec.source,
            user_k=False,
            valid_in_laminar_flow=spec.valid_in_laminar_flow,
        )
    d = diameters[i]
    symbols = {"$D": d}
    if fitting.angle is not None:
        symbols["$angle"] = fitting.angle
    if fitting.radius_ratio is not None:
        symbols["$radiusRatio"] = fitting.radius_ratio
        symbols["$rc"] = fitting.radius_ratio * d
    call = spec.calls["k"]
    k = evaluate_call(call, symbols)
    return ResolvedFitting(
        **common,
        k_forward=k,
        k_reverse=k,
        segment_forward=i,
        segment_reverse=i,
        correlation_forward=call.describe(),
        correlation_reverse=call.describe(),
        source=spec.source,
        user_k=False,
        valid_in_laminar_flow=spec.valid_in_laminar_flow,
    )
