"""Each test module sends from client addresses of its own.

The rate limit (60 requests a minute on the solve, system-curve, goal-seek and pump-group-curve
routes) counts by client key (``client_key``, SDD §7.2) in one table per app
(``middleware.RateLimit``), and every module in a pytest process shares the one app. Two modules
that send from the same addresses can therefore pass the limit together and fail with 429
``RATE_LIMITED`` on tests that check nothing of the kind, in any run that puts both in one
process within a minute: the pump-group one-pump-off module, given the project library
reference tests' 10.77.0.0/16, failed 15 of its 17 tests run beside them.

This test reads every ``TestClient(…, client=(address, port))`` written under ``apps/api/tests``
and asserts that no two modules' addresses can meet. An address is written whole (a string, or
a name a function binds only to strings) or as a range (an f-string: the text before its first
replacement field, which may continue with any address). Two whole addresses meet when their
keys are equal (an IPv6 address counts by its /64); a range meets an address or a range that
starts with it, or with which it starts. A ``TestClient`` given no address is not checked: it
sends as ``testclient``, which ``client_key`` counts as ``unknown``, one key for every such
client.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from opensolve_pipe.middleware import client_key

TESTS = Path(__file__).resolve().parents[1]


Address = tuple[str, bool]
"""The address as written and whether it is whole (True) or a range's leading text (False)."""


def _written(node: ast.expr, scope: ast.AST) -> list[Address] | None:
    """The addresses `node` can hold, read from the source; None when it is not plain to read."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [(node.value, True)]
    if isinstance(node, ast.JoinedStr):
        head = ""
        for part in node.values:
            if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
                return [(head, False)]
            head += part.value
        return [(head, True)]
    if isinstance(node, ast.Name):
        bound: list[list[Address] | None] = []
        for inner in ast.walk(scope):
            if isinstance(inner, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == node.id for t in inner.targets
            ):
                bound.append(_written(inner.value, scope))
            elif (
                isinstance(inner, ast.For)
                and isinstance(inner.target, ast.Name)
                and inner.target.id == node.id
                and isinstance(inner.iter, ast.Tuple | ast.List)
            ):
                bound.extend(_written(e, scope) for e in inner.iter.elts)
        if bound and all(b is not None for b in bound):
            return [a for b in bound if b is not None for a in b]
    return None


def _clients(tree: ast.Module) -> Iterator[tuple[ast.Call, ast.AST]]:
    """Every ``TestClient`` call given a ``client``, with the function it is in (or the module)."""
    seen: set[int] = set()
    scopes: list[ast.AST] = [
        *(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)),
        tree,
    ]
    for scope in scopes:
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call) or id(node) in seen:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name == "TestClient" and any(k.arg == "client" for k in node.keywords):
                seen.add(id(node))
                yield node, scope


def addresses_by_module() -> tuple[dict[str, set[Address]], list[str]]:
    """Each module's addresses (by its path under ``tests``), and the calls not plain to read."""
    found: dict[str, set[Address]] = {}
    unread: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        module = str(path.relative_to(TESTS))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call, scope in _clients(tree):
            value = next(k.value for k in call.keywords if k.arg == "client")
            first = value.elts[0] if isinstance(value, ast.Tuple) and value.elts else None
            written = _written(first, scope) if first is not None else None
            if written is None:
                unread.append(f"{module}:{call.lineno}")
            else:
                found.setdefault(module, set()).update(written)
    return found, unread


def _key(address: Address) -> str:
    text, whole = address
    return client_key(text) if whole else text


def meet(a: Address, b: Address) -> bool:
    """Whether a request from `a` and one from `b` can be counted under one key."""
    ka, kb = _key(a), _key(b)
    if a[1] and b[1]:
        return ka == kb
    return ka.startswith(kb) or kb.startswith(ka)


@pytest.mark.parametrize(
    ("a", "b", "met"),
    [
        (("10.77.", False), ("10.77.", False), True),
        (("10.76.", False), ("10.77.", False), False),
        (("10.", False), ("10.77.", False), True),
        (("100.", False), ("10.77.", False), False),
        (("198.51.100.", False), ("198.51.100.241", True), True),
        (("198.51.100.240", True), ("198.51.100.241", True), False),
        (("198.51.100.24", True), ("198.51.100.241", True), False),
        (("::ffff:198.51.100.77", True), ("198.51.100.77", True), True),
        (("2001:db8:c1e:1::1", True), ("2001:db8:c1e:1:dead:beef:1234:5678", True), True),
        (("2001:db8:c1e:1::1", True), ("2001:db8:c1e:2::1", True), False),
    ],
)
def test_two_addresses_meet_where_one_key_can_count_both(a: Address, b: Address, met: bool) -> None:
    assert meet(a, b) is met
    assert meet(b, a) is met


def test_every_address_is_read() -> None:
    found, unread = addresses_by_module()
    assert unread == [], "write each client address as a string or an f-string at the call"
    # The modules this guard was written for are among those read.
    assert ("10.76.", False) in found["unit/test_pump_groups_one_off.py"]
    assert ("10.77.", False) in found["reference/test_project_library.py"]
    assert len(found) > 20


def test_no_two_modules_share_a_client_address() -> None:
    found, _ = addresses_by_module()
    shared = [
        f"{m}: {a[0]!r} and {n}: {b[0]!r}"
        for i, (m, mine) in enumerate(sorted(found.items()))
        for n, theirs in sorted(found.items())[i + 1 :]
        for a in sorted(mine)
        for b in sorted(theirs)
        if meet(a, b)
    ]
    assert shared == []
