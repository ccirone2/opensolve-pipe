/**
 * The header on short landscape screens (build-density.md §19; ui-guide "One control per action,
 * at the top"): from 35.5 rem wide and at most 20 rem tall it is one pinned row, so Solve is
 * always in view, and its height is measured into `--header-h` on the root element for
 * `scroll-padding-top` (a pinned bar's height is measured, never a constant). jsdom applies no
 * media queries and lays nothing out: the classes are read here, the boxes are given with
 * testing/resize.ts as a browser would lay them out, and the rule itself is checked in the browser
 * (tests/one-solve.e2e.ts). The project is the home page's transfer example.
 */
import { render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { fakeResizeObserver, sizeBox } from '$lib/testing/resize';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import WorkspaceView from './Workspace.svelte';

const header = () => screen.getByRole('toolbar', { name: 'Project' }).closest('header')!;
const headerHeight = () => document.documentElement.style.getPropertyValue('--header-h');

/**
 * Lay the header out `height` px tall, as a browser would: its border box (offsetHeight, the
 * bounding box) and, inside its 1 px bottom border, its client box.
 */
function layOut(box: HTMLElement, height: number) {
	sizeBox(box, { clientHeight: height - 1, scrollHeight: height - 1 });
	Object.defineProperty(box, 'offsetHeight', { configurable: true, get: () => height });
	box.getBoundingClientRect = () => new DOMRect(0, 0, 568, height);
}

let observers: ReturnType<typeof fakeResizeObserver> | null = null;
afterEach(() => {
	observers?.restore();
	observers = null;
	document.documentElement.style.removeProperty('--header-h');
});

describe('the header on short landscape screens (build-density.md §19)', () => {
	it('is one pinned row from 35.5 rem wide when at most 20 rem tall', () => {
		render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		const bar = header();
		// Above the trace's side panel (z-40, later in the page), which scrolls under it from
		// 1024 px (the paint itself is read in tests/one-solve.e2e.ts).
		expect(bar).toHaveClass(
			'short:min-[35.5rem]:sticky',
			'short:min-[35.5rem]:top-0',
			'short:min-[35.5rem]:z-[45]'
		);
		expect(bar).not.toHaveClass('short:min-[35.5rem]:z-40');
		// Its row: one row, no padding above and below.
		const row = bar.firstElementChild!;
		expect(row).toHaveClass('short:min-[35.5rem]:flex-nowrap', 'short:min-[35.5rem]:py-0');
		expect(row.contains(screen.getByRole('toolbar', { name: 'Project' }))).toBe(true);
		// The toolbar takes its own width there, not the second row's.
		expect(screen.getByRole('toolbar', { name: 'Project' })).toHaveClass(
			'short:min-[35.5rem]:w-auto'
		);
	});

	it('measures its height into --header-h on the root element, following its box, removed on destroy', () => {
		observers = fakeResizeObserver();
		expect(headerHeight()).toBe('');
		const view = render(WorkspaceView, { workspace: testWorkspace(pumpTransferExample()) });
		const bar = header();
		layOut(bar, 45);
		observers.resize(bar);
		expect(headerHeight()).toBe('45px');
		// The box changes (the row wraps, the text grows): the value follows.
		layOut(bar, 95);
		observers.resize(bar);
		expect(headerHeight()).toBe('95px');
		view.unmount();
		expect(headerHeight()).toBe('');
		expect(observers.watched()).toBe(0);
	});
});
