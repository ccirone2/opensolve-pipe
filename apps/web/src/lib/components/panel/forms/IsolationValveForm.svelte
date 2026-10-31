<!--
	An isolation valve: its status and type are drawn from the registry (field-registry.ts); its
	resistance here, in More (CLAUDE.md D9: the default is Crane's open K at the connected size).
-->
<script lang="ts">
	import type { IsolationValve } from '$lib/api/types';
	import ValveResistanceField from '../ValveResistanceField.svelte';
	import FieldSections from '../FieldSections.svelte';

	let { component }: { component: IsolationValve } = $props();
</script>

<FieldSections {component}>
	{#snippet field(path)}
		{#if path === 'resistance'}
			<ValveResistanceField
				{component}
				defaultLabel="Crane TP-410 K, full bore and fully open, at the connected size"
			/>
		{/if}
	{/snippet}
</FieldSections>
