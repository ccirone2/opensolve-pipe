/**
 * The card's sections a solve withdraws (proposals/open-defects-2.md F3, the owner's answer of
 * 2026-11-26): Add cases and the two methods' disclosures stay withdrawn until the case shown's
 * curves have answered (the group curve and, when wanted, the group system curve: PumpsView's
 * shownSettled, given as `settled`), so they are never drawn with another solve's results, and
 * come back in one flush with the user's open sections (the plan, the stop order, "How the group
 * curve is computed", "How the group system curve is computed") and the focus: the figure holds
 * it meanwhile and gives it back to the same control, at the same offset in the pane, unless the
 * user has taken a step of their own. Any other control the solve takes away hands the focus to
 * the figure (else the toggle) rather than the page.
 *
 * The answers are the shared fixture's recorded API responses (apps/api/tests/fixtures/
 * pump_groups_input.py, case `one-off`); each phase's props are what PumpsView gives the card.
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
	SolveResponse
} from '$lib/api/types';
import type { GroupCurveState } from '$lib/state/project.svelte';
import { fakeResizeObserver, sizeBox } from '$lib/testing/resize';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { caseTags, ratedCurveRange } from '$lib/utils/pump-chart';
import type { GroupMemberInput } from '$lib/utils/pump-group-chart';
import {
	otherGroupCases,
	runningCombinations,
	type CombinationsInput
} from '$lib/utils/pump-group-one-off';
import { lineupPlan, type LineupPlanInput } from '$lib/utils/pump-lineups';
import { withScenarios } from '$lib/utils/scenarios';
import PumpGroupChart from './PumpGroupChart.svelte';

vi.mock('./chart-setup', async () => ({
	pumpGroupConfig: (await import('$lib/utils/pump-chart-config')).pumpGroupConfig,
	Chart: class {
		static defaults = { plugins: { legend: { labels: { generateLabels: () => [] } } } };
		draw() {}
		destroy() {}
	},
	downloadChartImage: async () => {},
	IMAGE_REASONS_IN: 'made-up place says'
}));

const getContext = HTMLCanvasElement.prototype.getContext;
const rectOf = HTMLElement.prototype.getBoundingClientRect;
let observers: ReturnType<typeof fakeResizeObserver>;
beforeEach(() => {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	observers = fakeResizeObserver();
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	HTMLElement.prototype.getBoundingClientRect = rectOf;
	observers.restore();
	vi.restoreAllMocks();
	localStorage.clear();
	cleanup();
	document.body.innerHTML = '';
});

type Answer = { status: number; body: unknown };
interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse & { solvedState: SolvedState };
	groupCurve: Answer;
	systemCurve: Answer | null;
	scenarioCases: Record<string, { solve: SolveResponse; groupCurve: Answer }>;
}
const c = (fixture.cases as unknown as FixtureCase[]).find((x) => x.name === 'one-off')!;
const station = (c.groupCurve.body as PumpGroupCurveResponse).station;

function pumpsOf(): Omit<GroupMemberInput, 'slot'>[] {
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
/** An answer of a solve: each new solve's a new object (structuredClone), as the API's are. */
const ready = (answer: Answer): GroupCurveState => ({
	status: 'ready',
	response: structuredClone(answer.body) as PumpGroupCurveResponse
});
/** The Add cases block's props for the base case, the project without its scenarios. */
const lineups = (values: Partial<LineupPlanInput> = {}) => ({
	plan: lineupPlan({
		project: withScenarios(structuredClone(c.project), []),
		shownCase: null,
		station,
		memberIds: ['PA', 'PB'],
		base: { response: c.solve, stale: false },
		preset: 'running',
		savedOrder: [],
		...values
	})
});

/** The case shown's curves have answered: everything drawn (PumpsView's shownSettled). */
const answered = () => ({
	curve: ready(c.groupCurve),
	system: ready(c.systemCurve!),
	lineups: lineups(),
	settled: true
});
/** A new solve's response: its group curve asked for, so no station and no plan. */
const asked = () => ({
	curve: { status: 'loading' } as GroupCurveState,
	system: undefined,
	lineups: null,
	settled: false
});
/** Its group curve answered; its group system curve not asked yet in that flush. */
const groupBack = () => ({
	curve: ready(c.groupCurve),
	system: undefined,
	lineups: lineups(),
	settled: false
});
/** Its group system curve asked for. */
const systemAsked = () => ({ ...groupBack(), system: { status: 'loading' } as GroupCurveState });

function props(values: Record<string, unknown> = {}) {
	return {
		pumps: pumpsOf(),
		slots: c.memberIds,
		prefs: c.project.settings.units,
		project: c.project,
		nodes: c.solve.solvedState.nodeResults,
		open: true,
		caseName: 'Base case',
		tags: caseTags(c.project),
		...answered(),
		...values
	};
}

const block = () => screen.queryByRole('region', { name: 'Add cases' });
const planOf = () => block()!.querySelector<HTMLDetailsElement>('[data-lineup-plan]')!;
const stopOf = () => block()!.querySelector<HTMLDetailsElement>('[data-stop-order]')!;
const methods = (name: RegExp) =>
	[...document.querySelectorAll('details')].find((d) =>
		name.test(d.querySelector(':scope > summary')!.textContent ?? '')
	);
// "How this curve is computed" while the group system curve is not shown.
const groupMethods = () => methods(/How (the group|this) curve is computed/);
const systemMethods = () => methods(/How the group system curve is computed/);
const figure = () => screen.getByRole('figure');
const toggle = () => screen.getByRole('button', { name: /^Pumps together/ });
const later = () => within(block()!).getByRole('button', { name: 'Stop Pump PB later' });
async function open(details: HTMLDetailsElement) {
	await fireEvent.click(details.querySelector(':scope > summary')!);
	expect(details.open).toBe(true);
}
/** Every task the handovers queue (tick, then the focus), run. */
const settle = async () => {
	await tick();
	await tick();
	await new Promise((r) => setTimeout(r, 0));
};
/** A rerender with the phase's props, its handovers run. */
async function phase(
	view: { rerender: (next: ReturnType<typeof props>) => Promise<void> },
	values: Record<string, unknown>
) {
	await view.rerender(props(values));
	await settle();
}
/** Nothing of the sections is drawn while the card waits (requirement 1). */
function withdrawn() {
	expect(block()).toBeNull();
	expect(groupMethods()).toBeUndefined();
	expect(systemMethods()).toBeUndefined();
}

describe('the sections withdrawn during a solve (open-defects-2 F3)', () => {
	it('keeps the open sections over the withdrawal: the plan closed, the stop order and both methods open', async () => {
		const view = render(PumpGroupChart, props());
		// The user closes the plan, drawn open (cases remain): the fold rule would draw it open.
		await fireEvent.click(planOf().querySelector(':scope > summary')!);
		expect(planOf().open).toBe(false);
		await open(groupMethods()!);
		await open(systemMethods()!);
		await phase(view, asked());
		await phase(view, answered());
		expect(planOf().open).toBe(false);
		expect(groupMethods()!.open).toBe(true);
		expect(systemMethods()!.open).toBe(true);
		// And the stop order, open, inside the plan opened again.
		await open(planOf());
		await open(stopOf());
		await phase(view, asked());
		await phase(view, answered());
		expect(planOf().open).toBe(true);
		expect(stopOf().open).toBe(true);
	});

	it('keeps Add cases and both methods withdrawn until the group system curve has answered, then brings them and the focus back in one flush', async () => {
		const view = render(PumpGroupChart, props());
		expect(planOf().open).toBe(true);
		await open(stopOf());
		await open(groupMethods()!);
		await open(systemMethods()!);
		const before = later();
		before.focus();

		// Ctrl+Enter's new solve: its group curve asked for, nothing drawn of the earlier one's.
		await phase(view, asked());
		withdrawn();
		expect(figure()).toHaveFocus();
		// The group curve answers: still withdrawn while the group system curve is not asked in
		// that flush, and while it loads (PumpsView's shownSettled).
		await phase(view, groupBack());
		withdrawn();
		expect(figure()).toHaveFocus();
		await phase(view, systemAsked());
		withdrawn();
		expect(figure()).toHaveFocus();

		// The group system curve answers: the block and both methods as the user left them, and
		// the focus on the same button (a new node), all in the one rerender.
		await view.rerender(props(answered()));
		expect(planOf().open).toBe(true);
		expect(stopOf().open).toBe(true);
		expect(groupMethods()!.open).toBe(true);
		expect(systemMethods()!.open).toBe(true);
		const again = later();
		expect(again).not.toBe(before);
		expect(again).toHaveFocus();
	});

	it('draws each section with its own answer at the card’s first drawing, as before, and a calculation that cancels a curve takes none away (holds already)', async () => {
		// Opened while the group system curve is computed: Add cases and the group curve's methods
		// with the group curve, as before; nothing a solve withdrew.
		const view = render(PumpGroupChart, props(systemAsked()));
		const add = block();
		expect(add).not.toBeNull();
		expect(groupMethods()).toBeDefined();
		expect(systemMethods()).toBeUndefined();
		// Solve all cancels it until the run ends (not settled), with no new response: the block
		// stays, the same node.
		await phase(view, {
			...systemAsked(),
			system: { status: 'cancelled', by: 'solve' } as GroupCurveState
		});
		expect(block()).toBe(add);
		expect(groupMethods()).toBeDefined();
	});

	it('gives the focus back once the group system curve has failed (nothing more to wait for)', async () => {
		const view = render(PumpGroupChart, props());
		within(block()!).getByRole('button', { name: 'Add 1 case' }).focus();
		await phase(view, asked());
		expect(figure()).toHaveFocus();
		await phase(view, {
			...groupBack(),
			system: { status: 'error', message: 'No answer.' },
			settled: true
		});
		expect(within(block()!).getByRole('button', { name: 'Add 1 case' })).toHaveFocus();
	});

	// The review of open defects round two, WS-1: a section's answer that goes in a flush with
	// nothing left to wait for (a case switch onto curves the store holds, its group system curve
	// failed) is a withdrawal already over, so a later wait with no loss (that curve's Try again)
	// withdraws nothing.
	it('withdraws nothing on a later wait when the withdrawal was already settled (a failed group system curve, then its Try again)', async () => {
		const view = render(PumpGroupChart, props());
		await phase(view, { system: { status: 'error', message: 'No answer.' }, settled: true });
		expect(block()).not.toBeNull();
		expect(groupMethods()).toBeDefined();
		expect(systemMethods()).toBeUndefined();
		// Try the group system curve again: it loads, nothing taken away meanwhile.
		await phase(view, { system: { status: 'loading' }, settled: false });
		expect(block()).not.toBeNull();
		expect(groupMethods()).toBeDefined();
		// Its answer: the group system curve's methods with the others.
		await phase(view, answered());
		expect(block()).not.toBeNull();
		expect(groupMethods()).toBeDefined();
		expect(systemMethods()).toBeDefined();
	});

	it('gives the focus back to a method’s summary, which comes back with the others', async () => {
		const view = render(PumpGroupChart, props());
		await open(systemMethods()!);
		systemMethods()!.querySelector<HTMLElement>(':scope > summary')!.focus();
		await phase(view, asked());
		expect(figure()).toHaveFocus();
		await phase(view, systemAsked());
		expect(figure()).toHaveFocus();
		await phase(view, answered());
		expect(systemMethods()!.open).toBe(true);
		expect(systemMethods()!.querySelector(':scope > summary')).toHaveFocus();
	});

	it('gives a preset’s radio back by its value', async () => {
		const view = render(PumpGroupChart, props());
		within(block()!).getByRole('radio', { name: 'Each pump off' }).focus();
		await phase(view, asked());
		expect(figure()).toHaveFocus();
		await phase(view, answered());
		expect(within(block()!).getByRole('radio', { name: 'Each pump off' })).toHaveFocus();
	});

	it('leaves the focus where the user moved it while the sections were withdrawn', async () => {
		const view = render(PumpGroupChart, props());
		await open(stopOf());
		later().focus();
		await phase(view, asked());
		expect(figure()).toHaveFocus();
		// Shift+Tab to the toggle.
		await fireEvent.keyDown(figure(), { key: 'Tab', shiftKey: true });
		toggle().focus();
		await phase(view, answered());
		expect(toggle()).toHaveFocus();
		expect(stopOf().open).toBe(true);
	});

	// A press on the canvas keeps the focus on the figure, its nearest focusable ancestor, and a
	// wheel or a touch moves no focus: each still ends the wait, so the pane never jumps to the
	// control afterwards (the ui-guide's rule, pumps-results-layout.md §15 item 222).
	for (const [step, fire] of [
		['a press on the canvas', (at: Element) => fireEvent.pointerDown(at)],
		['a wheel', (at: Element) => fireEvent.wheel(at, { deltaY: 400 })],
		['a touch', (at: Element) => fireEvent.touchStart(at)],
		['a key', (at: Element) => fireEvent.keyDown(at, { key: 'ArrowDown' })]
	] as const) {
		it(`ends the wait on the user’s own step (${step}): the focus stays on the figure`, async () => {
			const view = render(PumpGroupChart, props());
			await open(stopOf());
			later().focus();
			await phase(view, asked());
			expect(figure()).toHaveFocus();
			await fire(figure().querySelector('canvas')!);
			expect(figure()).toHaveFocus();
			const focus = vi.spyOn(HTMLElement.prototype, 'focus');
			await phase(view, answered());
			expect(figure()).toHaveFocus();
			expect(focus).not.toHaveBeenCalled();
		});
	}

	it('takes a window blur for no step: the focus still comes back', async () => {
		const view = render(PumpGroupChart, props());
		await open(stopOf());
		later().focus();
		await phase(view, asked());
		expect(figure()).toHaveFocus();
		// The window loses the system focus: a blur on the figure, which is still the document's
		// focused element.
		const hasFocus = vi.spyOn(document, 'hasFocus').mockReturnValue(false);
		figure().dispatchEvent(new FocusEvent('blur'));
		figure().dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
		expect(figure()).toHaveFocus();
		await phase(view, answered());
		expect(later()).toHaveFocus();
		hasFocus.mockRestore();
	});

	it('puts the control back at the same offset in the pane, not where focus() would scroll it', async () => {
		// The pane that scrolls (the Results pane's scroller), its top 100 px down the window.
		const pane = document.createElement('div');
		pane.style.overflowY = 'auto';
		document.body.append(pane);
		sizeBox(pane, { clientHeight: 700, scrollHeight: 9000 });
		let scrolled = 6456;
		Object.defineProperty(pane, 'scrollTop', {
			configurable: true,
			get: () => scrolled,
			set: (v: number) => (scrolled = Math.min(Math.max(0, v), 9000 - 700))
		});
		// Where the control lies in the pane's content: 6,913 px down it, then 7,700 px once the
		// block is drawn back (the curves above it grew meanwhile).
		let at = 6913;
		HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
			if (this === pane) return { top: 100 } as DOMRect;
			if (this.dataset.stopId === 'PB' && this.dataset.dir === 'down') {
				return { top: 100 + at - scrolled } as DOMRect;
			}
			return { top: 0 } as DOMRect;
		};
		const view = render(PumpGroupChart, { target: pane, props: props() });
		await open(stopOf());
		later().focus();
		const offset = later().getBoundingClientRect().top - 100;
		expect(offset).toBe(457);
		await view.rerender(props(asked()));
		// The pane shortened by the withdrawal: the browser clamps its scroll.
		scrolled = 2812;
		await settle();
		expect(figure()).toHaveFocus();
		at = 7700;
		const focus = vi.spyOn(HTMLElement.prototype, 'focus');
		await phase(view, answered());
		expect(later()).toHaveFocus();
		expect(focus).toHaveBeenCalledWith({ preventScroll: true });
		expect(later().getBoundingClientRect().top - 100).toBe(offset);
		expect(scrolled).toBe(7700 - 457);
	});

	// The offset held is the one the user last saw (open-defects-2.md F3, the browser agent's
	// defect 1): read as the control takes the focus and at each scroll of its pane, never in the
	// flush that withdraws it. That flush has already shrunk the pump chart's section above the card
	// (1,246 → 1,158 px), and Chromium anchors the scroll for it only at the frame's layout, so a
	// read there put the button back 68 px higher at 1280 × 800 (291 px; the user saw it at 359).
	for (const last of ['its focus', 'its pane’s last scroll'] as const) {
		it(`puts the control back at the offset last seen, at ${last}, not as read in the flush that withdraws it`, async () => {
			// The pane that scrolls, its top 100 px down the window, as the test above has it.
			const pane = document.createElement('div');
			pane.style.overflowY = 'auto';
			document.body.append(pane);
			sizeBox(pane, { clientHeight: 700, scrollHeight: 9000 });
			let scrolled = 6384;
			Object.defineProperty(pane, 'scrollTop', {
				configurable: true,
				get: () => scrolled,
				set: (v: number) => (scrolled = Math.min(Math.max(0, v), 9000 - 700))
			});
			// Where the control lies in the pane's content: 359 px below the pane's top at first.
			let at = 6743;
			HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
				if (this === pane) return { top: 100 } as DOMRect;
				if (this.dataset.stopId === 'PB' && this.dataset.dir === 'down') {
					return { top: 100 + at - scrolled } as DOMRect;
				}
				return { top: 0 } as DOMRect;
			};
			const offset = () => later().getBoundingClientRect().top - 100;
			const view = render(PumpGroupChart, { target: pane, props: props() });
			await open(stopOf());
			later().focus();
			expect(offset()).toBe(359);
			let seen = 359;
			if (last === 'its pane’s last scroll') {
				// The user wheels the pane 40 px down, the focus kept on the control, then the
				// solving line grows the content above it by 72 px and the browser anchors the
				// scroll: each a scroll event, the control at 319 px after both.
				await fireEvent.wheel(pane, { deltaY: 40 });
				scrolled += 40;
				await fireEvent.scroll(pane);
				at += 72;
				scrolled += 72;
				await fireEvent.scroll(pane);
				seen = 319;
				expect(offset()).toBe(seen);
			}
			// In the withdrawal's flush the pump chart's section above has shrunk by 68 px, not yet
			// anchored: no scroll event, the control read 68 px higher than the user saw it.
			at -= 68;
			expect(offset()).toBe(seen - 68);
			await view.rerender(props(asked()));
			// The pane shortened by the withdrawal: the browser clamps its scroll.
			scrolled = 2812;
			await settle();
			expect(figure()).toHaveFocus();
			at = 7700;
			await phase(view, answered());
			expect(later()).toHaveFocus();
			expect(offset()).toBe(seen);
			expect(scrolled).toBe(7700 - seen);
		});
	}

	it('keeps the focus on the figure when the control is gone from the block drawn back', async () => {
		const view = render(PumpGroupChart, props());
		await open(stopOf());
		later().focus();
		await phase(view, asked());
		// Back with Each pump off chosen meanwhile: no stop order, so no such button.
		await phase(view, { ...answered(), lineups: lineups({ preset: 'each' }) });
		expect(block()).not.toBeNull();
		expect(block()!.querySelector('[data-stop-order]')).toBeNull();
		expect(figure()).toHaveFocus();
	});

	it('gives the focus to the card’s toggle when the solve fails and the figure goes too', async () => {
		const view = render(PumpGroupChart, props());
		await open(stopOf());
		later().focus();
		await phase(view, {
			...asked(),
			unavailable:
				'The latest solve failed; the card shows nothing from an earlier version of the project.'
		});
		expect(screen.queryByRole('figure')).toBeNull();
		expect(toggle()).toHaveFocus();
	});

	it('draws the sections anew when the card is closed and opened (§5.3 The fold, holds already)', async () => {
		const view = render(PumpGroupChart, props());
		await open(stopOf());
		await open(groupMethods()!);
		await fireEvent.click(planOf().querySelector(':scope > summary')!);
		expect(planOf().open).toBe(false);
		await fireEvent.click(toggle());
		await view.rerender(props({ open: false }));
		await fireEvent.click(toggle());
		await view.rerender(props({ open: true }));
		await settle();
		// The fold rule's drawing: open, since cases remain to add.
		expect(planOf().open).toBe(true);
		expect(stopOf().open).toBe(false);
		expect(groupMethods()!.open).toBe(false);
	});

	it('goes on with the fold rule over a withdrawal: the plan folded with every case made opens itself once cases remain (holds already)', async () => {
		// Every case the plan makes exists (the fixture's S2, "Pump PB off"): the plan is drawn
		// folded.
		const made = withScenarios(
			structuredClone(c.project),
			c.project.scenarios!.filter((s) => s.id === 'S2')
		);
		const done = () => lineups({ project: made });
		const view = render(PumpGroupChart, props({ lineups: done() }));
		expect(planOf().open).toBe(false);
		await phase(view, asked());
		// Back with the case gone meanwhile (an Undo): cases remain, so it opens itself.
		await phase(view, answered());
		expect(planOf().open).toBe(true);
	});
});

describe('the focus on any control a solve takes from the card (open-defects-2 F3)', () => {
	/** The `one-off` scenarios as the card has them, every one ready. */
	const others = () =>
		otherGroupCases({
			valued: ['S1', 'S2'].map((id) => ({
				key: id,
				caseId: id,
				name: c.project.scenarios!.find((s) => s.id === id)!.name,
				stale: false,
				group: {
					status: 'ready',
					response: c.scenarioCases[id]!.groupCurve.body as PumpGroupCurveResponse
				},
				system: undefined,
				shared: true,
				solved: null
			})),
			tags: caseTags(c.project),
			shownKeys: new Set(['S1', 'S2']),
			othersOn: true,
			shownSettled: true,
			station,
			systemShown: c.systemCurve!.body as PumpGroupCurveResponse,
			memberIds: ['PA', 'PB'],
			project: c.project,
			boxes: ['PA', 'PB']
		});
	const combinations = () => {
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
					station: 'Station 55.15 L/s at a rise of 27.38 m',
					tag: 'Base'
				},
				{
					key: 'S2',
					name: 'Pump PB off',
					shown: false,
					status: 'solved',
					response: c.scenarioCases.S2!.solve,
					stale: false,
					station: null,
					tag: 2
				}
			],
			prefs: c.project.settings.units,
			project: c.project
		};
		return runningCombinations(input);
	};
	/** The card with scenarios: the other cases' switch and Running combinations drawn too. */
	const full = (values: Record<string, unknown> = {}) =>
		props({
			otherCases: others(),
			othersOn: true,
			onothers: () => {},
			combinations: combinations(),
			oninspect: () => {},
			...values
		});
	/** A new solve's response, as PumpsView gives it: no station, so no plan and no table. */
	const fullAsked = () => full({ ...asked(), otherCases: [], combinations: null });

	const controls: [string, () => HTMLElement][] = [
		["the group chart's slider", () => within(figure()).getByRole('slider')],
		[
			"the other cases' switch",
			() => screen.getByRole('checkbox', { name: /Also show the other cases' station duties/ })
		],
		[
			'a trace button in Running combinations',
			() => {
				const heading = screen.getByRole('heading', { name: 'Running combinations' });
				return heading.parentElement!.querySelector<HTMLElement>('table button, li button')!;
			}
		]
	];
	for (const [name, control] of controls) {
		it(`hands the focus on ${name} to the figure, not the page, and keeps it there`, async () => {
			const view = render(PumpGroupChart, full());
			const at = control();
			expect(at).toBeTruthy();
			at.focus();
			expect(at).toHaveFocus();
			await view.rerender(fullAsked());
			await settle();
			expect(at.isConnected).toBe(false);
			expect(figure()).toHaveFocus();
			// No key to give it back by: the focus stays on the figure.
			await view.rerender(full());
			await settle();
			expect(figure()).toHaveFocus();
		});
	}

	it('hands it to the toggle when the figure goes too (a failed solve)', async () => {
		const view = render(PumpGroupChart, full());
		const at = controls[2]![1]();
		at.focus();
		await view.rerender({
			...fullAsked(),
			unavailable:
				'The latest solve failed; the card shows nothing from an earlier version of the project.'
		});
		await settle();
		expect(toggle()).toHaveFocus();
	});
});
