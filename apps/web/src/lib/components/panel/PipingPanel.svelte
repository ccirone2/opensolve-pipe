<script lang="ts">
	import { projectStore } from '$lib/stores';
	import {
		PIPE_MATERIAL_LABELS,
		PIPE_SCHEDULE_LABELS,
		FITTING_TYPE_LABELS,
		FITTING_CATEGORIES,
		createDefaultPipingSegment,
		createDefaultFitting,
		type PipingSegment,
		type FittingType
	} from '$lib/models';

	interface Props {
		/** The component ID this piping belongs to. */
		componentId: string;
		/** The current piping segment (or undefined if none). */
		piping?: PipingSegment;
	}

	let { componentId, piping }: Props = $props();

	let showFittingSelector = $state(false);

	function initializePiping() {
		const newPiping = createDefaultPipingSegment();
		projectStore.updateUpstreamPiping(componentId, newPiping);
	}

	function removePiping() {
		projectStore.updateUpstreamPiping(componentId, undefined);
	}

	function updatePipeField(field: string, value: unknown) {
		if (!piping) return;
		projectStore.updateUpstreamPiping(componentId, {
			...piping,
			pipe: { ...piping.pipe, [field]: value }
		});
	}

	function addFitting(type: FittingType) {
		if (!piping) return;
		const newFitting = createDefaultFitting(type);
		projectStore.updateUpstreamPiping(componentId, {
			...piping,
			fittings: [...piping.fittings, newFitting]
		});
		showFittingSelector = false;
	}

	function updateFitting(index: number, field: string, value: unknown) {
		if (!piping) return;
		const newFittings = [...piping.fittings];
		newFittings[index] = { ...newFittings[index], [field]: value };
		projectStore.updateUpstreamPiping(componentId, {
			...piping,
			fittings: newFittings
		});
	}

	function removeFitting(index: number) {
		if (!piping) return;
		const newFittings = piping.fittings.filter((_, i) => i !== index);
		projectStore.updateUpstreamPiping(componentId, {
			...piping,
			fittings: newFittings
		});
	}

	function handleNumberInput(handler: (value: number) => void, e: Event) {
		const input = e.target as HTMLInputElement;
		const value = parseFloat(input.value);
		if (!isNaN(value)) {
			handler(value);
		}
	}
</script>

<div class="space-y-4">
	{#if !piping}
		<!-- No piping configured -->
		<div class="rounded-lg border-2 border-dashed border-gray-300 p-6 text-center">
			<svg
				class="mx-auto h-12 w-12 text-gray-400"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M12 6v6m0 0v6m0-6h6m-6 0H6"
				/>
			</svg>
			<p class="mt-2 text-sm text-gray-600">No upstream piping configured</p>
			<button
				type="button"
				onclick={initializePiping}
				class="mt-3 inline-flex items-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
			>
				Add Piping
			</button>
		</div>
	{:else}
		<!-- Pipe Configuration -->
		<div class="space-y-3">
			<h4 class="text-sm font-medium text-gray-900">Pipe</h4>

			<div class="grid grid-cols-2 gap-3">
				<div>
					<label for="material" class="block text-xs font-medium text-gray-700">Material</label>
					<select
						id="material"
						value={piping.pipe.material}
						onchange={(e) => updatePipeField('material', (e.target as HTMLSelectElement).value)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						{#each Object.entries(PIPE_MATERIAL_LABELS) as [value, label]}
							<option {value}>{label}</option>
						{/each}
					</select>
				</div>
				<div>
					<label for="schedule" class="block text-xs font-medium text-gray-700">Schedule</label>
					<select
						id="schedule"
						value={piping.pipe.schedule}
						onchange={(e) => updatePipeField('schedule', (e.target as HTMLSelectElement).value)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						{#each Object.entries(PIPE_SCHEDULE_LABELS) as [value, label]}
							<option {value}>{label}</option>
						{/each}
					</select>
				</div>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<div>
					<label for="diameter" class="block text-xs font-medium text-gray-700">Diameter (in)</label>
					<input
						type="number"
						id="diameter"
						value={piping.pipe.nominal_diameter}
						min="0"
						step="0.5"
						oninput={(e) => handleNumberInput((v) => updatePipeField('nominal_diameter', v), e)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>
				<div>
					<label for="length" class="block text-xs font-medium text-gray-700">Length (ft)</label>
					<input
						type="number"
						id="length"
						value={piping.pipe.length}
						min="0"
						oninput={(e) => handleNumberInput((v) => updatePipeField('length', v), e)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>
			</div>
		</div>

		<!-- Fittings List -->
		<div class="border-t border-gray-200 pt-4">
			<div class="flex items-center justify-between">
				<h4 class="text-sm font-medium text-gray-900">Fittings</h4>
				<div class="relative">
					<button
						type="button"
						onclick={() => (showFittingSelector = !showFittingSelector)}
						class="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
						</svg>
						Add
					</button>

					<!-- Fitting Selector Dropdown -->
					{#if showFittingSelector}
						<button
							type="button"
							class="fixed inset-0 z-40"
							onclick={() => (showFittingSelector = false)}
							aria-label="Close menu"
						></button>
						<div class="absolute right-0 z-50 mt-2 w-64 rounded-lg border border-gray-200 bg-white shadow-lg">
							<div class="max-h-64 overflow-y-auto p-2">
								{#each Object.entries(FITTING_CATEGORIES) as [category, types]}
									<div class="py-1">
										<p class="px-2 text-xs font-medium uppercase tracking-wide text-gray-500">
											{category}
										</p>
										{#each types as type}
											<button
												type="button"
												onclick={() => addFitting(type)}
												class="block w-full px-2 py-1 text-left text-sm text-gray-700 hover:bg-gray-100"
											>
												{FITTING_TYPE_LABELS[type]}
											</button>
										{/each}
									</div>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			</div>

			{#if piping.fittings.length === 0}
				<p class="mt-2 text-sm text-gray-500">No fittings added</p>
			{:else}
				<ul class="mt-2 space-y-2">
					{#each piping.fittings as fitting, index}
						<li class="flex items-center gap-2 rounded-md border border-gray-200 p-2">
							<div class="flex-1">
								<p class="text-sm font-medium text-gray-900">
									{FITTING_TYPE_LABELS[fitting.type]}
								</p>
								<div class="mt-1 flex items-center gap-2">
									<label for="qty-{index}" class="text-xs text-gray-500">Qty:</label>
									<input
										type="number"
										id="qty-{index}"
										value={fitting.quantity}
										min="1"
										onchange={(e) =>
											updateFitting(index, 'quantity', parseInt((e.target as HTMLInputElement).value))}
										class="w-16 rounded border border-gray-300 px-2 py-0.5 text-sm"
									/>
									{#if fitting.k_factor_override !== undefined}
										<span class="text-xs text-gray-500">K={fitting.k_factor_override}</span>
									{/if}
								</div>
							</div>
							<button
								type="button"
								onclick={() => removeFitting(index)}
								class="text-gray-400 hover:text-red-500"
								aria-label="Remove fitting"
							>
								<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M6 18L18 6M6 6l12 12"
									/>
								</svg>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		<!-- Remove Piping Button -->
		<div class="border-t border-gray-200 pt-4">
			<button
				type="button"
				onclick={removePiping}
				class="text-sm text-red-600 hover:text-red-700 hover:underline"
			>
				Remove piping
			</button>
		</div>
	{/if}
</div>
