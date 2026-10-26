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

const charts = vi.hoisted(() => [] as { config: unknown; destroyed: boolean }[]);
/** The chart image's requests (the image code itself is tested in chart-image.test.ts). */
const images = vi.hoisted(() => ({ requests: [] as unknown[] }));

vi.mock('./chart-setup', async () => ({
	// The chart's own configuration: only Chart.js and the image are replaced.
	pumpChartConfig: (await import('$lib/utils/pump-chart-config')).pumpChartConfig,
	Chart: class {
		static defaults = { plugins: { legend: { labels: { generateLabels: () => [] } } } };
		record: { config: unknown; destroyed: boolean };
		constructor(_context: unknown, config: unknown) {
			this.record = { config, destroyed: false };
			charts.push(this.record);
		}
		destroy() {
			this.record.destroyed = true;
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
			'Operating point'
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
		const toggle = screen.getByRole('button', { name: 'Show data table' });
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
		expect(screen.getByRole('figure')).toHaveAttribute('aria-busy', 'true');
		await vi.waitFor(() => expect(charts).toHaveLength(1));
		const labels = (i: number) => (charts[i]!.config as Recorded).data.datasets.map((d) => d.label);
		expect(labels(0)).not.toContain('System curve');
		expect(screen.getByRole('img').getAttribute('aria-label')).not.toMatch(/system curve/);

		await view.rerender({ result: pumpResult(), name: 'P', prefs: SI_UNITS, system: READY });
		await vi.waitFor(() => expect(charts).toHaveLength(2));
		expect(labels(1)).toContain('System curve');
		expect(screen.queryByText(/Computing the system curve/)).toBeNull();
		expect(screen.getByRole('figure')).toHaveAttribute('aria-busy', 'false');
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
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		expect(screen.getByRole('table', { name: 'Pump curve at 100 % speed' })).toBeInTheDocument();
		expect(screen.queryByRole('table', { name: 'System curve' })).toBeNull();
	});

	it('offers Cancel while the system curve is computed; cancelled, it offers to compute it', async () => {
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
		expect(screen.getByRole('figure')).toHaveAttribute('aria-busy', 'false');
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
		const table = screen.getByRole('button', { name: 'Show data table' });
		table.focus();
		await view.rerender({ ...props, system: { status: 'loading' } });
		await tick();
		expect(document.activeElement).toBe(table);
	});

	it('leaves the focus alone when Cancel did not have it, and offers no Cancel without a way to', async () => {
		const props = { result: pumpResult(), name: 'P', prefs: SI_UNITS, oncancel: vi.fn() };
		const view = render(PumpChart, { ...props, system: { status: 'loading' } });
		const table = screen.getByRole('button', { name: 'Show data table' });
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
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
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
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
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
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
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
				screen.getByRole('button', { name: 'Show data table' }).parentElement
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
				document.querySelector('figure p.text-slate-600:not([id])')?.firstChild?.textContent?.trim()
			);
			expect(request.notes.method).toMatch(/speed-controlled ones regulating to their setpoints/);
			expect(request.others.map((o) => o.label)).toEqual(['Winter']);
			expect(button()).toHaveAccessibleName(
				'Download image of the pump and system curves: Transfer pump, Base case'
			);
		});
	});
});
