<!--
	An assigned-flow node's flow (SDD §4.11) as it is entered: a direction (demand or supply) and
	a magnitude in the display flow unit, stored as one signed SI value (utils/assigned-flow.ts).
	Used by the node's form and, before the node exists, where it is added (its flow has no
	default). `flow` is null until entered; the direction shown then, or at 0 (which has none), is
	the one chosen here, and applies to the magnitude entered next. The note on a flow of 0 is a
	warning line, or (`zeroNote: 'hint'`, where the node is added, above the Add button) the
	field's hint in place of the direction's, so storing 0 adds no line.
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import type { FieldChange } from '$lib/components/ui/field-mode';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import {
		DIRECTION_LABELS,
		flowDirection,
		magnitudeBounds,
		signedFlow,
		type FlowDirection
	} from '$lib/utils/assigned-flow';

	interface Props {
		/** The stored flow, m³/s (positive: a demand), or null while none is entered. */
		flow: number | null;
		units: UnitPreferences;
		/** An error about the flow from the owner (e.g. not entered when the node is added). */
		error?: string | null;
		/**
		 * Receives the new signed flow (SI), and whether the user changed its direction or its
		 * magnitude. Return false when it was not stored.
		 */
		onchange: (flow: number, changed: 'direction' | 'magnitude') => boolean | void;
		/** Called on each edit of the flow's text, before it is stored (NumberField). */
		oninput?: () => void;
		/** Where the note on a flow of 0 goes: a warning line, or the hint's place. */
		zeroNote?: 'warning' | 'hint';
		/**
		 * A scenario value (the node's form): direction and magnitude are one change, noted once,
		 * under the flow.
		 */
		change?: FieldChange | null;
	}

	let {
		flow,
		units,
		error = null,
		onchange,
		oninput,
		zeroNote = 'warning',
		change = null
	}: Props = $props();

	const ZERO_NOTE = 'At 0 the node passes no flow: it is a closed end, as a plug.';

	/** The direction for a flow that has none (null or 0): the last one chosen or entered. */
	let chosen = $state<FlowDirection>('demand');
	const stored = $derived(flow === null ? null : flowDirection(flow));
	const direction = $derived(stored ?? chosen);

	function choose(next: FlowDirection) {
		chosen = next;
		// A stored flow with a direction changes sign; 0 (or none yet) keeps the choice for later.
		if (flow !== null && stored !== null && stored !== next) onchange(-flow, 'direction');
	}

	function enter(magnitude: number | null) {
		if (magnitude === null) return false;
		// A supply set to 0 stays a supply in the form, for the magnitude entered next.
		chosen = direction;
		return onchange(signedFlow(magnitude, direction), 'magnitude');
	}
</script>

<SelectField
	label="Direction"
	value={direction}
	options={(['demand', 'supply'] as const).map((d) => ({ value: d, label: DIRECTION_LABELS[d] }))}
	{change}
	changeNote={false}
	onchange={choose}
/>
<NumberField
	label="Flow"
	value={flow === null ? null : Math.abs(flow)}
	category="flow"
	{units}
	bounds={magnitudeBounds(direction)}
	hint={flow === 0 && zeroNote === 'hint'
		? ZERO_NOTE
		: direction === 'demand'
			? 'Leaves the network at the port, whatever the pressure there.'
			: 'Enters the network at the port, whatever the pressure there.'}
	warning={flow === 0 && zeroNote === 'warning' ? ZERO_NOTE : null}
	{error}
	{change}
	onchange={enter}
	{oninput}
/>
