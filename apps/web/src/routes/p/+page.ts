import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { createNewProject } from '$lib/models';
import { encodeProject } from '$lib/utils';

/**
 * Universal load function that redirects /p/ to /p/{encoded}.
 * Creates a fresh empty project and encodes it into the URL.
 * This runs in both SSR and CSR contexts, ensuring the redirect
 * always works (unlike the previous onMount+goto approach which
 * failed in Vite preview builds).
 */
export const load: PageLoad = () => {
	const project = createNewProject();
	const result = encodeProject(project);
	redirect(307, `/p/${result.encoded}`);
};
