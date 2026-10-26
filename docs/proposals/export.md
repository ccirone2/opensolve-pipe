# Export (CSV, XLSX, PNG): design proposal

**Status: built** (2026-10-26; CLAUDE.md D17; §12 records where the build departs from this design). This design was written on 2026-10-25 against `f1b44c2` (D14) by a design workflow. Three designers worked from different angles, each with measurements: one on the data and traceability, one on the web UX (layout and downloads in Chromium), and one on libraries, licensing and performance. A synthesizer merged their designs into this one. It checked the disputed claims against the code and by experiment (rows marked **S** in §4.4) and wrote this document. §1.3 lists where the designs disagreed and why this design chose as it did. Two reviewers (correctness and traceability; web, libraries and performance) then raised 21 issues. A reviser checked each one against the code and by experiment (rows marked **R** in §4.4) and revised the design where the issue was real. §11 lists every issue with its verdict and what changed.

The owner agreed to build export next in v1; D5 listed CSV/XLSX/PNG export as deferred. The workflow had already decided these points, which were not re-opened:
- **Specs.** PRD §3.2.3 ("CSV/Excel: all results in tabular format; Image: schematic/PFD as PNG or SVG") and SDD §5.1.4 ("`POST /api/v1/export` (CSV/XLSX) is Later"). There is no schematic in v1, so the images are the pump charts.
- **Privacy** as D3 and D10: the project leaves the browser only to be solved. There is no new server endpoint unless one is clearly better.
- **Licensing** as CLAUDE.md's License section: every new dependency is checked for AGPL-3.0-or-later compatibility, and the bundled notices stay complete.
- **Other sessions.** `docs/proposals/ui-ux-refinement.md` belongs to another session. Where export needs a control in a pane that proposal also changes (the Results header, Workspace), this design says so and keeps the footprint small.

Every other choice in this document is the designers' own. Each is a simple default chosen to serve working engineers, reversible under D14, and not escalated to the owner. §1.2 marks the origin of each, and §10 lists those the owner may want to revisit.

Sources:
- PRD §2.3, §3.2.3; SDD §3.1.3, §5.1.4; TSD §8, §10.3, §11.1, §12; GOALS §3, §4.2–§4.8; CLAUDE.md D3, D4, D5, D10, D14–D16, License.
- Code read at `f1b44c2`, with the other workflow's uncommitted edits in the tree: web `state/{project,workspace}.svelte.ts`; `components/results/{ResultsPanel,PumpChart,PumpsView,CompareView}.svelte`; `components/ui/{Dialog,Icon}.svelte`; `components/workspace/CaseStatusChip.svelte`; `components/links.ts`; `utils/{results,units,compare,trace,goal-seek,pump-chart,labels,encoding,scenarios}.ts`; `plugins/third-party-licenses.ts`; `playwright.config.ts`; API `pyproject.toml` and the generated `openapi.json`.
- The designers' prototypes, logs and screenshots are in the design workflow's scratchpad (`export-design/`, not committed):
  - Data: `measure.py` and `measure.json` (a corpus sample), `xlsx_size.py`, `dialect_check.py`.
  - Web: `chart-test.mjs`, `site/chart.html`, `dl-test.mjs`, `dl-unicode.mjs`, `app-layout*.mjs`, screenshots in `out/`.
  - Libraries: `libs/proj/{ooxml,sinks,csv,workload,bench,levels,async-bench,stream-rows,profile,sizes,edge}.mjs`, `libs/validate.py`, `libs/lo_check.py`, chunk listings in `libs/chunks-*.json`.
  - Synthesizer: `synth/caption_check.py`, `synth/yield.mjs`.
  - Reviewers: `review-correctness/{make_csv,make_xlsx,make_xlsx2}.py` with LibreOffice outputs, `review-build/module-report.json`.
  - Reviser: `reviser/{c1_branch,c1_oracle,c9_xlsx}.py`, the LibreOffice imports in `reviser/c2_*` and `reviser/c9/`.

---

## 1. Scope and decisions

### 1.1 Scope

This slice builds PRD §3.2.3 for v1:
- **Results workbook (`.xlsx`).** It holds:
  - every results table of the exported cases, one value per cell, at full precision;
  - the flags, the pump-curve points and the system curves already computed;
  - the scenario changes the server applied, the goal seek report, the methods text and, for one case, the trace;
  - an **About** sheet first: the traceability record of the file.
- **CSV files (`.zip`).** The same tables, each one strict RFC 4180 file, with `README.txt` (how to open the files without misreading them), `about.csv` and the text documents, in one zip.
- **Pump chart image (`.png`).** The chart shown, drawn again at a fixed size with a caption that names the pump, the case, the solve and its status.

Everything is made in the browser from results the page already holds. Nothing is sent, and no endpoint is added.

**Not in this slice (Later, §10):**
- SVG, and an image of the schematic (there is no schematic in v1: D5).
- Web Share ("Share file…"), copying a table to the clipboard, and a single-table CSV download.
- The values of a solve that did not converge, and the goal seek's own solved state at the values found.
- Goal-seek trial tables at full precision. The report's exact values found are included.
- Metadata in the PNG, and document properties beyond the title.
- A server-side export, a PDF report, and design-practice summaries.

### 1.2 Decisions

Origin key:
- **O**: decided before design.
- **D**: data and traceability designer.
- **W**: web UX designer.
- **L**: libraries, licensing and performance designer.
- **S**: synthesizer, either resolving a disagreement (§1.3) or adding what the designs missed.
- **R**: reviser, after a review issue (§11; the issue's id in brackets).

| # | Decision | Reason | Origin |
|---|---|---|---|
| 1 | Export runs entirely in the browser, from state the page already holds. SDD §5.1.4's `POST /api/v1/export` is dropped, not deferred. | Privacy (D3, D10, GOALS §4.5): an endpoint would send the project and its results a second time, only for formatting. No server CPU, worker or 503 path (GOALS §4.4). Export calculates nothing, so a pure function with exact oracles can test it. Measured cost: milliseconds for typical projects, about 0.4 s for the largest one-case workbook (§4.4). | O, D, W, L |
| 2 | No new runtime dependency. Own CSV writer; own minimal SpreadsheetML writer; own ZIP container on **pako**'s raw `Deflate`, which is already bundled for links; Chart.js, already bundled, for the PNG. The documented fallback is fflate 0.8.3 (MIT) behind the same sink interface. | It was the smallest, fastest and leanest option measured: 3,052 B gzip against 7.6–255 KB, and 0.37 s against 0.55–1.86 s for one case at SDD §7.1's limits. It adds no supply chain, and `third-party-licenses.txt` stays at 11 packages. exceljs's browser bundle would hide about 170 packages' notices from the notices plugin. | L |
| 3 | The export code is a **lazily loaded chunk**: `ExportDialog.svelte` with the model, tables, About and the writers, imported (`import()`) when the Export button first renders, at idle, and awaited on the click. It imports the shared modules (`results.ts`, `labels.ts`, `units.ts`, `compare.ts`, `trace.ts`) directly. A failed import is caught and explained (§5.2). `chart-image.ts` goes into the `chart-setup` chunk, which is loaded whenever a chart is drawn. Budget: the initial `/p` download grows by at most 3 KB gzip, read from the build's chunk report and stated in the PR. | Export is occasional, and every `/p` visit, on phones too, would otherwise load it. The 10 KB bundled budget rested on the writer alone (3.1 KB); the dialog, 20 tables, About and the image are estimated at 12–15 KB gzip in the chunk (review-build's module report). L measured that a lazy chunk importing statically loaded modules costs 1.5 KB at start-up, which the budget accepts instead of feeding formatters in. Preloading when results first exist narrows the stale-chunk window (a tab opened before a redeploy) to the time before the first solve; `import('./chart-setup')` has that exposure today. | W, L, R over S (W-WLP-3) |
| 4 | **Two formats** from one dialog: Excel workbook (default) or CSV files in one `.zip`. One click gives one file. | XLSX is what engineers open. CSV serves scripts, which want every table, with the About record, in one file. Several downloads from one click make Chrome ask for permission and fail on phones (W). A bare single-table CSV would carry no record of its case, solve or status. | D (zip), W (one file), S |
| 5 | **One unit system per file**, chosen in the dialog: the project's display units (default) or SI base units (m, m³/s, m/s, Pa, K, kg/m³, Pa·s, W, fractions 0–1 with no unit, as the API writes ''). The two are never side by side. Headers read `Label [unit]`, with `(g)`/`(a)` or `psig`/`psia` on pressures; differences are unmarked. Exceptions, each named in About's Units row: the trace, the methods text, the API's flag messages and details, and JSON values are always SI, as reported; the app's sentences (the flag Message column and the goal seek report) are written in the file's units, but give speeds and efficiencies in % and powers in kW (hp with gpm), as the app always writes them. | Display units are what the user reads on screen (D4: units affect only display). SI is what scripts and the API use, and in SI mode every number cell is bit-identical to its API field, which is the test oracle. Doubled columns would double the width and invite mixing. Trace equations are written for SI values. The sentences are the app's tested words (`flagText`, `goalSeekReport`); an export-only unit override would fork them for a text column (R, C-C11). | D, R (C-C11, W-WLP-2) |
| 6 | **Full precision.** A number is the API's double converted by `fromSI`, never rounded and never snapped to "≈ 0". CSV and `<v>` hold `String(n)`, the shortest round-trip form. About says that spreadsheets display and re-save 15 significant digits. | Rounding is a display choice. The file holds the exact double, and openpyxl and pandas read it back exactly (measured, with `float_precision='round_trip'` for CSV). Excel's 15 digits are 10¹² below D6's tolerance. | D, L |
| 7 | **One value per cell.** Screen cells that hold several values (per pipe, per port, "Flow 12 L/s: held", a setpoint whose unit depends on the valve type) become atomic columns or child tables keyed by the parent id: Pipes, Fittings, Branch ports, Boundary ports. A null is an empty cell, never "—" or 0. Booleans are boolean cells (`TRUE`/`FALSE` in CSV). | Filters, pivots and scripts need atomic, typed cells. | D |
| 8 | Every row carries the API **id** and the **name**. For a case whose results are current, names come from the current project (then the id); for an out-of-date case, from the project as sent for its solve (then the id), in its rows, connection ends and Scenario changes. **Structure comes from the project as solved**: connection endpoints (and so the flow sign), ports, kinds, pipe specs, fitting positions and valve types. | Ids match flags, traces and the link. A current case's fingerprint (components without names) guarantees the same ids and kinds, so its current names are safe and are what people read (the screen's rule). An out-of-date case's ids may have been re-used since: `newId` gives a deleted element's id to the next new one, so a current name could label another element. Taken from the project as sent, names, structure and the as-solved link agree. Structure as solved keeps "From → To" consistent with the flow sign after a reversal made since the solve, as ScenarioCard already does. | D, R (C-C4) |
| 9 | **Cases.** The dialog offers a choice only when the project has scenarios: the case shown (default) or All cases (the default when the Compare cases tab is shown). Values follow Compare's rule (D15), through one predicate, `hasValues` (§2.1), whatever the case's status: a converged response gets its values, labelled when out of date; a response that did not converge, current or out of date, gets only its About block, flags and methods; a failed, not reached or not solved case is listed in About. | An All cases workbook gives the long-format tables that pivots need. Correctness comes first: the values of a solve that did not converge are not a solution, and a table pasted out of a workbook loses any warning, which is why Compare shows none. `store.caseStatus` says `stale` for any out-of-date response, converged or not, so it cannot decide this (R). | D (S kept it over W's case shown only, §1.3), R (C-C5) |
| 10 | The **Trace** sheet is in single-case exports only. | The largest corpus trace has 24,232 rows, 6.5 MB of sheet XML; 21 such cases would be about 137 MB built in a phone's memory. About says that the trace is left out. | D |
| 11 | The **Compare cases** sheet is in All cases exports of two or more cases. It holds the rows chosen on the Compare tab, wide by case, with exact differences from the base. | A single-case file then holds one case only. | D (S over W, §1.3) |
| 12 | **Goal seek.** When a finished goal seek ran on an exported case, the file holds its report: the text Copy report gives, with the exact values found. It goes on a "Goal seek" sheet or in `goal-seek.txt`. The goal seek's own solved state is not a case. | One source of words, which is already tested. Apply the values as a scenario and solve to export full tables at them. | D (S reduced D's four sheets to one) |
| 13 | **About** comes first. It holds the export block, one block per case, the project links, the goal seek block, the software and source links, and the disclaimer verbatim (§2.7). | Traceability (GOALS §4.2): a file must say what produced each number, when, under which methods version and in which state. | D, W |
| 14 | The **project link** is included by default; a checkbox leaves it out. A case whose results are current gets the current project's link, and an out-of-date case gets the link of the project exactly as solved, with the methods version of that solve recorded in it (§2.7). Each distinct link is written once, with the cases it reproduces. Links are plain text, never a hyperlink and never in document properties or image metadata. Beyond 32,767 characters the XLSX says "not included" and points to Share; `about.csv` always holds the link. | A link lets anyone reopen the exact inputs and solve again, the strongest record a file can carry, and the file stays in the user's hands. The staleness key guarantees that a current case's current link reproduces its results; an out-of-date case needs its own. Excel cell hyperlinks fail beyond about 2,000 characters, below the measured median link (2,299). | D (S over W's always-as-solved, §1.3) |
| 15 | **XLSX sheet layout.** Row 1 holds a caption (sheet, project, case, solve time, methods version, status), row 2 is blank, and row 3 holds the bold headers with the autofilter. Panes are frozen below row 3, and rows 1–3 repeat on every printed page. | The case and an out-of-date or SI note stay visible on every sheet, on screen and on paper (D). The blank row keeps Excel's and LibreOffice's contiguous-range detection (Ctrl+T, PivotTable, Ctrl+A) from taking the caption for a header (S). pandas reads every sheet with `header=2`, exactly (S, measured). | D (caption), L (header in row 1), S (blank row) |
| 16 | **XLSX subset**, all written by our own code: shared strings (escaped for XML and for SpreadsheetML's `_xHHHH_` form, CR kept as `&#13;`); booleans `t="b"`; the General number format; minimal styles; column widths; a frozen pane and `sheetFormatPr` written exactly as §3.2 gives them; autofilter with the defined names Excel writes; `docProps/core.xml` (title, creator "OpenSolve Pipe", created). No formulas, hyperlinks, number formats, themes, charts or ZIP64. Deflate level 3. Deterministic bytes for given input and time. | It covers what engineers use, copied from what Excel writes, and openpyxl and LibreOffice read it exactly (measured). Level 3 is 35 % faster than level 6 for files 7 % larger. Determinism allows a checked-in fixture. | L |
| 17 | **CSV dialect.** RFC 4180: comma, CRLF, a quote only when needed, UTF-8 with a BOM, `.` decimals whatever the browser's locale. A **text** cell that begins with `= + - @`, TAB or CR gets a leading `'`; numbers and JSON cells (which begin with `-` only for a number literal) are never touched. The warning for comma-decimal spreadsheets is **in the files**: `README.txt`, the zip's first entry, and the first rows of `about.csv` say how to open them (§3.1); the dialog's hint says it too. | Measured in pandas, Python's `csv` (with `utf-8-sig`) and LibreOffice 24.2 (en-US, de-DE, fr-FR); Excel by hand (§7.4). In en-US every value reads right. In de-DE LibreOffice reads 101.325 as the number 101325 and 1.5 as text, silently (R measured); Excel opens a double-clicked CSV with the system list separator (`;` there) in one column. A locale-dependent CSV would make the file depend on who exported it, so the dialect stays and the people who receive the zip get the warning with it. Names come from shared links, so they are third-party input (OWASP CSV injection guidance). | D, L, W, R (C-C2, C-C7) |
| 18 | **Building.** On the main thread, cooperatively: a yield through a `MessageChannel` every 500 rows or 64 KiB of XML, an `AbortSignal` checked at each yield, rows as iterables built on the fly, and progress with Cancel after 300 ms. No Web Worker. | Measured: the longest synchronous slice is 24–31 ms. `setTimeout(0)` costs 4 ms per yield once nested, which would add 3.4 s at 850 slices (S). Peak memory is 201 MB, against 438 MB with rows built in advance. Vite does not run the notices plugin on worker bundles (L verified), so a worker would open a notice gap. | L (S over W's `setTimeout` and 2,000-row chunks) |
| 19 | Export is **unavailable while a calculation request is in flight** (`store.calculating`), with the reason. It sends no request and never computes a system curve; About lists the pumps whose curves were not computed. | A file is never made from results that are about to be replaced, and the rule is the one every Solve control already follows (D16). System curves cost about 41 solves each. | D (S over W, §1.3) |
| 20 | **Entry points.** One **Export** button in the Results header, left of Goal seek, labelled from a 30 rem header width (a container query) and icon-only (44 px) below. The heading gets `min-w-min`. The button is rendered only when there is something to export. **Download image** goes under each pump chart. Workspace and WorkspaceHeader are untouched. | Export belongs with the results it exports. Measured: a labelled button collapses the heading at 390 px and in the 409 px pane at 1024 px. The heading fix also ends an overlap that happens today. The chart's own action exports exactly what is drawn. | W |
| 21 | **The dialog** offers Cases (with scenarios), Format, Units and Include the project link. It shows the contents with row counts and what is left out, the file name and **Download** (which has the focus when the dialog opens). The choices are page state for the session. | Few choices with safe defaults: Enter, Enter gives the default workbook. Nothing is stored. | D, W, S |
| 22 | **PNG.** The chart is drawn off screen from the same Chart.js configuration as the screen (`pumpChartConfig`, moved into `utils/pump-chart.ts`), 800 CSS px wide at 2× (1600 px), on an opaque white background. A composite canvas adds a header (title, case, project, solve time, methods version, warnings) and a footer (the figure's notes, the disclaimer, the app). It is encoded with `toBlob`. No image for a solve that did not converge, or while the case shown failed (its earlier results are not exported, §2.4); an out-of-date image says so. Other cases' markers follow the file's rule: a case that failed, was not reached or did not converge is not drawn, on the screen's chart either (one helper, §2.1). | Measured: the on-screen canvas is transparent and its size depends on the device, while the fixed render gave byte-identical PNGs on desktop and phone in 31–37 ms. One configuration means the image cannot drift from the screen. A caption keeps the image self-explaining (GOALS §4.2). | W (render, measured), L (`toBlob`), D (caption, not converged) |
| 23 | **No SVG.** | Chart.js draws only to canvas, and a second renderer would make a second picture of one result. PRD's SVG was for the schematic (Later). The curve points in the workbook serve vector needs, and a 1600 px PNG prints at 246 dpi at report width. | W, L |
| 24 | **File names.** `{project} - {case} - {content} {YYYY-MM-DD HHmm}[ (not converged)].{ext}`, with the export's local time. The case is left out without scenarios. Sanitized as in §3.5. No "(out of date)". | The file says when it was made, and its contents name each solve. "Not converged" is a property of the values. "Out of date" is relative to the exporter's session, and the file is self-consistent: it links the project as solved. | W (rules), D (export time), S |
| 25 | **Download** through a Blob URL and an `<a download>` click, revoked after 60 s. No Web Share in v1. | It works on every target browser (measured in Chromium; documented for iOS 13+ and Android). Web Share cannot be tested in CI (it is undefined in Linux Chromium). It would also force the workbook to be built synchronously inside the click to keep the user's gesture, against decision 18. | W, L (S dropped W's Share, §1.3) |
| 26 | **Independent reader.** openpyxl 3.1.5 (MIT, dev group only) reads a committed fixture workbook built by the real writer, cell by cell, in an API-side test, with Python's `zipfile`. | openpyxl is an independent implementation of SpreadsheetML. Its full load rejected a malformed styles part that other readers accepted (L, excel-builder-vanilla). A standard-library parser would only confirm our own reading of the format. The API runtime is unchanged. | S (over L's standard library only) |
| 27 | Nothing changes in the API runtime, the model, the link format, `schemaVersion` or `METHOD_VERSION`. The export does not fetch `/api/v1/about`. It names the methods version and libraries of each solve and the server's `/source` link, worded as "the commit it runs now". | Export adds no calculation. A solve response does not carry the server commit (§10). | D, S |
| 28 | **Every table row names its solve.** Each table, in both formats, starts with `Case id` and `Case` (with scenarios), then `Solved at` (`SolvedState.timestamp`, verbatim) and `Results` (Current, Out of date, Did not converge, or Did not converge, out of date). Compare cases, which is wide by case, gets a Solved at row under its Status row. | Every file of the zip is a bare table once extracted, and a table copied out of a sheet loses its caption. With these columns a row read alone still says which solve produced it and whether it may be used: decision 4's reason, applied per row. Constant columns cost a little width in a one-case file; traceability ranks above usability (GOALS §3). | R (C-C3) |
| 29 | **Branch K is always on the combined-flow velocity**, as the API reports it (`BranchResult.kFactors`: "K v_ref²/(2g) is the path's loss"), the Darby 3-K fallback included. The export writes `referenceVelocity` beside every K, and the screen's `branchVelocityBasis` loses its `'own'` basis in the same build. | Measured on `tee_crane_bullhead_fallback`: K·v_ref²/2g gives the path loss exactly (0.71917 m), while the leg's own velocity gives 0.52010 m, 28 % low (0.58061 m against 0.75983 m, 24 % low, on the other leg). The screen pairs the API's K with the wrong velocity today; the export must not copy that rule, and its oracle (§7.1) would fail on it. | R (C-C1) |

### 1.3 Where the designs disagreed

1. **Lazy chunk or bundled.** L put all the export code in one lazily imported chunk (3.1 KB gzip, page +375 B) with a caught import error. W bundled it with the Results pane to avoid stale chunks. The synthesizer bundled it with a 10 KB budget, to avoid feeding formatters into a lazy chunk. The review (W-WLP-3) showed that the budget rested on the writer alone and that the whole export is estimated at 12–15 KB gzip. The revised design loads it lazily (decision 3) and lets the chunk import the shared modules, accepting L's measured 1.5 KB at start-up rather than passing formatters in; a preload when results first exist and a caught import cover the stale-chunk case.
2. **What CSV gives.** D: one zip of every table with `about.csv`. W: one table as one CSV (a select), no zip. L: one CSV per table, no zip. This design gives the zip (decision 4). Traceability ranks above usability (GOALS §3), and a bare table carries no case, solve or status. One click still gives one file, and scripts get every table together. A single-table CSV is reversible (§10).
3. **Cases in one file.** W: the case shown, plus a Compare sheet whenever the project has scenarios; other cases are exported while shown. D: the case shown or All cases, stacked with Case columns, and Compare only with All cases. This design takes D's (decisions 9 and 11). Long-format tables across cases are what pivots and scripts need, and the measured 21-case workbook at SDD's limits (6.8 s, 39 MB on desktop) is acceptable with progress and Cancel. A Compare sheet in a single-case file would put other cases' values in it.
4. **A solve that did not converge.** W exported its values, with "(not converged)" in the name. D exported its record only. This design takes D's (decision 9) for correctness, as Compare does. The screen keeps the values for diagnosis, and the file keeps the convergence report and flags. The image follows the same rule (decision 22). The "(not converged)" suffix is kept, because such a file still exists.
5. **Export during a calculation.** W allowed it ("exports what is shown at the click"); D blocked it. This design blocks it (decision 19). During Solve all, a case that is "waiting" or "solving" has no status the export rules could use, and results about to be replaced are rarely what a user wants to file. The dialog is modal, so nothing starts while a file is built.
6. **Caption row.** D: a caption in row 1 and headers in row 2. L: headers in row 1. This design keeps D's caption and adds a blank row 2 (decision 15). The synthesizer checked the layout in pandas 3.0.5, openpyxl 3.1.5 and LibreOffice (§4.4 S1).
7. **Units.** W: display units only. D: display or SI. This design offers both (decision 5). SI mode costs one radio group, and it is the exact oracle the tests use.
8. **The link.** W: always the project as solved. D: the current project for current cases, the project as solved for out-of-date ones, deduplicated, with a checkbox. This design takes D's (decision 14). A current case's link then carries the current names, and the staleness key (`caseKey`: the hydraulic fingerprint plus the scenario's changes) guarantees it reproduces the results.
9. **PNG caption.** W drew a header and footer on a composite canvas, wrapped with `measureText`, measured in Chromium. L used Chart.js's `Title`/`SubTitle` plugins (+490 B), unmeasured in a browser. This design takes W's (decision 22): the footer has several long sentences and coloured warnings, which the plugins neither wrap nor colour per line. It takes L's `toBlob`, since without Web Share nothing needs a synchronous data URL.
10. **Web Share.** Only W proposed it. This design leaves it out (decision 25, §10).
11. **Yielding.** W: `setTimeout(0)` between 2,000-row chunks. L: a `MessageChannel` every 500 rows. This design takes L's (decision 18). L measured the 2,000-row slices at 70 ms, a long task, and the synthesizer measured `setTimeout`'s clamp at 4.0 ms per yield (§4.4 S3).
12. **File names.** W: the solve's time, `_` for invalid characters, at most 150 characters. D: the export's time, `_`, at most 120, and an "(out of date)" suffix. L: `-`, at most 100. This design takes W's sanitizing rules (`_` is what Chromium does itself), D's export time (one time even for All cases), and W's "(not converged)" without "(out of date)" (decision 24).
13. **The label breakpoint.** L: the label hidden below a 24 rem viewport, as Goal seek's. W: a 30 rem container query on the header. This design takes W's (decision 20): W measured that the pane, not the viewport, is narrow at 1024–1279 px.
14. **The independent XLSX reader.** L: Python's standard library (`zipfile`, ElementTree). This design adds openpyxl in the API's dev group (decision 26), the stronger check, as the workflow suggested.

---

## 2. What is exported

### 2.1 The input: a snapshot taken at the click

`exportInput(ws, options, now)` (`utils/export/input.ts`, in the lazy chunk; it reads only the workspace's public getters) gathers everything the export reads, at the moment Download is pressed. `utils/export/model.ts` then builds the file from it with no other access to the page: it imports no module constant that depends on the build or the environment (`SOURCE_URL`, `apiBaseUrl`), and reads no clock or time zone.
- **Options:** `cases: 'shown' | 'all'`, `units: 'display' | 'si'`, `link: boolean`.
- **The page:**
  - `now` (a `Date`) and `utcOffsetMinutes` (`−now.getTimezoneOffset()`): every local time in the file (About, the file name, the ZIP entries' DOS time, the goal seek's run time) is computed from these two by arithmetic;
  - `appVersion` (`version` from `$app/environment`: the build commit), from which About writes `sourceLinks(appVersion)`, never `SOURCE_URL`;
  - `serverSource` (`serverSourceHref()`), `origin` (`location.origin`, for links);
  - the current project (`ws.store.project`, frozen), the display units, and the library's material and fitting names (`ws.library`, with the existing fallbacks).
- **Each exported case, in case order** (the base, then the scenarios):
  - its id, its name (`ws.caseName`) and its status (`store.caseStatus`: for Compare's rule below and for the words, never for convergence);
  - its response, by Compare's rule (`caseResponse(status, results)`, new in `utils/compare.ts`, which CompareView and PumpsView use too): null when the status is `failed` or `not_reached`, else `resultsFor(caseId).response`;
  - `hasValues = !!response && response.success && response.solvedState.converged`, and `stale = !!response && results.stale`. These two, never the status, decide values, curves, the trace, the image, the dialog's warnings, the file-name suffix, captions and the `Results` column: `store.caseStatus` returns `stale` for an out-of-date response whether or not it converged;
  - the project as sent (`sentProjectFor(caseId)`) and the case as solved (`caseInputs(caseId)`);
  - its computed system curves (`store.systemCurvesFor(caseId)`, new: the case's slot, read only).
- **Compare:** the rows chosen on the Compare tab (`ws.compareRows ?? defaultRows(...)`, exactly as CompareView computes them).
- **Goal seek:** the finished goal seek (`finishedGoalSeek(store.goalSeek)`) when its status is `done` and its run case is exported.
- **The link:** `loadedMethodVersion`, the methods version the link recorded.

The store replaces these objects and never mutates them, so the snapshot holds references. The dialog is modal and Export is unavailable while `store.calculating` is set, so no solve can start or end while a file is built.

### 2.2 The data contract (every table)

1. **One value per cell.** Numbers are number cells. No number is embedded in text, except in documents (About's sentences, Methods, Goal seek), in the flag Message columns, and in Scenario changes' text values (a pipe spec, a resistance), whose exact values are in the JSON columns.
2. **Full precision.** A number is `fromSI(apiValue, unit)`, with no rounding. Compare's differences are the only computed values: `fromSI(value − base, unit)` and `(value − base) / |base| × 100`, exactly as the screen computes them (§2.6).
3. **Empty means none.** A null is an empty cell.
4. **Booleans** are boolean cells (`TRUE`/`FALSE` in CSV; pandas reads them as booleans, and LibreOffice does with "Detect special numbers" on, otherwise as text: R measured).
5. **Ids and names** as decision 8. Names: for a current case, the current project's element, else the id; for an out-of-date case, the element in the project as sent for its solve, else the id. Compare cases, whose rows span cases, uses the current project's names, as the Compare tab does.
6. **Words are the app's.** States, types, regimes, patterns and statuses use the labels the screen shows (`pumpStatusLabel`, `valveStateLabel`, `valveTypeLabel`, `REGIME_LABELS`, `branchPatternLabel`, `kindLabel`, `portLabel`, `PUMP_CONTROL_STATE_LABELS`, `CASE_STATUS_LABELS`). Flag codes are the API's. D14: none of these words is a stable machine vocabulary yet.
7. **Screen order.** Rows follow the screen tables: components in project order, then their ports in port order; connections in project order; then ids no longer in the project. `orderedIds` in `results.ts` is exported for this, and a test asserts the same keys and order as `nodeTable`, `linkTable`, `segmentTable`, `fittingTable`, `pumpTable`, `valveTable`, `branchTable`, `boundaryTable` and `assignedFlowTable`.
8. **Units** are in headers: `Label [unit]`. Where the unit varies by row (Compare, Scenario changes, Trace), a `Unit` column holds it.
9. **Case and solve columns** (decision 28). In a project with scenarios, every table starts with `Case id` (empty for the base) and `Case` ("Base case" or the scenario's name), in single-case exports too, so the columns of a project's files never depend on the option. Without scenarios they are absent, as the app names a case only when scenarios exist. Then every table, with or without scenarios, has `Solved at` (`SolvedState.timestamp`, the API's UTC string, verbatim) and `Results` ("Current", "Out of date", "Did not converge" or "Did not converge, out of date", from `hasValues` and `stale`). A row read alone, out of its sheet or its zip, still names its solve and its state. Rows are in case order, then element order. The tables below list only the columns after these.

### 2.3 Units

`utils/export/units.ts` resolves the export unit of a category:
- **Display mode:** `displayUnit(category, prefs)`. Power is shown in hp when flow is in gpm, else kW. Fractions are % (value × 100).
- **SI mode:** `SI_BASE_UNITS` (new: length, diameter and head in m, pressure Pa, flow m³/s, velocity m/s, temperature K, density kg/m³, viscosity Pa·s), with power in W and fractions as the dimensionless 0–1 with no unit bracket, as Re, f and K have (the API's `''` for none; a `-` would also trip the CSV formula guard).

Every number cell in SI mode is the API's own double. The app's sentences, flag messages (`flagText`) and the goal seek report (`goalSeekReport`), are written with the file's units as preferences (`SI_BASE_UNITS` in SI mode), so a single code path serves both modes. `displayUnit` fixes two categories whatever the preferences: in these sentences speeds and efficiencies are in % and powers in kW (hp when flow is in gpm). About's Units row says so (decision 5).

Header labels use `unitLabel`:

| Category | Display (SI preset / US preset) | SI mode |
|---|---|---|
| Gauge pressure | `kPa(g)` / `psig` | `Pa(g)` |
| Absolute pressure | `kPa(a)` / `psia` | `Pa(a)` |
| Pressure difference (drop, dynamic pressure) | `kPa` / `psi` | `Pa` |
| Fraction | `%` | no bracket (0–1) |
| Re, f, K, Cv, quantity | no bracket | no bracket |

Kinematic viscosity has no display unit, so it is always m²/s. About states the atmospheric pressure each solve used, so gauge and absolute values can be related. Heads and elevations are measured from the project datum.

The categories are exactly the screen's for the same column (elevation is `length`; HGL, EGL, head and losses are `head`; diameters and roughness are `diameter`), so the screen agreement test (§7.1) holds. Where the unit varies by row (Compare, Scenario changes), a dimensionless value's `Unit` cell is empty in both modes.

### 2.4 Cases and their state

What the file holds for a case is decided by its response (Compare's rule), `hasValues` and `stale` (§2.1), never by its status alone:

| Case | What the file holds |
|---|---|
| `hasValues`, current | Everything. `Results`: Current. |
| `hasValues`, out of date | Everything, labelled out of date in About, in the `Results` column of every row, in every sheet's caption and in Compare's Status row. Its names and its link are the project as solved. |
| A response without values (did not converge), current or out of date | Its About block (status and convergence report), its flags (`Results`: Did not converge, or Did not converge, out of date), its scenario changes and its methods text, which already says "DID NOT CONVERGE … must not be used". No element values, curves or trace. |
| No response by Compare's rule: `failed` (an earlier response kept on screen is not used), `not_reached`, `not_solved`, or `cancelled` with nothing kept | A line in About with its status (and a failed solve's error message). No values. |

Two cases are never rendered as an option the user cannot use:
- The Export button is rendered when the case shown has a response on screen (`response && !previousHidden`, the screen's rule after a failed solve), or when the Compare cases tab is shown and any case has a response.
- The Cases choice appears only with scenarios. Its default is the case shown, or All cases on the Compare cases tab.

After a failed solve the user can reveal the earlier results; Export is then offered, but the file follows Compare's rule. The dialog says so (§5.3), and Download image is unavailable with the same reason (§5.5), so the dialog, the workbook and the image use one rule.

### 2.5 Sheets and files

XLSX sheets and CSV files. Each is written only when it has rows, except About and Flags:

| # | Sheet | CSV file | Kind | Present when |
|---|---|---|---|---|
| 0 | none | `README.txt` | text, the zip's first entry | CSV only, always (§3.1) |
| 1 | About | `about.csv` | document (Section, Item, Value) | always |
| 2 | Flags | `flags.csv` | table | always (headers only when there are none) |
| 3 | Compare cases | `compare-cases.csv` | table, wide | All cases, 2 or more cases |
| 4 | Nodes | `nodes.csv` | table | node results |
| 5 | Links | `links.csv` | table | link results |
| 6 | Pipes | `pipes.csv` | child of Links | link results |
| 7 | Fittings | `fittings.csv` | child of Links | any fitting |
| 8 | Pumps | `pumps.csv` | table | pumps |
| 9 | Pump curves | `pump-curves.csv` | table | pumps |
| 10 | System curves | `system-curves.csv` | table | a computed system curve |
| 11 | Valves | `valves.csv` | table | valves |
| 12 | Branches | `branches.csv` | table | tees or wyes |
| 13 | Branch ports | `branch-ports.csv` | child of Branches | tees or wyes |
| 14 | Boundaries | `boundaries.csv` | table | reservoirs, reference nodes or plugs |
| 15 | Boundary ports | `boundary-ports.csv` | child of Boundaries | a boundary with more than one port (10 % of the corpus sample) |
| 16 | Assigned flows | `assigned-flows.csv` | table | assigned-flow nodes |
| 17 | Scenario changes | `scenario-changes.csv` | table | an exported scenario case |
| 18 | Goal seek | `goal-seek.txt` | document | a finished goal seek on an exported case |
| 19 | Methods | `methods.txt` | document | a case with a response |
| 20 | Trace | `trace.csv` | table, long | a single-case export of a converged case |

Sheet names are the view tabs' words (`VIEW_LABELS`) where one exists. They are fixed, at most 31 characters and contain none of `[]:*?/\`. The order follows the screen's tabs.

### 2.6 Tables

Notation: `{Q}` flow, `{H}` head, `{L}` length, `{D}` diameter, `{V}` velocity, `{Pg}` gauge pressure, `{Pa}` absolute pressure, `{dP}` pressure difference, `{P}` power and `{%}` fraction, each in the export units.

A **Flags** column holds the codes of the flags the screen attaches to that row, joined by `; `: `flagsForElement` for components and connections, `segmentFlags` and `fittingFlags` for pipes and fittings, and the port's flags for nodes. The full record is on the Flags sheet.

**Flags.** One row per flag: invalid, then warning, then info, in API order within each (`groupFlags`).
- Columns: `Severity` (Invalid, Warning, Info) · `Code` · `Element kind` (Component, Connection, Network) · `Element id` · `Element` · `Port id` · `Port` · `Pipe #` (`details.segmentIndex` + 1) · `Fitting #` (`details.fittingIndex` + 1).
- Then three message columns: `Message` (`flagText`, the app's words in the export units) · `Message (as reported, SI)` · `Details (SI, JSON)` (canonical JSON of `details`).

**Nodes.** One row per port result.
- `Component id` · `Component` · `Type` (`kindLabel`) · `Port id` · `Port` · `Elevation [{L}]` · `Pressure [{Pg}]` · `Dynamic pressure [{dP}]` · `Total pressure [{Pg}]` · `Absolute pressure [{Pa}]` · `Velocity [{V}]` · `HGL [{H}]` · `EGL [{H}]` · `Flags`.

**Links.** One row per connection.
- `Connection id` · `Connection` ("From → To", endpoints as solved) · `From id` · `From port` · `To id` · `To port` · `Flow (+ from → to) [{Q}]` · `Largest velocity [{V}]` (the largest |v| over its pipes: Compare's and goal seek's `linkVelocity`) · `Head loss (EGL from − to) [{H}]` · `Friction loss (+ with the flow) [{H}]` · `Fittings loss (+ with the flow) [{H}]` · `Pipes` (count) · `Fittings` (count) · `Flags`.
- The API's top-level velocity, Re, f and regime describe the first pipe only, so they are not written here. The screen avoids them for connections of several pipes, and Pipes holds each pipe's values.

**Pipes.** One row per pipe of a connection.
- `Connection id` · `Connection` · `Pipe #` · `Material` (library name, else the id) · `Schedule` · `Nominal size` (`npsLabel`) · `Inner diameter [{D}]` · `Length [{L}]` · `Roughness [{D}]` · `Velocity (signed as the flow) [{V}]` · `Re` · `f (Darcy)` · `Regime` · `Friction loss (+ with the flow) [{H}]` · `Flags`.
- Material, schedule and size come from the case as solved, so a scenario's pipe spec applies. A custom pipe's spec uses the words Build shows for it. Diameter, length and roughness are the values the solver used (`SegmentResult`).

**Fittings.** One row per fitting.
- `Connection id` · `Connection` · `Fitting #` · `Type id` · `Fitting` (library name, else `fittingFallbackName`) · `Pipe #` (the solved project's `Fitting.pipeIndex` + 1: the pipe its K is referred to; a reducer sits between that pipe and the next) · `Quantity` · `K (each)` · `K referred to diameter [{D}]` · `Head loss, all (+ with the flow) [{H}]` · `K source` (`FittingResult.source`, verbatim) · `Flags`.

**Pumps.** One row per pump. The control columns are always present, empty for a fixed-speed pump, so the columns do not depend on the project.
- `Pump id` · `Pump` · `Status` (`pumpStatusLabel`) · `Speed [{%}]` (empty when off, as on screen) · `Control` (Fixed speed, Flow) · `Flow setpoint [{Q}]` · `Control state` (`PUMP_CONTROL_STATE_LABELS`) · `Setpoint achieved` · `Flow [{Q}]` · `Head [{H}]` · `In curve range` · `Efficiency [{%}]` · `Hydraulic power [{P}]` · `Shaft power [{P}]` · `NPSHa [{H}]` · `NPSHr [{H}]` · `NPSH margin [{H}]` · `Suction absolute pressure [{Pa}]` · `Flags`.

**Pump curves.** One row per point of `PumpResult.curve`, the curve at the operating speed.
- `Pump id` · `Pump` · `Point #` · `Flow [{Q}]` · `Head [{H}]`.

**System curves.** One row per point of every `ready` curve in the case's slot: the default range and any overlay range.
- `Pump id` · `Pump` · `Flow from [{Q}]` · `Flow to [{Q}]` (`flowRange`) · `Point #` · `Flow [{Q}]` · `Head [{H}]` (empty without one) · `Converged` · `Reason code` (the API's `reason`) · `Reason`.
- `Reason` is the text the chart's data table shows for a point without a head. The export calls the same function (`systemPointNote`, through `pumpChartData`'s rows), never a copy: another workflow is rewording these messages now.
- About lists the pumps without a computed curve: "not computed: open the pump's chart to compute it", "being computed when exported", "failed: {message}" or "cancelled". The sheet and About use one rule (§12 item 25): a pump is included when any curve of it is ready in the case's slot, so a pump whose only ready curve is an overlay range (drawn with another case's chart) is included, and About says that only that range is in the file and why its default range is not.

**Valves.** One row per valve.
- `Valve id` · `Valve` · `Type` (`valveTypeLabel`) · `State` (`valveStateLabel`) · `Flow (+ inlet → outlet) [{Q}]` · `Head loss [{H}]` · `Pressure drop, static [{dP}]` · `K (open)` · `K referred to diameter [{D}]` · `K effective` · `Cv effective` · `Pressure setpoint [{Pg}]` (PRV, PSV) · `Flow setpoint [{Q}]` (FCV) · `Setpoint achieved` · `Flags`.
- The screen's one Setpoint column, whose unit depends on the valve type, becomes two columns with one unit each, by `ValveResult.valveType`.

**Branches.**
- `Branch id` · `Branch` · `Type` (Tee, Wye) · `Loss model` (`LOSS_MODEL_LABELS`) · `Flow pattern` (`branchPatternLabel`) · `Combined port id` · `Combined-flow velocity [{V}]` · `K is on` (from `branchVelocityBasis` after decision 29: "Combined-flow velocity" or "None (ideal or no flow)") · `Correlation` (API text, verbatim; for the Darby fallback it lists each leg's own Darby K and the conversion) · `In correlation range` · `Flags`.

**Branch ports.**
- `Branch id` · `Branch` · `Port id` · `Port` · `Flow (+ into the branch) [{Q}]` · `Combined port` · `K of the path from the combined port` (empty on the combined port) · `Velocity K is on [{V}]` (`|referenceVelocity|` for every other port of a non-ideal branch that carries flow, else empty) · `Path head loss (+ in the flow direction) [{H}]`.
- Each row reproduces its loss on its own: K·v²/(2g) equals the path head loss to the solve's tolerance (the oracle of §7.1; R measured at most 2.0×10⁻⁷ m over the 22 ports of the reference cases with a loss model; with the leg's own velocity, `tee_crane_bullhead_fallback`'s two paths come out 0.18–0.20 m, 24–28 %, low).

**Boundaries.** Reservoirs, reference nodes and plugs. Assigned-flow nodes have their own table, as on screen.
- `Boundary id` · `Boundary` · `Type` · `EGL [{H}]` · `Net outflow (+ into the network) [{Q}]` · `Ports` · `Flags`.

**Boundary ports.** Only for a boundary with more than one port. A single-port boundary's port carries its net outflow, which the API computes as the sum of its port outflows.
- `Boundary id` · `Boundary` · `Port id` · `Port` · `Outflow (+ into the network) [{Q}]`.

**Assigned flows.**
- `Node id` · `Node` · `Port id` · `Direction` (Demand, Supply, "None (as a plug)") · `Assigned flow (+ demand, − supply) [{Q}]` (signed, from the case as solved) · `Net outflow (+ into the network) [{Q}]` (`BoundaryResult.outflow`, −flow: D12's check) · `Elevation [{L}]` · `Pressure [{Pg}]` · `Absolute pressure [{Pa}]` · `HGL [{H}]` · `Flags`.

**Scenario changes.** One row per override of each exported scenario case, from the server's record (`response.scenario.overrides`), never from the web's mirror.
- `Change #` · `Target` (`changeTargetLabel`) · `Element id` · `Pipe #` · `Field` (`changeFieldLabel`) · `Field id` · `State` (Applied; Not applied: element not in the project; Not applicable) · `Value` · `Base value` · `Unit` · `Value (SI, JSON)` · `Base value (SI, JSON)` · `SI unit` · `Message`.
- `Value` and `Base value` are numbers in the export units, or text: the app's text (`changeValueText`) for a pipe spec, a status or a whole fluid; for a valve's `resistance`, `{kind} {String(coefficient)}` ("Cv 120", exact) or "Default" when null, since its value is `{kind, value}` and the two sides may use different kinds. `Unit` is empty for a text value. The JSON columns hold the values as the server recorded them (the resistance object, or null).
- A change the server did not apply (orphaned, not applicable) has empty `Value`, `Base value` and `Unit` cells: the server records both values as null unless it applied the change, and the screen shows only its message. "Default" is written only for an applied resistance with a null side (§12 item 26).
- An assigned-flow change is the signed flow (+ demand, − supply), as in Assigned flows.
- Fields and units are read from the project as solved, and names follow §2.2 item 5 (current for a current case, as solved for an out-of-date one).

**Compare cases.** Wide, one row per Compare row, in the order chosen on the Compare tab. It has no `Case`, `Solved at` or `Results` columns: its cases are its columns, and its first two rows give each one's state and solve.
- Leading columns: `Element id` · `Port id` · `Row` (`rowLabel`) · `Quantity` (`QUANTITIES[...].label`) · `Unit`.
- Then, per case: `{case}`; and for each scenario `{case}: difference from base` and `{case}: difference from base [%]`. `{case}` is "Base case" or "Name (id)".
- The first row is the Status row: the case's status label (`CASE_STATUS_LABELS`), and, for every case with a response, `; ` and `statusText`'s words ("Converged, 0 physically invalid", "2 physically invalid", "Did not converge"), except where the label already says it (`not_converged`). An out-of-date response that did not converge reads "Out of date; Did not converge".
- The second row is the Solved at row: each case's `SolvedState.timestamp`, empty without a response.
- Each network extreme (lowest pressure, highest velocity) is followed by a text row "… (where)".
- Differences are exact: `fromSI(value − base, unit)`. Every Compare category is factor-only, so this equals the difference of the converted values up to round-off. There is no "Same" snapping. A relative difference appears only for quantities with a true zero (`spec.relative`) and a nonzero base, computed as `(value − base) / |base| × 100`, Compare's formula.
- A case without values (did not converge, failed, not reached, not solved) has empty cells, and its Status row says why.

**Trace.** A single converged case only. Long format, in SI as reported. Elements are in component order, then connection order.
- `Element id` · `Element` · `Element type` (as reported) · `Part` (Inputs, Equations, Correlations, Data sources, Intermediate values, Notes: the trace view's headings) · `#` · `Name` · `Value` (number, text or boolean as reported) · `Unit` (as reported) · `Source` (inputs: user, default, library, computed) · `Text` (an equation's or note's text, a reference's citation).
- Port keys such as `P1:discharge` stay as reported; the `Element` column names the element.

### 2.7 About: the traceability block

About is a three-column document (`Section`, `Item`, `Value`). `about.csv` holds the same rows. Values are numbers where they are numbers, with the unit in the item's words ("Atmospheric pressure [kPa(a)]").

**Reading this file** (the first section, so the first rows of `about.csv` and of the sheet; its rows are the format's own):
- XLSX: "Row 1 of each sheet is a caption and row 3 holds the headers (pandas: `read_excel(..., sheet_name=None, header=2)`). Each row's case and solve: the Case, Solved at and Results columns."
- CSV, the words of `README.txt` (§3.1):
  - "These CSV files use a comma between fields and a point as the decimal mark (101.325 is about a hundred). For a spreadsheet, open the .xlsx export instead."
  - "Opened with a comma-decimal setting (German, French and many others), a spreadsheet reads values such as 101.325 as 101325, or as text, without any warning."
  - "LibreOffice: in the Text Import dialog choose Language: English (USA). Excel: use Data › From Text/CSV, File origin 65001: Unicode (UTF-8), then Transform Data, and for each number column Change Type › Using Locale… › English (United States)."
  - "Scripts: RFC 4180, UTF-8 with BOM. pandas reads every number exactly with `float_precision='round_trip'`; Python's `csv` module needs `encoding='utf-8-sig'`. A text cell that begins with =, +, -, @, a tab or a carriage return is written with a leading '; numbers and the JSON columns never are." (As built: the design's sentence named only = + - @, while the guard of §3.1 also covers TAB and CR; §12 item 29.)
  - "Each row's case and solve: the Case, Solved at and Results columns."

**Export**
- Title: "OpenSolve Pipe results". The project name, and its description when it has one.
- Exported at: ISO 8601 in local time with its offset (`2026-10-25T14:32:05+02:00`), from `now` and `utcOffsetMinutes`.
- Contents: "Case shown: Winter (S2)" or "All cases", and the sheets (or files) written, each with its row count.
- Units: the unit of every category; the note "Pressures are gauge unless marked (a) or psia; differences carry no marker."; and the exceptions of decision 5: "The trace, the methods text, the server's flag messages and the JSON columns are in SI as the server reported them. The app's sentences (flag messages, the goal seek report) give speeds and efficiencies in % and powers in kW (hp with gpm)." In SI mode: "Fractions (speed, efficiency) are 0–1 and carry no unit."
- Numbers: "Full precision: each number is the value the calculation server returned, converted to these units, not rounded. The app shows 4 significant figures, and heads, elevations and lengths to at least 0.01 m (or its equivalent); it shows head differences below 1×10⁻⁷ m, valve pressure drops below ρg·10⁻⁷ m and branch K below 1×10⁻⁴ as ≈ 0 (round-off). The file gives them as computed. Spreadsheets display and re-save at most 15 significant digits."
- Sign conventions: link flow + from → to; valve + inlet → outlet; pump suction → discharge; boundary outflow + into the network; assigned flow + demand; branch port flow + into the branch. "Losses are signed like the flow: negative where the flow runs to → from (outlet → inlet for valves); a branch path's loss is positive in the flow direction." Elevations and heads are measured from the project datum.
- Not in this file, and why: no trace in an All cases export; values of cases that did not converge or were not solved, with each one's reason; system curves not computed; with the link left out, "Project link: left out when exported".
- Software:
  - the web app's version (`appVersion`, the build commit), its source link at that commit (`sourceLinks(appVersion).source`) and its license (AGPL-3.0-or-later);
  - the calculation server's source, `serverSource`, "for the commit it runs now".
- Disclaimer: `DISCLAIMER` verbatim (GOALS §4.8).

**One block per exported case**, headed "Case: Winter (S2)" (or "Case: Base case"; or "Results" without scenarios):
- Status (`CASE_STATUS_LABELS`), and whether its values are in the file, with the reason when not.
- Out of date: "No", or `solveStatusLines`' words: "Results out of date: the project changed after this solve. Solve again before using these results." Then: "This file holds the results, names the elements and links the project, as solved." With the link left out: "This file holds the results and names the elements as solved (the project link was left out)." (§12 item 28.)
- Solved at: `SolvedState.timestamp`, the API's UTC string, verbatim. Compute time in s.
- Calculation methods version. Where the link recorded another one (`loadedMethodVersion`), MethodVersionNotice's sentence (GOALS §4.3).
- Server libraries: `methods.libraries`, one row each.
- Convergence: converged; inner and outer iterations; the largest continuity residual in m³/s and the largest energy residual in m, each with its element (SI, as reported); the oscillating components; the API's message.
- Atmospheric pressure used [`{Pa}`] (`SolvedState.atmosphericPressure`), and the site elevation [`{L}`] of the case as solved.
- Fluid (`SolvedState.fluid`): name, temperature, concentration, density, dynamic viscosity, kinematic viscosity (m²/s), and "Vapor pressure [`{Pa}`]" (absolute) or "Not available". Each property has its source (origin and citation). Every absolute pressure in About carries the absolute unit label.
- Headline values (cases with values): the lowest static pressure and where (`lowestPressureNode`), and the highest velocity and where (`fastestLink`).
- Scenario: its description, and the number of changes applied and not applied (Scenario changes has the list).
- System curves: included, and not included with the reason.
- Project link: which link below reproduces this case.

**Project links** (when "Include the project link" is on): each distinct link once, with the cases it reproduces.
- A case whose results are current gets the current project's link (`projectUrl(project, origin)`). Its staleness key equals the key of the solve, so it solves to the same results, and it carries the current names.
- An out-of-date case gets the link of `{...sentProjectFor(caseId), methodVersion: response.solvedState.methodVersion}`, labelled "the project as solved, before the later changes". The project as sent still records the version of the solve before it (the store records a new version only after a current solve, `#recordMethodVersion`). Writing the solve's own version is the same non-hydraulic update the store makes; the fingerprint leaves `methodVersion` out, so the link still reproduces the results, and its "last solved with" agrees with this case's block.
- Each link carries four notes:
  - "It opens on the base case; choose the case under Case."
  - "It holds the whole project: every input and every scenario."
  - "Plain text: copy it into a browser."
  - D14: "A link may fail to open, or solve differently, after a later change to the app; the methods version above records what produced these results."
- XLSX writes no link longer than 32,767 characters, the Excel cell limit. Instead it says "Not included: N characters, more than a spreadsheet cell holds; copy it from Share in the app". `about.csv` always holds the full link. The largest link in the corpus sample is 6,695 characters.

**Goal seek** (when included): the case it ran on, when it ran (local time, from `startedAt` and `utcOffsetMinutes`), the outcome title, and whether it is out of date and whether its values were applied.

### 2.8 Methods

For each case with a response, the Methods sheet and `methods.txt` hold `methodsText(methods, {projectName, caseName, timestamp, converged, stale})`, exactly as the Methods view's Copy as text produces it.
- The sheet has one row per line, with a `Case` column in a project with scenarios.
- `methods.txt` holds the cases' texts in case order, separated by one blank line. It is UTF-8 with CRLF.

### 2.9 Goal seek

The Goal seek sheet holds `goalSeekReport(response, request, context)`, built with the context GoalSeekResult builds for Copy report, with the file's units as preferences (the display units, or `SI_BASE_UNITS` in SI mode; speeds and powers as decision 5 says) and the export's `utcOffsetMinutes` for its run time (`ReportContext` gains an optional offset; without one it uses the machine's, as today). The sheet has one row per line, and a line's tab-separated parts (the trial table) go into consecutive cells. `goal-seek.txt` holds the same text with CRLF.
- The report already holds each value found exactly ("stored 0.0123456789…"), the bounds, the goals with their tolerances, the notes, the method with its references, and the trials.
- The goal seek's solved state at the values found is not exported: it is not a case. The dialog's contents list says: "Goal seek: the report only. To export full results at the values found, apply them and solve."

---

## 3. File formats

### 3.1 CSV and the zip

- **Dialect.** RFC 4180: comma separator, CRLF line ends (including the last line), one header row.
- **Quoting.** A field is quoted only when it contains `,`, `"`, CR or LF; a quote inside it is doubled. Numbers are never quoted.
- **Encoding.** UTF-8 with a BOM (EF BB BF). Headers and names hold non-ASCII characters (³, →, ·, −, °); without the BOM, Excel on Windows decodes the file as cp1252.
- **Numbers.** `String(n)` with `.` as the decimal mark, no grouping, and JavaScript's exponent form (`1.5e-7`, `1e+21`). `-0` becomes `0`. A non-finite value is an empty field; the API never sends one.
- **Booleans** are `TRUE`/`FALSE`. A null is an empty field.
- **Formula guard.** A text field that begins with `=`, `+`, `-`, `@`, TAB or CR is written with a leading `'`. Numbers, negative ones included, are never guarded. Nor is a `json` cell: canonical JSON begins with `-` only for a number literal (`/^-(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$/`), which no spreadsheet runs as a formula, while `'-0.01` is not JSON (R measured). The writer guards a `json` cell that does not match that grammar and begins with a guarded character, which canonical JSON never produces. Empty unit cells (dimensionless, §2.3) need no guard.
- **Documents.** `about.csv` is a table (Section, Item, Value), whose first rows are "Reading this file" (§2.7). `methods.txt`, `goal-seek.txt` and `README.txt` are UTF-8 with CRLF.
- **`README.txt`**, the zip's first entry: the export's title, project and time, then the CSV rows of §2.7's "Reading this file", word for word, then "The record of the cases, the solves and the software is in about.csv." It exists because the people who receive the zip never see the dialog's hint, and a comma-decimal spreadsheet misreads these files silently (§4.4 R2).
- **The zip** holds one top folder, `results {YYYY-MM-DD HHmm}` (the export's local time), and in it the files of §2.5, `README.txt` first. Entries are deflated (§3.3). The long name is on the `.zip` only: Windows' Extract All proposes `Downloads\{zip name}\`, so a folder named like the zip would double the path and pass Excel's 218-character limit for names over about 86 characters (W-WLP-4). With the short folder and a 26-character Downloads folder (`C:\Users\abcdefg\Downloads`), the longest path is 26 + 1 + 143 + 1 + 23 + 1 + 20 = 215 characters at the 147-character name cap (§3.5): the separator after Downloads, the zip's name without `.zip`, the folder and the longest file, `scenario-changes.csv`. (The design's first sum, 26 + 146 + 1 + 23 + 1 + 18 at a 150-character cap, left out that separator and took an 18-character file: the real worst case was 218, Excel's limit itself; §12 item 31.)

### 3.2 XLSX structure (ECMA-376 / ISO/IEC 29500 subset)

**Parts:**
- `[Content_Types].xml`, `_rels/.rels`.
- `docProps/core.xml`: `dc:title` (the project name, as plain XML text: a document property is not ST_Xstring, so it gets neither the `_xHHHH_` escape nor the cell cut; §12 item 30), `dc:creator` "OpenSolve Pipe", `<dcterms:created xsi:type="dcterms:W3CDTF">` with the export time in UTC to the second, `now.toISOString().replace(/\.\d{3}Z$/, 'Z')` (as Excel and exceljs write it), with the `dc`, `dcterms`, `cp` and `xsi` namespaces declared. No other property, and never the link.
- `xl/workbook.xml`: the sheets, and per sheet the defined names `_xlnm._FilterDatabase` (hidden, the autofilter range, as Excel writes it) and `_xlnm.Print_Titles` (`'Sheet'!$1:$3`).
- `xl/_rels/workbook.xml.rels`.
- `xl/styles.xml`:
  - fonts: regular and bold;
  - fills: the two Excel requires (`none`, `gray125`);
  - one border;
  - `cellXfs`: 0 (default), 1 (bold: the caption), 2 (bold, wrapped: the headers).
- `xl/sharedStrings.xml` (with `count` and `uniqueCount`).
- `xl/worksheets/sheetN.xml`.

**Worksheet**, in the schema's element order, with the exact XML where the schema's defaults would give something else:
- `dimension`;
- `sheetViews`: `<sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView>` (`CT_Pane`'s `state` defaults to `split`, which would split, not freeze);
- `<sheetFormatPr defaultRowHeight="15"/>` (`defaultRowHeight` is required by `CT_SheetFormatPr`: an empty element fails schema validation);
- `cols` (widths);
- `sheetData`;
- `autoFilter` (`A3:{last column}{last row}`).

Row 1 holds the caption in A1, in style 1. Row 2 is absent, so it is blank. Row 3 holds the headers, in style 2. Data starts at row 4. Document sheets (About, Methods, Goal seek) follow the same layout, so `header=2` reads every sheet.

**Caption** (A1):
- Single case: "{Sheet} — {project} — {case} — solved {timestamp} — calculation methods {v}".
  - Add " — OUT OF DATE: the project changed after this solve" when stale.
  - Add " — DID NOT CONVERGE: not a solution" for the Flags and Methods sheets of such a case.
- All cases: "{Sheet} — {project} — all cases (each row's case and solve: Case, Solved at, Results)". Add " — includes out-of-date results" when any exported case is stale, and " — includes a solve that did not converge" on Flags and Methods when any did not converge. About and Compare cases have none of those columns, so they point to where each case's solve is: "all cases (each case's solve and state: its Case block in this sheet)" and "all cases (each case's solve and state: the Status and Solved at rows)" (§12 item 27).
- Goal seek, in both modes: "Goal seek — {project} — {case it ran on, with scenarios} — goal seek run {local time with offset} — calculation methods {result.methodVersion}", and " — OUT OF DATE: the project changed after this goal seek" when the goal seek is out of date. A goal seek is its own set of solves: its caption never names the exported case's solve or that solve's staleness (§12 item 27).
- Both: add " — SI base units" in SI mode, and " — SI, as reported" on Trace, Methods and Flags' message columns.

**Cells:**
- **Numbers:** `<c r="B4"><v>{String(n)}</v></c>`, General format. Exponent forms read back exactly (measured: 1e-7, 5e-324, 1.7976931348623157e308).
- **Text:** a shared string (`t="s"`). `xml:space="preserve"` when the text has leading or trailing whitespace or a line break. A text cell is never a formula, so a name such as `=HYPERLINK(...)` stays text (measured in openpyxl and LibreOffice).
- **Booleans:** `t="b"`, `1`/`0`.
- **Null:** no `<c>`.
- **Sanitizing,** for every shared string, the captions and sheet text included:
  1. `& < > "` are escaped.
  2. The characters XML 1.0 forbids (C0 controls other than TAB, LF and CR, plus U+FFFE and U+FFFF) are removed. A lone surrogate becomes U+FFFD through `TextEncoder`.
  3. Every underscore that begins a literal `_xHHHH_` is written `_x005F_` (`.replace(/_(?=x[0-9A-Fa-f]{4}_)/g, '_x005F_')`): SpreadsheetML (ST_Xstring) decodes `_xHHHH_` as a character, so LibreOffice reads a name `Pump_x0041_B` as `PumpAB`, while openpyxl keeps it (R measured). The design's first form, `/_x([0-9A-Fa-f]{4})_/g` → `_x005F_x$1_`, matched without overlap, so of two sequences that share an underscore (`A_x0041_x0042_B`) it escaped only the first, and LibreOffice read the name as `A_x0041BB` (§12 item 30).
  4. CR is written as `&#13;`: XML parsing turns a literal CR, and CRLF, into LF (R measured in both readers).
  5. Text longer than 32,767 characters is cut to 32,766 plus "…"; the project link is the exception (§2.7).

**Column widths:** `clamp(max(header length, longest text among the first 200 rows) + 2, 8, 60)` characters, deterministic.

**Limits:**
- at most 1,048,576 rows per sheet (the largest measured case is 24,232 rows; 21 cases in long format at SDD's limits need at most 126,000);
- sheet names fixed by the app;
- no ZIP64: the writer refuses more than 65,535 entries or 4 GiB, neither of which can happen.

**Determinism.** The same `ExportInput` (with its `now`, `utcOffsetMinutes`, `appVersion`, `serverSource` and `origin`) gives the same bytes. Nothing inside the model or the writers reads the clock, the time zone, the environment (`PUBLIC_API_URL`), the build's version constant or a random source.

**MIME type:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

### 3.3 ZIP container (PKWARE APPNOTE 6.3 subset, `utils/export/zip.ts`)

- **Each entry:** a local header (version needed 20; flags `0x0800` for UTF-8 names; method 8; DOS time and date of the export's local time, `now` shifted by `utcOffsetMinutes`, since DOS time has no zone and Explorer, Archive Utility and `unzip -l` show it as local time; CRC-32; sizes; name), then its deflated chunks. After the entries come one central-directory record per entry and the end-of-central-directory record.
- **No data descriptors.** Each entry is compressed before its header is written. The compressed chunks are kept as `Blob` parts, never concatenated in JavaScript memory.
- **Compression:** pako `new Deflate({ raw: true, level: 3, chunkSize: 65536 })`. Its `onData` hands over each full buffer, which is kept without copying (L checked pako 3's `push`).
- **CRC-32:** IEEE, reflected `0xEDB88320`, a 256-entry table, incremental.
- The CSV zip uses the same container, with `.csv` and `.txt` entries. MIME type `application/zip`.

### 3.4 PNG

`utils/export/chart-image.ts`: `renderChartImage(Chart, config, caption) → Promise<Blob>`.

**Configuration.** PumpChart's `$effect` builds the datasets, options and the `caseLabels` plugin inline today. They move to `utils/pump-chart.ts` as `pumpChartConfig(data, others, {speedText, forImage})`, which both the screen and the image use. `others` is PumpsView's list, which takes each other case's response through `caseResponse` (§2.1) and keeps only those with values: a failed or not reached case's earlier response is no longer drawn on the screen's chart either (today PumpsView draws any converged response), so the image and the file agree.

**Where it lives.** `chart-image.ts` is imported by `chart-setup.ts` and exported from it, so it is in the chunk PumpChart already loads before it draws (decision 3).

For the image, `forImage` sets:
- `responsive: false`, `maintainAspectRatio: false`, `animation: false`;
- `devicePixelRatio: 2`, `events: []`, the tooltip off;
- fonts of 14 px (axis titles 15 px, legend 14 px);
- the screen's palette.

**The chart.** A detached canvas of 800 × 440 CSS px (1600 × 880 px). Chart.js draws it synchronously when animation is off (W measured 8–11 ms on a detached canvas).

**The composite canvas** is 1600 px wide at 2×, painted opaque white first. It draws three parts:
1. **Header.** Each line is wrapped with `measureText` at 1,520 px.
   - The title, `600 18px system-ui`: "Pump and system curves: {pump}", with ", {case}" in a project with scenarios (the figcaption's words).
   - A subtitle, 13 px, slate: "{project} · solved {YYYY-MM-DD HH:mm} (UTC±hh:mm) · OpenSolve Pipe calculation methods {v}", the solve's time in the export's offset (`chartImageCaption` takes `now` and `utcOffsetMinutes`, as the model does).
   - When the results are out of date, an amber line: "Out of date: the project had changed after this solve when this image was made."
2. **The chart image.**
3. **Footer**, 13 px, slate:
   - the sentences the figure shows under the chart, from one function both use (`chartNotes`, new in `pump-chart.ts`): the off or held note; the system-curve state (not computed with its reason, or "N of 41 points have no head"); how the system curve was computed; the dashed extrapolation with its range; and the other cases with their markers, "(out of date)" where stale;
   - then the `DISCLAIMER`;
   - then "OpenSolve Pipe · {origin}".

The height grows with the text, typically to 1,150–1,350 px; the plot stays fixed. Encoding is `toBlob(cb, 'image/png')`, never `toDataURL`, which holds 33 % more as base64. The chart is destroyed afterwards.

**No metadata chunks.** The visible caption is the record, and apps strip PNG text chunks anyway. The link never goes into an image.

**Not offered** for a solve that did not converge, nor while the case shown failed (§5.5).

### 3.5 File names (`utils/export/filename.ts`)

**Pattern:** `{project} - {case} - {content} {YYYY-MM-DD HHmm}{ (not converged)}.{ext}`
- `{case}`: the scenario's name, "Base case" or "All cases". It is left out when the project has no scenarios.
- `{content}`: "results" (`.xlsx`), "results (CSV)" (`.zip`), or "{pump} chart" (`.png`).
- The time is the export's local time, from `now` and `utcOffsetMinutes`.
- " (not converged)" is added when the single exported case has a response without values (`hasValues` false), current or out of date.
- The CSV zip's inner folder is `results {YYYY-MM-DD HHmm}`, never the file name (§3.1).

**Examples:**
- `Pump transfer between two tanks - results 2026-10-25 1432.xlsx`
- `Booster station - Winter - results (CSV) 2026-10-25 1432.zip`
- `Booster station - All cases - results 2026-10-25 1432.xlsx`
- `Booster station - Base case - Transfer pump chart 2026-10-25 1432.png`

**Sanitizing,** applied to each part:
1. Normalize to NFC.
2. Remove bidi controls (U+202A–202E, U+2066–2069) and zero-width characters (U+200B–200F, U+FEFF).
3. Replace each run of whitespace (`\s`, which includes NBSP and U+2028) with one space. W measured that a name with an NBSP gave no download at all in Chromium.
4. Replace each run of `<>:"/\|?*`, C0, DEL and C1 characters with one `_`, as Chromium does itself.
5. Trim spaces and dots at both ends.
6. Truncate by grapheme (`Intl.Segmenter`, else by code point): project 60, case 40, content 40.

An empty part falls back to "Untitled project" or "results". A name is at most 147 characters, so the longest path Windows' Extract All proposes stays 3 characters inside Excel's 218-character limit on a full path (§3.1). Unicode is kept: Chromium keeps it under a UTF-8 locale (W measured).

### 3.6 Building: scheduling, cancelling, memory

```ts
// utils/export/model.ts
export type CellValue = string | number | boolean | null;
export interface ExportColumn { label: string; unit?: string; kind: 'text' | 'number' | 'boolean' | 'json'; width?: number }
export interface ExportSheet {
  id: string;                 // 'nodes'
  title: string;              // sheet name: 'Nodes'
  file: string;               // 'nodes.csv' | 'methods.txt'
  kind: 'table' | 'document';
  caption: string;
  columns: readonly ExportColumn[];
  rowCount: number;
  rows: () => Iterable<readonly CellValue[]>; // built on the fly
}
export interface ExportBundle {
  sheets: readonly ExportSheet[];
  omitted: readonly { what: string; reason: string }[]; // what the dialog lists as left out
  warnings: readonly { kind: 'not_converged' | 'stale' | 'failed_shown'; text: string }[];
  fileName: string;
  folder: string | null;      // the CSV zip's inner folder; null for XLSX
  title: string;
  created: Date;
}
export function buildExport(input: ExportInput): ExportBundle;          // pure, deterministic, builds no cells

// utils/export/xlsx.ts, csv.ts
export function writeXlsx(bundle: ExportBundle, options?: WriteOptions): Promise<Blob>;
export function writeCsvZip(bundle: ExportBundle, options?: WriteOptions): Promise<Blob>;
export function toCsv(columns: readonly ExportColumn[], rows: Iterable<readonly CellValue[]>): string;
interface WriteOptions { signal?: AbortSignal; onProgress?: (p: { sheet: number; sheets: number; title: string }) => void }
```

- **One function for the dialog and the file.** `buildExport` builds no cells (rows are built on the fly), so the dialog calls it whenever a choice changes and lists `bundle.sheets` (title, `rowCount`), `bundle.omitted`, `bundle.warnings` and `bundle.fileName`. Download writes that same kind of bundle from a fresh snapshot, so the contents shown cannot drift from the file. The name shown carries the time the dialog last computed; the status line names the file actually made (§5.4).
- **Cooperative.** The writer yields through a `MessageChannel` (`utils/export/yield.ts`) after every 500 rows or 64 KiB of XML. At each yield it checks `signal.aborted` and throws an `AbortError`.
- **Streaming.** Rows are iterables built from each case's solved state as the writer asks for them, never one array: L measured a peak of 201 MB for 21 cases at SDD's limits, against 438 MB with the rows built in advance. The XML of a slice is encoded, deflated and kept as chunks.
- **No Web Worker** (decision 18).

---

## 4. Libraries and licensing

### 4.1 Options compared (L, measured)

**Workload.** Synthetic results tables at SDD §7.1's limit (1,000 components and 2,000 connections, the 1 MB body filled out with pipes and fittings): 10 sheets and 208,712 cells per case, unrounded doubles. "21 cases" is the base plus 20 scenarios in long format: 4,380,752 cells.

**Method.** Node 22.22, 4 vCPU. Each run is a fresh process, timing the generation only. Peak memory is VmHWM above the baseline after garbage collection.

| Option (version, license) | Chunk, gzip | 1 case: time / peak / file | 21 cases: time / peak / file | Output | Dependencies | Notes |
|---|---|---|---|---|---|---|
| **Own writer + pako raw Deflate + own ZIP** | **3,052 B** | 0.30–0.64 s (level 1–6) / 38–41 MB / 1.8 MB | 6.0–10.9 s / 201–245 MB / 37–43 MB | openpyxl: every cell exact; LibreOffice opens it, with filter, freeze and bold; `unzip -t` and `zipfile` OK | 0 new | the choice |
| Own writer + fflate 0.8.3 (MIT) | 7,594 B | 0.55–0.63 s / 51–59 MB / 1.9 MB | 10.6 s / 202 MB / 39.7 MB | same | 1 | the fallback; `zipSync` peaks at 395 MB for 21 cases |
| write-excel-file 4.1.1 (MIT) | 19,542 B | 1.64 s / 154 MB / 1.9 MB | 18.0 s / 1,025 MB / 39.7 MB | openpyxl exact | 2 | 10 releases April–June 2026, one breaking |
| excel-builder-vanilla 5.3.1 (MIT) | 16,525 B | 0.80 s / 183 MB / 1.9 MB | 18.5 s / 1,636 MB / 39.6 MB | **openpyxl's full load fails** (styles); `freezePane` throws | 2 | rejected |
| SheetJS CE 0.20.3 (Apache-2.0) | 105,741 B | 1.12 s / 195 MB / 4.0 MB | 56.0 s / **4,830 MB** / 84.3 MB | values exact; no bold or frozen header in CE | 1 | only on cdn.sheetjs.com; npm `xlsx` 0.18.5 has 2 high advisories |
| exceljs 4.4.0 (MIT) | 254,660 B | 1.86 s / 231 MB / 1.9 MB | 112 s / **4,049 MB** / 39.1 MB | openpyxl exact | **177** | last release 2023; its browserify bundle hides bundled notices |

### 4.2 Choice and fallback

- **The choice.** Our own SpreadsheetML writer (about 150 lines), our own ZIP container (about 90 lines with the CRC table), our own CSV writer (about 30 lines), pako 3.0.2's `Deflate`, and Chart.js 4.5 for the PNG. All of these are already in the bundle.
- **The fallback.** If the container ever misbehaves, use fflate 0.8.3 (MIT, no dependencies, no install scripts, published 2026-05-16), pinned exactly, behind the same sink interface: only the synchronous `Zip` and `ZipDeflate`, never its worker-based async API. It costs 4.5 KB gzip and one notice, which the plugin writes by itself (L verified).

### 4.3 Licensing and notices

- **No new license.** pako `(MIT AND Zlib)` and Chart.js (MIT) are already in `third-party-licenses.txt`, which stays at 11 packages (L verified in a build of the app at `f1b44c2`). TSD §11.1's count stays true.
- **The plugin** reads every chunk of the client build, lazy chunks included. It does **not** read Web Worker bundles: L built fflate into a worker and found it missing from the notices. Hence no worker (decision 18). Anyone who adds one later must run the plugin on `worker.plugins` too.
- **Dev only:** openpyxl 3.1.5 (MIT, published 2024-06-28) and its dependency et-xmlfile 2.0.0 (MIT, published 2024-10-25) are added to the API's `dev` dependency group. They never ship, both are MIT, and both were published well over two weeks ago.
- **Rejected on licence grounds:**
  - exceljs: its browser build would leave about 170 bundled packages' MIT, BSD and Zlib notices out of our file;
  - SheetJS: its distribution outside the npm registry escapes `pnpm audit` and release-age checks.

### 4.4 Measurements

**Data (D).** Corpus sample: 310 projects (every `ref_`, `unit_` and `ladder_` item plus 60 each of `fuzz_`, `fuzzfc_` and `fuzzaf_`), solved at the current tree: 282 converged, 28 not.
- Rows per case (median / p95 / max): nodes 12 / 50 / 606; links 7 / 27 / 303; pipes 7 / 33 / 303; fittings 4 / 15 / 303; pumps 1 / 3 / 5; valves 1 / 7 / 10; branches 2 / 9 / 200; branch ports 6 / 27 / 600; boundaries 3 / 5 / 8; flags 3 / 25 / 50.
- Trace rows per case: median 680, p95 2,001, max 24,232 (`ladder_100_1_crane_True`). For that case: 6.5 MB of sheet XML (1,593 unique strings), 0.79 MB deflated, 2.8 MB as CSV.
- Methods text: 17.7k characters median, 21.9k max.
- Link length (with the origin): median 2,299, p95 4,692, max 6,695. None exceeds 8,000 or 32,767.
- 31 of 310 projects (10 %) have a boundary with more than one port.
- Of 154,215 solved floats, 61.3 % need 16–17 significant digits to round-trip. A LibreOffice XLSX re-save kept 184 of 2,005 test doubles exact; the others changed at about 1e-15 relative.
- A hand-written minimal XLSX was read by openpyxl and `pandas.read_excel`: 2,005 of 2,005 doubles exact, booleans as `bool`, and `=HYPERLINK(...)` as text.
- CSV with BOM, CRLF and the quoting: pandas' default parser read 1,350 of 2,005 exactly (worst 5.7e-13 relative), and `float_precision='round_trip'` all of them. Python's `csv` with `utf-8-sig` gave a clean header. LibreOffice kept the guarded `'=HYPERLINK` and `'-North tank` as text.

**Web (W).** Playwright 1.56.1 with headless Chromium 141, at 1280×800 and 390×844 (DPR 3), and at 320, 640 and 1024 px.
- Downloads with `<a download>` and a blob URL arrived in every context, even 6 s after the click. Chromium turned `:/*?"<>|` into `_`, dropped a leading dot, and kept 300-character names.
- With `LANG` unset, every non-ASCII name was saved as "download"; with `LANG=C.UTF-8` they were kept.
- `navigator.share` and `canShare` are undefined in Linux Chromium.
- The on-screen chart canvas is transparent: 453×288 px at 1280, 1020×768 px on the phone.
- The fixed 2× render took 31–37 ms in total (PNG encoding 16–18 ms), 234 KB, byte-identical from desktop and phone.
- XLSX prototype build: 8–12 ms for 40 node rows; 112–136 ms for 2,000 rows (442–519 ms at 6× CPU throttling); 567–689 ms for 10,000 rows. CSV of 2,000 rows: 7 ms.
- Header layout:
  - A labelled extra button collapsed the "Results" heading to 0 px at 390 px and in the 409 px pane at 1024 px.
  - With an icon-only Export below a 30 rem header and `min-w-min` on the heading there was no overlap at 320–1280 px.
  - The same overlap already happens today with a scenario chip and a long status.

**Libraries (L).** As §4.1, plus:
- Cooperative slicing, 1 case: 500-row slices give a longest synchronous slice of 31 ms (24 ms at 21 cases, 850 slices); 2,000-row slices give 70 ms.
- Small projects: 2,198 cells in 14 ms warm (59 ms cold), 28 KB.
- In a build of the app at `f1b44c2`: total client JS 301,914 B gzip. A lazy pako export chunk was 2,755 B and the page grew by 375 B. A lazy chunk importing `utils/results.ts` at runtime added 1,547 B to the initial download.
- Chart.js's `Title` and `SubTitle` plugins would add 490 B gzip.

**Synthesizer (S).**
- **S1. Caption layout.** A hand-written workbook with the caption in A1, row 2 absent, headers in row 3, the pane frozen at A4, the autofilter on A3:C2003, Print_Titles `$1:$3`, 2,000 random doubles, booleans and a `=HYPERLINK("x")` text cell:
  - `pandas.read_excel(header=2)` (pandas 3.0.5) gave the three headers, 2,000 rows, 2,000 of 2,000 doubles exact, and a `bool` column;
  - openpyxl 3.1.5 read freeze `A4`, filter `A3:C2003`, print titles `$1:$3`, and the formula-like text as data type `s`;
  - LibreOffice (headless) converted it with the caption, a blank row and the headers, and kept the text as text.
  - Script: `synth/caption_check.py`.
- **S2. CSV floats.** pandas 3.0.5's default parser read 1,377 of 2,000 doubles exactly; `float_precision='round_trip'` read 2,000 of 2,000. This confirms D.
- **S3. Yields** (headless Chromium 141, 200 yields each): `await new Promise(r => setTimeout(r, 0))` cost 4.0 ms per yield (the nesting clamp); a `MessageChannel` round trip cost 0.0075 ms. At 850 slices, `setTimeout` would add about 3.4 s. `scheduler.yield` exists in Chromium but not in every target browser. Script: `synth/yield.mjs`.
- **S4. Licences.** PyPI metadata: openpyxl 3.1.5, MIT, 2024-06-28; et-xmlfile 2.0.0, MIT, 2024-10-25.
- **S5. Code checked:**
  - `store.calculating` covers solve, Solve all and goal seek, not system curves.
  - CompareView hides the response of a failed or not-reached case and shows no values for a case that did not converge.
  - `labelsKey` includes connection endpoints, so `labelsProject` follows a reversal (§9).
  - PumpChart's `import('./chart-setup')` has no `catch` (§9).
  - The Goal seek button hides its label below a 24 rem viewport (`max-[24rem]`).
  - `CASE_STATUS_LABELS` lives in a `.svelte` module script.
  - `systemCurves` is exposed for the active case only.
  - The chart is drawn for a solve that did not converge.

**Reviser (R).** Scripts in the design workflow's scratchpad, `reviser/`.
- **R1. Branch K basis** (`c1_branch.py`, `c1_oracle.py`, the API at the current tree). `tee_crane_bullhead_fallback` (TEE_PATTERN_FALLBACK): v_ref = 4.2331 m/s; run_inlet K = 0.787149, path loss 0.719170 m, K·v_ref²/2g = 0.719170 m, K·v_leg²/2g = 0.520096 m (v_leg 3.5999 m/s); run_outlet 0.759832 m against 0.580612 m. Over every reference case with a combined port and a loss model (22 ports), the largest |K·v_ref²/2g − path loss| is 2.0×10⁻⁷ m.
- **R2. CSV in other locales** (`c2.csv`, the §3.1 dialect, imported by LibreOffice 24.2 headless). de-DE (1031): 101.325 → the number 101325, 12.345 → 12345, 0.0123, 1.5, −0.5, 1234.5678 and 1.5e-7 → text, 1e-7 and 1e+21 → numbers. en-US (1033): every number right. `TRUE` is a boolean only with "Detect special numbers" on, else text. This confirms the correctness reviewer's runs (`review-correctness/out_*`).
- **R3. SpreadsheetML text** (`c9_xlsx.py`, shared strings, read by openpyxl 3.1.5 and LibreOffice). Unescaped: LibreOffice read `Pump_x0041_B` as `PumpAB`, openpyxl as written; `cr\ronly` and `line1\r\nline2` came back with LF in both. With `_x005F_` and `&#13;`, both readers returned the original text. openpyxl read the pane written as §3.2 gives it as `A4`.
- **R4. Schema** (ISO/IEC 29500-4 transitional `sml.xsd`): `CT_SheetFormatPr/@defaultRowHeight` is `use="required"`; `CT_Pane/@state` defaults to `split`.
- **R5. JSON and the guard.** `JSON.parse("'" + JSON.stringify(-0.01))` throws; the number-literal pattern of §3.1 accepts `-0.01`, `-1e-7`, `-1.5e+21` and rejects `-North tank`, `-2+3`.
- **R6. Code checked:** `store.caseStatus` returns `stale` for any out-of-date response (`project.svelte.ts`, `caseStatus`); `#solveCase` stores the project as sent, then records the method version only for a current response; `newId` returns the first id unused in the current project; PumpsView's other cases include a failed case's earlier converged response; `goalSeekReport` formats its run time in the machine's time zone (`localDateTime`); `SOURCE_URL` is a module constant of the build's version, and `serverSourceHref()` reads `PUBLIC_API_URL`.

---

## 5. Web

### 5.1 Rules the user can rely on

- Export makes no request and computes nothing: every number is one the server returned, in the units chosen.
- A file says which project, case and solve it holds, when it was made, under which methods version, and whether the results were out of date.
- A solve that did not converge never yields values or an image, and neither do the earlier results revealed after a failed solve.
- Every row says which case and solve it comes from, and whether those results are current.
- One click gives one file.

### 5.2 The Export button (`ResultsPanel.svelte`, header row)

- **Placement:** immediately left of Goal seek, so Goal seek does not move. It is a `btn` with a new `download` icon (an arrow down into a tray) and `data-export-button`.
- **Label:** "Export". The header row gets `@container`, and the label is `hidden @min-[30rem]:inline`, so below a 30 rem header the button is icon-only, 44×44 px. The query is on the pane, not the viewport, because the pane is narrow at 1024–1279 px (409 px at 1024).
- **Name:** `aria-label` "Export results", or "Export results of {case}" with scenarios (as Solve names its case), and "Export results of all cases" on the Compare cases tab, where the dialog opens on All cases (§12 item 34). The name contains the visible "Export" (WCAG 2.5.3). `aria-haspopup="dialog"`.
- **The heading fix:** the `h2` gets `min-w-min`. Without it any added button collapses the heading at 390 px and at 1024 px (W measured). The class also fixes an overlap that exists today with a scenario chip and a long status.
- **When it shows:** rendered as §2.4 says. It is never shown as an unavailable control on an empty or unsolved project, in line with UI/UX proposal item 2.
- **When it is unavailable:** while `store.calculating` is set, the button is `aria-disabled`, with an sr-only reason and a `title`. The reason is `calculatingReason(calculating, 'export', true)`, a new wording such as "A solve is running; export when it finishes, or Cancel stops it."
- **Ownership:** `ResultsPanel` owns the dialog (`let exportOpen = $state(false)`, then `{#if exportOpen}`) and the session's choices (`exportOptions`). Nothing goes through `Workspace` or the URL.
- **Loading** (decision 3): `utils/export/load.ts` (static, a few lines) holds one memoized `import('$lib/components/results/ExportDialog.svelte')`. ResultsPanel starts it at idle (`requestIdleCallback`, else `setTimeout`) when the Export button first renders, so the chunk usually arrives while the deployment is the page's own. A click awaits the same promise and then renders the component. A failed preload is forgotten, and the click calls `import()` again; but Chromium keeps a failed module for the page's life and does not fetch that URL again, so after a failed preload the click fails without a request. The toast (`ws.notify('error', …)`) then says: "This part of the app could not be loaded: the app may have been updated since this page opened, or the connection dropped. Reload the page (the project is in its link), then solve again." (The design's words named only a redeploy, wrong for a dropped connection; §12 item 33.) PumpChart's `import('./chart-setup')` gets the same catch (§9 item 3), with the figure's words.

### 5.3 The Export dialog (`components/results/ExportDialog.svelte`, on `ui/Dialog.svelte`)

A centred modal on desktop and a bottom sheet on phones, as the existing dialogs are. Title: "Export results".

The body, in order:
1. **Warnings**, for the cases the choice exports:
   - Did not converge (red box, as in MethodsSummary): "This solve did not converge: its values are not a solution of the network. The file holds its convergence report, flags and methods, but no values." For All cases: "{N} cases did not converge: the file lists them without values."
   - Out of date (amber box): "The project changed after this solve. The file holds the results, names and link of the project as it was solved, and says so in every row. Solve again for current results." With the link left out: "… holds the results and names of the project as it was solved (the project link was left out), …" (§12 item 28).
   - The latest solve of the case shown failed and its earlier results are shown (amber box): "The latest solve failed. The results shown below the error are from an earlier version of the project and are not in the file."
   - The warnings come from `bundle.warnings` (§3.6), so they use `hasValues` and `stale`: an out-of-date solve that did not converge gets the red box, with "out of date" in its text.
2. **Cases** (a fieldset with radio buttons, shown only with scenarios): "{case} (the case shown)" and "All cases (base and N scenarios)". The default follows the tab shown (§2.4).
3. **Format** (a fieldset):
   - "Excel workbook (.xlsx)" (default). Hint: "Every table on its own sheet, numbers as numbers in Excel in any language setting."
   - "CSV files (.zip)". Hint: "One file per table, comma-separated, UTF-8, dot decimals: for scripts. LibreOffice or Excel set to a language that writes decimal commas can read these values wrongly without a warning (101.325 as 101325); use the workbook there. The zip's README.txt says how to open them."
4. **Units** (a fieldset):
   - "Display units ({summary}, as set in Settings)" (default), for example "L/s, kPa(g), m".
   - "SI base units (m³/s, Pa, m, …)".
5. **Include the project link** (a checkbox, on). Hint: "The link lets anyone open the whole project: every input of every case and scenario. Without it, the file still holds the exported cases' inputs (in the Trace and the tables) and every name and description."
6. **Contents** (`buildExport(input)`, no cells built, §3.6): the sheets with their row counts, such as "About · Flags (3) · Nodes (12) · … · Trace (680 rows)". Then `bundle.omitted`: system curves not computed ("open the pump's chart to compute it"), cases without values with their status, the trace in an All cases export, and the goal seek's solved state.
7. **The file name**, in `font-mono text-xs break-all`.
8. **Download** (`btn-primary`, focused when the dialog opens). As built it is in the footer (below), not the body (§12 item 32).
9. **Hints:**
   - "Files are made in this browser; nothing is sent to the server."
   - "Nothing saved? Pages opened inside an app (Teams, Slack, Outlook) often cannot save files: open the page in your browser."
   - With pumps: "To save a pump chart as an image, use Download image under the chart (Pumps)."
10. **Status:** one `role="status"` line (`empty:hidden`), and one `role="alert"` line for failures (§5.4).

Footer: **Close**. Closing cancels a build in progress. As built (§12 item 32) the footer also holds the status and alert lines, Cancel while a build runs, and Download: the footer is always in view, so focusing Download on open never scrolls the body, which opens at its top with the warnings, Cases and Format in view; the warnings are Download's description, so a screen reader hears them with it. When Cancel goes (the build is cancelled or ends) while it has the focus, the focus moves to Download.

The choices are kept for the page session in `ResultsPanel`. They are never stored in the project, the link or `localStorage`, and they reset when another project is loaded (`store.onLoad`).

### 5.4 Progress, cancel, completion and errors

- **Download** takes the snapshot (`exportInput(ws, options, new Date())`) and starts the build.
- **After 300 ms,** if the build is still running:
  - the button shows the spinner (`motion-safe:animate-spin`) and keeps its width, with both labels in one grid cell as Solve's are;
  - a **Cancel** button appears beside it;
  - the status line says "Preparing the workbook: {sheet} (sheet {i} of {n})…". It is updated at most once a second, so screen readers are not flooded.
- **Esc, Close and Cancel** abort the build. The status then says "Export cancelled; nothing was saved."
- **When the file is ready:** `saveBlob(blob, fileName)`, then "“{file}” ({size}) is ready; your browser saves it to its downloads." The words say "your browser saves it", never "saved": browsers do not report whether a download was kept.
- **Errors:**

| Case | Behaviour |
|---|---|
| The build throws | `role="alert"`: "The file could not be made: {message}. Nothing was saved." The dialog stays open, and nothing is logged or sent. |
| The link is longer than a spreadsheet cell | About says so (§2.7); the export is never refused. |
| The chart cannot be drawn (no 2D context) | No Download image button; the figure already says the chart cannot be drawn. |
| A build is already running | The other controls are `aria-disabled`, with "A file is being prepared." One build at a time. |

### 5.5 Download image (`PumpChart.svelte`)

- **Placement:** a quiet button (`btn btn-quiet px-2 text-blue-800`, `data-chart-image`) on the line of "Show data table". The line wraps at 270 px.
- **Name:** "Download image", with the accessible name "Download image of the pump and system curves: {pump}".
- **Hidden** when the chart cannot be drawn (`unavailable`).
- **Unavailable** (`aria-disabled`, with an sr-only reason and a `title`) while:
  - the chart has not drawn yet: "The chart is being drawn.";
  - this pump's system curve, or another case's curve on the chart, is being computed: "Wait until the system curve is computed, or cancel it.";
  - the solve did not converge (`hasValues` false, current or out of date): "This solve did not converge: its values are not a solution, so no image is made.";
  - the latest solve of the case shown failed and its earlier results are shown: "The latest solve failed; the chart shows results from an earlier version of the project, so no image is made.";
  - a calculation is in flight: the reason of §5.2.
- **After a failed or cancelled curve** the image can be made, and its footer says that the curve was not computed and why, as the figure does.
- **Behaviour:** the image takes about 35 ms, so there is no progress. Completion is announced with `ws.notify('info', '“{file}” ({size}) is ready; your browser saves it to its downloads.')`, the existing polite toast, in §5.4's words (never "downloaded" or "saved": on iPhone the user can still cancel Safari's prompt). An error goes to `ws.notify('error', …)`.
- **Source:** PumpChart keeps the `Chart` class from its `import('./chart-setup')`, so the image never awaits it again.

### 5.6 Downloads on desktop and phones

`saveBlob(blob, name)` (`utils/export/download.ts`):
1. creates `URL.createObjectURL(blob)`;
2. appends an `<a download=name rel="noopener">`, clicks it and removes it;
3. revokes the URL after 60 s, not at once: some browsers cancel a download whose URL is revoked, and iOS Safari needs the URL while its "Download?" prompt is open.

What users get:
- **Desktop browsers:** the file goes to their downloads.
- **Android Chrome:** the file goes to Downloads, with a notification.
- **iOS Safari 13 and later:** a "Do you want to download …?" prompt, then the file goes to Files › Downloads. A workbook opens from there in Excel or Numbers. The image is in Files › Downloads too, not in Photos; Share › Save Image puts it in Photos.

Not used:
- `showSaveFilePicker` (Chromium only);
- `data:` URLs (size limits);
- FileSaver.js (not needed);
- Web Share (§10).

### 5.7 Accessibility and keyboard

- **Keyboard:** Tab to Export, then Enter. The focus lands on Download, so Enter, Enter downloads the defaults. The radio groups are fieldsets with legends and use the arrow keys. Esc closes the dialog (and cancels a build), and the focus returns to Export (`Dialog.svelte` does this already).
- **Initial focus:** an `$effect` on Download, as ShareButton focuses its field. `autofocus` is not used.
- **Touch and motion:** every control is at least 44 px (`btn`, `min-h-11`). The spinner is `motion-safe`.
- **Announcements:** within the dialog, one polite status line and one alert. The chart's download uses the toast. Nothing else is live.
- **No global shortcut.** UI/UX item 5's list can add one; Ctrl/⌘+S is not taken, since it means "save page" and the project lives in its link.
- **The image's text** uses the screen's validated palette on white.

### 5.8 Mobile (390 × 844, and 320 px)

- **The Export button:** icon-only in the header (decision 20). With `min-w-min` on the heading, the header is 53 px high with the status wrapped to two lines, and 89–109 px with a scenario chip and a four- or five-line status, against 77 px today, which the existing overlap achieves (W measured). If the UI/UX session makes Goal seek icon-only below 30 rem as well, the header returns to today's heights (53/77/77 px, W measured).
- **The dialog:** a bottom sheet with a scrolling body. The fieldsets stack, the file name breaks anywhere, and Download stays in view in the footer (§12 item 32; the design had it at the end of the body, where focusing it scrolled the warnings out of view).
- **The chart button** wraps under "Show data table" at 320 px.

### 5.9 Footprint against `docs/proposals/ui-ux-refinement.md` (another session's)

- **The `ResultsPanel` header** (their items 1 and 2): one button before Goal seek, `@container` on the row, and `min-w-min` on the `h2`.
  - Export follows item 2's rule: it is shown when there is something to export.
  - Item 1 (merging the convergence card into this line) needs to keep one 44 px slot for Export, or move Export and Goal seek into an overflow menu. Either is theirs to decide; e2e tests select by `data-export-button`, never by position.
  - The dialog's lazy import and its preload live in `utils/export/load.ts`; ResultsPanel only calls it, so a move of the button (an overflow menu) takes one call with it.
  - Under the Branches table, one paragraph of the velocity note goes (decision 29); no layout change.
- **`Workspace.svelte` and `WorkspaceHeader.svelte`:** no change.
- **`PumpChart`** (their item 12, chart layers): one quiet button, and the configuration in `pumpChartConfig`, so any layer they add is in the image too.
- **Sortable tables** (their item 9): exports keep project order, not a screen sort, so files are stable and can be compared.

### 5.10 Store and workspace

- **`state/project.svelte.ts`:** `systemCurvesFor(caseId)`, a read-only getter for a case's slot (the active case's slot is already `systemCurves`).
- **`state/workspace.svelte.ts`:** no change. `exportInput(ws, options, now)` is in the lazy chunk (`utils/export/input.ts`) and reads the workspace's public getters, as §2.1 describes.
- **`utils/compare.ts`:** `caseResponse(status, results)`, Compare's rule as one function, used by CompareView, PumpsView's other cases and the export (§2.1).
- **`utils/goal-seek.ts`:** `calculatingReason` gains the `'export'` wording; `ReportContext` gains an optional `utcOffsetMinutes` for the report's run time (§2.9).
- **`CASE_STATUS_LABELS`** moves from `CaseStatusChip.svelte`'s module script to `utils/labels.ts`, which the chip re-exports, so a `.ts` module can import it.

---

## 6. Privacy

- **Nothing leaves the browser.** Export builds the file from the page's memory and saves it through a Blob URL. It sends no request: no endpoint, no `/about` fetch, no analytics, no third-party code. The e2e tests assert that no http(s) request is made from the click to the download (§7.3).
- **No data is fetched or sent.** The export's code is a static, same-origin chunk of the app (decision 3), requested once like the chart's: a GET that carries no project data, no query and no fragment. The e2e tests allow, from the click to the download, no request but a GET of a same-origin `/_app/immutable/` file without a query (§7.3).
- **Nothing is stored.** The dialog's choices are page state. Nothing goes into `localStorage`, the project or the link. The Blob URL is revoked after 60 s.
- **What the file holds is the user's.** The file is local and under the user's control. It holds names, descriptions, results and the exported cases' inputs: a one-case file's Trace lists every element's inputs with their sources, and the tables hold pipe specs, lengths, pump curves and scenario changes. With the link (the default) it also holds the whole project, every input of every case and scenario, and reopens it; the dialog says so beside the checkbox.
- **Never hidden.** No project data goes into document properties beyond the project name as the title, and none goes into image metadata. The link never goes into either.
- **Third-party input is inert.**
  - Names come from links that anyone can send. In XLSX they are typed string cells, never formulas.
  - In CSV, text that a spreadsheet would read as a formula is guarded with `'` (OWASP).
  - XML-invalid characters are removed and markup characters are escaped.
- **The server** is untouched: no request body or log changes, and D10's rules hold as they are.

---

## 7. Tests

### 7.1 Web unit tests (Vitest)

**Writers, against exact file contents:**
- `utils/export/csv.test.ts`: exact strings for small tables:
  - the BOM, the header, CRLF including the last line;
  - quoting of `,`, `"`, CR and LF; doubled quotes;
  - `String(n)` for `0.1`, `1e-7`, `1e+21`, `-0` → `0`, `5e-324`;
  - `TRUE`/`FALSE`, and empty fields for null;
  - the formula guard on `=1+2`, `+A1`, `-North tank`, `@SUM(A1)`, TAB and CR text, and **not** on the number −5;
  - a `json` cell `-0.01` written as `-0.01`, which `JSON.parse` reads back as −0.01, and an empty dimensionless `Unit` cell, both unguarded, while a `text` cell `-North tank` and `=1+2` stay guarded.
- `utils/export/zip.test.ts`:
  - CRC-32 of "The quick brown fox jumps over the lazy dog" is `414fa339`, and it equals `node:zlib.crc32` incrementally over 200 random chunks;
  - parse the archive by APPNOTE offsets, `inflateRawSync` each entry, and compare it with its input;
  - the UTF-8 name flag; DOS time from `now` and `utcOffsetMinutes` (the local time, not UTC);
  - the CSV zip's entries all under `results {YYYY-MM-DD HHmm}/`, with `README.txt` first;
  - identical bytes for identical input; the refusals beyond 65,535 entries and 4 GiB.
- `utils/export/xlsx.test.ts`: the exact XML of every part of a tiny workbook (two sheets, three rows), as inline expected strings:
  - content types, rels, `core.xml` (with `xsi:type="dcterms:W3CDTF"` and the time to the second, `Z`), the workbook with both defined names, and styles;
  - each sheet: caption in A1, row 2 absent, headers in row 3, the pane exactly as §3.2 (`state="frozen"`, `activePane="bottomLeft"`, the selection), `<sheetFormatPr defaultRowHeight="15"/>`, cols, autofilter;
  - shared strings with counts and `xml:space="preserve"`; number, boolean and text cells;
  - escaping, removed control characters, `Pump_x0041_B` written as `Pump_x005F_x0041_B`, CR written as `&#13;`, the 32,767 cut, the sheet-name rules, and the element order.
- `utils/export/filename.test.ts`: NFC; NBSP and other whitespace; reserved characters; bidi and zero-width characters; leading dots and spaces; grapheme truncation and the code-point fallback; empty parts; the name cap (147 as built: §12 item 31) and the longest path Extract All proposes; local time from `now` and `utcOffsetMinutes` (the same name under two values of `process.env.TZ`); the "(not converged)" rule, for a current and an out-of-date response without values; the zip's inner folder name.

**The model, against oracles, not snapshots** (`utils/export/model.test.ts`), over the shared fixture input (§7.2) and the `testing/results.ts` factories:
1. **SI mode:** every number cell equals its API field, bit for bit, by a column-to-field map written in the test (the map of item 3).
2. **Display mode:** every number cell equals `fromSI(api, unit)`.
3. **Screen agreement**, over one explicit map from each export column to its API field and unit category:
   - the row keys and order of each table equal the screen table's;
   - (a) the export cell `=== fromSI(field, exportUnit(category))`;
   - (b) for every column the screen also shows, the screen cell's text (its `valueText`, or the NotedText's `title` for "≈ 0") equals `new Formatter(prefs).num(field, category)`, or `.diff(field, category, noise)` with the screen's noise, of the same field. So the screen and the file read one field with one category, and the file is never compared with a rounding of itself;
   - named departures, each asserted on its own: the signed assigned flow (the screen shows |flow| with its Direction); the per-pipe and per-port child rows (the screen packs them into one cell); the valve setpoint split into two columns; "≈ 0" snapping (the file has the value); heads and lengths shown to at least 0.01 m on screen.
4. **Not converged:** no element tables, curves or trace; About, Flags and Methods present, with captions that say so and `Results` "Did not converge" on every Flags row. The same for a response that did not converge and is out of date (`caseStatus` `stale`): no values, the red warning, the "(not converged)" suffix, and Compare's Status row "Out of date; Did not converge".
5. **Out of date:** About, every caption, every row's `Results` and Compare's Status row say so, and the case's link is the project as sent with the solve's methods version.
6. **Names and structure as solved:**
   - a current case: rename an element, and the export shows the new name;
   - an out-of-date case: reverse a connection after solving, and the export keeps the solved "From → To" and the flow sign; delete valve `V2` and add a PRV (which `newId` names `V2` again), and the stale `V2` row shows the solved gate valve's name and type, as the as-solved link does.
7. **Cases:**
   - `Case id` and `Case` columns appear exactly when the project has scenarios; `Solved at` and `Results` always;
   - All cases stacks the rows in case order, holds Compare cases and no Trace;
   - an All cases export with one out-of-date case and one that did not converge marks exactly those rows, in Flags and in the element tables;
   - failed, not reached and not solved cases appear in About only;
   - a failed case's earlier response is not used, even when revealed, and the bundle warns `failed_shown`.
8. **Links:**
   - a current case gets the current project's link, an out-of-date case the project as sent, and each distinct link is written once;
   - an out-of-date case of a project opened from a 1.1.0 link and solved under 1.2.0 records 1.2.0 in its link, as its About block does;
   - with the checkbox off, no link and the "left out" line;
   - a link over 32,767 characters gives the note in XLSX and the full link in `about.csv`.
9. **Compare cases:** for the rows of `compare.test.ts`, the export's values and differences equal `compareCells`' exact values (the `title` differences), with no "Same".
10. **Documents:** Methods equals `methodsText(...)` line by line; Goal seek equals `goalSeekReport(...)` with tab-split cells; About holds `DISCLAIMER` verbatim.
11. **Boundary ports:** they appear only for a boundary with more than one port.
12. **System curves:** the reasons equal the chart data table's `note` for the same points.
13. **Branch K:** for every Branch ports row with a K and a velocity, |K·v²/(2g) − path head loss| ≤ 10⁻⁶ m + 10⁻⁶·|loss| (g = `STANDARD_GRAVITY`, converted to SI first), over the fixture's tees, the Darby fallback case included (R1: worst 2.0×10⁻⁷ m; the leg's own velocity fails by 0.18 m).
14. **Determinism:** the bytes of a workbook and a zip do not change when `process.env.TZ` or `PUBLIC_API_URL` changes, or under another build version; About's source link is `sourceLinks(input.appVersion).source`.
15. **Scenario changes:** a resistance change writes "Cv 120" (exact) or "Default" with an empty `Unit`, and its object in the JSON columns; a negative assigned flow is a number.

**The chart image:** `utils/export/chart-image.test.ts` covers the caption text, a pure `chartImageCaption()`: the title with and without a case, the subtitle's time and offset (from `utcOffsetMinutes`), the out-of-date line, and the footer, which equals `chartNotes(...)` plus the disclaimer and the app line. `pump-chart.test.ts` and `PumpsView`'s test: a failed, not reached or non-converged other case is not among `others`. jsdom has no canvas, so the drawing is covered by e2e.

**Components:**
- `ExportDialog.svelte.test.ts`:
  - which choices appear, with and without scenarios, and the Cases default by tab;
  - the warnings, including an out-of-date response that did not converge (red) and a failed case with its earlier results revealed (amber); the contents and omissions from `buildExport`; the file name following the choices;
  - Download focused on open; progress after 300 ms with fake timers;
  - Cancel, Close and Esc abort, with the status words; the alert on a build error;
  - one build at a time.
- `ResultsPanel.svelte.test.ts`:
  - the button rendered only with something to export (including Compare with another case's results, and not when the latest failed solve hides the earlier one);
  - `aria-disabled` with the reason while calculating; its name with scenarios;
  - the chunk preloaded once when the button first renders, and a failed import giving the reload message (a mocked loader).
- `PumpChart.svelte.test.ts`: the image button's unavailable states and reasons, including an out-of-date solve that did not converge and a failed case with its earlier results revealed; hidden when unavailable.

### 7.2 The shared fixture and the independent reader

- **The input.**
  - `apps/api/tests/fixtures/export_input.py` (new) solves three small projects with the real API: the "Pump transfer between two tanks" example; a project with two scenarios, a tee, a PRV, a two-port reservoir and an assigned-flow node, where one scenario changes the PRV's resistance to a Cv (`{kind: 'Cv', value: …}`) and another sets a negative assigned flow, and where one element's name holds `_x0041_` and a CR; and `tests/reference/cases/tee_crane_bullhead_fallback.json` (TEE_PATTERN_FALLBACK, the Darby basis of decision 29).
  - Its output is the `ExportInput` JSON: the projects as sent, the responses, the system curve of one pump, a finished goal seek, and fixed `now`, `utcOffsetMinutes` (a nonzero offset, +120), `appVersion` (a fixed 40-hex commit), `serverSource`, `origin` and timestamps (computeTime and timestamps replaced by constants).
  - `scripts/gen-api-types.sh` writes it to `apps/web/src/lib/utils/__fixtures__/export-input.json`, as it writes the scenario and goal-seek fixtures.
- **The workbook.**
  - `utils/export/fixture.test.ts` builds the workbook of each fixture case with the real model and writer.
  - It asserts that the bytes equal the committed `__fixtures__/export-results.xlsx` and that the typed cells equal the committed `__fixtures__/export-results.expected.json` (sheet, cell reference, type, value).
  - With `UPDATE_FIXTURES=1` it writes both instead. So it fails while the committed files are stale.
- **The reader.** `apps/api/tests/unit/test_web_export_fixture.py` (new, openpyxl in the dev group) opens the committed workbook with `openpyxl.load_workbook` (the full load, which checks styles) and checks:
  - the sheet names and order; the caption in A1; an empty row 2; the headers in row 3;
  - `freeze_panes == "A4"`, the autofilter range and `print_title_rows == "$1:$3"`;
  - every cell's value and type against the expected JSON: floats by equality, booleans as `bool`, text as data type `s`, including a formula-like name, and the `_x0041_` and CR name equal to the original text (openpyxl decodes `_x005F_`, R3);
  - and that `zipfile.ZipFile(...).testzip()` is `None`.
- **The API's precedent:** API tests already read the web's copy of `openapi.json`; this one reads the web's workbook.

### 7.3 End to end (Playwright, `tests/export.e2e.ts`, desktop and mobile projects)

1. **Workbook.**
   - Open "Pump transfer between two tanks", solve, then Export and Download.
   - `download.suggestedFilename()` matches `^Pump transfer between two tanks - results \d{4}-\d\d-\d\d \d{4}\.xlsx$`.
   - The bytes start with `PK\x03\x04`; the central directory lists the expected parts.
   - The Nodes sheet's XML holds the pressure of the suction port as `String(n)` of the value in the intercepted `/solve` response, converted to kPa.
   - From the click to the `download` event, no http(s) request is made but a GET of a same-origin `/_app/immutable/` file without a query (the lazy chunk, if the preload had not finished).
2. **CSV.** The same project with CSV and SI: the zip lists `README.txt` first, then `about.csv`, `nodes.csv` and the others, in one `results {YYYY-MM-DD HHmm}` folder. `nodes.csv` starts with the BOM and the header row and uses CRLF, and a pressure cell is the exact `String(n)` of the response's value in Pa. `about.csv`'s first rows are "Reading this file".
3. **Scenarios.** A project with a scenario: Solve all, then Compare cases, then Export. Cases defaults to All cases, and the workbook holds Compare cases, `Case` columns and no Trace.
4. **Image.** Pumps: wait for the system curve, then Download image. The file has the PNG signature, an IHDR width of 1600 and an opaque top-left pixel (IDAT inflated with `node:zlib`).
5. **States.**
   - Export is `aria-disabled` with its reason during a solve (a delayed route).
   - After an edit (out of date), the workbook's About says so.
   - A solve that did not converge gives a workbook without a Nodes sheet and with "(not converged)" in its name. No e2e flow has such a solve today, so the test answers `/solve` with a recorded non-converged response (`page.route`); the real-solver case is covered by Vitest over the fixture.
6. **Phone (390 × 844):** the dialog is a bottom sheet; Download is reachable and focused; the same assertions as test 1.

Names in e2e are ASCII: with `LANG` unset, as in CI, Chromium saves non-ASCII names as "download". A Unicode name is tested only in Vitest.

### 7.4 By hand, once before release and whenever the writer changes

Record the result in the TSD:
- Open the fixture workbook without a repair prompt in Excel 365 (Windows, macOS, web), Numbers (macOS, iOS), Google Sheets and LibreOffice. Check the frozen headers, the filter and the print titles, and check that Ctrl+T in Excel selects from row 3.
- The CSV zip under a comma-decimal setting: LibreOffice with Language German (Germany) in Text Import (101.325 must not become 101325 once README's step is followed), and Excel on Windows with German regional settings: a double-clicked CSV (one column expected), then README's Data › From Text/CSV steps. Correct README's wording to the menus the check finds.
- Extract the CSV zip with Windows' Extract All, with a project and case name at the length caps, and open a CSV from the extracted folder in Excel.
- iPhone Safari (iOS 17 or 18): download the workbook, then the prompt, then Files › Downloads, then open it in Excel and Numbers; download the image, find it in Files › Downloads, and save it to Photos with Share › Save Image.
- Android Chrome: all three formats.
- One in-app browser (Teams or Slack): the hint applies.

### 7.5 Acceptance

- Every API gate, unchanged by this slice.
- Every web gate (`pnpm test`, `check`, `lint`, e2e on both projects).
- `third-party-licenses.txt` unchanged (11 packages).
- The initial `/p` download grows by at most 3 KB gzip (the button, the loader, the image button and the shared-chunk cost of the lazy chunk), and the size of the export chunk itself, both read from the build's chunk report and stated in the PR.
- No file under `apps/api/src` changed.

---

## 8. What changes where

**Web (`apps/web`)**

| File | Change |
|---|---|
| `src/lib/utils/export/model.ts` (new, + test) | `ExportInput`, `ExportBundle` (with `omitted` and `warnings`), `buildExport`; the case rules (§2.4), captions, file name |
| `src/lib/utils/export/input.ts` (new, + test) | `exportInput(ws, options, now)`, the snapshot of §2.1 |
| `src/lib/utils/export/load.ts` (new, static, + test) | The memoized `import()` of the export chunk, its idle preload and the caught failure (§5.2) |
| `src/lib/utils/export/tables.ts` (new, + test) | The tables of §2.6, as row iterables |
| `src/lib/utils/export/about.ts` (new, + test) | About (§2.7), the links, the Methods and Goal seek documents |
| `src/lib/utils/export/units.ts` (new, + test) | `SI_BASE_UNITS`, `exportUnit`, header labels |
| `src/lib/utils/export/{csv,xlsx,zip,yield}.ts` (new, + tests) | The writers (§3.1–§3.3, §3.6) |
| `src/lib/utils/export/{filename,download}.ts` (new, + test) | §3.5, `saveBlob` |
| `src/lib/utils/export/chart-image.ts` (new, + test) | `renderChartImage`, `chartImageCaption` (§3.4), re-exported by `components/results/chart-setup.ts` so it is in that chunk |
| `src/lib/utils/export/fixture.test.ts`, `src/lib/utils/__fixtures__/export-input.json`, `export-results.xlsx`, `export-results.expected.json` (new) | §7.2 |
| `src/lib/utils/pump-chart.ts` (+ test) | `pumpChartConfig` (moved from PumpChart's `$effect`), `chartNotes` (the figure's sentences) |
| `src/lib/utils/results.ts` (+ test) | `orderedIds` exported. `branchVelocityBasis` loses `'own'` (decision 29): every non-ideal branch with flow is `'combined'`, so the screen pairs the API's K with `referenceVelocity`. `results.test.ts`'s Darby case uses K values the API returns (on v_ref), not the leg-velocity K it never sends. First commit of the build, before any export code. |
| `src/lib/utils/compare.ts` (+ test) | `caseResponse(status, results)` (Compare's rule, §2.1) |
| `src/lib/utils/labels.ts` | `CASE_STATUS_LABELS` (moved; re-exported by `CaseStatusChip.svelte`) |
| `src/lib/utils/goal-seek.ts` (+ test) | `calculatingReason(..., 'export')`; `ReportContext.utcOffsetMinutes` (optional) |
| `src/lib/state/project.svelte.ts` (+ test) | `systemCurvesFor(caseId)` |
| `src/lib/components/results/CompareView.svelte` | Uses `caseResponse` (no change in behaviour) |
| `src/lib/components/results/PumpsView.svelte` (+ test) | Other cases through `caseResponse`: a failed or not reached case's earlier response is no longer drawn (one line; another workflow is editing this file) |
| `src/lib/components/results/ExportDialog.svelte` (new, + test) | §5.3, §5.4 |
| `src/lib/components/results/ResultsPanel.svelte` (+ test) | The button, `@container`, `min-w-min` on the `h2`, `exportOpen`, `exportOptions`, the lazy dialog (`load.ts`); the branch table's note loses the Darby "own velocity" paragraph (decision 29) |
| `src/lib/components/results/PumpChart.svelte` (+ test) | Download image; the configuration from `pumpChartConfig`; the notes from `chartNotes`; a `catch` on `import('./chart-setup')` |
| `src/lib/components/workspace/CaseStatusChip.svelte` | Imports the moved labels |
| `src/lib/components/ui/Icon.svelte` | The `download` icon |
| `scripts/gen-api-types.sh` | Also writes `export-input.json` |
| `tests/export.e2e.ts` (new) | §7.3 |

`package.json` and `pnpm-lock.yaml` are unchanged. The generated `openapi.json` and `schema.d.ts` are unchanged.

**API (`apps/api`)**

| File | Change |
|---|---|
| `pyproject.toml`, `uv.lock` | `openpyxl>=3.1.5` in the `dev` group (et-xmlfile with it) |
| `tests/fixtures/export_input.py` (new) | §7.2's input |
| `tests/unit/test_web_export_fixture.py` (new) | §7.2's reader |
| `src/opensolve_pipe/**` | **no change** |

**Docs (made by the builders)**

| File | Change |
|---|---|
| `CLAUDE.md` | D5: move "CSV/XLSX/PNG export" from Deferred to "In v1" ("Export: results workbook, CSV files and pump chart images, made in the browser (D17)"); Deferred keeps "SVG, the schematic image". New D17 (draft below). The status line lists export among what v1 has. |
| PRD | §2.3 In v1 gains the export line, and the Later list keeps only "SVG and schematic image export". §3.2.3 drops "(Later)": the workbook (every results table, flags, curves, scenario changes, goal seek report, methods, trace for one case, About), CSV files in a zip, the pump chart as PNG, made in the browser, display or SI units; the schematic image and SVG stay Later. |
| SDD | §3.1.3 (Results Panel): an Export paragraph (the dialog, the chart image, the case rules). §5.1.4 becomes "Export (browser, D17): there is no export endpoint; files are made in the browser from the solve responses the page holds." |
| TSD | §8.3 (new) "Export": the module layout, the data contract, the CSV dialect, the XLSX subset and the ZIP subset (§2–§3 here). §10.3: the tests of §7.1–§7.3, and the record of §7.4. §11.1: the notices count is unchanged; a note that Web Worker bundles are not read by the plugin. §12: a decided item (export in the browser, own writer, the case rules). |
| `docs/proposals/export.md` | §12 "As built" after the build, as for the scenario manager and goal seek |
| `README.md` | The feature list gains export |

**CLAUDE.md D17, draft:**

> ### D17. Export (owner, 2026-10-25)
> Built from `docs/proposals/export.md`. Specs: PRD §3.2.3, SDD §3.1.3 and §5.1.4, TSD §8.3.
> - **Where.** In the browser, from the solve responses the page holds; no endpoint (SDD §5.1.4's is dropped), no request, nothing computed but Compare's differences; unavailable while a calculation runs; system curves only as computed. *(GOALS §4.5, §4.4.)*
> - **What.** A workbook (`.xlsx`) or CSV files (`.zip`) of the case shown or all cases: About first (how to read the file, project, case, solve time, methods version and libraries, convergence, atmosphere, fluid with sources, out-of-date state, the project link by default, web and server source, the disclaimer), flags, every results table one value per cell (pipes, fittings, branch and boundary ports as child tables), pump and computed system curves, scenario changes as the server applied them, Compare cases (all cases), the goal seek report, methods, and the trace (one case). Every table row carries its case, solve time and state (`Solved at`, `Results`). Display or SI base units, full precision, ids, names from the project the results belong to (current names for current results), structure as solved; branch K always on the combined-flow velocity. One rule decides values (Compare's, with `hasValues`): a solve that did not converge gives no values, current or out of date; an out-of-date one is labelled in every row and on every sheet. The pump chart as a 1600 px PNG with a caption, from the screen's own chart configuration; no SVG. *(GOALS §4.2.)*
> - **Formats.** CSV: RFC 4180, UTF-8 with BOM, `.` decimals, formula guard on text (not on JSON), `README.txt` first with how to open the files under a comma-decimal setting. XLSX: own SpreadsheetML subset (caption row 1, headers row 3, frozen, filtered, print titles), shared strings escaped for `_xHHHH_` and CR, no formulas, deterministic from its input alone; own ZIP on pako's raw deflate (level 3). A lazily loaded chunk (start-up +3 KB gzip at most). No new runtime dependency (notices unchanged; fflate 0.8.3 the fallback); no Web Worker (the notices plugin does not read worker bundles).
> - **Proof.** Writer tests against exact contents; model oracles (SI cells bit-identical to the API, display cells `fromSI`, rows, order and fields as the screen's, K·v²/2g equal to each branch path's loss); a committed fixture workbook read by openpyxl in an API test; e2e downloads on desktop and phone with no request sent but the app's own chunk.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| **Excel was not tested.** Only openpyxl, pandas and LibreOffice were available. Excel can show a "We found a problem with some content" repair prompt for XML that they accept. | The subset copies what Excel writes: shared strings, element order, the filter's defined names, the two required fills. The fixture is opened by hand in Excel, Numbers and Google Sheets before release and whenever the writer changes, and the result is recorded in the TSD (§7.4). |
| **Our own ZIP container** is code we must keep correct. | A fixed APPNOTE subset with refusals beyond it; CRC and inflate checked against `node:zlib`; Python's `zipfile` and openpyxl read the fixture; fflate 0.8.3 is a drop-in fallback behind the same interface. |
| **Phone performance is estimated,** not measured: about 1–2 s for the largest one-case workbook, 30–50 s and about 200 MB for 21 such cases. Old phones may kill the tab. | Cooperative slices (24–31 ms on desktop), rows on the fly, progress and Cancel. Typical projects take milliseconds (median 7,400 cells a case). The phone e2e project runs the workbook flow. |
| **Precision expectations.** The file holds 17-digit doubles, but spreadsheets display and re-save 15; pandas' default CSV parser misreads up to 5.7e-13 relative. | About says "full precision as written" and how to read exactly (`float_precision='round_trip'`). Both errors are 10¹⁰ or more below D6. |
| **Comma-decimal locales** (de, fr, …): the values are silently wrong, not just misplaced. LibreOffice in de-DE reads 101.325 as 101325 and 1.5 as text (R2); Excel opens a double-clicked CSV in one column, and its import types numbers in the system locale. The people who receive a zip never see the dialog. | The warning travels with the files: `README.txt` first in the zip and the first rows of `about.csv`, with the steps for LibreOffice and Excel; the dialog's hint names both. The workbook is the default and has no such problem. A locale-dependent CSV was rejected. Checked by hand in Excel (§7.4). |
| **The formula guard is visible:** a name such as "+10 m tank" shows a leading apostrophe in CSV viewers. | It is documented in About, and it is the accepted trade-off against CSV injection from shared links. XLSX needs no guard. |
| **The link discloses inputs.** A file sent to a third party carries every input and scenario, as a shared link does. | The checkbox, with a one-line warning beside it, which also says what stays without the link: the exported cases' inputs (Trace, tables), names and descriptions. |
| **Excluding a non-converged solve's values** may surprise a user who wants to debug in Excel. | The screen keeps the values; the file keeps the convergence report, flags and methods. It is reversible (D14, §10). |
| **The server commit** of a solve is not in the response. | The file names the methods version and library versions of each solve, and the server's current `/source`. Adding the commit to `MethodsSummary.libraries` would change every methods summary and needs its own change (§10). |
| **Drift from the screen.** Raw export tables built beside `results.ts`'s display tables could diverge in columns, order, fields or words. | The screen-agreement test (§7.1, item 3) compares keys, order and, through one column-to-field map, the field and category each side reads, with the deliberate departures named; the export reuses the screen's label helpers, never copies of them. Where the screen itself is wrong (the Darby K basis, decision 29), the screen is fixed first, never copied. |
| **System-curve reasons and issue texts** are being reworded by another workflow now. | The export calls `systemPointNote` and the chart's rows, never a copy, and is built on the merged version. |
| **Merge conflicts.** Another workflow is editing `PumpChart.svelte`, `PumpsView.svelte`, `ResultsPanel.svelte` and `pump-chart.ts`, and the UI/UX session will reshape the Results header. | Build export after their merge, or touch those files minimally: one button, one handler, the configuration extraction, the heading class. E2E tests select by `data-export-button` and `data-chart-image`. |
| **The image moves into a hidden canvas** whose layout browsers may treat differently; a zero-size canvas would draw nothing. | Explicit canvas attributes, `responsive: false` and animation off (measured in Chromium). If a browser gives a zero size, attach the canvas to a fixed off-screen container (`left: -10000px`, `aria-hidden`). The e2e test checks the PNG's size and an opaque pixel. |
| **Fonts in the image** are `system-ui`, so images differ slightly between operating systems: identical within one browser and font set, not across devices. Long names wrap the header and footer to more lines. | The plot region is fixed and the height grows to fit the text. |
| **In-app browsers** (Teams, Slack, Outlook on phones) often do not save blob downloads, and links are often opened there. | The dialog's hint to open the page in a browser. |
| **Unicode names in CI.** With `LANG` unset, Chromium saves non-ASCII names as "download". | ASCII names in e2e; the Unicode rules in Vitest. |
| **A Web Worker added later** would leave its packages out of `third-party-licenses.txt` (verified). | Stated in D17 and TSD §11.1. |
| **Bundle growth.** The export is estimated at 12–15 KB gzip (dialog, 20 tables, About, writers, image). | A lazy chunk (decision 3); the initial `/p` download may grow by at most 3 KB gzip, checked in the build change. |
| **A stale chunk.** A tab opened before a redeploy can fail to load the export chunk (hashed files of the old build are gone). | The chunk is preloaded at idle when results first exist, so the window is the time before the first solve; a failed load says to reload the page, which keeps the project (it is in the link) and asks for a new solve. `import('./chart-setup')` has the same exposure today and gets the same catch. Bundling is reversible (§10). |
| **Library names offline.** Material and fitting names fall back to ids or built-in names when the library is not loaded. | The values are still correct, only less readable; the ids are always present. |

**Found in passing, outside this slice:**
1. **Connection labels after a reversal.** The result tables label connections from `labelsProject`, which follows a reversal made after the solve. Out-of-date results can then show "B → A" beside a flow signed A → B. The export avoids this by reading endpoints from the project as solved; the screen deserves the same fix. *Done for the Links table in the build (§12 item 24); the other places are listed there.*
2. **The Results heading overlap.** Today the "Results" heading's width falls to 0 at 320 px, at 390 px and in the 1024 px pane when a scenario chip and a two- or three-line status are present. The heading, the chip and the status then overlap (W's screenshot `header5base-w390-staleScenario.png`). `min-w-min` fixes it. *Done in the build.*
3. **The chart import has no `catch`.** PumpChart's `import('./chart-setup')` has none, so a chunk that fails to load (a tab opened before a redeploy) leaves the chart blank without saying why. This slice adds it (§8). *Done in the build.*
4. **Branch K on the wrong velocity on screen** (review C-C1, fixed in this slice by decision 29). For a tee on the Darby fallback (TEE_PATTERN_FALLBACK), `branchVelocityBasis` returns `'own'` and the Branches table shows each leg's own velocity beside a K the API reports on the combined-flow velocity, so K·v²/2g comes out 24–28 % below the path loss (R1). ResultsPanel's note says the same, and `results.test.ts` tests it with a K the API never returns (1.088, the Darby K on the leg velocity, against the 0.787 the API sends). *Done before the build (`81627fd`, `a8b1d63`).*
5. **Re-used ids beside out-of-date results.** `newId` gives a deleted element's id to the next new one. The screen labels out-of-date results with the current names, so a stale row can carry another element's name, and Compare puts a stale case's old element and a current case's new one in one row. The export takes a stale case's names from the project as solved (decision 8); the screen could do the same, or `newId` could avoid ids that a kept response still names.
6. **Other cases on the pump chart.** PumpsView draws any other case whose response converged, a failed case's earlier response included, which Compare hides. This slice applies Compare's rule there (§3.4). *Done in the build.*

---

## 10. Open points the owner may want to revisit (none blocking)

1. **Web Share** ("Share file…") where `navigator.canShare({files})` accepts the file: Open in Excel and Save Image on iPhone. It needs the file built synchronously inside the click (decision 25) and manual testing on devices.
2. **A single-table CSV download** beside the zip, defaulting to the view shown, if users ask for one table without unzipping.
3. **The values of a solve that did not converge,** in a file marked as such, for diagnosis.
4. **Full-precision goal-seek tables** (variables, goals and trials as number cells), and the goal seek's solved state as an exportable case.
5. **SVG,** if users need vector charts (a second renderer, or a hand-built SVG of the same data).
6. **PNG metadata** (`tEXt` Title, Description, Software, Creation Time), repeating the caption and never the link.
7. **The server commit in each solve** (`MethodsSummary.libraries`), so that a file names the exact server source; this changes every methods summary.
8. **Display and SI values side by side,** or a third "both" option, if scripts and readers share one file.
9. **The trace in All cases exports,** with a size limit, if reviewers want every case's trace in one file.
10. **Bundling the export with the page** instead of the lazy chunk (decision 3), if users report the stale-chunk message; its cost is the chunk's size on every `/p` visit.
11. **A global shortcut** for Export, with UI/UX item 5's list.
12. **Clipboard copy** of a table (tab-separated), with the same locale caveat as CSV.
13. **A design-practice summary** (velocity limits, NPSH margin ratios), behind PRD §5's opt-in design checks.
14. **The schematic image,** when the schematic arrives (D5).

---

## 11. Design review

Two reviewers checked the design: one for correctness and traceability (issues C-C1 to C-C14), one for the web, libraries and performance (W-WLP-1 to W-WLP-7). The reviser checked each issue against the code at the current tree and by experiment (§4.4 R1–R6, scripts in `export-design/reviser/`). Every issue held. Two were the same defect (C-C7, W-WLP-2), and both are fixed by one rule. Where the reviser's fix differs from the reviewer's, the table says how and why.

| Issue | Verdict | What changed |
|---|---|---|
| **C-C1** (blocker) Darby fallback K exported on each leg's own velocity | Confirmed. `services/solver/results.py` converts Darby K to v_ref, and the API documents `kFactors` on the reference velocity. R1: on `tee_crane_bullhead_fallback`, K·v_ref²/2g = 0.71917 m equals the path loss, while the leg velocity gives 0.52010 m (28 % low). `results.ts` returns `'own'` for TEE_PATTERN_FALLBACK, and `results.test.ts` uses a K of 1.088 that the API never sends. | Decision 29: K is always on the combined-flow velocity. Branches' `K is on` has two values, and Branch ports' `Velocity K is on` is the magnitude of `referenceVelocity`. The screen fix (`branchVelocityBasis`, ResultsPanel's note, the test) is the build's first commit (§8), not only a §9 note (§9 item 4). The fixture gains the fallback case. Model oracle 13: K·v²/2g equals the path loss within 10⁻⁶ m + 10⁻⁶·\|loss\|, where the measured worst is 2.0×10⁻⁷ m. |
| **C-C2** CSV silently wrong under a comma-decimal locale; the warning never reaches recipients; decision 17 contradicts §9 | Confirmed. R2 reproduced it in LibreOffice 24.2 de-DE: 101.325 → 101325 and 1.5 → text; en-US is right. Decision 17 said "Excel (measured)" while §9 said Excel was not tested. | `README.txt` is the zip's first entry, and "Reading this file" is About's first section, with the LibreOffice and Excel steps (§2.7, §3.1). The dialog hint names both programs and says values can be wrong without a warning. Decision 17 now reads "measured in pandas, csv, LibreOffice; Excel by hand". §7.4 adds the de-DE LibreOffice and German-Excel checks and says to correct the README's menu names to what that check finds. The reviser also corrected §2.2's claim about booleans: LibreOffice reads `TRUE` as a boolean only with "Detect special numbers" on. |
| **C-C3** CSV files and All-cases sheets lose their solve and state | Confirmed (§3.1 has no caption, and the All-cases caption names no state). | Decision 28: every table, in both formats and with or without scenarios, has `Solved at` and `Results` after the Case columns. Compare cases gets a Solved at row. The All-cases caption points to those columns. The not-converged Flags rows say so in `Results`. Model test 7 covers an All-cases export with one stale case and one that did not converge. |
| **C-C4** A stale case can show another element's name (ids re-used) | Confirmed. `newId` returns the first id unused in the current project, and the fingerprint guarantees ids and kinds only for current cases. | Decision 8 and §2.2 item 5: a stale case takes its names from the project as sent, in its rows, connection ends and Scenario changes. A current case takes the current names. Compare cases, whose rows span cases, keeps the Compare tab's current names. The mixing this allows is a screen issue, recorded in §9 item 5. §7.1 test 6 is split into a current rename and a stale delete-and-add. |
| **C-C5** A stale response that did not converge would be exported as values | Confirmed. `caseStatus` checks convergence only when `!r.stale`. | §2.1 defines `hasValues` and `stale` from the response (CompareView's rule), and they decide everything; the status supplies words only. §2.4 is keyed by them. Compare's Status row reads the status label plus `statusText` for every case with a response ("Out of date; Did not converge"). Model, dialog and image tests cover a stale non-converged response. |
| **C-C6** The screen-agreement oracle cannot pass as written | Confirmed. `Formatter.num` keeps 0.01 m for heads and lengths (123.456 shows as 123.46, while `formatResultNumber` gives 123.5). `f.diff` snaps values to "≈ 0", assigned flow is shown as \|flow\|, and several cells pack parts. | §7.1 item 3 now has one column-to-field map with two exact checks. (a) The export cell equals `fromSI(field)`. (b) The screen text equals `Formatter.num/diff` of the same field. The departures are named. The Numbers row in About states the 0.01 m head resolution and the valve pressure-drop noise rule. |
| **C-C7** Formula guard breaks negative JSON values | Confirmed (R5: `'-0.01` does not parse as JSON). Same defect as W-WLP-2. | §3.1: a `json` cell that matches the JSON number grammar is never guarded. Unlike the reviewer's "`-` followed by a digit", the full grammar is required, so `-2+3` would still be guarded. `csv.test.ts` checks that it parses back. |
| **C-C8** The stale link records the previous methods version | Confirmed. `#solveCase` stores the project as sent, and `#recordMethodVersion` runs only for a current solve and changes only the current project. | §2.7: the stale link is written from `{...sentProjectFor(caseId), methodVersion: response.solvedState.methodVersion}`. The fingerprint excludes `methodVersion`. Decision 14 and model test 8 cover it. |
| **C-C9** `_xHHHH_` and CR in shared strings | Confirmed. R3: unescaped, LibreOffice read `Pump_x0041_B` as `PumpAB` and both readers turned CR into LF. Escaped, both readers returned the original text. | §3.2 sanitizing steps 3 and 4 apply to every shared string, captions included. `xlsx.test.ts` covers both. The fixture names an element with `_x0041_` and a CR, which openpyxl compares against the original text. |
| **C-C10** Schema-invalid `sheetFormatPr`; a split pane, not a frozen one; `dcterms:created` format | Confirmed (R4: `defaultRowHeight` is required, and `CT_Pane/@state` defaults to `split`). | §3.2 gives the exact XML for the pane (frozen, `bottomLeft`, with the selection), for `<sheetFormatPr defaultRowHeight="15"/>`, and for W3CDTF `created` to the second. `xlsx.test.ts` asserts all three. |
| **C-C11** SI mode is not one unit system | Confirmed. `displayUnit` fixes % and kW/hp, flag messages use them, the goal seek report was in display units, and vapor pressure had no (a). | Reviser's choice: list the exceptions rather than add an export-only override that would fork the app's sentences (decision 5). The goal seek report now follows the file's units (§2.9). About's Units row names every exception. Vapor pressure and atmospheric pressure carry the absolute unit label. |
| **C-C12** Losses are signed like the flow but not marked | Confirmed (`SegmentResult` and `FittingResult` both say "signed like the flow"). | The Links, Pipes and Fittings loss headers gain "(+ with the flow)", and the branch path loss gains "(+ in the flow direction)". About's sign conventions gain the losses sentence. |
| **C-C13** Button, workbook and image used three rules after a failed solve | Confirmed. After a reveal, `previousHidden` is false. PumpsView draws any converged other case, including failed ones. | One rule, `caseResponse` plus `hasValues` (§2.1), is used by the dialog, the workbook, the image and the other cases on the chart. The chart fix also changes the screen (PumpsView, §9 item 6). After a reveal, Export stays available and the dialog warns that the shown results are not in the file. Download image is unavailable there, with the reason. |
| **C-C14** A resistance change would come out as an empty cell | Confirmed. The value is `{kind, value}`, or null for the default. | Departure from the reviewer's fix: the Value and Base value can use different kinds (Cv against K), so one `Unit` column cannot label both. Each side is therefore written as exact text (`Cv 120`, or `Default`), with `Unit` empty and the object in the JSON columns (§2.6, §2.2 item 1). The fixture's scenario changes a PRV's resistance, and model test 15 covers it. |
| **W-WLP-1** The fixture bytes depend on the commit, `PUBLIC_API_URL` and the time zone; ZIP DOS time is in UTC | Confirmed. `SOURCE_URL` is a module constant of `version`, `serverSourceHref()` reads `$env/dynamic`, and local times use the machine's zone. The reviser found one more: `goalSeekReport` formats its run time with the machine's zone. | `ExportInput` gains `serverSource` and `utcOffsetMinutes`. About uses `sourceLinks(input.appVersion)`. Every local time (About, the file name, the ZIP DOS time, the PNG subtitle, the goal seek run time through an optional `ReportContext.utcOffsetMinutes`) is computed from `now` and the offset. The fixture fixes all of them with a nonzero offset. Model test 14 checks that the bytes stay the same under another `TZ` or `PUBLIC_API_URL`. |
| **W-WLP-2** The guard breaks JSON, and the SI `-` unit becomes `'-` | Confirmed (it is the same rule as C-C7, and `models/scenarios.py` writes `''` for none). | C-C7's exemption. Dimensionless SI values have no unit bracket and an empty `Unit` cell, as the API writes them (§2.3). `csv.test.ts` checks both, and that `-North tank` and `=1+2` are still guarded. |
| **W-WLP-3** The 10 KB bundled budget rests on the writer alone | Confirmed as a gap in the budget's basis. The 12–15 KB total is the reviewer's estimate from the module report, not a measurement; the reviser checked that report and found it plausible. | Decision 3 reversed: the export is a lazy chunk that imports the shared modules, as L measured (+1.5 KB at start-up). It is preloaded at idle when the Export button first renders, which narrows the stale-chunk window. A failed import gives a reload message. `chart-image.ts` goes in the `chart-setup` chunk. The gate is now: the initial `/p` download grows by ≤ 3 KB gzip. The reviewer proposed 2 KB, which would leave no room for the button, the image button and the loader on top of the 1.5 KB. §6's "no new code is fetched" now says a static chunk is fetched and carries no data, and the e2e request rule allows that chunk only. §9 adds a stale-chunk risk, and §10 item 10 now says bundling is the reversible alternative. |
| **W-WLP-4** A zip folder named like the zip doubles Windows paths | Confirmed by reasoning: Extract All proposes `Downloads\{zip name}\`. | The inner folder is `results {YYYY-MM-DD HHmm}`. The longest path at the name cap is 215 characters (§3.1; as built the cap is 147, since the first sum here missed a separator and the longest file name: §12 item 31). `zip.test.ts` and `filename.test.ts` check the folder, and §7.4 adds a Windows extraction at the length caps. |
| **W-WLP-5** The chart toast claims a download that was not confirmed; the PNG does not open in Photos from Files | Confirmed (§5.4's own rule; on iOS, Safari's prompt can be cancelled). | The toast uses §5.4's words. §5.6 and §7.4 now say the image is in Files › Downloads and that Share › Save Image puts it in Photos. |
| **W-WLP-6** The link hint suggests turning the link off keeps the inputs out | Confirmed: the Trace lists every input, and the tables hold specs, curves and changes. | The hint now says what the link adds and what stays without it (§5.3 item 5). §6 and §9 say the same. |
| **W-WLP-7** `exportContents` duplicates `buildExport` | Confirmed: rows are built on the fly, so `buildExport` builds no cells. | `exportContents` is dropped. `ExportBundle` gains `omitted` and `warnings` (and `folder`). The dialog lists `buildExport(input)`, so its contents and the file come from one function (§3.6, §5.3). |

---

## 12. As built

The web was built from §1–§11 by a model builder (`utils/export/` without the PNG, the API-side input fixture and the committed workbook) and a UI builder (the button, the dialog, the lazy loading, the chart image, the §5.10 changes and the e2e flows), after the screen fix of decision 29 (`81627fd`, `a8b1d63`). A screen fixer then fixed §9 item 1 for the Links table. An independent verifier who did not read `utils/export/` wrote the openpyxl reader (`apps/api/tests/unit/test_web_export_fixture.py`, 78 tests). An integrator reviewed every change against this design, ran the reader and the gates, measured the bundle, and wrote the specs (PRD §2.3 and §3.2.3, SDD §3.1.3 and §5.1.4, TSD §3.1, §8.3, §10.2, §10.3, §11.1 and §12 item 12, CLAUDE.md D5 and D17, README). Nothing under `apps/api/src` changed; the API gained openpyxl 3.1.5 and et-xmlfile 2.0.0 (both MIT) in its dev group, a fixture generator and two tests. `package.json`, the lockfile and the generated `openapi.json` and `schema.d.ts` are unchanged.

Where the build departs from this design, each departure is reversible (D14), and none weakens a rule of the design:

**Model and writers**

1. **Shared helpers.** `caseResponse` (`compare.ts`), `systemCurvesFor`, `CASE_STATUS_LABELS` in `labels.ts` and `ReportContext.utcOffsetMinutes` are as designed. `orderedIds` is not exported from `results.ts`: the export has its own ordering (`context.ts`, `orderedIds` and `orderedConnections`), and a test checks that its keys and order equal the screen tables' (`nodeTable`, `linkTable`, `segmentTable`, `fittingTable`, `pumpTable`, `valveTable`, `branchTable`, `boundaryTable`, `assignedFlowTable`).
2. **Types.** `ExportBundle` also holds `utcOffsetMinutes` (the zip's DOS times) and `readme` (`README.txt`'s lines); `ExportSheet` has an optional `text()` for the `.txt` documents (Methods, Goal seek); `ExportOptions` includes `format`, since the file name and the long-link rule depend on it; `exportInput` takes an optional fourth argument, the page's facts (build commit, server source, origin), for tests.
3. **One committed workbook.** §7.2 names one `export-results.xlsx` but three fixture projects. The committed workbook is the `scenarios` case (All cases, SI base units: 15 sheets, 4,219 cells); the other two cases feed the model's oracles. Its expected cells are `{generatedBy, input, sheets, cells}`, written through prettier, so no `.prettierignore` entry is needed.
4. **Words the design left open.** Without scenarios the reading note says "Each row's solve: the Solved at and Results columns." (there is no Case column). The Flags caption ends " — the server’s messages and the details in SI, as reported", since only those columns are in SI. Links' From port and To port hold port ids, and Fittings counts fitting entries, not their quantities. A custom pipe's Material is "Custom pipe" with Schedule and Nominal size empty; Schedule is the stored id; boundary types are the screen's words. Scenario changes' fields and units are read from the project as sent (ScenarioCard's rule). The Methods sheet has the Case, Solved at and Results columns; the Goal seek sheet's columns are "Goal seek report", "Part 2", "Part 3", …. Column widths count every cell's written text, numbers included. A file name over 147 characters (§12 item 31) is shortened at its longest part, one grapheme at a time.
5. **Zero-width characters in file names.** Removing U+200B–200F (§3.5) also removes the joiner (U+200D) of emoji sequences, which then save as their parts.
6. **A link's notes (integration).** "It opens on the base case; choose the case under Case." is written only in a project with scenarios: without them the app has no Case choice to point to. The other three notes are always written.

**Web**

7. **The chart's configuration** is `pumpChartConfig` in a new `utils/pump-chart-config.ts`, loaded only with the chart chunk (`chart-setup.ts` re-exports it with the image code), not in `pump-chart.ts`: in the page it put the initial download about 3.5 KB over its start, against the 3 KB budget. The screen and the image still draw from this one configuration.
8. **The chart chunk imports nothing from the page at run time.** The page passes in the number format, the legend labels, the notes, `MARKER_SYMBOLS` and `DISCLAIMER`; when the chunk imported them, the bundler split the shared code into a further chunk that the page loaded at start.
9. **`chartNotes`** gives the figure's sentences as the screen shows them, with a `reasonsIn` parameter, since the image has no data table to point to; the image's line naming the other cases and their markers is built in `chart-image.ts`. The screen's note texts are unchanged. `downloadChartImage` takes injectable render and save functions for tests (jsdom has no canvas).
10. **Close or Esc during a build** closes the dialog, so "Export cancelled; nothing was saved." goes to the page's notice; Cancel keeps the dialog open and says it in its status line.
11. **Choices across openings.** Format, Units and the link are kept for the page session; Cases goes back to its tab default each time the dialog opens. The focus returns to Export after closing only when the browser focused the button on the click, as `Dialog` does.
12. **Unavailable wording.** The Export button: "A solve is running; export when it finishes, or Cancel stops it." (also for Solve all and goal seek); the chart's button, which is not in the header: "… or Cancel in the header stops it."; a case a stopped Solve all did not reach gets its own sentence beside the failed one ("Solve all stopped before it reached this case; the chart shows results from an earlier version of the project, so no image is made.").
13. **A chart chunk that fails to load** shows the dialog's reload message followed by "The table below lists its points.", and the data table.
14. **Names in the image** are those on screen (current names); decision 8's names-as-solved rule is applied in the files.
15. **The export chunk** is 22.3 KB gzip (21.8 KB before the review fixes of items 25–35), against §1.2's estimate of 12–15 KB: the model, the tables, About, the writers and the dialog.

**Bundle and notices** (integration; gzip -9 of `p.html`'s scripts with their static imports, and its CSS, built from `a8b1d63` in a separate worktree and from the integrated tree, with the same commit id and `PUBLIC_API_URL`)

16. Initial `/p` download: 256,834 → 259,460 B (+2,626 B: JavaScript +2,538, CSS +88), inside the 3 KB budget; after the review fixes 259,521 B (+2,687 B: the longer load-failure message and the button's name on Compare cases, both in the page). About 1.4 KB is the shared chunk the lazy import splits off the page (§4.4 L measured 1.5 KB); the rest is the button and loader, the image button and its reasons, and the Links naming of item 24.
17. The export chunk is 21,769 B (22,280 B after the review fixes), with 1,069 B (download and file names) shared with the chart chunk and loaded with whichever comes first; the chart chunk grew from 54,992 to 57,608 B (the image renderer and the configuration).
18. `third-party-licenses.txt` is byte-identical: the same 11 packages. No runtime dependency was added.

**Proof**

19. **The reader** is `tests/unit/test_web_export_fixture.py` (§7.2/§8's name), with openpyxl pinned exactly (`==3.1.5`, where §8 had `>=`). Beyond §7.2 it solves the fixture project through `POST /api/v1/solve` once per case and checks every number cell against the response with its own column-to-field map, checks K·v_ref²/2g against every branch path's loss, decodes every shared string the ST_Xstring way, checks that every `<v>` is JavaScript's `String(n)` (its own implementation, tested on its own cases), and checks About's sentences and its project link, which decodes to the project exported. Seven seeded defects in edited copies of the workbook were each caught.
20. **What the committed workbook does not hold:** display units, Pumps, Pump curves, System curves, Goal seek, Trace, single-case captions, out-of-date and not-converged rows, flag rows, and names beginning with `+` or `@`. These are covered by the model's oracles over the other two fixture cases and the states tests (Vitest): the Flags sheet by an oracle of every column against the API flag over the fixture's flags and a case with a port, a pipe and a fitting number and the severities out of order, and the Trace sheet by an oracle of every row (order, count, part, number, name, value bit for bit, unit, source, text) over both single-case fixtures (§12 item 35; until the review the claim was false for these two sheets), and the integrator full-loaded every fixture case's workbook and zip, in both unit systems and both case choices, with openpyxl, `zipfile` and Python's `csv`: every sheet frozen at A4 with print titles `$1:$3`, no formula cell, every CSV a rectangular table with a BOM and CRLF, every `.txt` CRLF only.
21. **e2e** asserts that no request is sent from the click to the download on every download it makes, the out-of-date and not-converged flows included (integration).
22. **By hand (§7.4)** is not yet done: no Excel, Numbers, Google Sheets, iPhone or Android check has been recorded (TSD §10.3 holds the list).

**Outside this slice, done with it**

23. Decision 29's screen fix (`branchVelocityBasis` without `'own'`, the Branches note, the Darby test with the K the API sends) landed before the build (`81627fd`, `a8b1d63`).
24. **§9 item 1, for the Links table.** `linkTable` names each connection's "From → To" from the project its results belong to: `utils/results.ts` keeps a `WeakMap` from a `SolvedState` to a getter that the store records for every response it keeps (`recordResultsProject`), which gives null while the results are current and the project exactly as sent once they are out of date (`resultsProject`). So after a reversal made since the solve, the row names the ends its flow sign refers to, and an id re-used since never lends its new element's name to a connection's ends; a derived table follows its results going out of date without a label change. The call sites (`LinksView`, `TraceView` through `rowsForElement`) are unchanged. Still from the current project: the trace view's heading, Summary's fastest connection, the flags summary, the convergence status and Compare's rows (by design, §2.2 item 5); and the component tables' names (§9 item 5).

**Review fixes** (an adversarial review of the build, four lenses with a skeptic each; a fixer resolved every upheld finding, each with a test that failed before and passes after)

25. **System curves in the record (V1).** The System curves sheet wrote every ready curve of the case's slot, overlay ranges included (§2.6), while About, "Not in this file" and the dialog looked only at the default range: a curve drawn only with another case's chart was in the sheet while the file said "None" and "not computed". `context.ts` now owns `readyCurves` (moved from `tables.ts`), and the sheet, About and the dialog derive from it: a pump is included when any curve of it is ready; one included only over an overlay range gets About's "Included only over another case's chart range (Flow from and Flow to in System curves), where it was drawn for comparison; its default range is not in the file ({reason})". The overlay's range is not written as numbers in that sentence (the sheet holds it exactly).
26. **Changes not applied (V2).** Scenario changes wrote `null`, `Null` or `Default` for the values of an orphaned or not-applicable change; those cells are now empty (§2.6), and "Default" is kept for an applied resistance only.
27. **Captions (V3).** The Goal seek sheet's caption names its run time, its methods version (`result.methodVersion`) and its own staleness, never the exported case's solve; in All cases, About and Compare cases point to their case blocks and their Status and Solved at rows (§3.2). The API reader's caption oracle follows.
28. **The link in the out-of-date words (V5).** The dialog's warning and About's "Out of date" row mention the link only when the file holds one (§2.7, §5.3).
29. **The CSV reading note (F4)** names every character the guard covers: =, +, -, @, a tab or a carriage return (§2.7).
30. **`_xHHHH_` and the title (V4, F1, F2).** The escape is the lookahead form of §3.2 step 3, which escapes overlapping sequences; the API reader's expected escape is the same, and the fixture's reservoir is named `Low tank_x0041_x0042_\r(B)` so the reader's ST_Xstring decoding of every shared string checks two sequences that share an underscore (the old writer's workbook failed it). `dc:title` is plain XML text (`xmlText`): no `_x` escape and no cut.
31. **The file-name cap (F5)** is 147, not 150: §3.1's sum missed the separator after Downloads and took an 18-character longest file where `scenario-changes.csv` has 20, so the real worst case at 150 was 218, Excel's limit itself. A test builds the longest path from the cap, the folder and the longest file of §2.5 (and checks that no export writes a file outside that list).
32. **Download in the footer (W1, W2).** In the body, the focused Download sat about 760 px down a body showing about 560, so opening the dialog scrolled the warnings, Cases and Format out of view at 1280 × 800 and on phones; `focus({preventScroll: true})` would have left Download off screen. Download, Cancel, the busy reason and the status and alert lines moved to the Dialog's footer, as GoalSeekDialog keeps its run button, and the warnings became Download's description. A Cancel that goes while focused hands the focus to Download (it fell to `<body>`). The e2e out-of-date flow asserts the warning, Format and the focused Download in the viewport on desktop and phone.
33. **The load failure's words (W4).** STALE_CHUNK_MESSAGE names both causes, a redeploy or a dropped connection (Chromium keeps a failed module, so the click after a failed preload makes no request and a reload is the remedy either way), in words the chart's figure can also use (§5.2).
34. **The button's name on Compare cases (W5)** is "Export results of all cases", the dialog's default there (§5.2).
35. **Flags and Trace oracles (verification V1, V2).** `model.test.ts` checks every column of the Flags sheet and every row of the Trace sheet against the API; seeded defects that the suites let through before (severity, code, element kind and id, port id, pipe and fitting numbers without the +1, messages and details, the severity order; a trace unit, a part label, an intermediate value, a note's text) now each fail.
