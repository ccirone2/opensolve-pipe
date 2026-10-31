/**
 * The Build pane's density budgets (proposal build-density.md §3), measured in the running app at
 * the two project viewports, so a later field or toolbar that breaks them fails CI:
 * - every component's core fields are on the first screen at 390×844 (no scroll);
 * - chrome (buttons, tabs, disclosure rows) takes at most 15 % of the Build pane at 1280×800;
 * - the commonest edits are at most 2 actions after opening the panel;
 * - axe-core finds no WCAG 2.2 A/AA violation in Build, with its disclosures open.
 */
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import type { Project } from '../src/lib/api/types';
import { gzip } from 'pako';
import { exampleProject } from '../src/lib/utils/examples';
import {
	COMPONENT_KINDS,
	createComponent,
	createConnection,
	createEmptyProject,
	defaultPiping,
	type EnteredValues
} from '../src/lib/utils/factory';
import { canonicalJson } from '../src/lib/utils/json';
import { buildPane, showPane, solve } from './support';

/**
 * One of every kind of component, in a chain, with the values the kinds without defaults need;
 * every port left free is plugged, every control valve has a setpoint and the pump has the pump
 * example's curve, so each panel shows its normal state (an unconnected port, a setpoint of 0 or a
 * pump without a curve is an exception the panel raises, by design).
 */
function everyKind(): Project {
	const project = createEmptyProject({ name: 'Every kind', now: '2026-10-30T00:00:00Z' });
	const entered: Partial<Record<string, EnteredValues>> = {
		assigned_flow: { flow: 0.01 },
		equipment: { rating: { kind: 'point', pressureLoss: 50000, flow: 0.02, density: 998 } },
		orifice: { boreDiameter: 0.05 },
		relief_valve: { setPressure: 500000, capacity: { kind: 'api526', letter: 'D' } }
	};
	project.pumpLibrary = exampleProject('pump-transfer')!.pumpLibrary;
	for (const kind of COMPONENT_KINDS) {
		const component = createComponent(kind, project, entered[kind] ?? {});
		if (component.type === 'pump') component.curveId = project.pumpLibrary[0]!.id;
		if (component.type === 'valve' && 'setpoint' in component) {
			component.setpoint = component.valveType === 'fcv' ? 0.01 : 300000;
		}
		project.components.push(component);
	}
	const used = new Set<string>();
	for (let i = 0; i + 1 < project.components.length; i++) {
		const [a, b] = [project.components[i]!, project.components[i + 1]!];
		const pa = a.ports.find((p) => !used.has(`${a.id}/${p.id}`));
		const pb = b.ports.find((p) => !used.has(`${b.id}/${p.id}`));
		if (!pa || !pb) continue;
		used.add(`${a.id}/${pa.id}`).add(`${b.id}/${pb.id}`);
		project.connections.push(
			createConnection(
				project,
				{ componentId: a.id, portId: pa.id },
				{ componentId: b.id, portId: pb.id },
				defaultPiping(0.1016)
			)
		);
	}
	for (const component of [...project.components]) {
		for (const port of component.ports) {
			if (used.has(`${component.id}/${port.id}`)) continue;
			const plug = createComponent('plug', project);
			project.components.push(plug);
			used.add(`${component.id}/${port.id}`);
			project.connections.push(
				createConnection(
					project,
					{ componentId: component.id, portId: port.id },
					{ componentId: plug.id, portId: plug.ports[0]!.id },
					defaultPiping(0.1016)
				)
			);
		}
	}
	return project;
}

/**
 * The link fragment of a project, as utils/encoding.ts writes it (canonical JSON, gzip, base64url):
 * encoding.ts itself loads the schema, which Playwright's loader cannot import.
 */
function fragment(project: Project): string {
	const bytes = gzip(new TextEncoder().encode(canonicalJson(project)), { level: 9 });
	return Buffer.from(bytes).toString('base64url');
}

async function open(page: Page, project: Project) {
	await page.goto(`/p#${fragment(project)}`);
	await expect(buildPane(page).getByRole('heading', { level: 2 })).toBeVisible();
}

async function jumpTo(page: Page, name: string) {
	await buildPane(page).getByRole('button', { name: 'Jump to a component' }).click();
	const dialog = page.getByRole('dialog', { name: 'Jump to a component' });
	const filter = dialog.getByRole('searchbox', { name: 'Filter' });
	if (await filter.count()) await filter.fill(name);
	await dialog.getByRole('button', { name: new RegExp(`^${name}`) }).click();
	await expect(dialog).toBeHidden();
	await expect(buildPane(page).getByRole('heading', { level: 2 })).toHaveText(name);
}

/** The first control of every core field that lies below the Build pane's scrolling area. */
async function coreFieldsBelowFold(page: Page): Promise<string[]> {
	return page.evaluate(() => {
		const pane = document.querySelector('section[aria-label="Build"]')!;
		const scroller = pane.querySelector('.overflow-y-auto')!;
		const bottom = scroller.getBoundingClientRect().bottom;
		const below: string[] = [];
		for (const field of pane.querySelectorAll('[data-tier="core"] [data-field]')) {
			const control = [...field.querySelectorAll('input, select, textarea, button')].find(
				(c) => (c as HTMLElement).getBoundingClientRect().height > 0
			);
			if (control && control.getBoundingClientRect().bottom > bottom + 0.5) {
				below.push(field.getAttribute('data-field')!);
			}
		}
		return below;
	});
}

/**
 * The share of the Build pane's height (as shown, scrolled to its top) covered by chrome, row by
 * row: a row is chrome when a button, tab or disclosure row covers it and no input or result does.
 * Buttons that enter a field's value (a preset, `data-input`) are inputs, not chrome.
 */
async function chromeShare(page: Page): Promise<number> {
	return page.evaluate(() => {
		const pane = document.querySelector('section[aria-label="Build"]')!;
		const top = pane.getBoundingClientRect().top;
		const height = Math.round(pane.getBoundingClientRect().height);
		const rows = new Array<number>(height).fill(0);
		// Inside a closed <details> an element keeps a box but is not shown (checkVisibility).
		const shown = (e: Element) => {
			const r = e.getBoundingClientRect();
			return r.height > 0 && r.width > 0 && !e.closest('.sr-only') && e.checkVisibility();
		};
		const visibleIn = (e: Element) => {
			const scroller = e.closest('.overflow-y-auto');
			if (!scroller) return true;
			const r = e.getBoundingClientRect();
			const s = scroller.getBoundingClientRect();
			return r.bottom > s.top && r.top < s.bottom;
		};
		const clip = (e: Element) => {
			const scroller = e.closest('.overflow-y-auto');
			const r = e.getBoundingClientRect();
			if (!scroller) return r;
			const s = scroller.getBoundingClientRect();
			return { top: Math.max(r.top, s.top), bottom: Math.min(r.bottom, s.bottom) };
		};
		const markClipped = (e: Element, value: number) => {
			const r = clip(e);
			for (let y = Math.max(0, Math.floor(r.top - top)); y < Math.min(height, r.bottom - top); y++)
				rows[y] = Math.max(rows[y]!, value);
		};
		for (const e of pane.querySelectorAll('button, [role="tab"], summary, a')) {
			if (shown(e) && visibleIn(e) && !e.closest('[role="group"][aria-labelledby], [data-input]'))
				markClipped(e, 1);
		}
		for (const e of pane.querySelectorAll(
			'input, select, textarea, [role="group"][aria-labelledby], [data-input]'
		)) {
			if (shown(e) && visibleIn(e)) markClipped(e, 2);
		}
		return rows.filter((r) => r === 1).length / height;
	});
}

const DESKTOP = (name: string) => name === 'desktop';

test('every component’s core fields are on the first screen of a phone', async ({ page }, info) => {
	test.skip(DESKTOP(info.project.name), 'the budget is set at 390×844');
	const project = everyKind();
	await open(page, project);
	await showPane(page, 'Build');
	const misses: string[] = [];
	for (const component of project.components) {
		await jumpTo(page, component.name);
		for (const path of await coreFieldsBelowFold(page)) misses.push(`${component.name}: ${path}`);
	}
	expect(misses).toEqual([]);
});

test('with a solve shown, the core fields are still on the first screen of a phone', async ({
	page
}, info) => {
	test.skip(DESKTOP(info.project.name), 'the budget is set at 390×844');
	const project = exampleProject('pump-transfer')!;
	await open(page, project);
	await solve(page);
	await showPane(page, 'Build');
	const misses: string[] = [];
	for (const component of project.components) {
		await jumpTo(page, component.name);
		await expect(buildPane(page).getByRole('group', { name: /^Last solve/ })).toBeVisible();
		for (const path of await coreFieldsBelowFold(page)) misses.push(`${component.name}: ${path}`);
	}
	expect(misses).toEqual([]);
});

test('chrome takes at most 15 % of the Build pane on a laptop', async ({ page }, info) => {
	test.skip(!DESKTOP(info.project.name), 'the budget is set at 1280×800');
	const project = everyKind();
	await open(page, project);
	const shares: Record<string, number> = {};
	for (const component of project.components) {
		await jumpTo(page, component.name);
		shares[component.name] = Math.round((await chromeShare(page)) * 1000) / 10;
	}
	const solved = exampleProject('pump-transfer')!;
	await open(page, solved);
	await solve(page);
	for (const component of solved.components) {
		await jumpTo(page, component.name);
		shares[`solved ${component.name}`] = Math.round((await chromeShare(page)) * 1000) / 10;
	}
	const over = Object.entries(shares).filter(([, share]) => share > 15);
	expect(over, JSON.stringify(shares)).toEqual([]);
});

test('a pipe size is 2 actions from its component: Piping, then the size', async ({ page }) => {
	await open(page, exampleProject('pump-transfer')!);
	await showPane(page, 'Build');
	await jumpTo(page, 'Transfer pump');
	const panel = buildPane(page);
	await panel.getByRole('tab', { name: 'Piping' }).click(); // 1
	const size = panel.getByRole('combobox', { name: 'Size' }).first();
	await expect(size).toBeInViewport({ ratio: 1 });
	await size.selectOption({ index: 0 }); // 2
});

test('solved, a pipe size is still 2 actions with no scroll, beside both result strips', async ({
	page
}) => {
	await open(page, exampleProject('pump-transfer')!);
	await solve(page);
	await showPane(page, 'Build');
	await jumpTo(page, 'Transfer pump');
	const panel = buildPane(page);
	await panel.getByRole('tab', { name: 'Piping' }).click(); // 1
	await expect(panel.getByRole('group', { name: /^Last solve/ })).toHaveCount(2);
	await expect(panel.getByRole('combobox', { name: 'Size' }).first()).toBeInViewport({ ratio: 1 });
});

test('solved, a pump curve’s first point is 1 action from its panel, with no scroll', async ({
	page
}) => {
	await open(page, exampleProject('pump-transfer')!);
	await solve(page);
	await showPane(page, 'Build');
	await jumpTo(page, 'Transfer pump');
	const panel = buildPane(page);
	await expect(panel.getByRole('group', { name: /^Last solve/ })).toBeVisible();
	const head = panel.getByRole('table', { name: 'Head curve (at rated speed)' });
	await expect(head.getByRole('textbox', { name: /^Point 1 flow/ })).toBeInViewport({ ratio: 1 });
	await expect(head.getByRole('textbox', { name: /^Point 1 head/ })).toBeInViewport({ ratio: 1 });
});

test('a valve’s status is 1 action from its panel: one tap on its segment', async ({ page }) => {
	await open(page, exampleProject('pump-transfer')!);
	await showPane(page, 'Build');
	await jumpTo(page, 'Discharge isolation valve');
	const status = buildPane(page).getByRole('radiogroup', { name: 'Status' });
	await expect(status).toBeInViewport({ ratio: 1 });
	const closed = status.getByRole('radio', { name: 'Closed (isolated)' });
	await closed.click(); // 1
	await expect(closed).toBeChecked();
	await expect(status.getByRole('radio', { name: 'Open' })).not.toBeChecked();
});

test('at 400 % zoom (320×256) the form is reached by scrolling the page, never sideways', async ({
	page
}, info) => {
	test.skip(!DESKTOP(info.project.name), 'a laptop zoomed to 400 % (WCAG 1.4.10)');
	await open(page, exampleProject('pump-transfer')!);
	await page.setViewportSize({ width: 320, height: 256 });
	const level = buildPane(page).getByRole('textbox', { name: /^Liquid level/ });
	await level.scrollIntoViewIfNeeded();
	await expect(level).toBeInViewport({ ratio: 1 });
	const sideways = await page.evaluate(
		() => document.scrollingElement!.scrollWidth - document.scrollingElement!.clientWidth
	);
	expect(sideways).toBe(0);
});

test('axe finds no violation in Build, with its disclosures open', async ({ page }) => {
	const project = everyKind();
	await open(page, project);
	await showPane(page, 'Build');
	for (const name of ['Pump P1', 'Relief valve RV1', 'Check valve V5', 'Orifice O1']) {
		await jumpTo(page, name);
		await page.evaluate(() =>
			document.querySelectorAll('section[aria-label="Build"] details').forEach((d) => {
				(d as HTMLDetailsElement).open = true;
			})
		);
		const scan = await new AxeBuilder({ page })
			.include('section[aria-label="Build"]')
			.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
			.analyze();
		expect(scan.violations.map((v) => `${name}: ${v.id} (${v.nodes.length})`)).toEqual([]);
	}
	await buildPane(page).getByRole('tab', { name: 'Piping' }).click();
	const piping = await new AxeBuilder({ page })
		.include('section[aria-label="Build"]')
		.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
		.analyze();
	expect(piping.violations.map((v) => `Piping: ${v.id} (${v.nodes.length})`)).toEqual([]);
});
