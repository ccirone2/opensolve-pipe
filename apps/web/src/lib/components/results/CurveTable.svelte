<!--
	A curve's points as a table in its own disclosure (proposal pumps-results-layout.md §9 S7,
	§5.3 The data region, §6.2 "{caption} ({n} points)"): the summary names the curve and counts
	its points; open, the table is full height, so no box scrolls down inside the scrolling pane
	(F23: no scroll trap). It is open by default where the chart cannot be drawn, or where its
	reason column has entries, the reasons a note points to ("the data table says why"), so they
	stay one press away (D10's owner rule). The default only ever opens it: while drawn, a table it
	opened stays open when the default turns (a case switched, the curve computed again), since a
	disclosure never closes itself (§7 Disclosures; S7 review DATA-1). The user's opening or
	closing then holds, kept by the chart (`choice`, bindable) while its data region is hidden.
	The disclosure is a grid item that may shrink below its table (`min-w-0`), so a wide table
	scrolls in its own box and never widens the pane (§7 Targets; S7 review STRUCT-1). Its box
	scrolls sideways where the table is wider, and is a Tab stop and a region named by the caption
	only while it overflows (scrollRegion, §5.7). The caption is visually hidden: the summary shows
	the same words, and the caption stays the table's name.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { scrollRegion } from '$lib/utils/scroll-focus';

	interface Props {
		/** What the table lists: the caption, the summary's first words. */
		caption: string;
		/** How many points it lists. */
		points: number;
		/** Open until the user chooses: the chart cannot be drawn, or its reasons have entries. */
		openByDefault?: boolean;
		/** The user's choice, once made (bindable: the chart keeps it). */
		choice?: boolean;
		/** Which table, for the tests (`data-curve-table`). */
		key: string;
		/**
		 * Explicit ARIA roles on the table, for one that CSS lays out as a list on phones (its rows
		 * and cells then carry their own), with the table's classes.
		 */
		roles?: boolean;
		tableClass?: string;
		/** The table's head and body. */
		children: Snippet;
	}

	let {
		caption,
		points,
		openByDefault = false,
		choice = $bindable(),
		key,
		roles = false,
		tableClass = 'w-full text-sm',
		children
	}: Props = $props();
	const id = $props.id();

	/** "(41 points)", "(1 point)". */
	const count = $derived(`(${points} ${points === 1 ? 'point' : 'points'})`);
	/** Opened by the default while drawn: it stays open, the default never closing it (DATA-1). */
	let openedByDefault = $state(false);
	$effect.pre(() => {
		if (openByDefault) openedByDefault = true;
	});
	const open = $derived(choice ?? (openByDefault || openedByDefault));
	/**
	 * A toggle the user made becomes their choice. One that only draws what `open` says (the
	 * default drawn, or changed while no choice is made) is not a choice: the toggle event fires
	 * for it too, a task later.
	 */
	function toggled(event: Event & { currentTarget: HTMLDetailsElement }) {
		const now = event.currentTarget.open;
		if (choice !== undefined || now !== open) choice = now;
	}
</script>

<!-- A named group, so its chevron turns with this disclosure only, never a Details' inside it
	(§15 item 122's rule; S7 review A11Y-2). The count unbroken, "(42 points)" on one line
	(S7 review LAYOUT-4). -->
<details class="group/curve min-w-0" {open} ontoggle={toggled} data-curve-table={key}>
	<summary class="more-summary">
		<Icon
			name="right"
			class="size-4 shrink-0 text-slate-500 transition-transform group-open/curve:rotate-90 motion-reduce:transition-none"
		/>
		<span class="min-w-0 flex-1 break-words"
			>{caption} <span class="font-normal whitespace-nowrap text-slate-600">{count}</span></span
		>
	</summary>
	<div
		class="scroll-shadow-x relative max-w-full overflow-x-auto rounded-md border border-slate-200 bg-white"
		use:scrollRegion={`${id}-caption`}
	>
		<table role={roles ? 'table' : undefined} class={tableClass}>
			<caption id="{id}-caption" class="sr-only">{caption}</caption>
			{@render children()}
		</table>
	</div>
</details>
