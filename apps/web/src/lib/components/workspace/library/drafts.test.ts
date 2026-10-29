/**
 * The library forms' blank-source rule (drafts.ts): a source is missing exactly when the schema's
 * `\S` refuses it, which pydantic-core reads as Rust's regex does (Unicode White_Space), not as
 * JavaScript's `trim()` (validate.ts apiPattern); and the source saved loses only that white space
 * at its ends.
 */
import { describe, expect, it } from 'vitest';
import { pipeSpecMissing, pipeSpecOf, resistanceMissing, resistanceOf } from './drafts';

const SOURCE_MISSING = expect.stringMatching(/^Enter where the values come from/);

describe("a library form's source", () => {
	it('is missing when the API refuses it as blank (Unicode White_Space only)', () => {
		for (const blank of ['', '   ', '\t\n', '\u0085', '\u3000', '\u00a0\u2028']) {
			expect(
				resistanceMissing({ id: 'RS1', kind: 'Cv', name: 'n', value: 1, source: blank })
			).toEqual({ source: SOURCE_MISSING });
			expect(
				pipeSpecMissing({
					id: 'PS1',
					materialId: 'carbon_steel',
					name: 'n',
					innerDiameter: 0.1,
					source: blank
				})
			).toEqual({ source: SOURCE_MISSING });
		}
	});

	it('is entered when the API accepts it, though trim() would empty it (U+FEFF)', () => {
		for (const text of ['\ufeff', '\u200b', ' \ufeff ']) {
			expect(
				resistanceMissing({ id: 'RS1', kind: 'Cv', name: 'n', value: 1, source: text })
			).toEqual({});
		}
		const entry = resistanceOf({ id: 'RS1', kind: 'Cv', name: 'n', value: 1, source: ' \ufeff ' });
		expect(entry.source).toBe('\ufeff');
	});

	it('is saved without the API white space at its ends', () => {
		const spec = pipeSpecOf({
			id: 'PS1',
			materialId: 'carbon_steel',
			name: ' Lined ',
			innerDiameter: 0.1,
			source: '\u0085 Datasheet rev 2\u3000'
		});
		expect(spec).toMatchObject({ name: 'Lined', source: 'Datasheet rev 2' });
	});
});
