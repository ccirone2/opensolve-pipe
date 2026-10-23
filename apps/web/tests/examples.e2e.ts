import { readdirSync, readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { EXAMPLES } from '../src/lib/utils/examples';
import { buildPane, resultsPane, showPane, solveConverged } from './support';

/**
 * The home page's examples, opened as a new user would and solved unmodified against the real
 * API: each converges with no flag, so a first look at an example shows no warning its summary
 * does not explain.
 */
for (const example of EXAMPLES) {
	test(`example “${example.title}” solves without flags`, async ({ page }) => {
		await page.goto('/');
		await page.getByRole('link', { name: new RegExp(`^${example.title}`) }).click();
		await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
		const solved = await solveConverged(page);
		expect(solved.flags.map((f) => `${f.code}: ${f.message}`)).toEqual([]);
		await showPane(page, 'Results');
		await expect(resultsPane(page).getByRole('heading', { name: /^Flags/ })).toHaveCount(0);
	});
}

/**
 * Every released schema version's fixture link (src/lib/utils/__fixtures__/schema-vN.txt, D2:
 * shared links live forever), opened on this app's origin: it is decoded, upgraded by the
 * migrations and solved against the real API, and converges.
 */
const FIXTURES = new URL('../src/lib/utils/__fixtures__/', import.meta.url);
const fixtureLinks = readdirSync(FIXTURES).filter((name) => /^schema-v\d+\.txt$/.test(name));

test('there is a fixture link to open', () => {
	expect(fixtureLinks).toContain('schema-v1.txt');
});

for (const name of fixtureLinks) {
	test(`released link ${name} opens and solves`, async ({ page }) => {
		const link = readFileSync(new URL(name, FIXTURES), 'utf8').trim();
		const fragment = new URL(link).hash;
		expect(fragment).toMatch(/^#[A-Za-z0-9_-]+$/);
		await page.goto(`/p${fragment}`);
		await expect(buildPane(page).getByRole('heading', { level: 2 })).toBeVisible();
		await expect(page.getByRole('heading', { level: 1, name: /This link is damaged/ })).toHaveCount(
			0
		);
		await solveConverged(page);
	});
}
