> Second red-team pass for [`../build-density.md`](../build-density.md), on the built app (2026-10-30). Paths under `/tmp/claude-0/` are the reviewer's scratch evidence, not kept. Items 1, 2 (the select) and the 320 px action row were fixed afterwards (proposal §11, departures 8–10).

# Red team 2: the built Build-density redesign (app on 5182)

Shots: `/tmp/claude-0/scratch/findings/shots/redteam2-*.png`. Scripts: `/tmp/claude-0/-home-user-opensolve-pipe/237c8a8c-ec22-50c7-88e9-bdb1e9d0f236/scratchpad/r2{p1,b,d,e,f}.cjs`.

## 1. Field engineer, 390x844, touch (pump-transfer)
**10 taps, 0 scrolls** (first pass: 10 taps, 2 scrolls). The script printed "2 scrolls", but both were the fixed Solve at y 52, so no scroll actually happened.
Next: pump (y 800) → Piping (298) → Size (733, no scroll, `redteam2-p1-size.png`) + option → Solve (52) → Build tab (101) → Next: valve (800) → Status (466; the panel opens at its top, D19 holds, `redteam2-p1-valve.png`) + option → Solve (52).
- Still standing: 3 of the 10 taps are at the top of the screen (Solve, Build, Solve) (§10.1). A two-value status still takes 2 taps (§10.2). Size was only above the fold because the pump had not been solved yet (§10.3, not re-tested solved).
- **New, at 320 px** (`redteam2-f-V1-320.png`): the labels in the action row overflow their buttons ("Add afterAdd beforAdd branch"). The name field and the breadcrumb are clipped. There is no page scroll, so the reflow test passes while the text is unreadable.

## 2. Correctness auditor (condenser-water, S1)
What holds, with no focus anywhere:
- Base-case BP: the 2 "Winter: tower bypassed sets its own value." notes are shown.
- S1 BP: "Changed · Base: Closed (isolated) · Reset" and "Changed · Base: Default · Reset" are shown, and the Reset buttons have full names.
- More opens itself on a scenario change. Setting B1 surface pressure in S1 gives the summary "Surface pressure, ports (7) 1 set, 1 changed in this case", and More is open again on revisit. It also opens on a base-case note ("1 set by a scenario").
- "Surface pressure (default)" is named in the summary, and the note reads "Base: 0 kPa(g)".
- Help is hidden until focus (`c138-help`), then visible, and it is always in `aria-describedby`.

What fails:
- **The scenario banner is not one line on a phone (D15).** At 390 px it is 4 lines plus a button, about 160 px (y 388–548, `redteam2-a-BP-winter-solved-390.png`). With the Case bar and the result strip above it, BP's second scenario change (Resistance: Changed y 879, Reset y 869) sits under the Previous/Next bar. You have to scroll to see it.
- **The D10 default basis is cut off or dropped.** At 390 px the select reads "Default: Crane TP-410 K, full bore and f" (`redteam2-p1-valve.png`). The scenario note and the Reset name say only "Base: Default" / "…base value, Default", so the auditor never sees the Crane basis in the case view.
- Low: the strip shows B1's outflow as "−8.882×10⁻¹³ L/s" (`redteam2-a-B1-winter-solved-390.png`). That is convergence noise, which D13 treats as 0, shown as if it were a value.
- Low: "Names are the same in every case." starts at x = 4, outside the 16 px gutter.
- Not verified: a gauge node pressure in a result strip. The strips I saw showed only differences (kPa) and heads.

## 3. Next feature author (a plain optional number on Pump, e.g. `minimumFlow`)
- **It holds when the field is not changeable by a scenario or goal seek:** the Pydantic model, `pnpm gen:types` (2 generated files) and one registry entry, so **1 hand-edited web file**. The guard and the gauge test cover it.
- **The new input never appears in the export.** The pumps table in `export/tables.ts` (l.599–615) lists its columns by hand, and no guard notices the missing one.
- **If the field is on `x-override-fields` or the goal-seek allow-list, 3 more files and 5 switches need it, with no guard:**
  - `scenarios.ts` `fieldLabelFor` (l.1164) falls back to `humanize`.
  - The value text in `scenarios.ts` (l.1452) falls back to **dimensionless**, so a flow shows with no unit.
  - The override unit in `export/tables.ts` (l.1289) also falls back to dimensionless.
  - `goal-seek.ts` has its own switches for labels (≈l.655) and bounds/units (≈l.1357).
- That makes **4 files**, and the failure is silent: §10.5 stands. The registry already disagrees with itself: `Pump.speed`'s label function (field-registry.ts l.185–189) is a copy of `fieldLabelFor`'s `speed` case (scenarios.ts l.1168).
