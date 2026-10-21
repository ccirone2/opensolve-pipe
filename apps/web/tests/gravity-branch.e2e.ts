import { expect, test } from '@playwright/test';
import {
	addAfter,
	addFirst,
	buildPane,
	cellText,
	closeTrace,
	currentHeading,
	halfUlp,
	newProject,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	sig4,
	solveConverged,
	traceOf
} from './support';

/**
 * A gravity-fed branched network, built through the panel navigator, with no pump:
 *
 *   Reservoir R1 (30 m) → 100 m pipe → Tee T1 (0 m) ─ run outlet → 10 m pipe → Reservoir R2 (5 m)
 *                                                  └ branch → 10 m pipe → Globe valve V1 (0 m)
 *                                                               → 10 m pipe → Reservoir R3 (0 m)
 *
 * Illustrative test input (made-up elevations and lengths); pipes are the default carbon steel
 * schedule 40, NPS 4, and the tee uses the Crane TP-410 loss model (the default).
 */
const MAIN = 'Reservoir R1 → Tee T1';
const RUN = 'Tee T1 → Reservoir R2';
const BRANCH = 'Tee T1 → Globe valve V1';
const BRANCH_ON = 'Globe valve V1 → Reservoir R3';

test('a gravity-fed branched network: both branches flow, and their flows add up', async ({
	page
}) => {
	await newProject(page);
	const panel = buildPane(page);

	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await setNumber(panel, /^Elevation/, '30');

	// The tee after the elevated reservoir, at ground level; the main pipe is 100 m long.
	await addAfter(page, 'Tee', 'Tee T1');
	await setNumber(panel, /^Elevation/, '0');
	await panel.getByRole('tab', { name: 'Piping' }).click();
	const ports = panel.getByRole('group', { name: 'Ports of Tee T1' });
	await ports.getByRole('button', { name: /^Run inlet/ }).click();
	await expect(ports.getByRole('button', { name: /^Run inlet/ })).toHaveAttribute(
		'aria-pressed',
		'true'
	);
	await setNumber(panel, /^Length/, '100');

	// Next leads to the tee's free run outlet: connect a reservoir there.
	const next = panel.getByRole('button', { name: /^Next/ });
	await expect(next).toHaveText('Next: connect run outlet');
	await next.click();
	await expect(panel.getByRole('heading', { name: 'Run outlet is not connected' })).toBeVisible();
	await panel
		.getByRole('combobox', { name: 'Add a component here' })
		.selectOption({ label: 'Reservoir' });
	await panel.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Reservoir R2');
	await setNumber(panel, /^Elevation/, '5');

	// Back to the tee, and the branch through a globe valve to a third reservoir.
	await panel.getByRole('button', { name: /^Previous/ }).click();
	await expect(currentHeading(page)).toHaveText('Tee T1');
	await panel.getByRole('tab', { name: 'Piping' }).click();
	await ports.getByRole('button', { name: /^Branch/ }).click();
	await expect(panel.getByRole('heading', { name: 'Branch is not connected' })).toBeVisible();
	await panel
		.getByRole('combobox', { name: 'Add a component here' })
		.selectOption({ label: 'Globe valve' });
	await panel.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Globe valve V1');
	await addAfter(page, 'Reservoir', 'Reservoir R3');
	await expect(panel.getByRole('textbox', { name: /^Elevation/ })).toHaveValue('0');
	await expect(page.getByRole('navigation', { name: 'Path' }).getByRole('button')).toHaveText([
		'Reservoir R1',
		'Tee T1',
		'Globe valve V1',
		'Reservoir R3'
	]);

	// Solve: no pump, gravity alone.
	const solved = await solveConverged(page);
	expect(Object.keys(solved.pumpResults)).toEqual([]);
	await showPane(page, 'Results');
	await expect(resultsPane(page).getByRole('heading', { name: /^Flags/ })).toHaveCount(0);
	await expect(
		resultsPane(page).getByRole('tablist', { name: 'Results view' }).getByRole('tab')
	).toHaveText(['Summary', 'Nodes', 'Links', 'Valves', 'Branches', 'Boundaries', 'Methods']);

	// Links: both branches flow away from the tee, and together carry the main flow.
	const links = (await resultsView(page, 'Links')).getByRole('table', {
		name: 'Results per pipe connection'
	});
	const main = await cellText(links, MAIN, 'Flow L/s');
	const run = await cellText(links, RUN, 'Flow L/s');
	const branch = await cellText(links, BRANCH, 'Flow L/s');
	expect(Number(main)).toBeGreaterThan(0);
	expect(Number(run)).toBeGreaterThan(0);
	expect(Number(branch)).toBeGreaterThan(0);
	const rounding = halfUlp(main) + halfUlp(run) + halfUlp(branch);
	expect(Math.abs(Number(run) + Number(branch) - Number(main))).toBeLessThanOrEqual(rounding);
	expect(await cellText(links, BRANCH_ON, 'Flow L/s')).toBe(branch);
	// As the API reported them.
	expect(main).toBe(sig4(solved.linkResults.L1!.flow * 1000));

	// The tee's result: pattern, the flow at each port (+ into the tee), and K per path.
	const branches = (await resultsView(page, 'Branches')).getByRole('table', {
		name: 'Results per tee and wye'
	});
	expect(await cellText(branches, 'Tee T1', 'Flow pattern')).toBe('Diverging from run inlet');
	expect(await cellText(branches, 'Tee T1', 'Port flows (+ in) L/s')).toBe(
		`Run inlet ${main} Run outlet -${run} Branch -${branch}`
	);
	expect(await cellText(branches, 'Tee T1', 'K per path')).toMatch(
		/^Run outlet \d+(\.\d+)? Branch \d+(\.\d+)?$/
	);
	expect(await cellText(branches, 'Tee T1', 'Correlation')).toContain('Crane Co. TP-410');

	// The globe valve is open and passes the branch flow.
	const valves = (await resultsView(page, 'Valves')).getByRole('table', {
		name: 'Results per valve'
	});
	expect(await cellText(valves, 'Globe valve V1', 'Flow (+ inlet → outlet) L/s')).toBe(branch);
	expect(await cellText(valves, 'Globe valve V1', 'State')).toBe('Open');

	// The boundaries: R1 supplies the main flow, R2 and R3 take the branch flows.
	const boundaries = (await resultsView(page, 'Boundaries')).getByRole('table', {
		name: 'Results per boundary'
	});
	expect(await cellText(boundaries, 'Reservoir R1', 'Outflow (+ into network) L/s')).toBe(main);
	expect(await cellText(boundaries, 'Reservoir R2', 'Outflow (+ into network) L/s')).toBe(
		`-${run}`
	);
	expect(await cellText(boundaries, 'Reservoir R3', 'Outflow (+ into network) L/s')).toBe(
		`-${branch}`
	);

	// The tee's trace names the correlation and its source.
	await resultsView(page, 'Branches');
	await branches.getByRole('button', { name: /^Tee T1/ }).click();
	const trace = traceOf(page, 'Tee T1');
	await expect(trace).toBeVisible();
	await expect(trace.getByRole('heading', { name: 'Correlations' })).toBeVisible();
	await expect(trace.getByText(/Crane/).first()).toBeVisible();
	await closeTrace(page, 'Tee T1');
});
