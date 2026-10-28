/**
 * The orifice plate in the Build panel (proposal orifice-plate.md §6 W1-W3): every path that
 * creates one asks for its bore first (no source gives a default bore), the form enters the bore
 * in the display unit of diameters and shows β against the inlet pipe's inner diameter read-only
 * (four states before it is known, and a warning when the bore is not smaller than the pipe's),
 * the discharge coefficient is ISO 5167-2's by default or an entered C (user data, defined in its
 * hint; a choice picked with no C yet keeps ISO's, with a warning), the taps are optional and the
 * same in every case, and in a scenario the bore and the C are scenario values with Changed and
 * Reset. Bores and C values are made-up test inputs; the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { Project } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { orificeProject } from '$lib/testing/helpers';
import { TEST_LIBRARY } from '$lib/testing/library';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { createComponent, createEmptyProject } from '$lib/utils/factory';
import { withScenarios } from '$lib/utils/scenarios';
import { IMPERIAL_UNITS, toSI } from '$lib/utils/units';

const LABEL = 'Orifice plate (ISO 5167-2)';
const GROUP = 'Orifice plates: restriction orifices, flow meters';
const REQUIRED = 'Enter the orifice bore: it has no default.';
const library = { getLibrary: () => Promise.resolve(TEST_LIBRARY) };

function current(): string {
	const build = screen.getByRole('region', { name: 'Build' });
	return within(build).getAllByRole('heading', { level: 2 })[0]?.textContent?.trim() ?? '';
}

async function type(input: HTMLElement, text: string) {
	await fireEvent.input(input, { target: { value: text } });
	await fireEvent.change(input);
}

function plateOf(project: Project, id = 'O1') {
	const plate = project.components.find((c) => c.id === id);
	return plate?.type === 'orifice' ? plate : undefined;
}

describe('adding an orifice plate', () => {
	it('after a reservoir: asks for the bore first, then adds it on ISO 5167-2, without taps', async () => {
		const empty = createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' });
		const ws = testWorkspace({ ...empty, components: [createComponent('reservoir', empty)] });
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add after' }));
		const dialog = await screen.findByRole('dialog', { name: 'Add after Reservoir R1' });
		const kinds = within(dialog).getByRole('combobox', { name: 'Component' });
		const option = within(kinds).getByRole('option', { name: LABEL });
		expect(option.closest('optgroup')).toHaveAttribute('label', GROUP);
		await fireEvent.change(kinds, { target: { value: 'orifice' } });
		const bore = within(dialog).getByRole('textbox', { name: 'Bore diameter (mm)' });
		expect(bore).toHaveValue('');
		expect(bore).toHaveAccessibleDescription(
			"The diameter of the plate's hole (ISO 5167-2's d) at the flowing temperature; smaller than the inlet pipe's inner diameter."
		);

		// No bore is cited as a default, so none is invented: Add says it is missing.
		const add = within(dialog).getByRole('button', { name: 'Add' });
		await fireEvent.click(add);
		expect(within(dialog).getByRole('alert')).toHaveTextContent(REQUIRED);
		expect(ws.project.components).toHaveLength(1);
		// The error goes as soon as the bore is typed (never on blur: Add stays under the pointer).
		await fireEvent.input(bore, { target: { value: '50' } });
		expect(within(dialog).queryByRole('alert')).toBeNull();
		await fireEvent.change(bore);
		await fireEvent.click(add);

		expect(screen.queryByRole('dialog')).toBeNull();
		expect(current()).toBe('Orifice O1');
		// SI exactly, and nothing else entered: ISO 5167-2's C, no taps (a restriction orifice).
		expect(plateOf(ws.project)).toEqual({
			id: 'O1',
			name: 'Orifice O1',
			elevation: 0,
			type: 'orifice',
			boreDiameter: toSI(50, 'mm'),
			ports: [
				{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
				{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
			]
		});
		expect(ws.project.connections).toMatchObject([
			{ fromComponentId: 'R1', toComponentId: 'O1', toPortId: 'inlet' }
		]);
	});

	it('before a pump (inserted): the bore is asked for there too, the plate oriented with the flow', async () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.nav.jumpTo('P1');
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Add before' }));
		const dialog = await screen.findByRole('dialog', { name: /^Add before/ });
		const kinds = within(dialog).getByRole('combobox', { name: 'Component' });
		await fireEvent.change(kinds, { target: { value: 'orifice' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(within(dialog).getByRole('alert')).toHaveTextContent(REQUIRED);
		expect(ws.project.components).toHaveLength(4);
		await type(within(dialog).getByRole('textbox', { name: 'Bore diameter (mm)' }), '60');
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(plateOf(ws.project)?.boreDiameter).toBe(toSI(60, 'mm'));
		expect(ws.project.connections.find((c) => c.toComponentId === 'O1')).toMatchObject({
			fromComponentId: 'R1',
			toPortId: 'inlet'
		});
		expect(ws.project.connections.find((c) => c.fromComponentId === 'O1')).toMatchObject({
			fromPortId: 'outlet',
			toComponentId: 'P1'
		});
	});

	it('as the first component and in the Piping view: the bore is asked for in both', async () => {
		const ws = testWorkspace(createEmptyProject({ id: 'p1', now: '2026-01-01T00:00:00Z' }));
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'First component' }), {
			target: { value: 'orifice' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getByRole('alert')).toHaveTextContent(REQUIRED);
		expect(ws.project.components).toEqual([]);
		await type(build.getByRole('textbox', { name: 'Bore diameter (mm)' }), '40');
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(current()).toBe('Orifice O1');
		expect(plateOf(ws.project)?.boreDiameter).toBe(toSI(40, 'mm'));

		await fireEvent.click(build.getByRole('button', { name: 'Next: connect outlet' }));
		await fireEvent.change(build.getByRole('combobox', { name: 'Add a component here' }), {
			target: { value: 'orifice' }
		});
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(build.getByRole('alert')).toHaveTextContent(REQUIRED);
		expect(ws.project.components).toHaveLength(1);
		await type(build.getByRole('textbox', { name: 'Bore diameter (mm)' }), '45');
		await fireEvent.click(build.getByRole('button', { name: 'Add' }));
		expect(ws.project.components).toHaveLength(2);
		expect(plateOf(ws.project, 'O2')?.boreDiameter).toBe(toSI(45, 'mm'));
	});
});

describe('OrificeForm', () => {
	it('names the bore in the display unit of diameters and stores what is typed exactly in SI', async () => {
		const project = orificeProject();
		project.settings.units = { ...IMPERIAL_UNITS };
		const ws = testWorkspace(project);
		ws.nav.jumpTo('O1');
		render(WorkspaceView, { workspace: ws });
		expect(current()).toBe('Bypass orifice');
		const bore = screen.getByRole('textbox', { name: 'Bore diameter (in)' });
		expect(bore).toHaveValue(String(Number((0.05 / 0.0254).toPrecision(6))));
		await type(bore, '2');
		expect(plateOf(ws.project)?.boreDiameter).toBe(toSI(2, 'in'));
		expect(screen.getByRole('button', { name: 'Undo change bore diameter' })).toBeEnabled();
		// The schema's bounds: (0, 10] m.
		await type(bore, '0');
		expect(bore).toHaveAttribute('aria-invalid', 'true');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be greater than 0 in.');
		expect(plateOf(ws.project)?.boreDiameter).toBe(toSI(2, 'in'));
	});

	it('shows β against the inlet pipe once the library loads, and warns at β ≥ 1', async () => {
		const ws = testWorkspace(orificeProject(), { library });
		ws.nav.jumpTo('O1');
		render(WorkspaceView, { workspace: ws });
		const bore = screen.getByRole('textbox', { name: 'Bore diameter (mm)' });
		const line =
			'β = d ÷ D = 0.4889, with D = 102.3 mm, the inner diameter of the inlet pipe (NPS 4, Sch 40)';
		expect(await screen.findByText(line)).toBeInTheDocument();
		// Read-only, and part of the bore's description.
		expect(screen.getByText(line).tagName).toBe('OUTPUT');
		expect(bore).toHaveAccessibleDescription(
			new RegExp(line.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
		);
		await type(bore, '110');
		const warning = screen.getByText(
			"β ≥ 1: the bore is not smaller than the inlet pipe's (102.3 mm); the solve refuses it."
		);
		expect(warning).toHaveClass('text-amber-800');
		// Stored all the same: the solve's topology check refuses it, with the reason.
		expect(plateOf(ws.project)?.boreDiameter).toBe(0.11);
	});

	it('says when β will be shown: before the library loads, and with the inlet not connected', async () => {
		const ws = testWorkspace(orificeProject()); // the library fails to load (501)
		ws.nav.jumpTo('O1');
		render(WorkspaceView, { workspace: ws });
		expect(await screen.findByText('β is shown once the pipe library loads.')).toBeInTheDocument();
		const open = orificeProject();
		open.connections = open.connections.slice(1);
		const alone = testWorkspace(open, { library });
		alone.nav.jumpTo('O1');
		render(WorkspaceView, { workspace: alone });
		expect(await screen.findByText('β is shown once the inlet is connected.')).toBeInTheDocument();
	});

	it("enters a C as the user's value, defined in its hint; a choice with no C keeps ISO's, with a warning", async () => {
		const ws = testWorkspace(orificeProject());
		ws.nav.jumpTo('O1');
		render(WorkspaceView, { workspace: ws });
		const source = screen.getByRole('combobox', { name: 'Discharge coefficient' });
		expect(source).toHaveValue('iso');
		expect(within(source).getByRole('option', { selected: true })).toHaveTextContent(
			'ISO 5167-2 (Reader-Harris/Gallagher), the default'
		);
		expect(screen.queryByRole('textbox', { name: 'Entered C' })).toBeNull();
		await fireEvent.change(source, { target: { value: 'entered' } });
		const c = screen.getByRole('textbox', { name: 'Entered C' });
		expect(c).toHaveValue('');
		const pending = "Enter C to use it; until then ISO 5167-2's discharge coefficient applies.";
		expect(screen.getByText(pending)).toBeInTheDocument();
		// The warning describes the field to enter and the choice that made it pending.
		const pendingText = new RegExp(pending.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
		expect(c).toHaveAccessibleDescription(pendingText);
		expect(source).toHaveAccessibleDescription(pendingText);
		// The hint defines C (not the flow coefficient α).
		expect(c).toHaveAccessibleDescription(
			/^ISO 5167-2's discharge coefficient C at this plate's taps .* A datasheet's flow coefficient α = C ÷ √\(1 − β⁴\) is not C: enter α × √\(1 − β⁴\)\./
		);
		expect(plateOf(ws.project)).not.toHaveProperty('dischargeCoefficient');
		await type(c, '0.62');
		expect(plateOf(ws.project)?.dischargeCoefficient).toBe(0.62);
		expect(screen.queryByText(pending)).toBeNull();
		// The schema's bounds: (0, 1].
		await type(c, '1.2');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be at most 1.');
		expect(plateOf(ws.project)?.dischargeCoefficient).toBe(0.62);
		// Back to ISO's: the entered C is removed (undo restores it).
		await fireEvent.change(source, { target: { value: 'iso' } });
		expect(plateOf(ws.project)).not.toHaveProperty('dischargeCoefficient');
		expect(screen.queryByRole('textbox', { name: 'Entered C' })).toBeNull();
	});

	it('sets optional taps: none is a restriction orifice', async () => {
		const ws = testWorkspace(orificeProject());
		ws.nav.jumpTo('O1');
		render(WorkspaceView, { workspace: ws });
		const taps = screen.getByRole('combobox', { name: 'Pressure taps' });
		expect(taps).toHaveValue('none');
		expect(
			within(taps)
				.getAllByRole('option')
				.map((o) => o.textContent)
		).toEqual(['None (a restriction orifice)', 'Corner', 'Flange', 'D and D/2']);
		await fireEvent.change(taps, { target: { value: 'flange' } });
		expect(plateOf(ws.project)?.taps).toBe('flange');
		await fireEvent.change(taps, { target: { value: 'none' } });
		expect(plateOf(ws.project)).not.toHaveProperty('taps');
		expect(
			screen.getByText(
				/For a restriction orifice given by a pressure drop at a flow, a Cv or a Kv, use Equipment\./
			)
		).toBeInTheDocument();
	});

	it('in a scenario: the bore and the C are changes with their base values; the taps are locked', async () => {
		const ws = testWorkspace(
			withScenarios(orificeProject({ taps: 'flange' }), [
				{ id: 'S1', name: 'Calibrated', overrides: [] }
			])
		);
		ws.setCase('S1');
		ws.nav.jumpTo('O1');
		render(WorkspaceView, { workspace: ws });
		const overrides = () => ws.store.project.scenarios![0]!.overrides ?? [];
		const bore = screen.getByRole('textbox', { name: 'Bore diameter (mm)' });
		expect(bore).not.toHaveAttribute('readonly');
		await type(bore, '60');
		expect(overrides()).toEqual([
			{ kind: 'component', componentId: 'O1', field: 'boreDiameter', value: toSI(60, 'mm') }
		]);
		expect(bore).toHaveAccessibleDescription(/Changed in this scenario. Base value 50 mm./);
		await fireEvent.click(
			screen.getByRole('button', { name: 'Reset Bore diameter to the base value, 50 mm' })
		);
		expect(overrides()).toEqual([]);

		// A calibrated C: one change, noted once at the group, its base ISO 5167-2's.
		await fireEvent.change(screen.getByRole('combobox', { name: 'Discharge coefficient' }), {
			target: { value: 'entered' }
		});
		await type(screen.getByRole('textbox', { name: 'Entered C' }), '0.62');
		expect(overrides()).toEqual([
			{ kind: 'component', componentId: 'O1', field: 'dischargeCoefficient', value: 0.62 }
		]);
		expect(screen.getAllByText('Changed')).toHaveLength(1);
		expect(screen.getByRole('textbox', { name: 'Entered C' })).toHaveAccessibleDescription(
			/Changed in this scenario. Base value ISO 5167-2 \(default\)./
		);
		await fireEvent.click(
			screen.getByRole('button', {
				name: 'Reset Discharge coefficient to the base value, ISO 5167-2 (default)'
			})
		);
		expect(overrides()).toEqual([]);
		expect(plateOf(ws.project)).not.toHaveProperty('dischargeCoefficient');
		// The taps are installation, the same in every case.
		expect(screen.getByRole('textbox', { name: 'Pressure taps' })).toHaveAttribute('readonly');
	});
});
