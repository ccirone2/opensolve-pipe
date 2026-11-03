/**
 * Canonical JSON (keys sorted at every level), so equal values serialize identically: the URL
 * encoding (encoding.ts), staleness fingerprints and scenario changes compare values with it. It
 * imports nothing, so any module can use it.
 *
 * The text of a deep-frozen object is kept (a stored project is deep-frozen and its parts are
 * shared between versions: project.svelte.ts update()), so an edit writes again only what it
 * changed. The text is exactly JSON.stringify's with the sorting replacer (canonicalJsonByReplacer,
 * which also writes, or refuses, every value the fast writer does not handle itself).
 */

/** The canonical JSON of deep-frozen objects and arrays, which never change. */
const frozenJson = new WeakMap<object, string>();

/**
 * Texts kept: from this length (a shorter one is as quick to write again) up to the upper bound (a
 * project's or a long array's text is joined again from its parts, which are kept, so that the
 * versions in the undo history do not each keep a copy of the whole project).
 */
const KEEP_FROM = 64;
const KEEP_UP_TO = 65_536;

/** A value the fast writer leaves to JSON.stringify (canonicalJsonByReplacer). */
class Unusual extends Error {}

/** An array index (2³² − 1 is not one): JavaScript lists these keys first, in numeric order. */
function isArrayIndex(key: string): boolean {
	return /^(?:0|[1-9]\d*)$/.test(key) && Number(key) < 4294967295;
}

/** Whether the value written last is deep-frozen (set by write()). */
let deep = true;

/** The canonical JSON of `value` (undefined where JSON.stringify gives none). */
function write(value: unknown): string | undefined {
	switch (typeof value) {
		case 'string':
			deep = true;
			return JSON.stringify(value);
		case 'number':
			if (!Number.isFinite(value)) throw new Unusual();
			deep = true;
			return String(value);
		case 'boolean':
			deep = true;
			return value ? 'true' : 'false';
		case 'undefined':
		case 'symbol':
			deep = true;
			return undefined;
		case 'object':
			break;
		default:
			// A function (which may have a toJSON) or a bigint.
			throw new Unusual();
	}
	if (value === null) {
		deep = true;
		return 'null';
	}
	const frozen = Object.isFrozen(value);
	if (frozen) {
		const known = frozenJson.get(value);
		if (known !== undefined) {
			deep = true;
			return known;
		}
	}
	if (typeof (value as { toJSON?: unknown }).toJSON === 'function') throw new Unusual();
	let allDeep = frozen;
	let json: string;
	if (Array.isArray(value)) {
		const parts: string[] = new Array<string>(value.length);
		for (let i = 0; i < value.length; i++) {
			parts[i] = write(value[i]) ?? 'null';
			allDeep &&= deep;
		}
		json = `[${parts.join(',')}]`;
	} else {
		if (!isPlainObject(value)) throw new Unusual();
		json = writeObject(value);
		allDeep &&= deep;
	}
	deep = allDeep;
	if (allDeep && json.length >= KEEP_FROM && json.length <= KEEP_UP_TO) frozenJson.set(value, json);
	return json;
}

function isPlainObject(value: object): value is Record<string, unknown> {
	const proto: unknown = Object.getPrototypeOf(value);
	return !Array.isArray(value) && (proto === Object.prototype || proto === null);
}

/** A plain object's canonical JSON, without its key `omit` (sets `deep` for its values). */
function writeObject(record: Record<string, unknown>, omit?: string): string {
	const ordered = canonicalKeys(record);
	const parts: string[] = [];
	let allDeep = true;
	for (const key of ordered) {
		if (key === omit) continue;
		const text = write(record[key]);
		allDeep &&= deep;
		if (text !== undefined) parts.push(`${JSON.stringify(key)}:${text}`);
	}
	deep = allDeep;
	return `{${parts.join(',')}}`;
}

/** canonicalJsonWithout()'s texts of deep-frozen objects, by the key left out. */
const frozenJsonWithout = new Map<string, WeakMap<object, string>>();

/**
 * The canonical JSON of a copy of `value` without its key `omit` (`{ ...value }` with `omit`
 * deleted), kept for a deep-frozen object as canonicalJson's text is.
 */
export function canonicalJsonWithout(value: object, omit: string): string {
	let texts = frozenJsonWithout.get(omit);
	if (!texts) frozenJsonWithout.set(omit, (texts = new WeakMap()));
	const known = texts.get(value);
	if (known !== undefined) return known;
	try {
		if (!isPlainObject(value) || typeof value.toJSON === 'function') throw new Unusual();
		const json = writeObject(value, omit);
		if (deep && Object.isFrozen(value) && json.length <= KEEP_UP_TO) texts.set(value, json);
		return json;
	} catch {
		const copy: Record<string, unknown> = { ...value };
		delete copy[omit];
		return canonicalJsonByReplacer(copy);
	}
}

/** A plain object's keys in the order of its canonical text (writeObject's). */
function canonicalKeys(record: Record<string, unknown>): string[] {
	const keys = Object.keys(record);
	// The replacer's sorted copy lists array-index keys first, in numeric order (as Object.keys
	// already gives them), then the others in sorted order.
	let split = 0;
	while (split < keys.length && isArrayIndex(keys[split] as string)) split++;
	return split === 0 ? keys.sort() : [...keys.slice(0, split), ...keys.slice(split).sort()];
}

/** A plain object or array without a toJSON: sameText() compares its parts. */
function isContainer(value: unknown): value is Record<string, unknown> | unknown[] {
	if (typeof value !== 'object' || value === null) return false;
	if (typeof (value as { toJSON?: unknown }).toJSON === 'function') return false;
	return Array.isArray(value)
		? Object.getPrototypeOf(value) === Array.prototype
		: isPlainObject(value);
}

/** Two containers of the same kind (both arrays, or both objects): sameText() compares parts. */
function bothContainers(a: unknown, b: unknown): boolean {
	return isContainer(a) && isContainer(b) && Array.isArray(a) === Array.isArray(b);
}

/** Whether an object's value has a text in its JSON (else its key is left out). */
function hasText(value: unknown): boolean {
	if (value === undefined || typeof value === 'function' || typeof value === 'symbol') return false;
	if (typeof value === 'object' && value !== null && !isContainer(value)) throw new Unusual();
	return true;
}

/**
 * Whether canonicalJson(a) === canonicalJson(b): parts the two share (the same object or value in
 * the same place) are not written again, and every other part of `a` is (so that an `a`
 * canonicalJson refuses is refused). A JSON text has one reading, so two texts are equal when they
 * have the same keys, in order, with equal texts (objects), or equal texts in each place (arrays).
 */
function sameText(a: unknown, b: unknown): boolean {
	if (a === b) return true;
	if (!bothContainers(a, b)) return canonicalJson(a) === canonicalJson(b);
	let equal = true;
	if (Array.isArray(a)) {
		const others = b as unknown[];
		if (a.length !== others.length) equal = false;
		for (let i = 0; i < a.length; i++) {
			const x: unknown = a[i];
			const y: unknown = others[i];
			if (i < others.length && x === y) continue;
			// A value without a text is written "null" in an array.
			const same = bothContainers(x, y)
				? sameText(x, y)
				: (canonicalJson(x) ?? 'null') === (canonicalJson(y) ?? 'null');
			equal &&= same;
		}
		return equal;
	}
	const record = a as Record<string, unknown>;
	const other = b as Record<string, unknown>;
	const otherKeys = canonicalKeys(other);
	const has = new Set(otherKeys);
	const keys: string[] = [];
	for (const key of canonicalKeys(record)) {
		const x = record[key];
		const y = has.has(key) ? other[key] : undefined;
		if (hasText(x)) keys.push(key);
		if (x === y) continue;
		const same = bothContainers(x, y) ? sameText(x, y) : canonicalJson(x) === canonicalJson(y);
		equal &&= same;
	}
	const otherWithText = otherKeys.filter((key) => hasText(other[key]));
	return (
		equal &&
		keys.length === otherWithText.length &&
		keys.every((key, i) => key === otherWithText[i])
	);
}

/**
 * Whether two values have the same canonical JSON, as `canonicalJson(a) === canonicalJson(b)`
 * (throwing as it does), without writing the parts `a` shares with `b`: for `b` a stored project,
 * whose text canonicalJson has written, and `a` an edit of it that shares its unchanged parts.
 */
export function canonicalJsonEqual(a: unknown, b: unknown): boolean {
	try {
		return sameText(a, b);
	} catch {
		return canonicalJson(a) === canonicalJson(b);
	}
}

/**
 * JSON with object keys sorted at every level, so equal projects encode identically.
 *
 * Non-finite numbers would become `null` in JSON and make the link undecodable, so they are
 * rejected here instead. (Do not use an array replacer for ordering: it filters keys at every
 * depth and silently drops nested fields, TSD §4.7.)
 */
export function canonicalJson(value: unknown): string {
	try {
		return write(value) as string;
	} catch {
		// A toJSON, an instance of a class, a cycle, a non-finite number: JSON.stringify writes it
		// or refuses it, with its own message.
		return canonicalJsonByReplacer(value);
	}
}

/**
 * canonicalJson as JSON.stringify writes it, with a replacer that sorts each object's keys: the
 * definition the fast writer above keeps to (json.test.ts compares them).
 */
export function canonicalJsonByReplacer(value: unknown): string {
	return JSON.stringify(value, (key, v: unknown) => {
		if (typeof v === 'number' && !Number.isFinite(v)) {
			throw new TypeError(`Cannot encode the non-finite number ${v} (field "${key}")`);
		}
		if (v && typeof v === 'object' && !Array.isArray(v)) {
			const record = v as Record<string, unknown>;
			return Object.fromEntries(
				Object.keys(record)
					.sort()
					.map((k) => [k, record[k]])
			);
		}
		return v;
	});
}
