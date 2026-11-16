/**
 * Pump chart: what is drawn (Chart.js is replaced by a recorder; jsdom has no canvas), the data
 * table under it, and the states of the system curve fetched for the solve (loading with Cancel,
 * failed, cancelled, points without a solution). The pump results and curves are made-up test
 * inputs.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemCurveState } from '$lib/state/project.svelte';
import {
	caseTags,
	chartNotes,
	pumpChartData,
	type OtherCaseInput,
	type PanelKey,
	type PumpChecksInput
} from '$lib/utils/pump-chart';
import { fakeResizeObserver, sizeBox } from '$lib/testing/resize';
import { pumpResult, systemCurvePoint, systemCurveResponse } from '$lib/testing/results';
import {
	besideCaseTag,
	designators,
	outOfSight,
	shownCaseTag,
	spokenWords,
	wordsInSight
} from '$lib/testing/helpers';
import { pumpTransferExample } from '$lib/utils/examples';
import { IMPERIAL_UNITS, SI_UNITS } from '$lib/utils/units';
import type { ChartImageRequest, ChartImageSource } from '$lib/utils/export/chart-image';
import { DISCLAIMER } from '$lib/components/links';
import PumpChart from './PumpChart.svelte';

/**
 * Every case's number as the Pumps view gives them (pump-chart.ts caseTags; owner, 2026-11-12,
 * nit 5, Q2 "By list place"; docs/proposals/pumps-nits.md item 5, slice 5b): the tests' other
 * cases are scenarios S1 to S8, numbered 1 to 8 by their place in the Scenarios list.
 */
const TAGS = caseTags({
	scenarios: Array.from({ length: 8 }, (_, i) => ({
		id: `S${i + 1}`,
		name: `Scenario ${i + 1}`,
		overrides: []
	}))
});

interface Recorded {
	data: {
		datasets: { label: string; data: unknown[]; borderDash?: number[]; showLine?: boolean }[];
	};
	options: { scales: { x: { title: { text: string } }; y: { title: { text: string } } } };
}

const charts = vi.hoisted(() => [] as { config: unknown; destroyed: boolean; draws?: number }[]);
/** The chart image's requests (the image code itself is tested in chart-image.test.ts). */
const images = vi.hoisted(() => ({ requests: [] as unknown[] }));

vi.mock('./chart-setup', async () => ({
	// The chart's own configuration: only Chart.js and the image are replaced.
	pumpChartConfig: (await import('$lib/utils/pump-chart-config')).pumpChartConfig,
	Chart: class {
		static defaults = { plugins: { legend: { labels: { generateLabels: () => [] } } } };
		record: { config: unknown; destroyed: boolean; draws?: number };
		constructor(_context: unknown, config: unknown) {
			this.record = { config, destroyed: false };
			charts.push(this.record);
		}
		destroy() {
			this.record.destroyed = true;
		}
		/** Redrawn when the readout's flow moves. */
		draw() {
			this.record.draws = (this.record.draws ?? 0) + 1;
		}
	},
	downloadChartImage: async (_chart: unknown, request: unknown) =>
		void images.requests.push(request),
	IMAGE_REASONS_IN: 'made-up place says'
}));

const getContext = HTMLCanvasElement.prototype.getContext;

beforeEach(() => {
	charts.length = 0;
	images.requests.length = 0;
});

afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	// The data table shown is remembered in this browser (pumps-results-layout.md §9 S7): each
	// test starts from none remembered.
	localStorage.clear();
});

function withCanvas() {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
}

const READY: SystemCurveState = { status: 'ready', curve: systemCurveResponse() };

/** The next animation frame's callbacks have run (jsdom draws one every 16 ms). */
const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
/**
 * Two frames after a mount: its live lines have been drawn empty and may speak
 * (pumps-results-layout.md §7 Live regions, F17).
 */
async function linesDrawn() {
	await nextFrame();
	await nextFrame();
	await tick();
}

/** A curve table's disclosure (CurveTable), by its table's name. */
const disclosureOf = (name: string, scope: HTMLElement = document.body) =>
	within(scope).getByRole('table', { name }).closest('details')!;
/**
 * Open a curve table's disclosure as a user would, closed until then: a curve table is read
 * after its disclosure is opened (pumps-results-layout.md §9 S7, §10 S7). Its table.
 */
async function openTable(name: string, scope: HTMLElement = document.body) {
	const details = disclosureOf(name, scope);
	expect(details.open, `"${name}" closed until opened`).toBe(false);
	await fireEvent.click(details.querySelector(':scope > summary')!);
	expect(details.open).toBe(true);
	return within(scope).getByRole('table', { name });
}

describe('pump chart', () => {
	it('draws the curve, the dashed extrapolation, the system curve and the operating point', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false }),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: READY
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const config = charts[0]!.config as Recorded;
		expect(config.data.datasets.map((d) => d.label)).toEqual([
			'Pump curve at 100 % speed',
			'Pump curve, extrapolated (dashed)',
			'System curve',
			'Operating point',
			// The curve facts (proposal pump-chart.md §6): the shutoff head, always.
			'Shutoff head'
		]);
		const [curve, extrapolated, , operating] = config.data.datasets;
		expect(curve!.borderDash).toBeUndefined();
		expect(extrapolated!.borderDash).toEqual([6, 4]);
		expect(extrapolated!.data).toEqual([
			{ x: expect.closeTo(30, 9), y: 12 },
			{ x: expect.closeTo(34, 9), y: 7.5 }
		]);
		expect(operating!.showLine).toBe(false);
		expect(config.options.scales.x.title.text).toBe('Flow (L/s)');
		expect(config.options.scales.y.title.text).toBe('Head (m)');
		expect(
			screen.getByRole('img', {
				name: /operating point 34 L\/s at 7\.5 m; dashed: extrapolated beyond the curve data/
			})
		).toBeInTheDocument();
		expect(
			screen.getByText(/extrapolated beyond its data \(0 to 30 L\/s at this speed\)/)
		).toBeInTheDocument();
	});

	it('shows the data table on request', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult(),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			system: READY
		});
		const toggle = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		// The words in sight (Show kept beside them in one cell, invisible: pumps-nits.md item 1).
		expect(wordsInSight(toggle).replace(/\s+/g, ' ').trim()).toBe('Hide data table');
		const curve = await openTable('Pump curve at 100 % speed');
		const rows = within(curve).getAllByRole('row').slice(1);
		expect(
			rows.map((r) =>
				within(r)
					.getAllByRole('cell')
					.map((c) => c.textContent)
			)
		).toEqual([
			['0', '30', 'Curve'],
			['10', '28', 'Curve'],
			['20', '22', 'Curve'],
			['30', '12', 'Curve']
		]);
		const system = await openTable('System curve');
		expect(within(system).getAllByRole('row')).toHaveLength(5);
		expect(within(system).queryByRole('columnheader', { name: 'Why no head' })).toBeNull();
		expect(screen.getByText(/Operating point:/)).toHaveTextContent(
			'Operating point: 20 L/s at 22 m'
		);
	});

	it('shows the table instead when the chart cannot be drawn, and says when there is no system curve', async () => {
		render(PumpChart, { result: pumpResult(), name: 'Transfer pump', prefs: SI_UNITS });
		expect(
			await screen.findByText(/The chart cannot be drawn in this browser/)
		).toBeInTheDocument();
		expect(screen.getByRole('table', { name: 'Pump curve at 100 % speed' })).toBeInTheDocument();
		expect(screen.queryByRole('table', { name: 'System curve' })).toBeNull();
		expect(
			screen.getByText('The system curve has not been computed for this solve.')
		).toBeInTheDocument();
		// Without a way to compute it, nothing is offered.
		expect(screen.queryByRole('button', { name: 'Compute the system curve' })).toBeNull();
		expect(charts).toHaveLength(0);
	});

	it('says while the system curve is computed, and draws it when it arrives', async () => {
		withCanvas();
		const view = render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'loading' }
		});
		// Said once its line has been drawn empty (pumps-results-layout.md §7 Live regions, F17).
		expect(
			await screen.findByText('Computing the system curve for this solve…')
		).toBeInTheDocument();
		// Busy is the canvas's, the part redrawn (pumps-results-layout.md §5.3), not the figure's.
		expect(screen.getByRole('img')).toHaveAttribute('aria-busy', 'true');
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const labels = (i: number) => (charts[i]!.config as Recorded).data.datasets.map((d) => d.label);
		expect(labels(0)).not.toContain('System curve');
		expect(screen.getByRole('img').getAttribute('aria-label')).not.toMatch(/system curve/);

		await view.rerender({ result: pumpResult(), name: 'P', prefs: SI_UNITS, system: READY });
		await vi.waitFor(() => expect(charts).toHaveLength(2));
		expect(labels(1)).toContain('System curve');
		expect(screen.queryByText(/Computing the system curve/)).toBeNull();
		expect(screen.getByRole('img')).toHaveAttribute('aria-busy', 'false');
		expect(screen.getByRole('img')).toHaveAccessibleName(/and system curve; operating point/);
	});

	it('says how the system curve shown was computed and links to the pump trace', async () => {
		// The curve comes from POST /api/v1/system-curve, whose response has no trace: the chart
		// states how it was computed and opens the pump's trace, which defines it (GOALS §4.2).
		withCanvas();
		const ontrace = vi.fn();
		const view = render(PumpChart, {
			result: pumpResult(),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			system: { status: 'loading' },
			ontrace
		});
		expect(screen.queryByText(/^System curve: /)).toBeNull();
		expect(screen.queryByRole('button', { name: 'Trace of Transfer pump' })).toBeNull();

		await view.rerender({ system: READY });
		expect(screen.getByText(/^System curve: /)).toHaveTextContent(
			'System curve: the network of this solve, solved again with the pump replaced by each of ' +
				'4 evenly spaced flows from 0 to 30 L/s (other pumps running, valves following their ' +
				'rules); the system head at each flow is the EGL at the discharge minus the EGL at the ' +
				'suction.'
		);
		await fireEvent.click(screen.getByRole('button', { name: 'Trace of Transfer pump' }));
		expect(ontrace).toHaveBeenCalledTimes(1);
	});

	it('reports a failed or cancelled system curve and offers to compute it again', async () => {
		const onretry = vi.fn();
		const view = render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'error', message: 'Made-up server message.' },
			onretry
		});
		expect(
			screen.getByText('The system curve could not be computed: Made-up server message.')
		).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
		expect(onretry).toHaveBeenCalledTimes(1);

		await view.rerender({
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'cancelled', by: 'solve' },
			onretry
		});
		expect(
			screen.getByText('The system curve was not computed: a new solve was started.')
		).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Compute the system curve' }));
		expect(onretry).toHaveBeenCalledTimes(2);
		await view.rerender({
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'cancelled', by: 'goalSeek' },
			onretry
		});
		expect(
			screen.getByText('The system curve was not computed: a goal seek was started.')
		).toBeInTheDocument();
		// No system curve is shown in either state.
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		expect(screen.getByRole('table', { name: 'Pump curve at 100 % speed' })).toBeInTheDocument();
		expect(screen.queryByRole('table', { name: 'System curve' })).toBeNull();
	});

	it('offers Cancel while the system curve is computed; cancelled, it offers to compute it', async () => {
		// The canvas drawn, so its busy state can be read (pumps-results-layout.md §5.3).
		withCanvas();
		const oncancel = vi.fn();
		const onretry = vi.fn();
		const props = { result: pumpResult(), name: 'P', prefs: SI_UNITS, oncancel, onretry };
		const view = render(PumpChart, { ...props, system: { status: 'loading' } });
		const cancel = screen.getByRole('button', { name: 'Cancel the system curve' });
		expect(cancel).toHaveTextContent(/^Cancel$/);
		// A keyboard user presses it: the store marks the curve cancelled by the user.
		cancel.focus();
		await fireEvent.click(cancel);
		expect(oncancel).toHaveBeenCalledTimes(1);
		await view.rerender({ ...props, system: { status: 'cancelled', by: 'user' } });
		await tick();
		expect(screen.queryByRole('button', { name: 'Cancel the system curve' })).toBeNull();
		expect(screen.queryByText(/Computing the system curve/)).toBeNull();
		const again = screen.getByRole('button', { name: 'Compute the system curve' });
		expect(again).toHaveAccessibleDescription(
			'The system curve was not computed: you cancelled it.'
		);
		// The focus goes to what replaced Cancel, not to the page.
		expect(document.activeElement).toBe(again);
		expect(screen.getByRole('img')).toHaveAttribute('aria-busy', 'false');
		await fireEvent.click(again);
		expect(onretry).toHaveBeenCalledTimes(1);
	});

	it('moves the focus from Cancel to the chart when the curve arrives, and to Try again when it fails', async () => {
		withCanvas();
		const props = { result: pumpResult(), name: 'P', prefs: SI_UNITS, oncancel: vi.fn() };
		const view = render(PumpChart, { ...props, onretry: vi.fn(), system: { status: 'loading' } });
		screen.getByRole('button', { name: 'Cancel the system curve' }).focus();
		await view.rerender({ ...props, onretry: vi.fn(), system: READY });
		await tick();
		expect(document.activeElement).toBe(
			screen.getByRole('figure', { name: 'Pump and system curves: P' })
		);
		await view.rerender({ ...props, system: { status: 'loading' } });
		screen.getByRole('button', { name: 'Cancel the system curve' }).focus();
		await view.rerender({ ...props, system: { status: 'error', message: 'Made-up message.' } });
		await tick();
		expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Try again' }));
		expect(document.activeElement).toHaveAccessibleDescription(
			'The system curve could not be computed: Made-up message.'
		);
	});

	it('moves the focus to Cancel when the curve is computed again from Compute or Try again', async () => {
		const props = {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			oncancel: vi.fn(),
			onretry: vi.fn()
		};
		const view = render(PumpChart, { ...props, system: { status: 'cancelled', by: 'user' } });
		const again = screen.getByRole('button', { name: 'Compute the system curve' });
		// A keyboard user presses it: the store starts the curve again.
		again.focus();
		await fireEvent.click(again);
		expect(props.onretry).toHaveBeenCalledTimes(1);
		await view.rerender({ ...props, system: { status: 'loading' } });
		await tick();
		const cancel = () => screen.getByRole('button', { name: 'Cancel the system curve' });
		expect(document.activeElement).toBe(cancel());
		await view.rerender({ ...props, system: { status: 'error', message: 'Made-up message.' } });
		await tick();
		expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Try again' }));
		await view.rerender({ ...props, system: { status: 'loading' } });
		await tick();
		expect(document.activeElement).toBe(cancel());
		// With no way to cancel, the chart takes the focus.
		await view.rerender({ ...props, system: { status: 'error', message: 'Made-up message.' } });
		await tick();
		expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Try again' }));
		await view.rerender({ ...props, oncancel: undefined, system: { status: 'loading' } });
		await tick();
		expect(document.activeElement).toBe(
			screen.getByRole('figure', { name: 'Pump and system curves: P' })
		);
		// Focus elsewhere stays where it is.
		await view.rerender({ ...props, system: { status: 'cancelled', by: 'user' } });
		const table = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		table.focus();
		await view.rerender({ ...props, system: { status: 'loading' } });
		await tick();
		expect(document.activeElement).toBe(table);
	});

	it('leaves the focus alone when Cancel did not have it, and offers no Cancel without a way to', async () => {
		const props = { result: pumpResult(), name: 'P', prefs: SI_UNITS, oncancel: vi.fn() };
		const view = render(PumpChart, { ...props, system: { status: 'loading' } });
		const table = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		table.focus();
		await view.rerender({ ...props, system: { status: 'cancelled', by: 'user' } });
		await tick();
		expect(document.activeElement).toBe(table);
		await view.rerender({ ...props, oncancel: undefined, system: { status: 'loading' } });
		// Said once its line has been drawn empty, two frames after the mount (§7, F17).
		expect(
			await screen.findByText('Computing the system curve for this solve…')
		).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /^Cancel/ })).toBeNull();
	});

	it('draws points without a head as gaps and lists why in the table', async () => {
		withCanvas();
		const curve = systemCurveResponse('P1', [1]);
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'ready', curve }
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const system = (charts[0]!.config as Recorded).data.datasets.find(
			(d) => d.label === 'System curve'
		) as { data: { y: number | null }[]; spanGaps?: boolean };
		expect(system.data.map((p) => p.y)).toEqual([12, null, 22, 34.5]);
		expect(system.spanGaps).toBe(false);
		expect(
			screen.getByText(
				'1 of 4 system-curve points have no head: the line has gaps there, and the data table says why for each (no steady state carries the flow, its head is undetermined, its solve did not converge, or it was not computed).'
			)
		).toBeInTheDocument();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		const table = screen.getByRole('table', { name: 'System curve' });
		// Open by default: its Why no head column has entries (§9 S7).
		expect(disclosureOf('System curve').open).toBe(true);
		expect(within(table).getByRole('columnheader', { name: 'Why no head' })).toBeInTheDocument();
		const rows = within(table)
			.getAllByRole('row')
			.slice(1)
			.map((r) =>
				within(r)
					.getAllByRole('cell')
					.map((c) => c.textContent)
			);
		expect(rows[1]).toEqual(['10', '—', 'made-up reason: not converged']);
		expect(rows[0]).toEqual(['0', '12', '']);
	});

	it('tells why a point has no head with names and display units, the API sentence under Details', async () => {
		withCanvas();
		// Made-up test inputs: the point at 0.02 m³/s has an FCV at its switch, whose open head
		// is 15.24 m (50 ft).
		const curve = systemCurveResponse('P1', [2]);
		const message =
			"the head across the pump is undetermined: at this flow FCV 'V1' passes exactly its " +
			'setpoint flow, so the valve could also hold it throttled, with any head across the pump ' +
			'at or above 15.24 m (with the valve fully open), and no reservoir or reference node fixes ' +
			'the pressure between the valve and the pump';
		curve.points[2] = systemCurvePoint({
			flow: 0.02,
			message,
			reason: 'valve_at_switch',
			componentIds: ['V1'],
			openHead: 15.24,
			openHeadBound: 'lower'
		});
		const project = pumpTransferExample();
		project.components[2] = {
			type: 'valve',
			valveType: 'fcv',
			id: 'V1',
			name: 'Flow limiter',
			elevation: 0,
			status: 'active',
			setpoint: 0.02,
			ports: project.components[2]!.ports
		};
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: IMPERIAL_UNITS,
			names: { project, solved: project },
			system: { status: 'ready', curve }
		});
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		const table = screen.getByRole('table', { name: 'System curve' });
		// Open by default: its Why no head column has entries (§9 S7).
		expect(disclosureOf('System curve').open).toBe(true);
		const cell = within(table).getAllByRole('row')[3]!.querySelectorAll('td')[2]!;
		const details = cell.querySelector('details')!;
		expect(details.open).toBe(false);
		expect(within(details).getByText('Details')).toBeInTheDocument();
		// Its point named by a visually hidden suffix (pumps-results-layout.md §6.2): 0.02 m³/s is
		// 0.02 / (231 × 0.0254³ / 60) = 317.006 gpm, 317 to four figures.
		expect(0.02 / ((231 * 0.0254 ** 3) / 60)).toBeCloseTo(317.006, 3);
		const summary = details.querySelector('summary')!;
		expect(summary.textContent!.replace(/\s+/g, ' ').trim()).toBe(
			'Details of the point at 317 gpm'
		);
		expect(summary.querySelector('.sr-only')).toHaveTextContent(/^of the point at 317 gpm$/);
		expect(details).toHaveTextContent(`Calculation server's message: ${message}`);
		details.remove();
		expect(cell.textContent).toBe(
			'The head across the pump is undetermined: at this flow Flow limiter passes exactly its ' +
				'flow setpoint, so it could also hold the flow throttled, with any head across the pump ' +
				'at or above 50 ft (its head with the valve fully open), and no reservoir or reference ' +
				'node fixes the pressure between the valve and the pump.'
		);
		expect(15.24 / 0.3048).toBeCloseTo(50, 12);
	});

	it('says when no point of the system curve has a head, and draws none', async () => {
		withCanvas();
		const curve = systemCurveResponse('P1', [0, 1, 2, 3]);
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'ready', curve }
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const labels = (charts[0]!.config as Recorded).data.datasets.map((d) => d.label);
		expect(labels).not.toContain('System curve');
		expect(
			screen.getByText(
				'No point of the system curve has a head, so it is not drawn; the data table says why for each (no steady state carries the flow, its head is undetermined, its solve did not converge, or it was not computed).'
			)
		).toBeInTheDocument();
	});

	it('labels a speed-controlled pump at the speed it was solved to run at, and its state', async () => {
		withCanvas();
		const control = (state: 'active' | 'max_speed' | 'min_speed' | 'off') =>
			({ mode: 'flow', setpoint: 0.02, state, setpointAchieved: state === 'active' }) as const;
		const view = render(PumpChart, {
			result: pumpResult({ speed: 0.873214, control: control('active') }),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03]
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const label = (i: number) => (charts[i]!.config as Recorded).data.datasets[0]!.label;
		expect(label(0)).toBe('Pump curve at 87.32 % speed (flow control)');
		expect(screen.getByRole('img')).toHaveAccessibleName(
			/^Pump curve of Transfer pump at 87\.32 % speed \(flow control\); operating point/
		);
		// The curve's data range at that speed (the affinity law the solver applies).
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		expect(
			screen.getByRole('table', { name: 'Pump curve at 87.32 % speed (flow control)' })
		).toBeInTheDocument();

		await view.rerender({ result: pumpResult({ speed: 0.9, control: control('max_speed') }) });
		await vi.waitFor(() => expect(charts).toHaveLength(2));
		expect(label(1)).toBe('Pump curve at 90 % speed (flow control, at maximum speed)');
		await view.rerender({ result: pumpResult({ speed: 0.4, control: control('min_speed') }) });
		await vi.waitFor(() => expect(charts).toHaveLength(3));
		expect(label(2)).toBe('Pump curve at 40 % speed (flow control, at minimum speed)');

		await view.rerender({
			result: pumpResult({ status: 'off', speed: 0.9, operatingFlow: 0, control: control('off') })
		});
		expect(
			screen.getByText(
				'This pump is off: it carries no flow. Its curve is shown at its maximum speed, for reference; its flow control is not applied.'
			)
		).toBeInTheDocument();
		expect(screen.getByRole('img')).toHaveAccessibleName(/at its maximum speed \(90 %\)/);
	});

	it("says a speed-controlled pump's own control is replaced in its system curve", async () => {
		withCanvas();
		const control = {
			mode: 'flow',
			setpoint: 0.02,
			state: 'active',
			setpointAchieved: true
		} as const;
		const view = render(PumpChart, {
			result: pumpResult({ speed: 0.95, control }),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			system: READY
		});
		expect(screen.getByText(/^System curve: /)).toHaveTextContent(
			'replaced by each of 4 evenly spaced flows from 0 to 30 L/s (its flow control replaced by ' +
				'that fixed flow; other pumps running, valves following their rules)'
		);
		// Other speed-controlled pumps keep regulating at each point.
		await view.rerender({ result: pumpResult(), othersControlled: true });
		expect(screen.getByText(/^System curve: /)).toHaveTextContent(
			'(other pumps running, speed-controlled ones regulating to their setpoints, valves ' +
				'following their rules)'
		);
	});

	it('replaces the chart when the result changes and destroys it on unmount', async () => {
		withCanvas();
		const view = render(PumpChart, { result: pumpResult(), name: 'P', prefs: SI_UNITS });
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await view.rerender({
			result: pumpResult({ operatingFlow: 0.01, operatingHead: 28 }),
			name: 'P',
			prefs: SI_UNITS
		});
		await vi.waitFor(() => expect(charts).toHaveLength(2));
		expect(charts[0]!.destroyed).toBe(true);
		view.unmount();
		expect(charts[1]!.destroyed).toBe(true);
	});

	describe('Download image (proposal export.md §5.5)', () => {
		const notices: { kind: string; text: string }[] = [];
		const image = (values: Partial<ChartImageSource> = {}): ChartImageSource => ({
			projectName: 'Pump transfer between two tanks',
			timestamp: '2026-10-25T12:32:05Z',
			methodVersion: '1.2.0',
			stale: false,
			unavailable: '',
			origin: 'https://opensolve-pipe.app',
			notify: (kind, text) => void notices.push({ kind, text }),
			...values
		});
		const button = () =>
			screen.getByRole('button', {
				name: /^Download image of the pump and system curves: Transfer pump/
			});

		beforeEach(() => {
			notices.length = 0;
		});

		it('is offered only with an image source, beside Show data table', async () => {
			withCanvas();
			const view = render(PumpChart, {
				result: pumpResult(),
				name: 'Transfer pump',
				prefs: SI_UNITS,
				system: READY
			});
			await vi.waitFor(() => expect(charts).toHaveLength(1));
			expect(screen.queryByRole('button', { name: /^Download image/ })).toBeNull();
			await view.rerender({ image: image() });
			expect(button()).toHaveTextContent('Download image');
			expect(button()).toHaveAttribute('data-chart-image');
			// In the actions row beside Show data table, in its own item with its reason (§5.3 Actions).
			expect(button().parentElement!.parentElement).toBe(
				screen.getByRole('button', { name: 'Show data table of the pump chart' }).parentElement
			);
		});

		it('is unavailable, with the reason, until the chart is drawn and while a curve is computed', async () => {
			withCanvas();
			const props = {
				result: pumpResult(),
				name: 'Transfer pump',
				prefs: SI_UNITS,
				image: image()
			};
			const view = render(PumpChart, { ...props, system: { status: 'loading' } });
			expect(button()).toHaveAttribute('aria-disabled', 'true');
			expect(button()).toHaveAccessibleDescription(
				'Wait until the system curve is computed, or cancel it.'
			);
			await view.rerender({ ...props, system: READY });
			await vi.waitFor(() => expect(button()).not.toHaveAttribute('aria-disabled', 'true'));
			expect(button()).not.toHaveAttribute('title');
			// Another case's curve on the chart being computed.
			await view.rerender({ ...props, system: READY, overlayProgress: { done: 0, total: 1 } });
			expect(button()).toHaveAttribute(
				'title',
				'Wait until the system curve is computed, or cancel it.'
			);
			// The results' own reason (PumpsView's: not converged, failed shown, a calculation).
			await view.rerender({
				...props,
				system: READY,
				overlayProgress: null,
				image: image({ unavailable: 'Made-up reason.' })
			});
			expect(button()).toHaveAccessibleDescription('Made-up reason.');
			await fireEvent.click(button());
			expect(images.requests).toHaveLength(0);
		});

		it('says the chart is being drawn before it is', async () => {
			withCanvas();
			render(PumpChart, {
				result: pumpResult(),
				name: 'Transfer pump',
				prefs: SI_UNITS,
				system: READY,
				image: image()
			});
			expect(button()).toHaveAccessibleDescription('The chart is being drawn.');
			await vi.waitFor(() => expect(charts).toHaveLength(1));
			expect(button()).not.toHaveAttribute('aria-disabled', 'true');
		});

		it('is not offered when the chart cannot be drawn', async () => {
			render(PumpChart, {
				result: pumpResult(),
				name: 'Transfer pump',
				prefs: SI_UNITS,
				image: image()
			});
			expect(
				await screen.findByText(/The chart cannot be drawn in this browser/)
			).toBeInTheDocument();
			expect(screen.queryByRole('button', { name: /^Download image/ })).toBeNull();
		});

		it('asks the chart chunk for the image of what it shows', async () => {
			withCanvas();
			const others = [
				{ key: 'S1', name: 'Winter', result: pumpResult(), stale: false, system: null }
			];
			const source = image({ stale: true });
			render(PumpChart, {
				result: pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false }),
				name: 'Transfer pump',
				prefs: SI_UNITS,
				ratedRange: [0, 0.03],
				system: READY,
				caseName: 'Base case',
				tags: TAGS,
				others,
				othersControlled: true,
				image: source
			});
			await vi.waitFor(() => expect(charts).toHaveLength(1));
			await fireEvent.click(button());
			await vi.waitFor(() => expect(images.requests).toHaveLength(1));
			const request = images.requests[0] as ChartImageRequest;
			expect(request).toMatchObject({
				pumpName: 'Transfer pump',
				caseName: 'Base case',
				disclaimer: DISCLAIMER,
				source
			});
			// The screen's own datasets, drawn once at 2× without events.
			const screen = charts[0]!.config as Recorded;
			expect(request.config.data).toEqual(screen.data);
			expect(request.config.options).toMatchObject({
				responsive: false,
				devicePixelRatio: 2,
				events: []
			});
			// The figure's notes as shown, pointing to where the reasons are.
			expect(request.notes.method).toBe(
				document.querySelector('figure [data-pump-method]')?.firstChild?.textContent?.trim()
			);
			expect(request.notes.method).toMatch(/speed-controlled ones regulating to their setpoints/);
			expect(request.others.map((o) => o.label)).toEqual(['Winter']);
			expect(button()).toHaveAccessibleName(
				'Download image of the pump and system curves: Transfer pump, Base case'
			);
		});

		it('gives the image the line naming the cases that take no slot, as the screen shows it (pumps-results-layout.md §6.2 S8)', async () => {
			withCanvas();
			const off = { status: 'off', operatingFlow: 0, operatingHead: 0 } as const;
			const props = {
				result: pumpResult(),
				name: 'Transfer pump',
				prefs: SI_UNITS,
				ratedRange: [0, 0.03] as [number, number],
				system: READY,
				tags: TAGS,
				others: [
					{ key: 'S1', name: 'Winter', result: pumpResult(), stale: false, system: null },
					{ key: 'S2', name: 'Pump off', result: pumpResult(off), stale: true, system: null }
				],
				onoverlay: vi.fn(),
				image: image()
			};
			const view = render(PumpChart, props);
			await vi.waitFor(() => expect(charts).toHaveLength(1));
			// Nit 5, slice 5b: each case by its number (docs/proposals/pumps-nits.md item 5).
			const line = 'Off in this case (no operating point): case 2: Pump off (out of date).';
			expect(document.querySelector('[data-pump-off-cases]')).toHaveTextContent(line);
			await fireEvent.click(button());
			await vi.waitFor(() => expect(images.requests).toHaveLength(1));
			const request = images.requests[0] as ChartImageRequest;
			expect(request.offCases).toBe(line);
			expect(request.others.map((o) => o.label)).toEqual(['Winter']);
			// With the other cases' system curves asked for, the case takes its slot: no line.
			await view.rerender({ ...props, overlayCurves: true });
			await vi.waitFor(() => expect(charts.at(-1)!.destroyed).toBe(false));
			await vi.waitFor(() => expect(button()).not.toHaveAttribute('aria-disabled', 'true'));
			await fireEvent.click(button());
			await vi.waitFor(() => expect(images.requests).toHaveLength(2));
			const second = images.requests[1] as ChartImageRequest;
			expect(second.offCases).toBeNull();
			expect(second.others.map((o) => o.label)).toEqual(['Winter', 'Pump off (out of date)']);
		});
	});
});

describe('pump chart panels (proposal pump-chart.md §4)', () => {
	afterEach(() => localStorage.clear());

	const rich = () =>
		pumpResult({
			efficiencyCurve: [
				{ flow: 0.005, efficiency: 0.4 },
				{ flow: 0.03, efficiency: 0.65 }
			],
			powerCurve: [
				{ flow: 0.005, shaftPower: 3500 },
				{ flow: 0.03, shaftPower: 5500 }
			],
			npshrCurve: [
				{ flow: 0.005, npshr: 1 },
				{ flow: 0.03, npshr: 6 }
			]
		});
	const axes = (n: number) =>
		Object.keys((charts[n]!.config as { options: { scales: object } }).options.scales);

	it('shows a chip per panel with data, hides one on press, and remembers it', async () => {
		withCanvas();
		const view = render(PumpChart, { result: rich(), name: 'Transfer pump', prefs: SI_UNITS });
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		expect(axes(0)).toEqual(['x', 'yNpsh', 'yPower', 'yEfficiency', 'y']);
		const panels = screen.getByRole('group', { name: 'Show' });
		const power = within(panels).getByRole('button', { name: 'Shaft power' });
		expect(
			within(panels)
				.getAllByRole('button')
				.map((b) => b.textContent)
		).toEqual(['Efficiency', 'Shaft power', 'NPSH']);
		expect(power).toHaveAttribute('aria-pressed', 'true');
		await fireEvent.click(power);
		expect(power).toHaveAttribute('aria-pressed', 'false');
		await vi.waitFor(() => expect(charts).toHaveLength(2));
		expect(axes(1)).toEqual(['x', 'yNpsh', 'yEfficiency', 'y']);
		expect(screen.getByRole('img').getAttribute('aria-label')).toContain(
			'below, on the same flow axis: efficiency, npsh'
		);
		view.unmount();
		render(PumpChart, { result: rich(), name: 'Transfer pump', prefs: SI_UNITS });
		expect(screen.getByRole('button', { name: 'Shaft power' })).toHaveAttribute(
			'aria-pressed',
			'false'
		);
	});

	it('reads every line shown at the duty, and at the slider’s flow', async () => {
		withCanvas();
		render(PumpChart, { result: rich(), name: 'Transfer pump', prefs: SI_UNITS });
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const slider = screen.getByRole('slider', { name: 'Read at flow' });
		const line = () =>
			screen.getByRole('figure').querySelector('[data-pump-readout]')!.textContent!;
		expect(line().replace(/\s+/g, ' ')).toContain('At the duty 20 L/s: Pump head 22 m');
		await fireEvent.input(slider, { target: { value: '10' } });
		const text = line().replace(/\s+/g, ' ');
		expect(text).toContain('At 10 L/s: Pump head 28 m');
		expect(text).toContain('Pump head 28 m, Efficiency 45 %');
		expect(text).toContain('NPSHr 2 m');
		expect(slider.getAttribute('aria-valuetext')).toContain(
			'10 L/s: Pump head 28 m, Efficiency 45 %'
		);
		expect(charts[0]!.draws).toBeGreaterThan(0);
		await fireEvent.click(screen.getByRole('button', { name: 'Back to the duty' }));
		expect(line()).toContain('At the duty');
	});
});

// The pump chart's reading, strip, actions and notes (proposal pumps-results-layout.md §5.3
// item 2, §7, slice S1). The pump results and curves are made-up test inputs.
describe('pump chart layout (pumps-results-layout.md §5.3)', () => {
	afterEach(() => localStorage.clear());

	/** Every panel, a rising stretch, an extrapolated duty and an NPSHr curve (test input). */
	const full = () =>
		pumpResult({
			operatingFlow: 0.034,
			operatingHead: 7.5,
			inCurveRange: false,
			efficiencyCurve: [
				{ flow: 0.004, efficiency: 0.4 },
				{ flow: 0.012, efficiency: 0.7 },
				{ flow: 0.02, efficiency: 0.6 }
			],
			bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false },
			powerCurve: [
				{ flow: 0.004, shaftPower: 2000 },
				{ flow: 0.02, shaftPower: 5000 }
			],
			npshrCurve: [
				{ flow: 0, npshr: 1 },
				{ flow: 0.03, npshr: 4 }
			],
			risingHeadRanges: [{ flowMin: 0, flowMax: 0.005 }]
		});
	/**
	 * The system curve with NPSHa falling 10, 8, 4, 1 m against NPSHr 1, 2, 3, 4 m at 0 to 30 L/s:
	 * NPSHa − NPSHr goes from +1 m at 20 L/s to −3 m at 30 L/s, so the lines cross at
	 * 20 + 10 × 1 / (1 + 3) = 22.5 L/s.
	 */
	const withNpsha = (): SystemCurveState => {
		const curve = systemCurveResponse();
		[10, 8, 4, 1].forEach((npsha, i) => (curve.points[i]!.npshAvailable = npsha));
		return { status: 'ready', curve };
	};
	/** Design checks with every limit the chart draws (test input, the user's values). */
	const limits: PumpChecksInput = {
		checks: {
			npshMargin: { minimumMargin: 1, source: { kind: 'user' } },
			operatingRegion: { preferredMin: 0.7, preferredMax: 1.2, source: { kind: 'user' } }
		},
		curve: {
			id: 'C1',
			name: 'Curve',
			points: [
				{ flow: 0, head: 30 },
				{ flow: 0.03, head: 12 }
			],
			allowableOperatingRegion: { flowMin: 0.004, flowMax: 0.025 },
			minimumContinuousStableFlow: 0.003,
			motorRatedPower: 5500
		},
		sources: { npshMargin: 'your values', operatingRegion: 'your values' }
	};

	it('hands the focus to the slider when Back to the duty goes (F40)', async () => {
		withCanvas();
		render(PumpChart, { result: pumpResult(), name: 'Transfer pump', prefs: SI_UNITS });
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const slider = screen.getByRole('slider', { name: 'Read at flow' });
		await fireEvent.input(slider, { target: { value: '10' } });
		const back = screen.getByRole('button', { name: 'Back to the duty' });
		back.focus();
		await fireEvent.click(back);
		await tick();
		expect(screen.queryByRole('button', { name: 'Back to the duty' })).toBeNull();
		expect(slider).toHaveFocus();
		expect(screen.getByRole('figure').querySelector('[data-pump-readout]')).toHaveTextContent(
			/^At the duty 20 L\/s:/
		);
	});

	it('reads the readout as one paragraph of pairs, each kept on one line', async () => {
		withCanvas();
		render(PumpChart, { result: pumpResult(), name: 'P', prefs: SI_UNITS, system: READY });
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const readout = screen.getByRole('figure').querySelector('[data-pump-readout]')!;
		expect(readout.tagName).toBe('P');
		// Today's text: the separator is a comma and a no-break space.
		expect(readout.textContent).toBe('At the duty 20 L/s: Pump head 22 m,\u00a0System head 22 m');
		const pairs = [...readout.children].slice(1);
		expect(pairs.map((p) => p.className)).toEqual(['whitespace-nowrap', 'whitespace-nowrap']);
		// The separator is the screen reader's only.
		expect(pairs[1]!.firstElementChild).toHaveClass('sr-only');
		expect(pairs[1]!.firstElementChild).toHaveTextContent(',');
		expect(readout).not.toHaveAttribute('aria-live');
	});

	it('draws the chips as toggles: filled with a checked box when on, outlined with an empty box when off, the mark first in both, the same words', async () => {
		withCanvas();
		const result = pumpResult({
			efficiencyCurve: [
				{ flow: 0.005, efficiency: 0.4 },
				{ flow: 0.03, efficiency: 0.65 }
			],
			powerCurve: [
				{ flow: 0.005, shaftPower: 3500 },
				{ flow: 0.03, shaftPower: 5500 }
			]
		});
		render(PumpChart, { result, name: 'P', prefs: SI_UNITS });
		const chips = within(screen.getByRole('group', { name: 'Show' })).getAllByRole('button');
		// One aria-hidden 16 px mark leads the word in both states, so a press changes no chip's width
		// (the owner's nits of 2026-11-12, item 1, docs/proposals/pumps-nits.md): a box with its check
		// in blue-700 when on, the box alone in slate-500 when off. Nit 1 moved `check` (one svg when
		// on, none when off) to these: one svg in both, in the same slot, its shape and tone by state.
		const look = () =>
			chips.map((chip) => {
				const mark = chip.firstElementChild;
				const nodes = [...chip.childNodes];
				return {
					text: chip.textContent,
					pressed: chip.getAttribute('aria-pressed'),
					btn: chip.classList.contains('btn'),
					filled: chip.classList.contains('bg-blue-50'),
					marks: chip.querySelectorAll('svg').length,
					slot: !!mark?.matches('svg[aria-hidden="true"].size-4.shrink-0'),
					lead: !!mark && nodes.slice(0, nodes.indexOf(mark)).every((n) => !n.textContent?.trim()),
					shape: [...(mark?.children ?? [])].map((n) => n.tagName.toLowerCase()).join(' '),
					tone: [...(mark?.classList ?? [])].filter((c) => c.startsWith('text-')).join(' ')
				};
			});
		const on = { marks: 1, slot: true, lead: true, shape: 'rect path', tone: 'text-blue-700' };
		expect(look()).toEqual([
			{ text: 'Efficiency', pressed: 'true', btn: true, filled: true, ...on },
			{ text: 'Shaft power', pressed: 'true', btn: true, filled: true, ...on }
		]);
		await fireEvent.click(chips[1]!);
		expect(look()[1]).toEqual({
			text: 'Shaft power',
			pressed: 'false',
			btn: true,
			filled: false,
			marks: 1,
			slot: true,
			lead: true,
			shape: 'rect',
			tone: 'text-slate-500'
		});
		// And back: the checked box again, in the same slot.
		await fireEvent.click(chips[1]!);
		expect(look()[1]).toEqual({
			text: 'Shaft power',
			pressed: 'true',
			btn: true,
			filled: true,
			...on
		});
		expect(chips[1]).toHaveAccessibleName('Shaft power');
	});

	it('keeps the system curve’s line always there: polite, not a status, never under a busy element', async () => {
		withCanvas();
		const props = {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			oncancel: vi.fn(),
			onretry: vi.fn()
		};
		const view = render(PumpChart, { ...props, system: READY });
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const figure = screen.getByRole('figure');
		const strip = figure.querySelector('[data-pump-strip]')!;
		const line = strip.querySelector('[aria-live]')!;
		// Idle: present and empty, the strip taking no room.
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(line).toHaveAttribute('aria-atomic', 'true');
		expect(line).not.toHaveAttribute('role');
		expect(line.textContent).toBe('');
		expect(strip).toHaveClass('sr-only');
		expect(line.closest('[aria-busy="true"]')).toBeNull();
		expect(figure).not.toHaveAttribute('aria-busy');
		expect(within(figure).queryByRole('status')).toBeNull();

		// Loading: the same element speaks, once drawn empty (F17); the canvas is busy, the line is
		// not under it.
		await linesDrawn();
		await view.rerender({ ...props, system: { status: 'loading' } });
		expect(strip.querySelector('[aria-live]')).toBe(line);
		expect(line).toHaveTextContent('Computing the system curve for this solve…');
		expect(strip).not.toHaveClass('sr-only');
		expect(screen.getByRole('img')).toHaveAttribute('aria-busy', 'true');
		expect(line.closest('[aria-busy="true"]')).toBeNull();
		const cancel = screen.getByRole('button', { name: 'Cancel the system curve' });
		expect(line.contains(cancel)).toBe(false);
		expect(line.nextElementSibling).toBe(cancel);
		expect(cancel).toHaveAccessibleDescription('Computing the system curve for this solve…');
		expect(within(figure).queryByRole('status')).toBeNull();
		// Its mark set at its first line, however the sentence wraps (§5.2): the line's items at its
		// top, the 14 px mark 1 px down on the 16 px line.
		expect(line).toHaveClass('items-start');
		expect(line).not.toHaveClass('items-center');
		expect(line.querySelector('svg')).toHaveClass('mt-px');

		// Failed: the same line, its button after it, outside it.
		await view.rerender({ ...props, system: { status: 'error', message: 'Made-up message.' } });
		expect(strip.querySelector('[aria-live]')).toBe(line);
		expect(line).toHaveTextContent('The system curve could not be computed: Made-up message.');
		expect(line.querySelector('button')).toBeNull();
		expect(line.nextElementSibling).toBe(screen.getByRole('button', { name: 'Try again' }));
		// The failed request's mark (⬣) too, at the first of the lines a long message wraps to.
		expect(line).toHaveClass('items-start');
		expect(line).not.toHaveClass('items-center');
		expect(line.querySelector('svg')).toHaveClass('mt-px');

		// Points without a head: a plain line after it, outside the live line, which is idle.
		await view.rerender({
			...props,
			system: { status: 'ready', curve: systemCurveResponse('P1', [1]) }
		});
		expect(strip.querySelector('[aria-live]')).toBe(line);
		expect(line.textContent).toBe('');
		const coverage = within(strip as HTMLElement).getByText(/^1 of 4 system-curve points/);
		expect(coverage.tagName).toBe('P');
		expect(line.contains(coverage)).toBe(false);
		expect(strip).not.toHaveClass('sr-only');
	});

	it('draws the system curve’s line empty before it speaks, when mounted with the curve being computed (F17)', async () => {
		// PumpsView mounts the chart in the flush that starts its curve, on the tab's opening and on
		// a pump chosen (§7 Live regions): a polite line inserted already holding its words is not
		// announced, so the first progress message waits until the line has been drawn empty.
		withCanvas();
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'loading' },
			oncancel: vi.fn()
		});
		const strip = screen.getByRole('figure').querySelector('[data-pump-strip]')!;
		const line = strip.querySelector('[aria-live]')!;
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(line.textContent).toBe('');
		// Not in the first frame's callbacks either: they run before that frame draws the line.
		await nextFrame();
		expect(line.textContent).toBe('');
		await vi.waitFor(() =>
			expect(line).toHaveTextContent('Computing the system curve for this solve…')
		);
		// The same element speaks, with Cancel after it, described by it.
		expect(strip.querySelector('[aria-live]')).toBe(line);
		expect(
			screen.getByRole('button', { name: 'Cancel the system curve' })
		).toHaveAccessibleDescription('Computing the system curve for this solve…');
	});

	it('shows a lasting reason why no image is made, and keeps a passing one hidden', async () => {
		withCanvas();
		const source = (unavailable: string): ChartImageSource => ({
			projectName: 'P',
			timestamp: '2026-10-25T12:32:05Z',
			methodVersion: '1.2.0',
			stale: false,
			unavailable,
			origin: 'https://opensolve-pipe.app',
			notify: () => {}
		});
		const props = { result: pumpResult(), name: 'P', prefs: SI_UNITS };
		const view = render(PumpChart, { ...props, system: { status: 'loading' }, image: source('') });
		const button = () => screen.getByRole('button', { name: /^Download image/ });
		const reason = () => document.getElementById(button().getAttribute('aria-describedby')!)!;
		// Passing (a curve computed): visually hidden, and in the title.
		expect(reason()).toHaveTextContent('Wait until the system curve is computed, or cancel it.');
		expect(reason()).toHaveClass('sr-only');
		expect(button()).toHaveAttribute(
			'title',
			'Wait until the system curve is computed, or cancel it.'
		);
		// Lasting (the results' own): visible text beside the button, its description.
		await view.rerender({ ...props, system: READY, image: source('Made-up lasting reason.') });
		expect(reason()).toHaveTextContent('Made-up lasting reason.');
		expect(reason()).not.toHaveClass('sr-only');
		expect(outOfSight(reason())).toBe(false);
		expect(reason()).toHaveClass('text-xs');
		expect(reason().parentElement).toBe(button().parentElement);
		// With its button, one item of the actions row apart from Show data table, so it sits beside
		// Download image where the row has room and under it where not, never under Show data
		// table (§5.3 Actions, §5.5).
		const item = reason().parentElement!;
		expect([...item.children]).toEqual([button(), reason()]);
		expect(item).toHaveClass('flex', 'flex-wrap', 'flex-1');
		const show = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		expect(item.contains(show)).toBe(false);
		expect(item.parentElement).toBe(show.parentElement);
		expect(button()).toHaveAccessibleDescription('Made-up lasting reason.');
		expect(button()).toHaveAttribute('aria-disabled', 'true');
		expect(button()).not.toHaveAttribute('title');
	});

	it('names its data table button for the pump chart, its visible words unchanged, one width for both', async () => {
		withCanvas();
		render(PumpChart, { result: pumpResult(), name: 'P', prefs: SI_UNITS, system: READY });
		const toggle = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		expect(toggle.querySelector('.sr-only')).toHaveTextContent('of the pump chart');
		// Show and Hide stacked in one grid cell, the word not said invisible and aria-hidden, so the
		// swap changes the button's width by nothing and moves Download image beside it by nothing
		// (the owner's nits of 2026-11-12, item 1, docs/proposals/pumps-nits.md).
		expect(toggle.querySelector('[data-table-words]')).toHaveClass('grid');
		const words = () =>
			[...toggle.querySelectorAll('[data-table-words] > span')].map((w) => ({
				text: w.textContent,
				cell: w.classList.contains('col-start-1') && w.classList.contains('row-start-1'),
				invisible: w.classList.contains('invisible'),
				ariaHidden: w.getAttribute('aria-hidden')
			}));
		expect(words()).toEqual([
			{ text: 'Show data table', cell: true, invisible: false, ariaHidden: null },
			{ text: 'Hide data table', cell: true, invisible: true, ariaHidden: 'true' }
		]);
		await fireEvent.click(toggle);
		expect(toggle).toHaveAccessibleName('Hide data table of the pump chart');
		expect(words()).toEqual([
			{ text: 'Show data table', cell: true, invisible: true, ariaHidden: 'true' },
			{ text: 'Hide data table', cell: true, invisible: false, ariaHidden: null }
		]);
		await fireEvent.click(toggle);
		expect(toggle).toHaveAccessibleName('Show data table of the pump chart');
	});

	it('puts the actions under the strip and the notes after them: facts first, the method, the limits', async () => {
		withCanvas();
		const ontrace = vi.fn();
		const onchecks = vi.fn();
		render(PumpChart, {
			result: full(),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: withNpsha(),
			checks: limits,
			ontrace,
			onchecks
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const figure = screen.getByRole('figure');
		const notes = figure.querySelector('[data-pump-notes]')!;
		const toggle = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		const after = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		expect(after(figure.querySelector('[data-pump-strip]')!, toggle)).toBe(true);
		expect(after(toggle, notes)).toBe(true);
		const lines = [...notes.querySelectorAll('p')].map((p) =>
			p.textContent!.replace(/\s+/g, ' ').trim()
		);
		const order = [
			/^The head rises with flow from 0 to 5 L\/s \(amber\)/,
			/^NPSHa falls below NPSHr at about 22\.5 L\/s \(read from the drawn lines\)/,
			// Nit 5 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5): BEP and the dash in
			// words, not "(+)" and "(–)".
			/^Best efficiency point \(BEP\): 70 % at 12 L\/s/,
			/^Shutoff head \(the dash at zero flow\): 30 m\.$/,
			/^Efficiency: the duty's flow is outside the efficiency curve's data/,
			/^Shaft power ρgQH\/η over the flows/,
			/^Dashed: the pump curve extrapolated beyond its data \(0 to 30 L\/s/,
			/^System curve: the network of this solve, .* minus the EGL at the suction\. Trace of Transfer pump$/,
			/^Design-check limits drawn$/,
			/^Shaded blue \(POR\)/,
			/^Shaded grey \(AOR\)/,
			/^Dash-dot line: the minimum continuous stable flow/,
			/^Dotted on the NPSH panel/,
			/^Dashed on the power panel/,
			/^These are the limits of the design checks you turned on/
		];
		expect(lines).toHaveLength(order.length);
		order.forEach((pattern, i) => expect(lines[i]).toMatch(pattern));
		// The method's Trace is an inline link in its sentence, its name unchanged.
		const method = notes.querySelector('[data-pump-method]')!;
		const trace = within(method as HTMLElement).getByRole('button', {
			name: 'Trace of Transfer pump'
		});
		expect(trace).toHaveClass('underline');
		expect(trace).not.toHaveClass('min-h-11');
		await fireEvent.click(trace);
		expect(ontrace).toHaveBeenCalledTimes(1);
		// Go to Checks closes the limits.
		const go = screen.getByRole('button', { name: 'Go to Checks' });
		expect(after(notes.querySelectorAll('p')[order.length - 1]!, go)).toBe(true);
		expect(go.parentElement).toBe(notes.querySelector('[data-pump-checks]'));
		await fireEvent.click(go);
		expect(onchecks).toHaveBeenCalledTimes(1);
	});

	it('lists the design-check limits under their label, the closing sentence after them (pumps-results-layout.md §5.7 row 7, S3)', async () => {
		withCanvas();
		render(PumpChart, {
			result: full(),
			name: 'P',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03] as [number, number],
			checks: limits,
			onchecks: vi.fn()
		});
		const block = document.querySelector<HTMLElement>('[data-pump-checks]')!;
		const list = within(block).getByRole('list', { name: 'Design-check limits drawn' });
		const items = within(list)
			.getAllByRole('listitem')
			.map((li) => li.textContent!.trim());
		const paragraphs = [...block.querySelectorAll('p')].map((p) => p.textContent!.trim());
		// The label, each limit an item, then the closing sentence alone, then Go to Checks.
		expect(paragraphs[0]).toBe('Design-check limits drawn');
		expect(items.length).toBeGreaterThan(0);
		expect(paragraphs.slice(1, -1)).toEqual(items);
		expect(paragraphs.at(-1)).toMatch(/^These are the limits of the design checks you turned on/);
		expect(items.some((i) => /^These are the limits/.test(i))).toBe(false);
		expect(list.nextElementSibling!.textContent!.trim()).toBe(paragraphs.at(-1));
		expect(block.lastElementChild).toBe(screen.getByRole('button', { name: 'Go to Checks' }));
	});

	it('offers Go to Checks only with the limits shown and a way to go there', async () => {
		withCanvas();
		const props = {
			result: full(),
			name: 'P',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03] as [number, number],
			checks: limits
		};
		const view = render(PumpChart, props);
		expect(screen.getByText('Design-check limits drawn')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Go to Checks' })).toBeNull();
		await view.rerender({ ...props, onchecks: vi.fn() });
		expect(screen.getByRole('button', { name: 'Go to Checks' })).toBeInTheDocument();
		await fireEvent.click(
			within(screen.getByRole('group', { name: 'Show' })).getByRole('button', {
				name: 'Design checks'
			})
		);
		expect(screen.queryByText('Design-check limits drawn')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Go to Checks' })).toBeNull();
	});
});

// The second half of S1 (pumps-results-layout.md §5.3 item 2, §9 S1): the data region after the
// notes, the other cases under their own heading, their live line, the names tests pin, and every
// note of the figure on screen.
describe('pump chart data and other cases (pumps-results-layout.md §5.3)', () => {
	afterEach(() => localStorage.clear());

	const after = (a: Node, b: Node) =>
		!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
	const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
	/** Another case with a result for this pump (made-up test input). */
	const other = (key: string, name: string, values: Parameters<typeof pumpResult>[0] = {}) =>
		({
			key,
			name,
			result: pumpResult(values),
			stale: false,
			system: null
		}) satisfies OtherCaseInput;
	const offPump = { status: 'off', operatingFlow: 0, operatingHead: 0 } as const;
	const heldPump = { status: 'no_flow', operatingFlow: 0, operatingHead: 30 } as const;

	it('opens the data region after the notes: the operating point, the case shown, then the other cases’ curves', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult(),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: READY,
			caseName: 'Base case',
			tags: TAGS,
			others: [
				{ ...other('S1', 'Winter', { speed: 0.9 }), system: systemCurveResponse() },
				other('S2', 'Summer', offPump)
			],
			// Winter's system curve is given: the other cases' curves were asked for, so the case
			// in which the pump is off takes its slot (pumps-results-layout.md §9 S8 Slots).
			overlayCurves: true,
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const figure = screen.getByRole('figure');
		const toggle = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		await fireEvent.click(toggle);
		const region = figure.querySelector('[data-pump-data]')!;
		expect(region.id).toBe(toggle.getAttribute('aria-controls'));
		// After the notes, before the other cases' heading (§5.1 items 9 and 10).
		expect(after(figure.querySelector('[data-pump-notes]')!, region)).toBe(true);
		const heading = within(figure).getByRole('heading', {
			level: 4,
			name: 'Other cases on the pump chart'
		});
		expect(after(region, heading)).toBe(true);
		// The operating point first, then the case shown's tables, the other cases' last.
		expect(region.firstElementChild!.tagName).toBe('P');
		expect(squash(region.firstElementChild!.textContent)).toBe('Operating point: 20 L/s at 22 m');
		expect(
			within(region as HTMLElement)
				.getAllByRole('table')
				.map((t) => squash(t.querySelector('caption')!.textContent))
		).toEqual([
			'Operating points by case',
			'Pump curve at 100 % speed',
			'System curve',
			'System curve, Winter'
		]);
		// "Operating points by case": the case shown first, "Speed (%)" with bare numbers.
		const byCase = within(region as HTMLElement).getByRole('table', {
			name: 'Operating points by case'
		});
		expect(
			within(byCase)
				.getAllByRole('columnheader')
				.map((h) => h.textContent)
		).toEqual(['Case', 'Flow (L/s)', 'Head (m)', 'Speed (%)', 'State']);
		// Each row headed by its case's number in a box, then its words (owner, 2026-11-12, nit 5;
		// docs/proposals/pumps-nits.md item 5, slice 5b: in place of △ and □), the case shown's
		// "Base"; each row header heard with its number's words before its name.
		const rows = within(byCase)
			.getAllByRole('row')
			.slice(1)
			.map((r) => [
				shownCaseTag(within(r).getByRole('rowheader')),
				besideCaseTag(within(r).getByRole('rowheader')),
				...within(r)
					.getAllByRole('cell')
					.map((c) => c.textContent)
			]);
		expect(rows).toEqual([
			['Base', 'Base case (shown)', '20', '22', '100', 'Running'],
			['1', 'Winter', '20', '22', '90', 'Running'],
			['2', 'Summer', '—', '—', '—', 'Off']
		]);
		const heads = within(byCase).getAllByRole('rowheader');
		expect(heads[0]).toHaveAccessibleName('Base case (shown)');
		expect(heads[1]).toHaveAccessibleName('Case 1: Winter');
		expect(heads[2]).toHaveAccessibleName('Case 2: Summer');
		expect(designators(byCase)).toEqual([]);
		// A list below 640 px: its roles explicit, each value labelled by its column there.
		expect(byCase).toHaveAttribute('role', 'table');
		expect(byCase).toHaveClass('max-sm:block');
		expect(within(byCase).getAllByRole('cell')[0]).toHaveAttribute('data-label', 'Flow (L/s)');
		// The case shown's curves two-up only from a 40 rem container, never by the viewport: each
		// curve table a disclosure in the grid (§9 S7).
		const curve = disclosureOf('Pump curve at 100 % speed', region as HTMLElement);
		const grid = curve.parentElement!;
		expect(grid).toHaveClass('grid', '@min-[40rem]:grid-cols-2');
		expect(grid).not.toHaveClass('sm:grid-cols-2');
		expect(grid.parentElement).toHaveClass('@container');
		// Every box shades its edges when it scrolls sideways (each table's box: a region only
		// while it overflows since S7, measured in the tests of §9 S7 below).
		const boxes = within(region as HTMLElement)
			.getAllByRole('table')
			.map((t) => t.parentElement!);
		expect(boxes).toHaveLength(4);
		for (const box of boxes) expect(box).toHaveClass('scroll-shadow-x');
	});

	it('puts a held pump’s line at the top of the data region, before every table', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult(heldPump),
			name: 'P',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: READY,
			caseName: 'Base case',
			tags: TAGS,
			others: [{ ...other('S1', 'Winter'), system: systemCurveResponse() }],
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		const region = screen.getByRole('figure').querySelector('[data-pump-data]')!;
		// §5.3 The data region: "Operating point…" or "Held at zero flow: …" at its top.
		expect(region.firstElementChild!.tagName).toBe('P');
		expect(squash(region.firstElementChild!.textContent)).toBe(
			'Held at zero flow: 30 m across the pump'
		);
		expect(
			within(region as HTMLElement)
				.getAllByRole('table')
				.every((table) => after(region.firstElementChild!, table))
		).toBe(true);
	});

	it('shades the edges of every box in the data region, the panels’ and the speed range’s tables too', async () => {
		withCanvas();
		const curve = systemCurveResponse();
		[10, 8, 4, 1].forEach((v, i) => (curve.points[i]!.npshAvailable = v));
		render(PumpChart, {
			result: pumpResult({
				speed: 0.8,
				control: { mode: 'flow', setpoint: 0.016, state: 'active', setpointAchieved: true },
				operatingFlow: 0.016,
				operatingHead: 15,
				efficiencyCurve: [
					{ flow: 0.004, efficiency: 0.4 },
					{ flow: 0.012, efficiency: 0.7 },
					{ flow: 0.02, efficiency: 0.6 }
				],
				powerCurve: [
					{ flow: 0.004, shaftPower: 2000 },
					{ flow: 0.02, shaftPower: 5000 }
				],
				npshrCurve: [
					{ flow: 0, npshr: 1 },
					{ flow: 0.03, npshr: 4 }
				],
				speedCurves: [
					{
						limit: 'min',
						speed: 0.5,
						curve: [
							{ flow: 0, head: 7.5 },
							{ flow: 0.015, head: 3 }
						]
					},
					{
						limit: 'max',
						speed: 1,
						curve: [
							{ flow: 0, head: 30 },
							{ flow: 0.03, head: 12 }
						]
					}
				]
			}),
			name: 'P',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: { status: 'ready', curve },
			caseName: 'Base case',
			tags: TAGS,
			others: [{ ...other('S1', 'Winter'), system: systemCurveResponse() }],
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		const region = screen.getByRole('figure').querySelector('[data-pump-data]')!;
		// Each table's box (a region only while it overflows since S7), named by its caption.
		const boxes = within(region as HTMLElement)
			.getAllByRole('table')
			.map((t) => t.parentElement!);
		const at = '80 % speed (flow control)';
		expect(
			boxes.map((box) => squash(box.querySelector(':scope > table > caption')!.textContent))
		).toEqual([
			'Operating points by case',
			`Pump curve at ${at}`,
			'System curve',
			`Efficiency curve at ${at}`,
			`Shaft power curve at ${at}`,
			`NPSHr curve at ${at}`,
			'Pump curve at 50 % speed (minimum)',
			'Pump curve at 100 % speed (maximum)',
			'System curve, Winter'
		]);
		// §5.3: every box gets scroll-shadow-x.
		for (const box of boxes) expect(box).toHaveClass('scroll-shadow-x');
	});

	it('names each Why no head Details for its point, and the other case’s for its case', async () => {
		withCanvas();
		// Made-up test inputs: the point at 0.02 m³/s passes an FCV at its switch.
		const curve = systemCurveResponse('P1', [2]);
		curve.points[2] = systemCurvePoint({
			flow: 0.02,
			message: "made-up message about FCV 'V1'",
			reason: 'valve_at_switch',
			componentIds: ['V1'],
			openHead: 15.24,
			openHeadBound: 'lower'
		});
		const project = pumpTransferExample();
		project.components[2] = {
			type: 'valve',
			valveType: 'fcv',
			id: 'V1',
			name: 'Flow limiter',
			elevation: 0,
			status: 'active',
			setpoint: 0.02,
			ports: project.components[2]!.ports
		};
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			names: { project, solved: project },
			system: { status: 'ready', curve },
			caseName: 'Base case',
			tags: TAGS,
			others: [{ ...other('S1', 'Winter'), system: curve }]
		});
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		// Both open by default: each Why no head column has an entry (§9 S7).
		expect(disclosureOf('System curve').open).toBe(true);
		expect(disclosureOf('System curve, Winter').open).toBe(true);
		const summaries = [
			...screen.getByRole('table', { name: 'System curve' }).querySelectorAll('summary'),
			...screen.getByRole('table', { name: 'System curve, Winter' }).querySelectorAll('summary')
		].map((s) => squash(s.textContent));
		expect(summaries).toEqual([
			'Details of the point at 20 L/s',
			'Details of the point at 20 L/s, Winter'
		]);
		// Seen: the one word, as before.
		for (const summary of screen.getAllByText('Details')) {
			expect(summary.tagName).toBe('SUMMARY');
			expect(summary.querySelector('.sr-only')).toHaveTextContent(/^of the point at 20 L\/s/);
		}
	});

	it('puts the other cases under their own heading in the figure: the legend first, the case shown a tag, a grid', async () => {
		withCanvas();
		const ontick = vi.fn();
		const props = {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			caseName: 'Base case',
			tags: TAGS,
			others: [other('S1', 'Winter'), other('S2', 'Summer'), other('S3', 'Spring')],
			ontick,
			onoverlay: vi.fn()
		};
		const view = render(PumpChart, props);
		const figure = screen.getByRole('figure');
		const section = figure.querySelector('[data-pump-others]')!;
		const heading = within(figure).getByRole('heading', {
			level: 4,
			name: 'Other cases on the pump chart'
		});
		expect(section.firstElementChild).toBe(heading);
		expect(heading).toHaveClass('text-sm', 'font-semibold');
		// A rule above it (§5.2).
		expect(section).toHaveClass('border-t');
		const group = within(figure).getByRole('group', { name: 'Cases on the chart' });
		expect(section.contains(group)).toBe(true);
		expect(group.firstElementChild!.tagName).toBe('LEGEND');
		// The case shown: a tag, the grid's first item, not a control.
		const grid = group.querySelector('legend + div')!;
		expect(grid).toHaveClass('grid-cols-[repeat(auto-fill,minmax(13rem,1fr))]');
		const tag = grid.firstElementChild!;
		// Nit 5 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5): no ● before its words;
		// slice 5b: its case's number in a box, "Base", the one part hidden from a screen reader,
		// which hears its words alone ("Base case" says it).
		expect(designators(tag)).toEqual([]);
		expect(besideCaseTag(tag)).toBe('Base case (shown)');
		expect(shownCaseTag(tag)).toBe('Base');
		expect([...tag.querySelectorAll('[aria-hidden="true"]')]).toEqual([
			tag.querySelector('[data-case-tag]')
		]);
		expect(spokenWords(tag)).toBe('Base case (shown)');
		expect(tag).toHaveClass('rounded', 'bg-slate-100', 'text-xs');
		expect(tag).not.toHaveClass('border');
		expect(tag.querySelector('input')).toBeNull();
		// Each other case: its box, its case's number in a box in a 2.5 rem column of its own (nit 5,
		// slice 5b: in place of the 1 rem marker column), its name; its number's words heard first.
		const boxes = within(group).getAllByRole('checkbox');
		expect(boxes.map((b) => (b as HTMLInputElement).checked)).toEqual([true, true, true]);
		expect(
			boxes.map((b) => [shownCaseTag(b.closest('label')!), besideCaseTag(b.closest('label')!)])
		).toEqual([
			['1', 'Winter'],
			['2', 'Summer'],
			['3', 'Spring']
		]);
		for (const box of boxes) {
			const column = box.nextElementSibling!;
			expect(column).toHaveClass('w-10', 'shrink-0');
			expect(column.firstElementChild).toHaveAttribute('data-case-tag');
			expect(box.closest('label')).toHaveClass('min-h-11');
		}
		expect(designators(group)).toEqual([]);
		expect(boxes[0]).toHaveAccessibleName('Case 1: Winter');
		// Then the switch for their system curves, its cost visible and its description.
		const overlay = within(section as HTMLElement).getByRole('checkbox', {
			name: "Also show the other cases' system curves"
		});
		expect(after(group, overlay)).toBe(true);
		expect(overlay).toHaveAccessibleDescription(
			"Each is computed on request, one at a time, for that case's last solve; a curve costs about 41 solves of the network."
		);
		const cost = document.getElementById(overlay.getAttribute('aria-describedby')!)!;
		expect(cost).not.toHaveClass('sr-only');
		// At every width: jsdom applies no CSS, so its markup says (§6.4 item 8).
		expect(outOfSight(cost)).toBe(false);
		// Unticked, a box keeps its column and its case's number, so its name does not move (nit 5,
		// slice 5b: the number stays, where the marker went). The choice is the page's (§9 S8): the
		// box says so, and the page unticks it.
		await fireEvent.click(boxes[1]!);
		expect(ontick).toHaveBeenCalledExactlyOnceWith('S2', false);
		await view.rerender({ ...props, unticked: ['S2'] });
		const unticked = within(group).getByRole('checkbox', { name: 'Case 2: Summer' });
		expect((unticked as HTMLInputElement).checked).toBe(false);
		expect(unticked.nextElementSibling).toHaveClass('w-10');
		expect(shownCaseTag(unticked.nextElementSibling!)).toBe('2');
	});

	it('draws a capped box greyed, its name readable, aria-disabled and described by the cap', async () => {
		withCanvas();
		const names = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			tags: TAGS,
			others: names.map((n, i) => other(`S${i + 1}`, `Case ${n}`))
		});
		const group = screen.getByRole('group', { name: 'Cases on the chart' });
		// Each named with its case's number first (nit 5, slice 5b): S1 to S7 are 1 to 7.
		const box = (name: string) =>
			within(group).getByRole('checkbox', {
				name: `Case ${names.indexOf(name) + 1}: Case ${name}`
			});
		const cap = within(group).getByText('At most 6 cases at once.');
		expect(cap).not.toHaveClass('sr-only');
		expect(outOfSight(cap)).toBe(false);
		for (const name of ['F', 'G']) {
			const capped = box(name);
			expect(capped).toHaveAttribute('aria-disabled', 'true');
			expect(capped).not.toBeDisabled();
			expect(capped).toHaveClass('opacity-45');
			expect(capped).toHaveAccessibleDescription('At most 6 cases at once.');
			const label = capped.closest('label')!;
			expect(label).toHaveClass('cursor-not-allowed', 'text-slate-600');
			expect(label).not.toHaveClass('opacity-45');
			// Pressed, nothing changes.
			await fireEvent.click(capped);
			expect((capped as HTMLInputElement).checked).toBe(false);
		}
		const open = box('A');
		expect(open).not.toHaveAttribute('aria-disabled', 'true');
		expect(open).not.toHaveClass('opacity-45');
		expect(open.closest('label')).not.toHaveClass('cursor-not-allowed');
		expect(open).not.toHaveAccessibleDescription();
	});

	it('says beside an off case’s box, and in its description, that it has no operating point: only for an off pump', async () => {
		withCanvas();
		const NOTE = '(off in this case: no operating point)';
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			// An off case has its box while the other cases' system curves are asked for: then its
			// system curve is drawn (pumps-results-layout.md §9 S8 Slots).
			overlayCurves: true,
			tags: TAGS,
			others: [
				other('S1', 'Pump P off', offPump),
				other('S2', 'Check held', heldPump),
				other('S3', 'Running'),
				other('S4', 'Case D'),
				other('S5', 'Case E'),
				other('S6', 'Off past the cap', offPump)
			]
		});
		const group = screen.getByRole('group', { name: 'Cases on the chart' });
		// Each named with its case's number first (nit 5, slice 5b): S1 to S6 are 1 to 6.
		const numbers: Record<string, number> = {
			'Pump P off': 1,
			'Check held': 2,
			Running: 3,
			'Off past the cap': 6
		};
		const box = (name: string) =>
			within(group).getByRole('checkbox', { name: `Case ${numbers[name]}: ${name}` });
		const offBox = box('Pump P off');
		expect(offBox).toHaveAccessibleDescription(NOTE);
		const note = within(group).getAllByText(NOTE)[0]!;
		// Beside its box: outside its label, in the same grid item.
		expect(offBox.closest('label')!.contains(note)).toBe(false);
		expect(note.parentElement).toBe(offBox.closest('label')!.parentElement);
		expect(note).not.toHaveClass('sr-only');
		expect(outOfSight(note)).toBe(false);
		// The label keeps its name and words, its case's number in its box (nit 5, slice 5b).
		expect(besideCaseTag(offBox.closest('label')!)).toBe('Pump P off');
		expect(shownCaseTag(offBox.closest('label')!)).toBe('1');
		// A pump held at zero flow has its point drawn: no note; nor a running one.
		expect(box('Check held')).not.toHaveAccessibleDescription();
		expect(box('Running')).not.toHaveAccessibleDescription();
		// Off and capped: both, the note first.
		expect(box('Off past the cap')).toHaveAccessibleDescription(`${NOTE} At most 6 cases at once.`);
		expect(within(group).getAllByText(NOTE)).toHaveLength(2);
	});

	it('gives a case in which the pump is off no slot while the other cases’ system curves are off, and names it under the list; its slot back while they are on, which can push a case drawn past the cap (§9 S8 Slots)', async () => {
		withCanvas();
		const props = {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			tags: TAGS,
			others: [
				other('S1', 'Pump P off', offPump),
				other('S2', 'Case B'),
				other('S3', 'Check held', heldPump),
				other('S4', 'Case D'),
				other('S5', 'Case E'),
				other('S6', 'Case F'),
				{ ...other('S7', 'Also off', offPump), stale: true }
			],
			onoverlay: vi.fn()
		};
		const view = render(PumpChart, props);
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const group = screen.getByRole('group', { name: 'Cases on the chart' });
		// Each label's case number and words (nit 5, slice 5b: its case's number, in place of the
		// marker of its place).
		const names = () =>
			within(group)
				.getAllByRole('checkbox')
				.map((b) => [shownCaseTag(b.closest('label')!), besideCaseTag(b.closest('label')!)]);
		const FIVE = [
			['2', 'Case B'],
			['3', 'Check held'],
			['4', 'Case D'],
			['5', 'Case E'],
			['6', 'Case F']
		];
		const LINE =
			'Off in this case (no operating point): case 1: Pump P off; case 7: Also off (out of date).';
		// Off: no box for the two off cases, so the five others all fit, each with its case's
		// number; a held pump keeps its slot (its point is drawn).
		expect(names()).toEqual(FIVE);
		const line = group.querySelector('[data-pump-off-cases]')!;
		expect(line).toHaveTextContent(LINE);
		expect(line.tagName).toBe('P');
		expect(line).toHaveClass('hint');
		expect(line).not.toHaveClass('sr-only');
		expect(outOfSight(line)).toBe(false);
		// Under the list, before anything else of the fieldset.
		const grid = group.querySelector('legend + div')!;
		expect(grid.nextElementSibling).toBe(line);
		// Five boxes for five slots: no cap.
		expect(within(group).queryByText('At most 6 cases at once.')).toBeNull();
		for (const box of within(group).getAllByRole('checkbox')) {
			expect(box).not.toHaveAttribute('aria-disabled', 'true');
		}
		// The chart and its table draw the five, not the off cases (each "Case n: name", nit 5).
		const drawn = (charts.at(-1)!.config as Recorded).data.datasets.map((d) => d.label);
		expect(drawn).toEqual(
			expect.arrayContaining(['Case 2: Case B', 'Case 3: Check held', 'Case 6: Case F'])
		);
		expect(drawn.filter((label) => label.includes('Pump P off'))).toEqual([]);

		// On: the off cases take their slots, in order, so Case F, drawn before, goes past the
		// cap, and shows it as any capped case does; Also off is past it too.
		await view.rerender({ ...props, overlayCurves: true });
		expect(group.querySelector('[data-pump-off-cases]')).toBeNull();
		const numberOf: Record<string, number> = {
			'Pump P off': 1,
			'Case E': 5,
			'Case F': 6,
			'Also off (out of date)': 7
		};
		const box = (name: string) =>
			within(group).getByRole('checkbox', {
				name: `Case ${numberOf[name]}: ${name}`
			}) as HTMLInputElement;
		expect(box('Pump P off').checked).toBe(true);
		expect(box('Pump P off')).toHaveAccessibleDescription('(off in this case: no operating point)');
		expect(box('Case E').checked).toBe(true);
		expect(box('Case F').checked).toBe(false);
		expect(box('Case F')).toHaveAttribute('aria-disabled', 'true');
		expect(box('Case F')).toHaveClass('opacity-45');
		expect(box('Case F')).toHaveAccessibleDescription('At most 6 cases at once.');
		expect(box('Also off (out of date)')).toHaveAttribute('aria-disabled', 'true');
		expect(box('Also off (out of date)')).toHaveAccessibleDescription(
			'(off in this case: no operating point) At most 6 cases at once.'
		);
		expect(within(group).getByText('At most 6 cases at once.')).not.toHaveClass('sr-only');
		// Off again: the five come back, each with its case's number.
		await view.rerender({ ...props, overlayCurves: false });
		expect(names()).toEqual(FIVE);
		expect(group.querySelector('[data-pump-off-cases]')).toHaveTextContent(LINE);
	});

	it('draws the off line before “At most 6 cases at once.” when both are drawn (§5.6)', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			tags: TAGS,
			others: [
				other('S1', 'Pump P off', offPump),
				other('S2', 'Case B'),
				other('S3', 'Case C'),
				other('S4', 'Case D'),
				other('S5', 'Case E'),
				other('S6', 'Case F'),
				other('S7', 'Case G')
			],
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const group = screen.getByRole('group', { name: 'Cases on the chart' });
		// Six listed past a cap of five, and one case that takes no slot: both lines, in that order.
		const off = group.querySelector('[data-pump-off-cases]')!;
		expect(off).toHaveTextContent('Off in this case (no operating point): case 1: Pump P off.');
		const cap = within(group).getByText('At most 6 cases at once.');
		expect([...group.children].map((c) => c.tagName)).toEqual(['LEGEND', 'DIV', 'P', 'P']);
		expect(group.querySelector('legend + div')!.nextElementSibling).toBe(off);
		expect(off.nextElementSibling).toBe(cap);
	});

	// Nit 5, slice 5b (owner, 2026-11-12; Q2 "By list place"; docs/proposals/pumps-nits.md item 5):
	// replaces "draws each case's marker as the page gives it" (§9 S8 Markers): each case's number
	// is the page's (`tags`, caseTags of the project), never its place among the cases given or
	// drawn, and the case shown's too (`caseTag`).
	it('draws each case’s number as the page gives it, fixed by case, the case shown’s too (nit 5, slice 5b)', async () => {
		withCanvas();
		const props = {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			caseName: 'Autumn',
			caseTag: 2,
			tags: { '': 'Base', S1: 3, S2: 5, S3: 8, X: 2 } as const,
			others: [other('S1', 'Winter'), other('S2', 'Summer'), other('S3', 'Spring')],
			unticked: ['S1'],
			onoverlay: vi.fn()
		};
		render(PumpChart, props);
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const group = screen.getByRole('group', { name: 'Cases on the chart' });
		// Winter unticked: every case keeps its own number, none shifted up.
		expect(
			within(group)
				.getAllByRole('checkbox')
				.map((b) => [shownCaseTag(b.closest('label')!), besideCaseTag(b.closest('label')!)])
		).toEqual([
			['3', 'Winter'],
			['5', 'Summer'],
			['8', 'Spring']
		]);
		const shown = group.querySelector('legend + div')!.firstElementChild!;
		expect([shownCaseTag(shown), besideCaseTag(shown), spokenWords(shown)]).toEqual([
			'2',
			'Autumn (shown)',
			'Case 2: Autumn (shown)'
		]);
		// On the chart: slate rings, each named by its number (rule 4).
		const points = (charts[0]!.config as { data: { datasets: Record<string, unknown>[] } }).data
			.datasets;
		for (const [label, tag] of [
			['Case 5: Summer', '[5] Summer'],
			['Case 8: Spring', '[8] Spring']
		])
			expect(points.find((d) => d.label === label)).toMatchObject({
				caseLabel: tag,
				pointStyle: 'circle',
				pointRadius: 10,
				backgroundColor: 'transparent'
			});
		expect(points.some((d) => String(d.label).includes('Winter'))).toBe(false);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		expect(
			within(screen.getByRole('table', { name: 'Operating points by case' }))
				.getAllByRole('rowheader')
				.map((h) => [shownCaseTag(h), besideCaseTag(h)])
		).toEqual([
			['2', 'Autumn (shown)'],
			['5', 'Summer'],
			['8', 'Spring']
		]);
	});

	// Nit 5, slice 5b, rule 4 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5): the chart's
	// text alternative says what the canvas draws, each other case by the number its ring is tagged
	// with ("case 3: Winter"), the base case by its name, as the group chart's says "case 1: …".
	// It named them without numbers before this check (5b integration).
	it('names each other case drawn by its number in the chart’s text alternative, the base case by its name (nit 5, rule 4)', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			caseName: 'Autumn',
			caseTag: 2,
			tags: { '': 'Base', S1: 3, S2: 5, X: 2 },
			others: [
				other('', 'Base case'),
				other('S1', 'Winter', { operatingFlow: 0.012, operatingHead: 25 }),
				other('S2', 'Summer', heldPump)
			],
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		expect(screen.getByRole('img').getAttribute('aria-label')).toContain(
			"; other cases' operating points: Base case 20 L/s at 22 m; case 3: Winter 12 L/s at 25 m; case 5: Summer held at zero flow"
		);
	});

	it('keeps the other cases’ system curves’ line always there: polite, not a status, never busy, Cancel after it', async () => {
		withCanvas();
		const oncanceloverlay = vi.fn();
		const props = {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			tags: TAGS,
			others: [other('S1', 'Winter'), other('S2', 'Summer'), other('S3', 'Spring')],
			overlayCurves: true,
			onoverlay: vi.fn(),
			oncanceloverlay
		};
		const view = render(PumpChart, { ...props, system: READY, overlayProgress: null });
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const figure = screen.getByRole('figure');
		const line = figure.querySelector('[data-overlay-state]')!;
		const row = figure.querySelector('[data-overlay-row]')!;
		const overlay = screen.getByRole('checkbox', {
			name: "Also show the other cases' system curves"
		});
		// Idle: present and empty, its row out of sight.
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(line).toHaveAttribute('aria-atomic', 'true');
		expect(line).not.toHaveAttribute('role');
		expect(line.textContent).toBe('');
		expect(row).toHaveClass('sr-only');
		expect(row.firstElementChild).toBe(line);
		expect(after(overlay, line)).toBe(true);
		expect(line.closest('[aria-busy="true"]')).toBeNull();
		expect(within(figure).queryByRole('status')).toBeNull();
		expect(
			screen.queryByRole('button', { name: "Cancel the other cases' system curves" })
		).toBeNull();

		// Computing, while the canvas is busy too: the same element speaks, once drawn empty (F17),
		// outside anything busy.
		await linesDrawn();
		await view.rerender({
			...props,
			system: { status: 'loading' },
			overlayProgress: { done: 0, total: 3 }
		});
		expect(figure.querySelector('[data-overlay-state]')).toBe(line);
		expect(squash(line.textContent)).toBe('Computing system curves: 1 of 3…');
		expect(row).not.toHaveClass('sr-only');
		// Its spinner set at its first line, as the strip's marks are (§5.2).
		expect(line).toHaveClass('items-start');
		expect(line).not.toHaveClass('items-center');
		expect(line.querySelector('svg')).toHaveClass('mt-px');
		expect(screen.getByRole('img')).toHaveAttribute('aria-busy', 'true');
		expect(line.closest('[aria-busy="true"]')).toBeNull();
		expect(line.querySelector('button')).toBeNull();
		const cancel = screen.getByRole('button', { name: "Cancel the other cases' system curves" });
		expect(line.nextElementSibling).toBe(cancel);
		expect(cancel).toHaveAccessibleDescription('Computing system curves: 1 of 3…');
		expect(within(figure).queryByRole('status')).toBeNull();
		await fireEvent.click(cancel);
		expect(oncanceloverlay).toHaveBeenCalledTimes(1);

		await view.rerender({ ...props, system: READY, overlayProgress: { done: 2, total: 3 } });
		expect(squash(line.textContent)).toBe('Computing system curves: 3 of 3…');
		// Done: the same element, quiet again.
		await view.rerender({ ...props, system: READY, overlayProgress: null });
		expect(figure.querySelector('[data-overlay-state]')).toBe(line);
		expect(line.textContent).toBe('');
		expect(row).toHaveClass('sr-only');
	});

	it('holds “Also show the other cases’ system curves” where it was pressed while the curves it asked for arrive, until the last has answered or the user takes a step of their own (S8 second check LAYOUT-2)', async () => {
		withCanvas();
		const observers = fakeResizeObserver();
		// The pane that scrolls (the Results pane): its scroll the test's; the switch's top 300 px
		// down it, lower by what the content above it has grown and higher by what it scrolled.
		const pane = document.createElement('div');
		pane.style.overflowY = 'auto';
		document.body.append(pane);
		sizeBox(pane, { clientHeight: 600, scrollHeight: 4000 });
		let scrolled = 0;
		let grown = 0;
		Object.defineProperty(pane, 'scrollTop', {
			configurable: true,
			get: () => scrolled,
			set: (v: number) => (scrolled = v)
		});
		const props = {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			tags: TAGS,
			others: [other('S1', 'Winter'), other('S2', 'Summer'), other('S3', 'Spring')],
			oncanceloverlay: vi.fn()
		};
		// As the Pumps view: the curves asked for are computed one at a time when switched on;
		// once computed (`cached`), each is drawn at the press, its table with it.
		let cached = false;
		const onoverlay = (on: boolean) => {
			if (cached) grown += on ? 168 : -168;
			void view.rerender({
				...props,
				overlayCurves: on,
				overlayProgress: on && !cached ? { done: 0, total: 3 } : null,
				onoverlay
			});
		};
		const view = render(PumpChart, {
			target: pane,
			props: { ...props, overlayCurves: false, overlayProgress: null, onoverlay }
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const figure = screen.getByRole('figure');
		const box = screen.getByRole('checkbox', { name: "Also show the other cases' system curves" });
		box.getBoundingClientRect = () => ({ top: 300 + grown - scrolled }) as DOMRect;
		// With its data table hidden the chart watches no box of its own.
		const watchedBefore = observers.watched();
		expect(watchedBefore).toBe(0);
		/** Switch the curves on, a press; held while they are computed. */
		const switchOn = async () => {
			await fireEvent.click(box);
			expect(box).toBeChecked();
			await vi.waitFor(() => expect(observers.watched()).toBe(watchedBefore + 1));
		};
		/** A curve answers: its table above the switch (56 px), the figure taller. */
		const answer = () => {
			grown += 56;
			observers.resize(figure);
		};
		const top = () => box.getBoundingClientRect().top;

		for (const step of ['pointerdown', 'keydown', 'wheel', 'touchstart']) {
			await switchOn();
			answer();
			expect(top(), `held as a curve answers, before a ${step}`).toBe(300);
			// The user's own step: the switch let go, so their scroll and their next press are their
			// own; a curve answering after it moves it as the browser would.
			window.dispatchEvent(new Event(step));
			expect(observers.watched(), `let go at a ${step}`).toBe(watchedBefore);
			const at = scrolled;
			answer();
			expect(scrolled, `not scrolled after a ${step}`).toBe(at);
			// Back where it was, then off: nothing held while they are off.
			grown -= 112;
			scrolled -= 56;
			await fireEvent.click(box);
			expect(box).not.toBeChecked();
			await tick();
			expect(observers.watched()).toBe(watchedBefore);
		}
		// The last curve answered: its table is drawn, the switch kept in place once more and let go.
		await switchOn();
		answer();
		expect(top()).toBe(300);
		grown += 56;
		await view.rerender({ ...props, overlayCurves: true, overlayProgress: null, onoverlay });
		expect(top(), 'held as the last curve answers').toBe(300);
		expect(observers.watched(), 'let go once every curve has answered').toBe(watchedBefore);
		// Every curve computed: drawn at the press, which keeps the switch in place itself (S8
		// review LAYOUT-1); nothing is held, since nothing is left to arrive.
		await fireEvent.click(box);
		expect(top()).toBe(300);
		cached = true;
		await fireEvent.click(box);
		expect(box).toBeChecked();
		await tick();
		await tick();
		expect(top(), 'kept in place by the press').toBe(300);
		expect(observers.watched(), 'nothing held with every curve computed').toBe(watchedBefore);
		await fireEvent.click(box);
		await tick();
		expect(top()).toBe(300);
		// Switched on with curves to compute, then the chart gone (another pump shown): let go.
		cached = false;
		await switchOn();
		view.unmount();
		expect(observers.watched()).toBe(0);
		observers.restore();
		pane.remove();
	});

	it('draws the other cases’ line empty before it speaks, when mounted with their curves being computed (F17)', async () => {
		// A pump chosen whose own curve is ready, with the other cases' curves asked for: the chart is
		// mounted as their requests start (§7 Live regions).
		withCanvas();
		render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: READY,
			tags: TAGS,
			others: [other('S1', 'Winter'), other('S2', 'Summer')],
			overlayCurves: true,
			onoverlay: vi.fn(),
			overlayProgress: { done: 0, total: 2 },
			oncanceloverlay: vi.fn()
		});
		const line = screen.getByRole('figure').querySelector('[data-overlay-state]')!;
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(line.textContent).toBe('');
		await nextFrame();
		expect(line.textContent).toBe('');
		await vi.waitFor(() =>
			expect(squash(line.textContent)).toBe('Computing system curves: 1 of 2…')
		);
		expect(screen.getByRole('figure').querySelector('[data-overlay-state]')).toBe(line);
		expect(
			screen.getByRole('button', { name: "Cancel the other cases' system curves" })
		).toHaveAccessibleDescription('Computing system curves: 1 of 2…');
	});

	it('keeps every name the tests and the guides pin', async () => {
		withCanvas();
		const observers = fakeResizeObserver();
		render(PumpChart, {
			result: pumpResult(),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			system: READY,
			caseName: 'Base case',
			tags: TAGS,
			others: [{ ...other('S1', 'Winter'), system: systemCurveResponse() }],
			onoverlay: vi.fn(),
			overlayProgress: { done: 0, total: 1 },
			oncanceloverlay: vi.fn(),
			ontrace: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const figure = within(
			screen.getByRole('figure', { name: 'Pump and system curves: Transfer pump, Base case' })
		);
		expect(figure.getByRole('slider', { name: 'Read at flow' })).toBeInTheDocument();
		expect(figure.getByRole('button', { name: 'Trace of Transfer pump' })).toBeInTheDocument();
		expect(figure.getByRole('group', { name: 'Cases on the chart' })).toBeInTheDocument();
		expect(
			figure.getByRole('checkbox', { name: "Also show the other cases' system curves" })
		).toBeInTheDocument();
		expect(
			figure.getByRole('button', { name: "Cancel the other cases' system curves" })
		).toBeInTheDocument();
		await fireEvent.click(
			figure.getByRole('button', { name: 'Show data table of the pump chart' })
		);
		expect(figure.getByRole('button', { name: 'Hide data table of the pump chart' })).toBeVisible();
		for (const name of [
			'Operating points by case',
			'Pump curve at 100 % speed',
			'System curve',
			'System curve, Winter'
		]) {
			const table = figure.getByRole('table', { name });
			expect(table).toBeInTheDocument();
			// A curve table in its disclosure, opened first (§9 S7); then a named region and a Tab
			// stop while its box overflows: the table wider.
			if (name !== 'Operating points by case') await openTable(name);
			const box = table.parentElement!;
			sizeBox(box, { clientWidth: 300, scrollWidth: 500, clientHeight: 200, scrollHeight: 200 });
			observers.resize(box);
			expect(figure.getByRole('region', { name })).toBe(box);
			expect(figure.getByRole('region', { name })).toHaveAttribute('tabindex', '0');
		}
		observers.restore();
	});

	/**
	 * The words-on-screen guard (§10, §6.4 item 3): every one of chartNotes' lines, the image's
	 * footer words, is on screen word for word, at every width not visually hidden or hidden (by
	 * any class variant, attribute or inline style) and not in a closed disclosure, whatever the
	 * state of the chart, its system curve and its panels, chips and limits shown.
	 */
	describe('every note of the figure on screen, word for word', () => {
		// Only the words in sight are read, so a line hidden in a child of a visible <p> is off
		// screen (wordsInSight, testing/helpers.ts).
		const onScreen = (figure: HTMLElement, line: string) =>
			[...figure.querySelectorAll('p, span')].some(
				(el) => squash(wordsInSight(el)).includes(line) && !outOfSight(el)
			);

		it('reads only the words in sight: a line hidden inside a visible one is off screen', () => {
			const figure = document.createElement('figure');
			figure.innerHTML =
				'<p class="text-xs"><span class="max-sm:sr-only">Efficiency at 80 % speed: made up.</span></p>' +
				'<p class="text-xs">Shown <span class="sr-only">hidden</span> words.</p>';
			expect(onScreen(figure, 'Efficiency at 80 % speed: made up.')).toBe(false);
			expect(onScreen(figure, 'Shown hidden words.')).toBe(false);
			// The control: the words in sight are on screen.
			expect(onScreen(figure, 'Shown words.')).toBe(true);
		});

		const full = pumpResult({
			operatingFlow: 0.034,
			operatingHead: 7.5,
			inCurveRange: false,
			efficiencyCurve: [
				{ flow: 0.004, efficiency: 0.4 },
				{ flow: 0.012, efficiency: 0.7 },
				{ flow: 0.02, efficiency: 0.6 }
			],
			bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false },
			powerCurve: [
				{ flow: 0.004, shaftPower: 2000 },
				{ flow: 0.02, shaftPower: 5000 }
			],
			npshrCurve: [
				{ flow: 0, npshr: 1 },
				{ flow: 0.03, npshr: 4 }
			],
			risingHeadRanges: [{ flowMin: 0, flowMax: 0.005 }]
		});
		const npsha = () => {
			const curve = systemCurveResponse();
			[10, 8, 4, 1].forEach((v, i) => (curve.points[i]!.npshAvailable = v));
			return curve;
		};
		const limits: PumpChecksInput = {
			checks: {
				npshMargin: { minimumMargin: 1, source: { kind: 'user' } },
				operatingRegion: { preferredMin: 0.7, preferredMax: 1.2, source: { kind: 'user' } }
			},
			curve: null,
			sources: { npshMargin: 'your values', operatingRegion: 'your values' }
		};
		/** The limits from the curve's manufacturer data too: the AOR, the minimum flow, the motor. */
		const curveLimits: PumpChecksInput = {
			...limits,
			curve: {
				id: 'C1',
				name: 'Curve',
				points: [
					{ flow: 0, head: 30 },
					{ flow: 0.03, head: 12 }
				],
				allowableOperatingRegion: { flowMin: 0.004, flowMax: 0.025 },
				minimumContinuousStableFlow: 0.003,
				motorRatedPower: 5500
			}
		};
		/** A flow-controlled pump at 80 % speed with its speed range and lines of constant efficiency. */
		const controlled = pumpResult({
			speed: 0.8,
			control: { mode: 'flow', setpoint: 0.016, state: 'active', setpointAchieved: true },
			operatingFlow: 0.016,
			operatingHead: 15,
			efficiencyCurve: full.efficiencyCurve,
			bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false },
			shutoffHead: { head: 19.2, extrapolated: false },
			speedCurves: [
				{
					limit: 'min',
					speed: 0.5,
					curve: [
						{ flow: 0, head: 7.5 },
						{ flow: 0.015, head: 3 }
					]
				},
				{
					limit: 'max',
					speed: 1,
					curve: [
						{ flow: 0, head: 30 },
						{ flow: 0.03, head: 12 }
					]
				}
			],
			isoEfficiencyLines: [
				{
					efficiency: 0.7,
					best: true,
					ratedFlow: 0.015,
					points: [
						{ flow: 0.0075, head: 6.25 },
						{ flow: 0.015, head: 25 }
					]
				},
				{
					efficiency: 0.65,
					best: false,
					ratedFlow: 0.01,
					points: [
						{ flow: 0.005, head: 7 },
						{ flow: 0.01, head: 28 }
					]
				}
			]
		});
		/**
		 * Efficiency rising to the end of its data (no best efficiency point), the curve's data
		 * starting above zero flow (its shutoff extrapolated) and an NPSHr curve.
		 */
		const noBest = pumpResult({
			curve: [
				{ flow: 0.005, head: 29 },
				{ flow: 0.02, head: 22 },
				{ flow: 0.03, head: 12 }
			],
			shutoffHead: { head: 30.5, extrapolated: true },
			efficiencyCurve: [
				{ flow: 0.005, efficiency: 0.4 },
				{ flow: 0.025, efficiency: 0.72 }
			],
			npshrCurve: [
				{ flow: 0.005, npshr: 1.5 },
				{ flow: 0.03, npshr: 5 }
			]
		});
		const ALL: PanelKey[] = ['head', 'efficiency', 'power', 'npsh'];
		const cases: {
			name: string;
			result: ReturnType<typeof pumpResult>;
			system: SystemCurveState | undefined;
			checks?: PumpChecksInput;
			/** Lines the case must give, so the guard is known to read them. */
			covers?: RegExp[];
		}[] = [
			{
				name: 'every panel, a rising range, the crossing and the limits',
				result: full,
				system: { status: 'ready', curve: npsha() },
				checks: limits,
				covers: [/^The head rises with flow/, /^NPSHa falls below NPSHr/]
			},
			{
				name: 'held at zero flow, its curve being computed',
				result: pumpResult(heldPump),
				system: { status: 'loading' }
			},
			{
				name: 'off, its curve cancelled',
				result: pumpResult(offPump),
				system: { status: 'cancelled', by: 'user' }
			},
			{
				name: 'its curve failed',
				result: pumpResult(),
				system: { status: 'error', message: 'Made-up message.' }
			},
			{
				name: 'points without a head',
				result: pumpResult(),
				system: { status: 'ready', curve: systemCurveResponse('P1', [1]) },
				covers: [/^1 of 4 system-curve points have no head/]
			},
			{ name: 'no system curve asked for', result: pumpResult(), system: undefined },
			{
				name: 'a speed-controlled pump at 80 %: its speed range and its efficiency at that speed',
				result: controlled,
				system: { status: 'ready', curve: systemCurveResponse() },
				covers: [/^Speed range of the flow control/, /^Efficiency at 80 % speed/]
			},
			{
				name: 'no best efficiency point, the shutoff extrapolated, NPSHa to come with its curve',
				result: noBest,
				system: { status: 'cancelled', by: 'goalSeek' },
				covers: [
					/^No best efficiency point is marked/,
					// Nit 5: the dash in words, not "(–)".
					/^Shutoff head \(the dash at zero flow\): [\d.]+ m, extrapolated along the curve's start slope/,
					/^NPSHa along the system curve is drawn once the system curve is computed\.$/
				]
			},
			{
				name: 'every limit the curve’s data give: the AOR, the minimum flow, the motor’s rating',
				result: full,
				system: { status: 'ready', curve: npsha() },
				checks: curveLimits,
				covers: [/^Shaded grey \(AOR\)/, /^Dash-dot line/, /^Dashed on the power panel/]
			}
		];
		for (const c of cases) {
			it(c.name, async () => {
				withCanvas();
				render(PumpChart, {
					result: c.result,
					name: 'P',
					prefs: SI_UNITS,
					ratedRange: [0, 0.03],
					system: c.system,
					...(c.checks ? { checks: c.checks } : {}),
					othersControlled: true,
					ontrace: vi.fn(),
					onretry: vi.fn(),
					oncancel: vi.fn()
				});
				await vi.waitFor(() => expect(charts).toHaveLength(1));
				await linesDrawn();
				const curve = c.system?.status === 'ready' ? c.system.curve : null;
				const data = pumpChartData(c.result, SI_UNITS, [0, 0.03], curve, null, c.checks ?? null);
				// Every chip on, as the chart starts: its panels, the speed range and the limits.
				const notes = chartNotes({
					data,
					result: c.result,
					system: c.system,
					othersControlled: true,
					shown: ALL.filter((p) => data.panels.includes(p)),
					speedShown: !!data.facts.speedRange,
					checksShown: !!data.checks
				});
				const lines = [
					notes.pump,
					notes.curve?.text,
					notes.method,
					notes.extrapolated,
					...notes.panels,
					...notes.facts,
					...notes.checks
				].filter((line): line is string => !!line);
				expect(lines.length).toBeGreaterThan(1);
				for (const pattern of c.covers ?? []) {
					expect(
						lines.some((line) => pattern.test(line)),
						String(pattern)
					).toBe(true);
				}
				const figure = screen.getByRole('figure');
				for (const line of lines) expect(onScreen(figure, line), line).toBe(true);
			});
		}
	});
});

/**
 * S7 (pumps-results-layout.md §9 S7, §10 S7): each curve table a disclosure "{caption} ({n}
 * points)", full height when open, open by default where the chart cannot be drawn or its Why no
 * head column has entries; a box a Tab stop and a named region only while it overflows, on either
 * axis; whether the data table is shown remembered in this browser, storage refused or empty.
 */
describe('the pump chart’s data without scroll traps (pumps-results-layout.md §9 S7)', () => {
	const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
	/** Every curve table's disclosure, in order: its table's name, its summary, open or not. */
	const disclosures = () =>
		[...document.querySelectorAll<HTMLDetailsElement>('details[data-curve-table]')].map((d) => ({
			table: squash(d.querySelector('caption')!.textContent),
			summary: squash(d.querySelector(':scope > summary')!.textContent),
			rows: d.querySelectorAll('tbody tr').length,
			open: d.open
		}));
	/** A pump with every panel and a speed range (made-up test input), as the panels' tests use. */
	const everyPanel = () =>
		pumpResult({
			efficiencyCurve: [
				{ flow: 0.004, efficiency: 0.4 },
				{ flow: 0.012, efficiency: 0.7 },
				{ flow: 0.02, efficiency: 0.6 }
			],
			powerCurve: [
				{ flow: 0.004, shaftPower: 2000 },
				{ flow: 0.02, shaftPower: 5000 }
			],
			npshrCurve: [
				{ flow: 0, npshr: 1 },
				{ flow: 0.015, npshr: 2 },
				{ flow: 0.03, npshr: 4 }
			],
			speedCurves: [
				{
					limit: 'min',
					speed: 0.5,
					curve: [
						{ flow: 0, head: 7.5 },
						{ flow: 0.015, head: 3 }
					]
				},
				{
					limit: 'max',
					speed: 1,
					curve: [
						{ flow: 0, head: 30 },
						{ flow: 0.01, head: 28 },
						{ flow: 0.02, head: 22 },
						{ flow: 0.03, head: 12 },
						{ flow: 0.035, head: 5 }
					]
				}
			]
		});
	const winter = (system = systemCurveResponse()) =>
		({
			key: 'S1',
			name: 'Winter',
			result: pumpResult(),
			stale: false,
			system
		}) satisfies OtherCaseInput;
	const showTable = () =>
		fireEvent.click(screen.getByRole('button', { name: 'Show data table of the pump chart' }));

	it('draws each curve table as a disclosure named “{caption} ({n} points)”, its count its rows, closed while the chart is drawn and no point lacks a head', async () => {
		withCanvas();
		render(PumpChart, {
			result: everyPanel(),
			name: 'P',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: READY,
			caseName: 'Base case',
			tags: TAGS,
			others: [winter()],
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await showTable();
		const drawn = disclosures();
		// Every curve table, in the region's order; the counts of the inputs: the system curve's 4
		// points, 3 of efficiency, 2 of shaft power, 3 of NPSHr, the speed range's 2 and 5.
		expect(drawn.map(({ table, summary, open }) => ({ table, summary, open }))).toEqual([
			{
				table: 'Pump curve at 100 % speed',
				summary: `Pump curve at 100 % speed (${drawn[0]!.rows} points)`,
				open: false
			},
			{ table: 'System curve', summary: 'System curve (4 points)', open: false },
			{
				table: 'Efficiency curve at 100 % speed',
				summary: 'Efficiency curve at 100 % speed (3 points)',
				open: false
			},
			{
				table: 'Shaft power curve at 100 % speed',
				summary: 'Shaft power curve at 100 % speed (2 points)',
				open: false
			},
			{
				table: 'NPSHr curve at 100 % speed',
				summary: 'NPSHr curve at 100 % speed (3 points)',
				open: false
			},
			{
				table: 'Pump curve at 50 % speed (minimum)',
				summary: 'Pump curve at 50 % speed (minimum) (2 points)',
				open: false
			},
			{
				table: 'Pump curve at 100 % speed (maximum)',
				summary: 'Pump curve at 100 % speed (maximum) (5 points)',
				open: false
			},
			{ table: 'System curve, Winter', summary: 'System curve, Winter (4 points)', open: false }
		]);
		// Each count is the rows its table lists (the pump curve's 4 points of data).
		for (const d of drawn) expect(d.summary).toBe(`${d.table} (${d.rows} points)`);
		expect(drawn[0]!.rows).toBe(4);
		// "Operating points by case" is no curve: a table, never folded.
		const byCase = screen.getByRole('table', { name: 'Operating points by case' });
		expect(byCase.closest('details')).toBeNull();
		// Each summary a native disclosure's (.more-summary), the count in the regular weight.
		for (const d of document.querySelectorAll('details[data-curve-table]')) {
			const summary = d.querySelector(':scope > summary')!;
			expect(summary).toHaveClass('more-summary');
			expect(summary.querySelector('.font-normal')!.textContent).toMatch(/^\(\d+ points?\)$/);
			// Its words and count in sight: since the caption is hidden, the table's one visible
			// title (S7 review W2, MUT-SUMMARY-HIDDEN).
			const caption = squash(d.querySelector('caption')!.textContent);
			const rows = d.querySelectorAll('tbody tr').length;
			expect(squash(wordsInSight(summary))).toBe(`${caption} (${rows} points)`);
			// Full height when open: its box scrolls sideways only, never down inside the pane.
			const box = d.querySelector('table')!.parentElement!;
			expect(box).toHaveClass('overflow-x-auto', 'scroll-shadow-x');
			expect(box.className).not.toMatch(/max-h-/);
			// Its caption visually hidden, the summary showing the same words; still the name.
			expect(d.querySelector('caption')).toHaveClass('sr-only');
			expect(outOfSight(d.querySelector('caption')!)).toBe(true);
		}
		// Opened, its rows are in sight; closed, they are not (a closed disclosure hides them).
		const pump = disclosureOf('Pump curve at 100 % speed');
		expect(outOfSight(pump.querySelector('tbody td')!)).toBe(true);
		await openTable('Pump curve at 100 % speed');
		expect(outOfSight(pump.querySelector('tbody td')!)).toBe(false);
	});

	it('says “1 point” for a curve of one point', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult({ efficiencyCurve: [{ flow: 0.01, efficiency: 0.6 }] }),
			name: 'P',
			prefs: SI_UNITS,
			system: READY
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await showTable();
		const one = disclosures().filter((d) => d.rows === 1);
		for (const d of one) expect(d.summary).toBe(`${d.table} (1 point)`);
		expect(one.map((d) => d.table)).toEqual(['Efficiency curve at 100 % speed']);
	});

	it('opens every curve table by default where the chart cannot be drawn, the data region forced open', async () => {
		render(PumpChart, {
			result: everyPanel(),
			name: 'P',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: READY,
			caseName: 'Base case',
			tags: TAGS,
			others: [winter()],
			onoverlay: vi.fn()
		});
		expect(
			await screen.findByText(/The chart cannot be drawn in this browser/)
		).toBeInTheDocument();
		const drawn = disclosures();
		expect(drawn).toHaveLength(8);
		for (const d of drawn) expect(d.open, d.table).toBe(true);
	});

	it('opens by default a system curve whose Why no head column has entries, the shown case’s and another case’s alike; the rest stay closed', async () => {
		withCanvas();
		const view = render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'ready', curve: systemCurveResponse('P1', [1]) },
			caseName: 'Base case',
			tags: TAGS,
			others: [winter(systemCurveResponse('P1', [3])), { ...winter(), key: 'S2', name: 'Summer' }],
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await showTable();
		expect(disclosures().map(({ table, open }) => [table, open])).toEqual([
			['Pump curve at 100 % speed', false],
			['System curve', true],
			['System curve, Winter', true],
			['System curve, Summer', false]
		]);
		// Its reason in sight, one press away no more (D10's owner rule).
		const reason = within(screen.getByRole('table', { name: 'System curve' })).getByText(
			'made-up reason: not converged'
		);
		expect(outOfSight(reason)).toBe(false);
		// The default only ever opens a table (§7 Disclosures: "None closes itself"; S7 review
		// DATA-1): computed again with every point solved, the table stays open while drawn. Each
		// step waits a task, for the toggle event a drawn opening fires (S7 review MUT-TOGGLE).
		const task = () => new Promise((resolve) => setTimeout(resolve, 0));
		await task();
		await view.rerender({ system: READY });
		await tick();
		await task();
		expect(disclosureOf('System curve').open).toBe(true);
		// Drawn anew (the data region hidden and shown): no choice was made, so it takes the
		// default afresh, closed with every point solved.
		const hide = screen.getByRole('button', { name: 'Hide data table of the pump chart' });
		await fireEvent.click(hide);
		await showTable();
		await task();
		expect(disclosureOf('System curve').open).toBe(false);
		// A point without a head again: opened by default in place, which is no choice either.
		await view.rerender({ system: { status: 'ready', curve: systemCurveResponse('P1', [1]) } });
		await tick();
		await task();
		expect(disclosureOf('System curve').open).toBe(true);
		await view.rerender({ system: READY });
		await fireEvent.click(
			screen.getByRole('button', { name: 'Hide data table of the pump chart' })
		);
		await showTable();
		await task();
		expect(disclosureOf('System curve').open).toBe(false);
	});

	it('keeps the user’s choice of each curve table while the data region is hidden and shown, and over a new default', async () => {
		withCanvas();
		const view = render(PumpChart, {
			result: pumpResult(),
			name: 'P',
			prefs: SI_UNITS,
			system: { status: 'ready', curve: systemCurveResponse('P1', [1]) }
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await showTable();
		// Opened by the user, closed by the user (open by default): each a toggle event.
		await openTable('Pump curve at 100 % speed');
		const system = disclosureOf('System curve');
		expect(system.open).toBe(true);
		await fireEvent.click(system.querySelector(':scope > summary')!);
		expect(system.open).toBe(false);
		await vi.waitFor(() => expect(disclosureOf('System curve').open).toBe(false));
		await new Promise((resolve) => setTimeout(resolve, 0)); // the toggle events' task
		const hide = screen.getByRole('button', { name: 'Hide data table of the pump chart' });
		await fireEvent.click(hide);
		expect(screen.queryByRole('table', { name: 'System curve' })).toBeNull();
		await fireEvent.click(hide);
		expect(disclosureOf('Pump curve at 100 % speed').open).toBe(true);
		expect(disclosureOf('System curve').open).toBe(false);
		// A new default (every point solved, then one missing again) leaves a choice alone.
		await view.rerender({ system: READY });
		await view.rerender({ system: { status: 'ready', curve: systemCurveResponse('P1', [2]) } });
		await tick();
		expect(disclosureOf('System curve').open).toBe(false);
		expect(disclosureOf('Pump curve at 100 % speed').open).toBe(true);
	});

	it('keeps the choice of every kind of curve table: a panel’s, a speed range’s and another case’s system curve, while the data region is hidden and shown (S7 review MUT-BIND)', async () => {
		withCanvas();
		render(PumpChart, {
			result: everyPanel(),
			name: 'P',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03],
			system: READY,
			caseName: 'Base case',
			tags: TAGS,
			others: [winter(systemCurveResponse('P1', [3]))],
			onoverlay: vi.fn()
		});
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		await showTable();
		// Opened by the user: a panel's table and a speed range's; closed by the user: another
		// case's system curve, open by default (a point without a head).
		await openTable('Efficiency curve at 100 % speed');
		await openTable('Pump curve at 50 % speed (minimum)');
		const winterFold = disclosureOf('System curve, Winter');
		expect(winterFold.open).toBe(true);
		await fireEvent.click(winterFold.querySelector(':scope > summary')!);
		expect(winterFold.open).toBe(false);
		await new Promise((resolve) => setTimeout(resolve, 0)); // the toggle events' task
		const hide = screen.getByRole('button', { name: 'Hide data table of the pump chart' });
		await fireEvent.click(hide);
		expect(screen.queryByRole('table', { name: 'System curve, Winter' })).toBeNull();
		await fireEvent.click(hide);
		expect(disclosures().map(({ table, open }) => [table, open])).toEqual([
			['Pump curve at 100 % speed', false],
			['System curve', false],
			['Efficiency curve at 100 % speed', true],
			['Shaft power curve at 100 % speed', false],
			['NPSHr curve at 100 % speed', false],
			['Pump curve at 50 % speed (minimum)', true],
			['Pump curve at 100 % speed (maximum)', false],
			['System curve, Winter', false]
		]);
	});

	it('remembers in this browser whether the data table is shown, and starts hidden with nothing remembered', async () => {
		withCanvas();
		const props = { result: pumpResult(), name: 'P', prefs: SI_UNITS, system: READY };
		const first = render(PumpChart, props);
		const toggle = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(localStorage.getItem('opensolve-pipe:pump-chart-data-table')).toBeNull();
		await fireEvent.click(toggle);
		expect(localStorage.getItem('opensolve-pipe:pump-chart-data-table')).toBe('shown');
		first.unmount();
		// Another chart (a reload, another pump): shown, as left.
		const second = render(PumpChart, { ...props, name: 'Q' });
		const shown = screen.getByRole('button', { name: 'Hide data table of the pump chart' });
		expect(shown).toHaveAttribute('aria-expanded', 'true');
		expect(document.getElementById(shown.getAttribute('aria-controls')!)).not.toBeNull();
		await fireEvent.click(shown);
		expect(localStorage.getItem('opensolve-pipe:pump-chart-data-table')).toBeNull();
		second.unmount();
		render(PumpChart, props);
		expect(
			screen.getByRole('button', { name: 'Show data table of the pump chart' })
		).toHaveAttribute('aria-expanded', 'false');
		// The group chart's choice is its own.
		expect(localStorage.getItem('opensolve-pipe:pump-group-chart-data-table')).toBeNull();
	});

	it('works with storage refused: starts hidden, shows and hides on request', async () => {
		withCanvas();
		const refuse = () => {
			throw new DOMException('Storage refused', 'SecurityError');
		};
		const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(refuse);
		const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(refuse);
		const remove = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(refuse);
		try {
			render(PumpChart, { result: pumpResult(), name: 'P', prefs: SI_UNITS, system: READY });
			expect(get).toHaveBeenCalledWith('opensolve-pipe:pump-chart-data-table');
			const toggle = screen.getByRole('button', { name: 'Show data table of the pump chart' });
			expect(toggle).toHaveAttribute('aria-expanded', 'false');
			await fireEvent.click(toggle);
			expect(set).toHaveBeenCalled();
			expect(toggle).toHaveAttribute('aria-expanded', 'true');
			expect(screen.getByRole('table', { name: 'System curve' })).toBeInTheDocument();
			await fireEvent.click(toggle);
			expect(remove).toHaveBeenCalled();
			expect(toggle).toHaveAttribute('aria-expanded', 'false');
			expect(screen.queryByRole('table', { name: 'System curve' })).toBeNull();
		} finally {
			get.mockRestore();
			set.mockRestore();
			remove.mockRestore();
		}
	});

	it('makes a box a Tab stop and a named region only while it overflows, sideways or down, and no more when it fits', async () => {
		withCanvas();
		const observers = fakeResizeObserver();
		try {
			render(PumpChart, {
				result: pumpResult(),
				name: 'P',
				prefs: SI_UNITS,
				system: READY,
				caseName: 'Base case',
				tags: TAGS,
				others: [winter()],
				onoverlay: vi.fn()
			});
			await vi.waitFor(() => expect(charts).toHaveLength(1));
			await showTable();
			const region = screen.getByRole('figure').querySelector<HTMLElement>('[data-pump-data]')!;
			const boxes = within(region)
				.getAllByRole('table')
				.map((t) => t.parentElement!);
			expect(boxes).toHaveLength(4);
			// Laid out with room for every table: none is a Tab stop or a region.
			for (const box of boxes) {
				sizeBox(box, { clientWidth: 452, scrollWidth: 452, clientHeight: 300, scrollHeight: 300 });
				observers.resize(box);
				expect(box).not.toHaveAttribute('tabindex');
				expect(box).not.toHaveAttribute('role');
			}
			expect(within(region).queryAllByRole('region')).toEqual([]);
			// "Operating points by case" wider than its box (a long case name, a phone's pane).
			sizeBox(boxes[0]!, { scrollWidth: 600 });
			observers.resize(boxes[0]!);
			expect(within(region).getByRole('region', { name: 'Operating points by case' })).toBe(
				boxes[0]
			);
			expect(boxes[0]).toHaveAttribute('tabindex', '0');
			// The system curve's table taller than its box: down counts too, once its disclosure is
			// open; folded away, whatever it measures, it is neither (a browser lays it out still).
			const system = screen.getByRole('table', { name: 'System curve' }).parentElement!;
			sizeBox(system, { scrollHeight: 900 });
			observers.resize(system);
			expect(system).not.toHaveAttribute('tabindex');
			await openTable('System curve');
			await new Promise((resolve) => setTimeout(resolve, 0)); // the toggle event's task
			expect(within(region).getByRole('region', { name: 'System curve' })).toBe(system);
			expect(system).toHaveAttribute('tabindex', '0');
			// The pane widened: it fits again, and is neither.
			sizeBox(boxes[0]!, { clientWidth: 600 });
			observers.resize(boxes[0]!);
			expect(boxes[0]).not.toHaveAttribute('tabindex');
			expect(within(region).queryByRole('region', { name: 'Operating points by case' })).toBeNull();
			sizeBox(system, { scrollHeight: 300 });
			observers.resize(system);
			expect(within(region).queryAllByRole('region')).toEqual([]);
		} finally {
			observers.restore();
		}
	});
});
