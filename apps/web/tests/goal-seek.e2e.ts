import { expect, test, type Locator, type Page, type Request, type Route } from '@playwright/test';
import type { GoalSeekRequest, GoalSeekResponse } from '../src/lib/api/types';
import {
	buildPane,
	cellText,
	currentHeading,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	traceOf
} from './support';

/**
 * Goal seek (PRD §3.9, proposal goal-seek.md §7.6) against the real app and API, on desktop and on
 * a phone: a goal met and applied to the base case (the Links table shows what was reached), undo;
 * a target not reached; Cancel in the dialog and in the header; a scenario run applied as a new
 * scenario; a result out of date on a project opened from a link and never solved, and the Solve
 * controls waiting during a run; the trace's entry; the layout.
 *
 * Network: the home page's pump-transfer example (illustrative, made-up inputs): at 100 % speed
 * about 19 L/s flows from Transfer pump to the discharge isolation valve. The targets (15 L/s,
 * 25 L/s) and the scenario's suction-tank level are made-up test inputs; the values found are the
 * API's, checked only against the ranges the example allows.
 */

const PATH = '/api/v1/goal-seek';
const LINK = 'Transfer pump → Discharge isolation valve';

async function openExample(page: Page) {
	await page.goto('/');
	await page.getByRole('link', { name: /^Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(currentHeading(page)).toHaveText('Suction tank');
}

const goalSeekButton = (page: Page) =>
	resultsPane(page).getByRole('button', { name: /^Goal seek/ });
const dialog = (page: Page) => page.getByRole('dialog', { name: 'Goal seek' });
const runButton = (page: Page) =>
	dialog(page).getByRole('button', { name: /^(Run goal seek|Seeking…)/ });
const closeButton = (page: Page) =>
	dialog(page).getByRole('button', { name: 'Close', exact: true }).last();

async function openGoalSeek(page: Page): Promise<Locator> {
	await showPane(page, 'Results');
	await goalSeekButton(page).click();
	await expect(dialog(page)).toBeVisible();
	return dialog(page);
}

/** Add a goal: the element (option label) and the result (radio label). */
async function addGoal(d: Locator, element: string, result: string): Promise<Locator> {
	await d.getByRole('button', { name: 'Add goal' }).click();
	const form = d.getByRole('group', { name: 'New goal' });
	await form.getByRole('combobox', { name: 'Element' }).selectOption({ label: element });
	await form.getByRole('radio', { name: result, exact: true }).check();
	await form.getByRole('button', { name: 'Add goal' }).click();
	await expect(form).toBeHidden();
	const card = d.getByRole('group', { name: new RegExp(`${element} · ${result}$`) });
	await expect(card.getByRole('textbox', { name: /^Target/ })).toBeFocused();
	return card;
}

/** Add a variable: the element (option label) and the value (radio label), default bounds. */
async function addVariable(d: Locator, element: string, value: string): Promise<Locator> {
	await d.getByRole('button', { name: 'Add variable' }).click();
	const form = d.getByRole('group', { name: 'New variable' });
	await form.getByRole('combobox', { name: 'Element' }).selectOption({ label: element });
	await form.getByRole('radio', { name: value, exact: true }).check();
	await form.getByRole('button', { name: 'Add variable' }).click();
	await expect(form).toBeHidden();
	const card = d.getByRole('group', { name: new RegExp(`${element} · ${value}$`) });
	await expect(card.getByRole('textbox', { name: /^From/ })).toBeFocused();
	return card;
}

/** The pump-speed-for-a-flow setup: the flow into the discharge valve, the pump's speed. */
async function speedForFlow(page: Page, target: string): Promise<Locator> {
	const d = await openGoalSeek(page);
	const goal = await addGoal(d, LINK, 'Flow');
	await setNumber(goal, /^Target/, target);
	const variable = await addVariable(d, 'Transfer pump', 'Speed');
	await expect(variable.getByText('Defaults: 20 % to 100 %.')).toBeVisible();
	return d;
}

/** Run, and wait for the API's answer. */
async function run(page: Page): Promise<{ request: GoalSeekRequest; body: GoalSeekResponse }> {
	const answer = page.waitForResponse(
		(r) => r.url().endsWith(PATH) && r.request().method() === 'POST'
	);
	await runButton(page).click();
	const response = await answer;
	expect(response.status(), (await response.text()).slice(0, 500)).toBe(200);
	return {
		request: response.request().postDataJSON() as GoalSeekRequest,
		body: (await response.json()) as GoalSeekResponse
	};
}

async function hold(page: Page): Promise<Route[]> {
	const held: Route[] = [];
	await page.route(`**${PATH}`, (route) => {
		held.push(route);
	});
	return held;
}

function aborted(page: Page): Promise<Request> {
	return page.waitForEvent('requestfailed', (r) => r.url().endsWith(PATH));
}

function sidewaysScroll(page: Page): Promise<number> {
	return page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
}

/** The percentage of the first value found ("86.1174 %" → 86.1174). */
async function speedFound(d: Locator): Promise<number> {
	const text = await d.getByRole('definition').first().locator('strong').innerText();
	return Number(text.replace(/[^\d.]/g, ''));
}

test('a goal met, applied to the base case, the Links table showing it; undo', async ({ page }) => {
	await openExample(page);
	const d = await speedForFlow(page, '15');
	const { request, body } = await run(page);
	// The request carries SI values and no scenario.
	expect(request.scenarioId).toBeUndefined();
	expect(request.variables).toEqual([
		{ kind: 'component', componentId: 'P1', field: 'speed', lower: 0.2, upper: 1 }
	]);
	expect(request.goals).toEqual([{ quantity: 'link_flow', elementId: 'L2', target: 0.015 }]);
	expect(body.success).toBe(true);
	await expect(d.getByText('Goal met', { exact: true })).toBeVisible();
	const speed = await speedFound(d);
	expect(speed).toBeGreaterThan(85);
	expect(speed).toBeLessThan(87);
	const reached = await cellText(
		d.getByRole('table', { name: 'Results reached' }),
		`${LINK} · Flow`,
		'Reached'
	);
	await d.getByRole('button', { name: 'Apply to base case' }).click();
	await expect(dialog(page)).toBeHidden();
	await expect(resultsPane(page).getByRole('status')).toHaveText('Last solve: converged');
	const links = await resultsView(page, 'Links');
	expect(`${await cellText(links, LINK, 'Flow L/s')} L/s`).toBe(reached);

	await page.getByRole('button', { name: /^Undo apply goal seek values/ }).click();
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: /^Transfer pump/ })
		.click();
	await expect(buildPane(page).getByRole('textbox', { name: /^Speed/ })).toHaveValue('100');
	const again = await openGoalSeek(page);
	await expect(again.getByRole('button', { name: 'Apply to base case' })).not.toHaveAttribute(
		'aria-disabled',
		'true'
	);
});

test('a target not reached: the closest value at the upper bound, Apply still offered', async ({
	page
}) => {
	await openExample(page);
	const d = await speedForFlow(page, '25');
	const { body } = await run(page);
	expect(body.success).toBe(false);
	await expect(d.getByText('Goal not met', { exact: true })).toBeVisible();
	await expect(d.getByText(/\(at the upper bound\)/)).toBeVisible();
	expect(await speedFound(d)).toBe(100);
	await expect(d.getByRole('button', { name: 'Apply to base case' })).toBeVisible();
	await d.getByText(/^Trial solves \(\d+\)$/).click();
	const trials = d.getByRole('table', { name: 'Trial solves' });
	await expect(trials.getByRole('row')).toHaveCount(body.result.evaluations.length + 1);
});

test('Cancel in the dialog and in the header: the request is aborted, nothing changes', async ({
	page
}) => {
	await openExample(page);
	const before = page.url();
	await speedForFlow(page, '15');
	const held = await hold(page);
	const first = aborted(page);
	await runButton(page).click();
	await expect.poll(() => held.length).toBe(1);
	await dialog(page).getByRole('button', { name: 'Cancel goal seek' }).click();
	await first;
	await expect(
		dialog(page).getByText('Goal seek cancelled. Nothing in the project changed.')
	).toBeVisible();
	expect(page.url()).toBe(before);

	const second = aborted(page);
	await runButton(page).click();
	await expect.poll(() => held.length).toBe(2);
	await closeButton(page).click();
	await expect(dialog(page)).toBeHidden();
	await expect(goalSeekButton(page)).toHaveAccessibleName('Goal seek (running)');
	await page.getByRole('button', { name: 'Cancel goal seek' }).click();
	await second;
	await expect(goalSeekButton(page)).toHaveAccessibleName('Goal seek');

	await page.unroute(`**${PATH}`);
	await goalSeekButton(page).click();
	await run(page);
	await expect(dialog(page).getByText('Goal met', { exact: true })).toBeVisible();
});

test('a scenario run: never applied to the base, applied as a new scenario; undo', async ({
	page
}) => {
	await openExample(page);
	await page.getByRole('button', { name: /^Scenarios/ }).click();
	const manager = page.getByRole('dialog', { name: 'Scenarios' });
	await manager.getByRole('button', { name: 'New scenario' }).click();
	const name = manager.getByRole('textbox', { name: /^Name of scenario S\d+$/ }).last();
	await name.fill('Low suction');
	await name.press('Enter');
	await manager.getByRole('button', { name: 'Done' }).click();
	const caseMenu = page.getByRole('combobox', { name: 'Case', exact: true });
	await expect(caseMenu.locator('option:checked')).toHaveText(/^Low suction \(/);
	await showPane(page, 'Build');
	await expect(currentHeading(page)).toHaveText('Suction tank');
	await setNumber(buildPane(page), /^Liquid level/, '1.5');
	await expect(caseMenu.locator('option:checked')).toHaveText('Low suction (1 change)');

	const d = await speedForFlow(page, '15');
	await expect(d.getByText('Low suction', { exact: true })).toBeVisible();
	await expect(runButton(page)).toHaveAccessibleName('Run goal seek on Low suction');
	const { request } = await run(page);
	expect(request.scenarioId).toBe('S1');
	await expect(d.getByRole('button', { name: 'Apply to base case' })).toHaveCount(0);
	await expect(
		d.getByText(/^Not offered for the base case: the values were found with Low suction's changes/)
	).toBeVisible();
	await d.getByRole('button', { name: 'Apply as new scenario' }).click();
	await expect(dialog(page)).toBeHidden();
	await expect(caseMenu.locator('option:checked')).toHaveText('Goal seek 2 (2 changes)');
	await expect(resultsPane(page).getByRole('status')).toHaveText(
		'Last solve of Goal seek 2: converged'
	);
	await expect(
		resultsPane(page).getByText(/^Values found by goal seek on scenario Low suction for:/)
	).toBeVisible();
	await page.getByRole('button', { name: /^Undo add scenario Goal seek 2/ }).click();
	await expect(caseMenu.locator('option:checked')).toHaveText('Low suction (1 change)');
});

test('out of date on a project never solved, and every Solve waits during a run', async ({
	page
}) => {
	// The example as opened from its link: never solved, no results.
	await openExample(page);
	const d = await speedForFlow(page, '15');
	await run(page);
	await closeButton(page).click();
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: /^Transfer pump/ })
		.click();
	await setNumber(buildPane(page), /^Speed/, '95');
	await openGoalSeek(page);
	await expect(
		d.getByText(/^Out of date: the project changed after this goal seek/).first()
	).toBeVisible();
	const apply = d.getByRole('button', { name: 'Apply to base case' });
	await expect(apply).toHaveAttribute('aria-disabled', 'true');
	await expect(apply).toHaveAccessibleDescription(/^Out of date/);
	await closeButton(page).click();
	await page.getByRole('button', { name: /^Undo/ }).click();
	await openGoalSeek(page);
	await expect(apply).not.toHaveAttribute('aria-disabled', 'true');
	await run(page);
	await expect(apply).not.toHaveAttribute('aria-disabled', 'true');
	await closeButton(page).click();

	// Solved once, the link carries its method version: opened again, it offers Solve now.
	const unsolved = page.url();
	await page.getByRole('button', { name: 'Solve', exact: true }).click();
	await expect(resultsPane(page).getByRole('status')).toHaveText('Last solve: converged');
	await expect.poll(() => page.url()).not.toBe(unsolved);
	await page.reload();
	await expect(currentHeading(page)).toHaveText('Suction tank');
	await speedForFlow(page, '15');
	const held = await hold(page);
	await runButton(page).click();
	await expect.poll(() => held.length).toBe(1);
	await closeButton(page).click();
	const solveNow = resultsPane(page).getByRole('button', { name: 'Solve now' });
	await expect(solveNow).toHaveAttribute('aria-disabled', 'true');
	await expect(solveNow).toHaveAccessibleDescription(
		'A goal seek is running; Cancel in the header stops it.'
	);
	// Clicked anyway (Playwright waits for an aria-disabled button: force the click), it sends
	// nothing and the goal seek goes on.
	const solves: string[] = [];
	page.on('request', (r) => {
		if (r.url().endsWith('/api/v1/solve')) solves.push(r.url());
	});
	await solveNow.click({ force: true });
	await expect(goalSeekButton(page)).toHaveAccessibleName('Goal seek (running)');
	expect(solves).toEqual([]);
	const header = page.locator('[data-solve-button]');
	await expect(header).toHaveAttribute('aria-disabled', 'true');
	await expect(header).toHaveAccessibleDescription('A goal seek is running; Cancel stops it.');
	const stopped = aborted(page);
	await page.getByRole('button', { name: 'Cancel goal seek' }).click();
	await stopped;
	await page.unroute(`**${PATH}`);
	await expect(solveNow).not.toHaveAttribute('aria-disabled', 'true');
});

test("the trace's entry: Use in goal seek preselects the connection", async ({
	page
}, testInfo) => {
	await openExample(page);
	await showPane(page, 'Results');
	await page.getByRole('button', { name: 'Solve', exact: true }).click();
	await expect(resultsPane(page).getByRole('status')).toHaveText('Last solve: converged');
	const links = await resultsView(page, 'Links');
	await links.getByRole('button', { name: new RegExp(`^${LINK}`) }).click();
	const trace = traceOf(page, LINK);
	await trace.getByRole('button', { name: `Use a result of ${LINK} in goal seek` }).click();
	const d = dialog(page);
	await expect(d).toBeVisible();
	if (testInfo.project.name === 'mobile') {
		// The trace is a sheet on phones: it closed first, so modals are never stacked.
		await expect(page.getByRole('dialog', { name: LINK })).toHaveCount(0);
	}
	const form = d.getByRole('group', { name: 'New goal' });
	await expect(form.getByRole('combobox', { name: 'Element' })).toHaveValue(/L2$/);
	await expect(form.getByRole('radio').first()).toBeFocused();
	await form.getByRole('radio', { name: 'Flow', exact: true }).check();
	await form.getByRole('button', { name: 'Add goal' }).click();
	await expect(
		d
			.getByRole('group', { name: new RegExp(`${LINK} · Flow$`) })
			.getByRole('textbox', { name: /^Target/ })
	).toBeFocused();
	await closeButton(page).click();
	await expect(d).toBeHidden();
	if (testInfo.project.name === 'mobile') await expect(goalSeekButton(page)).toBeFocused();
	else
		await expect(
			trace.getByRole('button', { name: `Use a result of ${LINK} in goal seek` })
		).toBeFocused();
});

test('layout: no sideways scroll with a result shown; Run and Close in view; focus to the result', async ({
	page
}) => {
	await openExample(page);
	await speedForFlow(page, '15');
	await runButton(page).focus();
	await run(page);
	const d = dialog(page);
	await expect(d.getByText('Goal met', { exact: true })).toBeVisible();
	await expect(d.getByRole('heading', { name: 'Result', exact: true })).toBeFocused();
	await expect(d.getByRole('heading', { name: 'Result', exact: true })).toBeInViewport();
	// The sheet itself never scrolls: its title bar stays at its top. (Absolutely positioned
	// sr-only captions once made the overflow-hidden dialog scrollable below 1024 px, and the
	// focus move scrolled the title bar out of the sheet.)
	const geometry = await d.evaluate((element) => {
		const title = element.querySelector('h2')!.getBoundingClientRect();
		const sheet = element.getBoundingClientRect();
		return { scrollTop: element.scrollTop, titleTop: title.top, top: sheet.top };
	});
	expect(geometry.scrollTop).toBe(0);
	expect(geometry.titleTop).toBeGreaterThanOrEqual(geometry.top);
	expect(await sidewaysScroll(page)).toBe(0);
	await expect(runButton(page)).toBeInViewport();
	await expect(closeButton(page)).toBeInViewport();
	const box = await d.boundingBox();
	const viewport = page.viewportSize()!;
	expect(box!.x).toBeGreaterThanOrEqual(0);
	expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 0.5);
});
