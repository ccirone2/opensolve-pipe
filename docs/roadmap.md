# Roadmap: open work

In priority order. Pass each item through GOALS §5's gates first; design it as [`workflow.md`](workflow.md) §2 says. **Apply D13 to every solver change:** never take a question about zero-flow labels, iteration paths or convergence-level differences to the owner. Ask the owner only about product choices: what to build, and behaviour a user would see.

What is built is in [`history.md`](history.md); the deferred list of the v1 scope is [D5](decisions/D05-v1-scope.md); the decided and open implementation questions are TSD §12.

## 1. Blocked on a source

**Tee and wye coverage** beyond the Crane patterns (D9): a tee with the combined flow through its branch uses Darby 3-K and is flagged; a wye in that pattern is not converged. Blocked on a source the owner supplies: Idelchik's AEC translation and Bassett et al. 2001 are not readable here; Gardel 1957, *Bulletin technique de la Suisse romande* 83, is on e-periodica behind a human-verification page, and may cover only the patterns already built.

## 2. Next feature: the owner's choice

Each ships as one verified slice with reference cases and traces. Candidates, in the PRD's order, each with its proposal's "Later" section:

- **HI viscosity correction** (D9): needs the source in hand.
- **Equipment** (`proposals/equipment-pressure-drop.md` §9): a K on a stated diameter, a head or mass-flow rating, a pressure-drop curve, a viscosity correction (needs geometry or a cited correlation per type), and an `equipment` fuzz profile once the element gains behaviour an open valve does not have.
- **Orifice plate** (`proposals/orifice-plate.md` §9): other plate types, nozzles and venturis, a low-Reynolds-number C (needs a cited correlation over the β range), choked flow and an incipient-cavitation design check, gases, a Cv or Kv on the orifice.
- **Relief valve** (`proposals/pressure-relief-valve.md` §9): balanced-bellows and pilot valves (level-dependent status rules); pop action and blowdown (whose second steady state D13 requires to be reported); a manufacturer's lift or pressure–flow curve; API 520's Kv, Kw and Kc and non-certified valves, each once read in API 520; relief design checks, each once its standard is read; gas, steam and two-phase relief; the check valve's cracking pressure compared on the static difference (a method change with its D13 corpus cost).
- **Pump groups** (PRD §3.2.2; `proposals/pump-groups.md` §8): the group in the export; one pump off as a case of each running pump; and an open owner's question from the relief merge's review: whether a station whose bypass carries the flow back from D to S at the duty should mirror its frame, as it does now.
- **Project library** (`proposals/project-library.md` §9; TSD §12 open items 6–10): entries as scenario targets and goal-seek variables (the owner's "next slice"); a `source` on inline user values; equipment ratings from the library; sharing a library between projects; growing the cited library (the owner's call under D8).
- **Goal seek** (PRD §3.9; `proposals/goal-seek.md` §10): saved setups, a start value, more goals, a coefficient select, more than one goal seek in the pool.
- **Speed-controlled pumps, slices 2 and 3** (D11): discharge-pressure and differential-pressure setpoints. See *Shelved*.

## 3. Shelved (D13)

Speed-controlled pumps slice 2 (discharge pressure) and C1 (an exact Newton step for an active PRV's velocity-head term). Their design and measurements are in `proposals/vfd-slice2-discharge-pressure.md`; the owner's answers there are provisional notes, not decisions. Revisit with a simpler design under D13 if the owner asks for slice 2 again. The PRV's slow lag is TSD §12 open item 5.

## 4. Web: Build density (proposal `proposals/build-density.md` §10, §12)

Every Build form is laid out from the field registry, with one label and unit table and budgets the e2e suite enforces. Open, each with what it needs:
- **Adding a component in fewer than 3 actions**: an "Add after ▾" select that adds a kind with no entry values at once (the dialog stays for the others); the e2e suite's 20 dialog flows move with it.
- **A segmented control** for 2–3-value choices (a phone's status in one tap).
- **The export's pump table** from the registry (its input columns are listed by hand), and `labels.fieldLabel` from `fieldLabelFor`.
- **A solved connection's pipe size and a curve's first point on a phone** are one scroll below the first screen.
- The sibling inconsistencies of the proposal's §3.4 (labels of K, "difference", "default"), each reviewed on its own since a label reaches scenario notes and the export.

## 5. Still to do by hand

Export's by-hand checks (TSD §10.3): the workbook in Excel for Android and the chart image on Android are recorded; the rest is still to do.

## 6. Later, by the specs

PRD §2.4 (cost estimation, pipe sizing optimization, a pump database, curve digitization, a public API, colour-coded results, code compliance libraries) and the deferred list of [D5](decisions/D05-v1-scope.md). TSD §12's open items 1–2 (schematic layout, version storage) wait on accounts and the schematic, both Later.
