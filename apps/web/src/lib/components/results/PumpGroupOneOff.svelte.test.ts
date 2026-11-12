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
import { besideCaseTag, designators, shownCaseTag } from '$lib/testing/helpers';
import { systemCurveResponse } from '$lib/testing/results';
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
	// The data table shown is remembered in this browser (pumps-results-layout.md §9 S7): each
	// test starts from none remembered.
	localStorage.clear();
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
		/** The pump chart's system curves (made-up), when a test needs them. */
		systemCurve?: Solver['systemCurve'];
	} = {}
) {
	const calls: Call[] = [];
	const solves: (string | null)[] = [];
	const responsesOf = (id: string | undefined): Responses =>
		(id && oneOff.scenarioCases[id]) || oneOff;
	const solver: Solver = {
		...(options.systemCurve ? { systemCurve: options.systemCurve } : {}),
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
			// Its ring named by its case's number (owner, 2026-11-12, nit 5;
			// docs/proposals/pumps-nits.md item 5, slice 5b: "Case 2: …" in place of "2 · …").
			expect(within(legend).getByText('Case 2: Pump PB off (station duty)')).toBeVisible()
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
			// Its ring named by its case's number (owner, 2026-11-12, nit 5;
			// docs/proposals/pumps-nits.md item 5, slice 5b: "Case 2: …" in place of "2 · …").
			expect(within(legend).getByText('Case 2: Pump PB off (station duty)')).toBeVisible()
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
		// D24 §4.6: the requests go in the chart's order (S1, S4, S2, S3), so S3's ring, drawn once
		// all four are, is the last; it carries its case's number, 3 (nit 5, slice 5b: no longer the
		// fourth ring by the chart's order).
		await waitFor(() =>
			expect(within(within(card()).getByRole('figure')).getByRole('img')).toHaveAccessibleName(
				/case 3: Delivery tank 5 m higher/
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
		// Its heading named with its case's number first (nit 5, slice 5b).
		expect(
			within(table).getByRole('rowheader', { name: /^Case 1: Pump PA off/ })
		).toHaveTextContent(waits);
		expect(card().textContent).not.toContain('being computed');
		release.S2.resolve();
		await running;
		const legend = within(card()).getByRole('list', { name: 'Legend' });
		// D24 §4.6: the requests go in the chart's order (S1, S4, S2, S3), so S3's ring, drawn once
		// all four are, is the last; it carries its case's number, 3 (nit 5, slice 5b: no longer the
		// fourth ring by the chart's order).
		await waitFor(() =>
			expect(
				within(legend).getByText('Case 3: Delivery tank 5 m higher (station duty)')
			).toBeVisible()
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
		// D24 §4.6: the requests go in the chart's order (S1, S4, S2, S3), so S3's ring, drawn once
		// all four are, is the last; it carries its case's number, 3 (nit 5, slice 5b: no longer the
		// fourth ring by the chart's order).
		await waitFor(() =>
			expect(within(within(card()).getByRole('figure')).getByRole('img')).toHaveAccessibleName(
				/case 3: Delivery tank 5 m higher/
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
		// D24 §4.6: the requests go in the chart's order (S1, S4, S2, S3), so S3's ring, drawn once
		// all four are, is the last; it carries its case's number, 3 (nit 5, slice 5b: no longer the
		// fourth ring by the chart's order).
		await waitFor(() => expect(img()).toHaveAccessibleName(/case 3: Delivery tank 5 m higher/));
		const name = img().getAttribute('aria-label')!;
		// D24 §9.6: with this case's group curve drawn, each case's part gains "; group curve:
		// {words}" (its own curve drawn for a case with one pump off, which has flow; the same as this
		// case's for the delivery tank; none drawn for both pumps off), then the curves drawn.
		// Each case by its number (nit 5, slice 5b): Pump PA off 1, Pump PB off 2, the tank 3, both
		// off 4, in place of the rings' numbers by the chart's order.
		expect(name).toMatch(
			/case 1: Pump PA off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network; group curve: drawn \(1 running\): it crosses the group system curve at the ring\)/
		);
		expect(name).toMatch(
			/case 2: Pump PB off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network; group curve: drawn \(1 running\): it crosses the group system curve at the ring\)/
		);
		expect(name).toMatch(
			/case 3: Delivery tank 5 m higher, [\d.]+ L\/s at a rise of [\d.]+ m \(No: the rest of the network differs from this case's; its own group system curve is not drawn; group curve: the same as this case's: the station is the same inside\)/
		);
		expect(name).toMatch(
			/case 4: Both pumps off, 0 L\/s at a rise of 19 m \(Not said: at zero station flow the rest can hold more than one state; group curve: not drawn: no flow at any rise\)/
		);
		expect(name).toMatch(
			/; other cases' group curves drawn: case 1 \(1 running\) and case 2 \(1 running\); group curve shown; group system curve shown\.$/
		);
		await fireEvent.click(
			within(card()).getByRole('button', { name: 'Show data table of the group chart' })
		);
		const table = within(card()).getByRole('table', { name: "Other cases' station duties" });
		const claims = within(table)
			.getAllByRole('row')
			.slice(1)
			.map((r) => r.querySelectorAll('td')[2]?.textContent);
		// The table's rows in number order (nit 5, slice 5b; Q2 "By list place", in place of the
		// rings' order, D24 §7.9): Pump PA off, Pump PB off, Delivery tank 5 m higher, Both pumps
		// off.
		expect(
			within(table)
				.getAllByRole('rowheader')
				.map((h) => [shownCaseTag(h), besideCaseTag(h)])
		).toEqual([
			['1', 'Pump PA off'],
			['2', 'Pump PB off'],
			['3', 'Delivery tank 5 m higher'],
			['4', 'Both pumps off']
		]);
		expect(claims).toEqual([
			'Yes: the same rest of the network',
			'Yes: the same rest of the network',
			"No: the rest of the network differs from this case's; its own group system curve is not drawn",
			'Not said: at zero station flow the rest can hold more than one state'
		]);
		// Running combinations: every case, the shown first, with its station line, then the other
		// cases in number order, each heading led by its case's number in a box (owner, 2026-11-12,
		// nit 5; Q2 "By list place"; docs/proposals/pumps-nits.md item 5, slice 5b: in place of the
		// chart's order and " · ring n").
		const combos = within(card()).getByRole('table', { name: 'Running combinations' });
		const headings = within(combos)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'rowgroup')
			.map((h) => [shownCaseTag(h.firstElementChild!), besideCaseTag(h.firstElementChild!)]);
		expect(headings).toEqual([
			['Base', 'Base case (shown)'],
			['1', 'Pump PA off'],
			['2', 'Pump PB off'],
			['3', 'Delivery tank 5 m higher'],
			['4', 'Both pumps off']
		]);
	});

	// Nit 5, slice 5b (owner, 2026-11-12; Q2 "By list place"; docs/proposals/pumps-nits.md item
	// 5): replaces "lists 'Cases on this chart' and numbers the rings in the chart's order (D24
	// §4.6, §7.9)". The lineup priority still chooses the order of the requests and what is drawn;
	// the list, the rings and Running combinations run in number order, each case its own number.
	it('lists "Cases on this chart" in number order, each ring its case’s number; the lineup priority orders the requests (nit 5, slice 5b; D24 §4.6)', async () => {
		// S1 Pump PA off and S2 Pump PB off (1 running each), S3 a tank level (no lineup), S4 both
		// off (0 running): one lineup of each count first, most running first (S1, S4), then the
		// other lineup (S2), then every other case (S3): the requests' order.
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
			'Case 1: Pump PA off (station duty)',
			'Case 2: Pump PB off (station duty)',
			'Case 3: Delivery tank 5 m higher (station duty)',
			'Case 4: Both pumps off (station duty)'
		]);
		expect(others(calls).map((c) => c.scenarioId)).toEqual(['S1', 'S4', 'S2', 'S3']);
		const listed = () =>
			within(within(card()).getByRole('group', { name: 'Cases on this chart' }))
				.getAllByRole('checkbox')
				.map((box) => [shownCaseTag(box.closest('label')!), besideCaseTag(box.closest('label')!)]);
		expect(listed()).toEqual([
			['1', 'Pump PA off'],
			['2', 'Pump PB off'],
			['3', 'Delivery tank 5 m higher'],
			['4', 'Both pumps off']
		]);
		// Unticked, a case keeps its place in the list and its number, and every ring keeps its own.
		await fireEvent.click(
			within(within(card()).getByRole('group', { name: 'Cases on this chart' })).getByRole(
				'checkbox',
				{ name: /Both pumps off/ }
			)
		);
		await waitFor(() => expect(rings()).toHaveLength(3));
		expect(rings()).toEqual([
			'Case 1: Pump PA off (station duty)',
			'Case 2: Pump PB off (station duty)',
			'Case 3: Delivery tank 5 m higher (station duty)'
		]);
		expect(listed()).toEqual([
			['1', 'Pump PA off'],
			['2', 'Pump PB off'],
			['3', 'Delivery tank 5 m higher'],
			['4', 'Both pumps off']
		]);
		// Running combinations keeps number order (pumps-results-layout.md §5.3), each case with its
		// number: the unticked case keeps its place and its number, as in the list above.
		const combos = within(card()).getByRole('table', { name: 'Running combinations' });
		const headings = within(combos)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'rowgroup')
			.map((h) => [shownCaseTag(h.firstElementChild!), besideCaseTag(h.firstElementChild!)]);
		expect(headings).toEqual([
			['Base', 'Base case (shown)'],
			['1', 'Pump PA off'],
			['2', 'Pump PB off'],
			['3', 'Delivery tank 5 m higher'],
			['4', 'Both pumps off']
		]);
	}, 20_000);

	// Nit 5, slice 5b (owner, 2026-11-12; Q2 "By list place"; docs/proposals/pumps-nits.md item
	// 5): replaces S5's order (the cases with values in the chart's order, then those without in
	// case order): every case in number order, with values or not, the case shown first.
	it('Running combinations: the case shown, then every case in number order, with values or not, whatever is ticked; names trace buttons in the shown case’s group only (pumps-results-layout.md §5.3; nit 5, slice 5b)', async () => {
		// S1 and S2 fail to solve: no values. S3 a tank level (no lineup) and S4 both off (0
		// running): the chart's order (D24 §4.6) puts S4 before S3, which moves no case here.
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
		/** Each heading's first line: its case's number in a box, then its words. */
		const headings = () =>
			within(table())
				.getAllByRole('rowheader')
				.filter((h) => h.getAttribute('scope') === 'rowgroup')
				.map((h) => [shownCaseTag(h.firstElementChild!), besideCaseTag(h.firstElementChild!)]);
		const ORDER = [
			['Base', 'Base case (shown)'],
			['1', 'Pump PA off'],
			['2', 'Pump PB off'],
			['3', 'Delivery tank 5 m higher'],
			['4', 'Both pumps off']
		];
		// "Also show …" off: no rings, every case in number order with its number.
		expect(ws.pumpGroupOthers).toBe(false);
		expect(headings()).toEqual(ORDER);
		// Its lead counts the two without results (§5.3 the lead).
		expect(card().querySelector('[data-combinations-lead]')!.textContent).toMatch(
			/^5 cases: 3 with current results \(.+\), none out of date, 2 without results\.$/
		);
		// On: the rings drawn, each tagged with its case's number; no case and no number moves.
		const ringList = () =>
			[...card().querySelectorAll('[data-group-rings] li')].map((li) => shownCaseTag(li));
		await fireEvent.click(
			within(card()).getByRole('checkbox', { name: "Also show the other cases' station duties" })
		);
		await waitFor(() => expect(ringList()).toEqual(['3', '4']));
		expect(headings()).toEqual(ORDER);
		// Unticked under "Cases on this chart": its ring goes, its place and its number stay.
		await fireEvent.click(
			within(within(card()).getByRole('group', { name: 'Cases on this chart' })).getByRole(
				'checkbox',
				{ name: /Both pumps off/ }
			)
		);
		await waitFor(() => expect(ringList()).toEqual(['3']));
		expect(headings()).toEqual(ORDER);
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
		// Another case with values (Both pumps off, last in number order): plain row headers.
		expect(within(groups[4]!).getAllByRole('rowheader', { name: 'Pump PB' })).toHaveLength(1);
	}, 20_000);

	it('Running combinations with a scenario shown: its group first with the trace buttons, which open its trace; none in the base case’s (pumps-results-layout.md §5.3 Pump names, §10 S5)', async () => {
		const { ws, calls } = setup(structuredClone(oneOff.project));
		await ws.store.solveAll();
		ws.setCase('S3');
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === 'S3')).toHaveLength(2));
		const table = within(card()).getByRole('table', { name: 'Running combinations' });
		const groups = within(table).getAllByRole('rowgroup').slice(1);
		// Each heading's first line's words beside its case's number (nit 5, slice 5b).
		const heading = (g: HTMLElement) =>
			besideCaseTag(
				within(g)
					.getAllByRole('rowheader')
					.find((h) => h.getAttribute('scope') === 'rowgroup')!.firstElementChild!
			);
		expect(heading(groups[0]!)).toBe('Delivery tank 5 m higher (shown)');
		expect(shownCaseTag(groups[0]!.querySelector('th[scope="rowgroup"]')!)).toBe('3');
		expect(within(groups[0]!).getAllByRole('button')).toEqual([
			within(groups[0]!).getByRole('button', { name: 'Pump PA' }),
			within(groups[0]!).getByRole('button', { name: 'Pump PB' })
		]);
		const baseGroup = groups.find((g) => heading(g) === 'Base case')!;
		expect(within(baseGroup).queryAllByRole('button')).toEqual([]);
		for (const g of groups.slice(1)) expect(within(g).queryAllByRole('button')).toEqual([]);
		// Pressing one opens that pump's trace with the scenario still the case shown, so the
		// trace and the values beside the name are one case's (§5.3; GOALS §4.2, D15).
		await fireEvent.click(within(groups[0]!).getByRole('button', { name: 'Pump PB' }));
		expect(ws.inspected).toEqual({ kind: 'component', id: 'PB' });
		expect(ws.store.activeCase).toBe('S3');
	}, 20_000);

	it('Running combinations sorted, a scenario shown: one table with a Case column, the trace buttons in that case’s rows only, each opening its trace with the case kept; the sort cleared, the cases back (pumps-results-layout.md §9 S6b)', async () => {
		const { ws, calls } = setup(structuredClone(oneOff.project));
		await ws.store.solveAll();
		ws.setCase('S3');
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls.filter((c) => c.scenarioId === 'S3')).toHaveLength(2));
		// Its box (a region only while it overflows, pumps-results-layout.md §9 S7), by its table.
		const region = within(card()).getByRole('table', {
			name: 'Running combinations'
		}).parentElement!;
		// Each heading's first line's words beside its case's number (nit 5, slice 5b).
		const headings = () =>
			[...region.querySelectorAll('th[scope="rowgroup"]')].map((h) =>
				besideCaseTag(h.firstElementChild!)
			);
		const before = headings();
		expect(before[0]).toBe('Delivery tank 5 m higher (shown)');
		const margin = within(region).getByRole('columnheader', { name: /^NPSH margin/ });
		await fireEvent.click(within(margin).getByRole('button'));
		expect(margin).toHaveAttribute('aria-sort', 'ascending');
		expect(headings()).toEqual([]);
		const rows = [...region.querySelectorAll<HTMLElement>('tbody > tr')].filter((r) =>
			r.querySelector('th[scope="row"]')
		);
		// Every case's two members: the base case and its four scenarios, each solved.
		expect(rows).toHaveLength(10);
		// Its Case cell's words beside its case's number (nit 5, slice 5b), the number its case's.
		const caseOf = (r: Element) => besideCaseTag(r.querySelector('td[data-label="Case"]')!);
		const shownCell = rows
			.map((r) => r.querySelector('td[data-label="Case"]')!)
			.find((cell) => besideCaseTag(cell) === 'Delivery tank 5 m higher (shown)')!;
		expect(shownCaseTag(shownCell)).toBe('3');
		for (const r of rows) {
			expect(!!r.querySelector('button'), caseOf(r)).toBe(
				caseOf(r) === 'Delivery tank 5 m higher (shown)'
			);
		}
		const shown = rows.filter((r) => r.querySelector('button'));
		expect(shown).toHaveLength(2);
		const pb = shown.find((r) => within(r).queryByRole('button', { name: 'Pump PB' }))!;
		await fireEvent.click(within(pb).getByRole('button', { name: 'Pump PB' }));
		expect(ws.inspected).toEqual({ kind: 'component', id: 'PB' });
		expect(ws.store.activeCase).toBe('S3');
		// Descending, then cleared: the cases again, in the same order.
		await fireEvent.click(within(margin).getByRole('button'));
		await fireEvent.click(within(margin).getByRole('button'));
		expect(margin).not.toHaveAttribute('aria-sort');
		expect(headings()).toEqual(before);
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
		// so the seventh in the chart's order (Copy S7) is past the cap and reads as unticked. The
		// list runs in number order (nit 5, slice 5b; Q2): the lineup priority only chooses which.
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
				// Its words beside its case's number (nit 5, slice 5b: the number's box and words).
				.map((b) => besideCaseTag(b.closest('label')!));
		const hint = 'At most 6 other cases at once.';
		await waitFor(() => expect(within(group()).getAllByRole('checkbox')).toHaveLength(7));
		const six = [
			'Pump PA off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off',
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
		// The case unticked is the page's one choice (pumps-results-layout.md §9 S8); the case past
		// the cap is the card's own.
		expect(ws.casesUnticked).toEqual(['S1']);
		expect(ws.pumpGroupUnticked).toEqual(['S7']);

		// Ticked again, it takes its place back, and the box past the cap is capped again.
		await fireEvent.click(box(/Pump PA off/));
		expect(ticked()).toEqual(six);
		expect(box(/Pump PA off/).checked).toBe(true);
		expect(capped(/Copy S7/)).toBe(true);
		expect(ws.casesUnticked).toEqual([]);
		expect(ws.pumpGroupUnticked).toEqual(['S7']);

		// Or another case is ticked into the place: then the case unticked is the one capped.
		await fireEvent.click(box(/Pump PA off/));
		await fireEvent.click(box(/Copy S7/));
		expect(ticked()).toEqual([...six.slice(1), 'Copy S7']);
		expect(capped(/Pump PA off/)).toBe(true);
		expect(ws.casesUnticked).toEqual(['S1']);
		expect(ws.pumpGroupUnticked).toEqual([]);
		// A click on the capped box ticks nothing.
		await fireEvent.click(box(/Pump PA off/));
		expect(box(/Pump PA off/).checked).toBe(false);
		expect(ticked()).toEqual([...six.slice(1), 'Copy S7']);
	}, 20_000);
});

// One choice of cases for both charts (proposal pumps-results-layout.md §9 S8, §10 One choice of
// cases, the owner's answer 2): the cases the user unticked one set for "Cases on the chart" and
// "Cases on this chart"; the cases past each list's cap at an untick that chart's own; the pump
// chart's list kept over a pump switch; its slots; each case's number (owner, 2026-11-12, nit 5;
// docs/proposals/pumps-nits.md item 5, slice 5b: in place of S8's markers). Both lists run in
// number order (Q2): the card's arrays below moved from the chart's order (Pump PA off, Both pumps
// off, Pump PB off, …) to it.
describe('one choice of cases for the pump chart and the card', () => {
	/** The one-off's four other cases and copies of the base (no changes), S5 onwards. */
	function withCopies(ids: string[]) {
		const project = structuredClone(oneOff.project);
		const copies = ids.map((id) => ({ id, name: `Copy ${id}`, overrides: [] }));
		return withScenarios(project, [...scenariosOf(project), ...copies]);
	}
	const pumpCases = () => results().getByRole('group', { name: 'Cases on the chart' });
	const cardCases = () => within(card()).getByRole('group', { name: 'Cases on this chart' });
	/** A box's label without its case's number (nit 5, slice 5b: its box and its words). */
	const words = (b: HTMLElement) => besideCaseTag(b.closest('label')!);
	const ticked = (group: HTMLElement) =>
		within(group)
			.getAllByRole('checkbox')
			.filter((b) => (b as HTMLInputElement).checked)
			.map(words);
	const box = (group: HTMLElement, name: string) =>
		within(group).getByRole('checkbox', { name: new RegExp(`${name}$`) }) as HTMLInputElement;
	const capped = (group: HTMLElement, name: string) =>
		box(group, name).getAttribute('aria-disabled') === 'true';
	/**
	 * The boxes' labels under "Cases on the chart": each case's number and words, and "(unticked)"
	 * when not drawn (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md item 5, slice 5b: a
	 * case's number shows whether it is drawn or not, where S8's marker showed only when drawn).
	 */
	const labels = () =>
		within(pumpCases())
			.getAllByRole('checkbox')
			.map(
				(b) =>
					`${shownCaseTag(b.closest('label')!)} ${besideCaseTag(b.closest('label')!)}${(b as HTMLInputElement).checked ? '' : ' (unticked)'}`
			);
	/** Solve every case, show the Pumps view, open the card with its other cases on. */
	async function showBoth(ws: ReturnType<typeof setup>['ws']) {
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() =>
			expect(within(cardCases()).getAllByRole('checkbox').length).toBeGreaterThan(0)
		);
	}

	it('unticks a case under either list under the other too, every other case drawn staying; the cases past one list’s cap stay unticked on that chart only', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await showBoth(ws);
		// The card draws six, in its order; Pump PA's chart five, its two off cases taking no slot.
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S5',
			'Copy S6'
		]);
		expect(ticked(pumpCases())).toEqual([
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Copy S7'
		]);
		expect(capped(cardCases(), 'Copy S7')).toBe(true);
		expect(capped(pumpCases(), 'Copy S8')).toBe(true);
		// The rings drawn: each case on the card's chart with a station duty, by name.
		const rings = () =>
			[...card().querySelectorAll('[data-group-rings] li .font-medium')].map((n) => n.textContent);
		await waitFor(() => expect(rings()).toContain('Copy S6'));
		const ringsBefore = rings();
		expect(ringsBefore).toContain('Pump PB off');

		// Unticked under "Cases on this chart": unticked under "Cases on the chart" too. Copy S7,
		// past the card's cap, stays unticked on the card only: the pump chart keeps drawing it.
		await fireEvent.click(box(cardCases(), 'Pump PB off'));
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S5',
			'Copy S6'
		]);
		expect(ticked(pumpCases())).toEqual([
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Copy S7'
		]);
		expect(box(pumpCases(), 'Pump PB off').checked).toBe(false);
		// The places left free stay free: no case comes onto either chart by itself.
		for (const name of ['Pump PB off', 'Copy S7', 'Copy S8']) {
			expect(capped(cardCases(), name)).toBe(false);
		}
		expect(capped(pumpCases(), 'Copy S8')).toBe(false);
		expect(ws.casesUnticked).toEqual(['S2']);
		expect(ws.pumpGroupUnticked).toEqual(['S7', 'S8']);
		expect(ws.pumpChartUnticked).toEqual(['S8']);

		// Unticked under "Cases on the chart": unticked on the card too, every other ring staying.
		await waitFor(() =>
			expect(rings()).toEqual(ringsBefore.filter((name) => name !== 'Pump PB off'))
		);
		await fireEvent.click(box(pumpCases(), 'Copy S5'));
		expect(ticked(pumpCases())).toEqual(['Delivery tank 5 m higher', 'Copy S6', 'Copy S7']);
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S6'
		]);
		expect(ws.casesUnticked).toEqual(['S2', 'S5']);
		expect(ws.pumpGroupUnticked).toEqual(['S7', 'S8']);
		expect(ws.pumpChartUnticked).toEqual(['S8']);
		await waitFor(() =>
			expect(rings()).toEqual(
				ringsBefore.filter((name) => name !== 'Pump PB off' && name !== 'Copy S5')
			)
		);
	}, 30_000);

	it('ticks a case again under either list on both (the re-tick of web/cases-on-chart-retick), and a chart already full keeps every case it draws', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await showBoth(ws);
		await fireEvent.click(box(pumpCases(), 'Copy S5'));
		expect(box(cardCases(), 'Copy S5').checked).toBe(false);
		// Ticked again under the other list: on both, in its place.
		await fireEvent.click(box(cardCases(), 'Copy S5'));
		expect(ticked(pumpCases())).toEqual([
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Copy S7'
		]);
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S5',
			'Copy S6'
		]);
		expect(ws.casesUnticked).toEqual([]);

		// Pump PB off unticked on the card, Copy S7 ticked into its place there: the card is full.
		await fireEvent.click(box(cardCases(), 'Pump PB off'));
		await fireEvent.click(box(cardCases(), 'Copy S7'));
		const card6 = [
			'Pump PA off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S5',
			'Copy S6',
			'Copy S7'
		];
		expect(ticked(cardCases())).toEqual(card6);
		// Ticked again under "Cases on the chart": back on the pump chart, which has room; past
		// the cap on the card, which keeps every ring it draws.
		await fireEvent.click(box(pumpCases(), 'Pump PB off'));
		expect(ticked(pumpCases())).toEqual([
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Copy S7'
		]);
		expect(ticked(cardCases())).toEqual(card6);
		expect(capped(cardCases(), 'Pump PB off')).toBe(true);
		expect(ws.casesUnticked).toEqual([]);
		expect(ws.pumpGroupUnticked).toEqual(['S8', 'S2']);
	}, 30_000);

	it('keeps the pump chart’s unticks over a pump switch, and its numbers by case', async () => {
		const { ws } = setup(structuredClone(oneOff.project));
		await showBoth(ws);
		expect(labels()).toEqual(['2 Pump PB off', '3 Delivery tank 5 m higher']);
		await fireEvent.click(box(pumpCases(), 'Delivery tank 5 m higher'));
		expect(labels()).toEqual(['2 Pump PB off', '3 Delivery tank 5 m higher (unticked)']);
		// Pump PB on the chart: its own cases, the one unticked still unticked.
		await fireEvent.change(results().getByRole('combobox', { name: 'Pump chart' }), {
			target: { value: 'PB' }
		});
		await waitFor(() =>
			expect(
				results().getByRole('figure', { name: /^Pump and system curves: Pump PB/ })
			).toBeTruthy()
		);
		expect(labels()).toEqual(['1 Pump PA off', '3 Delivery tank 5 m higher (unticked)']);
		expect(
			within(pumpCases()).getByText(/^Off in this case \(no operating point\):/)
		).toHaveTextContent(
			'Off in this case (no operating point): case 2: Pump PB off; case 4: Both pumps off.'
		);
		expect(box(cardCases(), 'Delivery tank 5 m higher').checked).toBe(false);
		// And back: as left.
		await fireEvent.change(results().getByRole('combobox', { name: 'Pump chart' }), {
			target: { value: 'PA' }
		});
		await waitFor(() =>
			expect(
				results().getByRole('figure', { name: /^Pump and system curves: Pump PA/ })
			).toBeTruthy()
		);
		expect(labels()).toEqual(['2 Pump PB off', '3 Delivery tank 5 m higher (unticked)']);
		expect(ws.casesUnticked).toEqual(['S3']);
	}, 30_000);

	it('asks the other cases’ system curves only while they are on, for the cases drawn; a case they push past the cap shows it; each case keeps its number (§9 S8 Slots; nit 5, slice 5b)', async () => {
		const curves: (string | null)[] = [];
		const { ws } = setup(withCopies(['S5', 'S6', 'S7']), {
			systemCurve: async (_project, pumpId, options) => {
				curves.push(options?.scenarioId ?? null);
				return systemCurveResponse(pumpId);
			}
		});
		await showBoth(ws);
		await waitFor(() => expect(curves).toEqual([null]));
		// Off: Pump PA off and Both pumps off take no slot; the five others drawn, each its number.
		expect(labels()).toEqual([
			'2 Pump PB off',
			'3 Delivery tank 5 m higher',
			'5 Copy S5',
			'6 Copy S6',
			'7 Copy S7'
		]);
		expect(within(pumpCases()).queryByText('At most 6 cases at once.')).toBeNull();
		// Delivery tank unticked: every case keeps its number.
		await fireEvent.click(box(pumpCases(), 'Delivery tank 5 m higher'));
		const offAgain = [
			'2 Pump PB off',
			'3 Delivery tank 5 m higher (unticked)',
			'5 Copy S5',
			'6 Copy S6',
			'7 Copy S7'
		];
		expect(labels()).toEqual(offAgain);
		expect(curves).toEqual([null]);
		// On: the off cases take their slots, so Copy S7 goes past the cap and shows it; every case
		// keeps its number; the curves are asked for the five drawn only.
		await fireEvent.click(
			results().getByRole('checkbox', { name: "Also show the other cases' system curves" })
		);
		await waitFor(() => expect(curves).toHaveLength(6));
		expect([...curves.slice(1)].sort()).toEqual(['S1', 'S2', 'S4', 'S5', 'S6']);
		expect(labels()).toEqual([
			'1 Pump PA off',
			'2 Pump PB off',
			'3 Delivery tank 5 m higher (unticked)',
			'4 Both pumps off',
			'5 Copy S5',
			'6 Copy S6',
			'7 Copy S7 (unticked)'
		]);
		expect(capped(pumpCases(), 'Copy S7')).toBe(true);
		expect(box(pumpCases(), 'Copy S7')).toHaveAccessibleDescription('At most 6 cases at once.');
		expect(within(pumpCases()).queryByText(/^Off in this case/)).toBeNull();
		// Off again: Copy S7 drawn again with its number; nothing more asked.
		await fireEvent.click(
			results().getByRole('checkbox', { name: "Also show the other cases' system curves" })
		);
		expect(labels()).toEqual(offAgain);
		expect(curves).toHaveLength(6);
	}, 30_000);

	const showPump = async (id: string, name: string) => {
		await fireEvent.change(results().getByRole('combobox', { name: 'Pump chart' }), {
			target: { value: id }
		});
		await waitFor(() =>
			expect(
				results().getByRole('figure', { name: new RegExp(`^Pump and system curves: ${name}`) })
			).toBeTruthy()
		);
	};
	const curvesBox = () =>
		results().getByRole('checkbox', { name: "Also show the other cases' system curves" });
	const othersBox = () =>
		within(card()).getByRole('checkbox', { name: "Also show the other cases' station duties" });
	/** Solve every case, show the Pumps view, open the card with its other cases off. */
	async function openCardOnly(ws: ReturnType<typeof setup>['ws']) {
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(othersBox()).toBeTruthy());
		expect(ws.pumpGroupOthers).toBe(false);
		expect(within(card()).queryByRole('group', { name: 'Cases on this chart' })).toBeNull();
	}

	it('changes the card’s own unticks only while its chart draws the other cases: an untick or a tick on the pump chart while they are off leaves the card to draw its cap once they are on (§12 answer 2)', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await ws.store.solveAll();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		// Unticked on the pump chart before the card was ever opened, then ticked again there with
		// the card open and its other cases off: nothing of the card's own.
		await fireEvent.click(box(pumpCases(), 'Pump PB off'));
		await openCardOnly(ws);
		await fireEvent.click(box(pumpCases(), 'Pump PB off'));
		expect(ws.casesUnticked).toEqual([]);
		expect(ws.pumpGroupUnticked).toEqual([]);
		await fireEvent.click(othersBox());
		await waitFor(() => expect(within(cardCases()).getAllByRole('checkbox').length).toBe(8));
		const six = [
			'Pump PA off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S5',
			'Copy S6'
		];
		expect(ticked(cardCases())).toEqual(six);
		expect(capped(cardCases(), 'Pump PB off')).toBe(false);

		// Off again: Pump PB off unticked on the pump chart, with the card open and drawing none of
		// the other cases. On again: the card draws its cap, Copy S7 in the place left, which the
		// user never touched.
		await fireEvent.click(othersBox());
		expect(within(card()).queryByRole('group', { name: 'Cases on this chart' })).toBeNull();
		await fireEvent.click(box(pumpCases(), 'Pump PB off'));
		expect(ws.casesUnticked).toEqual(['S2']);
		expect(ws.pumpGroupUnticked).toEqual([]);
		await fireEvent.click(othersBox());
		await waitFor(() => expect(within(cardCases()).getAllByRole('checkbox').length).toBe(8));
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S5',
			'Copy S6',
			'Copy S7'
		]);
		expect(capped(cardCases(), 'Copy S8')).toBe(true);

		// And with the card closed: the same.
		ws.pumpGroupOthers = false;
		await fireEvent.click(box(pumpCases(), 'Pump PB off'));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		expect(ws.pumpGroupOpen).toBe(false);
		await fireEvent.click(box(pumpCases(), 'Copy S5'));
		expect(ws.casesUnticked).toEqual(['S5']);
		expect(ws.pumpGroupUnticked).toEqual([]);
	}, 30_000);

	/** The card's toggle: "Pumps together", opening and closing it. */
	const cardToggle = () => within(card()).getByRole('button', { name: /^Pumps together/ });

	it('changes none of the card’s own unticks by an untick on the pump chart while the card is closed with its other cases on: reopened, it draws its cap (§12 answer 2; S8 second check CHOICE-3)', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await showBoth(ws);
		await fireEvent.click(cardToggle());
		expect(ws.pumpGroupOpen).toBe(false);
		expect(ws.pumpGroupOthers).toBe(true);
		await fireEvent.click(box(pumpCases(), 'Copy S5'));
		expect(ws.casesUnticked).toEqual(['S5']);
		expect(ws.pumpGroupUnticked).toEqual([]);
		// Reopened: six, Copy S7 in the place Copy S5 left, which the user never touched.
		await fireEvent.click(cardToggle());
		await waitFor(() => expect(within(cardCases()).getAllByRole('checkbox').length).toBe(8));
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S6',
			'Copy S7'
		]);
	}, 30_000);

	for (const how of ['open', 'closed', 'with its other cases off'] as const) {
		it(`keeps a case the user ticked under “Cases on this chart” when another is ticked again under “Cases on the chart”, the card ${how}: the case ticked again past the card’s cap there (§9 S8; S8 second check CHOICE-2)`, async () => {
			const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
			await showBoth(ws);
			// Delivery tank unticked on the card, Copy S7 ticked into its place: the card is full,
			// with the six the user chose.
			await fireEvent.click(box(cardCases(), 'Delivery tank 5 m higher'));
			await fireEvent.click(box(cardCases(), 'Copy S7'));
			const chosen = [
				'Pump PA off',
				'Pump PB off',
				'Both pumps off',
				'Copy S5',
				'Copy S6',
				'Copy S7'
			];
			expect(ticked(cardCases())).toEqual(chosen);
			/** Close the card, or turn its other cases off; pressed again, back as it was. */
			const flip = async () => {
				if (how === 'closed') await fireEvent.click(cardToggle());
				if (how === 'with its other cases off') await fireEvent.click(othersBox());
			};
			await flip();
			expect(ws.pumpGroupOpen).toBe(how !== 'closed');
			expect(ws.pumpGroupOthers).toBe(how !== 'with its other cases off');
			// Delivery tank ticked again under "Cases on the chart": back on the pump chart.
			await fireEvent.click(box(pumpCases(), 'Delivery tank 5 m higher'));
			expect(box(pumpCases(), 'Delivery tank 5 m higher').checked).toBe(true);
			expect(ws.casesUnticked).toEqual([]);
			await flip();
			await waitFor(() => expect(within(cardCases()).getAllByRole('checkbox').length).toBe(8));
			// The card keeps every case the user chose; Delivery tank waits past its cap there.
			expect(ticked(cardCases())).toEqual(chosen);
			expect(capped(cardCases(), 'Delivery tank 5 m higher')).toBe(true);
			expect(capped(cardCases(), 'Copy S7')).toBe(false);
			expect(ws.pumpGroupUnticked).toEqual(['S8', 'S3']);
		}, 30_000);
	}

	// Nit 5, slice 5b (owner, 2026-11-12; Q2 "By list place"; docs/proposals/pumps-nits.md item
	// 5): the S8 tests of the markers (§9 S8 Markers; S8 second check MARK-2 and MARK-3, the
	// five-case boundary, the markers remembered past five) replaced by the same steps with each
	// case's number, which is its place in the Scenarios list whatever has a result, is drawn or is
	// shown, and never runs out.
	it('keeps each case’s number through the curves switched, unticks and ticks in either order and another pump shown (nit 5, slice 5b; was §9 S8 Markers)', async () => {
		const { ws } = setup(structuredClone(oneOff.project), {
			systemCurve: async (_project, pumpId) => systemCurveResponse(pumpId)
		});
		await showBoth(ws);
		// Off: Pump PA off and Both pumps off take no slot; the two drawn have their numbers.
		await waitFor(() => expect(curvesBox()).toBeEnabled());
		expect(labels()).toEqual(['2 Pump PB off', '3 Delivery tank 5 m higher']);
		const four = [
			'1 Pump PA off',
			'2 Pump PB off',
			'3 Delivery tank 5 m higher',
			'4 Both pumps off'
		];
		await fireEvent.click(curvesBox());
		await waitFor(() => expect(labels()).toEqual(four));
		for (const order of [
			['Pump PA off', 'Pump PB off'],
			['Pump PB off', 'Pump PA off']
		]) {
			for (const name of order) await fireEvent.click(box(pumpCases(), name));
			expect(labels()).toEqual([
				'1 Pump PA off (unticked)',
				'2 Pump PB off (unticked)',
				'3 Delivery tank 5 m higher',
				'4 Both pumps off'
			]);
			for (const name of order) await fireEvent.click(box(pumpCases(), name));
			expect(labels()).toEqual(four);
		}
		// Pump PB shown: the same cases, each the same number; its own off cases without slots
		// once the curves are off.
		await showPump('PB', 'Pump PB');
		expect(labels()).toEqual(four);
		await fireEvent.click(curvesBox());
		expect(labels()).toEqual(['1 Pump PA off', '3 Delivery tank 5 m higher']);
		await showPump('PA', 'Pump PA');
		expect(labels()).toEqual(['2 Pump PB off', '3 Delivery tank 5 m higher']);
	}, 30_000);

	it('gives each case its number with five, six or more other cases with a result: no boundary (nit 5, slice 5b; was S8 second check MARK-3)', async () => {
		const { ws } = setup(withCopies(['S5', 'S6']));
		await ws.store.solveAll();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		// Pump PA, the curves off: Pump PA off and Both pumps off take no slot; the four drawn have
		// their own numbers, past five cases with a result as before it.
		expect(labels()).toEqual([
			'2 Pump PB off',
			'3 Delivery tank 5 m higher',
			'5 Copy S5',
			'6 Copy S6'
		]);
		expect(ws.casesUnticked).toEqual([]);
	}, 30_000);

	it('keeps a case’s number over a pump switch when another case gives one pump no result (nit 5, slice 5b; was S8 second check MARK-2)', async () => {
		// A first case that closes Pump PA's valves: the API gives Pump PA no result in it (SDD
		// §4.10, a pump closed off on both sides is absent, flagged ISOLATED_SECTION). Emulated:
		// the base's answer without Pump PA's result.
		const project = structuredClone(oneOff.project);
		const isolating = { id: 'S5', name: 'Pump PA isolated', overrides: [] };
		const { ws } = setup(withScenarios(project, [isolating, ...scenariosOf(project)]), {
			solve: async (_p, _o, request) => {
				const id = request?.scenarioId ?? null;
				const answer = structuredClone(((id && oneOff.scenarioCases[id]) || oneOff).solve);
				if (id === 'S5') delete (answer.solvedState.pumpResults as Record<string, unknown>).PA;
				return answer;
			}
		});
		await ws.store.solveAll();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await showPump('PA', 'Pump PA');
		// The Scenarios list: Pump PA isolated 1, Pump PA off 2, Pump PB off 3, Delivery tank 4,
		// Both pumps off 5. Pump PA's chart draws Pump PB off and Delivery tank, each its number.
		const onPA = ['3 Pump PB off', '4 Delivery tank 5 m higher'];
		expect(labels()).toEqual(onPA);
		await showPump('PB', 'Pump PB');
		expect(labels()).toEqual(['1 Pump PA isolated', '2 Pump PA off', '4 Delivery tank 5 m higher']);
		await showPump('PA', 'Pump PA');
		expect(labels()).toEqual(onPA);
	}, 30_000);

	it('keeps each case’s number over a pump switch past five cases with a result, nothing remembered (nit 5, slice 5b; was §9 S8 Markers, remembered)', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7']), {
			systemCurve: async (_project, pumpId) => systemCurveResponse(pumpId)
		});
		await showBoth(ws);
		await waitFor(() => expect(curvesBox()).toBeEnabled());
		expect(labels()).toEqual([
			'2 Pump PB off',
			'3 Delivery tank 5 m higher',
			'5 Copy S5',
			'6 Copy S6',
			'7 Copy S7'
		]);
		// On: the off cases take their slots, Copy S6 and S7 go past the cap; every number stays.
		await fireEvent.click(curvesBox());
		const seven = [
			'1 Pump PA off',
			'2 Pump PB off',
			'3 Delivery tank 5 m higher',
			'4 Both pumps off',
			'5 Copy S5',
			'6 Copy S6 (unticked)',
			'7 Copy S7 (unticked)'
		];
		await waitFor(() => expect(labels()).toEqual(seven));
		// Pump PB draws the same five: each keeps its number.
		await showPump('PB', 'Pump PB');
		expect(labels()).toEqual(seven);
		await showPump('PA', 'Pump PA');
		expect(labels()).toEqual(seven);
	}, 30_000);

	it('cancels the card’s requests for a case unticked under “Cases on the chart”, as an untick on the card does', async () => {
		let firstS2 = true;
		const { ws, calls } = setup(structuredClone(oneOff.project), {
			hold: (call) => {
				if (call.scenarioId !== 'S2' || !firstS2) return undefined;
				firstS2 = false;
				return new Promise<void>(() => {});
			}
		});
		const state = (c: string) => ws.store.groupCurve(ws.store.resultsFor(c).response, ['PA', 'PB']);
		await showBoth(ws);
		// In the chart's order (S1, S4, S2, S3): S2's group curve held in flight.
		await waitFor(() => expect(calls.some((c) => c.scenarioId === 'S2')).toBe(true));
		expect(state('S2')).toEqual({ status: 'loading' });
		const held = calls.find((c) => c.scenarioId === 'S2')!;
		expect(held.settled).toBe(false);
		await fireEvent.click(box(pumpCases(), 'Pump PB off'));
		expect(box(cardCases(), 'Pump PB off').checked).toBe(false);
		expect(state('S2')).toEqual({ status: 'cancelled', by: 'user' });
		expect(held.settled).toBe(true);
	}, 30_000);

	it('keeps every case a full pump chart draws when a case is ticked again under “Cases on this chart”: past the cap there only', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await showBoth(ws);
		// Copy S5 unticked under "Cases on the chart", Copy S8 ticked into its place: full.
		await fireEvent.click(box(pumpCases(), 'Copy S5'));
		await fireEvent.click(box(pumpCases(), 'Copy S8'));
		const full = ['Pump PB off', 'Delivery tank 5 m higher', 'Copy S6', 'Copy S7', 'Copy S8'];
		expect(ticked(pumpCases())).toEqual(full);
		expect(capped(cardCases(), 'Copy S5')).toBe(false);
		// Copy S5 ticked again on the card: drawn there; the pump chart keeps its five.
		await fireEvent.click(box(cardCases(), 'Copy S5'));
		expect(box(cardCases(), 'Copy S5').checked).toBe(true);
		expect(ticked(pumpCases())).toEqual(full);
		expect(capped(pumpCases(), 'Copy S5')).toBe(true);
		expect(ws.casesUnticked).toEqual([]);
		expect(ws.pumpChartUnticked).toEqual(['S5']);
	}, 30_000);

	it('ticks a case again under “Cases on the chart” on the card too when the card has room', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await showBoth(ws);
		const rings = () =>
			[...card().querySelectorAll('[data-group-rings] li .font-medium')].map((n) => n.textContent);
		await waitFor(() => expect(rings()).toContain('Delivery tank 5 m higher'));
		await fireEvent.click(box(pumpCases(), 'Delivery tank 5 m higher'));
		// The card draws five, a place free.
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Pump PB off',
			'Both pumps off',
			'Copy S5',
			'Copy S6'
		]);
		await fireEvent.click(box(pumpCases(), 'Delivery tank 5 m higher'));
		expect(box(cardCases(), 'Delivery tank 5 m higher').checked).toBe(true);
		expect(capped(cardCases(), 'Delivery tank 5 m higher')).toBe(false);
		expect(ticked(cardCases())).toEqual([
			'Pump PA off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off',
			'Copy S5',
			'Copy S6'
		]);
		await waitFor(() => expect(rings()).toContain('Delivery tank 5 m higher'));
		expect(ws.casesUnticked).toEqual([]);
	}, 30_000);

	it('never holds a case off another pump’s chart by a tick on the card: neither one past the cap by order nor one the chart does not list', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await showBoth(ws);
		// Pump PA off unticked on the card (Pump PA's chart does not list it: PA is off in it), then
		// Copy S8, never unticked, ticked on the card into its place. Pump PA's chart is full and
		// lists Copy S8 past its cap by order.
		await fireEvent.click(box(cardCases(), 'Pump PA off'));
		await fireEvent.click(box(cardCases(), 'Copy S8'));
		expect(capped(pumpCases(), 'Copy S8')).toBe(true);
		expect(ws.pumpChartUnticked).toEqual([]);
		// Pump PB, off in Pump PB off and Both pumps off: room for Copy S8.
		await showPump('PB', 'Pump PB');
		expect(ticked(pumpCases())).toEqual([
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Copy S7',
			'Copy S8'
		]);
		// Pump PA off ticked again on the card while Pump PA's chart, full, does not list it: Pump
		// PB's chart draws it first.
		await showPump('PA', 'Pump PA');
		await fireEvent.click(box(cardCases(), 'Copy S8'));
		await fireEvent.click(box(cardCases(), 'Pump PA off'));
		expect(ws.casesUnticked).toEqual(['S8']);
		expect(ws.pumpChartUnticked).toEqual([]);
		await showPump('PB', 'Pump PB');
		expect(ticked(pumpCases())).toEqual([
			'Pump PA off',
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Copy S7'
		]);
	}, 30_000);

	it('forgets the cases’ choice when another project is loaded: page state, as a reload would', async () => {
		const { ws } = setup(withCopies(['S5', 'S6', 'S7', 'S8']));
		await showBoth(ws);
		await fireEvent.click(box(pumpCases(), 'Copy S5'));
		expect([ws.casesUnticked, ws.pumpChartUnticked, ws.pumpGroupUnticked]).toEqual([
			['S5'],
			['S8'],
			['S7', 'S8']
		]);
		// A choice under "Cases on this chart" too: the card's cases are a set the user chose.
		await fireEvent.click(box(cardCases(), 'Copy S6'));
		expect(box(cardCases(), 'Copy S6').checked).toBe(false);
		// Another project with Copy S5, S6 and S8 (scenario ids recur across projects).
		const other = withCopies(['S5', 'S6', 'S8']);
		ws.store.load({
			...other,
			id: 'another-project',
			metadata: { ...other.metadata, name: 'Another project' }
		});
		expect([ws.casesUnticked, ws.pumpChartUnticked, ws.pumpGroupUnticked]).toEqual([[], [], []]);
		await showBoth(ws);
		// Pump PA's chart has exactly five boxes: each ticked, Copy S8 among them.
		expect(ticked(pumpCases())).toEqual([
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Copy S8'
		]);
		expect(box(cardCases(), 'Copy S5').checked).toBe(true);
		// The card's set is no longer one the user chose (S8 second check CHOICE-2): an untick on
		// the pump chart with the card closed leaves the card nothing of its own.
		await fireEvent.click(cardToggle());
		expect(ws.pumpGroupOpen).toBe(false);
		await fireEvent.click(box(pumpCases(), 'Copy S5'));
		expect(ws.casesUnticked).toEqual(['S5']);
		expect(ws.pumpGroupUnticked).toEqual([]);
	}, 30_000);
});

// Case numbers (owner, 2026-11-12, nit 5: "I don't like the use of special characters to
// designate pumps and groups"; Q1 "Shapes go too", Q2 "By list place"; docs/proposals/pumps-nits.md
// item 5, slice 5b): one number per case for the whole Pumps tab, "Base", then 1 to n by the
// scenario's place in the Scenarios list, in a small box (CaseTag) in every list, ring list, table
// and heading, the same on both charts. Ticks, unticks, solves, a member change, the case shown and
// the pump shown move none; every list runs in that order (Running combinations the case shown
// first), D24's lineup priority choosing only what the group chart draws and its cap. These replace
// the S8 tests MARK-1/2/3 and the five-case boundary (the five hollow markers, fixed by place among
// at most five), never loosened: numbers never run out.
describe('case numbers on both charts (nit 5, slice 5b)', () => {
	/** The case number an element shows: its CaseTag's box, seen and hidden from screen readers. */
	function shownTag(el: Element): string | null {
		const tag = el.querySelector('[data-case-tag]');
		if (!tag) return null;
		const box =
			tag.getAttribute('aria-hidden') === 'true' ? tag : tag.querySelector('[aria-hidden="true"]');
		return box ? box.textContent!.replace(/\s+/g, ' ').trim() : null;
	}
	/** Its words beside the tag: its text without the CaseTag. */
	function besideTag(el: Element): string {
		const copy = el.cloneNode(true) as Element;
		for (const tag of copy.querySelectorAll('[data-case-tag]')) tag.remove();
		return copy.textContent!.replace(/\s+/g, ' ').trim();
	}
	/** What a screen reader reads of it: its text without the aria-hidden parts. */
	function spoken(el: Element): string {
		const copy = el.cloneNode(true) as Element;
		for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
		return copy.textContent!.replace(/\s+/g, ' ').trim();
	}
	const pumpCases = () => results().getByRole('group', { name: 'Cases on the chart' });
	const cardCases = () => within(card()).getByRole('group', { name: 'Cases on this chart' });
	/** A list's boxes in order: each label's words and the number beside them. */
	/** A case's words and the number shown beside them. */
	type Tagged = [string, string | null];
	const listed = (group: HTMLElement) =>
		within(group)
			.getAllByRole('checkbox')
			.map((b): Tagged => {
				const label = b.closest('label')!;
				return [besideTag(label), shownTag(label)];
			});
	/** The case shown at a list's head: its words and its number. */
	const shownOf = (group: HTMLElement) => {
		const tags = [...group.querySelectorAll('*')].filter(
			(el) => !el.closest('label') && /\(shown\)$/.test(besideTag(el))
		);
		const el = tags.at(-1)!;
		return [besideTag(el), shownTag(el)] as Tagged;
	};
	/** The ring list: each ring's case name and number, in its order. */
	const ringList = () =>
		[...card().querySelectorAll('[data-group-rings] li')].map((li): Tagged => [
			besideTag(li).split(',')[0]!,
			shownTag(li)
		]);
	/** A table's row headers: each case's words and number. */
	const rowHeads = (table: HTMLElement) =>
		within(table)
			.getAllByRole('rowheader')
			.map((th): Tagged => [besideTag(th), shownTag(th)]);
	/** Running combinations' case headings: each heading's first line and its number. */
	const headings = () =>
		[
			...within(card())
				.getByRole('table', { name: 'Running combinations' })
				.querySelectorAll('th[scope="rowgroup"]')
		].map((th): Tagged => {
			const first = [...th.children].find((c) => !c.matches('[data-case-tag]') && besideTag(c))!;
			return [besideTag(first), shownTag(th)];
		});
	const curvesBox = () =>
		results().getByRole('checkbox', { name: "Also show the other cases' system curves" });
	const systemCurve: Solver['systemCurve'] = async (_project, pumpId) =>
		systemCurveResponse(pumpId);
	/** Solve every case, show the Pumps view, open the card with its other cases on. */
	async function showBoth(ws: ReturnType<typeof setup>['ws']) {
		await ws.store.solveAll();
		ws.pumpGroupOthers = true;
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() =>
			expect(within(cardCases()).getAllByRole('checkbox').length).toBeGreaterThan(0)
		);
	}
	/** The one-off's four cases by name, each its number (S1 to S4 in its Scenarios list). */
	const FOUR: Tagged[] = [
		['Pump PA off', '1'],
		['Pump PB off', '2'],
		['Delivery tank 5 m higher', '3'],
		['Both pumps off', '4']
	];

	it('gives "Both pumps off" one number, 4, in both lists, the ring list and both data tables (today × on one chart and ring 2 on the other)', async () => {
		const { ws } = setup(structuredClone(oneOff.project), { systemCurve });
		await showBoth(ws);
		// The other cases' system curves on: Pump PA's chart lists all four.
		await waitFor(() => expect(curvesBox()).toBeEnabled());
		await fireEvent.click(curvesBox());
		await waitFor(() => expect(within(pumpCases()).getAllByRole('checkbox')).toHaveLength(4));
		await waitFor(() => expect(ringList()).toHaveLength(4));
		// Its checkbox's name under either list: its number's words, then the words seen (WCAG
		// 2.5.3, the visible box itself hidden from screen readers).
		for (const group of [pumpCases(), cardCases()]) {
			expect(within(group).getByRole('checkbox', { name: 'Case 4: Both pumps off' })).toBeTruthy();
		}
		expect(listed(pumpCases())).toEqual(FOUR);
		expect(listed(cardCases())).toEqual(FOUR);
		// The case shown heads both lists, its tag "Base".
		expect(shownOf(pumpCases())).toEqual(['Base case (shown)', 'Base']);
		expect(shownOf(cardCases())).toEqual(['Base case (shown)', 'Base']);
		// The ring list, in number order, each line heard as its entry in the image's sentence.
		expect(ringList()).toEqual(FOUR);
		const both = [...card().querySelectorAll('[data-group-rings] li')].find((li) =>
			besideTag(li).startsWith('Both pumps off,')
		)!;
		expect(spoken(both)).toMatch(/^Case 4: Both pumps off, 0 L\/s at a rise of 19 m: /);
		// Both data tables: the pump chart's "Operating points by case" (the case shown first) and
		// the group chart's "Other cases' station duties".
		await fireEvent.click(
			results().getByRole('button', { name: 'Show data table of the pump chart' })
		);
		await fireEvent.click(
			within(card()).getByRole('button', { name: 'Show data table of the group chart' })
		);
		const points = results().getByRole('table', { name: 'Operating points by case' });
		expect(rowHeads(points)).toEqual([['Base case (shown)', 'Base'], ...FOUR]);
		expect(within(points).getByRole('rowheader', { name: 'Case 4: Both pumps off' })).toBeTruthy();
		const duties = within(card()).getByRole('table', { name: "Other cases' station duties" });
		expect(rowHeads(duties)).toEqual(FOUR);
		expect(within(duties).getByRole('rowheader', { name: 'Case 4: Both pumps off' })).toBeTruthy();
	}, 30_000);

	it('keeps every other case’s number when case 1 is unticked: no ring renumbered (today ++number renumbers)', async () => {
		const { ws } = setup(structuredClone(oneOff.project));
		await showBoth(ws);
		await waitFor(() => expect(ringList()).toHaveLength(4));
		await fireEvent.click(within(cardCases()).getByRole('checkbox', { name: /Pump PA off$/ }));
		await waitFor(() => expect(ringList()).toHaveLength(3));
		expect(ringList()).toEqual(FOUR.slice(1));
		// Unticked, case 1 keeps its number in the list; every other case keeps its own.
		expect(listed(cardCases())).toEqual(FOUR);
		expect(
			within(cardCases()).getByRole('checkbox', { name: 'Case 1: Pump PA off' })
		).not.toBeChecked();
		// Running combinations: the case shown first, then every case in number order, each its tag.
		expect(headings()).toEqual([['Base case (shown)', 'Base'], ...FOUR]);
		// The group chart's data table too, the unticked case with its number and its reason.
		await fireEvent.click(
			within(card()).getByRole('button', { name: 'Show data table of the group chart' })
		);
		const duties = within(card()).getByRole('table', { name: "Other cases' station duties" });
		expect(rowHeads(duties)).toEqual(FOUR);
	}, 30_000);

	it('lists every case in number order; the lineup priority chooses only what the group chart draws and its cap', async () => {
		// The Scenarios list: the tank first, three copies of the base, then the lineups. Numbered
		// by that place: the tank 1, the copies 2 to 4, Pump PA off 5, Pump PB off 6, both off 7.
		// D24's priority draws the lineups first (S1, S4, S2), then the rest (S3, S5, S6): Copy S7,
		// number 4, is past the cap of six.
		const project = structuredClone(oneOff.project);
		const byId = (id: string) => scenariosOf(project).find((s) => s.id === id)!;
		const copy = (id: string) => ({ id, name: `Copy ${id}`, overrides: [] });
		const { ws } = setup(
			withScenarios(project, [
				byId('S3'),
				copy('S5'),
				copy('S6'),
				copy('S7'),
				byId('S1'),
				byId('S2'),
				byId('S4')
			])
		);
		await showBoth(ws);
		const seven: Tagged[] = [
			['Delivery tank 5 m higher', '1'],
			['Copy S5', '2'],
			['Copy S6', '3'],
			['Copy S7', '4'],
			['Pump PA off', '5'],
			['Pump PB off', '6'],
			['Both pumps off', '7']
		];
		await waitFor(() => expect(listed(cardCases())).toEqual(seven));
		const box = (name: string) =>
			within(cardCases()).getByRole('checkbox', { name: new RegExp(`${name}$`) });
		expect(
			within(cardCases())
				.getAllByRole('checkbox')
				.filter((b) => (b as HTMLInputElement).checked)
				.map((b) => besideTag(b.closest('label')!))
		).toEqual([
			'Delivery tank 5 m higher',
			'Copy S5',
			'Copy S6',
			'Pump PA off',
			'Pump PB off',
			'Both pumps off'
		]);
		expect(box('Copy S7')).toHaveAttribute('aria-disabled', 'true');
		await waitFor(() => expect(ringList()).toHaveLength(6));
		expect(ringList()).toEqual(seven.filter(([name]) => name !== 'Copy S7'));
		// Running combinations: the case shown first, then every case in number order.
		expect(headings()).toEqual([['Base case (shown)', 'Base'], ...seven]);
		// Pump PA's chart: its cases in number order, those in which it is off named by number
		// under the list (they take no slot while the other cases' system curves are off).
		expect(listed(pumpCases())).toEqual(
			seven.filter(([name]) => name !== 'Pump PA off' && name !== 'Both pumps off')
		);
		expect(
			within(pumpCases()).getByText(/^Off in this case \(no operating point\):/)
		).toHaveTextContent(
			'Off in this case (no operating point): case 5: Pump PA off; case 7: Both pumps off.'
		);
	}, 30_000);

	it('moves no number on a tick, an untick, a solve, a member change, the case shown or the pump shown', async () => {
		const { ws } = setup(structuredClone(oneOff.project), { systemCurve });
		await showBoth(ws);
		await waitFor(() => expect(curvesBox()).toBeEnabled());
		await fireEvent.click(curvesBox());
		await waitFor(() => expect(within(pumpCases()).getAllByRole('checkbox')).toHaveLength(4));
		// Every other case's station duty in before the steps: an untick of a case whose request
		// still waits cancels it (the user's), and it would then not be computed for the case shown
		// later (tickChoice, as before slice 5b).
		await waitFor(() => expect(ringList()).toHaveLength(4));
		/** Each case's number under both lists, by name, the case shown included. */
		const numbers = () => {
			const read = (group: HTMLElement): Tagged[] => [...listed(group), shownOf(group)];
			return {
				pump: Object.fromEntries(read(pumpCases())),
				card: Object.fromEntries(read(cardCases()))
			};
		};
		const base = Object.fromEntries([...FOUR, ['Base case (shown)', 'Base'] as Tagged]);
		const expected = { pump: base, card: base };
		expect(numbers()).toEqual(expected);
		// An untick and a tick, under either list.
		await fireEvent.click(within(pumpCases()).getByRole('checkbox', { name: /Pump PB off$/ }));
		expect(numbers()).toEqual(expected);
		await fireEvent.click(within(pumpCases()).getByRole('checkbox', { name: /Pump PB off$/ }));
		expect(numbers()).toEqual(expected);
		await fireEvent.click(
			within(cardCases()).getByRole('checkbox', { name: /Delivery tank 5 m higher$/ })
		);
		expect(numbers()).toEqual(expected);
		await fireEvent.click(
			within(cardCases()).getByRole('checkbox', { name: /Delivery tank 5 m higher$/ })
		);
		expect(numbers()).toEqual(expected);
		// A solve of the case shown (the card's list is drawn again once its curves answer).
		await ws.solve();
		await waitFor(() => expect(within(pumpCases()).getAllByRole('checkbox')).toHaveLength(4));
		await waitFor(() =>
			expect(within(card()).queryByRole('group', { name: 'Cases on this chart' })).not.toBeNull()
		);
		await waitFor(() => expect(within(cardCases()).getAllByRole('checkbox')).toHaveLength(4));
		expect(numbers()).toEqual(expected);
		// A member change and back: the card's members, Pump PB off the group (one pump: no other
		// cases on the card then) and on again.
		const member = () =>
			within(within(card()).getByRole('group', { name: 'Pumps in the group' })).getByRole(
				'checkbox',
				{ name: /Pump PB/ }
			);
		await fireEvent.click(member());
		expect(Object.fromEntries([...listed(pumpCases()), shownOf(pumpCases())])).toEqual(base);
		await fireEvent.click(member());
		await waitFor(() => expect(within(cardCases()).getAllByRole('checkbox')).toHaveLength(4));
		expect(numbers()).toEqual(expected);
		// Another case shown: Pump PB off (2) heads both lists; the base case is another case.
		ws.setCase('S2');
		await waitFor(() => expect(shownOf(pumpCases())).toEqual(['Pump PB off (shown)', '2']));
		await waitFor(() => expect(shownOf(cardCases())).toEqual(['Pump PB off (shown)', '2']));
		await waitFor(() =>
			expect(Object.fromEntries(listed(pumpCases()))).toEqual({
				'Base case': 'Base',
				'Pump PA off': '1',
				'Delivery tank 5 m higher': '3',
				'Both pumps off': '4'
			})
		);
		expect(Object.fromEntries(listed(cardCases()))).toEqual({
			'Base case': 'Base',
			'Pump PA off': '1',
			'Delivery tank 5 m higher': '3',
			'Both pumps off': '4'
		});
		ws.setCase(null);
		await waitFor(() => expect(numbers()).toEqual(expected));
		// Another pump shown: Pump PB's chart, the same numbers.
		await fireEvent.change(results().getByRole('combobox', { name: 'Pump chart' }), {
			target: { value: 'PB' }
		});
		await waitFor(() =>
			expect(
				results().getByRole('figure', { name: /^Pump and system curves: Pump PB/ })
			).toBeTruthy()
		);
		await waitFor(() => expect(within(pumpCases()).getAllByRole('checkbox')).toHaveLength(4));
		expect(numbers()).toEqual(expected);
	}, 60_000);

	it('draws no character for a case in either list, the ring list or either data table (the guard, extended)', async () => {
		const { ws } = setup(structuredClone(oneOff.project), { systemCurve });
		await showBoth(ws);
		await waitFor(() => expect(curvesBox()).toBeEnabled());
		await fireEvent.click(curvesBox());
		await waitFor(() => expect(ringList()).toHaveLength(4));
		await fireEvent.click(
			results().getByRole('button', { name: 'Show data table of the pump chart' })
		);
		await fireEvent.click(
			within(card()).getByRole('button', { name: 'Show data table of the group chart' })
		);
		const places: [string, Element][] = [
			['Cases on the chart', pumpCases()],
			['Cases on this chart', cardCases()],
			['the ring list', card().querySelector('[data-group-rings]')!],
			[
				'Operating points by case',
				results().getByRole('table', { name: 'Operating points by case' })
			],
			[
				"Other cases' station duties",
				within(card()).getByRole('table', { name: "Other cases' station duties" })
			]
		];
		for (const [name, el] of places) expect(designators(el), name).toEqual([]);
		// Each place shows its cases' numbers instead.
		for (const [name, el] of places)
			expect(el.querySelector('[data-case-tag]'), name).not.toBeNull();
	}, 30_000);
});
