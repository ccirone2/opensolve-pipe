/**
 * The Pumps together card (CLAUDE.md D21, proposal pump-groups.md §6): the disclosure, the
 * members (the cap and its hint, slots kept, the other groups found), the group curve's states
 * (progress with Cancel and the focus moves, a refusal in words), the accessible name, the data
 * table, the group table and the image. Chart.js is replaced by a recorder (jsdom has no canvas);
 * the results and responses are the shared fixture's real API answers. Slice 4b: the group
 * system curve's states, its rows in the data table and its line in the image, and "Read along
 * the curves".
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolvedState,
	TopologyIssue
} from '$lib/api/types';
import type { GroupCurveState } from '$lib/state/project.svelte';
import type { ChartImageSource, FigureImageRequest } from '$lib/utils/export/chart-image';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { ratedCurveRange } from '$lib/utils/pump-chart';
import type { GroupMemberInput } from '$lib/utils/pump-group-chart';
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
		// How the curve is computed: the response's methods section, under Details.
		expect(screen.getByText('How this curve is computed')).toBeInTheDocument();
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
		const cancel = screen.getByRole('button', { name: 'Cancel the group system curve' });
		expect(screen.queryByRole('button', { name: 'Cancel the group curve' })).toBeNull();
		cancel.focus();
		await fireEvent.click(cancel);
		expect(oncancelsystem).toHaveBeenCalledTimes(1);
		await view.rerender(values({ status: 'cancelled', by: 'user' }));
		await tick();
		await tick();
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
		// Back to the duty: the button, or Escape.
		await fireEvent.click(screen.getByRole('button', { name: 'Back to the duty' }));
		expect(slider).toHaveAttribute('aria-valuetext', `${words(duty)} (the duty's rise)`);
		expect(screen.queryByRole('button', { name: 'Back to the duty' })).toBeNull();
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
