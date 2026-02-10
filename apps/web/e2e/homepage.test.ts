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

		// Should navigate to /p/{encoded} (workspace with encoded project data)
		await expect(page).toHaveURL(/\/p\/.+/, { timeout: 5000 });

		// Should show the workspace with "Untitled Project" title
		await expect(page.getByText('Untitled Project').first()).toBeVisible({ timeout: 10000 });

		// Should show the Solve button (workspace is loaded)
		await expect(page.getByRole('button', { name: /Solve/i })).toBeVisible();
	});
});
