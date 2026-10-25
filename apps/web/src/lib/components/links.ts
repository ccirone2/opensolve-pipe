/** App links, resolved against the deployment's base path, and the disclaimer they lead to. */
import { version } from '$app/environment';
import { apiBaseUrl } from '$lib/api/client';
import { resolve } from '$app/paths';
import type { ResolvedPathname } from '$app/types';
import { NOTICES_FILE } from '$lib/notices';

/** The README disclaimer (GOALS §4.8), shown on the home page and under every result. */
export const DISCLAIMER =
	'OpenSolve Pipe is an engineering aid. Its results support, but do not replace, the judgment ' +
	'of a qualified engineer, and are provided without warranty.';

/** The source repository. */
export const REPOSITORY_URL = 'https://github.com/ccirone2/opensolve-pipe';

const COMMIT = /^[0-9a-f]{40}$/;

/**
 * The source and license links for a build. AGPL-3.0 §13 requires offering users the source of
 * the version they use, so with the commit the build was made from (svelte.config.js passes it
 * as the app version) both point at that commit. Any other version (a build without git) gets the
 * repository and its default branch.
 */
export function sourceLinks(appVersion: string): { source: string; license: string } {
	const ref = COMMIT.test(appVersion) ? appVersion : null;
	return ref
		? { source: `${REPOSITORY_URL}/tree/${ref}`, license: `${REPOSITORY_URL}/blob/${ref}/LICENSE` }
		: { source: REPOSITORY_URL, license: `${REPOSITORY_URL}/blob/HEAD/LICENSE` };
}

const links = sourceLinks(version);

/** The source code of this build (AGPL-3.0-or-later: the source must be offered to users). */
export const SOURCE_URL = links.source;

/** The license text, at the same commit. */
export const LICENSE_URL = links.license;

/**
 * The source code of the calculation server, which is deployed on its own and may run another
 * commit than this build: the API redirects /source to the commit it was built from (AGPL-3.0
 * §13; TSD §11.2). Nothing is requested until the link is followed.
 */
export function serverSourceHref(): string {
	return `${apiBaseUrl()}/source`;
}

/**
 * The licenses of the third-party code in the bundle (src/plugins/third-party-licenses.ts), at the
 * site root, which is where the site is served from (TSD §11.1).
 */
export const NOTICES_URL = `/${NOTICES_FILE}`;

/** The copyright notice (AGPL-3.0 §0, "Appropriate Legal Notices"). */
export const COPYRIGHT = 'Copyright © 2026 Chris Cirone';

/** The home page. */
export function homeHref(): ResolvedPathname {
	return resolve('/');
}

/** The project page; with an encoded project, the link that opens it. Without, a new project. */
export function projectHref(encoded = ''): ResolvedPathname {
	const path = resolve('/p');
	return (encoded ? `${path}#${encoded}` : path) as ResolvedPathname;
}

/** The home page's section on privacy, the disclaimer and the license. */
export function aboutHref(): ResolvedPathname {
	return `${resolve('/')}#about` as ResolvedPathname;
}
