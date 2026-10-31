import { expect, test, type Locator, type Page } from '@playwright/test';
import type {
	GoalSeekRequest,
	GoalSeekResponse,
	SolvedState,
	SolveRequest
} from '../src/lib/api/types';
import {
	addAfter,
	addFirst,
	ALLOWED_ORIGINS,
	buildPane,
	cellText,
	closeTrace,
	currentHeading,
	newProject,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	sig4,
	solveConverged,
	tableTexts,
	traceOf
} from './support';

/**
 * A pressure relief valve (proposal pressure-relief-valve.md §7.6) built through the panel
 * navigator and solved against the real API, on desktop and mobile:
 *
 *   Reservoir R1 (0 m, liquid level 3 m) → 10 m pipe, sharp entrance → Pump P1 → 10 m pipe →
 *     Tee T1 (Crane) run → 1 m pipe → Gate valve V1 → 10 m pipe, exit → Reservoir R2 (10 m,
 *     level 2 m); T1's branch → 10 m pipe → Relief valve RV1 (set 280 kPa, API 526 J, ASME's
 *     overpressure) → open discharge (Discharge to atmosphere: 1 m pipe with an exit → N1 at
 *     0 kPa(g))
 *
 * Every pipe the app's default, NPS 4 Sch 40 carbon steel; water at 20 °C (the new project's
 * fluid). Test inputs (made up, the proposal's): P1's curve 0 L/s at 30 m, 10 at 28, 20 at 22,
 * 30 at 12; scenarios "Blocked discharge" (V1 isolated), "Smaller valve" (blocked, letter E),
 * "Gagged" (blocked, RV1 locked closed); a goal seek of an API 520 effective area for an inlet of
 * 308 kPa(g), 1.1 × the set, in a blocked case.
 *
 * Expected values (D6: within 0.5 %): the synthesizer's (proposal §7.6, S5, this design's law),
 * which the API as built reproduces: base RV1 closed, inlet 129.5808 kPa(g), Δp ÷ set 46.28 %,
 * pump 28.91322 L/s; blocked: partial lift 9.30759 L/s, lift 0.703762, inlet 299.8260 kPa(g),
 * back 0.1207 kPa(g), Δp ÷ set 107.04 %, capacity 13.40724 L/s, 69.42 % of it; smaller: full lift
 * 2.086091 L/s, inlet 321.5098 kPa(g), 102.17 % of its capacity; gagged: inlet 323.0392 kPa(g);
 * the sizing goal seek: 447.0709 mm² (lift 0.99732), covering letter H. Displayed numbers are
 * checked against the solve's own response. Re-measured on this network with the API as built
 * (the web builder's relief-build/web-builder/e2e/net.py and gs.py): closed 129,580.80 Pa,
 * 0.462789, 0.0289132 m³/s; blocked 0.00930759 m³/s, lift 0.703762, 299,826.03 Pa; smaller
 * 0.00208609 m³/s, 321,509.77 Pa, 1.02168; gagged 323,039.25 Pa; the goal seek to 10 Pa,
 * 447.092 mm², lift 0.997300, letter H (to the default 1.54 kPa it stops at 448.262 mm²).
 */

const RV = 'Relief valve RV1';
const SET_REQUIRED = 'Enter the set pressure: it has no default.';
const CAPACITY_REQUIRED =
	'Choose an API 526 orifice letter, or enter an effective area or the certified area and coefficient: the capacity has no default.';
const CURVE = [
	{ flow: '0', head: '30' },
	{ flow: '10', head: '28' },
	{ flow: '20', head: '22' },
	{ flow: '30', head: '12' }
];
/** D6: a flow, head or pressure within 0.5 % of its reference. */
const within = (value: number, reference: number) =>
	expect(Math.abs(value - reference)).toBeLessThanOrEqual(0.005 * Math.abs(reference));

const caseMenu = (page: Page) => page.getByRole('combobox', { name: 'Case', exact: true });
const scenariosButton = (page: Page) => page.getByRole('button', { name: /^Scenarios/ });

/** Show a component in Build (through Jump to a component). */
async function show(page: Page, name: string): Promise<Locator> {
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: new RegExp(`^${name}`) })
		.click();
	await expect(currentHeading(page)).toHaveText(name);
	return buildPane(page);
}

/** A port's Piping view of the current component (its button in the ports group). */
async function piping(panel: Locator, component: string, port: RegExp): Promise<void> {
	await panel.getByRole('tab', { name: 'Piping' }).click();
	const ports = panel.getByRole('group', { name: `Ports of ${component}` });
	await ports.getByRole('button', { name: port }).click();
	await expect(ports.getByRole('button', { name: port })).toHaveAttribute('aria-pressed', 'true');
}

/**
 * Build the network: the pump and its curve, the tee and the line to R2, then at the tee's branch
 * the relief valve, entered in the Piping view (its two errors first), and its open discharge.
 */
async function buildNetwork(page: Page): Promise<void> {
	await newProject(page);
	const panel = buildPane(page);
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await setNumber(panel, /^Liquid level/, '3');
	await addAfter(page, 'Pump', 'Pump P1');
	const curve = panel.getByRole('region', { name: 'Pump curve' });
	await curve.getByRole('button', { name: 'Add point' }).click();
	for (const [i, point] of CURVE.entries()) {
		await setNumber(curve, `Point ${i + 1} flow (L/s)`, point.flow);
		await setNumber(curve, `Point ${i + 1} head (m)`, point.head);
	}
	await expect(curve.getByText('This pump needs a curve.')).toBeHidden();
	await addAfter(page, 'Tee', 'Tee T1');

	// The tee's run outlet: the isolation valve, 1 m from the tee, and the upper reservoir.
	await piping(panel, 'Tee T1', /^Run outlet/);
	await panel
		.getByRole('combobox', { name: 'Add a component here' })
		.selectOption({ label: 'Gate valve' });
	await panel.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Gate valve V1');
	await piping(panel, 'Gate valve V1', /^Inlet/);
	await setNumber(panel, /^Length/, '1');
	await panel.getByRole('tab', { name: 'Properties' }).click();
	await addAfter(page, 'Reservoir', 'Reservoir R2');
	await setNumber(panel, /^Elevation/, '10');
	await setNumber(panel, /^Liquid level/, '2');

	// The tee's branch: the relief valve, asked for its set and capacity first.
	await show(page, 'Tee T1');
	await piping(panel, 'Tee T1', /^Branch/);
	await expect(panel.getByRole('heading', { name: 'Branch is not connected' })).toBeVisible();
	const kinds = panel.getByRole('combobox', { name: 'Add a component here' });
	await kinds.selectOption({ label: 'Pressure relief valve (API 520, liquids)' });
	await expect(kinds.locator('option:checked')).toHaveText(
		'Pressure relief valve (API 520, liquids)'
	);
	const add = panel.getByRole('button', { name: 'Add', exact: true });
	await add.click();
	await expect(panel.getByRole('alert')).toHaveText([SET_REQUIRED, CAPACITY_REQUIRED]);
	await setNumber(panel, 'Set pressure (difference) (kPa)', '280');
	await panel
		.getByRole('combobox', { name: 'API 526 orifice letter' })
		.selectOption({ label: 'J: 830.3 mm²' });
	await expect(panel.getByRole('alert')).toHaveCount(0);
	await add.click();
	await expect(currentHeading(page)).toHaveText(RV);

	// Its outlet discharges to atmosphere: one action adds the reference node and its stub.
	await piping(panel, RV, /^Outlet/);
	await expect(panel.getByRole('heading', { name: 'Outlet is not connected' })).toBeVisible();
	await panel.getByRole('button', { name: 'Discharge to atmosphere' }).click();
	await expect(panel.getByRole('heading', { name: 'Outlet is not connected' })).toBeHidden();
	await expect(
		panel.getByText(/^From Relief valve RV1 \(outlet\) to Open discharge N1 \(port 1\)\./)
	).toBeVisible();
	// One step: the node and its stub are undone together.
	await expect(
		page.getByRole('button', { name: 'Undo discharge RV1 outlet to atmosphere' })
	).toBeVisible();
}

/** RV1's "Last solve" strip in Build (its name sets the element off with a hidden span). */
const valveStrip = (page: Page) =>
	buildPane(page).getByRole('group', { name: new RegExp(`^Last solve\\s?: ${RV}$`) });

/** The labels of an element's "Last solve" strip, spaces as spaces (once the strip is shown). */
async function stripLabels(strip: Locator): Promise<string[]> {
	await expect(strip.locator('dt').first()).toBeVisible();
	return (await strip.locator('dt').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim());
}

/** The value shown in an element's "Last solve" strip for one label. */
async function stripValue(strip: Locator, label: string): Promise<string> {
	const pattern = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s');
	const item = strip.locator('dl > div').filter({
		has: strip.page().locator('dt', { hasText: new RegExp(`^${pattern}$`) })
	});
	await expect(item).toHaveCount(1);
	return (await item.locator('dd').innerText()).trim();
}

/** The Relief valves view's table. */
async function reliefTable(page: Page): Promise<Locator> {
	await showPane(page, 'Results');
	return (await resultsView(page, 'Relief valves')).getByRole('table', {
		name: 'Results per relief valve'
	});
}

/** The displayed values of RV1 in the Relief valves table, checked against the solve. */
async function readValve(page: Page, solved: SolvedState) {
	const valve = solved.reliefValveResults.RV1!;
	const table = await reliefTable(page);
	const shown = {
		state: await cellText(table, RV, 'State'),
		flow: await cellText(table, RV, 'Flow (+ inlet → outlet) L/s'),
		capacity: await cellText(table, RV, 'Capacity (full lift) L/s'),
		ratio: await cellText(table, RV, 'Flow ÷ capacity %'),
		inlet: await cellText(table, RV, 'Inlet pressure kPa(g)'),
		setRatio: await cellText(table, RV, 'Δp ÷ set %'),
		lift: await cellText(table, RV, 'Lift %')
	};
	expect(shown.flow).toBe(sig4(valve.flow * 1000));
	expect(shown.capacity).toBe(sig4(valve.fullLiftFlow * 1000));
	expect(shown.ratio).toBe(sig4(valve.flowRatio * 100));
	expect(shown.inlet).toBe(sig4(valve.inletPressure! / 1000));
	expect(shown.setRatio).toBe(sig4(valve.setRatio * 100));
	expect(shown.lift).toBe(sig4(valve.lift * 100));
	return { valve, shown, rows: await tableTexts(table) };
}

/** A new scenario named `name`, shown. */
async function newScenario(page: Page, name: string): Promise<void> {
	await scenariosButton(page).click();
	const manager = page.getByRole('dialog', { name: 'Scenarios' });
	await manager.getByRole('button', { name: 'New scenario' }).click();
	const field = manager.getByRole('textbox', { name: /^Name of scenario S\d+$/ }).last();
	await field.fill(name);
	await field.press('Enter');
	await manager.getByRole('button', { name: 'Done' }).click();
	await expect(manager).toBeHidden();
}

/** In the scenario shown: V1 isolated (the blocked discharge the relief valve protects against). */
async function blockDischarge(page: Page): Promise<void> {
	const panel = await show(page, 'Gate valve V1');
	// A gate's status is a pair of segments (proposal build-density.md §11).
	const closed = panel
		.getByRole('radiogroup', { name: 'Status' })
		.getByRole('radio', { name: 'Closed (isolated)' });
	await closed.click();
	await expect(closed).toBeChecked();
}

test('build and solve: the relief valve stays closed; its results, strip and trace; share and reopen', async ({
	page,
	context
}) => {
	const origins = new Set<string>();
	context.on('request', (request) => origins.add(new URL(request.url()).origin));
	const sent: SolveRequest[] = [];
	page.on('request', (r) => {
		if (r.url().endsWith('/api/v1/solve') && r.method() === 'POST') {
			sent.push(r.postDataJSON() as SolveRequest);
		}
	});
	await buildNetwork(page);
	const solved = await solveConverged(page);
	// The valve as entered: the set in SI, the letter, active; the open discharge at 0 Pa gauge.
	const project = sent.at(-1)!.project;
	expect(project.components.find((c) => c.id === 'RV1')).toMatchObject({
		type: 'relief_valve',
		setPressure: 280000,
		capacity: { kind: 'api526', letter: 'J' },
		status: 'active'
	});
	expect(project.components.find((c) => c.id === 'N1')).toMatchObject({
		type: 'reference_node',
		pressure: 0
	});
	expect(project.connections.find((c) => c.toComponentId === 'N1')?.piping).toEqual({
		pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 1 }],
		fittings: [{ type: 'exit', quantity: 1, pipeIndex: 0 }]
	});

	await expect(
		resultsPane(page).getByRole('tablist', { name: 'Results view' }).getByRole('tab')
	).toHaveText([
		'Summary',
		'Nodes',
		'Links',
		'Pumps',
		'Valves',
		'Relief valves',
		'Branches',
		'Boundaries',
		'Methods'
	]);
	const { valve, shown, rows } = await readValve(page, solved);
	expect(valve.state).toBe('closed');
	expect(shown.state).toBe('Closed');
	expect(valve.flow).toBe(0);
	within(valve.inletPressure!, 129580.8);
	within(valve.setRatio, 0.4628);
	within(solved.pumpResults.P1!.operatingFlow, 0.02891322);
	// A closed valve that has a result raises no flag of its own.
	expect(solved.flags.filter((f) => f.componentId === 'RV1')).toEqual([]);

	// The strip beside RV1 in Build: the table's own cells.
	await show(page, RV);
	const strip = valveStrip(page);
	expect(await stripLabels(strip)).toEqual([
		'State',
		'Flow (+ inlet → outlet) (L/s)',
		'Inlet pressure (kPa(g))',
		'Δp ÷ set (%)'
	]);
	expect(await stripValue(strip, 'State')).toBe(shown.state);
	expect(await stripValue(strip, 'Flow (+ inlet → outlet) (L/s)')).toBe(shown.flow);
	expect(await stripValue(strip, 'Inlet pressure (kPa(g))')).toBe(shown.inlet);
	expect(await stripValue(strip, 'Δp ÷ set (%)')).toBe(shown.setRatio);

	// The trace: the set and the letter are the user's, the overpressure ASME's default.
	await showPane(page, 'Results');
	const table = await reliefTable(page);
	await table.getByRole('button', { name: new RegExp(`^${RV}`) }).click();
	const trace = traceOf(page, RV);
	await expect(trace).toBeVisible();
	const inputs = trace.getByRole('region', { name: 'Inputs' });
	for (const [name, source] of [
		[/^Set pressure Δp_s/, 'User'],
		[/^API 526 effective area A \(letter J\)/, 'Library'],
		[/^Effective coefficient of discharge Kd/, 'Library'],
		[/^Overpressure at full lift op/, 'Default']
	] as const) {
		const input = inputs.getByRole('listitem').filter({ hasText: name });
		await expect(input).toHaveCount(1);
		await expect(input).toContainText(source);
	}
	// On a phone the trace is a sheet over the page: closed before Share.
	await closeTrace(page, RV);

	// Share, reopen: the same table.
	await page.getByRole('button', { name: 'Share' }).click();
	const share = page.getByRole('dialog', { name: 'Share this project' });
	const link = await share
		.getByRole('textbox', { name: 'Link to this version of the project' })
		.inputValue();
	await share.getByRole('button', { name: 'Close' }).click();
	const reopened = await context.newPage();
	await reopened.goto(link);
	await expect(currentHeading(reopened)).toHaveText('Reservoir R1');
	await solveConverged(reopened);
	expect(await tableTexts(await reliefTable(reopened))).toEqual(rows);
	await reopened.close();

	// Nothing but the app and its calculation server was contacted (GOALS §4.5).
	expect([...origins].filter((o) => !ALLOWED_ORIGINS.has(o))).toEqual([]);
});

test('scenarios: a blocked discharge relieves; a smaller valve and a gagged one; compare and export', async ({
	page
}) => {
	const solves: Record<string, SolvedState> = {};
	page.on('response', async (r) => {
		if (r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST' && r.ok()) {
			const request = r.request().postDataJSON() as SolveRequest;
			const body = (await r.json()) as { solvedState: SolvedState };
			solves[request.scenarioId ?? 'base'] = body.solvedState;
		}
	});
	await buildNetwork(page);

	// Blocked discharge: V1 isolated, one change.
	await newScenario(page, 'Blocked discharge');
	await blockDischarge(page);
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Blocked discharge (1 change)');

	// A smaller valve: blocked, on API 526 E (a change of the letter alone, its base J).
	await newScenario(page, 'Smaller valve');
	await blockDischarge(page);
	let panel = await show(page, RV);
	const letter = panel.getByRole('combobox', { name: 'API 526 orifice letter' });
	await letter.selectOption({ label: 'E: 126.5 mm²' });
	await expect(letter).toHaveAccessibleDescription(
		/Changed in this scenario\. Base value API 526 J \(830\.3 mm²\)\./
	);
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Smaller valve (2 changes)');

	// Gagged: blocked, and the relief valve locked closed.
	await newScenario(page, 'Gagged');
	await blockDischarge(page);
	panel = await show(page, RV);
	await panel
		.getByRole('combobox', { name: 'Status' })
		.selectOption({ label: 'Locked closed (gagged or blocked: does not open)' });
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Gagged (2 changes)');

	// Solve all: the base, then each scenario.
	await page
		.getByRole('group', { name: 'Case' })
		.getByRole('button', { name: 'Solve all' })
		.click();
	await expect(page.getByRole('group', { name: 'Case' })).not.toContainText('Solving');
	await expect.poll(() => Object.keys(solves).sort()).toEqual(['S1', 'S2', 'S3', 'base']);
	const blocked = solves.S1!.reliefValveResults.RV1!;
	expect(blocked.state).toBe('partial_lift');
	within(blocked.flow, 0.00930759);
	within(blocked.lift, 0.703762);
	within(blocked.inletPressure!, 299826.0);
	within(blocked.setRatio, 1.0704);
	within(blocked.fullLiftFlow, 0.01340724);
	within(blocked.flowRatio, 0.6942);
	// Partial lift is the linear convention: flagged as a warning on RV1.
	expect(
		solves.S1!.flags.filter((f) => f.componentId === 'RV1').map((f) => [f.code, f.details.limit])
	).toEqual([['CORRELATION_OUT_OF_RANGE', 'partial_lift']]);
	const smaller = solves.S2!.reliefValveResults.RV1!;
	expect(smaller.state).toBe('full_lift');
	within(smaller.flow, 0.002086091);
	within(smaller.inletPressure!, 321509.8);
	within(smaller.flowRatio, 1.0217);
	expect(smaller.capacity).toMatchObject({ kind: 'api526', letter: 'E' });
	// At full lift: told as information (it relieves, at more than its capacity at full lift).
	expect(solves.S2!.flags.filter((f) => f.componentId === 'RV1').map((f) => f.code)).toEqual([
		'RELIEF_VALVE_OPEN'
	]);
	const gagged = solves.S3!.reliefValveResults.RV1!;
	expect(gagged.state).toBe('closed');
	expect(gagged.flow).toBe(0);
	within(gagged.inletPressure!, 323039.2);
	expect(solves.S3!.flags.filter((f) => f.componentId === 'RV1')).toEqual([]);

	// The blocked case's table: the solve's own values.
	await caseMenu(page).selectOption({ label: 'Blocked discharge (1 change)' });
	const { shown } = await readValve(page, solves.S1!);
	expect(shown.state).toBe('Partial lift');

	// Compare: RV1's flow, state and inlet pressure among the default rows.
	await showPane(page, 'Results');
	await resultsPane(page).getByRole('tab', { name: 'Compare cases' }).click();
	const compare = resultsPane(page).getByRole('region', { name: 'Compare cases' });
	for (const quantity of ['Flow', 'State', 'Inlet pressure']) {
		await expect(
			compare.getByRole('button', { name: `${RV} · ${quantity}` }).filter({ visible: true })
		).toHaveCount(1);
	}

	// Export, all cases: the Relief valves sheet holds one row per case.
	await resultsPane(page).locator('[data-export-button]').click();
	const exporting = page.getByRole('dialog', { name: 'Export results' });
	await exporting.getByRole('radio', { name: /^All cases/ }).check();
	await expect(exporting.getByRole('region', { name: 'In the file' })).toContainText(
		'Relief valves (4)'
	);
	await exporting.getByRole('button', { name: 'Close' }).last().click();
});

test('goal seek sizes an API 520 effective area for the relieving pressure, applied as a new scenario', async ({
	page
}) => {
	await buildNetwork(page);
	// A blocked case whose valve is an effective area: one whole-capacity change beside V1's.
	await newScenario(page, 'Sizing');
	await blockDischarge(page);
	const panel = await show(page, RV);
	await panel.getByRole('combobox', { name: 'Capacity given by' }).selectOption('effective');
	await expect(
		panel.getByText(
			'Enter the API 520 effective area to use it; until then the API 526 letter J applies.'
		)
	).toBeVisible();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Sizing (1 change)');
	// J's own effective area, 1.287 in² (x-relief-data). The field shows 6 significant digits and
	// stores the value typed (checked in the goal-seek request below), so setNumber's
	// shown-as-typed check does not apply.
	const area = panel.getByRole('textbox', { name: 'API 520 effective area (mm²)' });
	await area.fill('830.32092');
	await area.press('Enter');
	await expect(area).toHaveValue('830.321');
	await expect(area).not.toHaveAttribute('aria-invalid', 'true');
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Sizing (2 changes)');

	await showPane(page, 'Results');
	await resultsPane(page)
		.getByRole('button', { name: /^Goal seek/ })
		.click();
	const d = page.getByRole('dialog', { name: 'Goal seek' });
	await expect(d).toBeVisible();

	// The goal: RV1's inlet at the relieving pressure, 1.1 × 280 kPa (discharging to atmosphere),
	// to 0.01 kPa: the search stops inside a tenth of it, so the area found is the one that gives
	// this pressure, not one anywhere in the default 0.5 % (±1.54 kPa, about ±1.2 % in area here).
	await d.getByRole('button', { name: 'Add goal' }).click();
	const goalForm = d.getByRole('group', { name: 'New goal' });
	await goalForm
		.getByRole('combobox', { name: 'Element' })
		.selectOption({ label: `Inlet of ${RV}` });
	await goalForm.getByRole('radio', { name: 'Pressure', exact: true }).check();
	await goalForm.getByRole('button', { name: 'Add goal' }).click();
	const goal = d.getByRole('group', { name: new RegExp(`Inlet of ${RV} · Pressure$`) });
	await setNumber(goal, /^Target/, '308');
	await setNumber(goal, /^Tolerance/, '0.01');

	// The variable: the effective area, in API 526's D to T (the case's 830.3 mm² between them).
	await d.getByRole('button', { name: 'Add variable' }).click();
	const variableForm = d.getByRole('group', { name: 'New variable' });
	const element = variableForm.getByRole('combobox', { name: 'Element' });
	await element.selectOption({ label: RV });
	await expect(element.locator('option:checked')).toHaveText(RV);
	await variableForm.getByRole('radio', { name: 'API 520 effective area', exact: true }).check();
	await variableForm.getByRole('button', { name: 'Add variable' }).click();
	const variable = d.getByRole('group', { name: new RegExp(`${RV} · API 520 effective area$`) });
	await expect(variable.getByText('Defaults: 70.9676 mm² to 16774.2 mm².')).toBeVisible();

	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/goal-seek') && r.request().method() === 'POST'
	);
	await d.getByRole('button', { name: /^Run goal seek/ }).click();
	const response = await answer;
	expect(response.status(), (await response.text()).slice(0, 500)).toBe(200);
	const request = response.request().postDataJSON() as GoalSeekRequest;
	const body = (await response.json()) as GoalSeekResponse;
	expect(request.scenarioId).toBe('S1');
	// The whole capacity the scenario sets holds the area as typed, not as shown.
	const sizing = request.project.scenarios!.find((s) => s.id === 'S1')!;
	expect(
		sizing.overrides!.find((o) => o.kind === 'component' && o.field === 'capacity')
	).toMatchObject({ componentId: 'RV1', value: { kind: 'effective', area: 830.32092e-6 } });
	expect(request.goals).toEqual([
		{ quantity: 'port_pressure', elementId: 'RV1', portId: 'inlet', target: 308000, tolerance: 10 }
	]);
	// x-relief-data's API 526 D and T areas (fluids' in² × 0.0254²), m².
	expect(request.variables).toEqual([
		{
			kind: 'component',
			componentId: 'RV1',
			field: 'capacity.area',
			lower: 7.09676e-5,
			upper: 0.01677416
		}
	]);
	expect(body.success).toBe(true);
	await expect(d.getByText('Goal met', { exact: true })).toBeVisible();
	const found = body.result.variables[0]!.value!;
	within(found, 4.470709e-4);
	const sized = body.solvedState!.reliefValveResults.RV1!;
	expect(Math.abs(sized.inletPressure! - 308000)).toBeLessThanOrEqual(10);
	within(sized.lift, 0.99732);
	// Between API 526's G (324.5 mm²) and H (506.5 mm²): H is the smallest letter that covers it.
	expect(sized.capacity).toMatchObject({ kind: 'effective', area: found, coveringLetter: 'H' });

	await d.getByRole('button', { name: 'Apply as new scenario' }).click();
	await expect(d).toBeHidden();
	// The second scenario (S2, after Sizing): the run's V1 change, and its whole capacity holding
	// the area found.
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Goal seek 2 (2 changes)');
	await expect(resultsPane(page).getByRole('status')).toHaveText(
		'Last solve of Goal seek 2: converged'
	);
});
