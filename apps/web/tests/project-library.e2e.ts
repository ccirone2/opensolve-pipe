import { expect, test, type Locator, type Page } from '@playwright/test';
import type { PipeDefinition, SolveRequest } from '../src/lib/api/types';
import {
	ALLOWED_ORIGINS,
	buildPane,
	closeTrace,
	currentHeading,
	resultsView,
	setNumber,
	showPane,
	solveConverged,
	traceOf
} from './support';

/**
 * The project library (CLAUDE.md D21; proposal project-library.md §7.4), on desktop and mobile,
 * solved against the real API, on the pump transfer example:
 *
 *   Suction tank → NPS 4 → Transfer pump → NPS 3 → Discharge isolation valve (gate) → NPS 3 (60 m,
 *   4 elbows, exit) → Discharge tank
 *
 * A pipe spec is defined in the library (its errors first: nothing but the material has a
 * default), used for every pipe of the valve's outlet size (the pump's discharge pipe and the
 * valve's outlet pipe: 2 pipes, one undo step), solved, and its source found in a trace. A Cv entry
 * is defined from the valve's resistance ("New entry…"), used there in the same step, solved and
 * cited; the library then refuses to delete it, naming the valve. Test inputs (made up): a 78 mm
 * measured bore on carbon steel, a Cv of 250.
 */

const SPEC = 'NPS 3 measured bore';
const SPEC_SOURCE = 'Test input: a made-up bore, not data for a real pipe';
const ENTRY = 'Gate valve, open';
const ENTRY_SOURCE = 'Test input: a made-up Cv, not data for a real valve';
const VALVE = 'Discharge isolation valve';
const OUTLET_PIPING = `${VALVE} → Discharge tank`;
const NAME_ERROR = 'Enter a name: results and lists show the entry by it.';
const SOURCE_ERROR =
	'Enter where the values come from (a standard and its table, a datasheet, a measurement): every result that uses the entry cites it.';

/** Open the pump transfer example from the home page. */
async function openExample(page: Page): Promise<void> {
	await page.goto('/');
	await page.getByRole('link', { name: /Pump transfer/ }).click();
	await expect(page.getByRole('textbox', { name: 'Project name' })).toHaveValue(
		'Pump transfer between two tanks'
	);
}

/** Open the library from the header's Project toolbar. */
async function openLibrary(page: Page): Promise<Locator> {
	await page
		.getByRole('toolbar', { name: 'Project' })
		.getByRole('button', { name: 'Project library' })
		.click();
	const dialog = page.getByRole('dialog', { name: 'Project library' });
	await expect(dialog).toBeVisible();
	return dialog;
}

/** Show a component in Build (Jump to), on its form. */
async function jumpTo(page: Page, name: string): Promise<void> {
	await showPane(page, 'Build');
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	await page
		.getByRole('dialog', { name: 'Jump to a component' })
		.getByRole('button', { name: new RegExp(`^${name}`) })
		.click();
	await expect(currentHeading(page)).toHaveText(name);
}

/** Type into a text field and store it (Enter for a line, leaving the field for a text area). */
async function setText(scope: Locator, name: string, value: string): Promise<void> {
	const field = scope.getByRole('textbox', { name, exact: true });
	await field.fill(value);
	await field.blur();
	await expect(field).toHaveValue(value);
}

/** The pipes the last solve was sent with, by connection id. */
const pipesSent = (request: SolveRequest, connectionId: string): PipeDefinition[] =>
	request.project.connections.find((c) => c.id === connectionId)?.piping.pipes ?? [];

test('a pipe spec from the library, used for every pipe of a size and cited in the trace', async ({
	page
}) => {
	const origins = new Set<string>();
	page.on('request', (request) => origins.add(new URL(request.url()).origin));
	await openExample(page);

	const library = await openLibrary(page);
	const specsTab = library.getByRole('tab', { name: 'Pipe specs (0)' });
	await expect(specsTab).toHaveAttribute('aria-selected', 'true');
	await library.getByRole('button', { name: 'New pipe spec' }).click();
	const form = library.getByRole('region', { name: 'New pipe spec' });
	await expect(form.getByRole('textbox', { name: 'Name', exact: true })).toBeFocused();
	// Nothing but the material has a default: Add names what is missing, each at its field.
	await library.getByRole('button', { name: 'Add', exact: true }).click();
	await expect(form.getByRole('alert')).toHaveText([
		NAME_ERROR,
		'Enter the inner diameter.',
		SOURCE_ERROR
	]);
	await setText(form, 'Name', SPEC);
	await expect(form.getByRole('combobox', { name: 'Material' })).toHaveValue('carbon_steel');
	await setNumber(form, 'Inner diameter (mm)', '78');
	await setText(form, 'Source', SPEC_SOURCE);
	await expect(form.getByRole('alert')).toHaveCount(0);
	await library.getByRole('button', { name: 'Add', exact: true }).click();

	// The list, with the new spec in view and its values, source and use.
	await expect(library.getByRole('tab', { name: 'Pipe specs (1)' })).toBeVisible();
	const card = library.getByRole('region', { name: new RegExp(`^${SPEC}`) });
	await expect(card.getByRole('heading', { name: new RegExp(`^${SPEC}`) })).toBeFocused();
	await expect(card).toContainText('Carbon steel');
	await expect(card).toContainText('78 mm');
	await expect(card).toContainText(`Source: ${SPEC_SOURCE}`);
	await expect(card).toContainText('Not used.');
	await library.getByRole('button', { name: 'Done' }).click();
	await expect(library).toBeHidden();

	// The valve's outlet pipe: use the spec for every pipe of its size and material.
	await jumpTo(page, VALVE);
	const panel = buildPane(page);
	await panel.getByRole('tab', { name: 'Piping' }).click();
	await panel
		.getByRole('group', { name: `Ports of ${VALVE}` })
		.getByRole('button', { name: /^Outlet/ })
		.click();
	await panel.getByRole('button', { name: /^Use a pipe spec for pipe 1/ }).click();
	const use = page.getByRole('dialog', { name: 'Use a pipe spec' });
	await expect(use.getByRole('combobox', { name: 'Pipe spec' })).toHaveValue('PS1');
	const same = use.getByRole('radio', { name: /^Every pipe of the same material and size/ });
	await expect(same).toBeChecked();
	await expect(use.getByRole('status')).toContainText('2 pipes will use “NPS 3 measured bore”');
	await use.getByRole('button', { name: 'Use for 2 pipes' }).click();
	await expect(use).toBeHidden();
	await expect(page.getByText('2 pipes now use “NPS 3 measured bore”.')).toBeVisible();

	// The pipe shows the spec's values read-only, with its source.
	await expect(panel.getByRole('combobox', { name: 'Material' })).toHaveValue('spec:PS1');
	await expect(panel.getByRole('textbox', { name: /^Length/ })).toHaveValue('60');
	await expect(panel.getByText(`Source: ${SPEC_SOURCE}`)).toBeVisible();
	await expect(panel.getByRole('button', { name: `Edit ${SPEC} in the library` })).toBeVisible();

	// Solved against the real API: the two pipes refer to the spec, and keep their lengths.
	const solve = page.waitForRequest((r) => r.url().endsWith('/api/v1/solve'));
	await solveConverged(page);
	const request = (await solve).postDataJSON() as SolveRequest;
	expect(request.project.pipeLibrary?.map((s) => s.id)).toEqual(['PS1']);
	expect(pipesSent(request, 'L2')).toEqual([{ specId: 'PS1', length: 3 }]);
	expect(pipesSent(request, 'L3')).toEqual([{ specId: 'PS1', length: 60 }]);
	expect(pipesSent(request, 'L1')[0]?.specId).toBeUndefined();

	// The valve's outlet piping's trace cites the spec, and links to it.
	await showPane(page, 'Results');
	const links = await resultsView(page, 'Links');
	await links.getByRole('button', { name: new RegExp(`^${OUTLET_PIPING}`) }).click();
	const trace = traceOf(page, OUTLET_PIPING);
	const cited = trace.getByRole('button', {
		name: `project library pipe spec "${SPEC}" (PS1)`
	});
	await expect(cited.first()).toBeVisible();
	await expect(trace.getByText(SPEC_SOURCE).first()).toBeVisible();
	await cited.first().click();
	const shown = page.getByRole('dialog', { name: 'Project library' });
	await expect(shown.getByRole('heading', { name: new RegExp(`^${SPEC}`) })).toBeFocused();
	await expect(
		shown.getByRole('region', { name: new RegExp(`^${SPEC}`) }).getByText('Used by 2')
	).toBeVisible();
	await shown.getByRole('button', { name: 'Done' }).click();
	await closeTrace(page, OUTLET_PIPING);

	// One undo step puts both pipes back on their own size.
	await showPane(page, 'Build');
	const undo = page.getByRole('button', { name: /^Undo/ });
	await expect(undo).toHaveAccessibleName(`Undo use pipe spec ${SPEC} for 2 pipes`);
	await undo.click();
	await expect(panel.getByRole('combobox', { name: 'Material' })).toHaveValue('carbon_steel');
	await expect(undo).toHaveAccessibleName(`Undo add pipe spec ${SPEC}`);
	expect([...origins].every((o) => ALLOWED_ORIGINS.has(o))).toBe(true);
});

test('a Cv entry made from a valve, used there, cited, and kept while in use', async ({ page }) => {
	await openExample(page);
	await jumpTo(page, VALVE);
	const panel = buildPane(page);
	const resistance = panel.getByRole('combobox', { name: 'Resistance given as' });
	// As a keyboard user does: the focus on the list, then the choice.
	await resistance.focus();
	await resistance.selectOption({ label: 'New entry…' });

	// The library opens on a new entry's form; saving uses the entry for the valve.
	const library = page.getByRole('dialog', { name: 'Project library' });
	const form = library.getByRole('region', { name: 'New resistance entry' });
	await expect(form.getByRole('textbox', { name: 'Name', exact: true })).toBeFocused();
	await expect(form.getByRole('combobox', { name: 'Given as' })).toHaveValue('Cv');
	await setText(form, 'Name', ENTRY);
	await setNumber(form, 'Cv', '250');
	await setText(form, 'Source', ENTRY_SOURCE);
	await library.getByRole('button', { name: `Save and use for ${VALVE}` }).click();
	await expect(library).toBeHidden();
	await expect(resistance).toBeFocused();
	await expect(resistance).toHaveValue('entry:RS1');
	await expect(panel.getByText('Cv 250', { exact: true })).toBeVisible();
	await expect(panel.getByText(`Source: ${ENTRY_SOURCE}`)).toBeVisible();
	// One undo step made the entry and used it.
	await expect(page.getByRole('button', { name: /^Undo/ })).toHaveAccessibleName(
		`Undo add resistance entry ${ENTRY} for ${VALVE}`
	);

	const solve = page.waitForRequest((r) => r.url().endsWith('/api/v1/solve'));
	await solveConverged(page);
	const request = (await solve).postDataJSON() as SolveRequest;
	const valve = request.project.components.find((c) => c.id === 'V1');
	expect(valve?.type === 'valve' && valve.resistance).toEqual({ kind: 'library', id: 'RS1' });
	expect(request.project.resistanceLibrary).toEqual([
		{ id: 'RS1', name: ENTRY, source: ENTRY_SOURCE, kind: 'Cv', value: 250 }
	]);

	// The valve's trace cites the entry.
	await showPane(page, 'Results');
	const valves = await resultsView(page, 'Valves');
	await valves.getByRole('button', { name: new RegExp(`^${VALVE}`) }).click();
	const trace = traceOf(page, VALVE);
	await expect(
		trace.getByRole('button', { name: `project library resistance "${ENTRY}" (RS1)` }).first()
	).toBeVisible();
	await expect(trace.getByText(ENTRY_SOURCE).first()).toBeVisible();
	await closeTrace(page, VALVE);

	// Delete is refused while the valve uses the entry, naming it; the entry stays.
	const opened = await openLibrary(page);
	await opened.getByRole('tab', { name: 'Resistances (1)' }).click();
	await opened.getByRole('button', { name: `Delete ${ENTRY}` }).click();
	await expect(opened.getByRole('alert')).toHaveText(
		`Not deleted: ${VALVE} uses this entry. An entry can be deleted once nothing uses it.`
	);
	await expect(opened.getByRole('tab', { name: 'Resistances (1)' })).toBeVisible();
	await expect(opened.getByText('Used by 1')).toBeVisible();
	await opened.getByRole('button', { name: 'Done' }).click();
});

test('the header keeps its fit with Library, idle and while a solve runs, and a double click on Cancel stays there', async ({
	page
}, testInfo) => {
	test.skip(testInfo.project.name !== 'mobile', 'narrow-screen check');
	const overflow = () =>
		page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		);
	const toolbar = page.getByRole('toolbar', { name: 'Project' });
	const library = toolbar.getByRole('button', { name: 'Project library' });
	for (const width of [320, 390]) {
		await page.setViewportSize({ width, height: 700 });
		await openExample(page);
		await expect(library).toBeVisible();
		expect(await overflow()).toBe(0);
		// A solve held in flight: Cancel comes in, Library gives it room, nothing scrolls sideways.
		await page.route('**/api/v1/solve', () => {});
		await toolbar.getByRole('button', { name: /^Solve/ }).click();
		await expect(toolbar.getByRole('button', { name: 'Cancel solve' })).toBeVisible();
		await expect(library).toBeHidden();
		expect(await overflow()).toBe(0);
		const settings = (await toolbar.getByRole('button', { name: 'Settings' }).boundingBox())!;
		expect(settings.x + settings.width).toBeLessThanOrEqual(width);
		// Cancel goes, and Library comes back under the pointer: a double click does not open it.
		await toolbar.getByRole('button', { name: 'Cancel solve' }).dblclick();
		await expect(library).toBeVisible();
		await expect(page.getByRole('dialog', { name: 'Project library' })).toHaveCount(0);
		await page.unroute('**/api/v1/solve');
	}
});
