<script lang="ts">
	import type { PumpComponent, PumpCurve, PumpResult } from '$lib/models';
	import { PUMP_STATUS_LABELS, PUMP_OPERATING_MODE_LABELS } from '$lib/models';
	import PumpCurveChart from './PumpCurveChart.svelte';

	interface Props {
		/** The pump component. */
		pump: PumpComponent;
		/** The pump curve (if assigned). */
		curve?: PumpCurve;
		/** The pump result. */
		result: PumpResult;
	}

	let { pump, curve, result }: Props = $props();

	// Collapsible state for viscosity correction details
	let showViscosityDetails = $state(false);

	// Determine status styling
	let statusColor = $derived.by(() => {
		switch (result.status) {
			case 'running':
				return 'bg-[var(--color-success)]/10 text-[var(--color-success)] border-[var(--color-success)]/30';
			case 'off_check':
			case 'off_no_check':
				return 'bg-[var(--color-text-muted)]/10 text-[var(--color-text-muted)] border-[var(--color-border)]';
			case 'locked_out':
				return 'bg-[var(--color-error)]/10 text-[var(--color-error)] border-[var(--color-error)]/30';
			default:
				return 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)] border-[var(--color-border)]';
		}
	});

	// Determine if this is a VFD/variable speed pump
	let isVFD = $derived(
		pump.operating_mode === 'variable_speed' ||
			pump.operating_mode === 'controlled_pressure' ||
			pump.operating_mode === 'controlled_flow'
	);

	function formatNumber(value: number | undefined | null, decimals = 1): string {
		if (value == null) return '-'; // handles both null and undefined
		return value.toFixed(decimals);
	}
</script>

<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
		<div>
			<h4 class="text-sm font-medium text-[var(--color-text)]">{pump.name}</h4>
			{#if curve}
				<p class="text-xs text-[var(--color-text-muted)]">{curve.name}</p>
			{/if}
		</div>
		<span class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium {statusColor}">
			{PUMP_STATUS_LABELS[result.status]}
		</span>
	</div>

	<!-- Body -->
	<div class="p-4">
		<!-- Pump Curve Chart -->
		{#if curve}
			<PumpCurveChart {curve} {result} />
		{:else}
			<p class="text-sm text-[var(--color-warning)]">No pump curve assigned</p>
		{/if}

		<!-- Operating Point Summary -->
		<div class="mt-4 space-y-4">
			<!-- Primary Metrics -->
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
					<p class="text-xs text-[var(--color-text-muted)]">Flow</p>
					<p class="text-lg font-semibold text-[var(--color-text)]">{formatNumber(result.operating_flow)} GPM</p>
				</div>
				<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
					<p class="text-xs text-[var(--color-text-muted)]">Head</p>
					<p class="text-lg font-semibold text-[var(--color-text)]">{formatNumber(result.operating_head)} ft</p>
				</div>
				{#if isVFD && result.actual_speed !== undefined}
					<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
						<p class="text-xs text-[var(--color-text-muted)]">Speed (VFD)</p>
						<p class="text-lg font-semibold text-[var(--color-text)]">{(result.actual_speed * 100).toFixed(0)}%</p>
					</div>
				{/if}
				{#if result.power !== undefined}
					<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
						<p class="text-xs text-[var(--color-text-muted)]">Power</p>
						<p class="text-lg font-semibold text-[var(--color-text)]">{formatNumber(result.power, 2)} kW</p>
					</div>
				{/if}
			</div>

			<!-- Efficiency -->
			{#if result.efficiency !== undefined}
				<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
					<div class="flex items-center justify-between">
						<p class="text-xs text-[var(--color-text-muted)]">Efficiency</p>
						{#if result.viscosity_correction_applied}
							<span class="text-xs text-[var(--color-accent)]">(viscosity corrected)</span>
						{/if}
					</div>
					<p class="text-lg font-semibold text-[var(--color-text)]">{(result.efficiency * 100).toFixed(1)}%</p>
				</div>
			{/if}

			<!-- NPSH Section -->
			<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
				<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">NPSH</p>
				<div class="mt-2 grid grid-cols-3 gap-4">
					<div>
						<p class="text-xs text-[var(--color-text-muted)]">Available</p>
						<p class="text-sm font-semibold text-[var(--color-text)]">{formatNumber(result.npsh_available)} ft</p>
					</div>
					{#if result.npsh_margin !== undefined}
						<div>
							<p class="text-xs text-[var(--color-text-muted)]">Required</p>
							<p class="text-sm font-semibold text-[var(--color-text)]">
								{formatNumber(result.npsh_available - result.npsh_margin)} ft
							</p>
						</div>
						<div>
							<p class="text-xs text-[var(--color-text-muted)]">Margin</p>
							<p class="flex items-center gap-1 text-sm font-semibold {result.npsh_margin > 0 ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'}">
								{formatNumber(result.npsh_margin)} ft
								{#if result.npsh_margin > 0}
									<span>✓</span>
								{:else}
									<span>⚠️</span>
								{/if}
							</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Viscosity Correction Details (collapsible) -->
			{#if result.viscosity_correction_applied && result.viscosity_correction_factors}
				<details
					class="rounded-md border border-purple-500/30 bg-purple-500/5"
					bind:open={showViscosityDetails}
				>
					<summary class="cursor-pointer px-3 py-2 text-sm font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-500/10">
						Viscosity Correction Details
					</summary>
					<div class="border-t border-purple-500/20 px-3 py-3">
						<div class="grid grid-cols-3 gap-4 text-sm">
							<div>
								<p class="text-xs text-[var(--color-text-muted)]">C<sub>Q</sub> (Flow)</p>
								<p class="font-mono font-semibold text-[var(--color-text)]">
									{result.viscosity_correction_factors.c_q.toFixed(3)}
								</p>
							</div>
							<div>
								<p class="text-xs text-[var(--color-text-muted)]">C<sub>H</sub> (Head)</p>
								<p class="font-mono font-semibold text-[var(--color-text)]">
									{result.viscosity_correction_factors.c_h.toFixed(3)}
								</p>
							</div>
							<div>
								<p class="text-xs text-[var(--color-text-muted)]">C<sub>η</sub> (Efficiency)</p>
								<p class="font-mono font-semibold text-[var(--color-text)]">
									{result.viscosity_correction_factors.c_eta.toFixed(3)}
								</p>
							</div>
						</div>
						<p class="mt-2 text-xs text-[var(--color-text-muted)]">
							Per ANSI/HI 9.6.7 (Centrifugal Pumps for Viscous Liquids)
						</p>
					</div>
				</details>
			{/if}

			<!-- Operating Mode (if not fixed speed) -->
			{#if pump.operating_mode && pump.operating_mode !== 'fixed_speed'}
				<div class="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
					<span>Mode:</span>
					<span class="font-medium">{PUMP_OPERATING_MODE_LABELS[pump.operating_mode]}</span>
				</div>
			{/if}
		</div>
	</div>
</div>
