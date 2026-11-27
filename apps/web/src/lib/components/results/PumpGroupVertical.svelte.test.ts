/**
 * The group system curve's vertical part on the Pumps together card (docs/proposals/
 * open-defects-2.md §2 C1), drawn through the card as PumpGroupChart.svelte.test.ts draws it
 * (Chart.js replaced by a recorder), on the condenser example's recorded answers
 * (__fixtures__/condenser-charts.json, apps/api/tests/fixtures/condenser_charts.py): the chart's
 * accessible name, the strip's line, the duty words with the API's verdict (since C2 its system
 * duty check agrees on the vertical part, §3; an API deployed before C2 does not, and its verdict
 * is relayed as given), the data table's cell and the canvas's `data-system-rays`; and what lies
 * below zero flow named in the notes (X).
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GroupCurveState } from '$lib/state/project.svelte';
import { fakeResizeObserver } from '$lib/testing/resize';
import {
	baseBeforeC2,
	condenserCase,
	condenserCaseProject,
	condenserMembers,
	type CondenserCase
} from '$lib/utils/condenser-charts.testing';
import PumpGroupChart from './PumpGroupChart.svelte';

const charts = vi.hoisted(() => [] as { config: unknown; destroyed: boolean; draws: number }[]);

vi.mock('./chart-setup', async () => ({
	pumpGroupConfig: (await import('$lib/utils/pump-chart-config')).pumpGroupConfig,
	Chart: class {
		static defaults = { plugins: { legend: { labels: { generateLabels: () => [] } } } };
		record: { config: unknown; destroyed: boolean; draws: number };
		constructor(_context: unknown, config: unknown) {
			this.record = { config, destroyed: false, draws: 0 };
			charts.push(this.record);
		}
		draw() {
			this.record.draws++;
		}
		destroy() {
			this.record.destroyed = true;
		}
	},
	downloadChartImage: async () => undefined,
	IMAGE_REASONS_IN: 'made-up place says'
}));

const getContext = HTMLCanvasElement.prototype.getContext;
let observers: ReturnType<typeof fakeResizeObserver>;
beforeEach(() => {
	charts.length = 0;
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	observers = fakeResizeObserver();
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	observers.restore();
	localStorage.clear();
});

const drawn = () => vi.waitFor(() => expect(charts).toHaveLength(1), { timeout: 10_000 });

/** The card for a recorded condenser case, both curves answered. */
function props(name: CondenserCase, system = condenserCase(name).systemCurve!) {
	const c = condenserCase(name);
	const project = condenserCaseProject(name);
	return {
		pumps: condenserMembers(name).map(({ id, name, result, ratedRange, curveId, flags }) => ({
			id,
			name,
			result,
			ratedRange,
			curveId,
			flags
		})),
		slots: c.memberIds,
		prefs: project.settings.units,
		project,
		open: true,
		curve: { status: 'ready', response: c.groupCurve! } as GroupCurveState,
		system: { status: 'ready', response: system } as GroupCurveState
	};
}

describe('the group system curve’s vertical part on the card (open-defects-2.md C1)', () => {
	it('names the vertical part, says what it is, marks both checks ✓, calls the Group point the crossing, and lists its range (C2, as recorded)', async () => {
		const system = condenserCase('base').systemCurve!;
		expect(system.systemDutyCheck).toMatchObject({ agrees: true, head: null });
		render(PumpGroupChart, props('base'));
		await drawn();
		const figure = screen.getByRole('figure');
		expect(within(figure).getByRole('img')).toHaveAccessibleName(
			/on the group curve and the group system curve, where they cross; group curve shown; group system curve shown, vertical at 5678 L\/s from 24\.63 m up\.$/
		);
		expect(
			within(figure).getByText(
				"25 of 42 group-system-curve points have no rise: at 5678 L/s it is undetermined, any rise at or above 24.63 m holding, drawn as the curve's vertical part from there to the top of the plot; at the 24 flows sampled beyond 5678 L/s no steady state carries the flow. The data table says why for each."
			)
		).toBeInTheDocument();
		const notes = figure.querySelector('[data-group-notes]')!;
		// The API's verdict in one paragraph (pumps-results-layout.md §5.7 row 7), with its ✓.
		const verdict = [...notes.querySelectorAll('p')].filter((p) =>
			/At the duty's flow the group system curve is vertical/.test(p.textContent!)
		);
		expect(verdict).toHaveLength(1);
		expect(verdict[0]!.textContent).toContain(
			"At the duty's flow the group system curve is vertical, any rise at or above 24.63 m holding, and the solve's rise, 31.48 m, is one of them (within 0.5 % or 0.01 m): it passes through the Group point, where it crosses the group curve."
		);
		expect(notes.textContent).not.toMatch(/is not known/);
		expect(notes.querySelectorAll('[data-group-check]')).toHaveLength(2);
		const labels = (charts[0]!.config as { data: { datasets: { caseLabel?: string }[] } }).data
			.datasets;
		expect(labels.some((d) => d.caseLabel === 'Group (crossing)')).toBe(true);
		// The canvas keeps where the rays went, as each drawing tells it.
		const config = charts[0]!.config as {
			plugins: { id: string; afterDatasetsDraw?: () => void }[];
		};
		config.plugins.find((p) => p.id === 'systemRays')!.afterDatasetsDraw!();
		expect(figure.querySelector('canvas')!.dataset.systemRays).toBe('[]');
		// The legend: one entry for the curve, its vertical part part of it.
		const legend = within(figure).getByRole('list', { name: 'Legend' });
		expect(
			within(legend)
				.getAllByRole('listitem')
				.filter((li) => /Group system curve/.test(li.textContent!))
		).toHaveLength(1);
		await fireEvent.click(
			within(figure).getByRole('button', { name: 'Show data table of the group chart' })
		);
		const table = within(figure).getByRole('table', {
			name: "Group system curve (rise the rest of the network needs at each station's flow)"
		});
		const row = within(table)
			.getAllByRole('row')
			.find((r) => within(r).queryAllByRole('cell')[0]?.textContent?.trim() === '5678')!;
		expect(within(row).getAllByRole('cell')[1]!.textContent!.trim()).toBe('≥ 24.63');
	});

	it('keeps the verdict of an API before C2 (agrees false): its facts beside it in one paragraph, no ✓, no crossing', async () => {
		render(PumpGroupChart, props('base', baseBeforeC2()));
		await drawn();
		const figure = screen.getByRole('figure');
		expect(within(figure).getByRole('img')).toHaveAccessibleName(
			/; group system curve shown, vertical at 5678 L\/s from 24\.63 m up\.$/
		);
		const notes = figure.querySelector('[data-group-notes]')!;
		// The verdict and the vertical's facts in one paragraph (pumps-results-layout.md §5.7 row 7).
		const verdict = [...notes.querySelectorAll('p')].filter((p) =>
			/The group system curve has no rise at the duty's flow/.test(p.textContent!)
		);
		expect(verdict).toHaveLength(1);
		expect(verdict[0]!.textContent).toMatch(
			/^The group system curve has no rise at the duty's flow, so whether it passes through the Group point is not known: .+\. The curve is drawn vertical at that flow, from 24\.63 m up, the rises that hold there; the duty's rise is 31\.48 m\./
		);
		expect(
			[...notes.querySelectorAll('p')].filter((p) =>
				/The curve is drawn vertical at that flow/.test(p.textContent!)
			)
		).toEqual(verdict);
		// No ✓ on the system duty check: that API's does not agree.
		expect(notes.querySelectorAll('[data-group-check]')).toHaveLength(1);
		const labels = (charts[0]!.config as { data: { datasets: { caseLabel?: string }[] } }).data
			.datasets;
		expect(labels.some((d) => d.caseLabel === 'Group (crossing)')).toBe(false);
		expect(labels.some((d) => d.caseLabel === 'Group')).toBe(true);
	});
});
