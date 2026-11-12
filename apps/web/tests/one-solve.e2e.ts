/**
 * One Solve, one Solve all (proposal build-density.md §19; the owner, 2026-11-12: "Having 'solve'
 * buttons appear twice on a screen is unnecessary. The solve button is and should always be in
 * view at the top. Similar issue with 'solve all' button appearing more than once."), in the
 * running app on both projects.
 *
 * The owner's state: the condenser water example (6 pumps, 1 scenario), its base case solved, the
 * Pumps together card's Add cases By number running pressed (5 cases), then reopened by its link:
 * 6 scenarios, 7 cases, none solved. The link is built here, from the project the page wrote, never
 * pasted.
 *
 * 1. The owner's rule: in every state, exactly one Solve drawn outside a dialog, the header's, and
 *    no Solve all with the Scenarios menu closed, one (the menu's) with it open.
 * 2. Fit: no sideways scroll, the header's build-density budgets (95 px on phones, 49 px from
 *    640 px), the amber badge and the menu inside the viewport, the menu under its button from
 *    640 px, and the project name's room at 768 px (§19's budgets, measured in §5 step 1).
 * 3. Ctrl+Shift+Enter on a phone: from a Build field, the run, the badge's countdown, the refusal's
 *    notice and a held key's repeats.
 * 4. The menu's defects fixed: Tab past it closes it, Shift+Tab returns to Scenarios, a pointer
 *    Cancel keeps it open with its line seen, a network stop with it closed raises an alert.
 * 5. The trace, its results out of date: the sheet below 1024 px keeps Solve again (the header is
 *    inert behind it); the side panel from 1024 px names the header's Solve.
 * 6. Short landscape screens: one pinned row at most 48 px, Solve in view at the page's end, a
 *    focused control never under it, the menu's foot reachable; narrower short windows scroll as
 *    one page (WCAG 1.4.10).
 * 7. The Scenarios spinner keeps its 20 px.
 * 8. axe over the menu with the amber badge, Results' E1, Compare's amber line and the trace sheet.
 */
import { gunzipSync } from 'node:zlib';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Browser, type Locator, type Page, type Route } from '@playwright/test';
import { gzip } from 'pako';
import type { Project } from '../src/lib/api/types';
import { exampleProject } from '../src/lib/utils/examples';
import { canonicalJson } from '../src/lib/utils/json';
import { WEB_ORIGIN } from './servers';
import {
	buildPane,
	caseMenu,
	openCases,
	resultsPane,
	resultsView,
	showPane,
	solveAll,
	solveAllButton,
	solveConverged,
	traceOf
} from './support';

/** Solve, "Solve {case}", Solve now and Solve again; not Solve all (the build plan's §4). */
const SOLVE_ONE = /^Solve($| (?!all\b))/;
/** Solve all, with its count while it can run. */
const SOLVE_ALL = /^Solve all( \(\d+\))?$/;
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** The header's budgets (build-density.md §7, §8 item 20): two rows on a phone, one from 640 px. */
const HEADER_PHONE = 95;
const HEADER_WIDE = 49;
/** The pinned row on a short landscape screen: 15 % of 320 px, the chrome rule (§19). */
const PINNED_ROW = 48;
/** The project name's room (§19): at 568×320, and at 768 px idle. */
const NAME_SHORT = 80;
const NAME_768_IDLE = 150;
/**
 * The project name at 768 px while a held solve runs, measured in §5 step 1 on web/one-solve
 * (113.6 px on both projects, at deviceScaleFactor 1, for Solve and for Solve all; main's was
 * 26 and 28.8 px): the budget is that value less 4 px, and never under 60 px.
 */
const NAME_768_SOLVING = 113.6;

// ---- The owner's state --------------------------------------------------------------------------

/** The project a page wrote in its link (D3: canonical JSON, gzip, base64url). */
function linked(url: string): Project {
	const hash = new URL(url).hash.slice(1);
	return JSON.parse(gunzipSync(Buffer.from(hash, 'base64url')).toString('utf8')) as Project;
}

/** Open a project by its link, as utils/encoding.ts writes it: a fresh load, never a hash change. */
async function open(page: Page, project: Project) {
	if (page.url().startsWith(WEB_ORIGIN)) await page.goto('about:blank');
	const bytes = gzip(new TextEncoder().encode(canonicalJson(project)), { level: 9 });
	await page.goto(`/p#${Buffer.from(bytes).toString('base64url')}`);
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(page.getByRole('banner').getByRole('button', { name: /^Scenarios/ })).toBeVisible();
}

/**
 * The condenser example, its base case solved, the Pumps together card opened and Add cases By
 * number running pressed: the page left there, the focus on Add (build-density.md §19).
 */
async function addByNumberRunning(page: Page): Promise<Locator> {
	await open(page, exampleProject('condenser-water')!);
	await solveConverged(page);
	await showPane(page, 'Results');
	const tab = await resultsView(page, 'Pumps');
	const card = tab.getByRole('region', { name: /^Pumps together/ });
	const toggle = card.getByRole('button', { name: /^Pumps together/ });
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	await toggle.click();
	await expect(toggle).toHaveAttribute('aria-expanded', 'true');
	const block = card.getByRole('region', { name: 'Add cases' });
	const preset = block.getByRole('radio', { name: 'By number running' });
	if (!(await preset.isChecked())) await preset.check();
	const add = block.getByRole('button', { name: 'Add 5 cases', exact: true });
	await expect(add).toBeVisible({ timeout: 120_000 });
	await expect(add).not.toHaveAttribute('aria-disabled', 'true');
	await add.click();
	// The same node, now "Add cases" and unavailable, keeps the focus.
	await expect(block.getByRole('button', { name: 'Add cases', exact: true })).toBeFocused();
	await expect.poll(() => linked(page.url()).scenarios?.length ?? 0).toBe(6);
	return block;
}

/** The owner's 7-case project, built once per worker (a failed test starts a new one). */
let owners: Project | null = null;
async function ownersProject(browser: Browser): Promise<Project> {
	if (!owners) {
		const context = await browser.newContext({
			baseURL: WEB_ORIGIN,
			viewport: { width: 1280, height: 800 }
		});
		try {
			const page = await context.newPage();
			await addByNumberRunning(page);
			owners = linked(page.url());
		} finally {
			await context.close();
		}
	}
	return structuredClone(owners);
}

// ---- Reading the page -----------------------------------------------------------------------------

const banner = (page: Page) => page.getByRole('banner');
const scenariosButton = (page: Page) => banner(page).getByRole('button', { name: /^Scenarios/ });
const headerSolve = (page: Page) => page.locator('header [data-solve-button]');
const menuGroup = (page: Page) => page.getByRole('group', { name: 'Case', exact: true });
const cancelButton = (page: Page) => banner(page).getByRole('button', { name: /^Cancel/ });
const squash = (text: string) => text.replace(/\s+/g, ' ').trim();

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
 * A line on screen as text (ui-guide, "How a new UI change ships", item 3): seenBox's test, no
 * `.sr-only` element at or above it, and at least a 12 px line tall (as tests/pumps-layout.e2e.ts
 * reads it).
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

/** A fine pointer: KeysHint draws the shortcut only there (build-density.md §19). */
const finePointer = (page: Page) =>
	page.evaluate(() => window.matchMedia('(pointer: fine)').matches);

/**
 * The buttons named `name` drawn on the page outside a dialog (a modal keeps its own: the trace's
 * sheet): which are the header's Solve and the menu's Solve all. Read whether the page scrolled to
 * them or not: the owner's rule is about the page, not the part of it in view.
 */
async function drawnButtons(page: Page, name: RegExp) {
	const out: { header: boolean; menu: boolean }[] = [];
	for (const button of await page.getByRole('button', { name }).all()) {
		const at = await button.evaluate((el) => {
			const r = el.getBoundingClientRect();
			return {
				drawn:
					el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
					r.width > 1 &&
					r.height > 1,
				dialog: !!el.closest('dialog, [role="dialog"]'),
				header: el.hasAttribute('data-solve-button'),
				menu: el.hasAttribute('data-solve-all')
			};
		});
		if (at.drawn && !at.dialog) out.push({ header: at.header, menu: at.menu });
	}
	return out;
}

/** The owner's rule, counted: one Solve (the header's); Solve all only in the menu, when open. */
async function oneEach(page: Page, menuOpen: boolean, where: string) {
	await expect(menuGroup(page), `the menu ${menuOpen ? 'open' : 'closed'}, ${where}`).toBeVisible({
		visible: menuOpen
	});
	const solves = await drawnButtons(page, SOLVE_ONE);
	expect(solves, `the Solve buttons drawn, ${where}`).toEqual([{ header: true, menu: false }]);
	const alls = await drawnButtons(page, SOLVE_ALL);
	expect(alls, `the Solve all buttons drawn, ${where}`).toEqual(
		menuOpen ? [{ header: false, menu: true }] : []
	);
}

/** The header's parts as laid out (viewport px). */
async function headerParts(page: Page) {
	return page.evaluate(() => {
		const box = (el: Element | null | undefined) => {
			if (!el) return null;
			const r = el.getBoundingClientRect();
			return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width };
		};
		const header = document.querySelector('header')!;
		const button = header.querySelector('button[aria-controls$="-cases"]');
		const badge = button?.querySelector(':scope > span[aria-hidden="true"]');
		const icon = button?.querySelector(':scope > svg');
		const style = icon ? getComputedStyle(icon) : null;
		return {
			header: box(header)!,
			position: getComputedStyle(header).position,
			name: box(header.querySelector('input'))!,
			scenarios: box(button)!,
			badge: box(badge),
			badgeText: badge?.textContent?.trim() ?? null,
			badgeMark: !!badge?.querySelector('svg'),
			badgeClass: badge?.getAttribute('class') ?? '',
			icon: style ? { width: parseFloat(style.width), height: parseFloat(style.height) } : null,
			solve: box(header.querySelector('[data-solve-button]'))!,
			sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth
		};
	});
}

/** The menu's panel (the element the Scenarios button controls), as laid out. */
async function menuBox(page: Page) {
	const id = await scenariosButton(page).getAttribute('aria-controls');
	return page.locator(`[id="${id}"]`).evaluate((el) => {
		const r = el.getBoundingClientRect();
		return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
	});
}

/** The amber ▶n badge, inside the viewport (§19: left ≥ 0, right ≤ width, top ≥ −1). */
function amberBadge(
	parts: Awaited<ReturnType<typeof headerParts>>,
	width: number,
	count: number,
	where: string
) {
	expect(parts.badge, `the badge, ${where}`).not.toBeNull();
	expect(parts.badgeClass, `the badge amber, ${where}`).toContain('bg-amber-400');
	expect(parts.badgeMark, `the badge's ▶, ${where}`).toBe(true);
	expect(parts.badgeText, `the badge's count, ${where}`).toBe(String(count));
	expect(parts.badge!.left, `the badge's left, ${where}`).toBeGreaterThanOrEqual(0);
	expect(parts.badge!.right, `the badge's right, ${where}`).toBeLessThanOrEqual(width);
	expect(parts.badge!.top, `the badge's top, ${where}`).toBeGreaterThanOrEqual(-1);
}

/** Count the solves the page is answered from now on. */
function solveCounter(page: Page): { n: number } {
	const counter = { n: 0 };
	page.on('response', (r) => {
		if (r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST') counter.n++;
	});
	return counter;
}

/**
 * Hold every solve request at the network: `held` lists them; `release` lets them and every later
 * one go on.
 */
async function hold(page: Page): Promise<Route[] & { release: () => Promise<void> }> {
	const held: Route[] = [];
	let open = false;
	await page.route('**/api/v1/solve', (route) => {
		if (open) void route.continue();
		else held.push(route);
	});
	return Object.assign(held, {
		release: async () => {
			open = true;
			for (const route of held.splice(0)) await route.continue();
			await page.unroute('**/api/v1/solve');
		}
	});
}

/** Stop a held calculation with the header's Cancel and let the network go. */
async function cancelHeld(page: Page, held: Route[]) {
	await cancelButton(page).click();
	await expect(cancelButton(page)).toHaveCount(0);
	for (const route of held.splice(0)) await route.abort().catch(() => {});
	await page.unroute('**/api/v1/solve');
}

/** A Build edit that leaves the results out of date: the shown component's elevation, 1 unit up. */
async function editElevation(page: Page) {
	await showPane(page, 'Build');
	const elevation = buildPane(page).getByRole('textbox', { name: /^Elevation/ });
	const value = Number(await elevation.inputValue());
	await elevation.fill(String(value + 1));
	await elevation.press('Enter');
	await expect(elevation).toHaveValue(String(value + 1));
}

/** The info or error notice at the foot of the page, by its Dismiss button. */
const notice = (page: Page, role: 'status' | 'alert') =>
	page.getByRole(role).filter({ has: page.getByRole('button', { name: 'Dismiss' }) });

// ---- 1. The owner's rule --------------------------------------------------------------------------

for (const [width, height] of [
	[320, 640],
	[390, 844],
	[1280, 800]
] as const) {
	test(`one Solve and one Solve all at ${width}×${height}, in every state`, async ({ page }) => {
		test.setTimeout(300_000);
		await page.setViewportSize({ width, height });
		const keys = await finePointer(page);

		// The Pumps card open after Add (the base case solved, five cases added).
		await addByNumberRunning(page);
		await oneEach(page, false, 'the Pumps card after Add');

		// The owner's state: reopened by its link, no case solved.
		const project = linked(page.url());
		owners ??= structuredClone(project);
		await open(page, project);
		await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6), 7 cases to solve');
		await showPane(page, 'Results');
		const e1 = resultsPane(page).locator('p', { hasText: /^\s*Press\b/ });
		await expect(e1).toHaveCount(1);
		expect(squash(await e1.innerText())).toBe(
			keys
				? 'Press Solve, at the top (Ctrl+Enter or ⌘+Enter), to solve it. Solve all, in the Scenarios menu (Ctrl+Shift+Enter or ⌘+Shift+Enter), solves the 7 cases whose results are missing or out of date.'
				: 'Press Solve, at the top, to solve it. Solve all, in the Scenarios menu, solves the 7 cases whose results are missing or out of date.'
		);
		expect(await seenLine(e1), 'E1 on screen').toBe(true);
		// Each control's icon and word on one line, as an icon-only button reads at 320 px.
		for (const name of await e1.locator('span.whitespace-nowrap').all()) {
			expect(await name.evaluate((el) => el.getClientRects().length)).toBe(1);
		}
		await oneEach(page, false, 'unsolved, Results › Base case');
		if (width < 1024) {
			await showPane(page, 'Build');
			await oneEach(page, false, 'Build on a phone');
			await showPane(page, 'Results');
		}

		await resultsPane(page).getByRole('tab', { name: 'Compare cases' }).click();
		const compare = resultsPane(page).getByRole('region', { name: 'Compare cases' });
		const amber = compare.locator('p', { hasText: /missing or out of date/ });
		expect(squash(await amber.innerText())).toBe(
			`7 of 7 cases have results that are missing or out of date: Solve all, in the Scenarios menu at the top${keys ? ' (Ctrl+Shift+Enter or ⌘+Shift+Enter)' : ''}, solves them one after another.`
		);
		expect(await seenLine(amber), "Compare's amber line on screen").toBe(true);
		await expect(compare.getByText('No case has results yet.', { exact: true })).toBeVisible();
		await oneEach(page, false, 'Compare cases');

		await openCases(page);
		await expect(solveAllButton(page)).toHaveAccessibleName('Solve all (7)');
		await oneEach(page, true, 'the menu open');
		await page.keyboard.press('Escape');

		await resultsPane(page)
			.getByRole('tab', { name: /^Base case/ })
			.click();
		await solveConverged(page);
		await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6), 6 cases to solve');
		await oneEach(page, false, 'after the header Solve');

		await editElevation(page);
		await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6), 7 cases to solve');
		await oneEach(page, false, 'out of date after a Build edit, on Build');
		await showPane(page, 'Results');
		const stale = resultsPane(page).locator('p', { hasText: /^\s*Results are out of date/ });
		expect(squash(await stale.innerText())).toBe(
			`Results are out of date: the project changed after this solve. Press Solve, at the top${keys ? ' (Ctrl+Enter or ⌘+Enter)' : ''}, to update them.`
		);
		expect(await seenLine(stale), "the pane's out-of-date line on screen").toBe(true);
		await oneEach(page, false, 'out of date after a Build edit, on Results');
	});
}

// ---- 2. Fit ---------------------------------------------------------------------------------------

for (const [width, height] of [
	[320, 640],
	[360, 740],
	[390, 844],
	[640, 800],
	[768, 800],
	[1024, 800],
	[1280, 800]
] as const) {
	test(`the header and the menu fit at ${width}×${height}`, async ({ page, browser }) => {
		test.setTimeout(180_000);
		await page.setViewportSize({ width, height });
		await open(page, await ownersProject(browser));
		await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6), 7 cases to solve');
		const budget = width < 640 ? HEADER_PHONE : HEADER_WIDE;

		const idle = await headerParts(page);
		expect(idle.sideways, 'no sideways scroll').toBe(0);
		expect(idle.header.bottom - idle.header.top, 'the header').toBeLessThanOrEqual(budget);
		amberBadge(idle, width, 7, 'idle');
		if (width === 768) {
			expect(idle.name.width, 'the project name at 768 px').toBeGreaterThanOrEqual(NAME_768_IDLE);
		}

		await openCases(page);
		const menu = await menuBox(page);
		expect(menu.left, "the menu's left").toBeGreaterThanOrEqual(0);
		expect(menu.right, "the menu's right").toBeLessThanOrEqual(width);
		expect(menu.top, "the menu's top").toBeGreaterThanOrEqual(0);
		expect(menu.bottom, "the menu's bottom").toBeLessThanOrEqual(height);
		if (width >= 640) {
			expect(menu.left, 'the menu under its button').toBeCloseTo(idle.scenarios.left, 1);
		}
		expect((await headerParts(page)).sideways, 'no sideways scroll, the menu open').toBe(0);
		await page.keyboard.press('Escape');
		await expect(menuGroup(page)).toBeHidden();

		// A held solve, then a held Solve all: the header keeps its fit.
		for (const run of ['Solve', 'Solve all'] as const) {
			const held = await hold(page);
			if (run === 'Solve') {
				await headerSolve(page).click();
			} else {
				await solveAll(page);
				await expect.poll(() => held.length).toBe(1);
				await page.keyboard.press('Escape');
				await expect(menuGroup(page)).toBeHidden();
			}
			await expect.poll(() => held.length).toBe(1);
			await expect(cancelButton(page)).toBeVisible();
			const solving = await headerParts(page);
			const where = `${run} held`;
			expect(solving.sideways, `no sideways scroll, ${where}`).toBe(0);
			expect(
				solving.header.bottom - solving.header.top,
				`the header, ${where}`
			).toBeLessThanOrEqual(budget);
			amberBadge(solving, width, 7, where);
			if (width === 768) {
				expect(solving.name.width, `the project name at 768 px, ${where}`).toBeGreaterThanOrEqual(
					Math.max(NAME_768_SOLVING - 4, 60)
				);
			}
			await cancelHeld(page, held);
		}
	});
}

// ---- 3. Keyboard on a phone -----------------------------------------------------------------------

test('on a phone, Ctrl+Shift+Enter from a Build field runs Solve all, and says why when it cannot', async ({
	page,
	browser
}) => {
	test.setTimeout(300_000);
	await page.setViewportSize({ width: 390, height: 844 });
	const project = await ownersProject(browser);
	await open(page, project);
	await showPane(page, 'Build');
	const elevation = buildPane(page).getByRole('textbox', { name: /^Elevation/ });
	await elevation.focus();
	// Every name the Scenarios button takes from now on.
	await scenariosButton(page).evaluate((el) => {
		const w = window as unknown as { scenarioNames: string[] };
		w.scenarioNames = [el.getAttribute('aria-label') ?? ''];
		new MutationObserver(() => w.scenarioNames.push(el.getAttribute('aria-label') ?? '')).observe(
			el,
			{ attributes: true, attributeFilter: ['aria-label'] }
		);
	});
	const counter = solveCounter(page);
	await page.keyboard.press('Control+Shift+Enter');
	const resultsTab = page.getByRole('tablist', { name: 'View' }).getByRole('tab', {
		name: /^Results/
	});
	await expect(resultsTab).toHaveAttribute('aria-selected', 'true');
	await expect(resultsPane(page)).toBeVisible();
	// Build is hidden with the field: the focus goes to the Results tab, never to the page, and the
	// run does not move it.
	await expect(resultsTab).toBeFocused();
	await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6)', { timeout: 240_000 });
	expect(counter.n).toBe(7);
	// The badge counts down as each case gets its answer.
	expect(
		await page.evaluate(() => (window as unknown as { scenarioNames: string[] }).scenarioNames)
	).toEqual([
		'Scenarios (6), 7 cases to solve',
		'Scenarios (6), 6 cases to solve',
		'Scenarios (6), 5 cases to solve',
		'Scenarios (6), 4 cases to solve',
		'Scenarios (6), 3 cases to solve',
		'Scenarios (6), 2 cases to solve',
		'Scenarios (6), 1 case to solve',
		'Scenarios (6)'
	]);
	// The run's end moved no focus.
	await expect(resultsTab).toBeFocused();

	// Again, every case current: never silent, nothing sent.
	await page.keyboard.press('Control+Shift+Enter');
	await expect(notice(page, 'status')).toHaveText(/^\s*Every case's results are current\.\s*$/);
	expect(await seenLine(notice(page, 'status').locator('span').first())).toBe(true);
	expect(counter.n).toBe(7);

	// A held key's repeats start one run: one request, and no notice that it is running.
	await open(page, project);
	await showPane(page, 'Build');
	await buildPane(page)
		.getByRole('textbox', { name: /^Elevation/ })
		.focus();
	const held = await hold(page);
	const again = solveCounter(page);
	await page.keyboard.down('Control');
	await page.keyboard.down('Shift');
	await page.keyboard.down('Enter');
	await page.keyboard.down('Enter');
	await page.keyboard.down('Enter');
	await page.keyboard.up('Enter');
	await page.keyboard.up('Shift');
	await page.keyboard.up('Control');
	await expect.poll(() => held.length).toBe(1);
	await expect(notice(page, 'status')).toHaveCount(0);
	await held.release();
	await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6)', { timeout: 240_000 });
	expect(again.n).toBe(7);
	await expect(notice(page, 'status')).toHaveCount(0);

	// Ctrl+Enter from the field, the same way: Results shown, the focus on its tab.
	await showPane(page, 'Build');
	await buildPane(page)
		.getByRole('textbox', { name: /^Elevation/ })
		.focus();
	const answered = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await page.keyboard.press('Control+Enter');
	expect((await answered).status()).toBe(200);
	await expect(resultsTab).toHaveAttribute('aria-selected', 'true');
	await expect(resultsTab).toBeFocused();
});

// ---- 4. The menu's defects ------------------------------------------------------------------------

test('the Scenarios menu: Shift+Tab returns to Scenarios, Tab past it closes it, a pointer Cancel keeps it open', async ({
	page,
	browser
}) => {
	test.setTimeout(180_000);
	await open(page, await ownersProject(browser));
	const group = menuGroup(page);
	await scenariosButton(page).focus();
	await page.keyboard.press('Enter');
	await expect(group).toBeVisible();
	const all = solveAllButton(page);
	await expect(all).toHaveAccessibleName('Solve all (7)');
	await expect(all).toBeFocused();
	const line = page.locator(`[id="${await all.getAttribute('aria-describedby')}"]`);
	await expect(line).toHaveText(
		'Solves each case whose results are missing or out of date, one after another: up to 7 solves.'
	);
	expect(await seenLine(line), "Solve all's line on screen").toBe(true);

	// Shift+Tab from Solve all: Scenarios, the menu still open.
	await page.keyboard.press('Shift+Tab');
	await expect(scenariosButton(page)).toBeFocused();
	await expect(group).toBeVisible();
	// Tab through it: Solve all, the case shown, Manage scenarios…; then past it, which closes it.
	await page.keyboard.press('Tab');
	await expect(all).toBeFocused();
	await page.keyboard.press('Tab');
	await expect(caseMenu(page)).toBeFocused();
	await page.keyboard.press('Tab');
	await expect(group.getByRole('button', { name: 'Manage scenarios…' })).toBeFocused();
	await page.keyboard.press('Tab');
	await expect(group).toBeHidden();
	await expect(
		banner(page).getByRole('toolbar', { name: 'Project' }).getByRole('button', { name: /^Undo/ })
	).toBeFocused();

	// A pointer Cancel during a held run: the menu stays open, its cancel line seen.
	const held = await hold(page);
	await solveAll(page);
	await expect.poll(() => held.length).toBe(1);
	const status = group.getByRole('status');
	await expect(status).toHaveText('Solving 1 of 7: Base case…');
	await banner(page).getByRole('button', { name: 'Cancel solving all cases' }).click();
	await expect(status).toHaveText(
		'Solve all was cancelled: the cases not solved keep what they had.'
	);
	await expect(group).toBeVisible();
	expect(await seenBox(status), 'the cancel line seen').toBe(true);
	expect(await seenLine(status), 'the cancel line seen as text').toBe(true);
	await expect(all).toHaveAccessibleName('Solve all (7)');
	for (const route of held.splice(0)) await route.abort().catch(() => {});
	await page.unroute('**/api/v1/solve');
});

test('a network stop with the menu closed raises an alert naming the cases left; Solve all resumes them', async ({
	page,
	browser
}) => {
	test.setTimeout(300_000);
	await open(page, await ownersProject(browser));
	// The base case's request held until the menu is closed; the next one fails at the network.
	const held: Route[] = [];
	let requests = 0;
	await page.route('**/api/v1/solve', (route) => {
		requests++;
		if (requests === 1) held.push(route);
		else if (requests === 2) void route.abort('failed');
		else void route.continue();
	});
	await solveAll(page);
	await expect.poll(() => held.length).toBe(1);
	await page.keyboard.press('Escape');
	await expect(menuGroup(page)).toBeHidden();
	await held[0]!.continue();
	const alert = notice(page, 'alert');
	await expect(alert).toHaveText(
		/^\s*Solve all stopped after a network error: The calculation server could not be reached\. Check your connection and try again; your project is safe in this page and its link\. Solve all, in the Scenarios menu, solves the 6 cases left\.\s*$/
	);
	expect(await seenLine(alert.locator('span').first()), 'the alert seen as text').toBe(true);
	// The badge keeps the count the alert names.
	await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6), 6 cases to solve');
	const badge = await headerParts(page);
	expect(badge.badgeText).toBe('6');

	await page.unroute('**/api/v1/solve');
	const counter = solveCounter(page);
	await solveAll(page);
	await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6)', { timeout: 240_000 });
	expect(counter.n).toBe(6);
});

// ---- 5. The trace, its results out of date --------------------------------------------------------

/** Solve the base case, leave it out of date with a Build edit, and open a node's trace. */
async function staleTrace(page: Page, project: Project): Promise<Locator> {
	await open(page, project);
	await solveConverged(page);
	await editElevation(page);
	await showPane(page, 'Results');
	const nodes = await resultsView(page, 'Nodes');
	await nodes
		.getByRole('button', { name: /^Cooling tower basin/ })
		.first()
		.click();
	const trace = traceOf(page, 'Cooling tower basin');
	await expect(trace).toBeVisible();
	return trace;
}

const STALE_VALUES =
	'Results are out of date: the project changed after this solve. These values are from before the change.';

test("on a phone the trace's sheet keeps Solve again, which solves", async ({ page, browser }) => {
	test.setTimeout(180_000);
	await page.setViewportSize({ width: 390, height: 844 });
	const trace = await staleTrace(page, await ownersProject(browser));
	await expect(trace).toHaveJSProperty('tagName', 'DIALOG');
	const words = trace.locator('p', { hasText: /^\s*Results are out of date/ });
	expect(squash(await words.innerText())).toBe(
		`${STALE_VALUES} Solve again to update the results.`
	);
	expect(await seenLine(words), "the sheet's out-of-date line on screen").toBe(true);
	const again = trace.getByRole('button', { name: 'Solve again', exact: true });
	expect(await seenBox(again)).toBe(true);
	const answered = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await again.click();
	expect((await answered).status()).toBe(200);
	await expect(words).toHaveCount(0);
	await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (6), 6 cases to solve');
});

test('from 1024 px the side panel names the header Solve and has no button of its own', async ({
	page,
	browser
}) => {
	test.setTimeout(180_000);
	await page.setViewportSize({ width: 1280, height: 800 });
	const keys = await finePointer(page);
	const trace = await staleTrace(page, await ownersProject(browser));
	await expect(trace).toHaveAttribute('role', 'region');
	const words = trace.locator('p', { hasText: /^\s*Results are out of date/ });
	expect(squash(await words.innerText())).toBe(
		`${STALE_VALUES} Press Solve, at the top${keys ? ' (Ctrl+Enter or ⌘+Enter)' : ''}, to update them.`
	);
	expect(await seenLine(words), "the panel's out-of-date line on screen").toBe(true);
	await expect(trace.getByRole('button', { name: SOLVE_ONE })).toHaveCount(0);
	await oneEach(page, false, 'the side-panel trace open, out of date');
});

// ---- 6. Short screens -----------------------------------------------------------------------------

for (const [width, height] of [
	[568, 320],
	[640, 320]
] as const) {
	test(`short ${width}×${height}: one pinned row, Solve in view, focus never under it, the menu's foot reachable`, async ({
		page,
		browser
	}) => {
		test.setTimeout(180_000);
		await page.setViewportSize({ width, height });
		await open(page, await ownersProject(browser));
		await solveConverged(page);
		await showPane(page, 'Results');

		const top = await headerParts(page);
		expect(top.position, 'the header pinned').toBe('sticky');
		expect(top.header.bottom - top.header.top, 'the pinned row').toBeLessThanOrEqual(PINNED_ROW);
		// One row: the name, Scenarios and Solve side by side.
		expect(Math.abs(top.name.top - top.solve.top), 'the name and Solve in one row').toBeLessThan(1);
		expect(
			Math.abs(top.scenarios.top - top.solve.top),
			'Scenarios and Solve in one row'
		).toBeLessThan(1);
		if (width === 568) {
			expect(top.name.width, 'the project name at 568×320').toBeGreaterThanOrEqual(NAME_SHORT);
		}
		expect(top.sideways, 'no sideways scroll').toBe(0);

		// Results scrolled to its end: Solve still in view, within the row.
		await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
		await expect
			.poll(() => page.evaluate(() => window.scrollY), { message: 'the page scrolled' })
			.toBeGreaterThan(0);
		const solve = (await headerSolve(page).boundingBox())!;
		expect(solve.y, "Solve's top, the page at its end").toBeGreaterThanOrEqual(0);
		expect(solve.y + solve.height, "Solve's bottom, the page at its end").toBeLessThanOrEqual(
			PINNED_ROW
		);

		// A control reached by Tab while it sits under the pinned row is scrolled clear of it
		// (scroll-padding-top): the Results view's tab, scrolled to the row's middle, Tab pressed
		// from the control before it in the page (focused where it is).
		const row = top.header.bottom;
		const target = resultsPane(page)
			.getByRole('tablist', { name: 'Results view' })
			.getByRole('tab', { selected: true });
		const under = await target.evaluate((el, middle) => {
			window.scrollBy(0, el.getBoundingClientRect().top - middle);
			return el.getBoundingClientRect().top;
		}, row / 2);
		expect(under, 'the tab under the pinned row, before Tab').toBeLessThan(row);
		await target.evaluate((el) => {
			const stops = [
				...document.querySelectorAll<HTMLElement>(
					'a[href], button, input, select, textarea, summary, [tabindex]'
				)
			].filter(
				(e) =>
					e.tabIndex >= 0 &&
					!(e as HTMLButtonElement).disabled &&
					!e.closest('[inert]') &&
					e.checkVisibility()
			);
			stops[stops.indexOf(el as HTMLElement) - 1]!.focus({ preventScroll: true });
		});
		await page.keyboard.press('Tab');
		await expect(target).toBeFocused();
		const focused = (await target.boundingBox())!;
		expect(focused.y, 'the tab focused below the pinned row').toBeGreaterThanOrEqual(row - 0.5);

		// The menu's foot: Manage scenarios… reached in the menu's own scroll, and it opens.
		await openCases(page);
		const manage = menuGroup(page).getByRole('button', { name: 'Manage scenarios…' });
		await manage.scrollIntoViewIfNeeded();
		await expect(manage).toBeInViewport({ ratio: 1 });
		const box = (await manage.boundingBox())!;
		expect(box.y, 'Manage scenarios… below the pinned row').toBeGreaterThanOrEqual(row);
		await manage.click();
		await expect(page.getByRole('dialog', { name: 'Scenarios' })).toBeVisible();
	});
}

for (const [width, height] of [
	[320, 256],
	[480, 320]
] as const) {
	test(`short and narrow ${width}×${height}: the page scrolls as one, the header with it (WCAG 1.4.10)`, async ({
		page,
		browser
	}) => {
		test.setTimeout(180_000);
		await page.setViewportSize({ width, height });
		await open(page, await ownersProject(browser));
		await solveConverged(page);
		const top = await headerParts(page);
		expect(top.position, 'the header not pinned').not.toBe('sticky');
		expect(top.sideways, 'no sideways scroll').toBe(0);
		await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
		await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
		const solve = (await headerSolve(page).boundingBox())!;
		expect(solve.y + solve.height, 'Solve scrolled away with the page').toBeLessThanOrEqual(0);
		// A Build field is reached by the page's scroll, as before (build-density.md §11 item 14).
		await showPane(page, 'Build');
		const elevation = buildPane(page).getByRole('textbox', { name: /^Elevation/ });
		await elevation.scrollIntoViewIfNeeded();
		await expect(elevation).toBeInViewport({ ratio: 1 });
	});
}

// ---- 7. The spinner -------------------------------------------------------------------------------

for (const [width, height] of [
	[390, 844],
	[1280, 800]
] as const) {
	test(`the Scenarios spinner keeps its 20 px during Solve all, at ${width} px`, async ({
		page,
		browser
	}) => {
		test.setTimeout(120_000);
		await page.setViewportSize({ width, height });
		await open(page, await ownersProject(browser));
		const held = await hold(page);
		await solveAll(page);
		await expect.poll(() => held.length).toBe(1);
		await page.keyboard.press('Escape');
		const parts = await headerParts(page);
		expect(parts.icon).toEqual({ width: 20, height: 20 });
		await expect(scenariosButton(page).locator(':scope > svg')).toHaveClass(/animate-spin/);
		await cancelHeld(page, held);
	});
}

// ---- 8. axe ---------------------------------------------------------------------------------------

async function axeClean(page: Page, selector: string, where: string) {
	const scan = await new AxeBuilder({ page }).include(selector).withTags(AXE_TAGS).analyze();
	expect(
		scan.violations.map((v) => `${v.id} (${v.nodes.length})`),
		`axe, ${where}`
	).toEqual([]);
}

test("axe finds no violation: the menu with the amber badge, E1, Compare's amber line, the trace's sheet", async ({
	page,
	browser
}) => {
	test.setTimeout(180_000);
	const project = await ownersProject(browser);
	await open(page, project);
	await openCases(page);
	expect((await headerParts(page)).badgeClass).toContain('bg-amber-400');
	await axeClean(page, 'header', 'the menu open, the amber badge');
	await page.keyboard.press('Escape');

	await showPane(page, 'Results');
	await expect(resultsPane(page).getByText('Base case has not been solved yet.')).toBeVisible();
	await axeClean(page, 'section[aria-label="Results"]', 'Results E1');

	await resultsPane(page).getByRole('tab', { name: 'Compare cases' }).click();
	await expect(
		resultsPane(page)
			.getByRole('region', { name: 'Compare cases' })
			.locator('p', {
				hasText: /missing or out of date/
			})
	).toBeVisible();
	await axeClean(page, 'section[aria-label="Results"]', "Compare's amber line");

	await page.setViewportSize({ width: 390, height: 844 });
	const trace = await staleTrace(page, project);
	await expect(trace.getByRole('button', { name: 'Solve again', exact: true })).toBeVisible();
	await axeClean(page, 'dialog[open]', "the phone's trace sheet");
});
