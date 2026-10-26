/**
 * Results in context (proposal ui-ux-refinement.md item 6): the current element's key results
 * from the last solve, in Build. The solve results are made-up test inputs (testing/results.ts);
 * the API is replaced by fakes.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import { TopologyError } from '$lib/api/client';
import type { Component, Flag, PipeConnection, Project, SolveResponse } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { flag, link, pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { reversePiping, updateComponent } from '$lib/utils/edit';
import { addPipe, removePipe } from '$lib/utils/piping';
import { INCH } from '$lib/utils/units';

const build = () => within(screen.getByRole('region', { name: 'Build' }));
const strips = () => build().queryAllByRole('group', { name: /^Last solve/ });

/** "Label (unit): value" of each value shown, with the label's no-break space as a space. */
function values(strip: HTMLElement): string[] {
	return [...strip.querySelectorAll('dl > div')].map((d) =>
		`${d.querySelector('dt')?.textContent?.trim()}: ${d.querySelector('dd')?.textContent?.trim()}`.replace(
			/\u00a0/g,
			' '
		)
	);
}

/** As values(), with a value of several parts as "Pipe 1 -2.25, Pipe 2 -4". */
function shown(strip: HTMLElement): string[] {
	return [...strip.querySelectorAll('dl > div')].map((d) => {
		const dd = d.querySelector('dd');
		const grid = dd?.querySelector('span.inline-grid');
		const parts = grid ? [...grid.children].map((s) => s.textContent?.trim() ?? '') : null;
		const value = parts
			? parts.flatMap((text, i) => (i % 2 ? [] : [`${text} ${parts[i + 1] ?? ''}`])).join(', ')
			: (dd?.textContent?.trim() ?? '');
		return `${d.querySelector('dt')?.textContent?.trim()}: ${value}`.replace(/\u00a0/g, ' ');
	});
}

function mount(
	answer: () => Promise<SolveResponse> = () => Promise.resolve(response(pumpTransferSolved()))
) {
	const solve = vi.fn(answer);
	const ws = testWorkspace(pumpTransferExample(), { solver: { solve } });
	render(WorkspaceView, { workspace: ws });
	return { ws, solve };
}

describe('results in context', () => {
	it('shows nothing before a first solve, then the key values of the element shown', async () => {
		const { ws } = mount();
		ws.nav.jumpTo('P1');
		await tick();
		expect(strips()).toHaveLength(0);
		await ws.solve();
		ws.pane = 'build';
		await tick();
		const [strip] = strips();
		expect(values(strip!)).toEqual([
			'Status: Running',
			'Flow (L/s): 20',
			'Head (m): 22',
			'NPSH margin (m): 9'
		]);
		expect(within(strip!).queryByText(/Out of date/)).toBeNull();
	});

	it('shows a connection’s flow, velocity and head loss in Piping', async () => {
		const { ws } = mount();
		await ws.solve();
		ws.nav.jumpTo('V1');
		ws.nav.showConnection('outlet');
		ws.pane = 'build';
		await tick();
		const connection = strips().at(-1)!;
		expect(values(connection)).toEqual(['Flow (L/s): 20', 'Velocity (m/s): 4', 'Head loss (m): 8']);
	});

	it('marks the values out of date after an edit, and says when the element was not solved', async () => {
		const { ws } = mount();
		await ws.solve();
		ws.nav.jumpTo('P1');
		ws.pane = 'build';
		ws.edit(
			(p) => updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.9 }) as Component),
			'change speed'
		);
		await tick();
		const [strip] = strips();
		expect(within(strip!).getByText('Out of date: solve again')).toBeInTheDocument();
		expect(values(strip!)).toContain('Flow (L/s): 20');

		await fireEvent.click(build().getByRole('button', { name: 'Add after' }));
		const dialog = await screen.findByRole('dialog', { name: /^Add after/ });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }));
		await tick();
		expect(within(strips()[0]!).getByText(/^Not in the last solve/)).toBeInTheDocument();
	});

	it('gives no values for a solve that did not converge, and nothing after a failed solve', async () => {
		let answer: Promise<SolveResponse> = Promise.resolve(
			response(pumpTransferSolved({ converged: false }))
		);
		const { ws } = mount(() => answer);
		ws.nav.jumpTo('P1');
		await ws.solve();
		ws.pane = 'build';
		await tick();
		const [strip] = strips();
		expect(within(strip!).getByText(/^The last solve did not converge/)).toBeInTheDocument();
		expect(strip!.querySelector('dl')).toBeNull();

		answer = Promise.reject(
			new TopologyError('The network cannot be solved.', [
				{ code: 'NO_FIXED_HEAD', message: 'no fixed head', componentIds: [], connectionIds: [] }
			])
		);
		await ws.solve();
		ws.pane = 'build';
		await tick();
		expect(strips()).toHaveLength(0);
	});

	it('lists the element’s flags, and Trace opens its trace without moving Build', async () => {
		const flags = [
			flag({
				code: 'CAVITATION',
				severity: 'invalid',
				message: 'The pump would cavitate',
				componentId: 'P1'
			}),
			flag({
				code: 'PUMP_OUTSIDE_CURVE',
				severity: 'warning',
				message: 'Outside the curve',
				componentId: 'P1'
			}),
			flag({ code: 'NPSH_NOT_CHECKED', severity: 'info', message: 'A third', componentId: 'P1' })
		];
		const { ws } = mount(() => Promise.resolve(response(pumpTransferSolved({ flags }))));
		await ws.solve();
		ws.nav.jumpTo('P1');
		ws.pane = 'build';
		await tick();
		const [strip] = strips();
		expect(within(strip!).getByText(/The pump would cavitate/)).toBeInTheDocument();
		expect(within(strip!).getByText(/Outside the curve/)).toBeInTheDocument();
		expect(within(strip!).getByText('1 more in the trace.')).toBeInTheDocument();

		const path = ws.nav.path;
		await fireEvent.click(within(strip!).getByRole('button', { name: 'Trace of Transfer pump' }));
		expect(ws.inspected).toEqual({ kind: 'component', id: 'P1' });
		expect(ws.nav.path).toEqual(path);
	});

	it('gives each pipe its velocity beside its size, out of date after edits, none for a pipe added since', async () => {
		const { ws } = mount();
		await ws.solve();
		ws.nav.jumpTo('P1');
		ws.nav.showConnection('discharge');
		ws.pane = 'build';
		await tick();
		// A size select with the pipe library, a number field without it (as in these tests).
		const size = () => build().getByLabelText(/^Size/);
		// The fixture's pipe in L2 runs at 2 m/s.
		expect(size()).toHaveAccessibleDescription('Velocity at the last solve: 2 m/s.');
		ws.edit(
			(p) => updateComponent(p, 'P1', (c) => ({ ...c, speed: 0.9 }) as Component),
			'change speed'
		);
		await tick();
		expect(size()).toHaveAccessibleDescription('Velocity at the last solve: 2 m/s (out of date).');
		await fireEvent.click(build().getByRole('button', { name: /^Add pipe/ }));
		await tick();
		// The pipe solved keeps its own velocity (found by identity); the pipe added has none.
		const [solvedPipe, addedPipe, ...rest] = build().getAllByLabelText(/^Size/);
		expect(rest).toEqual([]);
		expect(solvedPipe).toHaveAccessibleDescription(
			'Velocity at the last solve: 2 m/s (out of date).'
		);
		expect(addedPipe).not.toHaveAccessibleDescription(/Velocity/);
	});
});

/**
 * After a structural edit since the solve (a reversal, an insertion, a join, pipes added and
 * removed), the strip and the pipe hints show a value only against the direction and the pipe it
 * refers to: found exactly (pipes by identity, the direction by the connection's ends), else left
 * out with a note.
 */
describe('results in context after a structural edit since the solve', () => {
	/** L2 of two pipes: pipe A (NPS 3, 3 m) then pipe B (NPS 4, 2 m), listed from `from` to `to`. */
	function twoPipeProject(drawnAgainstFlow = false): Project {
		const project = pumpTransferExample();
		const l2 = project.connections.find((c) => c.id === 'L2') as PipeConnection;
		const a = l2.piping.pipes[0]!;
		l2.piping.pipes = [a, { ...a, nominalSize: 4 * INCH, length: 2 }];
		if (drawnAgainstFlow) {
			[l2.fromComponentId, l2.toComponentId] = [l2.toComponentId, l2.fromComponentId];
			[l2.fromPortId, l2.toPortId] = [l2.toPortId, l2.fromPortId];
		}
		return project;
	}

	/** Made-up L2 results: 20 L/s (sign by its direction), 4 m/s in pipe A, 2.25 m/s in pipe B. */
	function twoPipeSolved(sign = 1, flags: Flag[] = []) {
		const one = link().segments[0]!;
		return pumpTransferSolved({
			flags,
			linkResults: {
				...pumpTransferSolved().linkResults,
				L2: link({
					flow: sign * 0.02,
					velocity: sign * 4,
					headLoss: sign * 1.5,
					segments: [
						{ ...one, index: 0, velocity: sign * 4 },
						{ ...one, index: 1, velocity: sign * 2.25 }
					]
				})
			}
		});
	}

	async function mountSolved(project: Project, sign = 1, flags: Flag[] = []) {
		const solve = vi.fn(() => Promise.resolve(response(twoPipeSolved(sign, flags))));
		const ws = testWorkspace(project, { solver: { solve } });
		render(WorkspaceView, { workspace: ws });
		await ws.solve();
		ws.nav.jumpTo('P1');
		ws.nav.showConnection('discharge');
		ws.pane = 'build';
		await tick();
		return ws;
	}

	const sizeHints = () =>
		build()
			.getAllByLabelText(/^Size/)
			.map((field) => field.getAttribute('aria-describedby') ?? '')
			.map((ids) =>
				ids
					.split(' ')
					.map((one) => document.getElementById(one)?.textContent?.trim() ?? '')
					.filter((text) => text.startsWith('Velocity'))
					.join(' ')
			);
	const connectionStrip = () => strips().at(-1)!;

	it('gives the values in the new direction after a reversal, each pipe its own velocity', async () => {
		const ws = await mountSolved(twoPipeProject());
		expect(sizeHints()).toEqual([
			'Velocity at the last solve: 4 m/s.',
			'Velocity at the last solve: 2.25 m/s.'
		]);
		ws.store.update((p) => {
			const c = p.connections.find((x) => x.id === 'L2')!;
			[c.fromComponentId, c.toComponentId] = [c.toComponentId, c.fromComponentId];
			[c.fromPortId, c.toPortId] = [c.toPortId, c.fromPortId];
			c.piping = reversePiping(c.piping);
		}, 'Reverse');
		await tick();
		// The panel now lists pipe B first, and positive flow runs from the valve to the pump.
		expect(shown(connectionStrip())).toEqual([
			'Flow (L/s): -20',
			'Velocity (m/s): Pipe 1 -2.25, Pipe 2 -4',
			'Head loss (m): -1.5'
		]);
		expect(
			within(connectionStrip()).getByText(
				'Reversed since the last solve: the values are given in its new direction.'
			)
		).toBeInTheDocument();
		expect(sizeHints()).toEqual([
			'Velocity at the last solve: -2.25 m/s (out of date).',
			'Velocity at the last solve: -4 m/s (out of date).'
		]);
	});

	it('follows the pipes when Build turns a connection drawn against the flow to insert a component', async () => {
		const ws = await mountSolved(twoPipeProject(true), -1);
		// Insert component: L2 is turned to the flow (pipe B first) and ends at the new valve.
		ws.insert('L2', 'gate');
		ws.nav.jumpTo('P1');
		ws.nav.showConnection('discharge');
		await tick();
		const l2 = ws.store.project.connections.find((c) => c.id === 'L2')!;
		expect([l2.fromComponentId, l2.piping.pipes.map((p) => p.length)]).toEqual(['P1', [2, 3]]);
		expect(shown(connectionStrip())).toEqual([
			'Flow (L/s): 20',
			'Velocity (m/s): Pipe 1 2.25, Pipe 2 4'
		]);
		expect(
			within(connectionStrip()).getByText(
				'Its ends changed since the last solve: solve again to see its head loss.'
			)
		).toBeInTheDocument();
		expect(sizeHints()).toEqual([
			'Velocity at the last solve: 2.25 m/s (out of date).',
			'Velocity at the last solve: 4 m/s (out of date).'
		]);
	});

	it('never gives a pipe another pipe’s velocity when pipes are added and removed', async () => {
		const ws = await mountSolved(twoPipeProject());
		ws.editConnection('L2', 'add pipe segment', (c) => ({ ...c, piping: addPipe(c.piping) }));
		ws.editConnection('L2', 'remove pipe', (c) => ({ ...c, piping: removePipe(c.piping, 0) }));
		await tick();
		// Two pipes again: pipe B, then the pipe added since.
		expect(sizeHints()).toEqual(['Velocity at the last solve: 2.25 m/s (out of date).', '']);
		expect(shown(connectionStrip())).toEqual([
			'Flow (L/s): 20',
			'Velocity (m/s): Pipe 1 2.25',
			'Head loss (m): 1.5'
		]);
		expect(
			within(connectionStrip()).getByText(
				'No velocity from the last solve for pipe 2: solve again to see it.'
			)
		).toBeInTheDocument();
	});

	it('leaves out what a joined connection did not have, and keeps each pipe’s own velocity', async () => {
		const ws = await mountSolved(twoPipeProject());
		expect(ws.remove('V1', true)).toBe(true);
		ws.nav.jumpTo('P1');
		ws.nav.showConnection('discharge');
		await tick();
		// L2 now runs to the discharge tank: pipes A and B, then L3's pipe (2 m/s in L3's results).
		expect(shown(connectionStrip())).toEqual(['Velocity (m/s): Pipe 1 4, Pipe 2 2.25, Pipe 3 2']);
		expect(
			within(connectionStrip()).getByText(
				'Its ends changed since the last solve: solve again to see its flow and head loss.'
			)
		).toBeInTheDocument();
		expect(sizeHints()).toEqual([
			'Velocity at the last solve: 4 m/s (out of date).',
			'Velocity at the last solve: 2.25 m/s (out of date).',
			'Velocity at the last solve: 2 m/s (out of date).'
		]);
	});

	it('gives no flow or head loss of a connection that took a solved id and its ends with a new pipe', async () => {
		const ws = await mountSolved(twoPipeProject());
		// Delete the valve with its connections, then add a gate after the pump: the gate takes the
		// id V1, and its connection the id L2, between the ports L2 was solved between.
		expect(ws.remove('V1', false)).toBe(true);
		expect(ws.addAfter('P1', 'discharge', 'gate')).toBe('V1');
		ws.nav.jumpTo('P1');
		ws.nav.showConnection('discharge');
		await tick();
		const l2 = ws.store.project.connections.find((c) => c.id === 'L2')!;
		expect([l2.fromComponentId, l2.fromPortId, l2.toComponentId, l2.toPortId]).toEqual([
			'P1',
			'discharge',
			'V1',
			'inlet'
		]);
		// Its one pipe is new: the solved L2's flow and head loss are not its own.
		expect(shown(connectionStrip())).toEqual([]);
		expect(
			within(connectionStrip()).getByText(
				'Its pipes changed since the last solve: solve again to see its flow and head loss.'
			)
		).toBeInTheDocument();
		expect(sizeHints()).toEqual(['']);
	});

	it('numbers a pipe’s flag as the pipe is now, and leaves to the trace what it cannot place', async () => {
		/** Pipe A's flag, and one about an elbow on it. */
		const flags = [
			flag({
				code: 'TRANSITIONAL_FLOW',
				severity: 'warning',
				message: "connection 'L2' pipe 1: made-up",
				connectionId: 'L2',
				details: { segmentIndex: 0, reynoldsNumber: 2500 }
			}),
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message: "connection 'L2' fitting 1 (elbow_90_lr): made-up reason",
				connectionId: 'L2',
				details: { fittingIndex: 0, reynoldsNumber: 1500 }
			})
		];
		const withElbow = () => {
			const project = twoPipeProject();
			project.connections.find((c) => c.id === 'L2')!.piping.fittings = [
				{ type: 'elbow_90_lr', quantity: 1, pipeIndex: 0 }
			];
			return project;
		};
		const reversed = await mountSolved(withElbow(), 1, flags);
		reversed.store.update((p) => {
			const c = p.connections.find((x) => x.id === 'L2')!;
			[c.fromComponentId, c.toComponentId] = [c.toComponentId, c.fromComponentId];
			[c.fromPortId, c.toPortId] = [c.toPortId, c.fromPortId];
			c.piping = reversePiping(c.piping);
		}, 'Reverse');
		await tick();
		// Pipe A is now pipe 2; the elbow is still fitting 1 (a reversal keeps the fittings' order).
		const listed = within(connectionStrip()).getAllByRole('listitem');
		expect(listed.map((li) => li.textContent?.trim())).toEqual([
			'Pipe 2: Re = 2500 is in the laminar–turbulent transition range: the friction factor is interpolated and the flow may be unsteady.',
			'90° elbow, long radius (fitting 1): Made-up reason'
		]);
		cleanup();

		const moved = await mountSolved(withElbow(), 1, flags);
		moved.editConnection('L2', 'add pipe segment', (c) => ({ ...c, piping: addPipe(c.piping) }));
		moved.editConnection('L2', 'remove pipe', (c) => ({ ...c, piping: removePipe(c.piping, 0) }));
		await tick();
		// Pipe A is gone, and the fittings' pipes are not the ones solved: both are in the trace.
		const items = within(connectionStrip()).getAllByRole('listitem');
		expect(items.map((li) => li.textContent?.trim())).toEqual(['2 flags in the trace.']);
	});
});
