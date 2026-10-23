/**
 * Build-time plugin: writes `third-party-licenses.txt` to the site root with the license of every
 * npm package whose code is in the browser bundle (TSD §11.1). The MIT, BSD and Zlib licenses
 * require their notices to go with every copy, and the minifier strips the notices from the code,
 * so the site serves them in this file instead.
 *
 * The packages are read from the client build's chunks, not from `package.json`: the bundle also
 * carries code from dev dependencies (the Svelte and SvelteKit runtimes), and leaves out
 * dependencies the app never imports. A bundled package without a license file fails the build.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Plugin } from 'vite';
import { NOTICES_FILE } from '../lib/notices.js';

/**
 * Packages in the bundle that no chunk lists as a module: Tailwind generates the stylesheet
 * (its preflight and utilities) from the app's classes, so its code reaches the CSS, not a chunk.
 */
export const GENERATED_FROM = ['tailwindcss'];

const NODE_MODULES = '/node_modules/';
const LICENSE_FILE = /^(licen[cs]e|copying)(\.(md|txt))?$/i;

/** One bundled package: the fields of its `package.json` the notice uses, and its license text. */
export interface BundledPackage {
	name: string;
	version: string;
	license: string;
	licenseText: string;
}

/**
 * The installed directory of the package a bundled module comes from, or null for the app's own
 * modules and virtual ones. pnpm's layout nests packages (`.pnpm/x@1/node_modules/x/...`), so the
 * last `node_modules` segment names the package.
 */
export function packageRoot(moduleId: string): string | null {
	const id = moduleId.replaceAll('\\', '/').split('?')[0]!;
	if (id.startsWith('\0')) return null;
	const at = id.lastIndexOf(NODE_MODULES);
	if (at < 0) return null;
	const start = at + NODE_MODULES.length;
	const parts = id.slice(start).split('/');
	const segments = parts[0]?.startsWith('@') ? 2 : 1;
	if (parts.length <= segments) return null;
	return id.slice(0, start) + parts.slice(0, segments).join('/');
}

/** Read a package's name, version, license and license text from its installed directory. */
export function readPackage(root: string): BundledPackage {
	const manifest = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')) as {
		name?: string;
		version?: string;
		license?: string;
	};
	const file = readdirSync(root).find((name) => LICENSE_FILE.test(name));
	if (!manifest.name || !manifest.license || !file) {
		throw new Error(
			`${manifest.name ?? root} is in the bundle but has no license field or license file`
		);
	}
	return {
		name: manifest.name,
		version: manifest.version ?? '',
		license: manifest.license,
		licenseText: readFileSync(join(root, file), 'utf8').trim()
	};
}

/** The notices file: a header, then each package (sorted by name) with its license text. */
export function renderNotices(packages: BundledPackage[]): string {
	const sorted = [...packages].sort((a, b) => a.name.localeCompare(b.name));
	const header = [
		'OpenSolve Pipe: third-party software in this web app',
		'',
		'OpenSolve Pipe is licensed under the GNU Affero General Public License v3.0 or later',
		'(AGPL-3.0-or-later). The code delivered to your browser includes the open source packages',
		'below, each under its own license, reproduced in full.',
		'',
		...sorted.map((p) => `- ${p.name} ${p.version}, license: ${p.license}`)
	].join('\n');
	const sections = sorted.map((p) =>
		['='.repeat(78), `${p.name} ${p.version}, license: ${p.license}`, '', p.licenseText].join('\n')
	);
	return [header, ...sections].join('\n\n') + '\n';
}

/** The Vite plugin: collects the client build's packages and emits the notices file. */
export function thirdPartyLicenses(): Plugin {
	let projectRoot = process.cwd();
	return {
		name: 'opensolve-third-party-licenses',
		apply: 'build',
		configResolved(config) {
			projectRoot = config.root;
		},
		generateBundle(_options, bundle) {
			// SvelteKit builds the server (prerendering) and the client; only the client ships.
			if (this.environment.name !== 'client') return;
			const roots = new Set<string>();
			for (const output of Object.values(bundle)) {
				if (output.type !== 'chunk') continue;
				for (const id of output.moduleIds) {
					const root = packageRoot(id);
					if (root) roots.add(root);
				}
			}
			if (roots.size === 0) this.error('No npm package found in the client bundle');
			const packages = new Map<string, BundledPackage>();
			const add = (root: string) => {
				const found = readPackage(root);
				packages.set(`${found.name}@${found.version}`, found);
			};
			for (const root of roots) add(root);
			for (const name of GENERATED_FROM) {
				add(join(projectRoot, 'node_modules', name));
			}
			this.emitFile({
				type: 'asset',
				fileName: NOTICES_FILE,
				source: renderNotices([...packages.values()])
			});
		}
	};
}
