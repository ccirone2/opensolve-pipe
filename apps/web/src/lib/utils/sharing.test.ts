import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { deepFreeze } from '../state/project.svelte';
import { reversePiping } from './edit';
import { condenserWaterExample, EXAMPLES } from './examples';
import { markCopy, markProjectCopy, originOf } from './identity';
import { canonicalJson } from './json';
import { copyData, equalData, shareUnchanged } from './sharing';

/** A stored project (deep-frozen) and an edit's draft of it, as update() makes them. */
function draftOf(project: Project = condenserWaterExample()) {
	const stored = deepFreeze(copyData(project));
	const draft = copyData(stored);
	markProjectCopy(draft, stored);
	return { stored, draft };
}

describe('copyData', () => {
	it('copies plain data as structuredClone does: same keys in the same order, same values', () => {
		for (const example of EXAMPLES) {
			const project = deepFreeze(example.create());
			const copy = copyData(project);
			expect(copy).toStrictEqual(structuredClone(project));
			expect(JSON.stringify(copy)).toBe(JSON.stringify(project));
			expect(Object.isFrozen(copy)).toBe(false);
			expect(Object.isFrozen(copy.components[0])).toBe(false);
			expect(copy.components[0]).not.toBe(project.components[0]);
		}
		const odd = { '2': 'b', a: -0, '1': undefined, u: [null, 1.5, 'x'] };
		expect(Object.keys(copyData(odd))).toEqual(Object.keys(structuredClone(odd)));
		expect(Object.is(copyData(odd).a, -0)).toBe(true);
		expect('1' in copyData(odd)).toBe(true);
	});

	it('gives each place its own copy, as JSON does', () => {
		const shared = { length: 1 };
		const copy = copyData({ a: shared, b: shared });
		expect(copy.a).toEqual(copy.b);
		expect(copy.a).not.toBe(copy.b);
	});

	it('leaves what is not plain data to structuredClone', () => {
		const date = new Date(0);
		expect(copyData({ date }).date).toBeInstanceOf(Date);
		expect(() => copyData({ f: () => 1 })).toThrow();
		const proto = JSON.parse('{"__proto__": {"x": 1}}') as object;
		expect(Object.keys(copyData(proto))).toEqual(['__proto__']);
	});
});

describe('equalData', () => {
	it('needs the same keys in the same order and equal values', () => {
		expect(equalData({ a: 1, b: [1, { c: 2 }] }, { a: 1, b: [1, { c: 2 }] })).toBe(true);
		expect(equalData({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(false);
		expect(equalData({ a: 0 }, { a: -0 })).toBe(false);
		expect(equalData({ a: undefined }, {})).toBe(false);
		expect(equalData([1, 2], [1, 2, 3])).toBe(false);
	});

	it('takes a pipe as equal only when it is the same pipe', () => {
		const pipe = { length: 1 };
		const copy = { length: 1 };
		const other = { length: 1 };
		markCopy(copy, pipe);
		expect(equalData({ pipes: [copy] }, { pipes: [pipe] })).toBe(true);
		expect(equalData({ pipes: [other] }, { pipes: [pipe] })).toBe(false);
	});
});

describe('shareUnchanged', () => {
	it('gives back the stored project when the edit changed nothing', () => {
		const { stored, draft } = draftOf();
		expect(shareUnchanged(draft, stored)).toBe(stored);
	});

	it('keeps the stored elements the edit did not change, and the edit’s changed ones', () => {
		const { stored, draft } = draftOf();
		draft.components[3]!.name = 'Renamed';
		draft.connections[2]!.piping.pipes[0]!.length += 1;
		const next = shareUnchanged(draft, stored);
		expect(next).toBe(draft);
		next.components.forEach((c, i) =>
			i === 3 ? expect(c).not.toBe(stored.components[i]) : expect(c).toBe(stored.components[i])
		);
		next.connections.forEach((c, i) =>
			i === 2 ? expect(c).not.toBe(stored.connections[i]) : expect(c).toBe(stored.connections[i])
		);
		expect(next.settings).toBe(stored.settings);
		expect(next.fluid).toBe(stored.fluid);
		expect(next.components[3]!.name).toBe('Renamed');
	});

	it('finds elements by id, after an insertion moved them', () => {
		const { stored, draft } = draftOf();
		const added = { ...structuredClone(stored.components[0]!), id: 'NEW', name: 'New' };
		draft.components.splice(1, 0, added as Project['components'][number]);
		const next = shareUnchanged(draft, stored);
		expect(next.components[1]).toBe(added);
		expect(next.components.filter((c) => stored.components.includes(c))).toHaveLength(
			stored.components.length
		);
	});

	it('never puts a stored pipe in the place of another pipe equal to it', () => {
		const { stored, draft } = draftOf();
		const index = stored.connections.findIndex((c) => c.piping.pipes.length === 1);
		const connection = draft.connections[index]!;
		// A new pipe, equal to the stored one but another pipe (identity.ts): never marked as a copy.
		connection.piping.pipes = [{ ...connection.piping.pipes[0]! }];
		const next = shareUnchanged(draft, stored);
		expect(next.connections[index]).not.toBe(stored.connections[index]);
		expect(originOf(next.connections[index]!.piping.pipes[0]!)).not.toBe(
			originOf(stored.connections[index]!.piping.pipes[0]!)
		);
	});

	it('keeps pipe identity through a reversal of a connection’s piping', () => {
		const { stored, draft } = draftOf();
		const index = stored.connections.findIndex((c) => c.piping.pipes.length > 1);
		if (index < 0) return expect.unreachable('the example has a connection of several pipes');
		const connection = draft.connections[index]!;
		connection.piping = reversePiping(connection.piping);
		const next = shareUnchanged(draft, stored);
		expect(next.connections[index]).toBe(connection);
		expect(next.connections[index]!.piping.pipes.map(originOf)).toEqual(
			[...stored.connections[index]!.piping.pipes].reverse().map(originOf)
		);
	});

	it('puts nothing back when the edit holds a frozen object of its own', () => {
		const { stored, draft } = draftOf();
		// A stored component taken from the page into a new element: putting the stored ports back
		// in its own place too would make one object appear twice.
		draft.components.push({
			...stored.components[0]!,
			id: 'COPY',
			ports: stored.components[0]!.ports
		} as Project['components'][number]);
		const next = shareUnchanged(draft, stored);
		expect(next.components.some((c, i) => c === stored.components[i])).toBe(false);
	});

	it('never changes the edit’s canonical JSON', () => {
		for (const example of EXAMPLES) {
			const { stored, draft } = draftOf(example.create());
			draft.metadata.name = 'Changed';
			const text = canonicalJson(draft);
			expect(canonicalJson(shareUnchanged(draft, stored))).toBe(text);
		}
	});
});
