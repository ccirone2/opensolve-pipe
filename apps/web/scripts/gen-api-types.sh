#!/usr/bin/env bash
# Regenerate the frontend API types from the FastAPI OpenAPI schema.
# Pydantic models in apps/api are the source of truth; never edit the outputs by hand.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd ../api && uv run --quiet python -m opensolve_pipe.openapi) > src/lib/api/openapi.json
pnpm exec openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts
pnpm exec prettier --write src/lib/api/openapi.json > /dev/null
