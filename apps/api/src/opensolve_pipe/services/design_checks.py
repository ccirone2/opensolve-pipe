"""Opt-in design checks (CLAUDE.md D19; proposal design-checks.md §3).

``evaluate`` reads a converged solved state and the project's limits and returns one result per
check and element: pass, fail, or not evaluated with the reason. It never changes a solved
value, a status or a flag (design practice is opt-in and never a flag, GOALS §4.6). Every value
is the solved state's own (SI); the messages state the inequality that set each outcome.
"""

from collections.abc import Callable

from ..models.design_checks import (
    PRESETS,
    CheckSource,
    DesignCheckId,
    DesignCheckLimits,
    DesignCheckResult,
    DesignChecks,
)
from ..models.project import Project
from ..models.pumps import PumpCurve
from ..models.results import MethodsSection, PumpResult, SolvedState

CITATIONS = {p.id: p.citation for p in PRESETS}


def source_text(source: CheckSource) -> str:
    """'user', or the preset's citation."""
    return "user" if source.kind == "user" else CITATIONS[source.preset]


def _g(value: float) -> str:
    return f"{value:.6g}"


def _digits(value: float, *limits: float | None) -> Callable[[float], str]:
    """A format for a value and its limits: 6 significant digits, or as many more (up to 17,
    enough for any two doubles) as tell the value from a limit it is not equal to, so that a
    message never states a strict inequality between equal-looking numbers."""
    sig = 6
    while sig < 17 and any(
        lim is not None and lim != value and f"{lim:.{sig}g}" == f"{value:.{sig}g}"
        for lim in limits
    ):
        sig += 1
    return lambda x: f"{x:.{sig}g}"


def _result(
    check: DesignCheckId,
    outcome: str,
    message: str,
    source: str,
    unit: str,
    *,
    value: float | None = None,
    pipe_index: int | None = None,
    pipes_outside: tuple[int, ...] = (),
    low: float | None = None,
    high: float | None = None,
    component_id: str | None = None,
    connection_id: str | None = None,
) -> DesignCheckResult:
    return DesignCheckResult.model_validate(
        {
            "check": check,
            "componentId": component_id,
            "connectionId": connection_id,
            "outcome": outcome,
            "value": value,
            "pipeIndex": pipe_index,
            "pipesOutside": list(pipes_outside),
            "limits": DesignCheckLimits(min=low, max=high),
            "unit": unit,
            "source": source,
            "message": message,
        }
    )


def _interval(lo: float | None, hi: float | None) -> str:
    """ "[0.7, 1.2]", "≥ 0.7" or "≤ 1.2"."""
    if lo is not None and hi is not None:
        return f"[{_g(lo)}, {_g(hi)}]"
    return f"≥ {_g(lo)}" if lo is not None else f"≤ {_g(hi or 0.0)}"


def _compare(ok: bool, lo: float | None, hi: float | None, fmt: Callable[[float], str] = _g) -> str:
    """How a value stands against the limits set: "within [0.7, 1.2]", "outside [0.7, 1.2]",
    "≥ 0.7", "< 0.7", "≤ 1.2" or "> 1.2"."""
    if lo is not None and hi is not None:
        return f"{'within' if ok else 'outside'} [{fmt(lo)}, {fmt(hi)}]"
    if lo is not None:
        return f"{'≥' if ok else '<'} {fmt(lo)}"
    return f"{'≤' if ok else '>'} {fmt(hi or 0.0)}"


def _not_running(pump: PumpResult) -> str | None:
    if pump.status == "off":
        return "not evaluated: the pump is off"
    if pump.status == "no_flow":
        return "not evaluated: the pump is held at zero flow"
    return None


def _npsh(checks: DesignChecks, pid: str, pump: PumpResult) -> list[DesignCheckResult]:
    check = checks.npsh_margin
    if check is None:
        return []
    source = source_text(check.source)

    def skip(reason: str) -> list[DesignCheckResult]:
        return [_result("npsh_margin", "not_evaluated", reason, source, "m", component_id=pid)]

    reason = _not_running(pump)
    if reason:
        return skip(reason)
    if check.minimum_margin is None and check.minimum_ratio is None:
        return skip("not evaluated: no limit set")
    if pump.npsh_required is None:
        return skip("not evaluated: the pump curve has no NPSHr curve")
    if pump.npsh_available is None:
        return skip(
            "not evaluated: no NPSHa (the fluid has no vapor pressure, or the suction's pressure "
            "level is undetermined)"
        )
    npshr, npsha = pump.npsh_required, pump.npsh_available
    margin, ratio = check.minimum_margin, check.minimum_ratio
    required = max(
        v for v in (
            None if margin is None else npshr + margin,
            None if ratio is None else ratio * npshr,
        ) if v is not None
    )  # fmt: skip
    f = _digits(npsha, required)
    terms = [
        *([f"NPSHr {f(npshr)} m + {_g(margin)} m"] if margin is not None else []),
        *([f"{_g(ratio)} × NPSHr {f(npshr)} m"] if ratio is not None else []),
    ]
    formula = terms[0] if len(terms) == 1 else f"max({terms[0]}, {terms[1]})"
    ok = npsha >= required
    message = f"NPSHa {f(npsha)} m {'≥' if ok else '<'} {f(required)} m = {formula}"
    return [
        _result(
            "npsh_margin",
            "pass" if ok else "fail",
            message,
            source,
            "m",
            value=npsha,
            low=required,
            component_id=pid,
        )
    ]


def _region(
    checks: DesignChecks, pid: str, pump: PumpResult, curve: PumpCurve | None
) -> list[DesignCheckResult]:
    check = checks.operating_region
    if check is None:
        return []
    source = source_text(check.source)
    reason = _not_running(pump)
    if reason:
        return [_result("operating_region", "not_evaluated", reason, source, "1", component_id=pid)]
    out: list[DesignCheckResult] = []
    q, s = pump.operating_flow, pump.speed
    bep = pump.best_efficiency_point
    lo, hi = check.preferred_min, check.preferred_max
    if lo is None and hi is None:
        out.append(
            _result(
                "operating_region", "not_evaluated", "not evaluated: no limit set", source, "1",
                component_id=pid,
            )
        )  # fmt: skip
    elif bep is None:
        why = (
            "the pump curve has no efficiency curve"
            if curve is None or curve.efficiency_curve is None
            else "the efficiency curve's highest point is at an end of its data, so it shows no "
            "best efficiency point"
        )
        out.append(
            _result(
                "operating_region", "not_evaluated", f"not evaluated: {why}", source, "1",
                low=lo, high=hi, component_id=pid,
            )
        )  # fmt: skip
    else:
        ratio = q / bep.flow
        ok = (lo is None or lo <= ratio) and (hi is None or ratio <= hi)
        f = _digits(ratio, lo, hi)
        message = (
            f"Q/Q_BEP = {_g(q)} / {_g(bep.flow)} m³/s = {f(ratio)} "
            f"{_compare(ok, lo, hi, f)} (Q_BEP at the running speed "
            f"{_g(s)}, by the affinity laws)"
        )
        out.append(
            _result(
                "operating_region", "pass" if ok else "fail", message, source, "1",
                value=ratio, low=lo, high=hi, component_id=pid,
            )
        )  # fmt: skip
    if curve is None:
        return out
    # The curve's manufacturer data, at rated speed: compared with the rated-speed equivalent
    # flow Q/s (affinity laws), checked with the operating region (proposal §3).
    rated = q / s
    data = "manufacturer data (user)"
    aor = curve.allowable_operating_region
    if aor is not None:
        ok = aor.flow_min <= rated <= aor.flow_max
        f = _digits(rated, aor.flow_min, aor.flow_max)
        out.append(
            _result(
                "allowable_region", "pass" if ok else "fail",
                f"Q/s = {f(rated)} m³/s {'within' if ok else 'outside'} the allowable operating "
                f"region [{f(aor.flow_min)}, {f(aor.flow_max)}] m³/s at rated speed",
                data, "m³/s", value=rated, low=aor.flow_min, high=aor.flow_max, component_id=pid,
            )
        )  # fmt: skip
    minimums = [
        (v, name)
        for v, name in (
            (curve.minimum_continuous_stable_flow, "minimum continuous stable flow"),
            (curve.minimum_thermal_flow, "minimum thermal flow"),
        )
        if v is not None
    ]
    if minimums:
        # The larger; on a tie the first, the stable flow (the chart names the same one).
        floor, name = max(minimums, key=lambda m: m[0])
        ok = rated >= floor
        f = _digits(rated, floor)
        out.append(
            _result(
                "minimum_flow", "pass" if ok else "fail",
                f"Q/s = {f(rated)} m³/s {'≥' if ok else '<'} the {name} {f(floor)} m³/s at "
                "rated speed", data, "m³/s", value=rated, low=floor, component_id=pid,
            )
        )  # fmt: skip
    if curve.motor_rated_power is not None:
        rating = curve.motor_rated_power
        if pump.shaft_power is None:
            out.append(
                _result(
                    "motor_power", "not_evaluated",
                    "not evaluated: no shaft power (the pump curve has no efficiency curve)",
                    data, "W", high=rating, component_id=pid,
                )
            )  # fmt: skip
        else:
            ok = pump.shaft_power <= rating
            f = _digits(pump.shaft_power, rating)
            out.append(
                _result(
                    "motor_power", "pass" if ok else "fail",
                    f"P_shaft {f(pump.shaft_power)} W {'≤' if ok else '>'} the motor's rated "
                    f"power {f(rating)} W (no service-factor margin)",
                    data, "W", value=pump.shaft_power, high=rating, component_id=pid,
                )
            )  # fmt: skip
    return out


def _velocity(checks: DesignChecks, state: SolvedState) -> list[DesignCheckResult]:
    check = checks.pipe_velocity
    if check is None:
        return []
    source = source_text(check.source)
    lo, hi = check.minimum, check.maximum
    out: list[DesignCheckResult] = []
    for cid, link in state.link_results.items():
        if lo is None and hi is None:
            out.append(
                _result(
                    "pipe_velocity", "not_evaluated", "not evaluated: no limit set", source,
                    "m/s", connection_id=cid,
                )
            )  # fmt: skip
            continue
        speeds = [(abs(seg.velocity), seg.index) for seg in link.segments]
        if not speeds:
            continue
        fast, fast_i = max(speeds)
        slow, slow_i = min(speeds)
        above = [i for v, i in speeds if hi is not None and v > hi]
        below = [i for v, i in speeds if lo is not None and v < lo]
        # Traces and messages number a connection's pipes from 1; data indexes stay 0-based (D10).
        if above and hi is not None:
            f = _digits(fast, hi)
            message = f"|v| {f(fast)} m/s in pipe {fast_i + 1} above {f(hi)} m/s"
            value, at = fast, fast_i
        elif below and lo is not None:
            f = _digits(slow, lo)
            message = f"|v| {f(slow)} m/s in pipe {slow_i + 1} below {f(lo)} m/s"
            value, at = slow, slow_i
        else:
            # The value nearest a limit set: the fastest against a maximum, else the slowest.
            value, at = (fast, fast_i) if hi is not None else (slow, slow_i)
            f = _digits(value, lo, hi)
            spread = f(fast) if slow == fast else f"from {f(slow)} to {f(fast)}"
            message = f"|v| {spread} m/s, {_compare(True, lo, hi, f)} m/s"
        outside = sorted({*above, *below})
        if len(outside) > 1:
            message += f" (pipes outside: {', '.join(str(i + 1) for i in outside)})"
        out.append(
            _result(
                "pipe_velocity", "fail" if outside else "pass", message, source, "m/s",
                value=value, pipe_index=at, pipes_outside=tuple(outside), low=lo, high=hi,
                connection_id=cid,
            )
        )  # fmt: skip
    return out


def evaluate(project: Project, state: SolvedState) -> list[DesignCheckResult]:
    """Every check the project turns on, for every element (empty without checks or when the
    solve did not converge): pumps in component order, then connections in their order."""
    checks = project.settings.design_checks
    if checks is None or not state.converged:
        return []
    curves = {c.id: c for c in project.pump_library}
    out: list[DesignCheckResult] = []
    for comp in project.components:
        pump = state.pump_results.get(comp.id)
        if pump is None or comp.type != "pump":
            continue
        out += _npsh(checks, comp.id, pump)
        out += _region(checks, comp.id, pump, curves.get(comp.curve_id))
    order = {c.id: i for i, c in enumerate(project.connections)}
    velocity = _velocity(checks, state)
    out += sorted(velocity, key=lambda r: order.get(r.connection_id or "", len(order)))
    return out


def methods_section(project: Project) -> MethodsSection | None:
    """The "Design checks" methods section (only when a check is on)."""
    checks = project.settings.design_checks
    if checks is None or not checks.any_on():
        return None
    unset = "on, with no limit set, so each {} is listed as not evaluated."
    items: list[str] = [
        "Design checks are opt-in design practice, not physics flags: a result never changes a "
        "solved value (GOALS §4.6). Each limit is user data or a cited preset."
    ]
    refs: list[str] = []
    if (c := checks.npsh_margin) is not None:
        parts = [f"NPSHr + {_g(c.minimum_margin)} m"] if c.minimum_margin is not None else []
        if c.minimum_ratio is not None:
            parts.append(f"{_g(c.minimum_ratio)} × NPSHr")
        rule = f"max({', '.join(parts)})" if len(parts) > 1 else (parts[0] if parts else "")
        items.append(
            f"NPSH margin: each running pump's NPSHa ≥ {rule}."
            if rule
            else f"NPSH margin: {unset.format('pump')}"
        )
        if c.source.kind == "preset":
            refs.append(CITATIONS[c.source.preset])
    if (c2 := checks.operating_region) is not None:
        data = (
            "the curve's manufacturer data at rated speed against Q/s: the allowable operating "
            "region, the minimum continuous stable and thermal flows, and P_shaft against the "
            "motor's rated power (no service-factor margin)."
        )
        if c2.preferred_min is None and c2.preferred_max is None:
            items.append(
                f"Operating region: on, with no limit set, so each pump's Q/Q_BEP is listed as "
                f"not evaluated; with it, {data}"
            )
        else:
            region = _interval(c2.preferred_min, c2.preferred_max)
            items.append(
                f"Operating region: each running pump's Q/Q_BEP {region}, Q_BEP the best "
                f"efficiency point at the running speed; with it, {data}"
            )
        if c2.source.kind == "preset":
            refs.append(CITATIONS[c2.source.preset])
    if (c3 := checks.pipe_velocity) is not None:
        lo = f"at least {_g(c3.minimum)} m/s" if c3.minimum is not None else None
        hi = f"at most {_g(c3.maximum)} m/s" if c3.maximum is not None else None
        rule = " and ".join(x for x in (lo, hi) if x)
        items.append(
            f"Pipe velocity: every pipe segment's |v| {rule}."
            if rule
            else f"Pipe velocity: {unset.format('connection')}"
        )
    return MethodsSection(title="Design checks", items=items, references=refs)
