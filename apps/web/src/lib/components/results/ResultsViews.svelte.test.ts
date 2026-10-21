/**
 * Results views after a solve: flags by severity, tables in display units with gauge/absolute
 * labels and inline flags, the not-converged report, the out-of-date banner, the method-version
 * notice, the trace view, expandable connections and the methods summary. The solve results are
 * made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
	MethodVersionsResponse,
	Project,
	SolvedState,
	SolveResponse,
	SystemCurveResponse
} from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import {
	flag,
	pumpResult,
	pumpTransferSolved,
	response,
	systemCurveResponse,
	SAMPLE_METHODS,
	SAMPLE_TRACE
} from '$lib/testing/results';
import { testWorkspace, type TestWorkspaceOptions } from '$lib/testing/workspace';
import { insertComponentInConnection } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';
import { methodsText } from '$lib/utils/trace';
import { IMPERIAL_UNITS } from '$lib/utils/units';

// Definitions (exact): 1 in = 0.0254 m; US gallon = 231 in³.
const IN = 0.0254;
const GPM = (231 * IN ** 3) / 60;
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

const results = () => within(screen.getByRole('region', { name: 'Results' }));

async function solveWith(
	solved: SolvedState,
	project: Project = pumpTransferExample(),
	options: TestWorkspaceOptions = {}
) {
	const solve = vi.fn(() => Promise.resolve(response(solved)));
	const ws = testWorkspace(project, { solver: { solve }, ...options });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
	await results().findByRole('heading', { name: /^(Converged|Did not converge)$/ });
	return { ws, solve };
}

async function openView(name: string) {
	await fireEvent.click(results().getByRole('tab', { name }));
}

/** The row of a table whose row header names `name` (e.g. a connection "from → to"). */
function rowFor(table: HTMLElement, name: string | RegExp): HTMLElement {
	return within(table)
		.getByRole('rowheader', { name: typeof name === 'string' ? new RegExp(`^${name}`) : name })
		.closest('tr') as HTMLElement;
}

/** The line under a row with its flag badges and details toggle. */
function rowNotes(row: HTMLElement): HTMLElement {
	return row.nextElementSibling as HTMLElement;
}

/** The text of each cell of a table row. */
function cells(row: HTMLElement): string[] {
	return within(row)
		.getAllByRole('cell')
		.map((c) => c.textContent?.replace(/\s+/g, ' ').trim() ?? '');
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('flags summary', () => {
	const flags = [
		flag({ code: 'TRANSITIONAL_FLOW', severity: 'info', message: 'Network-wide note' }),
		flag({
			code: 'CAVITATION',
			severity: 'invalid',
			message: 'The pump would cavitate',
			componentId: 'P1',
			portId: 'suction'
		}),
		flag({
			code: 'TRANSITIONAL_FLOW',
			severity: 'warning',
			message: 'Transitional flow in the discharge pipe',
			connectionId: 'L2'
		})
	];

	it('groups flags by severity, each with an icon and text', async () => {
		await solveWith(pumpTransferSolved({ flags }));
		const headings = results()
			.getAllByRole('heading', { level: 4 })
			.map((h) => h.textContent?.trim());
		expect(headings).toEqual(['Physically invalid (1)', 'Warnings (1)', 'Information (1)']);
		const invalid = results().getByRole('list', { name: 'Physically invalid (1)' });
		expect(within(invalid).getByText('The pump would cavitate')).toBeInTheDocument();
		expect(invalid.parentElement?.querySelector('svg')).not.toBeNull();
		// A network-wide flag has no element to link to.
		const info = results().getByRole('list', { name: 'Information (1)' });
		expect(within(info).queryByRole('button')).toBeNull();
	});

	it('opens the flagged element and points the navigator at it', async () => {
		const { ws } = await solveWith(pumpTransferSolved({ flags }));
		ws.pane = 'results';
		await fireEvent.click(
			results().getByRole('button', { name: 'Show Transfer pump: The pump would cavitate' })
		);
		const dialog = await screen.findByRole('dialog', { name: 'Transfer pump' });
		expect(within(dialog).getByText(/The pump would cavitate/)).toBeInTheDocument();
		expect(ws.nav.current?.id).toBe('P1');
		expect(ws.nav.path).toEqual([{ componentId: 'P1' }]);
		expect(ws.pane).toBe('results');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
		expect(screen.queryByRole('dialog')).toBeNull();

		// A connection's flag opens the connection and its piping in the navigator.
		await fireEvent.click(
			results().getByRole('button', {
				name: 'Show Transfer pump → Discharge isolation valve: Transitional flow in the discharge pipe'
			})
		);
		expect(
			await screen.findByRole('dialog', { name: 'Transfer pump → Discharge isolation valve' })
		).toBeInTheDocument();
		expect(ws.nav.current?.id).toBe('P1');
		expect(ws.nav.mode).toBe('connection');
		expect(ws.nav.activeConnection?.id).toBe('L2');
	});
});

describe('tables', () => {
	it('shows links in the project’s display units, with names and inline flags', async () => {
		const project = pumpTransferExample();
		project.settings.units = { ...IMPERIAL_UNITS };
		await solveWith(
			pumpTransferSolved({
				flags: [
					flag({
						code: 'TRANSITIONAL_FLOW',
						severity: 'warning',
						message: 'Transitional',
						connectionId: 'L3'
					})
				]
			}),
			project
		);
		await openView('Links');
		const table = results().getByRole('table', { name: 'Results per pipe connection' });
		expect(within(table).getByRole('columnheader', { name: 'Flow gpm' })).toBeInTheDocument();
		expect(within(table).getByRole('columnheader', { name: 'Velocity ft/s' })).toBeInTheDocument();
		const first = rowFor(table, 'Suction tank → Transfer pump');
		expect(within(table).getAllByRole('rowheader')[0]).toBe(within(first).getByRole('rowheader'));
		expect(cells(first)[0]).toBe(sig4(0.02 / GPM));
		const third = rowFor(table, 'Discharge isolation valve → Discharge tank');
		expect(within(rowNotes(third)).getByText('Warning')).toBeInTheDocument();
		expect(within(rowNotes(third)).getByText(': Transitional')).toHaveClass('sr-only');
		expect(within(rowNotes(first)).queryByText('Warning')).toBeNull();
		// The row header is the name and detail only: badges and toggles are on their own line.
		expect(within(third).getByRole('rowheader')).toHaveTextContent(
			/^Discharge isolation valve → Discharge tank\s*L3$/
		);
	});

	it('labels gauge and absolute pressures in the nodes table', async () => {
		await solveWith(pumpTransferSolved());
		await openView('Nodes');
		const table = results().getByRole('table', { name: 'Results per component port' });
		expect(
			within(table).getByRole('columnheader', { name: 'Pressure kPa(g)' })
		).toBeInTheDocument();
		expect(
			within(table).getByRole('columnheader', { name: 'Absolute pressure kPa(a)' })
		).toBeInTheDocument();
		const discharge = rowFor(table, /^Transfer pump\s*Discharge$/);
		expect(within(discharge).getByRole('rowheader')).toHaveTextContent('Transfer pump Discharge');
		expect(
			within(table).getByRole('columnheader', { name: 'Dynamic pressure kPa' })
		).toBeInTheDocument();
		expect(
			within(table).getByRole('columnheader', { name: 'Total pressure kPa(g)' })
		).toBeInTheDocument();
		// Elevation, pressure (gauge) and absolute pressure; dynamic and total sit between.
		const values = cells(discharge);
		expect([values[0], values[1], values[4]]).toEqual(['0', '100', '201.3']);
	});

	it('marks pressures psig and psia in US units', async () => {
		const project = pumpTransferExample();
		project.settings.units = { ...IMPERIAL_UNITS };
		await solveWith(pumpTransferSolved(), project);
		await openView('Nodes');
		const table = results().getByRole('table', { name: 'Results per component port' });
		expect(within(table).getByRole('columnheader', { name: 'Pressure psig' })).toBeInTheDocument();
		expect(
			within(table).getByRole('columnheader', { name: 'Absolute pressure psia' })
		).toBeInTheDocument();
	});

	it('expands a connection to its pipes and fittings, with K and its source', async () => {
		await solveWith(pumpTransferSolved());
		await openView('Links');
		const toggle = results().getByRole('button', {
			name: 'Pipes and fittings: Suction tank → Transfer pump'
		});
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		const pipe = results().getByRole('region', { name: 'Pipe 1 of Suction tank → Transfer pump' });
		expect(within(pipe).getByText('Inner diameter (mm)').nextElementSibling).toHaveTextContent(
			'100'
		);
		const fittings = results().getByRole('region', {
			name: 'Fittings of Suction tank → Transfer pump'
		});
		expect(within(fittings).getByText('Entrance, sharp-edged')).toBeInTheDocument();
		expect(within(fittings).getByText('K (each)').nextElementSibling).toHaveTextContent('0.5');
		expect(within(fittings).getByText(/Made-up source for tests/)).toBeInTheDocument();
	});

	it('switches views with the arrow keys and hides views without results', async () => {
		await solveWith(pumpTransferSolved());
		expect(results().queryByRole('tab', { name: 'Branches' })).toBeNull();
		const summary = results().getByRole('tab', { name: 'Summary' });
		summary.focus();
		await fireEvent.keyDown(summary, { key: 'ArrowRight' });
		const nodes = results().getByRole('tab', { name: 'Nodes' });
		expect(nodes).toHaveAttribute('aria-selected', 'true');
		expect(document.activeElement).toBe(nodes);
		await fireEvent.keyDown(nodes, { key: 'End' });
		expect(results().getByRole('tab', { name: 'Methods' })).toHaveAttribute(
			'aria-selected',
			'true'
		);
	});

	it('summarises the fluid properties used, with absolute vapor pressure', async () => {
		await solveWith(pumpTransferSolved());
		expect(results().getByRole('heading', { name: 'Fluid: Water' })).toBeInTheDocument();
		expect(results().getByText('2.339 kPa(a)')).toBeInTheDocument();
		expect(results().getByText('101.3 kPa(a)')).toBeInTheDocument();
		expect(results().getByText('Made-up citation for tests (density).')).toBeInTheDocument();
	});
});

describe('solve status', () => {
	it('reports a solve that did not converge: where, and what kept switching', async () => {
		const { ws } = await solveWith(
			pumpTransferSolved({
				converged: false,
				convergence: {
					innerIterations: 100,
					outerIterations: 30,
					message: 'Status iterations did not settle',
					oscillatingComponents: ['V1'],
					maxContinuityResidual: { value: 0.001, elementId: 'P1:suction' },
					maxEnergyResidual: { value: 0.02, elementId: 'L3' }
				}
			})
		);
		ws.pane = 'results';
		expect(results().getByRole('heading', { name: 'Did not converge' })).toBeInTheDocument();
		expect(results().getByText('Status iterations did not settle')).toBeInTheDocument();
		expect(results().getByText(/not a solution of the network/)).toBeInTheDocument();
		expect(results().getByText(/Largest continuity error: 1 L\/s/)).toBeInTheDocument();
		expect(results().getByRole('button', { name: 'Suction of Transfer pump' })).toBeInTheDocument();
		expect(
			results().getByRole('button', { name: 'Discharge isolation valve → Discharge tank' })
		).toBeInTheDocument();
		expect(results().getByRole('status')).toHaveTextContent('Last solve: did not converge');
		await fireEvent.click(results().getByRole('button', { name: 'Discharge isolation valve' }));
		expect(
			await screen.findByRole('dialog', { name: 'Discharge isolation valve' })
		).toBeInTheDocument();
		expect(ws.nav.current?.id).toBe('V1');
	});

	it('says the results are out of date after an edit, and solves again', async () => {
		const { ws, solve } = await solveWith(pumpTransferSolved());
		expect(results().queryByText(/Results are out of date/)).toBeNull();
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		expect(await results().findByText(/Results are out of date/)).toBeInTheDocument();
		expect(results().getByRole('status')).toHaveTextContent('Last solve: converged, out of date');
		await fireEvent.click(results().getByRole('button', { name: 'Solve again' }));
		expect(solve).toHaveBeenCalledTimes(2);
		await vi.waitFor(() => expect(results().queryByText(/Results are out of date/)).toBeNull());
	});
});

describe('method-version notice', () => {
	const changelog: MethodVersionsResponse = {
		current: '1.1.0',
		versions: [
			{ version: '1.0.0', date: '2026-10-21', changes: ['First release.'] },
			{ version: '1.1.0', date: '2026-11-02', changes: ['Made-up change for tests.'] }
		]
	};

	function sharedProject(version: string): Project {
		return { ...pumpTransferExample(), methodVersion: version };
	}

	it('shows what changed when the link was solved with another version', async () => {
		const methodVersions = vi.fn(() => Promise.resolve(changelog));
		await solveWith(pumpTransferSolved({ methodVersion: '1.1.0' }), sharedProject('1.0.0'), {
			library: { methodVersions }
		});
		expect(
			results().getByRole('heading', { name: 'Calculation methods changed' })
		).toBeInTheDocument();
		expect(
			results().getByText(/last solved with calculation methods version 1\.0\.0/)
		).toBeInTheDocument();
		expect(await results().findByText('Version 1.1.0 (2026-11-02)')).toBeInTheDocument();
		expect(results().getByText('Made-up change for tests.')).toBeInTheDocument();
		expect(results().queryByText('First release.')).toBeNull();
		expect(methodVersions).toHaveBeenCalledTimes(1);
	});

	it('offers to try again when the changelog cannot be loaded', async () => {
		await solveWith(pumpTransferSolved({ methodVersion: '1.1.0' }), sharedProject('1.0.0'));
		expect(
			await results().findByText(/The list of changes could not be loaded/)
		).toBeInTheDocument();
		expect(results().getByRole('button', { name: 'Try again' })).toBeInTheDocument();
	});

	it('is not shown for the same version, or for a project never solved', async () => {
		await solveWith(pumpTransferSolved({ methodVersion: '1.0.0' }), sharedProject('1.0.0'));
		expect(results().queryByText('Calculation methods changed')).toBeNull();
	});

	it('is not shown for a project that was never solved', async () => {
		await solveWith(pumpTransferSolved({ methodVersion: '1.0.0' }), sharedProject(''));
		expect(results().queryByText('Calculation methods changed')).toBeNull();
	});
});

describe('trace view', () => {
	it('shows inputs with sources, equations, references, values in display units and notes', async () => {
		const project = pumpTransferExample();
		project.settings.units = { ...IMPERIAL_UNITS };
		const { ws } = await solveWith(
			pumpTransferSolved({
				trace: { elements: { L1: SAMPLE_TRACE }, methods: SAMPLE_METHODS },
				flags: [
					flag({
						code: 'TRANSITIONAL_FLOW',
						severity: 'info',
						message: 'Made-up info',
						connectionId: 'L1'
					})
				]
			}),
			project
		);
		await openView('Links');
		await fireEvent.click(results().getByRole('button', { name: /^Suction tank → Transfer pump/ }));
		const dialog = within(
			await screen.findByRole('dialog', { name: 'Suction tank → Transfer pump' })
		);
		expect(dialog.getByText('Pipe connection · L1')).toBeInTheDocument();

		const inputs = dialog.getByRole('region', { name: 'Inputs' });
		const items = within(inputs).getAllByRole('listitem');
		expect(items.map((li) => li.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			`Length ${sig4(5 / 0.3048)} ft (5 m) User`,
			`Inner diameter ${sig4(0.1023 / IN)} in (0.1023 m) Library`,
			'Friction method colebrook Default',
			`Flow ${sig4(0.02 / GPM)} gpm (0.02 m³/s) Computed`
		]);
		expect(dialog.getByText('h_f = f (L/D) v²/(2g)')).toBeInTheDocument();
		const correlations = dialog.getByRole('region', { name: 'Correlations' });
		expect(within(correlations).getByText('Colebrook (1939)')).toBeInTheDocument();
		expect(
			within(correlations).getByText('Colebrook, C. F. J. ICE 11(4), 1939.')
		).toBeInTheDocument();
		const sources = dialog.getByRole('region', { name: 'Data sources' });
		expect(within(sources).getByText('ASME B36.10M-2018, Table 1.')).toBeInTheDocument();
		const intermediates = dialog.getByRole('region', { name: 'Intermediate values' });
		expect(within(intermediates).getByText('Velocity').nextElementSibling).toHaveTextContent(
			`${sig4(2.5 / 0.3048)} ft/s (2.5 m/s)`
		);
		expect(
			within(intermediates).getByText('Wall shear stress').nextElementSibling
		).toHaveTextContent('3.2 N/m²');
		expect(dialog.getByText('Made-up trace for tests.')).toBeInTheDocument();
		expect(dialog.getByRole('region', { name: 'Flags (1)' })).toHaveTextContent(
			'Info: Made-up info'
		);
		expect(dialog.getByRole('region', { name: 'Result values' })).toHaveTextContent('Flow (gpm)');

		// The navigator shows the connection's piping from its 'from' end.
		expect(ws.nav.current?.id).toBe('R1');
		expect(ws.nav.activeConnection?.id).toBe('L1');
		await fireEvent.click(dialog.getByRole('button', { name: 'Show in Build' }));
		expect(ws.pane).toBe('build');
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('says so when the solve returned no trace for the element', async () => {
		await solveWith(pumpTransferSolved());
		await openView('Pumps');
		await fireEvent.click(results().getByRole('button', { name: /^Transfer pump/ }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Transfer pump' }));
		expect(dialog.getByText(/did not return a calculation trace/)).toBeInTheDocument();
		expect(dialog.getByRole('region', { name: 'Result values' })).toHaveTextContent('Running');
	});
});

describe('methods summary', () => {
	it('lists the methods and copies them as text', async () => {
		const writeText = vi.fn(() => Promise.resolve());
		vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
		await solveWith(pumpTransferSolved());
		await openView('Methods');
		const article = within(
			results().getByRole('article', { name: 'Calculation methods and assumptions' })
		);
		expect(article.getByRole('heading', { name: 'Pipe friction' })).toBeInTheDocument();
		expect(article.getByText('Colebrook, C. F. (1939).')).toBeInTheDocument();
		expect(article.getByText('Steady, incompressible flow.')).toBeInTheDocument();
		expect(article.getByText('fluids')).toBeInTheDocument();
		await fireEvent.click(article.getByRole('button', { name: 'Copy as text' }));
		await vi.waitFor(() => expect(article.getByRole('status')).toHaveTextContent('Copied'));
		expect(writeText).toHaveBeenCalledWith(
			methodsText(SAMPLE_METHODS, {
				projectName: 'Pump transfer between two tanks',
				timestamp: '2026-10-21T00:00:00Z',
				converged: true,
				stale: false
			})
		);
	});

	it('shows the text to copy by hand without clipboard access', async () => {
		vi.stubGlobal('navigator', { ...navigator, clipboard: undefined });
		await solveWith(pumpTransferSolved());
		await openView('Methods');
		await fireEvent.click(results().getByRole('button', { name: 'Copy as text' }));
		const area = await results().findByRole('textbox', { name: 'Methods as text' });
		expect((area as HTMLTextAreaElement).value).toContain('Pipe friction\n- Darcy–Weisbach');
	});
});

describe('pump chart: the system curve on demand (D10)', () => {
	/** A fake system-curve endpoint whose answers the test releases one by one. */
	function curveEndpoint() {
		const answers: ((curve: SystemCurveResponse) => void)[] = [];
		const systemCurve = vi.fn<
			(
				project: Project,
				pumpId: string,
				options?: { signal?: AbortSignal }
			) => Promise<SystemCurveResponse>
		>(() => new Promise<SystemCurveResponse>((resolve) => answers.push(resolve)));
		return { systemCurve, answers };
	}

	async function solveAndOpenPumps(project: Project, solved: SolvedState) {
		const solve = vi.fn<(project: Project) => Promise<SolveResponse>>(() =>
			Promise.resolve(response(solved))
		);
		const { systemCurve, answers } = curveEndpoint();
		const ws = testWorkspace(project, { solver: { solve, systemCurve } });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await results().findByRole('heading', { name: 'Converged' });
		// Nothing is computed until a pump chart is shown.
		expect(systemCurve).not.toHaveBeenCalled();
		await openView('Pumps');
		const panel = within(results().getByRole('tabpanel', { name: 'Pumps' }));
		return { ws, solve, systemCurve, answers, panel };
	}

	it('fetches the curve of the pump shown for the project as solved, once per solve', async () => {
		const { ws, solve, systemCurve, answers, panel } = await solveAndOpenPumps(
			pumpTransferExample(),
			pumpTransferSolved()
		);
		expect(panel.getByText('Computing the system curve for this solve…')).toBeInTheDocument();
		await vi.waitFor(() => expect(systemCurve).toHaveBeenCalledTimes(1));
		const [project, pumpId] = systemCurve.mock.calls[0]!;
		expect(project).toBe(solve.mock.calls[0]![0]);
		expect(pumpId).toBe('P1');
		answers[0]!(systemCurveResponse('P1'));
		// jsdom has no canvas, so the data tables are shown.
		const table = await panel.findByRole('table', { name: 'System curve' });
		expect(within(table).getAllByRole('row')).toHaveLength(5);
		expect(panel.queryByText(/Computing the system curve/)).toBeNull();
		// Cached with the solve: another view and back sends nothing.
		await openView('Links');
		await openView('Pumps');
		expect(systemCurve).toHaveBeenCalledTimes(1);
		// An edit makes the results stale, not the curve another project's: it stays the solve's.
		ws.edit((p) => {
			p.connections[0]!.piping.pipes[0]!.length += 5;
		}, 'change length');
		expect(ws.store.results.stale).toBe(true);
		expect(panel.getByRole('table', { name: 'System curve' })).toBeInTheDocument();
		expect(systemCurve).toHaveBeenCalledTimes(1);
	});

	it('shows one pump at a time, chosen from the solved pumps', async () => {
		const base = pumpTransferExample();
		const booster = createComponent('pump', base, { name: 'Booster pump' });
		const project = insertComponentInConnection(base, 'L3', booster);
		const solved = pumpTransferSolved({
			pumpResults: {
				P1: pumpResult(),
				[booster.id]: pumpResult({ operatingFlow: 0.01, operatingHead: 28 })
			}
		});
		const { systemCurve, answers, panel } = await solveAndOpenPumps(project, solved);
		const picker = panel.getByRole('combobox', { name: 'Pump chart' });
		expect(
			within(picker)
				.getAllByRole('option')
				.map((o) => o.textContent)
		).toEqual(['Transfer pump', 'Booster pump']);
		expect(panel.getAllByRole('figure')).toHaveLength(1);
		expect(
			panel.getByRole('figure', { name: 'Pump and system curves: Transfer pump' })
		).toBeVisible();
		await vi.waitFor(() => expect(systemCurve).toHaveBeenCalledTimes(1));
		answers[0]!(systemCurveResponse('P1'));
		await panel.findByRole('table', { name: 'System curve' });
		await fireEvent.change(picker, { target: { value: booster.id } });
		expect(
			panel.getByRole('figure', { name: 'Pump and system curves: Booster pump' })
		).toBeInTheDocument();
		await vi.waitFor(() => expect(systemCurve).toHaveBeenCalledTimes(2));
		expect(systemCurve.mock.calls[1]![1]).toBe(booster.id);
		expect(panel.getByText('Computing the system curve for this solve…')).toBeInTheDocument();
		// Back to the first pump: its curve is cached.
		await fireEvent.change(picker, { target: { value: 'P1' } });
		expect(await panel.findByRole('table', { name: 'System curve' })).toBeInTheDocument();
		expect(systemCurve).toHaveBeenCalledTimes(2);
	});
});
