> Discipline findings for [`../build-density.md`](../build-density.md), written 2026-10-30 against the running app before the build (`5693197`). Paths under `/tmp/claude-0/` are the reviewer's scratch evidence, not kept. The proposal's §4 says what was adopted.

# Build panel: dark-cockpit review

Method: Playwright DOM inventory of the Build pane (`findings/cockpit-probe.cjs`, `cockpit-probe2.cjs`, results in `cockpit-probe*.json`). Shots are in `findings/shots/cockpit-{desktop,mobile}-*.png`. Desktop pane is 747 px (694 px with the case bar). Mobile pane is 646–699 px, fold at y 783.

## 1. What is loud in the normal state (should be quiet)

| Element (normal state) | Desktop | Mobile | Evidence |
|---|---|---|---|
| Static hints, always shown | P1 7 = 192 px; basin 17 = 512 px; RV1 9 = 336 px | basin 512 px; RV1 544 px | `cw-B1`, `all-RV1` |
| Repeated hints: "Above the project datum." on every component; "Names are the same in every case." under every name in a scenario | 16–32 px each | same | `sc-F1` |
| Case bar prose ("Edits change the base case and every scenario…") | 53 px row, always | – | `cw-P1` |
| Scenario banner (the same prose on every component) | **106 px**, 14 % of pane area | **198 px**, 29 % of pane | `sc-P1` mobile |
| Result strip frame: border, bg, uppercase "LAST SOLVE" heading, units inside wrapped labels | 98–138 px, 13 % of pane area | 114–138 px, 19 % of pane area; reservoir uses 114 px for **one** value | `cw-B1` |
| Component actions row; **Delete in red at rest** | 44 px | 56 px + gaps | every shot |
| Tabs 44 + breadcrumb 52 + bottom bar 61 | 157 px of chrome | same | – |

On mobile the first field sits at y 239 (y 292 with a scenario), so only 2–3 of 6–44 fields are above the fold.

## 2. Exceptions: what is raised today, and how strongly

- **Out of date** (`pt-P1-stale`): a 16 px amber chip with an area of 2 429 px², which is **3 % of the strip** and smaller than the "LAST SOLVE" heading. The old values only turn grey (slate-500 at full size), so a stale 22.76 m still reads as a number you can use. Salience is inverted.
- **Flags** (`flag-ptP1`): shown in the strip with a severity icon. This works (290 px on mobile). But `invalid` and `warning` use the **same triangle in red or amber, and the text names no severity**, so severity is carried by colour alone. On the mobile Results tab, stale (amber triangle) and invalid/error (red triangle) are also told apart by colour only.
- **Setpoint not met** (`flag-F1`): "It is open: it cannot hold its flow setpoint (3000 L/s)" is an *info* flag (slate circle). The Flow setpoint field still shows 3000 with no actual value (1 218 L/s) next to it. Because the pane keeps its scroll position after Solve, the strip and its flag were scrolled up under the breadcrumb (y −7…119), so the flag was **not visible at all**.
- **Topology errors** (`err-T1`): Tee T1 has 2 of the 7 errors ("Run outlet… not connected"), but **nothing in Build says so**. The strip is simply absent, and the only signal is a red icon on the Results tab.
- **Scenario not solved** (`sc-P1`, `sc-F1`): the strip silently disappears. Only the Results pane says "has not been solved yet".
- **Scenario changes** (`scs-BP-changed`): the teal input border plus a "Changed · Base: Closed · Reset" row (36 px) is good, and it is worded. But on the bypass valve both changed fields sit **below the fold** (y 752 on desktop, y 1060 on mobile). Meanwhile the 106 to 198 px of generic banner prose above them says nothing about this component.
- **"default" labels** (D10): some are in select text ("Default: ideal…"), which is good. Others are in hint prose: the tee's "…via the fluids library); **the default**." and the ports' "Default size for new piping here… **NPS 24**", which is dynamic data styled as `.hint`.

## 3. Recommendations

1. **Quiet the normal state**:
   - Drop the uppercase "LAST SOLVE" heading and the strip border/bg in the normal state.
   - Put units with the values: "Flow 949.3 L/s · Head 33.48 m · NPSH margin 2.155 m".
   - Make Delete neutral, or move it to an overflow menu; red only in the confirm dialog. Red stays reserved for invalid results and errors.
   - Replace the scenario banner with one line, about 32 px, in the strip slot: "Scenario *Winter* · 2 values changed here · Base case". The case bar already carries the teal mode stripe.
   - Remove the repeated hints (datum, names-shared).
2. **Raise every exception at the element, worded, with a shape for each severity**:
   - Invalid: octagon. Warning: triangle. Info: circle.
   - Prefix the text with "Invalid:", "Warning:", "Note:".
   - Out of date replaces the strip's state: "Out of date: values from the last solve" on the first line. Values are dimmed *and* marked, e.g. "(was 22.76 m)" or a hatched background, not grey alone.
   - Fill the strip slot with "Not solved: 2 problems here (Run outlet not connected…)" for topology errors, and with "Not solved in this case" for an unsolved scenario. A missing strip must never be silent.
3. **Solved value beside its input** for every target or command input: flow setpoint, speed or setpoint of a VFD pump, PRV/PSV pressure, status. Example: `Flow setpoint [3000] L/s   solved 1 218 L/s ⚠ not held`. The strip then keeps only results that have no input (flow, head, Δp, NPSH margin). Commanded and actual sit together, which is the primary cockpit pattern.
4. **Exposed vs disclosed**:
   - Exposed: the defining and state-setting inputs (status, control, setpoint, curve, level, K/Cv), plus any field that is in error, changed in the scenario or referenced by a flag.
   - Disclosed: elevation of inline items, port sizes and the repeated ports notes, loss overrides, library references.
5. **After a solve**, bring the open component's strip into view, or make the compact strip sticky (about 40 px), whenever it gained a flag, error or stale state.

## 4. The draft's items 3, 5 and 6

- **Item 3, help on focus**: yes for the quiet state, but classify by *content*, not by the `.hint` class. Default markers (D10) and dynamic data ("connected pipe: NPS 24") must stay visible. The tee's "the default" would vanish today. Problems to solve:
  - On touch, focusing a select opens the native picker, which covers the help, so select help is never seen on a phone.
  - Revealing 16–48 px on each focus shifts the layout during Tab traversal.
  - Prefer a per-label "?" toggle (aria-expanded) plus one "Show help" switch for the whole pane, remembered per viewer. That switch is the cockpit "lights test".
  - Consequence hints ("changing the type resets the setpoint to 0") should appear when the change is made, as a note.
- **Item 5, sections that open when set**: open on **exceptions** only (error, Changed in the scenario, a field named by a flag). Do not open on "holds a set value": in a built model such as the condenser plant almost everything is set, so every section would open. That gives no density gain, and spatial memory varies from component to component. The closed summary must word the exception, e.g. "Losses · 2 set · 1 changed", not tint it. Never auto-open or close while the user is editing inside the section.
- **Item 6, compact strip**: agree on 1–2 lines and about 40 px, which is what makes a *sticky* strip affordable.
  - Flags and errors must not be compressed into that line. They get their own rows under it, uncapped for invalid. Today only 2 are shown and the rest go to the trace.
  - Out of date must restyle the whole strip, not add a chip.
  - The compact line still needs its accessible group name. An empty strip slot must carry the "not solved" reason.
