<!--
	Valve resistance: the default (stated by the caller, e.g. "Crane TP-410 K ..."), a value the
	user enters as K, Cv or Kv, or an entry of the project library (CLAUDE.md D22: a K at the bore
	it is stated at, a Cv or a Kv, with its source), referred to by id so an edit to the entry
	reaches every valve that uses it. Cv and Kv are defined quantities and are stored as entered;
	the solver converts them to K at the connected inner diameter, and moves an entry's K to that
	bore (K₀ (D/d₀)⁴). Changing the kind clears the value.

	An entry is shown read-only, with "Edit in the library" (in a scenario "Show in the library":
	the library is base data, the same in every case). "New entry…" opens the library's new entry
	form, whose entry is then used here (not offered in a scenario; offered disabled, saying so,
	when the library holds as many entries as a project may: `libraryFull`). A reference to an
	entry the project does not have is kept and said, for the user to choose another (the solve
	reports it).
-->
<script lang="ts">
	import type { ResistanceSpec, UnitPreferences, ValveResistance } from '$lib/api/types';
	import ChangeNote from '$lib/components/ui/ChangeNote.svelte';
	import { hasChangeNote, type FieldChange } from '$lib/components/ui/field-mode';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField, { type SelectOption } from '$lib/components/ui/SelectField.svelte';
	import { COEFFICIENT_HINTS, COEFFICIENT_LABELS } from '$lib/utils/flow-coefficient';
	import { entryName, entryValueText, isResistanceRef } from '$lib/utils/project-library';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { newOptionLabel } from '$lib/components/workspace/library/limits';

	type Kind = 'K' | 'Cv' | 'Kv';
	type Choice = 'default' | Kind | `entry:${string}` | 'new-entry';

	interface Props {
		value: ValveResistance | null | undefined;
		/** What "default" means for this valve. */
		defaultLabel: string;
		units: UnitPreferences;
		onchange: (value: ValveResistance | null) => boolean | void;
		/** A scenario value: the kind and the number are one change, noted once at the group. */
		change?: FieldChange | null;
		/** The project library's resistance entries, offered under "From the project library". */
		entries?: readonly ResistanceSpec[];
		/**
		 * Open the project library on an entry (its id), or on a new entry's form (null) whose entry
		 * is then used here. Without it the field offers no way to the library.
		 */
		onlibrary?: (entryId: string | null) => void;
		/** The library can be edited (the base case): offers "New entry…" and "Edit in the library". */
		editLibrary?: boolean;
		/** The library holds as many entries as a project may: "New entry…" is offered disabled. */
		libraryFull?: boolean;
	}

	let {
		value,
		defaultLabel,
		units,
		onchange,
		change = null,
		entries = [],
		onlibrary,
		editLibrary = true,
		libraryFull = false
	}: Props = $props();
	const noteId = $props.id();
	/** The group's note, which describes the kind and the number (they show none of their own). */
	const groupNote = $derived(hasChangeNote(change) ? `${noteId}-change` : undefined);
	const NEW_ENTRY = 'new-entry' as const;

	/** The entry the value refers to (undefined: none, or one the project does not have). */
	const ref = $derived(isResistanceRef(value) ? value : null);
	const entry = $derived(ref ? entries.find((e) => e.id === ref.id) : undefined);

	/**
	 * A kind picked while no value is stored: kept here, with the field empty, until a number
	 * is entered (the default applies meanwhile).
	 */
	let pending = $state<Kind | null>(null);
	const choice = $derived<Choice>(
		ref ? `entry:${ref.id}` : value && !isResistanceRef(value) ? value.kind : (pending ?? 'default')
	);
	const kind = $derived<Kind | null>(
		choice === 'K' || choice === 'Cv' || choice === 'Kv' ? choice : null
	);
	const coefficient = $derived(value && !isResistanceRef(value) ? value : null);

	const LIBRARY_GROUP = 'From the project library';
	const options = $derived.by((): SelectOption<Choice>[] => {
		const list: SelectOption<Choice>[] = [
			{ value: 'default', label: `Default: ${defaultLabel}` },
			{ value: 'K', label: COEFFICIENT_LABELS.K },
			{ value: 'Cv', label: COEFFICIENT_LABELS.Cv },
			{ value: 'Kv', label: COEFFICIENT_LABELS.Kv }
		];
		for (const e of entries) {
			list.push({
				value: `entry:${e.id}`,
				label: `${entryName(e)} (${entryValueText(e, units, 4)})`,
				group: LIBRARY_GROUP
			});
		}
		if (ref && !entry) {
			list.push({
				value: `entry:${ref.id}`,
				label: `${ref.id} (not in the project library)`,
				group: LIBRARY_GROUP
			});
		}
		if (onlibrary && editLibrary) {
			list.push({
				value: NEW_ENTRY,
				label: newOptionLabel('New entry…', libraryFull, 'resistance'),
				disabled: libraryFull,
				group: LIBRARY_GROUP
			});
		}
		return list;
	});

	/**
	 * K, Cv and Kv are different quantities: a stored number is never carried over to another
	 * kind (K = 5 and Cv = 5 are very different restrictions). Changing the kind clears the value,
	 * so the default applies until a value of the new kind is entered (undo restores the old one).
	 * An entry is used as it is; "New entry…" opens the library (the choice stays as it was).
	 */
	function choose(next: Choice) {
		if (next === choice) return;
		if (next === NEW_ENTRY) {
			if (!libraryFull) onlibrary?.(null);
			return;
		}
		if (next.startsWith('entry:')) {
			const id = next.slice('entry:'.length);
			if (onchange({ kind: 'library', id }) !== false) pending = null;
			return;
		}
		pending = next === 'default' ? null : (next as Kind);
		if (value) onchange(null);
	}

	function enter(v: number | null): boolean | void {
		if (v === null || kind === null) return false;
		const accepted = onchange({ kind, value: v });
		if (accepted !== false) pending = null;
		return accepted;
	}
</script>

<fieldset class="space-y-3 sm:col-span-2" data-resistance-field>
	<legend class="label mb-1">Resistance</legend>
	{#if change}<ChangeNote {change} id="{noteId}-change" />{/if}
	<SelectField
		label="Resistance given as"
		hideLabel
		value={choice}
		{options}
		{change}
		changeNote={false}
		describedby={groupNote}
		onchange={choose}
	/>
	{#if kind}
		<NumberField
			label={kind}
			value={coefficient?.value}
			category="dimensionless"
			{units}
			bounds={schemaBounds('FlowCoefficient', 'value')}
			hint={COEFFICIENT_HINTS[kind]}
			warning={coefficient ? null : `Enter ${kind} to use it; until then the default applies.`}
			{change}
			changeNote={false}
			describedby={groupNote}
			onchange={enter}
		/>
	{:else if ref}
		<div class="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700" data-library-entry>
			{#if entry}
				<p>
					<strong class="break-words">{entry.name}</strong>
					<span class="font-mono text-xs text-slate-600">{entry.id}</span>
				</p>
				<p>{entryValueText(entry, units)}</p>
				<p class="text-xs text-slate-600">
					{entry.kind === 'K'
						? "Moved to this valve's inlet bore D when solving, K = K₀ (D/d₀)⁴: the same head loss at a given flow."
						: "Converted to K at this valve's inlet bore when solving (ISA-75.01.01)."}
				</p>
				<p class="mt-1 text-xs break-words text-slate-600">Source: {entry.source}</p>
			{:else}
				<p class="flex items-start gap-1 text-amber-800">
					<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
					<span
						>Resistance entry {ref.id} is not in the project library: the calculation server reports it.
						Choose another resistance.</span
					>
				</p>
			{/if}
			{#if entry && onlibrary}
				<button
					type="button"
					class="btn btn-quiet -ml-3 px-3 text-blue-800"
					aria-label="{editLibrary ? 'Edit' : 'Show'} {entry.name} in the library"
					onclick={() => onlibrary(entry.id)}
				>
					{editLibrary ? 'Edit in the library' : 'Show in the library'}
				</button>
			{/if}
		</div>
	{/if}
</fieldset>
