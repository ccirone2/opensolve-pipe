<script lang="ts">
	import { components } from '$lib/stores';
	import { COMPONENT_TYPE_LABELS, type SolvedState } from '$lib/models';

	interface Props {
		/** The solved state containing results. */
		results: SolvedState;
	}

	let { results }: Props = $props();

	// Get all components with their results
	let componentData = $derived.by(() => {
		return $components.map((component) => {
			const result = results.component_results[component.id];
			return {
				id: component.id,
				name: component.name,
				type: component.type,
				elevation: component.elevation,
				result
			};
		});
	});

	function formatNumber(value: number | undefined, decimals = 2): string {
		if (value === undefined) return '-';
		return value.toFixed(decimals);
	}
</script>

<div class="overflow-x-auto">
	<table class="min-w-full divide-y divide-gray-200">
		<thead class="bg-gray-50">
			<tr>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
					Component
				</th>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
					Type
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
					Pressure (psi)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
					HGL (ft)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
					EGL (ft)
				</th>
			</tr>
		</thead>
		<tbody class="divide-y divide-gray-200 bg-white">
			{#each componentData as component}
				<tr class="hover:bg-gray-50">
					<td class="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
						{component.name}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
						{COMPONENT_TYPE_LABELS[component.type]}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(component.result?.pressure)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(component.result?.hgl)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(component.result?.egl)}
					</td>
				</tr>
			{/each}
			{#if componentData.length === 0}
				<tr>
					<td colspan="5" class="px-4 py-8 text-center text-sm text-gray-500">
						No component results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
