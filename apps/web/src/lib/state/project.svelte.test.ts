/**
 * The store compiled for the browser: its state is reactive, so components update after
 * update(), undo() and redo().
 */
import { flushSync } from 'svelte';
import { describe, expect, it } from 'vitest';
import { EXAMPLES } from '../utils/examples';
import { ProjectStore } from './project.svelte';

describe('ProjectStore reactivity', () => {
	it('re-runs effects that read the project and the history flags', () => {
		const store = new ProjectStore(EXAMPLES[0]!.create(), { writeUrl: () => {} });
		const seen: string[] = [];
		const stop = $effect.root(() => {
			$effect(() => {
				seen.push(`${store.project.metadata.name} undo=${store.canUndo} redo=${store.canRedo}`);
			});
		});
		flushSync();
		store.update((p) => {
			p.metadata.name = 'Edited';
		}, 'Rename');
		flushSync();
		store.undo();
		flushSync();
		store.redo();
		flushSync();
		stop();
		expect(seen).toEqual([
			'Pump transfer between two tanks undo=false redo=false',
			'Edited undo=true redo=false',
			'Pump transfer between two tanks undo=false redo=true',
			'Edited undo=true redo=false'
		]);
		store.dispose();
	});

	it('re-runs effects that read results and the link length', async () => {
		const store = new ProjectStore(EXAMPLES[0]!.create(), {
			writeUrl: () => {},
			solver: {
				solve: async () => ({
					success: true,
					computeTime: 0,
					solvedState: { methodVersion: '1.0.0' } as never
				})
			}
		});
		const seen: string[] = [];
		const stop = $effect.root(() => {
			$effect(() => {
				seen.push(`solving=${store.results.solving} solved=${store.solved !== null}`);
			});
			$effect(() => {
				seen.push(`length=${store.encodedLength > 0}`);
			});
		});
		flushSync();
		const solving = store.solve();
		flushSync();
		await solving;
		flushSync();
		stop();
		expect(seen).toEqual([
			'solving=false solved=false',
			'length=true',
			'solving=true solved=false',
			'solving=false solved=true'
		]);
		store.dispose();
	});
});
