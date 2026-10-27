import { expect, test } from '@playwright/test';
import { cellText, resultsView, solveConverged } from './support';

/**
 * The pump chart's panels (proposal pump-chart.md §4), against the real app and API, on desktop
 * and on a phone: the pump example's efficiency, shaft-power and NPSH panels from the API's
 * curves, NPSHa along the computed system curve, the readout at the duty agreeing with the Pumps
 * table, a chip hiding a panel (remembered after a reload), and no sideways scrolling.
 */

test('draws the efficiency, power and NPSH panels and reads them at the duty', async ({ page }) => {
	await page.goto('/');
	await page.getByRole('link', { name: /Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await solveConverged(page);
	const pumps = await resultsView(page, 'Pumps');
	const figure = pumps.getByRole('figure').first();
	await expect(figure.getByText(/System curve: the network/)).toBeVisible({ timeout: 30_000 });

	const chart = figure.getByRole('img');
	await expect(chart).toHaveAccessibleName(
		/below, on the same flow axis: efficiency, shaft power, npsh/
	);
	const panels = figure.getByRole('group', { name: 'Show' });
	for (const name of ['Efficiency', 'Shaft power', 'NPSH'])
		await expect(panels.getByRole('button', { name })).toHaveAttribute('aria-pressed', 'true');

	// At the duty, the efficiency read from the chart is the table's (the duty is a sample's
	// neighbour, so the drawn line agrees to the table's four figures within a few units).
	const readout = figure.locator('p', { hasText: 'At the duty' });
	await expect(readout).toContainText('Efficiency');
	await expect(readout).toContainText('NPSHa');
	const table = pumps.getByRole('table').first();
	const efficiency = Number(
		(await cellText(table, 'Transfer pump', 'Efficiency %')).replace(/[^\d.]/g, '')
	);
	const read = Number(/Efficiency ([\d.]+) %/.exec(await readout.innerText())![1]);
	expect(Math.abs(read - efficiency)).toBeLessThan(0.05 * efficiency);

	// The slider reads elsewhere; Escape returns to the duty.
	const slider = figure.getByRole('slider', { name: 'Read at flow' });
	await slider.focus();
	await page.keyboard.press('Home');
	await expect(figure.locator('p', { hasText: /^At 0 / })).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(readout).toBeVisible();

	// Hiding a panel is remembered in this browser.
	await panels.getByRole('button', { name: 'Shaft power' }).click();
	await expect(chart).toHaveAccessibleName(/below, on the same flow axis: efficiency, npsh/);
	await figure.getByRole('button', { name: 'Show data table' }).click();
	await expect(
		figure.getByRole('table', { name: /Efficiency curve at 100 % speed/ })
	).toBeVisible();
	await expect(figure.getByRole('table', { name: /Shaft power curve/ })).toHaveCount(0);
	await expect(figure.getByRole('columnheader', { name: /NPSHa/ })).toBeVisible();
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
		true
	);
	await page.reload();
	await solveConverged(page);
	const again = await resultsView(page, 'Pumps');
	await expect(
		again.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Shaft power' })
	).toHaveAttribute('aria-pressed', 'false', { timeout: 30_000 });
});
