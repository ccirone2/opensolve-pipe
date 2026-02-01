---
title: "feat(web): Add pump operating mode and status controls to PumpPanel"
type: feat
date: 2026-02-01
issue: "#111"
---

## Overview

Update the PumpForm UI component to allow users to configure pump operating mode and status. This adds operating mode selection (Fixed Speed, Variable Speed, Controlled Pressure, Controlled Flow, Off), conditional fields based on mode, and viscosity correction toggle.

## Problem Statement / Motivation

The backend models already support pump operating modes and statuses (added in #106, #117), but the frontend PumpForm only has basic speed and status controls. Users need the ability to:

- Select different operating modes (VFD control, pressure/flow control)
- Configure mode-specific setpoints
- Enable/disable viscosity correction
- Set pump status in an advanced section

## Proposed Solution

Enhance `PumpForm.svelte` to add:

1. **Operating Mode Dropdown** - Select from 5 modes
2. **Conditional Fields** - Show/hide based on mode
3. **Status Selector** - In collapsible advanced section
4. **Viscosity Correction Toggle** - Checkbox with tooltip

## Technical Approach

### Files to Modify

#### `apps/web/src/lib/components/forms/PumpForm.svelte`

Add the following UI elements:

```svelte
<!-- Operating Mode Selector -->
<div>
  <label for="operating_mode">Operating Mode</label>
  <select id="operating_mode" value={component.operating_mode} onchange={...}>
    <option value="fixed_speed">Fixed Speed</option>
    <option value="variable_speed">Variable Speed (VFD)</option>
    <option value="controlled_pressure">Controlled Pressure</option>
    <option value="controlled_flow">Controlled Flow</option>
    <option value="off">Off</option>
  </select>
</div>

<!-- Conditional: Speed Ratio (Fixed/Variable Speed) -->
{#if component.operating_mode === 'fixed_speed' || component.operating_mode === 'variable_speed'}
  <NumberInput label="Speed Ratio" value={component.speed} ... />
{/if}

<!-- Conditional: Pressure Setpoint (Controlled Pressure) -->
{#if component.operating_mode === 'controlled_pressure'}
  <NumberInput label="Pressure Setpoint" value={component.pressure_setpoint} unit="psi" ... />
{/if}

<!-- Conditional: Flow Setpoint (Controlled Flow) -->
{#if component.operating_mode === 'controlled_flow'}
  <NumberInput label="Flow Setpoint" value={component.flow_setpoint} unit="GPM" ... />
{/if}

<!-- Viscosity Correction -->
<div>
  <label>
    <input type="checkbox" checked={component.viscosity_correction_enabled} ... />
    Apply viscosity correction
  </label>
</div>

<!-- Advanced Section (collapsible) -->
<details>
  <summary>Advanced</summary>
  <div>
    <label for="status">Status</label>
    <select id="status" value={component.status} ...>
      <option value="running">Running</option>
      <option value="off_check">Off (with Check)</option>
      <option value="off_no_check">Off (no Check)</option>
      <option value="locked_out">Locked Out</option>
    </select>
  </div>
</details>
```

### Implementation Steps

1. Import `PUMP_OPERATING_MODE_LABELS`, `PUMP_STATUS_LABELS` from models
2. Add operating mode dropdown after pump curve selection
3. Replace existing speed input with conditional rendering based on mode
4. Add pressure_setpoint and flow_setpoint inputs (conditional)
5. Add viscosity_correction_enabled checkbox
6. Move status to collapsible Advanced section
7. Update styles to match existing form patterns

## Acceptance Criteria

### Functional Requirements

- [x] Operating mode dropdown works with all 5 options
- [x] Conditional fields show/hide correctly based on mode
- [x] Speed ratio input with validation (0.0-1.5)
- [x] Setpoint inputs for controlled modes (pressure/flow)
- [x] Status dropdown in Advanced section
- [x] Viscosity correction checkbox
- [x] Changes update store correctly

### Non-Functional Requirements

- [x] Mobile-friendly layout
- [x] Consistent styling with other forms
- [x] Accessible (proper labels, keyboard navigation)

### Quality Gates

- [x] ESLint passes
- [x] Svelte check passes
- [x] No TypeScript errors

## Dependencies & Risks

### Dependencies

- #106 (TypeScript models with new types) - ✅ Complete
- #117 (Backend pump/valve model sync) - ✅ Complete

### Risks

| Risk | Mitigation |
|------|------------|
| Breaking existing pump forms | Keep default mode as "fixed_speed" |
| Missing model fields | Verify all fields exist in TypeScript models |

## References

### Internal References

- Existing PumpForm: `apps/web/src/lib/components/forms/PumpForm.svelte`
- TypeScript models: `apps/web/src/lib/models/components.ts:151-175` (PumpOperatingMode, PumpStatus)
- NumberInput component: `apps/web/src/lib/components/forms/NumberInput.svelte`

### Related Issues

- #106 - TypeScript models (completed)
- #112 - Valve status controls (similar pattern)
- #113 - Results display for pump outputs

---

Closes #111
