# OpenSolve Pipe

Free, browser-based hydraulic network design tool for steady-state pipe flow analysis.

[![CI](https://github.com/ccirone2/opensolve-pipe/actions/workflows/ci.yml/badge.svg)](https://github.com/ccirone2/opensolve-pipe/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Features

- **No Installation** - Runs entirely in your browser
- **Shareable via URL** - Projects encoded in links, no account needed
- **Mobile-Friendly** - Panel navigator designed for phones and tablets
- **Industry Standard Methods** - Darcy-Weisbach with Colebrook friction factor

## Quick Start

1. Visit [OpenSolve Pipe](https://opensolve-pipe.vercel.app/)
2. Click "New Project"
3. Add components (reservoirs, pumps, pipes, tanks)
4. Click "Solve"

## Documentation

### User Guides

- [Getting Started](docs/user/getting-started.md)
- [Component Reference](docs/user/components.md)
- [FAQ](docs/user/faq.md)
- [Calculation Methodology](docs/user/methodology.md)

### Technical Documentation

- [Product Requirements (PRD)](docs/PRD.md)
- [Software Design (SDD)](docs/SDD.md)
- [Technical Specification (TSD)](docs/TSD.md)
- [Changelog](docs/CHANGELOG.md)

## Project Structure

```text
opensolve-pipe/
├── apps/
│   ├── web/              # SvelteKit frontend
│   │   ├── src/lib/      # Components, stores, utilities
│   │   └── e2e/          # Playwright E2E tests
│   └── api/              # FastAPI backend
│       └── src/          # API routers, services, models
├── docs/
│   ├── user/             # User documentation
│   └── *.md              # Technical specifications
└── .github/workflows/    # CI/CD pipelines
```

## Development

### Prerequisites

- Node.js 20+
- Python 3.11+
- pnpm

### Frontend

```bash
cd apps/web
pnpm install
pnpm dev          # Start dev server at localhost:5173
```

### Backend

```bash
cd apps/api
pip install -e ".[dev]"
uvicorn opensolve_pipe.main:app --reload --port 8000
```

### Using Dev Container (Recommended)

1. Open in VS Code
2. Install "Dev Containers" extension
3. Click "Reopen in Container"
4. All dependencies installed automatically

## Testing

```bash
# Frontend unit tests
cd apps/web && pnpm test

# Frontend E2E tests
cd apps/web && pnpm test:e2e

# Backend tests
cd apps/api && pytest
```

## Deployment

- **Frontend**: Vercel (automatic from main branch)
- **Backend**: Railway (Docker-based)

See [Deployment Setup](docs/DEPLOYMENT.md) for details.

## Tech Stack

### Frontend

- [SvelteKit](https://kit.svelte.dev/) - Web framework
- [Svelte 5](https://svelte.dev/) - UI components with runes
- [Tailwind CSS](https://tailwindcss.com/) - Styling
- [Chart.js](https://www.chartjs.org/) - Pump curve visualization
- [TypeScript](https://www.typescriptlang.org/) - Type safety

### Backend

- [FastAPI](https://fastapi.tiangolo.com/) - API framework
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [fluids](https://fluids.readthedocs.io/) - Hydraulic calculations
- Python 3.11 - Runtime

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Crane TP-410](https://www.flowoffluids.com/) - K-factors and hydraulic data
- [EPANET](https://www.epa.gov/water-research/epanet) - Network solver reference
- [fluids library](https://github.com/CalebBell/fluids) - Python hydraulics
