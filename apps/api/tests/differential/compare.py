"""Compare two corpus dumps (``corpus.py``) exactly.

    uv run python -m tests.differential.compare A B [--ignore PATH ...]

For every A/<project>.json (files starting with '_' are skipped) the JSON of B/<project>.json
must be equal, ignoring ``timestamp``; numbers compare with ==, NaN equal to NaN. Prints
"identical N, different M", the projects missing from either side, and up to 25 different
projects with their number of numeric differences, the largest relative one and the first three
other differences (keys, list lengths, values). A file that cannot be read or parsed (a dump cut
short, for example) is listed as unreadable and counts as different. Exit status 1 when a
project differs.

``--ignore PATH`` (repeatable) leaves out the values at a path of the dump: its dict keys and
list indices from the root, separated by '.', each segment matched as an ``fnmatch`` pattern
(``*`` matches any one key or index), the whole path at the same depth. A key present on one
side only is also left out there. For example, a solver change that adds the new field
``control`` to every pump result and changes the method version (proposal vfd-pump-modes.md
§7.5) is compared with ``--ignore 'pumpResults.*.control' --ignore methodVersion --ignore
trace.methods.methodVersion``. Each pattern's count of values left out, and in how many
projects, is printed after the totals, so that an ignore broader than intended shows.
"""

import argparse
import fnmatch
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

IGNORE = {"timestamp"}
"""Keys left out at any depth."""

Difference = tuple[Any, ...]  # (kind, path, a, b[, relative difference])
Pattern = tuple[str, ...]  # an --ignore path, split on '.'


def ignored(segments: tuple[str, ...], patterns: Sequence[Pattern]) -> Pattern | None:
    """The first pattern that matches the whole path, or None."""
    for pattern in patterns:
        if len(pattern) == len(segments) and all(
            fnmatch.fnmatchcase(seg, pat) for seg, pat in zip(segments, pattern, strict=True)
        ):
            return pattern
    return None


def walk(
    a: Any,
    b: Any,
    path: str,
    out: list[Difference],
    segments: tuple[str, ...] = (),
    patterns: Sequence[Pattern] = (),
    hits: dict[Pattern, int] | None = None,
) -> None:
    """Differences between a and b (``path`` for display); values at a path matching one of
    ``patterns`` are left out and counted in ``hits``."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in IGNORE:
                continue
            pattern = ignored((*segments, k), patterns)
            if pattern is not None:
                if hits is not None:
                    hits[pattern] = hits.get(pattern, 0) + 1
                continue
            if k not in a or k not in b:
                out.append(("key", path + "/" + k, a.get(k, "<missing>"), b.get(k, "<missing>")))
                continue
            walk(a[k], b[k], path + "/" + k, out, (*segments, k), patterns, hits)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(("len", path, len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            pattern = ignored((*segments, str(i)), patterns)
            if pattern is not None:
                if hits is not None:
                    hits[pattern] = hits.get(pattern, 0) + 1
                continue
            walk(x, y, f"{path}[{i}]", out, (*segments, str(i)), patterns, hits)
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


def compare_dirs(a_dir: Path, b_dir: Path, ignore: Sequence[str] = ()) -> tuple[list[str], int]:
    """(report lines, number of different projects); ``ignore``: paths left out (module
    docstring)."""
    lines = []
    same = diff = 0
    worst = []
    patterns = [tuple(p.split(".")) for p in ignore]
    left_out: dict[Pattern, tuple[int, int]] = {}  # pattern -> (values, projects)
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
        hits: dict[Pattern, int] = {}
        walk(a, b, "", out, (), patterns, hits)
        for pattern, n in hits.items():
            values, projects = left_out.get(pattern, (0, 0))
            left_out[pattern] = (values + n, projects + 1)
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
    for pattern in patterns:
        values, projects = left_out.get(pattern, (0, 0))
        lines.append(f"ignored {'.'.join(pattern)}: {values} values in {projects} projects")
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
        help="leave out the values at this path ('.'-separated keys and indices, fnmatch"
        " patterns per segment, e.g. 'pumpResults.*.control'); repeatable",
    )
    args = parser.parse_args(argv)
    lines, diff = compare_dirs(args.a, args.b, args.ignore)
    print("\n".join(lines))
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
