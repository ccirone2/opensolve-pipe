# Speed-controlled (VFD) pumps: design proposal

**Status: slice 1 built** (Controlled Flow, CLAUDE.md D11): the model contract in `0fbe7cc`, the solver, reference cases, differential fuzz, web form and results in the commit that follows it. The owner's answers are at the end of §10. Slices 2 and 3 (§4.10) are designed here and not built. Where the build departs from or adds to this text, CLAUDE.md D11 and TSD §5.4 record it. One departure: two flow controls in series with equal setpoints (§4.6, §5) end not converged only when both could hold the common flow, the band where the pressure between them is undetermined; outside it both pumps are at a speed limit (or the pump at maximum speed with the FCV open), the flow differs from the setpoint, the state is unique and the solve converges.

Written against `c06ce88` (no solver change since `cd715ba`) by a design workflow: two research passes (the solver code, and how AFT Fathom, Bentley WaterGEMS, EPANET and PIPE-FLO define controlled pumps, in `vfd-industry-conventions.md`), three independent designs and a three-judge panel; the curve_a numbers in §4.3 were checked with a scratch script.

Where this comes from: it starts from Design 3, the flow-control first slice, which all three judges rated best. From Design 2 it takes the block-triangular argument, the exact uniqueness test, the bracket and the pure `LinkState.law` override. From Design 1 it takes the published speed-order rule, the EPANET substitutes, the zero-flow bounds for slice 2 and the independent rule checker. Each judge finding is resolved in §9.2.

---

## 1. Summary and recommended first slice

**Slice 1: Controlled Flow.** This is the PRD §3.1.2.1 row "VFD maintains constant flow rate".
- A drive varies the pump's speed to hold the pump's own volumetric flow Q_set, suction → discharge.
- The speed stays within [`control.minSpeed`, `speed`]. For a controlled pump, the existing `speed` field becomes the maximum speed.

**How it works:**
1. **While regulating,** the pump link is the existing `FIXED_FLOW` link. The FCV already uses it (`status.py:265-282`), and so do system-curve pumps (`status.py:302-303`). There is no GGA numerics change.
2. **The speed** is recovered after the solve as the unique root of s²H₀(Q_set/s) = EGL_d − EGL_s on [s_lo, s_max], where that head rises with speed (§4.3). This is exact, not an approximation, because the speed enters only the pump's own head row (§4.2).
3. **At a speed limit** the pump is exactly the v1 fixed-speed pump at that limit:
   - at maximum speed it uses the link's own law, so it is bit-identical;
   - at minimum speed it uses a per-solve law override.
4. **Every rule** compares only flows and head differences: the "difference class" of fixed pumps, check valves and FCVs. So `_holding_regions`, `_closed_bound` and `_level_changes` membership are untouched.
5. **Closed and re-opening** use the unchanged v1 pump code at s_max:
   - `pump_status` (`status.py:116-128`);
   - the zero-flow bound `−s_max²H₀(0)` in `_border_constraints` (`status.py:614-616`);
   - `zero_flow_openings`, which sets OPEN;
   - `_level_changes.new_status` (`status.py:797-802`).

   At zero flow a flow controller is at maximum speed, so these are the right physics.
6. **Projects without `control` give identical results.** This is proven by the corpus comparison of TSD §10.4 (3,092 projects).

**Deferred, with reasons**

| Item | When | Why |
|---|---|---|
| Discharge-pressure control (constant-pressure boosting) | Slice 2 | Its rules compare a head with a setpoint, so it needs the PRV-class level logic, which is the most fuzz-sensitive part of `status.py`. It also needs a velocity-head coupling fix shared with PRVs (§4.10). |
| Differential-pressure control | Slice 3 | It needs a `HeadOffsetLaw` in ACTIVE (it reuses slice 1's law override) and carries a lagged negative-slope risk (§4.10). |
| Suction-pressure control | Later | PSV class (`FIXED_UPSTREAM_HEAD`). No PRD row asks for it. |
| Remote control node or remote pipe | Later | Holding a node the link does not own breaks the GGA invariants (`gga.py:457-458`, `585-586`). It needs the bordered system of US 7,013,248. |
| Mass-flow setpoint, overspeed (s > 1), sleep or stop at low demand | Later | No PRD row. Overspeed extrapolates the affinity laws above the rated curve, and the SDD bounds 0 < s ≤ 1. |
| Lead/lag stations, equal-speed batteries, total station flow | Later | Non-unique by nature (Elhay et al. 2025). Needs a review of US 8,265,911 (active). |
| Reduced-speed efficiency correction | Separate decision | It would change fixed reduced-speed pumps too (Q10). |

**Why this order (GOALS):**
- §6: narrow, complete, verified slices.
- §5: the "Verifiable" gate. Every slice-1 state is checkable in closed form and by EPANET, with no solver code.
- §3: correctness first, so the riskiest logic (pressure modes in free-level sections) waits for its own verification.
- §5 maintenance weight: slice 1 touches no level logic.
- §4.3: no existing link changes.

---

## 2. User-facing semantics

### 2.1 Modes in slice 1
- **Fixed speed.** `control` is omitted. This is v1 behaviour, unchanged.
- **Flow.** `control = {mode: "flow", setpoint, minSpeed}`.

This follows the convention every surveyed tool uses: the setpoint is imposed in the network solve, and the speed is reported as a result.
- AFT: https://www.datacor.com/resources/to-affinity-and-beyond
- Bentley Fixed Flow VSP: https://docs.bentley.com/LiveContent/web/Bentley%20WaterCAD%20CONNECT%20Edition%20Help-v1/en/GUID-C7B51BFA-2FA0-4A1E-A53F-F61A93A61B27.html

### 2.2 Setpoint
- Q_set is the volumetric flow through the pump, suction → discharge, in m³/s: 0 < Q_set ≤ 100 m³/s.
- The upper bound is the model's existing flow bound (`FCV_SETPOINT_RANGE[1]`, `models/pumps.py:12`).
- **Q_set = 0 is excluded.** With the integral check holding zero flow, every speed with s²H₀(0) ≥ H holds it, so the speed would not be determined by the inputs.

### 2.3 Speed limits and defaults

| Field | Meaning when controlled | Default | Source |
|---|---|---|---|
| `speed` | Maximum speed s_max, as a fraction of the curve's rated speed | 1.0 (unchanged) | By definition the entered curve is the rated curve. EPANET 2.2: "the original pump curve … has a relative speed setting of 1" (https://usepa.github.io/EPANET2.2/3_network_model.html). AFT: the curve "is always assumed to be the 100% speed curve" (https://docs.aft.com/fathom/PumpPropertiesWindow.html). Bentley "Relative Speed Factor (Maximum)" defaults to 1.0 (https://docs.bentley.com/LiveContent/web/Bentley%20HAMMER%20SS6-v1/en/GUID-DA491001-73BE-4B16-9729-A3F9D8626DA2.html). The bound 0 < s ≤ 1 is unchanged (SDD §4.8). |
| `control.minSpeed` | Minimum speed s_min | **None: required** | No tool or paper cites a default. AFT makes it optional with no value. InfoWorks WS Pro requires a minimum and a maximum (https://help.autodesk.com/cloudhelp/2027/ENU/WSPro-Help/files/GUID-EF90E86C-328E-4BB3-82B4-0D5BBA636862.htm). Bentley and EPANET have none. GOALS §4.1 forbids an uncited number. **Owner decision (Q2).** |
| Cross-field rule | 0 < minSpeed < speed ≤ 1 | — | A model rule (400), published as `x-ordered-fields` (§3.3). |

Within these limits the drive regulates on [s_lo, `speed`], s_lo = max(minSpeed, Q_set/x_mono), where the head at the setpoint rises with speed (§4.3); s_lo exceeds minSpeed only when Q_set/minSpeed lies beyond x_mono on the curve's end tangent. The curve test of §4.3 makes the speed holding a flow against a head unique there; it does not make the operating state unique on a drooping curve (§4.3, §5).

### 2.4 States

| `control.state` | Solver status | `PumpResult.status` | `speed` reported | Meaning |
|---|---|---|---|---|
| `active` | ACTIVE | running | s*, solved | Holds Q = Q_set. |
| `max_speed` | OPEN | running | s_max | Holding Q_set needs more than s_max. Runs as the fixed-speed pump at s_max with Q < Q_set (Bentley "Fixed Speed Override": https://docs.bentley.com/LiveContent/web/Bentley%20WaterGEMS%20SS6-v1/en/GUID-31A4A446A15F448E8C7BD7C3B8D1249E.html). |
| `min_speed` | MIN_SPEED (new) | running | s_min | The system drives at least Q_set even at s_min. Runs at s_min with Q > Q_set. The pump keeps running and does not stop (Q3). |
| `no_flow` | CLOSED | no_flow | s_max | The head across it exceeds s_max²H₀(0), so the integral check holds it at zero flow. |
| `off` | CLOSED, fixed | off | `speed` (the web shows "—") | The control is not applied. The trace says so. |

### 2.5 Flags
- **New: `PUMP_SETPOINT_NOT_MET`, severity info.**
  - Raised when the state is `max_speed`, `min_speed` or `no_flow` and |Q − Q_set| > Qtol.
  - The severity matches `CONTROL_VALVE_SETPOINT_NOT_MET` (`flags.py:20-37`), because a pump at a limit is a physically valid state.
- **Existing flags, evaluated at the actual speed:**
  - `PUMP_OUTSIDE_CURVE` with details {flow, speed};
  - `PUMP_FLOW_REVERSAL` (no_flow, at s_max);
  - `CAVITATION`, `NPSH_NOT_CHECKED` and `BELOW_VAPOR_PRESSURE`;
  - `UNDETERMINED_PRESSURE`, which lists the controlled pump as a driver of a floating section.
- **New topology issue: `CONTROLLED_PUMP_CURVE` (422).** Raised only where the speed root is genuinely not unique (§4.3).
- **No low-speed warning.** No cited threshold exists. The DOE/HI guide warns only qualitatively (https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/variable_speed_pumping.pdf), and ORNL's 66.7 % concerns efficiency (https://www.osti.gov/servlets/purl/1649114).

### 2.6 Results
- `PumpResult.speed` is the actual speed. This is PRD §4's "actual speed when VFD-controlled".
- `PumpResult.curve` is sampled at the actual speed, so it passes through the operating point.
- Range, η = η₀(Q/s), NPSHr = s²NPSHr₀(Q/s) and shaft power are all at the actual speed.
- New `PumpResult.control` = {mode, setpoint, state, setpointAchieved}.

---

## 3. Model and schema

### 3.1 API models (`apps/api/src/opensolve_pipe/models/components.py`)

```python
class PumpControl(CamelModel):
    """Speed control by a drive (VFD): the speed varies between min_speed and the pump's
    speed (its maximum) to hold the setpoint."""
    mode: Literal["flow"]                      # required; slices 2-3 widen it
    setpoint: float = Field(gt=0, le=FCV_SETPOINT_RANGE[1],
        description="Flow through the pump, suction -> discharge, m³/s")
    min_speed: float = Field(gt=0, lt=1.0,
        description="Lowest speed the drive runs the pump at, fraction of the curve's rated "
                    "speed; no default (a property of the drive)")

class Pump(BaseComponent):
    """Centrifugal pump with an integral check (no reverse flow): fixed speed, or
    speed-controlled when `control` is given."""
    ORDERED_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (("control.minSpeed", "speed"),)
    speed: float = Field(default=1.0, gt=0, le=1.0, description=
        "Speed as a fraction of the curve's rated speed; for a speed-controlled pump, its "
        "maximum speed")
    control: PumpControl | None = Field(default=None,
        description="Speed control (VFD); omitted: fixed speed")
    # model_validator: control.min_speed < speed, else
    # "minSpeed must be below speed (the maximum speed of a speed-controlled pump)"
```

- The discriminator tag stays `"pump"`, so `_component_tag` and `componentSchemaName` are unchanged.
- `mode` is required now, so every link carries it and no later default has to be inferred.

### 3.2 Results (`models/results.py`, `services/solver/flags.py`)
- `PumpControlResult(OutputModel)`: `mode`, `setpoint` (m³/s), `state: Literal["active","max_speed","min_speed","no_flow","off"]`, `setpoint_achieved: bool | None` (None when off).
- `PumpResult.control: PumpControlResult | None`, None for a fixed-speed pump.
- `PumpResult.speed` description becomes "Speed the pump runs at: the set speed, or a speed-controlled pump's solved or limit speed".
- `FlagCode` gains `PUMP_SETPOINT_NOT_MET`, with severity info in `FLAG_SEVERITY`, covered by `test_flags_audit.py`.
- Results are not part of links, so slice 2 can add `controlled_value` without any migration.

### 3.3 Published rules (D10)
- `_component_schema_extra` (`components.py:18-42`) publishes `x-ordered-fields: [{"lower": "control.minSpeed", "upper": "speed", "strict": true}]`.
- The web needs:
  - a reader `orderedFields()` in `utils/model-rules.ts`;
  - the Ajv keyword declared in `utils/validate.ts:51`;
  - a `modelRuleIssues` entry (381-468).
- The API needs:
  - a pytest in the pattern of `test_schema_rules.py:85-107`;
  - a controlled-pump instance for `:44-47`;
  - the openapi copy check at `:149-155` kept passing.
- CLAUDE.md D10's list of extensions gains `x-ordered-fields`.
- The setpoint and minSpeed bounds are plain JSON Schema on `PumpControl`, so no `x-setpoint-bounds` entry is needed.

### 3.4 Topology issue `CONTROLLED_PUMP_CURVE`
- It sits in `builder.py` next to `UNKNOWN_PUMP_CURVE` (220-230).
- It is raised for a controlled pump whose curve fails the exact uniqueness test of §4.3. The message names the pump, the curve and the flow interval.
- Added by the owner's decision of 2026-10-23 (TSD §12): `CONTROLLED_PUMP_SETPOINT`, after this test on a curve that passes it, for a setpoint Q_set ≥ s_max·x_mono, which no speed in the drive's range controls (§4.3). The message names the pump, the setpoint, the maximum speed, the curve, x_mono and the bound s_max·x_mono.

### 3.5 schemaVersion decision
Facts:
- An optional field with a `None` default puts no `"default"` in `/openapi.json`, so `fillDefaults` (`validate.ts:209-237`) adds nothing.
- So the v1 fixtures decode and re-encode byte-identically (`fixtures.test.ts:36-50`, `82-87`), and `test_released_links.py` is unchanged.
- But a link that contains `control`, opened by an app released before this change, fails Ajv's "unknown field" check (`validate.ts:127-128`). The user then sees `LinkError('invalid')`, not SDD §5.2's "newer version, reload" message. The API also rejects it (`extra="forbid"`, `base.py:19`).

**The rule I apply:** schemaVersion counts the formats a released app can meet. Bump when either of these holds:
- old links would stop decoding (SDD §5.2 "Longevity"); or
- new links would be rejected by a released app's strict reader (SDD §5.2 "Newer links").

Every reader is strict, so any new field, and later any new `mode` value, bumps once an app with the older format has been released.

**Decision:**
- **If slice 1 merges before the first deployment or tagged build** (CLAUDE.md: "Not yet deployed"): keep schemaVersion 1. No released app can meet a link with `control`.
- **Otherwise**, bump to 2:
  - `MIGRATIONS[1] = (p) => p`;
  - `CURRENT_SCHEMA_VERSION = 2` and `SCHEMA_VERSION = 2`;
  - **`schema_version: Literal[1, 2]`**, so v1 bodies sent directly to the API still validate. This holds only while the migration is the identity. `Literal[2]` alone would reject them, which was the flaw in Design 3.
  - new `schema-v2.txt`/`.json` fixtures that contain a flow-controlled pump, with the v1 fixtures untouched;
  - `test_released_links.py` solves both.
- Q5 asks which applies.

### 3.6 METHOD_VERSION decision
- Bump `version.py:17` to **1.1.0**. Changelog entry: "Adds speed-controlled pumps (flow setpoint): the setpoint flow is imposed in the network solve and the speed recovered from the affinity laws, within a minimum and maximum speed. Results of projects without speed control are unchanged (corpus comparison)." As built, the entry says flows, heads, pressures and statuses, and a second line describes the outer loop's oscillation fallback added after the slice-1 review (`version.py`).
- Rule: `version.py` requires a bump only when results could change, and none do. But GOALS §4.3 says "each project records the calculation-method version that produced its results". A controlled-pump result stamped 1.0.0 would name a version whose changelog has no speed control. Traceability ranks above usability (GOALS §3).
- Cost: `MethodVersionNotice` appears once on old links (`ResultsPanel.svelte:92-94`), with the "unchanged" text.

### 3.7 Generated types and documents
- Regenerate with `apps/web/scripts/gen-api-types.sh`. The result is `Pump.control?: PumpControl | null`, which is optional, so `factory.ts:280-288` is unchanged.
- In the same change:
  - CLAUDE.md gets a new D11 (this design) and an updated D5 deferred list;
  - PRD §3.1.2.1: Controlled Flow released; PRD §4 pump results;
  - SDD §4.8 replaces the "Later: controlMode" line;
  - TSD §5.4 and §12.

---

## 4. Solver formulation and status rules

### 4.1 Notation
- Pump link k runs from suction s to discharge d (`builder.py:537-552`). Q > 0 means forward flow.
- H = EGL_d − EGL_s is the head the rules see. In closed-off and floating sections it is the section shifts (`status.py:343-354`).
- H₀(x) is the rated PCHIP with its tangent extension (`pumps.py:31-57`). F(σ, Q) = σ²H₀(Q/σ), which is `PumpCurveModel.head` (`pumps.py:99-102`).
- s_max = `speed`, s_min = `control.minSpeed`.
- F_max = F(s_max, Q_set), F_min = F(s_min, Q_set), S_max = F(s_max, 0), S_min = F(s_min, 0).
- s_lo = max(s_min, Q_set/x_mono), at most s_max, and F_lo = F(s_lo, Q_set) (§4.3; F_lo = F_min when s_lo = s_min).
- Htol = 1e-4 m and Qtol = 1e-8 m³/s (`status.py:77-80`: EPANET 2.2's Htol and Qtol). No new tolerance is introduced.

### 4.2 Why imposing the setpoint and recovering the speed is exact
Treat s as a Newton unknown with one extra row, r = Q_k − Q_set. The pump's head row is e_k = (H_d − H_s) − s²H₀(Q_k/s), with ∂e_k/∂s = −s·ψ(Q_k/s), where ψ(x) = 2H₀(x) − xH₀′(x).

The speed s appears in no other row. So, with columns (Q, H | s):

  J = [[J_red, 0], [∂e_k/∂(Q,H), −sψ]], so det J = ± det J_red · sψ.

Where ψ ≠ 0, the Newton iterates of (Q, H) are exactly those of the reduced system. The reduced system is the network with the pump replaced by a fixed flow: `LinkMode.FIXED_FLOW`, and the EPANET 2.2 FAQ's "specific flow" substitute (https://usepa.github.io/EPANET2.2/13_questions.html). The speed follows from e_k = 0 at convergence. So the converged state equals the simultaneous solve, and an ACTIVE inner solve never evaluates the curve. This argument (Design 2) goes into the methods summary.

### 4.3 Speed uniqueness and the bracket
**Lemma.** d/dσ F(σ, Q) = σ·ψ(x), with x = Q/σ.

**Exact test, at build time, per curve used by a controlled pump.** ψ > 0 must hold on [0, x_last], where x_last is the largest point flow.
- On each PCHIP piece, H₀ is a cubic in t = x − x_i (PPoly coefficients `.c`), so ψ is a cubic. Its minimum is at the ends or at the real roots of a quadratic.
- On the left tangent, ψ is linear.
- ψ(0) = 2H₀(0) also requires H₀(0) > 0.
- Data that do not increase pass automatically: PCHIP preserves monotone data (Fritsch–Carlson 1980, already cited in `methods.py`).
- A failure gives `CONTROLLED_PUMP_CURVE`. Drooping curves with ψ > 0 are accepted.

**Beyond the last point.** The right tangent H₀ = h_e + m(x − x_e) gives ψ = 2h_e − 2m·x_e + m·x.
- For m < 0, ψ reaches 0 at x_mono = 2(x_e + h_e/|m|) = 2x₀, twice the tangent's zero-head flow.
- For m ≥ 0, ψ only grows from its checked value at x_e, so x_mono = ∞.

**Bracket.** s_lo = max(s_min, Q_set/x_mono), at most s_max (below it since the owner's decision of 2026-10-23, which rejects Q_set ≥ s_max·x_mono as `CONTROLLED_PUMP_SETPOINT`, §3.4). Then F(·, Q_set) is strictly increasing on [s_lo, s_max].
- If s_lo > s_min, F decreases on [s_min, s_lo], so F(s_lo) < F_min. On that stretch raising the speed lowers the flow: at a fixed system Sys, Q(s) solves F(s, Q) = Sys(Q), so dQ/ds = (∂F/∂s)/(Sys′ − ∂F/∂Q), whose denominator is positive where F falls with Q and Sys rises; dQ/ds then has the sign of ∂F/∂s. No stable flow controller holds a speed there.
- So any H in [F_lo − Htol, F_max + Htol], F_lo = F(s_lo, Q_set), has exactly one root on [s_lo, s_max], up to the Htol band, and rule A2 tests F_lo (§4.5). A head in [F_lo, F_min) also has a root on (s_min, s_lo), on the falling stretch; it is not used.
- As built, A2 first tested F_min. The slice-1 review found the band [F_lo, F_min) sent to minimum speed although a speed in (s_lo, s_max] held the setpoint (curve_a, Q_set 0.03 m³/s, minSpeed 0.15, head −3.3 m at Q_set: speeds 0.2534 and 0.1944 hold it, the solve reported 0.15); A2 now tests F_lo.

**What the test guarantees.** One speed per head at a given flow on [s_lo, s_max]: a unique speed root. Not a unique operating state. §4.6's argument also needs F(σ, ·) to fall with Q; on a drooping curve (head rising from H₀(0) to a peak) it does not everywhere, and the limit rules X2, N2 and C1 close the pump against s²H₀(0), as v1 closes a fixed pump (EPANET 2.2 `pumpstatus`). A running state whose head lies between s²H₀(0) and the curve's peak is then not found: at maximum speed the result is no flow (`PUMP_FLOW_REVERSAL`, invalid); at minimum speed N2 closes against S_min, C1 re-opens against S_max and the solve ends not converged. The review reproduced both with the curve through (flow m³/s, head m) (0, 40), (0.01, 42), (0.02, 41), (0.03, 35), which passes the ψ test. A v1 fixed pump gives the same no-flow result; EPANET 2.2 rejects such curves (error 227). TSD §12 lists it as Open.

**Check on the suite's curve_a** (scratch script):
- x₀ = 0.067, x_mono = 0.134 m³/s, min ψ on the points = 89.5 m.
- With Q_set = 0.0335 m³/s and s_min = 0.4: F_min = −2.68 m (beyond run-out), s_lo = 0.4.
- For H = 30 m, s* = 0.96817, unique, and F is monotone on [0.4, 1].
- Design 3's `PUMP_CONTROL_SETPOINT_RANGE` would have rejected this valid case.

### 4.4 Inner-solve form of each state

| Status | `LinkState` | Equation | GGA path |
|---|---|---|---|
| ACTIVE | `FIXED_FLOW(Q_set)` | No energy row. Demand Q_set at s, supply at d. | `special_flows` (`gga.py:650-665`). `_supply_side` needs both ports grounded (321-325). `_drives_circulation` floats a loop with no fixed head (328-335). |
| OPEN (max speed) | `NORMAL` | The link's own `PumpLaw(curve, s_max)` | Newton link with the Jacobian floor (`gga.py:100-109`), the same object as v1 |
| MIN_SPEED | `LinkState(NORMAL, law=pump.min_law)` | h = −F(s_min, Q) | Newton link |
| CLOSED | `CLOSED` | — | — |
| Forced (system curve) | `FIXED_FLOW(q)`, written last | — | Unchanged (`status.py:302-303`) |

- `LinkState` gains `law: LinkLaw | None = None`, meaning "NORMAL with this law in place of the link's own".
- One helper, `law_of(link, state)`, replaces `link.law` at the five sites that read a NORMAL link's law: `gga.py:361`, `570`, `575`, `600` and `status.py:449`.
- Nothing on `BuiltNetwork` is mutated, so system-curve points and `_warm_start` carry no speed state.
- `PumpData` (`builder.py:101-108`) gains `control` and `min_law`; `min_law` is built once.

### 4.5 State machine
The first test that holds wins.

| From | Rule | Test | To | Source |
|---|---|---|---|---|
| ACTIVE | A0 | The GGA starves the link (a side reaches no fixed head, `gga.py:465-507`) | OPEN | Own departure. Valves close here (`status.py:368-369`). A flow controller that sees Q = 0 < Q_set runs to maximum speed, where it is the v1 pump. |
| ACTIVE | A1 | H > F_max + Htol | OPEN | In the style of fcvstatus; Bentley Fixed Speed Override |
| ACTIVE | A2 | H < F_lo − Htol, F_lo = F(s_lo, Q_set) (= F_min when s_lo = s_min) | MIN_SPEED | Mirror of A1 on the stretch the drive can regulate on (§4.3; EPANET has no speed range) |
| ACTIVE | A3 | Otherwise | ACTIVE | — |
| OPEN | X1 | Q ≥ Q_set | ACTIVE | EPANET 2.2 fcvstatus, XFCV → ACTIVE once q ≥ setting (https://github.com/OpenWaterAnalytics/EPANET/blob/master/src/hydstatus.c) |
| OPEN | X2 | Otherwise | `pump_status(OPEN, H, Q, S_max)` | EPANET 2.2 pumpstatus; v1 code unchanged |
| MIN_SPEED | N1 | Q ≤ Q_set | ACTIVE | Mirror of X1 |
| MIN_SPEED | N2 | Otherwise | `pump_status(OPEN, H, Q, S_min)`: CLOSED → CLOSED, OPEN → MIN_SPEED | v1 rule at s_min. Reachable only on a rising stretch, since Q > Q_set > 0. |
| CLOSED | C1 | Always | `pump_status(CLOSED, H, Q, S_max)`: OPEN if H ≤ S_max | v1 rule at s_max |

**Initial statuses:**
- on with a control: ACTIVE, not fixed. EPANET starts active control valves ACTIVE; the repository's control valves do the same (`status.py:254-262`).
- off: CLOSED, fixed.
- Forced (system curve): OPEN, fixed.

**Sections, existing logic:**
- Both ports in one closed-off or floating section: the rules apply on the shifts. In a floating section they are exact.
- One port in a section: the pump keeps its state.

**Fallbacks:**
- `_check_changes` (`status.py:1837-1870`) applies A1/A2 to ACTIVE pumps at the early iterate. The `ControlValve` assert at 1854 is limited to valves.
- `_open_bad_valves` (1873-1918) tries three passes in order:
  1. OPEN (for pumps this means maximum speed);
  2. MIN_SPEED, for pumps only, skipped for options with no pump;
  3. CLOSED.

  Valve-only networks follow today's exact option sequence.
- The GGA's undetermined message says "controls" when a pump is named. Text that names only valves is byte-identical.

### 4.6 Why the final state is unique, and why nothing chatters
Single pump, passive surroundings: the head the system needs, Sys(Q), increases with Q, and F(σ, ·) decreases with Q (not so everywhere on a drooping curve, §4.3). Then:
- ACTIVE holds ⟺ F_lo − Htol ≤ Sys(Q_set) ≤ F_max + Htol;
- OPEN holds ⟺ Sys(Q_set) > F_max;
- MIN_SPEED holds ⟺ Sys(Q_set) < F_min.

When s_lo = s_min (F_lo = F_min) the states partition outside 2·Htol bands. A boundary point satisfies both of its neighbours, which is EPANET's band behaviour. Design 3's scratch sweep found one final state from every start. When s_lo > s_min, ACTIVE and MIN_SPEED both hold for F_lo ≤ Sys(Q_set) < F_min: the drive at its minimum, passing more than Q_set, is saturated and stays there, and the drive at its root on [s_lo, s_max] holds Q_set. The solve starts ACTIVE and A2 keeps it there; a pump that other statuses' changes bring to MIN_SPEED in that band stays at MIN_SPEED. The band needs Q_set/s_min beyond x_mono, a negative pump head far out on the curve's end tangent (`PUMP_OUTSIDE_CURVE`). When Q_set/s_max itself lies beyond x_mono, s_lo is s_max and no speed in the range is on a rising stretch: a head above F(s_max, Q_set) + Htol gives max_speed (rule A1), and the pump at s_min passing more than Q_set can also satisfy the rules; both lie far out on the curve's end tangent and are flagged `PUMP_OUTSIDE_CURVE`, and which one the solve reports depends on its path (TSD §12, open item).

**Two flow pumps in series, P1 upstream with Q1 < Q2.** Let G(Q) = Sys(Q) − F₁(s_min1, Q) − F₂(s_max2, Q), which increases, with root Q_c. Then:
- (P1 active, P2 max) holds iff Q_c ≤ Q1;
- (P1 min, P2 max) holds iff Q1 < Q_c < Q2;
- (P1 min, P2 active) holds iff Q_c ≥ Q2.

The both-max and both-min states fall outside the two ends by the same argument. The state is therefore unique. Design 3's "smaller setpoint wins" holds only when Q_c ≤ Q1. The judge's "second equilibrium" holds only when the first does not.

With Q1 = Q2 the pressure between the pumps is undetermined, and every fallback returns to a state already tried, so the solve is not converged and names both. The message says the pressure between them is undetermined (over-controlled), whether the iteration stops at a converged state with one at a limit carrying the setpoint (`_over_controlled`) or with statuses cycling (`_equal_setpoints_note`: holding the cycling flow controls at their setpoints together leaves that pressure undetermined). AFT calls this "no solution" (https://www.datacor.com/resources/reference-pressure); PIPE-FLO calls it "Over Controlled".

Flow pump with an FCV, or with a downstream PRV: unique by the same monotonicity argument. Reference cases cover both regimes (§7).

### 4.7 Speed recovery
This runs after convergence, for ACTIVE only.
- Ĥ = clamp(H, F(s_lo, Q_set), F_max). The clamp is at most Htol, by A1 and A2 (A2 tests F_lo = F(s_lo, Q_set)).
- s* = `scipy.optimize.brentq(σ ↦ F(σ, Q_set) − Ĥ, s_lo, s_max, xtol=1e-14, rtol=4ε)` (Brent 1973), or the end value when Ĥ equals an end.
- So s* always lies in [s_lo, s_max] ⊆ [s_min, s_max]. The trace reports the residual |F(s*, Q_set) − H| ≤ Htol.
- Closed-form oracle for a linear curve H₀ = a − bx: s* = [bQ + √(b²Q² + 4aH)]/(2a). This is ORNL eq. (10) with c = 0.

**Speed reported:** ACTIVE s*; OPEN s_max; MIN_SPEED s_min; CLOSED s_max.

**Results changes:**
- `pump_result` (`results.py:545-717`) takes `s` from the state.
- `running` becomes status ∈ {OPEN, ACTIVE, MIN_SPEED} (`results.py:548-552`). Otherwise an ACTIVE pump would be `no_flow` with a false `PUMP_FLOW_REVERSAL`.

### 4.8 System curves (`system_curve.py`, no algorithm change)
- **The viewed pump's own control is replaced** by the forced flow, whatever its control (`status.py:236-238`, `302-303`). So H_sys has the same definition as for any pump, and the operating point lies on the curve at s*.
- **Other controlled pumps keep regulating.** `_warm_start` copies their statuses, MIN_SPEED included, and their laws follow from those statuses.
- **Series layouts.** In series, a forced flow that differs from B's setpoint pushes B to its max or min speed (§4.6). At q = Q_B exactly the point has no head (a gap), as today.
- **Default range:** 1.2·Q₀,max·`speed` = s_max (`system_curve.py:67-70`). Docstrings in `models/api.py:16-22` and `80-85` say so.

### 4.9 What changes where (slice 1)
- `network.py`: `LinkState.law`.
- `gga.py`:
  - `law_of` at four sites;
  - the message wording.
- `status.py`:
  - `Status.MIN_SPEED`;
  - `initial_controls`, `link_states`;
  - the `_update_controls` pump and starved branches: `if pump.component.control is None:` keeps today's code verbatim;
  - `_check_changes`, `_open_bad_valves`;
  - the `closed_off_sections` read.
- `pumps.py`: `uniqueness(curve) → (psi_min, x_mono, interval)` and `operating_speed(...)`.
- `builder.py`: `PumpData` fields and the topology issue.
- `results.py`, `trace.py`, `methods.py`, `flags.py`, models.
- Untouched: `pump_status`, `_border_constraints`, `zero_flow_openings`, `_level_changes`, `_holding_regions` and `_closed_bound`. They already do the right thing because OPEN means "at s_max".

### 4.10 Slices 2 and 3 (designed now, built later)

**Slice 2: discharge pressure.**
- **Setpoint.** Gauge static pressure at the discharge port, the D9 PRV convention. Every surveyed tool uses static pressure.
- **ACTIVE.** `FIXED_DOWNSTREAM_HEAD` on the pump link, with value z_d + p_set/ρg, the discharge connection as reference and c_d as coefficient. This is `active_state`'s PRV form, with exact m21 coupling (`gga.py:636-648`). The held node is the pump's own free discharge port, so the invariants at `gga.py:457-458` and `585-586` hold.
- **Rules.** Design 1's set, with reverse flow → CLOSED, and the pump added to the PRV-class condition at `status.py:370`.
  - A discharge pump with a port in a floating section ends **not converged**, unless it is closed at every level (Design 1). This fixes Design 2's case, which converged with an undetermined level.
- **Zero-flow bounds.**
  - One side known: S_eff = clip(H_set0 − H_s, S_min, S_max), from Design 1. Design 3 derived the same bound independently.
  - Both sides in sections: the convex bound H_s − H_d ≤ −S_max (Design 2). Design 1's "no constraint" can converge to a wrong all-closed state (R1 → check valve → pump → check valve → R2). The convex bound can only cause a spurious reopen, which fails safe as not converged.
- **Velocity-head coupling.**
  - The lagged term at `gga.py:787-793` converges at ratio 1/r, where r is the loss downstream of the port in discharge velocity heads.
  - With the web's default exit fitting, r > 1. A 1 m spool still gives r ≈ 1.2, a ratio of about 0.83 and about 110 iterations to 1e-9, against `max_iterations` = 100.
  - Fix it once, for PRVs and pumps together: add the exact slope where it is positive (r > 1). Measure it on the corpus first. It changes PRV iteration paths, so it ships with its own METHOD_VERSION bump and a corpus comparison within solver tolerance.
  - For r ≤ 1, the static pressure at the port does not rise with flow. The solve ends not converged and never returns a wrong converged result. The trace says why.
- **ACTIVE against a plug.** Running at zero flow, s* = √((H_set0 − H_s)/H₀(0)), no `PUMP_FLOW_REVERSAL`. A v1 fixed pump against a plug is also reported running at zero flow: its link is in `dead_end_links` with status OPEN.
- **EPANET references.** A fixed driver pump, a short pipe and an active PRV (Design 1), plus a generator-side brentq over EPANET's relative speed ω (Design 2).
- **Gate.** Fuzzed with the independent rule checker and the `state_search` pins before it ships.

**Slice 3: differential pressure.**
- ACTIVE = `LinkState(NORMAL, law=HeadOffsetLaw(offset = z_s − z_d − Δp/ρg, coefficient = c_s − c_d, reference = own = pump link))`, through slice 1's override. `merge_offset_links` merges {s, d}.
- The own slope goes to the single discharge pipe (`gga.py:606-620`).
- With c_s < c_d (the usual case, a smaller discharge pipe), the term is 2(c_d − c_s)Q of negative resistance. It is lagged (`gga.py:786`) and can diverge on a short discharge with no exit fitting. This needs its own stress case.
- EPANET reference: the FAQ's reversed-PBV substitute.

---

## 5. Edge cases (slice 1)

| Case | Behaviour | Why |
|---|---|---|
| Setpoint unreachable at maximum speed | A1 → OPEN: the v1 pump at `speed`, Q < Q_set, `PUMP_SETPOINT_NOT_MET`. If H > S_max + Htol, it goes on to CLOSED (no_flow, `PUMP_FLOW_REVERSAL`). | A drive saturates high (Bentley Fixed Speed Override). At s_max the pump is exactly the fixed pump. |
| Gravity drives more than Q_set even at s_min | A2 (H < F(s_lo, Q_set) − Htol) → MIN_SPEED: runs at s_min, Q > Q_set, flagged. `PUMP_OUTSIDE_CURVE` if Q/s_min is beyond the points. | A pump cannot throttle below its minimum. There is no sleep mode (Q3). |
| Q_set/s_min beyond run-out (curve_a, 0.0335 m³/s, s_min 0.4) | Solves ACTIVE, with s* unique on [s_lo, s_max]. | §4.3 bracket. Rejecting it would refuse a valid project (GOALS §4.6). |
| Q_set/s_min beyond x_mono, head at Q_set in [F(s_lo, Q_set), F(s_min, Q_set)) | ACTIVE at the root on [s_lo, s_max]. MIN_SPEED (Q > Q_set) also satisfies the rules there; the solve starts ACTIVE and A2 does not leave it for a head in the band. | §4.3, §4.6: the other root, on [s_min, s_lo], is on the falling stretch no stable controller holds. |
| Q_set/s_max beyond x_mono (Q_set ≥ s_max·x_mono) | `CONTROLLED_PUMP_SETPOINT` (422), after the ψ test, naming the bound s_max·x_mono. (As first built, s_lo was capped at s_max: MAX_SPEED by A1 and MIN_SPEED could both satisfy the rules, both flagged `PUMP_OUTSIDE_CURVE`, the reported one depending on the solve's path.) | No speed in the range is on a rising stretch of F(·, Q_set) (§4.3). The owner's decision of 2026-10-23: invalid input (TSD §12). |
| Reverse flow | Impossible in ACTIVE (Q ≡ Q_set > 0). At OPEN it closes by EPANET's rule. | Integral check. |
| Discharge into a plug or a closed valve | A0 → OPEN at s_max, zero flow, head S_max: running, `PUMP_SETPOINT_NOT_MET`. | Identical to a v1 fixed pump at s_max against a plug. A controller that sees zero flow goes to maximum. |
| Between two closed isolation valves | A0 → OPEN, inside a closed-off section: no pump result and no flag (`results.py:556-575` returns None for a running pump). | Fixes the false `PUMP_FLOW_REVERSAL` (invalid) that a starved → CLOSED rule would raise. Same as a fixed pump. |
| Sealed loop (its reservoir isolated by a closed valve) | Floating via `_drives_circulation`. Flows Q_set and the head difference are exact; s* is exact. `UNDETERMINED_PRESSURE` names the pump. NPSHa and suction pressure are None. | The existing floating-section path (`results.py:657-661`, `902-912`). |
| Pump and downstream check valve close together | Re-tested by `zero_flow_openings` with −S_max. On a negative cycle, OPEN at s_max, then X1 → ACTIVE. | The D9 reopen rule, unchanged. The bound is the v1 pump at s_max. |
| Parallel with a fixed pump, or two flow pumps in parallel | Each controlled pump is an independent fixed flow, with its own speed. | Determined. Not Bentley's common-speed battery (deferred). |
| Two flow pumps in series, unequal setpoints | A unique state set by Q_c (§4.6), reached by the fallbacks with MIN_SPEED options. | Monotone partition. |
| Two flow pumps in series, equal setpoints; or flow pump and FCV with equal setpoints | Not converged, naming both; the message says the pressure between them is undetermined (over-controlled). | The pressure between them is undetermined (AFT, PIPE-FLO). |
| Flow pump and a downstream PRV | PRV open and pump active if no throttling is needed at Q_set; otherwise PRV active and pump at max speed. | Unique (§4.6). Design 2's "undetermined" was wrong. |
| Drooping curve with ψ > 0 | Accepted; the speed root s* is unique, the operating state need not be: the limit rules close the pump against s²H₀(0), as v1 does a fixed pump, so a running state with a head above that is not found (no flow, `PUMP_FLOW_REVERSAL` invalid; or, at minimum speed, not converged). | §4.3. A known v1 limitation, kept by the owner's decision of 2026-10-23 (TSD §12); EPANET 2.2 rejects such curves (error 227). |
| Curve with ψ ≤ 0 inside its points | `CONTROLLED_PUMP_CURVE` (422). | The speed would not be unique. Loosening this later breaks no link. |
| minSpeed ≥ speed | 400 `VALIDATION_ERROR`, with no values echoed (D10). The form flags it before any solve. | Model rule. |
| Status off with a control | CLOSED and fixed; `control.state` off; no setpoint flag. | off wins. The trace notes it. |
| H within Htol beyond a limit while ACTIVE | s* is clamped to the limit; the trace states the residual (≤ 1e-4 m). | Keeps s ∈ [s_min, s_max]. Within D6. |
| Operating point outside the curve points at s* | `PUMP_OUTSIDE_CURVE` with speed s*. NPSHr and efficiency extrapolation flags at s*. | Existing flags, evaluated at the actual speed. |
| Glycol with no vapor pressure | `NPSH_NOT_CHECKED` at s*. | Existing behaviour. |
| Crane tees nearby | Sequential mode as today. Each saturation costs about one outer iteration. | Risk 3. |

---

## 6. Traceability

**Pump trace (`trace.py:918-1094`).** Additions appear only when `control` is set, so fixed-pump traces stay byte-identical.

- **Inputs:**
  - Control mode "flow" (user);
  - Flow setpoint Q_set (user);
  - Minimum speed s_min (user; always "user", since there is no default);
  - "Maximum speed s_max (field speed)", labelled default or user by `_given` (164-173).
- **Equations:**
  - "Active: Q = Q_set imposed as a fixed flow (a demand at the suction port, a supply at the discharge port; no energy equation of its own)";
  - "s* solves s²H₀(Q_set/s) = EGL_d − EGL_s on [s_lo, s_max] (Brent)";
  - "Exact: the speed enters only the pump's head equation, so the Newton system is block-triangular and flows and heads do not depend on s";
  - "Unique: d/ds[s²H₀(Q/s)] = s(2H₀ − xH₀′) > 0, x = Q/s";
  - rules A0–C1 with Htol and Qtol.
- **Correlations and sources:**
  - the affinity laws (existing);
  - EPANET 2.2 pumpstatus and fcvstatus (hydstatus.c);
  - the EPANET 2.2 FAQ "specific flow" substitute;
  - Brent (1973) via `scipy.optimize.brentq`;
  - Fritsch–Carlson (1980);
  - the speed-limit convention (Bentley Fixed Speed Override URL);
  - CLAUDE.md D11.
- **Values:**
  - H, F_min, F_max, S_max and S_min;
  - s*, or the limit speed;
  - s_lo, x_mono, and the uniqueness margin min ψ;
  - Q/s and the curve range at that speed;
  - the residual F(s, Q) − H;
  - all existing pump values at the actual speed.
- **State notes** state the inequality that set the state, with values, as `_control_rule_values` does for valves (1163-1257). Examples:
  - "Active: F(s_lo, Q_set) − Htol = 2.7199 m ≤ H = 20.000 m ≤ F(s_max, Q_set) + Htol = 41.0001 m, so the speed that holds Q_set lies within [s_lo, s_max]; s* = 0.7328 (residual 3e-13 m)." (s_lo = s_min here, so F(s_lo, Q_set) = F(s_min, Q_set).)
  - "At maximum speed: Q = 0.0182 m³/s < Q_set = 0.025 m³/s; runs as a fixed-speed pump at s_max = 0.9; returns to regulating once Q ≥ Q_set."
  - "No flow: H = 52.1 m > s_max²H₀(0) + Htol = 45.0001 m."
  - "Its control is not applied: status off."
- **Notes added:** "efficiency at reduced speed by the plain affinity law η = η₀(Q/s), with no Sârbu–Borza correction (EPANET 2.2 applies one)". The no-viscosity-correction note is kept.

**Methods summary (`methods.py:212-237`).** These items are added only when a controlled pump exists, so the summaries of other projects are unchanged:
1. "Speed-controlled pumps (flow setpoint): F(s, Q) = s²H₀(Q/s) is the pump's head at speed s, between its minimum speed s_min and its speed s_max (the maximum). F rises with speed on [s_lo, s_max], s_lo = max(s_min, Q/x_mono), where 2H₀ − (Q/s)H₀′ > 0 (checked exactly on the curve's cubic pieces). While a speed in [s_lo, s_max] holds the setpoint, F(s_lo, Q_set) − Htol ≤ EGL_d − EGL_s ≤ F(s_max, Q_set) + Htol, the pump carries the setpoint as a fixed flow and its speed is the unique root of F(s, Q_set) = EGL_d − EGL_s on [s_lo, s_max]. This equals solving the speed with the network: it enters only the pump's own head equation." As built, the item also states when s_lo exceeds s_min and that the pump held at s_min is then a steady state too in the band between F(s_lo, Q_set) and F(s_min, Q_set) (§4.6).
2. "Outside that band the pump runs as a fixed-speed pump at the nearer limit and the setpoint is not held (flagged). At zero flow its controller is at maximum speed, so it closes and re-opens as a fixed-speed pump at its maximum speed (EPANET 2.2 pumpstatus)."
3. "Efficiency and NPSHr at the solved speed by the affinity laws; no reduced-speed efficiency correction."
4. The system-curve item gains: "a speed-controlled pump's own control is replaced by the fixed flow at each point; other speed-controlled pumps keep regulating; default range × its maximum speed."

**Flags.** `PUMP_SETPOINT_NOT_MET` (info) carries details {state, setpoint, flow, speed, minSpeed, maxSpeed}. Its messages by state:
- max_speed: "runs at its maximum speed 0.9 and delivers X, below its setpoint Y";
- min_speed: "runs at its minimum speed and passes X, above its setpoint Y";
- no_flow, by its cause, as the trace note states it: "has no flow: the head across it (H) exceeds its shutoff head at its maximum speed 1 (S_max)" only when H > S_max; "its discharge (or suction) is closed off, so it runs dead-headed at its shutoff head at its maximum speed" for a dead-headed pump, whose head is S_max exactly; "it is held at no flow at its maximum speed and both its sides are closed off" when it has no head. The last two carry `closedOff` (the side, or "both") in the details.

`CONTROLLED_PUMP_CURVE` gets issue text. The existing flags are evaluated at the actual speed.

---

## 7. Verification plan

**Pass criteria.**
- D6: flows, heads and pressures within 0.5 % or 0.01 m of head, whichever is looser, with mass balance closing.
- Speed is new to D6. Proposed: 0.5 % relative, and |F(s, Q) − H_ref| ≤ 0.01 m (Q6). As built, the reference suite tests the implied head within 0.01 m of a derived head; the EPANET differential fuzz compares it with EPANET's head rise by D6's head criterion (0.5 % or 0.01 m, whichever is looser), because EPANET's own constants move its head by 8.1–9.2·10⁻⁴ of the path's losses (TSD §10.4, `checks.py`).
- States must be clear by `STATE_MARGIN` = 0.05 m (`tests/reference/element_laws.py:217`).

**Process (Design 3).** A second agent writes `tests/reference/derivations_pump_control.py` without reading `services/`. It may import `opensolve_pipe.models`, `element_laws` and `line.py` only. Then integration, then an adversarial review.

### 7.1 Closed-form cases (`build_closed_form_cases.py`; expected values gain `speed` and `controlState`)

| Case | Independent derivation | Proves |
|---|---|---|
| CF1 `pump_flow_control_active_linear` | Line R1 → PU1 → R2 with a lift and a linear curve. Q = Q_set; EGLs by Darcy–Weisbach at Q_set; s* = [bQ + √(b²Q² + 4aH)]/(2a) (ORNL eq. 10, c = 0). | The FIXED_FLOW mapping and speed recovery, with no root finder. |
| CF2 `…_active_pchip` | curve_a; x* = Q/s* by brentq on the affinity parabola H₀(x)/x² = H/Q², not on the solver's equation in s. | The PCHIP path. |
| CF3 `…_low_min_speed` | curve_a, Q_set = 0.0335, s_min = 0.4, line sized so H = 30 m; s* = 0.96817. | The bracket accepts Q_set/s_min beyond run-out. |
| CF4 `…_max_speed` | speed = 0.9; expected = the existing `solve_pump_line` at 0.9 (`derivations_pumps.py`). | Saturation ≡ fixed pump at `speed`; the flag. |
| CF5 `…_min_speed` | Gravity line; the fixed operating point at s_min; Q > Q_set. | The lower limit. |
| CF6 `…_no_flow` | H_R2 − H_R1 > S_max; zero-flow heads. | The CLOSED rule at s_max. |
| CF7 `…_parallel_fixed` | fsolve on the header head with the fixed pump's curve; s* from its head. | Coexistence with a fixed pump. |
| CF8 `…_parallel_two` | All flows known, so heads in closed form; each speed separately. | Independent controllers. |
| CF9 `…_series_fcv` (both orderings) | §4.6. | Fallbacks reach the physical state. |
| CF10 `…_series_two_pumps` (Q_c ≤ Q1, between, ≥ Q2; and equal setpoints) | Q_c by brentq on G(Q) = 0. | The uniqueness partition and MIN_SPEED fallbacks; not converged when the setpoints are equal. |
| CF11 `…_series_prv` (both regimes) | The PRV law at H_set; the pump at Q_set or at s_max. | Corrects Design 2's expectation. |
| CF12 `…_floating_loop` (in `test_floating_sections.py`) | Loop flow Q_set, H = Σh(Q_set), s*. | `UNDETERMINED_PRESSURE`; NPSHa None. |
| CF13 `…_loop_with_reference` | Heads from the ideal reference node. | Determined loops. |
| CF14 `…_check_valve_reopen` | Analogue of `pump_and_check_valve_reopen`. | As built, not the zero-flow bound (the slice-1 review): the pump starts as a fixed flow, so its check valve never closes; the pump goes to maximum speed (A1) as the FCV opens, then holds its setpoint. |
| CF14b `…_zero_flow_reopen` | CF14's network with R2's line split by an ideal PRV2 (400 kPa). The active PRV2 leaves the junction without a fixed head, so PU1 starts at s_max (A0); the surplus FCV1 forces past PRV2 (brentq) flows back through the pump line above S_max, so PU1 and CV1 close together; with them closed the junction is 10.60 m above R1, between S_min (8.0 m) and S_max (28.88 m). Final state by brentq on the FCV line, s* from the affinity parabola. | The zero-flow re-test bounds a closed controlled pump by S_max (D9): PU1 and CV1 re-open; a bound at S_min would keep them shut. |
| CF15 `…_dead_end` | Q = 0, head = S_max; equal to the fixed pump at s_max. | A0 → OPEN. |
| CF16 `…_isolated` | No pump result and no flag, equal to the fixed pump. | The false-flag fix. |
| CF17 `…_off` | The v1 off pump. | The control is ignored. |
| CF18 drooping curves | A curve with ψ > 0 solves with a unique s*; one with ψ ≤ 0 inside its points gives the 422. | The §4.3 test. |
| CF19 `…_active_outside_curve` | curve_b, Q_set = 0.04 m³/s, s ∈ [0.5, 1], line sized so H = 10 m. s* = 0.838230 by the straight-line formula on the curve's end tangent (the parabola route agrees); Q/s* = 0.0477 is beyond the last point (0.045), Q/s_max inside. | `PUMP_OUTSIDE_CURVE` at the solved speed. |
| CF20 `…_min_speed_outside_curve` | curve_b, Q_set = 0.02 m³/s, s ∈ [0.6, 1], 1 m lift. min_speed with Q = 0.028718 m³/s (brentq on the end tangent); Q/s_min = 0.0479 is beyond the points, Q/s_max inside. | `PUMP_OUTSIDE_CURVE` at the limit speed, with `PUMP_SETPOINT_NOT_MET`. |
| CF21 `…_stable_bracket` | Straight curve a = 40, b = 400, Q_set = 0.05 m³/s, s ∈ [0.1, 1], H = −2 m (braking a gravity flow). x_mono = 2a/b = 0.2, s_lo = bQ/2a = 0.25; F(s_lo) = −b²Q²/4a = −2.5 m < H < F(s_min) = −1.6 m. s* = 0.25 + √5/20 = 0.361803. | Rule A2 on F(s_lo, Q_set): active on [s_lo, s_max], not min_speed. |
| SC1 (`test_system_curves.py`) | H_sys = H2 − H1 + h_L1(Q) + h_L2(Q), whatever the mode; the operating point lies on F(s*, ·). | The system-curve definition. |
| SC2 | A fixed pump A in parallel with flow pump B. Closed-form H_sys,A(q) while B is active, then B's fixed law past the closed-form saturation flow. | Warm-started statuses carry B's control. |

### 7.2 EPANET cases
These use `generate_epanet_cases.py` with WNTR 1.5.0 / EPANET 2.2, `swamee_jain` mode, and collinear curves, so EPANET's piecewise-linear curve equals our PCHIP.
- **E1 `epanet_pump_flow_control`.** The `pump_network` loop with the pump flow-controlled.
  - The reference run is the FAQ substitute: pump CLOSED, base demand +Q_set at the suction junction and −Q_set at the discharge junction (https://usepa.github.io/EPANET2.2/13_questions.html).
  - Expected values: EPANET's flows, and its heads as our EGLs (D7).
  - s* comes from the closed form at EPANET's head difference.
  - Generator assertion: an EPANET run at SPEED = s* returns Q_set within D6. WNTR `base_speed` writes SPEED (`wntr/epanet/io.py` around 812-814), and EPANET evaluates h = ω²H₀(q/ω).
- **E1b.** The same network, with a generator-side brentq over ω ∈ [s_min, s_max] on EPANET runs (Q_EPANET(ω) = Q_set). This is an independent speed reference for our s*.
- **E2 `…_max`.** EPANET at SPEED = `speed`. **E3 `…_min`.** EPANET at SPEED = s_min, with Q/s_min inside the points.

### 7.3 Metamorphic and unit tests
- **M1.** A converged project with a pump in max_speed (or min_speed) and one steady state that satisfies every element's rule, re-solved with the control removed and speed = s_max (or s_min), gives identical flows, heads and statuses. Bit-identical for max_speed, since the law object is the same. Where several states satisfy every rule, M1 does not hold, and not because of a solver defect: a section closed off at zero flow has a free level at which the closed elements around it stay closed (D9), so "closed at zero flow" and another state (a dead-ended pump running at no flow, or a pump loop behind closed valves circulating) can both be valid, v1's zero-flow multiplicity. Each solve returns the state its iteration reaches, and the controlled pump's iteration differs from the fixed pump's: it starts ACTIVE and follows A0–C1 on the way (X1 makes it regulate whenever its flow reaches Q_set at s_max), where the fixed pump starts OPEN. The slice-1 review found this in `flow_control` seeds 10,236, 10,647 and 11,214 of the differential test: both final states pass the independent checks (`tests/differential/checks.py`); 10,236 and 10,647 have the same flows and differ in statuses at zero flow (the pump dead-ended running at no flow, or held closed), 11,214 in whether a pump loop behind closed valves circulates (0.000878 m³/s). Started OPEN instead, the controlled solve reaches the fixed solve's state in 10,647 and 11,214, but not in 10,236, where the path differs through X1. The unit test checks M1 on a line with one steady state.
- **M2.** Re-solved fixed at s*, the pump flow equals Q_set within D6.
- **Unit tests:**
  - the rule table at ±Htol and ±Qtol, with boundary points kept by both neighbours;
  - the ψ test against dense sampling on random PCHIP curves, and x_mono = 2x₀ against a grid;
  - `operating_speed` against the closed form, and s ∈ [s_min, s_max] always;
  - a `LinkState.law` override equal to the link's own law gives bit-identical GGA results;
  - MIN_SPEED inside closed-off and floating sections reads the override (`gga.py:361`, `status.py:449`);
  - `_open_bad_valves`: valve-only networks take the recorded v1 option sequence;
  - `_check_changes` on pumps;
  - the results mapping, and the curve sampled at the actual speed;
  - `x-ordered-fields` against the validator; a `PumpControl` instance; the openapi copy check;
  - `VALIDATION_ERROR` without echoed values;
  - the flags audit; trace notes per state; the conditional methods text;
  - system-curve warm starts with MIN_SPEED.

### 7.4 Differential fuzz (TSD §10.4)
- `generator.py` adds 0–2 flow-controlled pumps on collinear curves.
- `epanet_model.py` maps our final state to its substitute: active → the demand pair; max/min → SPEED; no_flow → CLOSED.
- `checks.py` gains an independent rule checker written from §4.5 that reads only results (Design 1). A converged result that breaks a rule is critical.
- `state_search.py` pins controlled pumps over the four states to detect networks with more than one valid state (Design 3).
- 3,000 seeds with zero critical. The smoke test on seeds 0–49 stays green.

### 7.5 No-regression proof
- The corpus is dumped before and after (TSD §10.4). `compare.py` leaves out exactly two paths: `pumpResults.*.control` (new) only where it is null or absent on both sides (`--ignore-null`), so a control result on a pump of the old corpus is a difference, and `methodVersion` (`--ignore`, at the top level and in the methods summary). All 3,092 projects must otherwise be identical.
- The whole reference suite and `test_released_links.py` stay green.

### 7.6 Gates for slices 2 and 3
- Each slice ships with:
  - its closed-form cases;
  - its EPANET substitute plus the brentq over ω;
  - the fuzz with the rule checker and `state_search`;
  - a stress case for the velocity-head or own-slope lag.
- Slice 2 also needs the shared PRV coupling change measured and versioned separately.

---

## 8. Web changes
All paths are under `apps/web/src/lib`. Desktop and mobile share the same single-column panel form, so no layout is device-specific.

1. **`components/panel/forms/PumpForm.svelte`:**
   - Add a "Control" `SelectField` with the options Fixed speed and Flow.
   - Choosing Flow shows "Flow setpoint" (category flow, bounds `schemaBounds('PumpControl','setpoint')`) and "Minimum speed" (category fraction).
   - These two values are held as a **local draft until both are valid and minSpeed < speed**. Then one undoable edit writes `control`, so a link never holds a partial or invented value. Until then the form says "Enter the flow setpoint and minimum speed to switch to flow control". This follows the `PumpCurveEditor` draft precedent.
   - Choosing Fixed speed deletes `control` in one edit (`withOptional`, `utils/piping.ts:192-201`).
   - When controlled, Speed (44-56) is relabelled "Maximum speed", with the hint "Highest speed the drive runs at; here the pump behaves as a fixed-speed pump."
   - The minimum-speed hint: "From the drive or pump data; there is no standard default."
   - A note when the status is off.
2. **`utils/model-rules.ts`:** `orderedFields()`. **`utils/validate.ts`:** the keyword (51) and a `modelRuleIssues` entry on the field: "The minimum speed of <name> must be below its maximum speed."
3. **`utils/labels.ts`:** control and state labels.
4. **`utils/results.ts`:**
   - `pumpStatusLabel` (566-579): "Running (holding flow setpoint)", "Running at maximum speed (setpoint not met)", "Running at minimum speed (above setpoint)", and no flow as today.
   - The Speed column already shows `result.speed`.
   - A "Control" column, shown only when the project has a controlled pump, keeps mobile tables narrow. Examples: "Flow 12.0 L/s: held", "Flow 12.0 L/s: 9.8 L/s at max speed".
5. **`PumpChart.svelte` (57-61):** the label becomes "Pump curve at 87.3 % speed (flow control)". `pump-chart.ts:98` is unchanged. The system-curve note adds "this pump's control is replaced by a fixed flow; other controlled pumps keep regulating" and links to the trace's H_sys definition (D10). The fetch is unchanged.
6. **`utils/flag-text.ts`:** a `PUMP_SETPOINT_NOT_MET` formatter in display units, so the raw-message fallback (152-171) is not used for it. **`utils/issue-text.ts`:** `CONTROLLED_PUMP_CURVE`.
7. **Types and sharing:**
   - regenerated types;
   - tests: a round trip of a controlled project; `fillDefaults` adds no `control` to `schema-v1.json`; the hydraulic fingerprint changes when `control` changes;
   - migrations and fixtures only if §3.5 bumps the version.
   - About 70 characters of link per controlled pump; the 8,000-character warning is unchanged.
8. **Tests:**
   - Vitest for the draft logic, the labels and the flag text;
   - Playwright at 1280×800 and 390×844: set flow control, solve, read the solved speed, state and chart label, share, reopen with the same results, switch back, undo; an unreachable setpoint shows max speed and the info flag.

---

## 9. Risks

### 9.1 Risks
1. **Status interactions.** The new transitions may interact with PRVs, PSVs, FCVs and Crane tees. Mitigation:
   - the rules stay in the difference class;
   - the fuzz runs with the rule checker and `state_search`;
   - M1 and M2;
   - the 30-iteration cap and cycle detection end in not converged, not a wrong answer.
2. **Over-control in series.** Reaching the unique state depends on the fallback order and on monotone surroundings. Crane-tee patterns can break monotonicity; `state_search` detects networks with more than one valid state.
3. **Outer-iteration budget.** Each saturation costs about one outer iteration, and more in sequential mode next to Crane tees. Measure on the fuzz corpus before merge.
4. **The five law read sites.** A missed site would silently use the s_max law in MIN_SPEED. Mitigation: one helper, and per-site unit tests.
5. **User expectations.**
   - At minimum speed the pump passes more than its setpoint instead of sleeping.
   - `speed` now means the maximum speed when controlled.

   Both are stated in labels, flags, trace and field descriptions, but remain product choices (Q3, Q4).
6. **No cited minimum speed.** This adds friction: a required input, where GOALS §4.1 prefers cited defaults.
7. **Plain-affinity efficiency is optimistic at low speed.** Shaft power will differ from EPANET's at s ≠ 1. Hydraulics are unaffected.
8. **Patent.** US 8,265,911 (Bentley, listed active to 2030-11-27) recites tank control nodes, extended periods, fixed-flow updates and batteries (https://patents.google.com/patent/US8265911). Slice 1 is steady-state, controls the pump's own flow and has no tank and no battery. This is not a legal reading. US 7,013,248 is listed as expired (https://patents.google.com/patent/US7013248).
9. **The method-version notice** appears on every reopened old link once. Its changelog says the results are unchanged.
10. **Stale apps.** If deployment precedes this change and the version is not bumped, stale apps show "unknown field" rather than "reload" (§3.5).
11. **`compare.py` ignore paths.** A broader ignore than the two named paths could hide a real change, so it must be exactly those two.
12. **Slice 2 carries the hard parts:** level logic, velocity-head coupling and a shared PRV change. They are scheduled with their own gates, not solved here.

### 9.2 Review findings and their disposition

| Finding (judge) | Disposition |
|---|---|
| D3 `PUMP_CONTROL_SETPOINT_RANGE` rejects valid inputs (J1, J2) | Dropped. Bracket s_lo = max(s_min, Q_set/x_mono) and A2 on F_min instead (§4.3). The curve_a counter-example becomes CF3. |
| D3 rejects every drooping curve (J1, J2, J3) | Replaced by the exact ψ test. A 422 only where ψ ≤ 0 inside the points (§4.3). |
| D3 series flow pumps: "smaller wins" wrong, second equilibrium (J1) | Both claims corrected by the Q_c partition (§4.6). The fallback gains MIN_SPEED. CF10 covers all regions. |
| D3 `Literal[2]` (J1, J2) | `Literal[1, 2]` if bumped (§3.5). |
| D3 minSpeed ≥ speed as 422 (J2, J3) | A 400 model rule, published as `x-ordered-fields` (§3.3). |
| D3 METHOD_VERSION kept (J2) | Bumped to 1.1.0 (§3.6). |
| D3 `_level_changes` reopening to ACTIVE with a side on a free level (J2) | Does not arise. Reopening is OPEN at s_max, a NORMAL link, through unchanged `pump_status` at `component.speed` (`status.py:797-802`). ACTIVE is reached only by X1 after a solve. |
| D3 mutating `PumpLaw.speed` (J3) | `LinkState.law` override (§4.4). |
| All designs: false `PUMP_FLOW_REVERSAL` for an isolated controlled pump (J2) | A0 → OPEN, not CLOSED. `results.py:556-575` then returns None with no flag, as for a fixed pump (CF16). |
| D3 breadth (J1, J3) | Accepted for slice 1, with slices 2 and 3 scheduled (GOALS §6). |
| D2 "flow pump + PRV undetermined" (J1) | Corrected: unique (§4.6, CF11). |
| D2 pumps-only velocity-head slope (J1, J2) | Not in slice 1. In slice 2, one change for PRVs and pumps together, versioned (§4.10). |
| D2 differential negative own-slope lag (J1) | A stated slice-3 risk, with a stress case (§4.10). |
| D2 CLOSED discharge pump in a floating section reported converged (J1) | Slice 2 uses Design 1's not-converged exit unless closed at every level. |
| D2 speed above s_max inside the band (J1, J2, J3) | The clamp keeps s* ∈ [s_min, s_max]; the residual is in the trace (§4.7). |
| D2 discharge mode not fuzzed (J2) | A slice-2 gate (§7.6). |
| D2 "OPEN or MIN in a closed-off section → CLOSED" (J2) | Not adopted. The existing section rule applies (`status.py:380-384` on shifts). |
| D2 convex zero-flow bounds can cycle (J2, J3) | Kept for slice 2 where both sides are in sections. It fails safe as not converged; correctness ranks above usability. |
| D1 flow setpoint 0 (J1, J2, J3) | Excluded (gt = 0). |
| D1 prefilled setpoint 0 and minSpeed = speed (J1, J2) | Draft until valid (§8). |
| D1 knot scan misses root pairs (J1) | Not used. With ψ > 0 the root is unique, and brentq needs one sign change. |
| D1 dead-headed ACTIVE labelled both running and no_flow (J1) | Slice 2: running at zero flow with no reversal flag, consistent with a v1 pump against a plug. |
| D1 law swap at 8 call sites (J1, J3) | Replaced by the override; no call-site changes. |
| D1 "no constraint" with both sides in sections converges wrong (J3) | Design 2's convex bound in slice 2. |
| D1 velocity-head lag understated (J2, J3) | Quantified at ratio 1/r, with a shared fix (§4.10). |
| D1 end-speed tests inexact on rising curves (J2, J3) | The ψ test makes F monotone on [s_lo, s_max], so the tests are exact. |
| D1 no system-curve reference (J2) | SC1, SC2. |

---

## 10. Questions for the owner

1. **Slice order.**
   - Options: (a) Controlled Flow first; (b) discharge pressure first, as the most common VFD use, which needs the level logic and the shared PRV coupling change before anything ships.
   - **Recommend (a).** It is verifiable now (GOALS §6, §5), and slice 2 follows with its own gates.
2. **Minimum speed default.**
   - Options: (a) a required input with no default; (b) a default you can cite.
   - **Recommend (a).** No tool or paper found cites one (GOALS §4.1). A default can be added later without breaking links.
3. **Low-demand behaviour.**
   - Options: (a) run at minimum speed and pass more than the setpoint; (b) sleep or stop, as Bentley "Off".
   - **Recommend (a) now, (b) Later.** Sleep needs a stopped-pump model; v1 models a stopped pump as a closed link, which has stable inferior solutions.
4. **Maximum speed field and overspeed.**
   - Options: (a) reuse `speed` as the maximum and keep s ≤ 1; (b) a separate `control.maxSpeed`; (c) allow s > 1 (Bentley allows it; EPANET has no cap).
   - **Recommend (a).** Every existing reader of `component.speed` then gets the value it needs. Overspeed extrapolates the affinity laws above the rated curve.
5. **Deployment order (schemaVersion).**
   - Will any build be deployed or tagged before slice 1 merges?
   - If yes: schemaVersion 2 with an identity migration and `Literal[1, 2]`. If no: keep 1.
   - **Recommend** deciding by that fact and applying the §3.5 rule to every later new field or mode value.
6. **D6 for speed.**
   - Options: (a) 0.5 % relative, plus the implied head within 0.01 m; (b) the implied head only.
   - **Recommend (a).** It is a CLAUDE.md D6 amendment.
7. **Slice 3 differential setpoint.**
   - Options: (a) static p_discharge − p_suction, as a dP transmitter reads it, including (v_d² − v_s²)/2g and Δz; (b) the pump's EGL head rise.
   - **Recommend (a).** It is consistent with D9's static setpoints.
8. **Slice 2 scope.** Discharge static pressure at the port, as recommended. Also suction-pressure control (the PSV shape)? Remote control nodes stay Later.
   - **Recommend** discharge only, with suction and remote Later.
9. **Parallel stations** (lead/lag, equal speed, total flow).
   - Options: (a) Later, with a legal review of US 8,265,911 before any design; (b) design now.
   - **Recommend (a).**
10. **Efficiency at reduced speed.**
    - Options: (a) keep plain affinity, η = η₀(Q/s); (b) Sârbu–Borza as in EPANET 2.2; (c) ORNL's rule below 66.7 %.
    - **Recommend (a)** for now. Treat (b) or (c) as a separate, versioned method change, because it alters existing fixed reduced-speed results.
### Owner's answers (2026-10-22)

The owner chose slice 1 as recommended, with every recommended option. In detail:
- **Q1:** (a) Controlled Flow first.
- **Q2:** (a) the minimum speed is a required input, with no default.
- **Q3:** (a) the pump runs at minimum speed at low demand.
- **Q4:** (a) `speed` is the maximum speed, at most 1.
- **Q6:** (a) speed is checked within 0.5 % relative, and its implied head within 0.01 m.
- **Q7–Q9:** as recommended.
- **Q10:** (a) plain affinity laws.
- **Q5 (schemaVersion):** slice 1 is built on the development branch before the first deployment, so schemaVersion stays 1. Cloudflare Pages for the web app and Cloud Run for the API were chosen, but nothing is deployed yet. If any build is deployed or tagged before slice 1 merges, apply the bump in §3.5.
- **"Default" label (separate question):** keep the current rule; no model change.
