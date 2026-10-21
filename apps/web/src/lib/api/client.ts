/**
 * Client for the OpenSolve Pipe API (SDD §5.1). The server is stateless: each request carries
 * the data it needs, and nothing else is sent (no credentials, cookies or referrer). No other
 * network calls are made from the app (GOALS §4.5).
 *
 * Errors are typed so the UI can say what to do (SDD §8.1):
 * - TopologyError: the network cannot be solved as connected (422 TOPOLOGY_ERROR);
 * - ValidationError: the request was rejected as invalid input (400, or 422 from validation);
 * - NetworkError: the API could not be reached or did not answer as documented (offline,
 *   timeout, 5xx, or an endpoint the server does not provide yet).
 */
import { env } from '$env/dynamic/public';
import type {
	CustomFluid,
	ErrorResponse,
	FluidInfo,
	FluidListResponse,
	FluidProperties,
	FluidPropertiesResponse,
	LibraryResponse,
	MethodVersionsResponse,
	Project,
	SolveOptions,
	SolveResponse,
	SystemCurveRequest,
	SystemCurveResponse,
	TopologyIssue,
	BuiltinFluidId
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
	constructor(message: string, status: number | null = null) {
		super(message, status);
		this.name = 'NetworkError';
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

export interface ApiClientOptions {
	/** Base URL; default apiBaseUrl() at request time. */
	baseUrl?: string;
	/** fetch implementation; default the global fetch at request time. */
	fetch?: typeof fetch;
	/** Request timeout, ms (default 60 s). */
	timeoutMs?: number;
}

export interface RequestOptions {
	/** Abort the request (for example when a newer solve supersedes it). */
	signal?: AbortSignal;
}

export interface SystemCurveOptions extends RequestOptions {
	flowMin?: number;
	flowMax?: number | null;
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
		const init: RequestInit = {
			method,
			credentials: 'omit',
			referrerPolicy: 'no-referrer',
			signal: options.signal ?? AbortSignal.timeout(this.#options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
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
			const details = [data.message, ...data.issues.map((i) => i.message)].filter(Boolean);
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

	/** Solve the network (POST /api/v1/solve). Non-convergence is a 200 with success false. */
	solve(project: Project, options: Partial<SolveOptions> = {}, request?: RequestOptions) {
		const solveOptions: SolveOptions = {
			includeSystemCurve: options.includeSystemCurve ?? true,
			systemCurvePoints: options.systemCurvePoints ?? 41
		};
		return this.#request<SolveResponse>(
			'POST',
			'/api/v1/solve',
			{ project, options: solveOptions },
			request
		);
	}

	/** System curve seen by one pump (POST /api/v1/system-curve). */
	systemCurve(project: Project, pumpId: string, options: SystemCurveOptions = {}) {
		const body: SystemCurveRequest = {
			project,
			pumpId,
			flowMin: options.flowMin ?? 0,
			flowMax: options.flowMax ?? null,
			numPoints: options.numPoints ?? 41
		};
		return this.#request<SystemCurveResponse>('POST', '/api/v1/system-curve', body, options);
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

	/** Properties of a built-in fluid (GET /api/v1/fluids/{id}/properties). */
	async fluidProperties(
		fluidId: BuiltinFluidId,
		temperature: number,
		concentration?: number | null,
		request?: RequestOptions
	): Promise<FluidProperties> {
		const query = new URLSearchParams({ temperature: String(temperature) });
		if (concentration !== undefined && concentration !== null) {
			query.set('concentration', String(concentration));
		}
		const response = await this.#request<FluidPropertiesResponse>(
			'GET',
			`/api/v1/fluids/${encodeURIComponent(fluidId)}/properties?${query}`,
			undefined,
			request
		);
		return response.properties;
	}

	/** Resolved properties of a custom fluid (POST /api/v1/fluids/custom). */
	async customFluidProperties(
		fluid: CustomFluid,
		request?: RequestOptions
	): Promise<FluidProperties> {
		const response = await this.#request<FluidPropertiesResponse>(
			'POST',
			'/api/v1/fluids/custom',
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
export const getLibrary = () => defaultClient().getLibrary();
export const getFluids = () => defaultClient().getFluids();
export const fluidProperties = (...args: Parameters<ApiClient['fluidProperties']>) =>
	defaultClient().fluidProperties(...args);
export const customFluidProperties = (...args: Parameters<ApiClient['customFluidProperties']>) =>
	defaultClient().customFluidProperties(...args);
export const methodVersions = (...args: Parameters<ApiClient['methodVersions']>) =>
	defaultClient().methodVersions(...args);
