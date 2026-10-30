<!--
	A component's fields laid out from the registry (utils/field-registry.ts, proposal
	build-density.md §5): its core fields in one section per facet (Operation, Rating, ...), in
	registry order, each a label/value row; then its other fields in one "More" disclosure whose
	summary names each of them, with "default" for those at their default (D10), so nothing it
	holds is unknown while it is closed. More opens itself while it holds a value the user set, a
	scenario change or a base-case note that a scenario sets its own value (D15), or what the form
	reports as pending (a draft, a warning, an error). The ports follow, in their own disclosure.

	A plain field (its entry declares `input`) is drawn here; any other is drawn by the type's form
	through `field`, which gets its path and label.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { Component } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { fieldEntry, isSet, labelOf, sectionsOf, valueAt } from '$lib/utils/field-registry';
	import { componentOverrideFields } from '$lib/utils/model-rules';
	import { componentSchema } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import PortsEditor from './PortsEditor.svelte';
	import RegistryField from './RegistryField.svelte';

	interface Props {
		component: Component;
		/** Draws a field the registry does not draw itself (no `input`). */
		field?: Snippet<[path: string, label: string]>;
		/** Paths the form reports as pending (a draft, a warning, an error): they open More. */
		pending?: readonly string[];
		/** Text about the model, after the fields: in its own closed disclosure. */
		about?: Snippet;
	}

	let { component, field, pending = [], about }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const schema = $derived(componentSchema(component));
	const core = $derived(sectionsOf(schema, 'core'));
	const more = $derived(
		sectionsOf(schema, 'more')
			.map((s) => ({ ...s, paths: s.paths.filter((p) => p !== 'ports') }))
			.filter((s) => s.paths.length)
	);
	const morePaths = $derived(more.flatMap((s) => s.paths));
	const overrides = $derived(componentOverrideFields(component));

	/** Whether a field's scenario value shows a note: changed in this case, or set by a scenario. */
	function noted(path: string): boolean {
		if (!(path in overrides)) return false;
		const change = ws.componentChange(component.id, path);
		return change.inScenario ? change.changed : change.setBy.length > 0;
	}

	const setPaths = $derived(morePaths.filter((p) => isSet(schema, p, valueAt(component, p))));
	const notedPaths = $derived(morePaths.filter(noted));
	const pendingPaths = $derived(morePaths.filter((p) => pending.includes(p)));
	/**
	 * Opens itself while it holds something the user should see, and never closes itself (a value
	 * set back to its default while editing leaves it open); the user may close it.
	 */
	const attention = $derived(setPaths.length + notedPaths.length + pendingPaths.length > 0);
	let open = $state(false);
	$effect.pre(() => {
		if (attention) open = true;
	});

	const label = (path: string) => {
		const entry = fieldEntry(schema, path);
		return entry ? labelOf(entry, component) : path;
	};
	/** "Resistance (default), Elevation": what More holds, each at its default said so. */
	const contents = $derived(
		morePaths.map((p) => (setPaths.includes(p) ? label(p) : `${label(p)} (default)`)).join(', ')
	);
	const status = $derived(
		[
			setPaths.length && `${setPaths.length} set`,
			notedPaths.length &&
				(ws.inScenario
					? `${notedPaths.length} changed in this case`
					: `${notedPaths.length} set by a scenario`),
			pendingPaths.length && `${pendingPaths.length} to finish`
		]
			.filter(Boolean)
			.join(', ')
	);
</script>

{#snippet one(path: string)}
	{@const entry = fieldEntry(schema, path)}
	{#if entry?.input}
		<RegistryField {schema} {path} {entry} {component} />
	{:else if entry}
		{@render field?.(path, labelOf(entry, component))}
	{/if}
{/snippet}

<div class="space-y-4">
	{#each core as section (section.facet)}
		<section class="space-y-2" aria-labelledby="{id}-{section.facet}">
			<h3 id="{id}-{section.facet}" class="section-title">{section.title}</h3>
			<div class="fields fields-pairs">
				{#each section.paths as path (path)}{@render one(path)}{/each}
			</div>
		</section>
	{/each}

	{#if morePaths.length}
		<details class="group rounded-md border border-slate-200 px-2" bind:open>
			<summary class="more-summary -mx-2 px-2">
				<Icon
					name="right"
					class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
				/>
				<span class="min-w-0 flex-1">
					More<span class="font-normal text-slate-600">: {contents}</span>
				</span>
				{#if status}
					<span class="shrink-0 rounded-full bg-blue-50 px-2 text-xs text-blue-900">{status}</span>
				{/if}
			</summary>
			<div class="space-y-3 pt-1 pb-3">
				{#each more as section (section.facet)}
					<section class="space-y-2" aria-labelledby="{id}-more-{section.facet}">
						<h4 id="{id}-more-{section.facet}" class="section-title">{section.title}</h4>
						<div class="fields fields-pairs">
							{#each section.paths as path (path)}{@render one(path)}{/each}
						</div>
					</section>
				{/each}
			</div>
		</details>
	{/if}

	<PortsEditor {component} />

	{#if about}
		<details class="group">
			<summary class="more-summary">
				<Icon
					name="right"
					class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
				/>
				About this model
			</summary>
			<div class="pb-2 text-sm text-slate-700">{@render about()}</div>
		</details>
	{/if}
</div>
