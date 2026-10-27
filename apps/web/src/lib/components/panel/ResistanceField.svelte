<!--
	Valve resistance: the default (stated by the caller, e.g. "Crane TP-410 K ...") or a value the
	user enters as K, Cv or Kv. Cv and Kv are defined quantities and are stored as entered; the
	solver converts them to K at the connected inner diameter. Changing the kind clears the value.
-->
<script lang="ts">
	import type { FlowCoefficient, UnitPreferences } from '$lib/api/types';
	import ChangeNote from '$lib/components/ui/ChangeNote.svelte';
	import { hasChangeNote, type FieldChange } from '$lib/components/ui/field-mode';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { COEFFICIENT_HINTS, COEFFICIENT_LABELS } from '$lib/utils/flow-coefficient';
	import { schemaBounds } from '$lib/utils/schema-bounds';

	type Choice = 'default' | FlowCoefficient['kind'];

	interface Props {
		value: FlowCoefficient | null | undefined;
		/** What "default" means for this valve. */
		defaultLabel: string;
		units: UnitPreferences;
		onchange: (value: FlowCoefficient | null) => boolean | void;
		/** A scenario value: the kind and the number are one change, noted once at the group. */
		change?: FieldChange | null;
	}

	let { value, defaultLabel, units, onchange, change = null }: Props = $props();
	const noteId = $props.id();
	/** The group's note, which describes the kind and the number (they show none of their own). */
	const groupNote = $derived(hasChangeNote(change) ? `${noteId}-change` : undefined);

	/**
	 * A kind picked while no value is stored: kept here, with the field empty, until a number
	 * is entered (the default applies meanwhile).
	 */
	let pending = $state<FlowCoefficient['kind'] | null>(null);
	const choice = $derived<Choice>(value?.kind ?? pending ?? 'default');

	/**
	 * K, Cv and Kv are different quantities: a stored number is never carried over to another
	 * kind (K = 5 and Cv = 5 are very different restrictions). Changing the kind clears the value,
	 * so the default applies until a value of the new kind is entered (undo restores the old one).
	 */
	function choose(next: Choice) {
		if (next === choice) return;
		pending = next === 'default' ? null : next;
		if (value) onchange(null);
	}

	function enter(v: number | null): boolean | void {
		if (v === null || choice === 'default') return false;
		const kind = choice;
		const accepted = onchange({ kind, value: v });
		if (accepted !== false) pending = null;
		return accepted;
	}
</script>

<fieldset class="space-y-3 sm:col-span-2">
	<legend class="label mb-1">Resistance</legend>
	{#if change}<ChangeNote {change} id="{noteId}-change" />{/if}
	<SelectField
		label="Resistance given as"
		hideLabel
		value={choice}
		options={[
			{ value: 'default', label: `Default: ${defaultLabel}` },
			{ value: 'K', label: COEFFICIENT_LABELS.K },
			{ value: 'Cv', label: COEFFICIENT_LABELS.Cv },
			{ value: 'Kv', label: COEFFICIENT_LABELS.Kv }
		]}
		{change}
		changeNote={false}
		describedby={groupNote}
		onchange={choose}
	/>
	{#if choice !== 'default'}
		<NumberField
			label={choice}
			value={value?.value}
			category="dimensionless"
			{units}
			bounds={schemaBounds('FlowCoefficient', 'value')}
			hint={COEFFICIENT_HINTS[choice]}
			warning={value ? null : `Enter ${choice} to use it; until then the default applies.`}
			{change}
			changeNote={false}
			describedby={groupNote}
			onchange={enter}
		/>
	{/if}
</fieldset>
