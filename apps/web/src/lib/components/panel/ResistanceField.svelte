<!--
	Valve resistance: the default (stated by the caller, e.g. "Crane TP-410 K ...") or a value the
	user enters as K, Cv or Kv. Cv and Kv are defined quantities and are stored as entered; the
	solver converts them to K at the connected inner diameter. Changing the kind clears the value.
-->
<script lang="ts">
	import type { FlowCoefficient, UnitPreferences } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { schemaBounds } from '$lib/utils/schema-bounds';

	type Choice = 'default' | FlowCoefficient['kind'];

	interface Props {
		value: FlowCoefficient | null | undefined;
		/** What "default" means for this valve. */
		defaultLabel: string;
		units: UnitPreferences;
		onchange: (value: FlowCoefficient | null) => boolean | void;
	}

	let { value, defaultLabel, units, onchange }: Props = $props();

	/**
	 * A kind picked while no value is stored: kept here, with the field empty, until a number
	 * is entered (the default applies meanwhile).
	 */
	let pending = $state<FlowCoefficient['kind'] | null>(null);
	const choice = $derived<Choice>(value?.kind ?? pending ?? 'default');

	const HINTS: Record<FlowCoefficient['kind'], string> = {
		K: 'Loss coefficient, referenced to the velocity in the connected pipe.',
		Cv: 'US gpm of water at 1 psi pressure drop (stored as entered).',
		Kv: 'm³/h of water at 1 bar pressure drop (stored as entered).'
	};

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
	<SelectField
		label="Resistance given as"
		hideLabel
		value={choice}
		options={[
			{ value: 'default', label: `Default: ${defaultLabel}` },
			{ value: 'K', label: 'K (loss coefficient)' },
			{ value: 'Cv', label: 'Cv (US flow coefficient)' },
			{ value: 'Kv', label: 'Kv (metric flow coefficient)' }
		]}
		onchange={choose}
	/>
	{#if choice !== 'default'}
		<NumberField
			label={choice}
			value={value?.value}
			category="dimensionless"
			{units}
			bounds={schemaBounds('FlowCoefficient', 'value')}
			hint={HINTS[choice]}
			warning={value ? null : `Enter ${choice} to use it; until then the default applies.`}
			onchange={enter}
		/>
	{/if}
</fieldset>
