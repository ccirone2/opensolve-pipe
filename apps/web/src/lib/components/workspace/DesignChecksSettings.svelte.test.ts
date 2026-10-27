/**
 * Settings → Design checks (CLAUDE.md D19; proposal design-checks.md §5): off by default; a switch
 * per check; a preset fills its limits with the API's published values and labels them with
 * its citation; a limit typed by hand makes the source the user's; a pair out of order is
 * refused with the reason at its field; turning every check off leaves the project as it was.
 * One undo step per change. The API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { designCheckPresets } from '$lib/utils/model-rules';
import { withScenarios } from '$lib/utils/scenarios';

async function openSettings() {
	const ws = testWorkspace(pumpTransferExample());
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
	const dialog = within(await screen.findByRole('dialog', { name: 'Project settings' }));
	return { ws, dialog };
}

async function enter(field: HTMLElement, text: string) {
	field.focus();
	await fireEvent.input(field, { target: { value: text } });
	await fireEvent.keyDown(field, { key: 'Enter' });
}

describe('DesignChecksSettings', () => {
	it('is off by default, and a project without checks has no field', async () => {
		const { ws, dialog } = await openSettings();
		for (const name of ['NPSH margin', 'Pump operating region', 'Pipe velocity'])
			expect(dialog.getByRole('checkbox', { name })).not.toBeChecked();
		expect('designChecks' in ws.project.settings).toBe(false);
	});

	it('fills a check from a preset, labelled with its citation, and a typed limit is the user’s', async () => {
		const { ws, dialog } = await openSettings();
		await fireEvent.click(dialog.getByRole('checkbox', { name: 'Pump operating region' }));
		expect(ws.project.settings.designChecks).toEqual({
			operatingRegion: { source: { kind: 'user' } }
		});
		const api610 = designCheckPresets().find((p) => p.id === 'api610_por')!;
		const button = dialog.getByRole('button', { name: 'Use API 610' });
		expect(button).toHaveAccessibleDescription(api610.citation);
		await fireEvent.click(button);
		expect(ws.project.settings.designChecks?.operatingRegion).toEqual({
			preferredMin: 0.7,
			preferredMax: 1.2,
			source: { kind: 'preset', preset: 'api610_por' }
		});
		expect(dialog.getByRole('textbox', { name: /^Lowest flow, of BEP flow/ })).toHaveValue('70');
		const source = () => dialog.getByText('Source:').parentElement!;
		expect(source()).toHaveTextContent(`Source: ${api610.citation}`);
		await enter(dialog.getByRole('textbox', { name: /^Highest flow, of BEP flow/ }), '110');
		expect(ws.project.settings.designChecks?.operatingRegion).toEqual({
			preferredMin: 0.7,
			preferredMax: 1.1,
			source: { kind: 'user' }
		});
		expect(source()).toHaveTextContent('Source: your values');
	});

	it('refuses a lower limit above the upper one and says why', async () => {
		const { ws, dialog } = await openSettings();
		await fireEvent.click(dialog.getByRole('checkbox', { name: 'Pipe velocity' }));
		await enter(dialog.getByRole('textbox', { name: /^Maximum velocity/ }), '3');
		const minimum = dialog.getByRole('textbox', { name: /^Minimum velocity/ });
		await enter(minimum, '4');
		expect(ws.project.settings.designChecks?.pipeVelocity).toEqual({
			maximum: 3,
			source: { kind: 'user' }
		});
		expect(minimum).toHaveAttribute('aria-invalid', 'true');
		expect(minimum).toHaveAccessibleDescription(/Must be less than 3 m\/s\./);
		await enter(minimum, '0.5');
		expect(minimum).not.toHaveAttribute('aria-invalid');
		expect(ws.project.settings.designChecks?.pipeVelocity?.minimum).toBe(0.5);
	});

	it('drops a refusal once the stored value changes (a preset, an undo)', async () => {
		const { ws, dialog } = await openSettings();
		await fireEvent.click(dialog.getByRole('checkbox', { name: 'Pump operating region' }));
		await enter(dialog.getByRole('textbox', { name: /^Highest flow, of BEP flow/ }), '50');
		const lowest = dialog.getByRole('textbox', { name: /^Lowest flow, of BEP flow/ });
		await enter(lowest, '80');
		expect(lowest).toHaveAttribute('aria-invalid', 'true');
		await fireEvent.click(dialog.getByRole('button', { name: 'Use API 610' }));
		expect(lowest).not.toHaveAttribute('aria-invalid');
		expect(lowest).toHaveValue('70');
		await enter(lowest, '130');
		expect(lowest).toHaveAttribute('aria-invalid', 'true');
		ws.undo(); // back to 50 % with no lowest flow: the field's value changed
		await tick();
		expect(lowest).not.toHaveAttribute('aria-invalid');
		expect(lowest).toHaveValue('');
	});

	it('removes the field when the last check goes off, one undo step per change', async () => {
		const { ws, dialog } = await openSettings();
		const npsh = dialog.getByRole('checkbox', { name: 'NPSH margin' });
		await fireEvent.click(npsh);
		await fireEvent.click(dialog.getByRole('button', { name: 'Use HI 9.6.1-2012 (general)' }));
		expect(ws.project.settings.designChecks?.npshMargin).toEqual({
			minimumRatio: 1.1,
			minimumMargin: 1,
			source: { kind: 'preset', preset: 'hi961_2012_general' }
		});
		await fireEvent.click(npsh);
		expect('designChecks' in ws.project.settings).toBe(false);
		ws.undo();
		expect(ws.project.settings.designChecks?.npshMargin?.minimumRatio).toBe(1.1);
		ws.undo();
		expect(ws.project.settings.designChecks).toEqual({ npshMargin: { source: { kind: 'user' } } });
		ws.undo();
		expect('designChecks' in ws.project.settings).toBe(false);
	});

	it('is the same in every case: locked in a scenario, as the site and solver are', async () => {
		const project = withScenarios(pumpTransferExample(), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		project.settings.designChecks = {
			pipeVelocity: { maximum: 3, source: { kind: 'user' } }
		};
		const ws = testWorkspace(project);
		ws.setCase('S1');
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
		const dialog = within(await screen.findByRole('dialog', { name: 'Project settings' }));
		expect(dialog.getByRole('checkbox', { name: 'Pipe velocity' })).toBeDisabled();
		expect(dialog.getByRole('checkbox', { name: 'NPSH margin' })).toBeDisabled();
		expect(dialog.getByRole('textbox', { name: /^Maximum velocity/ })).toHaveAttribute('readonly');
		expect(dialog.queryByRole('button', { name: /^Use / })).toBeNull();
		expect(dialog.getByText(/change them in the base case/)).toBeInTheDocument();
	});
});
