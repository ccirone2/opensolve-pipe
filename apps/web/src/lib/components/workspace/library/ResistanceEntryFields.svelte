<!--
	A resistance entry's form (proposal project-library.md §6.1): its name, the kind (K, Cv or Kv,
	as ResistanceField offers them), the value as the source prints it, the bore a K is stated at
	(a K only: a Cv or Kv needs none), and its source. Changing the kind clears the value (K = 5 and
	Cv = 5 are very different restrictions) and a K's bore. `errors` as PipeSpecFields.
-->
<script lang="ts">
	import type { ResistanceSpec, UnitPreferences } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { COEFFICIENT_HINTS, COEFFICIENT_LABELS } from '$lib/utils/flow-coefficient';
	import { schemaBounds, stringLimits } from '$lib/utils/schema-bounds';
	import { withKind, type FieldErrors, type ResistanceDraft } from './drafts';

	interface Props {
		draft: ResistanceDraft;
		errors: FieldErrors;
		units: UnitPreferences;
	}

	let { draft = $bindable(), errors = $bindable(), units }: Props = $props();
	const KINDS = ['K', 'Cv', 'Kv'] as const;

	function set<K extends keyof ResistanceDraft>(key: K, value: ResistanceDraft[K] | null) {
		const next = { ...draft };
		if (value === null || value === undefined) delete next[key];
		else next[key] = value;
		draft = next;
	}

	function drop(...fields: string[]) {
		if (fields.some((f) => errors[f])) {
			const next = { ...errors };
			for (const f of fields) delete next[f];
			errors = next;
		}
	}
</script>

<div class="grid gap-4 sm:grid-cols-2">
	<div class="sm:col-span-2" data-field="name">
		<TextField
			label="Name"
			value={draft.name}
			maxlength={stringLimits('ResistanceSpec', 'name').maxLength}
			hint="How lists and results name it, e.g. 30 in butterfly valve, open."
			error={errors.name ?? null}
			oninput={() => drop('name')}
			onchange={(v) => set('name', v)}
		/>
	</div>
	<SelectField
		class="sm:col-span-2"
		label="Given as"
		value={draft.kind}
		options={KINDS.map((k) => ({ value: k, label: COEFFICIENT_LABELS[k] }))}
		hint="As the source gives it. Changing it clears the value."
		onchange={(kind: ResistanceSpec['kind']) => {
			draft = withKind(draft, kind);
			drop('value', 'referenceDiameter');
		}}
	/>
	<div data-field="value">
		<NumberField
			label={draft.kind}
			value={draft.value}
			category="dimensionless"
			{units}
			optional
			bounds={schemaBounds('ResistanceSpec', 'value')}
			hint={draft.kind === 'K'
				? 'Loss coefficient, on the velocity in a pipe of the bore below.'
				: COEFFICIENT_HINTS[draft.kind]}
			error={errors.value ?? null}
			oninput={() => drop('value')}
			onchange={(v) => set('value', v)}
		/>
	</div>
	{#if draft.kind === 'K'}
		<div data-field="referenceDiameter">
			<NumberField
				label="Stated at bore"
				value={draft.referenceDiameter}
				category="diameter"
				{units}
				optional
				bounds={schemaBounds('ResistanceSpec', 'referenceDiameter')}
				hint="The inner diameter the K is stated at. Each valve or fitting takes K × (D / this bore)⁴ on its own bore D: the same head loss at a given flow."
				error={errors.referenceDiameter ?? null}
				oninput={() => drop('referenceDiameter')}
				onchange={(v) => set('referenceDiameter', v)}
			/>
		</div>
	{:else}
		<p class="hint self-end">
			A {draft.kind} needs no bore: the calculation server converts it to K at each valve's or fitting's
			own bore (ISA-75.01.01).
		</p>
	{/if}
	<div class="sm:col-span-2" data-field="source">
		<TextField
			label="Source"
			multiline
			value={draft.source}
			maxlength={stringLimits('ResistanceSpec', 'source').maxLength}
			hint="Where the value comes from: the manufacturer's datasheet (its number and edition), a standard and its table, a test. Every result that uses the entry cites it."
			error={errors.source ?? null}
			oninput={() => drop('source')}
			onchange={(v) => set('source', v)}
		/>
	</div>
</div>
