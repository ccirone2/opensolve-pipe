<!--
	The calculation server's own sentence behind a message the browser tells in names and display
	units (a topology issue, a system-curve point without a head): closed by default, so nothing the
	server said is lost and the browser's wording can be checked against it.
-->
<script lang="ts">
	import Icon from '$lib/components/ui/Icon.svelte';

	let { detail }: { detail: string } = $props();
</script>

<details class="group text-xs" data-issue-detail>
	<summary
		class="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
	>
		<Icon name="right" class="size-3 shrink-0 transition-transform group-open:rotate-90" />
		Details
	</summary>
	<p class="break-words">Calculation server's message: {detail}</p>
</details>
