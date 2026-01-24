<script lang="ts">
	import type { TeeBranch } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The tee branch component to edit. */
		component: TeeBranch;
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
	<div class="rounded-md bg-blue-50 p-3">
		<p class="text-sm text-blue-800">
			<strong>Tee Branch:</strong> 90° fitting for flow splitting or combining. Run ports are the main
			flow path, branch port is perpendicular.
		</p>
	</div>

	<!-- Visual diagram -->
	<div class="rounded-md border border-gray-200 bg-gray-50 p-4">
		<div class="flex items-center justify-center">
			<svg viewBox="0 0 120 80" class="h-16 w-24">
				<!-- Run line (horizontal) -->
				<line x1="10" y1="40" x2="110" y2="40" stroke="currentColor" stroke-width="4" />
				<!-- Branch line (vertical up) -->
				<line x1="60" y1="40" x2="60" y2="10" stroke="currentColor" stroke-width="4" />
				<!-- Port labels -->
				<text x="15" y="55" class="fill-gray-600 text-[8px]">Run In</text>
				<text x="85" y="55" class="fill-gray-600 text-[8px]">Run Out</text>
				<text x="65" y="20" class="fill-gray-600 text-[8px]">Branch</text>
				<!-- Flow arrows -->
				<polygon points="30,37 40,40 30,43" fill="currentColor" />
				<polygon points="90,37 100,40 90,43" fill="currentColor" />
				<polygon points="57,25 60,15 63,25" fill="currentColor" />
			</svg>
		</div>
		<p class="mt-2 text-center text-xs text-gray-500">Flow direction shown for diverging flow</p>
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
		min={45}
		max={90}
		step={5}
		hint="Standard tee is 90°"
		onchange={(value) => onUpdate('branch_angle', value)}
	/>

	<div class="border-t border-gray-200 pt-4">
		<span class="block text-sm font-medium text-gray-700">Port Sizes</span>
		<p class="mt-1 text-xs text-gray-500">Configure the nominal pipe size for each connection</p>
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
		hint="Can be same size or smaller than run (reducing tee)"
		onchange={(value) => updatePortSize('branch', value)}
	/>

	{#if branch && runInlet && branch.nominal_size > runInlet.nominal_size}
		<div class="rounded-md border border-amber-200 bg-amber-50 p-2">
			<p class="text-xs text-amber-800">
				Branch size larger than run is unusual. Typically branch is same size or smaller.
			</p>
		</div>
	{/if}
</div>
