import { afterEach, describe, expect, it, vi } from 'vitest';
import { NOTICES_URL, REPOSITORY_URL, serverSourceHref, sourceLinks } from './links';

const env = vi.hoisted(() => ({}) as Record<string, string | undefined>);
vi.mock('$env/dynamic/public', () => ({ env }));

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

describe('serverSourceHref', () => {
	afterEach(() => {
		delete env.PUBLIC_API_URL;
	});

	it("links the calculation server's /source, which redirects to the commit it runs", () => {
		expect(serverSourceHref()).toBe('http://localhost:8000/source');
		env.PUBLIC_API_URL = 'https://api.opensolve-pipe.app/';
		expect(serverSourceHref()).toBe('https://api.opensolve-pipe.app/source');
	});
});
