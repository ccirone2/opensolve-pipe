<!--
	An orifice plate (proposal orifice-plate.md §6 W3), after the elevation: its bore (OrificeFields),
	the β line read-only under it (β = d ÷ D with D the inlet pipe's inner diameter, utils/orifice.ts;
	also in the bore's description), the discharge coefficient (ISO 5167-2's by default, or an
	entered C, user data, in ResistanceField's pattern: a choice picked with no value yet keeps the
	stored one, with a warning), the optional pressure taps of a flow meter, and the hint. In a
	scenario the bore and the C are scenario values (D15); the C's choice and its number are one
	change, noted once at its group. The taps are installation, the same in every case (locked).
	No ISO 5167-2 range is checked here: the limits are the API's, and the solve flags them.
-->
<script lang="ts">
	import type { Orifice, OrificeTaps } from '$lib/api/types';
	import ChangeNote from '$lib/components/ui/ChangeNote.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { hasChangeNote } from '$lib/components/ui/field-mode';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { betaLine, inletBore, NO_TAPS_LABEL, TAP_LABELS } from '$lib/utils/orifice';
	import { withOptional } from '$lib/utils/piping';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import OrificeFields from '../OrificeFields.svelte';

	let { component }: { component: Orifice } = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const inlet = $derived(inletBore(ws.project, component.id, ws.library));
	const beta = $derived(betaLine(component.boreDiameter, inlet, ws.units, ws.library.nominalSizes));

	type Source = 'iso' | 'entered';
	/** "Entered C" picked while none is stored: kept here until a number is entered. */
	let pending = $state(false);
	const entered = $derived(component.dischargeCoefficient ?? null);
	const source = $derived<Source>(entered !== null || pending ? 'entered' : 'iso');
	const coefficientChange = $derived(ws.componentChange(component.id, 'dischargeCoefficient'));
	/** The group's note, which describes the choice and the number (they show none of their own). */
	const groupNote = $derived(
		hasChangeNote(coefficientChange) ? `${id}-coefficient-change` : undefined
	);
	/** "Entered C" picked with no C yet: the warning says ISO's applies, and describes both. */
	const waiting = $derived(source === 'entered' && entered === null);
	const described = $derived(
		[groupNote, waiting ? `${id}-pending` : undefined].filter(Boolean).join(' ') || undefined
	);

	const TAPS: readonly { value: OrificeTaps | 'none'; label: string }[] = [
		{ value: 'none', label: NO_TAPS_LABEL },
		...(Object.keys(TAP_LABELS) as OrificeTaps[]).map((t) => ({ value: t, label: TAP_LABELS[t] }))
	];

	function setCoefficient(value: number | null, label: string): boolean {
		return ws.editComponent<Orifice>(component.id, label, (c) =>
			withOptional(c, 'dischargeCoefficient', value)
		);
	}

	function choose(next: Source) {
		if (next === source) return;
		if (next === 'iso') {
			pending = false;
			if (entered !== null) setCoefficient(null, 'use ISO 5167-2 discharge coefficient');
			return;
		}
		pending = true;
	}

	function enter(v: number | null): boolean | void {
		if (v === null) return false;
		const accepted = setCoefficient(v, 'change discharge coefficient');
		if (accepted !== false) pending = false;
		return accepted;
	}
</script>

<div class="space-y-1">
	<OrificeFields
		boreDiameter={component.boreDiameter}
		units={ws.units}
		change={ws.componentChange(component.id, 'boreDiameter')}
		describedby="{id}-beta"
		onchange={(v) =>
			ws.editComponent<Orifice>(component.id, 'change bore diameter', (c) => {
				c.boreDiameter = v;
			})}
	/>
	<output
		id="{id}-beta"
		class={['block text-sm', beta.warning ? 'text-amber-800' : 'text-slate-700']}
		aria-live="polite">{beta.text}</output
	>
</div>

<fieldset class="space-y-3 sm:col-span-2">
	<legend class="label mb-1">Discharge coefficient</legend>
	<ChangeNote change={coefficientChange} id="{id}-coefficient-change" />
	<SelectField
		label="Discharge coefficient"
		hideLabel
		value={source}
		options={[
			{ value: 'iso', label: 'ISO 5167-2 (Reader-Harris/Gallagher), the default' },
			{ value: 'entered', label: 'Entered C' }
		]}
		change={coefficientChange}
		changeNote={false}
		describedby={described}
		onchange={choose}
	/>
	{#if source === 'entered'}
		<NumberField
			label="Entered C"
			value={entered}
			category="dimensionless"
			units={ws.units}
			bounds={schemaBounds('Orifice', 'dischargeCoefficient')}
			hint="ISO 5167-2's discharge coefficient C at this plate's taps (at D and D/2 tappings for a plate without taps), from a calibration or datasheet: q = C ÷ √(1 − β⁴) × (π/4)d² × √(2Δp/ρ). A datasheet's flow coefficient α = C ÷ √(1 − β⁴) is not C: enter α × √(1 − β⁴). The plate's loss uses this C moved to D and D/2 tappings."
			change={coefficientChange}
			changeNote={false}
			describedby={described}
			onchange={enter}
		/>
	{/if}
	{#if waiting}
		<p id="{id}-pending" class="flex items-start gap-1 text-sm text-amber-800">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span
				>Enter C to use it; until then ISO 5167-2's discharge coefficient applies.</span
			>
		</p>
	{/if}
</fieldset>

<SelectField
	label="Pressure taps"
	value={component.taps ?? 'none'}
	options={TAPS}
	hint="Where a flow meter's pressure taps are; the differential pressure is reported at them, and an entered C is the C at them. The plate's loss uses the C at D and D/2 tappings whatever the taps."
	onchange={(v) =>
		ws.editComponent<Orifice>(component.id, 'change pressure taps', (c) =>
			withOptional(c, 'taps', v === 'none' ? null : v)
		)}
/>

<p class="hint sm:col-span-2">
	An orifice plate: a restriction orifice (a minimum-flow bypass, balancing) or an orifice flow
	meter. Its loss in the network is ISO 5167-2's permanent pressure loss, the part of the pressure
	difference across the plate not recovered downstream, with the discharge coefficient at D and D/2
	tappings. A meter's differential pressure is reported at its taps. Flow from outlet to inlet,
	flashing at the vena contracta, and a plate or flow outside ISO 5167-2's validated range are
	flagged. For a restriction orifice given by a pressure drop at a flow, a Cv or a Kv, use
	Equipment.
</p>
