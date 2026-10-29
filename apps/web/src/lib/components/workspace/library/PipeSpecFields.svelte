<!--
	A pipe spec's form (proposal project-library.md §6.1): its name, material (a library material or
	Custom), inner diameter, roughness, optional outer diameter and nominal size, and its source.
	On a library material a blank roughness is the material's cited one at this bore (Farshad &
	Rieke 2006), which the calculation server evaluates; it is shown here only where the pipe
	library holds a size of exactly this bore (the same value the server gives), and said otherwise.
	A custom spec needs its roughness. `errors` are the values still to enter when the form is
	saved, each at its field until the user types there (they go as the user types, never when a
	field stores its value on losing focus, the press of Save: nothing moves under the pointer).
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { CUSTOM_MATERIAL_ID } from '$lib/utils/piping';
	import { schemaBounds, stringLimits } from '$lib/utils/schema-bounds';
	import { formatValue } from '$lib/utils/units';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import type { FieldErrors, PipeSpecDraft } from './drafts';

	interface Props {
		draft: PipeSpecDraft;
		errors: FieldErrors;
		units: UnitPreferences;
	}

	let { draft = $bindable(), errors = $bindable(), units }: Props = $props();
	const ws = useWorkspace();
	const lib = ws.library;

	const custom = $derived(draft.materialId === CUSTOM_MATERIAL_ID);
	const material = $derived(custom ? undefined : lib.material(draft.materialId));
	const options = $derived([
		...lib.materials.map((m) => ({ value: m.id, label: m.name })),
		...(!custom && !material
			? [
					{
						value: draft.materialId,
						label:
							lib.libraryStatus === 'ready'
								? `${draft.materialId} (not in the library)`
								: `${draft.materialId} (library unavailable)`
					}
				]
			: []),
		{ value: CUSTOM_MATERIAL_ID, label: 'Custom (enter the roughness)' }
	]);
	/** NPS is a designation in inches whatever the display units. */
	const inches = $derived({ ...units, diameter: 'in' as const });

	/**
	 * The material's roughness at the spec's bore, where the pipe library holds a size of exactly
	 * that bore: the library's per-size roughness is the same correlation at the same bore.
	 */
	const libraryRoughness = $derived.by(() => {
		if (!material || draft.innerDiameter == null) return undefined;
		for (const schedule of material.schedules) {
			const size = schedule.sizes.find((s) => s.innerDiameter === draft.innerDiameter);
			if (size) return { roughness: size.roughness, nps: size.nps, schedule: schedule.id };
		}
		return undefined;
	});
	const roughnessHint = $derived(
		custom
			? 'Absolute roughness of the pipe wall, from your source.'
			: draft.roughness != null
				? "Your value, in place of the material's cited roughness: give its origin in the source."
				: libraryRoughness
					? `Blank: the material's cited roughness at this bore, ${formatValue(libraryRoughness.roughness, 'diameter', units, 4)} (as the library's NPS ${libraryRoughness.nps} schedule ${libraryRoughness.schedule}; ${material?.roughnessSource ?? 'Farshad & Rieke 2006'}).`
					: "Blank: the material's cited roughness (Farshad & Rieke 2006) at this inner diameter, which the calculation server evaluates when solving; the trace shows it."
	);

	function set<K extends keyof PipeSpecDraft>(key: K, value: PipeSpecDraft[K] | null) {
		const next = { ...draft };
		if (value === null || value === undefined) delete next[key];
		else next[key] = value;
		draft = next;
	}

	function drop(field: string) {
		if (errors[field]) {
			const next = { ...errors };
			delete next[field];
			errors = next;
		}
	}
</script>

<div class="grid gap-4 sm:grid-cols-2">
	<div class="sm:col-span-2" data-field="name">
		<TextField
			label="Name"
			value={draft.name}
			maxlength={stringLimits('PipeSpec', 'name').maxLength}
			hint="How lists and results name it, e.g. NPS 60 STD carbon steel."
			error={errors.name ?? null}
			oninput={() => drop('name')}
			onchange={(v) => set('name', v)}
		/>
	</div>
	<SelectField
		class="sm:col-span-2"
		label="Material"
		value={draft.materialId}
		{options}
		hint={custom
			? 'A custom spec states its roughness.'
			: "A library material keeps its cited roughness unless you enter one; the spec's inner diameter replaces the library's sizes."}
		onchange={(id) => {
			set('materialId', id);
			if (id !== CUSTOM_MATERIAL_ID) drop('roughness');
		}}
	/>
	<div data-field="innerDiameter">
		<NumberField
			label="Inner diameter"
			value={draft.innerDiameter}
			category="diameter"
			{units}
			optional
			bounds={schemaBounds('PipeSpec', 'innerDiameter')}
			hint="The bore of every pipe that uses the spec."
			error={errors.innerDiameter ?? null}
			oninput={() => drop('innerDiameter')}
			onchange={(v) => set('innerDiameter', v)}
		/>
	</div>
	<div data-field="roughness">
		<NumberField
			label="Roughness"
			value={draft.roughness}
			category="diameter"
			{units}
			optional
			placeholder={custom ? '' : "Material's at this bore"}
			bounds={schemaBounds('PipeSpec', 'roughness')}
			hint={roughnessHint}
			error={errors.roughness ?? null}
			oninput={() => drop('roughness')}
			onchange={(v) => set('roughness', v)}
		/>
	</div>
	<NumberField
		label="Outer diameter"
		value={draft.outerDiameter}
		category="diameter"
		{units}
		optional
		placeholder="Optional"
		bounds={schemaBounds('PipeSpec', 'outerDiameter')}
		hint="For display only; above the inner diameter."
		onchange={(v) => set('outerDiameter', v)}
	/>
	<NumberField
		label="Nominal size (NPS)"
		value={draft.nominalSize}
		category="diameter"
		units={inches}
		optional
		placeholder="Optional"
		bounds={schemaBounds('PipeSpec', 'nominalSize')}
		hint="The designation in inches, for display and the size of ports on these pipes."
		onchange={(v) => set('nominalSize', v)}
	/>
	<div class="sm:col-span-2" data-field="source">
		<TextField
			label="Source"
			multiline
			value={draft.source}
			maxlength={stringLimits('PipeSpec', 'source').maxLength}
			hint="Where the values come from: a standard and its table, a datasheet, a measurement. Every result that uses the spec cites it."
			error={errors.source ?? null}
			oninput={() => drop('source')}
			onchange={(v) => set('source', v)}
		/>
	</div>
</div>
