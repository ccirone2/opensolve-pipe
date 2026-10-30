# Dnn. <Feature> (owner, YYYY-MM-DD)

Decision Dnn of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md Dnn`.

Design proposal: `docs/proposals/<slug>.md` (link it). Specs: PRD §…, SDD §…, TSD §….

---

Built from `docs/proposals/<slug>.md` (who designed, reviewed and built it; where its as-built departures are recorded).

### Model

The types, fields, units, bounds and defaults; which values have no default and why; the `x-…` extensions published; `schemaVersion`.

### Law

The equations the solver uses, exactly, with the library functions and citations; what is computed once and what per iteration; what is unchanged (`gga.py`, `status.py`, …).

### Limits, flagged and refused

Each flag with the inequality that raises it; each refusal (422) with what it quotes and its remedy; what is deliberately not checked.

### Results and traceability

The result fields; what a closed-off or floating element reports; what the trace shows; the methods section and when it appears.

### Scenarios and goal seek

Allow-list fields added; goal-seek variables and goals; Compare rows; `not_applicable` cases.

### Design checks

Which of D19's checks apply, or why none does.

### Designers' web defaults (reversible, D14)

Menu entry, id prefix, forms, results view, Build strip, Compare rows, goal-seek default bounds, export sheet.

### Versions

`METHOD_VERSION` before and after, the changelog line, and what the corpus comparison proves unchanged.

### Proof

Reference cases (who wrote them, what they derive from, worst deviations); unit tests; corpus checks and their counts; fuzz profiles; e2e flows. TSD §10.4 holds the counts in one place.
