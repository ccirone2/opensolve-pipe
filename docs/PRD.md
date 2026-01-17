# Product Requirements Document (PRD)
# HydraFlow - Web-Based Hydraulic Network Design Tool

**Version:** 0.1.0 (Draft)  
**Date:** January 2026  
**Status:** Skeleton PRD for Development Planning

---

## 1. Executive Summary

### 1.1 Vision Statement

HydraFlow is a free, browser-based hydraulic design tool that democratizes access to professional-grade pipe network analysis. It combines the approachability needed for students and field technicians with the power and flexibility demanded by process and consulting engineers.

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
- Provides Git-like version control via shareable URLs
- Works equally well on desktop and mobile devices
- Offers professional-grade steady-state hydraulic analysis
- Future: Includes accessible cost estimation capabilities

### 1.4 Target Users

| User Type | Needs | Experience Level |
|-----------|-------|------------------|
| Students | Learning tool, homework, projects | Beginner |
| Field Technicians | Quick calculations, troubleshooting | Intermediate |
| Maintenance Engineers | System verification, modifications | Intermediate |
| Process Engineers | New system design, optimization | Advanced |
| Consulting Engineers | Client deliverables, complex networks | Advanced |

---

## 2. Scope

### 2.1 In Scope

- Steady-state hydraulic analysis
- Single-phase, isothermal flow
- Pressurized pipe networks only
- Common liquids (water, glycols, common fuels)
- Branching and looped networks
- Series and parallel pump configurations

### 2.2 Out of Scope (Current Version)

- Transient/water hammer analysis
- Two-phase flow
- Compressible flow (gases)
- Open channel flow
- Heat transfer / temperature changes along network
- Slurry flow

### 2.3 Future Features (Planned)

| Feature | Priority | Phase |
|---------|----------|-------|
| Cost estimation utility | High | 2 |
| Pipe sizing optimization | Medium | 2 |
| Global pump database | Medium | 2 |
| Pump curve digitization from image | Medium | 3 |
| Public API | Medium | 3 |
| Color-coded results visualization | Low | 3 |
| Code compliance libraries | Low | 3 |

---

## 3. Functional Requirements

### 3.1 System Components

Users shall be able to model the following components:

#### 3.1.1 Nodes (Zero-Dimensional Elements)

| Component | Configuration Options |
|-----------|----------------------|
| Reservoir/Tank | Constant or variable level, elevation, geometry |
| Junction | Elevation, demand/supply |
| Sprinkler/Nozzle | K-factor, discharge coefficient |
| Orifice | Diameter, Cd, or Cv |

#### 3.1.2 Links (One-Dimensional Elements)

| Component | Configuration Options |
|-----------|----------------------|
| Pipe | Material, schedule, diameter, length, roughness |
| Pump | Curve (head vs flow), speed, status |
| Check Valve | Cv or K-factor, cracking pressure |
| Stop-Check Valve | Cv or K-factor, cracking pressure |
| Gate/Ball/Butterfly Valve | Cv or K-factor, position (% open) |
| Globe Valve | Cv or K-factor, position |
| Pressure Reducing Valve | Setpoint, Cv curve (detailed) or auto-sized (simplified) |
| Pressure Sustaining Valve | Setpoint, Cv curve or auto-sized |
| Flow Control Valve | Setpoint, Cv curve or auto-sized |
| Pressure Relief Valve | Setpoint, capacity |
| Heat Exchanger | Fixed pressure drop, or Cv/K model |
| Strainer/Filter | K-factor (clean and dirty) |
| User-Defined Element | Cv curve or K-factor |

#### 3.1.3 Piping Elements (Between Components)

| Element | Configuration Options |
|---------|----------------------|
| Elbow (45°, 90°, LR, SR) | Quantity, K or L/D |
| Tee (through, branch) | Quantity, K or L/D |
| Reducer/Expander | Inlet/outlet sizes, gradual/sudden |
| Coupling/Union | K-factor |
| Entrance/Exit | Type (sharp, rounded, projecting) |

### 3.2 Outputs

#### 3.2.1 Solved Network State

For each pipe/link element:

- Flow rate
- Velocity
- Head loss
- Reynolds number

For each node:

- Static pressure
- Dynamic pressure
- Total pressure
- Hydraulic grade line (HGL)
- Energy grade line (EGL)

#### 3.2.2 Pump Analysis

- System curve (graphical and tabular)
- Pump curve overlay
- Operating point (flow, head)
- NPSH available at pump suction
- NPSH margin (if NPSH required provided)

#### 3.2.3 Export Formats

- CSV/Excel: All results in tabular format
- Image: Schematic/PFD as PNG or SVG

### 3.3 Data Entry Methods

#### 3.3.1 Panel Navigator (Primary)

A wizard-like interface where users navigate element-by-element:

- View/edit current element properties
- Define connecting piping (fittings table)
- Navigate to next/previous element
- Add elements before/after current
- Create branches at current location

#### 3.3.2 Form/Table Entry (Secondary)

Traditional form-based entry for:

- Bulk component entry
- Copy/paste from spreadsheets
- Power users who prefer tabular view

#### 3.3.3 Auto-Generated Schematic (Visualization)

- Read-only process flow diagram
- Simplified custom symbols (not full P&ID)
- Click any element to open its panel for editing
- Software-defined layout (not user-draggable)

### 3.4 Pump Curve Input

| Method | Description |
|--------|-------------|
| Manual table | Enter flow/head pairs directly |
| CSV/Excel upload | Import from file |
| Project library | Save and reuse within project |

Future:
- Global database of common pumps
- Image digitization

### 3.5 Fluid Properties

#### 3.5.1 Built-In Library

- Water (temperature-dependent)
- Ethylene glycol solutions (concentration and temperature)
- Propylene glycol solutions
- Common fuels (diesel, gasoline, jet fuel)

#### 3.5.2 User-Defined Fluids

Manual entry of:

- Density
- Dynamic or kinematic viscosity
- Vapor pressure (for NPSH calculations)

#### 3.5.3 Temperature Handling

- User specifies operating temperature
- Properties auto-calculated from temperature
- User may override calculated values
- Calculated values displayed for verification

### 3.6 Units

- User-selectable unit system (Imperial, SI, or mixed)
- Automatic conversion between unit systems
- Mixed units allowed within same project (e.g., pipe diameter in inches, length in meters)
- Unit preference saved per-project

### 3.7 Calculation Method

- Darcy-Weisbach friction factor (Colebrook equation)
- No Hazen-Williams option (Darcy-Weisbach is more accurate and general)

---

## 4. Non-Functional Requirements

### 4.1 Usability

- Mobile and desktop equal priority (responsive design)
- Minimalist interface with intuitive navigation
- Results-first presentation (warnings opt-in)
- No default "nannying"—user controls design checks

### 4.2 Performance

- Simple systems (< 20 components): < 1 second solve time
- Medium systems (20-100 components): < 5 seconds
- Large systems (100+ components): Progress indicator with cancel option

### 4.3 Availability

- Online-only acceptable (no offline requirement)
- Target 99.5% uptime

### 4.4 Collaboration

- All projects shareable via URL
- No account required for basic use
- Account required for persistence and sharing
- Git-like versioning (invisible to user):
  - Branch
  - Merge
  - History
  - Checkout
  - Add
  - Commit

### 4.5 Sharing Behavior

- Shared links are always editable
- Changes auto-fork the project (copy-on-write)
- Original URL preserved for owner

---

## 5. Design Checks (Optional)

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

| Metric | Target |
|--------|--------|
| Time to first solve (new user) | < 5 minutes |
| Mobile usability score | > 90 (Lighthouse) |
| Solve accuracy vs EPANET | < 1% deviation |
| User retention (return within 7 days) | > 40% |

---

## 7. Open Questions

1. **Cloud storage threshold:** At what project size do we transition from URL-encoded state to cloud storage?

2. **Merge conflict resolution:** How do we handle merge conflicts in the Git-like versioning? Visual diff? Auto-merge with conflicts flagged?

3. **Cost estimation scope:** What cost data sources? How granular (component-level, system-level)?

4. **API design:** REST vs GraphQL? Authentication method?

---

## 8. Appendices

### Appendix A: Competitive Analysis

| Tool | Strengths | Weaknesses |
|------|-----------|------------|
| EPANET | Free, proven solver | Desktop-only, dated UI |
| AFT Fathom | Powerful, professional | Expensive, desktop-only |
| Pipe-FLO | Good UI, comprehensive | Expensive, desktop-only |
| Online calculators | Free, accessible | Single-pipe only, limited |

### Appendix B: User Stories

**US-001:** As a student, I want to model a simple pump system so I can verify my hand calculations.

**US-002:** As a field technician, I want to quickly check if a proposed pump will work for a retrofit so I can advise on feasibility.

**US-003:** As a consulting engineer, I want to share a system model with my client so they can review and comment without installing software.

**US-004:** As a process engineer, I want to compare different pipe sizes so I can optimize my design for cost and performance.

**US-005:** As a team lead, I want to see the history of changes to a design so I can understand how it evolved.

---

*End of PRD*
