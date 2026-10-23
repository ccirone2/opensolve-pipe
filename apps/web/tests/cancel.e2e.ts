import { expect, test, type Page, type Request, type Route } from '@playwright/test';
import {
	buildPane,
	currentHeading,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	solveConverged
} from './support';

/**
 * Cancel (PRD §4.2: a progress indicator with a cancel option) against the real app and API: a
 * solve and a system curve are held at the network (page.route), so Cancel can be pressed while
 * they run; the request is aborted, the app says what happened and keeps what it showed before,
 * labelled as before; solving or computing again then works. On desktop and on a phone.
 *
 * Network: the home page's pump-transfer example (illustrative, made-up inputs). The pump speed
 * entered below is a made-up test input.
 */

async function openExample(page: Page) {
	await page.goto('/');
	await page.getByRole('link', { name: /^Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(currentHeading(page)).toHaveText('Suction tank');
}

/**
 * Hold every request to the API path at the network, unanswered, until the page aborts it or the
 * route is removed. Returns the requests held.
 */
async function hold(page: Page, path: string): Promise<Route[]> {
	const held: Route[] = [];
	await page.route(`**${path}`, (route) => {
		held.push(route);
	});
	return held;
}

/** The request to the API path failing because the page aborted it. */
function aborted(page: Page, path: string): Promise<Request> {
	return page.waitForEvent('requestfailed', (r) => r.url().endsWith(path));
}

/** Pixels the page scrolls sideways (0: it fits). */
function sidewaysScroll(page: Page): Promise<number> {
	return page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
}

const solveButton = (page: Page) => page.getByRole('button', { name: 'Solve', exact: true });
const cancelSolve = (page: Page) => page.getByRole('button', { name: 'Cancel solve' });
const status = (page: Page) => resultsPane(page).getByRole('status');

test('cancel a solve: the request is aborted, the app says so, and solving again works', async ({
	page
}, testInfo) => {
	await openExample(page);
	const held = await hold(page, '/api/v1/solve');
	const sent = page.waitForRequest((r) => r.url().endsWith('/api/v1/solve'));
	await solveButton(page).click();
	await sent;

	// While it runs: Solving… (unavailable, still focusable) and Cancel, in the header.
	await expect(page.getByRole('button', { name: 'Solving…' })).toHaveAttribute(
		'aria-disabled',
		'true'
	);
	await expect(status(page)).toHaveText('Solving…');
	const cancel = cancelSolve(page);
	await expect(cancel).toBeVisible();
	await expect(page.getByRole('banner').getByRole('toolbar', { name: 'Project' })).toContainText(
		'Solving…'
	);
	// Fits the header: no sideways scroll, Cancel and Settings wholly on screen. On a phone it is
	// an icon button, as Share and Settings are; its name says what it cancels.
	expect(await sidewaysScroll(page)).toBe(0);
	const width = page.viewportSize()!.width;
	for (const button of [cancel, page.getByRole('button', { name: 'Settings' })]) {
		const box = (await button.boundingBox())!;
		expect(box.x).toBeGreaterThanOrEqual(0);
		expect(box.x + box.width).toBeLessThanOrEqual(width);
		expect(box.height).toBeGreaterThanOrEqual(44); // touch target
	}
	const label = cancel.getByText('Cancel', { exact: true });
	if (testInfo.project.name === 'mobile') await expect(label).toBeHidden();
	else await expect(label).toBeVisible();

	const abort = aborted(page, '/api/v1/solve');
	await cancel.click();
	expect((await abort).failure()?.errorText).toBe('net::ERR_ABORTED');
	expect(held).toHaveLength(1);

	// Said in the live status line and in the pane; Solve is available again and has the focus.
	await expect(cancel).toBeHidden();
	await expect(solveButton(page)).toBeFocused();
	await expect(solveButton(page)).toHaveAttribute('aria-disabled', 'false');
	await expect(status(page)).toHaveText('Solve cancelled');
	await expect(
		resultsPane(page).getByText(
			'The solve was cancelled before it finished, so there are no results yet.'
		)
	).toBeVisible();
	await expect(resultsPane(page).getByRole('heading', { name: 'Converged' })).toHaveCount(0);

	// Solving again, let through, gives results; the note goes.
	await page.unroute('**/api/v1/solve');
	await solveConverged(page);
	await expect(resultsPane(page).getByText(/The solve was cancelled/)).toHaveCount(0);
});

test('the header fits 320 px, and 640 px where Cancel has its text, while a solve runs', async ({
	page
}, testInfo) => {
	test.skip(testInfo.project.name !== 'mobile', 'narrow-screen check');
	await page.setViewportSize({ width: 320, height: 640 });
	await openExample(page);
	await hold(page, '/api/v1/solve');
	await solveButton(page).click();
	await expect(cancelSolve(page)).toBeVisible();
	for (const width of [320, 640]) {
		await page.setViewportSize({ width, height: 640 });
		expect(await sidewaysScroll(page), `${width} px`).toBe(0);
		for (const name of ['Solving…', 'Cancel solve', 'Share', 'Settings']) {
			const box = (await page.getByRole('button', { name, exact: true }).boundingBox())!;
			expect(box.x + box.width, `${name} at ${width} px`).toBeLessThanOrEqual(width);
		}
		// The toolbar keeps to one row.
		const header = (await page.getByRole('banner').boundingBox())!;
		expect(header.height, `${width} px`).toBeLessThan(110);
	}
	await expect(cancelSolve(page).getByText('Cancel', { exact: true })).toBeVisible();
});

test('Cancel works from the keyboard, and the focus returns to Solve', async ({ page }) => {
	await openExample(page);
	await hold(page, '/api/v1/solve');
	await solveButton(page).focus();
	await page.keyboard.press('Enter');
	await expect(cancelSolve(page)).toBeVisible();
	// Just before Solve in the tab order (it comes in to Solve's left, so that Solve keeps its place).
	await page.keyboard.press('Shift+Tab');
	await expect(cancelSolve(page)).toBeFocused();
	const abort = aborted(page, '/api/v1/solve');
	await page.keyboard.press('Enter');
	await abort;
	await expect(cancelSolve(page)).toBeHidden();
	await expect(solveButton(page)).toBeFocused();
	await expect(status(page)).toHaveText('Solve cancelled');
});

test('a double click (or tap) on Solve does not cancel it, nor one on Cancel solve again', async ({
	page
}, testInfo) => {
	await openExample(page);
	const held = await hold(page, '/api/v1/solve');
	const before = (await solveButton(page).boundingBox())!;
	await solveButton(page).dblclick();
	await expect(cancelSolve(page)).toBeVisible();
	await expect(status(page)).toHaveText('Solving…');
	// Solve keeps its place and size; Cancel comes in to its left, clear of it.
	const solving = page.getByRole('button', { name: 'Solving…' });
	expect(await solving.boundingBox()).toEqual(before);
	const cancel = (await cancelSolve(page).boundingBox())!;
	expect(cancel.x + cancel.width).toBeLessThanOrEqual(before.x);
	expect(held).toHaveLength(1);

	const abort = aborted(page, '/api/v1/solve');
	await cancelSolve(page).dblclick();
	await abort;
	await expect(status(page)).toHaveText('Solve cancelled');
	await expect(cancelSolve(page)).toBeHidden();
	expect(held).toHaveLength(1);

	if (testInfo.project.name === 'mobile') {
		// Two taps in quick succession on Solve.
		const x = before.x + before.width / 2;
		const y = before.y + before.height / 2;
		await page.touchscreen.tap(x, y);
		await page.touchscreen.tap(x, y);
		await expect(cancelSolve(page)).toBeVisible();
		await expect(status(page)).toHaveText('Solving…');
		expect(held).toHaveLength(2);
	}
});

test('a cancelled solve keeps the earlier results, out of date once the project changed', async ({
	page
}) => {
	await openExample(page);
	await solveConverged(page);
	const note =
		'The solve was cancelled before it finished. What is shown below is from an earlier solve.';

	// Solved again unchanged, and cancelled: the results are still the project's, as they were.
	await hold(page, '/api/v1/solve');
	await solveButton(page).click();
	await cancelSolve(page).click();
	await expect(status(page)).toHaveText('Solve cancelled. Last finished solve: converged');
	await expect(resultsPane(page).getByText(note)).toBeVisible();
	await expect(resultsPane(page).getByRole('heading', { name: 'Converged' })).toBeVisible();
	await expect(resultsPane(page).getByText(/Results are out of date/)).toHaveCount(0);

	// Changed (the pump's speed), solved and cancelled: out of date, as after any change.
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: /^Next/ }).click();
	await expect(currentHeading(page)).toHaveText('Transfer pump');
	await setNumber(buildPane(page), 'Speed (%)', '90');
	await solveButton(page).click();
	await cancelSolve(page).click();
	await showPane(page, 'Results');
	await expect(status(page)).toHaveText(
		'Solve cancelled. Last finished solve: converged, out of date'
	);
	await expect(resultsPane(page).getByText(note)).toBeVisible();
	await expect(
		resultsPane(page).getByText(/^Results are out of date: the project changed after this solve\./)
	).toBeVisible();
	await expect(resultsPane(page).getByRole('heading', { name: 'Converged' })).toBeVisible();
	expect(await sidewaysScroll(page)).toBe(0);
});

test('cancel a system curve: the request is aborted, the chart says so, and computes it on request', async ({
	page
}) => {
	await openExample(page);
	await solveConverged(page);
	const held = await hold(page, '/api/v1/system-curve');
	const sent = page.waitForRequest((r) => r.url().endsWith('/api/v1/system-curve'));
	const pumps = await resultsView(page, 'Pumps');
	await sent;
	const chart = pumps.getByRole('figure', { name: 'Pump and system curves: Transfer pump' });
	await expect(chart).toHaveAttribute('aria-busy', 'true');
	await expect(chart.getByText('Computing the system curve for this solve…')).toBeVisible();
	const cancel = chart.getByRole('button', { name: 'Cancel the system curve' });
	await expect(cancel).toHaveText('Cancel');
	expect(await sidewaysScroll(page)).toBe(0);

	const abort = aborted(page, '/api/v1/system-curve');
	await cancel.click();
	expect((await abort).failure()?.errorText).toBe('net::ERR_ABORTED');
	expect(held).toHaveLength(1);
	const again = chart.getByRole('button', { name: 'Compute the system curve' });
	await expect(again).toBeFocused();
	await expect(again).toHaveAccessibleDescription(
		'The system curve was not computed: you cancelled it.'
	);
	await expect(chart).toHaveAttribute('aria-busy', 'false');
	await expect(chart.getByRole('img')).not.toHaveAccessibleName(/system curve/);
	// The results of the solve are unchanged.
	await expect(status(page)).toHaveText('Last solve: converged');

	// Computed on request, let through: the curve is drawn.
	await page.unroute('**/api/v1/system-curve');
	const answer = page.waitForResponse((r) => r.url().endsWith('/api/v1/system-curve'));
	await again.click();
	expect((await answer).status()).toBe(200);
	await expect(chart.getByRole('img')).toHaveAccessibleName(/ and system curve; operating point /);
	await expect(chart.getByText(/^System curve: /)).toBeVisible();
});

test('the system curve: Cancel and the button that computes it again hand the focus to each other', async ({
	page
}) => {
	await openExample(page);
	await solveConverged(page);
	await hold(page, '/api/v1/system-curve');
	const pumps = await resultsView(page, 'Pumps');
	const chart = pumps.getByRole('figure', { name: 'Pump and system curves: Transfer pump' });
	const cancel = chart.getByRole('button', { name: 'Cancel the system curve' });
	const again = chart.getByRole('button', { name: 'Compute the system curve' });
	await cancel.focus();
	await page.keyboard.press('Enter');
	await expect(again).toBeFocused();
	await page.keyboard.press('Enter');
	await expect(cancel).toBeFocused();
	await expect(chart).toHaveAttribute('aria-busy', 'true');

	// A failure (made-up server error): Try again takes the focus, and gives it back to Cancel.
	await page.keyboard.press('Enter');
	await expect(again).toBeFocused();
	await page.unroute('**/api/v1/system-curve');
	await page.route('**/api/v1/system-curve', (route) =>
		route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
	);
	await page.keyboard.press('Enter');
	const retry = chart.getByRole('button', { name: 'Try again' });
	await expect(retry).toBeFocused();
	await page.unroute('**/api/v1/system-curve');
	await hold(page, '/api/v1/system-curve');
	await page.keyboard.press('Enter');
	await expect(cancel).toBeFocused();
});
