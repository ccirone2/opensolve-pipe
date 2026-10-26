/**
 * A ZIP container (PKWARE APPNOTE 6.3 subset; proposal export.md §3.3) on pako's raw Deflate, which
 * the app already bundles for its links: the workbook (.xlsx is a zip) and the CSV files' zip.
 *
 * - Each entry: a local header (version needed 2.0; flag 0x0800, UTF-8 names; method 8, deflate;
 *   the DOS time and date of the export's local time; CRC-32; sizes; name), then its deflated
 *   data. Then one central-directory record per entry and the end-of-central-directory record.
 * - No data descriptors: an entry is compressed before its header is written. Its compressed
 *   chunks are kept as Blob parts, never concatenated in JavaScript memory.
 * - Deflate level 3 (35 % faster than level 6 for files 7 % larger, measured), 64 KiB chunks;
 *   pako's onData hands over each full buffer, which is kept without copying (pako allocates a
 *   new one for the next).
 * - CRC-32: IEEE 802.3, reflected polynomial 0xEDB88320, a 256-entry table, incremental.
 * - No ZIP64: more than 65,535 entries or 4 GiB is refused (neither can happen: §3.2).
 *
 * The bytes depend only on the entries and the time given: no clock, time zone or random source.
 */
import { Deflate } from 'pako';
import { localTime } from './filename';

const CRC_TABLE = (() => {
	const table = new Uint32Array(256);
	for (let n = 0; n < 256; n++) {
		let c = n;
		for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
		table[n] = c >>> 0;
	}
	return table;
})();

/** CRC-32 of `data`, continuing from `crc` (the CRC of the bytes before; 0 to start). */
export function crc32(data: Uint8Array, crc = 0): number {
	let c = ~crc >>> 0;
	for (let i = 0; i < data.length; i++) {
		c = (CRC_TABLE[(c ^ (data[i] as number)) & 0xff] as number) ^ (c >>> 8);
	}
	return ~c >>> 0;
}

/** MS-DOS time and date fields of a local time (2 s resolution; years from 1980). */
export function dosDateTime(now: Date | number, utcOffsetMinutes: number) {
	const t = localTime(now, utcOffsetMinutes);
	if (t.year < 1980) return { time: 0, date: (1 << 5) | 1 };
	return {
		time: (t.hour << 11) | (t.minute << 5) | (t.second >> 1),
		date: ((t.year - 1980) << 9) | (t.month << 5) | t.day
	};
}

export const MAX_ENTRIES = 0xffff;
/** Sizes and offsets are 32-bit (no ZIP64). */
export const MAX_BYTES = 0xffffffff;

export const DEFLATE_LEVEL = 3;
const CHUNK_SIZE = 64 * 1024;
/** Characters of text buffered before they are encoded and deflated. */
const TEXT_BUFFER = 64 * 1024;

const encoder = new TextEncoder();

function header(size: number): { bytes: Uint8Array<ArrayBuffer>; view: DataView } {
	const bytes = new Uint8Array(size);
	return { bytes, view: new DataView(bytes.buffer) };
}

/** One entry being written: text and bytes go in, deflated, until end(). */
export class ZipEntry {
	readonly name: string;
	#zip: ZipWriter;
	#deflate = new Deflate({ raw: true, level: DEFLATE_LEVEL, chunkSize: CHUNK_SIZE });
	#chunks: Uint8Array<ArrayBuffer>[] = [];
	#compressed = 0;
	#size = 0;
	#crc = 0;
	#text: string[] = [];
	#textLength = 0;
	#ended = false;

	constructor(zip: ZipWriter, name: string) {
		this.#zip = zip;
		this.name = name;
		this.#deflate.onData = (chunk) => {
			this.#chunks.push(chunk);
			this.#compressed += chunk.length;
		};
	}

	/** Append text (UTF-8) or bytes. */
	write(data: string | Uint8Array): void {
		if (this.#ended) throw new Error(`The zip entry ${this.name} is closed.`);
		if (typeof data === 'string') {
			if (!data) return;
			this.#text.push(data);
			this.#textLength += data.length;
			if (this.#textLength >= TEXT_BUFFER) this.#flushText();
			return;
		}
		this.#flushText();
		this.#push(data);
	}

	#flushText(): void {
		if (!this.#text.length) return;
		const bytes = encoder.encode(this.#text.join(''));
		this.#text = [];
		this.#textLength = 0;
		this.#push(bytes);
	}

	#push(bytes: Uint8Array): void {
		if (!bytes.length) return;
		this.#crc = crc32(bytes, this.#crc);
		this.#size += bytes.length;
		if (this.#size > MAX_BYTES) throw new Error('The file is too large for a zip without ZIP64.');
		if (!this.#deflate.push(bytes, false)) throw new Error(this.#deflate.msg || 'Deflate failed.');
	}

	/** Finish the entry: its header and data go into the zip. */
	end(): void {
		if (this.#ended) return;
		this.#flushText();
		if (!this.#deflate.push(new Uint8Array(0), true) || this.#deflate.err) {
			throw new Error(this.#deflate.msg || 'Deflate failed.');
		}
		this.#ended = true;
		this.#zip.add(this.name, {
			crc: this.#crc,
			size: this.#size,
			compressed: this.#compressed,
			chunks: this.#chunks
		});
		this.#chunks = [];
	}
}

interface CentralRecord {
	name: Uint8Array;
	crc: number;
	size: number;
	compressed: number;
	offset: number;
}

/**
 * A zip being written. `now` and `utcOffsetMinutes` give every entry's DOS time: the export's
 * local time (DOS time has no zone, and Explorer, Archive Utility and `unzip -l` show it as local).
 */
export class ZipWriter {
	readonly #parts: BlobPart[] = [];
	readonly #records: CentralRecord[] = [];
	readonly #time: number;
	readonly #date: number;
	#offset = 0;
	#open: ZipEntry | null = null;
	#finished = false;

	constructor(now: Date | number, utcOffsetMinutes: number) {
		const { time, date } = dosDateTime(now, utcOffsetMinutes);
		this.#time = time;
		this.#date = date;
	}

	/** Start an entry; the one before must have ended. */
	entry(name: string): ZipEntry {
		if (this.#finished) throw new Error('The zip is finished.');
		if (this.#open) throw new Error(`The zip entry ${this.#open.name} has not ended.`);
		if (this.#records.length >= MAX_ENTRIES) {
			throw new Error(`A zip without ZIP64 holds at most ${MAX_ENTRIES} entries.`);
		}
		this.#open = new ZipEntry(this, name);
		return this.#open;
	}

	/** Write a whole entry at once. */
	file(name: string, data: string | Uint8Array): void {
		const entry = this.entry(name);
		entry.write(data);
		entry.end();
	}

	/** Called by ZipEntry.end(). */
	add(
		name: string,
		data: {
			crc: number;
			size: number;
			compressed: number;
			chunks: readonly Uint8Array<ArrayBuffer>[];
		}
	): void {
		this.#open = null;
		const nameBytes = encoder.encode(name);
		const local = header(30 + nameBytes.length);
		const v = local.view;
		v.setUint32(0, 0x04034b50, true);
		v.setUint16(4, 20, true); // version needed: 2.0 (deflate)
		v.setUint16(6, 0x0800, true); // UTF-8 names
		v.setUint16(8, 8, true); // deflate
		v.setUint16(10, this.#time, true);
		v.setUint16(12, this.#date, true);
		v.setUint32(14, data.crc, true);
		v.setUint32(18, data.compressed, true);
		v.setUint32(22, data.size, true);
		v.setUint16(26, nameBytes.length, true);
		v.setUint16(28, 0, true); // no extra field
		local.bytes.set(nameBytes, 30);
		const end = this.#offset + local.bytes.length + data.compressed;
		if (end > MAX_BYTES) throw new Error('The file is too large for a zip without ZIP64.');
		this.#records.push({
			name: nameBytes,
			crc: data.crc,
			size: data.size,
			compressed: data.compressed,
			offset: this.#offset
		});
		this.#parts.push(local.bytes, ...data.chunks);
		this.#offset = end;
	}

	/** The zip: its entries, the central directory and the end record. */
	finish(type: string): Blob {
		if (this.#open) throw new Error(`The zip entry ${this.#open.name} has not ended.`);
		this.#finished = true;
		const start = this.#offset;
		let size = 0;
		for (const r of this.#records) {
			const central = header(46 + r.name.length);
			const v = central.view;
			v.setUint32(0, 0x02014b50, true);
			v.setUint16(4, 20, true); // made by: MS-DOS, 2.0
			v.setUint16(6, 20, true); // version needed
			v.setUint16(8, 0x0800, true);
			v.setUint16(10, 8, true);
			v.setUint16(12, this.#time, true);
			v.setUint16(14, this.#date, true);
			v.setUint32(16, r.crc, true);
			v.setUint32(20, r.compressed, true);
			v.setUint32(24, r.size, true);
			v.setUint16(28, r.name.length, true);
			// extra, comment, disk number, internal and external attributes: 0
			v.setUint32(42, r.offset, true);
			central.bytes.set(r.name, 46);
			this.#parts.push(central.bytes);
			size += central.bytes.length;
		}
		if (start + size > MAX_BYTES) throw new Error('The file is too large for a zip without ZIP64.');
		const eocd = header(22);
		const v = eocd.view;
		v.setUint32(0, 0x06054b50, true);
		v.setUint16(8, this.#records.length, true);
		v.setUint16(10, this.#records.length, true);
		v.setUint32(12, size, true);
		v.setUint32(16, start, true);
		this.#parts.push(eocd.bytes);
		return new Blob(this.#parts, { type });
	}
}
