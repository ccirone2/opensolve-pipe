<script lang="ts">
	import type { Tank } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The tank component to edit. */
		component: Tank;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();

	// Get the first port for port elevation editing
	const port = $derived(component.ports[0]);

	function updatePortElevation(value: number) {
		const newPorts = component.ports.map((p) =>
			p.id === port.id ? { ...p, elevation: value } : p
		);
		onUpdate('ports', newPorts);
	}
</script>

<div class="space-y-4">
	<!-- Tank Geometry -->
	<div class="space-y-1">
		<span class="text-[0.625rem] font-medium uppercase tracking-wider text-[var(--color-text-subtle)]">
			Geometry
		</span>
		<NumberInput
			id="elevation"
			label="Base Elevation"
			value={component.elevation}
			unit="ft"
			onchange={(value) => onUpdate('elevation', value)}
		/>
		<NumberInput
			id="diameter"
			label="Diameter"
			value={component.diameter}
			unit="ft"
			min={0}
			required
			onchange={(value) => onUpdate('diameter', value)}
		/>
		{#if port}
			<NumberInput
				id="port_elevation"
				label="Port Height (from base)"
				value={port.elevation ?? 0}
				unit="ft"
				min={0}
				onchange={updatePortElevation}
			/>
		{/if}
	</div>

	<!-- Water Levels -->
	<div class="space-y-1">
		<span class="text-[0.625rem] font-medium uppercase tracking-wider text-[var(--color-text-subtle)]">
			Water Level
		</span>
		<div class="grid grid-cols-3 gap-3">
			<NumberInput
				id="min_level"
				label="Min"
				value={component.min_level}
				unit="ft"
				min={0}
				required
				onchange={(value) => onUpdate('min_level', value)}
			/>
			<NumberInput
				id="max_level"
				label="Max"
				value={component.max_level}
				unit="ft"
				min={0}
				required
				onchange={(value) => onUpdate('max_level', value)}
			/>
			<NumberInput
				id="initial_level"
				label="Initial"
				value={component.initial_level}
				unit="ft"
				min={0}
				required
				onchange={(value) => onUpdate('initial_level', value)}
			/>
		</div>
	</div>

	<!-- Pressure -->
	<div class="space-y-1">
		<span class="text-[0.625rem] font-medium uppercase tracking-wider text-[var(--color-text-subtle)]">
			Pressure
		</span>
		<NumberInput
			id="surface_pressure"
			label="Surface Pressure"
			value={component.surface_pressure}
			unit="psig"
			onchange={(value) => onUpdate('surface_pressure', value)}
		/>
	</div>
</div>
