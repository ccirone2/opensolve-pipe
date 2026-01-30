<script lang="ts">
	import type { WyeBranch } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The wye branch component to edit. */
		component: WyeBranch;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();

	// Get port sizes from component
	const runInlet = $derived(component.ports.find((p) => p.id === 'run_inlet'));
	const branch = $derived(component.ports.find((p) => p.id === 'branch'));

	function updatePortSize(portId: string, size: number) {
		const newPorts = component.ports.map((p) => (p.id === portId ? { ...p, nominal_size: size } : p));
		onUpdate('ports', newPorts);
	}

	function updateAllRunPorts(size: number) {
		const newPorts = component.ports.map((p) =>
			p.id === 'run_inlet' || p.id === 'run_outlet' ? { ...p, nominal_size: size } : p
		);
		onUpdate('ports', newPorts);
	}
</script>

<div class="space-y-4">
	<div class="rounded-md bg-[var(--color-success)]/10 p-3">
		<p class="text-sm text-[var(--color-success)]">
			<strong>Wye Branch:</strong> Angled fitting (typically 45°) for smoother flow transitions.
			Lower head loss than standard tee.
		</p>
	</div>

	<!-- Visual diagram -->
	<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-4">
		<div class="flex items-center justify-center">
			<svg viewBox="0 0 120 80" class="h-16 w-24">
				<!-- Run line (horizontal) -->
				<line x1="10" y1="50" x2="110" y2="50" stroke="currentColor" stroke-width="4" />
				<!-- Branch line (angled up at 45°) -->
				<line x1="60" y1="50" x2="85" y2="15" stroke="currentColor" stroke-width="4" />
				<!-- Port labels -->
				<text x="15" y="65" class="fill-current text-[8px] opacity-60">Run In</text>
				<text x="85" y="65" class="fill-current text-[8px] opacity-60">Run Out</text>
				<text x="75" y="20" class="fill-current text-[8px] opacity-60">Branch</text>
				<!-- Angle indicator -->
				<path d="M 60,50 L 70,50 A 10,10 0 0,0 67,40" fill="none" stroke="currentColor" stroke-width="1" class="opacity-50" />
				<text x="68" y="48" class="fill-current text-[6px] opacity-50">45°</text>
			</svg>
		</div>
		<p class="mt-2 text-center text-xs text-[var(--color-text-muted)]">Lower pressure drop than 90° tee</p>
	</div>

	<NumberInput
		id="elevation"
		label="Elevation"
		value={component.elevation}
		unit="ft"
		onchange={(value) => onUpdate('elevation', value)}
	/>

	<NumberInput
		id="branch_angle"
		label="Branch Angle"
		value={component.branch_angle}
		unit="deg"
		min={22.5}
		max={60}
		step={5}
		hint="Common values: 45°, 60°"
		onchange={(value) => onUpdate('branch_angle', value)}
	/>

	<div class="border-t border-[var(--color-border)] pt-4">
		<span class="block text-sm font-medium text-[var(--color-text)]">Port Sizes</span>
		<p class="mt-1 text-xs text-[var(--color-text-muted)]">Configure the nominal pipe size for each connection</p>
	</div>

	<NumberInput
		id="run_size"
		label="Run Size (Inlet & Outlet)"
		value={runInlet?.nominal_size ?? 4}
		unit="in"
		min={0.5}
		onchange={updateAllRunPorts}
	/>

	<NumberInput
		id="branch_size"
		label="Branch Size"
		value={branch?.nominal_size ?? 4}
		unit="in"
		min={0.5}
		hint="Can be same size or smaller than run"
		onchange={(value) => updatePortSize('branch', value)}
	/>

	{#if branch && runInlet && branch.nominal_size > runInlet.nominal_size}
		<div class="rounded-md border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 p-2">
			<p class="text-xs text-[var(--color-warning)]">
				Branch size larger than run is unusual. Typically branch is same size or smaller.
			</p>
		</div>
	{/if}
</div>
