# OpenSolve Pipe

A free, browser-based tool for steady-state hydraulic analysis of pressurized pipe networks: pumps, valves, fittings, branching and looped systems. No installation and no account. A project lives entirely in its URL, so sharing a design means sharing a link.

> **Status:** v1 (core analysis MVP) is implemented in this repository — API, network solver, reference suite and web app — deployed by the owner (Cloudflare Pages and Google Cloud Run), and not yet a stable release: links and results may change between versions until the owner declares one (CLAUDE.md D14). `docs/prompts/build-v1.md` is the plan it was built from.

## Who it's for

Students checking hand calculations, field technicians sizing a retrofit, and process or consulting engineers who need professional-grade results without a desktop license.

## v1 scope

- Branching and looped networks of pipes and fittings, with reservoirs, reference pressure nodes, assigned-flow nodes (a fixed demand or supply), tees, wyes and caps
- Fixed-speed pumps and speed-controlled (VFD) pumps holding a flow setpoint, isolation and check valves, and pressure-reducing, pressure-sustaining and flow-control valves
- Water, glycol solutions and user-defined fluids
- Darcy–Weisbach / Colebrook friction, with K-factor minor losses from Crane TP-410 (via the `fluids` library)
- Results: flows, velocities, head loss, pressures, HGL/EGL, pump operating point, system curve, NPSH available
- Scenarios: named cases of one network (a pump off, a valve closed, a larger pipe, another fluid temperature) kept as changes of the base case, solved one at a time or all together and compared side by side
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

## Deployment

The web app is meant for Cloudflare Pages and the API for Google Cloud Run; neither is deployed yet. [`docs/TSD.md`](docs/TSD.md) §11 explains each setting below and cites its source, and it lists the checks to run after every deployment and the costs. Ordinary use fits within both providers' free tiers.

**1. The API on Cloud Run.** You need a Google Cloud project with billing enabled and the [gcloud CLI](https://cloud.google.com/sdk/docs/install). Replace `PROJECT_ID`, `PROJECT_NUMBER` and `PAGES_PROJECT` (the name you will give the Pages project):

```bash
gcloud auth login
gcloud config set project PROJECT_ID
gcloud config set run/region us-central1
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com

# Let Cloud Build's default service account build and push the image
gcloud projects add-iam-policy-binding PROJECT_ID --role=roles/run.builder \
  --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com

# An image repository that deletes every image except the 3 most recent
# (the Delete rule matches every image; the Keep rule wins where both match)
gcloud artifacts repositories create opensolve-pipe --repository-format=docker --location=us-central1
cat > /tmp/cleanup.json <<'EOF'
[{"name": "delete-all", "action": {"type": "Delete"}, "condition": {"tagState": "any"}},
 {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 3}}]
EOF
gcloud artifacts repositories set-cleanup-policies opensolve-pipe --location=us-central1 --policy=/tmp/cleanup.json

# The API's own identity; it calls no Google API, so it has no roles
gcloud iam service-accounts create opensolve-pipe-api

# Build (--ignore-file uploads only what the image needs) and deploy
IMAGE=us-central1-docker.pkg.dev/PROJECT_ID/opensolve-pipe/api:$(git rev-parse --short HEAD)
gcloud builds submit apps/api --ignore-file=.dockerignore --tag "$IMAGE"
gcloud run deploy opensolve-pipe-api --image "$IMAGE" \
  --service-account=opensolve-pipe-api@PROJECT_ID.iam.gserviceaccount.com --allow-unauthenticated \
  --cpu=1 --memory=1Gi --concurrency=20 --timeout=60 --min-instances=0 --max-instances=1 \
  --set-env-vars=CORS_ORIGINS=https://PAGES_PROJECT.pages.dev

# Keep Cloud Run's own request log, which records client addresses and query strings, out of storage
gcloud logging sinks update _Default \
  --add-exclusion='name=no-run-request-logs,filter=LOG_ID("run.googleapis.com/requests")'

gcloud run services describe opensolve-pipe-api --format='value(status.url)'   # the API's URL
```

Then, in the console under Billing → Budgets & alerts, create a spend cap budget for this project and Cloud Run (TSD §11.5). Don't skip it. One instance bounds CPU and memory charges, at about $64 a month, but request fees and outbound data are charged per request and per byte, and only the spend cap bounds them.

**2. The web app on Cloudflare Pages.** You need a Cloudflare account that can see this GitHub repository.
- In Workers & Pages → Create → Pages, connect this repository and name the project `PAGES_PROJECT`.
- Use these build settings:
  - production branch `main`;
  - framework preset *None*;
  - root directory `apps/web`;
  - build command `pnpm build`;
  - build output directory `build`.
- Set these build variables:
  - `PUBLIC_API_URL` = the API's URL, without a trailing slash;
  - `NODE_VERSION` = `22.22.0`;
  - `PNPM_VERSION` = `10.28.0`.
- Under Settings → Build:
  - set *Build watch paths* to include `apps/web/*`;
  - set *Branch control → Preview branches* to *None*.
- Leave Web Analytics (under Metrics) **off**: the app has no analytics, cookies or third-party requests (GOALS §4.5).
- If the project's `*.pages.dev` address differs from `https://PAGES_PROJECT.pages.dev`, or when you add a custom domain, list every origin in `CORS_ORIGINS`: `gcloud run services update opensolve-pipe-api --update-env-vars='^;^CORS_ORIGINS=https://a.pages.dev,https://example.org'`.
- On a custom domain whose zone is on Cloudflare, keep the zone's Web Analytics, Bot Fight Mode and Email Address Obfuscation off (TSD §11.1).

**3. Check** the deployment with TSD §11.4. This step matters most for the client-address check. Google documents neither the address its proxy connects from nor where it puts the client's address in `X-Forwarded-For`, so only this check shows that each user gets their own rate limit. Run it over IPv6 too where you can, since the API keys an IPv6 client by its /64. If it fails, TSD §11.2 shows how to find out why.

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
