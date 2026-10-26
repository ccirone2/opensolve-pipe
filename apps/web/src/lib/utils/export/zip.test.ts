/**
 * The ZIP container (proposal export.md §3.3, §7.1), checked against node:zlib, not against itself:
 * the CRC-32 of a known string and node's crc32 over many chunks; every entry parsed by the
 * APPNOTE offsets and inflated by node's inflateRawSync; the UTF-8 name flag; the DOS time of the
 * export's local time; identical bytes for identical input; the refusals beyond the subset.
 */
import { crc32 as nodeCrc32 } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import { writeCsvZip } from './csv';
import type { ExportBundle } from './model';
import { crc32, dosDateTime, MAX_BYTES, MAX_ENTRIES, ZipWriter } from './zip';
import { readZip } from './zip-reader.testing';

async function bytesOf(blob: Blob): Promise<Uint8Array> {
	return new Uint8Array(await blob.arrayBuffer());
}

/** A deterministic generator of test bytes (xorshift32). */
function randomBytes(length: number, seed: number): Uint8Array {
	let x = seed >>> 0 || 1;
	const out = new Uint8Array(length);
	for (let i = 0; i < length; i++) {
		x ^= x << 13;
		x ^= x >>> 17;
		x ^= x << 5;
		out[i] = x & 0xff;
	}
	return out;
}

const NOW = new Date('2026-10-25T12:32:05Z');

describe('CRC-32', () => {
	it('of "The quick brown fox jumps over the lazy dog" is 414fa339', () => {
		const text = new TextEncoder().encode('The quick brown fox jumps over the lazy dog');
		expect(crc32(text).toString(16)).toBe('414fa339');
		expect(crc32(new Uint8Array(0))).toBe(0);
	});

	it('equals node:zlib crc32, incrementally over 200 chunks', () => {
		let ours = 0;
		let theirs = 0;
		for (let i = 0; i < 200; i++) {
			const chunk = randomBytes(1 + ((i * 7919) % 3000), i + 1);
			ours = crc32(chunk, ours);
			theirs = nodeCrc32(chunk, theirs);
			expect(ours).toBe(theirs);
		}
	});
});

describe('the DOS time', () => {
	it('is the local time of now at the offset, not UTC', () => {
		// 12:32:05Z at +02:00 is 14:32:05 local: 14 << 11 | 32 << 5 | 5 >> 1.
		const { time, date } = dosDateTime(NOW, 120);
		expect(time).toBe((14 << 11) | (32 << 5) | 2);
		expect(date).toBe(((2026 - 1980) << 9) | (10 << 5) | 25);
		// Across midnight: 23:30Z at +02:00 is 01:30 the next day.
		const late = dosDateTime(new Date('2026-12-31T23:30:00Z'), 120);
		expect(late.date).toBe(((2027 - 1980) << 9) | (1 << 5) | 1);
		expect(late.time).toBe((1 << 11) | (30 << 5));
		expect(dosDateTime(NOW, -300).time).toBe((7 << 11) | (32 << 5) | 2);
	});
});

describe('a zip', () => {
	it('holds each entry deflated, inflating back to its input, with UTF-8 names', async () => {
		const zip = new ZipWriter(NOW, 120);
		const big = randomBytes(300_000, 7);
		const text = 'Ü→ m³/s · −0.5\r\n'.repeat(10_000);
		zip.file('a.txt', 'hello');
		const entry = zip.entry('dir/größe.bin');
		entry.write(big.subarray(0, 100_000));
		entry.write(big.subarray(100_000));
		entry.end();
		zip.file('dir/text.csv', text);
		zip.file('empty.txt', '');
		const entries = readZip(await bytesOf(zip.finish('application/zip')));
		expect(entries.map((e) => e.name)).toEqual([
			'a.txt',
			'dir/größe.bin',
			'dir/text.csv',
			'empty.txt'
		]);
		expect(new TextDecoder().decode(entries[0]!.data)).toBe('hello');
		expect(entries[1]!.data).toEqual(big);
		expect(new TextDecoder().decode(entries[2]!.data)).toBe(text);
		expect(entries[3]!.data.length).toBe(0);
		for (const e of entries) {
			expect(e.flags).toBe(0x0800);
			expect(e.method).toBe(8);
			expect(e.crc).toBe(nodeCrc32(e.data));
			expect(e.time).toBe((14 << 11) | (32 << 5) | 2);
		}
	});

	it('is the same bytes for the same input', async () => {
		const make = async () => {
			const zip = new ZipWriter(NOW, 60);
			zip.file('x.txt', 'same');
			zip.file('y.bin', randomBytes(70_000, 3));
			return bytesOf(zip.finish('application/zip'));
		};
		expect(await make()).toEqual(await make());
	});

	it('refuses an entry before the last one ended, and more than the subset holds', () => {
		const zip = new ZipWriter(NOW, 0);
		zip.entry('open.txt');
		expect(() => zip.entry('next.txt')).toThrow(/has not ended/);
		const full = new ZipWriter(NOW, 0);
		for (let i = 0; i < MAX_ENTRIES; i++) {
			full.add(`f${i}`, { crc: 0, size: 0, compressed: 0, chunks: [] });
		}
		expect(() => full.entry('one more')).toThrow(/65535 entries/);
		const large = new ZipWriter(NOW, 0);
		expect(() =>
			large.add('huge', { crc: 0, size: MAX_BYTES, compressed: MAX_BYTES, chunks: [] })
		).toThrow(/ZIP64/);
	});
});

function documentBundle(): ExportBundle {
	return {
		sheets: [
			{
				id: 'about',
				title: 'About',
				file: 'about.csv',
				kind: 'document',
				caption: 'About',
				columns: [
					{ label: 'Section', kind: 'text' },
					{ label: 'Item', kind: 'text' },
					{ label: 'Value', kind: 'text' }
				],
				rowCount: 1,
				rows: () => [['Export', 'Title', 'OpenSolve Pipe results']]
			},
			{
				id: 'methods',
				title: 'Methods',
				file: 'methods.txt',
				kind: 'document',
				caption: 'Methods',
				columns: [{ label: 'Text', kind: 'text' }],
				rowCount: 2,
				rows: () => [['line 1'], ['line 2']],
				text: () => ['line 1', 'line 2']
			}
		],
		omitted: [],
		warnings: [],
		fileName: 'x.zip',
		folder: 'results 2026-10-25 1432',
		title: 'x',
		created: NOW,
		utcOffsetMinutes: 120,
		readme: ['OpenSolve Pipe results', '', 'Read me.']
	};
}

describe('the CSV zip', () => {
	it('puts every file under its folder, README.txt first, CSV with a BOM and text with CRLF', async () => {
		const entries = readZip(await bytesOf(await writeCsvZip(documentBundle())));
		expect(entries.map((e) => e.name)).toEqual([
			'results 2026-10-25 1432/README.txt',
			'results 2026-10-25 1432/about.csv',
			'results 2026-10-25 1432/methods.txt'
		]);
		// ignoreBOM: keep the BOM in the text, to check it is there.
		const text = (i: number) =>
			new TextDecoder('utf-8', { ignoreBOM: true }).decode(entries[i]!.data);
		expect(text(0)).toBe('OpenSolve Pipe results\r\n\r\nRead me.\r\n');
		expect(Array.from(entries[1]!.data.subarray(0, 3))).toEqual([0xef, 0xbb, 0xbf]);
		expect(text(1)).toBe('\uFEFFSection,Item,Value\r\nExport,Title,OpenSolve Pipe results\r\n');
		expect(text(2)).toBe('line 1\r\nline 2\r\n');
	});

	it('stops with an AbortError when its signal is aborted', async () => {
		const controller = new AbortController();
		controller.abort();
		await expect(writeCsvZip(documentBundle(), { signal: controller.signal })).rejects.toThrow(
			/cancelled/
		);
	});
});
