"""Differential test against EPANET 2.2 and corpus comparison of solver versions (TSD §10.4).

Command-line tools, not part of the reference suite:

- ``fuzz``: random networks (``generator``, profile 'default', or 'flow_control' with
  flow-controlled pumps) solved by our solver and by EPANET 2.2 (``epanet_model``), compared
  with the D6 criteria and checked independently (``checks``); ``stats`` summarizes a run.
- ``corpus``: every solved state of a fixed corpus of projects, system curves included, dumped
  to one JSON per project; ``compare`` compares two dumps exactly (``--ignore`` leaves out named
  paths).

pytest collects ``test_fuzz_smoke.py`` (pinned classes of seeds of both profiles) and
``test_harness.py`` (unit checks of these tools). Nothing here imports solver internals beyond
``solve_project`` and the models; the independent checks use ``tests/reference``.
"""
