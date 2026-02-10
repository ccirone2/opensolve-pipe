<script lang="ts">
	import { components, fluid, settings, solvedState, isSolved, metadata } from '$lib/stores';
	import { FLUID_TYPE_LABELS, COMPONENT_CATEGORIES, type FluidType } from '$lib/models';

	interface Props {
		onSolve?: () => void;
	}

	let { onSolve }: Props = $props();

	let componentCount = $derived($components.length);
	let fluidLabel = $derived(FLUID_TYPE_LABELS[$fluid?.type as FluidType] ?? 'Water');
	let unitSystem = $derived($settings?.units?.system ?? 'imperial');
	let projectName = $derived($metadata?.name ?? 'Untitled Project');

	let categoryCounts = $derived.by(() => {
		const counts = { sources: 0, equipment: 0, connections: 0 };
		for (const c of $components) {
			if ((COMPONENT_CATEGORIES.Sources as string[]).includes(c.type)) counts.sources++;
			else if ((COMPONENT_CATEGORIES.Equipment as string[]).includes(c.type)) counts.equipment++;
			else counts.connections++;
		}
		return counts;
	});
</script>

<div class="flex h-full flex-col items-center justify-center gap-4 p-4 text-center">
	<!-- Project Info -->
	<div>
		<h3 class="text-sm font-semibold text-[var(--color-text)]">{projectName}</h3>
		<p class="mt-1 text-[0.625rem] text-[var(--color-text-subtle)]">
			{componentCount} component{componentCount !== 1 ? 's' : ''}
		</p>
	</div>

	<!-- Quick Stats -->
	{#if componentCount > 0}
		<div class="grid w-full max-w-[200px] grid-cols-3 gap-2 text-center">
			<div>
				<p class="mono-value text-base font-semibold text-[var(--color-badge-source-text)]">{categoryCounts.sources}</p>
				<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Sources</p>
			</div>
			<div>
				<p class="mono-value text-base font-semibold text-[var(--color-badge-equipment-text)]">{categoryCounts.equipment}</p>
				<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Equipment</p>
			</div>
			<div>
				<p class="mono-value text-base font-semibold text-[var(--color-badge-connection-text)]">{categoryCounts.connections}</p>
				<p class="text-[0.5625rem] text-[var(--color-text-subtle)]">Connections</p>
			</div>
		</div>
	{/if}

	<!-- Fluid & Units -->
	<div class="space-y-1">
		<p class="text-[0.6875rem] text-[var(--color-text-muted)]">
			<span class="font-medium">{fluidLabel}</span> at {$fluid?.temperature ?? 68}{unitSystem === 'si' ? '\u00B0C' : '\u00B0F'}
		</p>
		<p class="text-[0.625rem] uppercase text-[var(--color-text-subtle)]">
			{unitSystem} units
		</p>
	</div>

	<!-- Solve Status -->
	{#if $isSolved && $solvedState?.converged}
		<div class="flex items-center gap-1 text-xs text-[var(--color-success)]">
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
			</svg>
			Solved
		</div>
	{:else if componentCount > 0}
		<button
			type="button"
			onclick={onSolve}
			class="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-accent)] px-4 py-1.5 text-xs font-semibold text-[var(--color-accent-text)] transition-colors hover:bg-[var(--color-accent-hover)]"
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728M9.172 15.172a4 4 0 010-5.656m5.656 0a4 4 0 010 5.656M12 12h.01" />
			</svg>
			Solve Network
		</button>
	{/if}
</div>
