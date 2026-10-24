/**
 * Assigned-flow nodes in the results (SDD §4.11, PRD §3.2.1): a view of their own with the flow
 * as entered and the node's static pressure and HGL, the flag of a pressure below the vapor
 * pressure, the node's trace, and a solve that names a node no reservoir reaches. The solve
 * results are made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { ElementTrace, Project, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { assignedFlowProject } from '$lib/testing/helpers';
import { assignedFlowSolved, flag, response, SAMPLE_METHODS } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { insertComponentInConnection } from '$lib/utils/edit';
import { createComponent } from '$lib/utils/factory';

const results = () => within(screen.getByRole('region', { name: 'Results' }));

/** A made-up trace of AF1, shaped like the API's (solver/trace.py). */
const AF1_TRACE: ElementTrace = {
	elementId: 'AF1',
	elementType: 'assigned_flow',
	inputs: [
		{
			name: 'Assigned flow Q_a (positive: leaves the network, a demand; negative: enters it, a supply)',
			value: 0.012,
			unit: 'm³/s',
			source: 'user'
		}
	],
	equations: ['Q_in = Q_a: continuity at the port'],
	correlations: [],
	dataSources: [],
	intermediates: [{ name: 'Static pressure p', value: -99000, unit: 'Pa(g)' }],
	notes: ['Made-up trace for tests.']
};

async function solveWith(solved: SolvedState, project: Project) {
	const solve = vi.fn(() => Promise.resolve(response(solved)));
	const ws = testWorkspace(project, { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
	await results().findByRole('heading', { name: /^(Converged|Did not converge)$/ });
	return ws;
}

async function openView(name: string) {
	await fireEvent.click(results().getByRole('tab', { name }));
}

function cells(row: HTMLElement): string[] {
	return within(row)
		.getAllByRole('cell')
		.map((c) => c.textContent?.replace(/\s+/g, ' ').trim() ?? '');
}

describe('assigned-flow results', () => {
	it('have a view of their own: the flow as entered, static pressure, HGL and the flag', async () => {
		const ws = await solveWith(
			assignedFlowSolved({ trace: { elements: { AF1: AF1_TRACE }, methods: SAMPLE_METHODS } }),
			assignedFlowProject(0.012)
		);
		const tabs = results().getByRole('tablist', { name: 'Results view' });
		expect(
			within(tabs)
				.getAllByRole('tab')
				.map((t) => t.textContent?.trim())
		).toEqual(['Summary', 'Nodes', 'Links', 'Boundaries', 'Assigned flows', 'Methods']);
		await openView('Assigned flows');
		const table = results().getByRole('table', { name: 'Results per assigned-flow node' });
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => h.textContent?.trim())
		).toEqual([
			'Assigned-flow node',
			'Direction',
			'Assigned flow L/s',
			'Elevation m',
			'Pressure kPa(g)',
			'Absolute pressure kPa(a)',
			'HGL m'
		]);
		const row = within(table)
			.getByRole('rowheader', { name: /^Process user/ })
			.closest('tr')!;
		expect(cells(row)).toEqual(['Demand', '12', '2', '-99', '2.325', '-8.1']);
		// The flag on the node, in the flags summary: below the vapor pressure, absolute.
		const invalid = results().getByRole('list', { name: 'Physically invalid (1)' });
		expect(invalid).toHaveTextContent(
			'The absolute pressure at the node is 2.325 kPa(a), below the vapor pressure (2.339 kPa(a)): the liquid would flash.'
		);

		// Not a boundary: the boundaries view lists the reservoir only.
		await openView('Boundaries');
		const boundaries = results().getByRole('table', { name: 'Results per boundary' });
		expect(within(boundaries).getAllByRole('rowheader')).toHaveLength(1);
		expect(within(boundaries).getByRole('rowheader')).toHaveTextContent(/^Supply tank/);

		// Its trace: the flow as entered (input), and the row of its own table.
		await openView('Assigned flows');
		await fireEvent.click(results().getByRole('button', { name: /^Process user/ }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Process user' }));
		expect(dialog.getByText('Assigned flow (demand or supply) · AF1')).toBeInTheDocument();
		expect(dialog.getByRole('region', { name: 'Inputs' })).toHaveTextContent(
			/Assigned flow Q_a .* 12 L\/s \(0\.012 m³\/s\) User/
		);
		expect(dialog.getByRole('region', { name: 'Result values' })).toHaveTextContent(
			/Direction\s*Demand\s*Assigned flow \(L\/s\)\s*12\s*Elevation/
		);
		expect(ws.nav.current?.id).toBe('AF1');

		// Edited after the solve: the results still show the flow they were solved with.
		await fireEvent.click(dialog.getByRole('button', { name: 'Close' }));
		ws.editComponent('AF1', 'change assigned flow', (c) => {
			if (c.type === 'assigned_flow') c.flow = -0.02;
		});
		expect(await results().findByText(/Results are out of date/)).toBeInTheDocument();
		expect(cells(row)).toEqual(['Demand', '12', '2', '-99', '2.325', '-8.1']);
	});

	it('name a node that no reservoir reaches, with what closes it off, as links', async () => {
		// The API's message for a node cut off by a closed valve (solver/gga.py, status.py).
		const base = assignedFlowProject(0.012);
		const valve = { ...createComponent('gate', base), status: 'isolated' as const };
		const project = insertComponentInConnection(base, 'L1', valve);
		const message =
			"no reservoir or reference node reaches assigned-flow node 'AF1' (takes 0.012 m³/s out " +
			'of the network) through open elements, so no steady state carries that flow (an ' +
			'assigned-flow node fixes a flow, not a pressure; EPANET reports such a part as ' +
			"disconnected); closed around it: valve 'V1' (isolated)";
		const ws = await solveWith(
			assignedFlowSolved({
				converged: false,
				nodeResults: {},
				linkResults: {},
				boundaryResults: {},
				convergence: {
					innerIterations: 2,
					outerIterations: 1,
					maxContinuityResidual: { value: 0, elementId: 'V1:inlet' },
					maxEnergyResidual: { value: 0, elementId: 'L1' },
					oscillatingComponents: [],
					message
				},
				flags: [
					flag({
						code: 'NOT_CONVERGED',
						severity: 'invalid',
						message: `the solve did not converge: ${message}`
					})
				]
			}),
			project
		);
		expect(results().getByRole('heading', { name: 'Did not converge' })).toBeInTheDocument();
		expect(
			results().getByText(
				'No reservoir or reference node reaches assigned-flow node “Process user” (takes 12 L/s out of the network) through open elements, so no steady state carries that flow (an assigned-flow node fixes a flow, not a pressure; EPANET reports such a part as disconnected); closed around it: valve “Gate valve V1” (isolated)'
			)
		).toBeInTheDocument();
		const named = results().getByText('Named in the message:').closest('li')!;
		expect(
			within(named)
				.getAllByRole('button')
				.map((b) => b.textContent?.trim())
		).toEqual(['Process user', 'Gate valve V1']);
		await fireEvent.click(within(named).getByRole('button', { name: 'Gate valve V1' }));
		expect(await screen.findByRole('dialog', { name: 'Gate valve V1' })).toBeInTheDocument();
		expect(ws.nav.current?.id).toBe('V1');
		expect(results().queryByRole('tab', { name: 'Assigned flows' })).toBeNull();
	});
});
