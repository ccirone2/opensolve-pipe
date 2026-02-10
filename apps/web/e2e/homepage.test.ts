import { test, expect } from '@playwright/test';

test.describe('Homepage', () => {
	test('displays the main landing page', async ({ page }) => {
		await page.goto('/');

		// Check page title
		await expect(page).toHaveTitle(/OpenSolve Pipe/);

		// Check main heading
		await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

		// Check "New Project" button exists
		await expect(page.getByRole('link', { name: /New Project/i })).toBeVisible();

		// Check features section
		await expect(page.getByText(/Fast Solver/i)).toBeVisible();
		await expect(page.getByText(/URL-Encoded State/i)).toBeVisible();
		await expect(page.getByText(/Engineering Workspace/i)).toBeVisible();
	});

	test('navigates to new project page', async ({ page }) => {
		await page.goto('/');

		// Click "New Project" button
		await page.getByRole('link', { name: /New Project/i }).click();

		// Should navigate to /p (new project redirect page)
		await expect(page).toHaveURL(/\/p/);

		// Should show the redirect loading page with "Creating new project..." text
		await expect(page.getByText(/Creating new project/i)).toBeVisible({ timeout: 10000 });
	});
});
