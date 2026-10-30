# D2. Data model: port graph is canonical

Decision D2 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D2`.

---

- Components have typed ports, and `PipeConnection`s are edges between two ports (SDD §4.2). `Project` has `components[]` and `connections[]`.
- The "component chain" (`upstreamPiping`, `downstreamConnections`, the legacy `Connection` type) is **removed**.
- The panel navigator derives Prev/Next by walking the graph from a chosen start component. At a branch it asks the user which path to take, and the breadcrumb records the path taken.
- `Project` carries an integer `schemaVersion`. Shared URLs live forever, so the decoder upgrades old versions through ordered migrations. Never break decoding of a released version; none is released yet (D14).
