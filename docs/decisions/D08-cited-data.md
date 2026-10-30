# D8. Cited data only (M2)

Decision D8 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D8`.

---

- Pipe dimensions come from `fluids.piping` (ASME B36.10M, B36.19M, ASTM D1785) and roughness from Farshad & Rieke (2006) via `fluids`, generated into `data/pipe_materials.json` by a script. Materials without both cited dimensions and roughness (HDPE, ductile iron) are not in v1; users can enter a custom pipe, or a pipe spec of the project library with its source (D22). The cited library grows only from sources that can be checked (owner, 2026-10-28). Never use `fluids`' fuzzy free-text roughness lookup. *(GOALS §4.1.)*
- Fitting K values come from one named `fluids.fittings` Crane function per fitting type (`data/fittings.json`); a user K overrides it and is labeled as user data.
