import { expect, test } from '@playwright/test';
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
