import { expect, test, type Page } from '@playwright/test';
import type { PumpResult, SolvedState, SystemCurveResponse } from '../src/lib/api/types';
import {
	ALLOWED_ORIGINS,
	buildPane,
	cellText,
	currentHeading,
	resultsPane,
	resultsView,
	setNumber,
	showPane,
	sig4,
	solveConverged,
	tableTexts
} from './support';

/**
 * A speed-controlled pump (CLAUDE.md D11, flow control) through the UI against the real API: the
 * pump-transfer example's pump is switched to flow control, solved, and its solved speed and
 * state read in the results table and the pump chart; the link is shared and reopened with the
 * same results; an unreachable setpoint runs the pump at its maximum speed with the information
 * flag; switching back to fixed speed is undone in one step.
 *
 * Network: the home page's pump-transfer example (illustrative, made-up inputs), whose pump curve
 * at rated speed is 0 L/s at 30 m, 10 L/s at 28 m, 20 L/s at 22 m and 30 L/s at 12 m. The flow
 * setpoints and the minimum speed below are made-up test inputs.
 */
const CURVE = [
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
