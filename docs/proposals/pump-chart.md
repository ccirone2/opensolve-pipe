# Pump chart: design proposal

**Status: slices 1, 2 and 3 built, slice 4 decided and its first part built** (slices 1 and 2 2026-10-26, §9 and §10 record where the builds depart from this text; slice 3, 2026-10-27, as the design checks of `docs/proposals/design-checks.md`, CLAUDE.md D19; slice 4, 2026-10-28, designed in `docs/proposals/pump-groups.md`, the owner's answers there, its slice 4a built, CLAUDE.md D20). **Owner's decision (2026-10-26):** the best efficiency point is shown by default as a fact of the curve; the duty as a % of BEP flow and every operating-region band wait for the opt-in design checks (slice 3). Written against `main` at `bbafbff` (export, D17, merged) for item 12 of `docs/proposals/ui-ux-refinement.md` ("pump chart layers"), which this document replaces and widens. Everything here is a reversible default under D14 except where it is marked **owner** (a GOALS value, a model input or a design-practice check).

The pump chart is where a mechanical engineer checks a selection: whether the pump meets the duty, how far from its best efficiency it runs, what power the driver needs, how much NPSH margin there is across the range the system will see, and how all of this moves between cases and speeds. Today the chart answers the first question only. This proposal lays out the whole chart a design engineer expects, in slices that each ship on their own, so that the first slice leaves room for every later one.

Sources:
- A research brief (2026-10-26) on chart conventions and what the standards say in public, with links: the HI Data Tool pages on pump and system curves, HI's tables of contents for ANSI/HI 9.6.3-2024 and 9.6.1-2024 and its 2022 and 2025 posts, API 610 clauses as quoted by Datacor and Amarinth, ISO 9906 grades as reproduced by KSB and Wilfley, Grundfos and KSB on reading curves, the DOE/HI/Europump guide to variable-speed pumping, FluidFlow and Datacor Fathom documentation, WCAG 2.2 (1.4.1, 1.4.11) and the W3C complex-images tutorial. The paywalled standards themselves (HI 9.6.3, 9.6.1, API 610, ISO 9906) were **not** read; numbers quoted from them below are marked with their secondary source and are used only where §5 allows.
- Code at `bbafbff`: web `components/results/PumpChart.svelte`, `utils/pump-chart.ts`, `utils/pump-chart-config.ts`, `utils/export/chart-image.ts`; API `models/pumps.py`, `models/results.py` (`PumpResult`, `CurvePoint`), `models/api.py` (`SystemCurvePoint`), `services/solver/pumps.py` (`PumpCurveModel`), `services/solver/results.py` (pump results), `services/solver/system_curve.py`.
- GOALS §3, §4.1, §4.2, §4.6, §4.7; CLAUDE.md D9, D10, D11, D15, D17; PRD §4.2.

---

## 1. What an engineer reads from a pump chart

Ranked by value to a design engineer, each marked **fact** (physics or the user's own data, shown by default) or **practice** (a design-practice criterion, opt-in only, GOALS §4.6).

| # | Element | Kind | The app today |
|---|---------|------|---------------|
| 1 | H–Q curve at the running speed, system curve, operating point; solid over the data, dashed where extrapolated | fact | drawn |
| 2 | NPSHr curve against NPSHa, at the duty and along the system curve (NPSHa(Q)) | fact | NPSHr and NPSHa at the duty only, in the Pumps table |
| 3 | Efficiency curve, with η at the duty | fact | η at the duty only |
| 4 | Shaft power curve P = ρgQH/η, with P at the duty; the largest P over the data | fact | P at the duty only |
| 5 | Best efficiency point (the efficiency curve's interior maximum) and the duty as a % of BEP flow | fact (the point); practice (judging the duty by it) | — |
| 6 | Preferred and allowable operating regions (POR, AOR) | practice; AOR is manufacturer data | — |
| 7 | Minimum continuous stable flow, minimum thermal flow | practice; manufacturer data | — |
| 8 | Shutoff head, head rise to shutoff; a rising (unstable) stretch of the curve | fact (the values); practice (API 610's ≥ 10 % rise for parallel duty) | shutoff head in the trace |
| 9 | End of the curve data (not "runout" unless the maker gives one) | fact | the dashed extrapolation starts there |
| 10 | Speed family of a variable-speed pump: curves at minimum, running and maximum speed, iso-efficiency lines (affinity parabolas H ∝ Q²) | fact (follows from the affinity model) | the running-speed curve only |
| 11 | Other cases' operating points, pump curves and system curves | fact | drawn (D15) |
| 12 | Static and friction parts of the system curve | fact once defined for a network | — |
| 13 | Several pumps: each pump's own solved point on a combined view | fact | one pump per chart |
| 14 | Impeller trims; ISO 9906 tolerance at the guarantee point | needs inputs | — |

Two conventions are near-universal on manufacturers' sheets (Grundfos, KSB, API data sheets): **every quantity is plotted against one flow axis**, and head sits on top with efficiency, power and NPSHr in panels below it. Twin y-axes (DOE figures, some API sheets) save height but are hard to read and cannot be told apart without colour on a phone.

## 2. What the app has, and what it lacks

**Has (per pump, from the API):** the H–Q points and optional η–Q and NPSHr–Q points at rated speed (`PumpCurve`); the running speed and, for a speed-controlled pump, its control state, setpoint and `minSpeed`; at the duty: Q, H, η, hydraulic and shaft power, NPSHa, NPSHr, margin, suction absolute pressure; the H–Q curve sampled at the running speed (`PumpResult.curve`, 41 points over the data); the system curve on demand (`POST /api/v1/system-curve`, 41 flows, each with a head or a reason); the fluid (ρ, μ, p_v).

**Lacks, and needs from the API (slice 1):** the efficiency, NPSHr and power curves at the running speed. The web must not compute them: the solver interpolates with PCHIP and holds or extrapolates each curve its own way (η held at its end values, NPSHr extrapolated along its end tangent, never below 0), and a straight line between the user's points in the browser would differ from the values the solver used, with no trace. NPSHa along the system curve needs the suction EGL of each system-curve point, which only the server has.

**Lacks, and needs model inputs (later, owner):** rated rpm (for specific speed, which HI 9.6.3's POR depends on), impeller diameter and trims, motor rating, the manufacturer's AOR, minimum continuous stable flow and minimum thermal flow, the NPSHr basis (NPSH3 or the 2024 "NPSHR"), the curve's ISO 9906 grade, and a grouping of pumps that run together.

## 3. Principles

1. **Every plotted value comes from the API** (as today, `pump-chart.ts`): curves sampled by the server with the solver's own interpolants and affinity laws, so the chart, the tables, the trace and the solve agree to the last digit.
2. **One flow axis, stacked panels.** Head on top; efficiency, power and NPSH below, each with its own y-axis and unit, sharing the x-axis. No twin axes.
3. **Progressive disclosure.** The head panel is always there. The other panels appear only when the pump has the data for them (an efficiency curve; an NPSHr curve or an NPSHa), and the user can hide any of them; the choice is remembered in this browser, like the pane split (never in the link). Design-practice overlays never appear unless the design checks are switched on (PRD §5, GOALS §4.6).
4. **Data versus extrapolation by line style**, never colour alone (WCAG 1.4.1): solid over the user's data, dashed beyond it; a curve the solver holds (η) is not drawn beyond its data at all.
5. **The duty in every panel.** A vertical line at the operating flow through all panels, with the operating value marked in each. A pointer or keyboard cursor reads every panel at one flow.
6. **Physics flagged, practice opt-in.** NPSHa below NPSHr is drawn as a fact (the NPSH panel shows where the curves cross) and stays flagged by default. Bands (POR, AOR), margin ratios, motor margins and the 10 % shutoff rise are opt-in, each naming its criterion and edition.
7. **Say what a value is not.** "End of curve data", not "runout"; "largest shaft power over the curve data", not "non-overloading"; a BEP only where the efficiency maximum is inside the data.
8. **Phones equal** (GOALS §4.7): panels stack at full width with a shorter height each; the readout is a line under the chart, not a floating tooltip; the data table remains the full long description (W3C complex images).

## 4. Design

### 4.1 Layout

```
┌───────────────────────────────────────────────┐
│ Head (m)      pump curve, system curve, cases │  weight 3
│        ●  operating point                     │
├───────────────────────────────────────────────┤
│ Efficiency (%)   η curve, η at duty           │  weight 1
├───────────────────────────────────────────────┤
│ Shaft power (kW) P curve, P at duty           │  weight 1
├───────────────────────────────────────────────┤
│ NPSH (m)   NPSHr curve, NPSHa along the       │  weight 1.2
│            system curve, both at duty         │
├───────────────────────────────────────────────┤
│ Flow (L/s)  ─ one axis for all ─              │
└───────────────────────────────────────────────┘
 Panels: [Head] [Efficiency] [Power] [NPSH]    (chips; shown only when there is data)
 At 21.4 L/s: H 31.2 m · η 71.8 % · P 9.14 kW · NPSHr 2.9 m · NPSHa 7.6 m
```

One Chart.js chart with stacked y-scales (`stack`, `stackWeight`; Chart.js ≥ 3), so the panels share one x-scale, one canvas, one interaction model and one image (the PNG of D17 gets the panels for free). Height grows with the panels shown (head alone keeps today's 16–18 rem). Legend under the chart, as today; panel titles are the y-axis titles.

### 4.2 Panels

- **Head.** As today: pump curve at the running speed (dashed where extrapolated), the system curve and its gaps, the operating point or the zero-flow diamond, other cases (slate, markers, direct labels). Later: speed family (§6, slice 2).
- **Efficiency.** η(Q) = η₀(Q/s) at the running speed over the efficiency data (flows × s), in %; η at the duty. Where the duty lies outside the efficiency data, the duty marker is hollow and the panel says the solver held η at the curve's end value (the existing `PUMP_OUTSIDE_CURVE` flag).
- **Power.** Shaft power ρgQH/η over the flows where both the head and efficiency data reach (at the running speed), in display power units; P at the duty; a note with the largest shaft power over that range ("largest over the curve data"), never "non-overloading". Hydraulic power is in the table, not plotted (it adds a line, not a decision).
- **NPSH.** NPSHr(Q) = s²·NPSHr₀(Q/s) over the NPSHr data; NPSHa along the system curve (one value per system-curve point with a head, when the vapor pressure is known and the suction side has a fixed pressure level), drawn in the system curve's colour; NPSHa and NPSHr at the duty. Where NPSHa(Q) falls below NPSHr(Q) inside the drawn range, the flow at which they cross is marked and named ("NPSHa = NPSHr at 27.3 L/s"): a fact, read from the two sampled curves by linear interpolation between neighbouring samples, labelled approximate to the sample spacing. No margin band unless the design checks are on.

### 4.3 Reading the chart

A vertical cursor follows the pointer (desktop; a tap on a phone) and a **Read at flow** slider under the chart (a native range input: arrow keys, Home and End, screen-reader values). The readout line under the chart gives every line shown at that flow, read as drawn: linear between the API's samples, nothing outside a line's samples or across a gap. It starts at the duty, and Escape or **Back to the duty** returns there. The slider's value text carries the readout, so a screen reader hears it as the value changes; the line itself is not a live region.

### 4.4 Data table

The table under the chart grows the matching columns: flow, head, efficiency, shaft power, NPSHr (pump curve), and flow, system head, NPSHa (system curve), with the "Data / Extrapolated / Held" note per value. It stays the chart's long description.

### 4.5 Image (D17)

The PNG draws the same configuration, so it carries the panels shown on screen; its footer adds the panels' notes (held η, largest power, NPSH crossing).

## 5. What not to show without a source or an input

- No POR/AOR band, no "70–120 % of BEP", no NPSH margin ratio, no motor-sizing margin by default. With the design checks on (PRD §5, D19), each band names its criterion and source (API 610 as quoted; AOR is manufacturer data; HI 9.6.3's region, which needs rated rpm, is not a preset).
- No BEP, % of BEP or POR from an efficiency maximum at an end of the data: that is not a BEP.
- Never "no cavitation" from NPSHa ≥ NPSHr: NPSHr (NPSH3) already includes a 3 % head drop (HI 9.6.1).
- No "non-overloading" beyond the data.
- No ISO 9906 tolerance band unless the user enters the grade the curve was guaranteed to.
- Glycols and other viscous fluids: the chart says the curves are uncorrected for viscosity (HI viscosity correction is Later, D5), as the trace does.
- Efficiency at reduced speed is plain affinity (η₀(Q/s), D11): the note says so.

## 6. Slices

**Slice 1: the four panels (API + web).**
- API, additive outputs only (no solved value, flag, trace text or method changes; `METHOD_VERSION` stays 1.2.0):
  - `PumpResult.efficiencyCurve: [{flow, efficiency}] | null`: 41 samples of η₀(Q/s) over the efficiency data × s (`PumpCurveModel.efficiency`).
  - `PumpResult.npshrCurve: [{flow, npshr}] | null`: 41 samples of `PumpCurveModel.npsh_required` over the NPSHr data × s.
  - `PumpResult.powerCurve: [{flow, shaftPower}] | null`: 41 samples of ρgQ·H(Q)/η(Q) over the overlap of the head and efficiency data × s (null without an efficiency curve or an overlap).
  - `SystemCurvePoint.npshAvailable: float | null`: `npsh_available` of the point's suction EGL, with the solve's own formula, for a point with a head when the vapor pressure is known (null otherwise).
  - Proof: unit tests that each sample equals the model function at its flow, at full and reduced speed and for a controlled pump; that the duty values (η, NPSHr, shaft power, NPSHa) lie on the curves (the sample at the duty's flow, or between neighbours); that `npshAvailable` at the operating flow's system-curve point equals the solve's NPSHa (to the solver tolerance); the corpus comparison with the new fields ignored (every existing value identical).
- Web: the stacked panels, chips, cursor and readout, table columns and image; unit tests of the data shaping; e2e on desktop and phone with an axe scan.

**Slice 2: speed and curve facts (web, mostly).** For a speed-controlled pump: the curves at `minSpeed` and maximum `speed` (from the API: the same samples at those speeds), the region between them shaded lightly, and iso-efficiency parabolas through two or three efficiency levels when an efficiency curve exists (affinity: H ∝ Q², η constant; the note cites the assumption and HI 14.3's limits). Shutoff head and the end of the curve data marked on the head panel; a rising stretch of the H–Q curve (dH/dQ > 0) shaded and named as a fact. **Owner:** whether the BEP point (the efficiency curve's interior maximum, flow and efficiency, scaled by speed) is a fact shown by default or part of the opt-in design checks (GOALS §4.6 lists "BEP proximity" as practice; the point itself is a property of the curve).

**Slice 3: opt-in design checks (owner; PRD §5). Built as `docs/proposals/design-checks.md` (CLAUDE.md D19),** widened by the owner to a check framework (NPSH margin, operating region, pipe velocity); as built, the chart draws the limits behind a "Design checks" chip and the verdicts are in Results → Checks, not flags. As proposed: needs model inputs: the AOR and POR source (API 610 as quoted, HI 9.6.3 with rated rpm, or user values), minimum continuous stable and thermal flows, the NPSH margin criterion (HI 9.6.1 table by application, or user value), motor rating. Draws bands and lines with their criterion named, and adds design-check flags. Each input is cited data or user data, labelled as such (D8, D10).

**Slice 4: several pumps (owner). Designed in `docs/proposals/pump-groups.md`; slice 4a built (CLAUDE.md D20):** the owner chose curves between the station's outer ports (the group curve built, the group's own system curve next), no composite curve drawn, groups as page state, and no trim or ISO 9906 inputs. As proposed: a combined view for pumps the user groups (parallel or series): each pump's own solved point and curve, the group's combined curve as a reference only (Fathom: for dissimilar pumps the composite curve does not cross the system curve at each pump's flow), and the system curve of the group. Impeller trims and ISO 9906 bands follow their inputs.

## 7. Accessibility and phones

- Contrast ≥ 3:1 for every line and marker against white (WCAG 1.4.11): the existing palette (pump #2a78d6, system #eb6834, ink, slate) is reused; efficiency, power and NPSHr take the pump's colour (they are the pump's curves), NPSHa takes the system's (it is the system's), and line style tells data from extrapolation.
- The figure's accessible name lists each panel's content and the duty values; the data table is the long description.
- Chips are a group of toggle buttons (`aria-pressed`), 44 px tall; the cursor is reachable by keyboard (the chart's focusable figure) with the readout as a live region.
- At 390 px: panels full width, head 13 rem and others 7 rem each; the readout wraps to two lines; the legend stays under the chart.

## 8. Tests and proof (slice 1)

API: §6's unit tests; `test_openapi` refresh (generated types); the corpus comparison against `main` with `--ignore` for the four new fields (identical, no other ignores). Web: `pump-chart.test.ts` (panels from data, nulls, held and extrapolated parts, NPSH crossing), `pump-chart-config.test.ts` (stacked scales and weights by panels shown), `PumpChart.svelte.test.ts` (chips, readout by keyboard, accessible name), the `pump-chart` e2e flow on desktop and phone with axe, and the image test of D17 with panels.

## 9. Slice 1 as built

**API** (branch `pump-chart`): as §6, with the samples taken by `PumpCurveModel.sample_efficiency`, `sample_npsh_required` and `sample_shaft_power` (`services/solver/pumps.py`) from the same functions the duty values use, and `npshAvailable` added in `system_curve.py` from the point's suction EGL where its level is determined. Proof: `tests/unit/test_pump_chart_curves.py` (9 tests; expected values derived with SciPy's PCHIP, the affinity laws and Darcy–Weisbach/Colebrook, not with solver code); the API suite (4,558 passed before the new tests); the corpus comparison against `bbafbff`: 5,136 identical, 0 different, with only the three new `PumpResult` fields ignored (TSD §10.4), and the `/system-curve` points of every corpus pump (70,192 points of 6,152 curves) identical with only `npshAvailable` ignored (TSD §10.4).

**Web.** Where the build departs from §3–§4:
- **A panel needs a line.** The NPSH panel appears for NPSHr data or NPSHa along a computed system curve, not for the two duty values alone (a panel of two dots says less than the Pumps table).
- **The readout reads the drawn lines** (§4.3 as revised): linear between the API's samples rather than snapping to one curve's samples, since the curves have different flow grids (each over its own data). The data table keeps the exact samples.
- **Short axis titles** on the lower panels (η (%), P (kW), NPSH (m)): a full title does not fit the height of a small panel. The legend names each line in full and leaves out the panels' duty dots, which repeat "Operating point".
- **NPSHr dashed, NPSHa solid.** NPSHr is the pump's curve in the pump's colour, dashed so it differs from the efficiency and power lines by more than colour; NPSHa is the system's colour. The NPSHr duty marker is hollow, NPSHa's filled.
- **Efficiency from zero.** The efficiency axis starts at 0 %, as on manufacturers' sheets, which flattens the curve in a small panel; the readout and the table give the values.
- **Hidden panels** are stored under `opensolve-pipe:pump-chart-hidden-panels`; every panel with data is shown by default.

Proof: `utils/pump-chart-panels.test.ts` (9 tests), new cases in `PumpChart.svelte.test.ts` (chips, persistence, readout), the `pump-chart` e2e flow on desktop and phone against the real API, and a clean axe scan (WCAG 2.0/2.1 A and AA, best practice) of the Pumps view with the chart and its data table at both sizes.

## 10. Slice 2 as built

**API** (`services/solver/curve_facts.py`; additive `PumpResult` fields, `METHOD_VERSION` unchanged): `bestEfficiencyPoint` (η₀'s largest value strictly inside its points, at speed: (s Q₀*, η₀(Q₀*)) with the head s² H₀(Q₀*)), `shutoffHead` (s² H₀(0), with whether it is on the start tangent), `risingHeadRanges` (dH/dQ > 0 within the head points), and for a speed-controlled pump `speedCurves` (the head curve at `minSpeed` and the maximum speed) and `isoEfficiencyLines` (through the BEP and through every rated-speed flow at up to three multiples of 5 % below it, over 11 speeds). Extrema and sign changes come from the derivative's roots on each PCHIP piece; every value is the interpolant's own. The pump trace gains the BEP's equation and values, a note per rising range, and the iso-efficiency equation. Proof: `tests/unit/test_pump_curve_facts.py` (closed form, and a property check of 300 random curves against a dense scan), the corpus comparison and the trace check (TSD §10.4).

**Web.** As §6 with the owner's decision on the BEP, and these departures:
- **No shading between the limit speeds.** Chart.js fills between datasets on a shared x grid only; the limit curves have their own grids. The two thin limit curves (the maximum dashed) and the dotted iso-efficiency lines bound the region well enough.
- **The end of the curve data** is not marked again: the dashed extrapolation already starts there, and its note gives the data range.
- **The shutoff head is a dash at zero flow** with a note (`Shutoff head (–)`), on every chart: it is the dead-head pressure a pipe rating is checked against. Where the head points start above zero flow, the start tangent down to it is drawn dashed, exactly as the solver extrapolates (straight in Q at a fixed speed).
- **Where the head rises** the pump curve is underlaid in amber (amber-700, 5.0:1 on white) and named in a note as a fact: a system curve can cross the pump curve more than once there. It is not a flag.
- **Labels avoid each other.** Short labels ("BEP", "BEP line", "65 %") are drawn in order and one that would overlap another is left out; the legend has one entry for all iso lines and the notes list the levels.
- **One chip group, "Show"**: the panels and, for a speed-controlled pump, **Speed range**, remembered in this browser with them.

Proof: `utils/pump-chart-facts.test.ts`, the updated chart, image and component tests, the `pump-chart-facts` e2e flow on desktop and phone, and a clean axe scan of the chart with a drooping curve and a speed range.

