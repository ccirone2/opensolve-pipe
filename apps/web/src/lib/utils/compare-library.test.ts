/**
 * Compare and Build read a connection's solved pipes by identity (identity.ts, results.ts
 * linkReading): a pipe switched to a project library spec (CLAUDE.md D22), or whose spec is
 * edited, is still the pipe solved, so its last results stay on it, out of date. Results do not
 * change form with the library (proposal project-library.md §5.3). Made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { libraryProject } from '../testing/helpers';
import { link, pumpTransferSolved } from '../testing/results';
import { testWorkspace } from '../testing/workspace';
import { applyPipeSpec, setPipeSpec } from './project-library';
import { linkReading, outOfDateProject, readsAsSolved } from './results';

function solvedWorkspace() {
	const project = libraryProject();
	const one = link().segments[0]!;
	const solvedState = pumpTransferSolved({
		linkResults: {
			L1: link({ segments: [one, { ...one, index: 1 }] }),
			L2: link()
		}
	});
	return testWorkspace(project, {
		solver: { solve: async () => ({ success: true, computeTime: 0, solvedState, scenario: null }) }
	});
}

describe('a connection with spec pipes, read on it as it is now', () => {
	it('keeps its pipes through a switch to a spec and an edit of the spec', async () => {
		const ws = solvedWorkspace();
		await ws.store.solve();
		const read = () => {
			const solved = ws.store.solved!;
			return linkReading(ws.store.project, outOfDateProject(solved), solved, 'L1')!;
		};
		expect(readsAsSolved(read())).toBe(true);
		expect(
			ws.store.update(
				(p: Project) =>
					applyPipeSpec(p, 'PS2', { kind: 'pipe', connectionId: 'L1', pipeIndex: 1 }).project,
				'use spec'
			).ok
		).toBe(true);
		expect(ws.store.results.stale).toBe(true);
		expect(read().pipes.map((p) => (p ? [p.connectionId, p.index, p.sign] : null))).toEqual([
			['L1', 0, 1],
			['L1', 1, 1]
		]);
		expect(readsAsSolved(read())).toBe(true);
		// An edit of a spec changes no pipe object: the results go out of date, the pipes stay.
		await ws.store.solve();
		expect(ws.store.results.stale).toBe(false);
		expect(
			ws.store.update(
				(p: Project) => setPipeSpec(p, { ...p.pipeLibrary![0]!, innerDiameter: 0.11 }),
				'edit spec'
			).ok
		).toBe(true);
		expect(ws.store.results.stale).toBe(true);
		expect(readsAsSolved(read())).toBe(true);
		ws.store.dispose();
	});
});
