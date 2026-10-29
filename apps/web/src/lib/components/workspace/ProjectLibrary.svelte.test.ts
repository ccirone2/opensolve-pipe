/**
 * The project library dialog (CLAUDE.md D22; proposal project-library.md §6.1, §7.4): a new
 * entry asks for what has no default at its field, and is added as one undo step; an edit
 * reaches every element that refers to the entry (references, not copies); delete is refused
 * while anything uses the entry, naming the first user, its reason scrolled into view; a list
 * holds at most 100 entries, and a full list offers no new one, saying why; in a scenario the
 * library is read-only. Test inputs (made up): the entries of testing/helpers.ts libraryProject,
 * lists of numbered entries, and a 78 mm bore.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { IsolationValve, PipeSpec, Project, ResistanceSpec } from '$lib/api/types';
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

/** n made-up pipe specs, PS1... (custom: a bore and roughness of their own). */
const manySpecs = (n: number): PipeSpec[] =>
	Array.from({ length: n }, (_, i) => ({
		id: `PS${i + 1}`,
		name: `Spec ${i + 1}`,
		source: 'Test input: a made-up bore',
		materialId: 'custom',
		innerDiameter: 0.05,
		roughness: 1e-5
	}));

/** n made-up Cv entries, RS1... */
const manyEntries = (n: number): ResistanceSpec[] =>
	Array.from({ length: n }, (_, i) => ({
		id: `RS${i + 1}`,
		name: `Entry ${i + 1}`,
		source: 'Test input: a made-up Cv',
		kind: 'Cv',
		value: 100
	}));

const PIPE_LIMIT =
	'A project holds at most 100 pipe specs. Delete one that nothing uses to add another.';
const RESISTANCE_LIMIT =
	'A project holds at most 100 resistance entries. Delete one that nothing uses to add another.';

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

	it("a card lists its users by name once its list is opened, and a closed card's list is not built", async () => {
		// libraryProject's users, and a scenario change of each kind (made up).
		const project = libraryProject();
		project.scenarios = [
			{
				id: 'S1',
				name: 'Lined',
				overrides: [
					{
						kind: 'pipe',
						connectionId: 'L1',
						pipeIndex: 1,
						field: 'spec',
						value: { specId: 'PS1' }
					},
					{
						kind: 'component',
						componentId: 'V1',
						field: 'resistance',
						value: { kind: 'library', id: 'RS2' }
					}
				]
			}
		];
		setup(project);
		const dialog = await openLibrary();
		const card = (name: RegExp) => dialog.getByRole('region', { name });
		const items = (region: HTMLElement) =>
			within(region)
				.queryAllByRole('listitem')
				.map((li) => li.textContent?.trim());
		/** Open a card's list from its summary, as a user does ("Used by 2"). */
		const open = async (region: HTMLElement) => {
			await fireEvent.click(within(region).getByText(/^Used by \d+$/));
			await vi.waitFor(() => expect(within(region).queryAllByRole('listitem')).not.toEqual([]));
		};

		// Closed, a card says its count alone: at the schema's largest network the lists of every
		// card took 0.3 s on a desktop and 2 s on a phone each time the dialog opened or saved.
		const spec = card(/^NPS 4 measured/);
		expect(within(spec).getByText('Used by 2')).toBeInTheDocument();
		expect(items(spec)).toEqual([]);
		await open(spec);
		expect(items(spec)).toEqual([
			'Pipe 1 of Upper tank → Gate valve V1',
			'Scenario Lined, change 1'
		]);
		expect(items(card(/^Lined 80 mm/))).toEqual([]);

		await fireEvent.click(dialog.getByRole('tab', { name: 'Resistances (2)' }));
		const gate = card(/^Gate, open/);
		expect(within(gate).getByText('Used by 2')).toBeInTheDocument();
		expect(items(gate)).toEqual([]);
		await open(gate);
		// The test library has no fittings: their names are the app's own, as the fittings editor's.
		expect(items(gate)).toEqual([
			'Gate valve V1',
			'Fitting 2 (Custom fitting (enter K)) of Upper tank → Gate valve V1'
		]);
		const elbow = card(/^Elbow \(K\)/);
		expect(items(elbow)).toEqual([]);
		await open(elbow);
		expect(items(elbow)).toEqual([
			'Fitting 1 (90° elbow, long radius) of Upper tank → Gate valve V1',
			'Scenario Lined, change 2'
		]);

		// An open list stays open, and current, across a change of tab and an edit to the project.
		await fireEvent.click(dialog.getByRole('tab', { name: 'Pipe specs (2)' }));
		await fireEvent.click(dialog.getByRole('button', { name: 'Edit NPS 4 measured' }));
		await type(dialog.getByRole('textbox', { name: 'Name' }), 'NPS 4 site');
		await fireEvent.click(dialog.getByRole('button', { name: 'Save' }));
		await tick();
		expect(items(card(/^NPS 4 site/))).toEqual([
			'Pipe 1 of Upper tank → Gate valve V1',
			'Scenario Lined, change 1'
		]);
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

	it('a refused delete scrolls its reason into view, the focus staying on Delete', async () => {
		// On a phone the reason, drawn below Delete, was under the dialog's footer.
		const scrolled = vi.fn();
		const original = Element.prototype.scrollIntoView;
		Element.prototype.scrollIntoView = scrolled;
		try {
			setup(libraryProject());
			const dialog = await openLibrary();
			const remove = dialog.getByRole('button', { name: 'Delete NPS 4 measured' });
			remove.focus();
			await fireEvent.click(remove);
			const alert = dialog.getByRole('alert');
			expect(alert).toHaveTextContent(/^Not deleted: Pipe 1 of Upper tank → Gate valve V1/);
			await vi.waitFor(() => expect(scrolled).toHaveBeenCalledWith({ block: 'nearest' }));
			expect(scrolled.mock.contexts.at(-1)).toBe(alert);
			expect(remove).toHaveFocus();
		} finally {
			Element.prototype.scrollIntoView = original;
		}
	});

	it('a full list offers no new entry and says why; one below the limit takes one more', async () => {
		const project = libraryProject();
		project.pipeLibrary = manySpecs(100);
		project.resistanceLibrary = manyEntries(99);
		const ws = setup(project);
		const dialog = await openLibrary();
		expect(dialog.getByRole('tab', { name: 'Pipe specs (100)' })).toHaveAttribute(
			'aria-selected',
			'true'
		);
		expect(dialog.getByText(PIPE_LIMIT)).toBeInTheDocument();
		const newSpec = dialog.getByRole('button', { name: 'New pipe spec' });
		expect(newSpec).toHaveAttribute('aria-disabled', 'true');
		expect(newSpec).toHaveAccessibleDescription(PIPE_LIMIT);
		await fireEvent.click(newSpec);
		expect(dialog.queryByRole('region', { name: 'New pipe spec' })).toBeNull();

		// 99 entries: one more is added, and the list is then full.
		await fireEvent.click(dialog.getByRole('tab', { name: 'Resistances (99)' }));
		expect(dialog.queryByText(/^A project holds at most/)).toBeNull();
		const newEntry = dialog.getByRole('button', { name: 'New resistance entry' });
		expect(newEntry).not.toHaveAttribute('aria-disabled', 'true');
		await fireEvent.click(newEntry);
		const form = within(dialog.getByRole('region', { name: 'New resistance entry' }));
		await type(form.getByRole('textbox', { name: 'Name' }), 'Gate, vendor B');
		await type(form.getByRole('textbox', { name: 'Cv' }), '250');
		await type(form.getByRole('textbox', { name: 'Source' }), 'Test input');
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		expect(ws.store.project.resistanceLibrary).toHaveLength(100);
		await tick();
		expect(dialog.getByRole('tab', { name: 'Resistances (100)' })).toBeInTheDocument();
		expect(dialog.getByText(RESISTANCE_LIMIT)).toBeInTheDocument();
		expect(dialog.getByRole('button', { name: 'New resistance entry' })).toHaveAttribute(
			'aria-disabled',
			'true'
		);
	});

	it("a picker's new entry on a full list opens the list, saying why, not a form", async () => {
		const project = libraryProject();
		project.pipeLibrary = manySpecs(100);
		const ws = setup(project);
		const use = vi.fn((p: Project) => p);
		ws.openLibrary({ list: 'pipe', create: true, use: { label: 'pipe 1 of A → B', apply: use } });
		const dialog = within(await screen.findByRole('dialog', { name: 'Project library' }));
		expect(dialog.queryByRole('region', { name: 'New pipe spec' })).toBeNull();
		expect(dialog.getByText(PIPE_LIMIT)).toBeInTheDocument();
		expect(use).not.toHaveBeenCalled();
	});

	it("a new entry saved once its list is full says the limit, not the schema's words", async () => {
		const project = libraryProject();
		project.pipeLibrary = manySpecs(99);
		const ws = setup(project);
		const dialog = await openLibrary();
		await fireEvent.click(dialog.getByRole('button', { name: 'New pipe spec' }));
		const form = within(dialog.getByRole('region', { name: 'New pipe spec' }));
		await type(form.getByRole('textbox', { name: 'Name' }), 'NPS 3 measured');
		await type(form.getByRole('textbox', { name: 'Inner diameter (mm)' }), '78');
		await type(form.getByRole('textbox', { name: 'Source' }), 'Test input');
		// Meanwhile the list fills (another path into the project).
		const filled = ws.store.update(
			(p) => ({ ...p, pipeLibrary: manySpecs(100) }),
			'fill the pipe specs'
		);
		expect(filled.ok).toBe(true);
		await fireEvent.click(dialog.getByRole('button', { name: 'Add' }));
		const refused = form.getByRole('alert');
		expect(refused).toHaveTextContent(/^Not saved:/);
		expect(refused).toHaveTextContent(/A project holds at most 100 pipe specs\.$/);
		expect(ws.store.project.pipeLibrary).toHaveLength(100);
		expect(ws.store.undoLabel).toBe('fill the pipe specs');
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
