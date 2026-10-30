"""The documentation's structure (docs/README.md).

`CLAUDE.md` is loaded into every AI session, so it must stay small and point at the rest; the
decision record must be contiguous and indexed; and relative links must resolve, since agents
follow them.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
DOCS = ROOT / "docs"
CLAUDE_MD = ROOT / "CLAUDE.md"

# The per-session context cost of CLAUDE.md. It was 119 KB before the decision record moved to
# docs/decisions/ (2026-10-30); the index and the rules fit in 14 KB.
CLAUDE_MD_BUDGET = 16_000

pytestmark = pytest.mark.skipif(not CLAUDE_MD.exists(), reason="repository documents not present")

_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _markdown_files() -> list[Path]:
    if not CLAUDE_MD.exists():
        return []
    return [CLAUDE_MD, ROOT / "README.md", *sorted(DOCS.rglob("*.md"))]


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(path: Path) -> None:
    broken = []
    for match in _LINK.finditer(path.read_text()):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_part = target.split("#")[0]
        if file_part and not (path.parent / file_part).exists():
            broken.append(target)
    assert broken == []


def test_decisions_are_contiguous_and_indexed() -> None:
    files = sorted((DOCS / "decisions").glob("D[0-9][0-9]-*.md"))
    numbers = [int(f.name[1:3]) for f in files]
    assert numbers == list(range(1, len(numbers) + 1)), "decision numbers must be D01…Dnn"
    index = (DOCS / "decisions" / "README.md").read_text()
    claude = CLAUDE_MD.read_text()
    for f in files:
        assert f.name in index, f"{f.name} missing from docs/decisions/README.md"
        assert f"docs/decisions/{f.name}" in claude, f"{f.name} missing from CLAUDE.md's index"


def test_claude_md_stays_small() -> None:
    assert CLAUDE_MD.stat().st_size <= CLAUDE_MD_BUDGET
