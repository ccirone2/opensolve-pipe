/**
 * The Add cases block on the Pumps together card (CLAUDE.md D24 slice L1b, proposal
 * pump-lineups.md §7 and §10.1 "L1b, component" and "L1b, workspace"). In the workspace, on the
 * shared fixture's `lineups` project (four curve_a pumps on Crane tees, every one carrying flow)
 * with a fake solver answering each case from its real API answers by scenario id: By number
 * running by default and the segments that switch the preset; the stop order's moves in both
 * directions, the focus on the same button of the moved pump after every press, the ends
 * aria-disabled and described, Default order and the status line's words; the add in one undo
 * step with its notice, "Also show" ticked and the focus kept on Add, then each case solved with
 * its lineup line by the Scenarios menu's Solve all (build-density.md §19); the scenario limit; page state reset on load. Drawn alone from lineupPlan's
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
import { besideCaseTag, outOfSight, shownCaseTag } from '$lib/testing/helpers';
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
/** PA and PB, both carrying flow; its scenarios S1 "Pump PA off" and S2 "Pump PB off" first. */
const oneOff = solvedCase('one-off');
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
 * A solver answering from the `lineups` fixture (or `from`) by scenario id; the base case (no id)
 * by `baseOf` of the project sent, the fixture's base answers by default.
 */
function setup(
	project: Project,
	baseOf: (sent: Project) => Responses = () => lineups,
	from: FixtureCase = lineups
) {
	const calls: { scenarioId: string | null; curve: 'group' | 'system' }[] = [];
	const solves: (string | null)[] = [];
	const responsesOf = (sent: Project, id: string | undefined): Responses =>
		(id && from.scenarioCases[id]) || baseOf(sent);
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
/** The stop order's own disclosure (inside the plan's since S4, pumps-results-layout.md §5.3). */
const details = () => block().querySelector<HTMLDetailsElement>('[data-stop-order]')!;

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

/**
 * The Scenarios menu's Solve all, the one Solve all of the page (build-density.md §19): the menu
 * opened from the header's Scenarios button.
 */
async function menuSolveAll(): Promise<HTMLElement> {
	if (!screen.queryByRole('group', { name: 'Case' })) {
		await fireEvent.click(screen.getByRole('button', { name: /^Scenarios/ }));
	}
	return within(screen.getByRole('group', { name: 'Case' })).getByRole('button', {
		name: /^Solve all/
	});
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
		// Its row holds Add alone: Solve all is the Scenarios menu's (build-density.md §19).
		expect([...add.parentElement!.children]).toEqual([add]);
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
		expect(block().querySelector('[data-stop-order]')).toBeNull();
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

	it('adds in one undo step with its notice, ticks "Also show", keeps the focus on Add; each case then has its lineup line', async () => {
		const { ws, calls, solves } = setup(withoutScenarios());
		await openCard(ws, calls);
		const depth = ws.store.undoDepth;
		const add = inBlock().getByRole('button', { name: 'Add 3 cases' });
		await press('Add 3 cases');
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
			text: 'Added 3 cases by number running: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)». Solve all, in the Scenarios menu at the top, solves every case not yet solved; Undo removes them.'
		});
		expect(screen.getByText(ws.notice!.text)).toBeVisible();
		// The focus stays on Add, the same node (build-density.md §19: no Solve all to move to).
		await waitFor(() => expect(add).toHaveFocus());
		// Every case is a scenario now: the cases say so, and Add is refused.
		expect(cases()).toEqual(NAMES.map((name, i) => `${name}: already a scenario (S${i + 1})`));
		const refused = inBlock().getByRole('button', { name: 'Add cases' });
		expect(refused).toBe(add);
		expect(refused).toHaveAttribute('aria-disabled', 'true');
		expect(refused).toHaveAccessibleDescription(
			'Every case by number running already exists: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)».'
		);
		// Solve all, the Scenarios menu's: the three cases, then each case's group curve (most
		// running first), three rings.
		const solveAll = await menuSolveAll();
		expect(solveAll).toHaveAccessibleName('Solve all (3)');
		await fireEvent.click(solveAll);
		await waitFor(() => expect(solves).toEqual([null, 'S1', 'S2', 'S3']));
		// Each ring named by its case's number, the case's place in the Scenarios list (owner,
		// 2026-11-12, nit 5; docs/proposals/pumps-nits.md item 5, slice 5b: "Case 3: …" in place
		// of "3 · …").
		const legend = within(card()).getByRole('list', { name: 'Legend' });
		await waitFor(() =>
			expect(within(legend).getByText(`Case 3: ${NAMES[2]} (station duty)`)).toBeVisible()
		);
		expect(within(legend).getByText(`Case 1: ${NAMES[0]} (station duty)`)).toBeVisible();
		expect(within(legend).getByText(`Case 2: ${NAMES[1]} (station duty)`)).toBeVisible();
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
			// Each heading's case number in its box, then its two lines' words (nit 5, slice 5b: the
			// number in a box, no " · ring n").
			.map((h) => [
				shownCaseTag(h),
				...[...h.children].slice(0, 2).map((line) => besideCaseTag(line))
			]);
		expect(lines).toEqual([
			['Base', 'Base case (shown)', '4 of 4 carrying flow: Pump P1, Pump P2, Pump P3 and Pump P4'],
			['1', NAMES[0], '3 of 4 carrying flow: Pump P1, Pump P2 and Pump P3; off: Pump P4'],
			['2', NAMES[1], '2 of 4 carrying flow: Pump P1 and Pump P2; off: Pump P3 and Pump P4'],
			['3', NAMES[2], '1 of 4 carrying flow: Pump P1; off: Pump P2, Pump P3 and Pump P4']
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
		const refusal = inBlock().getByText(
			'Adding 3 cases would make 21 scenarios; a project holds at most 20 scenarios.'
		);
		expect(refusal).toBeVisible();
		// On screen, not visually hidden (§5.3 item 4; S4 review MUT-02).
		expect(outOfSight(refusal)).toBe(false);
		const depth = ws.store.undoDepth;
		await press('Add 3 cases');
		expect(ws.store.undoDepth).toBe(depth);
		expect(ws.scenarios).toHaveLength(18);
		// The focus stays on Add (build-density.md §19).
		expect(add).toHaveFocus();
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
	return render(PumpLineupsBlock, { plan, ...handlers });
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
		const summary = document.querySelector('[data-stop-order] > summary')!;
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

	it('under a gate shows only its sentence, and no Solve all for gates 4 to 6 either', async () => {
		const series = (solvedCase('series').groupCurve.body as PumpGroupCurveResponse).station;
		const view = draw(planOn(lineups, { station: series }));
		const region = () => screen.getByRole('region', { name: 'Add cases' });
		expect(region()).toHaveTextContent(
			'Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.'
		);
		expect(alone().queryByRole('radiogroup')).toBeNull();
		expect(alone().queryByRole('button')).toBeNull();
		expect(region().querySelector('details')).toBeNull();
		// Gate 4: the sentence names the header's Solve, and the table button is the block's only
		// button (build-density.md §19: Solve all is the Scenarios menu's).
		const stale = planOn(lineups, { base: { response: lineups.solve, stale: true } });
		await view.rerender({ plan: stale, ontable: vi.fn() });
		expect(region()).toHaveTextContent(
			"The base case's results are out of date: solve it again with Solve, at the top, so the pumps that run are read from the project as it is now."
		);
		expect(alone().queryByRole('radiogroup')).toBeNull();
		expect(
			alone()
				.getAllByRole('button')
				.map((b) => b.textContent!.trim())
		).toEqual(['Pump lineups table…']);
		const mixed: PumpGroupStation = { ...stationOf(lineups), arrangement: 'mixed' };
		await view.rerender({ plan: planOn(lineups, { station: mixed }) });
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

// ---- The Pumps tab's S4: one structure, the fold, the new lines (pumps-results-layout.md) -----

/**
 * The panel's parts in order, each by what it is: its header row, the segments, the plan, the
 * row, the refusal, "Now ticked", the table button, and the polite line (§5.3 items 1 to 6; Solve
 * all and its reason are the Scenarios menu's since build-density.md §19).
 */
function partsOf(region: Element) {
	return [...region.children].map((el) => {
		if (el.querySelector(':scope > h4')) return 'header';
		if (el.querySelector('[role="radiogroup"]')) return 'segments';
		if (el.matches('[data-lineup-plan]')) return 'plan';
		if (el.querySelector('button') && el.tagName === 'DIV') return 'row';
		if (el.id.endsWith('-refusal')) return 'refusal';
		if (el.matches('[data-now-ticked]')) return 'ticked';
		if (el.tagName === 'BUTTON') return 'table';
		if (el.matches('[data-stop-status]')) return 'status';
		return el.tagName;
	});
}

describe('Add cases in one structure (pumps-results-layout.md §5.3, §9 S4, §10 S4)', () => {
	const region = () => screen.getByRole('region', { name: 'Add cases' });
	const plan = () => region().querySelector<HTMLDetailsElement>('[data-lineup-plan]');
	const solveAlls = () => alone().queryAllByRole('button', { name: /^Solve all/, hidden: true });
	/** The fixture's three lineups as scenarios S1 to S3: every case By number running made. */
	const made = (count: number) =>
		withScenarios(withoutScenarios(), lineups.project.scenarios!.slice(0, count));
	const eighteen: Scenario[] = Array.from({ length: 18 }, (_, i) => ({
		id: `S${i + 1}`,
		name: `Case ${i + 1}`,
		overrides: []
	}));
	const parts = () => partsOf(region());

	it('draws a framed panel: its h4 at 14 px with the tag "Changes the project" beside it, a sibling, and the label at 12 px', () => {
		draw(planOn(lineups), { ontable: vi.fn() });
		expect(region()).toHaveClass('rounded-lg', 'border', 'border-slate-300', 'bg-slate-50', 'p-3');
		// Every line in it wraps an unbroken name inside the frame (§5.5; a 40-character name).
		expect(region()).toHaveClass('wrap-break-word');
		const h4 = alone().getByRole('heading', { name: 'Add cases', level: 4 });
		expect(h4).toHaveClass('text-sm', 'font-semibold');
		// The region is named by the h4 alone; the tag is its sibling in the header row (§5.3).
		expect(region()).toHaveAccessibleName('Add cases');
		const tag = alone().getByText('Changes the project', { exact: true });
		expect(tag.parentElement).toBe(h4.parentElement);
		expect([...h4.parentElement!.children]).toEqual([h4, tag]);
		expect(h4.parentElement).toHaveClass('flex', 'flex-wrap', 'items-center');
		expect(tag).toHaveClass('text-xs', 'text-slate-600');
		expect(tag).not.toHaveClass('border');
		// On screen, not visually hidden (jsdom applies no CSS: the classes say so; S4 review MUT-02).
		expect(outOfSight(tag)).toBe(false);
		// "Cases to add" at 12 px (a field label inside a section, §5.2), outside any disclosure.
		const label = alone().getByText('Cases to add', { exact: true });
		expect(label).toHaveClass('label');
		const wrapper = label.closest('.field')!.parentElement!;
		expect(wrapper.classList.contains('[&_.label]:text-xs')).toBe(true);
		expect(label.closest('details')).toBeNull();
		expect(alone().getByRole('radiogroup', { name: 'Cases to add' }).closest('details')).toBeNull();
	});

	it('keeps one structure in every state: the segments, the plan, one row with Add only, the same node in every state, the refusal, the table button', async () => {
		const ontable = vi.fn();
		const states: [string, ReturnType<typeof planOn>, string[]][] = [
			['cases to add', planOn(lineups), ['header', 'segments', 'plan', 'row', 'table', 'status']],
			[
				'every case made',
				planOn(lineups, { project: made(3) }),
				['header', 'segments', 'plan', 'row', 'refusal', 'table', 'status']
			],
			[
				'refused past the limit',
				planOn(lineups, { project: withScenarios(withoutScenarios(), eighteen) }),
				['header', 'segments', 'plan', 'row', 'refusal', 'table', 'status']
			],
			[
				'Each pump off',
				planOn(lineups, { preset: 'each' }),
				['header', 'segments', 'plan', 'row', 'table', 'status']
			],
			[
				'only the base case’s state',
				planOn(closedLeg),
				['header', 'segments', 'plan', 'row', 'refusal', 'table', 'status']
			]
		];
		const [, first] = states[0]!;
		const view = draw(first, { ontable });
		const nodes = {
			segment: alone().getByRole('radio', { name: 'Each pump off' }),
			plan: plan(),
			add: alone().getByRole('button', { name: /^Add / })
		};
		for (const [what, p, order] of states) {
			await view.rerender({ plan: p, ontable });
			expect(parts(), what).toEqual(order);
			// The one row holds Add only: Solve all is the Scenarios menu's (build-density.md §19).
			expect(solveAlls(), what).toHaveLength(0);
			expect(
				[...alone().getByRole('button', { name: /^Add / }).parentElement!.children],
				what
			).toEqual([nodes.add]);
			// The same elements in every state: no control is drawn again elsewhere (A11Y-04).
			expect(alone().getByRole('radio', { name: 'Each pump off' }), what).toBe(nodes.segment);
			expect(plan(), what).toBe(nodes.plan);
			expect(alone().getByRole('button', { name: /^Add / }), what).toBe(nodes.add);
		}
	});

	it('under a gate shows only its sentence and the table button, gates 4 to 6 too (no Solve all); no plan', async () => {
		const ontable = vi.fn();
		const series = (solvedCase('series').groupCurve.body as PumpGroupCurveResponse).station;
		/** The base solve with some pumps' results changed (synthetic): gates 5 and 6. */
		const solved = (change: (r: SolveResponse['solvedState']['pumpResults'][string]) => void) => {
			const response = structuredClone(lineups.solve);
			for (const [id, r] of Object.entries(response.solvedState.pumpResults)) {
				if (['P1', 'P2', 'P3', 'P4'].includes(id)) change(r);
			}
			return { response, stale: false };
		};
		const gates: Partial<LineupPlanInput>[] = [
			{ station: series },
			{ station: { ...stationOf(lineups), arrangement: 'mixed' } },
			{ project: lineups.project, shownCase: 'S1' },
			{ base: { response: lineups.solve, stale: true } },
			{ base: solved((r) => (r.status = 'off')) },
			{ base: solved((r) => (r.operatingFlow = 0)) }
		];
		const view = draw(planOn(lineups, gates[0]!), { ontable });
		for (const values of gates) {
			const p = planOn(lineups, values);
			expect(p.gate).not.toBeNull();
			await view.rerender({ plan: p, ontable });
			// No Solve all at any gate (build-density.md §19): its lasting reason, which a gate's
			// Solve all showed here (S4 review AT-3), is the Scenarios menu's line, read on screen
			// by ScenarioCases.svelte.test.ts.
			expect(solveAlls()).toHaveLength(0);
			expect(region().querySelector('[id$="-solve-all"]')).toBeNull();
			expect(region()).toHaveTextContent(p.gate!);
			expect(plan()).toBeNull();
			expect(alone().queryByRole('radiogroup')).toBeNull();
			expect(alone().getAllByRole('button').at(-1)).toHaveAccessibleName('Pump lineups table…');
			expect(alone().getAllByRole('button')).toHaveLength(1);
		}
	});

	it('the fold: drawn closed only when every planned case exists; open otherwise; opens itself when cases come to remain; never closed by code', async () => {
		const view = draw(planOn(lineups, { project: made(3) }));
		// Drawn with every case made: folded, its summary saying so.
		expect(plan()!.open).toBe(false);
		expect(plan()!.querySelector('summary')).toHaveTextContent(
			'The plan: 3 cases by number running: all 3 made'
		);
		// A scenario deleted: a case remains, so it opens itself.
		await view.rerender({ plan: planOn(lineups, { project: made(2) }) });
		expect(plan()!.open).toBe(true);
		expect(plan()!.querySelector('summary')).toHaveTextContent(
			'The plan: 3 cases by number running: 1 to add'
		);
		// Every case made again (the user's own Add): it stays as the user left it, open.
		await view.rerender({ plan: planOn(lineups, { project: made(3) }) });
		expect(plan()!.open).toBe(true);
		// Closed by the user, then made: it stays closed; another preset with cases to add opens it.
		await fireEvent.click(plan()!.querySelector('summary')!);
		expect(plan()!.open).toBe(false);
		await view.rerender({ plan: planOn(lineups, { project: made(3) }) });
		expect(plan()!.open).toBe(false);
		await view.rerender({ plan: planOn(lineups, { project: made(3), preset: 'each' }) });
		expect(plan()!.open).toBe(true);
		// S1 ("3 of 4 running (Pump P4 off)") is the same case as "Pump P4 off" (sameCase).
		expect(plan()!.querySelector('summary')).toHaveTextContent(
			'The plan: 4 cases with each pump off: 3 to add'
		);
		// A gate, then lifted: drawn again by the rule (closed with every case made, else open).
		const stale = { base: { response: lineups.solve, stale: true } };
		await view.rerender({ plan: planOn(lineups, { ...stale, project: made(3) }) });
		expect(plan()).toBeNull();
		await view.rerender({ plan: planOn(lineups, { project: made(3) }) });
		expect(plan()!.open).toBe(false);
		await view.rerender({ plan: planOn(lineups, { ...stale }) });
		await view.rerender({ plan: planOn(lineups) });
		expect(plan()!.open).toBe(true);
	});

	it('is open, not folded, for a plan refused at the limit or one of base-state cases only (nothing made)', () => {
		draw(planOn(lineups, { project: withScenarios(withoutScenarios(), eighteen) }));
		expect(plan()!.open).toBe(true);
		expect(plan()!.querySelector('summary')).toHaveTextContent(
			'The plan: 3 cases by number running: 3 to add'
		);
		document.body.innerHTML = '';
		draw(planOn(closedLeg));
		expect(plan()!.open).toBe(true);
		expect(plan()!.querySelector('summary')).toHaveTextContent(
			"The plan: 1 case by number running: 0 made, 1 not made (the base case's state)"
		);
	});

	it('holds in the plan, in D24 §7.11’s order: About, the sentence, the stop order, the cases, the names line and which pump each id is', async () => {
		// The lineups' pumps renamed past the names' budget, each name without its id: the names
		// write ids, and the plan says which pump each is (§6.2).
		const project = withoutScenarios();
		const long = ['north', 'south', 'east', 'west'];
		for (const c of project.components) {
			if (c.type === 'pump')
				c.name = `Condenser water pump of the ${long[Number(c.id[1]) - 1]} loop`;
		}
		const p = planOn(lineups, { project, memberIds: ['P2', 'P3'] });
		expect(p.cases.map((c) => c.name)).toEqual(['3 of 4 running (P3 off)']);
		draw(p);
		const inside = [...plan()!.querySelector(':scope > div')!.children].map((el) =>
			el.matches('[data-stop-order]')
				? 'stop order'
				: el.tagName === 'UL'
					? 'cases'
					: el.textContent!.trim()
		);
		expect(inside).toEqual([
			p.about,
			p.sentence,
			'stop order',
			'Cases:',
			'cases',
			'Names count every pump of the group Condenser water pump of the north loop, Condenser water pump of the south loop, Condenser water pump of the east loop and Condenser water pump of the west loop.',
			'In the names, P3 is Condenser water pump of the east loop and P2 is Condenser water pump of the south loop.'
		]);
		expect(plan()!.querySelector('[data-stop-order] > summary')).toHaveTextContent(
			'Stop order: P3 stops; P2 stays on in every case'
		);
		const ids = alone().getByText(/^In the names, /);
		expect(ids).toBeVisible();
		expect(outOfSight(ids)).toBe(false);
		await fireEvent.click(plan()!.querySelector(':scope > summary')!);
		expect(ids).not.toBeVisible();
	});

	it('summarises the plan, its lead in medium weight and its words regular', () => {
		draw(planOn(lineups));
		const summary = plan()!.querySelector(':scope > summary')!;
		expect(summary).toHaveClass('more-summary');
		expect(summary.textContent!.replace(/\s+/g, ' ').trim()).toBe(
			'The plan: 3 cases by number running: 3 to add'
		);
		const clause = summary.querySelector('span > span')!;
		expect(clause.textContent).toBe(': 3 cases by number running: 3 to add');
		expect(clause).toHaveClass('font-normal', 'text-slate-600');
		expect(outOfSight(clause)).toBe(false);
		// Its chevron turns without motion when reduced motion is asked for (§5.3 markup rules), and
		// is the plan's own: the stop order's turns with the stop order alone (named groups).
		const chevrons = [...region().querySelectorAll('summary svg')];
		expect(chevrons).toHaveLength(2);
		expect(chevrons[0]).toHaveClass('motion-reduce:transition-none', 'group-open/plan:rotate-90');
		expect(chevrons[1]).toHaveClass('motion-reduce:transition-none', 'group-open/stop:rotate-90');
	});

	it('shows Add’s refusal after its row, visible; Solve all’s reason is the Scenarios menu’s, not the block’s', async () => {
		const view = draw(planOn(lineups, { project: made(3) }), { ontable: vi.fn() });
		const add = alone().getByRole('button', { name: 'Add cases' });
		// After the row, visible (§5.3 item 4), as §5.3 orders them; then the table button: no
		// Solve all reason between (build-density.md §19: the Scenarios menu's line shows it while it
		// lasts and hides it while it passes, read by ScenarioCases.svelte.test.ts).
		const refusal = region().querySelector('[id$="-refusal"]')!;
		expect(refusal).toHaveTextContent(/^Every case by number running already exists: /);
		expect(refusal).toHaveClass('hint');
		expect(refusal).not.toHaveClass('sr-only');
		expect(refusal).toBeVisible();
		expect(outOfSight(refusal)).toBe(false);
		expect(add).toHaveAccessibleDescription(refusal.textContent!);
		expect(refusal.previousElementSibling).toBe(add.parentElement);
		expect(refusal.nextElementSibling).toBe(
			alone().getByRole('button', { name: 'Pump lineups table…' })
		);
		expect(region().querySelector('[id$="-solve-all"]')).toBeNull();
		// Cases to add: no refusal, and nothing in its place.
		await view.rerender({ plan: planOn(lineups) });
		expect(region().querySelector('[id$="-refusal"]')).toBeNull();
		expect(alone().getByRole('button', { name: /^Add / }).parentElement!.nextElementSibling).toBe(
			alone().getByRole('button', { name: 'Pump lineups table…' })
		);
		expect(region().querySelector('[id$="-solve-all"]')).toBeNull();
	});

	it('keeps the focus on the chosen segment after a preset change with the plan open', async () => {
		let preset: 'running' | 'each' = 'running';
		const props = () => ({
			plan: planOn(lineups, { preset }),
			onpreset: (next: 'running' | 'each') => (preset = next)
		});
		const view = render(PumpLineupsBlock, props());
		expect(plan()!.open).toBe(true);
		const each = alone().getByRole('radio', { name: 'Each pump off' });
		each.focus();
		await fireEvent.click(each);
		expect(preset).toBe('each');
		await view.rerender(props());
		expect(alone().getByRole('radio', { name: 'Each pump off' })).toBe(each);
		expect(each).toBeChecked();
		expect(each).toHaveFocus();
		expect(plan()!.open).toBe(true);
		expect(plan()!.querySelector('summary')).toHaveTextContent(
			'The plan: 4 cases with each pump off: 4 to add'
		);
	});
});

describe('Add cases in the workspace since S4 (pumps-results-layout.md §5.3, §10 S4)', () => {
	const plan = () => block().querySelector<HTMLDetailsElement>('[data-lineup-plan]')!;
	const ticked = () => block().querySelector('[data-now-ticked]');
	const NOW_TICKED = "Now ticked: “Also show the other cases' station duties” (Group chart).";

	it('after an Add that ticked “Also show …”: “Now ticked” on screen and in the polite line, the focus kept on Add, the plan as the user left it', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		expect(ws.pumpGroupOthers).toBe(false);
		// Cases to add: the plan open; the user closes it.
		expect(plan().open).toBe(true);
		expect(plan().querySelector('summary')).toHaveTextContent(
			'The plan: 3 cases by number running: 3 to add'
		);
		await fireEvent.click(plan().querySelector('summary')!);
		expect(plan().open).toBe(false);
		expect(ticked()).toBeNull();
		const add = inBlock().getByRole('button', { name: 'Add 3 cases' });
		await press('Add 3 cases');
		// The focus stays on Add, the same node (build-density.md §19).
		await waitFor(() => expect(add).toHaveFocus());
		expect(add).toHaveAccessibleName('Add cases');
		expect(ws.pumpGroupOthers).toBe(true);
		// The line, visible, and the same words in the block's polite line: the line is drawn after
		// Add, which keeps the focus, so the focus would not pass it.
		await waitFor(() => expect(stopStatus()).toBe(NOW_TICKED));
		expect(ticked()).toHaveTextContent(NOW_TICKED);
		expect(ticked()).toBeVisible();
		// On screen, not visually hidden (jsdom applies no CSS: its classes say so).
		expect(outOfSight(ticked()!)).toBe(false);
		expect(block().querySelector('[data-stop-status]')).toHaveAttribute('aria-live', 'polite');
		// Every case made: the plan stays as the user left it (closed), its summary saying so.
		expect(plan().open).toBe(false);
		expect(plan().querySelector('summary')).toHaveTextContent(
			'The plan: 3 cases by number running: all 3 made'
		);
		// The after-Add state keeps the one structure: "Now ticked" after the refusal, before the
		// table button; the segments still first (§5.3).
		expect(partsOf(block())).toEqual([
			'header',
			'segments',
			'plan',
			'row',
			'refusal',
			'ticked',
			'table',
			'status'
		]);
		// The box unticked: the line goes, its polite copy with it (§5.3: the same sentence), and
		// neither comes back when it is ticked again.
		const box = within(card()).getByRole('checkbox', {
			name: "Also show the other cases' station duties"
		});
		await fireEvent.click(box);
		await waitFor(() => expect(ticked()).toBeNull());
		expect(box).not.toBeChecked();
		expect(stopStatus()).toBe('');
		await fireEvent.click(box);
		expect(ws.pumpGroupOthers).toBe(true);
		expect(ticked()).toBeNull();
		expect(stopStatus()).toBe('');
	}, 20_000);

	it('after Undo the plan opens itself; an Add with the plan open leaves it open; an Add with “Also show …” already ticked says nothing', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await fireEvent.click(plan().querySelector('summary')!);
		await press('Add 3 cases');
		await waitFor(() => expect(stopStatus()).toBe(NOW_TICKED));
		expect(plan().open).toBe(false);
		// Undo: cases remain again, so the plan opens itself, and "Now ticked" goes with its Add,
		// on screen and in the polite line.
		expect(ws.undo()).toBe(true);
		await waitFor(() => expect(plan().open).toBe(true));
		expect(ticked()).toBeNull();
		expect(stopStatus()).toBe('');
		// "Also show …" is still ticked (page state): this Add ticks nothing, so nothing is said.
		expect(ws.pumpGroupOthers).toBe(true);
		const add = inBlock().getByRole('button', { name: 'Add 3 cases' });
		await press('Add 3 cases');
		// The focus stays on Add, the same node (build-density.md §19).
		await waitFor(() => expect(add).toHaveFocus());
		expect(add).toHaveAccessibleName('Add cases');
		expect(ticked()).toBeNull();
		await new Promise((resolve) => setTimeout(resolve, 100));
		expect(stopStatus()).toBe('');
		// The user's own Add left the plan open: it stays open.
		expect(plan().open).toBe(true);
		expect(plan().querySelector('summary')).toHaveTextContent(
			'The plan: 3 cases by number running: all 3 made'
		);
	}, 20_000);

	it('another preset chosen after an Add: “Now ticked” goes, on screen and in the polite line, though every case of both presets is made', async () => {
		const { ws, calls } = setup(withoutScenarios(oneOff), () => oneOff, oneOff);
		await openCard(ws, calls);
		await fireEvent.click(inBlock().getByRole('radio', { name: 'Each pump off' }));
		await press('Add 2 cases');
		await waitFor(() => expect(stopStatus()).toBe(NOW_TICKED));
		expect(ticked()).toHaveTextContent(NOW_TICKED);
		expect(plan().querySelector('summary')).toHaveTextContent(
			'The plan: 2 cases with each pump off: all 2 made'
		);
		// By number running's one case is "Pump PB off" made: nothing remains, only the preset moved.
		await fireEvent.click(inBlock().getByRole('radio', { name: 'By number running' }));
		expect(plan().querySelector('summary')).toHaveTextContent(
			'The plan: 1 case by number running: 1 made'
		);
		expect(ws.pumpGroupOthers).toBe(true);
		expect(ticked()).toBeNull();
		expect(stopStatus()).toBe('');
	}, 20_000);

	it('a second Add that ticks “Also show …” again is said: the polite line is drawn empty for a frame before its words (§7 Live regions)', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		await press('Add 3 cases');
		await waitFor(() => expect(stopStatus()).toBe(NOW_TICKED));
		const box = within(card()).getByRole('checkbox', {
			name: "Also show the other cases' station duties"
		});
		await fireEvent.click(box);
		await waitFor(() => expect(ticked()).toBeNull());
		expect(stopStatus()).toBe('');
		await fireEvent.click(inBlock().getByRole('radio', { name: 'Each pump off' }));
		expect(plan().querySelector('summary')).toHaveTextContent(
			'The plan: 4 cases with each pump off: 3 to add'
		);
		// The line at each animation frame from the press on (this sampler is registered before
		// the block's own frames), and at the first task after the press.
		const frames: string[] = [];
		let sampling = true;
		/** The sampler's next frame, cancelled when sampling stops, so none runs after cleanup. */
		let next: number;
		const sample = () => {
			frames.push(stopStatus() ?? '');
			if (sampling) next = requestAnimationFrame(sample);
		};
		let firstTask: string | null = null;
		setTimeout(() => (firstTask = stopStatus()), 0);
		next = requestAnimationFrame(sample);
		await press('Add 3 cases');
		expect(ws.pumpGroupOthers).toBe(true);
		expect(ticked()).toHaveTextContent(NOW_TICKED);
		await waitFor(() => expect(stopStatus()).toBe(NOW_TICKED));
		await waitFor(() => expect(frames.at(-1)).toBe(NOW_TICKED));
		sampling = false;
		cancelAnimationFrame(next);
		// Empty in the press's own task and at its first frame, then the words, nothing else.
		expect(firstTask).toBe('');
		expect(frames[0]).toBe('');
		const spoke = frames.indexOf(NOW_TICKED);
		expect(spoke).toBeGreaterThan(0);
		expect(frames.slice(0, spoke).every((t) => t === '')).toBe(true);
		expect(frames.slice(spoke).every((t) => t === NOW_TICKED)).toBe(true);
	}, 20_000);
});

// ---- One Solve all, in the Scenarios menu (build-density.md §19) ----------------------------

describe('the block has no Solve all: the Scenarios menu’s is the one (build-density.md §19)', () => {
	const words = (text: string | null | undefined) => (text ?? '').replace(/\s+/g, ' ').trim();
	const region = () => screen.getByRole('region', { name: 'Add cases' });
	const solveAlls = () =>
		within(region()).queryAllByRole('button', { name: /^Solve all/, hidden: true });
	const made = (count: number) =>
		withScenarios(withoutScenarios(), lineups.project.scenarios!.slice(0, count));
	const eighteen: Scenario[] = Array.from({ length: 18 }, (_, i) => ({
		id: `S${i + 1}`,
		name: `Case ${i + 1}`,
		overrides: []
	}));

	it('draws Add alone in its row in every state, and under every gate only its sentence and the table button', async () => {
		const ontable = vi.fn();
		const series = (solvedCase('series').groupCurve.body as PumpGroupCurveResponse).station;
		/** The base solve with some pumps' results changed (synthetic): gates 5 and 6. */
		const solved = (change: (r: SolveResponse['solvedState']['pumpResults'][string]) => void) => {
			const response = structuredClone(lineups.solve);
			for (const [id, r] of Object.entries(response.solvedState.pumpResults)) {
				if (['P1', 'P2', 'P3', 'P4'].includes(id)) change(r);
			}
			return { response, stale: false };
		};
		const states: [string, ReturnType<typeof planOn>][] = [
			['cases to add', planOn(lineups)],
			['every case made', planOn(lineups, { project: made(3) })],
			[
				'refused past the limit',
				planOn(lineups, { project: withScenarios(withoutScenarios(), eighteen) })
			],
			['Each pump off', planOn(lineups, { preset: 'each' })],
			['only the base case’s state', planOn(closedLeg)]
		];
		const gates: [string, Partial<LineupPlanInput>][] = [
			['1, series', { station: series }],
			['2, mixed', { station: { ...stationOf(lineups), arrangement: 'mixed' } }],
			['3, a scenario shown', { project: lineups.project, shownCase: 'S1' }],
			['4, out of date', { base: { response: lineups.solve, stale: true } }],
			['5, fewer than two on', { base: solved((r) => (r.status = 'off')) }],
			['6, none carries flow', { base: solved((r) => (r.operatingFlow = 0)) }]
		];
		const view = draw(states[0]![1], { ontable });
		const add = alone().getByRole('button', { name: /^Add / });
		for (const [what, p] of states) {
			await view.rerender({ plan: p, ontable });
			expect(solveAlls(), what).toHaveLength(0);
			expect(alone().getByRole('button', { name: /^Add / }), what).toBe(add);
			expect([...add.parentElement!.children], what).toEqual([add]);
			expect(region().querySelector('[id$="-solve-all"]'), what).toBeNull();
		}
		for (const [what, values] of gates) {
			const p = planOn(lineups, values);
			expect(p.gate, what).not.toBeNull();
			await view.rerender({ plan: p, ontable });
			expect(solveAlls(), `gate ${what}`).toHaveLength(0);
			expect(
				alone()
					.getAllByRole('button')
					.map((b) => words(b.textContent)),
				`gate ${what}`
			).toEqual(['Pump lineups table…']);
			const parts = [...region().children].map((el) =>
				el.querySelector(':scope > h4')
					? 'header'
					: el.tagName === 'P' && words(el.textContent) === p.gate
						? 'gate'
						: el.tagName === 'BUTTON'
							? 'table'
							: el.matches('[data-stop-status]')
								? 'status'
								: el.outerHTML
			);
			expect(parts, `gate ${what}`).toEqual(['header', 'gate', 'table', 'status']);
		}
	});

	it('keeps the focus on Add after Add, then “Add cases”, refused and described; Tab goes on to “Pump lineups table…”', async () => {
		const { ws, calls } = setup(withoutScenarios());
		await openCard(ws, calls);
		const add = inBlock().getByRole('button', { name: 'Add 3 cases' });
		await press('Add 3 cases');
		expect(ws.scenarios).toHaveLength(3);
		// A frame and a task after the press: no focus move came after it.
		await new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)));
		expect(document.activeElement).toBe(add);
		expect(add).toHaveAccessibleName('Add cases');
		expect(add).toHaveAttribute('aria-disabled', 'true');
		expect(add).toHaveAccessibleDescription(
			'Every case by number running already exists: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)».'
		);
		// Its visible refusal, on screen.
		const refusal = document.getElementById(add.getAttribute('aria-describedby')!)!;
		expect(outOfSight(refusal)).toBe(false);
		expect(inBlock().queryAllByRole('button', { name: /^Solve all/, hidden: true })).toHaveLength(
			0
		);
		// The notice names the Scenarios menu's Solve all.
		expect(ws.notice?.text).toBe(
			'Added 3 cases by number running: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)». Solve all, in the Scenarios menu at the top, solves every case not yet solved; Undo removes them.'
		);
		// Tab from Add: the table button next, and last in the block.
		const stops = [
			...block().querySelectorAll<HTMLElement>(
				'button, a[href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])'
			)
		];
		expect(stops.slice(stops.indexOf(add)).map((el) => words(el.textContent))).toEqual([
			'Add cases',
			'Pump lineups table…'
		]);
	}, 20_000);
});
