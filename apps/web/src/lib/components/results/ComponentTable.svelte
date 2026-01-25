<script lang="ts">
	import { components } from '$lib/stores';
	import { COMPONENT_TYPE_LABELS, type SolvedState, type Port, type ComponentType } from '$lib/models';

	interface Props {
		/** The solved state containing results. */
		results: SolvedState;
	}

	let { results }: Props = $props();

	interface PortRow {
		componentId: string;
		componentName: string;
		componentType: ComponentType;
		port: Port;
		isFirstPort: boolean;
		portCount: number;
		result: typeof results.component_results[string] | undefined;
	}

	// Get all components with their ports and results
	let portData = $derived.by(() => {
		const rows: PortRow[] = [];

		$components.forEach((component) => {
			const result = results.component_results[component.id];
			const ports = component.ports || [];

			if (ports.length === 0) {
				// Component has no ports defined, show as single row
				rows.push({
					componentId: component.id,
					componentName: component.name,
					componentType: component.type,
					port: { id: 'default', nominal_size: 0, direction: 'bidirectional' },
					isFirstPort: true,
					portCount: 1,
					result
				});
			} else {
				ports.forEach((port, index) => {
					rows.push({
						componentId: component.id,
						componentName: component.name,
						componentType: component.type,
						port,
						isFirstPort: index === 0,
						portCount: ports.length,
						result
					});
				});
			}
		});

		return rows;
	});

	function formatNumber(value: number | undefined, decimals = 2): string {
		if (value === undefined) return '-';
		return value.toFixed(decimals);
	}

	function formatPortName(port: Port): string {
		const dirMap: Record<string, string> = {
			inlet: 'In',
			outlet: 'Out',
			bidirectional: ''
		};
		const dir = dirMap[port.direction] || '';
		return dir ? `${port.id} (${dir})` : port.id;
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
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
					Port
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
			{#each portData as row}
				<tr class="hover:bg-gray-50">
					{#if row.isFirstPort}
						<td
							class="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900"
							rowspan={row.portCount}
						>
							{row.componentName}
						</td>
						<td
							class="whitespace-nowrap px-4 py-3 text-sm text-gray-500"
							rowspan={row.portCount}
						>
							{COMPONENT_TYPE_LABELS[row.componentType]}
						</td>
					{/if}
					<td class="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
						{formatPortName(row.port)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(row.result?.pressure)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(row.result?.hgl)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-900">
						{formatNumber(row.result?.egl)}
					</td>
				</tr>
			{/each}
			{#if portData.length === 0}
				<tr>
					<td colspan="6" class="px-4 py-8 text-center text-sm text-gray-500">
						No component results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
