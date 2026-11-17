"""The gates' summaries that scripts/record_history.py writes into docs/verified-state.md
(docs/workflow.md §4), read from each tool's real summary lines.

Playwright prints its skipped count on the line before its passed count; the e2e summary read
the skipped count only after the passed one, so docs/verified-state.md said "0 skipped by design"
for a run with 15 skipped. The pytest and Vitest summaries are pinned as they were.
"""

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "record_history.py"


@pytest.fixture(scope="module")
def record_history() -> Iterator[ModuleType]:
    # A script, not a package: loaded from its path, and registered while it runs, since its
    # dataclass resolves its annotations through sys.modules.
    spec = importlib.util.spec_from_file_location("record_history", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _summary(module: ModuleType, gate: str, text: str) -> str:
    (found,) = [g for g in module.GATES if g.name == gate]
    result: str = module.summarize(found, text)
    return result


# The tail of a real `pnpm test:e2e` run (Playwright 1.56.1, list reporter), with 15 tests
# skipped by design.
PLAYWRIGHT_SKIPPED = """\
  ✓  228 [mobile] › tests/workspace.e2e.ts:134:1 › Ctrl+Enter solves, and the results start in the upper part of the pane (1.2s)
  ✓  229 [mobile] › tests/workspace.e2e.ts:160:1 › an empty project offers no Scenarios or Goal seek until it has a component (874ms)
  -  230 [mobile] › tests/workspace.e2e.ts:172:1 › from 1024 px the header names the fluid, and opens its settings

  15 skipped
  215 passed (9.2m)
"""  # noqa: E501, RUF001

# The same reporter's tail when nothing is skipped: no skipped line.
PLAYWRIGHT_NONE_SKIPPED = """\
  ✓  229 [mobile] › tests/workspace.e2e.ts:160:1 › an empty project offers no Scenarios or Goal seek until it has a component (874ms)
  ✓  230 [mobile] › tests/workspace.e2e.ts:172:1 › from 1024 px the header names the fluid, and opens its settings (1.0s)

  230 passed (9.3m)
"""  # noqa: E501, RUF001

# The tail of a real `uv run pytest -n auto -q` run.
PYTEST = """\
........................................................................ [ 99%]
..................................................                       [100%]
7178 passed in 371.41s (0:06:11)
"""

# The tail of a real `pnpm test` run (Vitest 4).
VITEST = """\
https://svelte.dev/e/perf_avoid_nested_class

 Test Files  122 passed (122)
      Tests  1682 passed (1682)
   Start at  05:10:29
   Duration  134.28s (transform 30.64s, setup 23.46s, import 66.82s, tests 254.97s, environment 34.12s)
"""  # noqa: E501


def test_the_e2e_summary_reads_playwrights_skipped_count_before_its_passed_count(
    record_history: ModuleType,
) -> None:
    assert _summary(record_history, "e2e", PLAYWRIGHT_SKIPPED) == "215 passed, 15 skipped by design"


def test_the_e2e_summary_without_a_skipped_line_says_0_skipped(record_history: ModuleType) -> None:
    assert (
        _summary(record_history, "e2e", PLAYWRIGHT_NONE_SKIPPED)
        == "230 passed, 0 skipped by design"
    )


def test_the_pytest_summary_is_unchanged(record_history: ModuleType) -> None:
    assert _summary(record_history, "pytest", PYTEST) == "7178 passed"
    assert (
        _summary(record_history, "pytest", "7178 passed, 3 skipped in 371.41s (0:06:11)\n")
        == "7178 passed"
    )


def test_the_vitest_summary_is_unchanged(record_history: ModuleType) -> None:
    assert _summary(record_history, "vitest", VITEST) == "1682 passed (122 files)"


def test_a_gate_without_a_summary_pattern_reads_clean(record_history: ModuleType) -> None:
    assert _summary(record_history, "ruff", "All checks passed!\n") == "clean"
