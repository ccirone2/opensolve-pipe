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
import type { PumpChecksInput } from '$lib/utils/pump-chart';
import { pumpResult, systemCurvePoint, systemCurveResponse } from '$lib/testing/results';
import { pumpTransferExample } from '$lib/utils/examples';
import { IMPERIAL_UNITS, SI_UNITS } from '$lib/utils/units';
import type { ChartImageRequest, ChartImageSource } from '$lib/utils/export/chart-image';
import { DISCLAIMER } from '$lib/components/links';
import PumpChart from './PumpChart.svelte';

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
});

function withCanvas() {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
}

const READY: SystemCurveState = { status: 'ready', curve: systemCurveResponse() };

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
		expect(toggle).toHaveTextContent('Hide data table');
		const curve = screen.getByRole('table', { name: 'Pump curve at 100 % speed' });
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
		const system = screen.getByRole('table', { name: 'System curve' });
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
		expect(screen.getByText('Computing the system curve for this solve…')).toBeInTheDocument();
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
		expect(screen.getByText('Computing the system curve for this solve…')).toBeInTheDocument();
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
		const cell = within(table).getAllByRole('row')[3]!.querySelectorAll('td')[2]!;
		const details = cell.querySelector('details')!;
		expect(details.open).toBe(false);
		expect(within(details).getByText('Details')).toBeInTheDocument();
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
			expect(button().parentElement).toBe(
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

	it('draws the chips as toggles: filled with a check when on, outlined when off, the same words', async () => {
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
		const look = () =>
			chips.map((chip) => ({
				text: chip.textContent,
				pressed: chip.getAttribute('aria-pressed'),
				btn: chip.classList.contains('btn'),
				filled: chip.classList.contains('bg-blue-50'),
				check: chip.querySelectorAll('svg[aria-hidden="true"]').length
			}));
		expect(look()).toEqual([
			{ text: 'Efficiency', pressed: 'true', btn: true, filled: true, check: 1 },
			{ text: 'Shaft power', pressed: 'true', btn: true, filled: true, check: 1 }
		]);
		await fireEvent.click(chips[1]!);
		expect(look()[1]).toEqual({
			text: 'Shaft power',
			pressed: 'false',
			btn: true,
			filled: false,
			check: 0
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

		// Loading: the same element speaks; the canvas is busy, the line is not under it.
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

		// Failed: the same line, its button after it, outside it.
		await view.rerender({ ...props, system: { status: 'error', message: 'Made-up message.' } });
		expect(strip.querySelector('[aria-live]')).toBe(line);
		expect(line).toHaveTextContent('The system curve could not be computed: Made-up message.');
		expect(line.querySelector('button')).toBeNull();
		expect(line.nextElementSibling).toBe(screen.getByRole('button', { name: 'Try again' }));

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
		expect(reason()).toHaveClass('text-xs');
		expect(reason().parentElement).toBe(button().parentElement);
		expect(button()).toHaveAccessibleDescription('Made-up lasting reason.');
		expect(button()).toHaveAttribute('aria-disabled', 'true');
		expect(button()).not.toHaveAttribute('title');
	});

	it('names its data table button for the pump chart, its visible words unchanged', async () => {
		withCanvas();
		render(PumpChart, { result: pumpResult(), name: 'P', prefs: SI_UNITS, system: READY });
		const toggle = screen.getByRole('button', { name: 'Show data table of the pump chart' });
		expect(toggle.querySelector('.sr-only')).toHaveTextContent('of the pump chart');
		await fireEvent.click(toggle);
		expect(toggle).toHaveAccessibleName('Hide data table of the pump chart');
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
			/^Best efficiency point \(\+\): 70 % at 12 L\/s/,
			/^Shutoff head \(–\): 30 m\.$/,
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
