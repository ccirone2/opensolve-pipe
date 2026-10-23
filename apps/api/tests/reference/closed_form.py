"""Every closed-form reference case: the M2 cases (``derivations``), the M3 component and
fluid cases (``derivations_pumps``, ``derivations_valves``, ``derivations_branches``,
``derivations_fluids``), the M4 status-logic cases from the differential test
(``derivations_status``) and the flow-controlled pump cases of CLAUDE.md D11
(``derivations_pump_control``). Each entry is a function named like its case file."""

from collections.abc import Callable

from tests.reference import (
    derivations,
    derivations_branches,
    derivations_fluids,
    derivations_pump_control,
    derivations_pumps,
    derivations_status,
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
        + derivations_status.CASES
        + derivations_pump_control.CASES
    )
)
"""The M3 generators are wrapped so that their sources cite the line fittings they use."""
