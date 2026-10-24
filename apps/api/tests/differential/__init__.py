"""Differential test against EPANET 2.2 and corpus comparison of solver versions (TSD §10.4).

Command-line tools, not part of the reference suite:

- ``fuzz``: random networks (``generator``, profile 'default', 'flow_control' with
  flow-controlled pumps, or 'assigned_flow' with assigned-flow nodes) solved by our solver and by
  EPANET 2.2 (``epanet_model``), compared with the D6 criteria and checked independently
  (``checks``); ``stats`` summarizes a run.
- ``corpus``: every solved state of a fixed corpus of projects, system curves included, dumped
  to one JSON per project (``--solver-options`` overrides every project's solver options);
  ``compare`` compares two dumps exactly (``--ignore`` leaves out named paths), or within the
  tolerances of a solver change that moves results by its convergence error
  (``--within-tolerance``, proposal vfd-slice2-discharge-pressure.md §2.7).

pytest collects ``test_fuzz_smoke.py`` (pinned classes of seeds of the three profiles),
``test_harness.py`` (unit checks of these tools) and ``test_compare_tolerance.py`` (unit checks
of ``compare --within-tolerance`` and ``corpus --solver-options``). Nothing here imports solver
internals beyond ``solve_project`` and the models; the independent checks use
``tests/reference``.
"""
