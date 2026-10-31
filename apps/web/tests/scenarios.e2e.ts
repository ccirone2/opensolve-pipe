import { expect, test, type Locator, type Page, type Request, type Route } from '@playwright/test';
import type { SolveRequest } from '../src/lib/api/types';
import {
	buildPane,
	caseGroup,
	caseMenu,
	chooseCase,
	currentHeading,
	openCases,
	openScenarioManager,
	resultsPane,
	resultsView,
	setNumber,
	showPane
} from './support';

/**
 * The scenario manager (PRD §3.8, proposal scenario-manager.md §7.5) against the real app and API,
 * on desktop and on a phone: create a scenario and change a value in it (Changed, the base value,
 * Reset); locked values; solve one case and all of them; the comparison; the other cases on the
 * pump chart; share and reopen; cancel Solve all and resume it; a deleted component's changes no
 * longer apply and undo restores them, switching case.
 *
 * Network: the home page's pump-transfer example (illustrative, made-up inputs). The scenario
 * values entered below (a 6 m discharge-tank level, a 90 % pump speed, a closed valve) are
 * made-up test inputs.
 */

async function openExample(page: Page) {
	await page.goto('/');
	await page.getByRole('link', { name: /^Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(currentHeading(page)).toHaveText('Suction tank');
}

const scenariosButton = (page: Page) => page.getByRole('button', { name: /^Scenarios/ });
const solveAllButton = (page: Page) =>
	caseGroup(page).getByRole('button', { name: 'Solve all', includeHidden: true });
/** Press Solve all, in the Scenarios menu. */
async function solveAll(page: Page): Promise<void> {
	await (await openCases(page)).getByRole('button', { name: 'Solve all' }).click();
}

/** Create a scenario in the manager, name it, and close the manager: it is the case shown. */
async function newScenario(page: Page, name: string): Promise<void> {
	const manager = await openScenarioManager(page);
	await manager.getByRole('button', { name: 'New scenario' }).click();
	const field = manager.getByRole('textbox', { name: /^Name of scenario S\d+$/ }).last();
	await expect(field).toBeFocused();
	await field.fill(name);
	await field.press('Enter');
	await manager.getByRole('button', { name: 'Done' }).click();
	await expect(manager).toBeHidden();
	await expect(caseMenu(page).locator('option:checked')).toHaveText(new RegExp(`^${name} \\(`));
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

/** The solve requests the page sends, as sent. */
function solveRequests(page: Page): SolveRequest[] {
	const sent: SolveRequest[] = [];
	page.on('request', (r: Request) => {
		if (r.url().endsWith('/api/v1/solve') && r.method() === 'POST') {
			sent.push(r.postDataJSON() as SolveRequest);
		}
	});
	return sent;
}

const resultsStatus = (page: Page) =>
	resultsPane(page)
		.getByRole('status')
		.filter({ hasText: /solve|Solving/i })
		.first();

test('create a scenario, change a value in it, reset it; locked values; back to the base case', async ({
	page
}) => {
	await openExample(page);
	// A project without scenarios shows no case bar.
	await expect(page.getByRole('group', { name: 'Case' })).toHaveCount(0);
	await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios');

	await newScenario(page, 'Pump off');
	await expect(scenariosButton(page)).toHaveAccessibleName('Scenarios (1)');
	const panel = await showComponent(page, 'Transfer pump');
	await expect(panel.getByRole('note', { name: 'Scenario' })).toContainText('Scenario: Pump off.');
	// Topology actions are hidden in a scenario.
	await expect(panel.getByRole('button', { name: 'Add after' })).toHaveCount(0);

	// A two-value status is a pair of segments (proposal build-density.md §11).
	const status = panel.getByRole('radiogroup', { name: 'Status' });
	const on = status.getByRole('radio', { name: 'On' });
	const off = status.getByRole('radio', { name: 'Off' });
	await off.click();
	await expect(status).toHaveAccessibleDescription(/Changed in this scenario\. Base value On\./);
	const reset = panel.getByRole('button', { name: 'Reset Status to the base value, On' });
	await expect(reset).toBeVisible();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Pump off (1 change)');
	await reset.click();
	await expect(on).toBeChecked();
	await expect(reset).toHaveCount(0);
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Pump off (0 changes)');
	await off.click();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Pump off (1 change)');

	// A value that is the same in every scenario: read-only, focusable, said so.
	const elevation = panel.getByRole('textbox', { name: /^Elevation/ });
	await expect(elevation).toHaveAttribute('readonly', '');
	await elevation.focus();
	await expect(elevation).toBeFocused();
	await expect(elevation).toHaveAccessibleDescription(/Same in every scenario\./);
	const control = panel.getByRole('textbox', { name: 'Control' });
	await expect(control).toHaveValue('Fixed speed');
	await expect(control).toHaveAttribute('readonly', '');

	// Back to the base case: its own values, editable, and which scenario sets its own value.
	await panel.getByRole('button', { name: 'Switch to base case' }).click();
	await expect(caseMenu(page)).toHaveValue('');
	await expect(panel.getByRole('note', { name: 'Scenario' })).toHaveCount(0);
	await expect(on).toBeChecked();
	await expect(status).toHaveAccessibleDescription(/Pump off sets its own value\./);
	await expect(elevation).not.toHaveAttribute('readonly', '');
	await expect(panel.getByRole('button', { name: 'Add after' })).toBeVisible();
});

test('solve one case and all of them, read the comparison and the other cases on the chart', async ({
	page
}) => {
	const sent = solveRequests(page);
	await openExample(page);
	await newScenario(page, 'Higher tank');
	let panel = await showComponent(page, 'Discharge tank');
	await setNumber(panel, /^Liquid level/, '6');
	await newScenario(page, 'Slower pump');
	panel = await showComponent(page, 'Transfer pump');
	await setNumber(panel, /^Speed/, '90');

	// Solve the case shown: its request carries its id, in the body.
	const solveButton = page.getByRole('banner').getByRole('button', { name: 'Solve Slower pump' });
	const answered = page.waitForResponse((r) => r.url().endsWith('/api/v1/solve'));
	await solveButton.click();
	expect((await answered).status()).toBe(200);
	expect(sent.map((r) => r.scenarioId)).toEqual(['S2']);
	await showPane(page, 'Results');
	await expect(resultsStatus(page)).toHaveText('Last solve of Slower pump: converged');
	const card = resultsPane(page).getByRole('region', { name: /^Scenario: Slower pump/ });
	await expect(card).toContainText('Transfer pump · Speed: 90 % (base: 100 %)');

	// Solve all: the cases still missing (the base, then Higher tank), one after the other. The
	// base request is the plain one, without a scenario id.
	await solveAll(page);
	await expect(solveAllButton(page)).toHaveAttribute('aria-disabled', 'true');
	await expect(caseGroup(page)).not.toContainText('Solving');
	expect(sent).toHaveLength(3);
	expect('scenarioId' in sent[1]!).toBe(false);
	expect(sent[2]!.scenarioId).toBe('S1');
	// Every request carries the whole project, its scenarios included.
	expect(sent.every((r) => r.project.scenarios?.length === 2)).toBe(true);

	// The comparison: the base first, then the scenarios, with differences from the base.
	await resultsPane(page).getByRole('tab', { name: 'Compare cases' }).click();
	const compare = resultsPane(page).getByRole('region', { name: 'Compare cases' });
	const wide = page.viewportSize()!.width >= 1024;
	if (wide) {
		const table = compare.getByRole('table', { name: 'Results by case' });
		await expect(table.getByRole('columnheader')).toHaveText([
			'Result',
			/^Base case/,
			/^Higher tank/,
			/^Slower pump/
		]);
		const flow = table.getByRole('row').filter({ hasText: 'Transfer pump · Flow' });
		await expect(flow.getByRole('cell')).toHaveCount(3);
		await expect(flow.getByRole('cell').nth(1)).toContainText(/difference from base\s*−/);
		await expect(flow.getByRole('cell').nth(2)).toContainText(/difference from base\s*−/);
	} else {
		const flow = compare.getByRole('region', { name: /^Transfer pump · Flow/ });
		await expect(flow.getByRole('term')).toHaveText(['Base case', 'Higher tank', 'Slower pump']);
		await expect(flow.getByRole('definition').nth(1)).toContainText(/difference from base\s*−/);
		// Cards on a phone: the page never scrolls sideways.
		expect(
			await page.evaluate(
				() => document.documentElement.scrollWidth - document.documentElement.clientWidth
			)
		).toBe(0);
	}

	// Add a result: the pump's efficiency.
	await compare.getByRole('button', { name: 'Choose results…' }).click();
	const choose = page.getByRole('dialog', { name: 'Choose results to compare' });
	await choose.getByRole('combobox', { name: 'Element' }).selectOption({ label: 'Transfer pump' });
	await choose.getByRole('checkbox', { name: 'Efficiency' }).check();
	await choose.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(choose.getByText('Transfer pump · Efficiency')).toBeVisible();
	await choose.getByRole('button', { name: 'Done' }).click();
	await expect(
		compare.getByRole('button', { name: 'Transfer pump · Efficiency' }).filter({ visible: true })
	).toHaveCount(1);

	// The pump chart of the case shown names it, and lists the other cases' operating points.
	await resultsPane(page).getByRole('tab', { name: 'Slower pump' }).click();
	const pumps = await resultsView(page, 'Pumps');
	const figure = pumps.getByRole('figure', {
		name: 'Pump and system curves: Transfer pump, Slower pump'
	});
	await expect(figure.getByRole('img')).toHaveAccessibleName(
		/other cases' operating points: Base case .* at .*; Higher tank /
	);
	await expect(figure.getByRole('group', { name: 'Cases on the chart' })).toBeVisible();
	await figure.getByRole('button', { name: 'Show data table' }).click();
	const byCase = figure.getByRole('table', { name: 'Operating points by case' });
	await expect(byCase.getByRole('rowheader')).toHaveText([
		'Slower pump (shown)',
		/Base case$/,
		/Higher tank$/
	]);
	// The shown curve is computed for this solve; the other cases' only on request, on its grid,
	// one at a time, with Cancel.
	await expect(figure.getByRole('table', { name: 'System curve' })).toBeVisible();
	const curves: { scenarioId?: string; flowMax?: number }[] = [];
	await page.route('**/api/v1/system-curve', (route) => {
		curves.push(route.request().postDataJSON());
	});
	const overlay = figure.getByRole('checkbox', {
		name: "Also show the other cases' system curves"
	});
	await overlay.check();
	const progress = figure.getByRole('status').filter({ hasText: 'Computing system curves' });
	await expect(progress).toHaveText('Computing system curves: 1 of 2…');
	await expect.poll(() => curves.length).toBe(1);
	expect('scenarioId' in curves[0]!).toBe(false); // the base case's
	expect(curves[0]!.flowMax).toBeGreaterThan(0);
	const aborted = page.waitForEvent('requestfailed', (r) => r.url().endsWith('/system-curve'));
	await figure.getByRole('button', { name: "Cancel the other cases' system curves" }).click();
	await aborted;
	await expect(progress).toHaveCount(0);
	await page.unroute('**/api/v1/system-curve');
	await overlay.uncheck();
	await overlay.check();
	await expect(figure.getByRole('table', { name: 'System curve, Base case' })).toBeVisible();
	await expect(figure.getByRole('table', { name: 'System curve, Higher tank' })).toBeVisible();
});

/** Hold every solve request at the network, unanswered, until the page aborts it. */
async function holdSolves(page: Page): Promise<Route[]> {
	const held: Route[] = [];
	await page.route('**/api/v1/solve', (route) => {
		held.push(route);
	});
	return held;
}

test('cancel Solve all; then Solve all solves only the cases still missing', async ({ page }) => {
	const sent = solveRequests(page);
	await openExample(page);
	await newScenario(page, 'Higher tank');
	const panel = await showComponent(page, 'Discharge tank');
	await setNumber(panel, /^Liquid level/, '6');
	await newScenario(page, 'Copy of base');

	// The base case first, on its own.
	await chooseCase(page, 'Base case');
	const first = page.waitForResponse((r) => r.url().endsWith('/api/v1/solve'));
	await page.getByRole('banner').getByRole('button', { name: 'Solve Base case' }).click();
	await first;
	await showPane(page, 'Results');
	await expect(resultsStatus(page)).toHaveText('Last solve of Base case: converged');

	// Solve all, held at the network: it starts with the first scenario (the base is current).
	const held = await holdSolves(page);
	await solveAll(page);
	await expect.poll(() => held.length).toBe(1);
	expect(held[0]!.request().postDataJSON().scenarioId).toBe('S1');
	const bar = caseGroup(page);
	await expect(bar.getByRole('status', { includeHidden: true })).toHaveText(
		'Solving 1 of 2: Higher tank…'
	);
	const aborted = page.waitForEvent('requestfailed', (r) => r.url().endsWith('/api/v1/solve'));
	await page.getByRole('button', { name: 'Cancel solving all cases' }).click();
	await aborted;
	await expect(bar.getByRole('status', { includeHidden: true })).toHaveText(
		/^Solve all was cancelled/
	);
	await expect(
		page.getByRole('banner').getByRole('button', { name: /^Solve Base case$/ })
	).toBeFocused();
	// The base keeps its results.
	await expect(resultsStatus(page)).toHaveText('Last solve of Base case: converged');

	// Solve all again: the two scenarios, not the base.
	await page.unroute('**/api/v1/solve');
	const before = sent.length;
	await solveAll(page);
	// Solve all stays in place, unavailable, during the run: wait for the run's end.
	await expect(caseGroup(page)).not.toContainText('Solving');
	await expect(solveAllButton(page)).toHaveAttribute('aria-disabled', 'true');
	expect(sent.slice(before).map((r) => r.scenarioId)).toEqual(['S1', 'S2']);
	await chooseCase(page, 'Higher tank (1 change)');
	await expect(resultsStatus(page)).toHaveText('Last solve of Higher tank: converged');
});

test('share and reopen: the scenarios are in the link, which opens on the base case', async ({
	page,
	context
}) => {
	await openExample(page);
	await newScenario(page, 'Higher tank');
	const panel = await showComponent(page, 'Discharge tank');
	await setNumber(panel, /^Liquid level/, '6');

	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share this project' });
	await expect(dialog).toContainText(
		'This link holds the base case and its scenario. It opens on the base case.'
	);
	await expect(dialog).toContainText('You are looking at «Higher tank»');
	const link = await dialog
		.getByRole('textbox', { name: 'Link to this version of the project' })
		.inputValue();
	const fragment = new URL(link).hash;

	const other = await context.newPage();
	await other.goto(`/p${fragment}`);
	await expect(currentHeading(other)).toHaveText('Suction tank');
	await expect(caseMenu(other)).toHaveValue('');
	await expect(scenariosButton(other)).toHaveAccessibleName('Scenarios (1)');
	await chooseCase(other, 'Higher tank (1 change)');
	const reopened = await showComponent(other, 'Discharge tank');
	const level = reopened.getByRole('textbox', { name: /^Liquid level/ });
	await expect(level).toHaveValue('6');
	await expect(level).toHaveAccessibleDescription(/Changed in this scenario\. Base value 2 m\./);
});

test('a deleted component’s changes no longer apply; undo restores them and switches case', async ({
	page
}) => {
	await openExample(page);
	await newScenario(page, 'Valve closed');
	let panel = await showComponent(page, 'Discharge isolation valve');
	await panel
		.getByRole('radiogroup', { name: 'Status' })
		.getByRole('radio', { name: 'Closed (isolated)' })
		.click();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Valve closed (1 change)');

	// Delete the valve in the base case: its change is kept and no longer applies.
	await panel.getByRole('button', { name: 'Switch to base case' }).click();
	panel = await showComponent(page, 'Discharge isolation valve');
	await panel.getByRole('button', { name: 'Delete' }).click();
	const confirm = page.getByRole('dialog', { name: 'Delete Discharge isolation valve?' });
	await expect(confirm).toContainText(
		'1 scenario change refers to it (Valve closed). They are kept but no longer apply'
	);
	await confirm.getByRole('button', { name: 'Delete' }).click();
	await expect(caseMenu(page).locator('option', { hasText: 'Valve closed' })).toHaveText(
		'Valve closed (1 change, 1 no longer applies)'
	);
	const manager = await openScenarioManager(page);
	await manager.getByText('Valve closed', { exact: true }).click();
	await expect(manager.getByRole('heading', { name: 'No longer applies (1)' })).toBeVisible();
	await manager.getByRole('button', { name: 'Done' }).click();

	// Undo the deletion: the change applies again (the base case stays shown).
	await page.getByRole('button', { name: /^Undo delete/ }).click();
	await expect(caseMenu(page).locator('option', { hasText: 'Valve closed' })).toHaveText(
		'Valve closed (1 change)'
	);
	await expect(caseMenu(page)).toHaveValue('');
	// Undo again, from the base case: the change made in Valve closed is undone there, and shown.
	await page.getByRole('button', { name: /^Undo change valve status in Valve closed/ }).click();
	await expect(caseMenu(page)).toHaveValue('S1');
	await expect(
		page.getByRole('status').filter({ hasText: 'Now showing scenario Valve closed' })
	).toBeVisible();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Valve closed (0 changes)');
});

test('a scenario value a base edit made invalid: reported, rejected by the server, reset to base', async ({
	page
}) => {
	await openExample(page);
	// The base pump gets flow control (a made-up setpoint and minimum speed).
	let panel = await showComponent(page, 'Transfer pump');
	await panel.getByRole('combobox', { name: 'Control' }).selectOption('flow');
	await setNumber(panel, /^Flow setpoint/, '15');
	await setNumber(panel, /^Minimum speed/, '50');
	await expect(panel.getByRole('textbox', { name: /^Maximum speed/ })).toBeVisible();
	await newScenario(page, 'Slow drive');
	panel = await showComponent(page, 'Transfer pump');
	await setNumber(panel, /^Maximum speed/, '80');
	// In the base case the minimum speed goes up to 85 %: valid there, not in Slow drive.
	await chooseCase(page, 'Base case');
	await setNumber(panel, /^Minimum speed/, '85');
	await chooseCase(page, 'Slow drive (1 change)');

	const manager = await openScenarioManager(page);
	await expect(manager.getByRole('heading', { name: 'Problems (1)' })).toBeVisible();
	await expect(manager).toContainText(
		'The value Slow drive sets for Transfer pump maximum speed is not valid'
	);
	await manager.getByRole('button', { name: 'Done' }).click();

	const answered = page.waitForResponse((r) => r.url().endsWith('/api/v1/solve'));
	await page.getByRole('banner').getByRole('button', { name: 'Solve Slow drive' }).click();
	expect((await answered).status()).toBe(400);
	await showPane(page, 'Results');
	const error = resultsPane(page).getByRole('region', {
		name: 'The calculation server rejected the project'
	});
	await expect(error).toContainText(
		'The value Slow drive sets for Transfer pump maximum speed is not valid'
	);
	await error.getByRole('button', { name: 'Reset to base' }).click();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Slow drive (0 changes)');
	await page.getByRole('banner').getByRole('button', { name: 'Solve Slow drive' }).click();
	await expect(resultsStatus(page)).toHaveText('Last solve of Slow drive: converged');
});

test('a long case name fits: Solve, the Case menu and the case bar during Solve all', async ({
	page
}) => {
	const name = 'A rather long scenario name for the winter peak case of the cooling water plant';
	await openExample(page);
	await newScenario(page, name);

	// The Solve of a case without results says the case before it, not on the button.
	await showPane(page, 'Results');
	const pane = (await resultsPane(page).boundingBox())!;
	const solve = resultsPane(page).getByRole('button', { name: `Solve ${name}` });
	await expect(solve).toBeVisible();
	const box = (await solve.boundingBox())!;
	expect(box.x + box.width).toBeLessThanOrEqual(pane.x + pane.width);

	// Solve all's progress has a line of its own in the case bar: a short one never squeezes the
	// Case menu, a long one never squeezes the sentence on where edits go.
	await chooseCase(page, 'Base case');
	await openCases(page);
	const bar = caseGroup(page);
	const sentence = bar.getByText(
		'Edits change the base case and every scenario that does not set its own value.'
	);
	const menu = (await caseMenu(page).boundingBox())!.width;
	const lines = (await sentence.isVisible()) ? (await sentence.boundingBox())!.height : 0;
	await holdSolves(page);
	await solveAll(page);
	await expect(bar.getByRole('status', { includeHidden: true })).toHaveText(
		'Solving 1 of 2: Base case…'
	);
	expect((await caseMenu(page).boundingBox())!.width).toBeGreaterThanOrEqual(menu - 1);
	await page.getByRole('button', { name: 'Cancel solving all cases' }).click();
	await expect(bar.getByRole('status', { includeHidden: true })).toHaveText(
		/^Solve all was cancelled/
	);

	await page.unroute('**/api/v1/solve');
	const first = page.waitForResponse((r) => r.url().endsWith('/api/v1/solve'));
	await page.getByRole('banner').getByRole('button', { name: 'Solve Base case' }).click();
	await first;
	await holdSolves(page);
	await solveAll(page);
	await expect(bar.getByRole('status', { includeHidden: true })).toHaveText(
		`Solving 1 of 1: ${name}…`
	);
	if (lines) expect((await sentence.boundingBox())!.height).toBeLessThanOrEqual(lines + 1);
	// The page never scrolls sideways.
	expect(
		await page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		)
	).toBe(0);
	await page.getByRole('button', { name: 'Cancel solving all cases' }).click();
	await expect(bar.getByRole('status', { includeHidden: true })).toHaveText(
		/^Solve all was cancelled/
	);
});
