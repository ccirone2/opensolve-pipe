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
import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import { gzip } from 'pako';
import type { Project } from '../src/lib/api/types';
import { exampleProject, pumpTransferExample } from '../src/lib/utils/examples';
import { canonicalJson } from '../src/lib/utils/json';
import {
	caseGroup,
	openCases,
	resultsPane,
	resultsScroller,
	resultsView,
	showPane,
	solve,
	solveConverged
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
 * family drawn), both data tables shown and every disclosure at or below the chart opened.
 */
async function lineups(page: Page) {
	const counter = solveCounter(page);
	await open(page, projectOf('lineups'));
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
	}[] = [];
	let run: Element[] = [];
	const flush = () => {
		if (run.length >= 3) {
			runs.push({
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
			.getByRole('button', { name: /^(Show|Hide) data table$/ })
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
	for (const name of names) {
		await toolbar.getByRole('button', { name, exact: true }).press('Enter');
		const animations = await page.evaluate(() => document.getAnimations().length);
		// The nav's state once the canvas's observer has run, a frame after the scroll (S2
		// review KBD-2: read at once, it was sometimes the state before the press).
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
	await measure(page, info, `${view}-${size}`, extra);
	await navPart(page, `${view} at ${size}`);
	if (info.project.name !== 'mobile') {
		await axeClean(page, `${view} at ${size}`);
		await pageHolds(page, `${view} at ${size}, every disclosure open`);
		return;
	}
	const viewport = page.viewportSize()!;
	await page.setViewportSize({ width: 320, height: 640 });
	await settle(page, 1000);
	await noSidewaysScroll(page, `${view} at 320x640`);
	await pageHolds(page, `${view} at 320x640`);
	await pumpChartPart(page, `${view} at 320x640`);
	await measure(page, info, `${view}-320x640`, extra);
	await navPart(page, `${view} at 320x640`);
	await axeClean(page, `${view} at 320x640`);
	await pageHolds(page, `${view} at 320x640, every disclosure open`);
	await page.setViewportSize(viewport);
	await settle(page, 1000);
	await axeClean(page, `${view} at ${size}`);
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

	// S1 (§5.3, §10): a case in which Pump PA is off says so in its box's description, beside
	// the box; the others do not. The fixture's scenarios set PA off in "Pump PA off" and "Both
	// pumps off" (pump-groups-input.json).
	const figure = await pumpFigure(page);
	const cases = figure.getByRole('group', { name: 'Cases on the chart' });
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
