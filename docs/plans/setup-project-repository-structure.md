# Issue #1: Project Setup and Repository Structure

**Type:** setup
**Priority:** Critical (Phase 1 blocker)
**Labels:** `setup`, `Phase 1`, `critical`
**Milestone:** Phase 1 - MVP
**Estimated Effort:** Medium (4-6 hours)

---

## Overview

Set up the monorepo structure with a working SvelteKit frontend and FastAPI backend. This is the foundation for all subsequent Phase 1 issues.

**Goal:** Any developer can clone the repo, run setup commands, and have both apps running with hot reload within 10 minutes.

---

## Problem Statement

The OpenSolve Pipe project has comprehensive specifications (PRD, SDD, TSD) and dev container configuration, but the actual application code doesn't exist yet. The `apps/web/` and `apps/api/` directories are empty shells.

**Current State:**

- `/workspace/apps/web/src/` - Empty directory
- `/workspace/apps/api/src/opensolve_pipe/` - Empty directory
- Dev container configured but apps won't start
- Pre-commit hooks configured but no code to lint

**Desired State:**

- SvelteKit app runs on `localhost:5173` with hot reload
- FastAPI app runs on `localhost:8000` with hot reload
- Health check endpoint returns `{"status": "healthy"}`
- OpenAPI docs available at `/docs`
- Both apps can be developed independently or together

---

## Technical Approach

### Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package manager (frontend) | **pnpm** | Already in devcontainer, faster than npm, strict node_modules |
| Python linter/formatter | **Ruff** | Replaces Black + isort + Flake8, already in pre-commit config |
| SvelteKit adapter | **adapter-auto** | Flexible deployment, detects Vercel/Cloudflare automatically |
| Python packaging | **hatchling** | Modern, PEP 517 compliant, good for src layout |
| Lockfile strategy | **pnpm-lock.yaml + no Python lock** | Frontend reproducibility, Python uses version ranges |

### Key Corrections from Original Issue

1. **Use Ruff instead of Black/isort** - Project pre-commit config already uses Ruff
2. **Use pnpm instead of npm** - Devcontainer installs pnpm globally
3. **Add minimum runnable code** - Apps need actual files to start

---

## Implementation Phases

### Phase 1: Backend Setup (FastAPI)

**Files to create:**

```
apps/api/
├── pyproject.toml
├── README.md
├── src/
│   └── opensolve_pipe/
│       ├── __init__.py
│       ├── main.py
│       └── routers/
│           └── __init__.py
└── tests/
    ├── __init__.py
    └── conftest.py
```

#### 1.1 Create pyproject.toml

```toml
# apps/api/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "opensolve-pipe"
version = "0.1.0"
description = "Hydraulic network analysis API"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [
    { name = "OpenSolve Team" }
]
dependencies = [
    "fastapi>=0.115.0,<1.0.0",
    "uvicorn[standard]>=0.32.0,<1.0.0",
    "pydantic>=2.10.0,<3.0.0",
    "pydantic-settings>=2.6.0,<3.0.0",
    "fluids>=1.0.0,<2.0.0",
    "scipy>=1.14.0,<2.0.0",
    "numpy>=2.0.0,<3.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
    "httpx>=0.28.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/opensolve_pipe"]

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = ["-ra", "-q", "--strict-markers"]

[tool.coverage.run]
source = ["src/opensolve_pipe"]
branch = true

[tool.coverage.report]
fail_under = 93
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:"]

[tool.ruff]
target-version = "py311"
line-length = 88
src = ["src"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "SIM", "TCH", "RUF"]
ignore = ["E501", "B008"]

[tool.ruff.lint.isort]
known-first-party = ["opensolve_pipe"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["fluids.*", "scipy.*"]
ignore_missing_imports = true
```

#### 1.2 Create main.py

```python
# apps/api/src/opensolve_pipe/main.py
"""OpenSolve Pipe API - Hydraulic network analysis."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    yield


app = FastAPI(
    title="OpenSolve Pipe API",
    description="Hydraulic network analysis API for steady-state pipe flow",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "name": "OpenSolve Pipe API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
```

#### 1.3 Create **init**.py files

```python
# apps/api/src/opensolve_pipe/__init__.py
"""OpenSolve Pipe - Hydraulic network analysis."""

__version__ = "0.1.0"
```

```python
# apps/api/src/opensolve_pipe/routers/__init__.py
"""API routers."""
```

```python
# apps/api/tests/__init__.py
"""Test package."""
```

#### 1.4 Create conftest.py

```python
# apps/api/tests/conftest.py
"""Pytest configuration and shared fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from opensolve_pipe.main import app


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio as the async backend."""
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for testing FastAPI endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
```

#### 1.5 Create backend README

```markdown
# OpenSolve Pipe API

FastAPI backend for hydraulic network analysis.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run development server
uvicorn opensolve_pipe.main:app --reload --port 8000

# Run tests
pytest

# Run linter
ruff check .
ruff format .
```

## Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `GET /docs` - OpenAPI documentation

```

---

### Phase 2: Frontend Setup (SvelteKit)

**Files to create:**

```

apps/web/
├── package.json
├── pnpm-lock.yaml (generated)
├── svelte.config.js
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── eslint.config.js
├── .prettierrc
├── README.md
├── src/
│   ├── app.html
│   ├── app.css
│   ├── app.d.ts
│   └── routes/
│       ├── +layout.svelte
│       └── +page.svelte
└── static/
    └── favicon.png

```

#### 2.1 Create package.json

```json
{
  "name": "opensolve-pipe-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
    "check:watch": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json --watch",
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "format": "prettier --write .",
    "test": "vitest",
    "test:coverage": "vitest --coverage"
  },
  "devDependencies": {
    "@sveltejs/adapter-auto": "^3.3.0",
    "@sveltejs/kit": "^2.15.0",
    "@sveltejs/vite-plugin-svelte": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "@types/pako": "^2.0.3",
    "@vitest/coverage-v8": "^2.0.0",
    "eslint": "^9.17.0",
    "eslint-config-prettier": "^10.0.0",
    "eslint-plugin-svelte": "^2.46.0",
    "globals": "^15.14.0",
    "prettier": "^3.4.0",
    "prettier-plugin-svelte": "^3.3.0",
    "prettier-plugin-tailwindcss": "^0.6.0",
    "svelte": "^5.15.0",
    "svelte-check": "^4.1.0",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.7.0",
    "typescript-eslint": "^8.18.0",
    "vite": "^6.0.0",
    "vitest": "^2.0.0"
  },
  "dependencies": {
    "chart.js": "^4.4.0",
    "pako": "^2.1.0"
  }
}
```

#### 2.2 Create svelte.config.js

```javascript
// apps/web/svelte.config.js
import adapter from '@sveltejs/adapter-auto';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter(),
    alias: {
      $lib: 'src/lib',
      '$lib/*': 'src/lib/*'
    }
  }
};

export default config;
```

#### 2.3 Create vite.config.ts

```typescript
// apps/web/vite.config.ts
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  test: {
    include: ['src/**/*.{test,spec}.{js,ts}'],
    environment: 'jsdom',
    globals: true
  }
});
```

#### 2.4 Create tsconfig.json

```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": true,
    "checkJs": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "strict": true,
    "moduleResolution": "bundler"
  }
}
```

#### 2.5 Create eslint.config.js

```javascript
// apps/web/eslint.config.js
import js from '@eslint/js';
import ts from 'typescript-eslint';
import svelte from 'eslint-plugin-svelte';
import prettier from 'eslint-config-prettier';
import globals from 'globals';

/** @type {import('eslint').Linter.Config[]} */
export default [
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs['flat/recommended'],
  prettier,
  ...svelte.configs['flat/prettier'],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node
      }
    }
  },
  {
    files: ['**/*.svelte'],
    languageOptions: {
      parserOptions: {
        parser: ts.parser
      }
    }
  },
  {
    ignores: ['build/', '.svelte-kit/', 'dist/', 'node_modules/']
  }
];
```

#### 2.6 Create .prettierrc

```json
{
  "useTabs": false,
  "tabWidth": 2,
  "singleQuote": true,
  "trailingComma": "es5",
  "printWidth": 100,
  "plugins": ["prettier-plugin-svelte", "prettier-plugin-tailwindcss"],
  "overrides": [
    {
      "files": "*.svelte",
      "options": {
        "parser": "svelte"
      }
    }
  ]
}
```

#### 2.7 Create app.html

```html
<!-- apps/web/src/app.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="%sveltekit.assets%/favicon.png" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>OpenSolve Pipe</title>
    %sveltekit.head%
  </head>
  <body data-sveltekit-preload-data="hover">
    <div style="display: contents">%sveltekit.body%</div>
  </body>
</html>
```

#### 2.8 Create app.css

```css
/* apps/web/src/app.css */
@import 'tailwindcss';
```

#### 2.9 Create app.d.ts

```typescript
// apps/web/src/app.d.ts
// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
  namespace App {
    // interface Error {}
    // interface Locals {}
    // interface PageData {}
    // interface PageState {}
    // interface Platform {}
  }
}

export {};
```

#### 2.10 Create +layout.svelte

```svelte
<!-- apps/web/src/routes/+layout.svelte -->
<script lang="ts">
  import '../app.css';

  let { children } = $props();
</script>

{@render children()}
```

#### 2.11 Create +page.svelte

```svelte
<!-- apps/web/src/routes/+page.svelte -->
<script lang="ts">
  let title = 'OpenSolve Pipe';
</script>

<main class="min-h-screen bg-gray-50">
  <header class="bg-white border-b border-gray-200 px-4 py-3">
    <h1 class="text-xl font-semibold text-gray-900">{title}</h1>
  </header>

  <div class="max-w-4xl mx-auto p-4">
    <div class="bg-white rounded-lg shadow p-6">
      <h2 class="text-lg font-medium text-gray-800 mb-4">
        Welcome to OpenSolve Pipe
      </h2>
      <p class="text-gray-600">
        A free, browser-based hydraulic network design tool for steady-state pipe flow analysis.
      </p>
      <p class="text-sm text-gray-500 mt-4">
        Project setup complete. Ready for Phase 1 development.
      </p>
    </div>
  </div>
</main>
```

#### 2.12 Create frontend README

```markdown
# OpenSolve Pipe Web

SvelteKit frontend for hydraulic network design.

## Quick Start

```bash
# Install dependencies
pnpm install

# Run development server
pnpm dev

# Run tests
pnpm test

# Type check
pnpm check

# Lint
pnpm lint
```

## Development

- **Dev server:** <http://localhost:5173>
- **API server:** <http://localhost:8000> (run separately)

```

---

### Phase 3: Environment Configuration

#### 3.1 Create apps/api/.env.example

```bash
# apps/api/.env.example
# OpenSolve Pipe API Configuration

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# CORS (comma-separated origins)
CORS_ORIGINS=http://localhost:5173,http://localhost:4173

# Database (optional, for large projects)
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/opensolve

# Redis (optional, for caching)
# REDIS_URL=redis://localhost:6379
```

#### 3.2 Create apps/web/.env.example

```bash
# apps/web/.env.example
# OpenSolve Pipe Web Configuration

# API URL
PUBLIC_API_URL=http://localhost:8000
```

#### 3.3 Update root .gitignore

Add these patterns to existing .gitignore:

```gitignore
# Frontend
apps/web/node_modules/
apps/web/.svelte-kit/
apps/web/build/
apps/web/.vercel/

# Environment files
.env
.env.local
*.local

# Test coverage
coverage/
.coverage
htmlcov/

# IDE
.idea/
*.swp
*.swo
```

---

### Phase 4: Verification

#### 4.1 Backend Verification Steps

```bash
cd apps/api

# Install dependencies
pip install -e ".[dev]"

# Verify installation
python -c "import opensolve_pipe; print(opensolve_pipe.__version__)"
# Expected: 0.1.0

# Start server
uvicorn opensolve_pipe.main:app --reload --port 8000

# Test endpoints (in another terminal)
curl http://localhost:8000/
# Expected: {"name":"OpenSolve Pipe API","version":"0.1.0","docs":"/docs"}

curl http://localhost:8000/health
# Expected: {"status":"healthy"}

# Run linter
ruff check .
ruff format --check .

# Run tests
pytest -v
```

#### 4.2 Frontend Verification Steps

```bash
cd apps/web

# Install dependencies
pnpm install

# Start dev server
pnpm dev

# Open browser to http://localhost:5173
# Expected: "Welcome to OpenSolve Pipe" page

# Type check
pnpm check

# Lint
pnpm lint
```

#### 4.3 Integration Verification

```bash
# In terminal 1
cd apps/api && uvicorn opensolve_pipe.main:app --reload --port 8000

# In terminal 2
cd apps/web && pnpm dev

# Verify both running
curl http://localhost:8000/health  # {"status":"healthy"}
curl http://localhost:5173         # HTML page
```

---

## Acceptance Criteria

### Required (Must Pass)

- [x] `apps/api/` contains valid Python package with pyproject.toml
- [x] `pip install -e ".[dev]"` succeeds without errors
- [x] `uvicorn opensolve_pipe.main:app --reload` starts server on port 8000
- [x] `GET /health` returns `{"status": "healthy"}`
- [x] `GET /docs` shows OpenAPI documentation
- [x] `apps/web/` contains valid SvelteKit project
- [x] `pnpm install` succeeds without errors
- [x] `pnpm dev` starts server on port 5173
- [x] Browser shows welcome page at localhost:5173
- [x] `pnpm check` passes with no type errors
- [x] `ruff check apps/api/` passes with no errors
- [x] `pnpm --filter web lint` passes with no errors

### Optional (Nice to Have)

- [x] Pre-commit hooks run successfully
- [x] Both apps work in dev container
- [x] Hot reload works (change file, see update without restart)

---

## Task Checklist

### Backend Tasks

- [x] Create `apps/api/pyproject.toml` with dependencies and tool config
- [x] Create `apps/api/src/opensolve_pipe/__init__.py`
- [x] Create `apps/api/src/opensolve_pipe/main.py` with FastAPI app
- [x] Create `apps/api/src/opensolve_pipe/routers/__init__.py`
- [x] Create `apps/api/tests/__init__.py`
- [x] Create `apps/api/tests/conftest.py` with fixtures
- [x] Create `apps/api/README.md` with setup instructions
- [x] Create `apps/api/.env.example`
- [x] Verify `pip install -e ".[dev]"` works
- [x] Verify `uvicorn` starts server
- [x] Verify `ruff check .` passes

### Frontend Tasks

- [x] Create `apps/web/package.json` with dependencies
- [x] Create `apps/web/svelte.config.js`
- [x] Create `apps/web/vite.config.ts`
- [x] Create `apps/web/tsconfig.json`
- [x] Create `apps/web/eslint.config.js`
- [x] Create `apps/web/.prettierrc`
- [x] Create `apps/web/src/app.html`
- [x] Create `apps/web/src/app.css`
- [x] Create `apps/web/src/app.d.ts`
- [x] Create `apps/web/src/routes/+layout.svelte`
- [x] Create `apps/web/src/routes/+page.svelte`
- [x] Create `apps/web/README.md`
- [x] Create `apps/web/.env.example`
- [x] Run `pnpm install` and commit lockfile
- [x] Verify `pnpm dev` works
- [x] Verify `pnpm check` passes
- [x] Verify `pnpm lint` passes

### Integration Tasks

- [x] Update root `.gitignore` with frontend patterns
- [x] Test both apps running simultaneously
- [x] Verify CORS allows frontend to call backend
- [x] Test in fresh clone (or delete node_modules/.venv and reinstall)

---

## Dependencies

### Backend Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | ^0.115.0 | Web framework |
| uvicorn[standard] | ^0.32.0 | ASGI server |
| pydantic | ^2.10.0 | Data validation |
| pydantic-settings | ^2.6.0 | Settings management |
| fluids | ^1.0.0 | Hydraulic calculations |
| scipy | ^1.14.0 | Scientific computing |
| numpy | ^2.0.0 | Numerical arrays |
| pytest | ^8.3.0 | Testing (dev) |
| pytest-asyncio | ^0.24.0 | Async testing (dev) |
| pytest-cov | ^6.0.0 | Coverage (dev) |
| httpx | ^0.28.0 | HTTP client for tests (dev) |
| ruff | ^0.8.0 | Linter/formatter (dev) |
| mypy | ^1.13.0 | Type checker (dev) |

### Frontend Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| @sveltejs/kit | ^2.15.0 | Framework |
| svelte | ^5.15.0 | Component library |
| tailwindcss | ^4.0.0 | CSS framework |
| chart.js | ^4.4.0 | Charts |
| pako | ^2.1.0 | gzip compression |
| typescript | ^5.7.0 | Type checking |
| vite | ^6.0.0 | Build tool |
| vitest | ^2.0.0 | Testing |
| eslint | ^9.17.0 | Linting |
| prettier | ^3.4.0 | Formatting |

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| scipy build fails on some systems | Medium | High | Document troubleshooting, suggest conda |
| Tailwind v4 breaking changes | Low | Medium | Pin to ^4.0.0, monitor changelog |
| pnpm version mismatch | Low | Low | Specify in package.json engines |
| Pre-commit hooks fail | Medium | Low | Update pre-commit config if needed |

---

## References

### Internal

- `docs/TSD.md` - Full technical specification
- `docs/DEVELOPMENT_PLAN.md` - Phase structure
- `.devcontainer/devcontainer.json` - Dev container config
- `.pre-commit-config.yaml` - Quality hooks

### External

- [SvelteKit Documentation](https://svelte.dev/docs/kit)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [Ruff Configuration](https://docs.astral.sh/ruff/)

---

**Plan Created:** 2026-01-19
**Last Updated:** 2026-01-19
**Status:** ✅ Completed (PR #2 merged)
