# D6. Correctness: reference test suite

Decision D6 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D6`.

---

- `apps/api/tests/reference/` holds benchmark cases: Crane TP-410 and textbook worked examples, closed-form hand calculations, and EPANET runs for water-only networks.
- Pass criteria: flows, heads and pressures within 0.5% of the reference, or 0.01 m of head, whichever is looser. Mass balance must close at every node to the solver tolerance. A speed-controlled pump's speed (D11) must be within 0.5% (relative) of the reference, and the head it implies, s²H₀(Q/s), within 0.01 m of the reference head.
- Any change to solver or loss-coefficient code must keep the whole suite green. A new component type ships with at least one reference case.
