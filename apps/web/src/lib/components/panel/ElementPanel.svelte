<script lang="ts">
	import { projectStore, pumpLibrary } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		VALVE_TYPE_LABELS,
		isReservoir,
		isTank,
		isJunction,
		isPump,
		isValve,
		isHeatExchanger,
		isStrainer,
		isOrifice,
		isSprinkler,
		type Component
	} from '$lib/models';

	interface Props {
		/** The component to display/edit. */
		component: Component;
	}

	let { component }: Props = $props();

	function updateField(field: string, value: unknown) {
		projectStore.updateComponent(component.id, { [field]: value });
	}

	function handleNumberInput(field: string, e: Event) {
		const input = e.target as HTMLInputElement;
		const value = parseFloat(input.value);
		if (!isNaN(value)) {
			updateField(field, value);
		}
	}

	function handleTextInput(field: string, e: Event) {
		const input = e.target as HTMLInputElement;
		updateField(field, input.value);
	}

	function handleSelectInput(field: string, e: Event) {
		const select = e.target as HTMLSelectElement;
		updateField(field, select.value);
	}
</script>

<div class="space-y-4">
	<!-- Component Header -->
	<div class="border-b border-gray-200 pb-3">
		<span class="text-xs font-medium uppercase tracking-wide text-gray-500">
			{COMPONENT_TYPE_LABELS[component.type]}
		</span>
	</div>

	<!-- Common Fields -->
	<div class="space-y-3">
		<div>
			<label for="name" class="block text-sm font-medium text-gray-700">Name</label>
			<input
				type="text"
				id="name"
				value={component.name}
				oninput={(e) => handleTextInput('name', e)}
				class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
			/>
		</div>

		<div>
			<label for="elevation" class="block text-sm font-medium text-gray-700">Elevation</label>
			<div class="mt-1 flex rounded-md shadow-sm">
				<input
					type="number"
					id="elevation"
					value={component.elevation}
					oninput={(e) => handleNumberInput('elevation', e)}
					class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
				<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
					ft
				</span>
			</div>
		</div>
	</div>

	<!-- Type-specific Fields -->
	<div class="border-t border-gray-200 pt-4">
		{#if isReservoir(component)}
			<div>
				<label for="water_level" class="block text-sm font-medium text-gray-700">Water Level</label>
				<div class="mt-1 flex rounded-md shadow-sm">
					<input
						type="number"
						id="water_level"
						value={component.water_level}
						min="0"
						oninput={(e) => handleNumberInput('water_level', e)}
						class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
					<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
						ft
					</span>
				</div>
			</div>
		{:else if isTank(component)}
			<div class="space-y-3">
				<div>
					<label for="diameter" class="block text-sm font-medium text-gray-700">Diameter</label>
					<div class="mt-1 flex rounded-md shadow-sm">
						<input
							type="number"
							id="diameter"
							value={component.diameter}
							min="0"
							oninput={(e) => handleNumberInput('diameter', e)}
							class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
							ft
						</span>
					</div>
				</div>
				<div class="grid grid-cols-3 gap-3">
					<div>
						<label for="min_level" class="block text-sm font-medium text-gray-700">Min Level</label>
						<input
							type="number"
							id="min_level"
							value={component.min_level}
							min="0"
							oninput={(e) => handleNumberInput('min_level', e)}
							class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<div>
						<label for="max_level" class="block text-sm font-medium text-gray-700">Max Level</label>
						<input
							type="number"
							id="max_level"
							value={component.max_level}
							min="0"
							oninput={(e) => handleNumberInput('max_level', e)}
							class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<div>
						<label for="initial_level" class="block text-sm font-medium text-gray-700">Initial</label>
						<input
							type="number"
							id="initial_level"
							value={component.initial_level}
							min="0"
							oninput={(e) => handleNumberInput('initial_level', e)}
							class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
				</div>
			</div>
		{:else if isJunction(component)}
			<div>
				<label for="demand" class="block text-sm font-medium text-gray-700">Demand</label>
				<div class="mt-1 flex rounded-md shadow-sm">
					<input
						type="number"
						id="demand"
						value={component.demand}
						min="0"
						oninput={(e) => handleNumberInput('demand', e)}
						class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
					<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
						GPM
					</span>
				</div>
			</div>
		{:else if isPump(component)}
			<div class="space-y-3">
				<div>
					<label for="curve_id" class="block text-sm font-medium text-gray-700">Pump Curve</label>
					<select
						id="curve_id"
						value={component.curve_id}
						onchange={(e) => handleSelectInput('curve_id', e)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						<option value="">Select a curve...</option>
						{#each $pumpLibrary as curve}
							<option value={curve.id}>{curve.name}</option>
						{/each}
					</select>
				</div>
				<div>
					<label for="speed" class="block text-sm font-medium text-gray-700">Speed</label>
					<div class="mt-1 flex rounded-md shadow-sm">
						<input
							type="number"
							id="speed"
							value={component.speed * 100}
							min="0"
							max="100"
							step="1"
							oninput={(e) => {
								const input = e.target as HTMLInputElement;
								const value = parseFloat(input.value);
								if (!isNaN(value)) {
									updateField('speed', value / 100);
								}
							}}
							class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
							%
						</span>
					</div>
				</div>
				<fieldset>
					<legend class="block text-sm font-medium text-gray-700">Status</legend>
					<div class="mt-2 flex gap-4">
						<label class="flex items-center">
							<input
								type="radio"
								name="status"
								value="on"
								checked={component.status === 'on'}
								onchange={() => updateField('status', 'on')}
								class="h-4 w-4 border-gray-300 text-blue-600 focus:ring-blue-500"
							/>
							<span class="ml-2 text-sm text-gray-700">On</span>
						</label>
						<label class="flex items-center">
							<input
								type="radio"
								name="status"
								value="off"
								checked={component.status === 'off'}
								onchange={() => updateField('status', 'off')}
								class="h-4 w-4 border-gray-300 text-blue-600 focus:ring-blue-500"
							/>
							<span class="ml-2 text-sm text-gray-700">Off</span>
						</label>
					</div>
				</fieldset>
			</div>
		{:else if isValve(component)}
			<div class="space-y-3">
				<div>
					<label for="valve_type" class="block text-sm font-medium text-gray-700">Valve Type</label>
					<select
						id="valve_type"
						value={component.valve_type}
						onchange={(e) => handleSelectInput('valve_type', e)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						{#each Object.entries(VALVE_TYPE_LABELS) as [value, label]}
							<option {value}>{label}</option>
						{/each}
					</select>
				</div>
				<div>
					<label for="position" class="block text-sm font-medium text-gray-700">Position</label>
					<div class="mt-1 flex rounded-md shadow-sm">
						<input
							type="number"
							id="position"
							value={(component.position ?? 1) * 100}
							min="0"
							max="100"
							step="1"
							oninput={(e) => {
								const input = e.target as HTMLInputElement;
								const value = parseFloat(input.value);
								if (!isNaN(value)) {
									updateField('position', value / 100);
								}
							}}
							class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
							%
						</span>
					</div>
					<p class="mt-1 text-xs text-gray-500">0% = fully closed, 100% = fully open</p>
				</div>
			</div>
		{:else if isHeatExchanger(component)}
			<div class="space-y-3">
				<div>
					<label for="pressure_drop" class="block text-sm font-medium text-gray-700">Pressure Drop</label>
					<div class="mt-1 flex rounded-md shadow-sm">
						<input
							type="number"
							id="pressure_drop"
							value={component.pressure_drop}
							min="0"
							oninput={(e) => handleNumberInput('pressure_drop', e)}
							class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
							psi
						</span>
					</div>
				</div>
				<div>
					<label for="design_flow" class="block text-sm font-medium text-gray-700">Design Flow</label>
					<div class="mt-1 flex rounded-md shadow-sm">
						<input
							type="number"
							id="design_flow"
							value={component.design_flow}
							min="0"
							oninput={(e) => handleNumberInput('design_flow', e)}
							class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
							GPM
						</span>
					</div>
				</div>
			</div>
		{:else if isStrainer(component)}
			<div>
				<label for="k_factor" class="block text-sm font-medium text-gray-700">K-Factor</label>
				<input
					type="number"
					id="k_factor"
					value={component.k_factor ?? ''}
					min="0"
					step="0.1"
					oninput={(e) => handleNumberInput('k_factor', e)}
					class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
				/>
			</div>
		{:else if isOrifice(component)}
			<div class="space-y-3">
				<div>
					<label for="orifice_diameter" class="block text-sm font-medium text-gray-700">Orifice Diameter</label>
					<div class="mt-1 flex rounded-md shadow-sm">
						<input
							type="number"
							id="orifice_diameter"
							value={component.orifice_diameter}
							min="0"
							oninput={(e) => handleNumberInput('orifice_diameter', e)}
							class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
							in
						</span>
					</div>
				</div>
				<div>
					<label for="discharge_coefficient" class="block text-sm font-medium text-gray-700">Discharge Coefficient (Cd)</label>
					<input
						type="number"
						id="discharge_coefficient"
						value={component.discharge_coefficient}
						min="0"
						max="1"
						step="0.01"
						oninput={(e) => handleNumberInput('discharge_coefficient', e)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>
			</div>
		{:else if isSprinkler(component)}
			<div class="space-y-3">
				<div>
					<label for="k_factor" class="block text-sm font-medium text-gray-700">K-Factor</label>
					<input
						type="number"
						id="k_factor"
						value={component.k_factor}
						min="0"
						step="0.1"
						oninput={(e) => handleNumberInput('k_factor', e)}
						class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
					<p class="mt-1 text-xs text-gray-500">Q = K × √P</p>
				</div>
				<div>
					<label for="design_pressure" class="block text-sm font-medium text-gray-700">Design Pressure (optional)</label>
					<div class="mt-1 flex rounded-md shadow-sm">
						<input
							type="number"
							id="design_pressure"
							value={component.design_pressure ?? ''}
							min="0"
							oninput={(e) => handleNumberInput('design_pressure', e)}
							class="block w-full rounded-l-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<span class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500">
							psi
						</span>
					</div>
				</div>
			</div>
		{/if}
	</div>

	<!-- Delete Button -->
	<div class="border-t border-gray-200 pt-4">
		<button
			type="button"
			onclick={() => projectStore.removeComponent(component.id)}
			class="text-sm text-red-600 hover:text-red-700 hover:underline"
		>
			Delete this component
		</button>
	</div>
</div>
