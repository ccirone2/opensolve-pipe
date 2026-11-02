/**
 * Recent projects on this device (the owner's decision of 2026-11-01, proposal landing-page.md;
 * ui-ux-refinement.md item 14). The project page remembers the link of each project opened or
 * edited here, and the home page lists them. They are kept in this browser's localStorage only:
 * never sent anywhere, never in a link (D3, GOALS §4.5), and "Forget" removes them.
 *
 * What is stored is what the address bar already holds, the encoded project, with the project's
 * id and name. Storage can be missing or refuse a write (a private window, a full quota, blocked
 * site data): every read and write is in try/catch, and the app works the same without it.
 */

/** The localStorage key. */
export const RECENT_KEY = 'opensolve-pipe:recent-projects';

/** How many projects are remembered (the newest first). */
export const RECENT_LIMIT = 8;

/** A project longer than this many characters is not remembered (a share of the quota). */
export const RECENT_MAX_LENGTH = 500_000;

export interface RecentProject {
	/** The project's id: one entry per project, the latest link wins. */
	id: string;
	/** The project's name when it was last seen. */
	name: string;
	/** The encoded project, as in its link after the "#". */
	encoded: string;
	/** When it was last opened or edited here (ISO 8601). */
	savedAt: string;
}

/** The part of the Storage interface used here (tests pass their own). */
export type RecentStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

/** This browser's localStorage, or null where it cannot be reached. */
export function browserStorage(): RecentStorage | null {
	try {
		return typeof localStorage === 'undefined' ? null : localStorage;
	} catch {
		return null;
	}
}

function isRecent(value: unknown): value is RecentProject {
	if (!value || typeof value !== 'object') return false;
	const entry = value as Record<string, unknown>;
	return (
		typeof entry.id === 'string' &&
		typeof entry.name === 'string' &&
		typeof entry.encoded === 'string' &&
		entry.encoded.length > 0 &&
		typeof entry.savedAt === 'string'
	);
}

/** The remembered projects, newest first. Anything unreadable is ignored. */
export function readRecent(storage: RecentStorage | null = browserStorage()): RecentProject[] {
	if (!storage) return [];
	try {
		const parsed: unknown = JSON.parse(storage.getItem(RECENT_KEY) ?? '[]');
		return Array.isArray(parsed) ? parsed.filter(isRecent).slice(0, RECENT_LIMIT) : [];
	} catch {
		return [];
	}
}

/** Write the list; on a full quota drop the oldest until it fits. False if nothing could be kept. */
function write(storage: RecentStorage, entries: RecentProject[]): boolean {
	for (let kept = entries; kept.length > 0; kept = kept.slice(0, -1)) {
		try {
			storage.setItem(RECENT_KEY, JSON.stringify(kept));
			return true;
		} catch {
			// Quota or blocked storage: try with one fewer.
		}
	}
	try {
		storage.removeItem(RECENT_KEY);
	} catch {
		// Nothing more to do: the list is a convenience.
	}
	return false;
}

/** Remember a project (it moves to the top). Returns the list as now stored. */
export function rememberProject(
	entry: RecentProject,
	storage: RecentStorage | null = browserStorage()
): RecentProject[] {
	if (!storage || !entry.encoded || entry.encoded.length > RECENT_MAX_LENGTH)
		return readRecent(storage);
	const others = readRecent(storage).filter((e) => e.id !== entry.id);
	const entries = [entry, ...others].slice(0, RECENT_LIMIT);
	write(storage, entries);
	return readRecent(storage);
}

/** Forget one project. Returns the list as now stored. */
export function forgetProject(
	id: string,
	storage: RecentStorage | null = browserStorage()
): RecentProject[] {
	if (!storage) return [];
	const entries = readRecent(storage).filter((e) => e.id !== id);
	if (entries.length) write(storage, entries);
	else forgetAll(storage);
	return readRecent(storage);
}

/** Forget every project: the key is removed. */
export function forgetAll(storage: RecentStorage | null = browserStorage()): void {
	try {
		storage?.removeItem(RECENT_KEY);
	} catch {
		// Blocked storage holds nothing to forget.
	}
}
