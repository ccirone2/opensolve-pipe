/**
 * The bound r_max of decision 17 (c) as the API computes it, for tests of the web's transcription
 * (utils/orifice-bound.ts) and of goal seek's default boxes: each number was printed by
 * `opensolve_pipe.services.solver.orifice.ratio_range(D, β·D, taps, re_lo(β, D, 'd_and_d_2'))[1]`
 * (`uv run python`, repr), the bound `refusal` tests an entered C against (C · r_max ≤ 1). Every
 * plate listed is one the API builds on ISO 5167-2's C (`refusal(D, d, None, taps, g)` is None).
 * Not used by the app.
 */

/** [taps, D (m), β, the API's r_max]. */
export const API_R_MAX: readonly (readonly ['corner' | 'flange', number, number, number])[] = [
	['corner', 0.0525, 0.1, 1.0],
	['corner', 0.0525, 0.3, 1.0],
	['corner', 0.0525, 0.5, 1.0],
	['corner', 0.0525, 0.7, 1.012141636448446],
	['corner', 0.0525, 0.75, 1.021894367245884],
	['corner', 0.0525, 0.8, 1.0391397068402253],
	['corner', 0.0525, 0.9, 1.156897004335893],
	['corner', 0.0525, 0.95, 1.4802815855038833],
	['corner', 0.10226, 0.1, 1.0],
	['corner', 0.10226, 0.5, 1.0],
	['corner', 0.10226, 0.7, 1.0121498441446926],
	['corner', 0.10226, 0.75, 1.021894367245884],
	['corner', 0.10226, 0.8, 1.0391123366521375],
	['corner', 0.10226, 0.9, 1.1565350133432368],
	['corner', 0.10226, 0.95, 1.4786555405857844],
	['corner', 0.3, 0.7, 1.0121498441446926],
	['corner', 0.3, 0.9, 1.1565350133432373],
	['corner', 1.0, 0.75, 1.021894367245884],
	['corner', 1.0, 0.95, 1.4786555405857844],
	['flange', 0.0525, 0.1, 1.0000096777819965],
	['flange', 0.0525, 0.3, 1.000085759952412],
	['flange', 0.0525, 0.5, 1.000448989779515],
	['flange', 0.0525, 0.7, 1.0018332423865999],
	['flange', 0.0525, 0.75, 1.0026231901782454],
	['flange', 0.0525, 0.8, 1.0038475261897695],
	['flange', 0.0525, 0.9, 1.0097690927727079],
	['flange', 0.0525, 0.95, 1.0181107012034636],
	['flange', 0.10226, 0.1, 1.0],
	['flange', 0.10226, 0.5, 1.0],
	['flange', 0.10226, 0.7, 1.005851115590747],
	['flange', 0.10226, 0.75, 1.0100655762954256],
	['flange', 0.10226, 0.8, 1.0174386415739762],
	['flange', 0.10226, 0.9, 1.0653043263008106],
	['flange', 0.10226, 0.95, 1.1759055534653904],
	['flange', 0.3, 0.5, 1.0],
	['flange', 0.3, 0.7, 1.011735392450666],
	['flange', 0.3, 0.75, 1.0202261776279147],
	['flange', 0.3, 0.8, 1.0350967152574602],
	['flange', 0.3, 0.9, 1.1342665688305749],
	['flange', 0.3, 0.95, 1.3913105491484141],
	['flange', 1.0, 0.7, 1.012881596851915],
	['flange', 1.0, 0.75, 1.0226114122942018],
	['flange', 1.0, 0.8, 1.039724843216178],
	['flange', 1.0, 0.9, 1.1555445392949895],
	['flange', 1.0, 0.95, 1.469586364927523]
];
