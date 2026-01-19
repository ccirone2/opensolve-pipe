import { test, expect } from '@playwright/test';

test.describe('Homepage', () => {
	test('displays the main landing page', async ({ page }) => {
		await page.goto('/');

		// Check page title
		await expect(page).toHaveTitle(/OpenSolve Pipe/);

		// Check main heading
		await expect(page.getByRole('heading', { name: /Hydraulic Network Analysis/i })).toBeVisible();

		// Check "New Project" button exists
		await expect(page.getByRole('link', { name: /New Project/i })).toBeVisible();

		// Check features section
		await expect(page.getByText(/Instant Results/i)).toBeVisible();
		await expect(page.getByText(/Shareable via URL/i)).toBeVisible();
		await expect(page.getByText(/Mobile-Friendly/i)).toBeVisible();
	});

	test('navigates to new project page', async ({ page }) => {
		await page.goto('/');

		// Click "New Project" button
		await page.getByRole('link', { name: /New Project/i }).click();

		// Should navigate to /p/
		await expect(page).toHaveURL(/\/p\//);

		// Should show project editor
		await expect(page.getByRole('heading', { name: /New Project/i })).toBeVisible();
	});
});
