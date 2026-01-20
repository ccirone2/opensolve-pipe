<script lang="ts">
	import { components } from '$lib/stores';
	import { FLOW_REGIME_LABELS, type SolvedState } from '$lib/models';

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

	// Get piping segments with their results
	let pipingData = $derived.by(() => {
		const data: PipingData[] = [];

		// Add piping segments from components with upstream_piping
		$components.forEach((comp) => {
			if (comp.upstream_piping) {
				const pipeId = `pipe_${comp.id}`;
				data.push({
					id: pipeId,
					name: `Pipe to ${comp.name}`,
					type: 'pipe',
					result: results.piping_results[pipeId] || results.piping_results[comp.id]
				});
			}

			// Also check downstream connections for piping
			comp.downstream_connections?.forEach((conn) => {
				if (conn.piping) {
					const pipeId = `pipe_${comp.id}_to_${conn.target_component_id}`;
					data.push({
						id: pipeId,
						name: `Pipe from ${comp.name}`,
						type: 'pipe',
						result: results.piping_results[pipeId]
					});
				}
			});
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
					Piping
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
			{#each pipingData as piping}
				<tr class="hover:bg-gray-50">
					<td class="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
						{piping.name}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
						Pipe
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
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatScientific(piping.result?.reynolds_number)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
						{#if piping.result?.regime}
							<span
								class="inline-flex rounded-full px-2 py-0.5 text-xs font-medium
									{piping.result.regime === 'laminar'
									? 'bg-green-100 text-green-800'
									: piping.result.regime === 'transitional'
										? 'bg-yellow-100 text-yellow-800'
										: 'bg-blue-100 text-blue-800'}"
							>
								{FLOW_REGIME_LABELS[piping.result.regime]}
							</span>
						{:else}
							-
						{/if}
					</td>
				</tr>
			{/each}
			{#if pipingData.length === 0}
				<tr>
					<td colspan="7" class="px-4 py-8 text-center text-sm text-gray-500">
						No piping results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
