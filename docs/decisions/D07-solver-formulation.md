# D7. Solver formulation (M2)

Decision D7 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D7`.

---

- The nodal unknown is the **energy grade line** (EGL = z + p/ρg + v²/2g), so pump head and fitting losses enter exactly; HGL and static pressure are derived with the velocity in the connected pipe. Reservoirs and reference nodes are quiescent boundaries (v = 0). EPANET neglects velocity heads, so EPANET comparisons compare our EGL with its heads. *(Correctness; GOALS §4.1.)*
- Transition zone 2000 ≤ Re < 4000: EPANET 2.2's Dunlop cubic (Hermite in Re/2000 between laminar and the turbulent formula in use), flagged `TRANSITIONAL_FLOW`. `swamee_jain` mode uses EPANET's exact 5.74/Re^0.9 form so EPANET tests compare network algorithms, not friction formulas.
- Branch legs are imposed exactly as head offsets on a merged head unknown, not iterated with a Jacobian floor (a floor stalled Newton on large mains feeding small tubing).
- Unknown pipe materials, schedules or sizes are topology issues, reported together with the other topology problems.
- **Stop test and flag (METHOD_VERSION 1.2.0, change set C0b):** a link's energy residual passes at 10⁻⁷ m + 4ε·max(\|H_start\|, \|H_end\|, \|h\|), ε = 2⁻⁵², since 10⁻⁷ m alone is below one unit in the last place of heads from 2²⁹ m and inner solves at large heads stalled at that round-off floor; the `NOT_CONVERGED` flag names a residual's location only where that residual exceeds its stop tolerance, and where the status updates keep returning to a failed state it reports the residuals of the solve its message describes (proposal `vfd-slice2-discharge-pressure.md` §2.11.10; TSD §5.2, §10.4). *(Correctness and traceability; GOALS §3, §4.2.)*
