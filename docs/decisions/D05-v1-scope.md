# D5. v1 scope: core analysis MVP

Decision D5 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D5`.

---

**In v1:**
- Branching and looped networks
- Reservoir, ideal reference node, assigned-flow node (fixed demand or supply), tee, wye, plug/cap
- Pipes with fittings
- Fixed-speed pumps (on/off), and speed-controlled pumps holding a flow setpoint (D11, slice 1)
- Isolation valves (gate, ball, butterfly, globe) and check valves
- PRV, PSV and FCV
- Equipment (heat exchangers, coils, strainers, filters) rated by a pressure drop at a flow, or by a Cv or Kv (D18)
- Square-edged concentric orifice plates (ISO 5167-2): restriction orifices and orifice flow meters (D20)
- Conventional spring-loaded pressure relief valves in liquid service: a set pressure difference and an API 526 letter, an API 520 effective area or a certified capacity (D23)
- Water, ethylene/propylene glycol and user-defined fluids
- NPSH available and margin
- Panel navigator, results tables and the pump/system curve chart
- Scenario manager (D15)
- Goal seek (D16)
- Export: results workbook, CSV files and pump chart images, made in the browser (D17)
- Opt-in design checks: NPSH margin, the pump's operating region with its manufacturer data, pipe velocity (D19)
- Pumps together: the station that holds a group of pumps, its duty, its group curve and its group system curve (D21)
- Project library: pipe specs and K, Cv or Kv entries, each with its source, defined once and referred to by id from pipe segments, valves and inline fittings (D22)
- URL sharing

**Deferred:** speed-controlled pumps holding a discharge pressure (slice 2) or a differential pressure (slice 3), suction-pressure control, remote control nodes, mass-flow setpoints, overspeed, sleep at low demand, lead/lag stations and reduced-speed efficiency corrections (D11); HI viscosity correction; three-way valves; the differential-pressure mode for control valves; non-ideal reference nodes; cross and elbow-branch fittings; tanks with levels; sprinklers and user-defined elements; other orifice plates (eccentric, quadrant-edge, conical, thick, multi-hole and multi-stage), nozzles and venturis, a low-Reynolds-number C correlation, choked flow and an incipient-cavitation check, gases through a plate, ISO's uncertainty of C, a reverse-flow (bevelled plate) model and a Cv or Kv on the orifice (D20); balanced-bellows and pilot relief valves (set on the inlet's gauge pressure), pop action, blowdown and chatter, a manufacturer's lift or pressure–flow curve, API 520's Kv, Kw and Kc, non-certified valves, a nameplate rated capacity, a one-shot required area, gas, steam and two-phase relief, a free-draining discharge, a one-port valve to atmosphere, a failed-open status and relief design checks (D23); equipment rated by a K on a stated diameter, a head, a mass flow or a pressure-drop curve, its viscosity correction, and a reverse or clean/dirty rating (D18); project library entries as scenario targets and goal-seek variables, a source on inline user values, equipment ratings from the library, sharing a library between projects, and cited pipe sizes and materials beyond `fluids`' tables (D22); fuels in the fluid library; the auto-generated schematic; SVG and schematic image export; table entry and CSV pump-curve import; design checks beyond D19's three (code compliance, user-defined check libraries); a pump group in the export, one-pump-off cases drawn together, stored groups, impeller trims and the ISO 9906 tolerance (D21); cost estimation.
