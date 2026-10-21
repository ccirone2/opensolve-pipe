/**
 * Project schema migrations (D2, SDD §5.2, TSD §4.7).
 *
 * Shared links live forever, so a link saved by any released schema version must always open.
 * A breaking change to the project model bumps `schemaVersion` (in the API models and here) and
 * adds an entry to MIGRATIONS that upgrades the previous version. Entries are never removed, and
 * every released version keeps a fixture link in `__fixtures__/` that a test decodes.
 */
import { LinkError, NOT_A_PROJECT_MESSAGE } from './link-error';

/** The project schema version this app writes. Must equal `Project.schemaVersion` in the API. */
export const CURRENT_SCHEMA_VERSION = 1;

/** A decoded, not yet validated project object. */
export type RawProject = Record<string, unknown>;

/** Upgrades a project from version n to n + 1 (the caller sets `schemaVersion`). */
export type Migration = (project: RawProject) => RawProject;

/** MIGRATIONS[n] upgrades a project from version n to n + 1. Never remove an entry. */
export const MIGRATIONS: Readonly<Record<number, Migration>> = Object.freeze({});

function isRecord(value: unknown): value is RawProject {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function newerVersionMessage(found: number, current: number): string {
	return (
		`This link was made with a newer version of OpenSolve Pipe (project format ${found}; ` +
		`this version reads formats up to ${current}). Reload the page to get the latest ` +
		'version of the app, then open the link again.'
	);
}

/**
 * Upgrade a decoded project to `currentVersion` by applying the migrations in order.
 * The result is not validated; `decodeProject` validates it against the current schema.
 *
 * Throws LinkError('invalid') when the value is not a project (no positive integer
 * `schemaVersion`) and LinkError('newer_version') when it is newer than this app.
 */
export function migrate(
	raw: unknown,
	migrations: Readonly<Record<number, Migration>> = MIGRATIONS,
	currentVersion: number = CURRENT_SCHEMA_VERSION
): RawProject {
	if (!isRecord(raw)) throw new LinkError('invalid', NOT_A_PROJECT_MESSAGE);
	const from = raw.schemaVersion;
	if (typeof from !== 'number' || !Number.isInteger(from) || from < 1) {
		throw new LinkError('invalid', NOT_A_PROJECT_MESSAGE);
	}
	if (from > currentVersion) {
		throw new LinkError('newer_version', newerVersionMessage(from, currentVersion));
	}
	let project = raw;
	for (let version = from; version < currentVersion; version++) {
		const step = migrations[version];
		// A missing step is a bug in this file, not in the link.
		if (!step) throw new Error(`No migration from project schema version ${version}`);
		project = { ...step(project), schemaVersion: version + 1 };
	}
	return project;
}
