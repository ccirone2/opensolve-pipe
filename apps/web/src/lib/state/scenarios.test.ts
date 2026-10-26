/**
 * The store with scenarios (proposal scenario-manager.md §6.8-6.10): results, staleness and system
 * curves per case; requests that name the scenario (and the base's that does not); Solve all (the
 * order, the cases it skips, the snapshot, a case's own error against a network stop, Cancel and
 * resuming); undo and redo show the case a change was made in; base edits carry pipe changes; a
 * project without scenarios encodes and solves exactly as before.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NetworkError, TopologyError } from '../api/client';
import type { Override, Project, Scenario, SolveResponse, SystemCurveResponse } from '../api/types';
import { deleteComponent, updateComponent, updateConnection } from '../utils/edit';
import { encodeProject } from '../utils/encoding';
import { pumpTransferExample } from '../utils/examples';
import { systemCurvePoint } from '../testing/results';
import { removePipe, addPipe } from '../utils/piping';
import { withScenarios } from '../utils/scenarios';
import { ProjectStore, type Solver } from './project.svelte';

/** Made-up responses, told apart by the case solved. */
function responseFor(scenarioId: string | undefined, version = '1.2.0'): SolveResponse {
	return {
		success: true,
		computeTime: 0.01,
		solvedState: {
			methodVersion: version,
			converged: true,
			case: scenarioId ?? 'base'
		} as unknown as SolveResponse['solvedState'],
		scenario: null
	};
}

interface Call {
	project: Project;
	scenarioId: string | undefined;
	request: { signal?: AbortSignal; scenarioId?: string } | undefined;
	resolve: (response: SolveResponse) => void;
	reject: (error: unknown) => void;
}

/** A server whose answers the test gives, one call at a time. */
function heldSolver() {
	const calls: Call[] = [];
	const solver: Solver = {
		solve: (project, _options, request) =>
			new Promise<SolveResponse>((resolve, reject) => {
				calls.push({ project, scenarioId: request?.scenarioId, request, resolve, reject });
				request?.signal?.addEventListener('abort', () =>
					reject(new DOMException('The operation was aborted.', 'AbortError'))
				);
			})
	};
	return { solver, calls };
}

/** A server that answers at once. */
function answeringSolver() {
	const calls: { scenarioId: string | undefined; request: unknown }[] = [];
	const solver: Solver = {
		solve: vi.fn(async (_project: Project, _options, request) => {
			calls.push({ scenarioId: request?.scenarioId, request });
			return responseFor(request?.scenarioId);
		})
	};
	return { solver, calls };
}

const LEVEL = (value: number): Override => ({
	kind: 'component',
	componentId: 'R2',
	field: 'liquidLevel',
	value
});

function twoScenarios(): Project {
	const scenarios: Scenario[] = [
		{ id: 'S1', name: 'Higher tank', overrides: [LEVEL(6)] },
		{
			id: 'S2',
			name: 'Slower pump',
			overrides: [{ kind: 'component', componentId: 'P1', field: 'speed', value: 0.9 }]
		}
	];
	return withScenarios(pumpTransferExample(), scenarios);
}

function setup(solver: Solver, project: Project = twoScenarios()) {
	return new ProjectStore(project, {
		writeUrl: () => {},
		origin: 'https://opensolve-pipe.app',
		solver
	});
}

/** Let pending promise callbacks run. */
async function settle() {
	for (let i = 0; i < 30; i++) await Promise.resolve();
}

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

describe('results per case', () => {
	it('solves the case shown: a scenario names itself, the base sends the plain request', async () => {
		const { solver, calls } = answeringSolver();
		const store = setup(solver);
		await store.solve();
		store.setCase('S1');
		await store.solve();
		expect(calls[0]!.request).toEqual({ signal: expect.any(AbortSignal) });
		expect(calls[1]!.request).toEqual({ signal: expect.any(AbortSignal), scenarioId: 'S1' });
		// Each case keeps its own response; `results` is the active case's.
		expect(store.results.response?.solvedState).toMatchObject({ case: 'S1' });
		expect(store.resultsFor(null).response?.solvedState).toMatchObject({ case: 'base' });
		store.setCase(null);
		expect(store.results.response?.solvedState).toMatchObject({ case: 'base' });
		expect(store.caseStatus(null)).toBe('solved');
		expect(store.caseStatus('S2')).toBe('not_solved');
	});

	it('makes only the edited case out of date; labels make none; a base edit makes all', async () => {
		const { solver } = answeringSolver();
		const store = setup(solver);
		await store.solveAll();
		expect(store.caseIds.map((c) => store.caseStatus(c))).toEqual(['solved', 'solved', 'solved']);
		// A change of S1's values: S1 only.
		store.update((p) => {
			p.scenarios![0]!.overrides = [LEVEL(7)];
		}, 'change liquid level in Higher tank');
		expect(store.caseIds.map((c) => store.resultsFor(c).stale)).toEqual([false, true, false]);
		// Renaming and reordering scenarios: labels only.
		store.update((p) => {
			p.scenarios![1]!.name = 'Pump at 90 %';
			p.scenarios!.reverse();
		}, 'rename scenario');
		expect(store.caseIds.map((c) => store.resultsFor(c).stale)).toEqual([false, false, true]);
		// A base edit: every case (conservative, never stale results shown as current).
		store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change pipe length');
		expect([null, 'S1', 'S2'].map((c) => store.resultsFor(c).stale)).toEqual([true, true, true]);
	});

	it('drops the results of a deleted scenario, and shows the base case if it was shown', async () => {
		const { solver } = answeringSolver();
		const store = setup(solver);
		store.setCase('S2');
		await store.solve();
		store.update((p) => withScenarios(p, p.scenarios!.slice(0, 1)), 'delete scenario');
		expect(store.activeCase).toBeNull();
		expect(store.resultsFor('S2').response).toBeNull();
		// Undo brings the scenario back (not its results: they were dropped with it).
		store.undo();
		expect(store.activeCase).toBe('S2');
		expect(store.resultsFor('S2').response).toBeNull();
	});

	it('keeps system curves per case, sent with the scenario id and the flow range asked for', async () => {
		const curves: { pumpId: string; options: unknown }[] = [];
		const curve: SystemCurveResponse = {
			pumpId: 'P1',
			flowRange: { min: 0, max: 0.03, unit: 'm³/s' },
			points: [systemCurvePoint({ flow: 0, head: 10, converged: true })],
			converged: [true],
			scenario: null
		};
		const solver: Solver = {
			solve: async (_p, _o, request) => responseFor(request?.scenarioId),
			systemCurve: vi.fn(async (_project: Project, pumpId: string, options?: object) => {
				const { signal, ...rest } = (options ?? {}) as { signal?: AbortSignal };
				void signal;
				curves.push({ pumpId, options: rest });
				return curve;
			})
		};
		const store = setup(solver);
		await store.solveAll();
		store.loadSystemCurve('P1');
		store.loadSystemCurve('P1', { caseId: 'S1', range: { flowMin: 0, flowMax: 0.03 } });
		await settle();
		expect(curves).toEqual([
			{ pumpId: 'P1', options: {} },
			{ pumpId: 'P1', options: { scenarioId: 'S1', flowMin: 0, flowMax: 0.03 } }
		]);
		const s1 = store.resultsFor('S1').response;
		expect(store.systemCurve(s1, 'P1', { flowMin: 0, flowMax: 0.03 })).toEqual({
			status: 'ready',
			curve
		});
		// The overlay is not the case's own curve, and the base's curve is the base's only.
		expect(store.systemCurve(s1, 'P1')).toBeUndefined();
		expect(store.systemCurve(store.resultsFor(null).response, 'P1')).toEqual({
			status: 'ready',
			curve
		});
		// A new solve of S1 drops S1's curves only.
		store.setCase('S1');
		await store.solve();
		expect(
			store.systemCurve(store.resultsFor('S1').response, 'P1', { flowMin: 0, flowMax: 0.03 })
		).toBeUndefined();
		expect(store.systemCurve(store.resultsFor(null).response, 'P1')).toMatchObject({
			status: 'ready'
		});
	});

	it('gives the case as solved for inputs shown as entered', async () => {
		const { solver } = answeringSolver();
		const store = setup(solver);
		store.setCase('S1');
		await store.solve();
		const inputs = store.caseInputs();
		expect(inputs?.components.find((c) => c.id === 'R2')).toMatchObject({ liquidLevel: 6 });
		expect(inputs?.scenarios).toBeUndefined();
		expect(store.caseInputs(null)).toBeNull();
	});
});

describe('Solve all', () => {
	it('solves the base, then the scenarios in order, one at a time, from a snapshot', async () => {
		const { solver, calls } = heldSolver();
		const store = setup(solver);
		const snapshot = store.project;
		const run = store.solveAll();
		expect(store.run).toEqual({ cases: [null, 'S1', 'S2'], index: 0 });
		expect(store.caseStatus(null)).toBe('solving');
		expect(store.caseStatus('S1')).toBe('waiting');
		expect(calls).toHaveLength(1);
		// An edit during the run: the run goes on from the snapshot; its results are stale.
		store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 1;
		}, 'change pipe length');
		calls[0]!.resolve(responseFor(undefined));
		await settle();
		expect(calls).toHaveLength(2);
		expect(calls[1]!.scenarioId).toBe('S1');
		expect(calls[1]!.project).toBe(snapshot);
		calls[1]!.resolve(responseFor('S1'));
		await settle();
		calls[2]!.resolve(responseFor('S2'));
		await run;
		expect(store.run).toBeNull();
		expect(calls.map((c) => c.scenarioId)).toEqual([undefined, 'S1', 'S2']);
		expect(store.caseIds.map((c) => store.caseStatus(c))).toEqual(['stale', 'stale', 'stale']);
	});

	it('skips cases with current results or a current topology error', async () => {
		const { solver, calls } = heldSolver();
		const store = setup(solver);
		const first = store.solve();
		calls[0]!.resolve(responseFor(undefined));
		await first;
		store.setCase('S1');
		const second = store.solve();
		calls[1]!.reject(new TopologyError('Made-up topology error.', []));
		await second;
		expect(store.casesToSolve()).toEqual(['S2']);
		const run = store.solveAll();
		expect(calls[2]!.scenarioId).toBe('S2');
		calls[2]!.resolve(responseFor('S2'));
		await run;
		expect(calls).toHaveLength(3);
		expect(store.casesToSolve()).toEqual([]);
		// Nothing to solve: Solve all does nothing.
		await store.solveAll();
		expect(calls).toHaveLength(3);
	});

	it("records a case's own error and goes on; a network error stops the run, and it resumes", async () => {
		const { solver, calls } = heldSolver();
		const store = setup(solver);
		const run = store.solveAll();
		calls[0]!.reject(new TopologyError('Made-up topology error.', []));
		await settle();
		expect(calls).toHaveLength(2);
		calls[1]!.reject(new NetworkError('Made-up: the server is busy.', 503, 'SERVER_BUSY'));
		await run;
		expect(calls).toHaveLength(2); // stopped: S2 not sent
		expect(store.resultsFor(null).error?.kind).toBe('topology');
		expect(store.resultsFor('S1').error).toEqual({
			kind: 'network',
			message: 'Made-up: the server is busy.',
			code: 'SERVER_BUSY'
		});
		expect(store.caseStatus('S2')).toBe('not_reached');
		expect(store.runStop).toEqual({ reason: 'network', message: 'Made-up: the server is busy.' });
		// Resume: the cases still missing (the network failure and the one not reached).
		expect(store.casesToSolve()).toEqual(['S1', 'S2']);
		const again = store.solveAll();
		expect(store.caseStatus('S2')).toBe('waiting');
		calls[2]!.resolve(responseFor('S1'));
		await settle();
		calls[3]!.resolve(responseFor('S2'));
		await again;
		expect(store.runStop).toBeNull();
		expect(['S1', 'S2'].map((c) => store.caseStatus(c))).toEqual(['solved', 'solved']);
	});

	it('Cancel aborts the request in flight and skips the rest; solved cases keep their results', async () => {
		const { solver, calls } = heldSolver();
		const store = setup(solver);
		const run = store.solveAll();
		calls[0]!.resolve(responseFor(undefined));
		await settle();
		expect(store.cancelSolve()).toBe(true);
		await run;
		expect(calls[1]!.request?.signal?.aborted).toBe(true);
		expect(calls).toHaveLength(2);
		expect(store.run).toBeNull();
		expect(store.runStop).toEqual({ reason: 'cancelled' });
		expect(store.caseStatus(null)).toBe('solved');
		expect(store.caseStatus('S1')).toBe('cancelled');
		expect(store.caseStatus('S2')).toBe('not_solved');
		expect(store.cancelSolve()).toBe(false);
	});

	it('a system curve asked for during the run waits for it to end', async () => {
		const { solver, calls } = heldSolver();
		const sent: string[] = [];
		solver.systemCurve = async (_p, pumpId) => {
			sent.push(pumpId);
			return {
				pumpId,
				flowRange: { min: 0, max: 1, unit: 'm³/s' },
				points: [],
				converged: [],
				scenario: null
			};
		};
		const store = setup(solver);
		const run = store.solveAll();
		calls[0]!.resolve(responseFor(undefined));
		await settle();
		store.loadSystemCurve('P1', { caseId: null });
		await settle();
		expect(sent).toEqual([]);
		calls[1]!.resolve(responseFor('S1'));
		await settle();
		calls[2]!.resolve(responseFor('S2'));
		await run;
		await settle();
		expect(sent).toEqual(['P1']);
	});
});

describe('history and edits', () => {
	it('undo and redo show the case a change was made in', () => {
		const store = setup(answeringSolver().solver);
		store.setCase('S1');
		store.update((p) => {
			p.scenarios![0]!.overrides = [LEVEL(8)];
		}, 'change liquid level in Higher tank');
		store.setCase(null);
		expect(store.undo()).toBe(true);
		expect(store.activeCase).toBe('S1');
		store.setCase('S2');
		expect(store.redo()).toBe(true);
		expect(store.activeCase).toBe('S1');
		// A scenario added in the base case: undoing it shows the base case.
		store.setCase(null);
		store.update(
			(p) => withScenarios(p, [...p.scenarios!, { id: 'S3', name: 'Three', overrides: [] }]),
			'add scenario'
		);
		store.setCase('S3');
		store.undo();
		expect(store.activeCase).toBeNull();
	});

	it('carries pipe changes through base edits and says what happened to removed ones', () => {
		const project = pumpTransferExample();
		const withPipes = {
			...project,
			connections: project.connections.map((c) =>
				c.id === 'L3'
					? { ...c, piping: addPipe(c.piping, { ...c.piping.pipes[0]!, length: 7 }) }
					: c
			)
		};
		const store = setup(
			answeringSolver().solver,
			withScenarios(withPipes, [
				{
					id: 'S1',
					name: 'Winter',
					overrides: [
						{ kind: 'pipe', connectionId: 'L3', pipeIndex: 1, field: 'length', value: 70 }
					]
				}
			])
		);
		// The first pipe goes: the change follows its pipe to index 0.
		let result = store.update(
			(p) => updateConnection(p, 'L3', (c) => ({ ...c, piping: removePipe(c.piping, 0) })),
			'remove pipe'
		);
		expect(result).toEqual({ ok: true, changed: true });
		expect(store.project.scenarios![0]!.overrides).toEqual([
			{ kind: 'pipe', connectionId: 'L3', pipeIndex: 0, field: 'length', value: 70 }
		]);
		store.undo();
		// Its own pipe goes: the change goes with it, and a note says so.
		result = store.update(
			(p) => updateConnection(p, 'L3', (c) => ({ ...c, piping: removePipe(c.piping, 1) })),
			'remove pipe'
		);
		expect(result).toMatchObject({
			ok: true,
			notes: [expect.stringMatching(/^Pipe 2 of connection L3 removed/)]
		});
		expect(store.project.scenarios![0]!.overrides).toEqual([]);
		store.undo();
		expect(store.project.scenarios![0]!.overrides).toHaveLength(1);
		// A deleted component: its changes are kept.
		store.update((p) => deleteComponent(p, 'V1'), 'delete valve');
		expect(store.project.scenarios![0]!.overrides).toHaveLength(1);
	});

	it('a project without scenarios encodes and solves as before', async () => {
		const project = pumpTransferExample();
		const { solver, calls } = answeringSolver();
		const store = setup(solver, project);
		expect(store.encoded).toBe(encodeProject(project));
		store.update(
			(p) => withScenarios(p, [{ id: 'S1', name: 'One', overrides: [] }]),
			'add scenario'
		);
		store.update((p) => withScenarios(p, []), 'delete scenario');
		expect('scenarios' in store.project).toBe(false);
		vi.runAllTimers();
		const { metadata: _a, ...now } = store.project;
		const { metadata: _b, ...before } = project;
		void _a;
		void _b;
		expect(now).toEqual(before);
		await store.solve();
		expect(calls[0]!.request).toEqual({ signal: expect.any(AbortSignal) });
		// An edit through the store with no scenarios adds no notes.
		expect(
			store.update((p) => updateComponent(p, 'P1', (c) => ({ ...c, name: 'X' })), 'rename')
		).toEqual({ ok: true, changed: true });
	});
});
