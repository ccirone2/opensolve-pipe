<!--
	A check valve: its status, type and cracking pressure are drawn from the registry
	(field-registry.ts); its resistance here, in More.
-->
<script lang="ts">
	import type { CheckValve } from '$lib/api/types';
	import ValveResistanceField from '../ValveResistanceField.svelte';
	import FieldSections from '../FieldSections.svelte';

	let { component }: { component: CheckValve } = $props();
</script>

<FieldSections {component}>
	{#snippet field(path)}
		{#if path === 'resistance'}
			<ValveResistanceField
				{component}
				defaultLabel="the solver's cited loss for this valve type (shown in the results)"
			/>
		{/if}
	{/snippet}
</FieldSections>
