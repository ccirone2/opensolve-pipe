import { expect, test, type Page } from '@playwright/test';

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
