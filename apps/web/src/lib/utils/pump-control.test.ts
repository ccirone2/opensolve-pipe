/**
 * The flow-control draft of the Build panel: a control is complete only with both values entered,
 * within the schema's bounds and with the minimum speed below the pump's speed (the maximum), and
 * the bounds the form offers are the schema's, tightened by that order. Control values are
 * made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import type { Pump } from '../api/types';
import { createComponent, createEmptyProject } from './factory';
import {
	completedControl,
	controlFieldBounds,
	draftProblem,
	EMPTY_CONTROL_DRAFT,
	speedBounds
} from './pump-control';
import { schemaBounds } from './schema-bounds';

const pump = (speed = 1): Pump => ({
	...(createComponent('pump', createEmptyProject()) as Pump),
	speed
});

describe('flow-control draft', () => {
	it('is incomplete until both values are entered', () => {
		expect(draftProblem(pump(), EMPTY_CONTROL_DRAFT)).toBe('incomplete');
		expect(draftProblem(pump(), { setpoint: 0.01, minSpeed: null })).toBe('incomplete');
		expect(draftProblem(pump(), { setpoint: null, minSpeed: 0.4 })).toBe('incomplete');
		expect(completedControl(pump(), { setpoint: 0.01, minSpeed: null })).toBeNull();
	});

	it('completes to the whole control when valid, the minimum speed below the maximum', () => {
		expect(completedControl(pump(0.9), { setpoint: 0.01, minSpeed: 0.4 })).toEqual({
			mode: 'flow',
			setpoint: 0.01,
			minSpeed: 0.4
		});
		expect(draftProblem(pump(0.9), { setpoint: 0.01, minSpeed: 0.9 })).toBe('invalid');
		expect(draftProblem(pump(0.9), { setpoint: 0.01, minSpeed: 0.95 })).toBe('invalid');
		expect(completedControl(pump(0.9), { setpoint: 0.01, minSpeed: 0.9 })).toBeNull();
	});

	it("is invalid outside the schema's bounds", () => {
		const { maximum } = schemaBounds('PumpControl', 'setpoint') as { maximum: number };
		expect(draftProblem(pump(), { setpoint: 0, minSpeed: 0.4 })).toBe('invalid');
		expect(draftProblem(pump(), { setpoint: maximum, minSpeed: 0.4 })).toBeNull();
		expect(draftProblem(pump(), { setpoint: maximum * 1.001, minSpeed: 0.4 })).toBe('invalid');
		expect(draftProblem(pump(), { setpoint: 0.01, minSpeed: 0 })).toBe('invalid');
	});
});

describe('control bounds', () => {
	it("are the schema's, the minimum speed below the speed", () => {
		expect(controlFieldBounds(pump(), 'setpoint')).toEqual(schemaBounds('PumpControl', 'setpoint'));
		expect(controlFieldBounds(pump(), 'minSpeed')).toEqual(schemaBounds('PumpControl', 'minSpeed'));
		expect(controlFieldBounds(pump(0.8), 'minSpeed')).toEqual({
			exclusiveMinimum: 0,
			exclusiveMaximum: 0.8
		});
	});

	it('bound the speed above the minimum speed only for a controlled pump or a draft', () => {
		expect(speedBounds(pump())).toEqual(schemaBounds('Pump', 'speed'));
		expect(speedBounds(pump(), EMPTY_CONTROL_DRAFT)).toEqual(schemaBounds('Pump', 'speed'));
		expect(speedBounds(pump(), { setpoint: null, minSpeed: 0.4 })).toEqual({
			exclusiveMinimum: 0.4,
			maximum: 1
		});
		const controlled: Pump = {
			...pump(0.9),
			control: { mode: 'flow', setpoint: 0.01, minSpeed: 0.5 }
		};
		expect(speedBounds(controlled)).toEqual({ exclusiveMinimum: 0.5, maximum: 1 });
		// A stored control wins over a draft (there is none once it is stored).
		expect(speedBounds(controlled, { setpoint: null, minSpeed: 0.3 })).toEqual({
			exclusiveMinimum: 0.5,
			maximum: 1
		});
		expect(controlFieldBounds(controlled, 'minSpeed')).toEqual({
			exclusiveMinimum: 0,
			exclusiveMaximum: 0.9
		});
	});
});
