"""Check the opt-in design checks over the corpus (CLAUDE.md D19; proposal design-checks.md §6).

    uv run python -m tests.differential.design_checks_check [--workers N] [--only PREFIX]
                                                            [--out FILE]

For every corpus project (``corpus.items()``, none of which has design checks), the project is
solved (A), then again (B) with every check on and every pump curve given manufacturer data,
both without system curves. Few corpus pumps have an efficiency or NPSHr curve, so in A and B
alike each pump curve without one is given one, a test input drawn from its head points (Q_max
their largest flow): efficiencies 0.40, 0.65, 0.75, 0.65, 0.55 and NPSHr 1 + 4 (Q/Q_max)² m at
0.1, 0.35, 0.6, 0.85 and 1.0 Q_max, so that it has a best efficiency point at 0.6 Q_max and a
shaft power (neither curve changes a flow or a head). In B:

- the checks: the HI 9.6.1-2012 "General" preset's NPSH margin (ratio 1.1, margin 1.0 m), API
  610's preferred operating region (0.7-1.2 of the BEP flow) and a pipe velocity of 0.5-3 m/s
  (the user's values);
- each pump curve's manufacturer data, test inputs drawn from its own head points (Q_max their
  largest flow, H_max their largest head): an allowable region of 0.25-1.1 Q_max, a minimum
  continuous stable flow of 0.2 Q_max, a minimum thermal flow of 0.15 Q_max and a motor rated
  power of ρ_w g Q_max H_max / 2 (ρ_w = 998 kg/m³), so that every check passes on some pumps
  and fails on others.

Checks (a difference names its letter):

- (a) A has no design check results, and B's solved state is A's in every value: the two dumps
  are equal but for B's ``designChecks``, B's last methods section ("Design checks") and the
  solves' timestamps (a check never changes a solved value, GOALS §4.6; the manufacturer data
  are not read by the solve);
- (b) B's ``designChecks`` equal the results re-derived here from B's solved state (API JSON)
  and the checks' limits, by a second implementation of the rules of the proposal's §3 that
  does not import ``services.design_checks``: the same list in the same order (pumps in
  component order, then connections in project order), each result's check, element, outcome,
  value, limits, pipe index, pipes outside and unit exactly equal (the same floating-point
  operations), the source the preset's citation, "user" or "manufacturer data (user)", and the
  message starting "not evaluated:" exactly when not evaluated, else stating the comparison its
  outcome says (≥, ≤ or within for a pass; <, >, outside, above or below for a fail) between
  numbers that differ in their text;
- (c) a solve that did not converge has no design check results.

The report counts, per profile (ref, unit, ladder, wye, fuzz, fuzzfc, fuzzaf), the projects
checked and not converged, and each check's outcomes, so that a check that never failed or
never ran would show. Exit status 1 on any difference; ``--out`` writes every project's record
as JSON. ``test_design_checks_check_smoke.py`` runs the reference cases, the unit-test data
networks and a few seeds of each fuzz profile, and falsified results.
"""

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from typing import Any

from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.design_checks import PRESETS
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import TopologyError, solve_project
from tests.differential.corpus import Item, items, load

NO_CURVES = SolveOptions(include_system_curve=False)
G = 9.80665
"""m/s², standard gravity (a defined value, 3rd CGPM, 1901)."""
WATER = 998.0
"""kg/m³: the motor rating's density (a test input)."""
CITATIONS = {p.id: p.citation for p in PRESETS}
CHECKS: dict[str, Any] = {
    "npshMargin": {
        "minimumRatio": 1.1,
        "minimumMargin": 1.0,
        "source": {"kind": "preset", "preset": "hi961_2012_general"},
    },
    "operatingRegion": {
        "preferredMin": 0.7,
        "preferredMax": 1.2,
        "source": {"kind": "preset", "preset": "api610_por"},
    },
    "pipeVelocity": {"minimum": 0.5, "maximum": 3.0, "source": {"kind": "user"}},
}
"""The checks turned on in B (module docstring)."""
PROFILES = ("ref", "unit", "ladder", "wye", "fuzz", "fuzzfc", "fuzzaf")
CHECK_IDS = (
    "npsh_margin",
    "operating_region",
    "allowable_region",
    "minimum_flow",
    "motor_power",
    "pipe_velocity",
)


def profile(name: str) -> str:
    return name.split("_", 1)[0]


EFFICIENCY_SHAPE = ((0.1, 0.40), (0.35, 0.65), (0.6, 0.75), (0.85, 0.65), (1.0, 0.55))
"""(fraction of Q_max, efficiency) of the efficiency curve given (module docstring)."""


def with_curves(project: dict[str, Any]) -> dict[str, Any]:
    """A's project (API JSON): each pump curve without an efficiency or NPSHr curve given one."""
    data = copy.deepcopy(project)
    data.pop("scenarios", None)
    for curve in data.get("pumpLibrary", []):
        q_max = max(p["flow"] for p in curve["points"])
        if q_max <= 0:
            continue
        if not curve.get("efficiencyCurve"):
            curve["efficiencyCurve"] = [
                {"flow": f * q_max, "efficiency": eta} for f, eta in EFFICIENCY_SHAPE
            ]
        if not curve.get("npshrCurve"):
            curve["npshrCurve"] = [
                {"flow": f * q_max, "npshr": 1.0 + 4.0 * f * f} for f, _ in EFFICIENCY_SHAPE
            ]
    return data


def with_checks(project: dict[str, Any]) -> dict[str, Any]:
    """B's project (API JSON): every check on, every pump curve with manufacturer data."""
    data = copy.deepcopy(project)
    data.pop("scenarios", None)
    data["settings"]["designChecks"] = copy.deepcopy(CHECKS)
    for curve in data.get("pumpLibrary", []):
        q_max = max(p["flow"] for p in curve["points"])
        h_max = max(p["head"] for p in curve["points"])
        if q_max <= 0:
            continue
        curve["allowableOperatingRegion"] = {"flowMin": 0.25 * q_max, "flowMax": 1.1 * q_max}
        curve["minimumContinuousStableFlow"] = 0.2 * q_max
        curve["minimumThermalFlow"] = 0.15 * q_max
        if h_max > 0:
            curve["motorRatedPower"] = WATER * G * q_max * h_max / 2.0
    return data


# ------------------------------------------------------------------ the second implementation


def _source(source: dict[str, Any]) -> str:
    return "user" if source["kind"] == "user" else CITATIONS[source["preset"]]


UNITS = {
    "npsh_margin": "m",
    "operating_region": "1",
    "allowable_region": "m³/s",
    "minimum_flow": "m³/s",
    "motor_power": "W",
    "pipe_velocity": "m/s",
}
"""The SI unit of each check's value and limits (proposal §4)."""
PASS_WORDS = ("≥", "≤", "within")
FAIL_WORDS = ("<", ">", "outside", "above", "below")


def _result(
    check: str,
    outcome: str,
    *,
    component: str | None = None,
    connection: str | None = None,
    value: float | None = None,
    low: float | None = None,
    high: float | None = None,
    pipe: int | None = None,
    outside: list[int] | None = None,
    source: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "componentId": component,
        "connectionId": connection,
        "outcome": outcome,
        "value": value,
        "limits": {"min": low, "max": high},
        "pipeIndex": pipe,
        "pipesOutside": outside or [],
        "unit": UNITS[check],
        "source": source,
    }


def expected(project: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    """The design check results of ``state`` (B's solved state, API JSON), re-derived from the
    proposal's §3 rules and the checks' limits in ``project`` (B's, API JSON)."""
    checks = project["settings"]["designChecks"]
    curves = {c["id"]: c for c in project.get("pumpLibrary", [])}
    out: list[dict[str, Any]] = []
    for comp in project["components"]:
        pump = state["pumpResults"].get(comp["id"])
        if comp["type"] != "pump" or pump is None:
            continue
        pid = comp["id"]
        running = pump["status"] == "running"
        npsh = checks.get("npshMargin")
        if npsh is not None:
            src = _source(npsh["source"])
            margin, ratio = npsh.get("minimumMargin"), npsh.get("minimumRatio")
            npshr, npsha = pump.get("npshRequired"), pump.get("npshAvailable")
            if not running or (margin is None and ratio is None) or npshr is None or npsha is None:
                out.append(_result("npsh_margin", "not_evaluated", component=pid, source=src))
            else:
                terms = []
                if margin is not None:
                    terms.append(npshr + margin)
                if ratio is not None:
                    terms.append(ratio * npshr)
                required = max(terms)
                out.append(
                    _result(
                        "npsh_margin", "pass" if npsha >= required else "fail", component=pid,
                        value=npsha, low=required, source=src,
                    )
                )  # fmt: skip
        region = checks.get("operatingRegion")
        if region is None:
            continue
        src = _source(region["source"])
        if not running:
            out.append(_result("operating_region", "not_evaluated", component=pid, source=src))
            continue
        lo, hi = region.get("preferredMin"), region.get("preferredMax")
        q, s = pump["operatingFlow"], pump["speed"]
        bep = pump.get("bestEfficiencyPoint")
        if lo is None and hi is None:
            out.append(_result("operating_region", "not_evaluated", component=pid, source=src))
        elif bep is None:
            out.append(
                _result(
                    "operating_region", "not_evaluated", component=pid, low=lo, high=hi,
                    source=src,
                )
            )  # fmt: skip
        else:
            ratio_bep = q / bep["flow"]
            ok = (lo is None or lo <= ratio_bep) and (hi is None or ratio_bep <= hi)
            out.append(
                _result(
                    "operating_region", "pass" if ok else "fail", component=pid,
                    value=ratio_bep, low=lo, high=hi, source=src,
                )
            )  # fmt: skip
        curve = curves.get(comp["curveId"])
        if curve is None:
            continue
        data = "manufacturer data (user)"
        rated = q / s
        aor = curve.get("allowableOperatingRegion")
        if aor is not None:
            ok = aor["flowMin"] <= rated <= aor["flowMax"]
            out.append(
                _result(
                    "allowable_region", "pass" if ok else "fail", component=pid, value=rated,
                    low=aor["flowMin"], high=aor["flowMax"], source=data,
                )
            )  # fmt: skip
        floors = [
            v
            for v in (curve.get("minimumContinuousStableFlow"), curve.get("minimumThermalFlow"))
            if v is not None
        ]
        if floors:
            floor = max(floors)
            out.append(
                _result(
                    "minimum_flow", "pass" if rated >= floor else "fail", component=pid,
                    value=rated, low=floor, source=data,
                )
            )  # fmt: skip
        rating = curve.get("motorRatedPower")
        if rating is not None:
            power = pump.get("shaftPower")
            if power is None:
                out.append(
                    _result("motor_power", "not_evaluated", component=pid, high=rating, source=data)
                )
            else:
                out.append(
                    _result(
                        "motor_power", "pass" if power <= rating else "fail", component=pid,
                        value=power, high=rating, source=data,
                    )
                )  # fmt: skip
    velocity = checks.get("pipeVelocity")
    if velocity is not None:
        src = _source(velocity["source"])
        lo, hi = velocity.get("minimum"), velocity.get("maximum")
        for conn in project["connections"]:
            link = state["linkResults"].get(conn["id"])
            if link is None:
                continue
            if lo is None and hi is None:
                out.append(
                    _result("pipe_velocity", "not_evaluated", connection=conn["id"], source=src)
                )
                continue
            speeds = [(abs(seg["velocity"]), seg["index"]) for seg in link["segments"]]
            if not speeds:
                continue
            above = sorted(i for v, i in speeds if hi is not None and v > hi)
            below = sorted(i for v, i in speeds if lo is not None and v < lo)
            fast, slow = max(speeds), min(speeds)
            if above:
                value, at = fast
            elif below:
                value, at = slow
            else:
                value, at = fast if hi is not None else slow
            outside = sorted({*above, *below})
            out.append(
                _result(
                    "pipe_velocity", "fail" if outside else "pass", connection=conn["id"],
                    value=value, low=lo, high=hi, pipe=at, outside=outside, source=src,
                )
            )  # fmt: skip
    return out


# --------------------------------------------------------------------------- the checks


def _dump(state: Any) -> dict[str, Any]:
    dumped: dict[str, Any] = state.model_dump(mode="json", by_alias=True)
    return dumped


def result_problems(
    project: dict[str, Any], state: dict[str, Any], reported: list[dict[str, Any]]
) -> list[str]:
    """(b): every difference between ``reported`` (B's designChecks) and the re-derived list."""
    want = expected(project, state)
    problems: list[str] = []
    if len(want) != len(reported):
        problems.append(
            f"(b) {len(reported)} results, {len(want)} expected: "
            f"{[(r['check'], r['componentId'] or r['connectionId']) for r in reported]}"
        )
        return problems
    for i, (got, exp) in enumerate(zip(reported, want, strict=True)):
        where = f"#{i} {exp['check']} {exp['componentId'] or exp['connectionId']}"
        for key in exp:
            if got.get(key) != exp[key]:
                problems.append(f"(b) {where}: {key} {got.get(key)!r}, expected {exp[key]!r}")
        message = got["message"]
        not_evaluated = message.startswith("not evaluated:")
        if not_evaluated != (got["outcome"] == "not_evaluated"):
            problems.append(f"(b) {where}: message {message!r} for {got['outcome']}")
        elif not not_evaluated:
            words = PASS_WORDS if got["outcome"] == "pass" else FAIL_WORDS
            wrong = FAIL_WORDS if got["outcome"] == "pass" else PASS_WORDS
            if not any(w in message for w in words) or any(f" {w} " in message for w in wrong):
                problems.append(f"(b) {where}: message {message!r} for {got['outcome']}")
            if got["outcome"] == "fail" and _equal_numbers(message):
                problems.append(f"(b) {where}: a fail between equal-looking numbers: {message!r}")
    return problems


UNIT_WORDS = ("m", "m/s", "m³/s", "W")
COMPARISONS = ("<", ">", "above", "below", "outside")


def _is_number(token: str) -> bool:
    try:
        float(token.strip("[],"))
    except ValueError:
        return False
    return True


def _quoted(tokens: list[str], i: int) -> bool:
    """Whether ``tokens[i]`` is a compared number: one with a unit after it, inside an
    interval's brackets, the ratio "= Q/Q_BEP" just before the comparison word, or the limit
    just after it; not a pipe number or a speed."""
    word = tokens[i]
    after = tokens[i + 1] if i + 1 < len(tokens) else ""
    before = tokens[i - 1] if i > 0 else ""
    return _is_number(word) and (
        after.strip("[],") in UNIT_WORDS
        or word.startswith("[")
        or word.endswith(("]", ","))
        or (before == "=" and after in COMPARISONS)
        or before in COMPARISONS
    )


def _equal_numbers(message: str) -> bool:
    """A fail message whose compared numbers read the same: "2.13301 m/s ... above 2.13301",
    or a value that reads as one end of the interval it is outside."""
    tokens = message.split()
    at = next((i for i, w in enumerate(tokens) if w in COMPARISONS), None)
    if at is None:
        return False
    left = [tokens[i].strip("[],") for i in range(at) if _quoted(tokens, i)]
    right = [tokens[i].strip("[],") for i in range(at + 1, len(tokens)) if _quoted(tokens, i)]
    if not left or not right:
        return False
    return left[-1] in (right[:2] if tokens[at] == "outside" else right[:1])


def check(name: str, project: Project) -> dict[str, Any]:
    """The record of one project: its outcome, counts and every difference found."""
    record: dict[str, Any] = {"name": name, "profile": profile(name), "differences": []}
    differences: list[str] = record["differences"]
    base = with_curves(project.model_dump(mode="json", by_alias=True, exclude_unset=True))
    try:
        a = _dump(solve_project(Project.model_validate(base), NO_CURVES))
    except TopologyError:
        record["outcome"] = "topology_error"
        return record
    data = with_checks(base)
    b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    record["outcome"] = "checked"
    record["converged"] = bool(b["converged"])
    if a["designChecks"]:
        differences.append(f"(a) A has {len(a['designChecks'])} design check results")
    reported = b.pop("designChecks")
    sections = b["trace"]["methods"]["sections"]
    if not sections or sections[-1]["title"] != "Design checks":
        differences.append("(a) B's last methods section is not 'Design checks'")
    else:
        sections.pop()
    a.pop("designChecks")
    a.pop("timestamp")
    b.pop("timestamp")
    if a != b:
        keys = sorted(k for k in a if a[k] != b.get(k))
        differences.append(f"(a) B's solved state differs from A's in {keys}")
    if not b["converged"]:
        if reported:
            differences.append(f"(c) {len(reported)} results of a solve that did not converge")
    else:
        differences += result_problems(data, b, reported)
    record["outcomes"] = dict(Counter(f"{r['check']}:{r['outcome']}" for r in reported))
    if differences:
        record["outcome"] = "different"
    return record


# --------------------------------------------------------------------------- the corpus


def run(item: Item) -> dict[str, Any]:
    name, spec = item
    try:
        project = load(spec)
    except Exception as ex:  # a corpus file that does not load is not a design-check finding
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "load_error",
            "error": repr(ex),
            "differences": [],
        }
    try:
        return check(name, project)
    except Exception as ex:
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "crash",
            "differences": [f"crash: {ex!r}"],
        }


def check_all(selection: list[Item], workers: int = 1) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order."""
    if workers <= 1:
        return [run(item) for item in selection]
    with Pool(workers) as pool:
        return pool.map(run, selection, chunksize=4)


def summarize(records: list[dict[str, Any]]) -> list[str]:
    """The report's lines (module docstring)."""
    by_profile: dict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        tally = by_profile[r["profile"]]
        tally["projects"] += 1
        tally[r["outcome"]] += 1
        if r.get("converged") is False:
            tally["not_converged"] += 1
        tally.update(r.get("outcomes", {}))
    columns = ["projects", "checked", "different", "not_converged", "topology_error"]
    columns += ["load_error", "crash"]
    outcomes = [f"{c}:{o}" for c in CHECK_IDS for o in ("pass", "fail", "not_evaluated")]
    lines = ["profile " + " ".join(columns + outcomes)]
    total: Counter[str] = Counter()
    for name in sorted(by_profile, key=lambda p: (*PROFILES, p).index(p)):
        tally = by_profile[name]
        total += tally
        lines.append(f"{name} " + " ".join(str(tally[c]) for c in columns + outcomes))
    lines.append("all " + " ".join(str(total[c]) for c in columns + outcomes))
    different = [r for r in records if r["differences"]]
    for r in different:
        lines.append(f"{r['name']}: " + "; ".join(r["differences"][:10]))
    lines.append(f"different: {len(different)}")
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.design_checks_check",
        description="Check the design checks over the corpus (proposal design-checks.md §6).",
    )
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument("--out", default="", help="write every project's record to this file")
    args = parser.parse_args(argv)
    selection = [t for t in items() if t[0].startswith(args.only)]
    print(f"projects: {len(selection)}", flush=True)
    records = check_all(selection, args.workers)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1, sort_keys=True)
    print("\n".join(summarize(records)))
    sys.exit(1 if any(r["differences"] for r in records) else 0)


if __name__ == "__main__":
    main()
