import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	compilerOptions: {
		// Runes mode everywhere in this project (libraries keep their own setting).
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: adapter(),
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
