<!--
	A relief valve's set pressure and capacity (proposal pressure-relief-valve.md §6 W1, W3), the two
	values it cannot be added without (neither has a default). The set is a pressure difference,
	inlet minus outlet static, in the pressure unit with no gauge marker. The capacity is one of
	three kinds, never mixed: an API 526 orifice letter (its effective area from x-relief-data,
	shown in the area unit), an API 520 effective area, each with API 520's effective coefficient
	and ASME's overpressure (preliminary, a read-only line that names ASME VIII's 15 psi scope and
	turns into a warning for a set below it); or the valve's certified actual area,
	rated coefficient and optional full-lift overpressure (ASME's default by default, its value at
	this set shown). No value is carried from one kind to another.

	Used by the valve's form (the stored values, or a kind picked whose values are not all entered
	yet: `warning` says which capacity applies meanwhile) and where the valve is added, before it
	exists (`errors`: the values still to enter, each at its field until the user types there).
	Nothing here changes size when a field stores its value on losing focus (an error goes as the
	user types), so a button below never moves under the pointer. In a scenario the form gives
	`setChange`, `wholeChange` (a change of kind: one change of the whole capacity, noted once at
	the group) and `partChange` (a value of the base's kind, noted at its field).
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import ChangeNote from '$lib/components/ui/ChangeNote.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { hasChangeNote, type FieldChange } from '$lib/components/ui/field-mode';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import {
		CAPACITY_KINDS,
		type CapacityDraft,
		type CapacityField,
		type CapacityKind,
		type MissingEntry
	} from '$lib/utils/factory';
	import {
		areaLabel,
		asmeDefaultText,
		asmeScopeText,
		CAPACITY_FIELD_LABELS,
		CAPACITY_KIND_LABELS,
		defaultOverpressureLine,
		letterOptionLabel,
		preliminaryLine,
		reliefLetters
	} from '$lib/utils/relief';
	import { schemaBounds } from '$lib/utils/schema-bounds';

	interface Props {
		/** The set pressure, Pa (a difference), or null while none is entered. */
		setPressure: number | null;
		/** The capacity shown: the stored one, or a draft (the values of its kind entered so far). */
		capacity: CapacityDraft;
		units: UnitPreferences;
		/** Values still to enter where the valve is added, each shown at its field. */
		errors?: readonly MissingEntry[];
		/** A set pressure entered (SI). Return false when it was not stored. */
		onset: (value: number) => boolean | void;
		/** Another kind of capacity was picked: no value is carried to it. */
		onkind: (kind: CapacityKind) => void;
		/**
		 * A capacity value entered (SI; a letter as chosen; null: a certified overpressure back to
		 * ASME's default). Return false when it was not stored.
		 */
		onvalue: (field: CapacityField, value: number | string | null) => boolean | void;
		/** Each edit of a field's text, before it is stored (to drop that field's error). */
		oninput?: (field: 'setPressure' | `capacity.${CapacityField}`) => void;
		/** A note under the capacity, e.g. which capacity applies until a new kind is entered. */
		warning?: string | null;
		/** A scenario's change of the set pressure. */
		setChange?: FieldChange | null;
		/** A scenario's whole-capacity change: noted once at the group; makes the choice editable. */
		wholeChange?: FieldChange | null;
		/** A scenario's change of one value of the base's kind (null: the whole change applies). */
		partChange?: ((field: CapacityField) => FieldChange | null) | null;
	}

	let {
		setPressure,
		capacity,
		units,
		errors = [],
		onset,
		onkind,
		onvalue,
		oninput,
		warning = null,
		setChange = null,
		wholeChange = null,
		partChange = null
	}: Props = $props();

	const noteId = $props.id();
	/** The group's note (a whole-capacity change), which describes every field of the capacity. */
	const groupNote = $derived(hasChangeNote(wholeChange) ? `${noteId}-change` : undefined);
	/** The warning (which capacity applies until a kind picked is entered): it describes them all. */
	const warningId = $derived(warning ? `${noteId}-warning` : undefined);
	const described = (...ids: (string | false | undefined)[]) =>
		ids.filter(Boolean).join(' ') || undefined;

	const errorOf = (field: string) => errors.find((e) => e.field === field)?.message ?? null;

	/** A field's scenario state: the whole change while it exists (noted at the group), else its own. */
	const changeOf = (field: CapacityField): FieldChange | null =>
		wholeChange && (wholeChange.changed || !partChange)
			? wholeChange
			: (partChange?.(field) ?? wholeChange);
	const groupNoted = (field: CapacityField) => changeOf(field) === wholeChange;

	const letterOptions = $derived([
		...(capacity.letter ? [] : [{ value: '', label: 'Choose a letter', disabled: true }]),
		...reliefLetters().map((l) => ({ value: l, label: letterOptionLabel(l, units) }))
	]);

	/** A certified overpressure: ASME's default, or one entered ("Entered" picked, none yet). */
	type OverpressureSource = 'asme' | 'entered';
	let pendingEntered = $state(false);
	const overpressureSource = $derived<OverpressureSource>(
		capacity.overpressure !== undefined || pendingEntered ? 'entered' : 'asme'
	);
	const defaultLine = $derived(defaultOverpressureLine(setPressure, units));
	/** The preliminary kinds' line: a warning for a set below ASME VIII's scope. */
	const preliminary = $derived(preliminaryLine(units, setPressure));
	/** That warning describes the letter or the effective area it is about. */
	const preliminaryNote = $derived(preliminary.warning ? `${noteId}-preliminary` : undefined);
	const waitingOverpressure = $derived(
		overpressureSource === 'entered' && capacity.overpressure === undefined
	);
</script>

<div class="min-w-0 sm:col-span-2">
	<NumberField
		label="Set pressure (difference)"
		value={setPressure}
		category="pressure"
		{units}
		bounds={schemaBounds('ReliefValve', 'setPressure')}
		hint="The static pressure difference, inlet minus outlet, at which the valve starts to open. Discharging to atmosphere at the valve's elevation it is the gauge set pressure; with a constant back pressure (a return line) it is the bench setting: the set pressure minus that back pressure. Back pressure adds to the inlet pressure at which a conventional valve opens."
		error={errorOf('setPressure')}
		change={setChange}
		oninput={() => oninput?.('setPressure')}
		onchange={(v) => (v === null ? false : onset(v))}
	/>
</div>

<fieldset class="grid gap-4 sm:col-span-2 sm:grid-cols-2">
	<legend class="label mb-1 sm:col-span-2">Capacity</legend>
	{#if wholeChange && hasChangeNote(wholeChange)}
		<div class="sm:col-span-2"><ChangeNote change={wholeChange} id="{noteId}-change" /></div>
	{/if}
	<SelectField
		class="sm:col-span-2"
		label="Capacity given by"
		value={capacity.kind}
		options={CAPACITY_KINDS.map((k) => ({ value: k, label: CAPACITY_KIND_LABELS[k] }))}
		hint="The manufacturer's actual orifice area with its rated coefficient, or an API 526 letter or effective area with API 520's effective values: never one from each. A letter or an effective area is for preliminary sizing."
		change={wholeChange}
		changeNote={false}
		describedby={described(groupNote, warningId)}
		onchange={(kind) => {
			pendingEntered = false;
			onkind(kind);
		}}
	/>
	{#if capacity.kind === 'api526'}
		<div class="min-w-0 space-y-1 sm:col-span-2">
			<SelectField
				label={CAPACITY_FIELD_LABELS.letter}
				value={capacity.letter ?? ''}
				options={letterOptions}
				hint="API 526's effective orifice area of the letter (via fluids), for preliminary sizing; the valve selected then has its own actual area and rated coefficient."
				change={changeOf('letter')}
				changeNote={!groupNoted('letter')}
				invalid={!!errorOf('capacity.letter')}
				describedby={described(
					groupNoted('letter') && groupNote,
					warningId,
					!!errorOf('capacity.letter') && `${noteId}-letter-error`,
					preliminaryNote
				)}
				onchange={(letter) => {
					oninput?.('capacity.letter');
					onvalue('letter', letter);
				}}
			/>
			{#if errorOf('capacity.letter')}
				<p
					id="{noteId}-letter-error"
					role="alert"
					class="mt-1 flex items-start gap-1 text-sm text-red-700"
				>
					<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span
						>{errorOf('capacity.letter')}</span
					>
				</p>
			{/if}
		</div>
	{/if}
	{#if capacity.kind === 'effective' || capacity.kind === 'certified'}
		<NumberField
			label={areaLabel(capacity.kind)}
			value={capacity.area ?? null}
			category="area"
			{units}
			bounds={schemaBounds(
				capacity.kind === 'effective' ? 'EffectiveOrifice' : 'CertifiedOrifice',
				'area'
			)}
			hint={capacity.kind === 'effective'
				? "An API 520 effective discharge area, as API 520's liquid sizing equation gives it (goal seek sizes it against the network); never a valve's actual orifice area."
				: "The valve's actual orifice area, from its certification; used with its rated coefficient, never with API 526's effective area."}
			error={errorOf('capacity.area')}
			change={changeOf('area')}
			changeNote={!groupNoted('area')}
			describedby={described(
				groupNoted('area') && groupNote,
				warningId,
				capacity.kind === 'effective' && preliminaryNote
			)}
			oninput={() => oninput?.('capacity.area')}
			onchange={(v) => (v === null ? false : onvalue('area', v))}
		/>
	{/if}
	{#if capacity.kind === 'api526' || capacity.kind === 'effective'}
		<p
			id="{noteId}-preliminary"
			class={[
				'sm:col-span-2',
				preliminary.warning ? 'flex items-start gap-1 text-sm text-amber-800' : 'hint'
			]}
		>
			{#if preliminary.warning}<Icon name="alert" class="mt-0.5 size-4 shrink-0" />{/if}
			<span>{preliminary.text}</span>
		</p>
	{/if}
	{#if capacity.kind === 'certified'}
		<NumberField
			label={CAPACITY_FIELD_LABELS.dischargeCoefficient}
			value={capacity.dischargeCoefficient ?? null}
			category="dimensionless"
			{units}
			bounds={schemaBounds('CertifiedOrifice', 'dischargeCoefficient')}
			hint="The valve's rated coefficient of discharge for liquid, from its certification: ASME's K, 0.9 × the measured coefficient. Never API 520's effective coefficient with an actual area."
			error={errorOf('capacity.dischargeCoefficient')}
			change={changeOf('dischargeCoefficient')}
			changeNote={!groupNoted('dischargeCoefficient')}
			describedby={described(groupNoted('dischargeCoefficient') && groupNote, warningId)}
			oninput={() => oninput?.('capacity.dischargeCoefficient')}
			onchange={(v) => (v === null ? false : onvalue('dischargeCoefficient', v))}
		/>
		<div class="min-w-0 space-y-2 sm:col-span-2">
			<SelectField
				label={CAPACITY_FIELD_LABELS.overpressure}
				value={overpressureSource}
				options={[
					{ value: 'asme', label: asmeDefaultText(units) },
					{ value: 'entered', label: 'Entered (certified)' }
				]}
				hint="The overpressure at which this valve reaches its rated capacity, from its certification; not the allowable accumulation a valve is sized for. Required for a set below {asmeScopeText(
					units
				)}."
				change={changeOf('overpressure')}
				changeNote={!groupNoted('overpressure')}
				describedby={described(
					groupNoted('overpressure') && groupNote,
					warningId,
					`${noteId}-overpressure`
				)}
				onchange={(next) => {
					if (next === overpressureSource) return;
					if (next === 'asme') {
						pendingEntered = false;
						if (capacity.overpressure !== undefined) onvalue('overpressure', null);
						return;
					}
					pendingEntered = true;
				}}
			/>
			{#if overpressureSource === 'entered'}
				<NumberField
					label="Entered overpressure"
					value={capacity.overpressure ?? null}
					category="fraction"
					{units}
					bounds={schemaBounds('CertifiedOrifice', 'overpressure')}
					hint="The rise of the pressure difference above the set, as a fraction of the set, at which this valve reaches full lift."
					change={changeOf('overpressure')}
					changeNote={false}
					describedby={described(groupNoted('overpressure') && groupNote, warningId)}
					oninput={() => oninput?.('capacity.overpressure')}
					onchange={(v) => {
						if (v === null) return false;
						const stored = onvalue('overpressure', v);
						if (stored !== false) pendingEntered = false;
						return stored;
					}}
				/>
			{/if}
			<p
				id="{noteId}-overpressure"
				class={[
					'flex items-start gap-1 text-sm',
					waitingOverpressure || (overpressureSource === 'asme' && defaultLine.warning)
						? 'text-amber-800'
						: 'text-slate-700'
				]}
			>
				{#if waitingOverpressure || (overpressureSource === 'asme' && defaultLine.warning)}
					<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
				{/if}
				<span
					>{waitingOverpressure
						? "Enter the overpressure to use it; until then ASME's default applies."
						: overpressureSource === 'asme'
							? defaultLine.text
							: 'Entered: user data, from the certification.'}</span
				>
			</p>
		</div>
	{/if}
	{#if warning}
		<p id={warningId} class="flex items-start gap-1 text-sm text-amber-800 sm:col-span-2">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span>{warning}</span>
		</p>
	{/if}
</fieldset>
