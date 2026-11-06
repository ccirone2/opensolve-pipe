<!--
	"Back to the sections" (proposal pumps-results-layout.md §5.4 The way back, §5.3): the last
	control of a card on the Pumps tab, visually hidden until focused, drawn while the section nav
	is. It focuses the nav's current button, so from a card's foot the nav is one Tab and a press
	away rather than dozens of Shift+Tab. Drawn without PumpsView (no nav), nothing.

	Shown, it takes no room: its wrapper is positioned and holds nothing in flow, and the focused
	button is laid over the card's foot from there (layout.css), white, over what follows. Showing
	or hiding it never changes the pane's height, so a press elsewhere that hides it lands where it
	was aimed, even with the pane at its end (the ui-guide's "so nothing moves").
-->
<script lang="ts">
	import { useSectionNav } from './section-nav.svelte';

	const nav = useSectionNav();
</script>

{#if nav?.shown}
	<div class="relative" data-back-to-sections>
		<button
			type="button"
			class="btn btn-quiet sr-only text-blue-800 focus:not-sr-only focus:border-slate-300 focus:bg-white focus:px-2 focus:shadow-sm"
			onclick={() => nav.back()}>Back to the sections</button
		>
	</div>
{/if}
