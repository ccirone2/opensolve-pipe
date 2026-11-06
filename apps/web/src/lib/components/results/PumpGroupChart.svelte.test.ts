/**
 * The Pumps together card (CLAUDE.md D21, proposal pump-groups.md §6): the disclosure, the
 * members (the cap and its hint, slots kept, the other groups found), the group curve's states
 * (progress with Cancel and the focus moves, a refusal in words), the accessible name, the data
 * table, the group table and the image. Chart.js is replaced by a recorder (jsdom has no canvas);
 * the results and responses are the shared fixture's real API answers. Slice 4b: the group
 * system curve's states, its rows in the data table and its line in the image, and "Read along
 * the curves". Slice 4d with D24's Add cases block (PumpLineupsBlock, drawn in 4d's place): 4d's
 * tests of its block, under Each pump off. D24 slice L3 (pump-lineups.md §10.3 Component): the
 * family's legend entry, the column "Its group curve", the table "Other cases' group curves" (its
 * row groups and its list below 640 px), and the notes' and the image's counts of labels left out,
 * on the `lineups` station's real answers (testing/curve-family.ts).
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolvedState,
	SolveResponse,
	TopologyIssue
} from '$lib/api/types';
import type { GroupCurveState } from '$lib/state/project.svelte';
import type { ChartImageSource, FigureImageRequest } from '$lib/utils/export/chart-image';
import {
	answer,
	drawnChart,
	lineupAnswers,
	lineupCaseName,
	lineupOn,
	lineupPrefs,
	lineups,
	lineupView,
	readyState,
	type LineupViewOptions
} from '$lib/testing/curve-family';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import type { CurveLabelsDrawn, PumpChartConfig } from '$lib/utils/pump-chart-config';
import { ratedCurveRange } from '$lib/utils/pump-chart';
import {
	GROUP_OTHER,
	groupMethodsHeading,
	OTHER_CURVES_CAPTION,
	OTHER_CURVES_LABEL,
	type GroupMemberInput
} from '$lib/utils/pump-group-chart';
import {
	combinationExtremes,
	otherGroupCases,
	runningCombinations,
	type CombinationsInput,
	type OtherGroupCase
} from '$lib/utils/pump-group-one-off';
import { lineupPlan, type LineupPlanInput } from '$lib/utils/pump-lineups';
import { withScenarios } from '$lib/utils/scenarios';
import { formatNumber } from '$lib/utils/units';
import PumpGroupChart from './PumpGroupChart.svelte';

const charts = vi.hoisted(() => [] as { config: unknown; destroyed: boolean; draws: number }[]);
const images = vi.hoisted(() => ({ requests: [] as unknown[] }));

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
	downloadChartImage: async (_chart: unknown, request: unknown) =>
		void images.requests.push(request),
	IMAGE_REASONS_IN: 'made-up place says'
}));

const getContext = HTMLCanvasElement.prototype.getContext;
beforeEach(() => {
	charts.length = 0;
	images.requests.length = 0;
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
});

interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: { solvedState: SolvedState };
	groupCurve: { status: number; body: unknown };
	systemCurve: { status: number; body: unknown } | null;
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;

function pumpsOf(c: FixtureCase): Omit<GroupMemberInput, 'slot'>[] {
	const s = c.solve.solvedState;
	return Object.keys(s.pumpResults).map((id) => {
		const pump = c.project.components.find((x) => x.id === id)!;
		return {
			id,
			name: pump.name,
			result: s.pumpResults[id] as PumpResult,
			ratedRange: ratedCurveRange(c.project, id),
			curveId: pump.type === 'pump' ? pump.curveId : null,
			flags: (s.flags as Flag[]).filter((f) => f.componentId === id)
		};
	});
}
const ready = (c: FixtureCase): GroupCurveState => ({
	status: 'ready',
	response: c.groupCurve.body as PumpGroupCurveResponse
});
const systemReady = (c: FixtureCase): GroupCurveState => ({
	status: 'ready',
	response: c.systemCurve!.body as PumpGroupCurveResponse
});

function props(c: FixtureCase, values: Record<string, unknown> = {}) {
	return {
		pumps: pumpsOf(c),
		slots: c.memberIds,
		prefs: c.project.settings.units,
		project: c.project,
		nodes: c.solve.solvedState.nodeResults,
		open: true,
		curve: ready(c),
		...values
	};
}

const image = (values: Partial<ChartImageSource> = {}): ChartImageSource => ({
	projectName: 'Booster station',
	timestamp: '2026-10-28T09:30:00Z',
	methodVersion: '1.3.0',
	stale: false,
	unavailable: '',
	origin: 'https://opensolve-pipe.app',
	notify: () => {},
	...values
});

type Recorded = { data: { datasets: { label: string }[] } };

/** The chart was drawn (its chunk is imported first: slow on a loaded machine). */
const drawn = () => vi.waitFor(() => expect(charts).toHaveLength(1), { timeout: 10_000 });

describe('the card', () => {
	it('is a disclosure, closed by default, naming the pumps; opened, it shows the members', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { open: false }));
		const toggle = screen.getByRole('button', { name: /Pumps together/ });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(toggle).toHaveTextContent('(Pump PA, Pump PB)');
		expect(screen.queryByRole('group', { name: 'Pumps in the group' })).toBeNull();
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		const members = screen.getByRole('group', { name: 'Pumps in the group' });
		expect(
			within(members)
				.getAllByRole('checkbox')
				.map((box) => [
					box.closest('label')!.textContent!.trim(),
					(box as HTMLInputElement).checked
				])
		).toEqual([
			['▲ Pump PA', true],
			['■ Pump PB', true]
		]);
		await drawn();
	});

	it('draws the members, the group curve and the Group point, with the figure named', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c));
		await drawn();
		const labels = (charts[0]!.config as Recorded).data.datasets.map((d) => d.label);
		expect(labels).toContain("Group curve (station's flow)");
		expect(labels.at(-1)).toBe('Group duty, on the curve');
		const figure = screen.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' });
		const duty = (c.groupCurve.body as PumpGroupCurveResponse).duty!;
		expect(within(figure).getByRole('img')).toHaveAccessibleName(
			new RegExp(
				`^Pump curves and points of Pump PA at .* share ${formatNumber(duty.members[0]!.share! * 100, 4)} %; .*station duty ${formatNumber(duty.flow * 1000, 4)} L/s at a rise of ${formatNumber(duty.head, 4)} m from Tee T1 \\(run inlet\\) to Tee T2 \\(run outlet\\), on the group curve; group curve shown\\.$`
			)
		);
		expect(within(figure).getByRole('img').querySelector('canvas')).toHaveAttribute(
			'aria-hidden',
			'true'
		);
		expect(
			within(figure).getByText(/^Pump curves and points are at each pump's flanges\./)
		).toBeVisible();
		// The legend under the chart, each line and marker named.
		expect(
			within(within(figure).getByRole('list', { name: 'Legend' }))
				.getAllByRole('listitem')
				.map((li) => li.textContent!.trim())
		).toEqual([
			'Pump PA, 100 % speed (own flow)',
			'Pump PB, 85 % speed (own flow)',
			"Group curve (station's flow)",
			'Group curve, a pump beyond its data (dashed)',
			'▲ Pump PA',
			'■ Pump PB',
			'● Group duty, on the curve'
		]);
		// How the curve is computed: the response's methods section, under Details, headed by the
		// words the export's Methods sheet gives it (groupMethodsHeading, slice 4c).
		const summary = screen.getByText('How this curve is computed');
		expect(summary).toBeInTheDocument();
		const details = summary.closest('details')!;
		await fireEvent.click(summary);
		expect(details.open).toBe(true);
		const response = c.groupCurve.body as PumpGroupCurveResponse;
		const heading = within(details).getByText(groupMethodsHeading(response));
		expect(heading).toBeVisible();
		expect(heading.textContent!.trim()).toBe('Pump group (calculation methods 1.6.0)');
	});

	it('shows progress while the curve is computed, with Cancel; the focus follows the controls', async () => {
		const c = named('parallel-ideal');
		const oncancel = vi.fn();
		const onretry = vi.fn();
		const view = render(
			PumpGroupChart,
			props(c, { curve: { status: 'loading' }, oncancel, onretry })
		);
		const figure = screen.getByRole('figure');
		expect(figure).toHaveAttribute('aria-busy', 'true');
		expect(screen.getByRole('status')).toHaveTextContent(
			'Computing the group curve for this solve…'
		);
		const cancel = screen.getByRole('button', { name: 'Cancel the group curve' });
		cancel.focus();
		await fireEvent.click(cancel);
		expect(oncancel).toHaveBeenCalledTimes(1);
		await view.rerender(
			props(c, { curve: { status: 'cancelled', by: 'user' }, oncancel, onretry })
		);
		await tick();
		await tick();
		const retry = screen.getByRole('button', { name: 'Compute the group curve' });
		expect(retry).toHaveFocus();
		expect(retry).toHaveAccessibleDescription(
			'The group curve was not computed: you cancelled it.'
		);
		expect(figure).toHaveAttribute('aria-busy', 'false');
		await fireEvent.click(retry);
		expect(onretry).toHaveBeenCalledTimes(1);
		await view.rerender(props(c, { curve: { status: 'loading' }, oncancel, onretry }));
		await tick();
		await tick();
		expect(screen.getByRole('button', { name: 'Cancel the group curve' })).toHaveFocus();
		await view.rerender(
			props(c, { curve: { status: 'error', message: 'The server is busy.' }, oncancel, onretry })
		);
		expect(screen.getByRole('button', { name: 'Try again' })).toHaveAccessibleDescription(
			'The group curve could not be computed: The server is busy.'
		);
	});

	it('caps the members at six: a capped box is aria-disabled, with a hint', async () => {
		const c = named('parallel-ideal');
		const [pa] = pumpsOf(c);
		const pumps = Array.from({ length: 7 }, (_, i) => ({
			...pa!,
			id: `P${i + 1}`,
			name: `Pump P${i + 1}`
		}));
		const onslots = vi.fn();
		render(
			PumpGroupChart,
			props(c, { pumps, slots: ['P1', 'P2', 'P3', 'P4', 'P5', 'P6'], curve: undefined, onslots })
		);
		const seventh = screen.getByRole('checkbox', { name: /Pump P7/ });
		expect(seventh).toHaveAttribute('aria-disabled', 'true');
		expect(seventh).toHaveAccessibleDescription('At most 6 pumps in a group.');
		await fireEvent.click(seventh);
		expect(onslots).not.toHaveBeenCalled();
		expect(seventh).not.toBeChecked();
		// Unticking frees its slot only: the others keep theirs (their colours).
		await fireEvent.click(screen.getByRole('checkbox', { name: /Pump P2/ }));
		expect(onslots).toHaveBeenLastCalledWith(['P1', null, 'P3', 'P4', 'P5', 'P6']);
	});

	it('ticks into the first free slot, and offers the other groups found', async () => {
		const c = named('ladder');
		const onslots = vi.fn();
		render(
			PumpGroupChart,
			props(c, {
				slots: [null, 'P2', 'P3'],
				curve: undefined,
				onslots,
				suggestions: [
					{ pumpIds: ['P1', 'P2', 'P3'], kind: 'parallel' },
					{ pumpIds: ['P2', 'P3'], kind: 'parallel' }
				]
			})
		);
		// The group shown is not offered again.
		expect(screen.queryByRole('button', { name: 'Also found: Pump P2 and Pump P3' })).toBeNull();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Also found: Pump P1, Pump P2 and Pump P3' })
		);
		expect(onslots).toHaveBeenLastCalledWith(['P1', 'P2', 'P3']);
		await fireEvent.click(screen.getByRole('checkbox', { name: /Pump P1/ }));
		expect(onslots).toHaveBeenLastCalledWith(['P1', 'P2', 'P3']);
	});

	it('says once that showing a group found replaces the pumps ticked, each button described by it and wrapping', () => {
		// pumps-results-layout.md §9 S0 (F10): `.btn` (its min-h-ctl kept) does not wrap; these do, so
		// the Results pane never scrolls sideways (tests/pumps-layout.e2e.ts measures it).
		const c = named('ladder');
		const sentence = 'Showing a group found replaces the pumps ticked.';
		const view = render(
			PumpGroupChart,
			props(c, {
				slots: ['P2'],
				curve: undefined,
				suggestions: [
					{ pumpIds: ['P1', 'P2', 'P3'], kind: 'parallel' },
					{ pumpIds: ['P2', 'P3'], kind: 'parallel' }
				]
			})
		);
		expect(screen.getAllByText(sentence)).toHaveLength(1);
		const buttons = screen.getAllByRole('button', { name: /^Also found: / });
		expect(buttons.map((b) => b.textContent)).toEqual([
			'Also found: Pump P1, Pump P2 and Pump P3',
			'Also found: Pump P2 and Pump P3'
		]);
		for (const button of buttons) {
			expect(button).toHaveAccessibleDescription(sentence);
			expect(button).toHaveClass('btn', 'whitespace-normal', 'text-left');
		}
		// No other group offered: no sentence.
		view.unmount();
		render(PumpGroupChart, props(c, { slots: ['P2', 'P3'], curve: undefined, suggestions: [] }));
		expect(screen.queryByText(sentence)).toBeNull();
	});

	it('keeps the focus in the card when a group found is shown and its button goes', async () => {
		const c = named('ladder');
		const suggestions = [
			{ pumpIds: ['P1', 'P2', 'P3'], kind: 'parallel' },
			{ pumpIds: ['P2', 'P3'], kind: 'parallel' }
		];
		const values = (slots: (string | null)[]) => ({
			slots,
			curve: undefined,
			suggestions,
			onslots: (next: string[]) => void view.rerender(props(c, values(next)))
		});
		const view = render(PumpGroupChart, props(c, values(['P2', 'P3'])));
		const whole = screen.getByRole('button', { name: 'Also found: Pump P1, Pump P2 and Pump P3' });
		whole.focus();
		await fireEvent.click(whole);
		await tick();
		await tick();
		// The button pressed is gone (its group is shown); the focus moves to the next one offered,
		// the group shown before, never to the page's body.
		expect(whole.isConnected).toBe(false);
		const back = screen.getByRole('button', { name: 'Also found: Pump P2 and Pump P3' });
		expect(back).toHaveFocus();
		await fireEvent.click(back);
		await tick();
		await tick();
		expect(
			screen.getByRole('button', { name: 'Also found: Pump P1, Pump P2 and Pump P3' })
		).toHaveFocus();
		// No other group offered: the chart's figure takes the focus.
		view.unmount();
		const alone = render(
			PumpGroupChart,
			props(c, {
				slots: ['P1'],
				curve: undefined,
				suggestions: [suggestions[0]],
				onslots: (next: string[]) =>
					void alone.rerender(
						props(c, { slots: next, curve: undefined, suggestions: [suggestions[0]] })
					)
			})
		);
		const only = screen.getByRole('button', { name: 'Also found: Pump P1, Pump P2 and Pump P3' });
		only.focus();
		await fireEvent.click(only);
		await tick();
		await tick();
		expect(document.activeElement).not.toBe(document.body);
		expect(screen.getByRole('figure')).toHaveFocus();
	});

	it('says in words why the pumps are not a station, names linked, and still draws them', async () => {
		const c = named('refused');
		const body = c.groupCurve.body as { message: string; issues: TopologyIssue[] };
		const oninspect = vi.fn();
		render(
			PumpGroupChart,
			props(c, {
				curve: { status: 'refused', message: body.message, issues: body.issues },
				oninspect
			})
		);
		const refusal = screen
			.getByText(/These pumps do not form a station/)
			.closest('[data-group-refusal]') as HTMLElement;
		const item = within(
			within(refusal).getByRole('list', { name: 'Why they do not form a station' })
		).getByRole('listitem');
		expect(item.firstChild?.textContent).toBeDefined();
		expect(item).toHaveTextContent(
			'The pumps meet the fixed heads of Reservoir R2 and Tank R4, one place more than a station has'
		);
		await fireEvent.click(within(item).getByRole('button', { name: 'Tank R4' }));
		expect(oninspect).toHaveBeenCalledWith('R4');
		// The server's sentence under Details.
		expect(within(item).getByText(/^Calculation server's message:/)).toHaveTextContent(
			body.issues[0]!.message
		);
		await drawn();
		const labels = (charts[0]!.config as Recorded).data.datasets.map((d) => d.label);
		expect(labels).toEqual([
			'Pump PA, 100 % speed (own flow)',
			'Pump PB, 85 % speed (own flow)',
			'Pump PA',
			'Pump PB'
		]);
		expect(screen.getByRole('figure', { name: 'Pump PA and Pump PB' })).toBeVisible();
	});

	it('lists the pumps in the group table, from the solve and the duty, with a footer', () => {
		const c = named('series');
		render(PumpGroupChart, props(c, { oninspect: () => {} }));
		const region = screen.getByRole('region', { name: 'The pumps in the group' });
		expect(region).toHaveAttribute('tabindex', '0');
		const table = within(region).getByRole('table');
		const headers = within(table)
			.getAllByRole('columnheader')
			.map((h) => h.textContent!.replace(/\s+/g, ' ').trim());
		expect(headers).toEqual([
			'Pump',
			'State',
			'Speed %',
			'Flow gpm',
			'Share %',
			'Head ft',
			'Inlet pressure psig',
			'Discharge pressure psig',
			'η %',
			'Shaft power hp',
			'NPSH margin ft',
			'Shutoff head ft',
			'Inside curve data',
			'Flags'
		]);
		expect(within(table).getByRole('rowheader', { name: 'Pump PA' })).toBeVisible();
		// The footer: the station as a whole, both ports named.
		expect(screen.getByText('Lost in the piping between the pumps:')).toBeVisible();
		expect(screen.getByText('Rise from Pump PA (suction) to Pump PB (discharge):')).toBeVisible();
	});

	it('shows the data table on request: the points, the duty and every sample', async () => {
		const c = named('dead-headed');
		render(PumpGroupChart, props(c));
		const toggle = screen.getByRole('button', { name: 'Show data table' });
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		const points = screen.getByRole('table', { name: "Each pump's point (flow through it)" });
		expect(within(points).getAllByRole('row')).toHaveLength(3);
		expect(within(points).getByRole('rowheader', { name: /Pump PB/ })).toHaveTextContent('◇');
		const samples = screen.getByRole('table', {
			name: "Group curve (station's flow at each rise)"
		});
		const response = c.groupCurve.body as PumpGroupCurveResponse;
		expect(within(samples).getAllByRole('row')).toHaveLength(response.points.length + 1);
		expect(within(samples).getByText("The duty's rise (the duty check).")).toBeVisible();
		expect(
			screen.getByText(/Duty check: the group curve passes through it; at the duty's rise it gives/)
		).toBeVisible();
	});

	it('says the duty check is not known when the duty’s point was not solved, and why', async () => {
		const c = named('parallel-ideal');
		// Made-up: the duty's point without a flow, as the API reports it (not computed, or its
		// solve did not converge).
		const unsolved = (reason: 'not_computed' | 'not_converged', message: string) => {
			const response = structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
			response.dutyCheck = {
				agrees: false,
				flow: null,
				members: response.duty!.members.map((x) => ({ pumpId: x.pumpId, flow: null })),
				message: 'made-up server words'
			};
			Object.assign(
				response.points.find((p) => p.isDuty)!,
				{
					flow: null,
					converged: false,
					reason,
					message,
					members: []
				}
			);
			return response;
		};
		const view = render(
			PumpGroupChart,
			props(c, {
				curve: {
					status: 'ready',
					response: unsolved('not_computed', "not computed: the request's 45 s budget ran out")
				}
			})
		);
		expect(
			screen.getByText(
				"The group curve's point at the duty's rise was not computed (the time budget ran out), so whether the curve passes through the Group point is not known."
			)
		).toBeVisible();
		expect(screen.queryByText(/Several steady states can exist/)).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		const line = () => screen.getByText(/Group duty \(station's flow\):/);
		expect(line()).toHaveTextContent(
			/Duty check: not known, its point at the duty’s rise was not computed \(the time budget ran out\)\.\s*Details/
		);
		expect(screen.queryByText(/the group curve does not pass through it/)).toBeNull();
		// The duty's row: its mark and the point's reason, two sentences.
		const samples = screen.getByRole('table', {
			name: "Group curve (station's flow at each rise)"
		});
		expect(
			within(samples).getByText(
				"The duty's rise (the duty check). Not computed: the time budget ran out before this point."
			)
		).toBeVisible();

		await view.rerender(
			props(c, {
				curve: {
					status: 'ready',
					response: unsolved(
						'not_converged',
						'not converged: statuses oscillate between states already solved (components: PB)'
					)
				}
			})
		);
		expect(
			screen.getByText(
				"The group curve's point at the duty's rise did not converge, so whether the curve passes through the Group point is not known."
			)
		).toBeVisible();
		expect(line()).toHaveTextContent(
			/Duty check: not known, its point at the duty’s rise did not converge\.\s*Details/
		);
		expect(
			within(samples).getByText(
				"The duty's rise (the duty check). Its solve did not converge. Statuses oscillate between states already solved (components: PB)."
			)
		).toBeVisible();
	});

	it('tells a dead-headed duty’s noise as 0, saying so, and the check’s tolerance as the API’s', async () => {
		const c = named('parallel-ideal');
		// Made-up, as the API answers a station whose inlet is closed: flows of solver noise.
		const response = structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
		response.duty!.flow = -2.474e-35;
		response.dutyCheck = {
			agrees: true,
			flow: -5.942e-15,
			members: response.duty!.members.map((x) => ({ pumpId: x.pumpId, flow: x.flow })),
			message: 'made-up server words'
		};
		render(PumpGroupChart, props(c, { curve: { status: 'ready', response } }));
		expect(
			screen.getByText(
				"At the duty's rise the group curve gives the solve's flows, the station's and every pump's (within 0.5 % or 0.001 L/s): it passes through the Group point."
			)
		).toBeVisible();
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		const line = screen.getByText(/Group duty \(station's flow\):/);
		expect(line).toHaveTextContent(
			/Group duty \(station's flow\): 0 L\/s at a rise of .*Duty check: the group curve passes through it; at the duty's rise it gives 0 L\/s \(the solve: 0 L\/s\); flows below 0\.001 L\/s, the check's floor, are shown as 0\./
		);
	});

	it('asks to tick another pump inside only when it has a box', () => {
		const c = named('parallel-ideal');
		const issues: TopologyIssue[] = [
			{
				code: 'OTHER_PUMP_INSIDE',
				message: 'made-up server words',
				componentIds: ['PC'],
				connectionIds: []
			}
		];
		// Made-up: a standby pump PC between the tees, closed off by its valves, so no result and
		// no box.
		const project = structuredClone(c.project);
		project.components.push({
			...project.components.find((x) => x.id === 'PA')!,
			id: 'PC',
			name: 'Standby PC'
		});
		render(
			PumpGroupChart,
			props(c, { project, curve: { status: 'refused', message: 'x', issues } })
		);
		expect(screen.queryByRole('checkbox', { name: /Standby PC/ })).toBeNull();
		const item = within(
			screen.getByRole('list', { name: 'Why they do not form a station' })
		).getByRole('listitem');
		expect(item).toHaveTextContent(
			'Standby PC lies between the pumps and the rest of the network but has no results in this case (closed off), so it cannot be ticked: a station holds no other pump. Open it to the network and solve again, or choose other pumps.'
		);
		expect(item).not.toHaveTextContent(/tick it too/);
	});

	it('says why a converged case has no group curve: no duty, in the API’s words', () => {
		const c = named('no-duty');
		const response = c.groupCurve.body as PumpGroupCurveResponse;
		render(PumpGroupChart, props(c));
		expect(
			screen.getByText(`No group curve for this case: ${response.message.replace(/\.$/, '')}.`)
		).toBeVisible();
		expect(screen.queryByText(/Duty check/)).toBeNull();
	});

	it('says why no image can be made, and makes one with the caption and notes', async () => {
		const c = named('parallel-crane');
		const view = render(PumpGroupChart, props(c, { image: image(), caseName: 'Winter' }));
		const button = () =>
			screen.getByRole('button', {
				name: 'Download image of the pumps together: Pump PA, Pump PB, Winter'
			});
		await vi.waitFor(() => expect(button()).not.toHaveAttribute('aria-disabled', 'true'), {
			timeout: 10_000
		});
		await fireEvent.click(button());
		await vi.waitFor(() => expect(images.requests).toHaveLength(1));
		const request = images.requests[0] as FigureImageRequest;
		expect(request.title).toBe('Pumps together: Pump PA, Pump PB (parallel)');
		expect(request.caseName).toBe('Winter');
		expect(request.content).toBe('Pumps together Pump PA, Pump PB');
		expect(request.lines[0]).toMatch(/^Pump curves and points are at each pump's flanges\./);
		await view.rerender(props(c, { image: image(), curve: { status: 'loading' } }));
		const loading = screen.getByRole('button', { name: /^Download image of the pumps together/ });
		expect(loading).toHaveAccessibleDescription(
			'Wait until the group curve is computed, or cancel it.'
		);
		await view.rerender(
			props(c, {
				image: image({
					unavailable:
						'This solve did not converge: its values are not a solution, so no image is made.'
				})
			})
		);
		expect(
			screen.getByRole('button', { name: /^Download image of the pumps together/ })
		).toHaveAccessibleDescription(
			'This solve did not converge: its values are not a solution, so no image is made.'
		);
	});

	it('shows no values for results that are not a solution, or not the latest', () => {
		const c = named('parallel-ideal');
		render(
			PumpGroupChart,
			props(c, {
				unavailable:
					'This solve did not converge: its values are not a solution, so the card shows none.'
			})
		);
		expect(
			screen.getByText(
				'This solve did not converge: its values are not a solution, so the card shows none.'
			)
		).toBeVisible();
		expect(screen.queryByRole('figure')).toBeNull();
		expect(screen.queryByRole('table')).toBeNull();
	});

	it('labels out-of-date results and the case in the caption', () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { stale: true, caseName: 'Winter' }));
		expect(
			screen.getByRole('figure', {
				name: 'Pump PA and Pump PB in parallel, Winter (out of date)'
			})
		).toBeVisible();
	});

	it('keeps the tables when the chart cannot be loaded', async () => {
		const c = named('parallel-ideal');
		HTMLCanvasElement.prototype.getContext = (() => null) as unknown as typeof getContext;
		render(PumpGroupChart, props(c));
		await vi.waitFor(
			() => expect(screen.getByText(/The chart cannot be drawn in this browser/)).toBeVisible(),
			{ timeout: 10_000 }
		);
		expect(
			screen.getByRole('table', { name: "Each pump's point (flow through it)" })
		).toBeVisible();
		expect(screen.getByRole('region', { name: 'The pumps in the group' })).toBeVisible();
	});
});

describe('the group system curve (slice 4b)', () => {
	type Plugin = { id: string; afterDatasetsDraw?: unknown };
	type Config = Recorded & { plugins: Plugin[] };

	it('is drawn in orange with its legend entry, the Group point at the crossing', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		const config = charts[0]!.config as Config;
		const system = config.data.datasets.find((d) => d.label.startsWith('Group system curve'));
		expect(system).toMatchObject({ borderColor: '#eb6834', spanGaps: false });
		expect(config.data.datasets.at(-1)!.label).toBe(
			'Group duty, where the group curve and the group system curve cross'
		);
		const figure = screen.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' });
		const legend = within(figure).getByRole('list', { name: 'Legend' });
		expect(
			within(legend)
				.getAllByRole('listitem')
				.map((li) => li.textContent!.trim())
		).toEqual([
			'Pump PA, 100 % speed (own flow)',
			'Pump PB, 85 % speed (own flow)',
			"Group curve (station's flow)",
			'Group curve, a pump beyond its data (dashed)',
			"Group system curve (the rest of the network between the station's inlet and outlet, station's flow)",
			'▲ Pump PA',
			'■ Pump PB',
			'● Group duty, where the group curve and the group system curve cross'
		]);
		expect(
			within(legend)
				.getByText(/^Group system curve/)
				.querySelector('line')
		).toHaveAttribute('stroke', '#eb6834');
		expect(within(figure).getByRole('img')).toHaveAccessibleName(
			/, on the group curve and the group system curve, where they cross; group curve shown; group system curve shown\.$/
		);
		expect(
			within(figure).getByText(
				"The group's system curve is the rise the rest of the network needs between Tee T1 (run inlet) and Tee T2 (run outlet) at each total flow; it does not depend on how the pumps share the flow."
			)
		).toBeVisible();
		expect(screen.getByText('How the group curve is computed')).toBeInTheDocument();
		expect(screen.getByText('How the group system curve is computed')).toBeInTheDocument();
	});

	it('shows its progress with its own Cancel, then its failure with a retry; the group curve stays', async () => {
		const c = named('parallel-ideal');
		const oncancelsystem = vi.fn();
		const onretrysystem = vi.fn();
		const values = (system: GroupCurveState) => props(c, { system, oncancelsystem, onretrysystem });
		const view = render(PumpGroupChart, values({ status: 'loading' }));
		await drawn();
		expect(screen.getByRole('status')).toHaveTextContent(
			'Computing the group system curve for this solve…'
		);
		// The figure is busy while either curve is computed, as the pump chart's for its system curve.
		const figure = screen.getByRole('figure');
		expect(figure).toHaveAttribute('aria-busy', 'true');
		const cancel = screen.getByRole('button', { name: 'Cancel the group system curve' });
		expect(screen.queryByRole('button', { name: 'Cancel the group curve' })).toBeNull();
		cancel.focus();
		await fireEvent.click(cancel);
		expect(oncancelsystem).toHaveBeenCalledTimes(1);
		await view.rerender(values({ status: 'cancelled', by: 'user' }));
		await tick();
		await tick();
		expect(figure).toHaveAttribute('aria-busy', 'false');
		const compute = screen.getByRole('button', { name: 'Compute the group system curve' });
		expect(compute).toHaveFocus();
		expect(compute).toHaveAccessibleDescription(
			'The group system curve was not computed: you cancelled it.'
		);
		await fireEvent.click(compute);
		expect(onretrysystem).toHaveBeenCalledTimes(1);
		await view.rerender(values({ status: 'loading' }));
		await tick();
		await tick();
		expect(screen.getByRole('button', { name: 'Cancel the group system curve' })).toHaveFocus();
		await view.rerender(values({ status: 'error', message: 'The server is busy.' }));
		expect(
			screen.getByRole('button', { name: 'Try the group system curve again' })
		).toHaveAccessibleDescription(
			'The group system curve could not be computed: The server is busy.'
		);
		// The group curve is still drawn, with its samples to read along.
		const legend = screen.getByRole('list', { name: 'Legend' });
		expect(within(legend).getByText("Group curve (station's flow)")).toBeVisible();
		expect(within(legend).queryByText(/^Group system curve/)).toBeNull();
		expect(screen.getByRole('slider', { name: 'Read along the curves' })).toBeVisible();
	});

	it('the group curve refused for a PRV inside only: says so, and draws the group system curve', async () => {
		const c = named('prv-inside');
		const body = c.groupCurve.body as { message: string; issues: TopologyIssue[] };
		const oninspect = vi.fn();
		render(
			PumpGroupChart,
			props(c, {
				curve: { status: 'refused', message: body.message, issues: body.issues },
				system: systemReady(c),
				oninspect
			})
		);
		await drawn();
		expect(
			screen.getByText(
				"These pumps form a station, but its group curve is not defined there; its group system curve is, and the pumps' own curves and points are drawn."
			)
		).toBeVisible();
		const why = screen.getByRole('list', { name: 'Why the group curve is not defined' });
		await fireEvent.click(within(why).getByRole('button', { name: 'Control valve V1' }));
		expect(oninspect).toHaveBeenCalledWith('V1');
		const labels = (charts[0]!.config as Recorded).data.datasets.map((d) => d.label);
		expect(labels.some((l) => l.startsWith('Group system curve'))).toBe(true);
		expect(labels).not.toContain("Group curve (station's flow)");
		expect(labels.at(-1)).toBe('Group duty, on the group system curve');
		// No group curve: nothing to read along, and no group curve's samples.
		expect(screen.queryByRole('slider')).toBeNull();
		expect(screen.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' })).toBeVisible();
	});

	it('lists its points in the data table, each rise or why it has none, and the system duty check', async () => {
		const c = named('fcv-outside');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		const table = screen.getByRole('table', {
			name: "Group system curve (rise the rest of the network needs at each station's flow)"
		});
		const response = c.systemCurve!.body as PumpGroupCurveResponse;
		const points = [...response.systemPoints].sort((a, b) => a.flow - b.flow);
		const rows = within(table).getAllByRole('row').slice(1);
		expect(rows).toHaveLength(points.length);
		for (const [i, p] of points.entries()) {
			const cells = within(rows[i]!)
				.getAllByRole('cell')
				.map((td) => td.textContent!);
			expect(cells[0]).toBe(formatNumber(p.flow * 1000, 4));
			expect(cells[1]).toBe(p.head === null ? '—' : formatNumber(p.head, 4));
			if (p.head === null) {
				expect(cells[2]).toMatch(
					/^No steady state carries this flow: every way from the station's outlet back to its inlet, .* passes Control valve FC, which passes at most 60 L\/s that way/
				);
				expect(cells[2]).toContain(`Calculation server's message: ${p.message}`);
			}
			if (p.isDuty) expect(cells[2]).toBe("The duty's flow (the system duty check).");
		}
		expect(
			screen.getByText(/System duty check: the group system curve passes through it\./)
		).toBeVisible();
		expect(
			screen.getByText(
				`${points.filter((p) => p.head === null).length} of ${points.length} group-system-curve points have no rise: the line has gaps there, and the data table says why for each.`
			)
		).toBeVisible();
	});

	it('a system duty check that disagrees: its words, the server’s under Details, and D13', async () => {
		const c = named('parallel-crane');
		const system = structuredClone(c.systemCurve!.body as PumpGroupCurveResponse);
		Object.assign(system.systemDutyCheck!, {
			agrees: false,
			head: system.duty!.head + 2,
			message: 'made-up server words'
		});
		render(PumpGroupChart, props(c, { system: { status: 'ready', response: system } }));
		await drawn();
		const note = screen.getByText(/^The group system curve does not pass through the Group point:/);
		expect(note).toHaveTextContent(
			`at the duty's flow it needs a rise of ${formatNumber(system.duty!.head + 2, 4)} m (the solve: ${formatNumber(system.duty!.head, 4)} m), more than 0.5 % or 0.01 m apart.`
		);
		expect(
			within(note).getByText("Calculation server's message: made-up server words")
		).toBeInTheDocument();
		expect(
			screen.getByText(
				'Several steady states can exist (D13); the point is the one the solve found.'
			)
		).toBeVisible();
		expect((charts[0]!.config as Recorded).data.datasets.at(-1)!.label).toBe(
			'Group duty, on the group curve'
		);
	});

	it('reads along the curves: each sample from the response, its value text, marked on the chart', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		const response = c.groupCurve.body as PumpGroupCurveResponse;
		const points = [...response.points].sort((a, b) => a.head - b.head);
		const slider = screen.getByRole('slider', {
			name: 'Read along the curves'
		}) as HTMLInputElement;
		// A native range input (the browser's keys step it), one step per sample, at the duty's.
		expect(slider.type).toBe('range');
		expect(slider).toHaveAttribute('min', '0');
		expect(slider).toHaveAttribute('max', String(points.length - 1));
		expect(slider).toHaveAttribute('step', '1');
		expect(slider.closest('div')!.parentElement).toHaveClass('space-y-1');
		const duty = points.findIndex((p) => p.isDuty);
		expect(slider.value).toBe(String(duty));
		const words = (i: number) => {
			const p = points[i]!;
			const l = (q: number) => `${formatNumber(q * 1000, 4)} L/s`;
			const member = (id: string) => {
				const x = p.members.find((m) => m.pumpId === id)!;
				return `${id === 'PA' ? 'Pump PA' : 'Pump PB'} ${l(x.flow)}${x.status === 'running' ? '' : ' (no flow)'}`;
			};
			return `At a rise of ${formatNumber(p.head, 4)} m: ${member('PA')}, ${member('PB')}, group ${l(p.flow!)}`;
		};
		expect(slider).toHaveAttribute('aria-valuetext', `${words(duty)} (the duty's rise)`);
		const readout = document.querySelector('[data-group-readout]')!;
		expect(readout).toHaveTextContent(`${words(duty)} (the duty's rise)`);
		const draws = charts[0]!.draws;
		// The next sample (an arrow key moves the native slider: its value and input event).
		await fireEvent.input(slider, { target: { value: String(duty + 1) } });
		expect(slider).toHaveAttribute('aria-valuetext', words(duty + 1));
		expect(readout).toHaveTextContent(words(duty + 1));
		expect(charts[0]!.draws).toBeGreaterThan(draws);
		// The mark: drawn by the chart's own plugin, from the sample read (the response's values).
		const config = charts[0]!.config as Config;
		expect(config.plugins.map((p) => p.id)).toEqual(['groupLabels', 'groupReadout']);
		await fireEvent.input(slider, { target: { value: '0' } });
		expect(slider).toHaveAttribute('aria-valuetext', words(0));
		// Back to the duty: the button, or Escape. The button goes, so the focus moves to the slider.
		const back = screen.getByRole('button', { name: 'Back to the duty' });
		back.focus();
		await fireEvent.click(back);
		await tick();
		expect(slider).toHaveAttribute('aria-valuetext', `${words(duty)} (the duty's rise)`);
		expect(screen.queryByRole('button', { name: 'Back to the duty' })).toBeNull();
		expect(slider).toHaveFocus();
		await fireEvent.input(slider, { target: { value: String(points.length - 1) } });
		await fireEvent.keyDown(slider, { key: 'Escape' });
		expect(slider).toHaveAttribute('aria-valuetext', `${words(duty)} (the duty's rise)`);
		expect(slider).toHaveAccessibleDescription(
			"Steps over the group curve's samples, each pump's flow and the station's as computed at that rise (nothing between samples is read)."
		);
	});

	it('the image draws the group system curve and its legend entry, with its notes', async () => {
		const c = named('parallel-crane');
		render(PumpGroupChart, props(c, { system: systemReady(c), image: image() }));
		const button = () =>
			screen.getByRole('button', { name: /^Download image of the pumps together/ });
		await vi.waitFor(() => expect(button()).not.toHaveAttribute('aria-disabled', 'true'), {
			timeout: 10_000
		});
		await fireEvent.click(button());
		await vi.waitFor(() => expect(images.requests).toHaveLength(1));
		const request = images.requests[0] as FigureImageRequest;
		const config = request.config as unknown as Config & {
			options: { plugins: { legend: { display: boolean } } };
		};
		const system = config.data.datasets.find((d) => d.label.startsWith('Group system curve'));
		expect(system).toMatchObject({ borderColor: '#eb6834' });
		expect(config.options.plugins.legend.display).toBe(true);
		// No readout mark in the image.
		expect(config.plugins.map((p) => p.id)).toEqual(['groupLabels']);
		// The caption is unchanged; the footer has the group system curve's notes.
		expect(request.title).toBe('Pumps together: Pump PA, Pump PB (parallel)');
		expect(request.lines).toContain(
			"The group's system curve is the rise the rest of the network needs between Tee T1 (run inlet) and Tee T2 (run outlet) at each total flow; it does not depend on how the pumps share the flow."
		);
		expect(request.lines).toContain(
			"At the duty's flow the group system curve gives the solve's rise (within 0.5 % or 0.01 m): it passes through the Group point, where it crosses the group curve."
		);
	});

	it('shows nothing of it for results that are not a solution', () => {
		const c = named('parallel-ideal');
		render(
			PumpGroupChart,
			props(c, {
				system: systemReady(c),
				unavailable:
					'This solve did not converge: its values are not a solution, so the card shows none.'
			})
		);
		expect(screen.queryByRole('figure')).toBeNull();
		expect(screen.queryByText(/group system curve/i)).toBeNull();
	});
});

describe('one pump off (slice 4d), now the Add cases block under Each pump off (D24)', () => {
	// 4d's assertions on its block, driven through D24's block with Each pump off chosen (4d's
	// cases). Only the strings pump-lineups.md §7.12 lists under "4d's strings that change"
	// changed, each named where it does.
	type Answer = { status: number; body: unknown };
	type OneOffCase = FixtureCase & {
		solve: SolveResponse;
		scenarioCases: Record<string, { solve: SolveResponse; groupCurve: Answer }>;
	};
	const c = named('one-off') as unknown as OneOffCase;
	const station = (c.groupCurve.body as PumpGroupCurveResponse).station;
	const runnable = {
		count: 2,
		canRun: true,
		reason: '',
		hint: 'Solves each case whose results are missing or out of date, one after another: up to 2 solves.'
	};
	/**
	 * The block's props for the base case of `project` (default: `one-off` without its scenarios),
	 * Each pump off chosen, with the handlers given.
	 */
	function plan(
		values: Partial<LineupPlanInput> = {},
		solveAll: typeof runnable = runnable,
		handlers: { onadd?: () => void; onsolveall?: () => void } = {}
	) {
		return {
			plan: lineupPlan({
				project: withScenarios(structuredClone(c.project), []),
				shownCase: null,
				station,
				memberIds: ['PA', 'PB'],
				base: { response: c.solve, stale: false },
				preset: 'each',
				savedOrder: [],
				...values
			}),
			solveAll,
			...handlers
		};
	}
	const base = (values: Record<string, unknown> = {}) =>
		props(c, { system: systemReady(c), caseName: 'Base case', ...values });
	// §7.12: the h4 and region name "One pump off" becomes "Add cases".
	const block = () => screen.getByRole('region', { name: 'Add cases' });
	/** The add button, by any of its labels ("Add {n} case(s)", or "Add cases"). */
	const ADD = /^Add (\d+ )?cases?$/;

	/** The `one-off` scenarios as the card has them, every one ready. */
	function others(ids = ['S1', 'S2', 'S3', 'S4']): OtherGroupCase[] {
		return otherGroupCases({
			valued: ids.map((id) => ({
				key: id,
				caseId: id,
				name: c.project.scenarios!.find((s) => s.id === id)!.name,
				stale: false,
				group: {
					status: 'ready',
					response: c.scenarioCases[id]!.groupCurve.body as PumpGroupCurveResponse
				},
				system: undefined,
				shared: id !== 'S3',
				solved: null
			})),
			shownKeys: new Set(ids),
			othersOn: true,
			shownSettled: true,
			station,
			systemShown: c.systemCurve!.body as PumpGroupCurveResponse,
			memberIds: ['PA', 'PB'],
			project: c.project,
			boxes: ['PA', 'PB']
		});
	}

	it('offers the add for a parallel station, and says why it is not offered otherwise', async () => {
		const view = render(PumpGroupChart, base({ lineups: plan() }));
		expect(within(block()).getByRole('heading', { name: 'Add cases', level: 4 })).toBeVisible();
		expect(block()).toHaveTextContent(
			'Makes one scenario per pump running in the base case (Pump PA and Pump PB): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		const add = within(block()).getByRole('button', { name: 'Add 2 cases' });
		expect(add).not.toHaveAttribute('aria-disabled', 'true');
		// §7.12: gates 1, 2 and 3 take §7.2's rows 1, 2 and 3; gate 4 is 4d's.
		const gates: [Partial<LineupPlanInput>, string, boolean][] = [
			[
				{ station: (named('series').groupCurve.body as PumpGroupCurveResponse).station },
				'Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.',
				false
			],
			[
				{ station: { ...station, arrangement: 'mixed' } },
				'Cases are added here for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.',
				false
			],
			[
				{ project: c.project, shownCase: 'S3' },
				'Cases are made from the base case: show the base case to add them. To study Delivery tank 5 m higher with pumps off, duplicate it in Scenarios and set those pumps off there.',
				false
			],
			[
				{ base: { response: c.solve, stale: true } },
				"The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now.",
				true
			]
		];
		for (const [values, sentence, solveAll] of gates) {
			await view.rerender(base({ lineups: plan(values) }));
			expect(block()).toHaveTextContent(sentence);
			expect(within(block()).queryByRole('button', { name: ADD })).toBeNull();
			expect(!!within(block()).queryByRole('button', { name: /^Solve all/ })).toBe(solveAll);
		}
		// No plan, or no station: no block.
		await view.rerender(base({ lineups: null }));
		expect(screen.queryByRole('region', { name: 'Add cases' })).toBeNull();
	});

	it('refuses the add with its reason, described, and makes nothing', async () => {
		const onadd = vi.fn();
		render(PumpGroupChart, base({ lineups: plan({ project: c.project }, runnable, { onadd }) }));
		// §7.12: "Add cases with one pump off" becomes "Add cases".
		const add = within(block()).getByRole('button', { name: 'Add cases' });
		expect(add).toHaveAttribute('aria-disabled', 'true');
		expect(add).toHaveAccessibleDescription(
			'Every case with one pump off already exists: Pump PA off and Pump PB off.'
		);
		// §7.12: "{name} has its case already: {found.name}." becomes the preview item
		// "{offName}: already a scenario, «{other}» ({id})", in §7.7's short form: the names are equal.
		expect(block()).toHaveTextContent('Pump PA off: already a scenario (S1)');
		await fireEvent.click(add);
		expect(onadd).not.toHaveBeenCalled();
	});

	it('adds, then gives the focus to Solve all, which stays in place with its reasons', async () => {
		const onadd = vi.fn();
		const onsolveall = vi.fn();
		const view = render(
			PumpGroupChart,
			base({ lineups: plan({}, runnable, { onadd, onsolveall }) })
		);
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		await fireEvent.click(within(block()).getByRole('button', { name: 'Add 2 cases' }));
		expect(onadd).toHaveBeenCalledTimes(1);
		await tick();
		const solveAll = within(block()).getByRole('button', { name: 'Solve all (2)' });
		expect(solveAll).toHaveFocus();
		expect(solveAll).toHaveAccessibleDescription(runnable.hint);
		await fireEvent.click(solveAll);
		expect(onsolveall).toHaveBeenCalledTimes(1);
		// A run: unavailable, with the reason; it stays, with the focus, when nothing is left.
		const states = [
			{ count: 2, canRun: false, reason: 'Solve all is running; Cancel in the header stops it.' },
			{ count: 0, canRun: false, reason: "Every case's results are current." },
			{
				count: 0,
				canRun: false,
				reason: 'Every case is solved except Pump PB off, which has an error to fix first.'
			}
		];
		for (const state of states) {
			await view.rerender(
				base({ lineups: plan({}, { ...state, hint: runnable.hint }, { onadd, onsolveall }) })
			);
			const button = within(block()).getByRole('button', { name: /^Solve all/ });
			expect(button).toBe(solveAll);
			expect(button).toHaveFocus();
			expect(button).toHaveAccessibleName(state.count ? 'Solve all (2)' : 'Solve all');
			expect(button).toHaveAttribute('aria-disabled', 'true');
			expect(button).toHaveAccessibleDescription(state.reason);
			await fireEvent.click(button);
		}
		expect(onsolveall).toHaveBeenCalledTimes(1);
	});

	it('the other cases: the box, the cases on the chart (six at most), progress, Cancel, again', async () => {
		const onothers = vi.fn();
		const onotherstick = vi.fn();
		const oncancelothers = vi.fn();
		const onretryothers = vi.fn();
		const [first] = others(['S1']);
		// Seven cases (synthetic): six on the chart, the seventh not (unticked, past the limit).
		const seven: OtherGroupCase[] = Array.from({ length: 7 }, (_, i) => ({
			...first!,
			key: `S${i + 1}`,
			caseId: `S${i + 1}`,
			name: `Case ${i + 1}`,
			...(i < 6
				? { number: i + 1 }
				: {
						onChart: false,
						number: null,
						state: 'unticked' as const,
						duty: null,
						claim: null,
						words: 'not on the chart (unticked under Cases on this chart)'
					})
		}));
		const handlers = { onothers, onotherstick, oncancelothers, onretryothers };
		const view = render(PumpGroupChart, base({ otherCases: seven, othersOn: true, ...handlers }));
		const fieldset = screen.getByRole('group', { name: 'Cases on this chart' });
		expect(fieldset).toHaveTextContent('Base case (shown)');
		const boxes = within(fieldset).getAllByRole('checkbox') as HTMLInputElement[];
		expect(boxes.map((b) => b.checked)).toEqual([true, true, true, true, true, true, false]);
		expect(boxes[0]!.closest('label')).toHaveTextContent('○ 1 · Case 1');
		expect(boxes[6]).toHaveAttribute('aria-disabled', 'true');
		expect(boxes[6]).toHaveAccessibleDescription('At most 6 other cases at once.');
		await fireEvent.click(boxes[6]!);
		expect(onotherstick).not.toHaveBeenCalled();
		await fireEvent.click(boxes[1]!);
		expect(onotherstick).toHaveBeenCalledWith('S2', false);
		const box = screen.getByRole('checkbox', { name: "Also show the other cases' station duties" });
		expect(box).toBeChecked();
		expect(box).toHaveAccessibleDescription(
			"Each case's station duty is computed on request, one case at a time, for that case's last solve: a solve of that case and about 41 solves of the station (its group curve, which the card shows when that case is shown)."
		);
		await fireEvent.click(box);
		expect(onothers).toHaveBeenCalledWith(false);

		// Being computed: the progress in the one live region, and Cancel.
		const loading = others(['S1', 'S2']).map((o, i) =>
			i === 1 ? { ...o, state: 'loading' as const, number: null, duty: null, claim: null } : o
		);
		await view.rerender(
			base({
				otherCases: loading,
				othersOn: true,
				othersProgress: { done: 1, total: 2 },
				...handlers
			})
		);
		expect(screen.getByRole('status')).toHaveTextContent(
			"Computing the other cases' station duties: 2 of 2…"
		);
		expect(screen.getByRole('figure')).toHaveAttribute('aria-busy', 'true');
		const cancel = screen.getByRole('button', { name: "Cancel the other cases' station duties" });
		cancel.focus();
		await fireEvent.click(cancel);
		expect(oncancelothers).toHaveBeenCalledTimes(1);
		const cancelled = loading.map((o, i) =>
			i === 1
				? {
						...o,
						state: 'cancelled' as const,
						retry: true,
						words: 'cancelled: you cancelled it'
					}
				: o
		);
		await view.rerender(
			base({ otherCases: cancelled, othersOn: true, othersProgress: null, ...handlers })
		);
		await tick();
		await tick();
		const again = screen.getByRole('button', { name: 'Compute them again' });
		expect(again).toHaveFocus();
		expect(again).toHaveAccessibleDescription(
			"Not every other case's station duty was computed: see Running combinations."
		);
		await fireEvent.click(again);
		expect(onretryothers).toHaveBeenCalledTimes(1);
		await view.rerender(
			base({
				otherCases: loading,
				othersOn: true,
				othersProgress: { done: 1, total: 2 },
				...handlers
			})
		);
		await tick();
		await tick();
		expect(
			screen.getByRole('button', { name: "Cancel the other cases' station duties" })
		).toHaveFocus();
		// Pressed while a calculation runs, the cases wait for it with no progress line (the Pumps
		// view gives none then) and no Cancel: the focus goes to the figure.
		await view.rerender(
			base({ otherCases: cancelled, othersOn: true, othersProgress: null, ...handlers })
		);
		screen.getByRole('button', { name: 'Compute them again' }).focus();
		await fireEvent.click(screen.getByRole('button', { name: 'Compute them again' }));
		expect(onretryothers).toHaveBeenCalledTimes(2);
		await view.rerender(
			base({ otherCases: loading, othersOn: true, othersProgress: null, ...handlers })
		);
		await tick();
		await tick();
		expect(screen.queryByRole('button', { name: 'Compute them again' })).toBeNull();
		expect(
			screen.queryByRole('button', { name: "Cancel the other cases' station duties" })
		).toBeNull();
		expect(screen.getByRole('figure')).toHaveFocus();
	});

	it('Running combinations: a row group per case, its members’ rows, invalid values marked; the extremes', () => {
		const dead = named('one-off-dead-headed') as unknown as OneOffCase;
		const input: CombinationsInput = {
			members: [
				{ id: 'PA', name: 'Pump PA', slot: 0 },
				{ id: 'PB', name: 'Pump PB', slot: 1 }
			],
			cases: [
				{
					key: '',
					name: 'Base case',
					shown: true,
					status: 'solved',
					response: c.solve,
					stale: false,
					station: 'Station 55.15 L/s at a rise of 27.38 m'
				},
				{
					key: 'S2',
					name: 'Pump PB off',
					shown: false,
					status: 'stale',
					response: c.scenarioCases.S2!.solve,
					stale: true,
					station: null,
					ring: 2
				},
				{
					key: 'S9',
					name: 'Held (synthetic)',
					shown: false,
					status: 'solved',
					response: dead.solve,
					stale: false,
					station: null
				},
				{
					key: 'S5',
					name: 'Failed case',
					shown: false,
					status: 'failed',
					response: null,
					stale: false,
					station: null
				}
			],
			prefs: c.project.settings.units,
			project: c.project
		};
		render(
			PumpGroupChart,
			base({
				combinations: runningCombinations(input),
				extremes: combinationExtremes(input)
			})
		);
		const table = screen.getByRole('table', { name: 'Running combinations' });
		const groups = within(table).getAllByRole('rowgroup');
		// The header, then one group per case.
		expect(groups).toHaveLength(5);
		const headings = within(table)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'rowgroup');
		// Each case with values gains D24's lineup line (§7.10) between its heading and 4d's station
		// line, read from its solve (a case without values has none).
		expect(headings.map((h) => h.textContent!.replace(/\s+/g, ' ').trim())).toEqual([
			'Base case (shown) 2 of 2 carrying flow: Pump PA and Pump PB Station 55.15 L/s at a rise of 27.38 m',
			'Pump PB off (out of date) · ring 2 1 of 2 carrying flow: Pump PA; off: Pump PB',
			'Held (synthetic) 1 of 2 carrying flow: Pump PA; on, carrying no flow: Pump PB',
			'Failed case Failed'
		]);
		expect([...headings[0]!.children].map((line) => line.textContent)).toEqual([
			'Base case (shown)',
			'2 of 2 carrying flow: Pump PA and Pump PB',
			'Station 55.15 L/s at a rise of 27.38 m'
		]);
		const held = groups[3]!;
		const rows = within(held).getAllByRole('row');
		expect(rows).toHaveLength(3);
		const pb = rows[2]!;
		expect(within(pb).getByRole('rowheader')).toHaveTextContent('Pump PB');
		// A long name wraps on a phone (the list has no sideways scroll; the e2e measures it).
		expect(within(pb).getByRole('rowheader')).toHaveClass(
			'max-sm:whitespace-normal',
			'max-sm:break-words'
		);
		const cells = within(pb).getAllByRole('cell');
		expect(cells[0]).toHaveTextContent('No flow (system head above shutoff)');
		// Speed next (Pump PB at another speed), then the flow, marked.
		expect(cells[1]).toHaveAttribute('data-label', 'Speed (%)');
		expect(cells[2]).toHaveAttribute('data-label', 'Flow (L/s)');
		expect(cells[2]).toHaveTextContent('physically invalid:');
		expect(cells.at(-1)).toHaveTextContent('Invalid');
		// Not marked where the pump has no invalid flag.
		const pa = within(groups[1]!).getAllByRole('row')[1]!;
		expect(within(pa).getAllByRole('cell')[2]).toHaveAttribute('data-label', 'Flow (L/s)');
		expect(within(pa).getAllByRole('cell')[2]).not.toHaveTextContent('physically invalid');
		expect(within(groups[4]!).getAllByRole('row')).toHaveLength(1);
		const extremes = screen.getByLabelText('Extremes over these cases');
		expect(extremes.tagName).toBe('DL');
		expect(
			screen.getByRole('heading', { name: 'Extremes over these cases (current results)' })
		).toBeVisible();
		expect(extremes).toHaveTextContent(
			'Pump PA, largest flow: 40.75 L/s in Held (synthetic); beyond its curve data (over 2 of 2 cases)'
		);
		expect(screen.getByText('Not counted (out of date): Pump PB off.')).toBeVisible();
	});

	it('the figure: the rings in the legend and the name, the data table’s rows, no image while computed', async () => {
		const list = others();
		const view = render(
			PumpGroupChart,
			base({ otherCases: list, othersOn: true, onothers: () => {}, image: image() })
		);
		const figure = screen.getByRole('figure');
		const legend = within(figure).getByRole('list', { name: 'Legend' });
		const items = within(legend)
			.getAllByRole('listitem')
			.map((li) => li.textContent!.trim());
		expect(items.slice(-4)).toEqual([
			'○ 1 · Pump PA off (station duty)',
			'○ 2 · Pump PB off (station duty)',
			'○ 3 · Delivery tank 5 m higher (station duty)',
			'○ 4 · Both pumps off (station duty)'
		]);
		expect(within(figure).getByRole('img')).toHaveAccessibleName(
			/; other cases' station duties: 1 · Pump PA off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network\); 2 · Pump PB off, .*; 4 · Both pumps off, 0 L\/s at a rise of 19 m \(Not said: at zero station flow the rest can hold more than one state \(D13\)\); group curve shown; group system curve shown\.$/
		);
		await drawn();
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		const table = screen.getByRole('table', { name: "Other cases' station duties" });
		const rows = within(table)
			.getAllByRole('row')
			.slice(1)
			.map((r) =>
				[...r.querySelectorAll('th, td')].map((cell) =>
					cell.textContent!.replace(/\s+/g, ' ').trim()
				)
			);
		const duty = (id: string) =>
			(c.scenarioCases[id]!.groupCurve.body as PumpGroupCurveResponse).duty!;
		expect(rows[0]).toEqual([
			'○ 1 · Pump PA off',
			formatNumber(duty('S1').flow * 1000, 4),
			formatNumber(duty('S1').head, 4),
			'Yes: the same rest of the network'
		]);
		expect(rows[2]![3]).toBe(
			"No: the rest of the network differs from this case's; its own group system curve is not drawn"
		);
		expect(rows[3]!.slice(1, 3)).toEqual(['0', '19']);
		// The box off: one note for every other case, no list, and no table of them.
		const off = otherGroupCases({
			valued: ['S1', 'S2', 'S3', 'S4'].map((id) => ({
				key: id,
				caseId: id,
				name: c.project.scenarios!.find((s) => s.id === id)!.name,
				stale: false,
				group: undefined,
				system: undefined,
				shared: id !== 'S3',
				solved: null
			})),
			shownKeys: new Set(['S1', 'S2', 'S3', 'S4']),
			othersOn: false,
			shownSettled: true,
			station,
			systemShown: c.systemCurve!.body as PumpGroupCurveResponse,
			memberIds: ['PA', 'PB'],
			project: c.project,
			boxes: ['PA', 'PB']
		});
		await view.rerender(
			base({ otherCases: off, othersOn: false, onothers: () => {}, image: image() })
		);
		expect(
			screen.getByText(
				"Other cases' station duties are not on the chart: tick “Also show the other cases' station duties” to compute them (4 other cases with results)."
			)
		).toBeVisible();
		expect(screen.queryByText(/not computed: tick/)).toBeNull();
		expect(screen.queryByText(/^Not on the chart:/)).toBeNull();
		expect(screen.queryByRole('table', { name: "Other cases' station duties" })).toBeNull();
		expect(
			screen.getByRole('table', { name: "Each pump's point (flow through it)" })
		).toBeVisible();

		// While the other cases' duties are computed: no image, and the figure is busy.
		await view.rerender(
			base({
				otherCases: list.map((o, i) =>
					i === 3 ? { ...o, state: 'loading' as const, number: null, duty: null } : o
				),
				othersOn: true,
				onothers: () => {},
				image: image(),
				othersProgress: { done: 3, total: 4 }
			})
		);
		expect(screen.getByRole('figure')).toHaveAttribute('aria-busy', 'true');
		expect(
			screen.getByRole('button', { name: /^Download image of the pumps together/ })
		).toHaveAccessibleDescription(
			"Wait until the other cases' station duties are computed, or cancel them."
		);
	}, 20_000);
});

describe('the curve family (D24 slice L3, pump-lineups.md §9.6, §10.3 Component)', () => {
	/** The `lineups` case names, as the fixture stores them. */
	const NAMES: Record<string, string> = {
		S1: '3 of 4 running (Pump P4 off)',
		S2: '2 of 4 running (Pump P3, Pump P4 off)',
		S3: '1 of 4 running (Pump P2, Pump P3, Pump P4 off)',
		S4: 'Pump P1 off',
		S5: 'Pump P2 off',
		S6: 'Pump P3 off',
		S7: 'Pump P1 at 90 % speed',
		S8: 'Delivery tank 5 m higher'
	};
	/** The card for the `lineups` station with `shown` shown and the others as PumpsView gives them. */
	function family(shown = '', options: LineupViewOptions = {}) {
		const view = lineupView(shown, options);
		const { groupCurve, systemCurve, solve } = lineupAnswers(shown);
		return {
			view,
			props: {
				// The members of the case shown, without their slots (the card gives them).
				pumps: view.members.map(({ id, name, result, ratedRange, curveId, flags }) => ({
					id,
					name,
					result,
					ratedRange,
					curveId,
					flags
				})),
				slots: lineups.memberIds,
				prefs: lineupPrefs,
				project: lineups.project,
				nodes: solve.solvedState.nodeResults,
				open: true,
				curve: readyState(groupCurve),
				system: readyState(systemCurve),
				otherCases: view.others,
				othersOn: true,
				onothers: () => {},
				shownOn: lineupOn(shown),
				caseName: shown ? lineupCaseName(shown) : 'Base case',
				image: image()
			}
		};
	}
	const crossing = (k: string) => `Drawn (${k}): it crosses the group system curve at the ring`;
	/**
	 * Render the card and wait for its chart (the chart chunk's import, slow on a loaded machine),
	 * so no import of one render is still pending in the next.
	 */
	async function renderDrawn(props: ReturnType<typeof family>['props']) {
		const before = charts.length;
		const view = render(PumpGroupChart, props);
		await vi.waitFor(() => expect(charts).toHaveLength(before + 1), { timeout: 10_000 });
		return view;
	}

	it('adds the family’s one legend entry, a slate line, after the group curve’s and before the group system curve’s', async () => {
		await renderDrawn(family().props);
		const legend = within(screen.getByRole('figure')).getByRole('list', { name: 'Legend' });
		const items = within(legend).getAllByRole('listitem');
		const texts = items.map((li) => li.textContent!.trim());
		const at = texts.indexOf(OTHER_CURVES_LABEL);
		expect(texts.slice(at - 1, at + 2)).toEqual([
			'Group curve, a pump beyond its data (dashed)',
			"Other cases' group curves (slate; dashed beyond a pump's data)",
			"Group system curve (the rest of the network between the station's inlet and outlet, station's flow)"
		]);
		const line = items[at]!.querySelector('line')!;
		expect(line.getAttribute('stroke')).toBe(GROUP_OTHER);
		expect(line.hasAttribute('stroke-dasharray')).toBe(false);
		// 4d's chart (no curve state): no such entry.
		cleanup();
		await renderDrawn(family('', { without: true }).props);
		expect(screen.queryByText(OTHER_CURVES_LABEL)).toBeNull();
	});

	it('gives "Other cases’ station duties" the column "Its group curve", in capitalised words', async () => {
		await renderDrawn(family('', { unticked: ['S5', 'S6'], stale: ['S1'] }).props);
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		const table = screen.getByRole('table', { name: "Other cases' station duties" });
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => h.textContent!.replace(/\s+/g, ' ').trim())
		).toEqual([
			'Case',
			'Station flow (L/s)',
			'Rise (m)',
			'On the group system curve shown',
			'Its group curve'
		]);
		const rows = within(table)
			.getAllByRole('row')
			.slice(1)
			.map((r) =>
				[...r.querySelectorAll('th, td')].map((c) => c.textContent!.replace(/\s+/g, ' ').trim())
			);
		// The cases in the chart's order: S1 (stale), S2, S3, S4, the unticked S5 and S6 in their
		// place (no ring), then S7 and S8 within the cap.
		expect(rows.map((r) => [r[0], r[4]])).toEqual([
			[`○ 1 · ${NAMES.S1} (out of date)`, crossing('as last solved: 3 running')],
			[`○ 2 · ${NAMES.S2}`, crossing('2 running')],
			[`○ 3 · ${NAMES.S3}`, crossing('1 running')],
			[`○ 4 · ${NAMES.S4}`, crossing('3 running')],
			[NAMES.S5, undefined],
			[NAMES.S6, undefined],
			[
				`○ 5 · ${NAMES.S7}`,
				'Not drawn: the station differs inside in more than which pumps are switched on'
			],
			[`○ 6 · ${NAMES.S8}`, "The same as this case's: the station is the same inside"]
		]);
		// The cases not on the chart span the four columns after their name.
		const unticked = within(table)
			.getAllByRole('row')
			.filter((r) => r.textContent!.includes(NAMES.S5!));
		expect(unticked).toHaveLength(1);
		expect(unticked[0]!.querySelector('td')!.getAttribute('colspan')).toBe('4');
		// 4d's table, without curve states: no such column.
		cleanup();
		await renderDrawn(family('', { without: true }).props);
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		expect(
			within(screen.getByRole('table', { name: "Other cases' station duties" })).queryByRole(
				'columnheader',
				{ name: 'Its group curve' }
			)
		).toBeNull();
		expect(screen.queryByRole('table', { name: OTHER_CURVES_CAPTION })).toBeNull();
	});

	it('lists every point of each curve drawn in "Other cases’ group curves": a row group per case, a list below 640 px', async () => {
		const { view, props } = family('', { stale: ['S1'] });
		await renderDrawn(props);
		await fireEvent.click(screen.getByRole('button', { name: 'Show data table' }));
		const region = screen.getByRole('region', { name: OTHER_CURVES_CAPTION });
		expect(region).toHaveClass('max-h-72', 'overflow-auto');
		expect(region).toHaveAttribute('tabindex', '0');
		const table = within(region).getByRole('table', { name: OTHER_CURVES_CAPTION });
		expect(OTHER_CURVES_CAPTION).toBe("Other cases' group curves (station's flow at each rise)");
		expect(table).toHaveClass('max-sm:block');
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => h.textContent!.trim())
		).toEqual(['Rise (m)', 'Flow (L/s)', 'Note']);
		expect(table.querySelector('thead')).toHaveClass('max-sm:sr-only');
		const groups = within(table).getAllByRole('rowgroup').slice(1);
		const headers = groups.map((g) => within(g).getAllByRole('rowheader')[0]!);
		expect(headers.map((h) => h.getAttribute('scope'))).toEqual(Array(6).fill('rowgroup'));
		expect(headers.map((h) => h.getAttribute('colspan'))).toEqual(Array(6).fill('3'));
		expect(headers.map((h) => h.textContent!.replace(/^○\s*/, '').trim())).toEqual([
			`1 · ${NAMES.S1} (out of date): as last solved: 3 running`,
			`2 · ${NAMES.S2}: 2 running`,
			`3 · ${NAMES.S3}: 1 running`,
			`4 · ${NAMES.S4}: 3 running`,
			`5 · ${NAMES.S5}: 3 running`,
			`6 · ${NAMES.S6}: 3 running`
		]);
		// A stale case's header as Running combinations marks one.
		expect(headers[0]).toHaveClass('bg-amber-50/60');
		expect(headers[1]).toHaveClass('bg-slate-50/60');
		const f = (v: number) => formatNumber(v, 4);
		for (const [i, key] of ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'].entries()) {
			const points = [...answer(lineupAnswers(key).groupCurve).points].sort(
				(a, b) => a.head - b.head
			);
			const rows = within(groups[i]!).getAllByRole('row').slice(1);
			expect(rows).toHaveLength(42);
			expect(rows).toHaveLength(points.length);
			for (const [j, row] of rows.entries()) {
				const cells = within(row).getAllByRole('cell');
				expect(cells.map((c) => c.getAttribute('data-label'))).toEqual([
					'Rise (m)',
					'Flow (L/s)',
					'Note'
				]);
				const p = points[j]!;
				expect(cells[0]).toHaveTextContent(f(p.head));
				expect(cells[1]!.textContent).toBe(p.flow === null ? '—' : f(p.flow * 1000));
				if (p.isDuty) expect(cells[2]!.textContent).toBe("Its duty's rise (its duty check).");
				// On a phone a pair of label and value; "—" and an empty note out of sight.
				expect(row).toHaveClass('max-sm:flex', 'max-sm:flex-wrap');
				for (const cell of cells) {
					expect(cell).toHaveClass('max-sm:before:content-[attr(data-label)]');
					expect(cell.classList.contains('max-sm:sr-only')).toBe(
						cell.textContent === '—' || cell.textContent === ''
					);
				}
			}
		}
		// "1 of 4 running" has no flow at its 45 m rise: the row says why.
		const gap = within(groups[2]!)
			.getAllByRole('row')
			.find((r) => within(r).queryAllByRole('cell')[1]?.textContent === '—')!;
		expect(within(gap).getAllByRole('cell')[2]!.textContent).toMatch(
			/^Its solve did not converge\. /
		);
		expect(view.data.otherCurves).toHaveLength(6);
	}, 20_000);

	it('counts the labels its drawing left out in the notes, keeps the placement on the canvas, and the image counts its own', async () => {
		const { props } = family('S3');
		await renderDrawn(props);
		const config = charts[0]!.config as PumpChartConfig;
		// A phone-sized drawing: the curves cut at the right edge end among the rings, and some
		// labels are left out for space (the browser's measurement, pump-lineups.md §15).
		const narrow = drawnChart(config);
		narrow.draw();
		const canvas = document.querySelector('[data-pumps-together] canvas') as HTMLCanvasElement;
		const placed = JSON.parse(canvas.dataset.curveLabels!) as CurveLabelsDrawn;
		expect(placed.leftOut).toBeGreaterThan(0);
		// Every curve is labelled or counted: the six other cases' and this case's.
		expect(placed.labels.flatMap((l) => l.curves).length + placed.leftOut).toBe(7);
		const sentence = (n: number) =>
			`Labels of ${n} ${n === 1 ? 'curve' : 'curves'} are left out for space; the data table lists every curve.`;
		expect(await screen.findByText(sentence(placed.leftOut))).toBeVisible();
		// A roomy drawing: none left out, and the sentence goes.
		drawnChart(config, { plot: { left: 50, right: 900, top: 10, bottom: 500 } }).draw();
		await tick();
		expect(JSON.parse(canvas.dataset.curveLabels!).leftOut).toBe(0);
		expect(screen.queryByText(/are left out for space/)).toBeNull();
		// Crowded again on screen; the image's own drawing places its labels anew.
		narrow.draw();
		await tick();
		await fireEvent.click(
			screen.getByRole('button', { name: /^Download image of the pumps together/ })
		);
		await vi.waitFor(() => expect(images.requests).toHaveLength(1));
		const request = images.requests[0] as FigureImageRequest;
		expect(request.lines).toContain(sentence(placed.leftOut));
		const imageChart = drawnChart(request.config, {
			plot: { left: 50, right: 900, top: 10, bottom: 500 }
		});
		imageChart.draw();
		// The image writes the curves' labels in the desktop's words at 14 px (§9.3, §9.6): the base
		// (1, 4 running), "2 of 4 running" (3) and the 3-running cases merged, numbers ascending,
		// and this case's own.
		const labels = imageChart.written.filter((w) => / running( \(this case\))?$/.test(w.text));
		expect(labels.map((w) => w.text).sort()).toEqual([
			'1 running (this case)',
			'1 · 4 running',
			'2, 4, 5, 6 · 3 running',
			'3 · 2 running'
		]);
		expect([...new Set(labels.map((w) => w.font))]).toEqual(['14px system-ui, sans-serif']);
		const drawnLines = request.drawnLines!();
		expect(drawnLines.some((l) => l.includes('left out for space'))).toBe(false);
		expect(drawnLines).toEqual(request.lines.filter((l) => l !== sentence(placed.leftOut)));
		// The image's datasets carry the family with its full labels.
		const sets = request.config.data.datasets as unknown as Record<string, unknown>[];
		expect(sets.filter((d) => d.curveFamily).map((d) => d.label)).toContain(
			`1 · Base case: group curve, 4 running`
		);
	}, 20_000);
});
