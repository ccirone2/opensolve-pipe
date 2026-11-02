import { describe, expect, it } from 'vitest';
import {
	forgetAll,
	forgetProject,
	readRecent,
	RECENT_KEY,
	RECENT_LIMIT,
	RECENT_MAX_LENGTH,
	rememberProject,
	type RecentProject,
	type RecentStorage
} from './recent';

/** An in-memory storage that can hold at most `quota` characters. */
function memory(quota = Infinity): RecentStorage & { data: Map<string, string> } {
	const data = new Map<string, string>();
	return {
		data,
		getItem: (key) => data.get(key) ?? null,
		setItem: (key, value) => {
			if (value.length > quota) throw new DOMException('full', 'QuotaExceededError');
			data.set(key, value);
		},
		removeItem: (key) => void data.delete(key)
	};
}

const entry = (id: string, encoded = `enc-${id}`): RecentProject => ({
	id,
	name: `Project ${id}`,
	encoded,
	savedAt: '2026-11-01T12:00:00.000Z'
});

describe('recent projects', () => {
	it('keeps the newest first, one entry per project id', () => {
		const storage = memory();
		rememberProject(entry('a'), storage);
		rememberProject(entry('b'), storage);
		const list = rememberProject(entry('a', 'enc-a2'), storage);
		expect(list.map((e) => [e.id, e.encoded])).toEqual([
			['a', 'enc-a2'],
			['b', 'enc-b']
		]);
	});

	it(`remembers at most ${RECENT_LIMIT}, dropping the oldest`, () => {
		const storage = memory();
		for (let i = 0; i < RECENT_LIMIT + 3; i++) rememberProject(entry(`p${i}`), storage);
		const list = readRecent(storage);
		expect(list).toHaveLength(RECENT_LIMIT);
		expect(list[0]?.id).toBe(`p${RECENT_LIMIT + 2}`);
		expect(list.at(-1)?.id).toBe('p3');
	});

	it('drops the oldest entries until the list fits a full quota', () => {
		// Room for one entry, not two.
		const one = JSON.stringify([entry('a', 'x'.repeat(100))]).length;
		const two = JSON.stringify([entry('a', 'x'.repeat(100)), entry('b', 'y'.repeat(100))]).length;
		const storage = memory(Math.floor((one + two) / 2));
		rememberProject(entry('a', 'x'.repeat(100)), storage);
		rememberProject(entry('b', 'y'.repeat(100)), storage);
		const list = rememberProject(entry('c', 'z'.repeat(100)), storage);
		expect(list.map((e) => e.id)).toEqual(['c']);
	});

	it('does not remember a project longer than its share of the quota', () => {
		const storage = memory();
		rememberProject(entry('big', 'x'.repeat(RECENT_MAX_LENGTH + 1)), storage);
		expect(readRecent(storage)).toEqual([]);
	});

	it('forgets one project, and all of them', () => {
		const storage = memory();
		rememberProject(entry('a'), storage);
		rememberProject(entry('b'), storage);
		expect(forgetProject('b', storage).map((e) => e.id)).toEqual(['a']);
		expect(forgetProject('a', storage)).toEqual([]);
		expect(storage.data.has(RECENT_KEY)).toBe(false);
		rememberProject(entry('c'), storage);
		forgetAll(storage);
		expect(storage.data.has(RECENT_KEY)).toBe(false);
	});

	it('ignores unreadable data and missing or blocked storage', () => {
		const storage = memory();
		storage.data.set(RECENT_KEY, '{not json');
		expect(readRecent(storage)).toEqual([]);
		storage.data.set(RECENT_KEY, JSON.stringify([{ id: 1 }, entry('ok'), null, 'x']));
		expect(readRecent(storage).map((e) => e.id)).toEqual(['ok']);
		expect(readRecent(null)).toEqual([]);
		expect(rememberProject(entry('a'), null)).toEqual([]);
		const blocked: RecentStorage = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			},
			removeItem: () => {
				throw new Error('blocked');
			}
		};
		expect(rememberProject(entry('a'), blocked)).toEqual([]);
		expect(() => forgetAll(blocked)).not.toThrow();
	});
});
