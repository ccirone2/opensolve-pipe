import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EXAMPLES } from '../utils/examples';
import {
	ApiClient,
	apiBaseUrl,
	DEFAULT_API_URL,
	getLibrary,
	NetworkError,
	solve,
	TopologyError,
	ValidationError
} from './client';
import type { LibraryResponse } from './types';

const env = vi.hoisted(() => ({}) as Record<string, string | undefined>);
vi.mock('$env/dynamic/public', () => ({ env }));

const BASE = 'https://api.example.test';
const project = EXAMPLES[0]!.create();

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function client(
	responses: (Response | Error)[] | ((url: string, init: RequestInit) => Promise<Response>)
) {
	const queue = Array.isArray(responses) ? [...responses] : null;
	const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		if (!queue)
			return (responses as (u: string, i: RequestInit) => Promise<Response>)(String(input), init!);
		const next = queue.shift();
		if (!next) throw new Error('unexpected request');
		if (next instanceof Error) throw next;
		return next;
	});
	return {
		api: new ApiClient({ baseUrl: `${BASE}/`, fetch: fetch as typeof globalThis.fetch }),
		fetch
	};
}

async function rejection(promise: Promise<unknown>): Promise<unknown> {
	try {
		await promise;
	} catch (error) {
		return error;
	}
	throw new Error('did not reject');
}

const library: LibraryResponse = { materials: [], fittings: [] };

afterEach(() => {
	vi.unstubAllGlobals();
	delete env.PUBLIC_API_URL;
});

describe('requests', () => {
	it('solve posts only the project and options, without credentials or referrer', async () => {
		const { api, fetch } = client([json({ success: true, computeTime: 0.1, solvedState: {} })]);
		await api.solve(project);
		expect(fetch).toHaveBeenCalledTimes(1);
		const [url, init] = fetch.mock.calls[0]!;
		expect(url).toBe(`${BASE}/api/v1/solve`);
		expect(init).toMatchObject({
			method: 'POST',
			credentials: 'omit',
			referrerPolicy: 'no-referrer',
			headers: { 'Content-Type': 'application/json' }
		});
		expect(Object.keys(init!.headers as object)).toEqual(['Content-Type']);
		// No system curves with the solve: the pump chart fetches its own (D10).
		expect(JSON.parse(init!.body as string)).toEqual({
			project,
			options: { includeSystemCurve: false, systemCurvePoints: 41 }
		});
		expect(init!.signal).toBeInstanceOf(AbortSignal);
	});

	it('passes solve options', async () => {
		const { api, fetch } = client([json({})]);
		await api.solve(project, { includeSystemCurve: true, systemCurvePoints: 11 });
		expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string).options).toEqual({
			includeSystemCurve: true,
			systemCurvePoints: 11
		});
	});

	it('GET requests carry no body and no headers', async () => {
		const { api, fetch } = client([json(library), json({ current: '1.0.0', versions: [] })]);
		await api.getLibrary();
		await api.methodVersions();
		for (const [url, init] of fetch.mock.calls) {
			expect(init).toMatchObject({
				method: 'GET',
				credentials: 'omit',
				referrerPolicy: 'no-referrer'
			});
			expect(init!.body).toBeUndefined();
			expect(init!.headers).toBeUndefined();
			expect(String(url).startsWith(`${BASE}/api/v1/`)).toBe(true);
		}
		expect(fetch.mock.calls.map((c) => c[0])).toEqual([
			`${BASE}/api/v1/library`,
			`${BASE}/api/v1/method-versions`
		]);
	});

	it('requests a system curve for one pump', async () => {
		const { api, fetch } = client([json({ pumpId: 'P1', points: [], converged: [] })]);
		await api.systemCurve(project, 'P1', { flowMax: 0.04, numPoints: 21 });
		expect(fetch.mock.calls[0]![0]).toBe(`${BASE}/api/v1/system-curve`);
		expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({
			project,
			pumpId: 'P1',
			flowMin: 0,
			flowMax: 0.04,
			numPoints: 21
		});
	});

	it('requests fluid properties by POST, with the fluid in the body and none in the URL', async () => {
		const properties = { name: 'Water', density: 998 };
		const { api, fetch } = client([
			json({ fluid: 'water', properties }),
			json({ fluid: 'propylene_glycol', properties }),
			json({ fluid: 'custom', properties })
		]);
		const water = { kind: 'builtin' as const, fluidId: 'water' as const, temperature: 293.15 };
		const glycol = {
			kind: 'builtin' as const,
			fluidId: 'propylene_glycol' as const,
			temperature: 280,
			concentration: 0.3
		};
		const oil = { kind: 'custom' as const, name: 'Oil', density: 850, dynamicViscosity: 0.03 };
		expect(await api.fluidProperties(water)).toEqual(properties);
		await api.fluidProperties(glycol);
		await api.fluidProperties(oil);
		expect(fetch.mock.calls.map((c) => c[0])).toEqual(
			Array(3).fill(`${BASE}/api/v1/fluids/properties`)
		);
		expect(fetch.mock.calls.map((c) => c[1]!.method)).toEqual(['POST', 'POST', 'POST']);
		expect(fetch.mock.calls.map((c) => JSON.parse(c[1]!.body as string))).toEqual([
			water,
			glycol,
			oil
		]);
	});

	it('puts no project or fluid values in any URL (GOALS §4.5): only bodies carry them', async () => {
		const answer = { fluids: [], properties: {}, current: '1.0.0', versions: [], points: [] };
		const { api, fetch } = client(() => Promise.resolve(json(answer)));
		await api.solve(project);
		await api.systemCurve(project, 'P1');
		await api.fluidProperties({ kind: 'builtin', fluidId: 'water', temperature: 301.2345 });
		await api.getLibrary();
		await api.getFluids();
		await api.methodVersions();
		expect(fetch).toHaveBeenCalledTimes(6);
		for (const [url] of fetch.mock.calls) {
			expect(String(url)).toMatch(/^https:\/\/api\.example\.test\/api\/v1\/[a-z/-]+$/);
		}
	});

	it('lists fluids', async () => {
		const fluids = [{ id: 'water', name: 'Water' }];
		const { api } = client([json({ fluids })]);
		expect(await api.getFluids()).toEqual(fluids);
	});
});

describe('caching of reference data', () => {
	it('fetches the library and fluid list once', async () => {
		const { api, fetch } = client([json(library), json({ fluids: [] })]);
		expect(await api.getLibrary()).toEqual(library);
		expect(await api.getLibrary()).toEqual(library);
		await api.getFluids();
		await api.getFluids();
		expect(fetch).toHaveBeenCalledTimes(2);
	});

	it('retries after a failure, so the UI can degrade and recover', async () => {
		const { api, fetch } = client([
			json({ detail: 'not implemented yet' }, 501),
			json(library),
			new TypeError('Failed to fetch'),
			json({ fluids: [] })
		]);
		const error = await rejection(api.getLibrary());
		expect(error).toBeInstanceOf(NetworkError);
		expect((error as InstanceType<typeof NetworkError>).status).toBe(501);
		expect((error as Error).message).toMatch(/not available on the calculation server yet/);
		expect(await api.getLibrary()).toEqual(library);
		expect(await rejection(api.getFluids())).toBeInstanceOf(NetworkError);
		expect(await api.getFluids()).toEqual([]);
		expect(fetch).toHaveBeenCalledTimes(4);
	});
});

describe('errors', () => {
	it('maps a topology error with its issues', async () => {
		const issues = [
			{ code: 'NO_BOUNDARY', message: 'Add a reservoir', componentIds: ['P1'], connectionIds: [] }
		];
		const { api } = client([
			json(
				{ success: false, error: 'TOPOLOGY_ERROR', message: 'No fixed-pressure boundary', issues },
				422
			)
		]);
		const error = await rejection(api.solve(project));
		expect(error).toBeInstanceOf(TopologyError);
		expect(error).toMatchObject({ message: 'No fixed-pressure boundary', issues, status: 422 });
	});

	it('maps API validation and fluid errors', async () => {
		const { api } = client([
			json(
				{
					success: false,
					error: 'VALIDATION_ERROR',
					message: 'Pipe size not in library',
					issues: []
				},
				400
			),
			json(
				{
					success: false,
					error: 'FLUID_ERROR',
					message: 'Temperature out of range',
					issues: [
						{ code: 'RANGE', message: 'Water: 273.16–373 K', componentIds: [], connectionIds: [] }
					]
				},
				400
			)
		]);
		const first = await rejection(api.solve(project));
		expect(first).toBeInstanceOf(ValidationError);
		expect(first).toMatchObject({
			details: ['Pipe size not in library'],
			status: 400,
			code: 'VALIDATION_ERROR'
		});
		const second = await rejection(
			api.fluidProperties({ kind: 'builtin', fluidId: 'water', temperature: 500 })
		);
		expect(second).toMatchObject({
			message: 'Temperature out of range',
			details: ['Temperature out of range', 'Water: 273.16–373 K'],
			code: 'FLUID_ERROR'
		});
	});

	it('maps request validation (422 with a detail list)', async () => {
		const { api } = client([
			json(
				{
					detail: [
						{
							loc: ['body', 'project', 'components', 0, 'liquidLevel'],
							msg: 'Input should be >= 0',
							type: 'x'
						},
						{ loc: [], msg: 'Bad', type: 'y' }
					]
				},
				422
			)
		]);
		const error = await rejection(api.solve(project));
		expect(error).toBeInstanceOf(ValidationError);
		expect((error as InstanceType<typeof ValidationError>).details).toEqual([
			'body › project › components › 0 › liquidLevel: Input should be >= 0',
			'Bad'
		]);
	});

	it('maps server failures and unreadable answers to NetworkError', async () => {
		const { api } = client([
			new Response('<html>Bad gateway</html>', { status: 502 }),
			new Response('not json', { status: 200 }),
			new TypeError('Failed to fetch')
		]);
		const bad = await rejection(api.solve(project));
		expect(bad).toBeInstanceOf(NetworkError);
		expect(bad).toMatchObject({ status: 502 });
		expect((bad as Error).message).toMatch(/HTTP 502/);
		const garbled = await rejection(api.solve(project));
		expect(garbled).toBeInstanceOf(NetworkError);
		expect((garbled as Error).message).toMatch(/unreadable/);
		const offline = await rejection(api.solve(project));
		expect(offline).toBeInstanceOf(NetworkError);
		expect(offline).toMatchObject({ status: null });
		expect((offline as Error).message).toMatch(/could not be reached/);
	});

	it('times out', async () => {
		const fetch = vi.fn(
			(_input: RequestInfo | URL, init?: RequestInit) =>
				new Promise<Response>((_resolve, reject) => {
					init!.signal!.addEventListener('abort', () => reject(init!.signal!.reason));
				})
		);
		const api = new ApiClient({
			baseUrl: BASE,
			fetch: fetch as typeof globalThis.fetch,
			timeoutMs: 5
		});
		const error = await rejection(api.solve(project));
		expect(error).toBeInstanceOf(NetworkError);
		expect((error as Error).message).toMatch(/did not answer in time/);
	});

	it('passes a caller abort through unchanged', async () => {
		const controller = new AbortController();
		const fetch = vi.fn(
			(_input: RequestInfo | URL, init?: RequestInit) =>
				new Promise<Response>((_resolve, reject) => {
					init!.signal!.addEventListener('abort', () => reject(init!.signal!.reason));
				})
		);
		const api = new ApiClient({ baseUrl: BASE, fetch: fetch as typeof globalThis.fetch });
		const pending = api.solve(project, {}, { signal: controller.signal });
		controller.abort();
		const error = await rejection(pending);
		expect(error).toBeInstanceOf(DOMException);
		expect((error as DOMException).name).toBe('AbortError');
	});
});

describe('cancellation and timeout without AbortSignal.any', () => {
	// AbortSignal.any is newer than the app's build target (Vite's 'baseline-widely-available':
	// Safari 16.4+, Chrome 111+, Firefox 114+; it arrived in Safari 17.4, Chrome 116 and
	// Firefox 124), and Vite does not polyfill APIs. Requests must work without it.
	const original = Object.getOwnPropertyDescriptor(AbortSignal, 'any');
	beforeEach(() => {
		Object.defineProperty(AbortSignal, 'any', { value: undefined, configurable: true });
	});
	afterEach(() => {
		if (original) Object.defineProperty(AbortSignal, 'any', original);
	});

	/** A fetch that answers `answer` unless its signal aborts first (rejecting with the reason). */
	function pendingFetch(answer?: Promise<Response>) {
		return vi.fn(
			(_input: RequestInfo | URL, init?: RequestInit) =>
				new Promise<Response>((resolve, reject) => {
					const signal = init!.signal!;
					if (signal.aborted) return reject(signal.reason);
					signal.addEventListener('abort', () => reject(signal.reason));
					answer?.then(resolve, reject);
				})
		);
	}

	it('sends a request that carries a caller signal', async () => {
		expect(AbortSignal.any).toBeUndefined();
		const controller = new AbortController();
		const fetch = pendingFetch(Promise.resolve(json({ pumpId: 'P1', points: [] })));
		const api = new ApiClient({ baseUrl: BASE, fetch: fetch as typeof globalThis.fetch });
		const curve = await api.systemCurve(project, 'P1', { signal: controller.signal });
		expect(curve).toEqual({ pumpId: 'P1', points: [] });
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(fetch.mock.calls[0]![0]).toBe(`${BASE}/api/v1/system-curve`);
		expect(fetch.mock.calls[0]![1]!.signal).toBeInstanceOf(AbortSignal);
	});

	it('passes a caller abort through unchanged', async () => {
		const controller = new AbortController();
		const fetch = pendingFetch();
		const api = new ApiClient({ baseUrl: BASE, fetch: fetch as typeof globalThis.fetch });
		const pending = api.systemCurve(project, 'P1', { signal: controller.signal });
		controller.abort();
		const error = await rejection(pending);
		expect(error).toBeInstanceOf(DOMException);
		expect((error as DOMException).name).toBe('AbortError');
		expect(fetch).toHaveBeenCalledTimes(1);
	});

	it('rejects at once for a caller signal that is already aborted', async () => {
		const controller = new AbortController();
		controller.abort();
		const fetch = pendingFetch();
		const api = new ApiClient({ baseUrl: BASE, fetch: fetch as typeof globalThis.fetch });
		const error = await rejection(api.solve(project, {}, { signal: controller.signal }));
		expect((error as DOMException).name).toBe('AbortError');
	});

	it('still times out when the caller gives a signal', async () => {
		const controller = new AbortController();
		const fetch = pendingFetch();
		const api = new ApiClient({
			baseUrl: BASE,
			fetch: fetch as typeof globalThis.fetch,
			timeoutMs: 5
		});
		const error = await rejection(api.systemCurve(project, 'P1', { signal: controller.signal }));
		expect(error).toBeInstanceOf(NetworkError);
		expect((error as Error).message).toMatch(/did not answer in time/);
		expect(controller.signal.aborted).toBe(false);
	});

	it('removes its listener from the caller signal when the request settles', async () => {
		// The store's signal outlives many requests: listeners must not pile up on it.
		const controller = new AbortController();
		const added = vi.spyOn(controller.signal, 'addEventListener');
		const removed = vi.spyOn(controller.signal, 'removeEventListener');
		const { api } = client([json({ pumpId: 'P1', points: [] }), new TypeError('Failed to fetch')]);
		await api.systemCurve(project, 'P1', { signal: controller.signal });
		await rejection(api.systemCurve(project, 'P1', { signal: controller.signal }));
		expect(added).toHaveBeenCalledTimes(2);
		expect(removed.mock.calls).toEqual(
			added.mock.calls.map(([type, listener]) => [type, listener])
		);
	});
});

describe('configuration', () => {
	it('uses PUBLIC_API_URL, else http://localhost:8000', () => {
		expect(apiBaseUrl()).toBe(DEFAULT_API_URL);
		expect(DEFAULT_API_URL).toBe('http://localhost:8000');
		env.PUBLIC_API_URL = 'https://api.opensolve-pipe.app/ ';
		expect(apiBaseUrl()).toBe('https://api.opensolve-pipe.app');
		env.PUBLIC_API_URL = '   ';
		expect(apiBaseUrl()).toBe(DEFAULT_API_URL);
		expect(new ApiClient().baseUrl).toBe(DEFAULT_API_URL);
	});

	it('the shared client reads the base URL and global fetch at request time', async () => {
		const fetch = vi.fn(async () => json(library));
		vi.stubGlobal('fetch', fetch);
		env.PUBLIC_API_URL = 'https://api.test';
		await getLibrary();
		expect(fetch).toHaveBeenCalledWith('https://api.test/api/v1/library', expect.anything());
		fetch.mockResolvedValueOnce(json({ success: true, computeTime: 0, solvedState: {} }));
		await solve(project);
		expect(fetch).toHaveBeenLastCalledWith('https://api.test/api/v1/solve', expect.anything());
	});
});
