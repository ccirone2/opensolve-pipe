/**
 * The Results pane names a connection as its results were solved once they are out of date
 * (utils/results.ts resultsProject): after a reversal since the solve, the trace's heading, the
 * flags list and a scenario's pipe changes name the ends the flow's sign, the pipe numbers and the
 * values refer to, as the Links table does. The solve results are made-up test inputs
 * (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Override, PipeConnection, Project, ScenarioResult } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, link, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import type { Workspace } from '$lib/state/workspace.svelte';
import { reversePiping } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { withScenarios } from '$lib/utils/scenarios';

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

afterEach(() => {
	vi.unstubAllGlobals();
});

/** L2 of two pipes (3 m, then 2 m). */
function twoPipeProject(): Project {
	const project = pumpTransferExample();
	const l2 = project.connections.find((c) => c.id === 'L2') as PipeConnection;
	const a = l2.piping.pipes[0]!;
	l2.piping.pipes = [a, { ...a, length: 2 }];
	return project;
}

/** Turn L2 around, as Build's turning of a connection does: ends swapped, pipes reversed. */
function reverseL2(ws: Workspace) {
	const result = ws.store.update((p) => {
		const c = p.connections.find((x) => x.id === 'L2')!;
		[c.fromComponentId, c.toComponentId] = [c.toComponentId, c.fromComponentId];
		[c.fromPortId, c.toPortId] = [c.toPortId, c.fromPortId];
		c.piping = reversePiping(c.piping);
	}, 'Reverse');
	expect(result.ok).toBe(true);
}

const transitional = flag({
	code: 'TRANSITIONAL_FLOW',
	severity: 'warning',
	message: "connection 'L2' pipe 1: made-up",
	connectionId: 'L2',
	details: { segmentIndex: 0, reynoldsNumber: 2500 }
});

async function solved(project: Project = twoPipeProject()) {
	const one = link().segments[0]!;
	const state = pumpTransferSolved({
		linkResults: {
			...pumpTransferSolved().linkResults,
			L2: link({
				flow: 0.02,
				velocity: 4,
				segments: [
					{ ...one, index: 0, velocity: 4 },
					{ ...one, index: 1, velocity: 4 }
				]
			})
		},
		flags: [transitional]
	});
	const solve = vi.fn(() => Promise.resolve(response(state)));
	const ws = testWorkspace(project, { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
	await results().findByRole('heading', { name: 'Converged' });
	return ws;
}

describe('after a reversal since the solve, the Results pane names a connection as solved', () => {
	it('heads the trace with the ends its flow and pipe numbers refer to', async () => {
		screenWidth(false);
		const ws = await solved();
		reverseL2(ws);
		await tick();
		expect(ws.store.results.stale).toBe(true);
		ws.inspect({ kind: 'connection', id: 'L2' });
		await tick();
		// Its values (flow 20 L/s from the pump; "Pipe 1" the 3 m pipe) are as solved.
		const trace = screen.getByRole('dialog', { name: 'Transfer pump → Discharge isolation valve' });
		expect(within(trace).getByText(/^Pipe 1: Re = 2500/)).toBeInTheDocument();
	});

	it('names a connection’s flag in the flags list as solved, as its pipe number is', async () => {
		screenWidth(true);
		const ws = await solved();
		reverseL2(ws);
		await tick();
		const flags = results().getByRole('region', { name: /^Flags/ });
		expect(
			within(flags).getByRole('button', {
				name: /^Show Transfer pump → Discharge isolation valve: Pipe 1: Re = 2500/
			})
		).toBeInTheDocument();
	});

	it('names the pipe of a scenario’s pipe change by the connection as solved', async () => {
		screenWidth(true);
		const overrides: Override[] = [
			{ kind: 'pipe', connectionId: 'L2', pipeIndex: 0, field: 'length', value: 7 }
		];
		const scenario: ScenarioResult = {
			id: 'S1',
			name: 'Winter',
			description: null,
			overrides: [
				{
					index: 0,
					override: overrides[0]!,
					state: 'applied',
					value: 7,
					baseValue: 3,
					unit: 'm',
					message: ''
				}
			]
		};
		const project = withScenarios(twoPipeProject(), [{ id: 'S1', name: 'Winter', overrides }]);
		const ws = testWorkspace(project, {
			solver: {
				solve: async (_p, _o, request) =>
					response(pumpTransferSolved(), request?.scenarioId ? { scenario } : {})
			}
		});
		render(WorkspaceView, { workspace: ws });
		ws.setCase('S1');
		await ws.solve();
		await tick();
		reverseL2(ws);
		await tick();
		// The change follows its pipe (now pipe 2); the record of the solve names it as solved.
		const change = ws.store.project.scenarios![0]!.overrides![0]!;
		expect(change).toMatchObject({ connectionId: 'L2', pipeIndex: 1 });
		const card = screen.getByRole('region', { name: /^Scenario: Winter/ });
		expect(card).toHaveTextContent('Pipe 1 of Transfer pump → Discharge isolation valve');
		expect(card).not.toHaveTextContent('Pipe 1 of Discharge isolation valve → Transfer pump');
	});
});
