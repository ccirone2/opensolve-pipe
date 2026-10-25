<!--
	The note under a scenario value (proposal scenario-manager.md §6.6, "Field states"): in a
	scenario that changes it, "[Changed] Base: 2.50 m [Reset]" (its `id` describes the input:
	"Changed in this scenario. Base value 2.50 m."); in the base case, which scenarios set their
	own value. Nothing otherwise. Composite inputs (a pipe's size and material, the fluid, a
	valve's resistance) show one note for the group.
-->
<script lang="ts">
	import Icon from './Icon.svelte';
	import { setByText, type FieldChange } from './field-mode';

	let { change, id }: { change: FieldChange; id: string } = $props();
</script>

{#if change.inScenario && change.changed}
	<div class="mt-1 flex flex-wrap items-center gap-x-2 text-sm">
		<span {id} class="sr-only">Changed in this scenario. Base value {change.baseText}.</span>
		<span
			class="rounded bg-teal-700 px-1.5 py-0.5 text-xs font-semibold text-white"
			aria-hidden="true">Changed</span
		>
		<span class="min-w-0 text-slate-700" aria-hidden="true">Base: {change.baseText}</span>
		<button
			type="button"
			class="btn btn-quiet -my-1 px-2 text-blue-800"
			aria-label="Reset {change.label} to the base value, {change.baseText}"
			onclick={() => change.reset()}
		>
			Reset
		</button>
	</div>
{:else if !change.inScenario && change.setBy.length}
	<p {id} class="hint flex items-start gap-1">
		<Icon name="layers" class="mt-0.5 size-4 shrink-0 text-teal-700" />
		<span>{setByText(change.setBy)}</span>
	</p>
{/if}
