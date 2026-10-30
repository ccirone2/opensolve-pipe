# D13. Same answer, different answer (owner, 2026-10-25)

Decision D13 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D13`.

Design proposal: [`vfd-slice2-discharge-pressure.md`](../proposals/vfd-slice2-discharge-pressure.md).

---

- **Two results are the same answer** when every flow, head and pressure agrees within D6's tolerance (0.5 % or 0.01 m of head, whichever is looser). Below that, differences are not regressions and need no owner decision: iteration counts and paths, convergence-level noise, and which state label (closed, open, isolated, no flow) an element carrying zero flow gets, or which of several such zero-flow states a solve reports.
- **What matters is a significantly different solution:** two valid states whose flows, heads or pressures differ beyond D6. Where the solver finds one it says so (not converged, naming the elements, as D11 does for over-control). Finding every such state is not a v1 goal.
- **Accepting a solver change:** the reference suite green (D6); in the corpus and the three fuzz profiles 0 critical seeds and no converged solve left not converged; every other value within D6 of the previous version or changed only at zero flow; anything beyond that named and explained in `METHOD_CHANGELOG`. No change-specific acceptance criteria are negotiated with the owner. *(GOALS §3: correctness is about answers, not labels.)*
- **Shelved by this rule (2026-10-25):** C1 (an exact Newton step for an active PRV's velocity-head term) and its redesign, kept in `docs/proposals/vfd-slice2-discharge-pressure.md` §2.2 and §2.11 as a record (the slow lag is TSD §12 open item 5); and slice 2 itself: that proposal's design and the owner's answers to its §13 questions are provisional notes, not decisions, to be revisited with a simpler design under this rule.
