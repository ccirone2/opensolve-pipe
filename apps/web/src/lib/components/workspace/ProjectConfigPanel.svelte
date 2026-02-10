<script lang="ts">
	import { projectStore, fluid, settings, pumpLibrary } from '$lib/stores';
	import {
		FLUID_TYPE_LABELS,
		GLYCOL_FLUID_TYPES,
		type FluidType,
		type UnitSystem,
		type UnitPreferences,
		type SolverOptions,
		type FluidDefinition
	} from '$lib/models';

	// Fluid config
	let fluidType = $derived($fluid?.type ?? 'water');
	let fluidTemp = $derived($fluid?.temperature ?? 68);
	let fluidConcentration = $derived($fluid?.concentration ?? 50);

	// Unit system
	let unitSystem = $derived($settings?.units?.system ?? 'imperial');

	// Solver options
	let maxIterations = $derived($settings?.solver_options?.max_iterations ?? 100);
	let tolerance = $derived($settings?.solver_options?.tolerance ?? 0.001);

	// Collapsible sections
	let fluidOpen = $state(true);
	let unitsOpen = $state(true);
	let solverOpen = $state(false);
	let pumpLibOpen = $state(false);

	function updateFluid(updates: Partial<FluidDefinition>) {
		const current = $fluid ?? { type: 'water' as FluidType, temperature: 68 };
		projectStore.updateFluid({ ...current, ...updates });
	}

	function updateUnitSystem(system: UnitSystem) {
		projectStore.updateSettings({
			units: { ...($settings?.units ?? {}), system } as UnitPreferences
		});
	}

	function updateSolverOption(key: string, value: number) {
		const current = $settings?.solver_options ?? {};
		projectStore.updateSettings({
			solver_options: { ...current, [key]: value } as SolverOptions
		});
	}

	const fluidTypes = Object.entries(FLUID_TYPE_LABELS) as [FluidType, string][];
	const unitSystems: { id: UnitSystem; label: string }[] = [
		{ id: 'imperial', label: 'Imperial' },
		{ id: 'si', label: 'SI' }
	];
</script>

<div class="flex flex-col gap-0.5 p-2">
	<!-- Fluid Configuration -->
	<div class="card">
		<button
			type="button"
			onclick={() => (fluidOpen = !fluidOpen)}
			class="flex w-full items-center justify-between px-2.5 py-2 text-left"
		>
			<span class="section-heading">
				Fluid
			</span>
			<svg
				class="h-3 w-3 text-[var(--color-text-subtle)] transition-transform {fluidOpen ? 'rotate-180' : ''}"
				fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if fluidOpen}
			<div class="space-y-2.5 border-t border-[var(--color-border)] px-2.5 py-2.5">
				<!-- Fluid Type -->
				<div>
					<label for="fluid-type" class="mb-1 block section-heading text-[var(--color-text-subtle)]">
						Type
					</label>
					<select
						id="fluid-type"
						value={fluidType}
						onchange={(e) => updateFluid({ type: (e.target as HTMLSelectElement).value as FluidType })}
						class="form-input"
					>
						{#each fluidTypes as [value, label]}
							<option {value}>{label}</option>
						{/each}
					</select>
				</div>

				<!-- Temperature -->
				<div>
					<label for="fluid-temp" class="mb-1 block section-heading text-[var(--color-text-subtle)]">
						Temperature ({unitSystem === 'si' ? 'C' : 'F'})
					</label>
					<input
						id="fluid-temp"
						type="number"
						value={fluidTemp}
						onchange={(e) => updateFluid({ temperature: parseFloat((e.target as HTMLInputElement).value) || 68 })}
						class="form-input mono-value"
					/>
				</div>

				<!-- Concentration (glycols only) -->
				{#if GLYCOL_FLUID_TYPES.includes(fluidType)}
					<div>
						<label for="fluid-concentration" class="mb-1 block section-heading text-[var(--color-text-subtle)]">
							Concentration (%)
						</label>
						<input
							id="fluid-concentration"
							type="number"
							min="0"
							max="100"
							value={fluidConcentration}
							onchange={(e) => updateFluid({ concentration: parseFloat((e.target as HTMLInputElement).value) || 50 })}
							class="form-input mono-value"
						/>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Unit System -->
	<div class="card">
		<button
			type="button"
			onclick={() => (unitsOpen = !unitsOpen)}
			class="flex w-full items-center justify-between px-2.5 py-2 text-left"
		>
			<span class="section-heading">
				Display Units
			</span>
			<svg
				class="h-3 w-3 text-[var(--color-text-subtle)] transition-transform {unitsOpen ? 'rotate-180' : ''}"
				fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if unitsOpen}
			<div class="border-t border-[var(--color-border)] px-2.5 py-2.5">
				<div class="flex gap-1">
					{#each unitSystems as sys}
						<button
							type="button"
							onclick={() => updateUnitSystem(sys.id)}
							class="flex-1 rounded px-2 py-1.5 text-[0.6875rem] font-medium transition-colors
								{unitSystem === sys.id
								? 'bg-[var(--color-accent)] text-[var(--color-accent-text)]'
								: 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-tree-hover)] hover:text-[var(--color-text)]'}"
						>
							{sys.label}
						</button>
					{/each}
				</div>
			</div>
		{/if}
	</div>

	<!-- Solver Options -->
	<div class="card">
		<button
			type="button"
			onclick={() => (solverOpen = !solverOpen)}
			class="flex w-full items-center justify-between px-2.5 py-2 text-left"
		>
			<span class="section-heading">
				Solver
			</span>
			<svg
				class="h-3 w-3 text-[var(--color-text-subtle)] transition-transform {solverOpen ? 'rotate-180' : ''}"
				fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if solverOpen}
			<div class="space-y-2.5 border-t border-[var(--color-border)] px-2.5 py-2.5">
				<div>
					<label for="solver-max-iter" class="mb-1 block section-heading text-[var(--color-text-subtle)]">
						Max Iterations
					</label>
					<input
						id="solver-max-iter"
						type="number"
						min="1"
						max="10000"
						value={maxIterations}
						onchange={(e) => updateSolverOption('max_iterations', parseInt((e.target as HTMLInputElement).value) || 100)}
						class="form-input mono-value"
					/>
				</div>

				<div>
					<label for="solver-tolerance" class="mb-1 block section-heading text-[var(--color-text-subtle)]">
						Tolerance
					</label>
					<input
						id="solver-tolerance"
						type="number"
						min="0.0000001"
						max="1"
						step="0.0001"
						value={tolerance}
						onchange={(e) => updateSolverOption('tolerance', parseFloat((e.target as HTMLInputElement).value) || 0.001)}
						class="form-input mono-value"
					/>
				</div>
			</div>
		{/if}
	</div>

	<!-- Pump Library -->
	<div class="card">
		<button
			type="button"
			onclick={() => (pumpLibOpen = !pumpLibOpen)}
			class="flex w-full items-center justify-between px-2.5 py-2 text-left"
		>
			<span class="section-heading">
				Pump Library
				{#if $pumpLibrary.length > 0}
					<span class="ml-1 text-[var(--color-accent)]">({$pumpLibrary.length})</span>
				{/if}
			</span>
			<svg
				class="h-3 w-3 text-[var(--color-text-subtle)] transition-transform {pumpLibOpen ? 'rotate-180' : ''}"
				fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		{#if pumpLibOpen}
			<div class="border-t border-[var(--color-border)] px-2.5 py-2.5">
				{#if $pumpLibrary.length === 0}
					<p class="text-center text-xs text-[var(--color-text-subtle)]">No pump curves defined</p>
				{:else}
					<div class="space-y-1">
						{#each $pumpLibrary as curve}
							<div class="flex items-center justify-between rounded bg-[var(--color-surface)] px-2 py-1.5">
								<span class="text-xs text-[var(--color-text)]">{curve.name}</span>
								<span class="text-[0.625rem] text-[var(--color-text-subtle)]">
									{curve.points?.length ?? 0} pts
								</span>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>
