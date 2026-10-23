import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { packageRoot, readPackage, renderNotices } from './third-party-licenses';

describe('packageRoot', () => {
	it('names the package from the last node_modules segment (pnpm layout)', () => {
		expect(
			packageRoot(
				'/repo/apps/web/node_modules/.pnpm/chart.js@4.5.1/node_modules/chart.js/dist/chart.js'
			)
		).toBe('/repo/apps/web/node_modules/.pnpm/chart.js@4.5.1/node_modules/chart.js');
	});

	it('keeps the scope of a scoped package', () => {
		expect(
			packageRoot(
				'/r/node_modules/.pnpm/@kurkle+color@0.3.4/node_modules/@kurkle/color/dist/color.esm.js'
			)
		).toBe('/r/node_modules/.pnpm/@kurkle+color@0.3.4/node_modules/@kurkle/color');
	});

	it('reads Windows paths and drops a query', () => {
		expect(packageRoot('C:\\r\\node_modules\\pako\\dist\\pako.esm.mjs?v=1')).toBe(
			'C:/r/node_modules/pako'
		);
	});

	it("returns null for the app's own modules and virtual ones", () => {
		expect(packageRoot('/repo/apps/web/src/lib/utils/encoding.ts')).toBeNull();
		expect(packageRoot('\0virtual:module')).toBeNull();
		expect(packageRoot('/r/node_modules/@scope')).toBeNull();
	});
});

describe('readPackage', () => {
	let dir = '';
	afterEach(() => {
		if (dir) rmSync(dir, { recursive: true, force: true });
		dir = '';
	});

	it('reads an installed package and its license file', () => {
		const found = readPackage(join(process.cwd(), 'node_modules', 'chart.js'));
		expect(found.name).toBe('chart.js');
		expect(found.license).toBe('MIT');
		expect(found.licenseText).toMatch(/Copyright \(c\) .*Chart\.js Contributors/);
	});

	it('fails for a bundled package without a license file', () => {
		dir = mkdtempSync(join(tmpdir(), 'notices-'));
		mkdirSync(join(dir, 'pkg'));
		writeFileSync(
			join(dir, 'pkg', 'package.json'),
			JSON.stringify({ name: 'pkg', version: '1.0.0', license: 'MIT' })
		);
		expect(() => readPackage(join(dir, 'pkg'))).toThrow(
			'pkg is in the bundle but has no license field or license file'
		);
	});
});

describe('renderNotices', () => {
	it('lists the packages by name, then reproduces each license in full', () => {
		const text = renderNotices([
			{ name: 'zeta', version: '2.0.0', license: 'BSD-3-Clause', licenseText: 'Zeta license' },
			{ name: '@a/alpha', version: '1.0.0', license: 'MIT', licenseText: 'Alpha license' }
		]);
		expect(text).toMatch(/^OpenSolve Pipe: third-party software in this web app\n/);
		expect(text).toContain('AGPL-3.0-or-later');
		expect(text).toContain('- @a/alpha 1.0.0, license: MIT\n- zeta 2.0.0, license: BSD-3-Clause\n');
		expect(text.indexOf('Alpha license')).toBeLessThan(text.indexOf('Zeta license'));
		expect(text.endsWith('Zeta license\n')).toBe(true);
	});
});
