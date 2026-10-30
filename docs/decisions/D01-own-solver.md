# D1. Solver: own Python network solver

Decision D1 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D1`.

---

- Implement a Global Gradient Algorithm (Todini–Pilati, the method EPANET uses) in `apps/api`, with Darcy–Weisbach + Colebrook friction from the `fluids` library.
- One solver for every topology (single-path, branching, looped). The TSD's separate "simple solver" and WNTR wrapper (TSD §5) are dropped.
- The solver must handle what EPANET cannot: flow-split-dependent tee/wye K-factors, real fluid properties (density, viscosity, vapor pressure), check valves and other valves as components, liquid pressure relief valves (D23), and NPSH available. Later: VFD setpoint control, balanced-bellows and pilot relief valves, gas, steam and two-phase relief.
- Gravity-fed and pressure-fed systems with no pump are valid inputs.
- Every network, including closed loops, needs at least one fixed-pressure boundary (reservoir or ideal reference node). Report a topology error when one is missing. Assigned-flow nodes fix a flow, not a pressure, so they never count as that boundary.
- WNTR/EPANET is a **test-only** dependency, used as a reference for water-only cases.
