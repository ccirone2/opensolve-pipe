/**
 * An assigned-flow node's flow as entered (SDD §4.11): a direction and a magnitude in the display
 * flow unit, stored as one signed SI value. Unit factors are written here from their definitions
 * (NIST SP 811: 1 in = 0.0254 m; US gallon = 231 in³), not taken from units.ts. Flows are
 * made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import type { UnitPreferences } from '../api/types';
import openapi from '../api/openapi.json';
import {
	assignedFlowText,
	DIRECTION_LABELS,
	flowDirection,
	magnitudeBounds,
	signedFlow
} from './assigned-flow';
import { CATEGORY_UNITS, formatNumber, fromSI, IMPERIAL_UNITS, SI_UNITS, toSI } from './units';

const GPM = (231 * 0.0254 ** 3) / 60; // m³/s

describe('direction and sign', () => {
	it('reads a demand as positive, a supply as negative, and 0 as neither', () => {
		expect(flowDirection(0.004)).toBe('demand');
		expect(flowDirection(-0.004)).toBe('supply');
		expect(flowDirection(0)).toBeNull();
		expect(flowDirection(-0)).toBeNull();
		expect(DIRECTION_LABELS.demand).toMatch(/leaves the network/);
		expect(DIRECTION_LABELS.supply).toMatch(/enters the network/);
	});

	it('signs a magnitude by its direction, and stores 0 as +0 either way', () => {
		expect(signedFlow(0.004, 'demand')).toBe(0.004);
		expect(signedFlow(0.004, 'supply')).toBe(-0.004);
		expect(Object.is(signedFlow(0, 'supply'), 0)).toBe(true);
		expect(Object.is(signedFlow(0, 'demand'), 0)).toBe(true);
	});

	it('bounds the magnitude by the schema’s bounds on the signed flow, in each direction', () => {
		const flow = openapi.components.schemas.AssignedFlow.properties.flow;
		expect(magnitudeBounds('demand')).toEqual({ minimum: 0, maximum: flow.maximum });
		expect(magnitudeBounds('supply')).toEqual({ minimum: 0, maximum: -flow.minimum });
	});
});

describe('round trip through the display unit', () => {
	// A magnitude typed in each flow unit is stored once in SI; switching the direction only
	// changes the sign, and the field shows what was typed.
	const typed = ['5', '12.5', '0.0375', '1234.56'];
	for (const unit of CATEGORY_UNITS.flow) {
		it(`keeps a value typed in ${unit} exactly, in both directions`, () => {
			for (const text of typed) {
				const si = toSI(Number(text), unit);
				const demand = signedFlow(si, 'demand');
				const supply = signedFlow(si, 'supply');
				expect(supply).toBe(-demand);
				expect(signedFlow(Math.abs(supply), 'demand')).toBe(demand);
				expect(-(-demand)).toBe(demand);
				for (const stored of [demand, supply]) {
					expect(formatNumber(fromSI(Math.abs(stored), unit), 6)).toBe(text);
				}
			}
		});
	}

	it('converts with the defined factors', () => {
		expect(toSI(5, 'L/s')).toBeCloseTo(0.005, 15);
		expect(toSI(100, 'gpm')).toBeCloseTo(100 * GPM, 15);
		expect(toSI(36, 'm3/h')).toBeCloseTo(0.01, 15);
	});
});

describe('as entered, in text', () => {
	const gpm: UnitPreferences = { ...IMPERIAL_UNITS };
	it('names the direction and shows the magnitude in the display unit', () => {
		expect(assignedFlowText(0.005, SI_UNITS)).toBe('Demand 5 L/s');
		expect(assignedFlowText(-0.005, SI_UNITS)).toBe('Supply 5 L/s');
		expect(assignedFlowText(-100 * GPM, gpm)).toBe('Supply 100 gpm');
		expect(assignedFlowText(0, SI_UNITS)).toBe('0 L/s (no flow, as a plug)');
	});
});
