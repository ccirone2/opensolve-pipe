<!--
	The Pumps tab's section nav (proposal pumps-results-layout.md §5.4, §9 S2): one way through the
	tab. A `nav` named "Pumps view sections" holds the visible lead word "Go to" and a toolbar it
	labels, one button per section drawn (PumpsView keeps them in document order as each section
	registers its target: section-nav.svelte.ts), so a button never points at a section that is
	gone. A toolbar, not the view row's tablist: the arrow keys move between its buttons (the APG
	toolbar pattern), and it looks unlike the view row's filled pills: quiet buttons, the current
	one semibold over a 2 px blue-700 underline, never filled.

	- One Tab stop: ←, →, Home and End move between the buttons; the stop is the button last
	  focused while the focus is in the toolbar, else the current one, else the first, clamped to
	  the buttons drawn (the same section, else the nearest earlier one).
	- A press scrolls the target to the top (smoothly unless the user asks for reduced motion) and
	  then focuses it without a second scroll. Buttons, never links: the URL fragment is the project
	  (D3), so nothing here touches `location.hash`. The pane's scroller is positioned, so the page
	  itself has nothing to scroll and only the pane moves (ResultsPanel).
	- An arrow key's focus, like "Back to the sections", brings a static nav into view (it may have
	  scrolled out above the pane); pinned, it is in sight and the focus scrolls nothing.
	- Where you are: `aria-current="location"` on the button whose target was passed last, set from
	  an IntersectionObserver on the pane's scroller (its top margin the nav's height and the
	  targets' 0.5 rem, its root reaching far below the pane so a jump past it is seen), paused
	  while the Pumps view is hidden. A target just pressed that the pane cannot bring to the top (at its
	  end) stays current while it is on screen, and while the press's own scroll brings it up from
	  below the pane; when that scroll stops the pane is read again, since a target that comes to
	  rest exactly on the line crosses no threshold. When it changes only the row scrolls, keeping
	  the current button and the next in view (ScrollRow), never the pane.
	- Pinned (`sticky -top-4 z-[35]`, white) only while the pump chart's canvas, or what stands in
	  its place, has scrolled out above the scroller's top, and while the nav takes at most 15 % of
	  the scroller's height (the ui-guide's chrome rule), never under `short:` (the workspace then
	  scrolls as one page). `-top-4` cancels the scroller's `py-4`; z 35 is above the tables' sticky
	  cells (z 10 to 30) and below the Fields sheet (z 50).
	- Its height is measured (a ResizeObserver, so text zoom follows) and given back (`height`, the
	  tab's `--pumps-nav-h`, the targets' scroll margin), and while pinned to ResultsPanel
	  (`onpinned`), whose scroller then keeps a focused control clear of it (scroll-padding-top,
	  WCAG 2.4.11).
	- Each button carries its section's worst mark (sectionMark): the red octagon, the amber alert
	  or ⬣, and its name the label then the mark's words, which start with a comma ("Running
	  combinations, has warnings"). The name is the button's `aria-label`: visually hidden words
	  after the label, as §5.4 drew them, are read with a space before the comma in Chromium's tree
	  and Playwright's ("combinations , has"), whatever the markup (measured: a flex item's text, an
	  absolutely placed span, an inline-block one). The visible label starts the name (WCAG 2.5.3).
-->
<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import ScrollRow from '$lib/components/ui/ScrollRow.svelte';
	import { mediaQuery } from '$lib/utils/media.svelte';
	import { clampSection, SECTION_LABELS, type SectionKey } from '$lib/utils/section-nav';
	import FlagIcon from './FlagIcon.svelte';
	import type { SectionTarget } from './section-nav.svelte';

	interface Props {
		/** The sections drawn, in document order. */
		sections: readonly SectionTarget[];
		/** The Results pane's scroller (null: none known, the nav never pins). */
		scroller?: HTMLElement | null;
		/** The pump chart's canvas, or what stands in its place. */
		canvas?: HTMLElement | null;
		/** The Pumps view is shown (ResultsPanel keeps visited views mounted, hidden). */
		active?: boolean;
		/** The nav's height in px, measured (bindable: the tab's `--pumps-nav-h`). */
		height?: number;
		/** The nav pinned (its height) or not (null). */
		onpinned?: (height: number | null) => void;
	}

	let {
		sections,
		scroller = null,
		canvas = null,
		active = true,
		height = $bindable(0),
		onpinned
	}: Props = $props();
	const id = $props.id();

	const reduced = mediaQuery('(prefers-reduced-motion: reduce)');
	/** A viewport under 20 rem tall (`short:`): the workspace scrolls as one page. */
	const short = mediaQuery('(max-height: 20rem)');

	let nav: HTMLElement | undefined = $state();
	let row: HTMLElement | undefined = $state();
	let rowComponent: ScrollRow | undefined = $state();

	const keys = $derived(sections.map((s) => s.key));
	/** The section whose target was passed last (aria-current), before clamping. */
	let current = $state<SectionKey | null>(null);
	/** The button focused while the focus is in the toolbar (null when it is elsewhere). */
	let focused = $state<SectionKey | null>(null);
	/** A target just pressed: current while it is on screen, though the pane cannot bring it up. */
	let pressed: SectionKey | null = null;
	/** The press's own scroll is running: a target pressed still below the pane stays pressed. */
	let pressing = false;
	/** Stop watching the press's scroll (another press, or the nav gone). */
	let unwatch: (() => void) | null = null;
	const shownCurrent = $derived(clampSection(current, keys));
	const stop = $derived(clampSection(focused ?? current, keys));

	/**
	 * The observers' roots reach this far below the scroller's bottom: a target is then "not
	 * intersecting" exactly when it is above the root's top, so a jump from below the pane to above
	 * its top (a press, a dragged scrollbar) is seen too, where a target out of view at both ends
	 * would look unchanged to a plain root.
	 */
	const BELOW = 100_000;

	const remPx = () =>
		typeof document === 'undefined'
			? 16
			: parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;

	// The nav's height, from its box, never a px constant: text zoom follows (§5.4).
	$effect(() => {
		const el = nav;
		if (!el) return;
		const measure = () => (height = el.getBoundingClientRect().height);
		measure();
		if (typeof ResizeObserver === 'undefined') return;
		const observer = new ResizeObserver(measure);
		observer.observe(el);
		return () => observer.disconnect();
	});

	/** The scroller's visible height (its clientHeight), for the 15 % rule. */
	let paneHeight = $state(0);
	$effect(() => {
		const el = scroller;
		if (!el) return;
		const measure = () => (paneHeight = el.clientHeight);
		measure();
		if (typeof ResizeObserver === 'undefined') return;
		const observer = new ResizeObserver(measure);
		observer.observe(el);
		return () => observer.disconnect();
	});

	/** The pump chart's canvas has scrolled out above the scroller's top. */
	let canvasOut = $state(false);
	$effect(() => {
		const root = scroller;
		const target = canvas;
		if (!active || !root || !target || typeof IntersectionObserver === 'undefined') {
			canvasOut = false;
			return;
		}
		// Read from the page on each change: the observer only says when to look.
		const check = () => {
			canvasOut =
				target.isConnected &&
				target.getBoundingClientRect().bottom <=
					root.getBoundingClientRect().top + root.clientTop + 0.5;
		};
		check();
		const observer = new IntersectionObserver(check, {
			root,
			rootMargin: `0px 0px ${BELOW}px 0px`,
			threshold: [0]
		});
		observer.observe(target);
		return () => observer.disconnect();
	});

	/** At most 15 % of the scroller's height, never under `short:` (§5.4 Place). */
	const fits = $derived(
		height > 0 && paneHeight > 0 && height <= 0.15 * paneHeight && !short.current
	);
	const pinned = $derived(active && canvasOut && fits);

	$effect(() => {
		onpinned?.(pinned ? height : null);
	});
	onDestroy(() => {
		unwatch?.();
		onpinned?.(null);
	});

	/**
	 * The section passed last: the last target whose top is at or above the line under the nav
	 * (its height and the targets' 0.5 rem margin); none passed, the first. A target pressed that
	 * the pane cannot bring to the line stays current while on screen and nothing after it passed.
	 */
	function locate() {
		const root = scroller;
		if (!root || !active) return;
		const box = root.getBoundingClientRect();
		const top = Math.max(box.top + root.clientTop, 0);
		const bottom = Math.min(box.top + root.clientTop + root.clientHeight, window.innerHeight);
		const line = top + height + remPx() / 2 + 1;
		let found = -1;
		sections.forEach((s, i) => {
			if (s.target.getBoundingClientRect().top <= line) found = i;
		});
		if (pressed !== null) {
			const i = sections.findIndex((s) => s.key === pressed);
			const r = sections[i]?.target.getBoundingClientRect();
			if (i > found && r && r.top < bottom && r.bottom > top) {
				current = pressed;
				return;
			}
			// Still on its way up from below the pane, the press's scroll running: kept.
			if (!(pressing && i > found && r && r.top >= bottom)) pressed = null;
		}
		current = sections[Math.max(found, 0)]?.key ?? null;
	}

	// aria-current follows the scroll, paused while the view is hidden (§5.4 Where you are).
	$effect(() => {
		const root = scroller;
		const targets = sections.map((s) => s.target);
		const margin = Math.round(height + remPx() / 2);
		if (!active || !root || typeof IntersectionObserver === 'undefined') return;
		const observer = new IntersectionObserver(() => locate(), {
			root,
			rootMargin: `-${margin}px 0px ${BELOW}px 0px`,
			threshold: [0, 1]
		});
		for (const target of targets) observer.observe(target);
		untrack(locate);
		return () => observer.disconnect();
	});

	const buttonOf = (key: SectionKey | null) =>
		key ? row?.querySelector<HTMLElement>(`[data-section="${key}"]`) : null;

	// Only the row scrolls when the current button changes, never the pane (§5.4).
	$effect(() => {
		const key = shownCurrent;
		untrack(() => rowComponent?.keepInView(buttonOf(key)));
	});

	/**
	 * Watch the press's own scroll until the pane stops with the target pressed in sight: its
	 * `scrollend`, or where a browser has none, 150 ms without a `scroll` event (never where it has
	 * one: a busy page can go longer than that between two frames of a smooth scroll); then read the
	 * pane again (§5.4 Where you are). A `scrollend` while the target is still below the pane (one
	 * that ends a scroll before the press's own, measured at 320×640) reads it and keeps watching.
	 * A press that scrolls nothing ends with the next scroll.
	 */
	function watchPress(root: HTMLElement) {
		unwatch?.();
		let quiet: ReturnType<typeof setTimeout> | undefined;
		const stop = () => {
			clearTimeout(quiet);
			root.removeEventListener('scroll', moved);
			root.removeEventListener('scrollend', ended);
			unwatch = null;
			pressing = false;
		};
		const ended = () => {
			const target = sections.find((s) => s.key === pressed)?.target;
			const box = root.getBoundingClientRect();
			const bottom = Math.min(box.top + root.clientTop + root.clientHeight, window.innerHeight);
			if (!target || target.getBoundingClientRect().top < bottom) stop();
			locate();
		};
		const moved = () => {
			clearTimeout(quiet);
			quiet = setTimeout(ended, 150);
		};
		if (!('onscrollend' in window)) root.addEventListener('scroll', moved, { passive: true });
		root.addEventListener('scrollend', ended);
		pressing = true;
		unwatch = stop;
	}

	/** Scroll a section's target to the top, then focus it without a second scroll (§5.4). */
	function go(key: SectionKey) {
		const section = sections.find((s) => s.key === key);
		if (!section) return;
		pressed = key;
		current = key;
		if (scroller) watchPress(scroller);
		section.target.scrollIntoView?.({
			block: 'start',
			behavior: reduced.current ? 'auto' : 'smooth'
		});
		section.target.focus({ preventScroll: true });
	}

	/**
	 * Focus a button of the toolbar. With the nav pinned it is in sight, so the focus scrolls
	 * nothing and the row alone brings the button in; static, the focus brings the nav into view.
	 */
	function focusButton(key: SectionKey | null, preventScroll: boolean) {
		const button = buttonOf(key);
		if (!button) return;
		button.focus({ preventScroll });
		rowComponent?.keepInView(button);
	}

	/** "Back to the sections" (§5.4 The way back): the nav's current button. */
	export function focusCurrent() {
		focusButton(clampSection(current, keys), pinned);
	}

	/**
	 * ←, →, Home and End move between the buttons (the APG toolbar), wrapping at the ends; static,
	 * the focus brings the nav into view, as "Back to the sections" does (§5.4 Focus never hidden).
	 */
	function keydown(event: KeyboardEvent) {
		const from = (event.target as HTMLElement).closest?.('[data-section]');
		const at = keys.indexOf(from?.getAttribute('data-section') as SectionKey);
		if (at < 0) return;
		const last = keys.length - 1;
		const next =
			event.key === 'ArrowRight'
				? at === last
					? 0
					: at + 1
				: event.key === 'ArrowLeft'
					? at === 0
						? last
						: at - 1
					: event.key === 'Home'
						? 0
						: event.key === 'End'
							? last
							: -1;
		if (next < 0) return;
		event.preventDefault();
		focusButton(keys[next]!, pinned);
	}
</script>

<nav
	bind:this={nav}
	aria-label="Pumps view sections"
	data-pumps-nav
	data-pinned={pinned ? '' : undefined}
	class={[
		'-mx-3 flex items-center gap-1 border-b border-slate-200 bg-white pl-3 sm:-mx-4 sm:pl-4',
		pinned && 'sticky -top-4 z-[35]'
	]}
>
	<span id="{id}-lead" class="shrink-0 text-xs font-medium text-slate-600">Go to</span>
	<!-- A rule between the lead and the row, so a button scrolled under the row's start reads as
		cut by the row, not run into "Go to". -->
	<span class="h-5 w-px shrink-0 bg-slate-200" aria-hidden="true"></span>
	<ScrollRow
		bind:this={rowComponent}
		bind:row
		role="toolbar"
		aria-labelledby="{id}-lead"
		aria-orientation="horizontal"
		class="min-w-0 flex-1 gap-0.5 pr-3 pl-1 sm:pr-4"
		onkeydown={keydown}
		onfocusin={(event) => {
			const key = (event.target as HTMLElement).getAttribute('data-section') as SectionKey | null;
			if (key) focused = key;
		}}
		onfocusout={(event) => {
			if (!row?.contains(event.relatedTarget as Node | null)) focused = null;
		}}
	>
		{#each sections as section (section.key)}
			{@const mark = section.mark()}
			{@const here = section.key === shownCurrent}
			<button
				type="button"
				data-section={section.key}
				tabindex={section.key === stop ? 0 : -1}
				aria-current={here ? 'location' : undefined}
				aria-label={mark ? `${SECTION_LABELS[section.key]}${mark.words}` : undefined}
				class={[
					'inline-flex min-h-ctl shrink-0 items-center gap-1 rounded-md px-2 text-sm whitespace-nowrap hover:bg-slate-100',
					here
						? 'font-semibold text-blue-900 shadow-[inset_0_-2px_0_var(--color-blue-700)]'
						: 'font-medium text-slate-700'
				]}
				onclick={() => go(section.key)}
			>
				{SECTION_LABELS[section.key]}
				{#if mark?.kind === 'invalid' || mark?.kind === 'warning'}
					<FlagIcon severity={mark.kind} class="size-3.5" />
				{:else if mark}
					<Icon name="octagon" class="size-3.5 shrink-0 text-red-700" />
				{/if}
			</button>
		{/each}
	</ScrollRow>
</nav>
