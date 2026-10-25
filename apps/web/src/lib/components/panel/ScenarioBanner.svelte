<!--
	In a scenario, in place of the component actions (proposal scenario-manager.md §6.6): which
	scenario is edited, what can be changed here and what is locked, and a way back to the base
	case, where the layout of the network is edited. About the height of the actions on phones.
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
	class="flex flex-wrap items-start gap-x-3 gap-y-2 rounded-md border border-l-4 border-teal-600 bg-teal-50 p-3 text-sm text-teal-950"
	role="note"
	aria-label="Scenario"
>
	<Icon name="layers" class="mt-0.5 size-4 shrink-0 text-teal-700" />
	<p class="min-w-0 flex-1 basis-56">
		<strong>Scenario: {name}.</strong> Values you change here are recorded in this scenario and marked
		“Changed”. Locked values are the base case's, the same in every scenario. Names and display units
		are shared by every case.
	</p>
	<button type="button" class="btn shrink-0" onclick={toBase}>Switch to base case</button>
</div>
