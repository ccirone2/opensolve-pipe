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
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';

function results() {
	return within(screen.getByRole('region', { name: 'Results' }));
}

async function solve() {
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
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
		// The app solves without system curves (D10): the pump chart fetches its own.
		expect(solveFn).toHaveBeenCalledWith(solved, { includeSystemCurve: false });
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
		expect(within(section).queryByText(/topology issue\(s\)|'P1'|'C1'/)).toBeNull();
		const item = within(section).getByRole('listitem');
		expect(item).toHaveTextContent(needs);
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
		expect(within(section).queryByText(/'P1'|m³\/s/)).toBeNull();
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
});
