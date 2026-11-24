import { expect, test, type Locator } from '@playwright/test';
import { addFirst, buildPane, currentHeading, setNumber, solveConverged } from './support';

/**
 * Data entry (proposal usability-entry.md): a new project in US units, as a first-time user
 * meets it, built through the panel navigator with values typed in other units, a pump curve
 * pasted from a spreadsheet in metric, and solved against the real API.
 *
 *   Reservoir R1 → Pump P1 → Reservoir R2
 *
 * Illustrative test input: made-up levels and a made-up pump curve, not a real pump's data.
 */

/** Paste `text` into a field as the browser does from the clipboard. */
async function pasteInto(field: Locator, text: string): Promise<void> {
	await field.evaluate((element, pasted) => {
		const data = new DataTransfer();
		data.setData('text/plain', pasted);
		element.dispatchEvent(
			new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true })
		);
	}, text);
}

/** True when an element's text is cut off (its content is wider than its box). */
async function cutOff(locator: Locator): Promise<boolean> {
	return locator.evaluate((element) => element.scrollWidth > element.clientWidth + 0.5);
}

test('a new US project: round pipe lengths, units typed and checked, a curve pasted, solved', async ({
	page
}) => {
	await page.goto('/');
	await page.getByRole('link', { name: 'New project' }).click();
	const panel = buildPane(page);
	await expect(panel.getByRole('heading', { name: 'Start the network' })).toBeVisible();
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await setNumber(panel, /^Liquid level/, '10');

	// A new connection's pipe is a round 30 ft where lengths show in feet (§5).
	await panel.getByRole('button', { name: 'Add after' }).click();
	const dialog = page.getByRole('dialog', { name: /^Add after/ });
	await expect(dialog).toContainText('with 30 ft of carbon steel schedule 40 pipe');
	await dialog.getByRole('combobox', { name: 'Component' }).selectOption({ label: 'Pump' });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Pump P1');

	// Previous names the reservoir in full; "Previous" is in its name, not beside it (§4).
	const previous = panel.getByRole('button', { name: /^Previous/ });
	await expect(previous).toHaveAccessibleName('Previous: Reservoir R1');
	await expect(previous).toHaveText('Reservoir R1');
	expect(await cutOff(previous.locator('span.truncate'))).toBe(false);
	const next = panel.getByRole('button', { name: /^Next/ });
	await expect(next).toHaveAccessibleName('Next: connect discharge');
	expect(await cutOff(next.locator('span.truncate'))).toBe(false);

	// The pump's curve pasted from a spreadsheet with metric headings (§6): converted, stored.
	const first = panel.getByRole('textbox', { name: 'Point 1 flow (gpm)' });
	await pasteInto(first, 'Flow (m3/h)\tHead (m)\n0\t46\n68\t40\n114\t30\n136\t24\n');
	await expect(panel.getByText('Pasted 4 points: flow in m³/h, head in m.')).toBeVisible();
	// 68 m³/h = 68/3600 m³/s ÷ (231 × 0.0254³ / 60) m³/s per gpm = 299.4 gpm (6 digits shown).
	const gpm = (231 * 0.0254 ** 3) / 60;
	await expect(panel.getByRole('textbox', { name: 'Point 2 flow (gpm)' })).toHaveValue(
		String(Number((68 / 3600 / gpm).toPrecision(6)))
	);
	await expect(panel.getByRole('textbox', { name: 'Point 4 head (ft)' })).toHaveValue(
		String(Number((24 / 0.3048).toPrecision(6)))
	);
	await expect(panel.getByText(/needs a curve/)).toHaveCount(0);

	// The suction pipe: 30 ft, and a length typed in metres is converted and said so (§3).
	await panel.getByRole('tab', { name: 'Piping' }).click();
	await panel.getByRole('button', { name: /^Suction/ }).click();
	const length = panel.getByRole('textbox', { name: 'Length (ft)' });
	await expect(length).toHaveValue('30');
	await length.fill('12 m');
	await length.press('Enter');
	await expect(length).toHaveValue(String(Number((12 / 0.3048).toPrecision(6))));
	await expect(length).toHaveAccessibleDescription(/Converted from 12 m\./);
	await length.fill('40 ft');
	await length.press('Enter');
	await expect(length).toHaveValue('40');

	// The discharge tank: a gauge field refuses an absolute pressure, and takes a gauge one.
	await panel.getByRole('tab', { name: 'Properties' }).click();
	await panel.getByRole('button', { name: 'Add after' }).click();
	await dialog.getByRole('combobox', { name: 'Component' }).selectOption({ label: 'Reservoir' });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Reservoir R2');
	await setNumber(panel, /^Liquid level/, '20');
	await panel.getByText(/^More/).first().click();
	const surface = panel.getByRole('textbox', { name: 'Surface pressure (psig)' });
	await surface.fill('14.7 psia');
	await surface.press('Enter');
	await expect(surface).toHaveAttribute('aria-invalid', 'true');
	await expect(panel.getByRole('alert')).toHaveText(
		'This is a gauge pressure (psig): an absolute value needs the atmospheric pressure subtracted first.'
	);
	await surface.fill('2 psig');
	await surface.press('Enter');
	await expect(surface).not.toHaveAttribute('aria-invalid', 'true');
	await expect(surface).toHaveValue('2');

	const solved = await solveConverged(page);
	expect(solved.converged).toBe(true);
});
