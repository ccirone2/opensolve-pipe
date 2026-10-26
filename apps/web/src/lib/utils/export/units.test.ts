/**
 * The units of a file (proposal export.md §2.3): display mode follows the screen's units (power
 * in hp with gpm, else kW; fractions in %); SI mode is the base units, power in W, fractions 0–1
 * with no unit, and every value the API's double.
 */
import { describe, expect, it } from 'vitest';
import { IMPERIAL_UNITS, SI_UNITS } from '../units';
import { exportUnit, ExportUnitSystem, SI_BASE_UNITS } from './units';

describe('SI mode', () => {
	const si = new ExportUnitSystem('si', IMPERIAL_UNITS);

	it('is the base units, whatever the display units', () => {
		expect(SI_BASE_UNITS).toEqual({
			length: 'm',
			diameter: 'm',
			pressure: 'Pa',
			head: 'm',
			flow: 'm3/s',
			velocity: 'm/s',
			temperature: 'K',
			density: 'kg/m3',
			viscosity: 'Pa.s'
		});
		expect(si.unit('power')).toBe('W');
		expect(si.unit('fraction')).toBe('');
		expect(si.unit('dimensionless')).toBe('');
		expect(si.prefs).toBe(SI_BASE_UNITS);
	});

	it('labels pressures with their marker and gives a fraction no unit', () => {
		expect(si.label('pressure', { gauge: true })).toBe('Pa(g)');
		expect(si.label('pressure', { absolute: true })).toBe('Pa(a)');
		expect(si.label('pressure')).toBe('Pa');
		expect(si.label('fraction')).toBe('');
		expect(si.header('Speed', 'fraction')).toBe('Speed');
		expect(si.header('Flow', 'flow')).toBe('Flow [m³/s]');
	});

	it('writes every value as the API sent it, bit for bit', () => {
		for (const v of [0.1 + 0.2, -0, 1e-300, 293.15, 101325.00000000001, -52340.5]) {
			for (const category of [
				'length',
				'pressure',
				'flow',
				'temperature',
				'power',
				'fraction'
			] as const) {
				expect(Object.is(si.value(v, category), v)).toBe(true);
			}
		}
		expect(si.value(null, 'flow')).toBeNull();
		expect(si.value(Number.NaN, 'flow')).toBeNull();
	});
});

describe('display mode', () => {
	it('follows the display units: kW, or hp with gpm; fractions in %', () => {
		expect(exportUnit('power', 'display', SI_UNITS)).toBe('kW');
		expect(exportUnit('power', 'display', IMPERIAL_UNITS)).toBe('hp');
		expect(exportUnit('fraction', 'display', SI_UNITS)).toBe('%');
		expect(exportUnit('flow', 'display', SI_UNITS)).toBe('L/s');
		const us = new ExportUnitSystem('display', IMPERIAL_UNITS);
		expect(us.label('pressure', { gauge: true })).toBe('psig');
		expect(us.label('pressure', { absolute: true })).toBe('psia');
		expect(us.header('Head', 'head')).toBe('Head [ft]');
	});

	it('converts by the unit registry: 0.02 m³/s is 20 L/s, 0.86 is 86 %', () => {
		const display = new ExportUnitSystem('display', SI_UNITS);
		// The registry's own arithmetic: (v − offset) / factor.
		expect(display.value(0.02, 'flow')).toBe(0.02 / 1e-3);
		expect(display.value(0.86, 'fraction')).toBe(0.86 / 0.01);
		expect(display.value(293.15, 'temperature')).toBe((293.15 - 273.15) / 1);
		expect(display.value(250_000, 'pressure')).toBe(250);
	});
});
