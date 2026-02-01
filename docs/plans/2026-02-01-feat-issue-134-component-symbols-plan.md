---
title: "feat: Complete Component Symbols for Schematic (#134)"
type: feat
date: 2026-02-01
---

## Overview

Complete the remaining SVG symbols for all component types following ISA-5.1 P&ID standards. Currently, 9 component types use the `GenericSymbol` fallback with abbreviations. This issue creates dedicated symbols for each.

## Problem Statement

The schematic viewer currently renders these components as generic boxes with abbreviations:

- HeatExchanger → "HX"
- Strainer → "STR"
- Orifice → "ORF"
- Sprinkler → "SPR"
- Plug → "PLG"
- ReferenceNode (ideal/non-ideal) → "REF"
- TeeBranch → "TEE"
- WyeBranch → "WYE"
- CrossBranch → "+"

Engineers expect recognizable P&ID symbols, not text labels.

## Proposed Solution

Create dedicated Svelte SVG symbol components for each missing type, following the established patterns in `PumpSymbol.svelte`, `ValveSymbol.svelte`, etc.

## Technical Approach

### Existing Pattern (Reference: `PumpSymbol.svelte:1-108`)

Each symbol follows this pattern:

1. Import `SymbolBase` wrapper
2. Define Props interface with standard properties
3. Use `$props()` with defaults
4. Render SVG graphics inside `SymbolBase`
5. Include connection points (circles/lines)

### File Structure

```text
apps/web/src/lib/components/schematic/symbols/
├── HeatExchangerSymbol.svelte  (new)
├── StrainerSymbol.svelte       (new)
├── OrificeSymbol.svelte        (new)
├── SprinklerSymbol.svelte      (new)
├── PlugSymbol.svelte           (new)
├── ReferenceNodeSymbol.svelte  (new)
├── TeeSymbol.svelte            (new)
├── WyeSymbol.svelte            (new)
├── CrossSymbol.svelte          (new)
├── index.ts                    (update exports)
└── ... (existing files)
```

### Symbol Designs (ISA-5.1 Reference)

| Component | Symbol Description |
|-----------|-------------------|
| HeatExchanger | Two concentric circles (shell-and-tube) or coil pattern |
| Strainer | Y-shape with mesh pattern (Y-strainer) |
| Orifice | Restriction plate - two vertical lines with gap |
| Sprinkler | Downward spray pattern from nozzle |
| Plug | Cap/dead-end - filled rectangle at pipe end |
| ReferenceNode | Diamond shape (boundary condition marker) |
| Tee | T-junction with three connection points |
| Wye | Y-junction with angled branch |
| Cross | Four-way intersection |

### Integration Points

1. Update `apps/web/src/lib/components/schematic/symbols/index.ts` - export new symbols
2. Update `apps/web/src/lib/components/schematic/SchematicComponent.svelte`:
   - Add type guards for new component types
   - Add rendering logic for each new symbol
   - Remove fallback to GenericSymbol for these types

## Implementation Phases

### Phase 1: Equipment Symbols

- [x] HeatExchangerSymbol.svelte
- [x] StrainerSymbol.svelte
- [x] OrificeSymbol.svelte
- [x] SprinklerSymbol.svelte
- [x] PlugSymbol.svelte
- [x] ReferenceNodeSymbol.svelte

### Phase 2: Branch Symbols

- [x] TeeSymbol.svelte
- [x] WyeSymbol.svelte
- [x] CrossSymbol.svelte

### Phase 3: Integration

- [x] Update index.ts exports
- [x] Update SchematicComponent.svelte
- [x] Add type guards to models

### Phase 4: Testing

- [x] Visual verification in schematic viewer
- [x] Theme switching (light/dark) - uses CSS variables
- [x] Hover/select states - inherited from SymbolBase

## Acceptance Criteria

- [x] All 9 component types have dedicated symbols
- [x] Symbols follow ISA-5.1 P&ID conventions
- [x] Symbols work in both light and dark themes (CSS variables)
- [x] Symbols are reusable Svelte components
- [x] No components fall through to GenericSymbol (except unknown types)

## References

### Internal References

- Existing symbol pattern: `apps/web/src/lib/components/schematic/symbols/PumpSymbol.svelte:1-108`
- SchematicComponent: `apps/web/src/lib/components/schematic/SchematicComponent.svelte:1-247`
- Symbol exports: `apps/web/src/lib/components/schematic/symbols/index.ts:1-16`

### External References

- ISA-5.1 P&ID Symbols Standard
- Crane TP-410 Flow of Fluids (valve/fitting symbols)

## Related Work

- Issue: #134
- Phase: 2 (Schematic Viewer)
