<script lang="ts">
	import type { ValveComponent, ControlValveResult } from '$lib/models';
	import { VALVE_STATUS_LABELS, VALVE_TYPE_LABELS } from '$lib/models';

	interface Props {
		/** The valve component. */
		valve: ValveComponent;
		/** The control valve result. */
		result: ControlValveResult;
	}

	let { valve, result }: Props = $props();

	// Determine status styling
	let statusColor = $derived.by(() => {
		switch (result.status) {
			case 'active':
				return 'bg-[var(--color-success)]/10 text-[var(--color-success)] border-[var(--color-success)]/30';
			case 'failed_open':
			case 'failed_closed':
				return 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30';
			case 'isolated':
				return 'bg-[var(--color-error)]/10 text-[var(--color-error)] border-[var(--color-error)]/30';
			case 'locked_open':
				return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30';
			default:
				return 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)] border-[var(--color-border)]';
		}
	});

	// Determine if this is a failed state
	let isFailed = $derived(
		result.status === 'failed_open' || result.status === 'failed_closed'
	);

	// Get unit based on valve type
	let valueUnit = $derived(valve.valve_type === 'fcv' ? 'GPM' : 'psi');
	let valueLabel = $derived.by(() => {
		switch (valve.valve_type) {
			case 'prv':
				return 'Downstream Pressure';
			case 'psv':
				return 'Relief Pressure';
			case 'fcv':
				return 'Flow Rate';
			case 'tcv':
				return 'Throttle';
			default:
				return 'Value';
		}
	});

	function formatNumber(value: number | undefined, decimals = 1): string {
		if (value === undefined) return '-';
		return value.toFixed(decimals);
	}
</script>

<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
		<div>
			<h4 class="text-sm font-medium text-[var(--color-text)]">{valve.name}</h4>
			<p class="text-xs text-[var(--color-text-muted)]">{VALVE_TYPE_LABELS[valve.valve_type]}</p>
		</div>
		<span class="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium {statusColor}">
			{VALVE_STATUS_LABELS[result.status]}
			{#if isFailed}
				<span>⚠️</span>
			{/if}
		</span>
	</div>

	<!-- Body -->
	<div class="p-4 space-y-4">
		<!-- Control Status -->
		{#if result.setpoint !== undefined}
			<div>
				<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
					{valueLabel} Control
				</p>
				<div class="mt-2 grid grid-cols-2 gap-2">
					<div class="rounded-md bg-[var(--color-surface-elevated)] px-3 py-2">
						<p class="text-xs text-[var(--color-text-muted)]">Setpoint</p>
						<p class="text-sm font-medium text-[var(--color-text)]">
							{formatNumber(result.setpoint)} {valueUnit}
						</p>
					</div>
					<div class="rounded-md bg-[var(--color-surface-elevated)] px-3 py-2">
						<p class="text-xs text-[var(--color-text-muted)]">Actual</p>
						<div class="flex items-center gap-2">
							<p class="text-sm font-medium text-[var(--color-text)]">
								{formatNumber(result.actual_value)} {valueUnit}
							</p>
							{#if result.setpoint_achieved}
								<span class="text-[var(--color-success)]" title="Setpoint achieved">✓</span>
							{:else}
								<span class="text-[var(--color-error)]" title="Setpoint not achieved">✗</span>
							{/if}
						</div>
					</div>
				</div>
				{#if !result.setpoint_achieved && isFailed}
					<p class="mt-2 text-xs text-[var(--color-warning)]">
						(not controlling - valve {result.status === 'failed_open' ? 'failed open' : 'failed closed'})
					</p>
				{/if}
			</div>
		{/if}

		<!-- Operating Data -->
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
			<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
				<p class="text-xs text-[var(--color-text-muted)]">Position</p>
				<p class="text-sm font-semibold text-[var(--color-text)]">
					{Math.round(result.valve_position * 100)}%
					{#if result.status === 'failed_open'}
						<span class="text-xs font-normal text-[var(--color-text-muted)]">(stuck)</span>
					{/if}
				</p>
			</div>
			<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
				<p class="text-xs text-[var(--color-text-muted)]">Pressure Drop</p>
				<p class="text-sm font-semibold text-[var(--color-text)]">{formatNumber(result.pressure_drop)} psi</p>
			</div>
			<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2">
				<p class="text-xs text-[var(--color-text-muted)]">Flow</p>
				<p class="text-sm font-semibold text-[var(--color-text)]">{formatNumber(result.flow)} GPM</p>
			</div>
		</div>
	</div>
</div>
