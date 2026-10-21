/** App links, resolved against the deployment's base path, and the disclaimer they lead to. */
import { resolve } from '$app/paths';
import type { ResolvedPathname } from '$app/types';

/** The README disclaimer (GOALS §4.8), shown on the home page and under every result. */
export const DISCLAIMER =
	'OpenSolve Pipe is an engineering aid. Its results support, but do not replace, the judgment ' +
	'of a qualified engineer, and are provided without warranty.';

/** The source repository (AGPL-3.0-or-later: the source must be offered to users). */
export const SOURCE_URL = 'https://github.com/ccirone2/opensolve-pipe';

/** The license text in the source repository. */
export const LICENSE_URL = `${SOURCE_URL}/blob/main/LICENSE`;

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
