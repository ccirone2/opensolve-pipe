"""Per-request limits on solver work: a wall-clock deadline and cancellation (SDD §7.2).

The API runs each solve in a worker thread with a ``Budget`` set for it (``use_budget``); the
solver calls ``check_budget`` at every outer iteration and every Newton iteration, so a request
that runs out of time, or whose client has gone, stops within one Newton iteration instead of
running on for minutes. Outside a request (tests, scripts) no budget is set and the checks do
nothing. The budget lives in a context variable: each worker thread runs in its own copy of
the request's context.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class SolveInterruptedError(Exception):
    """The solve was stopped before it finished (base class)."""


class SolveDeadlineError(SolveInterruptedError):
    """The request's time budget ran out."""


class SolveCancelledError(SolveInterruptedError):
    """The client went away; nobody is waiting for the result."""


@dataclass
class Budget:
    deadline: float | None
    """time.monotonic() value after which the solve stops (None: no deadline)."""
    cancelled: threading.Event = field(default_factory=threading.Event)
    seconds: float | None = None
    """The budget in seconds, for messages."""

    def expired(self) -> bool:
        return self.deadline is not None and time.monotonic() > self.deadline

    def check(self) -> None:
        if self.cancelled.is_set():
            raise SolveCancelledError("the client disconnected")
        if self.expired():
            raise SolveDeadlineError(
                f"the request's time budget of {self.seconds:g} s ran out"
                if self.seconds is not None
                else "the request's time budget ran out"
            )


_current: ContextVar[Budget | None] = ContextVar("solve_budget", default=None)


def check_budget() -> None:
    """Raise SolveDeadlineError or SolveCancelledError if this request's budget is spent."""
    budget = _current.get()
    if budget is not None:
        budget.check()


def current_budget() -> Budget | None:
    return _current.get()


@contextmanager
def use_budget(budget: Budget | None) -> Iterator[None]:
    token = _current.set(budget)
    try:
        yield
    finally:
        _current.reset(token)
