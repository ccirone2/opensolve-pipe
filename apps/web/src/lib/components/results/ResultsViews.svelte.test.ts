/**
 * Results views after a solve: flags by severity, tables in display units with gauge/absolute
 * labels and inline flags, the not-converged report, the out-of-date banner, the method-version
 * notice, the trace view, expandable connections and the methods summary. The solve results are
 * made-up test inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
	MethodVersionsResponse,
	Project,
	Pump,
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
import { outOfSight } from '$lib/testing/helpers';
import { testWorkspace, type TestWorkspaceOptions } from '$lib/testing/workspace';
import { insertComponentInConnection } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';
import { withScenarios } from '$lib/utils/scenarios';
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
		// Along the walk from its start, so Previous and Next name the pump's neighbours.
		expect(ws.nav.path).toEqual([
			{ componentId: 'R1' },
			{ componentId: 'P1', viaConnectionId: 'L1' }
		]);
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

	it('is the shared sideways row: ring room that moves no layout, the wheel, and a row-only keep-in-view (pumps-results-layout.md §5.4)', async () => {
		await solveWith(pumpTransferSolved());
		const row = results().getByRole('tablist', { name: 'Results view' });
		// py-1 keeps a focused pill's ring inside the box that clips; -my-1, in a flow root, keeps
		// the row where it was.
		expect(row).toHaveClass('scroll-shadow-x', 'overflow-x-auto', 'py-1', '-my-1');
		// Positioned: hidden words of a pill scrolled out of sight stay inside its clip.
		expect(row).toHaveClass('relative');
		expect(row.parentElement).toHaveClass('flow-root');
		// Boxes, as a 300 px row holding pills 100 px wide, 6 px apart from its 12 px padding.
		const tabs = within(row).getAllByRole('tab');
		Object.defineProperty(row, 'clientWidth', { configurable: true, value: 300 });
		Object.defineProperty(row, 'scrollWidth', {
			configurable: true,
			value: 12 + 106 * tabs.length
		});
		const at = new Map<Element, number>(tabs.map((t, i) => [t, 12 + 106 * i]));
		const boxes = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
			this: Element
		) {
			const left = this === row ? row.scrollLeft : (at.get(this) ?? 0);
			const width = this === row ? 300 : at.has(this) ? 100 : 0;
			return { left, right: left + width, width, top: 0, bottom: 44, height: 44 } as DOMRect;
		});
		row.style.paddingLeft = '12px';
		row.style.paddingRight = '12px';
		// The wheel scrolls it sideways while it can move, and takes the event from the pane.
		const wheel = new WheelEvent('wheel', { deltaY: 40, bubbles: true, cancelable: true });
		row.dispatchEvent(wheel);
		expect(wheel.defaultPrevented).toBe(true);
		expect(row.scrollLeft).toBe(40);
		row.scrollLeft = 0;
		// A view chosen far along: the row alone scrolls, to show it and the one after it, never
		// an ancestor (scrollIntoView would move the pane).
		const scrollTo = vi.fn();
		row.scrollTo = scrollTo as unknown as typeof row.scrollTo;
		const intoView = vi.fn();
		HTMLElement.prototype.scrollIntoView = intoView;
		try {
			expect(tabs.length).toBeGreaterThan(4);
			const fourth = tabs[3]!;
			await fireEvent.click(fourth);
			expect(fourth).toHaveAttribute('aria-selected', 'true');
			// The fifth pill ends at 12 + 106 × 4 + 100 = 536; with the 12 px end padding in view,
			// the row scrolls to 548 − 300 = 248.
			expect(scrollTo).toHaveBeenLastCalledWith({ left: 248, behavior: 'smooth' });
			expect(intoView).not.toHaveBeenCalled();
		} finally {
			delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
			boxes.mockRestore();
		}
	});

	it('keeps the chosen view in view when the row is drawn again: Compare cases and back (pumps-results-layout.md §5.4 One shared component)', async () => {
		const project = withScenarios(pumpTransferExample(), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const ws = testWorkspace(project, {
			solver: { solve: () => Promise.resolve(response(pumpTransferSolved())) }
		});
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		await results().findByRole('heading', { name: 'Converged' });
		const isRow = (e: Element) => e.matches('[role="tablist"][aria-label="Results view"]');
		const pillsOf = (e: Element) => [...(e.parentElement?.children ?? [])].indexOf(e);
		// Boxes for whichever row is drawn: 300 px wide, holding pills 100 px wide, 106 px apart
		// from 12 px (jsdom's row has no padding of its own).
		const count = within(results().getByRole('tablist', { name: 'Results view' })).getAllByRole(
			'tab'
		).length;
		expect(count).toBeGreaterThan(4);
		const spies = [
			vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(function (
				this: Element
			) {
				return isRow(this) ? 300 : 0;
			}),
			vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(function (
				this: Element
			) {
				return isRow(this) ? 12 + 106 * count : 0;
			}),
			vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
				this: Element
			) {
				const inRow = this.parentElement && isRow(this.parentElement);
				const left = isRow(this) ? this.scrollLeft : inRow ? 12 + 106 * pillsOf(this) : 0;
				const width = isRow(this) ? 300 : inRow ? 100 : 0;
				return { left, right: left + width, width, top: 0, bottom: 44, height: 44 } as DOMRect;
			})
		];
		const scrollTo = vi.fn();
		(Element.prototype as { scrollTo?: unknown }).scrollTo = scrollTo;
		try {
			const first = results().getByRole('tablist', { name: 'Results view' });
			await fireEvent.click(within(first).getAllByRole('tab')[3]!);
			// The fourth and fifth pills in view: 12 + 106 × 4 + 100 = 536, less the 300 px seen.
			expect(scrollTo).toHaveBeenLastCalledWith({ left: 236, behavior: 'smooth' });
			expect(scrollTo.mock.contexts.at(-1)).toBe(first);
			// Compare cases draws no view row; back on the case, the row drawn again keeps the
			// chosen view in view, as the row it replaced did.
			await fireEvent.click(results().getByRole('tab', { name: 'Compare cases' }));
			expect(results().queryByRole('tablist', { name: 'Results view' })).toBeNull();
			await fireEvent.click(results().getByRole('tab', { name: 'Base case' }));
			await tick();
			const again = results().getByRole('tablist', { name: 'Results view' });
			expect(again).not.toBe(first);
			expect(within(again).getAllByRole('tab')[3]).toHaveAttribute('aria-selected', 'true');
			expect(scrollTo.mock.contexts.at(-1)).toBe(again);
			expect(scrollTo).toHaveBeenLastCalledWith({ left: 236, behavior: 'smooth' });
		} finally {
			delete (Element.prototype as { scrollTo?: unknown }).scrollTo;
			for (const spy of spies) spy.mockRestore();
		}
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
		// The tab opened, the chart's line is drawn empty first, then speaks (pumps-results-layout.md
		// §7 Live regions, F17): inserted already holding its words, it would not be announced.
		const line = panel.getByRole('figure').querySelector('[data-pump-strip] [aria-live]')!;
		expect(line.textContent).toBe('');
		expect(await panel.findByText('Computing the system curve for this solve…')).toBe(line);
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

	it('heads the table "Results per pump", visibly, its caption kept (pumps-results-layout.md §5.3)', async () => {
		const { panel } = await solveAndOpenPumps(pumpTransferExample(), pumpTransferSolved());
		const headings = panel.getAllByRole('heading');
		expect(headings.map((h) => [h.tagName, h.textContent!.trim()])).toEqual([
			['H3', 'Results per pump'],
			['H3', 'Pump chart']
		]);
		const heading = headings[0]!;
		expect(heading).toBeVisible();
		expect(heading).not.toHaveClass('sr-only');
		expect(heading).toHaveAttribute('tabindex', '-1');
		expect(heading).toHaveClass('text-base', 'font-semibold');
		// The table keeps its name from its visually hidden caption, and follows its heading.
		const table = panel.getByRole('table', { name: 'Results per pump' });
		expect(table.querySelector('caption')).toHaveClass('sr-only');
		expect(heading.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		// Not a landmark: the tab gains no region for it.
		expect(heading.closest('section, [role="region"]')).toBe(
			screen.getByRole('region', { name: 'Results' })
		);
	});

	it("draws each pump's status as a pill holding its state word, tinted by the state, the qualifier after it as plain text and the cell's words the label's (docs/proposals/pumps-nits.md item 2)", async () => {
		// Made-up results: the transfer pump holds a flow setpoint (CLAUDE.md D11), booster A is
		// off and booster B gives no flow, the system head above its shutoff head.
		const base = pumpTransferExample();
		const a = createComponent('pump', base, { name: 'Booster pump A' });
		const withA = insertComponentInConnection(base, 'L3', a);
		const b = createComponent('pump', withA, { name: 'Booster pump B' });
		const project = insertComponentInConnection(withA, 'L4', b);
		(project.components.find((c) => c.id === 'P1') as Pump).control = {
			mode: 'flow',
			setpoint: 0.02,
			minSpeed: 0.4
		};
		const solved = pumpTransferSolved({
			pumpResults: {
				P1: pumpResult({
					speed: 0.873214,
					control: { mode: 'flow', setpoint: 0.02, state: 'active', setpointAchieved: true }
				}),
				[a.id]: pumpResult({ status: 'off', operatingFlow: 0, hydraulicPower: 0 }),
				[b.id]: pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 35 })
			},
			flags: [
				flag({
					code: 'PUMP_FLOW_REVERSAL',
					severity: 'invalid',
					message: 'made-up',
					componentId: b.id,
					details: { headRise: 35, shutoffHead: 30 }
				})
			]
		});
		const { panel } = await solveAndOpenPumps(project, solved);
		const table = panel.getByRole('table', { name: 'Results per pump' });
		const status = (name: string) =>
			within(rowFor(table, name))
				.getAllByRole('cell')
				.find((c) => c.dataset.label === 'Status')!;
		for (const [name, word, tone, label] of [
			[
				'Transfer pump',
				'Running',
				'bg-green-200 text-green-900',
				'Running (holding flow setpoint)'
			],
			['Booster pump A', 'Off', 'bg-slate-200 text-slate-700', 'Off'],
			[
				'Booster pump B',
				'No flow',
				'bg-red-200 text-red-950',
				'No flow (system head above shutoff)'
			]
		] as const) {
			const cell = status(name);
			const pills = cell.querySelectorAll('[data-status-pill]');
			expect(pills, name).toHaveLength(1);
			const pill = pills[0] as HTMLElement;
			// The state word alone in the pill; no icon, glyph or border (never a flag or a control).
			expect(pill.textContent, name).toBe(word);
			expect(pill.children, name).toHaveLength(0);
			expect(pill, name).toHaveClass(...tone.split(' '));
			expect(pill, name).toHaveClass(
				'inline-block',
				'align-top',
				'rounded-full',
				'px-2',
				'text-xs',
				'leading-5',
				'font-medium',
				'whitespace-nowrap'
			);
			expect(pill.className, name).not.toMatch(/\bborder\b|\bpy-/);
			// The cell's words are the label's, word for word: the export, Compare and the trace
			// read the same words, and a screen reader hears them as before.
			expect(cell.textContent!.trim(), name).toBe(label);
			// The qualifier follows the pill as plain text, inside one element with it, so a phone's
			// row wraps it after the pill.
			expect(pill.parentElement!.textContent, name).toBe(label);
			expect(pill.parentElement!.parentElement, name).toBe(cell);
			expect(pill.previousSibling, name).toBeNull();
		}
		// Every other cell as before: its text alone.
		expect(cells(rowFor(table, 'Transfer pump'))).toEqual(
			expect.arrayContaining(['Flow 20 L/s: held', '87.32'])
		);
		expect(table.querySelectorAll('[data-status-pill]')).toHaveLength(3);
	});

	it('cancels the curve being computed; computed again on request, it is shown', async () => {
		const { systemCurve, answers, panel } = await solveAndOpenPumps(
			pumpTransferExample(),
			pumpTransferSolved()
		);
		await vi.waitFor(() => expect(systemCurve).toHaveBeenCalledTimes(1));
		const signal = systemCurve.mock.calls[0]![2]?.signal;
		expect(signal?.aborted).toBe(false);
		const cancel = panel.getByRole('button', { name: 'Cancel the system curve' });
		cancel.focus();
		await fireEvent.click(cancel);
		await tick();
		expect(signal?.aborted).toBe(true);
		expect(panel.queryByText(/Computing the system curve/)).toBeNull();
		const again = panel.getByRole('button', { name: 'Compute the system curve' });
		expect(again).toHaveAccessibleDescription(
			'The system curve was not computed: you cancelled it.'
		);
		expect(document.activeElement).toBe(again);
		// Its answer arrives anyway: it is dropped.
		answers[0]!(systemCurveResponse('P1'));
		await vi.waitFor(() => expect(answers).toHaveLength(1));
		await tick();
		expect(panel.queryByRole('table', { name: 'System curve' })).toBeNull();
		// Another view and back: still cancelled, and nothing is sent until asked.
		await openView('Links');
		await openView('Pumps');
		expect(systemCurve).toHaveBeenCalledTimes(1);
		await fireEvent.click(panel.getByRole('button', { name: 'Compute the system curve' }));
		await vi.waitFor(() => expect(systemCurve).toHaveBeenCalledTimes(2));
		expect(systemCurve.mock.calls[1]![0]).toBe(systemCurve.mock.calls[0]![0]);
		answers[1]!(systemCurveResponse('P1'));
		expect(await panel.findByRole('table', { name: 'System curve' })).toBeInTheDocument();
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
		// Named by the chart's heading, beside it; its cost sentence visible and its description
		// (proposal pumps-results-layout.md §5.3 item 2).
		const heading = panel.getByRole('heading', { level: 3, name: 'Pump chart' });
		expect(heading).toHaveAttribute('tabindex', '-1');
		expect(picker).toHaveAttribute('aria-labelledby', heading.id);
		expect(picker.parentElement).toBe(heading.parentElement);
		const hint = panel.getByText(
			'The pump and system curves of one pump at a time; each system curve is computed when its pump is shown.'
		);
		expect(hint).toBeVisible();
		// Visible at every width: jsdom applies no CSS, so its markup says (§5.3 item 2, §6.4 item 8).
		expect(outOfSight(hint)).toBe(false);
		expect(picker).toHaveAccessibleDescription(hint.textContent!.replace(/\s+/g, ' ').trim());
		expect(panel.getAllByRole('figure')).toHaveLength(1);
		expect(
			panel.getByRole('figure', { name: 'Pump and system curves: Transfer pump' })
		).toBeVisible();
		await vi.waitFor(() => expect(systemCurve).toHaveBeenCalledTimes(1));
		answers[0]!(systemCurveResponse('P1'));
		await panel.findByRole('table', { name: 'System curve' });
		await fireEvent.change(picker, { target: { value: booster.id } });
		const boosterFigure = panel.getByRole('figure', {
			name: 'Pump and system curves: Booster pump'
		});
		// The new chart's line, too, is drawn empty before it speaks (§7 Live regions, F17).
		const line = boosterFigure.querySelector('[data-pump-strip] [aria-live]')!;
		expect(line.textContent).toBe('');
		await vi.waitFor(() => expect(systemCurve).toHaveBeenCalledTimes(2));
		expect(systemCurve.mock.calls[1]![1]).toBe(booster.id);
		expect(await panel.findByText('Computing the system curve for this solve…')).toBe(line);
		// Back to the first pump: its curve is cached.
		await fireEvent.change(picker, { target: { value: 'P1' } });
		expect(await panel.findByRole('table', { name: 'System curve' })).toBeInTheDocument();
		expect(systemCurve).toHaveBeenCalledTimes(2);
	});
	it('shows the control of speed-controlled pumps and how their system curves treat it', async () => {
		// Made-up results (CLAUDE.md D11): the transfer pump holds a flow setpoint at a solved
		// speed; a fixed-speed booster beside it.
		const base = pumpTransferExample();
		const booster = createComponent('pump', base, { name: 'Booster pump' });
		const project = insertComponentInConnection(base, 'L3', booster);
		(project.components.find((c) => c.id === 'P1') as Pump).control = {
			mode: 'flow',
			setpoint: 0.02,
			minSpeed: 0.4
		};
		const solved = pumpTransferSolved({
			pumpResults: {
				P1: pumpResult({
					speed: 0.873214,
					control: { mode: 'flow', setpoint: 0.02, state: 'active', setpointAchieved: true }
				}),
				[booster.id]: pumpResult({ operatingFlow: 0.02, operatingHead: 28 })
			}
		});
		const { answers, panel } = await solveAndOpenPumps(project, solved);
		const table = panel.getByRole('table', { name: 'Results per pump' });
		expect(within(table).getByRole('columnheader', { name: 'Control' })).toBeInTheDocument();
		const row = rowFor(table, 'Transfer pump');
		expect(cells(row)).toEqual(
			expect.arrayContaining(['Running (holding flow setpoint)', 'Flow 20 L/s: held', '87.32'])
		);
		expect(cells(rowFor(table, 'Booster pump'))).toEqual(
			expect.arrayContaining(['Running', 'Fixed speed', '100'])
		);
		const note = panel.getByText(/A speed-controlled pump's speed is the one it runs at/);
		expect(note).toBeVisible();
		// One sentence after another, with a space between them.
		expect(note.textContent?.replace(/\s+/g, ' ')).toContain(
			"An off pump has no speed. A speed-controlled pump's speed is the one it runs at"
		);
		// A limit is not always a setpoint out of the drive's range: a pump saturated at its
		// minimum speed can stay there although a higher speed would hold the setpoint (D11).
		expect(note.textContent?.replace(/\s+/g, ' ')).toContain(
			'or its minimum or maximum speed when its drive is at a limit'
		);

		// The chart of the controlled pump: its curve at the solved speed; its own control is
		// replaced at each point of its system curve.
		const figure = within(
			panel.getByRole('figure', { name: 'Pump and system curves: Transfer pump' })
		);
		expect(
			await figure.findByRole('table', { name: 'Pump curve at 87.32 % speed (flow control)' })
		).toBeInTheDocument();
		await vi.waitFor(() => expect(answers).toHaveLength(1));
		answers[0]!(systemCurveResponse('P1'));
		expect(await figure.findByText(/^System curve: /)).toHaveTextContent(
			'(its flow control replaced by that fixed flow; other pumps running, valves following their rules)'
		);
		// The booster's system curve: the controlled pump keeps regulating.
		await fireEvent.change(panel.getByRole('combobox', { name: 'Pump chart' }), {
			target: { value: booster.id }
		});
		await vi.waitFor(() => expect(answers).toHaveLength(2));
		answers[1]!(systemCurveResponse(booster.id));
		const other = within(
			panel.getByRole('figure', { name: 'Pump and system curves: Booster pump' })
		);
		expect(await other.findByText(/^System curve: /)).toHaveTextContent(
			'(other pumps running, speed-controlled ones regulating to their setpoints, valves following their rules)'
		);
	});
});
