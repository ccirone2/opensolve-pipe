/**
 * Pump chart: what is drawn (Chart.js is replaced by a recorder; jsdom has no canvas) and the
 * data table under it. The pump results are made-up test inputs.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pumpResult } from '$lib/testing/results';
import { SI_UNITS } from '$lib/utils/units';
import PumpChart from './PumpChart.svelte';

interface Recorded {
	data: {
		datasets: { label: string; data: unknown[]; borderDash?: number[]; showLine?: boolean }[];
	};
	options: { scales: { x: { title: { text: string } }; y: { title: { text: string } } } };
}

const charts = vi.hoisted(() => [] as { config: unknown; destroyed: boolean }[]);

vi.mock('./chart-setup', () => ({
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
	}
}));

const getContext = HTMLCanvasElement.prototype.getContext;

beforeEach(() => {
	charts.length = 0;
});

afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
});

function withCanvas() {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
}

describe('pump chart', () => {
	it('draws the curve, the dashed extrapolation, the system curve and the operating point', async () => {
		withCanvas();
		render(PumpChart, {
			result: pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false }),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			ratedRange: [0, 0.03]
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
		render(PumpChart, { result: pumpResult(), name: 'Transfer pump', prefs: SI_UNITS });
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
		expect(screen.getByRole('table', { name: 'System curve' })).toBeInTheDocument();
		expect(screen.getByText(/Operating point:/)).toHaveTextContent(
			'Operating point: 20 L/s at 22 m'
		);
	});

	it('shows the table instead when the chart cannot be drawn, and says when there is no system curve', async () => {
		render(PumpChart, {
			result: pumpResult({ systemCurve: null }),
			name: 'Transfer pump',
			prefs: SI_UNITS
		});
		expect(
			await screen.findByText(/The chart cannot be drawn in this browser/)
		).toBeInTheDocument();
		expect(screen.getByRole('table', { name: 'Pump curve at 100 % speed' })).toBeInTheDocument();
		expect(screen.queryByRole('table', { name: 'System curve' })).toBeNull();
		expect(
			screen.getByText('This solve did not return a system curve for this pump.')
		).toBeInTheDocument();
		expect(charts).toHaveLength(0);
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
});
