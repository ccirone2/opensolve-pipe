"""Every closed-form reference case: the M2 cases (``derivations``) and the M3 component and
fluid cases (``derivations_pumps``, ``derivations_valves``, ``derivations_branches``,
``derivations_fluids``). Each entry is a function named like its case file."""

from collections.abc import Callable

from tests.reference import (
    derivations,
    derivations_branches,
    derivations_fluids,
    derivations_pumps,
    derivations_valves,
)
from tests.reference.case_format import ReferenceCase
from tests.reference.line import cite_line_fittings

CLOSED_FORM_CASES: tuple[Callable[[], ReferenceCase], ...] = derivations.CLOSED_FORM_CASES + tuple(
    cite_line_fittings(derive)
    for derive in (
        derivations_pumps.CASES
        + derivations_valves.CASES
        + derivations_branches.CASES
        + derivations_fluids.CASES
    )
)
"""The M3 generators are wrapped so that their sources cite the line fittings they use."""
