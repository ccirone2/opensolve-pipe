# OpenSolve Pipe - Development Plan

**Status:** Phase 1 Implementation (Backend Core Complete - Issues #1, #2, #3, #4, #5)
**Last Updated:** 2026-01-19

> **Progress Summary:** 5 of 19 Phase 1 issues completed (26%). All backend core services are complete:
>
> - [x] Project Setup ([#1](https://github.com/ccirone2/opensolve-pipe/issues/1), [PR #2](https://github.com/ccirone2/opensolve-pipe/pull/2))
> - [x] Pydantic Data Models ([#5](https://github.com/ccirone2/opensolve-pipe/issues/5), [PR #6](https://github.com/ccirone2/opensolve-pipe/pull/6))
> - [x] Data Libraries ([#7](https://github.com/ccirone2/opensolve-pipe/issues/7), [PR #8](https://github.com/ccirone2/opensolve-pipe/pull/8))
> - [x] Fluid Properties Service ([#9](https://github.com/ccirone2/opensolve-pipe/issues/9), [PR #11](https://github.com/ccirone2/opensolve-pipe/pull/11))
> - [x] Simple Solver ([#10](https://github.com/ccirone2/opensolve-pipe/issues/10), [PR #12](https://github.com/ccirone2/opensolve-pipe/pull/12))

---

## Overview

This document outlines the phased development approach for OpenSolve Pipe, starting with a minimal viable product (MVP) and progressively adding features. Each phase is designed to be independently deployable and valuable to users.

**Guiding Principles:**

- Ship early and often
- Validate with real users after each phase
- Simple networks first, complex networks later
- Mobile-responsive from day one

---

## Phase 1: MVP - Simple Solver + Basic UI

**Goal:** Prove the core concept with a working single-path solver and minimal UI

**Estimated Complexity:** Medium (3-4 weeks)

**Success Criteria:**

- ✅ Users can model a pump → pipe → tank system
- ✅ System solves correctly (< 1% deviation from EPANET)
- ✅ Results display flow, pressures, operating point
- ✅ Project state encodes to URL
- ✅ URL decodes back to working project
- ✅ Works on mobile (responsive design)

### 1.1 Backend - Simple Solver (High Priority)

> ✅ **COMPLETED** - [GitHub Issue #10](https://github.com/ccirone2/opensolve-pipe/issues/10) | [PR #12](https://github.com/ccirone2/opensolve-pipe/pull/12)

**Files:**

- `apps/api/src/opensolve_pipe/services/solver/simple.py`
- `apps/api/src/opensolve_pipe/services/solver/friction.py`
- `apps/api/src/opensolve_pipe/services/solver/k_factors.py`

**Tasks:**

- [x] Implement Darcy-Weisbach friction factor calculation (Colebrook via `fluids` library)
- [x] Create head loss calculator for pipe segments (friction.py)
- [x] Implement K-factor resolution for fittings (Crane TP-410 L/D method)
- [x] Build system curve generator (head loss vs flow)
- [x] Create pump curve interpolator (cubic spline)
- [x] Implement operating point finder (Brent's method)
- [x] Calculate full network state at operating point (velocity, Reynolds, NPSH)

**Dependencies:** `fluids` library, `scipy` (for optimization)

**Complexity:** High - Core hydraulic calculations

---

### 1.2 Backend - Data Models (High Priority)

> ✅ **COMPLETED** - [GitHub Issue #5](https://github.com/ccirone2/opensolve-pipe/issues/5) | [PR #6](https://github.com/ccirone2/opensolve-pipe/pull/6)

**Files:** `apps/api/src/opensolve_pipe/models/`

**Tasks:**

- [x] Define Pydantic models for Project, Component, PipingSegment
- [x] Implement Reservoir, Tank, Junction models
- [x] Implement Pump model with curve handling
- [x] Create PipeDefinition and Fitting models
- [x] Define SolvedState output models
- [x] Add validation rules (physical bounds, required fields)

**Complexity:** Medium - Straightforward data modeling

---

### 1.3 Backend - Data Libraries (Medium Priority)

> ✅ **COMPLETED** - [GitHub Issue #7](https://github.com/ccirone2/opensolve-pipe/issues/7) | [PR #8](https://github.com/ccirone2/opensolve-pipe/pull/8)

**Files:** `apps/api/src/opensolve_pipe/data/`

**Tasks:**

- [x] Create `pipe_materials.json` (carbon steel, SS, PVC - Schedule 40/80)
- [x] Create `fittings.json` (elbows, tees, valves - Crane TP-410 L/D method)
- [x] Create `fluids.json` (water only for MVP)
- [x] Implement pipe material lookup service
- [x] Implement fitting K-factor lookup service (with f_T lookup)

**Complexity:** Low - Data entry and simple lookups

---

### 1.4 Backend - Fluid Properties (Medium Priority)

> ✅ **COMPLETED** - [GitHub Issue #9](https://github.com/ccirone2/opensolve-pipe/issues/9) | [PR #11](https://github.com/ccirone2/opensolve-pipe/pull/11)

**Files:**

- `apps/api/src/opensolve_pipe/services/fluids.py`
- `apps/api/src/opensolve_pipe/models/fluids.py`

**Tasks:**

- [x] Implement water property calculations (temp-dependent via `fluids` library)
- [x] Define FluidProperties model (density, viscosity, vapor pressure, specific gravity)
- [x] Add temperature unit conversion (Fahrenheit, Celsius, Kelvin)

**Dependencies:** `fluids` library for water properties

**Complexity:** Low - Library wrapper

---

### 1.5 Backend - API Endpoints (High Priority)

**Files:** `apps/api/src/opensolve_pipe/routers/`

**Tasks:**

- [ ] Implement `/api/v1/solve` endpoint
- [ ] Implement `/api/v1/fluids` endpoint
- [ ] Implement `/api/v1/fluids/{fluid_id}/properties` endpoint
- [ ] Add request/response validation
- [ ] Add error handling and meaningful error messages
- [ ] Set up CORS for frontend

**Complexity:** Medium - API plumbing

---

### 1.6 Backend - Unit Conversion (Medium Priority)

**File:** `apps/api/src/opensolve_pipe/utils/units.py`

**Tasks:**

- [ ] Implement unit conversion system (length, pressure, flow)
- [ ] Add unit validation
- [ ] Create UnitPreferences model

**Complexity:** Medium - Careful handling of conversions

---

### 1.7 Frontend - Project State Management (High Priority)

**Files:** `apps/web/src/lib/stores/`

**Tasks:**

- [ ] Create project store (Svelte store)
- [ ] Implement component chain management (add/remove/edit)
- [ ] Add undo/redo history
- [ ] Create current element navigation state
- [ ] Implement derived stores for common queries

**Complexity:** Medium - State management patterns

---

### 1.8 Frontend - URL Encoding/Decoding (High Priority)

**File:** `apps/web/src/lib/utils/encoding.ts`

**Tasks:**

- [ ] Implement project → JSON → gzip → base64url pipeline
- [ ] Implement reverse decoding pipeline
- [ ] Add error handling for corrupt URLs
- [ ] Add size threshold detection (warn if > 2KB)
- [ ] Write comprehensive tests for roundtrip encoding

**Dependencies:** `pako` (gzip library)

**Complexity:** Medium - Careful encoding/compression

---

### 1.9 Frontend - Panel Navigator UI (High Priority)

**Files:** `apps/web/src/lib/components/panel/`

**Tasks:**

- [ ] Create PanelNavigator component (main container)
- [ ] Create ElementPanel component (element properties form)
- [ ] Create PipingPanel component (pipe + fittings editor)
- [ ] Create FittingsTable component (add/remove/edit fittings)
- [ ] Create NavigationControls component (prev/next buttons)
- [ ] Implement breadcrumb navigation trail
- [ ] Add element type selector (for adding new elements)

**Complexity:** High - Core UI interaction

---

### 1.10 Frontend - Component Forms (Medium Priority)

**Files:** `apps/web/src/lib/components/forms/`

**Tasks:**

- [ ] Create ReservoirForm (elevation, water level)
- [ ] Create TankForm (elevation, dimensions, levels)
- [ ] Create PumpForm (curve entry, name)
- [ ] Create PipeForm (material, schedule, diameter, length)
- [ ] Create FittingSelector (dropdown with K-factors)
- [ ] Add unit display/conversion in forms

**Complexity:** Medium - Form handling

---

### 1.11 Frontend - Results Display (Medium Priority)

**Files:** `apps/web/src/lib/components/results/`

**Tasks:**

- [ ] Create ResultsPanel component (main container)
- [ ] Create PumpCurveChart component (pump + system curve)
- [ ] Create NodeTable component (pressures, HGL, EGL)
- [ ] Create LinkTable component (flows, velocities, head loss)
- [ ] Add convergence status indicator
- [ ] Handle non-converged results gracefully

**Dependencies:** Chart.js for pump curve

**Complexity:** Medium - Data visualization

---

### 1.12 Frontend - Basic UI Shell (High Priority)

**Files:** `apps/web/src/routes/`

**Tasks:**

- [ ] Create main layout with header
- [ ] Add view mode switcher (panel / results)
- [ ] Create "Solve" button with loading state
- [ ] Add project name editor
- [ ] Implement URL routing (/ vs /p/{encoded})
- [ ] Add mobile-responsive design (Tailwind)

**Complexity:** Medium - App structure

---

### 1.13 Testing & Validation (High Priority)

**Tasks:**

- [ ] Write backend solver tests (compare vs known results)
- [ ] Test URL encoding/decoding roundtrip
- [ ] Test API endpoints with Postman/curl
- [ ] Manual test on mobile devices
- [ ] Test with example systems (simple pump-pipe-tank)

**Complexity:** Medium - Test coverage

---

### 1.14 Deployment (Medium Priority)

**Tasks:**

- [ ] Set up Vercel deployment for frontend
- [ ] Set up Railway/Fly.io deployment for backend
- [ ] Configure environment variables
- [ ] Set up HTTPS and CORS
- [ ] Create basic landing page (project description)

**Complexity:** Low - Standard deployment

---

### Phase 1 Dependencies

```mermaid
graph TD
    A[Data Models] --> B[Simple Solver]
    A --> C[API Endpoints]
    D[Data Libraries] --> B
    E[Fluid Properties] --> B
    B --> C
    C --> F[Frontend State]
    F --> G[URL Encoding]
    F --> H[Panel Navigator]
    H --> I[Component Forms]
    G --> J[Results Display]
    C --> J
    J --> K[Testing]
    K --> L[Deployment]
```

**Critical Path:** Data Models → Simple Solver → API Endpoints → Frontend State → Panel Navigator → Results Display → Testing → Deployment

---

## Phase 2: Network Solver + Schematic

**Goal:** Support branching/looped networks and provide visual schematic

**Estimated Complexity:** High (4-5 weeks)

**Success Criteria:**

- ✅ Users can model branching networks (e.g., parallel pumps)
- ✅ Users can model looped networks
- ✅ Schematic auto-generates and is interactive
- ✅ Solver converges for complex topologies

### 2.1 Backend - Network Solver

**File:** `apps/api/src/opensolve_pipe/services/solver/network.py`

**Tasks:**

- [ ] Implement component chain → WNTR adapter
- [ ] Handle WNTR node creation (reservoirs, tanks, junctions)
- [ ] Handle WNTR link creation (pipes, pumps, valves)
- [ ] Map minor losses to WNTR equivalent
- [ ] Run EPANET solver via WNTR
- [ ] Convert WNTR results back to SolvedState
- [ ] Add topology validation (detect disconnected components)

**Dependencies:** `wntr` library

**Complexity:** Very High - Complex graph conversion

---

### 2.2 Backend - Solver Router

**File:** `apps/api/src/opensolve_pipe/services/solver/__init__.py`

**Tasks:**

- [ ] Implement solver selection logic (simple vs network)
- [ ] Detect topology type (single-path vs branching)
- [ ] Route to appropriate solver
- [ ] Unify result format

**Complexity:** Low - Routing logic

---

### 2.3 Frontend - Branching Support

**Tasks:**

- [ ] Update data model to support multiple downstream connections
- [ ] Update panel navigator to show branch selector
- [ ] Add "Create Branch" UI
- [ ] Handle loop closure detection
- [ ] Update URL encoding to support branches

**Complexity:** High - Complex state management

---

### 2.4 Frontend - Schematic Viewer

**File:** `apps/web/src/lib/components/schematic/`

**Tasks:**

- [ ] Create SchematicViewer component (SVG canvas)
- [ ] Implement graph layout algorithm (dagre or elkjs)
- [ ] Create component symbols (pump, tank, valve, etc.)
- [ ] Render pipes as connecting lines
- [ ] Add click handlers (click element → open panel)
- [ ] Implement zoom/pan controls
- [ ] Add mobile touch gesture support

**Dependencies:** D3.js, dagre/elkjs

**Complexity:** Very High - Graph visualization

---

### 2.5 Additional Component Types

**Tasks:**

- [ ] Add Valve components (gate, ball, butterfly)
- [ ] Add Check Valve component
- [ ] Add Heat Exchanger component (fixed pressure drop)
- [ ] Update forms and panel UI for new types

**Complexity:** Medium - More components

---

### 2.6 Testing

**Tasks:**

- [ ] Test parallel pump configuration
- [ ] Test looped network (Hardy Cross method validation)
- [ ] Test schematic rendering for various topologies
- [ ] Benchmark solve times for medium networks (20-100 components)

**Complexity:** High - Complex test cases

---

## Phase 3: Enhanced Features

**Goal:** Polish the user experience and add power-user features

**Estimated Complexity:** Medium (3-4 weeks)

### 3.1 Pump Library

**Tasks:**

- [ ] Add project-level pump curve storage
- [ ] Create pump curve manager UI
- [ ] Allow CSV import of pump curves
- [ ] Add pump curve validation (monotonic, positive)
- [ ] Support efficiency curves

**Complexity:** Medium

---

### 3.2 Additional Fluids

**Tasks:**

- [ ] Add ethylene glycol solutions (CoolProp)
- [ ] Add propylene glycol solutions
- [ ] Add common fuels (diesel, gasoline)
- [ ] Support custom fluid entry
- [ ] Update fluid selector UI

**Complexity:** Medium

---

### 3.3 Design Checks

**File:** `apps/api/src/opensolve_pipe/services/checks.py`

**Tasks:**

- [ ] Implement velocity checks (min/max)
- [ ] Implement NPSH margin checks
- [ ] Create check configuration UI
- [ ] Add "Check Model" button
- [ ] Display warnings in results panel

**Complexity:** Medium

---

### 3.4 Export Features

**Tasks:**

- [ ] Implement CSV export (results tables)
- [ ] Implement Excel export (formatted workbook)
- [ ] Implement PNG export (schematic)
- [ ] Implement SVG export (schematic)
- [ ] Add "Export" button to results panel

**Dependencies:** `openpyxl` for Excel export

**Complexity:** Medium

---

### 3.5 UI Polish

**Tasks:**

- [ ] Add keyboard shortcuts (arrow keys to navigate)
- [ ] Improve loading states and animations
- [ ] Add tooltips for technical terms
- [ ] Create onboarding tutorial/tour
- [ ] Add example projects (pre-built systems)

**Complexity:** Medium

---

### 3.6 Advanced Pipe Materials

**Tasks:**

- [ ] Expand pipe materials library (ductile iron, HDPE, GRP)
- [ ] Add pipe liner support
- [ ] Support custom roughness override
- [ ] Add more pipe schedules (5S, 10S, 160, XXS)

**Complexity:** Low - Data entry

---

### 3.7 Control Valves

**Tasks:**

- [ ] Implement PRV (pressure reducing valve)
- [ ] Implement PSV (pressure sustaining valve)
- [ ] Implement FCV (flow control valve)
- [ ] Add simplified vs detailed valve models
- [ ] Create valve configuration forms

**Complexity:** High - Valve logic in solver

---

## Phase 4: Collaboration & Persistence

**Goal:** Enable multi-user workflows and long-term project storage

**Estimated Complexity:** High (5-6 weeks)

### 4.1 User Accounts

**Tasks:**

- [ ] Set up authentication (Auth0 or Supabase Auth)
- [ ] Create user registration/login flow
- [ ] Add "My Projects" dashboard
- [ ] Store projects in PostgreSQL
- [ ] Implement project list/search

**Complexity:** High - Auth + DB setup

---

### 4.2 Project Persistence

**Tasks:**

- [ ] Implement server-side project storage
- [ ] Handle large projects (> 50KB)
- [ ] Create short reference keys for URLs
- [ ] Add auto-save functionality
- [ ] Implement project naming and metadata

**Complexity:** Medium

---

### 4.3 Version Control

**Tasks:**

- [ ] Implement commit operation
- [ ] Implement branch creation
- [ ] Implement checkout (load version)
- [ ] Create version history UI
- [ ] Add merge conflict detection
- [ ] Implement merge UI

**Complexity:** Very High - Git-like operations

---

### 4.4 Sharing & Permissions

**Tasks:**

- [ ] Implement project sharing (shareable links)
- [ ] Add copy-on-write for shared projects
- [ ] Create collaboration invite system
- [ ] Add read-only vs edit permissions
- [ ] Implement commenting system (optional)

**Complexity:** High - Multi-user coordination

---

## Phase 5: Future Enhancements

**Goal:** Advanced features for power users and new markets

**Estimated Complexity:** Variable

### 5.1 Cost Estimation

**Tasks:**

- [ ] Research cost data sources
- [ ] Create component cost database
- [ ] Implement cost calculation service
- [ ] Add cost estimation report UI
- [ ] Support regional pricing variations

**Complexity:** High - Data acquisition + calculations

---

### 5.2 Pipe Sizing Optimization

**Tasks:**

- [ ] Implement optimization objective functions
- [ ] Add constraints (velocity limits, pressure requirements)
- [ ] Integrate optimization solver (scipy.optimize)
- [ ] Create optimization configuration UI
- [ ] Display optimization results

**Complexity:** Very High - Optimization algorithms

---

### 5.3 Global Pump Database

**Tasks:**

- [ ] Create pump database schema
- [ ] Build pump data collection system
- [ ] Add pump search/filter UI
- [ ] Implement pump data submission
- [ ] Add manufacturer verification workflow

**Complexity:** High - Database + moderation

---

### 5.4 Pump Curve Digitization

**Tasks:**

- [ ] Research OCR/CV libraries for curve extraction
- [ ] Build image upload and preprocessing
- [ ] Implement curve detection algorithm
- [ ] Add manual adjustment UI
- [ ] Validate extracted curves

**Complexity:** Very High - Computer vision

---

### 5.5 Public API

**Tasks:**

- [ ] Design REST API specification
- [ ] Add API key authentication
- [ ] Implement rate limiting per key
- [ ] Create API documentation (OpenAPI/Swagger)
- [ ] Build API client examples (Python, JS)
- [ ] Add webhook support for async solves

**Complexity:** Medium - API wrapper

---

### 5.6 Advanced Visualization

**Tasks:**

- [ ] Color-coded results on schematic (flow/pressure)
- [ ] Animated flow visualization
- [ ] 3D isometric view option
- [ ] Export to CAD formats (DXF)

**Complexity:** High - Graphics programming

---

## Risk Mitigation

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| WNTR integration complexity | High | High | Start with simple solver, add WNTR in Phase 2 |
| URL size limits | Medium | Medium | Implement server storage for large projects |
| Mobile performance | Medium | High | Profile early, optimize rendering |
| Solver convergence failures | High | Medium | Clear error messages, provide diagnostics |
| CORS/deployment issues | Medium | Low | Test deployment early in Phase 1 |

### Product Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| User adoption | Medium | High | Focus on ease of use, onboarding |
| Accuracy concerns | Low | High | Validate against EPANET, document methods |
| Competitor moves | Low | Medium | Ship fast, build community |
| Complexity creep | High | Medium | Stick to phase plan, resist scope creep |

---

## Success Metrics

### Phase 1 (MVP)

- [ ] 10 beta users successfully solve a system
- [ ] Average time to first solve < 5 minutes
- [ ] Zero critical bugs after 1 week of use
- [ ] Mobile usability score > 80

### Phase 2 (Network Solver)

- [ ] 50+ active users
- [ ] Complex network solve success rate > 95%
- [ ] Average solve time < 5 seconds for 50-component networks
- [ ] Positive user feedback on schematic visualization

### Phase 3 (Enhanced Features)

- [ ] 200+ active users
- [ ] 50+ exports generated per week
- [ ] 10+ community-contributed pump curves
- [ ] User retention (7-day) > 40%

### Phase 4 (Collaboration)

- [ ] 500+ registered users
- [ ] 100+ projects saved to server
- [ ] 20+ shared projects actively used
- [ ] Average session duration > 10 minutes

---

## Development Workflow

### Sprint Structure

- **Sprint length:** 2 weeks
- **Velocity:** Adjust based on team size and complexity
- **Ceremonies:** Daily standup (async), sprint review, retro

### Definition of Done

- [ ] Code complete and peer reviewed
- [ ] Unit tests written and passing
- [ ] Integration tests passing
- [ ] Manual testing completed
- [ ] Documentation updated
- [ ] Deployed to staging
- [ ] Product owner approved

### Git Workflow

- **Main branch:** Production-ready code
- **Develop branch:** Integration branch
- **Feature branches:** `feature/issue-123-description`
- **Release branches:** `release/v1.2.0`

### Code Review

- All code requires 1 approval before merge
- Automated tests must pass
- Linting and formatting enforced (Prettier, ESLint, Ruff)

---

## Next Steps

1. ~~**Immediate:** Create GitHub issues for Phase 1~~ ✅ Done
2. ~~**Week 1:** Set up project structure, install dependencies~~ ✅ Done (Issue #1)
3. ~~**Backend Core:** Implement data models and simple solver~~ ✅ Done
   - ✅ Data Models ([#5](https://github.com/ccirone2/opensolve-pipe/issues/5), [PR #6](https://github.com/ccirone2/opensolve-pipe/pull/6))
   - ✅ Data Libraries ([#7](https://github.com/ccirone2/opensolve-pipe/issues/7), [PR #8](https://github.com/ccirone2/opensolve-pipe/pull/8))
   - ✅ Fluid Properties ([#9](https://github.com/ccirone2/opensolve-pipe/issues/9), [PR #11](https://github.com/ccirone2/opensolve-pipe/pull/11))
   - ✅ Simple Solver ([#10](https://github.com/ccirone2/opensolve-pipe/issues/10), [PR #12](https://github.com/ccirone2/opensolve-pipe/pull/12))
4. **Next:** Implement unit conversion system (Doc Issue #6) and API endpoints (Doc Issue #7)
5. **Then:** Create frontend state management and panel UI (Issues #10, #12)
6. **Then:** Build results display and URL encoding (Issues #11, #14)
7. **Finally:** Testing, bug fixes, deployment (Issues #17, #18)

---

## Appendix: Estimated Effort by Phase

| Phase | Complexity | Estimated Time | Core Team Size |
|-------|------------|----------------|----------------|
| Phase 1: MVP | Medium | 3-4 weeks | 2-3 developers |
| Phase 2: Network Solver | High | 4-5 weeks | 2-3 developers |
| Phase 3: Enhanced Features | Medium | 3-4 weeks | 2-3 developers |
| Phase 4: Collaboration | High | 5-6 weeks | 3-4 developers |
| Phase 5: Future (each feature) | Variable | 2-8 weeks | 1-2 developers |

**Total for MVP + Core (Phases 1-2):** 7-9 weeks

**Total for Production-Ready (Phases 1-4):** 15-19 weeks

---

**End of Development Plan**
