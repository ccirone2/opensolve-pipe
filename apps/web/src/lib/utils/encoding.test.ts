import { gzip } from 'pako';
import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { link, projectWith, reverseKeys } from '../testing/helpers';
import {
	canonicalJson,
	decodeProject,
	encodeProject,
	fragmentOf,
	fromBase64Url,
	projectPath,
	projectUrl,
	toBase64Url,
	URL_LENGTH_WARNING
} from './encoding';
import { EXAMPLES } from './examples';
import { createComponent, createEmptyProject } from './factory';
import { LinkError } from './link-error';
import fixtureJson from './__fixtures__/schema-v1.json';

const fixture = fixtureJson as unknown as Project;

/** Encode any JSON value the way encodeProject does, without type or validity checks. */
function encodeRaw(value: unknown): string {
	return toBase64Url(gzip(new TextEncoder().encode(JSON.stringify(value)), { level: 9 }));
}

function encodeBytes(bytes: Uint8Array): string {
	return toBase64Url(gzip(bytes, { level: 9 }));
}

function decodeError(encoded: string): LinkError {
	try {
		decodeProject(encoded);
	} catch (error) {
		if (error instanceof LinkError) return error;
		throw error;
	}
	throw new Error('decodeProject did not throw');
}

describe('canonicalJson', () => {
	it('sorts keys at every level and keeps array order', () => {
		expect(canonicalJson({ b: 1, a: { d: [3, { z: 1, y: 2 }], c: 3 } })).toBe(
			'{"a":{"c":3,"d":[3,{"y":2,"z":1}]},"b":1}'
		);
	});

	it('encodes independently of key order', () => {
		expect(canonicalJson({ b: 1, a: { d: 2, c: 3 } })).toBe(
			canonicalJson({ a: { c: 3, d: 2 }, b: 1 })
		);
		for (const example of EXAMPLES) {
			const project = example.create();
			const shuffled = reverseKeys(project) as Project;
			expect(JSON.stringify(shuffled)).not.toBe(JSON.stringify(project));
			expect(canonicalJson(shuffled)).toBe(canonicalJson(project));
			expect(encodeProject(shuffled)).toBe(encodeProject(project));
		}
	});

	it('keeps nested fields (an array replacer would drop them, TSD §4.7)', () => {
		expect(JSON.parse(canonicalJson({ metadata: { name: 'Test' } }))).toEqual({
			metadata: { name: 'Test' }
		});
	});

	it('rejects non-finite numbers instead of writing null', () => {
		expect(() => canonicalJson({ a: { b: Number.NaN } })).toThrow(/non-finite/);
		expect(() => canonicalJson([Infinity])).toThrow(/non-finite/);
		expect(() => canonicalJson({ a: -Infinity })).toThrow(/non-finite/);
	});
});

describe('base64url', () => {
	it('matches Node base64url for every length 0–299 and round-trips', () => {
		for (let n = 0; n < 300; n++) {
			const bytes = Uint8Array.from({ length: n }, (_, i) => (i * 37 + n * 11) % 256);
			const encoded = toBase64Url(bytes);
			expect(encoded).toBe(Buffer.from(bytes).toString('base64url'));
			expect(encoded).toMatch(/^[A-Za-z0-9_-]*$/);
			expect(fromBase64Url(encoded)).toEqual(bytes);
		}
	});

	it('rejects text that is not base64url', () => {
		expect(() => fromBase64Url('abc=')).toThrow();
		expect(() => fromBase64Url('a+b/')).toThrow();
		expect(() => fromBase64Url('abcde')).toThrow(); // length 1 mod 4 is impossible
	});
});

describe('encodeProject / decodeProject', () => {
	it('round-trips a project, including nested fields', () => {
		const project = createEmptyProject();
		project.metadata.name = 'Test Project';
		project.metadata.description = 'Nested ✓ — unicode survives';
		project.settings.units.pressure = 'psi';
		project.settings.solverOptions.frictionMethod = 'swamee_jain';
		project.fluid = {
			kind: 'builtin',
			fluidId: 'propylene_glycol',
			temperature: 280,
			concentration: 0.3
		};
		const decoded = decodeProject(encodeProject(project));
		expect(decoded).toEqual(project);
		expect(decoded.metadata.name).toBe('Test Project');
		expect(decoded.settings.units.pressure).toBe('psi');
	});

	it('round-trips every example and the schema-v1 fixture', () => {
		for (const example of EXAMPLES) {
			const project = example.create();
			expect(decodeProject(encodeProject(project))).toEqual(project);
		}
		expect(decodeProject(encodeProject(fixture))).toEqual(fixture);
	});

	it('produces URL-safe strings', () => {
		for (const project of [createEmptyProject(), ...EXAMPLES.map((e) => e.create())]) {
			const encoded = encodeProject(project);
			expect(encoded).toMatch(/^[A-Za-z0-9_-]+$/);
			expect(encodeURIComponent(encoded)).toBe(encoded);
		}
	});

	it('is deterministic', () => {
		const project = EXAMPLES[0]!.create();
		expect(encodeProject(project)).toBe(encodeProject(structuredClone(project)));
	});

	it('accepts a leading # and surrounding whitespace', () => {
		const project = EXAMPLES[1]!.create();
		expect(decodeProject(`  #${encodeProject(project)}\n`)).toEqual(project);
	});

	it('fills fields the schema gives defaults for', () => {
		const project = EXAMPLES[0]!.create() as unknown as Record<string, unknown> & Project;
		const raw = structuredClone(project) as unknown as {
			methodVersion?: string;
			components: { ports: { direction?: string }[]; surfacePressure?: number }[];
			connections: { piping: { fittings: { quantity?: number; pipeIndex?: number }[] } }[];
		};
		delete raw.methodVersion;
		delete raw.components[0]!.ports[0]!.direction;
		delete raw.components[0]!.surfacePressure;
		delete raw.connections[0]!.piping.fittings[0]!.quantity;
		delete raw.connections[0]!.piping.fittings[0]!.pipeIndex;
		expect(decodeProject(encodeRaw(raw))).toEqual(project);
	});

	it('rejects links from a newer schema version', () => {
		const future = { ...createEmptyProject(), schemaVersion: 999 };
		const error = decodeError(encodeRaw(future));
		expect(error.kind).toBe('newer_version');
		expect(error.message).toMatch(/newer version/);
		expect(() => decodeProject(encodeRaw(future))).toThrow(/newer version of OpenSolve Pipe/);
	});

	it('reports corrupt links', () => {
		const good = encodeProject(EXAMPLES[0]!.create());
		const corrupt = [
			'',
			'#',
			'   ',
			'not base64!',
			'abc=',
			good.slice(0, Math.floor(good.length / 2)), // cut short by a chat client
			good.slice(0, -3),
			`${good.slice(0, 40)}${good[40] === 'A' ? 'B' : 'A'}${good.slice(41)}`, // damaged
			toBase64Url(new TextEncoder().encode('{"schemaVersion":1}')), // not gzip
			encodeBytes(new TextEncoder().encode('{"schemaVersion": 1')), // not JSON
			encodeBytes(Uint8Array.from([0xff, 0xfe, 0x7b, 0x7d])) // not UTF-8
		];
		for (const text of corrupt) {
			const error = decodeError(text);
			expect(error.kind, text).toBe('corrupt');
			expect(error.message).toMatch(/incomplete or damaged/);
		}
	});

	it('reports links that hold something other than a project', () => {
		for (const value of [
			null,
			42,
			'text',
			[],
			{},
			{ schemaVersion: '1' },
			{ schemaVersion: 0 },
			{ schemaVersion: 1.5 },
			{ schemaVersion: -1 }
		]) {
			const error = decodeError(encodeRaw(value));
			expect(error.kind).toBe('invalid');
			expect(error.message).toMatch(/does not contain an OpenSolve Pipe project/);
		}
	});

	it('reports invalid projects with the problems found', () => {
		const project = EXAMPLES[0]!.create() as Project;
		const bad = structuredClone(project);
		(bad.components[0] as { liquidLevel: number }).liquidLevel = -1;
		const error = decodeError(encodeRaw(bad));
		expect(error.kind).toBe('invalid');
		expect(error.problems).toEqual(['components[0] "R1" › liquidLevel: must be >= 0']);

		const dangling = structuredClone(project);
		dangling.connections[0]!.toComponentId = 'nowhere';
		const danglingError = decodeError(encodeRaw(dangling));
		expect(danglingError.kind).toBe('invalid');
		expect(danglingError.problems.join(' ')).toMatch(/"nowhere", which does not exist/);
	});

	it('opens projects that only break solver-level rules (the solver reports those)', () => {
		const reservoir = createComponent('reservoir', createEmptyProject());
		const pump = createComponent('pump', projectWith([reservoir])); // curve not defined yet
		const project = projectWith(
			[reservoir, pump],
			[link('L1', ['R1', 'port_1'], ['P1', 'suction'])]
		);
		expect(decodeProject(encodeProject(project))).toEqual(project);
	});
});

describe('links', () => {
	it('builds the app path and the shareable URL', () => {
		const project = EXAMPLES[2]!.create();
		const encoded = encodeProject(project);
		expect(projectPath(project)).toBe(`/p#${encoded}`);
		expect(projectUrl(project)).toBe(`https://opensolve-pipe.app/p#${encoded}`);
		expect(projectUrl(project, 'http://localhost:4173/')).toBe(
			`http://localhost:4173/p#${encoded}`
		);
	});

	it('extracts the fragment from a full link', () => {
		const project = EXAMPLES[0]!.create();
		const url = projectUrl(project);
		expect(fragmentOf(url)).toBe(encodeProject(project));
		expect(fragmentOf(`#${encodeProject(project)}`)).toBe(encodeProject(project));
		expect(fragmentOf(encodeProject(project))).toBe(encodeProject(project));
		expect(decodeProject(fragmentOf(url))).toEqual(project);
	});

	it('warns above 8,000 characters (D3)', () => {
		expect(URL_LENGTH_WARNING).toBe(8000);
	});
});
