/**
 * The bound r_max of decision 17 (c) the web transcribes from the API (utils/orifice-bound.ts),
 * pinned to the API's own values (testing/orifice-r-max.ts says how they were printed; the other
 * numbers here were printed the same way). The tolerance, 10⁻¹² relative, is far above the two
 * implementations' round-off (their pow and exp may differ in the last bits) and far below the
 * 1 % margin goal seek's defaults keep (§6 W6).
 */
import { describe, expect, it } from 'vitest';
import { API_R_MAX } from '../testing/orifice-r-max';
import { movedRatioBound, RATIO_BOUND_ANY } from './orifice-bound';

const relative = (a: number, b: number) => Math.abs(a - b) / Math.abs(b);

describe("decision 17 (c)'s r_max, transcribed from the API (orifice-bound.ts)", () => {
	it("equals the API's ratio_range on corner and flange plates, D 52.5 mm to 1 m, β 0.1 to 0.95", () => {
		for (const [taps, D, beta, api] of API_R_MAX) {
			const r = movedRatioBound(D, beta * D, taps);
			expect(r, `${taps} ${D} ${beta}`).not.toBeNull();
			expect(relative(r!, api), `${taps} ${D} ${beta}: ${r} against ${api}`).toBeLessThan(1e-12);
		}
	});

	it('gives the plates the reviews named: β 0.5865 on 102.3 mm, the held 52.5 mm flange plate', () => {
		// Before a solve, at the bore 60 mm of a goal seek's default C box (API: refusal at C 1).
		expect(relative(movedRatioBound(0.1023, 0.06, 'corner')!, 1.001867465564057)).toBeLessThan(
			1e-12
		);
		expect(relative(movedRatioBound(0.1023, 0.06, 'flange')!, 1.001339471960576)).toBeLessThan(
			1e-12
		);
		// A flange plate whose ISO C was held below Re_lo, where C_L ÷ C_M was 0.9795 (below 1).
		expect(
			relative(movedRatioBound(0.0525, 0.7 * 0.0525, 'flange')!, 1.0018332423865999)
		).toBeLessThan(1e-12);
	});

	it('has no value for a bore not smaller than the pipe', () => {
		expect(movedRatioBound(0.1, 0.1, 'corner')).toBeNull();
		expect(movedRatioBound(0.1, 0.12, 'flange')).toBeNull();
		expect(movedRatioBound(0, 0.05, 'corner')).toBeNull();
	});

	it('stays below RATIO_BOUND_ANY wherever ISO 5167-2 at D and D/2 tappings stays at most 1', () => {
		// The API's largest r_max over plates it builds on ISO's C (bisected to its refusal limit,
		// D 0.1 mm to 10 m): 2.044509377809689 at corner taps, D 0.1 mm, β 0.9706021928121271.
		expect(
			relative(movedRatioBound(1e-4, 0.9706021928121271 * 1e-4, 'corner')!, 2.044509377809689)
		).toBeLessThan(1e-12);
		expect(2.044509377809689).toBeLessThan(RATIO_BOUND_ANY);
		// No plate the API builds has β above that limit (it falls with D: 0.97025 from 71.12 mm).
		for (let k = 0; k <= 50; k++) {
			const D = 10 ** (-4 + (5 * k) / 50);
			for (let i = 1; i <= 400; i++) {
				const beta = (0.9706021928121271 * i) / 400;
				for (const taps of ['corner', 'flange'] as const) {
					const r = movedRatioBound(D, beta * D, taps);
					expect(r, `${taps} ${D} ${beta}`).not.toBeNull();
					expect(r!, `${taps} ${D} ${beta}`).toBeLessThan(RATIO_BOUND_ANY);
				}
			}
		}
	});
});
