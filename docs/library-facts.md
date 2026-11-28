# Verified library facts

Facts about `fluids`, CoolProp, EPANET (via WNTR), numpy's OpenBLAS, Chart.js and Chromium that were not obvious and cost time to find. Read this before writing code against any of them, and re-verify a fact against the installed package's docstrings or source before relying on it. Add a fact here when you find one the hard way; give the package version it was checked at.

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
- At a fluid near the schema's bounds `C_Reader_Harris_Gallagher` gives no C and no clean error: `(D 0.1, Do 0.05, m 1, ρ 5e-324, μ 1e-3, 'D')` raises `ValueError: math domain error`, and with ρ 1000, μ 1e-300 it returns `inf`. `Clamond(inf, 1e-4)` returns `nan`. The builder refuses such plates first (D20 rule (e)) and the GGA names a law that raises (D7); checked 2026-11-03.

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

**numpy 2.5.4 and scipy 1.18.1 (scipy-openblas 0.3.34)**
- OpenBLAS picks its kernels for the CPU at run time: AVX-512 ones (SkylakeX) on this container's CPU, AVX2 ones (Haswell) on some GitHub runners. The two round differently, so a solve's last bits differ by runner. That is harmless where Newton converges to round-off, but it changes the path where a status rule has no tolerance. Two of round two's tests passed here and failed on some runners (`docs/proposals/open-defects-2.md`; CI runs 45907886175 and 45939994232):
  - a system-curve point exactly at an FCV's setpoint: the kernels chose different solves, and their answers differed by convergence-level noise, 7.7·10⁻⁸ m in `openHead` at the default tolerance;
  - a singular step reached only after round-off moved a zero flow.
- `OPENBLAS_CORETYPE=Haswell` reproduces such a runner here exactly. `NPY_DISABLE_CPU_FEATURES` (numpy's own SIMD paths) changed neither case.
- A test that reads a value at an exact switch, or a lost weight after round-off, should be solved to a tolerance where both kernels agree (`tests/fixtures/condenser_charts.py`'s single24, at 1e-12), or built so the outcome does not hang on the last bits (`test_singular_step.py`'s floating section).

**Chart.js 4.5.1**
- Datasets are drawn from the last to the first in their sorted order (`order`, then index; `_drawDatasets`), so the first dataset is drawn on top; the legend lists them in that sorted order (`_getSortedDatasetMetas`). The Pumps together chart gives other cases' rings `order: -1` to draw them on top, and its image legend sorts them back to the end (slice 4d, `pump-chart-config.ts`).
- A dataset's default `clip` lets its points reach past an axis edge by the larger of the radius and hover radius of its first and last points plus their border, or by half the line's border width if that is larger (`getMaxOverflow`, for a line dataset), only where that scale's `min` or `max` is unset (`scaleClip` in `dist/chart.js`). Where the configuration sets the bound, the allowance is 0, so a marker centred on that edge is drawn on the plot's side only. The Pumps together chart sets y max, and at times x max, while other cases' curves are drawn (x min too until `open-defects-2.md` X, which floors the axis without setting it; below), so it gives its members' points, the Group point and the rings their own `clip`, max(pointRadius, pointHoverRadius) + borderWidth, which equals the default where no bound is set (D24 slice L3, `markerClip` in `pump-chart-config.ts`; proposal `pump-lineups.md` §15 item 110; its test reads the internal `getDatasetMeta(i)._clip`).
- With `parsing: false` a line dataset is taken as sorted by x, without a check (`parse` sets `_sorted`). Where the configuration sets x min or max, only the index range a binary search finds is drawn (`_getStartAndCountOfVisiblePoints`), so data in falling x loses its points. A later update with the same axes also marks the points outside that range `skip` and leaves their positions as they were. The Pumps together chart sets `parsing: false`, and other cases' group curves run in rise order, so their flow falls: each such dataset carries its own `parsing` (`{ xAxisKey: 'x', yAxisKey: 'y' }`), so Chart.js finds them unsorted and draws every point (D24 slice L3; proposal `pump-lineups.md` §15 item 118).
- With `labels.usePointStyle`, the legend's default `generateLabels` takes each entry's style from `getStyle(0)`, the first point's options, which have no `borderDash`. The entry's `lineDash` is then undefined, `drawLegendBox` calls `setLineDash([])`, and a dashed line's `'line'` swatch is drawn solid. The Pumps together image legend sets each line entry's `lineDash` from its dataset's `borderDash` in its own `generateLabels` (slice 5c, review DOTS-LABELS-B3, `pump-chart-config.ts`; its test in `pump-group-others.test.ts` draws the legend with Chart.js itself). The single pump chart's legend does the same since leftover L16 (`pumps-nits.md` §11.5, 2026-11-18): each line's swatch takes its dataset's dash, on the page and in the image.
- Under `usePointStyle`, a `'line'` swatch is 2 × `boxHeight` × √2/2 long, 16.97 px at `boxHeight: 12`. `labels.pointStyleWidth` lengthens it, but it also widens every other point style to that width (`drawPointLegend`): a circle becomes `ctx.ellipse(x, y, w / 2, radius, …)` and a `rectRot` a wider rhombus. The Pumps together image keeps the 16.97 px swatches for this reason, and its six slot patterns differ by 3 px or more within them (slice 5c, review DOTS-LABELS-B5; proposal `pumps-nits.md` §8.10 and §8.14).
- A linear scale's default `bounds: 'ticks'` starts the axis at the nice tick at or below the least datum (`niceMin = Math.floor(rmin / spacing) * spacing` in `generateTicks$1`), so one datum at round-off below zero starts it a whole step below. A group curve's point at the shutoff rise is a sum of member flows near zero: at −6.08·10⁻¹⁵ m³/s (−6.08·10⁻¹² L/s) in a project like the owner's photo, it started the flow axis at −5,000 L/s. Setting `min: 0` cures that but also takes the clip allowance at that edge to 0 (above). A scale's `afterDataLimits` hook runs after `determineDataLimits` and before the grace and the ticks (`Scale.update`), and `getUserBounds` reads only the options (`_userMin`). So raising `scale.min` to 0 there floors the axis while `min` stays unset: Chart.js keeps its clip allowance, and a dataset drawn with `parsing: false` is not cut to a binary-searched range (`_getStartAndCountOfVisiblePoints`). Both charts' flow axes do this (`flowAxisFloor` in `pump-chart-config.ts`; proposal `open-defects-2.md` X; its tests read the rendered `scales.x.min`).

**Chromium (Chrome for Testing 153.0.8010.12, Playwright's `chromium-1243`)**
- Scroll anchoring is not applied to a layout a script forces in the middle of a task. Where a Svelte flush changes the DOM above a focused control in a scroller, `getBoundingClientRect` read inside that flush sees the moved layout with the scroller's `scrollTop` not yet adjusted. On the lineups example, with the pump chart's section above shrinking as it asked for its system curve again (1,246 → 1,158 px), "Stop Pump P4 later" read 291 px from the pane's top at 1280×800, where every frame until the withdrawal drew it at 359 (68 px off); at 390×844, 232 against 336 (104 px). Measured with the button's offset read after every frame from the press to the withdrawal (proposal `open-defects-2.md` F3, §9 item 8).
- An anchoring adjustment fires a `scroll` event at the scroller, after that frame's layout: the solving line's growth above the button scrolled the pane from 6,384 to 6,456 px, the button kept at 359 px. So where a control stood on screen is recorded at its focus and at each `scroll` event of its pane, never read in the flush that moves things around it (`SeenOffset` in `components/results/card-sections.svelte.ts`).
