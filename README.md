# OpenSolve Pipe

A free, browser-based tool for steady-state hydraulic analysis of pressurized pipe networks: pumps, valves, fittings, branching and looped systems. No installation and no account. A project lives entirely in its URL, so sharing a design means sharing a link.

> **Status:** v1 (core analysis MVP) is implemented in this repository — API, network solver, reference suite and web app — and not yet deployed. `docs/prompts/build-v1.md` is the plan it was built from.

## Who it's for

Students checking hand calculations, field technicians sizing a retrofit, and process or consulting engineers who need professional-grade results without a desktop license.

## v1 scope

- Branching and looped networks of pipes and fittings, with reservoirs, reference pressure nodes, tees, wyes and caps
- Fixed-speed pumps, isolation and check valves, and pressure-reducing, pressure-sustaining and flow-control valves
- Water, glycol solutions and user-defined fluids
- Darcy–Weisbach / Colebrook friction, with K-factor minor losses from Crane TP-410 (via the `fluids` library)
- Results: flows, velocities, head loss, pressures, HGL/EGL, pump operating point, system curve, NPSH available
- Imperial, SI or mixed units
- Share by link: the project is compressed into the URL fragment and never sent to a server for storage

Out of scope: transient (water hammer), two-phase, gas and open-channel flow, and heat transfer.

## Documents

| Document | Contents |
|----------|----------|
| [`docs/GOALS.md`](docs/GOALS.md) | Mission, values and priorities that guide decisions |
| [`docs/PRD.md`](docs/PRD.md) | Product requirements: users, scope, features |
| [`docs/SDD.md`](docs/SDD.md) | Software design: architecture, data models, API |
| [`docs/TSD.md`](docs/TSD.md) | Technical spec: stack, layout, implementation notes |
| [`CLAUDE.md`](CLAUDE.md) | Rebuild decisions that override the specs, plus conventions |

## Stack

- **Backend** (`apps/api`): Python 3.12, FastAPI, Pydantic v2, NumPy/SciPy, `fluids` (friction, fittings, pipe dimensions), CoolProp (fluid properties), and its own network solver (Global Gradient Algorithm). Managed with [uv](https://docs.astral.sh/uv/). WNTR/EPANET is a test-only dependency.
- **Frontend** (`apps/web`): SvelteKit 2, Svelte 5, TypeScript, Tailwind CSS, Chart.js, pako. Managed with [pnpm](https://pnpm.io/).

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22+ and pnpm 10 (`corepack enable`).

```bash
# API: http://localhost:8000 (OpenAPI schema at /openapi.json; with API_DOCS=1, interactive
# docs at /docs and /redoc, which load their assets from third-party CDNs)
cd apps/api
uv sync
uv run uvicorn opensolve_pipe.main:app --reload --port 8000

# Web: http://localhost:5173 (talks to PUBLIC_API_URL, default http://localhost:8000)
cd apps/web
pnpm install
pnpm dev
```

Quality gates (CI runs all of them):

```bash
# apps/api
uv run pytest                               # unit tests, the reference suite (tests/reference) and the EPANET differential smoke test (tests/differential, TSD §10.4)
uv run ruff check . && uv run ruff format --check .
uv run mypy src                             # strict

# apps/web
pnpm check && pnpm lint && pnpm test        # svelte-check, Prettier + ESLint, Vitest
pnpm exec playwright install chromium       # once: Playwright's browser (Linux: --with-deps chromium)
pnpm test:e2e                               # Playwright, desktop and mobile; starts the API with uv
```

The end-to-end tests start their own API (port 8010) and built app (port 4183), so the development servers above can keep running.

Generated files (never edit them by hand):

```bash
cd apps/web && pnpm gen:types                                  # TS types from the API's OpenAPI schema
cd apps/api && uv run python scripts/generate_pipe_data.py     # data/pipe_materials.json from fluids
cd apps/api && uv run python -m tests.reference.build_closed_form_cases   # closed-form reference cases
cd apps/api && uv run python -m tests.reference.generate_epanet_cases     # EPANET reference cases (WNTR)
```

The reference suite (`apps/api/tests/reference/`) is how hydraulic correctness is established: every case states where its expected values come from (a closed-form derivation or an EPANET run), and tests fail if a case file is stale.

## Contributing

Bug reports, data requests and questions are welcome as [issues](https://github.com/ccirone2/opensolve-pipe/issues). Code contributions are accepted by invitation, to keep the project on one consistent vision. See [`docs/GOALS.md`](docs/GOALS.md) for the values that guide decisions.

## Disclaimer

OpenSolve Pipe is an engineering aid. Its results support, but do not replace, the judgment of a qualified engineer, and are provided without warranty.

## License

[GNU Affero General Public License v3.0 or later](LICENSE) (`AGPL-3.0-or-later`). You may use, study, modify and share the code; if you run a modified version as a network service, you must offer its users the corresponding source code.
