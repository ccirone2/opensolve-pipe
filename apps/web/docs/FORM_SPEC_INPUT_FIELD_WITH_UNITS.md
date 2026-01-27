# Engineering Input Field Specification

This document defines the functional requirements for engineering input fields used throughout OpenSolve Pipe. These inputs handle numerical values with integrated unit selection, designed for technical/engineering applications.

---

## Overview

An **Engineering Input** is a composite form control consisting of:
1. A **label** identifying the field
2. A **numerical input** for entering values
3. A **unit selector** for choosing measurement units

This pattern applies to all fields representing physical quantities (length, pressure, flow, temperature, etc.).

---

## Functional Requirements

### 1. Numerical Input

#### 1.1 Input Type
- Use `type="number"` for native numerical keyboard on mobile devices
- Accept decimal values (`step="any"` or specific step like `0.1`)
- Hide browser-native spin buttons (increment/decrement arrows)

#### 1.2 Value Handling
- Accept positive, negative, and zero values (unless constrained)
- Support scientific notation where appropriate
- Preserve precision as entered by user
- Empty input represents "no value" (distinct from zero)

#### 1.3 Constraints
- Support optional `min` and `max` attributes for bounded values
- Support `required` attribute for mandatory fields
- Validate constraints on blur or form submission

#### 1.4 Placeholder
- Display contextual placeholder text (e.g., "Enter length", "0.00")
- Placeholder should indicate expected input format or valid range

### 2. Unit Selector

#### 2.1 Structure
- Button displaying currently selected unit
- Dropdown list of available unit options
- Visual indicator (chevron) showing dropdown state

#### 2.2 Available Units
Each field type has a predefined set of valid units:

| Field Type | Example Units |
|------------|---------------|
| Length | mm, cm, m, km, in, ft, yd, mi |
| Diameter | in, mm, cm |
| Flow | GPM, LPM, m³/h, ft³/s |
| Pressure | psi, kPa, MPa, bar, Pa, atm |
| Head | ft_head, m_head |
| Temperature | °C, °F, K |
| Velocity | ft/s, m/s |
| Viscosity (kinematic) | ft²/s, m²/s, cSt |
| Viscosity (dynamic) | cP, Pa·s |
| Density | lb/ft³, kg/m³ |

#### 2.3 Default Unit
- Each field has a default unit based on project unit system (Imperial or SI)
- Default is pre-selected when component mounts

#### 2.4 Unit Persistence
- Selected unit persists for the session
- Project-level unit preferences are stored in project settings

### 3. Interaction Behaviors

#### 3.1 Focus States
- Input wrapper shows visual focus indicator when input is focused
- Focus indicator uses theme-appropriate accent color
- Focus state removed on blur

#### 3.2 Dropdown Behavior

**Opening:**
- Click on unit button opens dropdown
- Dropdown appears below the unit button
- Opening a dropdown closes any other open dropdowns

**Closing:**
- Click on a unit option closes dropdown (and selects that unit)
- Click outside dropdown closes it
- Press `Escape` key closes dropdown
- Tab away from component closes dropdown

**Scrolling:**
- If unit list exceeds max height, dropdown is scrollable
- Maximum dropdown height: ~200px

#### 3.3 Unit Selection
- Click on unit option selects it
- Selected unit is visually highlighted in dropdown
- Button text updates to show selected unit
- Selection triggers value conversion (if applicable)

#### 3.4 Keyboard Navigation
- `Escape` closes open dropdown
- `Tab` moves focus out of component (closes dropdown)
- Future: Arrow keys navigate dropdown options

### 4. Component States

#### 4.1 Default State
- Input is empty
- Unit shows default for field type
- Ready for user input

#### 4.2 Focused State
- Visual focus ring around input wrapper
- Input caret visible
- Ready for typing

#### 4.3 Filled State
- Input contains user-entered value
- Value displayed with appropriate precision

#### 4.4 Disabled State
- Entire component visually dimmed (reduced opacity)
- Input cannot receive focus
- Unit button is not clickable
- No pointer interactions allowed

#### 4.5 Required State
- Field marked as required for form validation
- Validation error shown if empty on submission

#### 4.6 Error State (future)
- Visual indicator for invalid values
- Error message displayed below input
- Triggered by: out-of-range values, invalid format

### 5. Value-Unit Coupling

#### 5.1 Display Value
- The displayed value is always in the currently selected unit
- Value updates immediately when unit changes (with conversion)

#### 5.2 Internal Value
- Backend always stores values in SI units
- Conversion happens at API boundary
- Internal calculations use SI regardless of display unit

#### 5.3 Unit Conversion
When user changes unit:
1. Current value is converted from old unit to new unit
2. Converted value replaces displayed value
3. Precision is maintained (or formatted appropriately)

Example: 25.4 mm → 1.0 in

### 6. Data Binding

#### 6.1 Two-Way Binding
- Component supports two-way binding to parent state
- Changes propagate up immediately on input
- External state changes update displayed value

#### 6.2 Change Events
- Emit change event when value changes
- Emit change event when unit changes
- Event payload includes: `{ value: number, unit: string }`

#### 6.3 Validation Events
- Emit validation event on blur
- Emit validation event on form submission attempt

---

## Component API

### Props

| Prop | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `label` | `string` | Yes | — | Field label text |
| `value` | `number \| null` | No | `null` | Current numerical value |
| `unit` | `string` | No | Field default | Selected unit |
| `units` | `string[]` | Yes | — | Available unit options |
| `placeholder` | `string` | No | `""` | Input placeholder text |
| `min` | `number` | No | — | Minimum allowed value |
| `max` | `number` | No | — | Maximum allowed value |
| `step` | `number \| "any"` | No | `"any"` | Input step increment |
| `disabled` | `boolean` | No | `false` | Disable the component |
| `required` | `boolean` | No | `false` | Mark as required |
| `id` | `string` | No | auto | Input element ID |
| `name` | `string` | No | — | Form field name |

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| `change` | `{ value: number \| null, unit: string }` | Value or unit changed |
| `input` | `{ value: number \| null, unit: string }` | Value changed (on each keystroke) |
| `blur` | `{ value: number \| null, unit: string }` | Input lost focus |
| `unitChange` | `{ oldUnit: string, newUnit: string, value: number \| null }` | Unit selection changed |

### Slots (optional)

| Slot | Description |
|------|-------------|
| `label` | Custom label content |
| `suffix` | Content after unit selector |

---

## Accessibility Requirements

### Keyboard
- Input is focusable via Tab
- Unit button is focusable via Tab
- Escape closes dropdown
- Enter on focused unit option selects it (future)
- Arrow keys navigate dropdown options (future)

### Screen Readers
- Label properly associated with input via `for`/`id`
- Unit button has `aria-haspopup="listbox"`
- Dropdown has `role="listbox"`
- Options have `role="option"`
- Selected option has `aria-selected="true"`
- Dropdown state indicated by `aria-expanded`

### Focus Management
- Focus trapped in dropdown when open (future)
- Focus returns to button after selection
- Focus visible at all times

---

## Usage Examples

### Basic Usage
```svelte
<EngineeringInput
  label="Pipe Length"
  bind:value={pipeLength}
  bind:unit={lengthUnit}
  units={['ft', 'm', 'in', 'mm']}
  placeholder="Enter length"
/>
```

### With Constraints
```svelte
<EngineeringInput
  label="Valve Position"
  bind:value={valvePosition}
  unit="%"
  units={['%']}
  min={0}
  max={100}
  step={0.1}
  placeholder="0-100"
/>
```

### Disabled State
```svelte
<EngineeringInput
  label="Calculated Flow"
  value={calculatedFlow}
  unit="GPM"
  units={['GPM', 'LPM']}
  disabled
/>
```

### Required Field
```svelte
<EngineeringInput
  label="Design Pressure"
  bind:value={designPressure}
  bind:unit={pressureUnit}
  units={['psi', 'kPa', 'bar']}
  required
/>
```

---

## Implementation Notes

### For Svelte Components
- Use Svelte stores for unit preference persistence
- Use reactive statements for unit conversion
- Use `createEventDispatcher` for custom events

### For Form Integration
- Component should work within `<form>` elements
- Support native form validation
- Support `FormData` extraction

### For Mobile
- Numerical keyboard should appear on mobile devices
- Touch targets should be at least 44x44px
- Dropdown should not overflow viewport

---

## Related Documents
- `docs/TSD.md` - Technical specification (units system)
- `apps/web/src/lib/utils/units.ts` - Unit conversion utilities
- `apps/web/src/lib/models/project.ts` - Project unit settings

---

**Last Updated:** 2026-01-27
