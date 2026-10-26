/**
 * The pump's speed control in the Build panel (CLAUDE.md D11): flow control is entered as a
 * draft that is written in one undoable edit once the flow setpoint and the minimum speed are
 * both entered and valid, so the project and its link never hold a partial control or a value
 * the user did not enter; Fixed speed removes the control in one edit; Speed becomes Maximum
 * speed. The setpoints and speeds typed here are made-up test inputs.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { Project, Pump } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Workspace } from '$lib/state/workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { decodeProject, fragmentOf } from '$lib/utils/encoding';
import { pumpTransferExample } from '$lib/utils/examples';

function setup(edit?: (project: Project) => void) {
	const project = pumpTransferExample();
	edit?.(project);
	const ws = testWorkspace(project);
	ws.nav.jumpTo('P1');
	render(WorkspaceView, { workspace: ws });
	return ws;
}

const pumpOf = (project: Project) => project.components.find((c) => c.id === 'P1') as Pump;

/** The pump as the project's link holds it (the URL is written after a short delay). */
function linkedPump(ws: Workspace): Pump {
	ws.store.flush();
	return pumpOf(decodeProject(fragmentOf(ws.store.url)));
}

/**
 * The form control with this role and accessible name, queried by role inside its own field:
 * the element that holds its label, whose text is the name without the unit. Over the whole
 * workspace a role query computes the accessible name of every candidate, the pump curve's 20
 * point cells included, and jsdom recomputes those elements' styles after every DOM change:
 * about 150 ms a textbox query, which took tests past the 5 s timeout under CPU load. Inside
 * the field it takes a few milliseconds.
 */
function inField(role: 'textbox' | 'combobox', name: string): HTMLElement {
	const label = screen.getByText(name.replace(/ \([^)]*\)$/, ''), { selector: 'label' });
	return within(label.parentElement as HTMLElement).getByRole(role, { name });
}
const field = (name: string) => inField('textbox', name);
/** `field` once it appears (as findByRole is getByRole retried). */
const findField = (name: string) => waitFor(() => field(name));
const control = () => inField('combobox', 'Control');
/** The form's note about the draft (a live status), if shown. */
const draftNote = () =>
	screen.queryAllByRole('status').find((s) => /switch to flow control/.test(s.textContent ?? ''));

/** Type a value into a field and commit it (as leaving the field does). */
async function enter(name: string, value: string) {
	const input = field(name);
	await fireEvent.input(input, { target: { value } });
	await fireEvent.change(input);
	return input;
}

async function chooseControl(value: 'fixed' | 'flow') {
	await fireEvent.change(control(), { target: { value } });
}

describe('PumpForm: speed control', () => {
	// A worker's first workspace compiles the project schema's validator, and its first render,
	// queries and link decoding run cold: about 0.7 s, several times that under CPU load, which
	// the first test would otherwise pay inside its 5 s timeout. Pay it once, before the tests.
	beforeAll(() => {
		const ws = setup();
		control();
		field('Speed (%)');
		linkedPump(ws);
		cleanup();
	});

	it('holds flow control as a draft until it is complete and valid, then writes it in one edit', async () => {
		const ws = setup();
		expect(control()).toHaveValue('fixed');
		expect(field('Speed (%)')).toHaveValue('100');

		await chooseControl('flow');
		expect(control()).toHaveValue('flow');
		// Nothing is stored yet, and nothing is invented: both fields start empty.
		expect(field('Flow setpoint (L/s)')).toHaveValue('');
		expect(field('Minimum speed (%)')).toHaveValue('');
		expect(field('Minimum speed (%)')).toHaveAccessibleDescription(
			/From the drive or pump data; there is no standard default\./
		);
		expect(field('Maximum speed (%)')).toHaveAccessibleDescription(
			/Highest speed the drive runs the pump at/
		);
		expect(screen.queryByRole('textbox', { name: 'Speed (%)' })).toBeNull();
		expect(draftNote()).toHaveTextContent(
			'Enter the flow setpoint and minimum speed to switch to flow control.'
		);
		expect(ws.store.undoDepth).toBe(0);
		expect('control' in pumpOf(ws.project)).toBe(false);

		// One value: still a draft; the project and its link have no control.
		await enter('Flow setpoint (L/s)', '12');
		expect(field('Flow setpoint (L/s)')).toHaveValue('12');
		expect(ws.store.undoDepth).toBe(0);
		expect('control' in pumpOf(ws.project)).toBe(false);
		expect('control' in linkedPump(ws)).toBe(false);

		// A minimum speed at the maximum is refused at the field (control.minSpeed < speed).
		const minimum = await enter('Minimum speed (%)', '100');
		expect(minimum).toHaveAttribute('aria-invalid', 'true');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be less than 100 %.');
		expect('control' in pumpOf(ws.project)).toBe(false);

		// Both valid: one undoable edit writes the whole control.
		await enter('Minimum speed (%)', '40');
		expect(ws.store.undoDepth).toBe(1);
		expect(ws.store.undoLabel).toBe('switch pump to flow control');
		const written = { mode: 'flow', setpoint: expect.closeTo(0.012, 15), minSpeed: 0.4 };
		expect(pumpOf(ws.project).control).toEqual(written);
		expect(linkedPump(ws).control).toEqual(written);
		expect(draftNote()).toBeUndefined();
		expect(field('Flow setpoint (L/s)')).toHaveValue('12');
		expect(field('Minimum speed (%)')).toHaveValue('40');

		// The maximum speed is bounded below by the minimum speed.
		await enter('Maximum speed (%)', '30');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be greater than 40 %.');
		expect(pumpOf(ws.project).speed).toBe(1);
		await enter('Maximum speed (%)', '90');
		expect(pumpOf(ws.project).speed).toBe(0.9);
		expect(ws.store.undoLabel).toBe('change maximum speed');
	});

	it('undoes and redoes the switch as one step', async () => {
		const ws = setup();
		await chooseControl('flow');
		await enter('Flow setpoint (L/s)', '12');
		await enter('Minimum speed (%)', '40');
		expect(ws.store.undoDepth).toBe(1);

		ws.store.undo();
		await Promise.resolve();
		expect('control' in pumpOf(ws.project)).toBe(false);
		expect(await findField('Speed (%)')).toHaveValue('100');
		expect(control()).toHaveValue('fixed');
		expect(screen.queryByRole('textbox', { name: 'Minimum speed (%)' })).toBeNull();

		ws.store.redo();
		expect(await findField('Minimum speed (%)')).toHaveValue('40');
		expect(control()).toHaveValue('flow');
		expect(pumpOf(ws.project).control).toMatchObject({ mode: 'flow', minSpeed: 0.4 });
	});

	it('removes the control in one edit, and drops a draft without an edit', async () => {
		const ws = setup((p) => {
			pumpOf(p).control = { mode: 'flow', setpoint: 0.012, minSpeed: 0.4 };
		});
		expect(control()).toHaveValue('flow');
		expect(field('Flow setpoint (L/s)')).toHaveValue('12');

		// Editing a stored control is one edit per field, bounded by the maximum speed.
		await enter('Flow setpoint (L/s)', '15');
		expect(ws.store.undoLabel).toBe('change flow setpoint');
		expect(pumpOf(ws.project).control?.setpoint).toBeCloseTo(0.015, 15);
		await enter('Minimum speed (%)', '100');
		expect(screen.getByRole('alert')).toHaveTextContent('Must be less than 100 %.');
		await enter('Minimum speed (%)', '50');
		expect(ws.store.undoLabel).toBe('change minimum speed');
		expect(ws.store.undoDepth).toBe(2);

		await chooseControl('fixed');
		expect(ws.store.undoDepth).toBe(3);
		expect(ws.store.undoLabel).toBe('switch pump to fixed speed');
		// The field is removed, not left empty or null.
		expect('control' in pumpOf(ws.project)).toBe(false);
		expect('control' in linkedPump(ws)).toBe(false);
		expect(field('Speed (%)')).toHaveValue('100');

		// A draft that is dropped leaves no trace in the history.
		await chooseControl('flow');
		await enter('Flow setpoint (L/s)', '12');
		await chooseControl('fixed');
		expect(ws.store.undoDepth).toBe(3);
		expect(draftNote()).toBeUndefined();
		// Choosing flow again starts from an empty draft.
		await chooseControl('flow');
		expect(field('Flow setpoint (L/s)')).toHaveValue('');
	});

	/**
	 * A complete draft whose minimum speed is not below the maximum speed. The fields' bounds
	 * refuse that order, so only undo can reach it: it brings back a lower speed under a
	 * minimum speed already entered.
	 */
	async function draftAboveMaximum(ws: Workspace) {
		await enter('Speed (%)', '60');
		await enter('Speed (%)', '100');
		await chooseControl('flow');
		await enter('Minimum speed (%)', '80');
		expect(ws.store.undoLabel).toBe('change pump speed');
		ws.store.undo();
		await tick();
		expect(field('Maximum speed (%)')).toHaveValue('60');
		await enter('Flow setpoint (L/s)', '15');
		expect(draftNote()).toHaveTextContent(
			'The minimum speed must be below the maximum speed to switch to flow control. Until then the pump runs at a fixed speed.'
		);
		expect('control' in pumpOf(ws.project)).toBe(false);
		expect(ws.store.undoDepth).toBe(1);
	}

	it('writes a draft that a maximum speed edit completes, with that speed, in one edit', async () => {
		const ws = setup();
		await draftAboveMaximum(ws);

		await enter('Maximum speed (%)', '90');
		const written = { mode: 'flow', setpoint: expect.closeTo(0.015, 15), minSpeed: 0.8 };
		expect(pumpOf(ws.project).control).toEqual(written);
		expect(pumpOf(ws.project).speed).toBe(0.9);
		expect(linkedPump(ws).control).toEqual(written);
		expect(ws.store.undoLabel).toBe('switch pump to flow control');
		expect(ws.store.undoDepth).toBe(2);
		expect(draftNote()).toBeUndefined();
		expect(control()).toHaveValue('flow');

		// One step undoes the speed and the control together.
		ws.store.undo();
		await tick();
		expect('control' in pumpOf(ws.project)).toBe(false);
		expect(pumpOf(ws.project).speed).toBe(0.6);
		expect(control()).toHaveValue('fixed');
		expect(field('Speed (%)')).toHaveValue('60');
	});

	it('drops a draft that undo or redo makes valid: the form never shows a control the project lacks', async () => {
		const ws = setup();
		await draftAboveMaximum(ws);

		// Redo brings back 100 %, above the draft's minimum speed. Writing the draft then would be
		// an edit the user did not make (and would clear what is left to redo), so it is dropped.
		ws.store.redo();
		await tick();
		expect(pumpOf(ws.project).speed).toBe(1);
		expect('control' in pumpOf(ws.project)).toBe(false);
		expect(control()).toHaveValue('fixed');
		expect(field('Speed (%)')).toHaveValue('100');
		expect(screen.queryByRole('textbox', { name: 'Minimum speed (%)' })).toBeNull();
		expect(draftNote()).toBeUndefined();
		expect(ws.store.undoLabel).toBe('change pump speed');
		expect(ws.store.redoDepth).toBe(0);

		// A draft under a control that undo brings back is dropped too: it would come back,
		// unasked, when redo removes that control again.
		await chooseControl('flow');
		await enter('Flow setpoint (L/s)', '12');
		await enter('Minimum speed (%)', '40');
		await chooseControl('fixed');
		await chooseControl('flow');
		await enter('Flow setpoint (L/s)', '20');
		ws.store.undo(); // 'switch pump to fixed speed'
		await tick();
		expect(field('Flow setpoint (L/s)')).toHaveValue('12');
		ws.store.redo();
		await tick();
		expect(control()).toHaveValue('fixed');
		expect(draftNote()).toBeUndefined();
	});

	it('shows the draft note under the Control select, describes the select by it, and announces it', async () => {
		const scrolled = vi.fn();
		const original = Element.prototype.scrollIntoView;
		Element.prototype.scrollIntoView = scrolled;
		try {
			setup();
			// The live region is present before its text, so the text is announced when it appears.
			const regions = new Set(screen.queryAllByRole('status'));
			await chooseControl('flow');
			const note = draftNote();
			expect(note).toBeDefined();
			expect(regions.has(note!)).toBe(true);
			const incomplete =
				'Enter the flow setpoint and minimum speed to switch to flow control. Until then the pump runs at a fixed speed.';
			expect(note).toHaveTextContent(incomplete);
			expect(control()).toHaveAccessibleDescription(expect.stringContaining(incomplete));
			// Right under the Control select: after it, before the fields it asks for.
			const follows = (a: Node, b: Node) =>
				!!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
			expect(follows(control(), note!)).toBe(true);
			expect(follows(note!, field('Flow setpoint (L/s)'))).toBe(true);
			// Kept in view when it appears (e.g. above a phone's bottom bar).
			expect(scrolled).toHaveBeenCalledWith({ block: 'nearest' });
			expect(note!.contains(scrolled.mock.contexts.at(-1) as Node)).toBe(true);

			// Once the control is written, the note and the description are gone.
			await enter('Flow setpoint (L/s)', '12');
			await enter('Minimum speed (%)', '40');
			expect(draftNote()).toBeUndefined();
			expect(control()).not.toHaveAccessibleDescription(/switch to flow control/);
		} finally {
			Element.prototype.scrollIntoView = original;
		}
	});

	it('says an off pump does not apply its control', async () => {
		setup((p) => {
			const pump = pumpOf(p);
			pump.status = 'off';
			pump.control = { mode: 'flow', setpoint: 0.012, minSpeed: 0.4 };
		});
		expect(screen.getByText('This pump is off: its flow control is not applied.')).toBeVisible();
	});
});
