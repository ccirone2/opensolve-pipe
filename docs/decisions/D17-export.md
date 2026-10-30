# D17. Export (owner, 2026-10-25)

Decision D17 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D17`.

Design proposal: [`export.md`](../proposals/export.md).

---

Built from `docs/proposals/export.md` (data and traceability, web and libraries designers, a synthesizer, two reviewers and a reviser; then a model builder, a UI builder, a screen fixer, an independent verifier and an integrator; its §12 records the as-built departures). Specs: PRD §3.2.3, SDD §3.1.3 and §5.1.4, TSD §8.3.

### Where

In the browser, from the solve responses, system curves and goal seek the page holds: no endpoint (SDD §5.1.4's is dropped, not deferred), no request (not even `/about`), nothing computed but Compare's differences; unavailable while a calculation request is in flight (`store.calculating`); system curves only as computed. Nothing changes in the API runtime, the model, the link format, `schemaVersion` or `METHOD_VERSION`. *(GOALS §4.5, §4.4.)*

### What

A workbook (`.xlsx`, the default) or CSV files (`.zip`) of the case shown or, with scenarios, all cases: About first (how to read the file; the project, export time and contents; the units and their exceptions; full precision; sign conventions; what is left out and why; per case its status, solve time, methods version and server libraries, convergence, atmosphere, fluid with its sources and out-of-date state; the project links, on by default; the web app's and the server's source; the disclaimer), Flags, Compare cases (all cases), the element tables one value per cell (pipes, fittings, branch ports and boundary ports as child tables), pump curves and the system curves computed, Scenario changes as the server applied them, the goal seek report, Methods and, for one case, the Trace. Every row starts with its case (with scenarios), `Solved at` and `Results`. One unit system per file: the display units, or SI base units, in which every number cell is the API's double. Full precision; names from the project the results belong to (current names for current results, the project as sent for out-of-date ones; the screen's Links table follows the same rule for its "From → To"), structure as solved, except Compare cases, which reads a case's connection values on the connection as it is now, as the screen does (D15); branch K always on the combined-flow velocity, as the API reports it (the screen fixed first: `branchVelocityBasis` has no `'own'` basis). The pump chart as a 1600 px PNG with a caption, drawn from the screen's own chart configuration; no SVG. *(GOALS §4.2.)*

### One rule for values

Compare's (`caseResponse`), then `hasValues` (the response converged) and `stale`, never the status alone: a solve that did not converge gives its About block, flags, scenario changes and methods, never values or an image, current or out of date; an out-of-date one is labelled in About, every caption and every row, and links the project as solved with its solve's methods version; a failed or not-reached case's earlier response is never used, in the file, the image or the chart's other cases. *(GOALS §3: correctness first.)*

### Formats

CSV: RFC 4180, UTF-8 with BOM, `.` decimals, a formula guard on text (never on numbers or JSON number literals), `README.txt` first in the zip with how to open the files under a comma-decimal setting. XLSX: our own SpreadsheetML subset (caption row 1, blank row 2, headers row 3, frozen, filtered, print titles), shared strings escaped for `_xHHHH_` and CR, no formulas or hyperlinks, deterministic from its input alone. Our own ZIP on the bundled pako's raw deflate (level 3). No new runtime dependency (`third-party-licenses.txt` unchanged at 11 packages; fflate 0.8.3 the documented fallback); no Web Worker (the notices plugin does not read worker bundles). A lazily loaded chunk (22.3 KB gzip) preloaded at idle: the initial `/p` download grew by 2.7 KB gzip, inside a 3 KB budget.

### Designers' web defaults (reversible, D14)

An Export button left of Goal seek (labelled from a 30 rem header, a container query; icon-only below), shown when there is something to export; a dialog with Cases (with scenarios; All cases on Compare cases), Format, Units and the link checkbox, the warnings, the contents with row counts, what is left out and the file name, from the function that makes the file; Download in the footer, always in view, and focused, so Enter, Enter gives the default workbook; progress and Cancel after 300 ms, and Close or Esc cancel. Download image under each pump chart. File names `{project} - {case} - {content} {YYYY-MM-DD HHmm}[ (not converged)].{ext}`. The choices are page state. *(GOALS §4.7.)*

### Proof

Writer tests against exact contents; model oracles over a shared fixture of real API responses (`tests/fixtures/export_input.py`): SI cells bit-identical to the API, display cells `fromSI` of the field, rows, order (the tables' own, not a sort or Flagged only on screen), fields and unit categories as the screen's with the departures named, K·v²/2g equal to each branch path's loss (the Darby fallback included); the states on a real store with a fake solver; a committed workbook written by the real writer and read in an API test (`test_web_export_fixture.py`, openpyxl in the dev group) by a verifier who did not read the export code, every number cell against a fresh solve; e2e downloads on desktop and phone with no request sent but the app's own chunk.
