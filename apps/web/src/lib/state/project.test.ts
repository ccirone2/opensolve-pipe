import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NetworkError, TopologyError, ValidationError } from '../api/client';
import type { Project, SolveResponse, SystemCurveResponse } from '../api/types';
import { referentialIssues } from '../testing/helpers';
import { addBranch, deleteComponent, insertComponentInConnection } from '../utils/edit';
import { decodeProject, encodeProject, fragmentOf } from '../utils/encoding';
import { EXAMPLES } from '../utils/examples';
import { createComponent } from '../utils/factory';
import { schemaProblems } from '../utils/validate';
import { IMPERIAL_UNITS } from '../utils/units';
import {
	hydraulicFingerprint,
	MAX_HISTORY,
	ProjectStore,
	type ProjectStoreOptions,
	type Solver
} from './project.svelte';

const T0 = '2026-03-01T00:00:00.000Z';

function clock() {
	let n = 0;
	return () => new Date(Date.parse(T0) + 1000 * ++n).toISOString();
}

function setup(options: ProjectStoreOptions = {}, project: Project = EXAMPLES[0]!.create()) {
	const writes: string[] = [];
	const store = new ProjectStore(project, {
		writeUrl: (path) => writes.push(path),
		origin: 'https://opensolve-pipe.app',
		now: clock(),
		...options
	});
	return { store, writes };
}

function rename(name: string) {
	return (p: Project) => {
		p.metadata.name = name;
	};
}

/** A change that can change the results: the first pipe of the first connection gets longer. */
function lengthen(by: number) {
	return (p: Project) => {
		p.connections[0]!.piping.pipes[0]!.length += by;
	};
}

function solveResponse(methodVersion = '1.0.0'): SolveResponse {
	return {
		success: true,
		computeTime: 0.01,
		solvedState: { methodVersion, converged: true } as unknown as SolveResponse['solvedState']
	};
}

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (error: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

describe('loading', () => {
	it('starts from the given project with no history and no results', () => {
		const project = EXAMPLES[1]!.create();
		const { store, writes } = setup({}, project);
		expect(store.project).toEqual(project);
		expect(store.project).not.toBe(project); // a private copy
		expect(store.canUndo).toBe(false);
		expect(store.canRedo).toBe(false);
		expect(store.results).toEqual({
			response: null,
			stale: false,
			solving: false,
			error: null,
			errorStale: false
		});
		expect(store.encoded).toBe(encodeProject(project));
		expect(writes).toEqual([]); // the URL already holds an opened project
	});

	it('starts from an empty project by default', () => {
		const store = new ProjectStore(undefined, { writeUrl: () => {} });
		expect(store.project.components).toEqual([]);
		expect(schemaProblems(store.project)).toEqual([]);
	});

	it('resets history and results, and writes the URL when asked', () => {
		const { store, writes } = setup();
		store.update(rename('A'), 'Rename');
		store.load(EXAMPLES[2]!.create(), { writeUrl: true });
		expect(store.project.id).toBe('example-closed-loop');
		expect(store.canUndo).toBe(false);
		expect(writes).toEqual([`/p#${encodeProject(EXAMPLES[2]!.create())}`]);
		vi.runAllTimers();
		expect(writes).toHaveLength(1); // the pending write of the old project was cancelled
	});

	it('refuses an invalid project', () => {
		const { store } = setup();
		const bad = EXAMPLES[0]!.create();
		bad.connections[0]!.toComponentId = 'missing';
		expect(() => store.load(bad)).toThrow(/invalid project/);
		expect(store.project.id).toBe('example-pump-transfer');
	});

	it('keeps the stored project frozen', () => {
		const { store } = setup();
		expect(() => {
			(store.project.metadata as { name: string }).name = 'mutated';
		}).toThrow(TypeError);
		expect(() => store.project.components.push(store.project.components[0]!)).toThrow(TypeError);
	});
});

describe('update', () => {
	it('applies a change, records an undo step and the modified time', () => {
		const { store } = setup();
		const result = store.update(rename('Renamed'), 'Rename project');
		expect(result).toEqual({ ok: true, changed: true });
		expect(store.project.metadata.name).toBe('Renamed');
		expect(store.project.metadata.modified).toBe('2026-03-01T00:00:01.000Z');
		expect(store.project.metadata.created).toBe('2026-10-21T00:00:00Z');
		expect(store.canUndo).toBe(true);
		expect(store.undoLabel).toBe('Rename project');
	});

	it('accepts graph operations that return a new project', () => {
		const { store } = setup();
		expect(store.update((p) => addBranch(p, 'L3'), 'Add branch').ok).toBe(true);
		expect(store.project.components.map((c) => c.id)).toContain('T1');
		expect(
			store.update(
				(p) => insertComponentInConnection(p, 'L1', createComponent('gate', p)),
				'Add valve'
			).ok
		).toBe(true);
		expect(store.update((p) => deleteComponent(p, 'V1', { join: true }), 'Delete V1').ok).toBe(
			true
		);
		expect(referentialIssues(store.project)).toEqual([]);
		expect(store.undoDepth).toBe(3);
	});

	it('ignores changes that change nothing', () => {
		const { store } = setup();
		expect(store.update(rename(store.project.metadata.name), 'Rename')).toEqual({
			ok: true,
			changed: false
		});
		expect(store.update(() => {}, 'Nothing')).toEqual({ ok: true, changed: false });
		expect(store.canUndo).toBe(false);
		vi.runAllTimers();
		expect(store.syncPending).toBe(false);
	});

	it('refuses changes that would make the project invalid, leaving it unchanged', () => {
		const { store, writes } = setup();
		const before = store.project;
		const negative = store.update((p) => {
			(p.components[0] as { liquidLevel: number }).liquidLevel = -2;
		}, 'Level');
		expect(negative).toEqual({
			ok: false,
			problems: ['components[0] "R1" › liquidLevel: must be >= 0']
		});
		const dangling = store.update((p) => {
			p.connections[0]!.toComponentId = 'nowhere';
		}, 'Rewire');
		expect(dangling.ok).toBe(false);
		const nan = store.update((p) => {
			p.components[0]!.elevation = Number.NaN;
		}, 'Elevation');
		expect(nan.ok).toBe(false);
		const thrown = store.update((p) => deleteComponent(p, 'nope'), 'Delete');
		expect(thrown).toEqual({ ok: false, problems: ['There is no component "nope".'] });
		expect(store.project).toBe(before);
		expect(store.canUndo).toBe(false);
		vi.runAllTimers();
		expect(writes).toEqual([]);
	});

	it('merges a burst of edits with the same label when asked', () => {
		const { store } = setup();
		store.update(rename('a'), 'Name', { merge: true });
		store.update(rename('ab'), 'Name', { merge: true });
		store.update(rename('abc'), 'Name', { merge: true });
		expect(store.undoDepth).toBe(1);
		store.update(rename('abcd'), 'Other', { merge: true });
		expect(store.undoDepth).toBe(2);
		store.undo();
		store.update(rename('x'), 'Other', { merge: true }); // nothing to merge into after undo
		expect(store.undoDepth).toBe(2);
		store.undo();
		store.undo();
		expect(store.project.metadata.name).toBe('Pump transfer between two tanks');
	});
});

describe('undo and redo', () => {
	it('step back and forward through changes', () => {
		const { store } = setup();
		const original = store.project;
		store.update(rename('one'), 'One');
		store.update(rename('two'), 'Two');
		store.update(rename('three'), 'Three');

		expect(store.undo()).toBe(true);
		expect(store.project.metadata.name).toBe('two');
		expect(store.redoLabel).toBe('Three');
		expect(store.undo()).toBe(true);
		expect(store.project.metadata.name).toBe('one');
		expect(store.redo()).toBe(true);
		expect(store.project.metadata.name).toBe('two');
		expect(store.undoLabel).toBe('Two');
		expect(store.undo() && store.undo()).toBe(true);
		expect(store.project).toEqual(original);
		expect(store.canUndo).toBe(false);
		expect(store.undo()).toBe(false);
		expect(store.redoDepth).toBe(3);
	});

	it('clears redo when a new change is made after undo', () => {
		const { store } = setup();
		store.update(rename('one'), 'One');
		store.update(rename('two'), 'Two');
		store.undo();
		expect(store.canRedo).toBe(true);
		store.update(rename('other'), 'Other');
		expect(store.canRedo).toBe(false);
		expect(store.redo()).toBe(false);
		store.undo();
		expect(store.project.metadata.name).toBe('one');
	});

	it('restores graph edits exactly', () => {
		const { store } = setup();
		const original = structuredClone(store.project);
		store.update((p) => addBranch(p, 'L2'), 'Add branch');
		store.update((p) => deleteComponent(p, 'P1'), 'Delete pump');
		const edited = store.project;
		store.undo();
		store.undo();
		expect(store.project).toEqual(original);
		store.redo();
		store.redo();
		expect(store.project).toEqual(edited);
	});

	it(`keeps at most ${MAX_HISTORY} steps`, () => {
		const { store } = setup();
		for (let i = 1; i <= MAX_HISTORY + 5; i++) store.update(rename(`v${i}`), `Step ${i}`);
		expect(store.undoDepth).toBe(MAX_HISTORY);
		while (store.undo());
		expect(store.project.metadata.name).toBe('v5');
		expect(store.redoDepth).toBe(MAX_HISTORY);
	});

	it('honours a custom history depth', () => {
		const { store } = setup({ maxHistory: 2 });
		for (const name of ['a', 'b', 'c']) store.update(rename(name), name);
		expect(store.undoDepth).toBe(2);
	});
});

describe('URL sync', () => {
	it('writes the encoded project after a short pause, once per burst', () => {
		const { store, writes } = setup();
		store.update(rename('one'), 'One');
		store.update(rename('two'), 'Two');
		expect(writes).toEqual([]);
		expect(store.syncPending).toBe(true);
		vi.advanceTimersByTime(299);
		expect(writes).toEqual([]);
		vi.advanceTimersByTime(1);
		expect(writes).toHaveLength(1);
		expect(writes[0]).toBe(`/p#${encodeProject(store.project)}`);
		expect(decodeProject(fragmentOf(writes[0]!))).toEqual(store.project);
		expect(store.encoded).toBe(encodeProject(store.project));
	});

	it('writes after undo and redo too', () => {
		const { store, writes } = setup();
		store.update(rename('one'), 'One');
		vi.runAllTimers();
		store.undo();
		vi.runAllTimers();
		expect(decodeProject(fragmentOf(writes[1]!)).metadata.name).toBe(
			'Pump transfer between two tanks'
		);
		store.redo();
		vi.runAllTimers();
		expect(decodeProject(fragmentOf(writes[2]!)).metadata.name).toBe('one');
	});

	it('flushes on demand and gives the shareable link', () => {
		const { store, writes } = setup();
		store.update(rename('share me'), 'Rename');
		const url = store.shareLink();
		expect(writes).toHaveLength(1);
		expect(url).toBe(`https://opensolve-pipe.app/p#${encodeProject(store.project)}`);
		expect(store.url).toBe(url);
		expect(store.urlLength).toBe(url.length);
		expect(store.encodedLength).toBe(encodeProject(store.project).length);
		vi.runAllTimers();
		expect(writes).toHaveLength(1);
		store.flush(); // nothing pending
		expect(writes).toHaveLength(1);
	});

	it('copies on write: an earlier link still opens the earlier project', () => {
		const { store } = setup();
		const before = store.shareLink();
		store.update(rename('changed'), 'Rename');
		const after = store.shareLink();
		expect(after).not.toBe(before);
		expect(decodeProject(fragmentOf(before)).metadata.name).toBe('Pump transfer between two tanks');
		expect(decodeProject(fragmentOf(after)).metadata.name).toBe('changed');
	});

	it('warns when the link is longer than 8,000 characters', () => {
		const { store } = setup();
		expect(store.urlTooLong).toBe(false);
		// Incompressible names make the link long.
		let seed = 12345;
		const random = () => {
			seed = (seed * 1103515245 + 12345) % 2 ** 31;
			return seed;
		};
		const noise = (n: number) =>
			Array.from({ length: n }, () => 'abcdefghijklmnopqrstuvwxyz0123456789'[random() % 36]).join(
				''
			);
		const result = store.update((p) => {
			for (const component of p.components) component.name = noise(100);
			p.metadata.description = noise(5000);
			for (let i = 0; i < 60; i++) {
				p.pumpLibrary.push({ ...p.pumpLibrary[0]!, id: `X${i}`, name: noise(100) });
			}
		}, 'Long names');
		expect(result.ok).toBe(true);
		store.flush();
		expect(store.urlLength).toBeGreaterThan(8000);
		expect(store.urlTooLong).toBe(true);
		store.undo();
		store.flush();
		expect(store.urlTooLong).toBe(false);
	});

	it('uses history.replaceState by default, keeping the router state', () => {
		const replaceState = vi.fn();
		vi.stubGlobal('history', { state: { 'sveltekit:index': 3 }, replaceState });
		const store = new ProjectStore(EXAMPLES[0]!.create(), { now: clock() });
		store.update(rename('x'), 'Rename');
		vi.runAllTimers();
		expect(replaceState).toHaveBeenCalledTimes(1);
		expect(replaceState).toHaveBeenCalledWith(
			{ 'sveltekit:index': 3 },
			'',
			`/p#${encodeProject(store.project)}`
		);
	});

	it('stops pending writes when disposed', () => {
		const { store, writes } = setup();
		store.update(rename('x'), 'Rename');
		store.dispose();
		vi.runAllTimers();
		expect(writes).toEqual([]);
	});
});

describe('results', () => {
	it('stores a solve response and records the method version without an undo step', async () => {
		const solver: Solver = { solve: vi.fn(async () => solveResponse('2.1.0')) };
		const { store } = setup({ solver });
		const solving = store.solve({ includeSystemCurve: false });
		expect(store.results.solving).toBe(true);
		await solving;
		expect(solver.solve).toHaveBeenCalledWith(
			expect.objectContaining({ id: 'example-pump-transfer' }),
			{ includeSystemCurve: false }
		);
		expect(store.results).toMatchObject({ stale: false, solving: false, error: null });
		expect(store.solved?.methodVersion).toBe('2.1.0');
		expect(store.project.methodVersion).toBe('2.1.0');
		expect(store.canUndo).toBe(false);
	});

	it('keeps the method version the project was opened with, for the results notice', async () => {
		const shared = { ...EXAMPLES[0]!.create(), methodVersion: '1.0.0' };
		const { store } = setup({ solver: { solve: async () => solveResponse('1.1.0') } }, shared);
		expect(store.loadedMethodVersion).toBe('1.0.0');
		await store.solve();
		expect(store.project.methodVersion).toBe('1.1.0');
		expect(store.loadedMethodVersion).toBe('1.0.0');
		store.load(store.project);
		expect(store.loadedMethodVersion).toBe('1.1.0');
	});

	it('marks results stale after an edit, and fresh again after a new solve', async () => {
		const { store } = setup({ solver: { solve: async () => solveResponse() } });
		await store.solve();
		store.update(lengthen(5), 'Change length');
		expect(store.results.stale).toBe(true);
		expect(store.results.response).not.toBeNull();
		await store.solve();
		expect(store.results.stale).toBe(false);
		store.undo();
		expect(store.results.stale).toBe(true);
	});

	it('keeps results that arrive after an edit, marked stale', async () => {
		const pending = deferred<SolveResponse>();
		const { store } = setup({ solver: { solve: () => pending.promise } });
		const solving = store.solve();
		store.update(lengthen(5), 'Change length');
		pending.resolve(solveResponse('9.9.9'));
		await solving;
		expect(store.results.stale).toBe(true);
		expect(store.results.response).not.toBeNull();
		expect(store.project.methodVersion).toBe(''); // not solved with this version
	});

	it('ignores an older solve that finishes after a newer one', async () => {
		const first = deferred<SolveResponse>();
		const second = deferred<SolveResponse>();
		const calls = [first, second];
		const { store } = setup({ solver: { solve: () => calls.shift()!.promise } });
		const a = store.solve();
		const b = store.solve();
		second.resolve(solveResponse('2.0.0'));
		await b;
		first.resolve(solveResponse('1.0.0'));
		await a;
		expect(store.solved?.methodVersion).toBe('2.0.0');
	});

	it('reports topology, validation and network errors', async () => {
		const errors: unknown[] = [
			new TopologyError('No fixed-pressure boundary', [
				{ code: 'NO_BOUNDARY', message: 'Add a reservoir', componentIds: [], connectionIds: [] }
			]),
			new ValidationError('Invalid', ['body › project › id: bad'], 400),
			new NetworkError('Unreachable'),
			new Error('boom')
		];
		const { store } = setup({
			solver: {
				solve: async () => {
					throw errors.shift();
				}
			}
		});
		await store.solve();
		expect(store.results.error).toEqual({
			kind: 'topology',
			message: 'No fixed-pressure boundary',
			issues: [
				{ code: 'NO_BOUNDARY', message: 'Add a reservoir', componentIds: [], connectionIds: [] }
			]
		});
		expect(store.results.solving).toBe(false);
		await store.solve();
		expect(store.results.error).toEqual({
			kind: 'validation',
			message: 'Invalid',
			details: ['body › project › id: bad']
		});
		await store.solve();
		expect(store.results.error).toEqual({ kind: 'network', message: 'Unreachable' });
		await store.solve();
		expect(store.results.error).toEqual({ kind: 'network', message: 'boom' });
	});

	it('keeps the last good results when a later solve fails, stale only if the project changed', async () => {
		let fail = false;
		const { store } = setup({
			solver: {
				solve: async () => {
					if (fail) throw new NetworkError('Offline');
					return solveResponse();
				}
			}
		});
		await store.solve();
		fail = true;
		// The same project solved again: the kept results are still its results.
		await store.solve();
		expect(store.results.response).not.toBeNull();
		expect(store.results.stale).toBe(false);
		expect(store.results.error?.kind).toBe('network');
		expect(store.results.errorStale).toBe(false);
		// Changed, then a failed solve: the kept results are for the earlier project, and the
		// error is for the current one.
		store.update(lengthen(5), 'Change length');
		await store.solve();
		expect(store.results.stale).toBe(true);
		expect(store.results.error?.kind).toBe('network');
		expect(store.results.errorStale).toBe(false);
		// Changed again: now the error is about an earlier version too.
		store.update(lengthen(6), 'Change length');
		expect(store.results).toMatchObject({ stale: true, errorStale: true });
		store.undo();
		expect(store.results).toMatchObject({ stale: true, errorStale: false });
		store.clearResults();
		expect(store.results).toEqual({
			response: null,
			stale: false,
			solving: false,
			error: null,
			errorStale: false
		});
	});

	it('does not mark results stale for display units, names or metadata', async () => {
		const { store } = setup({ solver: { solve: async () => solveResponse() } });
		await store.solve();
		store.update((p) => {
			p.settings.units = { ...IMPERIAL_UNITS };
		}, 'Use US units');
		store.update(rename('Renamed'), 'Rename');
		store.update((p) => {
			p.components[0]!.name = 'Renamed tank';
		}, 'Rename tank');
		expect(store.results.stale).toBe(false);
		store.update(lengthen(5), 'Change length');
		expect(store.results.stale).toBe(true);
		// Undoing back to the solved project makes the results current again.
		store.undo();
		expect(store.results.stale).toBe(false);
	});

	it('marks an error stale after a change, so it is not shown as current', async () => {
		const { store } = setup({
			solver: {
				solve: async () => {
					throw new NetworkError('Offline');
				}
			}
		});
		await store.solve();
		expect(store.results).toMatchObject({ response: null, stale: false, errorStale: false });
		store.update(lengthen(5), 'Change length');
		expect(store.results).toMatchObject({ stale: true, errorStale: true });
	});

	it('fingerprints only what the solve depends on', () => {
		const project = EXAMPLES[0]!.create();
		const base = hydraulicFingerprint(project);
		const relabelled = structuredClone(project);
		relabelled.settings.units = { ...IMPERIAL_UNITS };
		relabelled.metadata.name = 'Other';
		relabelled.methodVersion = '9.9.9';
		relabelled.components[1]!.name = 'Other pump';
		expect(hydraulicFingerprint(relabelled)).toBe(base);
		const changed = structuredClone(project);
		changed.settings.siteElevation += 100;
		expect(hydraulicFingerprint(changed)).not.toBe(base);
		const fluid = structuredClone(project);
		fluid.fluid = { ...fluid.fluid, temperature: 300 } as Project['fluid'];
		expect(hydraulicFingerprint(fluid)).not.toBe(base);
	});

	it('drops a solve that finishes after the project was replaced', async () => {
		const pending = deferred<SolveResponse>();
		const { store } = setup({ solver: { solve: () => pending.promise } });
		const solving = store.solve();
		store.load(EXAMPLES[1]!.create());
		pending.resolve(solveResponse());
		await solving;
		expect(store.results.response).toBeNull();
	});
});

describe('system curves (D10: on demand, per solve)', () => {
	/** Let pending promise callbacks run. */
	async function settle() {
		for (let i = 0; i < 20; i++) await Promise.resolve();
	}

	function curve(pumpId: string, head: number): SystemCurveResponse {
		// Made-up test values.
		return {
			pumpId,
			flowRange: { min: 0, max: 0.01, unit: 'm³/s' },
			points: [{ flow: 0, head, converged: true, message: '' }],
			converged: [true]
		};
	}

	function curveSolver() {
		const calls: { project: Project; pumpId: string; signal?: AbortSignal }[] = [];
		const answers: ReturnType<typeof deferred<SystemCurveResponse>>[] = [];
		const solver: Solver = {
			solve: vi.fn(async () => solveResponse()),
			systemCurve: vi.fn((project: Project, pumpId: string, options?: { signal?: AbortSignal }) => {
				calls.push({ project, pumpId, signal: options?.signal });
				const answer = deferred<SystemCurveResponse>();
				answers.push(answer);
				return answer.promise;
			})
		};
		return { solver, calls, answers };
	}

	it('solves without system curves', async () => {
		const { solver } = curveSolver();
		const { store } = setup({ solver });
		await store.solve();
		expect(solver.solve).toHaveBeenCalledWith(expect.anything(), { includeSystemCurve: false });
	});

	it('computes a curve for the project exactly as solved, once per solve', async () => {
		const { solver, calls, answers } = curveSolver();
		const { store } = setup({ solver });
		const solved = store.project;
		await store.solve();
		const response = store.results.response;
		// The project as sent (the store then records the method version in its own copy).
		expect(solver.solve).toHaveBeenCalledWith(solved, { includeSystemCurve: false });
		expect(store.solvedProject).toBe(solved);
		// An edit after the solve: the curve is still the solved project's.
		store.update(lengthen(5), 'Change length');
		expect(store.results.stale).toBe(true);
		store.loadSystemCurve('P1');
		expect(store.systemCurve(response, 'P1')).toEqual({ status: 'loading' });
		await settle();
		expect(calls).toHaveLength(1);
		expect(calls[0]!.project).toBe(solved);
		expect(calls[0]!.project).not.toBe(store.project);
		expect(calls[0]!.pumpId).toBe('P1');
		answers[0]!.resolve(curve('P1', 12));
		await settle();
		expect(store.systemCurve(response, 'P1')).toEqual({ status: 'ready', curve: curve('P1', 12) });
		// Cached with the solve: asking again sends nothing.
		store.loadSystemCurve('P1');
		await settle();
		expect(calls).toHaveLength(1);
		// Never shown with another solve's results.
		expect(store.systemCurve(solveResponse(), 'P1')).toBeUndefined();
		expect(store.systemCurve(null, 'P1')).toBeUndefined();
	});

	it('drops the curves of an older solve, and never fills a newer solve with them', async () => {
		const { solver, calls, answers } = curveSolver();
		const { store } = setup({ solver });
		await store.solve();
		store.loadSystemCurve('P1');
		await settle();
		const first = calls[0]!;
		// A new solve starts: the request in flight is cancelled and said so.
		const solving = store.solve();
		expect(first.signal?.aborted).toBe(true);
		expect(store.systemCurve(store.results.response, 'P1')).toEqual({ status: 'cancelled' });
		await solving;
		// The new solve's cache is empty; the old answer arriving late changes nothing.
		const newer = store.results.response;
		expect(store.systemCurve(newer, 'P1')).toBeUndefined();
		answers[0]!.resolve(curve('P1', 99));
		await settle();
		expect(store.systemCurve(newer, 'P1')).toBeUndefined();
		store.loadSystemCurve('P1');
		await settle();
		expect(calls).toHaveLength(2);
		answers[1]!.resolve(curve('P1', 12));
		await settle();
		expect(store.systemCurve(newer, 'P1')).toEqual({ status: 'ready', curve: curve('P1', 12) });
		// Loading another project, or clearing the results, forgets them.
		store.clearResults();
		expect(store.solvedProject).toBeNull();
		expect(store.systemCurves).toEqual({});
	});

	it('sends one request at a time', async () => {
		// Two pump ids (the fake server answers for any id).
		const { solver, calls, answers } = curveSolver();
		const { store } = setup({ solver });
		await store.solve();
		store.loadSystemCurve('P1');
		store.loadSystemCurve('P2');
		await settle();
		expect(calls.map((c) => c.pumpId)).toEqual(['P1']);
		answers[0]!.resolve(curve('P1', 12));
		await settle();
		expect(calls.map((c) => c.pumpId)).toEqual(['P1', 'P2']);
		answers[1]!.reject(new NetworkError('Made-up failure.', 503));
		await settle();
		const response = store.results.response;
		expect(store.systemCurve(response, 'P2')).toEqual({
			status: 'error',
			message: 'Made-up failure.'
		});
		// A failure waits for a retry; then the curve is requested again.
		store.loadSystemCurve('P2');
		await settle();
		expect(calls).toHaveLength(2);
		store.loadSystemCurve('P2', { retry: true });
		await settle();
		expect(calls).toHaveLength(3);
		expect(store.systemCurve(response, 'P1')).toEqual({ status: 'ready', curve: curve('P1', 12) });
	});

	it('says so when the server offers no system curves', async () => {
		const { store } = setup({ solver: { solve: async () => solveResponse() } });
		store.loadSystemCurve('P1');
		expect(store.systemCurves).toEqual({}); // nothing solved yet
		await store.solve();
		store.loadSystemCurve('P1');
		expect(store.systemCurve(store.results.response, 'P1')).toMatchObject({ status: 'error' });
	});
});
