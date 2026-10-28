<!--
	An orifice plate's bore d (proposal orifice-plate.md §6 W2-W3), in the display unit of
	diameters, stored in SI: the one value a plate cannot be added without (no source gives a
	default bore). Used by the plate's form, with the β line under it (`describedby`), and, before
	the plate exists, where it is added (NewComponentFields), where the error says the bore is still
	to enter and goes as soon as the user types (never on blur, so the Add button stays under the
	pointer). The field's bounds are the schema's; whether the bore is smaller than the inlet pipe's
	is the solve's to refuse (a topology issue), and the form's β line says so beforehand.
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import type { FieldChange } from '$lib/components/ui/field-mode';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import { schemaBounds } from '$lib/utils/schema-bounds';

	interface Props {
		/** The stored bore, m, or null while none is entered. */
		boreDiameter: number | null;
		units: UnitPreferences;
		/** An error about the bore from the owner (not entered when the plate is added). */
		error?: string | null;
		/** Receives the new bore (SI). Return false when it was not stored. */
		onchange: (boreDiameter: number) => boolean | void;
		/** Called on each edit of the text, before it is stored (NumberField). */
		oninput?: () => void;
		/** A scenario value (the plate's form). */
		change?: FieldChange | null;
		/** Ids of other elements that describe the field (the form's β line). */
		describedby?: string;
	}

	let {
		boreDiameter,
		units,
		error = null,
		onchange,
		oninput,
		change = null,
		describedby
	}: Props = $props();
</script>

<NumberField
	label="Bore diameter"
	value={boreDiameter}
	category="diameter"
	{units}
	bounds={schemaBounds('Orifice', 'boreDiameter')}
	hint="The diameter of the plate's hole (ISO 5167-2's d) at the flowing temperature; smaller than the inlet pipe's inner diameter."
	{error}
	{change}
	{describedby}
	{oninput}
	onchange={(v) => (v === null ? false : onchange(v))}
/>
