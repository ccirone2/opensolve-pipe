<script lang="ts">
	import type { ValveComponent, ValveStatus } from '$lib/models';
	import { VALVE_TYPE_LABELS, VALVE_STATUS_LABELS } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The valve component to edit. */
		component: ValveComponent;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();

	// Determine if valve is in a non-active state
	let isIsolated = $derived(
		component.status === 'isolated' || component.status === 'failed_closed'
	);
	let isFailedOpen = $derived(component.status === 'failed_open');
	let isLockedOpen = $derived(component.status === 'locked_open');
	let isControlValve = $derived(
		component.valve_type === 'prv' ||
			component.valve_type === 'psv' ||
			component.valve_type === 'fcv'
	);
</script>

<div class="space-y-4">
	<NumberInput
		id="elevation"
		label="Elevation"
		value={component.elevation}
		unit="ft"
		onchange={(value) => onUpdate('elevation', value)}
	/>

	<div>
		<label for="valve_type" class="block text-sm font-medium text-[var(--color-text)]"
			>Valve Type</label
		>
		<select
			id="valve_type"
			value={component.valve_type}
			onchange={(e) => onUpdate('valve_type', (e.target as HTMLSelectElement).value)}
			class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] shadow-sm focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
		>
			{#each Object.entries(VALVE_TYPE_LABELS) as [value, label]}
				<option {value}>{label}</option>
			{/each}
		</select>
	</div>

	<!-- Status Selector -->
	<div>
		<label for="status" class="block text-sm font-medium text-[var(--color-text)]">Status</label>
		<select
			id="status"
			value={component.status}
			onchange={(e) => onUpdate('status', (e.target as HTMLSelectElement).value as ValveStatus)}
			class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] shadow-sm focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
		>
			{#each Object.entries(VALVE_STATUS_LABELS) as [value, label]}
				<option {value}>{label}</option>
			{/each}
		</select>
	</div>

	<!-- Status Warning Messages -->
	{#if isIsolated}
		<div
			class="rounded-md border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 p-3 text-sm text-[var(--color-error)]"
		>
			<span class="font-medium">⚠ No Flow:</span>
			{#if component.status === 'failed_closed'}
				Valve failed closed - no flow through this path
			{:else}
				Valve is isolated/closed - no flow through this path
			{/if}
		</div>
	{:else if isFailedOpen}
		<div
			class="rounded-md border border-orange-500/30 bg-orange-500/10 p-3 text-sm text-orange-600 dark:text-orange-400"
		>
			<span class="font-medium">⚠ Failed Open:</span>
			Valve failed open - position locked at 100%
			{#if isControlValve}
				<br /><span class="text-xs">Setpoint control is disabled</span>
			{/if}
		</div>
	{:else if isLockedOpen}
		<div
			class="rounded-md border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-600 dark:text-blue-400"
		>
			<span class="font-medium">ℹ Locked Open:</span>
			Valve is locked at current position
			{#if isControlValve}
				<br /><span class="text-xs">Setpoint control is disabled</span>
			{/if}
		</div>
	{/if}

	<!-- Position Control -->
	{#if !isIsolated}
		{#if isFailedOpen}
			<!-- Failed open: show 100% position as read-only -->
			<div>
				<span class="block text-sm font-medium text-[var(--color-text)]">Position</span>
				<div
					class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2 text-sm text-[var(--color-text-muted)]"
				>
					100% (locked open)
				</div>
			</div>
		{:else if isLockedOpen}
			<!-- Locked open: show current position as read-only -->
			<div>
				<span class="block text-sm font-medium text-[var(--color-text)]">Position</span>
				<div
					class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2 text-sm text-[var(--color-text-muted)]"
				>
					{Math.round((component.position ?? 1) * 100)}% (locked)
				</div>
			</div>
		{:else}
			<!-- Active: normal position control -->
			<NumberInput
				id="position"
				label="Position"
				value={(component.position ?? 1) * 100}
				unit="%"
				min={0}
				max={100}
				step={1}
				onchange={(value) => onUpdate('position', value / 100)}
				hint="0% = fully closed, 100% = fully open"
			/>
		{/if}
	{/if}

	<!-- Control Valve Setpoint -->
	{#if isControlValve && !isIsolated}
		{#if isFailedOpen || isLockedOpen}
			<!-- Setpoint shown but marked as ignored -->
			<div class="opacity-60">
				<span class="block text-sm font-medium text-[var(--color-text)]">
					{#if component.valve_type === 'prv'}
						Downstream Pressure Setting
					{:else if component.valve_type === 'psv'}
						Relief Pressure Setting
					{:else}
						Flow Setting
					{/if}
				</span>
				<div
					class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 py-2 text-sm text-[var(--color-text-muted)]"
				>
					{component.setpoint ?? 0}
					{component.valve_type === 'fcv' ? 'GPM' : 'psi'}
					<span class="ml-2 text-xs">(ignored)</span>
				</div>
			</div>
		{:else}
			<!-- Active: normal setpoint control -->
			{#if component.valve_type === 'prv' || component.valve_type === 'psv'}
				<NumberInput
					id="setpoint"
					label={component.valve_type === 'prv'
						? 'Downstream Pressure Setting'
						: 'Relief Pressure Setting'}
					value={component.setpoint}
					unit="psi"
					min={0}
					required
					onchange={(value) => onUpdate('setpoint', value)}
				/>
			{:else if component.valve_type === 'fcv'}
				<NumberInput
					id="setpoint"
					label="Flow Setting"
					value={component.setpoint}
					unit="GPM"
					min={0}
					required
					onchange={(value) => onUpdate('setpoint', value)}
				/>
			{/if}
		{/if}
	{/if}

	<!-- Optional Cv field -->
	{#if !isIsolated}
		<details class="rounded-md border border-[var(--color-border)]">
			<summary
				class="cursor-pointer px-3 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-elevated)]"
			>
				Advanced
			</summary>
			<div class="border-t border-[var(--color-border)] p-3">
				<NumberInput
					id="cv"
					label="Cv Coefficient"
					value={component.cv}
					min={0}
					step={1}
					onchange={(value) => onUpdate('cv', value)}
					hint="Flow coefficient (optional - for detailed hydraulic model)"
				/>
			</div>
		</details>
	{/if}
</div>
