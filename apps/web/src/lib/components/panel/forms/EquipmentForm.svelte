<!--
	An equipment item (proposal equipment-pressure-drop.md §6.2): its rating, as the datasheet
	gives it (EquipmentRatingFields), then the hint. A kind picked whose values are not all entered
	yet is pending (ResistanceField's rule: no number is carried to another kind); with no default
	to fall back on, the stored rating applies until the new kind's values are all entered, and the
	warning says so. In a scenario the rating is a scenario value (D15): a value of the base's kind
	is a change of that value, noted at its field; a change of kind is one whole-rating change,
	noted once at the group, which later edits of the rating update (utils/scenarios.ts
	nextOverrides).
-->
<script lang="ts">
	import type { Equipment } from '$lib/api/types';
	import {
		completeRating,
		ratingDraft,
		type RatingDraft,
		type RatingField,
		type RatingKind
	} from '$lib/utils/factory';
	import { fieldLabelFor } from '$lib/utils/scenarios';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import EquipmentRatingFields from '../EquipmentRatingFields.svelte';

	let { component }: { component: Equipment } = $props();
	const ws = useWorkspace();

	/** A kind picked whose values are not all entered yet (page state; the form is per item). */
	let pending = $state<RatingDraft | null>(null);
	const open = $derived(pending && pending.kind !== component.rating.kind ? pending : null);
	const shown = $derived<RatingDraft>(open ?? ratingDraft(component.rating));

	const RATING_WORDS: Readonly<Record<RatingKind, string>> = {
		point: 'the rated point',
		Cv: 'the Cv',
		Kv: 'the Kv'
	};
	const warning = $derived(
		open
			? open.kind === 'point'
				? `Enter the rated pressure drop, rated flow and rated fluid density to use them; until then ${RATING_WORDS[component.rating.kind]} applies.`
				: `Enter the ${open.kind} to use it; until then ${RATING_WORDS[component.rating.kind]} applies.`
			: null
	);

	function store(rating: Equipment['rating'], label: string): boolean {
		return ws.editComponent<Equipment>(component.id, label, (c) => {
			c.rating = rating;
		});
	}

	function onkind(kind: RatingKind) {
		pending = kind === component.rating.kind ? null : { kind };
	}

	function onvalue(field: RatingField, value: number): boolean | void {
		if (open) {
			const next = { ...open, [field]: value };
			const complete = completeRating(next);
			if (!complete) {
				pending = next;
				return;
			}
			const stored = store(complete, 'change rating');
			if (stored) pending = null;
			return stored;
		}
		const next = completeRating({ ...ratingDraft(component.rating), [field]: value });
		if (!next) return false;
		const label = fieldLabelFor(component, `rating.${field}`);
		return store(next, `change ${field === 'value' ? label : label.toLowerCase()}`);
	}
</script>

<EquipmentRatingFields
	rating={shown}
	units={ws.units}
	{warning}
	{onkind}
	{onvalue}
	wholeChange={ws.componentChange(component.id, 'rating')}
	partChange={(field) => ws.componentChange(component.id, `rating.${field}`)}
/>
<p class="hint sm:col-span-2">
	A heat exchanger, coil, strainer, filter or other element given by its datasheet: a pressure drop
	at a rated flow, or a Cv or Kv. The loss scales with the square of the flow and with density: ΔP =
	ΔP<sub>rated</sub> × (Q ÷ Q<sub>rated</sub>)² × ρ ÷ ρ<sub>rated</sub>; a Cv or Kv is a rating on
	water. Viscosity is not corrected; the scaling holds where the loss goes as the flow squared, as
	in turbulent flow. Laminar flow in a connected pipe, and flow from outlet to inlet, are flagged.
	For a dirty strainer or a fouled exchanger, make a scenario with its own rating: a higher rated
	pressure drop, or a lower Cv or Kv.
</p>
