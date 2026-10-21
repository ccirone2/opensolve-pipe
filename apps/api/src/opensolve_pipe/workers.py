"""Solver work for API requests: a bounded worker pool, one solve at a time per client, a
per-request time budget and cancellation when the client goes away (SDD §7.2).

The solver is CPU-bound Python, so solves run in a small dedicated thread pool rather than the
event loop's default executor, and no client can fill it: a client's solves run one at a time
(a second one waits for the first, as when a user solves again before the last result came
back; a third is refused), and a solve is refused at once with 503 SERVER_BUSY when the pool
already holds MAX_SOLVES_IN_FLIGHT, instead of queueing behind work that may take minutes. Each
request gets a wall-clock budget from its arrival (``budget.py``), waiting included: the solver
checks it at every Newton and outer iteration, a solve that runs out raises SolveDeadlineError
(503 TIMEOUT; system-curve points not reached are reported as not computed instead), and a
request whose client disconnects is cancelled (SolveCancelledError). The reported compute time
is measured inside the worker thread, without the time spent waiting.

The capacities and the budget are operating limits, not physics: the budget stays below the
frontend's 60 s request timeout (apps/web/src/lib/api/client.ts), so an answer always arrives
while the client still waits for it.
"""

import asyncio
import contextvars
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from .services.solver.budget import Budget, SolveCancelledError, use_budget

SOLVE_WORKERS = 2
"""Threads that run solves (the solver holds the GIL most of the time; two let one solve's
NumPy/SciPy calls overlap another's Python)."""
MAX_SOLVES_IN_FLIGHT = 6
"""Solves running or waiting for a worker (at most one per client); more are refused."""
MAX_WAITING_PER_CLIENT = 1
"""Solves a client may have waiting behind its running one; more are refused."""
REQUEST_BUDGET_S = 45.0
"""Wall-clock seconds a solve request may take from its arrival."""
DISCONNECT_POLL_S = 0.25
"""How often a waiting request checks whether its client is still connected."""


class ServerBusyError(Exception):
    """The worker pool is full, or this client already has solves running and waiting."""


class DisconnectAware(Protocol):
    async def is_disconnected(self) -> bool: ...


_executor = ThreadPoolExecutor(max_workers=SOLVE_WORKERS, thread_name_prefix="solve")
_submitted = 0
"""Solves in the pool, running or waiting for a worker thread."""
_turns: dict[str, asyncio.Lock] = {}
"""Per client: held while one of its solves is in the pool."""
_waiting: dict[str, int] = {}
"""Per client: requests waiting for their turn."""


def in_flight() -> int:
    """Solves in the pool, running or waiting for a worker thread."""
    return _submitted


def _end_turn(client: str, turn: asyncio.Lock) -> None:
    turn.release()
    if not turn.locked() and client not in _waiting:
        _turns.pop(client, None)  # forget idle clients: bounded memory


async def _poll(
    request: DisconnectAware, budget: Budget, wait: "asyncio.Future[Any] | asyncio.Task[Any]"
) -> None:
    """Wait for ``wait``, checking every DISCONNECT_POLL_S whether the client is still there;
    if it has gone, cancel the solve (a running one stops at its next check)."""
    while True:
        done, _ = await asyncio.wait({wait}, timeout=DISCONNECT_POLL_S)
        if done:
            return
        if await request.is_disconnected():
            budget.cancelled.set()
            raise SolveCancelledError("the client disconnected")
        if budget.expired():
            return  # the solve itself reports it (budget.check)


async def run_solve[T](
    request: DisconnectAware, client: str, work: Callable[..., T], *args: Any, **kwargs: Any
) -> tuple[T, float]:
    """Run ``work(*args, **kwargs)`` in the solve pool under a fresh budget, after this
    client's previous solve has finished; (result, seconds spent in the worker). Raises
    ServerBusyError at once if there is no room, and whatever the work raises
    (SolveDeadlineError when its budget runs out); a client that disconnects cancels the work
    (SolveCancelledError)."""
    global _submitted
    budget = Budget(deadline=time.monotonic() + REQUEST_BUDGET_S, seconds=REQUEST_BUDGET_S)
    turn = _turns.setdefault(client, asyncio.Lock())
    if turn.locked() and _waiting.get(client, 0) >= MAX_WAITING_PER_CLIENT:
        raise ServerBusyError
    _waiting[client] = _waiting.get(client, 0) + 1
    acquire = asyncio.ensure_future(turn.acquire())
    try:
        await _poll(request, budget, acquire)
        if not acquire.done():  # the budget ran out while waiting for this client's turn
            acquire.cancel()
            budget.check()
    except BaseException:
        if not acquire.cancel():  # already acquired: give the turn back
            _end_turn(client, turn)
        raise
    finally:
        _waiting[client] -= 1
        if not _waiting[client]:
            del _waiting[client]
    if _submitted >= MAX_SOLVES_IN_FLIGHT:
        _end_turn(client, turn)
        raise ServerBusyError

    def timed() -> tuple[T, float]:
        with use_budget(budget):
            budget.check()  # it may have run out, or the client gone, while queued
            start = time.perf_counter()
            result = work(*args, **kwargs)
            return result, time.perf_counter() - start

    def finished(future: "asyncio.Future[tuple[T, float]]") -> None:
        # The client's turn and the pool slot are held until the work has actually stopped,
        # not just until the request stops waiting for it; the error of a cancelled request
        # is expected and dropped here.
        global _submitted
        _submitted -= 1
        _end_turn(client, turn)
        if not future.cancelled():
            future.exception()

    loop = asyncio.get_running_loop()
    context = contextvars.copy_context()
    _submitted += 1
    future = loop.run_in_executor(_executor, context.run, timed)
    future.add_done_callback(finished)
    try:
        await _poll(request, budget, future)
        if not future.done():
            # Past the deadline: the solve stops at its next check and reports it.
            await asyncio.shield(future)
        return future.result()
    except asyncio.CancelledError:
        budget.cancelled.set()
        raise
