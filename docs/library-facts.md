# Verified library facts

Facts about `fluids`, CoolProp, EPANET (via WNTR) and Chart.js that were not obvious and cost time to find. Read this before writing code against any of them, and re-verify a fact against the installed package's docstrings or source before relying on it. Add a fact here when you find one the hard way; give the package version it was checked at.

**fluids 1.3.1**
- `friction_factor()` switches hard to 64/Re at Re 2040. The solver uses its own regimes (`services/solver/friction.py`) and never calls it.
- The Crane tee and wye functions:
  - cover only a combined flow through a run port;
  - give K on the combined-flow velocity in the run diameter;
  - do no input validation;
  - are piecewise in the flow ratio q (steps at q = 0.4, 0.5 and 0.6) and discontinuous in angle (at 60° and 75°).
- No other tee correlation exists in `fluids`. Darby 3-K has single-path tee entries only.
- `material_roughness()` fuzzy-matches free text: "PVC" returns 0.0008 m. Never use it.
- `nearest_pipe(Di=…)` returns the next size up, not the nearest.

**CoolProp 8.0.0**
- `INCOMP::MEG` and `INCOMP::MPG` take a mass fraction from 0 to 0.6 and define no saturation pressure.
- Above the saturation temperature, water silently returns vapor properties. `services/fluids.py` handles this.

**EPANET 2.2 (WNTR 1.5.0)**
- g = 32.2 ft/s², which gives a 0.08% head-loss bias.
- The water viscosity VISCOS is 1.02193344e-6 m²/s.
- The minor-loss constant is rounded to 0.02517.
- Results come back as float32.
- WNTR takes D-W roughness in metres.
- Use GPM INP units and `accuracy=1e-5` with `headerror`/`flowchange`. `ACCURACY` below 1e-5 is silently clamped.
- Multi-point pump curves are piecewise linear, so use collinear points to match PCHIP.
- PRV and PSV settings are heads without velocity head; our setpoints are static pressures. `generate_epanet_cases.py` converts between them by iterating.

**Chart.js 4.5.1**
- Datasets are drawn from the last to the first in their sorted order (`order`, then index; `_drawDatasets`), so the first dataset is drawn on top; the legend lists them in that sorted order (`_getSortedDatasetMetas`). The Pumps together chart gives other cases' rings `order: -1` to draw them on top, and its image legend sorts them back to the end (slice 4d, `pump-chart-config.ts`).
- A dataset's default `clip` lets its points reach past an axis edge by the larger of the radius and hover radius of its first and last points plus their border, or by half the line's border width if that is larger (`getMaxOverflow`, for a line dataset), only where that scale's `min` or `max` is unset (`scaleClip` in `dist/chart.js`). Where the configuration sets the bound, the allowance is 0, so a marker centred on that edge is drawn on the plot's side only. The Pumps together chart sets y max, and at times x min and x max, while other cases' curves are drawn, so it gives its members' points, the Group point and the rings their own `clip`, max(pointRadius, pointHoverRadius) + borderWidth, which equals the default where no bound is set (D24 slice L3, `markerClip` in `pump-chart-config.ts`; proposal `pump-lineups.md` §15 item 110; its test reads the internal `getDatasetMeta(i)._clip`).
- With `parsing: false` a line dataset is taken as sorted by x, without a check (`parse` sets `_sorted`). Where the configuration sets x min or max, only the index range a binary search finds is drawn (`_getStartAndCountOfVisiblePoints`), so data in falling x loses its points. A later update with the same axes also marks the points outside that range `skip` and leaves their positions as they were. The Pumps together chart sets `parsing: false`, and other cases' group curves run in rise order, so their flow falls: each such dataset carries its own `parsing` (`{ xAxisKey: 'x', yAxisKey: 'y' }`), so Chart.js finds them unsorted and draws every point (D24 slice L3; proposal `pump-lineups.md` §15 item 118).
