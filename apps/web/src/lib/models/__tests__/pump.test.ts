/**
 * Tests for pump model functions.
 */

import { describe, it, expect } from 'vitest';
import {
	validatePumpCurve,
	createDefaultPumpCurve,
	interpolatePumpHead,
	interpolateEfficiency,
	calculateBEP
} from '../pump';
import type { PumpCurve } from '../pump';

describe('validatePumpCurve', () => {
	it('should reject curves with less than 2 points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [{ flow: 0, head: 100 }]
		};
		expect(validatePumpCurve(curve)).toBe('Pump curve must have at least 2 points');
	});

	it('should reject unsorted points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 100, head: 50 },
				{ flow: 50, head: 75 }
			]
		};
		expect(validatePumpCurve(curve)).toBe('Pump curve points must be sorted by ascending flow');
	});

	it('should reject negative flow values', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: -10, head: 100 },
				{ flow: 50, head: 75 }
			]
		};
		expect(validatePumpCurve(curve)).toBe('Flow values cannot be negative');
	});

	it('should reject invalid efficiency values', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 50, head: 75 }
			],
			efficiency_curve: [{ flow: 25, efficiency: 1.5 }]
		};
		expect(validatePumpCurve(curve)).toBe('Efficiency values must be between 0 and 1');
	});

	it('should accept valid curves', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 50, head: 75 },
				{ flow: 100, head: 50 }
			]
		};
		expect(validatePumpCurve(curve)).toBeNull();
	});
});

describe('createDefaultPumpCurve', () => {
	it('should create a valid curve with 5 points', () => {
		const curve = createDefaultPumpCurve('test-id');
		expect(curve.id).toBe('test-id');
		expect(curve.points.length).toBe(5);
		expect(validatePumpCurve(curve)).toBeNull();
	});
});

describe('interpolatePumpHead', () => {
	const curve: PumpCurve = {
		id: 'test',
		name: 'Test',
		points: [
			{ flow: 0, head: 100 },
			{ flow: 100, head: 80 },
			{ flow: 200, head: 50 }
		]
	};

	it('should return null for curves with less than 2 points', () => {
		const smallCurve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [{ flow: 0, head: 100 }]
		};
		expect(interpolatePumpHead(smallCurve, 50)).toBeNull();
	});

	it('should return first point head for flow below range', () => {
		expect(interpolatePumpHead(curve, -10)).toBe(100);
	});

	it('should return last point head for flow above range', () => {
		expect(interpolatePumpHead(curve, 300)).toBe(50);
	});

	it('should interpolate head at midpoint', () => {
		expect(interpolatePumpHead(curve, 50)).toBe(90);
	});

	it('should interpolate head between second and third points', () => {
		expect(interpolatePumpHead(curve, 150)).toBe(65);
	});
});

describe('interpolateEfficiency', () => {
	const curveWithEfficiency: PumpCurve = {
		id: 'test',
		name: 'Test',
		points: [
			{ flow: 0, head: 100 },
			{ flow: 100, head: 80 },
			{ flow: 200, head: 50 }
		],
		efficiency_curve: [
			{ flow: 0, efficiency: 0 },
			{ flow: 100, efficiency: 0.8 },
			{ flow: 200, efficiency: 0.6 }
		]
	};

	it('should return null for curves without efficiency data', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			]
		};
		expect(interpolateEfficiency(curve, 50)).toBeNull();
	});

	it('should return null for efficiency curves with less than 2 points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			],
			efficiency_curve: [{ flow: 50, efficiency: 0.7 }]
		};
		expect(interpolateEfficiency(curve, 50)).toBeNull();
	});

	it('should return first point efficiency for flow below range', () => {
		expect(interpolateEfficiency(curveWithEfficiency, -10)).toBe(0);
	});

	it('should return last point efficiency for flow above range', () => {
		expect(interpolateEfficiency(curveWithEfficiency, 300)).toBe(0.6);
	});

	it('should interpolate efficiency at midpoint', () => {
		expect(interpolateEfficiency(curveWithEfficiency, 50)).toBe(0.4);
	});

	it('should interpolate efficiency between second and third points', () => {
		expect(interpolateEfficiency(curveWithEfficiency, 150)).toBe(0.7);
	});
});

describe('calculateBEP', () => {
	it('should return null for curves without efficiency data', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			]
		};
		expect(calculateBEP(curve)).toBeNull();
	});

	it('should find BEP at maximum efficiency point', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 50, head: 90 },
				{ flow: 100, head: 80 },
				{ flow: 150, head: 65 },
				{ flow: 200, head: 50 }
			],
			efficiency_curve: [
				{ flow: 0, efficiency: 0 },
				{ flow: 50, efficiency: 0.6 },
				{ flow: 100, efficiency: 0.8 },
				{ flow: 150, efficiency: 0.75 },
				{ flow: 200, efficiency: 0.6 }
			]
		};

		const bep = calculateBEP(curve);
		expect(bep).not.toBeNull();
		expect(bep!.flow).toBe(100);
		expect(bep!.efficiency).toBe(0.8);
		expect(bep!.head).toBe(80);
	});
});
