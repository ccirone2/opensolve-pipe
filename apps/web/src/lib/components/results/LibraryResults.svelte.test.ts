/**
 * The project library in the results (CLAUDE.md D21; proposal project-library.md §4.3, §6.2,
 * §6.4): a valve's Crane default K outside its table says to enter the manufacturer's coefficient
 * and offers "Enter a datasheet value", which shows the valve's resistance in Build; a trace's
 * note naming a library entry links to it in the library. The solve results are made-up test
 * inputs (testing/results.ts); the API is replaced by fakes.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Project, SolvedState } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, pumpTransferSolved, response, SAMPLE_TRACE } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { VALVE_LIBRARY_ADVICE } from '$lib/utils/flag-text';

const results = () => within(screen.getByRole('region', { name: 'Results' }));

/** The pump transfer example with its valve on a Cv entry of the library (test inputs). */
function withEntry(): Project {
	const project = pumpTransferExample();
	project.resistanceLibrary = [
		{ id: 'RS1', name: 'Gate, open', source: 'test input: a made-up Cv', kind: 'Cv', value: 250 }
	];
	return project;
}

async function solveWith(solved: SolvedState, project: Project) {
	const solve = vi.fn(() => Promise.resolve(response(solved)));
	const ws = testWorkspace(project, { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	await ws.solve();
	await results().findByRole('heading', { name: 'Converged' });
	return ws;
}

describe('the project library in the results', () => {
	it("a valve's Crane default out of its table offers to enter a datasheet value", async () => {
		const outOfTable = flag({
			code: 'CORRELATION_OUT_OF_RANGE',
			severity: 'warning',
			message: "valve 'V1': made-up reason",
			componentId: 'V1',
			details: { referenceDiameter: 0.7366 }
		});
		const ws = await solveWith(pumpTransferSolved({ flags: [outOfTable] }), withEntry());
		const flags = within(results().getByRole('region', { name: /^Flags/ }));
		expect(
			flags.getByRole('button', { name: /^Show Discharge isolation valve:/ })
		).toHaveTextContent(VALVE_LIBRARY_ADVICE);
		await fireEvent.click(
			flags.getByRole('button', { name: 'Enter a datasheet value for Discharge isolation valve' })
		);
		await tick();
		expect(ws.pane).toBe('build');
		expect(ws.nav.current?.id).toBe('V1');
		const resistance = screen.getByRole('combobox', { name: 'Resistance given as' });
		expect(resistance).toHaveFocus();
		expect(within(resistance).getByRole('option', { name: /^“Gate, open”/ })).toBeInTheDocument();
	});

	it('no datasheet action for a flag that is not on a valve default', async () => {
		const laminar = flag({
			code: 'CORRELATION_OUT_OF_RANGE',
			severity: 'warning',
			message: "valve 'V1': made-up laminar flow",
			componentId: 'V1',
			details: { reynoldsNumber: 900 }
		});
		await solveWith(pumpTransferSolved({ flags: [laminar] }), withEntry());
		expect(results().queryByRole('button', { name: /^Enter a datasheet value/ })).toBeNull();
	});

	it("a trace's mention of an entry opens it in the library", async () => {
		const project = withEntry();
		const valve = project.components.find((c) => c.id === 'V1');
		if (valve?.type === 'valve') valve.resistance = { kind: 'library', id: 'RS1' };
		const note =
			'Resistance: project library resistance "Gate, open" (RS1): test input: a made-up Cv';
		const solved = pumpTransferSolved();
		solved.trace = {
			...solved.trace,
			elements: { V1: { ...SAMPLE_TRACE, elementId: 'V1', elementType: 'valve', notes: [note] } }
		};
		const ws = await solveWith(solved, project);
		ws.inspect({ kind: 'component', id: 'V1' });
		await tick();
		const link = await screen.findByRole('button', {
			name: 'project library resistance "Gate, open" (RS1)'
		});
		expect(link.closest('li')).toHaveTextContent(note);
		await fireEvent.click(link);
		const dialog = within(await screen.findByRole('dialog', { name: 'Project library' }));
		expect(dialog.getByRole('tab', { name: 'Resistances (1)' })).toHaveAttribute(
			'aria-selected',
			'true'
		);
		await tick();
		expect(dialog.getByRole('heading', { name: /^Gate, open/ })).toHaveFocus();
	});
});
