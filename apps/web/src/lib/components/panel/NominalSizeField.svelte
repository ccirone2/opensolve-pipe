<!--
	Nominal pipe size (stored in m: NPS in inches × 0.0254). With library sizes it is a list of
	NPS designations; without them (library unavailable) the NPS is typed in inches.
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { npsLabel, sameSize } from '$lib/utils/labels';
	import { schemaBounds } from '$lib/utils/schema-bounds';

	interface Props {
		label: string;
		value: number | null | undefined;
		sizes: readonly { nominalSize: number; nps: string }[];
		units: UnitPreferences;
		hint?: string;
		onchange: (nominalSize: number) => boolean | void;
	}

	let { label, value, sizes, units, hint, onchange }: Props = $props();

	const current = $derived(
		value == null ? undefined : sizes.find((s) => sameSize(s.nominalSize, value))
	);
	const options = $derived([
		...(value != null && !current
			? [{ value: String(value), label: `${npsLabel(value)} (not in the library list)` }]
			: []),
		...sizes.map((s) => ({ value: String(s.nominalSize), label: `NPS ${s.nps}` }))
	]);
	const selected = $derived(current ? String(current.nominalSize) : String(value ?? ''));
	// NPS is a designation in inches whatever the display units.
	const inches = $derived({ ...units, diameter: 'in' as const });
</script>

{#if sizes.length}
	<SelectField
		{label}
		value={selected}
		{options}
		{hint}
		onchange={(v) => {
			const size = Number(v);
			if (Number.isFinite(size) && size > 0) onchange(size);
		}}
	/>
{:else}
	<NumberField
		label="{label} (NPS)"
		{value}
		category="diameter"
		units={inches}
		bounds={schemaBounds('PipeDefinition', 'nominalSize')}
		hint={hint ?? 'Nominal pipe size designation in inches (the size list needs the pipe library).'}
		onchange={(v) => v !== null && onchange(v)}
	/>
{/if}
