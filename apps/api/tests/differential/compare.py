"""Compare two corpus dumps (``corpus.py``) exactly.

    uv run python -m tests.differential.compare A B [--ignore PATH ...] [--ignore-null PATH ...]

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
"""

import argparse
import fnmatch
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NamedTuple

IGNORE = {"timestamp"}
"""Keys left out at any depth."""

MISSING = object()
"""The value of a key one side does not have."""

Difference = tuple[Any, ...]  # (kind, path, a, b[, relative difference])
Pattern = tuple[str, ...]  # an --ignore or --ignore-null path, split on '.'


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


def walk(
    a: Any,
    b: Any,
    path: str,
    out: list[Difference],
    segments: tuple[str, ...] = (),
    rules: Sequence[Ignore] = (),
    hits: dict[Ignore, int] | None = None,
) -> None:
    """Differences between a and b (``path`` for display); values that one of ``rules`` leaves
    out (``ignored``) are counted in ``hits``."""
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
            walk(a[k], b[k], path + "/" + k, out, (*segments, k), rules, hits)
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
            walk(x, y, f"{path}[{i}]", out, (*segments, str(i)), rules, hits)
    elif isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        if a != b and not (isinstance(a, float) and math.isnan(a) and math.isnan(b)):
            rel = abs(a - b) / max(abs(a), abs(b), 1e-300)
            out.append(("num", path, a, b, rel))
    elif a != b:
        out.append(("val", path, a, b))


def read(path: Path) -> tuple[Any, str | None]:
    """(parsed JSON, None), or (None, the error) when the file cannot be read or parsed."""
    try:
        return json.loads(path.read_text()), None
    except (OSError, ValueError) as ex:  # ValueError: JSONDecodeError, UnicodeDecodeError
        return None, f"{type(ex).__name__}: {ex}"


def compare_dirs(
    a_dir: Path, b_dir: Path, ignore: Sequence[str] = (), ignore_null: Sequence[str] = ()
) -> tuple[list[str], int]:
    """(report lines, number of different projects); ``ignore``: paths left out whatever their
    values, ``ignore_null``: paths left out where null or absent on both sides (module
    docstring)."""
    lines = []
    same = diff = 0
    worst = []
    rules = [Ignore(tuple(p.split("."))) for p in ignore]
    rules += [Ignore(tuple(p.split(".")), null=True) for p in ignore_null]
    left_out: dict[Ignore, tuple[int, int]] = {}  # rule -> (values, projects)
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
            diff += 1
            errs = [f"{side} {err}" for side, err in (("A", err_a), ("B", err_b)) if err]
            lines.append(f"unreadable: {name}: {'; '.join(errs)}")
            continue
        out: list[Difference] = []
        hits: dict[Ignore, int] = {}
        walk(a, b, "", out, (), rules, hits)
        for rule, n in hits.items():
            values, projects = left_out.get(rule, (0, 0))
            left_out[rule] = (values + n, projects + 1)
        if not out:
            same += 1
            continue
        diff += 1
        nums = [o for o in out if o[0] == "num"]
        others = [o for o in out if o[0] != "num"]
        mx = max((o[4] for o in nums), default=0.0)
        worst.append((mx, name, len(nums), others[:3]))
    for fb in sorted(b_dir.glob("*.json")):
        if not fb.name.startswith("_") and not (a_dir / fb.name).exists():
            lines.append(f"missing in A: {fb.name}")
    lines.append(f"identical {same}, different {diff}")
    for rule in rules:
        values, projects = left_out.get(rule, (0, 0))
        lines.append(f"ignored {rule}: {values} values in {projects} projects")
    for mx, name, n, others in sorted(worst, key=lambda x: -x[0])[:25]:
        shown = [(o[0], o[1], str(o[2])[:80], str(o[3])[:80]) for o in others]
        lines.append(f"  {name}: {n} numeric diffs, max rel {mx:.3g}; other: {shown}")
    return lines, diff


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.compare",
        description="Compare two corpus dumps exactly (TSD §10.4).",
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
    args = parser.parse_args(argv)
    lines, diff = compare_dirs(args.a, args.b, args.ignore, args.ignore_null)
    print("\n".join(lines))
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
