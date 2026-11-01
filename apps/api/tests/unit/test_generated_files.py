"""Every generated file has the `generated` merge driver (docs/workflow.md §6).

A merge keeps a branch's copy of a generated file instead of merging it line by line, and
.claude/hooks/pre-push.sh regenerates it on the merged tree before the push; a file the
generator writes but `.gitattributes` does not list would be merged as text, its two halves
neither side's output (CLAUDE.md, Rules: generated files are never edited by hand).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
ATTRIBUTES = ROOT / ".gitattributes"
GEN_TYPES = ROOT / "apps" / "web" / "scripts" / "gen-api-types.sh"
WEB = ROOT / "apps" / "web"

pytestmark = pytest.mark.skipif(not GEN_TYPES.exists(), reason="repository files not present")


def _generated() -> set[str]:
    listed = set()
    for line in ATTRIBUTES.read_text().splitlines():
        fields = line.split()
        if fields and not line.startswith("#") and "merge=generated" in fields[1:]:
            listed.add(fields[0])
    return listed


def _gen_types_outputs() -> set[str]:
    """The files gen-api-types.sh writes: its `> file` redirections and `-o file` options."""
    script = GEN_TYPES.read_text()
    paths = re.findall(r"(?:^|\s)(?:>|-o)\s+(src/\S+)", script, re.MULTILINE)
    return {str((WEB / p).relative_to(ROOT)) for p in paths}


def test_gen_types_outputs_are_found() -> None:
    outputs = _gen_types_outputs()
    assert "apps/web/src/lib/api/openapi.json" in outputs
    assert "apps/web/src/lib/api/schema.d.ts" in outputs


def test_every_generated_file_has_the_generated_merge_driver() -> None:
    expected = _gen_types_outputs() | {
        "apps/api/src/opensolve_pipe/data/pipe_materials.json",
        "apps/api/src/opensolve_pipe/data/api526_orifices.json",
        "docs/verified-state.md",
    }
    assert expected - _generated() == set()


def test_every_listed_file_exists() -> None:
    assert {p for p in _generated() if not (ROOT / p).exists()} == set()
