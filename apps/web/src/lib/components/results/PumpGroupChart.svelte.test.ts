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
import { outOfSight, wordsInSight } from '$lib/testing/helpers';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import type { CurveLabelsDrawn, PumpChartConfig } from '$lib/utils/pump-chart-config';
import { ratedCurveRange } from '$lib/utils/pump-chart';
import {
	DUTY_CLAIM_RULE,
	GROUP_OTHER,
	groupMethodsHeading,
	groupNotes,
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
import { fakeResizeObserver, sizeBox } from '$lib/testing/resize';
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
/** jsdom's missing ResizeObserver, run by the tests that lay a box out (§9 S7). */
let observers: ReturnType<typeof fakeResizeObserver>;
beforeEach(() => {
	charts.length = 0;
	images.requests.length = 0;
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	observers = fakeResizeObserver();
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	observers.restore();
	// The data table shown is remembered in this browser (pumps-results-layout.md §9 S7): each
	// test starts from none remembered.
	localStorage.clear();
});

/**
 * A table's scroll box in the card, by the table's name: a region and a Tab stop only while it
 * overflows since S7 (pumps-results-layout.md §9 S7), so found by what it holds.
 */
const boxOf = (name: string | RegExp, scope: HTMLElement = document.body) =>
	within(scope).getByRole('table', { name }).parentElement!;
/** Lay a box out as a browser would, its table wider than it (452 px), and measure it. */
function overflowSideways(box: HTMLElement) {
	sizeBox(box, { clientWidth: 452, scrollWidth: 900, clientHeight: 300, scrollHeight: 300 });
	observers.resize(box);
}
/** A curve table's disclosure (CurveTable), by its table's name. */
const disclosureOf = (name: string, scope: HTMLElement = document.body) =>
	within(scope).getByRole('table', { name }).closest('details')!;
/**
 * Open a curve table's disclosure as a user would, closed until then: a curve table is read
 * after its disclosure is opened (§9 S7, §10 S7). Its table.
 */
async function openTable(name: string, scope: HTMLElement = document.body) {
	const details = disclosureOf(name, scope);
	expect(details.open, `"${name}" closed until opened`).toBe(false);
	await fireEvent.click(details.querySelector(':scope > summary')!);
	expect(details.open).toBe(true);
	return within(scope).getByRole('table', { name });
}

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

/** The image's footer lines of the card on screen (groupNoteLines): Download image pressed. */
async function footerLines(): Promise<readonly string[]> {
	const button = () =>
		screen.getByRole('button', { name: /^Download image of the pumps together/ });
	await vi.waitFor(() => expect(button()).not.toHaveAttribute('aria-disabled', 'true'), {
		timeout: 10_000
	});
	const before = images.requests.length;
	await fireEvent.click(button());
	await vi.waitFor(() => expect(images.requests).toHaveLength(before + 1));
	return (images.requests.at(-1) as FigureImageRequest).lines;
}

/** The ring list's lead, which names it (pumps-results-layout.md §5.3; §6.2: its words kept). */
const RING_LEAD = 'Other cases on the chart (slate rings, numbered):';

/**
 * The words-on-screen guard (pumps-results-layout.md §10, §6.4 item 3): every line of the image's
 * footer, groupNoteLines with the refusals, is on the card word for word, in sight at every width
 * (wordsInSight: not visually hidden or hidden by any class variant, attribute or style, and not
 * in a closed disclosure), or else inside a named disclosure, and then only in "How to read this
 * chart" or "How to read the rings". The ring list's sentence is on screen as its lead and its
 * lines, one per ring, which otherNoteLines joins back into it. Returns the lines found only
 * inside a disclosure.
 */
function footerOnScreen(lines: readonly string[]): string[] {
	const card = screen.getByRole('region', { name: /^Pumps together/ });
	const squash = (t: string) => t.replace(/\s+/g, ' ').trim();
	const inSight = (line: string) =>
		[...card.querySelectorAll('p, span, li, summary')].some(
			(el) => !outOfSight(el) && squash(wordsInSight(el)).includes(line)
		);
	/** The reference that may hold a footer line (§5.3): what it holds, closed. */
	const reference = [...card.querySelectorAll('[data-group-reading], [data-group-rings-how]')];
	const allowed = reference.flatMap((d) => [...d.querySelectorAll('p')].map((p) => p.textContent));
	const inDisclosure: string[] = [];
	expect(lines.length).toBeGreaterThan(0);
	for (const line of lines) {
		if (line.startsWith(`${RING_LEAD} `)) {
			const list = within(card).getByRole('list', { name: RING_LEAD });
			const lead = document.getElementById(list.getAttribute('aria-labelledby')!)!;
			const items = within(list).getAllByRole('listitem');
			expect(outOfSight(lead), line).toBe(false);
			for (const li of items) expect(outOfSight(li), li.textContent!).toBe(false);
			const text = (li: Element) => {
				const copy = li.cloneNode(true) as Element;
				for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
				return squash(copy.textContent!);
			};
			expect(`${squash(wordsInSight(lead))} ${items.map(text).join('; ')}.`).toBe(line);
			continue;
		}
		if (inSight(line)) continue;
		// Not in sight: inside a closed disclosure that names what it holds, and in sight once open.
		const holder = reference.find((d) => squash(d.textContent!).includes(line)) as
			HTMLDetailsElement | undefined;
		expect(holder, `on screen, or in a named disclosure: ${line}`).toBeDefined();
		expect(holder!.open).toBe(false);
		expect(squash(holder!.querySelector(':scope > summary')!.textContent!)).toMatch(
			/^How to read (this chart|the rings): /
		);
		expect(allowed, line).toContain(line);
		holder!.open = true;
		expect(inSight(line), line).toBe(true);
		holder!.open = false;
		inDisclosure.push(line);
	}
	return inDisclosure;
}

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

	it('says, closed, what opening it shows: a second line under its heading that describes its toggle (pumps-results-layout.md §5.3)', async () => {
		const c = named('parallel-ideal');
		const ABOUT =
			"The station's duty, the group curve, each pump's share and cases with fewer pumps running";
		const view = render(PumpGroupChart, props(c, { open: false }));
		const toggle = screen.getByRole('button', { name: /^Pumps together/ });
		// Its name still starts "Pumps together" and names the pumps (the section nav's target).
		expect(toggle).toHaveAccessibleName('Pumps together (Pump PA, Pump PB)');
		expect(toggle).toHaveAccessibleDescription(ABOUT);
		const line = screen.getByText(ABOUT);
		// A line of its own under the heading, on screen: not inside the h3 or its button.
		expect(line.tagName).toBe('P');
		expect(line.closest('h3')).toBeNull();
		expect(line).toBeVisible();
		expect(outOfSight(line)).toBe(false);
		expect(
			screen.getByRole('heading', { level: 3 }).compareDocumentPosition(line) &
				Node.DOCUMENT_POSITION_FOLLOWING
		).toBeTruthy();
		// The chevron turns as the card opens, and never with reduced motion (§5.3 markup rules).
		const chevron = toggle.querySelector('svg')!;
		expect(chevron).toHaveAttribute('aria-hidden', 'true');
		expect(chevron).toHaveClass('transition-transform', 'motion-reduce:transition-none');
		expect(chevron).not.toHaveClass('rotate-90');
		// Opened: the line goes, and so does the description.
		await fireEvent.click(toggle);
		expect(screen.queryByText(ABOUT)).toBeNull();
		expect(toggle).not.toHaveAttribute('aria-describedby');
		expect(toggle).toHaveAccessibleDescription('');
		expect(chevron).toHaveClass('rotate-90');
		await drawn();
		// With scenarios (the box "Also show …" given only then), Running combinations too.
		view.unmount();
		render(PumpGroupChart, props(c, { open: false, onothers: () => {} }));
		expect(screen.getByRole('button', { name: /^Pumps together/ })).toHaveAccessibleDescription(
			`${ABOUT}; Running combinations`
		);
	});

	it('draws its actions under its legend and opens its data after its reference (pumps-results-layout.md §5.1, §9 S2, S3)', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { system: systemReady(c), image: image() }));
		await drawn();
		const figure = screen.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' });
		const legend = within(figure).getByRole('list', { name: 'Legend' });
		const show = within(figure).getByRole('button', { name: 'Show data table of the group chart' });
		const download = within(figure).getByRole('button', {
			name: /^Download image of the pumps together/
		});
		// One row (F3: it sat at the card's foot, after Running combinations); Download image and
		// its reason one item of it (§15 item 27). S3 (§5.3, §6.1): the reading controls and the
		// strip come first, so the readout sits under its canvas (F12); the actions right after
		// the strip, as on the pump chart, and the legend right after them (§5.7 row 3's budget).
		const strip = figure.querySelector('[data-group-strip]')!;
		expect(strip.nextElementSibling).toBe(show.parentElement);
		expect(show.parentElement!.nextElementSibling).toBe(legend.parentElement);
		expect(download.parentElement!.parentElement).toBe(show.parentElement);
		const follows = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		const slider = within(figure).getByRole('slider', { name: 'Read along the curves' });
		expect(follows(within(figure).getByRole('img'), slider)).toBe(true);
		expect(follows(slider, strip)).toBe(true);
		// No data region until asked for; then the one its toggle controls, in the figure, right
		// after the reference (how to read the chart, how each curve is computed), its last part:
		// after every note.
		expect(show).toHaveAttribute('aria-expanded', 'false');
		const controls = show.getAttribute('aria-controls')!;
		expect(document.getElementById(controls)).toBeNull();
		await fireEvent.click(show);
		expect(show).toHaveAttribute('aria-expanded', 'true');
		const data = document.getElementById(controls)!;
		expect(figure.lastElementChild).toBe(data);
		const reference = [...figure.querySelectorAll(':scope > details')];
		expect(reference.map((d) => d.querySelector('summary')!.textContent!.trim())).toEqual([
			"How to read this chart: the axes, the group system curve, each pump's own system curve",
			'How the group curve is computed',
			'How the group system curve is computed'
		]);
		expect(data.previousElementSibling).toBe(reference.at(-1));
		// Every note before the data region, the reference's included.
		const notes = [...figure.querySelectorAll('p')].filter((p) => !data.contains(p));
		expect(notes.length).toBeGreaterThan(5);
		for (const note of notes) expect(follows(note, data)).toBe(true);
		expect(
			within(data).getByRole('table', { name: "Each pump's point (flow through it)" })
		).toBeVisible();
		// A curve table in its disclosure, closed while every point has a rise (§9 S7).
		expect(
			await openTable(
				"Group system curve (rise the rest of the network needs at each station's flow)",
				data
			)
		).toBeVisible();
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
		// Busy is the canvas wrapper's, the part that is redrawn (§5.3 markup rules, §7).
		const canvas = within(figure).getByRole('img');
		expect(canvas).toHaveAttribute('aria-busy', 'true');
		// The group curve's line heads Station (§5.3): always there, polite, never role=status.
		const line = document.querySelector('[data-group-curve-state]')!;
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(await screen.findByText('Computing the group curve for this solve…')).toBe(line);
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
		expect(canvas).toHaveAttribute('aria-busy', 'false');
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

	it('says once that showing a group found replaces the pumps ticked, each button described by it and wrapping', async () => {
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
		// Two groups found: behind "Other groups found: 2" (pumps-results-layout.md §5.3), closed.
		const other = screen.getByText('Other groups found: 2').closest('details')!;
		expect(other.open).toBe(false);
		await fireEvent.click(other.querySelector('summary')!);
		expect(other.open).toBe(true);
		const buttons = screen.getAllByRole('button', { name: /^Also found: / });
		expect(buttons.map((b) => b.textContent)).toEqual([
			'Also found: Pump P1, Pump P2 and Pump P3',
			'Also found: Pump P2 and Pump P3'
		]);
		for (const button of buttons) {
			expect(button).toHaveAccessibleDescription(sentence);
			expect(button).toHaveClass('btn', 'whitespace-normal', 'text-left');
			expect(button).toBeVisible();
			expect(other.contains(button)).toBe(true);
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
		// Its box a named region and a Tab stop while it overflows (§9 S7): 13 columns in 452 px.
		const box = boxOf('The pumps in the group');
		overflowSideways(box);
		const region = screen.getByRole('region', { name: 'The pumps in the group' });
		expect(region).toBe(box);
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
			'Inside curve data'
		]);
		expect(within(table).getByRole('rowheader', { name: 'Pump PA' })).toBeVisible();
		// The footer: the station as a whole, both ports named.
		expect(screen.getByText('Lost in the piping between the pumps:')).toBeVisible();
		expect(screen.getByText('Rise from Pump PA (suction) to Pump PB (discharge):')).toBeVisible();
	});

	it('shows the data table on request: the points, the duty and every sample', async () => {
		const c = named('dead-headed');
		render(PumpGroupChart, props(c));
		const toggle = screen.getByRole('button', { name: 'Show data table of the group chart' });
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		const points = screen.getByRole('table', { name: "Each pump's point (flow through it)" });
		expect(within(points).getAllByRole('row')).toHaveLength(3);
		expect(within(points).getByRole('rowheader', { name: /Pump PB/ })).toHaveTextContent('◇');
		const samples = await openTable("Group curve (station's flow at each rise)");
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
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		const line = () => screen.getByText(/Group duty \(station's flow\):/);
		expect(line()).toHaveTextContent(
			/Duty check: not known, its point at the duty’s rise was not computed \(the time budget ran out\)\.\s*Details/
		);
		expect(screen.queryByText(/the group curve does not pass through it/)).toBeNull();
		// The duty's row: its mark and the point's reason, two sentences, in a table open by
		// default, since its point has no flow (§9 S7; S7 review STRUCT-2, W1, REG-1).
		expect(disclosureOf("Group curve (station's flow at each rise)").open).toBe(true);
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
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
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
		expect(screen.getByRole('table', { name: 'The pumps in the group' })).toBeVisible();
		// Its curve table open by default: the chart cannot be drawn (§9 S7).
		expect(disclosureOf("Group curve (station's flow at each rise)").open).toBe(true);
		expect(
			screen.getByRole('table', { name: "Group curve (station's flow at each rise)" })
		).toBeVisible();
	});
});

describe('the members, the station and the group chart’s reading (pumps-results-layout.md §5.3, §9 S3)', () => {
	const follows = (a: Node, b: Node) =>
		!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
	const squash = (text: string | null) => (text ?? '').replace(/\s+/g, ' ').trim();

	it('the members: a grid whose names never move on tick, the finder’s hint its description, a capped box greyed', async () => {
		const c = named('parallel-ideal');
		const [pa] = pumpsOf(c);
		const pumps = Array.from({ length: 7 }, (_, i) => ({
			...pa!,
			id: `P${i + 1}`,
			name: `Pump P${i + 1}`
		}));
		const view = render(
			PumpGroupChart,
			props(c, { pumps, slots: ['P1', 'P2', 'P3', 'P4', 'P5', 'P6'], curve: undefined })
		);
		const members = screen.getByRole('group', { name: 'Pumps in the group' });
		// Its legend the fieldset's first child, so the group keeps its name (§5.3 markup rules).
		expect(members.firstElementChild!.tagName).toBe('LEGEND');
		expect(members).toHaveAccessibleDescription(
			'The calculation server finds the part of the network that holds them, between two places (its inlet and outlet), and whether they are in parallel or in series.'
		);
		// The hint stays visible text (§6.2, §6.4 item 8).
		const finder = screen.getByText(/^The calculation server finds/);
		expect(finder).toBeVisible();
		expect(outOfSight(finder)).toBe(false);
		// An auto-fill grid of 13 rem at least: two columns in a 480 px pane, one on a phone.
		const grid = members.querySelector('legend + div')!;
		expect(grid).toHaveClass('grid', 'grid-cols-[repeat(auto-fill,minmax(13rem,1fr))]');
		// Every label: the box, the slot symbol's column (kept while unticked), then the name.
		const label = (n: number) =>
			screen.getByRole('checkbox', { name: `Pump P${n}` }).closest('label')!;
		for (const n of [1, 7]) {
			const [box, symbol, name] = [...label(n).children];
			expect(box!.tagName).toBe('INPUT');
			expect(symbol).toHaveAttribute('aria-hidden', 'true');
			expect(symbol).toHaveClass('w-4', 'shrink-0');
			expect(name).toHaveTextContent(`Pump P${n}`);
			expect(name).toHaveClass('min-w-0', 'wrap-break-word');
			// Wrapped, never cut with an ellipsis: its end tells two pumps apart (§15 item 17; S3
			// review MUT-08).
			expect(name).not.toHaveClass('truncate');
		}
		expect(label(1).children[1]).toHaveTextContent('▲');
		expect(label(7).children[1]!.textContent).toBe('');
		// Capped (ui-guide): the box greyed, the row not-allowed, the name kept readable.
		const seventh = screen.getByRole('checkbox', { name: 'Pump P7' });
		expect(seventh).toHaveClass('opacity-45');
		expect(label(7)).toHaveClass('cursor-not-allowed', 'text-slate-600');
		expect(screen.getByRole('checkbox', { name: 'Pump P1' })).not.toHaveClass('opacity-45');
		expect(label(1)).not.toHaveClass('cursor-not-allowed');
		// Unticked, a name keeps its place: the symbol's column is the same element, emptied.
		const name = label(2).children[2]!;
		await view.rerender(
			props(c, { pumps, slots: ['P1', null, 'P3', 'P4', 'P5', 'P6'], curve: undefined })
		);
		expect(label(2).children[2]).toBe(name);
		expect(label(2).children[1]!.textContent).toBe('');
		expect(seventh).not.toHaveClass('opacity-45');
	});

	it('says whom the members were suggested for while they are that suggestion', async () => {
		const c = named('parallel-ideal');
		const LINE =
			'Suggested for Pump PA, the pump on the pump chart above; tick pumps to choose your own.';
		const view = render(PumpGroupChart, props(c, { suggestedFor: 'Pump PA' }));
		const line = screen.getByText(LINE);
		expect(line).toBeVisible();
		expect(outOfSight(line)).toBe(false);
		// After the members, before anything else of the card's.
		const members = screen.getByRole('group', { name: 'Pumps in the group' });
		expect(members.nextElementSibling).toBe(line);
		// The user's own choice (or no group found holds the pump shown): no line.
		await view.rerender(props(c, { suggestedFor: null }));
		expect(screen.queryByText(/^Suggested for/)).toBeNull();
	});

	it('offers two groups found or more behind "Other groups found: {n}", one as its button; the focus stays in the disclosure', async () => {
		const c = named('ladder');
		const suggestions = [
			{ pumpIds: ['P1', 'P2', 'P3'], kind: 'parallel' },
			{ pumpIds: ['P2', 'P3'], kind: 'parallel' },
			{ pumpIds: ['P1', 'P2'], kind: 'parallel' }
		];
		const values = (slots: (string | null)[]) => ({
			slots,
			curve: undefined,
			suggestions,
			onslots: (next: string[]) => void view.rerender(props(c, values(next)))
		});
		const view = render(PumpGroupChart, props(c, values(['P2', 'P3'])));
		const sentence = 'Showing a group found replaces the pumps ticked.';
		// Two offered (the group shown is not): a native disclosure, closed, saying how many.
		const summary = screen.getByText('Other groups found: 2');
		expect(summary.tagName).toBe('SUMMARY');
		expect(summary).toHaveClass('more-summary');
		const chevron = summary.querySelector('svg')!;
		expect(chevron).toHaveAttribute('aria-hidden', 'true');
		expect(chevron).toHaveClass('motion-reduce:transition-none');
		const other = summary.closest('details')!;
		expect(other.open).toBe(false);
		for (const button of screen.getAllByRole('button', { name: /^Also found: / })) {
			expect(other.contains(button)).toBe(true);
			expect(button).not.toBeVisible();
		}
		await fireEvent.click(summary);
		// S0's one sentence first, saying what a button does before it is met; each described by it.
		const said = screen.getByText(sentence);
		const buttons = screen.getAllByRole('button', { name: /^Also found: / });
		expect(buttons.map((b) => b.textContent)).toEqual([
			'Also found: Pump P1, Pump P2 and Pump P3',
			'Also found: Pump P1 and Pump P2'
		]);
		for (const button of buttons) {
			expect(button).toBeVisible();
			expect(button).toHaveAccessibleDescription(sentence);
			expect(follows(said, button)).toBe(true);
		}
		// Showing one: its button goes and the group shown before is offered; still two, so the
		// disclosure stays as the user left it, open, and the focus moves to its first button.
		buttons[1]!.focus();
		await fireEvent.click(buttons[1]!);
		await tick();
		await tick();
		expect(other.isConnected).toBe(true);
		expect(other.open).toBe(true);
		expect(document.activeElement).toBe(
			screen.getByRole('button', { name: 'Also found: Pump P1, Pump P2 and Pump P3' })
		);
		// One offered: its button, out of any disclosure, after the sentence.
		view.unmount();
		render(
			PumpGroupChart,
			props(c, { ...values(['P2', 'P3']), suggestions: suggestions.slice(0, 2) })
		);
		expect(screen.queryByText(/^Other groups found/)).toBeNull();
		const only = screen.getByRole('button', { name: 'Also found: Pump P1, Pump P2 and Pump P3' });
		expect(only.closest('details')).toBeNull();
		expect(only).toBeVisible();
		expect(follows(screen.getByText(sentence), only)).toBe(true);
	});

	it('Station: the group curve’s line at its head, always there and empty until it speaks; the answer before the table', async () => {
		const c = named('series');
		const view = render(
			PumpGroupChart,
			props(c, { curve: { status: 'loading' }, oncancel: () => {} })
		);
		const station = screen.getByRole('heading', { name: 'Station', level: 4 }).parentElement!;
		const line = station.querySelector('[data-group-curve-state]')!;
		// The row's first child, right under the heading; polite, atomic, never role=status, holding
		// no button, with no busy ancestor (§5.3 markup rules, §7 Live regions).
		const row = line.parentElement!;
		expect(row.previousElementSibling).toBe(
			screen.getByRole('heading', { name: 'Station', level: 4 })
		);
		expect(row.firstElementChild).toBe(line);
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(line).toHaveAttribute('aria-atomic', 'true');
		expect(line).not.toHaveAttribute('role');
		expect(line.querySelector('button')).toBeNull();
		expect(line.closest('[aria-busy="true"]')).toBeNull();
		// Drawn empty first, then it speaks (two frames: a line inserted speaking is not announced).
		expect(line.textContent).toBe('');
		expect(await screen.findByText('Computing the group curve for this solve…')).toBe(line);
		expect(line.querySelector('svg')).toHaveClass('motion-safe:animate-spin');
		// Its Cancel after it, outside it, described by it; then the shares' pending sentence.
		const cancel = within(row).getByRole('button', { name: 'Cancel the group curve' });
		expect(cancel).toHaveAccessibleDescription('Computing the group curve for this solve…');
		const pending = screen.getByText(
			'The share of each pump and its loss on the way come with the group curve.'
		);
		expect(row.nextElementSibling).toBe(pending);
		// Answered: the line is there, empty and out of sight; the station's answer, then the table.
		await view.rerender(props(c));
		expect(station.querySelector('[data-group-curve-state]')).toBe(line);
		expect(line.textContent).toBe('');
		expect(row).toHaveClass('sr-only');
		const answer = within(station).getByLabelText('The station');
		expect(answer.tagName).toBe('DL');
		expect(answer).toHaveClass('text-sm');
		// In sight at every width: the answer first, on a phone too (§5.3 Station; S3 review MUT-09).
		expect(outOfSight(answer)).toBe(false);
		for (const term of answer.children) expect(outOfSight(term)).toBe(false);
		for (const dd of answer.querySelectorAll('dd')) expect(dd).toHaveClass('font-semibold');
		const terms = [...answer.children].map((e) => [e.tagName, squash(e.textContent)]);
		expect(terms.map(([tag]) => tag)).toEqual(['DT', 'DD', 'DT', 'DD', 'DT', 'DD']);
		expect(terms[0]![1]).toMatch(/^Station flow, into the station at .*:$/);
		expect(terms[1]![1]).toMatch(/^[\d.]+ gpm$/);
		expect(terms[2]![1]).toBe('Rise from Pump PA (suction) to Pump PB (discharge):');
		expect(terms[3]![1]).toMatch(/^[\d.]+ ft$/);
		expect(terms[4]![1]).toBe('Lost in the piping between the pumps:');
		expect(terms[5]![1]).toMatch(/^[\d.]+ ft$/);
		const box = boxOf('The pumps in the group', station);
		expect(follows(answer, box)).toBe(true);
		// The card's one dl.
		expect(
			screen.getByRole('region', { name: /^Pumps together/ }).querySelectorAll('dl')
		).toHaveLength(1);
		// Failed: its mark at its first line and its words; Try again after it.
		await view.rerender(
			props(c, { curve: { status: 'error', message: 'The server is busy.' }, onretry: () => {} })
		);
		expect(line).toHaveTextContent('The group curve could not be computed: The server is busy.');
		expect(line.querySelector('svg')).toHaveClass('mt-px', 'text-red-700');
		expect(within(row).getByRole('button', { name: 'Try again' })).toHaveAccessibleDescription(
			'The group curve could not be computed: The server is busy.'
		);
		// Said once, at Station's head: not in the group chart's strip any more (§5.3, §6.1; S3
		// review MUT-06).
		expect(
			screen.getAllByText('The group curve could not be computed: The server is busy.')
		).toEqual([line]);
		expect(screen.getByRole('figure').querySelector('[data-group-strip]')).not.toHaveTextContent(
			/could not be computed/
		);
	});

	it('Station: the refusal, its reasons each with "Details of {reason}", before the table', () => {
		const c = named('refused');
		const body = c.groupCurve.body as { message: string; issues: TopologyIssue[] };
		render(
			PumpGroupChart,
			props(c, {
				curve: { status: 'refused', message: body.message, issues: body.issues },
				oninspect: () => {}
			})
		);
		const station = screen.getByRole('heading', { name: 'Station', level: 4 }).parentElement!;
		const refusal = station.querySelector<HTMLElement>('[data-group-refusal]')!;
		expect(refusal).toHaveTextContent(/^These pumps do not form a station/);
		expect(follows(refusal, boxOf('The pumps in the group', station))).toBe(true);
		// Not in the figure any more.
		expect(screen.getByRole('figure').querySelector('[data-group-refusal]')).toBeNull();
		const item = within(refusal).getByRole('listitem');
		const reason =
			'The pumps meet the fixed heads of Reservoir R2 and Tank R4, one place more than a station has';
		const summary = item.querySelector('summary')!;
		expect(squash(summary.textContent)).toMatch(new RegExp(`^Details of ${reason}`));
		expect(summary.querySelector('.sr-only')!.textContent).toMatch(/^of The pumps meet/);
	});

	it('Station: a flag line under each flagged pump’s row, read once and named by its pump; no Flags column; a list below 640 px', () => {
		const c = named('dead-headed');
		const flagText = (flag: Flag) => `${flag.code}: ${flag.message}`;
		render(PumpGroupChart, props(c, { oninspect: () => {}, flagText }));
		const box = boxOf('The pumps in the group');
		// A size container (§5.5), so a flag line is the box's visible width.
		expect(box).toHaveClass('@container', 'scroll-shadow-x', 'overflow-auto', 'relative');
		const table = within(box).getByRole('table');
		expect(within(table).queryByRole('columnheader', { name: 'Flags' })).toBeNull();
		const rows = within(table).getAllByRole('row');
		for (const pump of pumpsOf(c)) {
			const row = rows.find((r) => within(r).queryByRole('rowheader', { name: pump.name }))!;
			const next = row.nextElementSibling;
			if (!pump.flags.length) {
				expect(next?.querySelector('[data-row-notes]') ?? null).toBeNull();
				continue;
			}
			const note = next!.querySelector<HTMLElement>(`[data-row-notes="${pump.id}"]`)!;
			expect(note).toHaveAttribute('data-label', 'Flags');
			expect(note).toHaveClass('sticky', 'left-0', 'w-[100cqw]');
			// Its one cell spans the row, so table navigation reads the line in one place.
			const cell = note.closest('td')!;
			expect(cell).toHaveAttribute(
				'colspan',
				String(within(table).getAllByRole('columnheader').length)
			);
			// Named by its pump first (visually hidden), then each flag: its pill, its text.
			expect(squash(note.textContent).startsWith(`${pump.name}, flags:`)).toBe(true);
			expect(note.querySelector('.sr-only')!.textContent).toBe(`${pump.name}, flags:`);
			// A list, an item per flag (S6a, one pattern with Running combinations, §15 item 149).
			const lines = [...note.querySelectorAll('li')];
			expect(lines).toHaveLength(pump.flags.length);
			for (const [i, flag] of pump.flags.entries()) {
				const pill = lines[i]!.querySelector('span')!;
				const word = { invalid: 'Invalid', warning: 'Warning', info: 'Info' }[flag.severity];
				expect(pill.textContent).toBe(word);
				expect(pill).not.toHaveAttribute('title');
				expect(pill.querySelector('.sr-only')).toBeNull();
				expect(pill).toHaveClass(
					...{
						invalid: ['border-red-300', 'bg-red-50', 'text-red-900'],
						warning: ['border-amber-300', 'bg-amber-50', 'text-amber-900'],
						info: ['border-slate-300', 'bg-slate-50', 'text-slate-700']
					}[flag.severity]
				);
				expect(pill.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
				// The flag's text visible after its pill, at 12 px, once.
				expect(squash(lines[i]!.textContent)).toBe(`${word} ${flagText(flag)}`);
				expect(lines[i]).toHaveClass('text-xs');
				expect(outOfSight(lines[i]!)).toBe(false);
				// The sentence its own element, in sight (S5 review MUT-01).
				const sentence = lines[i]!.querySelector('[data-flag-text]')!;
				expect(sentence).toHaveTextContent(flagText(flag));
				expect(outOfSight(sentence)).toBe(false);
				expect(note.textContent!.split(flagText(flag))).toHaveLength(2);
			}
		}
		// PB's invalid flag is there: the fixture has a flag of each kind this test reads.
		expect(
			pumpsOf(c)
				.flatMap((p) => p.flags.map((f) => f.severity))
				.sort()
		).toEqual(['invalid', 'warning', 'warning']);
		// No flag left in a tooltip anywhere in the table.
		expect(table.querySelector('[title]')).toBeNull();
		// Below 640 px a list (Running combinations' classes), the roles explicit.
		expect(table).toHaveAttribute('role', 'table');
		expect(table).toHaveClass('max-sm:block');
		expect(table.querySelector('thead')).toHaveClass('max-sm:sr-only');
		const pa = rows.find((r) => within(r).queryByRole('rowheader', { name: 'Pump PA' }))!;
		expect(pa).toHaveClass('max-sm:flex', 'max-sm:flex-wrap');
		const header = within(pa).getByRole('rowheader');
		// The sticky name wraps at 12 rem (§5.3): its one line up to 12 rem, the column that wide.
		expect(header).toHaveClass('sticky');
		expect(within(header).getByRole('button', { name: 'Pump PA' })).toHaveClass(
			'w-max',
			'max-w-48',
			'wrap-break-word'
		);
		// In the phone's list the line's width, wrapping anywhere: a name with no space (§5.5,
		// ui-guide; S3 review LAYOUT-2).
		expect(within(header).getByRole('button', { name: 'Pump PA' })).toHaveClass(
			'max-sm:w-auto',
			'max-sm:max-w-none',
			'max-sm:wrap-anywhere'
		);
		for (const td of within(pa).getAllByRole('cell')) {
			expect(td.dataset.label).toBeTruthy();
			expect(td).toHaveClass('max-sm:before:content-[attr(data-label)]');
			expect(td.classList.contains('max-sm:sr-only')).toBe(td.textContent === '—');
		}
		// A table without a flag has no flag line.
		cleanup();
		render(PumpGroupChart, props(named('one-off')));
		expect(boxOf('The pumps in the group').querySelector('[data-row-notes]')).toBeNull();
	});

	it('the group chart: its canvas busy while a curve loads, the strip’s live line always there, coverage plain after it', async () => {
		const c = named('fcv-outside');
		const view = render(PumpGroupChart, props(c, { system: { status: 'loading' } }));
		const figure = screen.getByRole('figure');
		// aria-busy on the canvas wrapper, never on the figure (§5.3, §7).
		expect(figure).not.toHaveAttribute('aria-busy');
		expect(within(figure).getByRole('img')).toHaveAttribute('aria-busy', 'true');
		const strip = figure.querySelector('[data-group-strip]')!;
		const line = strip.querySelector('[data-group-system-state]')!;
		expect(line).toHaveAttribute('aria-live', 'polite');
		// Atomic, so it is never read in fragments (§5.3 markup rules, §7; S3 review MUT-02).
		expect(line).toHaveAttribute('aria-atomic', 'true');
		expect(line).not.toHaveAttribute('role');
		expect(line.closest('[aria-busy="true"]')).toBeNull();
		expect(line.querySelector('button')).toBeNull();
		expect(line.parentElement!.firstElementChild).toBe(line);
		expect(line.textContent).toBe('');
		expect(await screen.findByText('Computing the group system curve for this solve…')).toBe(line);
		expect(strip).not.toHaveClass('sr-only');
		// Answered with points without a rise: the line empty, the coverage a plain p after it.
		await view.rerender(props(c, { system: systemReady(c) }));
		expect(within(figure).getByRole('img')).toHaveAttribute('aria-busy', 'false');
		expect(strip.querySelector('[data-group-system-state]')).toBe(line);
		expect(line.textContent).toBe('');
		const points = (c.systemCurve!.body as PumpGroupCurveResponse).systemPoints;
		const coverage = screen.getByText(
			`${points.filter((p) => p.head === null).length} of ${points.length} group-system-curve points have no rise: the line has gaps there, and the data table says why for each.`
		);
		expect(coverage.tagName).toBe('P');
		expect(coverage.parentElement).toBe(strip);
		expect(follows(line, coverage)).toBe(true);
		expect(coverage.querySelector('svg')).toBeNull();
		expect(outOfSight(coverage)).toBe(false);
		// Nothing to say: the strip takes no room, its line still there.
		cleanup();
		render(
			PumpGroupChart,
			props(named('parallel-ideal'), { system: systemReady(named('parallel-ideal')) })
		);
		const idle = screen.getByRole('figure').querySelector('[data-group-strip]')!;
		expect(idle).toHaveClass('sr-only');
		expect(idle.querySelector('[data-group-system-state]')!.textContent).toBe('');
		// One member: "Tick two pumps or more …" is the strip's.
		cleanup();
		render(PumpGroupChart, props(named('parallel-ideal'), { slots: ['PA'], curve: undefined }));
		const one = screen.getByText('Tick two pumps or more to compute their group curve.');
		expect(one.parentElement).toHaveAttribute('data-group-strip');
	});

	it('the readout: each pump and value a pair from the sample’s parts, its text the slider’s value text; its hint after it', async () => {
		const c = named('parallel-crane');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		const slider = screen.getByRole('slider', { name: 'Read along the curves' });
		const readout = document.querySelector('[data-group-readout]')!;
		// A container: two-up from 26 rem, one pair per line below (§5.5); 14 px tabular figures.
		expect(readout.parentElement).toHaveClass('@container');
		expect(readout).toHaveClass(
			'grid',
			'grid-cols-1',
			'@min-[26rem]:grid-cols-2',
			'text-sm',
			'tabular-nums'
		);
		// Its words, word for word the slider's value text, at the duty and elsewhere.
		const text = () => squash(readout.textContent);
		expect(text()).toBe(slider.getAttribute('aria-valuetext'));
		expect(text()).toMatch(/ \(the duty's rise\)$/);
		await fireEvent.input(slider, { target: { value: '0' } });
		expect(text()).toBe(slider.getAttribute('aria-valuetext'));
		// The lead, then one pair per member and the station's ("group"), each a grid item; the
		// separators visually hidden.
		const [lead, ...pairs] = [...readout.children];
		expect(lead).toHaveClass('col-span-full', 'font-medium');
		expect(lead!.textContent).toMatch(/^At a rise of [\d.]+ m:$/);
		expect(pairs.map((p) => p.querySelector('.text-slate-600')!.textContent)).toEqual([
			'Pump PA',
			'Pump PB',
			'group'
		]);
		for (const [i, pair] of pairs.entries()) {
			const hidden = pair.querySelector('.sr-only');
			expect(hidden?.textContent ?? null).toBe(i ? ', ' : null);
			expect(pair.querySelector('.font-medium')).toHaveClass('whitespace-nowrap');
		}
		// The hint after the readout, visible, and the slider's description (§5.3 Reading).
		const hint = screen.getByText(/^Steps over the group curve's samples/);
		expect(readout.nextElementSibling).toBe(hint);
		expect(outOfSight(hint)).toBe(false);
		expect(slider).toHaveAccessibleDescription(hint.textContent!.replace(/\s+/g, ' ').trim());
	});

	it('the readout at a duty’s sample with no flow: its words still the slider’s value text, " (the duty’s rise)" with them, at every sample (§5.3 Reading; S3 review STRUCT-1)', async () => {
		const c = named('parallel-crane');
		// Made-up: the duty's point not computed (the time budget ran out), as the API reports it;
		// the slider starts at it.
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
				reason: 'not_computed',
				message: "not computed: the request's 45 s budget ran out",
				members: []
			}
		);
		render(PumpGroupChart, props(c, { curve: { status: 'ready', response } }));
		await drawn();
		const slider = screen.getByRole('slider', { name: 'Read along the curves' });
		const readout = document.querySelector('[data-group-readout]')!;
		expect(slider.getAttribute('aria-valuetext')).toMatch(
			/^At a rise of [\d.]+ m: no flow solved here; the data table says why\. \(the duty's rise\)$/
		);
		for (let i = 0; i <= Number(slider.getAttribute('max')); i++) {
			await fireEvent.input(slider, { target: { value: String(i) } });
			expect(squash(readout.textContent), `sample ${i}`).toBe(
				slider.getAttribute('aria-valuetext')
			);
		}
	});

	it('the legend after the reading, the strip and the actions: its line entries one per row, the members’ markers two-up from 18 rem, every marker from 26 rem', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		const legend = screen.getByRole('list', { name: 'Legend' });
		expect(legend.parentElement).toHaveClass('@container');
		expect(legend).toHaveClass('grid', 'grid-cols-1', '@min-[18rem]:grid-cols-2');
		const items = within(legend).getAllByRole('listitem');
		const kinds = items.map((li) =>
			li.querySelector('svg') ? 'line' : /^\s*[▲■]/.test(li.textContent!) ? 'member' : 'marker'
		);
		expect(kinds).toEqual(['line', 'line', 'line', 'line', 'line', 'member', 'member', 'marker']);
		for (const [i, li] of items.entries()) {
			if (kinds[i] === 'line') expect(li).toHaveClass('col-span-full');
			if (kinds[i] === 'member') {
				expect(li).not.toHaveClass('col-span-full');
				expect(li.className).not.toContain('@min-[18rem]:col-span-full');
			}
			if (kinds[i] === 'marker') {
				expect(li).toHaveClass('@min-[18rem]:col-span-full', '@min-[26rem]:col-span-1');
			}
			// Its words in a span of their own that wraps in the cell, a name with no space too,
			// never over the next entry (§5.3; S3 review LAYOUT-1).
			const words = li.lastElementChild!;
			expect(words.tagName).toBe('SPAN');
			expect(words).not.toHaveAttribute('aria-hidden');
			expect(words).toHaveClass('min-w-0', 'wrap-break-word');
			const copy = li.cloneNode(true) as Element;
			for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
			expect(squash(words.textContent)).toBe(squash(copy.textContent));
		}
		expect(follows(screen.getByRole('slider'), legend)).toBe(true);
		expect(follows(document.querySelector('[data-group-strip]')!, legend)).toBe(true);
		expect(
			follows(screen.getByRole('button', { name: 'Show data table of the group chart' }), legend)
		).toBe(true);
	});

	it('the actions: Show data table named for its chart; a lasting image reason shown beside Download image, a passing one hidden', async () => {
		const c = named('parallel-ideal');
		const lasting =
			'This solve did not converge: its values are not a solution, so no image is made.';
		const view = render(PumpGroupChart, props(c, { image: image({ unavailable: lasting }) }));
		const show = screen.getByRole('button', { name: 'Show data table of the group chart' });
		// The visible words unchanged, the suffix visually hidden after a space outside it (§6.2);
		// the word not said kept beside them in one grid cell, invisible and aria-hidden, so the
		// swap moves nothing beside the button (the owner's nits of 2026-11-12, item 1,
		// docs/proposals/pumps-nits.md): its text read without it.
		const said = () => {
			const copy = show.cloneNode(true) as Element;
			for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
			return squash(copy.textContent);
		};
		const unsaid = () => show.querySelectorAll('[data-table-words] > [aria-hidden="true"]');
		expect(show.querySelector('.sr-only')!.textContent).toBe('of the group chart');
		expect(said()).toBe('Show data table of the group chart');
		expect(unsaid()).toHaveLength(1);
		expect(unsaid()[0]).toHaveTextContent(/^Hide data table$/);
		expect(unsaid()[0]).toHaveClass('invisible', 'col-start-1', 'row-start-1');
		await fireEvent.click(show);
		expect(screen.getByRole('button', { name: 'Hide data table of the group chart' })).toBe(show);
		expect(said()).toBe('Hide data table of the group chart');
		expect(unsaid()).toHaveLength(1);
		expect(unsaid()[0]).toHaveTextContent(/^Show data table$/);
		expect(unsaid()[0]).toHaveClass('invisible', 'col-start-1', 'row-start-1');
		const download = screen.getByRole('button', { name: /^Download image of the pumps together/ });
		const reason = screen.getByText(lasting);
		expect(reason).toHaveClass('text-xs');
		expect(reason).not.toHaveClass('sr-only');
		expect(outOfSight(reason)).toBe(false);
		expect(download).not.toHaveAttribute('title');
		expect(download).toHaveAccessibleDescription(lasting);
		// One item of the row, beside the button or under it, never under Show data table.
		expect(reason.parentElement).toBe(download.parentElement);
		// A passing reason: hidden, and the button's title.
		await view.rerender(props(c, { image: image(), curve: { status: 'loading' } }));
		const passing = screen.getByText('Wait until the group curve is computed, or cancel it.');
		expect(passing).toHaveClass('sr-only');
		expect(download).toHaveAttribute(
			'title',
			'Wait until the group curve is computed, or cancel it.'
		);
	});

	it('the notes: the duty checks first, each with a ✓ when it agrees; the frame, the members’ notes and the dashed note after them', async () => {
		const c = named('parallel-crane');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		const notes = screen.getByRole('figure').querySelector('[data-group-notes]')!;
		const texts = [...notes.querySelectorAll('p')].map((p) => squash(p.textContent));
		expect(texts[0]).toMatch(/^At the duty's rise the group curve gives the solve's flows/);
		expect(texts[1]).toMatch(/^At the duty's flow the group system curve gives the solve's rise/);
		expect(texts[2]).toMatch(/^Pump curves and points are at each pump's flanges\./);
		// The ✓: its own element before its sentence's p, never inside it, and hidden (§5.2).
		const checks = [...notes.querySelectorAll('[data-group-check]')];
		expect(checks).toHaveLength(2);
		for (const check of checks) {
			const [mark, sentence] = [...check.children];
			expect(mark!.tagName.toLowerCase()).toBe('svg');
			expect(mark).toHaveAttribute('aria-hidden', 'true');
			expect(mark).toHaveClass('text-emerald-700');
			expect(sentence!.tagName).toBe('P');
			expect(sentence!.querySelector('svg')).toBeNull();
		}
		// No other note is marked.
		expect(notes.querySelectorAll('svg')).toHaveLength(2);
		// The axes, the group system curve and each pump's own system curve are reference now.
		for (const re of [
			/^Each pump's curve and point are drawn/,
			/^The group's system curve is/,
			/^Each pump's own system curve/
		])
			expect(texts.some((t) => re.test(t))).toBe(false);
	});

	it('a duty check that disagrees: no ✓, its words visible, its Details named for it', async () => {
		const c = named('parallel-crane');
		const group = structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
		Object.assign(group.dutyCheck!, { agrees: false, message: 'made-up server words' });
		const system = structuredClone(c.systemCurve!.body as PumpGroupCurveResponse);
		Object.assign(system.systemDutyCheck!, {
			agrees: false,
			head: system.duty!.head + 2,
			message: 'made-up system words'
		});
		render(
			PumpGroupChart,
			props(c, {
				curve: { status: 'ready', response: group },
				system: { status: 'ready', response: system }
			})
		);
		await drawn();
		const notes = screen.getByRole('figure').querySelector('[data-group-notes]')!;
		expect(notes.querySelector('[data-group-check]')).toBeNull();
		expect([...notes.querySelectorAll('svg')].filter((svg) => !svg.closest('details'))).toEqual([]);
		const summaries = [...notes.querySelectorAll('summary')];
		expect(summaries.map((s) => squash(s.textContent))).toEqual([
			'Details of the duty check',
			'Details of the system duty check'
		]);
		for (const s of summaries) expect(s.querySelector('.sr-only')).toBeTruthy();
		expect(
			screen.getAllByText('Several steady states can exist; the point is the one the solve found.')
		).toHaveLength(2);
	});

	it('"How to read this chart", closed, holds the axes, the group system curve and each pump’s own system curve; the methods’ summaries as the app’s', async () => {
		const c = named('parallel-ideal');
		const view = render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		const figure = screen.getByRole('figure');
		const reading = figure.querySelector<HTMLDetailsElement>('[data-group-reading]')!;
		expect(reading.open).toBe(false);
		const summary = reading.querySelector('summary')!;
		expect(squash(summary.textContent)).toBe(
			"How to read this chart: the axes, the group system curve, each pump's own system curve"
		);
		const held = [...reading.querySelectorAll('p')].map((p) => squash(p.textContent));
		expect(held).toHaveLength(3);
		expect(held[0]).toMatch(
			/^Each pump's curve and point are drawn against the flow through that pump/
		);
		expect(held[1]).toMatch(/^The group's system curve is the rise the rest of the network needs/);
		expect(held[2]).toBe(
			"Each pump's own system curve is on its pump chart above; it crosses that pump's curve, not the group curve."
		);
		// The three summaries the app's disclosure summary, each closed, its chevron hidden and still
		// with reduced motion.
		const reference = [...figure.querySelectorAll(':scope > details')];
		expect(reference).toHaveLength(3);
		for (const details of reference) {
			const s = details.querySelector('summary')!;
			expect(s).toHaveClass('more-summary');
			expect(s.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
			expect(s.querySelector('svg')).toHaveClass('motion-reduce:transition-none');
			expect((details as HTMLDetailsElement).open).toBe(false);
		}
		for (const p of reading.querySelectorAll('p')) expect(p).not.toBeVisible();
		await fireEvent.click(summary);
		for (const p of reading.querySelectorAll('p')) expect(p).toBeVisible();
		// Without the card's nav (its own tests), no "Go to the pump chart".
		expect(within(reading).queryByRole('button', { name: 'Go to the pump chart' })).toBeNull();
		// No group system curve yet: it says what it holds without it.
		await view.rerender(props(c, { system: { status: 'loading' } }));
		expect(squash(reading.querySelector('summary')!.textContent)).toBe(
			"How to read this chart: the axes, each pump's own system curve"
		);
		expect(reading.querySelectorAll('p')).toHaveLength(2);
	});

	it('names each Details of the group system curve’s data by its point', async () => {
		const c = named('fcv-outside');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		const table = screen.getByRole('table', {
			name: "Group system curve (rise the rest of the network needs at each station's flow)"
		});
		// Open by default: some of its rows have no rise (§9 S7).
		expect(table.closest('details')!.open).toBe(true);
		const response = c.systemCurve!.body as PumpGroupCurveResponse;
		const missing = [...response.systemPoints]
			.sort((a, b) => a.flow - b.flow)
			.filter((p) => p.head === null);
		const names = [...table.querySelectorAll('summary')].map((s) => squash(s.textContent));
		expect(names).toEqual(
			missing.map((p) => `Details of the point at ${formatNumber(p.flow * 1000, 4)} L/s`)
		);
		expect(new Set(names).size).toBe(names.length);
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
				.closest('li')!
				.querySelector('line')
		).toHaveAttribute('stroke', '#eb6834');
		expect(within(figure).getByRole('img')).toHaveAccessibleName(
			/, on the group curve and the group system curve, where they cross; group curve shown; group system curve shown\.$/
		);
		// The group system curve's note is reference (§5.3): inside "How to read this chart".
		await fireEvent.click(within(figure).getByText('How to read this chart').closest('summary')!);
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
		// Its line is the strip's (§5.3 The strip): always there, polite, never role=status.
		const line = document.querySelector('[data-group-system-state]')!;
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(await screen.findByText('Computing the group system curve for this solve…')).toBe(line);
		// The canvas is busy while either curve is computed, as the pump chart's for its system
		// curve (the canvas wrapper since S3, §7).
		const figure = within(screen.getByRole('figure')).getByRole('img');
		expect(figure).toHaveAttribute('aria-busy', 'true');
		const cancel = screen.getByRole('button', { name: 'Cancel the group system curve' });
		// Described by its line, so it says what it cancels (§7 Live regions; S3 review MUT-02).
		expect(cancel).toHaveAccessibleDescription('Computing the group system curve for this solve…');
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
		// Its mark at its first line, as Station's (§5.2 Marks, §15 item 22; S3 review MUT-12).
		expect(line).toHaveTextContent(
			'The group system curve could not be computed: The server is busy.'
		);
		expect(line.querySelector('svg')).toHaveClass('mt-px', 'text-red-700');
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
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		const table = screen.getByRole('table', {
			name: "Group system curve (rise the rest of the network needs at each station's flow)"
		});
		// Open by default: some of its rows have no rise (§9 S7).
		expect(table.closest('details')!.open).toBe(true);
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
			screen.getByText('Several steady states can exist; the point is the one the solve found.')
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
		// Every case made: the plan is drawn folded, its summary saying so; opened before the preview
		// is read (pumps-results-layout.md §5.3 The fold, §10 S4).
		const folded = block().querySelector<HTMLDetailsElement>('[data-lineup-plan]')!;
		expect(folded.open).toBe(false);
		expect(folded.querySelector('summary')).toHaveTextContent(
			'The plan: 2 cases with each pump off: all 2 made'
		);
		await fireEvent.click(folded.querySelector('summary')!);
		expect(folded.open).toBe(true);
		// §7.12: "{name} has its case already: {found.name}." becomes the preview item
		// "{offName}: already a scenario, «{other}» ({id})", in §7.7's short form: the names are equal.
		expect(block()).toHaveTextContent('Pump PA off: already a scenario (S1)');
		expect(within(block()).getByText('Pump PA off: already a scenario (S1)')).toBeVisible();
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
		// The capped look (§5.3, as the pump chart's): the box greyed, the name kept readable.
		expect(boxes[6]).toHaveClass('opacity-45');
		expect(boxes[6]!.closest('label')).toHaveClass('cursor-not-allowed', 'text-slate-600');
		expect(boxes[0]).not.toHaveClass('opacity-45');
		expect(boxes[0]!.closest('label')).not.toHaveClass('cursor-not-allowed');
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

		// Being computed: the progress in their own live line (§5.3 markup rules: polite, never
		// role=status), and Cancel.
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
		const othersLine = document.querySelector('[data-group-others-state]')!;
		expect(othersLine).toHaveAttribute('aria-live', 'polite');
		await vi.waitFor(() =>
			expect(othersLine).toHaveTextContent("Computing the other cases' station duties: 2 of 2…")
		);
		expect(within(screen.getByRole('figure')).getByRole('img')).toHaveAttribute(
			'aria-busy',
			'true'
		);
		const cancel = screen.getByRole('button', { name: "Cancel the other cases' station duties" });
		// Described by their line (§7 Live regions; S3 review MUT-02).
		expect(cancel).toHaveAccessibleDescription(
			"Computing the other cases' station duties: 2 of 2…"
		);
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

	it('the other cases under their h5: the switch first, the cases under it, their own live line, the lasting retry reason shown (pumps-results-layout.md §5.3, S3)', async () => {
		const follows = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		const handlers = {
			onothers: vi.fn(),
			onotherstick: vi.fn(),
			oncancelothers: vi.fn(),
			onretryothers: vi.fn()
		};
		const view = render(
			PumpGroupChart,
			base({ otherCases: others(), othersOn: true, ...handlers })
		);
		await drawn();
		const figure = screen.getByRole('figure');
		const section = figure.querySelector<HTMLElement>('[data-group-others]')!;
		// The h5 heads the figure's last part (§5.1 item 10, §7's outline), a section title.
		const heading = within(figure).getByRole('heading', {
			name: 'Other cases on the group chart',
			level: 5
		});
		expect(section.firstElementChild).toBe(heading);
		expect(heading).toHaveClass('section-title');
		expect(figure.lastElementChild).toBe(section);
		// The switch first, its cost visible; the list it reveals under it (§6.4 item 10).
		const box = within(section).getByRole('checkbox', {
			name: "Also show the other cases' station duties"
		});
		const hint = document.getElementById(box.getAttribute('aria-describedby')!)!;
		expect(outOfSight(hint)).toBe(false);
		const fieldset = within(section).getByRole('group', { name: 'Cases on this chart' });
		expect(follows(heading, box)).toBe(true);
		expect(follows(hint, fieldset)).toBe(true);
		expect(fieldset.firstElementChild!.tagName).toBe('LEGEND');
		// The case shown: a tag, not a control (§5.2 Tags), the grid's first item.
		const grid = fieldset.querySelector('legend + div')!;
		const tag = grid.firstElementChild!;
		expect(tag).toHaveTextContent('● Base case (shown)');
		expect(tag).toHaveClass('rounded', 'bg-slate-100', 'text-xs');
		expect(tag.querySelector('input, button')).toBeNull();
		expect(grid).toHaveClass('grid-cols-[repeat(auto-fill,minmax(13rem,1fr))]');
		// Each box: the ring and its number in a reserved column, then the name.
		const labels = within(fieldset)
			.getAllByRole('checkbox')
			.map((b) => b.closest('label')!);
		for (const label of labels) {
			const column = label.querySelector('input + span')!;
			expect(column).toHaveClass('w-10', 'shrink-0');
			expect(column.querySelector('[aria-hidden="true"]')).toHaveTextContent('○');
		}
		expect(
			labels.map((l) => l.querySelector('input + span')!.textContent!.replace(/\s+/g, ' ').trim())
		).toEqual(labels.map((_, i) => `○ ${i + 1} ·`));
		// Then the name, wrapping, never cut; a stale case's with " (out of date)" (§5.3; S3 review
		// MUT-13, MUT-08).
		const staleFirst = others().map((o, i) => (i === 0 ? { ...o, stale: true } : o));
		await view.rerender(base({ otherCases: staleFirst, othersOn: true, ...handlers }));
		const nameSpans = within(fieldset)
			.getAllByRole('checkbox')
			.map((b) => b.closest('label')!.querySelector('input + span + span')!);
		expect(nameSpans.map((s) => s.textContent)).toEqual(
			staleFirst.map((o) => (o.stale ? `${o.name} (out of date)` : o.name))
		);
		expect(nameSpans[0]!.textContent).toMatch(/ \(out of date\)$/);
		for (const span of nameSpans) {
			expect(span).toHaveClass('min-w-0', 'wrap-break-word');
			expect(span).not.toHaveClass('truncate');
		}
		await view.rerender(base({ otherCases: others(), othersOn: true, ...handlers }));
		// Its own live line (§5.3 markup rules, §7): there while idle, empty, polite and atomic,
		// never role=status, the first child of its row, holding no button, no busy ancestor; the
		// card has no status region of its own.
		const line = section.querySelector<HTMLElement>('[data-group-others-state]')!;
		expect(line).toHaveAttribute('aria-live', 'polite');
		expect(line).toHaveAttribute('aria-atomic', 'true');
		expect(line).not.toHaveAttribute('role');
		expect(line.textContent).toBe('');
		expect(line.parentElement!.firstElementChild).toBe(line);
		expect(line.querySelector('button')).toBeNull();
		expect(line.closest('[aria-busy]')).toBeNull();
		expect(line.parentElement).toHaveClass('sr-only');
		expect(
			within(screen.getByRole('region', { name: /^Pumps together/ })).queryByRole('status')
		).toBeNull();
		expect(follows(fieldset, line)).toBe(true);

		// Some not computed, while a calculation runs: the sentence in the line, "Compute them
		// again" after it with its lasting reason shown (§6.2 Made visible), not in its title.
		const cancelled = others(['S1', 'S2']).map((o, i) =>
			i === 1
				? {
						...o,
						state: 'cancelled' as const,
						retry: true,
						number: null,
						duty: null,
						claim: null,
						words: 'cancelled: you cancelled it'
					}
				: o
		);
		const reason = 'Solve all is running; Cancel in the header stops it.';
		await view.rerender(
			base({
				otherCases: cancelled,
				othersOn: true,
				othersProgress: null,
				othersRetryReason: reason,
				...handlers
			})
		);
		expect(line.textContent).toBe(
			"Not every other case's station duty was computed: see Running combinations."
		);
		expect(line.parentElement).not.toHaveClass('sr-only');
		const again = within(section).getByRole('button', { name: 'Compute them again' });
		expect(again).toHaveAttribute('aria-disabled', 'true');
		expect(again).not.toHaveAttribute('title');
		expect(again).toHaveAccessibleDescription(
			`${reason} Not every other case's station duty was computed: see Running combinations.`
		);
		const shownReason = section.querySelector('[data-others-retry-reason]')!;
		expect(shownReason).toHaveTextContent(reason);
		expect(outOfSight(shownReason)).toBe(false);
		expect(shownReason.parentElement).toBe(again.parentElement);
		expect(follows(line, again)).toBe(true);
		await fireEvent.click(again);
		expect(handlers.onretryothers).not.toHaveBeenCalled();
		// Without the section nav (this card alone) there is no way to Running combinations.
		expect(
			within(section).queryByRole('button', { name: 'Go to Running combinations' })
		).toBeNull();

		// The switch off: the one line, no list, no ring notes.
		const off = others().map((o) => ({
			...o,
			state: 'off' as const,
			onChart: false,
			number: null,
			duty: null,
			claim: null
		}));
		await view.rerender(base({ otherCases: off, othersOn: false, ...handlers }));
		expect(within(section).queryByRole('group', { name: 'Cases on this chart' })).toBeNull();
		const offLine = section.querySelector('[data-group-others-off]')!;
		expect(offLine.textContent).toBe(
			"Other cases' station duties are not on the chart: tick “Also show the other cases' station duties” to compute them (4 other cases with results)."
		);
		expect(follows(box, offLine)).toBe(true);
		expect(section.querySelector('[data-group-rings-how], [data-group-rings]')).toBeNull();
	});

	/** `n` animation frames (jsdom pretends to be visual: requestAnimationFrame runs). */
	async function frames(n: number) {
		for (let i = 0; i < n; i++)
			await new Promise<void>((done) => requestAnimationFrame(() => done()));
	}
	const handlersOf = () => ({
		onothers: vi.fn(),
		onotherstick: vi.fn(),
		oncancelothers: vi.fn(),
		onretryothers: vi.fn()
	});

	it('the other cases wait for the card’s own curves: their line says nothing and there is no Cancel while the group system curve is computed (pumps-results-layout.md §5.3, §7; S3 review MUT-03)', async () => {
		const handlers = handlersOf();
		// As the Pumps view has them while the case shown's curves are not settled: each one
		// waits, so their progress is set (none settled of four).
		const waiting = others().map((o) => ({
			...o,
			state: 'waiting' as const,
			number: null,
			duty: null,
			claim: null,
			words: "waits for this case's curves"
		}));
		const values = (system: GroupCurveState) =>
			base({
				otherCases: waiting,
				othersOn: true,
				othersProgress: { done: 0, total: 4 },
				system,
				...handlers
			});
		const view = render(PumpGroupChart, values({ status: 'loading' }));
		const line = document.querySelector<HTMLElement>('[data-group-others-state]')!;
		// Long past the two frames the line holds back its words for: still nothing of theirs.
		await frames(4);
		expect(await screen.findByText('Computing the group system curve for this solve…')).toBe(
			document.querySelector('[data-group-system-state]')
		);
		expect(line.textContent).toBe('');
		expect(line.parentElement).toHaveClass('sr-only');
		expect(
			screen.queryByRole('button', { name: "Cancel the other cases' station duties" })
		).toBeNull();
		// The card's curves answered: their progress and their Cancel.
		await view.rerender(values(systemReady(c)));
		expect(line).toHaveTextContent("Computing the other cases' station duties: 1 of 4…");
		expect(
			screen.getByRole('button', { name: "Cancel the other cases' station duties" })
		).toHaveAccessibleDescription("Computing the other cases' station duties: 1 of 4…");
	});

	it('the other cases’ line mounted as their requests run is drawn empty before it speaks (§7 Live regions, F17; S3 review MUT-04)', async () => {
		// The card opened again while they are computed, its own curves ready: the section mounts
		// with their progress already set, and a polite line inserted speaking is not announced.
		const loading = others(['S1', 'S2']).map((o, i) =>
			i === 1 ? { ...o, state: 'loading' as const, number: null, duty: null, claim: null } : o
		);
		render(
			PumpGroupChart,
			base({
				otherCases: loading,
				othersOn: true,
				othersProgress: { done: 1, total: 2 },
				...handlersOf()
			})
		);
		const line = document.querySelector<HTMLElement>('[data-group-others-state]')!;
		expect(line.textContent).toBe('');
		expect(line.querySelector('svg')).toBeNull();
		await vi.waitFor(() =>
			expect(line).toHaveTextContent("Computing the other cases' station duties: 2 of 2…")
		);
		expect(line.querySelector('svg')).toHaveClass('motion-safe:animate-spin');
	});

	it('the rings on screen (4d): the frame in "How to read the rings", the rule only with a group system curve; no ring, no disclosure (pumps-results-layout.md §5.3, S3)', async () => {
		const follows = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		const list = others();
		// S4 unticked (synthetic): no ring, and the reason under the list.
		list[3] = {
			...list[3]!,
			state: 'unticked',
			onChart: false,
			number: null,
			duty: null,
			claim: null,
			words: 'not on the chart (unticked under Cases on this chart)'
		};
		const view = render(
			PumpGroupChart,
			base({ otherCases: list, othersOn: true, onothers: () => {}, image: image() })
		);
		await drawn();
		const section = document.querySelector<HTMLElement>('[data-group-others]')!;
		const how = section.querySelector<HTMLDetailsElement>('[data-group-rings-how]')!;
		// Closed by default; its summary names what it holds: the frame and the rule.
		expect(how.open).toBe(false);
		const summary = how.querySelector('summary')!;
		expect(summary).toHaveClass('more-summary');
		expect(summary.textContent!.replace(/\s+/g, ' ').trim()).toBe(
			'How to read the rings: what a ring is, which curve it lies on, when it is called a point of the group system curve'
		);
		const held = [...how.querySelectorAll('p')].map((p) => p.textContent);
		expect(held).toHaveLength(2);
		expect(held[0]).toMatch(/^Each numbered slate ring is another case's station duty: /);
		expect(held[1]).toMatch(/^A ring is called a point of the group system curve shown only when /);
		for (const p of how.querySelectorAll('p')) expect(outOfSight(p)).toBe(true);
		// The list after it, named by its lead (told apart from the legend), one item per ring.
		const ringList = within(section).getByRole('list', {
			name: 'Other cases on the chart (slate rings, numbered):'
		});
		expect(follows(how, ringList)).toBe(true);
		const items = within(ringList).getAllByRole('listitem');
		expect(items).toHaveLength(3);
		const notOn = within(section).getByText(
			'Not on the chart: Both pumps off (unticked under Cases on this chart).'
		);
		expect(follows(ringList, notOn)).toBe(true);
		expect(outOfSight(notOn)).toBe(false);
		// The image's footer keeps the frame, the rule and the ring list as one sentence (§6.3).
		await vi.waitFor(() =>
			expect(
				screen.getByRole('button', { name: /^Download image of the pumps together/ })
			).not.toHaveAttribute('aria-disabled', 'true')
		);
		await fireEvent.click(
			screen.getByRole('button', { name: /^Download image of the pumps together/ })
		);
		await vi.waitFor(() => expect(images.requests).toHaveLength(1));
		const lines = (images.requests[0] as FigureImageRequest).lines;
		expect(lines).toContain(held[0]);
		expect(lines).toContain(held[1]);
		const text = (li: Element) => {
			const copy = li.cloneNode(true) as Element;
			for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
			return copy.textContent!.replace(/\s+/g, ' ').trim();
		};
		expect(lines).toContain(
			`Other cases on the chart (slate rings, numbered): ${items.map(text).join('; ')}.`
		);

		// Without a group system curve: the frame alone, and the summary says so.
		await view.rerender(
			base({ otherCases: list, othersOn: true, onothers: () => {}, system: undefined })
		);
		const frameOnly = section.querySelector<HTMLDetailsElement>('[data-group-rings-how]')!;
		expect(frameOnly.querySelector('summary')!.textContent!.replace(/\s+/g, ' ').trim()).toBe(
			'How to read the rings: what a ring is, which curve it lies on'
		);
		expect(frameOnly.querySelectorAll('p')).toHaveLength(1);

		// No ring on the chart (every case unticked): no disclosure and no list, "Not on the chart" stays.
		const none = list.map((o) => ({
			...o,
			state: 'unticked' as const,
			onChart: false,
			number: null,
			duty: null,
			claim: null,
			words: 'not on the chart (unticked under Cases on this chart)'
		}));
		await view.rerender(base({ otherCases: none, othersOn: true, onothers: () => {} }));
		expect(section.querySelector('[data-group-rings-how]')).toBeNull();
		expect(section.querySelector('[data-group-rings]')).toBeNull();
		expect(within(section).getByText(/^Not on the chart: Pump PA off/)).toBeVisible();

		// No station shown (the group curve not ready, the group system curve without a duty): no
		// ring, so neither the disclosure nor the rule (§5.3: the rule never comes without the frame).
		const noDuty = structuredClone(c.systemCurve!.body as PumpGroupCurveResponse);
		noDuty.duty = null;
		await view.rerender(
			base({
				otherCases: list,
				othersOn: true,
				onothers: () => {},
				curve: { status: 'loading' },
				system: { status: 'ready', response: noDuty }
			})
		);
		expect(document.querySelector('[data-group-rings-how]')).toBeNull();
		expect(document.querySelector('[data-group-rings]')).toBeNull();
		expect(screen.queryByText(/^A ring is called a point of the group system curve/)).toBeNull();
	});

	it('every footer line on screen with the rings (4d) and with the duties not asked for (pumps-results-layout.md §10, S3)', async () => {
		const list = others();
		list[3] = {
			...list[3]!,
			state: 'unticked',
			onChart: false,
			number: null,
			duty: null,
			claim: null,
			words: 'not on the chart (unticked under Cases on this chart)'
		};
		const view = render(
			PumpGroupChart,
			base({ otherCases: list, othersOn: true, onothers: () => {}, image: image() })
		);
		await drawn();
		const lines = await footerLines();
		const inside = footerOnScreen(lines);
		// The frame and the rule are inside "How to read the rings"; "Not on the chart" in sight.
		expect(inside.filter((l) => /^Each numbered slate ring/.test(l))).toHaveLength(1);
		expect(inside).toContain(
			lines.find((l) => l.startsWith('A ring is called a point of the group system curve'))
		);
		const notOn = 'Not on the chart: Both pumps off (unticked under Cases on this chart).';
		expect(lines).toContain(notOn);
		expect(inside).not.toContain(notOn);
		expect(lines.some((l) => l.startsWith(`${RING_LEAD} `))).toBe(true);
		// The duties not asked for: the one line, in sight.
		const off = others().map((o) => ({
			...o,
			state: 'off' as const,
			onChart: false,
			number: null,
			duty: null,
			claim: null
		}));
		await view.rerender(
			base({ otherCases: off, othersOn: false, onothers: () => {}, image: image() })
		);
		const offLines = await footerLines();
		expect(offLines.filter((l) => l.includes('Also show'))).toHaveLength(1);
		expect(footerOnScreen(offLines).some((l) => l.includes('Also show'))).toBe(false);
	});

	it('the data region: each pump’s point, the duty sentence in two, the group curves’ tables, then the other cases’ (pumps-results-layout.md §5.3, S3)', async () => {
		render(PumpGroupChart, base({ otherCases: others(), othersOn: true, onothers: () => {} }));
		await drawn();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		const region = document.querySelector<HTMLElement>('[data-group-data]')!;
		// After the reference, before the other cases' part (§5.1 items 8 to 10).
		const reference = document.querySelectorAll('figure details:not([data-group-rings-how])');
		const follows = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		for (const d of reference) {
			if (!region.contains(d)) expect(follows(d, region)).toBe(true);
		}
		expect(follows(region, document.querySelector('[data-group-others]')!)).toBe(true);
		const parts = [...region.children].map((child) =>
			child.matches('[data-group-duty]')
				? 'duty'
				: child.matches('[data-group-system-duty]')
					? 'system duty'
					: child.querySelector('caption')!.textContent!.trim()
		);
		expect(parts).toEqual([
			"Each pump's point (flow through it)",
			'duty',
			'system duty',
			"Group curve (station's flow at each rise)",
			"Group system curve (rise the rest of the network needs at each station's flow)",
			"Other cases' station duties"
		]);
		// Each paragraph its own check and its own Details (§5.3 item 2), the words unchanged.
		const duty = region.querySelector('[data-group-duty]')!;
		expect(duty.textContent!.replace(/\s+/g, ' ')).toMatch(
			/^● Group duty \(station's flow\): [\d.]+ L\/s at a rise of [\d.]+ m; parallel\. Duty check: the group curve passes through it; /
		);
		expect(duty.querySelectorAll('details')).toHaveLength(1);
		expect(
			within(duty as HTMLElement)
				.getByText('Details')
				.closest('summary')
		).toHaveTextContent('Details of the duty check');
		expect(duty).not.toHaveTextContent('System duty check');
		const system = region.querySelector('[data-group-system-duty]')!;
		expect(system.textContent!.replace(/\s+/g, ' ').trim()).toMatch(
			/^System duty check: the group system curve passes through it\. ?Details/
		);
		expect(system.querySelectorAll('details')).toHaveLength(1);
		expect(system.querySelector('summary')).toHaveTextContent('Details of the system duty check');
	});

	it('its sections, in reading order under h4s: Station, Group chart, Add cases, Running combinations (pumps-results-layout.md §5.3, §9 S2)', async () => {
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
					status: 'solved',
					response: c.scenarioCases.S2!.solve,
					stale: false,
					station: null,
					ring: 2
				}
			],
			prefs: c.project.settings.units,
			project: c.project
		};
		const extremes = combinationExtremes(input);
		expect(extremes.lines.length).toBeGreaterThan(0);
		render(
			PumpGroupChart,
			base({
				lineups: plan(),
				otherCases: others(),
				othersOn: true,
				onothers: () => {},
				image: image(),
				combinations: runningCombinations(input),
				extremes
			})
		);
		await drawn();
		const card = screen.getByRole('region', { name: /^Pumps together/ });
		// The outline of the card (§7): the h3, an h4 per section, the extremes' h5 under the h4 of
		// the section it summarises (F13: before, it followed Add cases).
		expect(
			within(card)
				.getAllByRole('heading')
				.map((h) => [h.tagName, h.textContent!.replace(/\s+/g, ' ').trim()])
		).toEqual([
			['H3', 'Pumps together'],
			['H4', 'Station'],
			['H4', 'Group chart'],
			['H5', 'Other cases on the group chart'],
			['H4', 'Add cases'],
			['H4', 'Running combinations'],
			['H5', 'Extremes over these cases (current results)']
		]);
		const heading = (name: string) => within(card).getByRole('heading', { name, level: 4 });
		/** A section: its h4's wrapper, or for Add cases the block itself, its framed panel (§9 S4). */
		const section = (name: string) =>
			name === 'Add cases' ? block() : heading(name).parentElement!;
		const follows = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		const order = ['Station', 'Group chart', 'Add cases', 'Running combinations'];
		for (const [i, name] of order.entries()) {
			// After the members, each section after the one before, and its heading first in it.
			const s = section(name);
			expect(follows(within(card).getByRole('group', { name: 'Pumps in the group' }), s)).toBe(
				true
			);
			if (i > 0) expect(follows(section(order[i - 1]!), s)).toBe(true);
			expect(s.contains(heading(name))).toBe(true);
			expect(s.querySelector('h4')).toBe(heading(name));
			// The type scale (§5.2): a rule above each section; Add cases a framed, tinted panel
			// instead, the card's one part that changes the project (§5.3, §9 S4).
			if (name === 'Add cases') expect(s).toHaveClass('border', 'rounded-lg', 'bg-slate-50', 'p-3');
			else expect(s).toHaveClass('border-t', 'pt-3');
		}
		// Each part in its section, after its heading.
		const inSection = (name: string, el: Element) => {
			expect(section(name).contains(el)).toBe(true);
			expect(follows(heading(name), el)).toBe(true);
		};
		inSection('Station', boxOf('The pumps in the group, Base case', card));
		inSection('Station', within(card).getByLabelText('The station'));
		inSection('Group chart', within(card).getByRole('figure'));
		// The block (its own region) is a section of the card's body, as the others are, in place of
		// S2's wrapper (§15 item 54); its header row first in it: the h4, then its tag, a sibling,
		// so the region is named by the h4 alone (§5.3, §9 S4).
		expect(block().parentElement).toBe(section('Station').parentElement);
		expect([...block().firstElementChild!.children]).toEqual([
			heading('Add cases'),
			within(block()).getByText('Changes the project', { exact: true })
		]);
		inSection(
			'Running combinations',
			within(card).getByRole('table', { name: 'Running combinations' })
		);
		inSection(
			'Running combinations',
			within(card).getByRole('heading', { name: 'Extremes over these cases (current results)' })
		);
		inSection(
			'Running combinations',
			within(card).getByRole('table', { name: 'Extremes over these cases' })
		);
		// The type scale (§5.2): the h3 16 px, each h4 14 px, both semibold; the h5 a section title.
		expect(within(card).getByRole('heading', { level: 3 })).toHaveClass(
			'text-base',
			'font-semibold'
		);
		for (const name of ['Station', 'Group chart', 'Add cases', 'Running combinations']) {
			expect(heading(name)).toHaveClass('text-sm', 'font-semibold');
			// The section nav's targets (§5.4): headings that take the focus, never a Tab stop.
			expect(heading(name)).toHaveAttribute('tabindex', '-1');
		}
		expect(
			within(card).getByRole('heading', { name: 'Extremes over these cases (current results)' })
		).toHaveClass('section-title');
		// Plain divs with headings, not landmarks (§7): the regions are the ones tests pin.
		expect(within(card).queryByRole('region', { name: 'Station' })).toBeNull();
		expect(within(card).queryByRole('region', { name: 'Group chart' })).toBeNull();
		// Running combinations' box: a ResultsTable's since S6b (§9 S6b), the region in the block
		// that holds its controls and its box, named by the h4, while it overflows (§9 S7): its
		// cases taller than its box.
		const box = boxOf('Running combinations', card);
		sizeBox(box, { clientWidth: 452, scrollWidth: 452, clientHeight: 608, scrollHeight: 2400 });
		observers.resize(box);
		const combinations = within(card).getByRole('region', { name: 'Running combinations' });
		expect(combinations).toBe(box);
		expect(card.querySelector('[data-running-combinations] [role="region"]')).toBe(combinations);
		expect(combinations).toHaveAttribute('aria-labelledby', heading('Running combinations').id);
		// Running combinations' caption is visually hidden beside its h4, and still its name.
		const caption = within(card)
			.getByRole('table', { name: 'Running combinations' })
			.querySelector('caption')!;
		expect(caption).toHaveTextContent('Running combinations');
		expect(caption).toHaveClass('sr-only');
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
		// The heading's row and a row per member, each flagged member's followed by its flag line
		// (pumps-results-layout.md §5.3 Flags, §10 S5): in Held both are flagged, Pump PA with
		// warnings and Pump PB invalid.
		const flagged = runningCombinations(input).groups[2]!.rows.filter((r) => r.flags.length);
		expect(flagged.map((r) => r.id)).toEqual(['PA', 'PB']);
		expect(rows).toHaveLength(3 + flagged.length);
		// Pump PB's row by its row header, not by its index.
		const pb = rows.find((r) => within(r).queryByRole('rowheader', { name: 'Pump PB' }))!;
		expect(within(pb).getByRole('rowheader')).toHaveTextContent('Pump PB');
		// A long name wraps, at 12 rem in the table and anywhere on a phone (the list has no
		// sideways scroll; the e2e measures it): the name's own box wraps, the row header no longer
		// keeps it on one line (§15 item 92, the group table's).
		const name = within(pb).getByRole('rowheader').firstElementChild!;
		expect(name).toHaveTextContent('Pump PB');
		expect(name).toHaveClass(
			'w-max',
			'max-w-48',
			'wrap-break-word',
			'max-sm:w-auto',
			'max-sm:max-w-none',
			'max-sm:wrap-anywhere'
		);
		expect(within(pb).getByRole('rowheader')).not.toHaveClass('whitespace-nowrap');
		expect(name).not.toHaveClass('whitespace-nowrap');
		const cells = within(pb).getAllByRole('cell');
		expect(cells[0]).toHaveTextContent('No flow (system head above shutoff)');
		// Speed next (Pump PB at another speed), then the flow, marked.
		expect(cells[1]).toHaveAttribute('data-label', 'Speed (%)');
		expect(cells[2]).toHaveAttribute('data-label', 'Flow (L/s)');
		expect(cells[2]).toHaveTextContent('physically invalid:');
		// No Flags column: the flag line follows the pump's row (§10 S5).
		expect(cells.map((cell) => cell.dataset.label)).not.toContain('Flags');
		const line = pb.nextElementSibling!.querySelector('[data-row-notes]')!;
		expect(line).toHaveAttribute('data-row-notes', 'PB');
		expect(line).toHaveAttribute('data-label', 'Flags');
		expect(line).toHaveTextContent('Invalid');
		// Not marked where the pump has no invalid flag.
		const pa = within(groups[1]!).getAllByRole('row')[1]!;
		expect(within(pa).getAllByRole('cell')[2]).toHaveAttribute('data-label', 'Flow (L/s)');
		expect(within(pa).getAllByRole('cell')[2]).not.toHaveTextContent('physically invalid');
		expect(within(groups[4]!).getAllByRole('row')).toHaveLength(1);
		// The extremes a table (pumps-results-layout.md §5.3, §10 S5): the pump and the measure
		// pinned by the row and column headers, the cell's words whole.
		const extremes = screen.getByRole('table', { name: 'Extremes over these cases' });
		expect(extremes.tagName).toBe('TABLE');
		expect(
			screen.getByRole('heading', { name: 'Extremes over these cases (current results)' })
		).toBeVisible();
		const paRow = within(extremes)
			.getAllByRole('row')
			.find((r) => within(r).queryByRole('rowheader', { name: 'Pump PA' }))!;
		const flowColumn = within(extremes)
			.getAllByRole('columnheader')
			.findIndex((h) => h.textContent === 'Largest flow');
		// The row header is the row's first cell, so a column's cell is that index less one.
		expect(within(paRow).getAllByRole('cell')[flowColumn - 1]!.textContent).toBe(
			'40.75 L/s in Held (synthetic); beyond its curve data (over 2 of 2 cases)'
		);
		expect(screen.getByText('Not counted (out of date): Pump PB off.')).toBeVisible();
	});

	/** FlagIcon's shapes (Icon.svelte): the invalid octagon, and the warning's triangle. */
	const OCTAGON = 'M8 3h8l5 5v8l-5 5H8l-5-5V8z';
	const TRIANGLE = 'M12 3 2 20h20z';
	/** The icon shapes drawn inside an element, by their outline's path. */
	const shapes = (el: Element) =>
		[...el.querySelectorAll('svg')].map((svg) => svg.querySelector('path')!.getAttribute('d'));
	/** Two members, every case given, the one-off project's order. */
	const combinationsOf = (cases: CombinationsInput['cases']): CombinationsInput => ({
		members: [
			{ id: 'PA', name: 'Pump PA', slot: 0 },
			{ id: 'PB', name: 'Pump PB', slot: 1 }
		],
		cases,
		prefs: c.project.settings.units,
		project: c.project
	});
	const solvedCase = (
		key: string,
		name: string,
		response: SolveResponse | null,
		values: Partial<CombinationsInput['cases'][number]> = {}
	): CombinationsInput['cases'][number] => ({
		key,
		name,
		shown: key === '',
		status: response ? 'solved' : 'failed',
		response,
		stale: false,
		station: null,
		...values
	});

	it('the extremes’ box and Running combinations’ box: each a Tab stop and a named region only while it overflows (§9 S7, §7 item 25)', () => {
		const input = combinationsOf([
			solvedCase('', 'Base case', c.solve),
			solvedCase('S2', 'Pump PB off', c.scenarioCases.S2!.solve)
		]);
		render(
			PumpGroupChart,
			base({ combinations: runningCombinations(input), extremes: combinationExtremes(input) })
		);
		const extremes = boxOf('Extremes over these cases');
		const combos = boxOf('Running combinations');
		// From 26 rem the extremes fit their box: no Tab stop (S5's measure, §7 item 25).
		sizeBox(extremes, { clientWidth: 452, scrollWidth: 452, clientHeight: 300, scrollHeight: 300 });
		observers.resize(extremes);
		expect(extremes).not.toHaveAttribute('tabindex');
		expect(screen.queryByRole('region', { name: 'Extremes over these cases' })).toBeNull();
		// An unbroken name wider than the box: it scrolls, so the keyboard can reach it.
		sizeBox(extremes, { scrollWidth: 881 });
		observers.resize(extremes);
		expect(screen.getByRole('region', { name: 'Extremes over these cases' })).toBe(extremes);
		expect(extremes).toHaveAttribute('tabindex', '0');
		// Running combinations' cases fit (a phone's list, or few cases), then taller than the box.
		sizeBox(combos, { clientWidth: 452, scrollWidth: 452, clientHeight: 608, scrollHeight: 608 });
		observers.resize(combos);
		expect(screen.queryByRole('region', { name: 'Running combinations' })).toBeNull();
		expect(combos).not.toHaveAttribute('tabindex');
		sizeBox(combos, { scrollHeight: 2400 });
		observers.resize(combos);
		expect(screen.getByRole('region', { name: 'Running combinations' })).toBe(combos);
		expect(combos).toHaveAttribute('tabindex', '0');
	});

	it('Running combinations opens with its lead, its mark the worst severity, then the extremes, then its table (pumps-results-layout.md §5.3, §6.1, §9 S5)', () => {
		const dead = named('one-off-dead-headed') as unknown as OneOffCase;
		const input = combinationsOf([
			solvedCase('', 'Base case', c.solve),
			solvedCase('S2', 'Pump PB off', c.scenarioCases.S2!.solve, { status: 'stale', stale: true }),
			solvedCase('S9', 'Held (synthetic)', dead.solve),
			solvedCase('S5', 'Failed case', null)
		]);
		const view = render(
			PumpGroupChart,
			base({ combinations: runningCombinations(input), extremes: combinationExtremes(input) })
		);
		const heading = screen.getByRole('heading', { name: 'Running combinations', level: 4 });
		const section = heading.parentElement!;
		const lead = section.querySelector('[data-combinations-lead]')!;
		// The base and Held current (Held's Pump PB invalid, its Pump PA's warnings counted with
		// it), Pump PB off out of date, the failed case without results (§5.3 the lead).
		expect(lead.tagName).toBe('P');
		expect(lead.textContent).toBe(
			'4 cases: 2 with current results (1 physically invalid, none with warnings), 1 out of date, 1 without results.'
		);
		// 14 px with tabular figures (§5.2 Answers), on screen at every width: no hiding class at
		// any breakpoint on it or above it (S5 review MUT-04).
		expect(lead).toHaveClass('text-sm', 'tabular-nums');
		expect(outOfSight(lead)).toBe(false);
		// Its mark: its own element before the <p>, never inside it (§5.2 Placement), an image
		// named by the worst severity, the red octagon.
		const mark = within(section).getByRole('img', { name: 'Physically invalid' });
		expect(lead.contains(mark)).toBe(false);
		expect(mark.nextElementSibling).toBe(lead);
		// Drawn at every width, its octagon too (S5 review MUT-03; jsdom's roles see no CSS).
		expect(outOfSight(mark)).toBe(false);
		expect(outOfSight(mark.querySelector('svg')!)).toBe(false);
		expect(shapes(mark)).toEqual([OCTAGON]);
		expect(mark.querySelector('svg')).toHaveClass('text-red-700');
		// In reading order: the h4, the lead, the h5 and the extremes, "Not counted", then the
		// table (§5.3, §6.1: the extremes before Running combinations' table).
		const follows = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		const order = [
			heading,
			lead,
			screen.getByRole('heading', { name: 'Extremes over these cases (current results)' }),
			screen.getByRole('table', { name: 'Extremes over these cases' }),
			screen.getByText('Not counted (out of date): Pump PB off.'),
			screen.getByRole('table', { name: 'Running combinations' })
		];
		for (const [i, el] of order.entries()) {
			expect(section.contains(el)).toBe(true);
			if (i > 0) expect(follows(order[i - 1]!, el), String(i)).toBe(true);
		}
		// A warning alone: the amber alert, named "Warning".
		const warned = combinationsOf([
			solvedCase('', 'Base case', c.solve),
			solvedCase('S2', 'Pump PB off', c.scenarioCases.S2!.solve)
		]);
		view.rerender(
			base({ combinations: runningCombinations(warned), extremes: combinationExtremes(warned) })
		);
		expect(section.querySelector('[data-combinations-lead]')!.textContent).toBe(
			'2 cases: 2 with current results (none physically invalid, 1 with warnings), none out of date, none without results.'
		);
		const warning = within(section).getByRole('img', { name: 'Warning' });
		expect(shapes(warning)).toEqual([TRIANGLE]);
		expect(warning.querySelector('svg')).toHaveClass('text-amber-700');
		expect(within(section).queryByRole('img', { name: 'Physically invalid' })).toBeNull();
		// Neither: no mark.
		const clean = combinationsOf([
			solvedCase('', 'Base case', c.solve),
			solvedCase('S1', 'Pump PA off', c.scenarioCases.S1!.solve)
		]);
		view.rerender(
			base({ combinations: runningCombinations(clean), extremes: combinationExtremes(clean) })
		);
		expect(section.querySelector('[data-combinations-lead]')!.textContent).toBe(
			'2 cases: 2 with current results (none physically invalid, none with warnings), none out of date, none without results.'
		);
		expect(section.querySelector('[data-combinations-mark]')).toBeNull();
		expect(within(section).queryByRole('img')).toBeNull();
	});

	it('the extremes a table: caption, column and row headers, each cell its line’s words, the value first and the octagon in exactly the invalid ones; a list below 26 rem (pumps-results-layout.md §5.3, §9 S5)', () => {
		const dead = named('one-off-dead-headed') as unknown as OneOffCase;
		// Synthetic: the dead-headed base twice, so Pump PB's extremes are in a case where it is
		// invalid, and it gives no NPSH margin there.
		const input = combinationsOf([
			solvedCase('', 'Base case', dead.solve),
			solvedCase('S8', 'Copy', dead.solve)
		]);
		const extremes = combinationExtremes(input);
		render(PumpGroupChart, base({ combinations: runningCombinations(input), extremes }));
		const table = screen.getByRole('table', { name: 'Extremes over these cases' });
		// Its name a visually hidden caption, the dl's aria-label words; the h5 heads it.
		const caption = table.querySelector('caption')!;
		expect(caption).toHaveTextContent('Extremes over these cases');
		expect(caption).toHaveClass('sr-only');
		expect(table.querySelector('dl')).toBeNull();
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => [h.textContent, h.getAttribute('scope')])
		).toEqual([
			['Pump', 'col'],
			['Largest flow', 'col'],
			['Largest shaft power', 'col'],
			['Smallest NPSH margin', 'col']
		]);
		const rows = within(table)
			.getAllByRole('row')
			.filter((r) => within(r).queryByRole('rowheader'));
		expect(
			rows.map((r) => {
				const h = within(r).getByRole('rowheader');
				return [h.tagName, h.getAttribute('scope'), h.textContent];
			})
		).toEqual([
			['TH', 'row', 'Pump PA'],
			['TH', 'row', 'Pump PB']
		]);
		// The sticky row header wraps at 12 rem, an unbroken name breaking inside it (§5.3).
		for (const r of rows) {
			expect(within(r).getByRole('rowheader')).toHaveClass(
				'sticky',
				'left-0',
				'bg-white',
				'border-r',
				'max-w-48',
				'wrap-break-word'
			);
		}
		// Cell by cell, its line: the column's words its data-label, its text the line's value,
		// with the row's name and the column's words the line's term (§9 S5).
		const labels = ['Largest flow', 'Largest shaft power', 'Smallest NPSH margin'];
		let invalid = 0;
		let none = 0;
		for (const [i, r] of rows.entries()) {
			const cells = within(r).getAllByRole('cell');
			expect(cells.map((cell) => cell.dataset.label)).toEqual(labels);
			for (const [j, cell] of cells.entries()) {
				const line = extremes.lines[i * labels.length + j]!;
				const name = within(r).getByRole('rowheader').textContent;
				expect(line.term).toBe(
					`${name}, ${labels[j]!.charAt(0).toLowerCase()}${labels[j]!.slice(1)}`
				);
				expect(cell.textContent).toBe(line.value);
				const value = extremes.table.rows[i]!.cells[j]!;
				if (value.amount === null) {
					// "no case gives one" fills its cell alone, with no value line.
					expect(cell.children).toHaveLength(1);
					expect(cell.firstElementChild).toHaveTextContent(/^no case gives one$/);
					none++;
				} else {
					// The value on the cell's first line, medium and slate-900; the rest under it.
					const [first, rest] = [...cell.children];
					expect(first!.textContent).toBe(value.amount);
					expect(first).toHaveClass('flex', 'font-medium', 'text-slate-900');
					expect(rest!.textContent).toBe(value.rest);
					expect(rest).toHaveClass('text-slate-600');
				}
				// The red octagon before the value exactly where its case is physically invalid
				// for that pump (the words say so too), never the warning's triangle (§5.2).
				const marked = line.value.includes('; physically invalid');
				expect(value.invalid, line.term).toBe(marked);
				expect(shapes(cell), line.term).toEqual(marked ? [OCTAGON] : []);
				if (marked) {
					expect(cell.querySelector('svg')).toHaveClass('text-red-700');
					// Before the value: the value's nodes in order, its text counted (an element
					// child alone skips the amount's text node and so cannot see the order).
					const drawn = [...cell.firstElementChild!.childNodes].filter(
						(n) =>
							n.nodeType === Node.ELEMENT_NODE ||
							(n.nodeType === Node.TEXT_NODE && n.textContent!.trim() !== '')
					);
					expect(drawn.map((n) => n.nodeName.toLowerCase())).toEqual(['svg', '#text']);
					expect(drawn[1]!.textContent).toBe(value.amount);
					invalid++;
				}
			}
		}
		expect([invalid > 0, none > 0]).toEqual([true, true]);
		// Its box: sideways shadows, and no Tab stop in S5 (S7's measured rule covers it, §5.3);
		// not a region. Its wrapper, the box's width, the inline-size container, so the box drops
		// its frame in the list (§5.5); a long unbroken word breaks inside its cell.
		const box = table.parentElement!;
		expect(box).toHaveClass('scroll-shadow-x', 'overflow-x-auto', 'border');
		expect(box).toHaveClass('@max-[26rem]:border-0');
		expect(box).not.toHaveAttribute('tabindex');
		expect(box).not.toHaveAttribute('role');
		expect(box.parentElement).toHaveClass('@container');
		for (const cell of within(table).getAllByRole('cell'))
			expect(cell).toHaveClass('wrap-anywhere');
		// Below 26 rem of its box, a list (§5.3, §5.5; the e2e lays it out): the roles kept, the
		// header row visually hidden, a block per pump, each line headed by its data-label as
		// ::before content, never an element.
		expect(table).toHaveAttribute('role', 'table');
		expect(table.querySelector('thead')).toHaveClass('@max-[26rem]:sr-only');
		for (const r of rows) {
			expect(r).toHaveClass('@max-[26rem]:block');
			expect(within(r).getByRole('rowheader')).toHaveClass(
				'@max-[26rem]:block',
				'@max-[26rem]:static',
				'@max-[26rem]:font-semibold'
			);
			for (const cell of within(r).getAllByRole('cell')) {
				// Its header and a space (the mock's `attr(data-label) " "`), so the list cell's
				// accessible name never runs its header into its words (S5 review EXT-1).
				expect(cell).toHaveClass(
					'@max-[26rem]:block',
					"@max-[26rem]:before:content-[attr(data-label)_'_']",
					'@max-[26rem]:before:text-slate-600'
				);
				expect(cell.textContent).not.toContain(cell.dataset.label);
				// The value by its text on the line's baseline, its octagon centred (EXT-2).
				const amount = cell.querySelector(':scope > span.font-medium');
				if (amount) {
					expect(amount).toHaveClass('@max-[26rem]:inline-flex', '@max-[26rem]:items-baseline');
					const icon = amount.querySelector('svg');
					if (icon) expect(icon).toHaveClass('self-center');
				}
			}
		}
		// Running combinations' marked cells take the same octagon, keeping their visually hidden
		// "physically invalid:"; no value cell draws the triangle (the flag lines' warnings do).
		const combos = screen.getByRole('table', { name: 'Running combinations' });
		const valueCells = within(combos)
			.getAllByRole('cell')
			.filter((cell) => !cell.querySelector('[data-label="Flags"]'));
		const markedCells = valueCells.filter((cell) =>
			cell.textContent!.includes('physically invalid:')
		);
		expect(markedCells.length).toBeGreaterThan(0);
		for (const cell of valueCells) {
			const marked = markedCells.includes(cell);
			expect(shapes(cell)).toEqual(marked ? [OCTAGON] : []);
			if (marked) {
				expect(cell.querySelector('svg')).toHaveClass('text-red-700');
				expect(within(cell).getByText('physically invalid:')).toHaveClass('sr-only');
			}
		}
	});

	it('Running combinations’ lines and names: a size container, each heading line sticky at its visible width, a flag line under each flagged pump’s row (no Flags column, no “None”), trace buttons in the shown case’s group only (pumps-results-layout.md §5.3, §9 S5)', async () => {
		const dead = named('one-off-dead-headed') as unknown as OneOffCase;
		const input = combinationsOf([
			solvedCase('', 'Base case', c.solve, {
				station: 'Station 55.15 L/s at a rise of 27.38 m'
			}),
			solvedCase('S2', 'Pump PB off', c.scenarioCases.S2!.solve, { ring: 2 }),
			solvedCase('S9', 'Held (synthetic)', dead.solve),
			solvedCase('S5', 'Failed case', null)
		]);
		const table = runningCombinations(input);
		const flagText = (flag: Flag) => `${flag.code}: ${flag.message}`;
		const squash = (text: string | null) => (text ?? '').replace(/\s+/g, ' ').trim();
		const oninspect = vi.fn();
		render(PumpGroupChart, base({ combinations: table, flagText, oninspect }));
		const box = boxOf('Running combinations');
		// A size container (§5.5), so a heading line and a flag line are the box's visible width.
		expect(box).toHaveClass('@container', 'scroll-shadow-x', 'overflow-auto', 'relative');
		const combos = within(box).getByRole('table', { name: 'Running combinations' });
		const columns = within(combos).getAllByRole('columnheader');
		expect(columns.map((h) => h.textContent!.trim())).not.toContain('Flags');
		// No Flags column, so no "None" on screen or in a phone's list (§5.3 Phones).
		expect(within(combos).queryByText('None')).toBeNull();
		expect(combos.querySelector('[title]')).toBeNull();
		const groups = within(combos).getAllByRole('rowgroup').slice(1);
		expect(groups).toHaveLength(table.groups.length);
		let flaggedRows = 0;
		let plainRows = 0;
		for (const [g, group] of table.groups.entries()) {
			const body = groups[g]!;
			// The heading: one cell across the row, each line sticky at the box's visible width
			// and wrapping there, a list's line on a phone (§5.3 Group heading lines).
			const heading = within(body)
				.getAllByRole('rowheader')
				.find((h) => h.getAttribute('scope') === 'rowgroup')!;
			expect(heading).toHaveAttribute('colspan', String(columns.length));
			const lines = [...heading.children];
			expect(lines.map((l) => l.textContent)).toEqual(
				[group.heading, group.lineup, group.detail].filter((t) => t !== null)
			);
			for (const l of lines) {
				expect(l).toHaveClass(
					'sticky',
					'left-0',
					'block',
					'w-[100cqw]',
					'wrap-break-word',
					'max-sm:static',
					'max-sm:w-auto'
				);
				// On screen, every word of it (S6 review MUT-03: a line made invisible failed nothing).
				expect(outOfSight(l), l.textContent!).toBe(false);
				expect(wordsInSight(l)).toBe(l.textContent);
			}
			const rows = within(body).getAllByRole('row');
			// The heading's row, a row per member, and a flag line after each flagged one's.
			expect(rows).toHaveLength(
				1 + group.rows.length + group.rows.filter((r) => r.flags.length).length
			);
			// Trace buttons in the shown case's group only: a trace opens for the case shown
			// (§5.3 Pump names), so another case's names are plain row headers.
			expect(within(body).queryAllByRole('button')).toHaveLength(
				group.shown ? group.rows.length : 0
			);
			for (const member of group.rows) {
				const row = rows.find((r) => within(r).queryByRole('rowheader', { name: member.name }))!;
				const header = within(row).getByRole('rowheader');
				if (group.shown) {
					const button = within(header).getByRole('button', { name: member.name });
					expect(button).toHaveClass('w-max', 'max-w-48', 'wrap-break-word', 'min-h-11');
					await fireEvent.click(button);
					expect(oninspect).toHaveBeenLastCalledWith(member.id);
				} else {
					expect(within(header).queryByRole('button')).toBeNull();
				}
				const next = row.nextElementSibling;
				if (!member.flags.length) {
					expect(next?.querySelector('[data-row-notes]') ?? null).toBeNull();
					plainRows++;
					continue;
				}
				flaggedRows++;
				// The flag line (§5.3 Flags), as the group table's: one cell across the row,
				// sticky at the box's visible width, named by its pump first (visually hidden),
				// then each flag's pill and its text, visible, read once; the flags a list, an
				// item each (no run of paragraphs where no trace button parts the rows, §5.7).
				const note = next!.querySelector<HTMLElement>(`[data-row-notes="${member.id}"]`)!;
				expect(note).toHaveAttribute('data-label', 'Flags');
				expect(note).toHaveClass('sticky', 'left-0', 'w-[100cqw]', 'max-sm:static');
				expect(note.closest('td')).toHaveAttribute('colspan', String(columns.length));
				expect(next).toHaveClass('max-sm:block');
				expect(note.querySelector('.sr-only')!.textContent).toBe(`${member.name}, flags:`);
				expect(squash(note.textContent).startsWith(`${member.name}, flags:`)).toBe(true);
				expect(note.querySelector('p')).toBeNull();
				const said = [...note.querySelectorAll(':scope > ul > li')];
				expect(said).toHaveLength(member.flags.length);
				for (const [i, flag] of member.flags.entries()) {
					const pill = said[i]!.querySelector('span')!;
					const word = { invalid: 'Invalid', warning: 'Warning', info: 'Info' }[flag.severity];
					expect(pill.textContent).toBe(word);
					expect(pill).toHaveClass(
						...{
							invalid: ['border-red-300', 'bg-red-50', 'text-red-900'],
							warning: ['border-amber-300', 'bg-amber-50', 'text-amber-900'],
							info: ['border-slate-300', 'bg-slate-50', 'text-slate-700']
						}[flag.severity]
					);
					expect(squash(said[i]!.textContent)).toBe(`${word} ${flagText(flag)}`);
					expect(outOfSight(said[i]!)).toBe(false);
					// Its text in sight, not only its item (§10 Flags: the flag text visible):
					// its own element, never hidden by any class variant, attribute or style.
					expect(squash(wordsInSight(said[i]!))).toBe(`${word} ${flagText(flag)}`);
					const text = said[i]!.querySelector('[data-flag-text]')!;
					expect(text.textContent).toBe(flagText(flag));
					expect(outOfSight(text)).toBe(false);
					expect(note.textContent!.split(flagText(flag))).toHaveLength(2);
				}
			}
		}
		// Both forms drawn: flagged pumps (Held's both, Pump PB off's Pump PA) and pumps without.
		expect([flaggedRows > 0, plainRows > 0]).toEqual([true, true]);
		expect(oninspect).toHaveBeenCalledTimes(table.groups[0]!.rows.length);
		// Without oninspect (this card's own tests), no trace button anywhere: the box's only
		// buttons are its column headings' sorts (a ResultsTable since S6b), none in a row.
		cleanup();
		render(PumpGroupChart, base({ combinations: table, flagText }));
		const boxed = within(boxOf('Running combinations')).queryAllByRole('button');
		expect(boxed.filter((b) => !b.closest('thead'))).toHaveLength(0);
		for (const b of boxed) expect(b.closest('th[role="columnheader"]')).not.toBeNull();
	});

	it('Running combinations with a scenario shown: the trace buttons in its group, first, and none in the base case’s (pumps-results-layout.md §5.3 Pump names, §10 S5)', async () => {
		const input = combinationsOf([
			solvedCase('S2', 'Pump PB off', c.scenarioCases.S2!.solve, { shown: true }),
			solvedCase('', 'Base case', c.solve, { shown: false }),
			solvedCase('S3', 'Delivery tank 5 m higher', c.scenarioCases.S3!.solve)
		]);
		const oninspect = vi.fn();
		render(PumpGroupChart, base({ combinations: runningCombinations(input), oninspect }));
		const combos = screen.getByRole('table', { name: 'Running combinations' });
		const groups = within(combos).getAllByRole('rowgroup').slice(1);
		const heading = (g: HTMLElement) =>
			within(g)
				.getAllByRole('rowheader')
				.find((h) => h.getAttribute('scope') === 'rowgroup')!.firstElementChild!.textContent;
		expect(groups.map(heading)).toEqual([
			'Pump PB off (shown)',
			'Base case',
			'Delivery tank 5 m higher'
		]);
		// The scenario shown: a button per member, each opening that pump's trace (for that case).
		expect(
			within(groups[0]!)
				.getAllByRole('button')
				.map((b) => b.textContent)
		).toEqual(['▲Pump PA', '■Pump PB']);
		await fireEvent.click(within(groups[0]!).getByRole('button', { name: 'Pump PB' }));
		expect(oninspect).toHaveBeenLastCalledWith('PB');
		// The base case not shown: plain row headers, as every other case's.
		for (const g of groups.slice(1)) {
			expect(within(g).queryAllByRole('button')).toEqual([]);
			expect(within(g).getAllByRole('rowheader', { name: 'Pump PA' })).toHaveLength(1);
		}
	});

	it('Running combinations: a stale group amber whole, in the table each cell and below 640 px its block, every line in it transparent (pumps-results-layout.md §5.3 Invalid and stale, §5.5; S5 review LAYOUT-3)', () => {
		const dead = named('one-off-dead-headed') as unknown as OneOffCase;
		const input = combinationsOf([
			solvedCase('', 'Base case', c.solve),
			solvedCase('S9', 'Held (synthetic)', dead.solve, { status: 'stale', stale: true })
		]);
		render(PumpGroupChart, base({ combinations: runningCombinations(input) }));
		const combos = screen.getByRole('table', { name: 'Running combinations' });
		const [current, stale] = within(combos).getAllByRole('rowgroup').slice(1);
		// The stale group's cells: its heading, names, values and flag lines.
		const cells = (g: HTMLElement) => [...g.querySelectorAll(':scope > tr > th, :scope > tr > td')];
		expect(stale!.querySelector('[data-row-notes]')).not.toBeNull();
		expect(stale).toHaveClass('max-sm:block', 'max-sm:bg-amber-50/60');
		for (const cell of cells(stale!)) {
			expect(cell.className).toMatch(/(^|\s)bg-amber-50(\/60)?(\s|$)/);
			expect(cell).toHaveClass('max-sm:bg-transparent');
		}
		// A current group: no amber anywhere, its block untinted.
		expect(current!.className).not.toMatch(/amber/);
		for (const cell of cells(current!)) expect(cell.className).not.toMatch(/amber/);
	});

	// ---- S6b: Running combinations a ResultsTable (§9 S6b; the owner's answer 3, §12) --------

	/** The base case shown, Pump PB off, Held (both pumps flagged) and a failed case. */
	const s6bInput = (shown = '') => {
		const dead = named('one-off-dead-headed') as unknown as OneOffCase;
		return combinationsOf([
			solvedCase('', 'Base case', c.solve, { shown: shown === '' }),
			solvedCase('S2', 'Pump PB off', c.scenarioCases.S2!.solve, { shown: shown === 'S2' }),
			solvedCase('S9', 'Held (synthetic)', dead.solve),
			solvedCase('S5', 'Failed case', null)
		]);
	};
	const squashed = (t: string | null | undefined) => (t ?? '').replace(/\s+/g, ' ').trim();
	const combosRegion = () => boxOf('Running combinations');
	const combosColumn = (name: RegExp) => within(combosRegion()).getByRole('columnheader', { name });
	/** Sort by a column from its heading (from 640 px; a phone's "Sort by" does the same). */
	const sortBy = (name: RegExp) => fireEvent.click(within(combosColumn(name)).getByRole('button'));
	/**
	 * The body as drawn: each row group, its heading's first line (null in the flat form) and its
	 * rows, each pump's as "{name} | {case, flat only} | {npsh margin}", each flag line as "flags
	 * of {id}" after the row it follows.
	 */
	const drawnGroups = () =>
		within(combosRegion())
			.getAllByRole('rowgroup')
			.slice(1)
			.map((g) => ({
				heading: g.querySelector('th[scope="rowgroup"]')?.firstElementChild?.textContent ?? null,
				rows: [...g.querySelectorAll(':scope > tr')]
					.filter((r) => !r.querySelector('th[scope="rowgroup"]'))
					.map((r) => {
						const name = r.querySelector('th[scope="row"] span.min-w-0');
						if (!name) {
							return `flags of ${r.querySelector('[data-row-notes]')!.getAttribute('data-row-notes')}`;
						}
						const kase = r.querySelector('td[data-label="Case"]');
						const margin = r.querySelector('td[data-label="NPSH margin (m)"]');
						return [
							squashed(name.textContent),
							kase && squashed(kase.textContent),
							squashed(margin?.textContent)
						]
							.filter((t) => t !== null)
							.join(' | ');
					})
			}));

	it('Running combinations: a sort by NPSH margin makes one flat table with a Case column, its first row the smallest margin; clearing the sort brings the case groups back in S5’s order (pumps-results-layout.md §9 S6b, §10 S6b)', async () => {
		const input = s6bInput();
		const table = runningCombinations(input);
		const flagText = (flag: Flag) => `${flag.code}: ${flag.message}`;
		render(PumpGroupChart, base({ combinations: table, flagText, oninspect: () => {} }));
		const before = drawnGroups();
		// Unsorted: a row group per case, in S5's order (the table's input order).
		expect(before.map((g) => g.heading)).toEqual(table.groups.map((g) => g.heading));
		expect(
			within(combosRegion())
				.getAllByRole('columnheader')
				.map((h) => squashed(h.textContent))
		).not.toContain('Case');
		await sortBy(/^NPSH margin/);
		expect(combosColumn(/^NPSH margin/)).toHaveAttribute('aria-sort', 'ascending');
		// One row group, the Case column after the pump's name.
		const flat = drawnGroups();
		expect(flat).toHaveLength(1);
		expect(flat[0]!.heading).toBeNull();
		const headings = within(combosRegion())
			.getAllByRole('columnheader')
			.map((h) => squashed(h.textContent));
		expect(headings.slice(0, 2)).toEqual(['Pump', 'Case']);
		expect(headings).toHaveLength(table.columns.length + 2);
		// Every member of every case with values, by its margin, those without one last in the
		// table's order; each flag line still under its own pump.
		const rows = table.groups.flatMap((g) =>
			g.rows.map((r) => ({
				name: r.name,
				case: g.heading,
				margin: r.cells.npshMargin!,
				flagged: r.flags.length > 0,
				id: r.id
			}))
		);
		const value = (m: string) => (m === '—' ? null : Number(m));
		const sorted = rows
			.map((r, i) => ({ ...r, i }))
			.sort((a, b) => {
				const [x, y] = [value(a.margin), value(b.margin)];
				if (x === null || y === null) return x === y ? a.i - b.i : x === null ? 1 : -1;
				return x - y || a.i - b.i;
			});
		expect(flat[0]!.rows).toEqual(
			sorted.flatMap((r) => [
				`${r.name} | ${r.case} | ${r.margin}`,
				...(r.flagged ? [`flags of ${r.id}`] : [])
			])
		);
		// Its first row the smallest margin of all: Pump PA with Pump PB off.
		const margins = rows.map((r) => value(r.margin)).filter((m): m is number => m !== null);
		expect(flat[0]!.rows[0]).toBe(
			`Pump PA | Pump PB off | ${table.groups[1]!.rows[0]!.cells.npshMargin}`
		);
		expect(Number(table.groups[1]!.rows[0]!.cells.npshMargin)).toBe(Math.min(...margins));
		// Each Case cell wraps at 12 rem, an unbroken name too, anywhere on a phone.
		for (const cell of combosRegion().querySelectorAll('td[data-label="Case"]')) {
			expect(cell.firstElementChild).toHaveClass(
				'w-max',
				'max-w-48',
				'wrap-break-word',
				'max-sm:wrap-anywhere'
			);
			expect(cell).not.toHaveClass('whitespace-nowrap');
			expect(cell.firstElementChild).not.toHaveClass('whitespace-nowrap');
		}
		// The flag lines span the row, the Case column with it.
		for (const notes of combosRegion().querySelectorAll('[data-row-notes]')) {
			expect(notes.closest('td')).toHaveAttribute('colspan', String(headings.length));
		}
		// Descending, then cleared: the case groups again, in S5's order, each as before.
		await sortBy(/^NPSH margin/);
		expect(combosColumn(/^NPSH margin/)).toHaveAttribute('aria-sort', 'descending');
		await sortBy(/^NPSH margin/);
		expect(combosColumn(/^NPSH margin/)).not.toHaveAttribute('aria-sort');
		expect(drawnGroups()).toEqual(before);
		expect(within(combosRegion()).queryByRole('columnheader', { name: 'Case' })).toBeNull();
	});

	it('Running combinations: Fields hides a column in both forms, every heading and flag line spanning what is shown (§9 S6b, §10 S6b)', async () => {
		const table = runningCombinations(s6bInput());
		render(PumpGroupChart, base({ combinations: table, oninspect: () => {} }));
		const section = screen.getByRole('heading', {
			name: 'Running combinations',
			level: 4
		}).parentElement!;
		await fireEvent.click(within(section).getByRole('button', { name: /^Fields/ }));
		const menu = screen.getByRole('group', { name: 'Fields shown in Running combinations' });
		// Every column a field, the name and the case never.
		expect(within(menu).getAllByRole('checkbox')).toHaveLength(table.columns.length);
		await fireEvent.click(within(menu).getByRole('checkbox', { name: /^Head/ }));
		const spans = () => {
			const n = within(combosRegion()).getAllByRole('columnheader').length;
			for (const th of combosRegion().querySelectorAll('th[scope="rowgroup"]')) {
				expect(th).toHaveAttribute('colspan', String(n));
			}
			for (const notes of combosRegion().querySelectorAll('[data-row-notes]')) {
				expect(notes.closest('td')).toHaveAttribute('colspan', String(n));
			}
			return n;
		};
		// Grouped: no Head heading or cell in any case.
		expect(within(combosRegion()).queryByRole('columnheader', { name: /^Head/ })).toBeNull();
		expect(combosRegion().querySelectorAll('td[data-label="Head (m)"]')).toHaveLength(0);
		expect(spans()).toBe(table.columns.length);
		expect(within(section).getByRole('button', { name: /^Fields/ })).toHaveTextContent(
			`(${table.columns.length - 1} of ${table.columns.length})`
		);
		// Flat: the same.
		await sortBy(/^Flow/);
		expect(within(combosRegion()).queryByRole('columnheader', { name: /^Head/ })).toBeNull();
		expect(combosRegion().querySelectorAll('td[data-label="Head (m)"]')).toHaveLength(0);
		expect(combosRegion().querySelectorAll('td[data-label="Flow (L/s)"]').length).toBeGreaterThan(
			0
		);
		expect(spans()).toBe(table.columns.length + 1);
		expect(localStorage.getItem('opensolve-pipe:results-fields:Running combinations')).toBe(
			'["head"]'
		);
		localStorage.clear();
	});

	it('Running combinations: Flagged only keeps the flagged rows with their flag lines in both forms, and the cases with one (§9 S6b, §10 S6b)', async () => {
		const table = runningCombinations(s6bInput());
		const flagText = (flag: Flag) => `${flag.code}: ${flag.message}`;
		render(PumpGroupChart, base({ combinations: table, flagText, oninspect: () => {} }));
		const all = table.groups.flatMap((g) => g.rows);
		const flagged = table.groups.flatMap((g) =>
			g.rows.filter((r) => r.flags.length).map((r) => ({ g, r }))
		);
		expect(flagged.length).toBeGreaterThan(0);
		expect(flagged.length).toBeLessThan(all.length);
		// Its count the rows drawn, every case's (lesson: a count agrees with what is beside it).
		const toggle = screen.getByRole('checkbox', {
			name: `Flagged only (${flagged.length} of ${all.length})`
		});
		expect(outOfSight(toggle.closest('label')!)).toBe(false);
		await fireEvent.click(toggle);
		const grouped = drawnGroups();
		expect(grouped.map((g) => g.heading)).toEqual(
			table.groups.filter((g) => g.rows.some((r) => r.flags.length)).map((g) => g.heading)
		);
		expect(grouped.flatMap((g) => g.rows)).toEqual(
			flagged.flatMap(({ r }) => [`${r.name} | ${r.cells.npshMargin}`, `flags of ${r.id}`])
		);
		const sentences = () => {
			const said = [...combosRegion().querySelectorAll('[data-flag-text]')];
			for (const text of said) {
				expect(outOfSight(text)).toBe(false);
				expect(text.textContent).not.toBe('');
			}
			return said.length;
		};
		const count = flagged.reduce((n, { r }) => n + r.flags.length, 0);
		expect(sentences()).toBe(count);
		// Flat: the same rows, each with its flag line.
		await sortBy(/^Flow/);
		const flat = drawnGroups();
		expect(flat).toHaveLength(1);
		expect(flat[0]!.rows.filter((r) => r.startsWith('flags of'))).toHaveLength(flagged.length);
		expect(flat[0]!.rows.filter((r) => !r.startsWith('flags of'))).toHaveLength(flagged.length);
		for (const [i, row] of flat[0]!.rows.entries()) {
			if (!row.startsWith('flags of')) expect(flat[0]!.rows[i + 1]).toMatch(/^flags of /);
		}
		expect(sentences()).toBe(count);
		await fireEvent.click(toggle);
		expect(drawnGroups()[0]!.rows.filter((r) => !r.startsWith('flags of'))).toHaveLength(
			all.length
		);
	});

	it('Running combinations: trace buttons in the shown case’s rows only, in both forms, a scenario shown (§5.3 Pump names, §9 S6b; S5 review MUT-02)', async () => {
		const table = runningCombinations(s6bInput('S2'));
		const oninspect = vi.fn();
		render(PumpGroupChart, base({ combinations: table, oninspect }));
		const shown = table.groups.find((g) => g.shown)!;
		expect(shown.heading).toBe('Pump PB off (shown)');
		const traced = () =>
			[...combosRegion().querySelectorAll<HTMLElement>('tbody tr')].filter((r) =>
				r.querySelector('th[scope="row"] button')
			);
		// Grouped: the buttons in its group alone, one per member.
		const groups = within(combosRegion()).getAllByRole('rowgroup').slice(1);
		for (const g of groups) {
			const isShown =
				g.querySelector('th[scope="rowgroup"]')!.firstElementChild!.textContent === shown.heading;
			expect(within(g).queryAllByRole('button')).toHaveLength(isShown ? shown.rows.length : 0);
		}
		// Flat: the rows whose Case is the shown case's, and only they.
		await sortBy(/^Flow/);
		const rows = [...combosRegion().querySelectorAll('tbody tr')].filter((r) =>
			r.querySelector('th[scope="row"]')
		);
		expect(rows.length).toBe(table.groups.reduce((n, g) => n + g.rows.length, 0));
		for (const r of rows) {
			const kase = squashed(r.querySelector('td[data-label="Case"]')!.textContent);
			expect(!!r.querySelector('th[scope="row"] button'), kase).toBe(kase === shown.heading);
		}
		expect(traced()).toHaveLength(shown.rows.length);
		// Each opens its own pump's trace (for the case shown).
		const pb = traced().find(
			(r) => squashed(r.querySelector('th span.min-w-0')!.textContent) === 'Pump PB'
		)!;
		await fireEvent.click(within(pb).getByRole('button', { name: 'Pump PB' }));
		expect(oninspect).toHaveBeenLastCalledWith('PB');
	});

	it('Running combinations: its heading lines unfilled, so the box’s sideways shadow runs past them, the names at one edge after their slot symbols (§9 S6b; §15 item 157)', () => {
		const table = runningCombinations(s6bInput());
		render(PumpGroupChart, base({ combinations: table, oninspect: () => {} }));
		expect(combosRegion()).toHaveClass('scroll-shadow-x', '@container');
		const headings = [...combosRegion().querySelectorAll('th[scope="rowgroup"]')];
		expect(headings).toHaveLength(table.groups.length);
		for (const th of headings) {
			// A current case's heading: no fill over the box's shadow (a stale one is amber, §5.3).
			expect(th.className).not.toMatch(/(^|\s)bg-/);
			for (const line of th.children) expect(line.className).not.toMatch(/(^|\s)bg-/);
		}
		// Every slot symbol in a 1 rem column of its own, so every name starts at one edge.
		const symbols = [...combosRegion().querySelectorAll('th[scope="row"] [aria-hidden="true"]')];
		expect(symbols.length).toBe(table.groups.reduce((n, g) => n + g.rows.length, 0));
		for (const symbol of symbols) expect(symbol).toHaveClass('w-4', 'shrink-0', 'text-center');
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
			/; other cases' station duties: 1 · Pump PA off, [\d.]+ L\/s at a rise of [\d.]+ m \(Yes: the same rest of the network\); 2 · Pump PB off, .*; 4 · Both pumps off, 0 L\/s at a rise of 19 m \(Not said: at zero station flow the rest can hold more than one state\); group curve shown; group system curve shown\.$/
		);
		await drawn();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
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
		expect(within(screen.getByRole('figure')).getByRole('img')).toHaveAttribute(
			'aria-busy',
			'true'
		);
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
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
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
		// Below 640 px a list (pumps-results-layout.md §5.5, §9 S5), as "Other cases' group
		// curves": the roles explicit, the header row visually hidden, a block per case headed by
		// its name (wrapping anywhere), each value after its column's words as ::before content,
		// so a cell's text is the same at every width; a case without a ring its words alone.
		expect(table).toHaveAttribute('role', 'table');
		expect(table).toHaveClass('max-sm:block');
		expect(table.querySelector('thead')).toHaveClass('max-sm:sr-only');
		const headers = within(table)
			.getAllByRole('columnheader')
			.map((h) => h.textContent!.replace(/\s+/g, ' ').trim());
		let ringed = 0;
		for (const row of within(table).getAllByRole('row').slice(1)) {
			expect(row).toHaveClass('max-sm:flex', 'max-sm:flex-wrap');
			expect(within(row).getByRole('rowheader')).toHaveClass(
				'max-sm:block',
				'max-sm:w-full',
				'max-sm:wrap-anywhere'
			);
			const cells = within(row).getAllByRole('cell');
			if (cells.length === 1) {
				expect(cells[0]).not.toHaveAttribute('data-label');
				expect(cells[0]).toHaveClass('max-sm:block');
				continue;
			}
			ringed++;
			expect(cells.map((cell) => cell.dataset.label)).toEqual(headers.slice(1));
			// A number beside its column's words, a pair; a cell of words the whole line, its
			// column's words and a space before them in the same run of text, so its accessible
			// name never runs the two together (S5 review LAYOUT-1).
			for (const [i, cell] of cells.entries()) {
				expect(cell).toHaveClass(
					i < 2
						? 'max-sm:before:content-[attr(data-label)]'
						: "max-sm:before:content-[attr(data-label)_'_']"
				);
				expect(cell).toHaveClass(i < 2 ? 'max-sm:flex' : 'max-sm:block');
				if (i >= 2) expect(cell).toHaveClass('max-sm:w-full');
				// Its words the list's value style, as a number's, apart from its column's words
				// (12 px slate-600): 14 px slate-900 (S5 review LAYOUT-1).
				if (i >= 2) expect(cell).toHaveClass('max-sm:text-sm', 'max-sm:text-slate-900');
				expect(cell.textContent).not.toContain(cell.dataset.label);
			}
		}
		expect(ringed).toBe(6);
		// 4d's table, without curve states: no such column. The data table still shown: remembered
		// in this browser (§9 S7).
		cleanup();
		await renderDrawn(family('', { without: true }).props);
		expect(
			screen.getByRole('button', { name: 'Hide data table of the group chart' })
		).toHaveAttribute('aria-expanded', 'true');
		expect(
			within(screen.getByRole('table', { name: "Other cases' station duties" })).queryByRole(
				'columnheader',
				{ name: 'Its group curve' }
			)
		).toBeNull();
		expect(screen.queryByRole('table', { name: OTHER_CURVES_CAPTION })).toBeNull();
	});

	it('folds “Other cases’ group curves” into a disclosure counting every point of every case’s curve, closed while the chart is drawn (pumps-results-layout.md §9 S7)', async () => {
		const { view, props } = family();
		await renderDrawn(props);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		const details = disclosureOf(OTHER_CURVES_CAPTION);
		expect(details.open).toBe(false);
		// Every point of each curve drawn, the cases' own responses' (D24 §9.6).
		const drawnCurves = view.others.filter(
			(o) => o.onChart && o.state === 'ready' && o.curve && o.number !== null
		);
		expect(drawnCurves.length).toBeGreaterThan(1);
		const points = drawnCurves.reduce((n, o) => n + o.curve!.points.length, 0);
		expect(
			details.querySelector(':scope > summary')!.textContent!.replace(/\s+/g, ' ').trim()
		).toBe(`${OTHER_CURVES_CAPTION} (${points} points)`);
		// The count is the rows of values it lists, the cases' header rows apart.
		expect(details.querySelectorAll('tbody tr:not(:has(th[scope="rowgroup"]))')).toHaveLength(
			points
		);
		// Its words in sight, the count with them (S7 review W2, MUT-SUMMARY-HIDDEN).
		expect(
			wordsInSight(details.querySelector(':scope > summary')!).replace(/\s+/g, ' ').trim()
		).toBe(`${OTHER_CURVES_CAPTION} (${points} points)`);
	});

	it('opens every curve table by default where the chart cannot be drawn, “Other cases’ group curves” too (§9 S7; S7 review MUT-OTHERCURVES-DEFAULT)', async () => {
		HTMLCanvasElement.prototype.getContext = (() => null) as unknown as typeof getContext;
		render(PumpGroupChart, family().props);
		await vi.waitFor(
			() => expect(screen.getByText(/The chart cannot be drawn in this browser/)).toBeVisible(),
			{ timeout: 10_000 }
		);
		const folds = [...document.querySelectorAll<HTMLDetailsElement>('details[data-curve-table]')];
		expect(folds.map((d) => [d.dataset.curveTable, d.open])).toEqual([
			['group-curve', true],
			['group-system', true],
			['other-curves', true]
		]);
	});

	it('keeps the user’s opening of “Other cases’ group curves” while the data region is hidden and shown (S7 review MUT-BIND)', async () => {
		await renderDrawn(family().props);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		await openTable(OTHER_CURVES_CAPTION);
		await new Promise((resolve) => setTimeout(resolve, 0)); // the toggle event's task
		await fireEvent.click(
			screen.getByRole('button', { name: 'Hide data table of the group chart' })
		);
		expect(screen.queryByRole('table', { name: OTHER_CURVES_CAPTION })).toBeNull();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		expect(disclosureOf(OTHER_CURVES_CAPTION).open).toBe(true);
	});

	it('gives every box of the group data region its sideways shadows, and makes “Other cases’ station duties” a Tab stop and a named region only while it overflows (§5.3, §9 S7; S7 review LAYOUT-3, MUT-DUTIES-REGION)', async () => {
		await renderDrawn(family().props);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		const data = document.querySelector<HTMLElement>('[data-group-data]')!;
		const boxes = [...data.querySelectorAll('table')].map((t) => t.parentElement!);
		expect(
			boxes.map((b) =>
				b.querySelector(':scope > table > caption')!.textContent!.replace(/\s+/g, ' ').trim()
			)
		).toEqual([
			"Each pump's point (flow through it)",
			"Group curve (station's flow at each rise)",
			"Group system curve (rise the rest of the network needs at each station's flow)",
			"Other cases' station duties",
			OTHER_CURVES_CAPTION
		]);
		for (const box of boxes) expect(box).toHaveClass('scroll-shadow-x', 'relative');
		// The duties' box: wider than it holds (a long case name in its Case column), a region and a
		// Tab stop; given room, neither.
		const duties = boxOf("Other cases' station duties");
		expect(duties).toBe(boxes[3]);
		sizeBox(duties, { clientWidth: 452, scrollWidth: 452, clientHeight: 300, scrollHeight: 300 });
		observers.resize(duties);
		expect(duties).not.toHaveAttribute('tabindex');
		expect(within(data).queryByRole('region', { name: "Other cases' station duties" })).toBeNull();
		overflowSideways(duties);
		expect(within(data).getByRole('region', { name: "Other cases' station duties" })).toBe(duties);
		expect(duties).toHaveAttribute('tabindex', '0');
		sizeBox(duties, { clientWidth: 900 });
		observers.resize(duties);
		expect(duties).not.toHaveAttribute('tabindex');
		expect(duties).not.toHaveAttribute('role');
	});

	it('lists every point of each curve drawn in "Other cases’ group curves": a row group per case, a list below 640 px', async () => {
		const { view, props } = family('', { stale: ['S1'] });
		await renderDrawn(props);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		// A curve table in its disclosure, closed until opened, full height (§9 S7): no box that
		// scrolls down inside the pane; a region and a Tab stop only while it overflows.
		const table = await openTable(OTHER_CURVES_CAPTION);
		const region = table.parentElement!;
		expect(region).toHaveClass('overflow-x-auto');
		expect(region).not.toHaveClass('max-h-72');
		expect(region).not.toHaveAttribute('tabindex');
		overflowSideways(region);
		expect(screen.getByRole('region', { name: OTHER_CURVES_CAPTION })).toBe(region);
		expect(region).toHaveAttribute('tabindex', '0');
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

	it('the rings on screen: the clip note, “How to read the rings” closed before the list, the list named by its lead, one line per ring (pumps-results-layout.md §5.3, S3)', async () => {
		const follows = (a: Node, b: Node) =>
			!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		await renderDrawn(family().props);
		const section = document.querySelector<HTMLElement>('[data-group-others]')!;
		// Visible: the clip note, what is drawn is not every point.
		const clip = within(section).getByText(
			"The group system curve is cut at the top, above every pump's head; the data tables list all their points."
		);
		expect(clip.tagName).toBe('P');
		expect(outOfSight(clip)).toBe(false);
		// The notes come after the other cases' live line and its buttons, never above them, so
		// the progress and "Compute them again" stay by their switch (§5.3, §7 Tab order; S3 review
		// MUT-07); the chain below holds the rest of their order.
		expect(follows(section.querySelector('[data-group-others-row]')!, clip)).toBe(true);
		// One step away: the frame and the rule, closed, after the clip note and before the list.
		const how = section.querySelector<HTMLDetailsElement>('[data-group-rings-how]')!;
		expect(how.open).toBe(false);
		expect(follows(clip, how)).toBe(true);
		expect(how.querySelector('summary')!.textContent!.replace(/\s+/g, ' ').trim()).toBe(
			'How to read the rings: what a ring is, which curve it lies on, when it is called a point of the group system curve'
		);
		const [frameNote, rule] = [...how.querySelectorAll('p')];
		// The frame's family form ends "The list below says, for each ring, which." (§5.3): the
		// list comes after it.
		expect(frameNote!.textContent).toMatch(/The list below says, for each ring, which\.$/);
		expect(rule!.textContent).toBe(DUTY_CLAIM_RULE);
		expect(outOfSight(frameNote!)).toBe(true);
		const lead = within(section).getByText('Other cases on the chart (slate rings, numbered):');
		const ringList = within(section).getByRole('list', {
			name: 'Other cases on the chart (slate rings, numbered):'
		});
		expect(ringList).toHaveAttribute('aria-labelledby', lead.id);
		expect(follows(how, lead)).toBe(true);
		expect(follows(lead, ringList)).toBe(true);
		// One line per ring, in number order: the glyph and number in a reserved column, the
		// case's name in medium weight, the rest regular.
		const items = within(ringList).getAllByRole('listitem');
		const keys = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'] as const;
		expect(items).toHaveLength(keys.length);
		const text = (li: Element) => {
			const copy = li.cloneNode(true) as Element;
			for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
			return copy.textContent!.replace(/\s+/g, ' ').trim();
		};
		for (const [i, li] of items.entries()) {
			const column = li.firstElementChild!;
			expect(column).toHaveClass('w-9', 'shrink-0');
			const glyph = column.querySelector('[aria-hidden="true"]')!;
			expect(glyph.textContent).toBe('○');
			expect(glyph).toHaveStyle({ color: GROUP_OTHER });
			expect(column.textContent!.replace(/\s+/g, ' ').trim()).toBe(`○ ${i + 1} ·`);
			const name = li.querySelector('.font-medium')!;
			expect(name).toHaveClass('text-slate-900');
			expect(name.textContent).toBe(NAMES[keys[i]!]);
			// Its words wrap, never cut with an ellipsis (S3 review MUT-08).
			expect(name.parentElement).toHaveClass('min-w-0', 'wrap-break-word');
			expect(name.parentElement).not.toHaveClass('truncate');
			expect(text(li)).toMatch(
				new RegExp(
					`^${i + 1} · ${NAMES[keys[i]!]!.replace(/[()]/g, '\\$&')}, [\\d.]+ L/s at a rise of [\\d.]+ m: Yes: the same rest of the network; group curve: drawn \\(\\d running\\): it crosses the group system curve at the ring$`
				)
			);
			expect(outOfSight(li)).toBe(false);
		}
		const notOn = within(section).getByText(/^Not on the chart: /);
		expect(follows(ringList, notOn)).toBe(true);
		expect(outOfSight(notOn)).toBe(false);
		// Each line's text without its glyph is its part's (groupNotes' otherParts, §10).
		const { view } = family();
		const { groupCurve, systemCurve } = lineupAnswers('');
		const parts = groupNotes({
			data: view.data,
			members: view.members,
			state: readyState(groupCurve),
			system: readyState(systemCurve),
			project: lineups.project,
			prefs: lineupPrefs,
			others: view.others
		}).otherParts;
		expect(items.map(text)).toEqual(parts.rings!.items.map((item) => item.text));
		expect(lead.textContent).toBe(parts.rings!.lead);
		expect(clip.textContent).toBe(parts.clip);
		expect([frameNote!.textContent, rule!.textContent]).toEqual([parts.frame, parts.claim]);
		// The image's footer: the frame, the clip note, the rule and the ring list as one
		// sentence, its entries the lines' texts joined (§6.3: the image keeps its words).
		await vi.waitFor(() =>
			expect(
				screen.getByRole('button', { name: /^Download image of the pumps together/ })
			).not.toHaveAttribute('aria-disabled', 'true')
		);
		await fireEvent.click(
			screen.getByRole('button', { name: /^Download image of the pumps together/ })
		);
		await vi.waitFor(() => expect(images.requests).toHaveLength(1));
		const lines = (images.requests[0] as FigureImageRequest).lines;
		const at = lines.indexOf(frameNote!.textContent!);
		expect(lines.slice(at, at + 5)).toEqual([
			frameNote!.textContent,
			clip.textContent,
			DUTY_CLAIM_RULE,
			`${lead.textContent} ${items.map(text).join('; ')}.`,
			notOn.textContent
		]);
		// The data region: the other cases' tables after the shown case's, their curves last.
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		const captions = [...document.querySelectorAll('[data-group-data] caption')].map((c) =>
			c.textContent!.trim()
		);
		expect(captions.slice(-2)).toEqual(["Other cases' station duties", OTHER_CURVES_CAPTION]);
		expect(captions.indexOf("Group curve (station's flow at each rise)")).toBe(1);
	}, 20_000);

	it('every footer line on screen with the curve family: each clip clause, the left-out count, a stale case (pumps-results-layout.md §10, S3)', async () => {
		for (const [shown, options] of [
			['', {}],
			['S2', {}],
			['S3', {}],
			['', { unticked: ['S4', 'S5'], stale: ['S1'] }]
		] as const) {
			cleanup();
			const before = charts.length;
			render(PumpGroupChart, family(shown, options).props);
			await vi.waitFor(() => expect(charts).toHaveLength(before + 1), { timeout: 10_000 });
			// "1 of 4 running" shown, drawn narrow: some labels left out, and the notes count them.
			if (shown === 'S3') {
				drawnChart(charts.at(-1)!.config as PumpChartConfig).draw();
				await screen.findByText(/are left out for space; the data table lists every curve\.$/);
			}
			const lines = await footerLines();
			const inside = footerOnScreen(lines);
			const where = `${shown || 'Base case'} shown`;
			// Inside "How to read the rings": the frame (L3's form) and the rule, nothing else of theirs.
			expect(
				inside.filter((l) => /^Each numbered slate ring/.test(l)),
				where
			).toHaveLength(1);
			expect(inside, where).toContain(DUTY_CLAIM_RULE);
			// In sight: the clip note, "Not on the chart", the left-out count, each ring's claim.
			const qualifying = lines.filter((l) =>
				/(are cut at|^Not on the chart: |left out for space)/.test(l)
			);
			expect(qualifying.length, where).toBeGreaterThan(0);
			for (const line of qualifying) expect(inside, `${where}: ${line}`).not.toContain(line);
			if (shown === 'S3')
				expect(qualifying.some((l) => l.includes('left out for space'))).toBe(true);
		}
	}, 30_000);

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

describe('every footer line of the group chart on screen, word for word (pumps-results-layout.md §10, S3)', () => {
	it('reads only the words in sight, and a disclosure only where the reference is', async () => {
		const c = named('parallel-crane');
		render(PumpGroupChart, props(c, { system: systemReady(c), image: image() }));
		await drawn();
		const lines = await footerLines();
		// A line hidden inside a visible one is off screen, and not in a disclosure: the guard fails.
		const note = screen.getByText(/^Pump curves and points are at each pump's flanges\./);
		note.classList.add('max-sm:sr-only');
		expect(() => footerOnScreen(lines)).toThrow();
		note.classList.remove('max-sm:sr-only');
		const how = document.querySelector<HTMLDetailsElement>('[data-group-reading]')!;
		// "How to read this chart" holds the axes, the group system curve's and the own curves' notes.
		expect(footerOnScreen(lines).sort()).toEqual(
			[...how.querySelectorAll('p')].map((p) => p.textContent!).sort()
		);
	});

	const fixtureCase = (name: string) => named(name);
	const disagreeing = () => {
		const c = named('parallel-crane');
		const group = structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
		Object.assign(group.dutyCheck!, {
			agrees: false,
			flow: group.duty!.flow * 1.1,
			message: 'made-up server words'
		});
		const system = structuredClone(c.systemCurve!.body as PumpGroupCurveResponse);
		Object.assign(system.systemDutyCheck!, {
			agrees: false,
			head: system.duty!.head + 2,
			message: 'made-up server words'
		});
		return props(c, {
			curve: { status: 'ready', response: group },
			system: { status: 'ready', response: system }
		});
	};
	const notKnown = () => {
		const c = named('parallel-ideal');
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
				reason: 'not_computed',
				message: "not computed: the request's 45 s budget ran out",
				members: []
			}
		);
		return props(c, { curve: { status: 'ready', response } });
	};
	const refusedOf = (name: string, system = false) => {
		const c = named(name);
		const body = c.groupCurve.body as { message: string; issues: TopologyIssue[] };
		return props(c, {
			curve: { status: 'refused', message: body.message, issues: body.issues },
			...(system ? { system: systemReady(c) } : {}),
			oninspect: () => {}
		});
	};
	const states: {
		name: string;
		props: () => ReturnType<typeof props>;
		/** Lines the state must give, so the guard is known to read them, each visible. */
		covers: RegExp[];
	}[] = [
		{
			name: 'both curves, the checks agreeing (parallel-crane)',
			props: () =>
				props(fixtureCase('parallel-crane'), { system: systemReady(named('parallel-crane')) }),
			covers: [/^At the duty's rise the group curve gives/, /^Pump curves and points are at/]
		},
		{
			name: 'group-system-curve points without a rise (fcv-outside)',
			props: () => props(fixtureCase('fcv-outside'), { system: systemReady(named('fcv-outside')) }),
			covers: [/group-system-curve points have no rise/]
		},
		{
			name: 'both checks disagreeing (synthetic)',
			props: disagreeing,
			covers: [
				/^The group curve does not pass through the Group point:/,
				/^The group system curve does not pass through the Group point:/,
				/^Several steady states can exist/
			]
		},
		{
			name: 'the duty check not known (synthetic)',
			props: notKnown,
			covers: [/^The group curve's point at the duty's rise was not computed/]
		},
		{
			name: 'not a station (refused)',
			props: () => refusedOf('refused'),
			covers: [/^These pumps do not form a station/]
		},
		{
			name: 'the group curve not defined for a PRV inside, its group system curve drawn',
			props: () => refusedOf('prv-inside', true),
			covers: [/^These pumps form a station, but its group curve is not defined there/]
		},
		{
			name: 'the group curve failed, the group system curve cancelled',
			props: () =>
				props(fixtureCase('parallel-ideal'), {
					curve: { status: 'error', message: 'Made-up message.' },
					system: { status: 'cancelled', by: 'user' }
				}),
			covers: [/^The group curve could not be computed: Made-up message\.$/]
		},
		{
			name: 'in series, the piping between the pumps',
			props: () => props(fixtureCase('series'), { system: systemReady(named('series')) }),
			covers: [/the piping between the pumps loses/]
		},
		{
			name: 'no duty in this case',
			props: () => props(fixtureCase('no-duty')),
			covers: [/^No group curve for this case: /]
		},
		{
			name: 'one member ticked',
			props: () => props(fixtureCase('parallel-ideal'), { slots: ['PA'], curve: undefined }),
			covers: [/^Tick two pumps or more to compute their group curve\.$/]
		}
	];
	for (const state of states) {
		it(state.name, async () => {
			render(PumpGroupChart, { ...state.props(), image: image() });
			await drawn();
			const lines = await footerLines();
			for (const pattern of state.covers) {
				expect(
					lines.some((line) => pattern.test(line)),
					String(pattern)
				).toBe(true);
			}
			const inside = footerOnScreen(lines);
			// What qualifies the reading is never one step away (§5.3, §10): the checks, the
			// coverage, the refusal and the frame of the members are in sight.
			for (const pattern of state.covers) {
				expect(
					inside.some((line) => pattern.test(line)),
					String(pattern)
				).toBe(false);
			}
		});
	}
});

describe('the group table a ResultsTable (pumps-results-layout.md §5.3 Station, §9 S6a)', () => {
	afterEach(() => localStorage.clear());
	const squash = (text: string | null) => (text ?? '').replace(/\s+/g, ' ').trim();
	/** The table's box (a region only while it overflows, §9 S7). */
	const region = (name = 'The pumps in the group') => boxOf(name);
	/** The table's body rows: each pump by its name, each flag line as "flags of {id}". */
	const order = (name?: string) =>
		within(within(region(name)).getAllByRole('rowgroup')[1]!)
			.getAllByRole('row')
			.map((r) => {
				const header = within(r).queryByRole('rowheader');
				// The name's own span: its slot symbol (aria-hidden) before it.
				if (header) return squash(header.querySelector('span.min-w-0')!.textContent);
				return `flags of ${r.querySelector('[data-row-notes]')!.getAttribute('data-row-notes')}`;
			});
	const heading = (name: RegExp) => within(region()).getByRole('columnheader', { name });

	it('its title visible, naming its box (a region and a Tab stop) and its table; FlagLine, not FlagBadge', () => {
		const c = named('ladder');
		render(PumpGroupChart, props(c, { oninspect: () => {} }));
		const station = screen.getByRole('heading', { name: 'Station', level: 4 }).parentElement!;
		const title = within(station).getByText('The pumps in the group', { selector: 'p' });
		expect(title.tagName).toBe('P');
		expect(outOfSight(title)).toBe(false);
		// A region named by the title, and a Tab stop, while it overflows (§9 S7).
		overflowSideways(region());
		expect(screen.getByRole('region', { name: 'The pumps in the group' })).toBe(region());
		expect(region()).toHaveAttribute('aria-labelledby', title.id);
		expect(region()).toHaveAttribute('tabindex', '0');
		expect(within(region()).getByRole('table', { name: 'The pumps in the group' })).toBeVisible();
		// The title before the controls, the controls before the box.
		const fields = within(station).getByRole('button', { name: /^Fields/ });
		expect(title.compareDocumentPosition(fields) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(
			fields.compareDocumentPosition(region()) & Node.DOCUMENT_POSITION_FOLLOWING
		).toBeTruthy();
		// The pills drawn by FlagLine: no FlagBadge's tooltip or hidden copy of a flag's words.
		for (const line of region().querySelectorAll('[data-row-notes]')) {
			expect(line.querySelector('[title]')).toBeNull();
			expect([...line.querySelectorAll('.sr-only')].map((e) => e.textContent)).toEqual([
				`${squash(line.closest('tr')!.previousElementSibling!.querySelector('th span.min-w-0')!.textContent)}, flags:`
			]);
		}
		// Every slot symbol in a 1 rem column of its own, so every name starts at one edge, as in
		// Running combinations (§15 item 157; S6 review MUT-04).
		const symbols = [...region().querySelectorAll('th[scope="row"] [aria-hidden="true"]')];
		expect(symbols).toHaveLength(3);
		for (const symbol of symbols) expect(symbol).toHaveClass('w-4', 'shrink-0', 'text-center');
		// Each name its slot symbol (aria-hidden) and its trace button, wrapping at 12 rem.
		const header = within(region()).getByRole('rowheader', { name: 'Pump P2' });
		const button = within(header).getByRole('button', { name: 'Pump P2' });
		expect(button).toHaveClass('w-max', 'max-w-48', 'wrap-break-word', 'max-sm:wrap-anywhere');
		expect(button.querySelector('[aria-hidden="true"]')!.textContent).not.toBe('');
		expect(header).not.toHaveClass('sm:min-w-[11rem]');
	});

	it('sorts by any column from its heading, ascending, descending, then the table’s order, each flag line under its pump', async () => {
		const c = named('ladder');
		render(PumpGroupChart, props(c, { oninspect: () => {} }));
		const original = order();
		expect(original).toEqual(['Pump P1', 'Pump P2', 'flags of P2', 'Pump P3', 'flags of P3']);
		// The headings keep their names, a sort button inside each.
		const flow = heading(/^Flow/);
		expect(squash(flow.textContent)).toBe('Flow L/s');
		await fireEvent.click(within(flow).getByRole('button', { name: 'Flow L/s' }));
		expect(flow).toHaveAttribute('aria-sort', 'ascending');
		// The fixture's flows: P3 16.34, P2 30.47, P1 52.66 L/s.
		expect(order()).toEqual(['Pump P3', 'flags of P3', 'Pump P2', 'flags of P2', 'Pump P1']);
		await fireEvent.click(within(flow).getByRole('button'));
		expect(flow).toHaveAttribute('aria-sort', 'descending');
		expect(order()).toEqual(['Pump P1', 'Pump P2', 'flags of P2', 'Pump P3', 'flags of P3']);
		await fireEvent.click(within(flow).getByRole('button'));
		expect(flow).not.toHaveAttribute('aria-sort');
		expect(order()).toEqual(original);
		// By name, from the first column's heading.
		const pump = heading(/^Pump$/);
		await fireEvent.click(within(pump).getByRole('button', { name: 'Pump' }));
		await fireEvent.click(within(pump).getByRole('button', { name: 'Pump' }));
		expect(pump).toHaveAttribute('aria-sort', 'descending');
		expect(order()).toEqual(['Pump P3', 'flags of P3', 'Pump P2', 'flags of P2', 'Pump P1']);
		// A phone's "Sort by" (the same sort): every column, its unit named.
		const field = within(
			screen.getByRole('heading', { name: 'Station', level: 4 }).parentElement!
		).getByRole('combobox', { name: 'Sort by, The pumps in the group' });
		expect([...(field as HTMLSelectElement).options].map((o) => o.text)).toEqual(
			expect.arrayContaining(['Table order', 'Pump', 'State', 'Flow (L/s)', 'Share (%)'])
		);
		await fireEvent.change(field, { target: { value: 'flow' } });
		expect(flow).toHaveAttribute('aria-sort', 'ascending');
		expect(order()).toEqual(['Pump P3', 'flags of P3', 'Pump P2', 'flags of P2', 'Pump P1']);
	});

	it('sorts Shutoff head by its values, a controlled pump’s “at maximum speed” note after its value (S6 review TBL-3)', async () => {
		// The controlled station, its pump under control at 73.68 ft, the fixed one's shutoff head
		// set to 73.7 ft (22.46376 m, synthetic): their integer parts tie, so a sort of the cells
		// as text would put 73.68 last (68 > 7).
		const c = named('controlled');
		const pumps = pumpsOf(c).map((m) =>
			m.result.control
				? m
				: {
						...m,
						result: { ...m.result, shutoffHead: { ...m.result.shutoffHead, head: 22.46376 } }
					}
		);
		render(PumpGroupChart, props(c, { pumps, oninspect: () => {} }));
		const shutoff = heading(/^Shutoff head/);
		const cells = () =>
			[...region().querySelectorAll('td[data-label^="Shutoff head"]')].map((td) =>
				squash(td.textContent)
			);
		expect(cells()).toEqual(['73.7', '73.68 (79.72 at maximum speed)']);
		const values = () => cells().map((t) => Number(t.split(' ')[0]));
		await fireEvent.click(within(shutoff).getByRole('button'));
		expect(shutoff).toHaveAttribute('aria-sort', 'ascending');
		expect(values()).toEqual([73.68, 73.7]);
		await fireEvent.click(within(shutoff).getByRole('button'));
		expect(shutoff).toHaveAttribute('aria-sort', 'descending');
		expect(values()).toEqual([73.7, 73.68]);
	});

	it('Flagged only keeps each flagged pump with its flag line, and gives every pump back', async () => {
		const c = named('ladder');
		render(PumpGroupChart, props(c, { oninspect: () => {} }));
		const toggle = screen.getByRole('checkbox', { name: 'Flagged only (2 of 3)' });
		expect(outOfSight(toggle.closest('label')!)).toBe(false);
		await fireEvent.click(toggle);
		expect(order()).toEqual(['Pump P2', 'flags of P2', 'Pump P3', 'flags of P3']);
		for (const id of ['P2', 'P3']) {
			const line = region().querySelector(`[data-row-notes="${id}"]`)!;
			expect(line).toHaveAttribute('data-label', 'Flags');
			for (const sentence of line.querySelectorAll('[data-flag-text]')) {
				expect(outOfSight(sentence)).toBe(false);
				expect(sentence.textContent).not.toBe('');
			}
		}
		await fireEvent.click(toggle);
		expect(order()).toEqual(['Pump P1', 'Pump P2', 'flags of P2', 'Pump P3', 'flags of P3']);
		// Not offered where every pump has a flag (nothing to filter) or none has.
		cleanup();
		render(PumpGroupChart, props(named('parallel-crane'), { oninspect: () => {} }));
		expect(screen.queryByRole('checkbox', { name: /^Flagged only/ })).toBeNull();
	});

	it('Fields hides a column, remembered for the group table whatever the case shown', async () => {
		const c = named('ladder');
		const view = render(PumpGroupChart, props(c, { oninspect: () => {} }));
		await fireEvent.click(screen.getByRole('button', { name: /^Fields/ }));
		const menu = screen.getByRole('group', { name: 'Fields shown in The pumps in the group' });
		await fireEvent.click(within(menu).getByRole('checkbox', { name: /^Shaft power/ }));
		expect(within(region()).queryByRole('columnheader', { name: /^Shaft power/ })).toBeNull();
		expect(screen.getByRole('button', { name: /^Fields/ })).toHaveTextContent(/\(\d+ of \d+\)/);
		// The flag line still spans the row: the name and every column shown.
		const columns = within(region()).getAllByRole('columnheader').length;
		for (const line of region().querySelectorAll('[data-row-notes]')) {
			expect(line.closest('td')).toHaveAttribute('colspan', String(columns));
		}
		expect(localStorage.getItem('opensolve-pipe:results-fields:The pumps in the group')).toBe(
			'["shaftPower"]'
		);
		// Another case shown: its name in the title, the same fields.
		await view.rerender(props(c, { oninspect: () => {}, caseName: 'Winter' }));
		await tick();
		const winter = region('The pumps in the group, Winter');
		expect(within(winter).queryByRole('columnheader', { name: /^Shaft power/ })).toBeNull();
		expect(within(winter).getByRole('columnheader', { name: /^Flow/ })).toBeInTheDocument();
	});
});

/**
 * S7 (pumps-results-layout.md §9 S7, §10 S7): the group chart's curve tables each a disclosure
 * "{caption} ({n} points)", full height when open, open by default where the chart cannot be drawn
 * or the group system curve has rows without a rise; the data region's boxes a Tab stop and a
 * named region only while they overflow; whether the data table is shown remembered in this
 * browser, kept by the card with each table's opening while the section is drawn again.
 */
describe('the group chart’s data without scroll traps (pumps-results-layout.md §9 S7)', () => {
	const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
	const GROUP = "Group curve (station's flow at each rise)";
	const SYSTEM = "Group system curve (rise the rest of the network needs at each station's flow)";
	/** Every curve table's disclosure, in order: its table's name, its summary, its rows, open. */
	const disclosures = () =>
		[...document.querySelectorAll<HTMLDetailsElement>('details[data-curve-table]')].map((d) => ({
			table: squash(d.querySelector('caption')!.textContent),
			summary: squash(d.querySelector(':scope > summary')!.textContent),
			rows: d.querySelectorAll('tbody tr').length,
			open: d.open
		}));
	const showTable = () =>
		fireEvent.click(screen.getByRole('button', { name: 'Show data table of the group chart' }));

	it('draws the group curve’s and the group system curve’s tables as disclosures “{caption} ({n} points)”, closed while the chart is drawn and every point has a rise', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		await showTable();
		const group = c.groupCurve.body as PumpGroupCurveResponse;
		const system = c.systemCurve!.body as PumpGroupCurveResponse;
		// The fixture's 42 samples of each (pump-groups-input.json).
		expect(group.points).toHaveLength(42);
		expect(system.systemPoints).toHaveLength(42);
		expect(disclosures()).toEqual([
			{ table: GROUP, summary: `${GROUP} (42 points)`, rows: 42, open: false },
			{ table: SYSTEM, summary: `${SYSTEM} (42 points)`, rows: 42, open: false }
		]);
		// The other tables are no curves: never folded.
		for (const name of ["Each pump's point (flow through it)"]) {
			expect(screen.getByRole('table', { name }).closest('details')).toBeNull();
		}
		for (const d of document.querySelectorAll('details[data-curve-table]')) {
			const box = d.querySelector('table')!.parentElement!;
			// Full height when open: sideways only, never a box that scrolls down in the pane.
			expect(box).toHaveClass('overflow-x-auto', 'scroll-shadow-x', 'relative');
			expect(box.className).not.toMatch(/max-h-/);
			expect(d.querySelector('caption')).toHaveClass('sr-only');
			// The summary's words in sight, its count with them: the table's one visible title
			// (S7 review W2, MUT-SUMMARY-HIDDEN).
			const summary = d.querySelector(':scope > summary')!;
			const caption = squash(d.querySelector('caption')!.textContent);
			expect(squash(wordsInSight(summary))).toBe(`${caption} (42 points)`);
		}
		// Opened, its rows in sight.
		expect(outOfSight(screen.getByRole('table', { name: GROUP }).querySelector('td')!)).toBe(true);
		await openTable(GROUP);
		expect(outOfSight(screen.getByRole('table', { name: GROUP }).querySelector('td')!)).toBe(false);
	});

	it('opens the group system curve’s table by default when some of its rows have no rise, the group curve’s staying closed', async () => {
		const c = named('fcv-outside');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		await showTable();
		const system = c.systemCurve!.body as PumpGroupCurveResponse;
		const missing = system.systemPoints.filter((p) => p.head === null).length;
		expect(missing).toBe(21);
		expect(disclosures().map(({ table, summary, open }) => [table, summary, open])).toEqual([
			[GROUP, `${GROUP} (42 points)`, false],
			[SYSTEM, `${SYSTEM} (42 points)`, true]
		]);
		// The reasons the strip's coverage line points to, in sight.
		const table = screen.getByRole('table', { name: SYSTEM });
		const reasons = [...table.querySelectorAll('tbody tr')].filter(
			(r) => r.querySelectorAll('td')[1]!.textContent === '—'
		);
		expect(reasons).toHaveLength(21);
		for (const r of reasons) expect(outOfSight(r.querySelectorAll('td')[2]!)).toBe(false);
	});

	/** parallel-ideal's group curve with three points other than the duty's without a flow. */
	function withoutFlow(c: FixtureCase) {
		// Made-up, as the API reports points its 45 s budget did not reach.
		const response = structuredClone(c.groupCurve.body as PumpGroupCurveResponse);
		for (const p of response.points.filter((p) => !p.isDuty).slice(0, 3)) {
			Object.assign(p, {
				flow: null,
				converged: false,
				reason: 'not_computed',
				message: "not computed: the request's 45 s budget ran out",
				members: []
			});
		}
		return { status: 'ready', response } satisfies GroupCurveState;
	}

	it('opens the group curve’s table by default when some of its points have no flow: the reasons its coverage line points to, one press away (§9 S7, §5.3; S7 review STRUCT-2, W1, REG-1)', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { system: systemReady(c), curve: withoutFlow(c) }));
		await drawn();
		// The strip's coverage line sends the user to the data table.
		const line = screen.getByText(
			'3 of 42 group-curve points have no flow: the line has gaps there, and the data table says why for each.'
		);
		expect(outOfSight(line)).toBe(false);
		await showTable();
		expect(disclosures().map(({ table, open }) => [table, open])).toEqual([
			[GROUP, true],
			[SYSTEM, false]
		]);
		// Its Note column's reasons, in sight once the data table is shown.
		const reasons = within(screen.getByRole('table', { name: GROUP })).getAllByText(
			'Not computed: the time budget ran out before this point.'
		);
		expect(reasons).toHaveLength(3);
		for (const r of reasons) expect(outOfSight(r)).toBe(false);
	});

	it('never closes a table it opened by default while it is drawn: a new default leaves it open, and only the next drawing of the data region takes the default afresh (§7 Disclosures “None closes itself”; S7 review DATA-1, MUT-TOGGLE)', async () => {
		const c = named('parallel-ideal');
		const all = systemReady(c);
		// Made-up: two points of the same group system curve without a rise.
		const some = structuredClone(all) as Extract<GroupCurveState, { status: 'ready' }>;
		for (const p of some.response.systemPoints.filter((p) => !p.isDuty).slice(0, 2)) {
			Object.assign(p, {
				head: null,
				converged: false,
				reason: 'not_converged',
				message: 'not converged: made-up reason'
			});
		}
		const view = render(PumpGroupChart, props(c, { system: all }));
		await drawn();
		await showTable();
		const task = () => new Promise((resolve) => setTimeout(resolve, 0)); // a toggle event's task
		await task();
		expect(disclosureOf(SYSTEM).open).toBe(false);
		// Points without a rise: opened by default, in place.
		await view.rerender(props(c, { system: some }));
		await task();
		expect(disclosureOf(SYSTEM).open).toBe(true);
		// Every point with a rise again: it stays open while drawn (it never closes itself).
		await view.rerender(props(c, { system: all }));
		await task();
		expect(disclosureOf(SYSTEM).open).toBe(true);
		// Drawn again, hidden and shown: no choice was made, so the default holds (closed).
		const hide = screen.getByRole('button', { name: 'Hide data table of the group chart' });
		await fireEvent.click(hide);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		await task();
		expect(disclosureOf(SYSTEM).open).toBe(false);
		// The group curve's likewise: opened by default by points without a flow, kept open while
		// drawn, and its default again once drawn anew.
		await view.rerender(props(c, { system: all, curve: withoutFlow(c) }));
		await task();
		expect(disclosureOf(GROUP).open).toBe(true);
		await view.rerender(props(c, { system: all }));
		await task();
		expect(disclosureOf(GROUP).open).toBe(true);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Hide data table of the group chart' })
		);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		await task();
		expect(disclosureOf(GROUP).open).toBe(false);
	});

	it('keeps the user’s closing of the group system curve’s table, open by default, while the data region is hidden and shown and the card closed and opened (S7 review MUT-BIND)', async () => {
		const c = named('fcv-outside');
		const view = render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		await showTable();
		const system = disclosureOf(SYSTEM);
		expect(system.open).toBe(true);
		await fireEvent.click(system.querySelector(':scope > summary')!);
		expect(system.open).toBe(false);
		await new Promise((resolve) => setTimeout(resolve, 0)); // the toggle event's task
		await fireEvent.click(
			screen.getByRole('button', { name: 'Hide data table of the group chart' })
		);
		expect(screen.queryByRole('table', { name: SYSTEM })).toBeNull();
		await fireEvent.click(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		);
		expect(disclosureOf(SYSTEM).open).toBe(false);
		await view.rerender(props(c, { system: systemReady(c), open: false }));
		expect(screen.queryByRole('table', { name: SYSTEM })).toBeNull();
		await view.rerender(props(c, { system: systemReady(c), open: true }));
		expect(disclosureOf(SYSTEM).open).toBe(false);
	});

	it('opens every curve table by default where the chart cannot be drawn', async () => {
		const c = named('parallel-ideal');
		HTMLCanvasElement.prototype.getContext = (() => null) as unknown as typeof getContext;
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await vi.waitFor(
			() => expect(screen.getByText(/The chart cannot be drawn in this browser/)).toBeVisible(),
			{ timeout: 10_000 }
		);
		expect(disclosures().map(({ table, open }) => [table, open])).toEqual([
			[GROUP, true],
			[SYSTEM, true]
		]);
	});

	it('keeps each table’s opening, and the data table shown, while the card is closed and opened', async () => {
		const c = named('parallel-ideal');
		const view = render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		await showTable();
		await openTable(GROUP);
		await new Promise((resolve) => setTimeout(resolve, 0)); // the toggle event's task
		await view.rerender(props(c, { system: systemReady(c), open: false }));
		expect(screen.queryByRole('table', { name: GROUP })).toBeNull();
		await view.rerender(props(c, { system: systemReady(c), open: true }));
		expect(
			screen.getByRole('button', { name: 'Hide data table of the group chart' })
		).toHaveAttribute('aria-expanded', 'true');
		expect(disclosures().map(({ table, open }) => [table, open])).toEqual([
			[GROUP, true],
			[SYSTEM, false]
		]);
	});

	it('remembers in this browser whether the data table is shown, apart from the pump chart’s', async () => {
		const c = named('parallel-ideal');
		const first = render(PumpGroupChart, props(c));
		await drawn();
		expect(localStorage.getItem('opensolve-pipe:pump-group-chart-data-table')).toBeNull();
		await showTable();
		expect(localStorage.getItem('opensolve-pipe:pump-group-chart-data-table')).toBe('shown');
		expect(localStorage.getItem('opensolve-pipe:pump-chart-data-table')).toBeNull();
		first.unmount();
		const second = render(PumpGroupChart, props(c));
		const hide = screen.getByRole('button', { name: 'Hide data table of the group chart' });
		expect(hide).toHaveAttribute('aria-expanded', 'true');
		expect(document.getElementById(hide.getAttribute('aria-controls')!)).not.toBeNull();
		await fireEvent.click(hide);
		expect(localStorage.getItem('opensolve-pipe:pump-group-chart-data-table')).toBeNull();
		second.unmount();
		render(PumpGroupChart, props(c));
		expect(
			screen.getByRole('button', { name: 'Show data table of the group chart' })
		).toHaveAttribute('aria-expanded', 'false');
	});

	it('works with storage refused: starts hidden, shows and hides on request', async () => {
		const refuse = () => {
			throw new DOMException('Storage refused', 'SecurityError');
		};
		const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(refuse);
		const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(refuse);
		const remove = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(refuse);
		try {
			const c = named('parallel-ideal');
			render(PumpGroupChart, props(c));
			await drawn();
			expect(get).toHaveBeenCalledWith('opensolve-pipe:pump-group-chart-data-table');
			const toggle = screen.getByRole('button', { name: 'Show data table of the group chart' });
			expect(toggle).toHaveAttribute('aria-expanded', 'false');
			await fireEvent.click(toggle);
			expect(set).toHaveBeenCalled();
			expect(toggle).toHaveAttribute('aria-expanded', 'true');
			expect(screen.getByRole('table', { name: GROUP })).toBeInTheDocument();
			await fireEvent.click(toggle);
			expect(remove).toHaveBeenCalled();
			expect(toggle).toHaveAttribute('aria-expanded', 'false');
			expect(screen.queryByRole('table', { name: GROUP })).toBeNull();
		} finally {
			get.mockRestore();
			set.mockRestore();
			remove.mockRestore();
		}
	});

	it('makes each box of the data region a Tab stop and a named region only while it overflows, on either axis', async () => {
		const c = named('parallel-ideal');
		render(PumpGroupChart, props(c, { system: systemReady(c) }));
		await drawn();
		await showTable();
		await openTable(GROUP);
		const data = document.querySelector<HTMLElement>('[data-group-data]')!;
		const boxes = within(data)
			.getAllByRole('table')
			.map((t) => t.parentElement!);
		expect(
			boxes.map((b) => squash(b.querySelector(':scope > table > caption')!.textContent))
		).toEqual(["Each pump's point (flow through it)", GROUP, SYSTEM]);
		for (const box of boxes) {
			sizeBox(box, { clientWidth: 452, scrollWidth: 452, clientHeight: 300, scrollHeight: 300 });
			observers.resize(box);
		}
		expect(within(data).queryAllByRole('region')).toEqual([]);
		// The group curve's member columns wider than the box.
		sizeBox(boxes[1]!, { scrollWidth: 1400 });
		observers.resize(boxes[1]!);
		expect(within(data).getByRole('region', { name: GROUP })).toBe(boxes[1]);
		expect(boxes[1]).toHaveAttribute('tabindex', '0');
		// "Each pump's point" taller than its box.
		sizeBox(boxes[0]!, { scrollHeight: 500 });
		observers.resize(boxes[0]!);
		expect(within(data).getByRole('region', { name: "Each pump's point (flow through it)" })).toBe(
			boxes[0]
		);
		// They fit again: neither is.
		sizeBox(boxes[1]!, { clientWidth: 1400 });
		observers.resize(boxes[1]!);
		sizeBox(boxes[0]!, { clientHeight: 500 });
		observers.resize(boxes[0]!);
		expect(within(data).queryAllByRole('region')).toEqual([]);
		for (const box of boxes) expect(box).not.toHaveAttribute('tabindex');
	});
});
