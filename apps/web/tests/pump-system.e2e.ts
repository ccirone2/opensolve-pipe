import { gzipSync } from 'node:zlib';
import { expect, test, type Page, type Request } from '@playwright/test';
import type {
	ControlValve,
	SolveRequest,
	SystemCurveRequest,
	SystemCurveResponse
} from '../src/lib/api/types';
import { pumpTransferExample } from '../src/lib/utils/examples';
import { IMPERIAL_UNITS } from '../src/lib/utils/units';
import {
	addAfter,
	addFirst,
	ALLOWED_ORIGINS,
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
	tableTexts,
	toldText,
	traceOf
} from './support';
import { WEB_ORIGIN } from './servers';

/**
 * Build a pump system through the UI from a new project, solve it, read the results, share it,
 * and reopen the link: the same project gives the same results.
 *
 * Network (illustrative test input: made-up elevations and pump curve):
 *   Reservoir R1 (0 m) → 10 m pipe → Pump P1 → 10 m pipe → Gate valve V1 → 10 m pipe → Reservoir R2
 *   (10 m higher). Pipes: the default carbon steel schedule 40, NPS 4. Pump curve at rated
 *   speed: 0 L/s at 20 m, 10 L/s at 19 m, 20 L/s at 16 m, 30 L/s at 11 m.
 */
const CURVE = [
	{ flow: '0', head: '20' },
	{ flow: '10', head: '19' },
	{ flow: '20', head: '16' },
	{ flow: '30', head: '11' }
];
const LIFT = 10; // m, R2 above R1 (both open to the air, liquid level 0)

/** The system-curve requests a page makes (D10: on demand, cached per solve). */
function systemCurveRequests(page: Page): Request[] {
	const requests: Request[] = [];
	page.on('request', (r) => {
		if (r.url().endsWith('/api/v1/system-curve')) requests.push(r);
	});
	return requests;
}

/** The results as displayed: tables and texts compared between the two solves. */
async function displayedResults(page: Page) {
	await showPane(page, 'Results');
	const summary = await resultsView(page, 'Summary');
	const pumpLine = (
		await summary.getByRole('region', { name: 'Pumps' }).getByRole('listitem').innerText()
	).replace(/\s+/g, ' ');
	const tables: Record<string, string[]> = {};
	for (const [view, caption] of [
		['Nodes', 'Results per component port'],
		['Links', 'Results per pipe connection'],
		['Pumps', 'Results per pump'],
		['Valves', 'Results per valve'],
		['Boundaries', 'Results per boundary']
	] as const) {
		const panel = await resultsView(page, view);
		tables[view] = await tableTexts(panel.getByRole('table', { name: caption }));
		if (view === 'Pumps') {
			// The chart shows the pump's system curve once computed for this solve.
			await expect(
				panel.getByRole('figure', { name: 'Pump and system curves: Pump P1' }).getByRole('img')
			).toHaveAccessibleName(/ and system curve; operating point /);
		}
	}
	return { pumpLine, tables };
}

test('build a pump system from a new project, solve, share and reopen it', async ({
	page,
	context,
	baseURL
}) => {
	const origins = new Set<string>();
	context.on('request', (request) => origins.add(new URL(request.url()).origin));
	const curveRequests = systemCurveRequests(page);
	// Run as in the oldest browsers of the build target (Vite's 'baseline-widely-available',
	// e.g. Safari 16.4–17.3), which have no AbortSignal.any: Vite does not polyfill APIs.
	await context.addInitScript(() => {
		Reflect.deleteProperty(AbortSignal, 'any');
	});
	await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: baseURL });

	// --- Build, entirely through the panel navigator.
	await newProject(page);
	expect(await page.evaluate(() => 'any' in AbortSignal)).toBe(false);
	const panel = buildPane(page);
	await addFirst(page, 'Reservoir', 'Reservoir R1');
	await addAfter(page, 'Pump', 'Pump P1');

	// The new pump has no curve yet: enter four points in the curve table.
	const curve = panel.getByRole('region', { name: 'Pump curve' });
	await expect(curve.getByText('This pump needs a curve.')).toBeVisible();
	await curve.getByRole('button', { name: 'Add point' }).click();
	for (const [i, point] of CURVE.entries()) {
		await setNumber(curve, `Point ${i + 1} flow (L/s)`, point.flow);
		await setNumber(curve, `Point ${i + 1} head (m)`, point.head);
	}
	// Saved to the project's pump library and used by the pump.
	await expect(curve.getByText('This pump needs a curve.')).toBeHidden();
	await expect(curve.getByRole('combobox', { name: 'Pump curve' })).toHaveValue('C1');
	await expect(curve.getByRole('table', { name: 'Head curve (at rated speed)' })).toBeVisible();
	for (const [i, point] of CURVE.entries()) {
		await expect(curve.getByRole('textbox', { name: `Point ${i + 1} head (m)` })).toHaveValue(
			point.head
		);
	}

	await addAfter(page, 'Gate valve', 'Gate valve V1');
	await addAfter(page, 'Reservoir', 'Reservoir R2');
	await setNumber(panel, /^Elevation/, String(LIFT));

	// The walk so far, and nothing left unconnected.
	await expect(page.getByRole('navigation', { name: 'Path' }).getByRole('button')).toHaveText([
		'Reservoir R1',
		'Pump P1',
		'Gate valve V1',
		'Reservoir R2'
	]);
	await expect(panel.getByRole('button', { name: /^Next/ })).toBeDisabled();
	await showPane(page, 'Results');
	await expect(resultsPane(page).getByRole('heading', { name: /^Inputs to check/ })).toHaveCount(0);

	// --- Solve and read the results. The solve carries no system curve (D10).
	const solveSent = page.waitForRequest(
		(r) => r.url().endsWith('/api/v1/solve') && r.method() === 'POST'
	);
	const solved = await solveConverged(page);
	const solveRequest = (await solveSent).postDataJSON() as SolveRequest;
	expect(solved.pumpResults.P1!.systemCurve).toBeNull();
	expect(curveRequests).toHaveLength(0);
	const pump = solved.pumpResults.P1!;
	const flow = pump.operatingFlow * 1000; // L/s
	const head = pump.operatingHead; // m
	// The operating point is on the entered curve, between its 20 and 30 L/s points, and the
	// pump lifts the water the 10 m to R2 plus the losses.
	expect(flow).toBeGreaterThan(20);
	expect(flow).toBeLessThan(30);
	expect(head).toBeGreaterThan(LIFT);
	expect(head).toBeLessThan(16);

	// Summary: the pump's operating point as displayed.
	await showPane(page, 'Results');
	const summary = await resultsView(page, 'Summary');
	const operating = `${sig4(flow)} L/s at ${sig4(head)} m`;
	await expect(summary.getByRole('region', { name: 'Pumps' }).getByRole('listitem')).toContainText(
		`Pump P1 ${operating}`
	);

	// Links: one series path, so every connection carries the pump's flow.
	const links = (await resultsView(page, 'Links')).getByRole('table', {
		name: 'Results per pipe connection'
	});
	const lossesShown: string[] = [];
	for (const name of [
		'Reservoir R1 → Pump P1',
		'Pump P1 → Gate valve V1',
		'Gate valve V1 → Reservoir R2'
	]) {
		expect(await cellText(links, name, 'Flow L/s')).toBe(sig4(flow));
		lossesShown.push(await cellText(links, name, 'Head loss m'));
	}
	const valves = (await resultsView(page, 'Valves')).getByRole('table', {
		name: 'Results per valve'
	});
	lossesShown.push(await cellText(valves, 'Gate valve V1', 'Head loss m'));
	expect(await cellText(valves, 'Gate valve V1', 'State')).toBe('Open');

	// Energy balance from the displayed numbers: pump head = lift + pipe and valve losses,
	// within the rounding of the values shown. Showing the pump computes its system curve, for
	// the project exactly as solved.
	const curveAnswer = page.waitForResponse((r) => r.url().endsWith('/api/v1/system-curve'));
	const pumps = await resultsView(page, 'Pumps');
	const curveResponse = await curveAnswer;
	expect(curveResponse.status()).toBe(200);
	const curveRequest = curveResponse.request().postDataJSON() as SystemCurveRequest;
	expect(curveRequest.pumpId).toBe('P1');
	expect(curveRequest.project).toEqual(solveRequest.project);
	const systemCurve = (await curveResponse.json()) as SystemCurveResponse;
	expect(systemCurve.points).toHaveLength(41);
	expect(systemCurve.converged.every(Boolean)).toBe(true);
	// The operating point lies on the system curve: the system heads at the flows either side of
	// it bracket the pump's head there.
	const below = systemCurve.points.filter((p) => p.flow <= pump.operatingFlow).at(-1)!;
	const above = systemCurve.points.find((p) => p.flow >= pump.operatingFlow)!;
	expect(below.head!).toBeLessThanOrEqual(pump.operatingHead);
	expect(above.head!).toBeGreaterThanOrEqual(pump.operatingHead);
	const table = pumps.getByRole('table', { name: 'Results per pump' });
	const headShown = await cellText(table, 'Pump P1', 'Head m');
	expect(headShown).toBe(sig4(head));
	expect(await cellText(table, 'Pump P1', 'Flow L/s')).toBe(sig4(flow));
	expect(await cellText(table, 'Pump P1', 'Status')).toBe('Running');
	const losses = lossesShown.reduce((sum, text) => sum + Number(text), 0);
	const rounding = [headShown, ...lossesShown].reduce((sum, text) => sum + halfUlp(text), 0);
	expect(Math.abs(Number(headShown) - (LIFT + losses))).toBeLessThanOrEqual(rounding);

	// The pump chart's data table: the entered curve and the same operating point.
	const chart = pumps.getByRole('figure', { name: 'Pump and system curves: Pump P1' });
	await expect(chart.getByRole('img')).toHaveAccessibleName(
		new RegExp(`operating point ${sig4(flow)} L/s at ${sig4(head)} m`)
	);
	await chart.getByRole('button', { name: 'Show data table' }).click();
	await expect(chart.getByText(`Operating point: ${operating}`)).toBeVisible();
	const curveTable = chart.getByRole('table', { name: 'Pump curve at 100 % speed' });
	await expect(curveTable.getByRole('row').nth(1)).toHaveText(/^\s*0\s*20\s*Curve\s*$/);
	const systemTable = chart.getByRole('table', { name: 'System curve' });
	await expect(systemTable).toBeVisible();
	await expect(systemTable.getByRole('row')).toHaveCount(1 + systemCurve.points.length);
	await expect(systemTable.getByRole('row').nth(1)).toHaveText(
		new RegExp(`^\\s*0\\s*${sig4(systemCurve.points[0]!.head!)}\\s*$`)
	);
	await expect(chart.getByText(/Computing the system curve/)).toHaveCount(0);
	await chart.getByRole('button', { name: 'Hide data table' }).click();
	await expect(curveTable).toBeHidden();

	// Where the curve is shown, how it was computed (its response has no trace), and a link to
	// the pump's trace, which defines it (GOALS §4.2).
	await expect(chart.getByText(/^System curve: /)).toContainText(
		`replaced by each of 41 evenly spaced flows from 0 to ` +
			`${sig4(systemCurve.flowRange.max * 1000)} L/s`
	);
	await chart.getByRole('button', { name: 'Trace of Pump P1' }).click();
	await expect(
		traceOf(page, 'Pump P1').getByText(/^H_sys\(Q\) = EGL_discharge − EGL_suction/)
	).toBeVisible();
	await closeTrace(page, 'Pump P1');

	// The pump's trace: the curve points entered above, as user inputs, numbered as in the curve
	// table (the fourth point is 30 L/s), and the equations.
	await table.getByRole('button', { name: /^Pump P1/ }).click();
	const trace = traceOf(page, 'Pump P1');
	await expect(trace).toBeVisible();
	const inputs = trace.getByRole('heading', { name: 'Inputs' });
	await expect(inputs).toBeVisible();
	const point = trace.getByRole('listitem').filter({ hasText: 'Head curve point 4: flow' });
	await expect(point).toContainText('30 L/s');
	await expect(point).toContainText('User');
	await expect(trace.getByRole('heading', { name: 'Equations' })).toBeVisible();
	await expect(trace.getByText(/H = EGL_discharge − EGL_suction/)).toBeVisible();
	await closeTrace(page, 'Pump P1');

	const before = await displayedResults(page);
	// The curve is cached with the solve: showing the pump again sent nothing more.
	expect(curveRequests).toHaveLength(1);

	// --- Share: the link is copied and shown.
	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share this project' });
	await expect(dialog.getByRole('status')).toHaveText('Link copied to the clipboard.');
	const field = dialog.getByRole('textbox', { name: 'Link to this version of the project' });
	expect(new URL(await field.inputValue()).origin).toBe(WEB_ORIGIN);
	await expect(field).toHaveValue(/\/p#[A-Za-z0-9_-]+$/);
	const link = await field.inputValue();
	expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);
	expect(link.length).toBeLessThan(8000);
	await expect(dialog.getByText('This link is longer than')).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Close' }).click();
	await expect(dialog).toBeHidden();

	// --- Reopen the link in a new page and solve again: the same results, as displayed.
	const reopened = await context.newPage();
	await reopened.goto(link);
	await expect(currentHeading(reopened)).toHaveText('Reservoir R1');
	const again = await solveConverged(reopened);
	expect(again.pumpResults.P1!.operatingFlow).toBeCloseTo(pump.operatingFlow, 12);
	expect(again.pumpResults.P1!.operatingHead).toBeCloseTo(pump.operatingHead, 10);
	const after = await displayedResults(reopened);
	expect(after).toEqual(before);
	expect(after.pumpLine).toContain(operating);
	// Solved with the same calculation methods as the shared link: no notice.
	await expect(resultsPane(reopened).getByText('Calculation methods changed')).toHaveCount(0);

	// Only the app and its calculation server were contacted (GOALS §4.5).
	expect([...origins].filter((o) => !ALLOWED_ORIGINS.has(o))).toEqual([]);
});

test('a system-curve point without a head says why, with names and in the display units', async ({
	page
}) => {
	// The pump-transfer example in US units, with its isolation valve replaced by an FCV named
	// "Flow limiter" set to 15 L/s (made-up test inputs): every way from the pump's discharge back
	// to its suction passes the FCV, so no forced flow above 15 L/s has a steady state.
	const project = pumpTransferExample();
	project.settings.units = { ...IMPERIAL_UNITS };
	const fcv: ControlValve = {
		type: 'valve',
		valveType: 'fcv',
		id: 'V1',
		name: 'Flow limiter',
		elevation: 0,
		status: 'active',
		setpoint: 0.015,
		ports: project.components[2]!.ports
	};
	project.components[2] = fcv;
	const encoded = gzipSync(Buffer.from(JSON.stringify(project))).toString('base64url');
	await page.goto(`/p#${encoded}`);
	await expect(currentHeading(page)).toHaveText('Suction tank');
	await solveConverged(page);

	const answer = page.waitForResponse((r) => r.url().endsWith('/api/v1/system-curve'));
	const pumps = await resultsView(page, 'Pumps');
	const curve = (await (await answer).json()) as SystemCurveResponse;
	const index = curve.points.findIndex((p) => p.head === null);
	const point = curve.points[index]!;
	expect(point.flow).toBeGreaterThan(0.015);
	expect(point).toMatchObject({
		reason: 'beyond_limit',
		componentIds: ['V1'],
		assignedFlowNodeIds: [],
		limitFlow: 0.015,
		passedFlow: 0.015
	});
	expect(point.message).toContain("passes FCV 'V1', which passes at most 0.015 m³/s that way");

	const chart = pumps.getByRole('figure', { name: 'Pump and system curves: Transfer pump' });
	await expect(chart.getByRole('img')).toHaveAccessibleName(/ and system curve; operating point /);
	await chart.getByRole('button', { name: 'Show data table' }).click();
	const table = chart.getByRole('table', { name: 'System curve' });
	await expect(table.getByRole('columnheader')).toHaveText([
		'Flow (gpm)',
		'Head (ft)',
		'Why no head'
	]);
	const GPM = (231 * 0.0254 ** 3) / 60; // m³/s
	const row = table.getByRole('row').nth(index + 1);
	await expect(row.getByRole('cell').first()).toHaveText(sig4(point.flow / GPM));
	const why = row.getByRole('cell').nth(2);
	expect(await toldText(why)).toBe(
		"No steady state carries this flow: every way from the pump's discharge back to its suction, " +
			'through the network or a reservoir or reference node, passes Flow limiter, which passes at ' +
			`most ${sig4(0.015 / GPM)} gpm that way (an FCV passes neither reverse flow nor more than ` +
			'its flow setpoint).'
	);
	// The API's own sentence is kept under Details, closed until asked for.
	const server = why.getByText(`Calculation server's message: ${point.message}`);
	await expect(server).toBeHidden();
	await why.getByText('Details', { exact: true }).click();
	await expect(server).toBeVisible();
	// The words fit the screen: no sideways scroll of the page, on a phone too.
	expect(
		await page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		)
	).toBe(0);
});
