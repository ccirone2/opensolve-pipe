/**
 * The project library dialog (CLAUDE.md D21; proposal project-library.md §6.1, §7.4): a new
 * entry asks for what has no default at its field, and is added as one undo step; an edit
 * reaches every element that refers to the entry (references, not copies); delete is refused
 * while anything uses the entry, naming the first user; in a scenario the library is read-only.
 * Test inputs (made up): the entries of testing/helpers.ts libraryProject, and a 78 mm bore.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it } from 'vitest';
import type { IsolationValve, Project } from '$lib/api/types';
import { libraryProject } from '$lib/testing/helpers';
import { TEST_LIBRARY as LIBRARY } from '$lib/testing/library';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { componentById } from '$lib/utils/graph';
import WorkspaceView from './Workspace.svelte';

const NAME_ERROR = 'Enter a name: results and lists show the entry by it.';
const SOURCE_ERROR =
	'Enter where the values come from (a standard and its table, a datasheet, a measurement): every result that uses the entry cites it.';

function setup(project: Project = pumpTransferExample()) {
	const ws = testWorkspace(project, { library: { getLibrary: () => Promise.resolve(LIBRARY) } });
	render(WorkspaceView, { workspace: ws });
	return ws;
}

async function openLibrary() {
	await fireEvent.click(screen.getByRole('button', { name: 'Project library' }));
	return within(await screen.findByRole('dialog', { name: 'Project library' }));
}

/** Type into a field and store it, as leaving the field does. */
async function type(input: HTMLElement, text: string) {
	await fireEvent.input(input, { target: { value: text } });
	await fireEvent.change(input);
}

const alerts = (scope: ReturnType<typeof within>) =>
	scope.queryAllByRole('alert').map((a: HTMLElement) => a.textContent?.trim());

describe('ProjectLibrary', () => {
	it('a new pipe spec asks for its name, bore and source at their fields; Add is one undo step', async () => {
		const ws = setup();
		const dialog = await openLibrary();
		expect(dialog.getByRole('tab', { name: 'Pipe specs (0)' })).toHaveAttribute(
			'aria-selected',
			'true'
		);
		await fireEvent.click(dialog.getByRole('button', { name: 'New pipe spec' }));
		const form = within(dialog.getByRole('region', { name: 'New pipe spec' }));
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(alerts(form)).toEqual([NAME_ERROR, 'Enter the inner diameter.', SOURCE_ERROR]);
		expect(ws.store.project.pipeLibrary).toBeUndefined();

		// Each error goes as its value is typed (not when the field stores it).
		await fireEvent.input(form.getByRole('textbox', { name: 'Name' }), {
			target: { value: 'NPS 3 measured' }
		});
		expect(alerts(form)).toEqual(['Enter the inner diameter.', SOURCE_ERROR]);
		await fireEvent.change(form.getByRole('textbox', { name: 'Name' }));
		await type(form.getByRole('textbox', { name: 'Inner diameter (mm)' }), '78');
		await type(form.getByRole('textbox', { name: 'Source' }), 'Test input: a made-up bore');
		expect(alerts(form)).toEqual([]);
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));

		expect(ws.store.project.pipeLibrary).toEqual([
			{
				id: 'PS1',
				name: 'NPS 3 measured',
				source: 'Test input: a made-up bore',
				materialId: 'carbon_steel',
				innerDiameter: 0.078
			}
		]);
		expect(ws.store.undoLabel).toBe('add pipe spec NPS 3 measured');
		await tick();
		const card = within(dialog.getByRole('region', { name: /^NPS 3 measured/ }));
		expect(card.getByRole('heading', { name: /^NPS 3 measured/ })).toHaveFocus();
		expect(card.getByText('Source: Test input: a made-up bore')).toBeInTheDocument();
		expect(card.getByText('Not used.')).toBeInTheDocument();

		// Undo removes the spec and the list with it: the project is as before.
		ws.undo();
		expect('pipeLibrary' in ws.store.project).toBe(false);
	});

	it('a custom spec needs its roughness, and a rule the API publishes is said before saving', async () => {
		const ws = setup();
		const dialog = await openLibrary();
		await fireEvent.click(dialog.getByRole('button', { name: 'New pipe spec' }));
		const form = within(dialog.getByRole('region', { name: 'New pipe spec' }));
		await fireEvent.change(form.getByRole('combobox', { name: 'Material' }), {
			target: { value: 'custom' }
		});
		await type(form.getByRole('textbox', { name: 'Name' }), 'Lined');
		await type(form.getByRole('textbox', { name: 'Inner diameter (mm)' }), '78');
		await type(form.getByRole('textbox', { name: 'Source' }), 'Test input');
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(alerts(form)).toEqual(['Enter the roughness: a custom pipe spec has no cited one.']);

		await type(form.getByRole('textbox', { name: 'Roughness (mm)' }), '0.0015');
		await type(form.getByRole('textbox', { name: 'Outer diameter (mm)' }), '70');
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		const refused = form.getByRole('alert');
		expect(refused).toHaveTextContent(/^Not saved:/);
		expect(refused).toHaveTextContent(/inner diameter must be below its outer diameter/i);
		expect(ws.store.project.pipeLibrary).toBeUndefined();

		await type(form.getByRole('textbox', { name: 'Outer diameter (mm)' }), '89');
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(ws.store.project.pipeLibrary).toEqual([
			{
				id: 'PS1',
				name: 'Lined',
				source: 'Test input',
				materialId: 'custom',
				innerDiameter: 0.078,
				roughness: 1.5e-6,
				outerDiameter: 0.089
			}
		]);
	});

	it('an edit to an entry reaches every element that refers to it', async () => {
		const ws = setup(libraryProject());
		const dialog = await openLibrary();
		await fireEvent.click(dialog.getByRole('tab', { name: 'Resistances (2)' }));
		const card = within(dialog.getByRole('region', { name: /^Gate, open/ }));
		expect(card.getByText('Cv 900')).toBeInTheDocument();
		// RS1 is the valve's and the custom fitting's.
		expect(card.getByText('Used by 2')).toBeInTheDocument();
		await fireEvent.click(card.getByRole('button', { name: 'Edit Gate, open' }));
		const form = within(dialog.getByRole('region', { name: 'Edit resistance entry RS1' }));
		expect(form.getByText('Used by 2: saving changes every one of them.')).toBeInTheDocument();
		await type(form.getByRole('textbox', { name: 'Cv' }), '1200');
		await fireEvent.click(dialog.getByRole('button', { name: 'Save' }));

		const project = ws.store.project;
		expect(project.resistanceLibrary?.find((e) => e.id === 'RS1')?.value).toBe(1200);
		// The elements still refer to the entry: nothing was copied onto them.
		expect((componentById(project, 'V1') as IsolationValve).resistance).toEqual({
			kind: 'library',
			id: 'RS1'
		});
		expect(project.connections[0]?.piping.fittings[1]?.resistanceId).toBe('RS1');
		expect(ws.store.undoLabel).toBe('edit resistance entry Gate, open');
		await tick();
		expect(dialog.getByRole('button', { name: 'Edit Gate, open' })).toBeInTheDocument();
	});

	it('a change of kind clears the value, and a K asks for the bore it is stated at', async () => {
		const ws = setup();
		const dialog = await openLibrary();
		await fireEvent.click(dialog.getByRole('tab', { name: 'Resistances (0)' }));
		await fireEvent.click(dialog.getByRole('button', { name: 'New resistance entry' }));
		const form = within(dialog.getByRole('region', { name: 'New resistance entry' }));
		await type(form.getByRole('textbox', { name: 'Cv' }), '5');
		await fireEvent.change(form.getByRole('combobox', { name: 'Given as' }), {
			target: { value: 'K' }
		});
		expect(form.getByRole('textbox', { name: 'K' })).toHaveValue('');
		await type(form.getByRole('textbox', { name: 'Name' }), 'Butterfly, open');
		await type(form.getByRole('textbox', { name: 'K' }), '0.3');
		await type(form.getByRole('textbox', { name: 'Source' }), 'Test input');
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(alerts(form)).toEqual([
			'Enter the bore the K is stated at: a K means nothing without the velocity it is on.'
		]);
		await type(form.getByRole('textbox', { name: 'Stated at bore (mm)' }), '90');
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(ws.store.project.resistanceLibrary).toEqual([
			{
				id: 'RS1',
				name: 'Butterfly, open',
				source: 'Test input',
				kind: 'K',
				value: 0.3,
				referenceDiameter: 0.09
			}
		]);
	});

	it('refuses to delete an entry in use, naming the first user; deletes one nothing uses', async () => {
		const ws = setup(libraryProject());
		const dialog = await openLibrary();
		await fireEvent.click(dialog.getByRole('button', { name: 'Delete NPS 4 measured' }));
		expect(dialog.getByRole('alert')).toHaveTextContent(
			'Not deleted: Pipe 1 of Upper tank → Gate valve V1 uses this spec. An entry can be deleted once nothing uses it.'
		);
		expect(ws.store.project.pipeLibrary?.map((s) => s.id)).toEqual(['PS1', 'PS2']);
		expect(ws.store.canUndo).toBe(false);

		await fireEvent.click(dialog.getByRole('button', { name: 'Delete Lined 80 mm' }));
		expect(ws.store.project.pipeLibrary?.map((s) => s.id)).toEqual(['PS1']);
		expect(dialog.queryByRole('alert')).toBeNull();
		expect(dialog.getByRole('status')).toHaveTextContent(
			'Deleted pipe spec Lined 80 mm. Undo brings it back.'
		);
		expect(dialog.getByRole('tab', { name: 'Pipe specs (1)' })).toBeInTheDocument();
	});

	it('is read-only in a scenario, and says so', async () => {
		const project = libraryProject();
		project.scenarios = [{ id: 'S1', name: 'Winter', overrides: [] }];
		const ws = setup(project);
		ws.setCase('S1');
		await tick();
		const dialog = await openLibrary();
		expect(
			dialog.getByText(/^The library is the same in every case: switch to the base case/)
		).toBeInTheDocument();
		expect(dialog.queryByRole('button', { name: /^Edit / })).toBeNull();
		expect(dialog.queryByRole('button', { name: /^Delete / })).toBeNull();
		expect(dialog.queryByRole('button', { name: 'New pipe spec' })).toBeNull();
		expect(dialog.getByText('Source: test input: a bore measured on site')).toBeInTheDocument();
	});

	it('in a scenario an entry asked for is shown in its list, never in a form', async () => {
		const project = libraryProject();
		project.scenarios = [{ id: 'S1', name: 'Winter', overrides: [] }];
		const ws = setup(project);
		ws.setCase('S1');
		ws.openLibrary({ list: 'resistance', edit: 'RS2' });
		const dialog = within(await screen.findByRole('dialog', { name: 'Project library' }));
		expect(dialog.queryByRole('region', { name: /^Edit / })).toBeNull();
		expect(dialog.getByRole('tab', { name: 'Resistances (2)' })).toHaveAttribute(
			'aria-selected',
			'true'
		);
		await tick();
		expect(dialog.getByRole('heading', { name: /^Elbow \(K\)/ })).toHaveFocus();
	});

	it("a blank roughness is the material's at the bore, shown where the pipe library has that bore", async () => {
		setup();
		const dialog = await openLibrary();
		await fireEvent.click(dialog.getByRole('button', { name: 'New pipe spec' }));
		const form = within(dialog.getByRole('region', { name: 'New pipe spec' }));
		const roughness = form.getByRole('textbox', { name: 'Roughness (mm)' });
		const hint = () => document.getElementById(roughness.getAttribute('aria-describedby') ?? '');
		// A bore the library does not hold: the server evaluates the correlation there.
		await type(form.getByRole('textbox', { name: 'Inner diameter (mm)' }), '80');
		expect(hint()).toHaveTextContent(/which the calculation server evaluates when solving/);
		// NPS 4 schedule 40's bore in the test library: its per-size roughness.
		await type(form.getByRole('textbox', { name: 'Inner diameter (mm)' }), '102.26');
		expect(hint()).toHaveTextContent(
			"Blank: the material's cited roughness at this bore, 0.03501 mm (as the library's NPS 4 schedule 40; test roughness source)."
		);
	});

	it("a valve's New entry… opens the form, and the entry saved is used there in one step", async () => {
		const ws = testWorkspace(pumpTransferExample(), {
			library: { getLibrary: () => Promise.resolve(LIBRARY) }
		});
		ws.nav.jumpTo('V1');
		render(WorkspaceView, { workspace: ws });
		const select = screen.getByRole('combobox', { name: 'Resistance given as' });
		await fireEvent.change(select, { target: { value: 'new-entry' } });
		await tick();
		// The choice goes back to what the valve holds until the entry exists.
		expect(select).toHaveValue('default');
		const dialog = within(await screen.findByRole('dialog', { name: 'Project library' }));
		const form = within(dialog.getByRole('region', { name: 'New resistance entry' }));
		await type(form.getByRole('textbox', { name: 'Name' }), 'Gate, open');
		await type(form.getByRole('textbox', { name: 'Cv' }), '250');
		await type(form.getByRole('textbox', { name: 'Source' }), 'Test input');
		await fireEvent.click(
			dialog.getByRole('button', { name: 'Save and use for Discharge isolation valve' })
		);
		expect(screen.queryByRole('dialog', { name: 'Project library' })).toBeNull();

		const valve = () => componentById(ws.store.project, 'V1') as IsolationValve;
		expect(valve().resistance).toEqual({ kind: 'library', id: 'RS1' });
		expect(ws.store.project.resistanceLibrary?.map((e) => e.id)).toEqual(['RS1']);
		await tick();
		expect(screen.getByRole('combobox', { name: 'Resistance given as' })).toHaveValue('entry:RS1');
		expect(screen.getByText('Source: Test input')).toBeInTheDocument();
		ws.undo();
		expect(valve().resistance).toBeUndefined();
		expect('resistanceLibrary' in ws.store.project).toBe(false);
	});
});
