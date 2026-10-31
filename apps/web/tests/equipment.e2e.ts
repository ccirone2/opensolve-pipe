import { expect, test, type Locator, type Page } from '@playwright/test';
import type { SolvedState, SolveRequest } from '../src/lib/api/types';
import {
	addFirst,
	ALLOWED_ORIGINS,
	buildPane,
	caseGroup,
	caseMenu,
	cellText,
	closeTrace,
	currentHeading,
	newProject,
	openCases,
	openScenarioManager,
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
 * An equipment item (proposal equipment-pressure-drop.md §7.6) built through the panel navigator
 * and solved against the real API, on desktop and mobile:
 *
 *   Reservoir R1 (0 m, liquid level 5 m) → 10 m pipe, NPS 4, sharp entrance → Equipment E1
 *     → 10 m pipe, NPS 4, exit → Reservoir R2 (0 m, level 0 m)
 *
 * Water at 20 °C (the new project's fluid). The pipes and fittings are the app's defaults. Test
 * inputs (made up, the proposal's): E1 rated 35 kPa at 10 L/s on the case's fluid; a scenario
 * "Dirty strainer" with a 70 kPa rated drop; a scenario "Vendor B" rated Cv 80.
 *
 * Expected values (D6: within 0.5 %): measured by the web designer with E1 emulated as a gate
 * valve of K = 47.3021 on the 102.26 mm bore (proposal §7.6, S4): 11.2278 L/s, flow ÷ rated flow
 * 112.278 %, pressure loss and static drop 44.1222 kPa, head loss 4.5073 m; Vendor B's E1 (a gate
 * valve of Cv 80 on that bore, check_cvkv.out.txt F): 12.6015 L/s, pressure loss and static drop
 * 42.9327 kPa, head loss 4.3858 m. Displayed numbers are checked against the solve's own response.
 */

const RATED_DROP = '35'; // kPa
const RATED_FLOW = '10'; // L/s
const ITEM = 'Equipment E1';
const REQUIRED = [
	'Enter the rated pressure drop from the datasheet: it has no default.',
	'Enter the rated flow from the datasheet: it has no default.',
	'Enter the rated fluid density, or use one of the buttons: it has no default.'
];
/** D6: a flow, head or pressure within 0.5 % of its reference. */
const within = (value: number, reference: number) =>
	expect(Math.abs(value - reference)).toBeLessThanOrEqual(0.005 * Math.abs(reference));

/** Build R1 (5 m) → E1 → R2, E1 entered in the Add after dialog (its errors first). */
async function buildNetwork(page: Page): Promise<void> {
	await newProject(page);
	const panel = buildPane(page);
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await setNumber(panel, /^Liquid level/, '5');

	await panel.getByRole('button', { name: 'Add after' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add after Reservoir R1' });
	const kinds = dialog.getByRole('combobox', { name: 'Component' });
	await kinds.selectOption({ label: 'Equipment (rated pressure drop)' });
	await expect(dialog.getByRole('combobox', { name: 'Rated by' })).toHaveValue('point');
	// No value has a default: Add names the three, each at its field.
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog.getByRole('alert')).toHaveText(REQUIRED);
	await setNumber(dialog, 'Rated pressure drop (kPa)', RATED_DROP);
	await setNumber(dialog, 'Rated flow (L/s)', RATED_FLOW);
	const density = dialog.getByRole('textbox', { name: 'Rated fluid density (kg/m³)' });
	const properties = page.waitForResponse((r) => r.url().endsWith('/api/v1/fluids/properties'));
	await dialog.getByRole('button', { name: "This case's fluid" }).click();
	expect((await properties).status()).toBe(200);
	await expect(density).not.toHaveValue('');
	await expect(dialog.getByRole('alert')).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog).toBeHidden();
	await expect(currentHeading(page)).toHaveText(ITEM);

	await panel.getByRole('button', { name: 'Add after' }).click();
	const next = page.getByRole('dialog', { name: `Add after ${ITEM}` });
	await next.getByRole('combobox', { name: 'Component' }).selectOption({ label: 'Reservoir' });
	await next.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Reservoir R2');
}

/** The value shown in an element's "Last solve" strip for one label, e.g. "Flow (L/s)". */
async function stripValue(strip: Locator, label: string): Promise<string> {
	const pattern = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s');
	const item = strip.locator('dl > div').filter({
		has: strip.page().locator('dt', { hasText: new RegExp(`^${pattern}$`) })
	});
	await expect(item).toHaveCount(1);
	return (await item.locator('dd').innerText()).trim();
}

/** The labels of an element's "Last solve" strip, spaces as spaces (once the strip is shown). */
async function stripLabels(strip: Locator): Promise<string[]> {
	await expect(strip.locator('dt').first()).toBeVisible();
	return (await strip.locator('dt').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim());
}

/**
 * E1's "Last solve" strip in Build. Its name is "Last solve: Equipment E1", with the element's
 * name in a visually hidden span, which Chrome's name computation sets off with a space
 * ("Last solve : Equipment E1"; results-in-context.e2e.ts matches /^Last solve/).
 */
const itemStrip = (page: Page) =>
	buildPane(page).getByRole('group', { name: new RegExp(`^Last solve\\s?: ${ITEM}$`) });

/** The Equipment view's table. */
async function equipmentTable(page: Page): Promise<Locator> {
	await showPane(page, 'Results');
	return (await resultsView(page, 'Equipment')).getByRole('table', {
		name: 'Results per equipment item'
	});
}

/** The displayed values of E1 in the Equipment table, checked against the solve. */
async function readItem(page: Page, solved: SolvedState) {
	const item = solved.equipmentResults.E1!;
	const table = await equipmentTable(page);
	const shown = {
		flow: await cellText(table, ITEM, 'Flow (+ inlet → outlet) L/s'),
		ratio: await cellText(table, ITEM, 'Flow ÷ rated flow %'),
		loss: await cellText(table, ITEM, 'Pressure loss kPa'),
		head: await cellText(table, ITEM, 'Head loss m'),
		drop: await cellText(table, ITEM, 'Pressure drop (static) kPa')
	};
	expect(shown.flow).toBe(sig4(item.flow * 1000));
	expect(shown.loss).toBe(sig4(item.pressureLoss / 1000));
	expect(shown.drop).toBe(sig4(item.pressureDrop / 1000));
	expect(shown.ratio).toBe(item.flowRatio === null ? '—' : sig4(item.flowRatio * 100));
	return { item, shown, rows: await tableTexts(table) };
}

test('add an equipment item, solve, read its results, trace and strip; share and reopen', async ({
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
	// The rating as entered: SI, the density the API's own double for the case's fluid.
	const e1 = sent.at(-1)!.project.components.find((c) => c.id === 'E1');
	expect(e1).toMatchObject({
		type: 'equipment',
		rating: { kind: 'point', pressureLoss: 35000, flow: 0.01, density: solved.fluid.density }
	});

	await expect(
		resultsPane(page).getByRole('tablist', { name: 'Results view' }).getByRole('tab')
	).toHaveText(['Summary', 'Nodes', 'Links', 'Equipment', 'Boundaries', 'Methods']);
	const { item, shown, rows } = await readItem(page, solved);
	within(item.flow, 0.0112278);
	within(item.flowRatio!, 1.12278);
	within(item.pressureLoss, 44122.2);
	within(item.pressureDrop, 44122.2);
	within(item.headLoss, 4.5073);
	// One elevation and one bore at both ports: the static drop is the loss (§3.3).
	expect(Math.abs(item.pressureDrop - item.pressureLoss)).toBeLessThan(1);

	// The strip beside E1 in Build: the table's own cells.
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: new RegExp(`^${ITEM}`) })
		.click();
	await expect(currentHeading(page)).toHaveText(ITEM);
	const strip = itemStrip(page);
	expect(await stripLabels(strip)).toEqual([
		'Flow (+ inlet → outlet) (L/s)',
		'Flow ÷ rated flow (%)',
		'Pressure loss (kPa)'
	]);
	expect(await stripValue(strip, 'Flow (+ inlet → outlet) (L/s)')).toBe(shown.flow);
	expect(await stripValue(strip, 'Flow ÷ rated flow (%)')).toBe(shown.ratio);
	expect(await stripValue(strip, 'Pressure loss (kPa)')).toBe(shown.loss);

	// The trace: the rating as the user's data.
	await showPane(page, 'Results');
	const table = await equipmentTable(page);
	await table.getByRole('button', { name: new RegExp(`^${ITEM}`) }).click();
	const trace = traceOf(page, ITEM);
	await expect(trace).toBeVisible();
	const inputs = trace.getByRole('region', { name: 'Inputs' });
	for (const name of [/^Rated pressure drop/, /^Rated flow/, /^Rated fluid density/]) {
		const input = inputs.getByRole('listitem').filter({ hasText: name });
		await expect(input).toHaveCount(1);
		await expect(input).toContainText('User');
	}
	// On a phone the trace is a sheet over the page: closed before Share.
	await closeTrace(page, ITEM);

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
	expect(await tableTexts(await equipmentTable(reopened))).toEqual(rows);
	await reopened.close();

	// Nothing but the app and its calculation server was contacted (GOALS §4.5).
	expect([...origins].filter((o) => !ALLOWED_ORIGINS.has(o))).toEqual([]);
});

test('Add before inserts it into the line, the rating asked for; the first click adds it', async ({
	page
}) => {
	await newProject(page);
	const panel = buildPane(page);
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await panel.getByRole('button', { name: 'Add after' }).click();
	let dialog = page.getByRole('dialog', { name: 'Add after Reservoir R1' });
	await dialog.getByRole('combobox', { name: 'Component' }).selectOption({ label: 'Gate valve' });
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Gate valve V1');

	// Before the valve: into the connection the walk arrived by.
	await panel.getByRole('button', { name: 'Add before' }).click();
	dialog = page.getByRole('dialog', { name: 'Add before Gate valve V1' });
	const kinds = dialog.getByRole('combobox', { name: 'Component' });
	await kinds.selectOption({ label: 'Equipment (rated pressure drop)' });
	await dialog
		.getByRole('combobox', { name: 'Rated by' })
		.selectOption({ label: 'Kv (metric flow coefficient)' });
	const add = dialog.getByRole('button', { name: 'Add', exact: true });
	await add.click();
	await expect(dialog.getByRole('alert')).toHaveText(
		'Enter the Kv from the datasheet: it has no default.'
	);
	// Typed, not entered: the press on Add stores it as the field loses focus, and nothing moves
	// under the pointer, so the first click adds the item.
	await dialog.getByRole('textbox', { name: 'Kv' }).fill('60');
	await add.click();
	await expect(dialog).toBeHidden();
	await expect(currentHeading(page)).toHaveText(ITEM);
	await expect(panel.getByRole('textbox', { name: 'Kv' })).toHaveValue('60');
	// Between the reservoir and the valve: Previous names the reservoir, Next the valve.
	await expect(panel.getByRole('button', { name: /^Previous/ })).toHaveText(
		'Previous: Reservoir R1'
	);
	await expect(panel.getByRole('button', { name: /^Next/ })).toHaveText('Next: Gate valve V1');
});

test('as the first component: a density typed over a button’s note; the first click adds it', async ({
	page
}) => {
	await newProject(page);
	const panel = buildPane(page);
	await panel
		.getByRole('combobox', { name: 'First component' })
		.selectOption({ label: 'Equipment (rated pressure drop)' });
	await setNumber(panel, 'Rated pressure drop (kPa)', RATED_DROP);
	await setNumber(panel, 'Rated flow (L/s)', RATED_FLOW);
	const properties = page.waitForResponse((r) => r.url().endsWith('/api/v1/fluids/properties'));
	await panel.getByRole('button', { name: 'Water at 15 °C' }).click();
	expect((await properties).status()).toBe(200);
	await expect(panel.getByRole('group', { name: 'Rating' }).getByRole('status')).toHaveText(
		/^Entered the density of water at 15 °C/
	);
	// Typed, not entered: the note above Add goes as the density is typed over it, so the press on
	// Add, which stores the density as the field loses focus, moves nothing under the pointer.
	const density = panel.getByRole('textbox', { name: 'Rated fluid density (kg/m³)' });
	await density.fill('1000');
	await panel.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText(ITEM);
	await expect(density).toHaveValue('1000');
});

test('scenarios: a dirty strainer and another vendor’s Cv; compare and export all cases', async ({
	page
}) => {
	const sent: SolveRequest[] = [];
	page.on('request', (r) => {
		if (r.url().endsWith('/api/v1/solve') && r.method() === 'POST') {
			sent.push(r.postDataJSON() as SolveRequest);
		}
	});
	const solves: Record<string, SolvedState> = {};
	page.on('response', async (r) => {
		if (r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST' && r.ok()) {
			const request = r.request().postDataJSON() as SolveRequest;
			const body = (await r.json()) as { solvedState: SolvedState };
			solves[request.scenarioId ?? 'base'] = body.solvedState;
		}
	});
	await buildNetwork(page);

	/** A new scenario named `name`, shown, with E1 shown in Build. */
	async function scenario(name: string): Promise<Locator> {
		const manager = await openScenarioManager(page);
		await manager.getByRole('button', { name: 'New scenario' }).click();
		const field = manager.getByRole('textbox', { name: /^Name of scenario S\d+$/ }).last();
		await field.fill(name);
		await field.press('Enter');
		await manager.getByRole('button', { name: 'Done' }).click();
		await expect(manager).toBeHidden();
		await showPane(page, 'Build');
		await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
		await page
			.getByRole('dialog', { name: 'Jump to a component' })
			.getByRole('button', { name: new RegExp(`^${ITEM}`) })
			.click();
		await expect(currentHeading(page)).toHaveText(ITEM);
		return buildPane(page);
	}

	// A dirty strainer: one change, of the rated pressure drop, marked at its field.
	let panel = await scenario('Dirty strainer');
	await setNumber(panel, 'Rated pressure drop (kPa)', '70');
	await expect(
		panel.getByRole('textbox', { name: 'Rated pressure drop (kPa)' })
	).toHaveAccessibleDescription(/Changed in this scenario\. Base value 35 kPa\./);
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Dirty strainer (1 change)');

	// Another vendor's datasheet, by its Cv: pending until entered, then one change of the rating.
	panel = await scenario('Vendor B');
	await panel
		.getByRole('combobox', { name: 'Rated by' })
		.selectOption({ label: 'Cv (US flow coefficient)' });
	await expect(
		panel.getByText('Enter the Cv to use it; until then the rated point applies.')
	).toBeVisible();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Vendor B (0 changes)');
	await setNumber(panel, 'Cv', '80');
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Vendor B (1 change)');
	await expect(
		panel.getByRole('button', { name: /^Reset Rating to the base value/ })
	).toBeVisible();

	// Solve all: the base, then each scenario.
	await (await openCases(page)).getByRole('button', { name: 'Solve all' }).click();
	await expect(caseGroup(page)).not.toContainText('Solving');
	expect(sent.map((r) => r.scenarioId ?? 'base').sort()).toEqual(['S1', 'S2', 'base']);
	// The bodies are read as they arrive: wait for the three.
	await expect.poll(() => Object.keys(solves).sort()).toEqual(['S1', 'S2', 'base']);
	const vendor = solves.S2!.equipmentResults.E1!;
	within(vendor.flow, 0.0126015);
	within(vendor.pressureLoss, 42932.7);
	within(vendor.pressureDrop, 42932.7);
	within(vendor.headLoss, 4.3858);
	expect(vendor.flowRatio).toBeNull();
	expect(vendor.rating).toEqual({ kind: 'Cv', value: 80 });
	// The dirty strainer passes less.
	expect(solves.S1!.equipmentResults.E1!.flow).toBeLessThan(solves.base!.equipmentResults.E1!.flow);

	// Vendor B's table: flow ÷ rated flow "—"; the strip leaves it out.
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Vendor B (1 change)');
	await readItem(page, solves.S2!);
	await showPane(page, 'Build');
	const strip = itemStrip(page);
	expect(await stripLabels(strip)).toEqual([
		'Flow (+ inlet → outlet) (L/s)',
		'Pressure loss (kPa)'
	]);

	// Compare: E1's flow and pressure loss among the default rows.
	await showPane(page, 'Results');
	await resultsPane(page).getByRole('tab', { name: 'Compare cases' }).click();
	const compare = resultsPane(page).getByRole('region', { name: 'Compare cases' });
	await expect(
		compare.getByRole('button', { name: `${ITEM} · Flow` }).filter({ visible: true })
	).toHaveCount(1);
	await expect(
		compare.getByRole('button', { name: `${ITEM} · Pressure loss` }).filter({ visible: true })
	).toHaveCount(1);

	// Export, all cases: the Equipment sheet holds one row per case.
	await resultsPane(page).locator('[data-export-button]').click();
	const exporting = page.getByRole('dialog', { name: 'Export results' });
	await exporting.getByRole('radio', { name: /^All cases/ }).check();
	await expect(exporting.getByRole('region', { name: 'In the file' })).toContainText(
		'Equipment (3)'
	);
	await exporting.getByRole('button', { name: 'Close' }).last().click();
});
