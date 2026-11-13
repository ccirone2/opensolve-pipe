/**
 * Helpers shared by the end-to-end flows: the workspace panes, building a network through the
 * panel navigator, solving against the real API, and reading the results tables as displayed.
 * Selectors are accessible roles and names only.
 */
import { readFile } from 'node:fs/promises';
import { inflateRawSync } from 'node:zlib';
import { expect, type Download, type Locator, type Page } from '@playwright/test';
import type { ErrorResponse, SolvedState, SolveRequest, SolveResponse } from '../src/lib/api/types';
import { gzip } from 'pako';
import { createEmptyProject } from '../src/lib/utils/factory';
import { canonicalJson } from '../src/lib/utils/json';
import { SI_UNITS } from '../src/lib/utils/units';
import { API_ORIGIN, WEB_ORIGIN } from './servers';

export const buildPane = (page: Page) => page.getByRole('region', { name: 'Build', exact: true });
export const resultsPane = (page: Page) =>
	page.getByRole('region', { name: 'Results', exact: true });

/** The panel navigator's current component heading. */
export const currentHeading = (page: Page) => buildPane(page).getByRole('heading', { level: 2 });

/**
 * Show a pane. On narrow screens Build and Results are tabs; on wide ones both are shown and
 * the tabs are hidden.
 */
export async function showPane(page: Page, pane: 'Build' | 'Results'): Promise<void> {
	const tab = page
		.getByRole('tablist', { name: 'View' })
		.getByRole('tab', { name: new RegExp(`^${pane}`) });
	if (await tab.isVisible()) await tab.click();
	await expect(pane === 'Build' ? buildPane(page) : resultsPane(page)).toBeVisible();
}

/**
 * An empty project in SI display units, as the flows below type and read their values: a new
 * project starts in US customary units (proposal build-density.md §13; home.e2e.ts checks that
 * path), so this one is opened from its link, as utils/encoding.ts writes it.
 */
export async function newProject(page: Page): Promise<void> {
	const project = createEmptyProject({ units: SI_UNITS });
	const bytes = gzip(new TextEncoder().encode(canonicalJson(project)), { level: 9 });
	await page.goto(`/p#${Buffer.from(bytes).toString('base64url')}`);
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(buildPane(page).getByRole('heading', { name: 'Start the network' })).toBeVisible();
}

/** Add the first component of an empty project ("Reservoir", "Gate valve", ...). */
export async function addFirst(page: Page, kind: string, name: string): Promise<void> {
	const panel = buildPane(page);
	await panel.getByRole('combobox', { name: 'First component' }).selectOption({ label: kind });
	await panel.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText(name);
}

/**
 * Add a component after the current one, at its free port (Add after), and check the navigator
 * walked on to it.
 */
export async function addAfter(page: Page, kind: string, name: string): Promise<void> {
	await buildPane(page).getByRole('button', { name: 'Add after' }).click();
	const dialog = page.getByRole('dialog', { name: /^Add after/ });
	await expect(dialog.getByRole('radio', { name: /^At a free port/ })).toBeChecked();
	await dialog.getByRole('combobox', { name: 'Component' }).selectOption({ label: kind });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog).toBeHidden();
	await expect(currentHeading(page)).toHaveText(name);
}

/** Type a number into a unit-aware field and store it (Enter). */
export async function setNumber(scope: Locator, name: string | RegExp, value: string) {
	const field = scope.getByRole('textbox', { name });
	await field.fill(value);
	await field.press('Enter');
	await expect(field).toHaveValue(value);
	await expect(field).not.toHaveAttribute('aria-invalid', 'true');
}

/** The API's answer to a solve: a SolveResponse (200) or an ErrorResponse (e.g. 422). */
export interface SolveAnswer {
	status: number;
	body: Partial<SolveResponse> & Partial<ErrorResponse>;
	/** What the app sent: the project and the solve options. */
	request: SolveRequest;
}

/**
 * Press the header's Solve and wait for the API's answer. In a project with scenarios the button
 * names the case shown, the base case when a link has just been opened (D15).
 */
export async function solve(page: Page): Promise<SolveAnswer> {
	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await page
		.getByRole('banner')
		.getByRole('button', { name: /^Solve( Base case)?$/ })
		.click();
	const response = await answer;
	return {
		status: response.status(),
		body: (await response.json()) as SolveAnswer['body'],
		request: response.request().postDataJSON() as SolveRequest
	};
}

/**
 * Solve, and check the solve converged and its results are shown. The app solves without system
 * curves (D10: the pump chart fetches the one it shows).
 */
export async function solveConverged(page: Page): Promise<SolvedState> {
	const { status, body, request } = await solve(page);
	expect(request.options?.includeSystemCurve).toBe(false);
	expect(status, JSON.stringify(body).slice(0, 500)).toBe(200);
	expect(body.success).toBe(true);
	expect(body.solvedState?.converged).toBe(true);
	await expect(resultsPane(page).getByRole('heading', { name: 'Converged' })).toBeVisible();
	// With scenarios the status names the case (D15).
	await expect(resultsPane(page).getByRole('status')).toHaveText(
		/^Last solve( of Base case)?: converged$/
	);
	return body.solvedState!;
}

/**
 * The Results pane's own scroller, the column that scrolls the view shown (ResultsPanel.svelte's
 * `overflow-y-auto`, the first ancestor of the "Results view" row that scrolls): its visible width
 * and the width of what it holds, in px. The page can keep still while this scrolls sideways
 * (proposal pumps-results-layout.md §2.1 and F10: the "Also found" buttons), so a check of
 * `document.documentElement` alone misses it. Null while the pane shows no results view.
 */
export async function resultsScroller(
	page: Page
): Promise<{ clientWidth: number; scrollWidth: number } | null> {
	return page.evaluate(() => {
		const pane = document.querySelector('section[aria-label="Results"]');
		const row = pane?.querySelector('[role="tablist"][aria-label="Results view"]');
		if (!pane || !row || !row.checkVisibility()) return null;
		for (let e = row.parentElement; e && e !== pane; e = e.parentElement) {
			if (/(auto|scroll)/.test(getComputedStyle(e).overflowY)) {
				return { clientWidth: e.clientWidth, scrollWidth: e.scrollWidth };
			}
		}
		return null;
	});
}

/** Show one of the results views (Summary, Nodes, Links, Pumps, ...). */
export async function resultsView(page: Page, view: string): Promise<Locator> {
	const tab = resultsPane(page)
		.getByRole('tablist', { name: 'Results view' })
		.getByRole('tab', { name: view, exact: true });
	await tab.click();
	await expect(tab).toHaveAttribute('aria-selected', 'true');
	return resultsPane(page).getByRole('tabpanel', { name: view, exact: true });
}

const squash = (text: string) => text.replace(/\s+/g, ' ').trim();

/**
 * The displayed text of a results-table cell: the row whose header starts with `row`, in the
 * column whose heading (label and unit) is `column`, e.g. ("Reservoir R1 → Pump P1", "Flow L/s").
 */
export async function cellText(table: Locator, row: string, column: string): Promise<string> {
	await expect(table.getByRole('row').first()).toBeVisible();
	const headings = (await table.getByRole('columnheader').allInnerTexts()).map(squash);
	const index = headings.indexOf(column);
	expect(index, `column “${column}” in ${JSON.stringify(headings)}`).toBeGreaterThan(0);
	const match = table
		.getByRole('row')
		.filter({ has: table.page().getByRole('rowheader', { name: row }) });
	await expect(match).toHaveCount(1);
	return squash(
		await match
			.getByRole('cell')
			.nth(index - 1)
			.innerText()
	);
}

/**
 * An element's text as the app tells it (a topology issue, a system-curve point's reason): without
 * the calculation server's own messages, which it keeps under Details.
 */
export async function toldText(locator: Locator): Promise<string> {
	return squash(
		await locator.evaluate((element) => {
			const copy = element.cloneNode(true) as HTMLElement;
			copy.querySelectorAll('[data-issue-detail]').forEach((detail) => detail.remove());
			return copy.textContent ?? '';
		})
	);
}

/** Every row of a table as displayed (headers and cells), to compare two solves. */
export async function tableTexts(table: Locator): Promise<string[]> {
	await expect(table.getByRole('row').first()).toBeVisible();
	return (await table.getByRole('row').allInnerTexts()).map(squash);
}

/**
 * A chart's curve table: since S7 each in its own disclosure, "{caption} ({n} points)"
 * (proposal pumps-results-layout.md §9 S7). The disclosure, by its table's caption.
 */
export function curveTableFold(scope: Locator, caption: string): Locator {
	// Its own summary, by its whole words (a regular expression meets the text as it is, the
	// space before and after included): they match no Details summary inside its table.
	const words = caption.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
	return scope.locator('details[data-curve-table]').filter({
		has: scope.page().locator('summary', {
			hasText: new RegExp(`^\\s*${words} \\(\\d+ points?\\)\\s*$`)
		})
	});
}

/**
 * Open a curve table's disclosure as a user would, by its summary, where it is closed by default
 * (the chart drawn, no reason column with entries: §9 S7), and return its table, in sight.
 */
export async function openCurveTable(scope: Locator, caption: string): Promise<Locator> {
	const fold = curveTableFold(scope, caption);
	await expect(fold).toHaveCount(1);
	await expect(fold, `"${caption}" closed until opened`).not.toHaveAttribute('open');
	// Its own summary, the first in it (a Details summary inside its table comes after).
	await fold.locator('summary').first().click();
	await expect(fold).toHaveAttribute('open', '');
	const table = scope.getByRole('table', { name: caption, exact: true });
	await expect(table).toBeVisible();
	return table;
}

/** A number as shown in the results: 4 significant figures. */
export const sig4 = (value: number) => String(Number(value.toPrecision(4)));
/** Rounded toward zero to 4 significant digits: how a bound a value must stay below is shown. */
export const down4 = (value: number) => {
	const scale = 10 ** (3 - Math.floor(Math.log10(Math.abs(value))));
	return String(Math.trunc(value * scale) / scale);
};

/**
 * Half a unit in the last displayed digit of a number shown as `text` ("12.81" → 0.005): the
 * rounding a displayed value can carry.
 */
export function halfUlp(text: string): number {
	const decimals = text.split('.')[1]?.length ?? 0;
	return 0.5 * 10 ** -decimals;
}

/** The trace of an element: a panel over the results (wide screens) or a dialog (narrow). */
export function traceOf(page: Page, name: string): Locator {
	return page
		.getByRole('dialog', { name, exact: true })
		.or(resultsPane(page).getByRole('region', { name, exact: true }))
		.first();
}

/** Close an element's trace (its close button) and check it is gone. */
export async function closeTrace(page: Page, name: string): Promise<void> {
	const trace = traceOf(page, name);
	await trace.getByRole('button', { name: 'Close', exact: true }).click();
	await expect(traceOf(page, name)).toBeHidden();
}

/** Origins the app may contact: itself and its calculation server (GOALS §4.5). */
export const ALLOWED_ORIGINS = new Set([WEB_ORIGIN, API_ORIGIN]);

/**
 * The Scenarios menu (proposal build-density.md §13, §19): the header's Scenarios button opens it
 * once the project has scenarios; it holds Solve all first (the page's one Solve all, with its
 * count while it can run, its line and its progress), then the case shown (Case) and Manage
 * scenarios…. These read it whether it is open or not (includeHidden); openCases opens it to act
 * in it.
 */
export const caseMenu = (page: Page) =>
	page.getByRole('combobox', { name: 'Case', exact: true, includeHidden: true });
export const caseGroup = (page: Page) =>
	page.getByRole('group', { name: 'Case', exact: true, includeHidden: true });

export async function openCases(page: Page): Promise<Locator> {
	const group = page.getByRole('group', { name: 'Case', exact: true });
	if (!(await group.isVisible())) {
		await page.getByRole('button', { name: /^Scenarios/ }).click();
	}
	await expect(group).toBeVisible();
	return group;
}

/**
 * Solve all, the Scenarios menu's first button and the page's one Solve all (build-density.md
 * §19): "Solve all (n)" while it can run, "Solve all" otherwise. Read whether the menu is open or
 * not (includeHidden).
 */
export const solveAllButton = (page: Page) =>
	caseGroup(page).getByRole('button', { name: /^Solve all( \(\d+\))?$/, includeHidden: true });

/** Solve all, from the Scenarios menu (its one home): press it; `done` waits for the run's end. */
export async function solveAll(page: Page, opts: { done?: boolean } = {}): Promise<void> {
	await (await openCases(page)).getByRole('button', { name: /^Solve all/ }).click();
	if (opts.done) await expect(caseGroup(page)).not.toContainText('Solving', { timeout: 180_000 });
}

/** Show a case: from the Scenarios menu, which closes with the choice. */
export async function chooseCase(page: Page, label: string): Promise<void> {
	await openCases(page);
	await caseMenu(page).selectOption({ label });
	await expect(page.getByRole('group', { name: 'Case', exact: true })).toBeHidden();
}

/** Open the scenario manager: directly, or from the Scenarios menu once there are scenarios. */
export async function openScenarioManager(page: Page): Promise<Locator> {
	await page.getByRole('button', { name: /^Scenarios/ }).click();
	const manage = page.getByRole('button', { name: 'Manage scenarios…' });
	if (await manage.isVisible()) await manage.click();
	const manager = page.getByRole('dialog', { name: 'Scenarios' });
	await expect(manager).toBeVisible();
	return manager;
}

// ---------------------------------------------------------------------------------------------
// Downloads (the export, proposal export.md §7.3)
// ---------------------------------------------------------------------------------------------

/**
 * Press `control` and return the download, with every request the page made from the click to
 * the download event.
 */
export async function downloadFrom(
	page: Page,
	control: Locator
): Promise<{ download: Download; bytes: Buffer; requests: { url: string; method: string }[] }> {
	const requests: { url: string; method: string }[] = [];
	const listener = (r: { url(): string; method(): string }) =>
		requests.push({ url: r.url(), method: r.method() });
	page.on('request', listener);
	const [download] = await Promise.all([page.waitForEvent('download'), control.click()]);
	page.off('request', listener);
	const path = await download.path();
	return { download, bytes: await readFile(path), requests };
}

/** No request but a GET of the app's own static chunk (same origin, /_app/immutable/, no query). */
export function expectNothingSent(requests: { url: string; method: string }[]) {
	for (const request of requests) {
		const url = new URL(request.url);
		if (url.protocol === 'blob:' || url.protocol === 'data:') continue;
		expect(request.method, request.url).toBe('GET');
		expect(url.origin, request.url).toBe(WEB_ORIGIN);
		expect(url.pathname, request.url).toMatch(/^\/_app\/immutable\//);
		expect(url.search, request.url).toBe('');
	}
}

/** Every entry of a zip, in central-directory order, read by APPNOTE's offsets. */
export function readZip(bytes: Buffer): { name: string; flags: number; data: Buffer }[] {
	const end = bytes.length - 22;
	expect(bytes.readUInt32LE(end)).toBe(0x06054b50);
	const count = bytes.readUInt16LE(end + 10);
	let at = bytes.readUInt32LE(end + 16);
	const entries: { name: string; flags: number; data: Buffer }[] = [];
	for (let i = 0; i < count; i++) {
		expect(bytes.readUInt32LE(at)).toBe(0x02014b50);
		const flags = bytes.readUInt16LE(at + 8);
		const method = bytes.readUInt16LE(at + 10);
		const compressed = bytes.readUInt32LE(at + 20);
		const size = bytes.readUInt32LE(at + 24);
		const nameLength = bytes.readUInt16LE(at + 28);
		const extra = bytes.readUInt16LE(at + 30);
		const comment = bytes.readUInt16LE(at + 32);
		const offset = bytes.readUInt32LE(at + 42);
		const name = bytes.subarray(at + 46, at + 46 + nameLength).toString('utf8');
		expect(bytes.readUInt32LE(offset)).toBe(0x04034b50);
		const start = offset + 30 + bytes.readUInt16LE(offset + 26) + bytes.readUInt16LE(offset + 28);
		const raw = bytes.subarray(start, start + compressed);
		const data = method === 8 ? inflateRawSync(raw) : Buffer.from(raw);
		expect(data.length).toBe(size);
		entries.push({ name, flags, data });
		at += 46 + nameLength + extra + comment;
	}
	return entries;
}

/** A workbook's sheets by name: their XML, and the shared strings. */
export function readWorkbook(bytes: Buffer): { sheets: Map<string, string>; strings: string } {
	const parts = new Map(readZip(bytes).map((e) => [e.name, e.data.toString('utf8')]));
	const workbook = parts.get('xl/workbook.xml')!;
	const rels = parts.get('xl/_rels/workbook.xml.rels')!;
	const sheets = new Map<string, string>();
	for (const [, name, rid] of workbook.matchAll(/<sheet name="([^"]+)"[^>]*r:id="([^"]+)"/g)) {
		const target = new RegExp(
			`Id="${rid}"[^>]*Target="([^"]+)"|Target="([^"]+)"[^>]*Id="${rid}"`
		).exec(rels)!;
		sheets.set(name!, parts.get(`xl/${(target[1] ?? target[2])!.replace(/^\/?xl\//, '')}`)!);
	}
	return { sheets, strings: parts.get('xl/sharedStrings.xml') ?? '' };
}
