/**
 * One pump off on the Pumps together card, in the workspace (CLAUDE.md D21 slice 4d): the add in
 * one undo step, its notice and the box it ticks; the add during a run, after which the card asks
 * again for the curve the run cancelled, before any other case's; the other cases' requests (after
 * the case shown's curves and after any calculation, one at a time, cancelled by the box or a
 * solve and asked again after it, withdrawn by a members change and asked again on going back,
 * those still waiting withdrawn when another case is shown, a failure or the user's cancel never
 * asked again without "Compute them again"); the claims; the block in a scenario; the scenario
 * limit; and the block's Solve all, which keeps the focus through its run and words its reasons
 * as the Scenarios menu does. The solves and curves are the shared fixture's real API answers for
 * the `one-off` case and its scenarios, given by a fake solver by scenario id.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ValidationError } from '$lib/api/client';
import type { Project, PumpGroupCurveResponse, Scenario, SolveResponse } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { scenariosOf, withScenarios } from '$lib/utils/scenarios';

const getContext = HTMLCanvasElement.prototype.getContext;
const consoleError = console.error;
beforeEach(() => {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	console.error = (...args: unknown[]) => {
		if (String(args[0]).startsWith('Failed to create chart')) return;
		consoleError(...args);
	};
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	console.error = consoleError;
});

interface Answer {
	status: number;
	body: unknown;
}
interface Responses {
	solve: SolveResponse;
	groupCurve: Answer;
	systemCurve: Answer | null;
}
interface FixtureCase extends Responses {
	name: string;
	project: Project;
	scenarioCases: Record<string, Responses>;
}
const oneOff = (fixture.cases as unknown as FixtureCase[]).find((c) => c.name === 'one-off')!;
const withoutScenarios = () => withScenarios(structuredClone(oneOff.project), []);

interface Call {
	scenarioId: string | null;
	curve: 'group' | 'system';
	/** Answered, or aborted: no longer in flight. */
	settled: boolean;
}

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((res) => (resolve = res));
	return { promise, resolve };
}

/**
 * A solver answering from the fixture by scenario id (another scenario: the base's answers);
 * `hold(call)` returns a promise to answer a group-curve request later, and `fail(call)` an
 * error to answer it with instead.
 */
function setup(
	project: Project,
	options: {
		hold?: (call: Call) => Promise<void> | undefined;
		fail?: (call: Call) => Error | undefined;
		solve?: Solver['solve'];
	} = {}
) {
	const calls: Call[] = [];
	const solves: (string | null)[] = [];
	const responsesOf = (id: string | undefined): Responses =>
		(id && oneOff.scenarioCases[id]) || oneOff;
	const solver: Solver = {
		solve:
			options.solve ??
			(async (_p, _o, request) => {
				solves.push(request?.scenarioId ?? null);
				return structuredClone(responsesOf(request?.scenarioId).solve);
			}),
		groupCurve: async (_p, _ids, request) => {
			const call: Call = {
				scenarioId: request?.scenarioId ?? null,
				curve: request?.curve === 'system' ? 'system' : 'group',
				settled: false
			};
			calls.push(call);
			const held = options.hold?.(call);
			if (held) {
				// As the real client: an aborted request rejects (the store's queue then moves on).
				await new Promise<void>((resolve, reject) => {
					request?.signal?.addEventListener('abort', () => {
						call.settled = true;
						reject(new DOMException('The operation was aborted.', 'AbortError'));
					});
					void held.then(resolve);
				});
			}
			call.settled = true;
			const error = options.fail?.(call);
			if (error) throw error;
			const answer = responsesOf(request?.scenarioId);
			const sent = call.curve === 'system' ? answer.systemCurve! : answer.groupCurve;
			return structuredClone(sent.body as PumpGroupCurveResponse);
		}
	};
	const ws = testWorkspace(project, { solver });
	render(WorkspaceView, { workspace: ws });
	return { ws, calls, solves };
}

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const card = () => results().getByRole('region', { name: /^Pumps together/ }) as HTMLElement;
const block = () => within(card()).getByRole('region', { name: 'One pump off' });
const others = (calls: Call[]) => calls.filter((c) => c.scenarioId !== null);

/** Solve the base, show the Pumps view and open the card; its two curves answered. */
async function openCard(ws: ReturnType<typeof setup>['ws'], calls: Call[]) {
	await ws.solve();
	await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
	await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
	await waitFor(() => expect(calls.filter((c) => c.scenarioId === null)).toHaveLength(2));
}

describe('one pump off on the Pumps together card', () => {
	it('adds a case per running pump in one undo step, says so, and asks for their duties', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await waitFor(() =>
			expect(within(card()).getByRole('img')).toHaveAccessibleName(/group system curve shown/)
		);
		const add = within(block()).getByRole('button', { name: 'Add cases with one pump off (2)' });
		const depth = ws.store.undoDepth;
		await fireEvent.click(add);
		expect(ws.scenarios.map((s) => [s.id, s.name, s.overrides])).toEqual([
			[
				'S1',
				'Pump PA off',
				[{ kind: 'component', componentId: 'PA', field: 'status', value: 'off' }]
			],
			[
				'S2',
				'Pump PB off',
				[{ kind: 'component', componentId: 'PB', field: 'status', value: 'off' }]
			]
		]);
		expect(ws.store.undoDepth).toBe(depth + 1);
		expect(ws.store.undoLabel).toBe('add cases with one pump off');
		expect(ws.store.activeCase).toBeNull();
		expect(ws.pumpGroupOthers).toBe(true);
		expect(
			screen.getByText(
				'Added 2 cases with one pump off: Pump PA off and Pump PB off. Solve all solves every case not yet solved; Undo removes them.'
			)
		).toBeVisible();
		// The focus on the block's Solve all, which offers the two cases.
		await waitFor(() =>
			expect(within(block()).getByRole('button', { name: 'Solve all (2)' })).toHaveFocus()
		);
		// Undo removes both, and shows the base.
		ws.undo();
		expect(scenariosOf(ws.store.project)).toEqual([]);
		expect(ws.store.activeCase).toBeNull();
		await waitFor(() =>
			expect(
				within(block()).getByRole('button', { name: 'Add cases with one pump off (2)' })
			).toBeVisible()
		);
	});

	it('asks again after Solve all for the curve the run cancelled; the run solves the new cases', async () => {
		const held = deferred<void>();
		let first = true;
		const { ws, calls, solves } = setup(withoutScenarios(), {
			hold: (call) => {
				if (call.scenarioId === null && call.curve === 'system' && first) {
					first = false;
					return held.promise;
				}
				return undefined;
			}
		});
		await openCard(ws, calls);
		const response = ws.store.results.response;
		expect(ws.store.groupSystemCurve(response, ['PA', 'PB'])).toEqual({ status: 'loading' });
		await fireEvent.click(
			within(block()).getByRole('button', { name: 'Add cases with one pump off (2)' })
		);
		await fireEvent.click(within(block()).getByRole('button', { name: 'Solve all (2)' }));
		expect(ws.store.groupSystemCurve(response, ['PA', 'PB'])).toEqual({
			status: 'cancelled',
			by: 'solve'
		});
		held.resolve();
		await waitFor(() => expect(solves).toEqual([null, 'S1', 'S2']));
		// After the run: the base's group system curve asked again, and drawn.
		await waitFor(() =>
			expect(calls.filter((c) => c.scenarioId === null && c.curve === 'system')).toHaveLength(2)
		);
		await waitFor(() =>
			expect(ws.store.groupSystemCurve(response, ['PA', 'PB'])?.status).toBe('ready')
		);
		expect(card().textContent).not.toContain('was not computed: a new solve was started');
		const legend = within(card()).getByRole('list', { name: 'Legend' });
		await waitFor(() => expect(within(legend).getByText(/^Group system curve/)).toBeVisible());
		// Then the new cases' duties, as rings.
		await waitFor(() =>
			expect(within(legend).getByText('2 · Pump PB off (station duty)')).toBeVisible()
		);
		// In this order: none of the new cases is asked during the run, nor before the curve the
		// run cancelled has answered again.
		expect(calls.map((c) => [c.scenarioId, c.curve])).toEqual([
			[null, 'group'],
			[null, 'system'],
			[null, 'system'],
			['S1', 'group'],
			['S2', 'group']
		]);
	});

	it('keeps the focus on its Solve all through the run and after, the button in place', async () => {
		const { ws, calls, solves } = setup(withoutScenarios());
		await openCard(ws, calls);
		await fireEvent.click(
			within(block()).getByRole('button', { name: 'Add cases with one pump off (2)' })
		);
		const solveAll = within(block()).getByRole('button', { name: 'Solve all (2)' });
		await waitFor(() => expect(solveAll).toHaveFocus());
		await fireEvent.click(solveAll);
		await waitFor(() => expect(solves).toEqual([null, 'S1', 'S2']));
		await waitFor(() => expect(ws.store.calculating).toBeNull());
		// And after the new cases' duties have answered and been drawn.
		const legend = within(card()).getByRole('list', { name: 'Legend' });
		await waitFor(() =>
			expect(within(legend).getByText('2 · Pump PB off (station duty)')).toBeVisible()
		);
		expect(others(calls).every((c) => c.settled)).toBe(true);
		const after = within(block()).getByRole('button', { name: 'Solve all' });
		expect(after).toBe(solveAll);
		expect(after).toHaveAttribute('aria-disabled', 'true');
		expect(after).toHaveFocus();
	});

	it('after a run that solves the case shown, asks for its curves before any other case’s', async () => {
		const { ws, calls } = setup(structuredClone(oneOff.project));
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() =>
			expect(within(card()).getByRole('img')).toHaveAccessibleName(/4 · Both pumps off/)
		);
		// Every case out of date, then S3 shown with its curves answered (its group system curve
		// asked as the case shown).
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 0.5;
		}, 'Change length');
		ws.setCase('S3');
		await waitFor(() =>
			expect(calls.filter((c) => c.scenarioId === 'S3').map((c) => c.curve)).toEqual([
				'group',
				'system'
			])
		);
		const before = calls.length;
		await ws.solveAll();
		await waitFor(() => expect(calls.length - before).toBe(6));
		expect(
			calls.slice(before).map((c) => [c.scenarioId, c.curve]),
			'the case shown first, then the others in the chart’s order'
		).toEqual([
			['S3', 'group'],
			['S3', 'system'],
			['S1', 'group'],
			['S2', 'group'],
			[null, 'group'],
			['S4', 'group']
		]);
		// Two runs of five solves: the budget of the card's other long tests.
	}, 20_000);

	it('asks for the other cases after the case shown, one at a time, and cancels them as told', async () => {
		// Every request of another case waits until released; the base's first group system curve too.
		const waiting: (() => void)[] = [];
		const baseSystem = deferred<void>();
		let firstSystem = true;
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId === null) {
					if (call.curve !== 'system' || !firstSystem) return undefined;
					firstSystem = false;
					return baseSystem.promise;
				}
				const gate = deferred<void>();
				waiting.push(gate.resolve);
				return gate.promise;
			}
		});
		const ids = ['PA', 'PB'];
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === null)).toHaveLength(2));
		// The case shown's group system curve not answered yet: no other case is asked.
		expect(others(calls)).toEqual([]);
		baseSystem.resolve();
		// Then the cases with one pump off first, one at a time.
		await waitFor(() => expect(others(calls)).toHaveLength(1));
		expect(others(calls)[0]!.scenarioId).toBe('S1');
		expect(within(card()).getByRole('status')).toHaveTextContent(
			"Computing the other cases' station duties: 1 of 4…"
		);
		waiting.shift()!();
		await waitFor(() => expect(others(calls)).toHaveLength(2));
		expect(others(calls).map((c) => c.scenarioId)).toEqual(['S1', 'S2']);
		expect(others(calls).filter((c) => !c.settled)).toHaveLength(1);

		// A base solve during them cancels them; once it ends, they are asked again.
		const s2 = ws.store.resultsFor('S2').response;
		const solving = ws.solve();
		expect(ws.store.groupCurve(s2, ids)).toEqual({ status: 'cancelled', by: 'solve' });
		await solving;
		await waitFor(() => expect(others(calls).filter((c) => c.scenarioId === 'S2')).toHaveLength(2));
		// After the case shown's curves again, and still one at a time.
		const base = calls.filter((c) => c.scenarioId === null);
		expect(base).toHaveLength(4);
		expect(calls.indexOf(base[3]!)).toBeLessThan(calls.lastIndexOf(others(calls).at(-1)!));
		expect(others(calls).filter((c) => !c.settled)).toHaveLength(1);

		// Unticking the box cancels them.
		const box = () =>
			within(card()).getByRole('checkbox', { name: "Also show the other cases' station duties" });
		await fireEvent.click(box());
		expect(ws.pumpGroupOthers).toBe(false);
		expect(ws.store.groupCurve(s2, ids)).toEqual({ status: 'cancelled', by: 'user' });
		// Ticked again, a case the user cancelled waits for "Compute them again".
		const sent = calls.length;
		await fireEvent.click(box());
		const again = await within(card()).findByRole('button', { name: 'Compute them again' });
		expect(calls).toHaveLength(sent);
		await fireEvent.click(again);
		await waitFor(() => expect(ws.store.groupCurve(s2, ids)).toEqual({ status: 'loading' }));

		// A change of members withdraws them: not cancelled by the user, they read as never asked.
		await fireEvent.click(
			within(within(card()).getByRole('group', { name: 'Pumps in the group' })).getByRole(
				'checkbox',
				{ name: /Pump PB/ }
			)
		);
		expect(ws.store.groupCurve(s2, ids)).toBeUndefined();
		for (const release of waiting) release();
	});

	it('a change of members and back asks the other cases again, none cancelled by the user', async () => {
		// S1's first request is held until it is aborted; S2 to S4 wait behind it.
		let firstS1 = true;
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId !== 'S1' || !firstS1) return undefined;
				firstS1 = false;
				return new Promise<void>(() => {});
			}
		});
		const ids = ['PA', 'PB'];
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ids);
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(others(calls).map((c) => c.scenarioId)).toEqual(['S1']));
		expect(state('S4')).toEqual({ status: 'loading' });
		const pb = () =>
			within(within(card()).getByRole('group', { name: 'Pumps in the group' })).getByRole(
				'checkbox',
				{ name: /Pump PB/ }
			);
		await fireEvent.click(pb());
		// S1's request is aborted; each case reads as never asked.
		expect(others(calls)[0]!.settled).toBe(true);
		expect(['S1', 'S2', 'S3', 'S4'].map(state)).toEqual([
			undefined,
			undefined,
			undefined,
			undefined
		]);
		// Back to the same members: their curves for the case shown are still there, then each
		// other case's is asked again, in the chart's order.
		await fireEvent.click(pb());
		await waitFor(() =>
			expect(within(card()).getByRole('img')).toHaveAccessibleName(/4 · Both pumps off/)
		);
		expect(calls.map((c) => [c.scenarioId, c.curve])).toEqual([
			[null, 'group'],
			[null, 'system'],
			['S1', 'group'],
			['S1', 'group'],
			['S2', 'group'],
			['S3', 'group'],
			['S4', 'group']
		]);
		expect(card().textContent).not.toContain('you cancelled it');
		expect(within(card()).queryByRole('button', { name: 'Compute them again' })).toBeNull();
	}, 20_000);

	it('after the case shown changes, asks for its curves before the other cases still waiting', async () => {
		// S1's first request is held in flight; S2 and S3 wait behind it (S4 is not on the chart).
		const s1 = deferred<void>();
		let firstS1 = true;
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId !== 'S1' || !firstS1) return undefined;
				firstS1 = false;
				return s1.promise;
			}
		});
		const ids = ['PA', 'PB'];
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ids);
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		ws.pumpGroupUnticked = ['S4'];
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(others(calls).map((c) => c.scenarioId)).toEqual(['S1']));
		expect([state('S2'), state('S3')]).toEqual([{ status: 'loading' }, { status: 'loading' }]);
		ws.setCase('S4');
		await waitFor(() => expect(state('S4')).toEqual({ status: 'loading' }));
		const waited = { S1: state('S1'), S2: state('S2'), S3: state('S3') };
		s1.resolve();
		await waitFor(() => expect(others(calls)).toHaveLength(5));
		// The case now shown's two curves go first, then those that waited, asked again.
		expect(others(calls).map((c) => [c.scenarioId, c.curve])).toEqual([
			['S1', 'group'],
			['S4', 'group'],
			['S4', 'system'],
			['S2', 'group'],
			['S3', 'group']
		]);
		// The one in flight went on; those still waiting were withdrawn, never cancelled.
		expect(waited).toEqual({ S1: { status: 'loading' }, S2: undefined, S3: undefined });
		await waitFor(() => expect(state('S3')?.status).toBe('ready'));
		expect(card().textContent).not.toContain('you cancelled it');
		expect(within(card()).queryByRole('button', { name: 'Compute them again' })).toBeNull();
	});

	it('also when the case is switched from another view, the Pumps view shown after', async () => {
		const s1 = deferred<void>();
		let firstS1 = true;
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId !== 'S1' || !firstS1) return undefined;
				firstS1 = false;
				return s1.promise;
			}
		});
		const ids = ['PA', 'PB'];
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ids);
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		ws.pumpGroupUnticked = ['S4'];
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(others(calls).map((c) => c.scenarioId)).toEqual(['S1']));
		expect([state('S2'), state('S3')]).toEqual([{ status: 'loading' }, { status: 'loading' }]);
		// On the Summary, S4 shown: the Pumps view is drawn anew for its results.
		await fireEvent.click(results().getByRole('tab', { name: 'Summary' }));
		ws.setCase('S4');
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await waitFor(() => expect(state('S4')).toEqual({ status: 'loading' }));
		s1.resolve();
		await waitFor(() => expect(others(calls)).toHaveLength(5));
		expect(others(calls).map((c) => [c.scenarioId, c.curve])).toEqual([
			['S1', 'group'],
			['S4', 'group'],
			['S4', 'system'],
			['S2', 'group'],
			['S3', 'group']
		]);
	});

	it('never asks again by itself for a curve that failed or that the user cancelled', async () => {
		// S2's group curve fails; S3's first request is held in flight, S4 waits behind it.
		let firstS3 = true;
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId !== 'S3' || !firstS3) return undefined;
				firstS3 = false;
				return new Promise<void>(() => {});
			},
			fail: (call) => (call.scenarioId === 'S2' ? new Error('The server is busy.') : undefined)
		});
		const ids = ['PA', 'PB'];
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ids);
		const asked = (c: string) => calls.filter((call) => call.scenarioId === c).length;
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(asked('S3')).toBe(1));
		expect(state('S2')).toEqual({ status: 'error', message: 'The server is busy.' });
		expect(state('S4')).toEqual({ status: 'loading' });
		// The user unticks S4 while it waits, and ticks it again: cancelled by the user.
		const onChart = () =>
			within(within(card()).getByRole('group', { name: 'Cases on this chart' })).getByRole(
				'checkbox',
				{ name: /Both pumps off/ }
			);
		await fireEvent.click(onChart());
		await fireEvent.click(onChart());
		expect(state('S4')).toEqual({ status: 'cancelled', by: 'user' });
		// A Solve all of one new case: S3, cancelled by it, is asked again after it, and the new
		// case asked; S2 and S4 are not (S4 was never sent: it was cancelled while it waited).
		ws.store.update(
			(p) => withScenarios(p, [...scenariosOf(p), { id: 'S5', name: 'Copy', overrides: [] }]),
			'add scenario'
		);
		await ws.solveAll();
		await waitFor(() => expect(state('S5')?.status).toBe('ready'));
		await waitFor(() => expect(state('S3')?.status).toBe('ready'));
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(['S1', 'S2', 'S3', 'S4', 'S5'].map(asked)).toEqual([1, 1, 2, 0, 1]);
		expect(state('S2')).toEqual({ status: 'error', message: 'The server is busy.' });
		expect(state('S4')).toEqual({ status: 'cancelled', by: 'user' });
		// Only "Compute them again" asks for them, once each: S2 fails again and stays failed.
		await fireEvent.click(within(card()).getByRole('button', { name: 'Compute them again' }));
		await waitFor(() => expect(state('S4')?.status).toBe('ready'));
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(['S1', 'S2', 'S3', 'S4', 'S5'].map(asked)).toEqual([1, 2, 2, 1, 1]);
		expect(state('S2')).toEqual({ status: 'error', message: 'The server is busy.' });
	}, 20_000);

	it('says which duties lie on the base case’s group system curve, and why the others are not said to', async () => {
		const { ws, calls } = setup(structuredClone(oneOff.project));
		await ws.store.solveAll();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === null)).toHaveLength(2));
		await fireEvent.click(
			within(card()).getByRole('checkbox', { name: "Also show the other cases' station duties" })
		);
		const img = () => within(card()).getByRole('img');
		await waitFor(() => expect(img()).toHaveAccessibleName(/4 · Both pumps off/));
		const name = img().getAttribute('aria-label')!;
		expect(name).toMatch(
			/1 · Pump PA off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network\)/
		);
		expect(name).toMatch(
			/2 · Pump PB off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network\)/
		);
		expect(name).toMatch(
			/3 · Delivery tank 5 m higher, [\d.]+ L\/s at a rise of [\d.]+ m \(No: the rest of the network differs from this case's; its own group system curve is not drawn\)/
		);
		expect(name).toMatch(
			/4 · Both pumps off, 0 L\/s at a rise of 19 m \(Not said: at zero station flow the rest can hold more than one state \(D13\)\)/
		);
		await fireEvent.click(within(card()).getByRole('button', { name: 'Show data table' }));
		const table = within(card()).getByRole('table', { name: "Other cases' station duties" });
		const claims = within(table)
			.getAllByRole('row')
			.slice(1)
			.map((r) => r.querySelectorAll('td')[2]?.textContent);
		expect(claims).toEqual([
			'Yes: the same rest of the network',
			'Yes: the same rest of the network',
			"No: the rest of the network differs from this case's; its own group system curve is not drawn",
			'Not said: at zero station flow the rest can hold more than one state (D13)'
		]);
		// Running combinations: every case, the shown first, with its station line and ring.
		const combos = within(card()).getByRole('table', { name: 'Running combinations' });
		const headings = within(combos)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'rowgroup')
			.map((h) => h.firstElementChild!.textContent);
		expect(headings).toEqual([
			'Base case (shown)',
			'Pump PA off · ring 1',
			'Pump PB off · ring 2',
			'Delivery tank 5 m higher · ring 3',
			'Both pumps off · ring 4'
		]);
	});

	it('in a scenario: made from the base case only, and the base’s duty beyond this curve', async () => {
		const { ws, calls } = setup(structuredClone(oneOff.project));
		await ws.store.solveAll();
		ws.setCase('S1');
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === 'S1')).toHaveLength(2));
		expect(block()).toHaveTextContent(
			'Cases with one pump off are made from the base case: show the base case to add them. To study Pump PA off with a pump off, duplicate it in Scenarios and set that pump off there.'
		);
		expect(within(block()).queryByRole('button')).toBeNull();
		await fireEvent.click(within(card()).getByRole('button', { name: 'Show data table' }));
		const table = await within(card()).findByRole('table', { name: "Other cases' station duties" });
		await waitFor(() =>
			expect(within(table).getAllByRole('row')[1]!.textContent).toContain(
				'Not said: its flow is beyond the flows this curve was computed for'
			)
		);
		expect(within(table).getAllByRole('row')[1]!.textContent).toContain('Base case');
	});

	it('refuses the add past the scenario limit, and changes nothing', async () => {
		const nineteen: Scenario[] = Array.from({ length: 19 }, (_, i) => ({
			id: `S${i + 1}`,
			name: `Case ${i + 1}`,
			overrides: []
		}));
		const { ws, calls } = setup(withScenarios(withoutScenarios(), nineteen));
		await openCard(ws, calls);
		const add = within(block()).getByRole('button', { name: 'Add cases with one pump off (2)' });
		expect(add).toHaveAttribute('aria-disabled', 'true');
		expect(add).toHaveAccessibleDescription(
			'Adding 2 cases would make 21 scenarios; a project holds at most 20 scenarios.'
		);
		const depth = ws.store.undoDepth;
		await fireEvent.click(add);
		expect(ws.store.undoDepth).toBe(depth);
		expect(ws.scenarios).toHaveLength(19);
	});

	it('tells two pumps of the same name apart: the cases it makes, its notes and the extremes', async () => {
		// Synthetic: a duty and a standby unit both named "Booster pump" (names need not be unique).
		const project = withoutScenarios();
		for (const c of project.components) if (c.type === 'pump') c.name = 'Booster pump';
		const { ws, calls, solves } = setup(project);
		await openCard(ws, calls);
		await fireEvent.click(
			within(block()).getByRole('button', { name: 'Add cases with one pump off (2)' })
		);
		expect(ws.scenarios.map((s) => [s.id, s.name])).toEqual([
			['S1', 'Booster pump (PA) off'],
			['S2', 'Booster pump (PB) off']
		]);
		expect(
			within(block())
				.getAllByText(/has its case already/)
				.map((p) => p.textContent)
		).toEqual([
			'Booster pump (PA) has its case already: Booster pump (PA) off.',
			'Booster pump (PB) has its case already: Booster pump (PB) off.'
		]);
		await fireEvent.click(within(block()).getByRole('button', { name: 'Solve all (2)' }));
		await waitFor(() => expect(solves).toEqual([null, 'S1', 'S2']));
		const extremes = await within(card()).findByLabelText('Extremes over these cases');
		expect([...extremes.querySelectorAll('dt')].map((dt) => dt.textContent)).toEqual([
			'Booster pump (PA), largest flow:',
			'Booster pump (PA), largest shaft power:',
			'Booster pump (PA), smallest NPSH margin:',
			'Booster pump (PB), largest flow:',
			'Booster pump (PB), largest shaft power:',
			'Booster pump (PB), smallest NPSH margin:'
		]);
	});

	it('words Solve all as the Scenarios menu does, in every state', async () => {
		const failing = structuredClone(oneOff.project);
		/** A solve waits for this while it is set. */
		let held: ReturnType<typeof deferred<void>> | null = null;
		const { ws, calls } = setup(failing, {
			solve: async (_p, _o, request) => {
				if (request?.scenarioId === 'S3') {
					throw new ValidationError(
						'Invalid input: 1 problem(s).',
						['body.project.scenarios.2.overrides.0: made-up rule'],
						400,
						'VALIDATION_ERROR'
					);
				}
				if (held) await held.promise;
				const id = request?.scenarioId;
				return structuredClone(((id && oneOff.scenarioCases[id]) || oneOff).solve);
			}
		});
		await ws.store.solveAll();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === null)).toHaveLength(2));
		// Each read again: the block's button is drawn anew when the case shown changes, and the
		// menu closes when a run ends (its focus goes to Solve).
		const ours = () => within(block()).getByRole('button', { name: /^Solve all/ });
		const menu = () => screen.queryByRole('group', { name: 'Case' });
		const theirs = () => within(menu()!).getByRole('button', { name: 'Solve all' });
		const same = async (words: string) => {
			if (!menu()) await fireEvent.click(screen.getByRole('button', { name: /^Scenarios/ }));
			await waitFor(() => expect(theirs()).toHaveAccessibleDescription(words));
			expect(ours()).toHaveAccessibleDescription(words);
			expect(ours()).toHaveAttribute('aria-disabled', 'true');
		};
		await same(
			'Every case is solved except Delivery tank 5 m higher, which has an error to fix first.'
		);
		// Fixed: every case current.
		ws.store.update(
			(p) =>
				withScenarios(
					p,
					scenariosOf(p).filter((s) => s.id !== 'S3')
				),
			'delete scenario'
		);
		await same("Every case's results are current.");
		// A solve of another case than the one shown, in flight: both name that case.
		held = deferred<void>();
		const release = held.resolve;
		ws.setCase('S1');
		const solving = ws.solve();
		ws.setCase(null);
		await same('A solve of Pump PA off is running; Cancel in the header stops it.');
		held = null;
		release();
		await solving;
		await same("Every case's results are current.");
		// A Solve all run, held on the one case it solves.
		ws.store.update(
			(p) => withScenarios(p, [...scenariosOf(p), { id: 'S5', name: 'Copy', overrides: [] }]),
			'add scenario'
		);
		held = deferred<void>();
		const end = held.resolve;
		const run = ws.solveAll();
		await same('Solve all is running; Cancel in the header stops it.');
		held = null;
		end();
		await run;
		await same("Every case's results are current.");
		// Six states, each awaited: the budget of the card's other long tests.
	}, 20_000);
});
