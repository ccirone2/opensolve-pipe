import { expect, test, type Locator } from '@playwright/test';
import { exampleProject } from '../src/lib/utils/examples';
import { resultsPane, resultsView, showPane, sig4, solveConverged } from './support';

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

/** `text` as a regular expression that matches it literally. */
const literal = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** A results-table row header's accessible name: the element's name, then "Pump · P1". */
const rowHeader = (name: string, id: string) =>
	new RegExp(`^${literal(name)}\\s*Pump · ${literal(id)}$`);

/**
 * The NPSH margin ratio in the margin's place (the owner, 2026-11-12, nit 4: "add NPSH margin as a
 * ratio and make it a default in the results table. Don't make absolute margin a default."; Q3,
 * "Ratio everywhere"; docs/proposals/pumps-nits.md item 4), in the condenser water example, whose
 * six pumps each have an NPSHr curve and water's vapor pressure: Results per pump shows each pump's
 * ratio by default and not its margin; the Summary gives each pump's ratio in its line and the
 * smallest as its extreme, whose link sorts Results per pump by the ratio, that pump first. Every
 * ratio is the API's (PumpResult.npshMarginRatio, NPSHa ÷ NPSHr), shown to 4 significant figures
 * with no unit.
 */
test('the NPSH margin ratio: Results per pump shows it by default, the Summary gives each pump’s and the smallest, whose link sorts Results per pump by it (pumps-nits.md item 4)', async ({
	page
}) => {
	await page.goto('/');
	await page.getByRole('link', { name: /^Chiller plant/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	const solved = await solveConverged(page);
	const project = exampleProject('condenser-water')!;
	const nameOf = (id: string) => project.components.find((c) => c.id === id)!.name;
	const ratios = Object.entries(solved.pumpResults).map(([id, r]) => ({
		id,
		name: nameOf(id),
		ratio: r.npshMarginRatio!
	}));
	expect(ratios.length).toBeGreaterThan(1);
	for (const { id, ratio } of ratios) {
		expect(ratio, `${id}'s ratio`).toEqual(expect.any(Number));
		// The API's ratio, NPSHa ÷ NPSHr from the same solve.
		const r = solved.pumpResults[id]!;
		expect(sig4(ratio), `${id}'s ratio`).toBe(sig4(r.npshAvailable! / r.npshRequired!));
	}
	await showPane(page, 'Results');

	// Results per pump: the ratio, shown by default, each pump's; the absolute margin hidden.
	const pumpsView = await resultsView(page, 'Pumps');
	const table = pumpsView.getByRole('table', { name: 'Results per pump' });
	await expect(table.getByRole('columnheader', { name: 'NPSH margin ratio' })).toHaveCount(1);
	await expect(table.getByRole('columnheader', { name: /^NPSH margin(?! ratio)/ })).toHaveCount(0);
	const ratioCells = table.locator('td[data-label="NPSH margin ratio"]');
	await expect(ratioCells).toHaveCount(ratios.length);
	for (const { id, name, ratio } of ratios) {
		// The row's header: the pump's name, then its kind and id ("Pump · P1").
		const row = table
			.getByRole('row')
			.filter({ has: page.getByRole('rowheader', { name: rowHeader(name, id) }) });
		await expect(row).toHaveCount(1);
		await expect(row.locator('td[data-label="NPSH margin ratio"]')).toHaveText(sig4(ratio));
	}

	// The Summary: each pump's line ends in its ratio, never its margin.
	const summary = await resultsView(page, 'Summary');
	const lines = summary.getByRole('region', { name: 'Pumps' }).getByRole('listitem');
	await expect(lines).toHaveCount(ratios.length);
	for (const { name, ratio } of ratios) {
		const line = lines.filter({ has: page.getByRole('button', { name, exact: true }) });
		await expect(line).toHaveCount(1);
		const text = squash(await line.innerText());
		expect(text, name).toMatch(new RegExp(` · NPSH margin ratio ${literal(sig4(ratio))}$`));
		expect(text, name).not.toMatch(/NPSH margin -?\d/);
	}
	// Its extreme: the smallest ratio and its pump; the margin's extreme gone.
	const smallest = ratios.reduce((a, b) => (b.ratio < a.ratio ? b : a));
	const extremes = summary.getByRole('region', { name: 'Extremes' });
	await expect(
		extremes.getByRole('term').filter({ hasText: /^Smallest NPSH margin ratio$/ })
	).toHaveCount(1);
	await expect(
		extremes.getByRole('term').filter({ hasText: /^Smallest NPSH margin$/ })
	).toHaveCount(0);
	const extreme = extremes.locator('div', { hasText: 'Smallest NPSH margin ratio' });
	await expect(extreme.locator('dd .tabular-nums')).toHaveText(sig4(smallest.ratio));
	await expect(extreme.getByRole('button', { name: smallest.name, exact: true })).toHaveCount(1);

	// Its link: Results per pump sorted by the ratio, smallest first, its pump the first row, the
	// absolute margin still hidden.
	await extreme.getByRole('button', { name: 'Pumps, smallest first' }).click();
	const pumps = resultsPane(page).getByRole('tabpanel', { name: 'Pumps', exact: true });
	const sorted = pumps.getByRole('table', { name: 'Results per pump' });
	await expect(sorted.getByRole('columnheader', { name: /^NPSH margin ratio/ })).toHaveAttribute(
		'aria-sort',
		'ascending'
	);
	await expect(sorted.getByRole('columnheader', { name: /^NPSH margin(?! ratio)/ })).toHaveCount(0);
	expect(await firstRowName(sorted)).toBe(`${smallest.name} Pump · ${smallest.id}`);
	expect(
		(await sorted.locator('td[data-label="NPSH margin ratio"]').allInnerTexts()).map(squash)
	).toEqual([...ratios].sort((a, b) => a.ratio - b.ratio).map((r) => sig4(r.ratio)));
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
