/**
 * Client for the OpenSolve Pipe API (SDD §5.1). The server is stateless: each request carries
 * the data it needs, and nothing else is sent (no credentials, cookies or referrer). No other
 * network calls are made from the app (GOALS §4.5).
 *
 * Errors are typed so the UI can say what to do (SDD §8.1):
 * - TopologyError: the network cannot be solved as connected (422 TOPOLOGY_ERROR);
 * - ValidationError: the request was rejected as invalid input (400, or 422 from validation);
 *   NotFoundError, a ValidationError, when what it names is not in the project (404 NOT_FOUND:
 *   an unknown scenario or pump, or a goal seek's unknown elements, with their issues);
 *   NotAStationError, a ValidationError, when the pumps of a group curve do not form a station
 *   (422 NOT_A_STATION, every reason an issue with its code and ids);
 * - NetworkError: the API could not be reached, could not do the work now, or did not answer as
 *   documented (offline, timeout, 429 or 5xx, with the server's message when it sent the error
 *   envelope: busy, still solving the previous request, the time budget ran out; or an endpoint
 *   the server does not provide yet).
 */
import { env } from '$env/dynamic/public';
import type {
	ErrorResponse,
	FluidDefinition,
	FluidInfo,
	FluidListResponse,
	FluidProperties,
	FluidPropertiesResponse,
	GoalSeekRequest,
	GoalSeekResponse,
	LibraryResponse,
	MethodVersionsResponse,
	Project,
	PumpGroupCurveRequest,
	PumpGroupCurveResponse,
	SolveOptions,
	SolveResponse,
	SystemCurveRequest,
	SystemCurveResponse,
	TopologyIssue
} from './types';

export const DEFAULT_API_URL = 'http://localhost:8000';
export const DEFAULT_TIMEOUT_MS = 60_000;

/** Base URL of the API: PUBLIC_API_URL, else http://localhost:8000 (no trailing slash). */
export function apiBaseUrl(): string {
	const configured = env.PUBLIC_API_URL?.trim();
	return (configured || DEFAULT_API_URL).replace(/\/+$/, '');
}

export class ApiError extends Error {
	/** HTTP status, or null when no response was received. */
	readonly status: number | null;

	constructor(message: string, status: number | null) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
	}
}

export class NetworkError extends ApiError {
	/** The API's error code ('SERVER_BUSY', 'TIMEOUT', 'RATE_LIMITED', ...), when it sent one. */
	readonly code: string | null;

	constructor(message: string, status: number | null = null, code: string | null = null) {
		super(message, status);
		this.name = 'NetworkError';
		this.code = code;
	}
}

export class TopologyError extends ApiError {
	readonly issues: readonly TopologyIssue[];

	constructor(message: string, issues: readonly TopologyIssue[], status = 422) {
		super(message, status);
		this.name = 'TopologyError';
		this.issues = issues;
	}
}

export class ValidationError extends ApiError {
	/** One readable line per problem, e.g. "project › components › 0 › liquidLevel: ...". */
	readonly details: readonly string[];
	/** The API's error code ('VALIDATION_ERROR', 'FLUID_ERROR', ...), when it sent one. */
	readonly code: string | null;

	constructor(message: string, details: readonly string[], status: number, code?: string | null) {
		super(message, status);
		this.name = 'ValidationError';
		this.details = details;
		this.code = code ?? null;
	}
}

/**
 * 404 NOT_FOUND: the request names something the project does not have (an unknown scenario or
 * pump, or a goal seek's unknown elements, ports or pipes, each an issue with its ids). It is a
 * ValidationError, so every endpoint's 404 is about the request as before; goal seek reads its
 * issues to mark the rows they name.
 */
export class NotFoundError extends ValidationError {
	readonly issues: readonly TopologyIssue[];

	constructor(message: string, details: readonly string[], issues: readonly TopologyIssue[]) {
		super(message, details, 404, 'NOT_FOUND');
		this.name = 'NotFoundError';
		this.issues = issues;
	}
}

/**
 * 422 NOT_A_STATION: the pumps of a group curve do not form a station (CLAUDE.md D21; proposal
 * pump-groups.md §5.6). Every reason is an issue with its code (NO_SEPARATING_PORTS: one place,
 * or three or more; NO_WAY_THROUGH: two places, no member on a way between them;
 * FIXED_HEAD_INSIDE, ASSIGNED_FLOW_INSIDE, OTHER_PUMP_INSIDE, DIFFERENT_BOUNDARIES;
 * MEMBERS_OPPOSED: as many members face each way; MEMBER_REVERSED: a minority faces against the
 * rest; PRESSURE_CONTROL_INSIDE, alone or beside another reason), the server's sentence and the
 * ids it names, which the Pumps together card words with element names.
 */
export class NotAStationError extends ValidationError {
	readonly issues: readonly TopologyIssue[];

	constructor(message: string, details: readonly string[], issues: readonly TopologyIssue[]) {
		super(message, details, 422, 'NOT_A_STATION');
		this.name = 'NotAStationError';
		this.issues = issues;
	}
}

export interface ApiClientOptions {
	/** Base URL; default apiBaseUrl() at request time. */
	baseUrl?: string;
	/** fetch implementation; default the global fetch at request time. */
	fetch?: typeof fetch;
	/** Request timeout, ms (default 60 s). */
	timeoutMs?: number;
}

export interface RequestOptions {
	/** Abort the request (for example when a newer solve supersedes it); the timeout still applies. */
	signal?: AbortSignal;
}

export interface CaseRequestOptions extends RequestOptions {
	/**
	 * Solve this scenario of the project (its changes are applied to the base project on the
	 * server); absent or null: the base project, and the request carries no scenarioId at all.
	 */
	scenarioId?: string | null;
}

export interface SystemCurveOptions extends CaseRequestOptions {
	flowMin?: number;
	flowMax?: number | null;
	numPoints?: number;
}

export interface GroupCurveOptions extends CaseRequestOptions {
	/**
	 * 'group' (default): the group curve, the station solved alone at a grid of rises; 'system':
	 * the group system curve, the rest of the network with the station's flow forced from its
	 * inlet to its outlet, at a grid of flows (CLAUDE.md D21, slice 4b).
	 */
	curve?: 'group' | 'system';
	/** The rises sampled, m (default: the API's, from its duty and the pumps' shutoff heads). */
	headMin?: number;
	headMax?: number;
	/**
	 * The flows sampled, m³/s, curve 'system' only (default: the API's, from 0 to 1.2 × the
	 * largest of the duty's flow and the group curve's flows).
	 */
	flowMin?: number;
	flowMax?: number;
	numPoints?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isErrorResponse(body: unknown): body is ErrorResponse {
	return (
		isRecord(body) &&
		body.success === false &&
		typeof body.error === 'string' &&
		Array.isArray(body.issues)
	);
}

/** FastAPI request-validation detail: [{loc, msg, type}] → "body › project › id: msg". */
function validationDetails(body: unknown): string[] | null {
	if (!isRecord(body) || !Array.isArray(body.detail)) return null;
	return body.detail.map((item: unknown) => {
		if (!isRecord(item)) return String(item);
		const loc = Array.isArray(item.loc) ? item.loc.map(String).join(' › ') : '';
		const msg = typeof item.msg === 'string' ? item.msg : 'invalid value';
		return loc ? `${loc}: ${msg}` : msg;
	});
}

/**
 * A signal that aborts when either `caller` or `timeout` does, with that signal's reason (so a
 * timeout still rejects with a TimeoutError and a cancellation with the caller's reason).
 * AbortSignal.any does this, but it is newer than the app's build target (Vite's
 * 'baseline-widely-available': Safari 16.4+, Chrome 111+, Firefox 114+; AbortSignal.any arrived
 * in Safari 17.4, Chrome 116 and Firefox 124) and Vite does not polyfill APIs, so the two are
 * combined here. `release` removes the listeners: the caller's signal may outlive many requests.
 */
function eitherSignal(
	caller: AbortSignal,
	timeout: AbortSignal
): { signal: AbortSignal; release: () => void } {
	const controller = new AbortController();
	const sources = [caller, timeout];
	const release = () => {
		for (const source of sources) source.removeEventListener('abort', onAbort);
	};
	function onAbort(this: AbortSignal) {
		release();
		controller.abort(this.reason);
	}
	const aborted = sources.find((source) => source.aborted);
	if (aborted) controller.abort(aborted.reason);
	else for (const source of sources) source.addEventListener('abort', onAbort);
	return { signal: controller.signal, release };
}

const UNAVAILABLE =
	'The calculation server could not be reached. Check your connection and try again; ' +
	'your project is safe in this page and its link.';

export class ApiClient {
	readonly #options: ApiClientOptions;
	#library: Promise<LibraryResponse> | null = null;
	#fluids: Promise<FluidInfo[]> | null = null;

	constructor(options: ApiClientOptions = {}) {
		this.#options = options;
	}

	get baseUrl(): string {
		return (this.#options.baseUrl ?? apiBaseUrl()).replace(/\/+$/, '');
	}

	async #request<T>(
		method: 'GET' | 'POST',
		path: string,
		body: unknown,
		options: RequestOptions = {}
	): Promise<T> {
		const fetchImpl = this.#options.fetch ?? ((input, init) => globalThis.fetch(input, init));
		const timeout = AbortSignal.timeout(this.#options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
		// The caller's signal cancels; the timeout applies either way (until the body is read).
		const { signal, release } = options.signal
			? eitherSignal(options.signal, timeout)
			: { signal: timeout, release: () => {} };
		try {
			return await this.#send<T>(fetchImpl, method, path, body, signal, options);
		} finally {
			release();
		}
	}

	async #send<T>(
		fetchImpl: typeof fetch,
		method: 'GET' | 'POST',
		path: string,
		body: unknown,
		signal: AbortSignal,
		options: RequestOptions
	): Promise<T> {
		const init: RequestInit = {
			method,
			credentials: 'omit',
			referrerPolicy: 'no-referrer',
			signal
		};
		if (body !== undefined) {
			init.headers = { 'Content-Type': 'application/json' };
			init.body = JSON.stringify(body);
		}
		let response: Response;
		try {
			response = await fetchImpl(`${this.baseUrl}${path}`, init);
		} catch (error) {
			if (error instanceof DOMException && error.name === 'AbortError' && options.signal?.aborted) {
				throw error; // cancelled by the caller: not a failure to report
			}
			const timedOut = error instanceof DOMException && error.name === 'TimeoutError';
			throw new NetworkError(
				timedOut ? 'The calculation server did not answer in time. Try again.' : UNAVAILABLE
			);
		}
		let data: unknown;
		try {
			data = await response.json();
		} catch {
			// Not JSON: handled below as an unreadable answer.
		}
		if (response.ok) {
			if (data === undefined) {
				throw new NetworkError(
					'The calculation server sent an unreadable answer.',
					response.status
				);
			}
			return data as T;
		}
		if (isErrorResponse(data)) {
			if (data.error === 'TOPOLOGY_ERROR') {
				throw new TopologyError(data.message, data.issues, response.status);
			}
			if (response.status === 429 || response.status >= 500) {
				// Not about the project: the server is busy (SERVER_BUSY, e.g. still solving a
				// request just cancelled), out of time (TIMEOUT), rate-limited or failed.
				throw new NetworkError(data.message, response.status, data.error);
			}
			const details = [data.message, ...data.issues.map((i) => i.message)].filter(Boolean);
			if (response.status === 404 && data.error === 'NOT_FOUND') {
				throw new NotFoundError(data.message, details, data.issues);
			}
			if (response.status === 422 && data.error === 'NOT_A_STATION') {
				throw new NotAStationError(data.message, details, data.issues);
			}
			throw new ValidationError(data.message, details, response.status, data.error);
		}
		const details = validationDetails(data);
		if (details && (response.status === 400 || response.status === 422)) {
			throw new ValidationError(
				'The server rejected the project as invalid.',
				details,
				response.status
			);
		}
		throw new NetworkError(
			response.status === 501
				? 'This feature is not available on the calculation server yet.'
				: `The calculation server returned an error (HTTP ${response.status}). Try again later.`,
			response.status
		);
	}

	/**
	 * Solve the network (POST /api/v1/solve). Non-convergence is a 200 with success false.
	 * System curves are not computed with the solve unless asked for (D10: the app fetches the
	 * curve of the pump being viewed with systemCurve(), keeping a plain solve fast). With
	 * `request.scenarioId`, that scenario of the project is solved; the id travels in the body
	 * only, never in the URL (D10).
	 */
	solve(project: Project, options: Partial<SolveOptions> = {}, request?: CaseRequestOptions) {
		const solveOptions: SolveOptions = {
			includeSystemCurve: options.includeSystemCurve ?? false,
			systemCurvePoints: options.systemCurvePoints ?? 41
		};
		const scenarioId = request?.scenarioId;
		return this.#request<SolveResponse>(
			'POST',
			'/api/v1/solve',
			{ project, options: solveOptions, ...(scenarioId ? { scenarioId } : {}) },
			request
		);
	}

	/** System curve seen by one pump (POST /api/v1/system-curve), of a scenario with scenarioId. */
	systemCurve(project: Project, pumpId: string, options: SystemCurveOptions = {}) {
		const body: SystemCurveRequest = {
			project,
			pumpId,
			flowMin: options.flowMin ?? 0,
			flowMax: options.flowMax ?? null,
			numPoints: options.numPoints ?? 41,
			...(options.scenarioId ? { scenarioId: options.scenarioId } : {})
		};
		return this.#request<SystemCurveResponse>('POST', '/api/v1/system-curve', body, options);
	}

	/**
	 * The group curve of the station holding `pumpIds` (POST /api/v1/pump-group-curve, CLAUDE.md
	 * D21): the station the API finds, its duty in the case's solve and the station solved alone
	 * at a grid of rises; with `curve: 'system'`, its group system curve instead (the rest of the
	 * network at a grid of the station's flows); of a scenario with `scenarioId` (in the body
	 * only). Pumps that do not form a station: NotAStationError, with every reason.
	 */
	groupCurve(project: Project, pumpIds: readonly string[], options: GroupCurveOptions = {}) {
		const body: PumpGroupCurveRequest = {
			project,
			pumpIds: [...pumpIds],
			curve: options.curve ?? 'group',
			numPoints: options.numPoints ?? 41,
			...(options.headMin === undefined ? {} : { headMin: options.headMin }),
			...(options.headMax === undefined ? {} : { headMax: options.headMax }),
			...(options.flowMin === undefined ? {} : { flowMin: options.flowMin }),
			...(options.flowMax === undefined ? {} : { flowMax: options.flowMax }),
			...(options.scenarioId ? { scenarioId: options.scenarioId } : {})
		};
		return this.#request<PumpGroupCurveResponse>('POST', '/api/v1/pump-group-curve', body, options);
	}

	/**
	 * Goal seek (POST /api/v1/goal-seek, PRD §3.9): the values of `variables` that bring `goals`
	 * to their targets, each evaluation a full solve of the case (the base, or the scenario
	 * `request.scenarioId`, sent in the body only). A goal not met is a 200 with success false.
	 * The project is never changed: each variable's override applies the value found.
	 */
	goalSeek(
		project: Project,
		setup: Pick<GoalSeekRequest, 'variables' | 'goals'>,
		request?: CaseRequestOptions
	) {
		const scenarioId = request?.scenarioId;
		const body: GoalSeekRequest = {
			project,
			...(scenarioId ? { scenarioId } : {}),
			variables: setup.variables,
			goals: setup.goals
		};
		return this.#request<GoalSeekResponse>('POST', '/api/v1/goal-seek', body, request);
	}

	/** Pipe materials and fitting types (GET /api/v1/library). Cached; retried after a failure. */
	getLibrary(): Promise<LibraryResponse> {
		if (!this.#library) {
			this.#library = this.#request<LibraryResponse>('GET', '/api/v1/library', undefined);
			this.#library.catch(() => (this.#library = null));
		}
		return this.#library;
	}

	/** Built-in fluids with their valid ranges (GET /api/v1/fluids). Cached; retried after a failure. */
	getFluids(): Promise<FluidInfo[]> {
		if (!this.#fluids) {
			this.#fluids = this.#request<FluidListResponse>('GET', '/api/v1/fluids', undefined).then(
				(r) => r.fluids
			);
			this.#fluids.catch(() => (this.#fluids = null));
		}
		return this.#fluids;
	}

	/**
	 * Properties of a fluid definition as the solver will use them (POST
	 * /api/v1/fluids/properties). The fluid travels in the request body, which the server never
	 * logs; nothing about it is put in the URL (the API's GET form carries it in the query
	 * string, which intermediaries may log).
	 */
	async fluidProperties(
		fluid: FluidDefinition,
		request?: RequestOptions
	): Promise<FluidProperties> {
		const response = await this.#request<FluidPropertiesResponse>(
			'POST',
			'/api/v1/fluids/properties',
			fluid,
			request
		);
		return response.properties;
	}

	/** Calculation-method versions (GET /api/v1/method-versions). */
	methodVersions(request?: RequestOptions): Promise<MethodVersionsResponse> {
		return this.#request<MethodVersionsResponse>(
			'GET',
			'/api/v1/method-versions',
			undefined,
			request
		);
	}
}

let shared: ApiClient | null = null;

/** The app's client (base URL from PUBLIC_API_URL). */
export function defaultClient(): ApiClient {
	shared ??= new ApiClient();
	return shared;
}

export const solve = (...args: Parameters<ApiClient['solve']>) => defaultClient().solve(...args);
export const systemCurve = (...args: Parameters<ApiClient['systemCurve']>) =>
	defaultClient().systemCurve(...args);
export const groupCurve = (...args: Parameters<ApiClient['groupCurve']>) =>
	defaultClient().groupCurve(...args);
export const goalSeek = (...args: Parameters<ApiClient['goalSeek']>) =>
	defaultClient().goalSeek(...args);
export const getLibrary = () => defaultClient().getLibrary();
export const getFluids = () => defaultClient().getFluids();
export const fluidProperties = (...args: Parameters<ApiClient['fluidProperties']>) =>
	defaultClient().fluidProperties(...args);
export const methodVersions = (...args: Parameters<ApiClient['methodVersions']>) =>
	defaultClient().methodVersions(...args);
