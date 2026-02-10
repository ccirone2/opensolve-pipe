# Issue #196: Replace 'Mixed' Unit Mode with 'Display Units'

## Current Implementation

- **Backend:** `UnitSystem` enum has three values: `IMPERIAL`, `SI`, `MIXED`
- **Frontend:** `UnitSystem` type is `'imperial' | 'si' | 'mixed'`
- **UI:** Three-button toggle (Imperial / SI / Mixed) in Config > Units section
- **SYSTEM_PRESETS:** Each system maps to a preset of unit strings per physical quantity
- **Mixed preset:** Uses a combination of SI and Imperial units (e.g., `m` for length, `in` for diameter, `bar` for pressure)

## Problem

The "Mixed" option is ambiguous -- users don't know what units will be used. The issue requests:

1. Remove the "Mixed" button
2. Rename section to "Display Units"
3. Keep only Imperial and SI as display presets

## Changes

### Backend (`apps/api/src/opensolve_pipe/models/units.py`)

- Remove `MIXED` from `UnitSystem` enum
- Remove `UnitSystem.MIXED` entry from `SYSTEM_PRESETS`
- Add a `field_validator` on `UnitPreferences.system` for backward compatibility: if `'mixed'` is received, coerce to `'imperial'`

### Frontend (`apps/web/src/lib/models/units.ts`)

- Remove `'mixed'` from `UnitSystem` type
- Remove `mixed` entry from `SYSTEM_PRESETS`

### Frontend (`apps/web/src/lib/components/workspace/ProjectConfigPanel.svelte`)

- Remove `{ id: 'mixed', label: 'Mixed' }` from the `unitSystems` array
- Change the section heading from "Units" to "Display Units"

### Frontend (`apps/web/src/lib/components/workspace/ProjectSummary.svelte`)

- Update the unit system label display (was showing "mixed units" in uppercase)

### Backend Tests (`apps/api/tests/test_models/test_units.py`)

- Remove `test_create_mixed_preferences` test
- Update `test_all_unit_systems` to not check for MIXED
- Add backward compatibility test: loading `'mixed'` coerces to `'imperial'`

## Backward Compatibility

- Existing URL-encoded projects with `unit_system: 'mixed'` will be treated as `'imperial'`
- Backend validator coerces 'mixed' -> 'imperial' on deserialization
- Frontend: if a loaded project has system='mixed', `createUnitPreferencesFromSystem` will fall back to 'imperial'
