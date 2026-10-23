import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import { createEmptyProject } from './factory';
import { LinkError } from './link-error';
import { CURRENT_SCHEMA_VERSION, migrate, MIGRATIONS, type Migration } from './migrations';

function thrown(fn: () => unknown): unknown {
	try {
		fn();
	} catch (error) {
		return error;
	}
	throw new Error('did not throw');
}

describe('schema version', () => {
	it('matches the API Project schema', () => {
		expect(openapi.components.schemas.Project.properties.schemaVersion.const).toBe(
			CURRENT_SCHEMA_VERSION
		);
		expect(createEmptyProject().schemaVersion).toBe(CURRENT_SCHEMA_VERSION);
	});

	it('has one migration for every version below the current one, and none above', () => {
		const versions = Object.keys(MIGRATIONS).map(Number);
		const expected = Array.from({ length: CURRENT_SCHEMA_VERSION - 1 }, (_, i) => i + 1);
		expect(versions.sort((a, b) => a - b)).toEqual(expected);
		expect(Object.isFrozen(MIGRATIONS)).toBe(true);
	});
});

describe('migrate', () => {
	it('leaves a current-version project unchanged', () => {
		const project = createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' });
		expect(migrate(structuredClone(project))).toEqual(project);
	});

	it('rejects values that are not projects', () => {
		for (const value of [
			null,
			undefined,
			3,
			'project',
			[],
			{},
			{ schemaVersion: null },
			{ schemaVersion: '1' },
			{ schemaVersion: 0 },
			{ schemaVersion: -2 },
			{ schemaVersion: 1.5 },
			{ schemaVersion: Number.NaN }
		]) {
			const error = thrown(() => migrate(value));
			expect(error).toBeInstanceOf(LinkError);
			expect((error as LinkError).kind).toBe('invalid');
			expect((error as LinkError).message).toMatch(/does not contain an OpenSolve Pipe project/);
		}
	});

	it('rejects projects from a newer version with a clear message', () => {
		const error = thrown(() => migrate({ schemaVersion: CURRENT_SCHEMA_VERSION + 1 }));
		expect(error).toBeInstanceOf(LinkError);
		expect((error as LinkError).kind).toBe('newer_version');
		expect((error as LinkError).message).toMatch(
			/This link was made with a newer version of OpenSolve Pipe/
		);
		expect((error as LinkError).message).toContain(`format ${CURRENT_SCHEMA_VERSION + 1}`);
	});

	describe('with a migration table', () => {
		const calls: number[] = [];
		const table: Record<number, Migration> = {
			// v1 → v2: add a field
			1: (p) => {
				calls.push(1);
				return { ...p, added: 'in v2' };
			},
			// v2 → v3: rename it (needs the v2 field, so order matters)
			2: (p) => {
				calls.push(2);
				const { added, ...rest } = p;
				return { ...rest, renamed: `${String(added)} → v3` };
			}
		};

		it('applies every step in order and sets schemaVersion after each', () => {
			calls.length = 0;
			expect(migrate({ schemaVersion: 1, keep: true }, table, 3)).toEqual({
				schemaVersion: 3,
				keep: true,
				renamed: 'in v2 → v3'
			});
			expect(calls).toEqual([1, 2]);
		});

		it('starts from the version the project has', () => {
			calls.length = 0;
			expect(migrate({ schemaVersion: 2, added: 'x' }, table, 3)).toEqual({
				schemaVersion: 3,
				renamed: 'x → v3'
			});
			expect(calls).toEqual([2]);
		});

		it('sets schemaVersion even when a step forgets to', () => {
			expect(migrate({ schemaVersion: 1 }, { 1: (p) => ({ ...p, schemaVersion: 1 }) }, 2)).toEqual({
				schemaVersion: 2
			});
		});

		it('treats a missing step as a bug, not as a bad link', () => {
			const error = thrown(() => migrate({ schemaVersion: 1 }, { 2: (p) => p }, 3));
			expect(error).toBeInstanceOf(Error);
			expect(error).not.toBeInstanceOf(LinkError);
			expect((error as Error).message).toMatch(/No migration from project schema version 1/);
		});

		it('rejects versions newer than the table supports', () => {
			const error = thrown(() => migrate({ schemaVersion: 4 }, table, 3));
			expect((error as LinkError).kind).toBe('newer_version');
		});
	});
});
