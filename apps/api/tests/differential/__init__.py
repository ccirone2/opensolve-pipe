"""Differential test against EPANET 2.2 and corpus comparison of solver versions (TSD §10.4).

Command-line tools, not part of the reference suite:

- ``fuzz``: random networks (``generator``) solved by our solver and by EPANET 2.2
  (``epanet_model``), compared with the D6 criteria and checked independently (``checks``);
  ``stats`` summarizes a run.
- ``corpus``: every solved state of a fixed corpus of projects, system curves included, dumped
  to one JSON per project; ``compare`` compares two dumps exactly.

Only ``test_fuzz_smoke.py`` is collected by pytest. Nothing here imports solver internals beyond
``solve_project`` and the models; the independent checks use ``tests/reference``.
"""
