import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { execFileSync } from 'node:child_process';

/**
 * The commit being built: Cloudflare Pages' CF_PAGES_COMMIT_SHA, else `git rev-parse HEAD`, else
 * null (no git). The footer's source and license links point at it, so a deployment offers the
 * source of the version it runs (AGPL-3.0 §13; TSD §11.1).
 */
function sourceCommit() {
	const fromHost = process.env.CF_PAGES_COMMIT_SHA?.trim();
	if (fromHost) return fromHost;
	try {
		return execFileSync('git', ['rev-parse', 'HEAD'], {
			encoding: 'utf8',
			stdio: ['ignore', 'pipe', 'ignore']
		}).trim();
	} catch {
		return null;
	}
}

const commit = sourceCommit();

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	compilerOptions: {
		// Runes mode everywhere in this project (libraries keep their own setting).
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: adapter(),
		// The commit, read in the app as `version` from $app/environment (links.ts). Without one,
		// SvelteKit's default (the build's timestamp), and the links fall back to the repository.
		...(commit ? { version: { name: commit } } : {}),
		// Root-relative links in prerendered pages ("/p#…"), the same as after hydration, so a link
		// read or followed before the app starts is the link it will be (the site is served from
		// the domain root, TSD §11).
		paths: { relative: false },
		prerender: {
			// On /p the fragment holds the project (D3), not the id of an element on the page.
			handleMissingId: ({ path, message }) => {
				if (path === '/p') return;
				throw new Error(message);
			}
		}
	}
};

export default config;
