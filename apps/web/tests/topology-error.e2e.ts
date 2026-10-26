import { expect, test, type Page } from '@playwright/test';
import {
	addAfter,
	addFirst,
	buildPane,
	cellText,
	currentHeading,
	newProject,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	sig4,
	solve,
	solveConverged,
	toldText
} from './support';

/**
 * Networks the solver cannot solve as connected: Solve lists the calculation server's topology
 * issues, told with component and port names, each issue links back to its components in the
 * panel navigator, and once the network is fixed it solves. Illustrative test inputs (made-up
 * elevations); default pipes.
 */

const issuesSection = (page: Page) =>
	resultsPane(page).getByRole('region', { name: 'The network cannot be solved yet' });

/** Solve, expecting the API's topology error, and return the issues it listed. */
async function solveWithTopologyError(page: Page) {
	const { status, body } = await solve(page);
	expect(status).toBe(422);
	expect(body.error).toBe('TOPOLOGY_ERROR');
	await expect(issuesSection(page)).toBeVisible();
	await expect(resultsPane(page).getByRole('status')).toHaveText('Last solve: no results');
	await expect(resultsPane(page).getByRole('heading', { name: 'Converged' })).toHaveCount(0);
	return body.issues ?? [];
}

/** Open a port's piping view of the current component (Piping tab, then the port). */
async function openPort(page: Page, component: string, port: string) {
	const panel = buildPane(page);
	await panel.getByRole('tab', { name: 'Piping' }).click();
	const button = panel
		.getByRole('group', { name: `Ports of ${component}` })
		.getByRole('button', { name: new RegExp(`^${port}`) });
	await button.click();
	await expect(button).toHaveAttribute('aria-pressed', 'true');
}

/** Add a component at the current component's free port, from its piping view. */
async function addHere(page: Page, port: string, kind: string, name: string) {
	const panel = buildPane(page);
	await expect(panel.getByRole('heading', { name: `${port} is not connected` })).toBeVisible();
	await panel.getByRole('combobox', { name: 'Add a component here' }).selectOption({ label: kind });
	await panel.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText(name);
}

/** Follow an issue's link to a component: the navigator shows that component. */
async function followIssueLink(page: Page, issue: number, component: string) {
	await showPane(page, 'Results');
	await issuesSection(page)
		.getByRole('listitem')
		.nth(issue)
		.getByRole('button', { name: component, exact: true })
		.click();
	await expect(buildPane(page)).toBeVisible();
	await expect(currentHeading(page)).toHaveText(component);
}

test('a network without a reservoir: each topology issue links to its components, and the fixed network solves', async ({
	page
}) => {
	await newProject(page);
	await addFirst(page, 'Gate valve', 'Gate valve V1');
	await addAfter(page, 'Gate valve', 'Gate valve V2');

	// The browser already lists the problems it can see; solving is not blocked.
	await showPane(page, 'Results');
	await expect(
		resultsPane(page).getByRole('heading', { name: 'Inputs to check (3)' })
	).toBeVisible();

	const issues = await solveWithTopologyError(page);
	expect(issues.map((i) => [i.code, i.componentIds])).toEqual([
		['UNCONNECTED_PORT', ['V1']],
		['UNCONNECTED_PORT', ['V2']],
		['NO_FIXED_HEAD', ['V1', 'V2']]
	]);
	// Each issue is told with names, chosen by its code and ids (not the server's id-based text).
	await expect(issuesSection(page)).toContainText(
		'3 problems to fix before the network can be solved:'
	);
	const items = issuesSection(page).getByRole('listitem');
	await expect(items).toHaveCount(3);
	await expect(items.nth(0)).toContainText(
		'Inlet of Gate valve V1 is not connected: connect it or add a plug.'
	);
	await expect(items.nth(1)).toContainText(
		'Outlet of Gate valve V2 is not connected: connect it or add a plug.'
	);
	await expect(items.nth(2)).toContainText(
		'This part of the network has no fixed-pressure boundary: add a reservoir or reference node to it.'
	);
	// The server's own message is kept, under Details (closed).
	for (const [i, issue] of issues.entries()) {
		expect(await toldText(items.nth(i))).not.toContain(issue.message);
		const details = items.nth(i).locator('details');
		await expect(details).not.toHaveAttribute('open');
		await expect(details).toContainText(`Calculation server's message: ${issue.message}`);
	}
	await items.nth(0).getByText('Details', { exact: true }).click();
	await expect(
		items.nth(0).getByText(`Calculation server's message: ${issues[0]!.message}`)
	).toBeVisible();
	await expect(items.nth(0).getByRole('button')).toHaveText(['Gate valve V1']);
	await expect(items.nth(1).getByRole('button')).toHaveText(['Gate valve V2']);
	await expect(items.nth(2).getByRole('button')).toHaveText(['Gate valve V1', 'Gate valve V2']);

	// Every link of every issue opens its component in the navigator.
	for (const [i, names] of [
		[0, ['Gate valve V1']],
		[1, ['Gate valve V2']],
		[2, ['Gate valve V1', 'Gate valve V2']]
	] as const) {
		for (const name of names) await followIssueLink(page, i, name);
	}

	// Fix: a reservoir at each open end, the upstream one 10 m higher.
	await followIssueLink(page, 0, 'Gate valve V1');
	await openPort(page, 'Gate valve V1', 'Inlet');
	await addHere(page, 'Inlet', 'Reservoir', 'Reservoir R1');
	await setNumber(buildPane(page), /^Elevation/, '10');
	await followIssueLink(page, 1, 'Gate valve V2');
	await openPort(page, 'Gate valve V2', 'Outlet');
	await addHere(page, 'Outlet', 'Reservoir', 'Reservoir R2');
	await expect(buildPane(page).getByRole('textbox', { name: /^Elevation/ })).toHaveValue('0');

	// The error's results are now out of date; solving again succeeds.
	await showPane(page, 'Results');
	await expect(resultsPane(page).getByText(/^Results are out of date/)).toBeVisible();
	await expect(resultsPane(page).getByRole('heading', { name: /^Inputs to check/ })).toHaveCount(0);
	const solved = await solveConverged(page);
	await expect(issuesSection(page)).toHaveCount(0);
	// L1 joins the two valves (the first connection made); the flow runs from R1 down to R2.
	const flow = solved.linkResults.L1!.flow;
	expect(flow).toBeGreaterThan(0);
	const links = (await resultsView(page, 'Links')).getByRole('table', {
		name: 'Results per pipe connection'
	});
	const shown = await cellText(links, 'Gate valve V1 → Gate valve V2', 'Flow L/s');
	expect(shown).toBe(sig4(flow * 1000));
	expect(await cellText(links, 'Reservoir R1 → Gate valve V1', 'Flow L/s')).toBe(shown);
	expect(await cellText(links, 'Gate valve V2 → Reservoir R2', 'Flow L/s')).toBe(shown);
});

test('an unconnected tee branch: the issue links to the tee, and plugging the port fixes it', async ({
	page
}) => {
	await newProject(page);
	const panel = buildPane(page);
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await setNumber(panel, /^Elevation/, '10');
	await addAfter(page, 'Tee', 'Tee T1');
	await panel.getByRole('button', { name: 'Next: connect run outlet' }).click();
	await addHere(page, 'Run outlet', 'Reservoir', 'Reservoir R2');
	await setNumber(panel, /^Elevation/, '0');

	const issues = await solveWithTopologyError(page);
	expect(issues.map((i) => [i.code, i.componentIds])).toEqual([['UNCONNECTED_PORT', ['T1']]]);
	const item = issuesSection(page).getByRole('listitem');
	await expect(item).toHaveCount(1);
	await expect(item).toContainText('Branch of Tee T1 is not connected: connect it or add a plug.');

	// The issue's link opens the tee; plug its free branch port there.
	await followIssueLink(page, 0, 'Tee T1');
	await openPort(page, 'Tee T1', 'Branch');
	await expect(panel.getByRole('heading', { name: 'Branch is not connected' })).toBeVisible();
	await panel.getByRole('button', { name: 'Plug this port' }).click();
	await expect(
		panel.getByRole('group', { name: 'Ports of Tee T1' }).getByRole('button', { name: /^Branch/ })
	).toHaveText(/to Plug PL1/);
	await expect(panel.getByRole('heading', { name: 'Branch is not connected' })).toHaveCount(0);

	const solved = await solveConverged(page);
	await expect(issuesSection(page)).toHaveCount(0);
	expect(solved.linkResults.L1!.flow).toBeGreaterThan(0);
	const links = (await resultsView(page, 'Links')).getByRole('table', {
		name: 'Results per pipe connection'
	});
	const main = await cellText(links, 'Reservoir R1 → Tee T1', 'Flow L/s');
	expect(Number(main)).toBeGreaterThan(0);
	expect(await cellText(links, 'Tee T1 → Reservoir R2', 'Flow L/s')).toBe(main);
	// The plugged branch is a dead end: no flow.
	expect(await cellText(links, 'Tee T1 → Plug PL1', 'Flow L/s')).toBe('0');
});
