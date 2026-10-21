/**
 * A Svelte action for a box that may scroll (a dialog's body): while its content overflows it is
 * a focusable, named region, so keyboard users can reach and scroll it in browsers that do not
 * make scroll boxes focusable (WCAG 2.1.1; axe "scrollable-region-focusable"). When it does not
 * overflow it adds no tab stop.
 */
export function focusableWhenScrollable(node: HTMLElement, labelledBy: string) {
	function update() {
		const scrolls = node.scrollHeight > node.clientHeight + 1;
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
	update();
	if (typeof ResizeObserver === 'undefined') return {};
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
		destroy() {
			observer.disconnect();
			mutations?.disconnect();
		}
	};
}
