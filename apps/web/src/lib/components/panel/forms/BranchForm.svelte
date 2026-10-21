<script lang="ts">
	import type { TeeBranch, WyeBranch } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { LOSS_MODEL_LABELS } from '$lib/utils/labels';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	let { component }: { component: TeeBranch | WyeBranch } = $props();
	const ws = useWorkspace();
</script>

<SelectField
	label="Loss model"
	value={component.lossModel}
	options={[
		{ value: 'crane', label: LOSS_MODEL_LABELS.crane },
		{ value: 'ideal', label: LOSS_MODEL_LABELS.ideal }
	]}
	hint={component.lossModel === 'crane'
		? 'K for each path depends on the solved flow split (Crane TP-410, via the fluids library); the default.'
		: 'No loss in the fitting itself; use it to compare with EPANET, which models junctions this way.'}
	onchange={(v) =>
		ws.editComponent<TeeBranch | WyeBranch>(component.id, 'change loss model', (c) => {
			c.lossModel = v;
		})}
/>
{#if component.branchType === 'wye'}
	<NumberField
		label="Branch angle"
		value={component.angle}
		category="angle"
		units={ws.units}
		bounds={schemaBounds('WyeBranch', 'angle')}
		hint="Angle between the branch leg (outlet 2) and the run; the Crane correlation covers 30–60°."
		onchange={(v) =>
			v !== null &&
			ws.editComponent<WyeBranch>(component.id, 'change wye angle', (c) => {
				c.angle = v;
			})}
	/>
{:else}
	<p class="hint sm:col-span-2">
		The run goes from the run inlet to the run outlet; the branch port is the side outlet. Whether
		flow diverges or converges is a result of the solve, not an input.
	</p>
{/if}
