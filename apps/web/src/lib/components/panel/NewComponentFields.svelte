<!--
	Values the user enters where a component is added, for a kind that has no default for them
	(factory.ts ENTRY_KINDS, missingEntries): an assigned-flow node's flow, an equipment item's
	rating. Nothing for other kinds. `values` holds what is entered (SI); `errors` say what is
	still missing when the owner tries to add, each at its field, and each goes as soon as the
	user types that value. The Add button can sit below these fields, and a field stores what was
	typed when it loses focus, on the press of that button: nothing here changes size then (the
	error is gone already, a flow of 0 has its note in the hint's place, a density button's note
	went as the density was typed over it), so the button stays under the pointer and the click
	adds the component.
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import type { ComponentKind, EnteredValues, MissingEntry, RatingDraft } from '$lib/utils/factory';
	import AssignedFlowFields from './AssignedFlowFields.svelte';
	import EquipmentRatingFields from './EquipmentRatingFields.svelte';

	interface Props {
		kind: ComponentKind;
		units: UnitPreferences;
		values: EnteredValues;
		errors: readonly MissingEntry[];
	}

	let { kind, units, values = $bindable(), errors = $bindable() }: Props = $props();

	/** The rating being entered: a rated point until another kind is chosen. */
	const draft = $derived<RatingDraft>(values.rating ?? { kind: 'point' });

	function drop(field: string) {
		if (errors.some((e) => e.field === field)) errors = errors.filter((e) => e.field !== field);
	}
</script>

{#if kind === 'assigned_flow'}
	<AssignedFlowFields
		flow={values.flow ?? null}
		{units}
		error={errors.find((e) => e.field === 'flow')?.message ?? null}
		zeroNote="hint"
		oninput={() => drop('flow')}
		onchange={(flow) => {
			values = { ...values, flow };
			drop('flow');
		}}
	/>
{:else if kind === 'equipment'}
	<EquipmentRatingFields
		rating={draft}
		{units}
		{errors}
		onkind={(next) => {
			// No value is carried to another kind (a rated flow is not a Cv).
			values = { ...values, rating: { kind: next } };
			errors = [];
		}}
		oninput={(field) => drop(`rating.${field}`)}
		onvalue={(field, v) => {
			values = { ...values, rating: { ...draft, [field]: v } };
			drop(`rating.${field}`);
		}}
	/>
{/if}
