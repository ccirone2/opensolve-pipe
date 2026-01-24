<script lang="ts">
	import type { IdealReferenceNode, NonIdealReferenceNode, FlowPressurePoint } from '$lib/models';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The reference node component to edit (ideal or non-ideal). */
		component: IdealReferenceNode | NonIdealReferenceNode;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();

	// Check if this is an ideal or non-ideal reference node
	const isIdeal = $derived(component.type === 'ideal_reference_node');

	// For non-ideal nodes, get the curve data
	const curvePoints = $derived(
		component.type === 'non_ideal_reference_node' ? component.pressure_flow_curve : []
	);

	// Validate curve: must be sorted by flow
	const curveError = $derived(() => {
		if (component.type !== 'non_ideal_reference_node') return '';
		const curve = component.pressure_flow_curve;
		if (curve.length < 2) return 'Curve must have at least 2 points';
		for (let i = 1; i < curve.length; i++) {
			if (curve[i].flow <= curve[i - 1].flow) {
				return 'Flow values must be in ascending order';
			}
		}
		return '';
	});

	function addCurvePoint() {
		if (component.type !== 'non_ideal_reference_node') return;
		const curve = component.pressure_flow_curve;
		const lastPoint = curve[curve.length - 1];
		const newPoint: FlowPressurePoint = {
			flow: lastPoint ? lastPoint.flow + 50 : 0,
			pressure: lastPoint ? lastPoint.pressure - 5 : 60
		};
		onUpdate('pressure_flow_curve', [...curve, newPoint]);
	}

	function updateCurvePoint(index: number, field: 'flow' | 'pressure', value: number) {
		if (component.type !== 'non_ideal_reference_node') return;
		const newCurve = [...component.pressure_flow_curve];
		newCurve[index] = { ...newCurve[index], [field]: value };
		onUpdate('pressure_flow_curve', newCurve);
	}

	function removeCurvePoint(index: number) {
		if (component.type !== 'non_ideal_reference_node') return;
		const newCurve = component.pressure_flow_curve.filter((_, i) => i !== index);
		onUpdate('pressure_flow_curve', newCurve);
	}

	function updatePortSize(size: number) {
		if (component.ports.length > 0) {
			const newPorts = [...component.ports];
			newPorts[0] = { ...newPorts[0], nominal_size: size };
			onUpdate('ports', newPorts);
		}
	}
</script>

<div class="space-y-4">
	<NumberInput
		id="elevation"
		label="Elevation"
		value={component.elevation}
		unit="ft"
		onchange={(value) => onUpdate('elevation', value)}
	/>

	<NumberInput
		id="port_size"
		label="Port Size"
		value={component.ports[0]?.nominal_size ?? 4}
		unit="in"
		min={0.5}
		hint="Nominal pipe size for connections"
		onchange={updatePortSize}
	/>

	{#if isIdeal}
		<!-- Ideal Reference Node: Fixed Pressure -->
		<div class="rounded-md bg-blue-50 p-3">
			<p class="text-sm text-blue-800">
				<strong>Ideal Reference Node:</strong> Maintains constant pressure regardless of flow.
			</p>
		</div>

		<NumberInput
			id="pressure"
			label="Fixed Pressure"
			value={(component as IdealReferenceNode).pressure}
			unit="psi"
			hint="Constant pressure maintained at this boundary"
			onchange={(value) => onUpdate('pressure', value)}
		/>
	{:else}
		<!-- Non-Ideal Reference Node: Pressure-Flow Curve -->
		<div class="rounded-md bg-amber-50 p-3">
			<p class="text-sm text-amber-800">
				<strong>Non-Ideal Reference Node:</strong> Pressure varies with flow rate.
			</p>
		</div>

		<div class="space-y-2">
			<div class="flex items-center justify-between">
				<span class="block text-sm font-medium text-gray-700">Pressure-Flow Curve</span>
				<button
					type="button"
					onclick={addCurvePoint}
					class="inline-flex items-center rounded-md bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700"
				>
					Add Point
				</button>
			</div>

			{#if curveError()}
				<p class="text-xs text-red-600">{curveError()}</p>
			{/if}

			<div class="overflow-x-auto">
				<table class="min-w-full divide-y divide-gray-200 text-sm">
					<thead class="bg-gray-50">
						<tr>
							<th class="px-3 py-2 text-left font-medium text-gray-500">Flow (GPM)</th>
							<th class="px-3 py-2 text-left font-medium text-gray-500">Pressure (psi)</th>
							<th class="px-3 py-2 text-left font-medium text-gray-500"></th>
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-200">
						{#each curvePoints as point, index}
							<tr>
								<td class="px-1 py-1">
									<input
										type="number"
										value={point.flow}
										min={0}
										step="any"
										class="w-20 rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
										oninput={(e) =>
											updateCurvePoint(index, 'flow', parseFloat(e.currentTarget.value))}
									/>
								</td>
								<td class="px-1 py-1">
									<input
										type="number"
										value={point.pressure}
										step="any"
										class="w-20 rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
										oninput={(e) =>
											updateCurvePoint(index, 'pressure', parseFloat(e.currentTarget.value))}
									/>
								</td>
								<td class="px-1 py-1">
									{#if curvePoints.length > 2}
										<button
											type="button"
											onclick={() => removeCurvePoint(index)}
											class="text-red-600 hover:text-red-800"
											title="Remove point"
										>
											<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M6 18L18 6M6 6l12 12"
												/>
											</svg>
										</button>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<p class="text-xs text-gray-500">
				Enter flow-pressure pairs in ascending flow order. Pressure will be interpolated between
				points.
			</p>
		</div>

		<NumberInput
			id="max_flow"
			label="Maximum Flow (optional)"
			value={(component as NonIdealReferenceNode).max_flow}
			unit="GPM"
			min={0}
			hint="Flow capacity limit for validation"
			onchange={(value) => onUpdate('max_flow', value)}
		/>
	{/if}
</div>
