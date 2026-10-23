/**
 * The results pane says what state its values are in, wherever they are shown: out of date,
 * kept after a failed solve, not converged, or about an element deleted since. Also: focus and
 * inert content around the trace view, the flags list on long solves, the Results tab marker,
 * flag text in names and display units, and the notes under the tables. The solve results are
 * made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NetworkError, TopologyError } from '$lib/api/client';
import type { Flag, Project, SolveResponse, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, link, pumpResult, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace, type TestWorkspaceOptions } from '$lib/testing/workspace';
import { gravityBranchExample, pumpTransferExample } from '$lib/utils/examples';
import { IMPERIAL_UNITS } from '$lib/utils/units';

const IN = 0.0254;
const GPM = (231 * IN ** 3) / 60;
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

const results = () => within(screen.getByRole('region', { name: 'Results' }));

/** Wide screens (≥ 1024 px): the trace is a side panel. Narrow: a dialog. */
function screenWidth(wide: boolean) {
	vi.stubGlobal('matchMedia', (query: string) => ({
		matches: wide,
		media: query,
		onchange: null,
		addEventListener() {},
		removeEventListener() {},
		addListener() {},
		removeListener() {},
		dispatchEvent: () => false
	}));
}

async function solveWith(
	answer: SolvedState | SolveResponse,
	project: Project = pumpTransferExample(),
	options: TestWorkspaceOptions = {}
) {
	const res = 'solvedState' in answer ? answer : response(answer);
	const solve = vi.fn(() => Promise.resolve(res));
	const ws = testWorkspace(project, { solver: { solve }, ...options });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
	await results().findByRole('heading', { name: /^(Converged|Did not converge)$/ });
	return { ws, solve };
}

async function openTrace(view: string, name: RegExp) {
	await fireEvent.click(results().getByRole('tab', { name: view }));
	await fireEvent.click(results().getByRole('button', { name }));
}

/** The nearest ancestor (or self) that is inert. Svelte sets the `inert` property. */
function inertAncestor(element: Element | null): Element | null {
	for (let e = element; e; e = e.parentElement) {
		if ((e as HTMLElement & { inert?: boolean }).inert || e.hasAttribute('inert')) return e;
	}
	return null;
}

const notConverged: Flag = flag({
	code: 'NOT_CONVERGED',
	severity: 'invalid',
	message: 'the solve did not converge: made-up reason'
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('trace side panel (wide screens)', () => {
	it('says its values are out of date after an edit, and solves again from there', async () => {
		screenWidth(true);
		const { ws, solve } = await solveWith(pumpTransferSolved());
		await openTrace('Links', /^Suction tank → Transfer pump/);
		const panel = await screen.findByRole('region', { name: 'Suction tank → Transfer pump' });
		expect(within(panel).queryByText(/out of date/)).toBeNull();

		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		expect(await within(panel).findByText(/Results are out of date/)).toBeInTheDocument();
		expect(panel).toHaveTextContent(/These values are from before the change/);
		await fireEvent.click(within(panel).getByRole('button', { name: 'Solve again' }));
		expect(solve).toHaveBeenCalledTimes(2);
		await vi.waitFor(() => expect(within(panel).queryByText(/out of date/)).toBeNull());
	});

	it('says a solve that did not converge is not a solution, with the network-wide flag', async () => {
		screenWidth(true);
		await solveWith(pumpTransferSolved({ converged: false, flags: [notConverged] }));
		await openTrace('Pumps', /^Transfer pump/);
		const panel = await screen.findByRole('region', { name: 'Transfer pump' });
		expect(panel).toHaveTextContent(/This solve did not converge/);
		expect(panel).toHaveTextContent(/not a solution of the network\. Do not use them\./);
		expect(within(panel).getByText('About the whole network:')).toBeInTheDocument();
		expect(panel).toHaveTextContent(/The solve did not converge: made-up reason/);
	});

	it('makes the results under it inert, and is a region (not a nested complementary)', async () => {
		screenWidth(true);
		await solveWith(pumpTransferSolved());
		expect(inertAncestor(results().getByRole('tablist', { name: 'Results view' }))).toBeNull();
		await openTrace('Links', /^Suction tank → Transfer pump/);
		const panel = await screen.findByRole('region', { name: 'Suction tank → Transfer pump' });
		expect(screen.queryByRole('complementary')).toBeNull();
		expect(document.activeElement).toBe(within(panel).getByRole('heading', { level: 2 }));
		const tabs = screen.getByRole('tablist', { name: 'Results view', hidden: true });
		expect(inertAncestor(tabs)).not.toBeNull();
		expect(inertAncestor(screen.getByText(/^Last solve:/))).not.toBeNull();
		expect(inertAncestor(panel)).toBeNull();

		await fireEvent.click(within(panel).getByRole('button', { name: 'Close' }));
		expect(inertAncestor(tabs)).toBeNull();
	});

	it('says when the element was deleted after the solve', async () => {
		screenWidth(true);
		const { ws } = await solveWith(pumpTransferSolved());
		await openTrace('Valves', /^Discharge isolation valve/);
		await screen.findByRole('region', { name: 'Discharge isolation valve' });
		expect(ws.remove('V1', true)).toBe(true);
		const panel = await screen.findByRole('region', { name: 'V1' });
		expect(panel).toHaveTextContent(
			/V1 is no longer in the project: it was deleted after this solve/
		);
		expect(panel).toHaveTextContent(/Component · V1 · deleted/);
		expect(within(panel).queryByRole('button', { name: 'Show in Build' })).toBeNull();
	});
});

describe('trace dialog (narrow screens)', () => {
	it('says a solve that did not converge is not a solution', async () => {
		screenWidth(false);
		await solveWith(pumpTransferSolved({ converged: false, flags: [notConverged] }));
		await openTrace('Links', /^Suction tank → Transfer pump/);
		const dialog = await screen.findByRole('dialog', { name: 'Suction tank → Transfer pump' });
		expect(dialog).toHaveTextContent(/This solve did not converge/);
		expect(dialog).toHaveTextContent(/Do not use them/);
	});

	it('Show in Build moves focus to the component in Build', async () => {
		screenWidth(false);
		const { ws } = await solveWith(pumpTransferSolved());
		ws.pane = 'results';
		await openTrace('Pumps', /^Transfer pump/);
		const dialog = await screen.findByRole('dialog', { name: 'Transfer pump' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Show in Build' }));
		await tick();
		await vi.waitFor(() =>
			expect(document.activeElement).toBe(
				within(screen.getByRole('region', { name: 'Build' })).getByRole('heading', {
					level: 2,
					name: 'Transfer pump'
				})
			)
		);
		expect(ws.pane).toBe('build');
	});
});

describe('results state', () => {
	it('stays current after a change of display units', async () => {
		const { ws } = await solveWith(pumpTransferSolved());
		ws.store.update((p) => {
			p.settings.units = { ...IMPERIAL_UNITS };
		}, 'use US units');
		await tick();
		expect(results().queryByText(/Results are out of date/)).toBeNull();
		expect(results().getByRole('status')).toHaveTextContent('Last solve: converged');
	});

	it('after a failed solve of the same project, says the results are from the previous solve', async () => {
		let calls = 0;
		const solve = vi.fn(() =>
			++calls === 1
				? Promise.resolve(response(pumpTransferSolved()))
				: Promise.reject(new NetworkError('The calculation server could not be reached.', 0))
		);
		const ws = testWorkspace(pumpTransferExample(), { solver: { solve } });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		expect(await results().findByText(/could not be reached/)).toBeInTheDocument();
		expect(results().queryByText(/the project changed after this solve/)).toBeNull();
		expect(
			results().getByText(
				/The last solve failed\. The results below are from the previous solve of this same project\./
			)
		).toBeInTheDocument();
	});

	it('after an edit and a failed solve: the error first, and the earlier results only on request', async () => {
		let calls = 0;
		const solve = vi.fn(() =>
			++calls === 1
				? Promise.resolve(response(pumpTransferSolved()))
				: Promise.reject(
						new TopologyError('The network cannot be solved: 1 topology issue(s).', [
							{
								code: 'UNCONNECTED_PORT',
								message: "port 'V1:outlet' is not connected; connect it or add a plug",
								componentIds: ['V1'],
								connectionIds: []
							}
						])
					)
		);
		const ws = testWorkspace(pumpTransferExample(), { solver: { solve } });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		expect(ws.remove('R2', false)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));

		const error = await results().findByRole('region', {
			name: 'The network cannot be solved yet'
		});
		const notice = results().getByText(
			'The last solve failed (see above). The results below are from an earlier version of the project, before your last changes.'
		);
		// The error comes first; nothing says the project changed after this solve.
		expect(error.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(results().queryByText(/the project changed after this solve/)).toBeNull();
		expect(results().queryByRole('button', { name: 'Solve again' })).toBeNull();
		expect(results().getByRole('status')).toHaveTextContent(/^Last solve: no results$/);
		// The earlier results are not shown as if current.
		expect(results().queryByRole('heading', { name: 'Converged' })).toBeNull();
		expect(results().queryByRole('tablist', { name: 'Results view' })).toBeNull();

		await fireEvent.click(results().getByRole('button', { name: 'Show the earlier results' }));
		expect(results().getByRole('heading', { name: 'Converged' })).toBeInTheDocument();
		expect(results().getByRole('tablist', { name: 'Results view' })).toBeInTheDocument();

		// Another edit: the error is now about an earlier version too.
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 77;
		}, 'change length');
		expect(
			await results().findByText(/Results are out of date: the project changed after this solve/)
		).toBeInTheDocument();
		expect(results().getByRole('status')).toHaveTextContent('Last solve: no results, out of date');
	});

	it('marks the Results tab when results are out of date or physically invalid', async () => {
		const { ws } = await solveWith(
			pumpTransferSolved({
				flags: [
					flag({ code: 'CAVITATION', severity: 'invalid', message: 'made-up', componentId: 'P1' })
				]
			})
		);
		const tab = () => screen.getByRole('tab', { name: /^Results/ });
		expect(tab()).toHaveAccessibleName('Results (1 physically invalid)');
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		await tick();
		expect(tab()).toHaveAccessibleName('Results (1 physically invalid, out of date)');
	});

	it('copies the methods of a solve that did not converge with that said', async () => {
		const writeText = vi.fn(() => Promise.resolve());
		vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
		await solveWith(pumpTransferSolved({ converged: false }));
		await fireEvent.click(results().getByRole('tab', { name: 'Methods' }));
		expect(results().getByText(/This solve did not converge: its values are not a solution/));
		await fireEvent.click(results().getByRole('button', { name: 'Copy as text' }));
		await vi.waitFor(() => expect(writeText).toHaveBeenCalled());
		const text = (writeText.mock.calls[0] as unknown as [string])[0];
		expect(text).toContain('Solve status: DID NOT CONVERGE.');
	});
});

describe('flags list', () => {
	const many = Array.from({ length: 8 }, (_, i) =>
		flag({
			code: 'TRANSITIONAL_FLOW',
			severity: 'warning',
			message: `Made-up warning ${i + 1}`,
			connectionId: 'L2'
		})
	);

	it('shows the first five of a long group, all on request, and can be skipped', async () => {
		await solveWith(pumpTransferSolved({ flags: many }));
		const list = results().getByRole('list', { name: 'Warnings (8)' });
		expect(within(list).getAllByRole('listitem')).toHaveLength(5);
		const more = results().getByRole('button', { name: 'Show all 8 warnings' });
		expect(more).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(more);
		expect(within(list).getAllByRole('listitem')).toHaveLength(8);
		expect(more).toHaveAttribute('aria-expanded', 'true');

		await fireEvent.click(results().getByRole('button', { name: 'Skip to the results views' }));
		expect(document.activeElement).toBe(results().getByRole('tab', { name: 'Summary' }));
	});

	it('leads with the element and reads in names and display units', async () => {
		const project = pumpTransferExample();
		project.settings.units = { ...IMPERIAL_UNITS };
		await solveWith(
			pumpTransferSolved({
				flags: [
					flag({
						code: 'PUMP_OUTSIDE_CURVE',
						severity: 'warning',
						message: "pump 'P1' operates at 0.0475089 m³/s, outside its curve's flow range",
						componentId: 'P1',
						details: { flow: 0.0475089, speed: 1, curve: 'head' }
					})
				]
			}),
			project
		);
		const list = results().getByRole('list', { name: 'Warnings (1)' });
		const item = within(list).getByRole('listitem');
		const button = within(item).getByRole('button', {
			name: /^Show Transfer pump: It operates at/
		});
		expect(button.firstElementChild).toHaveTextContent(/^Transfer pump$/);
		expect(item).toHaveTextContent(`It operates at ${sig4(0.0475089 / GPM)} gpm`);
		expect(item).not.toHaveTextContent(/m³\/s|'P1'/);
	});
});

describe('convergence report', () => {
	it('lists each place on its own line with a full-size link', async () => {
		await solveWith(
			pumpTransferSolved({
				converged: false,
				convergence: {
					innerIterations: 100,
					outerIterations: 30,
					message: 'Status iterations did not settle',
					oscillatingComponents: ['V1', 'P1'],
					maxContinuityResidual: { value: 0.001, elementId: 'P1:suction' },
					maxEnergyResidual: { value: 0.02, elementId: 'L3' }
				}
			})
		);
		const report = within(results().getByRole('region', { name: 'Did not converge' }));
		for (const name of [
			'Suction of Transfer pump',
			'Discharge isolation valve → Discharge tank',
			'Discharge isolation valve',
			'Transfer pump'
		]) {
			const button = report.getByRole('button', { name });
			expect(button).toHaveClass('min-h-11', 'inline-flex', 'text-left');
		}
		const switching = results()
			.getByText(/Kept switching state/)
			.closest('li')!;
		expect(within(switching).getAllByRole('listitem')).toHaveLength(2);
	});

	it('does not repeat the iteration counts of a converged solve', async () => {
		await solveWith(pumpTransferSolved());
		expect(results().getByText(/6 iterations \(1 outer\)/)).toBeInTheDocument();
		expect(results().queryByText(/Newton iterations in 1 outer iteration/)).toBeNull();
	});
});

describe('notes and tables', () => {
	it('states the valve flow direction and the node velocity at boundaries', async () => {
		await solveWith(pumpTransferSolved());
		await fireEvent.click(results().getByRole('tab', { name: 'Valves' }));
		const valves = results().getByRole('tabpanel', { name: 'Valves' });
		expect(valves).toHaveTextContent(/Flow is positive from the valve's inlet to its outlet/);
		expect(
			within(valves).getByRole('columnheader', { name: 'Flow (+ inlet → outlet) L/s' })
		).toBeInTheDocument();
		await fireEvent.click(results().getByRole('tab', { name: 'Nodes' }));
		expect(results().getByRole('tabpanel', { name: 'Nodes' })).toHaveTextContent(
			/except at reservoir and reference-node ports, which show the boundary's still liquid: velocity 0, and HGL equal to EGL/
		);
		// The visited view stays rendered (hidden) for a quick switch back.
		const valvesTab = results().getByRole('tab', { name: 'Valves' });
		const kept = document.getElementById(valvesTab.getAttribute('aria-controls') ?? '');
		expect(kept).toBe(valves);
		expect(kept).not.toBeVisible();
	});

	it('explains the velocity each branch K is on, for the models in the solve', async () => {
		await solveWith(
			pumpTransferSolved({
				branchResults: {
					T1: {
						branchType: 'tee',
						lossModel: 'crane',
						pattern: 'diverging from branch',
						combinedPortId: 'branch',
						portFlows: { run_inlet: -0.017, run_outlet: -0.018, branch: 0.035 },
						kFactors: { run_inlet: 1.088, run_outlet: 1.088 },
						pathHeadLosses: { run_inlet: 0.719, run_outlet: 0.76 },
						referenceVelocity: 4.233,
						correlation: 'Made-up Darby text',
						inCorrelationRange: false
					}
				},
				flags: [
					flag({
						code: 'TEE_PATTERN_FALLBACK',
						severity: 'warning',
						message: 'made-up',
						componentId: 'T1'
					})
				]
			}),
			gravityBranchExample()
		);
		await fireEvent.click(results().getByRole('tab', { name: 'Branches' }));
		const panel = results().getByRole('tabpanel', { name: 'Branches' });
		expect(panel).toHaveTextContent(/each run path's K is on that leg's own velocity/);
		expect(panel).not.toHaveTextContent(/every K is on the combined-flow velocity/);
		expect(
			within(panel).getByRole('columnheader', { name: 'Velocity K is on m/s' })
		).toBeInTheDocument();
	});

	it('shows a pipe’s flag on that pipe when a connection is expanded', async () => {
		const solved = pumpTransferSolved({
			linkResults: {
				...pumpTransferSolved().linkResults,
				L1: link({
					segments: [0, 1].map((index) => ({
						index,
						innerDiameter: 0.1,
						length: 5,
						roughness: 4.6e-5,
						velocity: 2,
						reynoldsNumber: index ? 2909 : 1493,
						frictionFactor: 0.04,
						flowRegime: index ? ('transitional' as const) : ('laminar' as const),
						headLoss: 0.1
					}))
				})
			},
			flags: [
				flag({
					code: 'TRANSITIONAL_FLOW',
					severity: 'warning',
					message: "connection 'L1' pipe 2: made-up",
					connectionId: 'L1',
					details: { segmentIndex: 1, reynoldsNumber: 2909 }
				})
			]
		});
		await solveWith(solved);
		await fireEvent.click(results().getByRole('tab', { name: 'Links' }));
		await fireEvent.click(
			results().getByRole('button', { name: 'Pipes and fittings: Suction tank → Transfer pump' })
		);
		const pipe1 = results().getByRole('region', { name: 'Pipe 1 of Suction tank → Transfer pump' });
		const pipe2 = results().getByRole('region', { name: 'Pipe 2 of Suction tank → Transfer pump' });
		expect(within(pipe1).queryByText('Warning')).toBeNull();
		expect(within(pipe2).getByText('Warning')).toBeInTheDocument();
		expect(within(pipe2).getByText(/^: Pipe 2: Re = 2909/)).toHaveClass('sr-only');
	});

	it('shows no speed for an off pump and says its curve is for reference', async () => {
		await solveWith(
			pumpTransferSolved({
				pumpResults: { P1: pumpResult({ status: 'off', operatingFlow: 0, hydraulicPower: 0 }) }
			})
		);
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		const panel = results().getByRole('tabpanel', { name: 'Pumps' });
		expect(panel).toHaveTextContent(/This pump is off: it carries no flow/);
		expect(
			await within(panel).findByRole('region', { name: /Pump curve at its set speed \(100 %\)/ })
		).toBeInTheDocument();
		expect(within(panel).getByRole('table', { name: 'Results per pump' })).toHaveTextContent('Off');
	});
});

describe('method-version notice', () => {
	it('keeps focus in the notice when trying again, and announces the outcome', async () => {
		const project = { ...pumpTransferExample(), methodVersion: '1.0.0' };
		let fail = true;
		const methodVersions = vi.fn(() =>
			fail
				? Promise.reject(new NetworkError('Server error', 500))
				: Promise.resolve({
						current: '1.1.0',
						versions: [{ version: '1.1.0', date: '2026-11-02', changes: ['Made-up change.'] }]
					})
		);
		await solveWith(pumpTransferSolved({ methodVersion: '1.1.0' }), project, {
			library: { methodVersions }
		});
		const notice = results()
			.getByRole('heading', { name: 'Calculation methods changed' })
			.closest('section')!;
		const status = within(notice).getByRole('status');
		await vi.waitFor(() => expect(status).toHaveTextContent(/could not be loaded: Server error/));
		fail = false;
		const retry = within(notice).getByRole('button', { name: 'Try again' });
		retry.focus();
		await fireEvent.click(retry);
		expect(document.activeElement).toBe(
			within(notice).getByRole('heading', { name: 'Calculation methods changed' })
		);
		await vi.waitFor(() => expect(status).toHaveTextContent('What changed:'));
		expect(within(notice).getByText('Made-up change.')).toBeInTheDocument();
	});
});
