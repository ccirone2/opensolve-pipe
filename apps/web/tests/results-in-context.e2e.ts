import { expect, test, type Locator, type Page } from '@playwright/test';
import { buildPane, cellText, resultsView, showPane, solveConverged } from './support';

/**
 * Results in context (proposal ui-ux-refinement.md item 6), against the real app and API, on
 * desktop and on a phone: the current element's key results in Build are the values the Results
 * tables show, they are marked out of date after an edit, and a new solve brings them up to date.
 */

/** The value shown in an element's "Last solve" strip for one label, e.g. "Flow (L/s)". */
async function stripValue(strip: Locator, label: string): Promise<string> {
	const item = strip.locator('dl > div').filter({
		has: strip.page().locator('dt', {
			hasText: new RegExp(`^${label.replace(/[()]/g, '\\$&').replace(/ /g, '\\s')}$`)
		})
	});
	await expect(item).toHaveCount(1);
	return (await item.locator('dd').innerText()).trim();
}

const strips = (page: Page) => buildPane(page).getByRole('region', { name: /^Last solve/ });

async function tableValue(page: Page, view: string, row: string, column: string) {
	await showPane(page, 'Results');
	return cellText(await resultsView(page, view), row, column);
}

test('the element shown in Build has its key results, as the tables show them', async ({
	page
}) => {
	await page.goto('/');
	await page.getByRole('link', { name: /Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await solveConverged(page);

	const flow = await tableValue(page, 'Pumps', 'Transfer pump', 'Flow L/s');
	const head = await tableValue(page, 'Pumps', 'Transfer pump', 'Head m');
	const velocity = await tableValue(
		page,
		'Links',
		'Transfer pump → Discharge isolation valve',
		'Velocity m/s'
	);

	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: /^Next/ }).click();
	const pump = strips(page).first();
	expect(await stripValue(pump, 'Flow (L/s)')).toBe(flow);
	expect(await stripValue(pump, 'Head (m)')).toBe(head);
	await expect(pump.getByText('Out of date: solve again')).toHaveCount(0);

	// The discharge connection, in Piping.
	await buildPane(page).getByRole('tab', { name: 'Piping' }).click();
	const connection = strips(page).last();
	expect(await stripValue(connection, 'Velocity (m/s)')).toBe(velocity);
	// Its one pipe's velocity is beside the pipe's size, where it is chosen.
	await expect(buildPane(page).getByRole('combobox', { name: 'Size' })).toHaveAccessibleDescription(
		`Velocity at the last solve: ${velocity} m/s.`
	);

	// An edit marks the values out of date; a solve brings them up to date, as the table.
	await buildPane(page).getByRole('tab', { name: 'Properties' }).click();
	const speed = buildPane(page).getByRole('textbox', { name: /^Speed/ });
	await speed.fill('90');
	await speed.press('Enter');
	await expect(pump.getByText('Out of date: solve again')).toBeVisible();
	await page.keyboard.press('Control+Enter');
	await expect(
		page.getByRole('region', { name: 'Results', exact: true }).getByRole('status')
	).toHaveText('Last solve: converged');
	const slower = await tableValue(page, 'Pumps', 'Transfer pump', 'Flow L/s');
	expect(slower).not.toBe(flow);
	await showPane(page, 'Build');
	await expect(pump.getByText('Out of date: solve again')).toHaveCount(0);
	expect(await stripValue(pump, 'Flow (L/s)')).toBe(slower);

	// Trace opens the element's results and trace (on a phone, from the Results pane).
	await pump.getByRole('button', { name: 'Trace of Transfer pump' }).click();
	await expect(page.getByText('Result values', { exact: true })).toBeVisible();
	expect(
		await page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		)
	).toBe(0);
});
