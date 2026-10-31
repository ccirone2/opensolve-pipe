import { gzipSync, inflateRawSync, inflateSync } from 'node:zlib';
import { readFile } from 'node:fs/promises';
import { expect, test, type Download, type Locator, type Page } from '@playwright/test';
import type { SolveResponse } from '../src/lib/api/types';
import { pumpTransferExample } from '../src/lib/utils/examples';
import {
	caseGroup,
	currentHeading,
	openCases,
	resultsPane,
	resultsView,
	showPane,
	solveConverged
} from './support';
import { WEB_ORIGIN } from './servers';

/**
 * Export (proposal export.md §7.3) against the real app and API, on desktop and on a phone: the
 * results workbook, the CSV files in a zip, a project with scenarios exported as all cases, the
 * pump chart as a PNG, and the states (unavailable during a solve, out of date, a solve that did
 * not converge). Each file is read here independently of the app's writers: the zip by PKWARE
 * APPNOTE's offsets with node:zlib, the PNG by its chunks. Every expected number comes from the
 * intercepted /solve response, converted here. From the click to the download no request is made
 * but a GET of the app's own static chunk (same origin, /_app/immutable/, no query): the file is
 * made in the browser and nothing is sent.
 *
 * Network: the home page's pump-transfer example (illustrative, made-up inputs). The scenario's
 * value (a 6 m discharge-tank level) is a made-up test input. Names are ASCII: with LANG unset, as
 * in CI, Chromium saves a non-ASCII name as "download" (Unicode names are tested in Vitest).
 */

const STAMP = String.raw`\d{4}-\d\d-\d\d \d{4}`;

/** The link format of D3: JSON → gzip → base64url without padding (the app reads any gzip). */
function encode(project: unknown): string {
	return gzipSync(Buffer.from(JSON.stringify(project))).toString('base64url');
}

async function openExample(page: Page) {
	await page.goto('/');
	await page.getByRole('link', { name: /^Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(currentHeading(page)).toHaveText('Suction tank');
}

/** Solve, and keep the API's answer (the oracle of every number in the files). */
async function solveAndKeep(page: Page): Promise<SolveResponse> {
	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await solveConverged(page);
	const body = (await (await answer).json()) as SolveResponse;
	await showPane(page, 'Results');
	return body;
}

const exportButton = (page: Page) => resultsPane(page).locator('[data-export-button]');

async function openExport(page: Page): Promise<Locator> {
	await exportButton(page).click();
	const dialog = page.getByRole('dialog', { name: 'Export results' });
	await expect(dialog).toBeVisible();
	return dialog;
}

/**
 * Press `control` and return the download, with every request the page made from the click to
 * the download event.
 */
async function downloadFrom(
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
function expectNothingSent(requests: { url: string; method: string }[]) {
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
function readZip(bytes: Buffer): { name: string; flags: number; data: Buffer }[] {
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
function readWorkbook(bytes: Buffer): { sheets: Map<string, string>; strings: string } {
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

/** The Pressure of the pump's suction port in the response, Pa gauge. */
const suctionPressure = (body: SolveResponse) =>
	body.solvedState.nodeResults['P1:suction']!.pressure;

test('the results workbook, made in the browser', async ({ page }) => {
	await openExample(page);
	const body = await solveAndKeep(page);
	await expect(exportButton(page)).toHaveAccessibleName('Export results');
	const dialog = await openExport(page);
	const download = dialog.getByRole('button', { name: 'Download' });
	await expect(download).toBeFocused();
	const made = await downloadFrom(page, download);
	expect(made.download.suggestedFilename()).toMatch(
		new RegExp(`^Pump transfer between two tanks - results ${STAMP}\\.xlsx$`)
	);
	expectNothingSent(made.requests);
	expect([...made.bytes.subarray(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04]);
	const names = readZip(made.bytes).map((e) => e.name);
	for (const part of [
		'[Content_Types].xml',
		'_rels/.rels',
		'docProps/core.xml',
		'xl/workbook.xml',
		'xl/_rels/workbook.xml.rels',
		'xl/styles.xml',
		'xl/sharedStrings.xml'
	]) {
		expect(names).toContain(part);
	}
	const { sheets, strings } = readWorkbook(made.bytes);
	expect([...sheets.keys()].slice(0, 3)).toEqual(['About', 'Flags', 'Nodes']);
	// Display units (kPa): the response's Pa converted here, written at full precision.
	expect(sheets.get('Nodes')).toContain(`<v>${String(suctionPressure(body) / 1000)}</v>`);
	expect(strings).toContain('Pressure [kPa(g)]');
	await expect(dialog.getByRole('status')).toHaveText(
		new RegExp(
			`^“${made.download.suggestedFilename().replace(/[.()]/g, '\\$&')}” \\(.+\\) is ready; your browser saves it to its downloads\\.$`
		)
	);
	// Esc closes the dialog and gives the focus back to Export.
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
	await expect(exportButton(page)).toBeFocused();
});

test('CSV files in SI base units, in one zip', async ({ page }) => {
	await openExample(page);
	const body = await solveAndKeep(page);
	const dialog = await openExport(page);
	await dialog.getByRole('radio', { name: /^CSV files \(\.zip\)/ }).check();
	await dialog.getByRole('radio', { name: /^SI base units/ }).check();
	const made = await downloadFrom(page, dialog.getByRole('button', { name: 'Download' }));
	expect(made.download.suggestedFilename()).toMatch(
		new RegExp(`^Pump transfer between two tanks - results \\(CSV\\) ${STAMP}\\.zip$`)
	);
	expectNothingSent(made.requests);
	const entries = readZip(made.bytes);
	const folder = new RegExp(`^results ${STAMP}/`);
	expect(entries.every((e) => folder.test(e.name))).toBe(true);
	const files = entries.map((e) => e.name.replace(folder, ''));
	expect(files.slice(0, 3)).toEqual(['README.txt', 'about.csv', 'flags.csv']);
	expect(files).toContain('nodes.csv');
	// UTF-8 names flagged.
	expect(entries.every((e) => (e.flags & 0x0800) !== 0)).toBe(true);

	const nodes = entries.find((e) => e.name.endsWith('/nodes.csv'))!.data;
	expect([...nodes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
	const text = nodes.subarray(3).toString('utf8');
	expect(text.endsWith('\r\n')).toBe(true);
	expect(text.replace(/\r\n/g, '')).not.toMatch(/\n/);
	const [header, ...rows] = text.split('\r\n');
	expect(header).toMatch(/^Solved at,Results,Component id,/);
	expect(header).toContain('Pressure [Pa(g)]');
	// SI: the response's own double, as String(n).
	const suction = rows.find((r) => /,P1,.*,suction,/.test(r))!;
	expect(suction.split(',')).toContain(String(suctionPressure(body)));

	const about = entries
		.find((e) => e.name.endsWith('/about.csv'))!
		.data.subarray(3)
		.toString('utf8');
	expect(about.split('\r\n')[1]).toMatch(/^Reading this file,/);
});

test('a project with a scenario: all cases from Compare cases', async ({ page }) => {
	// The project's scenarios as the link holds them (Project.scenarios, D15).
	const project = {
		...pumpTransferExample(),
		scenarios: [
			{
				id: 'S1',
				name: 'Higher tank',
				overrides: [{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 }]
			}
		]
	};
	await page.goto(`/p#${encode(project)}`);
	await expect(currentHeading(page)).toHaveText('Suction tank');
	await showPane(page, 'Results');
	const solveAll = (await openCases(page)).getByRole('button', { name: 'Solve all' });
	// Solve all: the base, then the scenario, one request after the other.
	let answered = 0;
	page.on('response', (r) => {
		if (r.url().endsWith('/api/v1/solve') && r.status() === 200) answered++;
	});
	await solveAll.click();
	await expect.poll(() => answered).toBe(2);
	await expect(caseGroup(page)).not.toContainText('Solving');
	await resultsPane(page).getByRole('tab', { name: 'Compare cases' }).click();
	await expect(exportButton(page)).toHaveAccessibleName('Export results of all cases');
	const dialog = await openExport(page);
	await expect(
		dialog.getByRole('radio', { name: /^All cases \(base and 1 scenario\)/ })
	).toBeChecked();
	const made = await downloadFrom(page, dialog.getByRole('button', { name: 'Download' }));
	expect(made.download.suggestedFilename()).toMatch(
		new RegExp(`^Pump transfer between two tanks - All cases - results ${STAMP}\\.xlsx$`)
	);
	expectNothingSent(made.requests);
	const { sheets, strings } = readWorkbook(made.bytes);
	expect([...sheets.keys()]).toContain('Compare cases');
	expect([...sheets.keys()]).not.toContain('Trace');
	expect(strings).toContain('<t>Case id</t>');
	expect(strings).toContain('<t>Higher tank</t>');
});

test('the pump chart as a PNG', async ({ page }) => {
	await openExample(page);
	await solveAndKeep(page);
	const pumps = await resultsView(page, 'Pumps');
	// Wait for the system curve, computed for this solve.
	await expect(pumps.getByText(/^System curve: the network of this solve/)).toBeVisible();
	const image = pumps.locator('[data-chart-image]');
	await expect(image).toHaveAccessibleName(
		'Download image of the pump and system curves: Transfer pump'
	);
	await expect(image).not.toHaveAttribute('aria-disabled', 'true');
	const made = await downloadFrom(page, image);
	expect(made.download.suggestedFilename()).toMatch(
		new RegExp(`^Pump transfer between two tanks - Transfer pump chart ${STAMP}\\.png$`)
	);
	expectNothingSent(made.requests);
	const png = made.bytes;
	expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
	expect(png.toString('latin1', 12, 16)).toBe('IHDR');
	const width = png.readUInt32BE(16);
	const height = png.readUInt32BE(20);
	expect(width).toBe(1600);
	// The plot (880 px) and its caption.
	expect(height).toBeGreaterThan(880);
	expect(png[24]).toBe(8); // bit depth
	const colorType = png[25]!;
	expect([2, 6]).toContain(colorType);
	// The image data: every IDAT chunk, inflated. The first row's first pixel is stored as it
	// is whatever the row's filter (no pixel to its left or above): it is opaque.
	const idat: Buffer[] = [];
	for (let at = 8; at < png.length;) {
		const length = png.readUInt32BE(at);
		const type = png.toString('latin1', at + 4, at + 8);
		if (type === 'IDAT') idat.push(png.subarray(at + 8, at + 8 + length));
		at += 12 + length;
	}
	const pixels = inflateSync(Buffer.concat(idat));
	const channels = colorType === 6 ? 4 : 3;
	expect(pixels.length).toBe(height * (1 + width * channels));
	if (colorType === 6) expect(pixels[1 + 3]).toBe(255);
	await expect(
		page.getByText(/” \(.+\) is ready; your browser saves it to its downloads\.$/)
	).toBeVisible();
});

test('unavailable while a solve runs; an out-of-date workbook says so', async ({ page }) => {
	await openExample(page);
	await solveAndKeep(page);
	// The next solve waits at the network until the test lets it through.
	let release: () => void = () => {};
	const held = new Promise<void>((resolve) => (release = resolve));
	await page.route('**/api/v1/solve', async (route) => {
		await held;
		await route.continue();
	});
	await page.getByRole('button', { name: 'Solve', exact: true }).click();
	await showPane(page, 'Results');
	await expect(exportButton(page)).toHaveAttribute('aria-disabled', 'true');
	await expect(exportButton(page)).toHaveAccessibleDescription(
		'A solve is running; export when it finishes, or Cancel stops it.'
	);
	// Pressed anyway (it keeps the focus, aria-disabled): nothing opens.
	await exportButton(page).click({ force: true });
	await expect(page.getByRole('dialog', { name: 'Export results' })).toHaveCount(0);
	release();
	await expect(exportButton(page)).not.toHaveAttribute('aria-disabled', 'true');
	await page.unroute('**/api/v1/solve');

	// Out of date: a value changed after the solve (a made-up discharge-tank level).
	await showPane(page, 'Build');
	await page
		.getByRole('region', { name: 'Build', exact: true })
		.getByRole('button', { name: 'Jump to a component' })
		.click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: /^Discharge tank/ })
		.click();
	const level = page
		.getByRole('region', { name: 'Build', exact: true })
		.getByRole('textbox', { name: /^Liquid level/ });
	await level.fill('6');
	await level.press('Enter');
	await showPane(page, 'Results');
	await expect(
		resultsPane(page)
			.getByText(/project changed after this solve/)
			.first()
	).toBeVisible();
	const dialog = await openExport(page);
	// The dialog opens at the top of its body, the warning in view, and Download focused in the
	// footer: focusing it scrolls nothing away (review W1), on desktop and on the phone.
	await expect(dialog.locator('[data-export-warning="stale"]')).toBeInViewport();
	await expect(dialog.getByRole('group', { name: 'Format' })).toBeInViewport();
	const focused = dialog.getByRole('button', { name: 'Download' });
	await expect(focused).toBeFocused();
	await expect(focused).toBeInViewport();
	await expect(focused).toHaveAccessibleDescription(/^The project changed after this solve\./);
	const made = await downloadFrom(page, focused);
	expectNothingSent(made.requests);
	const { strings } = readWorkbook(made.bytes);
	expect(strings).toContain(
		'Results out of date: the project changed after this solve. Solve again before using these results.'
	);
	expect(strings).toContain('OUT OF DATE: the project changed after this solve');
});

test('a solve that did not converge gives its record, without values', async ({ page }) => {
	await openExample(page);
	// The real answer, recorded and marked as not converged: no e2e flow has such a solve.
	await page.route('**/api/v1/solve', async (route) => {
		const response = await route.fetch();
		const body = (await response.json()) as SolveResponse;
		body.success = false;
		body.solvedState.converged = false;
		body.solvedState.convergence.message = 'made-up: the iteration limit was reached';
		await route.fulfill({ response, json: body });
	});
	await page.getByRole('button', { name: 'Solve', exact: true }).click();
	await showPane(page, 'Results');
	await expect(resultsPane(page).getByRole('heading', { name: 'Did not converge' })).toBeVisible();
	const dialog = await openExport(page);
	await expect(dialog.locator('[data-export-warning="not_converged"]')).toBeVisible();
	const made = await downloadFrom(page, dialog.getByRole('button', { name: 'Download' }));
	expect(made.download.suggestedFilename()).toMatch(
		new RegExp(`^Pump transfer between two tanks - results ${STAMP} \\(not converged\\)\\.xlsx$`)
	);
	expectNothingSent(made.requests);
	const { sheets } = readWorkbook(made.bytes);
	expect([...sheets.keys()]).toContain('About');
	expect([...sheets.keys()]).toContain('Flags');
	expect([...sheets.keys()]).not.toContain('Nodes');
	// Nor an image of it.
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
	const pumps = await resultsView(page, 'Pumps');
	await expect(pumps.locator('[data-chart-image]')).toHaveAccessibleDescription(
		'This solve did not converge: its values are not a solution, so no image is made.'
	);
});

test('on a phone the dialog is a bottom sheet, with Download reachable and focused', async ({
	page,
	isMobile
}) => {
	test.skip(!isMobile, 'phone layout');
	await openExample(page);
	await solveAndKeep(page);
	// Icon-only below a 30 rem header: 44 px wide, named by its label.
	const button = exportButton(page);
	await expect(button).toHaveAccessibleName('Export results');
	const box = (await button.boundingBox())!;
	expect(Math.round(box.width)).toBe(44);
	expect(Math.round(box.height)).toBeGreaterThanOrEqual(44);
	// The status line keeps its width beside it (on a phone the title is for screen readers: the
	// view tab says Results; proposal build-density.md §15).
	const status = resultsPane(page)
		.getByRole('status')
		.filter({ hasText: /^Last solve/ });
	expect((await status.boundingBox())!.height).toBeLessThan(30); // one line, not squeezed
	const dialog = await openExport(page);
	const viewport = page.viewportSize()!;
	const sheet = (await dialog.boundingBox())!;
	expect(Math.round(sheet.x)).toBe(0);
	expect(Math.round(sheet.width)).toBe(viewport.width);
	expect(Math.round(sheet.y + sheet.height)).toBe(viewport.height);
	const download = dialog.getByRole('button', { name: 'Download' });
	await expect(download).toBeFocused();
	// In the footer, in view without scrolling (review W1).
	await expect(download).toBeInViewport();
	const made = await downloadFrom(page, download);
	expect(made.download.suggestedFilename()).toMatch(
		new RegExp(`^Pump transfer between two tanks - results ${STAMP}\\.xlsx$`)
	);
	expectNothingSent(made.requests);
	expect([...made.bytes.subarray(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04]);
	// The page never scrolls sideways.
	expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
		viewport.width
	);
});
