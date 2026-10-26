/**
 * Goal seek in the store and the workspace (proposal goal-seek.md §6.8, §6.10, §6.11, §6.15): one
 * request at a time (refused, never dropped), Cancel, staleness by the case key whether or not
 * the project has results, Apply as one undo step, page state reset on load, and ids a setup names
 * kept from new elements. The solver is a fake; responses are made up (testing/results.ts).
 */
import { describe, expect, it, vi } from 'vitest';
import { NetworkError, NotFoundError, TopologyError, ValidationError } from '../api/client';
import type { Component, GoalSeekResponse, Override, Project, SolveResponse } from '../api/types';
import {
	goalSeekResponse,
	pumpTransferSolved,
	response,
	systemCurveResponse
} from '../testing/results';
import { testWorkspace } from '../testing/workspace';
import { updateComponent } from '../utils/edit';
import { pumpTransferExample } from '../utils/examples';
import { newGoal, newVariable, toRequest, type GoalSeekSetup } from '../utils/goal-seek';
import { elementSummary, solvedPipe } from '../utils/results';
import { withScenarios } from '../utils/scenarios';
import { finishedGoalSeek, ProjectStore, type Solver } from './project.svelte';

const P1 = { kind: 'component', componentId: 'P1' } as const;

function setupFor(project: Project): GoalSeekSetup {
	return {
		goals: [{ ...newGoal({ elementId: 'L2' }, 'link_flow'), target: 0.015 }],
		variables: [newVariable(project, { target: P1, field: 'speed' })]
	};
}

/** A goal-seek solver whose answers wait until released (the latest request first). */
function heldGoalSeek() {
	const pending: {
		resolve: (r: GoalSeekResponse) => void;
		reject: (e: unknown) => void;
		signal?: AbortSignal;
		scenarioId?: string;
	}[] = [];
	const goalSeek = vi.fn(
		(_p: Project, _s: unknown, request?: { signal?: AbortSignal; scenarioId?: string }) =>
			new Promise<GoalSeekResponse>((resolve, reject) => {
				pending.push({
					resolve,
					reject,
					...(request?.signal ? { signal: request.signal } : {}),
					...(request?.scenarioId ? { scenarioId: request.scenarioId } : {})
				});
			})
	);
	const solve = vi.fn(async () => response(pumpTransferSolved()));
	return {
		solver: { solve, goalSeek } satisfies Solver,
		solve,
		goalSeek,
		pending,
		answer: (r: GoalSeekResponse = goalSeekResponse()) => pending.at(-1)?.resolve(r),
		fail: (e: unknown) => pending.at(-1)?.reject(e)
	};
}

function store(project: Project, solver: Solver) {
	return new ProjectStore(project, { writeUrl: () => {}, solver });
}

const speedFaster = (p: Project) =>
	updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.95 }) as Component);

describe('the store runs one goal seek at a time, and only Cancel stops it', () => {
	it('runs, answers, and records the run as sent', async () => {
		const held = heldGoalSeek();
		const s = store(pumpTransferExample(), held.solver);
		const request = toRequest(setupFor(s.project), s.project, null);
		expect(s.calculating).toBeNull();
		const running = s.runGoalSeek(request);
		expect(s.goalSeek?.status).toBe('running');
		expect(s.calculating).toBe('goalSeek');
		expect(held.goalSeek).toHaveBeenCalledWith(
			s.project,
			{ variables: request.variables, goals: request.goals },
			{ signal: expect.any(AbortSignal) }
		);
		held.answer();
		expect(await running).toBe(true);
		const done = s.goalSeek;
		expect(done).toMatchObject({
			status: 'done',
			stale: false,
			applied: null,
			appliedCurrent: false
		});
		expect(done?.run.request).toBe(request);
		expect(s.calculating).toBeNull();
	});

	it('fails with each kind of error, the not-found issues kept', async () => {
		const errors = [
			[new TopologyError('cannot', []), 'topology'],
			[new ValidationError('rejected', ['body.goals.0: x'], 400, 'VALIDATION_ERROR'), 'validation'],
			[new ValidationError('fluid', [], 400, 'FLUID_ERROR'), 'validation'],
			[
				new NotFoundError(
					'missing',
					[],
					[{ code: 'X', message: 'm', componentIds: ['P9'], connectionIds: [] }]
				),
				'validation'
			],
			[new NetworkError('busy', 503, 'SERVER_BUSY'), 'network']
		] as const;
		for (const [error, kind] of errors) {
			const held = heldGoalSeek();
			const s = store(pumpTransferExample(), held.solver);
			const running = s.runGoalSeek(toRequest(setupFor(s.project), s.project, null));
			held.fail(error);
			await running;
			expect(s.goalSeek).toMatchObject({ status: 'failed', response: null, error: { kind } });
		}
		const held = heldGoalSeek();
		const s = store(pumpTransferExample(), held.solver);
		const running = s.runGoalSeek(toRequest(setupFor(s.project), s.project, null));
		held.fail(errors[3][0]);
		await running;
		const failed = s.goalSeek;
		expect(
			failed && 'error' in failed && failed.error?.kind === 'validation'
				? failed.error.issues
				: null
		).toEqual([{ code: 'X', message: 'm', componentIds: ['P9'], connectionIds: [] }]);
	});

	it('Cancel aborts the request, drops a late answer and keeps the result before it', async () => {
		const held = heldGoalSeek();
		const s = store(pumpTransferExample(), held.solver);
		const request = toRequest(setupFor(s.project), s.project, null);
		const first = s.runGoalSeek(request);
		held.answer();
		await first;
		const before = s.goalSeek;
		const second = s.runGoalSeek(request);
		expect(s.goalSeek).toMatchObject({ status: 'running', previous: before });
		expect(s.cancelGoalSeek()).toBe(true);
		expect(held.pending[1]!.signal!.aborted).toBe(true);
		expect(s.goalSeek).toMatchObject({ status: 'cancelled', previous: before });
		held.answer(goalSeekResponse({ met: false, stopReason: 'no_progress' }));
		await second;
		expect(s.goalSeek).toMatchObject({ status: 'cancelled', previous: before });
		expect(s.cancelGoalSeek()).toBe(false);
	});

	it("the header's cancelSolve() cancels a goal seek", async () => {
		const held = heldGoalSeek();
		const s = store(pumpTransferExample(), held.solver);
		const running = s.runGoalSeek(toRequest(setupFor(s.project), s.project, null));
		expect(s.cancelSolve()).toBe(true);
		expect(s.goalSeek?.status).toBe('cancelled');
		expect(held.pending[0]!.signal!.aborted).toBe(true);
		held.answer();
		await running;
		expect(s.goalSeek?.status).toBe('cancelled');
	});

	it('refuses a solve or Solve all during a goal seek, and a goal seek during a solve', async () => {
		const held = heldGoalSeek();
		const s = store(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Winter', overrides: [] }]),
			held.solver
		);
		const request = toRequest(setupFor(s.project), s.project, null);
		const running = s.runGoalSeek(request);
		await s.solve();
		await s.solveAll();
		expect(held.solve).not.toHaveBeenCalled();
		expect(s.goalSeek?.status).toBe('running');
		expect(held.pending[0]!.signal!.aborted).toBe(false);
		expect(await s.runGoalSeek(request)).toBe(false);
		expect(held.goalSeek).toHaveBeenCalledTimes(1);
		held.answer();
		await running;

		let release: () => void = () => {};
		held.solve.mockImplementationOnce(
			() =>
				new Promise<SolveResponse>(
					(resolve) => (release = () => resolve(response(pumpTransferSolved())))
				)
		);
		const solving = s.solve();
		expect(s.calculating).toBe('solve');
		expect(await s.runGoalSeek(request)).toBe(false);
		expect(held.goalSeek).toHaveBeenCalledTimes(1);
		release();
		await solving;
		const all = s.solveAll();
		expect(s.calculating).toBe('solveAll');
		expect(await s.runGoalSeek(request)).toBe(false);
		await all;
		expect(held.goalSeek).toHaveBeenCalledTimes(1);
	});

	it('cancels a system curve in flight when it starts, and new curves wait for it', async () => {
		const held = heldGoalSeek();
		let curveSignal: AbortSignal | undefined;
		// A request that answers only when aborted (as fetch rejects then), else never.
		const systemCurve = vi.fn((_p: Project, _id: string, options?: { signal?: AbortSignal }) => {
			curveSignal = options?.signal;
			return new Promise<ReturnType<typeof systemCurveResponse>>((resolve, reject) => {
				if (systemCurve.mock.calls.length > 1) resolve(systemCurveResponse());
				options?.signal?.addEventListener('abort', () =>
					reject(new DOMException('', 'AbortError'))
				);
			});
		});
		const s = store(pumpTransferExample(), { ...held.solver, systemCurve });
		await s.solve();
		s.loadSystemCurve('P1');
		await Promise.resolve();
		await Promise.resolve();
		await Promise.resolve();
		expect(systemCurve).toHaveBeenCalledTimes(1);
		const running = s.runGoalSeek(toRequest(setupFor(s.project), s.project, null));
		expect(curveSignal?.aborted).toBe(true);
		// Cancelled by the goal seek, which the chart says (not "a new solve was started").
		expect(s.systemCurves.P1).toEqual({ status: 'cancelled', by: 'goalSeek' });
		s.loadSystemCurve('P1', { retry: true });
		await new Promise((r) => setTimeout(r, 0));
		expect(systemCurve).toHaveBeenCalledTimes(1);
		held.answer();
		await running;
		await new Promise((r) => setTimeout(r, 0));
		expect(systemCurve).toHaveBeenCalledTimes(2);
	});

	it('sends scenarioId only for a scenario', async () => {
		const held = heldGoalSeek();
		const s = store(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Winter', overrides: [] }]),
			held.solver
		);
		const base = s.runGoalSeek(toRequest(setupFor(s.project), s.project, null));
		held.answer();
		await base;
		const scenario = s.runGoalSeek(toRequest(setupFor(s.project), s.project, 'S1'));
		held.answer();
		await scenario;
		expect(held.goalSeek.mock.calls[0]![2]).toEqual({ signal: expect.any(AbortSignal) });
		expect(held.goalSeek.mock.calls[1]![2]).toEqual({
			signal: expect.any(AbortSignal),
			scenarioId: 'S1'
		});
		expect(s.goalSeek?.run.caseId).toBe('S1');
	});
});

describe('a result goes out of date by its case key, results or not (§6.11)', () => {
	async function ran(project: Project, caseId: string | null = null) {
		const held = heldGoalSeek();
		const s = store(project, held.solver);
		const running = s.runGoalSeek(toRequest(setupFor(s.project), s.project, caseId));
		held.answer();
		await running;
		return s;
	}

	it('on a project never solved: stale after a hydraulic edit, not after a rename; undo makes it current', async () => {
		const s = await ran(pumpTransferExample());
		expect(s.resultsFor(null).response).toBeNull();
		s.update((p) => {
			p.components[1]!.name = 'Renamed pump';
		}, 'rename');
		expect(s.goalSeek).toMatchObject({ status: 'done', stale: false });
		s.update(speedFaster, 'change speed');
		expect(s.goalSeek).toMatchObject({ status: 'done', stale: true });
		s.undo();
		expect(s.goalSeek).toMatchObject({ status: 'done', stale: false });
	});

	it('is applied while the applied key holds, out of date after another edit, current after undo', async () => {
		const s = await ran(pumpTransferExample());
		s.update(
			(p) => updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.8611744213850658 }) as Component),
			'apply goal seek values'
		);
		s.markGoalSeekApplied(null);
		expect(s.goalSeek).toMatchObject({
			stale: true,
			appliedCurrent: true,
			applied: { caseId: null }
		});
		s.update(speedFaster, 'change speed');
		expect(s.goalSeek).toMatchObject({ stale: true, appliedCurrent: false });
		s.undo();
		expect(s.goalSeek).toMatchObject({ stale: true, appliedCurrent: true });
		s.undo();
		expect(s.goalSeek).toMatchObject({ stale: false, appliedCurrent: false });
	});

	it("a scenario's change makes its run stale; a deleted scenario too", async () => {
		const level: Override = {
			kind: 'component',
			componentId: 'R2',
			field: 'liquidLevel',
			value: 6
		};
		const s = await ran(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Winter', overrides: [] }]),
			'S1'
		);
		expect(finishedGoalSeek(s.goalSeek)?.stale).toBe(false);
		s.update((p) => withScenarios(p, [{ id: 'S1', name: 'Winter', overrides: [level] }]), 'change');
		expect(finishedGoalSeek(s.goalSeek)?.stale).toBe(true);
		s.undo();
		expect(finishedGoalSeek(s.goalSeek)?.stale).toBe(false);
		s.update((p) => withScenarios(p, []), 'delete scenario');
		expect(finishedGoalSeek(s.goalSeek)?.stale).toBe(true);
	});

	it('load() clears it, and aborts a run in flight', async () => {
		const held = heldGoalSeek();
		const s = store(pumpTransferExample(), held.solver);
		const running = s.runGoalSeek(toRequest(setupFor(s.project), s.project, null));
		s.load(pumpTransferExample());
		expect(held.pending[0]!.signal!.aborted).toBe(true);
		expect(s.goalSeek).toBeNull();
		held.answer();
		await running;
		expect(s.goalSeek).toBeNull();
		expect(s.calculating).toBeNull();
	});
});

describe('the workspace: Apply, notices, page state and reserved ids', () => {
	function workspace(project = pumpTransferExample()) {
		const held = heldGoalSeek();
		const ws = testWorkspace(project, { solver: held.solver });
		ws.goalSeekSetup = setupFor(ws.project);
		return { ws, held };
	}

	it('applies to the base as one undo step, solves, and says what it wrote', async () => {
		const { ws, held } = workspace();
		const running = ws.runGoalSeek();
		held.answer();
		await running;
		// The dialog was closed: a notice says how it ended.
		expect(ws.notice?.text).toBe(
			'Goal seek on the base case finished: goal met. Open Goal seek to apply the values.'
		);
		ws.goalSeekOpen = true;
		expect(ws.applyGoalSeek('case')).toBe(true);
		expect(
			(ws.store.project.components.find((c) => c.id === 'P1') as { speed: number }).speed
		).toBe(0.8611744213850658);
		expect(ws.store.undoLabel).toBe('apply goal seek values');
		expect(ws.goalSeekOpen).toBe(false);
		expect(ws.notice?.text).toBe(
			'Applied to the base case: Transfer pump speed 86.1174 %. Undo restores the values before.'
		);
		expect(ws.store.goalSeek).toMatchObject({ appliedCurrent: true });
		await vi.waitFor(() => expect(held.solve).toHaveBeenCalledTimes(1));
		ws.undo();
		expect(
			(ws.store.project.components.find((c) => c.id === 'P1') as { speed: number }).speed
		).toBe(1);
		expect(ws.store.goalSeek).toMatchObject({ stale: false, appliedCurrent: false });
	});

	it('applies values only: each pipe stays the pipe solved, so Build still finds its results', async () => {
		const { ws, held } = workspace();
		await ws.store.solve();
		const velocity = () =>
			solvedPipe(ws.store.project, ws.store.solved!, 'L3', 0)?.segment.velocity;
		const strip = () =>
			elementSummary(
				ws.labelsProject,
				ws.store.solved!,
				ws.displayUnits,
				{ kind: 'connection', id: 'L3' },
				null,
				ws.store.project
			)!;
		expect(velocity()).toBe(2);
		const running = ws.runGoalSeek();
		held.answer();
		await running;
		ws.goalSeekOpen = true;
		expect(ws.applyGoalSeek('case')).toBe(true);
		// The values applied are out of date until the solve after Apply answers: L3's pipe is the
		// pipe solved, with its velocity, and nothing is left out.
		expect(ws.store.results.stale).toBe(true);
		expect(velocity()).toBe(2);
		expect(strip().notes).toEqual([]);
		await vi.waitFor(() => expect(ws.store.results.stale).toBe(false));
		// Undo: the solve of the values applied is out of date, and still of the same pipes.
		ws.undo();
		expect(ws.store.results.stale).toBe(true);
		expect(velocity()).toBe(2);
		expect(strip().notes).toEqual([]);
	});

	it('says a scenario keeps its own value of a value applied to the base', async () => {
		const own: Override = { kind: 'component', componentId: 'P1', field: 'speed', value: 0.9 };
		const { ws, held } = workspace(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Winter', overrides: [own] }])
		);
		ws.goalSeekOpen = true;
		const running = ws.runGoalSeek();
		held.answer();
		await running;
		ws.applyGoalSeek('case');
		expect(ws.notice?.text).toMatch(/Winter sets its own Transfer pump speed, so it keeps it\.$/);
	});

	it('applies as a new scenario holding the run case changes, Undo going back to that case', async () => {
		const level: Override = {
			kind: 'component',
			componentId: 'R1',
			field: 'liquidLevel',
			value: 2
		};
		const { ws, held } = workspace(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Low suction', overrides: [level] }])
		);
		ws.setCase('S1');
		ws.goalSeekOpen = true;
		const running = ws.runGoalSeek();
		held.answer();
		await running;
		expect(ws.store.goalSeek?.run.caseId).toBe('S1');
		expect(ws.applyGoalSeek('new')).toBe(true);
		const added = ws.store.project.scenarios![1]!;
		expect(added).toMatchObject({ id: 'S2', name: 'Goal seek 2' });
		expect(added.overrides).toEqual([
			level,
			{ kind: 'component', componentId: 'P1', field: 'speed', value: 0.8611744213850658 }
		]);
		expect(added.description).toMatch(
			/^Values found by goal seek on scenario Low suction for: Transfer pump → Discharge isolation valve · Flow 15 L\/s \(met\)\. \d{4}-\d\d-\d\d\.$/
		);
		expect(ws.store.activeCase).toBe('S2');
		expect(ws.store.undoLabel).toBe('add scenario Goal seek 2');
		ws.undo();
		expect(ws.store.activeCase).toBe('S1');
		expect(ws.store.project.scenarios).toHaveLength(1);
	});

	it('applies the result shown again after a cancelled run', async () => {
		const { ws, held } = workspace();
		ws.goalSeekOpen = true;
		const first = ws.runGoalSeek();
		held.answer();
		await first;
		const second = ws.runGoalSeek();
		expect(ws.store.cancelGoalSeek()).toBe(true);
		held.answer(goalSeekResponse({ met: false, stopReason: 'no_progress' })); // dropped
		await second;
		expect(ws.store.goalSeek?.status).toBe('cancelled');
		expect(ws.applyGoalSeek('case')).toBe(true);
		expect(
			(ws.store.project.components.find((c) => c.id === 'P1') as { speed: number }).speed
		).toBe(0.8611744213850658);
		expect(ws.store.undoLabel).toBe('apply goal seek values');
		// The applied result takes the cancelled state's place ("nothing changed" no longer holds).
		expect(ws.store.goalSeek).toMatchObject({ status: 'done', appliedCurrent: true });
	});

	it('writes nothing when the case already holds the values, and says so', async () => {
		const { ws, held } = workspace();
		ws.edit((p) => {
			p.metadata.name = 'Renamed';
		}, 'rename project');
		const before = ws.store.project;
		ws.goalSeekOpen = true;
		const running = ws.runGoalSeek();
		const closest = goalSeekResponse({
			met: false,
			stopReason: 'not_reachable',
			reportedEvaluation: 0
		});
		const variable = closest.result.variables[0]!;
		closest.result.variables = [
			{
				...variable,
				value: 1,
				atBound: 'upper',
				override: { kind: 'component', componentId: 'P1', field: 'speed', value: 1 }
			}
		];
		held.answer(closest);
		await running;
		expect(ws.applyGoalSeek('case')).toBe(false);
		expect(ws.store.project).toBe(before);
		expect(ws.store.undoLabel).toBe('rename project');
		expect(ws.notice?.text).toBe(
			'The base case already holds the values found (Transfer pump speed 100 %): nothing changed.'
		);
		expect(ws.store.goalSeek).toMatchObject({ applied: null, appliedCurrent: false });
		expect(held.solve).not.toHaveBeenCalled();
	});

	it('says a closed run met at the start needs nothing applied', async () => {
		const { ws, held } = workspace();
		const running = ws.runGoalSeek();
		held.answer(
			goalSeekResponse({
				stopReason: 'met_at_start',
				message: 'The case already meets every goal: nothing to change.',
				reportedEvaluation: 0
			})
		);
		await running;
		expect(ws.notice?.text).toBe(
			'Goal seek on the base case finished: the case already meets every goal; nothing to change.'
		);
	});

	it('refuses to apply an out-of-date result, with a notice', async () => {
		const { ws, held } = workspace();
		ws.goalSeekOpen = true;
		const running = ws.runGoalSeek();
		held.answer();
		await running;
		ws.edit(speedFaster, 'change speed');
		expect(ws.applyGoalSeek('case')).toBe(false);
		expect(ws.notice?.text).toMatch(/^Out of date/);
	});

	it('resets the setup and the dialog when another project is loaded', () => {
		const { ws } = workspace();
		ws.openGoalSeek({ kind: 'component', id: 'P1' });
		ws.store.load(pumpTransferExample());
		expect(ws.goalSeekOpen).toBe(false);
		expect(ws.goalSeekPrefill).toBeNull();
		expect(ws.goalSeekSetup).toEqual({ goals: [], variables: [] });
	});

	it('keeps the ids the setup names from new elements, until the row is removed', () => {
		const ws = testWorkspace(pumpTransferExample());
		const valve = ws.insert('L3', 'gate');
		expect(valve).toBe('V2');
		ws.goalSeekSetup = {
			goals: [{ ...newGoal({ elementId: 'V2' }, 'valve_flow'), target: 0.01 }],
			variables: []
		};
		expect(ws.remove('V2', true)).toBe(true);
		expect(ws.insert('L3', 'gate')).toBe('V3');
		ws.undo();
		ws.undo();
		expect(ws.store.project.components.some((c) => c.id === 'V2')).toBe(true);
		ws.goalSeekSetup = { goals: [], variables: [] };
		expect(ws.remove('V2', true)).toBe(true);
		expect(ws.insert('L3', 'gate')).toBe('V2');
	});

	it('keeps a connection id the setup names from a new connection', () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.goalSeekSetup = {
			goals: [{ ...newGoal({ elementId: 'L4' }, 'link_flow'), target: 0.01 }],
			variables: []
		};
		expect(ws.insert('L3', 'gate')).toBe('V2');
		const ids = ws.store.project.connections.map((c) => c.id);
		expect(ids).not.toContain('L4');
		expect(ids).toContain('L5');
	});
});
