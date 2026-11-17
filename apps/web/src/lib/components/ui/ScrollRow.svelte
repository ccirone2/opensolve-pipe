<!--
	One row that scrolls sideways (ui-guide: "Groups of tabs or pills are one row that scrolls
	sideways at every width"; proposal pumps-results-layout.md §5.4 One shared component): the
	Results view row and the Pumps tab's section nav. Edge shadows say there is more; a mouse wheel
	scrolls it sideways while it can still move that way (a non-passive listener), and at its ends
	the wheel scrolls the pane, a sideways gesture being the browser's.

	Its scrolling element has `py-1`: `overflow-x: auto` also clips vertically, so without block
	padding a focused item's ring (2 px at a 2 px offset) would be drawn at its sides only. A row
	whose layout must not move takes `-my-1` (the view row).

	It is positioned, so the visually hidden words of an item scrolled out of sight (a mark's
	", has warnings", absolutely placed) stay inside its clip rather than widening the pane.

	`keepInView` scrolls the row alone, never an ancestor (which `scrollIntoView` would: the pane, or
	a scroll already running), so that an item and the one after it are in view, smoothly unless
	the user asks for reduced motion (§7 Motion).
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ClassValue, HTMLAttributes } from 'svelte/elements';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import { keepInViewLeft } from '$lib/utils/section-nav';

	interface Props extends Omit<HTMLAttributes<HTMLDivElement>, 'class' | 'children'> {
		class?: ClassValue;
		/** The scrolling element (bindable). */
		row?: HTMLElement;
		children: Snippet;
	}

	let { class: className, row = $bindable(), children, ...rest }: Props = $props();
	const reduced = mediaQuery('(prefers-reduced-motion: reduce)');

	$effect(() => {
		const el = row;
		if (!el) return;
		const wheel = (event: WheelEvent) => {
			if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
			const room = el.scrollWidth - el.clientWidth;
			const moving =
				(event.deltaY > 0 && el.scrollLeft < room - 1) || (event.deltaY < 0 && el.scrollLeft > 0);
			if (room <= 0 || !moving) return;
			event.preventDefault();
			el.scrollLeft += event.deltaY;
		};
		el.addEventListener('wheel', wheel, { passive: false });
		return () => el.removeEventListener('wheel', wheel);
	});

	/** Bring `item` (a child of the row) and the one after it into view, scrolling the row only. */
	export function keepInView(item: Element | null | undefined) {
		const el = row;
		if (!el || !item || !el.contains(item)) return;
		const box = el.getBoundingClientRect();
		const at = (e: Element) => {
			const r = e.getBoundingClientRect();
			const left = r.left - box.left - el.clientLeft + el.scrollLeft;
			return { left, right: left + r.width };
		};
		const style = getComputedStyle(el);
		const next = item.nextElementSibling;
		const left = keepInViewLeft(
			{
				scrollLeft: el.scrollLeft,
				clientWidth: el.clientWidth,
				scrollWidth: el.scrollWidth,
				padStart: parseFloat(style.paddingLeft) || 0,
				padEnd: parseFloat(style.paddingRight) || 0
			},
			at(item),
			next ? at(next) : null
		);
		if (left === null) return;
		const behavior = reduced.current ? 'auto' : 'smooth';
		if (typeof el.scrollTo === 'function') el.scrollTo({ left, behavior });
		else el.scrollLeft = left;
	}
</script>

<div
	bind:this={row}
	{...rest}
	class={[
		'scroll-shadow-x relative flex [scrollbar-width:none] overflow-x-auto py-1 [&::-webkit-scrollbar]:hidden',
		className
	]}
>
	{@render children()}
</div>
