/**
 * Helpers shared by the end-to-end flows: the workspace panes, building a network through the
 * panel navigator, solving against the real API, and reading the results tables as displayed.
 * Selectors are accessible roles and names only.
 */
import { expect, type Locator, type Page } from '@playwright/test';
import type { ErrorResponse, SolvedState, SolveRequest, SolveResponse } from '../src/lib/api/types';
import { API_ORIGIN, WEB_ORIGIN } from './servers';

export const buildPane = (page: Page) => page.getByRole('region', { name: 'Build', exact: true });
export const resultsPane = (page: Page) =>
	page.getByRole('region', { name: 'Results', exact: true });

/** The panel navigator's current component heading. */
export const currentHeading = (page: Page) => buildPane(page).getByRole('heading', { level: 2 });

/**
 * Show a pane. On narrow screens Build and Results are tabs; on wide ones both are shown and
 * the tabs are hidden.
 */
export async function showPane(page: Page, pane: 'Build' | 'Results'): Promise<void> {
	const tab = page
		.getByRole('tablist', { name: 'View' })
		.getByRole('tab', { name: new RegExp(`^${pane}`) });
	if (await tab.isVisible()) await tab.click();
	await expect(pane === 'Build' ? buildPane(page) : resultsPane(page)).toBeVisible();
}

/** Start a new, empty project from the home page. */
export async function newProject(page: Page): Promise<void> {
	await page.goto('/');
	await page.getByRole('link', { name: 'New project' }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(buildPane(page).getByRole('heading', { name: 'Start the network' })).toBeVisible();
}

/** Add the first component of an empty project ("Reservoir", "Gate valve", ...). */
export async function addFirst(page: Page, kind: string, name: string): Promise<void> {
	const panel = buildPane(page);
	await panel.getByRole('combobox', { name: 'First component' }).selectOption({ label: kind });
	await panel.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText(name);
}

/**
 * Add a component after the current one, at its free port (Add after), and check the navigator
 * walked on to it.
 */
export async function addAfter(page: Page, kind: string, name: string): Promise<void> {
	await buildPane(page).getByRole('button', { name: 'Add after' }).click();
	const dialog = page.getByRole('dialog', { name: /^Add after/ });
	await expect(dialog.getByRole('radio', { name: /^At a free port/ })).toBeChecked();
	await dialog.getByRole('combobox', { name: 'Component' }).selectOption({ label: kind });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog).toBeHidden();
	await expect(currentHeading(page)).toHaveText(name);
}

/** Type a number into a unit-aware field and store it (Enter). */
export async function setNumber(scope: Locator, name: string | RegExp, value: string) {
	const field = scope.getByRole('textbox', { name });
	await field.fill(value);
	await field.press('Enter');
	await expect(field).toHaveValue(value);
	await expect(field).not.toHaveAttribute('aria-invalid', 'true');
}

/** The API's answer to a solve: a SolveResponse (200) or an ErrorResponse (e.g. 422). */
export interface SolveAnswer {
	status: number;
	body: Partial<SolveResponse> & Partial<ErrorResponse>;
	/** What the app sent: the project and the solve options. */
	request: SolveRequest;
}

/**
 * Press the header's Solve and wait for the API's answer. In a project with scenarios the button
 * names the case shown, the base case when a link has just been opened (D15).
 */
export async function solve(page: Page): Promise<SolveAnswer> {
	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await page
		.getByRole('banner')
		.getByRole('button', { name: /^Solve( Base case)?$/ })
		.click();
	const response = await answer;
	return {
		status: response.status(),
		body: (await response.json()) as SolveAnswer['body'],
		request: response.request().postDataJSON() as SolveRequest
	};
}

/**
 * Solve, and check the solve converged and its results are shown. The app solves without system
 * curves (D10: the pump chart fetches the one it shows).
 */
export async function solveConverged(page: Page): Promise<SolvedState> {
	const { status, body, request } = await solve(page);
	expect(request.options?.includeSystemCurve).toBe(false);
	expect(status, JSON.stringify(body).slice(0, 500)).toBe(200);
	expect(body.success).toBe(true);
	expect(body.solvedState?.converged).toBe(true);
	await expect(resultsPane(page).getByRole('heading', { name: 'Converged' })).toBeVisible();
	await expect(resultsPane(page).getByRole('status')).toHaveText('Last solve: converged');
	return body.solvedState!;
}

/** Show one of the results views (Summary, Nodes, Links, Pumps, ...). */
export async function resultsView(page: Page, view: string): Promise<Locator> {
	const tab = resultsPane(page)
		.getByRole('tablist', { name: 'Results view' })
		.getByRole('tab', { name: view, exact: true });
	await tab.click();
	await expect(tab).toHaveAttribute('aria-selected', 'true');
	return resultsPane(page).getByRole('tabpanel', { name: view, exact: true });
}

const squash = (text: string) => text.replace(/\s+/g, ' ').trim();

/**
 * The displayed text of a results-table cell: the row whose header starts with `row`, in the
 * column whose heading (label and unit) is `column`, e.g. ("Reservoir R1 → Pump P1", "Flow L/s").
 */
export async function cellText(table: Locator, row: string, column: string): Promise<string> {
	await expect(table.getByRole('row').first()).toBeVisible();
	const headings = (await table.getByRole('columnheader').allInnerTexts()).map(squash);
	const index = headings.indexOf(column);
	expect(index, `column “${column}” in ${JSON.stringify(headings)}`).toBeGreaterThan(0);
	const match = table
		.getByRole('row')
		.filter({ has: table.page().getByRole('rowheader', { name: row }) });
	await expect(match).toHaveCount(1);
	return squash(
		await match
			.getByRole('cell')
			.nth(index - 1)
			.innerText()
	);
}

/**
 * An element's text as the app tells it (a topology issue, a system-curve point's reason): without
 * the calculation server's own messages, which it keeps under Details.
 */
export async function toldText(locator: Locator): Promise<string> {
	return squash(
		await locator.evaluate((element) => {
			const copy = element.cloneNode(true) as HTMLElement;
			copy.querySelectorAll('[data-issue-detail]').forEach((detail) => detail.remove());
			return copy.textContent ?? '';
		})
	);
}

/** Every row of a table as displayed (headers and cells), to compare two solves. */
export async function tableTexts(table: Locator): Promise<string[]> {
	await expect(table.getByRole('row').first()).toBeVisible();
	return (await table.getByRole('row').allInnerTexts()).map(squash);
}

/** A number as shown in the results: 4 significant figures. */
export const sig4 = (value: number) => String(Number(value.toPrecision(4)));
/** Rounded toward zero to 4 significant digits: how a bound a value must stay below is shown. */
export const down4 = (value: number) => {
	const scale = 10 ** (3 - Math.floor(Math.log10(Math.abs(value))));
	return String(Math.trunc(value * scale) / scale);
};

/**
 * Half a unit in the last displayed digit of a number shown as `text` ("12.81" → 0.005): the
 * rounding a displayed value can carry.
 */
export function halfUlp(text: string): number {
	const decimals = text.split('.')[1]?.length ?? 0;
	return 0.5 * 10 ** -decimals;
}

/** The trace of an element: a panel over the results (wide screens) or a dialog (narrow). */
export function traceOf(page: Page, name: string): Locator {
	return page
		.getByRole('dialog', { name, exact: true })
		.or(resultsPane(page).getByRole('region', { name, exact: true }))
		.first();
}

/** Close an element's trace (its close button) and check it is gone. */
export async function closeTrace(page: Page, name: string): Promise<void> {
	const trace = traceOf(page, name);
	await trace.getByRole('button', { name: 'Close', exact: true }).click();
	await expect(traceOf(page, name)).toBeHidden();
}

/** Origins the app may contact: itself and its calculation server (GOALS §4.5). */
export const ALLOWED_ORIGINS = new Set([WEB_ORIGIN, API_ORIGIN]);
