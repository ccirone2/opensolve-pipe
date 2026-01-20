# Implementation Plan: Issue #50 - Fix GitHub Actions CI Test Failures

## Issue Summary

Two CI checks are failing in GitHub Actions:

1. Backend unit tests for `UnitPreferences` - head unit mismatch
2. Frontend E2E tests - URL patterns and page element selectors

## Root Cause Analysis

### 1. Backend Tests

The `UnitPreferences` model uses `"ft_head"` and `"m_head"` as valid head unit values (with `_head` suffix to distinguish from length units), but the tests expect `"ft"` and `"m"`.

**Model definition (`models/units.py`):**

- Default: `head: str = "ft_head"`
- SI preset: `"head": "m_head"`

**Tests (`test_units.py`):**

- Expects: `assert prefs.head == "ft"`
- Expects: `head="m"` to be valid

### 2. E2E Tests

The E2E tests have outdated expectations:

1. **URL Pattern:** Tests expect `/p/{encoded}/` with trailing slash, but app uses `/p/{encoded}` without trailing slash
2. **Page Elements:** Tests look for `heading` role with "New Project" but the actual implementation uses a button with the project name

## Implementation Steps

### Step 1: Fix Backend Unit Tests

Update `apps/api/tests/test_models/test_units.py` to use correct head unit values:

1. Change `assert prefs.head == "ft"` to `assert prefs.head == "ft_head"`
2. Change `head="m"` to `head="m_head"` in SI preferences test
3. Change `head="ft"` to `head="ft_head"` in mixed preferences test

### Step 2: Fix E2E Tests

Update `apps/web/e2e/homepage.test.ts`:

1. Change URL assertion from `/\/p\//` to `/\/p/`

Update `apps/web/e2e/project-workflow.test.ts`:

1. Update `goto('/p/')` to `goto('/p')`
2. Update element selectors to match actual UI structure

## Files to Modify

1. `apps/api/tests/test_models/test_units.py`
2. `apps/web/e2e/homepage.test.ts`
3. `apps/web/e2e/project-workflow.test.ts`

## Acceptance Criteria

- [ ] Backend tests pass locally
- [ ] E2E tests pass locally
- [ ] GitHub Actions CI checks pass
