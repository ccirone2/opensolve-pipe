# OpenSolve Pipe

A free, browser-based tool for steady-state hydraulic analysis of pressurized pipe networks: pumps, valves, fittings, branching and looped systems. No installation and no account. A project lives entirely in its URL, so sharing a design means sharing a link.

> **Status:** v1 (core analysis MVP) is implemented in this repository — API, network solver, reference suite and web app — deployed by the owner (Cloudflare Pages and Google Cloud Run), and not yet a stable release: links and results may change between versions until the owner declares one ([D14](docs/decisions/D14-deployed-not-stable.md)). [`docs/history.md`](docs/history.md) records what was built and the numbers the gates gave.

## Who it's for

Students checking hand calculations, field technicians sizing a retrofit, and process or consulting engineers who need professional-grade results without a desktop license.

## v1 scope

- Branching and looped networks of pipes and fittings, with reservoirs, reference pressure nodes, assigned-flow nodes (a fixed demand or supply), tees, wyes and caps
- Fixed-speed pumps and speed-controlled (VFD) pumps holding a flow setpoint, isolation and check valves, and pressure-reducing, pressure-sustaining and flow-control valves
- Equipment such as heat exchangers, coils, strainers and filters, entered from the datasheet as a pressure drop at a rated flow (with the density of the fluid it is rated for) or as a Cv or Kv, and scaled with the square of the flow and with density
- Orifice plates (ISO 5167-2), as restriction orifices or flow meters: the bore, with the Reader-Harris/Gallagher discharge coefficient or a calibrated one, giving the plate's permanent pressure loss in the network and a meter's differential pressure at its taps, with a flashing check at the vena contracta
- Pressure relief valves for liquid service (conventional spring-loaded): a set pressure and an API 526 orifice letter, an API 520 effective area or the valve's certified area and coefficient, relieving with API 520's liquid capacity at full lift; the lift between set and full lift is a linear convention and flagged, and a free outlet can discharge to atmosphere in one step
- A project library: pipe specs (a cited material or a custom pipe, at a stated bore) and K, Cv or Kv entries from a datasheet, each with its source, defined once in the project and used by pipes, valves and fittings, so an edit to an entry reaches every element that uses it
- Water, glycol solutions and user-defined fluids
- Darcy–Weisbach / Colebrook friction, with K-factor minor losses from Crane TP-410 (via the `fluids` library)
- Results: flows, velocities, head loss, pressures, HGL/EGL, pump operating point, system curve, NPSH available, each equipment item's pressure loss against its rating, each orifice plate's permanent loss and meter reading, and each relief valve's state, relieving flow and inlet pressure against its set and capacity
- Scenarios: named cases of one network (a pump off, a valve closed, a larger pipe, another fluid temperature, a dirty strainer, another orifice bore, a blocked discharge behind a relief valve) kept as changes of the base case, solved one at a time or all together and compared side by side
- Goal seek: the input values (a pump speed, a reservoir level, a valve's Cv, a pipe length, an orifice bore, a relief valve's effective area for its relieving pressure, up to four at once) that bring chosen results to their targets, each trial a full network solve, applied to the case or as a new scenario only when you choose
- Pumps together: pumps in parallel or in series on one chart, each with its own curve and point, how the flow divides between them and what each loses on its way, and the group curve, the station's flow at each rise, solved with every pump on its own curve (so it shows where a weaker pump stops delivering)
- Design checks, off until you turn them on: each pump's NPSH margin and flow against its best efficiency flow (with the manufacturer's allowable region, minimum flows and motor rating, when entered) and every pipe's velocity, against your limits or a cited preset (API 610, HI 9.6.1), shown on the pump chart and listed as met, not met or not evaluated; they never change a result
- Export: every results table of the case shown or of all cases as an Excel workbook or CSV files (each value at full precision, with the project, case, solve and methods version it came from), and the pump chart as a PNG, all made in your browser: nothing is sent
- Imperial, SI or mixed units
- Share by link: the project is compressed into the URL fragment and never sent to a server for storage

Out of scope: transient (water hammer), two-phase, gas and open-channel flow, and heat transfer.

## Documents

[`docs/README.md`](docs/README.md) maps every document. The short list:

| Document | Contents |
|----------|----------|
| [`docs/GOALS.md`](docs/GOALS.md) | Mission, values and priorities that guide decisions |
| [`docs/decisions/`](docs/decisions/README.md) | Decisions D1–D23: the architecture rules and one record per built feature |
| [`docs/PRD.md`](docs/PRD.md) | Product requirements: users, scope, features |
| [`docs/SDD.md`](docs/SDD.md) | Software design: architecture, data models, API |
| [`docs/TSD.md`](docs/TSD.md) | Technical spec: stack, layout, solver, tests, deployment settings |
| [`docs/workflow.md`](docs/workflow.md) | How a feature is designed, built, proven and recorded |
| [`CLAUDE.md`](CLAUDE.md) | The context guide loaded into every AI session: rules, reading map, decision index |

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

## Deployment

The web app runs on Cloudflare Pages (`https://opensolve-pipe.pages.dev`) and the API on Google Cloud Run; the owner deployed both on 2026-10-25. A deployment is not a stable release: until the owner declares one, the model, the link format, the API and the methods may change ([D14](docs/decisions/D14-deployed-not-stable.md)). The copy-and-paste runbook is [`docs/deployment.md`](docs/deployment.md); [`docs/TSD.md`](docs/TSD.md) §11 explains each setting, the checks after every deployment and the costs. Ordinary use fits within both providers' free tiers.

## Contributing

Bug reports, data requests and questions are welcome as [issues](https://github.com/ccirone2/opensolve-pipe/issues). Code contributions are accepted by invitation, to keep the project on one consistent vision. See [`docs/GOALS.md`](docs/GOALS.md) for the values that guide decisions.

## Disclaimer

OpenSolve Pipe is an engineering aid. Its results support, but do not replace, the judgment of a qualified engineer, and are provided without warranty.

## License

Copyright © 2026 Chris Cirone

[GNU Affero General Public License v3.0 or later](LICENSE) (`AGPL-3.0-or-later`). You may use, study, modify and share the code; if you run a modified version as a network service, you must offer its users the corresponding source code.

> This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
>
> This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

The web app shows the copyright notice, links to the source of the exact commit it was built from, and serves the licenses of the open source packages bundled into it at `/third-party-licenses.txt` (TSD §11.1).
