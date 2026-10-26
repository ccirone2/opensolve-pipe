/**
 * Cooperative building (proposal export.md §3.6): a yield after every 500 rows or 64 KiB of text,
 * the AbortSignal checked at each, and an AbortError when it is aborted; the writers stop at the
 * next slice of a long sheet.
 */
import { describe, expect, it } from 'vitest';
import type { ExportBundle } from './model';
import { CHARS_PER_SLICE, isAbortError, nextTask, Pacer, ROWS_PER_SLICE } from './yield';
import { writeXlsx } from './xlsx';
import { writeCsvZip } from './csv';

describe('the pacer', () => {
	it('yields after 500 rows, or after 64 KiB of text', async () => {
		let yields = 0;
		const pacer = new Pacer(undefined, async () => {
			yields++;
		});
		for (let i = 0; i < ROWS_PER_SLICE * 3; i++) await pacer.row(10);
		expect(yields).toBe(3);
		await pacer.row(CHARS_PER_SLICE);
		expect(yields).toBe(4);
	});

	it('throws an AbortError at the yield after its signal is aborted', async () => {
		const controller = new AbortController();
		const pacer = new Pacer(controller.signal, async () => {});
		await pacer.row(1);
		controller.abort();
		const error = await pacer.pause().catch((e: unknown) => e);
		expect(isAbortError(error)).toBe(true);
	});

	it('gives other tasks a turn: a message posted before runs first', async () => {
		const order: string[] = [];
		const channel = new MessageChannel();
		channel.port1.onmessage = () => {
			order.push('other');
			channel.port1.close();
		};
		channel.port2.postMessage(null);
		await nextTask();
		order.push('after yield');
		expect(order).toEqual(['other', 'after yield']);
	});
});

/** A bundle of one long sheet, whose rows abort the build halfway. */
function longBundle(onRow: (i: number) => void): ExportBundle {
	return {
		sheets: [
			{
				id: 'nodes',
				title: 'Nodes',
				file: 'nodes.csv',
				kind: 'table',
				caption: 'Nodes',
				columns: [{ label: 'x', kind: 'number' }],
				rowCount: 5000,
				*rows() {
					for (let i = 0; i < 5000; i++) {
						onRow(i);
						yield [i];
					}
				}
			}
		],
		omitted: [],
		warnings: [],
		fileName: 'x',
		folder: 'results 2026-10-25 1432',
		title: 'x',
		created: new Date('2026-10-25T12:32:05Z'),
		utcOffsetMinutes: 0,
		readme: []
	};
}

describe('a build in progress', () => {
	it.each([
		['the workbook', writeXlsx],
		['the CSV zip', writeCsvZip]
	] as const)(
		'%s stops at the next slice once cancelled, with an AbortError',
		async (_name, write) => {
			const controller = new AbortController();
			let last = 0;
			const bundle = longBundle((i) => {
				last = i;
				if (i === 1200) controller.abort();
			});
			const error = await write(bundle, { signal: controller.signal }).catch((e: unknown) => e);
			expect(isAbortError(error)).toBe(true);
			expect(last).toBeLessThan(1200 + ROWS_PER_SLICE);
		}
	);

	it('reports its progress sheet by sheet', async () => {
		const progress: unknown[] = [];
		await writeXlsx(
			longBundle(() => {}),
			{ onProgress: (p) => progress.push(p) }
		);
		expect(progress).toEqual([{ sheet: 1, sheets: 1, title: 'Nodes' }]);
	});
});
