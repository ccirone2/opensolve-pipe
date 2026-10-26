import { expect, test, type Page } from '@playwright/test';
import { ALLOWED_ORIGINS } from './support';

/** The examples on the home page, their start component and the next one along the walk. */
const EXAMPLES = [
	{ link: /Pump transfer/, start: 'Suction tank', next: 'Transfer pump' },
	{ link: /Gravity-fed/, start: 'Elevated tank', next: 'Distribution tee' },
	{
		link: /Closed loop/,
		start: 'Expansion tank (pressurization point)',
		next: 'Pressurization tee'
	}
];

const build = (page: Page) => page.getByRole('region', { name: 'Build' });
const breadcrumb = (page: Page) =>
	page.getByRole('navigation', { name: 'Path' }).getByRole('button');

for (const example of EXAMPLES) {
	test(`opens the example starting at “${example.start}” and walks on with Next`, async ({
		page
	}) => {
		await page.goto('/');
		await page.getByRole('link', { name: example.link }).click();
		await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);

		const panel = build(page);
		await expect(panel.getByRole('heading', { level: 2, name: example.start })).toBeAttached();
		// The name is shown once, in its in-place field: a walk of one step has no breadcrumb.
		await expect(panel.getByRole('textbox', { name: 'Name' })).toHaveValue(example.start);
		await expect(breadcrumb(page)).toHaveCount(0);

		await panel.getByRole('button', { name: /^Next/ }).click();
		await expect(panel.getByRole('heading', { level: 2, name: example.next })).toBeVisible();
		await expect(breadcrumb(page)).toHaveText([example.start, example.next]);

		await panel.getByRole('button', { name: /^Previous/ }).click();
		await expect(panel.getByRole('heading', { level: 2, name: example.start })).toBeVisible();
	});
}

test('a shared link opens the project directly, and edits make a new link', async ({ page }) => {
	const origins = new Set<string>();
	page.on('request', (request) => origins.add(new URL(request.url()).origin));

	await page.goto('/');
	const href = await page.getByRole('link', { name: /Gravity-fed/ }).getAttribute('href');
	expect(href).toMatch(/^\/p#/);
	await page.goto(href ?? '/');
	const panel = build(page);
	await expect(panel.getByRole('heading', { level: 2, name: 'Elevated tank' })).toBeVisible();

	const original = page.url();
	const name = panel.getByRole('textbox', { name: 'Name' });
	await name.fill('Header tank');
	await name.press('Enter');
	await expect(panel.getByRole('heading', { level: 2, name: 'Header tank' })).toBeVisible();
	await expect.poll(() => page.url()).not.toBe(original);

	// The new link holds the edit; the original still opens the original.
	await page.reload();
	await expect(build(page).getByRole('heading', { level: 2, name: 'Header tank' })).toBeVisible();
	await page.goto(original);
	await page.reload();
	await expect(build(page).getByRole('heading', { level: 2, name: 'Elevated tank' })).toBeVisible();

	// Only the app and its calculation server are contacted (GOALS §4.5).
	expect([...origins].filter((o) => !ALLOWED_ORIGINS.has(o))).toEqual([]);
});

test('a damaged link explains what happened', async ({ page }) => {
	await page.goto('/p#not-a-project');
	await expect(page.getByRole('heading', { level: 1, name: /This link is damaged/ })).toBeVisible();
	await page.getByRole('link', { name: 'Start a new project' }).click();
	await expect(page.getByRole('heading', { name: 'Start the network' })).toBeVisible();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
});
