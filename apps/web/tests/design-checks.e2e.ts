import { gzipSync } from 'node:zlib';
import { expect, test } from '@playwright/test';
import { pumpTransferExample } from '../src/lib/utils/examples';
import { resultsPane, resultsView, showPane, solveConverged } from './support';

/**
 * Opt-in design checks (CLAUDE.md D19; proposal design-checks.md), against the real app and API,
 * on desktop and on a phone. The pump example runs at about 127 % of its best efficiency flow
 * (19.0 of 15 L/s) and moves 2.3 and 4.0 m/s in its pipes: with API 610's preferred region and a
 * 3 m/s maximum velocity, its operating region and two pipes fail; its NPSH margin passes the
 * HI 9.6.1-2012 preset, and its manufacturer data (allowable region, minimum flows, a 5.5 kW
 * motor under 6.1 kW of shaft power) give one more failure.
 */

function checkedExample() {
	const project = pumpTransferExample();
	project.settings.designChecks = {
		npshMargin: {
			minimumRatio: 1.1,
			minimumMargin: 1.0,
			source: { kind: 'preset', preset: 'hi961_2012_general' }
		},
		operatingRegion: {
			preferredMin: 0.7,
			preferredMax: 1.2,
			source: { kind: 'preset', preset: 'api610_por' }
		},
		pipeVelocity: { maximum: 3, source: { kind: 'user' } }
	};
	Object.assign(project.pumpLibrary[0]!, {
		allowableOperatingRegion: { flowMin: 0.006, flowMax: 0.026 },
		minimumContinuousStableFlow: 0.004,
		minimumThermalFlow: 0.003,
		motorRatedPower: 5500
	});
	return project;
}

test('lists the checks not met first, and draws their limits on the pump chart', async ({
	page
}) => {
	const encoded = gzipSync(Buffer.from(JSON.stringify(checkedExample()))).toString('base64url');
	await page.goto(`/p#${encoded}`);
	await solveConverged(page);
	await showPane(page, 'Results');

	// The Summary counts them and names those not met.
	const summary = resultsPane(page).getByRole('region', { name: 'Design checks' });
	await expect(summary).toContainText('4 not met · 4 met');
	await expect(summary).toContainText(
		'Operating region: Flow 126.6 % of the best efficiency flow, outside 70 % to 120 %'
	);
	await expect(summary).toContainText('and 1 more not met');

	// Checks: not met first, each naming its element, its value and its limit's source.
	await summary.getByRole('button', { name: 'All checks' }).click();
	const checks = resultsPane(page).getByRole('tabpanel', { name: 'Checks' });
	const notMet = checks.getByRole('region', { name: /^Not met/ });
	await expect(notMet.getByRole('heading')).toHaveText(/Not met \(4\)/);
	await expect(notMet).toContainText("Shaft power 6.119 kW, above the motor's rated 5.5 kW");
	await expect(notMet).toContainText('Velocity 3.981 m/s in pipe 1, above 3 m/s');
	await expect(notMet).toContainText('Limits: API 610 preset');
	const met = checks.getByRole('region', { name: /^Met/ });
	await expect(met).toContainText('NPSHa 12.74 m, at least the 4.039 m required');
	await expect(met).toContainText('Limits: HI 9.6.1-2012 (general) preset');
	await expect(checks).toContainText('as quoted by Datacor');
	// The API's own words are under Details.
	await met.getByText(/HI 9\.6\.1-2012 \(general\) preset · Details/).click();
	await expect(met.getByText(/= max\(NPSHr 3\.03913 m \+ 1 m, 1\.1 × NPSHr/)).toBeVisible();
	// A check not met never marks the Results tab (checks are not flags; it is a tab on phones).
	const tab = page.getByRole('tablist', { name: 'View' }).getByRole('tab', { name: /^Results/ });
	if (await tab.isVisible()) await expect(tab).toHaveAccessibleName('Results');

	// The pump chart: the limits shown, in notes, behind a chip.
	const pumps = await resultsView(page, 'Pumps');
	const figure = pumps.getByRole('figure').first();
	await expect(figure.getByText(/System curve: the network/)).toBeVisible({ timeout: 30_000 });
	const por = figure.getByText(
		/^Shaded blue \(POR\): the preferred operating region, 70 % to 120 %/
	);
	await expect(por).toContainText('10.5 to 18 L/s; API 610 preset');
	await expect(figure.getByText(/^Shaded grey \(AOR\)/)).toContainText('6 to 26 L/s at this speed');
	await expect(
		figure.getByText(/^Dash-dot line: the minimum continuous stable flow, 4 L\/s/)
	).toBeVisible();
	await expect(figure.getByText(/^Dotted on the NPSH panel/)).toContainText(
		'the greater of NPSHr + 1 m and 1.1 × NPSHr (HI 9.6.1-2012 (general) preset)'
	);
	await expect(
		figure.getByText(/^Dashed on the power panel: the motor's rated power, 5.5 kW/)
	).toBeVisible();
	await expect(figure.getByRole('img')).toHaveAccessibleName(/with the design checks' limits/);
	const chip = figure
		.getByRole('group', { name: 'Show' })
		.getByRole('button', { name: 'Design checks' });
	await expect(chip).toHaveAttribute('aria-pressed', 'true');
	await chip.click();
	await expect(chip).toHaveAttribute('aria-pressed', 'false');
	await expect(por).toHaveCount(0);
	await expect(figure.getByRole('img')).not.toHaveAccessibleName(/design checks/);
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
		true
	);
});

test('turns a check on in Settings, fills it from a preset, and solves with it', async ({
	page
}) => {
	const encoded = gzipSync(Buffer.from(JSON.stringify(pumpTransferExample()))).toString(
		'base64url'
	);
	await page.goto(`/p#${encoded}`);
	await page.getByRole('button', { name: 'Settings' }).click();
	const dialog = page.getByRole('dialog', { name: 'Settings' });
	const npsh = dialog.getByRole('checkbox', { name: 'NPSH margin' });
	await expect(npsh).not.toBeChecked();
	await npsh.check();
	await dialog.getByRole('button', { name: 'Use HI 9.6.1-2012 (general)' }).click();
	await expect(dialog.getByRole('textbox', { name: 'Minimum margin NPSHa − NPSHr' })).toHaveValue(
		'1'
	);
	await expect(dialog.getByRole('textbox', { name: 'Minimum ratio NPSHa / NPSHr' })).toHaveValue(
		'1.1'
	);
	await expect(dialog.getByText(/^Source: ANSI\/HI 9\.6\.1-2012/)).toBeVisible();
	// A limit typed by hand makes the source the user's.
	const velocity = dialog.getByRole('checkbox', { name: 'Pipe velocity' });
	await velocity.check();
	const maximum = dialog.getByRole('textbox', { name: 'Maximum velocity' });
	await maximum.fill('3');
	await maximum.press('Enter');
	await dialog.getByRole('button', { name: 'Done' }).click();
	await expect(dialog).toBeHidden();

	await solveConverged(page);
	await showPane(page, 'Results');
	const checks = await resultsView(page, 'Checks');
	await expect(checks.getByRole('region', { name: /^Not met \(2\)/ })).toBeVisible();
	await expect(checks.getByRole('region', { name: /^Met \(2\)/ })).toContainText(
		'Limits: your values'
	);
	// The checks travel with the link.
	await expect(page).toHaveURL(/\/p#/);
	const url = page.url();
	await page.goto('about:blank');
	await page.goto(url);
	await page.getByRole('button', { name: 'Settings' }).click();
	await expect(
		page.getByRole('dialog', { name: 'Settings' }).getByRole('checkbox', { name: 'NPSH margin' })
	).toBeChecked();
});
