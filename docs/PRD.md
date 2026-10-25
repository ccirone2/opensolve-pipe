# Product Requirements Document (PRD): OpenSolve Pipe

**Version:** 0.2.0 (Rebuild baseline)
**Date:** October 2026
**Status:** Aligned with the rebuild decisions D1–D6 in `CLAUDE.md`

---

## 1. Executive Summary

### 1.1 Vision Statement

OpenSolve Pipe is a free, browser-based hydraulic design tool that democratizes access to professional-grade pipe network analysis. It combines the approachability needed for students and field technicians with the power and flexibility demanded by process and consulting engineers.

### 1.2 Problem Statement

Current hydraulic design tools suffer from one or more of the following limitations:

- **Cost barriers:** Professional tools (AFT Fathom, Pipe-FLO) require expensive licenses
- **Installation friction:** Desktop software requires IT involvement and machine-specific setup
- **Collaboration gaps:** Sharing designs requires file transfers and compatible software versions
- **Mobile limitations:** Existing tools don't support field calculations on mobile devices
- **Cost estimation:** Accessible, accurate cost estimation tools are not commonly available

### 1.3 Solution

A web application that:

- Runs entirely in the browser with no installation
- Shares any project as a self-contained link, with no account
- Works equally well on desktop and mobile devices
- Offers professional-grade steady-state hydraulic analysis
- Future: version history, collaboration, and cost estimation

### 1.4 Target Users

**Primary user: working engineers** (process, maintenance, consulting). When user needs conflict, theirs win (`docs/GOALS.md` §1).

| User Type             | Needs                                 | Experience Level |
| --------------------- | ------------------------------------- | ---------------- |
| Students              | Learning tool, homework, projects     | Beginner         |
| Field Technicians     | Quick calculations, troubleshooting   | Intermediate     |
| Maintenance Engineers | System verification, modifications    | Intermediate     |
| Process Engineers     | New system design, optimization       | Advanced         |
| Consulting Engineers  | Client deliverables, complex networks | Advanced         |

---

## 2. Scope

### 2.1 In Scope (Product)

- Steady-state hydraulic analysis
- Single-phase, isothermal flow
- Pressurized pipe networks only
- Common liquids (water, glycols, common fuels)

**Network Topologies:**

- Open systems (once-through flow from source to discharge)
- Closed systems (recirculating loops). Like the real system, a closed loop must include a pressurization point, modeled as a reservoir or ideal reference node (e.g., an expansion tank connection).
- Branching networks (flow divides at tees/wyes)
- Looped networks (multiple flow paths between points, no limit on number of loops)
- Any combination of the above

**Driving Forces:**

- Pressure-fed systems (pressurized source, e.g., municipal supply, pressurized tank)
- Gravity-fed systems (elevated reservoir, head tank), with no pump required
- Known loads: a fixed flow withdrawn from or injected into the network at a point (assigned-flow node), e.g. a process user, a coil or a fire-flow demand
- Pumped systems, including:
  - Multiple pumps in parallel
  - Multiple pumps in series
  - Combined configurations

**System States:**

- Active operation (pumps running, valves open)
- Degraded operation (individual pumps off, valves closed)
- Isolation scenarios (sections of network isolated)

These states can be kept as scenarios of one project and compared (§3.8).

Every model needs at least one fixed-pressure boundary (reservoir or ideal reference node). A model without one is reported as a topology error, not solved. An assigned-flow node fixes a flow, not a pressure, so it never counts as that boundary.

### 2.2 Out of Scope (Current Version)

- Transient/water hammer analysis
- Two-phase flow
- Compressible flow (gases)
- Open channel flow
- Heat transfer / temperature changes along network
- Slurry flow

### 2.3 v1 Release Scope

v1 is the core analysis MVP. Everything else in this document is **Later**. The *Release* columns in §3 mark each item.

**In v1:**

- Branching and looped networks
- Reservoirs, ideal reference nodes, assigned-flow nodes, tees, wyes, plugs/caps
- Pipes with inline fittings
- Fixed-speed pumps (running/off), and speed-controlled (VFD) pumps holding a flow setpoint (§3.1.2.1; CLAUDE.md D11, slice 1)
- Isolation valves (gate, ball, butterfly, globe), check and stop-check valves
- PRV, PSV, FCV
- Water, ethylene/propylene glycol solutions, user-defined fluids
- NPSH available and NPSH margin
- Panel navigator, results tables, pump/system curve chart
- Scenario manager: named cases of one project, solved one at a time or all together and compared side by side (§3.8; CLAUDE.md D15)
- Sharing by link (§4.4)

**Later:** VFD pressure and differential-pressure control modes (D11 slices 2-3); HI viscosity correction; pressure relief valves; three-way valves; differential-pressure control valve mode; goal seek (§3.9); non-ideal reference nodes; variable-level tanks; cross and elbow-with-branch fittings; sprinklers, orifices, heat exchangers, strainers, user-defined elements; fuels in the fluid library; auto-generated schematic; CSV/XLSX/image export; form/table entry and CSV pump curve import; design checks; version history and accounts.

### 2.4 Future Features (Planned)

| Feature                            | Priority | Phase |
| ---------------------------------- | -------- | ----- |
| Cost estimation utility            | High     | 2     |
| Scenario manager (§3.8): built in v1 | High   | 2     |
| Goal seek (§3.9)                   | Medium   | 2     |
| Pipe sizing optimization           | Medium   | 2     |
| Global pump database               | Medium   | 2     |
| Pump curve digitization from image | Medium   | 3     |
| Public API                         | Medium   | 3     |
| Color-coded results visualization  | Low      | 3     |
| Code compliance libraries          | Low      | 3     |

---

## 3. Functional Requirements

### 3.1 System Components

Users shall be able to model the following components:

#### 3.1.1 Nodes (Zero-Dimensional Elements)

| Component                  | Configuration Options                                     | Connection Ports                         | Release |
| -------------------------- | --------------------------------------------------------- | ---------------------------------------- | ------- |
| Reservoir                  | Constant level, elevation, port configuration             | 1-n ports (user-defined, each with size) | v1      |
| Tank (variable level)      | Geometry, level limits                                    | 1-n ports (user-defined, each with size) | Later   |
| Reference Node (Ideal)     | Elevation, pressure setpoint                              | 1 port                                   | v1      |
| Reference Node (Non-Ideal) | Elevation, pressure-flow curve, capacity limits           | 1 port                                   | Later   |
| Assigned Flow              | Elevation, flow (demand out of or supply into the network) | 1 port                                  | v1      |
| Branch (Tee)               | Orientation (through/branch flows), port sizes            | 3 ports                                  | v1      |
| Branch (Wye)               | Angle, port sizes                                         | 3 ports                                  | v1      |
| Branch (Cross)             | Port sizes                                                | 4 ports                                  | Later   |
| Branch (Elbow with Branch) | Main angle (90°/45°), branch angle, port sizes            | 3 ports                                  | Later   |
| Sprinkler/Nozzle           | K-factor, discharge coefficient                           | 1 port (inlet)                           | Later   |
| Orifice                    | Diameter, Cd, or Cv                                       | 2 ports                                  | Later   |
| Plug/Cap                   | None (closed end, zero flow boundary)                     | 1 port (no flow)                         | v1      |

**Note:** There is no generic junction node. Branch components provide explicit fitting geometry and flow-dependent K-factors.

#### 3.1.2 Links (One-Dimensional Elements)

| Component                 | Configuration Options                                                              | Release |
| ------------------------- | ---------------------------------------------------------------------------------- | ------- |
| Pipe                      | Material, schedule, diameter, length, roughness                                    | v1      |
| Pump                      | Curve (head vs flow), speed ratio (the maximum speed when speed-controlled), status, speed control holding a flow setpoint (setpoint, minimum speed; CLAUDE.md D11); later: pressure and differential-pressure control modes, viscosity correction | v1      |
| Check Valve               | Cv or K-factor, cracking pressure, status (active/locked-open/locked-closed)       | v1      |
| Stop-Check Valve          | Cv or K-factor, cracking pressure, status (active/locked-open/locked-closed)       | v1      |
| Gate/Ball/Butterfly Valve | Cv, Kv or K-factor at the actual opening (default: Crane full-open K), status (active/isolated); position-dependent K: Later | v1      |
| Globe Valve               | Cv, Kv or K-factor at the actual opening (default: Crane full-open K), status (active/isolated); position-dependent K: Later | v1      |
| Pressure Reducing Valve   | Setpoint, fully open Cv/Kv/K (default: ideal), status (active/failed-open/failed-closed); Cv-vs-position curve: Later | v1      |
| Pressure Sustaining Valve | Setpoint, fully open Cv/Kv/K (default: ideal), status (active/failed-open/failed-closed); Cv-vs-position curve: Later | v1      |
| Flow Control Valve        | Setpoint, fully open Cv/Kv/K (default: ideal), status (active/failed-open/failed-closed); Cv-vs-position curve: Later | v1      |
| Differential Pressure Control Valve | Pressure-drop setpoint across the valve (inlet minus outlet), fully open Cv/Kv/K, status (active/failed-open/failed-closed) | Later   |
| Three-Way Valve           | Mixing or diverting; Cv per path at the actual position (a cited characteristic is needed for position-dependent Cv), status | Later   |
| Pressure Relief Valve     | Setpoint, capacity                                                                 | Later   |
| Heat Exchanger            | Fixed pressure drop, or Cv/K model                                                 | Later   |
| Strainer/Filter           | K-factor (clean and dirty)                                                         | Later   |
| User-Defined Element      | Cv curve or K-factor                                                               | Later   |

##### 3.1.2.1 Pump Operating Modes

Pumps support multiple operating modes to model real-world control strategies:

| Mode                 | Description                                                 | Required Input              | Release |
| -------------------- | ----------------------------------------------------------- | --------------------------- | ------- |
| Fixed Speed          | Pump operates at defined speed ratio (1.0 = full speed)     | Speed ratio (0.0-1.0)       | v1      |
| Off                  | Pump is not running; treated as closed valve or check valve | Status = off                | v1      |
| Variable Speed (VFD) | Speed adjusts to maintain setpoint (the two modes below)    | Control variable + setpoint | Flow: v1 (D11); pressure: Later |
| Controlled Pressure  | VFD maintains constant discharge or differential pressure   | Pressure setpoint           | Later (D11 slices 2-3) |
| Controlled Flow      | VFD maintains constant flow rate through the pump           | Flow setpoint and minimum speed (required, no default); the speed ratio is the maximum speed | v1 (D11, slice 1) |

**Controlled Flow (CLAUDE.md D11; design in `docs/proposals/vfd-pump-modes.md`):** the drive varies the speed between the minimum speed and the pump's speed ratio (its maximum, at most 1.0) to hold the volumetric flow through the pump, suction to discharge. The solved speed is reported. Where the setpoint needs a speed above the maximum, the pump runs as a fixed-speed pump at the maximum and delivers less; where the system drives more than the setpoint even at the minimum speed, it runs at the minimum speed and passes more (it does not stop at low demand). Either way the result says the setpoint is not met (an information flag). Efficiency at reduced speed follows the plain affinity law, η₀(Q/s). A pump curve along which the speed holding a flow would not be unique is rejected with a topology issue; two flow controls in series with equal setpoints, where both could hold that flow, are reported as not converged, since the pressure between them is undetermined (where one cannot, the state is unique and is solved).

**Viscosity Correction (Later):**
For fluids more viscous than water, pump performance is corrected using the Hydraulic Institute method (ANSI/HI 9.6.7). Correction factors are applied to:

- Head (reduced)
- Flow (reduced)
- Efficiency (reduced)
- Power (increased)

Users may disable viscosity correction for pumps already rated for the operating fluid. Until this ships, pump curves are used as entered and the UI states that no viscosity correction is applied.

##### 3.1.2.2 Component Status

**Pump Status:**

| Status           | Behavior                             |
| ---------------- | ------------------------------------ |
| Running          | Normal operation per curve and speed |
| Off (with check) | Zero flow, prevents reverse flow     |

**Valve Status:**

| Status        | Behavior                               |
| ------------- | -------------------------------------- |
| Active        | Normal operation per position/setpoint |
| Failed Open   | Full open position, no control action  |
| Failed Closed | Zero flow, treated as closed           |

#### 3.1.3 Pipe Connections (Between Component Ports)

A **pipe connection** is a collection of pipes and fittings that connects exactly two endpoints (component ports). Each connection has:

- One or more pipe segments (material, diameter, length)
- Zero or more inline fittings (elbows, reducers, inline valves)
- Two endpoints that attach to component ports

| Element                  | Configuration Options                           |
| ------------------------ | ----------------------------------------------- |
| Pipe Segment             | Material, schedule, diameter, length, roughness |
| Elbow (45°, 90°, LR, SR) | Quantity, K or L/D                              |
| Reducer/Expander         | Inlet/outlet sizes, gradual/sudden              |
| Coupling/Union           | K-factor                                        |
| Entrance/Exit            | Type (sharp, rounded, projecting)               |
| Inline Valve             | Type, K-factor or Cv                            |

**Note:** Tees are modeled as Branch components (nodes), not inline fittings, so that flow splitting and combining is modeled accurately.

#### 3.1.4 Connection Architecture

The hydraulic network is modeled as a graph. This port graph is the only project data model:

- **Components** are nodes with one or more **ports**
- **Pipe connections** are edges connecting exactly two ports
- Each port has a **nominal size** that determines the connection diameter

**Port Types:**

| Component Type   | Port Count | Port Naming Convention              |
| ---------------- | ---------- | ----------------------------------- |
| Reservoir/Tank   | 1-n        | port_1, port_2, ... (user-defined)  |
| Reference Node   | 1          | port_1                              |
| Assigned Flow    | 1          | port_1                              |
| Pump             | 2          | suction (inlet), discharge (outlet) |
| Valve            | 2          | inlet, outlet                       |
| Branch (Tee)     | 3          | run_inlet, run_outlet, branch       |
| Branch (Wye)     | 3          | inlet, outlet_1, outlet_2           |
| Branch (Cross)   | 4          | port_1, port_2, port_3, port_4      |
| Three-Way Valve (Later) | 3   | common, port_a, port_b              |
| Orifice          | 2          | inlet, outlet                       |
| Sprinkler        | 1          | inlet                               |
| Plug/Cap         | 1          | port_1 (zero flow boundary)         |

**Reference Node Types:**

1. **Ideal Reference Node**: Maintains constant pressure regardless of flow rate. Acts as an infinite reservoir or ideal pressure source. Useful for:
   - System boundary conditions
   - Representing large municipal supply mains
   - Modeling ideal pressure sources
   - Pressurization point of a closed loop

2. **Non-Ideal Reference Node (Later)**: Pressure varies with flow rate based on a pressure-flow curve. Useful for:
   - Pressure regulators with capacity limits
   - Booster pumps with supply limitations
   - Wells with drawdown curves

**Assigned Flow Node:** Fixes the flow leaving (demand) or entering (supply) the network at its port, regardless of pressure; the pressure there is a result. Useful for:
   - Process users, coils and terminal units with a known design flow
   - Fire-flow and other point demands
   - Injection points with a known flow (e.g. a metered make-up or dosing connection)

An assigned-flow node is not a pressure boundary: a sub-network whose only boundaries are assigned-flow nodes has no unique solution and is a topology error. If closing a valve or stopping a pump cuts an assigned-flow node off from every fixed-pressure boundary, the solve reports the node as disconnected rather than returning a result. (Assigned flows that balance there, such as a supply feeding an equal demand, are still solved, with the pressure level there undetermined and flagged.) A flow control that alone feeds an assigned flow cannot hold another flow: an FCV set above it is fully open and a speed-controlled pump runs at a speed limit (setpoint not met, flagged), while one set to that same flow, or an FCV set below it, has no determined steady state and is reported as not converged, naming both.

### 3.2 Outputs

All pressures are reported as **gauge** pressure unless labeled absolute (see §3.6).

#### 3.2.1 Solved Network State

For each pipe/link element:

- Flow rate
- Velocity
- Head loss
- Reynolds number
- Friction factor

For each node:

- Static pressure
- Dynamic pressure
- Total pressure
- Hydraulic grade line (HGL)
- Energy grade line (EGL)

For each pump:

- Operating point (flow, head)
- Status (running/off)
- Efficiency and power consumption (when an efficiency curve is provided)
- NPSH available
- NPSH margin (when NPSH required is provided)
- Speed: the set speed ratio, or a speed-controlled pump's solved speed or the limit speed it runs at (D11)
- Speed control (when VFD-controlled): mode, setpoint, state (holding the setpoint, at maximum speed, at minimum speed, no flow, off) and whether the setpoint is achieved
- Later: viscosity-corrected performance

For each control valve:

- Status (active/bypassed/failed)
- Actual flow/pressure vs setpoint
- Valve position (% open): Later (needs a Cv-vs-position curve); v1 reports the equivalent K and Cv of the throttling loss
- Whether setpoint is achieved

For each assigned-flow node:

- Assigned flow (as entered)
- Static pressure and HGL at the node (flagged when the absolute pressure is below the fluid's vapor pressure)

#### 3.2.2 Pump Analysis

- System curve (graphical and tabular)
- Pump curve overlay
- Operating point (flow, head)
- NPSH available at pump suction
- NPSH margin (if NPSH required provided)

#### 3.2.3 Export Formats (Later)

- CSV/Excel: All results in tabular format
- Image: Schematic/PFD as PNG or SVG

### 3.3 Data Entry Methods

#### 3.3.1 Panel Navigator (Primary, v1)

A wizard-like interface where users move element by element through the network graph:

- View/edit current element properties
- Define the piping (pipes and fittings) of each connection at the current element
- Navigate to next/previous element along the path being walked
- At a branch (more than one way forward), choose which path to follow; the breadcrumb records the path taken
- Add elements before/after current
- Create branches at current location

#### 3.3.2 Form/Table Entry (Secondary, Later)

Traditional form-based entry for:

- Bulk component entry
- Copy/paste from spreadsheets
- Power users who prefer tabular view

#### 3.3.3 Auto-Generated Schematic (Visualization, Later)

- Read-only process flow diagram
- Simplified custom symbols (not full P&ID)
- Click any element to open its panel for editing
- Software-defined layout (not user-draggable)

### 3.4 Pump Curve Input

| Method           | Description                    | Release |
| ---------------- | ------------------------------ | ------- |
| Manual table     | Enter flow/head pairs directly | v1      |
| Project library  | Save and reuse within project  | v1      |
| CSV/Excel upload | Import from file               | Later   |

Future:

- Global database of common pumps
- Image digitization

### 3.5 Fluid Properties

#### 3.5.1 Built-In Library

- Water (temperature-dependent) — v1
- Ethylene glycol solutions (concentration and temperature) — v1
- Propylene glycol solutions — v1
- Common fuels (diesel, gasoline, jet fuel) — Later

Each built-in fluid cites the source of its property data.

#### 3.5.2 User-Defined Fluids (v1)

Manual entry of:

- Density
- Dynamic or kinematic viscosity
- Vapor pressure (for NPSH calculations)

#### 3.5.3 Temperature Handling

- User specifies operating temperature
- Properties auto-calculated from temperature
- User may override calculated values
- Calculated values displayed for verification

### 3.6 Units and Reference Conditions

- User-selectable unit system (Imperial, SI, or mixed)
- Automatic conversion between unit systems
- Mixed units allowed within same project (e.g., pipe diameter in inches, length in meters)
- Unit preference saved per-project. Changing preferences changes only what is displayed; it never changes the model.
- Pressures are entered and displayed as **gauge**. Absolute values are shown where they matter (NPSH, vapor pressure).
- Each project has a **site elevation**. Atmospheric pressure is calculated from it (standard atmosphere), and the user may override it.
- All elevations are measured from a single project datum.

### 3.7 Calculation Method

- Darcy-Weisbach friction factor (Colebrook equation)
- No Hazen-Williams option (Darcy-Weisbach is more accurate and general)
- One network solver handles every topology (single path, branching, looped) and every supported fluid

### 3.8 Scenarios

A scenario manager keeps several operating or design cases in one project and compares them, instead of the user keeping one URL per case. It serves the degraded-operation and isolation states in §2.1 and US-004. Built in v1 (CLAUDE.md D15; design: `docs/proposals/scenario-manager.md`).

- A project holds the **base case** and up to 20 named **scenarios**. A scenario stores only its changes of base values (up to 30), so editing the base updates every scenario that does not set its own value. A scenario sets each value at most once, so the order of its changes never matters.
- Values a scenario can change: component status, valve resistance and setpoint, pump speed ratio and speed-control setpoint, reservoir level and surface pressure, reference-node pressure, assigned flow, pipe size and material (one change: material, schedule, size and any bore or roughness override together), pipe length, the fluid, and a built-in fluid's temperature. A scenario never adds or removes components, connections, ports or pipes; it keeps scenarios small in the URL and makes every difference from the base a list of values.
- **Editing.** The case being edited is always named, and a scenario is shown in its own colour and words. In a scenario, only the values above can be edited; each changed value is marked "Changed" with the base value and a Reset, and typing the base value back removes the change. Names, the project description and display units are the same in every case. Everything else is shown read-only ("Same in every scenario"), and adding, inserting, deleting or connecting components is done in the base case. Undo and redo cover the base and every scenario, and show the case each change was made in.
- **Base edits.** A scenario's change of a pipe follows that pipe when the base case joins, reverses or splits its connection; removing the pipe removes its changes. A change whose component, connection or pipe was deleted, or whose value no longer exists on it (a flow setpoint on a pump without flow control, a temperature on a custom fluid), is kept, shown as "no longer applies" and ignored when solving.
- **Solving.** Solve one case, or Solve all: the base case and then each scenario whose results are missing or out of date, one after another, with progress and Cancel. Each case keeps its own results, errors and out-of-date state. A scenario's value that is not valid is shown with the change that set it and a Reset to base, and never blocks the base case or another scenario.
- **Comparing.** Compare cases shows chosen results of every case side by side (a table on wide screens, one card per result on phones), with each scenario's difference from the base case, and lets the user choose and order the results. The pump/system curve chart shows the other cases' operating points and pump curves, and their system curves on request.
- Scenarios travel in the shared URL with the rest of the project; the long-link warning (§4.4) applies to the whole encoded project. A link opens on the base case.
- Traceability: every result shows which case produced it and lists the scenario's changes as the server applied them, with any it ignored; the methods summary and every changed element's trace say so.
- Later: the active case in the link, applying a scenario's changes to the base, differences against a case other than the base, and adding or removing components in a scenario.

### 3.9 Goal Seek (Later)

Goal seek finds the input values that make chosen results hit target values, e.g. "what impeller speed gives 3 bar at the far user?" or "what reservoir level delivers 20 L/s?".

- The user picks one or more **variables** (an input from the overridable list in §3.8, with lower and upper bounds) and the same number of **goals** (a result such as a pressure at a port, a flow in a connection, a pump head or an NPSH margin, with a target value).
- Each goal-seek run repeats the full network solve; it never approximates the network.
- Output: the variable values found, each goal's achieved value and residual, and the iteration count. If a target can't be reached within the bounds, report the closest achievable value and flag the goal as not met; never clamp silently.
- The result never changes the model on its own. The user applies the found values to the base or to a scenario.
- Goal seek is a design aid that finds an input. It is separate from control valves and (Later) VFD control, which are devices that act inside a single solve.

---

## 4. Non-Functional Requirements

### 4.1 Usability

- Mobile and desktop equal priority (responsive design)
- Minimalist interface with intuitive navigation
- Results-first presentation: always solve and show results
- Physically invalid or unreliable results are flagged by default: cavitation (NPSHa < NPSHr), flow reversal through a pump, operation outside a correlation's validated range, non-convergence
- No default "nannying" on design practice—user controls design checks (§5)
- Every result is traceable to its inputs, equations, correlations and data sources, and a methods-and-assumptions summary is available for each solved project (GOALS §4.2)

### 4.2 Performance

- Simple systems (< 20 components): < 1 second solve time
- Medium systems (20-100 components): < 5 seconds
- Large systems (100+ components): Progress indicator with cancel option. v1: while a solve runs, the header shows a spinner with "Solving…" and a Cancel button, and while a pump's system curve is computed its chart says so and offers Cancel; the progress shown is that the work is running, not how far it has got (the solve is one request). Cancel aborts the request, the server stops the work, and the results shown before stay, labelled current or out of date as before.

### 4.3 Availability

- Online-only acceptable (no offline requirement)
- Target 99.5% uptime

### 4.4 Sharing and Persistence

**v1:**

- Every project is shareable as a link; the whole project, its scenarios included (§3.8), is encoded in the link
- No account, sign-in, or server-side project storage
- Project data travels only in the link and is never stored or logged by the server
- Undo/redo within a session; earlier states can be kept by keeping their links
- Links remain openable after app updates (older links are upgraded on open)
- The user is warned when a link becomes long enough that some email and chat apps may cut it off

**Later (requires accounts and storage):**

- Short links for large projects
- Saved projects tied to an account
- Git-like versioning: history, branch, merge, checkout

### 4.5 Sharing Behavior

- Shared links are always editable
- Editing a shared project produces a new link (copy-on-write)
- The original link is unchanged and still opens the original state

---

## 5. Design Checks (Optional, Later)

Users may enable checks from a library:

### 5.1 Velocity Checks

- Minimum velocity (sedimentation)
- Maximum velocity (erosion, noise, water hammer risk)
- Configurable by pipe material and application

### 5.2 NPSH Checks

- NPSH margin (NPSH_A - NPSH_R)
- Configurable minimum margin

### 5.3 Code Compliance (Future)

- NFPA 13 (fire sprinkler systems)
- NFPA 20 (fire pumps)
- ASME B31.1 (power piping)
- User-defined check libraries

### 5.4 Check Behavior

- Not active by default
- User toggles individual checks on/off
- "Check Model" button for on-demand validation
- Violations flagged on solve attempt

---

## 6. Success Metrics

| Metric                                | Target                                                                       |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| Time to first solve (new user)        | < 5 minutes                                                                  |
| Mobile usability score                | > 90 (Lighthouse)                                                            |
| Solve accuracy vs reference suite     | Flows, heads, pressures within 0.5% or 0.01 m head (whichever is looser); mass balance closes at every node |
| User retention (return within 7 days) | > 40%                                                                        |

The reference suite combines Crane TP-410 and textbook worked examples, closed-form hand calculations, and EPANET runs for water-only networks (see TSD §10).

---

## 7. Open Questions

1. **Cost estimation scope:** What cost data sources? How granular (component-level, system-level)?

2. **Versioning (Later):** When history and branching arrive, how are merge conflicts presented — visual diff, or auto-merge with conflicts flagged?

3. **Public API (Future):** Authentication method for API keys; usage tiers.

Resolved by the rebuild decisions: URL vs cloud storage threshold (v1 is link-only), REST vs GraphQL (REST).

---

## 8. Appendices

### Appendix A: Competitive Analysis

| Tool               | Strengths              | Weaknesses                |
| ------------------ | ---------------------- | ------------------------- |
| EPANET             | Free, proven solver    | Desktop-only, dated UI    |
| AFT Fathom         | Powerful, professional | Expensive, desktop-only   |
| Pipe-FLO           | Good UI, comprehensive | Expensive, desktop-only   |
| Online calculators | Free, accessible       | Single-pipe only, limited |

### Appendix B: User Stories

**US-001:** As a student, I want to model a simple pump system so I can verify my hand calculations.

**US-002:** As a field technician, I want to quickly check if a proposed pump will work for a retrofit so I can advise on feasibility.

**US-003:** As a consulting engineer, I want to share a system model with my client so they can review and comment without installing software.

**US-004:** As a process engineer, I want to compare different pipe sizes so I can optimize my design for cost and performance.

**US-005 (Later):** As a team lead, I want to see the history of changes to a design so I can understand how it evolved.

---

<!-- End of PRD -->
