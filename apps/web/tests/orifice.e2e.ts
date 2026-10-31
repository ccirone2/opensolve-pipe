import { expect, test, type Locator, type Page } from '@playwright/test';
import type {
	GoalSeekRequest,
	GoalSeekResponse,
	SolvedState,
	SolveRequest
} from '../src/lib/api/types';
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
 * An orifice plate (proposal orifice-plate.md §7.6) built through the panel navigator and solved
 * against the real API, on desktop and mobile:
 *
 *   Reservoir R1 (0 m, liquid level 5 m) → 10 m pipe, NPS 4 Sch 40, sharp entrance → Orifice O1
 *     → 10 m pipe, NPS 4 Sch 40, exit → Reservoir R2 (0 m, level 0 m)
 *
 * Water at 20 °C (the new project's fluid). The pipes and fittings are the app's defaults. Test
 * inputs (made up, the proposal's): O1's bore 50 mm with flange taps, on ISO 5167-2's C; a
 * scenario "Bigger bore" with a 60 mm bore; a scenario "Calibrated" with an entered C of 0.62 at
 * O1's flange taps; a goal seek of O1's bore for 12 L/s.
 *
 * Expected values (D6: within 0.5 %): measured by the synthesizer with O1 emulated as a gate
 * valve of K = K(C_L(Q)) iterated to a fixed point (proposal §7.6, synth/e2e.out.txt; "Calibrated"
 * re-measured under decision 13's move, reviser/cases2.out.txt): 13.0855 L/s, permanent loss and
 * static drop 42.4832 kPa, differential pressure 57.1424 kPa, β 0.48895, C 0.604705, Re 162,376,
 * head loss 4.33987 m; "Bigger bore" 19.2555 L/s, 35.3691 kPa, reading 55.2133 kPa; "Calibrated"
 * C_L 0.619924, 13.4147 L/s, 42.1685 kPa, reading 57.1409 kPa; the bore for 12 L/s near
 * 48.0331 mm (β 0.46972). Displayed numbers are checked against the solve's own response.
 *
 * β is shown to 4 decimals: 0.05 ÷ 0.10226 = 0.4889497, "0.4889" (the proposal's W3 example,
 * "0.4890", rounds 0.48895 a second time).
 */

const ITEM = 'Orifice O1';
const REQUIRED = 'Enter the orifice bore: it has no default.';
/**
 * NPS 4 schedule 40's inner diameter in the API's pipe library (data/pipe_materials.json: ASME
 * B36.10M's metric OD 114.3 mm and wall 6.02 mm, via fluids), m.
 */
const D = 0.10226;
/** D6: a flow, head or pressure within 0.5 % of its reference. */
const within = (value: number, reference: number) =>
	expect(Math.abs(value - reference)).toBeLessThanOrEqual(0.005 * Math.abs(reference));

/** Show O1 in Build (through Jump to a component). */
async function showPlate(page: Page): Promise<Locator> {
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: new RegExp(`^${ITEM}`) })
		.click();
	await expect(currentHeading(page)).toHaveText(ITEM);
	return buildPane(page);
}

/**
 * Build R1 (5 m) → O1 → R2: O1 entered in the Add after dialog (its error first), its flange taps
 * chosen in its form, where β is shown against the inlet pipe.
 */
async function buildNetwork(page: Page): Promise<void> {
	await newProject(page);
	const panel = buildPane(page);
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await setNumber(panel, /^Liquid level/, '5');

	await panel.getByRole('button', { name: 'Add after' }).click();
	const dialog = page.getByRole('dialog', { name: 'Add after Reservoir R1' });
	await dialog
		.getByRole('combobox', { name: 'Component' })
		.selectOption({ label: 'Orifice plate (ISO 5167-2)' });
	// No bore has a default: Add says so at the field.
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog.getByRole('alert')).toHaveText(REQUIRED);
	await setNumber(dialog, 'Bore diameter (mm)', '50');
	await expect(dialog.getByRole('alert')).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(dialog).toBeHidden();
	await expect(currentHeading(page)).toHaveText(ITEM);
	await panel.getByRole('combobox', { name: 'Pressure taps' }).selectOption({ label: 'Flange' });
	// β against the inlet pipe, read-only, part of the bore's description.
	const beta =
		'β = d ÷ D = 0.4889, with D = 102.3 mm, the inner diameter of the inlet pipe (NPS 4, Sch 40)';
	await expect(panel.getByText(beta)).toBeVisible();
	await expect(
		panel.getByRole('textbox', { name: 'Bore diameter (mm)' })
	).toHaveAccessibleDescription(new RegExp(beta.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));

	await panel.getByRole('button', { name: 'Add after' }).click();
	const next = page.getByRole('dialog', { name: `Add after ${ITEM}` });
	await next.getByRole('combobox', { name: 'Component' }).selectOption({ label: 'Reservoir' });
	await next.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(currentHeading(page)).toHaveText('Reservoir R2');
}

/** The labels of an element's "Last solve" strip, spaces as spaces (once the strip is shown). */
async function stripLabels(strip: Locator): Promise<string[]> {
	await expect(strip.locator('dt').first()).toBeVisible();
	return (await strip.locator('dt').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim());
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

/** O1's "Last solve" strip in Build (its name sets the element off with a hidden span). */
const plateStrip = (page: Page) =>
	buildPane(page).getByRole('group', { name: new RegExp(`^Last solve\\s?: ${ITEM}$`) });

/** The Orifices view's table. */
async function orificeTable(page: Page): Promise<Locator> {
	await showPane(page, 'Results');
	return (await resultsView(page, 'Orifices')).getByRole('table', {
		name: 'Results per orifice plate'
	});
}

/** The displayed values of O1 in the Orifices table, checked against the solve. */
async function readPlate(page: Page, solved: SolvedState) {
	const plate = solved.orificeResults.O1!;
	const table = await orificeTable(page);
	const shown = {
		flow: await cellText(table, ITEM, 'Flow (+ inlet → outlet) L/s'),
		loss: await cellText(table, ITEM, 'Permanent loss kPa'),
		reading: await cellText(table, ITEM, 'Differential pressure (taps) kPa'),
		beta: await cellText(table, ITEM, 'β'),
		c: await cellText(table, ITEM, 'C'),
		source: await cellText(table, ITEM, 'C from'),
		re: await cellText(table, ITEM, 'Re (inlet pipe)'),
		drop: await cellText(table, ITEM, 'Pressure drop (static) kPa')
	};
	expect(shown.flow).toBe(sig4(plate.flow * 1000));
	expect(shown.loss).toBe(sig4(plate.pressureLoss / 1000));
	expect(shown.reading).toBe(
		plate.differentialPressure === null ? '—' : sig4(plate.differentialPressure / 1000)
	);
	expect(shown.beta).toBe(sig4(plate.beta));
	expect(shown.c).toBe(sig4(plate.dischargeCoefficient));
	expect(shown.re).toBe(sig4(plate.reynoldsNumber));
	expect(shown.drop).toBe(sig4(plate.pressureDrop / 1000));
	return { plate, shown, rows: await tableTexts(table) };
}

test('add an orifice plate, solve, read its results, trace and strip; share and reopen', async ({
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
	// The plate as entered: the bore in SI, the taps, and no C (ISO 5167-2's, the default).
	const o1 = sent.at(-1)!.project.components.find((c) => c.id === 'O1');
	expect(o1).toMatchObject({ type: 'orifice', boreDiameter: 0.05, taps: 'flange' });
	expect(o1).not.toHaveProperty('dischargeCoefficient');

	await expect(
		resultsPane(page).getByRole('tablist', { name: 'Results view' }).getByRole('tab')
	).toHaveText(['Summary', 'Nodes', 'Links', 'Orifices', 'Boundaries', 'Methods']);
	const { plate, shown, rows } = await readPlate(page, solved);
	within(plate.flow, 0.0130855);
	within(plate.pressureLoss, 42483.2);
	within(plate.differentialPressure!, 57142.4);
	within(plate.pressureDrop, 42483.2);
	within(plate.headLoss, 4.33987);
	expect(plate.beta).toBeCloseTo(0.05 / D, 12);
	expect(plate.pipeDiameter).toBe(D);
	within(plate.dischargeCoefficient, 0.604705);
	within(plate.reynoldsNumber, 162376);
	expect(shown.source).toBe('ISO 5167-2');
	expect(plate.taps).toBe('flange');
	// One elevation and one bore at both ports: the static drop is the loss (§3.7).
	expect(Math.abs(plate.pressureDrop - plate.pressureLoss)).toBeLessThan(1);
	// Inside ISO 5167-2's range, forward flow, no flashing: no flag about O1.
	expect(solved.flags.filter((f) => f.componentId === 'O1')).toEqual([]);

	// The strip beside O1 in Build: the table's own cells.
	await showPlate(page);
	const strip = plateStrip(page);
	expect(await stripLabels(strip)).toEqual([
		'Flow (+ inlet → outlet) (L/s)',
		'Permanent loss (kPa)',
		'Differential pressure (taps) (kPa)'
	]);
	expect(await stripValue(strip, 'Flow (+ inlet → outlet) (L/s)')).toBe(shown.flow);
	expect(await stripValue(strip, 'Permanent loss (kPa)')).toBe(shown.loss);
	expect(await stripValue(strip, 'Differential pressure (taps) (kPa)')).toBe(shown.reading);

	// The trace: the bore and the taps the user's, ISO 5167-2's C the default.
	await showPane(page, 'Results');
	const table = await orificeTable(page);
	await table.getByRole('button', { name: new RegExp(`^${ITEM}`) }).click();
	const trace = traceOf(page, ITEM);
	await expect(trace).toBeVisible();
	const inputs = trace.getByRole('region', { name: 'Inputs' });
	for (const [name, source] of [
		[/^Bore diameter d/, 'User'],
		[/^Discharge coefficient C/, 'Default'],
		[/^Pressure taps/, 'User']
	] as const) {
		const input = inputs.getByRole('listitem').filter({ hasText: name });
		await expect(input).toHaveCount(1);
		await expect(input).toContainText(source);
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
	expect(await tableTexts(await orificeTable(reopened))).toEqual(rows);
	await reopened.close();

	// Nothing but the app and its calculation server was contacted (GOALS §4.5).
	expect([...origins].filter((o) => !ALLOWED_ORIGINS.has(o))).toEqual([]);
});

test('Add before inserts it into the line, the bore asked for; the first click adds it', async ({
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

	// Before the valve: into the connection the walk arrived by (a bypass line's placement).
	await panel.getByRole('button', { name: 'Add before' }).click();
	dialog = page.getByRole('dialog', { name: 'Add before Gate valve V1' });
	await dialog
		.getByRole('combobox', { name: 'Component' })
		.selectOption({ label: 'Orifice plate (ISO 5167-2)' });
	const add = dialog.getByRole('button', { name: 'Add', exact: true });
	await add.click();
	await expect(dialog.getByRole('alert')).toHaveText(REQUIRED);
	// Typed, not entered: the press on Add stores it as the field loses focus, and nothing moves
	// under the pointer (the error went as the bore was typed), so the first click adds the plate.
	await dialog.getByRole('textbox', { name: 'Bore diameter (mm)' }).fill('15');
	await expect(dialog.getByRole('alert')).toHaveCount(0);
	await add.click();
	await expect(dialog).toBeHidden();
	await expect(currentHeading(page)).toHaveText(ITEM);
	await expect(panel.getByRole('textbox', { name: 'Bore diameter (mm)' })).toHaveValue('15');
	// Between the reservoir and the valve: Previous names the reservoir, Next the valve.
	await expect(panel.getByRole('button', { name: /^Previous/ })).toHaveText(
		'Previous: Reservoir R1'
	);
	await expect(panel.getByRole('button', { name: /^Next/ })).toHaveText('Next: Gate valve V1');
});

test('scenarios: a bigger bore and a calibrated C; compare and export all cases', async ({
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

	/** A new scenario named `name`, shown, with O1 shown in Build. */
	async function scenario(name: string): Promise<Locator> {
		const manager = await openScenarioManager(page);
		await manager.getByRole('button', { name: 'New scenario' }).click();
		const field = manager.getByRole('textbox', { name: /^Name of scenario S\d+$/ }).last();
		await field.fill(name);
		await field.press('Enter');
		await manager.getByRole('button', { name: 'Done' }).click();
		await expect(manager).toBeHidden();
		return showPlate(page);
	}

	// A second plate: one change, of the bore, marked at its field.
	let panel = await scenario('Bigger bore');
	await setNumber(panel, 'Bore diameter (mm)', '60');
	await expect(
		panel.getByRole('textbox', { name: 'Bore diameter (mm)' })
	).toHaveAccessibleDescription(/Changed in this scenario\. Base value 50 mm\./);
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Bigger bore (1 change)');
	// The taps are installation, the same in every case.
	await expect(panel.getByRole('textbox', { name: 'Pressure taps' })).toHaveAttribute('readonly');

	// A calibrated plate: the C at its flange taps, pending until entered, then one change.
	panel = await scenario('Calibrated');
	await panel
		.getByRole('combobox', { name: 'Discharge coefficient' })
		.selectOption({ label: 'Entered C' });
	await expect(
		panel.getByText("Enter C to use it; until then ISO 5167-2's discharge coefficient applies.")
	).toBeVisible();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Calibrated (0 changes)');
	await setNumber(panel, 'Entered C', '0.62');
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Calibrated (1 change)');
	await expect(
		panel.getByRole('button', {
			name: 'Reset Discharge coefficient to the base value, ISO 5167-2 (default)'
		})
	).toBeVisible();

	// Solve all: the base, then each scenario.
	await (await openCases(page)).getByRole('button', { name: 'Solve all' }).click();
	await expect(caseGroup(page)).not.toContainText('Solving');
	expect(sent.map((r) => r.scenarioId ?? 'base').sort()).toEqual(['S1', 'S2', 'base']);
	// The bodies are read as they arrive: wait for the three.
	await expect.poll(() => Object.keys(solves).sort()).toEqual(['S1', 'S2', 'base']);
	const bigger = solves.S1!.orificeResults.O1!;
	within(bigger.flow, 0.0192555);
	within(bigger.pressureLoss, 35369.1);
	within(bigger.differentialPressure!, 55213.3);
	expect(bigger.boreDiameter).toBe(0.06);
	const calibrated = solves.S2!.orificeResults.O1!;
	within(calibrated.flow, 0.0134147);
	within(calibrated.pressureLoss, 42168.5);
	within(calibrated.differentialPressure!, 57140.9);
	within(calibrated.dischargeCoefficient, 0.619924);
	// The entered C as entered for the reading, moved to D and D/2 tappings for the loss.
	expect(calibrated.coefficientSource).toBe('entered');
	expect(calibrated.meterDischargeCoefficient).toBe(0.62);
	expect(calibrated.tapCoefficientRatio).not.toBeNull();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Calibrated (1 change)');
	const { shown } = await readPlate(page, solves.S2!);
	expect(shown.source).toBe('Entered, moved to D and D/2');

	// Compare: O1's flow and permanent loss among the default rows.
	await showPane(page, 'Results');
	await resultsPane(page).getByRole('tab', { name: 'Compare cases' }).click();
	const compare = resultsPane(page).getByRole('region', { name: 'Compare cases' });
	await expect(
		compare.getByRole('button', { name: `${ITEM} · Flow` }).filter({ visible: true })
	).toHaveCount(1);
	await expect(
		compare.getByRole('button', { name: `${ITEM} · Permanent loss` }).filter({ visible: true })
	).toHaveCount(1);

	// Export, all cases: the Orifice plates sheet holds one row per case.
	await resultsPane(page).locator('[data-export-button]').click();
	const exporting = page.getByRole('dialog', { name: 'Export results' });
	await exporting.getByRole('radio', { name: /^All cases/ }).check();
	await expect(exporting.getByRole('region', { name: 'In the file' })).toContainText(
		'Orifice plates (3)'
	);
	await exporting.getByRole('button', { name: 'Close' }).last().click();
});

test('goal seek: the bore for a flow, in the default bounds, applied as a new scenario', async ({
	page
}) => {
	await buildNetwork(page);
	await solveConverged(page);
	await showPane(page, 'Results');
	await resultsPane(page)
		.getByRole('button', { name: /^Goal seek/ })
		.click();
	const d = page.getByRole('dialog', { name: 'Goal seek' });
	await expect(d).toBeVisible();

	await d.getByRole('button', { name: 'Add goal' }).click();
	const goalForm = d.getByRole('group', { name: 'New goal' });
	await goalForm.getByRole('combobox', { name: 'Element' }).selectOption({ label: ITEM });
	await goalForm.getByRole('radio', { name: 'Flow', exact: true }).check();
	await goalForm.getByRole('button', { name: 'Add goal' }).click();
	const goal = d.getByRole('group', { name: new RegExp(`${ITEM} · Flow$`) });
	await setNumber(goal, /^Target/, '12');

	await d.getByRole('button', { name: 'Add variable' }).click();
	const variableForm = d.getByRole('group', { name: 'New variable' });
	await variableForm.getByRole('combobox', { name: 'Element' }).selectOption({ label: ITEM });
	await variableForm.getByRole('radio', { name: 'Bore diameter', exact: true }).check();
	await variableForm.getByRole('button', { name: 'Add variable' }).click();
	const variable = d.getByRole('group', { name: new RegExp(`${ITEM} · Bore diameter$`) });
	// ISO 5167-2's β range on the last solve's pipe bore, 0.1 D to 0.75 D (6 digits).
	await expect(variable.getByText('Defaults: 10.226 mm to 76.695 mm.')).toBeVisible();
	await expect(variable.getByText('Now 50 mm')).toBeVisible();

	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/goal-seek') && r.request().method() === 'POST'
	);
	await d.getByRole('button', { name: /^Run goal seek/ }).click();
	const response = await answer;
	expect(response.status(), (await response.text()).slice(0, 500)).toBe(200);
	const request = response.request().postDataJSON() as GoalSeekRequest;
	const body = (await response.json()) as GoalSeekResponse;
	expect(request.goals).toEqual([{ quantity: 'orifice_flow', elementId: 'O1', target: 0.012 }]);
	expect(request.variables).toEqual([
		{
			kind: 'component',
			componentId: 'O1',
			field: 'boreDiameter',
			lower: 0.1 * D,
			upper: 0.75 * D
		}
	]);
	expect(body.success).toBe(true);
	await expect(d.getByText('Goal met', { exact: true })).toBeVisible();
	const found = body.result.variables[0]!.value;
	// Near the synthesizer's 48.0331 mm: the flow within its tolerance moves the bore less.
	within(found!, 0.0480331);
	within(body.solvedState!.orificeResults.O1!.flow, 0.012);

	await d.getByRole('button', { name: 'Apply as new scenario' }).click();
	await expect(d).toBeHidden();
	await expect(caseMenu(page).locator('option:checked')).toHaveText('Goal seek 1 (1 change)');
	await expect(resultsPane(page).getByRole('status')).toHaveText(
		'Last solve of Goal seek 1: converged'
	);
	const panel = await showPlate(page);
	await expect(
		panel.getByRole('textbox', { name: 'Bore diameter (mm)' })
	).toHaveAccessibleDescription(/Changed in this scenario\. Base value 50 mm\./);
});
