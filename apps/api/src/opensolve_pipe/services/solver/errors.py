"""Solver exceptions.

Topology problems (and other references in the project that do not resolve) are collected
and raised together as one ``TopologyError`` so that the user sees every issue at once
(design §1.2). The API maps it to HTTP 422. Non-convergence is not an exception: it is a
``SolvedState`` with ``converged = False`` (SDD §8.2).
"""

from ...models.api import TopologyIssue


class TopologyError(Exception):
    """The project cannot be turned into a solvable network. ``issues`` lists every problem."""

    def __init__(self, issues: list[TopologyIssue]) -> None:
        self.issues = issues
        count = len(issues)
        summary = "; ".join(issue.message for issue in issues[:3])
        more = f" (and {count - 3} more)" if count > 3 else ""
        super().__init__(f"{count} topology issue(s): {summary}{more}")


def issue(
    code: str,
    message: str,
    component_ids: list[str] | None = None,
    connection_ids: list[str] | None = None,
) -> TopologyIssue:
    """Shorthand for a ``TopologyIssue``."""
    return TopologyIssue(
        code=code,
        message=message,
        component_ids=component_ids or [],
        connection_ids=connection_ids or [],
    )
