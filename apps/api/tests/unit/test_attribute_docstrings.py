"""Attribute docstrings stay under the name they document.

A bare string directly under an assignment in a module or class body is that name's docstring,
the convention the API's models and the solver's aliases and fields use (editors and
documentation tools pair them so). A name inserted between an assignment and its docstring
leaves the first undocumented and gives the second two strings, the later one describing another
name: ``orifice.Basis`` lost its loss, reading and move text to ``FluidReason`` so (2026-11-03).
"""

import ast
from pathlib import Path

import pytest

import opensolve_pipe

PACKAGE = Path(opensolve_pipe.__file__).resolve().parent
ASSIGNMENTS = (ast.Assign, ast.AnnAssign, ast.TypeAlias)


def _is_string(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _orphaned_strings(path: Path) -> list[str]:
    """Each bare string in a module or class body, after its first statement, that does not
    directly follow an assignment, as "line: what precedes it"."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef):
            continue
        for before, statement in zip(node.body, node.body[1:], strict=False):
            if _is_string(statement) and not isinstance(before, ASSIGNMENTS):
                found.append(f"{statement.lineno}: after {type(before).__name__}")
    return found


@pytest.mark.parametrize(
    "path", sorted(PACKAGE.rglob("*.py")), ids=lambda p: str(p.relative_to(PACKAGE))
)
def test_every_attribute_docstring_follows_its_assignment(path: Path) -> None:
    assert _orphaned_strings(path) == []
