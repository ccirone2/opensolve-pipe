import { expect, test, type Locator } from '@playwright/test';
import { resultsPane, resultsView, showPane, solveConverged } from './support';

/**
 * The Summary answers first and results tables sort (proposal ui-ux-refinement.md items 8 and 9),
 * against the real app and API, on desktop and on a phone: each extreme's link shows its table
 * sorted on it, with that extreme in the first row, and a column heading sorts the table.
 */

const squash = (text: string) => text.replace(/\s+/g, ' ').trim();

/** The text of a row's first cell (its element's name and detail). */
async function firstRowName(table: Locator): Promise<string> {
	return squash(await table.getByRole('rowheader').first().innerText());
}

test('each extreme links to its table sorted on it, and headings sort', async ({
	page,
	isMobile
}) => {
	await page.goto('/');
	await page.getByRole('link', { name: /Gravity-fed/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await solveConverged(page);
	await showPane(page, 'Results');
	const summary = await resultsView(page, 'Summary');
	const extremes = summary.getByRole('region', { name: 'Extremes' });

	// Lowest static pressure: its place is the first row of Nodes sorted lowest first.
	const lowest = extremes.locator('div', { hasText: 'Lowest static pressure' });
	const lowestPlace = squash(await lowest.getByRole('button').first().innerText());
	await lowest.getByRole('button', { name: 'Nodes, lowest first' }).click();
	const nodes = resultsPane(page).getByRole('tabpanel', { name: 'Nodes' });
	await expect(nodes.getByRole('columnheader', { name: /^Pressure/ })).toHaveAttribute(
		'aria-sort',
		'ascending'
	);
	// "Port 1 of Lower tank B" names the port; the row header names the component, then the port.
	const [port, component] = lowestPlace.split(' of ');
	expect(await firstRowName(nodes)).toBe(`${component} ${port}`);

	// Highest velocity: the first row of Links sorted highest first.
	await resultsView(page, 'Summary');
	const fastest = extremes.locator('div', { hasText: 'Highest velocity' });
	const fastestPlace = squash(await fastest.getByRole('button').first().innerText());
	await fastest.getByRole('button', { name: 'Links, highest first' }).click();
	const links = resultsPane(page).getByRole('tabpanel', { name: 'Links' });
	await expect(links.getByRole('columnheader', { name: /^Velocity/ })).toHaveAttribute(
		'aria-sort',
		'descending'
	);
	expect(await firstRowName(links)).toContain(fastestPlace);

	// A heading sorts: Flow, ascending then descending; the order reverses where values differ.
	// On a phone the table is a list with its headings for screen readers only: "Sort by" and its
	// direction button sort it, the same sort (proposal build-density.md §14).
	const flow = links.getByRole('columnheader', { name: /^Flow/ });
	if (isMobile) {
		await links.getByRole('combobox', { name: 'Sort by' }).selectOption({ label: 'Flow (L/s)' });
	} else {
		await flow.getByRole('button').click();
	}
	await expect(flow).toHaveAttribute('aria-sort', 'ascending');
	const ascending = await firstRowName(links);
	if (isMobile) {
		await links.getByRole('button', { name: 'Ascending: lowest first' }).click();
	} else {
		await flow.getByRole('button').click();
	}
	await expect(flow).toHaveAttribute('aria-sort', 'descending');
	expect(await firstRowName(links)).not.toBe(ascending);
	expect(
		await page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		)
	).toBe(0);
});

test('on a phone, Fields opens as a sheet across the screen; Done closes it', async ({
	page,
	isMobile
}) => {
	test.skip(!isMobile, 'phone layout (proposal build-density.md §16)');
	await page.goto('/');
	await page.getByRole('link', { name: /Gravity-fed/ }).click();
	await solveConverged(page);
	await showPane(page, 'Results');
	const links = await resultsView(page, 'Links');
	const fields = links.getByRole('button', { name: /^Fields/ });
	// Sort, its direction and Fields share one line (proposal build-density.md §18).
	const sortField = links.getByRole('combobox', { name: 'Sort by' });
	await sortField.selectOption({ label: 'Flow (L/s)' });
	const direction = links.getByRole('button', { name: /lowest first|highest first/ });
	const tops = [sortField, direction, fields].map(async (c) => (await c.boundingBox())!.y);
	const [a, b, c] = await Promise.all(tops);
	expect(Math.abs(a! - b!)).toBeLessThan(2);
	expect(Math.abs(a! - c!)).toBeLessThan(2);
	await fields.click();
	const sheet = links.getByRole('group', { name: /^Fields shown in/ });
	await expect(sheet).toBeVisible();
	const box = (await sheet.boundingBox())!;
	const viewport = page.viewportSize()!;
	expect(Math.round(box.width)).toBe(viewport.width);
	expect(Math.round(box.y + box.height)).toBe(viewport.height);
	await sheet.getByRole('checkbox', { name: /^Velocity/ }).uncheck();
	await expect(links.getByRole('columnheader', { name: /^Velocity/ })).toHaveCount(0);
	await sheet.getByRole('button', { name: 'Show all' }).click();
	await sheet.getByRole('button', { name: 'Done' }).click();
	await expect(sheet).toBeHidden();
	await expect(fields).toHaveAttribute('aria-expanded', 'false');
});
