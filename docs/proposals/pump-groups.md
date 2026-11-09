# Several pumps: design proposal

**Status: decided** (owner, 2026-10-28); slices 4a, 4b, 4c and 4d are built (§14 to §17 record the as-built departures); the card's place in the Pumps tab restructured by `docs/proposals/pumps-results-layout.md`, slices S2 and S3, 2026-11-06, and S4, 2026-11-07 (§18). **Owner's answers (2026-10-28), each the recommended option of §13:** Q1, the station frame: the group curve and the group system curve between the station's outer ports S and D; Q2, the plain combined curve is not drawn (revisit after users have seen the group curve); Q3, groups are page state, with a suggested default; Q4, no new inputs for impeller trims or the ISO 9906 tolerance in slice 4. This is slice 4 of `docs/proposals/pump-chart.md`: §1 rows 8, 13 and 14, and §6 slice 4 ("a combined view for pumps the user groups (parallel or series): each pump's own solved point and curve, the group's combined curve as a reference only …, and the system curve of the group. Impeller trims and ISO 9906 bands follow their inputs."). It was written read-only against branch `pump-groups` at `main` `b6e2088` (D19 merged).

It merges three designs, each built on the same API, web and practice notes:
- *derive first*: the smallest model change; web only;
- *engineer first*: a station designer's questions first;
- *correctness first*: one exact frame for any group.

§11 records what was taken from each and what was left. Everything here is a reversible default under D14, except where it is marked **owner** (now answered, §13).

A station engineer checks four things:
- each pump's own point with every pump running;
- how the flow divides;
- at what pressure a weaker pump stops delivering;
- where the station runs as the system changes, with one pump off as well as all on.

Today the app answers the first question, one pump per chart. This proposal adds a view of the pumps together. It is built on two curves defined between the station's outer ports. The probes show that both are exact and that they meet at the solved duty. The catalogue composite curve is kept out of the first slice, because it does not meet the system at the duty.

Sources:
- **Practice research (2026-10-28).** Every claim below is labelled **[read]** (page or PDF opened) or **[snippet]** (seen only in search results).
  - Parallel and series pumps:
    - Datacor (B. Keiser, "Know Your Pump & System Curves – Part 3", 2021) [read];
    - KSB Centrifugal Pump Lexicon, "Parallel operation" and "Series operation" [read];
    - Xylem Bell & Gossett TEH-1109A, "Parallel and Series Pump Application" (2012) [read];
    - DOE Tip Sheet #8 (2006), and the DOE/HI *Improving Pumping System Performance* sourcebook (2006) [read];
    - HI, "Five Keys to Understanding Parallel Pump Optimization" (2022) [read];
    - NRC Bulletin 88-04 [read];
    - FluidFlow, Bentley WaterCAD and Pipe Flow Expert documentation [read];
    - the Grundfos Hydro Multi-E and CRNE-HS manuals [read];
    - UFC 3-240-04A (1 March 1997), ch. 7 ¶ d(2), read through a third-party mirror (tpub). The official copy is to be checked before the build cites it.
  - Trims:
    - DOE Tip Sheet #7, the HI 2022 trimming post and the KSB lexicon [read];
    - Nikolova et al., Proc. Univ. Ruse 63 (1.1), 2024 [read], which also quotes Gülich.
  - ISO 9906:2012 grades: KSB lexicon "Tolerance", Wilfley (2015) and the HI white paper (2018) [read].
  - The standards themselves (ISO 9906, API 610, ANSI/HI 9.6.3, 14.6 and 14.3) were **not** read.
- **Probes (2026-10-28).** They were run read-only on these cases:
  - the reference fixtures `pumps_in_parallel` and `pumps_in_series` (`apps/api/tests/reference/derivations_pumps.py`), with their tees set to `ideal` or `crane`;
  - a 3-pump ladder on Crane-tee headers with a check valve in each leg, built for the probe;
  - the corpus.

  The scripts are `probe_header`, `probe_ports`, `probe7`–`probe10`, `ladder`, `series_station`, `series_plain` and `detect`. They are kept with the design notes in `/tmp/claude-0/-home-user-opensolve-pipe/ca1a3fad-9c12-5ec7-9b4a-0260b4196220/scratchpad/slice4/`, not in the repository. The reference cases of §9 reproduce every number this proposal relies on.
- **Code at `b6e2088`:**
  - API: `models/results.py` (`PumpResult`, `NodeResult`, `LinkResult`), `models/api.py` (`SystemCurveRequest`, `SystemCurvePoint`), `services/solver/status.py`, `system_curve.py`, `network.py` and `builder.py`.
  - Web: `components/results/PumpsView.svelte` and `PumpChart.svelte`, `utils/pump-chart.ts`, `pump-chart-config.ts`, `graph.ts` and `export/chart-image.ts`, and `state/project.svelte.ts`.
- **Project documents:** GOALS §3, §4.1, §4.2, §4.6 and §4.7; CLAUDE.md D10, D11, D13, D14, D15, D16, D17 and D19; PRD §2 (system states, "degraded operation (individual pumps off)") and §3.2.2.

---

## 1. What a station engineer checks, and what answers it

Each need is marked **fact** (physics or the user's own data, shown by default) or **practice** (opt-in, GOALS §4.6).

| # | Need | Answered by | Kind | Slice |
|---|---|---|---|---|
| 1 | Each pump's point (Q, H, η, P, NPSH) with every pump running | `PumpResult` per pump | fact | today, one pump per chart; together in 4a |
| 2 | Each pump's share, and the head each loses on its own way between the headers | the station duty, from one solve (§3.2) | fact, exact identities | 4a |
| 3 | A weaker pump pushed to zero flow, and the rise at which each member stops | status `no_flow` with `PUMP_FLOW_REVERSAL` (today); the group curve (§3.3) | fact | 4a |
| 4 | What the station delivers at each rise, and how the split changes | the group curve | fact (a stated definition, exact) | 4a |
| 5 | Where the station runs as the system changes | the group system curve, crossing the group curve at the duty | fact (a stated definition, exact) | 4b |
| 6 | One pump off (N−1): runout, the motor's worst case, NPSH at the higher flow | a D15 case with that pump off (possible today; TEH-1109A's "Point C" [read]) | fact | today; drawn together in 4d |
| 7 | Series: each next pump's inlet pressure; casing pressure | inlet and discharge pressures from `nodeResults` (4a table); a casing check | fact; practice | 4a; later (owner) |
| 8 | The catalogue composite curve (flows added at equal head) | — | reference only | not drawn (**owner**, Q2) |
| 9 | API 610's ≥ 10 % head rise from the rated point to shutoff, for parallel duty | needs a rated point (new input) | practice | later |
| 10 | Impeller trims; the ISO 9906 tolerance | need inputs | — | **owner**, Q4 |

## 2. Findings that set the design

### 2.1 The plain combined curve misses the duty

The tools solve each pump separately. They treat the composite curve as an aid:
- Datacor: "The Composite Pump Curve with the Traditional Method does NOT cross the Composite System curve at the total flow rate for each pump" [read].
- Pipe Flow Expert draws no combined system curve [read].
- Bentley warns that its combination can disagree with the model when there is "significant headloss between the pumps and the common downstream node" [snippet].

Measured against the group system curve of §3.4, the plain sum crosses at these flows:

| Case | Plain sum crosses at (total flow vs duty) | Members' flows read there |
|---|---|---|
| `pumps_in_parallel`, ideal tees (probe3) | +6.3 % | PA +3.2 %, PB +12.9 % |
| same, Crane tees (`probe10`) | +9.11 % (0.0586163 against 0.0537207 m³/s) | PA +2.5 %, PB +24.6 % |
| 3-pump Crane ladder, a check valve per leg (`ladder`) | +6.31 % | P1 +9.0 %, P2 +7.6 %, P3 −6.1 % |
| `pumps_in_series`, against the curve between the group's ports (`series_plain`) | +10.34 % | — |

**Parallel.** The members' heads at their flanges differ at the duty: 29.5455 m and 29.3524 m with ideal tees. So no single head on a composite of flange curves carries the solved total. Read at the rise between the headers (27.3816 m), the composite gives 0.061899 m³/s, 12.2 % above the solved total (web probe).

**Series.** The plain sum is exact only against a curve that counts the piping between the pumps as system (−2.1×10⁻¹⁵), not against one taken between the group's ports.

### 2.2 The tee centres are not a frame; the outer ports are

On `pumps_in_parallel` with Crane tees, forcing the members at splits w_A = 0.70, 0.50 and 0.80 at the duty total (`probe7`) gives these rises:
- **Between the tee centres:** 27.1317, 27.2042 and 27.0845 m. The spread (0.12 m, 0.44 %) depends on the split, and 27.1317 m differs from the closed-member construction's 26.9680 m by 0.6 %, beyond D6.
- **Between the outer ports** (`T1:run_inlet` → `T2:run_outlet`): 26.967981 m at every split, equal to the solved rise. With ideal tees, both readings give 27.381586 m.

Two other checks agree:
- **Two constructions** (`probe_ports`): the members closed with Q put in at the ports, and the members forced. They agree to 8.2×10⁻¹³ m at 0.5, 1.0 and 1.2 × Q*.
- **The ladder** (`ladder`): the duty split, an equal split and 0.6/0.3/0.1 agree to 10 digits at 0.5, 1.0 and 1.2 × Q* (21.98796955, 30.31874935 and 35.12436994 m).

**Why.** The two outer ports separate the station from the rest of the network. The outside therefore sees only the total flow entering at one and leaving at the other, whatever the split inside.

### 2.3 Two exact curves at the outer ports meet at the duty

The **group curve** is the station alone, with its two ports held a set head apart (§3.3). The **group system curve** is the rest of the network, with the station's flow forced between its ports (§3.4). They cross at the solved duty, and each member's flow on the group curve there is its solved flow:

| Case | Crossing vs the duty | Members' flows at the duty's rise |
|---|---|---|
| `pumps_in_parallel`, ideal tees (`probe8`) | −7.65×10⁻¹⁴ relative | equal to 10 digits |
| same, Crane tees (`probe8`) | 4.91×10⁻⁹ relative (the duty solved at the default tolerance, the probe at 10⁻¹⁰) | equal to 9 digits |
| 3-pump Crane ladder (`ladder`) | −2.30×10⁻¹³ | P1, P2, P3 equal to 10 digits |
| `pumps_in_series` (`series_station`) | exact: at the reported rise 53.8074999 m the group curve gives 0.024823562366810072 m³/s, the solved flow bit for bit, and the group system curve at that flow is 53.8074999 m | — |

A station of one pump, with its ports at the pump's suction and discharge, gives D10's `/system-curve` to 7.1×10⁻¹⁵ m (`series_station`). The definition extends D10 rather than competing with it.

The probes stood in for the virtual forced link of §3.4: they used a forced split (parallel) or a demand pair with the members off (series). By §2.2's cut argument, each equals the virtual link.

### 2.4 Reported values give the duty exactly

From the solve's reported values only (`probe_header`):
- Each member's head, minus its legs' losses and its tee paths' losses (`branchResults.pathHeadLosses`), equals the EGL rise between the outer ports, with a difference of 0.0.
- With Crane tees:

  | Member | Head | Legs | Tee paths | Port rise |
  |---|---|---|---|---|
  | PA | 29.3226028 m | 2.19092 m | 0.163706 m | 26.9679813 m |
  | PB | 29.9118633 m | 1.62833 m | 1.31555 m | 26.9679813 m |

- Why it holds: `LinkResult.headLoss` is an EGL difference, and a pump's head is its EGL rise (`models/results.py:212`), so the sum telescopes.
- In series, the sum of the heads (58.8811995 m) minus the interstage loss (5.0737 m) is the port rise (53.8074999 m).

### 2.5 The group curve shows where each member stops

On the parallel fixture (`probe8`), PB delivers nothing from a rise of 33 m. Its shutoff head at s = 0.85 is 32.5125 m, and the solver closes a running pump whose head would exceed its shutoff head (`services/solver/status.py:175-187`, EPANET 2.2 pumpstatus).

The ladder (`ladder`):

| Rise | P1 | P2 | P3 |
|---|---|---|---|
| 33 m | 0.029166 m³/s | 0.018934 m³/s | 0 |
| 38 m | 0.02274 m³/s | 0.001266 m³/s | 0 |
| 40 m | 0.019262 m³/s | 0 | 0 |
| 45 m | 0 | 0 | 0 |

These are the dead-heading hazards that KSB, TEH-1109A, DOE Tip #8 and NRC 88-04 describe [read]. Here they are read from the solver's own rules, not from an assumed split.

**A speed-controlled member** (`series_station`, PB with a flow setpoint of 0.024 m³/s): the group curve holds 0.024 m³/s at rises of 40 and 50 m, with PB active. From 55 m up, PB runs at its maximum speed. This is D11's behaviour, with no split assumed.

### 2.6 Limits a group view must state

- **One pump off in series** (`probe9`): with PA or PB off, the chain carries zero flow. An `off` pump is a closed control, closed both ways (`status.py:369-375`). KSB describes a stopped series pump passing flow "as through a rotating throttle", and Fathom has "Pump Off with Flow Through" [read]. The app does not model this. Slice 4 states it and adds no model: no source read gives a loss law for a stopped impeller.
- **One pump off in parallel** works as a case today (`probe9`): with PB off, PA runs at 0.040752 m³/s against 0.037367 m³/s (+9.1 %), beyond its curve data, flagged `PUMP_OUTSIDE_CURVE`.
- **PRV and PSV inside a station.** Their setpoints are static pressures, that is, absolute heads. Every other law inside a station depends on head differences or flows: pipes, pumps, check valves, FCVs, branch K and equipment. So a station holding an active PRV or PSV has no group curve that is a function of the rise alone.
- **Several steady states (D13).** On drooping curves, a solve at a held rise can find another state than the full solve. This is checked at the duty (§5.4), not assumed.

### 2.7 Groups in the corpus

`detect` loaded and classified all 5,151 corpus projects in 6.7 s. Of the 1,789 projects with two or more pumps:
- **231** have pumps on one chain of two-port elements. In 85 of them some pumps face each other; in 67 a blocking element or an off pump sits on the chain.
- **52** have pump legs between the same two junctions. In 33 of them, one end is a reservoir or a reference node.
- **1,511** have neither.

## 3. Definitions (owner: Q1)

**No standard defines a group's system curve,** and the tools differ [read]:
- Datacor's Fathom holds a split, equal ("Traditional") or the solved one ("Enhanced");
- Bentley takes the losses along a "Representative Pump";
- Pipe Flow Expert swaps in one equivalent pump.

The definitions below need no split. For one pump they reduce to D10's. The group curve is UFC 3-240-04A's construction carried out by solves: there, each pump's curve less its own suction and discharge losses gives "a modified curve which represents pump performance at the point of connection to the discharge header", and capacities are added at equal head. The solves also take into account the header fittings and pipes inside the station, which no hand method separates.

### 3.1 Group, station, ports

- **Group:** 2 to 6 pumps the user ticks (page state, §4).
- **Station:** the smallest part of the solver network that meets all of these:
  - it holds every member's link;
  - it meets the rest of the network at exactly two places, the **inlet S** and the **outlet D**. Each is a port node, or a reservoir or reference node taken whole (every port of a boundary has the same fixed head, `services/solver/builder.py:648, 662`). A tee or wye centre is never S or D, so a header tee lies whole inside;
  - its interior holds no fixed-head node, no assigned-flow node and no pump that is not a member;
  - each member faces from S to D.
- Members drawing from two different reservoirs are not a station, even at equal levels: a scenario can change one level.
- **Interior:** every link of the station. **Outside:** every other link.
- **Arrangement**, found by the API and used for wording and columns:
  - **series:** one route from S to D passes every member in turn;
  - **parallel:** no member's discharge reaches another member's suction inside the station (tee ladders are parallel);
  - **mixed:** anything else, for example a 2 × 2 layout or a bypass around a series pump. The group curves of a mixed station are still exact; only the share and route-loss columns are left out.

### 3.2 The station's duty (exact, from one solve of the case)

- **Q_st:** the net flow from S into the interior. It equals the sum of the running members' flows, within the continuity tolerance, in parallel; it equals the common flow in series.
- **ΔH_st = EGL(D) − EGL(S):** an EGL rise, as a pump's head is (D7).
- **Per member:** status, speed, flow, head (the EGL rise at its flanges), and:
  - the **share**: Q_i/Q_st in parallel, H_i/ΣH in series;
  - in parallel, the **route head loss** H_i − ΔH_st: everything on the member's way from S to D, including tee paths and, in a ladder, header segments it shares with other members;
  - in series, the **interstage head loss** ΣH_i − ΔH_st (5.0737 m on the fixture).

### 3.3 The group curve

Q_group(ΔH) is the station's flow under these conditions:
- the station is solved **alone**, with nothing outside it;
- S is held at the duty's EGL(S), and D at EGL(S) + ΔH;
- every element inside follows its own law and rules:
  - members at their laws;
  - a speed-controlled member regulating;
  - off members closed;
  - check valves and FCVs by their rules;
  - branch K by the flow split.

Each point carries every member's flow, head and status. The curve is sampled on a **head** grid, which captures what a flow grid cannot: the shutoff plateau (no flow above the largest rise the station can hold) and a controlled member's vertical segment. It crosses the group system curve at the duty wherever the station has one steady state at that rise (§5.4). Since every law inside depends on differences only (PRV and PSV are refused, §5.6), the curve does not depend on the level chosen for S. Its absolute pressures away from the duty are not physical, so it reports no NPSHa and no pressure flags.

### 3.4 The group system curve (slice 4b)

H_sys,group(Q) = EGL(D) − EGL(S) under these conditions:
- every interior link is closed;
- one virtual fixed-flow link from S to D carries Q;
- the outside follows its own laws and rules: other pumps running, valves by their rules, as in D10.

It is D10's construction, with the whole station in place of one pump. It depends neither on the members' statuses nor on the split (§2.2). For a station of one pump it is D10's curve (§2.3).

### 3.5 The plain combined curve (reference; not drawn, owner Q2)

- Parallel: Σ Q_i(H) at equal flange head, a member adding nothing above its shutoff head.
- Series: Σ H_i(Q) at equal flow.

It is defined here so that the methods text and a later slice (4e) can name it. §2.1 is why the first slices do not draw it.

## 4. Groups on the page (owner: Q3)

- **Page state, no model change.** The members are chosen on the page, like the viewed pump (`chosen`, `PumpsView.svelte:46`), the active case (D15) and the goal-seek setup (D16):
  - not in the link, and not an undo step;
  - a link opens on the suggested default.
  - Rationale (design choice): nothing in the solve reads a grouping, and the API finds the station and the arrangement from the members alone (§5.2). So nothing needs storing to reproduce the curves, and D16 kept a setup out of `Project` for the same reason. Storing groups later is additive: about 56 link characters per two-pump group, measured on the reference project.
- **The suggestion** (`utils/pump-groups.ts`, new, pure; derive first's rules) runs on the topology as solved (`ws.store.solvedProject`), memoised per solve. It finds two kinds of group:
  - pumps on one chain of two-port elements, all facing the same way (series);
  - pumps whose chains lie between one pair of junctions (S, D) whose removal cuts the pumps off from every fixed head, assigned flow and other pump (parallel; tee ladders and pumps drawing from one reservoir included).

  The candidates are junctions within three junction hops of a member's chain ends, with at most 400 pairs.
  - The default is the suggested group holding the viewed pump. Other groups are offered as buttons ("Also found: P3 and P4").
  - The suggestion only picks members; the API is the authority on the station and its arrangement, and its `NOT_A_STATION` reasons are shown in words (§6.2).
- **Membership** is the same in every case, since scenarios never change topology (D15). Each case's member statuses come from that case's own results, so a scenario that turns a member off shows it off. *(As built, §14: an active PRV or PSV inside refuses a station, and a scenario can set one active or not, so the suggestion reads the case's own values.)*

## 5. API, slice 4a: the group curve

### 5.1 Endpoint

`POST /api/v1/pump-group-curve` sits in `routers/solve.py` beside `/system-curve`. It uses the same worker pool, 45 s budget, gzip compression and rate limit; a client has one request at a time.

**Request** (`models/api.py`):
- `project`;
- `scenarioId?` (body only, D15);
- `pumpIds`: 2–6 distinct ids;
- `curve`: `'group'` (4b adds `'system'`);
- `headMin?` and `headMax?` (m);
- `numPoints` (5–201, default 41).

**Response:**
- `station`:
  - `inlet` and `outlet`, each `{componentId, portId | null}` (null: a boundary taken whole);
  - `arrangement`;
  - `memberIds` in component order;
  - `interiorComponentIds` and `interiorConnectionIds`.
- `duty` (§3.2):
  - `{flow, head}`;
  - `members[]`, each `{pumpId, status, speed, flow, head, share | null, routeHeadLoss | null}`;
  - `interstageHeadLoss | null`.

  A case that does not converge gives `duty: null` and no points, with a message. The web never asks for one (Compare's rule).
- `dutyCheck` (§5.4): `{agrees, flow, members: [{pumpId, flow}], message}`.
- `points[]`, sorted by head. Each is `{head, flow | null, converged, members: [{pumpId, flow, head, status, beyondData}], reason | null, message | null, componentIds}`, where:
  - `reason` is `not_converged` (naming the oscillating components, as `/solve` does, SDD §4.10) or `not_computed` (past the budget);
  - with both ports held, every converged point has a flow;
  - `beyondData` is true when the member runs beyond its head data, on the end tangent (the `PUMP_OUTSIDE_CURVE` condition).
- `headRange`;
- `methods` (a `MethodsSection`, as goal seek's response carries one);
- `methodVersion` and `scenario` (D15).

### 5.2 Station finder (`services/pump_groups.py`, new)

The finder works on the built network, reading it only.

1. Join each boundary's port nodes into one vertex.
2. Bound the search region to what is reachable from the members before a fixed head, an assigned flow or another pump, since the interior can hold none of these.
3. For each candidate outlet, take the articulation points of the rest as candidate inlets (Hopcroft–Tarjan). Only port nodes and joined boundaries may be cut.
4. Keep the pair with the smallest interior; ties go by node key.

The cost is O(N·(N+E)) at worst, run only on request. Its time is measured over the corpus and on a 1,000-component project, the model's limit (`models/project.py:110`).

The finder reports either the station or every reason it has none (§5.6).

### 5.3 The group curve's solves

**The network.** The group curve is solved on the interior alone: a network holding only the interior's nodes and links, with S and D at fixed heads and nothing outside (no outside boundary, demand or pump).
- **Design choice:** it is a re-indexed copy of the built network, made in `services/pump_groups.py`, so that nothing under `services/solver/` changes.
- **Fallback:** if the build finds the copy fragile, use an additive, defaulted option of `run_outer_loop` that holds the outside CLOSED with its demands set to zero, proved by the corpus comparison of §9.1.
- **Why the outside is removed, not just left in place** (the probes left it): an outside part can fail to converge, or be disconnected (an assigned flow cut off, D12), and the solve would then be reported as not converged even though the station itself solved.

**The grid.**
- `numPoints` heads, evenly spaced, plus ΔH_st exactly, so the duty's rise is a sample.
- Default `headMin`: min(0, ΔH_st).
- Default `headMax`: the largest rise the station can hold with flow. This is the largest, over the routes from S to D, of the sum of the members' shutoff heads s²H₀(0), taken at the maximum speed for a speed-controlled member. Above it the solver closes the members (`pump_status`).

**Order.**
- The duty's rise is solved first, warm-started from the case's solve restricted to the interior.
- Then the points outward, each from its converged neighbour toward the duty.
- A point that does not converge from there is solved again from the initial state (D10's retry).
- So the curve is the branch through the duty.

**Cost.** One solve of the case, plus at most `numPoints` + 1 solves of the interior, a far smaller network than D10's.

### 5.4 Duty check (the D13 guard)

The request solves the case once; a unit test asserts this solve is bit-identical to `/solve`. The group curve's point at ΔH_st is the check.

`agrees` is true when the station flow and every member's flow are each within 0.5 % (D6) or 10⁻⁶ m³/s (D16's flow floor), whichever is looser. Otherwise the message says that the station has another steady state at the duty's rise, naming the members whose state differs. The web then does not claim that the curve passes through the duty (§6.4).

### 5.5 Methods section

The section states:
- the station's ports and interior, by id;
- the definitions of §3.2–3.3, with their equations;
- the cut argument (the outside sees only Q at S and D);
- the grid, the order and the retries;
- the duty check's result;
- why the absolute pressures along the curve are not reported;
- that no standard defines a group's curves, with Datacor, Bentley and UFC 3-240-04A cited for the alternatives and the construction;
- that a stopped pump is closed;
- `METHOD_VERSION`.

### 5.6 Errors, in D16's order

1. The request: 400 (count, duplicates). No submitted value is echoed.
2. The scenario: 404 or 400 (D15).
3. The case fluid: 400.
4. An id that is not in the project or is not a pump: 404, naming it.
5. The case's topology: 422, as for `/solve`.
6. `NOT_A_STATION`: 422, listing every issue with its `reason` and ids, and nothing else echoed. The reasons are:
   - `no_separating_ports`;
   - `fixed_head_inside`, `assigned_flow_inside` and `other_pump_inside`, each naming the element;
   - `member_reversed`;
   - `different_boundaries`;
   - for `curve: 'group'` only, `pressure_control_inside`: a PRV or PSV that is neither `failed_open` nor `failed_closed` (§2.6). The group system curve of 4b is still computed for such a station.

### 5.7 Versions and privacy

**`METHOD_VERSION` stays 1.3.0** (design choice; D16's precedent):
- no solved value, flag or trace changes;
- every point is a solve by 1.3.0's laws;
- the construction is defined in the response's own methods section, as goal seek's search is.
- D18's rule (a new result names a version that has it) applies to elements inside `/solve`, and the group curve is not one of them.

**`schemaVersion` stays 1:** nothing is added to `Project`.

**Privacy:** request bodies are never logged, and errors name only ids (D10).

## 6. Web, slice 4a

### 6.1 Where

**Placement.** A "Pumps together" card (`components/results/PumpGroupChart.svelte`, new) in `PumpsView`, under the pump chart:
- It is shown when two or more pumps have results.
- It is a disclosure, closed by default.
- `PumpChart` is unchanged. A group entry in the "Pump chart" select would split nearly every derived value of a chart built around one pump (web notes §2).

**The request.**
- Opening the card with a group of two or more members requests the group curve, as viewing a pump requests its system curve.
- One request at a time, queued with the system curves (D10), with `aria-busy`, a progress line (`role=status`) and Cancel.
- Cached against the solve response, the case and the sorted member ids.
- A solve or goal seek cancels and drops it (`project.svelte.ts` `#cancelSystemCurves`), and a curve is never shown with another solve's results.

### 6.2 Members

**The fieldset.**
- "Pumps in the group": one checkbox per pump with a result, labels `min-h-11`.
- At most 6 members (`MAX_CHART_CASES`, `pump-chart.ts:722`); a capped box is `aria-disabled` with a hint, as the cases fieldset does (`PumpChart.svelte:638-674`).
- No arrangement input: the API reports the arrangement.

**When the API refuses** (`NOT_A_STATION`):
- the card says why in words, with element names linked to their results, for example "T3 connects the pumps to the rest of the network a third time" or "PA and PB face opposite ways";
- the members' curves and points are still drawn, since they are exact and need no request.

### 6.3 Chart (head panel only: 16 rem on phones, 18 rem on desktop, `chartHeightRem`)

**Members** (exact, no request):
- Each member's curve, from `pumpChartData` unchanged: solid over its data, dashed beyond, the start tangent dashed to the shutoff head. Its x value is the flow through that pump.
- Members with the same curve at the same speed share one line that names them all (the once-per-speed precedent, `pump-chart.ts:783-792`).
- Each member's solved point: a filled marker with its own shape and a direct label. A pump held at zero flow gets the pump chart's diamond.

**The group curve** (from the response):
- ink, 2 px, solid;
- dashed where a member runs beyond its data;
- gaps at points without a flow;
- its x value is the station's flow.

**The station point** (Q_st, ΔH_st): an ink marker labelled "Group", always drawn, because it is the solve's exact duty. It is labelled as on the group curve only when `dutyCheck.agrees`.

**Not drawn:**
- the plain combined curve (Q2);
- each member's own system curve. That curve is drawn against its own pump's flow and crosses only that pump's curve; it stays on that pump's chart, and a note says so (design choice: a curve against one pump's flow on an axis the group curve reads as total flow invites the misreading GOALS §3 ranks worst).

**Colours** (design choice):
- Orange keeps one meaning across the Pumps view: the system. It is reserved for the group system curve of 4b.
- Members take the dataviz palette's slots 1 and 3 (blue `#2a78d6`, aqua `#1baf7a`) in ticking order. Together with orange, these are the three slots validated all-pairs.
- A third or later member reuses those hues with its own dash pattern and marker. A colour follows its pump while it stays ticked.
- Aqua is 2.82:1 on white, below the proposal's 3:1 (pump-chart.md §7). Either a darker validated step is used, re-checked with the palette's validator, or the relief rule applies: direct labels and the table.
- Identity never rests on colour alone: colour, dash, marker, direct label, legend and table row all carry it (WCAG 1.4.1, 1.4.11). The markers have text stand-ins, as `MARKER_SYMBOLS` does.

### 6.4 Notes (the `chartNotes` pattern; one function for the screen and the image footer)

- **Parallel:** "Pump curves and points are at each pump's flanges. The group curve is the rise from T1 (run inlet) to T2 (run outlet), solved with every pump on its own law: it lies below the pumps' curves added together by each pump's own losses on its way. At the duty PA loses 2.35 m and PB 2.94 m."
- **Series:** "… the piping between the pumps loses 5.07 m at the duty."
- **A dead-headed member** (from the curve's data): "PB delivers nothing from a rise of 33.0 m: above its shutoff head, 32.5 m, the solver closes it." *(As built, §14: "PB delivers nothing from a rise of 33.0 m, the first rise sampled where it has no flow: its own head there, the rise plus its losses on the way, would be above 32.5 m, so the solver closes it"; the rule compares the pump's own head, not the rise.)*
- **An off member:** "{member} is off and adds nothing. A stopped pump is closed both ways in this app; in series it blocks the line (a stopped pump passing flow is not modelled)."
- **A controlled member:** "{member} is speed-controlled: its curve is drawn at its solved speed, {s}; the group curve follows its control."
- **Each pump's own system curve:** "Each pump's own system curve is on its pump chart above; it crosses that pump's curve, not the group curve."
- **When the duty check fails:** its message, and "Several steady states can exist (D13); the point is the one the solve found."
- **"How this curve is computed"** (under Details): the response's methods section, as D10 links each pump's trace.

### 6.5 The group table and the data table

**The group table** (exact; under the chart, and since the Pumps tab's S2 before it, under the heading "Station", §18; a scroll region with a sticky first column):
- **Columns for every arrangement:**
  - Pump, a link to its trace;
  - State, Speed, Flow, Share, Head;
  - η, Shaft power, NPSH margin;
  - Shutoff head, at the running speed, and at the maximum speed for a controlled pump;
  - Inside curve data;
  - flags.
- **Parallel adds:** "Lost on its way".
- **Series adds:** inlet and discharge static pressure (gauge, from `nodeResults`), the facts a casing check would use.
- **Footer:** the station's flow, the rise between S and D (both named), and, in series, the interstage loss.
- **Where values come from:**
  - the per-member values come from the solve and are shown before the group curve arrives;
  - share and route loss come from the response's `duty`.
- **Not shown:** the % of BEP flow (left to the opt-in checks, owner 2026-10-26). D19 verdicts appear only when checks are on.

**The data table** (the long description; the `PumpChart.svelte:710-975` pattern; since the Pumps tab's S2 the table opens after the notes and methods, and since S3 its Show data table sits after the request line, before the legend, §18):
- the members' points;
- the station's duty and its check;
- the group curve's samples, each with its head, total flow, and every member's flow, head and status, or the point's reason.

### 6.6 States, scenarios, image

**States.** As the pump chart:
- **not converged:** no values and no image;
- **out of date:** labelled in the caption and the image;
- **a failed or not-reached case:** Compare's rule, no earlier response used;
- **a failed chunk load:** the tables stay.

**Scenarios.** The card shows the case being viewed and sends its `scenarioId`. Other cases are not drawn in 4a (4d).

**Image.** "Download image" through `downloadChartImage` (`utils/export/chart-image.ts:313`), with a group configuration (`pumpGroupConfig` in `pump-chart-config.ts`, same chunk).
- The caption's title becomes a parameter, "Pumps together: PA, PB (parallel)[, case]"; today it is fixed at `:90`.
- The notes go in the footer (`imageNoteLines`).

**Export.** The workbook is unchanged in 4a; its About says that group curves are left out (D17 lists what is left out and why). The sheet is 4c.

### 6.7 Accessibility and phones

**Structure.**
- `figure` and `figcaption` ("Pumps PA and PB in parallel").
- A `role=img` wrapper whose name gives every member's point and share, the station's duty and "group curve shown"; the canvas is `aria-hidden`.
- Scroll regions with `tabindex=0`, `role=region` and `aria-labelledby`.

**No readout slider in 4a.** The data table gives every sample exactly. A readout along the curves comes with 4b, where the crossing makes it worth having.

**Phones (390 × 844).**
- The head panel at 16 rem.
- The legend under the chart.
- The checkboxes wrap.
- No sideways page scroll.
- On a phone, identity relies on the legend, markers and table, because direct labels can collide (overlap avoidance covers short labels only).

## 7. Slice 4b: the group system curve (API + web)

**API.** `curve: 'system'` (§3.4):
- **Points:** D10's `SystemCurvePoint` shape and its nine reasons (`models/api.py:171-181`), without `npshAvailable`, because with the interior removed the members' suction EGLs are not solved.
- **Grid:** D10's, from 0 to 1.2 × the group curve's largest flow, plus Q_st exactly.
- **Duty check:** at Q_st, warm-started from the solve.

**Machinery.** D10's machinery is generalised from "the pump link" (`PumpData`) to a forced element `{start node, end node, link index, the links it replaces, a label for messages}`. The functions affected are:
- `has_way_through`;
- `flow_limit`, with S as the sink and D as the source, and the interior left out;
- `_read`;
- `_at_switch` and `_switch_message`;
- `_held_open_switch`;
- `_message`.

All are in `system_curve.py`. The virtual link enters through an additive `forced_links` option of `link_states` and `run_outer_loop`. The GGA already treats a `FIXED_FLOW` link as a demand at its start and a supply at its end (`network.py`, `LinkMode.FIXED_FLOW`). The pump path stays bit-identical.

**Rejected: a demand pair at S and D.** It works numerically, but the outer loop and `flow_limit` would treat S and D as assigned-flow nodes, and their messages would call a tee port one (API notes §2).

**Web.**
- The group system curve is drawn in the system orange, with gaps and its reasons as D10's (`systemRows`).
- When both duty checks agree, the station point is labelled as the crossing.
- A "Read along the curves" slider steps over the response's samples. At each sample it gives every member's flow exactly ("At a rise of 20.0 m: PA 43.8 L/s, PB 24.0 L/s, group 67.8 L/s"), with no interpolation in the browser and its value text carrying the readout.
- The note: "The group's system curve is the rise the rest of the network needs between T1 and T2 at each total flow; it does not depend on how the pumps share the flow."

**Versions.** `METHOD_VERSION` is unchanged: no `/solve` value or `/system-curve` point changes, which the proof of §9.2 shows.

## 8. Later slices

Each is its own PR, and each is a reversible default unless marked **owner**.

- **4c, export (web)** (built, §16). A "Pump groups" sheet after "System curves":
  - the station, the duty with its check, and both curves' points with their reasons, written only as computed (D17: system curves only as computed);
  - shares and route losses come from the API's `duty`, never computed by the export;
  - About lines appear only in a file that has the sheet;
  - proof: writer and oracle tests over a group case added to `tests/fixtures/export_input.py`, and the committed-workbook verifier.
- **4d, one pump off (web).**
  - **An "Add cases with one pump off" action, parallel stations only.** It creates one D15 scenario per running member, each with the single override `{component, status: 'off'}`:
    - one undo step;
    - it skips a set that already exists, and refuses with the count past `MAX_SCENARIOS` (20);
    - then it offers Solve all.

    In series the action is replaced by §2.6's note: a stopped pump blocks the line in this app.
  - **A "Running combinations" table:** one row per case with a response, by Compare's rule.
  - **Other cases' station duties on the group chart,** as hollow markers. They go on the base case's group system curve only when every override of that case targets the station's interior, since only then is that curve exactly shared.
  - **Extremes over the cases** (largest flow and shaft power, smallest NPSH margin) stay on screen only, by D17's rule, and are labelled "over these cases".

  *(Built as slice 4d, 2026-11-03: §17.)*
- **4e, the plain combined curve as an opt-in reference** (only if the owner chooses Q2 option 2).
  - **How it is computed:** sampled by the API from each member's `PumpCurveModel` at its running speed, as exact PCHIP inverses with the end-tangent extrapolation. The solver's rules apply: a member adds nothing above its shutoff head, and the curve has a gap over a rising stretch (`risingHeadRanges`).
  - **How it is drawn:** slate, dotted. No crossing is marked, and a note quotes its miss against the group system curve.
  - **Never computed from the drawn lines:** near a flat shutoff those err by up to 47 % in flow at a given head (web probe).
- **4f, stored groups** (only if the owner chooses Q3 option 2).
  - **The field:** `Project.pumpGroups [{id, name, pumpIds}]`, with no arrangement field.
    - It is omitted when empty (`exclude_if`, as `scenarios`), and its ids are validated.
    - It is not on D15's allow-list, and the solver ignores it.
  - **Edits:**
    - a deleted pump is dropped from its groups in the same undo step;
    - a group left with fewer than two members is removed.
- **4g, impeller trims (owner, Q4).** An optional `PumpCurve.impellerDiameter` label that the solve does not read, as D19's manufacturer data. A trimmed impeller is the maker's curve at that diameter, entered as its own `pumpLibrary` curve, which works today (`Pump.curveId`). No computed trim law.
- **4h, the ISO 9906 tolerance (owner, Q4).**
  - **Inputs:** on `PumpCurve`, the grade, the guarantee point, and an optional η_G or P_G (not both).
  - **Drawing:** KSB's tolerance cross at the guarantee point, on each pump's own chart.
  - **Verdict:** an opt-in D19 check.
  - **Citation:** the 2012 grade table, as reproduced by KSB, Wilfley and the HI white paper (secondary sources).
  - **No band along the curve:** HI does not say how its band is built, so one would be our own construction.
- **4i, group design checks (owner, D19's framework).** Each needs a new input:
  - **Series casing pressure:** the inlet pressure at the duty + ρg × the shutoff head at the maximum speed ≤ a new optional `PumpCurve.maximumOperatingPressure`. The rule is cited from the Grundfos manuals [read]. It is user data only, with no preset, because API 610's MAWP definition was seen only as a snippet. The check states that the next pump's inlet pressure is higher at zero flow.
  - **API 610's ≥ 10 % head rise** from a new rated point, cited only through WWD and Datacor, which quote the standard.
  - **Each member against its minimum flow** in every combination that runs (through cases).
- **Later, each its own decision:**
  - a group curve with an active PRV or PSV inside (it needs the inlet level along the group system curve, not one held level);
  - a stopped pump passing flow (it needs a cited loss law);
  - nested groups;
  - goal-seek station quantities (station flow, station rise);
  - lead/lag stations (D11, deferred).

## 9. Tests and proof

### 9.1 Slice 4a

**Reference cases** (`tests/reference/test_pump_groups.py`). They are written by a tester who did not read `services/`. The closed forms use SciPy's PCHIP and the affinity laws, with Darcy–Weisbach and Colebrook from `fluids` and Crane tees from `fluids.fittings`.

- **PG1.** Identical pumps on symmetric legs, ideal tees.
  - Group curve: Q = 2q, where H(q) − h_leg(q) = ΔH.
  - Each share is exactly 0.5.
- **PG2.** `pumps_in_parallel` (dissimilar speeds).
  - Each leg's equation is solved separately at each ΔH.
  - PB's flow is 0 for ΔH ≥ 32.5125 m.
- **PG3.** PG2 with Crane tees.
  - The group curve at `/solve`'s duty agrees within D6, and so does each member's flow there.
  - Each route loss equals the sum of the reported losses along its route.
- **PG4.** `pumps_in_series`.
  - Group curve: Q from H_A + H_B − h_L2 = ΔH.
  - The interstage loss at the duty is 5.0737 m.
- **PG5.** PG4 with PB on a flow setpoint.
  - The group curve holds Q_set over the band given by D11's F(s, Q_set).
  - Outside the band it follows the limit speeds.
- **PG6.** The 3-pump Crane ladder with check valves.
  - The duty and each member's flow are reproduced.
  - P3 and P2 stop at the rises of §2.5.
- **PG7.** A station of one pump: the group curve is the inverse of s²H₀(Q/s).
- **PG8.** A reservoir as the inlet: the members draw from one reservoir through separate ports.
- **PG9.** Not a station: one case per reason code, among them an assigned flow tapped between member tees, a non-member pump inside, two reservoirs, a reversed member, and a PRV in a member leg.
- **PG10.** An off member.
  - It is left out of the duty's shares.
  - The group curve is the other members' only.
- **PG11** (if the tester can build one). A drooping member with two steady states: `dutyCheck.agrees` is false, and the message names the member.

**Unit tests:**
- the finder (ports, interior, arrangement, ties, reasons) on every reference topology;
- the default `headMax`;
- the methods text;
- the error order, with no submitted value echoed;
- with `scenarioId`, the result equals the hand-edited project's (D15);
- the duty's solve is bit-identical to `/solve`;
- points past the budget are `not_computed`.

**Corpus.**
- **Comparison against `b6e2088`:** `/solve` identical for 5,151 projects with no ignores. Nothing under `services/solver/` changes. If §5.3's fallback is used, every `/system-curve` point must be identical too.
- **A new `tests/differential/pump_group_check.py`.** It covers every corpus project with two or more pumps, for every group the web suggests and every pair of pumps that forms a station. It checks:
  - the duty check;
  - §2.4's identities (continuity at S, and the telescoping route losses within 10⁻⁹ m);
  - the finder against a second implementation, written by someone who did not read the finder, that tests every pair of candidate port nodes by plain reachability (not Hopcroft–Tarjan);
  - that every web suggestion is accepted by the finder.

  It reports counts by arrangement, refusals by reason, and timings. It exits with status 1 on any violation, and the counts go in TSD §10.4.

**Web.**
- **A shared fixture of real API responses** (`apps/api/tests/fixtures/pump_groups_input.py`, as `export_input.py`), covering:
  - parallel with ideal and with Crane tees;
  - the ladder;
  - series;
  - a dead-headed member;
  - an off member;
  - a controlled member;
  - a refused group.
- **Unit tests:**
  - `pump-groups.test.ts` (suggestions on hand-built projects and their negatives);
  - group chart data and config (members' datasets, colours kept while ticked, dashes and shapes, the station point and its label rule, no other marker);
  - the notes' exact wording.
- **Component tests:**
  - the disclosure and the request, with progress, Cancel and focus moves;
  - the member cap and its hint;
  - the refusal's words;
  - the accessible name and the data table toggle;
  - the image's unavailable reasons;
  - a case switch keeping the members.
- **End to end:** `pump-groups.e2e.ts` on desktop (1280 × 800) and phone (390 × 844) against the real API.
  - The flows: parallel, series and a refused group.
  - Assertions: the table's values equal the intercepted responses; no sideways scroll; the PNG signature.
- **Axe:** a clean scan at both sizes, outside the suite, recorded in the as-built section as slices 1–3 did.

### 9.2 Slice 4b

**Reference cases.**
- The group system curve in closed form:
  - for PG2 and PG3 (pipes only outside: static + h_L1 + h_L2);
  - for PG4 (H_R2 − H_R1 + h_L1 + h_L3).
- With Crane tees, the curve is the same at three forced splits to 10⁻⁹ m.
- Invariance: PG10's curve is identical with the member on or off.

**Consistency.**
- A one-member station gives `/system-curve` within 10⁻¹² m on every corpus pump.
- The virtual link agrees with the forced-split construction read at S and D (`probe7`'s), within 10⁻⁹ m, wherever both converge.
- The group curve and the group system curve cross at the duty, within the solver tolerance, for every station in the differential check.

**Corpus comparison** (`system_curve.py` and `status.py` change): `/solve` identical for 5,151 projects, and every corpus pump's `/system-curve` points identical (as slice 1 did for 70,192 points), with no ignores. D13's acceptance rule otherwise.

**Timings** against the 45 s budget (TSD §5.6).

**Web:** the e2e and axe steps above, extended to the system curve and the readout.

## 10. Specs to update in each build

- **CLAUDE.md:** a new decision D21 (pump groups: the station frame, page-state groups, the answers to §13). Mark slice 4 in `docs/proposals/pump-chart.md` §6 and its status line.
- **PRD** §3.2.2 Pump Analysis: the group view.
- **SDD:** a new §4.16 (pump group curve model; §4.17 as built, the orifice plate having taken §4.16) and §5.1 (the endpoint and `NOT_A_STATION`); §3.1.3, the Pumps view.
- **TSD:**
  - a new §5.9 (the finder, the interior network, the grid and the duty check; in 4b, the forced element);
  - the file layout;
  - the §10 web test list;
  - §10.4 counts;
  - §12 entries: groups as page state; the plain sum not drawn; a PRV or PSV inside a station; a stopped pump passing flow.
- **A new §14 "As built"** in this proposal for each slice.
- **Branch:** 4a and 4b touch the API, so they do not go on a `web/*` branch (CLAUDE.md, Tooling). 4c and 4d may.

## 11. What was taken from each design

| From | Taken | Left, and why |
|---|---|---|
| Derive first | groups as page state with a suggested default and "Also found"; the suggestion rules (series chains, the (S, D) cut, ladders, the pair cap); the reported-value identities as checks (§2.4, §9.1); members' curves via `pumpChartData` unchanged, shared lines for identical curves; a shared fixture of real responses; the colour and phone constraints; the states rules; the image | the combined curve computed from the drawn lines: it breaks pump-chart.md principle 1, carries the lines' error (up to 47 % in flow near a flat shutoff), and crosses no system curve at the duty (§2.1); each member's own system curve on the group chart: mixed flow axes |
| Engineer first | the station-boundary framing at port nodes; UFC 3-240-04A as the construction's citation; the station table's columns (η, P, NPSH margin, shutoff head, series inlet and discharge pressures); N−1 for parallel only, with the series note; the "Running combinations" table; the casing-pressure check; trims and ISO 9906 as user data | `Project.pumpGroups` in the first slice: nothing in the solve reads it (now Q3); `pumpGroupResults` inside `/solve`: it would put graph work and curve sampling into every solve of a grouped project, and its combined curve was the plain sum; `METHOD_VERSION` 1.4.0 for station curves: D16's precedent fits an endpoint outside `/solve` better |
| Correctness first | the definitions (§3), the endpoint and its reasons, `pressure_control_inside`, the head grid solved outward from the duty, the duty check, the methods section, reference cases PG1–PG11, the corpus proof of 4b, the rejected demand pair | 4a as the system curve and group curve together: the D10 refactor is the risky part, so it is split into 4b to keep 4a to one PR, and the group curve alone already replaces the composite with an exact curve; the members drawn in slots after orange: only three slots validate all-pairs, so members get blue and aqua |

## 12. Risks

- **Two flows on one axis.** Members' curves use each pump's own flow, and the group curve uses the station's (in parallel). A reader may still cross a member's curve with a group curve. Mitigations: the notes and legend name each line's flow, and the only group marker is the solve's duty. In 4b the crossing is labelled only when both duty checks agree.
- **Station finding.** Detection will often say "no station" or "mixed": side consumers on a header, two reservoirs, a station in a loop, opposed pumps, bypasses. Mitigations: every reason is named, the members are still drawn, and the differential check exercises suggestions and arbitrary pairs. The finder's worst case must fit the budget on a 1,000-component project.
- **The interior copy (§5.3)** must re-index every link reference (pumps, valves, branch legs, equipment, connections). An error there would give wrong flows, which the reference cases and the duty check would catch. The fallback is a solver option with a corpus proof.
- **Several steady states (D13).** The duty check guards the duty, and the outward order keeps the branch through it. Elsewhere, a point is the state its solve finds, and the methods text says so.
- **Held inlet level.** The group curve holds S at the duty's level, so absolute pressures away from the duty are not physical. No NPSHa or pressure flag is reported along it, and a PRV or PSV inside a station is refused.
- **4b's refactor** of D10's machinery could move `/solve` or `/system-curve` values. Mitigation: the pump path stays bit-identical, and the corpus comparison of every value and point must show no ignores.
- **Cost.** 4a costs one solve of the case plus about 42 small interior solves. 4b costs about D10's: 41 solves of the outside plus retries; a Crane-tee ladder's pump behind a series FCV took up to 14.8 s for a 41-point D10 curve at 206 components (TSD §5.6). Points past the budget are `not_computed`.
- **Phones.** Up to six members, the group curve and, in 4b, the group system curve on a 16 rem chart. Mitigations: shared lines for identical curves, the legend, markers and table carry identity, and the system curves of single pumps stay on their own charts.
- **A modelling gap made visible.** An off pump in series blocks the line; practitioners expect a rotating throttle. The view says so wherever a series member is off, and the N−1 action is not offered for series stations.
- **Owner expectations.** The slice text asks for "the group's combined curve as a reference only". This proposal puts an exact curve in its place and leaves the plain one to Q2.
- **UFC 3-240-04A** was read through a third-party mirror; the official copy must be checked before the build cites it.

## 13. Owner questions

**Q1. How are the group's curves defined?**
1. *(recommended)* Between the station's outer ports S and D:
   - the **group curve**: the station alone, with S and D held ΔH apart and every element on its own rules;
   - the **group system curve**: the rest of the network, with the station's flow forced from S to D (D10 widened).

   The group curve comes in 4a and the group system curve in 4b. One definition covers parallel, series, ladders and one pump, where it is D10's.
2. Datacor's "Enhanced" convention: each pump forced at its solved share of the total, read at its own flanges.
3. No group curves: each pump's own D10 system curve only.

*Why:* No standard defines a group's system curve, and the tools differ. Option 1 is the only one that is exact at every flow:
- the two curves cross at the solved duty (7.7×10⁻¹⁴ with ideal tees, 4.9×10⁻⁹ with Crane tees, 2.3×10⁻¹³ on a 3-pump ladder);
- at the outer ports the system curve does not depend on any split;
- the group curve gives each member's flow at every rise from the solver's own rules.

A fixed split is exact only at the duty, and at the tee centres it moves the header head by 0.6 % (beyond D6). Option 3 does not give what slice 4 asks for.

**Q2. Is the plain combined curve drawn (flows added at equal flange head, or heads at equal flow)?**
1. *(recommended)* Not drawn: the exact group curve takes its place. Revisit after users have seen it.
2. Also drawn, as an opt-in reference sampled by the API from the solver's interpolants: slate, dotted, never crossed with a system curve, its miss quoted in a note (later slice 4e).
3. Drawn by default as the slice text says, computed by the web from the drawn lines.

*Why:* On the fixtures the plain sum crosses the group system curve 6.3–10.3 % beyond the duty, with a member off by up to 24.6 %. Drawn beside an exact curve, it invites the misreading GOALS §3 ranks worst. The group curve shows what the composite was for, the "hump" where a weaker pump stops, exactly. Option 3 also breaks pump-chart.md principle 1: near a flat shutoff the drawn lines err by up to 47 % in flow at a given head.

**Q3. Where does a pump group live?**
1. *(recommended)* Page state: members chosen on the page, defaulting to a group suggested from the topology as solved; the API finds the station and its arrangement. A link opens on the suggestion.
2. Stored: `Project.pumpGroups [{id, name, pumpIds}]`, omitted when empty, so a link reopens a hand-picked group (later slice 4f).

*Why:* Nothing in the solve reads a grouping, and the API derives the station and arrangement from the members, so nothing needs storing to reproduce the curves. D16 kept goal seek's setup out of `Project` for the same reason. D14 keeps the choice reversible, and storing groups later is additive (about 56 link characters per two-pump group).

**Q4. Do impeller trims and the ISO 9906 tolerance get inputs in slice 4?**
1. *(recommended)* No new inputs in slice 4:
   - a trimmed impeller is the maker's curve at that diameter, entered as its own library curve (works today);
   - the ISO 9906 tolerance cross at a user-entered guarantee point and grade waits for a later opt-in check (4h).
2. Add the inputs now: an `impellerDiameter` label on `PumpCurve` (not read by the solve), and an ISO 9906 grade with a guarantee point (and η_G or P_G), drawn as KSB's tolerance cross.
3. Compute trimmed curves by a law (DOE/HI: Q ∝ D, H ∝ D²; or KSB: Q, H ∝ D²), limited to HI's 5 % with a flag beyond.

*Why:*
- **Trims.** The trim laws disagree: for a 5 % trim, flow falls 5 % under one and 9.75 % under the other. HI endorses affinity predictions only to a 5 % reduction, and a 2024 study of Grundfos, KSB and VIPOM curves found that none matches real trimmed impellers. GOALS §4.1 allows only cited data, and the maker's curve is that data.
- **ISO 9906.** It is known here only through secondary sources (KSB, Wilfley, HI); it serves acceptance testing more than network sizing, and is design practice, so opt-in (GOALS §4.6).

## 14. As built (slice 4a, 2026-10-28)

The owner chose the recommended answer to every question of §13 (status line). Slice 4a was built as §5 and §6 describe, with these departures:

- **API**
  - **One pump is a group.** `pumpIds` takes 1 to 6 ids, so a station of one pump (PG7) is a request; the web asks for two or more. A station of one pump is reported as parallel (its share 1, its route loss 0).
  - **The finder is one minimum vertex cut**, not articulation points per candidate outlet (§5.2): every vertex passes one unit but tee and wye centres, the members' ends join a source and every boundary, assigned-flow node and other pump's port a sink, and the cut nearest the source after Edmonds–Karp's augmenting paths is the smallest station (Menger's theorem). 3.5 ms at 206 components, 13 ms at 1,000; a refusal 24 ms at 1,000.
  - **The station is solved alone by §5.3's fallback, not by a re-indexed copy.** The copy would have had to re-index the branch legs' laws (their own and reference links), the branch solutions, the port pipes and the warm-start flows. Instead `BuiltNetwork.held_closed` (empty for every network `build_network` makes, applied last in `status.link_states`) holds every outside link closed, and a shallow copy of the built network keeps only the station's pumps, valves, equipment and branches under the rules, with every demand set aside and S and D fixed heads. Every index stays, so the case's solve warm-starts the station as it is. The GGA removes the closed-off outside, so a point costs about a solve of the station: 42 points took 0.5 s on a 1,000-component network whose own solve took 5.4 s. Proof: the corpus comparison against `b6e2088`, 5,151 identical, 0 different, no ignores (the dumps hold every pump's system curve, so `/system-curve` is unchanged too); merged with the orifice plate (D20), against `b7f09eb`, 5,168 identical.
  - **Refusal reasons.** With three places or more, the cut is searched again with assigned flows, other pumps, both, then each boundary lifted out of the sink. A lift explains the refusal only when the search then finds a station by structure: two places, and every member facing from one to the other. Without that test, lifting the delivery reservoir of a group whose suction header meets three reservoirs left the two suction ports as the "places". Only boundaries whose lift can leave a station alone are tried (TSD §5.9's `_lift_candidates`: with three places, those the cut's flow ends at; lifting every boundary in turn took 3.65 s on a refusal with 497 reservoirs, now 24 ms, with the same reasons for all 4,235 corpus groups). Every reason is listed: an active PRV or PSV inside the station a lift finds is named beside the lifted reason. A lift explains when it leaves a station `find_station` accepts, including one whose members do not tell its places apart but lie on a way between them (the second review: requiring every member to face one way skipped such a lift, and a larger lift then named elements outside the station). `DIFFERENT_BOUNDARIES` is kept for members whose own chains of pipes and two-port elements end at different boundaries. Any other boundary a station cannot hold is `FIXED_HEAD_INSIDE`, naming every boundary whose lift leaves a station: a tank on a discharge header names the tank and the delivery reservoir, either of which lifted leaves one. `NO_SEPARATING_PORTS` names the places otherwise, or the one place (no flow passes through). The review gave three cases codes of their own, so that the web need not tell them apart from the ids: `NO_WAY_THROUGH` (two places, no member on a way between them), `MEMBERS_OPPOSED` (as many members facing each way, every one named) and `MEMBER_REVERSED` (the fewer, facing against the rest). The codes are upper case, as every other error code (§5.6 wrote them lower case).
  - **A header piped to the outlet's boundary** makes that boundary D, taken whole: the pipe and the outlet piping are inside, and the station is mixed. This is a station by §3.1's definition, though not what a reader may expect, so the response names both ports.
  - **Which port is S.** The members' majority direction along the ways through the station's parts (the members removed). Where no way from one port to the other passes a member (a bypass inside), S is the port the duty's flow enters, and the station is mixed. A duty flow within the solver's continuity tolerance of zero enters neither: the ports then keep the finder's order (the relief merge's review: the sign of round-off picked S for 12 corpus stations, and rises of a deadheaded station came out as +45 m or −45 m by a pipe's length). Whether a bypass that carries the flow back from D to S at the duty should mirror the frame is a question for the owner: as built it does.
  - **Loops and dead ends** (found by the corpus check, fixed): a single cut place that is not a pump's own port means the outside closes a loop through it (a closed circuit whose only fixed head is a tank, a pump circulating round a loop: 125 corpus groups were refused as "one place" before the fix); the cut is searched again toward that place alone. A single place at a pump's own port is a dead end. An unoriented station whose pumps lie on no simple path between its two places (each pump in a loop of its own off the way between them) is refused as `NO_WAY_THROUGH`: tested by a flow of 2 from the pump's ends to S and D, an independent criterion from the check's (blocks).
  - **A tank taken whole, and a loop's own place** (found by the reviews, fixed): pumps that draw from a tank's own nozzles and return to the same tank were refused as three places, since the loop search made the tank pass any flow. The loop search never makes its own place c a place, so the stations with c as one of their places are candidates too (each link of c in turn, every single vertex along the chain that cuts the members from it), ranked with the search's own pair: for a tank, every member facing one way first, then members facing both ways (refused for them), then none on a way; pairs with the tank whose members circulate through the tank itself (one on no way, or none telling the places apart) are left out, since every such layout also has a pair whose "rest" is one pump's suction pipe. A booster with a check-valve bypass that returns to its own tank is therefore refused (every pair with the tank circulates a pump through it); the same booster delivering to another reservoir is a station. The second review's random networks (`tests/differential/pump_group_random.py`) found these: 813 disagreements with the second finder in 20,000 networks before, 0 in 60,000 after.
  - **Default range with a bypassed member** (found by the reviews, fixed): a bypass inside that joins a member's two ends in one part hides it from the ways through the parts, so a booster with a check-valve bypass got the default top of one pump's shutoff head and half its curve went undrawn. Each way now adds the shutoff heads of the members whose two ends lie in a part it passes (90 m, not every member's 122.5 m, for a parallel pair followed by a bypassed booster).
  - **Methods' references:** Ford and Fulkerson (1962), Datacor (Keiser 2021) and the KSB Lexicon, not §5.5's Datacor, Bentley and UFC 3-240-04A (UFC 3-240-04A was read only through a mirror, §12).
  - **Floating ports** (found by the corpus check, fixed): a duty whose S or D alone lies in a section no reservoir or reference node reaches gave an arbitrary rise (6 corpus groups); it now has no duty and says why. A station whole in one floating section keeps its exact rise on the solver's arbitrary level.
  - **Response fields added to §5.1:** `converged` and `message` (the case's solve), `duty.inletEgl`, each point's `isDuty`, and each member point's `controlState` and `speed`.
  - **`METHOD_VERSION` is left as it is** (1.3.0 when built; 1.4.0 since the orifice plate, D20, merged first; 1.5.0 since the project library, D22; 1.6.0 since the relief valve, D23), `schemaVersion` 1.
  - **Relief valves inside a station** (merged with D23, 2026-10-29): a relief valve is a two-port element on the chains, follows its rule at every point and starts closed as in a solve; it is allowed inside, since its set is a pressure difference, compared with the EGL difference across it less its ports' fixed elevation term. The series interstage term ΣH_i − ΔH_st is the head across the elements between the pumps, a closed valve's held head included, and parallel shares are null at a duty without flow (they were −0.0 or 0.0 by the sign of round-off). `pump_group_check` reads relief valves and orifice plates on its walks (it found no reported loss for either, so a walk stopped there); `tests/unit/test_pump_groups_relief.py` (28 tests) and the check's smoke cases cover them, since no corpus station holds one.
- **Web**
  - **Caption** "Pump PA and Pump PB in parallel", from the pumps' names (which already say "Pump"); the image's title "Pumps together: Pump PA, Pump PB (parallel)[, case]".
  - **Legend** on screen is a list under the canvas (Chart.js's legend took half of the 16 rem plot on a phone); the image keeps Chart.js's, whose dashed lines draw solid, so their labels say "(dashed)".
  - **Table footer** is a list under the table, not a `<tfoot>` (a sticky full-width footer cell was cut off on phones).
  - **Aqua** is the palette's darker step `#199e70`, 3.41:1 on white, validated all-pairs with the blue and the system orange (CVD ΔE 8.4).
  - **Colour kept while ticked:** members hold slots; unticking frees one and the next ticked pump takes the first free.
  - **Suggestions:** up to 400 pairs per pump chain (not 400 in all), pairs not repeated across chains, so a large network still finds every station (172 ms at 998 components). Pumps a pump-less bypass joins are not suggested (the API finds them mixed); a 2 × 2 layout is suggested as one group and its two series pairs. Measured over the corpus, the suggestion rules of §4 read literally gave groups the API mostly refused (844 of 1,353); the web's rules also leave out a series chain that leads nowhere at one end and a group with an active PRV or PSV inside, and then every suggestion over the corpus (142, the default group of 379 pumps viewed) is a station.
  - **Duty check** words from the response's values in display units, the server's SI sentence under Details; notes on which flow each line is against and on what is dashed were added.
  - **Review fixes** (each reproduced first, each with a test that fails on the old code where it can): suggestions and the default group from the case shown as solved (`store.caseInputs`), so a scenario that sets a PRV or PSV active or not changes them as it changes the API's answer; the ids of ticked pumps reserved, so a new element never takes a deleted member's id; the focus after "Also found" moves to the next group offered, else the chart; a converged case with no duty says so with the response's reason; a duty check without a flow says its point did not converge or was not computed, so whether the curve passes through the Group point is not known (no D13 sentence); the stop note gives the first rise sampled without flow and the rule on the pump's own head (in parallel the rise plus its losses on the way), not "above its shutoff head"; refusals worded by the new codes, never from counts; a different boundaries' side read from the project the refusal belongs to. A second round: names always from the labels project (an element deleted since the solve under its name as solved), topology from the project as solved; the default group's ids reserved too; a curve asked for during a solve is sent only if the solve fails or is cancelled; "tick it too" only for a pump that has a box (a standby closed off by its valves has no results, so it is told to open it to the network); NO_SEPARATING_PORTS names the pumps' own ports as such, never as places; the duty check's tolerance stated as the server's (0.5 % or 10⁻⁶ m³/s in display units) and flows below that floor shown as 0; the duty check's and the data table's reasons for a duty's point that did not converge or was not computed; ASSIGNED_FLOW_INSIDE in the plural.
  - **Export:** "Group curves" is listed as left out only in a file with a case that has two or more pumps with results, so the committed workbook is unchanged.
  - **API requests:** whether reversed members face each other, and two places with no member on a way, are codes of their own since the review (`MEMBERS_OPPOSED`, `NO_WAY_THROUGH`). Not built: ports as data for `NO_SEPARATING_PORTS` places, and `DIFFERENT_BOUNDARIES`' side, which the web derives from the project the response belongs to, naming the places' components.
- **Reference cases** (`tests/reference/test_pump_groups.py`, `derivations_pump_groups.py`, by a tester who did not read `services/`; 32 tests, the pump on a loop added after the loop fix): PG1–PG10 as §9.1 lists them, against closed forms and the tester's own solves, with the duty's identities against `/solve` to 10⁻⁹ m; PG2's stop at 32.5125 m and PG4's interstage loss of 5.073699675 m confirmed; PG6 on the tester's own Crane ladder (P3 stops at 28.4334 m, P2 at 38.8795 m, their shutoff heads less the tee offsets); PG9 with every reason, a PSV, and failed-open and failed-closed PRVs accepted; a mixed 2 × 2 station; scenarios equal to the hand-edited project. **PG11 adapted:** no case was found where `dutyCheck.agrees` is false, since the duty's rise starts from the case's own solve, and where v1's rules leave a drooping member no valid state the case's solve does not converge either; the test checks those rises come back not converged, naming the member, and the closed form on either side. The tester found one defect, fixed: the methods' Points item counted the duty's rise and then added it again.
- **Corpus check** (`tests/differential/pump_group_check.py`, a second station finder written from §3.1 by another builder, with liveness: each place leads to a fixed head or the other place, and some pump lies on a way between them): 4,235 groups over the 1,789 corpus projects with two or more pumps, 537 stations, **0 violations** after the two fixes above (TSD §10.4 has the counts). The proposal's "every web suggestion is accepted by the finder" does not hold for the suggestion rules of §4 read literally: of 1,353 suggested groups, 844 are refused (523 for an active PRV or PSV inside, 284 reversed members): the web's suggestion therefore offers only what it can check without the API, and the card shows the API's reason when it refuses.
- **Known limit: a bypass hides reversed members.** Where a bypass inside joins S's side and D's, no way through the parts passes a member, so the members' directions are not read and pumps piped against each other are not refused; S is the port the duty's flow enters, and the station is mixed (found by the review; reading each member's direction on the vertex graph, as `_on_a_way` reads whether it lies on a way, would refuse them: Later).
- **Known limits, the same answer under D13.** A point exactly at a member's stop rise with Crane tees can fail to converge on one grid and converge on another (its message names the branches; `componentIds` is empty, as SDD §4.10 allows). Near zero flow a member can read "running" at ±10⁻¹⁴ m³/s, and one at −1.3 × 10⁻¹⁴ m³/s as beyond its data, as `/solve`'s own results do there.

## 15. As built (slice 4b, 2026-10-29)

Slice 4b was built as §7 describes, with these departures:

- **API**
  - **The forced element.** `system_curve.Forced(link_index, suction, discharge, pump_id, words, ids)` is a pump's own link (`pump_forced`, `PUMP_WORDS`) or the station's virtual link (`STATION_WORDS`, its pumps as `ids`). The functions §7 lists take it, and the virtual link enters through `forced_links`, an additive option of `link_states` and `run_outer_loop`. It is a `FIXED_FLOW` link from S to D appended to a copy of a fresh build (`system_network`), every link inside the station held closed (`held_closed`), so the GGA removes the inside and S and D are joined only by the forced flow. A pump's path is the same code with its own link: the corpus comparison shows `/solve` and every pump's `/system-curve` unchanged.
  - **Names.** Where the outer loop names the forced flow among the controls it cannot settle, a point's `componentIds` name the station's pumps (`Forced.ids`), not the virtual link, as a pump's point names the pump (review); the outer loop's own words call it "station PA+PB" (the pumps' ids joined by "+", so a list of controls stays readable).
  - **A closed-off part's report skips the inside.** `_disconnected_report` looked up the closing rule of every closed link around a disconnected part, the links held closed inside the station among them (a tee inside: a `KeyError`); it now skips them, since no rule of theirs can re-open. Found by the first corpus runs.
  - **Flows.** §7's grid ran from 0 to 1.2 × the group curve's largest flow. As built, `flowMin` defaults to min(0, Q_st), so a round-off duty below zero (every member off) is a point (review); `flowMax` to 1.2 × the largest of Q_st and the group curve's flows (on its default or given rises), 1.2 × Q_st with an active PRV or PSV inside (no group curve), and, where none of those is above 10⁻⁶ m³/s (no flow through the station at the duty or on the group curve: every member off, the first build giving a range of 0 to 3 × 10⁻¹⁸ m³/s, or members closed by their rules or running without carrying flow from S to D), 1.2 × the sum over the members of their curves' largest flows × their speeds. The methods section and `EMPTY_FLOW_RANGE`'s message name the rule used (review). Q_st is solved first, warm from the case's solve (`_padded` appends it to the case's flows); the grid then as `/system-curve` solves it.
  - **An active PRV or PSV inside** refuses only `curve: 'group'` (`find_station(..., pressure_controls=False)` for the system curve): everything inside is held closed, so the group system curve does not depend on it.
  - **The system duty check** takes D6's tolerance on the rise (0.5 % or 0.01 m), as the group curve's duty check takes D6's 0.5 % on flows with D16's floor of 10⁻⁶ m³/s. It says why a point at Q_st has no rise. Where it disagrees and the duty's first start alone (`system_curve.first_start`, warm from the case's solve) has no rise, it says the station alone sets the level there and that the rise shown is the state D10's rule finds from another start (review). The corpus check found this in 14 one-pump stations of the `fuzzaf` profile: in each the pump alone carries exactly the net assigned flow (a demand, or in 2 a supply) of a part that the elements closed around it leave with no fixed head (a check valve in 8, a pump its rule closes in 5, a PRV in 1); it is D10's, inherited. The first full corpus run reported them as violations, before the check had a rule for them.
  - **No NPSHa**, as planned; the reason stated is that the station is read at its ports, each pump's NPSHa at the duty being in its own results (review: the first text said the suctions are not solved, which is true only of the group curve's absolute pressures).
  - **`METHOD_VERSION` is left as it is** (1.4.0 when built; 1.6.0 since the project library, D22, and the relief valve, D23, merged first), `schemaVersion` 1.
  - **Merged with the relief valve (D23).** A solve starts an active relief valve closed, a system-curve point open (`initial_controls`, when `forced_flows` is given): closed in the forced flow's only way out, no rule re-opens it. The station's forced element passed `forced_flows=None`, so in the group system curve such a valve started closed and the forced flow starved: a pump behind a relief valve had no steady state at any flow but the duty's, where `/system-curve` has a head at each. `Forced.pumps` gives an empty map for a station, so every solve of the curve is a system-curve solve; a unit test pins a station of one pump behind a relief valve equal to `/system-curve` (it fails on the first form). Main's zero-flow orientation (the solver's continuity tolerance) is in the shared `_case`, so both curves orient a station alike.
- **Web** as §7 (the system orange, gaps, the crossing named only when both duty checks agree, "Read along the curves", the note), with these departures: the group system curve is asked for after the group curve's answer (with a duty, or refused only for an active PRV or PSV inside), not with it, so a refused group costs no solves of the outside; with an active PRV or PSV inside the card says the group curve is not defined there and draws the group system curve with the members' curves; the slider's mark is on screen only, never in the image; a "Group system curve" table lists every point with its rise or its reason in the station's words. Review fixes: the duty's reason worded with each element's kind as solved; the chart's accessible name gives the shares from the group system curve's duty when the group curve is refused for a PRV or PSV inside; "Back to the duty" moves the focus to the slider as it goes; the figure is `aria-busy` while either curve is computed. The export lists group system curves as left out.
- **Reference cases** PGS1–PGS12 (`tests/reference/test_pump_groups.py`, `derivations_pump_groups.py`, 39 tests by a tester who did not read `services/`): the closed forms of §9.2 (parallel with ideal and Crane tees, series, a reservoir as the inlet); Crane tees at three forced splits, read at S and D, equal to the curve to 10⁻⁹ m (with flow-controlled members holding the split, D11); the curve unchanged with a member off, at another speed, on a flow setpoint or behind a check valve; a station of one pump equal to `/system-curve` on the same grid bit for bit, the duty's own point to 10⁻⁹ m; the two curves crossing at the duty; an FCV outside (no rise beyond its limit, and why); an active PRV inside (the group curve refused, the group system curve computed); the default range and its fallback; scenarios equal to the hand-edited project; EPANET 2.2 on the outside alone (rises within D6; the outside's losses within 1.5 × 10⁻³, measured 8.2 × 10⁻⁴ low on one line out and 8.4 × 10⁻⁴ to 1.2 × 10⁻³ low on the branched outside (the most at the lowest flow), from EPANET's g of 32.2 ft/s² and minor-loss constant 0.02517, which on the branched outside also shift the split between its two reservoirs); the errors in order, no 400 quoting a value, a case that does not converge, the methods.
- **§9.2's consistency items, as measured** (`tests/differential/pump_group_check.py` (t1)–(t4), TSD §10.4 has the counts):
  - *A one-member station gives `/system-curve` within 10⁻¹² m on every corpus pump*: of the 6,154 corpus pumps, 140 are refused alone (dead ends, `NO_SEPARATING_PORTS`) and 1,471 have no duty, so no curve (case not converged 613, S or D closed off 844, floating 14); the other 4,543 equal `/system-curve` bit for bit at every grid flow except the one the duty stands for (49,340 points: rises, reasons, every reason field, and the messages in the station's words). The duty's own point is solved warm from the case's solve, `/system-curve`'s cold in flow order, so at the 633 grid flows it stands for they agree within D6 or reach another state under D13 (equal 396, within D6 226, another state 11).
  - *The virtual link agrees with the forced-split construction*: in the reference cases (PGS2), not over the corpus: the construction needs flow-controlled members, which change the case.
  - *The group curve and the group system curve cross at the duty for every station*: the system duty check agrees on 553 of 800 curves with a duty; each disagreement is explained and listed: zero station flow (149: the rest has more than one state there, a side held closed hanging on elements closed or open at zero flow, D9, D13), no rise at Q_st and why (97), a control in series at its switch (1).
  - *Invariance*: 1,282 curves compared with every member off and at another speed, 10,920 points, identical.
  - *Timings*: a group system curve of 9 flows and the duty took 94 ms median, 1.23 s at most, inside the 45 s budget.
  - *Corpus comparison*: against `b407676`, 5,168 identical, 0 different, no ignores (`/solve` and every pump's `/system-curve`); after merging D22 and D23, against `83da77e`, 5,189 identical, no ignores, and the corpus check again 0 violations (TSD §10.4).
- **Adversarial review** (five reviewers, each finding judged by two skeptics): 13 findings confirmed, 1 split, 2 rejected; the fixes are marked "review" above, each with a test. The corpus check, run again after them, gave 0 violations.
- **Known limits, the same answer under D13.** Where the rest has several steady states at a flow, the curve shows the one D10's starts find (the duty's first from the case's solve), and the system duty check says when that is not the case's. Near zero station flow a point can be another zero-flow state than the case's.

## 16. As built (slice 4c, 2026-11-03)

Slice 4c was built as §8 describes, with these departures:

1. **Five sheets, not one.** D17 writes one value per cell and keeps child tables apart (Pipes, Fittings, Branch ports and Boundary ports; Pump curves and System curves are separate sheets too), and a group has five kinds of row. So the group data is in five sheets, right after System curves and before Valves: Pump groups (one row per group per case: the station, its duty, both duty checks and each curve's state), Pump group members (each pump at the duty), Group curves (each point of the group curve), Group curve members (each pump at each point) and Group system curves (each point of the group system curve). Each is dropped when it has no rows.
2. **No inlet EGL.** `duty.inletEgl` is the level the group curve holds S at; where the station lies in a part of the network that no reservoir or reference node reaches it is arbitrary (`models/pump_groups.py`), and the screen never shows it. It is not written; About says so, and that the Nodes sheet gives the EGL at S where it is determined.
3. **The group id** is the pumps' ids in component order joined by +, `PA+PB`, as the server's messages name a station ("station PA+PB"); a group with no response takes the key's ids in the case's component order. Groups are per case: with scenarios each case's rows are its own, and each left-out line names its case.
4. **Share as reported, in every arrangement** (flow ÷ station flow in parallel, head ÷ the sum of the heads in series, empty for a mixed station or a parallel duty without flow); the column labels are the card's, `Lost on its way` and `Lost in the piping between the pumps`. The export computes none of them.
5. **Words** come from the card's helpers: `dutyCheckState`, `systemDutyCheckState`, `groupSampleRows` and `groupSystemRows` (each point's reason), `refusalWords`, `stationPortWords`, `ARRANGEMENT_WORDS`; the duty's members' states from `pumpStatusLabel`, as the Pumps sheet (a member with no result: `MEMBER_STATUS_WORDS`, now exported); the curve members' control states from `PUMP_CONTROL_STATE_LABELS`, the Pumps sheet's `Control state` words, not the card's data table's, so one column name has one vocabulary in the file.
6. **The Group system curves sheet's reason data**: the limit and passed flows, the open-valve rise and its bound, the starts tried, the component and assigned-flow node ids, one value per cell (D10: the reason as data). The pumps' System curves sheet does not write them and is unchanged; adding them there is a separate change (`docs/roadmap.md` §2).
7. **States.** A group refused only for an active PRV or PSV inside is a row from its group system curve (the same station and duty), its Group curve cell "Not defined: …" with the card's words; a group with no duty is a row with the server's reason (`No duty (as reported, SI)`) and no point rows. Every other group without a ready curve is a left-out line per case with its state (being computed, failed, cancelled, not a station, not computed); a case with two or more pumps and no group computed gets one line saying where to compute them. The single "Group curves and group system curves" line of 4a and 4b is gone, and About's case blocks gain "Pump groups included" wherever the card could show a group (every case with values and two or more pumps with results, with or without the group sheets; None when no group of the case is in the file). About's other group rows and the Methods' group sections are only in a file that has the group sheets, so only a file in which no case with values has two or more pumps with results is byte-identical to 4b's.
8. **Methods.** Each group response's methods section follows its case's methods text in the Methods sheet and `methods.txt`, after a blank line and "Pumps together: PA+PB, group curve" (or "group system curve"), in `methodsText`'s layout (`groupMethodsLines`). The card's two headings now come from `groupMethodsHeading`, so the words the web adds have one source.
9. **The file-name cap is 144, not 147.** The new sheets' CSV files are 23 characters (`group-curve-members.csv`, `group-system-curves.csv`), longer than `scenario-changes.csv` (20), which set the cap in `export.md` §12 item 31. By the same sum, with the 26-character Downloads folder, Windows' Extract All path stays at 215 characters, 3 inside Excel's 218, only with names of at most 144 characters (26 + 1 + 140 + 1 + 23 + 1 + 23). `MAX_NAME_LENGTH` is 144, and `filename.test.ts` checks the longest file and the path as before. Only names longer than 144 characters, a 60-character project with a long case name, are cut sooner. (Shorter file names for the new sheets were the other way; the design's names were kept, as the sheets' titles.)
10. **Proof.** A second committed workbook, `export-pump-groups.xlsx` with `export-pump-groups.expected.json`, written by `fixture.test.ts` from the export fixture's `pump-groups` case (All cases, SI base units, the link on) and read by a new verifier module, `tests/unit/test_web_export_groups_fixture.py`, since the first workbook's verifier is bound to a project without pumps; the first workbook is byte-identical. The verifier finds every number cell equal to the stored group responses bit for bit; the ids, reason codes, server messages, booleans, the arrangement and the curve-state cells exactly; and the app's words as non-empty text, which `utils/export/pump-groups.test.ts` checks word for word against the card's helpers. The expected JSON gives a −0 cell as 0, as the writer writes it (`numberText`; the first workbook had none, an ideal tee's path loss here). The ordering and no-flow-point tests use cloned, relabelled real responses, labelled synthetic, since no real response has a group-curve point without a flow (§14, PG11); the ordering test lists the ladder's pumps P3, P2, P1, so the rule (the place of a group's first member in the case, then the id) and a sort by id or by key give different orders. The branch K test over the fixture's cases now says that the `pump-groups` case's tees are all ideal (K 0, no velocity, no loss) instead of finding no K to check.
11. **Measured.** Bundle, measured as TSD §8.3's *Bundle* paragraph does, both trees built with the same commit string: the export chunk 26,177 → 28,939 B gzip -9 (+2.8 KB: the five sheets, About's group rows and the Methods' group sections); the initial `/p` download 367,844 → 365,656 B (−2.2 KB; 1,272,788 → 1,273,333 B before compression, +545 B). `pump-group-chart.ts`, now imported by the lazy export chunk too, moved from the `/p` page node into a preloaded shared chunk, which compresses it better; nothing new loads first. `third-party-licenses.txt` is byte-identical. Tests: `utils/export/pump-groups.test.ts` 38 (13 on the export fixture's `pump-groups` case in each of SI and display units, 9 on the pump-group fixture's cases, 1 on a one-pump case, 2 synthetic); `test_web_export_groups_fixture.py` 26; the `pump-groups` and `export` e2e specs 29 passed and 1 skipped by design on desktop and phone; the full suites' counts in [`verified-state.md`](../verified-state.md) (nothing under `apps/api/src` changed, so no corpus comparison or corpus check was run).

## 17. As built (slice 4d, 2026-11-03)

Slice 4d was built on branch `web/pump-groups-one-off` from `main` `7fcbdb8`, from a design reviewed by three critics (engineering, UX, build) and revised once; the departures of that design from §8 and of the build from that design are recorded here. Nothing under `apps/api/src` changes: `METHOD_VERSION` stays 1.6.0, `schemaVersion` 1, and the corpus comparison, fuzz profiles and corpus checks were not run (no solved value, curve or check can change).

**Measured before the build** (probes through `TestClient` at `7fcbdb8`):
- Every one-pump-off duty is a point of the base's group system curve: the base's curve asked on a grid holding that case's Q_st (`flowMin` 0, `flowMax` 4 Q_st, 5 points) gives the case's ΔH_st to between 0 and 2.3 × 10⁻¹⁰ relative on `parallel-ideal`, `parallel-crane`, the ladder, `dead-headed` and a twin-speed variant.
- The 41-point default curve's chord at that flow is off by at most 0.027 % (21.0277 m against 21.0220 m, `parallel-ideal` with PA off).
- An outside change moves the duty off the curve: the delivery tank 5 m higher puts its duty 5.000 m off the base's curve.
- Both pumps off gives a zero-flow duty: (2.4 × 10⁻¹⁸ m³/s, 19.0 m) on `parallel-ideal` and (−5.9 × 10⁻¹⁸ m³/s, 19.0 m) on the `one-off` fixture project.
- The base's Q_st (0.05515 m³/s) lies beyond "Pump PA off"'s own group system curve, which ends at 0.05226 m³/s.
- An idle member's case repeats the base: with PB off, `parallel-ideal`'s duty (0.04075241500465534 m³/s, 23.684028469683472 m) is bit for bit `dead-headed`'s base duty, where PB is on but held at zero flow.
- The station (inlet, outlet, arrangement, interior) is the same in every one-pump-off case.

**Departures from §8:**
1. **Offered only while the base case is shown and its results are current.** §8 fixes the single base-relative override but not the case shown; in a scenario the block says how to make that scenario's N−1 by hand (duplicate it in Scenarios, set the pump off there). In series it says a stopped pump blocks the line; in a mixed station, that it is not all in parallel.
2. **A running member** is `status === 'running'` in the base's current solve. A member on but held at zero flow gets no case (with it off the base's state is the same) and the block says why; two members switched on are needed.
3. **The duty claim compares the networks each case solved**, not the overrides: a ring is called a point of the group system curve shown only when that case as solved (`store.caseInputs`) has the same `hydraulicFingerprint` as the case shown's without what changes no value outside the station (`restOf`: the station's interior, D21, since the curve depends on nothing inside; the design checks, D19; and the library entries no element outside refers to, D22), its station flow is above zero, the curve has a rise at the computed flows on both sides of it, and the shown case's system duty check agrees (D13). So an out-of-date case whose outside changed since, or an outside change, withholds it; an outside override equal to the base, one not applied, a design-check limit or a members' library curve edited since does not; it holds for whichever case is shown, and its "No" says the two rests differ, never that the ring's case changed one; a ring is never called a crossing.
4. **The other cases' duties come from one group-curve request per case**, on request ("Also show the other cases' station duties", which the add ticks), one at a time after the case shown's curves, at most six other cases on the chart ("Cases on this chart"), the cases with one pump off first. §8 had hollow markers and no cap: as built each is a numbered slate ring with a transparent fill, drawn on top (`order: -1`, `library-facts.md`), duties within the duty checks' tolerances sharing one, drawn only when its station is the one shown. While the box is off, the notes and the image's footer give one line with the count of other cases with values ("Other cases' station duties are not on the chart: tick … to compute them (n other cases with results)"), the data table lists none, and Running combinations keeps each case's own words: a project whose scenarios have nothing to do with pumps would otherwise list every case, "not computed", on every card and image.
5. **Running combinations lists every case** (the shown first), with Compare's words for a case without values, in long format: a row group per case and a row per member (state; speed whenever a member that is on runs at a speed other than 1 or under a speed control in some case with values, as the group table shows it, an off pump's never; flow, head, shaft power, NPSH margin, curve data, flags; design checks when a member has one), physically invalid values marked as Compare marks them, a list on phones where a long name wraps. §8 had one row per case with a response.
6. **The extremes** count current results only, name their case ("and k other cases" on equal doubles), carry "beyond its curve data" and "physically invalid", and say over how many cases each has a value.
7. **The card asks again for its curves** a solve, Solve all or goal seek cancelled. In 4a and 4b such a curve waited for "Compute the group curve"; the pump chart's own system curves keep that behaviour (roadmap).
8. **Nothing new in the export (D17):** the cases are scenarios it already carries (Compare cases, Scenario changes, every element table per case), and each other case's group curve the card computed is in slice 4c's sheets as that case's group (§16; another case's group system curve is asked only where its group curve is refused for an active PRV or PSV inside, so it otherwise reads not computed); the rings reach the group chart's image; Running combinations and its extremes stay on screen.

**Departures of the build from its design:**
- **Asked again whenever no calculation runs**, not only on the moment one ends: while the card is open, any curve it wants that stands cancelled by a solve, Solve all or goal seek is asked again with `retry`, so one cancelled while the card was closed is asked for when it opens. The other cases' curves are asked again only after the case shown's have answered, as their first requests are; asked at once, they went ahead of the shown case's group system curve in the one queue.
- **No `othersUnticked` prop:** each case's `onChart` says whether its box is ticked; a box that would pass six is `aria-disabled` with the hint, whichever way it came to be unticked, and a case past the six reads as unticked.
- **`groupSummary` takes no sixth parameter:** each ring carries its cases (`OtherRing.cases`: number, name, flow and rise in display units, claim words), which the accessible name, the notes and the data table read. A drawn case's words are its claim's (`DUTY_CLAIM_WORDS`); the rule's sentence `DUTY_CLAIM_RULE` lives in `pump-group-chart.ts` and `pump-group-one-off.ts` re-exports it, so the two modules import no values from each other in a cycle.
- `withOnePumpOffCases(project, pumps)` takes each case's name as the plan gives it (`offName` applied once); `CombinationsInput.cases` gains `ring` for a group's "· ring n"; a shown case with no duty has "No duty: …" as its second line; an other case asked in the same turn reads "being computed", and one not asked yet while a calculation runs says what it waits for (the check of the review fixes below).
- The extremes' "physically invalid" is in the value's words, with an `aria-hidden` alert icon (no `sr-only` copy: the words already say it). The Add's refusal is described by its visible hint line.
- The block's Solve all and the Scenarios menu's take their reason from one function (`goal-seek.ts` `solveAllReason`, after the review: the block had worded a single solve as "A solve is running", the menu "A solve of {case} is running"); the workspace test (`PumpGroupOneOff.svelte.test.ts`), which has the store CaseMenu reads, compares the two descriptions with an error, every case current, a solve of another case in flight and a run. Two 4a workspace tests that took every checkbox of the card now take the members' fieldset ("Pumps in the group"), since with scenarios the card has one more box; their assertions are unchanged.
- The shared fixture grew from 2.04 MB to 3.44 MB (the two cases' scenario answers).

**Review fixes** (an adversarial review of the build; each reproduced first, the numbers below from its probes through `TestClient`, each fix with a test that fails on the old code):
- **The frame of a ring** said that with a pump off a ring lies "below their curves by their losses on the way" and is not on this case's group curve. That holds with one pump running only: with one of three or more off, two or more run, and the ring lies at their summed flow, beyond each one's own (the ladder with P2 off: 0.07825 m³/s against P1's own 0.05612 m³/s and P3's 0.02213 m³/s); and a ring whose case changes only the outside lies on this case's group curve (the delivery tank 5 m higher: 8.9 × 10⁻¹⁶ relative). The note now says a ring is the station's point, drawn against the station's flow (in parallel the sum of the flows of the pumps running in that case, its rise each one's head less its loss on the way; in series the flow through every pump), on its own case's group curve where that case has one and the station has one state at its rise (D13), which is the curve drawn when its case differs only outside the station (without a group curve drawn, as the check below words it). A test words it on the ladder's three pumps, with the API's flows summed.
- **The shared rest** kept the design checks and the whole library, so a base whose NPSH limit or members' curve was edited since told an out-of-date one-pump-off case "it changes the rest of the network" although its duty lay on the curve shown to 0.0 m; `restOf` now leaves out what changes no value outside (decision 3 above).
- **The "No" words** blamed the ring's case ("it changes the rest of the network") even when the case shown was the one that changed it; they now say the rest differs from this case's.
- **Speed in Running combinations** showed only for a speed-controlled member, so the fixture's Pump PB at a fixed 0.85 had none; it now follows decision 5.
- **Names need not be unique:** two members of one name made two scenarios of one name, and the block's notes and the extremes, keyed by their words, threw Svelte's `each_key_duplicate` and the card was lost. The keys are now ids or indexes, and words that name a member alone add its id where another member has its name ("Booster pump (PA) off", "Booster pump (PA), largest flow"; after the check below, Running combinations' row headers too, "Booster pump (PA)").
- **A long pump name** kept Running combinations' row header on one line on a phone, so the list scrolled sideways; it wraps.
- **Solve all's words** while a single solve runs name its case, as the menu's do (the build departure above).
- **The order of the requests.** The other cases' first requests were made while a calculation ran, and a shown curve the calculation had cancelled counted as answered, so each case a Solve all solved had its group curve queued ahead of the shown case's own curves: after Add during the base's group system curve, the calls were the base's two, then S1's and S2's group curves, then the base's group system curve again; with S3 shown after an edit of the base, the calls after the run were the base's, S1's and S2's group curves, then S3's two. They now wait until no calculation runs and the shown case's curves have answered, so the case shown's go first: when a calculation ends, the effect that asks again for the curves it cancelled runs first in the same flush and turns them to loading before the first requests are made. The Pumps view's `settled()` also counts a curve a calculation cancelled as still to answer; for the order that is only defensive, and no test pins it there (the check below). After another case is shown, the other cases' requests still waiting their turn are withdrawn (the one in flight goes on), so its curves go next and the withdrawn ones after them; before, its group system curve waited behind every other case queued before the switch. The Pumps view does this also when it is drawn anew, as after a case switch made on another view (the views visited are kept per solve).
- **A change of members** cancelled the other cases' requests as the user's Cancel does, so going back to the same members left every case that was computing "cancelled: you cancelled it" with "Compute them again", and asked nothing, while the box was still ticked. A change of members and a case switch now withdraw requests rather than cancel them: `cancelGroupCurve(ids, {caseId, forget, waiting})` aborts the request and drops the curve's entry, so it reads as never asked and the first requests' rule asks it again after the shown case's curves. A new cancelled reason with its own words was considered and not taken: it would have needed words in the shown case's notes and the other cases' states, and a cancelled case would have left the progress line while it waited to be asked again. A failure, a refusal and the user's cancel are still never asked again without "Compute them again" (a workspace test across a Solve all).
- **The API test's client addresses** were the project library reference tests' (10.77.0.0/16), and the rate limit counts by address in one table per process, so the two modules run together failed 15 of the API test's 17 with `RATE_LIMITED`. It now sends from 10.76.0.0/16, and `tests/unit/test_client_addresses.py` reads every `TestClient` address under `apps/api/tests` and fails when two modules' addresses can share a key; it found eight other sets of modules sharing addresses (among them the goal-seek corpus check, whose `10.{pid}` range, run by its smoke test inside the suite, covered every reference module's), and ten modules moved to addresses of their own.
- **Two checks that checked nothing.** The cap of six was asserted on `chartPriority(…).slice(0, 6)`, true whatever the card did; the cap and the unticked cases are now `chartKeys` in `pump-group-one-off.ts`, which the Pumps view calls, and its unit test fails without either. The e2e said the block's Solve all kept the focus after its run and did not check it; it does now, as does a workspace test with the real store, which fails when the button is drawn anew during the run.
- With the fixes, a designers' web default changed (D14): while "Also show the other cases' station duties" is off, one line for the other cases instead of a list (decision 4).

**A check of the review fixes** (an independent check of the fixes above; each fix with a test that fails before it where it is behaviour):
- **The frame without a group curve.** The ring's frame said a ring is drawn "as the group curve is" and lies on "the curve drawn here" also where there is none: with an active PRV or PSV inside, the group curve is refused, the station and its duty come from the group system answer and rings are still drawn; and a ring whose own case has a PRV its scenario made active has no group curve of its own. Without a group curve drawn, the frame is now said against the group system curve (or the Group point); with an active PRV or PSV inside it says the station has no group curve and each ring is its case's duty from its group system curve where one is active in that case too, else from its group curve; the general sentence says "where that case has one". Exact words on the fixture's `prv-inside` case and on a curve with no point with a flow (`pump-group-others.test.ts`).
- **Waiting during a calculation.** Since the first requests wait while a calculation runs, a case not asked yet during a Solve all read "being computed" whenever the shown case's curves had answered, and the live region said "Computing the other cases' station duties: k of n…" for the whole run with no request made. A case not asked yet now says what it waits for: "waits for Solve all to end" (the solve, the goal seek), with ", then for this case's curves" while a curve of the case shown is still to answer, and "waits for this case's curves" with no calculation; while a calculation runs no progress line and no Cancel are given for the other cases, and "Compute them again" pressed then gives the focus to the figure. A workspace test holds a run twice, once with the shown case's group system curve cancelled by it and once with its curves answered (`PumpGroupOneOff.svelte.test.ts`); the words in every state (`pump-group-one-off.test.ts`); the focus (`PumpGroupChart.svelte.test.ts`).
- **`settled()`.** That the Pumps view counts a curve a calculation cancelled as still to answer was given as what keeps the order of the requests, but no test failed without it: when a calculation ends, the effect that asks again runs first and turns such a curve to loading before the first requests' effect reads it. For the order it is defensive, as its comment now says; with the waiting words it decides whether a case not asked yet waits "then for this case's curves", which the workspace test above pins.
- **The client-address guard's scope.** TSD §10.2 said no two modules share a rate-limit bucket; the modules that build a `TestClient` with no address all send as `testclient`, which `client_key` counts as `unknown`, one bucket, and the guard does not check them. TSD now says so.
- **"Compute them again" during a calculation.** With the progress line hidden while a calculation runs, "Compute them again" could be pressed during a Solve all; the store sends no curve request until the run ends, yet the cases it asked read "being computed" with no Cancel. It is now unavailable while a calculation runs (`aria-disabled`, with the calculation's words, `calculatingReason`), and a request still waiting then reads "waits for Solve all to end" (or the solve, or the goal seek). Pinned by a workspace test (it presses the button during a held run: nothing is asked, nothing says computed; after the run it asks) and the state words' unit test; both fail before the change.
- **Running combinations' row headers** kept plain names while the slot's symbol is hidden from screen readers, so two members of one name gave two rows the same header; they now take `memberLabels` ("Booster pump (PA)" only where a name is shared), asserted in the extremes' unit test and in the workspace test of two members of one name.

**Proof** (the web's tests, and the API test of the design, written after this build by a tester who read neither `services/` nor the web code):
- **Fixture** (`apps/api/tests/fixtures/pump_groups_input.py`): sixteen cases. `one-off` is `parallel-ideal` on water at 20 °C with an efficiency curve, a 15 kW motor (illustrative manufacturer data) and two design checks, its scenarios S1 "Pump PA off" and S2 "Pump PB off" exactly as the action makes them, S3 "Delivery tank 5 m higher" and S4 "Both pumps off", each with its solve and both curves (`scenarioCases`); `one-off-dead-headed` is `dead-headed` with S1. The generator asserts every scenario's station equal to the base's, PA beyond its curve data and flagged with PB off, S4 at zero station flow, the base's design checks, and PB held in the dead-headed base and running in its S1.
- **API test** (`tests/unit/test_pump_groups_one_off.py`, 17 tests through `TestClient`, metamorphic: both sides of each comparison are the API's answers, and no expected number is typed but two closed forms, the 5 m tank raise and the static rise H_R2 − H_R1; design §6.2): on `parallel-ideal`, `parallel-crane`, the ladder, `dead-headed` and `one-off`, each one-pump-off case made as the action makes it has the base's station and a duty with flow, which the base's group system curve, asked on a grid holding that flow, gives within D6, as does each one-pump-off case's own curve for the base's duty and the other one-pump-off duties (the largest difference 2.27 × 10⁻¹⁰ relative, measured at `c5abb74`); on the base's default flows each such duty lies in range with a rise on both sides and the chord there within D6 (at most 0.027 %), and the shown case's system duty check agrees; with a PRV inside, each case's group curve is refused for that reason alone and its duty from the group system answer lies on the base's curve (1.0 × 10⁻¹³ relative); the station the same in every scenario of `one-off`, in the group and the system answers; S3 off the base's curve beyond D6 and 5 m above it within D6, and on its own curve; S4 below 10⁻⁶ m³/s, every member off with no share, at the static rise; `dead-headed` with the idle PB off the base's answer within D6 at every node, link, pump, boundary and branch and in its duty (D13), where PA off is not; S1 and S2 as the action makes them equal to the hand-edited project bit for bit, `/solve` apart from `scenario`, the timestamp, `computeTime` and D15's trace additions (the Scenario methods section, the changed pump's note), `/pump-group-curve` (group and system) apart from `scenario`. With it, `tests/unit/test_client_addresses.py` (12 tests; review fixes above).
- **Unit tests:** `utils/pump-group-one-off.test.ts` (27; 32 after the review): the gates in order with every sentence, the cases made equal to the fixture's (the scenarios the API solved), ids on the growing project, existing cases skipped, an idle member, the refusal past 20, a long name, two members of one name told apart; `sharedRest` on real `applyScenario` inputs (true for S1, S2 and S4 against the base, an interior speed or pipe spec, a level set to its base value, a design-check limit and a members' curve or an interior pipe spec or resistance entry edited since; false for S3, a fluid temperature, an outside pipe edited since, a reservoir taken whole, a pipe spec, resistance entry or pump curve an outside element uses, edited); every claim on the fixture's curves (S1 and S2 on the base's curve, S3 another rest, S4 zero flow, the base's duty beyond S1's curve, a gap, the shown duty off its curve, no curve, the base's ring with S3 shown); the cases on the chart (`chartKeys`: six of seven, those with one pump off first, an unticked case letting the next in); the other cases' states and words (one not asked yet waiting for a solve, Solve all or goal seek, after its check); Running combinations (the shown case's cells, speed among them, equal to the group table's; the speed column for PB at 0.85 and none for two pumps at speed 1 or an off one at 0.85; two members of one name's row headers with their ids, after the check) and the extremes (40.75 L/s for PA with PB off, 15.02 kW over 3 of 5 cases, 6.806 m; keyed by id). `utils/pump-group-others.test.ts` (12; 14 after the review; 15 after its check): the rings, merged at 0.4 % and not at 0.6 % of flow, the legend, the colour, the name, the notes' exact words (the frame also on the ladder's three pumps, in series and mixed, and without a group curve drawn: `prv-inside` and a curve with no flow; one line while the box is off), and the configuration (nothing else changed without rings, labels in slate, rings last in the image's legend). `utils/goal-seek.test.ts`: the shared Solve all reason in every state. `state/group-curves.test.ts` (two, after the review): `forget` aborts and reads as never asked, asked again without `retry`; with `waiting`, a request sent goes on and one waiting its turn is withdrawn, or cancelled by the user without `forget`.
- **Component and workspace tests:** six in `PumpGroupChart.svelte.test.ts` (the block's gates and refusal, the focus to Solve all and its reasons, the cases on the chart at six, progress, Cancel and "Compute them again" with focus (to the figure when it goes with no progress line, after the check), Running combinations' roles and marks, a member's name wrapping on a phone, the extremes, the legend, the name, the data table and none of the other cases with the box off, the image's wait); seven in `PumpGroupOneOff.svelte.test.ts` with a fake solver giving the fixture's answers by scenario id (one undo step, the curve a Solve all cancelled asked again after it, the requests one at a time after the case shown's and cancelled by a members change, the box and a solve, the claims, the block in a scenario, the limit, the Scenarios menu's words), fourteen after the review (two members of one name added and solved; Solve all keeping the focus through its run and after, the same button; the Scenarios menu's words also with a solve of another case and a run in flight; the calls in order after the run that cancelled the base's curve, and after a run that solved the case shown; a members change withdrawing the requests, and going back asking each case again; a case switch with requests waiting, on the Pumps view and from the Summary with the Pumps view shown after; a failure and a user's cancel asked again only by "Compute them again", across a Solve all), fifteen after its check (a run held twice: a case not asked yet waits for it, then for the shown case's curve it cancelled, with no progress line and no Cancel; the same with the shown case's curves answered; and the same-name test checks the row headers), sixteen after a second check ("Compute them again" unavailable while a run holds, saying why, asking nothing until it ends, then asking).
- **e2e** (`tests/pump-groups.e2e.ts`, real API, desktop 1280×800 and phone 390×844): the cases added in one step and solved, Running combinations equal to the intercepted solves in display units, the extremes, both rings with the intercepted duties and the claim in the legend, the chart's name and the data table, the image, no sideways scroll and a list on the phone; offered for pumps in parallel only; axe clean on the card with everything open (3 flows per viewport). After the review, a fourth on the phone: a pump named in 60 characters wraps in Running combinations, with no sideways scroll; and the first flow checks that Solve all keeps the focus after its run.
- **Gates on the branch** (before the API test): API pytest 7,178 passed, ruff, ruff format and mypy clean; `pnpm gen:types` with no diff in `src/lib/api`; svelte-check (815 files), Prettier and ESLint clean; Vitest 1,681 passed (125 files; one earlier full run had a single failure in `PumpsView.svelte.test.ts`'s single-pump image test, whose 1 s wait for the chart chunk ran out under a load average near 7 on 4 CPUs; it passed alone three times and in the next full run); Playwright 219 passed, 15 skipped by design. After the API test and the review's fixes, the gates' numbers are in [`verified-state.md`](../verified-state.md).

## 18. In the Pumps tab's sections (`pumps-results-layout.md` S2, S3 and S4, as built)

The card's parts kept their contents and moved into the sections of [`pumps-results-layout.md`](pumps-results-layout.md) (§5.3, §6.4 items 1 and 2; its §15 items 47 to 85 record the build). Where this text placed them:

- **The order:** the members (§6.2), then four sections: Station, the group table and the station's flow and rise (§6.5), now before the chart; Group chart, the figure (§6.3, §6.4, §6.6); Add cases (D24's block, 4d's place); and Running combinations, with the extremes under its h5. Each is a plain `div` under an h4 with a rule above, but Add cases since S4: a framed panel in place of the rule (below).
- **The group chart:** Show data table and Download image right under the legend (§6.7; before it since S3, below), the data table (§6.5) after the notes and the methods, the figure's last part until S3 put the other cases after it. The figure stays `aria-busy` while a curve is computed, until the Pumps tab's S3.
- **Since S3** (its §15 items 86 to 107): the members a grid, with a line naming the pump the default group was suggested for and two groups found or more behind "Other groups found: {n}"; Station's answer first (the group curve's progress line, the refusal, the station's flow and rise), then the group table, its flags a line under each flagged row (§6.5), a list on phones; the group chart in the pump chart's anatomy: the canvas (now the one `aria-busy`), Read along the curves, the group system curve's progress line and the coverage lines, Show data table and Download image, the legend, the notes with the duty checks first, "How to read this chart" (the axes, the group system curve, each pump's own system curve), the methods, the data table, then the other cases under the h5 "Other cases on the group chart" with their own progress line and the rings' notes cut: what a ring is inside "How to read the rings", one line per ring. The image's footer is unchanged (§6.4). Each request's progress line is a polite live line of its own, never `role=status` (§6.1's request).
- **Since S4** (its §15 items 116 to 135): Add cases is D24's block as a framed, tinted panel, `PumpLineupsBlock`'s own `<section>` with S2's wrapper gone, the card's one part that changes the project. Its h4 is 14 px with the plain tag "Changes the project" beside it, and "Cases to add" is 12 px. Under no gate its details sit in one disclosure, "The plan: …", drawn closed only when every planned case exists, then one row with Add and the one Solve all. Solve all's lasting reason is shown, under gates 4 to 6 too. An Add that ticked "Also show the other cases' station duties" says "Now ticked: …" on screen and in the block's polite line (D24).
- **Closed,** a second line under the card's heading says what opening it shows, and describes the toggle; the heading is 16 px. The toggle is the section nav's "Pumps together" target.
