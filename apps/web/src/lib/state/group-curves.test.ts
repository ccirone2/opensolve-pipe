/**
 * Group curves in the store (CLAUDE.md D21, proposal pump-groups.md §6.1): fetched on demand for
 * the project exactly as solved, per case and set of pumps (in any order), cached with that
 * solve and dropped by the next; on the system curves' queue (one request at a time, after a
 * Solve all run and a goal seek); cancelled by a solve, a goal seek or the user; a refusal
 * (NOT_A_STATION) kept with its issues. The responses are the shared fixture's (real API
 * answers); the solver is a fake whose answers the test gives.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NetworkError, NotAStationError } from '../api/client';
import type {
	Project,
	PumpGroupCurveResponse,
	SolveResponse,
	SystemCurveResponse,
	TopologyIssue
} from '../api/types';
import { goalSeekResponse, systemCurveResponse } from '../testing/results';
import { testWorkspace } from '../testing/workspace';
import { pumpTransferExample } from '../utils/examples';
import fixture from '../utils/__fixtures__/pump-groups-input.json';
import { newGoal, newVariable, toRequest } from '../utils/goal-seek';
import { withScenarios } from '../utils/scenarios';
import { groupKey, ProjectStore, type Solver } from './project.svelte';

interface FixtureCase {
	name: string;
	project: Project;
	solve: SolveResponse;
	groupCurve: { status: number; body: unknown };
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;
const parallel = named('parallel-ideal');
const curveOf = (c: FixtureCase) => c.groupCurve.body as PumpGroupCurveResponse;

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (error: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

async function settle() {
	for (let i = 0; i < 20; i++) await Promise.resolve();
}

interface Call {
	project: Project;
	pumpIds: readonly string[];
	signal?: AbortSignal;
	scenarioId?: string;
}

/** A fake server: the solve answers at once (a copy of the fixture's), group curves when told. */
function groupSolver({ rejectOnAbort = false } = {}) {
	const calls: Call[] = [];
	const answers: ReturnType<typeof deferred<PumpGroupCurveResponse>>[] = [];
	const solver: Solver = {
		solve: vi.fn(async () => structuredClone(parallel.solve)),
		groupCurve: vi.fn((project: Project, pumpIds: readonly string[], options = {}) => {
			calls.push({ project, pumpIds, ...options });
			const answer = deferred<PumpGroupCurveResponse>();
			if (rejectOnAbort) {
				options.signal?.addEventListener('abort', () =>
					answer.reject(new DOMException('The operation was aborted.', 'AbortError'))
				);
			}
			answers.push(answer);
			return answer.promise;
		})
	};
	return { solver, calls, answers };
}

function setup(solver: Solver, project: Project = parallel.project) {
	return new ProjectStore(project, {
		writeUrl: () => {},
		origin: 'https://opensolve-pipe.app',
		solver
	});
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('group curves (D21: on demand, per solve and set of pumps)', () => {
	it('computes one for the project exactly as solved, keyed by the pumps in any order', async () => {
		const { solver, calls, answers } = groupSolver();
		const store = setup(solver);
		const solved = store.project;
		await store.solve();
		const response = store.results.response;
		store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 5;
		}, 'Change length');
		store.loadGroupCurve(['PB', 'PA']);
		expect(store.groupCurve(response, ['PA', 'PB'])).toEqual({ status: 'loading' });
		await settle();
		expect(calls).toHaveLength(1);
		expect(calls[0]!.project).toBe(solved);
		expect(calls[0]!.pumpIds).toEqual(['PA', 'PB']);
		expect(calls[0]).not.toHaveProperty('scenarioId');
		answers[0]!.resolve(curveOf(parallel));
		await settle();
		expect(store.groupCurve(response, ['PB', 'PA'])).toEqual({
			status: 'ready',
			response: curveOf(parallel)
		});
		// Cached with the solve; never shown with another solve's results.
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		expect(calls).toHaveLength(1);
		expect(store.groupCurve(structuredClone(parallel.solve), ['PA', 'PB'])).toBeUndefined();
		expect(groupKey(['PB', 'PA'])).toBe(groupKey(['PA', 'PB']));
		// One pump is not a group: nothing is sent.
		store.loadGroupCurve(['PA']);
		await settle();
		expect(calls).toHaveLength(1);
	});

	it("sends a scenario's id, and keeps each case's curves apart", async () => {
		const { solver, calls, answers } = groupSolver();
		const project = withScenarios(structuredClone(parallel.project), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const store = setup(solver, project);
		await store.solve();
		store.setCase('S1');
		await store.solve();
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		expect(calls[0]!.scenarioId).toBe('S1');
		answers[0]!.resolve(curveOf(parallel));
		await settle();
		expect(store.groupCurve(store.resultsFor('S1').response, ['PA', 'PB'])).toMatchObject({
			status: 'ready'
		});
		expect(store.groupCurve(store.resultsFor(null).response, ['PA', 'PB'])).toBeUndefined();
	});

	it('keeps a refusal with its issues, and does not ask again for that solve', async () => {
		const { solver, calls, answers } = groupSolver();
		const store = setup(solver);
		await store.solve();
		const refused = named('refused').groupCurve.body as {
			message: string;
			issues: TopologyIssue[];
		};
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		answers[0]!.reject(new NotAStationError(refused.message, [refused.message], refused.issues));
		await settle();
		const response = store.results.response;
		expect(store.groupCurve(response, ['PA', 'PB'])).toEqual({
			status: 'refused',
			message: refused.message,
			issues: refused.issues
		});
		store.loadGroupCurve(['PA', 'PB'], { retry: true });
		await settle();
		expect(calls).toHaveLength(1);
	});

	it('shares the system curves’ queue: one request at a time; a failure waits for a retry', async () => {
		const { solver, calls, answers } = groupSolver();
		const curves: ReturnType<typeof deferred<SystemCurveResponse>>[] = [];
		solver.systemCurve = vi.fn(() => {
			const answer = deferred<SystemCurveResponse>();
			curves.push(answer);
			return answer.promise;
		});
		const store = setup(solver);
		await store.solve();
		store.loadSystemCurve('PA');
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		expect(solver.systemCurve).toHaveBeenCalledTimes(1);
		expect(calls).toHaveLength(0);
		curves[0]!.resolve(systemCurveResponse());
		await settle();
		expect(calls).toHaveLength(1);
		answers[0]!.reject(new NetworkError('The server is busy.', 503, 'SERVER_BUSY'));
		await settle();
		const response = store.results.response;
		expect(store.groupCurve(response, ['PA', 'PB'])).toEqual({
			status: 'error',
			message: 'The server is busy.'
		});
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		expect(calls).toHaveLength(1);
		store.loadGroupCurve(['PA', 'PB'], { retry: true });
		await settle();
		expect(calls).toHaveLength(2);
	});

	it('cancels: the request is aborted, a late answer dropped, and it waits for a retry', async () => {
		const { solver, calls, answers } = groupSolver();
		const store = setup(solver);
		await store.solve();
		const response = store.results.response;
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		store.cancelGroupCurve(['PB', 'PA']);
		expect(calls[0]!.signal?.aborted).toBe(true);
		expect(store.groupCurve(response, ['PA', 'PB'])).toEqual({ status: 'cancelled', by: 'user' });
		answers[0]!.resolve(curveOf(parallel));
		await settle();
		expect(store.groupCurve(response, ['PA', 'PB'])).toEqual({ status: 'cancelled', by: 'user' });
		store.loadGroupCurve(['PA', 'PB'], { retry: true });
		await settle();
		answers[1]!.resolve(curveOf(parallel));
		await settle();
		expect(store.groupCurve(response, ['PA', 'PB'])).toMatchObject({ status: 'ready' });
	});

	it('a new solve cancels the curve in flight and drops it; its late answer fills nothing', async () => {
		const { solver, calls, answers } = groupSolver();
		const store = setup(solver);
		await store.solve();
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		const solving = store.solve();
		expect(calls[0]!.signal?.aborted).toBe(true);
		expect(store.groupCurve(store.results.response, ['PA', 'PB'])).toEqual({
			status: 'cancelled',
			by: 'solve'
		});
		await solving;
		const newer = store.results.response;
		expect(store.groupCurve(newer, ['PA', 'PB'])).toBeUndefined();
		answers[0]!.resolve(curveOf(parallel));
		await settle();
		expect(store.groupCurve(newer, ['PA', 'PB'])).toBeUndefined();
		store.clearResults();
		expect(store.groupCurve(newer, ['PA', 'PB'])).toBeUndefined();
	});

	it('a curve asked for while a solve is in flight waits for it: dropped unsent when the solve answers', async () => {
		const { solver, calls, answers } = groupSolver();
		const solves: ReturnType<typeof deferred<SolveResponse>>[] = [];
		solver.solve = vi.fn((_project, _options, request = {}) => {
			const answer = deferred<SolveResponse>();
			request.signal?.addEventListener('abort', () =>
				answer.reject(new DOMException('The operation was aborted.', 'AbortError'))
			);
			solves.push(answer);
			return answer.promise;
		});
		const curves: string[] = [];
		solver.systemCurve = vi.fn((_project, pumpId: string) => {
			curves.push(pumpId);
			return new Promise<SystemCurveResponse>(() => {});
		});
		const store = setup(solver);
		const first = store.solve();
		solves[0]!.resolve(structuredClone(parallel.solve));
		await first;
		const response = store.results.response;

		// Solve again; while it is in flight the card ticks a box, and the chart asks for a curve.
		const solving = store.solve();
		expect(store.calculating).toBe('solve');
		store.loadGroupCurve(['PA', 'PB']);
		store.loadSystemCurve('PA');
		await settle();
		expect(calls).toEqual([]);
		expect(curves).toEqual([]);
		solves[1]!.resolve(structuredClone(parallel.solve));
		await solving;
		await settle();
		// The solve replaced the response: neither request was sent, and nothing is filled.
		expect(calls).toEqual([]);
		expect(curves).toEqual([]);
		expect(store.results.response).not.toBe(response);
		expect(store.groupCurve(store.results.response, ['PA', 'PB'])).toBeUndefined();

		// A solve that fails keeps the response: the curve asked for meanwhile goes after it.
		const kept = store.results.response;
		const failing = store.solve();
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		expect(calls).toEqual([]);
		solves[2]!.reject(new NetworkError('No connection.', 0));
		await failing;
		await settle();
		expect(store.results.response).toBe(kept);
		expect(calls).toHaveLength(1);
		answers[0]!.resolve(curveOf(parallel));
		await settle();
		expect(store.groupCurve(kept, ['PA', 'PB'])).toMatchObject({ status: 'ready' });

		// A solve cancelled likewise: the curve waits for it, then goes.
		const cancelled = store.solve();
		store.loadSystemCurve('PB');
		await settle();
		expect(curves).toEqual([]);
		expect(store.cancelSolve()).toBe(true);
		await cancelled;
		await settle();
		expect(store.results.response).toBe(kept);
		expect(curves).toEqual(['PB']);
	});

	it('a goal seek cancels the curve in flight, and new ones wait for it', async () => {
		const { solver, calls, answers } = groupSolver({ rejectOnAbort: true });
		const goal = deferred<ReturnType<typeof goalSeekResponse>>();
		solver.goalSeek = vi.fn(() => goal.promise);
		const store = setup(solver);
		await store.solve();
		store.loadGroupCurve(['PA', 'PB']);
		await settle();
		const request = toRequest(
			{
				goals: [{ ...newGoal({ elementId: 'L2' }, 'link_flow'), target: 0.05 }],
				variables: [
					newVariable(store.project, {
						target: { kind: 'component', componentId: 'PA' },
						field: 'speed'
					})
				]
			},
			store.project,
			null
		);
		const running = store.runGoalSeek(request);
		expect(calls[0]!.signal?.aborted).toBe(true);
		expect(store.groupCurve(store.results.response, ['PA', 'PB'])).toEqual({
			status: 'cancelled',
			by: 'goalSeek'
		});
		store.loadGroupCurve(['PA', 'PB'], { retry: true });
		await settle();
		expect(calls).toHaveLength(1);
		goal.resolve(goalSeekResponse());
		await running;
		await settle();
		expect(calls).toHaveLength(2);
		answers[1]!.resolve(curveOf(parallel));
		await settle();
		expect(store.groupCurve(store.results.response, ['PA', 'PB'])).toMatchObject({
			status: 'ready'
		});
	});

	it('says so when the server offers no group curves', async () => {
		const store = setup({ solve: async () => structuredClone(parallel.solve) });
		await store.solve();
		store.loadGroupCurve(['PA', 'PB']);
		expect(store.groupCurve(store.results.response, ['PA', 'PB'])).toEqual({
			status: 'error',
			message: 'Group curves are not available from this server.'
		});
	});
});

describe('the group in page state keeps its pumps’ ids from new elements', () => {
	it('a member deleted and a new pump added never takes its place, until the group lets go', () => {
		const ws = testWorkspace(pumpTransferExample());
		expect(ws.store.project.components.some((c) => c.id === 'P2')).toBe(false);
		// P2 was ticked, then deleted: its slot still names it.
		ws.pumpGroup = ['P1', null, 'P2'];
		expect(ws.reservedIds).toEqual(expect.arrayContaining(['P1', 'P2']));
		expect(ws.addStandalone('pump')).toBe('P3');
		ws.undo();
		ws.pumpGroup = ['P1'];
		expect(ws.addStandalone('pump')).toBe('P2');
	});
});
