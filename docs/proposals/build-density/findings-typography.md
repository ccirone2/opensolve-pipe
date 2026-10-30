> Discipline findings for [`../build-density.md`](../build-density.md), written 2026-10-30 against the running app before the build (`5693197`). Paths under `/tmp/claude-0/` are the reviewer's scratch evidence, not kept. The proposal's §4 says what was adopted.

# Typography and grid: Build, workspace header, scenario bar

Method: Playwright computed styles of every visible element in `header`, the scenario bar and `section[aria-label=Build]`, over all 19 forms of `all` plus 75 forms of solved `condenser-water`, at 1280x800 and 390x844 (deduplicated: 2019 / 2006 elements). Label widths: canvas + DOM wrap tests in the app's font stack (system stack; Linux renders Inter, so allow +-8 % for SF Pro / Segoe UI). Script: scratchpad `typo.cjs`, `lab.cjs`, `wrap.cjs`.

## 1. Inventory (desktop / mobile counts; text elements only for type)
| Type (size/line-height/weight) | n | where |
|---|---|---|
| 14/20/400 | 575 / 572 | body, results, buttons |
| 14/20/500 | 294 / 280 | `.label`, `.btn` |
| 14/20/600 | 34 | strong values |
| 16/24/400 | 100 | inputs (`text-base`), breadcrumb `›` |
| 16/**normal**/400 | 38 | **selects** (line-height not set) |
| 16/24/500 | 34 | breadcrumb links |
| 12/16/400-600 | 115 / 123 | `.hint` (95), section titles, dt, ids (mono) |
| 20/28/600 | 2 | component name input |
| **9/0** | 6 | `<sub>` in "rated" symbols |
| 12/**20**/600 | 1 | scenario count badge |
| 14/20/**700** | 1 | lone bold |

Families: system sans 1106, `ui-monospace` 95 (ids). Numerals: tabular only in results (141); **inputs are proportional** (0 of 115).
Spacing: margins 4 (175), 12 (60), 16 (105), 8 (1), **2** (5, icon `mt-0.5`), -1 (4, tab-border overlap). Gaps 8 (113/101), 12 (21), 4/12 (20), 4 (7/15), 16 (5), **6** (2, mobile actions `gap-1.5`). Padding x: 12 (134), 8 (134), 32 chevron (37), **2** (24, breadcrumb `px-0.5`), **6/4** (8 mobile action buttons `py-1.5`).
Control heights: **44 everywhere** (header 12, scenario 2, Build 280: button 164, input 78, select 37, summary 1), plus **56** (8 mobile action buttons, icon above label). Bars: header 53, scenario bar 53, breadcrumb 53, tabs 45 (each 4n + a 1 px border).
Off the 4 px grid: 33 elements desktop, 43 mobile: 2 px (53), 6 px (18), select `line-height: normal`, the 9 px sub, the 12/20 badge, and every bar height (+1 px border).

## 2. Tokens (fit `layout.css`, Tailwind 4 `@theme`)
```css
@theme {
  --spacing: 0.25rem;            /* Tailwind default; Build uses steps 1 2 3 4 6 8 only (no 0.5/1.5/2.5) */
  --spacing-ctl: 2.5rem;         /* h-ctl / min-h-ctl / w-ctl: 40 px, every button, input, select, tab, summary */
  --spacing-label: 10rem;        /* label column */
  --container-field: 21rem;      /* @field: label left of control */
  --container-pairs: 44rem;      /* @pairs: two label/value columns */
  /* type: Tailwind xs 12/16, sm 14/20, base 16/24, xl 20/28 only; weights 400/500/600 (drop 700, text-lg, 9 px) */
}
:root { --field-row-gap: 0.5rem; --field-col-gap: 0.75rem; --section-gap: 1rem; --pane-pad: 1rem; }
@media (max-width: 40rem) { :root { --pane-pad: 0.75rem; } }
.btn, .input { @apply min-h-ctl; }            /* was min-h-11 */
.btn-icon    { @apply w-ctl; }
.input       { @apply text-base leading-6 tabular-nums; } /* 16 px always: no iOS focus zoom; fixes select 'normal' */
```
- **One control height, 40 px.** WCAG 2.5.8 needs 24 (40 = 1.7x); with the 8 px row gap the pitch is 48 px (= Material 48 dp, near Apple 44 pt + gap) for thumbs; inputs are 130-560 px wide, so the short axis is the only miss axis. 36 px on fine pointers would save 4 px a row (8 %) at the cost of a second token: not worth it. Keep 44 only for the thumb-zone bottom Prev/Next bar if the owner wants (one exception, documented).
- **Input text 16 px on every pointer** (iOS Safari zooms below 16). Values are the content; at 1280 width is not the constraint (input column >= 184 px; "-12345.678" is 86 px + 24 padding at 16 px).
- **Tabular numerals** on `.input`, unit suffixes, result-strip `dd`, trace tables (already), any column of numbers. Bars: put the 1 px border inside a 52/44 box (`box-shadow: inset 0 -1px` or fixed `h-13`/`h-11` with border-box) so bars land on 4n. Replace `px-0.5`/`gap-1.5`/`py-1.5`/`mt-0.5` with 1/2 steps; `<sub>` at 0.75em with `line-height:0`.

## 3. Left labels vs top labels (measured)
Longest Build labels at 14/500 (Inter): "Allowable operating region, highest flow" 270 px, "...lowest flow" 264, "Rated coefficient of discharge (K)" 225, "Minimum margin NPSHa - NPSHr" 224, "Minimum continuous stable flow" 217, "Rated fluid density from a fluid" 205, "Set pressure (difference)" 167, "Outlet pressure setpoint" 162, "Inner diameter override" 157. Median label ~ 95 px.
Wrap test of 44 field labels: column 128 px -> 3 labels need 3 lines; **144 px -> 33 one line, 11 two lines, 0 three**; 160 px -> 36/8/0 (82 % one line); 176-192 -> 38/6/0.
Key: a 2-line label (40 px at 20 px leading) is exactly one 40 px control, so **any label <= 2 lines costs zero height**. 10rem (160) keeps 2 lines with ~8 % headroom for SF/Segoe.

Per-field vertical pitch (hint shown on focus only):
| layout | pitch | vs today |
|---|---|---|
| today: label 20 + 4 + ctl 44 + gap 12 (+ hint 20-52) | 80 (100-132) | - |
| top labels, 40 ctl | 20 + 4 + 40 + 12 = 76 | -4 |
| **left labels, 40 ctl** | 40 + 8 = **48** | **-32 / field (-40 %)** |
Saving vs top-aligned at the same control height: 28 px/field (37 %); 8 core fields at 390x844 = 224 px, a third of the 646 px Build pane.

Widths: 390 px -> content 366: label 160 + 12 + 194 (input 134 + unit <= 60: "kPa(g)" 44, "US gpm" 53, + 16 pad). 1280 px -> pane content 736: one pair column would give a 564 px input; use **two pair columns at container >= 44rem** (each 356 = 160 + 12 + 184), the same order as today's `sm:grid-cols-2`.
Grid: `grid-template-columns: minmax(9rem, 10rem) minmax(10.5rem, 1fr)`; label `align-self:center` in row 1 (1 or 2 lines both centre on the 40 px control, no 10 px offset); hint, error, warning, ChangeNote, "default" in row 2, column 2 (`grid-column: 2`), so notes never push the label off its control.
**Stack (label above) below a container width of 21rem (336 px)**: 144 + 12 + 170 (110 number + 60 unit) = 326. 320 px reflow -> content 296 stacks; 360 px Android -> 336 stays side by side (label shrinks to 156); 390 -> 366 side by side. Use a container query on the form (`@container`), not the viewport, because the Build pane is resizable.
Verdict: left-aligned labels in a fixed 10rem column suit these forms: users scan and edit existing values more than they fill blank forms, the labels are short noun phrases (82 % one line), and the 37 % height saving is what puts core fields above the fold at 390x844.
