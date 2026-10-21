/**
 * Project ⇄ URL fragment encoding (D3, SDD §5.2, TSD §4.7).
 *
 *   encode: Project → canonical JSON (keys sorted at every level) → gzip (pako, level 9)
 *           → base64url without padding → https://opensolve-pipe.app/p#<encoded>
 *   decode: base64url → gunzip → JSON.parse → migrate() → validate
 *
 * The project lives in the fragment, which browsers never send to a server, so project data is
 * never logged. Shared links live forever: decoding must keep working for every released
 * schema version (see migrations.ts and the fixtures in __fixtures__/).
 */
import { gzip, ungzip } from 'pako';
import type { Project } from '../api/types';
import { CORRUPT_LINK_MESSAGE, INVALID_PROJECT_MESSAGE, LinkError } from './link-error';
import { migrate } from './migrations';
import { parseProject, ProjectValidationError } from './validate';

/** Links longer than this (in characters) may be cut short by some email and chat clients. */
export const URL_LENGTH_WARNING = 8000;

/** The app route that opens a project from its fragment. */
export const PROJECT_PATH = '/p';

/** Canonical public origin, used where the page's own origin is unknown. */
export const CANONICAL_ORIGIN = 'https://opensolve-pipe.app';

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

export function toBase64Url(bytes: Uint8Array): string {
	let binary = '';
	for (const b of bytes) binary += String.fromCharCode(b);
	return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function fromBase64Url(text: string): Uint8Array {
	if (!/^[A-Za-z0-9_-]*$/.test(text) || text.length % 4 === 1) {
		throw new SyntaxError('Not a base64url string');
	}
	const b64 = text.replace(/-/g, '+').replace(/_/g, '/');
	const binary = atob(b64 + '==='.slice((b64.length + 3) % 4));
	return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

/** The URL-fragment encoding of a project (no leading '#'). */
export function encodeProject(project: Project): string {
	return toBase64Url(gzip(new TextEncoder().encode(canonicalJson(project)), { level: 9 }));
}

/** The text after the first '#' of a link, or the whole text when it has none. */
export function fragmentOf(link: string): string {
	const hash = link.indexOf('#');
	return (hash === -1 ? link : link.slice(hash + 1)).trim();
}

/**
 * Decode a URL fragment (with or without the leading '#') into a validated, current-version
 * project. Throws LinkError with kind 'corrupt', 'newer_version' or 'invalid'.
 */
export function decodeProject(encoded: string): Project {
	const text = encoded.trim().replace(/^#/, '');
	if (!text) throw new LinkError('corrupt', CORRUPT_LINK_MESSAGE);
	let raw: unknown;
	try {
		const json = new TextDecoder('utf-8', { fatal: true }).decode(ungzip(fromBase64Url(text)));
		raw = JSON.parse(json);
	} catch {
		throw new LinkError('corrupt', CORRUPT_LINK_MESSAGE);
	}
	const migrated = migrate(raw);
	try {
		return parseProject(migrated);
	} catch (error) {
		if (error instanceof ProjectValidationError) {
			throw new LinkError('invalid', INVALID_PROJECT_MESSAGE, error.problems);
		}
		throw error;
	}
}

/** App-relative link to a project: `/p#<encoded>`. */
export function projectPath(project: Project): string {
	return `${PROJECT_PATH}#${encodeProject(project)}`;
}

/** Full shareable link to a project: `${origin}/p#<encoded>`. */
export function projectUrl(project: Project, origin: string = CANONICAL_ORIGIN): string {
	return `${origin.replace(/\/+$/, '')}${projectPath(project)}`;
}
