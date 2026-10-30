# D9. Component models (M3; resolves TSD §12)

Decision D9 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D9`.

---

- **Tees and wyes:** Crane TP-410 correlations in `fluids.fittings` (`K_branch/run_diverging/converging_Crane`) on the combined-flow velocity. They cover only a combined flow through a run port: a tee with the combined flow through its branch uses Darby 3-K "Tee, through-branch (as elbow)" per path and is flagged; a wye in that pattern has no cited correlation and is reported as not converged. The wye's lateral leans toward `outlet_1`. `lossModel: 'ideal'` gives EPANET-style junctions. *(GOALS §4.1: no uncited K.)*
- **Fluids:** CoolProp 8.0.0 (pinned): `Water` (IAPWS-95), `INCOMP::MEG`/`INCOMP::MPG` (Melinder 2010) within CoolProp's queried ranges. Glycols have no vapor pressure in CoolProp, so NPSH needs a user value (flagged otherwise).
- **Pump curves:** monotone piecewise cubic (`scipy.interpolate.PchipInterpolator`), straight end-slope extrapolation (flagged), affinity laws for speed. No viscosity correction (Later); the trace states it.
- **Valves:** default K from the Crane function for the valve type at the inlet pipe's diameter; Cv/Kv via `fluids` (ISA-75.01.01). No position-dependent K and no control-valve Cv curve in v1 (no cited characteristic); control valves default to ideal (zero loss when wide open). PRV/PSV setpoints are static pressures at the valve port.
- **Status logic:** EPANET 2.2 rules translated to EGL, at most 30 outer iterations that change statuses or branch K (iterations that only hold or release a zero-flow tee leg are bounded separately), oscillation → `converged: false` naming the components. Deliberate departures from EPANET: an FCV closes on reverse flow and opens when the head across it is below its fully open loss; closed elements around a closed-off section are re-tested (difference constraints) so a pump and check valve that close together can reopen.
