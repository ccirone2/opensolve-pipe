# D14. Deployed is not stable (owner, 2026-10-25)

Decision D14 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D14`.

---

- The app is deployed (Cloudflare Pages and Google Cloud Run), but a deployment is not a stable release. Until the owner makes a specific decision to promise compatibility, nothing is "released" in D2's or SDD §5.2's sense: the model, the link format, the API and the methods may change without migrations or compatibility shims, and a link made before a change may fail to open (with the app's clear error) or solve differently.
- `schemaVersion` stays 1 until then. `METHOD_VERSION` and its changelog keep labelling each method for traceability (GOALS §4.3), without a compatibility promise. The schema-v1 fixture link and its tests (`test_released_links.py`, `examples.e2e.ts`) follow the model: when a change breaks them, they are regenerated, not kept as a frozen format.
- From the first stable release the owner declares, D2's and SDD §5.2's longevity rules apply. *(GOALS §3: longevity is promised once the owner releases; until then breadth and correctness move freely.)*
