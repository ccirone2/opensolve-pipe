import { describe, expect, it } from 'vitest';
import { NOTICES_URL, REPOSITORY_URL, sourceLinks } from './links';

describe('sourceLinks', () => {
	it('points the source and the license at the commit the build was made from', () => {
		const sha = 'a8058212495687d2413e7cd5d1766ddbd885c843';
		expect(sourceLinks(sha)).toEqual({
			source: `${REPOSITORY_URL}/tree/${sha}`,
			license: `${REPOSITORY_URL}/blob/${sha}/LICENSE`
		});
	});

	it('falls back to the repository when the version is not a commit (a build without git)', () => {
		for (const version of [
			'1761234567890',
			'a805821',
			'',
			'A8058212495687D2413E7CD5D1766DDBD885C843'
		])
			expect(sourceLinks(version)).toEqual({
				source: REPOSITORY_URL,
				license: `${REPOSITORY_URL}/blob/HEAD/LICENSE`
			});
	});
});

it('serves the third-party licenses from the site root', () => {
	expect(NOTICES_URL).toBe('/third-party-licenses.txt');
});
