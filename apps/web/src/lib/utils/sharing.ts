/**
 * Structural sharing between versions of a project (per-edit speed on large networks).
 *
 * An edit works on a deep copy of the stored project (copyData below; state/project.svelte.ts
 * update()), so every element of the result is a new object, even one the edit did not touch. shareUnchanged()
 * puts the stored element back wherever the edit's is equal to it: the stored project is
 * deep-frozen, so what an edit did not change keeps its identity, its canonical JSON (json.ts keeps
 * the text of frozen objects) and its validity (the store checks only the elements that changed).
 *
 * Sharing never changes a value: an element is put back only when it is equal to the stored one in
 * every key, in the same order, and every value (Object.is); a pipe (identity.ts: pipes have no
 * ids, so their objects carry their identity) only when it is also the same pipe, so a new pipe
 * equal to an old one stays another pipe. It is done for whole elements of the project's lists
 * (components, connections, pump curves, scenarios, library entries) and whole top-level values
 * (settings, fluid, metadata). It is not done at all when the edit's project holds a frozen object
 * outside the elements put back (a stored object an edit took from the page, not from its draft):
 * putting back the stored element could make that object appear twice, and the next edit's clone
 * would then keep the two as one object.
 */
import type { Project } from '../api/types';
import { originOf } from './identity';

type Data = Record<string, unknown>;

function isPlainObject(value: unknown): value is Data {
	if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
	const proto: unknown = Object.getPrototypeOf(value);
	return proto === Object.prototype || proto === null;
}

/**
 * Whether `a` and `b` are equal data: the same keys in the same order and equal values (Object.is
 * for anything that is not a plain object or array). In a list of pipes (`key` 'pipes'), each pipe
 * must also be the same pipe (identity.ts originOf).
 */
export function equalData(a: unknown, b: unknown, key = ''): boolean {
	if (Object.is(a, b)) return true;
	if (Array.isArray(a)) {
		if (!Array.isArray(b) || a.length !== b.length) return false;
		const pipes = key === 'pipes';
		for (let i = 0; i < a.length; i++) {
			const x: unknown = a[i];
			const y: unknown = b[i];
			if (pipes && typeof x === 'object' && x !== null && typeof y === 'object' && y !== null) {
				if (originOf(x) !== originOf(y)) return false;
			}
			if (!equalData(x, y)) return false;
		}
		return true;
	}
	if (!isPlainObject(a) || !isPlainObject(b)) return false;
	const keys = Object.keys(a);
	const others = Object.keys(b);
	if (keys.length !== others.length) return false;
	for (let i = 0; i < keys.length; i++) {
		const k = keys[i] as string;
		if (k !== others[i] || !equalData(a[k], b[k], k)) return false;
	}
	return true;
}

/** Whether `value` holds a frozen object (itself included). */
function holdsFrozen(value: unknown): boolean {
	if (typeof value !== 'object' || value === null) return false;
	if (Object.isFrozen(value)) return true;
	for (const child of Object.values(value)) if (holdsFrozen(child)) return true;
	return false;
}

/** The id of a list element, or null when it has none. */
function idOf(value: unknown): string | null {
	return isPlainObject(value) && typeof value.id === 'string' ? value.id : null;
}

/**
 * For each element of `next`, the element of `stored` to compare it with: the one with its id when
 * every element of both has an id (each used once, the first of an id), else the one in its place.
 */
function counterparts(next: readonly unknown[], stored: readonly unknown[]): unknown[] {
	const ids = next.map(idOf);
	const storedIds = stored.map(idOf);
	if (ids.some((id) => id === null) || storedIds.some((id) => id === null)) {
		return next.map((_, i) => stored[i]);
	}
	const byId = new Map<string, unknown>();
	stored.forEach((element, i) => {
		const id = storedIds[i] as string;
		if (!byId.has(id)) byId.set(id, element);
	});
	return ids.map((id) => {
		const element = byId.get(id as string);
		byId.delete(id as string);
		return element;
	});
}

/**
 * `next` (an edit's result, built on a clone of `stored`) with each element and top-level value
 * equal to `stored`'s put back as `stored`'s own object (see the module's comment); `stored` itself
 * when nothing differs. `next` is changed in place; a frozen `next` is returned as it is.
 */
export function shareUnchanged(next: Project, stored: Project): Project {
	if (next === stored || Object.isFrozen(next) || !isPlainObject(next)) return next;
	const was = stored as unknown as Data;
	const now = next as unknown as Data;
	/** Writes to make: [object, key, stored value]. */
	const puts: [Data | unknown[], string | number, unknown][] = [];
	/** Values of `next` that stay: none may hold a frozen object. */
	const kept: unknown[] = [];
	const keys = Object.keys(now);
	let same = equalKeys(keys, Object.keys(was));
	for (const key of keys) {
		const value = now[key];
		const before = Object.hasOwn(was, key) ? was[key] : undefined;
		if (value === before) continue;
		if (Array.isArray(value) && Array.isArray(before) && !Object.isFrozen(value)) {
			// A list: its elements one by one; the stored list itself when every one is put back.
			const match = counterparts(value, before);
			const listPuts: typeof puts = [];
			let whole = value.length === before.length;
			value.forEach((element: unknown, i) => {
				const other = match[i];
				if (other !== before[i]) whole = false;
				if (element === other) return;
				if (other !== undefined && equalData(element, other)) listPuts.push([value, i, other]);
				else {
					whole = false;
					kept.push(element);
				}
			});
			if (whole) puts.push([now, key, before]);
			else {
				same = false;
				puts.push(...listPuts);
			}
		} else if (before !== undefined && equalData(value, before, key)) {
			puts.push([now, key, before]);
		} else {
			same = false;
			kept.push(value);
		}
	}
	if (kept.some(holdsFrozen)) return next;
	if (same && puts.every(([holder]) => holder === now)) return stored;
	for (const [holder, key, value] of puts) (holder as Data)[key as string] = value;
	return next;
}

function equalKeys(a: readonly string[], b: readonly string[]): boolean {
	return a.length === b.length && a.every((k, i) => k === b[i]);
}

/** A value copyData() leaves to structuredClone. */
class NotPlainData extends Error {}

function copy(value: unknown): unknown {
	if (typeof value !== 'object' || value === null) {
		if (typeof value === 'function' || typeof value === 'symbol') throw new NotPlainData();
		return value;
	}
	if (Array.isArray(value)) {
		if (Object.getPrototypeOf(value) !== Array.prototype) throw new NotPlainData();
		const out: unknown[] = new Array<unknown>(value.length);
		for (let i = 0; i < value.length; i++) {
			if (!(i in value)) throw new NotPlainData();
			out[i] = copy(value[i]);
		}
		return out;
	}
	if (!isPlainObject(value)) throw new NotPlainData();
	const out: Data = {};
	for (const key of Object.keys(value)) {
		// An own "__proto__" (JSON.parse makes one) would set the copy's prototype instead.
		if (key === '__proto__') throw new NotPlainData();
		out[key] = copy(value[key]);
	}
	return out;
}

/**
 * A deep copy of plain data (an edit's draft of a stored project): the same keys in the same order
 * and the same values as structuredClone's, in a fifth to a sixth of its time (measured 2026-11-03
 * on a deep-frozen 1,000-component network: about 1.5-2 ms against 8-13 ms, in Chromium and
 * Node 22). Each place gets its own copy, as JSON has it (structuredClone would keep an object
 * that appears twice as one object). Anything that is not plain data (a class instance, a function, a cycle, a sparse
 * array) is copied, or refused, by structuredClone itself.
 */
export function copyData<T>(value: T): T {
	try {
		return copy(value) as T;
	} catch {
		return structuredClone(value);
	}
}
