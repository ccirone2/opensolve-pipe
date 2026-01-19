# Changelog

All notable changes to OpenSolve Pipe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-19

### Added

#### Backend (API)

- Unit conversion system with SI/Imperial support
- Fluid properties service with temperature-dependent calculations
- Simple solver for single-path hydraulic networks
- Pipe materials and fittings data libraries (Crane TP-410)
- `/api/v1/solve` endpoint for network solving
- `/api/v1/fluids` endpoints for fluid properties
- `/api/v1/solve/simple` endpoint for pump-pipe systems
- Health check endpoint at `/health`

#### Frontend (Web)

- SvelteKit application with TypeScript
- Panel Navigator for component-by-component editing
- Component forms for all node and link types
- Results display with pump curve visualization
- URL encoding/decoding for shareable projects
- Project state management with undo/redo
- API client with retry logic and error handling
- Solve button with loading state and keyboard shortcut

#### Infrastructure

- GitHub Actions CI/CD pipeline
- Vercel configuration for frontend deployment
- Docker and Railway configuration for backend deployment
- Pre-commit hooks for code quality

#### Documentation

- Getting Started guide
- Component reference
- FAQ
- Calculation methodology

### Technical Details

- Python 3.11 with FastAPI for backend
- Svelte 5 with runes for frontend
- Chart.js for pump curve visualization
- Tailwind CSS for styling
- Vitest for unit tests
- Playwright for E2E tests

## [Unreleased]

### Planned Features

- Branching network support
- Looped network support (EPANET integration)
- Server-side project storage for large projects
- Pump curve digitization from images
- Global pump database
- Export to EPANET format
- Cost estimation utility
- Pipe sizing optimization

---

## Release Notes Format

### [Version] - YYYY-MM-DD

#### Added

- New features

#### Changed

- Changes in existing functionality

#### Deprecated

- Soon-to-be removed features

#### Removed

- Removed features

#### Fixed

- Bug fixes

#### Security

- Vulnerability fixes
