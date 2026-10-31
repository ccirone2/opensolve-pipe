# Web UI guide: the patterns new work follows

What the web app's layout is converging on, distilled from the owner's direction and its measured build (`proposals/build-density.md`, `proposals/ui-ux-refinement.md`). Read it before adding a field, a view, a toolbar or a dialog. Every pattern here is a reversible web default (D14); none outranks GOALS: correctness, traceability and longevity are never traded for density.

## The goals

- **Condensed, structured, quick to scan**, and staying so as features add fields: a new field or view gets dense, grouped, consistent UI by being declared, not by a layout redesign.
- **The defining inputs and the answer at a glance**, on a laptop and on a phone, with **nothing the user set, no default and no exception hidden** (D10, D15, GOALS §4.2, §4.6).
- **Phone and desktop equal in capability, each in its own layout** (GOALS §4.7): a table on desktop can be a list on a phone, a menu a sheet; never a feature on one only.
- **Measured, then enforced**: budgets live in tests, so a regression fails CI rather than review.

## Patterns

### Declare, don't lay out
- A Build field is one entry in `utils/field-registry.ts` (facet, tier, label, help, and how a plain field is drawn); its type, bounds, default, choices and scenario status come from `openapi.json` (D10). [`adding-a-field.md`](adding-a-field.md) is the recipe.
- The registry is the one label and unit table: Build, scenario notes, goal seek and the export read it. Guards fail on a schema field with no entry, an allow-listed field with no label, a varied number with no unit, a pressure that does not say gauge or not (D4).
- Facets, in this order on every type: Operation, Rating, Size and position, Fittings, Identification. Core fields are shown; the rest go in one **More**.

### Disclose without hiding
- A disclosure **says what it holds**: More names each field, "(default)" for those at their default; a reference summary carries its key values ("Calculated properties: 62.32 lb/ft³, 1.002 cP", "Per quantity: ft, in, psi, …", "Convergence (advanced): 100 iterations …", "Design checks: opt-in, all off", "Fields (3 of 8)").
- It **opens itself** for what the user must see: a set value, a scenario change or base-case note, a pending draft, a warning (an unconnected port, a mismatched size). It never closes itself.
- **Static help shows on focus** (`help`), floating under its field so nothing moves; **notes about the value always show** (`hint`: live results, a default's basis, a shared curve, warnings, errors, scenario notes). Tell them apart by what the text says, never by its class.
- Reference information sits one step away, the way Results shows the fluid: values in the summary, sources inside.

### Spend vertical space on content
- **One control height**: `--ctl-h` (Build and its menus 36 px with a mouse, 40 px on touch; 44 px where the suite holds touch targets: the header, Results' header buttons). Label beside control in a fixed column, stacking below a 21 rem container (reflow at 320 px); 4 px grid; tabular figures; 16 px input text (no iOS zoom).
- **Chrome earns its row** (≤ 15 % of the Build pane at 1280×800, tested): merge rows (actions beside tabs; Previous and Next in the top bar on wide screens), one-line banners and status lines with a mark (✓, ⚠, ⬣, spinner), icon-only buttons in narrow panes with the word kept for screen readers.
- **A bar that is used now and then becomes a menu** under the button that owns it (the case bar became the Scenarios menu); **don't repeat** what a tab, a chip or a status line already says.
- **Groups of tabs or pills are one row that scrolls sideways at every width**: edge shadows say there is more, a mouse wheel scrolls it sideways while it can move, the selected one is scrolled into view.

### Phones
- **Tables read as lists** below 640 px: a block per element headed by its name, values as label and value pairs that wrap, "—" out of sight. The table keeps explicit ARIA roles and its headings for screen readers, so CSS never unmakes its semantics.
- **What a heading did on desktop, a control does on a phone**: "Sort" (field + direction), sharing **one line** with Fields; labels shorten ("Sort", named "Sort by"; Fields to icon and count below 360 px) rather than wrap.
- **Pickers open as sheets** from the screen's foot at full width over a dimmed page (Fields), as native selects do; Done, a press outside or Escape closes them.
- **Two-value choices are segments** (one tap); three or more stay selects. Previous and Next stay at the bottom, under the thumb.

### Personal choices stay personal
- Layout and view choices (the pane split, the fields shown per table) are remembered **per browser** in `localStorage`, read and written in try/catch: a convenience, never project data, never in the link (D3, GOALS §4.5).
- Defaults favour the user's likely setting (a new project in US customary units), but **content keeps what it was made with**: the examples stay SI, a link without units shows SI, so links give the same numbers (GOALS §4.3).

### Accessibility is part of compact
- Visually hidden (`sr-only`), not `display: none`, for anything that must stay in the accessibility tree (a list's "—" cell, a phone's heading row, a title the tab already shows).
- A control's visible words are part of its accessible name (WCAG 2.5.3); targets ≥ 24 px (2.5.8); disclosures are native `<summary>`; axe-core runs in the e2e suite with disclosures open.

## How a new UI change ships

1. **Measure first** at 1280×800 and 390×844 (and 320 px): what the change adds per row, per screen; whether core fields stay on a phone's first screen.
2. **Declare** fields in the registry; reuse `FieldSections`, `ResultsTable`, the disclosure and sheet patterns above before writing new layout.
3. **Prove** with `tests/build-density.e2e.ts` (its budgets), the registry guards, Vitest and the whole e2e suite at both sizes, axe clean. A test that drove an old control drives the new one with the same assertions; never a looser one.
4. **Record** the owner's words and every choice with its reason in the feature's proposal (the build-density proposal's §13–§18 are the pattern), and the merge in [`history.md`](history.md).
