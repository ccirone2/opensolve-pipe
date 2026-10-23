import { gzipSync } from 'node:zlib';
import { expect, test, type Locator, type Page } from '@playwright/test';
import type { Pump, PumpResult, SolvedState, SystemCurveResponse } from '../src/lib/api/types';
import { pumpTransferExample } from '../src/lib/utils/examples';
import {
	ALLOWED_ORIGINS,
	buildPane,
	cellText,
	currentHeading,
	down4,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	sig4,
	solve,
	solveConverged,
	tableTexts
} from './support';

/**
 * A speed-controlled pump (CLAUDE.md D11, flow control) through the UI against the real API: the
 * pump-transfer example's pump is switched to flow control, solved, and its solved speed and
 * state read in the results table and the pump chart; the link is shared and reopened with the
 * same results; an unreachable setpoint runs the pump at its maximum speed with the information
 * flag; switching back to fixed speed is undone in one step. A setpoint that no speed up to the
 * maximum can hold on the curve is rejected, and told with names and the bound in display units.
 *
 * Network: the home page's pump-transfer example (illustrative, made-up inputs), whose pump curve
 * at rated speed is 0 L/s at 30 m, 10 L/s at 28 m, 20 L/s at 22 m and 30 L/s at 12 m. The flow
 * setpoints and the minimum speed below are made-up test inputs.
 */
type Point = { flow: number; head: number };
const CURVE: Point[] = [
	{ flow: 0, head: 30 },
	{ flow: 10, head: 28 },
	{ flow: 20, head: 22 },
	{ flow: 30, head: 12 }
]; // L/s, m
const SETPOINT = 15; // L/s, below the fixed-speed operating flow, so the drive slows the pump
const MIN_SPEED = 40; // %
const UNREACHABLE = 40; // L/s, above what the pump delivers at its maximum speed

const pumpTable = async (page: Page) =>
	(await resultsView(page, 'Pumps')).getByRole('table', { name: 'Results per pump' });

const pumpChart = (page: Page) =>
	resultsPane(page).getByRole('figure', { name: 'Pump and system curves: Transfer pump' });

/** Open the pump-transfer example and walk to its pump. */
async function openExamplePump(page: Page) {
	await page.goto('/');
	await page.getByRole('link', { name: /^Pump transfer/ }).click();
	await expect(page).toHaveURL(/\/p#[A-Za-z0-9_-]+$/);
	await expect(currentHeading(page)).toHaveText('Suction tank');
	await buildPane(page).getByRole('button', { name: /^Next/ }).click();
	await expect(currentHeading(page)).toHaveText('Transfer pump');
}

/**
 * The element is wholly in the viewport and not covered (e.g. by the panel's Previous/Next bar):
 * the element at its centre is inside it.
 */
async function expectInView(locator: Locator) {
	await expect(locator).toBeInViewport({ ratio: 1 });
	await expect
		.poll(() =>
			locator.evaluate((element) => {
				const box = element.getBoundingClientRect();
				const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
				return !!hit && element.contains(hit);
			})
		)
		.toBe(true);
}

/**
 * The speed s the API reports is consistent with the entered curve: at x = Q/s the monotone
 * cubic through monotone points (Fritsch–Carlson) lies between the heads of the points either
 * side, so s²·H(x_{i+1}) ≤ H ≤ s²·H(x_i) for the head H the pump adds.
 */
function expectSpeedOnCurve(pump: PumpResult) {
	const x = (pump.operatingFlow * 1000) / pump.speed; // L/s at rated speed
	const i = CURVE.findIndex(
		(p, k) => k + 1 < CURVE.length && x >= p.flow && x <= CURVE[k + 1]!.flow
	);
	expect(i, `Q/s = ${x} L/s inside the curve's points`).toBeGreaterThanOrEqual(0);
	const s2 = pump.speed ** 2;
	expect(pump.operatingHead).toBeGreaterThanOrEqual(s2 * CURVE[i + 1]!.head - 1e-9);
	expect(pump.operatingHead).toBeLessThanOrEqual(s2 * CURVE[i]!.head + 1e-9);
}

test('switch a pump to flow control, solve, read its speed and state, share and reopen', async ({
	page,
	context
}) => {
	const origins = new Set<string>();
	context.on('request', (request) => origins.add(new URL(request.url()).origin));
	await openExamplePump(page);
	const panel = buildPane(page);

	// --- At fixed speed first: the flow it delivers at its maximum (rated) speed.
	const fixed = (await solveConverged(page)).pumpResults.P1!;
	expect(fixed.control).toBeNull();
	expect(fixed.operatingFlow * 1000).toBeGreaterThan(SETPOINT);
	expect(fixed.operatingFlow * 1000).toBeLessThan(UNREACHABLE);

	// --- Switch to flow control: nothing is written until both values are entered.
	await showPane(page, 'Build');
	const control = panel.getByRole('combobox', { name: 'Control' });
	await control.selectOption({ label: 'Flow control (variable speed)' });
	const note = panel.getByText(/^Enter the flow setpoint and minimum speed to switch/);
	await expect(note).toBeVisible();
	// The note is in view where the choice was made, and describes the Control select.
	await expectInView(note);
	await expect(control).toHaveAccessibleDescription(
		/Enter the flow setpoint and minimum speed to switch to flow control\. Until then the pump runs at a fixed speed\./
	);
	await expect(panel.getByRole('textbox', { name: 'Minimum speed (%)' })).toHaveValue('');
	await expect(panel.getByRole('textbox', { name: 'Maximum speed (%)' })).toHaveValue('100');
	await setNumber(panel, 'Flow setpoint (L/s)', String(SETPOINT));
	await expect(note).toBeVisible();
	await setNumber(panel, 'Minimum speed (%)', String(MIN_SPEED));
	await expect(note).toBeHidden();
	await expect(
		page.getByRole('button', { name: 'Undo switch pump to flow control' })
	).toBeVisible();

	// --- Solve: the pump holds the setpoint at a solved speed between its limits.
	const solved: SolvedState = await solveConverged(page);
	const pump = solved.pumpResults.P1!;
	expect(pump.status).toBe('running');
	expect(pump.control).toEqual({
		mode: 'flow',
		setpoint: SETPOINT / 1000,
		state: 'active',
		setpointAchieved: true
	});
	expect(pump.operatingFlow * 1000).toBeCloseTo(SETPOINT, 9);
	expect(pump.speed).toBeGreaterThan(MIN_SPEED / 100);
	expect(pump.speed).toBeLessThan(1);
	expectSpeedOnCurve(pump);
	expect(solved.flags.filter((f) => f.code === 'PUMP_SETPOINT_NOT_MET')).toEqual([]);

	// The results table: state, setpoint and the solved speed as displayed.
	await showPane(page, 'Results');
	const speedShown = sig4(pump.speed * 100);
	const curveAnswer = page.waitForResponse((r) => r.url().endsWith('/api/v1/system-curve'));
	const table = await pumpTable(page);
	await expect(
		resultsPane(page).getByText(/^Head is the rise in the energy grade line/)
	).toContainText(
		"An off pump has no speed. A speed-controlled pump's speed is the one it runs at"
	);
	expect(await cellText(table, 'Transfer pump', 'Status')).toBe('Running (holding flow setpoint)');
	expect(await cellText(table, 'Transfer pump', 'Control')).toBe(`Flow ${SETPOINT} L/s: held`);
	expect(await cellText(table, 'Transfer pump', 'Speed %')).toBe(speedShown);
	expect(await cellText(table, 'Transfer pump', 'Flow L/s')).toBe(String(SETPOINT));

	// The chart: the curve at the solved speed, through the operating point, which lies on the
	// system curve (the pump's own control replaced by each fixed flow).
	const chart = pumpChart(page);
	await expect(chart.getByRole('img')).toHaveAccessibleName(
		new RegExp(
			`^Pump curve of Transfer pump at ${speedShown.replace('.', '\\.')} % speed \\(flow control\\)`
		)
	);
	const systemCurve = (await (await curveAnswer).json()) as SystemCurveResponse;
	const below = systemCurve.points.filter((p) => p.flow <= pump.operatingFlow).at(-1)!;
	const above = systemCurve.points.find((p) => p.flow >= pump.operatingFlow)!;
	expect(below.head!).toBeLessThanOrEqual(pump.operatingHead + 1e-9);
	expect(above.head!).toBeGreaterThanOrEqual(pump.operatingHead - 1e-9);
	await expect(chart.getByText(/^System curve: /)).toContainText(
		'its flow control replaced by that fixed flow'
	);
	await chart.getByRole('button', { name: 'Show data table' }).click();
	await expect(
		chart.getByRole('table', { name: `Pump curve at ${speedShown} % speed (flow control)` })
	).toBeVisible();
	await expect(chart.getByText(/^Operating point: /)).toContainText(`${SETPOINT} L/s at`);
	const before = await tableTexts(table);

	// --- Share, reopen: the link holds the control, and solves to the same results.
	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share this project' });
	const link = await dialog
		.getByRole('textbox', { name: 'Link to this version of the project' })
		.inputValue();
	await dialog.getByRole('button', { name: 'Close' }).click();
	const reopened = await context.newPage();
	await reopened.goto(link);
	const again = (await solveConverged(reopened)).pumpResults.P1!;
	expect(again.control).toEqual(pump.control);
	expect(again.speed).toBeCloseTo(pump.speed, 12);
	expect(again.operatingHead).toBeCloseTo(pump.operatingHead, 10);
	await showPane(reopened, 'Results');
	expect(await tableTexts(await pumpTable(reopened))).toEqual(before);
	await expect(resultsPane(reopened).getByText('Calculation methods changed')).toHaveCount(0);
	await reopened.close();

	// --- An unreachable setpoint: the pump runs as the fixed-speed pump at its maximum speed.
	await showPane(page, 'Build');
	await setNumber(panel, 'Flow setpoint (L/s)', String(UNREACHABLE));
	const limited = (await solveConverged(page)).pumpResults.P1!;
	expect(limited.control).toEqual({
		mode: 'flow',
		setpoint: UNREACHABLE / 1000,
		state: 'max_speed',
		setpointAchieved: false
	});
	expect(limited.speed).toBe(1);
	// Exactly the fixed-speed pump at that speed: the same flow, within the solver's tolerance.
	expect(limited.operatingFlow).toBeCloseTo(fixed.operatingFlow, 9);
	await showPane(page, 'Results');
	const delivered = `${sig4(limited.operatingFlow * 1000)} L/s`;
	await expect(
		resultsPane(page)
			.getByRole('listitem')
			.filter({
				hasText: `It runs at its maximum speed (100 %) and delivers ${delivered}, below its flow setpoint (${UNREACHABLE} L/s).`
			})
	).toHaveCount(1);
	const limitedTable = await pumpTable(page);
	expect(await cellText(limitedTable, 'Transfer pump', 'Status')).toBe(
		'Running at maximum speed (setpoint not met)'
	);
	expect(await cellText(limitedTable, 'Transfer pump', 'Control')).toBe(
		`Flow ${UNREACHABLE} L/s: ${delivered} at maximum speed`
	);
	expect(await cellText(limitedTable, 'Transfer pump', 'Speed %')).toBe('100');
	await expect(pumpChart(page).getByRole('img')).toHaveAccessibleName(
		/^Pump curve of Transfer pump at 100 % speed \(flow control, at maximum speed\)/
	);

	// --- Back to fixed speed in one edit, and undone in one step.
	await showPane(page, 'Build');
	await control.selectOption({ label: 'Fixed speed' });
	await expect(panel.getByRole('textbox', { name: 'Speed (%)' })).toHaveValue('100');
	await expect(panel.getByRole('textbox', { name: 'Flow setpoint (L/s)' })).toHaveCount(0);
	await page.getByRole('button', { name: 'Undo switch pump to fixed speed' }).click();
	await expect(control).toHaveValue('flow');
	await expect(panel.getByRole('textbox', { name: 'Flow setpoint (L/s)' })).toHaveValue(
		String(UNREACHABLE)
	);
	await expect(panel.getByRole('textbox', { name: 'Minimum speed (%)' })).toHaveValue(
		String(MIN_SPEED)
	);

	// Only the app and its calculation server were contacted (GOALS §4.5).
	expect([...origins].filter((o) => !ALLOWED_ORIGINS.has(o))).toEqual([]);
});

test('a flow control that a maximum speed completes after an undo is written, and solved', async ({
	page
}) => {
	// Undo brings back a maximum speed (60 %) below the minimum speed entered (80 %); entering a
	// maximum speed above it completes the control, which is then in the project and its solve.
	await openExamplePump(page);
	const panel = buildPane(page);
	await setNumber(panel, 'Speed (%)', '60');
	await setNumber(panel, 'Speed (%)', '100');
	const control = panel.getByRole('combobox', { name: 'Control' });
	await control.selectOption({ label: 'Flow control (variable speed)' });
	await setNumber(panel, 'Minimum speed (%)', '80');
	await page.getByRole('button', { name: 'Undo change pump speed' }).click();
	await expect(panel.getByRole('textbox', { name: 'Maximum speed (%)' })).toHaveValue('60');
	await setNumber(panel, 'Flow setpoint (L/s)', String(SETPOINT));
	const note = panel.getByText(/^The minimum speed must be below the maximum speed/);
	await expect(note).toBeVisible();

	await setNumber(panel, 'Maximum speed (%)', '90');
	await expect(note).toBeHidden();
	await expect(control).toHaveValue('flow');
	await expect(
		page.getByRole('button', { name: 'Undo switch pump to flow control' })
	).toBeVisible();
	const { status, body, request } = await solve(page);
	const sent = request.project.components.find((c) => c.id === 'P1') as Pump;
	expect(sent.speed).toBe(0.9);
	expect(sent.control).toEqual({ mode: 'flow', setpoint: SETPOINT / 1000, minSpeed: 0.8 });
	expect(status).toBe(200);
	expect(body.solvedState?.pumpResults.P1?.control).toMatchObject({
		mode: 'flow',
		setpoint: SETPOINT / 1000
	});
});

test("a controlled pump's curve issue: told with its names, and in the server's words once the pump has another curve", async ({
	page
}) => {
	// The pump-transfer example with its pump under flow control on a curve whose head rises
	// steeply between its points (the reference suite's PC-R test curve, made-up points), so the
	// API reports CONTROLLED_PUMP_CURVE; the example's own curve is in the library as C2.
	const project = pumpTransferExample();
	const own = project.pumpLibrary[0]!;
	project.pumpLibrary = [
		{
			id: 'C1',
			name: 'Steep curve',
			points: [
				{ flow: 0, head: 5 },
				{ flow: 0.01, head: 6 },
				{ flow: 0.02, head: 30 },
				{ flow: 0.03, head: 33 },
				{ flow: 0.04, head: 20 }
			]
		},
		{ ...own, id: 'C2', name: 'Good curve' }
	];
	const pump = project.components.find((c) => c.id === 'P1') as Pump;
	pump.curveId = 'C1';
	pump.control = { mode: 'flow', setpoint: SETPOINT / 1000, minSpeed: MIN_SPEED / 100 };
	const encoded = gzipSync(Buffer.from(JSON.stringify(project))).toString('base64url');
	await page.goto(`/p#${encoded}`);
	await expect(currentHeading(page)).toHaveText('Suction tank');
	await buildPane(page).getByRole('button', { name: /^Next/ }).click();
	await expect(currentHeading(page)).toHaveText('Transfer pump');
	const item = resultsPane(page)
		.getByRole('region', { name: 'The network cannot be solved yet' })
		.getByRole('listitem');

	// For the project as it is: told with its names, and the advice points at the rising head.
	expect((await solve(page)).status).toBe(422);
	await showPane(page, 'Results');
	await expect(item).toHaveCount(1);
	await expect(item).toContainText(
		'Transfer pump is speed-controlled, but its pump curve “Steep curve” does not give one speed'
	);
	await expect(item).toContainText(
		'Use a curve whose head rises less steeply with flow there (2·H₀(x) > x·H₀′(x)), or a fixed speed.'
	);

	// Solved again, held until the pump has been given C2.
	let release: () => void = () => {};
	const held = new Promise<void>((resolve) => (release = resolve));
	await page.route('**/api/v1/solve', async (route) => {
		await held;
		await route.continue();
	});
	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await page.getByRole('button', { name: 'Solve', exact: true }).click();
	await showPane(page, 'Build');
	await buildPane(page)
		.getByRole('combobox', { name: 'Pump curve' })
		.selectOption({ label: 'Good curve (C2)' });
	release();
	const response = await answer;
	expect(response.status()).toBe(422);
	const [issue] = ((await response.json()) as { issues: { message: string }[] }).issues;
	expect(issue!.message).toMatch(
		/^pump 'P1' is speed-controlled, but its curve 'C1' \(Steep curve\)/
	);

	await showPane(page, 'Results');
	await expect(item).toHaveCount(1);
	await expect(item).toContainText(issue!.message);
	await expect(item).not.toContainText('Good curve');
	await expect(resultsPane(page).getByRole('status')).toHaveText(
		'Last solve: no results, out of date'
	);
});

test('a flow setpoint no speed can hold on the curve: rejected, and told with its names and bound', async ({
	page
}) => {
	// A setpoint must be below the maximum speed × x_mono (CLAUDE.md D11; the owner's decision of
	// 2026-10-23), x_mono being twice the flow at which the curve's end tangent reaches zero head.
	// The API's curve is SciPy's PchipInterpolator, whose end slope is the one-sided three-point
	// estimate of C. Moler, Numerical Computing with MATLAB (2004), §3.6:
	// d = ((2h₁ + h₂)δ₁ − h₁δ₂)/(h₁ + h₂), with the last interval h₁, δ₁ and the one before h₂, δ₂;
	// here −1.2 m per L/s, of the sign of δ₁ and δ₂, so it is not limited. The tangent
	// 12 − 1.2(x − 30) is zero at 40 L/s: x_mono = 80 L/s, the bound at 100 % maximum speed.
	const [before, prev, last] = CURVE.slice(-3) as [Point, Point, Point];
	const h1 = last.flow - prev.flow;
	const h2 = prev.flow - before.flow;
	const d1 = (last.head - prev.head) / h1;
	const d2 = (prev.head - before.head) / h2;
	const slope = ((2 * h1 + h2) * d1 - h1 * d2) / (h1 + h2);
	expect(Math.sign(slope)).toBe(Math.sign(d1));
	const xMono = 2 * (last.flow - last.head / slope); // L/s
	expect(xMono).toBeCloseTo(80, 12);
	const beyond = 90; // L/s, a made-up setpoint at or above the bound

	await openExamplePump(page);
	const panel = buildPane(page);
	await panel
		.getByRole('combobox', { name: 'Control' })
		.selectOption({ label: 'Flow control (variable speed)' });
	await setNumber(panel, 'Flow setpoint (L/s)', String(beyond));
	await setNumber(panel, 'Minimum speed (%)', String(MIN_SPEED));
	const { status, body } = await solve(page);
	expect(status).toBe(422);
	expect(body.issues).toEqual([
		expect.objectContaining({ code: 'CONTROLLED_PUMP_SETPOINT', componentIds: ['P1'] })
	]);
	expect(body.issues![0]!.message).toContain(`setpoints must be below ${xMono / 1000} m³/s`);

	await showPane(page, 'Results');
	const item = resultsPane(page)
		.getByRole('region', { name: 'The network cannot be solved yet' })
		.getByRole('listitem');
	await expect(item).toHaveCount(1);
	const curve = pumpTransferExample().pumpLibrary[0]!.name;
	await expect(item).toContainText(
		`Transfer pump is speed-controlled to hold ${beyond} L/s, but no speed up to its maximum ` +
			`speed (100 %) can hold that flow on its pump curve “${curve}”:`
	);
	await expect(item).toContainText(
		`Use a setpoint below ${down4(xMono)} L/s (the maximum speed × x_mono), or a curve that ` +
			'extends to higher flows.'
	);
	await expect(item).not.toContainText('m³/s');
	await expect(item.getByRole('button', { name: 'Transfer pump' })).toBeVisible();

	// A setpoint below the bound solves (at the maximum speed: it is beyond what the pump gives).
	await showPane(page, 'Build');
	await setNumber(panel, 'Flow setpoint (L/s)', String(UNREACHABLE));
	await solveConverged(page);
});
