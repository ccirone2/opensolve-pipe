<!--
	The calculation server's own sentence behind a message the browser tells in names and display
	units (a topology issue, a system-curve point without a head): closed by default, so nothing the
	server said is lost and the browser's wording can be checked against it. With a `subject`, the
	summary is named "Details of {subject}" by a visually hidden suffix, its visible word unchanged,
	so the Pumps tab's Details are told apart (proposal pumps-results-layout.md §5.3, §6.2).
-->
<script lang="ts">
	import Icon from '$lib/components/ui/Icon.svelte';

	let { detail, subject }: { detail: string; subject?: string } = $props();
</script>

<details class="group text-xs" data-issue-detail>
	<summary
		class="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
	>
		<Icon
			name="right"
			class="size-3 shrink-0 transition-transform group-open:rotate-90 motion-reduce:transition-none"
		/>
		<!-- The space outside the hidden suffix, so every name computation keeps it. -->
		Details
		{#if subject}<span class="sr-only">of {subject}</span>{/if}
	</summary>
	<p class="break-words">Calculation server's message: {detail}</p>
</details>
