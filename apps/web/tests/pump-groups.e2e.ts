import { readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { expect, test, type Locator, type Page } from '@playwright/test';
import type {
	ErrorResponse,
	Project,
	PumpGroupCurveRequest,
	PumpGroupCurveResponse
} from '../src/lib/api/types';
import { halfUlp, resultsView, solveConverged } from './support';

/**
 * The Pumps together card (CLAUDE.md D21, proposal pump-groups.md §6), against the real app and
 * API, on desktop and on a phone: two pumps in parallel between Crane tees, two in series (US
 * display units) and two pumps the API refuses as a station (a tank on the discharge header).
 * Slice 4b (§7): the group system curve asked for after the group curve, drawn and listed in the
 * data table, the Group point at the curves' crossing, "Read along the curves", an FCV outside
 * the station (points without a rise, and why) and a PRV inside it (no group curve, the group
 * system curve all the same). The projects are the shared fixture's
 * (apps/api/tests/fixtures/pump_groups_input.py); every expected number is read from the
 * intercepted response of the real API and compared in display units, to the rounding the table
 * shows. No sideways scroll; the image is a PNG.
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

/** The answer to a group-curve request of `curve` ('group' or 'system'). */
function curveAnswer(page: Page, curve: 'group' | 'system') {
	return page
		.waitForResponse(
			(r) =>
				r.url().endsWith('/api/v1/pump-group-curve') &&
				r.request().method() === 'POST' &&
				(r.request().postDataJSON() as PumpGroupCurveRequest).curve === curve
		)
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

	await card.getByRole('button', { name: 'Show data table' }).click();
	const samples = card.getByRole('table', { name: "Group curve (station's flow at each rise)" });
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

	// The data table: every point of the group system curve, its flow and rise as the response's.
	await card.getByRole('button', { name: 'Show data table' }).click();
	const table = card.getByRole('table', {
		name: "Group system curve (rise the rest of the network needs at each station's flow)"
	});
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
	await card.getByRole('button', { name: 'Show data table' }).click();
	const table = card.getByRole('table', {
		name: "Group system curve (rise the rest of the network needs at each station's flow)"
	});
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
	await card.getByRole('button', { name: 'Show data table' }).click();
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
