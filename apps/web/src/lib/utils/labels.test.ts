import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import type { Pump } from '../api/types';
import { pumpTransferExample } from './examples';
import { IMPERIAL_UNITS, SI_UNITS } from './units';
import {
	componentName,
	fieldLabel,
	fittingFallbackName,
	fluidChipText,
	humanize,
	npsLabel,
	portLabel,
	portOf,
	PUMP_CONTROL_LABELS,
	PUMP_CONTROL_MODE_NAMES,
	PUMP_CONTROL_STATE_LABELS
} from './labels';
import { fittingTypes } from './schema-bounds';
import { INCH } from './units';

describe('labels', () => {
	it('names ports', () => {
		expect(portLabel('run_inlet')).toBe('Run inlet');
		expect(portLabel('port_12')).toBe('Port 12');
		expect(portLabel('outlet_2')).toBe('Outlet 2 (branch leg)');
		expect(portLabel('some_new_port')).toBe('Some new port');
	});

	it('names components and their ports', () => {
		const project = pumpTransferExample();
		expect(componentName(project, 'P1')).toBe('Transfer pump');
		expect(componentName(project, 'gone')).toBe('gone');
		expect(portOf(project, 'P1', 'suction')).toBe('Suction of Transfer pump');
	});

	it('shows nominal sizes as NPS, using the library designation when known', () => {
		expect(npsLabel(4 * INCH)).toBe('NPS 4');
		expect(npsLabel(2.5 * INCH, [{ nominalSize: 0.0635, nps: '2-1/2' }])).toBe('NPS 2-1/2');
		expect(npsLabel(null)).toBe('NPS —');
	});

	it('has a fallback name for every fitting type in the schema', () => {
		for (const type of fittingTypes()) {
			expect(fittingFallbackName(type)).not.toBe(humanize(type));
		}
	});

	it('names the speed-control fields, modes and states of the API schema', () => {
		const pump = pumpTransferExample().components[1] as Pump;
		expect(fieldLabel(pump, 'speed')).toBe('speed');
		const controlled: Pump = { ...pump, control: { mode: 'flow', setpoint: 0.01, minSpeed: 0.4 } };
		expect(fieldLabel(controlled, 'speed')).toBe('maximum speed');
		expect(fieldLabel(controlled, 'control.minSpeed')).toBe('minimum speed');
		expect(fieldLabel(controlled, 'control.setpoint')).toBe('flow setpoint');
		expect(fieldLabel(controlled, 'elevation')).toBe('elevation');
		const schemas = openapi.components.schemas;
		const mode = schemas.PumpControl.properties.mode.const;
		expect(Object.keys(PUMP_CONTROL_MODE_NAMES)).toEqual([mode]);
		expect(Object.keys(PUMP_CONTROL_LABELS)).toEqual(['fixed', mode]);
		expect(Object.keys(PUMP_CONTROL_STATE_LABELS).sort()).toEqual(
			[...schemas.PumpControlResult.properties.state.enum].sort()
		);
	});
});

describe('fluidChipText', () => {
	it('names a built-in fluid with its temperature in the display unit', () => {
		const water = { kind: 'builtin', fluidId: 'water', temperature: 293.15 } as const;
		expect(fluidChipText(water, { ...SI_UNITS })).toBe('Water · 20 °C');
		expect(fluidChipText(water, { ...IMPERIAL_UNITS })).toBe('Water · 68 °F');
	});

	it('gives a glycol its concentration, and a custom fluid its name', () => {
		expect(
			fluidChipText(
				{ kind: 'builtin', fluidId: 'ethylene_glycol', temperature: 278.15, concentration: 0.3 },
				{ ...SI_UNITS }
			)
		).toBe('Ethylene glycol 30 % · 5 °C');
		expect(
			fluidChipText(
				{ kind: 'custom', name: 'Brine', density: 1100, dynamicViscosity: 0.0015 },
				{ ...SI_UNITS }
			)
		).toBe('Brine');
	});
});
