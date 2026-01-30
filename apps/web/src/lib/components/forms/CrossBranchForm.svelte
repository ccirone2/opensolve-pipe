<script lang="ts">
	import type { CrossBranch } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The cross branch component to edit. */
		component: CrossBranch;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();

	// Get port sizes from component
	const runInlet = $derived(component.ports.find((p) => p.id === 'run_inlet'));
	const runOutlet = $derived(component.ports.find((p) => p.id === 'run_outlet'));
	const branch1 = $derived(component.ports.find((p) => p.id === 'branch_1'));
	const branch2 = $derived(component.ports.find((p) => p.id === 'branch_2'));

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

	function updateAllBranchPorts(size: number) {
		const newPorts = component.ports.map((p) =>
			p.id === 'branch_1' || p.id === 'branch_2' ? { ...p, nominal_size: size } : p
		);
		onUpdate('ports', newPorts);
	}
</script>

<div class="space-y-4">
	<div class="rounded-md bg-[var(--color-accent-muted)] p-3">
		<p class="text-sm text-[var(--color-accent)]">
			<strong>Cross Branch:</strong> Four-way fitting with perpendicular branches. Used for complex
			flow distribution.
		</p>
	</div>

	<!-- Visual diagram -->
	<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-4">
		<div class="flex items-center justify-center">
			<svg viewBox="0 0 100 100" class="h-20 w-20">
				<!-- Run line (horizontal) -->
				<line x1="10" y1="50" x2="90" y2="50" stroke="currentColor" stroke-width="4" />
				<!-- Branch lines (vertical) -->
				<line x1="50" y1="10" x2="50" y2="90" stroke="currentColor" stroke-width="4" />
				<!-- Port labels -->
				<text x="10" y="45" class="fill-current text-[7px] opacity-60">In</text>
				<text x="80" y="45" class="fill-current text-[7px] opacity-60">Out</text>
				<text x="55" y="18" class="fill-current text-[7px] opacity-60">Br 1</text>
				<text x="55" y="92" class="fill-current text-[7px] opacity-60">Br 2</text>
				<!-- Flow arrows from center -->
				<polygon points="30,47 20,50 30,53" fill="currentColor" />
				<polygon points="70,47 80,50 70,53" fill="currentColor" />
				<polygon points="47,30 50,20 53,30" fill="currentColor" />
				<polygon points="47,70 50,80 53,70" fill="currentColor" />
			</svg>
		</div>
		<p class="mt-2 text-center text-xs text-[var(--color-text-muted)]">Four-way flow distribution</p>
	</div>

	<NumberInput
		id="elevation"
		label="Elevation"
		value={component.elevation}
		unit="ft"
		onchange={(value) => onUpdate('elevation', value)}
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
		hint="Main line through the cross"
		onchange={updateAllRunPorts}
	/>

	<NumberInput
		id="branch_size"
		label="Branch Size (Both Branches)"
		value={branch1?.nominal_size ?? 4}
		unit="in"
		min={0.5}
		hint="Perpendicular branches"
		onchange={updateAllBranchPorts}
	/>

	<!-- Individual port override if needed -->
	<details class="rounded-md border border-[var(--color-border)]">
		<summary class="cursor-pointer px-3 py-2 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-surface-elevated)]">
			Configure ports individually
		</summary>
		<div class="space-y-3 border-t border-[var(--color-border)] p-3">
			<NumberInput
				id="run_inlet_size"
				label="Run Inlet"
				value={runInlet?.nominal_size ?? 4}
				unit="in"
				min={0.5}
				onchange={(value) => updatePortSize('run_inlet', value)}
			/>
			<NumberInput
				id="run_outlet_size"
				label="Run Outlet"
				value={runOutlet?.nominal_size ?? 4}
				unit="in"
				min={0.5}
				onchange={(value) => updatePortSize('run_outlet', value)}
			/>
			<NumberInput
				id="branch_1_size"
				label="Branch 1"
				value={branch1?.nominal_size ?? 4}
				unit="in"
				min={0.5}
				onchange={(value) => updatePortSize('branch_1', value)}
			/>
			<NumberInput
				id="branch_2_size"
				label="Branch 2"
				value={branch2?.nominal_size ?? 4}
				unit="in"
				min={0.5}
				onchange={(value) => updatePortSize('branch_2', value)}
			/>
		</div>
	</details>
</div>
