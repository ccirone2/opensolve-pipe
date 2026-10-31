<!--
	A plain field drawn from its registry entry (utils/field-registry.ts, proposal build-density.md
	§5): a number in its unit category, or a choice of the values the schema allows. Its bounds
	and choices are read from the schema, and it is a scenario value exactly when the scenario
	allow-list (x-override-fields) names it, so a field added to the model and to the registry
	needs nothing else here.
-->
<script lang="ts">
	import type { Component } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SegmentedField from '$lib/components/ui/SegmentedField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { labelOf, valueAt, type FieldEntry } from '$lib/utils/field-registry';
	import { inSentence } from '$lib/utils/labels';
	import { componentOverrideFields, schemaChoices } from '$lib/utils/model-rules';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	let {
		schema,
		path,
		entry,
		component
	}: { schema: string; path: string; entry: FieldEntry; component: Component } = $props();
	const ws = useWorkspace();

	const label = $derived(labelOf(entry, component));
	const edit = $derived(entry.edit ?? `change ${inSentence(label)}`);
	const change = $derived(
		path in componentOverrideFields(component) ? ws.componentChange(component.id, path) : null
	);
	const value = $derived(valueAt(component, path));

	function store(next: unknown): boolean {
		return ws.editComponent(component.id, edit, (c) => {
			(c as unknown as Record<string, unknown>)[path] = next;
		});
	}
</script>

{#if entry.input?.kind === 'number'}
	{@const optional = entry.input.optional ?? false}
	<NumberField
		{label}
		value={typeof value === 'number' ? value : null}
		category={entry.input.category}
		gauge={entry.input.gauge}
		{optional}
		units={ws.units}
		bounds={schemaBounds(schema, path)}
		help={entry.help}
		{change}
		onchange={(v) => (v === null && !optional ? false : store(v))}
	/>
{:else if entry.input?.kind === 'choice' && schemaChoices(schema, path).length === 2}
	<!-- Two values: one tap, as segments (build-density.md §11). -->
	{@const labels = entry.input.labels}
	<SegmentedField
		{label}
		value={String(value)}
		options={schemaChoices(schema, path).map((v) => ({ value: v, label: labels[v] ?? v }))}
		help={entry.help}
		{change}
		onchange={(v) => store(v)}
	/>
{:else if entry.input?.kind === 'choice'}
	{@const labels = entry.input.labels}
	<SelectField
		{label}
		value={String(value)}
		options={schemaChoices(schema, path).map((v) => ({ value: v, label: labels[v] ?? v }))}
		help={entry.help}
		{change}
		onchange={(v) => store(v)}
	/>
{/if}
