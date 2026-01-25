<script lang="ts">
	import { components, connections } from '$lib/stores';
	import type { SolvedState } from '$lib/models';

	interface Props {
		/** The solved state containing results. */
		results: SolvedState;
	}

	let { results }: Props = $props();

	interface PipingData {
		id: string;
		name: string;
		type: string;
		result: typeof results.piping_results[string] | undefined;
	}

	// Build a map of component IDs to names for display
	let componentNames = $derived.by(() => {
		const names: Record<string, string> = {};
		$components.forEach((comp) => {
			names[comp.id] = comp.name;
		});
		return names;
	});

	// Get piping segments with their results using connections
	let pipingData = $derived.by(() => {
		const data: PipingData[] = [];

		// Use the connections array which has the proper IDs that match piping_results
		$connections.forEach((conn) => {
			if (conn.piping) {
				const fromName = componentNames[conn.from_component_id] || conn.from_component_id;
				const toName = componentNames[conn.to_component_id] || conn.to_component_id;
				data.push({
					id: conn.id,
					name: `${fromName} → ${toName}`,
					type: 'pipe',
					result: results.piping_results[conn.id]
				});
			}
		});

		return data;
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
					Piping
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
					Flow (GPM)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
					Velocity (ft/s)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
					Head Loss (ft)
				</th>
			</tr>
		</thead>
		<tbody class="divide-y divide-gray-200 bg-white">
			{#each pipingData as piping}
				<tr class="hover:bg-gray-50">
					<td class="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
						{piping.name}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(piping.result?.flow)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(piping.result?.velocity)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(piping.result?.head_loss)}
					</td>
				</tr>
			{/each}
			{#if pipingData.length === 0}
				<tr>
					<td colspan="4" class="px-4 py-8 text-center text-sm text-gray-500">
						No piping results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
