/**
 * The Add cases block on the Pumps together card (CLAUDE.md D24 slice L1b, proposal
 * pump-lineups.md §7 and §10.1 "L1b, component" and "L1b, workspace"). In the workspace, on the
 * shared fixture's `lineups` project (four curve_a pumps on Crane tees, every one carrying flow)
 * with a fake solver answering each case from its real API answers by scenario id: By number
 * running by default and the segments that switch the preset; the stop order's moves in both
 * directions, the focus on the same button of the moved pump after every press, the ends
 * aria-disabled and described, Default order and the status line's words; the add in one undo
 * step with its notice, "Also show" ticked and the focus on Solve all, then each case solved with
 * its lineup line; the scenario limit; page state reset on load. Drawn alone from lineupPlan's
 * real plans: the preview's item kinds, the refusals, the gates, an idle pump and the names-count
 * sentence. Every string is §7.12's, word for word. D24 slice L2 (§8.1, §10.2 "The card"): the
 * block's "Pump lineups table…" opens the Scenarios manager on Pump lineups showing the card's
 * pumps only (on the fixture's `two-systems`, whose card holds PA and PB of six pumps), and is
 * drawn under a gate too.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
	Override,
	Project,
	PumpGroupCurveResponse,
	PumpGroupStation,
	Scenario,
	SolveResponse
} from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { lineupPlan, type LineupPlanInput } from '$lib/utils/pump-lineups';
import { scenariosOf, withScenarios } from '$lib/utils/scenarios';
import PumpLineupsBlock from './PumpLineupsBlock.svelte';

const getContext = HTMLCanvasElement.prototype.getContext;
const consoleError = console.error;
beforeEach(() => {
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	console.error = (...args: unknown[]) => {
		if (String(args[0]).startsWith('Failed to create chart')) return;
		consoleError(...args);
	};
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	console.error = consoleError;
});

interface Answer {
	status: number;
	body: unknown;
}
interface Responses {
	solve: SolveResponse;
	groupCurve: Answer;
	systemCurve: Answer | null;
}
interface FixtureCase extends Responses {
	name: string;
	project: Project;
	memberIds: string[];
	scenarioCases: Record<string, Responses>;
}
const solvedCase = (name: string) =>
	(fixture.cases as unknown as FixtureCase[]).find((c) => c.name === name)!;
/** Four curve_a pumps P1 to P4 on Crane tees, every one carrying flow in the base case. */
const lineups = solvedCase('lineups');
/** PA and PB, PB's discharge valve isolated: PB `running` at 0.0 m³/s in the base case. */
const closedLeg = solvedCase('lineups-closed-leg');
const stationOf = (c: FixtureCase) => (c.groupCurve.body as PumpGroupCurveResponse).station;
const withoutScenarios = (c: FixtureCase = lineups) =>
	withScenarios(structuredClone(c.project), []);

const NAMES = [
	'3 of 4 running (Pump P4 off)',
	'2 of 4 running (Pump P3, Pump P4 off)',
	'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
];

// ---- In the workspace ----------------------------------------------------------------------

/**
 * A solver answering from the `lineups` fixture by scenario id; the base case (no id) by
 * `baseOf` of the project sent, the fixture's base answers by default.
 */
function setup(project: Project, baseOf: (sent: Project) => Responses = () => lineups) {
	const calls: { scenarioId: string | null; curve: 'group' | 'system' }[] = [];
	const solves: (string | null)[] = [];
	const responsesOf = (sent: Project, id: string | undefined): Responses =>
		(id && lineups.scenarioCases[id]) || baseOf(sent);
	const solver: Solver = {
		solve: async (project, _o, request) => {
			solves.push(request?.scenarioId ?? null);
			return structuredClone(responsesOf(project, request?.scenarioId).solve);
		},
		groupCurve: async (project, _ids, request) => {
			const curve = request?.curve === 'system' ? 'system' : 'group';
			calls.push({ scenarioId: request?.scenarioId ?? null, curve });
			const answer = responsesOf(project, request?.scenarioId);
			const sent = curve === 'system' ? answer.systemCurve! : answer.groupCurve;
			return structuredClone(sent.body as PumpGroupCurveResponse);
		}
	};
	const ws = testWorkspace(project, { solver });
	render(WorkspaceView, { workspace: ws });
	return { ws, calls, solves };
}

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const card = () => results().getByRole('region', { name: /^Pumps together/ }) as HTMLElement;
const block = () => within(card()).getByRole('region', { name: 'Add cases' });
const inBlock = () => within(block());
/** The preview's items. */
const cases = () =>
	[...inBlock().getByRole('list', { name: 'Cases:' }).querySelectorAll('li')].map(
		(li) => li.textContent
	);
/** The stop order's items, as shown (label and note). */
/** A stop order's items as shown: each pump's label and its muted note (its buttons left out). */
const labelsOf = (list: HTMLElement) =>
	within(list)
		.getAllByRole('listitem')
		.map((li) => li.querySelector('div > span:first-child')!.textContent);
const stopItems = () => labelsOf(inBlock().getByRole('list', { name: 'Stop order' }));
const stopStatus = () => block().querySelector('[data-stop-status]')!.textContent;
const details = () => block().querySelector('details')!;

/** Solve the base, show the Pumps view and open the card; its two curves answered. */
async function openCard(
	ws: ReturnType<typeof setup>['ws'],
	calls: ReturnType<typeof setup>['calls']
) {
	await ws.solve();
	await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
	await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
	await waitFor(() => expect(calls.filter((c) => c.scenarioId === null)).toHaveLength(2));
}

/** Open the stop order (a click on its summary, as a press). */
async function openStopOrder() {
	await fireEvent.click(details().querySelector('summary')!);
	expect(details().open).toBe(true);
}

/**
 * Press a button as a keyboard user does: focused, then activated. Returns once the block's
 * handler has run (it awaits a tick before it puts the focus back).
 */
async function press(name: string) {
	const button = inBlock().getByRole('button', { name });
	button.focus();
	await fireEvent.click(button);
	await new Promise((resolve) => setTimeout(resolve, 0));
}

/** The element focused is the stop order's `dir` button of `pumpId`, by its name. */
function focusedOn(pumpId: string, dir: 'up' | 'down', name: string) {
	const active = document.activeElement as HTMLElement;
	expect(active.dataset.stopId).toBe(pumpId);
	expect(active.dataset.dir).toBe(dir);
	expect(active).toHaveAccessibleName(name);
	expect(block().contains(active)).toBe(true);
}

describe('the Add cases block in the workspace', () => {
	it('shows By number running by default: what it makes, the sentence, the stop order closed, the cases and Add', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		expect(within(block()).getByRole('heading', { name: 'Add cases', level: 4 })).toBeVisible();
		const presets = inBlock().getByRole('radiogroup', { name: 'Cases to add' });
		expect(within(presets).getByRole('radio', { name: 'By number running' })).toBeChecked();
		expect(within(presets).getByRole('radio', { name: 'Each pump off' })).not.toBeChecked();
		expect(ws.lineupPreset).toBe('running');
		expect(block()).toHaveTextContent(
			"Makes one scenario for each number of these pumps running, from 3 down to 1: the base case with the pumps that stop first switched off and nothing else changed. In a case's name, running means switched on; Running combinations shows whether each pump carries flow. Other sets of the same number of pumps are not made: change the stop order and add again to compare them."
		);
		expect(block()).toHaveTextContent(
			"Pump P1, Pump P2, Pump P3 and Pump P4 have the same pump curve and speed. Which of them run can still change the answer, through the tees and each pump's own piping, most when few run: change the stop order to compare which run at each count; Each pump off compares them with one off."
		);
		// The stop order: closed, its summary saying what it holds.
		expect(details().open).toBe(false);
		expect(details().querySelector('summary')).toHaveTextContent(
			'Stop order: Pump P4 first, then Pump P3 and Pump P2; Pump P1 stays on in every case'
		);
		expect(inBlock().queryByRole('button', { name: 'Default order' })).toBeNull();
		expect(cases()).toEqual(NAMES);
		// The card's members are the frame's group: no names-count sentence.
		expect(block().textContent).not.toMatch(/Names (count|list)/);
		const add = inBlock().getByRole('button', { name: 'Add 3 cases' });
		expect(add).not.toHaveAttribute('aria-disabled', 'true');
		expect(add).not.toHaveAttribute('aria-describedby');
		expect(inBlock().getByRole('button', { name: 'Solve all' })).toBeVisible();
		expect(stopStatus()).toBe('');
	});

	it('the segments switch the preset, and back', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await fireEvent.click(inBlock().getByRole('radio', { name: 'Each pump off' }));
		expect(ws.lineupPreset).toBe('each');
		expect(inBlock().getByRole('radio', { name: 'Each pump off' })).toBeChecked();
		// 4d's About, cases and names; no stop order and no sentence.
		expect(block()).toHaveTextContent(
			'Makes one scenario per pump running in the base case (Pump P1, Pump P2, Pump P3 and Pump P4): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		expect(cases()).toEqual(['Pump P1 off', 'Pump P2 off', 'Pump P3 off', 'Pump P4 off']);
		expect(block().querySelector('details')).toBeNull();
		expect(block().textContent).not.toContain('have the same pump curve and speed');
		expect(inBlock().getByRole('button', { name: 'Add 4 cases' })).toBeVisible();
		await fireEvent.click(inBlock().getByRole('radio', { name: 'By number running' }));
		expect(ws.lineupPreset).toBe('running');
		expect(inBlock().getByRole('radio', { name: 'By number running' })).toBeChecked();
		expect(cases()).toEqual(NAMES);
		expect(details().open).toBe(false);
	});

	it('moves a pump earlier: the focus stays on its button, which at the end is aria-disabled and described', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await openStopOrder();
		expect(stopItems()).toEqual([
			'Pump P4 (stops first)',
			'Pump P3',
			'Pump P2',
			'Pump P1 (stays on in every case)'
		]);
		expect(
			inBlock().getByText(
				'The first in this list stops first. The cases below change as you move pumps.'
			)
		).toBeVisible();
		// Every move button is an icon at least 44 × 44 px (the btn-icon class: --ctl-h, 2.75 rem
		// outside .dense; the layout is measured in a browser), named for screen readers.
		for (const button of block().querySelectorAll<HTMLElement>('[data-stop-id][data-dir]')) {
			expect(button).toHaveClass('btn-icon', 'min-w-11');
		}
		const earlier = 'Stop Pump P1 earlier';
		await press(earlier);
		focusedOn('P1', 'up', earlier);
		expect(stopStatus()).toBe('Pump P1 is now number 3 of 4 to stop.');
		expect(ws.pumpStopOrder).toEqual(['P4', 'P3', 'P1', 'P2']);
		await press(earlier);
		focusedOn('P1', 'up', earlier);
		expect(stopStatus()).toBe('Pump P1 is now number 2 of 4 to stop.');
		await press(earlier);
		focusedOn('P1', 'up', earlier);
		expect(stopStatus()).toBe('Pump P1 is now number 1 of 4 to stop.');
		// The first now: it stays, focused, aria-disabled and described.
		const first = document.activeElement as HTMLElement;
		expect(first).toHaveAttribute('aria-disabled', 'true');
		expect(first).toHaveAccessibleDescription('Already the first to stop.');
		expect(stopItems()).toEqual([
			'Pump P1 (stops first)',
			'Pump P4',
			'Pump P3',
			'Pump P2 (stays on in every case)'
		]);
		// Pressed again at the end: nothing moves, and the focus stays.
		await press(earlier);
		expect(document.activeElement).toBe(first);
		expect(ws.pumpStopOrder).toEqual(['P1', 'P4', 'P3', 'P2']);
		// The cases and the summary follow.
		expect(cases()).toEqual([
			'3 of 4 running (Pump P1 off)',
			'2 of 4 running (Pump P1, Pump P4 off)',
			'1 of 4 running (Pump P1, Pump P3, Pump P4 off)'
		]);
		expect(details().querySelector('summary')).toHaveTextContent(
			'Stop order: Pump P1 first, then Pump P4 and Pump P3; Pump P2 stays on in every case'
		);
		// Then later once (the keyed list moves the focused node: the focus is put back).
		const later = 'Stop Pump P1 later';
		await press(later);
		focusedOn('P1', 'down', later);
		expect(stopStatus()).toBe('Pump P1 is now number 2 of 4 to stop.');
		expect(ws.pumpStopOrder).toEqual(['P4', 'P1', 'P3', 'P2']);
		expect(cases()).toEqual([
			'3 of 4 running (Pump P4 off)',
			'2 of 4 running (Pump P1, Pump P4 off)',
			'1 of 4 running (Pump P1, Pump P3, Pump P4 off)'
		]);
	});

	it('moves a pump later: the focus put back on its button each time, aria-disabled at the end', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await openStopOrder();
		const later = 'Stop Pump P4 later';
		await press(later);
		focusedOn('P4', 'down', later);
		expect(stopStatus()).toBe('Pump P4 is now number 2 of 4 to stop.');
		await press(later);
		focusedOn('P4', 'down', later);
		expect(stopStatus()).toBe('Pump P4 is now number 3 of 4 to stop.');
		await press(later);
		focusedOn('P4', 'down', later);
		expect(stopStatus()).toBe('Pump P4 is now number 4 of 4 to stop.');
		const last = document.activeElement as HTMLElement;
		expect(last).toHaveAttribute('aria-disabled', 'true');
		expect(last).toHaveAccessibleDescription('Already the last to stop.');
		expect(stopItems()).toEqual([
			'Pump P3 (stops first)',
			'Pump P2',
			'Pump P1',
			'Pump P4 (stays on in every case)'
		]);
		await press(later);
		expect(document.activeElement).toBe(last);
		expect(ws.pumpStopOrder).toEqual(['P3', 'P2', 'P1', 'P4']);
		expect(cases()).toEqual([
			'3 of 4 running (Pump P3 off)',
			'2 of 4 running (Pump P2, Pump P3 off)',
			'1 of 4 running (Pump P1, Pump P2, Pump P3 off)'
		]);
		// A move up from the middle, the other direction, keeps it too.
		await press('Stop Pump P2 earlier');
		focusedOn('P2', 'up', 'Stop Pump P2 earlier');
		expect(stopStatus()).toBe('Pump P2 is now number 1 of 4 to stop.');
	});

	it('Default order: shown off the default, described; it resets, then the focus is on the first pump’s Stop … later', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await openStopOrder();
		expect(inBlock().queryByRole('button', { name: 'Default order' })).toBeNull();
		// Moved and moved back: the order saved is the default again, so the button is not shown.
		await press('Stop Pump P4 later');
		expect(inBlock().getByRole('button', { name: 'Default order' })).toBeVisible();
		await press('Stop Pump P4 earlier');
		expect(ws.pumpStopOrder).toEqual(['P4', 'P3', 'P2', 'P1']);
		expect(inBlock().queryByRole('button', { name: 'Default order' })).toBeNull();
		await press('Stop Pump P2 earlier');
		const reset = inBlock().getByRole('button', { name: 'Default order' });
		expect(reset).toHaveAccessibleDescription(
			"The default: the last pump switched on in the group's list stops first."
		);
		await press('Default order');
		expect(inBlock().queryByRole('button', { name: 'Default order' })).toBeNull();
		focusedOn('P4', 'down', 'Stop Pump P4 later');
		expect(stopStatus()).toBe('Default order: Pump P4 stops first.');
		expect(ws.pumpStopOrder).toEqual([]);
		expect(cases()).toEqual(NAMES);
		expect(details().open).toBe(true);
		expect(details().querySelector('summary')).toHaveTextContent(
			'Stop order: Pump P4 first, then Pump P3 and Pump P2; Pump P1 stays on in every case'
		);
	});

	it('after the pumps on change in the base, shows the default order, and a move starts from it (§7.5)', async () => {
		// The base with P4 switched off is answered by the fixture's S1 (P4 off), the same answer
		// as the hand edit (API proof 1), without its scenario record.
		const p4Off = lineups.scenarioCases.S1!;
		const asBase: Responses = {
			solve: { ...p4Off.solve, scenario: null },
			groupCurve: {
				...p4Off.groupCurve,
				body: { ...(p4Off.groupCurve.body as PumpGroupCurveResponse), scenario: null }
			},
			systemCurve: {
				...p4Off.systemCurve!,
				body: { ...(p4Off.systemCurve!.body as PumpGroupCurveResponse), scenario: null }
			}
		};
		const offInBase = (sent: Project) =>
			sent.components.some((c) => c.id === 'P4' && c.type === 'pump' && c.status === 'off');
		const { ws, calls } = setup(withoutScenarios(), (sent) => (offInBase(sent) ? asBase : lineups));
		await openCard(ws, calls);
		await openStopOrder();
		await press('Stop Pump P1 earlier');
		expect(ws.pumpStopOrder).toEqual(['P4', 'P3', 'P1', 'P2']);
		// P4 switched off in the base and solved again: the saved order no longer holds the
		// pumps on, so the default is shown, nothing merged; the saved order is kept, unused.
		expect(
			ws.updateStored((draft) => {
				const p4 = draft.components.find((c) => c.id === 'P4');
				if (p4?.type === 'pump') p4.status = 'off';
			}, 'switch Pump P4 off')
		).toBe(true);
		await ws.solve();
		const summary = () => details().querySelector('summary')!.textContent!.trim();
		await waitFor(() =>
			expect(summary()).toBe(
				'Stop order: Pump P3 first, then Pump P2; Pump P1 stays on in every case'
			)
		);
		expect(ws.pumpStopOrder).toEqual(['P4', 'P3', 'P1', 'P2']);
		expect(cases()).toEqual([
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		]);
		if (!details().open) await openStopOrder();
		expect(stopItems()).toEqual([
			'Pump P3 (stops first)',
			'Pump P2',
			'Pump P1 (stays on in every case)'
		]);
		expect(inBlock().queryByRole('button', { name: 'Default order' })).toBeNull();
		// The move starts from the default [P3, P2, P1]: P1 one place earlier.
		await press('Stop Pump P1 earlier');
		focusedOn('P1', 'up', 'Stop Pump P1 earlier');
		expect(stopStatus()).toBe('Pump P1 is now number 2 of 3 to stop.');
		expect(ws.pumpStopOrder).toEqual(['P3', 'P1', 'P2']);
		expect(summary()).toBe(
			'Stop order: Pump P3 first, then Pump P1; Pump P2 stays on in every case'
		);
		expect(cases()).toEqual([
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P1, Pump P3, Pump P4 off)'
		]);
		// Default order, described truly with P4 off: the last pump switched on in the group's
		// list (P3, not P4) stops first.
		const reset = inBlock().getByRole('button', { name: 'Default order' });
		expect(reset).toHaveAccessibleDescription(
			"The default: the last pump switched on in the group's list stops first."
		);
		await press('Default order');
		expect(stopStatus()).toBe('Default order: Pump P3 stops first.');
		focusedOn('P3', 'down', 'Stop Pump P3 later');
	}, 20_000);

	it('adds in one undo step with its notice, ticks "Also show", focuses Solve all; each case then has its lineup line', async () => {
		const { ws, calls, solves } = setup(withoutScenarios());
		await openCard(ws, calls);
		const depth = ws.store.undoDepth;
		await fireEvent.click(inBlock().getByRole('button', { name: 'Add 3 cases' }));
		// Exactly the fixture's S1 to S3, the scenarios the API solved.
		expect(ws.scenarios).toEqual(lineups.project.scenarios!.slice(0, 3));
		expect(ws.store.undoDepth).toBe(depth + 1);
		expect(ws.store.undoLabel).toBe('add cases by number running');
		expect(ws.store.activeCase).toBeNull();
		expect(ws.pumpGroupOthers).toBe(true);
		expect(
			within(card()).getByRole('checkbox', { name: "Also show the other cases' station duties" })
		).toBeChecked();
		expect(ws.notice).toMatchObject({
			kind: 'info',
			text: 'Added 3 cases by number running: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)». Solve all solves every case not yet solved; Undo removes them.'
		});
		expect(screen.getByText(ws.notice!.text)).toBeVisible();
		const solveAll = inBlock().getByRole('button', { name: 'Solve all (3)' });
		await waitFor(() => expect(solveAll).toHaveFocus());
		// Every case is a scenario now: the cases say so, and Add is refused.
		expect(cases()).toEqual(NAMES.map((name, i) => `${name}: already a scenario (S${i + 1})`));
		const refused = inBlock().getByRole('button', { name: 'Add cases' });
		expect(refused).toHaveAttribute('aria-disabled', 'true');
		expect(refused).toHaveAccessibleDescription(
			'Every case by number running already exists: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)».'
		);
		// Solve all: the three cases, then each case's group curve (most running first), three rings.
		await fireEvent.click(solveAll);
		await waitFor(() => expect(solves).toEqual([null, 'S1', 'S2', 'S3']));
		const legend = within(card()).getByRole('list', { name: 'Legend' });
		await waitFor(() =>
			expect(within(legend).getByText(`3 · ${NAMES[2]} (station duty)`)).toBeVisible()
		);
		expect(within(legend).getByText(`1 · ${NAMES[0]} (station duty)`)).toBeVisible();
		expect(within(legend).getByText(`2 · ${NAMES[1]} (station duty)`)).toBeVisible();
		expect(calls.filter((c) => c.scenarioId !== null).map((c) => [c.scenarioId, c.curve])).toEqual([
			['S1', 'group'],
			['S2', 'group'],
			['S3', 'group']
		]);
		// Running combinations: four groups, each with its lineup line read from its solve.
		const combos = within(card()).getByRole('table', { name: 'Running combinations' });
		const lines = within(combos)
			.getAllByRole('rowheader')
			.filter((h) => h.getAttribute('scope') === 'rowgroup')
			.map((h) => [...h.children].slice(0, 2).map((line) => line.textContent));
		expect(lines).toEqual([
			['Base case (shown)', '4 of 4 carrying flow: Pump P1, Pump P2, Pump P3 and Pump P4'],
			[`${NAMES[0]} · ring 1`, '3 of 4 carrying flow: Pump P1, Pump P2 and Pump P3; off: Pump P4'],
			[
				`${NAMES[1]} · ring 2`,
				'2 of 4 carrying flow: Pump P1 and Pump P2; off: Pump P3 and Pump P4'
			],
			[`${NAMES[2]} · ring 3`, '1 of 4 carrying flow: Pump P1; off: Pump P2, Pump P3 and Pump P4']
		]);
		// Undo removes every case at once.
		expect(ws.undo()).toBe(true);
		expect(scenariosOf(ws.store.project)).toEqual([]);
		await waitFor(() =>
			expect(inBlock().getByRole('button', { name: 'Add 3 cases' })).toBeVisible()
		);
	}, 20_000);

	it('refuses the add past the scenario limit, described, and makes nothing', async () => {
		const eighteen: Scenario[] = Array.from({ length: 18 }, (_, i) => ({
			id: `S${i + 1}`,
			name: `Case ${i + 1}`,
			overrides: []
		}));
		const { ws, calls } = setup(withScenarios(withoutScenarios(), eighteen));
		await openCard(ws, calls);
		const add = inBlock().getByRole('button', { name: 'Add 3 cases' });
		expect(add).toHaveAttribute('aria-disabled', 'true');
		expect(add).toHaveAccessibleDescription(
			'Adding 3 cases would make 21 scenarios; a project holds at most 20 scenarios.'
		);
		expect(
			inBlock().getByText(
				'Adding 3 cases would make 21 scenarios; a project holds at most 20 scenarios.'
			)
		).toBeVisible();
		const depth = ws.store.undoDepth;
		await fireEvent.click(add);
		expect(ws.store.undoDepth).toBe(depth);
		expect(ws.scenarios).toHaveLength(18);
		expect(document.activeElement).not.toHaveAccessibleName(/^Solve all/);
	});

	it('“Pump lineups table…” opens the manager on Pump lineups, showing the card’s pumps only', async () => {
		const two = solvedCase('two-systems');
		const calls: string[] = [];
		const solver: Solver = {
			solve: async () => structuredClone(two.solve),
			groupCurve: async (_project, ids, request) => {
				calls.push(`${request?.curve ?? 'group'} ${ids.join(',')}`);
				const sent = request?.curve === 'system' ? two.systemCurve! : two.groupCurve;
				return structuredClone(sent.body as PumpGroupCurveResponse);
			}
		};
		const ws = testWorkspace(withScenarios(structuredClone(two.project), []), { solver });
		ws.pumpGroup = ['PA', 'PB'];
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		await fireEvent.click(results().getByRole('tab', { name: 'Pumps' }));
		await fireEvent.click(within(card()).getByRole('button', { name: /^Pumps together/ }));
		await waitFor(() => expect(calls).toEqual(['group PA,PB', 'system PA,PB']));
		const button = inBlock().getByRole('button', { name: 'Pump lineups table…' });
		await fireEvent.click(button);
		const manager = await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(ws.managerTab).toBe('lineups');
		expect(ws.managerPumps).toEqual(['PA', 'PB']);
		expect(within(manager).getByRole('tab', { name: 'Pump lineups' })).toHaveAttribute(
			'aria-selected',
			'true'
		);
		const grid = within(manager).getByRole('grid', { name: 'Pumps on or off in each case' });
		const headers = within(grid)
			.getAllByRole('columnheader')
			.map((h) => h.textContent?.replace(/\s+/g, ' ').trim());
		expect(headers).toEqual(['Case', 'Pump PA PA', 'Pump PB PB']);
		expect(manager).toHaveTextContent(
			'Only the pumps on the Pumps together card are shown: Pump PA and Pump PB.'
		);
		// Done forgets the filter: the header's Scenarios shows every pump.
		await fireEvent.click(within(manager).getByRole('button', { name: 'Done' }));
		expect(ws.managerPumps).toBeNull();
	});

	it('resets the preset and the stop order when another project is loaded', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await openStopOrder();
		await press('Stop Pump P1 earlier');
		ws.lineupPreset = 'each';
		ws.store.load(withoutScenarios(closedLeg));
		expect(ws.lineupPreset).toBe('running');
		expect(ws.pumpStopOrder).toEqual([]);
	});
});

// ---- Drawn alone, from lineupPlan's real plans --------------------------------------------

const runnable = {
	count: 0,
	canRun: false,
	reason: "Every case's results are current.",
	hint: 'Solves each case whose results are missing or out of date, one after another: up to 0 solves.'
};

/** The plan for a fixture case's base case shown and current (its station, members and solve). */
function planOn(c: FixtureCase, values: Partial<LineupPlanInput> = {}) {
	return lineupPlan({
		project: withoutScenarios(c),
		shownCase: null,
		station: stationOf(c),
		memberIds: c.memberIds,
		base: { response: c.solve, stale: false },
		preset: 'running',
		savedOrder: [],
		...values
	});
}

function draw(plan: ReturnType<typeof planOn>, handlers: Record<string, unknown> = {}) {
	return render(PumpLineupsBlock, { plan, solveAll: runnable, ...handlers });
}
const alone = () => within(screen.getByRole('region', { name: 'Add cases' }));
const items = () =>
	[...alone().getByRole('list', { name: 'Cases:' }).querySelectorAll('li')].map(
		(li) => li.textContent
	);

describe('the Add cases block, drawn alone', () => {
	const off = (...ids: string[]): Override[] =>
		ids.map((componentId) => ({ kind: 'component', componentId, field: 'status', value: 'off' }));

	it('words each kind of case in the preview: added, already a scenario (both forms), another case with its name', () => {
		const project = withScenarios(withoutScenarios(), [
			// The same case, the same name: the short form.
			{ id: 'S1', name: NAMES[0]!, overrides: off('P4') },
			// The same case by another name, its changes in another order: the long form.
			{ id: 'S2', name: 'Two off (hand)', overrides: off('P4', 'P3') },
			// Another case (a tank level too) with the third case's name: it is added, and said.
			{
				id: 'S3',
				name: NAMES[2]!,
				overrides: [
					...off('P2', 'P3', 'P4'),
					{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 7 }
				]
			}
		]);
		draw(planOn(lineups, { project }));
		expect(items()).toEqual([
			'3 of 4 running (Pump P4 off): already a scenario (S1)',
			'2 of 4 running (Pump P3, Pump P4 off): already a scenario, «Two off (hand)» (S2)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off): scenario S3 has this name too but is another case'
		]);
		expect(alone().getByText('Cases:')).toBeVisible();
		const add = alone().getByRole('button', { name: 'Add 1 case' });
		expect(add).not.toHaveAttribute('aria-disabled', 'true');
	});

	it('words an idle pump’s case as the base case’s state, and refuses: nothing to add', async () => {
		const onadd = vi.fn();
		draw(planOn(closedLeg), { onadd });
		expect(items()).toEqual([
			"1 of 2 running (Pump PB off): not made, the base case's state (Pump PB carries no flow in the base case)"
		]);
		expect(
			alone().getByText(
				'Makes one scenario with one of these pumps running: the base case with the pump that stops first switched off and nothing else changed.',
				{ exact: false }
			)
		).toBeVisible();
		const summary = document.querySelector('details > summary')!;
		expect(summary).toHaveTextContent('Stop order: Pump PB stops; Pump PA stays on in every case');
		await fireEvent.click(summary);
		expect(labelsOf(alone().getByRole('list', { name: 'Stop order' }))).toEqual([
			'Pump PB (stops first) (carries no flow in the base case)',
			'Pump PA (stays on in every case)'
		]);
		const add = alone().getByRole('button', { name: 'Add cases' });
		expect(add).toHaveAttribute('aria-disabled', 'true');
		expect(add).toHaveAccessibleDescription(
			"Nothing to add: each case by number running already exists or is the base case's state."
		);
		await fireEvent.click(add);
		expect(onadd).not.toHaveBeenCalled();
	});

	it('says which group the names count for a card that is not one group of the frame', () => {
		draw(planOn(lineups, { memberIds: ['P2', 'P3'] }));
		expect(
			alone().getByText(
				'Names count every pump of the group Pump P1, Pump P2, Pump P3 and Pump P4.'
			)
		).toBeVisible();
		expect(items()).toEqual(['3 of 4 running (Pump P3 off)']);
	});

	it('under a gate shows only its sentence, and Solve all for gates 4 to 6', async () => {
		const series = (solvedCase('series').groupCurve.body as PumpGroupCurveResponse).station;
		const view = draw(planOn(lineups, { station: series }));
		const region = () => screen.getByRole('region', { name: 'Add cases' });
		expect(region()).toHaveTextContent(
			'Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.'
		);
		expect(alone().queryByRole('radiogroup')).toBeNull();
		expect(alone().queryByRole('button')).toBeNull();
		expect(region().querySelector('details')).toBeNull();
		const stale = planOn(lineups, { base: { response: lineups.solve, stale: true } });
		await view.rerender({ plan: stale, solveAll: runnable });
		expect(region()).toHaveTextContent(
			"The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now."
		);
		expect(alone().queryByRole('radiogroup')).toBeNull();
		expect(
			alone()
				.getAllByRole('button')
				.map((b) => b.textContent!.trim())
		).toEqual(['Solve all']);
		const mixed: PumpGroupStation = { ...stationOf(lineups), arrangement: 'mixed' };
		await view.rerender({ plan: planOn(lineups, { station: mixed }), solveAll: runnable });
		expect(region()).toHaveTextContent(
			'Cases are added here for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.'
		);
	});

	it('draws “Pump lineups table…” at its foot, under a gate too', async () => {
		const ontable = vi.fn();
		const series = (solvedCase('series').groupCurve.body as PumpGroupCurveResponse).station;
		draw(planOn(lineups, { station: series }), { ontable });
		expect(
			alone()
				.getAllByRole('button')
				.map((b) => b.textContent?.trim())
		).toEqual(['Pump lineups table…']);
		await fireEvent.click(alone().getByRole('button', { name: 'Pump lineups table…' }));
		expect(ontable).toHaveBeenCalledTimes(1);
		document.body.innerHTML = '';
		draw(planOn(lineups), { ontable });
		const buttons = alone().getAllByRole('button');
		expect(buttons.at(-1)).toHaveAccessibleName('Pump lineups table…');
	});

	it('reports the preset chosen, and a move, to the caller', async () => {
		const onpreset = vi.fn();
		const onmove = vi.fn();
		draw(planOn(lineups), { onpreset, onmove });
		await fireEvent.click(alone().getByRole('radio', { name: 'Each pump off' }));
		expect(onpreset).toHaveBeenCalledWith('each');
		await fireEvent.click(alone().getByRole('button', { name: 'Stop Pump P3 earlier' }));
		expect(onmove).toHaveBeenCalledWith('P3', 'up');
		// At an end, nothing is reported.
		await fireEvent.click(alone().getByRole('button', { name: 'Stop Pump P4 earlier' }));
		await fireEvent.click(alone().getByRole('button', { name: 'Stop Pump P1 later' }));
		expect(onmove).toHaveBeenCalledTimes(1);
	});
});
