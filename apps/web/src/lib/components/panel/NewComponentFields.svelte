<!--
	Values the user enters where a component is added, for a kind that has no default for them
	(factory.ts missingEntry): an assigned-flow node's flow. Nothing for other kinds. `values`
	holds what is entered (SI); `error` says what is still missing when the owner tries to add,
	and goes as soon as the user types the value. The Add button can sit below these fields, and
	a field stores what was typed when it loses focus, on the press of that button: nothing here
	changes size then (the error is gone already, a flow of 0 has its note in the hint's place),
	so the button stays under the pointer and the click adds the component.
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import type { ComponentKind, EnteredValues } from '$lib/utils/factory';
	import AssignedFlowFields from './AssignedFlowFields.svelte';

	interface Props {
		kind: ComponentKind;
		units: UnitPreferences;
		values: EnteredValues;
		error: string | null;
	}

	let { kind, units, values = $bindable(), error = $bindable() }: Props = $props();
</script>

{#if kind === 'assigned_flow'}
	<AssignedFlowFields
		flow={values.flow ?? null}
		{units}
		{error}
		zeroNote="hint"
		oninput={() => (error = null)}
		onchange={(flow) => {
			values = { ...values, flow };
			error = null;
		}}
	/>
{/if}
