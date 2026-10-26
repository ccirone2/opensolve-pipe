/**
 * Local times and file names of an export (proposal export.md §3.5).
 *
 * Every local time an export writes (About, the file name, the zip's folder and entries' DOS
 * time, the goal seek's run time) is computed from the export's `now` and its `utcOffsetMinutes`
 * (−Date.getTimezoneOffset() at the click) by arithmetic, never from the machine's time zone, so
 * the same input gives the same file anywhere (W-WLP-1).
 *
 * File names: `{project} - {case} - {content} {YYYY-MM-DD HHmm}[ (not converged)].{ext}`, the case
 * left out without scenarios. Each part is sanitized (NFC; bidi controls and zero-width characters
 * removed; each run of whitespace one space; each run of characters Windows forbids, C0, DEL and
 * C1 controls one `_`, as Chromium does itself; spaces and dots trimmed at both ends) and cut by
 * grapheme to 60 (project), 40 (case) or 40 (content) characters; the whole name is at most 147
 * characters. Excel opens no file whose full path is longer than 218 characters, and Windows'
 * Extract All proposes `Downloads\{zip name}\results {time}\{file}`: with a 26-character
 * Downloads folder and the longest file, `scenario-changes.csv`, that path is
 * 26 + 1 + 143 + 1 + 23 + 1 + 20 = 215 characters at the cap, 3 below the limit (§3.1).
 */

/** The local calendar fields of `now` at `utcOffsetMinutes` from UTC. */
export interface LocalTime {
	year: number;
	month: number;
	day: number;
	hour: number;
	minute: number;
	second: number;
}

export function localTime(now: Date | number, utcOffsetMinutes: number): LocalTime {
	const ms = typeof now === 'number' ? now : now.getTime();
	const d = new Date(ms + utcOffsetMinutes * 60_000);
	return {
		year: d.getUTCFullYear(),
		month: d.getUTCMonth() + 1,
		day: d.getUTCDate(),
		hour: d.getUTCHours(),
		minute: d.getUTCMinutes(),
		second: d.getUTCSeconds()
	};
}

const pad = (n: number, width = 2) => String(n).padStart(width, '0');

/** "+02:00", "-05:30", "+00:00". */
export function offsetText(utcOffsetMinutes: number): string {
	const sign = utcOffsetMinutes < 0 ? '-' : '+';
	const minutes = Math.abs(utcOffsetMinutes);
	return `${sign}${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
}

/** ISO 8601 local time with its offset: "2026-10-25T14:32:05+02:00". */
export function localIso(now: Date | number, utcOffsetMinutes: number): string {
	const t = localTime(now, utcOffsetMinutes);
	return `${pad(t.year, 4)}-${pad(t.month)}-${pad(t.day)}T${pad(t.hour)}:${pad(t.minute)}:${pad(t.second)}${offsetText(utcOffsetMinutes)}`;
}

/** The file name's time: "2026-10-25 1432". */
export function fileStamp(now: Date | number, utcOffsetMinutes: number): string {
	const t = localTime(now, utcOffsetMinutes);
	return `${pad(t.year, 4)}-${pad(t.month)}-${pad(t.day)} ${pad(t.hour)}${pad(t.minute)}`;
}

/** The longest name, in characters (UTF-16 code units, as Windows counts a path): see above. */
export const MAX_NAME_LENGTH = 147;
export const PROJECT_PART_LENGTH = 60;
export const CASE_PART_LENGTH = 40;
export const CONTENT_PART_LENGTH = 40;

const BIDI_AND_ZERO_WIDTH = /[\u202A-\u202E\u2066-\u2069\u200B-\u200F\uFEFF]/g;
// eslint-disable-next-line no-control-regex -- C0, DEL and C1 controls are what it removes
const RESERVED = /[<>:"/\\|?*\u0000-\u001F\u007F-\u009F]+/g;

function graphemes(text: string): string[] {
	if (typeof Intl !== 'undefined' && 'Segmenter' in Intl) {
		const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
		return Array.from(segmenter.segment(text), (s) => s.segment);
	}
	return Array.from(text);
}

const trimEnds = (text: string) => text.replace(/^[ .]+|[ .]+$/g, '');

/**
 * One part of a file name, sanitized (see the module comment) and cut to `max` graphemes; ''
 * when nothing is left.
 */
export function sanitizePart(text: string, max: number): string {
	const clean = trimEnds(
		text
			.normalize('NFC')
			.replace(BIDI_AND_ZERO_WIDTH, '')
			.replace(/\s+/g, ' ')
			.replace(RESERVED, '_')
	);
	const parts = graphemes(clean);
	// Cut by grapheme; a cut can leave a space or a dot at the end, which is trimmed again.
	return parts.length > max ? trimEnds(parts.slice(0, max).join('')) : clean;
}

/** Drop the last grapheme of `text` (and the spaces and dots it then ends with). */
function shorten(text: string): string {
	const parts = graphemes(text);
	return trimEnds(parts.slice(0, -1).join(''));
}

export interface FileNameParts {
	project: string;
	/** The case ("Winter", "Base case", "All cases"); null without scenarios. */
	case: string | null;
	/** "results", "results (CSV)", "Transfer pump chart". */
	content: string;
	ext: string;
	now: Date | number;
	utcOffsetMinutes: number;
	/** The single exported case has a response without values. */
	notConverged?: boolean;
}

/**
 * The file name of an export (§3.5): "Booster station - Winter - results 2026-10-25 1432.xlsx".
 * An empty part becomes "Untitled project" (the project) or "results" (the case or the content).
 */
export function exportFileName(parts: FileNameParts): string {
	let project = sanitizePart(parts.project, PROJECT_PART_LENGTH) || 'Untitled project';
	let caseName =
		parts.case === null ? null : sanitizePart(parts.case, CASE_PART_LENGTH) || 'results';
	let content = sanitizePart(parts.content, CONTENT_PART_LENGTH) || 'results';
	const tail = ` ${fileStamp(parts.now, parts.utcOffsetMinutes)}${parts.notConverged ? ' (not converged)' : ''}.${parts.ext}`;
	const name = () =>
		[project, ...(caseName === null ? [] : [caseName]), content].join(' - ') + tail;
	// Within the cap: shorten the longest part, one grapheme at a time. The parts' caps (140
	// characters) and the tail (at most 38) leave every part long when the name is too long, so
	// none becomes empty.
	while (name().length > MAX_NAME_LENGTH) {
		const lengths = [project.length, caseName?.length ?? 0, content.length];
		const longest = lengths.indexOf(Math.max(...lengths));
		if (longest === 0) project = shorten(project);
		else if (longest === 1 && caseName !== null) caseName = shorten(caseName);
		else content = shorten(content);
	}
	return name();
}

/** The CSV zip's inner folder: "results 2026-10-25 1432" (never the file name: W-WLP-4). */
export function zipFolderName(now: Date | number, utcOffsetMinutes: number): string {
	return `results ${fileStamp(now, utcOffsetMinutes)}`;
}
