> Discipline findings for [`../build-density.md`](../build-density.md), written 2026-10-30 against the running app before the build (`5693197`). Paths under `/tmp/claude-0/` are the reviewer's scratch evidence, not kept. The proposal's §4 says what was adopted.

# Field registry: architecture findings (design item 4)

Paths below are under `apps/web/src/lib/`. Line numbers are from HEAD `5693197` (branch `web/build-density`).

## 0. What exists today: five per-field tables, and enums copied into the forms

A field's presentation is written out in up to six places, each keyed by the same path string:

| Concern | Where | Fallback when a case is missing |
|---|---|---|
| label in the form | literal `label="…"` in each form | none |
| label for scenarios, undo text, goal seek, Reset | `utils/scenarios.ts:1164-1222` `fieldLabelFor` (+ `PIPE_FIELD_NAMES` :253) | `humanize`, which leaves camelCase as is (`minimumFlow`). Caught only by `scenarios.test.ts:842` |
| lowercase label in rule messages | `utils/labels.ts:190` `fieldLabel` (used by `validate.ts:696`) | the raw path |
| unit and gauge for goal seek | `utils/goal-seek.ts:658-716` `variableSpec`; order in `FIELD_ORDER` :809 | **silently `dimensionless`** |
| unit and gauge in scenario value text | `utils/scenarios.ts:1362-1455` `changeValueText` | **silently `dimensionless`** |
| unit and gauge in the export | `utils/export/tables.ts:1238-1292` `changeCategory` | **silently `dimensionless`** |

`ws.componentChange(...).label` (`state/workspace.svelte.ts:545`) already comes from `fieldLabelFor`. So the scenario label table is in place, and the form literals repeat it by hand. **Unify like this:** the registry becomes the one label and unit table. `fieldLabelFor` keeps its signature (it has 9 callers and tests) and becomes a lookup in the registry. `labels.fieldLabel` becomes `inSentence(fieldLabelFor(…))`. The number cases of the three unit switches read `unitOf()`; only their real special cases stay (the K/Cv prefix, demand/supply wording, the default texts).

The forms also copy schema enums, against the rule in D10 that rules are never copied: `IsolationValveForm:12` `TYPES`, `CheckValveForm:13,20`, `ControlValveForm:13-14`, `ReliefValveForm:31`, and PumpForm's `on`/`off`. With the registry, option values come from the schema's `enum` and the registry holds only their labels. A guard checks the labels against the enum.

## 1. Registry API (`utils/fields.ts`, pure TS, testable without the DOM)

**Read from `openapi.json`, never declared:** whether the field exists, its type, its bounds (per holder schema, plus `x-ordered-fields` through `orderedBounds`), `default`, `enum`, `required`, whether it is nullable, whether a scenario may change it (`x-override-fields`), and `const` (structural, skipped).
**Declared in the registry (web presentation):** facet, tier, order, label, unit category, the pressure reference, hint, select option labels, and whether the field is custom.

**Path keys** are dot-joined camelCase paths from the target. Where a scenario or goal-seek allow-list has the value, the key is that list's key: `control.setpoint`, `rating.value`, `capacity.letter`, `capacity.area`, `resistance`. I checked these against `x-override-fields` and `x-goal-variables`. Note that `resistance` is the key even though its goal path is `resistance.value`. A union path such as `capacity.area` does not depend on the member: `schemaField` returns every holder schema (Effective and Certified), as `holdersOf` does today. A whole union (`rating`, `capacity`, `resistance`) or an object a form drafts (`control`) is one **custom** entry. Its leaves are `within` entries, which carry only a label and a unit, for scenarios and goal seek.

```ts
export type Facet = 'operation' | 'rating' | 'geometry' | 'losses' | 'references';
export type Tier = 'core' | 'more';
type Of<T> = T | ((owner: any) => T);                  // owner: the component or pipe
export type PressureRef = 'gauge' | 'absolute' | 'difference';
export type NumberInput = { kind: 'number'; unit: Of<UnitCategory>; pressure?: Of<PressureRef>; integer?: boolean };
export type SelectInput = { kind: 'select'; options: Readonly<Record<string, string>>; none?: string };
interface Placed { facet: Facet; tier: Of<Tier>; order: number; label: Of<string>; hint?: Of<string> }
export type FieldEntry =
  | (Placed & { input: NumberInput | SelectInput; custom?: false })       // rendered generically
  | (Placed & { custom: true; input?: NumberInput | SelectInput })        // a snippet renders it
  | { within: string; label: Of<string>; input?: NumberInput | SelectInput }; // a leaf of a custom entry
export const FIELDS: Readonly<Record<string /*schema*/, Readonly<Record<string /*path*/, FieldEntry>>>>;

export interface SchemaField { holders: readonly string[]; type: 'number'|'integer'|'string'|'boolean'|'object';
  required: boolean; nullable: boolean; default?: unknown; enum?: readonly string[]; overridable: boolean }
export function schemaField(schema: string, path: string): SchemaField | null;  // walks $ref, anyOf-null, oneOf
export function boundsOf(schema: string, path: string, owner: unknown): Bounds;  // holder bounds ∩ orderedBounds
export function buildPaths(schema: string): string[];   // the guard's enumeration, below
export function layoutOf(schema: string, owner: unknown): Section[];  // facets → core/more rows, sorted
export function labelOf(schema: string, path: string, owner?: unknown): string | null;
export function unitOf(schema: string, path: string, owner?: unknown): { category: UnitCategory; options: { gauge?: boolean; absolute?: boolean } } | null;
export const STRUCTURAL = new Set(['id', 'name', 'type', 'ports']);  // edited by the header and PortsEditor
```

`elevation` is a `COMMON` entry that is merged into every component schema, with tier and order set per type (design item 7). Afterwards `ComponentPanel.svelte:145-156` no longer renders it.

**`buildPaths(schema)`**, for the guard, walks the schema's `properties`:
- skip `STRUCTURAL` and every `const` property;
- unwrap `anyOf [X, null]`;
- stop at a path whose entry is custom;
- for a `$ref` object, descend;
- for a `oneOf` of `$ref`s, descend into each member, skip the `kind` discriminator, and merge the members' leaves;
- for an array, stop (structural).

It runs over `COMPONENT_SCHEMAS` (`model-rules.ts:121`) and `PipeDefinition`. A pipe's `spec` is a custom entry whose covered keys are `OVERRIDE_FIELDS.PipeDefinition.spec.keys`, read from the schema and not copied.

**Vitest guard (`fields.test.ts`):**
1. Every `buildPaths` leaf has an entry.
2. Every entry and `within` resolves through `schemaField`.
3. Every `x-override-fields` and `x-goal-variables` key of a component schema or `PipeDefinition` has a label that is not humanized. This replaces the label half of `scenarios.test.ts:842`.
4. `kind:'number'` only on number or integer fields; for every select, `Object.keys(options)` equals the schema's `enum`.
5. Evaluated on `createComponent(kind)` for every kind: every `unit:'pressure'` resolves a `pressure`.

Check 5 makes the D4 gauge-or-difference choice explicit for each field. Today the forms differ: `surfacePressure` is gauge, `crackingPressure` and `setPressure` are differences.

## 2. Layout component (`components/panel/FieldLayout.svelte`)

```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { layoutOf, boundsOf, setPath, type Row } from '$lib/utils/fields';
  import { inSentence } from '$lib/utils/labels';
  let { schema, owner, target, edit, fields = {}, pending = new Set<string>(), after }: {
    schema: string; owner: object; target: ChangeTarget;
    edit: (path: string, value: unknown, undoLabel: string) => boolean;
    fields?: Readonly<Record<string, Snippet<[Row]>>>;   // per-path escape hatch
    pending?: ReadonlySet<string>;                        // a form's own warnings (a draft) open the section
    after?: Snippet;                                      // the type's closing hint
  } = $props();
  const ws = useWorkspace();
  // Row: { path, entry, label, hint, schemaField, value, set, change, error }
  //   set    = value non-null and not the schema default (a custom entry: any covered key set)
  //   change = ws.change(target, path) when schemaField.overridable, else null
  //   error  = ws.issues whose pointer is under this path (SchemaIssue.pointer, validate.ts:225)
  const sections = $derived(layoutOf(schema, owner).map((s) => s.withState(ws, target)));
  let opened = $state<Record<string, boolean>>({});      // the user's choice, per facet; reset by {#key component.id}
</script>

{#snippet field(row: Row)}
  {#if fields[row.path]}{@render fields[row.path]?.(row)}
  {:else if row.entry.input.kind === 'number'}
    <NumberField label={row.label} value={row.value} category={row.unit.category} {...row.unit.options}
      units={ws.units} bounds={boundsOf(schema, row.path, owner)} optional={row.schemaField.nullable}
      hint={row.hint} change={row.change} error={row.error}
      onchange={(v) => (v !== null || row.schemaField.nullable) && edit(row.path, v, `change ${inSentence(row.label)}`)} />
  {:else}
    <SelectField label={row.label} value={row.value ?? '__none__'} hint={row.hint} change={row.change}
      options={[...(row.entry.input.none ? [{ value: '__none__', label: row.entry.input.none }] : []),
                ...row.schemaField.enum!.map((v) => ({ value: v, label: row.entry.input.options[v] }))]}
      onchange={(v) => edit(row.path, v === '__none__' ? null : v, `change ${inSentence(row.label)}`)} />
  {/if}
{/snippet}

{#each sections as s (s.facet)}
  <section aria-labelledby="{s.facet}-h" class="field-grid">
    <h3 id="{s.facet}-h" class="section-h">{FACET_LABELS[s.facet]}</h3>
    {#each s.core as row (row.path)}{@render field(row)}{/each}
    {#if s.more.length}
      {@const forced = s.more.some((r) => r.change?.changed || r.change?.setBy.length || r.error || pending.has(r.path))}
      {@const nSet = s.more.filter((r) => r.set).length}
      <details open={forced || (opened[s.facet] ?? nSet > 0)}
               ontoggle={(e) => (opened[s.facet] = e.currentTarget.open)}>
        <summary>More{#if nSet}<span class="count"> · {nSet} set</span>{/if}</summary>
        {#each s.more as row (row.path)}{@render field(row)}{/each}
      </details>
    {/if}
  </section>
{/each}
{@render after?.()}
```

Notes:
- `setPath` writes nested paths and uses `withOptional` (`utils/piping`) for a nullable value cleared to null.
- `forced` must reopen the section when a new reason appears. Use an `$effect` on the count of forced rows that clears `opened[facet]`, because a user who collapsed it would otherwise hide a new error.
- NumberField's own parse errors need nothing extra: the field has focus, so its section is open.
- The schema `default` also lets the generic field show D10's "default" mark when value equals default. The owner decides whether to show it.

**PumpForm with the layout.** The draft logic stays as it is (lines 23-126). Only the markup changes.

```ts
// fields.ts
Pump: {
  status:  { facet: 'operation', tier: 'core', order: 10, label: 'Status', input: { kind: 'select', options: PUMP_STATUS_LABELS } },
  control: { facet: 'operation', tier: 'core', order: 20, label: 'Control', custom: true },
  'control.setpoint': { within: 'control', label: 'Flow setpoint', input: { kind: 'number', unit: 'flow' } },
  'control.minSpeed': { within: 'control', label: 'Minimum speed', input: { kind: 'number', unit: 'fraction' } },
  speed:   { facet: 'operation', tier: 'core', order: 30, custom: true, label: (p: Pump) => (p.control ? 'Maximum speed' : 'Speed'),
             input: { kind: 'number', unit: 'fraction' } },
  curveId: { facet: 'rating', tier: 'core', order: 10, label: 'Pump curve', custom: true },
  elevation: elevation('core', 90),
},
```
```svelte
<FieldLayout schema="Pump" owner={component} target={{ kind: 'component', componentId: component.id }}
  edit={(path, v, label) => ws.editComponent<Pump>(component.id, label, (c) => setPath(c, path, v))}
  fields={{ control: controlRow, speed: speedRow, curveId: curveRow }}
  pending={problem ? new Set(['control']) : undefined} />
{#snippet controlRow(row)} <!-- today's Control select, note, setpoint and minSpeed (lines 144-195);
   labels from labelOf('Pump', 'control.setpoint', component) --> {/snippet}
{#snippet speedRow(row)} <NumberField label={row.label} … onchange={(v) => v !== null && setSpeed(v)} /> {/snippet}
{#snippet curveRow(row)} <!-- curve picker + PumpCurveEditor (lines 211-243) --> {/snippet}
```

`ComponentPanel` swaps its 25-line if-chain (158-182) for `FORMS[schema]`, a map that lists only the types with form-local state: Pump, Equipment, ReliefValve, Orifice, ControlValve. Every other type renders `<FieldLayout>` directly. Valve `resistance` is one shared custom control (`ValveResistanceField`, its `defaultLabel` taken from the entry's hint), so `ReservoirForm`, `IsolationValveForm`, `CheckValveForm`, `AssignedFlowForm` and `ReferenceNodeForm` (184 lines) become registry entries of about 5 lines per field.

## 3. Cost of the next field (counted)

Example: an optional `minimumFlow` (m³/s, nullable) on `Pump`. The API side (Pydantic, then `pnpm gen:types`) is the same in both cases, and the generated files are not hand-edited.

**Today:**

| File | Lines | What |
|---|---|---|
| `forms/PumpForm.svelte` | +1 import (`schemaBounds`), +16 | the NumberField block: label, value, category, units, bounds, optional, hint, change, onchange with `withOptional`; the pattern of `CheckValveForm:38-51` or `OrificeForm:112-123` |
| *If scenarios may change it (in `x-override-fields`):* | | |
| `utils/scenarios.ts` | +2 | `fieldLabelFor` case; without it `scenarios.test.ts:842` fails |
| `utils/scenarios.ts` | +1 | `changeValueText` case; **silent `dimensionless` if missed** |
| `utils/export/tables.ts` | +1 | `changeCategory` case; **silent if missed** |
| *If goal seek may vary it:* | | |
| `utils/goal-seek.ts` | +1 | `variableSpec`; **silent** |
| `utils/goal-seek.ts` | +1 | `FIELD_ORDER` |
| `utils/goal-seek.ts` | +1-3 | search range |
| *If it is in an `x-ordered-fields` pair:* | | |
| `utils/labels.ts:190` | +1 | |

That is 17 lines in 1 file for a plain field. A field a scenario may change takes about 25 lines in 5 files, 3 of them silent switches. Nothing fails if the form line is forgotten altogether: the field is then reachable only through the link.

**With the registry:**

| File | Lines | What |
|---|---|---|
| `utils/fields.ts` | +6 | `minimumFlow: { facet: 'operation', tier: 'more', order: 40, label: 'Minimum flow', hint: '…', input: { kind: 'number', unit: 'flow' } }` |

That is one file and 0 other lines, whether or not scenarios or goal seek may change it: the label, unit, order and scenario note all come from the entry, and bounds, nullability and the allow-list from the schema. The goal-seek search range is an algorithm, not presentation, and stays in `goal-seek.ts`; a default case covers it. The guard test **fails** until the entry exists. The same holds for an optional number on `Equipment` (today about 18 lines in `EquipmentForm` plus the scenario switches), as long as it is a plain sibling of `rating` and not a leaf of the rating union. A union leaf adds one `within` entry and is edited in its custom snippet.

**One-time cost:**
- About 55 entries at about 5 lines each, roughly 280 lines.
- About 184 form lines deleted.
- About 45 lines of `fieldLabelFor`, `PIPE_FIELD_NAMES` and `labels.fieldLabel` replaced by roughly 8 lines.
- About 40 number cases across the three unit switches replaced by `unitOf`.
- Tests that assert labels (`equipment.test.ts:240`, `relief.test.ts:786`, `orifice.test.ts:767`) keep passing unchanged, because `fieldLabelFor`'s output is kept.
