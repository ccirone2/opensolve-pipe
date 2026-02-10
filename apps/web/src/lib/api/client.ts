/**
 * API client for communicating with the OpenSolve Pipe backend.
 */

import type { Project, SolvedState, FluidProperties, FluidDefinition } from '$lib/models';
import { browser } from '$app/environment';

// =============================================================================
// Configuration
// =============================================================================

/**
 * Get the API base URL from environment or use default.
 *
 * - Browser: uses relative URL `/api/v1` (proxied by Vite in dev, rewritten by Vercel in prod)
 * - SSR: uses PUBLIC_API_URL env var if set, otherwise falls back to localhost:8000
 */
function getBaseUrl(): string {
	// In browser, use relative URL (proxied by Vite dev server or Vercel rewrites)
	if (browser) {
		return '/api/v1';
	}
	// In SSR, use environment variable or fall back to localhost for local dev
	const apiUrl = import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';
	return `${apiUrl.replace(/\/$/, '')}/api/v1`;
}

/** Default request timeout in milliseconds. */
const DEFAULT_TIMEOUT = 30000;

/** Maximum number of retry attempts for transient failures. */
const MAX_RETRIES = 3;

/** Delay between retries in milliseconds. */
const RETRY_DELAY = 1000;

// =============================================================================
// Error Types
// =============================================================================

/** Base class for API errors. */
export class ApiError extends Error {
	constructor(
		message: string,
		public readonly statusCode?: number,
		public readonly details?: Record<string, unknown>
	) {
		super(message);
		this.name = 'ApiError';
	}
}

/** Network error (no response received). */
export class NetworkError extends ApiError {
	constructor(message: string, public readonly originalError?: Error) {
		super(message);
		this.name = 'NetworkError';
	}
}

/** Timeout error. */
export class TimeoutError extends ApiError {
	constructor(message = 'Request timed out') {
		super(message);
		this.name = 'TimeoutError';
	}
}

/** Validation error from the API. */
export class ValidationError extends ApiError {
	constructor(
		message: string,
		public readonly validationDetails?: Record<string, unknown>
	) {
		super(message, 400, validationDetails);
		this.name = 'ValidationError';
	}
}

/** Server error (5xx). */
export class ServerError extends ApiError {
	constructor(message: string, statusCode: number) {
		super(message, statusCode);
		this.name = 'ServerError';
	}
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Sleep for a given number of milliseconds.
 */
function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Create an AbortController with a timeout.
 */
function createTimeoutController(timeoutMs: number): AbortController {
	const controller = new AbortController();
	setTimeout(() => controller.abort(), timeoutMs);
	return controller;
}

/**
 * Check if an error is retryable (transient failure).
 */
function isRetryableError(error: unknown): boolean {
	// Network errors are retryable
	if (error instanceof NetworkError) return true;
	if (error instanceof TimeoutError) return true;

	// Server errors (5xx except 501) are retryable
	if (error instanceof ServerError) {
		return error.statusCode !== undefined && error.statusCode >= 500 && error.statusCode !== 501;
	}

	return false;
}

/**
 * Make a fetch request with error handling.
 */
async function fetchWithHandling<T>(
	url: string,
	options: RequestInit,
	timeoutMs: number = DEFAULT_TIMEOUT
): Promise<T> {
	const controller = createTimeoutController(timeoutMs);

	try {
		const response = await fetch(url, {
			...options,
			signal: controller.signal
		});

		// Parse response body
		const contentType = response.headers.get('content-type');
		const isJson = contentType?.includes('application/json');
		const body = isJson ? await response.json() : await response.text();

		// Handle error responses
		if (!response.ok) {
			const errorDetail = isJson ? (body as Record<string, unknown>) : undefined;
			const errorMessage =
				errorDetail?.message ?? errorDetail?.detail ?? body ?? `Request failed: ${response.status}`;

			if (response.status === 400) {
				throw new ValidationError(
					String(errorMessage),
					errorDetail as Record<string, unknown> | undefined
				);
			}

			if (response.status >= 500) {
				throw new ServerError(String(errorMessage), response.status);
			}

			throw new ApiError(String(errorMessage), response.status, errorDetail);
		}

		return body as T;
	} catch (error) {
		// Handle abort (timeout)
		if (error instanceof DOMException && error.name === 'AbortError') {
			throw new TimeoutError();
		}

		// Handle fetch errors (network issues)
		if (error instanceof TypeError && error.message.includes('fetch')) {
			throw new NetworkError('Network request failed', error);
		}

		// Re-throw known errors
		if (error instanceof ApiError) {
			throw error;
		}

		// Wrap unknown errors
		throw new NetworkError(
			error instanceof Error ? error.message : 'Unknown error',
			error instanceof Error ? error : undefined
		);
	}
}

/**
 * Make a request with retry logic for transient failures.
 */
async function fetchWithRetry<T>(
	url: string,
	options: RequestInit,
	timeoutMs: number = DEFAULT_TIMEOUT,
	maxRetries: number = MAX_RETRIES
): Promise<T> {
	let lastError: unknown;

	for (let attempt = 0; attempt <= maxRetries; attempt++) {
		try {
			return await fetchWithHandling<T>(url, options, timeoutMs);
		} catch (error) {
			lastError = error;

			// Don't retry non-retryable errors
			if (!isRetryableError(error)) {
				throw error;
			}

			// Don't retry after max attempts
			if (attempt === maxRetries) {
				throw error;
			}

			// Wait before retrying (exponential backoff)
			const delay = RETRY_DELAY * Math.pow(2, attempt);
			await sleep(delay);
		}
	}

	// Should never reach here, but TypeScript needs this
	throw lastError;
}

// =============================================================================
// API Client Functions
// =============================================================================

/**
 * Solve a hydraulic network project.
 */
export async function solveNetwork(project: Project): Promise<SolvedState> {
	const baseUrl = getBaseUrl();
	const url = `${baseUrl}/solve`;

	return fetchWithRetry<SolvedState>(url, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(project)
	});
}

/**
 * List all available fluid types.
 */
export interface FluidInfo {
	id: string;
	name: string;
	type: 'temperature_dependent' | 'fixed';
	temperature_range_C?: { min: number; max: number };
	notes?: string;
}

export async function listFluids(): Promise<FluidInfo[]> {
	const baseUrl = getBaseUrl();
	const url = `${baseUrl}/fluids`;

	return fetchWithRetry<FluidInfo[]>(url, {
		method: 'GET',
		headers: {
			Accept: 'application/json'
		}
	});
}

/**
 * Get fluid properties at a specific temperature.
 */
export interface GetFluidPropertiesOptions {
	fluidId: string;
	temperature?: number;
	temperatureUnit?: 'F' | 'C' | 'K';
	concentration?: number;
}

export async function getFluidProperties(
	options: GetFluidPropertiesOptions
): Promise<FluidProperties> {
	const { fluidId, temperature = 68, temperatureUnit = 'F', concentration } = options;

	const baseUrl = getBaseUrl();
	const params = new URLSearchParams({
		temperature: String(temperature),
		temperature_unit: temperatureUnit
	});

	if (concentration !== undefined) {
		params.append('concentration', String(concentration));
	}

	const url = `${baseUrl}/fluids/${encodeURIComponent(fluidId)}/properties?${params}`;

	return fetchWithRetry<FluidProperties>(url, {
		method: 'GET',
		headers: {
			Accept: 'application/json'
		}
	});
}

/**
 * Calculate fluid properties from a full fluid definition.
 */
export async function calculateFluidProperties(
	fluidDefinition: FluidDefinition,
	temperatureUnit: 'F' | 'C' | 'K' = 'F'
): Promise<FluidProperties> {
	const baseUrl = getBaseUrl();
	const params = new URLSearchParams({
		temperature_unit: temperatureUnit
	});

	const url = `${baseUrl}/fluids/properties?${params}`;

	return fetchWithRetry<FluidProperties>(url, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Accept: 'application/json'
		},
		body: JSON.stringify(fluidDefinition)
	});
}

/**
 * Simple solve request for pump-pipe systems without full project model.
 */
export interface SimpleSolveRequest {
	pump_curve: Array<{ flow: number; head: number }>;
	static_head_ft: number;
	pipe_length_ft: number;
	pipe_diameter_in: number;
	pipe_roughness_in: number;
	fluid?: FluidDefinition;
	total_k_factor?: number;
	suction_head_ft?: number;
	suction_losses_ft?: number;
	temperature_unit?: 'F' | 'C' | 'K';
}

export interface SimpleSolveResponse {
	converged: boolean;
	error?: string;
	operating_flow_gpm?: number;
	operating_head_ft?: number;
	velocity_fps?: number;
	reynolds_number?: number;
	friction_factor?: number;
	total_head_loss_ft?: number;
	static_head_ft?: number;
	npsh_available_ft?: number;
	system_curve: Array<[number, number]>;
	pump_curve: Array<[number, number]>;
}

/**
 * Solve a simple pump-pipe system.
 */
export async function solveSimple(request: SimpleSolveRequest): Promise<SimpleSolveResponse> {
	const baseUrl = getBaseUrl();
	const url = `${baseUrl}/solve/simple`;

	return fetchWithRetry<SimpleSolveResponse>(url, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Accept: 'application/json'
		},
		body: JSON.stringify(request)
	});
}
