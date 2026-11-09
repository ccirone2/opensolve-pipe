<!--
	A curve's points as a table in its own disclosure (proposal pumps-results-layout.md §9 S7,
	§5.3 The data region, §6.2 "{caption} ({n} points)"): the summary names the curve and counts
	its points; open, the table is full height, so no box scrolls down inside the scrolling pane
	(F23: no scroll trap). It is open by default where the chart cannot be drawn, or where its
	reason column has entries, the reasons a note points to ("the data table says why"), so they
	stay one press away (D10's owner rule); the user's opening or closing then holds, kept by the
	chart (`choice`, bindable) while its data region is hidden. Its box scrolls sideways where the
	table is wider, and is a Tab stop and a region named by the caption only while it overflows
	(scrollRegion, §5.7). The caption is visually hidden: the summary shows the same words, and the
	caption stays the table's name.
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
	const open = $derived(choice ?? openByDefault);
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

<details class="group" {open} ontoggle={toggled} data-curve-table={key}>
	<summary class="more-summary">
		<Icon
			name="right"
			class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
		/>
		<span class="min-w-0 flex-1 break-words"
			>{caption} <span class="font-normal text-slate-600">{count}</span></span
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
