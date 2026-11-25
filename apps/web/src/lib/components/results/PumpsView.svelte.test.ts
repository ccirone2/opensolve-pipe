/**
 * The Pumps view's chart and the export's rule (proposal export.md §2.1, §3.4, §5.5): the other
 * cases drawn on the chart are those Compare shows (a case whose latest solve failed, that a
 * stopped run did not reach, or whose solve did not converge is not drawn), and Download image
 * says why no image can be made of results that are not a solution, of the earlier results shown
 * after a failed solve, or while a calculation runs. And the base case's system curve, asked for,
 * drawn and counted when it is the only other case the chart draws (proposals/open-defects.md
 * P1). The solved states and system curves are made-up test inputs, except the fixture's solves.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { NetworkError, TopologyError } from '$lib/api/client';
import type {
	Component,
	Project,
	PumpGroupCurveResponse,
	SolveResponse,
	SystemCurveResponse
} from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { besideCaseTag, shownCaseTag } from '$lib/testing/helpers';
import { pumpTransferSolved, response, systemCurveResponse } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { updateComponent } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { withScenarios } from '$lib/utils/scenarios';

// The chart: jsdom has no canvas. A stub context lets the chart be "drawn" (Chart.js cannot draw on
// it and says so on the console, which these tests silence); Download image then needs only the
// reasons the results give. (A mock of './chart-setup' does not reach the chart through the
// workspace in this test runner; PumpChart.svelte.test.ts mocks it for the chart itself.)
const getContext = HTMLCanvasElement.prototype.getContext;
const consoleError = console.error;
// The chart loads Chart.js on first draw (`import('./chart-setup')`). Loaded here once, so a wait
// for the drawn chart waits for the drawing, not for the test runner's first transform of
// Chart.js, which took over waitFor's second on a loaded 4-CPU machine (on main too).
beforeAll(async () => {
	await import('./chart-setup');
});
beforeEach(() => {
	console.error = (...args: unknown[]) => {
		if (String(args[0]).startsWith('Failed to create chart')) return;
		consoleError(...args);
	};
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	console.error = consoleError;
});

function setup(project: Project, solver: Solver) {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	const ws = testWorkspace(project, { solver });
	render(WorkspaceView, { workspace: ws });
	return ws;
}

const results = () => within(screen.getByRole('region', { name: 'Results' }));

async function showPumps() {
	await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
}

const imageButton = () =>
	results().getByRole('button', { name: /^Download image of the pump and system curves/ });

const notConverged = () => response(pumpTransferSolved({ converged: false }), { success: false });

describe('other cases on the pump chart (Compare’s rule)', () => {
	it('draws only cases whose last solve of the project converged', async () => {
		let stop = false;
		const ws = setup(
			withScenarios(pumpTransferExample(), [
				{ id: 'S1', name: 'Converged', overrides: [] },
				{ id: 'S2', name: 'Not converged', overrides: [] },
				{ id: 'S3', name: 'Failed', overrides: [] },
				{ id: 'S4', name: 'Not reached', overrides: [] }
			]),
			{
				solve: async (_p, _o, request) => {
					if (stop && request?.scenarioId === 'S3')
						throw new NetworkError('The server is busy.', 503, 'SERVER_BUSY');
					return request?.scenarioId === 'S2' ? notConverged() : response(pumpTransferSolved());
				}
			}
		);
		await ws.solveAll();
		// Every case out of date, then a run that stops at S3: S3 failed, S4 not reached, both
		// keeping an earlier converged response.
		ws.store.update(
			(p) => updateComponent(p, 'R1', (c) => ({ ...c, liquidLevel: 3.4 }) as Component),
			'change level'
		);
		stop = true;
		await ws.solveAll();
		await tick();
		expect(['S1', 'S2', 'S3', 'S4'].map((c) => ws.store.caseStatus(c))).toEqual([
			'solved',
			'not_converged',
			'failed',
			'not_reached'
		]);
		await showPumps();
		const cases = await results().findByRole('group', { name: 'Cases on the chart' });
		// Its case's number, its place in the Scenarios list (nit 5, slice 5b: in place of △).
		expect(
			within(cases)
				.getAllByRole('checkbox')
				.map((c) => [shownCaseTag(c.closest('label')!), besideCaseTag(c.closest('label')!)])
		).toEqual([['1', 'Converged']]);
	});
});

describe('"Cases on the chart" past its cap of five other cases', () => {
	it('keeps the place a case leaves free: the case unticked can be ticked again, or another into its place', async () => {
		const ws = setup(
			withScenarios(
				pumpTransferExample(),
				['S1', 'S2', 'S3', 'S4', 'S5', 'S6'].map((id) => ({
					id,
					name: `Case ${id}`,
					overrides: []
				}))
			),
			{ solve: async () => response(pumpTransferSolved()) }
		);
		await ws.solveAll();
		await showPumps();
		const group = await results().findByRole('group', { name: 'Cases on the chart' });
		const box = (name: string) =>
			within(group).getByRole('checkbox', { name: new RegExp(`${name}$`) }) as HTMLInputElement;
		const capped = (name: string) => box(name).getAttribute('aria-disabled') === 'true';
		const ticked = () =>
			within(group)
				.getAllByRole('checkbox')
				.filter((b) => (b as HTMLInputElement).checked)
				// Its words beside its case's number (nit 5, slice 5b: the number's box and words).
				.map((b) => besideCaseTag(b.closest('label')!));
		const five = ['Case S1', 'Case S2', 'Case S3', 'Case S4', 'Case S5'];
		expect(ticked()).toEqual(five);
		expect(capped('Case S6')).toBe(true);

		// Unticked, Case S1 leaves its place free: no case comes in by itself.
		await fireEvent.click(box('Case S1'));
		expect(ticked()).toEqual(five.slice(1));
		expect(capped('Case S1')).toBe(false);
		expect(capped('Case S6')).toBe(false);

		// Ticked again, it takes its place back, and the box past the cap is capped again.
		await fireEvent.click(box('Case S1'));
		expect(ticked()).toEqual(five);
		expect(capped('Case S6')).toBe(true);

		// Or another case is ticked into the place: then the case unticked is the one capped.
		await fireEvent.click(box('Case S1'));
		await fireEvent.click(box('Case S6'));
		expect(ticked()).toEqual([...five.slice(1), 'Case S6']);
		expect(capped('Case S1')).toBe(true);
		await fireEvent.click(box('Case S1'));
		expect(box('Case S1').checked).toBe(false);
	});
});

describe('Download image under the chart', () => {
	it('is available for a converged solve once the chart is drawn', async () => {
		setup(pumpTransferExample(), { solve: async () => response(pumpTransferSolved()) });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		await waitFor(() => expect(imageButton()).not.toHaveAttribute('aria-disabled', 'true'));
	});

	it('is unavailable for a solve that did not converge, current or out of date', async () => {
		const ws = setup(pumpTransferExample(), { solve: async () => notConverged() });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Did not converge' });
		await showPumps();
		const reason =
			'This solve did not converge: its values are not a solution, so no image is made.';
		await waitFor(() => expect(imageButton()).toHaveAccessibleDescription(reason));
		expect(imageButton()).toHaveAttribute('aria-disabled', 'true');
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		await waitFor(() => expect(ws.store.results.stale).toBe(true));
		expect(ws.store.caseStatus(null)).toBe('stale');
		expect(imageButton()).toHaveAccessibleDescription(reason);
	});

	it('is unavailable for the earlier results shown after a failed solve', async () => {
		let calls = 0;
		const ws = setup(pumpTransferExample(), {
			solve: async () => {
				if (++calls === 1) return response(pumpTransferSolved());
				throw new TopologyError('The network cannot be solved: 1 topology issue(s).', [
					{
						code: 'UNCONNECTED_PORT',
						message: "port 'V1:outlet' is not connected; connect it or add a plug",
						componentIds: ['V1'],
						connectionIds: []
					}
				]);
			}
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		expect(ws.remove('R2', false)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await fireEvent.click(
			await results().findByRole('button', { name: 'Show the earlier results' })
		);
		await showPumps();
		await waitFor(() =>
			expect(imageButton()).toHaveAccessibleDescription(
				'The latest solve failed; the chart shows results from an earlier version of the project, so no image is made.'
			)
		);
	});

	it('is unavailable while a solve runs', async () => {
		let release: (r: SolveResponse) => void = () => {};
		let calls = 0;
		const ws = setup(pumpTransferExample(), {
			solve: () =>
				++calls === 1
					? Promise.resolve(response(pumpTransferSolved()))
					: new Promise<SolveResponse>((resolve) => (release = resolve))
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		await waitFor(() => expect(imageButton()).not.toHaveAttribute('aria-disabled', 'true'));
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		void ws.solve();
		await waitFor(() =>
			expect(imageButton()).toHaveAccessibleDescription(
				'A solve is running; export when it finishes, or Cancel in the header stops it.'
			)
		);
		release(response(pumpTransferSolved()));
		await waitFor(() => expect(imageButton()).not.toHaveAttribute('aria-disabled', 'true'));
	});
});

// proposals/open-defects.md P1: the base case's key is '' (OtherCaseInput), so the overlay's
// request list must tell [''] (the base case the only other case drawn) from no case at all.
describe('the base case’s system curve on the pump chart (proposals/open-defects.md P1)', () => {
	// The data table shown is remembered in this browser (pumps-results-layout.md §9 S7): each
	// test starts from none remembered.
	afterEach(() => localStorage.clear());
	/** A request for a system curve: its case, and its flow range (an overlay's) or none. */
	interface CurveCall {
		scenarioId: string | null;
		range: [number, number] | null;
		signal: AbortSignal | undefined;
	}
	/** A made-up curve over 0 to `max` m³/s: systemCurveResponse's points, its range `max`. */
	const curveTo = (pumpId: string, max: number): SystemCurveResponse => ({
		...systemCurveResponse(pumpId),
		flowRange: { min: 0, max, unit: 'm³/s' }
	});
	/**
	 * A solver recording every system-curve request: a case's own curve over 0–0.036 m³/s (the
	 * grid the overlays are asked on), an overlay over its range, or `overlay`'s answer to it.
	 */
	function recording(
		options: {
			solve?: Solver['solve'];
			overlay?: (call: CurveCall) => Promise<SystemCurveResponse>;
		} = {}
	) {
		const calls: CurveCall[] = [];
		const solver: Solver = {
			solve: options.solve ?? (async () => response(pumpTransferSolved())),
			systemCurve: async (_p, pumpId, request) => {
				const call: CurveCall = {
					scenarioId: request?.scenarioId ?? null,
					range: request?.flowMin === undefined ? null : [request.flowMin, request.flowMax!],
					signal: request?.signal
				};
				calls.push(call);
				if (call.range && options.overlay) return options.overlay(call);
				return curveTo(pumpId, call.range ? call.range[1] : 0.036);
			}
		};
		const sent = () => calls.map(({ scenarioId, range }) => ({ scenarioId, range }));
		return { solver, calls, sent };
	}
	const overlayBox = () =>
		results().findByRole('checkbox', { name: "Also show the other cases' system curves" });
	const casesBox = async (name: RegExp) =>
		within(await results().findByRole('group', { name: 'Cases on the chart' })).getByRole(
			'checkbox',
			{ name }
		);
	const overlayLine = () => document.querySelector('[data-overlay-state]')!;
	const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
	const baseCurveTable = () => results().queryByRole('table', { name: 'System curve, Base case' });

	/** Solve every case, then show the Pumps tab on `shown`: its own curve asked for first. */
	async function showOn(ws: ReturnType<typeof setup>, shown: string, sent: () => unknown[]) {
		await ws.solveAll();
		ws.setCase(shown);
		await tick();
		await showPumps();
		await waitFor(() => expect(sent()).toEqual([{ scenarioId: shown, range: null }]));
	}

	it('one scenario shown, the box ticked: asks for the base case’s curve on the grid shown, and draws it', async () => {
		const { solver, sent } = recording();
		const ws = setup(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Higher tank', overrides: [] }]),
			solver
		);
		await showOn(ws, 'S1', sent);
		await fireEvent.click(await overlayBox());
		// The base case: no scenarioId, on the flow grid of the curve shown (S1's, 0–0.036 m³/s).
		await waitFor(() =>
			expect(sent()).toEqual([
				{ scenarioId: 'S1', range: null },
				{ scenarioId: null, range: [0, 0.036] }
			])
		);
		await fireEvent.click(
			results().getByRole('button', { name: 'Show data table of the pump chart' })
		);
		// Its table names it as the legend does ("System curve, Base case": otherCasesData's label).
		await waitFor(() => expect(baseCurveTable()).not.toBeNull());
	});

	it('two scenarios, the other unticked under "Cases on the chart": asks for the base case’s curve alone', async () => {
		const { solver, sent } = recording();
		const ws = setup(
			withScenarios(pumpTransferExample(), [
				{ id: 'S1', name: 'Higher tank', overrides: [] },
				{ id: 'S2', name: 'Slower pump', overrides: [] }
			]),
			solver
		);
		await showOn(ws, 'S1', sent);
		await fireEvent.click(await casesBox(/Slower pump$/));
		await fireEvent.click(await overlayBox());
		await waitFor(() =>
			expect(sent()).toEqual([
				{ scenarioId: 'S1', range: null },
				{ scenarioId: null, range: [0, 0.036] }
			])
		);
		await fireEvent.click(
			results().getByRole('button', { name: 'Show data table of the pump chart' })
		);
		await waitFor(() => expect(baseCurveTable()).not.toBeNull());
		expect(
			results().queryByRole('table', { name: 'System curve, case 2: Slower pump' })
		).toBeNull();
	});

	it('no other case drawn: the box ticked sends nothing; the base case ticked again is asked for', async () => {
		const { solver, sent } = recording();
		const ws = setup(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Higher tank', overrides: [] }]),
			solver
		);
		await showOn(ws, 'S1', sent);
		await fireEvent.click(await casesBox(/Base case$/));
		expect(((await casesBox(/Base case$/)) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(await overlayBox());
		await tick();
		// Nothing to wait for: a request would be on the store's queue well within this.
		await new Promise((resolve) => setTimeout(resolve, 50));
		expect(sent()).toEqual([{ scenarioId: 'S1', range: null }]);
		expect(squash(overlayLine().textContent)).toBe('');
		expect(
			results().queryByRole('button', { name: "Cancel the other cases' system curves" })
		).toBeNull();
		// The base case ticked again, the box still ticked: its curve is asked for.
		await fireEvent.click(await casesBox(/Base case$/));
		await waitFor(() =>
			expect(sent()).toEqual([
				{ scenarioId: 'S1', range: null },
				{ scenarioId: null, range: [0, 0.036] }
			])
		);
	});

	it('counts the base case’s curve in the progress line, and Cancel cancels it', async () => {
		const { solver, calls } = recording({
			overlay: (call) =>
				new Promise((_resolve, reject) => {
					// Held: answered only by its abort (as the real client, an aborted request rejects).
					call.signal?.addEventListener('abort', () =>
						reject(new DOMException('The operation was aborted.', 'AbortError'))
					);
				})
		});
		const ws = setup(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Higher tank', overrides: [] }]),
			solver
		);
		await showOn(ws, 'S1', () => calls.map(({ scenarioId, range }) => ({ scenarioId, range })));
		await fireEvent.click(await overlayBox());
		await waitFor(() =>
			expect(squash(overlayLine().textContent)).toBe('Computing system curves: 1 of 1…')
		);
		const base = calls.find((c) => c.scenarioId === null && c.range)!;
		expect(base.signal?.aborted).toBe(false);
		await fireEvent.click(
			results().getByRole('button', { name: "Cancel the other cases' system curves" })
		);
		expect(base.signal?.aborted).toBe(true);
		await waitFor(() => expect(squash(overlayLine().textContent)).toBe(''));
		expect(
			results().queryByRole('button', { name: "Cancel the other cases' system curves" })
		).toBeNull();
	});

	it('marks the pump chart in the section nav when the base case’s curve fails', async () => {
		// Two pumps (the nav is drawn) and one scenario: the fixture's real solves by scenario id.
		interface Responses {
			solve: SolveResponse;
			groupCurve: { body: unknown };
		}
		const c = (
			fixture.cases as unknown as (Responses & {
				name: string;
				project: Project;
				scenarioCases: Record<string, Responses>;
			})[]
		).find((x) => x.name === 'one-off-dead-headed')!;
		const of = (id: string | undefined): Responses => (id && c.scenarioCases[id]) || c;
		const { solver, sent } = recording({
			solve: async (_p, _o, request) => structuredClone(of(request?.scenarioId).solve),
			overlay: async () => {
				throw new NetworkError('The server is busy.', 503, 'SERVER_BUSY');
			}
		});
		solver.groupCurve = async (_p, _ids, request) =>
			structuredClone(of(request?.scenarioId).groupCurve.body as PumpGroupCurveResponse);
		const ws = setup(structuredClone(c.project), solver);
		await showOn(ws, 'S1', sent);
		const nav = within(results().getByRole('toolbar', { name: 'Go to' }));
		expect(nav.getByRole('button', { name: 'Pump chart' })).toBeInTheDocument();
		await fireEvent.click(await overlayBox());
		await waitFor(() =>
			expect(sent()).toEqual([
				{ scenarioId: 'S1', range: null },
				{ scenarioId: null, range: [0, 0.036] }
			])
		);
		await waitFor(() =>
			expect(nav.getByRole('button', { name: 'Pump chart, a request failed' })).toBeInTheDocument()
		);
	});
});
