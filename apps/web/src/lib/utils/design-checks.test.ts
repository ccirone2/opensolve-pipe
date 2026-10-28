/**
 * Design check results in words and display units (CLAUDE.md D19; utils/design-checks.ts): the
 * real API's results of the shared fixture's `design-checks` case (export_input.py: the pump at
 * 90 % speed with every check on, US display units), and made-up results (test inputs) for the
 * wordings the fixture does not reach. The words are built from the result's numbers, never from
 * its message.
 */
import { describe, expect, it } from 'vitest';
import type { DesignCheckResult } from '../api/types';
import { fixtureInput } from './export/export-testing.testing';
import {
	CHECK_CATEGORIES,
	checkCounts,
	checkElement,
	checkText,
	groupChecks,
	settingsSourceLabel,
	sourceLabel
} from './design-checks';
import { designCheckPresets } from './model-rules';
import { displayUnit, formatValue, fromSI, SI_UNITS } from './units';

const input = fixtureInput('design-checks');
const solved = input.cases[0]!.response!.solvedState;
const results = solved.designChecks;
const prefs = input.prefs;
const byCheck = (check: string, element: string) =>
	results.find((r) => r.check === check && (r.componentId ?? r.connectionId) === element)!;

/** A made-up result (test input): a pipe velocity check unless told otherwise. */
function result(values: Partial<DesignCheckResult>): DesignCheckResult {
	return {
		check: 'pipe_velocity',
		componentId: null,
		connectionId: 'L1',
		outcome: 'pass',
		value: 2,
		pipeIndex: 0,
		pipesOutside: [],
		limits: { min: null, max: 3 },
		unit: 'm/s',
		source: 'user',
		message: '',
		...values
	};
}

describe('the fixture', () => {
	it('is US display units with every outcome', () => {
		expect([prefs.flow, prefs.head, prefs.velocity]).toEqual(['gpm', 'ft', 'ft/s']);
		expect(new Set(results.map((r) => r.outcome))).toEqual(
			new Set(['pass', 'fail', 'not_evaluated'])
		);
	});
});

describe('checkText', () => {
	it('words each check from its numbers, in display units', () => {
		const f = (si: number, check: DesignCheckResult['check']) =>
			formatValue(si, CHECK_CATEGORIES[check], prefs, 4);
		const region = byCheck('operating_region', 'P1');
		expect(checkText(region, prefs)).toBe(
			`Flow ${f(region.value!, 'operating_region')} of the best efficiency flow, within 70 % to 120 %`
		);
		expect(checkText(region, prefs)).toMatch(/^Flow 119\.6 % of/);
		const motor = byCheck('motor_power', 'P1');
		expect(checkText(motor, prefs)).toBe(
			`Shaft power ${f(motor.value!, 'motor_power')}, above the motor's rated ${f(4000, 'motor_power')}`
		);
		const aor = byCheck('allowable_region', 'P1');
		expect(checkText(aor, prefs)).toBe(
			`Flow at rated speed ${f(aor.value!, 'allowable_region')}, within the allowable region ${f(0.006, 'allowable_region')} to ${f(0.026, 'allowable_region')}`
		);
		const minimum = byCheck('minimum_flow', 'P1');
		expect(checkText(minimum, prefs)).toBe(
			`Flow at rated speed ${f(minimum.value!, 'minimum_flow')}, at least the minimum ${f(0.005, 'minimum_flow')}`
		);
		const fast = byCheck('pipe_velocity', 'L2');
		expect(checkText(fast, prefs)).toBe(
			`Velocity ${f(fast.value!, 'pipe_velocity')} in pipe 1, above ${f(3, 'pipe_velocity')}`
		);
		expect(checkText(fast, prefs)).toContain('ft/s');
		const ok = byCheck('pipe_velocity', 'L1');
		expect(checkText(ok, prefs)).toBe(
			`Every pipe at most ${f(3, 'pipe_velocity')} (highest ${f(ok.value!, 'pipe_velocity')}, pipe 1)`
		);
	});

	it("says why a check was not evaluated, in the API's words (no number or id in them)", () => {
		const npsh = byCheck('npsh_margin', 'P1');
		expect(npsh.outcome).toBe('not_evaluated');
		expect(checkText(npsh, prefs)).toBe('The pump curve has no NPSHr curve');
	});

	it('gives a value just past its limit the digits that tell them apart', () => {
		const just = result({ outcome: 'fail', value: 3.0000004, limits: { min: null, max: 3 } });
		const text = checkText(just, SI_UNITS);
		expect(text).toBe('Velocity 3.0000004 m/s in pipe 1, above 3 m/s');
		// Equal values need no more digits.
		expect(checkText(result({ value: 3 }), SI_UNITS)).toBe(
			'Every pipe at most 3 m/s (highest 3 m/s, pipe 1)'
		);
	});

	it('tells doubles one ulp apart, and says so when display units make them read the same', () => {
		/** The next double above `x` (> 0). */
		const up = (x: number) => {
			const view = new DataView(new ArrayBuffer(8));
			view.setFloat64(0, x);
			view.setBigUint64(0, view.getBigUint64(0) + 1n);
			return view.getFloat64(0);
		};
		const minimum = (value: number, floor: number) =>
			result({
				check: 'minimum_flow',
				componentId: 'P1',
				connectionId: null,
				outcome: value >= floor ? 'pass' : 'fail',
				value,
				limits: { min: floor, max: null },
				unit: 'm³/s'
			});
		const floor = 0.0031702823690999997;
		const below = checkText(minimum(floor - 1e-18, floor), SI_UNITS);
		const [shown, limit] = [...below.matchAll(/([\d.]+) L\/s/g)].map((m) => m[1]);
		expect(shown).not.toBe(limit);
		expect(below).not.toContain('round-off');
		// Two neighbouring doubles that the conversion to L/s makes equal: the words say so.
		let a = floor;
		while (
			fromSI(up(a), displayUnit('flow', SI_UNITS)) !== fromSI(a, displayUnit('flow', SI_UNITS))
		)
			a = up(a);
		const tied = checkText(minimum(a, up(a)), SI_UNITS);
		expect(tied).toMatch(/, below the minimum [\d.]+ L\/s \(by round-off\)$/);
	});

	it('words NPSH, one-sided regions, a minimum velocity and several pipes', () => {
		expect(
			checkText(
				result({
					check: 'npsh_margin',
					componentId: 'P1',
					connectionId: null,
					value: 4,
					limits: { min: 4.4, max: null },
					outcome: 'fail'
				}),
				SI_UNITS
			)
		).toBe('NPSHa 4 m, below the 4.4 m required');
		const region = (outcome: 'pass' | 'fail', min: number | null, max: number | null) =>
			checkText(
				result({
					check: 'operating_region',
					componentId: 'P1',
					connectionId: null,
					value: 0.65,
					limits: { min, max },
					outcome
				}),
				SI_UNITS
			);
		expect(region('fail', 0.7, null)).toBe('Flow 65 % of the best efficiency flow, below 70 %');
		expect(region('pass', null, 1.2)).toBe('Flow 65 % of the best efficiency flow, at most 120 %');
		expect(
			checkText(
				result({
					outcome: 'fail',
					value: 0.4,
					pipeIndex: 2,
					pipesOutside: [0, 2],
					limits: { min: 0.5, max: null }
				}),
				SI_UNITS
			)
		).toBe('Velocity 0.4 m/s in pipe 3, below 0.5 m/s; pipes outside: 1, 3');
		expect(checkText(result({ value: 0.6, limits: { min: 0.5, max: null } }), SI_UNITS)).toBe(
			'Every pipe at least 0.5 m/s (lowest 0.6 m/s, pipe 1)'
		);
	});
});

describe('grouping, counts, elements and sources', () => {
	it('lists not met, then met, then not evaluated, each in the API order', () => {
		const groups = groupChecks(results);
		expect(groups.map((g) => g.outcome)).toEqual(['fail', 'pass', 'not_evaluated']);
		expect(groups[0]!.results.map((r) => r.check)).toEqual([
			'motor_power',
			'pipe_velocity',
			'pipe_velocity'
		]);
		expect(groups.flatMap((g) => g.results)).toHaveLength(results.length);
		expect(checkCounts(results)).toBe('3 not met · 4 met · 1 not evaluated');
		expect(checkCounts([])).toBe('');
		expect(checkElement(byCheck('motor_power', 'P1'))).toEqual({ kind: 'component', id: 'P1' });
		expect(checkElement(byCheck('pipe_velocity', 'L2'))).toEqual({
			kind: 'connection',
			id: 'L2'
		});
	});

	it("names each source: a preset by its name, the user's values, the manufacturer data", () => {
		const [api610, hi] = ['api610_por', 'hi961_2012_general'].map((id) =>
			designCheckPresets().find((p) => p.id === id)!
		);
		expect(sourceLabel(byCheck('operating_region', 'P1').source)).toBe('API 610 preset');
		expect(sourceLabel(byCheck('operating_region', 'P1').source)).toBe(
			sourceLabel(api610!.citation)
		);
		expect(sourceLabel(hi!.citation)).toBe('HI 9.6.1-2012 (general) preset');
		expect(sourceLabel(byCheck('pipe_velocity', 'L1').source)).toBe('your values');
		expect(sourceLabel(byCheck('motor_power', 'P1').source)).toBe(
			"the pump curve's manufacturer data"
		);
		expect(settingsSourceLabel({ kind: 'preset', preset: 'api610_por' })).toBe('API 610 preset');
		expect(settingsSourceLabel({ kind: 'user' })).toBe('your values');
	});

	it('maps each check to the display category of the unit its API value is in', () => {
		expect(CHECK_CATEGORIES).toEqual({
			npsh_margin: 'head',
			operating_region: 'fraction',
			allowable_region: 'flow',
			minimum_flow: 'flow',
			motor_power: 'power',
			pipe_velocity: 'velocity'
		});
		const categoryOf: Record<string, string> = {
			m: 'head',
			'1': 'fraction',
			'm³/s': 'flow',
			W: 'power',
			'm/s': 'velocity'
		};
		for (const r of results) expect(CHECK_CATEGORIES[r.check]).toBe(categoryOf[r.unit]);
		// Each in its display unit, not only through CHECK_CATEGORIES.
		expect(checkText(byCheck('allowable_region', 'P1'), prefs)).toMatch(
			/ gpm, within .* gpm to .* gpm$/
		);
		expect(checkText(byCheck('minimum_flow', 'P1'), prefs)).toMatch(
			/ gpm, at least the minimum .* gpm$/
		);
	});
});
