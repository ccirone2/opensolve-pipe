/**
 * The equipment item in the Build panel (proposal equipment-pressure-drop.md §6.1–§6.2): every path
 * that creates one asks for its rating first (no value has a default); the form enters a rated
 * point in display units (the drop a difference, never gauge) or a Cv or Kv as entered, the
 * density buttons write the API's exact double as the user's value, a kind picked is pending until
 * its values are all entered, and in a scenario a value of the base's kind is a change of that value
 * while a change of kind is one change of the whole rating. Ratings and densities are made-up test
 * inputs; the API is replaced by fakes (a density is what a fake answers, not a property value).
 */
import { SI_UNITS } from '$lib/utils/units';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { FluidDefinition, FluidProperties, Project } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { equipmentProject } from '$lib/testing/helpers';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent, createEmptyProject } from '$lib/utils/factory';
import { withScenarios } from '$lib/utils/scenarios';
import { IMPERIAL_UNITS, toSI } from '$lib/utils/units';

const LABEL = 'Equipment (rated pressure drop)';
const GROUP = 'Equipment: heat exchangers, coils, strainers, filters';
const REQUIRED = [
	'Enter the rated pressure drop from the datasheet: it has no default.',
	'Enter the rated flow from the datasheet: it has no default.',
	'Enter the rated fluid density, or use one of the buttons: it has no default.'
];
/** What the fakes answer for the two buttons' fluids (made-up doubles, as the API would send). */
const WATER_15C = 999.1026214252;
const CASE_FLUID = 998.207150484;

function current(): string {
	const build = screen.getByRole('region', { name: 'Build' });
	return within(build).getAllByRole('heading', { level: 2 })[0]?.textContent?.trim() ?? '';
}

async function type(input: HTMLElement, text: string) {
	await fireEvent.input(input, { target: { value: text } });
	await fireEvent.change(input);
}

function ratingOf(project: Project, id = 'E1') {
	const item = project.components.find((c) => c.id === id);
	return item?.type === 'equipment' ? item.rating : undefined;
}

/** A fake of POST /fluids/properties: the density of water at 15 °C, else of the case fluid. */
function fluidProperties() {
	return vi.fn(
		async (fluid: FluidDefinition): Promise<FluidProperties> =>
			({
				name: 'made-up',
				temperature: 293.15,
				concentration: null,
				density:
					fluid.kind === 'builtin' && fluid.fluidId === 'water' && fluid.temperature === 288.15
						? WATER_15C
						: CASE_FLUID,
				dynamicViscosity: 0.001,
				kinematicViscosity: 1e-6,
				vaporPressure: 2339,
				sources: {}
			}) as FluidProperties
	);
}

describe('adding an equipment item', () => {
	it('after a reservoir: asks for every rating value first, then adds it with the exact values', async () => {
		const empty = createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z', units: SI_UNITS });
		const properties = fluidProperties();
		const ws = testWorkspace(
			{ ...empty, components: [createComponent('reservoir', empty)] },
			{ library: { fluidProperties: properties } }
		);
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const dialog = await screen.findByRole('dialog', { name: 'Add after Reservoir R1' });
		const kinds = within(dialog).getByRole('combobox', { name: 'Component' });
		const option = within(kinds).getByRole('option', { name: LABEL });
		expect(option.closest('optgroup')).toHaveAttribute('label', GROUP);
		await fireEvent.change(kinds, { target: { value: 'equipment' } });
		expect(within(dialog).getByRole('combobox', { name: 'Rated by' })).toHaveValue('point');
		const drop = within(dialog).getByRole('textbox', { name: 'Rated pressure drop (kPa)' });
		const flow = within(dialog).getByRole('textbox', { name: 'Rated flow (L/s)' });
		const density = within(dialog).getByRole('textbox', { name: 'Rated fluid density (kg/m³)' });
		for (const field of [drop, flow, density]) expect(field).toHaveValue('');

		// No rating is cited as a default, so none is invented: Add names each value missing.
		const add = within(dialog).getByRole('button', { name: 'Add' });
		await fireEvent.click(add);
		expect(
			within(dialog)
				.getAllByRole('alert')
				.map((a) => a.textContent?.trim())
		).toEqual(REQUIRED);
		expect(ws.project.components).toHaveLength(1);
		// Each error goes as soon as its value is typed (never on blur: Add stays under the pointer).
		await fireEvent.input(drop, { target: { value: '35' } });
		expect(within(dialog).getAllByRole('alert')).toHaveLength(2);
		await fireEvent.change(drop);
		await type(flow, '10');
		await fireEvent.click(within(dialog).getByRole('button', { name: "This case's fluid" }));
		await vi.waitFor(() => expect(density).toHaveValue('998.207'));
		expect(properties).toHaveBeenCalledWith(ws.project.fluid);
		expect(within(dialog).queryByRole('alert')).toBeNull();
		await fireEvent.click(add);

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Equipment E1');
		// SI exactly: the typed values converted, the density the API's double, untouched.
		expect(ratingOf(ws.project)).toEqual({
			kind: 'point',
			pressureLoss: toSI(35, 'kPa'),
			flow: toSI(10, 'L/s'),
			density: CASE_FLUID
		});
		expect(ws.project.connections).toMatchObject([
			{ fromComponentId: 'R1', toComponentId: 'E1', toPortId: 'inlet' }
		]);
	});

	it('before a pump (inserted): the rating is asked for there too, a Cv stored as entered', async () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.nav.jumpTo('P1');
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add before' }));
		const dialog = await screen.findByRole('dialog', { name: /^Add before/ });
		const kinds = within(dialog).getByRole('combobox', { name: 'Component' });
		expect(within(kinds).getByRole('option', { name: LABEL })).toBeInTheDocument();
		await fireEvent.change(kinds, { target: { value: 'equipment' } });
		await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Rated by' }), {
			target: { value: 'Cv' }
		});
		const cv = within(dialog).getByRole('textbox', { name: 'Cv' });
		expect(cv).toHaveAccessibleDescription(/US gpm of water at 1 psi pressure drop/);
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(within(dialog).getByRole('alert')).toHaveTextContent(
			'Enter the Cv from the datasheet: it has no default.'
		);
		expect(ws.project.components).toHaveLength(4);
		await type(cv, '80');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(ratingOf(ws.project)).toEqual({ kind: 'Cv', value: 80 });
		// Inserted in the suction line, oriented with the flow: inlet upstream, outlet to the pump.
		expect(ws.project.connections.find((c) => c.toComponentId === 'E1')).toMatchObject({
			fromComponentId: 'R1',
			toPortId: 'inlet'
		});
		expect(ws.project.connections.find((c) => c.fromComponentId === 'E1')).toMatchObject({
			fromPortId: 'outlet',
			toComponentId: 'P1'
		});
	});

	it('as the first component and at a free port: the rating is asked for in both', async () => {
		const ws = testWorkspace(
			createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z', units: SI_UNITS })
		);
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'First component' }), {
			target: { value: 'equipment' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getAllByRole('alert').map((a) => a.textContent?.trim())).toEqual(REQUIRED);
		expect(ws.project.components).toEqual([]);
		await fireEvent.change(build.getByRole('combobox', { name: 'Rated by' }), {
			target: { value: 'Kv' }
		});
		// Another kind: the errors of the rated point go, none is carried.
		expect(build.queryByRole('alert')).toBeNull();
		await type(build.getByRole('textbox', { name: 'Kv' }), '60');
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Equipment E1');
		expect(ratingOf(ws.project)).toEqual({ kind: 'Kv', value: 60 });

		await fireEvent.click(build.getByRole('button', { name: 'Next: connect outlet' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'Add a component here' }), {
			target: { value: 'equipment' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getAllByRole('alert')).toHaveLength(3);
		expect(ws.project.components).toHaveLength(1);
	});
	it('the first component: a density note goes as the density is typed, so Add never moves on the press', async () => {
		const properties = fluidProperties();
		const ws = testWorkspace(
			createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z', units: SI_UNITS }),
			{
				library: { fluidProperties: properties }
			}
		);
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'First component' }), {
			target: { value: 'equipment' }
		});
		const add = build.getByRole('button', { name: 'Add' });
		const form = add.closest('form')!;
		await type(build.getByRole('textbox', { name: 'Rated pressure drop (kPa)' }), '35');
		await type(build.getByRole('textbox', { name: 'Rated flow (L/s)' }), '10');
		await fireEvent.click(build.getByRole('button', { name: 'Water at 15 °C' }));
		const rating = build.getByRole('group', { name: 'Rating' });
		await vi.waitFor(() =>
			expect(within(rating).getByRole('status')).toHaveTextContent(
				/^Entered the density of water at 15 °C/
			)
		);
		// Typing over the density: the note no longer describes it, and goes as the user types…
		const density = build.getByRole('textbox', { name: 'Rated fluid density (kg/m³)' });
		await fireEvent.input(density, { target: { value: '1000' } });
		expect(within(rating).getByRole('status')).toHaveTextContent('');
		// …so when the field stores it, on the press of Add (it loses focus), nothing above the
		// button changes: Add stays under the pointer and the press adds the item.
		const before = form.textContent;
		await fireEvent.change(density);
		expect(form.textContent).toBe(before);
		await fireEvent.click(add);
		expect(current()).toBe('Equipment E1');
		expect(ratingOf(ws.project)).toEqual({
			kind: 'point',
			pressureLoss: toSI(35, 'kPa'),
			flow: toSI(10, 'L/s'),
			density: 1000
		});
	});
});

describe('EquipmentForm', () => {
	it('names the rated drop as a difference in the display unit, never gauge', () => {
		const project = equipmentProject();
		project.settings.units = { ...IMPERIAL_UNITS };
		const ws = testWorkspace(project);
		ws.nav.jumpTo('E1');
		render(WorkspaceView, { workspace: ws });
		expect(current()).toBe('Strainer');
		expect(screen.getByRole('textbox', { name: 'Rated pressure drop (psi)' })).toBeInTheDocument();
		expect(screen.queryByRole('textbox', { name: /\(psig\)|\(kPa\(g\)\)/ })).toBeNull();
		expect(screen.getByRole('textbox', { name: 'Rated flow (gpm)' })).toBeInTheDocument();
		expect(
			screen.getByRole('textbox', { name: 'Rated fluid density (lb/ft³)' })
		).toBeInTheDocument();
		expect(screen.getByText(/ΔP = ΔP/)).toBeInTheDocument();
	});

	it("tells how to enter a static drop between nozzles: decision 4's elevation and velocity terms at ρ_r", () => {
		const ws = testWorkspace(equipmentProject());
		ws.nav.jumpTo('E1');
		render(WorkspaceView, { workspace: ws });
		expect(
			screen.getByRole('textbox', { name: 'Rated pressure drop (kPa)' })
		).toHaveAccessibleDescription(
			'From the datasheet: the pressure lost from inlet to outlet at the rated flow, without any static head. For a static drop measured between nozzles at different heights or bores, subtract ρ_r g × (outlet − inlet height) and ρ_r (v_out² − v_in²)/2, with ρ_r the rated fluid density and v the nozzle velocities at the rated flow; keep the ports at their real elevations.'
		);
	});

	it('stores what is typed exactly in SI, and refuses a value out of the schema bounds', async () => {
		const ws = testWorkspace(equipmentProject());
		ws.nav.jumpTo('E1');
		render(WorkspaceView, { workspace: ws });
		const drop = screen.getByRole('textbox', { name: 'Rated pressure drop (kPa)' });
		expect(drop).toHaveValue('25');
		await type(drop, '70');
		expect(ratingOf(ws.project)).toEqual({
			kind: 'point',
			pressureLoss: 70000,
			flow: 0.01,
			density: 999.1
		});
		expect(screen.getByRole('button', { name: 'Undo change rated pressure drop' })).toBeEnabled();
		await type(drop, '0');
		expect(drop).toHaveAttribute('aria-invalid', 'true');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be greater than 0 kPa.');
		await type(drop, '200000');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be at most 100000 kPa.');
		expect(ratingOf(ws.project)).toMatchObject({ pressureLoss: 70000 });
	});

	it("each density button writes the API's exact double, as the user's value", async () => {
		const properties = fluidProperties();
		const ws = testWorkspace(equipmentProject(), { library: { fluidProperties: properties } });
		ws.nav.jumpTo('E1');
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Water at 15 °C' }));
		await vi.waitFor(() => expect(ratingOf(ws.project)).toMatchObject({ density: WATER_15C }));
		expect(properties).toHaveBeenLastCalledWith({
			kind: 'builtin',
			fluidId: 'water',
			temperature: 288.15
		});
		expect(
			screen.getByText(/^Entered the density of water at 15 °C, 999\.103 kg\/m³, as your value/)
		).toHaveAttribute('role', 'status');
		await fireEvent.click(screen.getByRole('button', { name: "This case's fluid" }));
		await vi.waitFor(() => expect(ratingOf(ws.project)).toMatchObject({ density: CASE_FLUID }));
		expect(properties).toHaveBeenLastCalledWith(ws.project.fluid);
	});

	it('a density button keeps focus while it works; its note goes to a live region present before it', async () => {
		let answer!: (properties: FluidProperties) => void;
		const properties = vi.fn(() => new Promise<FluidProperties>((resolve) => (answer = resolve)));
		const ws = testWorkspace(equipmentProject(), { library: { fluidProperties: properties } });
		ws.nav.jumpTo('E1');
		render(WorkspaceView, { workspace: ws });
		const rating = screen.getByRole('group', { name: 'Rating' });
		// The live region is there, empty, before any note is put in it.
		const status = within(rating).getByRole('status');
		expect(status).toHaveTextContent('');
		const water = within(rating).getByRole('button', { name: 'Water at 15 °C' });
		const other = within(rating).getByRole('button', { name: "This case's fluid" });
		water.focus();
		await fireEvent.click(water);
		// While it works: the pressed button keeps focus, unavailable but not disabled, and a press
		// on either button asks nothing more.
		expect(water).toHaveTextContent('Getting…');
		expect(water).toHaveFocus();
		for (const button of [water, other]) {
			expect(button).not.toBeDisabled();
			expect(button).toHaveAttribute('aria-disabled', 'true');
		}
		await fireEvent.click(other);
		await fireEvent.click(water);
		expect(properties).toHaveBeenCalledTimes(1);
		const fake = await fluidProperties()({
			kind: 'builtin',
			fluidId: 'water',
			temperature: 288.15
		});
		answer(fake);
		await vi.waitFor(() => expect(ratingOf(ws.project)).toMatchObject({ density: WATER_15C }));
		expect(within(rating).getByRole('status')).toBe(status);
		expect(status).toHaveTextContent(/^Entered the density of water at 15 °C, 999\.103 kg\/m³/);
		expect(water).toHaveTextContent('Water at 15 °C');
		expect(water).toHaveFocus();
		for (const button of [water, other]) {
			expect(button).not.toHaveAttribute('aria-disabled', 'true');
			expect(button).not.toBeDisabled();
		}
	});

	it('Rated by: a kind picked is pending until its values are in; no number is carried', async () => {
		const ws = testWorkspace(equipmentProject());
		ws.nav.jumpTo('E1');
		render(WorkspaceView, { workspace: ws });
		const ratedBy = screen.getByRole('combobox', { name: 'Rated by' });
		await fireEvent.change(ratedBy, { target: { value: 'Cv' } });
		const cv = screen.getByRole('textbox', { name: 'Cv' });
		expect(cv).toHaveValue('');
		expect(
			screen.getByText('Enter the Cv to use it; until then the rated point applies.')
		).toBeInTheDocument();
		// The warning describes the field to enter and the choice that made it pending.
		const pending = /Enter the Cv to use it; until then the rated point applies\./;
		expect(cv).toHaveAccessibleDescription(pending);
		expect(ratedBy).toHaveAccessibleDescription(pending);
		expect(ratingOf(ws.project)).toEqual({
			kind: 'point',
			pressureLoss: 25000,
			flow: 0.01,
			density: 999.1
		});
		await type(cv, '80');
		expect(ratingOf(ws.project)).toEqual({ kind: 'Cv', value: 80 });
		expect(screen.queryByText(/until then/)).toBeNull();
		expect(screen.getByRole('textbox', { name: 'Cv' })).not.toHaveAccessibleDescription(
			/until then/
		);
		expect(ratedBy).not.toHaveAccessibleDescription(/until then/);
		await fireEvent.change(ratedBy, { target: { value: 'Kv' } });
		expect(screen.getByRole('textbox', { name: 'Kv' })).toHaveValue('');
		expect(
			screen.getByText('Enter the Kv to use it; until then the Cv applies.')
		).toBeInTheDocument();
		await fireEvent.change(ratedBy, { target: { value: 'point' } });
		expect(screen.getByRole('textbox', { name: 'Rated pressure drop (kPa)' })).toHaveValue('');
		const points =
			'Enter the rated pressure drop, rated flow and rated fluid density to use them; until then the Cv applies.';
		expect(screen.getByText(points)).toBeInTheDocument();
		for (const name of [
			'Rated pressure drop (kPa)',
			'Rated flow (L/s)',
			'Rated fluid density (kg/m³)'
		]) {
			expect(screen.getByRole('textbox', { name }), name).toHaveAccessibleDescription(
				new RegExp(points.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
			);
		}
		await fireEvent.change(ratedBy, { target: { value: 'Cv' } });
		expect(screen.getByRole('textbox', { name: 'Cv' })).toHaveValue('80');
	});

	it('in a scenario: a value is a change at its field; a change of kind one change at the group', async () => {
		const ws = testWorkspace(
			withScenarios(equipmentProject(), [{ id: 'S1', name: 'Dirty strainer', overrides: [] }])
		);
		ws.setCase('S1');
		ws.nav.jumpTo('E1');
		render(WorkspaceView, { workspace: ws });
		const drop = screen.getByRole('textbox', { name: 'Rated pressure drop (kPa)' });
		expect(drop).not.toHaveAttribute('readonly');
		await type(drop, '70');
		const overrides = () => ws.store.project.scenarios![0]!.overrides ?? [];
		expect(overrides()).toEqual([
			{ kind: 'component', componentId: 'E1', field: 'rating.pressureLoss', value: 70000 }
		]);
		expect(drop).toHaveAccessibleDescription(/Changed in this scenario. Base value 25 kPa./);
		expect(screen.getAllByText('Changed')).toHaveLength(1);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Reset Rated pressure drop to the base value, 25 kPa' })
		);
		expect(overrides()).toEqual([]);

		// Another datasheet, by its Cv: one change of the whole rating, noted once at the group.
		await fireEvent.change(screen.getByRole('combobox', { name: 'Rated by' }), {
			target: { value: 'Cv' }
		});
		await type(screen.getByRole('textbox', { name: 'Cv' }), '80');
		expect(overrides()).toEqual([
			{ kind: 'component', componentId: 'E1', field: 'rating', value: { kind: 'Cv', value: 80 } }
		]);
		expect(screen.getAllByText('Changed')).toHaveLength(1);
		expect(screen.getByRole('textbox', { name: 'Cv' })).toHaveAccessibleDescription(
			/Changed in this scenario. Base value 25 kPa at 10 L\/s, 999.1 kg\/m³./
		);
		await fireEvent.click(
			screen.getByRole('button', {
				name: 'Reset Rating to the base value, 25 kPa at 10 L/s, 999.1 kg/m³'
			})
		);
		expect(overrides()).toEqual([]);
		expect(ratingOf(ws.project)).toEqual({
			kind: 'point',
			pressureLoss: 25000,
			flow: 0.01,
			density: 999.1
		});
	});
});
