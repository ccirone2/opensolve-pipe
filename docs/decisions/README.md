# Decision record

One file per decision, `Dnn-<slug>.md`. Decisions override the specs (PRD, SDD, TSD) and are overridden only by [`GOALS.md`](../GOALS.md). Code, tests and the specs cite a decision as `CLAUDE.md Dn`; the index below and the one in [`CLAUDE.md`](../../CLAUDE.md) resolve the citation.

D1–D14 are the architecture and the rules of the rebuild. D15 onward each record one feature: its model, law, flags, results, scenario and goal-seek hooks, web defaults, method version and proof, so a reader working on that feature needs this file and the proposal's as-built section, not the whole spec.

| # | Decision | Status |
|---|---|---|
| [D1](D01-own-solver.md) | Solver: own Python network solver | built |
| [D2](D02-port-graph.md) | Data model: port graph is canonical | built |
| [D3](D03-url-sharing.md) | Sharing: URL fragment only in v1 | built |
| [D4](D04-si-units-gauge-pressure.md) | Units: SI everywhere internally, gauge pressure at the edges | built |
| [D5](D05-v1-scope.md) | v1 scope: core analysis MVP (in and deferred) | built |
| [D6](D06-reference-suite.md) | Correctness: reference test suite | built |
| [D7](D07-solver-formulation.md) | Solver formulation | built (stop test 1.2.0) |
| [D8](D08-cited-data.md) | Cited data only | built |
| [D9](D09-component-models.md) | Component models | built |
| [D10](D10-api-traceability-limits.md) | API, traceability and limits | built |
| [D11](D11-speed-controlled-pumps.md) | Speed-controlled pumps (VFD), slice 1: flow setpoint | built (1.1.0); slices 2–3 Later |
| [D12](D12-assigned-flow-node.md) | Assigned-flow node | built (1.1.0) |
| [D13](D13-same-answer.md) | Same answer, different answer | rule (owner, 2026-10-25) |
| [D14](D14-deployed-not-stable.md) | Deployed is not stable | rule (owner, 2026-10-25) |
| [D15](D15-scenario-manager.md) | Scenario manager | built |
| [D16](D16-goal-seek.md) | Goal seek | built |
| [D17](D17-export.md) | Export | built |
| [D18](D18-equipment-pressure-drop.md) | Equipment pressure drop | built (1.3.0) |
| [D19](D19-design-checks.md) | Design checks | built |
| [D20](D20-orifice-plate.md) | Orifice plate | built (1.4.0) |
| [D21](D21-pump-groups.md) | Pump groups, slices 4a and 4b | built |
| [D22](D22-project-library.md) | Project library | built (1.5.0) |
| [D23](D23-pressure-relief-valve.md) | Pressure relief valve | built (1.6.0) |

## Adding a decision

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to `Dnn-<slug>.md` with the next free number. The slug names the feature, so a renumbering at merge time is one `git mv` and two index rows (D20–D23 were each renumbered when branches merged in another order).
2. Fill the sections that apply; delete the others. Keep every statement checkable: name the file, function, flag code, tolerance or source.
3. Add the row here and in `CLAUDE.md`'s index (one line each), the TSD §12 "Decided" item, and the spec sections the decision changes (PRD §2.3 and §3, SDD §4, TSD §4–§5).
4. If any solved value can change, bump `METHOD_VERSION` and add the changelog entry; record the corpus comparison in the Proof section and in TSD §10.4.
5. Record the merge in [`history.md`](../history.md) and trim [`roadmap.md`](../roadmap.md).

The owner records product choices (what to build, what a user sees) and rules; the builders record how it was built. Owner's answers go in the proposal's questions section and are quoted in the decision as "(owner, date)".
