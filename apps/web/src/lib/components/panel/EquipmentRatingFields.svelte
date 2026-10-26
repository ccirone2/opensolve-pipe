<!--
	An equipment item's rating (proposal equipment-pressure-drop.md §6.1–§6.2), as the datasheet
	gives it: Rated by (a pressure drop at a flow, a Cv or a Kv), then that kind's values. A rated
	point's pressure drop is a difference (never marked gauge), its flow and the density of the
	fluid it is rated for, each in its display unit; two buttons fill the density from a fluid's
	properties (Water at 15 °C, This case's fluid: the exact number the API gives, entered as the
	user's value). A Cv or Kv is stored as entered (the valves' hints, utils/flow-coefficient.ts).
	Nothing has a default (decision 3).

	Used by the item's form (the stored rating, or a kind picked whose values are not all entered
	yet: `warning` says which rating applies meanwhile, and describes each field and the choice)
	and where the item is added, before it exists (`errors`: the values still to enter, each shown
	at its field until the user types there). Nothing here changes size when a field stores its
	value on losing focus, which a press on a button below does (an error, and a density button's
	note, go as the user types), so that button never moves under the pointer. In a scenario the
	form gives `wholeChange` (a change of kind: one change, noted once at the group) and
	`partChange` (a value of the base's kind: noted at its field).
-->
<script lang="ts">
	import type { FluidDefinition, UnitPreferences } from '$lib/api/types';
	import ChangeNote from '$lib/components/ui/ChangeNote.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import {
		hasChangeNote,
		isLocked,
		useFieldMode,
		type FieldChange
	} from '$lib/components/ui/field-mode';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import {
		RATING_FIELDS,
		RATING_KINDS,
		type MissingEntry,
		type RatingDraft,
		type RatingField,
		type RatingKind
	} from '$lib/utils/factory';
	import { COEFFICIENT_HINTS, COEFFICIENT_LABELS } from '$lib/utils/flow-coefficient';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { formatValue, type UnitCategory } from '$lib/utils/units';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	interface Props {
		/** The rating shown: the stored one, or a draft (the values of its kind entered so far). */
		rating: RatingDraft;
		units: UnitPreferences;
		/** Values still to enter where the item is added, each shown at its field. */
		errors?: readonly MissingEntry[];
		/** Another kind was picked: no value is carried to it. */
		onkind: (kind: RatingKind) => void;
		/** A value entered (SI; a Cv or Kv as entered). Return false when it was not stored. */
		onvalue: (field: RatingField, value: number) => boolean | void;
		/** Each edit of a field's text, before it is stored (to drop that field's error). */
		oninput?: (field: RatingField) => void;
		/** A note under the fields, e.g. which rating applies until a new kind's values are in. */
		warning?: string | null;
		/** A scenario's whole-rating change: noted once at the group; makes the choice editable. */
		wholeChange?: FieldChange | null;
		/** A scenario's change of one value of the base's kind (null: the whole change applies). */
		partChange?: ((field: RatingField) => FieldChange | null) | null;
	}

	let {
		rating,
		units,
		errors = [],
		onkind,
		onvalue,
		oninput,
		warning = null,
		wholeChange = null,
		partChange = null
	}: Props = $props();

	const ws = useWorkspace();
	const mode = useFieldMode();
	const noteId = $props.id();
	/** The group's note (a whole-rating change), which describes every field of the rating. */
	const groupNote = $derived(hasChangeNote(wholeChange) ? `${noteId}-change` : undefined);
	/** The warning (which rating applies until a kind picked is entered): it describes them all. */
	const warningId = $derived(warning ? `${noteId}-warning` : undefined);
	const described = (...ids: (string | false | undefined)[]) =>
		ids.filter(Boolean).join(' ') || undefined;

	const KIND_OPTIONS: Readonly<Record<RatingKind, string>> = {
		point: 'Pressure drop at a flow',
		Cv: COEFFICIENT_LABELS.Cv,
		Kv: COEFFICIENT_LABELS.Kv
	};

	interface FieldSpec {
		label: string;
		category: UnitCategory;
		hint: string;
		schema: string;
	}

	const POINT: Readonly<Record<Exclude<RatingField, 'value'>, FieldSpec>> = {
		pressureLoss: {
			label: 'Rated pressure drop',
			category: 'pressure',
			// Decision 4 (proposal equipment-pressure-drop.md; the schema's description): a static
			// drop S_r is entered as S_r − ρ_r g (z_out − z_in) − ρ_r (v_out² − v_in²)/2.
			hint: 'From the datasheet: the pressure lost from inlet to outlet at the rated flow, without any static head. For a static drop measured between nozzles at different heights or bores, subtract ρ_r g × (outlet − inlet height) and ρ_r (v_out² − v_in²)/2, with ρ_r the rated fluid density and v the nozzle velocities at the rated flow; keep the ports at their real elevations.',
			schema: 'RatedPoint'
		},
		flow: {
			label: 'Rated flow',
			category: 'flow',
			hint: 'The flow at which the datasheet gives that drop.',
			schema: 'RatedPoint'
		},
		density: {
			label: 'Rated fluid density',
			category: 'density',
			hint: 'The density of the fluid the datasheet is rated with. Strainer and filter charts are usually for water; exchanger and coil datasheets state their fluid.',
			schema: 'RatedPoint'
		}
	};

	function spec(field: RatingField): FieldSpec {
		if (field !== 'value') return POINT[field];
		const kind = rating.kind === 'point' ? 'Cv' : rating.kind;
		return {
			label: kind,
			category: 'dimensionless',
			hint: COEFFICIENT_HINTS[kind],
			schema: 'RatedFlowCoefficient'
		};
	}

	const errorOf = (field: RatingField) =>
		errors.find((e) => e.field === `rating.${field}`)?.message ?? null;

	/** A field's scenario state: the whole change while it exists (noted at the group), else its own. */
	const changeOf = (field: RatingField): FieldChange | null =>
		wholeChange && (wholeChange.changed || !partChange)
			? wholeChange
			: (partChange?.(field) ?? wholeChange);
	const groupNoted = (field: RatingField) => changeOf(field) === wholeChange;

	/** The density buttons: which fluid, and what the last one entered (page state). */
	type Source = 'water' | 'case';
	const WATER_15C: FluidDefinition = { kind: 'builtin', fluidId: 'water', temperature: 288.15 };
	let busy = $state<Source | null>(null);
	let densityNote = $state<string | null>(null);
	let densityError = $state<string | null>(null);
	const densityLocked = $derived(isLocked(mode, changeOf('density'), false));

	/**
	 * Enter the density of a fluid: built-in water at 15 °C, or the case's fluid as it is now (its
	 * properties from the API, D10's POST with the fluid in the body). The exact double is entered
	 * as the user's value (user data), never a rounded display.
	 */
	async function fillDensity(source: Source) {
		if (busy !== null) return;
		const fluid = source === 'water' ? WATER_15C : ws.project.fluid;
		const what = source === 'water' ? 'water at 15 °C' : "this case's fluid";
		busy = source;
		densityError = null;
		densityNote = null;
		try {
			const properties = await ws.library.fluidProperties(fluid);
			if (onvalue('density', properties.density) !== false) {
				densityNote = `Entered the density of ${what}, ${formatValue(properties.density, 'density', units, 6)}, as your value (it does not follow later fluid changes).`;
			}
		} catch (error) {
			densityError = `Could not get the density of ${what}: ${error instanceof Error ? error.message : 'no answer'}. Enter it instead.`;
		} finally {
			busy = null;
		}
	}
</script>

<fieldset class="grid gap-4 sm:col-span-2 sm:grid-cols-2">
	<legend class="label mb-1 sm:col-span-2">Rating</legend>
	{#if wholeChange && hasChangeNote(wholeChange)}
		<div class="sm:col-span-2"><ChangeNote change={wholeChange} id="{noteId}-change" /></div>
	{/if}
	<SelectField
		class="sm:col-span-2"
		label="Rated by"
		value={rating.kind}
		options={RATING_KINDS.map((k) => ({ value: k, label: KIND_OPTIONS[k] }))}
		hint="How the datasheet gives the rating."
		change={wholeChange}
		changeNote={false}
		describedby={described(groupNote, warningId)}
		onchange={(kind) => {
			densityNote = null;
			densityError = null;
			onkind(kind);
		}}
	/>
	{#each RATING_FIELDS[rating.kind] as field (`${rating.kind}:${field}`)}
		{@const s = spec(field)}
		<!-- The density's note is hidden while empty: a gap only between what is shown. -->
		<div class={['min-w-0', field === 'density' && 'flex flex-col gap-2']}>
			<NumberField
				label={s.label}
				value={rating[field] ?? null}
				category={s.category}
				{units}
				bounds={schemaBounds(s.schema, field)}
				hint={s.hint}
				error={field === 'density' ? (densityError ?? errorOf(field)) : errorOf(field)}
				change={changeOf(field)}
				changeNote={!groupNoted(field)}
				describedby={described(groupNoted(field) && groupNote, warningId)}
				oninput={() => {
					// A density typed over a button's: its note no longer describes it. It goes now,
					// never when the field stores the value on losing focus (the press of Add).
					if (field === 'density') {
						densityError = null;
						densityNote = null;
					}
					oninput?.(field);
				}}
				onchange={(v) => (v === null ? false : onvalue(field, v))}
			/>
			{#if field === 'density'}
				<div
					class="flex flex-wrap gap-2"
					role="group"
					aria-label="Rated fluid density from a fluid"
				>
					<button
						type="button"
						class="btn"
						disabled={densityLocked}
						aria-disabled={busy !== null}
						onclick={() => fillDensity('water')}
					>
						{busy === 'water' ? 'Getting…' : 'Water at 15 °C'}
					</button>
					<button
						type="button"
						class="btn"
						disabled={densityLocked}
						aria-disabled={busy !== null}
						onclick={() => fillDensity('case')}
					>
						{busy === 'case' ? 'Getting…' : "This case's fluid"}
					</button>
				</div>
				<!-- A live region present before its text (the convention: PumpForm, Workspace). -->
				<p class="hint empty:hidden" role="status">{densityNote ?? ''}</p>
			{/if}
		</div>
	{/each}
	{#if warning}
		<p id={warningId} class="flex items-start gap-1 text-sm text-amber-800 sm:col-span-2">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span>{warning}</span>
		</p>
	{/if}
</fieldset>
