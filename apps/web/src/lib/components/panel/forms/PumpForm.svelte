<script lang="ts">
	import type { Pump } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { CURVE_PREFIX, newId } from '$lib/utils/factory';
	import { PUMP_STATUS_LABELS } from '$lib/utils/labels';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import PumpCurveEditor from './PumpCurveEditor.svelte';

	let { component }: { component: Pump } = $props();
	const ws = useWorkspace();

	/** A new curve being entered for this pump (not in the library until it has 3 points). */
	let creating = $state<string | null>(null);

	const library = $derived(ws.project.pumpLibrary);
	const curve = $derived(library.find((c) => c.id === component.curveId));
	const users = $derived(
		ws.project.components.filter((c) => c.type === 'pump' && c.curveId === component.curveId).length
	);
	const NEW = '__new__';
	const options = $derived([
		...library.map((c) => ({ value: c.id, label: `${c.name} (${c.id})` })),
		...(curve
			? []
			: [{ value: component.curveId, label: `${component.curveId} (not defined yet)` }]),
		{ value: NEW, label: 'New curve…' }
	]);
</script>

<SelectField
	label="Status"
	value={component.status}
	options={[
		{ value: 'on', label: PUMP_STATUS_LABELS.on },
		{ value: 'off', label: PUMP_STATUS_LABELS.off }
	]}
	onchange={(v) =>
		ws.editComponent<Pump>(component.id, 'change pump status', (c) => {
			c.status = v;
		})}
/>
<NumberField
	label="Speed"
	value={component.speed}
	category="fraction"
	units={ws.units}
	bounds={schemaBounds('Pump', 'speed')}
	hint="Fixed speed, as a percentage of the curve's rated speed (affinity laws)."
	onchange={(v) =>
		v !== null &&
		ws.editComponent<Pump>(component.id, 'change pump speed', (c) => {
			c.speed = v;
		})}
/>

<section class="space-y-3 border-t border-slate-200 pt-4 sm:col-span-2" aria-label="Pump curve">
	<SelectField
		label="Pump curve"
		value={creating ?? component.curveId}
		options={creating ? [...options, { value: creating, label: `${creating} (new)` }] : options}
		hint={curve && users > 1
			? `This curve is shared by ${users} pumps; changes apply to all of them.`
			: !curve && !creating && library.length
				? 'Pick a curve from the project library, or enter this pump’s own curve below.'
				: undefined}
		onchange={(v) => {
			if (v === NEW) {
				creating = newId(ws.project, CURVE_PREFIX);
			} else {
				creating = null;
				ws.editComponent<Pump>(component.id, 'change pump curve', (c) => {
					c.curveId = v;
				});
			}
		}}
	/>
	{#key creating ?? component.curveId}
		<PumpCurveEditor
			pump={component}
			curve={creating ? undefined : curve}
			curveId={creating ?? component.curveId}
			oncreated={() => (creating = null)}
		/>
	{/key}
</section>
