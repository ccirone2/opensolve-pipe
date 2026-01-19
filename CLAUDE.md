# OpenSolve Pipe - Claude Context Guide

**Quick Summary:** Free, browser-based hydraulic network design tool for steady-state pipe flow analysis. No installation, shareable via URL, works on desktop and mobile.

**Current Status:** 🚧 Planning phase - specifications complete, implementation not started

---

## Core Concept

OpenSolve Pipe democratizes access to professional-grade hydraulic analysis by:
- Running entirely in browser (no installation)
- Storing small projects in URL state (Git-like versioning via shareable links)
- Using a "component chain" data model that matches how engineers think
- Providing professional accuracy at zero cost

**Target Users:** Students, field technicians, maintenance engineers, process engineers, consulting engineers

---

## Key Architectural Decisions

### 1. Hybrid Client-Server Architecture
- **Client (SvelteKit):** UI, state management, URL encoding/decoding
- **Server (FastAPI):** Hydraulic solving, fluid properties, optional persistence
- **Why:** Maximize shareability and privacy while leveraging Python's hydraulic libraries

### 2. URL-Encoded State (< 50KB projects)
```
Project → JSON → gzip → base64url → https://opensolve-pipe.app/p/{encoded}
```
- No server storage for small projects
- True decentralization
- Zero account friction
- Git-like branching: every edit creates a new URL (copy-on-write)

### 3. Component Chain Data Model
```typescript
Project {
  components: Component[]  // Ordered list: Reservoir → Pump → Pipe → Junction → ...
  connections: Connection[] // How components link together
}
```
- Matches mental model: "walk through the system"
- Powers panel navigator UI (wizard-like element-by-element editing)
- Converts to WNTR/EPANET graph for solving

### 4. Solver Strategy
- **Simple networks** (no branches): Direct calculation using `fluids` library
- **Complex networks** (branching/looped): WNTR/EPANET wrapper
- Adapter pattern converts component chain → solver-specific format

### 5. Panel Navigator as Primary UI
```
┌─────────────────────┐
│ Element Properties  │  ← Edit current component
├─────────────────────┤
│ Upstream Piping     │  ← Fittings, pipe specs
│ Downstream Piping   │
├─────────────────────┤
│ [← Prev] [Next →]   │  ← Navigate chain
└─────────────────────┘
```
- Mobile-first interaction model
- Schematic is auto-generated (read-only visualization)
- Click schematic element → opens panel for that element

---

## Technology Stack

### Frontend
- **Framework:** SvelteKit (performance, bundle size)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **Charts:** Chart.js (pump curves) + D3.js (schematics)
- **State:** Svelte stores

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **Hydraulics:** `fluids` library, WNTR/EPANET
- **Validation:** Pydantic
- **Database:** PostgreSQL (optional, for projects > 50KB)

### Infrastructure
- **Frontend:** Vercel or Cloudflare Pages
- **Backend:** Railway, Fly.io, or AWS Lambda
- **Database:** Supabase or Railway

---

## Project Structure

```
opensolve-pipe/
├── apps/
│   ├── web/              # SvelteKit frontend
│   │   └── src/
│   │       ├── lib/components/
│   │       │   ├── panel/      # Panel navigator UI
│   │       │   ├── schematic/  # Auto-generated PFD
│   │       │   └── results/    # Solved state display
│   │       ├── stores/         # Svelte stores (project state)
│   │       ├── models/         # TypeScript interfaces
│   │       └── utils/          # Encoding, units
│   │
│   └── api/              # FastAPI backend
│       └── src/opensolve_pipe/
│           ├── routers/        # API endpoints
│           ├── services/       # Business logic
│           │   └── solver/     # Hydraulic solvers
│           ├── models/         # Pydantic models
│           └── data/           # Pipe materials, fittings, fluids
│
├── docs/
│   ├── PRD.md            # Product requirements
│   ├── SDD.md            # Software design
│   └── TSD.md            # Technical specs
│
└── CLAUDE.md             # This file
```

---

## Data Model Highlights

### Component Types
**Nodes:** Reservoir, Tank, Junction, Sprinkler, Orifice
**Links:** Pump, Valves (gate/ball/check/PRV/PSV/FCV), Heat Exchanger, Strainer
**Piping:** Pipes + Fittings (elbows, tees, reducers, etc.)

### Key Models
```typescript
interface Project {
  metadata: ProjectMetadata;
  settings: ProjectSettings;      // Units, checks, solver options
  fluid: FluidDefinition;          // Water, glycols, fuels, custom
  components: Component[];         // Chain of elements
  pumpLibrary: PumpCurve[];        // Reusable pump curves
  results?: SolvedState;           // Solved pressures, flows, etc.
}

interface Component {
  id: string;
  type: ComponentType;
  properties: {...};               // Type-specific
  upstreamPiping?: PipingSegment;
  downstreamConnections: Connection[];
}

interface PipingSegment {
  pipe: PipeDefinition;            // Material, schedule, diameter, length
  fittings: Fitting[];             // Elbows, tees, valves (quantity + K)
}
```

### Solved State
- **Per Node:** Pressure, HGL, EGL
- **Per Link:** Flow, velocity, head loss, Reynolds number, friction factor
- **Per Pump:** Operating point (flow, head), system curve, NPSH available

---

## Scope

### In Scope
✅ Steady-state hydraulic analysis
✅ Single-phase, isothermal flow
✅ Pressurized pipes (not open channel)
✅ Common liquids (water, glycols, fuels)
✅ Branching and looped networks
✅ Darcy-Weisbach friction factor (Colebrook)

### Out of Scope (v1)
❌ Transient/water hammer analysis
❌ Two-phase or compressible flow
❌ Heat transfer
❌ Gas flow

### Future Features
- Cost estimation utility
- Pipe sizing optimization
- Global pump database
- Pump curve digitization from images
- Public API

---

## Calculation Method

**Darcy-Weisbach Equation:**
```
h_f = f × (L/D) × (v²/2g)
```

- Friction factor `f` from Colebrook equation (implicit, iterative)
- Minor losses from K-factors (Crane TP-410 correlations)
- NPSH calculations for pump suction evaluation

**Solver Algorithms:**
1. **Simple solver:** Generate system curve, interpolate pump curve, find intersection
2. **Network solver:** Convert to WNTR graph, run EPANET steady-state solver

---

## Key Files to Review

### For Product Understanding
- `docs/PRD.md` - User needs, features, competitive analysis
- `docs/SDD.md` - Architecture, data models, API contracts

### For Implementation
- `docs/TSD.md` - Tech stack, file structure, code examples
- `docs/DEVELOPMENT_PLAN.md` - Phased milestones (create this next!)

---

## Development Philosophy

### Design Principles
1. **Mobile = Desktop** - Equal priority, responsive design
2. **Results-first** - No nannying, user controls design checks
3. **No installation friction** - Browser only, no plugins
4. **Shareability** - Every project state has a URL
5. **Simplicity** - Don't over-engineer, MVP first

### Unit Handling
- User selects preferred units per project (Imperial, SI, mixed)
- Backend always calculates in SI
- Frontend converts for display/input

### Version Control Strategy
- URL changes = new version (copy-on-write)
- Optional named branches for collaboration
- Full Git-like operations: branch, merge, checkout, history

---

## Quick Start

### Option 1: VS Code Dev Container (Recommended)

```bash
# Open project in VS Code
code .

# Reopen in Container (Command Palette: "Dev Containers: Reopen in Container")
# Wait for container to build and dependencies to install

# Frontend (in integrated terminal)
cd apps/web && pnpm dev  # → http://localhost:5173

# Backend (in new terminal)
cd apps/api && uvicorn opensolve_pipe.main:app --reload --port 8000  # → http://localhost:8000
```

**Includes:** Python 3.11, Node.js 20, PostgreSQL 16, Redis 7, all dependencies

### Option 2: Local Development

**Frontend:**
```bash
cd apps/web
npm install
npm run dev  # localhost:5173
```

**Backend:**
```bash
cd apps/api
pip install -e ".[dev]"
uvicorn opensolve_pipe.main:app --reload --port 8000
```

**Requires:** Python 3.11+, Node.js 20+, PostgreSQL 16, Redis 7

### Option 3: Docker Compose

```bash
docker-compose -f .devcontainer/docker-compose.yml up
```

---

## Development Workflow

This project uses the **compound-engineering plugin** for the core development workflow. The plugin provides comprehensive tools for planning, implementing, and reviewing code changes.

### Core Workflows (compound-engineering plugin)

- **`/workflows:plan`** - Create detailed implementation plans
  - Analyzes requirements and breaks down into tasks
  - Identifies dependencies and risks
  - Estimates complexity and effort

- **`/workflows:work`** - Execute work systematically
  - Follows implementation plan step-by-step
  - Tracks progress and handles errors
  - Integrates with test and validation

- **`/workflows:review`** - Comprehensive code review
  - Checks code quality, tests, and documentation
  - Validates against specifications
  - Identifies potential issues

- **`/workflows:compound`** - Document learnings
  - Captures decisions and rationale
  - Updates architectural documentation
  - Shares knowledge with team

- **`/deepen-plan`** - Expand implementation details
  - Adds granular steps to plans
  - Clarifies ambiguities
  - Refines estimates

- **`/changelog`** - Generate changelog entries
  - Automatically formats commit messages
  - Follows keep-a-changelog format
  - Updates CHANGELOG.md

### Project-Specific Tools

In addition to compound-engineering, we have custom OpenSolve Pipe tools:

#### Custom Skills

**`hydraulics`** - Hydraulic engineering domain knowledge
- Use when implementing solvers, calculations, or reviewing hydraulics
- Provides reference data: K-factors, roughness values, unit conversions
- Includes validation checklist for hydraulic correctness
- Located: `.claude/skills/hydraulics/SKILL.md`

**`opensolve-pipe-data-model`** - Component chain model conventions
- Use when working with project data structures
- Documents component types, piping segments, connections
- Provides examples and validation rules
- Located: `.claude/skills/data-model/SKILL.md`

#### Custom Agents

**`hydraulics-reviewer`** - Reviews hydraulic calculations
- Invoked for: Solver implementations, calculations, physics validation
- Checks: Darcy-Weisbach usage, K-factor resolution, NPSH calculations
- Output: Detailed review with correctness assessment and recommendations
- Located: `.claude/agents/hydraulics-reviewer.md`

**`tsd-compliance`** - Ensures TSD compliance
- Invoked for: New components, API changes, data model updates
- Checks: File locations, naming conventions, API contracts, data models
- Output: Compliance report with TSD section references
- Located: `.claude/agents/tsd-compliance.md`

#### Custom Hooks

**`stop-iterate`** - Feedback and iteration loop
- Automatically runs after each task completion
- Iterates up to 5 times to improve quality
- Checks: Test coverage (≥93%), linting, type checking
- Provides specific feedback for improvements

**`block-dangerous`** - Safety guard for commands
- Blocks: Destructive rm -rf, database drops, credential exposure
- Warns: Force push, DELETE without WHERE, chmod 777
- Prevents accidental system damage or data loss

### Quality Gates

Pre-commit hooks enforce quality before commits:

**Python:**
- Ruff lint and format (auto-fix)
- MyPy type checking
- Tests must pass (≥93% coverage)

**TypeScript/Svelte:**
- ESLint (auto-fix, zero warnings)
- Prettier formatting
- Svelte type checking

**General:**
- Trailing whitespace removal
- YAML/JSON syntax validation
- No commits to main/master
- Large file detection (>1MB)

### Auto-Updates

The following files are automatically maintained:

**`docs/CHANGELOG.md`**
- Updated on each commit
- Follows keep-a-changelog format
- Categorized: Added, Changed, Fixed, etc.

**`docs/DECISIONS.md`**
- Updated when architecture changes
- Documents ADRs (Architecture Decision Records)
- Includes context, decision, and consequences

**`apps/web/src/lib/api/types.ts`**
- Regenerated when backend models change
- Keeps frontend/backend types in sync
- Triggered by changes to `apps/api/src/opensolve_pipe/models/`

**`docs/API.md`**
- Generated from FastAPI route definitions
- Includes schemas and examples
- Keeps API documentation current

### Development Container

VS Code devcontainer provides complete environment:

**Services:**
- **App:** Python 3.11 + Node.js 20 LTS
- **PostgreSQL 16:** Database (localhost:5432)
- **Redis 7:** Cache/queue (localhost:6379)

**Ports:**
- 5173 - Frontend (SvelteKit)
- 8000 - Backend (FastAPI)
- 5432 - PostgreSQL
- 6379 - Redis

**Setup:**
```bash
# Open in VS Code
code .

# Reopen in Container (Command Palette)
# Or click "Reopen in Container" notification

# Services start automatically
# Dependencies install via post-create script
```

### Recommended Development Flow

1. **Start with planning**
   ```
   /workflows:plan [describe feature or fix]
   ```

2. **Review and refine plan**
   ```
   /deepen-plan [specify area to expand]
   ```

3. **Execute implementation**
   ```
   /workflows:work
   ```

4. **Review changes**
   ```
   /workflows:review
   ```

5. **Document learnings**
   ```
   /workflows:compound
   ```

6. **Commit with quality checks**
   ```bash
   git add .
   git commit -m "feat: implement simple solver"
   # Pre-commit hooks run automatically
   ```

### When to Use Custom Tools

**Use `hydraulics` skill when:**
- Implementing solver algorithms
- Adding new component types with hydraulic behavior
- Reviewing head loss calculations
- Need reference data (K-factors, roughness, conversions)

**Use `opensolve-pipe-data-model` skill when:**
- Creating or modifying component interfaces
- Working with project structure
- Adding new component types
- Debugging component chain issues

**Invoke `hydraulics-reviewer` agent when:**
- Completing solver implementation
- Reviewing pull requests with hydraulic code
- Validating calculation correctness
- Need expert review of physics/math

**Invoke `tsd-compliance` agent when:**
- Adding new API endpoints
- Modifying data models
- Restructuring files/directories
- Need compliance verification before PR

### Continuous Integration

GitHub Actions run on pull requests:
- All pre-commit hooks
- Full test suite (backend + frontend)
- Build verification
- Documentation generation
- Coverage reporting

**Required Checks:**
- ✅ All tests pass
- ✅ Coverage ≥93%
- ✅ Linting passes (zero errors/warnings)
- ✅ Type checking passes
- ✅ Builds successfully

---

## Testing Strategy

### Backend
- Unit tests: Solver accuracy vs EPANET (< 1% deviation)
- Integration tests: Full solve workflow
- Property tests: Fluid properties at various temperatures

### Frontend
- Component tests: UI components render correctly
- Integration tests: State management, URL encoding roundtrip
- E2E tests: Complete user workflows (create → solve → export)

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Time to first solve (new user) | < 5 minutes |
| Page load (cold) | < 2s |
| Solve time (< 20 components) | < 1s |
| Solve time (20-100 components) | < 5s |
| Mobile usability score | > 90 |

---

## Open Questions

1. **Schematic layout:** dagre, elkjs, or custom algorithm?
2. **Version storage:** Git under the hood vs PostgreSQL?
3. **Real-time collaboration:** WebSockets vs polling?
4. **Pump curve digitization:** Existing library vs custom ML model?

---

## Related Resources

- **Crane TP-410:** Fitting K-factors reference ([link](https://www.flowoffluids.com/))
- **EPANET:** Network solver documentation
- **WNTR:** Water Network Tool for Resilience (Python wrapper)
- **fluids library:** Python hydraulic calculations

---

## Getting Help

- **Issues:** https://github.com/ccirone2/opensolve-pipe/issues
- **Discussions:** TBD
- **Docs:** See `docs/` directory

---

**Last Updated:** 2026-01-17
**Project Phase:** Planning → Implementation (Phase 1 starting)
