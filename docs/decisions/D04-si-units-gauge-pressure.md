# D4. Units: SI everywhere internally, gauge pressure at the edges

Decision D4 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D4`.

---

- Project data is stored in SI (m, m³/s, Pa, K, kg/m³, Pa·s). Unit preferences only affect input and display; changing them never changes stored values. This replaces "in project units" throughout SDD §4 and TSD §4.
- Users enter and see pressures as **gauge**. Each project has a `siteElevation` (m), from which atmospheric pressure is computed with the standard atmosphere and can be overridden. The solver uses absolute pressure wherever physics needs it (NPSH, vapor-pressure checks).
- Elevations are measured from a single project datum.
