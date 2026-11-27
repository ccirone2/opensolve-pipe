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

- **Tier it first** (§4): the tier sets how much of what follows a change needs. A tier-1 change is made and checked inline; a tier-2 change is built test-first, then tried by one skeptic; the rest of this section is tier 3's.
- **Split implementation from reference-writing.** One agent implements; an independent agent writes the reference cases from first principles, from the cited sources and its own transcription of the law, **without reading `services/`**. Integrate; on any mismatch find the root cause, never the tolerance.
- **Then adversarial review** (physics, the reference suite's independence, the web, the wording), each finding reproduced before it is fixed, and each fix with a test that fails before it.
- Make the smallest change that serves the slice. Nothing under `services/solver/` changes for a feature that only reads results (scenarios, goal seek, export, design checks, pump groups all proved this with a bit-identical corpus comparison).
- Generated files are never edited by hand (`CLAUDE.md`, Rules).

## 4. Prove it

The proof scales with what a change can break, never with its size. The owner (2026-11-27): "we need to speed up the pace of development without cost in quality. … the quality gates need to be conditionalized for improved efficiency. simple changes should implement quickly." and "scale with complexity of the change. not just size". A one-character change to a loss coefficient is tier 3; a page of new wording is tier 1.

Take the tier of the riskiest thing the change touches; when unsure, the higher one; move up as soon as the work shows more (a fix that turns out to touch shared state is tier 2). CI runs every suite a change can affect on every push and pull request, whatever its tier (§4.2), and a pull request merges only once every job that ran passed. GitHub does not enforce that: `main`'s ruleset requires a pull request but no status check, so it rests on whoever merges, Claude included, reading the checks first. So a tier decides what runs before the push and how much review a change gets. It never decides what is skipped before the merge.

| Tier | What puts a change here | Before the push | Review |
|---|---|---|---|
| **1. Local** | One place and few states, with nothing a user's numbers or data depend on: wording, a style or a layout inside one component, docs, comments, a test added or a test's wording or structure, a fix whose root cause is in one function | The test files of the modules changed, and for a layout the e2e file that measures it (`build-density.e2e.ts`, `pumps-layout.e2e.ts`); the type check and lint of the files changed (`pnpm check`, ESLint and Prettier; ruff and mypy); `tests/unit/test_docs.py` for docs | Re-read the diff; no agents |
| **2. Behaviour** | A behaviour with several states or paths, in the web app's view state or in tooling, where no solved value, cited number or user's data can change: what a user can do and when (an action made available or not), state shared by several views, async, cancel and focus paths, accessibility semantics, the export's layout and wording, an API route outside the solve (about, source), scripts, CI that only adds a check | Test-first, each new test failing before the change. The touched app's whole unit suite and its checks (Vitest with `pnpm check` and `pnpm lint`; or pytest with ruff and mypy); the e2e files that cover the behaviour, on both projects | One skeptic, an agent that did not build it, tries to break it in tests and in the browser; its findings fixed test-first |
| **3. Proof** | Anything that can change a solved value or a cited number: the solver, a loss law, a component model, fluid properties, `data/`, reference cases, `METHOD_VERSION`, and any code the solve, its response or its errors run through, a result added included. A changed expected value or tolerance in any test, and anything in `tests/reference`, `tests/differential` or `tests/fixtures`. Anything that changes the project the user keeps or shares (editing, undo, copying, the model and its schema, the link encoding, D3), or a number or unit the user sees or exports. The trust boundary: privacy and errors (D10), CORS, limits, and the deployment: `deploy-api.yml` and what CI runs on `main` and when (its triggers, job conditions, `changes`, `e2e-result`), the deploy's only test gate (D25) | Every gate (§4.1) and the proofs of its table that fit the change. A result added runs the corpus comparison with `--ignore-empty` for its field. A change to CI or the deploy has the pull request's own full CI run (a change to `ci.yml` always runs every job) | §3's split of implementation from reference-writing where there is a law or a number to check, then the adversarial review |

- **Agents.** Tier 1 is done inline. Tier 2 is built inline or by one agent, then tried by one skeptic. Workflows of many agents (design panels, finder and verifier fleets) are for tier 3, and for a design question with several credible answers.
- **Playwright here.** The whole suite takes about 40 minutes in one worker on a 4-CPU container. Tiers 1 and 2 run only the files that cover the change, in one worker, since the API solves one request per client at a time (`playwright.config.ts`); CI runs the whole suite in shards.
- **The record.** The history line (§5, item 5) names the tier and the gates run before the push. `scripts/record_history.py` refreshes [`verified-state.md`](verified-state.md) for a tier-3 change, which runs every gate anyway; otherwise the file is left as it is, and its date says which state it measured.

### 4.1 Every gate

`cd apps/api && uv run python scripts/record_history.py` runs them all, prints each summary and rewrites [`verified-state.md`](verified-state.md) (`--skip e2e` for a quick pass, `--dry-run` to write nothing, `--only pytest` for one gate; a failed gate leaves the file unchanged). By hand:

```bash
cd apps/api && uv sync && uv run pytest -n auto && uv run ruff check . && uv run ruff format --check . && uv run mypy src
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

### 4.2 CI

`.github/workflows/ci.yml` runs on every push and pull request:
- the API job (pytest, ruff, mypy; its pytest includes the docs checks);
- the Web job (`pnpm check`, `pnpm lint`, Vitest);
- the history-line check, on a pull request;
- the end-to-end suite on desktop and mobile, each in six shards with its own API and app.

The end-to-end suite was CI's critical path: 21–33 min in one job per project on CI's last eight green runs before the shards (2026-11-27), where the API job took 5–9 min and the Web job 4–7. Every test still runs, in exactly one shard. Playwright splits shards by test count, not time, and the heavy tests come last: in three shards the last took 15.1 and 17.0 min against 2.4–3.5 for the first (desktop and mobile, the run on `f1929c1`), hence six.

- **When the suite is skipped.** Its `changes` job skips it only when every changed file is one no browser test or build reads (they read `apps/` alone): `docs/`, `CLAUDE.md`, `README.md`, `.claude/`, `.github/pull_request_template.md` and `.github/workflows/deploy-api.yml`. Anything new under `.github/`, such as a local action `ci.yml` could use, runs it.
  - Renames count under both paths.
  - A pull request is judged against `main` whatever its base, so a stacked pull request retargeted to `main` (an `edited` event, which starts no run) was already judged by all it brings.
  - A push to `main` runs every job, so every head of `main`, and so every commit the deploy may take (D25), has a full run.
  - The job fails closed: if it cannot tell, it fails, and *End-to-end (desktop + mobile)* with it.
- **The API and Web jobs always run.** The apps share fixtures, so each reads the other's files. The docs checks are in the API job.

## 5. Record it

In the same change set as the code:

1. The decision file, `docs/decisions/Dnn-<slug>.md` from [`decisions/TEMPLATE.md`](decisions/TEMPLATE.md), and its two index rows (`decisions/README.md`, `CLAUDE.md`). Numbers are assigned by merge order to `main`: on a branch take the next free number, and renumber at merge if another decision got there first (slugged file names make that one `git mv`).
2. The specs: PRD §2.3 and §3 (scope and requirements), SDD §4 (a model subsection) and §5 where a contract changes, TSD §4–§5 (data and solver), §10.4 (the proof counts) and §12 (the "Decided" item). Add subsections at the end of a section; never renumber, since code cites `TSD §4.10`.
3. `METHOD_VERSION` and `METHOD_CHANGELOG` (`services/solver/version.py`) if any solved value can change, with a line saying what is unchanged and how that was proven.
4. The proposal's status line and as-built section.
5. [`history.md`](history.md): a line for the change naming its PR (`owner/repo#N`) or, written before the PR is opened, its branch in backticks, with its decision, method version and tier (§4), committed in the PR before it merges (the merge hash does not exist yet and is not needed: the PR links to it; CI's "History line" check fails a PR that adds no line naming it), with [`verified-state.md`](verified-state.md) refreshed by `scripts/record_history.py` for a tier-3 change, and the proof record below it (reference-suite deviations, corpus counts) updated by hand; [`roadmap.md`](roadmap.md) trimmed.
6. [`library-facts.md`](library-facts.md) if a library surprised you.

## 6. Commits, branches and agents

- One change set per commit, its tier's gates green (§4), a conventional-commit message that states what was verified. Develop on the branch the session assigns, push only to it, never force-push, open a PR only when asked. Web-only changes on `web/<topic>` (`CLAUDE.md`, Rules).
- With 4 CPUs a workflow runs about two agents at a time. Give parallel agents disjoint directories and tell them not to run `ruff format` or Prettier outside their own paths. If a workflow is stopped, check the tree before resuming: a stopped agent may have left edits half done. Two agents running the Playwright suite at once each need their own worktree (both build into `apps/web/build`) and their own ports: `E2E_API_PORT=8020 E2E_WEB_PORT=4193 pnpm test:e2e` (`tests/servers.ts`); outside CI Playwright reuses whatever server already holds a port.
- **Parallel sessions.** In a cloud session, `.claude/hooks/session-start.sh` installs the dependencies when a lockfile changed and prints the coordination report (`.claude/hooks/coordination.sh`): the branch against `main`, the other `claude/*` and `web/*` branches, the next decision number and `METHOD_VERSION` here and on `main`, and a number both this branch and `main` added since they parted. Take numbers from it and from the other branches' open PRs; renumber at merge as §5 says. The report runs at startup, resume, `/clear` and compaction, never in between, so `.claude/hooks/pre-push.sh` runs it again before every `git push` (1–2 s) and blocks the push on a collision (renumber first; `OPENSOLVE_PUSH_ANYWAY=1 git push …` pushes work in progress anyway, and the user is told). `tests/unit/test_docs.py` (index rows, cited versions, numbered headings, TSD §12 items) and `test_methods.py` (the changelog's order) fail on a collision that reaches the merged tree.
- **Generated files are regenerated, never merged.** `.gitattributes` gives the outputs of `pnpm gen:types`, the two data files and `docs/verified-state.md` the `generated` merge driver, which the session-start hook configures: a merge (or a rebase) keeps this branch's copy, and the next coordination report names the file. Regenerate it on the merged tree and commit: `pnpm gen:types`, the data script, or `scripts/record_history.py`. CI's generated-types check fails on stale API types; nothing else stops the push. Where the driver is not configured, git merges these files as text; resolve a conflict in one by regenerating it. `tests/unit/test_generated_files.py` fails when one of these is missing from `.gitattributes`. Other generated files (the reference case JSONs, the export's expected workbook) merge as text: a conflict there is safer than a silently kept side.
- Where the Playwright browsers are preinstalled (`PLAYWRIGHT_BROWSERS_PATH` is set), never run `playwright install`.

## 7. Report

End every session with: the gate results with counts; reference-suite changes and their worst deviations; anything left out or limited, and why; decisions recorded and spec changes made; known issues. Report failures plainly, with their output. Never describe as working anything you have not run.
