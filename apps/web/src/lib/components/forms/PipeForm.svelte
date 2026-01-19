<script lang="ts">
	import type { PipeDefinition } from '$lib/models';
	import { PIPE_MATERIAL_LABELS, PIPE_SCHEDULE_LABELS } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The pipe definition to edit. */
		pipe: PipeDefinition;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { pipe, onUpdate }: Props = $props();
</script>

<div class="space-y-4">
	<div class="grid grid-cols-2 gap-3">
		<div>
			<label for="material" class="block text-sm font-medium text-gray-700">Material</label>
			<select
				id="material"
				value={pipe.material}
				onchange={(e) => onUpdate('material', (e.target as HTMLSelectElement).value)}
				class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
			>
				{#each Object.entries(PIPE_MATERIAL_LABELS) as [value, label]}
					<option {value}>{label}</option>
				{/each}
			</select>
		</div>

		<div>
			<label for="schedule" class="block text-sm font-medium text-gray-700">Schedule</label>
			<select
				id="schedule"
				value={pipe.schedule}
				onchange={(e) => onUpdate('schedule', (e.target as HTMLSelectElement).value)}
				class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
			>
				{#each Object.entries(PIPE_SCHEDULE_LABELS) as [value, label]}
					<option {value}>{label}</option>
				{/each}
			</select>
		</div>
	</div>

	<div class="grid grid-cols-2 gap-3">
		<NumberInput
			id="nominal_diameter"
			label="Nominal Diameter"
			value={pipe.nominal_diameter}
			unit="in"
			min={0.125}
			max={48}
			step={0.125}
			required
			onchange={(value) => onUpdate('nominal_diameter', value)}
		/>

		<NumberInput
			id="length"
			label="Length"
			value={pipe.length}
			unit="ft"
			min={0}
			required
			onchange={(value) => onUpdate('length', value)}
		/>
	</div>

	{#if pipe.roughness_override !== undefined}
		<NumberInput
			id="roughness"
			label="Roughness Override"
			value={pipe.roughness_override}
			unit="ft"
			min={0}
			step={0.00001}
			onchange={(value) => onUpdate('roughness_override', value)}
			hint="Leave blank to use material default"
		/>
	{/if}
</div>
