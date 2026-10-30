"""Run the gates and write their counts into docs/history.md (docs/workflow.md §4).

    uv run python scripts/record_history.py              # every gate, then rewrite the block
    uv run python scripts/record_history.py --skip e2e   # a quick pass
    uv run python scripts/record_history.py --dry-run    # print the block, write nothing

Each gate is a command with a parser for its summary line. The block between
``<!-- verified-state:start -->`` and ``<!-- verified-state:end -->`` in docs/history.md is
replaced with a table of the results, the commit and the date. A failed gate leaves the file
unchanged (unless ``--force``) and the script exits 1; its log names where the output went.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

API = Path(__file__).resolve().parents[1]
ROOT = API.parent
WEB = ROOT / "apps" / "web"
HISTORY = ROOT / "docs" / "history.md"
START = "<!-- verified-state:start -->"
END = "<!-- verified-state:end -->"


@dataclass(frozen=True)
class Gate:
    name: str
    area: str
    cwd: Path
    command: tuple[str, ...]
    summary: tuple[tuple[str, str], ...] = ()
    """``(regex, template)`` pairs tried in order on the output; the first match's groups fill
    the template. With none, or no match, a passing gate reads "clean"."""


GATES: tuple[Gate, ...] = (
    Gate(
        "pytest",
        "API pytest",
        API,
        ("uv", "run", "pytest", "-q", "-p", "no:cacheprovider"),
        ((r"(\d+) passed(?:, (\d+) skipped)?", "{0} passed"),),
    ),
    Gate("ruff", "API ruff", API, ("uv", "run", "ruff", "check", ".")),
    Gate("format", "API ruff format", API, ("uv", "run", "ruff", "format", "--check", ".")),
    Gate("mypy", "API mypy strict", API, ("uv", "run", "mypy", "src")),
    Gate(
        "pipe-data",
        "API pipe data",
        API,
        ("uv", "run", "python", "scripts/generate_pipe_data.py", "--check"),
    ),
    Gate(
        "relief-data",
        "API relief data",
        API,
        ("uv", "run", "python", "scripts/generate_relief_data.py", "--check"),
    ),
    Gate(
        "gen-types",
        "Web generated API types",
        WEB,
        ("sh", "-c", "pnpm gen:types && git diff --exit-code -- src/lib/api"),
    ),
    Gate(
        "check",
        "Web svelte-check",
        WEB,
        ("pnpm", "check"),
        ((r"found 0 errors and 0 warnings in (\d+) files", "clean ({0} files)"),),
    ),
    Gate("lint", "Web Prettier + ESLint", WEB, ("pnpm", "lint")),
    Gate(
        "vitest",
        "Web Vitest",
        WEB,
        ("pnpm", "test"),
        ((r"Test Files\s+(\d+) passed.*?Tests\s+(\d+) passed", "{1} passed ({0} files)"),),
    ),
    Gate(
        "e2e",
        "Web Playwright (desktop 1280×800 and mobile 390×844, one worker)",
        WEB,
        ("pnpm", "test:e2e"),
        ((r"(\d+) passed(?:.*?(\d+) skipped)?", "{0} passed, {1} skipped by design"),),
    ),
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def run_gate(gate: Gate, log_dir: Path) -> tuple[bool, str]:
    """Run one gate; return (passed, summary) and keep its output in ``log_dir``."""
    log = log_dir / f"{gate.name}.log"
    with log.open("w") as out:
        code = subprocess.run(
            gate.command, cwd=gate.cwd, stdout=out, stderr=subprocess.STDOUT, check=False
        ).returncode
    text = log.read_text()
    summary = "clean"
    for pattern, template in gate.summary:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            groups = tuple("0" if g is None else g for g in match.groups())
            summary = template.format(*groups)
            break
    if code != 0:
        return False, f"**FAILED** (exit {code}; see {log})"
    return True, summary


def render(rows: list[tuple[str, str]], skipped: list[Gate]) -> str:
    sha = _git("rev-parse", "--short", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    today = dt.date.today().isoformat()
    lines = [
        START,
        f"Verified state at `{sha}` (`{branch}`, {today}), written by "
        "`apps/api/scripts/record_history.py`:",
        "",
        "| Area | Result |",
        "|---|---|",
        *[f"| {area} | {result} |" for area, result in rows],
    ]
    if skipped:
        names = ", ".join(g.area for g in skipped)
        lines.append(f"| Not run this time | {names} |")
    lines.append(END)
    return "\n".join(lines)


def write_block(block: str) -> None:
    text = HISTORY.read_text()
    start, end = text.index(START), text.index(END) + len(END)
    HISTORY.write_text(text[:start] + block + text[end:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    names = [g.name for g in GATES]
    parser.add_argument("--skip", nargs="*", default=[], choices=names, metavar="GATE")
    parser.add_argument("--only", nargs="*", default=None, choices=names, metavar="GATE")
    parser.add_argument("--dry-run", action="store_true", help="print the block; write nothing")
    parser.add_argument("--force", action="store_true", help="write the block even on a failure")
    parser.add_argument("--log-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    selected = [g for g in GATES if (args.only is None or g.name in args.only)]
    skipped = [g for g in selected if g.name in args.skip]
    log_dir = args.log_dir or Path(tempfile.mkdtemp(prefix="opensolve-gates-"))
    log_dir.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str]] = []
    failed = False
    for gate in selected:
        if gate in skipped:
            continue
        print(f"→ {gate.area}: {' '.join(gate.command)}", flush=True)
        ok, summary = run_gate(gate, log_dir)
        failed |= not ok
        rows.append((gate.area, summary))
        print(f"  {summary}", flush=True)

    block = render(rows, skipped)
    print("\n" + block)
    if args.dry_run:
        return 1 if failed else 0
    if failed and not args.force:
        print(f"\nA gate failed; docs/history.md left unchanged (logs in {log_dir}).")
        return 1
    write_block(block)
    print(f"\nWrote the block into {HISTORY.relative_to(ROOT)} (logs in {log_dir}).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
