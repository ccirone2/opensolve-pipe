# OpenSolve Pipe — Goals and Values

**Purpose:** guide decisions. When a choice isn't settled by the specs, decide it here: find the values involved, apply the priority order, and check the feature gates.

**Status:** v1.0, October 2026. Changes to this document are deliberate decisions, made by the project owner.

---

## 1. Mission

Give working engineers a free, zero-install hydraulic analysis tool whose results they can **trust and check** — accurate enough to design with, transparent enough to sign off on, and shareable with a link.

**Primary user: working engineers** — process, maintenance and consulting engineers doing real design work. Students and field technicians are welcome and benefit from the same tool, but when needs conflict, depth and rigor for working engineers win.

## 2. What success looks like

**12 months after v1: trusted by professionals.** Engineers use OpenSolve Pipe for real deliverables and cite it as their calculation tool.

Signals that we're getting there:

- Engineers reproduce results from established tools and hand calculations, and report that they match
- Shared links appear in real design reviews and client correspondence
- Bug reports are about edge cases, not basic correctness

Not success measures: raw user counts, revenue, or contributor numbers. Those may come, but no decision is made to chase them at the expense of trust.

## 3. Priority order

When goals conflict, the higher one wins.

1. **Correctness** — A wrong answer is the worst outcome. Never trade it for speed, features, polish or convenience.
2. **Traceability** — Every result can be checked: inputs, equations, correlations, data sources and assumptions are visible. A correct result the user can't verify is not good enough.
3. **Longevity** — A shared link opens and gives the same answer indefinitely, or explains exactly why the answer changed.
4. **Accessibility** — Core analysis stays free, zero-install and account-free.
5. **Privacy** — Project data stays with the user; the app collects nothing by default.
6. **Usability** — Fast, uncluttered, equally good on desktop and mobile.
7. **Breadth** — More components, fluids and features.

Correctness outranks longevity: if a method is found to be wrong, it is fixed even though old links will now give different results — and the change is disclosed to the user when the link is opened (§4.3).

## 4. Values

### 4.1 Correctness, proven not assumed

- Every calculation method is verified against an independent reference before it ships: closed-form solutions, published worked examples (e.g., Crane TP-410), or established solvers (EPANET for water).
- Every coefficient, correlation and property table cites its source. No uncited numbers.
- Physical rigor beats simplicity, **with sensible defaults**: use the more accurate method, and give each extra input a cited default so simple models stay simple to build.
- When a model is outside a correlation's validated range, say so.

### 4.2 Show the work

- Any result can be traced to the inputs, equations, correlations and data that produced it — per element, not just in the documentation.
- A methods-and-assumptions summary is available for every solved project, suitable for inclusion in a deliverable.
- Defaults are visible and labeled as defaults.

### 4.3 Links last

- A link shared today opens in ten years.
- Each project records the calculation-method version that produced its results. If a later version would give different results, the user is told what changed and why.
- Breaking changes to the data model always come with a migration. Old schema versions are never dropped.

### 4.4 Free and frictionless

- No installation, payment or account is ever required for core analysis.
- This is a personal project with no funding plan. Keep hosting costs near zero; prefer architectures that need no paid infrastructure.

### 4.5 Privacy by default

- No analytics, tracking or cookies by default. Usage is understood only from aggregate server request counts.
- Project contents are never stored or logged by the server.
- Diagnostics (e.g., bug reports) are opt-in and show the user exactly what is sent.

### 4.6 Results first, physics flagged

- Always solve and show results; never block a solve over a design-practice concern.
- **Flagged by default:** conditions that make a result physically invalid or unreliable — cavitation (NPSHa < NPSHr), flow reversal through a pump, operation outside a correlation's validated range, non-convergence.
- **Opt-in only:** design-practice checks (velocity limits, BEP proximity, code compliance).

### 4.7 Mobile and desktop are equal

Every feature is designed for both from the start. Neither is an afterthought.

### 4.8 Professional responsibility stays with the engineer

OpenSolve Pipe is an engineering aid. Its results support, but do not replace, the judgment of a qualified engineer, and they come with no warranty. Full traceability (§4.2) is how the tool earns trust, not a claim of certification.

## 5. Feature gates

A feature enters scope only if it passes **all three**:

| Gate | Question |
|------|----------|
| **Serves working engineers** | Does it help the primary user do real design work? |
| **Verifiable** | Can it ship with reference tests against a cited source? If it can't be verified, it doesn't ship. |
| **Free and zero-install** | Does core analysis remain free, install-free and account-free? |

**Also weigh, but not a gate:** ongoing maintenance cost. This is a personal project; between two features of equal value, prefer the one that needs less upkeep.

## 6. How work ships

- **Small, correct increments.** Ship narrow slices early; each one is complete, tested and verified within its scope. Never ship something broad but unverified.
- A slice is done when its reference tests pass, its sources are cited, and its traceability output exists.

## 7. How the project is run

### 7.1 Openness

- **License:** AGPL. Anyone may use, study and modify the code; anyone who runs a modified version as a hosted service must publish their changes.
- **Contributions:** issues, bug reports and data requests are welcome. Code contributions are accepted by invitation, to keep one consistent vision.

### 7.2 AI-assisted development

- AI agents may do much of the implementation.
- The project owner is accountable for every merge decision.
- Hydraulic correctness is established by the reference test suite, never by trusting generated code or generated explanations. AI-written solver code meets exactly the same verification bar as any other code.

## 8. Using this document

- **For a design decision:** name the values in tension, apply §3's order, and record the choice and its reasoning (in the PR, or as a decision in `CLAUDE.md` if it's architectural).
- **For a feature request:** check §5's gates first, then weigh maintenance cost.
- **Precedence:** this document → rebuild decisions in `CLAUDE.md` → PRD → SDD → TSD. When a spec conflicts with this document, change the spec.
