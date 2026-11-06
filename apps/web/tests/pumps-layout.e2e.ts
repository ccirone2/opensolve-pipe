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

/**
 * Check and measure the view at the project's size and, on the phone, at 320×640 too (reflow at
 * 400 % zoom; pump-lineups.e2e.ts resizes the same way).
 */
async function atEachSize(page: Page, info: TestInfo, view: string, extra: object) {
	await noSidewaysScroll(page, `${view} at ${sizeOf(page)}`);
	await pumpChartPart(page, `${view} at ${sizeOf(page)}`);
	await measure(page, info, `${view}-${sizeOf(page)}`, extra);
	if (info.project.name !== 'mobile') return;
	await page.setViewportSize({ width: 320, height: 640 });
	await settle(page, 1000);
	await noSidewaysScroll(page, `${view} at 320x640`);
	await pumpChartPart(page, `${view} at 320x640`);
	await measure(page, info, `${view}-320x640`, extra);
}

// ---- S0: no sideways scroll; S1: the pump chart's budget and outline -----------------------------

test('the condenser example after Add cases, the card open: the Results pane’s scroller does not scroll sideways; the pump chart holds its budget', async ({
	page
}, info) => {
	test.setTimeout(420_000);
	const extra = await condenser(page);
	await atEachSize(page, info, '3-condenser', extra);
});

test('one-off, the Pumps tab’s defaults: nothing scrolls sideways; the pump chart holds its budget', async ({
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

test('lineups, every disclosure and data table open: nothing scrolls sideways; the pump chart holds its budget', async ({
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
