/**
 * The scenario manager in the workspace (proposal scenario-manager.md §6): the case bar and the
 * Scenarios button; the manager's actions; fields in a scenario (its values editable and marked
 * Changed with Reset, everything else locked, read-only and focusable; every allow-listed value of
 * every component type editable); the Build banner and hidden topology actions; the results'
 * scenario card, the trace's "Changed by this scenario"; Compare cases; and a project without
 * scenarios looks as it did. Values typed here and the solved states are made-up test inputs.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Override, Project, ScenarioResult, SolveResponse } from '$lib/api/types';
import { enteredFor } from '$lib/testing/helpers';
import { pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent } from '$lib/utils/factory';
import { OVERRIDE_FIELDS } from '$lib/utils/model-rules';
import { withScenarios } from '$lib/utils/scenarios';
import WorkspaceView from './Workspace.svelte';

function project(overrides: Override[] = [], base: Project = pumpTransferExample()): Project {
	return withScenarios(base, [{ id: 'S1', name: 'Winter', overrides }]);
}

function setup(p: Project = project(), options: Parameters<typeof testWorkspace>[1] = {}) {
	const ws = testWorkspace(p, options);
	render(WorkspaceView, { workspace: ws });
	return ws;
}

/** Type a value into a field and commit it (as leaving the field does). */
async function enter(input: HTMLElement, value: string) {
	await fireEvent.input(input, { target: { value } });
	await fireEvent.change(input);
}

describe('a project without scenarios', () => {
	it('has no case bar, no case tabs and a plain Solve; the Scenarios button opens the manager', async () => {
		setup(pumpTransferExample());
		expect(screen.queryByRole('group', { name: 'Case' })).toBeNull();
		expect(screen.queryByRole('tab', { name: 'Compare cases' })).toBeNull();
		expect(screen.getByRole('button', { name: 'Solve' })).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Scenarios' }));
		const manager = await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(within(manager).getByText('The network as built.')).toBeInTheDocument();
	});
});

describe('the scenario manager', () => {
	it('adds a scenario, shows it, and focuses its name with the text selected', async () => {
		const ws = setup(pumpTransferExample());
		await fireEvent.click(screen.getByRole('button', { name: 'Scenarios' }));
		const manager = await screen.findByRole('dialog', { name: 'Scenarios' });
		await fireEvent.click(within(manager).getByRole('button', { name: 'New scenario' }));
		await tick();
		await tick();
		const name = within(manager).getByRole('textbox', { name: 'Name of scenario S1' });
		expect(name).toHaveValue('Scenario 1');
		expect(document.activeElement).toBe(name);
		expect(ws.store.activeCase).toBe('S1');
		expect(ws.store.undoLabel).toBe('add scenario');
		expect(screen.getByRole('button', { name: 'Scenarios (1)' })).toBeInTheDocument();
		await enter(name, 'Winter');
		expect(ws.scenarios[0]!.name).toBe('Winter');
		expect(ws.store.undoLabel).toBe('rename scenario Scenario 1');
	});

	it('duplicates, moves and deletes, each one undo step; the last delete removes the key', async () => {
		const ws = setup(
			project([{ kind: 'component', componentId: 'P1', field: 'status', value: 'off' }])
		);
		ws.managerFocus = 'S1';
		ws.managerOpen = true;
		await tick();
		const manager = await screen.findByRole('dialog', { name: 'Scenarios' });
		await fireEvent.click(within(manager).getByRole('button', { name: 'Duplicate Winter' }));
		expect(ws.scenarios.map((s) => [s.id, s.name, s.overrides?.length])).toEqual([
			['S1', 'Winter', 1],
			['S2', 'Winter (copy)', 1]
		]);
		expect(ws.store.activeCase).toBe('S2');
		await fireEvent.click(within(manager).getByRole('button', { name: 'Move Winter (copy) up' }));
		expect(ws.scenarios.map((s) => s.id)).toEqual(['S2', 'S1']);
		await fireEvent.click(within(manager).getByRole('button', { name: 'Delete Winter (copy)' }));
		const confirm = await screen.findByRole('dialog', { name: 'Delete scenario «Winter (copy)»?' });
		expect(confirm).toHaveTextContent(
			'Its 1 change and its results are removed. You can undo this.'
		);
		await fireEvent.click(within(confirm).getByRole('button', { name: 'Delete' }));
		await tick();
		expect(ws.scenarios.map((s) => s.id)).toEqual(['S1']);
		expect(ws.store.activeCase).toBeNull();
		expect(document.activeElement).toHaveTextContent('Cases (2)');
		await fireEvent.click(within(manager).getByRole('button', { name: 'Delete Winter' }));
		await fireEvent.click(
			within(await screen.findByRole('dialog', { name: 'Delete scenario «Winter»?' })).getByRole(
				'button',
				{ name: 'Delete' }
			)
		);
		expect('scenarios' in ws.store.project).toBe(false);
		ws.undo();
		expect(ws.scenarios.map((s) => s.id)).toEqual(['S1']);
	});

	it('lists changes with base values, and the changes that no longer apply, which can be removed', async () => {
		const ws = setup(
			project([
				{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 },
				{ kind: 'component', componentId: 'P7', field: 'speed', value: 0.9 },
				{ kind: 'component', componentId: 'R1', field: 'status', value: 'off' }
			])
		);
		ws.managerFocus = 'S1';
		ws.managerOpen = true;
		const manager = await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(manager).toHaveTextContent('Discharge tank · Liquid level: 6 m');
		expect(manager).toHaveTextContent('Base: 2 m');
		expect(
			within(manager).getByRole('heading', { name: 'No longer applies (2)' })
		).toBeInTheDocument();
		expect(manager).toHaveTextContent('P7 (deleted) · Speed 90 %: no longer applies');
		expect(manager).toHaveTextContent('Suction tank (reservoir) has no status');
		await fireEvent.click(
			within(manager).getByRole('button', { name: 'Remove the 2 changes that no longer apply' })
		);
		expect(ws.scenarios[0]!.overrides).toEqual([
			{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 }
		]);
	});

	it('shows problems with a scenario’s values after a base edit', async () => {
		const base = pumpTransferExample();
		const pump = base.components[1]!;
		if (pump.type === 'pump') pump.control = { mode: 'flow', setpoint: 0.015, minSpeed: 0.85 };
		const ws = setup(
			project([{ kind: 'component', componentId: 'P1', field: 'speed', value: 0.8 }], base)
		);
		ws.managerFocus = 'S1';
		ws.managerOpen = true;
		const manager = await screen.findByRole('dialog', { name: 'Scenarios' });
		expect(within(manager).getByRole('heading', { name: 'Problems (1)' })).toBeInTheDocument();
		expect(manager).toHaveTextContent(
			'The value Winter sets for Transfer pump maximum speed is not valid: The minimum speed of Transfer pump must be below its maximum speed.'
		);
	});
});

describe('fields in a scenario', () => {
	it('edits a scenario value: Changed, the base value and Reset; the base is unchanged', async () => {
		const ws = setup();
		ws.setCase('S1');
		ws.nav.jumpTo('R2');
		await tick();
		const level = screen.getByRole('textbox', { name: 'Liquid level (m)' });
		await enter(level, '6');
		expect(ws.scenarios[0]!.overrides).toEqual([
			{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 }
		]);
		expect(ws.store.project.components[3]).toMatchObject({ liquidLevel: 2 });
		expect(ws.store.undoLabel).toBe('change liquid level in Winter');
		expect(level).toHaveAccessibleDescription(/^Changed in this scenario\. Base value 2 m\./);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Reset Liquid level to the base value, 2 m' })
		);
		expect(ws.scenarios[0]!.overrides).toEqual([]);
		expect(level).toHaveValue('2');
		// Typing the base value back also removes the change.
		await enter(level, '5');
		await enter(level, '2');
		expect(ws.scenarios[0]!.overrides).toEqual([]);
	});

	it('locks other values: read-only, focusable, “Same in every scenario”; names are shared', async () => {
		const ws = setup();
		ws.setCase('S1');
		ws.nav.jumpTo('R2');
		await tick();
		const elevation = screen.getByRole('textbox', { name: 'Elevation (m)' });
		expect(elevation).toHaveAttribute('readonly');
		expect(elevation).not.toBeDisabled();
		elevation.focus();
		expect(document.activeElement).toBe(elevation);
		expect(elevation).toHaveAccessibleDescription(/Same in every scenario\./);
		const name = screen.getByRole('textbox', { name: 'Name' });
		expect(name).not.toHaveAttribute('readonly');
		await enter(name, 'Upper tank');
		expect(ws.store.project.components[3]!.name).toBe('Upper tank');
		expect(ws.scenarios[0]!.overrides).toEqual([]);
	});

	it('shows the banner instead of the component actions, and hides topology actions', async () => {
		const ws = setup();
		ws.setCase('S1');
		ws.nav.jumpTo('V1');
		await tick();
		expect(screen.getByRole('note', { name: 'Scenario' })).toHaveTextContent('Scenario: Winter.');
		expect(screen.queryByRole('button', { name: 'Add after' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
		ws.nav.showConnection('outlet');
		await tick();
		expect(screen.getByRole('button', { name: /^Go to/ })).toBeInTheDocument();
		for (const name of ['Insert component', 'Add branch', 'Disconnect', 'Add pipe segment']) {
			expect(screen.queryByRole('button', { name: new RegExp(name) })).toBeNull();
		}
		await fireEvent.click(screen.getByRole('button', { name: 'Switch to base case' }));
		expect(ws.store.activeCase).toBeNull();
	});

	it('refuses an edit that is not a scenario value, with the reason', async () => {
		const ws = setup();
		ws.setCase('S1');
		expect(ws.remove('V1', true)).toBe(false);
		expect(ws.notice?.text).toBe(
			'In a scenario you can change only its values. Switch to the base case to delete Discharge isolation valve.'
		);
		expect(ws.store.project.components).toHaveLength(4);
	});

	it('in Settings: the fluid is a scenario value, units and the description are shared, the site is locked', async () => {
		const ws = setup();
		ws.setCase('S1');
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
		const dialog = await screen.findByRole('dialog', { name: 'Project settings' });
		expect(dialog).toHaveTextContent('Scenario: Winter.');
		await enter(within(dialog).getByRole('textbox', { name: 'Operating temperature (°C)' }), '5');
		expect(ws.scenarios[0]!.overrides).toEqual([
			{ kind: 'project', field: 'fluid.temperature', value: 278.15 }
		]);
		expect(ws.store.project.fluid).toMatchObject({ temperature: 293.15 });
		expect(dialog).toHaveTextContent('Changed');
		expect(within(dialog).getByRole('textbox', { name: 'Site elevation (m)' })).toHaveAttribute(
			'readonly'
		);
		await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Flow' }), {
			target: { value: 'gpm' }
		});
		expect(ws.store.project.settings.units.flow).toBe('gpm');
		expect(ws.scenarios[0]!.overrides).toHaveLength(1);
		expect(within(dialog).getByRole('textbox', { name: 'Description' })).not.toHaveAttribute(
			'readonly'
		);
	});

	it('says in the base case which scenarios set their own value', async () => {
		const ws = setup(
			project([{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 }])
		);
		ws.nav.jumpTo('R2');
		await tick();
		expect(screen.getByRole('textbox', { name: 'Liquid level (m)' })).toHaveAccessibleDescription(
			/Winter sets its own value\./
		);
	});

	it('makes every allow-listed value of every component type editable in a scenario', async () => {
		const base = pumpTransferExample();
		const kinds = [
			'reference_node',
			'assigned_flow',
			'check',
			'prv',
			'fcv',
			'equipment',
			'orifice',
			'relief_valve'
		] as const;
		const extra = kinds.reduce<Project['components']>((list, kind) => {
			const so_far = { ...base, components: [...base.components, ...list] };
			return [...list, createComponent(kind, so_far, { ...enteredFor(kind), flow: 0.002 })];
		}, []);
		const pump = base.components[1]!;
		if (pump.type === 'pump') pump.control = { mode: 'flow', setpoint: 0.015, minSpeed: 0.5 };
		const ws = setup(project([], { ...base, components: [...base.components, ...extra] }));
		ws.setCase('S1');
		/** Field names in the panel, per component, for the values the allow-list names. */
		const expected: Record<string, string[]> = {
			R2: ['Liquid level (m)', 'Surface pressure (kPa(g))'],
			P1: ['Status', 'Flow setpoint (L/s)', 'Maximum speed (%)'],
			V1: ['Status', 'Resistance given as'],
			[extra[0]!.id]: ['Pressure (kPa(g))'],
			[extra[1]!.id]: ['Direction', 'Flow (L/s)'],
			[extra[2]!.id]: ['Status', 'Resistance given as'],
			[extra[3]!.id]: ['Status', 'Outlet pressure setpoint (kPa(g))', 'Resistance given as'],
			[extra[4]!.id]: ['Status', 'Flow setpoint (L/s)', 'Resistance given as'],
			[extra[5]!.id]: [
				'Rated by',
				'Rated pressure drop (kPa)',
				'Rated flow (L/s)',
				'Rated fluid density (kg/m³)'
			],
			[extra[6]!.id]: ['Bore diameter (mm)', 'Discharge coefficient'],
			[extra[7]!.id]: [
				'Status',
				'Set pressure (difference) (kPa)',
				'Capacity given by',
				'API 526 orifice letter'
			]
		};
		for (const [id, names] of Object.entries(expected)) {
			ws.nav.jumpTo(id);
			await tick();
			for (const name of names) {
				const field = screen.getByRole(
					/given as|given by|Status|Direction|Rated by|Discharge coefficient|orifice letter/.test(
						name
					)
						? 'combobox'
						: 'textbox',
					{
						name
					}
				);
				expect(field, `${id} ${name}`).not.toHaveAttribute('readonly');
			}
		}
		// Locked on the orifice plate: its taps (installation, the same in every case).
		ws.nav.jumpTo(extra[6]!.id);
		await tick();
		expect(screen.getByRole('textbox', { name: 'Pressure taps' })).toHaveAttribute('readonly');
		// Locked on the pump: its control mode and minimum speed.
		ws.nav.jumpTo('P1');
		await tick();
		expect(screen.getByRole('textbox', { name: 'Minimum speed (%)' })).toHaveAttribute('readonly');
		expect(screen.getByRole('textbox', { name: 'Control' })).toHaveAttribute('readonly');
		// A pipe's size and material, and its length.
		ws.nav.jumpTo('P1');
		ws.nav.showConnection('discharge');
		await tick();
		// (A locked select is drawn as a read-only textbox: a combobox is editable. Without the pipe
		// library, the schedule and size are typed.)
		expect(screen.getByRole('combobox', { name: 'Material' })).toBeInTheDocument();
		for (const name of ['Schedule', 'Size (NPS) (in)']) {
			expect(screen.getByRole('textbox', { name })).not.toHaveAttribute('readonly');
		}
		expect(screen.getByRole('textbox', { name: 'Length (m)' })).not.toHaveAttribute('readonly');
		// Every component type with allow-listed values was walked (the allow-list is the API's).
		expect(Object.keys(OVERRIDE_FIELDS).sort()).toEqual(
			[
				'AssignedFlow',
				'CheckValve',
				'ControlValve',
				'Equipment',
				'IdealReferenceNode',
				'IsolationValve',
				'Orifice',
				'PipeDefinition',
				'Plug',
				'Project',
				'Pump',
				'ReliefValve',
				'Reservoir',
				'TeeBranch',
				'WyeBranch'
			].sort()
		);
	});
});

describe('results of a scenario', () => {
	const scenario: ScenarioResult = {
		id: 'S1',
		name: 'Winter',
		description: 'A colder month.',
		overrides: [
			{
				index: 0,
				override: { kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 },
				state: 'applied',
				value: 6,
				baseValue: 2,
				unit: 'm',
				message: ''
			},
			{
				index: 1,
				override: { kind: 'component', componentId: 'P7', field: 'status', value: 'off' },
				state: 'orphaned',
				value: null,
				baseValue: null,
				unit: '',
				message: 'the project has no component P7'
			}
		]
	};

	function solvedWorkspace() {
		const solve = vi.fn(
			async (
				_p: Project,
				_o?: unknown,
				request?: { scenarioId?: string }
			): Promise<SolveResponse> =>
				response(pumpTransferSolved(), request?.scenarioId ? { scenario } : {})
		);
		return setup(
			project([
				{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 },
				{ kind: 'component', componentId: 'P7', field: 'status', value: 'off' }
			]),
			{ solver: { solve } }
		);
	}

	it('say which case produced them, with the changes the server applied and those it ignored', async () => {
		const ws = solvedWorkspace();
		ws.setCase('S1');
		await ws.solve();
		await tick();
		const results = screen.getByRole('region', { name: 'Results' });
		expect(within(results).getByRole('heading', { level: 2 })).toHaveTextContent(
			'Results of Winter'
		);
		expect(within(results).getByRole('status')).toHaveTextContent(
			'Last solve of Winter: converged'
		);
		const card = within(results).getByRole('region', { name: /^Scenario: Winter/ });
		expect(card).toHaveTextContent('A colder month.');
		expect(card).toHaveTextContent('Discharge tank · Liquid level: 6 m (base: 2 m)');
		expect(card).toHaveTextContent('Ignored, no longer applies:');
		expect(card).toHaveTextContent('the project has no component P7');
		// The trace of a changed element lists its change.
		await fireEvent.click(within(card).getByRole('button', { name: 'Discharge tank' }));
		const trace = await screen.findByRole('dialog', { name: 'Discharge tank' });
		const block = within(trace).getByRole('region', { name: 'Changed by this scenario' });
		expect(block).toHaveTextContent('Liquid level: 6 m (base: 2 m)');
		expect(trace).toHaveTextContent('Scenario Winter');
	});

	it('compare cases: the base first, differences under scenario values', async () => {
		const ws = solvedWorkspace();
		await ws.solveAll();
		await tick();
		await fireEvent.click(screen.getByRole('tab', { name: 'Compare cases' }));
		const compare = screen.getByRole('region', { name: 'Compare cases' });
		const table = within(compare).getByRole('table', { name: 'Results by case' });
		expect(
			within(table)
				.getAllByRole('columnheader')
				.map((h) => h.textContent?.trim())
		).toEqual(['Result', expect.stringMatching(/^Base case/), expect.stringMatching(/^Winter/)]);
		const row = within(table).getByRole('row', { name: /Transfer pump · Flow/ });
		expect(row).toHaveTextContent('Same');
		// A column header shows its case.
		await fireEvent.click(within(table).getByRole('button', { name: 'Winter' }));
		expect(ws.store.activeCase).toBe('S1');
		expect(ws.comparing).toBe(false);
	});
});
