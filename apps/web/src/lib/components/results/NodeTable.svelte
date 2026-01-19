<script lang="ts">
	import { components } from '$lib/stores';
	import { COMPONENT_TYPE_LABELS, type SolvedState } from '$lib/models';

	interface Props {
		/** The solved state containing results. */
		results: SolvedState;
	}

	let { results }: Props = $props();

	// Get nodes with their results
	let nodeData = $derived.by(() => {
		const nodes = $components.filter((c) =>
			['reservoir', 'tank', 'junction', 'sprinkler', 'orifice'].includes(c.type)
		);

		return nodes.map((node) => {
			const result = results.node_results[node.id];
			return {
				id: node.id,
				name: node.name,
				type: node.type,
				elevation: node.elevation,
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
					Node
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
			{#each nodeData as node}
				<tr class="hover:bg-gray-50">
					<td class="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
						{node.name}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
						{COMPONENT_TYPE_LABELS[node.type]}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(node.result?.pressure)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(node.result?.hgl)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(node.result?.egl)}
					</td>
				</tr>
			{/each}
			{#if nodeData.length === 0}
				<tr>
					<td colspan="5" class="px-4 py-8 text-center text-sm text-gray-500">
						No node results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
