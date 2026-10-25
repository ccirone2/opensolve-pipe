/**
 * Canonical JSON (keys sorted at every level), so equal values serialize identically: the URL
 * encoding (encoding.ts), staleness fingerprints and scenario changes compare values with it. It
 * imports nothing, so any module can use it.
 */

/**
 * JSON with object keys sorted at every level, so equal projects encode identically.
 *
 * Non-finite numbers would become `null` in JSON and make the link undecodable, so they are
 * rejected here instead. (Do not use an array replacer for ordering: it filters keys at every
 * depth and silently drops nested fields, TSD §4.7.)
 */
export function canonicalJson(value: unknown): string {
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
