"""Every closed-form reference case: the M2 cases (``derivations``), the M3 component and
fluid cases (``derivations_pumps``, ``derivations_valves``, ``derivations_branches``,
``derivations_fluids``), the M4 status-logic cases from the differential test
(``derivations_status``), the flow-controlled pump cases of CLAUDE.md D11
(``derivations_pump_control``), the assigned-flow node cases (``derivations_assigned_flow``,
TSD §4.8), the round-off floor of the energy stop test (``derivations_round_off``,
METHOD_VERSION 1.2.0) and the equipment cases (``derivations_equipment``, proposal
equipment-pressure-drop.md §7.1). Each entry is a function named like its case file."""

from collections.abc import Callable

from tests.reference import (
    derivations,
    derivations_assigned_flow,
    derivations_branches,
    derivations_equipment,
    derivations_fluids,
    derivations_pump_control,
    derivations_pumps,
    derivations_round_off,
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
        + derivations_assigned_flow.CASES
        + derivations_round_off.CASES
        + derivations_equipment.CASES
    )
)
"""The M3 generators are wrapped so that their sources cite the line fittings they use."""
