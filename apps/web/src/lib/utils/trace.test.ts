/**
 * Trace values in display units, and the methods summary as text. Expected conversions are
 * computed here from the unit definitions.
 */
import { describe, expect, it } from 'vitest';
import { SAMPLE_METHODS } from '../testing/results';
import { pumpTransferExample } from './examples';
import { formatQuantity, methodsText, quantityMapping, traceName, traceTextValue } from './trace';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

const IN = 0.0254;
const PSI = (0.45359237 * 9.80665) / (IN * IN);
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

describe('trace quantities', () => {
	it('maps SI unit strings to display categories', () => {
		expect(quantityMapping('Inner diameter', 'm')?.category).toBe('diameter');
		expect(quantityMapping('Friction head loss', 'm')?.category).toBe('head');
		expect(quantityMapping('Length', 'm')?.category).toBe('length');
		expect(quantityMapping('Flow', 'm³/s')?.category).toBe('flow');
		// Gauge or absolute comes from the unit string only, never from the name.
		expect(quantityMapping('Vapor pressure', 'Pa(a)')?.options).toEqual({ absolute: true });
		expect(quantityMapping('Vapor pressure', 'Pa')).toEqual({
			category: 'pressure',
			options: {},
			referenceUnstated: true
		});
		expect(quantityMapping('Inlet pressure', 'Pa (gauge)')?.options).toEqual({ gauge: true });
		expect(quantityMapping('Pressure drop', 'Pa (difference)')).toEqual({
			category: 'pressure',
			options: {}
		});
		// Kelvin may be a temperature or a difference (different conversions): shown as reported.
		expect(quantityMapping('Temperature', 'K')).toBeNull();
		expect(quantityMapping('Approach', 'K')).toBeNull();
		expect(quantityMapping('Kinematic viscosity', 'm²/s')).toBeNull();
	});

	it('shows known units in display units with the SI value alongside', () => {
		expect(formatQuantity('Flow', 0.02, 'm³/s', SI_UNITS)).toEqual({
			text: '20 L/s',
			si: '0.02 m³/s'
		});
		expect(formatQuantity('Inner diameter', 0.1023, 'm', IMPERIAL_UNITS)).toEqual({
			text: `${sig4(0.1023 / IN)} in`,
			si: '0.1023 m'
		});
		expect(formatQuantity('Inlet pressure', 200000, 'Pa (gauge)', IMPERIAL_UNITS).text).toBe(
			`${sig4(200000 / PSI)} psig`
		);
		expect(formatQuantity('Velocity', 2.5, 'm/s', SI_UNITS)).toEqual({ text: '2.5 m/s' });
	});

	it('shows other values as reported', () => {
		expect(formatQuantity('Wall shear stress', 3.2, 'N/m²', SI_UNITS)).toEqual({
			text: '3.2 N/m²'
		});
		expect(formatQuantity('Reynolds number', 250000, '', SI_UNITS)).toEqual({ text: '250000' });
		expect(formatQuantity('Method', 'colebrook', '', SI_UNITS)).toEqual({ text: 'colebrook' });
		expect(formatQuantity('Laminar', true, '', SI_UNITS)).toEqual({ text: 'Yes' });
		expect(formatQuantity('Override', null, 'm', SI_UNITS)).toEqual({ text: '—' });
	});
});

describe('trace units by unit string only', () => {
	it('does not convert kelvin, whose meaning (temperature or difference) is not stated', () => {
		expect(formatQuantity('Temperature rise', 5, 'K', SI_UNITS)).toEqual({ text: '5 K' });
		expect(formatQuantity('Temperature', 293.15, 'K', SI_UNITS)).toEqual({
			text: `${sig4(293.15)} K`
		});
	});

	it('never labels a pressure absolute or gauge from its name', () => {
		expect(formatQuantity('Pressure above vapor pressure', 20000, 'Pa', SI_UNITS)).toEqual({
			text: '20 kPa',
			si: '20000 Pa'
		});
		expect(formatQuantity('Vapor pressure', 2339, 'Pa(a)', SI_UNITS).text).toBe('2.339 kPa(a)');
	});

	it('says when a pressure’s reference is not stated', () => {
		expect(formatQuantity('Upstream static pressure', 123456, 'Pa', SI_UNITS)).toEqual({
			text: '123.5 kPa (reference not stated)',
			si: '123500 Pa'
		});
		expect(formatQuantity('Pressure drop', 1000, 'Pa', SI_UNITS).text).toBe('1 kPa');
		expect(formatQuantity('Absolute suction pressure', 1000, 'Pa', SI_UNITS).text).toBe('1 kPa');
	});
});

describe('methods as text', () => {
	it('states a solve that did not converge, and results out of date', () => {
		const text = methodsText(SAMPLE_METHODS, {
			timestamp: '2026-10-21T00:00:00Z',
			converged: false,
			stale: true
		});
		expect(text).toContain('Solved: 2026-10-21T00:00:00Z\nSolve status: DID NOT CONVERGE.');
		expect(text).toContain('they are not a solution of the network');
		expect(text).toContain('Results out of date: the project changed after this solve.');
		expect(methodsText(SAMPLE_METHODS, { converged: true })).toContain('Solve status: converged.');
	});

	it('lists sections, references, assumptions and software', () => {
		expect(
			methodsText(SAMPLE_METHODS, { projectName: 'Test', timestamp: '2026-10-21T00:00:00Z' })
		).toBe(
			[
				'Calculation methods and assumptions',
				'Project: Test',
				'OpenSolve Pipe calculation methods version 1.0.0',
				'Solved: 2026-10-21T00:00:00Z',
				'',
				'Pipe friction',
				'- Darcy–Weisbach head loss.',
				'- Colebrook friction factor.',
				'References:',
				'- Colebrook, C. F. (1939).',
				'',
				'Assumptions',
				'- Steady, incompressible flow.',
				'',
				'Software',
				'- fluids 1.3.1',
				'- scipy 1.18.1',
				''
			].join('\n')
		);
	});
});

describe('trace names and port values as in Build', () => {
	const project = pumpTransferExample();

	it('names a port node key, keeping the key', () => {
		expect(traceTextValue('P1:discharge', project)).toBe(
			'Discharge of Transfer pump (P1:discharge)'
		);
		expect(traceTextValue('R2:port_1', project)).toBe('Port 1 of Discharge tank (R2:port_1)');
		// Not a port of the project, or not a key: as reported.
		expect(traceTextValue('P1:nope', project)).toBe('P1:nope');
		expect(traceTextValue('Carbon steel (carbon_steel)', project)).toBe(
			'Carbon steel (carbon_steel)'
		);
	});

	it('keeps the API pipe and fitting numbers (from 1, as in Build), and names ports of the element', () => {
		expect(traceName('Pipe 1 length L', project, 'L1')).toBe('Pipe 1 length L');
		expect(traceName('Fitting 2 (exit) type', project, 'L3')).toBe('Fitting 2 (exit) type');
		expect(traceName('Port port_1 outflow', project, 'R1')).toBe('Port 1 outflow');
		expect(traceName('Port suction static pressure p', project, 'P1')).toBe(
			'Suction static pressure p'
		);
		// A port the element does not have, or anything else: unchanged.
		expect(traceName('Port inlet flow', project, 'R1')).toBe('Port inlet flow');
		expect(traceName('Friction method', project, 'L1')).toBe('Friction method');
	});
});
