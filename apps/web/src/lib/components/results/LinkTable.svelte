<script lang="ts">
	import { components } from '$lib/stores';
	import { COMPONENT_TYPE_LABELS, FLOW_REGIME_LABELS, type SolvedState, type ComponentType } from '$lib/models';

	interface Props {
		/** The solved state containing results. */
		results: SolvedState;
	}

	let { results }: Props = $props();

	interface LinkData {
		id: string;
		name: string;
		type: string;
		result: typeof results.link_results[string] | undefined;
	}

	// Get links with their results
	let linkData = $derived.by(() => {
		const data: LinkData[] = [];

		// Add component links (pumps, valves, etc.)
		const linkComponents = $components.filter((c) =>
			['pump', 'valve', 'heat_exchanger', 'strainer'].includes(c.type)
		);

		linkComponents.forEach((comp) => {
			data.push({
				id: comp.id,
				name: comp.name,
				type: comp.type,
				result: results.link_results[comp.id]
			});
		});

		// Add piping segments from components with upstream_piping
		$components.forEach((comp) => {
			if (comp.upstream_piping) {
				const pipeId = `pipe_${comp.id}`;
				data.push({
					id: pipeId,
					name: `Pipe to ${comp.name}`,
					type: 'pipe',
					result: results.link_results[pipeId] || results.link_results[comp.id]
				});
			}
		});

		return data;
	});

	function formatNumber(value: number | undefined, decimals = 2): string {
		if (value === undefined) return '-';
		return value.toFixed(decimals);
	}

	function formatScientific(value: number | undefined): string {
		if (value === undefined) return '-';
		if (value >= 10000 || value < 0.01) {
			return value.toExponential(2);
		}
		return value.toFixed(0);
	}
</script>

<div class="overflow-x-auto">
	<table class="min-w-full divide-y divide-gray-200">
		<thead class="bg-gray-50">
			<tr>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
					Link
				</th>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
					Type
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
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
					Reynolds
				</th>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
					Regime
				</th>
			</tr>
		</thead>
		<tbody class="divide-y divide-gray-200 bg-white">
			{#each linkData as link}
				<tr class="hover:bg-gray-50">
					<td class="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
						{link.name}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
						{link.type === 'pipe' ? 'Pipe' : COMPONENT_TYPE_LABELS[link.type as ComponentType] ?? link.type}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(link.result?.flow)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(link.result?.velocity)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(link.result?.head_loss)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatScientific(link.result?.reynolds_number)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
						{#if link.result?.regime}
							<span
								class="inline-flex rounded-full px-2 py-0.5 text-xs font-medium
									{link.result.regime === 'laminar'
									? 'bg-green-100 text-green-800'
									: link.result.regime === 'transitional'
										? 'bg-yellow-100 text-yellow-800'
										: 'bg-blue-100 text-blue-800'}"
							>
								{FLOW_REGIME_LABELS[link.result.regime]}
							</span>
						{:else}
							-
						{/if}
					</td>
				</tr>
			{/each}
			{#if linkData.length === 0}
				<tr>
					<td colspan="7" class="px-4 py-8 text-center text-sm text-gray-500">
						No link results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
