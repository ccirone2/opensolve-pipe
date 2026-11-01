import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { API_ORIGIN } from './servers';

test('home page shows the product name', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('OpenSolve Pipe');
});

/**
 * The legal notices of a production build (AGPL-3.0 §13, TSD §11.1): the source link names the
 * commit the build was made from, the server source link leads to the API's own, and the
 * third-party licenses file is served from the site root
 * with the packages that are in the bundle.
 */
test('home page links to the source of this build and the third-party licenses', async ({
	page,
	request
}) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Source code', exact: true })).toHaveAttribute(
		'href',
		/^https:\/\/github\.com\/ccirone2\/opensolve-pipe\/tree\/[0-9a-f]{40}$/
	);
	// The calculation server's source: its /source redirects to the commit it runs, here the
	// repository, since the e2e API is not an image built with SOURCE_COMMIT (TSD §11.2).
	const server = page.getByRole('link', { name: "calculation server's source code" });
	await expect(server).toHaveAttribute('href', `${API_ORIGIN}/source`);
	const redirect = await request.get(`${API_ORIGIN}/source`, { maxRedirects: 0 });
	expect(redirect.status()).toBe(302);
	expect(redirect.headers()['location']).toBe('https://github.com/ccirone2/opensolve-pipe');
	const notices = page.getByRole('link', { name: 'third-party licenses' });
	await expect(notices).toHaveAttribute('href', '/third-party-licenses.txt');
	const response = await request.get('/third-party-licenses.txt');
	expect(response.status()).toBe(200);
	const text = await response.text();
	for (const name of ['chart.js', 'pako', 'svelte', 'tailwindcss'])
		expect(text).toMatch(new RegExp(`^- ${name.replace('.', '\\.')} \\d`, 'm'));
});

test('a new project starts in US customary units; SI is the first choice in Settings, one tap', async ({
	page
}) => {
	await page.goto('/');
	await page.getByRole('link', { name: 'New project' }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await page.getByRole('button', { name: 'Settings' }).click();
	const dialog = page.getByRole('dialog', { name: 'Project settings' });
	// The units come first: the setting people reach for (proposal build-density.md §13).
	const presets = dialog.getByRole('group', { name: 'Unit presets' });
	const first = dialog.getByRole('heading', { level: 3 }).first();
	await expect(first).toHaveText('Units');
	await expect(presets.getByRole('button', { name: 'US customary' })).toHaveAttribute(
		'aria-pressed',
		'true'
	);
	await expect(dialog.getByRole('textbox', { name: 'Site elevation (ft)' })).toBeVisible();
	await presets.getByRole('button', { name: 'SI' }).click();
	await expect(presets.getByRole('button', { name: 'SI' })).toHaveAttribute('aria-pressed', 'true');
	await expect(dialog.getByRole('textbox', { name: 'Site elevation (m)' })).toBeVisible();
});

/**
 * The landing page (proposal landing-page.md): the start first, then what it models, how its
 * results are checked, its scope and limits and privacy, with the screenshots shown for the
 * screen's size, and no WCAG 2.2 A/AA violation with its Details open.
 */
test('the landing page: the start, its sections, the screenshots, and axe clean', async ({
	page,
	isMobile
}) => {
	await page.goto('/');
	await expect(page.getByRole('link', { name: 'New project' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Open an example' })).toBeVisible();
	for (const name of [
		'Examples',
		'What it models',
		'How the results are checked',
		'Scope and limits',
		'Your project lives in the link'
	])
		await expect(page.getByRole('heading', { level: 2, name })).toBeVisible();
	// No recent projects in a fresh browser: the section is not there at all.
	await expect(page.getByRole('heading', { name: 'Recent on this device' })).toHaveCount(0);
	// The phone shot always; the laptop shot from 640 px. Each one loaded.
	const phone = page.getByRole('img', { name: /on a phone/ });
	const laptop = page.getByRole('img', { name: /on a laptop/ });
	await expect(phone).toBeVisible();
	if (isMobile) await expect(laptop).toBeHidden();
	else await expect(laptop).toBeVisible();
	for (const image of isMobile ? [phone] : [phone, laptop]) {
		await image.scrollIntoViewIfNeeded();
		await expect
			.poll(() => image.evaluate((img) => (img as HTMLImageElement).naturalWidth))
			.toBeGreaterThan(0);
	}
	// Privacy: short, with the full text one step away.
	const privacy = page.getByRole('region', { name: 'Your project lives in the link' });
	await expect(privacy.getByText(/Solving sends the project/)).toBeHidden();
	await privacy.getByText('Details').click();
	await expect(privacy.getByText(/Solving sends the project/)).toBeVisible();
	await expect(
		privacy.getByText(/Recent\s+projects are remembered in this browser only/)
	).toBeVisible();
	const scan = await new AxeBuilder({ page })
		.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
		.analyze();
	expect(scan.violations.map((v) => `${v.id} (${v.nodes.length})`)).toEqual([]);
});

/** Go home from the project page, through the app's own link. */
async function goHome(page: Page) {
	await page.getByRole('link', { name: 'OpenSolve Pipe home' }).click();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('OpenSolve Pipe');
}

test('recent projects: an opened example or an empty project is not kept; a change is', async ({
	page
}) => {
	const recent = page.getByRole('region', { name: 'Recent on this device' });
	// An example opened and left unchanged, and a new project with nothing in it: not kept.
	await page.goto('/');
	await page.getByRole('link', { name: /^Gravity-fed/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await goHome(page);
	await page.getByRole('link', { name: 'New project' }).click();
	await expect(page.getByRole('heading', { name: 'Start the network' })).toBeVisible();
	await goHome(page);
	await expect(recent).toHaveCount(0);

	// A changed example is kept, under its name, and its link opens the project as it was.
	await page.getByRole('link', { name: /^Pump transfer/ }).click();
	const name = page.getByRole('textbox', { name: 'Project name' });
	await name.fill('Line 4 transfer');
	await name.press('Tab');
	await goHome(page);
	await expect(recent.getByRole('link', { name: /^Line 4 transfer/ })).toBeVisible();
	const axe = await new AxeBuilder({ page })
		.include('section[aria-labelledby="recent-title"]')
		.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
		.analyze();
	expect(axe.violations.map((v) => `${v.id} (${v.nodes.length})`)).toEqual([]);
	await recent.getByRole('link', { name: /^Line 4 transfer/ }).click();
	await expect(page.getByRole('textbox', { name: 'Project name' })).toHaveValue('Line 4 transfer');

	// One entry per project: a second change updates it rather than adding another.
	await page.getByRole('textbox', { name: 'Project name' }).fill('Line 4 transfer, rev B');
	await page.getByRole('textbox', { name: 'Project name' }).press('Tab');
	await goHome(page);
	await expect(recent.getByRole('listitem')).toHaveCount(1);
	await expect(recent.getByRole('link', { name: /^Line 4 transfer, rev B/ })).toBeVisible();

	// Forget one, and Forget all; the list stays forgotten after a reload.
	await page.getByRole('link', { name: /^Chiller plant/ }).click();
	await page.getByRole('textbox', { name: 'Project name' }).fill('Plant B condenser water');
	await page.getByRole('textbox', { name: 'Project name' }).press('Tab');
	await goHome(page);
	await expect(recent.getByRole('listitem')).toHaveCount(2);
	await expect(recent.getByRole('listitem').first()).toContainText('Plant B condenser water');
	await recent.getByRole('button', { name: 'Forget Plant B condenser water' }).click();
	await expect(recent.getByRole('listitem')).toHaveCount(1);
	await recent.getByRole('button', { name: 'Forget all' }).click();
	await expect(recent).toHaveCount(0);
	await page.reload();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('OpenSolve Pipe');
	await expect(recent).toHaveCount(0);
	expect(
		await page.evaluate(() => localStorage.getItem('opensolve-pipe:recent-projects'))
	).toBeNull();
});
