"""Whether a committed fixture of solver output is current: a fresh run must agree with it to
round-off, since the solver's last bits differ between CPUs (the export, goal-seek and scenario
fixtures' staleness tests)."""

from typing import Any

ROUND_OFF_REL = 1e-9
ROUND_OFF_ABS = 1e-9
"""How far a fresh run may be from the committed fixture, in SI units. The solver's last bits
differ between CPUs (from one commit, two CI runners gave 275862.7184869591 and
275862.7184869592 Pa(g) for a pressure in the export fixture, and 0.027675604544287736 and
0.027675604544287732 m³/s for a flow in the goal-seek fixture), so a fixture is current when every
number agrees with it to round-off and every other value exactly."""

CONVERGENCE_NOISE = frozenset(
    {"innerIterations", "outerIterations", "maxContinuityResidual", "maxEnergyResidual", "message"}
)
"""A solve's convergence diagnostics: iteration counts and the largest residuals below their
stop tolerances, which are not answers (CLAUDE.md D13) and differ between CPUs by more than
round-off; left out of the comparison (``converged`` itself is compared)."""


def round_off_differences(fresh: Any, kept: Any, path: str = "") -> list[str]:
    """Where ``fresh`` differs from ``kept`` by more than round-off (``ROUND_OFF_REL``,
    ``ROUND_OFF_ABS``), convergence diagnostics aside (``CONVERGENCE_NOISE``)."""
    if isinstance(fresh, dict) and isinstance(kept, dict):
        if set(fresh) != set(kept):
            return [f"{path}: keys {sorted(set(fresh) ^ set(kept))}"]
        out: list[str] = []
        for key in fresh:
            if path.endswith("convergence") and key in CONVERGENCE_NOISE:
                continue
            out += round_off_differences(fresh[key], kept[key], f"{path}.{key}" if path else key)
        return out
    if isinstance(fresh, list) and isinstance(kept, list):
        if len(fresh) != len(kept):
            return [f"{path}: {len(fresh)} items against {len(kept)}"]
        out = []
        for i, (a, b) in enumerate(zip(fresh, kept, strict=True)):
            out += round_off_differences(a, b, f"{path}[{i}]")
        return out
    numbers = (int, float)
    if (
        (isinstance(fresh, float) or isinstance(kept, float))
        and not isinstance(fresh, bool)
        and not isinstance(kept, bool)
    ):
        if isinstance(fresh, numbers) and isinstance(kept, numbers):
            bound = ROUND_OFF_REL * max(abs(fresh), abs(kept)) + ROUND_OFF_ABS
            if abs(fresh - kept) <= bound:
                return []
        return [f"{path}: {fresh!r} against {kept!r}"]
    return [] if fresh == kept else [f"{path}: {fresh!r} against {kept!r}"]
