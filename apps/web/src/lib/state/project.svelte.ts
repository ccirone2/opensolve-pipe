/**
 * Project state (SDD §3.1.4): the port-graph project (SI values), in-browser undo/redo, the URL
 * fragment that holds the project (D3), and the latest solve results.
 *
 * Invariants:
 * - `project` is replaced, never mutated: every change goes through update(), undo(), redo()
 *   or load(), and each stored project is deep-frozen, so an accidental in-place edit throws.
 * - Every stored project is valid against the API schema and its port graph is consistent, so
 *   every link the app writes opens again. An update() that would break this is refused.
 * - Copy-on-write sharing: each change rewrites the current URL (history.replaceState, after a
 *   short debounce). A link copied earlier still opens the project as it was then.
 *
 * Nothing is kept in browser storage; history lives only in this page.
 */
import { getContext, setContext } from 'svelte';
import { defaultClient, NetworkError, TopologyError, ValidationError } from '../api/client';
import type {
	Project,
	SolvedState,
	SolveOptions,
	SolveResponse,
	TopologyIssue
} from '../api/types';
import {
	CANONICAL_ORIGIN,
	canonicalJson,
	encodeProject,
	PROJECT_PATH,
	URL_LENGTH_WARNING
} from '../utils/encoding';
import { createEmptyProject, isoNow } from '../utils/factory';
import { referenceProblems, schemaProblems } from '../utils/validate';

export const MAX_HISTORY = 100;
export const URL_SYNC_DELAY_MS = 300;

export interface HistoryEntry {
	project: Project;
	/** What the change did, e.g. "Add pump" (for "Undo add pump"). */
	label: string;
}

export type UpdateResult = { ok: true; changed: boolean } | { ok: false; problems: string[] };

export type ResultsError =
	| { kind: 'topology'; message: string; issues: readonly TopologyIssue[] }
	| {
			kind: 'validation';
			message: string;
			details: readonly string[];
			/** The API's error code, e.g. 'FLUID_ERROR' (absent when it sent none). */
			code?: string;
	  }
	| { kind: 'network'; message: string };

export interface ResultsState {
	/**
	 * The latest successful solve response (kept when stale, and when a later solve fails, so the
	 * last numbers can still be shown).
	 */
	response: SolveResponse | null;
	/**
	 * True when the project changed, in a way that can change the results, after `response` was
	 * computed (or, with no response, after the solve that gave `error`). Display units, names
	 * and metadata do not count: see hydraulicFingerprint().
	 */
	stale: boolean;
	solving: boolean;
	/** Why the latest solve gave no results (`response`, if any, is from an earlier solve). */
	error: ResultsError | null;
	/**
	 * True when the project changed, in a way that can change the results, after the solve that
	 * gave `error` (false without an error). With an error that is not stale and a stale
	 * `response`, the latest solve of the current project failed and the response is from an
	 * earlier version of it.
	 */
	errorStale: boolean;
}

export interface Solver {
	solve(project: Project, options?: Partial<SolveOptions>): Promise<SolveResponse>;
}

export interface ProjectStoreOptions {
	/** Writes the app-relative URL ('/p#…'). Default: history.replaceState, keeping its state. */
	writeUrl?: (path: string) => void;
	/** Origin used for the full link length. Default: location.origin, else the public origin. */
	origin?: string;
	/** Debounce of URL writes, ms (default 300). */
	urlSyncDelayMs?: number;
	/** Undo depth (default 100). */
	maxHistory?: number;
	/** Clock for metadata.modified (ISO 8601). */
	now?: () => string;
	/** Solver used by solve() (default: the API client). */
	solver?: Solver;
}

const EMPTY_RESULTS: ResultsState = Object.freeze({
	response: null,
	stale: false,
	solving: false,
	error: null,
	errorStale: false
});

function deepFreeze<T>(value: T): T {
	if (value && typeof value === 'object' && !Object.isFrozen(value)) {
		Object.freeze(value);
		for (const child of Object.values(value)) deepFreeze(child);
	}
	return value;
}

function defaultWriteUrl(path: string): void {
	if (typeof history === 'undefined') return;
	// Keep the router's state object so SvelteKit's history bookkeeping stays intact.
	history.replaceState(history.state, '', path);
}

function structuralProblems(project: unknown): string[] {
	const schema = schemaProblems(project);
	return schema.length ? schema : referenceProblems(project as Project);
}

/**
 * What a solve depends on: the project without its display units, metadata, method version
 * and component names (D4: unit preferences never change stored values; names and metadata
 * only label the results). Two projects with the same fingerprint give the same results.
 */
export function hydraulicFingerprint(project: Project): string {
	const solverSettings: Partial<Project['settings']> = { ...project.settings };
	delete solverSettings.units;
	return canonicalJson({
		schemaVersion: project.schemaVersion,
		settings: solverSettings,
		fluid: project.fluid,
		components: project.components.map((component) => {
			const unnamed: Partial<Project['components'][number]> = { ...component };
			delete unnamed.name;
			return unnamed;
		}),
		connections: project.connections,
		pumpLibrary: project.pumpLibrary
	});
}

function toResultsError(error: unknown): ResultsError {
	if (error instanceof TopologyError) {
		return { kind: 'topology', message: error.message, issues: error.issues };
	}
	if (error instanceof ValidationError) {
		return {
			kind: 'validation',
			message: error.message,
			details: error.details,
			...(error.code ? { code: error.code } : {})
		};
	}
	if (error instanceof NetworkError) return { kind: 'network', message: error.message };
	return {
		kind: 'network',
		message: error instanceof Error ? error.message : 'The solve failed unexpectedly.'
	};
}

export class ProjectStore {
	/** The current project. Never mutate it: use update(). */
	project = $state.raw<Project>(createEmptyProject());
	/** The latest solve results. */
	results = $state.raw<ResultsState>(EMPTY_RESULTS);
	/** URL-fragment encoding of the project as of the last URL write. */
	encoded = $state.raw('');
	/**
	 * The calculation-method version the project carried when it was loaded (empty: never
	 * solved). solve() records the version of each new solve in the project, so this keeps the
	 * one the link was shared with, for the results' method-version notice.
	 */
	loadedMethodVersion = $state.raw('');

	#undo = $state.raw<readonly HistoryEntry[]>([]);
	#redo = $state.raw<readonly HistoryEntry[]>([]);
	#mergeable = false;
	#solveSequence = 0;
	/** Fingerprints of the projects `results.response` and `results.error` came from. */
	#responseFingerprint: string | null = null;
	#errorFingerprint: string | null = null;
	#timer: ReturnType<typeof setTimeout> | null = null;
	readonly #options: ProjectStoreOptions;

	constructor(project?: Project, options: ProjectStoreOptions = {}) {
		this.#options = options;
		this.load(project ?? createEmptyProject({ now: this.#now() }));
	}

	/** The latest solved state, if any (check results.stale before relying on it). */
	get solved(): SolvedState | null {
		return this.results.response?.solvedState ?? null;
	}

	get canUndo(): boolean {
		return this.#undo.length > 0;
	}

	get canRedo(): boolean {
		return this.#redo.length > 0;
	}

	/** Label of the change undo() reverts, or null. */
	get undoLabel(): string | null {
		return this.#undo[this.#undo.length - 1]?.label ?? null;
	}

	/** Label of the change redo() re-applies, or null. */
	get redoLabel(): string | null {
		return this.#redo[this.#redo.length - 1]?.label ?? null;
	}

	get undoDepth(): number {
		return this.#undo.length;
	}

	get redoDepth(): number {
		return this.#redo.length;
	}

	/** Characters in the encoded project. */
	get encodedLength(): number {
		return this.encoded.length;
	}

	/** The full shareable link as of the last URL write. */
	get url(): string {
		return `${this.#origin()}${PROJECT_PATH}#${this.encoded}`;
	}

	/** Characters in the full link. */
	get urlLength(): number {
		return this.url.length;
	}

	/** True when the link is longer than 8,000 characters (D3): some clients truncate it. */
	get urlTooLong(): boolean {
		return this.urlLength > URL_LENGTH_WARNING;
	}

	#now(): string {
		return this.#options.now?.() ?? isoNow();
	}

	#origin(): string {
		const origin =
			this.#options.origin ??
			(typeof location !== 'undefined' && location.origin !== 'null' ? location.origin : undefined);
		return (origin ?? CANONICAL_ORIGIN).replace(/\/+$/, '');
	}

	/**
	 * Replace the project and reset undo/redo and results (opening a link, an example or a new
	 * project). The URL is written only when `writeUrl` is set; a project opened from the URL is
	 * already there. Throws when the project is not valid.
	 */
	load(project: Project, options: { writeUrl?: boolean } = {}): void {
		const problems = structuralProblems(project);
		if (problems.length) throw new Error(`Cannot load an invalid project: ${problems[0]}`);
		this.#cancelSync();
		this.project = deepFreeze(structuredClone(project));
		this.loadedMethodVersion = this.project.methodVersion;
		this.#undo = [];
		this.#redo = [];
		this.#mergeable = false;
		this.#solveSequence++;
		this.#responseFingerprint = null;
		this.#errorFingerprint = null;
		this.results = EMPTY_RESULTS;
		this.encoded = encodeProject(this.project);
		if (options.writeUrl) this.#write();
	}

	/**
	 * Apply a change. `change` receives a mutable copy of the project and may modify it or
	 * return a new project (the graph operations in utils/edit.ts return one). The result must
	 * be valid; otherwise nothing changes and the problems are returned. A change that leaves
	 * the project as it was adds no undo step.
	 *
	 * With `merge`, a change with the same label as the previous one (and nothing undone in
	 * between) joins its undo step, so a burst of edits to one field undoes at once.
	 */
	update(
		change: (draft: Project) => Project | void,
		label: string,
		options: { merge?: boolean } = {}
	): UpdateResult {
		const current = this.project;
		const draft = structuredClone(current);
		let next: Project;
		try {
			next = change(draft) ?? draft;
			if (canonicalJson(next) === canonicalJson(current)) return { ok: true, changed: false };
		} catch (error) {
			return { ok: false, problems: [error instanceof Error ? error.message : String(error)] };
		}
		next = { ...next, metadata: { ...next.metadata, modified: this.#now() } };
		const problems = structuralProblems(next);
		if (problems.length) return { ok: false, problems };

		const previous = this.#undo[this.#undo.length - 1];
		if (!(options.merge && this.#mergeable && previous?.label === label)) {
			const undo = [...this.#undo, { project: current, label }];
			this.#undo = undo.slice(Math.max(0, undo.length - (this.#options.maxHistory ?? MAX_HISTORY)));
		}
		this.#redo = [];
		this.#mergeable = true;
		this.#replace(next);
		return { ok: true, changed: true };
	}

	/** Revert the last change. Returns false when there is nothing to undo. */
	undo(): boolean {
		const entry = this.#undo[this.#undo.length - 1];
		if (!entry) return false;
		this.#undo = this.#undo.slice(0, -1);
		this.#redo = [...this.#redo, { project: this.project, label: entry.label }];
		this.#mergeable = false;
		this.#replace(entry.project);
		return true;
	}

	/** Re-apply the last undone change. Returns false when there is nothing to redo. */
	redo(): boolean {
		const entry = this.#redo[this.#redo.length - 1];
		if (!entry) return false;
		this.#redo = this.#redo.slice(0, -1);
		this.#undo = [...this.#undo, { project: this.project, label: entry.label }];
		this.#mergeable = false;
		this.#replace(entry.project);
		return true;
	}

	#replace(project: Project): void {
		this.project = deepFreeze(project);
		const { stale, errorStale } = this.#staleness(project);
		if (stale !== this.results.stale || errorStale !== this.results.errorStale) {
			this.results = { ...this.results, stale, errorStale };
		}
		this.#scheduleSync();
	}

	/**
	 * Whether the results shown (the response, else the error) are for another project, and
	 * whether the error (if any) is.
	 */
	#staleness(
		project: Project,
		results: ResultsState = this.results
	): { stale: boolean; errorStale: boolean } {
		if (this.#responseFingerprint === null && this.#errorFingerprint === null) {
			return { stale: false, errorStale: false };
		}
		const current = hydraulicFingerprint(project);
		const differs = (from: string | null) => from !== null && current !== from;
		const errorStale = !!results.error && differs(this.#errorFingerprint);
		const stale = results.response ? differs(this.#responseFingerprint) : errorStale;
		return { stale, errorStale };
	}

	#scheduleSync(): void {
		this.#cancelSync();
		this.#timer = setTimeout(() => this.flush(), this.#options.urlSyncDelayMs ?? URL_SYNC_DELAY_MS);
	}

	#cancelSync(): void {
		if (this.#timer !== null) clearTimeout(this.#timer);
		this.#timer = null;
	}

	#write(): void {
		(this.#options.writeUrl ?? defaultWriteUrl)(`${PROJECT_PATH}#${this.encoded}`);
	}

	/** True while a URL write is waiting for the debounce. */
	get syncPending(): boolean {
		return this.#timer !== null;
	}

	/** Write a pending URL change now (before sharing, or when the page is hidden). */
	flush(): void {
		if (this.#timer === null) return;
		this.#cancelSync();
		this.encoded = encodeProject(this.project);
		this.#write();
	}

	/** The current shareable link (writes any pending URL change first). */
	shareLink(): string {
		this.flush();
		return this.url;
	}

	/** Stop pending work (when the page is destroyed). */
	dispose(): void {
		this.#cancelSync();
		this.#solveSequence++;
	}

	/**
	 * Solve the current project. Results arriving after the project changed are kept but
	 * marked stale; a newer solve supersedes an older one. A failed solve keeps the previous
	 * response (it is stale only if the project changed since it was computed). On success the
	 * project records the method version it was solved with (traceability), without an undo step.
	 */
	async solve(options?: Partial<SolveOptions>): Promise<void> {
		const project = this.project;
		const fingerprint = hydraulicFingerprint(project);
		const sequence = ++this.#solveSequence;
		this.results = { ...this.results, solving: true };
		try {
			const solver = this.#options.solver ?? defaultClient();
			const response = await solver.solve(project, options);
			if (sequence !== this.#solveSequence) return;
			this.#responseFingerprint = fingerprint;
			this.#errorFingerprint = null;
			const stale = hydraulicFingerprint(this.project) !== fingerprint;
			this.results = { response, stale, solving: false, error: null, errorStale: false };
			if (!stale) this.#recordMethodVersion(response);
		} catch (error) {
			if (sequence !== this.#solveSequence) return;
			this.#errorFingerprint = fingerprint;
			// The previous response (if any) stays; it is stale only if the project changed since.
			const failed = { ...this.results, solving: false, error: toResultsError(error) };
			this.results = { ...failed, ...this.#staleness(this.project, failed) };
		}
	}

	#recordMethodVersion(response: SolveResponse): void {
		const version = response.solvedState?.methodVersion;
		if (!version || version === this.project.methodVersion) return;
		const next = { ...this.project, methodVersion: version };
		if (structuralProblems(next).length) return;
		// Not a hydraulic change: the results stay current and no undo step is added.
		this.project = deepFreeze(next);
		this.#scheduleSync();
	}

	/** Forget results and errors (e.g. after the user dismisses an error). */
	clearResults(): void {
		this.#solveSequence++;
		this.#responseFingerprint = null;
		this.#errorFingerprint = null;
		this.results = EMPTY_RESULTS;
	}
}

const STORE_KEY = Symbol('opensolve-pipe:project-store');

/** Make a store available to the components below (call during component initialisation). */
export function provideProjectStore(store: ProjectStore): ProjectStore {
	return setContext(STORE_KEY, store);
}

/** The store provided by an ancestor component. */
export function useProjectStore(): ProjectStore {
	const store = getContext<ProjectStore | undefined>(STORE_KEY);
	if (!store) throw new Error('No ProjectStore: call provideProjectStore in a parent component.');
	return store;
}
