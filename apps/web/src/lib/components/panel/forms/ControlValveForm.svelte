<script lang="ts">
	import type { ControlValve } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { KIND_LABELS } from '$lib/utils/factory';
	import { CONTROL_STATUS_LABELS } from '$lib/utils/labels';
	import { withOptional } from '$lib/utils/piping';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import ResistanceField from '../ResistanceField.svelte';

	let { component }: { component: ControlValve } = $props();
	const ws = useWorkspace();
	const TYPES = ['prv', 'psv', 'fcv'] as const;
	const STATUSES = ['active', 'failed_open', 'failed_closed'] as const;

	const isFlow = $derived(component.valveType === 'fcv');
	/** FCV setpoints are flows (the API accepts 0–100 m³/s); PRV/PSV setpoints are gauge pressures. */
	const setpointBounds = $derived(
		isFlow ? { minimum: 0, maximum: 100 } : schemaBounds('ControlValve', 'setpoint')
	);

	/** A new control valve's setpoint is 0, for the user to set: say what 0 means until then. */
	const setpointWarning = $derived(
		component.setpoint !== 0 || component.status !== 'active'
			? null
			: isFlow
				? 'Set the flow to hold: at 0 the valve shuts the line.'
				: `Set the pressure to hold: 0 is ${component.valveType === 'prv' ? 'an outlet' : 'an inlet'} at atmospheric pressure.`
	);

	function changeType(next: ControlValve['valveType']) {
		const flowBefore = component.valveType === 'fcv';
		const flowAfter = next === 'fcv';
		ws.editComponent<ControlValve>(component.id, 'change valve type', (c) => {
			c.valveType = next;
			// A pressure setpoint means nothing as a flow (and vice versa): start from 0 to re-enter.
			if (flowBefore !== flowAfter) c.setpoint = 0;
		});
	}
</script>

<SelectField
	label="Valve type"
	value={component.valveType}
	options={TYPES.map((t) => ({ value: t, label: KIND_LABELS[t] }))}
	hint="Changing between a pressure valve (PRV, PSV) and a flow valve (FCV) resets the setpoint to 0."
	onchange={changeType}
/>
<SelectField
	label="Status"
	value={component.status}
	options={STATUSES.map((s) => ({ value: s, label: CONTROL_STATUS_LABELS[s] }))}
	onchange={(v) =>
		ws.editComponent<ControlValve>(component.id, 'change valve status', (c) => {
			c.status = v;
		})}
/>
{#if isFlow}
	<NumberField
		label="Flow setpoint"
		value={component.setpoint}
		category="flow"
		units={ws.units}
		bounds={setpointBounds}
		hint="The flow the valve throttles to."
		warning={setpointWarning}
		onchange={(v) =>
			v !== null &&
			ws.editComponent<ControlValve>(component.id, 'change setpoint', (c) => {
				c.setpoint = v;
			})}
	/>
{:else}
	<NumberField
		label={component.valveType === 'prv' ? 'Outlet pressure setpoint' : 'Inlet pressure setpoint'}
		value={component.setpoint}
		category="pressure"
		gauge
		units={ws.units}
		bounds={setpointBounds}
		hint={component.valveType === 'prv'
			? 'Gauge static pressure the valve holds at its outlet.'
			: 'Gauge static pressure the valve holds at its inlet.'}
		warning={setpointWarning}
		onchange={(v) =>
			v !== null &&
			ws.editComponent<ControlValve>(component.id, 'change setpoint', (c) => {
				c.setpoint = v;
			})}
	/>
{/if}
<ResistanceField
	value={component.resistance}
	units={ws.units}
	defaultLabel="ideal (no loss when fully open)"
	onchange={(r) =>
		ws.editComponent<ControlValve>(component.id, 'change valve resistance', (c) =>
			withOptional(c, 'resistance', r)
		)}
/>
