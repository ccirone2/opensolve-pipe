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
 * The Pumps together card (CLAUDE.md D20, proposal pump-groups.md §6), against the real app and
 * API, on desktop and on a phone: two pumps in parallel between Crane tees, two in series (US
 * display units) and two pumps the API refuses as a station (a tank on the discharge header).
 * The projects are the shared fixture's (apps/api/tests/fixtures/pump_groups_input.py); every
 * expected number is read from the intercepted response of the real API and compared in display
 * units, to the rounding the table shows. No sideways scroll; the image is a PNG.
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

async function answerOf(page: Page, press: () => Promise<void>) {
	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/pump-group-curve') && r.request().method() === 'POST'
	);
	await press();
	const response = await answer;
	return {
		status: response.status(),
		body: (await response.json()) as PumpGroupCurveResponse & Partial<ErrorResponse>,
		request: response.request().postDataJSON() as PumpGroupCurveRequest
	};
}

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
	const { status, body, request } = await answerOf(page, () => toggle.click());
	expect(status).toBe(200);
	expect(request.pumpIds).toEqual(['PA', 'PB']);
	expect(request).not.toHaveProperty('scenarioId');
	const duty = body.duty!;
	expect(body.station.arrangement).toBe('parallel');

	const figure = card.getByRole('figure', { name: 'Pump PA and Pump PB in parallel' });
	await expect(figure).toBeVisible();
	await expect(figure.getByRole('img')).toHaveAccessibleName(/; group curve shown\.$/);
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
