import { test, expect } from '@playwright/test';

// Navigate to /p/empty to directly load workspace with default (empty) project.
// The "empty" string is invalid encoded data, so tryDecodeProject returns null
// and the workspace renders with the default store state.
const WORKSPACE_URL = '/p/empty';

test.describe('Project Workflow', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto(WORKSPACE_URL);
	});

	test('shows new project view with workspace layout', async ({ page }) => {
		// Check page elements - project name is displayed in toolbar
		await expect(page.getByText('Untitled Project').first()).toBeVisible({ timeout: 10000 });

		// Should show Solve button in toolbar
		await expect(page.getByRole('button', { name: 'Solve', exact: true })).toBeVisible();
	});

	test('solve button is disabled when project has no components', async ({ page }) => {
		// Wait for workspace to render
		await expect(
			page.getByRole('button', { name: 'Solve', exact: true })
		).toBeVisible({ timeout: 10000 });

		// Solve button should be disabled for empty project
		const solveButton = page.getByRole('button', { name: 'Solve', exact: true });
		await expect(solveButton).toBeDisabled();
	});
});

test.describe('Project Navigation', () => {
	test('shows add component elements in empty state', async ({ page }) => {
		await page.goto(WORKSPACE_URL);

		// Should show empty state with build prompt
		await expect(
			page.getByText(/Start Building|Add Component|No components/i).first()
		).toBeVisible({ timeout: 10000 });
	});

	test('can open command palette', async ({ page }) => {
		await page.goto(WORKSPACE_URL);

		// Wait for workspace to render
		await expect(page.getByText('Untitled Project').first()).toBeVisible({ timeout: 10000 });

		// Click the "Add component" button in the sidebar footer to open command palette
		await page.getByRole('button', { name: /Add component/i }).first().click();

		// Should show command palette with search input
		await expect(page.getByPlaceholder(/search|type/i).first()).toBeVisible({ timeout: 5000 });
	});
});

test.describe('Keyboard Shortcuts', () => {
	test('Ctrl+Enter triggers solve', async ({ page }) => {
		await page.goto(WORKSPACE_URL);

		// Wait for workspace to render
		await expect(
			page.getByRole('button', { name: 'Solve', exact: true })
		).toBeVisible({ timeout: 10000 });

		// Press Ctrl+Enter (should not cause errors on empty project)
		await page.keyboard.press('Control+Enter');

		// Page should still be functional
		await expect(
			page.getByRole('button', { name: 'Solve', exact: true })
		).toBeVisible();
	});
});
