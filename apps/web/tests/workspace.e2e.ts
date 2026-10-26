import { expect, test, type Page } from '@playwright/test';
import type { FluidPropertiesResponse } from '../src/lib/api/types';
import { EXAMPLES } from '../src/lib/utils/examples';
import { showPane, sig4 } from './support';

/** Open the pump transfer example from the home page. */
async function openExample(page: Page) {
	await page.goto('/');
	await page.getByRole('link', { name: /Pump transfer/ }).click();
	await expect(page.getByRole('textbox', { name: 'Project name' })).toHaveValue(
		'Pump transfer between two tanks'
	);
}

const focusedText = (page: Page) =>
	page.evaluate(() => {
		const el = document.activeElement;
		return el ? `${el.tagName} ${el.getAttribute('aria-label') ?? el.textContent?.trim()}` : '';
	});

test('an edit made just before leaving by an in-app link is in the link Back returns to', async ({
	page
}) => {
	await openExample(page);
	const name = page.getByRole('textbox', { name: 'Project name' });
	await name.fill('Edited just before leaving');
	await name.press('Enter');
	// Within the URL debounce, leave by the header's Home link.
	await page.getByRole('link', { name: 'OpenSolve Pipe home' }).click();
	await expect(page.getByRole('heading', { level: 1, name: 'OpenSolve Pipe' })).toBeVisible();
	await page.goBack();
	await expect(page.getByRole('textbox', { name: 'Project name' })).toHaveValue(
		'Edited just before leaving'
	);
});

test('the fluid settings get the calculated properties with the fluid in the request body', async ({
	page
}) => {
	const urls: string[] = [];
	page.on('request', (r) => urls.push(r.url()));
	await openExample(page);
	const answer = page.waitForResponse((r) => r.url().endsWith('/api/v1/fluids/properties'));
	await page.getByRole('button', { name: 'Settings' }).click();
	const response = await answer;
	expect(response.request().method()).toBe('POST');
	expect(response.status()).toBe(200);
	// The project's built-in fluid at its state (no overrides in the example).
	const fluid = EXAMPLES[0]!.create().fluid;
	expect(fluid.kind).toBe('builtin');
	if (fluid.kind !== 'builtin') return;
	expect(response.request().postDataJSON()).toEqual({
		kind: 'builtin',
		fluidId: fluid.fluidId,
		temperature: fluid.temperature
	});
	const { properties } = (await response.json()) as FluidPropertiesResponse;
	const dialog = page.getByRole('dialog', { name: 'Project settings' });
	await expect(dialog.getByText('Calculated properties', { exact: true })).toBeVisible();
	await expect(dialog.getByText(`${sig4(properties.density)} kg/m³`)).toBeVisible();
	// No request put anything in its address: no query strings (GOALS §4.5).
	expect(urls.filter((u) => u.includes('?'))).toEqual([]);
});

test('the workspace fits 320 px without scrolling sideways', async ({ page }, testInfo) => {
	test.skip(testInfo.project.name !== 'mobile', 'narrow-screen check');
	await page.setViewportSize({ width: 320, height: 640 });
	await openExample(page);
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBe(0);
	const settings = await page.getByRole('button', { name: 'Settings' }).boundingBox();
	expect(settings).not.toBeNull();
	expect((settings?.x ?? 0) + (settings?.width ?? 0)).toBeLessThanOrEqual(320);
});

test('on a phone in landscape the header is one row', async ({ page }, testInfo) => {
	test.skip(testInfo.project.name !== 'mobile', 'landscape phone check');
	await page.setViewportSize({ width: 844, height: 390 });
	await openExample(page);
	const name = await page.getByRole('textbox', { name: 'Project name' }).boundingBox();
	const solve = await page.getByRole('button', { name: 'Solve', exact: true }).boundingBox();
	// Name and toolbar side by side: their vertical centres line up.
	expect(
		Math.abs(
			(name?.y ?? 0) + (name?.height ?? 0) / 2 - ((solve?.y ?? 0) + (solve?.height ?? 0) / 2)
		)
	).toBeLessThan(4);
	const header = await page.getByRole('banner').boundingBox();
	expect(header?.height ?? 999).toBeLessThan(60);
});

test('keyboard focus stays on Solve and on Undo when they become unavailable', async ({ page }) => {
	await openExample(page);
	const solve = page.getByRole('button', { name: 'Solve', exact: true });
	await solve.focus();
	await page.keyboard.press('Enter');
	await expect.poll(() => focusedText(page)).toMatch(/^BUTTON Solv/);

	const name = page.getByRole('textbox', { name: 'Project name' });
	await name.fill('Renamed');
	await name.press('Enter');
	const undo = page.getByRole('button', { name: /^Undo/ });
	await undo.focus();
	await page.keyboard.press('Enter');
	await expect(name).toHaveValue('Pump transfer between two tanks');
	expect(await focusedText(page)).toMatch(/^BUTTON Undo/);
});

test('Escape in an edited number field of a dialog reverts the field, not the dialog', async ({
	page
}) => {
	await openExample(page);
	await page.getByRole('button', { name: 'Settings' }).click();
	const dialog = page.getByRole('dialog', { name: 'Project settings' });
	await expect(dialog).toBeVisible();
	const elevation = dialog.getByRole('textbox', { name: /^Site elevation/ });
	const before = await elevation.inputValue();
	await elevation.fill('123');
	await elevation.press('Escape');
	await expect(elevation).toHaveValue(before);
	await expect(dialog).toBeVisible();
	// A second Escape (nothing left to revert) closes the dialog.
	await elevation.press('Escape');
	await expect(dialog).toBeHidden();
});

test('Ctrl+Enter solves, and the results start in the upper part of the pane', async ({ page }) => {
	await openExample(page);
	await showPane(page, 'Results');
	// The description is the pane's context until there are results.
	const about = page
		.getByRole('region', { name: 'Results', exact: true })
		.getByRole('button', { name: 'About this project' });
	await expect(about).toHaveAttribute('aria-expanded', 'true');
	await page.keyboard.press('Control+Enter');
	const results = page.getByRole('region', { name: 'Results', exact: true });
	await expect(results.getByRole('heading', { name: 'Converged' })).toBeVisible();
	await expect(about).toHaveAttribute('aria-expanded', 'false');
	await results.getByRole('tab', { name: 'Links', exact: true }).click();
	// One line of description, one line of status and one row of views above the table: its
	// first row starts within the upper 55 % of the screen (63 % on desktop and 73 % on a phone
	// before, docs/proposals/ui-ux-refinement.md F1).
	const row = await results.locator('tbody tr:visible').first().boundingBox();
	const height = page.viewportSize()?.height ?? 0;
	expect(row?.y ?? height).toBeLessThan(0.55 * height);
	expect(
		await page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		)
	).toBe(0);
});

test('an empty project offers no Scenarios or Goal seek until it has a component', async ({
	page
}) => {
	await page.goto('/');
	await page.getByRole('link', { name: 'New project' }).click();
	await expect(page.getByRole('heading', { name: 'Start the network' })).toBeVisible();
	await expect(page.getByRole('button', { name: /^Scenarios/ })).toHaveCount(0);
	await expect(page.getByRole('button', { name: /^Goal seek/ })).toHaveCount(0);
	await page.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(page.getByRole('button', { name: /^Scenarios/ })).toBeVisible();
});

test('from 1024 px the header names the fluid, and opens its settings', async ({
	page
}, testInfo) => {
	test.skip(testInfo.project.name !== 'desktop', 'wide-screen check');
	await openExample(page);
	await page.getByRole('button', { name: 'Fluid: Water · 20 °C' }).click();
	const dialog = page.getByRole('dialog', { name: 'Project settings' });
	await expect(dialog.getByRole('combobox', { name: 'Fluid' })).toBeFocused();
});
