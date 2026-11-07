/**
 * One pump off on the Pumps together card, in the workspace (CLAUDE.md D21 slice 4d), now D24's Add
 * cases block (PumpLineupsBlock) with Each pump off chosen: 4d's tests with the same assertions,
 * only the strings pump-lineups.md §7.12 lists under "4d's strings that change" changed, each named
 * where it does. The add in one undo step, its notice and the box it ticks; the add during a run, after which the card asks
 * again for the curve the run cancelled, before any other case's; the other cases' requests (after
 * the case shown's curves and after any calculation, one at a time, cancelled by the box or a
 * solve and asked again after it, withdrawn by a members change and asked again on going back,
 * those still waiting withdrawn when another case is shown, a failure or the user's cancel never
 * asked again without "Compute them again"); a case not asked yet while a run holds, which waits
 * for it with no progress line; the claims; the block in a scenario; the scenario limit; two
 * members of one name; and the block's Solve all, which keeps the focus through its run and words
 * its reasons as the Scenarios menu does. The solves and curves are the shared fixture's real API answers for
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
// §7.12: the h4 and region name "One pump off" becomes "Add cases".
const block = () => within(card()).getByRole('region', { name: 'Add cases' });
/** Choose Each pump off in the block (4d's cases; By number running is the default). */
const chooseEach = () =>
	fireEvent.click(within(block()).getByRole('radio', { name: 'Each pump off' }));
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
		await chooseEach();
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		const add = within(block()).getByRole('button', { name: 'Add 2 cases' });
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
			expect(within(block()).getByRole('button', { name: 'Add 2 cases' })).toBeVisible()
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
		await chooseEach();
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		await fireEvent.click(within(block()).getByRole('button', { name: 'Add 2 cases' }));
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
		await chooseEach();
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		await fireEvent.click(within(block()).getByRole('button', { name: 'Add 2 cases' }));
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
		// D24 §7.9: the rings are numbered in the chart's order (S1, S4, S2, S3), so the fourth,
		// drawn once all four are, is S3's (in case order it was S4's).
		await waitFor(() =>
			expect(within(within(card()).getByRole('figure')).getByRole('img')).toHaveAccessibleName(
				/4 · Delivery tank 5 m higher/
			)
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
		// The chart's order is D24's (lineupChartPriority, pump-lineups.md §4.6): one lineup of each
		// number running first, most running first (the base, 2; S1, 1; S4, 0), then S2.
		expect(
			calls.slice(before).map((c) => [c.scenarioId, c.curve]),
			'the case shown first, then the others in the chart’s order'
		).toEqual([
			['S3', 'group'],
			['S3', 'system'],
			[null, 'group'],
			['S1', 'group'],
			['S4', 'group'],
			['S2', 'group']
		]);
		// Two runs of five solves: the budget of the card's other long tests.
	}, 20_000);

	it('while a run holds, a case not asked yet waits for it, and nothing says it is computed', async () => {
		// The base solved, its group system curve held in flight; then Solve all of the scenarios
		// (the base current), S2's solve held: S1 has values and is not asked while the run goes on.
		const baseSystem = deferred<void>();
		let firstSystem = true;
		let hold: string | null = 'S2';
		const release = { S2: deferred<void>(), S6: deferred<void>() };
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId !== null || call.curve !== 'system' || !firstSystem) return undefined;
				firstSystem = false;
				return baseSystem.promise;
			},
			solve: async (_p, _o, request) => {
				const id = request?.scenarioId;
				if (id && id === hold) await release[id as 'S2' | 'S6'].promise;
				return structuredClone(((id && oneOff.scenarioCases[id]) || oneOff).solve);
			}
		});
		ws.pumpGroupOthers = true;
		await openCard(ws, calls);
		const response = ws.store.results.response;
		const ids = ['PA', 'PB'];
		// The other cases' own live line (pumps-results-layout.md §5.3: polite, never role=status).
		const status = () => {
			const line = card().querySelector('[data-group-others-state]')!;
			expect(line).toHaveAttribute('aria-live', 'polite');
			return line;
		};
		const running = ws.solveAll();
		await waitFor(() => expect(ws.store.resultsFor('S1').response).not.toBeNull());
		expect(ws.store.calculating).toBe('solveAll');
		expect(ws.store.groupSystemCurve(response, ids)).toEqual({ status: 'cancelled', by: 'solve' });
		expect(ws.store.groupCurve(ws.store.resultsFor('S1').response, ids)).toBeUndefined();
		// Nothing is computed for the other cases while the run goes on, and nothing says so; S1
		// waits for the run, then for the curve the run cancelled, which is asked again first.
		expect(status().textContent!.trim()).toBe('');
		expect(
			within(card()).queryByRole('button', { name: "Cancel the other cases' station duties" })
		).toBeNull();
		const waits = "waits for Solve all to end, then for this case's curves";
		expect(card().textContent).toContain(`Not on the chart: Pump PA off (${waits}).`);
		const table = within(card()).getByRole('table', { name: 'Running combinations' });
		expect(within(table).getByRole('rowheader', { name: /^Pump PA off/ })).toHaveTextContent(waits);
		expect(card().textContent).not.toContain('being computed');
		release.S2.resolve();
		await running;
		const legend = within(card()).getByRole('list', { name: 'Legend' });
		// D24 §7.9: the rings are numbered in the chart's order (S1, S4, S2, S3), so the fourth,
		// drawn once all four are, is S3's (in case order it was S4's).
		await waitFor(() =>
			expect(within(legend).getByText('4 · Delivery tank 5 m higher (station duty)')).toBeVisible()
		);
		// In the chart's order (D24 §4.6): S1 (1 running), S4 (0), then S2 and S3.
		expect(calls.map((c) => [c.scenarioId, c.curve])).toEqual([
			[null, 'group'],
			[null, 'system'],
			[null, 'system'],
			['S1', 'group'],
			['S4', 'group'],
			['S2', 'group'],
			['S3', 'group']
		]);

		// The case shown's curves answered: two new cases, S6's solve held. S5, solved, waits for
		// the run alone; it was once said to be computed, with the progress line, before any request.
		baseSystem.resolve();
		ws.store.update(
			(p) =>
				withScenarios(p, [
					...scenariosOf(p),
					{ id: 'S5', name: 'Copy A', overrides: [] },
					{ id: 'S6', name: 'Copy B', overrides: [] }
				]),
			'add scenarios'
		);
		hold = 'S6';
		const before = calls.length;
		const again = ws.solveAll();
		await waitFor(() => expect(ws.store.resultsFor('S5').response).not.toBeNull());
		expect(ws.store.calculating).toBe('solveAll');
		expect(calls).toHaveLength(before);
		expect(status().textContent!.trim()).toBe('');
		expect(
			within(card()).queryByRole('button', { name: "Cancel the other cases' station duties" })
		).toBeNull();
		expect(card().textContent).toContain('Not on the chart: Copy A (waits for Solve all to end).');
		expect(card().textContent).not.toContain('being computed');
		release.S6.resolve();
		await again;
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ids);
		await waitFor(() => expect(state('S6')?.status).toBe('ready'));
		expect(state('S5')?.status).toBe('ready');
		expect(calls.slice(before).map((c) => [c.scenarioId, c.curve])).toEqual([
			['S5', 'group'],
			['S6', 'group']
		]);
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
		// Then in the chart's order (D24 §4.6: S1, 1 running; S4, 0; then S2, S3), one at a time.
		await waitFor(() => expect(others(calls)).toHaveLength(1));
		expect(others(calls)[0]!.scenarioId).toBe('S1');
		const othersLine = card().querySelector('[data-group-others-state]')!;
		expect(othersLine).toHaveAttribute('aria-live', 'polite');
		await waitFor(() =>
			expect(othersLine).toHaveTextContent("Computing the other cases' station duties: 1 of 4…")
		);
		waiting.shift()!();
		await waitFor(() => expect(others(calls)).toHaveLength(2));
		expect(others(calls).map((c) => c.scenarioId)).toEqual(['S1', 'S4']);
		expect(others(calls).filter((c) => !c.settled)).toHaveLength(1);

		// A base solve during them cancels them; once it ends, they are asked again.
		const s4 = ws.store.resultsFor('S4').response;
		const solving = ws.solve();
		expect(ws.store.groupCurve(s4, ids)).toEqual({ status: 'cancelled', by: 'solve' });
		await solving;
		await waitFor(() => expect(others(calls).filter((c) => c.scenarioId === 'S4')).toHaveLength(2));
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
		expect(ws.store.groupCurve(s4, ids)).toEqual({ status: 'cancelled', by: 'user' });
		// Ticked again, a case the user cancelled waits for "Compute them again".
		const sent = calls.length;
		await fireEvent.click(box());
		const again = await within(card()).findByRole('button', { name: 'Compute them again' });
		expect(calls).toHaveLength(sent);
		await fireEvent.click(again);
		await waitFor(() => expect(ws.store.groupCurve(s4, ids)).toEqual({ status: 'loading' }));

		// A change of members withdraws them: not cancelled by the user, they read as never asked.
		await fireEvent.click(
			within(within(card()).getByRole('group', { name: 'Pumps in the group' })).getByRole(
				'checkbox',
				{ name: /Pump PB/ }
			)
		);
		expect(ws.store.groupCurve(s4, ids)).toBeUndefined();
		for (const release of waiting) release();
	});

	it('a change of members and back asks the other cases again, none cancelled by the user', async () => {
		// S1's first request is held until it is aborted; S4, S2 and S3 wait behind it (the chart's
		// order, D24 §4.6).
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
		// D24 §7.9: the rings are numbered in the chart's order (S1, S4, S2, S3), so the fourth,
		// drawn once all four are, is S3's (in case order it was S4's).
		await waitFor(() =>
			expect(within(within(card()).getByRole('figure')).getByRole('img')).toHaveAccessibleName(
				/4 · Delivery tank 5 m higher/
			)
		);
		expect(calls.map((c) => [c.scenarioId, c.curve])).toEqual([
			[null, 'group'],
			[null, 'system'],
			['S1', 'group'],
			['S1', 'group'],
			['S4', 'group'],
			['S2', 'group'],
			['S3', 'group']
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
		// In the chart's order (D24 §4.6: S1, S4, S2, S3): S4's group curve fails; S2's first
		// request is held in flight, S3 waits behind it.
		let firstS2 = true;
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId !== 'S2' || !firstS2) return undefined;
				firstS2 = false;
				return new Promise<void>(() => {});
			},
			fail: (call) => (call.scenarioId === 'S4' ? new Error('The server is busy.') : undefined)
		});
		const ids = ['PA', 'PB'];
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ids);
		const asked = (c: string) => calls.filter((call) => call.scenarioId === c).length;
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(asked('S2')).toBe(1));
		expect(state('S4')).toEqual({ status: 'error', message: 'The server is busy.' });
		expect(state('S3')).toEqual({ status: 'loading' });
		// The user unticks S3 while it waits, and ticks it again: cancelled by the user.
		const onChart = () =>
			within(within(card()).getByRole('group', { name: 'Cases on this chart' })).getByRole(
				'checkbox',
				{ name: /Delivery tank 5 m higher/ }
			);
		await fireEvent.click(onChart());
		await fireEvent.click(onChart());
		expect(state('S3')).toEqual({ status: 'cancelled', by: 'user' });
		// A Solve all of one new case: S2, cancelled by it, is asked again after it, and the new
		// case asked; S4 and S3 are not (S3 was never sent: it was cancelled while it waited).
		ws.store.update(
			(p) => withScenarios(p, [...scenariosOf(p), { id: 'S5', name: 'Copy', overrides: [] }]),
			'add scenario'
		);
		await ws.solveAll();
		await waitFor(() => expect(state('S5')?.status).toBe('ready'));
		await waitFor(() => expect(state('S2')?.status).toBe('ready'));
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(['S1', 'S2', 'S3', 'S4', 'S5'].map(asked)).toEqual([1, 2, 0, 1, 1]);
		expect(state('S4')).toEqual({ status: 'error', message: 'The server is busy.' });
		expect(state('S3')).toEqual({ status: 'cancelled', by: 'user' });
		// Only "Compute them again" asks for them, once each: S4 fails again and stays failed.
		await fireEvent.click(within(card()).getByRole('button', { name: 'Compute them again' }));
		await waitFor(() => expect(state('S3')?.status).toBe('ready'));
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(['S1', 'S2', 'S3', 'S4', 'S5'].map(asked)).toEqual([1, 2, 1, 2, 1]);
		expect(state('S4')).toEqual({ status: 'error', message: 'The server is busy.' });
	}, 20_000);

	it('beside "Compute them again", "Go to Running combinations" focuses that section’s heading, never touching the link (pumps-results-layout.md §5.3, §6.2, S3)', async () => {
		let failS1 = true;
		const { ws } = setup(structuredClone(oneOff.project), {
			fail: (call) => {
				if (call.scenarioId !== 'S1' || !failS1) return undefined;
				failS1 = false;
				return new Error('The server is busy.');
			}
		});
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		const again = await within(card()).findByRole('button', { name: 'Compute them again' });
		const section = card().querySelector<HTMLElement>('[data-group-others]')!;
		const line = section.querySelector('[data-group-others-state]')!;
		expect(line.textContent).toBe(
			"Not every other case's station duty was computed: see Running combinations."
		);
		const go = within(section).getByRole('button', { name: 'Go to Running combinations' });
		// After "Compute them again", in the same row as the line that names Running combinations.
		expect(again.compareDocumentPosition(go) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(go.parentElement).toBe(line.parentElement);
		const hash = location.hash;
		await fireEvent.click(go);
		const heading = within(card()).getByRole('heading', { name: 'Running combinations', level: 4 });
		expect(document.activeElement).toBe(heading);
		expect(location.hash).toBe(hash);
	}, 20_000);

	it('offers "Compute them again" as unavailable while a run holds, says why, and asks nothing until it ends', async () => {
		// S1's first group curve fails, so the card offers "Compute them again"; then a Solve all of
		// one new case is held. The store sends no curve request while it runs.
		let failS1 = true;
		const release = deferred<void>();
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			fail: (call) => {
				if (call.scenarioId !== 'S1' || !failS1) return undefined;
				failS1 = false;
				return new Error('The server is busy.');
			},
			solve: async (_p, _o, request) => {
				const id = request?.scenarioId;
				if (id === 'S5') await release.promise;
				return structuredClone(((id && oneOff.scenarioCases[id]) || oneOff).solve);
			}
		});
		const ids = ['PA', 'PB'];
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ids);
		const asked = (c: string) => calls.filter((call) => call.scenarioId === c).length;
		const again = () => within(card()).getByRole('button', { name: 'Compute them again' });
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await within(card()).findByRole('button', { name: 'Compute them again' });
		await waitFor(() => expect(state('S4')?.status).toBe('ready'));
		expect(state('S1')).toEqual({ status: 'error', message: 'The server is busy.' });
		expect(again()).not.toHaveAttribute('aria-disabled', 'true');
		ws.store.update(
			(p) => withScenarios(p, [...scenariosOf(p), { id: 'S5', name: 'Copy', overrides: [] }]),
			'add scenario'
		);
		const run = ws.solveAll();
		await waitFor(() => expect(ws.store.calculating).toBe('solveAll'));
		await waitFor(() => expect(again()).toHaveAttribute('aria-disabled', 'true'));
		expect(again()).toHaveAccessibleDescription(
			/^Solve all is running; Cancel in the header stops it\. /
		);
		await fireEvent.click(again());
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(asked('S1')).toBe(1);
		expect(state('S1')).toEqual({ status: 'error', message: 'The server is busy.' });
		// Nothing on the card says a duty is computed while nothing is sent.
		expect(within(card()).queryByText(/being computed/)).toBeNull();
		release.resolve();
		await run;
		await waitFor(() => expect(again()).not.toHaveAttribute('aria-disabled', 'true'));
		await fireEvent.click(again());
		await waitFor(() => expect(state('S1')?.status).toBe('ready'));
		expect(asked('S1')).toBe(2);
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
		const img = () => within(within(card()).getByRole('figure')).getByRole('img');
		// D24 §7.9: the rings are numbered in the chart's order (S1, S4, S2, S3), so the fourth,
		// drawn once all four are, is S3's (in case order it was S4's).
		await waitFor(() => expect(img()).toHaveAccessibleName(/4 · Delivery tank 5 m higher/));
		const name = img().getAttribute('aria-label')!;
		// D24 §9.6: with this case's group curve drawn, each case's part gains "; group curve:
		// {words}" (its own curve drawn for a case with one pump off, which has flow; the same as this
		// case's for the delivery tank; none drawn for both pumps off), then the curves drawn.
		expect(name).toMatch(
			/1 · Pump PA off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network; group curve: drawn \(1 running\): it crosses the group system curve at the ring\)/
		);
		expect(name).toMatch(
			/3 · Pump PB off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network; group curve: drawn \(1 running\): it crosses the group system curve at the ring\)/
		);
		expect(name).toMatch(
			/4 · Delivery tank 5 m higher, [\d.]+ L\/s at a rise of [\d.]+ m \(No: the rest of the network differs from this case's; its own group system curve is not drawn; group curve: the same as this case's: the station is the same inside\)/
		);
		expect(name).toMatch(
			/2 · Both pumps off, 0 L\/s at a rise of 19 m \(Not said: at zero station flow the rest can hold more than one state \(D13\); group curve: not drawn: no flow at any rise\)/
		);
		expect(name).toMatch(
			/; other cases' group curves drawn: 1 \(1 running\) and 3 \(1 running\); group curve shown; group system curve shown\.$/
		);
		await fireEvent.click(
			within(card()).getByRole('button', { name: 'Show data table of the group chart' })
		);
		const table = within(card()).getByRole('table', { name: "Other cases' station duties" });
		const claims = within(table)
			.getAllByRole('row')
			.slice(1)
			.map((r) => r.querySelectorAll('td')[2]?.textContent);
		// The table's rows in the rings' order (D24 §7.9): Pump PA off, Both pumps off, Pump PB off,
		// Delivery tank 5 m higher.
		expect(claims).toEqual([
			'Yes: the same rest of the network',
			'Not said: at zero station flow the rest can hold more than one state (D13)',
			'Yes: the same rest of the network',
			"No: the rest of the network differs from this case's; its own group system curve is not drawn"
		]);
		// Running combinations: every case, the shown first, with its station line and ring, then
		// the other cases in the chart's order (pumps-results-layout.md §5.3, §10 S5: D24 §4.6's,
		// so the rings, numbered in it, §7.9, read 1 to 4).
		const combos = within(card()).getByRole('table', { name: 'Running combinations' });
		const headings = within(combos)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'rowgroup')
			.map((h) => h.firstElementChild!.textContent);
		expect(headings).toEqual([
			'Base case (shown)',
			'Pump PA off · ring 1',
			'Both pumps off · ring 2',
			'Pump PB off · ring 3',
			'Delivery tank 5 m higher · ring 4'
		]);
	});

	it('lists "Cases on this chart" and numbers the rings in the chart’s order (D24 §4.6, §7.9)', async () => {
		// S1 Pump PA off and S2 Pump PB off (1 running each), S3 a tank level (no lineup), S4 both
		// off (0 running): one lineup of each count first, most running first (S1, S4), then the
		// other lineup (S2), then every other case (S3).
		const { ws, calls } = setup(structuredClone(oneOff.project));
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		const legend = () => within(card()).getByRole('list', { name: 'Legend' });
		const rings = () =>
			within(legend())
				.getAllByRole('listitem')
				.map((li) => li.textContent!.replace(/\s+/g, ' ').trim())
				.filter((text) => text.endsWith('(station duty)'));
		await waitFor(() => expect(rings()).toHaveLength(4));
		expect(rings()).toEqual([
			'○ 1 · Pump PA off (station duty)',
			'○ 2 · Both pumps off (station duty)',
			'○ 3 · Pump PB off (station duty)',
			'○ 4 · Delivery tank 5 m higher (station duty)'
		]);
		expect(others(calls).map((c) => c.scenarioId)).toEqual(['S1', 'S4', 'S2', 'S3']);
		const listed = () =>
			within(within(card()).getByRole('group', { name: 'Cases on this chart' }))
				.getAllByRole('checkbox')
				.map((box) => box.closest('label')!.textContent!.replace(/\s+/g, ' ').trim());
		expect(listed()).toEqual([
			'○ 1 · Pump PA off',
			'○ 2 · Both pumps off',
			'○ 3 · Pump PB off',
			'○ 4 · Delivery tank 5 m higher'
		]);
		// Unticked, a case keeps its place in the list, and the rings after it are numbered on.
		await fireEvent.click(
			within(within(card()).getByRole('group', { name: 'Cases on this chart' })).getByRole(
				'checkbox',
				{ name: /Both pumps off/ }
			)
		);
		await waitFor(() => expect(rings()).toHaveLength(3));
		expect(listed()).toEqual([
			'○ 1 · Pump PA off',
			'Both pumps off',
			'○ 2 · Pump PB off',
			'○ 3 · Delivery tank 5 m higher'
		]);
		// Running combinations keeps the chart's order (pumps-results-layout.md §5.3, §10 S5), each
		// case with its ring's number: the unticked case keeps its place, as in the list above.
		const combos = within(card()).getByRole('table', { name: 'Running combinations' });
		const headings = within(combos)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'rowgroup')
			.map((h) => h.firstElementChild!.textContent);
		expect(headings).toEqual([
			'Base case (shown)',
			'Pump PA off · ring 1',
			'Both pumps off',
			'Pump PB off · ring 2',
			'Delivery tank 5 m higher · ring 3'
		]);
	}, 20_000);

	it('Running combinations: the case shown, the cases with values in the chart’s order, then those without in case order, whatever is ticked; names trace buttons in the shown case’s group only (pumps-results-layout.md §5.3, §10 S5)', async () => {
		// S1 and S2 fail to solve: no values. S3 a tank level (no lineup) and S4 both off (0
		// running), so the chart's order (D24 §4.6) puts S4 before S3; in case order S1 to S4.
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			solve: async (_p, _o, request) => {
				const id = request?.scenarioId;
				if (id === 'S1' || id === 'S2') {
					throw new ValidationError(
						'Invalid input: 1 problem(s).',
						['body.project.scenarios.0.overrides.0: made-up rule'],
						400,
						'VALIDATION_ERROR'
					);
				}
				return structuredClone(((id && oneOff.scenarioCases[id]) || oneOff).solve);
			}
		});
		await ws.store.solveAll();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === null)).toHaveLength(2));
		const table = () => within(card()).getByRole('table', { name: 'Running combinations' });
		const headings = () =>
			within(table())
				.getAllByRole('rowheader')
				.filter((h) => h.getAttribute('scope') === 'rowgroup')
				.map((h) => h.firstElementChild!.textContent);
		// "Also show …" off: no rings, the order already the chart's.
		expect(ws.pumpGroupOthers).toBe(false);
		expect(headings()).toEqual([
			'Base case (shown)',
			'Both pumps off',
			'Delivery tank 5 m higher',
			'Pump PA off',
			'Pump PB off'
		]);
		// Its lead counts the two without results (§5.3 the lead).
		expect(card().querySelector('[data-combinations-lead]')!.textContent).toMatch(
			/^5 cases: 3 with current results \(.+\), none out of date, 2 without results\.$/
		);
		// On: the rings numbered in the same order; no case moves.
		await fireEvent.click(
			within(card()).getByRole('checkbox', { name: "Also show the other cases' station duties" })
		);
		await waitFor(() =>
			expect(headings()).toEqual([
				'Base case (shown)',
				'Both pumps off · ring 1',
				'Delivery tank 5 m higher · ring 2',
				'Pump PA off',
				'Pump PB off'
			])
		);
		// Unticked under "Cases on this chart": its ring goes, its place stays.
		await fireEvent.click(
			within(within(card()).getByRole('group', { name: 'Cases on this chart' })).getByRole(
				'checkbox',
				{ name: /Both pumps off/ }
			)
		);
		await waitFor(() =>
			expect(headings()).toEqual([
				'Base case (shown)',
				'Both pumps off',
				'Delivery tank 5 m higher · ring 1',
				'Pump PA off',
				'Pump PB off'
			])
		);
		// Names: trace buttons in the shown case's group only (§5.3 Pump names), each opening
		// that pump's trace for the case shown; plain row headers in every other group.
		const groups = within(table()).getAllByRole('rowgroup').slice(1);
		// Each named by its pump alone (its slot's symbol hidden), one per member.
		expect(within(groups[0]!).getAllByRole('button')).toEqual([
			within(groups[0]!).getByRole('button', { name: 'Pump PA' }),
			within(groups[0]!).getByRole('button', { name: 'Pump PB' })
		]);
		for (const group of groups.slice(1)) expect(within(group).queryAllByRole('button')).toEqual([]);
		await fireEvent.click(within(groups[0]!).getByRole('button', { name: 'Pump PB' }));
		expect(ws.inspected).toEqual({ kind: 'component', id: 'PB' });
		expect(within(groups[1]!).getAllByRole('rowheader', { name: 'Pump PB' })).toHaveLength(1);
	}, 20_000);

	it('in a scenario: made from the base case only, and the base’s duty beyond this curve', async () => {
		const { ws, calls } = setup(structuredClone(oneOff.project));
		await ws.store.solveAll();
		ws.setCase('S1');
		ws.pumpGroupOthers = true;
		// Each pump off chosen (page state; the gate holds under both presets, no control shows).
		ws.lineupPreset = 'each';
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === 'S1')).toHaveLength(2));
		// §7.12: gate 3's words become §7.2 row 3's.
		expect(block()).toHaveTextContent(
			'Cases are made from the base case: show the base case to add them. To study Pump PA off with pumps off, duplicate it in Scenarios and set those pumps off there.'
		);
		// No Add and no Solve all under the gate; its one button is D24 slice L2's "Pump lineups
		// table…", drawn whenever the block is, gates included (pump-lineups.md §8.1).
		expect(
			within(block())
				.getAllByRole('button')
				.map((b) => b.textContent?.trim())
		).toEqual(['Pump lineups table…']);
		await fireEvent.click(
			within(card()).getByRole('button', { name: 'Show data table of the group chart' })
		);
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
		await chooseEach();
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		const add = within(block()).getByRole('button', { name: 'Add 2 cases' });
		expect(add).toHaveAttribute('aria-disabled', 'true');
		expect(add).toHaveAccessibleDescription(
			'Adding 2 cases would make 21 scenarios; a project holds at most 20 scenarios.'
		);
		const depth = ws.store.undoDepth;
		await fireEvent.click(add);
		expect(ws.store.undoDepth).toBe(depth);
		expect(ws.scenarios).toHaveLength(19);
	});

	it('tells two pumps of the same name apart: the cases it makes, its notes, the rows and the extremes', async () => {
		// Synthetic: a duty and a standby unit both named "Booster pump" (names need not be unique).
		const project = withoutScenarios();
		for (const c of project.components) if (c.type === 'pump') c.name = 'Booster pump';
		const { ws, calls, solves } = setup(project);
		await openCard(ws, calls);
		await chooseEach();
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		await fireEvent.click(within(block()).getByRole('button', { name: 'Add 2 cases' }));
		expect(ws.scenarios.map((s) => [s.id, s.name])).toEqual([
			['S1', 'Booster pump (PA) off'],
			['S2', 'Booster pump (PB) off']
		]);
		// §7.12: the note "{name} has its case already: {found.name}." becomes the preview item
		// "{offName}: already a scenario, «{other}» ({id})", in §7.7's short form: the names are equal.
		expect(
			within(block())
				.getAllByText(/: already a scenario/)
				.map((p) => p.textContent)
		).toEqual([
			'Booster pump (PA) off: already a scenario (S1)',
			'Booster pump (PB) off: already a scenario (S2)'
		]);
		await fireEvent.click(within(block()).getByRole('button', { name: 'Solve all (2)' }));
		await waitFor(() => expect(solves).toEqual([null, 'S1', 'S2']));
		// The extremes a table (pumps-results-layout.md §5.3, §10 S5): the six pump and measure
		// pairs the dl's terms named, pinned by the row headers (the twins still told apart by
		// their ids), the column headers, and each row's cells under the three measures, none empty.
		const extremes = await within(card()).findByRole('table', {
			name: 'Extremes over these cases'
		});
		expect(
			within(extremes)
				.getAllByRole('rowheader')
				.map((h) => h.textContent)
		).toEqual(['Booster pump (PA)', 'Booster pump (PB)']);
		expect(
			within(extremes)
				.getAllByRole('columnheader')
				.map((h) => h.textContent)
		).toEqual(['Pump', 'Largest flow', 'Largest shaft power', 'Smallest NPSH margin']);
		const extremeRows = within(extremes)
			.getAllByRole('row')
			.filter((r) => within(r).queryByRole('rowheader'));
		expect(
			extremeRows.map((r) =>
				within(r)
					.getAllByRole('cell')
					.map((c) => c.dataset.label)
			)
		).toEqual([
			['Largest flow', 'Largest shaft power', 'Smallest NPSH margin'],
			['Largest flow', 'Largest shaft power', 'Smallest NPSH margin']
		]);
		for (const row of extremeRows) {
			for (const cell of within(row).getAllByRole('cell')) {
				expect(cell.textContent!.trim()).not.toBe('');
			}
		}
		// Running combinations: each case's two member rows have headers of their own (the slot's
		// symbol is hidden from screen readers, so the names alone tell them apart).
		const table = within(card()).getByRole('table', { name: 'Running combinations' });
		const members = within(table)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'row');
		expect(members).toHaveLength(6);
		expect(within(table).getAllByRole('rowheader', { name: 'Booster pump (PA)' })).toHaveLength(3);
		expect(within(table).getAllByRole('rowheader', { name: 'Booster pump (PB)' })).toHaveLength(3);
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
		await chooseEach();
		// Each read again: the block's button is drawn anew when the case shown changes, and the
		// menu closes when a run ends (its focus goes to Solve).
		const ours = () => within(block()).getByRole('button', { name: /^Solve all/ });
		const menu = () => screen.queryByRole('group', { name: 'Case' });
		const theirs = () => within(menu()!).getByRole('button', { name: 'Solve all' });
		/**
		 * The block's reason, drawn as the state asks (pumps-results-layout.md §5.3 item 5, §6.2): a
		 * lasting one visible text, no title; a passing one (a solve or Solve all runs) visually
		 * hidden and the button's title (S4 review MUT-01: PumpsView's `passing`).
		 */
		const reason = () => block().querySelector<HTMLElement>('[id$="-solve-all"]')!;
		const same = async (words: string, form: 'lasting' | 'passing') => {
			if (!menu()) await fireEvent.click(screen.getByRole('button', { name: /^Scenarios/ }));
			await waitFor(() => expect(theirs()).toHaveAccessibleDescription(words));
			expect(ours()).toHaveAccessibleDescription(words);
			expect(ours()).toHaveAttribute('aria-disabled', 'true');
			expect(reason()).toHaveTextContent(words);
			if (form === 'lasting') {
				expect(reason(), words).not.toHaveClass('sr-only');
				expect(reason(), words).toHaveClass('hint');
				expect(ours(), words).not.toHaveAttribute('title');
			} else {
				expect(reason(), words).toHaveClass('sr-only');
				expect(ours(), words).toHaveAttribute('title', words);
			}
		};
		await same(
			'Every case is solved except Delivery tank 5 m higher, which has an error to fix first.',
			'lasting'
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
		await same("Every case's results are current.", 'lasting');
		// A solve of another case than the one shown, in flight: both name that case.
		held = deferred<void>();
		const release = held.resolve;
		ws.setCase('S1');
		const solving = ws.solve();
		ws.setCase(null);
		await same('A solve of Pump PA off is running; Cancel in the header stops it.', 'passing');
		held = null;
		release();
		await solving;
		await same("Every case's results are current.", 'lasting');
		// A Solve all run, held on the one case it solves.
		ws.store.update(
			(p) => withScenarios(p, [...scenariosOf(p), { id: 'S5', name: 'Copy', overrides: [] }]),
			'add scenario'
		);
		held = deferred<void>();
		const end = held.resolve;
		const run = ws.solveAll();
		await same('Solve all is running; Cancel in the header stops it.', 'passing');
		held = null;
		end();
		await run;
		await same("Every case's results are current.", 'lasting');
		// Six states, each awaited: the budget of the card's other long tests.
	}, 20_000);
});

describe('"Cases on this chart" past its cap of six', () => {
	it('keeps the place a case leaves free: the case unticked can be ticked again, or another into its place', async () => {
		// Seven other cases: the one-off project's four and three copies of the base (no changes),
		// so the seventh in the chart's order (Copy S7) is past the cap and reads as unticked.
		const project = structuredClone(oneOff.project);
		const copies = ['S5', 'S6', 'S7'].map((id) => ({ id, name: `Copy ${id}`, overrides: [] }));
		const { ws } = setup(withScenarios(project, [...scenariosOf(project), ...copies]));
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		const group = () => within(card()).getByRole('group', { name: 'Cases on this chart' });
		const box = (name: RegExp) =>
			within(group()).getByRole('checkbox', { name }) as HTMLInputElement;
		const capped = (name: RegExp) => box(name).getAttribute('aria-disabled') === 'true';
		const ticked = () =>
			within(group())
				.getAllByRole('checkbox')
				.filter((b) => (b as HTMLInputElement).checked)
				.map((b) =>
					b
						.closest('label')!
						.textContent!.replace(/^[^A-Z]*/, '')
						.trim()
				);
		const hint = 'At most 6 other cases at once.';
		await waitFor(() => expect(within(group()).getAllByRole('checkbox')).toHaveLength(7));
		const six = [
			'Pump PA off',
			'Both pumps off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6'
		];
		expect(ticked()).toEqual(six);
		expect(capped(/Copy S7/)).toBe(true);
		expect(group()).toHaveTextContent(hint);

		// Unticked, Pump PA off leaves its place free: no case comes in by itself.
		await fireEvent.click(box(/Pump PA off/));
		expect(ticked()).toEqual(six.slice(1));
		expect(capped(/Pump PA off/)).toBe(false);
		expect(capped(/Copy S7/)).toBe(false);
		expect(group()).not.toHaveTextContent(hint);
		expect(ws.pumpGroupUnticked).toEqual(['S1', 'S7']);

		// Ticked again, it takes its place back, and the box past the cap is capped again.
		await fireEvent.click(box(/Pump PA off/));
		expect(ticked()).toEqual(six);
		expect(box(/Pump PA off/).checked).toBe(true);
		expect(capped(/Copy S7/)).toBe(true);
		expect(ws.pumpGroupUnticked).toEqual(['S7']);

		// Or another case is ticked into the place: then the case unticked is the one capped.
		await fireEvent.click(box(/Pump PA off/));
		await fireEvent.click(box(/Copy S7/));
		expect(ticked()).toEqual([...six.slice(1), 'Copy S7']);
		expect(capped(/Pump PA off/)).toBe(true);
		expect(ws.pumpGroupUnticked).toEqual(['S1']);
		// A click on the capped box ticks nothing.
		await fireEvent.click(box(/Pump PA off/));
		expect(box(/Pump PA off/).checked).toBe(false);
		expect(ticked()).toEqual([...six.slice(1), 'Copy S7']);
	}, 20_000);
});
