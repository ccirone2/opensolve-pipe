import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import type { UnitPreferences } from '../api/types';
import {
	CATEGORY_UNITS,
	displayUnit,
	formatNumber,
	formatNumberTowardZero,
	formatValue,
	fromSI,
	IMPERIAL_UNITS,
	isUnitId,
	parseInput,
	parseNumber,
	PREFERENCE_CATEGORIES,
	SI_UNITS,
	toSI,
	unitLabel,
	type UnitCategory,
	type UnitId
} from './units';

// Definitions, restated here from NIST SP 811 (2008) Appendix B and the 1959 international
// yard and pound, so the registry is checked against them rather than against itself.
const ft = 0.3048;
const inch = 0.0254;
const lb = 0.45359237;
const gn = 9.80665;
const lbf = lb * gn;
const gallon = 231 * inch ** 3;

function expectRelative(actual: number, expected: number, tolerance = 1e-14) {
	const scale = Math.max(Math.abs(expected), 1e-300);
	expect(Math.abs(actual - expected) / scale).toBeLessThanOrEqual(tolerance);
}

describe('unit registry', () => {
	it('round-trips every unit of every category', () => {
		const samples = [-1234.5678, -1, 0, 1e-7, 0.5, 1, 42, 98765.4321, 3.2e8];
		for (const [category, units] of Object.entries(CATEGORY_UNITS)) {
			for (const unit of units as readonly UnitId[]) {
				for (const value of samples) {
					const back = fromSI(toSI(value, unit), unit);
					expect(Math.abs(back - value), `${category} ${unit} ${value}`).toBeLessThanOrEqual(
						1e-12 * Math.max(1, Math.abs(value))
					);
				}
			}
		}
	});

	it('converts lengths, diameters and heads exactly', () => {
		expect(toSI(1, 'ft')).toBe(ft);
		expect(toSI(1, 'in')).toBe(inch);
		expect(toSI(1, 'mm')).toBe(0.001);
		expect(toSI(1, 'm')).toBe(1);
		expectRelative(toSI(12, 'in'), toSI(1, 'ft'));
		expectRelative(fromSI(1, 'ft'), 1 / ft);
		expectRelative(fromSI(0.1016, 'in'), 4);
	});

	it('converts pressures exactly (psi = lbf/in²)', () => {
		expectRelative(toSI(1, 'psi'), lbf / inch ** 2);
		expect(toSI(1, 'bar')).toBe(1e5);
		expect(toSI(1, 'kPa')).toBe(1e3);
		expect(toSI(1, 'MPa')).toBe(1e6);
		expect(toSI(1, 'Pa')).toBe(1);
		expectRelative(fromSI(1e5, 'psi'), 1e5 / (lbf / inch ** 2));
	});

	it('converts flows exactly (US gallon = 231 in³)', () => {
		expectRelative(toSI(1, 'gpm'), gallon / 60);
		expectRelative(fromSI(toSI(1, 'gpm'), 'L/min'), (231 * 2.54 ** 3) / 1000);
		expectRelative(toSI(1, 'm3/h'), 1 / 3600);
		expectRelative(toSI(1, 'L/s'), 1e-3);
		expectRelative(toSI(1, 'L/min'), 1e-3 / 60);
		expect(toSI(1, 'm3/s')).toBe(1);
	});

	it('converts velocity, density, viscosity and power exactly', () => {
		expect(toSI(1, 'ft/s')).toBe(ft);
		expectRelative(toSI(1, 'lb/ft3'), lb / ft ** 3);
		expectRelative(toSI(1, 'cP'), 1e-3); // 1 P = 0.1 Pa·s
		expectRelative(toSI(1, 'mPa.s'), 1e-3);
		expect(toSI(1, 'cP')).toBe(toSI(1, 'mPa.s'));
		expect(toSI(1, 'Pa.s')).toBe(1);
		expectRelative(toSI(1, 'hp'), 550 * ft * lbf); // 550 ft·lbf/s
		expect(toSI(1, 'kW')).toBe(1000);
	});

	it('converts temperatures by their definitions', () => {
		for (const f of [-459.67, -40, 0, 32, 68, 212, 1000]) {
			expect(toSI(f, 'F')).toBeCloseTo(((f + 459.67) * 5) / 9, 10);
		}
		expect(toSI(32, 'F')).toBeCloseTo(273.15, 10);
		expect(toSI(212, 'F')).toBeCloseTo(373.15, 10);
		expect(toSI(-40, 'F')).toBeCloseTo(toSI(-40, 'C'), 10);
		expect(toSI(20, 'C')).toBeCloseTo(293.15, 12);
		expect(fromSI(0, 'C')).toBeCloseTo(-273.15, 12);
		expect(fromSI(293.15, 'F')).toBeCloseTo(68, 10);
		expect(toSI(300, 'K')).toBe(300);
	});

	it('shows fractions as percentages and angles in degrees', () => {
		expect(toSI(85, '%')).toBeCloseTo(0.85, 15);
		expect(fromSI(0.3, '%')).toBeCloseTo(30, 12);
		expect(toSI(45, 'deg')).toBe(45);
	});

	it('rejects unknown units', () => {
		expect(() => toSI(1, 'furlong' as UnitId)).toThrow(RangeError);
		expect(isUnitId('psi')).toBe(true);
		expect(isUnitId('furlong')).toBe(false);
		expect(isUnitId('toString')).toBe(false);
	});
});

describe('unit preferences', () => {
	const schema = openapi.components.schemas.UnitPreferences.properties as Record<
		string,
		{ enum: string[]; default: string }
	>;

	it('offer exactly the units of the API UnitPreferences, with the same defaults as SI_UNITS', () => {
		expect([...PREFERENCE_CATEGORIES].sort()).toEqual(Object.keys(schema).sort());
		for (const category of PREFERENCE_CATEGORIES) {
			expect([...CATEGORY_UNITS[category]].sort(), category).toEqual(
				[...schema[category]!.enum].sort()
			);
			expect(SI_UNITS[category], category).toBe(schema[category]!.default);
		}
	});

	it('have an Imperial preset using US customary units', () => {
		expect(IMPERIAL_UNITS).toEqual({
			length: 'ft',
			diameter: 'in',
			pressure: 'psi',
			head: 'ft',
			flow: 'gpm',
			velocity: 'ft/s',
			temperature: 'F',
			density: 'lb/ft3',
			viscosity: 'cP'
		});
		for (const category of PREFERENCE_CATEGORIES) {
			expect(schema[category]!.enum).toContain(IMPERIAL_UNITS[category]);
		}
		expect(Object.isFrozen(SI_UNITS) && Object.isFrozen(IMPERIAL_UNITS)).toBe(true);
	});

	it('choose display units per category', () => {
		const mixed: UnitPreferences = { ...SI_UNITS, pressure: 'psi', flow: 'gpm' };
		expect(displayUnit('pressure', mixed)).toBe('psi');
		expect(displayUnit('length', mixed)).toBe('m');
		expect(displayUnit('power', SI_UNITS)).toBe('kW');
		expect(displayUnit('power', IMPERIAL_UNITS)).toBe('hp');
		expect(displayUnit('power', mixed)).toBe('hp');
		expect(displayUnit('dimensionless', SI_UNITS)).toBe('');
		expect(displayUnit('fraction', SI_UNITS)).toBe('%');
		expect(displayUnit('angle', SI_UNITS)).toBe('deg');
	});
});

describe('labels', () => {
	it('mark gauge and absolute pressures', () => {
		expect(unitLabel('pressure', 'kPa', { gauge: true })).toBe('kPa(g)');
		expect(unitLabel('pressure', 'kPa', { absolute: true })).toBe('kPa(a)');
		expect(unitLabel('pressure', 'bar', { gauge: true })).toBe('bar(g)');
		expect(unitLabel('pressure', 'psi', { gauge: true })).toBe('psig');
		expect(unitLabel('pressure', 'psi', { absolute: true })).toBe('psia');
		expect(unitLabel('pressure', 'psi')).toBe('psi');
		expect(unitLabel('pressure', 'Pa', { gauge: true })).toBe('Pa(g)');
	});

	it('use proper symbols and ignore gauge marks outside pressure', () => {
		const labels: [UnitCategory, UnitId, string][] = [
			['temperature', 'C', '°C'],
			['temperature', 'F', '°F'],
			['temperature', 'K', 'K'],
			['flow', 'm3/s', 'm³/s'],
			['flow', 'm3/h', 'm³/h'],
			['density', 'kg/m3', 'kg/m³'],
			['density', 'lb/ft3', 'lb/ft³'],
			['viscosity', 'Pa.s', 'Pa·s'],
			['viscosity', 'mPa.s', 'mPa·s'],
			['viscosity', 'cP', 'cP'],
			['head', 'ft', 'ft'],
			['angle', 'deg', '°']
		];
		for (const [category, unit, label] of labels) {
			expect(unitLabel(category, unit, { gauge: true })).toBe(label);
		}
	});
});

describe('formatting and parsing', () => {
	it('formats numbers to significant digits', () => {
		expect(formatNumber(0)).toBe('0');
		expect(formatNumber(-0)).toBe('0');
		expect(formatNumber(1234.5678)).toBe('1235');
		expect(formatNumber(1.5)).toBe('1.5');
		expect(formatNumber(-0.012345)).toBe('-0.01235');
		expect(formatNumber(0.0000123456)).toBe('1.235e-5');
		expect(formatNumber(1e12)).toBe('1e12');
		expect(formatNumber(101325, 6)).toBe('101325');
		expect(formatNumber(Number.NaN)).toBe('—');
		expect(formatNumber(Infinity)).toBe('—');
	});

	it('formats a bound rounded toward zero, so that a value below what is shown is below it', () => {
		expect(formatNumberTowardZero(573.46469)).toBe('573.4');
		expect(formatNumberTowardZero(-573.46469)).toBe('-573.4');
		expect(formatNumberTowardZero(9.99961)).toBe('9.999');
		expect(formatNumberTowardZero(12345)).toBe('12340');
		expect(formatNumberTowardZero(0.000013579)).toBe('1.357e-5');
		// Exact at 4 digits, or within floating-point error of it: not a digit lower.
		expect(formatNumberTowardZero(36.18)).toBe('36.18');
		expect(formatNumberTowardZero(36.17999999999999)).toBe('36.18');
		expect(formatNumberTowardZero(80)).toBe('80');
		expect(formatNumberTowardZero(1.35e-5)).toBe('1.35e-5');
		expect(formatNumberTowardZero(0)).toBe('0');
		expect(formatNumberTowardZero(Number.NaN)).toBe('—');
		const bound = 0.03618; // m³/s: 573.46 gpm, 36.18 L/s
		expect(formatValue(bound, 'flow', IMPERIAL_UNITS, 4, { towardZero: true })).toBe('573.4 gpm');
		expect(formatValue(bound, 'flow', SI_UNITS, 4, { towardZero: true })).toBe('36.18 L/s');
		expect(formatValue(bound, 'flow', IMPERIAL_UNITS)).toBe('573.5 gpm');
	});

	it('formats SI values in the display unit', () => {
		expect(formatValue(101325, 'pressure', SI_UNITS)).toBe('101.3 kPa');
		expect(formatValue(101325, 'pressure', SI_UNITS, 4, { gauge: true })).toBe('101.3 kPa(g)');
		expect(
			formatValue((lbf / inch ** 2) * 50, 'pressure', IMPERIAL_UNITS, 4, { gauge: true })
		).toBe('50 psig');
		expect(formatValue(293.15, 'temperature', SI_UNITS)).toBe('20 °C');
		expect(formatValue(293.15, 'temperature', IMPERIAL_UNITS)).toBe('68 °F');
		expect(formatValue(0.01, 'flow', SI_UNITS)).toBe('10 L/s');
		expect(formatValue((gallon / 60) * 150, 'flow', IMPERIAL_UNITS)).toBe('150 gpm');
		expect(formatValue(0.1016, 'diameter', IMPERIAL_UNITS)).toBe('4 in');
		expect(formatValue(745.6998715822702, 'power', IMPERIAL_UNITS)).toBe('1 hp');
		expect(formatValue(0.85, 'fraction', SI_UNITS)).toBe('85 %');
		expect(formatValue(45, 'angle', SI_UNITS)).toBe('45°');
		expect(formatValue(1234.5, 'dimensionless', SI_UNITS)).toBe('1235');
		expect(formatValue(1.23456, 'length', SI_UNITS, 3)).toBe('1.23 m');
		expect(formatValue(1.23456, 'length', SI_UNITS, 3, { unit: false })).toBe('1.23');
	});

	it('shows missing values as a dash', () => {
		expect(formatValue(null, 'pressure', SI_UNITS)).toBe('—');
		expect(formatValue(undefined, 'flow', SI_UNITS)).toBe('—');
		expect(formatValue(Number.NaN, 'flow', SI_UNITS)).toBe('—');
	});

	it('parses typed numbers and never returns NaN', () => {
		expect(parseNumber('12.5')).toBe(12.5);
		expect(parseNumber(' -3 ')).toBe(-3);
		expect(parseNumber('+.5')).toBe(0.5);
		expect(parseNumber('5.')).toBe(5);
		expect(parseNumber('1e-3')).toBe(0.001);
		expect(parseNumber('2.5E+2')).toBe(250);
		for (const bad of [
			'',
			' ',
			'abc',
			'1,5',
			'1.2.3',
			'0x10',
			'Infinity',
			'NaN',
			'1e999',
			'--1',
			'.'
		]) {
			expect(parseNumber(bad), bad).toBeNull();
		}
	});

	it('converts typed input to SI', () => {
		expect(parseInput('100', 'kPa')).toBe(100_000);
		expectRelative(parseInput('50', 'psi')!, (50 * lbf) / inch ** 2);
		expect(parseInput('20', 'C')).toBeCloseTo(293.15, 12);
		expect(parseInput('x', 'kPa')).toBeNull();
	});
});
