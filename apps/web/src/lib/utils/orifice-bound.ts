/**
 * The bound r_max of decision 17 (c) (proposal orifice-plate.md §1.2): an entered discharge
 * coefficient C_e at corner or flange taps is moved to D and D/2 tappings by ISO 5167-2's ratio
 * r = C_ISO(D and D/2)/C_ISO(taps) (decision 13), and the API refuses a plate whose C_e · r_max
 * exceeds 1 (ORIFICE_OUT_OF_RANGE; at a goal seek's bound, a bounds 400). r_max is a closed form
 * of the plate's geometry alone (D, d and the taps), the same for every fluid and flow:
 *
 *   r_max = 1 + max(ΔC(Re_lo), ΔC(∞), 0)/C_taps,min,   ΔC = C_ISO(D and D/2) − C_ISO(taps),
 *
 * over Re ∈ [Re_lo, ∞), Re_lo = max(5000, 16000 β²) (ISO's lowest Re at D and D/2 tappings, made
 * continuous, decision 7), with C_taps,min eq. (4)'s smallest bound at the taps there.
 *
 * Goal seek's default boxes use it so that they stay inside decision 17 (c) (§6 W6), before any
 * solve and whatever the last solve's state: a pre-fill only, never a check. The API decides, and
 * this transcription of its bound (services/solver/orifice.py `rhg_terms_at`, `c_range`,
 * `tap_difference`, `ratio_range`, term by term in its order of operations, eq. (4) as fluids
 * 1.3.1's C_Reader_Harris_Gallagher computes it) is pinned to the API's values in
 * orifice-bound.test.ts. Every constant is eq. (4)'s, ISO's or fluids', but RATIO_BOUND_ANY, which
 * the API's own functions gave.
 */
import type { OrificeTaps } from '../api/types';

/** m: 1 in (fluids.constants.inch), eq. (4)'s flange tap length and small-pipe unit. */
const INCH = 0.0254;
/** ISO 5167-2's lowest Reynolds number, every tap set (fluids' docstring). */
const RE_LO_MIN = 5000;
/** Corner and D and D/2 tappings: Re_D ≥ 16000 β² (fluids' docstring), continuous (decision 7). */
const RE_LO_BETA = 16000;
/** m (2.8 in): eq. (4)'s small-pipe term applies below this D (fluids' code). */
const SMALL_PIPE = 0.07112;
/** 19000^0.8, as the API writes A = (19000 β/Re)^0.8. */
const A_SCALE = 2648.5177066967326;

/**
 * The largest r_max over every plate the API builds on ISO 5167-2's C at corner or flange taps,
 * 2.0445 (corner taps at D → 0 and β 0.97060, where eq. (4) at D and D/2 tappings reaches 1,
 * decision 17 (b)), rounded up: found by bisecting β to that limit with the API's own `refusal`
 * and `ratio_range`, D from 0.1 mm to 10 m, both tap sets. For a plate whose D is not known.
 */
export const RATIO_BOUND_ANY = 2.05;

/** eq. (4)'s L1 and L2' for a tap set (fluids' code): corner 0, 0; flange 1 in/D; D and D/2 1, 0.47. */
function tapLengths(taps: OrificeTaps, pipe: number): [number, number] {
	if (taps === 'corner') return [0, 0];
	if (taps === 'flange') return [INCH / pipe, INCH / pipe];
	return [1, 0.47];
}

interface Terms {
	/** C∞ + downstream + small-pipe: the terms that do not depend on Re. */
	rest: number;
	upstream: number;
	downstream: number;
}

/**
 * The terms of eq. (4) at Re (Infinity for its infinite-Re limit) that r_max needs, as the API's
 * `rhg_terms_at` computes them (its two slope terms, positive and only in eq. (4)'s largest
 * bound, are left out).
 */
function terms(pipe: number, bore: number, re: number, taps: OrificeTaps): Terms {
	const [l1, l2] = tapLengths(taps, pipe);
	const inv = 1 / re;
	const beta = bore / pipe;
	const beta2 = beta * beta;
	const beta4 = beta2 * beta2;
	const beta8 = beta4 * beta4;
	const a = A_SCALE * (beta * inv) ** 0.8;
	const m2 = (2 * l2) / (1 - beta);
	const e1 = Math.exp(-l1);
	const e2 = e1 * e1;
	const e3 = e1 * e2;
	const factor = 0.043 + e3 * e2 * e2 * (0.08 * e3 - 0.123);
	const ratio4 = beta4 / (1 - beta4);
	const upstream = factor * (1 - 0.11 * a) * ratio4;
	const downstream = -0.031 * (m2 - 0.8 * m2 ** 1.1) * beta ** 1.3;
	const cInf = 0.5961 + 0.0261 * beta2 - 0.216 * beta8;
	const small = pipe < SMALL_PIPE ? 0.011 * (0.75 - beta) * (2.8 - pipe / INCH) : 0;
	return { rest: cInf + downstream + small, upstream, downstream };
}

/**
 * r_max of decision 17 (c) for a bore `bore` in an inlet pipe of inner diameter `pipe` (m) with
 * corner or flange taps; null for β ≥ 1 (no plate), or where it is not a finite number.
 */
export function movedRatioBound(
	pipe: number,
	bore: number,
	taps: 'corner' | 'flange'
): number | null {
	if (!(pipe > 0 && bore > 0 && bore < pipe)) return null;
	const beta = bore / pipe;
	const reLo = Math.max(RE_LO_MIN, RE_LO_BETA * beta * beta);
	const low = terms(pipe, bore, reLo, taps);
	const top = terms(pipe, bore, Infinity, taps);
	const tapsMin = low.rest + Math.min(low.upstream, top.upstream);
	const difference = (re: number) => {
		const dd = terms(pipe, bore, re, 'd_and_d_2');
		const tp = terms(pipe, bore, re, taps);
		return dd.upstream - tp.upstream + (dd.downstream - tp.downstream);
	};
	const r = 1 + Math.max(difference(reLo), difference(Infinity), 0) / tapsMin;
	return Number.isFinite(r) && r >= 1 ? r : null;
}
