/**
 * Results pane: Solve calls the API through the store and the pane shows what came back —
 * topology issues, validation errors, a network error or the solve status.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { TopologyError, ValidationError } from '$lib/api/client';
import type { Project, Pump, SolveResponse } from '$lib/api/types';
import { pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { gravityBranchExample, pumpTransferExample } from '$lib/utils/examples';
import { IMPERIAL_UNITS } from '$lib/utils/units';
import { withScenarios } from '$lib/utils/scenarios';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';

// The export dialog's chunk loader (utils/export/load.ts), replaced so a test sees when the
// chunk is preloaded and can make its import fail.
const exportLoader = vi.hoisted(() => ({
	load: (() => Promise.reject(new Error('not loaded in this test'))) as () => Promise<unknown>,
	preloads: 0
}));
vi.mock('$lib/utils/export/load', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/utils/export/load')>()),
	loadExportDialog: () => exportLoader.load(),
	preloadExportDialog: () => void exportLoader.preloads++
}));

function results() {
	return within(screen.getByRole('region', { name: 'Results' }));
}

async function solve() {
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
}

/** An element's text as the browser tells it: without the server's messages under Details. */
function toldText(element: HTMLElement): string {
	const copy = element.cloneNode(true) as HTMLElement;
	copy.querySelectorAll('[data-issue-detail]').forEach((detail) => detail.remove());
	return copy.textContent ?? '';
}

/** The server's message kept under an issue's Details (closed by default). */
function serverDetail(item: HTMLElement): HTMLElement {
	const detail = item.querySelector<HTMLDetailsElement>('details[data-issue-detail]');
	if (!detail) throw new Error('no Details');
	expect(detail.open).toBe(false);
	return detail;
}

describe('results pane', () => {
	it('reports topology issues and shows the components they name', async () => {
		const ws = testWorkspace(gravityBranchExample(), {
			solver: {
				solve: () =>
					Promise.reject(
						new TopologyError('The network cannot be solved.', [
							{
								code: 'NO_BOUNDARY',
								message: 'This part of the network has no fixed-pressure boundary.',
								componentIds: ['V1'],
								connectionIds: []
							}
						])
					)
			}
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		expect(ws.pane).toBe('results');
		expect(await results().findByText('The network cannot be solved yet')).toBeInTheDocument();
		expect(
			results().getByText('1 problem to fix before the network can be solved:')
		).toBeInTheDocument();
		// An issue code the browser does not name keeps the server's message.
		expect(
			results().getByText(/This part of the network has no fixed-pressure boundary\./)
		).toBeInTheDocument();

		await fireEvent.click(results().getByRole('button', { name: 'Branch A globe valve' }));
		expect(ws.pane).toBe('build');
		expect(ws.nav.current?.id).toBe('V1');
	});

	it('lists validation details', async () => {
		const ws = testWorkspace(pumpTransferExample(), {
			solver: {
				solve: () =>
					Promise.reject(
						new ValidationError('Invalid input', ['project › fluid › temperature: too high'], 400)
					)
			}
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		expect(
			await results().findByText('The calculation server rejected the project')
		).toBeInTheDocument();
		expect(results().getByText('project › fluid › temperature: too high')).toBeInTheDocument();
	});

	it('shows the network error when the server cannot answer', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		await solve();
		expect(await results().findByText('No results')).toBeInTheDocument();
		expect(results().getByText(/not available on the calculation server yet/)).toBeInTheDocument();
	});

	it('shows whether the solve converged, and marks it stale after an edit', async () => {
		// Test input: a made-up non-converged state (see testing/results.ts).
		const solveFn = vi.fn((project: Project): Promise<SolveResponse> =>
			Promise.resolve(
				response(
					pumpTransferSolved({
						converged: false,
						flags: [
							{
								code: 'NOT_CONVERGED',
								severity: 'invalid',
								message: `Did not converge for ${project.id}`,
								componentId: null,
								connectionId: null,
								portId: null,
								details: {}
							}
						],
						convergence: {
							message: 'Iteration limit reached',
							innerIterations: 100,
							outerIterations: 3,
							oscillatingComponents: [],
							maxContinuityResidual: { elementId: null, value: 1e-3 },
							maxEnergyResidual: { elementId: null, value: 1e-2 }
						}
					}),
					{ success: false, computeTime: 0.25 }
				)
			)
		);
		const ws = testWorkspace(pumpTransferExample(), { solver: { solve: solveFn } });
		render(WorkspaceView, { workspace: ws });
		const solved = ws.project;
		await solve();
		// The app solves without system curves (D10): the pump chart fetches its own. The request
		// carries a signal, so Cancel can abort it.
		expect(solveFn).toHaveBeenCalledWith(
			solved,
			{ includeSystemCurve: false },
			{ signal: expect.any(AbortSignal) }
		);
		expect(await results().findByText('Did not converge')).toBeInTheDocument();
		expect(results().getByText('Iteration limit reached')).toBeInTheDocument();
		expect(results().getByText(/Did not converge for example-pump-transfer/)).toBeInTheDocument();
		expect(results().queryByText(/project changed after this solve/)).toBeNull();

		// Renaming the project cannot change the results: they stay current.
		ws.store.update((p) => {
			p.metadata.name = 'Changed';
		}, 'rename project');
		expect(results().queryByText(/project changed after this solve/)).toBeNull();
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		expect(await results().findByText(/project changed after this solve/)).toBeInTheDocument();
	});

	it('lists inputs to check before solving', () => {
		const project = pumpTransferExample();
		project.connections = project.connections.filter((c) => c.id !== 'L3');
		render(WorkspaceView, { workspace: testWorkspace(project) });
		expect(results().getByText(/Inputs to check \(2\)/)).toBeInTheDocument();
		expect(
			results().getByText('Outlet of Discharge isolation valve is not connected or plugged.')
		).toBeInTheDocument();
		expect(
			results().getByText('Port 1 of Discharge tank is not connected or plugged.')
		).toBeInTheDocument();
	});

	it('Show opens the piping of a port that is not connected', async () => {
		const project = pumpTransferExample();
		project.connections = project.connections.filter((c) => c.id !== 'L3');
		const ws = testWorkspace(project);
		render(WorkspaceView, { workspace: ws });
		ws.pane = 'results';
		const show = results().getByRole('button', {
			name: 'Show: Port 1 of Discharge tank is not connected or plugged.'
		});
		await fireEvent.click(show);
		expect(ws.pane).toBe('build');
		expect(ws.nav.current?.id).toBe('R2');
		expect(screen.getByRole('tab', { name: 'Piping' })).toHaveAttribute('aria-selected', 'true');
		expect(screen.getByRole('heading', { name: 'Port 1 is not connected' })).toBeInTheDocument();
	});

	it('lists a control valve setpoint still at 0', () => {
		const project = pumpTransferExample();
		const valve = project.components.find((c) => c.id === 'V1')!;
		Object.assign(valve, { valveType: 'fcv', setpoint: 0 });
		render(WorkspaceView, { workspace: testWorkspace(project) });
		expect(
			results().getByText(
				'The flow setpoint of Discharge isolation valve is 0 L/s, which shuts the line.'
			)
		).toBeInTheDocument();
	});

	it('announces only the short status line, and shows the disclaimer', async () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		expect(document.querySelector('[aria-live]')).toBeNull();
		await solve();
		expect(await results().findByRole('status')).toHaveTextContent('Last solve: no results');
		expect(results().getByText(/is an engineering aid/)).toBeInTheDocument();
		expect(results().getByRole('link', { name: 'About and privacy' })).toHaveAttribute(
			'href',
			'/#about'
		);
	});

	it('a pump without a curve: named in the inputs to check and in the issue, with links', async () => {
		const project = pumpTransferExample();
		project.pumpLibrary = [];
		const ws = testWorkspace(project, {
			solver: {
				solve: () =>
					Promise.reject(
						new TopologyError('The network cannot be solved: 1 topology issue(s).', [
							{
								code: 'UNKNOWN_PUMP_CURVE',
								message: "pump 'P1' refers to pump curve 'C1', which is not in the pump library",
								componentIds: ['P1'],
								connectionIds: []
							}
						])
					)
			}
		});
		render(WorkspaceView, { workspace: ws });
		const needs =
			"Transfer pump needs a pump curve: enter at least 3 points of its head against flow, or pick a curve from the project's pump library.";
		expect(results().getByText(needs)).toBeInTheDocument();
		await fireEvent.click(results().getByRole('button', { name: `Show: ${needs}` }));
		expect(ws.pane).toBe('build');
		expect(ws.nav.current?.id).toBe('P1');

		ws.pane = 'results';
		await solve();
		const section = await results().findByRole('region', {
			name: 'The network cannot be solved yet'
		});
		expect(toldText(section)).not.toMatch(/topology issue\(s\)|'P1'|'C1'/);
		const item = within(section).getByRole('listitem');
		expect(item).toHaveTextContent(needs);
		// The server's message is kept, under Details.
		expect(serverDetail(item)).toHaveTextContent(
			"Details Calculation server's message: pump 'P1' refers to pump curve 'C1', which is not in the pump library"
		);
		await fireEvent.click(within(item).getByRole('button', { name: 'Transfer pump' }));
		expect(ws.nav.current?.id).toBe('P1');
	});

	it('a speed-controlled pump whose curve gives no single speed: named, in display units', async () => {
		const project = pumpTransferExample();
		project.settings.units = { ...IMPERIAL_UNITS };
		(project.components[1] as Pump).control = { mode: 'flow', setpoint: 0.01, minSpeed: 0.4 };
		const ws = testWorkspace(project, {
			solver: {
				solve: () =>
					Promise.reject(
						new TopologyError('The network cannot be solved: 1 topology issue(s).', [
							{
								code: 'CONTROLLED_PUMP_CURVE',
								// Wording of the API (solver/builder.py); made-up interval.
								message:
									"pump 'P1' is speed-controlled, but its curve 'C1' (x) does not give one speed " +
									'for each head: the head at a fixed flow, s² H₀(Q/s), does not rise with speed ' +
									"s where 2 H₀(x) − x H₀'(x) ≤ 0, which holds for rated-speed flows x from " +
									'0.0125 to 0.0315 m³/s; use a curve whose head rises less steeply with flow ' +
									"there (2 H₀(x) > x H₀'(x)), or a fixed speed",
								componentIds: ['P1'],
								connectionIds: []
							}
						])
					)
			}
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		const section = await results().findByRole('region', {
			name: 'The network cannot be solved yet'
		});
		const item = within(section).getByRole('listitem');
		expect(item).toHaveTextContent(/^Transfer pump is speed-controlled, but its pump curve/);
		expect(item).toHaveTextContent(/for rated-speed flows x from 198\.1 to 499\.3 gpm\./);
		expect(item).toHaveTextContent(/Use a curve whose head rises less steeply with flow there/);
		expect(toldText(section)).not.toMatch(/'P1'|m³\/s/);
		expect(serverDetail(item)).toHaveTextContent(/from 0\.0125 to 0\.0315 m³\/s/);
	});

	it('a curve issue that arrives after the pump was given another curve: the server names the curve', async () => {
		// The solve is sent with curve C1; while it is being computed the pump is given C2, and
		// the issue about C1 arrives. Telling it with the pump's curve now would blame C2.
		const project = pumpTransferExample();
		(project.components[1] as Pump).control = { mode: 'flow', setpoint: 0.01, minSpeed: 0.4 };
		const sent = project.pumpLibrary[0]!;
		project.pumpLibrary = [...project.pumpLibrary, { ...sent, id: 'C2', name: 'Other curve' }];
		let fail: (error: unknown) => void = () => {};
		const ws = testWorkspace(project, {
			solver: { solve: () => new Promise<SolveResponse>((_, reject) => (fail = reject)) }
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		expect(
			ws.editComponent<Pump>('P1', 'change pump curve', (c) => {
				c.curveId = 'C2';
			})
		).toBe(true);
		// Wording of the API (solver/builder.py); made-up interval.
		const message =
			`pump 'P1' is speed-controlled, but its curve 'C1' (${sent.name}) does not give one ` +
			'speed for each head: the head at a fixed flow, s² H₀(Q/s), does not rise with speed s ' +
			"where 2 H₀(x) − x H₀'(x) ≤ 0, which holds for rated-speed flows x from 0.0125 to " +
			'0.0315 m³/s; use a curve whose head rises less steeply with flow there ' +
			"(2 H₀(x) > x H₀'(x)), or a fixed speed";
		fail(
			new TopologyError('The network cannot be solved: 1 topology issue(s).', [
				{ code: 'CONTROLLED_PUMP_CURVE', message, componentIds: ['P1'], connectionIds: [] }
			])
		);
		const section = await results().findByRole('region', {
			name: 'The network cannot be solved yet'
		});
		const item = within(section).getByRole('listitem');
		expect(item).toHaveTextContent(message);
		expect(item).not.toHaveTextContent('Other curve');
		expect(results().getByRole('status')).toHaveTextContent('Last solve: no results, out of date');
	});

	it('tells a piping issue with names and display units, and its link opens that piping', async () => {
		const project = pumpTransferExample();
		project.settings.units = { ...IMPERIAL_UNITS };
		// The API's wording (solver/builder.py) for made-up values.
		const message =
			"connection 'L2' pipe 1: roughness 0.008 m is 4 times the inner diameter 0.002 m; the " +
			'Colebrook equation has no solution for relative roughness of 3.7 or more';
		const ws = testWorkspace(project, {
			solver: {
				solve: () =>
					Promise.reject(
						new TopologyError('The network cannot be solved: 1 topology issue(s).', [
							{ code: 'ROUGHNESS_OUT_OF_RANGE', message, componentIds: [], connectionIds: ['L2'] }
						])
					)
			}
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		const section = await results().findByRole('region', {
			name: 'The network cannot be solved yet'
		});
		const item = within(section).getByRole('listitem');
		const inch = (m: number) => String(Number((m / 0.0254).toPrecision(4)));
		expect(toldText(item)).toContain(
			'Piping Transfer pump → Discharge isolation valve, pipe 1: its roughness ' +
				`(${inch(0.008)} in) is 4 times its inner diameter (${inch(0.002)} in)`
		);
		expect(toldText(item)).not.toMatch(/'L2'| m[ ;)]/);
		expect(serverDetail(item)).toHaveTextContent(message);
		await fireEvent.click(
			within(item).getByRole('button', { name: 'Transfer pump → Discharge isolation valve' })
		);
		expect(ws.pane).toBe('build');
		expect(ws.nav.current?.id).toBe('P1');
		expect(ws.nav.mode).toBe('connection');
		expect(ws.nav.activeConnection?.id).toBe('L2');
	});

	it('names open ports in the server issues, and their links open the port', async () => {
		const project = pumpTransferExample();
		project.connections = project.connections.filter((c) => c.id !== 'L3');
		const ws = testWorkspace(project, {
			solver: {
				solve: () =>
					Promise.reject(
						new TopologyError('The network cannot be solved: 2 topology issue(s).', [
							{
								code: 'UNCONNECTED_PORT',
								message: "port 'V1:outlet' is not connected; connect it or add a plug",
								componentIds: ['V1'],
								connectionIds: []
							},
							{
								code: 'UNCONNECTED_PORT',
								message: "port 'R2:port_1' is not connected; connect it or add a plug",
								componentIds: ['R2'],
								connectionIds: []
							}
						])
					)
			}
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		const section = await results().findByRole('region', {
			name: 'The network cannot be solved yet'
		});
		expect(
			within(section).getByText('2 problems to fix before the network can be solved:')
		).toBeInTheDocument();
		const items = within(section).getAllByRole('listitem');
		expect(items[0]).toHaveTextContent(
			'Outlet of Discharge isolation valve is not connected: connect it or add a plug.'
		);
		expect(items[1]).toHaveTextContent(
			'Port 1 of Discharge tank is not connected: connect it or add a plug.'
		);
		await fireEvent.click(within(items[1]!).getByRole('button', { name: 'Discharge tank' }));
		expect(ws.nav.current?.id).toBe('R2');
		expect(screen.getByRole('heading', { name: 'Port 1 is not connected' })).toBeInTheDocument();

		// After an edit the issues are out of date, still told as they were.
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 42;
		}, 'change length');
		ws.pane = 'results';
		expect(
			await results().findByText(/Results are out of date: the project changed after this solve/)
		).toBeInTheDocument();
		expect(within(section).getAllByRole('listitem')[1]).toHaveTextContent(
			'Port 1 of Discharge tank is not connected: connect it or add a plug.'
		);
	});

	it('tells a glycol without a concentration in percent, once', async () => {
		const project = pumpTransferExample();
		project.fluid = { kind: 'builtin', fluidId: 'ethylene_glycol', temperature: 293.15 };
		const message =
			'Ethylene glycol (aqueous) needs a concentration (glycol mass fraction, 0 to 1)';
		const ws = testWorkspace(project, {
			solver: {
				solve: () => Promise.reject(new ValidationError(message, [message], 400, 'FLUID_ERROR'))
			}
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		expect(
			await results().findByText('The fluid properties cannot be calculated')
		).toBeInTheDocument();
		expect(
			results().getByText(
				'Ethylene glycol (aqueous) needs a glycol concentration: enter it in Settings, as a percentage by mass.'
			)
		).toBeInTheDocument();
		expect(results().queryByText(/mass fraction, 0 to 1/)).toBeNull();

		// Entering the concentration makes the error out of date; its text stays the browser's.
		ws.store.update((p) => {
			if (p.fluid.kind === 'builtin') p.fluid.concentration = 0.3;
		}, 'change glycol concentration');
		expect(
			await results().findByText(/Results are out of date: the project changed after this solve/)
		).toBeInTheDocument();
		expect(results().getByText(/needs a glycol concentration: enter it in Settings/)).toBeVisible();
		expect(results().queryByText(/mass fraction, 0 to 1/)).toBeNull();
	});

	it('shows another validation message once, with its other details', async () => {
		const ws = testWorkspace(pumpTransferExample(), {
			solver: {
				solve: () =>
					Promise.reject(
						new ValidationError(
							'Temperature out of range',
							['Temperature out of range', 'Water: 273.16–373 K'],
							400,
							'FLUID_ERROR'
						)
					)
			}
		});
		render(WorkspaceView, { workspace: ws });
		await solve();
		expect(await results().findAllByText('Temperature out of range')).toHaveLength(1);
		expect(results().getByText('Water: 273.16–373 K')).toBeInTheDocument();
	});

	it('a shared link: shows its description and says the link holds no results, with a Solve', async () => {
		const project = {
			...pumpTransferExample(),
			methodVersion: '1.0.0',
			metadata: {
				...pumpTransferExample().metadata,
				description: 'Rev A for client review.\nPump P1 duty point.'
			}
		};
		const solveFn = vi.fn(() => Promise.resolve(response(pumpTransferSolved())));
		const ws = testWorkspace(project, { solver: { solve: solveFn } });
		render(WorkspaceView, { workspace: ws });
		const about = results().getByRole('region', { name: 'About this project' });
		expect(about.querySelector('p')!.textContent).toBe(
			'Rev A for client review.\nPump P1 duty point.'
		);
		expect(results().getByText(/^This project was opened without results/)).toBeInTheDocument();
		await fireEvent.click(results().getByRole('button', { name: 'Solve now' }));
		expect(solveFn).toHaveBeenCalledTimes(1);
		expect(await results().findByRole('heading', { name: 'Converged' })).toBeInTheDocument();
		expect(results().getByRole('region', { name: 'About this project' })).toBeInTheDocument();
	});

	it('a project never solved and without a description: the plain prompt to solve', () => {
		const project = pumpTransferExample();
		delete project.metadata.description;
		render(WorkspaceView, { workspace: testWorkspace(project) });
		expect(results().queryByRole('region', { name: 'About this project' })).toBeNull();
		expect(
			results().getByText(
				'Press Solve to calculate the flows, pressures and pump operating points of the network.'
			)
		).toBeInTheDocument();
	});

	describe('the Export button (proposal export.md §5.2)', () => {
		const exportButton = () => results().queryByRole('button', { name: /^Export results/ });

		it('is shown once there are results to export, and preloads the dialog once', async () => {
			exportLoader.preloads = 0;
			const solveFn = vi.fn(() => Promise.resolve(response(pumpTransferSolved())));
			const ws = testWorkspace(pumpTransferExample(), { solver: { solve: solveFn } });
			render(WorkspaceView, { workspace: ws });
			// Never an unavailable control on an unsolved project.
			expect(exportButton()).toBeNull();
			expect(document.querySelector('[data-export-button]')).toBeNull();
			expect(exportLoader.preloads).toBe(0);
			await solve();
			await results().findByRole('heading', { name: 'Converged' });
			const button = exportButton()!;
			expect(button).toHaveAccessibleName('Export results');
			expect(button).toHaveAttribute('aria-haspopup', 'dialog');
			expect(button).not.toHaveAttribute('aria-disabled', 'true');
			expect(button).toHaveTextContent('Export');
			expect(exportLoader.preloads).toBe(1);
			// Out of date: still offered (the file says so); the chunk is not asked for again.
			ws.store.update((p) => {
				p.connections[0]!.piping.pipes[0]!.length = 500;
			}, 'change length');
			expect(await results().findByText(/project changed after this solve/)).toBeInTheDocument();
			expect(exportButton()).toBeInTheDocument();
			await solve();
			await results().findByRole('heading', { name: 'Converged' });
			expect(exportLoader.preloads).toBe(1);
		});

		it('is not shown while a failed solve hides the earlier results, and is once they are shown', async () => {
			let calls = 0;
			const solveFn = vi.fn(() =>
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
			const ws = testWorkspace(pumpTransferExample(), { solver: { solve: solveFn } });
			render(WorkspaceView, { workspace: ws });
			await solve();
			await results().findByRole('heading', { name: 'Converged' });
			expect(ws.remove('R2', false)).toBe(true);
			await solve();
			await results().findByRole('region', { name: 'The network cannot be solved yet' });
			expect(exportButton()).toBeNull();
			await fireEvent.click(results().getByRole('button', { name: 'Show the earlier results' }));
			// The dialog then says these results are not in the file (Compare's rule).
			expect(exportButton()).toBeInTheDocument();
		});

		it('is unavailable, with the reason, while a solve runs', async () => {
			let release: (r: SolveResponse) => void = () => {};
			let calls = 0;
			const solveFn = vi.fn(() =>
				++calls === 1
					? Promise.resolve(response(pumpTransferSolved()))
					: new Promise<SolveResponse>((resolve) => (release = resolve))
			);
			let opened = 0;
			exportLoader.load = () => {
				opened++;
				return Promise.reject(new Error('not loaded in this test'));
			};
			const ws = testWorkspace(pumpTransferExample(), { solver: { solve: solveFn } });
			render(WorkspaceView, { workspace: ws });
			await solve();
			await results().findByRole('heading', { name: 'Converged' });
			ws.store.update((p) => {
				p.connections[0]!.piping.pipes[0]!.length = 500;
			}, 'change length');
			void ws.solve();
			await vi.waitFor(() => expect(ws.store.calculating).toBe('solve'));
			const button = exportButton()!;
			expect(button).toHaveAttribute('aria-disabled', 'true');
			expect(button).toHaveAccessibleDescription(
				'A solve is running; export when it finishes, or Cancel stops it.'
			);
			expect(button).toHaveAttribute(
				'title',
				'A solve is running; export when it finishes, or Cancel stops it.'
			);
			await fireEvent.click(button);
			expect(opened).toBe(0);
			release(response(pumpTransferSolved()));
			await vi.waitFor(() => expect(button).not.toHaveAttribute('aria-disabled', 'true'));
			expect(button).not.toHaveAttribute('aria-describedby');
		});

		it('names the case shown, and on Compare cases is shown when any case has a response', async () => {
			const project = withScenarios(pumpTransferExample(), [
				{ id: 'S1', name: 'Winter', overrides: [] }
			]);
			const solveFn = vi.fn(() => Promise.resolve(response(pumpTransferSolved())));
			const ws = testWorkspace(project, { solver: { solve: solveFn } });
			render(WorkspaceView, { workspace: ws });
			ws.comparing = true;
			await vi.waitFor(() => expect(results().getByRole('region', { name: 'Compare cases' })));
			expect(exportButton()).toBeNull();
			ws.setCase('S1');
			await ws.solve();
			// The base case is shown and has no results, but Winter has: Compare can be exported,
			// and the dialog opens on All cases there, so the button says so (review W5).
			ws.setCase(null);
			await vi.waitFor(() =>
				expect(exportButton()).toHaveAccessibleName('Export results of all cases')
			);
			ws.comparing = false;
			await vi.waitFor(() => expect(exportButton()).toBeNull());
			ws.setCase('S1');
			await vi.waitFor(() =>
				expect(exportButton()).toHaveAccessibleName('Export results of Winter')
			);
		});

		it('says to reload the page when the dialog cannot be loaded', async () => {
			exportLoader.load = () =>
				Promise.reject(new TypeError('Failed to fetch dynamically imported module'));
			const solveFn = vi.fn(() => Promise.resolve(response(pumpTransferSolved())));
			const ws = testWorkspace(pumpTransferExample(), { solver: { solve: solveFn } });
			render(WorkspaceView, { workspace: ws });
			await solve();
			await results().findByRole('heading', { name: 'Converged' });
			await fireEvent.click(exportButton()!);
			await vi.waitFor(() =>
				expect(ws.notice).toMatchObject({
					kind: 'error',
					text: 'This part of the app could not be loaded: the app may have been updated since this page opened, or the connection dropped. Reload the page (the project is in its link), then solve again.'
				})
			);
			expect(screen.queryByRole('dialog', { name: 'Export results' })).toBeNull();
		});
	});
});
