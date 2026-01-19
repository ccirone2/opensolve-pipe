import { test, expect } from '@playwright/test';

test.describe('URL Encoding', () => {
	test('new project has no encoded data in URL', async ({ page }) => {
		await page.goto('/p/');

		// URL should be just /p/ or /p
		expect(page.url()).toMatch(/\/p\/?$/);
	});

	test('handles invalid encoded data gracefully', async ({ page }) => {
		// Navigate to a URL with invalid encoded data
		await page.goto('/p/invalid-data-here');

		// Page should still load without crashing
		await expect(page.locator('body')).toBeVisible();

		// Should show some error state or fallback to new project
		// (exact behavior depends on implementation)
	});

	test('handles malformed base64 gracefully', async ({ page }) => {
		// Navigate to a URL with malformed base64
		await page.goto('/p/!!!invalid!!!');

		// Page should still load without crashing
		await expect(page.locator('body')).toBeVisible();
	});
});
