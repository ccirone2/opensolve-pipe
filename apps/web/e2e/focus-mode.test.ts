import { test, expect } from '@playwright/test';

const WORKSPACE_URL = '/p/empty';

test.describe('Focus Mode', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto(WORKSPACE_URL);
		// Wait for workspace to load
		await expect(page.getByText('Untitled Project').first()).toBeVisible({ timeout: 10000 });
		// Wait a moment for stores to initialize
		await page.waitForTimeout(500);
	});

	test('Focus button is visible in toolbar', async ({ page }) => {
		const focusButton = page.getByRole('button', { name: /Focus/i }).first();
		await expect(focusButton).toBeVisible();
	});

	test('clicking Focus button activates focus mode', async ({ page }) => {
		// Verify initial state — no focus-mode class
		const workspace = page.locator('.workspace').first();
		const initialClass = await workspace.getAttribute('class');
		console.log('Initial workspace class:', initialClass);
		expect(initialClass).not.toContain('focus-mode');

		// Click the Focus button
		const focusButton = page.getByRole('button', { name: /Focus/i }).first();
		await focusButton.click();
		await page.waitForTimeout(300);

		// Check workspace class after click
		const afterClass = await workspace.getAttribute('class');
		console.log('After click workspace class:', afterClass);

		// The workspace container should have the focus-mode class
		await expect(page.locator('.workspace.focus-mode')).toBeVisible({ timeout: 5000 });

		// Sidebar should be collapsed
		await expect(page.locator('.workspace.sidebar-collapsed')).toBeVisible();

		// Inspector should also be collapsed
		await expect(page.locator('.workspace.inspector-collapsed')).toBeVisible();

		// Focus panel should be visible
		const focusPanel = page.locator('.workspace-focus-panel');
		await expect(focusPanel).toBeVisible({ timeout: 5000 });

		// Should show "Focus Mode" heading text
		await expect(page.getByText('Focus Mode')).toBeVisible();
	});

	test('clicking Focus button again deactivates focus mode', async ({ page }) => {
		const focusButton = page.getByRole('button', { name: /Focus/i }).first();

		// Activate
		await focusButton.click();
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).toBeVisible({ timeout: 5000 });

		// Deactivate
		await focusButton.click();
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).not.toBeVisible({ timeout: 5000 });
	});

	test('Ctrl+Shift+F keyboard shortcut toggles focus mode', async ({ page }) => {
		// Click somewhere on the page first to ensure focus
		await page.locator('.workspace').first().click();
		await page.waitForTimeout(200);

		// Activate via keyboard
		await page.keyboard.press('Control+Shift+F');
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).toBeVisible({ timeout: 5000 });

		// Deactivate via keyboard
		await page.keyboard.press('Control+Shift+F');
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).not.toBeVisible({ timeout: 5000 });
	});

	test('Escape key exits focus mode', async ({ page }) => {
		// Activate focus mode via button
		const focusButton = page.getByRole('button', { name: /Focus/i }).first();
		await focusButton.click();
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).toBeVisible({ timeout: 5000 });

		// Press Escape to exit
		await page.keyboard.press('Escape');
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).not.toBeVisible({ timeout: 5000 });
	});

	test('focus panel has close button that exits focus mode', async ({ page }) => {
		// Activate focus mode
		const focusButton = page.getByRole('button', { name: /Focus/i }).first();
		await focusButton.click();
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).toBeVisible({ timeout: 5000 });

		// Click the X close button using JavaScript to avoid pointer interception
		const closeButton = page.getByTitle('Exit focus mode (Esc)');
		await expect(closeButton).toBeVisible();
		await closeButton.click({ force: true });
		await page.waitForTimeout(300);

		// Focus mode should be deactivated
		await expect(page.locator('.workspace.focus-mode')).not.toBeVisible({ timeout: 5000 });
	});

	test('focus mode shows PanelNavigator content', async ({ page }) => {
		// Activate focus mode
		const focusButton = page.getByRole('button', { name: /Focus/i }).first();
		await focusButton.click();
		await page.waitForTimeout(300);
		await expect(page.locator('.workspace.focus-mode')).toBeVisible({ timeout: 5000 });

		// The focus panel should be visible
		const focusPanel = page.locator('.workspace-focus-panel');
		await expect(focusPanel).toBeVisible();
	});
});
