"""Classes of the differential fuzz (``fuzz.py`` sets them, in the record's ``status``).

Comparisons use the D6 criteria (``checks.compare``); "the checks" are the independent checks of
``checks.py``: mass at every component, energy on every connection, each pump and valve law in
its state, the status rules, and the feasibility of every section reported without heads.

- ``pass``: flows, head losses, EGLs and element states agree.
- ``documented``: they agree once EPANET is pinned where our documented departures apply (an
  FCV closes on reverse flow where EPANET's XFCV passes it; an FCV opens when the head across it
  is below its fully open loss; a PRV/PSV that EPANET reports XPRESSURE, no fixed head on one
  side, is held in our state).
- ``pass_ep_unbalanced``: EPANET does not balance (more than ``epanet_model.TRIALS`` trials)
  and its last iterate agrees with ours, states included.
- ``ours_verified_by_pinned_epanet``: EPANET does not balance, even with our documented FCV
  semantics, but EPANET with every pump at no flow and every valve open or closed pinned to our
  final state (running pumps and active control valves left to EPANET's rules) balances and its
  numbers agree with ours (a check of our element laws at our states).
- ``epanet_unbalanced``: as above, but the pinned EPANET run does not balance or disagrees:
  there is no balanced EPANET reference.
- ``state_only``: the numbers agree but an element state differs.
- ``state_only_zero_flow``: as ``state_only``, and every element whose state differs carries no
  more than EPANET's Qtol or its closed-link leak (a state at zero flow).
- ``a_ours_invalid``: the numbers differ and our result fails the checks (critical).
- ``d_no_converged_reference``: the numbers differ, ours passes the checks, and EPANET (with our
  FCV semantics) does not balance.
- ``b_stagnant_heads``: only EGLs differ, and both solutions pass the checks (EPANET's within
  its own tolerances): the free level of a zero-flow section, which EPANET's 1/CBIG conductance
  across closed links fixes.
- ``b_multiple_steady_states``: flows or head losses differ and both solutions pass the checks.
- ``e_epanet_invalid``: the numbers differ, ours passes the checks, EPANET's breaks mass,
  energy or an element law.
- ``review``: the numbers differ, ours passes the checks, EPANET's keeps the laws but breaks its
  status rules.
- ``unsupported``: an element has no exact EPANET equivalent (``epanet_model.UnsupportedError``).
- ``epanet_failed``: the first EPANET run returned an EPANET error (``epanet_model.EpanetError``,
  for example ``runH error 110``).
- ``ours_not_converged`` / ``both_unconverged``: our solver did not converge (EPANET balanced /
  did not balance); suffix ``_valid_state_exists`` when the brute-force search over pinned
  states (``state_search``, first 729 combinations) finds a fully determined state that passes
  the checks.
- ``no_steady_state``: the project alone shows that its assigned flows have no steady state
  (``checks.assigned_flow_expectations``: no pattern of flows carries them, or they force flow
  controls to their setpoints with nothing fixing the pressure, TSD §4.8), our solver did not
  converge, and its message states one of those reasons (names an assigned-flow node of the
  part concerned and, for flow controls held at their setpoints, the controls and that the
  pressure is undetermined). EPANET's run is recorded, not compared.
- ``no_steady_state_other_message``: as ``no_steady_state``, but the message states another
  reason (for example a head-dependent one where the network has several), to be reviewed.
- ``ours_exception``: our solver raised. ``gen_error``: the generator raised.
- ``harness_error``: anything else raised (for example EPANET failing in a re-run with pins, or
  the EPANET library failing to load). The record keeps what was computed before it raised.

Independently of the class, every converged result of ours is checked before EPANET runs; a
failure is stored in the record's ``self_check`` (kept in a ``harness_error`` record too) and
written to findings/self_check_failed. That self-check is the same check that makes a class
``a_ours_invalid``, so a record is critical (``is_critical``) when its ``self_check`` is
non-empty or its class is critical. With assigned-flow nodes (generator profile
'assigned_flow') it includes their results and that the network has a steady state at all
(a converged result where ``assigned_flow_expectations`` says there is none fails it), and a
project with a zero assigned flow must solve as with plugs in those nodes' places, bit for
bit, converged or not (``fuzz.plug_twin_problems``; a difference is a ``self_check`` failure
even when our solver did not converge). With flow-controlled pumps (generator profile
'flow_control') it includes their rules (proposal vfd-pump-modes.md §4.5), laws, speeds and
control fields (``checks.control_problems``); EPANET stands for the state we report for each,
so a state of ours that is wrong shows in the self-check, not as a state difference.

Also independent of the class: a converged network with flow-controlled pumps is searched over
their states (``state_search.control_search``); more than one distinct valid solution is
written to findings/control_multiple_states and counted by ``stats.py``.
"""

from collections.abc import Mapping
from typing import Any

CRITICAL = frozenset({"a_ours_invalid"})
"""Classes in which a converged result of ours fails the independent checks."""

AGREEING = (
    "pass",
    "documented",
    "pass_ep_unbalanced",
    "ours_verified_by_pinned_epanet",
    "state_only_zero_flow",
)
"""Classes whose comparison records enter the statistics (``stats.py``)."""


def is_critical(record: Mapping[str, Any]) -> bool:
    """A converged result of ours that fails the independent checks."""
    return record.get("status") in CRITICAL or bool(record.get("self_check"))
