# OpenSolve Pipe

A free, browser-based tool for steady-state hydraulic analysis of pressurized pipe networks: pumps, valves, fittings, branching and looped systems. No installation and no account. A project lives entirely in its URL, so sharing a design means sharing a link.

> **Status:** rebuilding from scratch. This repository currently contains only the specifications; no application code yet.

## Who it's for

Students checking hand calculations, field technicians sizing a retrofit, and process or consulting engineers who need professional-grade results without a desktop license.

## Planned v1

- Branching and looped networks of pipes and fittings, with reservoirs, reference pressure nodes, tees, wyes and caps
- Fixed-speed pumps, isolation and check valves, and pressure-reducing, pressure-sustaining and flow-control valves
- Water, glycol solutions and user-defined fluids
- Darcy–Weisbach / Colebrook friction, with K-factor minor losses from Crane TP-410
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

## Planned stack

- **Backend:** Python 3.12, FastAPI, Pydantic, `fluids`, with a custom network solver (global gradient method). Managed with [uv](https://docs.astral.sh/uv/).
- **Frontend:** SvelteKit, TypeScript, Tailwind CSS. Managed with [pnpm](https://pnpm.io/).

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22+ and pnpm.

Once the apps exist:

```bash
# API: http://localhost:8000
cd apps/api
uv sync
uv run uvicorn opensolve_pipe.main:app --reload --port 8000

# Web: http://localhost:5173
cd apps/web
pnpm install
pnpm dev
```

## Contributing

Bug reports, data requests and questions are welcome as [issues](https://github.com/ccirone2/opensolve-pipe/issues). Code contributions are accepted by invitation, to keep the project on one consistent vision. See [`docs/GOALS.md`](docs/GOALS.md) for the values that guide decisions.

## Disclaimer

OpenSolve Pipe is an engineering aid. Its results support, but do not replace, the judgment of a qualified engineer, and are provided without warranty.

## License

[GNU Affero General Public License v3.0](LICENSE). You may use, study, modify and share the code; if you run a modified version as a network service, you must offer its users the corresponding source code.
