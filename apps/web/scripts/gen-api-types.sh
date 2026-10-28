#!/usr/bin/env bash
# Regenerate the frontend API types from the FastAPI OpenAPI schema, the shared scenario and
# goal-seek fixtures the web's client mirrors are checked against (proposals scenario-manager.md
# §6.16, goal-seek.md §7.5), the export's input fixture, real API responses the export model
# and its committed workbook are built from (export.md §7.2), and the pump-group fixture, real
# solve and group-curve responses the Pumps together card is tested with (pump-groups.md §9.1).
# Pydantic models in apps/api are the source of truth; never edit the outputs by hand.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd ../api && uv run --quiet python -m opensolve_pipe.openapi) > src/lib/api/openapi.json
pnpm exec openapi-typescript src/lib/api/openapi.json -o src/lib/api/schema.d.ts
pnpm exec prettier --write src/lib/api/openapi.json > /dev/null
(cd ../api && uv run --quiet python -m tests.fixtures.scenario_cases) \
	> src/lib/utils/__fixtures__/scenario-cases.json
(cd ../api && uv run --quiet python -m tests.fixtures.goal_seek_cases) \
	> src/lib/utils/__fixtures__/goal-seek-cases.json
(cd ../api && uv run --quiet python -m tests.fixtures.export_input) \
	> src/lib/utils/__fixtures__/export-input.json
pnpm exec prettier --write src/lib/utils/__fixtures__/export-input.json > /dev/null
(cd ../api && uv run --quiet python -m tests.fixtures.pump_groups_input) \
	> src/lib/utils/__fixtures__/pump-groups-input.json
