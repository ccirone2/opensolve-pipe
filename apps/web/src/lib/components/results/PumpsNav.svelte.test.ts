/**
 * The Pumps tab's section nav (proposal pumps-results-layout.md §5.4, §7, §10 The nav): a toolbar
 * named "Go to" in a nav named "Pumps view sections", one button per section drawn; one Tab
 * stop, the arrows, Home and End; a press that scrolls its target to the top and focuses it
 * without a second scroll, smoothly unless reduced motion is asked for, never touching the link;
 * the stop clamped when the buttons change; aria-current from an observer of the pane; pinned
 * only once the pump canvas has scrolled out and only at ≤ 15 % of the pane; the marks; and, in
 * the workspace, the buttons from the sections drawn and "Back to the sections".
 *
 * jsdom lays nothing out: the observer-driven tests give the elements their boxes and run a fake
 * IntersectionObserver, whose callbacks the test fires after moving a box. The browser's own
 * layout is measured in tests/pumps-layout.e2e.ts.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotAStationError } from '$lib/api/client';
import type { Project, PumpGroupCurveResponse, SolveResponse, TopologyIssue } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { outOfSight } from '$lib/testing/helpers';
import { pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { pumpTransferExample } from '$lib/utils/examples';
import { sectionMark, type SectionKey } from '$lib/utils/section-nav';
import PumpsNav from './PumpsNav.svelte';
import type { SectionTarget } from './section-nav.svelte';

// ---- Fakes: boxes, the observer, media queries ---------------------------------------------------

/** Boxes by element (top and bottom in viewport px); the nav's own height by its hook. */
const boxes = new Map<Element, { top: number; bottom: number }>();
let navHeight = 53;
function box(this: Element): DOMRect {
	const b = boxes.get(this);
	const height = this.matches('[data-pumps-nav]') ? navHeight : b ? b.bottom - b.top : 0;
	const top = b?.top ?? 0;
	return {
		top,
		bottom: top + height,
		left: 0,
		right: 0,
		width: 0,
		height,
		x: 0,
		y: top,
		toJSON: () => ({})
	} as DOMRect;
}

class FakeObserver {
	static all: FakeObserver[] = [];
	readonly root: Element | Document | null;
	readonly rootMargin: string;
	readonly thresholds: readonly number[] = [];
	targets = new Set<Element>();
	constructor(
		readonly callback: IntersectionObserverCallback,
		options: IntersectionObserverInit = {}
	) {
		this.root = options.root ?? null;
		this.rootMargin = options.rootMargin ?? '';
		FakeObserver.all.push(this);
	}
	observe(target: Element) {
		this.targets.add(target);
	}
	unobserve(target: Element) {
		this.targets.delete(target);
	}
	disconnect() {
		this.targets.clear();
		FakeObserver.all = FakeObserver.all.filter((o) => o !== this);
	}
	takeRecords() {
		return [];
	}
}
/** Run every live observer's callback, as the browser does once an intersection changes. */
async function observe() {
	for (const o of [...FakeObserver.all]) o.callback([], o as unknown as IntersectionObserver);
	await tick();
}

const realMatchMedia = window.matchMedia;
/** Media queries answered by `matches` (svelte's MediaQuery reads window.matchMedia). */
function media(matches: (query: string) => boolean) {
	window.matchMedia = ((query: string) => ({
		matches: matches(query),
		media: query,
		onchange: null,
		addEventListener() {},
		removeEventListener() {},
		addListener() {},
		removeListener() {},
		dispatchEvent: () => false
	})) as unknown as typeof window.matchMedia;
}

/** `n` animation frames (jsdom pretends to be visual: requestAnimationFrame runs). */
async function frames(n: number) {
	for (let i = 0; i < n; i++)
		await new Promise<void>((done) => requestAnimationFrame(() => done()));
}

/** jsdom has no scrollIntoView: a recording one, for the test. */
function stubScroll() {
	const scrolled = vi.fn();
	HTMLElement.prototype.scrollIntoView = scrolled;
	return scrolled;
}

const holders: HTMLElement[] = [];
afterEach(() => {
	delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
	for (const h of holders.splice(0)) h.remove();
	boxes.clear();
	navHeight = 53;
	FakeObserver.all = [];
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
	window.matchMedia = realMatchMedia;
});

/** Headings (tabindex −1) standing for the sections' targets, in document order. */
function sectionsOf(
	keys: SectionKey[],
	marks: Partial<Record<SectionKey, ReturnType<typeof sectionMark>>> = {}
): SectionTarget[] {
	const holder = document.createElement('div');
	document.body.append(holder);
	holders.push(holder);
	return keys.map((key) => {
		const target = document.createElement(key === 'pumps-together' ? 'button' : 'h4');
		target.tabIndex = -1;
		target.textContent = key;
		holder.append(target);
		return { key, target, mark: () => marks[key] ?? null };
	});
}

const ALL: SectionKey[] = [
	'per-pump',
	'pump-chart',
	'pumps-together',
	'station',
	'group-chart',
	'add-cases',
	'combinations'
];
const nav = () => screen.getByRole('navigation', { name: 'Pumps view sections' });
const toolbar = () => within(nav()).getByRole('toolbar', { name: 'Go to' });
const buttons = () => within(toolbar()).getAllByRole('button');
/** A button's accessible name: its aria-label with a mark, else its words. */
const nameOf = (b: HTMLElement) => b.getAttribute('aria-label') ?? b.textContent!.trim();
const button = (name: string) => within(toolbar()).getByRole('button', { name });
const stops = () => buttons().filter((b) => b.tabIndex === 0);
const currentNames = () =>
	buttons()
		.filter((b) => b.getAttribute('aria-current') === 'location')
		.map(nameOf);

// ---- The toolbar ---------------------------------------------------------------------------------

describe('the section nav', () => {
	it('is a toolbar labelled by its visible lead word "Go to" in a nav, one button per section, in order', () => {
		render(PumpsNav, { props: { sections: sectionsOf(ALL) } });
		expect(nav().tagName).toBe('NAV');
		expect(toolbar()).toHaveAttribute('aria-orientation', 'horizontal');
		const lead = within(nav()).getByText('Go to', { exact: true });
		expect(lead).toBeVisible();
		// Seen at every width: toBeVisible reads no class, so an sr-only lead would pass it.
		expect(outOfSight(lead)).toBe(false);
		expect(buttons().map(nameOf)).toEqual([
			'Per pump',
			'Pump chart',
			'Pumps together',
			'Station',
			'Group chart',
			'Add cases',
			'Running combinations'
		]);
		// Not the view row's tablist: buttons, never tabs or links (the fragment is the project).
		expect(within(nav()).queryAllByRole('tab')).toEqual([]);
		expect(within(nav()).queryAllByRole('link')).toEqual([]);
		for (const b of buttons()) expect(b).toHaveAttribute('type', 'button');
	});

	it('has one Tab stop; ←, →, Home and End move between the buttons, wrapping at the ends', async () => {
		render(PumpsNav, { props: { sections: sectionsOf(ALL) } });
		expect(stops()).toEqual([button('Per pump')]);
		button('Per pump').focus();
		// Each key it handles is taken from the browser (fireEvent gives false once the default
		// is prevented): the browser's own End and Home would scroll the pane to its ends.
		expect(await fireEvent.keyDown(button('Per pump'), { key: 'ArrowRight' })).toBe(false);
		expect(document.activeElement).toBe(button('Pump chart'));
		expect(stops()).toEqual([button('Pump chart')]);
		expect(await fireEvent.keyDown(button('Pump chart'), { key: 'End' })).toBe(false);
		expect(document.activeElement).toBe(button('Running combinations'));
		expect(stops()).toEqual([button('Running combinations')]);
		expect(await fireEvent.keyDown(button('Running combinations'), { key: 'ArrowRight' })).toBe(
			false
		);
		expect(document.activeElement).toBe(button('Per pump'));
		expect(await fireEvent.keyDown(button('Per pump'), { key: 'ArrowLeft' })).toBe(false);
		expect(document.activeElement).toBe(button('Running combinations'));
		expect(await fireEvent.keyDown(button('Running combinations'), { key: 'Home' })).toBe(false);
		expect(document.activeElement).toBe(button('Per pump'));
		expect(stops()).toEqual([button('Per pump')]);
		// Another key is the browser's: not taken.
		const other = new KeyboardEvent('keydown', {
			key: 'ArrowDown',
			bubbles: true,
			cancelable: true
		});
		button('Per pump').dispatchEvent(other);
		expect(other.defaultPrevented).toBe(false);
		expect(document.activeElement).toBe(button('Per pump'));
	});

	it('brings the button an arrow key focuses into the row’s view, scrolling the row alone (§5.4 One shared component)', async () => {
		const scrolled = stubScroll();
		render(PumpsNav, { props: { sections: sectionsOf(ALL) } });
		// Boxes, as a 200 px row holding buttons 100 px wide side by side.
		const row = toolbar();
		const all = buttons();
		Object.defineProperty(row, 'clientWidth', { configurable: true, value: 200 });
		Object.defineProperty(row, 'scrollWidth', { configurable: true, value: 100 * all.length });
		vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
			this: Element
		) {
			const i = all.indexOf(this as HTMLElement);
			const left = this === row ? row.scrollLeft : i >= 0 ? 100 * i : 0;
			const width = this === row ? 200 : i >= 0 ? 100 : 0;
			return { left, right: left + width, width, top: 0, bottom: 44, height: 44 } as DOMRect;
		});
		const scrollTo = vi.fn();
		row.scrollTo = scrollTo as unknown as typeof row.scrollTo;
		button('Per pump').focus();
		await fireEvent.keyDown(button('Per pump'), { key: 'End' });
		expect(document.activeElement).toBe(button('Running combinations'));
		// The row brings the last button in, at 700 − 200 = 500, never by scrollIntoView.
		expect(scrollTo).toHaveBeenLastCalledWith({ left: 500, behavior: 'smooth' });
		expect(scrollTo.mock.contexts.at(-1)).toBe(row);
		expect(scrolled).not.toHaveBeenCalled();
	});

	it('keeps the stop on the button last focused while the focus is in it, else on the current one', async () => {
		const outside = document.createElement('button');
		document.body.append(outside);
		holders.push(outside);
		render(PumpsNav, { props: { sections: sectionsOf(ALL) } });
		button('Per pump').focus();
		await fireEvent.keyDown(button('Per pump'), { key: 'ArrowRight' });
		await fireEvent.keyDown(button('Pump chart'), { key: 'ArrowRight' });
		expect(stops()).toEqual([button('Pumps together')]);
		outside.focus();
		await tick();
		// The focus gone, the stop is the current one (none passed yet: the first).
		expect(stops()).toEqual([button('Per pump')]);
	});

	it('scrolls a pressed target to the top smoothly, then focuses it without a second scroll; never touches the link (D3)', async () => {
		const scrolled = stubScroll();
		history.replaceState(null, '', '#the-project');
		const sections = sectionsOf(ALL);
		render(PumpsNav, { props: { sections } });
		for (const section of sections) {
			const focus = vi.spyOn(section.target, 'focus');
			const name = buttons()[sections.indexOf(section)]!;
			await fireEvent.click(name);
			expect(scrolled).toHaveBeenLastCalledWith({ block: 'start', behavior: 'smooth' });
			expect(scrolled.mock.contexts.at(-1)).toBe(section.target);
			expect(focus).toHaveBeenCalledWith({ preventScroll: true });
			expect(document.activeElement).toBe(section.target);
			expect(location.hash).toBe('#the-project');
			// The button pressed is current, and the stop.
			expect(currentNames()).toEqual([nameOf(name)]);
			expect(stops()).toEqual([name]);
		}
	});

	it('scrolls without motion when the user asks for reduced motion (§7 Motion)', async () => {
		media((query) => query.includes('prefers-reduced-motion: reduce'));
		const scrolled = stubScroll();
		render(PumpsNav, { props: { sections: sectionsOf(ALL) } });
		await fireEvent.click(button('Station'));
		expect(scrolled).toHaveBeenLastCalledWith({ block: 'start', behavior: 'auto' });
	});

	it('clamps the stop when the buttons change: the same section, else the nearest earlier one', async () => {
		stubScroll();
		const sections = sectionsOf(ALL);
		const { rerender } = render(PumpsNav, { props: { sections } });
		await fireEvent.click(button('Group chart'));
		expect(stops()).toEqual([button('Group chart')]);
		// The station's sections go (the card closed, the last member unticked): Pumps together.
		const without = sections.filter((s) => s.key !== 'station' && s.key !== 'group-chart');
		await rerender({ sections: without });
		expect(buttons().map(nameOf)).not.toContain('Group chart');
		expect(stops()).toEqual([button('Pumps together')]);
		expect(currentNames()).toEqual(['Pumps together']);
		// They come back: the section the user was in is current again.
		await rerender({ sections });
		expect(stops()).toEqual([button('Group chart')]);
	});

	it('marks a button by its section’s worst mark, its name the label then the mark’s words (§5.4 Marks)', () => {
		render(PumpsNav, {
			props: {
				sections: sectionsOf(ALL, {
					'pump-chart': sectionMark({ failed: true }),
					station: sectionMark({ warning: true }),
					'group-chart': sectionMark({ refused: true, failed: true }),
					combinations: sectionMark({ invalid: true, warning: true })
				})
			}
		});
		expect(buttons().map(nameOf)).toEqual([
			'Per pump',
			'Pump chart, a request failed',
			'Pumps together',
			'Station, has warnings',
			'Group chart, has a refusal',
			'Add cases',
			'Running combinations, has physically invalid values'
		]);
		expect(button('Running combinations, has physically invalid values')).toBeInTheDocument();
		// The icon is aria-hidden (Icon); a button with no mark has none, and no aria-label.
		for (const b of buttons()) {
			const icon = b.querySelector('svg');
			expect(!!icon, nameOf(b)).toBe(nameOf(b).includes(','));
			expect(b.hasAttribute('aria-label'), nameOf(b)).toBe(!!icon);
			if (icon) expect(icon).toHaveAttribute('aria-hidden', 'true');
		}
		// Only the label is shown, and it starts the name (WCAG 2.5.3); the warning's icon is the
		// amber alert, the invalid one's the red octagon.
		expect(button('Station, has warnings')).toHaveTextContent(/^Station$/);
		expect(button('Station, has warnings').querySelector('svg')).toHaveClass('text-amber-700');
		expect(
			button('Running combinations, has physically invalid values').querySelector('svg')
		).toHaveClass('text-red-700');
	});

	it('gives "Back to the sections" the current button (§5.4 The way back)', async () => {
		stubScroll();
		const { component } = render(PumpsNav, { props: { sections: sectionsOf(ALL) } });
		await fireEvent.click(button('Add cases'));
		expect(document.activeElement).not.toBe(button('Add cases'));
		component.focusCurrent();
		expect(document.activeElement).toBe(button('Add cases'));
	});
});

// ---- Where you are, and the pinning (observer-driven) --------------------------------------------

describe('the section nav in its pane', () => {
	beforeEach(() => {
		vi.stubGlobal('IntersectionObserver', FakeObserver);
		vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(box);
	});

	/** The pane's scroller: its top at 100 px, `height` px seen. */
	function pane(height = 600) {
		const scroller = document.createElement('div');
		Object.defineProperty(scroller, 'clientHeight', { value: height });
		document.body.append(scroller);
		holders.push(scroller);
		boxes.set(scroller, { top: 100, bottom: 100 + height });
		const canvas = document.createElement('div');
		scroller.append(canvas);
		boxes.set(canvas, { top: 150, bottom: 774 });
		return { scroller, canvas };
	}
	/** Put each section's top at a place, in viewport px. */
	function place(sections: SectionTarget[], tops: number[]) {
		sections.forEach((s, i) => boxes.set(s.target, { top: tops[i]!, bottom: tops[i]! + 20 }));
	}

	it('marks where you are: the target passed last under the nav, the first when none; follows the scroll', async () => {
		const { scroller, canvas } = pane();
		const sections = sectionsOf(ALL);
		// The line: the pane's top (100), the nav (53) and the targets' half rem (8), and 1 px.
		place(sections, [180, 900, 2000, 2400, 2700, 4000, 4500]);
		render(PumpsNav, { props: { sections, scroller, canvas } });
		await observe();
		expect(currentNames()).toEqual(['Per pump']);
		place(sections, [-1500, -700, 162, 500, 800, 2100, 2600]);
		await observe();
		expect(currentNames()).toEqual(['Pumps together']);
		place(sections, [-3000, -2300, -1600, -1000, 155, 1000, 1500]);
		await observe();
		expect(currentNames()).toEqual(['Group chart']);
		// Its root reaches below the pane, so a jump past it is seen; its top margin is the nav's,
		// the targets' 0.5 rem and 1 px, so a target at rest 0.5 rem under the nav (161) lies across
		// the root's top edge (162): seen to arrive there and to leave (S2 check NAV2-LEAVE).
		const observer = FakeObserver.all.find((o) => o.targets.has(sections[0]!.target))!;
		expect(observer.root).toBe(scroller);
		expect(observer.rootMargin).toBe('-62px 0px 100000px 0px');
	});

	it('moves aria-current only, never the stop, while the focus is in the toolbar', async () => {
		const { scroller, canvas } = pane();
		const sections = sectionsOf(ALL);
		place(sections, [180, 900, 2000, 2400, 2700, 4000, 4500]);
		render(PumpsNav, { props: { sections, scroller, canvas } });
		await observe();
		button('Per pump').focus();
		await tick();
		place(sections, [-3000, -2300, -1600, 150, 800, 2100, 2600]);
		await observe();
		expect(currentNames()).toEqual(['Station']);
		expect(stops()).toEqual([button('Per pump')]);
	});

	it('keeps a pressed target current that the pane cannot bring up, while it is on screen', async () => {
		stubScroll();
		const { scroller, canvas } = pane();
		const sections = sectionsOf(ALL);
		place(sections, [-6000, -5300, -4600, -4000, -3000, 150, 450]);
		render(PumpsNav, { props: { sections, scroller, canvas } });
		await observe();
		expect(currentNames()).toEqual(['Add cases']);
		// At the pane's end Running combinations stays below the line: pressed, it is current.
		await fireEvent.click(button('Running combinations'));
		await observe();
		expect(currentNames()).toEqual(['Running combinations']);
		// Scrolled up out of sight, the scroll says where you are again.
		place(sections, [-4000, -3300, -2600, -2000, 150, 1200, 1450]);
		await observe();
		expect(currentNames()).toEqual(['Group chart']);
	});

	it('reads the pane again when a press’s scroll ends: the section pressed is current where it stops (§5.4 Where you are)', async () => {
		stubScroll();
		const { scroller, canvas } = pane();
		const sections = sectionsOf(ALL);
		place(sections, [180, 900, 2000, 2400, 2700, 4000, 4500]);
		render(PumpsNav, { props: { sections, scroller, canvas } });
		await observe();
		expect(currentNames()).toEqual(['Per pump']);
		// A smooth scroll to Add cases. A scroll that ended just before it (the focus bringing the
		// nav into view) ends now, Add cases still below the pane (100 to 700): it is read, and
		// the press's scroll still watched.
		await fireEvent.click(button('Add cases'));
		scroller.dispatchEvent(new Event('scrollend'));
		await tick();
		// On the way Group chart crosses the line while Add cases is still below the pane.
		place(sections, [-2000, -1300, -200, 100, 150, 900, 1400]);
		await observe();
		// It stops with Add cases at rest, 0.5 rem under the nav (100 + 53 + 8): here no observer
		// callback runs, so the read is the scroll's end's.
		place(sections, [-2800, -2100, -1000, -700, -650, 161, 600]);
		scroller.dispatchEvent(new Event('scrollend'));
		await tick();
		expect(currentNames()).toEqual(['Add cases']);
		// From the top again, Running combinations, which the pane cannot bring to the line (at
		// its end): pressed while still below the pane, it stays current where the scroll stops.
		place(sections, [180, 900, 2000, 2400, 2700, 4000, 4500]);
		await observe();
		expect(currentNames()).toEqual(['Per pump']);
		await fireEvent.click(button('Running combinations'));
		scroller.dispatchEvent(new Event('scrollend'));
		place(sections, [-2400, -1700, -600, -300, -250, 150, 1000]);
		await observe();
		place(sections, [-2600, -1900, -800, -500, -450, -50, 450]);
		scroller.dispatchEvent(new Event('scrollend'));
		await tick();
		expect(currentNames()).toEqual(['Running combinations']);
		// The scroll over, the pane says where you are again.
		place(sections, [-1500, -800, 300, 600, 900, 2200, 2700]);
		await observe();
		expect(currentNames()).toEqual(['Pump chart']);
	});

	/** A pane whose scroll the test moves: its scrollTop, and each target's top that much higher. */
	function scrolling(scroller: HTMLElement, sections: SectionTarget[], start: number[]) {
		let at = 0;
		Object.defineProperty(scroller, 'scrollTop', {
			configurable: true,
			get: () => at,
			set: (v: number) => (at = v)
		});
		place(sections, start);
		return async (to: number) => {
			at = to;
			place(
				sections,
				start.map((t) => t - to)
			);
			await observe();
		};
	}

	it('ends a press its scroll stops short of: the user’s own scroll then brings the target in from below unmarked (§5.4 Where you are; S2 check NAV2-STUCK)', async () => {
		stubScroll();
		const { scroller, canvas } = pane();
		const sections = sectionsOf(ALL);
		const scrollTo = scrolling(scroller, sections, [180, 900, 2000, 2400, 2700, 4000, 4500]);
		render(PumpsNav, { props: { sections, scroller, canvas } });
		await observe();
		for (const cut of ['Home', 'a scrollbar dragged back'] as const) {
			await scrollTo(0);
			await fireEvent.click(button('Running combinations'));
			await frames(2);
			// The press's smooth scroll on its way, 1500 px down; then cut short, the pane back at its
			// top (Home) or at 600 px (the drag), where it stops, Running combinations still below
			// the pane (100 to 700).
			await scrollTo(1500);
			await scrollTo(cut === 'Home' ? 0 : 600);
			scroller.dispatchEvent(new Event('scrollend'));
			await frames(4);
			expect(currentNames(), cut).toEqual(['Per pump']);
			// Later the user's own scroll brings it in from below, Add cases passed: Add cases is
			// current, never the target before it is passed.
			await scrollTo(3850);
			expect(currentNames(), cut).toEqual(['Add cases']);
			await scrollTo(3950);
			expect(currentNames(), cut).toEqual(['Add cases']);
		}
	});

	it('keeps a press whose scroll goes on: a stop before its first frame, or one after which the pane goes on toward the target (§5.4 Where you are; S2 check NAV2-STUCK)', async () => {
		stubScroll();
		const { scroller, canvas } = pane();
		const sections = sectionsOf(ALL);
		const scrollTo = scrolling(scroller, sections, [180, 900, 2000, 2400, 2700, 4000, 4500]);
		render(PumpsNav, { props: { sections, scroller, canvas } });
		await observe();
		await fireEvent.click(button('Running combinations'));
		// A stop before the first frame after the press ends a scroll begun before it (the focus
		// bringing the nav into view, at 320×640): the press holds, though the pane has not moved.
		scroller.dispatchEvent(new Event('scrollend'));
		await frames(4);
		// A stop on the way (a scroll it took over ended), after which the pane goes on toward the
		// target: the press holds.
		await scrollTo(1500);
		scroller.dispatchEvent(new Event('scrollend'));
		await scrollTo(1600);
		await frames(4);
		// It stops at the pane's end, Running combinations on screen under the line: current.
		await scrollTo(3950);
		scroller.dispatchEvent(new Event('scrollend'));
		await tick();
		expect(currentNames()).toEqual(['Running combinations']);
	});

	it('brings a static nav back into view with the focus an arrow key moves; pinned, the focus scrolls nothing (§5.4 Focus never hidden)', async () => {
		const { scroller, canvas } = pane();
		render(PumpsNav, { props: { sections: sectionsOf(ALL), scroller, canvas } });
		await observe();
		expect(nav()).not.toHaveAttribute('data-pinned');
		// Static, the nav scrolls out above the pane while the pump canvas is still in view: the
		// focus brings it back.
		const chart = vi.spyOn(button('Pump chart'), 'focus');
		button('Per pump').focus();
		await fireEvent.keyDown(button('Per pump'), { key: 'ArrowRight' });
		expect(document.activeElement).toBe(button('Pump chart'));
		expect(chart).toHaveBeenCalledWith({ preventScroll: false });
		// Pinned, it is in sight: the focus scrolls nothing, the row alone brings the button in.
		boxes.set(canvas, { top: -524, bottom: 100 });
		await observe();
		expect(nav()).toHaveAttribute('data-pinned');
		const together = vi.spyOn(button('Pumps together'), 'focus');
		await fireEvent.keyDown(button('Pump chart'), { key: 'ArrowRight' });
		expect(document.activeElement).toBe(button('Pumps together'));
		expect(together).toHaveBeenCalledWith({ preventScroll: true });
	});

	it('pins only once the pump canvas has scrolled out above the pane’s top', async () => {
		const { scroller, canvas } = pane();
		const pinned = vi.fn();
		render(PumpsNav, { props: { sections: sectionsOf(ALL), scroller, canvas, onpinned: pinned } });
		await observe();
		expect(nav()).not.toHaveAttribute('data-pinned');
		expect(nav()).not.toHaveClass('sticky');
		expect(pinned).toHaveBeenLastCalledWith(null);
		// Its bottom 1 px under the pane's top: still in view.
		boxes.set(canvas, { top: -523, bottom: 101 });
		await observe();
		expect(nav()).not.toHaveAttribute('data-pinned');
		boxes.set(canvas, { top: -524, bottom: 100 });
		await observe();
		expect(nav()).toHaveAttribute('data-pinned');
		expect(nav()).toHaveClass('sticky', '-top-4', 'z-[35]', 'bg-white');
		expect(pinned).toHaveBeenLastCalledWith(53);
		// Back in view: static again.
		boxes.set(canvas, { top: 0, bottom: 624 });
		await observe();
		expect(nav()).not.toHaveAttribute('data-pinned');
		expect(pinned).toHaveBeenLastCalledWith(null);
		// Its root reaches below the pane: "not intersecting" is "above its top", seen after a jump.
		const observer = FakeObserver.all.find((o) => o.targets.has(canvas))!;
		expect(observer.rootMargin).toBe('0px 0px 100000px 0px');
	});

	it('pins only while it takes at most 15 % of the pane’s height', async () => {
		// 53 px: at most 15 % of 354 px (53.1), more than 15 % of 353 (52.95).
		for (const [height, expected] of [
			[353, false],
			[354, true]
		] as const) {
			const { scroller, canvas } = pane(height);
			boxes.set(canvas, { top: -1000, bottom: -376 });
			const { unmount } = render(PumpsNav, {
				props: { sections: sectionsOf(ALL), scroller, canvas }
			});
			await observe();
			expect(nav().hasAttribute('data-pinned'), `a ${height} px pane`).toBe(expected);
			unmount();
		}
	});

	it('never pins under short: (the workspace scrolls as one page), nor while the view is hidden', async () => {
		media((query) => query.includes('max-height: 20rem'));
		const first = pane();
		boxes.set(first.canvas, { top: -1000, bottom: -376 });
		const { unmount } = render(PumpsNav, {
			props: { sections: sectionsOf(ALL), scroller: first.scroller, canvas: first.canvas }
		});
		await observe();
		expect(nav()).not.toHaveAttribute('data-pinned');
		unmount();
		window.matchMedia = realMatchMedia;
		const second = pane();
		boxes.set(second.canvas, { top: -1000, bottom: -376 });
		const { rerender } = render(PumpsNav, {
			props: {
				sections: sectionsOf(ALL),
				scroller: second.scroller,
				canvas: second.canvas,
				active: false
			}
		});
		await observe();
		expect(nav()).not.toHaveAttribute('data-pinned');
		// Hidden, nothing observes the pane (§5.4: paused).
		expect(FakeObserver.all).toEqual([]);
		await rerender({ active: true });
		await observe();
		expect(nav()).toHaveAttribute('data-pinned');
	});
});

// ---- In the workspace ----------------------------------------------------------------------------

interface Answer {
	status: number;
	body: unknown;
}
interface Responses {
	solve: SolveResponse;
	groupCurve: Answer;
	systemCurve: Answer | null;
}
interface FixtureCase extends Responses {
	name: string;
	project: Project;
	scenarioCases?: Record<string, Responses>;
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;

const getContext = HTMLCanvasElement.prototype.getContext;
const consoleError = console.error;

describe('the section nav in the Pumps view', () => {
	beforeEach(() => {
		HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
		console.error = (...args: unknown[]) => {
			if (String(args[0]).startsWith('Failed to create chart')) return;
			consoleError(...args);
		};
	});
	afterEach(() => {
		HTMLCanvasElement.prototype.getContext = getContext;
		console.error = consoleError;
	});

	/** The fixture's answers by scenario id (another scenario: the base's). */
	function setup(c: FixtureCase, solve?: Solver['solve']) {
		const of = (id: string | undefined): Responses => (id && c.scenarioCases?.[id]) || c;
		const solver: Solver = {
			solve: solve ?? (async (_p, _o, request) => structuredClone(of(request?.scenarioId).solve)),
			groupCurve: async (_p, _ids, request) => {
				const answer = of(request?.scenarioId);
				const sent = request?.curve === 'system' ? answer.systemCurve! : answer.groupCurve;
				return structuredClone(sent.body as PumpGroupCurveResponse);
			}
		};
		const ws = testWorkspace(structuredClone(c.project), { solver });
		render(WorkspaceView, { workspace: ws });
		return ws;
	}
	const results = () => within(screen.getByRole('region', { name: 'Results' }));
	const card = () => results().getByRole('region', { name: /^Pumps together/ }) as HTMLElement;
	const toggle = () => within(card()).getByRole('button', { name: /^Pumps together/ });
	/** The buttons' names; `labels`, their words before a mark's (", has warnings"). */
	const names = () =>
		within(results().getByRole('toolbar', { name: 'Go to' }))
			.getAllByRole('button')
			.map(nameOf);
	const labels = () => names().map((name) => name.split(',')[0]);

	it('is drawn with the Pumps together card (two pumps with results), the tab’s first child; not with one pump', async () => {
		const ws = setup(named('parallel-ideal'));
		await ws.solve();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		const panel = results().getByRole('tabpanel', { name: 'Pumps' });
		const navigation = within(panel).getByRole('navigation', { name: 'Pumps view sections' });
		expect(panel.firstElementChild!.firstElementChild).toBe(navigation);
		expect(labels()).toEqual(['Per pump', 'Pump chart', 'Pumps together']);
		// The tab's --pumps-nav-h and the targets' scroll margins read it.
		expect((panel.firstElementChild as HTMLElement).style.getPropertyValue('--pumps-nav-h')).toBe(
			'0px'
		);
	});

	it('is not drawn with one pump', async () => {
		const ws = testWorkspace(pumpTransferExample(), {
			solver: { solve: async () => response(pumpTransferSolved()) }
		});
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		expect(results().queryByRole('navigation', { name: 'Pumps view sections' })).toBeNull();
		expect(results().queryByRole('button', { name: 'Back to the sections' })).toBeNull();
	});

	it('draws a button per section drawn, in document order: the card closed, then open with its sections', async () => {
		const ws = setup(named('one-off'));
		await ws.solveAll();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		expect(labels()).toEqual(['Per pump', 'Pump chart', 'Pumps together']);
		await fireEvent.click(toggle());
		await waitFor(() =>
			expect(labels()).toEqual([
				'Per pump',
				'Pump chart',
				'Pumps together',
				'Station',
				'Group chart',
				'Add cases',
				'Running combinations'
			])
		);
		// Each button's target: the headings (tabindex −1), the card's toggle for Pumps together.
		const expected = [
			results().getByRole('heading', { name: 'Results per pump' }),
			results().getByRole('heading', { name: 'Pump chart' }),
			toggle(),
			within(card()).getByRole('heading', { name: 'Station' }),
			within(card()).getByRole('heading', { name: 'Group chart' }),
			within(card()).getByRole('heading', { name: 'Add cases' }),
			within(card()).getByRole('heading', { name: 'Running combinations' })
		];
		const bar = within(results().getByRole('toolbar', { name: 'Go to' }));
		stubScroll();
		for (const [i, target] of expected.entries()) {
			await fireEvent.click(bar.getAllByRole('button')[i]!);
			expect(document.activeElement).toBe(target);
			if (target.tagName !== 'BUTTON') expect(target).toHaveAttribute('tabindex', '-1');
		}
		// The marks follow their sections: the base case's pumps have no flag, a current case's
		// do ("Pump PB off": Pump PA outside its curve, a warning), and this test's solver
		// computes no system curve, so the pump chart's request failed.
		expect(names()).toEqual([
			'Per pump',
			'Pump chart, a request failed',
			'Pumps together',
			'Station',
			'Group chart',
			'Add cases',
			'Running combinations, has warnings'
		]);
	});

	it('has no Station or Group chart with the card’s unavailable sentence, or with no member ticked; the stop clamps', async () => {
		let converged = true;
		const c = named('parallel-ideal');
		const ws = setup(c, async () => {
			const solved = structuredClone(c.solve);
			if (!converged) {
				solved.success = false;
				solved.solvedState.converged = false;
			}
			return solved;
		});
		await ws.solve();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(toggle());
		await waitFor(() => expect(labels()).toContain('Group chart'));
		stubScroll();
		const bar = () => within(results().getByRole('toolbar', { name: 'Go to' }));
		await fireEvent.click(bar().getByRole('button', { name: 'Group chart' }));
		// No member ticked: the station's sections go, and the stop with them to Pumps together.
		for (const box of within(card()).getAllByRole('checkbox')) {
			if ((box as HTMLInputElement).checked) await fireEvent.click(box);
		}
		await waitFor(() => expect(labels()).toEqual(['Per pump', 'Pump chart', 'Pumps together']));
		const stop = bar()
			.getAllByRole('button')
			.filter((b) => b.tabIndex === 0);
		expect(stop.map(nameOf)).toEqual(['Pumps together']);
		// The card closed: the same.
		await fireEvent.click(toggle());
		expect(labels()).toEqual(['Per pump', 'Pump chart', 'Pumps together']);
		// A solve that does not converge: the unavailable sentence, no station sections.
		await fireEvent.click(toggle());
		for (const box of within(card()).getAllByRole('checkbox')) {
			if (!(box as HTMLInputElement).checked) await fireEvent.click(box);
		}
		await waitFor(() => expect(labels()).toContain('Group chart'));
		converged = false;
		await ws.solve();
		await within(card()).findByText(
			'This solve did not converge: its values are not a solution, so the card shows none.'
		);
		expect(labels()).toEqual(['Per pump', 'Pump chart', 'Pumps together']);
	});

	it('marks Station with the group curve’s refusal, which heads it since S3; "Go to the pump chart" in "How to read this chart" goes there (pumps-results-layout.md §5.3, §6.2)', async () => {
		const c = named('refused');
		const body = c.groupCurve.body as { message: string; issues: TopologyIssue[] };
		const solver: Solver = {
			// No flags, so the refusal is Station's worst mark (a warning would outrank it, §5.4).
			solve: async () => {
				const solved = structuredClone(c.solve);
				solved.solvedState.flags = [];
				return solved;
			},
			groupCurve: async () => {
				throw new NotAStationError(body.message, [body.message], body.issues);
			}
		};
		const ws = testWorkspace(structuredClone(c.project), { solver });
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(toggle());
		// Nothing is suggested here: the user ticks the pumps.
		for (const box of within(card()).getAllByRole('checkbox') as HTMLInputElement[]) {
			if (!box.checked) await fireEvent.click(box);
		}
		await within(card()).findByText(/^These pumps do not form a station/);
		await waitFor(() => expect(names()).toContain('Station, has a refusal'));
		// The group chart's own requests neither failed nor were refused: no mark there.
		expect(names()).toContain('Group chart');
		expect(names().filter((n) => n.startsWith('Group chart'))).toEqual(['Group chart']);
		// "Go to the pump chart": a button in the reference, focusing the pump chart's heading
		// as the nav's own button does, never touching the link (D3).
		const reading = card().querySelector('[data-group-reading]')!;
		await fireEvent.click(reading.querySelector('summary')!);
		const scrolled = stubScroll();
		const hash = location.hash;
		await fireEvent.click(
			within(reading as HTMLElement).getByRole('button', { name: 'Go to the pump chart' })
		);
		const heading = results().getByRole('heading', { name: 'Pump chart' });
		expect(document.activeElement).toBe(heading);
		expect(scrolled.mock.contexts.at(-1)).toBe(heading);
		expect(location.hash).toBe(hash);
	});

	it('ends each card with "Back to the sections", visually hidden until focused, which focuses the nav’s current button', async () => {
		const ws = setup(named('parallel-ideal'));
		await ws.solve();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(toggle());
		await waitFor(() => expect(labels()).toContain('Station'));
		const back = results().getAllByRole('button', { name: 'Back to the sections' });
		expect(back).toHaveLength(2);
		const pumpCard = results().getByRole('heading', { name: 'Pump chart' }).closest('.card')!;
		// Each its card's last control, after every other control of that card.
		for (const [i, container] of [pumpCard, card()].entries()) {
			const controls = container.querySelectorAll('button, input, select, summary, [tabindex="0"]');
			expect(controls[controls.length - 1]).toBe(back[i]);
			expect(back[i]).toHaveClass('sr-only', 'focus:not-sr-only');
		}
		stubScroll();
		const bar = within(results().getByRole('toolbar', { name: 'Go to' }));
		// Both pumps' NPSH is not checked (a warning flag each): Station carries it.
		const station = bar.getByRole('button', { name: 'Station, has warnings' });
		await fireEvent.click(station);
		await fireEvent.click(back[1]!);
		expect(document.activeElement).toBe(station);
		await fireEvent.click(back[0]!);
		expect(document.activeElement).toBe(station);
	});
});
