#!/usr/bin/env bash
# Regenerate the frontend API types from the FastAPI OpenAPI schema, and the shared scenario
# fixture the web's client mirror is checked against (proposal scenario-manager.md §6.16).
# Pydantic models in apps/api are the source of truth; never edit the outputs by hand.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd ../api && uv run --quiet python -m opensolve_pipe.openapi) > src/lib/api/openapi.json
pnpm exec openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts
pnpm exec prettier --write src/lib/api/openapi.json > /dev/null
(cd ../api && uv run --quiet python -m tests.fixtures.scenario_cases) \
	> src/lib/utils/__fixtures__/scenario-cases.json
