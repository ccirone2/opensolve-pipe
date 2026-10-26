/**
 * A zip reader for the export's tests (not used by the app): it reads an archive by PKWARE
 * APPNOTE's offsets (the end record, the central directory, each local header) and inflates each
 * entry with node:zlib, an implementation independent of the writer's.
 */
import { inflateRawSync } from 'node:zlib';
import { expect } from 'vitest';

export interface ZipEntryRead {
	name: string;
	flags: number;
	method: number;
	time: number;
	date: number;
	crc: number;
	data: Uint8Array;
}

/** Every entry of a zip, in central-directory order, with its data inflated. */
export function readZip(bytes: Uint8Array): ZipEntryRead[] {
	const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
	const end = bytes.length - 22;
	expect(view.getUint32(end, true)).toBe(0x06054b50);
	const count = view.getUint16(end + 10, true);
	const cdSize = view.getUint32(end + 12, true);
	let at = view.getUint32(end + 16, true);
	expect(at + cdSize).toBe(end);
	const decoder = new TextDecoder('utf-8', { fatal: true });
	const entries: ZipEntryRead[] = [];
	for (let i = 0; i < count; i++) {
		expect(view.getUint32(at, true)).toBe(0x02014b50);
		const flags = view.getUint16(at + 8, true);
		const method = view.getUint16(at + 10, true);
		const time = view.getUint16(at + 12, true);
		const date = view.getUint16(at + 14, true);
		const crc = view.getUint32(at + 16, true);
		const compressed = view.getUint32(at + 20, true);
		const size = view.getUint32(at + 24, true);
		const nameLength = view.getUint16(at + 28, true);
		const extra = view.getUint16(at + 30, true);
		const comment = view.getUint16(at + 32, true);
		const offset = view.getUint32(at + 42, true);
		const name = decoder.decode(bytes.subarray(at + 46, at + 46 + nameLength));
		// The local header repeats the record.
		expect(view.getUint32(offset, true)).toBe(0x04034b50);
		expect(view.getUint16(offset + 6, true)).toBe(flags);
		expect(view.getUint32(offset + 14, true)).toBe(crc);
		expect(view.getUint32(offset + 18, true)).toBe(compressed);
		expect(view.getUint32(offset + 22, true)).toBe(size);
		const localName = view.getUint16(offset + 26, true);
		const localExtra = view.getUint16(offset + 28, true);
		const start = offset + 30 + localName + localExtra;
		const data = new Uint8Array(inflateRawSync(bytes.subarray(start, start + compressed)));
		expect(data.length).toBe(size);
		entries.push({ name, flags, method, time, date, crc, data });
		at += 46 + nameLength + extra + comment;
	}
	return entries;
}

/** An entry's text (UTF-8, its BOM kept). */
export function entryText(entries: readonly ZipEntryRead[], name: string): string {
	const entry = entries.find((e) => e.name === name);
	if (!entry) throw new Error(`No zip entry ${name}`);
	return new TextDecoder('utf-8', { ignoreBOM: true }).decode(entry.data);
}

export async function blobBytes(blob: Blob): Promise<Uint8Array> {
	return new Uint8Array(await blob.arrayBuffer());
}
