import { expect, test, type Page } from '@playwright/test';
import { resultsPane, resultsView, solveConverged } from './support';

/**
 * The splitter between Build and Results (proposal ui-ux-refinement.md item 10), against the real
 * app and API: on desktop it drags the Results pane wider, so the solved Links table, which scrolls
 * sideways at the default split, fits, the choice survives a reload and Enter restores the default; on a phone the
 * panes are tabs and there is no splitter.
 */

const splitter = (page: Page) => page.getByRole('separator', { name: 'Resize Build and Results' });

async function resultsWidth(page: Page): Promise<number> {
	return (await resultsPane(page).boundingBox())!.width;
}

test('drags the Results pane wider, remembers it, and Enter restores the default', async ({
	page
}, testInfo) => {
	test.skip(testInfo.project.name !== 'desktop', 'side by side on wide screens only');
	await page.goto('/');
	await page.getByRole('link', { name: /Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await solveConverged(page);
	const links = await resultsView(page, 'Links');
	const table = links.getByRole('table');
	const scrolls = () =>
		table.evaluate((el) => {
			const box = el.parentElement!;
			return box.scrollWidth > box.clientWidth;
		});

	const before = await resultsWidth(page);
	expect(await scrolls()).toBe(true);
	const handle = splitter(page);
	await expect(handle).toHaveAttribute('aria-valuenow', '60');

	// Drag the splitter far left: it stops where Build keeps 22 rem (352 of 1280 px, 28 %).
	const box = (await handle.boundingBox())!;
	const y = box.y + box.height / 2;
	await page.mouse.move(box.x + box.width / 2, y);
	await page.mouse.down();
	await page.mouse.move(400, y, { steps: 5 });
	await page.mouse.move(100, y, { steps: 5 });
	await page.mouse.up();
	await expect(handle).toHaveAttribute('aria-valuenow', '28');
	const after = await resultsWidth(page);
	expect(after).toBeGreaterThan(before + 300);
	expect(await scrolls()).toBe(false);
	// The page itself never scrolls sideways.
	expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
		page.viewportSize()!.width
	);

	// Remembered in this browser.
	await page.reload();
	await expect(splitter(page)).toHaveAttribute('aria-valuenow', '28');
	expect(Math.abs((await resultsWidth(page)) - after)).toBeLessThan(2);

	// The keyboard: one step back, then Enter for the default layout.
	await splitter(page).focus();
	await page.keyboard.press('ArrowRight');
	await expect(splitter(page)).toHaveAttribute('aria-valuenow', '33');
	await page.keyboard.press('Enter');
	await expect(splitter(page)).toHaveAttribute('aria-valuenow', '60');
	expect(Math.abs((await resultsWidth(page)) - before)).toBeLessThan(2);
	expect(await page.evaluate(() => localStorage.getItem('opensolve-pipe:results-share'))).toBe(
		null
	);
});

test('has no splitter on a phone, where Build and Results are tabs', async ({ page }, testInfo) => {
	test.skip(testInfo.project.name !== 'mobile', 'narrow-screen check');
	await page.goto('/');
	await page.getByRole('link', { name: /Pump transfer/ }).click();
	await expect(page.getByRole('tab', { name: 'Build' })).toBeVisible();
	await expect(splitter(page)).toBeHidden();
});
