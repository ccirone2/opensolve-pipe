# Loose ends: an inventory (2026-11-28)

**Status:** decided (owner, 2026-11-28): the owner's answers are in §9; A1 (§2) is being built, then §3, §4 and §7's record corrections.

The owner (2026-11-28): "Let's focus on loose ends before we start another major feature. Let's take a structured approach to the loose ends you described at the end of your turn. I didn't understand them because they were overly condensed."

## 1. How this was made, and the plan

Six investigators each took one group: the system curve's limits, inputs at the schema's bounds, the orifice plate's leftovers, the web app's leftovers, the questions and checks waiting on the owner, and a sweep of every record (roadmap, history, proposals, TSD §12, library facts, the code) for anything else. Each read its records and **ran each item on `main` at `da43e96` (`METHOD_VERSION` 1.6.2)**, with a scratch script against the API or a component test, without changing the repository. The numbers below are from those runs; the scripts lived in the session's scratch space and were not kept, and each item's *run* names its script and its output. The key reproductions (SC-3, CS-1, CS-2, CS-3 and the wye of CS-4) were run a second time by the session itself and gave the same output.

41 loose ends, none of them a wrong value in an ordinary project except SC-3, which is the same kind of picture as the owner's photo of 2026-11-26. The plan, in order:

1. **§2, the charts that disagree with the solve** (SC-3, SC-4): one tier-3 slice, about two days with its proofs.
2. **§3, the messages that point the wrong way** (CS-1, CS-3, and CS-2's words): one tier-3 slice, about a day; CS-2's behaviour is the owner's question.
3. **§4, the small web fixes** (WEB-1 with WEB-1b, CS-9, CS-14, WEB-2): one tier-2 slice, a few hours.
4. **§7's record corrections**: one tier-1 docs change, under an hour, which can ride with any of the above.
5. **§5 and §6** wait on the owner's answers and checks; each item says exactly what to do.

Each item gives: what happens, a concrete example, whether it was reproduced, who would hit it and how often, the consequence, the options with their cost and tier (`workflow.md` §4), the recommendation and the records it comes from.

| § | Group | Items |
|---|---|---|
| 2 | Fix first: the charts disagree with the solve | SC-3, SC-4 |
| 3 | Fix next: messages that point the wrong way | CS-1, CS-3, CS-2 |
| 4 | Small web fixes | WEB-1, WEB-1b, CS-9, CS-14, WEB-2 |
| 5 | Decisions for the owner | OW-1, CS-5, OW-3, OW-4, OW-5, CS-6, CS-15, CS-4 |
| 6 | Checks only the owner can do | OW-2, OW-6, OW-7, OW-8, OW-9, CS-11, CS-13 |
| 7 | Leave as they are, with the records corrected | SC-1, SC-2, SB-1, SB-2, SB-3, SB-4, SB-5, OP-1, OP-2, OP-3, OP-4, WEB-3, CS-7, CS-8, CS-10, CS-12 |

## 2. Fix first: the charts disagree with the solve

The one kind of loose end a real project reaches and that shows a wrong picture: the pump chart's or group chart's system curve stops short of an operating point the solve got right. One slice, tier 3 (it changes `/system-curve` and `/pump-group-curve` points; a `METHOD_VERSION` entry and the `/system-curve` corpus comparison).

### SC-3. At a zero-flow one-way element, the curve ends below the duty

- **Consequence:** wrong value shown; **likelihood:** occasional; **reproduced on main:** yes.
- **What happens.** At the flow limit, a one-way element across the cut (a check valve, or an FCV with nothing to pass) carries exactly zero flow. It can be just open with no flow, or closed with the pressure behind it higher than in front. So every head from the 'just open' value upward holds at that flow: the system curve should turn vertical there. The API instead reports that one lowest head as if it were the only answer, with no reason attached. The chart ends the system curve at that low point, while the case's operating point sits at the same flow far above it. The pump and system curves therefore do not cross on screen, the same kind of picture as the owner's photo of 2026-11-26. A grid flow that lands exactly on the limit gets the same single head, so this is not only about the extra point added in 1.6.2.
- **Example.** Reservoir R1 (20 m) feeds pump PU, which feeds tee T1 and then a fixed demand D1 of 20 L/s. A standby reservoir R0 (20 m) also feeds T1 through a check valve (or through FCV V1 at 5 L/s, the recorded network). All pipes are 10 m; the pump curve is 41 m at 20 L/s. The solve puts the pump at 20.0 L/s and 41.0 m, with the standby valve closed: no flow, its outlet side 39.8 m above its inlet. The pump chart's system curve runs from 0.68 m at 15.6 L/s to 1.11 m at 19.2 L/s and ends at (20 L/s, 1.20 m). The operating point at (20 L/s, 41 m) sits 39.8 m above the curve's end. Above 20 L/s the points say no steady state carries the flow. A correct answer would draw a vertical at 20 L/s from 1.20 m upward, through the operating point.
- **Who would hit it.** Users whose pump supplies a fixed demand (an assigned-flow node) that also has a standby or backup source behind a check valve or an FCV. Whenever the backup is shut, the pump's flow equals the demand, which is exactly the limit, so the operating point sits on this flow.
- **The run.** sub23_floor.py on `_floor()`: limit 0.02 [('V1', 0.0)], floor 0.015. The grid gives 0.0156 → 0.6769616782657373 m … 0.0192 → 1.1073006140289756 m, and 0.0204 and up → beyond_limit. The extra point is `{'flow': 0.02, 'head': 1.2009147309991164}` with no reason. The solve gives pump 0.020000000000000417 m³/s at 40.99999999999984 m, and V1 flow 0.0 with headLoss −39.79908526900067. sub3_check.py, with a plain check valve in V1's place: solve 0.019999999999998578 m³/s at 41.000000000000554 m, check valve flow 0.0, headLoss −39.79908526900161; extra point `{'flow': 0.02, 'head': 1.2009147309988428}` with no reason. sub3_grid.py (flowMax 0.04, 5 points): the grid point at exactly 0.02 gives head 1.2009147309991164 with no reason. All scripts are under system-curve-limits/.
- **Options:**
  - When every element across the cut passes zero flow at a point at the limit, run the same test the API already uses for an FCV at its setpoint: does closing that element leave nothing fixing the pressure between it and the pump? If so, report the point as undetermined, with the head found as the foot of the range and 'this head or more' as its bound. Reusing the valve_at_switch reason, with words for a check valve at zero flow, would let the web draw the vertical with no change. A new reason code would also need the web's words. *Cost:* medium (about a day: the rule and its message, a reference case written by someone who has not read the solver, the /system-curve corpus comparison, a METHOD_VERSION bump and its changelog entry). *Tier:* 3. *Risk:* If the test were wrong, a point that truly has a single head would be drawn as a vertical. The corpus comparison shows every point that changes. The group system duty check (C2) would start agreeing on such duties, which is intended, but it changes pump_group_check's counts.
  - Leave it as recorded *Cost:* none. *Tier:* -. *Risk:* The chart keeps showing such operating points off their system curve, the picture the owner already reported once.
- **Recommendation.** Fix it (the first option). Of the four, this is the one a real project reaches: a pump with a check-valved standby source feeding a fixed demand. The chart then contradicts the solve by almost 40 m in a small, ordinary network. The API's existing switch test already decides the case, and the web needs no change if the reason is reused.
- **Records:** docs/roadmap.md §2, 'System curves' limits', third sub-item (line 37); docs/proposals/open-defects-2.md §7, 'A limit point where a one-way element passes no flow' (line 121); apps/api/src/opensolve_pipe/services/solver/system_curve.py _at_switch, _switch_message, _held_open_switch (line 737); apps/api/tests/unit/test_system_curve_limit_points.py _floor(); apps/web/src/lib/utils/system-curve-line.ts module comment (a point with a head is a point of the line).

### SC-4. Group system curve has no extra point at its flow limit

- **Consequence:** value missing; **likelihood:** occasional; **reproduced on main:** yes.
- **What happens.** Since 1.6.2, the single-pump system curve (/system-curve) solves extra points at its flow limit and floor, so the chart can turn vertical exactly at an FCV's setpoint. The pump-group endpoint does not, and it says so in the 1.6.2 changelog: "the group system curve gets no limit points". It does add the duty's own flow, so when the duty sits on the FCV's setpoint the vertical is drawn there. When the duty is elsewhere, the group system curve stops at the last grid flow below the setpoint, and nothing at all is drawn at the setpoint. This matters most in a duty/standby station. There, another lineup (for example both pumps running) reaches the FCV's cap, but its duty ring floats above the end of the shown case's system curve, and the ring's words say the curve has no rise next to its flow.
- **Example.** The shared fixture 'fcv-outside': pumps PA and PB in parallel form a station, with an FCV FC (60 L/s) on the delivery pipe. The duty is 45.55 L/s at 30.47 m, and the system duty check agrees. The group system curve's default range is 0 to 125.8 L/s, about 3.1 L/s apart: 59.76 L/s → 38.35 m, then 62.90 L/s → beyond the limit (60 L/s). No vertical is drawn. With a 0 to 80 L/s range, 60 L/s happens to be a grid flow, and the vertical appears from 38.50 m up. Duty/standby version: FC at 40 L/s, PB off in the shown case. The duty is 37.74 L/s at 26.99 m; the curve runs to 38.61 L/s and 27.35 m, then 40.45 L/s is beyond the limit. With both pumps on, the duty is 40.0 L/s at 31.64 m, the FCV throttling. That ring lies between a point with a head and one without, so by the group chart's ring rule it reads 'Not said: the curve has no rise next to its flow'. With 40 L/s on the grid (0 to 80 L/s), the vertical runs from 27.94 m up and passes through that duty.
- **Who would hit it.** Users of the Pumps tab's group chart whose station has an FCV downstream, whose setpoint lies in the chart's range but is not reached at the shown case's duty. Duty/standby stations, whose other lineups reach the cap, are hit hardest.
- **The run.** sub4_group.py posts the fixture's pgi.fcv_outside_project() to /api/v1/pump-group-curve with curve 'system'. Duty flow 0.04555061458508251, head 30.46543287887018; flowRange max 0.12580783795420228. Points: 0.059759 → 38.35063383680461 m; 0.062904 → beyond_limit, limitFlow 0.06. The response keys include no limitPoints. With flowMax 0.08: 0.06 → valve_at_switch, openHead 38.502017682893054. sub4_standby.py (FC 0.04, PB off): duty 0.0377369955787031 at 26.993007336057005 m; 0.038613 → 27.351702862906002 m; 0.040452 → beyond_limit. Both running ('group' curve): duty 0.04 at 31.64364571182351 m. sub4_ongrid.py (flowMax 0.08): 0.04 → valve_at_switch, openHead 27.935527792011182, 'lower'. The ring's words come from reading dutyClaim in apps/web/src/lib/utils/pump-group-one-off.ts (it returns 'gap' when the neighbouring point has no head); I did not view this in a browser.
- **Options:**
  - Give the group system curve its extra points: in group_system_curve, call limit_flows with the station's forced link (flow_limit already handles stations, D21) and solve each point alone, as /system-curve does. Return them in systemPoints, marked, or in their own list. *Cost:* medium (about a day: the API, the generated types, the group chart's merge, tables and export counts, a reference case, and the pump_group_check run). *Tier:* 3. *Risk:* Point counts in the group chart's tables and workbook change, so tests, fixtures and e2e checks pinned to the current counts need regenerating. Ring claims near the cap change from 'gap' to 'on', which is intended. The 1.6.2 changelog's statement must be superseded by a new entry.
  - Leave it as recorded *Cost:* none. *Tier:* -. *Risk:* The group system curve stops one grid step short of the FCV's cap, and lineups that reach the cap show no crossing.
- **Recommendation.** Fix it, in the same slice as SC-3. Both make the charts' curves meet where the solve says they meet. They share one corpus proof and one method-version entry, and this one reuses code that is already proven on /system-curve.
- **Records:** docs/roadmap.md §1, 'Pump groups' bullet (line 19): 'the group system curve's own flow limit where the duty is not at it, whose points there stay a gap'; docs/proposals/open-defects-2.md §7, 'The group system curve's own limit' (line 114); docs/proposals/open-defects-2.md §9, the version paragraph (C3's changelog item); apps/api/src/opensolve_pipe/services/pump_groups.py group_system_curve (line 1803); apps/api/src/opensolve_pipe/services/solver/version.py METHOD_CHANGELOG 1.6.2 ('the group system curve gets no limit points'); apps/web/src/lib/utils/pump-group-one-off.ts dutyClaim and DUTY_CLAIM_WORDS.gap (line 266); apps/api/tests/fixtures/pump_groups_input.py fcv_outside_project (line 333).

## 3. Fix next: messages that point the wrong way

No value changes; the words a user reads send them after the wrong cause. Each touches the solve's response, so tier 3 with the corpus comparison (`--ignore-empty` for a field added).

### CS-1. A pump dead-headed on its suction side is described as discharge closed off

- **Consequence:** misleading or vague message; **likelihood:** occasional; **reproduced on main:** yes.
- **What happens.** When a fixed-speed pump cannot run and one of its sides is shut (for example a foot valve that the system head keeps closed), the solver gets the side right in its own message: 'its suction is closed off'. But the flag's data carries only the pump's head rise and shutoff head, not which side. The web app writes its own sentence from that data, and its rule says 'discharge closed off' whenever the head rise is not above the shutoff head. So a suction-side dead-head is shown on screen as a discharge-side one. A speed-controlled pump already gets the side, because its control flag carries it.
- **Example.** Network from the API's own test (test_m3_solve.py foot_valve_line): tank R1 at 2 m, 5 m pipe, check valve CV used as a foot valve, 5 m pipe, pump PU (shutoff head 32 m), 200 m pipe, tank R2 at 40 m. The system head (38 m) is above the shutoff, the foot valve closes and the pump runs dead-headed. The pump's status reads 'No flow (discharge closed off: dead-headed at shutoff head)' and the flag reads 'Its discharge is closed off, so it runs dead-headed at its shutoff head (32 m), held at zero flow by its check.' In fact the suction is the closed side.
- **Who would hit it.** Anyone who models a pump with a foot valve or suction check valve, or a closed valve on the suction side, against a system head above the pump's shutoff head.
- **The run.** A scratch script, completeness/foot_valve.py, run with `cd apps/api && uv run python <script>` (it reuses the test's network builder). Output: converged True; pump status no_flow, flow 0.0, head 32.0; message: "pump 'PU': its suction is closed off, so it runs dead-headed at its shutoff head (32 m at speed 1); flow would reverse, and the pump's check holds it at zero"; details: {'headRise': 32.0, 'shutoffHead': 32.0}. The web's words come from apps/web/src/lib/utils/flag-text.ts lines 364-370 (rise > shutoff, otherwise 'Its discharge is closed off…') and apps/web/src/lib/utils/results.ts lines 1047-1052 ('(discharge closed off: dead-headed at shutoff head)'). With headRise equal to shutoffHead (32 = 32) both take the 'discharge' branch. The web half was read, not run.
- **Options:**
  - API adds the closed side to PUMP_FLOW_REVERSAL's details ('closedOff': suction or discharge), as the speed-control flag already does (results.py line 810); the web reads it in both places *Cost:* medium (the code is under an hour; the proof is the rest of a day). *Tier:* 3 (a value added to the solve's response: corpus comparison with --ignore-empty for the new field). *Risk:* Low. No solved value changes. The generated types and the export fixture need regenerating.
  - Web only: when the side is unknown, say 'one side is closed off' rather than naming the discharge *Cost:* small. *Tier:* 2. *Risk:* Gives up the precise words for the common discharge case.
- **Recommendation.** Take the API option. It is the real fix and is small in code. The roadmap already says it needs an API detail (pumps-nits.md §11.6).
- **Records:** docs/proposals/pumps-nits.md §10 (first bullet) and §11.6; docs/roadmap.md §2, Pumps nits, 'Later: a suction-side dead-head reads "discharge closed off"'; apps/api/src/opensolve_pipe/services/solver/results.py lines 915-935; apps/web/src/lib/utils/flag-text.ts lines 364-370; apps/web/src/lib/utils/results.ts lines 1030-1053.

### CS-3. A pressure-reducing valve on a short pipe into a tank reports 'not converged'

- **Consequence:** misleading or vague message; **likelihood:** occasional; **reproduced on main:** yes.
- **What happens.** The solver takes the velocity head that an active PRV holds from the previous iteration. Where the pipe after the PRV loses only about one velocity head (a short spool ending in a tank), each iteration closes only a small share of the gap. The default 100 iterations run out and the solve is reported not converged, although a correct steady state exists. Raising Maximum iterations converges it, and a wrong converged answer is never given. New finding: the message blames status cycling ('the status and branch-loss updates keep returning to this state (control valves: V)') rather than slow convergence, so it points the user the wrong way. An exact fix (C1) was designed and shelved by the owner on 2026-10-25.
- **Example.** Tank R1 at 50 m, 100 m of 0.1 m pipe, PRV V set to 49,424.5 Pa(g) (5.05 m of water at 998 kg/m³), then a 0.3 m spool of 0.1 m pipe with an exit loss into tank R2 at 5 m. The user presses Solve and sees 'The solve did not converge… the status and branch-loss updates keep returning to this state (control valves: V)'. With a 1 m spool it is also not converged, although the largest flow change is already 9.41e-11 m³/s. A 5 m spool converges.
- **Who would hit it.** Anyone modelling a PRV station that discharges through a short spool into a tank, or into a tee and a main close by.
- **The run.** A scratch script, completeness/prv_spool.py. Output: 'spool 0.3 m, maxIterations default: converged False, iterations 111 inner / 3 outer'; message 'not converged after 100 iterations (largest flow change 5.08e-06 m³/s, …, energy residual 0.000284 m); the status and branch-loss updates keep returning to this state (control valves: V)'. 'spool 1.0 m: converged False, … largest flow change 9.41e-11 m³/s'. 'spool 5.0 m: converged True, 25 inner, PRV active, flow 0.007746…'. 'spool 0.3 m, maxIterations 1000: converged True, 340 inner, PRV active, flow 0.033955…'. These match the shelved proposal's measurements (vfd-slice2-discharge-pressure.md §2, 'not converged' up to 1 m spools).
- **Options:**
  - Change the message: when an active PRV or PSV's flow change is still shrinking at the limit, say the solve is converging slowly and suggest raising Maximum iterations *Cost:* small to medium. *Tier:* 3 (a solve's message). *Risk:* Low. Values are unchanged. It needs a rule for 'shrinking' that does not fire on genuine cycling.
  - Raise the default Maximum iterations (the schema allows up to 1000) *Cost:* small code, medium proof. *Tier:* 3 (results change for projects that now fail: D13 proof). *Risk:* Networks that truly do not converge take longer before they fail, within the 45 s budget.
  - C1: the exact Newton step for the velocity-head term (designed and measured, shelved) *Cost:* large. *Tier:* 3. *Risk:* Touches solver status logic, so it needs a METHOD_VERSION bump and the full D13 proof.
- **Recommendation.** Take the message change now: it costs little and stops sending users after a cycling valve that is not there. Revisit C1 only if the owner asks.
- **Records:** docs/TSD.md §12, Open (Later) item 5; docs/roadmap.md §3 (Shelved); docs/proposals/vfd-slice2-discharge-pressure.md §2 (contraction ratio and measurements).

### CS-2. A drooping pump curve can be held at no flow when it could run

- **Consequence:** wrong value shown; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** Some pump curves rise from shutoff to a peak before falling (a 'drooping' curve). The solver decides whether a pump can run by comparing the head across it with its shutoff head (EPANET 2.2's rule), not with the curve's peak. When the system's static head lies between the shutoff head and the peak, the solver stops the pump at no flow and flags it invalid, even though a normal running point exists on the falling part of the curve. EPANET refuses such curves outright. The owner decided on 2026-10-23 to keep this behaviour and document it. The flag then says 'flow would reverse', which is not true in this band.
- **Example.** Pump curve (test input): 30 m at 0, 31 m at 0.01, 28 m at 0.02 and 20 m at 0.03 m³/s. Tank R1 at 2 m, then 10 m of 0.1 m pipe, the pump, 20 m of 0.1 m pipe, tank R2 at 32.3 m (static rise 30.3 m). The result shows the pump 'No flow' with the red flag 'the system head across it (30.3 m) exceeds its shutoff head (30 m)…; flow would reverse'. A running point exists at 0.01138 m³/s and 30.92 m of head.
- **Who would hit it.** Users with a drooping (low specific speed) pump curve whose static head lies in the narrow band between the shutoff head and the peak.
- **The run.** A scratch script, completeness/drooping_and_wye.py (the test's pump_line builder with heads [30, 31, 28, 20], h2 32.3 m, l2 20 m). Output: 'converged True | status no_flow | flow 0.0 | head 30.299999999999997', flag PUMP_FLOW_REVERSAL as quoted. A root of curve head = static + pipe losses, found with the test's own closed-form helpers and brentq: 'no root on [0.002, 0.01]', 'running state exists: Q = 0.0113761 m3/s, head 30.9165 m'.
- **Options:**
  - Leave as decided (owner, 2026-10-23) *Cost:* none. *Tier:* -. *Risk:* The result stays wrong in that band, though it is flagged invalid.
  - Reword the flag when the curve droops and the head lies between shutoff and peak: say a running point may exist on the falling part and the solver's rule does not find it *Cost:* small to medium. *Tier:* 3 (a message the solve returns). *Risk:* Low. Values are unchanged.
  - Refuse drooping curves at input, as EPANET does (error 227) *Cost:* medium. *Tier:* 3. *Risk:* Refuses curves users have from datasheets.
  - Close the pump against s² × the curve's peak rather than s² × the shutoff head *Cost:* large (a method change: METHOD_VERSION bump and the D13 corpus and fuzz proofs). *Tier:* 3. *Risk:* On the rising part two running points can exist, so the solver may pick either. This also changes fixed pumps.
- **Recommendation.** Ask the owner whether the 2026-10-23 decision still stands now that the wording can be fixed cheaply. At least take the rewording, because today the flag says 'flow would reverse' when it would not.
- **Records:** docs/TSD.md §12, Open (Later) item 3; docs/decisions/D11-speed-controlled-pumps.md (the drooping-curve paragraph).

## 4. Small web fixes

Tier 1 or 2, web only; a few hours together.

### WEB-1. "Converted from" note vanishes when the paired field is entered

- **Consequence:** cosmetic; **likelihood:** occasional; **reproduced on main:** yes.
- **What happens.** When you type a number with a different unit after it (for example "100 gpm" in a project that shows L/s), the field stores the converted value and shows a small line under it: "Converted from 100 gpm." That line is supposed to stay until you type in that field again, store another value there, or change the project's units. Three places have two linked fields, a low limit and a high limit: the pump's allowable operating region (in the pump curve's Manufacturer data), and two design checks in Settings (pump operating region as % of BEP flow, and pipe velocity minimum and maximum). In those places the app redraws each field from scratch whenever its partner's stored value changes. It does this on purpose, so that a refusal like "Must be less than ..." goes away once the partner moves. The redraw also throws away the "Converted from" line. The stored value is right and is shown right. Only the confirmation line goes.
- **Example.** Pump transfer example (flows shown in L/s), pump P1, Manufacturer data. Type "100 gpm" in "Allowable operating region, lowest flow" and press Enter: it shows 6.30902 with "Converted from 100 gpm." under it. Then type "400 gpm" in "highest flow": it shows 25.2361 with "Converted from 400 gpm.", and the line under the lowest flow is gone, though its value (6.30902 L/s) is still stored. The same happens in Settings, Design checks, Pipe velocity: "3 ft/s" in the minimum shows 0.9144 m/s with its note. Then "10 ft/s" in the maximum removes the minimum's note. For comparison, two fields that are not linked (Minimum continuous stable flow "100 gpm", then Minimum thermal flow "50 gpm") both keep their notes.
- **Who would hit it.** Anyone who fills in both ends of one of these three pairs with a unit typed after the number, for example from a US datasheet in an SI project. A screen-reader user has already heard the note read out when the first value was entered, so for them almost nothing is lost. What goes is the line on screen.
- **The run.** Scratch Vitest component tests run against main's components, with nothing in the repository changed: web/converted-note.svelte.test.ts and control-note.svelte.test.ts, run with `cd /home/user/opensolve-pipe/apps/web && pnpm exec vitest run --config web/vitest.scratch.config.mts --silent=false --reporter=verbose converted-note`. Output: 'B stored region: {"flowMin":0.006309019639999999,"flowMax":0.025236078559999996}', 'B lowest field value: 6.30902 | same element as before: false | visible note under lowest: (none)', 'B highest field value: 25.2361 | visible note under highest: Converted from 400 gpm.'; 'D stored: {"source":{"kind":"user"},"minimum":0.9144000000000001,"maximum":3.048}', 'D min value: 0.9144 | note under min: (none)', 'D max value: 3.048 | note under max: Converted from 10 ft/s.'. Control: 'E stable value: 6.30902 | note: Converted from 100 gpm.', 'E thermal value: 3.15451 | note: Converted from 50 gpm.'. I did not run the BEP-percentage pair. It uses the same structure (DesignChecksSettings.svelte:156 and :168).
- **Options:**
  - Replace the redraw: give the number field a narrower 'the partner changed' signal that clears only its own refusal and unsaved text and keeps the conversion note. The field already has a similar 'reset' signal, but that one also clears the note. Then remove the six redraw blocks. *Cost:* small (a few hours with the tests written first in both forms). *Tier:* 2 (focus and accessibility paths in two forms; no stored value can change). *Risk:* The refusal must still clear when the partner moves. Existing tests guard this ('drops a refusal once either end as stored changes', the F4 focus tests), and they must stay green unchanged. This option also removes the possible focus problem in WEB-1b.
  - Keep the redraw and have each form remember the note and hand it back to the redrawn field. *Cost:* small to medium. *Tier:* 2. *Risk:* Note state copied into two parent forms, a second source of truth that can drift from the field's own rules (dropped on the next keystroke, on another stored value, on a change of units).
  - Leave it. *Cost:* none. *Tier:* n/a. *Risk:* None to values. A user who types units in both ends sees only the latest end's note and may wonder whether the first one was converted. Its value is shown correctly in the field's own unit.
- **Recommendation.** Do the first option as one small tier-2 slice together with the browser check in WEB-1b, because one change settles both. If the owner prefers not to spend the time, it is fine to leave: the value is converted and stored correctly, and only a confirmation line is lost.
- **Records:** docs/roadmap.md §2, Usability bullet (line 23): "the paired fields' 'Converted from' note still goes when the other end changes"; docs/proposals/open-defects.md §6 (line 52), F4's other half; docs/proposals/usability-entry.md §9 (line 83) and §3 'Shown' (line 41, the note's rule); apps/web/src/lib/components/panel/forms/PumpCurveEditor.svelte:284-312 ({#key region?.flowMax ?? null} / {#key region?.flowMin ?? null}); apps/web/src/lib/components/workspace/DesignChecksSettings.svelte:155-202 (four {#key} blocks); apps/web/src/lib/components/ui/NumberField.svelte:161-173 (the note lives in the field's own state, so a redraw loses it), :324-328 (cleared on the field's next keystroke).

### WEB-1b. Tabbing between paired fields may drop keyboard focus (unverified)

- **Consequence:** manual check pending; **likelihood:** occasional; **reproduced on main:** not attempted.
- **What happens.** Found while checking WEB-1, and not in the records. In the same three pairs, storing one end's value redraws the other end from scratch. Pressing Tab after typing in the low limit stores that value at the moment the focus leaves it, so the high-limit field the focus is moving to gets replaced by a new copy at that same moment. I confirmed the replacement in a component test. What I could not confirm without a real browser is whether Chrome then puts the focus on the new copy or on nothing. If it is nothing, a keyboard user who presses Tab lands nowhere, and their next keystrokes go nowhere. No browser test covers Tab between these fields; the existing focus tests use Enter, which keeps the focus.
- **Example.** Settings, Design checks, Pipe velocity on. Type 1 in Minimum velocity and press Tab toward Maximum velocity. In the component test, the Maximum velocity field present before the value was stored is gone from the page once it is stored ('maximum field replaced: true | old one still on the page: false'), and focusing that old field does nothing.
- **Who would hit it.** Keyboard and screen-reader users who tab from one limit to the other after changing it, if the suspicion holds.
- **The run.** Partial, in jsdom only: web/tab-pair.svelte.test.ts (the same scratch config as WEB-1). Output: 'F stored: {"source":{"kind":"user"},"minimum":1} | maximum field replaced: true | old one still on the page: false'. Where the focus lands in Chrome after a real Tab needs a browser, and Playwright was out of scope for this check. I found no e2e test that tabs between these fields: grep of tests/*.e2e.ts for the fields' labels found none.
- **Options:**
  - Check by hand or with one Playwright test (type in the low limit, press Tab, assert the high limit has focus) on desktop and mobile. *Cost:* small. *Tier:* 1 (a test added). *Risk:* None. If it fails, WEB-1's first fix option is the cure.
  - Fix WEB-1 by its first option, which removes the redraw and with it this risk, and add the Tab test. *Cost:* small (shared with WEB-1). *Tier:* 2. *Risk:* As WEB-1.
- **Recommendation.** Add the Tab test as part of the WEB-1 fix. Do not report it to anyone as a defect until that test has run in a browser.
- **Records:** apps/web/src/lib/components/workspace/DesignChecksSettings.svelte:155-202; apps/web/src/lib/components/panel/forms/PumpCurveEditor.svelte:284-312; apps/web/src/lib/components/workspace/DesignChecksSettings.svelte.test.ts:114-137 (focus test, Enter only); docs/proposals/usability-entry.md §9 (line 83): the focus dropped after Enter before F4.

### CS-9. The pump chart's cancelled system curve waits for a button press

- **Consequence:** cosmetic; **likelihood:** occasional; **reproduced on main:** not attempted.
- **What happens.** A solve, Solve all or goal seek cancels any curve being computed. Since slice 4d, the Pumps together card asks again for its own cancelled curves once nothing is calculating. The single pump chart's system curve does not: it stays cancelled and shows a button to compute it again. The records list making it behave like the card as 'Later'.
- **Example.** In a project with scenarios, open the Pumps tab while the pump chart's system curve is computing, then start a goal seek. When the run ends, the Pumps together card below redraws its curves by itself, but the pump chart shows its curve as cancelled until the user presses the button.
- **Who would hit it.** Users who start a solve or a goal seek while the pump chart is still computing its curve.
- **The run.** Not run in a browser. Confirmed by reading the code: apps/web/src/lib/components/results/PumpsView.svelte lines 639-670 ask again for the card's curves that a calculation cancelled ('a cancelled curve is never asked again otherwise'). The pump chart only receives `onretry` (lines 1108-1110), drawn as a button when the curve is cancelled (PumpChart.svelte line 1102).
- **Options:**
  - Give the pump chart's system curve the card's rule: after any calculation ends, ask again for a curve that calculation cancelled (not one the user cancelled) *Cost:* small to medium. *Tier:* 2 (async and cancel paths). *Risk:* Request ordering with the card's curves in the one queue: the card asks for the shown case's curves first.
- **Recommendation.** Do it in the next Pumps-tab web slice. It is a small consistency fix.
- **Records:** docs/proposals/pump-groups.md §17 (As built, slice 4d), item 7; docs/roadmap.md §2, Pump groups, 'Later: … the pump chart's system curves asked again after a solve'.

### CS-14. Pasted '1.000' meaning one thousand is read as 1

- **Consequence:** wrong value shown; **likelihood:** rare; **reproduced on main:** not attempted.
- **What happens.** A pump curve can be pasted into its points table. The app always reads a point as a decimal mark, so a column written with points as thousands separators ('1.000' for one thousand, as some European data sheets do) is read as 1, 1.5, 2 and so on, a thousand times too small, with no warning. Commas are refused for exactly this reason, but points are not, since refusing every value with three decimals would refuse ordinary data. This is a documented design choice, not a bug, but it can store a wrong value.
- **Example.** A user copies a flow column '1.000 / 1.500 / 2.000' (meaning 1,000 to 2,000 L/h) and a head column from a German data sheet into a pump's curve. The note says 'Pasted 3 points: flow in …' and the table holds 1, 1.5 and 2.
- **Who would hit it.** Users pasting from European-locale data sheets that use whole numbers with dot grouping and no decimal commas.
- **The run.** Not run: there is no test for it in paste-points.test.ts, and running one would need a file in the repo. The behaviour is stated in usability-entry.md §6 (Separators): 'A column grouped with points ("1.000" for one thousand, as some locales write) reads as decimals.'
- **Options:**
  - Leave: the values are visible in the table and on the pump chart *Cost:* none. *Tier:* -. *Risk:* A 1000× error may go unnoticed in a long table.
  - A warning (not a refusal) in the paste note when every value in a column has exactly three digits after the point *Cost:* small. *Tier:* 2 (words only; nothing stored changes). *Risk:* May warn on genuine three-decimal data.
- **Recommendation.** The warning is cheap and keeps the design's choice. Leaving it is also defensible, since such sheets usually also use decimal commas, which are refused.
- **Records:** docs/proposals/usability-entry.md §6 (Separators) and §9.

### WEB-2. Rare browser-test failure in the system-curve keyboard test

- **Consequence:** test flake; **likelihood:** only in tests; **reproduced on main:** not attempted.
- **What happens.** This is a test that sometimes fails, not a fault users see. The failing test is tests/cancel.e2e.ts:271, 'the system curve: Cancel and the button that computes it again hand the focus to each other'. It is the same test the records call :265. A commit on 2026-11-27 (82fd96e) added six lines to an earlier test in the file, which moved it down. Its body has not changed since 2026-11-05. The test opens the pump transfer example and solves it. It then opens the Pumps view, where the app asks the server for the pump's system curve, and the test holds that request so it stays 'computing'. Using only the keyboard, it checks that Cancel hands the focus to 'Compute the system curve' and back. Next it swaps in a fake server error and checks that 'Try again' gets the focus. In the recorded failure (2026-11-25) the fake error never came: the real server answered and the real curve was drawn. The request had got past the test's fake. The most likely cause is in the test, not the app. To swap fakes, it first removes the only fake it has and then installs a new one. In the Playwright version used (1.56.1), removing the last fake turns the browser's request interception off, and installing one turns it back on. If the browser has not finished turning it back on when the test presses Enter, the request goes straight to the real server. A busy machine makes that more likely. The same remove-then-install step happens a second time later in the test. On the app side, I found no request that could go out by itself: after Cancel, the app asks again only when a button is pressed.
- **Example.** No user sees this. What a builder sees: a full local run on the 4-CPU container shows '[mobile] cancel.e2e.ts:271 failed' on a commit that never touched the pump chart. Re-running it usually passes. Recorded: 1 failure in the full run of 2026-11-25, then 95 passes. On 2026-11-27, per the task's account, it failed in a full local run, 4 times in 20 repeats right after, then 0 in 80.
- **Who would hit it.** Only builders running the whole browser suite locally under load; CI has not failed on it in 97 mobile runs.
- **The run.** Playwright was not run (out of scope for this check). What I did instead: (1) `git log -- apps/web/tests/cancel.e2e.ts` and diffing the test's text at e40cdec (line 265) against main (line 271) shows the body is identical ('test body identical since e40cdec'). 82fd96e added six lines to the earlier test at line 189. (2) Read the test: lines 288-292 call `page.unroute` and then `page.route` (fake 500) before Enter; lines 298-299 call `page.unroute` and then `hold` before Enter. (3) Read Playwright 1.56.1: node_modules/.pnpm/playwright-core@1.56.1/node_modules/playwright-core/lib/client/page.js:435-457 (unroute updates the patterns; with no route left, none) and lib/server/chromium/crNetworkManager.js:139-162 (interception on means `Fetch.enable`, off means `Fetch.disable`). (4) Read the app's path: project.svelte.ts:1517-1518 sends nothing for a cancelled curve unless 'retry' is asked; :1548 drops an answer to a cancelled request; PumpChart.svelte:736-751 handles the focus handover. (5) GitHub CI: of the last 98 CI runs (2026-11-13 to 2026-11-28), the mobile end-to-end suite ran 97 times (90 whole, 2 in three shards, 5 in six). 9 failed, none in cancel.e2e.ts: 8 at pump-system.e2e.ts:301 (fixed in Session 16), 1 at data-entry.e2e.ts:30. I found no Playwright trace of either local failure (apps/web/test-results is empty), so the network log of the failing step cannot be read.
- **Options:**
  - Install one fake for the system-curve address at the start of the test and never remove it. A variable picks what it does ('hold', 'answer 500', 'let through'). The browser's interception then stays on for the whole test. Every assertion stays as it is. *Cost:* small (under an hour, plus repeat runs). *Tier:* 1 (a test's structure). *Risk:* None to the app. Because the failure is rare, a clean run of, say, 100 repeats under CPU load shows the fix holds but cannot prove the cause. Saying 'most likely' is the honest record.
  - Keep the test and add a catch-all fake that only passes requests on, installed for the whole page in the test's openExample helper, so removing the specific fake never turns interception off. *Cost:* small. *Tier:* 1. *Risk:* Touches a helper the whole file uses. Same proof limit as above.
  - First capture a failure: repeat the test on mobile under CPU load with traces kept, and read the failing step's network log (was the request fulfilled by the fake or by the server?). *Cost:* small to medium (depends on how long it takes to fail). *Tier:* 1. *Risk:* It may not fail for a long time, as the 0 in 80 run shows.
  - Leave it and keep recording. *Cost:* none. *Tier:* n/a. *Risk:* Each builder who runs the full suite locally may lose time re-checking an unrelated red test.
- **Recommendation.** The first option, recorded as 'most likely cause, not proven'. It is cheap and tier 1, it removes the window whatever the browser does inside, and it weakens no assertion. If a trace of a failure turns up first, read it and record the cause.
- **Records:** docs/roadmap.md §2, Usability bullet (line 23): "cancel.e2e.ts:265 failed once on mobile ... its cause not found"; docs/history.md Session 15 (line 92): the failure's description and the 95 passes since; the task's account of 2026-11-27 (cancel.e2e.ts:271; 4 in 20, then 0 in 80), not yet in the docs; apps/web/tests/cancel.e2e.ts:271-303; git commits 82fd96e (moved it from :265 to :271) and e40cdec; playwright-core 1.56.1 lib/client/page.js:435-457, lib/server/chromium/crNetworkManager.js:139-162; apps/web/src/lib/state/project.svelte.ts:1517-1518, 1548; apps/web/src/lib/components/results/PumpChart.svelte:736-751, 1090-1112; GitHub Actions: repos/ccirone2/opensolve-pipe/actions/runs?per_page=100, jobs and check-run annotations.

## 5. Decisions for the owner

Each needs only an answer; the options and what each means are with it.

### OW-1. Pump station with a bypass: which side counts as suction when flow reverses

- **Consequence:** owner decision pending; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** For a pump group, the app treats the station as the part of the network between two points: S (where the flow comes in) and D (where it leaves). It draws the group curve as the rise from S to D. Usually S is found from the way the pumps face. When a bypass inside the station joins the suction and discharge headers, for example a minimum-flow relief line, the layout alone cannot say which side is which. So the app takes S as the side where the case's own flow enters. If, in some case, the flow runs backwards (from the delivery side, through the bypass, to the suction side), S and D swap, and the app reports the station back to front. Your question is whether that is what you want, or whether S should always stay on the pumps' suction side.
- **Example.** I ran a scratch script on main using the test network bypass_parallel. Pumps P1 and P2 sit in parallel between suction tees TS1/TS2 and discharge tees TD1/TD2. Relief valve RV1 (set at 150 kPa) runs from TD2 back to TS2. The suction tank R1 is at 2 m, and the pumps' shutoff head is 45 m.

With the delivery tank R2 at 20 m everything reads normally:
- S is TS1's run inlet.
- The duty is 0.0393 m3/s at a rise of 28.86 m.
- The group curve runs from 0.1098 m3/s at 0 m down to -0.0478 m3/s at 90 m.

With R2 raised to 60 m, above what the pumps can lift:
- The pumps stop (zero flow), and RV1 carries 0.0353 m3/s backwards from R2 to R1.
- The station is turned around: S becomes TD2's run outlet (the discharge side) and D becomes TS1's run inlet (the suction side).
- The duty reads +0.0353 m3/s at a rise of -49.18 m.
- 8 of the 9 group-curve points are at negative flow, for example (-0.032 m3/s, -31.78 m) and (-0.2192 m3/s, 90.0 m).

On screen, the chart's notes would read 'The group curve is the rise from <discharge tee> to <suction tee>' (pump-group-chart.ts:1425). Since round two, the flow axis starts at zero and anything at negative flow is cut off or listed in the notes instead (open-defects-2.md §2, item X). So most of the pumps' curve would not be drawn. I inferred the chart's appearance from that rule and did not check it in a browser.
- **Who would hit it.** Someone using Pumps together on a station that has a bypass inside it (a minimum-flow relief or recirculation line between the headers), in a case where the delivery head is above what the running pumps can lift, so the flow runs backwards through the bypass.
- **The run.** This is not a defect: the script shows the current behaviour the question is about. owner/mirror.py, run with 'cd apps/api && uv run python <script>'. It uses tests/unit/relief_stations.bypass_parallel(r2_level=20 or 60) and calls group_curve(project, ['P1','P2'], num_points=9).

Output at R2 = 60 m:
- L1 flow -0.03534 m3/s; P1 and P2 status no_flow; RV1 full_lift at 0.03534 m3/s.
- Arrangement mixed, oriented False.
- S (inlet) port: TD2 run_outlet. D (outlet) port: TS1 run_inlet.
- Duty flow 0.03534 m3/s, rise -49.18 m.

Output at R2 = 20 m: S is TS1 run_inlet; duty 0.03933 m3/s at 28.86 m.

If S stayed on the suction side, the duty would read about -0.0353 m3/s at +49.18 m. That would put it on the 20 m run's curve, between (-0.0279, 45.0) and (-0.0378, 56.25). This is my inference from the two runs; I did not compute it directly.
- **Options:**
  - A. Keep it as built (S follows the flow) and record your answer *Cost:* small (under an hour; a line in pump-groups.md §14 and the roadmap). *Tier:* 1. *Risk:* None to values. In this rare case the chart stays hard to read: the pumps' curve is drawn back to front and mostly off the chart.
  - B. S is always the side the pumps draw from, whatever the case's flow does *Cost:* medium (about a day): the API's station finder, its tests, the pump_group_check corpus check, and the chart's wording. *Tier:* 3 (changes reported group-curve and duty numbers for such stations; likely a METHOD_VERSION entry). *Risk:* A new rule for stations whose layout cannot decide S, which needs its own tests. In this case the duty would show at negative flow, listed in the notes rather than drawn, while the pumps' curve reads normally.
  - C. Keep the swap but say so on screen ('the flow runs back through the bypass, so S and D are swapped') *Cost:* medium: the API would need to report that it swapped them. *Tier:* 3 (adds a field to the API's response, though no value changes). *Risk:* Small. The chart stays back to front, but explained.
- **Recommendation.** Answer the question now: it takes a minute and only needs a yes or no. I lean to B, because an engineer expects S to be the pumps' suction side, and B keeps the pumps' curve readable. However, the case is rare and B is a day of careful API work at the highest tier. So if you choose B, schedule it as a small slice after the next feature rather than now. If you are content with the current behaviour, answer A and the item closes.
- **Records:** docs/roadmap.md §2 'Pump groups' bullet; docs/proposals/pump-groups.md §14 'As built (slice 4a)', 'Which port is S'; apps/api/tests/unit/test_pump_groups_relief.py test_a_minimum_flow_relief_bypass_inside_a_parallel_station; apps/api/tests/unit/relief_stations.py bypass_parallel; apps/web/src/lib/utils/pump-group-chart.ts:1425; docs/proposals/open-defects-2.md §2 item X and §9 item 11.

### CS-5. A station with an internal bypass does not catch a reversed pump

- **Consequence:** misleading or vague message; **likelihood:** rare; **reproduced on main:** not attempted.
- **What happens.** The Pumps together card refuses a station whose pumps face opposite ways (MEMBER_REVERSED). It reads each pump's direction from the paths between the station's suction and discharge sides. If a bypass line inside the station joins those two sides, no path is needed through any pump. The directions are then not read, and a pump installed backwards is not refused: the station is called 'mixed', with its suction side taken as the side the duty's flow enters. This is distinct from, but next to, the open owner question on how such a bypass station's frame is drawn.
- **Example.** A suction header and a discharge header joined by two pumps P1 and P2, plus a recirculation bypass line between the headers. P2 is accidentally connected with its suction on the discharge header. Expected: the card says P2 faces the wrong way. As recorded, the station is accepted as mixed and its curves are offered.
- **Who would hit it.** A user who models a station with a bypass or recirculation line and has wired one pump backwards (a modelling mistake).
- **The run.** Not attempted: building a station through the pump-group endpoint is not cheap in 25 minutes. The record is pump-groups.md §14 'Known limit: a bypass hides reversed members', found by the slice 4a review. No later record says it was fixed.
- **Options:**
  - Read each member's direction on the vertex graph, as the code already checks whether a member lies on a way (`_on_a_way`), and refuse reversed members *Cost:* medium. *Tier:* 3 (an API refusal; pump_group_check must stay at 0 violations). *Risk:* Could newly refuse stations users have today.
  - Leave *Cost:* none. *Tier:* -. *Risk:* A wrongly wired station gets curves rather than a refusal.
- **Recommendation.** Do it together with the open bypass frame question (covered by another group), since both concern a bypass inside a station and one design pass can settle both.
- **Records:** docs/proposals/pump-groups.md §14 (As built, slice 4a), 'Known limit: a bypass hides reversed members'; docs/decisions/D21-pump-groups.md (MEMBER_REVERSED).

### OW-3. Pump lineups table: a 30 px scroll and fewer rows on phones

- **Consequence:** owner decision pending; **likelihood:** occasional; **reproduced on main:** not attempted.
- **What happens.** Two layout results of the Pump lineups table were kept as built and left for you to accept or change; they are web defaults you can reverse at any time (D14). First (item 71): on a desktop, when the table is opened from the Pumps together card, a change that renames a lineup makes the status sentence longer, and the panel then scrolls by 30 px. Second (item 55): on a phone, the first screen shows fewer pump rows than the design's prototype did. The reason is that each changed pump's 'Changed · Base: On · Reset' note wraps onto extra lines. Nothing is lost in either case; you just scroll a little more.
- **Example.** Item 71: at 1280×800, open the condenser example's Pumps together card and press 'Pump lineups table…'. The filter sentence makes the intro 88 px tall instead of 40. When it opens, the panel's content is 552 px where it may take 558, so it does not scroll. After a press that renames a lineup it is 588 px, so the body scrolls by 30 px; six rows are still fully visible.

Item 55: on a 390×844 phone, in the condenser example's Winter case (five changed pumps), the first screen shows 3 pump rows, against the prototype's 7. It shows 5 rows on a case with one change and 6 in the base list. At 320×640 it shows 1, 1 and 5 rows (the prototype showed 4). A changed pump's field is 100 px tall instead of 40 at 390 px.
- **Who would hit it.** Item 71: desktop users who open the table from the Pumps together card and rename a lineup. Item 55: phone users editing lineups in the Scenarios manager's Pump lineups tab.
- **The run.** Not needed: this is a decision about a measured layout. The numbers come from the build's measurements in pump-lineups.md §15 items 55 and 71.
- **Options:**
  - A. Accept both as built *Cost:* small (a line in the proposal and the roadmap). *Tier:* 1. *Risk:* None.
  - B. Item 71: shorten the filtered table's intro, or allow fewer than six rows in the filtered table, so the panel does not scroll *Cost:* small to medium. *Tier:* 1 (layout inside one component). *Risk:* Shorter wording, or fewer rows visible when the table opens.
  - C. Item 55: put Changed · Base · Reset on one line on phones *Cost:* medium (Build's shared change note, or a phone-only variant). *Tier:* 2 (a component shared by Build and the lineups). *Risk:* It touches every Build field's change note. By the record's own measurement it would not add a row on two of the cases at 320×640.
- **Recommendation.** A. Neither result hides anything, and both fixes cost more than the 30 px or the extra scroll is worth. Answer 'accept' and the item closes.
- **Records:** docs/roadmap.md §2 'Pump lineups' bullet; docs/proposals/pump-lineups.md §15 items 55 and 71, §8.2, §8.10.

### OW-4. Lineups chart: where to label a curve that runs off the right edge

- **Consequence:** owner decision pending; **likelihood:** occasional; **reproduced on main:** not attempted.
- **What happens.** The lineups' group chart draws one curve for each number of pumps running, and labels each curve on the chart. A curve that runs past the chart's right edge is labelled at its last point inside the chart. When you view a low-flow case such as '1 of 4 running', the chart's flow range is short. The labels of the 4- and 3-running curves would then land at the top right, among the other cases' rings and their tags. So the chart leaves those labels out and the notes count them. The tooltips, the chart's text description and its data table still name every curve. Where to put such a label instead is yours to choose (item 108). Item 107, the overlapping point labels, is already settled for both charts. The roadmap still lists it, though, which makes it look open.
- **Example.** The 'lineups' test project has four identical pumps and eight solved scenarios. With '1 of 4 running' shown, the flow axis runs 0-100 L/s. The 4-, 3- and 2-running curves are cut at 100 L/s, and their last points inside the plot are at 98.45-99.97 L/s. For the 4- and 3-running curves that point is at 28.1-36 m, among the rings. On desktop, 5 curves' labels are left out, and the notes say 'Labels of 5 curves are left out for space; the data table lists every curve.' On phones 4 are left out.
- **Who would hit it.** Anyone viewing a low-flow lineup case, for example '1 of 4 running', on the Pumps together group chart with the other cases' rings shown.
- **The run.** Not needed: this is a decision about measured label placement (pump-lineups.md §15 items 107 and 108). Item 107's point-label half is settled by pumps-nits.md slice 5c, per pump-lineups.md §15 item 107's closing note and pumps-results-layout.md F31.
- **Options:**
  - A. Keep it: labels left out where there is no room, counted in the notes *Cost:* small (record the answer; trim the roadmap's item 107 text, which is already settled). *Tier:* 1. *Risk:* None. You read those curves from the tooltips or the data table.
  - B. A new anchor for a cut curve, such as the right edge at the height where the curve leaves the chart, the first free spot moving left along the curve, or the right margin *Cost:* medium (about a day, with the layout tests' measurements redone). *Tier:* 2 (label placement with several states, measured by the e2e layout budgets). *Risk:* New overlaps in other views, and the six measured views need re-measuring.
- **Recommendation.** A, unless you often read lineups at low flow and miss those labels. Either way, trim the roadmap so that item 107 no longer reads as open.
- **Records:** docs/roadmap.md §2 'Pump lineups' bullet; docs/proposals/pump-lineups.md §15 items 107 and 108, §9.3; docs/proposals/pumps-results-layout.md §6 F31.

### OW-5. Pump chart: toggle buttons on two rows, and a taller card with no height limit

- **Consequence:** owner decision pending; **likelihood:** common; **reproduced on main:** not attempted.
- **What happens.** When the area under the pump chart was reorganised (S1), two side effects were left for you to accept or change. First: the row of toggle buttons that show or hide the chart's panels (Efficiency, Shaft power, NPSH, Speed range, Design checks) now takes two rows on a desktop when there are four buttons, and three rows on a small phone. Second: the space under the chart grew by about a quarter in the default view, and nothing in the tests stops it growing further. Both are web defaults you can reverse at any time (D14).
- **Example.** In the test project with two pumps (PA and PB) and Design checks on, there are four toggle buttons. At 1280×800 they take two rows, with 'Design checks' alone on the second (one row before S1). At 390×844 they take two rows, and at 320×640 three rows (148 px). With the Pumps together card closed, the area below the pump chart grew from 859 to 1,096 px at 1280×800 (+28 %), from 1,095 to 1,308 px at 390×844, and from 1,295 to 1,488 px at 320×640. The wrapped buttons, the readout (128 px against 80) and the other cases' section (309 px against 188) account for 221 px of the 237 px growth at 1280×800.
- **Who would hit it.** Everyone who opens a pump's chart. The extra rows appear when a pump has four toggles, for example with Design checks on.
- **The run.** Not needed: these are measured layout facts kept as defaults (pumps-results-layout.md §15 items 42 and 44). The row counts were confirmed again after pumps-nits item 1 (§15 item 42's last bullet).
- **Options:**
  - A. Accept both as built *Cost:* small (a line in the proposal and the roadmap). *Tier:* 1. *Risk:* None now. The card can keep growing unnoticed.
  - B. Add a height limit for the pump card to the layout tests, at today's height *Cost:* small. *Tier:* 1 (a test added). *Risk:* A later change that rightly makes the card taller has to raise the limit on purpose.
  - C. Fit four toggles on one desktop row, with shorter labels or tighter buttons *Cost:* small to medium. *Tier:* 1 (layout inside one component). *Risk:* Smaller tap targets on phones, against the ui-guide's touch-size rule.
- **Recommendation.** A with B: accept the layout, and add the limit so the card cannot grow further unnoticed. C is not worth the smaller tap targets.
- **Records:** docs/roadmap.md §2 'The Pumps tab below the pump chart' bullet ('Open from S1'); docs/proposals/pumps-results-layout.md §15 items 42 and 44; apps/web/src/lib/components/results/PumpChart.svelte (the chip list, lines 378-382).

### CS-6. An old saved column choice can hide NPSH margin in one browser

- **Consequence:** owner decision pending; **likelihood:** rare; **reproduced on main:** not attempted.
- **What happens.** Results per pump remembers in the browser which columns the user hid with Fields. Between pull requests #280 and #285 (mid-November), 'Show all' stored a choice that, under today's columns, hides NPSH margin. A browser that pressed Show all in that window still hides it, and pressing Show all again brings it back. A one-time correction would be a compatibility shim, which D14 forbids until the owner declares a release, so the build asked the owner and recorded no answer.
- **Example.** In a browser used between those merges, the user opens Results per pump, presses Fields, then Show all. Today the NPSH margin column is missing, although Fields counts it as a field.
- **Who would hit it.** Mainly the owner and testers who used the app in that week and pressed Show all.
- **The run.** Not attempted: it needs browser storage written by an old build. Recorded in pumps-nits.md §11.7 L7.
- **Options:**
  - Leave: the user presses Show all once *Cost:* none. *Tier:* -. *Risk:* None beyond the missing column until then.
  - A one-time correction of that stored choice *Cost:* small. *Tier:* 2 (browser view state, not the project). *Risk:* It is the kind of shim D14 rules out before a release.
- **Recommendation.** Leave it, and answer the open question with 'no' so the record can close. Few browsers are affected and the user can fix it themselves.
- **Records:** docs/proposals/pumps-nits.md §11.7, L7; docs/roadmap.md §2, Pumps nits, 'Open from slice E'.

### CS-15. The Pumps tab's many small layout choices left for the owner

- **Consequence:** owner decision pending; **likelihood:** occasional; **reproduced on main:** not attempted.
- **What happens.** Each Pumps-tab web slice ended with a list of small layout choices left 'for the owner'. These are reversible web defaults under D14: things like how tall a table gets on a phone, where a label lands when it has no room, or whether a sorted table's Case column sits second. Slices S2 to S8 (pumps-results-layout.md §15) and the nits' slice E, item 1, 5b and 5c (pumps-nits.md §8.8, §8.14, §11.7) hold several dozen. Another group covers S1's and lineups L2 and L3's. Most are measured residuals (pixels, a label left out at 320 px) rather than wrong values.
- **Example.** At 320×640 the condenser example's group chart leaves out 4 curve labels and the group system curve's tag (all named in the notes). Sorted Running combinations at 1280×800 shows a row's NPSH margin but not its case when scrolled far right (§15 item 165).
- **Who would hit it.** Users of the Pumps tab, mostly on phones and with stations of four or more pumps.
- **The run.** Not attempted: these are many measured layout residuals, each recorded with its numbers in the cited sections.
- **Options:**
  - One walk-through with the owner in the app, at desktop and phone sizes, taking a keep, change or drop for each group of items *Cost:* medium. *Tier:* 1 to 2 per item chosen. *Risk:* Each change moves measured budgets in pumps-layout.e2e.ts.
  - Leave them recorded until a user complains *Cost:* none. *Tier:* -. *Risk:* The record keeps growing.
- **Recommendation.** Batch them into one owner review rather than item by item. Until then nothing here changes a solved value, so it is fine to leave.
- **Records:** docs/roadmap.md §2, 'The Pumps tab below the pump chart' (Open from S2 to S8) and 'Pumps nits' (Open from slice E, item 1, 5b, 5c); docs/proposals/pumps-results-layout.md §15; docs/proposals/pumps-nits.md §8.8, §8.14, §11.7.

### CS-4. A wye fed through its angled leg ends not converged

- **Consequence:** no solution where one exists; **likelihood:** occasional; **reproduced on main:** yes.
- **What happens.** The Crane tee and wye correlations cover only flow whose combined stream passes through a run port. A tee in the other pattern falls back to Darby 3-K and is flagged. A wye whose combined flow passes through its angled leg has no cited correlation at all, so the solve ends not converged and names the wye. The message tells the user the workaround: an ideal (no-loss) wye, or a tee. Better coverage is blocked on a source the owner would have to supply (Idelchik, Bassett et al. 2001 or Gardel 1957).
- **Example.** Tanks R1 at 10 m and R2 at 10 m on the wye's straight run, and tank R3 at 19 m on its 45° lateral, so flow enters through the lateral and splits both ways. The result reads not converged, with 'wye 'W': the solved flow pattern (diverging from outlet_2) has its combined flow through the angled leg, which no cited correlation covers; use lossModel 'ideal' for this wye or a tee'.
- **Who would hit it.** Users with a wye whose lateral is the supply (a branch feeding a header both ways), or a looped network where the flow in a wye reverses.
- **The run.** A scratch script, completeness/drooping_and_wye.py (the test's wye_network(10, 10, 19)). Output: 'wye: converged False'; flags UNSUPPORTED_FLOW_PATTERN invalid (message as quoted) and NOT_CONVERGED 'unsupported branch flow pattern at W: no cited loss correlation (design §5.4)'.
- **Options:**
  - Leave until the owner supplies a source; the message already names the workaround *Cost:* none. *Tier:* -. *Risk:* None new.
  - With a source in hand: implement its correlation, with reference cases written by someone who did not read the solver *Cost:* large. *Tier:* 3. *Risk:* Needs a METHOD_VERSION bump, the corpus proof and cited data (D8).
- **Recommendation.** Fine to leave. The ball is with the owner: does a copy of Idelchik's tables or Bassett et al. 2001 exist that could be supplied?
- **Records:** docs/roadmap.md §1 (Blocked on a source); docs/TSD.md §4.2 (the pattern table) and §12 Decided item 1; docs/library-facts.md, fluids 1.3.1 (Crane tee and wye functions).

## 6. Checks only the owner can do

On a device, in a settings page or with an old link.

### OW-2. The 2026-11-26 photo: group system curve 14.4 m lower than the example's

- **Consequence:** manual check pending; **likelihood:** rare; **reproduced on main:** not attempted.
- **What happens.** Your photo of 2026-11-26 showed the condenser example's group chart with the orange group system curve starting at about -4 m at zero flow, 14.4 m below what the shipped example gives. Round two fixed the two drawing defects the photo showed: the curve stopping short of the Group point, and the flow axis starting at -5,000 L/s. The 14.4 m itself was never explained, because nobody had your project or the server version you used. The record matches it exactly if the cooling tower basin's level was 15.0 m instead of the example's 0.6 m. One look at your saved link would settle it.
- **Example.** Values from the fixture the API generates for the shipped example at method version 1.6.2, 'Chiller plant condenser water system':
- As shipped, the group system curve starts at 10.4 m at zero flow (10.45 m at 351.1 L/s), and the duty is 5,678.1 L/s at a rise of 31.48 m.
- With the 'Cooling tower basin' Liquid level set to 15.0 m, the curve starts at -4.0 m (-3.95 m at 351.1 L/s), with the same duty, 5,678.1 L/s at 31.48 m.
The photo showed about -4 m at zero flow and the group curve near (5,700 L/s, 31 m). The example's basin level is 0.6 m (examples.ts:345 and :438). The deployed API was redeployed on 2026-11-27 to 322db41 at method 1.6.2, so today's site is the version that has round two's fixes. The server version at the time of the photo was not recorded, and the server no longer reports it.
- **Who would hit it.** Only you: it concerns one project you photographed.
- **The run.** Your project is not available, so the photo itself cannot be reproduced. I read the comparison values from apps/web/src/lib/utils/__fixtures__/condenser-charts.json, which apps/api/tests/fixtures/condenser_charts.py generates at methodVersion 1.6.2. Its cases 'base' (no edits) and 'basin15' (B1 liquidLevel 15.0) give systemPoints[0] = (0.0, 10.4 m) and (0.0, -4.0 m), and the same duty, 5678.1 L/s at 31.48 m.
- **Options:**
  - A. You check the saved link (about a minute): on your phone, reopen the link from that day, for example from the browser's history. In Build, select 'Cooling tower basin' and read Liquid level. If it is not 0.6 m (15.0 m would explain the whole 14.4 m), the difference came from your data and the item closes. *Cost:* small (a minute for you; a docs line to close it). *Tier:* 1. *Risk:* None.
  - B. If the level is 0.6 m: press Solve on today's site, open Results, Pumps, Pumps together, Group chart, and read where the group system curve starts at zero flow. 10.4 m means today's server is right and the old one differed. About -4 m still means a real discrepancy: send the link. It carries the whole project, so sharing it is your choice. *Cost:* small for you; investigating a real discrepancy could be medium. *Tier:* 1 to record; 3 if it turns out to be a defect. *Risk:* None to check.
  - C. If the link is lost: close the item as 'explained by a basin level of 15.0 m, not reproducible'. The visible defects are fixed either way. *Cost:* small. *Tier:* 1. *Risk:* A real discrepancy, if there was one, would go unnoticed. The fixture shows the shipped example gives 10.4 m on today's code.
- **Recommendation.** Do A. Then B only if the level reads 0.6 m. If you cannot find the link, choose C. Nothing points to a defect: the basin-level explanation matches to the decimal.
- **Records:** docs/roadmap.md §2 'Pump groups' bullet ('For the owner: the project in the photo'); docs/proposals/open-defects-2.md §1 (the photo), §2 ('The photo's 15 m'), §7 ('The photo's project'); docs/history.md lines 147-151 (the deploy of 322db41, 1.6.2); apps/web/src/lib/utils/__fixtures__/condenser-charts.json (cases base and basin15); apps/web/src/lib/utils/examples.ts:345, :438.

### OW-6. Export: spreadsheet checks only a person with Excel, Numbers or an iPhone can do

- **Consequence:** manual check pending; **likelihood:** occasional; **reproduced on main:** not attempted.
- **What happens.** The export (workbook, CSV zip, chart image) was tested by machine against exact file contents, and opened in pandas and LibreOffice. It has never been opened in Microsoft Excel 365, Apple Numbers or Google Sheets, or on an iPhone. Excel can refuse a file other programs accept, showing 'We found a problem with some content'. Under German regional settings (comma as the decimal mark) a CSV can be read silently wrong: 101.325 becomes 101325. The zip's README.txt tells the user how to avoid that, but its Excel steps were never checked against real menus. These checks are meant to be done once before release and whenever the export code changes.
- **Example.** Already done: the workbook in Excel for Android and the chart image on Android (by you, 2026-10-26), and LibreOffice 24.2 under a German setting (2026-11-03). Still to do, each a few minutes. In the app, open the condenser example, press Solve, then Export:
1. Workbook in Excel 365 on Windows, Mac and the web: it opens with no repair prompt, the header rows stay frozen, the filter and print titles are there, and Ctrl+T selects from row 3.
2. The same workbook in Numbers (Mac, iPhone) and Google Sheets.
3. CSV zip in Excel on Windows set to German regional settings: double-click a CSV (one column is expected), then follow README.txt's Data > From Text/CSV steps, and note any menu names that differ.
4. Windows' Extract All on the zip, with a long project name and case name, then open a CSV from the extracted folder.
5. iPhone Safari: download the workbook and find it in Files > Downloads, then open it in Excel and Numbers. Download the image and save it to Photos with Share > Save Image.
6. Export once from inside Teams' or Slack's built-in browser.
- **Who would hit it.** Engineers who export results to Excel, especially on Windows with a comma decimal setting, and iPhone users.
- **The run.** Cannot be run from a cloud container: it needs Excel, Numbers, an iPhone and Windows. The list comes from export.md §7.4 and roadmap §5.
- **Options:**
  - A. Do steps 1 and 3 now (Excel 365 on Windows, the German-locale CSV) and record them; leave the rest for before release *Cost:* small (about 20 minutes for you; Claude records the result). *Tier:* 1. *Risk:* The untested platforms stay untested until release.
  - B. Do the whole list now *Cost:* medium (an hour or two across devices). *Tier:* 1. *Risk:* None. It may need redoing if the export changes before release.
  - C. Leave it all until you declare a release (D14) *Cost:* none now. *Tier:* 1. *Risk:* An Excel repair prompt or a README wording error stays hidden until then.
- **Recommendation.** A. Excel on Windows is what most engineers use, and the export proposal names 'Excel was not tested' as its main untested risk. The rest can wait for the release checklist.
- **Records:** docs/roadmap.md §5 'Still to do by hand'; docs/proposals/export.md §7.4 'By hand', risk table rows 'Excel was not tested' and 'Comma-decimal locales', §12 item 22; docs/TSD.md §10.3 (Export).

### OW-7. Editing speed on large networks: never measured on a phone, Firefox or Safari

- **Consequence:** manual check pending; **likelihood:** rare; **reproduced on main:** not attempted.
- **What happens.** Earlier work made each edit on a very large network much faster. The page used to freeze for 0.7 to 2.5 s on a slowed-down desktop. It was measured only in Chrome on a desktop, with the processor slowed to imitate a phone. Nobody has typed into a large project on a real phone, or in Firefox or Safari, to see whether typing still lags.
- **Example.** Before the fix, an edit on a network near the size limit froze the page for 140-405 ms on a desktop, and for 0.7-2.5 s with the processor slowed four times. After it, the desktop freeze was gone in the typical edit, and the slowed-down medians were 68-229 ms. Single runs reached 329-405 ms. The real-phone experience is unknown.
- **Who would hit it.** Someone editing a network of several hundred components or more on a phone, or in Safari or Firefox.
- **The run.** Needs a real phone and Safari/Firefox. Figures from TSD §12 item 20 and docs/history.md (Session 13's line).
- **Options:**
  - A. Claude makes a link to a large test network, near the size limit of 1,000 components and 2,000 connections. You open it on your phone, change a few pipe lengths and names, and say whether typing lags *Cost:* small (Claude builds the link; about five minutes for you). *Tier:* 1. *Risk:* None. The result is a feel, not a measurement.
  - B. Leave it until a real large project is used on a phone *Cost:* none. *Tier:* 1. *Risk:* A slow phone experience stays unknown.
- **Recommendation.** B is fine for now: few real networks are that large, and the desktop numbers show the main cost was removed. Choose A if you expect large projects to be edited on phones.
- **Records:** docs/roadmap.md §5 'Still to do by hand' (last sentence); docs/TSD.md §12 item 20; docs/history.md (the per-edit speed line, Session 13).

### OW-8. Three deploy checks the workflow cannot do: per-user limits, logs, real browsers

- **Consequence:** manual check pending; **likelihood:** occasional; **reproduced on main:** not attempted.
- **What happens.** The Deploy API workflow checks the server itself before and after it takes traffic (health, version, a solve, cross-site permission). Three checks need a second network or a person, and I found no record of them being done after the 2026-11-27 deploy. Check 3: the server limits each user to 60 solves a minute and one solve at a time, so it must tell users apart by their address. Google does not document where it puts that address, and only a live test shows whether each user gets their own allowance. If it is wrong, all users share one allowance and two people solving at once get 'server busy'. Check 4: the logs hold no user addresses. Check 5: in a real browser and on a phone, the site sends nothing to third parties and sets no cookies.
- **Example.** Check 3, which TSD §11.4 gives as commands: from one machine, send 60 empty solve requests in a minute. Each gets 400 (rejected, no solve). The 61st gets 429 (too many). Adding a made-up 'X-Forwarded-For' header must still get 429. Then, within the same minute, a request from another network (a phone on mobile data) must get 400, not 429. A 429 there means every user shares one allowance.
Check 4: in Google Cloud, Logging > Logs Explorer, project opensolve-pipe-api, run the query LOG_ID("run.googleapis.com/requests"). It should show nothing newer than the exclusion. The container log should show lines like - - "POST /api/v1/solve HTTP/1.1" 400, with no addresses.
Check 5: on a desktop browser, open the home page's example and solve. In the developer tools, the Network tab should show requests only to the site and the API, and Application > Storage should show no cookies. The page source of / and /p should contain no 'cloudflareinsights' or 'email-decode'. On a phone, open the example and solve.
- **Who would hit it.** Every user if check 3's assumption is wrong (the limits shared by everyone, 'server busy' whenever two people solve at once). Checks 4 and 5 protect every user's privacy.
- **The run.** Needs a second network, Google Cloud console access and a person's browser and phone. This session has no Google Cloud access and is read-only. I searched docs/history.md, docs/deployment.md and D25 and found no record of checks 3-5 after the deploy of 322db41. D25 says they 'stay by hand'.
- **Options:**
  - A. You run checks 3-5 as written in TSD §11.4: check 3 in Cloud Shell or a terminal, then from a phone hotspot; check 4 in Logs Explorer; check 5 in Chrome and on your phone *Cost:* small (about 15-20 minutes). *Tier:* 1 (record the result in history.md). *Risk:* None.
  - B. Split it: at your request, Claude runs check 3's first three steps and the curl-able parts of check 5 (page source, headers) from its cloud container. Within the same minute you press Solve on the site from your phone on mobile data: a normal result means separate allowances, 'too many requests' or 'busy' means shared. You still do check 4 and the browser half of check 5 *Cost:* small (about 5 minutes of yours). *Tier:* 1. *Risk:* Claude's container reaches the internet through one proxy address, so it cannot test IPv6. Its 61 requests briefly use up that address's allowance, which affects nobody else.
- **Recommendation.** B. Check 3 matters most, because only a live test can prove it. B cuts it to a tap on your phone at an agreed moment. Do checks 4 and 5 in the same sitting.
- **Records:** docs/TSD.md §11.4 items 3-5, §11.2 'Client address behind Google's front end'; docs/deployment.md step 3 'Check'; docs/decisions/D25-api-deploy-workflow.md (verified by the first runs: 'TSD §11.4 items 3 to 5 stay by hand'); docs/history.md lines 147-151.

### OW-9. GitHub does not stop a merge when CI fails

- **Consequence:** owner decision pending; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** The project's rule is that a pull request merges only when every CI job that ran has passed. GitHub does not enforce it. The protection on main ('Protect-main') requires a pull request and blocks force pushes and deletion, but it requires no passing checks. So a merge with a red check is possible: by you, or by Claude acting for you. Only you can change this, in the repository's settings. I confirmed today that it is still unenforced.
- **Example.** Today, through GitHub's API (read only), ruleset 26295576 'Protect-main' (active, on the default branch) has three rules: deletion, non_fast_forward, and pull_request with 0 approvals. It has no status-check rule and no bypass actors, and main has no older-style branch protection ('Branch not protected'). The check names GitHub shows on main's head da43e96 are 'API (pytest, ruff, mypy)', 'Web (svelte-check, lint, vitest)', 'End-to-end (Playwright, desktop + mobile)', 'History line' (skipped on pushes, run on pull requests), 'Changes', and twelve shard jobs.

What you would do (about a minute):
1. Go to github.com/ccirone2/opensolve-pipe > Settings > Rules > Rulesets > Protect-main.
2. Tick 'Require status checks to pass'.
3. Under Add checks, add the four checks 'API (pytest, ruff, mypy)', 'Web (svelte-check, lint, vitest)', 'End-to-end (Playwright, desktop + mobile)' and 'History line'.
4. Save.
- **Who would hit it.** Whoever merges a pull request (you, or Claude when you ask it to merge) while a check is red or still running.
- **The run.** gh api repos/ccirone2/opensolve-pipe/rulesets/26295576 returned rules [deletion, non_fast_forward, pull_request{required_approving_review_count:0}] and bypass_actors []: no required_status_checks rule. gh api repos/ccirone2/opensolve-pipe/branches/main/protection returned 404 'Branch not protected'. gh api .../commits/da43e96.../check-runs listed the check names above, all success except History line (skipped) and one unexpanded shard row (skipped).
- **Options:**
  - A. Require the four checks named above. Do not add the twelve shard jobs: the 'End-to-end (Playwright, desktop + mobile)' summary job stands for them all and passes when they are rightly skipped for a docs-only change (ci.yml lines 175-176) *Cost:* small (a minute in Settings; then Claude updates workflow.md §4 and D25's description of the ruleset). *Tier:* 1 (docs only; the setting itself is outside the code). *Risk:* If a CI job is later renamed, GitHub keeps waiting for the old name and blocks merges until the ruleset is updated. CI's required checks then gate every pull request, so a flaky end-to-end test blocks a merge until it is re-run.
  - B. Leave it as it is, resting on whoever merges reading the checks *Cost:* none. *Tier:* 1. *Risk:* A red merge can happen by mistake. Deploy API only deploys a main commit whose CI passed on main (D25), so a bad merge would not reach the server, but it would sit on main.
- **Recommendation.** A. It costs a minute and turns the written rule into one GitHub enforces. Tell Claude when it is done, so workflow.md §4 and D25 stop saying that GitHub does not enforce it.
- **Records:** docs/workflow.md §4 (second paragraph), §4.2; docs/decisions/D25-api-deploy-workflow.md 'What main controls'; docs/history.md line 165; /home/user/opensolve-pipe/.github/workflows/ci.yml jobs api, web, history, changes, e2e, e2e-result (lines 11-194).

### CS-11. Nothing is tested in Safari's engine

- **Consequence:** manual check pending; **likelihood:** common; **reproduced on main:** not attempted.
- **What happens.** Every automated browser test and every recorded browser check runs in Chromium (Chrome's engine). WebKit, the engine of Safari and of every browser on an iPhone, has never been run. Phone performance has only been estimated, for example the export's 1-2 s for the largest workbook. Per-edit speed in Safari and on a real phone is listed as not measured. Defects specific to iPhones would go unseen, and phones are meant to be equal to desktop (GOALS §4.7).
- **Example.** A user opens a shared link on an iPhone. Layout budgets, focus handling and the scroll-anchoring behaviour that the Pumps tab relies on (library-facts.md, Chromium) were measured only in Chromium.
- **Who would hit it.** iPhone users and other Safari users.
- **The run.** Not attempted: no WebKit or real phone here. The records: pumps-nits.md §11.6 ('WebKit: only Chromium is installed here; every browser check is Chromium'); roadmap §5 ('Per-edit speed … on a real phone, in Firefox and in Safari: not measured'); export.md §9 ('Phone performance is estimated, not measured').
- **Options:**
  - The owner does a short by-hand pass on an iPhone (open an example, solve, Pumps tab, share, export) *Cost:* small. *Tier:* -. *Risk:* None. It finds only what one person sees.
  - Add a WebKit project to CI, perhaps a smoke subset at first *Cost:* medium to large (layout budgets measured in Chromium may need triage). *Tier:* 3 (what CI runs on main). *Risk:* Longer CI. Budget tests may fail on font metrics rather than real defects.
- **Recommendation.** Start with the owner's iPhone pass, alongside the export's by-hand checks (covered by another group). Add WebKit to CI only if the pass finds engine-specific defects.
- **Records:** docs/proposals/pumps-nits.md §11.6; docs/roadmap.md §5 (Still to do by hand); docs/proposals/export.md §9 (Risks); docs/library-facts.md, Chromium.

### CS-13. CI's docs-only shortcut has not yet run on a real docs pull request

- **Consequence:** manual check pending; **likelihood:** only in tests; **reproduced on main:** no, could not reproduce.
- **What happens.** Since 2026-11-27, CI skips the 40-minute browser suite for a change that touches only docs. The record says the skip would first be exercised on GitHub by a docs-only change after that merge. None has happened yet. One run shows the skip firing when nothing at all differed from main, which is consistent but is not a docs-only change.
- **Example.** The next pull request that changes only files under docs/ should show the end-to-end shards as skipped and the end-to-end result job as passed.
- **Who would hit it.** Development only.
- **The run.** Read-only GitHub API: CI run 46095157416 (a push of claude/kind-wozniak-oui7h9 at da43e96, the same tree as main) had Changes success, End-to-end (Playwright, desktop + mobile) success and the shard jobs skipped. The latest main run 46095139219 at da43e96 passed. No docs-only pull request run exists yet.
- **Options:**
  - Look at the first docs-only pull request's checks (for example the one that records these loose ends) *Cost:* small. *Tier:* -. *Risk:* None.
- **Recommendation.** Check it on the next docs-only pull request and note the result in history.md.
- **Records:** docs/history.md, Session 18, gates by risk tier, CI paragraph; docs/workflow.md §4.2.

## 7. Leave as they are, with the records corrected

Inputs far outside engineering practice, layouts no project was found to use, or work that belongs in a later change of the same feature. Where a record is wrong or stale, the correction is a tier-1 docs change.

### SC-1. The flow limit is placed too high with crossed FCVs in series

- **Consequence:** value missing; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** To find the flow limit, the API looks at two places to "cut" the network: just past the pump's discharge, and just before its suction. It adds up what the FCVs or one-way elements across each cut can pass, and takes the smaller total. That total is always a safe upper bound, but it is not always the true largest flow. The true largest flow is lower when each of two parallel paths has two FCVs in series and the tighter FCV is upstream on one path and downstream on the other. The API then solves its extra point at the wrong flow, where nothing can flow, so that point has no head. No point is solved at the true limit, so the chart never shows the vertical there. Every grid point between the true limit and the computed one is a gap. The operating point itself is correct.
- **Example.** Reservoir R1 (2 m) feeds pump PU (curve 45 m at 0, 44 m at 10 L/s, 41 m at 20 L/s, 35.5 m at 30 L/s, 27 m at 40 L/s). PU feeds a tee that splits into two paths, which rejoin at a second tee and run to reservoir R2 (10 m). Every pipe is 10 m long. Path A has FCV A1 (1 L/s) followed by FCV A2 (10 L/s). Path B has FCV B1 (10 L/s) followed by FCV B2 (1 L/s). At most 1 + 1 = 2 L/s can pass, but the API computes 11 L/s. The solve puts the pump at 2.0 L/s and 44.94 m. The pump chart's system curve has two points, 8.00 m at 0 and 8.01 m at 1.2 L/s, and then nothing. From 2.4 to 10.8 L/s every point says "no steady state found that carries this flow: the status rules close FCV 'A1' and FCV 'B2'…". The extra point at 11 L/s says "not converged: statuses oscillate between states already solved (components: A1, B1)". From 12 L/s up the points say no steady state carries the flow, quoting 11 L/s. The operating point sits about 37 m above the curve's last point, and the two curves never cross on screen. Asked for a point at exactly 2 L/s, the API already gives the right answer: B2 sits at its setpoint, and any head from 8.03 m up holds, which would draw the vertical through the operating point.
- **Who would hit it.** Users whose networks have two flow control valves in series on each of two parallel paths, with the tighter valve upstream on one path and downstream on the other (or a similar mix of FCVs and one-way elements at different depths). One FCV per path, or FCVs only on a common header, give the right limit.
- **The run.** A scratch script, system-curve-limits/sub1_crossed.py (run from apps/api with `uv run python`). It builds the unit tests' `_crossed()` network and posts it to /api/v1/system-curve and /api/v1/solve through TestClient. Output: `flow_limit: 0.011 elements: [('A1', 0.001), ('B1', 0.01)]`; the grid's points are 0.0 → 8.0 m and 0.0012 → 8.01320715104456 m; 0.0024 to 0.0108 → no_steady_state_found ['A1','B2']; 0.012 and up → beyond_limit, limitFlow 0.011. limitPoints: `{'flow': 0.011, 'reason': 'not_converged', 'componentIds': ['A1','B1']}`. The solve's pumpResults PU: operatingFlow 0.0019999999999999814, operatingHead 44.94400000000001. A point alone at 0.002 m³/s gives reason valve_at_switch for B2, open_head 8.032682566244759, bound 'lower'. A grid of 0 to 0.004 m³/s in 5 points gives the same at its 0.002 point.
- **Options:**
  - True maximum flow everywhere: compute flow_limit by the augmenting-path maximum-flow method on the links it already builds, with the assigned flows as one extra supply and one extra demand, and compute the floor the same way *Cost:* large (several days, including D13's acceptance proof: the corpus comparison, the /system-curve corpus comparison and the three fuzz profiles, a METHOD_VERSION bump, and an independently written reference case). *Tier:* 3. *Risk:* It changes the reasons and messages of grid points: 'no steady state found' becomes 'no steady state carries this flow'. If the capacity model were wrong anywhere, a flow that can really be carried would be labelled beyond the limit and lose the retries that might find its head. The tolerance margin would also have to be counted on the new cut.
  - Place the extra point only: use the true maximum flow just to choose where the extra point is solved (limit_flows), and leave flow_limit and every grid label unchanged *Cost:* medium (about a day, plus a reference case and the /system-curve corpus comparison). *Tier:* 3. *Risk:* One response would then quote two limits: the grid points say 11 L/s while the vertical stands at 2 L/s. The messages would need to explain that. The floor would still use the two simple cuts.
  - Leave it as recorded *Cost:* none. *Tier:* -. *Risk:* In such a network the system curve stops short of the operating point. The gaps say 'no steady state found' rather than naming the true limit. Nothing wrong is claimed, and the operating point and its trace are right.
- **Recommendation.** Leave it for now. The layout is unusual, the solve's own results are right, and since 1.6.2 the API no longer draws a false vertical here (the review's AC-1 fix). Revisit if a real project shows this. If it is done, the 'place the extra point only' option gets the chart right without touching grid labels.
- **Records:** docs/roadmap.md §2, 'System curves' limits', first sub-item (line 35); docs/proposals/open-defects-2.md §7, 'The system curve's true flow limit' (line 115); docs/proposals/open-defects-2.md §9, the review fixes' AC-1 item (line 269); docs/history.md Session 16 (AC-1); apps/api/src/opensolve_pipe/services/solver/system_curve.py flow_limit (line 298), _held_open_switch (line 737), limit_flows (line 1038); apps/api/tests/unit/test_system_curve_limit_points.py _crossed() and test_a_held_open_fcv_above_its_setpoint_is_no_other_valve_s_switch.

### SC-2. Floor equal to the limit: one point, labelled not converged

- **Consequence:** misleading or vague message; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** Sometimes the least flow the pump must pass (the floor) equals the most it can pass (the limit), so exactly one flow is possible. Both FCVs then sit exactly at their setpoints. Either one could throttle: one raises the head the pump must add, the other lowers it. So any head at all holds at that flow, bounded neither above nor below. To find a valve at its setpoint, the API holds one FCV fully open at a time, and it only knows two kinds of range: 'this head or more' and 'this head or less'. Holding one FCV open at a time finds nothing here; holding both open together does. So the point comes back 'not converged', with a message that describes the starting valve statuses rather than the real situation. On the chart it is a gap at the one flow the network can carry.
- **Example.** Reservoir R1 (20 m) feeds FCV VS (setpoint 15 L/s), then pump PU, then tee T1, then a fixed demand D1 of 20 L/s. A second reservoir R0 (20 m) feeds T1 through FCV V1 (5 L/s). All pipes are 10 m. The pump must pass at least 20 − 5 = 15 L/s, and VS lets through at most 15 L/s, so 15 L/s is the only possible flow. Every grid point says 'below the floor' or 'beyond the limit'. The one extra point, at 15 L/s, says "not converged: in these statuses only FCV 'V1' can connect assigned-flow node(s) 'D1' to a reservoir or reference node, and they take 0.02 m³/s through it, more than its setpoint (0.005 m³/s)…". With VS and V1 held open together, the network carries the flow: VS passes 15 L/s, V1 5 L/s, and the head across the pump is 0.95 m with both fully open. The case's own solve does not converge either: it shows the NOT_CONVERGED flag and the same message. So the user sees no operating point, and a system curve with nothing drawn.
- **Who would hit it.** Users whose FCV setpoints exactly balance a fixed demand, for example a supply FCV set to exactly the demand minus a bypass FCV's setpoint, so that one flow is the only possibility.
- **The run.** Scratch scripts system-curve-limits/sub23_floor.py, sub2_more.py and sub2_held.py, on `_floor(suction_fcv=0.015)`. flow_limit gives limit 0.015 (VS) and floor 0.015 (V1 0.005). Every grid point from 0.012 to 0.0228 m³/s is below_floor or beyond_limit. limitPoints: `{'flow': 0.015, 'reason': 'not_converged', 'componentIds': ['V1'], ...}`. Holding VS and V1 open together: `converged True VS 0.015 V1 0.004999999999999998`, read as head 0.951464421023104. Holding V1 alone: starved, with VS closed. Holding VS alone: not converged. The /api/v1/solve of the same project: converged False, flags ['NO_VAPOR_PRESSURE', 'NOT_CONVERGED'], oscillating ['V1'].
- **Options:**
  - Hold every FCV of both cuts open together when the floor equals the limit, and add a third kind of range meaning 'any head holds here' (a new openHeadBound value), which the charts would draw as a full-height vertical line with its own words *Cost:* medium (one to two days: the model and generated types, the web's line, words and export, and a reference case). *Tier:* 3. *Risk:* A new range value reaches every reader of openHeadBound: the pump chart, the group chart, the C2 system duty check, the rings' claims and the export.
  - Words only: at a floor equal to the limit, replace the 'not converged' message with an honest one: this is the only flow the network can carry, and the head there is undetermined. No vertical is drawn. *Cost:* small to medium (about half a day). *Tier:* 3. *Risk:* It still needs a reason code that the web's reason words know. It is less informative than drawing the line.
  - Leave it as recorded *Cost:* none. *Tier:* -. *Risk:* A misleading message on one point, in a network whose own solve already fails to converge.
- **Recommendation.** Leave it. It needs an exact balance of setpoints, and in the reproduced network the case's own solve does not converge either. The user is already told the case has no result, and a better system-curve point would not change what they do next.
- **Records:** docs/roadmap.md §2, 'System curves' limits', second sub-item (line 36); docs/proposals/open-defects-2.md §7, 'A floor equal to the limit' (line 120); docs/proposals/open-defects-2.md §8, the skeptic's findings after the review fixes; apps/api/src/opensolve_pipe/services/solver/system_curve.py _held_open_switch (line 737), limit_flows (line 1038); apps/api/tests/unit/test_system_curve_limit_points.py test_a_floor_equal_to_the_limit_is_one_limit_point.

### SB-1. Nearly closed valve to a dead end gives no solution

- **Consequence:** no solution where one exists; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** Suppose a valve is given a tiny Cv to make it act closed, and the pipe beyond it ends at a dead end or an assigned flow. The solver adds up how easily each element at a junction passes a flow change. Next to the pipe, the valve's share is about 10^16 times smaller, so it disappears in the computer's last-digit rounding. The part of the network beyond the valve then has nothing tying it to a fixed head, and the Newton step cannot be solved. The answer does exist: with a dead end it is simply no flow and the reservoir's head everywhere. Since 1.6.2 the message names the valve. The solve still fails, and the user gets no results. The record states the threshold as 'above about 3·10^19 s²/m⁵', but that is only the first-iteration threshold for one test network (0.1 m bore, 10 m pipes). Whole solves fail at much lower values, the threshold grows smaller with larger bores and shorter pipes beyond the valve, and whether a given value fails depends on the iteration path.
- **Example.** Network: reservoir R1 at 10 m, then 10 m of 1 m bore pipe, then gate valve V1 (1 m bore) entered as Cv 0.025, then 1 m of pipe, then a plug. Water-like fluid (998 kg/m³, 1 mPa·s). Cv 0.025 is K 3.39·10^12 (fluids' Cv_to_K), a loss coefficient of 2.8·10^11 s²/m⁵. For comparison, the same valve fully open has K 0.0832 (Crane via fluids), which is Cv 160,322. What the user sees: the red 'Did not converge' card with 'the linear system could not be solved (singular matrix): in Newton iteration 3, at the flows after iteration 2, the weight 1/(dh/dQ) of 'V1' ... is lost in rounding ...', V1 listed under 'Lost in rounding in the Newton step', and no flows or heads. On a 0.1 m valve with 10 m of pipe to the plug, the first failing Cv is about 9·10⁻⁶. The same network with Cv 0.02 or 0.01 converges.
- **Who would hit it.** A user who models a closed or leaking-closed valve by typing a very small Cv or Kv instead of setting its status to Isolated, upstream of a dead end or an assigned flow. The schema accepts any positive Cv (models/components.py line 72: gt=0). A K entry cannot reach it, since K is capped at 1e7 (models/base.py line 41).
- **The run.** Scripts in schema-bounds/ (item1_singular.py, item1_sample.py, item1_threshold.py, item1_geometry.py, item1_geometry2.py, item1_big.py), run with cd apps/api && uv run python <script>, using the test module's bridge() network (R1 10 m -> 10 m of 0.1 m pipe -> V1 -> 10 m pipe -> plug or 0.01 m³/s assigned flow).

First-step threshold: c* = 3.0100583407992963e19 s²/m⁵, which is K 3.64e16 and Cv 2.42e-6 on the 0.1 m valve.

Whole solves, plug end:
- c 1e18 and 1.47e18: converge.
- c 2.15e18 (Cv 9.06e-6) and 3.16e18: singular in Newton iteration 3.
- c 4.64e18 and 6.81e18: converge.
- c 1e19 and above: fail.

Whole solves, assigned-flow end: converge up to c 1e19; fail from c 1.47e19 (Cv 3.47e-6).

Just below c* (c*(1-1e-9)) the first step is taken, but the whole solve still fails in iteration 3.

When the plug-end solve does converge, the answer is flow 0 and every head 10.0 m. That is the steady state the failing cases also have.

Largest grid Cv that fails, plug end (a 61-point grid of Cv from 100 down to 1e-4, or 41 points from 1e-3 down to 1e-7):
- 0.1 m valve, 1 m pipe beyond: 2.5e-5
- 0.3 m valve, 1 m beyond: 2.5e-4
- 0.6 m valve, 1 m beyond: 3.2e-3
- 1 m valve, 1 m beyond: 0.025, c 2.8e11 s²/m⁵

On the 1 m valve, Cv 0.1, 0.05, 0.02 and 0.01 all converge.
- **Options:**
  - Correct the record only: say c* is one network's first-step threshold, and record the measured reach (whole solves fail from about 2·10^18 s²/m⁵ on 0.1 m with 10 m pipes, and from 2.8·10^11 s²/m⁵ on a 1 m valve with 1 m of pipe), path-dependent and not monotone *Cost:* small. *Tier:* 1. *Risk:* None; docs only (roadmap §2, TSD §12 item 19, open-defects-2 §7).
  - A hint in the web's convergence card: when singularStepAt names a valve, suggest setting its status to Isolated to model a closed valve *Cost:* small. *Tier:* 1 (wording in one component); 2 if it adds an action that changes the valve's status. *Risk:* Low. The hint could be wrong for a lost weight on equipment or a fitting, so it should apply only when the named element is a valve.
  - The recorded solver fix (open-defects-2 §7 'A2b's step'): only when the step is singular and a cut-off part is found, take the bridge's flow change from the far part's continuity and the far part's head from the bridge's own energy equation *Cost:* large. *Tier:* 3. *Risk:* Changes the solver's failure path. Converged solves should be untouched, but it needs a reference case, the corpus comparison and D13's three fuzz profiles (the 57 singular inner steps in the fuzz seeds would take the new path).
- **Recommendation.** Correct the record now (option 1). The current figure of about 3·10^19 understates how easily this is reached on large valves. Add the web hint (option 2) if the owner thinks users will type tiny Cv values to close valves, since Isolated already gives the right answer. Leave the solver fix (option 3) until a real project needs it. Its cost is the full tier-3 proof, and the realistic path has a one-click workaround.
- **Records:** docs/roadmap.md §2, 'Inputs at the schema's bounds', first sub-item (line 29); docs/proposals/open-defects-2.md §7 'A2b's step' (line 113); §9 item 4 (A2b: closed form c*, 'The step itself is unchanged'); docs/TSD.md §12 item 19 (d) 'Not done: the singular step itself'; docs/history.md Session 16 (f56a83d A2b); apps/api/tests/unit/test_singular_step.py (module docstring; test_the_first_step_is_singular_exactly_past_the_closed_form_threshold, line 250); apps/api/src/opensolve_pipe/models/components.py line 72; models/base.py line 41.

### SB-2. Plain 'singular matrix' message can be the final result

- **Consequence:** misleading or vague message; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** Since 1.6.2, a failed Newton step is explained by naming the element whose share was lost in rounding. The test only checks whether that share disappears when it is added to the others at its junction. Sometimes the share survives the addition by a few last digits, but the matrix is still singular a step later, when the solver eliminates the junctions one by one. Then no element is named, and the user gets only 'the linear system could not be solved (singular matrix)'. The record says 31 of the 57 such steps in the fuzz seeds keep this plain message and that 'none of them [is] a final result'. That holds for the fuzz seeds. The simple valve-to-dead-end network of SB-1 does end on the plain message.
- **Example.** Network: R1 at 10 m, then 10 m of 0.1 m pipe, then gate valve V1 (0.1 m) at Cv 4.204·10⁻⁶ (a loss coefficient of 1·10^19 s²/m⁵), then 10 m of pipe, then a plug. Water-like fluid. What the user sees: the red 'Did not converge' card with only 'the linear system could not be solved (singular matrix)', and the largest continuity error at V1's outlet and the largest energy error on V1. No element is listed as lost in rounding and there are no results. At the failing step, V1's share is 4.65 last-digit units of the pipe's share. The sum keeps it, so the rule finds nothing.
- **Who would hit it.** The same users as SB-1: a valve with a very small Cv or Kv upstream of a dead end or an assigned flow, at a value where the failure appears in a later iteration. It may also come from an active PRV or PSV, whose coupling the rule does not examine (gga.py docstring); no example of that was built here.
- **The run.** Scripts in schema-bounds/.

item2_plain.py output:
- message: 'the linear system could not be solved (singular matrix)'
- flag NOT_CONVERGED: {'maxContinuityResidualAt': 'V1:outlet', 'maxEnergyResidualAt': 'V1'}, with no singularStepAt
- the inner solve takes 4 iterations, then the 5th step is singular

item2_weights.py, at the flows after iteration 4 (pipe L2 0.0012555 m³/s, valve 0.00038726 m³/s):
- pipe share 0.19268, valve share 1.291e-16
- valve share / last-digit unit of the pipe share = 4.65
- lost in the sum: False

The gga.py lost_weights docstring (lines 390-417) says a singularity from 'a weight lost only in a partial sum' or from the PRV/PSV coupling is not found.
- **Options:**
  - Correct the record: 'none a final result' is true of the 56 fuzz seeds only; a plain series network (Cv 4.2e-6 on 0.1 m to a plug) ends on the plain message *Cost:* small. *Tier:* 1. *Risk:* None; docs only.
  - Web wording for the plain message: explain in plain words that a part of the network is probably joined to the rest only through an element whose loss is so large that rounding loses it, and point at the largest-error location already shown *Cost:* small. *Tier:* 1. *Risk:* Low. The explanation would be a 'probably', and it could be wrong for the PRV/PSV coupling.
  - Widen the API's rule: when SciPy reports a singular step and no weight is lost in the sum, name the link whose share is smallest relative to its junction's sum (or one within a few last-digit units of it), worded as the likely cause *Cost:* medium. *Tier:* 3 (the solve's error messages and flag details). *Risk:* A heuristic could name the wrong link. Message and flag changes need the corpus comparison and the fuzz records (1.6.2's message changes went through D13's proof) and probably a METHOD_VERSION entry.
- **Recommendation.** Correct the record (option 1). If SB-1's solver fix is ever done, it removes most of these cases at the cause, so a better API message (option 3) is worth building only as part of that work. Option 2 is a cheap way to make the bare message less mysterious meanwhile.
- **Records:** docs/roadmap.md §2, 'Inputs at the schema's bounds', second sub-item (line 30); docs/proposals/open-defects-2.md §9 item 4 ('of the 57 singular inner steps of the designer's 56 seeds, 26 are named and 31 keep the plain message, none of them a final result'); docs/TSD.md §12 item 19 (d) 'Not done: ... the 31 of 57 inner singular steps'; apps/api/src/opensolve_pipe/services/solver/gga.py lost_weights docstring, lines 390-417; apps/web/src/lib/components/results/ConvergenceStatus.svelte (what the card shows).

### SB-3. Check valve whose cracking head overflows: no solution

- **Consequence:** no solution where one exists; **likelihood:** extreme inputs only; **reproduced on main:** yes.
- **What happens.** A check valve's cracking pressure is turned into a head by dividing by density times g. If the density is absurdly small, that head is beyond the largest number the computer can hold. The right answer is simple: the valve can never crack open, so it stays closed with no flow. With the check valve on Active, the solver stops at its first step whichever way the pressure pushes. The message says 'not a finite number in the law of V1', which is the right valve, but it quotes the valve's ordinary loss coefficient (1346 s²/m⁵) rather than the cracking pressure, so it points the user at the wrong input. New measurement (the record said this was not measured): the same valve solves when Locked closed, Locked open, or closed off between two isolated gate valves.
- **Example.** Network: R1 at 20 m, then 10 m of 0.1 m pipe, then check valve V1 (0.1 m, cracking pressure 1·10^6 Pa, Active), then 10 m of pipe, then R2 at 1 m. Custom fluid of density 5·10⁻³⁰⁵ kg/m³. What the user sees: 'Did not converge' with 'the iteration diverged (non-finite head loss): not a finite number in the law of 'V1' (head loss at a flow of 0.00239 m³/s; loss coefficient K/(2 g A²) = 1346.32 s²/m⁵)'. Reversing the reservoirs (R1 at 1 m, R2 at 20 m), where the valve must simply stay shut, gives the same message. The same forward network in an air-like fluid (1.2 kg/m³) converges with V1 closed.

Density at which the cracking head stops being a finite number (bisected):
- cracking 1·10^3 Pa: at or below 5.67·10⁻³⁰⁷ kg/m³
- cracking 1·10^5 Pa: at or below 5.67·10⁻³⁰⁵ kg/m³
- cracking 1·10^7 Pa, the schema's maximum: at or below 5.67·10⁻³⁰³ kg/m³

No real fluid is anywhere near these densities.
- **Who would hit it.** Only someone who types a custom fluid density below about 10⁻³⁰² kg/m³. The schema accepts any density above 0 (models/fluids.py line 45: gt=0). No engineering fluid comes close.
- **The run.** Script: schema-bounds/items345.py. Fluid 5e-305 kg/m³, cracking pressure 1e6 Pa.

Results:
- 3a forward, Active: converged=False, 0 inner iterations; NOT_CONVERGED nonFiniteLawAt 'V1', nonFiniteLawCoefficient 1346.32
- 3b reverse, Active: converged=False, same message
- 3c Locked closed: converged=True, 2 iterations, V1 closed, flow 0.0
- 3d Locked open: converged=True, 52 iterations
- 3e between two isolated gate valves: converged=True, 2 iterations
- 3f forward, 1.2 kg/m³ and 1.8e-5 Pa·s: converged=True, V1 closed, flow 0.0

The edge densities come from test_boundary_head.edge() (bisection over the doubles with fluids' g).
- **Options:**
  - Leave it, and record today's measurements (Active fails in both flow directions; Locked closed, Locked open and closed-off solve; the message quotes the loss coefficient, not the cracking pressure) *Cost:* small. *Tier:* 1. *Risk:* None.
  - Refuse an Active check valve whose crackingPressure/(ρg) is not a finite number before the solve, as reservoirs are refused since 1.6.2 (BOUNDARY_HEAD_OUT_OF_RANGE), with web words *Cost:* medium. *Tier:* 3 (a project that gets a 200 today would get a 422; METHOD_VERSION entry, corpus comparison). *Risk:* Refusing only Active valves keeps the Locked and closed-off cases solving. It is one more refusal path to test and word in the web.
  - Make the solver hold such a valve closed (an infinite cracking head can never be exceeded) *Cost:* medium. *Tier:* 3 (status logic; differential fuzz under D13). *Risk:* Touches the status rules for a case no real fluid reaches.
- **Recommendation.** Leave it (option 1) and update the record with the new measurements. No real fluid has these densities. The valve is already named, and Locked closed gives the right answer. If the owner wants the schema-bound cases closed off for good, do option 2 together with SB-4 in one tier-3 round, since both are the same refusal pattern.
- **Records:** docs/roadmap.md §2, 'Inputs at the schema's bounds', third sub-item (line 31); docs/proposals/open-defects-2.md §7 'A check valve's cracking head' (line 117); docs/TSD.md §12 item 19 (d) 'an active check valve's cracking head that overflows (named as its law, not refused)'; apps/api/tests/unit/test_boundary_head.py test_a_check_valve_whose_cracking_head_overflows_is_named_not_refused (line 536); apps/api/src/opensolve_pipe/models/components.py lines 322-323 (crackingPressure 0 to 1e7 Pa); models/fluids.py line 45 (density gt=0, le=3e4).

### SB-4. PRV/PSV held head overflow reported as 'no steady state'

- **Consequence:** misleading or vague message; **likelihood:** extreme inputs only; **reproduced on main:** yes.
- **What happens.** An active PRV holds the head at its outlet, and an active PSV holds the head at its inlet. That held head is the elevation plus the setpoint divided by density times g. With an absurdly small density, it is beyond the largest number the computer can hold. Where the network needs the valve active (a PRV feeding an assigned-flow demand, or a PSV after an assigned supply), the active solve fails at once. The status logic then falls back to the valve closed and reports that no reservoir reaches the assigned flow. The real cause, a held head the solver cannot represent, is not mentioned. The same network in water solves normally with the PRV active.
- **Example.** Network: R1 at 10 m, then 10 m of 0.1 m pipe, then PRV V1 (setpoint −1·10^5 Pa(g), Active), then 10 m of pipe, then assigned flow AF1 taking 0.01 m³/s out. Custom fluid of 5·10⁻³⁰⁵ kg/m³. What the user sees: 'Did not converge' with 'no reservoir or reference node reaches assigned-flow node 'AF1' (takes 0.01 m³/s out of the network) through open elements, so no steady state carries that flow ...; closed around it: PRV 'V1' (closed by its status rule: a PRV passes no reverse flow, and no flow while the pressure its outlet side needs is above its setting)'. The NOT_CONVERGED details are empty. The same network in water (998 kg/m³) converges in 2 iterations with V1 active passing 0.01 m³/s. A PSV at 1·10^8 Pa(g) after a 0.01 m³/s supply, in 5·10⁻³⁰² kg/m³, gives the matching PSV message.

Density at which the held head stops being a finite number (bisected):
- setpoint ±1·10^5 Pa(g): at or below 5.67·10⁻³⁰⁵ kg/m³
- setpoint 1·10^8 Pa(g), the maximum: at or below 5.67·10⁻³⁰² kg/m³
- **Who would hit it.** Only a custom fluid density below about 10⁻³⁰¹ kg/m³ (the schema accepts any density above 0). No engineering fluid comes close.
- **The run.** Script: schema-bounds/items345.py.

Results:
- 4a PRV −1e5 Pa(g), 5e-305 kg/m³: converged=False, inner/outer 4/3, message as quoted, NOT_CONVERGED details {}
- 4b PSV 1e8 Pa(g), 5e-302 kg/m³: converged=False, inner/outer 4/3, 'closed around it: PSV 'V1' (closed by its status rule ...)'
- 4c same PRV network in water: converged=True, 2/1, V1 ('active', 0.01)

The record says the same verdict holds on 8535900; that was not re-run here. Between two reservoirs the valve settles open or closed and the case converges, which test_boundary_head.py line 496 pins.
- **Options:**
  - Leave it, with the record as it stands (it already describes this correctly) *Cost:* small. *Tier:* 1. *Risk:* None.
  - Refuse a PRV or PSV whose held head z + p_set/(ρg) is not a finite number before the solve, with the same words as BOUNDARY_HEAD_OUT_OF_RANGE *Cost:* medium. *Tier:* 3 (a 200 becomes a 422 for the open/closed cases that converge today; the pinned regression test would change by owner decision; METHOD_VERSION entry, corpus comparison). *Risk:* Simple and consistent with reservoirs. It refuses cases that solve today between two reservoirs, so it needs the owner's decision.
  - The recorded outer-loop fix: when the active solve fails on a non-finite held head, report that failure (the held head, or the energy balance at the held node) instead of the closed fallback's 'no steady state' *Cost:* medium. *Tier:* 3 (status logic: D13's proof, the three fuzz profiles). *Risk:* Changes status-loop reporting for every PRV/PSV divergence, not just this one, so it needs the full fuzz proof.
- **Recommendation.** Leave it. It needs a density no fluid has, and the message at least names the right valve. If the owner wants a schema-bounds round, option 2 is the simpler and safer fix, and it pairs with SB-3. Option 3 touches the status loop for a case no project reaches.
- **Records:** docs/roadmap.md §2, 'Inputs at the schema's bounds', fourth sub-item (line 32); docs/proposals/open-defects-2.md §7 'An active PRV's or PSV's held head that overflows' (line 119); §8 review record AS-1; docs/history.md Session 16 ('The other three (AS-1, AO-1, AO-2) had their records corrected in 7623637'); apps/api/tests/unit/test_boundary_head.py test_a_prv_or_psv_whose_setpoint_head_overflows_is_not_refused_and_converges_open_or_closed (line 496); apps/api/src/opensolve_pipe/models/components.py line 341 (setpoint −1e5 to 1e8).

### SB-5. Orifice plate at the refusal's exact edge (AO-2)

- **Consequence:** none found; **likelihood:** extreme inputs only; **reproduced on main:** yes.
- **What happens.** A rule refuses an orifice plate whose loss factor, K/(2gA²), cannot be a finite number at the smallest discharge coefficient C its law can use. The rule computes that smallest C one way (a transcription of ISO 5167-2's equation), and the loss law computes it another way (through fluids). The two can differ in the last digit, so at the exact edge a plate is accepted although its law can hold C one last-digit unit lower, where the loss factor is infinite. This happens only for an entered C around 10⁻¹⁵⁴, against a real plate's C of about 0.6 to 0.8. Measured: in water the solve stops at its first step and names the plate. In a very viscous liquid it converges at zero flow. The record puts the true flow at about 10⁻¹⁵⁴ m³/s, so zero is the same answer under D6. No wrong value or misleading message was found. The only effect is that the user gets a 'did not converge' naming the plate instead of an 'out of range' refusal.
- **Example.** Network: R1 at 10 m, then 10 m of 0.1 m pipe, then orifice plate O1 (bore 0.097 m, flange taps, entered C 6.212305790600638·10⁻¹⁵⁴), then 10 m of pipe, then R2 at 0 m. For comparison, ISO 5167-2's C for this plate is 0.7716, from fluids' Reader-Harris/Gallagher at 1 kg/s of water. In water the user sees 'Did not converge' with 'the iteration diverged (non-finite head loss): not a finite number in the law of 'O1' (slope dh/dQ at a flow of 0.00239 m³/s; loss coefficient K/(2 g A²) = 1.76011e+308 s²/m⁵)'. In 1000 kg/m³ and 10 Pa·s it converges in 505 iterations with flow 0.0 and a head loss of 10.0 m across the plate. With C 0.6 in water the same line converges in 9 iterations.
- **Who would hit it.** Only someone who types a discharge coefficient around 10⁻¹⁵⁴ on a plate at the very edge of the refusal. The schema accepts any C above 0 and up to 1 (models/components.py line 488). The record found 10 such edges among 449.
- **The run.** Script: schema-bounds/items345.py, using test_orifice_least_c._plate_line.

Results:
- water: converged=False, 0 inner iterations; NOT_CONVERGED nonFiniteLawAt 'O1', nonFiniteLawCoefficient 1.7601066922884978e+308
- 1000 kg/m³, 10 Pa·s: converged=True, 505 iterations; orifice result flow 0.0, head_loss 10.0, discharge_coefficient 7.718e-154, loss_coefficient 2.17e305, differential_pressure nan
- C 0.6 in water: converged=True, 9 iterations

fluids.flow_meter.C_Reader_Harris_Gallagher(0.1, 0.097, 998, 1e-3, 1.0, taps='flange') = 0.7716.
- **Options:**
  - Leave it; the record already describes it accurately *Cost:* small. *Tier:* 1. *Risk:* None.
  - Add a margin of a few last-digit units to the refusal's second stage, with a written bound on the rounding of the two ways of computing C (as the record suggests, D8) *Cost:* medium. *Tier:* 3 (a plate accepted today would be refused; reference cases and corpus comparison). *Risk:* The margin needs a derived bound, not a guessed one. Without that it would break the no-uncited-numbers rule.
  - Compute fluids' own C inside the refusal so both sides use the same arithmetic *Cost:* medium. *Tier:* 3. *Risk:* More code in the refusal path. It changes which edge plates are refused.
- **Recommendation.** Leave it. The input is absurd, the user is never shown a wrong number, and every failure names the plate. The fixes cost a tier-3 round for no practical gain.
- **Records:** docs/roadmap.md §2, 'Inputs at the schema's bounds', fifth sub-item (line 33); docs/proposals/open-defects-2.md §7 'Rule (d)'s stage 2 at the exact edge' (line 116); §9 item 2 (A1: 'At 10 of the 449 edges ... flange taps, D 0.1 m, bore 0.097 m, C_e 6.212305790600638·10⁻¹⁵⁴'); docs/proposals/open-defects-2.md §8 review record AO-2; docs/TSD.md §12 item 19 (b), rule (d); apps/api/tests/unit/test_orifice_least_c.py (_plate_line, line 157).

### OP-1. Meter reading blank at a reported zero flow

- **Consequence:** value missing; **likelihood:** extreme inputs only; **reproduced on main:** yes.
- **What happens.** A plate with taps reports a meter reading: the differential pressure between its taps. For any real discharge coefficient C, a plate on a branch with no flow correctly reads 0 Pa. The reading is blank only when someone enters an absurdly small C: below about 9×10⁻¹⁵³ for a 0.1 m bore in a 0.2 m pipe in a water-density liquid. The formula (1 − β⁴)/(C²β⁴) × ρ × v|v|/2 is multiplied left to right. Its first part times the density already passes the largest number the computer can hold, so it becomes 'infinity', and infinity times a zero velocity gives no number. The API sends that as null. The table then shows the same dash it shows for a plate without taps, and the trace drops the reading line with no note saying why. Such a plate is not really at zero flow. It takes the whole available head at about 2.4×10⁻¹⁵⁴ m³/s, a flow the solver reports as 0. At that flow the true reading is about the plate's whole permanent loss, 97,953 Pa in the example, not 0.
- **Example.** Realistic, works: R1 (level 10 m) → 100 m of 0.1 m pipe → tee T1 → 100 m → R2 (level 0 m). From T1's branch a spur runs 10 m → plate O1 (D 0.1 m, bore 0.05 m, flange taps, ISO's C) → 10 m → a plug. Water. Result: flow 0, differentialPressure 0.0 Pa, trace line 'Differential pressure Δp at the taps (the reading) = 0.0 Pa'. An entered C of 0.61 at corner taps gives the same. Extreme, blank: R1 (10 m) → 10 m of 0.2 m pipe → O1 (bore 0.1 m, flange taps, entered C 2.0773717524832402×10⁻¹⁵³, D20's documented plate) → 10 m → R2 (0 m), in a liquid of 1000 kg/m³ and 10 Pa·s, max iterations 1000. It converges in 507 iterations: flow 0.0, head loss 10.0 m, permanent loss 98,066.5 Pa, differentialPressure null. The trace has no 'Differential pressure' line and no 'Vena contracta drop' line. In the web's Orifices table, 'Differential pressure (taps)' shows '—', the same as a plate without taps. An entered C of 5×10⁻¹⁵³ (a plate the 1.6.1 test also accepted) also gives null. A goal seek on this plate's reading would say it 'has no pressure taps'. That comes from the code, not from a run.
- **Who would hit it.** No one modelling a real plate. Only a project with an entered discharge coefficient around 10⁻¹⁵², about 150 orders of magnitude below a real plate's C of about 0.6.
- **The run.** Scripts in orifice/, run with `cd apps/api && uv run python <file>`.

zero_flow.py posts each network to /api/v1/solve through FastAPI's TestClient. Output in zero_flow.out:
- A (ISO C, flange, dead-end spur): 'flow: 0.0 … differentialPressure: 0.0 … trace row: Differential pressure Δp at the taps (the reading) = 0.0 Pa'.
- B (C 0.61, corner): the same.
- D (documented plate, 1000 kg/m³, 10 Pa·s): 'converged: 507 Newton iterations … flow: 0.0, headLoss: 10.0, pressureLoss: 98066.5, differentialPressure: None … trace has a Differential pressure row: False … Vena contracta drop row: False'.

threshold.py: 'rho 998.0: the reading at zero flow is null for an entered C below about 9.125e-153' and 'C_e 5e-153: refused=False … flow=0.0, head loss=10.0, differentialPressure=nan'. A one-off check showed that the 1.6.1-era first-stage test passes this plate: 'r_min 0.9993960278048072 r_max 1.0 first-stage (1.6.1) test passes: True'.

An inline check on the documented plate: 'true flow Q = sqrt(10 m / factor): 2.3585344276198314e-154 m³/s … reading at that flow, multiplied in the API's order: inf … v|v| first: 97952.94871614972 Pa … permanent pressure loss rho g h: 98066.5 Pa'.
- **Options:**
  - Report 0 Pa whenever the reported flow is 0 *Cost:* small code (under an hour); the tier-3 proofs add about half a day. *Tier:* 3. *Risk:* Replaces a blank with a wrong number. In exactly the cases that reach this, the plate takes the whole head and the true reading is about 98 kPa, not 0. Not recommended.
  - Compute the reading from the solved permanent loss where the reported flow is 0: reading = ρ·g·h × (1 − β⁴)/(C_M²β⁴) ÷ K(C_L). This is an exact rearrangement of D20's two formulas at one flow, a closed form under D8. *Cost:* medium (about a day: the code is short, plus an independent closed-form reference case, a METHOD_VERSION 1.6.3 entry, the corpus comparison and the fuzz profiles). *Tier:* 3. *Risk:* Low. Every reading at a non-zero reported flow stays the same to the last digit, and a true no-flow branch still reads 0 because its head loss is 0. A zero-flow loop whose head loss is only the solver's last-digit noise would show a tiny noise value unless it is cut off at the solver's head resolution. It also fixes OP-2.
  - Keep the blank but say why: a trace note and a web label such as 'not computed: too large to represent' in place of the silent dash, and correct goal seek's 'has no pressure taps' text *Cost:* small to medium. *Tier:* 3 (trace and error text go through the solve's response, workflow.md §4). *Risk:* Low, but there is still no number.
  - Leave the code; correct the records *Cost:* small. *Tier:* 1. *Risk:* None; the blank stays. D20 (Reading; Versions 1.6.2), TSD §5 (the line on differentialPressure) and open-defects-2.md §7 call this 'inf·0 at a reported flow of 0', which invites option 1. They should say the true reading there is about the plate's permanent loss, and add OP-2.
- **Recommendation.** Correct the records now (tier 1). Then fold option 2 into the next orifice method change, for example the low-Reynolds-number C slice the roadmap lists, so it shares that change's tier-3 proofs. A standalone tier-3 change for an input 150 orders of magnitude outside practice is not worth its cost. Never take option 1: it turns a blank into a wrong number.
- **Records:** docs/roadmap.md §2, 'Orifice plate' bullet; docs/proposals/open-defects-2.md §7 ('differentialPressure null' bullet), §9 item 2 (third sub-bullet); docs/decisions/D20-orifice-plate.md 'Reading and vena contracta', 'Versions' (1.6.2 paragraph's last sentence); docs/TSD.md line 798; apps/api/src/opensolve_pipe/services/solver/orifice.py:429-433 (pressure_term), 486-487; apps/api/src/opensolve_pipe/services/solver/trace.py:236-238 (a value that is not finite is dropped silently), 2500-2503; apps/api/src/opensolve_pipe/services/solver/results.py:8-12 (round-off flows reported as 0), 1283; apps/api/src/opensolve_pipe/services/goal_seek.py:2319-2321; apps/web/src/lib/utils/results.ts:646, 1510, 1528, 1899-1900.

### OP-2. Meter reading shows 0 Pa while the plate takes the whole head

- **Consequence:** wrong value shown; **likelihood:** extreme inputs only; **reproduced on main:** yes.
- **What happens.** This one is new: no record mentions it. It comes from the same root as OP-1, but it appears at much less absurd values. The solver reports any flow at round-off level, at most 10⁻¹² of the largest flow plus 10⁻¹⁴ m³/s, as exactly zero. The permanent loss is taken from the solved heads, so it still shows the whole head across the plate. The meter reading is computed from the reported flow, so it shows 0 Pa. The results table then says the flow is 0, the permanent loss is about 98 kPa and the reading is 0 Pa. Those disagree. A real meter across a plate this tight would read the full difference, about 98 kPa. In the 10 m line below this starts at an entered C between 10⁻¹³ and 10⁻¹⁴. That is still far outside practice, but it is a value someone might type to model a blind plate. D20 intends isolation valves for that job.
- **Example.** R1 (level 10 m) → 10 m of 0.2 m pipe → plate O1 (bore 0.1 m, flange taps, entered C) → 10 m → R2 (level 0 m), water (998 kg/m³, 1 mPa·s). With C 10⁻¹³: flow 1.135×10⁻¹⁴ m³/s, permanent loss 97,870.4 Pa, reading 97,757 Pa, consistent. With C 10⁻¹⁴: flow 0, permanent loss 97,870.4 Pa, reading 0.0 Pa. The web's Orifices table would show flow 0, permanent loss about 97.87 kPa and differential pressure 0. The same holds at C 10⁻¹⁰⁰ and 10⁻¹⁵², where the reading at the plate's true flow is 97,952.9 Pa in 1000 kg/m³.
- **Who would hit it.** Someone who models a closed (blind) plate by entering a tiny discharge coefficient instead of using an isolation valve. With real coefficients no one does.
- **The run.** orifice/snap.py, output in snap.out:
- '998.0 kg/m³ 0.001 Pa·s, C_e 1e-13: converged True, flow 1.135e-14 m³/s, permanent loss 97870.4 Pa, reading 97757.04315566277 Pa'
- '… C_e 1e-14: converged True, flow 0 m³/s, permanent loss 97870.4 Pa, reading 0.0 Pa'
- 1000 kg/m³ and 10 Pa·s gives the same pattern: 97,952.9 Pa at 1e-13, 0.0 Pa at 1e-14.

An inline check gave 'C_e 1e-100: flow at which the plate takes 10 m: 1.14e-101 m³/s; reading there … 97952.9 Pa … at flow 0 0.0'. threshold.py: 'C_e 1e-152 … flow=0.0, head loss=10.0, differentialPressure=0.0'.
- **Options:**
  - OP-1's option 2: where the reported flow is 0, compute the reading from the solved permanent loss *Cost:* medium (about a day, shared with OP-1). *Tier:* 3. *Risk:* As OP-1's option 2. The reading at C 10⁻¹⁴ would become about 97.76 kPa, consistent with the permanent loss.
  - Leave and record it beside OP-1 *Cost:* small. *Tier:* 1. *Risk:* The disagreeing row stays for C below about 10⁻¹³.
- **Recommendation.** Record it now with OP-1 (tier 1), and fix it in the same change as OP-1's option 2. One formula covers both. Fixing OP-1 alone would leave this case behind.
- **Records:** apps/api/src/opensolve_pipe/services/solver/results.py:8-12, 314 (zero-flow reporting rule); apps/api/src/opensolve_pipe/services/solver/gga.py:147, 172 (CONTINUITY_ATOL 1e-14, ZERO_FLOW_RTOL 1e-12); apps/api/src/opensolve_pipe/services/solver/orifice.py:429-433, 486; docs/decisions/D20-orifice-plate.md 'Model' (no status: valves isolate the plate).

### OP-3. Plate accepted one rounding step past rule (d)'s edge

- **Consequence:** none found; **likelihood:** extreme inputs only; **reproduced on main:** yes.
- **What happens.** Rule (d) refuses a plate, before solving, if its loss factor K/(2gA²) could become infinite at some flow. Since 1.6.2 the rule checks this at the least C the plate's law can take. It computes that least C from the project's own written-out copy of ISO 5167-2 eq. (4). The solver's law gets its C from the fluids library, by a slightly different route, so the last digit can differ. At the exact edge, the refusal's C gives a finite factor while the law's C, one rounding step smaller, gives an infinite one, so the plate is let through. I found no visible harm. In water such a plate's solve ends 'not converged' and names the plate, as do band plates with no gap at all. In a very viscous liquid it converges with flow 0 and the whole head across the plate, which is the right answer within D6. The only cost is a broken promise: an accepted plate should never meet an infinite number.
- **Example.** R1 (level 10 m) → 10 m of 0.1 m pipe → O1 (bore 0.097 m, flange taps, entered C 6.212305790600638×10⁻¹⁵⁴, the plate named in open-defects-2.md §9 item 2) → 10 m → R2 (0 m). The refusal accepts it. The least C it tests is 7.71842795922812×10⁻¹⁵⁴, with a finite factor of 1.797×10³⁰⁸ s²/m⁵. The law holds 7.718427959228118×10⁻¹⁵⁴, one step below, where the factor is infinite. In water: 'not converged … not a finite number in the law of O1'. In 1000 kg/m³ at 10 Pa·s, and in 800 kg/m³ at 0.0518 Pa·s: converged in 505 iterations, flow 0, head loss 10 m, reading blank (OP-1). The review's plate (D 0.1 m, bore 0.093 m, corner taps) at its edge, C 1.0251723041390432×10⁻¹⁵³, found here by bisection, shows the gap in water and in 800 kg/m³ at 0.0518 Pa·s but not at 10 Pa·s. So the gap depends on the fluid.
- **Who would hit it.** Only a project whose entered C lies within a rounding step of the edge, about 10⁻¹⁵⁴ to 10⁻¹⁵³. The record found 10 such edges among 449 bisected ones, all at β 0.9 or more.
- **The run.** orifice/edge_gap.py, output in edge_gap.out:
- 'refusal(): None'
- 'least C the refusal tests … 7.71842795922812e-154', 'loss factor … 1.7976931348623153e+308'
- 'fluid 998.0 …: law's held C (fluids) 7.718427959228118e-154, +1.00 last-digit steps below; loss factor there inf', 'solve: converged=False; the iteration diverged … in the law of O1'
- '1000.0 kg/m³, 10.0 Pa·s: … converged: 505 Newton iterations … flow 0.0 m³/s, head loss 10.0 m, differentialPressure nan'
- For the 0.093 m corner plate: '+0.00 last-digit steps below' at 10 Pa·s and '+1.00' in the other two fluids.

D20's documented plate has no gap ('+0.00'), but in water its solve is also not converged. So the gap is not what makes water fail.
- **Options:**
  - Add a margin of a few rounding steps to the least C in rule (d)'s second stage *Cost:* medium (the code is small, but D8 needs a written bound on how far the fluids route can round, plus a reference case, a METHOD_VERSION entry and the corpus proofs). *Tier:* 3. *Risk:* Newly refuses the few edge plates that converge at flow 0 today in viscous liquids. The first stage is unchanged, so the refusals stay inside 1.6.1's.
  - Evaluate fluids' own C at the least point inside the refusal *Cost:* large. *Tier:* 3. *Risk:* The rounding depends on the fluid (measured above), so the test would move into the fluid-dependent rule (e). Goal seek's bound argument (decision 21) would have to be proved again.
  - Leave it; the records already state it *Cost:* none, or small to tidy the roadmap. *Tier:* 1 for the tidy. *Risk:* None found. The outcome on screen matches that of band plates with no gap.
- **Recommendation.** Leave it. It is reached only at C around 10⁻¹⁵⁴ and changes nothing a user can see. One small tidy: the roadmap lists it twice, under 'Orifice plate' and again under 'Inputs at the schema's bounds' as AO-2. Keep one entry.
- **Records:** docs/roadmap.md §2, 'Orifice plate' bullet and 'Inputs at the schema's bounds' last sub-bullet; docs/proposals/open-defects-2.md §3 A1, §7 ('Rule (d)'s stage 2 at the exact edge', AO-2), §8, §9 item 2 (first sub-bullet); docs/decisions/D20-orifice-plate.md 'Limits, flagged and refused', rule (d), the paragraph beginning 'New refusals are a subset'; docs/TSD.md line 795; apps/api/src/opensolve_pipe/services/solver/orifice.py:690-714 (least_coefficient), 732-801 (refusal), 376-394 (the law's C from fluids).

### OP-4. AO-1: where the slope test takes over (records, already fixed)

- **Consequence:** none found; **likelihood:** extreme inputs only; **reproduced on main:** no, it is fixed.
- **What happens.** Rule (d) has a second half, the 'slope' test. The solver also needs the slope of the head-loss curve, which doubles K. If K is above half the largest number even at the plate's largest C, that slope is infinite at every flow, so the plate is refused with a different message. The round-two review (AO-1) found that the records put the pipe size where this second test takes over 1.6.2's newly accepted band at D 0.536 m. It is really about 0.45 m. The records were corrected, and a test pins the corrected statement. The behaviour was right all along. Nothing is left to fix in the code. One record still calls the cause 'left for later', but there is no later item for it.
- **Example.** Band plates at β 0.8, corner taps, R1 (10 m) → 10 m pipe → O1 → 10 m pipe → R2 (0 m). On D 0.45 m (bore 0.36 m, entered C 1.2536500045118327×10⁻¹⁵⁴): accepted. In water it is not converged, naming O1. In 1000 kg/m³ at 10 Pa·s it converges in 510 iterations at flow 0. On D 0.46 m (bore 0.368 m, entered C 1.1997359447714848×10⁻¹⁵⁴): HTTP 422 ORIFICE_OUT_OF_RANGE, 'with a discharge coefficient of at most 1.24666e-154 at every flow it gives a loss coefficient K of at least 9.27449e+307, above 8.98847e+307, half the largest floating-point number, so the slope of its head loss … is not a finite floating-point number at any flow but zero; the solver cannot represent this plate'.
- **Who would hit it.** No one; this was a records correction.
- **The run.** orifice/ao1.py (output in ao1.out) shows the behaviour the corrected record describes: accepted on D 0.45 m, refused by the slope test on D 0.46 m. I also ran the pinning test alone, plus the band and documented-plate tests: `uv run pytest tests/unit/test_orifice_least_c.py -k "slope_test_takes_over or high_beta_plate_in_the_band or documented"` gave '4 passed, 27 deselected'.
- **Options:**
  - Amend open-defects-2.md §8 so AO-1 reads 'records corrected; nothing left' rather than 'the cause left for later' *Cost:* small. *Tier:* 1. *Risk:* None.
- **Recommendation.** Fine to leave as closed. The wording fix is optional. If anyone tidies the records for OP-1 and OP-2, make it in the same change.
- **Records:** docs/proposals/open-defects-2.md §8 (line 152), §9 item 16 ('AS-1, AO-1'); docs/history.md line 113; docs/decisions/D20-orifice-plate.md 'Versions' 1.6.2, third sub-bullet; apps/api/tests/unit/test_orifice_least_c.py:429 (test_the_slope_test_takes_over_the_band_from_d_about_0_451_m).

### WEB-3. Editing in a scenario case is slow on very large networks

- **Consequence:** none found; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** Every edit you make (a pipe length, a valve status) is processed in your browser before the page responds again. On the base case this has been made fast: the app copies, writes and checks only what you changed. With a scenario case shown, an edit still goes the long way, because the app rebuilds the whole case's project (the base with that scenario's changes applied). It makes a full copy for the edit and checks the whole case for structural problems twice, before and after. That work grows with the size of the network, not the size of the edit. The project's own target is that no edit holds the page for more than 100 ms on a desktop, and 300 ms on a CPU slowed fourfold to stand in for a phone. On the largest network measured (999 components, 1,999 connections) the edit code alone took 135 ms in Node, without the browser's redrawing, so the target is not met there. On a network of about 100 components the same edit takes about 10 ms, which nobody feels.
- **Example.** A 1,000-component network (near the app's limit of 1,000 components) with a scenario 'High demand'. Show that scenario, change a pipe's length and press Enter. On a desktop the page is busy for about a tenth of a second, plus the redraw: a click or keystroke made in that moment waits, a barely noticeable hitch. The same edit on the base case is about ten times quicker. On a phone it would be longer, but this has never been measured on a real phone or in a fourfold-throttled browser.
- **Who would hit it.** An engineer with a model of several hundred to 1,000 components who uses scenarios and edits values while a scenario is shown. Typical models (the examples have tens of components) are not affected.
- **The run.** Scratch timing test in Node with a simulated browser page (jsdom), run through the real Workspace edit path on main: web/perf.svelte.test.ts. The network is a chain: tank, then N gate valves joined by pipes, then tank, plus one scenario. It makes 12 pipe-length edits per case, with the first 2 dropped for warm-up. Run on a 4-CPU container at load 0.2-0.4. Last run: '99 components, 98 connections | base edit median 1.1 ms | scenario edit median 10.0 ms'; '299 components, 298 connections | base 1.9 ms | scenario 27.0 ms'; '999 components, 998 connections | base 9.3 ms (range 5.7–14.7) | scenario 63.1 ms (range 61.8–97.9)'. Earlier runs gave 69.3 and 94.6 ms for the scenario median at 999 components. My chain has half the connections of the recorded 999/1,999 network, which explains the lower figure against the recorded 135 ms. These are edit-code times, not browser long tasks; rendering comes on top.
- **Options:**
  - Leave it on the roadmap. *Cost:* none. *Tier:* n/a. *Risk:* A noticeable hitch per edit for the rare very large model in a scenario case, worse on phones (not measured).
  - Measure it first in a real browser: the scenario-case edit in Chromium on desktop and with the CPU slowed fourfold, at 99 and 999 components. The earlier timing setup was never committed, so it would be rebuilt. *Cost:* small to medium (a few hours). *Tier:* 1 (measurement only; no app code changes). *Risk:* None. It tells whether the hitch is 0.1 s or 0.5 s on a phone before any code is touched.
  - Make the scenario edit work like the base edit: keep the case's project and its structural check from the last stored version instead of rebuilding them for every edit, and copy only the element being edited. *Cost:* medium to large (one to several days). *Tier:* 3 (it is the path that decides which scenario changes are saved in the user's project; workflow §4: 'Anything that changes the project the user keeps or shares (editing, undo ...)'). *Risk:* A stale saved copy could save a wrong scenario value or miss a refusal of an invalid edit. That would change a solved value, so it needs every gate, including scenario_check, and a proof that each faster path equals the slow one.
- **Recommendation.** Leave it for now. The project's goals put correctness first and usability later, and the delay is near the limit of what anyone notices, only at the network size limit and only in a scenario case. The fix is tier 3 because it touches the path that saves the user's scenario changes. If a real user brings a model of that size, do the browser measurement first, then decide on the fix.
- **Records:** docs/roadmap.md §2, Per-edit speed bullet (line 27); docs/TSD.md §12 item 20 (line 2217): targets of 100 ms desktop and 300 ms under fourfold throttling, and 'Not met: an edit in a scenario case ... 447 to 135 ms'; SDD §3.1.4 (per-edit path, cited by TSD §12 item 20); apps/web/src/lib/utils/scenarios.ts:829-866 (scenarioEdit: caseProject at :836, full copy at :839); apps/web/src/lib/state/workspace.svelte.ts:993-1030 (editScenario: structuralProblems of the whole case before and after, :1017-1024); docs/workflow.md §4 (tiers).

### CS-7. The home page's How it works screenshots are out of date

- **Consequence:** cosmetic; **likelihood:** common; **reproduced on main:** yes.
- **What happens.** The eight steps on the home page use hand-taken screenshots. They were last retaken on 2026-11-18. On 2026-11-24 the navigator's Previous and Next buttons were changed to show the neighbour's whole name, so the shots now show the old cut-off text. The owner chose to retake them by hand when they go out of date. Later visible changes (Solve dimmed while results are current, 2026-11-27) may also differ. That was not checked.
- **Example.** On the home page, the 'Describe each element' laptop shot shows 'Next: Discharge isol…' cut off, where the app now shows the full name.
- **Who would hit it.** Every visitor to the home page.
- **The run.** Viewed apps/web/static/landing/build-laptop.webp: its navigator reads 'Next: Discharge isol...'. `git log -1 -- apps/web/static/landing/` gives 63b3727 2026-11-18 'web: Pumps leftovers, the home page's How it works shots retaken', before the navigator change of 2026-11-24 (usability-entry.md §4, U2).
- **Options:**
  - Retake the sixteen shots (a laptop and a phone shot for each of the eight steps) in the same states, as landing-page.md §3 and §7 describe *Cost:* small to medium (one to two hours). *Tier:* 1. *Risk:* None to results. Alt texts may need a word changed.
- **Recommendation.** Do it, ideally batched with the next visible UI change so the shots are retaken once.
- **Records:** docs/proposals/usability-entry.md §9, last bullet; docs/proposals/landing-page.md §9; docs/proposals/open-defects.md §6; docs/roadmap.md §2, Usability.

### CS-8. The export's System curves sheet lacks the reason numbers

- **Consequence:** value missing; **likelihood:** occasional; **reproduced on main:** yes.
- **What happens.** When a system-curve point has no head (for example past a flow control valve's limit), the API returns the reason as data: the limit flow, the flow that passed, the open-valve head and its bound, the starts tried and the ids involved. The workbook's Group system curves sheet writes each of these to its own cell. The single pump's System curves sheet writes only the reason code and the sentence, so those numbers are not available as cells there. Recorded as a separate change when the group sheets were built.
- **Example.** A pump feeding a line with a flow control valve set to 12 L/s: the chart's system curve ends at a limit point, and its data table says why. In the exported workbook, the System curves sheet has 'At a flow limit', 'Reason code' and 'Reason' (the words), but no 'Limit flow' or 'Passed flow' column to filter or plot on.
- **Who would hit it.** Users who export the workbook and analyse system-curve gaps outside the app.
- **The run.** Read apps/web/src/lib/utils/export/tables.ts: the 'System curves' table (around lines 697-741) has columns Pump id, Pump, Flow from, Flow to, Point #, Flow, Head, Converged, At a flow limit, Reason code, Reason. The Group system curves rows (around lines 1000-1016) also write message, limitFlow, passedFlow, openHead, openHeadBound, startsTried, componentIds and assignedFlowNodeIds.
- **Options:**
  - Add the same reason columns to the System curves sheet; regenerate the export fixture and run the committed-workbook verifier *Cost:* medium. *Tier:* 3 (numbers the user exports). *Risk:* Low. Wider sheet; the fixture changes.
- **Recommendation.** Worth doing next time the export is touched. It makes the two sheets consistent with D10's 'reason as data'. Not urgent.
- **Records:** docs/roadmap.md §2, Export; docs/proposals/pump-groups.md §16 (As built, slice 4c), item 6.

### CS-10. A library note still says the pump chart's legend draws dashes solid

- **Consequence:** cosmetic; **likelihood:** only in tests; **reproduced on main:** no, it is fixed.
- **What happens.** The library-facts file warns future sessions that the single pump chart's legend draws its dashed and dotted curves as solid lines. That was fixed on 2026-11-18 (leftover L16): the legend now gives each line its own dash pattern on screen and in the image, and tests pin it. The note is stale and could send a future session to fix something already fixed.
- **Example.** No user impact. A developer reading docs/library-facts.md (Chart.js 4.5.1, third bullet) is told 'Motor rated power (dashed)' is drawn solid, but the app draws it dashed.
- **Who would hit it.** Future development sessions only.
- **The run.** pumps-nits.md §11.5 L16 records the fix. apps/web/src/lib/utils/pump-chart-config.ts gives each legend entry its dataset's borderDash (lines 162-179, 378-381), and pump-chart-config.test.ts lines 1194-1207 assert each line entry's lineDash equals its own.
- **Options:**
  - Rewrite that bullet's last sentence to say the single pump chart's legend does the same since L16 *Cost:* small. *Tier:* 1. *Risk:* None.
- **Recommendation.** Fix it in the next docs change.
- **Records:** docs/library-facts.md, Chart.js 4.5.1, the usePointStyle bullet; docs/proposals/pumps-nits.md §11.5, L16.

### CS-12. A field-registry check skips valve resistance; two label lists are kept by hand

- **Consequence:** none found; **likelihood:** rare; **reproduced on main:** yes.
- **What happens.** The Build forms read every field's label and unit from one registry, and a test checks that every field of the model is registered. Fields marked 'whole' are skipped, so a valve's resistance editor (its kind, value and library id) is not checked field by field. Two other lists are still written by hand rather than read from the registry: the export's pump input columns, and the labels used in the 'must be below its…' order message. Nothing is wrong today, but a renamed or added field could drift unnoticed.
- **Example.** No user impact today. If a future change renamed a pump field's label, the Build form would follow but the order message ('The minimum speed of P1 must be below its maximum speed') and the export's pump columns might keep the old words.
- **Who would hit it.** Developers adding or renaming fields; users only if words drift.
- **The run.** Read apps/web/src/lib/utils/field-registry.ts: `whole?: boolean` (line 88), RESISTANCE with `whole: true` (line 115), and the guard drops sub-paths under a whole entry (lines 441-451). labels.fieldLabel is used by the order rule in validate.ts line 814.
- **Options:**
  - Register the resistance sub-fields so the guard sees them *Cost:* small to medium. *Tier:* 1. *Risk:* Low.
  - Read the export's pump columns and fieldLabel from the registry *Cost:* medium. *Tier:* 2 (the export's wording). *Risk:* Export words may change, so the fixture is regenerated.
- **Recommendation.** Fine to leave until a change touches valve resistance or the export's pump table, then fold it in.
- **Records:** docs/proposals/build-density.md §10, items 4 and 5.

## 8. Notes from the investigators

**The system curve's limits.** WHAT THE TERMS MEAN (for the owner). A system curve answers one question for each flow Q: what head would this pump have to add to push Q through the rest of the network as it is? The API swaps the pump for a fixed flow, solves the network at 41 evenly spaced flows, and reports the head across the pump at each one.
- FLOW LIMIT: some networks cannot carry more than a certain flow, whatever the head. An FCV passes at most its setpoint, and a check valve passes nothing backwards. The flow limit is that largest flow. Above it, each point says 'no steady state carries this flow' (reason beyond_limit, quoting the limit), and the chart draws nothing there.
- FLOOR: the opposite bound, set by fixed demands or supplies (assigned flows). Take a 20 L/s demand fed by the pump and by an FCV that passes at most 5 L/s: the pump must pass at least 15 L/s. Below the floor each point says so (below_floor), and nothing is drawn.
- LIMIT POINT (since 1.6.2): the 41 grid flows rarely land exactly on the limit or the floor, so the API solves one extra point at each, when it lies inside the chart's range and the floor is not above the limit. At an FCV's limit the valve passes exactly its setpoint. It can be fully open or throttling, so every head at or above the fully-open value holds there ('lower'), or at or below it ('upper') for a valve beside the pump feeding a demand. The API reports this as reason valve_at_switch, with openHead (the fully-open head, the foot of the range) and openHeadBound (which side). The chart draws the curve up to the foot and then a vertical line to the top of the chart (or down to the bottom). The pump curve crosses that vertical at the operating point where the FCV throttles. Any other point without a head is drawn as a gap and never bridged (apps/web/src/lib/utils/system-curve-line.ts, module comment).

STATUS TODAY: all four loose ends reproduce on main da43e96 (METHOD_VERSION 1.6.2), with the numbers in the records: 0.011 against 0.002 m³/s; 1.2009147309991164 m against 41 m; VS 0.015 and V1 0.004999999999999998 m³/s held open together.

RECOMMENDED ORDER: SC-3 and SC-4 together, as one tier-3 slice of about one to two days, each with a reference case written by someone who has not read the solver, the corpus comparisons and one METHOD_VERSION entry. Both fix cases where the chart shows an operating point off its system curve in ordinary networks: a pump with a check-valved standby feed to a fixed demand, and a duty/standby station behind an FCV. SC-1 and SC-2 are fine to leave: each needs an unusual or exactly balanced layout, nothing false is claimed, and in SC-2's network the case's own solve already fails.

SIDE OBSERVATION, outside this group and not investigated further: in SC-2's network the case's own /api/v1/solve does not converge (NOT_CONVERGED, oscillating V1), although holding VS and V1 open together converges at their setpoints. The solve's valve-status rules fail to find a steady state that exists, at an exact tie of setpoints. I found it in no record I read; it may deserve its own entry. Its likelihood is rare.

LIMITS OF THIS CHECK: the web behaviour (what is drawn, and the ring words in SC-4) comes from reading system-curve-line.ts and pump-group-one-off.ts, not from a browser run. I did not run the full suites, and nothing in the repository was changed. The scratch scripts are in system-curve-limits/ (common.py, sub1_crossed.py, sub23_floor.py, sub2_more.py, sub2_held.py, sub3_check.py, sub3_grid.py, sub4_group.py, sub4_standby.py, sub4_ongrid.py, solve_peek.py). Each runs with `cd /home/user/opensolve-pipe/apps/api && uv run python <script>`.

**Inputs at the schema's bounds.** I read files and ran small scripts only. The checkout is unchanged at da43e96 (git status is clean). Scratch scripts are in schema-bounds/ and were run with PYTHONDONTWRITEBYTECODE=1, so no bytecode cache files were left in the repository.

How the five compare:
- Only SB-1, and SB-2 which comes from the same inputs, can plausibly happen on a real project: someone gives a valve a tiny Cv to make it act closed, upstream of a dead end or an assigned flow.
- SB-3, SB-4 and SB-5 need a fluid density below about 10⁻³⁰¹ kg/m³ or a discharge coefficient around 10⁻¹⁵⁴. No engineering input reaches them.

Two records are wrong or understated:
- **SB-1's threshold.** The roadmap's 'above about 3·10^19 s²/m⁵' is only the first-iteration threshold for one 0.1 m test network. Whole solves fail from about 2·10^18 s²/m⁵ on that network. On a 1 m valve with 1 m of pipe to a dead end they fail at 2.8·10^11 s²/m⁵ (Cv 0.025). Whether a given value fails depends on the iteration path.
- **SB-2's 'none a final result'.** That holds for the fuzz seeds only. A simple valve-to-plug network ends on the plain 'singular matrix' message (Cv 4.2·10⁻⁶ on 0.1 m).

New measurement for SB-3: an Active check valve fails in both flow directions. Locked closed, Locked open and closed off between isolated gates all solve.

Seen but outside this group: in SB-5's viscous run the plate's differential pressure came back as NaN at zero flow. That is the separate §7 item "differentialPressure null for a plate with taps at a reported zero flow"; I did not check how it reaches the web.

If the owner wants SB-3 and SB-4 closed, the cheapest consistent fix is one tier-3 round that refuses them before the solve, the way 1.6.2 refuses reservoirs. That would turn some cases that solve today into refusals, so it needs the owner's decision.

Not done: nothing was re-run on 8535900, and no screen was checked in a browser. What the user sees is taken from the API messages plus apps/web/src/lib/components/results/ConvergenceStatus.svelte.

**The orifice plate.** Rule (d) and the 'least C', in plain words. The solver writes a plate's head loss as h = [K/(2gA²)] × Q|Q|. K is the plate's loss coefficient and comes from its discharge coefficient C: the smaller the C, the larger the K. For tiny C, K grows as 1/C². For scale: an entered C of 0.61 on D 0.2 m with a 0.1 m bore gives K = 29.5; a C of 10⁻¹⁵² gives K = 1.5×10³⁰⁵ (threshold.py). A computer number stops at about 1.8×10³⁰⁸; beyond that it becomes 'infinity', and the solve breaks. Rule (d) (D20, 'Limits, flagged and refused') refuses such a plate before solving, with a 422 ORIFICE_OUT_OF_RANGE, so the solver never meets infinity part-way through. Because K is largest where C is smallest, it is enough to test the smallest C the plate's law can ever use at any flow. That is the 'least C':
- an entered C used as entered: that C;
- ISO's C: its value at infinite Reynolds number;
- a C entered at corner or flange taps: the C times the smallest ratio of ISO's two tap coefficients over all Reynolds numbers, because the app moves such a C to D and D/2 taps by that ratio.
Up to 1.6.1 the rule used a cruder lower bound for C and so wrongly refused some plates. Since 1.6.2 it retests at the exact least C. The second half of rule (d), the 'slope' test, refuses where even the largest C gives a K above half the largest number. Every item in this group needs an entered C between about 10⁻¹³ (OP-2) and 10⁻¹⁵⁴ (OP-1, OP-3, OP-4). Real plates have a C of about 0.6.

What is new here. OP-2 is in no record. It has the same root as OP-1 at far less extreme values: a flow at round-off level is reported as 0, so the reading is computed from that 0 while the permanent loss comes from the heads. The cheap fix for OP-1, 'report 0 at zero flow', would therefore be wrong: in the cases that reach it, the true reading is about the whole permanent loss (97,953 Pa against 98,066.5 Pa in the documented example). The records' phrase 'inf·0' points toward that wrong fix.

Records detail. D20's rule (d) says such a solve 'converges at flow 0 … (so the loss is 0)'. That means the law's own value at Q = 0. The results show a head loss of 10 m and a permanent loss of 98 kPa at a reported flow of 0, because the true flow is about 2.4×10⁻¹⁵⁴ m³/s. A reader could take 'the loss is 0' to describe the results.

Method notes. I edited nothing in the repository. Scratch scripts and their outputs are in orifice/: zero_flow.py, edge_gap.py, threshold.py, snap.py and ao1.py, each with a matching .out file. I could not run 1.6.1's code without checking it out. So the claim that the null predates 1.6.2 rests on two things: D20 says the first stage is 1.6.1's test, and that first stage passes the C 5×10⁻¹⁵³ plate that gives null. My rounding-step gaps are measured in steps of the least C's own last digit and came out at 1.00. The record's '0.6 to 1.5' range over 10 of 449 edges was not re-bisected, which would have meant re-running the 449-plate study.

**The web app.** Every check in this group was read-only. The repository was not modified: scratch tests and their config are under web/ (converted-note, control-note, tab-pair and perf .svelte.test.ts, vitest.scratch.config.mts, and a node_modules link to apps/web's). They run with `cd /home/user/opensolve-pipe/apps/web && pnpm exec vitest run --config <that dir>/vitest.scratch.config.mts --silent=false --reporter=verbose <name>`. No Playwright, servers or full suites were run. (1) The test at :265 and the one at :271 are the same test. Commit 82fd96e (2026-11-27) added six lines above it, and its body is unchanged since e40cdec (2026-11-05). The roadmap's ':265' should read ':271' when it is next edited. The 2026-11-27 failures (4 in 20, then 0 in 80) are not in docs/history.md yet. (2) WEB-1b is new and unverified: a possible loss of keyboard focus when tabbing between the paired limits, suggested by the same redraw. It is listed so that the WEB-1 fix checks it in a browser, not as a confirmed defect. (3) The remove-then-install-fake step suspected in WEB-2 also appears in other browser-test files (page.unroute in one-solve, scenarios, goal-seek, project-library, export, pumps-layout). I did not check whether those are followed by a new fake before a request, and none of them has failed in the 97 CI mobile runs looked at. (4) The WEB-3 times are from Node with a simulated page on a chain of 999 components and 998 connections, so they are lower than TSD's 135 ms on 999 components and 1,999 connections. They show the growth with network size (about 10, 27 and 63-95 ms at 99, 299 and 999 components) and the roughly tenfold gap to a base-case edit. They are not browser long-task figures.

**Waiting on the owner.** Nine items in this group, all checked against main da43e96 (METHOD_VERSION 1.6.2).
- Need only your answer, a minute each: OW-1 (bypass station turned around), OW-3 (lineups table layout), OW-4 (label of a cut curve), OW-5 (pump chart toggles and card height).
- Need a quick look by you: OW-2 (the photo; one look at the basin level in your saved link).
- Need hands-on checks only you can do: OW-6 (export in Excel, Numbers and on iPhone), OW-7 (editing speed on a real phone), OW-8 (deploy checks 3-5).
- Needs a settings change only you can make: OW-9 (make GitHub stop a merge when CI fails).

None of them is a wrong value on today's main. OW-1 is a question about how a rare case is presented, and the numbers behind it are consistent. For OW-2, the shipped example's fixture at 1.6.2 shows the group system curve starting at 10.4 m, and at -4.0 m with the basin level at 15.0 m, exactly the photo's 14.4 m gap. That points to the project's data rather than a defect.

Two record clean-ups worth doing in the same change as your answers:
- The roadmap's 'Pump lineups' bullet still lists item 107 as if open. pumps-nits slice 5c settled it; only item 108 is open.
- Once you add the required checks, workflow.md §4 and D25's 'What main controls' need updating.

What I did: I edited nothing in the repository. I ran one scratch script, owner/mirror.py, and made three read-only GitHub API calls (the ruleset, branch protection, and the check names on main's head). I did not check in a browser how OW-1's turned-around group curve looks on screen; that description is inferred from the axis rule in open-defects-2.md §2 item X.

**The sweep.** How the sweep was done: I read docs/roadmap.md, docs/history.md, docs/TSD.md §12 (decided and open items), docs/library-facts.md, docs/verified-state.md, the open-defects proposals' Later sections, and every proposal's Later, Known limit and open-point passages. I also searched apps/api/src and apps/web/src. Scratch scripts are under completeness/. Nothing in the repository was changed.

Found and dropped, with the reason:
- Code markers: the source has no TODO, FIXME, XXX or HACK. Every skipped browser test is skipped by design for the other screen size.
- Pump-group 'same answer under D13' limits (pump-groups.md §14 and §15): for example, a member reading 'running' at ±10⁻¹⁴ m³/s near zero flow. D13 says these are not regressions and are never taken to the owner.
- 'Scenario 3' keeping number 2 after a deletion: the trade-off the owner accepted with Q2 (pumps-nits.md §11.6).
- Build density's red-team objection 1, a top-heavy phone loop: a decided phone flow.
- Build density's §12 'strip kept in view when it gains a flag' and 'segments for three-value choices': small usability features, not defects.
- TSD §12 open item 4, the three-way valve characteristic: a Later component, a feature.
- Export §10 and goal-seek §10 open points: all feature candidates.
- open-defects.md §6 F2 and F3: fixed in round two.

Overlaps with other groups, to avoid double counting:
- CS-5 sits next to the pump-group bypass frame question.
- CS-11 overlaps the export's by-hand checks (iPhone Safari) and per-edit speed on a real phone; it is broader, covering every browser test.
- CS-15 is the remainder of the Pumps-tab open defaults beyond S1 and lineups L2 and L3.
- Every item in open-defects-2.md §7 is on the excluded list.

Small record gaps noticed:
- history.md's reference-suite paragraph says the worst deviations 'were not re-measured' for round two's new cases (2026-11-26).
- CS-3's reproduction shows the 'not converged' message naming the PRV as cycling when it is converging slowly. This is not in any record, so it is new.

Likelihood judgements in CS-1 to CS-4 are mine. CS-3's network is ordinary engineering (a PRV discharging through a short spool into a tank). CS-2 needs a static head inside a narrow band (here 30-31 m).

## 9. The owner's answers (2026-11-28)

The owner's words: "yes, start A1 and go with your recommendations. B8- leave for future work. OW-2 mark resolved. OW-9 is completed. OW-8, im too lazy to figure out how to verify, you do it. OW-6 works. CS-11 cannot test yet. OW-7 make the link." The B numbers are the decisions as the session listed them in chat, here by item.

| Item | Answer | What follows |
|---|---|---|
| §2 (A1: SC-3, SC-4) | Build it | Being built (tier 3) |
| B1: OW-1, with CS-5 | The recommendation: S stays on the pumps' suction side whatever the case's flow | Built after §2–§4, tier 3, with CS-5's refusal of a member facing the wrong way; recorded in `pump-groups.md` §14 and the roadmap |
| B2: CS-2 | The recommendation: keep EPANET 2.2's rule (the owner's decision of 2026-10-23 stands) and fix the words | In §3's slice |
| B3: OW-3 | Accepted as built | Roadmap updated |
| B4: OW-4 | Kept as built | Roadmap updated; item 107 was already settled |
| B5: OW-5 | Accepted as built, with a height budget for the pump card | The budget goes into §4's slice |
| B6: CS-6 | Left (no one-time correction, D14) | Closed |
| B7: CS-15 | One walk-through together later | Open, not scheduled |
| B8: CS-4 | Leave for future work | Roadmap §1 updated |
| OW-2 | Resolved | `open-defects-2.md` §2 and the roadmap updated |
| OW-6 | "works" | Recorded in the roadmap's §5 |
| CS-11 | Cannot be tested yet | Recorded in the roadmap's §5 |
| OW-7 | Make the link | Done: a 999-component, 1,494-connection ladder (`Phone speed test`), checked to open on the live site in an emulated Pixel 7 (1.9 s) and to solve there (converged, 266 iterations, 7.85 s, method 1.6.2); sent to the owner; result pending |
| OW-9 | Done by the owner | See below: one of the four required names does not match a check |
| OW-8 | The session runs the checks | See below |

**OW-9, as set.** *Protect-main* now requires four status checks. Three match checks the workflow reports: *API (pytest, ruff, mypy)*, *Web (svelte-check, lint, vitest)* and *History line*. The fourth, `End-to-end (Playwright, ${{ matrix.project }}, ${{ matrix.shard }}/6)`, is the shard job's name template from `ci.yml`; GitHub reports each shard under its expanded name, such as "End-to-end (Playwright, desktop, 3/6)", so no check ever has that name, and every pull request would wait on it. It should be *End-to-end (Playwright, desktop + mobile)*, the summary job that passes only when every shard did (`workflow.md` §4.2). Until it is changed, `workflow.md` §4's sentence that GitHub does not enforce merge-on-green stays.

**OW-8, the checks after the deploy (TSD §11.4 items 3 to 5)**, run by the session on 2026-11-28 against the service at `322db41`:

- **Item 3, the client address: fails. Every client shares one bucket.** The rate limiter counts `/api/v1/solve` by path whatever the method, so a GET there is counted and answered 405 when allowed, 429 when the bucket is full. The session's container (160.79.106.146) sent 60 invalid bodies (400 each); the 61st, one with `X-Forwarded-For: 203.0.113.7` and a GET all got 429. A second network, Anthropic's fetch service (34.133.39.13), then sent GETs:
  - while the container's bucket was full: 429, with Retry-After 46 and 44, which is the container's bucket's clock (its first hit about 14 s earlier);
  - as a control, with nothing held: 405, so its requests reach the app when its bucket is free;
  - the control's one GET then took one of the container's 60 slots: in the next hold, the container's 60th request within the minute got 429;
  - with the container's bucket held full without gaps (about three requests a second): both GETs got 429, with Retry-After 35 and 33, again the container's clock.

  So two networks are counted under one key: on the deployed service every user shares one bucket of 60 rate-limited requests a minute and one solve at a time (TSD §11.2). The local check of 2026-10 had the proxy simulated; this is the first check on Cloud Run. The cause needs TSD §11.2's echo service, in the owner's project: is the proxy's address outside the image's `FORWARDED_ALLOW_IPS`, or does Google's front end append its own address after the client's? Since the bucket is shared, the session's three holds also kept every other user's requests out while the bucket was full: about a minute each, about three minutes in all, between 19:39 and 19:48 UTC.
- **Item 4, the logs:** not reachable without the owner's project; two read-only `gcloud logging read` commands go to the owner with the echo service's.
- **Item 5, the site: passes** in Chromium at 1280×800 and emulating a Pixel 7. The first example opened and solved (200); every request went to `opensolve-pipe.pages.dev` or the API; no cookies and no `Set-Cookie`; the HTML of `/` and `/p` holds no `cloudflareinsights`, `email-decode` or beacon script; `/p` carries `_headers`' `Cache-Control` with `no-transform`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` and `frame-ancestors 'none'`. A physical phone and Safari were not tried (CS-11).
