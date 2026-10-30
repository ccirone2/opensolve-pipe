# How work ships

The method that made v1 trustworthy, written down so each slice follows it. GOALS §6: small, correct increments; a slice is done when its reference tests pass, its sources are cited and its traceability output exists.

## 1. Gate it

- Pass the feature through GOALS §5's three gates (serves working engineers, verifiable against a cited source, free and zero-install), then weigh maintenance cost.
- Check [`roadmap.md`](roadmap.md): is it open, shelved or Later, and what does its proposal's "Later" section already say?
- Ask the owner only product questions: what to build, and behaviour a user would see. Solver questions about zero-flow labels, iteration paths or convergence-level differences are settled by D13, never escalated.

## 2. Design it: a proposal

Write `docs/proposals/<slug>.md` (see [`proposals/README.md`](proposals/README.md) for the shape the built ones share):

1. **Status line** first: proposed / decided (owner, date) / built (date, decision, where the as-built notes are) / shelved.
2. **Scope and decisions:** the owner's request quoted; what is already decided and not re-opened (the binding decisions); what is the designers' own and reversible under D14.
3. **Model and API**, **physics and solver**, **traceability**, **scenarios, goal seek, Compare and export**, **web**, **verification plan**, **files to change**, **Later**, **questions for the owner** (with the answers once given), **review record**, **as built** (every departure from the text above, numbered).

Design workflows have worked well as several designers from different angles (physics; sources and verification; web), a synthesizer, two reviewers and a reviser. Each designer prototypes and measures; a claim that was not measured says so.

## 3. Build it

- **Split implementation from reference-writing.** One agent implements; an independent agent writes the reference cases from first principles, from the cited sources and its own transcription of the law, **without reading `services/`**. Integrate; on any mismatch find the root cause, never the tolerance.
- **Then adversarial review** (physics, the reference suite's independence, the web, the wording), each finding reproduced before it is fixed, and each fix with a test that fails before it.
- Make the smallest change that serves the slice. Nothing under `services/solver/` changes for a feature that only reads results (scenarios, goal seek, export, design checks, pump groups all proved this with a bit-identical corpus comparison).
- Generated files are never edited by hand (`CLAUDE.md`, Rules).

## 4. Prove it

Every gate, every time (`history.md` holds the latest counts to confirm):

```bash
cd apps/api && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run python scripts/generate_pipe_data.py --check && uv run python scripts/generate_relief_data.py --check
cd ../web && pnpm install && pnpm gen:types && git diff --exit-code -- src/lib/api
pnpm check && pnpm lint && pnpm test && pnpm test:e2e
```

Then the proofs that fit the change (TSD §10.4 has every command and the baseline counts):

| Change | Proof |
|---|---|
| Any solver or loss-law change | The reference suite (D6); the **corpus comparison**, before and after, every value identical or the difference named in `METHOD_CHANGELOG` with a version bump (D13) |
| Status logic, the outer loop | The **differential fuzz** against EPANET, three profiles (`default`, `flow_control`, `assigned_flow`): 0 critical seeds, no converged solve lost |
| A new element | At least one reference case per behaviour (closed-form and, where EPANET can model it, EPANET), a **corpus check** that swaps the element in for an existing one with an exact expected answer (`equipment_check`, `orifice_check`, `relief_check`, `library_check` are the pattern), and the other checks re-run (`scenario_check`, `goal_seek_check`, `design_checks_check`, `pump_group_check`, `missing_result_check`) |
| Scenarios, goal seek, export, design checks, pump groups | Their corpus checks, and the corpus comparison with `--ignore-empty` for the field the feature adds |
| Web | Vitest, component tests, Playwright on desktop (1280×800) and mobile (390×844), axe clean |

**EPANET as a reference.** EPANET's friction formula (Swamee–Jain) differs from exact Colebrook by up to 3.0 % in f, so EPANET cases run the solver with `frictionMethod = "swamee_jain"` and compare our EGL with EPANET's heads (it neglects velocity heads, D7). An orifice plate runs in EPANET as a GPV whose head-loss curve is the plate's own law (D20); a relief valve as a GPV tabulating its law at zero flow, full lift and 201 flows, in series with its inlet pipe as a CV pipe (D23). Known EPANET biases are in [`library-facts.md`](library-facts.md).

## 5. Record it

In the same change set as the code:

1. The decision file, `docs/decisions/Dnn-<slug>.md` from [`decisions/TEMPLATE.md`](decisions/TEMPLATE.md), and its two index rows (`decisions/README.md`, `CLAUDE.md`). Numbers are assigned by merge order to `main`: on a branch take the next free number, and renumber at merge if another decision got there first (slugged file names make that one `git mv`).
2. The specs: PRD §2.3 and §3 (scope and requirements), SDD §4 (a model subsection) and §5 where a contract changes, TSD §4–§5 (data and solver), §10.4 (the proof counts) and §12 (the "Decided" item). Add subsections at the end of a section; never renumber, since code cites `TSD §4.10`.
3. `METHOD_VERSION` and `METHOD_CHANGELOG` (`services/solver/version.py`) if any solved value can change, with a line saying what is unchanged and how that was proven.
4. The proposal's status line and as-built section.
5. [`history.md`](history.md): a line for the merge with its hash, PR, decision and method version, and the new gate counts; [`roadmap.md`](roadmap.md) trimmed.
6. [`library-facts.md`](library-facts.md) if a library surprised you.

## 6. Commits, branches and agents

- One change set per commit, every gate green, a conventional-commit message that states what was verified. Develop on the branch the session assigns, push only to it, never force-push, open a PR only when asked. Web-only changes on `web/<topic>` (`CLAUDE.md`, Rules).
- With 4 CPUs a workflow runs about two agents at a time. Give parallel agents disjoint directories and tell them not to run `ruff format` or Prettier outside their own paths. If a workflow is stopped, check the tree before resuming: a stopped agent may have left edits half done.
- Where the Playwright browsers are preinstalled (`PLAYWRIGHT_BROWSERS_PATH` is set), never run `playwright install`.

## 7. Report

End every session with: the gate results with counts; reference-suite changes and their worst deviations; anything left out or limited, and why; decisions recorded and spec changes made; known issues. Report failures plainly, with their output. Never describe as working anything you have not run.
