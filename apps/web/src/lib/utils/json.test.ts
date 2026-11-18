import { describe, expect, it } from 'vitest';
import { deepFreeze } from '../state/project.svelte';
import { EXAMPLES } from './examples';
import {
	canonicalJson,
	canonicalJsonByReplacer,
	canonicalJsonEqual,
	canonicalJsonWithout
} from './json';

/** A deterministic random number generator (mulberry32). */
function rng(seed: number) {
	let a = seed >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = a;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

const KEYS = ['id', 'name', 'b', 'a', '10', '2', '0', 'Z', 'é', '😀', '__x', 'length', 'toString'];
const STRINGS = ['', 'x', 'quote "', 'back\\slash', 'line\nbreak', 'é', '😀', ' ', '\ud800'];

/** Random JSON-like data: objects with array-index keys too, unicode, -0, undefined values. */
function randomValue(random: () => number, depth = 0): unknown {
	const r = random();
	if (depth > 3 || r < 0.35) {
		const leaves = [
			null,
			true,
			false,
			0,
			-0,
			1e21,
			-1.5e-7,
			Math.round(random() * 1000) / 7,
			undefined,
			STRINGS[Math.floor(random() * STRINGS.length)]
		];
		return leaves[Math.floor(random() * leaves.length)];
	}
	if (r < 0.6) {
		return Array.from({ length: Math.floor(random() * 4) }, () => randomValue(random, depth + 1));
	}
	const record: Record<string, unknown> = {};
	const n = Math.floor(random() * 5);
	for (let i = 0; i < n; i++) {
		record[KEYS[Math.floor(random() * KEYS.length)] as string] = randomValue(random, depth + 1);
	}
	return record;
}

/** A copy of `value` with one random change somewhere (or none). */
function changed(value: unknown, random: () => number): unknown {
	const copy = structuredClone(value);
	const at = (node: unknown): void => {
		if (typeof node !== 'object' || node === null) return;
		const keys = Object.keys(node);
		if (!keys.length) return;
		const key = keys[Math.floor(random() * keys.length)] as string;
		const record = node as Record<string, unknown>;
		const child = record[key];
		if (typeof child === 'object' && child !== null && random() < 0.6) at(child);
		else if (random() < 0.2) delete record[key];
		else record[key] = randomValue(random, 3);
	};
	if (random() < 0.8) at(copy);
	return copy;
}

describe('canonicalJson', () => {
	it('writes what JSON.stringify writes with the sorting replacer, frozen or not', () => {
		const random = rng(1);
		for (let i = 0; i < 2000; i++) {
			const value = randomValue(random);
			expect(canonicalJson(value)).toBe(canonicalJsonByReplacer(value));
			const frozen = deepFreeze(structuredClone(value));
			expect(canonicalJson(frozen)).toBe(canonicalJsonByReplacer(value));
			// Twice: the second time from the texts kept for the frozen parts.
			expect(canonicalJson(frozen)).toBe(canonicalJsonByReplacer(value));
		}
	});

	it('writes every example project as the replacer does, and again after an edit', () => {
		for (const example of EXAMPLES) {
			const project = deepFreeze(example.create());
			expect(canonicalJson(project)).toBe(canonicalJsonByReplacer(project));
			const edited = {
				...project,
				components: project.components.map((c, i) => (i === 0 ? { ...c, name: 'Edited' } : c))
			};
			expect(canonicalJson(edited)).toBe(canonicalJsonByReplacer(edited));
		}
	});

	it('orders array-index keys first, in numeric order, as JSON.stringify of the sorted copy', () => {
		const value = { b: 1, '10': 2, '2': 3, a: 4, '01': 5, '4294967295': 6 };
		expect(canonicalJson(value)).toBe(canonicalJsonByReplacer(value));
		expect(canonicalJson(value)).toBe('{"2":3,"10":2,"01":5,"4294967295":6,"a":4,"b":1}');
	});

	it('leaves toJSON, instances of classes and cycles to JSON.stringify', () => {
		const date = new Date(0);
		expect(canonicalJson({ when: date })).toBe(canonicalJsonByReplacer({ when: date }));
		expect(canonicalJson(new Map([[1, 2]]))).toBe('{}');
		// A cycle: the replacer's copies hide it from JSON.stringify, which runs out of stack.
		const cycle: Record<string, unknown> = {};
		cycle.self = cycle;
		expect(() => canonicalJsonByReplacer(cycle)).toThrow(RangeError);
		expect(() => canonicalJson(cycle)).toThrow(RangeError);
	});

	it('refuses a non-finite number with the replacer’s message', () => {
		const value = deepFreeze({ piping: { pipes: [{ length: 1 }, { length: Number.NaN }] } });
		expect(() => canonicalJson(value)).toThrow(
			'Cannot encode the non-finite number NaN (field "length")'
		);
		expect(() => canonicalJson([1, Infinity])).toThrow(
			'Cannot encode the non-finite number Infinity (field "1")'
		);
	});

	it('keeps no text of a frozen object whose parts may still change', () => {
		const inner = { length: 1 };
		const outer = Object.freeze({ pipes: Object.freeze([inner]), more: 'x'.repeat(100) });
		const before = canonicalJson(outer);
		inner.length = 2;
		expect(canonicalJson(outer)).toBe(canonicalJsonByReplacer(outer));
		expect(canonicalJson(outer)).not.toBe(before);
	});
});

describe('canonicalJsonWithout', () => {
	it('writes the object without the key, as a copy with it deleted', () => {
		const random = rng(2);
		for (let i = 0; i < 1000; i++) {
			const value = randomValue(random);
			if (typeof value !== 'object' || value === null || Array.isArray(value)) continue;
			for (const target of [value, deepFreeze(structuredClone(value))]) {
				for (const key of ['name', 'id', '0']) {
					const copy: Record<string, unknown> = { ...target };
					delete copy[key];
					expect(canonicalJsonWithout(target, key)).toBe(canonicalJsonByReplacer(copy));
					expect(canonicalJsonWithout(target, key)).toBe(canonicalJsonByReplacer(copy));
				}
			}
		}
	});
});

describe('canonicalJsonEqual', () => {
	it('answers as comparing the two texts, on values that share parts', () => {
		const random = rng(3);
		let same = 0;
		for (let i = 0; i < 3000; i++) {
			const stored = deepFreeze(randomValue(random));
			// An edit of a stored value shares the parts it did not change.
			const edit = changed(stored, random);
			const shared =
				typeof edit === 'object' && edit !== null && typeof stored === 'object' && stored
					? Object.fromEntries(
							Object.entries(edit).map(([k, v]) => [
								k,
								canonicalJson(v) === canonicalJson((stored as Record<string, unknown>)[k])
									? (stored as Record<string, unknown>)[k]
									: v
							])
						)
					: edit;
			for (const a of [edit, shared]) {
				const expected = canonicalJsonByReplacer(a) === canonicalJsonByReplacer(stored);
				expect(canonicalJsonEqual(a, stored)).toBe(expected);
				if (expected) same++;
			}
		}
		expect(same).toBeGreaterThan(100);
	});

	it('refuses a non-finite number in a part it writes, as canonicalJson does', () => {
		const stored = deepFreeze({ a: { length: 1 }, b: [1, 2] });
		expect(() => canonicalJsonEqual({ ...stored, a: { length: Number.NaN } }, stored)).toThrow(
			'Cannot encode the non-finite number NaN (field "length")'
		);
		// Even when another part already differs: canonicalJson writes all of it first.
		expect(() =>
			canonicalJsonEqual({ a: { length: 2 }, b: [1, Number.POSITIVE_INFINITY] }, stored)
		).toThrow('Cannot encode the non-finite number Infinity (field "1")');
		expect(() => canonicalJsonEqual({ ...stored, c: Number.NaN }, stored)).toThrow(
			'Cannot encode the non-finite number NaN (field "c")'
		);
	});
});
