"""The documentation's structure (docs/README.md).

`CLAUDE.md` is loaded into every AI session, so it must stay small and point at the rest; the
decision record must be contiguous and indexed; and relative links must resolve, since agents
follow them.

Parallel sessions each take "the next free" decision number, method version and spec section on
their own branch, and the second to merge must renumber (docs/workflow.md §5; D20–D23 were each
renumbered so). The checks below make a collision fail CI on the merged tree instead of relying
on review: each index row names its own file, each version a decision cites exists, the version
`CLAUDE.md` states is the current one, and numbered headings and TSD §12's items are unique.
"""

import re
from pathlib import Path

import pytest

from opensolve_pipe.services.solver import METHOD_CHANGELOG, METHOD_VERSION

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


_CITED_DOC = re.compile(r"\bdocs/[A-Za-z0-9_./-]+\.md\b")
_CODE_DIRS = (
    "apps/api/src",
    "apps/api/tests",
    "apps/api/scripts",
    "apps/web/src",
    "apps/web/tests",
)
_CODE_SUFFIXES = {".py", ".ts", ".js", ".svelte"}


def test_documents_cited_in_code_exist() -> None:
    """Comments and docstrings cite the record they implement (CLAUDE.md Conventions), as
    `docs/proposals/<name>.md, item 4`. A record that a later branch is to write leaves the
    citation dangling on main if this branch merges first."""
    missing = []
    for directory in _CODE_DIRS:
        for path in sorted((ROOT / directory).rglob("*")):
            if path.suffix not in _CODE_SUFFIXES or "node_modules" in path.parts:
                continue
            for cited in sorted(set(_CITED_DOC.findall(path.read_text()))):
                if not (ROOT / cited).is_file():
                    missing.append(f"{path.relative_to(ROOT)}: {cited}")
    assert missing == []


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


# One row per decision in each index: CLAUDE.md's "| D22 | … | [`docs/decisions/D22-…`]" and
# docs/decisions/README.md's "| [D22](D22-…) | …".
_CLAUDE_ROW = re.compile(r"^\| D(\d+) \|.*?docs/decisions/D(\d\d)-", re.MULTILINE)
_README_ROW = re.compile(r"^\| \[D(\d+)\]\(D(\d\d)-", re.MULTILINE)
_VERSION_IN_ROW = re.compile(r"\((\d+\.\d+\.\d+)\)")


def _decision_numbers() -> list[int]:
    return sorted(int(f.name[1:3]) for f in (DOCS / "decisions").glob("D[0-9][0-9]-*.md"))


@pytest.mark.parametrize(
    ("index", "row"),
    [("CLAUDE.md", _CLAUDE_ROW), ("docs/decisions/README.md", _README_ROW)],
    ids=["CLAUDE.md", "decisions/README.md"],
)
def test_each_decision_has_one_index_row_naming_its_own_file(
    index: str, row: re.Pattern[str]
) -> None:
    """A renumbering at merge that moves the file but not its row (or adds a second row with the
    same number) leaves "Dn" citing the wrong decision."""
    rows = row.findall((ROOT / index).read_text())
    mismatched = [(label, file) for label, file in rows if int(label) != int(file)]
    assert mismatched == [], f"rows whose label is not their file's number: {mismatched}"
    assert sorted(int(label) for label, _ in rows) == _decision_numbers()


def test_versions_cited_by_decisions_are_in_the_changelog() -> None:
    """A decision row citing a method version (as "built (1.6.0)") names one METHOD_CHANGELOG
    holds, so two branches that both took the next version cannot both merge unnoticed."""
    known = {entry["version"] for entry in METHOD_CHANGELOG}
    for index, row in (("CLAUDE.md", _CLAUDE_ROW), ("docs/decisions/README.md", _README_ROW)):
        for line in (ROOT / index).read_text().splitlines():
            if row.match(line):
                cited = set(_VERSION_IN_ROW.findall(line))
                assert cited <= known, f"{index}: {line[:60]}… cites {cited - known}"


def test_claude_md_states_the_current_method_version() -> None:
    stated = re.findall(r"`METHOD_VERSION` (\d+\.\d+\.\d+)", CLAUDE_MD.read_text())
    assert stated == [METHOD_VERSION]


_NUMBERED_HEADING = re.compile(r"^#+ (\d+(?:\.\d+)*)\.? ")


@pytest.mark.parametrize("spec", ["PRD.md", "SDD.md", "TSD.md"])
def test_numbered_headings_are_unique(spec: str) -> None:
    """Code cites `TSD §4.10`; two branches that each added "the next" subsection would give one
    number two meanings (docs/workflow.md §5, item 2)."""
    numbers: list[str] = []
    in_code = False
    for line in (DOCS / spec).read_text().splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and (match := _NUMBERED_HEADING.match(line)):
            numbers.append(match.group(1))
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert duplicates == [], f"{spec} headings numbered more than once: {duplicates}"


def test_tsd_section_12_items_are_numbered_1_to_n() -> None:
    """TSD §12's "Decided" and "Open" lists are cited by item number (`TSD §12 item 17`)."""
    tsd = (DOCS / "TSD.md").read_text()
    section = tsd[tsd.index("\n## 12.") + 1 :]
    if (end := section.find("\n## ")) != -1:
        section = section[:end]
    lists: list[list[int]] = []
    for line in section.splitlines():
        if re.match(r"\*\*(Decided|Open)", line):
            lists.append([])
        elif lists and (match := re.match(r"(\d+)\. ", line)):
            lists[-1].append(int(match.group(1)))
    assert len(lists) >= 2, "TSD §12 should hold its Decided and Open lists"
    for items in lists:
        assert items == list(range(1, len(items) + 1))
