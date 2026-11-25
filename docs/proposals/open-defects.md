# Open defects (2026-11-25)

**Status: decided (the owner, 2026-11-25); being built, web only, on `web/open-defects` (built as `claude/kind-wozniak-oui7h9`).** No API, model or solver change; `METHOD_VERSION` unchanged (1.6.1): every change is in what the web app shows, sorts or focuses, and no stored or solved value changes. Everything here is a reversible web default under D14 except the owner's two answers (§1). Follows [`../ui-guide.md`](../ui-guide.md).

## 1. Scope

**The request (2026-11-25).** Asked "what to work on now?", the designers checked every defect the docs recorded as open or "found, not looked into" against main `6891b48`: five agents, each reproducing its claims with a scratch probe (Playwright on the built app against the API, Vitest, or a Python script), and a sixth sizing the remaining usability candidates against GOALS §5. They recommended one web-only branch of the fixes that need no product choice, then "what changed since the last solve" (`usability-entry.md` U5). **The owner (2026-11-25):** "Yes. Use absolute value of velocity. Open the text keyboard."

| Question put to the owner | Answer |
|---|---|
| Should the Links table's Velocity column, and so the Summary's "Links, highest first", rank by speed \|v\| or by the signed value shown? | **Speed, \|v\|** |
| On phones, should number fields open the text keyboard so a unit can be typed, or keep the decimal keypad (units pasted)? | **The text keyboard** |
| A new scenario that reuses a deleted one's id: start ticked, or reserve ids? (F2) | Not answered: left open (§6) |
| Add cases and the methods during a base solve: kept on screen busy, or restored afterwards? (F3) | Not answered: left open (§6) |

**Already decided, not re-opened.** SI inside, gauge at the edges (D4): the API's velocity is signed like the flow (`models/results.py`), and the cell keeps showing it so; only the rank changes. Nothing is released (D14): no compatibility shim. The physically invalid mark is the octagon (`FlagIcon severity="invalid"`, `ui-guide.md` "No value is not a safe value"; `pumps-results-layout.md` S5).

**The designers' own reading.** "Use absolute value of velocity" answers the question asked, the rank: every results table's Velocity column ranks by \|v\| (a connection of several pipes by its largest \|v\|), the cell still shows the signed value, as the API, the trace and the export give it. Showing \|v\| in the cells too would be a further change, the owner's to ask for.

## 2. The fixes

Each is reproduced on `6891b48` (the triage's evidence is in the as-built record, §8) and ships with a test that fails before it.

| # | What a user sees on `6891b48` | Cause | Fix |
|---|---|---|---|
| P1 | Shown on a scenario whose only other case on the pump chart is the base case (a project with one scenario, or every other scenario unticked), "Also show the other cases' system curves" never draws the base case's system curve or names it in the legend, and nothing says so. Recorded as seen with the transfer example's NPSHr 0 scenario (`pumps-nits.md` §11.7, §11.10); NPSHr 0 has nothing to do with it. | The overlay's request effect joins the case keys into one string; the base case's key is `''`, so `['']` joins to `''` and is read as no cases (`PumpsView.svelte`, `overlayList`) | Tell an empty list from `['']` |
| S1 | The Summary's "Lowest pressure", "Highest pressure" and "Highest velocity" can name one element while the table their link sorts puts another first: two elements equal to 4 figures, and (new) a connection whose flow runs against its drawn direction, which the Summary names fastest and "Links, highest first" puts last | The Summary ranks raw SI values (\|v\| for velocity); the tables rank the signed, rounded text in project order (`results.ts`) | Every Velocity column ranks by \|v\| (the owner's answer); the tables break a tie of the text by the raw value; and each Summary extreme is, by construction, the first row of the table its link sorts, the pattern `pumps-nits.md` L2 set for the NPSH margin ratio |
| S2 | Compare cases marks a physically invalid value with a red triangle; the Pumps tab marks it with the octagon | `CompareView.svelte`'s two marks predate S5's octagon | The octagon, with the same words for screen readers |
| F1 | "Cancel the other cases' system curves", pressed with the keyboard, drops the focus to the page; so does the curves finishing while Cancel holds it (`pumps-results-layout.md` §15 item 229) | The button goes when the progress ends and nothing takes the focus | The focus goes to the switch "Also show the other cases' system curves", still ticked (the figure where the switch is not drawn), the handover pattern of S1 |
| F4 | The pump's allowable operating region: the first value typed in either end, then Enter, drops the focus to the page (`usability-entry.md` §9) | `{#key region?.flowMax}` changes from `undefined` to `null` on the field's own first entry, so the field is drawn again | Key on `?? null` |
| W1.1 | At 320×640 a 40-character name without spaces makes the Summary tab scroll 20 px sideways | The Summary's link buttons have no `min-w-0` or break rule | Let them wrap anywhere |
| W1.2 | The same name makes the Pumps tab scroll 7 px sideways with Pumps together closed | The closed toggle's member list has no `min-w-0` or break rule | Let it wrap anywhere |
| W2 | (A test gap, `pumps-results-layout.md` §15 item 187.) No test makes the browser's storage refuse a remembered choice | — | Tests: Fields and the pump chart's panels work with every storage call throwing |
| W4 | On a phone a field whose unit takes no negative value opens the decimal keypad, which has no letters, so "100 ft" cannot be typed (`usability-entry.md` §9) | `inputmode={allowsNegative ? 'text' : 'decimal'}` | The text keyboard everywhere (the owner's answer) |

## 3. Verification plan

Vitest for every fix that jsdom can show (P1, S1, S2, F1, F4, W2, W4), each test run first on the unfixed code to see it fail; Playwright at 320×640 for the two layout fixes (W1.1, W1.2), and at 1280×800 for P1 against the API, each run first on a build without the fixes. Then every gate (`workflow.md` §4) and an adversarial review of the diff, each finding reproduced before it is fixed.

## 4. Files

`apps/web/src/lib/components/results/{PumpsView,PumpChart,SummaryView,CompareView,PumpGroupChart}.svelte`, `utils/results.ts` (and its callers of the extremes), `components/panel/forms/PumpCurveEditor.svelte`, `components/ui/NumberField.svelte`, their tests, `tests/*.e2e.ts`.

## 5. Re-checked and left open

The three API items open since 1.6.1 (TSD §12 item 19; roadmap §2) still reproduce, and each is reached only by an input no physical network has: `ORIFICE_OUT_OF_RANGE` rule (d) refuses a plate only at an entered C near 10⁻¹⁵³; a reservoir head p/(ρg) overflows only at a density near the smallest double; the singular step needs a loss coefficient of about 1.2·10¹⁹. Each fix would cost a method bump or a solver change. Left on the roadmap with these measurements.

## 6. Later

- F2: a new scenario that takes a deleted one's id comes in unticked under both charts' lists (`pumps-results-layout.md` §15 item 229). Prune the untick when the id is created, or reserve ids: the owner's choice.
- F3: a base solve with the focus in Add cases sends it to the page, and the stop order and the methods come back closed (§15 item 133): the owner's choice between keeping them on screen busy and restoring them after.
- F4's other half: the paired fields' "Converted from" note is still lost when the other end changes (`usability-entry.md` §9).
- The home page's How it works shots retaken (they show the navigator's old text; `landing-page.md` §7), when the owner says.
- "What changed since the last solve" (`usability-entry.md` U5), the recommended next slice.

## 7. Review record

To be written with the build.

## 8. As built

To be written with the build.
