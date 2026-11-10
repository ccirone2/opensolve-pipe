/**
 * Scroll boxes a Tab stop only while they overflow (proposal pumps-results-layout.md §9 S7, §5.7):
 * `scrollRegion` measures both axes whenever the box or its content changes size, a ResizeObserver
 * replaced by one whose callbacks the test runs (jsdom lays nothing out), and the sizes given as a
 * browser would. `focusableWhenScrollable` (a dialog's body) keeps measuring its height alone.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fakeResizeObserver, sizeBox } from '$lib/testing/resize';
import { drawn, focusableWhenScrollable, overflows, scrollRegion } from './scroll-focus';

let observers: ReturnType<typeof fakeResizeObserver>;
beforeEach(() => {
	observers = fakeResizeObserver();
});
afterEach(() => {
	observers.restore();
	vi.restoreAllMocks();
	document.body.replaceChildren();
});

/** A box holding a table named by its caption, as the data regions draw one. */
function box() {
	const el = document.createElement('div');
	el.innerHTML = '<table><caption id="made-up-caption">System curve</caption></table>';
	document.body.append(el);
	return { el, table: el.querySelector('table')! };
}

/**
 * The page loses the system focus (a tab, app or find-bar switch): the browser fires `focusout` on
 * the focused box, which stays the document's active element, and `document.hasFocus()` is false
 * (S7 second check A11Y-1-BLUR). `back` is the page's return: the browser focuses the box again.
 */
function pageBlurred(el: HTMLElement) {
	const hasFocus = vi.spyOn(document, 'hasFocus').mockReturnValue(false);
	el.dispatchEvent(new FocusEvent('blur'));
	el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
	return { back: () => hasFocus.mockRestore() };
}

/** The box is a Tab stop and a region named by the caption: all three attributes, or none. */
function stop(el: HTMLElement) {
	const attributes = ['tabindex', 'role', 'aria-labelledby'].map((a) => el.getAttribute(a));
	if (attributes.every((a) => a === null)) return false;
	expect(attributes).toEqual(['0', 'region', 'made-up-caption']);
	return true;
}

describe('scrollRegion (§9 S7: a Tab stop only while it overflows)', () => {
	it('is no Tab stop and no region while its content fits', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 400, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, 'made-up-caption');
		expect(stop(el)).toBe(false);
		action.destroy();
	});

	it('becomes a Tab stop and a named region when it overflows sideways, and stops being one when it fits again', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 400, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, 'made-up-caption');
		expect(stop(el)).toBe(false);
		// The pane narrowed: the table is wider than its box.
		sizeBox(el, { clientWidth: 300, scrollWidth: 400 });
		observers.resize(el);
		expect(stop(el)).toBe(true);
		// Widened again.
		sizeBox(el, { clientWidth: 400 });
		observers.resize(el);
		expect(stop(el)).toBe(false);
		action.destroy();
	});

	it('becomes a Tab stop when it overflows down, and stops when it fits', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 400, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, 'made-up-caption');
		sizeBox(el, { scrollHeight: 900 });
		observers.resize(el);
		expect(stop(el)).toBe(true);
		sizeBox(el, { scrollHeight: 200 });
		observers.resize(el);
		expect(stop(el)).toBe(false);
		action.destroy();
	});

	it('measures when its content changes size: the table it holds is watched, and a child added', async () => {
		const { el, table } = box();
		sizeBox(el, { clientWidth: 400, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, 'made-up-caption');
		expect(observers.watched()).toBe(2); // the box and its table
		// Rows drawn: only the table's observer runs (the box's own size is unchanged).
		sizeBox(el, { scrollHeight: 400 });
		observers.resize(table);
		expect(stop(el)).toBe(true);
		sizeBox(el, { scrollHeight: 200 });
		observers.resize(table);
		expect(stop(el)).toBe(false);
		// A child added, wider than the box: measured as it is added, with no resize of the box or
		// its table, and watched from then on (S7 review MUT-MUTATION-OBSERVER).
		const wide = document.createElement('div');
		sizeBox(el, { scrollWidth: 900 });
		el.append(wide);
		await new Promise((resolve) => setTimeout(resolve, 0)); // the mutation records
		expect(stop(el)).toBe(true);
		expect(observers.watched()).toBe(3);
		sizeBox(el, { scrollWidth: 400 });
		observers.resize(wide);
		expect(stop(el)).toBe(false);
		action.destroy();
		expect(observers.watched()).toBe(0);
	});

	it('keeps the focus on a box that stops overflowing while it holds it: still focusable and named, no Tab stop, until the focus leaves; then neither (S7 review A11Y-1)', () => {
		const { el } = box();
		const after = document.createElement('button');
		document.body.append(after);
		sizeBox(el, { clientWidth: 300, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, 'made-up-caption');
		expect(stop(el)).toBe(true);
		el.focus();
		expect(document.activeElement).toBe(el);
		const attributes = () => ['tabindex', 'role', 'aria-labelledby'].map((a) => el.getAttribute(a));
		// The window widened: it fits while focused.
		sizeBox(el, { clientWidth: 400 });
		observers.resize(el);
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		expect(document.activeElement).toBe(el);
		// Narrowed again while focused: a Tab stop again.
		sizeBox(el, { clientWidth: 300 });
		observers.resize(el);
		expect(stop(el)).toBe(true);
		sizeBox(el, { clientWidth: 400 });
		observers.resize(el);
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		// The focus moves on: measured again, it is neither.
		after.focus();
		expect(stop(el)).toBe(false);
		action.destroy();
		// Destroyed, it listens no more.
		sizeBox(el, { clientWidth: 300 });
		el.setAttribute('tabindex', '0');
		el.focus();
		after.focus();
		expect(el.getAttribute('role')).toBeNull();
	});

	it('keeps a fitting box that holds the focus focusable and named while the page loses the system focus, then measures it when the focus really leaves (S7 second check A11Y-1-BLUR)', () => {
		const { el } = box();
		const after = document.createElement('button');
		document.body.append(after);
		sizeBox(el, { clientWidth: 300, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, 'made-up-caption');
		el.focus();
		const attributes = () => ['tabindex', 'role', 'aria-labelledby'].map((a) => el.getAttribute(a));
		// The window widened: it fits while focused.
		sizeBox(el, { clientWidth: 400 });
		observers.resize(el);
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		// Another tab brought to the front: the page's own focusout is no focus leaving the box.
		const page = pageBlurred(el);
		expect(document.activeElement).toBe(el);
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		page.back();
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		// The focus moves on: measured again, it is neither.
		after.focus();
		expect(stop(el)).toBe(false);
		action.destroy();
	});

	it('measures a fitting box as left at a focusout during which the browser still reports it focused while the page has the system focus (S7 second check A11Y-1-BLUR)', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 300, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, 'made-up-caption');
		el.focus();
		sizeBox(el, { clientWidth: 400 });
		observers.resize(el);
		expect(['tabindex', 'role', 'aria-labelledby'].map((a) => el.getAttribute(a))).toEqual([
			'-1',
			'region',
			'made-up-caption'
		]);
		// jsdom keeps the box its active element through a dispatched focusout, and the page focused.
		el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
		expect(document.activeElement).toBe(el);
		expect(document.hasFocus()).toBe(true);
		expect(stop(el)).toBe(false);
		action.destroy();
	});

	it('keeps the focus on a dialog’s body that stops overflowing while it holds it (S7 review A11Y-1)', () => {
		const { el } = box();
		const after = document.createElement('button');
		document.body.append(after);
		sizeBox(el, { clientWidth: 300, scrollWidth: 300, clientHeight: 200, scrollHeight: 900 });
		const action = focusableWhenScrollable(el, 'made-up-caption');
		expect(stop(el)).toBe(true);
		el.focus();
		sizeBox(el, { scrollHeight: 200 });
		observers.resize(el);
		expect(['tabindex', 'role', 'aria-labelledby'].map((a) => el.getAttribute(a))).toEqual([
			'-1',
			'region',
			'made-up-caption'
		]);
		after.focus();
		expect(stop(el)).toBe(false);
		action.destroy();
	});

	it('keeps a dialog’s body that fits and holds the focus focusable and named while the page loses the system focus, then measures it when the focus really leaves (S7 second check A11Y-1-BLUR)', () => {
		const { el } = box();
		const after = document.createElement('button');
		document.body.append(after);
		sizeBox(el, { clientWidth: 300, scrollWidth: 300, clientHeight: 200, scrollHeight: 900 });
		const action = focusableWhenScrollable(el, 'made-up-caption');
		el.focus();
		const attributes = () => ['tabindex', 'role', 'aria-labelledby'].map((a) => el.getAttribute(a));
		sizeBox(el, { scrollHeight: 200 });
		observers.resize(el);
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		const page = pageBlurred(el);
		expect(document.activeElement).toBe(el);
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		page.back();
		expect(attributes()).toEqual(['-1', 'region', 'made-up-caption']);
		after.focus();
		expect(stop(el)).toBe(false);
		action.destroy();
	});

	it('ignores an overflow on an axis it does not scroll (a phone’s list, overflow visible)', () => {
		const { el } = box();
		el.style.overflowX = 'visible';
		el.style.overflowY = 'visible';
		sizeBox(el, { clientWidth: 300, scrollWidth: 400, clientHeight: 200, scrollHeight: 900 });
		expect(overflows(el)).toBe(false);
		const action = scrollRegion(el, 'made-up-caption');
		expect(stop(el)).toBe(false);
		// Sideways scrolling only: its sideways overflow counts, its downward one does not.
		el.style.overflowX = 'auto';
		el.style.overflowY = 'hidden';
		expect(overflows(el)).toBe(true);
		sizeBox(el, { scrollWidth: 300 });
		expect(overflows(el)).toBe(false);
		action.destroy();
	});

	it('counts no overflow within a pixel’s rounding', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 300, scrollWidth: 301, clientHeight: 200, scrollHeight: 201 });
		expect(overflows(el)).toBe(false);
		sizeBox(el, { scrollWidth: 302 });
		expect(overflows(el)).toBe(true);
	});

	it('leaves a box without a name as it is, and follows a name given or taken away', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 300, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = scrollRegion(el, undefined);
		observers.resize(el);
		expect(stop(el)).toBe(false);
		action.update('made-up-caption');
		expect(stop(el)).toBe(true);
		action.update(undefined);
		expect(stop(el)).toBe(false);
		observers.resize(el);
		expect(stop(el)).toBe(false);
		action.destroy();
	});
});

describe('scrollRegion in a disclosure (a curve table, §9 S7)', () => {
	/** A box in a closed disclosure, as CurveTable draws one. */
	function folded() {
		const details = document.createElement('details');
		details.innerHTML = '<summary>System curve (41 points)</summary>';
		const { el } = box();
		details.append(el);
		document.body.append(details);
		return { details, el };
	}

	it('is no Tab stop while its disclosure is closed, whatever it measures (a browser lays it out still), and is measured again as it opens and closes', async () => {
		const { details, el } = folded();
		sizeBox(el, { clientWidth: 452, scrollWidth: 1929, clientHeight: 300, scrollHeight: 300 });
		const action = scrollRegion(el, 'made-up-caption');
		observers.resize(el);
		expect(stop(el)).toBe(false);
		// Opened: no resize comes (its size is the same), the toggle measures it.
		details.open = true;
		details.dispatchEvent(new Event('toggle'));
		expect(stop(el)).toBe(true);
		details.open = false;
		details.dispatchEvent(new Event('toggle'));
		expect(stop(el)).toBe(false);
		action.destroy();
		// Destroyed, it listens no more.
		details.open = true;
		details.dispatchEvent(new Event('toggle'));
		expect(stop(el)).toBe(false);
	});

	it('is no Tab stop where the browser says it is not rendered (display: none above it)', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 452, scrollWidth: 900, clientHeight: 300, scrollHeight: 300 });
		let rendered = false;
		Object.defineProperty(el, 'checkVisibility', { configurable: true, value: () => rendered });
		const action = scrollRegion(el, 'made-up-caption');
		expect(stop(el)).toBe(false);
		rendered = true;
		observers.resize(el);
		expect(stop(el)).toBe(true);
		action.destroy();
	});

	it('counts a disclosure above its own: drawn only while every one is open', () => {
		const outer = document.createElement('details');
		outer.open = true;
		const { details, el } = folded();
		details.open = true;
		outer.append(details);
		document.body.append(outer);
		expect(drawn(el)).toBe(true);
		outer.open = false;
		expect(drawn(el)).toBe(false);
	});
});

describe('focusableWhenScrollable (a dialog’s body): its height alone, as before S7', () => {
	it('is a Tab stop while it overflows down, not when it overflows sideways', () => {
		const { el } = box();
		sizeBox(el, { clientWidth: 300, scrollWidth: 400, clientHeight: 200, scrollHeight: 200 });
		const action = focusableWhenScrollable(el, 'made-up-caption');
		expect(stop(el)).toBe(false);
		sizeBox(el, { scrollHeight: 900 });
		observers.resize(el);
		expect(stop(el)).toBe(true);
		action.destroy();
	});
});
