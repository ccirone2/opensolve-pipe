/**
 * Results tables compiled for the browser: a table derived from a solve, as the Links view derives
 * its own, follows its results going out of date (proposal export.md decision 8). The solved
 * state is a made-up test input (testing/results.ts).
 */
import { flushSync } from 'svelte';
import { describe, expect, it } from 'vitest';
import { pumpTransferSolved } from '../testing/results';
import { testWorkspace } from '../testing/workspace';
import { pumpTransferExample } from './examples';
import { linkTable } from './results';

describe('link names from the project the results belong to', () => {
	it('re-derive when the results go out of date with no label changed', async () => {
		const ws = testWorkspace(pumpTransferExample(), {
			solver: {
				solve: async () => ({
					success: true,
					computeTime: 0,
					solvedState: pumpTransferSolved(),
					scenario: null
				})
			}
		});
		await ws.store.solve();
		const seen: string[] = [];
		const stop = $effect.root(() => {
			const table = $derived(linkTable(ws.labelsProject, ws.store.solved!, ws.displayUnits));
			$effect(() => {
				seen.push(table.rows.find((r) => r.key === 'L2')!.name);
			});
		});
		flushSync();
		// A name is not hydraulic: the results stay current and show it.
		ws.store.update((p) => {
			p.components.find((c) => c.id === 'V1')!.name = 'Gate valve';
		}, 'Rename');
		flushSync();
		// A length is: the results go out of date, and are named as solved (labelsProject is the same).
		const labels = ws.labelsProject;
		ws.store.update((p) => {
			p.connections.find((c) => c.id === 'L1')!.piping.pipes[0]!.length = 12;
		}, 'Edit length');
		flushSync();
		expect(ws.labelsProject).toBe(labels);
		expect(ws.store.results.stale).toBe(true);
		// Undone, they are current again.
		ws.store.undo();
		flushSync();
		stop();
		expect(seen).toEqual([
			'Transfer pump → Discharge isolation valve',
			'Transfer pump → Gate valve',
			'Transfer pump → Discharge isolation valve',
			'Transfer pump → Gate valve'
		]);
		ws.store.dispose();
	});
});
