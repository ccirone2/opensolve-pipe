import { gunzipSync, gzipSync } from 'node:zlib';
import { readFileSync } from 'node:fs';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';
import type { Project, SolveRequest, SolveResponse } from '../src/lib/api/types';
import { condenserWaterExample } from '../src/lib/utils/examples';
import {
	buildPane,
	cellText,
	chooseCase,
	currentHeading,
	openCases,
	openScenarioManager,
	resultsView,
	showPane,
	solveConverged
} from './support';

/**
 * The Pump lineups table (CLAUDE.md D24, proposal pump-lineups.md §8 and §10.2 "e2e"), against
 * the real app and API, at 1280×800 and 390×844:
 * 1. the condenser example: six columns, the winter case's five status changes Off and marked with
 *    its 14 other changes, New lineup's "Scenario 2" the same case as the base, presses naming it
 *    by ids, Undo one step, the arrows and Space (desktop), then Solve all with CWP-5 and CWP-6 off
 *    in that case's results;
 * 2. the same case made by New scenario and Build's Status segments on a second page gives the
 *    same link, apart from metadata.modified;
 * 3. `two-systems` by link: the group header row, a standby turned on marked "Base value Off", a
 *    crossed lineup named with "; ";
 * 4. from the Pumps together card: the card's pumps only, then Show every pump; axe clean with the
 *    tab open, filtered and unfiltered;
 * 5. the phone: the picker, the segments with Changed · Base · Reset, New lineup picking the new
 *    case, no sideways page scroll at 390 px and 320 px;
 * 6. the layout at 1280×800 with 21 rows and the condenser example's names: the dialog body does
 *    not scroll and at least 6 rows are fully visible in the table's box; the Cases tab at xl: no
 *    prose line longer than max-w-prose, its body's scroll recorded.
 * The projects are the condenser example (utils/examples.ts) and the shared fixture's
 * `two-systems` (apps/api/tests/fixtures/pump_groups_input.py), opened by link; every string is
 * §8.12's, word for word.
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
const twoSystems = () =>
	structuredClone(fixture.cases.find((c) => c.name === 'two-systems')!.project);

/** Open a project by its link (the app's own encoding: gzip, base64url). */
async function open(page: Page, project: Project) {
	const encoded = gzipSync(Buffer.from(JSON.stringify(project))).toString('base64url');
	await page.goto(`/p#${encoded}`);
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
}

/** The project in a page's link, as the app wrote it. */
function linked(url: string): Project {
	const hash = new URL(url).hash.slice(1);
	return JSON.parse(gunzipSync(Buffer.from(hash, 'base64url')).toString('utf8')) as Project;
}

const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
async function axeClean(page: Page) {
	const scan = await new AxeBuilder({ page }).include('dialog[open]').withTags(AXE_TAGS).analyze();
	expect(scan.violations.map((v) => `${v.id} (${v.nodes.length})`)).toEqual([]);
}

async function noSidewaysScroll(page: Page) {
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
		true
	);
}

/** The manager on Pump lineups. */
async function openLineups(page: Page): Promise<Locator> {
	const manager = await openScenarioManager(page);
	const tab = manager.getByRole('tab', { name: 'Pump lineups' });
	if ((await tab.getAttribute('aria-selected')) !== 'true') await tab.click();
	await expect(tab).toHaveAttribute('aria-selected', 'true');
	return manager;
}

const gridOf = (manager: Locator) =>
	manager.getByRole('grid', { name: 'Pumps on or off in each case' });
/** A switch: named by its visible headers, the pump's and the case's (§8.5). */
const switchOf = (manager: Locator, pump: string, caseName: string) =>
	gridOf(manager).getByRole('switch', { name: `${pump} ${caseName}`, exact: true });
const pickerOf = (manager: Locator) => manager.getByRole('combobox', { name: 'Case to edit' });
const segmentOf = (manager: Locator, pump: string) =>
	manager.getByRole('radiogroup', { name: pump, exact: true });

/** Pick a case on a phone by its name (its option reads "{name} ({changes text})"). */
async function pick(manager: Locator, caseName: string) {
	const picker = pickerOf(manager);
	const texts = await picker.locator('option').allInnerTexts();
	const label = texts.find((t) => t === caseName || t.startsWith(`${caseName} (`));
	expect(label, `${caseName} in ${JSON.stringify(texts)}`).toBeDefined();
	await picker.selectOption({ label: label! });
}

/**
 * Turn `pump` to `value` in case `caseName`: a press of its switch on desktop (when it is not so
 * already), of its segment on a phone.
 */
async function setPump(
	manager: Locator,
	isMobile: boolean,
	caseName: string,
	pump: string,
	value: 'On' | 'Off'
) {
	if (isMobile) {
		await pick(manager, caseName);
		await segmentOf(manager, pump).getByRole('radio', { name: value }).click();
		return;
	}
	const s = switchOf(manager, pump, caseName);
	if ((await s.getAttribute('aria-checked')) !== String(value === 'On')) await s.click();
}

/** The scenario names in the manager's table (desktop) or picker (phone). */
async function caseNames(manager: Locator, isMobile: boolean): Promise<string[]> {
	if (isMobile) {
		const texts = await pickerOf(manager).locator('option').allInnerTexts();
		return texts
			.slice(1)
			.map((t) => t.replace(/ \(\d+ changes?(, \d+ no longer appl(y|ies))?\)$/, ''));
	}
	const headers = gridOf(manager).getByRole('rowheader');
	const names = await headers.evaluateAll((hs) =>
		hs.map((h) => h.querySelector('span')?.textContent ?? '')
	);
	return names.slice(1);
}

/** Show a component in Build (Jump to). */
async function showComponent(page: Page, name: string): Promise<Locator> {
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: new RegExp(`^${name}`) })
		.click();
	await expect(currentHeading(page)).toHaveText(name);
	return buildPane(page);
}

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

const CWP = (n: number) => `Condenser water pump CWP-${n}`;
const WINTER = 'Winter: tower bypassed';

test('the condenser example: a lineup made by presses, Undo, the keys, solved; the same link as Build’s', async ({
	page,
	isMobile
}) => {
	test.setTimeout(180_000);
	await open(page, condenserWaterExample());
	const manager = await openLineups(page);
	const status = manager.getByRole('status');

	// 1. Six columns, the base case and the winter case.
	if (isMobile) {
		await expect(gridOf(manager)).toHaveCount(0);
		await pick(manager, WINTER);
		await expect(manager.locator('[data-picked-line] p')).toHaveText([
			`Changes go to «${WINTER}» only: 19 of at most 30 changes.`,
			'14 other changes'
		]);
		await expect(manager.getByRole('radiogroup')).toHaveCount(6);
		await expect(segmentOf(manager, CWP(1)).getByRole('radio', { name: 'On' })).toBeChecked();
		for (const n of [2, 3, 4, 5, 6]) {
			const segment = segmentOf(manager, CWP(n));
			await expect(segment.getByRole('radio', { name: 'Off' })).toBeChecked();
			await expect(segment).toHaveAccessibleDescription(
				/^Changed in this scenario\. Base value On\./
			);
		}
	} else {
		const grid = gridOf(manager);
		await expect(grid.getByRole('row').first().getByRole('columnheader')).toHaveText([
			'Case',
			...[1, 2, 3, 4, 5, 6].map((n) => `${CWP(n)} P${n}`)
		]);
		await expect(grid.getByRole('rowheader')).toHaveText([
			'Base case Set in Build',
			`${WINTER} S1 14 other changes`
		]);
		await expect(switchOf(manager, CWP(1), WINTER)).toHaveAttribute('aria-checked', 'true');
		await expect(switchOf(manager, CWP(1), WINTER)).not.toHaveAttribute('aria-describedby');
		for (const n of [2, 3, 4, 5, 6]) {
			const s = switchOf(manager, CWP(n), WINTER);
			await expect(s).toHaveAttribute('aria-checked', 'false');
			await expect(s).toHaveText('Off');
			await expect(s).toHaveAccessibleDescription('Changed in this scenario. Base value On.');
			await expect(s).toHaveAttribute('title', 'Changed in this scenario. Base value On.');
		}
	}

	// New lineup: "Scenario 2", the same case as the base case.
	await manager.getByRole('button', { name: 'New lineup' }).click();
	await expect(status).toHaveText('Added «Scenario 2», its pumps as in the base case.');
	if (isMobile) {
		await expect(pickerOf(manager)).toBeFocused();
		await expect(pickerOf(manager).locator('option:checked')).toHaveText('Scenario 2 (0 changes)');
		await expect(manager.locator('[data-picked-line] p')).toHaveText([
			'Changes go to «Scenario 2» only: 0 of at most 30 changes.',
			'Same case as the base case'
		]);
	} else {
		await expect(switchOf(manager, CWP(1), 'Scenario 2')).toBeFocused();
		await expect(gridOf(manager).getByRole('rowheader').last()).toHaveText(
			'Scenario 2 S2 Same case as the base case'
		);
	}

	// Press P6, then P5: the name follows by ids (§4.4).
	await setPump(manager, isMobile, 'Scenario 2', CWP(6), 'Off');
	await expect(status).toHaveText(
		'«Scenario 2» is now «5 of 6 running (P6 off)»: a name the app made follows its pumps until you rename it.'
	);
	await setPump(manager, isMobile, '5 of 6 running (P6 off)', CWP(5), 'Off');
	expect(await caseNames(manager, isMobile)).toEqual([WINTER, '4 of 6 running (P5, P6 off)']);

	// Undo goes back one step.
	const undo = manager.getByRole('button', { name: /^Undo/ });
	await expect(undo).toHaveAccessibleName(`Undo turn ${CWP(5)} off in 4 of 6 running (P5, P6 off)`);
	await undo.click();
	await expect(status).toHaveText(`Undid turn ${CWP(5)} off in 4 of 6 running (P5, P6 off).`);
	expect(await caseNames(manager, isMobile)).toEqual([WINTER, '5 of 6 running (P6 off)']);

	if (isMobile) {
		await setPump(manager, isMobile, '5 of 6 running (P6 off)', CWP(5), 'Off');
	} else {
		// The arrows and Space; the focus stays on the pressed cell; Tab leaves the grid and
		// Shift+Tab comes back to the cell last used.
		await switchOf(manager, CWP(6), '5 of 6 running (P6 off)').focus();
		await page.keyboard.press('ArrowLeft');
		await expect(switchOf(manager, CWP(5), '5 of 6 running (P6 off)')).toBeFocused();
		await page.keyboard.press('Space');
		const pressed = switchOf(manager, CWP(5), '4 of 6 running (P5, P6 off)');
		await expect(pressed).toHaveAttribute('aria-checked', 'false');
		await expect(pressed).toBeFocused();
		await page.keyboard.press('ArrowUp');
		await expect(switchOf(manager, CWP(5), WINTER)).toBeFocused();
		await page.keyboard.press('Tab');
		await expect(gridOf(manager).locator(':focus')).toHaveCount(0);
		await expect(manager.getByRole('button', { name: /^Undo/ })).toBeFocused();
		await page.keyboard.press('Shift+Tab');
		await expect(switchOf(manager, CWP(5), WINTER)).toBeFocused();
	}
	expect(await caseNames(manager, isMobile)).toEqual([WINTER, '4 of 6 running (P5, P6 off)']);
	// The link as the table left it (a solve then stamps the method version into the project).
	await expect
		.poll(() => linked(page.url()).scenarios?.[1]?.name)
		.toBe('4 of 6 running (P5, P6 off)');
	const fromTable = linked(page.url());

	// Done, Solve all: the case solves with CWP-5 and CWP-6 off in its results.
	await manager.getByRole('button', { name: 'Done' }).click();
	await expect(manager).toBeHidden();
	const answered = solveAnswer(page, 'S2');
	await (await openCases(page)).getByRole('button', { name: 'Solve all' }).click();
	const answer = await answered;
	expect(answer.success).toBe(true);
	expect(answer.solvedState.converged).toBe(true);
	const pumps = answer.solvedState.pumpResults;
	expect([1, 2, 3, 4, 5, 6].map((n) => pumps[`P${n}`]?.status)).toEqual([
		'running',
		'running',
		'running',
		'running',
		'off',
		'off'
	]);
	await expect(
		page.getByRole('group', { name: 'Case', exact: true, includeHidden: true })
	).not.toContainText('Solving');
	await chooseCase(page, '4 of 6 running (P5, P6 off) (2 changes)');
	await showPane(page, 'Results');
	const table = (await resultsView(page, 'Pumps')).getByRole('table', {
		name: 'Results per pump'
	});
	for (const n of [5, 6]) expect(await cellText(table, CWP(n), 'Status')).toBe('Off');
	expect(await cellText(table, CWP(4), 'Status')).not.toBe('Off');

	// 2. The same case by New scenario and Build's Status segments, on a second page.
	const build = await page.context().newPage();
	await open(build, condenserWaterExample());
	const cases = await openScenarioManager(build);
	await cases.getByRole('button', { name: 'New scenario' }).click();
	await cases.getByRole('button', { name: 'Done' }).click();
	await expect(cases).toBeHidden();
	for (const n of [6, 5]) {
		const panel = await showComponent(build, CWP(n));
		await panel
			.getByRole('radiogroup', { name: 'Status' })
			.getByRole('radio', { name: 'Off' })
			.click();
	}
	const without = (p: Project) => {
		const copy = structuredClone(p);
		delete (copy.metadata as { modified?: string }).modified;
		return copy;
	};
	await expect
		.poll(() => linked(build.url()).scenarios?.[1]?.name)
		.toBe('4 of 6 running (P5, P6 off)');
	expect(fromTable.scenarios?.[1]?.overrides).toEqual(
		[6, 5].map((n) => ({ kind: 'component', componentId: `P${n}`, field: 'status', value: 'off' }))
	);
	expect(without(linked(build.url()))).toEqual(without(fromTable));
	await build.close();
});

test('two-systems: the group header row, a standby turned on, a crossed lineup named with “; ”', async ({
	page,
	isMobile
}) => {
	await open(page, twoSystems());
	const manager = await openLineups(page);
	if (isMobile) {
		await expect(manager.locator('fieldset > legend')).toHaveText([
			'Pumps together, PA and PB',
			'Pumps together, P1 to P3',
			'Other pumps'
		]);
		await pick(manager, 'PB in service, PA off');
		const pb = segmentOf(manager, 'Pump PB');
		await expect(pb.getByRole('radio', { name: 'On' })).toBeChecked();
		await expect(pb).toHaveAccessibleDescription(/^Changed in this scenario\. Base value Off\./);
	} else {
		await expect(gridOf(manager).getByRole('row').first().getByRole('columnheader')).toHaveText([
			'Case',
			'Pumps together, PA and PB',
			'Pumps together, P1 to P3',
			'Other pumps'
		]);
		const pb = switchOf(manager, 'Pump PB', 'PB in service, PA off');
		await expect(pb).toHaveAttribute('aria-checked', 'true');
		await expect(pb).toHaveAccessibleDescription('Changed in this scenario. Base value Off.');
	}
	// A crossed lineup: New lineup, PB on, then P1 off.
	await manager.getByRole('button', { name: 'New lineup' }).click();
	await setPump(manager, isMobile, 'Scenario 4', 'Pump PB', 'On');
	await setPump(manager, isMobile, '2 of 2 running', 'Pump P1', 'Off');
	expect((await caseNames(manager, isMobile)).at(-1)).toBe(
		'2 of 2 running; 2 of 3 running (Pump P1 off)'
	);
	expect(await caseNames(manager, isMobile)).toContain(
		'2 of 2 running; 2 of 3 running (Pump P3 off)'
	);
});

test('from the Pumps together card: its pumps only, then every pump; axe clean filtered and unfiltered', async ({
	page,
	isMobile
}) => {
	await open(page, twoSystems());
	await solveConverged(page);
	const pumpsView = await resultsView(page, 'Pumps');
	const card = pumpsView.getByRole('region', { name: /^Pumps together/ });
	const answered = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/pump-group-curve') && r.request().method() === 'POST'
	);
	await card.getByRole('button', { name: /^Pumps together/ }).click();
	expect((await answered).status()).toBe(200);
	await card.getByRole('button', { name: 'Pump lineups table…' }).click();
	const manager = page.getByRole('dialog', { name: 'Scenarios' });
	await expect(manager.getByRole('tab', { name: 'Pump lineups' })).toHaveAttribute(
		'aria-selected',
		'true'
	);
	await expect(manager).toContainText(
		'Only the pumps on the Pumps together card are shown: Pump PA and Pump PB.'
	);
	if (isMobile) {
		await expect(manager.getByRole('radiogroup')).toHaveCount(2);
		await expect(manager.locator('fieldset > legend')).toHaveCount(0);
	} else {
		await expect(gridOf(manager).getByRole('row').first().getByRole('columnheader')).toHaveText([
			'Case',
			'Pump PA PA',
			'Pump PB PB'
		]);
	}
	await axeClean(page);
	await manager.getByRole('button', { name: 'Show every pump' }).click();
	await expect(manager).not.toContainText('Only the pumps');
	if (isMobile) {
		await expect(manager.getByRole('radiogroup')).toHaveCount(6);
		await expect(pickerOf(manager)).toBeFocused();
	} else {
		await expect(gridOf(manager).getByRole('row').nth(1).getByRole('columnheader')).toHaveCount(6);
		await expect(switchOf(manager, 'Pump PA', 'PB in service, PA off')).toBeFocused();
	}
	await axeClean(page);
	await noSidewaysScroll(page);
	// Done forgets the filter: the header's Scenarios shows every pump.
	await manager.getByRole('button', { name: 'Done' }).click();
	const again = await openLineups(page);
	await expect(again).not.toContainText('Only the pumps');
});

test('on a phone: the picker, Changed · Base · Reset, New lineup picks the new case, no sideways scroll', async ({
	page,
	isMobile
}) => {
	test.skip(!isMobile, 'the phone layout');
	await open(page, condenserWaterExample());
	const manager = await openLineups(page);
	await expect(manager).toContainText(
		'Pick a case, then turn its pumps on or off: the same change as in Build, one undo step each; in a name, running means switched on. The base case is changed in Build.'
	);
	// The default: the base case is shown, so the first scenario.
	await expect(pickerOf(manager).locator('option:checked')).toHaveText(`${WINTER} (19 changes)`);
	const cwp2 = segmentOf(manager, CWP(2)).locator(
		'xpath=ancestor::div[contains(@class,"field")][1]'
	);
	await expect(cwp2).toContainText('Changed');
	await expect(cwp2).toContainText('Base: On');
	await expect(
		manager.getByRole('button', { name: `Reset ${CWP(2)} to the base value, On` })
	).toBeVisible();
	await noSidewaysScroll(page);

	// New lineup picks the new case and focuses the picker; a press, then Reset back by the name rule.
	await manager.getByRole('button', { name: 'New lineup' }).click();
	await expect(pickerOf(manager)).toBeFocused();
	await expect(pickerOf(manager).locator('option:checked')).toHaveText('Scenario 2 (0 changes)');
	await segmentOf(manager, CWP(6)).getByRole('radio', { name: 'Off' }).click();
	await expect(pickerOf(manager).locator('option:checked')).toHaveText(
		'5 of 6 running (P6 off) (1 change)'
	);
	await manager.getByRole('button', { name: `Reset ${CWP(6)} to the base value, On` }).click();
	await expect(pickerOf(manager).locator('option:checked')).toHaveText('Scenario 2 (0 changes)');
	await expect(manager.getByRole('status')).toHaveText(
		'«5 of 6 running (P6 off)» is now «Scenario 2»: a name the app made follows its pumps until you rename it.'
	);
	await expect(segmentOf(manager, CWP(6)).getByRole('radio', { name: 'On' })).toBeFocused();

	// The base case: a list, no controls.
	await pick(manager, 'Base case');
	await expect(manager.locator('[data-picked-line] p')).toHaveText([
		"The base case's pumps: change them in Build."
	]);
	await expect(manager.getByRole('radiogroup')).toHaveCount(0);
	await expect(manager.locator('dl > div')).toHaveText(
		[1, 2, 3, 4, 5, 6].map((n) => `${CWP(n)}: On`)
	);
	await noSidewaysScroll(page);
	await axeClean(page);

	await page.setViewportSize({ width: 320, height: 640 });
	await pick(manager, WINTER);
	await noSidewaysScroll(page);
	expect(
		await manager.evaluate((d) => {
			const body = d.querySelector('.overflow-y-auto') as HTMLElement;
			return body.scrollWidth <= body.clientWidth;
		})
	).toBe(true);
});

test('the layout at 1280×800: 21 rows with the condenser example’s names, the Cases tab at xl', async ({
	page,
	isMobile
}) => {
	test.skip(isMobile, 'the desktop table');
	test.setTimeout(120_000);
	await open(page, condenserWaterExample());
	let manager = await openLineups(page);
	// Nineteen lineups by presses (P2 to P6 off as the bits of k), with the app's names.
	for (let k = 1; k <= 19; k++) {
		await manager.getByRole('button', { name: 'New lineup' }).click();
		const row = gridOf(manager).getByRole('row').last();
		await expect(row.getByRole('rowheader')).toContainText(`S${k + 1}`);
		for (const n of [2, 3, 4, 5, 6].filter((_, b) => (k >> b) & 1)) {
			await row
				.getByRole('switch')
				.nth(n - 1)
				.click();
		}
	}
	await expect(gridOf(manager).getByRole('rowheader')).toHaveCount(21);
	await expect(manager.getByRole('button', { name: 'New lineup' })).toHaveAttribute(
		'aria-disabled',
		'true'
	);
	// The manager opened afresh: the body does not scroll, at least six rows fully in the box.
	await manager.getByRole('button', { name: 'Done' }).click();
	manager = await openLineups(page);
	const layout = await manager.evaluate((dialog) => {
		const body = dialog.querySelector('.overflow-y-auto') as HTMLElement;
		const box = dialog.querySelector('[data-lineups-box]') as HTMLElement;
		const b = box.getBoundingClientRect();
		const head = box.querySelector('thead')!.getBoundingClientRect();
		const rows = [...box.querySelectorAll('tbody tr')].map((tr) => tr.getBoundingClientRect());
		return {
			bodyScrollHeight: body.scrollHeight,
			bodyClientHeight: body.clientHeight,
			boxHeight: Math.round(b.height),
			headerHeight: Math.round(head.height),
			rowsFullyVisible: rows.filter((r) => r.top >= head.bottom - 0.5 && r.bottom <= b.bottom + 0.5)
				.length
		};
	});
	test.info().annotations.push({ type: 'lineups layout', description: JSON.stringify(layout) });
	expect(layout.bodyScrollHeight).toBeLessThanOrEqual(layout.bodyClientHeight);
	expect(layout.rowsFullyVisible).toBeGreaterThanOrEqual(6);
	await axeClean(page);

	// The Cases tab at xl: no prose line longer than max-w-prose (65ch); the body's scroll recorded.
	await manager.getByRole('tab', { name: 'Cases (21)' }).click();
	await manager.locator('details summary').first().click();
	const prose = await manager.evaluate((dialog) => {
		const panel = dialog.querySelector('[role="tabpanel"]') as HTMLElement;
		const probe = document.createElement('span');
		probe.style.cssText = 'position:absolute;visibility:hidden;width:65ch;font-size:14px';
		panel.appendChild(probe);
		const limit = probe.getBoundingClientRect().width;
		probe.remove();
		let widest = 0;
		const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
		for (let n = walker.nextNode(); n; n = walker.nextNode()) {
			if (!n.textContent?.trim()) continue;
			const range = document.createRange();
			range.selectNodeContents(n);
			for (const r of range.getClientRects()) widest = Math.max(widest, r.width);
		}
		const body = dialog.querySelector('.overflow-y-auto') as HTMLElement;
		return {
			dialogWidth: Math.round(dialog.getBoundingClientRect().width),
			limit: Math.round(limit),
			widest: Math.round(widest),
			bodyScrollHeight: body.scrollHeight,
			bodyClientHeight: body.clientHeight
		};
	});
	test.info().annotations.push({ type: 'cases layout', description: JSON.stringify(prose) });
	expect(prose.dialogWidth).toBe(1024);
	expect(prose.widest).toBeLessThanOrEqual(prose.limit + 1);
	await axeClean(page);
});
