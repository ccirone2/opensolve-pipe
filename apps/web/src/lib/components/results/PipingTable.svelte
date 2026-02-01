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

	function formatNumber(value: number | undefined | null, decimals = 2): string {
		if (value == null) return '-'; // handles both null and undefined
		return value.toFixed(decimals);
	}
</script>

<div class="overflow-x-auto">
	<table class="min-w-full divide-y divide-[var(--color-border)]">
		<thead class="bg-[var(--color-surface-elevated)]">
			<tr>
				<th class="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Piping
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Flow (GPM)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Velocity (ft/s)
				</th>
				<th class="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
					Head Loss (ft)
				</th>
			</tr>
		</thead>
		<tbody class="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
			{#each pipingData as piping}
				<tr class="hover:bg-[var(--color-surface-elevated)]">
					<td class="whitespace-nowrap px-4 py-3 text-sm font-medium text-[var(--color-text)]">
						{piping.name}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-[var(--color-text)]">
						{formatNumber(piping.result?.flow)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-[var(--color-text)]">
						{formatNumber(piping.result?.velocity)}
					</td>
					<td class="whitespace-nowrap px-4 py-3 text-right text-sm text-[var(--color-text)]">
						{formatNumber(piping.result?.head_loss)}
					</td>
				</tr>
			{/each}
			{#if pipingData.length === 0}
				<tr>
					<td colspan="4" class="px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
						No piping results available
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>
