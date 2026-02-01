<script lang="ts">
	import { components } from '$lib/stores';
	import {
		COMPONENT_TYPE_LABELS,
		type SolvedState,
		type Port,
		type ComponentType,
		type ComponentResult
	} from '$lib/models';

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
		result: ComponentResult | undefined;
	}

	/**
	 * Get the result for a specific port on a component.
	 * Tries composite key first, then falls back to component-level lookup.
	 */
	function getPortResult(componentId: string, portId: string): ComponentResult | undefined {
		// Try the composite key first (new format: "{component_id}_{port_id}")
		const compositeKey = `${componentId}_${portId}`;
		if (results.component_results[compositeKey]) {
			return results.component_results[compositeKey];
		}

		// Fallback: try the component ID directly (legacy format)
		if (results.component_results[componentId]) {
			return results.component_results[componentId];
		}

		// Final fallback: search for any result with matching component_id and port_id
		return Object.values(results.component_results).find(
			(r) => r.component_id === componentId && r.port_id === portId
		);
	}

	// Get all components with their ports and results
	let portData = $derived.by(() => {
		const rows: PortRow[] = [];

		$components.forEach((component) => {
			const ports = component.ports || [];

			if (ports.length === 0) {
				// Component has no ports defined, show as single row
				const result = getPortResult(component.id, 'default');
				rows.push({
					componentId: component.id,
					componentName: component.name,
					componentType: component.type,
					port: { id: 'P0', name: 'Default', nominal_size: 0, direction: 'bidirectional' },
					isFirstPort: true,
					portCount: 1,
					result
				});
			} else {
				ports.forEach((port, index) => {
					// Look up port-specific result
					const result = getPortResult(component.id, port.id);
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

	function formatNumber(value: number | undefined | null, decimals = 2): string {
		if (value == null) return '-'; // handles both null and undefined
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
	<table class="min-w-full divide-y divide-[var(--color-border)]">
		<thead class="bg-[var(--color-surface-elevated)]">
			<tr>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Component
				</th>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Type
				</th>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Port
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Pressure (psi)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					HGL (ft)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					EGL (ft)
				</th>
			</tr>
		</thead>
		<tbody class="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
			{#each portData as row}
				<tr class="hover:bg-[var(--color-surface-elevated)]">
					{#if row.isFirstPort}
						<td
							class="whitespace-nowrap px-4 py-3 text-sm font-medium text-[var(--color-text)]"
							rowspan={row.portCount}
						>
							{row.componentName}
						</td>
						<td
							class="whitespace-nowrap px-4 py-3 text-sm text-[var(--color-text-muted)]"
							rowspan={row.portCount}
						>
							{COMPONENT_TYPE_LABELS[row.componentType]}
						</td>
					{/if}
					<td class="whitespace-nowrap px-4 py-3 text-sm text-[var(--color-text-muted)]">
						{formatPortName(row.port)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-[var(--color-text)]">
						{formatNumber(row.result?.pressure)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-[var(--color-text)]">
						{formatNumber(row.result?.hgl)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-[var(--color-text)]">
						{formatNumber(row.result?.egl)}
					</td>
				</tr>
			{/each}
			{#if portData.length === 0}
				<tr>
					<td colspan="6" class="px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
						No component results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
