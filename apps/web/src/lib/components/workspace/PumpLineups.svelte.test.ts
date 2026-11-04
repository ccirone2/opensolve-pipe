/**
 * The Pump lineups table in the Scenarios manager (CLAUDE.md D24, proposal pump-lineups.md §8 and
 * §10.2 "Component"), in the workspace with testWorkspace and a fixed clock:
 * - a press in the rendered table and a press of Build's Status segment (RegistryField, in the
 *   Build pane) give the same project JSON, also where an app-made name follows;
 * - the tabs only with two pumps or more, the manager xl on both tabs (wide otherwise), the tab
 *   remembered, Cases when a scenario's card is asked for, the panel .dense;
 * - the grid's roles, caption and group header row (a mixed group's header, the series sentence);
 * - the switches' names from the visible headers (never their state word), aria-checked, the
 *   changed description and title; the base cells aria-readonly;
 * - every key of §8.7, one Tab stop, and the focus on the active cell after a press, an undo, a
 *   redo and a rename; the Tab stop never vanishing (an undone New lineup, an undone pump, an
 *   undo to one pump);
 * - New lineup (its name, the focus, the status line, the 20 limit), Undo and Redo (their names,
 *   the status line, Ctrl+Z and Ctrl+Shift+Z from a switch), the manager's status line in the
 *   Cases tab (a Remove's rename; the count form), Delete's focus with the tab row, the card's
 *   filter and Show every pump, the alert line on a refusal;
 * - the phone (matchMedia stubbed): the picker and its default, the fall back after an undo, the
 *   segments with Changed · Base · Reset (Reset following the name rule), the base case's list,
 *   New lineup picking the new case.
 * The projects are the shared fixture's `two-systems` (apps/api/tests/fixtures/pump_groups_input.py)
 * and made-up test inputs (testing/lineups.ts); every string is §8.12's, word for word.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component, Override, Project, Scenario } from '$lib/api/types';
import { projectWith } from '$lib/testing/helpers';
import { pipe, pump, series, station, tank, twoByTwo } from '$lib/testing/lineups';
import { testWorkspace } from '$lib/testing/workspace';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import { canonicalJson } from '$lib/utils/json';
import { lineupName, renameNotice } from '$lib/utils/pump-lineups';
import {
	LIMIT_TEXT,
	MAX_CHANGES,
	MAX_SCENARIOS,
	SCENARIO_DESCRIPTION_LIMIT,
	scenariosOf,
	withScenarios
} from '$lib/utils/scenarios';
import { pumpTransferExample } from '$lib/utils/examples';
import type { Workspace } from '$lib/state/workspace.svelte';
import WorkspaceView from './Workspace.svelte';

/** A fixed clock: two workspaces stamp the same metadata.modified. */
const NOW = () => '2026-11-04T10:00:00.000Z';

interface FixtureCase {
	name: string;
	project: Project;
}
/** `two-systems`: PA and PB (PB off in the base), the P1–P3 ladder, a lone P9; S1 to S3. */
const twoSystems = () =>
	structuredClone(
		(fixture.cases as unknown as FixtureCase[]).find((c) => c.name === 'two-systems')!.project
	);
/** `two-systems` with these scenarios after its own. */
const withMore = (...more: Scenario[]) =>
	withScenarios(twoSystems(), [...scenariosOf(twoSystems()), ...more]);

const status = (componentId: string, value: 'on' | 'off'): Override => ({
	kind: 'component',
	componentId,
	field: 'status',
	value
});
const named = (id: string, name: string, overrides: Override[] = []): Scenario => ({
	id,
	name,
	overrides
});

function setup(project: Project): Workspace {
	const ws = testWorkspace(project, { now: NOW });
	render(WorkspaceView, { workspace: ws });
	return ws;
}

/** Let a handler that awaits a tick before it moves the focus finish. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

const manager = () => screen.getByRole('dialog', { name: 'Scenarios' });
const inManager = () => within(manager());
const grid = () => inManager().getByRole('grid', { name: 'Pumps on or off in each case' });
const inGrid = () => within(grid());
const statusLine = () => inManager().getByRole('status');
const alertLine = () => inManager().getByRole('alert');
const tab = (name: string | RegExp) => inManager().getByRole('tab', { name });

/** Open the manager (on the tab last used, or as `options` asks), then Pump lineups. */
async function openLineups(ws: Workspace, options: Parameters<Workspace['openManager']>[0] = {}) {
	ws.openManager(options);
	await tick();
	await screen.findByRole('dialog', { name: 'Scenarios' });
	if (tab('Pump lineups').getAttribute('aria-selected') !== 'true') {
		await fireEvent.click(tab('Pump lineups'));
	}
	return manager();
}

/** The switch of `pumpLabel` in case `caseName`: its name is its visible headers (§8.5). */
const cell = (pumpLabel: string, caseName: string) =>
	inGrid().getByRole('switch', { name: `${pumpLabel} ${caseName}` });

/** The grid's one Tab stop (§8.7). */
function tabStops(): HTMLElement[] {
	return [...grid().querySelectorAll<HTMLElement>('[tabindex]')].filter((e) => e.tabIndex === 0);
}

/** Press a switch as a keyboard user does: focused, then activated; its handler finished. */
async function press(element: HTMLElement) {
	element.focus();
	await fireEvent.click(element);
	await settle();
}

/** A key in the grid, on the focused element. */
async function key(init: KeyboardEventInit) {
	const target = document.activeElement as HTMLElement;
	const result = await fireEvent.keyDown(target, init);
	await settle();
	return result;
}

/** The scenarios' names, in order. */
const names = (ws: Workspace) => ws.scenarios.map((s) => s.name);

/**
 * The elements `element`'s aria-describedby points to (§8.2, §8.5): the description itself, not
 * the title, which an accessible-description check falls back to when there is none.
 */
function describers(element: HTMLElement): HTMLElement[] {
	const ids = element.getAttribute('aria-describedby')?.split(' ').filter(Boolean) ?? [];
	return ids.map((i) => document.getElementById(i)!);
}

/** Count the changes made to a live region's content (each one is announced). */
function mutations(target: HTMLElement): { count: () => number; stop: () => void } {
	let n = 0;
	const observer = new MutationObserver((records) => {
		n += records.length;
	});
	observer.observe(target, { childList: true, characterData: true, subtree: true });
	return {
		count: () => {
			n += observer.takeRecords().length;
			return n;
		},
		stop: () => observer.disconnect()
	};
}

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------------------------
// Identity through the components (§8.6 item 1)
// ---------------------------------------------------------------------------------------------

describe('a press is Build’s own edit', () => {
	it('three presses in the table and three presses of Build’s Status segment give the same project', async () => {
		// "Scenario 4" is app-made: both ways rename it, in the same steps.
		const project = withMore(named('S4', 'Scenario 4'));
		const table = setup(structuredClone(project));
		await openLineups(table);
		for (const pumpLabel of ['Pump P3', 'Pump P1', 'Pump PB']) {
			await press(cell(pumpLabel, table.caseName('S4')));
			expect(document.activeElement).toBe(cell(pumpLabel, table.caseName('S4')));
		}
		const tableJson = canonicalJson(table.store.project);
		const tableNames = names(table);
		document.body.innerHTML = '';

		const build = setup(structuredClone(project));
		build.setCase('S4');
		const buildPane = () => within(screen.getByRole('region', { name: 'Build' }));
		for (const [pumpId, value] of [
			['P3', 'Off'],
			['P1', 'Off'],
			['PB', 'On']
		] as const) {
			build.nav.jumpTo(pumpId);
			await tick();
			const segment = buildPane().getByRole('radiogroup', { name: 'Status' });
			await fireEvent.click(within(segment).getByRole('radio', { name: value }));
		}
		expect(names(build)).toEqual(tableNames);
		expect(tableNames[3]).not.toBe('Scenario 4');
		expect(canonicalJson(build.store.project)).toBe(tableJson);
	});
});

// ---------------------------------------------------------------------------------------------
// Tabs and width (§8.1)
// ---------------------------------------------------------------------------------------------

describe('the tabs and the width', () => {
	it('with no pump or one pump: no tabs, the manager stays wide', async () => {
		for (const project of [
			projectWith([tank('R1', 1)], [], pumpTransferExample().pumpLibrary),
			pumpTransferExample()
		]) {
			const ws = setup(project);
			ws.openManager();
			await tick();
			const dialog = await screen.findByRole('dialog', { name: 'Scenarios' });
			expect(within(dialog).queryByRole('tablist')).toBeNull();
			expect(within(dialog).queryByRole('tabpanel')).toBeNull();
			expect(dialog.className).toContain('sm:max-w-2xl');
			expect(dialog.className).not.toContain('lg:max-w-5xl');
			// The heading stays visible.
			expect(within(dialog).getByRole('heading', { name: 'Cases (1)' })).toHaveClass(
				'section-title'
			);
			document.body.innerHTML = '';
		}
	});

	it('with one pump: the Cases prose as before L2, no max-w-prose; with the tab row it is capped', async () => {
		/** Letters a link cannot compress: with them the link is longer than 8,000 characters. */
		let seed = 12345;
		const noise = (n: number) =>
			Array.from({ length: n }, () => {
				seed = (seed * 1103515245 + 12345) % 2 ** 31;
				return 'abcdefghijklmnopqrstuvwxyz0123456789'[seed % 36];
			}).join('');
		/**
		 * `base` with every element of the Cases prose drawn: a change, a scenario with none, a
		 * change that no longer applies (its pump deleted), a value with a problem (a maximum speed
		 * below the flow control's minimum, of `pumpId`), the 20 scenarios' limit line and the
		 * long-link warning.
		 */
		function everyLine(base: Project, pumpId: string, other: Override): Project {
			const project = structuredClone(base);
			const pump = project.components.find((c) => c.id === pumpId)!;
			if (pump.type === 'pump') pump.control = { mode: 'flow', setpoint: 0.015, minSpeed: 0.85 };
			project.metadata.description = noise(5000);
			const speed = (value: number): Override => ({
				kind: 'component',
				componentId: pumpId,
				field: 'speed',
				value
			});
			const lapsed: Override = { kind: 'component', componentId: 'X7', field: 'speed', value: 0.9 };
			const own = scenariosOf(project);
			const more = [
				named('L1', 'Empty'),
				named('L2', 'Lapsed', [other, lapsed]),
				named('L3', 'Problem', [speed(0.8)])
			];
			for (let i = own.length + more.length + 1; i <= MAX_SCENARIOS; i++) {
				more.push(named(`L${i}`, `Case ${i}`, [other]));
			}
			return withScenarios(project, [
				...own,
				...more.map((s) => ({ ...s, description: noise(SCENARIO_DESCRIPTION_LIMIT) }))
			]);
		}
		/** Each element of the Cases prose (§8.1), the manager's status and alert lines too. */
		const lines = (dialog: HTMLElement) => {
			const w = within(dialog);
			return {
				intro: w.getByText(/^A scenario keeps another operating/),
				base: w.getByText('The network as built.'),
				change: w.getAllByText(/^Base: /)[0]!.parentElement!,
				none: w.getByText(/^No changes yet/),
				lapsed: w.getByText(/: no longer applies, ignored when solving \(/),
				problem: w.getByText(/^The value Problem sets for/),
				limit: w.getByText(LIMIT_TEXT),
				link: w.getByText(/^The link to this project is longer than 8,000 characters/),
				status: w.getByRole('status'),
				alert: w.getByRole('alert')
			};
		};

		// One pump: every one of them drawn, none capped.
		const level: Override = {
			kind: 'component',
			componentId: 'R2',
			field: 'liquidLevel',
			value: 3
		};
		const one = everyLine(
			withScenarios(pumpTransferExample(), [named('S1', 'Level', [level])]),
			'P1',
			level
		);
		const ws = setup(one);
		expect(ws.store.urlTooLong).toBe(true);
		ws.openManager({ focus: 'L3' });
		await tick();
		const dialog = await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(within(dialog).queryByRole('tablist')).toBeNull();
		await fireEvent.click(within(dialog).getByText('Empty'));
		for (const [name, element] of Object.entries(lines(dialog))) {
			expect(element, name).toBeInTheDocument();
			expect(element, name).not.toHaveClass('max-w-prose');
		}
		expect(dialog.querySelectorAll('.max-w-prose')).toHaveLength(0);
		document.body.innerHTML = '';

		// With the tab row (xl): the intro, the cards' text, the limit line, the long-link warning
		// and the manager's lines on the Cases tab capped (§8.1).
		const speed: Override = { kind: 'component', componentId: 'P9', field: 'speed', value: 0.9 };
		const two = setup(everyLine(twoSystems(), 'P9', speed));
		expect(two.store.urlTooLong).toBe(true);
		two.openManager({ focus: 'L3' });
		await tick();
		const xl = await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(tab('Cases (21)')).toHaveAttribute('aria-selected', 'true');
		for (const [name, element] of Object.entries(lines(xl))) {
			expect(element, name).toHaveClass('max-w-prose');
		}
	});

	it('opens with the dialog’s title out of the Tab order: focusable only when the manager puts the focus there', async () => {
		const ws = setup(twoSystems());
		ws.openManager();
		await tick();
		const dialog = await screen.findByRole('dialog', { name: 'Scenarios' });
		const title = within(dialog).getByRole('heading', { name: 'Scenarios', level: 2 });
		// No tabindex: a dialog's first focus (showModal) is its first control, Close, as before L2.
		expect(title).not.toHaveAttribute('tabindex');
	});

	it('with two pumps or more: the tabs, xl on both, the tab remembered, Cases for a card asked for', async () => {
		const ws = setup(twoSystems());
		ws.openManager();
		await tick();
		const dialog = await screen.findByRole('dialog', { name: 'Scenarios' });
		const tablist = within(dialog).getByRole('tablist', { name: 'Scenarios view' });
		expect(
			within(tablist)
				.getAllByRole('tab')
				.map((t) => t.textContent?.trim())
		).toEqual(['Cases (4)', 'Pump lineups']);
		expect(tab('Cases (4)')).toHaveAttribute('aria-selected', 'true');
		expect(dialog.className).toContain('lg:max-w-5xl');
		expect(inManager().getByRole('tabpanel', { name: 'Cases (4)' })).toBeInTheDocument();
		// The heading is the tab's: sr-only.
		expect(inManager().getByRole('heading', { name: 'Cases (4)' })).toHaveClass('sr-only');
		// The Cases tab's footer.
		expect(inManager().getByRole('button', { name: 'New scenario' })).toBeInTheDocument();
		expect(inManager().queryByRole('button', { name: 'New lineup' })).toBeNull();

		await fireEvent.click(tab('Pump lineups'));
		expect(ws.managerTab).toBe('lineups');
		expect(tab('Pump lineups')).toHaveAttribute('aria-selected', 'true');
		expect(manager().className).toContain('lg:max-w-5xl');
		const panel = inManager().getByRole('tabpanel', { name: 'Pump lineups' });
		expect(panel.querySelector('[data-pump-lineups]')).toHaveClass('dense');
		expect(inManager().queryByRole('button', { name: 'New scenario' })).toBeNull();
		for (const name of ['Undo', 'Redo', 'New lineup', 'Done']) {
			expect(inManager().getByRole('button', { name })).toBeInTheDocument();
		}
		// ← and → between the tabs.
		tab('Pump lineups').focus();
		await fireEvent.keyDown(tab('Pump lineups'), { key: 'ArrowLeft' });
		expect(tab('Cases (4)')).toHaveAttribute('aria-selected', 'true');
		expect(document.activeElement).toBe(tab('Cases (4)'));
		await fireEvent.keyDown(tab('Cases (4)'), { key: 'ArrowRight' });
		expect(tab('Pump lineups')).toHaveAttribute('aria-selected', 'true');

		// Done, then the header's Scenarios: the tab last used.
		await fireEvent.click(inManager().getByRole('button', { name: 'Done' }));
		expect(screen.queryByRole('dialog', { name: 'Scenarios' })).toBeNull();
		ws.openManager();
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(tab('Pump lineups')).toHaveAttribute('aria-selected', 'true');
		await fireEvent.click(inManager().getByRole('button', { name: 'Done' }));

		// A scenario's card asked for (the results' Review): Cases.
		ws.openManager({ focus: 'S2' });
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(tab('Cases (4)')).toHaveAttribute('aria-selected', 'true');
		expect(ws.managerTab).toBe('cases');
		// A card asked for by setting the page state directly, as before L2: Cases too.
		await fireEvent.click(inManager().getByRole('button', { name: 'Done' }));
		ws.managerTab = 'lineups';
		ws.managerFocus = 'S1';
		ws.managerOpen = true;
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(tab('Cases (4)')).toHaveAttribute('aria-selected', 'true');
	});
});

// ---------------------------------------------------------------------------------------------
// The grid (§8.3 to §8.5, §8.7)
// ---------------------------------------------------------------------------------------------

describe('the grid', () => {
	it('has explicit roles, the caption, the group header row with each group’s ids', async () => {
		const ws = setup(twoSystems());
		await openLineups(ws);
		const g = grid();
		expect(g.tagName).toBe('TABLE');
		expect(g.querySelector('caption')).toHaveTextContent('Pumps on or off in each case');
		expect(g.querySelector('caption')).toHaveClass('sr-only');
		expect(inGrid().getAllByRole('rowgroup')).toHaveLength(2);
		const rows = inGrid().getAllByRole('row');
		expect(rows).toHaveLength(2 + 4);
		const groupRow = within(rows[0]!).getAllByRole('columnheader');
		expect(groupRow.map((h) => [h.textContent?.trim(), h.getAttribute('colspan')])).toEqual([
			['Case', null],
			['Pumps together, PA and PB', '2'],
			['Pumps together, P1 to P3', '3'],
			['Other pumps', '1']
		]);
		expect(groupRow[0]).toHaveAttribute('rowspan', '2');
		const pumpRow = within(rows[1]!).getAllByRole('columnheader');
		expect(pumpRow.map((h) => h.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			'Pump PA PA',
			'Pump PB PB',
			'Pump P1 P1',
			'Pump P2 P2',
			'Pump P3 P3',
			'Pump P9 P9'
		]);
		const rowHeaders = inGrid().getAllByRole('rowheader');
		expect(rowHeaders.map((h) => h.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			'Base case Set in Build',
			'PB in service, PA off S1',
			'2 of 2 running; 2 of 3 running (Pump P3 off) S2',
			'Aged pipe S3 1 other change'
		]);
		expect(inGrid().getAllByRole('gridcell')).toHaveLength(4 * 6);
		// The base case's six cells are read-only gridcells; the scenarios' hold switches.
		const baseCells = within(rows[2]!).getAllByRole('gridcell');
		expect(baseCells.map((c) => [c.textContent?.trim(), c.getAttribute('aria-readonly')])).toEqual(
			['On', 'Off', 'On', 'On', 'On', 'On'].map((w) => [w, 'true'])
		);
		expect(within(rows[2]!).queryByRole('switch')).toBeNull();
		expect(inGrid().getAllByRole('switch')).toHaveLength(3 * 6);
		// No series group: no series sentence. The shown case is the base: no Shown.
		expect(manager()).not.toHaveTextContent('Pumps in series');
		expect(inGrid().queryByText('Shown')).toBeNull();
		expect(manager()).toHaveTextContent(
			"Each case's pumps, on or off; in a name, running means switched on. Pressing a cell turns that pump on or off in that case only, the same change as in Build, one undo step each; the base case is changed in Build. A corner mark is the case's own value; unmarked cells follow the base case."
		);
	});

	it('heads a mixed group and a series one, with the series sentence; marks the case shown', async () => {
		const mixed = twoByTwo();
		const project = withScenarios(
			projectWith(
				[...mixed.components, tank('R3', 1), pump('PA'), pump('PB'), tank('R4', 1)] as Component[],
				[
					...mixed.connections,
					pipe('M1', 'R3:port_1', 'PA:suction'),
					pipe('M2', 'PA:discharge', 'PB:suction'),
					pipe('M3', 'PB:discharge', 'R4:port_1')
				],
				mixed.pumpLibrary
			),
			[named('S1', 'Night', [status('A2', 'off')])]
		);
		expect(series().components.map((c) => c.id)).toEqual(['R1', 'PA', 'PB', 'R2']);
		const ws = setup(project);
		ws.setCase('S1');
		await openLineups(ws);
		const header = within(inGrid().getAllByRole('row')[0]!).getAllByRole('columnheader');
		expect(header.map((h) => h.textContent?.trim())).toEqual([
			'Case',
			'Pumps together, some in series, A1 to B2',
			'Pumps together, in series, PA and PB'
		]);
		expect(manager()).toHaveTextContent(
			'unmarked cells follow the base case. Pumps in series: one off stops the flow through their line (an off pump passes no flow).'
		);
		expect(inGrid().getByRole('rowheader', { name: /^Night S1 Shown/ })).toBeInTheDocument();
	});

	it('names each switch from its headers, never its state word; marks a case’s own value three ways', async () => {
		const ws = setup(withMore(named('S4', 'Same as base', [status('PA', 'on')])));
		await openLineups(ws);
		const switches = inGrid().getAllByRole('switch');
		for (const s of switches) {
			const labelledBy = s.getAttribute('aria-labelledby')!.split(' ');
			expect(labelledBy).toHaveLength(2);
			const [pumpHeader, caseHeader] = labelledBy.map((i) => document.getElementById(i)!) as [
				HTMLElement,
				HTMLElement
			];
			expect(pumpHeader.closest('[role="columnheader"]')).not.toBeNull();
			expect(caseHeader.closest('[role="rowheader"]')).not.toBeNull();
			const name = `${pumpHeader.textContent} ${caseHeader.textContent}`;
			expect(s).toHaveAccessibleName(name);
			// The state word is the switch's value: never in its name.
			expect(name.split(/[\s,;()]+/)).not.toContain(s.textContent!.trim());
		}
		// A standby turned on: On, marked, described and titled with the base value.
		const pb = cell('Pump PB', 'PB in service, PA off');
		expect(pb).toHaveAttribute('aria-checked', 'true');
		expect(pb).toHaveTextContent('On');
		expect(pb).toHaveAccessibleDescription('Changed in this scenario. Base value Off.');
		expect(pb).toHaveAttribute('title', 'Changed in this scenario. Base value Off.');
		expect(pb).toHaveClass('ring-2');
		// The description is the cell's sr-only span (a title reaches only the mouse, §8.5).
		const [pbText, ...pbMore] = describers(pb);
		expect(pbMore).toEqual([]);
		expect(pbText).toHaveClass('sr-only');
		expect(pbText!.textContent).toBe('Changed in this scenario. Base value Off.');
		expect(pbText!.closest('[role="gridcell"]')).toBe(pb.closest('[role="gridcell"]'));
		const pa = cell('Pump PA', 'PB in service, PA off');
		expect(pa).toHaveAttribute('aria-checked', 'false');
		expect(pa).toHaveTextContent('Off');
		expect(pa).toHaveAccessibleDescription('Changed in this scenario. Base value On.');
		expect(describers(pa).map((d) => d.textContent)).toEqual([
			'Changed in this scenario. Base value On.'
		]);
		// A cell that follows the base case: no mark, no description, no title.
		const p9 = cell('Pump P9', 'PB in service, PA off');
		expect(p9).toHaveAttribute('aria-checked', 'true');
		expect(p9).not.toHaveAttribute('aria-describedby');
		expect(p9).not.toHaveAttribute('title');
		expect(p9).not.toHaveClass('ring-2');
		// A change equal to the base value is still the case's own (as Build's Changed is).
		const same = cell('Pump PA', 'Same as base');
		expect(same).toHaveAttribute('aria-checked', 'true');
		expect(same).toHaveAccessibleDescription('Changed in this scenario. Base value On.');
		expect(describers(same).map((d) => d.textContent)).toEqual([
			'Changed in this scenario. Base value On.'
		]);
		expect(inGrid().getByRole('rowheader', { name: /^Same as base S4/ })).toHaveTextContent(
			'Same case as the base case'
		);
	});
});

describe('the keys (§8.7)', () => {
	it('arrows with no wrap, Home and End, Ctrl+Home and Ctrl+End; one Tab stop; Space presses', async () => {
		const ws = setup(twoSystems());
		await openLineups(ws);
		// One Tab stop, on the first scenario's first pump; Tab then leaves the grid.
		expect(tabStops()).toEqual([cell('Pump PA', 'PB in service, PA off')]);
		tabStops()[0]!.focus();
		const at = (r: number, c: number) =>
			document.activeElement?.getAttribute('data-cell') === `${r},${c}`;
		expect(at(1, 0)).toBe(true);
		await key({ key: 'ArrowRight' });
		expect(document.activeElement).toBe(cell('Pump PB', 'PB in service, PA off'));
		await key({ key: 'ArrowDown' });
		expect(document.activeElement).toBe(
			cell('Pump PB', '2 of 2 running; 2 of 3 running (Pump P3 off)')
		);
		await key({ key: 'End' });
		expect(document.activeElement).toBe(
			cell('Pump P9', '2 of 2 running; 2 of 3 running (Pump P3 off)')
		);
		// At an edge: nothing, and the key is not prevented (the box can still scroll).
		expect(await key({ key: 'ArrowRight' })).toBe(true);
		expect(at(2, 5)).toBe(true);
		await key({ key: 'Home' });
		expect(at(2, 0)).toBe(true);
		expect(await key({ key: 'ArrowLeft' })).toBe(true);
		expect(at(2, 0)).toBe(true);
		// Up into the base row: its cells are focusable, read-only gridcells.
		await key({ key: 'ArrowUp' });
		await key({ key: 'ArrowUp' });
		expect(at(0, 0)).toBe(true);
		expect(document.activeElement).toHaveAttribute('role', 'gridcell');
		expect(document.activeElement).toHaveAttribute('aria-readonly', 'true');
		expect(await key({ key: 'ArrowUp' })).toBe(true);
		expect(at(0, 0)).toBe(true);
		// Space on a base cell presses nothing.
		const before = canonicalJson(ws.store.project);
		await key({ key: ' ' });
		expect(canonicalJson(ws.store.project)).toBe(before);
		await key({ key: 'End', ctrlKey: true });
		expect(document.activeElement).toBe(cell('Pump P9', 'Aged pipe'));
		await key({ key: 'Home', ctrlKey: true });
		expect(at(0, 0)).toBe(true);
		await key({ key: 'ArrowDown' });
		await key({ key: 'ArrowDown' });
		await key({ key: 'ArrowDown' });
		expect(await key({ key: 'ArrowDown' })).toBe(true);
		expect(document.activeElement).toBe(cell('Pump PA', 'Aged pipe'));
		// The Tab stop is the cell last moved to, and only it.
		expect(tabStops()).toEqual([document.activeElement]);
		// Space on a switch is left to the button (not prevented): its activation presses it.
		const sw = document.activeElement as HTMLElement;
		expect(await key({ key: ' ' })).toBe(true);
		await press(sw);
		expect(scenariosOf(ws.store.project)[2]!.overrides).toContainEqual(status('PA', 'off'));
		expect(cell('Pump PA', 'Aged pipe')).toHaveAttribute('aria-checked', 'false');
	});
});

// ---------------------------------------------------------------------------------------------
// The focus (§8.7, §8.9)
// ---------------------------------------------------------------------------------------------

describe('the focus', () => {
	it('stays on the active cell through a press, a rename, an undo and a redo', async () => {
		const ws = setup(withMore(named('S4', 'Scenario 4')));
		await openLineups(ws);
		await press(cell('Pump P3', 'Scenario 4'));
		// The name followed its pumps: the switch is named by the row's new name.
		const renamed = ws.caseName('S4');
		expect(renamed).toBe(lineupName(ws.store.project, ws.scenarios[3]!));
		expect(renamed).not.toBe('Scenario 4');
		expect(document.activeElement).toBe(cell('Pump P3', renamed));
		expect(statusLine()).toHaveTextContent(
			`«Scenario 4» is now «${renamed}»: a name the app made follows its pumps until you rename it.`
		);
		expect(ws.store.undoLabel).toBe(`turn Pump P3 off in ${renamed}`);
		await key({ key: 'z', ctrlKey: true });
		expect(ws.caseName('S4')).toBe('Scenario 4');
		expect(document.activeElement).toBe(cell('Pump P3', 'Scenario 4'));
		expect(statusLine()).toHaveTextContent(`Undid turn Pump P3 off in ${renamed}.`);
		await key({ key: 'z', ctrlKey: true, shiftKey: true });
		expect(ws.caseName('S4')).toBe(renamed);
		expect(document.activeElement).toBe(cell('Pump P3', renamed));
		expect(statusLine()).toHaveTextContent(`Redid turn Pump P3 off in ${renamed}.`);
		// Ctrl+Y redoes too; with nothing to redo it does nothing.
		await key({ key: 'z', ctrlKey: true });
		await key({ key: 'y', ctrlKey: true });
		expect(ws.caseName('S4')).toBe(renamed);
		expect(document.activeElement).toBe(cell('Pump P3', renamed));
		// A press without a rename (a name the user typed) says nothing: the switch announces its
		// state, and the line says no more what the last step did.
		await press(cell('Pump P9', 'Aged pipe'));
		expect(ws.caseName('S3')).toBe('Aged pipe');
		expect(statusLine().textContent).toBe('');
	});

	it('a click alone (no focus, as on Safari or a tablet) focuses the pressed cell, the one Tab stop, also after a rename', async () => {
		const ws = setup(withMore(named('S4', 'Scenario 4')));
		await openLineups(ws);
		// The focus elsewhere in the grid first: the cell last wanted is another one.
		const other = cell('Pump PA', 'PB in service, PA off');
		other.focus();
		await fireEvent.focusIn(other);
		// A name the user typed: the same row.
		await fireEvent.click(cell('Pump P9', 'Aged pipe'));
		await settle();
		expect(ws.scenarios[2]!.overrides).toContainEqual(status('P9', 'off'));
		expect(document.activeElement).toBe(cell('Pump P9', 'Aged pipe'));
		expect(tabStops()).toEqual([cell('Pump P9', 'Aged pipe')]);
		// An app-made name: the row is renamed, the focus is on the cell under its new name.
		(document.activeElement as HTMLElement).blur();
		expect(document.activeElement).toBe(document.body);
		await fireEvent.click(cell('Pump P3', 'Scenario 4'));
		await settle();
		const renamed = ws.caseName('S4');
		expect(renamed).not.toBe('Scenario 4');
		expect(document.activeElement).toBe(cell('Pump P3', renamed));
		expect(tabStops()).toEqual([cell('Pump P3', renamed)]);
	});

	it('the Tab stop never vanishes with the focus outside the grid: the footer’s Undo of New lineup', async () => {
		const ws = setup(twoSystems());
		await openLineups(ws);
		await fireEvent.click(inManager().getByRole('button', { name: 'New lineup' }));
		await settle();
		expect(document.activeElement).toBe(cell('Pump PA', 'Scenario 4'));
		const undo = inManager().getByRole('button', { name: 'Undo add scenario' });
		await press(undo);
		expect(ws.scenarios.map((s) => s.id)).toEqual(['S1', 'S2', 'S3']);
		// The focus stays on Undo (§8.9); the derived stop is on the nearest remaining row.
		expect(document.activeElement).toBe(undo);
		expect(tabStops()).toEqual([cell('Pump PA', 'Aged pipe')]);
	});

	it('the Tab stop never vanishes: an undone New lineup moves it to the nearest remaining row', async () => {
		const ws = setup(twoSystems());
		await openLineups(ws);
		await fireEvent.click(inManager().getByRole('button', { name: 'New lineup' }));
		await settle();
		expect(document.activeElement).toBe(cell('Pump PA', 'Scenario 4'));
		await key({ key: 'End' });
		expect(document.activeElement).toBe(cell('Pump P9', 'Scenario 4'));
		await key({ key: 'z', ctrlKey: true });
		expect(ws.scenarios.map((s) => s.id)).toEqual(['S1', 'S2', 'S3']);
		// The nearest remaining row (the previous: there is no next), the same column.
		expect(tabStops()).toEqual([cell('Pump P9', 'Aged pipe')]);
		expect(document.activeElement).toBe(cell('Pump P9', 'Aged pipe'));
	});

	it('the Tab stop never vanishes: an undo that removes its pump moves it to the first column', async () => {
		const ws = setup(twoSystems());
		// A pump of its own, added in one step (no connection: Other pumps).
		expect(
			ws.updateStored((draft) => {
				draft.components.push(pump('PX', 'Spare'));
			}, 'add pump')
		).toBe(true);
		await openLineups(ws);
		const spare = cell('Spare', 'Aged pipe');
		spare.focus();
		await fireEvent.focusIn(spare);
		expect(tabStops()).toEqual([spare]);
		await key({ key: 'z', ctrlKey: true });
		expect(ws.store.project.components.some((c) => c.id === 'PX')).toBe(false);
		expect(inGrid().queryByRole('columnheader', { name: /Spare/ })).toBeNull();
		expect(tabStops()).toEqual([cell('Pump PA', 'Aged pipe')]);
		expect(document.activeElement).toBe(cell('Pump PA', 'Aged pipe'));
		expect(statusLine()).toHaveTextContent('Undid add pump.');
	});

	it('the Tab stop never vanishes: an undo to one pump takes the tabs away, Cases shows, the focus on the title', async () => {
		const ws = setup(pumpTransferExample());
		expect(
			ws.updateStored((draft) => {
				draft.components.push(pump('PX', 'Spare'));
			}, 'add pump')
		).toBe(true);
		await openLineups(ws);
		const first = tabStops()[0]!;
		first.focus();
		await key({ key: 'z', ctrlKey: true });
		expect(inManager().queryByRole('tablist')).toBeNull();
		expect(inManager().queryByRole('grid')).toBeNull();
		expect(inManager().getByRole('heading', { name: 'Cases (1)' })).toHaveClass('section-title');
		const title = inManager().getByRole('heading', { name: 'Scenarios', level: 2 });
		expect(document.activeElement).toBe(title);
		expect(statusLine()).toHaveTextContent('Undid add pump.');
		// Focusable while it holds the focus only: out of the Tab order again once it leaves.
		inManager().getByRole('button', { name: 'Close' }).focus();
		expect(title).not.toHaveAttribute('tabindex');
		// The tab last used is kept: back with two pumps, Pump lineups shows again.
		await fireEvent.click(inManager().getByRole('button', { name: 'Done' }));
		ws.redo();
		ws.openManager();
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(tab('Pump lineups')).toHaveAttribute('aria-selected', 'true');
	});

	it('Cases shown: an undo or redo across two pumps keeps the focus where it was; on the title when its tab goes', async () => {
		const ws = setup(pumpTransferExample());
		expect(
			ws.updateStored((draft) => {
				draft.components.push(pump('PX', 'Spare'));
			}, 'add pump')
		).toBe(true);
		ws.openManager();
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(tab('Cases (1)')).toHaveAttribute('aria-selected', 'true');
		const show = inManager().getByRole('button', { name: 'Show the base case' });
		show.focus();
		// Undo to one pump: the tab row goes; the Cases view stays, and the focus on its button.
		await key({ key: 'z', ctrlKey: true });
		expect(inManager().queryByRole('tablist')).toBeNull();
		expect(statusLine()).toHaveTextContent('Undid add pump.');
		expect(show.isConnected).toBe(true);
		expect(document.activeElement).toBe(show);
		// Redo back to two pumps: the tab row comes back, the focus still there.
		await key({ key: 'y', ctrlKey: true });
		expect(tab('Cases (1)')).toHaveAttribute('aria-selected', 'true');
		expect(statusLine()).toHaveTextContent('Redid add pump.');
		expect(document.activeElement).toBe(show);
		// From the Cases tab itself, which an undo takes away: the focus on the dialog's title.
		tab('Cases (1)').focus();
		await key({ key: 'z', ctrlKey: true });
		expect(inManager().queryByRole('tablist')).toBeNull();
		expect(document.activeElement).toBe(
			inManager().getByRole('heading', { name: 'Scenarios', level: 2 })
		);
	});

	it('the footer’s Undo to one pump: the focus on the title too', async () => {
		const ws = setup(pumpTransferExample());
		ws.updateStored((draft) => {
			draft.components.push(pump('PX', 'Spare'));
		}, 'add pump');
		await openLineups(ws);
		const undo = inManager().getByRole('button', { name: 'Undo add pump' });
		await press(undo);
		expect(inManager().queryByRole('tablist')).toBeNull();
		expect(document.activeElement).toBe(
			inManager().getByRole('heading', { name: 'Scenarios', level: 2 })
		);
	});
});

// ---------------------------------------------------------------------------------------------
// New lineup (§8.8), Undo and Redo (§8.9)
// ---------------------------------------------------------------------------------------------

describe('New lineup', () => {
	it('adds “Scenario n” at the end in one step, the case shown unchanged, the focus on its first switch', async () => {
		const ws = setup(twoSystems());
		ws.setCase('S2');
		await openLineups(ws);
		await fireEvent.click(inManager().getByRole('button', { name: 'New lineup' }));
		await settle();
		expect(ws.scenarios.at(-1)).toEqual({ id: 'S4', name: 'Scenario 4', overrides: [] });
		expect(ws.store.undoLabel).toBe('add scenario');
		expect(ws.store.activeCase).toBe('S2');
		expect(statusLine()).toHaveTextContent('Added «Scenario 4», its pumps as in the base case.');
		expect(document.activeElement).toBe(cell('Pump PA', 'Scenario 4'));
		expect(inGrid().getByRole('rowheader', { name: /^Scenario 4 S4/ })).toHaveTextContent(
			'Same case as the base case'
		);
		expect(tab('Cases (5)')).toBeInTheDocument();
		// Its first press names it (§4.5).
		await press(cell('Pump PB', 'Scenario 4'));
		expect(ws.caseName('S4')).toBe(lineupName(ws.store.project, ws.scenarios[3]!));
		expect(document.activeElement).toBe(cell('Pump PB', ws.caseName('S4')));
	});

	it('at 20 scenarios: aria-disabled, titled and described by the limit; a press does nothing', async () => {
		const many = Array.from({ length: MAX_SCENARIOS - 3 }, (_, i) =>
			named(`S${i + 4}`, `Case ${i + 4}`)
		);
		const ws = setup(withMore(...many));
		await openLineups(ws);
		const button = inManager().getByRole('button', { name: 'New lineup' });
		expect(button).toHaveAttribute('aria-disabled', 'true');
		expect(button).toHaveAttribute('title', 'A project holds at most 20 scenarios.');
		expect(button).toHaveAccessibleDescription('A project holds at most 20 scenarios.');
		// Described by an sr-only span with the same words (a title reaches only the mouse, §8.2).
		const [limit, ...more] = describers(button);
		expect(more).toEqual([]);
		expect(limit).toHaveClass('sr-only');
		expect(limit!.textContent).toBe('A project holds at most 20 scenarios.');
		await press(button);
		expect(ws.scenarios).toHaveLength(MAX_SCENARIOS);
		expect(statusLine().textContent).toBe('');
		// The Cases tab's New scenario and Duplicate: the same description, by aria-describedby.
		await fireEvent.click(tab('Cases (21)'));
		for (const name of ['New scenario', 'Duplicate Case 4']) {
			const b = inManager().getByRole('button', { name });
			expect(b).toHaveAttribute('aria-disabled', 'true');
			expect(b).toHaveAccessibleDescription('A project holds at most 20 scenarios.');
			expect(describers(b).map((d) => d.textContent)).toEqual([
				'A project holds at most 20 scenarios.'
			]);
		}
	});
});

describe('Undo and Redo in the panel', () => {
	it('are named by the step, say what they did, and Ctrl+Z and Ctrl+Shift+Z from a switch say the same', async () => {
		const ws = setup(twoSystems());
		await openLineups(ws);
		const undo = () => inManager().getByRole('button', { name: /^Undo/ });
		const redo = () => inManager().getByRole('button', { name: /^Redo/ });
		expect(undo()).toHaveAccessibleName('Undo');
		expect(undo()).toHaveAttribute('aria-disabled', 'true');
		expect(redo()).toHaveAccessibleName('Redo');
		expect(redo()).toHaveAttribute('aria-disabled', 'true');
		await press(cell('Pump P9', 'Aged pipe'));
		const label = 'turn Pump P9 off in Aged pipe';
		expect(undo()).toHaveAccessibleName(`Undo ${label}`);
		expect(undo()).not.toHaveAttribute('aria-disabled', 'true');
		expect(undo()).toHaveTextContent(/^Undo$/);
		await press(undo());
		expect(statusLine()).toHaveTextContent(`Undid ${label}.`);
		expect(document.activeElement).toBe(undo());
		expect(redo()).toHaveAccessibleName(`Redo ${label}`);
		await press(redo());
		expect(statusLine()).toHaveTextContent(`Redid ${label}.`);
		// From a focused switch: the same words, the focus kept.
		cell('Pump P9', 'Aged pipe').focus();
		await key({ key: 'z', ctrlKey: true });
		expect(statusLine()).toHaveTextContent(`Undid ${label}.`);
		expect(document.activeElement).toBe(cell('Pump P9', 'Aged pipe'));
		await key({ key: 'Z', ctrlKey: true, shiftKey: true });
		expect(statusLine()).toHaveTextContent(`Redid ${label}.`);
		expect(document.activeElement).toBe(cell('Pump P9', 'Aged pipe'));
		// ⌘ too.
		await key({ key: 'z', metaKey: true });
		expect(statusLine()).toHaveTextContent(`Undid ${label}.`);
		expect(ws.store.canUndo).toBe(false);
		// One step per key: with two steps, Ctrl+Z undoes one (the window's shortcut does not
		// undo a second time), Ctrl+Shift+Z redoes one.
		await press(cell('Pump P9', 'Aged pipe'));
		await press(cell('Pump P1', 'Aged pipe'));
		await key({ key: 'z', ctrlKey: true });
		expect(statusLine()).toHaveTextContent('Undid turn Pump P1 off in Aged pipe.');
		expect(ws.store.undoLabel).toBe(label);
		await key({ key: 'z', ctrlKey: true });
		await key({ key: 'z', ctrlKey: true, shiftKey: true });
		expect(ws.store.undoLabel).toBe(label);
		expect(ws.store.redoLabel).toBe('turn Pump P1 off in Aged pipe');
	});

	it('says the case shown when the step was made in another case', async () => {
		const ws = setup(twoSystems());
		ws.setCase('S1');
		ws.editComponent('P9', 'change pump status', (c) => {
			(c as Component & { status: string }).status = 'off';
		});
		ws.setCase(null);
		await openLineups(ws);
		await press(inManager().getByRole('button', { name: /^Undo/ }));
		expect(statusLine()).toHaveTextContent(
			'Undid change pump status in PB in service, PA off. Now showing scenario PB in service, PA off.'
		);
		expect(ws.store.activeCase).toBe('S1');
	});

	it('leaves Ctrl+Z to a text field', async () => {
		const ws = setup(twoSystems());
		ws.updateStored((draft) => {
			draft.metadata.name = 'Plant';
		}, 'rename project');
		ws.openManager({ focus: 'S1' });
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		const input = inManager().getByRole('textbox', { name: 'Name of scenario S1' });
		input.focus();
		expect(await fireEvent.keyDown(input, { key: 'z', ctrlKey: true })).toBe(true);
		expect(ws.store.undoLabel).toBe('rename project');
		expect(ws.project.metadata.name).toBe('Plant');
		expect(statusLine().textContent).toBe('');
	});
});

// ---------------------------------------------------------------------------------------------
// The manager's lines in the Cases tab; Delete's focus (§8.1)
// ---------------------------------------------------------------------------------------------

describe('the manager’s status line in the Cases tab', () => {
	it('says the rename a Remove of a status change makes', async () => {
		const ws = setup(withMore(named('S4', '2 of 3 running (Pump P3 off)', [status('P3', 'off')])));
		expect(lineupName(ws.store.project, ws.scenarios[3]!)).toBe('2 of 3 running (Pump P3 off)');
		ws.openManager({ focus: 'S4' });
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		// S2 changes P3 too: S4's card's Remove (the card asked for is open).
		const remove = inManager()
			.getAllByRole('button', { name: 'Remove the change of Pump P3 · Status' })
			.find((b) => b.closest('details')?.querySelector('summary')?.textContent?.includes('S4'))!;
		await fireEvent.click(remove);
		expect(ws.caseName('S4')).toBe('Scenario 4');
		expect(statusLine()).toHaveTextContent(
			'«2 of 3 running (Pump P3 off)» is now «Scenario 4»: a name the app made follows its pumps until you rename it.'
		);
		// Said in the manager, not behind it.
		expect(ws.notice).toBeNull();
		expect(ws.store.undoLabel).toBe('remove a change in Scenario 4');
	});

	it('gives the count form for three renames', async () => {
		const ws = setup(twoSystems());
		const real = ws.updateStoredQuiet.bind(ws);
		const three = [
			{ from: 'A', to: 'B' },
			{ from: 'C', to: 'D' },
			{ from: 'E', to: 'F' }
		];
		// No action of the manager renames three cases at once (a step renames the case it changes);
		// the words are the step's, as updateStoredQuiet gives them.
		vi.spyOn(ws, 'updateStoredQuiet').mockImplementation((change, label) => {
			const result = real(change, label);
			return result.ok ? { ...result, renamed: renameNotice(three) } : result;
		});
		ws.openManager();
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		await fireEvent.click(inManager().getByRole('button', { name: 'Move Aged pipe up' }));
		expect(statusLine()).toHaveTextContent(
			'Renamed 3 scenarios to match their pumps, for example «A» is now «B». A name the app made follows its pumps until you rename it.'
		);
	});

	it('Delete with the tab row: the focus on the Cases tab', async () => {
		const ws = setup(twoSystems());
		ws.openManager({ focus: 'S3' });
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		await fireEvent.click(inManager().getByRole('button', { name: 'Delete Aged pipe' }));
		const confirm = await screen.findByRole('dialog', { name: 'Delete scenario «Aged pipe»?' });
		await fireEvent.click(within(confirm).getByRole('button', { name: 'Delete' }));
		await settle();
		expect(ws.scenarios.map((s) => s.id)).toEqual(['S1', 'S2']);
		expect(document.activeElement).toBe(tab('Cases (3)'));
	});
});

// ---------------------------------------------------------------------------------------------
// The filter (§8.1, §8.2) and the alert line (§8.6)
// ---------------------------------------------------------------------------------------------

describe('the filter from the card', () => {
	it('shows the card’s pumps only; Show every pump shows them all, the focus on the active cell', async () => {
		const ws = setup(twoSystems());
		ws.openManager({ pumps: ['PA', 'PB'] });
		await tick();
		await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(tab('Pump lineups')).toHaveAttribute('aria-selected', 'true');
		const pumpHeaders = () =>
			within(inGrid().getAllByRole('row')[0]!)
				.getAllByRole('columnheader')
				.slice(1)
				.map((h) => h.textContent?.replace(/\s+/g, ' ').trim());
		expect(pumpHeaders()).toEqual(['Pump PA PA', 'Pump PB PB']);
		// One group shown: no group header row.
		expect(inGrid().getAllByRole('row')).toHaveLength(1 + 4);
		expect(manager()).toHaveTextContent(
			'Only the pumps on the Pumps together card are shown: Pump PA and Pump PB. Show every pump'
		);
		const stop = tabStops()[0]!;
		stop.focus();
		await key({ key: 'ArrowRight' });
		expect(document.activeElement).toBe(cell('Pump PB', 'PB in service, PA off'));
		await press(inManager().getByRole('button', { name: 'Show every pump' }));
		expect(ws.managerPumps).toBeNull();
		expect(inGrid().getAllByRole('row')).toHaveLength(2 + 4);
		expect(manager()).not.toHaveTextContent('Only the pumps');
		expect(document.activeElement).toBe(cell('Pump PB', 'PB in service, PA off'));
		// Closing the manager forgets the filter.
		ws.managerPumps = ['P1'];
		await fireEvent.click(inManager().getByRole('button', { name: 'Done' }));
		expect(ws.managerPumps).toBeNull();
	});
});

describe('the alert line', () => {
	it('says a refusal at 30 changes, and nothing changes', async () => {
		const project = station(15);
		const lengths: Override[] = project.connections.map((c) => ({
			kind: 'pipe',
			connectionId: c.id,
			pipeIndex: 0,
			field: 'length',
			value: 25
		}));
		expect(lengths).toHaveLength(MAX_CHANGES);
		const ws = setup(withScenarios(project, [named('S1', 'Full', lengths)]));
		await openLineups(ws);
		const before = canonicalJson(ws.store.project);
		await press(cell('Pump P1', 'Full'));
		expect(alertLine()).toHaveTextContent(
			'Could not turn Pump P1 off in Full: A scenario holds at most 30 changes.'
		);
		expect(canonicalJson(ws.store.project)).toBe(before);
		expect(ws.notice).toBeNull();
		expect(document.activeElement).toBe(cell('Pump P1', 'Full'));
		expect(cell('Pump P1', 'Full')).toHaveAttribute('aria-checked', 'true');
		// The next action clears it.
		await press(inManager().getByRole('button', { name: 'New lineup' }));
		expect(alertLine().textContent).toBe('');
	});

	it('a refusal clears the status line: it no longer says what an earlier step did', async () => {
		const project = station(15);
		const lengths: Override[] = project.connections.map((c) => ({
			kind: 'pipe',
			connectionId: c.id,
			pipeIndex: 0,
			field: 'length',
			value: 25
		}));
		const ws = setup(
			withScenarios(project, [named('S1', 'Full', lengths), named('S2', 'Scenario 2')])
		);
		await openLineups(ws);
		// A press that renames: the status line says so.
		await press(cell('Pump P2', 'Scenario 2'));
		expect(ws.caseName('S2')).not.toBe('Scenario 2');
		expect(statusLine()).toHaveTextContent(/^«Scenario 2» is now «/);
		await press(cell('Pump P1', 'Full'));
		expect(alertLine()).toHaveTextContent(
			'Could not turn Pump P1 off in Full: A scenario holds at most 30 changes.'
		);
		expect(statusLine().textContent).toBe('');
	});

	it('says a message again when it is the same words (two undos, two refusals)', async () => {
		const ws = setup(twoSystems());
		await openLineups(ws);
		const lines = mutations(statusLine());
		for (let i = 0; i < 2; i++) {
			await fireEvent.click(inManager().getByRole('button', { name: 'New lineup' }));
			await settle();
		}
		expect(ws.scenarios).toHaveLength(5);
		await key({ key: 'z', ctrlKey: true });
		expect(statusLine()).toHaveTextContent('Undid add scenario.');
		const first = lines.count();
		await key({ key: 'z', ctrlKey: true });
		expect(ws.scenarios).toHaveLength(3);
		expect(statusLine()).toHaveTextContent('Undid add scenario.');
		// The line changed again, so a screen reader says the second undo too.
		expect(lines.count()).toBeGreaterThan(first);
		lines.stop();
		document.body.innerHTML = '';

		const project = station(15);
		const lengths: Override[] = project.connections.map((c) => ({
			kind: 'pipe',
			connectionId: c.id,
			pipeIndex: 0,
			field: 'length',
			value: 25
		}));
		const full = setup(withScenarios(project, [named('S1', 'Full', lengths)]));
		await openLineups(full);
		const alerts = mutations(alertLine());
		const words = 'Could not turn Pump P1 off in Full: A scenario holds at most 30 changes.';
		await press(cell('Pump P1', 'Full'));
		expect(alertLine()).toHaveTextContent(words);
		const once = alerts.count();
		await press(cell('Pump P1', 'Full'));
		expect(alertLine()).toHaveTextContent(words);
		expect(alerts.count()).toBeGreaterThan(once);
		alerts.stop();
	});
});

// ---------------------------------------------------------------------------------------------
// The phone (§8.10)
// ---------------------------------------------------------------------------------------------

describe('on a phone', () => {
	function phone() {
		vi.stubGlobal('matchMedia', (query: string) => ({
			matches: query === '(max-width: 639px)',
			media: query,
			onchange: null,
			addEventListener() {},
			removeEventListener() {},
			addListener() {},
			removeListener() {},
			dispatchEvent: () => false
		}));
	}
	const picker = () =>
		inManager().getByRole('combobox', { name: 'Case to edit' }) as HTMLSelectElement;
	/** The picked case's line and notes, one per paragraph. */
	const pickedLines = () =>
		[...manager().querySelectorAll('[data-picked-line] p')].map((p) => p.textContent);

	it('picks a case: the default, the options, the line; one layout only', async () => {
		phone();
		const ws = setup(twoSystems());
		await openLineups(ws);
		expect(inManager().queryByRole('grid')).toBeNull();
		expect(manager()).toHaveTextContent(
			'Pick a case, then turn its pumps on or off: the same change as in Build, one undo step each; in a name, running means switched on. The base case is changed in Build.'
		);
		expect([...picker().options].map((o) => o.text)).toEqual([
			'Base case',
			'PB in service, PA off (2 changes)',
			'2 of 2 running; 2 of 3 running (Pump P3 off) (2 changes)',
			'Aged pipe (2 changes)'
		]);
		// The base case is shown: the default is the first scenario.
		expect(picker().value).toBe('S1');
		expect(pickedLines()).toEqual([
			'Changes go to «PB in service, PA off» only: 2 of at most 30 changes.'
		]);
		// The groups as fieldsets with their headers.
		const groups = inManager().getAllByRole('group');
		expect(groups.map((g) => g.querySelector('legend')?.textContent)).toEqual(
			expect.arrayContaining([
				'Pumps together, PA and PB',
				'Pumps together, P1 to P3',
				'Other pumps'
			])
		);
		// The case shown is the default when it is a scenario.
		document.body.innerHTML = '';
		const shown = setup(twoSystems());
		shown.setCase('S3');
		await openLineups(shown);
		expect(picker().value).toBe('S3');
		expect(pickedLines()).toEqual([
			'Changes go to «Aged pipe» only: 2 of at most 30 changes.',
			'1 other change'
		]);
	});

	it('segments with Changed · Base · Reset; Reset follows the name rule', async () => {
		phone();
		const app = '2 of 3 running (Pump P3 off)';
		const ws = setup(withMore(named('S4', app, [status('P3', 'off')])));
		expect(lineupName(ws.store.project, ws.scenarios[3]!)).toBe(app);
		await openLineups(ws);
		await fireEvent.change(picker(), { target: { value: 'S1' } });
		const pb = inManager().getByRole('radiogroup', { name: 'Pump PB' });
		expect(within(pb).getByRole('radio', { name: 'On' })).toBeChecked();
		expect(pb).toHaveAccessibleDescription(/^Changed in this scenario\. Base value Off\./);
		const pbField = pb.closest('.field') as HTMLElement;
		expect(pbField).toHaveTextContent('Changed Base: Off Reset');
		// A pump that follows the base case: no note.
		expect(
			inManager().getByRole('radiogroup', { name: 'Pump P9' }).closest('.field')
		).not.toHaveTextContent('Changed');
		// A segment pressed: Build's edit through editScenario.
		await fireEvent.click(
			within(inManager().getByRole('radiogroup', { name: 'Pump P9' })).getByRole('radio', {
				name: 'Off'
			})
		);
		expect(ws.scenarios[0]!.overrides).toContainEqual(status('P9', 'off'));
		expect(ws.store.undoLabel).toBe('turn Pump P9 off in PB in service, PA off');
		// Reset, in a case whose name the app made: back to the base value, the name follows.
		await fireEvent.change(picker(), { target: { value: 'S4' } });
		await fireEvent.click(
			inManager().getByRole('button', { name: 'Reset Pump P3 to the base value, On' })
		);
		await settle();
		expect(ws.scenarios[3]).toEqual({ id: 'S4', name: 'Scenario 4', overrides: [] });
		expect(statusLine()).toHaveTextContent(
			`«${app}» is now «Scenario 4»: a name the app made follows its pumps until you rename it.`
		);
		expect(picker().value).toBe('S4');
		expect(document.activeElement).toBe(
			within(inManager().getByRole('radiogroup', { name: 'Pump P3' })).getByRole('radio', {
				name: 'On'
			})
		);
	});

	it('Reset of a change equal to the base value removes it in one step, as Build’s Reset does', async () => {
		phone();
		const ws = setup(twoSystems());
		// Build, in the base case: the standby PB turned on. S1 keeps its own "PB on", now equal
		// to the base value (still the case's own, §8.5).
		expect(
			ws.editComponent('PB', 'change pump status', (c) => {
				(c as Component & { status: string }).status = 'on';
			})
		).toBe(true);
		ws.dismissNotice();
		expect(ws.scenarios[0]!.overrides).toEqual([status('PB', 'on'), status('PA', 'off')]);
		// Build's Reset of that change in S1, in a second workspace: the project it leaves.
		const build = testWorkspace(JSON.parse(canonicalJson(ws.store.project)) as Project, {
			now: NOW
		});
		build.setCase('S1');
		build.componentChange('PB', 'status').reset();
		expect(build.scenarios[0]!.overrides).toEqual([status('PA', 'off')]);

		await openLineups(ws);
		await fireEvent.change(picker(), { target: { value: 'S1' } });
		const field = () =>
			inManager().getByRole('radiogroup', { name: 'Pump PB' }).closest('.field') as HTMLElement;
		expect(field()).toHaveTextContent('Changed Base: On Reset');
		const depth = ws.store.undoDepth;
		await fireEvent.click(
			inManager().getByRole('button', { name: 'Reset Pump PB to the base value, On' })
		);
		await settle();
		expect(ws.scenarios[0]!.overrides).toEqual([status('PA', 'off')]);
		expect(ws.store.undoDepth).toBe(depth + 1);
		expect(canonicalJson(ws.store.project)).toBe(canonicalJson(build.store.project));
		// The mark and Reset are gone; the name the user typed stays, so nothing is said.
		expect(field()).not.toHaveTextContent('Changed');
		expect(inManager().queryByRole('button', { name: /^Reset Pump PB/ })).toBeNull();
		expect(ws.caseName('S1')).toBe('PB in service, PA off');
		expect(statusLine().textContent).toBe('');
		expect(document.activeElement).toBe(
			within(inManager().getByRole('radiogroup', { name: 'Pump PB' })).getByRole('radio', {
				name: 'On'
			})
		);
		// One undo step, named by the field it resets, as Build's is.
		expect(ws.store.undoLabel).toBe('reset Pump PB in PB in service, PA off');
		await press(inManager().getByRole('button', { name: /^Undo/ }));
		expect(ws.scenarios[0]!.overrides).toEqual([status('PB', 'on'), status('PA', 'off')]);
		expect(statusLine()).toHaveTextContent('Undid reset Pump PB in PB in service, PA off.');
	});

	it('the base case: a read-only list', async () => {
		phone();
		const ws = setup(twoSystems());
		await openLineups(ws);
		await fireEvent.change(picker(), { target: { value: '' } });
		expect(pickedLines()).toEqual(["The base case's pumps: change them in Build."]);
		expect(inManager().queryByRole('radiogroup')).toBeNull();
		const items = [...manager().querySelectorAll('dl > div')].map((d) =>
			d.textContent?.replace(/\s+/g, ' ').trim()
		);
		expect(items).toEqual([
			'Pump PA: On',
			'Pump PB: Off',
			'Pump P1: On',
			'Pump P2: On',
			'Pump P3: On',
			'Pump P9: On'
		]);
	});

	it('New lineup picks the new case and focuses the picker; an Undo falls back to the default', async () => {
		phone();
		const ws = setup(twoSystems());
		await openLineups(ws);
		await fireEvent.click(inManager().getByRole('button', { name: 'New lineup' }));
		await settle();
		expect(picker().value).toBe('S4');
		expect(document.activeElement).toBe(picker());
		expect(pickedLines()).toEqual([
			'Changes go to «Scenario 4» only: 0 of at most 30 changes.',
			'Same case as the base case'
		]);
		expect(statusLine()).toHaveTextContent('Added «Scenario 4», its pumps as in the base case.');
		await press(inManager().getByRole('button', { name: /^Undo/ }));
		expect(ws.scenarios.map((s) => s.id)).toEqual(['S1', 'S2', 'S3']);
		expect(picker().value).toBe('S1');
		expect(statusLine()).toHaveTextContent('Undid add scenario.');
	});
});
