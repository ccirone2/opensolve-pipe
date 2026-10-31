# Documentation map

What each document provides and when to read it. Agents start from [`CLAUDE.md`](../CLAUDE.md), which is loaded into every session and points here.

**Precedence when documents disagree:** [`GOALS.md`](GOALS.md) → [`decisions/`](decisions/README.md) → [`PRD.md`](PRD.md) → [`SDD.md`](SDD.md) → [`TSD.md`](TSD.md). Follow the higher one and fix the lower one in the same change.

## The documents

| Document | Provides | Read when | Owner of changes |
|---|---|---|---|
| [`GOALS.md`](GOALS.md) | Mission, priority order, values, feature gates | Any judgment call | The project owner only |
| [`decisions/`](decisions/README.md) | D1–D23: the architecture rules and one record per built feature (model, law, flags, results, web defaults, version, proof) | Working on that feature; resolving a `CLAUDE.md Dn` citation | Builders, with the owner's answers quoted |
| [`PRD.md`](PRD.md) | What the product does, for whom; v1 scope and Later (§2.3); component and output requirements (§3); design checks (§5) | Asking whether something is in scope or how a user sees it | Updated with each decision |
| [`SDD.md`](SDD.md) | Architecture; data models (§4, one subsection per component and feature); REST contracts and link encoding (§5); errors (§8) | Changing a model, an endpoint or the link format | Updated with each decision |
| [`TSD.md`](TSD.md) | Stack (§2), file tree (§3), data files and model sketches (§4), solver implementation (§5), units (§6), web internals (§8), dev setup (§9), tests and the corpus proofs with their counts (§10), deployment settings (§11), decided and open questions (§12) | Implementing; proving a solver change; deploying | Updated with each decision; §10.4 and §12 with each merge |
| [`workflow.md`](workflow.md) | How a slice ships: gate, propose, build with independent reference cases, prove, record; agent practices; session report | Starting any feature or solver change | Builders |
| [`history.md`](history.md) | Where things stand: sessions, merges, the verified numbers of the latest gate run | Starting a session; before changing anything | Appended per merge |
| [`roadmap.md`](roadmap.md) | Open work in priority order, shelved items, Later lists by feature | Choosing or scoping the next slice | Trimmed per merge |
| [`ui-guide.md`](ui-guide.md) | The web UI's goals and patterns (declare don't lay out, disclose without hiding, chrome budget, menus over bars, phone lists and sheets, per-browser choices, accessibility) and how a UI change ships | Any change to the web app's layout | Updated when a UI pattern is decided |
| [`adding-a-field.md`](adding-a-field.md) | One page: how a field or a component type reaches the Build forms through the field registry, and what CI checks | Adding a model field or a component type | Updated with the registry |
| [`library-facts.md`](library-facts.md) | Verified quirks of `fluids`, CoolProp and EPANET/WNTR | Writing code against any of them | Anyone who finds one the hard way |
| [`deployment.md`](deployment.md) | The Cloud Run and Cloudflare Pages runbook, copy-and-paste | Deploying or checking a deployment | The owner |
| [`proposals/`](proposals/README.md) | One design proposal per feature, with the owner's answers, the review record and the as-built departures | Understanding why a feature is shaped as it is; designing its next slice | Frozen after the build, except the as-built section |
| [`prompts/`](prompts/) | The prompt v1 was built from (historical) and the short session-start prompt | Starting a fresh session by hand | Rarely |

Code and tests cite sections as `TSD §10.4`, `SDD §4.19`, `PRD §3.8`, `GOALS §4.2` and decisions as `CLAUDE.md D22`. Section numbers are therefore stable: add subsections at the end of a section rather than renumbering.

## Reading paths by task

- **Add a component type:** `workflow.md` → the closest decision (D18 equipment, D20 orifice, D23 relief valve: the pattern) and its proposal's §12 → `decisions/TEMPLATE.md` → TSD §4–§5, §10 → SDD §4 → `adding-a-field.md` for its Build form.
- **Change the solver or a loss law:** D6, D7, D9, D13 → TSD §5 and §10.4 (the corpus comparison) → `library-facts.md`.
- **Change a model, the API or the link format:** D2, D3, D10, D14 → SDD §4–§5 → TSD §4.7 (encoding), §7.
- **Web-only change:** PRD §3.2, §4.1 → the feature's decision ("Designers' web defaults") → TSD §8 → the `web/<topic>` branch rule in `CLAUDE.md`.
- **Scenarios, goal seek, export, compare:** D15, D16, D17 → TSD §5.7, §8.3.
- **Deploy or check a deployment:** `deployment.md` → TSD §11.
- **Decide what to build next:** GOALS §5 → `roadmap.md` → PRD §2.3–§2.4 → the relevant proposal's "Later" section.
