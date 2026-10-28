/**
 * The Pumps together card in the Pumps view (CLAUDE.md D21, proposal pump-groups.md §4, §6.1):
 * shown with two pumps or more, closed by default; opening it asks for the group curve of the
 * suggested group for this solve; the members are page state, kept when the case shown changes,
 * and the card asks for the case shown (its scenario id). The solves and group curves are the
 * shared fixture's real API answers, given by a fake solver.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { NotAStationError, TopologyError } from '$lib/api/client';
import type {
	Component,
	PipeConnection,
	Project,
	PumpGroupCurveResponse,
	SolveResponse
} from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { withScenarios } from '$lib/utils/scenarios';
import { formatNumber } from '$lib/utils/units';

// jsdom has no canvas: a stub context lets the chart be "drawn" (Chart.js says it cannot, on the
// console, which these tests silence).
const getContext = HTMLCanvasElement.prototype.getContext;
const consoleError = console.error;
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

interface FixtureCase {
	name: string;
	project: Project;
	solve: SolveResponse;
	groupCurve: { status: number; body: unknown };
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;

interface Call {
	pumpIds: readonly string[];
	scenarioId?: string;
}

function setup(project: Project, c: FixtureCase) {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	const calls: Call[] = [];
	const solver: Solver = {
		solve: async () => structuredClone(c.solve),
		groupCurve: async (_project, pumpIds, options) => {
			calls.push({ pumpIds, ...(options?.scenarioId ? { scenarioId: options.scenarioId } : {}) });
			return structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
		}
	};
	const ws = testWorkspace(project, { solver });
	render(WorkspaceView, { workspace: ws });
	return { ws, calls };
}

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const card = () => results().getByRole('region', { name: /^Pumps together/ }) as HTMLElement;

async function showPumps() {
	await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
}

describe('the Pumps together card in the Pumps view', () => {
	it('is closed by default; opened, it asks for the suggested group’s curve and shows its shares', async () => {
		const c = named('parallel-ideal');
		const { calls } = setup(structuredClone(c.project), c);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		const toggle = within(card()).getByRole('button', { name: /^Pumps together/ });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(calls).toEqual([]);
		await fireEvent.click(toggle);
		await waitFor(() => expect(calls).toEqual([{ pumpIds: ['PA', 'PB'] }]));
		const duty = (c.groupCurve.body as PumpGroupCurveResponse).duty!;
		const table = within(card()).getByRole('table', { name: 'The pumps in the group' });
		await waitFor(() =>
			expect(within(table).getByText(formatNumber(duty.members[0]!.share! * 100, 4))).toBeVisible()
		);
		expect(
			within(card()).getByRole('figure', { name: 'Pump PA and Pump PB in parallel' })
		).toBeVisible();
		// Asked once per solve.
		await fireEvent.click(toggle);
		await fireEvent.click(toggle);
		expect(calls).toHaveLength(1);
	});

	it('keeps the members when the case shown changes, and asks for that case', async () => {
		const c = named('ladder');
		const project = withScenarios(structuredClone(c.project), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const { ws, calls } = setup(project, c);
		await ws.store.solveAll();
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls).toEqual([{ pumpIds: ['P1', 'P2', 'P3'] }]));
		await fireEvent.click(within(card()).getByRole('checkbox', { name: /Pump P1/ }));
		await waitFor(() => expect(calls.at(-1)).toEqual({ pumpIds: ['P2', 'P3'] }));
		ws.setCase('S1');
		await waitFor(() => expect(calls.at(-1)).toEqual({ pumpIds: ['P2', 'P3'], scenarioId: 'S1' }));
		const boxes = within(card()).getAllByRole('checkbox') as HTMLInputElement[];
		expect(boxes.map((b) => [b.closest('label')!.textContent!.trim(), b.checked])).toEqual([
			['Pump P1', false],
			['■ Pump P2', true],
			['★ Pump P3', true]
		]);
		// The case is named on the figure (the fake answers with the fixture's three-pump station).
		expect(
			within(card()).getByRole('figure', { name: /^Pump .* in parallel, Winter$/ })
		).toBeVisible();
	});

	it('shows no values and asks nothing for a solve that did not converge', async () => {
		const c = named('parallel-ideal');
		const notConverged = structuredClone(c);
		notConverged.solve.success = false;
		notConverged.solve.solvedState.converged = false;
		const { calls } = setup(structuredClone(c.project), notConverged);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Did not converge' });
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		expect(
			within(card()).getByText(
				'This solve did not converge: its values are not a solution, so the card shows none.'
			)
		).toBeVisible();
		expect(within(card()).queryByRole('figure')).toBeNull();
		expect(calls).toEqual([]);
	});

	it('uses nothing of the earlier results shown after a failed solve (Compare’s rule)', async () => {
		const c = named('parallel-ideal');
		let solves = 0;
		HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
		const calls: Call[] = [];
		const ws = testWorkspace(structuredClone(c.project), {
			solver: {
				solve: async () => {
					if (++solves === 1) return structuredClone(c.solve);
					throw new TopologyError('The network cannot be solved: 1 topology issue(s).', [
						{
							code: 'UNCONNECTED_PORT',
							message: "port 'T2:run_outlet' is not connected; connect it or add a plug",
							componentIds: ['T2'],
							connectionIds: []
						}
					]);
				},
				groupCurve: async (_p, pumpIds) => {
					calls.push({ pumpIds });
					return structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
				}
			}
		});
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		expect(ws.remove('R2', false)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await fireEvent.click(
			await results().findByRole('button', { name: 'Show the earlier results' })
		);
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		expect(
			within(card()).getByText(
				'The latest solve failed; the card shows nothing from an earlier version of the project.'
			)
		).toBeVisible();
		expect(within(card()).queryByRole('table')).toBeNull();
		expect(calls).toEqual([]);
	});

	it('suggests on the case as solved: a scenario that sets a PRV between the tees active', async () => {
		const c = named('parallel-ideal');
		const base = structuredClone(c.project);
		const leg = base.connections.find((x) => x.id === 'LA2')!;
		const pa = base.components.find((x) => x.id === 'PA')!;
		// Made-up: a PRV on PA's discharge leg, failed open in the base, active in Winter.
		const prv = {
			type: 'valve',
			valveType: 'prv',
			id: 'V1',
			name: 'PRV V1',
			elevation: pa.elevation,
			status: 'failed_open',
			setpoint: 2e5,
			ports: ['inlet', 'outlet'].map((id) => ({ id, nominalSize: 0.1016 }))
		} as unknown as Component;
		const project = withScenarios(
			{
				...base,
				components: [...base.components, prv],
				connections: [
					...base.connections.filter((x) => x.id !== 'LA2'),
					{ ...leg, toComponentId: 'V1', toPortId: 'inlet' },
					{ ...leg, id: 'LA3', fromComponentId: 'V1', fromPortId: 'outlet' } as PipeConnection
				]
			},
			[
				{
					id: 'S1',
					name: 'Winter',
					overrides: [{ kind: 'component', componentId: 'V1', field: 'status', value: 'active' }]
				}
			]
		);
		const { ws, calls } = setup(project, c);
		await ws.store.solveAll();
		// The PRV holds a pressure inside the station in Winter: nothing is suggested, nothing asked.
		ws.setCase('S1');
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		const boxes = () => within(card()).getAllByRole('checkbox') as HTMLInputElement[];
		expect(boxes().map((b) => b.checked)).toEqual([false, false]);
		expect(within(card()).queryByRole('button', { name: /^Also found/ })).toBeNull();
		expect(calls).toEqual([]);
		// In the base it is failed open: PA and PB are the group suggested, and asked for.
		ws.setCase(null);
		await waitFor(() => expect(calls).toEqual([{ pumpIds: ['PA', 'PB'] }]));
		expect(boxes().map((b) => b.checked)).toEqual([true, true]);
	});

	it('words a refusal on the project it belongs to, not on edits made since', async () => {
		const c = named('parallel-ideal');
		const base = structuredClone(c.project);
		const r1 = base.components.find((x) => x.id === 'R1')!;
		const piping = base.connections.find((x) => x.id === 'LA1')!.piping;
		const join = (id: string, from: string, to: string): PipeConnection => {
			const [fromComponentId, fromPortId] = from.split(':') as [string, string];
			const [toComponentId, toPortId] = to.split(':') as [string, string];
			return { id, fromComponentId, fromPortId, toComponentId, toPortId, piping };
		};
		// Made-up: each pump draws from its own tank, R1 and R3, into one discharge header.
		const project: Project = {
			...base,
			components: [
				...base.components.filter((x) => x.id !== 'T1'),
				{ ...r1, id: 'R3', name: 'Tank R3' } as Component
			],
			connections: [
				join('LA1', 'R1:port_1', 'PA:suction'),
				join('LB1', 'R3:port_1', 'PB:suction'),
				...base.connections.filter((x) => ['LA2', 'LB2', 'L2'].includes(x.id))
			]
		};
		HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
		const message = 'the pumps PA and PB draw from different boundaries';
		const issues = [
			{
				code: 'DIFFERENT_BOUNDARIES',
				message: 'made-up server words',
				componentIds: ['R1', 'R3'],
				connectionIds: []
			}
		];
		const ws = testWorkspace(project, {
			solver: {
				solve: async () => structuredClone(c.solve),
				groupCurve: async () => {
					throw new NotAStationError(message, [message], issues);
				}
			}
		});
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		for (const name of [/Pump PA/, /Pump PB/]) {
			await fireEvent.click(within(card()).getByRole('checkbox', { name }));
		}
		const told = () =>
			within(within(card()).getByRole('list', { name: 'Why they do not form a station' }))
				.getByRole('listitem')
				.textContent!.replace(/\s+/g, ' ');
		await waitFor(() => expect(told()).toMatch(/^Pump PA and Pump PB draw from different/));
		// Both pumps turned round since the solve: the tanks are now at their discharges, but the
		// refusal answered the project as solved, whose tanks are at the suctions.
		const turned = (x: PipeConnection) =>
			x.toComponentId === 'PA' || x.toComponentId === 'PB'
				? { ...x, toPortId: 'discharge' }
				: x.fromComponentId === 'PA' || x.fromComponentId === 'PB'
					? { ...x, fromPortId: 'suction' }
					: x;
		expect(ws.edit((p) => ({ ...p, connections: p.connections.map(turned) }), 'turn')).toBe(true);
		await waitFor(() => expect(results().getAllByText(/out of date/i).length).toBeGreaterThan(0));
		expect(told()).toMatch(/^Pump PA and Pump PB draw from different/);
		// Renamed since: the names are the current ones, in the box and the words alike.
		const rename = (x: Component) =>
			x.id === 'PA'
				? { ...x, name: 'Duty pump' }
				: x.id === 'R1'
					? { ...x, name: 'Suction tank' }
					: x;
		expect(ws.edit((p) => ({ ...p, components: p.components.map(rename) }), 'rename')).toBe(true);
		await waitFor(() =>
			expect(told()).toMatch(
				/^Duty pump and Pump PB draw from different reservoirs or reference nodes, Suction tank and Tank R3,/
			)
		);
		expect(within(card()).getByRole('checkbox', { name: /Duty pump/ })).toBeChecked();
	});

	it('names elements as the rest of the screen does while results are out of date', async () => {
		const c = named('parallel-ideal');
		const { ws, calls } = setup(structuredClone(c.project), c);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls).toHaveLength(1));
		await within(card()).findByRole('table', { name: 'The pumps in the group' });
		// One edit that makes the results out of date (L2 a metre longer), and two renames.
		const rename = (x: Component) =>
			x.id === 'PA'
				? { ...x, name: 'Duty pump' }
				: x.id === 'T1'
					? { ...x, name: 'Suction header' }
					: x;
		const longer = (x: PipeConnection): PipeConnection =>
			x.id === 'L2'
				? {
						...x,
						piping: {
							...x.piping,
							pipes: x.piping.pipes.map((pipe) => ({ ...pipe, length: pipe.length + 1 }))
						}
					}
				: x;
		expect(
			ws.edit(
				(p) => ({
					...p,
					components: p.components.map(rename),
					connections: p.connections.map(longer)
				}),
				'edit'
			)
		).toBe(true);
		await waitFor(() =>
			expect(within(card()).getByRole('figure', { name: /\(out of date\)$/ })).toBeVisible()
		);
		const text = card().textContent!.replace(/\s+/g, ' ');
		expect(within(card()).getByRole('checkbox', { name: /Duty pump/ })).toBeChecked();
		expect(text).toContain('The group curve is the rise from Suction header (run inlet) to Tee T2');
		expect(text).toContain('Rise from Suction header (run inlet) to Tee T2 (run outlet)');
		expect(text).not.toContain('Tee T1');
		expect(text).not.toContain('Pump PA');
	});

	it('keeps the ids of the group shown by default from new pumps', async () => {
		const c = named('ladder');
		const { ws, calls } = setup(structuredClone(c.project), c);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		await showPumps();
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls).toEqual([{ pumpIds: ['P1', 'P2', 'P3'] }]));
		// No box touched: the group suggested is shown ticked, not the user's.
		expect(ws.pumpGroup).toBe(null);
		expect(ws.reservedIds).toEqual(expect.arrayContaining(['P1', 'P2', 'P3']));
		expect(ws.remove('P3', true)).toBe(true);
		const added = ws.addStandalone('pump');
		expect(added).not.toBe(null);
		expect(added).not.toBe('P3');
	});
});
