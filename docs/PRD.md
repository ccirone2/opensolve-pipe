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
- Equipment such as heat exchangers, coils, strainers and filters, rated by a pressure drop at a flow or by a Cv or Kv (§3.1.2; CLAUDE.md D18)
- Orifice plates (square-edged, concentric, ISO 5167-2): restriction orifices and orifice flow meters, with the permanent pressure loss in the network and a meter's differential pressure at its taps (§3.1.2; CLAUDE.md D20)
- Pressure relief valves (conventional spring-loaded, liquid service): a set pressure difference and a capacity by API 526 letter, API 520 effective area or certified area and coefficient, with API 520's liquid capacity at full lift (§3.1.2; CLAUDE.md D23)
- Water, ethylene/propylene glycol solutions, user-defined fluids
- NPSH available and NPSH margin
- Panel navigator, results tables, pump/system curve chart
- Scenario manager: named cases of one project, solved one at a time or all together and compared side by side (§3.8; CLAUDE.md D15)
- Goal seek: the input values (1 to 4) that bring as many results to their targets, each trial a full solve (§3.9; CLAUDE.md D16)
- Export: a results workbook (.xlsx) or CSV files (.zip) of the case shown or all cases, and the pump chart as a PNG, made in the browser (§3.2.3; CLAUDE.md D17)
- Opt-in design checks: NPSH margin, the pump's operating region with its manufacturer data, and pipe velocity, with cited presets (§5; CLAUDE.md D19)
- Project library: pipe sizes and valve and fitting loss coefficients (K at a stated bore, Cv, Kv) from the user's own sources, each with its source, defined once and used by reference (§3.1.5; CLAUDE.md D22)
- Sharing by link (§4.4)

**Later:** VFD pressure and differential-pressure control modes (D11 slices 2-3); HI viscosity correction; balanced-bellows and pilot relief valves, gas, steam and two-phase relief, and for relief valves pop action and blowdown, a manufacturer's lift curve, API 520's viscosity, back-pressure and rupture-disc corrections and relief design checks; three-way valves; differential-pressure control valve mode; non-ideal reference nodes; variable-level tanks; cross and elbow-with-branch fittings; sprinklers, user-defined elements; other orifice plates (eccentric, quadrant-edge, conical, thick, multi-hole, multi-stage), nozzles and venturis, and for orifice plates a low-Reynolds-number C correlation, choked flow and an incipient-cavitation check, gases, ISO's uncertainty of C, a reverse-flow (bevelled plate) model and a Cv or Kv; other ways to rate equipment (a K on a stated diameter, a head, a mass flow, a pressure-drop curve) and its viscosity correction; for the project library, entries as scenario values and goal-seek variables, a source on one-off user values, equipment ratings from the library, and importing a library from another project; larger cited pipe sizes and other cited materials (each needs a source the owner can check); fuels in the fluid library; auto-generated schematic; SVG and schematic image export; form/table entry and CSV pump curve import; design checks beyond §5's three (code compliance, user-defined libraries); version history and accounts.

### 2.4 Future Features (Planned)

| Feature                            | Priority | Phase |
| ---------------------------------- | -------- | ----- |
| Cost estimation utility            | High     | 2     |
| Scenario manager (§3.8): built in v1 | High   | 2     |
| Goal seek (§3.9): built in v1      | Medium   | 2     |
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
| Plug/Cap                   | None (closed end, zero flow boundary)                     | 1 port (no flow)                         | v1      |

**Note:** There is no generic junction node. Branch components provide explicit fitting geometry and flow-dependent K-factors.

#### 3.1.2 Links (One-Dimensional Elements)

| Component                 | Configuration Options                                                              | Release |
| ------------------------- | ---------------------------------------------------------------------------------- | ------- |
| Pipe                      | Material, schedule, diameter, length, roughness; or a pipe spec of the project library and a length (§3.1.5) | v1      |
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
| Pressure Relief Valve (conventional spring-loaded, liquid service) | Set pressure, a pressure difference, inlet minus outlet static (no default; discharging to atmosphere it is the gauge set, with a return line the bench setting); capacity (no default), one of three kinds never mixed: an API 526 orifice letter or an API 520 effective area, each with API 520's effective coefficient 0.65 and ASME's overpressure (preliminary), or the valve's certified actual area, rated coefficient and full-lift overpressure (default ASME's 10 % or 3 psi, whichever is greater, for sets of at least 15 psi); status active or locked closed. Closed below its set, its lift rising linearly with the overpressure to full lift at set plus overpressure (a convention, flagged: real valves surge open and reclose below set), API 520's liquid capacity at its lift. Discharge to atmosphere is an open discharge the app adds at its free outlet. Flashing at its outlet and a viscous liquid are flagged; a set below 15 psi on ASME's overpressure is refused (CLAUDE.md D23) | v1      |
| Pressure relief valves, other kinds | Balanced-bellows and pilot valves (set on the inlet's gauge pressure), pop action and blowdown, a manufacturer's lift or pressure–flow curve, API 520's Kv, Kw and Kc, non-certified valves, a nameplate rated capacity, gas, steam and two-phase relief, a one-port valve to atmosphere, failed open | Later   |
| Equipment (heat exchanger side, coil, strainer, filter) | Rated pressure drop at a rated flow, with the density of the fluid the rating is for, or a Cv or Kv (a rating on water); loss ∝ ρQ² (constant K). No status, no default rating. Reverse flow and laminar flow in a connected pipe are flagged; viscosity is not corrected (CLAUDE.md D18) | v1      |
| Equipment, other ratings  | K on a stated diameter, a head rating, a mass-flow rating, a ΔP–flow curve, a viscosity correction, a reverse or clean/dirty rating | Later   |
| Orifice plate (square-edged, concentric; a restriction orifice or a flow meter) | Bore; C by ISO 5167-2 (Reader-Harris/Gallagher, the default) or entered (ISO's discharge coefficient at the plate's taps, from a calibration or datasheet, not the flow coefficient α = C/√(1 − β⁴)); optional pressure taps (corner, flange, or D and D/2) for a meter's differential pressure. The loss is ISO 5167-2's permanent pressure loss, with the C at D and D/2 tappings whatever the taps (one loss per plate). No status, no default bore. A plate outside ISO 5167-2's range, below its lowest Reynolds number, in reverse flow or with an outlet pipe of another bore is flagged, flashing at the vena contracta too; one whose C could exceed 1 is refused. A restriction given by a pressure drop at a flow, a Cv or a Kv is Equipment (CLAUDE.md D20) | v1      |
| Orifice plates, other kinds | Eccentric, quadrant-edge, conical, thick, multi-hole and multi-stage plates; nozzles and venturis (ISO 5167-3 and -4); a Cv or Kv on the orifice; a low-Reynolds-number C | Later   |
| User-Defined Element      | Cv curve or K-factor                                                               | Later   |

A valve's Cv, Kv or K is entered on the valve or taken from an entry of the project library (§3.1.5); an equipment item's rating is entered on the item.

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
| Pipe Segment             | Material, schedule, diameter, length, roughness; or a project library pipe spec and a length |
| Elbow (45°, 90°, LR, SR) | Quantity, K or L/D                              |
| Reducer/Expander         | Inlet/outlet sizes, gradual/sudden              |
| Coupling/Union           | K-factor                                        |
| Entrance/Exit            | Type (sharp, rounded, projecting)               |
| Inline Valve             | Type, K-factor or Cv                            |

Every fitting takes its cited K by default; a user K, or a project library entry (a K at its stated bore, a Cv or a Kv), replaces it (§3.1.5).

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
| Equipment        | 2          | inlet, outlet                       |
| Orifice plate    | 2          | inlet, outlet                       |
| Relief valve     | 2          | inlet, outlet                       |
| Branch (Tee)     | 3          | run_inlet, run_outlet, branch       |
| Branch (Wye)     | 3          | inlet, outlet_1, outlet_2           |
| Branch (Cross)   | 4          | port_1, port_2, port_3, port_4      |
| Three-Way Valve (Later) | 3   | common, port_a, port_b              |
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

#### 3.1.5 Project Library

The cited libraries stop where their sources stop: steel pipe at NPS 48 (NPS 36 for schedules 10–40), Crane's butterfly valve table at NPS 24, and no HDPE or ductile iron (CLAUDE.md D8). A design beyond them needs the engineer's own data: a pipe bore from a standard or manufacturer the tool does not carry, a valve's Cv from its datasheet. The project library holds such values once, with where they came from, and every element that needs one refers to it (CLAUDE.md D22; design: `docs/proposals/project-library.md`).

- **Pipe specs.** A name, a source, a material (a library material, whose cited roughness evaluated at the spec's bore applies unless a roughness is entered; or Custom, with its roughness), the inner diameter, and optionally the outer diameter and nominal size (for display and port sizes only). A pipe segment that refers to a spec keeps only its own length.
- **Resistances.** A name, a source and a loss coefficient as the datasheet prints it: a K with the bore it is stated at, a Cv (US gpm of water at 1 psi) or a Kv (m³/h of water at 1 bar). A valve takes an entry as its resistance; an inline fitting takes one in place of its cited K. A K is moved to the bore it is used on, K₀ (D/d₀)⁴, the same head loss at a given flow; a Cv or Kv is converted on that bore as one entered there.
- **References, not copies.** Editing an entry changes every element that uses it. Each list holds up to 100 entries; when one is full, the app says so where a new entry would start, before a form is filled in. An entry in use cannot be deleted, and the app names what uses it. One action uses a spec for one pipe, for every pipe of the same material and size, or for every pipe of a connection.
- **Sources are required.** Every entry states its source (1–300 characters): a standard and its table, a datasheet, a measurement, or that the value is illustrative. Every result that uses an entry names it and its source in its trace, and the methods summary lists the whole library, with any entry no element uses.
- **The same answer.** An element that uses an entry is solved exactly as if the same values were entered on it: the library adds reuse and provenance, not a new calculation. A project without a library is unchanged.
- **Scenarios and goal seek.** A scenario can switch a pipe to or from a spec and point a valve at another entry (§3.8); a goal seek can vary a valve's resistance that comes from an entry, and the value found is the valve's own (§3.9). The entries themselves are the same in every case.
- **Flags stay.** A Crane default outside its table is still flagged, and the flag suggests entering the manufacturer's coefficient, on the element or in the library.
- The library travels in the link with the rest of the project; nothing is stored on the server.
- **Later:** entries as scenario values and goal-seek variables (one change resizing every header that uses a spec), a source on one-off values entered on an element, equipment ratings from the library, and importing a library from another project's link. Larger cited sizes (ASME B36.10M beyond NPS 48) and other cited materials (HDPE, cement-lined ductile iron) each need a source the owner can check; they are not part of the library.

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

For each equipment item:

- Flow, and flow ÷ rated flow (a rated point only)
- Pressure loss (the rating scaled to the solved flow and density) and head loss
- Static pressure drop between its ports (what gauges read; it also holds the ports' elevation and velocity terms)
- The rating used, and flags for reverse flow and for laminar flow in a connected pipe

For each orifice plate:

- Flow, and the permanent pressure loss (ISO 5167-2's, what the plate takes from the line) and head loss
- A flow meter's differential pressure at its taps (none for a plate without taps)
- Static pressure drop between its ports, and the static pressure at the vena contracta (flagged where the liquid would flash)
- β, the inlet pipe's Reynolds number, the discharge coefficient that sets the loss and where it came from, the meter's C and the loss coefficient K, and flags for a plate or flow outside ISO 5167-2's range, reverse flow and an outlet pipe of another bore

For each relief valve:

- State (closed, partial lift, full lift; a valve locked closed reads "Closed (locked)"), flow, and the lift
- Inlet pressure and back pressure (gauge), the pressure difference across it ÷ its set (above 100 % an active valve relieves, and the rise is its overpressure; a valve locked closed stays closed at any ratio), the static pressure drop and the head loss
- Its capacity at full lift for the fluid's density and flow ÷ capacity; the set, the overpressure at full lift and where it came from; the capacity used, and for an effective area the smallest API 526 letter covering it
- Flags for full lift, for partial lift (the linear lift is a convention), for a closed valve with no result, for flashing at its outlet and for a viscous liquid

For each assigned-flow node:

- Assigned flow (as entered)
- Static pressure and HGL at the node (flagged when the absolute pressure is below the fluid's vapor pressure)

#### 3.2.2 Pump Analysis

- System curve (graphical and tabular)
- Pump curve overlay
- Operating point (flow, head)
- NPSH available at pump suction
- NPSH margin (if NPSH required provided)
- Pumps together (CLAUDE.md D21; `docs/proposals/pump-groups.md`): for pumps that run together, in parallel or in series, the station that holds them (between the two places it meets the rest of the network), each pump's own curve and solved point on one chart, how the flow divides (each pump's share, and in parallel what each loses on its way between the headers; in series what the piping between the pumps loses), and the group curve: the station's flow at each rise between its inlet and outlet, solved with every pump on its own curve, so it shows where a weaker pump stops delivering. The group is chosen on the page (suggested from the network), never stored. The catalogue composite curve (flows added at equal head) is not drawn: it does not meet the system at the duty. The group's own system curve (slice 4b): the rise the rest of the network needs between the station's inlet and outlet at each flow through it, the same for any split between the pumps, crossing the group curve at the duty; a slider reads every pump's flow along the group curve. **Later:** the group in the export; one pump off as a case of each running pump

#### 3.2.3 Export Formats

The Results pane exports what the page holds, made in the browser: nothing is sent to the server and nothing is calculated but Compare's differences (CLAUDE.md D17; `docs/proposals/export.md`). Export is unavailable while a calculation request is in flight.

- **Results workbook (.xlsx, the default) or CSV files (.zip)** of the case shown or, in a project with scenarios, all cases:
  - **About** first: how to read the file, the project, the export time, each case's solve time, methods version and server libraries, convergence, the atmosphere and the fluid with their sources, whether the results are out of date, the project link (by default; a checkbox leaves it out), the web app's and the server's source, and the disclaimer;
  - the flags, and every results table with one value per cell at full precision (nodes, links with their pipes and fittings, pumps with their curves and the system curves already computed, valves, equipment with the rating each solve used, orifice plates with the bore each solve used, relief valves with the capacity each solve used, branches and their ports, boundaries and their ports, assigned flows), and, in a project with a library, the project library (each entry with its source and the elements that use it) with the entry each pipe, fitting and valve refers to;
  - the scenario changes as the server applied them, Compare cases (all cases), the goal seek report, the methods text and, for one case, the trace.
  - Every table row carries its case, its solve time and its state (current, out of date, did not converge). A solve that did not converge gives its record (convergence, flags, methods) but no values.
  - One unit system per file: the display units or SI base units (in SI every number is the server's own value).
  - CSV files are RFC 4180, UTF-8, with a point as the decimal mark; the zip's `README.txt` says how to open them under a comma-decimal setting.
- **Pump chart image (PNG):** the chart shown, drawn again at 1600 px wide with a caption naming the pump, the case, the solve and its state, its notes and the disclaimer. None for a solve that did not converge.
- **Later:** SVG; an image of the schematic (when the schematic exists); a single-table CSV; Web Share; the values of a solve that did not converge.

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
- Values a scenario can change: component status, valve resistance and setpoint, pump speed ratio and speed-control setpoint, reservoir level and surface pressure, reference-node pressure, assigned flow, an equipment item's rating (the whole rating, such as another vendor's datasheet as printed or a Cv, or one of its values: the rated pressure drop of a dirty strainer, the rated flow, the rated fluid density, the Cv or Kv), an orifice plate's bore (a second plate) and discharge coefficient (a calibrated plate, or ISO 5167-2's), a relief valve's set pressure and capacity (the whole capacity, such as another letter, or one of its values: the area, the rated coefficient, the certified overpressure or ASME's), pipe size and material (one change: material, schedule, size and any bore or roughness override together, or a project library pipe spec, §3.1.5), pipe length, the fluid, and a built-in fluid's temperature. A valve's resistance may be a project library entry; the library's entries themselves are the same in every case (Later: entries as scenario values). A scenario never adds or removes components, connections, ports or pipes; it keeps scenarios small in the URL and makes every difference from the base a list of values.
- **Editing.** The case being edited is always named, and a scenario is shown in its own colour and words. In a scenario, only the values above can be edited; each changed value is marked "Changed" with the base value and a Reset, and typing the base value back removes the change. Names, the project description and display units are the same in every case. Everything else is shown read-only ("Same in every scenario"), and adding, inserting, deleting or connecting components is done in the base case. Undo and redo cover the base and every scenario, and show the case each change was made in.
- **Base edits.** A scenario's change of a pipe follows that pipe when the base case joins, reverses or splits its connection; removing the pipe removes its changes. A change whose component, connection or pipe was deleted, or whose value no longer exists on it (a flow setpoint on a pump without flow control, a temperature on a custom fluid, a rated flow on equipment now rated by a Cv, a rated coefficient on a relief valve now sized by a letter), is kept, shown as "no longer applies" and ignored when solving.
- **Solving.** Solve one case, or Solve all: the base case and then each scenario whose results are missing or out of date, one after another, with progress and Cancel. Each case keeps its own results, errors and out-of-date state. A scenario's value that is not valid is shown with the change that set it and a Reset to base, and never blocks the base case or another scenario.
- **Comparing.** Compare cases shows chosen results of every case side by side (a table on wide screens, one card per result on phones), with each scenario's difference from the base case, and lets the user choose and order the results. The pump/system curve chart shows the other cases' operating points and pump curves, and their system curves on request.
- Scenarios travel in the shared URL with the rest of the project; the long-link warning (§4.4) applies to the whole encoded project. A link opens on the base case.
- Traceability: every result shows which case produced it and lists the scenario's changes as the server applied them, with any it ignored; the methods summary and every changed element's trace say so.
- Later: the active case in the link, applying a scenario's changes to the base, differences against a case other than the base, and adding or removing components in a scenario.

### 3.9 Goal Seek

Goal seek finds the input values that make chosen results hit target values, e.g. "what impeller speed gives 3 bar at the far user?" or "what reservoir level delivers 20 L/s?". Built in v1 (CLAUDE.md D16; design: `docs/proposals/goal-seek.md`).

- **Variables.** The user picks 1 to 4 **variables**, each a number from the list in §3.8, with lower and upper bounds inside the value's own limits: a reservoir's liquid level or surface pressure, a reference node's pressure, an assigned flow, a pump's speed ratio (its maximum speed when speed-controlled) or flow setpoint, a control valve's setpoint, a valve's resistance (one K, Cv or Kv; on a valve that takes its resistance from the project library, the search starts at the entry's value when it is of the same kind, and the value found is the valve's own, in place of the entry), an equipment item's rated pressure drop, rated flow, rated fluid density, or Cv or Kv (the values its kind of rating holds), an orifice plate's bore or discharge coefficient (the bore for a bypass flow or a meter's reading, the C a calibration must show), a relief valve's set pressure, area, rated coefficient or overpressure (the set for a relief flow; sizing: the API 520 effective area that puts the inlet at the relieving pressure, with the API 526 letter that covers it), a pipe's length, or a built-in fluid's temperature. Statuses, pipe sizes, the whole fluid, an equipment item's whole rating and a relief valve's whole capacity or letter are not numbers and are not variables: set them in a scenario and compare cases.
- **Goals.** The user picks as many **goals**: a port's static pressure, a connection's flow, largest velocity or head loss, a pump's flow, head, NPSH available or NPSH margin, a valve's flow or pressure drop, an equipment item's flow, pressure loss or static pressure drop, an orifice plate's flow, permanent pressure loss, differential pressure at its taps (a plate with taps) or static pressure drop, a relief valve's flow or static pressure drop, or a reservoir's or reference node's outflow (the results Compare cases shows, §3.8), each with a target. Each goal has a tolerance: by default 0.5 % of the target, at least 0.01 m of head (pressures converted with the fluid's density), 10⁻⁶ m³/s for flows or 10⁻³ m/s for velocity; the user may enter a tighter or looser one, down to a fixed smallest tolerance per kind of result. A goal is met when its achieved value is within its tolerance of the target.
- **Search.** Each evaluation is a full network solve of the case with the variables at trial values; nothing is approximated. The search starts from the case's own values. With one variable it solves 9 values across the bounds, then Brent's method where the result crosses its target nearest the start; with several, a bounded least-squares search. At most 60 evaluations for one variable and 20 per variable plus 20 for several, inside one request's time budget of 45 s (the best evaluation so far is reported when the budget runs out).
- **Output.** The values found, each goal's achieved value, residual, tolerance and met status, why the search stopped, every evaluation (its values, its goal values, whether it was usable and the element states that changed), notes on what the search found (another crossing, a jump where an element switches state, a crossing where the network has no solution, a value that must be applied exactly), the full results at the values found and a "Goal seek" methods section. If a target can't be reached within the bounds, the closest value found is reported and the goal flagged as not met; it is never clamped silently, and the message says only what the values solved show.
- **Applying.** The result never changes the model on its own. A run on the base case can be applied to the base case or as a new scenario; a run on a scenario to that scenario or as a new scenario (a scenario's values are never applied to the base). Apply writes the exact values found as one undo step and solves the case. A result goes out of date when the case it ran on changes.
- **The case.** Goal seek runs on the case shown, the base or a scenario; the variables are written on top of the scenario's values. While it runs, solving waits; Cancel stops it. The setup and the last result belong to the page, not to the project or the link.
- Goal seek is a design aid that finds an input. It is separate from control valves and VFD control, which are devices that act inside a single solve.
- Later: saving goal-seek setups in the project, a start value or evaluation limit chosen by the user, streamed progress, goals on network extremes, absolute pressure, HGL/EGL, efficiency or power, applying a scenario run's values to the base, a global search for several variables, and more than 4 variables.

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

## 5. Design Checks (Optional)

Design practice, not physics: a check never changes a result or raises a flag (GOALS §4.6). Built in v1 (CLAUDE.md D19; `docs/proposals/design-checks.md`): three checks, each limit the user's value or a cited preset.

### 5.1 Velocity Check

- Every pipe's velocity within a minimum (sedimentation) and/or a maximum (erosion, noise, water hammer risk), one result per connection naming the pipes outside
- The user's values: no preset, since no source read gives limits that suit every fluid and use

### 5.2 NPSH Margin Check

- NPSHa at least NPSHr plus a margin and/or a ratio times NPSHr, the greater applying
- Preset: ANSI/HI 9.6.1-2012 "General" (ratio 1.1 or 1.0 m), as reproduced by a secondary source

### 5.3 Pump Operating Region Check

- The flow as a fraction of the best efficiency flow at the running speed
- Preset: API 610's preferred operating region (70–120 %), as quoted by a secondary source
- With it, the pump curve's optional manufacturer data at rated speed: the allowable operating region, the minimum continuous stable and thermal flows, and the motor's rated power against the shaft power

### 5.4 Check Behavior

- Not active by default; the user turns each check on in Settings, and the limits travel with the project's link
- Results on every solve: not met, met, or not evaluated with the reason, in Results → Checks and a Summary card, each linked to its element
- The pump chart shows the limits (regions, minimum flow, NPSHa required, motor rating); the export has a Design checks sheet

### 5.5 Later

- Code compliance: NFPA 13 (fire sprinkler systems), NFPA 20 (fire pumps), ASME B31.1 (power piping)
- User-defined check libraries, velocity limits by pipe material and application
- Relief valve checks, each once its standard is read: the overpressure at the relieving flow within an allowable value, API 520 Part II's 3 % inlet loss, built-up back pressure within 10 % of set for a conventional valve (CLAUDE.md D23)
- A "Check model" button for on-demand validation

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
