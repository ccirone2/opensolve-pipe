# Phase 1 GitHub Issues

This document contains all GitHub issues for Phase 1 (MVP) of OpenSolve Pipe.

**Choose your format:**
- [Manual Creation (Markdown Checklist)](#manual-creation-markdown-checklist)
- [Automated Creation (gh CLI Commands)](#automated-creation-gh-cli-commands)

---

## Manual Creation (Markdown Checklist)

Copy each issue below and create it manually in GitHub Issues.

---

### Issue #1: Project Setup and Repository Structure

**Labels:** `setup`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Set up the monorepo structure and install core dependencies for both frontend and backend.

**Tasks:**
- [ ] Create `apps/web/` directory structure for SvelteKit frontend
- [ ] Create `apps/api/` directory structure for FastAPI backend
- [ ] Initialize SvelteKit project with TypeScript
- [ ] Initialize FastAPI project with pyproject.toml
- [ ] Install backend dependencies: `fastapi`, `uvicorn`, `pydantic`, `fluids`, `scipy`
- [ ] Install frontend dependencies: `pako`, `tailwindcss`, `chart.js`
- [ ] Set up ESLint and Prettier for frontend
- [ ] Set up Black and isort for backend
- [ ] Create `.gitignore` for both apps
- [ ] Add README.md with setup instructions
- [ ] Verify both apps run locally (`npm run dev` and `uvicorn`)

**Acceptance Criteria:**
- Frontend runs on `localhost:5173`
- Backend runs on `localhost:8000`
- Both apps have working hot reload

---

### Issue #2: Backend - Define Pydantic Data Models

**Labels:** `backend`, `models`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create Pydantic models for all core data structures: Project, Component, Piping, and SolvedState.

**Related Files:**
- `apps/api/src/opensolve_pipe/models/project.py`
- `apps/api/src/opensolve_pipe/models/components.py`
- `apps/api/src/opensolve_pipe/models/results.py`

**Tasks:**
- [ ] Define `Project` model (metadata, settings, fluid, components, results)
- [ ] Define `ProjectMetadata` model
- [ ] Define `ProjectSettings` model (units, solver options)
- [ ] Define `Component` base model with type discriminator
- [ ] Define `Reservoir`, `Tank`, `Junction` component models
- [ ] Define `Pump` model with `PumpCurve`
- [ ] Define `PipingSegment` model (pipe + fittings)
- [ ] Define `PipeDefinition` and `Fitting` models
- [ ] Define `SolvedState` output model
- [ ] Define `NodeResult` and `LinkResult` models
- [ ] Define `PumpResult` model
- [ ] Add validation rules (positive values, required fields)
- [ ] Write unit tests for model validation

**Acceptance Criteria:**
- All models serialize to/from JSON correctly
- Invalid data raises `ValidationError`
- Models match TypeScript interfaces in TSD

---

### Issue #3: Backend - Create Pipe Materials and Fittings Data Libraries

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
- [ ] Create `pipe_materials.json` with carbon steel, stainless steel, PVC (Schedule 40/80)
- [ ] Include nominal sizes 2", 2.5", 3", 4", 6", 8" with ID/OD/wall thickness
- [ ] Create `fittings.json` with elbows (90°, 45°), tees, valves (Crane TP-410 K-factors)
- [ ] Create `fluids.json` with water properties (temperature-dependent)
- [ ] Implement `get_pipe_material()` service function
- [ ] Implement `get_fitting_k_factor()` service function
- [ ] Implement `get_fluid_properties()` service function
- [ ] Add error handling for missing materials/fittings
- [ ] Write tests for data lookup functions

**Acceptance Criteria:**
- All data files validate as proper JSON
- Service functions return correct data
- Missing items raise appropriate errors

---

### Issue #4: Backend - Implement Fluid Properties Service

**Labels:** `backend`, `fluids`, `Phase 1`
**Milestone:** Phase 1 - MVP

**Description:**
Create service for calculating fluid properties using the `fluids` library.

**Related Files:**
- `apps/api/src/opensolve_pipe/services/fluids.py`
- `apps/api/src/opensolve_pipe/models/fluids.py`

**Tasks:**
- [ ] Define `FluidProperties` model (density, viscosity, vapor pressure)
- [ ] Implement water properties calculation at given temperature
- [ ] Add temperature unit conversion (F, C, K)
- [ ] Handle out-of-range temperatures gracefully
- [ ] Write tests comparing results to known values
- [ ] Add docstrings with example usage

**Acceptance Criteria:**
- Water at 68°F returns correct density (~62.32 lb/ft³)
- Properties are consistent with `fluids` library
- Unit conversions work correctly

---

### Issue #5: Backend - Implement Simple Solver (Core Hydraulic Calculations)

**Labels:** `backend`, `solver`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP

**Description:**
Implement the simple solver for single-path networks (no branches). This is the core hydraulic calculation engine.

**Related Files:**
- `apps/api/src/opensolve_pipe/services/solver/simple.py`
- `apps/api/src/opensolve_pipe/services/solver/k_factors.py`

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
- Darcy-Weisbach equation: `h_f = f × (L/D) × (v²/2g)`

---

### Issue #6: Backend - Implement Unit Conversion System

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

## Automated Creation (gh CLI Commands)

Run these commands to automatically create all Phase 1 issues:

```bash
# Issue #1: Project Setup
gh issue create \
  --title "Project Setup and Repository Structure" \
  --body "Set up the monorepo structure and install core dependencies for both frontend and backend.

**Tasks:**
- [ ] Create \`apps/web/\` directory structure for SvelteKit frontend
- [ ] Create \`apps/api/\` directory structure for FastAPI backend
- [ ] Initialize SvelteKit project with TypeScript
- [ ] Initialize FastAPI project with pyproject.toml
- [ ] Install backend dependencies: \`fastapi\`, \`uvicorn\`, \`pydantic\`, \`fluids\`, \`scipy\`
- [ ] Install frontend dependencies: \`pako\`, \`tailwindcss\`, \`chart.js\`
- [ ] Set up ESLint and Prettier for frontend
- [ ] Set up Black and isort for backend
- [ ] Create \`.gitignore\` for both apps
- [ ] Add README.md with setup instructions
- [ ] Verify both apps run locally (\`npm run dev\` and \`uvicorn\`)

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

**Total Phase 1 Issues:** 19

**Critical Path (7 issues):**
1. #1 - Project Setup
2. #2 - Backend Data Models
3. #5 - Simple Solver
4. #7 - API Endpoints
5. #10 - Frontend State Management
6. #12 - Panel Navigator UI
7. #14 - Results Display

**Estimated Effort:** 3-4 weeks with 2-3 developers

**Next Steps:**
1. Create the "Phase 1 - MVP" milestone in GitHub
2. Create all issues using either manual or automated method
3. Assign issues to team members based on expertise
4. Begin development with Issue #1

---

**Note:** Remember to create the "Phase 1 - MVP" milestone in GitHub before running the gh CLI commands, or the commands will fail.
