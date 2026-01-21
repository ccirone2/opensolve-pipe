# Phase 1 GitHub Issues

This document contains all GitHub issues for Phase 1 (MVP) of OpenSolve Pipe.

---

## Issue Status Summary

| Doc # | Title | GitHub Issue | PR | Status |
|-------|-------|--------------|----|----|
| 1 | Project Setup and Repository Structure | [#1](https://github.com/ccirone2/opensolve-pipe/issues/1) | [PR #2](https://github.com/ccirone2/opensolve-pipe/pull/2) | ✅ **COMPLETE** |
| 2 | Backend - Define Pydantic Data Models | [#5](https://github.com/ccirone2/opensolve-pipe/issues/5) | [PR #6](https://github.com/ccirone2/opensolve-pipe/pull/6) | ✅ **COMPLETE** |
| 3 | Backend - Create Pipe Materials and Fittings Data Libraries | [#7](https://github.com/ccirone2/opensolve-pipe/issues/7) | [PR #8](https://github.com/ccirone2/opensolve-pipe/pull/8) | ✅ **COMPLETE** |
| 4 | Backend - Implement Fluid Properties Service | [#9](https://github.com/ccirone2/opensolve-pipe/issues/9) | [PR #11](https://github.com/ccirone2/opensolve-pipe/pull/11) | ✅ **COMPLETE** |
| 5 | Backend - Implement Simple Solver | [#10](https://github.com/ccirone2/opensolve-pipe/issues/10) | [PR #12](https://github.com/ccirone2/opensolve-pipe/pull/12) | ✅ **COMPLETE** |
| 6 | Backend - Implement Unit Conversion System | [#14](https://github.com/ccirone2/opensolve-pipe/issues/14) | - | ✅ **COMPLETE** |
| 7 | Backend - Create API Endpoints | [#15](https://github.com/ccirone2/opensolve-pipe/issues/15) | - | ✅ **COMPLETE** |
| 8 | Frontend - Setup SvelteKit Project and Routing | [#16](https://github.com/ccirone2/opensolve-pipe/issues/16) | - | ✅ **COMPLETE** |
| 9 | Frontend - Define TypeScript Interfaces | [#17](https://github.com/ccirone2/opensolve-pipe/issues/17) | - | ✅ **COMPLETE** |
| 10 | Frontend - Implement Project State Management | [#18](https://github.com/ccirone2/opensolve-pipe/issues/18) | - | ✅ **COMPLETE** |
| 11 | Frontend - Implement URL Encoding/Decoding | [#19](https://github.com/ccirone2/opensolve-pipe/issues/19) | - | ✅ **COMPLETE** |
| 12 | Frontend - Build Panel Navigator UI | [#20](https://github.com/ccirone2/opensolve-pipe/issues/20) | - | ✅ **COMPLETE** |
| 13 | Frontend - Build Component Property Forms | [#21](https://github.com/ccirone2/opensolve-pipe/issues/21) | - | ✅ **COMPLETE** |
| 14 | Frontend - Build Results Display Components | [#22](https://github.com/ccirone2/opensolve-pipe/issues/22) | - | ✅ **COMPLETE** |
| 15 | Frontend - Create API Client | [#23](https://github.com/ccirone2/opensolve-pipe/issues/23) | - | ✅ **COMPLETE** |
| 16 | Frontend - Implement "Solve" Button and Workflow | [#24](https://github.com/ccirone2/opensolve-pipe/issues/24) | - | ✅ **COMPLETE** |
| 17 | End-to-End Testing and Bug Fixes | [#25](https://github.com/ccirone2/opensolve-pipe/issues/25) | - | ✅ **COMPLETE** |
| 18 | Deployment Setup (Frontend + Backend) | [#26](https://github.com/ccirone2/opensolve-pipe/issues/26) | - | ✅ **COMPLETE** |
| 19 | Documentation and Landing Page | [#27](https://github.com/ccirone2/opensolve-pipe/issues/27) | - | ✅ **COMPLETE** |
| 20 | Backend - Port-Based Architecture | [#58](https://github.com/ccirone2/opensolve-pipe/issues/58) | - | 📋 Not Started |
| 21 | Backend - Reference Node and Plug Components | [#59](https://github.com/ccirone2/opensolve-pipe/issues/59) | - | 📋 Not Started |
| 22 | Backend - Branch Component (Tee/Wye/Cross) | [#60](https://github.com/ccirone2/opensolve-pipe/issues/60) | - | 📋 Not Started |
| 23 | Frontend - Port Connection Editor | [#61](https://github.com/ccirone2/opensolve-pipe/issues/61) | - | 📋 Not Started |
| 24 | Frontend - Reference Node Form | [#62](https://github.com/ccirone2/opensolve-pipe/issues/62) | - | 📋 Not Started |
| 25 | Frontend - Branch Component Forms | [#63](https://github.com/ccirone2/opensolve-pipe/issues/63) | - | 📋 Not Started |

**Progress:** 19 of 25 issues completed (76%)

**Backend Progress:** 7 of 10 backend issues completed (70%)

**Frontend Progress:** 12 of 12 frontend issues completed (100%)

---

**Choose your format:**

- [Manual Creation (Markdown Checklist)](#manual-creation-markdown-checklist)
- [Automated Creation (gh CLI Commands)](#automated-creation-gh-cli-commands)

---

## Manual Creation (Markdown Checklist)

Copy each issue below and create it manually in GitHub Issues.

---

### Issue #1: Project Setup and Repository Structure

> ✅ **COMPLETED** - [GitHub Issue #1](https://github.com/ccirone2/opensolve-pipe/issues/1) | [PR #2](https://github.com/ccirone2/opensolve-pipe/pull/2)

**Labels:** `setup`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Set up the monorepo structure and install core dependencies for both frontend and backend.

**Tasks:**

- [x] Create `apps/web/` directory structure for SvelteKit frontend
- [x] Create `apps/api/` directory structure for FastAPI backend
- [x] Initialize SvelteKit project with TypeScript
- [x] Initialize FastAPI project with pyproject.toml
- [x] Install backend dependencies: `fastapi`, `uvicorn`, `pydantic`, `fluids`, `scipy`
- [x] Install frontend dependencies: `pako`, `tailwindcss`, `chart.js`
- [x] Set up ESLint and Prettier for frontend
- [x] Set up Ruff for backend (replaces Black and isort)
- [x] Create `.gitignore` for both apps
- [x] Add README.md with setup instructions
- [x] Verify both apps run locally (`pnpm dev` and `uvicorn`)

**Acceptance Criteria:**

- Frontend runs on `localhost:5173`
- Backend runs on `localhost:8000`
- Both apps have working hot reload

---

### Issue #2: Backend - Define Pydantic Data Models

> ✅ **COMPLETED** - [GitHub Issue #5](https://github.com/ccirone2/opensolve-pipe/issues/5) | [PR #6](https://github.com/ccirone2/opensolve-pipe/pull/6)

**Labels:** `backend`, `models`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create Pydantic models for all core data structures: Project, Component, Piping, and SolvedState.

**Related Files:**

- `apps/api/src/opensolve_pipe/models/project.py`
- `apps/api/src/opensolve_pipe/models/components.py`
- `apps/api/src/opensolve_pipe/models/results.py`

**Tasks:**

- [x] Define `Project` model (metadata, settings, fluid, components, results)
- [x] Define `ProjectMetadata` model
- [x] Define `ProjectSettings` model (units, solver options)
- [x] Define `Component` base model with type discriminator
- [x] Define `Reservoir`, `Tank`, `Junction` component models
- [x] Define `Pump` model with `PumpCurve`
- [x] Define `PipingSegment` model (pipe + fittings)
- [x] Define `PipeDefinition` and `Fitting` models
- [x] Define `SolvedState` output model
- [x] Define `NodeResult` and `LinkResult` models
- [x] Define `PumpResult` model
- [x] Add validation rules (positive values, required fields)
- [x] Write unit tests for model validation

**Acceptance Criteria:**

- All models serialize to/from JSON correctly
- Invalid data raises `ValidationError`
- Models match TypeScript interfaces in TSD

---

### Issue #3: Backend - Create Pipe Materials and Fittings Data Libraries

> ✅ **COMPLETED** - [GitHub Issue #7](https://github.com/ccirone2/opensolve-pipe/issues/7) | [PR #8](https://github.com/ccirone2/opensolve-pipe/pull/8)

**Labels:** `backend`, `data`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create JSON data files for pipe materials and fittings with lookup services.

**Related Files:**

- `apps/api/src/opensolve_pipe/data/pipe_materials.json`
- `apps/api/src/opensolve_pipe/data/fittings.json`
- `apps/api/src/opensolve_pipe/data/fluids.json`
- `apps/api/src/opensolve_pipe/services/data.py`

**Tasks:**

- [x] Create `pipe_materials.json` with carbon steel, stainless steel, PVC (Schedule 40/80)
- [x] Include nominal sizes 2", 2.5", 3", 4", 6", 8" with ID/OD/wall thickness
- [x] Create `fittings.json` with elbows (90°, 45°), tees, valves (Crane TP-410 K-factors)
- [x] Create `fluids.json` with water properties (temperature-dependent)
- [x] Implement `get_pipe_material()` service function
- [x] Implement `get_fitting_k_factor()` service function
- [x] Implement `get_fluid_properties()` service function
- [x] Add error handling for missing materials/fittings
- [x] Write tests for data lookup functions

**Acceptance Criteria:**

- All data files validate as proper JSON
- Service functions return correct data
- Missing items raise appropriate errors

---

### Issue #4: Backend - Implement Fluid Properties Service

> ✅ **COMPLETED** - [GitHub Issue #9](https://github.com/ccirone2/opensolve-pipe/issues/9) | [PR #11](https://github.com/ccirone2/opensolve-pipe/pull/11)

**Labels:** `backend`, `fluids`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create service for calculating fluid properties using the `fluids` library.

**Related Files:**

- `apps/api/src/opensolve_pipe/services/fluids.py`
- `apps/api/src/opensolve_pipe/models/fluids.py`

**Tasks:**

- [x] Define `FluidProperties` model (density, viscosity, vapor pressure)
- [x] Implement water properties calculation at given temperature
- [x] Add temperature unit conversion (F, C, K)
- [x] Handle out-of-range temperatures gracefully
- [x] Write tests comparing results to known values
- [x] Add docstrings with example usage

**Acceptance Criteria:**

- Water at 68°F returns correct density (~62.32 lb/ft³)
- Properties are consistent with `fluids` library
- Unit conversions work correctly

---

### Issue #5: Backend - Implement Simple Solver (Core Hydraulic Calculations)

> ✅ **COMPLETED** - [GitHub Issue #10](https://github.com/ccirone2/opensolve-pipe/issues/10) | [PR #12](https://github.com/ccirone2/opensolve-pipe/pull/12)

**Labels:** `backend`, `solver`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Implement the simple solver for single-path networks (no branches). This is the core hydraulic calculation engine.

**Related Files:**

- `apps/api/src/opensolve_pipe/services/solver/simple.py`
- `apps/api/src/opensolve_pipe/services/solver/k_factors.py`

**Tasks:**

- [x] Implement Darcy-Weisbach friction factor calculation (Colebrook equation)
- [x] Implement pipe head loss calculation (friction + minor losses)
- [x] Implement K-factor resolution for fittings (L/D method)
- [x] Create system curve generator (head loss vs flow)
- [x] Implement pump curve interpolator (cubic spline)
- [x] Implement operating point finder (curve intersection with scipy.optimize)
- [x] Calculate node pressures, velocities, Reynolds numbers
- [x] Calculate NPSH available at pump suction
- [x] Add convergence detection and iteration limits
- [x] Write comprehensive tests with known solutions

**Acceptance Criteria:**

- Simple pump-pipe-tank system solves correctly
- Results match hand calculations (< 1% error)
- Solver converges in < 100 iterations
- Non-converged cases return clear error messages

**Reference:**

- Crane TP-410 for K-factors
- Darcy-Weisbach equation: `h_f = f × (L/D) × (v²/2g)`

---

### Issue #6: Backend - Implement Unit Conversion System

> ✅ **COMPLETED** - [GitHub Issue #14](https://github.com/ccirone2/opensolve-pipe/issues/14)

**Labels:** `backend`, `utilities`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create a comprehensive unit conversion system for all physical quantities.

**Related Files:**

- `apps/api/src/opensolve_pipe/utils/units.py`

**Tasks:**

- [ ] Define `UnitCategory` enum (length, pressure, flow, velocity, etc.)
- [ ] Create conversion factors dictionary (to SI base units)
- [ ] Implement `convert(value, from_unit, to_unit)` function
- [ ] Add validation for compatible unit categories
- [ ] Define `UnitPreferences` model
- [ ] Write tests for all conversion pairs
- [ ] Add temperature conversions (with offset handling)

**Acceptance Criteria:**

- All common conversions work correctly (psi ↔ kPa, GPM ↔ L/s, etc.)
- Incompatible conversions raise `ValueError`
- Temperature conversions handle offsets correctly

---

### Issue #7: Backend - Create API Endpoints (Solve, Fluids)

> ✅ **COMPLETED** - [GitHub Issue #15](https://github.com/ccirone2/opensolve-pipe/issues/15)

**Labels:** `backend`, `api`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Implement FastAPI endpoints for solving networks and querying fluid properties.

**Related Files:**

- `apps/api/src/opensolve_pipe/main.py`
- `apps/api/src/opensolve_pipe/routers/solve.py`
- `apps/api/src/opensolve_pipe/routers/fluids.py`

**Tasks:**

- [ ] Create FastAPI app with CORS middleware
- [ ] Implement `POST /api/v1/solve` endpoint
- [ ] Implement `GET /api/v1/fluids` endpoint (list available fluids)
- [ ] Implement `GET /api/v1/fluids/{fluid_id}/properties` endpoint
- [ ] Add request validation (Pydantic models)
- [ ] Add response models for type safety
- [ ] Implement error handling (validation errors, solver failures)
- [ ] Add health check endpoint (`GET /health`)
- [ ] Write API tests (pytest + httpx)
- [ ] Document endpoints with OpenAPI docstrings

**Acceptance Criteria:**

- `/api/v1/solve` accepts Project and returns SolvedState
- Fluid endpoints return correct properties
- Invalid requests return 400/422 with clear error messages
- OpenAPI docs accessible at `/docs`

---

### Issue #8: Frontend - Setup SvelteKit Project and Routing

> ✅ **COMPLETED** - [GitHub Issue #16](https://github.com/ccirone2/opensolve-pipe/issues/16)

**Labels:** `frontend`, `setup`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Initialize SvelteKit with TypeScript, Tailwind CSS, and basic routing.

**Related Files:**

- `apps/web/src/routes/+page.svelte`
- `apps/web/src/routes/p/[...encoded]/+page.svelte`
- `apps/web/src/app.html`
- `apps/web/tailwind.config.js`

**Tasks:**

- [ ] Configure Tailwind CSS with custom design tokens
- [ ] Create main landing page (`/`)
- [ ] Create project viewer route (`/p/{encoded}`)
- [ ] Set up routing with SvelteKit
- [ ] Add responsive mobile-first layout
- [ ] Create basic header component with project name
- [ ] Add view mode switcher (panel / results)
- [ ] Test routing on mobile and desktop

**Acceptance Criteria:**

- Tailwind classes work correctly
- Routes navigate properly
- Responsive design works on mobile (< 768px)

---

### Issue #9: Frontend - Define TypeScript Interfaces (Data Models)

> ✅ **COMPLETED** - [GitHub Issue #17](https://github.com/ccirone2/opensolve-pipe/issues/17)

**Labels:** `frontend`, `models`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create TypeScript interfaces matching backend Pydantic models.

**Related Files:**

- `apps/web/src/lib/models/project.ts`
- `apps/web/src/lib/models/components.ts`
- `apps/web/src/lib/models/results.ts`

**Tasks:**

- [ ] Define `Project` interface
- [ ] Define component interfaces (Reservoir, Tank, Junction, Pump)
- [ ] Define `PipingSegment`, `PipeDefinition`, `Fitting` interfaces
- [ ] Define `SolvedState` and result interfaces
- [ ] Add type guards for component discrimination
- [ ] Export all types from index file
- [ ] Verify alignment with backend models

**Acceptance Criteria:**

- All interfaces compile without errors
- Type guards work correctly for component types
- Interfaces match backend Pydantic models

---

### Issue #10: Frontend - Implement Project State Management (Svelte Stores)

> ✅ **COMPLETED** - [GitHub Issue #18](https://github.com/ccirone2/opensolve-pipe/issues/18)

**Labels:** `frontend`, `state`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Create Svelte stores for managing project state, including component chain and navigation.

**Related Files:**

- `apps/web/src/lib/stores/project.ts`
- `apps/web/src/lib/stores/navigation.ts`

**Tasks:**

- [ ] Create `projectStore` (writable store for Project)
- [ ] Add methods: `addComponent()`, `removeComponent()`, `updateComponent()`
- [ ] Create `currentElementId` store for navigation
- [ ] Create `navigationPath` derived store (breadcrumb trail)
- [ ] Implement undo/redo with history stack
- [ ] Add `solvedState` store for results
- [ ] Write tests for store actions
- [ ] Add local storage persistence (optional MVP enhancement)

**Acceptance Criteria:**

- Components can be added/removed/edited
- Navigation state updates correctly
- Undo/redo works for all actions
- Store updates trigger UI re-renders

---

### Issue #11: Frontend - Implement URL Encoding/Decoding

> ✅ **COMPLETED** - [GitHub Issue #19](https://github.com/ccirone2/opensolve-pipe/issues/19)

**Labels:** `frontend`, `encoding`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Implement project serialization to URL-safe compressed format.

**Related Files:**

- `apps/web/src/lib/utils/encoding.ts`

**Tasks:**

- [ ] Install `pako` library (gzip compression)
- [ ] Implement `encodeProject(project: Project): string` function
- [ ] Implement `decodeProject(encoded: string): Project` function
- [ ] Add error handling for corrupt/invalid URLs
- [ ] Implement size threshold detection (warn if > 2KB)
- [ ] Add compression level optimization
- [ ] Write roundtrip tests (encode → decode should equal original)
- [ ] Test with various project sizes

**Acceptance Criteria:**

- Empty project encodes to short string (< 200 chars)
- Medium project (5 components) encodes to < 2KB
- Roundtrip preserves all data
- Invalid URLs throw descriptive errors

**Reference:**

- Encoding pipeline: JSON → gzip → base64url

---

### Issue #12: Frontend - Build Panel Navigator UI

> ✅ **COMPLETED** - [GitHub Issue #20](https://github.com/ccirone2/opensolve-pipe/issues/20)

**Labels:** `frontend`, `ui`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Create the primary UI for building and editing the hydraulic network element-by-element.

**Related Files:**

- `apps/web/src/lib/components/panel/PanelNavigator.svelte`
- `apps/web/src/lib/components/panel/ElementPanel.svelte`
- `apps/web/src/lib/components/panel/PipingPanel.svelte`
- `apps/web/src/lib/components/panel/NavigationControls.svelte`

**Tasks:**

- [ ] Create `PanelNavigator` component (main container)
- [ ] Create `ElementPanel` with property forms
- [ ] Create `PipingPanel` for pipe and fittings configuration
- [ ] Create `NavigationControls` (prev/next buttons)
- [ ] Add breadcrumb navigation trail
- [ ] Implement element type selector for adding new elements
- [ ] Add tab switcher (Element / Upstream / Downstream)
- [ ] Style with Tailwind CSS (mobile-first)
- [ ] Add keyboard navigation support (arrow keys)

**Acceptance Criteria:**

- Users can navigate through component chain
- Users can edit component properties
- Users can add/remove components
- UI is responsive on mobile devices
- Navigation feels intuitive

---

### Issue #13: Frontend - Build Component Property Forms

> ✅ **COMPLETED** - [GitHub Issue #21](https://github.com/ccirone2/opensolve-pipe/issues/21)

**Labels:** `frontend`, `forms`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create forms for editing properties of each component type.

**Related Files:**

- `apps/web/src/lib/components/forms/ReservoirForm.svelte`
- `apps/web/src/lib/components/forms/TankForm.svelte`
- `apps/web/src/lib/components/forms/PumpForm.svelte`
- `apps/web/src/lib/components/forms/PipeForm.svelte`
- `apps/web/src/lib/components/forms/FittingsTable.svelte`

**Tasks:**

- [ ] Create `ReservoirForm` (elevation, water level)
- [ ] Create `TankForm` (elevation, dimensions, levels)
- [ ] Create `PumpForm` with curve entry table
- [ ] Create `PipeForm` (material selector, schedule, diameter, length)
- [ ] Create `FittingsTable` (add/remove/edit fittings with quantity)
- [ ] Add unit display and inline unit conversion
- [ ] Add form validation (positive numbers, required fields)
- [ ] Add number input with sensible min/max ranges

**Acceptance Criteria:**

- All component types can be fully configured
- Form validation prevents invalid inputs
- Unit labels display correctly
- Forms work on mobile touch screens

---

### Issue #14: Frontend - Build Results Display Components

> ✅ **COMPLETED** - [GitHub Issue #22](https://github.com/ccirone2/opensolve-pipe/issues/22)

**Labels:** `frontend`, `visualization`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Create components for displaying solved network results, including pump curve visualization.

**Related Files:**

- `apps/web/src/lib/components/results/ResultsPanel.svelte`
- `apps/web/src/lib/components/results/PumpCurveChart.svelte`
- `apps/web/src/lib/components/results/NodeTable.svelte`
- `apps/web/src/lib/components/results/LinkTable.svelte`

**Tasks:**

- [ ] Create `ResultsPanel` component (main container)
- [ ] Create `PumpCurveChart` using Chart.js (pump + system curves)
- [ ] Create `NodeTable` showing pressures, HGL, EGL for all nodes
- [ ] Create `LinkTable` showing flows, velocities, head loss for all links
- [ ] Add operating point indicator on pump curve
- [ ] Display convergence status (success/failure)
- [ ] Handle non-converged results with error messages
- [ ] Add loading state during solve
- [ ] Make tables scrollable on mobile

**Acceptance Criteria:**

- Pump curve displays correctly with operating point marked
- Tables show all solved values with proper units
- Results update when project is re-solved
- Loading state shows during API call

---

### Issue #15: Frontend - Create API Client

> ✅ **COMPLETED** - [GitHub Issue #23](https://github.com/ccirone2/opensolve-pipe/issues/23)

**Labels:** `frontend`, `api`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create API client for communicating with backend.

**Related Files:**

- `apps/web/src/lib/api/client.ts`

**Tasks:**

- [ ] Create `solveNetwork(project: Project): Promise<SolvedState>` function
- [ ] Create `getFluidProperties(fluidId, temperature)` function
- [ ] Create `listFluids()` function
- [ ] Add error handling for network failures
- [ ] Add retry logic for transient failures
- [ ] Add request timeout handling
- [ ] Configure API base URL from environment variable
- [ ] Write tests with mocked fetch

**Acceptance Criteria:**

- API calls succeed with valid data
- Network errors are caught and handled gracefully
- Environment variable controls backend URL

---

### Issue #16: Frontend - Implement "Solve" Button and Workflow

> ✅ **COMPLETED** - [GitHub Issue #24](https://github.com/ccirone2/opensolve-pipe/issues/24)

**Labels:** `frontend`, `integration`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Connect the UI to the backend solver via the "Solve" button.

**Related Files:**

- `apps/web/src/routes/+page.svelte`

**Tasks:**

- [ ] Add "Solve" button to header
- [ ] Implement solve workflow (get project → call API → update results)
- [ ] Show loading spinner during solve
- [ ] Display success message with solve time
- [ ] Display error message on failure
- [ ] Disable solve button if project invalid
- [ ] Add keyboard shortcut (Ctrl+Enter)
- [ ] Update URL after successful solve

**Acceptance Criteria:**

- Clicking "Solve" sends project to backend
- Results display after successful solve
- Errors display with helpful messages
- Loading state prevents multiple simultaneous solves

---

### Issue #17: End-to-End Testing and Bug Fixes

> ✅ **COMPLETED** - [GitHub Issue #25](https://github.com/ccirone2/opensolve-pipe/issues/25)

**Labels:** `testing`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Comprehensive testing of the complete workflow from project creation to solved results.

**Tasks:**

- [ ] Create test project: Reservoir → Pump → 100ft pipe → Tank
- [ ] Test project creation via panel navigator
- [ ] Test URL encoding/decoding roundtrip
- [ ] Test solve workflow end-to-end
- [ ] Verify results are physically reasonable
- [ ] Test on mobile device (iPhone, Android)
- [ ] Test on different browsers (Chrome, Firefox, Safari)
- [ ] Compare results to EPANET or hand calculations
- [ ] Document any discrepancies or bugs
- [ ] Fix critical bugs blocking MVP launch

**Acceptance Criteria:**

- Test project solves successfully
- Results match expected values (< 1% error)
- No critical bugs remain
- Works on mobile and desktop browsers

---

### Issue #18: Deployment Setup (Frontend + Backend)

> ✅ **COMPLETED** - [GitHub Issue #26](https://github.com/ccirone2/opensolve-pipe/issues/26)

**Labels:** `deployment`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Deploy frontend to Vercel and backend to Railway (or Fly.io).

**Tasks:**

- [ ] Create Vercel project for frontend
- [ ] Configure build settings for SvelteKit
- [ ] Set up environment variables (PUBLIC_API_URL)
- [ ] Create Railway project for backend
- [ ] Configure Dockerfile for FastAPI app
- [ ] Set up environment variables (CORS_ORIGINS)
- [ ] Configure custom domain (optional)
- [ ] Set up HTTPS for both services
- [ ] Test deployed application end-to-end
- [ ] Add health check monitoring

**Acceptance Criteria:**

- Frontend accessible at public URL
- Backend API accessible and CORS configured
- Deployed app works identically to local
- HTTPS enabled on both services

---

### Issue #19: Documentation and Landing Page

> ✅ **COMPLETED** - [GitHub Issue #27](https://github.com/ccirone2/opensolve-pipe/issues/27)

**Labels:** `documentation`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create user-facing documentation and landing page.

**Tasks:**

- [ ] Create landing page with project description
- [ ] Add "Getting Started" tutorial
- [ ] Document component types and properties
- [ ] Add example projects (simple pump system)
- [ ] Create FAQ section
- [ ] Add "About" page with methodology
- [ ] Document limitations (single-path only in MVP)
- [ ] Add link to GitHub repository
- [ ] Add changelog/release notes

**Acceptance Criteria:**

- Landing page is clear and professional
- Tutorial walks users through first solve
- Documentation answers common questions
- Example projects load and solve correctly

---

### Issue #20: Backend - Port-Based Architecture

> 📋 **NOT STARTED** - [GitHub Issue #58](https://github.com/ccirone2/opensolve-pipe/issues/58)

**Labels:** `backend`, `architecture`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Implement the port-based connection architecture that enables components with variable numbers of connection points.

**Related Files:**

- `apps/api/src/opensolve_pipe/models/ports.py`
- `apps/api/src/opensolve_pipe/models/connections.py`

**Tasks:**

- [ ] Define `Port` model (id, nominal_size, direction: inlet/outlet/bidirectional)
- [ ] Define `PortDirection` enum
- [ ] Define `PipeConnection` model (from/to component and port IDs)
- [ ] Update `BaseComponent` to include `ports` field
- [ ] Add port factory functions for each component type
- [ ] Update `PipingSegment` to support multiple pipe segments in series
- [ ] Add validation for port connections (size compatibility)
- [ ] Add validation for port direction (inlet → outlet)
- [ ] Update Project model to use `PipeConnection` list
- [ ] Migrate existing `downstream_connections` to new model
- [ ] Write unit tests for port-based topology validation
- [ ] Write tests for connection validation rules

**Acceptance Criteria:**

- All components have explicit port definitions
- Pipe connections reference specific ports
- Port size validation catches mismatched connections
- Existing tests continue to pass with new model

**Dependencies:** Issue #2 (Data Models)

---

### Issue #21: Backend - Reference Node and Plug Components

> 📋 **NOT STARTED** - [GitHub Issue #59](https://github.com/ccirone2/opensolve-pipe/issues/59)

**Labels:** `backend`, `components`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Implement Reference Node and Plug/Cap components for defining boundary conditions in the network.

**Related Files:**

- `apps/api/src/opensolve_pipe/models/reference_node.py`
- `apps/api/src/opensolve_pipe/models/plug.py`
- `apps/api/src/opensolve_pipe/services/solver/reference.py`

**Tasks:**

Reference Node:

- [ ] Define `ReferenceNode` base model with single port
- [ ] Define `IdealReferenceNode` model (fixed pressure boundary)
- [ ] Define `NonIdealReferenceNode` model (pressure-flow curve)
- [ ] Define `FlowPressurePoint` model for curve data
- [ ] Add reference node to component type discriminator
- [ ] Implement ideal reference node handling in simple solver
- [ ] Implement non-ideal reference node interpolation
- [ ] Add reference node to WNTR adapter for network solver
- [ ] Write tests comparing ideal vs reservoir results
- [ ] Write tests for non-ideal pressure-flow curve behavior

Plug/Cap:

- [ ] Define `Plug` model with single port (zero flow boundary)
- [ ] Add plug to component type discriminator
- [ ] Implement plug handling in simple solver (enforces Q=0)
- [ ] Add plug to WNTR adapter for network solver
- [ ] Write tests for plug zero-flow enforcement
- [ ] Create frontend form for plug configuration

**Acceptance Criteria:**

- Ideal reference node produces same results as reservoir at same pressure
- Non-ideal reference node correctly interpolates pressure at given flow
- Reference nodes work with both simple and network solvers
- Maximum flow limits are enforced for non-ideal nodes
- Plug enforces zero flow at connected port
- Plug correctly calculates pressure at dead-end

**Dependencies:** Issue #20 (Port-Based Architecture)

**Hydraulic Notes:**

- Ideal reference node = infinite reservoir (constant pressure regardless of flow)
- Non-ideal reference node = pressure regulator with capacity curve
- Plug/Cap = dead end with zero flow (pressure calculated from network)
- Use at system boundaries where pressure is known or flow is zero

---

### Issue #22: Backend - Branch Component (Tee/Wye/Cross)

> 📋 **NOT STARTED** - [GitHub Issue #60](https://github.com/ccirone2/opensolve-pipe/issues/60)

**Labels:** `backend`, `components`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Implement Branch components for flow splitting/combining with proper K-factor calculations.

**Related Files:**

- `apps/api/src/opensolve_pipe/models/branch.py`
- `apps/api/src/opensolve_pipe/data/branch_k_factors.json`
- `apps/api/src/opensolve_pipe/services/solver/branch.py`

**Tasks:**

- [ ] Define `Branch` base model with variable ports
- [ ] Define `TeeBranch` model (3 ports: run_inlet, run_outlet, branch)
- [ ] Define `WyeBranch` model (3 ports with configurable angle)
- [ ] Define `CrossBranch` model (4 ports)
- [ ] Define `ElbowBranch` model (3 ports: main elbow + branch)
- [ ] Create `branch_k_factors.json` with Crane TP-410 data
- [ ] Implement K-factor calculation for diverging flow (tee)
- [ ] Implement K-factor calculation for converging flow (tee)
- [ ] Handle reduced-size branch ports in K-factor calculation
- [ ] Add branch to component type discriminator
- [ ] Implement branch handling in simple solver (single branch path)
- [ ] Add branch to WNTR adapter for network solver
- [ ] Write tests for K-factor calculations vs Crane TP-410 tables
- [ ] Write tests for different flow configurations

**Acceptance Criteria:**

- K-factors match Crane TP-410 within 5%
- Reduced-size branches calculate correct K adjustment
- Flow direction (diverging/converging) is automatically detected
- Branch works with both simple and network solvers

**Dependencies:** Issue #20 (Port-Based Architecture)

**Hydraulic Reference:**

- Crane TP-410, Chapter 4: Flow Through Fittings
- K_branch = 60 × f_T for tee branch flow
- K_run = 20 × f_T for tee through flow
- Branch size reduction increases K by factor of (D_run/D_branch)^4

---

### Issue #23: Frontend - Port Connection Editor

> 📋 **NOT STARTED** - [GitHub Issue #61](https://github.com/ccirone2/opensolve-pipe/issues/61)

**Labels:** `frontend`, `ui`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create UI for managing port-based connections between components.

**Related Files:**

- `apps/web/src/lib/components/panel/PortConnectionEditor.svelte`
- `apps/web/src/lib/components/panel/PortSelector.svelte`
- `apps/web/src/lib/stores/connections.ts`

**Tasks:**

- [ ] Create `PortSelector` component (dropdown of available ports)
- [ ] Create `PortConnectionEditor` component (manage connection between two ports)
- [ ] Display port sizes and directions in selector
- [ ] Show connection validation errors (size mismatch, direction mismatch)
- [ ] Update `PipingPanel` to work with port-based connections
- [ ] Add "Add Connection" button for components with available ports
- [ ] Show visual indicator for connected vs unconnected ports
- [ ] Update project store to manage `PipeConnection` objects
- [ ] Write tests for connection editor interactions

**Acceptance Criteria:**

- Users can select source and target ports for connections
- Invalid connections (size mismatch) show clear errors
- All available ports are visible in the selector
- Connection state updates correctly in the store

**Dependencies:** Issue #20 (Backend Port Architecture), Issue #10 (Frontend State Management)

---

### Issue #24: Frontend - Reference Node Form

> 📋 **NOT STARTED** - [GitHub Issue #62](https://github.com/ccirone2/opensolve-pipe/issues/62)

**Labels:** `frontend`, `forms`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create form components for configuring Reference Node components.

**Related Files:**

- `apps/web/src/lib/components/forms/ReferenceNodeForm.svelte`
- `apps/web/src/lib/components/forms/PressureFlowCurveEditor.svelte`

**Tasks:**

- [ ] Create `ReferenceNodeForm` component
- [ ] Add reference type selector (ideal vs non-ideal)
- [ ] Add elevation input
- [ ] Add pressure input for ideal reference node
- [ ] Create `PressureFlowCurveEditor` for non-ideal reference node
- [ ] Add curve point table (flow, pressure pairs)
- [ ] Add curve visualization (simple line chart)
- [ ] Add port size configuration
- [ ] Add validation for curve data (monotonic, positive values)
- [ ] Write tests for form validation

**Acceptance Criteria:**

- Ideal reference node can be configured with fixed pressure
- Non-ideal reference node curve can be entered and visualized
- Form validation prevents invalid configurations
- Port size can be set independently

**Dependencies:** Issue #21 (Backend Reference Node), Issue #13 (Component Forms)

---

### Issue #25: Frontend - Branch Component Forms

> 📋 **NOT STARTED** - [GitHub Issue #63](https://github.com/ccirone2/opensolve-pipe/issues/63)

**Labels:** `frontend`, `forms`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create form components for configuring Branch components (tee, wye, cross).

**Related Files:**

- `apps/web/src/lib/components/forms/BranchForm.svelte`
- `apps/web/src/lib/components/forms/TeeForm.svelte`
- `apps/web/src/lib/components/forms/WyeForm.svelte`
- `apps/web/src/lib/components/forms/CrossForm.svelte`

**Tasks:**

- [ ] Create `BranchForm` base component with type selector
- [ ] Create `TeeForm` with orientation selector (through/diverging/converging)
- [ ] Create `WyeForm` with angle input
- [ ] Create `CrossForm` for 4-way intersections
- [ ] Add port size configuration for each port
- [ ] Support reduced-size branch ports
- [ ] Add visual diagram showing port arrangement
- [ ] Add validation for port sizes (branch ≤ run for tees)
- [ ] Write tests for form validation

**Acceptance Criteria:**

- All branch types can be configured
- Port sizes can be set independently
- Visual diagram helps users understand port arrangement
- Reduced-size branches are properly supported

**Dependencies:** Issue #22 (Backend Branch Component), Issue #13 (Component Forms)

---

## Automated Creation (gh CLI Commands)

Run these commands to automatically create all Phase 1 issues:

```bash
# Issue #1: Project Setup
gh issue create \
  --title "Project Setup and Repository Structure" \
  --body "Set up the monorepo structure and install core dependencies for both frontend and backend.

**Tasks:**
- [x] Create \`apps/web/\` directory structure for SvelteKit frontend
- [x] Create \`apps/api/\` directory structure for FastAPI backend
- [x] Initialize SvelteKit project with TypeScript
- [x] Initialize FastAPI project with pyproject.toml
- [x] Install backend dependencies: \`fastapi\`, \`uvicorn\`, \`pydantic\`, \`fluids\`, \`scipy\`
- [x] Install frontend dependencies: \`pako\`, \`tailwindcss\`, \`chart.js\`
- [x] Set up ESLint and Prettier for frontend
- [x] Set up Ruff for backend (replaces Black and isort)
- [x] Create \`.gitignore\` for both apps
- [x] Add README.md with setup instructions
- [x] Verify both apps run locally (\`pnpm dev\` and \`uvicorn\`)

**Acceptance Criteria:**
- Frontend runs on \`localhost:5173\`
- Backend runs on \`localhost:8000\`
- Both apps have working hot reload" \
  --label "setup,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #2: Backend Data Models
gh issue create \
  --title "Backend - Define Pydantic Data Models" \
  --body "Create Pydantic models for all core data structures: Project, Component, Piping, and SolvedState.

**Related Files:**
- \`apps/api/src/opensolve_pipe/models/project.py\`
- \`apps/api/src/opensolve_pipe/models/components.py\`
- \`apps/api/src/opensolve_pipe/models/results.py\`

**Tasks:**
- [ ] Define \`Project\` model (metadata, settings, fluid, components, results)
- [ ] Define \`ProjectMetadata\` model
- [ ] Define \`ProjectSettings\` model (units, solver options)
- [ ] Define \`Component\` base model with type discriminator
- [ ] Define \`Reservoir\`, \`Tank\`, \`Junction\` component models
- [ ] Define \`Pump\` model with \`PumpCurve\`
- [ ] Define \`PipingSegment\` model (pipe + fittings)
- [ ] Define \`PipeDefinition\` and \`Fitting\` models
- [ ] Define \`SolvedState\` output model
- [ ] Define \`NodeResult\` and \`LinkResult\` models
- [ ] Define \`PumpResult\` model
- [ ] Add validation rules (positive values, required fields)
- [ ] Write unit tests for model validation

**Acceptance Criteria:**
- All models serialize to/from JSON correctly
- Invalid data raises \`ValidationError\`
- Models match TypeScript interfaces in TSD" \
  --label "backend,models,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #3: Data Libraries
gh issue create \
  --title "Backend - Create Pipe Materials and Fittings Data Libraries" \
  --body "Create JSON data files for pipe materials and fittings with lookup services.

**Related Files:**
- \`apps/api/src/opensolve_pipe/data/pipe_materials.json\`
- \`apps/api/src/opensolve_pipe/data/fittings.json\`
- \`apps/api/src/opensolve_pipe/data/fluids.json\`
- \`apps/api/src/opensolve_pipe/services/data.py\`

**Tasks:**
- [ ] Create \`pipe_materials.json\` with carbon steel, stainless steel, PVC (Schedule 40/80)
- [ ] Include nominal sizes 2\", 2.5\", 3\", 4\", 6\", 8\" with ID/OD/wall thickness
- [ ] Create \`fittings.json\` with elbows (90°, 45°), tees, valves (Crane TP-410 K-factors)
- [ ] Create \`fluids.json\` with water properties (temperature-dependent)
- [ ] Implement \`get_pipe_material()\` service function
- [ ] Implement \`get_fitting_k_factor()\` service function
- [ ] Implement \`get_fluid_properties()\` service function
- [ ] Add error handling for missing materials/fittings
- [ ] Write tests for data lookup functions

**Acceptance Criteria:**
- All data files validate as proper JSON
- Service functions return correct data
- Missing items raise appropriate errors" \
  --label "backend,data,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #4: Fluid Properties Service
gh issue create \
  --title "Backend - Implement Fluid Properties Service" \
  --body "Create service for calculating fluid properties using the \`fluids\` library.

**Related Files:**
- \`apps/api/src/opensolve_pipe/services/fluids.py\`
- \`apps/api/src/opensolve_pipe/models/fluids.py\`

**Tasks:**
- [ ] Define \`FluidProperties\` model (density, viscosity, vapor pressure)
- [ ] Implement water properties calculation at given temperature
- [ ] Add temperature unit conversion (F, C, K)
- [ ] Handle out-of-range temperatures gracefully
- [ ] Write tests comparing results to known values
- [ ] Add docstrings with example usage

**Acceptance Criteria:**
- Water at 68°F returns correct density (~62.32 lb/ft³)
- Properties are consistent with \`fluids\` library
- Unit conversions work correctly" \
  --label "backend,fluids,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #5: Simple Solver (CRITICAL)
gh issue create \
  --title "Backend - Implement Simple Solver (Core Hydraulic Calculations)" \
  --body "Implement the simple solver for single-path networks (no branches). This is the core hydraulic calculation engine.

**Related Files:**
- \`apps/api/src/opensolve_pipe/services/solver/simple.py\`
- \`apps/api/src/opensolve_pipe/services/solver/k_factors.py\`

**Tasks:**
- [ ] Implement Darcy-Weisbach friction factor calculation (Colebrook equation)
- [ ] Implement pipe head loss calculation (friction + minor losses)
- [ ] Implement K-factor resolution for fittings (L/D method)
- [ ] Create system curve generator (head loss vs flow)
- [ ] Implement pump curve interpolator (cubic spline)
- [ ] Implement operating point finder (curve intersection with scipy.optimize)
- [ ] Calculate node pressures, velocities, Reynolds numbers
- [ ] Calculate NPSH available at pump suction
- [ ] Add convergence detection and iteration limits
- [ ] Write comprehensive tests with known solutions

**Acceptance Criteria:**
- Simple pump-pipe-tank system solves correctly
- Results match hand calculations (< 1% error)
- Solver converges in < 100 iterations
- Non-converged cases return clear error messages

**Reference:**
- Crane TP-410 for K-factors
- Darcy-Weisbach equation: \`h_f = f × (L/D) × (v²/2g)\`" \
  --label "backend,solver,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #6: Unit Conversion
gh issue create \
  --title "Backend - Implement Unit Conversion System" \
  --body "Create a comprehensive unit conversion system for all physical quantities.

**Related Files:**
- \`apps/api/src/opensolve_pipe/utils/units.py\`

**Tasks:**
- [ ] Define \`UnitCategory\` enum (length, pressure, flow, velocity, etc.)
- [ ] Create conversion factors dictionary (to SI base units)
- [ ] Implement \`convert(value, from_unit, to_unit)\` function
- [ ] Add validation for compatible unit categories
- [ ] Define \`UnitPreferences\` model
- [ ] Write tests for all conversion pairs
- [ ] Add temperature conversions (with offset handling)

**Acceptance Criteria:**
- All common conversions work correctly (psi ↔ kPa, GPM ↔ L/s, etc.)
- Incompatible conversions raise \`ValueError\`
- Temperature conversions handle offsets correctly" \
  --label "backend,utilities,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #7: API Endpoints (CRITICAL)
gh issue create \
  --title "Backend - Create API Endpoints (Solve, Fluids)" \
  --body "Implement FastAPI endpoints for solving networks and querying fluid properties.

**Related Files:**
- \`apps/api/src/opensolve_pipe/main.py\`
- \`apps/api/src/opensolve_pipe/routers/solve.py\`
- \`apps/api/src/opensolve_pipe/routers/fluids.py\`

**Tasks:**
- [ ] Create FastAPI app with CORS middleware
- [ ] Implement \`POST /api/v1/solve\` endpoint
- [ ] Implement \`GET /api/v1/fluids\` endpoint (list available fluids)
- [ ] Implement \`GET /api/v1/fluids/{fluid_id}/properties\` endpoint
- [ ] Add request validation (Pydantic models)
- [ ] Add response models for type safety
- [ ] Implement error handling (validation errors, solver failures)
- [ ] Add health check endpoint (\`GET /health\`)
- [ ] Write API tests (pytest + httpx)
- [ ] Document endpoints with OpenAPI docstrings

**Acceptance Criteria:**
- \`/api/v1/solve\` accepts Project and returns SolvedState
- Fluid endpoints return correct properties
- Invalid requests return 400/422 with clear error messages
- OpenAPI docs accessible at \`/docs\`" \
  --label "backend,api,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #8: Frontend Setup
gh issue create \
  --title "Frontend - Setup SvelteKit Project and Routing" \
  --body "Initialize SvelteKit with TypeScript, Tailwind CSS, and basic routing.

**Related Files:**
- \`apps/web/src/routes/+page.svelte\`
- \`apps/web/src/routes/p/[...encoded]/+page.svelte\`
- \`apps/web/src/app.html\`
- \`apps/web/tailwind.config.js\`

**Tasks:**
- [ ] Configure Tailwind CSS with custom design tokens
- [ ] Create main landing page (\`/\`)
- [ ] Create project viewer route (\`/p/{encoded}\`)
- [ ] Set up routing with SvelteKit
- [ ] Add responsive mobile-first layout
- [ ] Create basic header component with project name
- [ ] Add view mode switcher (panel / results)
- [ ] Test routing on mobile and desktop

**Acceptance Criteria:**
- Tailwind classes work correctly
- Routes navigate properly
- Responsive design works on mobile (< 768px)" \
  --label "frontend,setup,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #9: Frontend TypeScript Interfaces
gh issue create \
  --title "Frontend - Define TypeScript Interfaces (Data Models)" \
  --body "Create TypeScript interfaces matching backend Pydantic models.

**Related Files:**
- \`apps/web/src/lib/models/project.ts\`
- \`apps/web/src/lib/models/components.ts\`
- \`apps/web/src/lib/models/results.ts\`

**Tasks:**
- [ ] Define \`Project\` interface
- [ ] Define component interfaces (Reservoir, Tank, Junction, Pump)
- [ ] Define \`PipingSegment\`, \`PipeDefinition\`, \`Fitting\` interfaces
- [ ] Define \`SolvedState\` and result interfaces
- [ ] Add type guards for component discrimination
- [ ] Export all types from index file
- [ ] Verify alignment with backend models

**Acceptance Criteria:**
- All interfaces compile without errors
- Type guards work correctly for component types
- Interfaces match backend Pydantic models" \
  --label "frontend,models,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #10: Project State Management (CRITICAL)
gh issue create \
  --title "Frontend - Implement Project State Management (Svelte Stores)" \
  --body "Create Svelte stores for managing project state, including component chain and navigation.

**Related Files:**
- \`apps/web/src/lib/stores/project.ts\`
- \`apps/web/src/lib/stores/navigation.ts\`

**Tasks:**
- [ ] Create \`projectStore\` (writable store for Project)
- [ ] Add methods: \`addComponent()\`, \`removeComponent()\`, \`updateComponent()\`
- [ ] Create \`currentElementId\` store for navigation
- [ ] Create \`navigationPath\` derived store (breadcrumb trail)
- [ ] Implement undo/redo with history stack
- [ ] Add \`solvedState\` store for results
- [ ] Write tests for store actions
- [ ] Add local storage persistence (optional MVP enhancement)

**Acceptance Criteria:**
- Components can be added/removed/edited
- Navigation state updates correctly
- Undo/redo works for all actions
- Store updates trigger UI re-renders" \
  --label "frontend,state,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #11: URL Encoding (CRITICAL)
gh issue create \
  --title "Frontend - Implement URL Encoding/Decoding" \
  --body "Implement project serialization to URL-safe compressed format.

**Related Files:**
- \`apps/web/src/lib/utils/encoding.ts\`

**Tasks:**
- [ ] Install \`pako\` library (gzip compression)
- [ ] Implement \`encodeProject(project: Project): string\` function
- [ ] Implement \`decodeProject(encoded: string): Project\` function
- [ ] Add error handling for corrupt/invalid URLs
- [ ] Implement size threshold detection (warn if > 2KB)
- [ ] Add compression level optimization
- [ ] Write roundtrip tests (encode → decode should equal original)
- [ ] Test with various project sizes

**Acceptance Criteria:**
- Empty project encodes to short string (< 200 chars)
- Medium project (5 components) encodes to < 2KB
- Roundtrip preserves all data
- Invalid URLs throw descriptive errors

**Reference:**
- Encoding pipeline: JSON → gzip → base64url" \
  --label "frontend,encoding,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #12: Panel Navigator UI (CRITICAL)
gh issue create \
  --title "Frontend - Build Panel Navigator UI" \
  --body "Create the primary UI for building and editing the hydraulic network element-by-element.

**Related Files:**
- \`apps/web/src/lib/components/panel/PanelNavigator.svelte\`
- \`apps/web/src/lib/components/panel/ElementPanel.svelte\`
- \`apps/web/src/lib/components/panel/PipingPanel.svelte\`
- \`apps/web/src/lib/components/panel/NavigationControls.svelte\`

**Tasks:**
- [ ] Create \`PanelNavigator\` component (main container)
- [ ] Create \`ElementPanel\` with property forms
- [ ] Create \`PipingPanel\` for pipe and fittings configuration
- [ ] Create \`NavigationControls\` (prev/next buttons)
- [ ] Add breadcrumb navigation trail
- [ ] Implement element type selector for adding new elements
- [ ] Add tab switcher (Element / Upstream / Downstream)
- [ ] Style with Tailwind CSS (mobile-first)
- [ ] Add keyboard navigation support (arrow keys)

**Acceptance Criteria:**
- Users can navigate through component chain
- Users can edit component properties
- Users can add/remove components
- UI is responsive on mobile devices
- Navigation feels intuitive" \
  --label "frontend,ui,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #13: Component Forms
gh issue create \
  --title "Frontend - Build Component Property Forms" \
  --body "Create forms for editing properties of each component type.

**Related Files:**
- \`apps/web/src/lib/components/forms/ReservoirForm.svelte\`
- \`apps/web/src/lib/components/forms/TankForm.svelte\`
- \`apps/web/src/lib/components/forms/PumpForm.svelte\`
- \`apps/web/src/lib/components/forms/PipeForm.svelte\`
- \`apps/web/src/lib/components/forms/FittingsTable.svelte\`

**Tasks:**
- [ ] Create \`ReservoirForm\` (elevation, water level)
- [ ] Create \`TankForm\` (elevation, dimensions, levels)
- [ ] Create \`PumpForm\` with curve entry table
- [ ] Create \`PipeForm\` (material selector, schedule, diameter, length)
- [ ] Create \`FittingsTable\` (add/remove/edit fittings with quantity)
- [ ] Add unit display and inline unit conversion
- [ ] Add form validation (positive numbers, required fields)
- [ ] Add number input with sensible min/max ranges

**Acceptance Criteria:**
- All component types can be fully configured
- Form validation prevents invalid inputs
- Unit labels display correctly
- Forms work on mobile touch screens" \
  --label "frontend,forms,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #14: Results Display (CRITICAL)
gh issue create \
  --title "Frontend - Build Results Display Components" \
  --body "Create components for displaying solved network results, including pump curve visualization.

**Related Files:**
- \`apps/web/src/lib/components/results/ResultsPanel.svelte\`
- \`apps/web/src/lib/components/results/PumpCurveChart.svelte\`
- \`apps/web/src/lib/components/results/NodeTable.svelte\`
- \`apps/web/src/lib/components/results/LinkTable.svelte\`

**Tasks:**
- [ ] Create \`ResultsPanel\` component (main container)
- [ ] Create \`PumpCurveChart\` using Chart.js (pump + system curves)
- [ ] Create \`NodeTable\` showing pressures, HGL, EGL for all nodes
- [ ] Create \`LinkTable\` showing flows, velocities, head loss for all links
- [ ] Add operating point indicator on pump curve
- [ ] Display convergence status (success/failure)
- [ ] Handle non-converged results with error messages
- [ ] Add loading state during solve
- [ ] Make tables scrollable on mobile

**Acceptance Criteria:**
- Pump curve displays correctly with operating point marked
- Tables show all solved values with proper units
- Results update when project is re-solved
- Loading state shows during API call" \
  --label "frontend,visualization,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #15: API Client
gh issue create \
  --title "Frontend - Create API Client" \
  --body "Create API client for communicating with backend.

**Related Files:**
- \`apps/web/src/lib/api/client.ts\`

**Tasks:**
- [ ] Create \`solveNetwork(project: Project): Promise<SolvedState>\` function
- [ ] Create \`getFluidProperties(fluidId, temperature)\` function
- [ ] Create \`listFluids()\` function
- [ ] Add error handling for network failures
- [ ] Add retry logic for transient failures
- [ ] Add request timeout handling
- [ ] Configure API base URL from environment variable
- [ ] Write tests with mocked fetch

**Acceptance Criteria:**
- API calls succeed with valid data
- Network errors are caught and handled gracefully
- Environment variable controls backend URL" \
  --label "frontend,api,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #16: Solve Button (CRITICAL)
gh issue create \
  --title "Frontend - Implement \"Solve\" Button and Workflow" \
  --body "Connect the UI to the backend solver via the \"Solve\" button.

**Related Files:**
- \`apps/web/src/routes/+page.svelte\`

**Tasks:**
- [ ] Add \"Solve\" button to header
- [ ] Implement solve workflow (get project → call API → update results)
- [ ] Show loading spinner during solve
- [ ] Display success message with solve time
- [ ] Display error message on failure
- [ ] Disable solve button if project invalid
- [ ] Add keyboard shortcut (Ctrl+Enter)
- [ ] Update URL after successful solve

**Acceptance Criteria:**
- Clicking \"Solve\" sends project to backend
- Results display after successful solve
- Errors display with helpful messages
- Loading state prevents multiple simultaneous solves" \
  --label "frontend,integration,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #17: End-to-End Testing (CRITICAL)
gh issue create \
  --title "End-to-End Testing and Bug Fixes" \
  --body "Comprehensive testing of the complete workflow from project creation to solved results.

**Tasks:**
- [ ] Create test project: Reservoir → Pump → 100ft pipe → Tank
- [ ] Test project creation via panel navigator
- [ ] Test URL encoding/decoding roundtrip
- [ ] Test solve workflow end-to-end
- [ ] Verify results are physically reasonable
- [ ] Test on mobile device (iPhone, Android)
- [ ] Test on different browsers (Chrome, Firefox, Safari)
- [ ] Compare results to EPANET or hand calculations
- [ ] Document any discrepancies or bugs
- [ ] Fix critical bugs blocking MVP launch

**Acceptance Criteria:**
- Test project solves successfully
- Results match expected values (< 1% error)
- No critical bugs remain
- Works on mobile and desktop browsers" \
  --label "testing,Phase 1,critical" \
  --milestone "Phase 1 - MVP"

# Issue #18: Deployment
gh issue create \
  --title "Deployment Setup (Frontend + Backend)" \
  --body "Deploy frontend to Vercel and backend to Railway (or Fly.io).

**Tasks:**
- [ ] Create Vercel project for frontend
- [ ] Configure build settings for SvelteKit
- [ ] Set up environment variables (PUBLIC_API_URL)
- [ ] Create Railway project for backend
- [ ] Configure Dockerfile for FastAPI app
- [ ] Set up environment variables (CORS_ORIGINS)
- [ ] Configure custom domain (optional)
- [ ] Set up HTTPS for both services
- [ ] Test deployed application end-to-end
- [ ] Add health check monitoring

**Acceptance Criteria:**
- Frontend accessible at public URL
- Backend API accessible and CORS configured
- Deployed app works identically to local
- HTTPS enabled on both services" \
  --label "deployment,Phase 1" \
  --milestone "Phase 1 - MVP"

# Issue #19: Documentation
gh issue create \
  --title "Documentation and Landing Page" \
  --body "Create user-facing documentation and landing page.

**Tasks:**
- [ ] Create landing page with project description
- [ ] Add \"Getting Started\" tutorial
- [ ] Document component types and properties
- [ ] Add example projects (simple pump system)
- [ ] Create FAQ section
- [ ] Add \"About\" page with methodology
- [ ] Document limitations (single-path only in MVP)
- [ ] Add link to GitHub repository
- [ ] Add changelog/release notes

**Acceptance Criteria:**
- Landing page is clear and professional
- Tutorial walks users through first solve
- Documentation answers common questions
- Example projects load and solve correctly" \
  --label "documentation,Phase 1" \
  --milestone "Phase 1 - MVP"

echo "✅ All Phase 1 issues created!"
```

---

## Summary

**Total Phase 1 Issues:** 25

**Critical Path (10 issues):**

1. #1 - Project Setup
2. #2 - Backend Data Models
3. #5 - Simple Solver
4. #7 - API Endpoints
5. #10 - Frontend State Management
6. #12 - Panel Navigator UI
7. #14 - Results Display
8. #20 - Port-Based Architecture
9. #22 - Branch Component
10. #23 - Port Connection Editor

**Estimated Effort:** 4-5 weeks with 2-3 developers (increased due to port-based architecture)

**Architecture Notes:**

- Issues #20-25 implement the port-based connection architecture
- This enables components with variable numbers of connection ports
- Branch components replace inline tee fittings for better hydraulic accuracy
- Reference nodes provide flexible pressure boundary conditions

**Next Steps:**

1. Create the "Phase 1 - MVP" milestone in GitHub
2. Create all issues using either manual or automated method
3. Assign issues to team members based on expertise
4. Begin development with Issue #1

---

**Note:** Remember to create the "Phase 1 - MVP" milestone in GitHub before running the gh CLI commands, or the commands will fail.
