/**
 * The convergence report of a solve whose iteration diverged (CLAUDE.md D7, TSD §12 item 19): the
 * elements whose laws gave a value that is not a finite number, from the NOT_CONVERGED flag's
 * `nonFiniteLawAt`, each a link, a pipe connection named by its piping ("Tank → Pump"), then the
 * other elements the message names. An energy balance that is not a finite number
 * (`nonFiniteBalanceAt`) and a weight lost in rounding in the Newton step (`singularStepAt`) are
 * listed under words of their own, never as a law (method 1.6.2). The solve results are made-up
 * test inputs shaped like the API's (apps/api solver/gga.py diverged_message, balance_message,
 * singular_message, solver/results.py; the messages as the real solver printed them for
 * tests/unit/test_nonfinite_laws.py, test_boundary_head.py and test_singular_step.py, with this
 * project's ids); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Project, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';

const results = () => within(screen.getByRole('region', { name: 'Results' }));

async function solveWith(solved: SolvedState, project: Project = pumpTransferExample()) {
	const solve = vi.fn(() => Promise.resolve(response(solved)));
	const ws = testWorkspace(project, { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
	await results().findByRole('heading', { name: /^(Converged|Did not converge)$/ });
	return ws;
}

/** A solve that diverged with `message`; the flag's details as the API gives them. */
function diverged(message: string, details: Record<string, string | number>): SolvedState {
	return pumpTransferSolved({
		converged: false,
		nodeResults: {},
		linkResults: {},
		pumpResults: {},
		valveResults: {},
		boundaryResults: {},
		convergence: {
			innerIterations: 1,
			outerIterations: 1,
			maxContinuityResidual: { value: 2.0092572467351805e288, elementId: 'P1:suction' },
			maxEnergyResidual: { value: null, elementId: 'L1' },
			oscillatingComponents: [],
			message
		},
		flags: [
			flag({
				code: 'NOT_CONVERGED',
				severity: 'invalid',
				message: `the solve did not converge: ${message}`,
				details
			})
		]
	});
}

/** The texts of the links in the report's item that `label` starts. */
function linksUnder(label: string | RegExp): string[] {
	const item = results().getByText(label).closest('li')!;
	return within(item)
		.getAllByRole('button')
		.map((b) => b.textContent?.trim() ?? '');
}

const PIPES =
	"the iteration diverged (non-finite head loss): not a finite number in the laws of 'L1' " +
	"(head loss at a flow of 4.09e+300 m³/s) and 'L2' (head loss at a flow of 4.09e+300 m³/s)";

describe('a solve whose iteration diverged', () => {
	it('names the pipe connections whose laws were not finite by their piping, as links', async () => {
		const ws = await solveWith(
			diverged(PIPES, {
				maxEnergyResidualAt: 'L1',
				nonFiniteLawAt: 'L1, L2',
				nonFiniteLawFlow: 4.090000166935048e300
			})
		);
		expect(results().getByRole('heading', { name: 'Did not converge' })).toBeInTheDocument();
		expect(
			results().getByText(
				'The iteration diverged (non-finite head loss): not a finite number in the laws of ' +
					'“Suction tank → Transfer pump” (head loss at a flow of 4.09×10³⁰³ L/s) and ' +
					'“Transfer pump → Discharge isolation valve” (head loss at a flow of 4.09×10³⁰³ L/s)'
			)
		).toBeInTheDocument();
		expect(linksUnder('Not a finite number in the laws of:')).toEqual([
			'Suction tank → Transfer pump',
			'Transfer pump → Discharge isolation valve'
		]);
		// They are the elements the message names: no second list repeats them.
		expect(results().queryByText(/named in the message:/i)).toBeNull();
		const item = results().getByText('Not a finite number in the laws of:').closest('li')!;
		await fireEvent.click(
			within(item).getByRole('button', { name: 'Suction tank → Transfer pump' })
		);
		expect(ws.inspected).toEqual({ kind: 'connection', id: 'L1' });
		expect(
			await screen.findByRole('dialog', { name: 'Suction tank → Transfer pump' })
		).toBeInTheDocument();
	});

	it('names one component in the singular, and links the other elements the message names', async () => {
		// The API's message for one law (diverged_message), after a made-up note that names a
		// closed valve, as the outer loop's notes name elements.
		const message =
			"closed: valve 'V1' (isolated); the iteration diverged (non-finite head loss): not a " +
			"finite number in the law of 'P1' (slope dh/dQ at a flow of 0.00239 m³/s; loss " +
			"coefficient c = 1.7e+308 s²/m⁵), next to 'L2'";
		const ws = await solveWith(
			diverged(message, {
				nonFiniteLawAt: 'P1',
				nonFiniteLawFlow: 0.00239,
				nonFiniteLawCoefficient: 1.7e308
			})
		);
		expect(linksUnder('Not a finite number in the law of:')).toEqual(['Transfer pump']);
		expect(linksUnder('Also named in the message:')).toEqual([
			'Discharge isolation valve',
			'Transfer pump → Discharge isolation valve'
		]);
		const also = results().getByText('Also named in the message:').closest('li')!;
		await fireEvent.click(
			within(also).getByRole('button', { name: 'Transfer pump → Discharge isolation valve' })
		);
		expect(ws.inspected).toEqual({ kind: 'connection', id: 'L2' });
	});

	it('links the connections a message names when the flag lists no law', async () => {
		// A message in this form without the details (a solve that did not diverge names its
		// elements too): every element it names, components and connections, under one heading.
		await solveWith(diverged(PIPES, {}));
		expect(results().queryByText(/^Not a finite number/)).toBeNull();
		expect(linksUnder('Named in the message:')).toEqual([
			'Suction tank → Transfer pump',
			'Transfer pump → Discharge isolation valve'
		]);
	});

	it('shows an id the project no longer has as text', async () => {
		// The project changed after the solve: L9 was removed (made-up id).
		await solveWith(diverged(PIPES.replace("'L2'", "'L9'"), { nonFiniteLawAt: 'L1, L9' }));
		const item = results().getByText('Not a finite number in the laws of:').closest('li')!;
		expect(
			within(item)
				.getAllByRole('button')
				.map((b) => b.textContent?.trim())
		).toEqual(['Suction tank → Transfer pump']);
		expect(within(item).getByText('L9')).toBeInTheDocument();
	});
});

describe('a solve whose energy balance overflowed, or whose Newton step lost a weight', () => {
	it('lists the connection under the energy balance and the reservoir as also named', async () => {
		const message =
			'the iteration diverged (non-finite energy balance): not a finite number in the energy ' +
			"balance h − (H_start − H_end) of 'L1' (an EGL of -1.79769e+308 m at its start, fixed by " +
			"'R1', and of 0 m at its end, with a head loss of 1.7534e+304 m at a flow of 0.00239 m³/s)";
		await solveWith(
			diverged(message, {
				maxContinuityResidualAt: 'P1:suction',
				maxEnergyResidualAt: 'L1',
				nonFiniteBalanceAt: 'L1'
			})
		);
		expect(linksUnder('Not a finite number in the energy balance of:')).toEqual([
			'Suction tank → Transfer pump'
		]);
		expect(linksUnder('Also named in the message:')).toEqual(['Suction tank']);
		// Its law is finite: never under the law's words.
		expect(results().queryByText(/^Not a finite number in the laws? of:$/)).toBeNull();
		// The message names the reservoir that fixes the head it overflows from.
		const report = within(results().getByRole('region', { name: 'Did not converge' }));
		expect(report.getByText(/fixed by “Suction tank”/)).toBeInTheDocument();
	});

	it('lists the element whose weight was lost under its own words, as a link', async () => {
		const message =
			'the linear system could not be solved (singular matrix): in Newton iteration 1, at the ' +
			"starting flows, the weight 1/(dh/dQ) of 'V1' (a slope of 8.46e+17 s/m² at a flow of " +
			'0.00239 m³/s; loss coefficient K/(2 g A²) = 1.76758e+20 s²/m⁵) is lost in rounding: ' +
			'added to the weights of the other links at its end beyond it, it leaves their sum ' +
			'unchanged, so the network beyond it, which reaches a reservoir or reference node only ' +
			'through it, has no fixed head in the Newton step';
		const ws = await solveWith(
			diverged(message, {
				maxEnergyResidualAt: 'V1',
				singularStepAt: 'V1',
				singularStepFlow: 0.002393893602035422,
				singularStepSlope: 8.462810398359405e17,
				singularStepCoefficient: 1.7675828180425084e20
			})
		);
		expect(linksUnder('Lost in rounding in the Newton step:')).toEqual([
			'Discharge isolation valve'
		]);
		// The only element the message names: no second list repeats it, and no law's list.
		expect(results().queryByText(/named in the message:/i)).toBeNull();
		expect(results().queryByText(/^Not a finite number/)).toBeNull();
		const item = results().getByText('Lost in rounding in the Newton step:').closest('li')!;
		await fireEvent.click(within(item).getByRole('button', { name: 'Discharge isolation valve' }));
		expect(ws.inspected).toEqual({ kind: 'component', id: 'V1' });
	});
});
