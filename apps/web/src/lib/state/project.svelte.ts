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
 * - System curves (D10) are fetched on demand, per pump, for the exact project of the solve whose
 *   results are shown (`solvedProject`), and cached with that solve: a new solve, a load or
 *   clearing the results drops them, and a request for an older solve never fills the cache of a
 *   newer one. Requests go one at a time (the server runs one solve per client at a time), and a
 *   solve starting cancels them.
 * - A solve and a system curve can be cancelled (PRD §4.2): the request is aborted (the server
 *   stops the work of a client that has gone, D10), an answer that still arrives is dropped, and
 *   what was shown before stays, current or out of date by the same rules.
 * - Scenarios (PRD §3.8, proposal scenario-manager.md §6.9-6.10): the project holds the base case
 *   and its scenarios. `activeCase` is the case shown (null: the base case; page state, not in
 *   the link and not an undo step). Results, errors, staleness and system curves are kept per
 *   case; `results`, `solvedProject` and `systemCurves` are the active case's. A case's staleness
 *   key is the base's hydraulic fingerprint, plus that scenario's changes (utils/scenarios.ts
 *   caseKey): conservative, never showing stale results as current. solveAll() solves every case
 *   whose results are missing or out of date, one request at a time, from a snapshot. Each undo
 *   step records the case it was made in, and undo and redo show that case again. A base edit
 *   carries the scenarios' changes with the pipes it moves (utils/scenarios.ts carryChanges).
 * - Goal seek (PRD §3.9, proposal goal-seek.md §6.15): one run at a time, on a case, from the
 *   project exactly as sent. It never changes the project; its result (`goalSeek`) goes out of
 *   date by that case's staleness key, recomputed on every project change whether or not any case
 *   has results, and current again when undo returns to the project it ran on. One calculation
 *   request at a time per page (D10): `calculating` names the one running; while a goal seek runs
 *   solve() and solveAll() send nothing, and while a solve or Solve all runs runGoalSeek() sends
 *   nothing (refused, never dropped); only Cancel, load() and dispose() stop a request in flight.
 *   System curves wait for a goal seek, and one in flight is cancelled when it starts.
 * - Group curves (CLAUDE.md D21, proposal pump-groups.md §6.1) follow the system curves' rules:
 *   fetched on demand for the solve shown, per case and set of pumps (the sorted ids), on the same
 *   queue, cached with that solve and dropped by the next, cancelled by a solve or a goal seek.
 *   A group's system curve (slice 4b, §7) is kept beside its group curve, by the same rules, and
 *   asked for only after the group curve's answer for the same pumps and case
 *   (wantsGroupSystemCurve).
 *
 * Nothing is kept in browser storage; history lives only in this page.
 */
import { getContext, setContext } from 'svelte';
import {
	defaultClient,
	NetworkError,
	NotAStationError,
	NotFoundError,
	TopologyError,
	ValidationError
} from '../api/client';
import type {
	GoalSeekRequest,
	GoalSeekResponse,
	Project,
	PumpGroupCurveResponse,
	SolvedState,
	SolveOptions,
	SolveResponse,
	SystemCurveResponse,
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
import { markProjectCopy } from '../utils/identity';
import type { Calculating } from '../utils/goal-seek';
import { pressureControlOnly } from '../utils/pump-groups';
import { recordResultsProject } from '../utils/results';
import {
	applyScenario,
	carryChanges,
	caseKey,
	findScenario,
	scenariosOf,
	trackPipes,
	type CaseId
} from '../utils/scenarios';
import { referenceProblems, schemaProblems } from '../utils/validate';

export const MAX_HISTORY = 100;
export const URL_SYNC_DELAY_MS = 300;

export interface HistoryEntry {
	project: Project;
	/** What the change did, e.g. "Add pump" (for "Undo add pump"). */
	label: string;
	/** The case the change was made in (null: the base case): undo and redo show it again. */
	caseId: CaseId;
}

/**
 * What update() did. `notes` (only when there are any) say what a base edit did to scenario
 * changes (a removed pipe's changes went with it, a valve's setpoint changes were removed, ...).
 */
export type UpdateResult =
	{ ok: true; changed: boolean; notes?: string[] } | { ok: false; problems: string[] };

export type ResultsError =
	| { kind: 'topology'; message: string; issues: readonly TopologyIssue[] }
	| {
			kind: 'validation';
			message: string;
			details: readonly string[];
			/** The API's error code, e.g. 'FLUID_ERROR' (absent when it sent none). */
			code?: string;
			/** A 404 NOT_FOUND's issues, with the ids it did not find (a goal seek's elements). */
			issues?: readonly TopologyIssue[];
	  }
	| {
			kind: 'network';
			message: string;
			/** The API's error code, e.g. 'SERVER_BUSY' (absent when it sent none). */
			code?: string;
	  };

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
	 * True when the latest solve was cancelled before it answered (cancelSolve()): `response` and
	 * `error`, if any, are from earlier solves, as stale as the project's changes make them.
	 * Cleared when a solve starts.
	 */
	cancelled: boolean;
	/**
	 * True when the project changed, in a way that can change the results, after the solve that
	 * gave `error` (false without an error). With an error that is not stale and a stale
	 * `response`, the latest solve of the current project failed and the response is from an
	 * earlier version of it.
	 */
	errorStale: boolean;
}

export interface Solver {
	/**
	 * Solve (POST /api/v1/solve); `request.signal` aborts it (cancelled, or no longer wanted).
	 * `request.scenarioId` (only for a scenario) solves that scenario of the project.
	 */
	solve(
		project: Project,
		options?: Partial<SolveOptions>,
		request?: { signal?: AbortSignal; scenarioId?: string }
	): Promise<SolveResponse>;
	/**
	 * System curve of one pump (POST /api/v1/system-curve); absent when not available. A
	 * scenario's curve has `scenarioId`; a curve over a given flow range has flowMin and flowMax.
	 */
	systemCurve?(
		project: Project,
		pumpId: string,
		options?: { signal?: AbortSignal; scenarioId?: string; flowMin?: number; flowMax?: number }
	): Promise<SystemCurveResponse>;
	/**
	 * Goal seek (POST /api/v1/goal-seek); absent when not available. A scenario's run has
	 * `scenarioId`; `signal` aborts it (Cancel).
	 */
	goalSeek?(
		project: Project,
		setup: Pick<GoalSeekRequest, 'variables' | 'goals'>,
		request?: { signal?: AbortSignal; scenarioId?: string }
	): Promise<GoalSeekResponse>;
	/**
	 * The group curve of the station holding `pumpIds` (POST /api/v1/pump-group-curve), or with
	 * `curve: 'system'` its group system curve; absent when not available. A scenario's curve has
	 * `scenarioId`; `signal` aborts it.
	 */
	groupCurve?(
		project: Project,
		pumpIds: readonly string[],
		options?: { signal?: AbortSignal; scenarioId?: string; curve?: 'group' | 'system' }
	): Promise<PumpGroupCurveResponse>;
}

/** A goal seek as sent: the case it runs on and the request exactly as sent (SI). */
export interface GoalSeekRun {
	/** The case it ran on (null: the base case). */
	caseId: CaseId;
	request: GoalSeekRequest;
	/** The whole project as sent (request.project). */
	project: Project;
	/** The case's staleness key when sent (caseKey). */
	key: string;
	/** When it was sent, ms since the epoch. */
	startedAt: number;
}

/** A goal seek that answered (done) or failed (an error: topology, validation, not found, fluid, network). */
export interface GoalSeekFinished {
	status: 'done' | 'failed';
	run: GoalSeekRun;
	response: GoalSeekResponse | null;
	error: ResultsError | null;
	/** The run case's key differs from the run's now (or the scenario is gone). */
	stale: boolean;
	/** Where its values were applied: that case's key right after the edit (null: not applied). */
	applied: { caseId: CaseId; key: string } | null;
	/** The applied case's key is still `applied.key`: the project holds the values applied. */
	appliedCurrent: boolean;
}

/**
 * The page's goal seek: running or cancelled (with the result before it, shown again after a
 * cancel), finished, or none.
 */
export type GoalSeekState =
	| { status: 'running' | 'cancelled'; run: GoalSeekRun; previous: GoalSeekFinished | null }
	| GoalSeekFinished
	| null;

/** The finished goal seek of a state: itself, or the one before a run in flight or cancelled. */
export function finishedGoalSeek(state: GoalSeekState): GoalSeekFinished | null {
	if (!state) return null;
	return 'previous' in state ? state.previous : state;
}

/**
 * The system curve of one pump for the solve whose results are shown: being computed, computed
 * (points without a head say why), failed, or cancelled before it was computed, `by` a newer
 * solve starting, a goal seek starting, or by the user (cancelSystemCurve()).
 */
export type SystemCurveState =
	| { status: 'loading' }
	| { status: 'ready'; curve: SystemCurveResponse }
	| { status: 'error'; message: string }
	| { status: 'cancelled'; by: 'solve' | 'goalSeek' | 'user' };

/**
 * The group curve of a set of pumps for the solve whose results are shown (CLAUDE.md D21): being
 * computed, computed, refused (the pumps do not form a station: 422 NOT_A_STATION, every reason
 * an issue), failed, or cancelled before it was computed, `by` a newer solve, a goal seek or the
 * user (cancelGroupCurve()).
 */
export type GroupCurveState =
	| { status: 'loading' }
	| { status: 'ready'; response: PumpGroupCurveResponse }
	| { status: 'refused'; message: string; issues: readonly TopologyIssue[] }
	| { status: 'error'; message: string }
	| { status: 'cancelled'; by: 'solve' | 'goalSeek' | 'user' };

/**
 * The group system curve of a set of pumps for the solve whose results are shown (CLAUDE.md D21,
 * slice 4b): the rest of the network between the station's inlet and outlet at a grid of the
 * station's flows (the same response, curve 'system'). Its own state, with the group curve's
 * states: a refusal here is the API's for this solve too.
 */
export type GroupSystemCurveState = GroupCurveState;

/** The key of a group of pumps: its ids sorted, NUL-separated (the order ticked never matters). */
export function groupKey(pumpIds: readonly string[]): string {
	return [...pumpIds].sort().join('\u0000');
}

/**
 * The group system curve is asked for after this answer of the group curve (for the same pumps,
 * case and solve): a group curve with a duty, or a refusal for an active PRV or PSV inside only.
 * Not after a failure or a cancellation (asked again with the group curve), a refusal for another
 * reason (the API refuses both curves), or a case with no duty (its answer says the same for
 * both: no duty, no points).
 */
export function wantsGroupSystemCurve(state: GroupCurveState | undefined): boolean {
	if (state?.status === 'ready') return state.response.converged && state.response.duty !== null;
	return state?.status === 'refused' && pressureControlOnly(state.issues);
}

/** A system curve over a given flow range (m³/s): an overlay on another case's chart. */
export interface FlowRange {
	flowMin: number;
	flowMax: number;
}

/** Where a case's results stand, for the case chips (manager, Compare, the Case menu). */
export type CaseStatus =
	| 'solving'
	| 'waiting'
	| 'solved'
	| 'not_converged'
	| 'stale'
	| 'failed'
	| 'cancelled'
	| 'not_solved'
	| 'not_reached';

/** A Solve all run in progress: the cases it solves, in order, and the one being solved. */
export interface SolveRun {
	cases: readonly CaseId[];
	/** Index into `cases` of the case being solved. */
	index: number;
}

/** How the last Solve all ended, when it did not finish (null: it finished, or none ran). */
export type RunStop = { reason: 'network'; message: string } | { reason: 'cancelled' } | null;

interface CaseState {
	results: ResultsState;
	/** The project exactly as sent for the solve of `results.response`. */
	solvedProject: Project | null;
	/** The project exactly as sent for the solve that gave `results.error`. */
	errorProject: Project | null;
	/** System curves by pump id (or pump id and flow range), for the solve of `results.response`. */
	systemCurves: Readonly<Record<string, SystemCurveState>>;
	/** Group curves by groupKey(), for the solve of `results.response`. */
	groupCurves: Readonly<Record<string, GroupCurveState>>;
	/** Group system curves by groupKey(), for the solve of `results.response`. */
	groupSystemCurves: Readonly<Record<string, GroupSystemCurveState>>;
	/** Staleness keys of the projects `results.response` and `results.error` came from. */
	responseKey: string | null;
	errorKey: string | null;
	/** A Solve all run stopped (after a network error) before it reached this case. */
	notReached: boolean;
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
	cancelled: false,
	errorStale: false
});

const EMPTY_CASE: CaseState = Object.freeze({
	results: EMPTY_RESULTS,
	solvedProject: null,
	errorProject: null,
	systemCurves: Object.freeze({}),
	groupCurves: Object.freeze({}),
	groupSystemCurves: Object.freeze({}),
	responseKey: null,
	errorKey: null,
	notReached: false
});

/** The key of a case in the per-case maps: '' for the base (scenario ids are never empty). */
const slot = (caseId: CaseId) => caseId ?? '';
const caseOfSlot = (key: string): CaseId => (key === '' ? null : key);

/** The key of a system curve in a case's map: the pump id, with the flow range of an overlay. */
const curveKey = (pumpId: string, range?: FlowRange) =>
	range ? `${pumpId}\u0000${range.flowMin}\u0000${range.flowMax}` : pumpId;

/** The group curves of a case, and its group system curves (CaseState's maps). */
type GroupCurveKind = 'group' | 'system';
const GROUP_MAPS = { group: 'groupCurves', system: 'groupSystemCurves' } as const;

/**
 * A group curve's request key among the curve requests, and a group system curve's (never a pump
 * id: ids have no U+0001 or U+0002).
 */
const groupRequestKey = (key: string, kind: GroupCurveKind = 'group') =>
	`${kind === 'group' ? '\u0001' : '\u0002'}${key}`;

/** Freeze `value` and everything in it (stored projects are never mutated). */
export function deepFreeze<T>(value: T): T {
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

/** Structural problems of a project (schema, then the port graph), as update() checks them. */
export function structuralProblems(project: unknown): string[] {
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
			...(error.code ? { code: error.code } : {}),
			...(error instanceof NotFoundError ? { issues: error.issues } : {})
		};
	}
	if (error instanceof NetworkError) {
		return { kind: 'network', message: error.message, ...(error.code ? { code: error.code } : {}) };
	}
	return {
		kind: 'network',
		message: error instanceof Error ? error.message : 'The solve failed unexpectedly.'
	};
}

export class ProjectStore {
	/** The current project (the base case and its scenarios). Never mutate it: use update(). */
	project = $state.raw<Project>(createEmptyProject());
	/**
	 * The case shown and edited (null: the base case). Page state: not in the link and not an
	 * undo step (setCase()); a link opens on the base case.
	 */
	activeCase = $state.raw<CaseId>(null);
	/** The Solve all run in progress (null: none). */
	run = $state.raw<SolveRun | null>(null);
	/** How the last Solve all ended when it did not finish (null: it finished, or none ran). */
	runStop = $state.raw<RunStop>(null);
	/** URL-fragment encoding of the project as of the last URL write. */
	encoded = $state.raw('');
	/**
	 * The calculation-method version the project carried when it was loaded (empty: never
	 * solved). solve() records the version of each new solve in the project, so this keeps the
	 * one the link was shared with, for the results' method-version notice.
	 */
	loadedMethodVersion = $state.raw('');
	/** The page's goal seek (null: none since the project was loaded). */
	goalSeek = $state.raw<GoalSeekState>(null);

	/** Results, errors, staleness and system curves of each case (slot()). */
	#cases = $state.raw<Readonly<Record<string, CaseState>>>({});
	#undo = $state.raw<readonly HistoryEntry[]>([]);
	#redo = $state.raw<readonly HistoryEntry[]>([]);
	#mergeable = false;
	#solveSequence = 0;
	#timer: ReturnType<typeof setTimeout> | null = null;
	/** Aborts the solve request in flight (cancelled, superseded, or its results no longer wanted). */
	#solveRequest: AbortController | null = null;
	/** The case the solve in flight is for (undefined: none in flight). */
	#solvingCase = $state.raw<CaseId | undefined>(undefined);
	/** Resolves when the solve in flight ends or is dropped (curve requests wait for it). */
	#solveDone: Promise<void> = Promise.resolve();
	#endSolve: () => void = () => {};
	/** The Solve all run in progress, to stop it (cancelled or superseded). */
	#runToken: object | null = null;
	/** Resolves when the run in progress ends (curve requests wait for it). */
	#runDone: Promise<void> = Promise.resolve();
	#endRun: () => void = () => {};
	/** The system-curve requests in flight or queued, to abort them. */
	#curveRequests: readonly { caseKey: string; key: string; controller: AbortController }[] = [];
	/** The system-curve requests, one after the other. */
	#curveQueue: Promise<unknown> = Promise.resolve();
	/** Case projects of solved projects (for the inputs a case was solved with). */
	#caseInputs = new WeakMap<Project, Record<string, Project>>();
	/** Called after every load(): page state of the project shown resets (onLoad()). */
	#loadListeners: (() => void)[] = [];
	/** Aborts the goal seek in flight. */
	#goalSeekRequest: AbortController | null = null;
	#goalSeekSequence = 0;
	/** Resolves when the goal seek in flight ends (curve requests wait for it). */
	#goalSeekDone: Promise<void> = Promise.resolve();
	#endGoalSeek: () => void = () => {};
	readonly #options: ProjectStoreOptions;

	constructor(project?: Project, options: ProjectStoreOptions = {}) {
		this.#options = options;
		this.load(project ?? createEmptyProject({ now: this.#now() }));
	}

	/** The latest solve results of the active case. */
	get results(): ResultsState {
		return this.#case(this.activeCase).results;
	}

	/**
	 * The project exactly as sent for the solve of `results.response` (null without one): system
	 * curves are computed for it, never for a newer, edited project. For a scenario it is the
	 * whole project sent (base and scenarios); caseInputs() gives the case as solved.
	 */
	get solvedProject(): Project | null {
		return this.#case(this.activeCase).solvedProject;
	}

	/** System curves by pump id, for the solve of `results.response` (see systemCurve()). */
	get systemCurves(): Readonly<Record<string, SystemCurveState>> {
		return this.#case(this.activeCase).systemCurves;
	}

	/**
	 * A case's system curves (read only), for the solve of its latest response: its slot, as
	 * `systemCurves` is the active case's. Keyed by pump id, or for a curve over a given flow range
	 * (an overlay on another case's chart) by the pump id, NUL, flowMin, NUL and flowMax (m³/s). The
	 * export lists them as computed and never computes one (proposal export.md §2.1).
	 */
	systemCurvesFor(caseId: CaseId): Readonly<Record<string, SystemCurveState>> {
		return this.#case(caseId).systemCurves;
	}

	/** The latest solved state of the active case, if any (check results.stale before relying on it). */
	get solved(): SolvedState | null {
		return this.results.response?.solvedState ?? null;
	}

	/**
	 * The case whose solve is in flight, alone or in a Solve all run (undefined: none). It need not
	 * be the case shown: a solve goes on after a case switch, and Cancel stops it.
	 */
	get solvingCase(): CaseId | undefined {
		return this.#solvingCase;
	}

	/** A goal seek is in flight. */
	get goalSeekRunning(): boolean {
		return this.goalSeek?.status === 'running';
	}

	/**
	 * What the page is calculating (null: nothing): a goal seek, a Solve all run or one solve. Every
	 * control that starts a solve or a goal seek reads it (utils/goal-seek.ts calculatingReason).
	 */
	get calculating(): Calculating {
		if (this.goalSeekRunning) return 'goalSeek';
		if (this.run) return 'solveAll';
		return this.#solvingCase !== undefined ? 'solve' : null;
	}

	/** The latest results of a case (the base: null). */
	resultsFor(caseId: CaseId): ResultsState {
		return this.#case(caseId).results;
	}

	/** The project as sent for a case's latest response or error (null: none). */
	sentProjectFor(caseId: CaseId, which: 'response' | 'error' = 'response'): Project | null {
		const state = this.#case(caseId);
		return which === 'response' ? state.solvedProject : state.errorProject;
	}

	/**
	 * The case's project as it was solved (a scenario applied to the base sent), for inputs shown
	 * as entered (an assigned flow). Null without a response.
	 */
	caseInputs(caseId: CaseId = this.activeCase): Project | null {
		const sent = this.#case(caseId).solvedProject;
		if (!sent || caseId === null) return sent;
		let byCase = this.#caseInputs.get(sent);
		if (!byCase) {
			byCase = {};
			this.#caseInputs.set(sent, byCase);
		}
		byCase[caseId] ??= deepFreeze(applyScenario(sent, caseId).project);
		return byCase[caseId];
	}

	/** Every case of the project in order: the base case (null), then the scenarios. */
	get caseIds(): CaseId[] {
		return [null, ...scenariosOf(this.project).map((s) => s.id)];
	}

	/** Where a case's results stand (see CaseStatus). */
	caseStatus(caseId: CaseId): CaseStatus {
		const run = this.run;
		if (run) {
			const at = run.cases.indexOf(caseId);
			if (at === run.index && this.#case(caseId).results.solving) return 'solving';
			if (at > run.index) return 'waiting';
		}
		const state = this.#case(caseId);
		const r = state.results;
		if (r.solving) return 'solving';
		if (r.response && !r.stale) {
			return r.response.success && r.response.solvedState.converged ? 'solved' : 'not_converged';
		}
		if (r.error && !r.errorStale) return 'failed';
		if (state.notReached) return 'not_reached';
		if (r.response || r.error) return 'stale';
		if (r.cancelled) return 'cancelled';
		return 'not_solved';
	}

	/**
	 * Whether Solve all solves a case: its results are missing, out of date or cancelled, or its
	 * last solve failed with a network error. A case with current results, or with a current
	 * topology or validation error, is skipped: the solver is deterministic.
	 */
	needsSolve(caseId: CaseId): boolean {
		const r = this.#case(caseId).results;
		if (r.response && !r.stale) return false;
		if (r.error && r.error.kind !== 'network' && !r.errorStale) return false;
		return true;
	}

	/** The cases Solve all would solve now, in order: the base first, then the scenarios. */
	casesToSolve(): CaseId[] {
		return this.caseIds.filter((id) => this.needsSolve(id));
	}

	/**
	 * The cases whose latest solve of the project as it is failed with their own error (topology,
	 * validation or fluid), in order: Solve all skips them until their inputs change (needsSolve).
	 */
	casesWithErrors(): CaseId[] {
		return this.caseIds.filter((id) => {
			const r = this.#case(id).results;
			return !(r.response && !r.stale) && !!r.error && r.error.kind !== 'network' && !r.errorStale;
		});
	}

	/**
	 * Call `listener` after every load() (another project opened in the page), so that page state
	 * about the project shown resets as a reload would. Returns a function that removes it.
	 */
	onLoad(listener: () => void): () => void {
		this.#loadListeners = [...this.#loadListeners, listener];
		return () => {
			this.#loadListeners = this.#loadListeners.filter((l) => l !== listener);
		};
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

	#case(caseId: CaseId): CaseState {
		return this.#cases[slot(caseId)] ?? EMPTY_CASE;
	}

	#setCase(caseId: CaseId, change: Partial<CaseState>): void {
		this.#cases = { ...this.#cases, [slot(caseId)]: { ...this.#case(caseId), ...change } };
	}

	/** The staleness key of a case in `project` (null: the scenario no longer exists). */
	#key(project: Project, caseId: CaseId, fingerprint = hydraulicFingerprint(project)) {
		return caseKey(project, caseId, fingerprint);
	}

	/**
	 * Show another case (null: the base case). Page state: no undo step, no URL change. An id
	 * that is not a scenario of the project shows the base case.
	 */
	setCase(caseId: CaseId): void {
		this.activeCase = caseId !== null && findScenario(this.project, caseId) ? caseId : null;
	}

	/**
	 * Replace the project and reset undo/redo and results (opening a link, an example or a new
	 * project). The URL is written only when `writeUrl` is set; a project opened from the URL is
	 * already there. It opens on the base case. Throws when the project is not valid.
	 */
	load(project: Project, options: { writeUrl?: boolean } = {}): void {
		const problems = structuralProblems(project);
		if (problems.length) throw new Error(`Cannot load an invalid project: ${problems[0]}`);
		this.#cancelSync();
		this.#stopRun();
		this.project = deepFreeze(structuredClone(project));
		this.activeCase = null;
		this.runStop = null;
		this.loadedMethodVersion = this.project.methodVersion;
		this.#undo = [];
		this.#redo = [];
		this.#mergeable = false;
		this.#dropSolve();
		this.#dropGoalSeek();
		this.goalSeek = null;
		this.#abortCurveRequests();
		this.#cases = {};
		this.encoded = encodeProject(this.project);
		if (options.writeUrl) this.#write();
		for (const listener of this.#loadListeners) listener();
	}

	/**
	 * Apply a change. `change` receives a mutable copy of the project and may modify it or
	 * return a new project (the graph operations in utils/edit.ts return one). The result must
	 * be valid; otherwise nothing changes and the problems are returned. A change that leaves
	 * the project as it was adds no undo step. Scenario changes follow the pipes the change moves
	 * (carryChanges), and the result's notes say what happened to them.
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
		// The draft's pipes are the current ones (identity.ts): scenario changes and the results
		// shown in Build follow them through the edit.
		markProjectCopy(draft, current);
		const tracker = scenariosOf(current).length ? trackPipes(current, draft) : null;
		let next: Project;
		let notes: string[] = [];
		try {
			next = change(draft) ?? draft;
			if (tracker) ({ project: next, notes } = carryChanges(current, tracker, next));
			if (canonicalJson(next) === canonicalJson(current)) return { ok: true, changed: false };
		} catch (error) {
			return { ok: false, problems: [error instanceof Error ? error.message : String(error)] };
		}
		next = { ...next, metadata: { ...next.metadata, modified: this.#now() } };
		const problems = structuralProblems(next);
		if (problems.length) return { ok: false, problems };

		const previous = this.#undo[this.#undo.length - 1];
		const sameCase = previous?.caseId === this.activeCase;
		if (!(options.merge && this.#mergeable && previous?.label === label && sameCase)) {
			const undo = [...this.#undo, { project: current, label, caseId: this.activeCase }];
			this.#undo = undo.slice(Math.max(0, undo.length - (this.#options.maxHistory ?? MAX_HISTORY)));
		}
		this.#redo = [];
		this.#mergeable = true;
		this.#replace(next);
		return notes.length ? { ok: true, changed: true, notes } : { ok: true, changed: true };
	}

	/**
	 * Revert the last change, and show the case it was made in (the base case when that scenario
	 * is not in the restored project). Returns false when there is nothing to undo.
	 */
	undo(): boolean {
		const entry = this.#undo[this.#undo.length - 1];
		if (!entry) return false;
		this.#undo = this.#undo.slice(0, -1);
		this.#redo = [
			...this.#redo,
			{ project: this.project, label: entry.label, caseId: entry.caseId }
		];
		this.#mergeable = false;
		this.#replace(entry.project);
		this.setCase(entry.caseId);
		return true;
	}

	/** Re-apply the last undone change, in the case it was made in. False when there is none. */
	redo(): boolean {
		const entry = this.#redo[this.#redo.length - 1];
		if (!entry) return false;
		this.#redo = this.#redo.slice(0, -1);
		this.#undo = [
			...this.#undo,
			{ project: this.project, label: entry.label, caseId: entry.caseId }
		];
		this.#mergeable = false;
		this.#replace(entry.project);
		this.setCase(entry.caseId);
		return true;
	}

	#replace(project: Project): void {
		this.project = deepFreeze(project);
		if (this.activeCase !== null && !findScenario(project, this.activeCase)) this.activeCase = null;
		const fingerprint = hydraulicFingerprint(project);
		// Apart from #restale, which returns at once when no case has results: a goal seek needs
		// none (proposal goal-seek.md §6.11).
		this.#restaleGoalSeek(project, fingerprint);
		this.#restale(project, fingerprint);
		this.#scheduleSync();
	}

	/**
	 * Recompute the goal seek's staleness and applied state for `project`: stale when its case's
	 * key differs from the run's (or the scenario is gone); applied while the applied case's key is
	 * the one recorded right after Apply.
	 */
	#restaleGoalSeek(project: Project, fingerprint: string): void {
		const state = this.goalSeek;
		if (!state) return;
		const finished = finishedGoalSeek(state);
		if (!finished) return;
		const next = this.#goalSeekStaleness(finished, project, fingerprint);
		if (next.stale === finished.stale && next.appliedCurrent === finished.appliedCurrent) return;
		const updated = { ...finished, ...next };
		this.goalSeek = 'previous' in state ? { ...state, previous: updated } : updated;
	}

	#goalSeekStaleness(
		finished: Pick<GoalSeekFinished, 'run' | 'applied'>,
		project: Project,
		fingerprint = hydraulicFingerprint(project)
	): { stale: boolean; appliedCurrent: boolean } {
		const stale = this.#key(project, finished.run.caseId, fingerprint) !== finished.run.key;
		const applied = finished.applied;
		const appliedCurrent =
			!!applied && this.#key(project, applied.caseId, fingerprint) === applied.key;
		return { stale, appliedCurrent };
	}

	/**
	 * Recompute every case's staleness for `project` (one fingerprint for all cases). A scenario
	 * that is no longer in the project drops its results.
	 */
	#restale(project: Project, fingerprint = hydraulicFingerprint(project)): void {
		const keys = Object.keys(this.#cases);
		if (!keys.length) return;
		let cases: Record<string, CaseState> | null = null;
		for (const key of keys) {
			const state = this.#cases[key] as CaseState;
			const caseKey = this.#key(project, caseOfSlot(key), fingerprint);
			if (caseKey === null) {
				cases ??= { ...this.#cases };
				delete cases[key];
				this.#abortCurveRequests(key);
				continue;
			}
			const { stale, errorStale } = this.#staleness(state, caseKey);
			if (stale !== state.results.stale || errorStale !== state.results.errorStale) {
				cases ??= { ...this.#cases };
				cases[key] = { ...state, results: { ...state.results, stale, errorStale } };
			}
		}
		if (cases) this.#cases = cases;
	}

	/**
	 * Whether the results shown (the response, else the error) are for another project, and
	 * whether the error (if any) is: compared by the case's staleness key `current`.
	 */
	#staleness(
		state: CaseState,
		current: string | null,
		results: ResultsState = state.results
	): { stale: boolean; errorStale: boolean } {
		if (state.responseKey === null && state.errorKey === null) {
			return { stale: false, errorStale: false };
		}
		const differs = (from: string | null) => from !== null && current !== from;
		const errorStale = !!results.error && differs(state.errorKey);
		const stale = results.response ? differs(state.responseKey) : errorStale;
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
		this.#stopRun();
		this.#dropSolve();
		this.#dropGoalSeek();
		this.#abortCurveRequests();
	}

	/**
	 * Solve the active case of the current project (or `caseId`). Results arriving after the
	 * project changed are kept but marked stale; a newer solve supersedes an older one (whose
	 * request is aborted, as it is when the project is replaced or the results cleared). A failed
	 * solve keeps the previous response (it is stale only if the project changed since it was
	 * computed). On success the project records the method version it was solved with
	 * (traceability), without an undo step. A scenario's request carries its id; the base's is the
	 * plain request.
	 */
	async solve(options?: Partial<SolveOptions>, caseId: CaseId = this.activeCase): Promise<void> {
		if (this.goalSeekRunning) return; // one request at a time: only Cancel stops a goal seek
		this.#stopRun();
		await this.#solveCase(caseId, this.project, options, false);
	}

	/**
	 * Solve every case whose results are missing or out of date (casesToSolve()), the base first,
	 * then the scenarios in order, one request at a time, all from the project as it is now. A
	 * topology, validation or fluid error belongs to its case and the run goes on; a network error
	 * (no connection, a timeout, 429, 503) stops it, and the cases not reached say so: Solve all
	 * again resumes with them. cancelSolve() stops the run.
	 */
	async solveAll(options?: Partial<SolveOptions>): Promise<void> {
		if (this.run || this.goalSeekRunning) return;
		const project = this.project;
		const cases = this.casesToSolve();
		if (!cases.length) return;
		this.#dropSolve();
		this.#cancelSystemCurves();
		const token = {};
		this.#runToken = token;
		this.#runDone = new Promise((resolve) => (this.#endRun = resolve));
		this.runStop = null;
		for (const id of cases) if (this.#case(id).notReached) this.#setCase(id, { notReached: false });
		this.run = { cases, index: 0 };
		try {
			for (const [index, caseId] of cases.entries()) {
				if (this.#runToken !== token) return;
				this.run = { cases, index };
				const outcome = await this.#solveCase(caseId, project, options, true);
				if (this.#runToken !== token || outcome === 'superseded') return;
				if (outcome === 'network') {
					const error = this.#case(caseId).results.error;
					this.runStop = { reason: 'network', message: error?.message ?? '' };
					for (const rest of cases.slice(index + 1)) {
						if (rest === null || findScenario(this.project, rest)) {
							this.#setCase(rest, { notReached: true });
						}
					}
					return;
				}
			}
		} finally {
			if (this.#runToken === token) this.#stopRun();
		}
	}

	/** End the Solve all run in progress, if any (its request in flight is not touched). */
	#stopRun(): void {
		if (!this.#runToken && !this.run) return;
		this.#runToken = null;
		this.run = null;
		this.#endRun();
	}

	/**
	 * Solve one case of `project`. Returns how it ended: 'ok' (a response, converged or not),
	 * 'error' (topology, validation or fluid: the case's own), 'network' (no answer, or one that
	 * is not about the project) or 'superseded' (cancelled, or another solve started).
	 */
	async #solveCase(
		caseId: CaseId,
		project: Project,
		options: Partial<SolveOptions> | undefined,
		inRun: boolean
	): Promise<'ok' | 'error' | 'network' | 'superseded'> {
		const key = this.#key(project, caseId);
		if (key === null) return 'error';
		this.#dropSolve();
		const sequence = this.#solveSequence;
		const request = new AbortController();
		this.#solveRequest = request;
		this.#solvingCase = caseId;
		const ended = new Promise<void>((resolve) => (this.#endSolve = resolve));
		this.#solveDone = ended;
		const before = this.#case(caseId);
		this.#setCase(caseId, {
			results: { ...before.results, solving: true, cancelled: false },
			notReached: false
		});
		if (!inRun) this.#cancelSystemCurves();
		try {
			const solver = this.#options.solver ?? defaultClient();
			// No system curves with the solve (D10): the pump chart fetches its own.
			const response = await solver.solve(
				project,
				{ includeSystemCurve: false, ...options },
				caseId === null
					? { signal: request.signal }
					: { signal: request.signal, scenarioId: caseId }
			);
			if (sequence !== this.#solveSequence) return 'superseded';
			const current = this.#key(this.project, caseId);
			if (current === null) {
				this.#dropCase(caseId);
				return 'ok';
			}
			const stale = current !== key;
			this.#forgetSystemCurves(caseId);
			this.#setCase(caseId, {
				responseKey: key,
				errorKey: null,
				solvedProject: project,
				results: {
					response,
					stale,
					solving: false,
					error: null,
					cancelled: false,
					errorStale: false
				}
			});
			// Result tables name its connections from the project as sent once it is out of date.
			recordResultsProject(response.solvedState, () => {
				const kept = this.#case(caseId).results;
				return kept.response === response && !kept.stale ? null : project;
			});
			if (!stale) this.#recordMethodVersion(response);
			return 'ok';
		} catch (error) {
			if (sequence !== this.#solveSequence) return 'superseded';
			const current = this.#key(this.project, caseId);
			if (current === null) {
				this.#dropCase(caseId);
				return 'error';
			}
			const state = { ...this.#case(caseId), errorKey: key, errorProject: project };
			// The previous response (if any) stays; it is stale only if the project changed since.
			const failed = { ...state.results, solving: false, error: toResultsError(error) };
			this.#setCase(caseId, {
				...state,
				results: { ...failed, ...this.#staleness(state, current, failed) }
			});
			return failed.error.kind === 'network' ? 'network' : 'error';
		} finally {
			if (this.#solveRequest === request) {
				this.#solveRequest = null;
				this.#solvingCase = undefined;
				// After the case's new response (or error) is set: a curve asked for meanwhile goes
				// only if its solve is still the latest.
				this.#endSolve();
			}
		}
	}

	#dropCase(caseId: CaseId): void {
		const cases = { ...this.#cases };
		delete cases[slot(caseId)];
		this.#cases = cases;
	}

	/**
	 * Cancel the solve in progress (PRD §4.2), or the Solve all run: the request is aborted, and
	 * its answer, if one still arrives, is dropped. The response and error shown before it started
	 * stay, each current or stale as the project's changes since make it, and `results.cancelled`
	 * says the latest solve gave nothing. In a run, cases already solved keep their new results and
	 * the rest are not solved. System curves it cancelled when it started stay cancelled. A goal
	 * seek running is cancelled (cancelGoalSeek(): the header's Cancel stops it too). Returns false
	 * when nothing is being solved.
	 */
	cancelSolve(): boolean {
		if (this.cancelGoalSeek()) return true;
		const running = !!this.run;
		if (!running && this.#solvingCase === undefined) return false;
		if (running) {
			this.#stopRun();
			this.runStop = { reason: 'cancelled' };
		}
		this.#dropSolve();
		return true;
	}

	/**
	 * Forget the solve in flight, if any: its answer is dropped and its request aborted, and its
	 * case says the solve was cancelled before it finished.
	 */
	#dropSolve(): void {
		this.#solveSequence++;
		this.#solveRequest?.abort();
		this.#solveRequest = null;
		this.#endSolve(); // curve requests waiting for it go on (or wait for the next one)
		const caseId = this.#solvingCase;
		this.#solvingCase = undefined;
		if (caseId === undefined) return;
		const results = this.#case(caseId).results;
		if (results.solving)
			this.#setCase(caseId, { results: { ...results, solving: false, cancelled: true } });
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

	/**
	 * Run a goal seek (POST /api/v1/goal-seek) of case `caseId` with `request` (its project is the
	 * stored project as it is now, with the scenario's id for a scenario). Returns false, sending
	 * nothing, while a solve, a Solve all run or another goal seek runs: one request at a time
	 * (D10), refused rather than dropped. System curves in flight are cancelled, and new ones wait
	 * for it. Its answer, or its error, becomes `goalSeek`; one that arrives after a cancel or a
	 * load() is dropped. The project never changes.
	 */
	async runGoalSeek(
		request: GoalSeekRequest,
		caseId: CaseId = request.scenarioId ?? null
	): Promise<boolean> {
		if (this.calculating !== null) return false;
		const key = this.#key(request.project, caseId);
		if (key === null) return false;
		this.#cancelSystemCurves('goalSeek');
		const sequence = ++this.#goalSeekSequence;
		const controller = new AbortController();
		this.#goalSeekRequest = controller;
		this.#goalSeekDone = new Promise((resolve) => (this.#endGoalSeek = resolve));
		const run: GoalSeekRun = {
			caseId,
			request,
			project: request.project,
			key,
			startedAt: Date.now()
		};
		const previous = finishedGoalSeek(this.goalSeek);
		this.goalSeek = { status: 'running', run, previous };
		const finish = (response: GoalSeekResponse | null, error: ResultsError | null) => {
			const done = { run, applied: null };
			this.goalSeek = {
				status: response ? 'done' : 'failed',
				...done,
				response,
				error,
				...this.#goalSeekStaleness(done, this.project)
			};
		};
		try {
			const solver = this.#options.solver ?? defaultClient();
			if (!solver.goalSeek) {
				throw new NetworkError('Goal seek is not available from this calculation server.');
			}
			const response = await solver.goalSeek(
				request.project,
				{ variables: request.variables, goals: request.goals },
				caseId === null
					? { signal: controller.signal }
					: { signal: controller.signal, scenarioId: caseId }
			);
			if (sequence === this.#goalSeekSequence) finish(response, null);
		} catch (error) {
			if (sequence === this.#goalSeekSequence) finish(null, toResultsError(error));
		} finally {
			if (this.#goalSeekRequest === controller) {
				this.#goalSeekRequest = null;
				this.#endGoalSeek();
			}
		}
		return true;
	}

	/**
	 * Cancel the goal seek in flight: its request is aborted (the server stops at its next check,
	 * D10), an answer that still arrives is dropped, and the result before it is kept (shown again,
	 * current or out of date as before). Returns false when none is running.
	 */
	cancelGoalSeek(): boolean {
		const state = this.goalSeek;
		if (state?.status !== 'running') return false;
		this.#dropGoalSeek();
		this.goalSeek = { ...state, status: 'cancelled' };
		return true;
	}

	/** Abort the goal seek in flight, if any; its answer is dropped. */
	#dropGoalSeek(): void {
		this.#goalSeekSequence++;
		this.#goalSeekRequest?.abort();
		this.#goalSeekRequest = null;
		this.#endGoalSeek();
	}

	/**
	 * Record that the latest goal seek's values were applied to case `caseId` (right after the
	 * edit): its result says so while that case's key stays as it is now. A result shown again
	 * after a cancelled run takes the cancelled state's place: the project changed since.
	 */
	markGoalSeekApplied(caseId: CaseId): void {
		const state = this.goalSeek;
		if (state?.status === 'running') return;
		const finished = finishedGoalSeek(state);
		if (finished?.status !== 'done') return;
		const key = this.#key(this.project, caseId);
		if (key === null) return;
		this.goalSeek = { ...finished, applied: { caseId, key }, appliedCurrent: true };
	}

	/** Forget the results and errors of every case (e.g. after the user dismisses an error). */
	clearResults(): void {
		this.#stopRun();
		this.#dropSolve();
		this.#abortCurveRequests();
		this.#cases = {};
		this.runStop = null;
	}

	/** The case whose latest response is `response`, if any. */
	#caseOf(response: SolveResponse | null): CaseId | undefined {
		if (!response) return undefined;
		for (const [key, state] of Object.entries(this.#cases)) {
			if (state.results.response === response) return caseOfSlot(key);
		}
		return undefined;
	}

	/**
	 * The system curve of `pumpId` for the solve `response`, if it has been requested: undefined
	 * when it has not, or when `response` is not the latest of its case (a curve is never shown
	 * with another solve's results). `range`: the curve over that flow range (an overlay).
	 */
	systemCurve(
		response: SolveResponse | null,
		pumpId: string,
		range?: FlowRange
	): SystemCurveState | undefined {
		const caseId = this.#caseOf(response);
		if (caseId === undefined) return undefined;
		return this.#case(caseId).systemCurves[curveKey(pumpId, range)];
	}

	/**
	 * Compute the system curve of `pumpId` for the latest solve of a case (default: the active
	 * one), from the project exactly as solved (POST /api/v1/system-curve, with the scenario's id),
	 * unless it is cached; with `retry`, again after a failure or a cancellation; with `range`,
	 * over that flow range (an overlay on another case's chart, on its flow grid). Requests run one
	 * at a time, after any Solve all run, goal seek or solve in flight; one whose solve is no
	 * longer its case's latest, or that is cancelled, is dropped (or aborted) and never fills the
	 * cache.
	 */
	loadSystemCurve(
		pumpId: string,
		options: { retry?: boolean; caseId?: CaseId; range?: FlowRange } = {}
	): void {
		const caseId = options.caseId === undefined ? this.activeCase : options.caseId;
		const state = this.#case(caseId);
		const response = state.results.response;
		const project = state.solvedProject;
		if (!response || !project) return;
		const key = curveKey(pumpId, options.range);
		const known = state.systemCurves[key];
		const again = known?.status === 'error' || known?.status === 'cancelled';
		if (known && !(options.retry && again)) return;
		const solver = this.#options.solver ?? defaultClient();
		const set = (next: SystemCurveState) => {
			const now = this.#case(caseId);
			if (now.results.response !== response) return; // another solve's results by now
			this.#setCase(caseId, { systemCurves: { ...now.systemCurves, [key]: next } });
		};
		if (!solver.systemCurve) {
			set({ status: 'error', message: 'System curves are not available from this server.' });
			return;
		}
		set({ status: 'loading' });
		const controller = new AbortController();
		this.#abortCurveRequests(slot(caseId), key);
		this.#curveRequests = [...this.#curveRequests, { caseKey: slot(caseId), key, controller }];
		const { signal } = controller;
		const request = async () => {
			try {
				await this.#runDone; // one request at a time: after a Solve all run
				await this.#goalSeekDone; // and after a goal seek
				// And after a solve in flight (dropped unsent if it replaced the response).
				if (this.#solvingCase !== undefined) await this.#solveDone;
				if (signal.aborted || this.#case(caseId).results.response !== response) return;
				const curve = await solver.systemCurve!(project, pumpId, {
					signal,
					...(caseId === null ? {} : { scenarioId: caseId }),
					...(options.range ?? {})
				});
				if (!signal.aborted) set({ status: 'ready', curve });
			} catch (error) {
				if (signal.aborted) return; // cancelled: whoever cancelled it says so
				set({
					status: 'error',
					message: error instanceof Error ? error.message : 'The system curve failed.'
				});
			} finally {
				this.#curveRequests = this.#curveRequests.filter((r) => r.controller !== controller);
			}
		};
		this.#curveQueue = this.#curveQueue.then(request, request);
	}

	/**
	 * Cancel the system curve of `pumpId` while it is computed or waits its turn (the pump chart's
	 * Cancel): its request is aborted, an answer that still arrives is dropped, and the curve is
	 * marked cancelled by the user until it is asked for again (loadSystemCurve with `retry`).
	 * Other pumps' requests go on.
	 */
	cancelSystemCurve(pumpId: string, options: { caseId?: CaseId; range?: FlowRange } = {}): void {
		const caseId = options.caseId === undefined ? this.activeCase : options.caseId;
		const key = curveKey(pumpId, options.range);
		const state = this.#case(caseId);
		if (state.systemCurves[key]?.status !== 'loading') return;
		this.#abortCurveRequests(slot(caseId), key);
		this.#setCase(caseId, {
			systemCurves: { ...state.systemCurves, [key]: { status: 'cancelled', by: 'user' } }
		});
	}

	/**
	 * The group curve of `pumpIds` (any order) for the solve `response`, if it has been requested:
	 * undefined when it has not, or when `response` is not the latest of its case (a curve is
	 * never shown with another solve's results).
	 */
	groupCurve(
		response: SolveResponse | null,
		pumpIds: readonly string[]
	): GroupCurveState | undefined {
		return this.#groupState('group', response, pumpIds);
	}

	/**
	 * The group system curve of `pumpIds` (any order) for the solve `response`, if it has been
	 * requested, by groupCurve()'s rules.
	 */
	groupSystemCurve(
		response: SolveResponse | null,
		pumpIds: readonly string[]
	): GroupSystemCurveState | undefined {
		return this.#groupState('system', response, pumpIds);
	}

	#groupState(
		kind: GroupCurveKind,
		response: SolveResponse | null,
		pumpIds: readonly string[]
	): GroupCurveState | undefined {
		const caseId = this.#caseOf(response);
		if (caseId === undefined) return undefined;
		return this.#case(caseId)[GROUP_MAPS[kind]][groupKey(pumpIds)];
	}

	/**
	 * Compute the group curve of `pumpIds` for the latest solve of a case (default: the active
	 * one), from the project exactly as solved (POST /api/v1/pump-group-curve, with the scenario's
	 * id), unless it is cached; with `retry`, again after a failure or a cancellation (a refusal is
	 * the API's answer for that solve and is kept). Two pumps at least, as the card asks. On the
	 * system curves' queue: one request at a time, after any Solve all run, goal seek or solve in
	 * flight; one whose solve is no longer its case's latest, or that is cancelled, is dropped
	 * (unsent, when a solve replaced it while it waited) and never fills the cache.
	 */
	loadGroupCurve(
		pumpIds: readonly string[],
		options: { retry?: boolean; caseId?: CaseId } = {}
	): void {
		this.#loadGroup('group', pumpIds, options);
	}

	/**
	 * Compute the group system curve of `pumpIds` (curve 'system') for the latest solve of a case
	 * (default: the active one), by loadGroupCurve()'s rules, once the group curve of the same
	 * pumps has answered for that solve with a duty, or been refused for an active PRV or PSV
	 * inside only (wantsGroupSystemCurve); before that, or after any other answer, nothing is
	 * sent. The flows sampled are the API's default (from the lower of 0 and the duty's flow to
	 * 1.2 × the largest of the duty's flow and the group curve's flows, SDD §4.17).
	 */
	loadGroupSystemCurve(
		pumpIds: readonly string[],
		options: { retry?: boolean; caseId?: CaseId } = {}
	): void {
		const caseId = options.caseId === undefined ? this.activeCase : options.caseId;
		if (!wantsGroupSystemCurve(this.#case(caseId).groupCurves[groupKey(pumpIds)])) return;
		this.#loadGroup('system', pumpIds, { ...options, caseId });
	}

	#loadGroup(
		kind: GroupCurveKind,
		pumpIds: readonly string[],
		options: { retry?: boolean; caseId?: CaseId }
	): void {
		if (pumpIds.length < 2) return;
		const caseId = options.caseId === undefined ? this.activeCase : options.caseId;
		const state = this.#case(caseId);
		const response = state.results.response;
		const project = state.solvedProject;
		if (!response || !project) return;
		const map = GROUP_MAPS[kind];
		const key = groupKey(pumpIds);
		const known = state[map][key];
		const again = known?.status === 'error' || known?.status === 'cancelled';
		if (known && !(options.retry && again)) return;
		const solver = this.#options.solver ?? defaultClient();
		const set = (next: GroupCurveState) => {
			const now = this.#case(caseId);
			if (now.results.response !== response) return; // another solve's results by now
			this.#setCase(caseId, { [map]: { ...now[map], [key]: next } });
		};
		if (!solver.groupCurve) {
			set({ status: 'error', message: 'Group curves are not available from this server.' });
			return;
		}
		set({ status: 'loading' });
		const controller = new AbortController();
		const requestKey = groupRequestKey(key, kind);
		this.#abortCurveRequests(slot(caseId), requestKey);
		this.#curveRequests = [
			...this.#curveRequests,
			{ caseKey: slot(caseId), key: requestKey, controller }
		];
		const { signal } = controller;
		const ids = [...pumpIds].sort();
		const request = async () => {
			try {
				await this.#runDone; // one request at a time: after a Solve all run
				await this.#goalSeekDone; // and after a goal seek
				// And after a solve in flight (dropped unsent if it replaced the response).
				if (this.#solvingCase !== undefined) await this.#solveDone;
				if (signal.aborted || this.#case(caseId).results.response !== response) return;
				const curve = await solver.groupCurve!(project, ids, {
					signal,
					...(caseId === null ? {} : { scenarioId: caseId }),
					...(kind === 'system' ? { curve: 'system' as const } : {})
				});
				if (!signal.aborted) set({ status: 'ready', response: curve });
			} catch (error) {
				if (signal.aborted) return; // cancelled: whoever cancelled it says so
				set(
					error instanceof NotAStationError
						? { status: 'refused', message: error.message, issues: error.issues }
						: {
								status: 'error',
								message:
									error instanceof Error
										? error.message
										: kind === 'group'
											? 'The group curve failed.'
											: 'The group system curve failed.'
							}
				);
			} finally {
				this.#curveRequests = this.#curveRequests.filter((r) => r.controller !== controller);
			}
		};
		this.#curveQueue = this.#curveQueue.then(request, request);
	}

	/**
	 * Cancel the group curve of `pumpIds` while it is computed or waits its turn (the card's
	 * Cancel): its request is aborted, an answer that still arrives is dropped, and the curve is
	 * marked cancelled by the user until it is asked for again (loadGroupCurve with `retry`).
	 */
	cancelGroupCurve(pumpIds: readonly string[], options: { caseId?: CaseId } = {}): void {
		this.#cancelGroup('group', pumpIds, options);
	}

	/** Cancel the group system curve of `pumpIds`, as cancelGroupCurve() its group curve. */
	cancelGroupSystemCurve(pumpIds: readonly string[], options: { caseId?: CaseId } = {}): void {
		this.#cancelGroup('system', pumpIds, options);
	}

	#cancelGroup(
		kind: GroupCurveKind,
		pumpIds: readonly string[],
		options: { caseId?: CaseId }
	): void {
		const caseId = options.caseId === undefined ? this.activeCase : options.caseId;
		const map = GROUP_MAPS[kind];
		const key = groupKey(pumpIds);
		const state = this.#case(caseId);
		if (state[map][key]?.status !== 'loading') return;
		this.#abortCurveRequests(slot(caseId), groupRequestKey(key, kind));
		this.#setCase(caseId, {
			[map]: { ...state[map], [key]: { status: 'cancelled', by: 'user' } }
		});
	}

	/**
	 * Abort every case's system-curve, group-curve and group-system-curve requests; the curves
	 * being computed are marked cancelled `by` what started (a solve, or a goal seek).
	 */
	#cancelSystemCurves(by: 'solve' | 'goalSeek' = 'solve'): void {
		this.#abortCurveRequests();
		let cases: Record<string, CaseState> | null = null;
		const cancelled = <T extends { status: string }>(curves: Readonly<Record<string, T>>) =>
			Object.fromEntries(
				Object.entries(curves).map(([id, curve]) => [
					id,
					curve.status === 'loading' ? { status: 'cancelled' as const, by } : curve
				])
			);
		for (const [key, state] of Object.entries(this.#cases)) {
			const loading = (curves: Readonly<Record<string, { status: string }>>) =>
				Object.values(curves).some((curve) => curve.status === 'loading');
			if (
				!loading(state.systemCurves) &&
				!loading(state.groupCurves) &&
				!loading(state.groupSystemCurves)
			) {
				continue;
			}
			cases ??= { ...this.#cases };
			cases[key] = {
				...state,
				systemCurves: cancelled(state.systemCurves) as Record<string, SystemCurveState>,
				groupCurves: cancelled(state.groupCurves) as Record<string, GroupCurveState>,
				groupSystemCurves: cancelled(state.groupSystemCurves) as Record<
					string,
					GroupSystemCurveState
				>
			};
		}
		if (cases) this.#cases = cases;
	}

	/** Drop a case's system and group curves (their solve is no longer the one shown). */
	#forgetSystemCurves(caseId: CaseId): void {
		this.#abortCurveRequests(slot(caseId));
		this.#setCase(caseId, {
			solvedProject: null,
			systemCurves: {},
			groupCurves: {},
			groupSystemCurves: {}
		});
	}

	/** Abort the system-curve requests of a case (and of one curve of it); default: all of them. */
	#abortCurveRequests(caseKey?: string, key?: string): void {
		const aborted = (r: { caseKey: string; key: string }) =>
			(caseKey === undefined || r.caseKey === caseKey) && (key === undefined || r.key === key);
		for (const r of this.#curveRequests) if (aborted(r)) r.controller.abort();
		this.#curveRequests = this.#curveRequests.filter((r) => !aborted(r));
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
