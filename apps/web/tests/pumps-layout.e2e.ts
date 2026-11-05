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
import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import { gzip } from 'pako';
import type { Project } from '../src/lib/api/types';
import { exampleProject } from '../src/lib/utils/examples';
import { canonicalJson } from '../src/lib/utils/json';
import {
	caseGroup,
	openCases,
	resultsPane,
	resultsScroller,
	resultsView,
	showPane,
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

/** The Pumps tab at rest: no figure busy and no request in progress, for `stable` ms on end. */
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
					if (
						[...tab.querySelectorAll('figure')].some((f) => f.getAttribute('aria-busy') === 'true')
					) {
						return false;
					}
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
	const below = (el: Element) => el.getBoundingClientRect().top >= base - 0.5;

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
 * CSS pixels (measure.mjs `stitched`); the files and the scroll offset each was taken at.
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
	const segments: { file: string; scrollTop: number }[] = [];
	let position = Math.max(0, geometry.start);
	for (let i = 0; i < 200 && position < geometry.end; i++) {
		const actual = await page.evaluate((top) => {
			const s = document.querySelector('[data-layout-scroller]')!;
			s.scrollTop = top;
			return s.scrollTop;
		}, position);
		await page.waitForTimeout(150);
		const file = path.join(dir, 'segments', `${label}-${String(i).padStart(3, '0')}.png`);
		const b = geometry.box;
		await page.screenshot({
			path: file,
			scale: 'css',
			clip: { x: Math.round(b.x), y: Math.round(b.y), width: b.width, height: b.height }
		});
		segments.push({ file, scrollTop: actual });
		if (actual + b.height >= geometry.end) break;
		const next = actual + b.height;
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

/**
 * Check and measure the view at the project's size and, on the phone, at 320×640 too (reflow at
 * 400 % zoom; pump-lineups.e2e.ts resizes the same way).
 */
async function atEachSize(page: Page, info: TestInfo, view: string, extra: object) {
	await noSidewaysScroll(page, `${view} at ${sizeOf(page)}`);
	await measure(page, info, `${view}-${sizeOf(page)}`, extra);
	if (info.project.name !== 'mobile') return;
	await page.setViewportSize({ width: 320, height: 640 });
	await settle(page, 1000);
	await noSidewaysScroll(page, `${view} at 320x640`);
	await measure(page, info, `${view}-320x640`, extra);
}

// ---- S0: no sideways scroll ---------------------------------------------------------------------

test('the condenser example after Add cases, the card open: the Results pane’s scroller does not scroll sideways', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	const extra = await condenser(page);
	await atEachSize(page, info, '3-condenser', extra);
});

test('one-off, the Pumps tab’s defaults: nothing scrolls sideways', async ({ page }, info) => {
	test.setTimeout(240_000);
	const extra = await oneOff(page);
	await atEachSize(page, info, '1-one-off', extra);
});

test('lineups, every disclosure and data table open: nothing scrolls sideways', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	const extra = await lineups(page);
	await atEachSize(page, info, '2-lineups', extra);
});
