<!--
	A pressure relief valve (proposal pressure-relief-valve.md §6 W3), after the elevation: its
	status, then its set pressure and capacity (ReliefValveFields), then the hint. A kind of
	capacity picked whose values are not all entered yet is pending (EquipmentForm's rule: no number
	is carried to another kind); with no default to fall back on, the stored capacity applies until
	the new kind's values are all entered, and the warning says so. In a scenario the status, the
	set and the capacity are scenario values (D15): a value of the base's kind is a change of that
	value, noted at its field; a change of kind is one whole-capacity change, noted once at the
	group (utils/scenarios.ts nextOverrides). No range is checked here: the API refuses what its law
	cannot represent, and the solve flags partial lift.
-->
<script lang="ts">
	import type { ReliefValve } from '$lib/api/types';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import {
		capacityDraft,
		completeCapacity,
		type CapacityDraft,
		type CapacityField,
		type CapacityKind,
		withCapacityValue
	} from '$lib/utils/factory';
	import { inSentence } from '$lib/utils/labels';
	import { RELIEF_STATUS_LABELS } from '$lib/utils/relief';
	import { fieldLabelFor } from '$lib/utils/scenarios';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import ReliefValveFields from '../ReliefValveFields.svelte';
	import FieldSections from '../FieldSections.svelte';

	let { component }: { component: ReliefValve } = $props();
	const ws = useWorkspace();
	const STATUSES = ['active', 'locked_closed'] as const;

	/** A kind picked whose values are not all entered yet (page state; the form is per valve). */
	let pending = $state<CapacityDraft | null>(null);
	const open = $derived(pending && pending.kind !== component.capacity.kind ? pending : null);
	const shown = $derived<CapacityDraft>(open ?? capacityDraft(component.capacity));

	/** What applies until the kind picked is entered: the stored capacity, in words. */
	const current = $derived(
		component.capacity.kind === 'api526'
			? `the API 526 letter ${component.capacity.letter}`
			: component.capacity.kind === 'effective'
				? 'the API 520 effective area'
				: 'the certified capacity'
	);
	const ENTER: Readonly<Record<CapacityKind, string>> = {
		api526: 'Choose an API 526 orifice letter to use it',
		effective: 'Enter the API 520 effective area to use it',
		certified: 'Enter the actual orifice area and the rated coefficient of discharge to use them'
	};
	const warning = $derived(open ? `${ENTER[open.kind]}; until then ${current} applies.` : null);

	function store(capacity: ReliefValve['capacity'], label: string): boolean {
		return ws.editComponent<ReliefValve>(component.id, label, (c) => {
			c.capacity = capacity;
		});
	}

	function onkind(kind: CapacityKind) {
		pending = kind === component.capacity.kind ? null : { kind };
	}

	function onvalue(field: CapacityField, value: number | string | null): boolean | void {
		if (open) {
			const next = withCapacityValue(open, field, value);
			const complete = completeCapacity(next);
			if (!complete) {
				pending = next;
				return;
			}
			const stored = store(complete, 'change capacity');
			if (stored) pending = null;
			return stored;
		}
		const next = completeCapacity(
			withCapacityValue(capacityDraft(component.capacity), field, value)
		);
		if (!next) return false;
		// Its acronyms and symbols keep their case: "change API 526 orifice letter".
		const label = fieldLabelFor(component, `capacity.${field}`);
		return store(next, `change ${inSentence(label)}`);
	}
</script>

<FieldSections {component}>
	{#snippet field(path)}
		{#if path === 'status'}
			<SelectField
				label="Status"
				value={component.status}
				options={STATUSES.map((s) => ({ value: s, label: RELIEF_STATUS_LABELS[s] }))}
				help="Locked closed: gagged, or isolated by its block valve; it does not open, so a scenario shows the pressure without relief."
				change={ws.componentChange(component.id, 'status')}
				onchange={(v) =>
					ws.editComponent<ReliefValve>(component.id, 'change valve status', (c) => {
						c.status = v;
					})}
			/>
		{:else if path === 'setPressure'}
			<ReliefValveFields
				setPressure={component.setPressure}
				capacity={shown}
				units={ws.units}
				{warning}
				onset={(v) =>
					ws.editComponent<ReliefValve>(component.id, 'change set pressure', (c) => {
						c.setPressure = v;
					})}
				{onkind}
				{onvalue}
				setChange={ws.componentChange(component.id, 'setPressure')}
				wholeChange={ws.componentChange(component.id, 'capacity')}
				partChange={(field) => ws.componentChange(component.id, `capacity.${field}`)}
			/>
		{/if}
	{/snippet}
	{#snippet about()}
		A conventional spring-loaded pressure relief valve in liquid service (API 520 Part I): closed
		while the pressure difference across it is below its set pressure, opening in proportion to the
		overpressure (a convention: real valves surge open and reclose below set; partial lift is
		flagged), fully open at set plus overpressure with API 520's liquid capacity. Not EPANET's PSV
		(pressure-sustaining valve). Flashing at its outlet and a viscous liquid are flagged; gases,
		steam and two-phase relief are not modelled. To discharge to atmosphere, use Discharge to
		atmosphere at its free outlet (Piping).
	{/snippet}
</FieldSections>
