# Open defects, round two (2026-11-26)

**Status: decided (the owner, 2026-11-26, §1), being built on `claude/kind-wozniak-oui7h9`. The web-only part (§2, F2, F3, C1 and X) also goes to `web/open-defects`; the API part (§3) stays on the session's branch.** `METHOD_VERSION` 1.6.1 → 1.6.2 (§4): the API part changes refusals, messages and flags of solves that cannot converge, and one duty check's verdict, and it adds the system curve's limit points. No converged value changes. Review record §8, as built §9. Follows [`open-defects.md`](open-defects.md), whose §5 and §6 left these items open, and [`../ui-guide.md`](../ui-guide.md).

## 1. Scope

**The request (2026-11-26).** The designers recommended a fix for each of F2 and F3 ([`open-defects.md`](open-defects.md) §6). F2: drop a remembered untick when a new scenario takes a deleted one's id, while Undo of the delete still restores it. F3: keep Add cases and the methods withdrawn during a base solve, then restore their open sections and the focus. **The owner:** "I agree with both proceed to make the fixes for f2 and f3. Also make the three API edge case fixes. Finally, resolve this issue in the attached photo where the system and pump curve do not cross each other. Also, limit the plot to never show negative flow in the x-axis."

**The photo** shows the condenser example's Pumps together group chart at phone width, Base case:
- the group curve passes about (5,700 L/s, 31 m);
- the orange group system curve runs from about −4 m at zero flow to about 9 m at about 5,580 L/s, and stops there;
- the flow axis runs from −5,000 to 15,000 L/s.

**Already decided, not re-opened.**
- A curve is never shown with another solve's results (D10).
- The Group point is called the two curves' crossing only when both duty checks agree (D21). This round changes what one of those checks decides (C2), not the rule.
- Nothing is released (D14): no compatibility shim, and `schemaVersion` stays 1.
- Expected values come from a library, a closed form or EPANET, never from solver code (D8, D6).
- A solver change is accepted by the suite, the corpus comparison and the three fuzz profiles (D13).

**The designers' calls.** The session continued without further questions to the owner. Each call below is a reversible default under D14 unless it changes a solved value, and each is put to the owner in the report.
1. **The crossing in the photo is real, and the API now says so (C2).** At the FCVs' limit the group system curve is vertical: the API states that any rise at or above `openHead` holds there. The duty's rise lies in that range. So the system duty check agrees, and D21's unchanged rule labels the Group point the crossing. The alternative was to draw the vertical and keep "not known". That leaves the chart showing two curves crossing while its words deny it, so the request would not be met.
2. **The single-pump chart gets the same vertical (C3).** In the example's own Winter case, P1's chart shows the photo's defect: its operating point sits right of where its system curve stops. The fix is an API change. `/system-curve` adds points at the flows where its range beyond the limit or below the floor begins. The grid could not land a sample there, since the web must not copy the API's default range.
3. **The singular step (A2b) is named, not solved.** The step itself is the follow-up (§7).
4. **F3's sections come back with the shown case's curves.** They wait for the group curve and, when wanted, the group system curve. They do not wait for the other cases' duties. The block, the methods and the focus return in one flush.

## 2. Web only (both branches)

| # | What a user sees on `593378d` | Cause | Fix |
|---|---|---|---|
| F2 | Delete a scenario unticked under "Cases on the chart" or "Cases on this chart". The next scenario added takes its id and comes in unticked under both lists, so it is missing from both charts. | The three untick lists in `Workspace` are page state keyed by scenario id. They outlive the scenario so that Undo of a delete restores the untick, and `newScenarioId` reuses the lowest free `S<n>`. | In `#step`, a step that creates an id drops that id from the three lists. What it dropped is remembered under the created `Scenario` object, which survives `#recordMethodVersion`'s copy of the project. Undo and Redo swap it back, so Undo of the delete still restores the untick. |
| F3 | A base solve, or Ctrl+Enter, with the focus in Add cases sends the focus to the page. The stop order and both "How … is computed" sections come back closed, and the plan comes back as the fold rule draws it. Other focusable controls on the card that a base solve unmounts lose the focus the same way: the slider, "Lost on its way", the other cases' switch and Running combinations' controls. | Add cases is mounted under `{#if lineups && stationShown}` and the methods under `{#if shown}` and `{#if systemShown}`. Their open state is local, and nothing takes the focus when they unmount. | The open state lives in a `CardSections` object, one per opening of the card. While withdrawn, the focus goes to the group figure, or to the toggle when the figure is gone. When the shown case's curves have answered, the sections and the focus come back in one flush: to the same control by `data-focus-key`, at the same offset in the pane, but only if the user has not stepped meanwhile. A step is a pointerdown, wheel, touchstart or keydown (the ui-guide's rule). A window blur is no step. |
| C1 | The group system curve stops short of the Group point, which sits at the FCVs' limit. The same holds on a pump chart whose system curve has a point at its limit. | A `valve_at_switch` point has head null and states its range of heads in `openHead` and `openHeadBound`. The charts draw head null as a gap. | `system-curve-line.ts`. Such a point puts `y = openHead` in the line and adds a ray from `openHead` to the edge of its own y-axis: the top for `'lower'`, the foot for `'upper'`. Both charts draw it, on screen and in the image, and on other cases' dotted curves. Every other point without a head stays a gap. The words follow: the notes, the accessible name, the tooltip ("rise at or above 24.63 m, undetermined", never a bare head), the data table's cell (`≥ 24.63`) and a ring on the vertical part (§3 C2's rule). Every other reason stays a gap. |
| X | In a project like the photo's, the flow axis starts at −5,000 L/s. A pump chart can do the same. | The group curve's point at the shutoff rise is a sum of member flows near zero, so its sign is round-off: −6.08·10⁻¹⁵ m³/s in the photo-like project, +1.20·10⁻¹⁴ as shipped. Chart.js 4.5.1's `ticks` bounds round the least flow down to a tick, so one value below zero starts the axis one step below it. | Both charts' x scales get an `afterDataLimits` that raises `min` to 0. The configuration's `min` stays unset, so Chart.js keeps its clip room for a mark at zero flow. D24's `xMin` and its item-96 rule are removed. A drawn datum below −10⁻⁶ m³/s is not drawn and is named in the notes with its values. |

**The photo's 15 m.** The photo's system curve is 14.4 m below the shipped example's. That is reproduced by raising the basin's level from 0.6 m to 15.0 m, with an unchanged duty, since the FCVs fix the flow. The shipped example's elevations are the same in every commit that touched it. What the owner's project held, and the deployed API's commit, were not available. C1 and X fix the photo's two defects in either case.

## 3. API (`claude/kind-wozniak-oui7h9` only)

**C2: the system duty check on the vertical part.**
- In `pump_groups._system_duty_check`, a duty point that is `valve_at_switch` with a finite `openHead` and a bound agrees when the duty's rise lies on that bound's side of `openHead`, within D6's allowance.
- Its `head` stays null.
- Its message says the rise is undetermined at this flow, quotes the range and the solve's rise, and says the curve passes through the duty on its vertical part. A rise on the wrong side disagrees, and the message says so.
- `tests/differential/pump_group_check.py` recomputes `agrees` by the same rule.
- The web words relay it (`systemDutyCheckState`).

**C3: limit points on `/system-curve`.**
- `SystemCurveResponse.limitPoints` is a list of `SystemCurvePoint`. It holds the points solved at `flow_limit`'s limit and at its floor, where either is finite, lies inside the range and is at no grid flow.
- Each is solved after the grid, from the network's initial state, so every grid point stays bit-identical.
- The web merges them into the line in flow order: on the pump chart, its other cases' curves, the data table, the image and the workbook's System curves sheet.
- The group system curve is unchanged. Its duty point already gives its vertical, and its own limit, where the duty is not at it, is §7.

**A1: `ORIFICE_OUT_OF_RANGE` rule (d)'s coefficient test at the least C the law takes.**
- The test is two-stage. Main's test runs first and passes every plate main passes.
- Where main refuses, the test is retaken at the least C_L the plate's law takes at any flow:
  - an entered C used as entered: C_e;
  - a moved C: C_e·min r, the least ratio of the two tap sets' ISO 5167-2 coefficients over [Re_lo, ∞). That minimum is found at either end or at a root of dr/dx, x = Re^(−1/10). Eq. (4) becomes a sparse polynomial in x, and its roots are found by a Rolle chain with bisection;
  - ISO's C: C(∞) at D and D/2 tappings, with the written argument and its constants rounded down.
- New refusals are a subset of main's by construction, and goal seek's bound builds stay monotone in C_e.
- The test still refuses a plate whose flows never reach that C (decision 17: finite at every flow, whatever the fluid). The records say so.
- Measured: the changed band runs from about 4·10⁻⁸ to 75 % of C_e, widest at β 0.97, on pipes from 1 mm to 1 m. The edges in C_e run from about 1.5·10⁻¹⁵⁵ to 8.3·10⁻¹⁴⁹.

**A2a: a boundary head that is not a finite number.**
- `builder.boundary_head` computes a reservoir's or a reference node's fixed head by today's expressions, bit for bit.
- `_unrepresentable_boundaries` refuses a head that is not finite as the 422 topology issue `BOUNDARY_HEAD_OUT_OF_RANGE`, naming the component, its pressure and the density. This reaches the solve, system curves, scenarios, pump-group curves and goal-seek trials.
- Goal seek builds at the bounds of a Reservoir's `surfacePressure` or an IdealReferenceNode's `pressure`, keyed by component type, and refuses an overflowing bound as a 400 located by index, with no value quoted.
- An iteration that diverges where no law gave a value that is not a finite number now names each link whose energy balance is not one. That goes in its own list, `nonFiniteBalanceAt`, never `nonFiniteLawAt`. Its prefix is "(non-finite energy balance)", and it names the EGLs at the start and the end and the fixed-head component there. With this, DIVERGED never stands alone.
- The web gets `issue-text.ts`'s words, `siText` keeping a quantity as quoted when it is not finite in display units, and ConvergenceStatus's list.
- PRV and PSV setpoint heads are not refused: they converge (a regression test pins it). A relief valve is already refused wherever its set head overflows. A check valve's cracking head stays named, not refused (§7).

**A2b: the singular step named.**
- When `splu` finds the step singular, `lost_weights` re-sums each free end's diagonal without each weight. It names the links whose weight 1/(dh/dQ) is lost in that sum and which alone join a part of free nodes to every fixed head.
- The message quotes the element, its slope, the flow and its loss coefficient, and says which iterate it quotes.
- The NOT_CONVERGED details are `singularStepAt`, `singularStepFlow`, `singularStepSlope` and `singularStepCoefficient`.
- Where no lost weight is found, the plain message stays. The 9,000 fuzz seeds have 27 such inner solves, none of them final.
- The step itself is unchanged, so the case still does not converge (§7).

## 4. Method version 1.6.2

One `METHOD_CHANGELOG` entry with an item each for C2, C3, A1, A2a and A2b. It states what is unchanged and the proof: flows, heads, pressures, statuses and traces of every solve that converges, and every grid point of every system curve.

## 5. Verification plan

- Each fix is test-first, each new test run on the unfixed code to see it fail. A test of behaviour that already holds says so.
- **Independent reference cases** by writers who do not read `services/`:
  - A1 (RA–RD): the accepted and refused halves at the least-ratio edge; corner taps least at infinite Re; the interior-minimum window; a control. Each is computed in mpmath from ISO 5167-2 eq. (4) as D20 states it.
  - A2a: the finite edge, every EGL = DBL_MAX, solving to zero flow; the infinite side as an HTTP test.
  - C2 and C3: a pump behind an FCV whose limit point's `openHead` is a closed form, and a station whose duty lies on its vertical part.
- **The corpus comparison** against `593378d`: with methodVersion and its trace path ignored, and `--ignore-empty` for `limitPoints`. Every project with a non-empty `limitPoints` is listed and explained.
- **The three fuzz profiles**, before and after.
- **The corpus checks** the 1.6.1 merge ran: scenario_check, pump_group_check, library_check, equipment_check, orifice_check, relief_check, design_checks_check, missing_result_check and goal_seek_check --sample 400.
- **Web:** Vitest, component tests, and Playwright on both projects, including the new F3 and chart tests; axe on the card.
- **Then** an adversarial review of the diff, each finding reproduced before it is fixed, and every gate (`workflow.md` §4).

## 6. Files

- **Web:**
  - `state/workspace.svelte.ts`;
  - `components/results/{card-sections.svelte.ts,PumpGroupChart,PumpGroupFigure,PumpLineupsBlock,PumpChart,ConvergenceStatus}.svelte`;
  - `utils/{system-curve-line,pump-chart-config,pump-chart,pump-group-chart,pump-group-one-off,pump-group-others,issue-text,results,flag-text}.ts`;
  - the export's System curves sheet;
  - their tests, and `tests/pumps-layout.e2e.ts`.
- **API:**
  - `services/solver/{orifice,builder,gga,system_curve,version}.py`;
  - `services/{pump_groups,goal_seek,results}.py`;
  - `models/api.py` and the generated types;
  - `tests/differential/pump_group_check.py`;
  - their unit tests, and the reference cases.

## 7. Later

- **A2b's step.** On the failure branch only (`splu` singular and a cut-off part found), take the bridge's dq from the far part's continuity and pin the far part's head by the bridge's own energy equation. No solve that converges today would take it. The 57 fuzz inner cases would need D13's check.
- **The group system curve's own limit** where the duty is not at it: its points there stay a gap.
- **A check valve's cracking head** that overflows (`crackingPressure/(ρg)`). It is named today when it diverges. Whether a closed-off one solves was not measured.
- **`differentialPressure` null** for a plate with taps at a reported zero flow (inf·0 in `pressure_term`). This predates this round, which widens it to the accepted band.
- **The photo's project.** Its link, or the deployed API's `/api/v1/about` commit, would settle the 15 m.

## 8. Review record

**The design pass** (2026-11-26, `593378d`): four designers, each prototyping in its own worktree and measuring in Chromium, the API's TestClient or mpmath, each followed by a critic who reproduced or refuted its claims. All four verdicts were "sound with changes", and every required change is taken above:
- **Charts:**
  - a tooltip stated `openHead` as the head;
  - the duty words claimed the crossing against the API's verdict, now settled by C2;
  - the example's Winter case kept the defect on P1's chart, now C3;
  - a ring on the vertical part got contradicting words;
  - a clip test could not fail on the group chart.
- **F2 and F3:**
  - the Undo swap keyed by the project object broke under `#recordMethodVersion` (measured), so it is now keyed by `Scenario` objects;
  - the focus returned after the block had moved 1,252 px;
  - a click or scroll during the wait ended in a jump;
  - a window blur ended the wait;
  - "where it was" was really centred;
  - other controls on the card dropped the focus too.
- **A1:** the band's size was misstated: 75 % at β 0.97, and on 1 mm to 1 m pipes. A test said to fail on main passes there. The ISO constants were rounded the wrong way. SDD §4.16 and the fuzz profiles were missing.
- **A2:**
  - the balance was listed as a law;
  - its prefix contradicted its finite head loss;
  - the lost-weight test was not exact at a binade;
  - expected values were taken from bisecting the solver;
  - the D13 proofs were missing;
  - "pressure" was keyed by field name alone;
  - the message quoted the starting flow without saying so.

## 9. As built

To be written with the build.
