<script lang="ts">
	import { solvedState } from '$lib/stores';
	import { isPump, type Component } from '$lib/models';

	interface Props {
		component: Component;
	}

	let { component }: Props = $props();

	let componentResult = $derived($solvedState?.component_results?.[component.id] ?? null);
	let pipingResult = $derived($solvedState?.piping_results?.[component.id] ?? null);
	let pumpResult = $derived(isPump(component) ? $solvedState?.pump_results?.[component.id] ?? null : null);

	let hasResults = $derived(!!componentResult || !!pipingResult || !!pumpResult);

	function fmt(val: number | null | undefined, decimals = 1): string {
		if (val === null || val === undefined) return '-';
		return val.toFixed(decimals);
	}
</script>

{#if $solvedState && hasResults}
	<div class="flex gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-1.5">
		{#if componentResult?.pressure !== undefined}
			<div class="min-w-0 flex-1 text-center">
				<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Pressure</p>
				<p class="mono-value text-[0.6875rem] font-semibold text-[var(--color-text)]">{fmt(componentResult.pressure)}</p>
			</div>
		{/if}
		{#if pipingResult?.flow !== undefined}
			<div class="min-w-0 flex-1 text-center">
				<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Flow</p>
				<p class="mono-value text-[0.6875rem] font-semibold text-[var(--color-text)]">{fmt(pipingResult.flow)}</p>
			</div>
		{/if}
		{#if pipingResult?.velocity !== undefined}
			<div class="min-w-0 flex-1 text-center">
				<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Velocity</p>
				<p class="mono-value text-[0.6875rem] font-semibold text-[var(--color-text)]">{fmt(pipingResult.velocity)}</p>
			</div>
		{/if}
		{#if pumpResult?.operating_head !== undefined}
			<div class="min-w-0 flex-1 text-center">
				<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Head</p>
				<p class="mono-value text-[0.6875rem] font-semibold text-[var(--color-text)]">{fmt(pumpResult.operating_head)}</p>
			</div>
		{/if}
	</div>
{/if}
