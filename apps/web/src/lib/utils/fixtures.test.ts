/**
 * Every released project schema version keeps a fixture link that must always open (D2,
 * SDD §5.2, TSD §4.7). The fixture links are never edited once committed.
 */
import { createHash } from 'node:crypto';
import { ungzip } from 'pako';
import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { canonicalJson, decodeProject, encodeProject, fragmentOf, fromBase64Url } from './encoding';
import { CURRENT_SCHEMA_VERSION, migrate } from './migrations';
import { parseProject, projectProblems } from './validate';

const links = import.meta.glob<string>('./__fixtures__/schema-v*.txt', {
	query: '?raw',
	import: 'default',
	eager: true
});
const projects = import.meta.glob<unknown>('./__fixtures__/schema-v*.json', {
	import: 'default',
	eager: true
});

describe('schema fixtures', () => {
	it('exist for every released schema version', () => {
		for (let version = 1; version <= CURRENT_SCHEMA_VERSION; version++) {
			expect(links[`./__fixtures__/schema-v${version}.txt`], `schema-v${version}.txt`).toBeTypeOf(
				'string'
			);
			expect(
				projects[`./__fixtures__/schema-v${version}.json`],
				`schema-v${version}.json`
			).toBeDefined();
		}
	});

	it('schema-v1.txt decodes to exactly schema-v1.json', () => {
		const text = links['./__fixtures__/schema-v1.txt'] ?? '';
		expect(decodeProject(fragmentOf(text))).toEqual(projects['./__fixtures__/schema-v1.json']);
	});

	it('schema-v1.txt is the committed link, unchanged', () => {
		// Links already shared must keep opening, so the fixture link must never be regenerated
		// (not even together with its JSON). This pins its exact text; if this fails, restore the
		// file instead of updating the hash. A schema change needs a new version, a migration and
		// a new fixture (schema-v2.txt), never a new schema-v1.txt.
		const text = links['./__fixtures__/schema-v1.txt']?.trim() ?? '';
		expect(createHash('sha256').update(text).digest('hex')).toBe(
			'2f192eee9b2251c0c0f2beacde603a62154f231d9a9121496c000ec9aa3c8954'
		);
	});

	it('schema-v1.txt is a full shareable link', () => {
		expect(links['./__fixtures__/schema-v1.txt']?.trim()).toMatch(
			/^https:\/\/opensolve-pipe\.app\/p#[A-Za-z0-9_-]+$/
		);
	});

	for (const [path, text] of Object.entries(links)) {
		it(`${path} decodes to its JSON`, () => {
			const expected = projects[path.replace(/\.txt$/, '.json')];
			expect(expected).toBeDefined();
			const decoded = decodeProject(fragmentOf(text));
			expect(decoded.schemaVersion).toBe(CURRENT_SCHEMA_VERSION);
			// The link holds exactly its JSON, upgraded to the current version.
			expect(decoded).toEqual(parseProject(migrate(structuredClone(expected))));
			expect(projectProblems(decoded)).toEqual([]);
		});
	}
});

describe('encodeProject', () => {
	const fixture = projects['./__fixtures__/schema-v1.json'] as Project;

	it('gzips canonical JSON at level 9 (gzip header XFL = 2, maximum compression)', () => {
		const bytes = fromBase64Url(encodeProject(fixture));
		// RFC 1952 §2.3: ID1 ID2 CM FLG MTIME(4) XFL OS. XFL 2: slowest, maximum compression.
		expect([...bytes.slice(0, 4)]).toEqual([0x1f, 0x8b, 0x08, 0x00]);
		expect(bytes[8]).toBe(0x02);
		expect(new TextDecoder().decode(ungzip(bytes))).toBe(canonicalJson(fixture));
	});

	it('reproduces the committed v1 link byte for byte from its JSON', () => {
		// Canonical JSON, gzip level 9 and base64url without padding, as when the fixture was
		// made. (Decoding does not depend on this; it shows the encoder itself has not changed.)
		const link = links['./__fixtures__/schema-v1.txt']?.trim() ?? '';
		expect(encodeProject(fixture)).toBe(fragmentOf(link));
	});
});
