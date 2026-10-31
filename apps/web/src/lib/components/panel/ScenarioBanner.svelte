<!--
	In a scenario, in place of the component actions (proposal scenario-manager.md §6.6): which
	scenario is edited, what can be changed here and what is locked, and a way back to the base
	case, where the layout of the network is edited. One line where it fits (build-density.md §6).
-->
<script lang="ts">
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { focusCurrentHeading } from './focus';

	const ws = useWorkspace();
	const name = $derived(ws.activeScenario?.name ?? '');

	async function toBase() {
		ws.setCase(null);
		await focusCurrentHeading();
	}
</script>

<div
	class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-l-4 border-teal-600 bg-teal-50 py-1 pr-1 pl-2 text-sm text-teal-950"
	role="note"
	aria-label="Scenario"
>
	<Icon name="layers" class="size-4 shrink-0 text-teal-700" />
	<p class="min-w-0 flex-1 basis-56">
		<strong>Scenario: {name}.</strong> Changes here are this scenario's, marked “Changed”; locked values,
		names and units are every case's.
	</p>
	<button type="button" class="btn btn-quiet shrink-0 text-teal-900" onclick={toBase}
		>Switch to base case</button
	>
</div>
