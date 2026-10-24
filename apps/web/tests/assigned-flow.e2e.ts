import { expect, test, type Page } from '@playwright/test';
import type { SolvedState } from '../src/lib/api/types';
import {
	addFirst,
	ALLOWED_ORIGINS,
	buildPane,
	cellText,
	currentHeading,
	halfUlp,
	newProject,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	sig4,
	solveConverged,
	tableTexts
} from './support';

/**
 * An assigned-flow node (SDD §4.11) built through the panel navigator and solved against the
 * real API, on desktop and mobile:
 *
 *   Reservoir R1 (0 m, liquid level 20 m) → 10 m pipe, NPS 4 → Assigned flow AF1 (0 m)
 *
 * Illustrative test inputs (made-up level and flow); the pipe is the default carbon steel
 * schedule 40 with the default sharp entrance at the reservoir. The node has no default flow, so
 * it is entered where the node is added. As a demand of 5 L/s the reservoir supplies it; switched
 * to a supply of 5 L/s the flow runs back into the reservoir. Either way the pipe carries the
 * assigned flow, the energy grade line falls along the flow by the pipe's head loss (read from
 * the displayed results), and the node's static pressure is below the reservoir's static head
 * ρ·g·20 m for the demand and above it for the supply.
 */
const LEVEL = 20; // m
const FLOW = '5'; // L/s
const G = 9.80665; // m/s², standard gravity (a defined value)
const LINK = 'Reservoir R1 → Assigned flow AF1';
const REQUIRED = 'Enter the flow: an assigned-flow node has no default flow.';

interface Shown {
	assigned: string[];
	pressure: number;
	density: number;
}

/** Read the solve's results as displayed and check them against the solve and each other. */
async function readResults(page: Page, solved: SolvedState, direction: 'Demand' | 'Supply') {
	await showPane(page, 'Results');
	await expect(
		resultsPane(page).getByRole('tablist', { name: 'Results view' }).getByRole('tab')
	).toHaveText(['Summary', 'Nodes', 'Links', 'Boundaries', 'Assigned flows', 'Methods']);
	await expect(resultsPane(page).getByRole('heading', { name: /^Flags/ })).toHaveCount(0);
	const node = solved.nodeResults['AF1:port_1']!;
	const sign = direction === 'Demand' ? '' : '-';

	// The node's own table: the flow as entered, its static pressure and HGL.
	const assigned = (await resultsView(page, 'Assigned flows')).getByRole('table', {
		name: 'Results per assigned-flow node'
	});
	expect(await cellText(assigned, 'Assigned flow AF1', 'Direction')).toBe(direction);
	expect(await cellText(assigned, 'Assigned flow AF1', 'Assigned flow L/s')).toBe(FLOW);
	const pressure = await cellText(assigned, 'Assigned flow AF1', 'Pressure kPa(g)');
	expect(pressure).toBe(sig4(node.pressure / 1000));
	expect(await cellText(assigned, 'Assigned flow AF1', 'HGL m')).toBe(
		String(Number(node.hgl.toFixed(2)))
	);
	const rows = await tableTexts(assigned);

	// The pipe carries the assigned flow; the reservoir supplies (or takes) it.
	const links = (await resultsView(page, 'Links')).getByRole('table', {
		name: 'Results per pipe connection'
	});
	expect(await cellText(links, LINK, 'Flow L/s')).toBe(`${sign}${FLOW}`);
	const loss = await cellText(links, LINK, 'Head loss m');
	const boundaries = (await resultsView(page, 'Boundaries')).getByRole('table', {
		name: 'Results per boundary'
	});
	expect(await cellText(boundaries, 'Reservoir R1', 'Outflow (+ into network) L/s')).toBe(
		`${sign}${FLOW}`
	);
	await expect(boundaries.getByRole('rowheader')).toHaveCount(1);

	// Energy along the pipe, from the numbers shown: EGL(R1) − EGL(AF1) = head loss (from → to).
	const nodes = (await resultsView(page, 'Nodes')).getByRole('table', {
		name: 'Results per component port'
	});
	const eglR1 = await cellText(nodes, 'Reservoir R1', 'EGL m');
	const eglAF1 = await cellText(nodes, 'Assigned flow AF1', 'EGL m');
	expect(Number(eglR1)).toBe(LEVEL);
	const rounding = halfUlp(eglR1) + halfUlp(eglAF1) + halfUlp(loss);
	expect(Math.abs(Number(eglR1) - Number(eglAF1) - Number(loss))).toBeLessThanOrEqual(rounding);
	expect(await cellText(nodes, 'Assigned flow AF1', 'Pressure kPa(g)')).toBe(pressure);
	return { assigned: rows, pressure: node.pressure, density: solved.fluid.density } as Shown;
}

test('add an assigned-flow node, solve, read its pressure, switch to supply, share and reopen', async ({
	page,
	context
}) => {
	const origins = new Set<string>();
	context.on('request', (request) => origins.add(new URL(request.url()).origin));
	await newProject(page);
	const panel = buildPane(page);
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await setNumber(panel, /^Liquid level/, String(LEVEL));

	// --- Add the node after the reservoir: it is added only with its flow.
	await panel.getByRole('button', { name: 'Add after' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add after Reservoir R1' });
	await dialog
		.getByRole('combobox', { name: 'Component' })
		.selectOption({ label: 'Assigned flow (demand or supply)' });
	await expect(dialog.getByRole('combobox', { name: 'Direction' })).toHaveValue('demand');
	const flow = dialog.getByRole('textbox', { name: 'Flow (L/s)' });
	await expect(flow).toHaveValue('');
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog.getByRole('alert')).toHaveText(REQUIRED);
	await expect(flow).toHaveAttribute('aria-invalid', 'true');
	await setNumber(dialog, 'Flow (L/s)', FLOW);
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog).toBeHidden();
	await expect(currentHeading(page)).toHaveText('Assigned flow AF1');
	// One port, connected: the walk ends here, as at a plug.
	await expect(panel.getByRole('button', { name: /^Next/ })).toHaveText('Next: end of path');
	await expect(panel.getByRole('button', { name: /^Next/ })).toBeDisabled();

	// --- Solve as a demand, and read the node's pressure.
	const demand = await solveConverged(page);
	const demandShown = await readResults(page, demand, 'Demand');
	const staticHead = demandShown.density * G * LEVEL; // Pa, the reservoir's static head at 0 m
	expect(demandShown.pressure).toBeLessThan(staticHead);

	// --- Switch it to a supply: only the sign changes.
	await showPane(page, 'Build');
	await expect(currentHeading(page)).toHaveText('Assigned flow AF1');
	await panel
		.getByRole('combobox', { name: 'Direction' })
		.selectOption({ label: 'Supply (enters the network)' });
	await expect(panel.getByRole('textbox', { name: 'Flow (L/s)' })).toHaveValue(FLOW);
	const supplySent = page.waitForRequest(
		(r) => r.url().endsWith('/api/v1/solve') && r.method() === 'POST'
	);
	const supply = await solveConverged(page);
	const request = (await supplySent).postDataJSON() as { project: { components: unknown[] } };
	expect(request.project.components).toContainEqual(
		expect.objectContaining({ id: 'AF1', type: 'assigned_flow', flow: -0.005 })
	);
	const supplyShown = await readResults(page, supply, 'Supply');
	expect(supplyShown.pressure).toBeGreaterThan(staticHead);

	// --- Share, reopen: the link holds the supply, and solves to the same results.
	await page.getByRole('button', { name: 'Share' }).click();
	const share = page.getByRole('dialog', { name: 'Share this project' });
	const link = await share
		.getByRole('textbox', { name: 'Link to this version of the project' })
		.inputValue();
	await share.getByRole('button', { name: 'Close' }).click();
	const reopened = await context.newPage();
	await reopened.goto(link);
	await expect(currentHeading(reopened)).toHaveText('Reservoir R1');
	const again = await solveConverged(reopened);
	expect(again.nodeResults['AF1:port_1']!.pressure).toBeCloseTo(
		supply.nodeResults['AF1:port_1']!.pressure,
		6
	);
	await showPane(reopened, 'Results');
	const table = (await resultsView(reopened, 'Assigned flows')).getByRole('table', {
		name: 'Results per assigned-flow node'
	});
	expect(await tableTexts(table)).toEqual(supplyShown.assigned);
	await reopened.close();

	// Nothing but the app and its calculation server was contacted (GOALS §4.5).
	expect([...origins].filter((o) => !ALLOWED_ORIGINS.has(o))).toEqual([]);
});

// The field stores what was typed when it loses focus, which the press on Add does; nothing may
// then move under the pointer before the release, or the click lands off the button and nothing
// is added (no Enter is pressed here). Both places that add a node with its flow below it: the
// first component of a project, and a free port; after the "Enter the flow" error, and with a
// flow of 0 (which has a note of its own).
for (const where of ['first component', 'free port'] as const) {
	for (const { value, error } of [
		{ value: FLOW, error: true },
		{ value: '0', error: false }
	]) {
		test(`a flow of ${value} L/s typed at the ${where}${error ? ' after the error' : ''} is added by the first click on Add`, async ({
			page
		}) => {
			const panel = buildPane(page);
			const add = panel.getByRole('button', { name: 'Add', exact: true });
			await newProject(page);
			if (where === 'first component') {
				await panel
					.getByRole('combobox', { name: 'First component' })
					.selectOption({ label: 'Assigned flow (demand or supply)' });
			} else {
				await addFirst(page, 'Reservoir', 'Reservoir R1');
				await panel.getByRole('button', { name: 'Next: connect port 1' }).click();
				await panel
					.getByRole('combobox', { name: 'Add a component here' })
					.selectOption({ label: 'Assigned flow (demand or supply)' });
			}
			if (error) {
				await add.click();
				await expect(panel.getByRole('alert')).toHaveText(REQUIRED);
			}
			await panel.getByRole('textbox', { name: 'Flow (L/s)' }).fill(value);
			await add.click();
			await expect(currentHeading(page)).toHaveText('Assigned flow AF1');
			await expect(panel.getByRole('textbox', { name: 'Flow (L/s)' })).toHaveValue(value);
		});
	}
}
