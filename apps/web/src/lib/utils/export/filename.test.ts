/**
 * File names and local times of an export (proposal export.md §3.5, §7.1): NFC; whitespace,
 * reserved, bidi and zero-width characters; leading and trailing dots and spaces; grapheme cuts;
 * empty parts; the 147-character cap and the longest path Extract All proposes; the local time
 * from `now` and the offset (the same under two time zones of the machine); the "(not
 * converged)" suffix; the zip's inner folder.
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
	exportFileName,
	fileStamp,
	localIso,
	MAX_NAME_LENGTH,
	offsetText,
	sanitizePart,
	zipFolderName
} from './filename';
import { fixtureInput, FIXTURE_NAMES } from './export-testing.testing';
import { buildExport } from './model';

const NOW = new Date('2026-10-25T12:32:05Z');
const base = { now: NOW, utcOffsetMinutes: 120, ext: 'xlsx', content: 'results', case: null };
const savedTz = process.env.TZ;

afterEach(() => {
	process.env.TZ = savedTz;
});

describe('local times', () => {
	it('come from now and the offset, by arithmetic', () => {
		expect(localIso(NOW, 120)).toBe('2026-10-25T14:32:05+02:00');
		expect(localIso(NOW, -330)).toBe('2026-10-25T07:02:05-05:30');
		expect(localIso(NOW, 0)).toBe('2026-10-25T12:32:05+00:00');
		expect(fileStamp(NOW, 120)).toBe('2026-10-25 1432');
		expect(fileStamp(new Date('2026-12-31T23:30:00Z'), 60)).toBe('2027-01-01 0030');
		expect(offsetText(345)).toBe('+05:45');
	});

	it('do not depend on the machine’s time zone', () => {
		process.env.TZ = 'America/Los_Angeles';
		const west = [localIso(NOW, 120), exportFileName({ ...base, project: 'P' })];
		process.env.TZ = 'Asia/Tokyo';
		const east = [localIso(NOW, 120), exportFileName({ ...base, project: 'P' })];
		expect(west).toEqual(east);
		expect(west[1]).toBe('P - results 2026-10-25 1432.xlsx');
	});
});

describe('a part of a name', () => {
	it('is NFC', () => {
		expect(sanitizePart('Café', 60)).toBe('Café');
	});

	it('turns each run of whitespace (NBSP and U+2028 too) into one space', () => {
		expect(sanitizePart('Booster\u00A0\u00A0station\u2028 two\t\nlines', 60)).toBe(
			'Booster station two lines'
		);
	});

	it('turns each run of reserved and control characters into one _', () => {
		expect(sanitizePart('a<>:"/\\|?*b', 60)).toBe('a_b');
		expect(sanitizePart('x\u0001\u007f\u0085y', 60)).toBe('x_y');
		expect(sanitizePart('Tank: 1/2', 60)).toBe('Tank_ 1_2');
	});

	it('drops bidi controls and zero-width characters', () => {
		expect(sanitizePart('\u202Eabc\u202C\u200B\u200D\u2066d\u2069\uFEFF', 60)).toBe('abcd');
	});

	it('trims spaces and dots at both ends', () => {
		expect(sanitizePart(' ..Booster. ', 60)).toBe('Booster');
		expect(sanitizePart('...', 60)).toBe('');
	});

	it('is cut by grapheme, never inside one, and trimmed again', () => {
		// A flag is one grapheme of two code points. (A ZWJ sequence loses its joiners: U+200D is a
		// zero-width character, which §3.5 removes.)
		expect(sanitizePart('🇩🇪🇫🇷🇮🇹', 2)).toBe('🇩🇪🇫🇷');
		expect(sanitizePart('a\u0323\u0308bc', 2)).toBe('\u1ea1\u0308b');
		expect(sanitizePart('ab cd', 3)).toBe('ab');
		expect(sanitizePart('x'.repeat(100), 60)).toBe('x'.repeat(60));
	});

	it('is cut by code point where Intl.Segmenter is missing', () => {
		const intl = Intl as unknown as { Segmenter?: unknown };
		const segmenter = intl.Segmenter;
		try {
			delete intl.Segmenter;
			expect(sanitizePart('🇩🇪🇫🇷', 3)).toBe('🇩🇪🇫');
		} finally {
			intl.Segmenter = segmenter;
		}
	});
});

describe('a file name', () => {
	it('follows the pattern, with the case only with scenarios', () => {
		expect(exportFileName({ ...base, project: 'Pump transfer between two tanks' })).toBe(
			'Pump transfer between two tanks - results 2026-10-25 1432.xlsx'
		);
		expect(
			exportFileName({
				...base,
				project: 'Booster station',
				case: 'Winter',
				content: 'results (CSV)',
				ext: 'zip'
			})
		).toBe('Booster station - Winter - results (CSV) 2026-10-25 1432.zip');
		expect(exportFileName({ ...base, project: 'Booster station', case: 'All cases' })).toBe(
			'Booster station - All cases - results 2026-10-25 1432.xlsx'
		);
		expect(
			exportFileName({
				...base,
				project: 'Booster station',
				case: 'Base case',
				content: 'Transfer pump chart',
				ext: 'png'
			})
		).toBe('Booster station - Base case - Transfer pump chart 2026-10-25 1432.png');
	});

	it('says "(not converged)" when the case has a response without values', () => {
		expect(exportFileName({ ...base, project: 'P', notConverged: true })).toBe(
			'P - results 2026-10-25 1432 (not converged).xlsx'
		);
	});

	it('falls back to "Untitled project" and "results" for empty parts', () => {
		expect(exportFileName({ ...base, project: ' .. ', case: '\u200B', content: '' })).toBe(
			'Untitled project - results - results 2026-10-25 1432.xlsx'
		);
	});

	it('is at most MAX_NAME_LENGTH (147) characters, whatever the parts', () => {
		const name = exportFileName({
			...base,
			project: 'P'.repeat(200),
			case: 'C'.repeat(200),
			content: 'R'.repeat(200),
			notConverged: true
		});
		expect(name.length).toBe(MAX_NAME_LENGTH);
		expect(name.endsWith(' 2026-10-25 1432 (not converged).xlsx')).toBe(true);
		const [project, caseName] = name.split(' - ');
		expect(project?.length).toBeLessThanOrEqual(60);
		expect(caseName?.length).toBeLessThanOrEqual(40);
	});

	it('keeps Unicode', () => {
		expect(exportFileName({ ...base, project: 'Pumpstation Süd – Kühlwasser' })).toBe(
			'Pumpstation Süd – Kühlwasser - results 2026-10-25 1432.xlsx'
		);
	});
});

describe("the CSV zip's folder", () => {
	it('is "results" and the local time, never the file name', () => {
		expect(zipFolderName(NOW, 120)).toBe('results 2026-10-25 1432');
	});

	it('keeps the longest path Extract All proposes within 215 characters (W-WLP-4, review F5)', () => {
		// §2.5's files: the longest name a zip can hold.
		const FILES = [
			'README.txt',
			'about.csv',
			'flags.csv',
			'design-checks.csv',
			'compare-cases.csv',
			'nodes.csv',
			'links.csv',
			'pipes.csv',
			'fittings.csv',
			'pumps.csv',
			'pump-curves.csv',
			'system-curves.csv',
			'valves.csv',
			'equipment.csv',
			'branches.csv',
			'branch-ports.csv',
			'boundaries.csv',
			'boundary-ports.csv',
			'assigned-flows.csv',
			'scenario-changes.csv',
			'goal-seek.txt',
			'methods.txt',
			'trace.csv'
		];
		for (const name of FIXTURE_NAMES) {
			for (const cases of ['shown', 'all'] as const) {
				const bundle = buildExport(fixtureInput(name, { format: 'csv', cases }));
				for (const sheet of bundle.sheets) expect(FILES).toContain(sheet.file);
			}
		}
		const longest = FILES.reduce((a, b) => (b.length > a.length ? b : a));
		expect(longest).toBe('scenario-changes.csv');
		// The design's reference: a 26-character Downloads folder; Extract All proposes
		// Downloads\{zip name without .zip}\, and in it the zip's own folder.
		const downloads = 'C:\\Users\\abcdefg\\Downloads';
		expect(downloads).toHaveLength(26);
		const zip = exportFileName({
			...base,
			ext: 'zip',
			content: 'results (CSV)',
			project: 'P'.repeat(200),
			case: 'C'.repeat(200),
			notConverged: true
		});
		expect(zip).toHaveLength(MAX_NAME_LENGTH);
		const path = [downloads, zip.replace(/\.zip$/, ''), zipFolderName(NOW, 120), longest].join(
			'\\'
		);
		expect(path.length).toBeLessThanOrEqual(215);
	});
});
