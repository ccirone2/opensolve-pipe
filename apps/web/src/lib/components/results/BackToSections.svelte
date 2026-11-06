<!--
	"Back to the sections" (proposal pumps-results-layout.md §5.4 The way back, §5.3): the last
	control of a card on the Pumps tab, visually hidden until focused, drawn while the section nav
	is. It focuses the nav's current button, so from a card's foot the nav is one Tab and a press
	away rather than dozens of Shift+Tab. Drawn without PumpsView (no nav), nothing.

	Its wrapper is positioned: a visually hidden element is absolutely placed, and with no
	positioned ancestor inside the pane's scroller it would escape the scroller's clip and make the
	page itself scroll (as ResultsTable's boxes are `relative` for their flags' hidden words).
-->
<script lang="ts">
	import { useSectionNav } from './section-nav.svelte';

	const nav = useSectionNav();
</script>

{#if nav?.shown}
	<div class="relative" data-back-to-sections>
		<button
			type="button"
			class="btn btn-quiet sr-only text-blue-800 focus:not-sr-only focus:px-2"
			onclick={() => nav.back()}>Back to the sections</button
		>
	</div>
{/if}
