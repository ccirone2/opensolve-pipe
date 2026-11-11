/**
 * The Results pane's Pumps tab below the pump chart (proposal pumps-results-layout.md), measured
 * in the running app, so a later slice that breaks a budget fails CI as the Build pane's do
 * (tests/build-density.e2e.ts). The audit's probe (§2, its measure.mjs) is the support below: the
 * three views it measured and what it read in each (§2.1), each view recorded at the project's
 * size and, on the phone, at 320×640 too. The budgets of §5.7 join with their slices (§9).
 *
 * S0 (§9): the Results pane's own scroller, the element that scrolls the tab, never scrolls
 * sideways (§5.7 row 1). The audit found it scrolling in the condenser example, its cases added and
 * the card open, at both sizes, while the page did not (§2.1; F10: the four "Also found" buttons
 * did not wrap), so the check reads that scroller as well as `document.documentElement`, and the
 * other two views are held to it too.
 *
 * With PUMPS_LAYOUT_RECORD set to a directory, each view's numbers (JSON), its accessibility
 * snapshot and the pane's screenshots from the pump chart's canvas down (one per screen of the
 * pane, at CSS pixels) are written there: the before and after records of each slice.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import {
	expect,
	test,
	type JSHandle,
	type Locator,
	type Page,
	type TestInfo
} from '@playwright/test';
import { gzip } from 'pako';
import type { Project } from '../src/lib/api/types';
import { exampleProject, pumpTransferExample } from '../src/lib/utils/examples';
import { canonicalJson } from '../src/lib/utils/json';
import { IMPERIAL_UNITS } from '../src/lib/utils/units';
import {
	buildPane,
	caseGroup,
	chooseCase,
	curveTableFold,
	openCases,
	openCurveTable,
	resultsPane,
	resultsScroller,
	resultsView,
	setNumber,
	showPane,
	solve,
	solveConverged,
	traceOf
} from './support';

interface FixtureCase {
	name: string;
	project: Project;
}
const fixture = JSON.parse(
	readFileSync(
		new URL('../src/lib/utils/__fixtures__/pump-groups-input.json', import.meta.url),
		'utf8'
	)
) as { cases: FixtureCase[] };
const projectOf = (name: string) =>
	structuredClone(fixture.cases.find((c) => c.name === name)!.project);

/** Open a project by its link, as utils/encoding.ts writes it (canonical JSON, gzip, base64url). */
async function open(page: Page, project: Project) {
	const bytes = gzip(new TextEncoder().encode(canonicalJson(project)), { level: 9 });
	await page.goto(`/p#${Buffer.from(bytes).toString('base64url')}`);
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
}

const RECORD = process.env.PUMPS_LAYOUT_RECORD ?? '';

// ---- The views (§2) -----------------------------------------------------------------------------

/** Count the solves the page is answered from now on. */
function solveCounter(page: Page): { n: number } {
	const counter = { n: 0 };
	page.on('response', (r) => {
		if (r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST') counter.n++;
	});
	return counter;
}

/** Solve all from the Scenarios menu, and wait for its `expected` solves and the run's end. */
async function solveAll(page: Page, counter: { n: number }, expected: number) {
	const start = counter.n;
	await (await openCases(page)).getByRole('button', { name: 'Solve all' }).click();
	await expect.poll(() => counter.n - start, { timeout: 180_000 }).toBe(expected);
	await expect(caseGroup(page)).not.toContainText('Solving', { timeout: 60_000 });
	if (await page.getByRole('group', { name: 'Case', exact: true }).isVisible()) {
		await page.keyboard.press('Escape');
	}
	await showPane(page, 'Results');
	await expect(resultsPane(page).getByRole('heading', { name: 'Converged' })).toBeVisible();
}

/** The Pumps tab at rest: nothing busy and no request in progress, for `stable` ms on end. */
async function settle(page: Page, stable = 1500) {
	let since = 0;
	await expect
		.poll(
			async () => {
				const quiet = await page.evaluate(() => {
					const pane = document.querySelector('section[aria-label="Results"]');
					const tab = [...(pane?.querySelectorAll('[role="tabpanel"]') ?? [])].find(
						(p) => !(p as HTMLElement).hidden
					) as HTMLElement | undefined;
					if (!tab) return false;
					// Busy is a figure's or, from S1, its canvas's (pumps-results-layout.md §5.3).
					if (tab.querySelector('[aria-busy="true"]')) return false;
					return !/Computing|Solving/.test(tab.innerText);
				});
				if (!quiet) {
					since = 0;
					return false;
				}
				since ||= Date.now();
				return Date.now() - since >= stable;
			},
			{ timeout: 240_000, intervals: [250] }
		)
		.toBe(true);
}

async function pumpsTab(page: Page): Promise<Locator> {
	await showPane(page, 'Results');
	return resultsView(page, 'Pumps');
}

/** The Pumps together card, opened, its first requests answered. */
async function openCard(page: Page, tab: Locator): Promise<Locator> {
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const toggle = card.getByRole('button', { name: /^Pumps together/ });
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'true');
	await settle(page);
	return card;
}

/**
 * 1. one-off (`pump-groups-input.json`): 2 pumps and 4 scenarios after Solve all (5 solves), the
 * Pumps tab with its defaults (the card closed, no data table, every chip on), Pump PA viewed.
 */
async function oneOff(page: Page) {
	const counter = solveCounter(page);
	await open(page, projectOf('one-off'));
	await solveAll(page, counter, 5);
	const tab = await pumpsTab(page);
	await tab.getByRole('combobox', { name: 'Pump chart' }).selectOption('PA');
	await settle(page);
	return { solves: counter.n };
}

/**
 * 2. lineups (the same fixture): 4 pumps on Crane tees and 8 scenarios after Solve all (9 solves);
 * the card open, "Also show the other cases' station duties" ticked (the rings and the curve
 * family drawn), both data tables shown and every disclosure at or below the chart opened. The
 * project can be given, with names of its own (the long-name test).
 */
async function lineups(page: Page, project: Project = projectOf('lineups')) {
	const counter = solveCounter(page);
	await open(page, project);
	await solveAll(page, counter, 9);
	const tab = await pumpsTab(page);
	const card = await openCard(page, tab);
	await card.getByRole('checkbox', { name: "Also show the other cases' station duties" }).check();
	await expect(card.getByRole('figure').getByRole('img')).toHaveAccessibleName(
		/other cases' group curves drawn/,
		{ timeout: 240_000 }
	);
	await settle(page, 2500);
	// A pressed one is renamed "Hide data table": press the first one left, until none is.
	for (let i = 0; i < 4; i++) {
		const show = tab.getByRole('button', { name: 'Show data table' });
		if (!(await show.count())) break;
		await show.first().click();
	}
	// The first closed disclosure at or below the pump chart, found anew each round since an opened
	// one can hold more, pressed as a user would, until none is closed.
	const summaries = tab.locator('details > summary');
	for (let round = 0; round < 60; round++) {
		const index = await summaries.evaluateAll((all) => {
			const figure = [...document.querySelectorAll('section[aria-label="Results"] figure')].find(
				(f) =>
					(f.querySelector(':scope > figcaption')?.textContent ?? '')
						.trim()
						.startsWith('Pump and system curves')
			);
			const top = figure!.querySelector('[role="img"]')!.getBoundingClientRect().top;
			return all.findIndex((s) => {
				const r = s.getBoundingClientRect();
				return (
					!(s.parentElement as HTMLDetailsElement).open &&
					s.checkVisibility() &&
					r.height > 1 &&
					r.top >= top
				);
			});
		});
		if (index < 0) break;
		await summaries.nth(index).click();
	}
	await settle(page);
	const details = await tab.locator('details').evaluateAll((all) => ({
		total: all.length,
		open: all.filter((d) => (d as HTMLDetailsElement).open).length
	}));
	return { solves: counter.n, details };
}

/**
 * 3. condenser (the example "Chiller plant condenser water system"): 6 pumps and 1 scenario; the
 * base case solved, the card open, Add cases by number running pressed (5 cases, "Also show the
 * other cases' station duties" ticked by it), then the block's Solve all: 7 solves in all.
 */
async function condenser(page: Page) {
	const counter = solveCounter(page);
	await open(page, exampleProject('condenser-water')!);
	await solveConverged(page);
	const tab = await pumpsTab(page);
	const card = await openCard(page, tab);
	const block = card.getByRole('region', { name: 'Add cases' });
	const preset = block.getByRole('radio', { name: 'By number running' });
	if (!(await preset.isChecked())) await preset.click();
	await expect(preset).toBeChecked();
	const add = block.getByRole('button', { name: /^Add \d+ cases?$/ });
	const added = (await add.innerText()).trim();
	await add.click();
	const solveAllButton = block.getByRole('button', { name: /^Solve all/ });
	await expect(solveAllButton).toBeFocused();
	await solveAllButton.click();
	await expect.poll(() => counter.n, { timeout: 240_000 }).toBe(7);
	await expect(solveAllButton).toHaveText('Solve all', { timeout: 240_000 });
	await expect(solveAllButton).toHaveAttribute('aria-disabled', 'true');
	await settle(page, 3000);
	// The Add's notice sits over the pane's foot: dismissed, as a user would.
	const dismiss = page.getByRole('button', { name: 'Dismiss' }).first();
	if (await dismiss.isVisible()) await dismiss.click();
	return { solves: counter.n, added };
}

// ---- What the probe reads, in the page (§2) ----------------------------------------------------

/**
 * The audit's numbers for the tab shown (measure.mjs `collect`), in px from the bottom of the pump
 * chart's canvas: the pane, the charts, the outline, the paragraphs and controls below the chart
 * (each control's distance below the nearest chart above it), the blocks of the figure and the
 * card, the runs of notes with no heading or control between them, and what overflows sideways.
 */
function collect() {
	const results = document.querySelector('section[aria-label="Results"]')!;
	const panel = [...results.querySelectorAll('[role="tabpanel"]')].find(
		(p) => !(p as HTMLElement).hidden
	) as HTMLElement;
	const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
	const text = (el: Element | null | undefined) =>
		squash((el as HTMLElement | null)?.innerText ?? el?.textContent ?? '');
	const pumpFigure = [...panel.querySelectorAll('figure')].find((f) =>
		text(f.querySelector(':scope > figcaption')).startsWith('Pump and system curves')
	)!;
	const chart = pumpFigure.querySelector('[role="img"]')!;
	const card = panel.querySelector('[data-pumps-together]');
	const groupFigure = card?.querySelector('figure') ?? null;
	const groupChart = groupFigure?.querySelector('[role="img"]') ?? null;
	const cr = chart.getBoundingClientRect();
	const base = cr.bottom;
	const pr = panel.getBoundingClientRect();
	const R = Math.round;
	const y = (el: Element) => R(el.getBoundingClientRect().top - base);
	const h = (el: Element) => R(el.getBoundingClientRect().height);

	/** Out of sight for screen readers only: sr-only, or a responsive max-sm:sr-only applied. */
	const srOnly = (el: Element) => {
		for (let e: Element | null = el; e && e !== panel; e = e.parentElement) {
			if (e.classList.contains('sr-only')) return true;
			const cs = getComputedStyle(e);
			if (
				cs.position === 'absolute' &&
				parseFloat(cs.width) <= 1 &&
				parseFloat(cs.height) <= 1 &&
				(cs.overflow === 'hidden' || /inset\(50%\)/.test(cs.clipPath) || cs.clip !== 'auto')
			)
				return true;
		}
		return false;
	};
	const shown = (el: Element | null | undefined): boolean => {
		if (!el || srOnly(el)) return false;
		if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
		const r = el.getBoundingClientRect();
		return r.width > 1 && r.height > 1;
	};
	type Labelled = Element & { labels?: NodeListOf<HTMLLabelElement> | null };
	/** A control is visible when it or its label is (the segments' radios are transparent). */
	const controlShown = (el: Labelled) => {
		if (shown(el)) return true;
		const label = el.labels?.[0] ?? el.closest('label');
		return !!label && shown(label);
	};
	// The section nav (S2, §5.4) is the tab's first child, above the pump chart: pinned, it sits
	// over the area below the canvas but is not part of it, so none of the probe's counts holds it.
	const below = (el: Element) =>
		!el.closest('[data-pumps-nav]') && el.getBoundingClientRect().top >= base - 0.5;

	function nameOf(el: Labelled): string {
		const aria = el.getAttribute('aria-label');
		if (aria) return squash(aria);
		const by = el.getAttribute('aria-labelledby');
		if (by)
			return squash(
				by
					.split(/\s+/)
					.map((id) => text(document.getElementById(id)))
					.join(' ')
			);
		switch (el.tagName) {
			case 'FIELDSET':
				return text(el.querySelector(':scope > legend'));
			case 'FIGURE':
				return text(el.querySelector(':scope > figcaption'));
			case 'TABLE':
				return text(el.querySelector(':scope > caption'));
			case 'DETAILS':
				return text(el.querySelector(':scope > summary'));
		}
		if (el.labels?.length) return text(el.labels[0]);
		if (el.tagName === 'INPUT' && el.closest('label')) return text(el.closest('label'));
		return text(el);
	}
	const clip = (s: string, n = 90) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

	// The outline: headings, regions, groups, figures, tables, disclosures and named lists, with
	// their depth among these containers.
	const OUTLINE =
		'h1,h2,h3,h4,h5,h6,section,[role=region],fieldset,[role=group],[role=radiogroup],figure,table,details,ul[aria-label],ol[aria-label],dl[aria-label],[role=list][aria-label],ul[aria-labelledby],[role=img]';
	const CONTAINERS =
		'section,[role=region],fieldset,[role=group],[role=radiogroup],figure,details,table';
	const outline = [];
	for (const el of panel.querySelectorAll(OUTLINE)) {
		if (!shown(el)) continue;
		const tag = el.tagName.toLowerCase();
		const role = el.getAttribute('role');
		const kind = /^h[1-6]$/.test(tag)
			? tag
			: role === 'img'
				? 'chart'
				: role
					? role
					: tag === 'section'
						? 'region'
						: tag === 'fieldset'
							? 'group'
							: tag === 'figure'
								? 'figure'
								: tag === 'table'
									? 'table'
									: tag === 'details'
										? (el as HTMLDetailsElement).open
											? 'disclosure (open)'
											: 'disclosure (closed)'
										: `list:${tag}`;
		if (kind === 'region' && !el.getAttribute('aria-labelledby') && !el.getAttribute('aria-label'))
			continue;
		const name = nameOf(el);
		let depth = 0;
		for (let e = el.parentElement; e && e !== panel; e = e.parentElement) {
			if (e.matches(CONTAINERS) && shown(e)) depth++;
		}
		outline.push({
			kind,
			level: /^h[1-6]$/.test(tag) ? Number(tag[1]) : null,
			depth,
			name: clip(kind === 'chart' ? `(canvas) ${name.slice(0, 60)}` : name, 120),
			y: y(el),
			height: h(el),
			below: below(el)
		});
	}

	// Paragraphs below the chart.
	const words = (s: string) => (s.match(/[\p{L}\p{N}][\p{L}\p{N}'’.-]*/gu) ?? []).length;
	const paragraphs = [...panel.querySelectorAll('p')]
		.filter((p) => shown(p) && below(p))
		.map((p) => ({
			y: y(p),
			height: h(p),
			words: words(text(p)),
			fontSize: getComputedStyle(p).fontSize,
			text: text(p)
		}));

	// Controls below the chart.
	const charts = [chart, groupChart].filter((c): c is Element => c !== null);
	const kindOf = (c: Element) =>
		c.tagName === 'INPUT'
			? `input:${(c as HTMLInputElement).type}`
			: c.tagName === 'BUTTON' && c.getAttribute('aria-pressed') !== null
				? 'button:toggle'
				: c.tagName === 'BUTTON' && c.getAttribute('aria-expanded') !== null
					? 'button:disclosure'
					: c.tagName.toLowerCase();
	const controls = [...panel.querySelectorAll<Labelled>('input,select,textarea,button,summary')]
		.filter((c) => controlShown(c) && below(c.labels?.[0] ?? c))
		.map((c) => {
			const box = (c.labels?.[0] && !shown(c) ? c.labels[0] : c).getBoundingClientRect();
			let near: { chart: Element; bottom: number } | null = null;
			for (const ch of charts) {
				const bottom = ch.getBoundingClientRect().bottom;
				if (bottom <= box.top + 0.5 && (!near || bottom > near.bottom))
					near = { chart: ch, bottom };
			}
			return {
				kind: kindOf(c),
				name: clip(nameOf(c), 100),
				y: R(box.top - base),
				x: R(box.left - pr.left),
				disabled:
					c.getAttribute('aria-disabled') === 'true' || (c as HTMLButtonElement).disabled === true,
				nearestChartAbove: near ? (near.chart === chart ? 'pump chart' : 'group chart') : null,
				pxBelowThatChart: near ? R(box.top - near.bottom) : null
			};
		});

	// Each block's place and height, for the containers that hold the area.
	const pumpCard = pumpFigure.closest('.card') ?? pumpFigure.parentElement!;
	const stackOf = (container: Element | null | undefined, label: string) =>
		container
			? [...container.children]
					.filter((c) => shown(c))
					.map((c) => ({
						in: label,
						tag:
							c.tagName.toLowerCase() +
							(c.getAttribute('role') ? `[${c.getAttribute('role')}]` : ''),
						label: clip(nameOf(c) || text(c), 80),
						y: y(c),
						height: h(c)
					}))
			: [];
	const cardBody = card?.querySelector(':scope > div[id$="-body"]') ?? null;
	const stack = [
		...stackOf(pumpFigure, 'pump chart figure').filter((b) => b.y >= -1),
		...stackOf(pumpFigure.querySelector('[id$="-table"]'), 'pump chart data table'),
		...stackOf(card, 'Pumps together card'),
		...stackOf(cardBody, 'card body'),
		...stackOf(groupFigure, 'group figure'),
		...stackOf(card?.querySelector('[id$="-data"]'), 'group data tables'),
		...stackOf(card?.querySelector('[data-add-cases]'), 'Add cases')
	];

	// Runs of paragraphs with nothing else between them (walls of notes), in document order.
	const BLOCKS =
		'p,h1,h2,h3,h4,h5,h6,input,select,button,summary,table,[role=img],legend,li,dt,ul,ol';
	const runs: {
		paragraphs: number;
		words: number;
		y: number;
		height: number;
		first: string;
		last: string;
		inCard: boolean;
		inDisclosure: boolean;
	}[] = [];
	let run: Element[] = [];
	const flush = () => {
		if (run.length >= 3) {
			runs.push({
				inCard: !!card && card.contains(run[0]!),
				inDisclosure: !!run[0]!.closest('details'),
				paragraphs: run.length,
				words: run.reduce((s, p) => s + words(text(p)), 0),
				y: y(run[0]!),
				height: R(run.at(-1)!.getBoundingClientRect().bottom - run[0]!.getBoundingClientRect().top),
				first: clip(text(run[0]), 100),
				last: clip(text(run.at(-1)), 100)
			});
		}
		run = [];
	};
	for (const el of panel.querySelectorAll<Labelled>(BLOCKS)) {
		if (!below(el)) continue;
		if (el.tagName === 'P') {
			if (!shown(el)) continue;
			if (run.length && run.at(-1)!.contains(el)) continue;
			run.push(el);
		} else if (shown(el) || controlShown(el)) {
			if (el.tagName === 'UL' || el.tagName === 'OL') {
				if (run.length) flush();
				continue;
			}
			if (run.some((p) => p.contains(el))) continue; // a link or Details inside a note
			flush();
		}
	}
	flush();

	// Sideways: the page, the pane's scroller, what sticks out of the tab, and the boxes that scroll.
	const row = results.querySelector('[role="tablist"][aria-label="Results view"]')!;
	let scroller: Element = document.scrollingElement!;
	for (let e = row.parentElement; e && e !== results; e = e.parentElement) {
		if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
			scroller = e;
			break;
		}
	}
	const inScrollBox = (el: Element) => {
		for (let e = el.parentElement; e && e !== panel; e = e.parentElement) {
			if (/(auto|scroll|hidden)/.test(getComputedStyle(e).overflowX)) return true;
		}
		return false;
	};
	const sticking = [];
	for (const el of panel.querySelectorAll('*')) {
		if (!shown(el) || !below(el) || inScrollBox(el)) continue;
		const r = el.getBoundingClientRect();
		if (r.right > pr.right + 1 || r.left < pr.left - 1)
			sticking.push({
				tag: el.tagName.toLowerCase(),
				name: clip(nameOf(el), 60),
				left: R(r.left - pr.left),
				right: R(r.right - pr.left)
			});
	}
	const sidewaysBoxes = [...panel.querySelectorAll('*')]
		.filter(
			(el) =>
				shown(el) &&
				below(el) &&
				el.scrollWidth > el.clientWidth + 1 &&
				/(auto|scroll)/.test(getComputedStyle(el).overflowX)
		)
		.map((el) => ({
			name: clip(nameOf(el), 80),
			clientWidth: el.clientWidth,
			scrollWidth: el.scrollWidth,
			y: y(el)
		}));
	const tallBoxes = [...panel.querySelectorAll('[role=region]')]
		.filter((el) => shown(el) && below(el) && el.scrollHeight > el.clientHeight + 1)
		.map((el) => ({
			name: clip(nameOf(el), 80),
			clientHeight: el.clientHeight,
			scrollHeight: el.scrollHeight,
			y: y(el)
		}));

	const fontSize = (el: Element | null | undefined) => (el ? getComputedStyle(el).fontSize : null);
	return {
		pane: {
			width: R(pr.width),
			scrollerClientHeight: scroller.clientHeight,
			scrollerIsDocument: scroller === document.scrollingElement
		},
		chart: { top: R(cr.top - pr.top), height: R(cr.height), width: R(cr.width) },
		groupChart: groupChart
			? {
					y: y(groupChart),
					height: h(groupChart),
					width: R(groupChart.getBoundingClientRect().width)
				}
			: null,
		belowChartHeightPx: R(pr.bottom - base),
		pumpChartBelowCanvasPx: R(pumpCard.getBoundingClientRect().bottom - base),
		card: card ? { y: y(card), height: h(card), open: !!cardBody } : null,
		outline,
		headingsBelowChart: outline.filter((o) => o.level !== null && o.below).length,
		paragraphs: {
			count: paragraphs.length,
			words: paragraphs.reduce((s, p) => s + p.words, 0),
			small: paragraphs.filter((p) => parseFloat(p.fontSize) <= 12).length,
			list: paragraphs
		},
		controls: { count: controls.length, list: controls },
		stack,
		runs,
		sideways: {
			documentScrollWidth: document.documentElement.scrollWidth,
			innerWidth: window.innerWidth,
			pageScrollsSideways: document.documentElement.scrollWidth > window.innerWidth,
			scrollerClientWidth: scroller.clientWidth,
			scrollerScrollWidth: scroller.scrollWidth,
			scrollerScrollsSideways: scroller.scrollWidth > scroller.clientWidth,
			stickingCount: sticking.length,
			sticking: sticking.slice(0, 20),
			sidewaysBoxes
		},
		tallBoxes,
		fontSizes: {
			figcaption: fontSize(pumpFigure.querySelector('figcaption')),
			cardHeading: fontSize(card?.querySelector('h3'))
		}
	};
}

/** The Tab stops from the pump chart's figure until the focus leaves the tab (measure.mjs). */
async function tabStops(page: Page): Promise<{ kind: string; name: string }[]> {
	await page.evaluate(() => {
		const figure = [...document.querySelectorAll('section[aria-label="Results"] figure')].find(
			(f) =>
				(f.querySelector(':scope > figcaption')?.textContent ?? '')
					.trim()
					.startsWith('Pump and system curves')
		) as HTMLElement;
		figure.focus();
	});
	const stops: { kind: string; name: string }[] = [];
	for (let i = 0; i < 600; i++) {
		await page.keyboard.press('Tab');
		const info = await page.evaluate(() => {
			const pane = document.querySelector('section[aria-label="Results"]')!;
			const panel = [...pane.querySelectorAll('[role="tabpanel"]')].find(
				(p) => !(p as HTMLElement).hidden
			);
			const a = document.activeElement as (HTMLElement & { labels?: NodeListOf<Element> }) | null;
			if (!a || !panel?.contains(a)) return null;
			const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
			const by = a.getAttribute('aria-labelledby');
			const label =
				a.getAttribute('aria-label') ||
				(by
					? by
							.split(/\s+/)
							.map((id) => squash(document.getElementById(id)?.textContent))
							.join(' ')
					: '') ||
				(a.labels?.[0] ? squash(a.labels[0].textContent) : '') ||
				(a.closest('label') ? squash(a.closest('label')!.textContent) : '') ||
				squash(a.innerText ?? a.textContent);
			const role = a.getAttribute('role');
			const kind =
				a.tagName === 'INPUT'
					? `input:${(a as HTMLInputElement).type}`
					: role
						? `${a.tagName.toLowerCase()}[${role}]`
						: a.tagName.toLowerCase();
			return { kind, name: label.length > 90 ? `${label.slice(0, 89)}…` : label };
		});
		if (!info) break;
		stops.push(info);
	}
	return stops;
}

/**
 * The record (PUMPS_LAYOUT_RECORD): an element inside the pane's scroller, one screenshot per
 * screen of it at CSS pixels (`{label}-{i}.png` under `segments`, each with the element's offset
 * it starts at), the section nav hidden so that nothing is drawn over it; the scroller is put back
 * where it was. Element screenshots cannot be used: the page does not scroll, its scroller does.
 */
async function elementScreens(page: Page, element: Locator, label: string) {
	const scroll = (to: number | null) =>
		element.evaluate((el, top) => {
			let s = el.parentElement;
			while (s && !/(auto|scroll)/.test(getComputedStyle(s).overflowY)) s = s.parentElement;
			if (top !== null) s!.scrollTop = top;
			const sr = s!.getBoundingClientRect();
			const er = el.getBoundingClientRect();
			return {
				scrollTop: s!.scrollTop,
				view: { y: sr.top + s!.clientTop, height: s!.clientHeight },
				element: { x: er.left, top: er.top, width: er.width, height: er.height }
			};
		}, to);
	const start = await scroll(null);
	const top = start.element.top - start.view.y + start.scrollTop;
	const parts: { file: string; from: number }[] = [];
	for (let from = 0, i = 0; from < start.element.height && i < 40; i++) {
		const at = await scroll(top + from);
		await page.waitForTimeout(150);
		const y = Math.max(at.view.y, at.element.top + from);
		const height = Math.min(at.view.y + at.view.height - y, at.element.top + at.element.height - y);
		if (height < 1) break;
		const file = path.join(RECORD, 'segments', `${label}-${String(i).padStart(2, '0')}.png`);
		await page.screenshot({
			path: file,
			scale: 'css',
			clip: {
				x: Math.round(at.element.x),
				y: Math.round(y),
				width: Math.round(at.element.width),
				height: Math.floor(height)
			},
			style: '[data-pumps-nav] { visibility: hidden; }'
		});
		parts.push({ file, from: Math.round(y - at.element.top) });
		from = Math.round(y - at.element.top) + Math.floor(height);
	}
	await scroll(start.scrollTop);
	writeFileSync(
		path.join(RECORD, 'segments', `${label}.json`),
		JSON.stringify({ height: Math.round(start.element.height), parts }, null, 1)
	);
}

/**
 * The pane's scroller from the pump chart's canvas to the tab's end, one screenshot per screen at
 * CSS pixels (measure.mjs `stitched`); the files and the scroll offset each was taken at. Where
 * the section nav is pinned over a screen's top (S2, §5.4), that screen's `cover` is its height,
 * and the screen starts that much sooner than where the one before it ended: measured on the
 * screen itself, since the nav pins as the canvas scrolls out, so nothing under the nav is left
 * out (S2 review LAYOUT-2).
 */
async function screens(page: Page, dir: string, label: string) {
	const geometry = await page.evaluate(() => {
		const pane = document.querySelector('section[aria-label="Results"]')!;
		const row = pane.querySelector('[role="tablist"][aria-label="Results view"]')!;
		let scroller: HTMLElement | null = null;
		for (let e = row.parentElement; e && e !== pane; e = e.parentElement) {
			if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
				scroller = e;
				break;
			}
		}
		document
			.querySelectorAll('[data-layout-scroller]')
			.forEach((e) => e.removeAttribute('data-layout-scroller'));
		scroller!.setAttribute('data-layout-scroller', '');
		const panel = [...pane.querySelectorAll('[role="tabpanel"]')].find(
			(p) => !(p as HTMLElement).hidden
		)!;
		const figure = [...panel.querySelectorAll('figure')].find((f) =>
			(f.querySelector(':scope > figcaption')?.textContent ?? '')
				.trim()
				.startsWith('Pump and system curves')
		)!;
		const chart = figure.querySelector('[role="img"]')!.getBoundingClientRect();
		const sr = scroller!.getBoundingClientRect();
		const box = {
			x: sr.left + scroller!.clientLeft,
			y: sr.top + scroller!.clientTop,
			width: scroller!.clientWidth,
			height: scroller!.clientHeight
		};
		const at = scroller!.scrollTop;
		return {
			box,
			start: Math.round(chart.top - box.y + at - 8),
			chartBottom: Math.round(chart.bottom - box.y + at),
			end: Math.round(panel.getBoundingClientRect().bottom - box.y + at + 8)
		};
	});
	const segments: { file: string; scrollTop: number; cover: number }[] = [];
	let position = Math.max(0, geometry.start);
	const at = async (top: number) => {
		const actual = await page.evaluate((to) => {
			const s = document.querySelector('[data-layout-scroller]')!;
			s.scrollTop = to;
			return s.scrollTop;
		}, top);
		await page.waitForTimeout(150);
		const cover = await page.evaluate(() => {
			const nav = document.querySelector('[data-pumps-nav][data-pinned]');
			return nav ? Math.round(nav.getBoundingClientRect().height) : 0;
		});
		return { actual, cover };
	};
	for (let i = 0; i < 200 && position < geometry.end; i++) {
		let { actual, cover } = await at(position);
		const last = segments.at(-1);
		if (last && actual + cover > last.scrollTop + geometry.box.height) {
			// The nav pinned over this screen and not the one before: start it sooner by its height.
			position = last.scrollTop + geometry.box.height - cover;
			({ actual, cover } = await at(position));
		}
		const file = path.join(dir, 'segments', `${label}-${String(i).padStart(3, '0')}.png`);
		const b = geometry.box;
		await page.screenshot({
			path: file,
			scale: 'css',
			clip: { x: Math.round(b.x), y: Math.round(b.y), width: b.width, height: b.height }
		});
		segments.push({ file, scrollTop: actual, cover });
		// Each screen starts, below the nav pinned over it, at or above where the screen before
		// it ended: no line of the tab is left out of the record (S2 review LAYOUT-2).
		const before = segments.at(-2);
		if (before) {
			expect
				.soft(
					actual + cover,
					`screen ${i} of ${label} starts in sight where screen ${i - 1} ends (${before.scrollTop} + ${b.height})`
				)
				.toBeLessThanOrEqual(before.scrollTop + b.height);
		}
		if (actual + b.height >= geometry.end) break;
		const next = actual + b.height - cover;
		if (next <= position && actual < position) break; // it cannot scroll further
		position = next;
	}
	return { ...geometry, segments };
}

/**
 * Measure the tab as shown and record it: a one-line summary in the run's output, the numbers
 * attached to the test and, with PUMPS_LAYOUT_RECORD, written there with the accessibility
 * snapshot and the screens.
 */
async function measure(page: Page, info: TestInfo, label: string, extra: object) {
	await page.mouse.move(1, 1);
	const data = await page.evaluate(collect);
	const stops = await tabStops(page);
	const report: Record<string, unknown> = {
		label,
		viewport: page.viewportSize(),
		...extra,
		...data,
		tabStops: { count: stops.length, list: stops }
	};
	if (RECORD) {
		mkdirSync(path.join(RECORD, 'segments'), { recursive: true });
		const tab = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
		writeFileSync(path.join(RECORD, `${label}.aria.yaml`), await tab.ariaSnapshot());
		report.screenshot = await screens(page, RECORD, label);
		writeFileSync(path.join(RECORD, `${label}.json`), JSON.stringify(report, null, 1));
	}
	await info.attach(`${label}.json`, {
		body: JSON.stringify(report, null, 1),
		contentType: 'application/json'
	});
	const s = data.sideways;
	console.log(
		`${label}: pane ${data.pane.width} px wide (scroller ${s.scrollerClientWidth} wide, ${data.pane.scrollerClientHeight} high, holding ${s.scrollerScrollWidth}), ` +
			`below the pump canvas ${data.belowChartHeightPx} px, headings ${data.headingsBelowChart}, ` +
			`paragraphs ${data.paragraphs.count} (${data.paragraphs.words} words), controls ${data.controls.count}, ` +
			`Tab stops ${stops.length}, sticking out ${s.stickingCount}, page sideways ${s.pageScrollsSideways}, pane sideways ${s.scrollerScrollsSideways}`
	);
	return data;
}

/**
 * §5.7 row 1: neither the page nor the Results pane's own scroller scrolls sideways (soft, so a
 * run reports every size).
 */
async function noSidewaysScroll(page: Page, where: string) {
	const pageWidth = await page.evaluate(() => ({
		scrollWidth: document.documentElement.scrollWidth,
		innerWidth: window.innerWidth
	}));
	expect
		.soft(pageWidth.scrollWidth, `the page's width, ${where}`)
		.toBeLessThanOrEqual(pageWidth.innerWidth);
	const scroller = await resultsScroller(page);
	expect.soft(scroller, `the Results pane's scroller, ${where}`).not.toBeNull();
	if (scroller) {
		expect
			.soft(scroller.scrollWidth, `the width the Results pane's scroller holds, ${where}`)
			.toBeLessThanOrEqual(scroller.clientWidth);
	}
}

const sizeOf = (page: Page) => {
	const v = page.viewportSize()!;
	return `${v.width}x${v.height}`;
};

// ---- S1: the pump chart (§9 S1) -----------------------------------------------------------------

/**
 * §5.7 row 2: the pump chart's Show data table at most this far below its canvas, measured idle
 * after the requests; at 320×640 no budget (§5.7: the sideways, nav and outline checks only).
 */
/**
 * What Chromium's `<select>` keeps for itself beyond the author's padding: its inner start padding
 * and its arrow. Measured in this Chromium at 16 px by comparing a select's text with the same
 * select 80 px wider, pixel for pixel: names of 69, 237 and 276 px drew whole from 18 or 19 px
 * more than text and padding, with `pr-8` or `pr-3` alike.
 */
const MENULIST_INNER = 20;

const SHOW_TABLE_BELOW_CANVAS: Readonly<Record<string, number>> = {
	'1280x800': 300,
	'390x844': 400
};

/** On screen at a size of its own: not hidden, and not sr-only's 1 px box, which toBeVisible accepts. */
async function seenBox(locator: Locator): Promise<boolean> {
	return locator.evaluate((el) => {
		const r = el.getBoundingClientRect();
		return (
			el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
			r.width > 1 &&
			r.height > 1
		);
	});
}

/**
 * A line on screen as text: seenBox's test, no `.sr-only` element at or above it, and at least a
 * 12 px line tall (pumps-results-layout.md §9 S4 "New lines … visible"; S4 review MUT-01, MUT-02).
 */
async function seenLine(locator: Locator): Promise<boolean> {
	return locator.evaluate((el) => {
		const r = el.getBoundingClientRect();
		return (
			el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
			!el.closest('.sr-only') &&
			r.width > 1 &&
			r.height >= 12
		);
	});
}

const pumpFigure = (page: Page) =>
	resultsView(page, 'Pumps').then((tab) =>
		tab.getByRole('figure', { name: /^Pump and system curves/ })
	);

/**
 * The pump chart's part of S1, at the size shown (soft, so a run reports every check): its
 * budget, the tab's outline down to the Pumps together card (§7: h3 Results per pump, h3 Pump
 * chart, h4 Other cases on the pump chart), the containers (§5.5: none above a "Fields shown in …"
 * group, whose sheet is fixed on a phone) and its two live lines at rest (§7 Live regions).
 */
async function pumpChartPart(page: Page, where: string) {
	const size = sizeOf(page);
	const figure = await pumpFigure(page);
	const budget = SHOW_TABLE_BELOW_CANVAS[size];
	if (budget !== undefined) {
		const canvas = await figure.getByRole('img').boundingBox();
		const toggle = await figure
			.getByRole('button', { name: /^(Show|Hide) data table of the pump chart$/ })
			.boundingBox();
		expect.soft(canvas && toggle, `the canvas and Show data table drawn, ${where}`).toBeTruthy();
		if (canvas && toggle) {
			const below = Math.round(toggle.y - (canvas.y + canvas.height));
			console.log(`${where}: Show data table ${below} px below the pump canvas (budget ${budget})`);
			expect
				.soft(below, `Show data table below the pump canvas, ${where}`)
				.toBeLessThanOrEqual(budget);
		}
	}

	const read = await page.evaluate(() => {
		const pane = document.querySelector('section[aria-label="Results"]')!;
		const tab = [...pane.querySelectorAll('[role="tabpanel"]')].find(
			(p) => !(p as HTMLElement).hidden
		)!;
		const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
		const card = tab.querySelector('[data-pumps-together]');
		const headings = [...tab.querySelectorAll('h1,h2,h3,h4,h5,h6')]
			.filter((h) => h.checkVisibility() && h.getBoundingClientRect().height > 1)
			.map((h) => ({
				level: Number(h.tagName[1]),
				text: squash(h.textContent),
				inCard: !!card && card.contains(h)
			}));
		const containers: string[] = [];
		const groups = [...document.querySelectorAll('[role="group"][aria-label^="Fields shown in"]')];
		for (const group of groups) {
			for (let e = group.parentElement; e; e = e.parentElement) {
				const type = getComputedStyle(e).containerType;
				if (type !== 'normal') {
					containers.push(
						`${group.getAttribute('aria-label')}: <${e.tagName.toLowerCase()} class="${e.className}"> ${type}`
					);
				}
			}
		}
		const figure = [...tab.querySelectorAll('figure')].find((f) =>
			squash(f.querySelector(':scope > figcaption')?.textContent).startsWith(
				'Pump and system curves'
			)
		)!;
		const lines = [
			figure.querySelector('[data-pump-strip] [aria-live]'),
			figure.querySelector('[data-overlay-state]')
		]
			.filter((l): l is Element => l !== null)
			.map((l) => ({
				id: l.id,
				live: l.getAttribute('aria-live'),
				atomic: l.getAttribute('aria-atomic'),
				role: l.getAttribute('role'),
				text: squash(l.textContent),
				busyAncestor: !!l.parentElement?.closest('[aria-busy="true"]'),
				buttons: l.querySelectorAll('button').length
			}));
		// What §5.3 keeps visible, on screen at this size: not hidden and not a 1 px visually hidden
		// box (toBeVisible accepts sr-only's): the notes about the values and the strip's plain
		// lines (§10 Words on screen), the select's cost sentence, an off case's note, the cap and
		// the overlay's cost (§6.4 item 8).
		const seen = (el: Element) => {
			const r = el.getBoundingClientRect();
			return (
				el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
				r.width > 1 &&
				r.height > 1
			);
		};
		const select = tab.querySelector('select[aria-labelledby][aria-describedby]');
		const kept = [
			...figure.querySelectorAll('[data-pump-notes] p, [data-pump-strip] p'),
			document.getElementById(select?.getAttribute('aria-describedby') ?? ''),
			...figure.querySelectorAll('[data-pump-others] fieldset p, [id$="-overlay-hint"]')
		].filter((el): el is Element => el !== null);
		const unseen = kept.filter((el) => !seen(el)).map((el) => squash(el.textContent));
		return {
			headings,
			groups: groups.length,
			containers,
			lines,
			kept: kept.length,
			unseen,
			scenarios: !!figure.querySelector('[data-pump-others]'),
			// The card's group curve keeps its status until S3 (§10 S3); the pump chart has none.
			statuses: figure.querySelectorAll('[role="status"]').length
		};
	});

	// The outline down to the card, in order: the pump chart's part (§7).
	const before = read.headings.filter((h) => !h.inCard);
	expect
		.soft(before, `the headings above the Pumps together card, ${where}`)
		.toEqual([
			{ level: 3, text: 'Results per pump', inCard: false },
			{ level: 3, text: 'Pump chart', inCard: false },
			...(read.scenarios
				? [{ level: 4, text: 'Other cases on the pump chart', inCard: false }]
				: [])
		]);
	const next = read.headings[before.length];
	expect.soft(next?.level, `the card's heading next, ${where}`).toBe(3);
	expect.soft(next?.text ?? '', `the card's heading next, ${where}`).toMatch(/^Pumps together/);

	// §5.5: no container above a "Fields shown in …" group (a phone's sheet is fixed).
	expect.soft(read.groups, `"Fields shown in …" groups, ${where}`).toBeGreaterThan(0);
	expect
		.soft(read.containers, `containers above a "Fields shown in …" group, ${where}`)
		.toEqual([]);

	// The live lines, at rest: there, polite, never a status, never busy, holding no button.
	expect
		.soft(read.lines.length, `the pump chart's live lines, ${where}`)
		.toBe(read.scenarios ? 2 : 1);
	for (const line of read.lines) {
		expect.soft(line, `the live line ${line.id || 'of the other cases'}, ${where}`).toEqual({
			id: line.id,
			live: 'polite',
			atomic: 'true',
			role: null,
			text: '',
			busyAncestor: false,
			buttons: 0
		});
	}
	expect.soft(read.statuses, `role=status in the pump chart, ${where}`).toBe(0);

	// Kept visible (§5.3, §6.4 item 8, §10 Words on screen): each at a size of its own.
	expect.soft(read.kept, `the pump chart's notes and hints read, ${where}`).toBeGreaterThan(2);
	expect.soft(read.unseen, `the pump chart's notes and hints out of sight, ${where}`).toEqual([]);

	// §5.3 item 2 (§15 item 17): the select shows each pump's whole name, since a name's end can be
	// the only part that tells two pumps apart ("Condenser water pump CWP-1" to "… CWP-6"). Its
	// text box is its width less its padding and less what Chromium's own select keeps beyond the
	// author's padding (MENULIST_INNER, measured), against the longest name in its own font. At
	// 320×640 no row holds the condenser's names: there the select takes the row's whole width.
	const select = await page.evaluate((inner) => {
		const el = document.querySelector<HTMLSelectElement>('[data-pump-chart] select');
		if (!el) return null;
		const css = getComputedStyle(el);
		const context = document.createElement('canvas').getContext('2d')!;
		context.font = `${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
		const longest = [...el.options].reduce(
			(widest, option) => {
				const width = context.measureText(option.text).width;
				return width > widest.width ? { name: option.text, width } : widest;
			},
			{ name: '', width: 0 }
		);
		const padding = parseFloat(css.paddingLeft) + parseFloat(css.paddingRight);
		return {
			name: longest.name,
			text: Math.ceil(longest.width),
			room: Math.floor(el.clientWidth - padding - inner),
			width: Math.round(el.getBoundingClientRect().width),
			row: Math.round(el.parentElement!.getBoundingClientRect().width)
		};
	}, MENULIST_INNER);
	if (select && size === '320x640') {
		expect.soft(select.width, `the Pump chart select's width, ${where}`).toBe(select.row);
	} else if (select) {
		expect
			.soft(select.room, `room in the Pump chart select for "${select.name}", ${where}`)
			.toBeGreaterThanOrEqual(select.text);
	}
}

// ---- S2: the card's sections and the section nav (§9 S2) -----------------------------------------

/**
 * §5.7 row 3: the group chart's Show data table at most this far below its canvas, measured idle
 * after the requests, with the card open; at 320×640 no budget (§5.7: the sideways, nav and
 * outline checks only).
 */
const GROUP_SHOW_TABLE_BELOW_CANVAS: Readonly<Record<string, number>> = {
	'1280x800': 600,
	'390x844': 900
};

/** §5.7 row 6 and §7's outline below the pump canvas, as S2 builds it (§15). */
const OUTLINE_CARD_CLOSED = [
	{ level: 4, text: 'Other cases on the pump chart' },
	{ level: 3, text: expect.stringMatching(/^Pumps together/) }
];
const OUTLINE_CARD_OPEN = [
	{ level: 4, text: 'Other cases on the pump chart' },
	{ level: 3, text: 'Pumps together' },
	{ level: 4, text: 'Station' },
	{ level: 4, text: 'Group chart' },
	{ level: 5, text: 'Other cases on the group chart' },
	{ level: 4, text: 'Add cases' },
	{ level: 4, text: 'Running combinations' },
	{ level: 5, text: 'Extremes over these cases (current results)' }
];

/** The section nav and its pane as laid out (viewport px), and the element with the focus. */
function readNav() {
	const pane = document.querySelector('section[aria-label="Results"]')!;
	const row = pane.querySelector('[role="tablist"][aria-label="Results view"]')!;
	let scroller: HTMLElement | null = null;
	for (let e = row.parentElement; e && e !== pane; e = e.parentElement) {
		if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
			scroller = e as HTMLElement;
			break;
		}
	}
	const nav = document.querySelector<HTMLElement>('[data-pumps-nav]')!;
	const toolbar = nav.querySelector<HTMLElement>('[role="toolbar"]')!;
	const figure = [...pane.querySelectorAll('figure')].find((f) =>
		(f.querySelector(':scope > figcaption')?.textContent ?? '')
			.trim()
			.startsWith('Pump and system curves')
	)!;
	const canvas = figure.querySelector('[role="img"]')!.getBoundingClientRect();
	const s = scroller!.getBoundingClientRect();
	const n = nav.getBoundingClientRect();
	const t = toolbar.getBoundingClientRect();
	const a = document.activeElement as HTMLElement | null;
	const ar = a?.getBoundingClientRect();
	const here = toolbar.querySelector('[aria-current="location"]')?.getBoundingClientRect();
	return {
		pinned: nav.hasAttribute('data-pinned'),
		position: getComputedStyle(nav).position,
		navTop: n.top,
		navBottom: n.bottom,
		navHeight: n.height,
		scrollerTop: s.top + scroller!.clientTop,
		scrollerBottom: s.top + scroller!.clientTop + scroller!.clientHeight,
		scrollerLeft: s.left + scroller!.clientLeft,
		scrollerRight: s.left + scroller!.clientLeft + scroller!.clientWidth,
		innerWidth: window.innerWidth,
		innerHeight: window.innerHeight,
		// The toolbar's row as it clips (its client box), and the current button in it.
		toolbarLeft: t.left + toolbar.clientLeft,
		toolbarRight: t.left + toolbar.clientLeft + toolbar.clientWidth,
		current: here ? { left: here.left, right: here.right } : null,
		clientHeight: scroller!.clientHeight,
		scrollTop: scroller!.scrollTop,
		scrollMax: scroller!.scrollHeight - scroller!.clientHeight,
		scrollPadding: getComputedStyle(scroller!).scrollPaddingTop,
		canvasTop: canvas.top,
		canvasBottom: canvas.bottom,
		buttons: [...toolbar.querySelectorAll<HTMLElement>('button')].map((b) => ({
			// Its accessible name: a marked button's aria-label (§5.4 Marks), else its words.
			name: b.getAttribute('aria-label') ?? (b.textContent ?? '').trim(),
			stop: b.tabIndex === 0,
			current: b.getAttribute('aria-current')
		})),
		active: a
			? {
					tag: a.tagName,
					text: (a.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 80),
					name: a.getAttribute('aria-label') ?? (a.textContent ?? '').replace(/\s+/g, ' ').trim(),
					inNav: nav.contains(a),
					top: ar!.top,
					bottom: ar!.bottom,
					left: ar!.left,
					right: ar!.right,
					height: ar!.height
				}
			: null
	};
}

type NavState = ReturnType<typeof readNav>;

/** Two animation frames: an observer's callback after a scroll has run (S2 review KBD-2). */
const frames = (page: Page) =>
	page.evaluate(
		() =>
			new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())))
	);

/**
 * The pane's scroll and the nav's row at rest: neither has moved for ten frames (a press's
 * smooth scroll, the row's keep-in-view), at most 10 s.
 */
async function scrollStops(page: Page) {
	await page.evaluate(
		() =>
			new Promise<void>((done) => {
				const pane = document.querySelector('section[aria-label="Results"]')!;
				const row = pane.querySelector('[role="tablist"][aria-label="Results view"]')!;
				let scroller: HTMLElement | null = null;
				for (let e = row.parentElement; e && e !== pane; e = e.parentElement) {
					if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
						scroller = e as HTMLElement;
						break;
					}
				}
				const toolbar = document.querySelector<HTMLElement>('[data-pumps-nav] [role="toolbar"]')!;
				let last = '';
				let same = 0;
				let n = 0;
				const step = () => {
					const now = `${scroller!.scrollTop} ${toolbar.scrollLeft}`;
					same = now === last ? same + 1 : 0;
					last = now;
					if (same >= 10 || ++n > 600) done();
					else requestAnimationFrame(step);
				};
				requestAnimationFrame(step);
			})
	);
}

/**
 * The page itself never scrolls (§5.4 Place: only under `short:` does the workspace scroll as one
 * page; S2 review KBD-1, TS-05): the document no taller than the viewport, not scrolled, the
 * header at its top (soft).
 */
async function pageStill(page: Page, where: string) {
	const p = await page.evaluate(() => ({
		scrollY: window.scrollY,
		scrollHeight: document.documentElement.scrollHeight,
		innerHeight: window.innerHeight,
		// The banner: the header outside main and the sections (the app's, with Solve).
		bannerTop: [...document.querySelectorAll('header')]
			.find((h) => !h.parentElement?.closest('main, section, article, aside, nav'))!
			.getBoundingClientRect().top
	}));
	expect.soft(p.scrollHeight, `the page's height, ${where}`).toBeLessThanOrEqual(p.innerHeight);
	expect.soft(p.scrollY, `the page's scroll, ${where}`).toBe(0);
	expect.soft(p.bannerTop, `the header's top, ${where}`).toBe(0);
}

/** As pageStill, and a wheel over the header scrolls nothing either (S2 review TS-05). */
async function pageHolds(page: Page, where: string) {
	await pageStill(page, where);
	const banner = (await page.getByRole('banner').boundingBox())!;
	await page.mouse.move(banner.x + banner.width / 2, banner.y + banner.height / 2);
	await page.mouse.wheel(0, 1500);
	await page.waitForTimeout(300);
	await pageStill(page, `${where}, after a wheel over the header`);
	await page.mouse.move(1, 1);
}

/**
 * The focused element in sight (§5.4 Focus never hidden, WCAG 2.4.11; S2 review): a box of its
 * own inside the pane's visible area and the viewport and, for a button of the nav, inside the
 * row that clips it.
 */
function focusInSight(s: NavState, what: string) {
	const a = s.active;
	const soft = expect.configure({ soft: true });
	soft(a && a.height > 1, `${what}: a focused box`).toBe(true);
	if (!a) return;
	const top = Math.max(s.scrollerTop, 0);
	const bottom = Math.min(s.scrollerBottom, s.innerHeight);
	soft(
		a.top,
		`${what}: the focus's top in the pane's view and the viewport`
	).toBeGreaterThanOrEqual(top - 0.5);
	soft(
		a.bottom,
		`${what}: the focus's bottom in the pane's view and the viewport`
	).toBeLessThanOrEqual(bottom + 0.5);
	soft(a.left >= Math.max(s.scrollerLeft, 0) - 0.5, `${what}: the focus's left in sight`).toBe(
		true
	);
	soft(
		a.right <= Math.min(s.scrollerRight, s.innerWidth) + 0.5,
		`${what}: the focus's right in sight`
	).toBe(true);
	if (a.inNav) {
		soft(
			a.left >= s.toolbarLeft - 0.5 && a.right <= s.toolbarRight + 0.5,
			`${what}: the focused button inside the row (${Math.round(a.left)} to ${Math.round(a.right)} in ${Math.round(s.toolbarLeft)} to ${Math.round(s.toolbarRight)})`
		).toBe(true);
	}
}

/**
 * Where the pane says you are (§5.4 Where you are), read from the targets given in document order
 * (the sections' targets, as their presses focused them): the last whose top is at or above the
 * line under the nav (the pane's top, the nav's height, the targets' 0.5 rem and 1 px for
 * rounding), else the first; and whether each is on screen in the pane.
 */
function sectionsPassed(targets: Element[]) {
	const pane = document.querySelector('section[aria-label="Results"]')!;
	const row = pane.querySelector('[role="tablist"][aria-label="Results view"]')!;
	let scroller: HTMLElement | null = null;
	for (let e = row.parentElement; e && e !== pane; e = e.parentElement) {
		if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
			scroller = e as HTMLElement;
			break;
		}
	}
	const box = scroller!.getBoundingClientRect();
	const top = Math.max(box.top + scroller!.clientTop, 0);
	const bottom = Math.min(box.top + scroller!.clientTop + scroller!.clientHeight, innerHeight);
	const nav = document.querySelector('[data-pumps-nav]')!.getBoundingClientRect().height;
	const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
	const line = top + nav + rem / 2 + 1;
	const boxes = targets.map((t) => t.getBoundingClientRect());
	let passed = 0;
	boxes.forEach((b, i) => {
		if (b.top <= line) passed = i;
	});
	return {
		passed,
		line,
		bottom,
		tops: boxes.map((b) => Math.round(b.top)),
		onScreen: boxes.map((b) => b.top < bottom && b.bottom > top)
	};
}

/** Scroll the Results pane's scroller by `by` px (or to `to`), and let its observers run. */
async function scrollPane(page: Page, move: { by?: number; to?: number }) {
	await page.evaluate((m) => {
		const pane = document.querySelector('section[aria-label="Results"]')!;
		const row = pane.querySelector('[role="tablist"][aria-label="Results view"]')!;
		for (let e = row.parentElement; e && e !== pane; e = e.parentElement) {
			if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
				e.scrollTop = m.to ?? e.scrollTop + (m.by ?? 0);
				return;
			}
		}
	}, move);
	await page.waitForTimeout(150);
}

/**
 * The section nav's part of S2 at the size shown (§5.4, §5.7, §10 The nav; soft, so a run reports
 * every check): the group chart's budget; the outline below the pump canvas; one Tab stop and a
 * ring the row never clips; pinned only once the pump canvas has scrolled out, at the pane's top,
 * at most 15 % of it, and the canvas whole under the tab's top at 1280×800; each press, by the
 * keyboard, lands on its target under the nav, uncovered, without motion when reduced motion is
 * asked for, the link untouched; `aria-current` follows the scroll; Tab and Shift+Tab through the
 * card never put the focus under the pinned nav; and "Back to the sections" gives the nav's
 * current button the focus.
 */
async function navPart(page: Page, where: string) {
	const soft = expect.configure({ soft: true });
	const size = sizeOf(page);
	const tab = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
	const nav = tab.getByRole('navigation', { name: 'Pumps view sections' });
	const toolbar = nav.getByRole('toolbar', { name: 'Go to' });
	await soft(toolbar, `the section nav's toolbar, ${where}`).toHaveAttribute(
		'aria-orientation',
		'horizontal'
	);
	// Its lead word seen, a box of its own, not sr-only's 1 px (§5.4 Markup: "a visible lead word").
	soft(
		await seenBox(nav.getByText('Go to', { exact: true })),
		`the nav's lead word "Go to" seen, ${where}`
	).toBe(true);
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const toggle = card.getByRole('button', { name: /^Pumps together/ });
	const open = (await toggle.getAttribute('aria-expanded')) === 'true';
	const hash = await page.evaluate(() => location.hash);

	// §5.7 row 3: the group canvas to its Show data table, with the card open.
	const budget = GROUP_SHOW_TABLE_BELOW_CANVAS[size];
	if (open && budget !== undefined) {
		const figure = card.getByRole('figure');
		const canvas = await figure.getByRole('img').boundingBox();
		const button = await figure
			.getByRole('button', { name: /^(Show|Hide) data table of the group chart$/ })
			.boundingBox();
		soft(canvas && button, `the group canvas and its Show data table, ${where}`).toBeTruthy();
		if (canvas && button) {
			const below = Math.round(button.y - (canvas.y + canvas.height));
			console.log(
				`${where}: group Show data table ${below} px below its canvas (budget ${budget})`
			);
			soft(
				below,
				`the group chart's Show data table below its canvas, ${where}`
			).toBeLessThanOrEqual(budget);
		}
	}

	// §5.7 row 6, §7: the outline below the pump canvas, in order; the nav holds no heading.
	const outline = await page.evaluate(() => {
		const pane = document.querySelector('section[aria-label="Results"]')!;
		const panel = [...pane.querySelectorAll('[role="tabpanel"]')].find(
			(p) => !(p as HTMLElement).hidden
		)!;
		const figure = [...panel.querySelectorAll('figure')].find((f) =>
			(f.querySelector(':scope > figcaption')?.textContent ?? '')
				.trim()
				.startsWith('Pump and system curves')
		)!;
		const base = figure.querySelector('[role="img"]')!.getBoundingClientRect().bottom;
		return [...panel.querySelectorAll('h1,h2,h3,h4,h5,h6')]
			.filter(
				(h) =>
					h.checkVisibility() &&
					h.getBoundingClientRect().height > 1 &&
					h.getBoundingClientRect().top >= base - 0.5
			)
			.map((h) => ({
				level: Number(h.tagName[1]),
				text: (h.textContent ?? '').replace(/\s+/g, ' ').trim()
			}));
	});
	soft(outline, `the headings below the pump canvas, ${where}`).toEqual(
		open ? OUTLINE_CARD_OPEN : OUTLINE_CARD_CLOSED
	);
	expect
		.soft(await nav.locator('h1,h2,h3,h4,h5,h6').count(), `headings in the nav, ${where}`)
		.toBe(0);

	// One Tab stop (§5.4): from the Pumps view's tab, Tab lands in the toolbar, once.
	await scrollPane(page, { to: 0 });
	await resultsPane(page).getByRole('tab', { name: 'Pumps', exact: true }).focus();
	await page.keyboard.press('Tab');
	let state = await page.evaluate(readNav);
	soft(state.active?.inNav, `Tab from the view's tab lands in the nav, ${where}`).toBe(true);
	soft(state.buttons.filter((b) => b.stop).length, `the nav's Tab stops, ${where}`).toBe(1);
	// Its ring (2 px at a 2 px offset) whole inside the row, which clips (§5.4 One shared component).
	const ring = await page.evaluate(() => {
		const a = document.activeElement as HTMLElement;
		const row = a.closest('[role="toolbar"]') as HTMLElement;
		const r = a.getBoundingClientRect();
		const box = row.getBoundingClientRect();
		const style = getComputedStyle(a);
		return {
			outline: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0,
			reach: parseFloat(style.outlineWidth) + parseFloat(style.outlineOffset),
			top: r.top - box.top - row.clientTop,
			bottom: box.top + row.clientTop + row.clientHeight - r.bottom
		};
	});
	soft(ring.outline, `the focused button's ring drawn, ${where}`).toBe(true);
	soft(ring.top, `room above the ring in the row, ${where}`).toBeGreaterThanOrEqual(ring.reach);
	soft(ring.bottom, `room below the ring in the row, ${where}`).toBeGreaterThanOrEqual(ring.reach);
	await page.keyboard.press('Tab');
	state = await page.evaluate(readNav);
	soft(state.active?.inNav, `a second Tab leaves the nav, ${where}`).toBe(false);

	// Pinned only once the pump canvas has scrolled out (§5.4 Place): at the tab's top static;
	// the canvas 2 px in view, static; 2 px out, pinned at the pane's top, ≤ 15 % of its height.
	await scrollPane(page, { to: 0 });
	state = await page.evaluate(readNav);
	soft(state.pinned, `the nav at the tab's top, ${where}`).toBe(false);
	soft(state.position, `the nav at the tab's top, ${where}`).toBe('static');
	await scrollPane(page, { by: state.canvasBottom - state.scrollerTop - 2 });
	state = await page.evaluate(readNav);
	soft(state.pinned, `the nav with the canvas's last 2 px in view, ${where}`).toBe(false);
	await scrollPane(page, { by: 4 });
	state = await page.evaluate(readNav);
	const share = state.navHeight / state.clientHeight;
	console.log(
		`${where}: the nav ${Math.round(state.navHeight)} px, ${(share * 100).toFixed(1)} % of a ${state.clientHeight} px pane, pinned ${state.pinned}`
	);
	soft(share, `the nav's share of the pane, ${where}`).toBeLessThanOrEqual(0.15);
	soft(state.pinned, `the nav with the canvas scrolled out, ${where}`).toBe(true);
	soft(state.position, `the nav with the canvas scrolled out, ${where}`).toBe('sticky');
	soft(
		Math.abs(state.navTop - state.scrollerTop),
		`the pinned nav at the pane's top, ${where}`
	).toBeLessThan(1);
	// Its height and 0.5 rem: a focus ring and a scroll's rounding never reach under it.
	soft(state.scrollPadding, `the pane's scroll padding while pinned, ${where}`).toBe(
		`${state.navHeight + 8}px`
	);
	if (size === '1280x800') {
		// §5.7: the canvas whole under the tab's top, the nav not over it (F12).
		await scrollPane(page, { by: state.canvasTop - state.scrollerTop });
		state = await page.evaluate(readNav);
		soft(state.pinned, `the nav over the whole canvas, ${where}`).toBe(false);
		soft(state.canvasBottom, `the canvas's bottom in the pane, ${where}`).toBeLessThanOrEqual(
			state.scrollerBottom
		);
	}

	// Each press, by the keyboard (§5.4 A press): the focus on its target, 0.5 rem under the nav
	// (pinned) or the pane's top (static), unless the pane cannot scroll that far; no motion.
	await page.emulateMedia({ reducedMotion: 'reduce' });
	const names = state.buttons.map((b) => b.name);
	/** Each button's target, as its press focused it, in the buttons' order. */
	const targets: JSHandle<Element>[] = [];
	for (const name of names) {
		await toolbar.getByRole('button', { name, exact: true }).press('Enter');
		const animations = await page.evaluate(() => document.getAnimations().length);
		// The nav's state once the canvas's observer has run, two frames after the scroll (S2
		// review KBD-2: read at once, it was sometimes the state before the press; and a press back
		// to the pump chart unpins the nav a frame after the jump, so a read in between took it
		// still pinned over a target already at the pane's top).
		await frames(page);
		const pressed = await page.evaluate(() => {
			const n = document.querySelector('[data-pumps-nav]')!;
			return {
				nav: { pinned: n.hasAttribute('data-pinned'), bottom: n.getBoundingClientRect().bottom }
			};
		});
		state = await page.evaluate(readNav);
		const label = name.split(',')[0]!;
		const top = state.active ? state.active.top : NaN;
		const edge = pressed.nav.pinned ? pressed.nav.bottom : state.scrollerTop;
		const atEnd = state.scrollTop >= state.scrollMax - 1;
		soft(animations, `animations after pressing ${label}, ${where}`).toBe(0);
		soft(state.active?.inNav, `the focus after pressing ${label}, ${where}`).toBe(false);
		soft(state.active?.text ?? '', `the focus after pressing ${label}, ${where}`).toMatch(
			label === 'Per pump' ? /^Results per pump/ : new RegExp(`^${label}`)
		);
		if (atEnd) {
			soft(top, `${label}'s target below the nav, ${where}`).toBeGreaterThanOrEqual(edge - 0.5);
		} else {
			soft(Math.round(top - edge), `${label}'s target under the nav, ${where}`).toBe(8);
		}
		soft(state.active!.bottom, `${label}'s target in the pane, ${where}`).toBeLessThanOrEqual(
			state.scrollerBottom + 0.5
		);
		soft(
			state.buttons.find((b) => b.current === 'location')?.name,
			`aria-current after pressing ${label}, ${where}`
		).toBe(name);
		soft(
			await page.evaluate(() => location.hash),
			`the link after pressing ${label}, ${where}`
		).toBe(hash);
		focusInSight(state, `after pressing ${label}, ${where}`);
		await pageStill(page, `after pressing ${label}, ${where}`);

		// Then 150 px back up: aria-current follows, to the section passed last, unless the pane
		// stopped at its end with the target short of the line and it is still on screen (§5.4
		// Where you are; S2 check NAV2-LEAVE: a target at rest on the observer's edge left it
		// unseen, and the section pressed stayed current). Then back where the press left it.
		targets.push(await page.evaluateHandle(() => document.activeElement!));
		const i = targets.length - 1;
		const landed = await page.evaluate(sectionsPassed, targets);
		await scrollPane(page, { by: -150 });
		await frames(page);
		const up = await page.evaluate(sectionsPassed, targets);
		const held = landed.passed < i && up.onScreen[i]!;
		soft(
			(await page.evaluate(readNav)).buttons.find((b) => b.current === 'location')?.name,
			`aria-current 150 px back up after pressing ${label} (tops ${up.tops.join(', ')}, the line at ${Math.round(up.line)}), ${where}`
		).toBe(names[held ? i : up.passed]);
		await scrollPane(page, { to: state.scrollTop });
	}

	// Each press from the tab's top, the nav static, with motion (the default): the target lands
	// as it does from the pinned nav, 0.5 rem under it, and once the scroll has stopped the button
	// pressed is current (S2 review TS-01, NAV-2).
	await page.emulateMedia({ reducedMotion: 'no-preference' });
	for (const name of names) {
		await scrollPane(page, { to: 0 });
		await toolbar.getByRole('button', { name, exact: true }).press('Enter');
		await scrollStops(page);
		state = await page.evaluate(readNav);
		const label = `${name.split(',')[0]!} from the tab's top`;
		const top = state.active ? state.active.top : NaN;
		const edge = state.pinned ? state.navBottom : state.scrollerTop;
		soft(state.active?.text ?? '', `the focus after pressing ${label}, ${where}`).toMatch(
			name.startsWith('Per pump') ? /^Results per pump/ : new RegExp(`^${name.split(',')[0]}`)
		);
		if (state.scrollTop >= state.scrollMax - 1) {
			soft(top, `${label}'s target below the nav, ${where}`).toBeGreaterThanOrEqual(edge - 0.5);
		} else {
			soft(Math.round(top - edge), `${label}'s target under the nav, ${where}`).toBe(8);
		}
		soft(
			state.buttons.find((b) => b.current === 'location')?.name,
			`aria-current once the scroll has stopped, after pressing ${label}, ${where}`
		).toBe(name);
		focusInSight(state, `after pressing ${label}, ${where}`);
		await pageStill(page, `after pressing ${label}, ${where}`);
	}

	// A press cut short (S2 check NAV2-STUCK): the last button pressed from the tab's top, with
	// motion, then Home, or the scrollbar dragged back to where the press began (an instant
	// scroll), while its scroll runs and its target is still below the pane. Later the user's own
	// scroll brings the target in from below, 60 px above the pane's foot and then 100 px further:
	// aria-current is the section passed last, never the target before it is passed.
	const last = names.at(-1)!;
	for (const cut of ['Home', 'a drag'] as const) {
		let below = false;
		// The cut must come while the target is below the pane: tried again if the press was
		// quicker (at most three times).
		for (let attempt = 0; attempt < 3 && !below; attempt++) {
			await scrollPane(page, { to: 0 });
			await toolbar.getByRole('button', { name: last, exact: true }).press('Enter');
			below = await page.evaluate(
				([target, drag]) =>
					new Promise<boolean>((done) => {
						const pane = document.querySelector('section[aria-label="Results"]')!;
						const row = pane.querySelector('[role="tablist"][aria-label="Results view"]')!;
						let scroller: HTMLElement | null = null;
						for (let e = row.parentElement; e && e !== pane; e = e.parentElement) {
							if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
								scroller = e as HTMLElement;
								break;
							}
						}
						const s = scroller!;
						const from = s.scrollTop;
						let n = 0;
						// 200 px into the press's scroll (or its end, or 10 s), then the cut.
						const step = () => {
							if (s.scrollTop < from + 200 && ++n < 600) {
								requestAnimationFrame(step);
								return;
							}
							const box = s.getBoundingClientRect();
							const bottom = Math.min(box.top + s.clientTop + s.clientHeight, innerHeight);
							const out = target.getBoundingClientRect().top >= bottom;
							if (drag) s.scrollTop = from;
							done(out);
						};
						requestAnimationFrame(step);
					}),
				[targets.at(-1)!, cut === 'a drag'] as const
			);
			if (cut === 'Home') await page.keyboard.press('Home');
			await scrollStops(page);
			await frames(page);
		}
		soft(
			below,
			`the press of ${last} cut short (${cut}) while its target was below the pane, ${where}`
		).toBe(true);
		for (const [step, by] of [
			['60 px above the pane’s foot', null],
			['100 px further', 100]
		] as const) {
			const at = await page.evaluate(sectionsPassed, targets);
			await scrollPane(page, { by: by ?? at.tops.at(-1)! - (at.bottom - 60) });
			await frames(page);
			const now = await page.evaluate(sectionsPassed, targets);
			soft(
				(await page.evaluate(readNav)).buttons.find((b) => b.current === 'location')?.name,
				`aria-current, ${last} pressed and cut short (${cut}), then scrolled in to ${step} (tops ${now.tops.join(', ')}, the line at ${Math.round(now.line)}), ${where}`
			).toBe(names[now.passed]);
		}
	}
	await page.emulateMedia({ reducedMotion: 'reduce' });

	if (open) {
		// aria-current follows the scroll (§5.4 Where you are): each heading brought under the nav.
		for (const heading of ['Station', 'Group chart', 'Running combinations']) {
			const top = await card
				.getByRole('heading', { name: heading, exact: true })
				.evaluate((h) => h.getBoundingClientRect().top);
			state = await page.evaluate(readNav);
			await scrollPane(page, { by: top - state.scrollerTop - state.navHeight - 4 });
			await soft
				.poll(
					async () =>
						(await page.evaluate(readNav)).buttons
							.find((b) => b.current === 'location')
							?.name.split(',')[0],
					{ message: `aria-current scrolled to ${heading}, ${where}`, timeout: 3000 }
				)
				.toBe(heading);
			// The row scrolls to keep it in view (§5.4 Where you are; S2 review TS-07).
			await frames(page);
			state = await page.evaluate(readNav);
			soft(
				!!state.current &&
					state.current.left >= state.toolbarLeft - 0.5 &&
					state.current.right <= state.toolbarRight + 0.5,
				`the current button inside the row, scrolled to ${heading}, ${where}`
			).toBe(true);
		}

		// Tab and Shift+Tab through the card, the nav pinned: no focused element meets it (§5.7,
		// WCAG 2.4.11). The toggle first (the nav's Pumps together), then to the card's end.
		await toolbar.getByRole('button', { name: /^Pumps together/ }).press('Enter');
		const covered: string[] = [];
		const tall: string[] = [];
		const check = (s: Awaited<ReturnType<typeof readNav>>, how: string) => {
			if (!s.pinned || !s.active || s.active.inNav || s.active.height < 1) return;
			const seen = `${how} ${s.active.tag} "${s.active.text.slice(0, 40)}" at ${Math.round(s.active.top - s.navBottom)}`;
			if (s.active.height > s.scrollerBottom - s.navBottom) {
				// A box taller than the pane under the nav always meets it: WCAG 2.4.11's own test,
				// some of it in sight below the nav.
				tall.push(seen);
				if (!(s.active.bottom > s.navBottom + 1 && s.active.top < s.scrollerBottom - 1)) {
					covered.push(`${seen} (none of it in sight)`);
				}
			} else if (s.active.bottom + 4 > s.navTop + 0.5 && s.active.top - 4 < s.navBottom - 0.5) {
				// Its ring too: 2 px at a 2 px offset.
				covered.push(seen);
			}
		};
		let steps = 0;
		for (; steps < 300; steps++) {
			await page.keyboard.press('Tab');
			state = await page.evaluate(readNav);
			check(state, 'Tab');
			const last = await page.evaluate(
				() => !!document.activeElement?.closest('[data-back-to-sections]')
			);
			if (last) break;
		}
		soft(steps, `Tab reached "Back to the sections" at the card's end, ${where}`).toBeLessThan(300);
		for (let i = 0; i < 300; i++) {
			await page.keyboard.press('Shift+Tab');
			state = await page.evaluate(readNav);
			check(state, 'Shift+Tab');
			if (await toggle.evaluate((t) => t === document.activeElement)) break;
		}
		soft(covered, `focused elements under the pinned nav, ${where}`).toEqual([]);
		if (tall.length)
			console.log(`${where}: focused boxes taller than the pane: ${tall.join('; ')}`);

		// "Back to the sections" (§5.4 The way back): visible once focused; the nav's current
		// button gets the focus.
		const back = card.getByRole('button', { name: 'Back to the sections' });
		const unshown = await page.evaluate(readNav);
		await back.focus();
		await frames(page);
		const shown = await page.evaluate(readNav);
		soft(await seenBox(back), `"Back to the sections" seen when focused, ${where}`).toBe(true);
		// Shown, it lies over the card's foot (from the end of the card's content, over its
		// padding) and moves nothing: the pane's scroll range is the same, so a press elsewhere
		// that hides it lands where it was aimed (S2 review LAYOUT-1).
		const foot = await back.evaluate((b) => ({
			top: b.getBoundingClientRect().top,
			cardBottom: b.closest('section')!.getBoundingClientRect().bottom
		}));
		soft(
			foot.top >= foot.cardBottom - 16 && foot.top <= foot.cardBottom,
			`"Back to the sections" shown at its card's foot (${Math.round(foot.top - foot.cardBottom)} px from its bottom), ${where}`
		).toBe(true);
		soft(
			shown.scrollMax,
			`the pane's scroll range with "Back to the sections" shown, ${where}`
		).toBe(unshown.scrollMax);
		// The nav's row wheeled back to its start, so the current button is out of its view and
		// the focus must bring it in: the row alone moves.
		await toolbar.evaluate((t) => (t.scrollLeft = 0));
		const before = await page.evaluate(readNav);
		await page.keyboard.press('Enter');
		await frames(page);
		state = await page.evaluate(readNav);
		const focused = state.buttons.find((b) => b.current === 'location');
		soft(state.active?.inNav, `the focus after "Back to the sections", ${where}`).toBe(true);
		soft(state.active?.name, `the focus after "Back to the sections", ${where}`).toBe(
			focused?.name
		);
		// The nav pinned is in sight: the focus scrolls nothing (S2 review TS-02).
		if (before.pinned) {
			soft(state.scrollTop, `the pane after "Back to the sections", the nav pinned, ${where}`).toBe(
				before.scrollTop
			);
		}
		focusInSight(state, `after "Back to the sections", ${where}`);
		await pageStill(page, `after "Back to the sections", ${where}`);
	}

	// The toolbar's keys with the nav pinned (§5.4 One Tab stop, §7; S2 review TS-03, TS-04):
	// End, Home and the arrows move the focus along the row, which brings the button in, and
	// scroll nothing else (the browser's End and Home would take the pane to its ends).
	await scrollPane(page, { to: 0 });
	state = await page.evaluate(readNav);
	await scrollPane(page, { by: state.canvasBottom - state.scrollerTop + 200 });
	await toolbar
		.getByRole('button')
		.first()
		.evaluate((b) => (b as HTMLElement).focus({ preventScroll: true }));
	await frames(page);
	const keyed = await page.evaluate(readNav);
	soft(keyed.pinned, `the nav pinned for its keys, ${where}`).toBe(true);
	const order = keyed.buttons.map((b) => b.name);
	for (const [key, expected] of [
		['End', order.at(-1)],
		['Home', order[0]],
		['ArrowLeft', order.at(-1)],
		['ArrowRight', order[0]],
		['ArrowRight', order[1]]
	] as const) {
		await page.keyboard.press(key);
		await frames(page);
		state = await page.evaluate(readNav);
		soft(state.active?.name, `the focus after ${key} in the toolbar, ${where}`).toBe(expected);
		soft(state.scrollTop, `the pane after ${key} in the toolbar, ${where}`).toBe(keyed.scrollTop);
		focusInSight(state, `after ${key} in the toolbar, ${where}`);
		await pageStill(page, `after ${key} in the toolbar, ${where}`);
	}

	// Static, the nav scrolled out above the pane while the pump canvas is still in view: an
	// arrow key's focus brings it back into view (§5.4 Focus never hidden; S2 review NAV-3).
	await scrollPane(page, { to: 0 });
	await toolbar
		.getByRole('button')
		.first()
		.evaluate((b) => (b as HTMLElement).focus({ preventScroll: true }));
	state = await page.evaluate(readNav);
	await scrollPane(page, { by: state.navBottom - state.scrollerTop + 40 });
	state = await page.evaluate(readNav);
	soft(state.pinned, `the nav scrolled out with the canvas in view, ${where}`).toBe(false);
	soft(state.navBottom, `the nav scrolled out above the pane, ${where}`).toBeLessThan(
		state.scrollerTop
	);
	await page.keyboard.press('ArrowRight');
	await frames(page);
	state = await page.evaluate(readNav);
	soft(state.active?.name, `the focus after ArrowRight, the nav scrolled out, ${where}`).toBe(
		order[1]
	);
	focusInSight(state, `after ArrowRight, the nav scrolled out, ${where}`);
	await pageStill(page, `after ArrowRight, the nav scrolled out, ${where}`);

	if (!open) {
		// The closed card: Tab from its toggle to its "Back to the sections", the pane at its end,
		// then a press on the toggle opens the card. Shown, Back moves nothing, so the press is
		// not lost to content jumping under the pointer (S2 review LAYOUT-1).
		await toggle.focus();
		await page.keyboard.press('Tab');
		const back = card.getByRole('button', { name: 'Back to the sections' });
		soft(
			await back.evaluate((b) => b === document.activeElement),
			`Tab from the closed card's toggle reaches "Back to the sections", ${where}`
		).toBe(true);
		await scrollPane(page, { to: 1e7 });
		await toggle.click();
		soft(
			await toggle.getAttribute('aria-expanded'),
			`the toggle pressed, "Back to the sections" focused and the pane at its end, ${where}`
		).toBe('true');
		if ((await toggle.getAttribute('aria-expanded')) === 'true') await toggle.click();
		await expect(toggle).toHaveAttribute('aria-expanded', 'false');

		// The pump chart card's "Back to the sections", shown, reaches over the gap onto this
		// card's top, its toggle's top edge: a press there is the toggle's (S2 check
		// BACK-OVERLAY: it was Back's, and the focus jumped to the nav).
		const chartBack = page.locator('[data-pump-chart] [data-back-to-sections] button');
		await chartBack.evaluate((b) => b.scrollIntoView({ block: 'center' }));
		await chartBack.evaluate((b) => (b as HTMLElement).focus({ preventScroll: true }));
		await frames(page);
		const edge = await chartBack.evaluate(
			(b, t) => {
				const r = b.getBoundingClientRect();
				const box = t.getBoundingClientRect();
				const x = Math.max(box.left, r.left) + 10;
				const y = box.top + 2;
				const hit = document.elementFromPoint(x, y);
				return {
					x,
					y,
					over: x >= r.left && x <= r.right && y >= r.top && y <= r.bottom,
					hit: !!hit && t.contains(hit)
				};
			},
			(await toggle.elementHandle())!
		);
		console.log(
			`${where}: the pump chart card's Back shown, ${edge.over ? 'over' : 'clear of'} the toggle's top edge`
		);
		soft(
			edge.hit,
			`the toggle's top edge takes a press, the pump chart card's Back shown, ${where}`
		).toBe(true);
		await page.mouse.click(edge.x, edge.y);
		soft(
			await toggle.getAttribute('aria-expanded'),
			`a click on the toggle's top edge, the pump chart card's Back shown, ${where}`
		).toBe('true');
		if ((await toggle.getAttribute('aria-expanded')) === 'true') await toggle.click();
		await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	}
	await page.emulateMedia({ reducedMotion: null });
	soft(await page.evaluate(() => location.hash), `the link after the nav's part, ${where}`).toBe(
		hash
	);
}

/**
 * §9's merge condition "axe is clean with every disclosure open", over the whole Pumps tabpanel
 * (§7 Proof): axe-core with the suite's WCAG 2.0 to 2.2 A and AA tags, then `heading-order` and
 * `landmark-unique`, which those tags leave out. Run after the view's measurement, so the
 * disclosures it opens change no number. It presses only closed summaries
 * (`details:not([open]) > summary`), found anew each round since an opened one can hold more, so
 * it never closes one.
 */
async function axeClean(page: Page, where: string) {
	const panel = '[role="tabpanel"][id$="-panel-pumps"]';
	const closed = page.locator(`${panel} details:not([open]) > summary`);
	// The first closed one a user can see and press; one inside a closed one is pressed after it.
	const firstShown = () =>
		closed.evaluateAll((all) =>
			all.findIndex((s) => {
				const r = s.getBoundingClientRect();
				return s.checkVisibility() && r.width > 1 && r.height > 1;
			})
		);
	for (let round = 0; round < 60; round++) {
		const index = await firstShown();
		if (index < 0) break;
		await closed.nth(index).click();
	}
	expect(await firstShown(), `a closed disclosure left in the Pumps tab, ${where}`).toBe(-1);
	await settle(page, 1000);
	const wcag = await new AxeBuilder({ page })
		.include(panel)
		.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
		.analyze();
	expect
		.soft(
			wcag.violations.map((v) => `${v.id} (${v.nodes.length})`),
			`axe over the Pumps tab, every disclosure open, ${where}`
		)
		.toEqual([]);
	expect
		.soft(wcag.passes.length, `axe's rules that passed over the Pumps tab, ${where}`)
		.toBeGreaterThan(0);
	// Every table's Fields menu open too, one at a time (a menu under its button from 640 px, a
	// sheet on a phone): a disclosure axe never sees while it is hidden (§9 S6, §10 axe; S6 review
	// MUT-01). Each closed again by Escape from its button.
	const fieldsButtons = page.locator(`${panel} button[aria-controls][aria-expanded]`);
	const menus = await fieldsButtons.evaluateAll((all) =>
		all
			.map((b, i) => ({
				i,
				menu: document
					.getElementById(b.getAttribute('aria-controls') ?? '')
					?.getAttribute('aria-label')
			}))
			.filter((b) => b.menu?.startsWith('Fields shown in '))
	);
	expect.soft(menus.length, `the Fields menus in the Pumps tab, ${where}`).toBeGreaterThan(0);
	for (const { i, menu } of menus) {
		const button = fieldsButtons.nth(i);
		await button.scrollIntoViewIfNeeded();
		await button.click();
		await expect(page.getByRole('group', { name: menu! })).toBeVisible();
		const open = await new AxeBuilder({ page })
			.include(panel)
			.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
			.analyze();
		expect
			.soft(
				open.violations.map((v) => `${v.id} (${v.nodes.length})`),
				`axe over the Pumps tab, "${menu}" open, ${where}`
			)
			.toEqual([]);
		await button.focus();
		await page.keyboard.press('Escape');
		await expect(button).toHaveAttribute('aria-expanded', 'false');
	}
	const outline = await new AxeBuilder({ page })
		.include(panel)
		.withRules(['heading-order', 'landmark-unique'])
		.analyze();
	expect
		.soft(
			outline.violations.map((v) => `${v.id} (${v.nodes.length})`),
			`axe's heading-order and landmark-unique over the Pumps tab, ${where}`
		)
		.toEqual([]);
}

// ---- S3: Station and Group chart (§9 S3) -----------------------------------------------------

/**
 * §5.7 row 5: the card's header to the station's first value, at most this: from the header's
 * bottom (its toggle's) to the top of the first value of the dl "The station", as S3's first half
 * measured it (397 px in the condenser at 1280×800). The audit's "Before" (3,522 px, §2.1) ran
 * from the card's top to the dl's, 56 px more (the card's padding and its 44 px header).
 */
const STATION_BELOW_HEADER: Readonly<Record<string, number>> = {
	'1280x800': 400,
	'390x844': 600
};
/**
 * §5.7 row 7: the longest run of notes with no heading or control between them, paragraphs, as
 * drawn: a run inside a disclosure the user opened to read (the methods' items, in the lineups
 * view, which opens every one) is reference text, not counted; at its defaults (the condenser's
 * view, the one-off's) nothing is open, so every run counts.
 */
const LONGEST_RUN = { card: 5, tab: 6 };
/**
 * §5.7 row 8: the ring notes under "Other cases on the group chart" at 1280×800, "How to read the
 * rings" closed (its default), from the first note under the live line to the last: the lineups'
 * measured in S3 + 10 % (458 px, so 503), the condenser's set from S8's words, the mock's after-S8
 * 466 px + 10 % (S3 measured 402).
 */
const RING_NOTES_1280: Readonly<Record<string, number>> = {
	'2-lineups': 503,
	'3-condenser': 513
};
/** §5.7 row 10: Tab stops from the card's header to the group chart's Show data table. */
const TABS_TO_GROUP_TABLE = 20;
/** §5.7 row 4: the lineups' group legend at 390×844: measured in S3 + 10 % (332 px), and ≤ 452 px. */
const LEGEND_390 = 365;

/**
 * No name in the card cut short: no button, summary, label, list item, legend or heading, and
 * nothing inside one, whose words run past its own box, so each shows its end (a name's end can be
 * what tells two apart, §15 item 17). Inside one too, since a child that clips its own words (an
 * ellipsis, `overflow: hidden`) leaves its parent's box whole (S3 review MUT-08). Each one cut,
 * by its tag, its first words and its widths.
 */
async function cutInCard(page: Page): Promise<string[]> {
	return page.evaluate(() => {
		const c = document.querySelector('[data-pumps-together]')!;
		const roots = 'button, summary, label, li, legend, h4, h5';
		return [...c.querySelectorAll(`${roots}, :is(${roots}) *`)]
			.filter((el): el is HTMLElement => el instanceof HTMLElement)
			.filter((el) => {
				const r = el.getBoundingClientRect();
				return el.checkVisibility() && r.width > 1 && el.scrollWidth > el.clientWidth + 1;
			})
			.map(
				(el) =>
					`${el.tagName.toLowerCase()} "${(el.textContent ?? '').trim().slice(0, 50)}" ${el.scrollWidth} in ${el.clientWidth}`
			);
	});
}

/**
 * Below 640 px the group table reads as a list (§5.3 Station, §5.5), so its box never scrolls
 * sideways, a long name wrapping inside its line (S3 review LAYOUT-2); at 640 px and over it is a
 * table, whose box may (false then).
 */
async function groupTableSideways(page: Page): Promise<boolean> {
	return page.evaluate(() => {
		// The table's box (a region only while it overflows since S7, §9 S7).
		const box = document.querySelector<HTMLElement>(
			'[data-pumps-together] [data-group-table] table[role="table"]'
		)?.parentElement;
		return !!box && window.innerWidth < 640 && box.scrollWidth > box.clientWidth + 1;
	});
}

/**
 * The card's part of S3 at the size shown, with the card open (soft, so a run reports every
 * check): its budgets (§5.7 rows 4, 5, 7, 8, 10); the other cases under their h5, the switch
 * before the list it reveals, in the DOM and on screen (§10 Order), their own live line at rest
 * (§7 Live regions), the ring notes in sight with "How to read the rings" closed before the list
 * (§5.3), and no name in the card cut short (a name the user must read is shown to its end).
 */
async function cardPart(
	page: Page,
	view: string,
	where: string,
	data: Awaited<ReturnType<typeof measure>>
) {
	const soft = expect.configure({ soft: true });
	const size = sizeOf(page);
	const tab = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const toggle = card.getByRole('button', { name: /^Pumps together/ });
	if ((await toggle.getAttribute('aria-expanded')) !== 'true') {
		// The card closed (the one-off view's defaults): only the tab's run of notes is held.
		const tabRun = Math.max(
			0,
			...data.runs.filter((r) => !r.inDisclosure).map((r) => r.paragraphs)
		);
		console.log(`${where}: the longest run of notes, ${tabRun} paragraphs (the card closed)`);
		soft(tabRun, `the longest run of notes in the tab, ${where}`).toBeLessThanOrEqual(
			LONGEST_RUN.tab
		);
		return;
	}

	// §5.7 row 5: the station's first value under the card's header.
	const stationAt = await page.evaluate(() => {
		const c = document.querySelector('[data-pumps-together]')!;
		const header = c.querySelector('h3 button');
		const dl = c.querySelector('dl[aria-label="The station"]');
		const value = dl?.querySelector('dd');
		// In sight at a size of its own, not sr-only's 1 px box (S3 review MUT-09).
		const seen = (el: Element) => {
			const r = el.getBoundingClientRect();
			return (
				el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
				r.width > 1 &&
				r.height > 1
			);
		};
		return header && dl && value
			? {
					fromHeader: Math.round(
						value.getBoundingClientRect().top - header.getBoundingClientRect().bottom
					),
					fromCardTop: Math.round(dl.getBoundingClientRect().top - c.getBoundingClientRect().top),
					seen: [dl, ...dl.querySelectorAll('dt, dd')].every(seen)
				}
			: null;
	});
	const station = stationAt?.fromHeader ?? null;
	// The condenser's (§5.7 row 5): its card at its defaults, six members and four groups found.
	const stationBudget = view === '3-condenser' ? STATION_BELOW_HEADER[size] : undefined;
	console.log(
		`${where}: the station's first value ${station} px under the card's header (its dl ${stationAt?.fromCardTop} px under the card's top)`
	);
	soft(station, `the station's dl drawn, ${where}`).not.toBeNull();
	soft(stationAt?.seen, `the station's dl and its values in sight, ${where}`).toBe(true);
	if (stationBudget !== undefined && station !== null) {
		soft(
			station,
			`the station's first value under the card's header, ${where}`
		).toBeLessThanOrEqual(stationBudget);
	}

	// §5.7 row 7: the longest run of notes, in the card and in the tab.
	const drawn = data.runs.filter((r) => !r.inDisclosure);
	const cardRun = Math.max(0, ...drawn.filter((r) => r.inCard).map((r) => r.paragraphs));
	const tabRun = Math.max(0, ...drawn.map((r) => r.paragraphs));
	const opened = Math.max(0, ...data.runs.filter((r) => r.inDisclosure).map((r) => r.paragraphs));
	console.log(
		`${where}: the longest run of notes, ${cardRun} in the card, ${tabRun} in the tab (${opened} inside an opened disclosure)`
	);
	soft(cardRun, `the longest run of notes in the card, ${where}`).toBeLessThanOrEqual(
		LONGEST_RUN.card
	);
	soft(tabRun, `the longest run of notes in the tab, ${where}`).toBeLessThanOrEqual(
		LONGEST_RUN.tab
	);

	// The other cases (§5.3, §10 Order, §7 Live regions), and the ring notes' height (§5.7 row 8).
	const others = await page.evaluate(() => {
		const c = document.querySelector('[data-pumps-together]')!;
		const section = c.querySelector<HTMLElement>('[data-group-others]');
		if (!section) return null;
		const seen = (el: Element | null) => {
			if (!el) return false;
			const r = el.getBoundingClientRect();
			return (
				el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
				r.width > 1 &&
				r.height > 1
			);
		};
		const squash = (t: string | null) => (t ?? '').replace(/\s+/g, ' ').trim();
		const h5 = section.querySelector('h5');
		const box = [...section.querySelectorAll('label')].find((l) =>
			squash(l.textContent).startsWith("Also show the other cases' station duties")
		);
		const fieldset = section.querySelector('fieldset');
		const line = section.querySelector('[data-group-others-state]');
		const row = line?.parentElement ?? null;
		const how = section.querySelector<HTMLDetailsElement>('[data-group-rings-how]');
		// The ring notes, "How to read the rings" at its default (closed) while measured.
		const wasOpen = !!how?.open;
		if (how) how.open = false;
		const notes = row
			? [...section.children].slice([...section.children].indexOf(row) + 1).filter(seen)
			: [];
		// Every ring note after the live line's row (§5.3 top to bottom, §7 Tab order), so the
		// height above is theirs (S3 review MUT-07).
		const ringNotes = [
			...section.querySelectorAll(
				':scope > p:not([data-group-others-off]), :scope > [data-group-rings-how], :scope > [data-group-rings]'
			)
		];
		const height = notes.length
			? Math.round(
					notes.at(-1)!.getBoundingClientRect().bottom - notes[0]!.getBoundingClientRect().top
				)
			: 0;
		const list = section.querySelector('[data-group-rings] ul');
		const lead = list ? document.getElementById(list.getAttribute('aria-labelledby') ?? '') : null;
		const inSight = [
			...section.querySelectorAll(':scope > p'),
			...(list ? [lead, ...list.querySelectorAll('li')] : [])
		].filter((el): el is Element => !!el);
		const result = {
			h5: squash(h5?.textContent ?? null),
			switchFirst:
				!!box && !!h5 && !!(h5.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING),
			listAfterSwitch:
				!fieldset ||
				(!!box &&
					!!(box.compareDocumentPosition(fieldset) & Node.DOCUMENT_POSITION_FOLLOWING) &&
					fieldset.getBoundingClientRect().top >= box.getBoundingClientRect().bottom - 0.5),
			line: line
				? {
						live: line.getAttribute('aria-live'),
						atomic: line.getAttribute('aria-atomic'),
						role: line.getAttribute('role'),
						text: squash(line.textContent),
						busyAncestor: !!line.parentElement?.closest('[aria-busy="true"]'),
						buttons: line.querySelectorAll('button').length,
						first: line.parentElement?.firstElementChild === line
					}
				: null,
			howBeforeList:
				!how ||
				(!!list && !!(how.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING)),
			howOpen: wasOpen,
			notesAfterRow:
				!!row &&
				ringNotes.every(
					(n) => !!(row.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING)
				),
			rings: list ? list.querySelectorAll('li').length : 0,
			unseen: inSight.filter((el) => !seen(el)).map((el) => squash(el.textContent).slice(0, 60)),
			height,
			heights: notes.map((n) => ({
				what: squash(n.textContent).slice(0, 40),
				height: Math.round(n.getBoundingClientRect().height)
			}))
		};
		if (how) how.open = wasOpen;
		return result;
	});
	soft(others, `the other cases on the group chart, ${where}`).not.toBeNull();
	if (others) {
		console.log(
			`${where}: the ring notes ${others.height} px (${others.rings} rings): ${others.heights
				.map((h) => `${h.what} ${h.height}`)
				.join('; ')}`
		);
		soft(others.h5, `the other cases' heading, ${where}`).toBe('Other cases on the group chart');
		soft(others.switchFirst, `the switch first under the h5, ${where}`).toBe(true);
		soft(others.listAfterSwitch, `"Cases on this chart" after its switch, ${where}`).toBe(true);
		soft(others.line, `the other cases' live line at rest, ${where}`).toEqual({
			live: 'polite',
			atomic: 'true',
			role: null,
			text: '',
			busyAncestor: false,
			buttons: 0,
			first: true
		});
		soft(others.howBeforeList, `"How to read the rings" before the ring list, ${where}`).toBe(true);
		// Closed by default (§5.3): the condenser's view leaves every disclosure as drawn.
		if (view === '3-condenser') {
			soft(others.howOpen, `"How to read the rings" at its default, ${where}`).toBe(false);
		}
		soft(others.rings, `the ring list's lines, ${where}`).toBeGreaterThan(0);
		soft(others.notesAfterRow, `the ring notes after the live line's row, ${where}`).toBe(true);
		if (others.rings > 0) {
			soft(others.height, `the ring notes measured, ${where}`).toBeGreaterThan(0);
		}
		soft(others.unseen, `the ring notes out of sight, ${where}`).toEqual([]);
		const ringBudget = size === '1280x800' ? RING_NOTES_1280[view] : undefined;
		if (ringBudget) {
			soft(others.height, `the ring notes' height, ${where}`).toBeLessThanOrEqual(ringBudget);
		}
	}
	// The record (PUMPS_LAYOUT_RECORD): the other cases' section as measured, "How to read the
	// rings" closed, then open (the frame and the rule, §6.2 S8's W3 to W6).
	if (RECORD && others && others.rings > 0) {
		mkdirSync(path.join(RECORD, 'segments'), { recursive: true });
		const section = card.locator('[data-group-others]');
		const how = section.locator('[data-group-rings-how]');
		const hasHow = (await how.count()) > 0;
		const setOpen = async (open: boolean) => {
			if (hasHow) await how.evaluate((d, o) => ((d as HTMLDetailsElement).open = o), open);
		};
		for (const open of hasHow ? [false, true] : [false]) {
			await setOpen(open);
			await elementScreens(page, section, `rings-${view}-${size}-${open ? 'open' : 'closed'}`);
		}
		await setOpen(others.howOpen);
	}

	// §5.7 row 4: the group legend's height (the lineups' at 390×844 is the budget).
	const legend = await card.getByRole('list', { name: 'Legend' }).boundingBox();
	const legendHeight = legend ? Math.round(legend.height) : null;
	console.log(`${where}: the group legend ${legendHeight} px`);
	if (view === '2-lineups' && size === '390x844' && LEGEND_390 && legendHeight !== null) {
		soft(legendHeight, `the group legend's height, ${where}`).toBeLessThanOrEqual(LEGEND_390);
		soft(legendHeight, `the group legend's height, ${where}`).toBeLessThanOrEqual(452);
	}

	soft(await cutInCard(page), `names cut short in the card, ${where}`).toEqual([]);
	soft(await groupTableSideways(page), `the group table's box scrolls sideways, ${where}`).toBe(
		false
	);

	// §5.7 row 10: Tab stops from the card's header to the group chart's Show data table.
	await toggle.focus();
	let stops = 0;
	for (; stops < 80; stops++) {
		const at = await page.evaluate(() => {
			const a = document.activeElement;
			return (
				!!a &&
				/^(Show|Hide) data table of the group chart$/.test(
					(a.textContent ?? '').replace(/\s+/g, ' ').trim()
				)
			);
		});
		if (at) break;
		await page.keyboard.press('Tab');
	}
	console.log(`${where}: ${stops} Tab stops from the card's header to the group's Show data table`);
	if (view === '3-condenser') {
		soft(
			stops,
			`Tab stops from the card's header to the group's Show data table, ${where}`
		).toBeLessThanOrEqual(TABS_TO_GROUP_TABLE);
	} else {
		soft(stops, `the group's Show data table reached by Tab, ${where}`).toBeLessThan(80);
	}
}

// ---- S4: Add cases (§9 S4) --------------------------------------------------------------------

/**
 * §5.5 and §6.4 item 7 (D24's measured block re-measured): Add cases folded, every planned case
 * made and the plan closed, at most this tall: S4's measurement + 10 %, the lineups' 354 / 370 px
 * and the condenser's 378 / 410 px (its "Now ticked" line drawn after its Add), at 1280×800 /
 * 390×844. Before S4 the block was 624 px in the condenser after its Add (§2.1), and D24 measured
 * it closed at 440 and 504 px.
 */
const ADD_CASES_FOLDED: Readonly<Record<string, Readonly<Record<string, number>>>> = {
	'2-lineups': { '1280x800': 389, '390x844': 407 },
	'3-condenser': { '1280x800': 415, '390x844': 451 }
};

/** Add cases as laid out (viewport px): its parts, its text lines, and the plan folded. */
function readAddCases(b: Element) {
	const R = Math.round;
	const r = b.getBoundingClientRect();
	const cs = getComputedStyle(b);
	const inner = {
		left: r.left + parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft),
		right: r.right - parseFloat(cs.borderRightWidth) - parseFloat(cs.paddingRight)
	};
	const squash = (t: string | null | undefined) => (t ?? '').replace(/\s+/g, ' ').trim();
	const mid = (e: Element) => {
		const x = e.getBoundingClientRect();
		return x.top + x.height / 2;
	};
	const h4 = b.querySelector('h4')!;
	const tag = b.querySelector('[data-add-cases-tag]');
	const label = b.querySelector('.label');
	const group = b.querySelector('[role="radiogroup"]');
	const segments = group
		? [...group.querySelectorAll('label')].map((l) => l.getBoundingClientRect())
		: [];
	const plan = b.querySelector<HTMLDetailsElement>('[data-lineup-plan]');
	const solveAlls = [...b.querySelectorAll('button')].filter((x) =>
		/^Solve all/.test(squash(x.textContent))
	);
	const row = solveAlls[0]?.parentElement ?? null;
	// Every line of text in sight inside the panel's padding: a long name wraps there (§5.5).
	const past: string[] = [];
	const walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
	for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
		const el = n.parentElement!;
		if (!n.data.trim() || !el.checkVisibility() || el.closest('.sr-only')) continue;
		const range = document.createRange();
		range.selectNodeContents(n);
		for (const box of range.getClientRects()) {
			if (box.width > 0 && (box.right > inner.right + 0.5 || box.left < inner.left - 0.5)) {
				past.push(
					`${el.tagName.toLowerCase()} "${n.data.trim().slice(0, 40)}" ${R(box.left)} to ${R(box.right)} in ${R(inner.left)} to ${R(inner.right)}`
				);
			}
		}
	}
	// The scroller and the nav, for where a press of the nav's "Add cases" leaves the row.
	let scroller: HTMLElement | null = null;
	for (let e = b.parentElement; e; e = e.parentElement) {
		if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
			scroller = e;
			break;
		}
	}
	const navHeight = document.querySelector('[data-pumps-nav]')?.getBoundingClientRect().height ?? 0;
	// Folded (§5.3 The fold): the plan closed, as it is drawn once every planned case exists.
	const fold = () => ({
		height: R(b.getBoundingClientRect().height),
		// A press lands the h4 0.5 rem under the pinned nav (§5.4): is the row then in the pane?
		rowInSight:
			!!row &&
			!!scroller &&
			row.getBoundingClientRect().bottom - h4.getBoundingClientRect().top + navHeight + 8 <=
				scroller.clientHeight
	});
	let folded: ReturnType<typeof fold> | null = null;
	if (plan) {
		const was = plan.open;
		plan.open = false;
		folded = fold();
		plan.open = was;
	}
	// The frame's padding at its foot, under its last part in sight, and at its head (§5.3).
	const shown = [...b.children].filter(
		(c) => !c.classList.contains('sr-only') && c.getBoundingClientRect().height > 1
	);
	const pad = {
		head: R(shown[0]!.getBoundingClientRect().top - r.top),
		foot: R(r.bottom - shown.at(-1)!.getBoundingClientRect().bottom)
	};
	return {
		height: R(r.height),
		pad,
		planOpen: plan?.open ?? null,
		summary: squash(plan?.querySelector(':scope > summary')?.textContent),
		h4: getComputedStyle(h4).fontSize,
		tag: tag ? getComputedStyle(tag).fontSize : null,
		tagBesideH4:
			!!tag && Math.abs(mid(tag) - mid(h4)) < 4 && tag.parentElement === h4.parentElement,
		label: label ? getComputedStyle(label).fontSize : null,
		segmentsOneRow: segments.length === 2 && Math.abs(segments[0]!.top - segments[1]!.top) < 1,
		group: group ? R(group.getBoundingClientRect().height) : null,
		solveAll: solveAlls.length,
		past,
		folded
	};
}

/**
 * Add cases' part of S4 at the size shown, with the card open (soft, so a run reports every
 * check): the panel's type (the h4 14 px, its label and tag 12 px, the tag beside the h4), its
 * segments one row of 44 px (§5.5), one Solve all, every line inside the frame, the plan's
 * folded height (§5.7 via ADD_CASES_FOLDED) with the row in sight after the nav's press (§2.2),
 * and its Tab order (§7 item 24): the segments, the plan's summary and what it holds, Add,
 * Solve all, the table button.
 */
async function addCasesPart(page: Page, view: string, where: string) {
	const soft = expect.configure({ soft: true });
	const size = sizeOf(page);
	const block = page.locator('[data-pumps-together] [data-add-cases]');
	if (!(await block.count())) return;
	const m = await block.evaluate(readAddCases);
	console.log(
		`${where}: Add cases ${m.height} px (the plan ${m.planOpen ? 'open' : 'closed'}), folded ${m.folded?.height} px, the row ${m.folded?.rowInSight ? 'in sight' : 'out of sight'} after the nav's press; "${m.summary}"`
	);
	soft(m.h4, `Add cases' h4, ${where}`).toBe('14px');
	soft(m.label, `"Cases to add", ${where}`).toBe('12px');
	soft(m.tag, `"Changes the project", ${where}`).toBe('12px');
	soft(m.tagBesideH4, `the tag beside the h4, ${where}`).toBe(true);
	soft(m.segmentsOneRow, `the segments one row, ${where}`).toBe(true);
	soft(m.group, `the segments' height, ${where}`).toBeGreaterThanOrEqual(44);
	soft(m.solveAll, `Solve all in the block, ${where}`).toBe(1);
	soft(m.past, `lines past Add cases' frame, ${where}`).toEqual([]);
	soft(m.pad.foot, `the frame's padding at its foot as at its head, ${where}`).toBe(m.pad.head);
	soft(m.folded, `the plan drawn, ${where}`).not.toBeNull();
	const budget = ADD_CASES_FOLDED[view]?.[size];
	if (budget !== undefined && m.folded) {
		soft(m.folded.height, `Add cases folded, ${where}`).toBeLessThanOrEqual(budget);
		soft(m.folded.rowInSight, `Add and Solve all in sight after the nav's press, ${where}`).toBe(
			true
		);
	}
	// The lines the block shows as text are on screen, each where it is drawn (§9 S4 New lines;
	// §5.3 items 4 and 5; S4 review MUT-01, MUT-02): the tag, the plan's summary clause, Add's
	// refusal, "Now ticked", the id line while the plan is open, and Solve all's reason while it
	// lasts (unavailable at rest: no solve runs here).
	const lines: [string, Locator][] = [
		['"Changes the project"', block.locator('[data-add-cases-tag]')],
		["the plan's summary clause", block.locator('[data-lineup-plan] > summary > span > span')],
		["Add's refusal", block.locator('[id$="-refusal"]')],
		['"Now ticked"', block.locator('[data-now-ticked]')]
	];
	if (m.planOpen) lines.push(['the id line', block.locator('[data-lineup-ids]')]);
	const solveAllButton = block.getByRole('button', { name: /^Solve all/ });
	if (
		(await solveAllButton.count()) === 1 &&
		(await solveAllButton.getAttribute('aria-disabled')) === 'true'
	) {
		lines.push(["Solve all's lasting reason", block.locator('[id$="-solve-all"]')]);
	}
	for (const [what, line] of lines) {
		if (!(await line.count())) continue;
		soft(await seenLine(line), `${what} on screen, ${where}`).toBe(true);
	}

	// §7 item 24: the Tab order through the block, from its segments.
	const checked = block.locator('[role="radiogroup"] input:checked');
	await checked.focus();
	const stops: { name: string; inPlan: boolean; inBlock: boolean; summary: boolean }[] = [];
	for (let i = 0; i < 60; i++) {
		const at = await page.evaluate(() => {
			const a = document.activeElement as HTMLElement;
			const b = document.querySelector('[data-pumps-together] [data-add-cases]')!;
			return {
				name: (a.getAttribute('aria-label') ?? a.textContent ?? (a as HTMLInputElement).value ?? '')
					.replace(/\s+/g, ' ')
					.trim(),
				inPlan: !!a.closest('[data-lineup-plan]'),
				inBlock: b.contains(a),
				summary: a.tagName === 'SUMMARY'
			};
		});
		if (!at.inBlock) break;
		stops.push(at);
		await page.keyboard.press('Tab');
	}
	const names = stops.map((t) => t.name);
	soft(stops[0]?.inPlan, `the segments first, outside the plan, ${where}`).toBe(false);
	soft(
		stops[1]?.summary && /^The plan: /.test(stops[1].name),
		`then the plan's summary, ${where}`
	).toBe(true);
	soft(
		stops.slice(1, -3).every((t) => t.inPlan),
		`then what the plan holds, ${where}: ${names.join(' | ')}`
	).toBe(true);
	soft(
		names.slice(-3).map((n) => n.replace(/ \(\d+\)$/, '').replace(/^Add (\d+ )?cases?$/, 'Add')),
		`then the row and the table button, ${where}`
	).toEqual(['Add', 'Solve all', 'Pump lineups table…']);
}

// ---- S5: Running combinations' lead and the extremes as a table (§5.3, §9 S5, §10 S5) ----------

/** Running combinations' lead in each view with scenarios and a station shown (§5.3, §6.2). */
const COMBINATIONS_LEAD: Readonly<Record<string, { text: string; mark: string | null }>> = {
	// The proposal's own example (§5.3): S7's Pump P1 has a warning flag.
	'2-lineups': {
		text: '9 cases: 9 with current results (none physically invalid, 1 with warnings), none out of date, none without results.',
		mark: 'Warning'
	},
	// The condenser's cases with pumps off run the others beyond their curves (§10 New tests).
	'3-condenser': {
		text: '7 cases: 7 with current results (4 physically invalid, none with warnings), none out of date, none without results.',
		mark: 'Physically invalid'
	}
};
const EXTREMES_COLUMNS = ['Pump', 'Largest flow', 'Largest shaft power', 'Smallest NPSH margin'];
/**
 * A list line's header ending in a space as drawn: its column's words and a space, as ::before
 * content (the mock's `attr(data-label) " "`; S5 review EXT-1, LAYOUT-1), as getComputedStyle
 * gives it, one string.
 */
const lineHeader = (label: string) => `"${label} "`;
/**
 * §5.7 row 9: the condenser's extremes with their h5 (the h5, the box and "Not counted"), at most
 * this: S5's measurement + 10 %, 725 px at 1280×800 (the mock's table 711 px and the h5) and 893 at
 * 390×844 (the mock's list 834 px), so 797 and 982. At 320×640 no budget (§5.7).
 */
const EXTREMES_HEIGHT: Readonly<Record<string, number>> = {
	'1280x800': 797,
	'390x844': 982
};

/**
 * The extremes table as drawn (§5.3 the extremes): its form (a table from 26 rem of its box, a
 * list below), its box, its headers and rows, each cell's text and line header, the icons in its
 * cells and in Running combinations' value cells, and the lead with its mark.
 */
function readExtremes() {
	const section = document.querySelector('[data-pumps-together] [data-group-combinations]');
	const box = section?.querySelector<HTMLElement>('[data-extremes]');
	const table = box?.querySelector('table');
	if (!section || !box || !table) return null;
	const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
	const OCTAGON = 'M8 3h8l5 5v8l-5 5H8l-5-5V8z';
	const TRIANGLE = 'M12 3 2 20h20z';
	const shapes = (el: Element) =>
		[...el.querySelectorAll('svg')].map((svg) => svg.querySelector('path')!.getAttribute('d'));
	/**
	 * A cell's value against the words after it on its line (S5 review EXT-2): the bottom of the
	 * rest's first line box less the bottom of the amount's text, in px, where the two share a
	 * line (null otherwise, or with no amount). 0 when the value sits on the line's baseline.
	 */
	const lift = (td: Element) => {
		const [amount, rest] = [...td.children];
		const text = [...(amount?.childNodes ?? [])].find(
			(n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? '').trim() !== ''
		);
		if (!amount || !rest || !text || amount.tagName !== 'SPAN') return null;
		const range = document.createRange();
		range.selectNodeContents(text);
		const a = range.getBoundingClientRect();
		range.selectNodeContents(rest);
		const r = range.getClientRects()[0];
		if (!r || r.top >= a.bottom) return null;
		return Math.round((r.bottom - a.bottom) * 10) / 10;
	};
	const thead = table.querySelector('thead')!;
	const rows = [...table.querySelectorAll('tbody tr')].map((tr) => {
		const th = tr.querySelector('th')!;
		const cells = [...tr.querySelectorAll('td')] as HTMLElement[];
		return {
			name: th.textContent ?? '',
			nameShown: th.scrollWidth <= th.clientWidth + 1,
			nameDisplay: getComputedStyle(th).display,
			nameWeight: getComputedStyle(th).fontWeight,
			cells: cells.map((td) => ({
				label: td.dataset.label ?? '',
				text: td.textContent ?? '',
				display: getComputedStyle(td).display,
				before: getComputedStyle(td, '::before').content,
				octagons: shapes(td).filter((d) => d === OCTAGON).length,
				triangles: shapes(td).filter((d) => d === TRIANGLE).length,
				others: shapes(td).filter((d) => d !== OCTAGON).length,
				lift: lift(td)
			}))
		};
	});
	// Its value cells: every cell but the flag lines' (S5's second half: no Flags column).
	const combos = [...section.querySelectorAll('[data-running-combinations] td')].filter(
		(td) => !td.querySelector('[data-label="Flags"]')
	);
	const lead = section.querySelector('[data-combinations-lead]');
	const mark = section.querySelector('[data-combinations-mark]');
	const container = box.parentElement!;
	return {
		width: Math.round(box.getBoundingClientRect().width),
		list: box.getBoundingClientRect().width < 26 * rem,
		display: getComputedStyle(table).display,
		sideways: box.scrollWidth > box.clientWidth + 1,
		tabindex: box.getAttribute('tabindex'),
		role: box.getAttribute('role'),
		containerType: getComputedStyle(container).containerType,
		containerWidth: Math.round(container.getBoundingClientRect().width),
		frame: getComputedStyle(box).borderTopWidth,
		height: Math.round(container.getBoundingClientRect().height),
		headClipped:
			getComputedStyle(thead).position === 'absolute' && thead.getBoundingClientRect().width <= 1,
		caption: table.querySelector('caption')?.textContent ?? '',
		columns: [...thead.querySelectorAll('th')].map((th) => th.textContent ?? ''),
		rows,
		combos: combos.map((td) => ({
			marked: td.textContent!.includes('physically invalid:'),
			octagons: shapes(td).filter((d) => d === OCTAGON).length,
			triangles: shapes(td).filter((d) => d === TRIANGLE).length
		})),
		lead: lead?.textContent ?? null,
		leadTag: lead?.tagName ?? null,
		mark: mark
			? {
					role: mark.getAttribute('role'),
					name: mark.getAttribute('aria-label'),
					// Drawn, its octagon or alert too: not only named (S5 review MUT-03).
					seen: [mark, mark.querySelector('svg')].every((el) => {
						const r = el?.getBoundingClientRect();
						return (
							!!el &&
							!!r &&
							el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
							r.width > 1 &&
							r.height > 1
						);
					}),
					beforeLead: mark.nextElementSibling === lead,
					shape:
						shapes(mark)[0] === OCTAGON
							? 'octagon'
							: shapes(mark)[0] === TRIANGLE
								? 'triangle'
								: 'other'
				}
			: null
	};
}

/**
 * The extremes as a list (soft; S5 review EXT-2): each value on its line's baseline, the octagon
 * beside it, so the amount's text and the words after it end on one line, in an invalid cell as
 * in a valid one (§5.3: the cell's words after it on the same line).
 */
function listLines(m: NonNullable<ReturnType<typeof readExtremes>>, where: string) {
	const soft = expect.configure({ soft: true });
	const measured = m.rows.flatMap((r) =>
		r.cells
			.filter((c) => c.lift !== null)
			.map((c) => ({ what: `"${r.name}", ${c.label}`, lift: c.lift!, marked: c.octagons > 0 }))
	);
	soft(measured.length, `the list's values measured on their lines, ${where}`).toBeGreaterThan(0);
	const marked = measured.filter((c) => c.marked).length;
	console.log(`${where}: the list's values on their lines, ${measured.length} (${marked} marked)`);
	for (const c of measured) {
		soft(
			Math.abs(c.lift),
			`${c.what}: its value lifted off its line (px), ${where}`
		).toBeLessThanOrEqual(0.5);
	}
}

/**
 * Each extremes cell's accessible name (soft; §7: in the list it gains its header there; S5
 * review EXT-1): in the list its column's words, a space, then its words, "no case gives one"
 * too, never the two run together; in the table its words alone.
 */
async function extremesNames(page: Page, list: boolean, where: string) {
	await cellNames(page.locator('[data-pumps-together] [data-extremes] td'), list, where);
}

/**
 * Each cell's accessible name (soft): in a list form, whose line header is ::before content, its
 * column's words, a space, then its words; in a table its words alone.
 */
async function cellNames(cells: Locator, list: boolean, where: string) {
	const soft = expect.configure({ soft: true });
	const said = await cells.evaluateAll((all) =>
		all.map((td) => ({
			label: (td as HTMLElement).dataset.label ?? '',
			text: (td.textContent ?? '').replace(/\s+/g, ' ').trim()
		}))
	);
	for (const [i, c] of said.entries()) {
		await soft(
			cells.nth(i),
			`the accessible name of "${c.label}: ${c.text.slice(0, 30)}", ${where}`
		).toHaveAccessibleName(list ? `${c.label} ${c.text}` : c.text);
	}
}

/**
 * S5's first half at the size shown (soft): Running combinations' lead and its mark (§5.3: named
 * by the worst severity, the red octagon or the amber alert); the extremes a table from 26 rem of
 * its box and a list below, with the same roles, headers and data-labels, each line headed by its
 * data-label as ::before content and each cell's text its words (the same as in the table form:
 * at 1280×800 the box's container is narrowed to a list and read again); the box never scrolls
 * sideways and has no Tab stop; every pump name shown to its end; the red octagon in exactly the
 * cells whose words say "physically invalid", and in Running combinations' marked cells, and no
 * triangle in any (§5.2, §6.4 item 15); axe's table rules over the extremes (§9 S5 Proof).
 */
async function extremesPart(page: Page, view: string, where: string) {
	const soft = expect.configure({ soft: true });
	const m = await page.evaluate(readExtremes);
	if (!m) return;
	console.log(
		`${where}: the extremes a ${m.list ? 'list' : 'table'} in a ${m.width} px box, ${m.height} px with their h5; lead "${m.lead}" (${m.mark?.name ?? 'no mark'})`
	);
	// §5.7 row 9: the condenser's extremes' height (S5).
	const heightBudget = view === '3-condenser' ? EXTREMES_HEIGHT[sizeOf(page)] : undefined;
	if (heightBudget !== undefined) {
		soft(m.height, `the extremes' height with their h5, ${where}`).toBeLessThanOrEqual(
			heightBudget
		);
	}
	const expected = COMBINATIONS_LEAD[view];
	if (expected) {
		soft(m.lead, `Running combinations' lead, ${where}`).toBe(expected.text);
		soft(m.mark?.name ?? null, `the lead's mark, ${where}`).toBe(expected.mark);
	}
	soft(m.leadTag, `the lead a paragraph, ${where}`).toBe('P');
	// On screen as text at every size, not a 1 px box (§5.2 Answers; S5 review MUT-04).
	const leadLine = page.locator('[data-pumps-together] [data-combinations-lead]');
	soft(await seenLine(leadLine), `the lead on screen, ${where}`).toBe(true);
	if (m.mark) {
		// Drawn, and an image of that name in the page's accessibility tree, which leaves out
		// what CSS hides (S5 review MUT-03).
		soft(m.mark.seen, `the lead's mark drawn, ${where}`).toBe(true);
		await soft(
			leadLine.locator('xpath=..').getByRole('img', { name: m.mark.name ?? '', exact: true }),
			`the lead's mark an image named "${m.mark.name}" in the accessibility tree, ${where}`
		).toBeVisible();
		soft(m.mark.role, `the lead's mark an image, ${where}`).toBe('img');
		soft(m.mark.beforeLead, `the lead's mark its own element before its <p>, ${where}`).toBe(true);
		soft(m.mark.shape, `the lead's mark's shape, ${where}`).toBe(
			m.mark.name === 'Physically invalid' ? 'octagon' : 'triangle'
		);
	}
	soft(m.caption, `the extremes' caption, ${where}`).toBe('Extremes over these cases');
	soft(m.columns, `the extremes' column headers, ${where}`).toEqual(EXTREMES_COLUMNS);
	soft(m.rows.length, `a row per member, ${where}`).toBeGreaterThan(1);
	soft(m.sideways, `the extremes' box scrolls sideways, ${where}`).toBe(false);
	// A Tab stop and a region only while it overflows (S7's rule, §7 item 25): it never scrolls
	// sideways (above), so neither.
	soft(m.tabindex, `the extremes' box a Tab stop (S7's), ${where}`).toBeNull();
	soft(m.role, `the extremes' box a region (S7's), ${where}`).toBeNull();
	soft(m.containerType, `the extremes' container, ${where}`).toBe('inline-size');
	soft(m.containerWidth, `the container the box's width, ${where}`).toBe(m.width);
	soft(m.display, `the extremes' form, ${where}`).toBe(m.list ? 'block' : 'table');
	soft(m.headClipped, `the header row visually hidden in the list only, ${where}`).toBe(m.list);
	soft(m.frame, `the box's frame, ${where}`).toBe(m.list ? '0px' : '1px');
	for (const row of m.rows) {
		soft(row.nameShown, `"${row.name}" shown to its end, ${where}`).toBe(true);
		soft(
			row.cells.map((c) => c.label),
			`"${row.name}"'s cells under the measures, ${where}`
		).toEqual(EXTREMES_COLUMNS.slice(1));
		if (m.list) {
			soft(row.nameDisplay, `"${row.name}" heads its block, ${where}`).toBe('block');
			soft(row.nameWeight, `"${row.name}" in semibold, ${where}`).toBe('600');
		}
		for (const cell of row.cells) {
			const what = `"${row.name}", ${cell.label}, ${where}`;
			soft(cell.text.trim(), `${what}: its words`).not.toBe('');
			soft(cell.text.includes(cell.label), `${what}: its header outside its text`).toBe(false);
			soft(cell.display, `${what}: its form`).toBe(m.list ? 'block' : 'table-cell');
			soft(cell.before, `${what}: its line header`).toBe(m.list ? lineHeader(cell.label) : 'none');
			const invalid = cell.text.includes('; physically invalid');
			soft(cell.octagons, `${what}: the octagon`).toBe(invalid ? 1 : 0);
			soft(cell.others, `${what}: another icon`).toBe(0);
			soft(cell.triangles, `${what}: a triangle`).toBe(0);
		}
	}
	if (m.list) listLines(m, where);
	await extremesNames(page, m.list, where);
	for (const [i, cell] of m.combos.entries()) {
		soft(cell.octagons, `Running combinations' value cell ${i}: the octagon, ${where}`).toBe(
			cell.marked ? 1 : 0
		);
		soft(cell.triangles, `Running combinations' value cell ${i}: a triangle, ${where}`).toBe(0);
	}
	const axe = await new AxeBuilder({ page })
		.include('[data-pumps-together] [data-extremes]')
		.withRules(['td-has-header', 'th-has-data-cells', 'scope-attr-valid', 'td-headers-attr'])
		.analyze();
	soft(
		axe.violations.map((v) => `${v.id} (${v.nodes.length})`),
		`axe's table rules over the extremes, ${where}`
	).toEqual([]);
	soft(
		axe.passes.length,
		`axe's table rules that passed over the extremes, ${where}`
	).toBeGreaterThan(0);

	// From 26 rem a table: its container narrowed to a list below 26 rem reads the same words in
	// every cell, each line headed by its data-label (§10 S5: the same as at 1280×800).
	if (!m.list) {
		const container = page.locator('[data-pumps-together] [data-combination-extremes]');
		await container.evaluate((el) => (el.style.width = '20rem'));
		const narrowed = await page.evaluate(readExtremes);
		if (narrowed?.list) {
			listLines(narrowed, `narrowed to 20 rem, ${where}`);
			await extremesNames(page, true, `narrowed to 20 rem, ${where}`);
		}
		await container.evaluate((el) => (el.style.width = ''));
		soft(narrowed?.list, `the extremes narrowed to 20 rem a list, ${where}`).toBe(true);
		soft(narrowed?.display, `the extremes narrowed, its form, ${where}`).toBe('block');
		soft(
			narrowed?.rows.map((r) => [r.name, ...r.cells.map((c) => c.text)]),
			`the extremes narrowed to a list: every cell's words as in the table, ${where}`
		).toEqual(m.rows.map((r) => [r.name, ...r.cells.map((c) => c.text)]));
		soft(
			narrowed?.rows.flatMap((r) => r.cells.map((c) => c.before)),
			`the extremes narrowed: each line headed by its data-label, ${where}`
		).toEqual(m.rows.flatMap((r) => r.cells.map((c) => lineHeader(c.label))));
		soft(narrowed?.sideways, `the extremes narrowed scroll sideways, ${where}`).toBe(false);
	}
}

// ---- S5: Running combinations' order, lines and names (§5.3, §9 S5, §10 S5) ------------------

/**
 * §5.7 row 11: the open card, the condenser's after Add cases at 1280×800, at most this: the
 * measurement + 10 %. S5 set 10,501 from its 9,547 px (S4's 7,418; §5.7 estimated about 5,650):
 * each flagged pump's flags visible under its row, and the names wrapping at 12 rem in 42 rows.
 * Since S6b (§9 S6b) Running combinations is a ResultsTable, its box held to ResultsTable's
 * height there (608 px, scrolling inside, its headings sticky), so the card is 5,724 px: 6,296.
 */
const OPEN_CARD_1280 = 6_296;

/**
 * Running combinations as laid out (viewport px): its box and form; each case's group, its
 * heading's lines, its members' names and its flag lines, each read against the box's visible
 * width with the box at its start and scrolled to its end (the lines, names and flag lines are
 * sticky, §5.3); the cases of "Cases on this chart", ticked or not, which list them in the chart's
 * order (D24 §4.6); and "Other cases' station duties" while drawn (a list below 640 px, §9 S5).
 */
function readCombinations() {
	const card = document.querySelector('[data-pumps-together]');
	// The box: a ResultsTable's since S6b, the table's in the block that holds its controls (a
	// region only while it overflows since S7, §9 S7).
	const block = card?.querySelector<HTMLElement>('[data-running-combinations]');
	const box = block?.querySelector<HTMLElement>('table[role="table"]')?.parentElement;
	if (!card || !block || !box) return null;
	const table = box.querySelector('table')!;
	const squash = (t: string | null | undefined) => (t ?? '').replace(/\s+/g, ' ').trim();
	/** An element's words without its aria-hidden marks (a slot's symbol, a ring). */
	const words = (el: Element) => {
		const copy = el.cloneNode(true) as Element;
		for (const hidden of copy.querySelectorAll('[aria-hidden="true"]')) hidden.remove();
		return squash(copy.textContent);
	};
	const seen = (el: Element) => {
		const r = el.getBoundingClientRect();
		return (
			el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
			r.width > 1 &&
			r.height > 1
		);
	};
	const shownWhole = (el: Element) => el.scrollWidth <= el.clientWidth + 1;
	const b = box.getBoundingClientRect();
	const left = b.left + box.clientLeft;
	const right = left + box.clientWidth;
	const inView = (el: Element) => {
		const r = el.getBoundingClientRect();
		return r.left >= left - 0.5 && r.right <= right + 0.5;
	};
	const read = () =>
		[...table.querySelectorAll(':scope > tbody')].map((tbody) => {
			const heading = tbody.querySelector('th[scope="rowgroup"]')!;
			return {
				lines: [...heading.children].map((line) => ({
					text: squash(line.textContent),
					// On screen, not only in its place (S6 review MUT-03: a line made invisible kept
					// its text, position and box).
					seen: seen(line),
					position: getComputedStyle(line).position,
					inView: inView(line),
					shown: shownWhole(line)
				})),
				members: [...tbody.querySelectorAll('th[scope="row"]')].map((th) => {
					const name = th.firstElementChild!;
					return {
						name: words(name),
						button: name.tagName === 'BUTTON',
						inView: inView(name),
						shown: shownWhole(name) && [...name.children].every(shownWhole)
					};
				}),
				notes: [...tbody.querySelectorAll<HTMLElement>('[data-row-notes]')].map((note) => ({
					id: note.dataset.rowNotes ?? '',
					label: note.dataset.label ?? '',
					text: squash(note.textContent),
					inView: inView(note),
					said: [...note.querySelectorAll('li')].map((li) => {
						// The flag's sentence, its own element after the pill: drawn as text, not
						// only its item (§10 Flags: the flag text visible; S5 review MUT-01).
						const text = li.querySelector('[data-flag-text]');
						return {
							seen: seen(li),
							inView: inView(li),
							textSeen:
								!!text &&
								seen(text) &&
								!text.closest('.sr-only') &&
								text.getBoundingClientRect().height >= 12 &&
								squash(text.textContent) !== '',
							textInView: !!text && inView(text)
						};
					})
				}))
			};
		});
	const atStart = read();
	const sideways = box.scrollWidth > box.clientWidth + 1;
	box.scrollLeft = box.scrollWidth;
	const atEnd = read();
	box.scrollLeft = 0;
	const fieldset = [...card.querySelectorAll('fieldset')].find(
		(f) => squash(f.querySelector('legend')?.textContent) === 'Cases on this chart'
	);
	const tag = fieldset?.querySelector(':scope > div > span');
	const duties = card.querySelector<HTMLElement>('[data-other-duties]');
	const dutiesTable = duties?.querySelector('table');
	const dutiesHead = dutiesTable?.querySelector('thead');
	return {
		containerType: getComputedStyle(box).containerType,
		sideways,
		list: getComputedStyle(table).display === 'block',
		height: Math.round(b.height),
		columns: [...table.querySelectorAll('thead th')].map((th) => squash(th.textContent)),
		nones: [...table.querySelectorAll('td')].filter((td) => squash(td.textContent) === 'None')
			.length,
		titles: table.querySelectorAll('[title]').length,
		atStart,
		atEnd,
		chartOrder:
			fieldset && tag
				? [
						words(tag),
						...[...fieldset.querySelectorAll('label > span.min-w-0')].map((s) => words(s))
					]
				: null,
		duties:
			duties && dutiesTable && dutiesHead && seen(duties)
				? {
						display: getComputedStyle(dutiesTable).display,
						sideways: duties.scrollWidth > duties.clientWidth + 1,
						headClipped:
							getComputedStyle(dutiesHead).position === 'absolute' &&
							dutiesHead.getBoundingClientRect().width <= 1,
						names: [...dutiesTable.querySelectorAll('tbody th')].map((th) => ({
							name: words(th),
							shown: shownWhole(th)
						})),
						cells: [...dutiesTable.querySelectorAll<HTMLElement>('tbody td[data-label]')].map(
							(td) => ({
								label: td.dataset.label ?? '',
								text: squash(td.textContent),
								before: getComputedStyle(td, '::before').content,
								// A number cell (a pair) or a cell of words (S5 review LAYOUT-1).
								numeric: /tabular-nums/.test(td.className),
								style: `${getComputedStyle(td).fontSize} ${getComputedStyle(td).color} ${getComputedStyle(td).fontWeight}`,
								beforeStyle: `${getComputedStyle(td, '::before').fontSize} ${getComputedStyle(td, '::before').color} ${getComputedStyle(td, '::before').fontWeight}`
							})
						)
					}
				: null
	};
}

/**
 * S5's second half at the size shown (soft): Running combinations' order, lines and names (§5.3,
 * §9 S5). The box an inline-size container; the case shown first, then the cases in the chart's
 * order, ticked or not; each line of a group's heading sticky (in the table) and in view at the
 * box's start and end, shown to its end; no Flags column and no "None"; a flag line under each
 * flagged pump, its text visible inside the box's visible width; names shown to their end, trace
 * buttons in the shown case's group only; the list below 640 px with no sideways scroll; "Other
 * cases' station duties" a list below 640 px. And §5.7 row 11, the condenser's open card.
 */
async function combinationsPart(
	page: Page,
	view: string,
	where: string,
	data: Awaited<ReturnType<typeof measure>> | null
) {
	const soft = expect.configure({ soft: true });
	const m = await page.evaluate(readCombinations);
	const size = sizeOf(page);
	if (data?.card?.open) {
		console.log(`${where}: the open card ${data.card.height} px`);
		if (view === '3-condenser' && size === '1280x800') {
			soft(data.card.height, `the open card's height, ${where}`).toBeLessThanOrEqual(
				OPEN_CARD_1280
			);
		}
	}
	if (!m) return;
	const flagLines = m.atStart.reduce((n, g) => n + g.notes.length, 0);
	console.log(
		`${where}: Running combinations a ${m.list ? 'list' : 'table'}, ${m.height} px, ${m.atStart.length} cases, ${flagLines} flag lines${m.sideways ? ', scrolls sideways' : ''}`
	);
	soft(m.containerType, `Running combinations' box a container, ${where}`).toBe('inline-size');
	soft(m.list, `Running combinations a list below 640 px only, ${where}`).toBe(
		page.viewportSize()!.width < 640
	);
	if (m.list) soft(m.sideways, `Running combinations' list scrolls sideways, ${where}`).toBe(false);
	soft(m.columns, `no Flags column, ${where}`).not.toContain('Flags');
	soft(m.nones, `"None" in Running combinations, ${where}`).toBe(0);
	soft(m.titles, `a tooltip in Running combinations, ${where}`).toBe(0);
	// The order (§5.3): the case shown, then the chart's, ticked or not.
	const cases = m.atStart.map((g) => g.lines[0]?.text.replace(/ · ring \d+$/, '') ?? '');
	if (m.chartOrder) {
		soft(
			cases.slice(0, m.chartOrder.length),
			`Running combinations in the chart's order, ${where}`
		).toEqual(m.chartOrder);
	}
	soft(cases[0], `the case shown first, ${where}`).toMatch(/ \(shown\)/);
	for (const [label, groups] of [
		['at its start', m.atStart],
		['scrolled to its end', m.atEnd]
	] as const) {
		for (const [g, group] of groups.entries()) {
			const what = `"${cases[g]}" ${label}, ${where}`;
			for (const line of group.lines) {
				soft(line.seen, `${what}: "${line.text.slice(0, 40)}" on screen`).toBe(true);
				soft(line.position, `${what}: "${line.text.slice(0, 40)}" sticky`).toBe(
					m.list ? 'static' : 'sticky'
				);
				soft(line.inView, `${what}: "${line.text.slice(0, 40)}" in the box's view`).toBe(true);
				soft(line.shown, `${what}: "${line.text.slice(0, 40)}" shown to its end`).toBe(true);
			}
			for (const member of group.members) {
				soft(member.button, `${what}: "${member.name}" a trace button`).toBe(g === 0);
				soft(member.inView, `${what}: "${member.name}" in the box's view`).toBe(true);
				soft(member.shown, `${what}: "${member.name}" shown to its end`).toBe(true);
			}
			for (const note of group.notes) {
				soft(note.label, `${what}: a flag line's label`).toBe('Flags');
				soft(
					group.members.some((member) => note.text.startsWith(`${member.name}, flags:`)),
					`${what}: the flag line of ${note.id} named by its pump`
				).toBe(true);
				soft(note.inView, `${what}: the flag line of ${note.id} in the box's view`).toBe(true);
				soft(note.said.length, `${what}: the flag line of ${note.id}'s flags`).toBeGreaterThan(0);
				for (const said of note.said) {
					soft(said.seen, `${what}: a flag of ${note.id} visible`).toBe(true);
					soft(said.inView, `${what}: a flag of ${note.id} inside the box's view`).toBe(true);
					soft(said.textSeen, `${what}: a flag of ${note.id}: its text visible`).toBe(true);
					soft(said.textInView, `${what}: a flag of ${note.id}: its text in the box's view`).toBe(
						true
					);
				}
			}
		}
	}
	// S6b (§9 S6b): a ResultsTable, its controls, names, flag lines and shadow, in its own order.
	await combinationsTablePart(page, where, 'grouped');
	if (m.duties) {
		const list = page.viewportSize()!.width < 640;
		soft(m.duties.display, `"Other cases' station duties" a list below 640 px only, ${where}`).toBe(
			list ? 'block' : 'table'
		);
		soft(m.duties.headClipped, `its header row visually hidden in the list only, ${where}`).toBe(
			list
		);
		if (list) soft(m.duties.sideways, `its list scrolls sideways, ${where}`).toBe(false);
		for (const name of m.duties.names) {
			soft(name.shown, `"${name.name}" shown to its end in its duties, ${where}`).toBe(true);
		}
		soft(m.duties.cells.length, `"Other cases' station duties"' cells, ${where}`).toBeGreaterThan(
			0
		);
		for (const cell of m.duties.cells) {
			// A number's column's words alone (a flex pair), a cell of words' with a space.
			soft(cell.before, `a duty's line header (${cell.label}), ${where}`).toBe(
				list ? (cell.numeric ? `"${cell.label}"` : lineHeader(cell.label)) : 'none'
			);
			soft(cell.text.includes(cell.label), `a duty's header outside its text, ${where}`).toBe(
				false
			);
		}
		// In the list a cell of words in the list's value style, a number's (14 px slate-900), so
		// its column's words and its answer read apart (S5 review LAYOUT-1).
		const numbers = [...new Set(m.duties.cells.filter((c) => c.numeric).map((c) => c.style))];
		const words = m.duties.cells.filter((c) => !c.numeric && c.text !== '—');
		soft(numbers.length, `one style for the duties' numbers, ${where}`).toBe(1);
		if (list) {
			soft(words.length, `"Other cases' station duties"' cells of words, ${where}`).toBeGreaterThan(
				0
			);
			for (const cell of words) {
				const what = `"${cell.label}: ${cell.text.slice(0, 30)}", ${where}`;
				soft(cell.style, `${what}: its words as a number's`).toBe(numbers[0]);
				soft(cell.style, `${what}: its words apart from its column's`).not.toBe(cell.beforeStyle);
			}
		}
		await cellNames(
			page.locator('[data-pumps-together] [data-other-duties] tbody td[data-label]'),
			list,
			`"Other cases' station duties", ${where}`
		);
	}
}

// ---- S6b: Running combinations a ResultsTable (§9 S6b) -----------------------------------------

/**
 * Running combinations as a ResultsTable (§9 S6b; the owner's answer 3, §12) in either form, as
 * laid out (viewport px): its controls (Fields, Flagged only, a phone's "Sort by" with its room for
 * its longest field, the headings' sort buttons); its form, a row group per case or one flat table
 * with a Case column; each pump's row (its name, its case, its NPSH margin, a trace button or not,
 * in sight and shown to its end) and the flag line under it; and every element inside the box
 * that paints a fill over its right edge, where the sideways shadow is drawn (§15 item 157), with
 * the box scrolled to show more on its right and read screen by screen down it. A stale case's
 * amber is left out: it is its look (§5.3 Invalid and stale).
 */
function readCombinationsTable() {
	const block = document.querySelector<HTMLElement>(
		'[data-pumps-together] [data-running-combinations]'
	);
	// The table's box (a region only while it overflows since S7, §9 S7).
	const box = block?.querySelector<HTMLElement>('table[role="table"]')?.parentElement;
	const table = box?.querySelector('table');
	if (!block || !box || !table) return null;
	const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
	// In sight at a size of its own, inside no visually hidden box (readGroupTable's rule).
	const seen = (el: Element | null) => {
		if (!el) return false;
		const r = el.getBoundingClientRect();
		for (let a: Element | null = el; a; a = a.parentElement) {
			const b = a.getBoundingClientRect();
			if (getComputedStyle(a).overflow === 'hidden' && (b.width <= 1 || b.height <= 1)) {
				return false;
			}
		}
		return (
			el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
			r.width > 1 &&
			r.height > 1
		);
	};
	const whole = (el: Element | null) => !!el && el.scrollWidth <= el.clientWidth + 1;
	const headerRoom = (td: Element) => {
		const css = getComputedStyle(td, '::before');
		if (css.content === 'none' || !td.firstElementChild) return null;
		const context = document.createElement('canvas').getContext('2d')!;
		context.font = `${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
		const text = css.content.replace(/^"|"$/g, '');
		return {
			room: td.firstElementChild.getBoundingClientRect().left - td.getBoundingClientRect().left,
			text: Math.ceil(context.measureText(text).width)
		};
	};
	const drawn = (el: Element | null) => {
		if (!el) return '';
		const copy = el.cloneNode(true) as Element;
		for (const hidden of copy.querySelectorAll('.sr-only')) hidden.remove();
		return squash(copy.textContent);
	};
	const b = box.getBoundingClientRect();
	const left = b.left + box.clientLeft;
	const right = left + box.clientWidth;
	const inWidth = (el: Element) => {
		const r = el.getBoundingClientRect();
		return r.left >= left - 0.5 && r.right <= right + 0.5;
	};
	const select = block.querySelector<HTMLSelectElement>(
		'select[aria-label="Sort by, Running combinations"]'
	);
	const fields = [...block.querySelectorAll('button')].find((x) =>
		squash(x.textContent).startsWith('Fields')
	);
	const flagged = [...block.querySelectorAll('label')].find((l) =>
		squash(l.textContent).startsWith('Flagged only')
	);
	let sortRoom: {
		name: string;
		text: number;
		room: number;
		chosen: { name: string; text: number };
	} | null = null;
	if (select && seen(select)) {
		const css = getComputedStyle(select);
		const context = document.createElement('canvas').getContext('2d')!;
		context.font = `${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
		const longest = [...select.options].reduce(
			(widest, option) => {
				const width = context.measureText(option.text).width;
				return width > widest.width ? { name: option.text, width } : widest;
			},
			{ name: '', width: 0 }
		);
		const chosen = select.selectedOptions[0]?.text ?? '';
		sortRoom = {
			name: longest.name,
			text: Math.ceil(longest.width),
			room: Math.floor(
				select.clientWidth - parseFloat(css.paddingLeft) - parseFloat(css.paddingRight)
			),
			// The field shown while sorted, beside its direction button (S6 review TBL-4).
			chosen: { name: chosen, text: Math.ceil(context.measureText(chosen).width) }
		};
	}
	const headings = [...table.querySelectorAll('thead th')].map((h) => ({
		name: squash(h.textContent),
		button: !!h.querySelector('button'),
		seen: seen(h.querySelector('button') ?? h)
	}));
	const bodies = [...table.querySelectorAll(':scope > tbody')];
	const groupOf = (tr: Element) =>
		squash(tr.closest('tbody')?.querySelector('th[scope="rowgroup"] > :first-child')?.textContent);
	const rows = [...table.querySelectorAll(':scope > tbody > tr')]
		.filter((r) => r.querySelector('th[scope="row"]'))
		.map((r) => {
			const name = r.querySelector('th[scope="row"] span.min-w-0');
			const kase = r.querySelector('td[data-label="Case"]');
			const notes = r.nextElementSibling?.querySelector<HTMLElement>('[data-row-notes]') ?? null;
			return {
				name: squash(name?.textContent),
				nameSeen: seen(name),
				nameWhole: whole(name),
				case: kase ? squash(kase.textContent) : groupOf(r),
				caseCell: kase
					? {
							// Its words in sight, not only its cell (whose header is ::before content).
							seen: seen(kase.firstElementChild ?? kase),
							whole: whole(kase) && whole(kase.firstElementChild),
							before: getComputedStyle(kase, '::before').content,
							// A phone's header ("Case") whole on its line: the room before the words
							// against the header's own width (never "Cas" over "e").
							headerRoom: headerRoom(kase)
						}
					: null,
				// Its words as drawn: a marked value's "physically invalid:" is for screen readers.
				margin: drawn(r.querySelector('td[data-label="NPSH margin (m)"]')),
				head: r.querySelector('td[data-label^="Head"]') !== null,
				button: !!r.querySelector('th[scope="row"] button'),
				flags: notes
					? {
							id: notes.dataset.rowNotes ?? '',
							label: notes.dataset.label ?? '',
							hidden: [...notes.querySelectorAll('.sr-only')].map((e) => squash(e.textContent)),
							said: [...notes.querySelectorAll('[data-flag-text]')].map((t) => ({
								seen: seen(t),
								inWidth: inWidth(t),
								words: squash(t.textContent)
							}))
						}
					: null
			};
		});
	// Each value on its line: in a row, the first line of every cell's words (a marked value's
	// amount after its octagon included) shares one baseline with the cells beside it (§15 item
	// 157: a marked value 3 px above its line on a phone; EXT-2).
	const offLine: string[] = [];
	for (const tr of [...table.querySelectorAll(':scope > tbody > tr')].slice(0, 60)) {
		const lines: { cell: string; top: number; bottom: number }[] = [];
		for (const td of tr.querySelectorAll<HTMLElement>(':scope > td[data-label]')) {
			const walker = document.createTreeWalker(td, NodeFilter.SHOW_TEXT);
			for (let n = walker.nextNode(); n; n = walker.nextNode()) {
				if (!n.textContent?.trim() || n.parentElement?.closest('.sr-only')) continue;
				const range = document.createRange();
				range.selectNodeContents(n);
				const r = range.getClientRects()[0];
				if (r && r.height > 1) {
					lines.push({
						cell: `${td.dataset.label}: ${squash(td.textContent)}`,
						top: r.top,
						bottom: r.bottom
					});
				}
				break;
			}
		}
		for (const a of lines) {
			for (const c of lines) {
				if (Math.abs(a.top - c.top) < 6 && Math.abs(a.bottom - c.bottom) > 0.5) {
					offLine.push(`"${a.cell.slice(0, 40)}" against "${c.cell.slice(0, 40)}"`);
				}
			}
		}
	}
	// The fills over the box's right edge, screen by screen, the box scrolled to its middle.
	const covers: string[] = [];
	const sideways = box.scrollWidth > box.clientWidth + 1;
	if (sideways) {
		const [x0, y0] = [box.scrollLeft, box.scrollTop];
		box.scrollLeft = Math.floor((box.scrollWidth - box.clientWidth) / 2);
		const clear = (c: string) => c === 'rgba(0, 0, 0, 0)' || c === 'transparent';
		const top = b.top + box.clientTop;
		for (let at = 0; at < box.scrollHeight; at += Math.max(1, box.clientHeight)) {
			box.scrollTop = at;
			for (const el of box.querySelectorAll('tbody *')) {
				const bg = getComputedStyle(el).backgroundColor;
				if (clear(bg)) continue;
				const r = el.getBoundingClientRect();
				if (r.right <= right - 12 || r.left >= right) continue;
				if (r.bottom <= top || r.top >= top + box.clientHeight) continue;
				const tr = el.closest('tr');
				const stale =
					groupOf(el).includes('(out of date)') ||
					squash(tr?.querySelector('td[data-label="Case"]')?.textContent).includes(
						'(out of date)'
					) ||
					squash(
						tr?.previousElementSibling?.querySelector('td[data-label="Case"]')?.textContent
					).includes('(out of date)');
				if (stale) continue;
				covers.push(`<${el.tagName.toLowerCase()}> "${squash(el.textContent).slice(0, 30)}" ${bg}`);
			}
			if (box.scrollHeight <= box.clientHeight) break;
		}
		box.scrollLeft = x0;
		box.scrollTop = y0;
	}
	return {
		height: Math.round(b.height),
		scrollHeight: box.scrollHeight,
		list: getComputedStyle(table).display === 'block',
		sideways,
		flat: headings.some((h) => h.name === 'Case'),
		groups: bodies.map((t) =>
			t.querySelector('th[scope="rowgroup"]') ? groupOf(t.querySelector('tr')!) : null
		),
		headings,
		select: select ? { seen: seen(select), top: select.getBoundingClientRect().top } : null,
		sortRoom,
		fields: fields ? { seen: seen(fields), top: fields.getBoundingClientRect().top } : null,
		flagged: flagged ? { seen: seen(flagged), text: squash(flagged.textContent) } : null,
		rows,
		offLine: [...new Set(offLine)].slice(0, 6),
		covers: [...new Set(covers)]
	};
}

/**
 * Running combinations' S6b checks at the size shown (soft): its controls in sight (Fields,
 * Flagged only, the headings' sort buttons from 640 px, "Sort by" below it on one line with Fields,
 * showing its longest field to its end while unsorted, §15 item 17), its form as expected, a
 * trace button in each row of the shown case and in no other, every name and Case cell in sight
 * and shown to its end, each flag line under its own pump with its sentences in sight inside the
 * box's visible width, and no fill over the box's right edge, where its shadow is (§15 item 157).
 */
async function combinationsTablePart(page: Page, where: string, form: 'grouped' | 'flat') {
	const soft = expect.configure({ soft: true });
	const m = await page.evaluate(readCombinationsTable);
	if (!m) return null;
	const phone = (page.viewportSize()?.width ?? 1280) < 640;
	console.log(
		`${where}: Running combinations ${form}, a ${m.list ? 'list' : 'table'}, its box ${m.height} px (holding ${m.scrollHeight}), ${m.rows.length} rows, ${m.rows.filter((r) => r.flags).length} flag lines${m.sortRoom ? `, Sort by ${m.sortRoom.room} px for "${m.sortRoom.name}" (${m.sortRoom.text})` : ''}${m.flagged ? `, "${m.flagged.text}"` : ''}`
	);
	soft(m.flat, `Running combinations ${form}, ${where}`).toBe(form === 'flat');
	if (form === 'flat') {
		soft(m.groups, `one row group, no case heading, ${where}`).toEqual([null]);
		soft(
			m.headings.slice(0, 2).map((h) => h.name),
			`Pump and Case first, ${where}`
		).toEqual(['Pump', 'Case']);
	} else {
		soft(
			m.groups.every((g) => !!g),
			`a heading on every row group, ${where}`
		).toBe(true);
	}
	soft(m.fields?.seen, `Running combinations' Fields in sight, ${where}`).toBe(true);
	if (m.flagged) soft(m.flagged.seen, `its Flagged only in sight, ${where}`).toBe(true);
	for (const h of m.headings) {
		if (!h.button) continue;
		soft(h.seen, `its heading "${h.name}" a sort in sight, ${where}`).toBe(!phone);
	}
	if (phone) {
		soft(m.select?.seen, `its "Sort by" in sight, ${where}`).toBe(true);
		soft(
			Math.abs((m.select?.top ?? 0) - (m.fields?.top ?? 99)) < 12,
			`its "Sort by" and Fields on one line, ${where}`
		).toBe(true);
		if (m.sortRoom && form === 'grouped') {
			soft(
				m.sortRoom.room - MENULIST_INNER,
				`room in its "Sort by" for "${m.sortRoom.name}", ${where}`
			).toBeGreaterThanOrEqual(m.sortRoom.text);
		}
		// Sorted, the field it shows whole beside its direction button (S6 review TBL-4).
		if (m.sortRoom && form === 'flat') {
			soft(
				m.sortRoom.room - MENULIST_INNER,
				`room in its "Sort by" for "${m.sortRoom.chosen.name}" chosen, ${where}`
			).toBeGreaterThanOrEqual(m.sortRoom.chosen.text);
		}
	} else {
		soft(m.select?.seen ?? false, `its "Sort by" out of sight from 640 px, ${where}`).toBe(false);
	}
	soft(m.rows.length, `Running combinations' rows, ${where}`).toBeGreaterThan(0);
	for (const r of m.rows) {
		const what = `"${r.name}" in "${r.case}", ${where}`;
		soft(r.nameSeen, `${what}: its name in sight`).toBe(true);
		soft(r.nameWhole, `${what}: its name shown to its end`).toBe(true);
		soft(r.button, `${what}: a trace button in the shown case's rows only`).toBe(
			/\(shown\)/.test(r.case)
		);
		if (form === 'flat') {
			soft(r.caseCell?.seen, `${what}: its Case in sight`).toBe(true);
			soft(r.caseCell?.whole, `${what}: its Case shown to its end`).toBe(true);
			soft(r.caseCell?.before, `${what}: its Case's line header`).toBe(phone ? '"Case"' : 'none');
			if (phone && r.caseCell?.headerRoom) {
				soft(
					r.caseCell.headerRoom.room + 0.5,
					`${what}: its Case's line header whole before its words`
				).toBeGreaterThanOrEqual(r.caseCell.headerRoom.text);
			}
		}
		if (r.flags) {
			soft(r.flags.label, `${what}: its flag line labelled`).toBe('Flags');
			soft(r.flags.hidden, `${what}: its flag line named by its pump`).toEqual([
				`${r.name}, flags:`
			]);
			soft(r.flags.said.length, `${what}: its flags`).toBeGreaterThan(0);
			for (const said of r.flags.said) {
				soft(said.seen, `${what}: "${said.words.slice(0, 40)}" in sight`).toBe(true);
				soft(said.inWidth, `${what}: "${said.words.slice(0, 40)}" inside the box's width`).toBe(
					true
				);
			}
		}
	}
	soft(m.offLine, `Running combinations' values off their line, ${where}`).toEqual([]);
	soft(m.covers, `fills over Running combinations' right shadow, ${where}`).toEqual([]);
	return m;
}

// ---- S6a: the group table a ResultsTable (§9 S6a) ----------------------------------------------

/**
 * The group table as the page draws it (§5.3 Station, §9 S6a): its title, its box (a region named
 * by the title), its controls and its rows, each read against the box's visible rectangle.
 */
function readGroupTable() {
	const block = document.querySelector<HTMLElement>('[data-pumps-together] [data-group-table]');
	if (!block) return null;
	const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
	// In sight at a size of its own: not hidden, and inside no visually hidden box (sr-only's 1 px
	// box, at any breakpoint: a phone's table headings), which clips it whatever its own size.
	const seen = (el: Element | null) => {
		if (!el) return false;
		const r = el.getBoundingClientRect();
		for (let a: Element | null = el; a; a = a.parentElement) {
			const b = a.getBoundingClientRect();
			if (getComputedStyle(a).overflow === 'hidden' && (b.width <= 1 || b.height <= 1)) {
				return false;
			}
		}
		return (
			el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
			r.width > 1 &&
			r.height > 1
		);
	};
	const rect = (el: Element) => {
		const r = el.getBoundingClientRect();
		return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
	};
	const title = block.querySelector('p');
	// The table's box (a region only while it overflows since S7, §9 S7).
	const box = block.querySelector<HTMLElement>('table[role="table"]')?.parentElement;
	const table = box?.querySelector('table');
	const select = block.querySelector<HTMLSelectElement>('select[aria-label^="Sort by, The pumps"]');
	const fields = [...block.querySelectorAll('button')].find((b) =>
		squash(b.textContent).startsWith('Fields')
	);
	const flagged = [...block.querySelectorAll('label')].find((l) =>
		squash(l.textContent).startsWith('Flagged only')
	);
	const group = block.querySelector('[role="group"][aria-label^="Fields shown in"]');
	const containers: string[] = [];
	for (let e = group?.parentElement ?? null; e; e = e.parentElement) {
		const type = getComputedStyle(e).containerType;
		if (type !== 'normal') containers.push(`<${e.tagName.toLowerCase()}> ${type}`);
	}
	// A select's text box against its longest option (MENULIST_INNER is added by the caller).
	let sortRoom: { name: string; text: number; room: number } | null = null;
	if (select && seen(select)) {
		const css = getComputedStyle(select);
		const context = document.createElement('canvas').getContext('2d')!;
		context.font = `${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
		const longest = [...select.options].reduce(
			(widest, option) => {
				const width = context.measureText(option.text).width;
				return width > widest.width ? { name: option.text, width } : widest;
			},
			{ name: '', width: 0 }
		);
		sortRoom = {
			name: longest.name,
			text: Math.ceil(longest.width),
			room: Math.floor(
				select.clientWidth - parseFloat(css.paddingLeft) - parseFloat(css.paddingRight)
			)
		};
	}
	const headings = [...(table?.querySelectorAll('thead th') ?? [])];
	const rows = [...(table?.querySelectorAll('tbody > tr') ?? [])];
	return {
		title: title ? { id: title.id, text: squash(title.textContent), seen: seen(title) } : null,
		box: box
			? {
					labelledby: box.getAttribute('aria-labelledby'),
					tabindex: box.getAttribute('tabindex'),
					role: box.getAttribute('role'),
					// It overflows on an axis it scrolls (§9 S7: a Tab stop only then).
					overflows: (() => {
						const css = getComputedStyle(box);
						return (
							(/(auto|scroll)/.test(css.overflowX) && box.scrollWidth > box.clientWidth + 1) ||
							(/(auto|scroll)/.test(css.overflowY) && box.scrollHeight > box.clientHeight + 1)
						);
					})(),
					rect: rect(box),
					sideways: box.scrollWidth > box.clientWidth + 1,
					caption: squash(table?.querySelector('caption')?.textContent)
				}
			: null,
		list: !!table && getComputedStyle(table).display === 'block',
		// Each heading, whether it is a sort button, and whether its column shows a value in some
		// row: ResultsTable sorts a column only then (a column of "—" alone has no button).
		headingButtons: headings.map((h, k) => {
			const b = h.querySelector('button');
			const valued =
				k === 0 ||
				rows.some((r) => {
					const cell = r.querySelectorAll(':scope > td')[k - 1];
					return !!cell && squash(cell.textContent) !== '—';
				});
			return { name: squash(h.textContent), button: !!b, valued, seen: seen(b ?? h) };
		}),
		select: select ? { seen: seen(select), top: rect(select).top } : null,
		sortRoom,
		fields: fields ? { seen: seen(fields), top: rect(fields).top } : null,
		flagged: flagged ? { seen: seen(flagged), top: rect(flagged).top } : null,
		group: !!group,
		containers,
		titles: block.querySelectorAll('[title]').length,
		members: rows
			.filter((r) => r.querySelector('th[scope="row"]'))
			.map((r) => {
				const th = r.querySelector('th')!;
				const name = th.querySelector('span.min-w-0');
				return {
					name: squash(name?.textContent),
					seen: seen(name),
					whole: !!name && name.scrollWidth <= name.clientWidth + 1,
					button: !!th.querySelector('button'),
					// Where its words start, after its slot symbol's 1 rem column (§15 item 157).
					left: name ? name.getBoundingClientRect().left : null
				};
			}),
		lines: [...(table?.querySelectorAll('[data-row-notes]') ?? [])].map((line) => {
			const row = line.closest('tr')!.previousElementSibling;
			const whole = squash(line.textContent);
			return {
				id: line.getAttribute('data-row-notes'),
				label: line.getAttribute('data-label'),
				after: squash(row?.querySelector('th span.min-w-0')?.textContent),
				hidden: [...line.querySelectorAll('.sr-only')].map((e) => squash(e.textContent)),
				said: [...line.querySelectorAll('li')].map((li) => {
					const text = li.querySelector('[data-flag-text]');
					const words = squash(text?.textContent);
					return {
						words,
						seen: seen(text),
						rect: text ? rect(text) : null,
						once: !!words && whole.split(words).length === 2
					};
				})
			};
		})
	};
}

/**
 * The group table's part of S6a at the size shown, the card open (soft): a ResultsTable (§9 S6a)
 * with its title in sight naming its box (a region and a Tab stop) and its table; Fields in sight
 * at every size, its group under no container (§5.5); the heading buttons in sight from 640 px,
 * a list with "Sort by" in sight below it, sharing a line with Fields and showing its longest
 * field to its end (§15 item 17); each name in sight and shown to its end; each flag line
 * labelled Flags under its pump's row, named by its pump, each flag's sentence in sight, read once
 * and inside the box's visible width, with no FlagBadge (no tooltip, no hidden copy).
 */
async function groupTablePart(page: Page, where: string) {
	const soft = expect.configure({ soft: true });
	const m = await page.evaluate(readGroupTable);
	if (!m) {
		console.log(`${where}: no group table (the card closed or no member ticked)`);
		return;
	}
	const phone = (page.viewportSize()?.width ?? 1280) < 640;
	console.log(
		`${where}: the group table a ${m.list ? 'list' : 'table'}, ${m.members.length} pumps, ${m.lines.length} flag lines, ${Math.round((m.box?.rect.bottom ?? 0) - (m.box?.rect.top ?? 0))} px${m.sortRoom ? `, Sort by ${m.sortRoom.room} px for "${m.sortRoom.name}" (${m.sortRoom.text})` : ''}`
	);
	soft(m.title?.text ?? '', `the group table's title, ${where}`).toMatch(
		/^The pumps in the group(, .+)?$/
	);
	soft(m.title?.seen, `the group table's title in sight, ${where}`).toBe(true);
	// A region named by its title and a Tab stop while it overflows, neither when it fits (§9 S7).
	const stop = !!m.box?.overflows;
	soft(m.box?.labelledby, `the group table's box named by its title, ${where}`).toBe(
		stop ? m.title?.id : null
	);
	soft(m.box?.role, `the group table's box a region, ${where}`).toBe(stop ? 'region' : null);
	soft(m.box?.tabindex, `the group table's box a Tab stop, ${where}`).toBe(stop ? '0' : null);
	console.log(`${where}: the group table's box ${stop ? 'overflows: a Tab stop' : 'fits'}`);
	soft(m.box?.caption, `the group table named as its title, ${where}`).toBe(m.title?.text);
	soft(m.list, `the group table a list below 640 px only, ${where}`).toBe(phone);
	soft(m.fields?.seen, `Fields in sight, ${where}`).toBe(true);
	soft(m.group, `the Fields group drawn, ${where}`).toBe(true);
	soft(m.containers, `containers above the group table's Fields, ${where}`).toEqual([]);
	soft(m.titles, `a tooltip in the group table, ${where}`).toBe(0);
	soft(m.headingButtons.length, `the group table's headings, ${where}`).toBeGreaterThan(2);
	for (const h of m.headingButtons) {
		// A sort button over every column that shows a value (ResultsTable's sortableColumn).
		soft(h.button, `the heading "${h.name}" a sort button, ${where}`).toBe(h.valued);
		// From 640 px the headings sort; below it the list's "Sort by" does, the headings hidden.
		soft(h.seen, `the heading "${h.name}" in sight, ${where}`).toBe(!phone);
	}
	if (phone) {
		soft(m.select?.seen, `"Sort by" in sight, ${where}`).toBe(true);
		soft(
			Math.abs((m.select?.top ?? 0) - (m.fields?.top ?? 99)) < 12,
			`"Sort by" and Fields on one line, ${where}`
		).toBe(true);
		if (m.sortRoom) {
			soft(
				m.sortRoom.room - MENULIST_INNER,
				`room in "Sort by" for "${m.sortRoom.name}", ${where}`
			).toBeGreaterThanOrEqual(m.sortRoom.text);
		}
	} else {
		soft(m.select?.seen ?? false, `"Sort by" out of sight from 640 px, ${where}`).toBe(false);
	}
	if (m.flagged) soft(m.flagged.seen, `Flagged only in sight, ${where}`).toBe(true);
	for (const member of m.members) {
		soft(member.seen, `the name "${member.name}" in sight, ${where}`).toBe(true);
		soft(member.whole, `the name "${member.name}" shown to its end, ${where}`).toBe(true);
		soft(member.button, `the name "${member.name}" a trace button, ${where}`).toBe(true);
	}
	// Every name starts at one edge, whatever its slot symbol's width (§15 item 157; S6 review
	// MUT-04: the symbols' 1 rem column taken away failed nothing).
	const lefts = m.members.map((member) => member.left ?? 0);
	soft(
		Math.max(...lefts) - Math.min(...lefts),
		`the group table's names start at one edge, ${where}`
	).toBeLessThanOrEqual(0.5);
	for (const line of m.lines) {
		const what = `the flag line of ${line.id}, ${where}`;
		soft(line.label, `${what}: labelled`).toBe('Flags');
		soft(line.hidden, `${what}: named by its pump`).toEqual([`${line.after}, flags:`]);
		soft(line.said.length, `${what}: its flags`).toBeGreaterThan(0);
		for (const flag of line.said) {
			const said = `${what}: "${flag.words.slice(0, 40)}"`;
			soft(flag.seen, `${said} in sight`).toBe(true);
			soft(flag.once, `${said} read once`).toBe(true);
			if (flag.rect && m.box) {
				soft(
					flag.rect.left >= m.box.rect.left - 0.5 && flag.rect.right <= m.box.rect.right + 0.5,
					`${said} inside the box's visible width`
				).toBe(true);
			}
		}
	}
	if (phone) soft(m.box?.sideways, `the group table's box scrolls sideways, ${where}`).toBe(false);
}

// ---- S7: data without scroll traps (§9 S7) -----------------------------------------------------

/**
 * §5.7 row 11: the scroll regions that are Tab stops in the lineups, every disclosure and data
 * table open, at each size: the boxes that overflow, as measured after S7 (13 on main). The rule
 * holds in every view at every size: every focusable box overflows, and every box of the data
 * regions and the card's tables that overflows is one.
 */
const SCROLL_STOPS: Readonly<Record<string, number>> = {
	// The group table's, the group curve's and Running combinations' boxes.
	'1280x800': 3,
	// The group curve's box alone: the group table and Running combinations are lists there.
	'390x844': 1,
	'320x640': 1
};

/**
 * The tab's scroll boxes (§9 S7): every element made a Tab stop that is no control of its own,
 * and every box S7 measures (the two data regions' tables', the group table's, Running
 * combinations' and the extremes'), each with what it holds, whether it is drawn, whether it
 * overflows on an axis it scrolls, and what it is: a Tab stop, a region, its name.
 */
function readScrollBoxes() {
	const pane = document.querySelector('section[aria-label="Results"]')!;
	const tab = [...pane.querySelectorAll('[role="tabpanel"]')].find(
		(p) => !(p as HTMLElement).hidden
	)!;
	const squash = (t: string | null | undefined) => (t ?? '').replace(/\s+/g, ' ').trim();
	const overflows = (el: Element) => {
		const css = getComputedStyle(el);
		return (
			(/(auto|scroll)/.test(css.overflowX) && el.scrollWidth > el.clientWidth + 1) ||
			(/(auto|scroll)/.test(css.overflowY) && el.scrollHeight > el.clientHeight + 1)
		);
	};
	const named = (el: Element) =>
		squash(
			(el.getAttribute('aria-labelledby') ?? '')
				.split(/\s+/)
				.map((id) => document.getElementById(id)?.textContent ?? '')
				.join(' ')
		);
	const read = (box: HTMLElement) => {
		const r = box.getBoundingClientRect();
		return {
			holds: squash(box.querySelector('caption')?.textContent) || box.tagName.toLowerCase(),
			drawn: box.checkVisibility() && r.width > 1 && r.height > 1,
			overflows: overflows(box),
			stop: box.getAttribute('tabindex') === '0',
			role: box.getAttribute('role'),
			name: named(box)
		};
	};
	const NATIVE = 'a[href],button,input,select,textarea,summary,[contenteditable="true"]';
	const focusable = [...tab.querySelectorAll<HTMLElement>('[tabindex="0"]')]
		.filter((el) => !el.matches(NATIVE))
		.map(read);
	const measured = [
		...tab.querySelectorAll('[data-pump-data] table, [data-group-data] table'),
		...tab.querySelectorAll(
			'[data-group-table] table[role="table"], [data-running-combinations] table[role="table"], [data-extremes] > table'
		)
	].map((t) => read(t.parentElement!));
	// A data region or a card's table drawn: S7 has boxes to measure (none in the one-off's
	// defaults, the card closed and no data table shown).
	const tables = !!tab.querySelector(
		'[data-pump-data], [data-group-data], [data-group-table], [data-running-combinations]'
	);
	return { focusable, measured, tables };
}

/**
 * S7 at the size shown (soft): every focusable box overflows and is a region named by what it
 * holds; every box S7 measures is a Tab stop exactly while it overflows (none while folded away);
 * in the lineups, everything open, the count of scroll-region Tab stops is §5.7 row 11's.
 */
async function scrollBoxesPart(page: Page, view: string, where: string) {
	const soft = expect.configure({ soft: true });
	const m = await page.evaluate(readScrollBoxes);
	console.log(
		`${where}: ${m.focusable.length} scroll-region Tab stops (${m.focusable.map((b) => b.holds).join('; ')}); ${m.measured.filter((b) => b.drawn).length} measured boxes drawn, ${m.measured.filter((b) => b.overflows).length} overflowing`
	);
	for (const box of m.focusable) {
		soft(box.overflows, `a focusable box overflows: "${box.holds}", ${where}`).toBe(true);
		soft(box.role, `a focusable box a region: "${box.holds}", ${where}`).toBe('region');
		soft(box.name.length, `a focusable box named: "${box.holds}", ${where}`).toBeGreaterThan(0);
	}
	if (m.tables) soft(m.measured.length, `boxes S7 measures, ${where}`).toBeGreaterThan(0);
	for (const box of m.measured) {
		const stop = box.drawn && box.overflows;
		soft(box.stop, `"${box.holds}" a Tab stop only while it overflows, ${where}`).toBe(stop);
		soft(box.role, `"${box.holds}" a region only while it overflows, ${where}`).toBe(
			stop ? 'region' : null
		);
		if (stop && box.holds !== 'div') {
			// Named by what it holds: the caption, or the group table's and Running combinations'
			// titles, the same words.
			soft(box.name, `"${box.holds}" named by what it holds, ${where}`).toBe(box.holds);
		}
	}
	const size = sizeOf(page);
	if (view === '2-lineups') {
		soft(m.focusable.length, `scroll-region Tab stops, lineups everything open, ${where}`).toBe(
			SCROLL_STOPS[size]
		);
	}
}

/**
 * Check and measure the view at the project's size and, on the phone, at 320×640 too (reflow at
 * 400 % zoom; pump-lineups.e2e.ts resizes the same way). Then axe with every disclosure open at
 * each size, once the measuring is done, so the view is measured as the test set it up: on the
 * phone at 320×640 first, then back at 390×844.
 */
async function atEachSize(page: Page, info: TestInfo, view: string, extra: object) {
	const size = sizeOf(page);
	await noSidewaysScroll(page, `${view} at ${size}`);
	await pageHolds(page, `${view} at ${size}`);
	await pumpChartPart(page, `${view} at ${size}`);
	const data = await measure(page, info, `${view}-${size}`, extra);
	await cardPart(page, view, `${view} at ${size}`, data);
	await groupTablePart(page, `${view} at ${size}`);
	await navPart(page, `${view} at ${size}`);
	await addCasesPart(page, view, `${view} at ${size}`);
	await extremesPart(page, view, `${view} at ${size}`);
	await combinationsPart(page, view, `${view} at ${size}`, data);
	await scrollBoxesPart(page, view, `${view} at ${size}`);
	if (info.project.name !== 'mobile') {
		await axeClean(page, `${view} at ${size}`);
		await scrollBoxesPart(page, '', `${view} at ${size}, every disclosure open`);
		await pageHolds(page, `${view} at ${size}, every disclosure open`);
		return;
	}
	const viewport = page.viewportSize()!;
	await page.setViewportSize({ width: 320, height: 640 });
	await settle(page, 1000);
	await noSidewaysScroll(page, `${view} at 320x640`);
	await pageHolds(page, `${view} at 320x640`);
	await pumpChartPart(page, `${view} at 320x640`);
	const narrow = await measure(page, info, `${view}-320x640`, extra);
	await cardPart(page, view, `${view} at 320x640`, narrow);
	await groupTablePart(page, `${view} at 320x640`);
	await navPart(page, `${view} at 320x640`);
	await addCasesPart(page, view, `${view} at 320x640`);
	await extremesPart(page, view, `${view} at 320x640`);
	await combinationsPart(page, view, `${view} at 320x640`, narrow);
	await scrollBoxesPart(page, view, `${view} at 320x640`);
	await axeClean(page, `${view} at 320x640`);
	await scrollBoxesPart(page, '', `${view} at 320x640, every disclosure open`);
	await pageHolds(page, `${view} at 320x640, every disclosure open`);
	await page.setViewportSize(viewport);
	await settle(page, 1000);
	await axeClean(page, `${view} at ${size}`);
	await scrollBoxesPart(page, '', `${view} at ${size}, every disclosure open`);
	await pageHolds(page, `${view} at ${size}, every disclosure open`);
}

// ---- S0: no sideways scroll; S1: the pump chart's budget and outline -----------------------------

test('the condenser example after Add cases, the card open: the Results pane’s scroller does not scroll sideways; the pump chart holds its budget; axe clean, every disclosure open', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	const extra = await condenser(page);
	await atEachSize(page, info, '3-condenser', extra);
});

test('one-off, the Pumps tab’s defaults: nothing scrolls sideways; the pump chart holds its budget; axe clean, every disclosure open', async ({
	page
}, info) => {
	test.setTimeout(240_000);
	const extra = await oneOff(page);
	await atEachSize(page, info, '1-one-off', extra);

	// S8 (§9 S8 Slots, §6.2): while the other cases' system curves are off, a case in which Pump
	// PA is off takes no slot: no box, and the line under the list names it, on screen at each
	// size. The fixture's scenarios set PA off in "Pump PA off" and "Both pumps off"
	// (pump-groups-input.json).
	const figure = await pumpFigure(page);
	const cases = figure.getByRole('group', { name: 'Cases on the chart' });
	const offLine = cases.locator('[data-pump-off-cases]');
	await expect(offLine).toHaveText(
		'Off in this case (no operating point): Pump PA off; Both pumps off.'
	);
	expect(await seenLine(offLine), `the off line on screen at ${sizeOf(page)}`).toBe(true);
	for (const name of ['Pump PA off', 'Both pumps off']) {
		await expect(cases.getByRole('checkbox', { name, exact: true })).toHaveCount(0);
	}
	// S1 (§5.3, §10), while the other cases' system curves are on (S8): a case in which Pump PA
	// is off has its box again, and says so in its description, beside the box; the others do not.
	await figure.getByRole('checkbox', { name: "Also show the other cases' system curves" }).check();
	await expect(offLine).toHaveCount(0);
	const NOTE = 'off in this case: no operating point';
	for (const name of ['Pump PA off', 'Both pumps off']) {
		const box = cases.getByRole('checkbox', { name, exact: true });
		await expect(box).toHaveAccessibleDescription(new RegExp(`\\(${NOTE}\\)`));
	}
	for (const name of ['Pump PB off', 'Delivery tank 5 m higher']) {
		const box = cases.getByRole('checkbox', { name, exact: true });
		await expect(box).toHaveAccessibleDescription('');
	}
	await expect(cases.getByText(`(${NOTE})`, { exact: true })).toHaveCount(2);
	await expect(cases.getByText(`(${NOTE})`, { exact: true }).first()).toBeVisible();
	// Its own box, not sr-only's 1 px one, which toBeVisible accepts (§5.3).
	for (const note of await cases.getByText(`(${NOTE})`, { exact: true }).all()) {
		expect(await seenBox(note), `the off note's box at ${sizeOf(page)}`).toBe(true);
	}
	// S8 review FID-1: the off notes exist only while the curves are on (§9 S8 Slots), so the
	// per-size check pumpChartPart gave them by default before S8 follows them there: each note in
	// sight at every size atEachSize visits, 320×640 too on the phone (§10: a test reading a moved
	// element gains the step that reaches it), and axe once over the off boxes' descriptions.
	await settle(page);
	await axeClean(page, `1-one-off, the other cases' system curves on, at ${sizeOf(page)}`);
	if (info.project.name === 'mobile') {
		const viewport = page.viewportSize()!;
		await page.setViewportSize({ width: 320, height: 640 });
		await settle(page, 1000);
		const notes = await cases.getByText(`(${NOTE})`, { exact: true }).all();
		expect(notes, 'the off notes at 320x640').toHaveLength(2);
		for (const note of notes) {
			expect(await seenBox(note), `the off note's box at ${sizeOf(page)}`).toBe(true);
		}
		await page.setViewportSize(viewport);
		await settle(page, 1000);
	}
});

test('lineups, every disclosure and data table open: nothing scrolls sideways; the pump chart holds its budget; axe clean', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	const extra = await lineups(page);
	await atEachSize(page, info, '2-lineups', extra);

	// S1 (§5.1, §5.3): the data region opens after the notes and before the other cases, the
	// operating point at its top and the case shown's tables first.
	const figure = await pumpFigure(page);
	const order = await figure.evaluate((f) => {
		const squash = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
		const region = f.querySelector('[data-pump-data]');
		const notes = f.querySelector('[data-pump-notes]');
		const others = f.querySelector('[data-pump-others]');
		const follows = (a: Element | null, b: Element | null) =>
			!!a && !!b && !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
		return {
			afterNotes: follows(notes, region),
			beforeOthers: follows(region, others),
			first: squash(region?.firstElementChild?.textContent),
			tables: [...(region?.querySelectorAll('table') ?? [])].map((t) =>
				squash(t.querySelector('caption')?.textContent)
			)
		};
	});
	expect(order.afterNotes).toBe(true);
	expect(order.beforeOthers).toBe(true);
	expect(order.first).toMatch(/^Operating point: [\d.]+ L\/s at [\d.]+ m/);
	expect(order.tables[0]).toBe('Operating points by case');
	expect(order.tables[1]).toMatch(/^Pump curve at /);
	expect(order.tables[2]).toBe('System curve');
	// The case shown first in "Operating points by case", "Speed (%)" with bare numbers.
	const byCase = figure.getByRole('table', { name: 'Operating points by case' });
	await expect(byCase.getByRole('columnheader')).toHaveText([
		'Case',
		'Flow (L/s)',
		'Head (m)',
		'Speed (%)',
		'State'
	]);
	await expect(byCase.getByRole('rowheader').first()).toHaveText(/\(shown\)$/);
	for (const cell of await byCase.getByRole('row').nth(1).getByRole('cell').all()) {
		await expect(cell).not.toContainText('%');
	}

	// S8 (§9 S8, §10 One choice of cases; the owner's answer 2): a case unticked under "Cases on
	// the chart" is unticked under "Cases on this chart", every other ring staying; the pump
	// chart's list kept over a pump switch; ticked again under the card's list, on both.
	const tab = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const pumpCases = figure.getByRole('group', { name: 'Cases on the chart' });
	const cardCases = card.getByRole('group', { name: 'Cases on this chart' });
	const TWO = '2 of 4 running (Pump P3, Pump P4 off)';
	const rings = () =>
		card
			.locator('[data-group-rings] li .font-medium')
			.evaluateAll((all) => all.map((n) => n.textContent));
	const ringsBefore = await rings();
	expect(ringsBefore).toContain(TWO);
	await expect(pumpCases.getByRole('checkbox', { name: TWO, exact: true })).toBeChecked();
	await pumpCases.getByRole('checkbox', { name: TWO, exact: true }).uncheck();
	await expect(cardCases.getByRole('checkbox', { name: TWO, exact: true })).not.toBeChecked();
	await expect.poll(rings).toEqual(ringsBefore.filter((name) => name !== TWO));
	// Pump P3 is off in that case: on its chart the case takes no slot and is named.
	const select = tab.getByRole('combobox', { name: 'Pump chart' });
	await select.selectOption({ label: 'Pump P3' });
	await expect(tab.getByRole('figure', { name: /^Pump and system curves: Pump P3/ })).toBeVisible();
	await expect(pumpCases.locator('[data-pump-off-cases]')).toContainText(TWO);
	// Pump P2 runs in it: its box is there, still unticked.
	await select.selectOption({ label: 'Pump P2' });
	await expect(tab.getByRole('figure', { name: /^Pump and system curves: Pump P2/ })).toBeVisible();
	await expect(pumpCases.getByRole('checkbox', { name: TWO, exact: true })).not.toBeChecked();
	// Ticked again under "Cases on this chart": on both.
	await cardCases.getByRole('checkbox', { name: TWO, exact: true }).check();
	await expect(pumpCases.getByRole('checkbox', { name: TWO, exact: true })).toBeChecked();
	await expect.poll(rings).toEqual(ringsBefore);
});

// ---- S1 review fixes: the live line, the failed request's mark, the lasting reason, the notes ---

/**
 * Logs each live line's words when it is inserted and each time they change, with the frame it
 * happened in (a counter its own animation-frame callback steps, registered before any of the
 * page's), so a test can tell a line drawn empty before it spoke from one inserted speaking.
 */
function liveRecorder() {
	const w = window as unknown as {
		__frame: number;
		__live: { id: string; kind: 'insert' | 'change'; text: string; frame: number }[];
	};
	w.__frame = 0;
	w.__live = [];
	const step = () => {
		w.__frame++;
		requestAnimationFrame(step);
	};
	requestAnimationFrame(step);
	const words = new WeakMap<Element, string>();
	new MutationObserver(() => {
		for (const e of document.querySelectorAll('[aria-live]')) {
			const text = (e.textContent ?? '').replace(/\s+/g, ' ').trim();
			const before = words.get(e);
			if (before === text) continue;
			words.set(e, text);
			w.__live.push({
				id: e.id,
				kind: before === undefined ? 'insert' : 'change',
				text,
				frame: w.__frame
			});
		}
	}).observe(document, { subtree: true, childList: true, characterData: true });
}

/** The recorder's log for one live line, in order. */
async function liveLog(page: Page, id: string) {
	const log = await page.evaluate(() => (window as unknown as { __live: { id: string }[] }).__live);
	return (log as { id: string; kind: string; text: string; frame: number }[]).filter(
		(e) => e.id === id
	);
}

const COMPUTING = 'Computing the system curve for this solve…';

/**
 * §7 Live regions (F17): the line's first progress message is announced, so the line is drawn
 * empty before it speaks, and never inserted already speaking: the frame after the one that first
 * draws it, at the soonest. Both ways a curve starts with a new chart: the tab's opening and a
 * pump chosen.
 */
async function drawnEmptyThenSpoke(page: Page, figure: Locator, where: string) {
	const id = (await figure.locator('[data-pump-strip] [aria-live]').getAttribute('id'))!;
	const log = await liveLog(page, id);
	expect(log[0], `the line inserted, ${where}`).toMatchObject({ kind: 'insert', text: '' });
	const spoke = log.find((e) => e.text === COMPUTING);
	expect(spoke, `the line said "${COMPUTING}", ${where}`).toBeDefined();
	expect(spoke!.kind, `as a change, ${where}`).toBe('change');
	expect(spoke!.frame - log[0]!.frame, `frames from insert to words, ${where}`).toBeGreaterThan(1);
	return id;
}

test('the pump chart’s live line is drawn empty before it speaks: on the tab’s opening and on a pump chosen (§7, F17)', async ({
	page
}) => {
	test.setTimeout(120_000);
	await page.addInitScript(liveRecorder);
	await open(page, projectOf('one-off'));
	await solveConverged(page);
	// Each curve held a moment, so its progress has time to be said.
	await page.route('**/api/v1/system-curve', async (route) => {
		await new Promise((resolve) => setTimeout(resolve, 600));
		await route.continue();
	});
	const tab = await pumpsTab(page);
	const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
	const method = figure.locator('[data-pump-method]');
	await expect(method).toBeVisible({ timeout: 60_000 });
	const first = await drawnEmptyThenSpoke(page, figure, 'the Pumps tab opened');

	const select = tab.getByRole('combobox', { name: 'Pump chart' });
	const shown = await select.inputValue();
	const values = await select
		.locator('option')
		.evaluateAll((all) => all.map((o) => (o as HTMLOptionElement).value));
	await select.selectOption(values.find((v) => v !== shown)!);
	await expect(method).toBeVisible({ timeout: 60_000 });
	const second = await drawnEmptyThenSpoke(page, figure, 'another pump chosen');
	expect(second, 'a new chart, a new line').not.toBe(first);
});

test('the card’s live lines are drawn empty before they speak: the group curve’s at Station’s head and the group system curve’s in the strip, the card opened (§7, F17; §9 S3)', async ({
	page
}) => {
	test.setTimeout(120_000);
	await page.addInitScript(liveRecorder);
	await open(page, projectOf('parallel-crane'));
	await solveConverged(page);
	// Each curve held a moment, so its progress has time to be said.
	await page.route('**/api/v1/pump-group-curve', async (route) => {
		await new Promise((resolve) => setTimeout(resolve, 600));
		await route.continue();
	});
	const tab = await pumpsTab(page);
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	await card.getByRole('button', { name: /^Pumps together/ }).click();
	const figure = card.getByRole('figure');
	// Both curves answered: the chart names the group system curve shown, and nothing is busy.
	await expect(figure.getByRole('img')).toHaveAccessibleName(/group system curve shown\.$/, {
		timeout: 60_000
	});
	await expect(figure.getByRole('img')).toHaveAttribute('aria-busy', 'false');
	for (const [hook, words] of [
		['[data-group-station] [data-group-curve-state]', 'Computing the group curve for this solve…'],
		[
			'[data-group-strip] [data-group-system-state]',
			'Computing the group system curve for this solve…'
		]
	] as const) {
		const line = card.locator(hook);
		// Polite and atomic, never role=status, with no busy ancestor, holding no button.
		await expect(line).toHaveAttribute('aria-live', 'polite');
		await expect(line).toHaveAttribute('aria-atomic', 'true');
		await expect(line).not.toHaveAttribute('role', /./);
		expect(
			await line.evaluate((el) => !!el.parentElement?.closest('[aria-busy="true"]')),
			`no busy ancestor, ${hook}`
		).toBe(false);
		await expect(line.locator('button')).toHaveCount(0);
		const id = (await line.getAttribute('id'))!;
		const log = await liveLog(page, id);
		expect(log[0], `the line inserted, ${hook}`).toMatchObject({ kind: 'insert', text: '' });
		const spoke = log.find((e) => e.text === words);
		expect(spoke, `the line said "${words}"`).toBeDefined();
		expect(spoke!.kind, `as a change, ${hook}`).toBe('change');
		expect(spoke!.frame - log[0]!.frame, `frames from insert to words, ${hook}`).toBeGreaterThan(1);
		// Answered: still there, saying nothing.
		await expect(line).toHaveText('');
	}
	// A pane-wide status query still finds the Results header's alone (§5.3 markup rules).
	await expect(resultsPane(page).getByRole('status')).toHaveCount(1);
});

test('the other cases’ live line under their h5 is drawn empty before it speaks, says their progress, and is empty again once they are drawn (§7, F17; §9 S3)', async ({
	page
}) => {
	test.setTimeout(240_000);
	await page.addInitScript(liveRecorder);
	await oneOff(page);
	const tab = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
	const card = await openCard(page, tab);
	// Each other case's request held a moment, so its progress has time to be said.
	await page.route('**/api/v1/pump-group-curve', async (route) => {
		const body = route.request().postDataJSON() as { scenarioId?: string | null };
		if (body?.scenarioId) await new Promise((resolve) => setTimeout(resolve, 600));
		await route.continue();
	});
	const section = card.locator('[data-group-others]');
	await expect(
		section.getByRole('heading', { name: 'Other cases on the group chart', level: 5 })
	).toBeVisible();
	const line = section.locator('[data-group-others-state]');
	await expect(line).toHaveText('');
	await section
		.getByRole('checkbox', { name: "Also show the other cases' station duties" })
		.check();
	await expect(line).toHaveText(/^Computing the other cases' station duties: 1 of 4…$/, {
		timeout: 60_000
	});
	await expect(
		section.getByRole('button', { name: "Cancel the other cases' station duties" })
	).toBeVisible();
	await expect(line).toHaveText('', { timeout: 120_000 });
	// Polite and atomic, never role=status, with no busy ancestor, holding no button.
	await expect(line).toHaveAttribute('aria-live', 'polite');
	await expect(line).toHaveAttribute('aria-atomic', 'true');
	await expect(line).not.toHaveAttribute('role', /./);
	await expect(line.locator('button')).toHaveCount(0);
	expect(
		await line.evaluate((el) => !!el.parentElement?.closest('[aria-busy="true"]')),
		'no busy ancestor'
	).toBe(false);
	const log = await liveLog(page, (await line.getAttribute('id'))!);
	expect(log[0], 'the line inserted').toMatchObject({ kind: 'insert', text: '' });
	const spoke = log.find((e) => e.text.startsWith("Computing the other cases' station duties"));
	expect(spoke, 'the line said its progress').toBeDefined();
	expect(spoke!.kind, 'as a change').toBe('change');
	expect(spoke!.frame - log[0]!.frame, 'frames from insert to words').toBeGreaterThan(1);
	// The rings drawn: the ring list, one line per ring, and "How to read the rings" closed.
	const rings = section.getByRole('list', {
		name: 'Other cases on the chart (slate rings, numbered):'
	});
	await expect(rings.getByRole('listitem')).toHaveCount(4);
	await expect(section.locator('[data-group-rings-how]')).not.toHaveAttribute('open', /.*/);
	// A pane-wide status query still finds the Results header's alone (§5.3 markup rules).
	await expect(resultsPane(page).getByRole('status')).toHaveCount(1);
});

/** The pump example with every note that qualifies a reading (made-up curve data; the API's). */
function notedTransfer(): Project {
	const project = pumpTransferExample();
	const curve = project.pumpLibrary[0]!;
	// The head rises from 26 m at shutoff to 28 m at 10 L/s.
	curve.points[0]!.head = 26;
	// NPSHr climbs to 14 m at 30 L/s, past NPSHa (about 12.4 m there along the system curve).
	curve.npshrCurve = [
		{ flow: 0.005, npshr: 1.5 },
		{ flow: 0.015, npshr: 2.5 },
		{ flow: 0.03, npshr: 14 }
	];
	// A flow control set above the duty: the system curve has no head past its 33 L/s.
	const valve = project.components[2]!;
	project.components[2] = {
		type: 'valve',
		valveType: 'fcv',
		id: valve.id,
		name: 'Flow limiter',
		elevation: valve.elevation,
		status: 'active',
		setpoint: 0.033,
		ports: valve.ports
	} as Project['components'][number];
	return project;
}

test('every note that qualifies a reading is on screen at each size: the rising head, NPSHa below NPSHr, the points without a head (§10 Words on screen)', async ({
	page
}, info) => {
	test.setTimeout(120_000);
	await open(page, notedTransfer());
	await solveConverged(page);
	const tab = await pumpsTab(page);
	const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
	await expect(figure.locator('[data-pump-method]')).toBeVisible({ timeout: 60_000 });
	const notes = [
		figure.locator('[data-pump-notes] p').filter({ hasText: /^The head rises with flow/ }),
		figure.locator('[data-pump-notes] p').filter({ hasText: /^NPSHa falls below NPSHr at about/ }),
		figure.locator('[data-pump-strip] p').filter({ hasText: /system-curve points have no head/ })
	];
	const sizes = info.project.name === 'mobile' ? [null, { width: 320, height: 640 }] : [null];
	for (const size of sizes) {
		if (size) await page.setViewportSize(size);
		for (const note of notes) {
			await expect(note).toHaveCount(1);
			expect(await seenBox(note), `${await note.innerText()} at ${sizeOf(page)}`).toBe(true);
		}
	}
});

test('a failed system curve’s mark is set at its first line, however its sentence wraps (§5.2)', async ({
	page
}, info) => {
	test.setTimeout(120_000);
	await page.route('**/api/v1/system-curve', (route) =>
		route.fulfill({
			status: 500,
			contentType: 'application/json',
			body: JSON.stringify({ error: { code: 'INTERNAL', message: 'Made-up failure.' } })
		})
	);
	await open(page, pumpTransferExample());
	await solveConverged(page);
	const tab = await pumpsTab(page);
	const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
	await expect(figure.getByRole('button', { name: 'Try again' })).toBeVisible({ timeout: 60_000 });
	const line = figure.locator('[data-pump-strip] [aria-live]');
	await expect(line).toHaveText(/^The system curve could not be computed: /);
	const sizes = info.project.name === 'mobile' ? [null, { width: 320, height: 640 }] : [null];
	for (const size of sizes) {
		if (size) await page.setViewportSize(size);
		const m = await line.evaluate((el) => {
			const mark = el.querySelector('svg')!.getBoundingClientRect();
			const words = [...el.childNodes].find((n) => n.nodeType === 3 && n.textContent!.trim())!;
			const range = document.createRange();
			range.selectNodeContents(words);
			const lines = [...range.getClientRects()].filter((r) => r.width > 0);
			const top = Math.min(...lines.map((r) => r.top));
			const first = lines.find((r) => r.top < top + 1)!;
			return {
				lines: new Set(lines.map((r) => Math.round(r.top))).size,
				mark: mark.top + mark.height / 2,
				first: first.top + first.height / 2
			};
		});
		const where = sizeOf(page);
		if (info.project.name === 'mobile') {
			expect(m.lines, `the sentence wraps at ${where}`).toBeGreaterThan(1);
		}
		expect(
			Math.abs(m.mark - m.first),
			`the mark's middle from its first line's, ${where}`
		).toBeLessThanOrEqual(2);
	}
});

test('a lasting image reason sits with Download image, beside it or under it, never under Show data table (§5.3 Actions, §5.5)', async ({
	page
}, info) => {
	test.setTimeout(120_000);
	await open(page, pumpTransferExample());
	await solveConverged(page);
	let tab = await pumpsTab(page);
	await expect(tab.getByRole('figure').getByRole('img')).toHaveAccessibleName(
		/ and system curve; operating point /,
		{ timeout: 60_000 }
	);
	// The latest solve did not converge: no image is made of its values, a lasting reason.
	await page.route('**/api/v1/solve', async (route) => {
		const response = await route.fetch();
		const body = await response.json();
		body.solvedState.converged = false;
		await route.fulfill({ response, json: body });
	});
	await solve(page);
	tab = await pumpsTab(page);
	const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
	const download = figure.getByRole('button', { name: /^Download image/ });
	await expect(download).toHaveAttribute('aria-disabled', 'true');
	const reason = page.locator(`[id="${await download.getAttribute('aria-describedby')}"]`);
	await expect(reason).toHaveText(/no image is made/);
	const show = figure.getByRole('button', { name: 'Show data table of the pump chart' });
	const sizes = info.project.name === 'mobile' ? [null, { width: 320, height: 640 }] : [null];
	for (const size of sizes) {
		if (size) await page.setViewportSize(size);
		const where = sizeOf(page);
		expect(await seenBox(reason), `the reason shown, ${where}`).toBe(true);
		const [r, d, s] = await Promise.all([reason, download, show].map((l) => l.boundingBox()));
		const beside = r!.x >= d!.x + d!.width - 1 && r!.y < d!.y + d!.height;
		const under = r!.y >= d!.y + d!.height - 1 && Math.abs(r!.x - d!.x) <= 1;
		expect(beside || under, `the reason beside or under Download image, ${where}`).toBe(true);
		// Under Show data table only where Download image itself is (both at the row's start).
		if (Math.abs(r!.x - s!.x) <= 1) {
			expect(
				Math.abs(d!.x - s!.x),
				`Download image dropped under Show, ${where}`
			).toBeLessThanOrEqual(1);
		}
	}
});

// ---- S2: the section nav where it stays static, and its Tab stop clamped ----------------------

test('the section nav stays static where it would cover too much (844×390, and 320×256 under short:); its stop is clamped to the buttons drawn (§5.4, §5.7)', async ({
	page
}) => {
	test.setTimeout(240_000);
	await oneOff(page);
	const tab = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
	const card = await openCard(page, tab);
	const toolbar = tab
		.getByRole('navigation', { name: 'Pumps view sections' })
		.getByRole('toolbar', { name: 'Go to' });
	const hash = await page.evaluate(() => location.hash);
	await page.emulateMedia({ reducedMotion: 'reduce' });

	// The pinned nav never takes a press meant for the header's Scenarios menu, which opens over
	// the pane: each of the menu's controls is what a press at its centre reaches.
	await scrollPane(page, { to: 0 });
	const top = await page.evaluate(readNav);
	await scrollPane(page, { by: top.canvasBottom - top.scrollerTop + 200 });
	expect((await page.evaluate(readNav)).pinned, 'the nav pinned under the menu').toBe(true);
	const menu = await openCases(page);
	const reached = await menu.evaluate((group) =>
		[...group.querySelectorAll<HTMLElement>('button, select')].map((control) => {
			const r = control.getBoundingClientRect();
			const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
			return {
				name: (control.textContent ?? '').trim().slice(0, 30),
				reached: control.contains(hit)
			};
		})
	);
	expect(reached.length, 'the menu’s controls').toBeGreaterThan(1);
	expect(reached.filter((c) => !c.reached)).toEqual([]);
	await page.keyboard.press('Escape');
	await expect(menu).toBeHidden();

	// A landscape phone (a 212 px pane, measured) and a laptop at 400 % zoom, where the workspace
	// scrolls as one page: the nav would take more than 15 %, so it never pins (§5.4 Place).
	const viewport = page.viewportSize()!;
	for (const [width, height] of [
		[844, 390],
		[320, 256]
	] as const) {
		await page.setViewportSize({ width, height });
		await settle(page, 1000);
		await noSidewaysScroll(page, `one-off at ${width}x${height}`);
		await scrollPane(page, { to: 0 });
		let state = await page.evaluate(readNav);
		await scrollPane(page, { by: state.canvasBottom - state.scrollerTop + 200 });
		// Under short: the page scrolls, not the pane: the canvas goes out of the viewport.
		await page.evaluate(() => {
			const fig = [...document.querySelectorAll('figure')].find((f) =>
				(f.querySelector(':scope > figcaption')?.textContent ?? '')
					.trim()
					.startsWith('Pump and system curves')
			)!;
			fig.closest('[data-pump-chart]')!.nextElementSibling?.scrollIntoView({ block: 'start' });
		});
		await page.waitForTimeout(300);
		state = await page.evaluate(readNav);
		console.log(
			`one-off at ${width}x${height}: the nav ${Math.round(state.navHeight)} px in a ${state.clientHeight} px pane, pinned ${state.pinned}`
		);
		expect.soft(state.pinned, `the nav at ${width}x${height}`).toBe(false);
		expect.soft(state.position, `the nav at ${width}x${height}`).toBe('static');
		expect
			.soft(state.scrollPadding, `the pane's scroll padding at ${width}x${height}`)
			.toBe('auto');
		// A press still lands on its target, uncovered (nothing is pinned over it).
		await toolbar.getByRole('button', { name: /^Group chart/ }).press('Enter');
		await expect(card.getByRole('heading', { name: 'Group chart', exact: true })).toBeFocused();
		const top = await card
			.getByRole('heading', { name: 'Group chart', exact: true })
			.evaluate((h) => h.getBoundingClientRect().top);
		expect.soft(top, `the target in the viewport at ${width}x${height}`).toBeGreaterThanOrEqual(0);
		expect
			.soft(await page.evaluate(() => location.hash), `the link at ${width}x${height}`)
			.toBe(hash);
		// From the card's foot, "Back to the sections" gives the nav's current button the focus,
		// in sight: the static nav is brought back into view (§5.4 The way back; S2 review TS-02).
		// Then an arrow key, the nav scrolled out again: the same (S2 review NAV-3).
		const back = card.getByRole('button', { name: 'Back to the sections' });
		for (const key of ['Enter', 'ArrowRight']) {
			if (key === 'Enter') {
				await back.focus();
			} else {
				// The nav 40 px out of sight: above the pane, or under short: above the viewport.
				const before = await page.evaluate(readNav);
				if (height > 320) {
					await scrollPane(page, { by: before.navBottom - before.scrollerTop + 40 });
				} else {
					await page.evaluate((by) => window.scrollBy(0, by), before.navBottom + 40);
					await page.waitForTimeout(150);
				}
				const out = await page.evaluate(readNav);
				expect
					.soft(out.navBottom, `the nav scrolled out of sight at ${width}x${height}`)
					.toBeLessThan(height > 320 ? out.scrollerTop : 0);
			}
			await page.keyboard.press(key);
			await frames(page);
			const after = await page.evaluate(readNav);
			const what = `${key === 'Enter' ? '"Back to the sections"' : 'ArrowRight'} at ${width}x${height}`;
			expect.soft(after.active?.inNav, `the focus after ${what}`).toBe(true);
			const a = after.active!;
			expect.soft(a.top, `the focus's top in the viewport after ${what}`).toBeGreaterThanOrEqual(0);
			expect
				.soft(a.bottom, `the focus's bottom in the viewport after ${what}`)
				.toBeLessThanOrEqual(after.innerHeight);
			if (height > 320) {
				// Not under short:, where the page scrolls: the pane's own view too, the page still.
				focusInSight(after, `after ${what}`);
				await pageStill(page, `after ${what}`);
			}
		}
	}
	await page.setViewportSize(viewport);
	await settle(page, 1000);

	// The stop on Group chart, then every member unticked and the card closed: the station's
	// buttons go, and Tab into the nav lands on one that exists, the nearest earlier (§5.4).
	await toolbar.getByRole('button', { name: /^Group chart/ }).press('Enter');
	await expect(toolbar.getByRole('button', { name: /^Group chart/ })).toHaveAttribute(
		'tabindex',
		'0'
	);
	const members = card.getByRole('group', { name: 'Pumps in the group' });
	for (const box of await members.getByRole('checkbox').all()) {
		if (await box.isChecked()) await box.click();
	}
	await card.getByRole('button', { name: /^Pumps together/ }).click();
	await expect(toolbar.getByRole('button')).toHaveText([
		'Per pump',
		/^Pump chart/,
		/^Pumps together/
	]);
	// The focus outside the toolbar, the stop is the current section (the scroll's; the clamp to
	// the nearest earlier section is PumpsNav.svelte.test.ts's): one that exists, the only stop.
	await resultsPane(page).getByRole('tab', { name: 'Pumps', exact: true }).focus();
	await page.keyboard.press('Tab');
	const focused = await page.evaluate(() => {
		const a = document.activeElement as HTMLElement;
		return {
			inToolbar: !!a.closest('[role="toolbar"]'),
			name: (a.textContent ?? '').trim(),
			stop: a.tabIndex,
			stops: [...(a.closest('[role="toolbar"]')?.querySelectorAll('button') ?? [])].filter(
				(b) => b.tabIndex === 0
			).length
		};
	});
	expect(focused.inToolbar).toBe(true);
	expect(['Per pump', 'Pump chart', 'Pumps together']).toContain(focused.name.split(',')[0]);
	expect(focused.stop).toBe(0);
	expect(focused.stops).toBe(1);
	expect(await page.evaluate(() => location.hash)).toBe(hash);
});

// ---- S2 review fixes: the closed card's heading ------------------------------------------------

test('the closed card’s heading keeps “Pumps together” on one line beside the condenser’s six members, at each size (§5.3 item 3, §5.6; S2 review LAYOUT-3)', async ({
	page
}, info) => {
	test.setTimeout(240_000);
	await open(page, exampleProject('condenser-water')!);
	await solveConverged(page);
	const tab = await pumpsTab(page);
	await settle(page);
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const toggle = card.getByRole('button', { name: /^Pumps together/ });
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	const viewport = page.viewportSize()!;
	const sizes =
		info.project.name === 'mobile' ? [viewport, { width: 320, height: 640 }] : [viewport];
	for (const size of sizes) {
		await page.setViewportSize(size);
		await settle(page, 1000);
		// The lines the words are drawn on: the distinct tops of a Range's boxes over them.
		const read = await toggle.evaluate((button) => {
			const words = 'Pumps together';
			const walker = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
			let lines = 0;
			for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
				const at = n.data.indexOf(words);
				if (at < 0) continue;
				const range = document.createRange();
				range.setStart(n, at);
				range.setEnd(n, at + words.length);
				lines = new Set(
					[...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top))
				).size;
				break;
			}
			return {
				lines,
				text: (button.textContent ?? '').replace(/\s+/g, ' ').trim(),
				// Nothing of the members cut off (their names shown whole, S1's lesson).
				clipped: button.scrollWidth > button.clientWidth
			};
		});
		console.log(
			`the closed card's heading at ${sizeOf(page)}: ${read.lines} line(s), ${read.text}`
		);
		expect.soft(read.lines, `"Pumps together" on one line at ${sizeOf(page)}`).toBe(1);
		expect.soft(read.clipped, `the toggle's words cut off at ${sizeOf(page)}`).toBe(false);
	}
	await page.setViewportSize(viewport);
});

// ---- S3 review: a 40-character unbroken name in the card (LAYOUT-1, LAYOUT-2) ------------------

/** §9 S5's unbroken-name case, 40 characters and no space: a pump's name and a case's. */
const LONG_PUMP = 'CondenserWaterPrimaryLoopPumpNorthSide01';
const LONG_CASE = 'PumpP1OffForMaintenanceNorthSideWinter01';

test('a 40-character unbroken pump name and case name show their ends in the card at each size: the legend, the members, the cases, the group table a list on phones (§5.3, §5.5; S3 review LAYOUT-1, LAYOUT-2)', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	const project = projectOf('lineups');
	project.components.find((c) => c.id === 'P1')!.name = LONG_PUMP;
	project.scenarios!.find((s) => s.id === 'S4')!.name = LONG_CASE;
	await lineups(page, project);
	const tab = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	// The names are drawn where the review found them cut: the legend, the members, the cases on
	// the chart and the group table.
	await expect(card.getByRole('list', { name: 'Legend' })).toContainText(LONG_PUMP);
	await expect(card.getByRole('group', { name: 'Pumps in the group' })).toContainText(LONG_PUMP);
	await expect(card.getByRole('group', { name: 'Cases on this chart' })).toContainText(LONG_CASE);
	await expect(
		card.getByRole('table', { name: 'The pumps in the group' }).getByRole('rowheader').first()
	).toContainText(LONG_PUMP);
	const viewport = page.viewportSize()!;
	const sizes =
		info.project.name === 'mobile' ? [viewport, { width: 320, height: 640 }] : [viewport];
	for (const size of sizes) {
		await page.setViewportSize(size);
		await settle(page, 1000);
		const where = `the long names at ${sizeOf(page)}`;
		// The card's own checks: Results per pump's table above it is the shared ResultsTable's,
		// outside this slice, and draws a long name of its own.
		const cut = await cutInCard(page);
		console.log(`${where}: cut ${JSON.stringify(cut)}`);
		expect.soft(cut, `names cut short in the card, ${where}`).toEqual([]);
		expect
			.soft(await groupTableSideways(page), `the group table's box scrolls sideways, ${where}`)
			.toBe(false);
		// The group table a ResultsTable (§9 S6a): the long name in sight to its end, a trace
		// button; its title, controls and flag lines as in every view.
		await groupTablePart(page, where);
		// The extremes (§9 S5): the long pump name a row header shown to its end, the long case
		// name in their cells, and their box not scrolling sideways, at 1280×800 a table.
		const extremes = await page.evaluate(readExtremes);
		expect.soft(extremes, `the extremes drawn, ${where}`).not.toBeNull();
		expect.soft(extremes?.rows[0]?.name, `the extremes' first row, ${where}`).toBe(LONG_PUMP);
		expect
			.soft(
				extremes?.rows.some((r) => r.cells.some((c) => c.text.includes(LONG_CASE))),
				`the long case's name in an extremes' cell, ${where}`
			)
			.toBe(true);
		if (size.width === 1280)
			expect.soft(extremes?.list, `the extremes a table, ${where}`).toBe(false);
		await extremesPart(page, '', where);
		// Running combinations (§9 S5): the long pump name in every case's rows and the long case
		// name in its heading, each shown to its end in the box's view, sticky in the table.
		await combinationsPart(page, '', where, null);
		const named = await page.evaluate(readCombinations);
		expect
			.soft(
				named?.atStart.filter((g) => g.members.some((m) => m.name === LONG_PUMP)).length,
				`the long pump name in each case's rows, ${where}`
			)
			.toBe(named?.atStart.filter((g) => g.members.length).length);
		expect
			.soft(
				named?.atStart.some((g) => g.lines[0]?.text.startsWith(LONG_CASE)),
				`the long case name heading its case, ${where}`
			)
			.toBe(true);
		// Sorted (§9 S6b): one table with a Case column, the long case name in its Case cells and
		// the long pump name in its rows, each shown to its end; then the cases back.
		await sortCombinations(page, /^NPSH margin/, 'npshMargin');
		const flat = await combinationsTablePart(page, `${where}, sorted`, 'flat');
		expect
			.soft(
				flat?.rows.filter((r) => r.case.startsWith(LONG_CASE)).length,
				`the long case's rows, ${where}`
			)
			.toBeGreaterThan(0);
		expect
			.soft(flat?.rows.filter((r) => r.name === LONG_PUMP).length, `the long pump's rows, ${where}`)
			.toBe(named?.atStart.filter((g) => g.members.length).length);
		await sortCombinations(page, /^NPSH margin/, 'npshMargin', true);
		// Each line of a long name ends inside the card, outside a box that scrolls (the data
		// tables, and the group table at 640 px and over, whose name column wraps at 12 rem).
		const past = await card.evaluate(namesPast, [LONG_PUMP, LONG_CASE]);
		console.log(`${where}: past the card ${JSON.stringify(past)}`);
		expect.soft(past, `a long name's line past the card's edge, ${where}`).toEqual([]);
		// And inside the pump chart's figure: its caption and, on a phone, the case's row header in
		// the list "Operating points by case" (S7 review LAYOUT-5, PRE-OPPOINTS-LONGCASE). Pump P1 is
		// off in the long-named case, which since S8 takes a slot (and a row there) only while the
		// other cases' system curves are on (§9 S8 Slots): on for these checks, then off again.
		const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
		await expect(figure.locator('figcaption')).toContainText(LONG_PUMP);
		const curves = figure.getByRole('checkbox', {
			name: "Also show the other cases' system curves"
		});
		await curves.check();
		await expect(curveTableFold(figure, `System curve, ${LONG_CASE}`)).toHaveCount(1, {
			timeout: 120_000
		});
		await settle(page);
		await expect(
			figure.getByRole('table', { name: 'Operating points by case' }).getByRole('rowheader')
		).toContainText([LONG_CASE]);
		const pastFigure = await figure.evaluate(namesPast, [LONG_PUMP, LONG_CASE]);
		console.log(`${where}: past the pump chart ${JSON.stringify(pastFigure)}`);
		expect.soft(pastFigure, `a long name's line past the pump chart's edge, ${where}`).toEqual([]);
		await curves.uncheck();
		await settle(page);
		// S8 (§9 S8, §6.2): Pump P1 is off in the long-named case, so on its chart the case takes
		// no slot and the line under the list names it, every line of it inside the chart's card.
		const offLine = tab.locator('[data-pump-chart] [data-pump-off-cases]');
		await expect(offLine).toContainText(LONG_CASE);
		const offPast = await offLine.evaluate((p) => {
			const edge = p.closest('[data-pump-chart]')!.getBoundingClientRect().right;
			const range = document.createRange();
			range.selectNodeContents(p);
			return Math.max(...[...range.getClientRects()].map((b) => b.right)) - edge;
		});
		expect
			.soft(offPast, `the off line past the pump chart's card, ${where}`)
			.toBeLessThanOrEqual(0.5);
		expect.soft(await seenLine(offLine), `the off line on screen, ${where}`).toBe(true);
	}
	await page.setViewportSize(viewport);
});

/**
 * The lines of `names` drawn past the right edge of `scope`, outside a box that scrolls sideways
 * (where a line may run past the box's view by design), each as "tag "words" to x past edge".
 */
function namesPast(scope: Element, names: string[]): string[] {
	const edge = scope.getBoundingClientRect().right;
	const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
	const found: string[] = [];
	for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
		const el = n.parentElement!;
		if (!names.some((name) => n!.data.includes(name))) continue;
		const r = el.getBoundingClientRect();
		if (!el.checkVisibility() || r.width <= 1 || r.height <= 1) continue;
		let scrolls = false;
		for (let a: Element | null = el; a && a !== scope; a = a.parentElement) {
			if (/(auto|scroll)/.test(getComputedStyle(a).overflowX)) scrolls = true;
		}
		if (scrolls) continue;
		const range = document.createRange();
		range.selectNodeContents(n);
		const right = Math.max(...[...range.getClientRects()].map((b) => b.right));
		if (right > edge + 0.5) {
			found.push(
				`${el.tagName.toLowerCase()} "${n.data.trim().slice(0, 50)}" to ${Math.round(right)} past ${Math.round(edge)}`
			);
		}
	}
	return found;
}

// ---- S6a: the group table's sort, Fields and Flagged only in the browser ------------------------

test('the group table sorts, chooses its fields and shows the flagged pumps only, each flag line under its pump; on a phone its Fields sheet spans the screen from its foot, over the pinned nav (§9 S6a, §5.5; build-density.md §14 to §18)', async ({
	page
}, info) => {
	test.setTimeout(240_000);
	// The ladder (pump-groups-input.json): Pump P1 without a flag, P2 and P3 with a warning each.
	await open(page, projectOf('ladder'));
	await solveConverged(page);
	const tab = await pumpsTab(page);
	const card = await openCard(page, tab);
	const block = card.locator('[data-group-table]');
	// The table's box (a region only while it overflows since S7, §9 S7).
	const region = card.getByRole('table', { name: 'The pumps in the group' }).locator('..');
	await expect(region.getByRole('rowheader')).toHaveCount(3);
	const phone = info.project.name === 'mobile';
	const names = () => region.locator('tbody th[scope="row"] span.min-w-0').allTextContents();
	/** Each flag line, the pump whose row it follows and whether its sentences are in sight. */
	const lines = () =>
		region.locator('[data-row-notes]').evaluateAll((all) =>
			all.map((line) => ({
				id: line.getAttribute('data-row-notes'),
				after: line
					.closest('tr')!
					.previousElementSibling?.querySelector('th span.min-w-0')
					?.textContent?.trim(),
				seen: [...line.querySelectorAll('[data-flag-text]')].every((t) => {
					const r = t.getBoundingClientRect();
					return t.checkVisibility() && r.width > 1 && r.height > 1;
				})
			}))
		);
	// Its title, controls, names and flag lines in sight, each as in every view; here with
	// Flagged only offered and two flag lines drawn.
	await groupTablePart(page, `the ladder at ${sizeOf(page)}`);
	// The record (PUMPS_LAYOUT_RECORD): the table with its flag lines, and the Fields sheet below.
	const shot = async (name: string) => {
		if (!RECORD) return;
		await page.waitForTimeout(300);
		await page.screenshot({
			path: path.join(RECORD, 'segments', `ladder-${sizeOf(page)}-${name}.png`),
			scale: 'css'
		});
	};
	if (RECORD) mkdirSync(path.join(RECORD, 'segments'), { recursive: true });
	await block.scrollIntoViewIfNeeded();
	await shot('group-table');
	const original = await names();
	expect(original).toEqual(['Pump P1', 'Pump P2', 'Pump P3']);
	expect(await lines()).toEqual([
		{ id: 'P2', after: 'Pump P2', seen: true },
		{ id: 'P3', after: 'Pump P3', seen: true }
	]);

	// Sort by flow: from its heading from 640 px, from "Sort by" on a phone (the same sort).
	const flow = region.getByRole('columnheader', { name: /^Flow/ });
	if (phone) await block.getByRole('combobox', { name: 'Sort by' }).selectOption('flow');
	else await flow.getByRole('button', { name: 'Flow L/s' }).click();
	await expect(flow).toHaveAttribute('aria-sort', 'ascending');
	const flows = (await region.locator('tbody td[data-label^="Flow"]').allTextContents()).map(
		Number
	);
	expect(flows).toEqual([...flows].sort((a, b) => a - b));
	expect(await names()).not.toEqual(original);
	// Each flag line still under its own pump.
	for (const line of await lines()) expect(line.after).toBe(`Pump ${line.id}`);

	// Flagged only: the flagged pumps, each with its flag line, its sentences in sight.
	const flagged = block.getByRole('checkbox', { name: 'Flagged only (2 of 3)' });
	await flagged.check();
	await expect(region.getByRole('rowheader')).toHaveCount(2);
	expect(await lines()).toEqual([
		{ id: 'P3', after: 'Pump P3', seen: true },
		{ id: 'P2', after: 'Pump P2', seen: true }
	]);
	await flagged.uncheck();
	await expect(region.getByRole('rowheader')).toHaveCount(3);

	// Fields: a menu under its button from 640 px; on a phone a sheet across the screen from its
	// foot (build-density.md §16), fixed to the screen, no container above it trapping it (§5.5),
	// drawn over the pinned nav and the page.
	const fields = block.getByRole('button', { name: /^Fields/ });
	await fields.click();
	const sheet = page.getByRole('group', { name: 'Fields shown in The pumps in the group' });
	await expect(sheet).toBeVisible();
	await fieldsMenuInPlace(page, sheet, fields, `the ladder's group table at ${sizeOf(page)}`);
	await shot('fields');
	await sheet.getByRole('checkbox', { name: /^Shaft power/ }).uncheck();
	await expect(region.locator('td[data-label^="Shaft power"]')).toHaveCount(0);
	await expect(region.getByRole('columnheader', { name: /^Shaft power/ })).toHaveCount(0);
	await expect(fields).toContainText(/\(\d+ of \d+\)/);
	if (phone) await sheet.getByRole('button', { name: 'Done' }).click();
	else await page.keyboard.press('Escape');
	await expect(sheet).toBeHidden();
	await expect(fields).toHaveAttribute('aria-expanded', 'false');
	// Closed from inside it, its button has the focus back (S6 review A11Y-S6-2).
	await expect(fields).toBeFocused();
	// Its flag lines still span the row, inside the box's visible width.
	const width = (await region.boundingBox())!;
	for (const text of await region.locator('[data-flag-text]').all()) {
		const r = (await text.boundingBox())!;
		expect(r.x).toBeGreaterThanOrEqual(width.x - 0.5);
		expect(r.x + r.width).toBeLessThanOrEqual(width.x + width.width + 0.5);
	}
	await fields.click();
	await sheet.getByRole('button', { name: 'Show all' }).click();
	await expect(region.locator('td[data-label^="Shaft power"]')).toHaveCount(3);
	// "Show all" goes as it is pressed: the focus stays in the menu, which Escape still closes.
	await expect(sheet).toBeVisible();
	expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true);
	await page.keyboard.press('Escape');
	await expect(sheet).toBeHidden();
	await expect(fields).toBeFocused();
	await noSidewaysScroll(page, `the ladder's group table at ${sizeOf(page)}`);
});

/**
 * A table's Fields menu where it belongs (§5.5; build-density.md §16): on a phone a sheet fixed to
 * the screen, across its width from its foot, drawn over the pinned nav and the page; from 640 px
 * a menu under its button, inside the window; under no container, transform, filter or
 * will-change that would trap a fixed sheet. S6a's check, for every Fields of the card (S6 review
 * MUT-02: Running combinations' sheet could open 6,300 px down the page with every test green).
 */
async function fieldsMenuInPlace(page: Page, sheet: Locator, fields: Locator, where: string) {
	const phone = (page.viewportSize()?.width ?? 1280) < 640;
	const viewport = page.viewportSize()!;
	const box = (await sheet.boundingBox())!;
	const button = (await fields.boundingBox())!;
	const over = await sheet.evaluate((el) => {
		const r = el.getBoundingClientRect();
		const containers: string[] = [];
		for (let e = el.parentElement; e; e = e.parentElement) {
			const s = getComputedStyle(e);
			if (
				s.containerType !== 'normal' ||
				s.transform !== 'none' ||
				s.filter !== 'none' ||
				s.willChange !== 'auto'
			) {
				containers.push(`<${e.tagName.toLowerCase()} class="${e.className}">`);
			}
		}
		const top = document.elementFromPoint(r.left + r.width / 2, r.top + 12);
		return {
			containers,
			onTop: !!top && el.contains(top),
			position: getComputedStyle(el).position
		};
	});
	expect(over.containers, `containers above the Fields menu, ${where}`).toEqual([]);
	expect(over.onTop, `the Fields menu on top, ${where}`).toBe(true);
	if (phone) {
		expect(over.position, `the Fields sheet fixed, ${where}`).toBe('fixed');
		expect(box.x, `the Fields sheet from the screen's left, ${where}`).toBeCloseTo(0, 0);
		expect(box.width, `the Fields sheet across the screen, ${where}`).toBeCloseTo(
			viewport.width,
			0
		);
		expect(box.y + box.height, `the Fields sheet at the screen's foot, ${where}`).toBeCloseTo(
			viewport.height,
			0
		);
	} else {
		expect(over.position, `the Fields menu under its button, ${where}`).toBe('absolute');
		expect(box.y).toBeGreaterThanOrEqual(button.y + button.height - 0.5);
		expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
	}
}

// ---- S6b: Running combinations sorted, its fields and its flagged rows, in the browser ---------

/** Sort Running combinations by a column, or clear the sort: its heading from 640 px, "Sort by" below. */
async function sortCombinations(page: Page, column: RegExp, key: string, clear = false) {
	const block = page.locator('[data-pumps-together] [data-running-combinations]');
	const heading = block.getByRole('table').getByRole('columnheader', { name: column });
	if ((page.viewportSize()?.width ?? 1280) < 640) {
		await block.getByRole('combobox', { name: 'Sort by' }).selectOption(clear ? '' : key);
	} else if (clear) {
		// Ascending, descending, then the table's own order.
		while ((await heading.getAttribute('aria-sort')) !== null) {
			await heading.getByRole('button').click();
		}
	} else {
		await heading.getByRole('button').click();
	}
	if (clear) await expect(heading).not.toHaveAttribute('aria-sort');
	else await expect(heading).toHaveAttribute('aria-sort', 'ascending');
}

test('Running combinations sorts into one table with a Case column, its first row the smallest NPSH margin, and back into its cases in S5’s order; Fields and Flagged only in both forms; trace buttons in the shown case’s rows only; its shadow unbroken (§9 S6b, §10 S6b; the owner’s answer 3)', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	await condenser(page);
	const tab = await pumpsTab(page);
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const block = card.locator('[data-running-combinations]');
	// The table's box (a region only while it overflows since S7, §9 S7).
	const region = card.getByRole('table', { name: 'Running combinations' }).locator('..');
	const viewport = page.viewportSize()!;
	const sizes =
		info.project.name === 'mobile' ? [viewport, { width: 320, height: 640 }] : [viewport];
	if (RECORD) mkdirSync(path.join(RECORD, 'segments'), { recursive: true });
	/** The record (PUMPS_LAYOUT_RECORD): Running combinations' top under the nav, as shown. */
	const shot = async (name: string) => {
		if (!RECORD) return;
		// Its controls' row under the pinned nav: the pane scrolled to the block, then, once the
		// nav has pinned, back by its height and a margin.
		await block.evaluate((el) => el.scrollIntoView({ block: 'start' }));
		await page.waitForTimeout(300);
		await block.evaluate((el) => {
			const nav = document.querySelector('[data-pumps-nav][data-pinned]');
			let scroller = el.parentElement;
			while (scroller && !/(auto|scroll)/.test(getComputedStyle(scroller).overflowY)) {
				scroller = scroller.parentElement;
			}
			scroller?.scrollBy(0, -((nav?.getBoundingClientRect().height ?? 0) + 8));
		});
		await page.waitForTimeout(300);
		await page.screenshot({
			path: path.join(RECORD, 'segments', `s6b-condenser-${sizeOf(page)}-${name}.png`),
			scale: 'css'
		});
	};
	const cardHeight = () => card.evaluate((c) => Math.round(c.getBoundingClientRect().height));
	const key = (r: { name: string; case: string }) => `${r.name} | ${r.case}`;
	for (const size of sizes) {
		await page.setViewportSize(size);
		await settle(page, 1000);
		const where = `the condenser at ${sizeOf(page)}`;
		const phone = size.width < 640;

		// In its own order: a row group per case, in S5's order (combinationsPart reads it).
		const before = (await combinationsTablePart(page, `${where}, unsorted`, 'grouped'))!;
		expect(before, `Running combinations drawn, ${where}`).not.toBeNull();
		expect(before.groups.length).toBe(7);
		console.log(`${where}: the open card ${await cardHeight()} px, unsorted`);
		await shot('unsorted');

		// Sorted by NPSH margin: one table, every case's pumps, by margin, those without one last,
		// the smallest first; the same rows as the cases held.
		await sortCombinations(page, /^NPSH margin/, 'npshMargin');
		const sorted = (await combinationsTablePart(page, `${where}, sorted`, 'flat'))!;
		const values = sorted.rows.map((r) => (/^-?[\d.]+$/.test(r.margin) ? Number(r.margin) : null));
		const numbers = values.filter((v): v is number => v !== null);
		expect(numbers.length, `margins, ${where}`).toBeGreaterThan(1);
		expect(values.slice(0, numbers.length), `the margins in order, ${where}`).toEqual(
			[...numbers].sort((a, b) => a - b)
		);
		expect(values.slice(numbers.length).every((v) => v === null)).toBe(true);
		expect(values[0], `the smallest margin first, ${where}`).toBe(Math.min(...numbers));
		expect(sorted.rows.map(key).sort(), `the same rows, ${where}`).toEqual(
			before.rows.map(key).sort()
		);
		// A trace button in each of the shown case's rows, wherever the sort puts them.
		expect(sorted.rows.filter((r) => r.button).map((r) => r.case)).toEqual(
			before.rows.filter((r) => r.button).map(() => before.groups[0])
		);
		console.log(`${where}: the open card ${await cardHeight()} px, sorted`);
		await shot('sorted');

		// Flagged only, still sorted: the flagged rows, each with its flag line; its count the rows.
		const flaggedRows = before.rows.filter((r) => r.flags);
		const flagged = block.getByRole('checkbox', { name: /^Flagged only/ });
		await expect(flagged).toHaveAccessibleName(
			`Flagged only (${flaggedRows.length} of ${before.rows.length})`
		);
		await flagged.check();
		const flatFlagged = (await combinationsTablePart(
			page,
			`${where}, sorted, flagged only`,
			'flat'
		))!;
		expect(flatFlagged.rows.map(key).sort()).toEqual(flaggedRows.map(key).sort());
		expect(flatFlagged.rows.every((r) => !!r.flags)).toBe(true);

		// The sort cleared: the cases with a flagged pump, in S5's order, each such pump's row.
		await sortCombinations(page, /^NPSH margin/, 'npshMargin', true);
		const groupedFlagged = (await combinationsTablePart(
			page,
			`${where}, flagged only`,
			'grouped'
		))!;
		expect(groupedFlagged.groups).toEqual(
			before.groups.filter((g) => flaggedRows.some((r) => r.case === g))
		);
		expect(groupedFlagged.rows.map(key)).toEqual(flaggedRows.map(key));
		console.log(`${where}: the open card ${await cardHeight()} px, flagged only`);
		await shot('flagged-only');
		await flagged.uncheck();

		// Fields: Head hidden in both forms, then every field back.
		const fields = block.getByRole('button', { name: /^Fields/ });
		const sheet = page.getByRole('group', { name: 'Fields shown in Running combinations' });
		// Closed by Done on a phone, from 640 px by Escape from inside it: its button has the focus
		// back (S6 review A11Y-S6-2).
		const closeSheet = async () => {
			if (phone) await sheet.getByRole('button', { name: 'Done' }).click();
			else await page.keyboard.press('Escape');
			await expect(sheet).toBeHidden();
			await expect(fields).toHaveAttribute('aria-expanded', 'false');
			await expect(fields).toBeFocused();
		};
		await fields.click();
		await expect(sheet).toBeVisible();
		await fieldsMenuInPlace(page, sheet, fields, `Running combinations, ${where}`);
		await sheet.getByRole('checkbox', { name: /^Head/ }).uncheck();
		await closeSheet();
		const noHead = async (form: string) => {
			await expect(region.locator('td[data-label^="Head"]'), `Head cells, ${form}`).toHaveCount(0);
			await expect(region.getByRole('columnheader', { name: /^Head/ })).toHaveCount(0);
			await expect(region.locator('td[data-label^="Flow"]').first()).toBeVisible();
		};
		await noHead(`grouped, ${where}`);
		await sortCombinations(page, /^Flow/, 'flow');
		await noHead(`flat, ${where}`);
		await sortCombinations(page, /^Flow/, 'flow', true);
		await fields.click();
		await sheet.getByRole('button', { name: 'Show all' }).click();
		// "Show all" goes as it is pressed: the focus stays in the menu, never on the page.
		await expect(sheet).toBeVisible();
		expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true);
		await closeSheet();

		// Back as it was: every case, in S5's order, every row.
		const after = (await combinationsTablePart(page, `${where}, again`, 'grouped'))!;
		expect(after.groups).toEqual(before.groups);
		expect(after.rows.map(key)).toEqual(before.rows.map(key));
		await noSidewaysScroll(page, `Running combinations, ${where}`);
	}
	await page.setViewportSize(viewport);
});

// ---- S6 review: the card's tables in the browser ----------------------------------------------

/**
 * The focused element against what its table's box pins (ResultsTable: the sticky first column
 * and the sticky heading row): whether the point at its centre is its own, and whether it lies
 * whole in the box's view, right of the first column (but a name or the first heading, which are
 * in it) and below the heading row (but a heading). WCAG 2.4.11 (S6 review A11Y-S6-1,
 * LAYOUT-S6-3, S6-TBL-2).
 */
function focusedInBox() {
	const a = document.activeElement as HTMLElement | null;
	const box = a?.closest<HTMLElement>('.scroll-shadow-x');
	const table = box?.querySelector('table');
	if (!a || !box || !table) return null;
	const r = a.getBoundingClientRect();
	const b = box.getBoundingClientRect();
	const [boxLeft, boxTop] = [b.left + box.clientLeft, b.top + box.clientTop];
	const [boxRight, boxBottom] = [boxLeft + box.clientWidth, boxTop + box.clientHeight];
	const fixed = table.querySelector('thead th')!;
	const inFixed = !!a.closest('th[scope="row"]') || fixed.contains(a);
	const inHead = !!a.closest('thead');
	const left = inFixed ? boxLeft : fixed.getBoundingClientRect().right;
	// The heading row's cells stick, not its row group, which keeps its place in the table.
	const top = inHead ? boxTop : fixed.getBoundingClientRect().bottom;
	const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
	return {
		name: (a.textContent ?? '').replace(/\s+/g, ' ').trim(),
		own: !!hit && a.contains(hit),
		whole:
			r.left >= left - 0.5 &&
			r.right <= boxRight + 0.5 &&
			r.top >= top - 0.5 &&
			r.bottom <= boxBottom + 0.5,
		at: [r.left, r.top, r.right, r.bottom].map(Math.round),
		clear: [left, top].map(Math.round)
	};
}

test('S6 review: in the card’s tables a focus is never under what they pin, a pressed heading stays under the pointer, “Pump” sorts on a phone and the field chosen shows whole, each table’s controls named apart (§5.4, §7; WCAG 2.4.11)', async ({
	page
}, info) => {
	test.setTimeout(480_000);
	await condenser(page);
	const tab = await pumpsTab(page);
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const phone = info.project.name === 'mobile';
	const soft = expect.configure({ soft: true });
	const groupBlock = card.locator('[data-group-table]');
	const combos = card.locator('[data-running-combinations]');
	const groupTitle = (await groupBlock.locator('p').first().innerText()).trim();
	expect(groupTitle).toMatch(/^The pumps in the group, /);

	// Each table's Fields and, on a phone, its "Sort by" named apart: the visible words, then the
	// table's name, visually hidden (A11Y-S6-3; ui-guide).
	const captions = ['Results per pump', groupTitle, 'Running combinations'];
	await expect(tab.getByRole('button', { name: /^Fields/ })).toHaveCount(3);
	for (const caption of captions) {
		await expect
			.soft(
				tab.getByRole('button', { name: `Fields, ${caption}`, exact: true }),
				`Fields of ${caption}`
			)
			.toHaveCount(1);
		if (phone) {
			await expect
				.soft(
					tab.getByRole('combobox', { name: `Sort by, ${caption}`, exact: true }),
					`"Sort by" of ${caption}`
				)
				.toHaveCount(1);
		}
	}

	if (!phone) {
		const boxes = {
			'Results per pump': tab.getByRole('table', { name: 'Results per pump' }).locator('xpath=..'),
			'the group table': groupBlock.getByRole('region'),
			'Running combinations': combos.getByRole('region')
		};
		// Every heading focused from the last to the first (as Shift+Tab reached them, S6's
		// findings), the box scrolled to its right end: in sight, never under the sticky column.
		const hidden: string[] = [];
		const walk = async (label: string, box: Locator) => {
			await box.evaluate((el) => {
				el.scrollIntoView({ block: 'center' });
				el.scrollLeft = el.scrollWidth;
			});
			const buttons = box.locator('thead button');
			const n = await buttons.count();
			for (let i = n - 1; i >= 0; i--) {
				await buttons.nth(i).evaluate((b) => b.focus());
				await frames(page);
				const f = await page.evaluate(focusedInBox);
				if (!f?.own || !f.whole) hidden.push(`${label}: "${f?.name}" ${JSON.stringify(f)}`);
			}
		};
		for (const [label, box] of Object.entries(boxes)) await walk(label, box);
		// Running combinations sorted (one table with a Case column) too.
		await sortCombinations(page, /^NPSH margin/, 'npshMargin');
		await walk('Running combinations sorted', boxes['Running combinations']);
		soft(hidden, 'focused headings under the sticky column or out of the box').toEqual([]);

		// The heading row one Tab stop: End and the arrows walk it, each heading in sight.
		const arrows: string[] = [];
		for (const [label, box] of Object.entries(boxes)) {
			const stop = box.locator('thead button:not([tabindex="-1"])');
			soft(await stop.count(), `${label}: its heading row's Tab stops`).toBe(1);
			const names = (await box.locator('thead button').allInnerTexts()).map((t) =>
				t.replace(/\s+/g, ' ').trim()
			);
			await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
			await stop.first().focus();
			await page.keyboard.press('End');
			for (let i = names.length - 1; i >= 0; i--) {
				await frames(page);
				const f = await page.evaluate(focusedInBox);
				if (!f || f.name !== names[i] || !f.own || !f.whole) {
					arrows.push(`${label}: "${names[i]}" ${JSON.stringify(f)}`);
				}
				if (i > 0) await page.keyboard.press('ArrowLeft');
			}
		}
		soft(arrows, 'headings walked by the arrows, from End back to the first').toEqual([]);

		// The trace buttons of the sorted table, Shift+Tab from after its box scrolled to its foot:
		// never under the sticky heading row (S6-TBL-2).
		const box = boxes['Running combinations'];
		await box.evaluate((el) => (el.scrollTop = el.scrollHeight));
		await card.getByRole('button', { name: 'Back to the sections' }).focus();
		const under: string[] = [];
		let traced = 0;
		for (let i = 0; i < 80; i++) {
			await page.keyboard.press('Shift+Tab');
			await frames(page);
			const where = await page.evaluate(() => {
				const a = document.activeElement;
				const block = document.querySelector('[data-running-combinations]');
				return !a || !block?.contains(a) ? 'out' : a.closest('tbody') ? 'body' : 'other';
			});
			if (where !== 'body') {
				if (traced) break;
				continue;
			}
			traced++;
			const f = await page.evaluate(focusedInBox);
			if (!f?.own || !f.whole) under.push(JSON.stringify(f));
		}
		soft(traced, 'trace buttons reached by Shift+Tab').toBeGreaterThan(0);
		soft(under, 'focused trace buttons under the heading row').toEqual([]);
		await sortCombinations(page, /^NPSH margin/, 'npshMargin', true);

		// A heading pressed by the pointer stays under it as the table flattens and groups again:
		// a second press at the same point reverses, a third clears (LAYOUT-S6-2).
		const jumps: string[] = [];
		for (const [column, words, end] of [
			[/^Flow/, 'Flow', false],
			[/^NPSH margin/, 'NPSH margin', true]
		] as const) {
			const heading = box.getByRole('columnheader', { name: column });
			await box.evaluate((el, toEnd) => {
				el.scrollIntoView({ block: 'center' });
				el.scrollLeft = toEnd ? el.scrollWidth : 0;
			}, end);
			await frames(page);
			const b = (await heading.getByRole('button').boundingBox())!;
			const [x, y] = [b.x + b.width / 2, b.y + b.height / 2];
			for (const sort of ['ascending', 'descending', null]) {
				await page.mouse.click(x, y);
				await frames(page);
				const now = await heading.getAttribute('aria-sort');
				const f = await page.evaluate(focusedInBox);
				const what = `${words} at the box's ${end ? 'end' : 'start'}, pressed to ${sort ?? 'clear'}`;
				if (now !== sort) jumps.push(`${what}: aria-sort ${now}`);
				if (!f?.own || !f.whole || !f.name.startsWith(words)) {
					jumps.push(`${what}: the focus ${JSON.stringify(f)}`);
				}
				if (now !== sort) break;
			}
			if ((await heading.getAttribute('aria-sort')) !== null) {
				await sortCombinations(page, column, '', true);
			}
		}
		soft(jumps, 'a heading pressed three times at one point').toEqual([]);
	} else {
		// A phone's "Sort by": "Pump" sorts by name in both card tables (STRUCT-3, TBL-1), and
		// every field chosen shows whole beside its direction button, on one line with Fields, at
		// 390 and 320 px (TBL-4).
		const viewport = page.viewportSize()!;
		const cut: string[] = [];
		for (const size of [viewport, { width: 320, height: 640 }]) {
			await page.setViewportSize(size);
			await settle(page, 1000);
			for (const [label, block] of [
				['the group table', groupBlock],
				['Running combinations', combos]
			] as const) {
				const where = `${label} at ${sizeOf(page)}`;
				const select = block.getByRole('combobox', { name: /^Sort by/ });
				const fields = block.getByRole('button', { name: /^Fields/ });
				const direction = block.getByRole('button', { name: /lowest first|highest first/ });
				await select.selectOption({ label: 'Pump' });
				await expect
					.soft(
						block.getByRole('columnheader', { name: 'Pump', exact: true }),
						`${where}: sorted by name`
					)
					.toHaveAttribute('aria-sort', 'ascending');
				soft(
					await select.evaluate((el) => (el as HTMLSelectElement).selectedOptions[0]?.text),
					`${where}: "Pump" shown`
				).toBe('Pump');
				soft(await direction.count(), `${where}: "Pump" chosen, its direction`).toBe(1);
				if (label === 'Running combinations') {
					await expect
						.soft(
							block.getByRole('columnheader', { name: 'Case', exact: true }),
							`${where}: one table with a Case column`
						)
						.toHaveCount(1);
				}
				const options = (await select.locator('option').allInnerTexts()).filter(
					(o) => o !== 'Table order'
				);
				for (const option of options) {
					await select.selectOption({ label: option });
					const m = await select.evaluate((el) => {
						const s = el as HTMLSelectElement;
						const css = getComputedStyle(s);
						const context = document.createElement('canvas').getContext('2d')!;
						context.font = `${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
						const text = s.selectedOptions[0]?.text ?? '';
						return {
							text,
							width: Math.ceil(context.measureText(text).width),
							room: Math.floor(
								s.clientWidth - parseFloat(css.paddingLeft) - parseFloat(css.paddingRight)
							)
						};
					});
					if (m.room - MENULIST_INNER < m.width) {
						cut.push(`${where}: "${m.text}" ${m.width} px in ${m.room - MENULIST_INNER}`);
					}
					if (!(await direction.count())) {
						cut.push(`${where}: "${m.text}" chosen, no sort`);
						continue;
					}
					const tops = await Promise.all(
						[select, direction, fields].map(async (c) => (await c.boundingBox())!.y)
					);
					if (Math.max(...tops) - Math.min(...tops) > 2) {
						cut.push(`${where}: "${m.text}" chosen, Sort, its direction and Fields on ${tops}`);
					}
				}
				await select.selectOption({ label: 'Table order' });
				await expect(direction).toHaveCount(0);
			}
		}
		soft(cut, 'a field chosen cut short, or its line broken').toEqual([]);
		await page.setViewportSize(viewport);
	}
});

// ---- S6, the second check: a pressed heading's words stay put; a tap is a press ---------------

/**
 * Heading `i` of a results table's heading row (its sort buttons in order), the box placed so the
 * heading lies whole in its view, 8 px clear of the box's right edge and 32 px clear of the sticky
 * column (room for the arrow and gap a sort adds on a numeric heading's left, 20 px, and its ring,
 * 4 px, so the box need not scroll to show them), as far from the box's start as that allows and
 * at least 24 px from it, so a press that scrolled the box back by the arrow's 20 px would show
 * (S6-FIX-1). `placed` is false where no such place is.
 */
function placeHeading(el: Element, i: number) {
	const box = el as HTMLElement;
	const button = box.querySelectorAll<HTMLElement>('thead button[data-sort-key]')[i]!;
	const name = (button.textContent ?? '').replace(/\s+/g, ' ').trim();
	const numeric = button.classList.contains('flex-row-reverse');
	box.scrollLeft = 0;
	const fixed = box.querySelector('thead th')!.getBoundingClientRect().right;
	const b = box.getBoundingClientRect();
	const right = b.left + box.clientLeft + box.clientWidth;
	const r = button.getBoundingClientRect();
	const hi = Math.min(box.scrollWidth - box.clientWidth, Math.floor(r.left - fixed - 32));
	const lo = Math.max(24, Math.ceil(r.right - right + 8));
	if (hi < lo) return { name, numeric, placed: false };
	box.scrollLeft = hi;
	return { name, numeric, placed: true };
}

/**
 * What a press on heading `i` may move (S6-FIX-1): the left of its words (the button's first
 * child, its label and unit, whose size no sort changes), its column's width, its sort, and the
 * edges of each value's cell in the first row of values, by its column's label, in their order.
 * `own` is the pressed column's label. `hit` says whether the point at the button's centre is the
 * button's (no pinned nav over it); `whole`, whether the button, its arrow with it, lies whole in
 * the box's view right of the sticky column (LAYOUT-S6-2).
 */
function readPress(el: Element, i: number) {
	const button = el.querySelectorAll<HTMLElement>('thead button[data-sort-key]')[i]!;
	const th = button.closest('th')!;
	const row = el.querySelector('tbody tr:has(> td[data-label])')!;
	const tds = [...row.querySelectorAll<HTMLElement>(':scope > td[data-label]')];
	const cells: Record<string, [number, number]> = {};
	for (const td of tds) {
		const r = td.getBoundingClientRect();
		cells[td.dataset.label!] = [r.left, r.right];
	}
	const own = (row.children[[...th.parentElement!.children].indexOf(th)] as HTMLElement).dataset
		.label!;
	const b = button.getBoundingClientRect();
	const at = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
	const box = el as HTMLElement;
	const fixed = box.querySelector('thead th')!.getBoundingClientRect().right;
	const right = box.getBoundingClientRect().left + box.clientLeft + box.clientWidth;
	return {
		words: button.firstElementChild!.getBoundingClientRect().left,
		width: th.getBoundingClientRect().width,
		sort: th.getAttribute('aria-sort'),
		cells,
		order: tds.map((td) => td.dataset.label!),
		own,
		hit: !!at && button.contains(at),
		whole: b.left >= fixed - 0.5 && b.right <= right + 0.5
	};
}

/**
 * A press read against the table before the first press: the heading's words keep their x; only
 * the pressed column may change width, by its arrow and gap (20 px) at most, and then it grows
 * away from its words, so the columns before it move back by as much and those after it stay;
 * every other column stays (S6-FIX-1). The Case column a sort adds is in neither reading's place.
 */
function pressMoves(
	before: ReturnType<typeof readPress>,
	after: ReturnType<typeof readPress>,
	what: string
): string[] {
	const out: string[] = [];
	const words = after.words - before.words;
	if (Math.abs(words) > 0.5) out.push(`${what}: its words moved ${words.toFixed(1)} px`);
	const grew = after.width - before.width;
	if (grew < -0.5 || grew > 20.5) out.push(`${what}: its column grew ${grew.toFixed(1)} px`);
	const at = before.order.indexOf(before.own);
	before.order.forEach((label, k) => {
		const [then, now] = [before.cells[label]!, after.cells[label]];
		if (!now) return;
		const [edge, shift] = k < at ? [0, -grew] : k === at ? [1, 0] : [0, 0];
		const moved = now[edge]! - then[edge]! - shift;
		if (Math.abs(moved) > 0.5) {
			out.push(`${what}: "${label}" ${edge ? 'right' : 'left'} edge moved ${moved.toFixed(1)} px`);
		}
	});
	return out;
}

/** Clear a results table's sort from a script (its sorted heading's button pressed until none). */
async function clearSort(box: Locator) {
	for (let k = 0; k < 3; k++) {
		const sorted = box.locator('thead th[aria-sort] button');
		if (!(await sorted.count())) return;
		await sorted.evaluate((b) => (b as HTMLElement).click());
	}
}

test('S6, the second check: a numeric heading pressed three times at one point, its box scrolled from its start, keeps its words and every other column in place, but for its own column’s growth by its arrow (Links, Nodes and the Pumps tab’s three tables; S6-FIX-1)', async ({
	page
}, info) => {
	test.skip(
		info.project.name === 'mobile',
		'the headings show from 640 px; a phone sorts by Sort by'
	);
	test.setTimeout(480_000);
	const moved: string[] = [];
	const pressed: Record<string, number> = {};
	const pressEach = async (label: string, box: Locator) => {
		await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
		await clearSort(box);
		const n = await box.locator('thead button[data-sort-key]').count();
		pressed[label] = 0;
		for (let i = 1; i < n; i++) {
			const place = await box.evaluate(placeHeading, i);
			if (!place.numeric || !place.placed) continue;
			await frames(page);
			const before = await box.evaluate(readPress, i);
			if (!before.hit) {
				moved.push(`${label}, "${place.name}": its button's centre covered`);
				continue;
			}
			pressed[label]++;
			const b = (await box.locator('thead button[data-sort-key]').nth(i).boundingBox())!;
			for (const sort of ['ascending', 'descending', null]) {
				await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
				await frames(page);
				const after = await box.evaluate(readPress, i);
				const what = `${label}, "${place.name}" pressed to ${sort ?? 'clear'}`;
				if (after.sort !== sort) {
					moved.push(`${what}: aria-sort ${after.sort}`);
					break;
				}
				moved.push(...pressMoves(before, after, what));
				if (!after.whole) moved.push(`${what}: the button not whole in the box's view`);
			}
			await clearSort(box);
		}
	};

	await open(page, exampleProject('gravity-branch')!);
	await solveConverged(page);
	await showPane(page, 'Results');
	const links = await resultsView(page, 'Links');
	await pressEach(
		'Links',
		links.getByRole('table', { name: 'Results per pipe connection' }).locator('xpath=..')
	);
	const nodes = await resultsView(page, 'Nodes');
	await pressEach('Nodes', nodes.getByRole('table').first().locator('xpath=..'));

	await condenser(page);
	const tab = await pumpsTab(page);
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	await pressEach(
		'Results per pump',
		tab.getByRole('table', { name: 'Results per pump' }).locator('xpath=..')
	);
	await pressEach('the group table', card.locator('[data-group-table]').getByRole('region'));
	await pressEach(
		'Running combinations',
		card.locator('[data-running-combinations]').getByRole('region')
	);
	expect.soft(moved, 'what a press on a numeric heading moved').toEqual([]);
	// Each table's headings pressed where its box scrolls from its start: at least two in each.
	for (const [label, n] of Object.entries(pressed)) {
		expect.soft(n, `${label}: numeric headings pressed`).toBeGreaterThanOrEqual(2);
	}
	expect(Object.keys(pressed)).toHaveLength(5);
});

/**
 * The end of a box's scroll, a column a sort's arrow widens by a fraction of a pixel (S6, the CI
 * fix; PR #273's desktop run): CI's Chromium drew Nodes' "HGL (m)" in the gravity-branch example
 * 0.8 px narrower than its heading with its arrow and gap, and the table ending more than 0.5 px
 * past a whole pixel, where the box's scroll range is a whole number of pixels. Placed at the end
 * of the box's scroll, the press widened the table 0.8 px but not the range, the box could not
 * follow, and its words and every other column moved 0.8 px (1.0 on the clear).
 *
 * This draws that in any Chromium, by styles on box `el` (`data-fraction`): heading `name`'s
 * words a min-width of its column's width rounded up, so its heading (words, button and cell
 * padding) sets the column's width and a sort's arrow and gap (20 px) widen it; its values cells
 * a min-width `growth` px short of that, so a sort widens the column by exactly `growth`; with
 * `caseWidth`, the Case column a sort adds to a table of row groups that wide; and the first other
 * column's cells a min-width up to 63/64 px over their width, chosen so a table wider by what
 * the sort adds gets the least scroll range (`short`, what it lacks); with `more`, the most (the
 * other way: `short` below 0, the range a whole pixel more than a 13/64 px growth; the CI fix's
 * review CIFIX-1, TEST-CI-1). Widths are in 64ths of a pixel, as layout keeps them. `index` is the
 * heading's among the heading row's sort buttons.
 */
function fractionAtEnd(
	el: Element,
	[name, growth, caseWidth, more = false]: readonly [string, number, number, boolean?]
) {
	const box = el as HTMLElement;
	box.dataset.fraction = '';
	let style = document.getElementById('fraction-at-end') as HTMLStyleElement | null;
	if (!style) {
		style = document.createElement('style');
		style.id = 'fraction-at-end';
		document.head.append(style);
	}
	style.textContent = '';
	const buttons = [...box.querySelectorAll<HTMLElement>('thead button[data-sort-key]')];
	const index = buttons.findIndex((b) => (b.textContent ?? '').trim().startsWith(name));
	const button = buttons[index]!;
	const th = button.closest('th')!;
	const row = box.querySelector('tbody tr:has(> td[data-label])')!;
	const own = (row.children[[...th.parentElement!.children].indexOf(th)] as HTMLElement).dataset
		.label!;
	const knob = [...row.querySelectorAll<HTMLElement>(':scope > td[data-label]')].find(
		(td) => td.dataset.label !== own
	)!;
	const rule = (selector: string, width: number) =>
		`[data-fraction] ${selector} { min-width: ${width}px; }`;
	const cells = (label: string) => `td[data-label="${CSS.escape(label)}"]`;
	const key = CSS.escape(button.dataset.sortKey!);
	const rules = [
		rule(
			`thead button[data-sort-key="${key}"] > span:first-child`,
			Math.ceil(th.getBoundingClientRect().width)
		)
	];
	style.textContent = rules.join('\n');
	const heading = th.getBoundingClientRect().width;
	rules.push(rule(cells(own), heading + 20 - growth));
	if (caseWidth) rules.push(rule(cells('Case'), caseWidth));
	const knobWidth = knob.getBoundingClientRect().width;
	const range = (extra: number) => {
		style.textContent = [...rules, rule(cells(knob.dataset.label!), knobWidth + extra)].join('\n');
		return box.scrollWidth - box.clientWidth;
	};
	const lacks = Array.from({ length: 64 }, (_, k) => {
		const from = range(k / 64);
		return growth + caseWidth - (range(k / 64 + growth + caseWidth) - from);
	});
	const short = more ? Math.min(...lacks) : Math.max(...lacks);
	const ks = lacks.flatMap((s, k) => (s === short ? [k] : []));
	range(ks[Math.floor(ks.length / 2)]! / 64);
	return { index, short, own, column: th.getBoundingClientRect().width, heading };
}

test('S6, the CI fix: a numeric heading pressed three times at one point at the end of its box’s scroll, a column the arrow widens by a fraction of a pixel, keeps its words and every other column in place, but for its own column’s growth by its arrow (Nodes and Running combinations)', async ({
	page
}, info) => {
	test.skip(
		info.project.name === 'mobile',
		'the headings show from 640 px; a phone sorts by Sort by'
	);
	test.setTimeout(480_000);
	const moved: string[] = [];
	const pressAtEnd = async (
		label: string,
		box: Locator,
		name: string,
		growth: number,
		caseWidth = 0
	) => {
		await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
		await clearSort(box);
		const set = await box.evaluate(fractionAtEnd, [name, growth, caseWidth] as const);
		const what = `${label}, "${name}" widened ${growth} px${caseWidth ? `, its Case column ${caseWidth} px` : ''}`;
		// The setup: the column `growth` px short of its heading with the arrow, and the scroll
		// range unable to grow by all a sort adds (so on the code before the fix, 0.8 px of it).
		expect(set.index, `${what}: its heading`).toBeGreaterThan(0);
		expect(set.heading + 20 - set.column, `${what}: its column short of its heading`).toBe(growth);
		expect(set.short, `${what}: what the scroll range lacks`).toBeGreaterThan(0);
		const place = await box.evaluate(placeHeading, set.index);
		expect(place.placed && place.numeric, `${what}: placed whole in view`).toBe(true);
		const end = await box.evaluate((el) => {
			const b = el as HTMLElement;
			return b.scrollWidth - b.clientWidth - b.scrollLeft;
		});
		expect(end, `${what}: the box at the end of its scroll`).toBe(0);
		await frames(page);
		const before = await box.evaluate(readPress, set.index);
		expect(before.hit, `${what}: its button's centre its own`).toBe(true);
		const button = box.locator('thead button[data-sort-key]').nth(set.index);
		const b = (await button.boundingBox())!;
		for (const sort of ['ascending', 'descending', null]) {
			await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
			await frames(page);
			const after = await box.evaluate(readPress, set.index);
			const at = `${what}, pressed to ${sort ?? 'clear'}`;
			if (after.sort !== sort) {
				moved.push(`${at}: aria-sort ${after.sort}`);
				break;
			}
			// The setup's arrow and gap: the button 20 px wider while sorted; the Case column as set.
			const grew = (await button.boundingBox())!.width - b.width;
			expect(grew, `${at}: the button's growth`).toBe(sort ? 20 : 0);
			const caseCell = after.cells['Case'];
			if (caseWidth && sort) {
				expect(caseCell![1] - caseCell![0], `${at}: the Case column`).toBe(caseWidth);
			}
			moved.push(...pressMoves(before, after, at));
			if (!after.whole) moved.push(`${at}: the button not whole in the box's view`);
		}
		await clearSort(box);
		await box.evaluate((el) => {
			delete (el as HTMLElement).dataset.fraction;
			document.getElementById('fraction-at-end')?.remove();
		});
	};

	await open(page, exampleProject('gravity-branch')!);
	await solveConverged(page);
	await showPane(page, 'Results');
	const nodes = (await resultsView(page, 'Nodes')).getByRole('table').first().locator('xpath=..');
	// CI's 0.8 px; 19.2 px, whose scroll range lacks 0.2 px of it; 19.8 px, 0.8 px of it. In 64ths.
	for (const growth of [51 / 64, 19 + 13 / 64, 19 + 51 / 64]) {
		await pressAtEnd('Nodes', nodes, 'HGL', growth);
	}

	// A sort that flattens Running combinations' cases adds the Case column before the heading:
	// 208.6 px of it and 0.2 of the arrow's, together 0.8 px past a whole pixel. Its last column,
	// "Inside curve data" (14 rem at least), hidden by Fields, so a numeric heading can lie whole
	// at the end of the box's scroll: "Shaft power", the one before "NPSH margin".
	await condenser(page);
	const combinations = (await pumpsTab(page))
		.getByRole('region', { name: /^Pumps together/ })
		.locator('[data-running-combinations]');
	await combinations.getByRole('button', { name: /^Fields/ }).click();
	await combinations.getByRole('checkbox', { name: 'Inside curve data' }).uncheck();
	await page.keyboard.press('Escape');
	await pressAtEnd(
		'Running combinations',
		combinations.getByRole('region'),
		'Shaft power',
		13 / 64,
		208 + 38 / 64
	);
	expect.soft(moved, 'what a press at the end of the box’s scroll moved').toEqual([]);
});

/**
 * A sort a fraction of a pixel wider than its table unsorted, pressed at the end of its box's
 * scroll (S6, the CI fix's review CIFIX-1, TEST-CI-1): the CI fix held a press's column the rest
 * of a pixel so the table changed by whole pixels, but only on a press that left its column
 * sorted; new results and Flagged only dropped the hold (a case ticked under "Cases on this
 * chart" makes Running combinations' rows anew), and a sort the Summary's link set was never
 * held. With the knob the other way from the CI fix's test (the scroll range a whole pixel more
 * than a 13/64 px growth), the press to clear then narrowed the table by that fraction and the
 * range by a whole pixel, and at the end of the box's scroll its words and every other column
 * moved 0.8 px. Each press is read against the reading just before it (the event between moves
 * the table, not a press); a press to clear is a press to sort read backwards.
 */
test('S6, the CI fix’s review: a sort a fraction of a pixel wider than its table unsorted, its hold dropped by new results, Flagged only or a case ticked on the group chart, or never made by the Summary’s link, pressed to descending and to clear at one point at the end of its box’s scroll, keeps its words and every other column in place (Nodes and Running combinations; CIFIX-1, TEST-CI-1)', async ({
	page
}, info) => {
	test.skip(
		info.project.name === 'mobile',
		'the headings show from 640 px; a phone sorts by Sort by'
	);
	test.setTimeout(480_000);
	const growth = 13 / 64;
	const moved: string[] = [];
	/**
	 * Heading `index` placed by placeHeading (unsorted, room for its arrow) or, sorted, the box
	 * scrolled to its end; either way the box at the end of its scroll and the button whole in
	 * its view. The point a press there is made at: the button's centre.
	 */
	const atEnd = async (box: Locator, index: number, what: string, sorted: boolean) => {
		if (sorted) {
			await box.evaluate((el) => {
				const b = el as HTMLElement;
				b.scrollLeft = b.scrollWidth - b.clientWidth;
			});
		} else {
			const place = await box.evaluate(placeHeading, index);
			expect(place.placed && place.numeric, `${what}: placed whole in view`).toBe(true);
		}
		const end = await box.evaluate((el) => {
			const b = el as HTMLElement;
			return b.scrollWidth - b.clientWidth - b.scrollLeft;
		});
		expect(end, `${what}: the box at the end of its scroll`).toBe(0);
		await frames(page);
		expect((await box.evaluate(readPress, index)).whole, `${what}: its button whole`).toBe(true);
		const b = (await box.locator('thead button[data-sort-key]').nth(index).boundingBox())!;
		return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
	};
	const pressAt = async (
		box: Locator,
		index: number,
		at: { x: number; y: number },
		sort: string | null,
		what: string
	) => {
		const before = await box.evaluate(readPress, index);
		expect(before.hit, `${what}: its button's centre its own`).toBe(true);
		await page.mouse.click(at.x, at.y);
		await frames(page);
		const after = await box.evaluate(readPress, index);
		const pressed = `${what}, pressed to ${sort ?? 'clear'}`;
		if (after.sort !== sort) {
			moved.push(`${pressed}: aria-sort ${after.sort}`);
			return;
		}
		moved.push(
			...(sort
				? pressMoves(before, after, pressed)
				: pressMoves(after, before, `${pressed}, read back from after it`))
		);
		if (!after.whole) moved.push(`${pressed}: the button not whole in the box's view`);
	};
	/**
	 * Heading `name` at the end of box `box`'s scroll, sorted ascending by `sortBy` (a press at the
	 * button's centre, or the caller's: the Summary's link), the event `between` (if any), then
	 * pressed to descending and to clear at one point, the box placed at its end again first. The
	 * event leaves the sort a fraction of a pixel wider than the table unsorted, nothing held.
	 */
	const sortedThenPressed = async (
		label: string,
		box: Locator,
		name: string,
		caseWidth: number,
		sortBy: (() => Promise<void>) | null,
		between: (() => Promise<void>) | null
	) => {
		await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
		await clearSort(box);
		const set = await box.evaluate(fractionAtEnd, [name, growth, caseWidth, true] as const);
		const what = `${label}, "${name}" widened 13/64 px${caseWidth ? `, its Case column ${caseWidth} px` : ''}`;
		expect(set.index, `${what}: its heading`).toBeGreaterThan(0);
		expect(set.heading + 20 - set.column, `${what}: its column short of its heading`).toBe(growth);
		expect(set.short, `${what}: the scroll range gains more than the sort adds`).toBeLessThan(0);
		if (sortBy) await sortBy();
		else await pressAt(box, set.index, await atEnd(box, set.index, what, false), 'ascending', what);
		await expect(box.locator('thead th[aria-sort]'), `${what}: sorted`).toHaveAttribute(
			'aria-sort',
			'ascending'
		);
		if (between) await between();
		await expect(box, `${what}: its styles kept`).toHaveAttribute('data-fraction', '');
		await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
		const at = await atEnd(box, set.index, `${what}, sorted`, true);
		await expect(box.locator('thead th[aria-sort]'), `${what}: still sorted`).toHaveAttribute(
			'aria-sort',
			'ascending'
		);
		expect(
			await box.locator('thead th[style*="min-width"]').count(),
			`${what}: nothing held before the presses`
		).toBe(0);
		await pressAt(box, set.index, at, 'descending', what);
		await pressAt(box, set.index, at, null, what);
		// The hold the clear may leave dropped, by a sort by name and its clear.
		await box
			.locator('thead button[data-sort-key]')
			.first()
			.evaluate((b) => (b as HTMLElement).click());
		await clearSort(box);
		await box.evaluate((el) => {
			delete (el as HTMLElement).dataset.fraction;
			document.getElementById('fraction-at-end')?.remove();
		});
	};

	await open(page, exampleProject('gravity-branch')!);
	await solveConverged(page);
	await showPane(page, 'Results');
	const nodesView = await resultsView(page, 'Nodes');
	const nodes = nodesView.getByRole('table').first().locator('xpath=..');
	// New results while sorted: the header's Solve.
	await sortedThenPressed('Nodes', nodes, 'HGL', 0, null, async () => {
		await solveConverged(page);
		await frames(page);
	});
	// The Summary's link, "Nodes, lowest first", sorts by "Pressure": the columns after "Dynamic
	// pressure" hidden by Fields and "Elevation" 400 px wide, so "Pressure" lies at the end of the
	// box's scroll.
	await nodesView.getByRole('button', { name: /^Fields/ }).click();
	for (const field of [/^Total pressure/, /^Absolute pressure/, /^Velocity/, /^HGL/, /^EGL/]) {
		await nodesView.getByRole('checkbox', { name: field }).uncheck();
	}
	await page.keyboard.press('Escape');
	await nodes.evaluate(() => {
		const pad = document.createElement('style');
		pad.id = 'elevation-wide';
		pad.textContent = 'td[data-label="Elevation (m)"] { min-width: 400px; }';
		document.head.append(pad);
	});
	await sortedThenPressed(
		'Nodes',
		nodes,
		'Pressure',
		0,
		async () => {
			const summary = await resultsView(page, 'Summary');
			await summary.getByRole('button', { name: 'Nodes, lowest first' }).click();
			await expect(nodesView).toBeVisible();
			await frames(page);
		},
		null
	);
	await nodes.evaluate(() => document.getElementById('elevation-wide')?.remove());

	// Running combinations, "Shaft power" with "Inside curve data" hidden, as in the CI fix's test:
	// a sort adds a 208 px Case column, so the table grows 208 + 13/64 px and the range 209.
	await condenser(page);
	const card = (await pumpsTab(page)).getByRole('region', { name: /^Pumps together/ });
	const combinations = card.locator('[data-running-combinations]');
	await combinations.getByRole('button', { name: /^Fields/ }).click();
	await combinations.getByRole('checkbox', { name: 'Inside curve data' }).uncheck();
	await page.keyboard.press('Escape');
	const box = combinations.getByRole('region');
	const only = combinations.getByRole('checkbox', { name: /^Flagged only/ });
	await sortedThenPressed('Running combinations', box, 'Shaft power', 208, null, async () => {
		await only.check();
		await frames(page);
		await only.uncheck();
		await frames(page);
	});
	const chartCases = card.getByRole('group', { name: 'Cases on this chart' }).getByRole('checkbox');
	expect(await chartCases.count(), 'cases under "Cases on this chart"').toBeGreaterThan(1);
	await sortedThenPressed('Running combinations', box, 'Shaft power', 208, null, async () => {
		const last = chartCases.last();
		const ticked = await last.isChecked();
		await last.setChecked(!ticked);
		await settle(page);
		await last.setChecked(ticked);
		await settle(page);
	});
	expect.soft(moved, 'what a press at the end of the box’s scroll moved').toEqual([]);
});

/**
 * A press moves nothing up or down (S6, the CI fix's review PRE-1; ui-guide, a press moves nothing
 * under the pointer): a numeric heading's arrow sits on its words' left (its button's row
 * reversed), and a browser takes an inline flex box's baseline from its first item along the
 * line, so the sorted heading's button sat on its arrow's foot, 3 px of the line's strut below
 * it, and the heading row grew 53 to 56 px; the rows under it moved down 3 px, and the Results
 * pane, anchored on them, scrolled 3 px to follow, moving the heading under the pointer (Running
 * combinations with its box's top just under the pinned nav, a band of about 40 px). Here each
 * of the Pumps tab's tables keeps its heading row's height through three presses of each numeric
 * heading, and Running combinations, its box's top at each of five places just under the pinned
 * nav, keeps the pane's scroll and the heading's top.
 */
test('S6, the CI fix’s review: a numeric heading pressed three times at one point moves nothing up or down: its heading row keeps its height, and the Results pane keeps its scroll with Running combinations just under the pinned nav (the Pumps tab’s three tables; PRE-1)', async ({
	page
}, info) => {
	test.skip(
		info.project.name === 'mobile',
		'the headings show from 640 px; a phone sorts by Sort by'
	);
	test.setTimeout(480_000);
	const moved: string[] = [];
	/** The heading row's height, the pane's scroll, and heading `i`'s button's top and centre. */
	const readUpright = (el: Element, i: number) => {
		const button = el.querySelectorAll<HTMLElement>('thead button[data-sort-key]')[i]!;
		const b = button.getBoundingClientRect();
		let pane: HTMLElement | null = el.parentElement;
		while (pane && !/(auto|scroll)/.test(getComputedStyle(pane).overflowY)) {
			pane = pane.parentElement;
		}
		return {
			row: el.querySelector('thead tr')!.getBoundingClientRect().height,
			pane: pane!.scrollTop,
			top: b.top,
			x: b.left + b.width / 2,
			y: b.top + b.height / 2,
			numeric: button.classList.contains('flex-row-reverse'),
			name: (button.textContent ?? '').replace(/\s+/g, ' ').trim(),
			sort: button.closest('th')!.getAttribute('aria-sort')
		};
	};
	const pressUpright = async (label: string, box: Locator, i: number) => {
		const before = await box.evaluate(readUpright, i);
		if (!before.numeric) return 0;
		for (const sort of ['ascending', 'descending', null]) {
			await page.mouse.click(before.x, before.y);
			await frames(page);
			const after = await box.evaluate(readUpright, i);
			const what = `${label}, "${before.name}" pressed to ${sort ?? 'clear'}`;
			if (after.sort !== sort) {
				moved.push(`${what}: aria-sort ${after.sort}`);
				break;
			}
			for (const [part, then, now] of [
				['its heading row grew', before.row, after.row],
				['the pane scrolled down', before.pane, after.pane],
				['its button moved down', before.top, after.top]
			] as const) {
				if (Math.abs(now - then) > 0.5)
					moved.push(`${what}: ${part} ${(now - then).toFixed(1)} px`);
			}
		}
		await clearSort(box);
		return 1;
	};

	await condenser(page);
	const tab = await pumpsTab(page);
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const combinations = card.locator('[data-running-combinations]').getByRole('region');
	const tables: [string, Locator][] = [
		['Results per pump', tab.getByRole('table', { name: 'Results per pump' }).locator('xpath=..')],
		['the group table', card.locator('[data-group-table]').getByRole('region')],
		['Running combinations', combinations]
	];
	const pressed: Record<string, number> = {};
	for (const [label, box] of tables) {
		await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
		await clearSort(box);
		pressed[label] = 0;
		const n = await box.locator('thead button[data-sort-key]').count();
		for (let i = 1; i < n; i++) {
			const place = await box.evaluate(placeHeading, i);
			if (!place.numeric || !place.placed) continue;
			await frames(page);
			pressed[label] += await pressUpright(label, box, i);
		}
	}
	// Running combinations' box, its top at the pinned nav's foot and 3, 6, 9 and 12 px under it,
	// at its scroll's start, each numeric heading whole in view there pressed.
	await combinations.evaluate((el) => el.scrollIntoView({ block: 'center' }));
	const under: Record<number, number> = {};
	for (const gap of [0, 3, 6, 9, 12]) {
		under[gap] = 0;
		const nav = await page.evaluate(readNav);
		expect(nav.pinned, 'the section nav pinned').toBe(true);
		await combinations.evaluate((el, top) => {
			let pane: HTMLElement | null = el.parentElement;
			while (pane && !/(auto|scroll)/.test(getComputedStyle(pane).overflowY)) {
				pane = pane.parentElement;
			}
			pane!.scrollTop += el.getBoundingClientRect().top - top;
			(el as HTMLElement).scrollLeft = 0;
		}, nav.navBottom + gap);
		await frames(page);
		const n = await combinations.locator('thead button[data-sort-key]').count();
		for (let i = 1; i < n; i++) {
			const whole = await combinations.evaluate((el, k) => {
				const box = el as HTMLElement;
				const r = box.querySelectorAll('thead button[data-sort-key]')[k]!.getBoundingClientRect();
				const fixed = box.querySelector('thead th')!.getBoundingClientRect().right;
				const right = box.getBoundingClientRect().left + box.clientLeft + box.clientWidth;
				return box.scrollLeft === 0 && r.left >= fixed + 24 && r.right <= right - 8;
			}, i);
			if (!whole) continue;
			under[gap] += await pressUpright(
				`Running combinations ${gap} px under the nav`,
				combinations,
				i
			);
		}
	}
	expect.soft(moved, 'what a press moved up or down').toEqual([]);
	for (const [label, n] of Object.entries(pressed)) {
		expect.soft(n, `${label}: numeric headings pressed`).toBeGreaterThanOrEqual(2);
	}
	for (const [gap, n] of Object.entries(under)) {
		expect
			.soft(n, `Running combinations ${gap} px under the nav: headings pressed`)
			.toBeGreaterThan(0);
	}
});

test.describe('a touch screen from 640 px', () => {
	test.use({ hasTouch: true });

	test('S6, the second check: a tap on a heading with 6 px of it showing, beside the sticky column or at the box’s right edge, sorts by it and moves nothing under the finger (Links; S6-FIX-2)', async ({
		page
	}, info) => {
		test.skip(
			info.project.name === 'mobile',
			'the headings show from 640 px; a phone sorts by Sort by'
		);
		test.setTimeout(240_000);
		await open(page, exampleProject('gravity-branch')!);
		await solveConverged(page);
		await showPane(page, 'Results');
		const links = await resultsView(page, 'Links');
		const box = links
			.getByRole('table', { name: 'Results per pipe connection' })
			.locator('xpath=..');
		await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
		const n = await box.locator('thead button[data-sort-key]').count();
		const lost: string[] = [];
		let tapped = 0;
		for (let i = 1; i < n; i++) {
			for (const edge of ['left', 'right'] as const) {
				await clearSort(box);
				await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
				// 6 px of the button in view, right of the sticky column or left of the box's edge.
				const p = await box.evaluate(
					(el, [i, edge]) => {
						const b = el as HTMLElement;
						const button = b.querySelectorAll<HTMLElement>('thead button[data-sort-key]')[
							i as number
						]!;
						b.scrollLeft = 0;
						const fixed = b.querySelector('thead th')!.getBoundingClientRect().right;
						const right = b.getBoundingClientRect().left + b.clientLeft + b.clientWidth;
						const r0 = button.getBoundingClientRect();
						const want = edge === 'left' ? r0.right - fixed - 6 : r0.left + 6 - right;
						if (want < 0 || want > b.scrollWidth - b.clientWidth) return null;
						b.scrollLeft = want;
						const r = button.getBoundingClientRect();
						const [lo, hi] = [Math.max(fixed, r.left), Math.min(right, r.right)];
						return {
							name: (button.textContent ?? '').replace(/\s+/g, ' ').trim(),
							shown: hi - lo,
							x: (lo + hi) / 2,
							y: r.top + r.height / 2
						};
					},
					[i, edge] as const
				);
				if (!p) continue;
				await frames(page);
				const before = await box.evaluate(readPress, i);
				tapped++;
				await page.touchscreen.tap(p.x, p.y);
				await frames(page);
				await frames(page);
				const after = await box.evaluate(readPress, i);
				const what = `"${p.name}", ${p.shown.toFixed(1)} px of it showing at the ${edge}`;
				if (after.sort !== 'ascending') lost.push(`${what}: aria-sort ${after.sort}`);
				const words = after.words - before.words;
				if (Math.abs(words) > 0.5) lost.push(`${what}: its words moved ${words.toFixed(1)} px`);
			}
		}
		await clearSort(box);
		expect.soft(lost, 'a tap on a heading partly in view').toEqual([]);
		// Each side tapped: Links' six headings after the name give both at 1280×800.
		expect(tapped).toBeGreaterThanOrEqual(6);
	});
});

// ---- S5 review: a measure no case gives, the trace's focus, a stale group on a phone ----------

/**
 * The lineups project with Pump P3 on a copy of its curve without efficiencies and Pump P4 on a
 * copy without NPSHr (synthetic), so the extremes hold "no case gives one" for P3's shaft power and
 * P4's NPSH margin (§5.3: a pump with no NPSH data, a measure no case gives).
 */
function lineupsWithoutData(): Project {
	const project = projectOf('lineups');
	const library = project.pumpLibrary!;
	const curve = library.find((c) => c.id === 'PC-A')!;
	library.push(
		{
			...structuredClone(curve),
			id: 'PC-A-NOEFF',
			name: 'Curve PC-A, no efficiencies',
			efficiencyCurve: null
		},
		{ ...structuredClone(curve), id: 'PC-A-NONPSH', name: 'Curve PC-A, no NPSHr', npshrCurve: null }
	);
	for (const [id, curveId] of [
		['P3', 'PC-A-NOEFF'],
		['P4', 'PC-A-NONPSH']
	] as const) {
		const pump = project.components.find((c) => c.id === id)!;
		if (pump.type === 'pump') pump.curveId = curveId;
	}
	return project;
}

/**
 * Open a pump's trace from `opener` by the keyboard, close it by Escape (or its Close button) and
 * expect the focus back on the opener (WCAG 2.4.3; S5 review A11Y-S5-1): on a phone the trace is a
 * dialog, which gives it back; at 1280×800 a panel over the results, inert under it until it goes.
 */
async function traceGivesFocusBack(
	page: Page,
	opener: Locator,
	name: string,
	how: 'Escape' | 'Close',
	where: string
) {
	await opener.scrollIntoViewIfNeeded();
	await opener.focus();
	await page.keyboard.press('Enter');
	const trace = traceOf(page, name);
	await expect(trace, `the trace of ${name} open, ${where}`).toBeVisible();
	if (how === 'Escape') await page.keyboard.press('Escape');
	else await trace.getByRole('button', { name: 'Close', exact: true }).click();
	await expect(traceOf(page, name)).toBeHidden();
	await expect.soft(opener, `the focus back on its opener after ${how}, ${where}`).toBeFocused();
}

/**
 * A stale group in Running combinations as painted (§5.3 Invalid and stale: stale groups amber;
 * §5.5: below 640 px only the layout changes; S5 review LAYOUT-3): each of its cells' background,
 * its own or else the nearest painted one inside its group (its row's, its group's), against the
 * ambers the card paints (amber-50, and at 60 %); in the list one tone over the whole block.
 */
function readStaleGroup() {
	const box = document.querySelector('[data-pumps-together] [data-running-combinations]');
	const tbody = [...(box?.querySelectorAll('table > tbody') ?? [])].find((t) =>
		(t.querySelector('th[scope="rowgroup"]')?.textContent ?? '').includes('(out of date)')
	);
	if (!tbody) return null;
	const clear = (c: string) => c === 'rgba(0, 0, 0, 0)' || c === 'transparent' || /\/ 0\)$/.test(c);
	const painted = (el: Element) => {
		for (let e: Element | null = el; e && e !== tbody.parentElement; e = e.parentElement) {
			const bg = getComputedStyle(e).backgroundColor;
			if (!clear(bg)) return bg;
		}
		return 'none';
	};
	/** The ambers the card paints, as computed: amber-50 and amber-50 at 60 %. */
	const ambers = ['bg-amber-50', 'bg-amber-50/60'].map((name) => {
		const probe = document.createElement('div');
		probe.className = name;
		document.body.append(probe);
		const bg = getComputedStyle(probe).backgroundColor;
		probe.remove();
		return bg;
	});
	const cells = [...tbody.querySelectorAll(':scope > tr > th, :scope > tr > td')]
		.filter((cell) => {
			const r = cell.getBoundingClientRect();
			return cell.checkVisibility() && r.width > 1 && r.height > 1;
		})
		.map((cell) => ({
			what: (cell.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 30),
			bg: painted(cell)
		}));
	return {
		heading: (tbody.querySelector('th[scope="rowgroup"] > span')?.textContent ?? '').trim(),
		ambers,
		cells: cells.map((c) => ({ ...c, amber: ambers.includes(c.bg) })),
		tones: [...new Set(cells.map((c) => c.bg))]
	};
}

test('S5 review: the extremes list’s names with a measure no case gives, each value on its line; the trace gives the focus back to its opener; the duties’ words apart from their column’s; a stale group amber whole on a phone (§5.3, §5.5, §7; A11Y-S5-1, EXT-1, EXT-2, LAYOUT-1, LAYOUT-3)', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	const counter = solveCounter(page);
	await open(page, lineupsWithoutData());
	await solveAll(page, counter, 9);
	const tab = await pumpsTab(page);
	const card = await openCard(page, tab);
	const size = sizeOf(page);

	// The trace's openers: Running combinations' names (S5), the Station's group table's (S3) and
	// Results per pump's (the shared ResultsTable), each closed by Escape, one by Close too.
	// The tables' boxes (regions only while they overflow since S7, §9 S7).
	const combos = card.getByRole('table', { name: 'Running combinations' }).locator('..');
	const station = card.getByRole('table', { name: /^The pumps in the group/ }).locator('..');
	const perPump = tab.getByRole('table', { name: 'Results per pump' });
	await expect(combos.getByRole('button', { name: 'Pump P2', exact: true })).toHaveCount(1);
	await traceGivesFocusBack(
		page,
		combos.getByRole('button', { name: 'Pump P2', exact: true }),
		'Pump P2',
		'Escape',
		`Running combinations at ${size}`
	);
	await traceGivesFocusBack(
		page,
		combos.getByRole('button', { name: 'Pump P3', exact: true }),
		'Pump P3',
		'Close',
		`Running combinations at ${size}`
	);
	await traceGivesFocusBack(
		page,
		station.getByRole('button', { name: 'Pump P2', exact: true }),
		'Pump P2',
		'Escape',
		`the group table at ${size}`
	);
	await traceGivesFocusBack(
		page,
		perPump.getByRole('button', { name: /^Pump P2\b/ }),
		'Pump P2',
		'Escape',
		`Results per pump at ${size}`
	);

	// "Other cases' station duties" drawn and the group chart's data table shown, so their list is
	// read below 640 px (combinationsPart: a cell of words in a number's style; LAYOUT-1).
	await card.getByRole('checkbox', { name: "Also show the other cases' station duties" }).check();
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	await expect(card.getByRole('table', { name: "Other cases' station duties" })).toBeVisible({
		timeout: 240_000
	});
	await settle(page, 2500);

	// "no case gives one" in P3's shaft power and P4's NPSH margin; the extremes' names and lines
	// at each size (extremesPart: in the list, each cell's name its header, a space, its words).
	const sizes =
		info.project.name === 'mobile'
			? [page.viewportSize()!, { width: 320, height: 640 }]
			: [page.viewportSize()!];
	const viewport = page.viewportSize()!;
	for (const s of sizes) {
		await page.setViewportSize(s);
		await settle(page, 1000);
		const where = `no data at ${sizeOf(page)}`;
		const m = await page.evaluate(readExtremes);
		const none = m?.rows.flatMap((r) =>
			r.cells.filter((c) => c.text === 'no case gives one').map((c) => `${r.name}, ${c.label}`)
		);
		expect
			.soft(none, `the measures no case gives, ${where}`)
			.toEqual(['Pump P3, Largest shaft power', 'Pump P4, Smallest NPSH margin']);
		await extremesPart(page, '', where);
		await combinationsPart(page, '', where, null);
	}
	await page.setViewportSize(viewport);
	await settle(page, 1000);

	// A stale case: "Delivery tank 5 m higher" shown and its tank's level edited, then the base
	// case shown again (only that case's results go out of date).
	await chooseCase(page, 'Delivery tank 5 m higher (1 change)');
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	const jump = page.getByRole('dialog', { name: 'Jump to a component' });
	const filter = jump.getByRole('searchbox', { name: 'Filter' });
	if (await filter.count()) await filter.fill('Reservoir R2');
	await jump.getByRole('button', { name: /^Reservoir R2/ }).click();
	await expect(jump).toBeHidden();
	await setNumber(buildPane(page), /^Liquid level/, '8');
	await chooseCase(page, 'Base case');
	await showPane(page, 'Results');
	await settle(page, 2000);
	for (const s of sizes) {
		await page.setViewportSize(s);
		await settle(page, 1000);
		const where = `a stale case at ${sizeOf(page)}`;
		const g = await page.evaluate(readStaleGroup);
		expect(g, `a group out of date, ${where}`).not.toBeNull();
		console.log(`${where}: "${g!.heading}", tones ${JSON.stringify(g!.tones)}`);
		expect.soft(g!.heading).toBe('Delivery tank 5 m higher (out of date)');
		for (const cell of g!.cells) {
			expect.soft(cell.amber, `"${cell.what}" amber (${cell.bg}), ${where}`).toBe(true);
		}
		// On a phone one tone over the whole block, as one group (no stripes).
		if (s.width < 640) {
			expect.soft(g!.tones, `the stale block's tones, ${where}`).toHaveLength(1);
		}
		await combinationsPart(page, '', where, null);
	}
	await page.setViewportSize(viewport);
});

// ---- S4: Add cases in one structure (§5.3, §9 S4, §10 S4) --------------------------------------

/** A second 40-character unbroken pump name: with two, the lineups' names write ids (§6.2). */
const LONG_PUMP_2 = 'CondenserWaterPrimaryLoopPumpNorthSide02';
const NOW_TICKED = "Now ticked: “Also show the other cases' station duties” (Group chart).";

test('Add cases in one structure: the plan, its fold and its new lines, one Solve all and the focus kept on it after Add, long names inside the frame at each size; axe clean with the plan and the stop order open (§5.3, §9 S4, §10 S4)', async ({
	page,
	isMobile
}) => {
	test.setTimeout(420_000);
	// The lineups without their scenarios, two pumps renamed past the names' budget.
	const project = projectOf('lineups');
	delete project.scenarios;
	project.components.find((c) => c.id === 'P1')!.name = LONG_PUMP;
	project.components.find((c) => c.id === 'P2')!.name = LONG_PUMP_2;
	const counter = solveCounter(page);
	await open(page, project);
	await solveConverged(page);
	const tab = await pumpsTab(page);
	const card = await openCard(page, tab);
	const toggle = card.getByRole('button', { name: /^Pumps together/ });
	const block = card.getByRole('region', { name: 'Add cases' });
	const plan = block.locator('[data-lineup-plan]');
	const summary = plan.locator(':scope > summary');
	const ids = block.locator('[data-lineup-ids]');
	const solveAlls = block.getByRole('button', { name: /^Solve all/ });

	// 1. Cases to add: the plan drawn open, its summary saying what it holds; the names write ids,
	// so it says which pump each id is, in the stop order.
	await expect(plan).toHaveAttribute('open', '');
	await expect(summary).toHaveText('The plan: 3 cases by number running: 3 to add');
	await expect(block.getByRole('list', { name: 'Cases:' }).getByRole('listitem')).toHaveText([
		'3 of 4 running (P4 off)',
		'2 of 4 running (P3, P4 off)',
		'1 of 4 running (P2, P3, P4 off)'
	]);
	await expect(ids).toHaveText(
		`In the names, P4 is Pump P4, P3 is Pump P3, P2 is ${LONG_PUMP_2} and P1 is ${LONG_PUMP}.`
	);
	await expect(ids).toBeVisible();
	// On screen as text, not sr-only's 1 px box, which toBeVisible accepts (S4 review MUT-02): the
	// id line, the tag and the summary's clause.
	expect.soft(await seenLine(ids), 'the id line on screen').toBe(true);
	expect
		.soft(await seenLine(block.locator('[data-add-cases-tag]')), 'the tag on screen')
		.toBe(true);
	expect
		.soft(await seenLine(summary.locator(':scope > span > span')), "the summary's clause on screen")
		.toBe(true);
	await expect(solveAlls).toHaveCount(1);
	// The stop order opened too: every line the block draws ends inside its frame, the long names
	// in the sentence, the stop order and the id line among them.
	await block.locator('[data-stop-order] > summary').click();
	await expect(block.getByRole('list', { name: 'Stop order' })).toBeVisible();
	await expect(block.getByRole('list', { name: 'Stop order' })).toContainText(LONG_PUMP);
	const viewport = page.viewportSize()!;
	const sizes = isMobile ? [viewport, { width: 320, height: 640 }] : [viewport];
	for (const size of sizes) {
		await page.setViewportSize(size);
		await settle(page, 1000);
		const where = `Add cases with long names at ${sizeOf(page)}`;
		const m = await block.evaluate(readAddCases);
		console.log(
			`${where}: ${m.height} px, folded ${m.folded?.height} px; past ${JSON.stringify(m.past)}`
		);
		expect.soft(m.past, `lines past Add cases' frame, ${where}`).toEqual([]);
		expect.soft(await cutInCard(page), `names cut short in the card, ${where}`).toEqual([]);
		expect.soft(m.solveAll, `Solve all in the block, ${where}`).toBe(1);
		expect.soft(m.tagBesideH4, `the tag beside the h4, ${where}`).toBe(true);
		expect.soft(m.segmentsOneRow, `the segments one row, ${where}`).toBe(true);
		expect.soft(m.pad.foot, `the frame's padding at its foot, ${where}`).toBe(m.pad.head);
	}
	await page.setViewportSize(viewport);
	await settle(page, 1000);
	// axe over the whole tab with the plan and the stop order open (every disclosure is).
	await axeClean(page, `Add cases, the plan and the stop order open, at ${sizeOf(page)}`);

	// 2. Add, by the keyboard on desktop and a tap on a phone: the focus on the block's Solve all
	// (D24 §7.8), "Now ticked" on screen and in the block's polite line, which the focus would not
	// pass; the plan as the user left it, open; the refusal naming the cases made.
	const add = block.getByRole('button', { name: 'Add 3 cases' });
	if (isMobile) {
		await add.tap();
	} else {
		await add.focus();
		await page.keyboard.press('Enter');
	}
	const solveAll = block.getByRole('button', { name: 'Solve all (3)' });
	await expect(solveAll).toBeFocused();
	await expect(block.locator('[data-now-ticked]')).toHaveText(NOW_TICKED);
	await expect(block.locator('[data-now-ticked]')).toBeVisible();
	expect
		.soft(await seenLine(block.locator('[data-now-ticked]')), '"Now ticked" on screen')
		.toBe(true);
	await expect(block.locator('[data-stop-status]')).toHaveText(NOW_TICKED);
	await expect(block.locator('[data-stop-status]')).toHaveAttribute('aria-live', 'polite');
	await expect(
		card.getByRole('checkbox', { name: "Also show the other cases' station duties" })
	).toBeChecked();
	await expect(plan).toHaveAttribute('open', '');
	await expect(summary).toHaveText('The plan: 3 cases by number running: all 3 made');
	const refusal = block.getByText(
		'Every case by number running already exists: «3 of 4 running (P4 off)», «2 of 4 running (P3, P4 off)» and «1 of 4 running (P2, P3, P4 off)».',
		{ exact: true }
	);
	await expect(refusal).toBeVisible();
	expect.soft(await seenLine(refusal), 'the refusal on screen').toBe(true);
	await expect(solveAlls).toHaveCount(1);

	// 3. Solve all: the three cases solved; the button keeps the focus, in place, and its reason,
	// which lasts, is then on screen and its description (§5.3 item 5).
	const start = counter.n;
	if (isMobile) await solveAll.tap();
	else await page.keyboard.press('Enter');
	await expect.poll(() => counter.n - start, { timeout: 180_000 }).toBe(3);
	const after = block.getByRole('button', { name: 'Solve all', exact: true });
	await expect(after).toHaveAttribute('aria-disabled', 'true', { timeout: 120_000 });
	await expect(after).toBeFocused();
	const reason = block.getByText("Every case's results are current.", { exact: true });
	await expect(reason).toBeVisible();
	expect.soft(await seenLine(reason), "Solve all's lasting reason on screen").toBe(true);
	await expect(after).toHaveAccessibleDescription("Every case's results are current.");
	await expect(solveAlls).toHaveCount(1);
	await settle(page);

	// 4. The card closed and opened: the block is drawn again with every case made, so the plan is
	// folded (§5.3 The fold): the segments, its summary, the row, the refusal, the reason and the
	// table button.
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'true');
	await settle(page);
	await expect(plan).not.toHaveAttribute('open');
	await expect(summary).toHaveText('The plan: 3 cases by number running: all 3 made');
	await expect(ids).toBeHidden();
	await expect(refusal).toBeVisible();
	await expect(reason).toBeVisible();
	expect.soft(await seenLine(refusal), 'the refusal on screen, folded').toBe(true);
	expect.soft(await seenLine(reason), "Solve all's lasting reason on screen, folded").toBe(true);
	expect
		.soft(
			await seenLine(summary.locator(':scope > span > span')),
			"the summary's clause on screen, folded"
		)
		.toBe(true);
	await expect(block.getByRole('radiogroup', { name: 'Cases to add' })).toBeVisible();
	await expect(block.getByRole('button', { name: 'Pump lineups table…' })).toBeVisible();
	const folded = await block.evaluate(readAddCases);
	console.log(`Add cases folded at ${sizeOf(page)}: ${folded.height} px`);
	expect.soft(folded.planOpen, 'the plan drawn folded').toBe(false);
	expect.soft(folded.past, `lines past Add cases' frame, folded`).toEqual([]);

	// 5. Another preset: cases remain, so the plan opens itself; the focus stays on the segment
	// chosen (one structure: no control is drawn again elsewhere).
	const each = block.getByRole('radio', { name: 'Each pump off' });
	if (isMobile) {
		await each.tap();
	} else {
		await block.getByRole('radio', { name: 'By number running' }).focus();
		await page.keyboard.press('ArrowRight');
	}
	await expect(each).toBeChecked();
	await expect(each).toBeFocused();
	await expect(plan).toHaveAttribute('open', '');
	// S1, "3 of 4 running (P4 off)", is the same case as Each pump off's P4 off (D24 §7.4).
	await expect(summary).toHaveText('The plan: 4 cases with each pump off: 3 to add');
	await expect(ids).toHaveCount(0);
	await expect(solveAlls).toHaveCount(1);
	await noSidewaysScroll(page, `Add cases, Each pump off, at ${sizeOf(page)}`);

	// 6. "Also show …" unticked, then an Add that ticks it again: the polite line is empty at the
	// press and its words come two frames later, so it is drawn empty before it speaks and the
	// words are said though the focus goes to Solve all (§5.3, §7 Live regions; S1's rule; S4
	// review AT-1, ADD-1). A frame counter and the line's changes, from here on.
	const box = card.getByRole('checkbox', { name: "Also show the other cases' station duties" });
	const status = block.locator('[data-stop-status]');
	await box.uncheck();
	await expect(box).not.toBeChecked();
	await expect(status).toHaveText('');
	await status.evaluate((line) => {
		const w = window as unknown as {
			__frame: number;
			__press: { frame: number; text: string } | null;
			__changes: { frame: number; text: string }[];
		};
		w.__frame = 0;
		w.__press = null;
		w.__changes = [];
		const step = () => {
			w.__frame++;
			requestAnimationFrame(step);
		};
		requestAnimationFrame(step);
		const text = () => (line.textContent ?? '').trim();
		document.addEventListener('click', () => (w.__press ??= { frame: w.__frame, text: text() }), {
			capture: true
		});
		new MutationObserver(() => w.__changes.push({ frame: w.__frame, text: text() })).observe(line, {
			subtree: true,
			childList: true,
			characterData: true
		});
	});
	const again = block.getByRole('button', { name: 'Add 3 cases' });
	if (isMobile) {
		await again.tap();
	} else {
		await again.focus();
		await page.keyboard.press('Enter');
	}
	await expect(block.getByRole('button', { name: /^Solve all/ })).toBeFocused();
	await expect(box).toBeChecked();
	await expect(block.locator('[data-now-ticked]')).toHaveText(NOW_TICKED);
	await expect(status).toHaveText(NOW_TICKED);
	const seen = await page.evaluate(() => {
		const w = window as unknown as {
			__press: { frame: number; text: string } | null;
			__changes: { frame: number; text: string }[];
		};
		return { press: w.__press, changes: w.__changes };
	});
	console.log(`Add cases' polite line after the second ticking Add: ${JSON.stringify(seen)}`);
	expect(seen.press, 'the press seen').not.toBeNull();
	expect.soft(seen.press!.text, 'the line empty at the press').toBe('');
	const spoke = seen.changes.find((c) => c.text === NOW_TICKED);
	expect(spoke, `the line said "${NOW_TICKED}"`).toBeDefined();
	expect
		.soft(spoke!.frame - seen.press!.frame, 'frames from the press to the words')
		.toBeGreaterThan(1);

	// 7. Unticked again: "Now ticked" goes from the screen and from the polite line, which no
	// longer says it (§5.3: the same sentence; S4 review W1, ADD-2).
	await box.uncheck();
	await expect(box).not.toBeChecked();
	await expect(block.locator('[data-now-ticked]')).toHaveCount(0);
	await expect(status).toHaveText('');
});

// ---- S7: the curve tables folded, the boxes measured, the choice remembered (§9 S7) -------------

/**
 * Each curve table's disclosure in `scope`: its caption, its summary, its rows, open or not, its
 * summary's words and count in sight, and on how many lines the count is drawn.
 */
function readFolds(scope: Element) {
	const squash = (t: string | null | undefined) => (t ?? '').replace(/\s+/g, ' ').trim();
	// In sight as text: a box of its own, no sr-only at or above it, 12 px at least.
	const inSight = (el: Element) => {
		const r = el.getBoundingClientRect();
		return (
			el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
			!el.closest('.sr-only') &&
			r.width > 1 &&
			r.height >= 12
		);
	};
	return [...scope.querySelectorAll<HTMLDetailsElement>('details[data-curve-table]')].map((d) => {
		const summary = d.querySelector(':scope > summary')!;
		const words = summary.querySelector(':scope > span')!;
		const count = words.querySelector(':scope > span')!;
		const table = d.querySelector('table')!;
		const caption = squash(table.querySelector('caption')?.textContent);
		// A column of a row, '—' where it has no value.
		const none = (column: number) =>
			[...table.querySelectorAll('tbody tr')].some(
				(tr) => squash(tr.querySelectorAll('td')[column]?.textContent) === '—'
			);
		return {
			caption,
			summary: squash(summary.textContent),
			// What its reason column holds (§9 S7): the pump chart's "Why no head", the group
			// system curve's rows without a rise, the group curve's points without a flow (S7
			// review STRUCT-2).
			reasons:
				[...table.querySelectorAll('thead th')].some(
					(th) => squash(th.textContent) === 'Why no head'
				) ||
				(caption.startsWith('Group system curve') && none(1)) ||
				(caption.startsWith('Group curve') && none(1)),
			rows: table.querySelectorAll('tbody tr').length,
			open: d.open,
			// The summary's words and its count in sight, each measured itself: the chevron keeps
			// the summary drawn without them (S7 review W2, MUT-SUMMARY-HIDDEN).
			seen: inSight(words) && inSight(count),
			// The count whole, "(42 points)" on one line (S7 review LAYOUT-4).
			countLines: count.getClientRects().length
		};
	});
}

test('S7: each curve table a disclosure “{caption} ({n} points)” in sight, open where its reasons have entries; a box a Tab stop only while it overflows, resized in the browser; each chart’s data table remembered after a reload (§9 S7, §5.7)', async ({
	page
}) => {
	test.setTimeout(300_000);
	await open(page, projectOf('fcv-outside'));
	await solveConverged(page);
	const tab = await pumpsTab(page);
	const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
	await expect(figure.locator('[data-pump-method]')).toBeVisible({ timeout: 60_000 });
	await figure.getByRole('button', { name: 'Show data table of the pump chart' }).click();
	const pumpFolds = await figure.evaluate(readFolds);
	console.log(`the pump chart's curve tables: ${JSON.stringify(pumpFolds)}`);
	expect(pumpFolds.map((f) => f.caption).slice(0, 2)).toEqual([
		'Pump curve at 100 % speed',
		'System curve'
	]);
	for (const f of pumpFolds) {
		expect(f.summary, f.caption).toBe(`${f.caption} (${f.rows} point${f.rows === 1 ? '' : 's'})`);
		expect(f.rows, f.caption).toBeGreaterThan(1);
		expect(f.seen, `"${f.summary}" in sight`).toBe(true);
		expect(f.countLines, `"${f.summary}": its count on one line`).toBe(1);
		// The chart drawn: open exactly where its Why no head column has entries.
		expect(f.open, `"${f.caption}" open`).toBe(f.reasons);
	}

	const card = await openCard(page, tab);
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	const data = card.locator('[data-group-data]');
	const groupFolds = await data.evaluate(readFolds);
	console.log(`the group chart's curve tables: ${JSON.stringify(groupFolds)}`);
	expect(groupFolds.map((f) => [f.caption, f.open, f.reasons])).toEqual([
		["Group curve (station's flow at each rise)", false, false],
		["Group system curve (rise the rest of the network needs at each station's flow)", true, true]
	]);
	for (const f of groupFolds) {
		expect(f.summary).toBe(`${f.caption} (${f.rows} points)`);
		expect(f.seen, `"${f.summary}" in sight`).toBe(true);
		expect(f.countLines, `"${f.summary}": its count on one line`).toBe(1);
	}
	// The rule with the curve tables at their defaults, most folded (§9 S7): only drawn boxes
	// that overflow are Tab stops.
	await scrollBoxesPart(page, '', `the curve tables at their defaults, ${sizeOf(page)}`);
	// The group system curve's reasons in sight, the note pointing to them answered.
	const reason = data
		.getByRole('table', { name: /^Group system curve/ })
		.getByRole('cell', { name: /^No steady state carries this flow/ })
		.first();
	expect(await seenLine(reason), 'a reason without a rise in sight').toBe(true);

	// Real boxes resized: the group curve's table is wider than its box (its member columns), so
	// it is a Tab stop and a region by its caption once its disclosure is open; folded away it is
	// neither, though the browser lays it out still; given room, it fits and is neither; back.
	const box = data.locator('details[data-curve-table="group-curve"] table').locator('..');
	const state = () =>
		box.evaluate((el) => ({
			tabindex: el.getAttribute('tabindex'),
			role: el.getAttribute('role'),
			sideways: el.scrollWidth > el.clientWidth + 1
		}));
	expect(await state()).toEqual({ tabindex: null, role: null, sideways: true });
	await openCurveTable(card, "Group curve (station's flow at each rise)");
	await expect.poll(state).toEqual({ tabindex: '0', role: 'region', sideways: true });
	await expect(
		data.getByRole('region', { name: "Group curve (station's flow at each rise)" })
	).toHaveCount(1);
	// Its right shadow drawn in its first rows, the box full height (S7 review LAYOUT-2).
	const shadow = await edgeShadow(page, box);
	console.log(`the group curve's right shadow in its first row, ${sizeOf(page)}: ${shadow}`);
	expect(shadow, 'the right shadow in the first row').toBeGreaterThan(15);
	// Its keyboard scroll: focused by Tab from its summary, → moves it sideways.
	await card.locator('details[data-curve-table="group-curve"] > summary').focus();
	await page.keyboard.press('Tab');
	await expect(box).toBeFocused();
	await page.keyboard.press('ArrowRight');
	await expect.poll(() => box.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
	await box.evaluate((el) => {
		el.style.maxWidth = 'none';
		el.style.width = `${el.scrollWidth + 400}px`;
	});
	// It fits while it holds the focus: no Tab stop, but still focusable and named, so the focus
	// stays on it rather than falling to the page (S7 review A11Y-1); once the focus leaves, it
	// is neither.
	await expect.poll(state).toEqual({ tabindex: '-1', role: 'region', sideways: false });
	await expect(box).toBeFocused();
	expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);
	await page.keyboard.press('Shift+Tab');
	await expect(card.locator('details[data-curve-table="group-curve"] > summary')).toBeFocused();
	await expect.poll(state).toEqual({ tabindex: null, role: null, sideways: false });
	await box.evaluate((el) => {
		el.style.maxWidth = '';
		el.style.width = '';
	});
	await expect.poll(state).toEqual({ tabindex: '0', role: 'region', sideways: true });
	// Down too: "Each pump's point" fits; held to 40 px high it overflows, and back.
	const points = data
		.getByRole('table', { name: "Each pump's point (flow through it)" })
		.locator('..');
	const pointsState = () =>
		points.evaluate((el) => ({
			tabindex: el.getAttribute('tabindex'),
			role: el.getAttribute('role'),
			down: el.scrollHeight > el.clientHeight + 1
		}));
	expect(await pointsState()).toEqual({ tabindex: null, role: null, down: false });
	await points.evaluate((el) => (el.style.maxHeight = '40px'));
	await expect.poll(pointsState).toEqual({ tabindex: '0', role: 'region', down: true });
	await expect(
		data.getByRole('region', { name: "Each pump's point (flow through it)" })
	).toHaveCount(1);
	await points.evaluate((el) => (el.style.maxHeight = ''));
	await expect.poll(pointsState).toEqual({ tabindex: null, role: null, down: false });

	// Both choices remembered in this browser: after a reload each chart's data table is shown.
	await page.reload();
	await solveConverged(page);
	const again = await pumpsTab(page);
	await expect(
		again.getByRole('button', { name: 'Hide data table of the pump chart' })
	).toHaveAttribute('aria-expanded', 'true', { timeout: 60_000 });
	const reopened = await openCard(page, again);
	await expect(
		reopened.getByRole('button', { name: 'Hide data table of the group chart' })
	).toHaveAttribute('aria-expanded', 'true');
	await expect(reopened.locator('[data-group-data]')).toBeVisible();
	// Hidden again, it stays hidden after the next reload.
	await reopened.getByRole('button', { name: 'Hide data table of the group chart' }).click();
	await again.getByRole('button', { name: 'Hide data table of the pump chart' }).click();
	await page.reload();
	await solveConverged(page);
	const third = await pumpsTab(page);
	await expect(
		third.getByRole('button', { name: 'Show data table of the pump chart' })
	).toHaveAttribute('aria-expanded', 'false', { timeout: 60_000 });
	const closedAgain = await openCard(page, third);
	await expect(
		closedAgain.getByRole('button', { name: 'Show data table of the group chart' })
	).toHaveAttribute('aria-expanded', 'false');
});

// ---- S7 review: the curve tables with long names, their marks, shadows and focus ----------------

/**
 * The pump-transfer example in US units, its isolation valve an FCV held at 15 L/s and named by
 * a 40-character unbroken name (made-up test inputs, as pump-system.e2e.ts's): every forced flow
 * above 15 L/s has no steady state, so the System curve's Why no head reasons name the valve, and
 * the table is open by default (§9 S7).
 */
const LONG_VALVE = 'FlowLimiterOnTheTransferPumpDischarge001';
function limitedTransfer(): Project {
	const project = pumpTransferExample();
	project.settings.units = { ...IMPERIAL_UNITS };
	project.components[2] = {
		type: 'valve',
		valveType: 'fcv',
		id: 'V1',
		name: LONG_VALVE,
		elevation: 0,
		status: 'active',
		setpoint: 0.015,
		ports: project.components[2]!.ports
	} as Project['components'][number];
	return project;
}

/**
 * The curve tables of a data region at the size shown: each fold's right edge against the
 * region's, its words' end against its summary's, its words and count in sight, the count's
 * lines, its chevron's turn and those of the Details inside its table, and its box: overflowing
 * sideways, a Tab stop, a region.
 */
function readCurveFolds(region: Element) {
	const inSight = (el: Element) => {
		const r = el.getBoundingClientRect();
		return (
			el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
			!el.closest('.sr-only') &&
			r.width > 1 &&
			r.height >= 12
		);
	};
	const turn = (svg: Element | null) => (svg ? getComputedStyle(svg).rotate : 'no chevron');
	return [...region.querySelectorAll<HTMLDetailsElement>('details[data-curve-table]')].map((d) => {
		const summary = d.querySelector(':scope > summary')!;
		const words = summary.querySelector(':scope > span')!;
		const count = words.querySelector(':scope > span')!;
		const box = d.querySelector('table')!.parentElement!;
		const range = document.createRange();
		range.selectNodeContents(words);
		const wordsEnd = Math.max(...[...range.getClientRects()].map((b) => b.right));
		return {
			key: d.dataset.curveTable!,
			open: d.open,
			right: Math.round(d.getBoundingClientRect().right),
			regionRight: Math.round(region.getBoundingClientRect().right),
			wordsInside: wordsEnd <= summary.getBoundingClientRect().right + 0.5,
			seen: inSight(words) && inSight(count),
			countLines: count.getClientRects().length,
			chevron: turn(summary.querySelector('svg')),
			details: [...box.querySelectorAll<HTMLDetailsElement>('details[data-issue-detail]')].map(
				(x) => ({ open: x.open, chevron: turn(x.querySelector(':scope > summary svg')) })
			),
			sideways: box.scrollWidth > box.clientWidth + 1,
			// How far it scrolls sideways, px.
			more: box.scrollWidth - box.clientWidth,
			tabindex: box.getAttribute('tabindex'),
			role: box.getAttribute('role')
		};
	});
}

/**
 * The mean colour of a clip of the screen, in CSS pixels, its screenshot decoded in the page (no
 * image library): [red, green, blue], 0 to 255.
 */
async function meanColour(
	page: Page,
	clip: { x: number; y: number; width: number; height: number }
): Promise<number[]> {
	const png = (await page.screenshot({ clip })).toString('base64');
	return page.evaluate(async (b64) => {
		const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
		const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
		const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
		const context = canvas.getContext('2d')!;
		context.drawImage(bitmap, 0, 0);
		const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height);
		let [red, green, blue] = [0, 0, 0];
		for (let i = 0; i < data.length; i += 4) {
			red += data[i]!;
			green += data[i + 1]!;
			blue += data[i + 2]!;
		}
		const n = data.length / 4;
		return [red / n, green / n, blue / n];
	}, png);
}

/**
 * How much the sideways edge shadow darkens a box that scrolls sideways at its inner right edge,
 * in its first body row, scrolled to its start (§5.3 "Every box gets scroll-shadow-x"; S7 review
 * LAYOUT-2): 255 less the mean of the clip's channels, its words made transparent while read so
 * only the box's background is measured. A white edge gives 0; the shadow about 35.
 */
async function edgeShadow(page: Page, box: Locator): Promise<number> {
	const clip = await box.evaluate((el) => {
		el.querySelector('thead')!.scrollIntoView({
			block: 'center',
			inline: 'start',
			behavior: 'instant'
		});
		el.scrollLeft = 0;
		for (const e of el.querySelectorAll<HTMLElement>('*')) {
			e.style.setProperty('color', 'transparent');
		}
		const row = el.querySelector('tbody tr')!.getBoundingClientRect();
		const r = el.getBoundingClientRect();
		const right = r.left + el.clientLeft + el.clientWidth;
		return { x: right - 3, y: row.top + row.height / 2 - 2, width: 2, height: 4 };
	});
	const colour = await meanColour(page, clip);
	await box.evaluate((el) => {
		for (const e of el.querySelectorAll<HTMLElement>('*')) e.style.removeProperty('color');
	});
	return 255 - colour.reduce((a, b) => a + b, 0) / 3;
}

test('S7 review: a curve table never widens the pane: with a 40-character unbroken name in the System curve’s reasons nothing scrolls sideways and its box scrolls in itself, a named Tab stop that keeps the focus as it stops overflowing; each summary’s words and count whole and in sight; each chevron its own disclosure’s; the edge shadow in the first rows (§7 Targets, §5.3, §9 S7; S7 review STRUCT-1, LAYOUT-1, DATA-2, A11Y-1, A11Y-2, LAYOUT-2, LAYOUT-4, W2)', async ({
	page
}, info) => {
	test.setTimeout(240_000);
	const soft = expect.configure({ soft: true });
	await open(page, limitedTransfer());
	await solveConverged(page);
	const tab = await pumpsTab(page);
	const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
	await expect(figure.locator('[data-pump-method]')).toBeVisible({ timeout: 60_000 });
	await figure.getByRole('button', { name: 'Show data table of the pump chart' }).click();
	const region = figure.locator('[data-pump-data]');
	// The System curve open by default, its reasons naming the valve.
	const system = curveTableFold(figure, 'System curve');
	await expect(system).toHaveAttribute('open', '');
	await expect(system.getByRole('table', { name: 'System curve', exact: true })).toContainText(
		LONG_VALVE
	);
	const box = system.locator('table').locator('..');
	const viewport = page.viewportSize()!;
	const sizes =
		info.project.name === 'mobile' ? [viewport, { width: 320, height: 640 }] : [viewport];
	for (const size of sizes) {
		await page.setViewportSize(size);
		await settle(page, 1000);
		const where = `the long valve name at ${sizeOf(page)}`;
		await noSidewaysScroll(page, where);
		const folds = await region.evaluate(readCurveFolds);
		console.log(`${where}: ${JSON.stringify(folds)}`);
		soft(folds.map((f) => f.key).slice(0, 2), where).toEqual(['pump', 'system']);
		for (const f of folds) {
			// Never wider than the data region: a wide table scrolls in its own box.
			soft(f.right, `"${f.key}" inside the data region, ${where}`).toBeLessThanOrEqual(
				f.regionRight
			);
			soft(f.seen, `"${f.key}": its words and count in sight, ${where}`).toBe(true);
			soft(f.wordsInside, `"${f.key}": its words end inside its summary, ${where}`).toBe(true);
			soft(f.countLines, `"${f.key}": its count on one line, ${where}`).toBe(1);
			// Each chevron turns with its own disclosure only.
			soft(f.chevron, `"${f.key}"'s chevron, ${where}`).toBe(f.open ? '90deg' : 'none');
			for (const [i, d] of f.details.entries()) {
				soft(d.chevron, `"${f.key}": Details ${i + 1}'s chevron, ${where}`).toBe(
					d.open ? '90deg' : 'none'
				);
			}
			// A Tab stop and a region only while drawn and overflowing.
			const stop = f.open && f.sideways;
			soft(f.tabindex, `"${f.key}" a Tab stop only while it overflows, ${where}`).toBe(
				stop ? '0' : null
			);
			soft(f.role, `"${f.key}" a region only while it overflows, ${where}`).toBe(
				stop ? 'region' : null
			);
		}
		const curve = folds.find((f) => f.key === 'system')!;
		soft(curve.details.length, `Details in the System curve, ${where}`).toBeGreaterThan(0);
		// On a phone its table is wider than the pane: it scrolls in its box, named by its caption.
		if (size.width < 640) {
			soft(curve.sideways, `the System curve's box scrolls sideways, ${where}`).toBe(true);
			// Far enough for its shadow to be read below.
			soft(curve.more, `how far the System curve's box scrolls, ${where}`).toBeGreaterThanOrEqual(
				40
			);
		}
		if (curve.sideways) {
			await expect(region.getByRole('region', { name: 'System curve', exact: true })).toHaveCount(
				1
			);
		}
		// Its right shadow in its first row, where it scrolls past the end's white cover (2.5 rem,
		// which hides the shadow by design as the table's end comes into view).
		if (curve.more >= 40) {
			const shadow = await edgeShadow(page, box);
			console.log(`${where}: the System curve's right shadow in its first row: ${shadow}`);
			soft(shadow, `the right shadow in the first row, ${where}`).toBeGreaterThan(15);
		}
	}
	// A Details opened turns its own chevron, and only its own.
	const detail = system.locator('details[data-issue-detail]').first();
	const chevrons = () =>
		system.evaluate((d) =>
			[...d.querySelectorAll('details[data-issue-detail]')]
				.slice(0, 2)
				.map((x) => getComputedStyle(x.querySelector(':scope > summary svg')!).rotate)
		);
	expect(await chevrons()).toEqual(['none', 'none']);
	await detail.locator('summary').click();
	await expect.poll(chevrons).toEqual(['90deg', 'none']);
	await detail.locator('summary').click();
	await expect.poll(chevrons).toEqual(['none', 'none']);
	// A box that holds the focus as it stops overflowing keeps it (S7 review A11Y-1): focused by
	// Tab from its summary on a phone, the window widened until the table fits.
	if (info.project.name === 'mobile') {
		const state = () =>
			box.evaluate((el) => ({
				tabindex: el.getAttribute('tabindex'),
				role: el.getAttribute('role'),
				sideways: el.scrollWidth > el.clientWidth + 1
			}));
		await page.setViewportSize({ width: 320, height: 640 });
		await expect.poll(state).toEqual({ tabindex: '0', role: 'region', sideways: true });
		await system.locator(':scope > summary').focus();
		await page.keyboard.press('Tab');
		await expect(box).toBeFocused();
		await page.setViewportSize({ width: 1920, height: 1080 });
		await expect.poll(state).toEqual({ tabindex: '-1', role: 'region', sideways: false });
		await expect(box).toBeFocused();
		expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);
		await page.keyboard.press('Shift+Tab');
		await expect(system.locator(':scope > summary')).toBeFocused();
		await expect.poll(state).toEqual({ tabindex: null, role: null, sideways: false });
	}
	await page.setViewportSize(viewport);
});

test('S7 review: a 40-character unbroken case name ends inside the pump chart’s data region at each size, in “System curve, {case}”’s summary and in its row of “Operating points by case”, and nothing scrolls sideways (§5.5, §5.7 row 1; S7 review MUT-SUMMARY-NOBREAK, PRE-OPPOINTS-LONGCASE)', async ({
	page
}, info) => {
	test.setTimeout(300_000);
	const soft = expect.configure({ soft: true });
	const project = projectOf('one-off');
	project.scenarios!.find((s) => s.id === 'S3')!.name = LONG_CASE;
	const counter = solveCounter(page);
	await open(page, project);
	await solveAll(page, counter, 5);
	const tab = await pumpsTab(page);
	await tab.getByRole('combobox', { name: 'Pump chart' }).selectOption('PA');
	await settle(page);
	const figure = tab.getByRole('figure', { name: /^Pump and system curves/ });
	await figure.getByRole('button', { name: 'Show data table of the pump chart' }).click();
	await figure.getByRole('checkbox', { name: "Also show the other cases' system curves" }).check();
	const fold = curveTableFold(figure, `System curve, ${LONG_CASE}`);
	await expect(fold).toHaveCount(1, { timeout: 120_000 });
	await settle(page);
	const header = figure
		.getByRole('table', { name: 'Operating points by case' })
		.getByRole('rowheader')
		.filter({ hasText: LONG_CASE });
	await expect(header).toHaveCount(1);
	const viewport = page.viewportSize()!;
	const sizes =
		info.project.name === 'mobile' ? [viewport, { width: 320, height: 640 }] : [viewport];
	for (const size of sizes) {
		await page.setViewportSize(size);
		await settle(page, 1000);
		const where = `the long case name at ${sizeOf(page)}`;
		await noSidewaysScroll(page, where);
		const summary = await fold.evaluate((d) => {
			const s = d.querySelector(':scope > summary')!;
			const range = document.createRange();
			range.selectNodeContents(s.querySelector(':scope > span')!);
			return {
				wordsEnd: Math.round(Math.max(...[...range.getClientRects()].map((b) => b.right))),
				right: Math.round(s.getBoundingClientRect().right)
			};
		});
		console.log(`${where}: the summary ${JSON.stringify(summary)}`);
		soft(
			summary.wordsEnd,
			`"System curve, {case}"'s words end inside it, ${where}`
		).toBeLessThanOrEqual(summary.right);
		// Its row header in "Operating points by case" (a list below 640 px, a table that scrolls
		// sideways in its box above) and every other line of the name inside the pump chart.
		const past = await figure.evaluate(namesPast, [LONG_CASE]);
		console.log(`${where}: past the pump chart ${JSON.stringify(past)}`);
		soft(past, `a line of the long case name past the pump chart's edge, ${where}`).toEqual([]);
	}
	await page.setViewportSize(viewport);
});

/**
 * "Also show the other cases' system curves" as read for a press (S8 review LAYOUT-1): its top in
 * the viewport, and whether the element at a point is the switch itself.
 */
function readSwitch(el: Element, point: { x: number; y: number }) {
	return {
		top: el.getBoundingClientRect().top,
		hit: document.elementFromPoint(point.x, point.y) === el
	};
}

test('S8 review: “Also show the other cases’ system curves” stays under the pointer as it is switched on and off, though the boxes above it change (§9 S8 Slots; ui-guide, a press moves nothing under the pointer; S8 review LAYOUT-1)', async ({
	page,
	isMobile
}) => {
	test.setTimeout(240_000);
	const soft = expect.configure({ soft: true });
	await oneOff(page);
	const tab = await pumpsTab(page);
	const figure = await pumpFigure(page);
	const cases = figure.getByRole('group', { name: 'Cases on the chart' });
	const box = figure.getByRole('checkbox', { name: "Also show the other cases' system curves" });
	const viewport = page.viewportSize()!;
	const sizes = isMobile ? [viewport, { width: 320, height: 640 }] : [viewport];
	// The card closed (the tab's default), then open: below the switch the pane then holds more
	// than the boxes it adds or takes away, so no scroll end keeps it in place.
	for (const card of ['closed', 'open']) {
		if (card === 'open') await openCard(page, tab);
		for (const size of sizes) {
			await page.setViewportSize(size);
			await settle(page, 1000);
			for (const on of [true, false]) {
				const where = `switched ${on ? 'on' : 'off'} at ${sizeOf(page)}, the card ${card}`;
				// The switch in the middle of the pane's scroller, as a user reading the list reaches it.
				await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
				await page.waitForTimeout(200);
				const r = (await box.boundingBox())!;
				const point = { x: r.x + r.width / 2, y: r.y + r.height / 2 };
				const before = await box.evaluate(readSwitch, point);
				expect(before.hit, `the switch at the point pressed before the press, ${where}`).toBe(true);
				if (isMobile) await page.touchscreen.tap(point.x, point.y);
				else await page.mouse.click(point.x, point.y);
				await expect(box).toBeChecked({ checked: on });
				// Pump PA's two off cases: their boxes above the switch while the curves are on, the
				// line naming them while they are off (§9 S8 Slots).
				await expect(cases.getByRole('checkbox', { name: 'Pump PA off', exact: true })).toHaveCount(
					on ? 1 : 0
				);
				await expect(cases.locator('[data-pump-off-cases]')).toHaveCount(on ? 0 : 1);
				await page.waitForTimeout(300);
				const after = await box.evaluate(readSwitch, point);
				console.log(`${where}: the switch's top ${before.top} -> ${after.top}`);
				soft(Math.abs(after.top - before.top), `the switch moved, ${where}`).toBeLessThanOrEqual(1);
				soft(after.hit, `the switch still under the point pressed, ${where}`).toBe(true);
				await settle(page);
			}
		}
	}
	await page.setViewportSize(viewport);
});

test('S8 second check: “Also show the other cases’ system curves” stays under the pointer with the data table shown, as each curve’s table arrives above it (ui-guide, a press moves nothing under the pointer; S8 second check LAYOUT-2)', async ({
	page,
	isMobile
}) => {
	test.setTimeout(240_000);
	const soft = expect.configure({ soft: true });
	await oneOff(page);
	const figure = await pumpFigure(page);
	const box = figure.getByRole('checkbox', { name: "Also show the other cases' system curves" });
	// The data table shown (remembered in this browser since S7): each other case's system curve
	// has its table there, above the switch, inserted when its curve answers (§5.3 The data
	// region). The curves are asked for by this press, for the first time in this solve.
	await figure.getByRole('button', { name: /^Show data table/ }).click();
	await expect(figure.getByRole('button', { name: /^Hide data table/ })).toBeVisible();
	await settle(page);
	const tables = figure.locator('[data-curve-table^="system-"]');
	await expect(tables).toHaveCount(0);
	for (const on of [true, false]) {
		const where = `switched ${on ? 'on' : 'off'} at ${sizeOf(page)}, the data table shown`;
		await box.evaluate((el) => el.scrollIntoView({ block: 'center' }));
		await page.waitForTimeout(200);
		const r = (await box.boundingBox())!;
		const point = { x: r.x + r.width / 2, y: r.y + r.height / 2 };
		const before = await box.evaluate(readSwitch, point);
		expect(before.hit, `the switch at the point pressed before the press, ${where}`).toBe(true);
		if (isMobile) await page.touchscreen.tap(point.x, point.y);
		else await page.mouse.click(point.x, point.y);
		await expect(box).toBeChecked({ checked: on });
		await page.waitForTimeout(300);
		const soon = await box.evaluate(readSwitch, point);
		console.log(`${where}: the switch's top ${before.top} -> ${soon.top} at 300 ms`);
		soft(
			Math.abs(soon.top - before.top),
			`the switch moved by 300 ms, ${where}`
		).toBeLessThanOrEqual(1);
		soft(soon.hit, `the switch still under the point pressed at 300 ms, ${where}`).toBe(true);
		// Every curve answered, each table drawn: Pump PA's four other cases, its off ones too.
		await settle(page);
		await expect(tables).toHaveCount(on ? 4 : 0);
		const settled = await box.evaluate(readSwitch, point);
		console.log(`${where}: the switch's top ${before.top} -> ${settled.top} once settled`);
		soft(
			Math.abs(settled.top - before.top),
			`the switch moved once the curves settled, ${where}`
		).toBeLessThanOrEqual(1);
		soft(settled.hit, `the switch still under the point pressed once settled, ${where}`).toBe(true);
	}
});
