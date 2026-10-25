/**
 * The goal-seek dialog and its entry points (proposal goal-seek.md §6.2-§6.14, §7.5): adding and
 * removing goals and variables with their focus, a prefilled goal from a trace, fields editable in
 * a scenario, Run's reasons, the running state (Cancel, the timer hidden from screen readers, the
 * live region), the result's banners, Apply per run case, out of date and applied, Copy report,
 * the trial table, the flags at the values found, focus at the end of a run, the notice when the
 * dialog is closed, and every Solve control unavailable during a goal seek. The solver is a fake;
 * responses are made up (testing/results.ts).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NetworkError, ValidationError } from '$lib/api/client';
import type { Component, GoalSeekResponse, Override, Project } from '$lib/api/types';
import type { Solver } from '$lib/state/project.svelte';
import { flag, goalSeekResponse, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { updateComponent } from '$lib/utils/edit';
import { pumpTransferExample } from '$lib/utils/examples';
import { newGoal, newVariable, type GoalSeekSetup } from '$lib/utils/goal-seek';
import { withScenarios } from '$lib/utils/scenarios';
import WorkspaceView from './Workspace.svelte';

const P1 = { kind: 'component', componentId: 'P1' } as const;

function setupFor(project: Project): GoalSeekSetup {
	return {
		goals: [{ ...newGoal({ elementId: 'L2' }, 'link_flow'), target: 0.015 }],
		variables: [newVariable(project, { target: P1, field: 'speed' })]
	};
}

/** A solver whose goal seeks wait until released; solves answer at once. */
function heldSolver() {
	const pending: {
		resolve: (r: GoalSeekResponse) => void;
		reject: (e: unknown) => void;
		signal?: AbortSignal;
	}[] = [];
	const goalSeek = vi.fn(
		(_p: Project, _s: unknown, request?: { signal?: AbortSignal }) =>
			new Promise<GoalSeekResponse>((resolve, reject) => {
				pending.push({ resolve, reject, ...(request?.signal ? { signal: request.signal } : {}) });
			})
	);
	const solve = vi.fn(async () => response(pumpTransferSolved()));
	return {
		solver: { solve, goalSeek } satisfies Solver,
		solve,
		goalSeek,
		pending,
		answer: async (r: GoalSeekResponse = goalSeekResponse()) => {
			pending.at(-1)?.resolve(r);
			await tick();
			await tick();
		},
		fail: async (e: unknown) => {
			pending.at(-1)?.reject(e);
			await tick();
			await tick();
		}
	};
}

function mount(project: Project = pumpTransferExample(), withSetup = true) {
	const held = heldSolver();
	const ws = testWorkspace(project, { solver: held.solver });
	if (withSetup) ws.goalSeekSetup = setupFor(ws.project);
	render(WorkspaceView, { workspace: ws });
	return { ws, held };
}

const dialog = () => within(screen.getByRole('dialog', { name: 'Goal seek' }));
const runButton = () => dialog().getByRole('button', { name: /^(Run goal seek|Seeking…)/ });
const closeButton = () => dialog().getAllByRole('button', { name: 'Close' }).at(-1)!;

async function open() {
	await fireEvent.click(screen.getByRole('button', { name: 'Goal seek' }));
	return dialog();
}

function screenWidth(wide: boolean) {
	vi.stubGlobal('matchMedia', (query: string) => ({
		matches: wide,
		media: query,
		onchange: null,
		addEventListener() {},
		removeEventListener() {},
		addListener() {},
		removeListener() {},
		dispatchEvent: () => false
	}));
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('setting up a goal seek', () => {
	it('opens from the Results header, adds and removes goals and variables with their focus', async () => {
		mount(pumpTransferExample(), false);
		const d = await open();
		expect(d.getByText('Add a goal and a variable, then Run goal seek.')).toBeInTheDocument();
		expect(runButton()).toHaveAttribute('aria-disabled', 'true');
		expect(runButton()).toHaveAccessibleDescription('Add at least one goal and one variable.');

		await fireEvent.click(d.getByRole('button', { name: 'Add goal' }));
		const form = d.getByRole('group', { name: 'New goal' });
		const element = within(form).getByRole('combobox', { name: 'Element' });
		const option = within(element).getByRole('option', {
			name: 'Transfer pump → Discharge isolation valve'
		});
		await fireEvent.change(element, { target: { value: (option as HTMLOptionElement).value } });
		await fireEvent.click(within(form).getByRole('radio', { name: 'Flow' }));
		await fireEvent.click(within(form).getByRole('button', { name: 'Add goal' }));
		const card = d.getByRole('group', { name: /Transfer pump → Discharge isolation valve · Flow/ });
		await waitFor(() =>
			expect(within(card).getByRole('textbox', { name: /^Target/ })).toHaveFocus()
		);
		expect(d.queryByRole('group', { name: 'New goal' })).toBeNull();

		await fireEvent.click(d.getByRole('button', { name: 'Add variable' }));
		const vform = d.getByRole('group', { name: 'New variable' });
		const target = within(vform).getByRole('combobox', { name: 'Element' });
		const pump = within(target).getByRole('option', { name: 'Transfer pump' });
		await fireEvent.change(target, { target: { value: (pump as HTMLOptionElement).value } });
		await fireEvent.click(within(vform).getByRole('radio', { name: 'Speed' }));
		await fireEvent.click(within(vform).getByRole('button', { name: 'Add variable' }));
		const variable = d.getByRole('group', { name: /Transfer pump · Speed/ });
		expect(within(variable).getByText('Now 100 %')).toBeInTheDocument();
		expect(within(variable).getByText('Defaults: 20 % to 100 %.')).toBeInTheDocument();
		await waitFor(() =>
			expect(within(variable).getByRole('textbox', { name: /^From/ })).toHaveFocus()
		);
		expect(within(variable).getByRole('textbox', { name: /^From/ })).toHaveValue('20');
		expect(within(variable).getByRole('textbox', { name: /^To/ })).toHaveValue('100');
		// The same value again is unavailable.
		await fireEvent.click(d.getByRole('button', { name: 'Add variable' }));
		const again = d.getByRole('group', { name: 'New variable' });
		await fireEvent.change(within(again).getByRole('combobox', { name: 'Element' }), {
			target: { value: (pump as HTMLOptionElement).value }
		});
		expect(
			within(again).getByRole('radio', { name: /Speed.\(already a variable\)/ })
		).toHaveAttribute('aria-disabled', 'true');
		await fireEvent.click(within(again).getByRole('button', { name: 'Cancel' }));
		await waitFor(() => expect(d.getByRole('button', { name: 'Add variable' })).toHaveFocus());

		expect(runButton()).toHaveAccessibleDescription('Enter a target for each goal.');
		await fireEvent.click(within(card).getByRole('button', { name: /^Remove goal/ }));
		await waitFor(() => expect(d.getByRole('button', { name: 'Add goal' })).toHaveFocus());
		expect(d.getByRole('heading', { name: 'Results to reach (0)' })).toBeInTheDocument();
	});

	it("opens on a trace's element, with the New goal form and the focus on its results", async () => {
		screenWidth(false);
		const { ws } = mount(pumpTransferExample(), false);
		await ws.solve();
		await tick();
		ws.inspect({ kind: 'connection', id: 'L2' });
		await tick();
		const trace = screen.getByRole('dialog', { name: 'Transfer pump → Discharge isolation valve' });
		await fireEvent.click(
			within(trace).getByRole('button', {
				name: 'Use a result of Transfer pump → Discharge isolation valve in goal seek'
			})
		);
		// On a phone the trace sheet closes first: modals are never stacked.
		expect(ws.inspected).toBeNull();
		const form = dialog().getByRole('group', { name: 'New goal' });
		const element = within(form).getByRole('combobox', { name: 'Element' }) as HTMLSelectElement;
		expect(element.selectedOptions[0]?.textContent).toBe(
			'Transfer pump → Discharge isolation valve'
		);
		await waitFor(() => expect(within(form).getAllByRole('radio')[0]).toHaveFocus());
		// The prefill is used once: after its goal is added, Add goal opens on the first element,
		// with the focus on Element.
		await fireEvent.click(within(form).getByRole('radio', { name: 'Flow' }));
		await fireEvent.click(within(form).getByRole('button', { name: 'Add goal' }));
		await waitFor(() => expect(dialog().queryByRole('group', { name: 'New goal' })).toBeNull());
		await fireEvent.click(dialog().getByRole('button', { name: 'Add goal' }));
		const again = dialog().getByRole('group', { name: 'New goal' });
		const next = within(again).getByRole('combobox', { name: 'Element' }) as HTMLSelectElement;
		expect(next.selectedIndex).toBe(0);
		expect(next.value).not.toMatch(/L2$/);
		await waitFor(() => expect(next).toHaveFocus());
	});

	it('keeps its fields editable in a scenario, and names the case', async () => {
		const project = withScenarios(pumpTransferExample(), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const { ws } = mount(project);
		ws.setCase('S1');
		const d = await open();
		expect(d.getByText('Winter', { selector: 'span' })).toBeInTheDocument();
		const target = d.getByRole('textbox', { name: /^Target/ });
		expect(target).not.toHaveAttribute('readonly');
		expect(runButton()).toHaveAccessibleName('Run goal seek on Winter');
	});

	it('the Dialog has the xl size', async () => {
		mount();
		await open();
		expect(screen.getByRole('dialog', { name: 'Goal seek' })).toHaveClass('lg:max-w-5xl');
	});
});

describe('running a goal seek', () => {
	it('shows Seeking… with Cancel, a hidden timer and the live text; Cancel keeps the project', async () => {
		const { ws, held } = mount();
		const d = await open();
		const before = ws.store.project;
		await fireEvent.click(runButton());
		expect(held.goalSeek).toHaveBeenCalledTimes(1);
		expect(runButton()).toHaveAttribute('aria-disabled', 'true');
		expect(d.getByText('Running…')).toBeInTheDocument();
		const status = d.getByText(/^Running on the base case…/);
		expect(status).toHaveTextContent('A goal seek stops by itself after at most 45 s.');
		expect(within(status).getByText(/^\d+ s\.$/)).toHaveAttribute('aria-hidden', 'true');
		expect(
			d.getAllByRole('status').some((s) => s.textContent === 'Goal seek running on the base case.')
		).toBe(true);
		// A second click does nothing: one request at a time.
		await fireEvent.click(runButton());
		expect(held.goalSeek).toHaveBeenCalledTimes(1);
		const cancel = d.getByRole('button', { name: 'Cancel goal seek' });
		cancel.focus();
		await fireEvent.click(cancel);
		expect(held.pending[0]!.signal!.aborted).toBe(true);
		expect(d.getByText('Goal seek cancelled. Nothing in the project changed.')).toBeInTheDocument();
		await waitFor(() => expect(d.getByRole('heading', { name: 'Result' })).toHaveFocus());
		expect(ws.store.project).toBe(before);
		expect(d.getAllByRole('status').some((s) => s.textContent === 'Goal seek cancelled.')).toBe(
			true
		);
	});

	it('shows the met result, moves the focus to it from Run, and announces the values', async () => {
		const { held } = mount();
		const d = await open();
		runButton().focus();
		await fireEvent.click(runButton());
		await held.answer();
		await waitFor(() => expect(d.getByRole('heading', { name: 'Result' })).toHaveFocus());
		expect(d.getByText('Goal met')).toBeInTheDocument();
		expect(d.getByText('3 trial solves in 0.4 s on the base case.')).toBeInTheDocument();
		const found = d.getByText('86.1174 %');
		expect(found).toHaveAttribute('title', '0.8611744213850658 (SI, as stored)');
		expect(d.getByRole('table', { name: 'Results reached' })).toBeInTheDocument();
		expect(d.getByRole('table', { name: 'Trial solves' })).toBeInTheDocument();
		expect(d.getByText('Trial 3 (reported)')).toBeInTheDocument();
		expect(
			d.getByText('At the values found: converged, no physically invalid results')
		).toBeInTheDocument();
		expect(
			d
				.getAllByRole('status')
				.some((s) => s.textContent === 'Goal met: Transfer pump speed 86.1174 %.')
		).toBe(true);
		expect(d.getByRole('button', { name: 'Apply to base case' })).not.toHaveAttribute(
			'aria-disabled',
			'true'
		);
		expect(d.getByRole('button', { name: 'Apply as new scenario' })).toBeInTheDocument();
	});

	it('says the outcome of a run that does not meet its goals, or fails', async () => {
		const { held } = mount();
		const d = await open();
		await fireEvent.click(runButton());
		await held.answer(
			goalSeekResponse({
				met: false,
				stopReason: 'evaluation_limit',
				goals: [
					{ ...goalSeekResponse().result.goals[0]!, met: false, residual: 0.004, value: 0.019 }
				]
			})
		);
		expect(d.getByText('Goal not met')).toBeInTheDocument();
		expect(d.getByText(/the most one goal seek makes/)).toBeInTheDocument();
		// Apply is offered for the closest values.
		expect(d.getByRole('button', { name: 'Apply to base case' })).toBeInTheDocument();

		await fireEvent.click(runButton());
		await held.fail(
			new ValidationError(
				'Goal seek: 1 input problem(s).',
				[
					'Goal seek: 1 input problem(s).',
					'body.variables.0.lower: Input should be greater than 0'
				],
				400,
				'VALIDATION_ERROR'
			)
		);
		expect(d.getByText('The calculation server rejected the goal seek')).toBeInTheDocument();
		expect(
			d.getByText('Variable 1 (Transfer pump · Speed): From: Input should be greater than 0')
		).toBeInTheDocument();
		// Shown at its card too.
		const card = d.getByRole('group', { name: /Transfer pump · Speed/ });
		expect(within(card).getByText('From: Input should be greater than 0')).toBeInTheDocument();

		await fireEvent.click(runButton());
		await held.fail(new NetworkError('The calculation server is busy.', 503, 'SERVER_BUSY'));
		expect(d.getByText('The calculation server is busy.')).toBeInTheDocument();
		await fireEvent.click(d.getByRole('button', { name: 'Run again' }));
		expect(held.goalSeek).toHaveBeenCalledTimes(4);
	});

	it('lists the physically invalid results at the values found', async () => {
		const { held } = mount();
		const d = await open();
		await fireEvent.click(runButton());
		const solved = pumpTransferSolved({
			flags: [
				flag({
					code: 'CAVITATION',
					severity: 'invalid',
					message: "pump 'P1': NPSH available is below NPSH required (made-up)",
					componentId: 'P1'
				})
			]
		});
		await held.answer(goalSeekResponse({}, { solvedState: solved }));
		expect(d.getByText(/^At the values found: 1 physically invalid result:/)).toBeInTheDocument();
	});

	it('copies the report, with the selected-text fallback', async () => {
		const { held } = mount();
		const d = await open();
		await fireEvent.click(runButton());
		await held.answer();
		const writeText = vi.fn<(text: string) => Promise<void>>(async () => {});
		vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
		await fireEvent.click(d.getByRole('button', { name: 'Copy report' }));
		await waitFor(() => expect(d.getByText('Copied to the clipboard.')).toBeInTheDocument());
		expect(writeText.mock.calls[0]![0]).toMatch(
			/^Goal seek: Pump transfer between two tanks\nCase: base case\n/
		);
		vi.stubGlobal('navigator', { ...navigator, clipboard: undefined });
		await fireEvent.click(d.getByRole('button', { name: 'Copy report' }));
		const area = await d.findByRole('textbox', { name: 'Goal seek report as text' });
		expect((area as HTMLTextAreaElement).value).toContain('Trial\tWhy');
	});

	it('says how a run ended in a notice when the dialog was closed, never in both', async () => {
		const { ws, held } = mount();
		await open();
		await fireEvent.click(runButton());
		await fireEvent.click(closeButton());
		expect(screen.queryByRole('dialog', { name: 'Goal seek' })).toBeNull();
		// The run goes on; the header's Cancel and the results button say so.
		expect(screen.getByRole('button', { name: 'Cancel goal seek' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Goal seek (running)' })).toBeInTheDocument();
		await held.answer();
		expect(ws.notice?.text).toBe(
			'Goal seek on the base case finished: goal met. Open Goal seek to apply the values.'
		);
	});
});

describe('one request at a time: every Solve control waits during a goal seek', () => {
	it('the header Solve, the Results Solve and Solve all, Compare and the case bar', async () => {
		const project = withScenarios(pumpTransferExample(), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const { ws, held } = mount(project);
		await open();
		await fireEvent.click(runButton());
		await fireEvent.click(closeButton());
		const header = document.querySelector<HTMLButtonElement>('[data-solve-button]')!;
		expect(header).toHaveAttribute('aria-disabled', 'true');
		expect(header).toHaveAccessibleDescription('A goal seek is running; Cancel stops it.');
		await fireEvent.click(header);
		const results = within(screen.getByRole('region', { name: 'Results' }));
		const solve = results.getByRole('button', { name: 'Solve Base case' });
		expect(solve).not.toBe(header);
		expect(solve).toHaveAttribute('aria-disabled', 'true');
		expect(solve).toHaveAccessibleDescription(
			'A goal seek is running; Cancel in the header stops it.'
		);
		await fireEvent.click(solve);
		const bar = within(screen.getByRole('group', { name: 'Case' }));
		const all = bar.getByRole('button', { name: 'Solve all' });
		expect(all).toHaveAttribute('aria-disabled', 'true');
		expect(all).toHaveAccessibleDescription(
			'A goal seek is running; Cancel in the header stops it.'
		);
		expect(bar.getByRole('status')).toHaveTextContent('Goal seek running on the base case…');
		await fireEvent.click(all);
		await fireEvent.click(results.getByRole('tab', { name: 'Compare cases' }));
		const compares = within(results.getByRole('region', { name: 'Compare cases' })).getAllByRole(
			'button',
			{ name: 'Solve all' }
		);
		for (const compare of compares) {
			expect(compare).toHaveAttribute('aria-disabled', 'true');
			await fireEvent.click(compare);
		}
		expect(held.solve).not.toHaveBeenCalled();
		expect(ws.store.goalSeek?.status).toBe('running');
		expect(held.pending[0]!.signal!.aborted).toBe(false);
		// The header's Cancel stops it.
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel goal seek' }));
		expect(held.pending[0]!.signal!.aborted).toBe(true);
		expect(ws.store.calculating).toBeNull();
	});

	it("Solve again and a link's Solve now", async () => {
		const project = { ...pumpTransferExample(), methodVersion: '1.2.0' };
		const { ws, held } = mount(project);
		await open();
		await fireEvent.click(runButton());
		await fireEvent.click(closeButton());
		const results = within(screen.getByRole('region', { name: 'Results' }));
		const now = results.getByRole('button', { name: 'Solve now' });
		expect(now).toHaveAttribute('aria-disabled', 'true');
		expect(now).toHaveAccessibleDescription(
			'A goal seek is running; Cancel in the header stops it.'
		);
		await fireEvent.click(now);
		expect(held.solve).not.toHaveBeenCalled();
		ws.store.cancelGoalSeek();
		await ws.solve();
		ws.edit(
			(p) => updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.9 }) as Component),
			'change speed'
		);
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: 'Goal seek' }));
		await fireEvent.click(runButton());
		await fireEvent.click(closeButton());
		const again = results.getByRole('button', { name: 'Solve again' });
		expect(again).toHaveAttribute('aria-disabled', 'true');
		expect(again).toHaveAccessibleDescription(
			'A goal seek is running; Cancel in the header stops it.'
		);
		await fireEvent.click(again);
		expect(held.solve).toHaveBeenCalledTimes(1);
	});
});

describe('Apply', () => {
	it('applies to the base, closes, solves, and shows Applied; undo makes Apply current again', async () => {
		const { ws, held } = mount();
		const d = await open();
		await fireEvent.click(runButton());
		await held.answer();
		await fireEvent.click(d.getByRole('button', { name: 'Apply to base case' }));
		expect(screen.queryByRole('dialog', { name: 'Goal seek' })).toBeNull();
		await waitFor(() => expect(held.solve).toHaveBeenCalledTimes(1));
		expect(ws.notice?.text).toMatch(/^Applied to the base case: Transfer pump speed 86\.1174 %/);
		const again = await open();
		expect(again.getByText('Applied to the base case.')).toBeInTheDocument();
		expect(again.queryByRole('button', { name: 'Apply to base case' })).toBeNull();
		ws.undo();
		await tick();
		expect(again.getByRole('button', { name: 'Apply to base case' })).not.toHaveAttribute(
			'aria-disabled',
			'true'
		);
	});

	it('is unavailable when out of date, with the reason', async () => {
		const { ws, held } = mount();
		const d = await open();
		await fireEvent.click(runButton());
		await held.answer();
		ws.edit(
			(p) => updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.9 }) as Component),
			'change speed'
		);
		await tick();
		expect(
			d.getByText(/^Out of date: the project changed after this goal seek/, { selector: 'span' })
		).toBeInTheDocument();
		const apply = d.getByRole('button', { name: 'Apply to base case' });
		expect(apply).toHaveAttribute('aria-disabled', 'true');
		expect(apply).toHaveAccessibleDescription(/^Out of date/);
		await fireEvent.click(apply);
		expect(
			(ws.store.project.components.find((c) => c.id === 'P1') as { speed: number }).speed
		).toBe(0.9);
	});

	it('a scenario run applies to its scenario or as a new one, never to the base', async () => {
		const level: Override = {
			kind: 'component',
			componentId: 'R1',
			field: 'liquidLevel',
			value: 2
		};
		const { ws, held } = mount(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Low suction', overrides: [level] }])
		);
		ws.setCase('S1');
		const d = await open();
		await fireEvent.click(runButton());
		await held.answer();
		expect(d.queryByRole('button', { name: 'Apply to base case' })).toBeNull();
		expect(d.getByRole('button', { name: 'Apply to scenario Low suction' })).toBeInTheDocument();
		expect(
			d.getByText(
				/^Not offered for the base case: the values were found with Low suction's changes/
			)
		).toBeInTheDocument();
		// After a case switch, the result keeps its case.
		ws.setCase(null);
		await tick();
		expect(
			d.getByText('This goal seek ran on scenario Low suction (you are viewing the base case).')
		).toBeInTheDocument();
		await fireEvent.click(d.getByRole('button', { name: 'Apply to scenario Low suction' }));
		expect(ws.store.activeCase).toBe('S1');
		expect(ws.store.project.scenarios![0]!.overrides).toEqual([
			level,
			{ kind: 'component', componentId: 'P1', field: 'speed', value: 0.8611744213850658 }
		]);
	});
});
