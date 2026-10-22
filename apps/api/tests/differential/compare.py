"""Compare two corpus dumps (``corpus.py``) exactly.

    uv run python -m tests.differential.compare A B

For every A/<project>.json (files starting with '_' are skipped) the JSON of B/<project>.json
must be equal, ignoring ``timestamp``; numbers compare with ==, NaN equal to NaN. Prints
"identical N, different M", the projects missing from either side, and up to 25 different
projects with their number of numeric differences, the largest relative one and the first three
other differences (keys, list lengths, values). Exit status 1 when a project differs.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

IGNORE = {"timestamp"}

Difference = tuple[Any, ...]  # (kind, path, a, b[, relative difference])


def walk(a: Any, b: Any, path: str, out: list[Difference]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in IGNORE:
                continue
            if k not in a or k not in b:
                out.append(("key", path + "/" + k, a.get(k, "<missing>"), b.get(k, "<missing>")))
                continue
            walk(a[k], b[k], path + "/" + k, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(("len", path, len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            walk(x, y, f"{path}[{i}]", out)
    elif isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        if a != b and not (isinstance(a, float) and math.isnan(a) and math.isnan(b)):
            rel = abs(a - b) / max(abs(a), abs(b), 1e-300)
            out.append(("num", path, a, b, rel))
    elif a != b:
        out.append(("val", path, a, b))


def compare_dirs(a_dir: Path, b_dir: Path) -> tuple[list[str], int]:
    """(report lines, number of different projects)."""
    lines = []
    same = diff = 0
    worst = []
    for fa in sorted(a_dir.glob("*.json")):
        name = fa.name
        if name.startswith("_"):
            continue
        fb = b_dir / name
        if not fb.exists():
            lines.append(f"missing in B: {name}")
            continue
        out: list[Difference] = []
        walk(json.loads(fa.read_text()), json.loads(fb.read_text()), "", out)
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
    args = parser.parse_args(argv)
    lines, diff = compare_dirs(args.a, args.b)
    print("\n".join(lines))
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
