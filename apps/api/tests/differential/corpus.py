"""Dump every solved state of a fixed corpus, to compare two versions of the solver exactly.

    uv run python -m tests.differential.corpus OUTDIR [--workers N] [--only PREFIX] [--resume]
                                                      [--solver-options NAME=VALUE,...] [--dry-run]

Solves with the code that is importable (run it from inside the apps/api of the tree to test, see
TSD §10.4) and writes OUTDIR/<project>.json: the ``SolvedState`` API JSON with system curves, or
``{"error": ...}`` / ``{"load_error": ...}``; OUTDIR/_times.json holds each solve's time.
Each file is written to <project>.json.tmp and renamed into place, so an interrupted run leaves
no partial dump. An OUTDIR that already holds dumps is refused, since they may come from another
commit; ``--resume`` continues an interrupted run there, keeping every existing file as it is.
``tests.differential.compare A B`` compares two dumps.

``--solver-options NAME=VALUE,...`` overrides those fields of every project's
``settings.solverOptions`` (``SolverOptions``: snake_case names, checked against its bounds),
for example ``tolerance=1e-13,max_iterations=1000`` for the fixed-point dumps of proposal
vfd-slice2-discharge-pressure.md §2.7 criterion 7; the other fields keep each project's values,
and the methods summary of every dump states the settings it was solved with.
OUTDIR/_solver_options.json records the override ({} without one); ``--resume`` refuses a run
whose override differs from it (a directory without that file was dumped without one).

Corpus (names are the file names):

- ``ref_<case>``: every reference case project (``tests/reference/cases``), 41-point curves;
- ``unit_<name>``: the unit-test data networks (``tests/unit/data/*/``), 41-point curves;
- ``ladder_<rungs>_<pumps>_<loss>_<library>``: six Crane-tee ladders (``networks.ladder``);
- ``wye_step_<i>``: a step-hold probe wye at six levels of R3 (``networks.step_hold_wye``; not
  the reference case ``wye_crane_step_hold``, which is ``ref_wye_crane_step_hold``);
- ``fuzz_<seed>``: the differential-test networks of seeds 0-2999 (``generator``), 11-point
  curves;
- ``fuzzfc_<seed>``: the generator profile 'flow_control' (flow-controlled pumps, CLAUDE.md D11)
  on seeds 10000-10999, 11-point curves. A tree from before that profile has none of them
  ("missing in A" in ``compare``, not counted as different);
- ``fuzzaf_<seed>``: the generator profile 'assigned_flow' (assigned-flow nodes, TSD §4.8) on
  seeds 20000-20999, 11-point curves; likewise missing in a tree from before that profile.
"""

import argparse
import functools
import json
import os
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import opensolve_pipe
from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.project import Project, SolverOptions
from opensolve_pipe.services.solver import solve_project
from tests.differential import networks
from tests.differential.generator import ASSIGNED_FLOW, FLOW_CONTROL, generate

API_ROOT = Path(__file__).resolve().parents[2]
"""The apps/api tree whose tests/ this module belongs to (its corpus files are read)."""

LADDERS = [
    (7, 1, "crane", True),
    (47, 1, "crane", True),
    (45, 5, "crane", True),
    (47, 1, "ideal", False),
    (100, 1, "crane", True),
    (20, 2, "crane", False),
]
WYE_LEVELS = [10.0, 10.2, 10.21, 10.22, 10.23, 10.25]
FUZZ_SEEDS = range(3000)
FLOW_CONTROL_SEEDS = range(10_000, 11_000)
ASSIGNED_FLOW_SEEDS = range(20_000, 21_000)

Spec = tuple[str, Any, int]  # (kind, argument, system-curve points)
Item = tuple[str, Spec]


def items() -> list[Item]:
    out: list[Item] = []
    for f in sorted(API_ROOT.glob("tests/reference/cases/*.json")):
        out.append(("ref_" + f.stem, ("file", str(f), 41)))
    for f in sorted(API_ROOT.glob("tests/unit/data/*/*.json")):
        out.append(("unit_" + f.stem, ("file", str(f), 41)))
    for rungs, pumps, loss, lib in LADDERS:
        out.append(
            (f"ladder_{rungs}_{pumps}_{loss}_{lib}", ("ladder", (rungs, pumps, loss, lib), 41))
        )
    for i, lv in enumerate(WYE_LEVELS):
        out.append((f"wye_step_{i}", ("wye", lv, 41)))
    for s in FUZZ_SEEDS:
        out.append((f"fuzz_{s}", ("fuzz", s, 11)))
    for s in FLOW_CONTROL_SEEDS:
        out.append((f"fuzzfc_{s}", ("fuzz_flow_control", s, 11)))
    for s in ASSIGNED_FLOW_SEEDS:
        out.append((f"fuzzaf_{s}", ("fuzz_assigned_flow", s, 11)))
    return out


def load(spec: Spec) -> Project:
    kind, arg, _ = spec
    if kind == "file":
        d = json.loads(Path(arg).read_text())
        return Project.model_validate(d.get("project", d))
    if kind == "ladder":
        return networks.ladder(*arg)
    if kind == "wye":
        return networks.step_hold_wye(arg)
    if kind == "fuzz":
        # through the API JSON, as the app sends it
        return Project.model_validate(generate(arg).model_dump(mode="json", by_alias=True))
    if kind in ("fuzz_flow_control", "fuzz_assigned_flow"):
        project = generate(arg, FLOW_CONTROL if kind == "fuzz_flow_control" else ASSIGNED_FLOW)
        return Project.model_validate(project.model_dump(mode="json", by_alias=True))
    raise ValueError(kind)


def solver_options(text: str) -> dict[str, Any]:
    """The fields of ``--solver-options`` ('tolerance=1e-13,max_iterations=1000'), validated by
    ``SolverOptions`` (its types and bounds); raises ValueError for anything else."""
    fields: dict[str, str] = {}
    for part in text.split(","):
        name, sep, value = (s.strip() for s in part.partition("="))
        if not sep or not name or not value:
            raise ValueError(f"expected NAME=VALUE, got {part.strip()!r}")
        if name not in SolverOptions.model_fields:
            known = ", ".join(SolverOptions.model_fields)
            raise ValueError(f"unknown solver option {name!r} (one of {known})")
        if name in fields:
            raise ValueError(f"solver option {name!r} given twice")
        fields[name] = value
    try:
        checked = SolverOptions.model_validate(fields)
    except ValidationError as ex:
        reasons = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in ex.errors())
        raise ValueError(reasons) from None
    return {name: getattr(checked, name) for name in fields}


def with_solver_options(project: Project, options: dict[str, Any]) -> Project:
    """The project with those fields of its solver options replaced (none: unchanged)."""
    if not options:
        return project
    settings = project.settings
    replaced = settings.solver_options.model_copy(update=options)
    return project.model_copy(
        update={"settings": settings.model_copy(update={"solver_options": replaced})}
    )


def write_json(path: str, data: Any, **kwargs: Any) -> None:
    """Write JSON to ``path`` through ``path``.tmp and a rename, so ``path`` is never partial."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, **kwargs)
    os.replace(tmp, path)


def run(item: Item, out_dir: str, options: dict[str, Any] | None = None) -> tuple[str, str, float]:
    name, spec = item
    path = os.path.join(out_dir, name + ".json")
    if os.path.exists(path):
        return name, "cached", 0.0
    try:
        p = with_solver_options(load(spec), options or {})
    except Exception as ex:
        write_json(path, {"load_error": repr(ex)})
        return name, "load_error", 0.0
    t = time.perf_counter()
    try:
        st = solve_project(p, SolveOptions(include_system_curve=True, system_curve_points=spec[2]))
        d = st.model_dump(mode="json", by_alias=True)
    except Exception as ex:
        d = {"error": repr(ex)}
    dt = time.perf_counter() - t
    write_json(path, d, sort_keys=True)
    return name, "ok", dt


def sources() -> tuple[Path, Path]:
    """(solver package directory, corpus tree); refuses a solver from another tree."""
    solver = Path(opensolve_pipe.__file__).resolve().parent
    if not solver.is_relative_to(API_ROOT / "src"):
        raise SystemExit(
            f"opensolve_pipe is imported from {solver}, not from {API_ROOT / 'src'}: run from"
            f" inside that tree's apps/api with uv run --project <that apps/api>"
        )
    return solver, API_ROOT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.corpus",
        description="Dump every solved state of the corpus (TSD §10.4).",
    )
    parser.add_argument("out", help="output directory")
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue an interrupted run in OUTDIR, keeping every dump already there",
    )
    parser.add_argument(
        "--solver-options",
        default="",
        metavar="NAME=VALUE,...",
        help="override these fields of every project's solver options, e.g."
        " tolerance=1e-13,max_iterations=1000",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the sources and the selection, solve nothing"
    )
    args = parser.parse_args(argv)
    try:
        options = solver_options(args.solver_options) if args.solver_options else {}
    except ValueError as ex:
        parser.error(f"--solver-options: {ex}")
    solver, tree = sources()
    todo = [t for t in items() if t[0].startswith(args.only)]
    print(f"solver: {solver}\ncorpus: {tree}\nprojects: {len(todo)}", flush=True)
    if options:
        shown = ", ".join(f"{k}={v!r}" for k, v in options.items())
        print(f"solver options of every project: {shown}", flush=True)
    out_dir = os.path.abspath(args.out)
    held = [f for f in Path(out_dir).glob("*.json") if not f.name.startswith("_")]
    if held and not args.resume:
        raise SystemExit(
            f"{out_dir} already holds {len(held)} dumps, which may come from another commit:"
            " name a new or empty directory, or pass --resume to continue a run there"
        )
    recorded = os.path.join(out_dir, "_solver_options.json")
    if held:
        before = json.loads(Path(recorded).read_text()) if os.path.exists(recorded) else {}
        if before != options:
            raise SystemExit(
                f"{out_dir} was dumped with solver options {before}, not {options}:"
                " resume it with the same --solver-options, or name a new directory"
            )
    if args.dry_run:
        return
    os.makedirs(out_dir, exist_ok=True)
    write_json(recorded, options, sort_keys=True)
    times = {}
    with Pool(args.workers) as pool:
        work = functools.partial(run, out_dir=out_dir, options=options)
        for name, _, dt in pool.imap_unordered(work, todo, chunksize=4):
            times[name] = dt
    write_json(os.path.join(out_dir, "_times.json"), times, indent=0, sort_keys=True)
    print("done", len(times), "total", round(sum(times.values()), 1), "s")


if __name__ == "__main__":
    main()
