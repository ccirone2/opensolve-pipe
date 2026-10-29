<script lang="ts">
	import type { IsolationValve } from '$lib/api/types';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { KIND_LABELS } from '$lib/utils/factory';
	import { ISOLATION_STATUS_LABELS } from '$lib/utils/labels';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import ValveResistanceField from '../ValveResistanceField.svelte';

	let { component }: { component: IsolationValve } = $props();
	const ws = useWorkspace();
	const TYPES = ['gate', 'ball', 'butterfly', 'globe'] as const;
</script>

<SelectField
	label="Valve type"
	value={component.valveType}
	options={TYPES.map((t) => ({ value: t, label: KIND_LABELS[t] }))}
	onchange={(v) =>
		ws.editComponent<IsolationValve>(component.id, 'change valve type', (c) => {
			c.valveType = v;
		})}
/>
<SelectField
	label="Status"
	value={component.status}
	options={[
		{ value: 'active', label: ISOLATION_STATUS_LABELS.active },
		{ value: 'isolated', label: ISOLATION_STATUS_LABELS.isolated }
	]}
	change={ws.componentChange(component.id, 'status')}
	onchange={(v) =>
		ws.editComponent<IsolationValve>(component.id, 'change valve status', (c) => {
			c.status = v;
		})}
/>
<ValveResistanceField
	{component}
	defaultLabel="Crane TP-410 K, full bore and fully open, at the connected size"
/>
