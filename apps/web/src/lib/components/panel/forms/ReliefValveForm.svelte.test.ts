/**
 * The pressure relief valve in the Build panel (proposal pressure-relief-valve.md §6 W1-W3): every
 * path that creates one asks for its set pressure and capacity first (neither has a default), the
 * set is a pressure difference in the display unit (never a gauge marker), the capacity is one of
 * three kinds never mixed (an API 526 letter with its area from x-relief-data, an API 520 effective
 * area, or a certified area, rated coefficient and optional overpressure on ASME's default), a kind
 * picked with no values yet keeps the stored capacity with a warning, a relief valve's free outlet
 * offers Discharge to atmosphere (one undo step), and in a scenario the status, set and capacity
 * are changes with Reset. Sets, areas and coefficients are made-up test inputs; the API is
 * replaced by fakes.
 */
import { SI_UNITS } from '$lib/utils/units';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { Project } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { projectWith, reliefProject } from '$lib/testing/helpers';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent, createEmptyProject } from '$lib/utils/factory';
import { RELIEF_DATA } from '$lib/utils/model-rules';
import { withScenarios } from '$lib/utils/scenarios';
import { IMPERIAL_UNITS, toSI } from '$lib/utils/units';

const LABEL = 'Pressure relief valve (API 520, liquids)';
const GROUP = 'Relief valves: overpressure protection, liquids';
const SET_REQUIRED = 'Enter the set pressure: it has no default.';
const CAPACITY_REQUIRED =
	'Choose an API 526 orifice letter, or enter an effective area or the certified area and coefficient: the capacity has no default.';
const SET = 'Set pressure (difference) (kPa)';

function current(): string {
	const build = screen.getByRole('region', { name: 'Build' });
	return within(build).getAllByRole('heading', { level: 2 })[0]?.textContent?.trim() ?? '';
}

async function type(input: HTMLElement, text: string) {
	await fireEvent.input(input, { target: { value: text } });
	await fireEvent.change(input);
}

function valveOf(project: Project, id = 'RV1') {
	const valve = project.components.find((c) => c.id === id);
	return valve?.type === 'relief_valve' ? valve : undefined;
}

describe('adding a relief valve', () => {
	it('after a reservoir: asks for the set and the capacity first, each at its field', async () => {
		const empty = createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z', units: SI_UNITS });
		const ws = testWorkspace({ ...empty, components: [createComponent('reservoir', empty)] });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const dialog = await screen.findByRole('dialog', { name: 'Add after Reservoir R1' });
		const kinds = within(dialog).getByRole('combobox', { name: 'Component' });
		const option = within(kinds).getByRole('option', { name: LABEL });
		expect(option.closest('optgroup')).toHaveAttribute('label', GROUP);
		await fireEvent.change(kinds, { target: { value: 'relief_valve' } });
		const set = within(dialog).getByRole('textbox', { name: SET });
		expect(set).toHaveValue('');
		// A difference: no gauge marker, and the hint says what the set is measured against.
		expect(set).toHaveAccessibleDescription(
			/^The static pressure difference, inlet minus outlet, at which the valve starts to open\. Discharging to atmosphere at the valve's elevation it is the gauge set pressure; with a constant back pressure \(a return line\) it is the bench setting/
		);
		const given = within(dialog).getByRole('combobox', { name: 'Capacity given by' });
		expect(given).toHaveValue('api526');
		expect(
			within(given)
				.getAllByRole('option')
				.map((o) => o.textContent)
		).toEqual([
			'API 526 orifice letter',
			'API 520 effective area',
			'Certified area and coefficient'
		]);
		const letter = within(dialog).getByRole('combobox', { name: 'API 526 orifice letter' });
		// Each letter with its effective area from x-relief-data, in the display unit (mm² in SI).
		const letters = within(letter)
			.getAllByRole('option')
			.map((o) => o.textContent);
		expect(letters[0]).toBe('Choose a letter');
		expect(letters).toContain('J: 830.3 mm²');
		expect(letters).toHaveLength(1 + Object.keys(RELIEF_DATA.api526Areas).length);
		expect(
			within(dialog).getByText(
				/^API 520's effective coefficient of discharge 0\.65 and ASME's 10 % or 3 psi/
			)
		).toBeInTheDocument();

		// Neither has a default: Add says both are missing, each at its field.
		const add = within(dialog).getByRole('button', { name: 'Add' });
		await fireEvent.click(add);
		const alerts = within(dialog)
			.getAllByRole('alert')
			.map((a) => a.textContent?.trim());
		expect(alerts).toEqual([SET_REQUIRED, CAPACITY_REQUIRED]);
		// Each field with an error is marked invalid, the letter's select as the set's input.
		expect(set).toHaveAttribute('aria-invalid', 'true');
		expect(letter).toHaveAttribute('aria-invalid', 'true');
		expect(letter).toHaveAccessibleDescription(new RegExp(`${CAPACITY_REQUIRED.slice(0, 40)}`));
		expect(ws.project.components).toHaveLength(1);
		// Each error goes as its value is entered (the set's as it is typed, never on blur).
		await fireEvent.input(set, { target: { value: '500' } });
		expect(within(dialog).queryByText(SET_REQUIRED)).toBeNull();
		await fireEvent.change(set);
		await fireEvent.change(letter, { target: { value: 'J' } });
		expect(within(dialog).queryByRole('alert')).toBeNull();
		expect(letter).not.toHaveAttribute('aria-invalid');
		await fireEvent.click(add);

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Relief valve RV1');
		expect(valveOf(ws.project)).toEqual({
			id: 'RV1',
			name: 'Relief valve RV1',
			elevation: 0,
			type: 'relief_valve',
			setPressure: toSI(500, 'kPa'),
			capacity: { kind: 'api526', letter: 'J' },
			status: 'active',
			ports: [
				{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
				{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
			]
		});
		expect(ws.project.connections).toMatchObject([
			{ fromComponentId: 'R1', toComponentId: 'RV1', toPortId: 'inlet' }
		]);
	});

	it('before a pump (inserted), with a certified capacity: every required value is asked for', async () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.nav.jumpTo('P1');
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add before' }));
		const dialog = await screen.findByRole('dialog', { name: /^Add before/ });
		await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Component' }), {
			target: { value: 'relief_valve' }
		});
		await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Capacity given by' }), {
			target: { value: 'certified' }
		});
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(
			within(dialog)
				.getAllByRole('alert')
				.map((a) => a.textContent?.trim())
		).toEqual([
			SET_REQUIRED,
			'Enter the certified actual orifice area: the capacity has no default.',
			'Enter the rated coefficient of discharge from the certification: the capacity has no default.'
		]);
		await type(within(dialog).getByRole('textbox', { name: SET }), '400');
		await type(within(dialog).getByRole('textbox', { name: 'Actual orifice area (mm²)' }), '250');
		await type(
			within(dialog).getByRole('textbox', { name: 'Rated coefficient of discharge (K)' }),
			'0.7'
		);
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(screen.queryByRole('dialog')).toBeNull();
		// The overpressure is left out: ASME's, the default.
		expect(valveOf(ws.project)?.capacity).toEqual({
			kind: 'certified',
			area: toSI(250, 'mm2'),
			dischargeCoefficient: 0.7
		});
		expect(ws.project.connections.find((c) => c.toComponentId === 'RV1')).toMatchObject({
			fromComponentId: 'R1',
			toPortId: 'inlet'
		});
		expect(ws.project.connections.find((c) => c.fromComponentId === 'RV1')).toMatchObject({
			fromPortId: 'outlet',
			toComponentId: 'P1'
		});
	});

	it('as the first component and in the Piping view: asked for in both', async () => {
		const ws = testWorkspace(
			createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z', units: SI_UNITS })
		);
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'First component' }), {
			target: { value: 'relief_valve' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getAllByRole('alert').map((a) => a.textContent?.trim())).toEqual([
			SET_REQUIRED,
			CAPACITY_REQUIRED
		]);
		expect(ws.project.components).toEqual([]);
		await type(build.getByRole('textbox', { name: SET }), '300');
		await fireEvent.change(build.getByRole('combobox', { name: 'Capacity given by' }), {
			target: { value: 'effective' }
		});
		await type(build.getByRole('textbox', { name: 'API 520 effective area (mm²)' }), '447.07');
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Relief valve RV1');
		expect(valveOf(ws.project)?.capacity).toEqual({ kind: 'effective', area: toSI(447.07, 'mm2') });

		await fireEvent.click(build.getByRole('button', { name: 'Next: connect outlet' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'Add a component here' }), {
			target: { value: 'relief_valve' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getAllByRole('alert').map((a) => a.textContent?.trim())).toEqual([
			SET_REQUIRED,
			CAPACITY_REQUIRED
		]);
		expect(ws.project.components).toHaveLength(1);
		await type(build.getByRole('textbox', { name: SET }), '350');
		await fireEvent.change(build.getByRole('combobox', { name: 'API 526 orifice letter' }), {
			target: { value: 'F' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(ws.project.components).toHaveLength(2);
		expect(valveOf(ws.project, 'RV2')).toMatchObject({
			setPressure: toSI(350, 'kPa'),
			capacity: { kind: 'api526', letter: 'F' }
		});
	});
});

describe('Discharge to atmosphere', () => {
	/** R1 → L1 → RV1, its outlet free (made-up test inputs). */
	function freeOutlet(): Project {
		const project = reliefProject();
		return {
			...project,
			components: project.components.slice(0, 2),
			connections: [project.connections[0]!]
		};
	}

	it("adds an open discharge at a relief valve's free outlet, in one undo step", async () => {
		const project = freeOutlet();
		project.components[1] = {
			...project.components[1]!,
			elevation: 3
		} as Project['components'][number];
		const ws = testWorkspace(project);
		ws.nav.jumpTo('RV1');
		ws.nav.showConnection('outlet');
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		const discharge = build.getByRole('button', { name: 'Discharge to atmosphere' });
		expect(discharge).toHaveAccessibleDescription(
			/^Discharge to atmosphere adds an open discharge: a reference node at 0 kPa\(g\), reached by 1 m of pipe sized to the port with an exit, at the valve's elevation\./
		);
		// Beside Plug this port, before it.
		const buttons = build.getAllByRole('button').map((b) => b.textContent?.trim());
		expect(buttons.indexOf('Discharge to atmosphere')).toBe(buttons.indexOf('Plug this port') - 1);
		await fireEvent.click(discharge);
		const node = ws.project.components.find((c) => c.id === 'N1');
		expect(node).toEqual({
			id: 'N1',
			name: 'Open discharge N1',
			elevation: 3,
			type: 'reference_node',
			referenceType: 'ideal',
			pressure: 0,
			ports: [{ id: 'port_1', nominalSize: 0.0762, direction: 'bidirectional' }]
		});
		expect(ws.project.connections.at(-1)).toEqual({
			id: 'L2',
			fromComponentId: 'RV1',
			fromPortId: 'outlet',
			toComponentId: 'N1',
			toPortId: 'port_1',
			piping: {
				pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.0762, length: 1 }],
				fittings: [{ type: 'exit', quantity: 1, pipeIndex: 0 }]
			}
		});
		// One undo step takes both away.
		expect(ws.undo()).toBe(true);
		expect(ws.project.components.map((c) => c.id)).toEqual(['R1', 'RV1']);
		expect(ws.project.connections.map((c) => c.id)).toEqual(['L1']);
	});

	it('words the discharge in the display units, its pipe length too', async () => {
		const project = freeOutlet();
		project.settings.units = { ...IMPERIAL_UNITS };
		const ws = testWorkspace(project);
		ws.nav.jumpTo('RV1');
		ws.nav.showConnection('outlet');
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		// 1 m (factory SHORT_PIPE_LENGTH) in feet, to four significant digits: 3.281 ft.
		const feet = Number((1 / 0.3048).toPrecision(4));
		expect(
			build.getByRole('button', { name: 'Discharge to atmosphere' })
		).toHaveAccessibleDescription(
			new RegExp(
				`^Discharge to atmosphere adds an open discharge: a reference node at 0 psig, reached by ${String(feet).replace('.', '\\.')} ft of pipe sized to the port with an exit,`
			)
		);
		await fireEvent.click(build.getByRole('button', { name: 'Discharge to atmosphere' }));
		expect(ws.project.connections.at(-1)?.piping.pipes[0]?.length).toBe(1);
	});

	it('is not offered at a check valve outlet', async () => {
		const valve = createComponent('check', createEmptyProject());
		const ws = testWorkspace(projectWith([valve]));
		ws.nav.jumpTo('V1');
		ws.nav.showConnection('outlet');
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		expect(build.getByRole('button', { name: 'Plug this port' })).toBeInTheDocument();
		expect(build.queryByRole('button', { name: 'Discharge to atmosphere' })).toBeNull();
	});

	it('is not offered at a relief valve inlet', async () => {
		const project = reliefProject();
		const ws = testWorkspace({
			...project,
			connections: [project.connections[1]!]
		});
		ws.nav.jumpTo('RV1');
		ws.nav.showConnection('inlet');
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		expect(build.getByRole('button', { name: 'Plug this port' })).toBeInTheDocument();
		expect(build.queryByRole('button', { name: 'Discharge to atmosphere' })).toBeNull();
	});
});

describe('ReliefValveForm', () => {
	it('names the set in the display pressure unit as a difference and stores it exactly in SI', async () => {
		const project = reliefProject();
		project.settings.units = { ...IMPERIAL_UNITS };
		const ws = testWorkspace(project);
		ws.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: ws });
		expect(current()).toBe('Discharge relief');
		const set = screen.getByRole('textbox', { name: 'Set pressure (difference) (psi)' });
		expect(set).toHaveValue(String(Number((500000 / toSI(1, 'psi')).toPrecision(6))));
		await type(set, '80');
		expect(valveOf(ws.project)?.setPressure).toBe(toSI(80, 'psi'));
		expect(screen.getByRole('button', { name: 'Undo change set pressure' })).toBeEnabled();
		// The schema's bounds: (0, 1e8] Pa.
		await type(set, '0');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be greater than 0 psi.');
		expect(valveOf(ws.project)?.setPressure).toBe(toSI(80, 'psi'));
		// The letters in in² with US units.
		const letter = screen.getByRole('combobox', { name: 'API 526 orifice letter' });
		expect(letter).toHaveValue('F');
		expect(within(letter).getByRole('option', { name: 'J: 1.287 in²' })).toBeInTheDocument();
		await fireEvent.change(letter, { target: { value: 'J' } });
		expect(valveOf(ws.project)?.capacity).toEqual({ kind: 'api526', letter: 'J' });
	});

	it('names each capacity edit in its undo step with its acronyms and symbols as written', async () => {
		const ws = testWorkspace(reliefProject());
		ws.nav.jumpTo('RV1');
		const { unmount } = render(WorkspaceView, { workspace: ws });
		await fireEvent.change(screen.getByRole('combobox', { name: 'API 526 orifice letter' }), {
			target: { value: 'J' }
		});
		expect(ws.store.undoLabel).toBe('change API 526 orifice letter');
		expect(
			screen.getByRole('button', { name: 'Undo change API 526 orifice letter' })
		).toBeEnabled();
		unmount();

		const effective = testWorkspace(reliefProject({ capacity: { kind: 'effective', area: 4e-4 } }));
		effective.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: effective });
		await type(screen.getByRole('textbox', { name: 'API 520 effective area (mm²)' }), '450');
		expect(effective.store.undoLabel).toBe('change API 520 effective area');
	});

	it('names a certified capacity edit in its undo step, its symbol (K) as written', async () => {
		const ws = testWorkspace(
			reliefProject({
				capacity: { kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7, overpressure: 0.1 }
			})
		);
		ws.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: ws });
		await type(screen.getByRole('textbox', { name: 'Actual orifice area (mm²)' }), '300');
		expect(ws.store.undoLabel).toBe('change actual orifice area');
		await type(screen.getByRole('textbox', { name: 'Rated coefficient of discharge (K)' }), '0.75');
		expect(ws.store.undoLabel).toBe('change rated coefficient of discharge (K)');
		await type(screen.getByRole('textbox', { name: 'Entered overpressure (%)' }), '8');
		expect(ws.store.undoLabel).toBe('change overpressure at full lift');
	});

	it('has the statuses active and locked closed, and a hint that names what it is not', async () => {
		const ws = testWorkspace(reliefProject());
		ws.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: ws });
		const status = screen.getByRole('combobox', { name: 'Status' });
		expect(
			within(status)
				.getAllByRole('option')
				.map((o) => o.textContent)
		).toEqual(['Active', 'Locked closed (gagged or blocked: does not open)']);
		await fireEvent.change(status, { target: { value: 'locked_closed' } });
		expect(valveOf(ws.project)?.status).toBe('locked_closed');
		expect(
			screen.getByText(/Not EPANET's PSV \(pressure-sustaining valve\)\./)
		).toBeInTheDocument();
		expect(screen.getByText(/partial lift is\s+flagged/)).toBeInTheDocument();
	});

	it('keeps the stored capacity while a kind picked is not entered, then stores the new one whole', async () => {
		const ws = testWorkspace(reliefProject());
		ws.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: ws });
		const given = screen.getByRole('combobox', { name: 'Capacity given by' });
		await fireEvent.change(given, { target: { value: 'certified' } });
		const pending =
			'Enter the actual orifice area and the rated coefficient of discharge to use them; until then the API 526 letter F applies.';
		expect(screen.getByText(pending)).toBeInTheDocument();
		expect(valveOf(ws.project)?.capacity).toEqual({ kind: 'api526', letter: 'F' });
		const area = screen.getByRole('textbox', { name: 'Actual orifice area (mm²)' });
		expect(area).toHaveValue('');
		await type(area, '250');
		// Not all entered: still the letter.
		expect(valveOf(ws.project)?.capacity).toEqual({ kind: 'api526', letter: 'F' });
		await type(screen.getByRole('textbox', { name: 'Rated coefficient of discharge (K)' }), '0.7');
		expect(valveOf(ws.project)?.capacity).toEqual({
			kind: 'certified',
			area: toSI(250, 'mm2'),
			dischargeCoefficient: 0.7
		});
		expect(screen.queryByText(pending)).toBeNull();
		// ASME's overpressure by default, its value at this set shown (10 % at 500 kPa).
		const overpressure = screen.getByRole('combobox', { name: 'Overpressure at full lift' });
		expect(overpressure).toHaveValue('asme');
		expect(within(overpressure).getByRole('option', { selected: true }).textContent).toBe(
			"ASME's 10 % or 3 psi (20.68 kPa), whichever is greater (the default)"
		);
		expect(overpressure).toHaveAccessibleDescription(/: 10 % at this set\./);
		// An entered overpressure, then back to ASME's.
		await fireEvent.change(overpressure, { target: { value: 'entered' } });
		const entered = screen.getByRole('textbox', { name: 'Entered overpressure (%)' });
		await type(entered, '8');
		expect(valveOf(ws.project)?.capacity).toMatchObject({ overpressure: 0.08 });
		await fireEvent.change(screen.getByRole('combobox', { name: 'Overpressure at full lift' }), {
			target: { value: 'asme' }
		});
		expect(valveOf(ws.project)?.capacity).not.toHaveProperty('overpressure');
	});

	it("says ASME's default applies to a set of at least 15 psi only", async () => {
		const ws = testWorkspace(
			reliefProject({
				setPressure: 50000,
				capacity: { kind: 'certified', area: 0.00025, dischargeCoefficient: 0.7 }
			})
		);
		ws.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: ws });
		expect(
			screen.getByText(
				"Below 15 psi (103.4 kPa) (ASME VIII's scope) no source gives the overpressure: enter the valve's certified area, rated coefficient and full-lift overpressure."
			)
		).toBeInTheDocument();
	});

	it("warns at a letter or an effective area set below ASME VIII's 15 psi scope", async () => {
		const below =
			"This set is below 15 psi (103.4 kPa), where no source gives the overpressure: give the capacity as a certified area and coefficient, with the valve's full-lift overpressure.";
		const ws = testWorkspace(reliefProject({ setPressure: 50000 }));
		ws.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: ws });
		const letter = screen.getByRole('combobox', { name: 'API 526 orifice letter' });
		expect(letter).toHaveAccessibleDescription(new RegExp(`${below.replace(/[().]/g, '\\$&')}$`));
		expect(screen.getByText(/This set is below 15 psi/).closest('p')).toHaveClass('text-amber-800');
		// An effective area: the same warning, describing the area.
		await fireEvent.change(screen.getByRole('combobox', { name: 'Capacity given by' }), {
			target: { value: 'effective' }
		});
		expect(
			screen.getByRole('textbox', { name: 'API 520 effective area (mm²)' })
		).toHaveAccessibleDescription(/This set is below 15 psi \(103\.4 kPa\), where no source/);
		// At or above the scope: the statement alone, no warning.
		await type(screen.getByRole('textbox', { name: SET }), '200');
		expect(screen.queryByText(/This set is below/)).toBeNull();
		expect(
			screen
				.getByText(/for a set of at least 15 psi \(103\.4 kPa\), ASME VIII's scope:/)
				.closest('p')
		).toHaveClass('hint');
	});

	it('in a scenario: the set and a letter are changes of their values; a kind change is one', async () => {
		const ws = testWorkspace(
			withScenarios(reliefProject(), [{ id: 'S1', name: 'Smaller valve', overrides: [] }])
		);
		ws.setCase('S1');
		ws.nav.jumpTo('RV1');
		render(WorkspaceView, { workspace: ws });
		const overrides = () => ws.store.project.scenarios![0]!.overrides ?? [];
		await type(screen.getByRole('textbox', { name: SET }), '450');
		await fireEvent.change(screen.getByRole('combobox', { name: 'API 526 orifice letter' }), {
			target: { value: 'E' }
		});
		expect(overrides()).toEqual([
			{ kind: 'component', componentId: 'RV1', field: 'setPressure', value: toSI(450, 'kPa') },
			{ kind: 'component', componentId: 'RV1', field: 'capacity.letter', value: 'E' }
		]);
		expect(screen.getByRole('textbox', { name: SET })).toHaveAccessibleDescription(
			/Changed in this scenario. Base value 500 kPa./
		);
		expect(
			screen.getByRole('combobox', { name: 'API 526 orifice letter' })
		).toHaveAccessibleDescription(/Changed in this scenario. Base value API 526 F \(198.1 mm²\)./);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Reset Set pressure to the base value, 500 kPa' })
		);
		expect(overrides()).toEqual([
			{ kind: 'component', componentId: 'RV1', field: 'capacity.letter', value: 'E' }
		]);
		// A kind change: one whole-capacity change, which takes the letter's place.
		await fireEvent.change(screen.getByRole('combobox', { name: 'Capacity given by' }), {
			target: { value: 'effective' }
		});
		await type(screen.getByRole('textbox', { name: 'API 520 effective area (mm²)' }), '500');
		expect(overrides()).toEqual([
			{
				kind: 'component',
				componentId: 'RV1',
				field: 'capacity',
				value: { kind: 'effective', area: toSI(500, 'mm2') }
			}
		]);
		expect(screen.getAllByText('Changed')).toHaveLength(1);
		await fireEvent.click(
			screen.getByRole('button', {
				name: 'Reset Capacity to the base value, API 526 F (198.1 mm²), Kd 0.65 (preliminary)'
			})
		);
		expect(overrides()).toEqual([]);
		expect(valveOf(ws.store.project)?.capacity).toEqual({ kind: 'api526', letter: 'F' });
	});
});

describe('the forms that point to the relief valve', () => {
	it("a check valve's cracking pressure says it reads the EGL and points to the relief valve", async () => {
		const ws = testWorkspace(projectWith([createComponent('check', createEmptyProject())]));
		ws.nav.jumpTo('V1');
		render(WorkspaceView, { workspace: ws });
		expect(
			screen.getByRole('textbox', { name: 'Cracking pressure (kPa)' })
		).toHaveAccessibleDescription(
			"The forward pressure across the valve that opens it, read on the energy grade line: the static pressure difference, inlet minus outlet, plus ρg × (inlet port elevation − outlet port elevation); 0 opens on any forward flow. For overpressure protection use a pressure relief valve: a check valve's fixed K does not follow API 520's capacity."
		);
	});

	it("a PSV's setpoint says it is EPANET's pressure-sustaining valve and points to the relief valve", async () => {
		const project = projectWith([createComponent('psv', createEmptyProject())]);
		const ws = testWorkspace(project);
		ws.nav.jumpTo('V1');
		render(WorkspaceView, { workspace: ws });
		expect(
			screen.getByRole('textbox', { name: 'Inlet pressure setpoint (kPa(g))' })
		).toHaveAccessibleDescription(
			/EPANET's pressure-sustaining valve, which modulates to hold it\. For a safety or relief valve \(overpressure protection\), use the pressure relief valve \(API 520, liquids\)\./
		);
	});
});
