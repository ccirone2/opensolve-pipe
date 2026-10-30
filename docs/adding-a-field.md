# Adding a field to a Build form

One page for the next slice that adds a field or a component type (proposal [`proposals/build-density.md`](proposals/build-density.md)). The Build forms are laid out from one registry, `apps/web/src/lib/utils/field-registry.ts`, so a new field needs its entry, not a layout.

## 1. The model comes first

Add the field to the Pydantic model (the API's source of truth), then `pnpm gen:types` in `apps/web`. From then on the web app reads the field's type, bounds, default, choices and whether a scenario may change it (`x-override-fields`) from `src/lib/api/openapi.json`. Nothing of that is written again in the web app (CLAUDE.md D10).

## 2. The registry entry: the one required step

`pnpm test` now fails at `field-registry.test.ts` ("gives every field of *Schema* a section and a tier") until the field has an entry. Add it under its schema, at its place in the form's order:

```ts
// apps/web/src/lib/utils/field-registry.ts, in FIELD_REGISTRY.Pump
minimumFlow: {
	facet: 'operation',            // Operation · Rating · Size and position · Fittings · Identification
	tier: 'more',                  // core: always shown; more: in the form's More disclosure
	label: 'Minimum flow',
	help: 'The lowest flow the pump may run at continuously, from its datasheet.',
	input: { kind: 'number', category: 'flow', optional: true }
},
```

That is all for a **plain field**: a number in one unit category (`input.kind: 'number'`; a pressure must say `gauge: true` or `false`, which a test checks, D4) or a choice of the schema's values with a label for each (`input.kind: 'choice'`). `FieldSections` draws it in its section, `RegistryField` gives it its unit, schema bounds, label, help on focus, the scenario note when the allow-list names it (D15), and its undo step "change minimum flow" (`edit` overrides the wording).

How to choose:
- **Facet**: what the engineer looks for it under. Operation: what the element does in this case (status, setpoints, levels, assigned flows). Rating: what it is (curve, capacity, coefficients, set pressure). Size and position: elevation, ports, angles, taps, pipe size and length. Fittings: a pipe's fittings. Identification: names.
- **Tier**: core if an engineer sets or reads it to define the element; more if a cited default fits most projects. A field in More is never hidden from someone who set it: More names every field it holds, says "(default)" for each at its default, and opens itself while one holds a value the user set, a scenario change or a pending entry.
- **help** is static explanation and shows while the field has focus. A note about the current value (a live result, a "default" label, a shared-curve warning) is a `hint` and always shows.

## 3. When the field needs its own editor

A field whose input is not one number or one choice (a union with a kind select, a draft that must be complete before it is stored, a table) is drawn by its type's form: leave out `input` and handle its path in the form's `field` snippet:

```svelte
<FieldSections {component}>
	{#snippet field(path, label)}
		{#if path === 'minimumFlow'}<MyEditor {label} ... />{/if}
	{/snippet}
</FieldSections>
```

A union's sub-fields each get an entry too (`capacity.letter`, `rating.value`), so the guard still sees them; `whole: true` is for an editor that owns every sub-field (a valve's resistance).

## 4. What CI checks for you

- `field-registry.test.ts`: every field of every component schema (and `Port`, `PipeDefinition`, `PumpCurve`) has an entry; no entry names a field the schema lacks; every pressure states gauge or not.
- `tests/build-density.e2e.ts`: every component's core fields are on the first screen of a 390×844 phone; chrome is at most 15 % of the Build pane at 1280×800; a pipe size and a valve's status stay 2 and 1 actions from their panel; axe-core finds no WCAG 2.2 A/AA violation in Build with its disclosures open.

If the density spec fails after your entry, the field is probably core when it should be more, or a core section has grown past a phone's first screen: move the field to More, or record why it must stay core in the proposal and rebalance the type's core fields.

## 5. A new component type

Add its schema to the model (it joins `Project.components`); the guard then asks for an entry for each of its fields. Plain fields need nothing else. If it has its own editors, add `forms/<Type>Form.svelte` with a `FieldSections` and its `field` snippet, and a branch in `ComponentPanel.svelte`. Put its explanation of the model in the `about` snippet: it is shown last in More.
