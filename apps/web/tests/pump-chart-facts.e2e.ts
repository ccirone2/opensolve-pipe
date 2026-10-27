import { gzipSync } from 'node:zlib';
import { expect, test } from '@playwright/test';
import type { Pump } from '../src/lib/api/types';
import { pumpTransferExample } from '../src/lib/utils/examples';
import { resultsView, solveConverged } from './support';

/**
 * The pump chart's curve facts (proposal pump-chart.md §6, slice 2), against the real app and
 * API, on desktop and on a phone: the pump example with a flow control, so the chart has the best
 * efficiency point (the example's efficiency curve peaks at 70 % inside its data), the shutoff
 * head, and the speed range with its iso-efficiency lines, which a chip hides.
 */

test('marks the best efficiency point and shows a flow-controlled pump’s speed range', async ({
	page
}) => {
	const project = pumpTransferExample();
	const pump = project.components.find((c) => c.id === 'P1') as Pump;
	pump.control = { mode: 'flow', setpoint: 0.012, minSpeed: 0.5 };
	const encoded = gzipSync(Buffer.from(JSON.stringify(project))).toString('base64url');
	await page.goto(`/p#${encoded}`);
	await solveConverged(page);
	const pumps = await resultsView(page, 'Pumps');
	const figure = pumps.getByRole('figure').first();
	await expect(figure.getByText(/System curve: the network/)).toBeVisible({ timeout: 30_000 });

	const chart = figure.getByRole('img');
	await expect(chart).toHaveAccessibleName(/best efficiency point 70 % at [\d.]+ L\/s/);
	await expect(chart).toHaveAccessibleName(
		/speed range from 50 % to 100 % speed, with lines of constant efficiency/
	);
	await expect(figure.getByText(/^Best efficiency point \(\+\): 70 % at/)).toBeVisible();
	await expect(figure.getByText(/^Shutoff head \(–\): [\d.]+ m\.$/)).toBeVisible();
	const speedNote = figure.getByText(/^Speed range of the flow control/);
	await expect(speedNote).toContainText('minimum (50 %) and maximum (100 %) speeds');
	await expect(speedNote).toContainText('at 65, 60, 55 %');

	await figure.getByRole('button', { name: 'Show data table' }).click();
	await expect(
		figure.getByRole('table', { name: 'Pump curve at 50 % speed (minimum)' })
	).toBeVisible();

	// The chip hides the speed range, its note and its tables.
	const chip = figure
		.getByRole('group', { name: 'Show' })
		.getByRole('button', { name: 'Speed range' });
	await expect(chip).toHaveAttribute('aria-pressed', 'true');
	await chip.click();
	await expect(chip).toHaveAttribute('aria-pressed', 'false');
	await expect(speedNote).toHaveCount(0);
	await expect(figure.getByRole('table', { name: /Pump curve at 50 % speed/ })).toHaveCount(0);
	await expect(chart).not.toHaveAccessibleName(/speed range/);
	expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
		true
	);
});
