import { describe, expect, it } from 'vitest';
import type { Fitting, PipeMaterial, PipingSegment } from '../api/types';
import { deepFreeze } from '../testing/helpers';
import {
	addFitting,
	addPipe,
	maxPipeIndex,
	nearestSize,
	newFitting,
	removeFitting,
	removePipe,
	resolvedPipe,
	updateFitting,
	updatePipe,
	withMaterial,
	withOptional,
	withSchedule
} from './piping';
import { INCH } from './units';

const pipe = (length: number, nominalSize = 4 * INCH) => ({
	materialId: 'carbon_steel',
	schedule: '40',
	nominalSize,
	length
});

const fitting = (type: Fitting['type'], pipeIndex: number): Fitting => ({
	type,
	pipeIndex,
	quantity: 1
});

function piping(): PipingSegment {
	return deepFreeze({
		pipes: [pipe(10), pipe(20), pipe(30)],
		fittings: [
			fitting('elbow_90_lr', 0),
			fitting('reducer_sudden', 0),
			fitting('gate_valve', 1),
			fitting('reducer_conical', 1),
			fitting('exit', 2)
		]
	});
}

/** A material for the tests: sizes are test inputs, not library data. */
const material: PipeMaterial = deepFreeze({
	id: 'test_steel',
	name: 'Test steel',
	roughness: 4.5e-5,
	roughnessSource: 'test',
	dimensionsSource: 'test',
	notes: '',
	schedules: [
		{
			id: '40',
			sizes: [
				{
					nps: '2',
					nominalSize: 2 * INCH,
					innerDiameter: 0.05,
					outerDiameter: 0.06,
					wallThickness: 0.004,
					roughness: 1e-5
				},
				{
					nps: '4',
					nominalSize: 4 * INCH,
					innerDiameter: 0.1,
					outerDiameter: 0.11,
					wallThickness: 0.006,
					roughness: 1e-5
				}
			]
		},
		{
			id: '80',
			sizes: [
				{
					nps: '3',
					nominalSize: 3 * INCH,
					innerDiameter: 0.07,
					outerDiameter: 0.09,
					wallThickness: 0.008,
					roughness: 1e-5
				}
			]
		}
	]
});

describe('pipe segments', () => {
	it('appends a copy of the last pipe with the default length', () => {
		const next = addPipe(piping());
		expect(next.pipes).toHaveLength(4);
		expect(next.pipes[3]).toEqual({ ...pipe(30), length: 10 });
	});

	it('removes a pipe and keeps fittings on the pipes they were on', () => {
		const next = removePipe(piping(), 1);
		expect(next.pipes.map((p) => p.length)).toEqual([10, 30]);
		expect(next.fittings.map((f) => [f.type, f.pipeIndex])).toEqual([
			['elbow_90_lr', 0],
			['reducer_sudden', 0], // between pipes 0 and 1 (was 0 and 1; 1 was removed)
			['gate_valve', 0], // was on the removed pipe: moves to the one before
			['reducer_conical', 0], // was between 1 and 2: now between 0 and 1
			['exit', 1]
		]);
	});

	it('moves fittings on a removed first pipe to the new first pipe', () => {
		const next = removePipe(piping(), 0);
		expect(next.fittings.map((f) => f.pipeIndex)).toEqual([0, 0, 0, 0, 1]);
	});

	it('keeps at least one pipe', () => {
		const one = { pipes: [pipe(5)], fittings: [] };
		expect(removePipe(one, 0)).toBe(one);
		expect(removePipe(piping(), 7)).toEqual(piping());
	});

	it('updates one pipe', () => {
		const next = updatePipe(piping(), 2, (p) => ({ ...p, length: 99 }));
		expect(next.pipes.map((p) => p.length)).toEqual([10, 20, 99]);
	});
});

describe('fittings', () => {
	it('adds, updates and removes fittings', () => {
		const added = addFitting(piping(), fitting('custom', 2));
		expect(added.fittings).toHaveLength(6);
		const updated = updateFitting(added, 5, (f) => ({ ...f, kOverride: 2.5 }));
		expect(updated.fittings[5]).toMatchObject({ type: 'custom', kOverride: 2.5 });
		expect(removeFitting(updated, 0).fittings.map((f) => f.type)).toEqual([
			'reducer_sudden',
			'gate_valve',
			'reducer_conical',
			'exit',
			'custom'
		]);
	});

	it('limits a reducer to sitting between two pipes', () => {
		expect(maxPipeIndex({ type: 'reducer_sudden' }, 3)).toBe(1);
		expect(maxPipeIndex({ type: 'elbow_90_lr' }, 3)).toBe(2);
		expect(maxPipeIndex({ type: 'reducer_conical' }, 1)).toBe(0);
	});

	it('creates a fitting with no guessed parameters', () => {
		expect(newFitting('bend', 5, 2)).toEqual({ type: 'bend', quantity: 1, pipeIndex: 1 });
		expect(newFitting('reducer_conical', 5, 3)).toEqual({
			type: 'reducer_conical',
			quantity: 1,
			pipeIndex: 1
		});
	});
});

describe('materials and schedules', () => {
	it('keeps the schedule and size when the new material has them, dropping overrides', () => {
		const next = withMaterial({ ...pipe(12), roughness: 1e-4, innerDiameter: 0.09 }, material);
		expect(next).toEqual({
			materialId: 'test_steel',
			schedule: '40',
			nominalSize: 4 * INCH,
			length: 12
		});
	});

	it('takes the first schedule and the nearest size when the material lacks them', () => {
		const next = withMaterial({ ...pipe(12, 3.5 * INCH), schedule: '10S' }, material);
		expect(next).toMatchObject({ schedule: '40', nominalSize: 4 * INCH });
		expect(nearestSize(material.schedules[0]!.sizes, 2.4 * INCH)?.nps).toBe('2');
	});

	it('to custom: keeps the bore and roughness the pipe resolved to', () => {
		expect(withMaterial(pipe(7), 'custom', { innerDiameter: 0.1023, roughness: 4.5e-5 })).toEqual({
			materialId: 'custom',
			length: 7,
			innerDiameter: 0.1023,
			roughness: 4.5e-5
		});
		// Nothing known: left empty for the user, never guessed.
		expect(withMaterial(pipe(7), 'custom')).toEqual({ materialId: 'custom', length: 7 });
	});

	it('from custom: picks the size nearest the custom bore', () => {
		const custom = { materialId: 'custom', length: 3, innerDiameter: 0.052, roughness: 1e-5 };
		expect(withMaterial(custom, material)).toEqual({
			materialId: 'test_steel',
			schedule: '40',
			nominalSize: 2 * INCH,
			length: 3
		});
	});

	it('changes schedule, keeping the size when it exists', () => {
		const schedule80 = material.schedules[1]!;
		expect(withSchedule(pipe(1, 3 * INCH), schedule80)).toMatchObject({
			schedule: '80',
			nominalSize: 3 * INCH
		});
		expect(withSchedule(pipe(1, 4 * INCH), schedule80).nominalSize).toBe(3 * INCH);
	});
});

describe('withOptional', () => {
	it('sets a value or removes the key', () => {
		const value = deepFreeze({ a: 1, b: 2 as number | undefined });
		expect(withOptional(value, 'b', 5)).toEqual({ a: 1, b: 5 });
		expect(withOptional(value, 'b', null)).toEqual({ a: 1 });
		expect('b' in withOptional(value, 'b', undefined)).toBe(false);
	});
});

describe('resolvedPipe', () => {
	const size = material.schedules[0]!.sizes[1]!;

	it('takes the bore and the per-size roughness from the size entry', () => {
		expect(resolvedPipe(pipe(5, 4 * INCH), size)).toEqual({ innerDiameter: 0.1, roughness: 1e-5 });
	});

	it('prefers overrides', () => {
		expect(resolvedPipe({ ...pipe(5, 4 * INCH), roughness: 2e-5 }, size)).toEqual({
			innerDiameter: 0.1,
			roughness: 2e-5
		});
	});

	it('leaves the roughness unknown for a bore override (the server evaluates it there)', () => {
		expect(resolvedPipe({ ...pipe(5, 4 * INCH), innerDiameter: 0.09 }, size)).toEqual({
			innerDiameter: 0.09
		});
		expect(resolvedPipe(pipe(5, 4 * INCH), undefined)).toEqual({});
	});
});
