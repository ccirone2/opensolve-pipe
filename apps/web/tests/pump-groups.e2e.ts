import { readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';
import type {
	ErrorResponse,
	Project,
	PumpGroupCurveRequest,
	PumpGroupCurveResponse,
	SolvedState,
	SolveRequest,
	SolveResponse
} from '../src/lib/api/types';
import {
	caseTagBoxes,
	curveTableFold,
	downloadFrom,
	expectNothingSent,
	halfUlp,
	openCurveTable,
	readWorkbook,
	resultsPane,
	resultsScroller,
	resultsView,
	solveAll,
	solveAllButton,
	solveConverged
} from './support';

/**
 * The Pumps together card (CLAUDE.md D21, proposal pump-groups.md §6), against the real app and
 * API, on desktop and on a phone: two pumps in parallel between Crane tees, two in series (US
 * display units) and two pumps the API refuses as a station (a tank on the discharge header).
 * Slice 4b (§7): the group system curve asked for after the group curve, drawn and listed in the
 * data table, the Group point at the curves' crossing, "Read along the curves", an FCV outside
 * the station (points without a rise, and why) and a PRV inside it (no group curve, the group
 * system curve all the same). Slice 4c: the export writes the group computed, in five sheets after
 * System curves, sending nothing. Slice 4d: the cases with one pump off added in one step and
 * solved with Solve all (the Scenarios menu's since build-density.md §19), each case's pumps in
 * Running combinations, each station duty a slate ring tagged with its case's number on the base
 * case's group system curve, offered for pumps in parallel only, and axe clean with everything
 * open; since D24 through the Add cases block with Each pump off chosen. D24 slice L1b
 * (pump-lineups.md §10.1): By number running on four pumps, the stop order moved by keyboard on
 * desktop and by taps on a phone, three cases added and solved, each with its lineup line in
 * Running combinations, and axe clean with the stop order open. D24 slice L3 (pump-lineups.md
 * §10.3): after that flow, the three lineups' own group curves named in the chart's accessible name,
 * listed point by point in "Other cases' group curves" and drawn in the image, axe clean. The
 * projects are the shared fixture's
 * (apps/api/tests/fixtures/pump_groups_input.py); every expected number is read from the
 * intercepted response of the real API and compared in display units, to the rounding the table
 * shows. No sideways scroll; the image is a PNG. Since pumps-results-layout.md S2 (§7 Proof, §9)
 * each axe scan covers the whole Pumps tab, with every disclosure opened and none closed, and
 * runs `heading-order` and `landmark-unique` too.
 */

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
const projectOf = (name: string) => fixture.cases.find((c) => c.name === name)!.project;

/** Open a project by its link (the app's own encoding: gzip, base64url). */
async function open(page: Page, project: Project) {
	const encoded = gzipSync(Buffer.from(JSON.stringify(project))).toString('base64url');
	await page.goto(`/p#${encoded}`);
}

const squash = (text: string) => text.replace(/\s+/g, ' ').trim();

/** The group table's cells by column heading (label and unit), for the row of `pump`. */
async function rowOf(table: Locator, pump: string): Promise<Record<string, string>> {
	const headings = (await table.getByRole('columnheader').allInnerTexts()).map(squash);
	const row = table
		.getByRole('row')
		.filter({ has: table.page().getByRole('rowheader', { name: pump, exact: true }) });
	await expect(row).toHaveCount(1);
	const cells = (await row.getByRole('cell').allInnerTexts()).map(squash);
	return Object.fromEntries(headings.slice(1).map((h, i) => [h, cells[i] ?? '']));
}

/** A displayed number agrees with `value` (display units) to the rounding it shows. */
function shows(text: string, value: number) {
	expect(Math.abs(Number(text) - value), `${text} against ${value}`).toBeLessThanOrEqual(
		halfUlp(text) + 1e-9 * Math.abs(value)
	);
}

/** Open the card and return it with the group-curve request and answer it sent. */
async function openCard(page: Page) {
	const pumps = await resultsView(page, 'Pumps');
	const card = pumps.getByRole('region', { name: /^Pumps together/ });
	const toggle = card.getByRole('button', { name: /^Pumps together/ });
	await expect(toggle).toHaveAttribute('aria-expanded', 'false');
	return { card, toggle };
}

/**
 * The answer to a group-curve request of `curve` ('group' or 'system') for a case: the base case
 * (no scenario id sent) by default, else the scenario `scenarioId`.
 */
function curveAnswer(page: Page, curve: 'group' | 'system', scenarioId?: string) {
	return page
		.waitForResponse((r) => {
			if (!r.url().endsWith('/api/v1/pump-group-curve') || r.request().method() !== 'POST') {
				return false;
			}
			const request = r.request().postDataJSON() as PumpGroupCurveRequest;
			return request.curve === curve && (request.scenarioId ?? undefined) === scenarioId;
		})
		.then(async (response) => ({
			status: response.status(),
			body: (await response.json()) as PumpGroupCurveResponse & Partial<ErrorResponse>,
			request: response.request().postDataJSON() as PumpGroupCurveRequest
		}));
}

/** Press, and wait for the group curve's answer (the request the press sends first). */
async function answerOf(page: Page, press: () => Promise<void>) {
	const answer = curveAnswer(page, 'group');
	await press();
	return answer;
}

/** Press, and wait for the group curve's answer, then the group system curve's (slice 4b). */
async function answersOf(page: Page, press: () => Promise<void>) {
	const group = curveAnswer(page, 'group');
	const system = curveAnswer(page, 'system');
	await press();
	return { group: await group, system: await system };
}

/** The numbers in a text, in order (display units, as shown). */
const numbers = (text: string) =>
	[...text.matchAll(/-?\d+(?:\.\d+)?(?:e-?\d+)?/g)].map((m) => m[0]);

async function noSidewaysScroll(page: Page) {
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
		true
	);
	// The Results pane's own scroller too, which can scroll while the page keeps still (proposal
	// pumps-results-layout.md §9 S0).
	const scroller = await resultsScroller(page);
	expect(scroller).not.toBeNull();
	expect(scroller!.scrollWidth).toBeLessThanOrEqual(scroller!.clientWidth);
}

/** The Pumps tabpanel, axe's scope (proposal pumps-results-layout.md §7 Proof). */
const PUMPS_TAB = '[role="tabpanel"][id$="-panel-pumps"]';

/**
 * Open every disclosure in the Pumps tab, as a user would and as `axeClean` in
 * tests/pumps-layout.e2e.ts does (proposal pumps-results-layout.md §7 Proof, §9 S2): press only
 * closed summaries a user can see (`details:not([open]) > summary`), found anew each round since
 * an opened one can hold more, so none that opened itself is closed; then none is left.
 */
async function openEveryDisclosure(page: Page) {
	const closed = page.locator(`${PUMPS_TAB} details:not([open]) > summary`);
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
	expect(await firstShown(), 'a closed disclosure left in the Pumps tab').toBe(-1);
}

/**
 * axe over the whole Pumps tabpanel (§7 Proof): the suite's WCAG 2.0 to 2.2 A and AA tags, then
 * `heading-order` and `landmark-unique`, which those tags leave out. Some rule must pass, so an
 * empty scope cannot.
 */
async function axeCleanTab(page: Page) {
	const scan = await new AxeBuilder({ page })
		.include(PUMPS_TAB)
		.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
		.analyze();
	expect(scan.violations.map((v) => `${v.id} (${v.nodes.length})`)).toEqual([]);
	expect(scan.passes.length).toBeGreaterThan(0);
	const outline = await new AxeBuilder({ page })
		.include(PUMPS_TAB)
		.withRules(['heading-order', 'landmark-unique'])
		.analyze();
	expect(outline.violations.map((v) => `${v.id} (${v.nodes.length})`)).toEqual([]);
}

test('two pumps in parallel: the station, each share and loss on its way, the PNG', async ({
	page
}) => {
	await open(page, projectOf('parallel-crane'));
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const answers = await answersOf(page, () => toggle.click());
	const { status, body, request } = answers.group;
	expect(status).toBe(200);
	expect(request.pumpIds).toEqual(['PA', 'PB']);
	expect(request).not.toHaveProperty('scenarioId');
	const duty = body.duty!;
	expect(body.station.arrangement).toBe('parallel');
	expect(answers.system.status).toBe(200);

	const figure = card.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' });
	await expect(figure).toBeVisible();
	await expect(figure.getByRole('img')).toHaveAccessibleName(
		/; group curve shown; group system curve shown\.$/
	);
	await expect(figure.getByRole('img')).toHaveAccessibleName(
		/from Tee T1 \(run inlet\) to Tee T2 \(run outlet\), on the group curve/
	);
	await expect(
		figure.getByText(/^Pump curves and points are at each pump's flanges\./)
	).toBeVisible();

	const table = card.getByRole('table', { name: 'The pumps in the group' });
	for (const [i, pump] of ['Pump PA', 'Pump PB'].entries()) {
		const member = duty.members[i]!;
		const row = await rowOf(table, pump);
		shows(row['Share %']!, member.share! * 100);
		shows(row['Lost on its way m']!, member.routeHeadLoss!);
		shows(row['Flow L/s']!, member.flow * 1000);
		shows(row['Head m']!, member.head!);
	}
	const footer = squash(await card.locator('dl').innerText());
	const [flow, rise] = [...footer.matchAll(/: ([\d.]+) (?:L\/s|m)/g)].map((m) => m[1]!);
	shows(flow!, duty.flow * 1000);
	shows(rise!, duty.head);
	expect(footer).toContain('Station flow, into the station at Tee T1 (run inlet)');
	expect(footer).toContain('Rise from Tee T1 (run inlet) to Tee T2 (run outlet)');

	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	// In its disclosure, opened first (proposal pumps-results-layout.md §9 S7).
	const samples = await openCurveTable(card, "Group curve (station's flow at each rise)");
	await expect(samples.getByRole('row')).toHaveCount(body.points.length + 1);
	await noSidewaysScroll(page);

	const image = card.locator('[data-chart-image]');
	await expect(image).not.toHaveAttribute('aria-disabled', 'true');
	const [download] = await Promise.all([page.waitForEvent('download'), image.click()]);
	expect(download.suggestedFilename()).toMatch(
		/ - Pumps together Pump PA, Pump PB \d{4}-\d\d-\d\d \d{4}\.png$/
	);
	const png = readFileSync(await download.path());
	expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
	expect(png.toString('latin1', 12, 16)).toBe('IHDR');
	expect(png.readUInt32BE(16)).toBe(1600);
});

test('the station: its answer before the group table, each flagged pump’s flag line under its row, its text in the box’s visible width and read once (pumps-results-layout.md §5.3, §9 S3)', async ({
	page
}) => {
	await open(page, projectOf('parallel-crane'));
	const solved = await solveConverged(page);
	const { card, toggle } = await openCard(page);
	await answersOf(page, () => toggle.click());
	const station = card.locator('[data-group-station]');
	await expect(station.getByRole('heading', { name: 'Station', level: 4 })).toBeVisible();
	// The answer first: the station's dl, then the table.
	const answer = station.getByLabel('The station');
	// The table's box (a region only while it overflows since S7, pumps-results-layout.md §9 S7).
	const region = station.getByRole('table', { name: 'The pumps in the group' }).locator('..');
	const [a, r] = [(await answer.boundingBox())!, (await region.boundingBox())!];
	expect(a.y + a.height).toBeLessThanOrEqual(r.y);
	// In sight at a size of its own, on a phone too: not sr-only's 1 px box, which toBeVisible
	// accepts (S3 review MUT-09).
	await expect(answer).toBeVisible();
	expect(a.width, "the station's answer's width").toBeGreaterThan(1);
	expect(a.height, "the station's answer's height").toBeGreaterThan(1);
	await expect(region.getByRole('columnheader', { name: 'Flags' })).toHaveCount(0);
	// Both pumps' NPSH is not checked here: a warning flag each, in the solve.
	const flagged = ['PA', 'PB'].filter((id) => solved.flags.some((f) => f.componentId === id));
	expect(flagged).toEqual(['PA', 'PB']);
	const box = (await region.boundingBox())!;
	for (const id of flagged) {
		const name = `Pump ${id}`;
		const line = region.locator(`[data-row-notes="${id}"]`);
		await expect(line).toHaveAttribute('data-label', 'Flags');
		// Named by its pump first (visually hidden), then each flag's pill and its text, visible.
		await expect(line).toHaveText(new RegExp(`^${name}, flags:\\s*Warning\\s+\\S`));
		// A list, an item per flag (S6a: one pattern with Running combinations, §15 item 149).
		const flags = line.locator('li');
		const count = solved.flags.filter((f) => f.componentId === id).length;
		await expect(flags).toHaveCount(count);
		const whole = squash((await line.textContent()) ?? '');
		for (let i = 0; i < count; i++) {
			const p = flags.nth(i);
			await expect(p).toBeVisible();
			const text = squash(await p.innerText()).replace(/^Warning /, '');
			expect(text.length).toBeGreaterThan(10);
			// The flag's sentence once in its line (no hidden copy, no title).
			expect(whole.split(text)).toHaveLength(2);
			await expect(p.locator('[title]')).toHaveCount(0);
			// Inside the box's visible width, whatever the table's own width.
			const b = (await p.boundingBox())!;
			expect(b.x).toBeGreaterThanOrEqual(box.x - 0.5);
			expect(b.x + b.width).toBeLessThanOrEqual(box.x + box.width + 0.5);
		}
	}
	await noSidewaysScroll(page);
});

test('two pumps in series: inlet and discharge pressures and the loss between them, in US units', async ({
	page
}) => {
	await open(page, projectOf('series'));
	const solved = await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const { status, body } = await answerOf(page, () => toggle.click());
	expect(status).toBe(200);
	expect(body.station.arrangement).toBe('series');
	await expect(card.getByRole('figure', { name: 'Pump PA and Pump PB in series' })).toBeVisible();
	const table = card.getByRole('table', { name: 'The pumps in the group' });
	const psi = 6894.757293168361;
	const foot = 0.3048;
	for (const [i, pump] of ['Pump PA', 'Pump PB'].entries()) {
		const member = body.duty!.members[i]!;
		const row = await rowOf(table, pump);
		shows(row['Share %']!, member.share! * 100);
		shows(row['Head ft']!, member.head! / foot);
		shows(
			row['Inlet pressure psig']!,
			solved.nodeResults[`${member.pumpId}:suction`]!.pressure / psi
		);
		shows(
			row['Discharge pressure psig']!,
			solved.nodeResults[`${member.pumpId}:discharge`]!.pressure / psi
		);
	}
	const footer = squash(await card.locator('dl').innerText());
	const loss = /Lost in the piping between the pumps: ([\d.]+) ft/.exec(footer)![1]!;
	shows(loss, body.duty!.interstageHeadLoss! / foot);
	await expect(
		card.getByText(/the piping between the pumps loses [\d.]+ ft at the duty\.$/)
	).toBeVisible();
	await noSidewaysScroll(page);
});

test('two pumps that are not a station: why, in words, and their own curves still drawn', async ({
	page
}) => {
	await open(page, projectOf('refused'));
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	await toggle.click();
	// Nothing is suggested here: the user ticks the pumps.
	const members = card.getByRole('group', { name: 'Pumps in the group' });
	await members.getByRole('checkbox', { name: /Pump PA/ }).check();
	const { status, body } = await answerOf(page, () =>
		members.getByRole('checkbox', { name: /Pump PB/ }).check()
	);
	expect(status).toBe(422);
	expect(body.error).toBe('NOT_A_STATION');
	expect(body.issues!.map((i) => i.code)).toEqual(['FIXED_HEAD_INSIDE']);
	await expect(card.getByText(/^These pumps do not form a station/)).toBeVisible();
	const reason = card
		.getByRole('list', { name: 'Why they do not form a station' })
		.getByRole('listitem')
		.first();
	await expect(reason).toContainText(
		'The pumps meet the fixed heads of Reservoir R2 and Tank R4, one place more than a station has'
	);
	await expect(reason.getByRole('button', { name: 'Tank R4' })).toBeVisible();
	const figure = card.getByRole('figure', { name: 'Pump PA and Pump PB' });
	// Each member's point is drawn (the chart's name lists it, "without a point" otherwise) …
	await expect(figure.getByRole('img')).toHaveAccessibleName(
		/^Pump curves and points of Pump PA at [^;]+; Pump PB at [^;]+; no group curve shown\.$/
	);
	// … and each member's curve: the legend, made from the chart's datasets, has a line for it.
	const legend = figure.getByRole('list', { name: 'Legend' });
	for (const curve of ['Pump PA, 100 % speed (own flow)', 'Pump PB, 85 % speed (own flow)']) {
		const entry = legend.getByRole('listitem').filter({ hasText: curve });
		await expect(entry).toHaveCount(1);
		await expect(entry.locator('svg line')).toHaveCount(1);
	}
	await expect(legend.getByRole('listitem').filter({ hasText: /group curve/i })).toHaveCount(0);
	await noSidewaysScroll(page);
});

test('the group system curve: drawn, listed with the response’s values, crossing at the Group point; reading along the curves', async ({
	page
}) => {
	await open(page, projectOf('parallel-crane'));
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const { group, system } = await answersOf(page, () => toggle.click());
	expect(group.status).toBe(200);
	expect(system.status).toBe(200);
	expect(system.request).toMatchObject({ pumpIds: ['PA', 'PB'], curve: 'system' });
	expect(system.request).not.toHaveProperty('flowMax');
	const body = system.body;
	expect(body.station).toEqual(group.body.station);
	expect(body.duty).toEqual(group.body.duty);
	expect(group.body.dutyCheck!.agrees).toBe(true);
	expect(body.systemDutyCheck!.agrees).toBe(true);

	const figure = card.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' });
	const legend = figure.getByRole('list', { name: 'Legend' });
	// A regular expression is matched against the item's raw text, which starts with the
	// whitespace after its swatch.
	const line = legend.getByRole('listitem').filter({ hasText: /^\s*Group system curve/ });
	await expect(line).toHaveText(
		"Group system curve (the rest of the network between the station's inlet and outlet, station's flow)"
	);
	await expect(line.locator('svg line')).toHaveAttribute('stroke', '#eb6834');
	await expect(
		legend.getByRole('listitem').filter({
			hasText: 'Group duty, where the group curve and the group system curve cross'
		})
	).toHaveCount(1);
	await expect(figure.getByRole('img')).toHaveAccessibleName(
		/, on the group curve and the group system curve, where they cross; group curve shown; group system curve shown\.$/
	);
	// The group system curve's note is reference since pumps-results-layout.md S3 (§5.3): inside
	// "How to read this chart", opened first.
	await figure.locator('[data-group-reading] > summary').click();
	await expect(
		figure.getByText(
			"The group's system curve is the rise the rest of the network needs between Tee T1 (run inlet) and Tee T2 (run outlet) at each total flow; it does not depend on how the pumps share the flow."
		)
	).toBeVisible();
	await expect(
		figure.getByText(
			"At the duty's flow the group system curve gives the solve's rise (within 0.5 % or 0.01 m): it passes through the Group point, where it crosses the group curve."
		)
	).toBeVisible();

	// The data table: every point of the group system curve, its flow and rise as the response's,
	// in its disclosure, opened first (proposal pumps-results-layout.md §9 S7).
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	const table = await openCurveTable(
		card,
		"Group system curve (rise the rest of the network needs at each station's flow)"
	);
	const points = [...body.systemPoints].sort((a, b) => a.flow - b.flow);
	const rows = table.getByRole('row');
	await expect(rows).toHaveCount(points.length + 1);
	for (const [i, p] of points.entries()) {
		const cells = (
			await rows
				.nth(i + 1)
				.getByRole('cell')
				.allInnerTexts()
		).map(squash);
		shows(cells[0]!, p.flow * 1000);
		shows(cells[1]!, p.head!);
		if (p.isDuty) expect(cells[2]).toBe("The duty's flow (the system duty check).");
	}
	await expect(
		card.getByText(/System duty check: the group system curve passes through it\./)
	).toBeVisible();

	// Read along the curves: a native slider over the group curve's samples, each read exactly.
	const slider = card.getByRole('slider', { name: 'Read along the curves' });
	const box = (await slider.boundingBox())!;
	expect(box.height).toBeGreaterThanOrEqual(44);
	const samples = [...group.body.points].sort((a, b) => a.head - b.head);
	const duty = samples.findIndex((p) => p.isDuty);
	await expect(slider).toHaveValue(String(duty));
	const readsAt = async (i: number) => {
		const sample = samples[i]!;
		const text = (await slider.getAttribute('aria-valuetext'))!;
		expect(text).toMatch(
			/^At a rise of [\d.e-]+ m: Pump PA [\d.e-]+ L\/s(?: \(no flow\))?, Pump PB [\d.e-]+ L\/s(?: \(no flow\))?, group [\d.e-]+ L\/s/
		);
		const [rise, pa, pb, station] = numbers(text);
		shows(rise!, sample.head);
		shows(pa!, sample.members.find((m) => m.pumpId === 'PA')!.flow * 1000);
		shows(pb!, sample.members.find((m) => m.pumpId === 'PB')!.flow * 1000);
		shows(station!, sample.flow! * 1000);
		await expect(card.locator('[data-group-readout]')).toHaveText(text);
	};
	await readsAt(duty);
	await slider.focus();
	await page.keyboard.press('ArrowRight');
	await expect(slider).toHaveValue(String(duty + 1));
	await readsAt(duty + 1);
	await page.keyboard.press('Home');
	await expect(slider).toHaveValue('0');
	await readsAt(0);
	await card.getByRole('button', { name: 'Back to the duty' }).click();
	await expect(slider).toHaveValue(String(duty));
	await noSidewaysScroll(page);

	// The image: a PNG of the chart with the group system curve.
	const image = card.locator('[data-chart-image]');
	await expect(image).not.toHaveAttribute('aria-disabled', 'true');
	const [download] = await Promise.all([page.waitForEvent('download'), image.click()]);
	const png = readFileSync(await download.path());
	expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
	expect(png.readUInt32BE(16)).toBe(1600);
});

test('the group system curve in US units: its points in gpm and ft', async ({ page }) => {
	await open(page, projectOf('series'));
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const { system } = await answersOf(page, () => toggle.click());
	expect(system.status).toBe(200);
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	// In its disclosure, opened first (proposal pumps-results-layout.md §9 S7).
	const table = await openCurveTable(
		card,
		"Group system curve (rise the rest of the network needs at each station's flow)"
	);
	const heads = (await table.getByRole('columnheader').allInnerTexts()).map(squash);
	expect(heads).toEqual(['Flow (gpm)', 'Rise (ft)', 'Note']);
	const points = [...system.body.systemPoints].sort((a, b) => a.flow - b.flow);
	const gpm = 0.0000630901964;
	for (const i of [1, points.length - 1]) {
		const cells = (
			await table
				.getByRole('row')
				.nth(i + 1)
				.getByRole('cell')
				.allInnerTexts()
		).map(squash);
		shows(cells[0]!, points[i]!.flow / gpm);
		shows(cells[1]!, points[i]!.head! / 0.3048);
	}
	await expect(
		card.getByText(
			`At the duty's flow the group system curve gives the solve's rise (within 0.5 % or 0.03281 ft): it passes through the Group point, where it crosses the group curve.`
		)
	).toBeVisible();
	await noSidewaysScroll(page);
});

test('an FCV outside the station: the group system curve has no rise beyond it, and says why', async ({
	page
}) => {
	await open(page, projectOf('fcv-outside'));
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const { system } = await answersOf(page, () => toggle.click());
	expect(system.status).toBe(200);
	const points = [...system.body.systemPoints].sort((a, b) => a.flow - b.flow);
	const missing = points.filter((p) => p.head === null);
	expect(missing.length).toBeGreaterThan(0);
	expect(new Set(missing.map((p) => p.reason))).toEqual(new Set(['beyond_limit']));
	await expect(
		card.getByText(
			`${missing.length} of ${points.length} group-system-curve points have no rise: the line has gaps there, and the data table says why for each.`
		)
	).toBeVisible();
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	// Open by default: some of its rows have no rise (proposal pumps-results-layout.md §9 S7).
	await expect(
		curveTableFold(
			card,
			"Group system curve (rise the rest of the network needs at each station's flow)"
		)
	).toHaveAttribute('open', '');
	const table = card.getByRole('table', {
		name: "Group system curve (rise the rest of the network needs at each station's flow)"
	});
	const at = points.indexOf(missing[0]!);
	const row = table.getByRole('row').nth(at + 1);
	const cells = (await row.getByRole('cell').allInnerTexts()).map(squash);
	shows(cells[0]!, missing[0]!.flow * 1000);
	expect(cells[1]).toBe('—');
	expect(cells[2]).toContain(
		"No steady state carries this flow: every way from the station's outlet back to its inlet, through the network or a reservoir or reference node, passes Control valve FC, which passes at most 60 L/s that way (an FCV passes neither reverse flow nor more than its flow setpoint)."
	);
	await noSidewaysScroll(page);
});

test('a PRV inside the station: no group curve there, the group system curve all the same', async ({
	page
}) => {
	await open(page, projectOf('prv-inside'));
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	await toggle.click();
	// Nothing is suggested with an active PRV inside: the user ticks the pumps.
	const members = card.getByRole('group', { name: 'Pumps in the group' });
	await members.getByRole('checkbox', { name: /Pump PA/ }).check();
	const { group, system } = await answersOf(page, () =>
		members.getByRole('checkbox', { name: /Pump PB/ }).check()
	);
	expect(group.status).toBe(422);
	expect(group.body.issues!.map((i) => i.code)).toEqual(['PRESSURE_CONTROL_INSIDE']);
	expect(system.status).toBe(200);
	await expect(
		card.getByText(
			"These pumps form a station, but its group curve is not defined there; its group system curve is, and the pumps' own curves and points are drawn."
		)
	).toBeVisible();
	await expect(
		card.getByRole('list', { name: 'Why the group curve is not defined' }).getByRole('listitem')
	).toContainText('is inside the station and holds a pressure (an active PRV or PSV)');
	const figure = card.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' });
	const legend = figure.getByRole('list', { name: 'Legend' });
	// Regular expressions are matched against an item's raw text (whitespace after its swatch).
	await expect(
		legend.getByRole('listitem').filter({ hasText: /^\s*Group system curve/ })
	).toHaveCount(1);
	await expect(legend.getByRole('listitem').filter({ hasText: /^\s*Group curve/ })).toHaveCount(0);
	await expect(
		legend.getByRole('listitem').filter({ hasText: 'Group duty, on the group system curve' })
	).toHaveCount(1);
	await expect(card.getByRole('slider')).toHaveCount(0);
	await noSidewaysScroll(page);
});

test('the export writes the group computed: five sheets after System curves, nothing sent', async ({
	page
}) => {
	await open(page, projectOf('parallel-crane'));
	await solveConverged(page);
	const { toggle } = await openCard(page);
	const { group, system } = await answersOf(page, () => toggle.click());
	expect(group.status).toBe(200);
	expect(system.status).toBe(200);

	await resultsPane(page).locator('[data-export-button]').click();
	const dialog = page.getByRole('dialog', { name: 'Export results' });
	await expect(dialog).toBeVisible();
	await dialog.getByRole('radio', { name: /^SI base units/ }).check();
	const contents = dialog.locator('[data-export-contents]');
	const members = group.body.points.reduce((n, p) => n + p.members.length, 0);
	for (const item of [
		'Pump groups (1)',
		'Pump group members (2)',
		`Group curves (${group.body.points.length})`,
		`Group curve members (${members})`,
		`Group system curves (${system.body.systemPoints.length})`
	]) {
		await expect(contents).toContainText(item);
	}
	const omitted = dialog.locator('[data-export-omitted] li');
	for (const text of await omitted.allInnerTexts()) {
		expect(text).not.toMatch(/^(Pump group|Group curves and group system curves)/);
	}

	const made = await downloadFrom(page, dialog.getByRole('button', { name: 'Download' }));
	expectNothingSent(made.requests);
	const { sheets, strings } = readWorkbook(made.bytes);
	const names = [...sheets.keys()];
	// The Pumps view computes the viewed pump's system curve first, on the same queue.
	const at = names.indexOf('System curves');
	expect(at).toBeGreaterThan(0);
	expect(names.slice(at + 1, at + 6)).toEqual([
		'Pump groups',
		'Pump group members',
		'Group curves',
		'Group curve members',
		'Group system curves'
	]);
	const groups = sheets.get('Pump groups')!;
	expect(groups).toContain(`<v>${String(group.body.duty!.flow)}</v>`);
	expect(groups).toContain(`<v>${String(group.body.duty!.head)}</v>`);
	expect(strings).toContain('PA+PB');
	await noSidewaysScroll(page);
});

// ---- Slice 4d: one pump off ----------------------------------------------------------------

/** The answer to a solve of the scenario `scenarioId`. */
function solveAnswer(page: Page, scenarioId: string) {
	return page
		.waitForResponse(
			(r) =>
				r.url().endsWith('/api/v1/solve') &&
				r.request().method() === 'POST' &&
				(r.request().postDataJSON() as SolveRequest).scenarioId === scenarioId
		)
		.then(async (response) => (await response.json()) as SolveResponse);
}

/**
 * Open `one-off` without its scenarios, solve, open the card (its two curves answered), add the
 * cases with one pump off (Each pump off chosen in the Add cases block, D24) and solve them with
 * the Scenarios menu's Solve all, the page's one since build-density.md §19; returns the answers.
 */
async function addAndSolve(page: Page) {
	const project = structuredClone(projectOf('one-off'));
	delete project.scenarios;
	await open(page, project);
	const base = await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const answers = await answersOf(page, () => toggle.click());
	expect(answers.group.status).toBe(200);
	expect(answers.system.status).toBe(200);
	// §7.12: the region "One pump off" becomes "Add cases", and its button "Add cases with one
	// pump off ({n})" becomes "Add {n} cases"; 4d's cases are Each pump off.
	const block = card.getByRole('region', { name: 'Add cases' });
	await block.getByRole('radio', { name: 'Each pump off' }).click();
	await expect(block.getByRole('radio', { name: 'Each pump off' })).toBeChecked();
	await block.getByRole('button', { name: 'Add 2 cases' }).click();
	await expect(
		page.getByText(
			'Added 2 cases with one pump off: Pump PA off and Pump PB off. Solve all, in the Scenarios menu at the top, solves every case not yet solved; Undo removes them.'
		)
	).toBeVisible();
	// The focus stays on Add, which then reads "Add cases"; the menu's Solve all counts the two.
	await expect(block.getByRole('button', { name: /^Add( \d+)? cases?$/ })).toBeFocused();
	await expect(solveAllButton(page)).toHaveText('Solve all (2)');
	const solves = [solveAnswer(page, 'S1'), solveAnswer(page, 'S2')];
	const duties = [curveAnswer(page, 'group', 'S1'), curveAnswer(page, 'group', 'S2')];
	await solveAll(page);
	const [s1, s2] = await Promise.all(solves);
	const [d1, d2] = await Promise.all(duties);
	for (const d of [d1!, d2!]) expect(d.status).toBe(200);
	// The run ends with the menu's Solve all in place, unavailable, and the header's Solve focused:
	// the menu's end-of-run handoff (build-density.md §19).
	await expect(solveAllButton(page)).toHaveAttribute('aria-disabled', 'true');
	await expect(
		page.getByRole('banner').getByRole('button', { name: 'Solve Base case' })
	).toBeFocused();
	return { card, block, base, solves: { S1: s1!, S2: s2! }, duties: [d1!, d2!] };
}

test('one pump off: the cases added in one step, solved, each pump listed and each station duty drawn', async ({
	page,
	isMobile
}) => {
	const { card, base, solves, duties } = await addAndSolve(page);
	// Running combinations: every case, the shown first, each pump's values from its own solve.
	// Nit 5 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5, slice 5b): each heading led by
	// its case's number in a box, "Base", then 1 and 2 by the Scenarios list, heard as "Case 1:"
	// before the name (no " · ring n" after it).
	const combos = card.getByRole('table', { name: 'Running combinations' });
	const group = (name: RegExp) =>
		combos.getByRole('rowgroup').filter({ has: page.getByRole('rowheader', { name }) });
	await expect(group(/^Base case \(shown\)/)).toHaveCount(1);
	await expect(group(/^Case 1: Pump PA off/)).toHaveCount(1);
	await expect(group(/^Case 2: Pump PB off/)).toHaveCount(1);
	await expect(caseTagBoxes(combos.locator('th[scope="rowgroup"]'))).toHaveText(['Base', '1', '2']);
	const cases = [
		[/^Base case \(shown\)/, base],
		[/^Case 1: Pump PA off/, solves.S1.solvedState],
		[/^Case 2: Pump PB off/, solves.S2.solvedState]
	] as const;
	for (const [name, solved] of cases) {
		for (const pump of ['PA', 'PB']) {
			const r = solved.pumpResults[pump]!;
			const row = group(name)
				.getByRole('row')
				.filter({ has: page.getByRole('rowheader', { name: `Pump ${pump}`, exact: true }) });
			const cell = async (label: string) =>
				squash(await row.locator(`[data-label="${label}"]`).innerText());
			shows(await cell('Flow (L/s)'), r.operatingFlow * 1000);
			shows(await cell('Head (m)'), r.operatingHead);
			if (r.shaftPower !== null) shows(await cell('Shaft power (kW)'), r.shaftPower / 1000);
			if (r.npshMargin !== null) shows(await cell('NPSH margin (m)'), r.npshMargin);
		}
	}
	const paWithoutPb = group(/^Case 2: Pump PB off/)
		.getByRole('row')
		.filter({ has: page.getByRole('rowheader', { name: 'Pump PA', exact: true }) });
	await expect(paWithoutPb.locator('[data-label="Inside curve data"]')).toHaveText(
		'No: beyond its data'
	);
	// Its flags in the flag line following its row (pumps-results-layout.md §5.3 Flags, §10 S5),
	// no longer a Flags cell in it.
	await expect(paWithoutPb.locator('[data-label="Flags"]')).toHaveCount(0);
	await expect(
		paWithoutPb.locator('xpath=following-sibling::*[1]').locator('[data-label="Flags"]')
	).toContainText('Warning');
	// The extremes: PA's largest flow with PB off, a table since pumps-results-layout.md S5 (§10
	// S5): PA's row by its header, the cell under "Largest flow" by its data-label, the pattern
	// anchored at the cell's start; on a phone the same roles and data-labels, the line's header
	// ::before content outside the cell's text.
	const extremes = card.getByRole('table', { name: 'Extremes over these cases' });
	const paExtremes = extremes
		.getByRole('row')
		.filter({ has: page.getByRole('rowheader', { name: 'Pump PA', exact: true }) });
	await expect(paExtremes.locator('[data-label="Largest flow"]')).toHaveText(
		/^[\d.]+ L\/s in Pump PB off; beyond its curve data/
	);

	// Each case's station duty, a slate ring on the base case's group system curve, named by its
	// case's number (nit 5, slice 5b: "Case 1: …", no "1 ·").
	const figure = card.getByRole('figure');
	const legend = figure.getByRole('list', { name: 'Legend' });
	await expect(legend.getByText('Case 1: Pump PA off (station duty)')).toBeVisible();
	await expect(legend.getByText('Case 2: Pump PB off (station duty)')).toBeVisible();
	await expect(
		legend.getByRole('listitem').filter({ hasText: /^\s*Group system curve/ })
	).toHaveCount(1);
	await expect(card.getByText(/was not computed/)).toHaveCount(0);
	const name = (await figure.getByRole('img').getAttribute('aria-label'))!;
	// D24 §9.6: with the base's group curve drawn, each case's part gains "; group curve: {words}":
	// each case with one pump off has its own curve drawn (1 running), crossing at its ring.
	for (const [n, label, answer] of [
		[1, 'Pump PA off', duties[0]!],
		[2, 'Pump PB off', duties[1]!]
	] as const) {
		const match = new RegExp(
			`case ${n}: ${label}, ([\\d.]+) L/s at a rise of ([\\d.]+) m \\(Yes: the same rest of the network; group curve: drawn \\(1 running\\): it crosses the group system curve at the ring\\)`
		).exec(name);
		expect(match, name).not.toBeNull();
		shows(match![1]!, answer.body.duty!.flow * 1000);
		shows(match![2]!, answer.body.duty!.head);
	}
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	const table = card.getByRole('table', { name: "Other cases' station duties" });
	for (const [i, answer] of duties.entries()) {
		// Each row headed by its case's number in a box and its name (nit 5, slice 5b).
		const header = table
			.getByRole('row')
			.nth(i + 1)
			.getByRole('rowheader');
		await expect(header).toHaveAccessibleName(
			`Case ${i + 1}: ${['Pump PA off', 'Pump PB off'][i]}`
		);
		await expect(caseTagBoxes(header)).toHaveText(String(i + 1));
		const cells = table
			.getByRole('row')
			.nth(i + 1)
			.getByRole('cell');
		shows(squash(await cells.nth(0).innerText()), answer.body.duty!.flow * 1000);
		shows(squash(await cells.nth(1).innerText()), answer.body.duty!.head);
		await expect(cells.nth(2)).toHaveText('Yes: the same rest of the network');
	}

	// The image, with the rings.
	const image = card.locator('[data-chart-image]');
	await expect(image).not.toHaveAttribute('aria-disabled', 'true');
	const [download] = await Promise.all([page.waitForEvent('download'), image.click()]);
	const png = readFileSync(await download.path());
	expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

	await noSidewaysScroll(page);
	// Its box (a region only while it overflows since S7, pumps-results-layout.md §9 S7).
	const region = card.getByRole('table', { name: 'Running combinations' }).locator('..');
	if (isMobile) {
		// A list on a phone: nothing to scroll sideways, each case's heading in view.
		expect(await region.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
		await expect(region.getByRole('rowheader', { name: /^Base case \(shown\)/ })).toBeVisible();
	}
});

test('Running combinations wraps a long pump name on a phone, with no sideways scroll', async ({
	page,
	isMobile
}) => {
	test.skip(!isMobile, 'phone layout');
	// Names may be up to 100 characters: one of 60 must wrap in the list, not scroll it.
	const project = structuredClone(projectOf('one-off'));
	const long = 'Chilled water primary pump CHWP-1A, duty, variable speed (A)';
	expect(long).toHaveLength(60);
	project.components.find((c) => c.id === 'PA')!.name = long;
	await open(page, project);
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	await answersOf(page, () => toggle.click());
	// Its box (a region only while it overflows since S7, pumps-results-layout.md §9 S7).
	const region = card.getByRole('table', { name: 'Running combinations' }).locator('..');
	// PA's own row header, by its exact name: since D24 §7.10 each case's heading holds a lineup
	// line naming every member, which a substring match (and `.first()`) would find first.
	await expect(region.getByRole('rowheader', { name: long, exact: true })).toBeVisible();
	expect(await region.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
	await noSidewaysScroll(page);
});

test('one pump off is offered for pumps in parallel only', async ({ page }) => {
	await open(page, projectOf('series'));
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const { status } = await answerOf(page, () => toggle.click());
	expect(status).toBe(200);
	// §7.12: the region "One pump off" becomes "Add cases", and gate 1 takes §7.2 row 1's words.
	const block = card.getByRole('region', { name: 'Add cases' });
	await expect(block).toContainText(
		'Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.'
	);
	// No Add and no Solve all under the gate; its one button is D24 slice L2's "Pump lineups
	// table…", drawn whenever the block is, gates included (pump-lineups.md §8.1).
	await expect(block.getByRole('button')).toHaveText(['Pump lineups table…']);
});

test('the Pumps together card with its cases passes axe, everything open', async ({ page }) => {
	const { card } = await addAndSolve(page);
	// Nit 5, slice 5b: the ring's entry names its case by number.
	await expect(card.getByRole('figure').getByRole('list', { name: 'Legend' })).toContainText(
		'Case 2: Pump PB off (station duty)'
	);
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	await openEveryDisclosure(page);
	await expect(card.getByRole('table', { name: "Other cases' station duties" })).toBeVisible();
	await axeCleanTab(page);
});

// ---- D24 slice L1b: the Add cases block, By number running -----------------------------------

/** "A and B", "A, B and C" (the app's lists). */
const andList = (items: readonly string[]) =>
	items.length < 2 ? (items[0] ?? '') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;

/**
 * Running combinations' lineup line of a case (pump-lineups.md §7.10), read from its solve as the
 * app reads it: a pump carries flow when it is not off and its |flow| is above 10⁻⁶ m³/s.
 */
function lineupLine(solved: SolvedState, pumps: readonly string[]) {
	const result = (id: string) => solved.pumpResults[id]!;
	const off = pumps.filter((id) => result(id).status === 'off');
	const carrying = pumps.filter(
		(id) => result(id).status !== 'off' && Math.abs(result(id).operatingFlow) > 1e-6
	);
	expect(carrying.length + off.length, 'no pump on without flow here').toBe(pumps.length);
	const name = (id: string) => `Pump ${id}`;
	return `${carrying.length} of ${pumps.length} carrying flow: ${andList(carrying.map(name))}${
		off.length ? `; off: ${andList(off.map(name))}` : ''
	}`;
}

test('add cases by number running: the stop order moved, three cases added and solved, each with its lineup line', async ({
	page,
	isMobile
}) => {
	const project = structuredClone(projectOf('lineups'));
	delete project.scenarios;
	await open(page, project);
	const base = await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const answers = await answersOf(page, () => toggle.click());
	expect(answers.group.status).toBe(200);
	expect(answers.system.status).toBe(200);

	// 1. The region, By number running chosen.
	const block = card.getByRole('region', { name: 'Add cases' });
	await expect(block.getByRole('radio', { name: 'By number running' })).toBeChecked();
	// 2. The three cases it would make.
	const preview = block.getByRole('list', { name: 'Cases:' }).getByRole('listitem');
	await expect(preview).toHaveText([
		'3 of 4 running (Pump P4 off)',
		'2 of 4 running (Pump P3, Pump P4 off)',
		'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
	]);

	// 3. The stop order: P1 to the first place, then one place later; by keyboard on desktop
	// (the focus asserted after every press), by taps on a phone.
	// The stop order's own disclosure, inside the plan's since S4 (pumps-results-layout.md §5.3).
	const summary = block.locator('[data-stop-order] > summary');
	await expect(summary).toHaveText(
		'Stop order: Pump P4 first, then Pump P3 and Pump P2; Pump P1 stays on in every case'
	);
	const status = block.locator('[data-stop-status]');
	const earlier = block.getByRole('button', { name: 'Stop Pump P1 earlier' });
	const later = block.getByRole('button', { name: 'Stop Pump P1 later' });
	if (isMobile) {
		await summary.tap();
		await expect(block.getByRole('list', { name: 'Stop order' })).toBeVisible();
		for (const n of [3, 2, 1]) {
			await earlier.tap();
			await expect(status).toHaveText(`Pump P1 is now number ${n} of 4 to stop.`);
			await expect(earlier).toBeFocused();
		}
		await expect(earlier).toHaveAttribute('aria-disabled', 'true');
		await later.tap();
	} else {
		await summary.focus();
		await page.keyboard.press('Enter');
		await expect(block.getByRole('list', { name: 'Stop order' })).toBeVisible();
		// From the summary, Tab passes P4's, P3's and P2's two buttons, then P1's "earlier".
		for (let i = 0; i < 7; i++) await page.keyboard.press('Tab');
		await expect(earlier).toBeFocused();
		for (const n of [3, 2, 1]) {
			await page.keyboard.press('Enter');
			await expect(status).toHaveText(`Pump P1 is now number ${n} of 4 to stop.`);
			await expect(earlier).toBeFocused();
		}
		await expect(earlier).toHaveAttribute('aria-disabled', 'true');
		await expect(earlier).toHaveAccessibleDescription('Already the first to stop.');
		await page.keyboard.press('Tab');
		await expect(later).toBeFocused();
		await page.keyboard.press('Enter');
	}
	await expect(status).toHaveText('Pump P1 is now number 2 of 4 to stop.');
	await expect(later).toBeFocused();
	const names = [
		'3 of 4 running (Pump P4 off)',
		'2 of 4 running (Pump P1, Pump P4 off)',
		'1 of 4 running (Pump P1, Pump P3, Pump P4 off)'
	];
	await expect(preview).toHaveText(names);
	await expect(summary).toHaveText(
		'Stop order: Pump P4 first, then Pump P1 and Pump P3; Pump P2 stays on in every case'
	);
	await expect(block.getByRole('button', { name: 'Default order' })).toBeVisible();
	await noSidewaysScroll(page);

	// 4. Add 3 cases: the notice, the focus kept on Add; then the Scenarios menu's Solve all, the
	// page's one (build-density.md §19).
	await block.getByRole('button', { name: 'Add 3 cases' }).click();
	await expect(
		page.getByText(
			`Added 3 cases by number running: ${andList(names.map((n) => `«${n}»`))}. Solve all, in the Scenarios menu at the top, solves every case not yet solved; Undo removes them.`
		)
	).toBeVisible();
	await expect(block.getByRole('button', { name: /^Add( \d+)? cases?$/ })).toBeFocused();
	await expect(solveAllButton(page)).toHaveText('Solve all (3)');
	const ids = ['S1', 'S2', 'S3'] as const;
	const solves = ids.map((id) => solveAnswer(page, id));
	const duties = ids.map((id) => curveAnswer(page, 'group', id));
	await solveAll(page);
	const solved = (await Promise.all(solves)).map((r) => r.solvedState!);
	for (const d of await Promise.all(duties)) expect(d.status).toBe(200);
	await expect(solveAllButton(page)).toHaveAttribute('aria-disabled', 'true');
	await expect(
		page.getByRole('banner').getByRole('button', { name: 'Solve Base case' })
	).toBeFocused();

	// 5. Running combinations: four groups, each with its lineup line and each pump's values from
	// its own solve, in display units; three rings. Nit 5 (slice 5b): each heading led by its case's
	// number, the case's place in the Scenarios list, heard as "Case n:" before the name.
	const combos = card.getByRole('table', { name: 'Running combinations' });
	const group = (heading: RegExp) =>
		combos.getByRole('rowgroup').filter({ has: page.getByRole('rowheader', { name: heading }) });
	const escape = (text: string) => text.replace(/[()]/g, '\\$&');
	const cases = [
		[/^Base case \(shown\)/, base],
		...names.map((n, i) => [new RegExp(`^Case ${i + 1}: ${escape(n)}`), solved[i]!] as const)
	] as const;
	await expect(caseTagBoxes(combos.locator('th[scope="rowgroup"]'))).toHaveText([
		'Base',
		'1',
		'2',
		'3'
	]);
	await expect(combos.getByRole('rowgroup')).toHaveCount(1 + cases.length);
	const pumps = ['P1', 'P2', 'P3', 'P4'];
	for (const [heading, state] of cases) {
		await expect(group(heading)).toHaveCount(1);
		await expect(group(heading).getByRole('rowheader').first()).toContainText(
			lineupLine(state, pumps)
		);
		for (const pump of pumps) {
			const r = state.pumpResults[pump]!;
			if (r.status === 'off') continue;
			const row = group(heading)
				.getByRole('row')
				.filter({ has: page.getByRole('rowheader', { name: `Pump ${pump}`, exact: true }) });
			const cell = async (label: string) =>
				squash(await row.locator(`[data-label="${label}"]`).innerText());
			shows(await cell('Flow (L/s)'), r.operatingFlow * 1000);
			shows(await cell('Head (m)'), r.operatingHead);
			if (r.shaftPower !== null) shows(await cell('Shaft power (kW)'), r.shaftPower / 1000);
			if (r.npshMargin !== null) shows(await cell('NPSH margin (m)'), r.npshMargin);
		}
	}
	const legend = card.getByRole('figure').getByRole('list', { name: 'Legend' });
	for (const [i, n] of names.entries()) {
		await expect(legend.getByText(`Case ${i + 1}: ${n} (station duty)`)).toBeVisible();
	}
	await expect(legend.getByText(/ \(station duty\)$/)).toHaveCount(3);

	// 7. No sideways scroll; axe clean over the whole Pumps tab, every disclosure open.
	await noSidewaysScroll(page);
	await openEveryDisclosure(page);
	await expect(block.getByRole('list', { name: 'Stop order' })).toBeVisible();
	await noSidewaysScroll(page);
	await axeCleanTab(page);
});

// ---- D24 slice L3: the curve family -----------------------------------------------------------

test('the curve family: after adding cases by number running, each lineup’s own group curve named, listed with its points and in the image; axe clean', async ({
	page,
	isMobile
}) => {
	// L1's flow (pump-lineups.md §10.1), the default stop order: three cases added and solved.
	const project = structuredClone(projectOf('lineups'));
	delete project.scenarios;
	await open(page, project);
	await solveConverged(page);
	const { card, toggle } = await openCard(page);
	const answers = await answersOf(page, () => toggle.click());
	expect(answers.group.status).toBe(200);
	const block = card.getByRole('region', { name: 'Add cases' });
	await expect(block.getByRole('radio', { name: 'By number running' })).toBeChecked();
	const names = [
		'3 of 4 running (Pump P4 off)',
		'2 of 4 running (Pump P3, Pump P4 off)',
		'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
	];
	await expect(block.getByRole('list', { name: 'Cases:' }).getByRole('listitem')).toHaveText(names);
	await block.getByRole('button', { name: 'Add 3 cases' }).click();
	// The focus stays on Add; Solve all is the Scenarios menu's (build-density.md §19).
	await expect(block.getByRole('button', { name: /^Add( \d+)? cases?$/ })).toBeFocused();
	await expect(solveAllButton(page)).toHaveText('Solve all (3)');
	const ids = ['S1', 'S2', 'S3'] as const;
	const curves = ids.map((id) => curveAnswer(page, 'group', id));
	await solveAll(page);
	const family = await Promise.all(curves);
	for (const c of family) expect(c.status).toBe(200);
	const running = [3, 2, 1];

	// 1. The chart's accessible name: each case's curve in its words, then the curves drawn
	// (§9.6), every lineup the same as the base outside the station; each case by its number
	// (nit 5, slice 5b: "case 1", no bare "1").
	const figure = card.getByRole('figure');
	const img = figure.getByRole('img');
	await expect(img).toHaveAccessibleName(
		/; other cases' group curves drawn: case 1 \(3 running\), case 2 \(2 running\) and case 3 \(1 running\); group curve shown; group system curve shown\.$/
	);
	const accessible = (await img.getAttribute('aria-label'))!;
	for (const [i, name] of names.entries()) {
		expect(accessible).toMatch(
			new RegExp(
				`case ${i + 1}: ${name.replace(/[()]/g, '\\$&')}, [\\d.]+ L/s at a rise of [\\d.]+ m \\(Yes: the same rest of the network; group curve: drawn \\(${running[i]} running\\): it crosses the group system curve at the ring\\)`
			)
		);
	}
	await expect(
		figure
			.getByRole('list', { name: 'Legend' })
			.getByText("Other cases' group curves (slate; dashed beyond a pump's data)")
	).toBeVisible();

	// 2. The data table: the column, and every point of each case's curve, in display units.
	await card.getByRole('button', { name: 'Show data table of the group chart' }).click();
	const duties = card.getByRole('table', { name: "Other cases' station duties" });
	await expect(duties.getByRole('columnheader', { name: 'Its group curve' })).toBeVisible();
	for (const [i] of names.entries()) {
		await expect(
			duties
				.getByRole('row')
				.nth(i + 1)
				.getByRole('cell')
				.nth(3)
		).toHaveText(`Drawn (${running[i]} running): it crosses the group system curve at the ring`);
	}
	// In its disclosure, opened first (proposal pumps-results-layout.md §9 S7).
	const table = await openCurveTable(
		card,
		"Other cases' group curves (station's flow at each rise)"
	);
	await expect(table).toBeVisible();
	await expect(table.getByRole('rowgroup')).toHaveCount(1 + names.length);
	for (const [i, name] of names.entries()) {
		// Its header led by its case's number in a box (nit 5, slice 5b), heard as "Case n:".
		const group = table.getByRole('rowgroup').filter({
			has: page.getByRole('rowheader', {
				name: `Case ${i + 1}: ${name}: ${running[i]} running`,
				exact: true
			})
		});
		await expect(group).toHaveCount(1);
		await expect(caseTagBoxes(group.getByRole('rowheader').first())).toHaveText(String(i + 1));
		const points = [...family[i]!.body.points].sort((a, b) => a.head - b.head);
		expect(points).toHaveLength(42);
		await expect(group.getByRole('row')).toHaveCount(1 + points.length);
		const rises = (await group.locator('[data-label="Rise (m)"]').allInnerTexts()).map(squash);
		const flows = (await group.locator('[data-label="Flow (L/s)"]').allInnerTexts()).map(squash);
		expect(rises).toHaveLength(points.length);
		for (const [j, p] of points.entries()) {
			shows(rises[j]!, p.head);
			if (p.flow === null) expect(flows[j]).toBe('—');
			else shows(flows[j]!, p.flow * 1000);
		}
	}
	// Its box (a region only while it overflows since S7, pumps-results-layout.md §9 S7).
	const region = table.locator('..');
	if (isMobile) {
		// A list on a phone: nothing to scroll sideways.
		expect(await region.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
	}
	await noSidewaysScroll(page);

	// 3. Download image with the family on: a PNG at 1600 px wide.
	const image = card.locator('[data-chart-image]');
	await expect(image).not.toHaveAttribute('aria-disabled', 'true');
	const [download] = await Promise.all([page.waitForEvent('download'), image.click()]);
	const png = readFileSync(await download.path());
	expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
	expect(png.toString('latin1', 12, 16)).toBe('IHDR');
	expect(png.readUInt32BE(16)).toBe(1600);

	// 4. Axe clean over the whole Pumps tab, every disclosure open and the data table shown.
	await openEveryDisclosure(page);
	await noSidewaysScroll(page);
	await axeCleanTab(page);
});
