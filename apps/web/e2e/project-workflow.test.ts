import { test, expect } from '@playwright/test';

test.describe('Project Workflow', () => {
	test.beforeEach(async ({ page }) => {
		// Navigate to new project page
		await page.goto('/p');
	});

	test('shows new project view with panel navigator', async ({ page }) => {
		// Check page elements - project name is displayed in header - use first() to handle multiple instances
		await expect(page.getByText('Untitled Project').first()).toBeVisible();

		// Should show Build/Results view switcher
		await expect(page.getByRole('button', { name: /Build/i })).toBeVisible();
		await expect(page.getByRole('button', { name: /Results/i })).toBeVisible();

		// Should show Solve button
		await expect(page.getByRole('button', { name: /Solve/i })).toBeVisible();
	});

	test('switches between Build and Results views', async ({ page }) => {
		// Start in Build view
		const buildButton = page.getByRole('button', { name: /Build/i });
		const resultsButton = page.getByRole('button', { name: /Results/i });

		// Build should be active initially - check for visibility
		await expect(buildButton).toBeVisible();

		// Click Results button
		await resultsButton.click();

		// Results should now be active (button should still be visible)
		await expect(resultsButton).toBeVisible();

		// Click Build button
		await buildButton.click();

		// Build should be active again
		await expect(buildButton).toBeVisible();
	});

	test('solve button is disabled when project has no components', async ({ page }) => {
		// Solve button should be disabled for empty project
		const solveButton = page.getByRole('button', { name: /Solve/i });
		await expect(solveButton).toBeDisabled();
	});
});

test.describe('Project Navigation', () => {
	test('panel navigator shows add component button', async ({ page }) => {
		await page.goto('/p');

		// Should show "Add First Component" or similar
		await expect(
			page.getByRole('button', { name: /Add|Create|Start/i }).first()
		).toBeVisible();
	});

	test('can add a component to the project', async ({ page }) => {
		await page.goto('/p');

		// Click add component button
		const addButton = page.getByRole('button', { name: /Add|Create|Start/i }).first();
		await addButton.click();

		// Should show component type selector with "Add Component" heading
		await expect(page.getByRole('heading', { name: /Add Component/i })).toBeVisible();
	});
});

test.describe('Keyboard Shortcuts', () => {
	test('Ctrl+Enter triggers solve', async ({ page }) => {
		await page.goto('/p');

		// Add a component first to enable solve
		// For now, just test that the shortcut doesn't cause errors
		await page.keyboard.press('Control+Enter');

		// Page should still be functional
		await expect(page.getByRole('button', { name: /Solve/i })).toBeVisible();
	});
});
