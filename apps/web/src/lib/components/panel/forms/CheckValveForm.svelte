<script lang="ts">
	import type { CheckValve } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { KIND_LABELS } from '$lib/utils/factory';
	import { CHECK_STATUS_LABELS } from '$lib/utils/labels';
	import { withOptional } from '$lib/utils/piping';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import ResistanceField from '../ResistanceField.svelte';

	let { component }: { component: CheckValve } = $props();
	const ws = useWorkspace();
	const STATUSES = ['active', 'locked_open', 'locked_closed'] as const;
</script>

<SelectField
	label="Valve type"
	value={component.valveType}
	options={[
		{ value: 'check', label: KIND_LABELS.check },
		{ value: 'stop_check', label: KIND_LABELS.stop_check }
	]}
	onchange={(v) =>
		ws.editComponent<CheckValve>(component.id, 'change valve type', (c) => {
			c.valveType = v;
		})}
/>
<SelectField
	label="Status"
	value={component.status}
	options={STATUSES.map((s) => ({ value: s, label: CHECK_STATUS_LABELS[s] }))}
	onchange={(v) =>
		ws.editComponent<CheckValve>(component.id, 'change valve status', (c) => {
			c.status = v;
		})}
/>
<NumberField
	label="Cracking pressure"
	value={component.crackingPressure}
	category="pressure"
	units={ws.units}
	bounds={schemaBounds('CheckValve', 'crackingPressure')}
	hint="Pressure difference across the valve (inlet minus outlet) that opens it; 0 opens on any forward flow."
	onchange={(v) =>
		v !== null &&
		ws.editComponent<CheckValve>(component.id, 'change cracking pressure', (c) => {
			c.crackingPressure = v;
		})}
/>
<ResistanceField
	value={component.resistance}
	units={ws.units}
	defaultLabel="the solver's cited loss for this valve type (shown in the results)"
	onchange={(r) =>
		ws.editComponent<CheckValve>(component.id, 'change valve resistance', (c) =>
			withOptional(c, 'resistance', r)
		)}
/>
