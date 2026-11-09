/**
 * Scroll boxes that keyboard users can reach: while its content overflows a box is a focusable,
 * named region, so keyboard users can reach and scroll it in browsers that do not make scroll
 * boxes focusable (WCAG 2.1.1; axe "scrollable-region-focusable"). When it does not overflow it
 * adds no Tab stop and no landmark (proposal pumps-results-layout.md §9 S7: "a Tab stop only while
 * it overflows").
 */

/** Make the box a named region and a Tab stop, or neither. */
function mark(node: HTMLElement, scrolls: boolean, labelledBy: string) {
	if (scrolls) {
		node.setAttribute('tabindex', '0');
		node.setAttribute('role', 'region');
		node.setAttribute('aria-labelledby', labelledBy);
	} else {
		node.removeAttribute('tabindex');
		node.removeAttribute('role');
		node.removeAttribute('aria-labelledby');
	}
}

/**
 * Call `update` now and whenever the box or one of its children changes size (a table's rows
 * drawn, a disclosure opened, the pane resized), or a child is added or removed. Without a
 * ResizeObserver (an old browser, jsdom) it is called once.
 */
function watch(node: HTMLElement, update: () => void) {
	update();
	if (typeof ResizeObserver === 'undefined') return { disconnect() {} };
	const observer = new ResizeObserver(update);
	observer.observe(node);
	for (const child of node.children) observer.observe(child);
	const mutations =
		typeof MutationObserver === 'undefined'
			? null
			: new MutationObserver(() => {
					for (const child of node.children) observer.observe(child);
					update();
				});
	mutations?.observe(node, { childList: true });
	return {
		disconnect() {
			observer.disconnect();
			mutations?.disconnect();
		}
	};
}

/**
 * A Svelte action for a box that may scroll down (a dialog's body), measured on its height.
 */
export function focusableWhenScrollable(node: HTMLElement, labelledBy: string) {
	const watching = watch(node, () =>
		mark(node, node.scrollHeight > node.clientHeight + 1, labelledBy)
	);
	return {
		destroy() {
			watching.disconnect();
		}
	};
}

/**
 * Whether an axis's computed `overflow` lets the user scroll it: `auto` or `scroll` in a browser.
 * `visible`, `hidden` and `clip` do not (a phone's list is `overflow: visible`, so it never
 * scrolls, whatever it measures). jsdom computes no stylesheet, so it gives '', which counts: its
 * tests decide by the sizes they give.
 */
const canScroll = (overflow: string) =>
	overflow !== 'visible' && overflow !== 'hidden' && overflow !== 'clip';

/**
 * The box's content overflows on an axis it scrolls: sideways (a table wider than its box) or
 * down (a box with a maximum height), by more than a pixel's rounding.
 */
export function overflows(node: HTMLElement): boolean {
	const style = getComputedStyle(node);
	return (
		(canScroll(style.overflowX) && node.scrollWidth > node.clientWidth + 1) ||
		(canScroll(style.overflowY) && node.scrollHeight > node.clientHeight + 1)
	);
}

/** The disclosures the box is inside, nearest first. */
function foldsOf(node: HTMLElement): HTMLDetailsElement[] {
	const folds: HTMLDetailsElement[] = [];
	for (let d = node.closest('details'); d; d = d.parentElement?.closest('details') ?? null) {
		folds.push(d);
	}
	return folds;
}

/**
 * The box is drawn: in no closed disclosure (a browser still lays out a closed one's content, so
 * its sizes say nothing of what is on screen, and it is no Tab stop there) and, where the
 * browser can tell, rendered.
 */
export function drawn(node: HTMLElement): boolean {
	if (foldsOf(node).some((d) => !d.open)) return false;
	return typeof node.checkVisibility !== 'function' || node.checkVisibility();
}

/**
 * A Svelte action for a data table's scroll box (proposal pumps-results-layout.md §9 S7, §5.7):
 * a Tab stop (`tabindex="0"`) and a region named by `labelledBy` only while it is drawn and
 * overflows, measured on both axes whenever it or its content changes size, as
 * `focusableWhenScrollable` measures a dialog's height, and whenever a disclosure it is in opens
 * or closes (a closed one's content keeps its size, so no resize says so). Without `labelledBy`
 * the box is left as it is: neither.
 */
export function scrollRegion(node: HTMLElement, labelledBy: string | undefined) {
	let label = labelledBy;
	const update = () => {
		if (label) mark(node, drawn(node) && overflows(node), label);
	};
	const watching = watch(node, update);
	const folds = foldsOf(node);
	for (const d of folds) d.addEventListener('toggle', update);
	return {
		update(next: string | undefined) {
			if (label && !next) mark(node, false, label);
			label = next;
			update();
		},
		destroy() {
			watching.disconnect();
			for (const d of folds) d.removeEventListener('toggle', update);
		}
	};
}
