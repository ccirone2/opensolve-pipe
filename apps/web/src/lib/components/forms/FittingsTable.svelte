<script lang="ts">
	import type { Fitting, FittingType } from '$lib/models';
	import { FITTING_TYPE_LABELS, FITTING_CATEGORIES, createDefaultFitting } from '$lib/models';

	interface Props {
		/** Current list of fittings. */
		fittings: Fitting[];
		/** Callback when fittings change. */
		onUpdate: (fittings: Fitting[]) => void;
	}

	let { fittings, onUpdate }: Props = $props();

	let showSelector = $state(false);

	function addFitting(type: FittingType) {
		const newFitting = createDefaultFitting(type);
		onUpdate([...fittings, newFitting]);
		showSelector = false;
	}

	function updateFitting(index: number, field: keyof Fitting, value: unknown) {
		const newFittings = [...fittings];
		newFittings[index] = { ...newFittings[index], [field]: value };
		onUpdate(newFittings);
	}

	function removeFitting(index: number) {
		onUpdate(fittings.filter((_, i) => i !== index));
	}

	function duplicateFitting(index: number) {
		const newFitting = { ...fittings[index], id: crypto.randomUUID() };
		const newFittings = [...fittings];
		newFittings.splice(index + 1, 0, newFitting);
		onUpdate(newFittings);
	}
</script>

<div class="space-y-3">
	<div class="flex items-center justify-between">
		<h4 class="text-sm font-medium text-[var(--color-text)]">Fittings</h4>
		<div class="relative">
			<button
				type="button"
				onclick={() => (showSelector = !showSelector)}
				class="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-accent)] hover:opacity-80"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
				</svg>
				Add Fitting
			</button>

			<!-- Fitting Selector Dropdown -->
			{#if showSelector}
				<button
					type="button"
					class="fixed inset-0 z-40"
					onclick={() => (showSelector = false)}
					aria-label="Close menu"
				></button>
				<div class="absolute right-0 z-50 mt-2 w-64 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg">
					<div class="max-h-64 overflow-y-auto p-2">
						{#each Object.entries(FITTING_CATEGORIES) as [category, types]}
							<div class="py-1">
								<p class="px-2 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
									{category}
								</p>
								{#each types as type}
									<button
										type="button"
										onclick={() => addFitting(type)}
										class="block w-full px-2 py-1.5 text-left text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-elevated)] rounded"
									>
										{FITTING_TYPE_LABELS[type]}
									</button>
								{/each}
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	</div>

	{#if fittings.length === 0}
		<p class="text-sm text-[var(--color-text-muted)] italic">No fittings added</p>
	{:else}
		<div class="overflow-hidden rounded-md border border-[var(--color-border)]">
			<table class="min-w-full divide-y divide-[var(--color-border)]">
				<thead class="bg-[var(--color-surface-elevated)]">
					<tr>
						<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
							Type
						</th>
						<th class="w-20 px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
							Qty
						</th>
						<th class="w-24 px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
							K-Factor
						</th>
						<th class="w-20 px-3 py-2"></th>
					</tr>
				</thead>
				<tbody class="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
					{#each fittings as fitting, index}
						<tr>
							<td class="px-3 py-2">
								<span class="text-sm text-[var(--color-text)]">{FITTING_TYPE_LABELS[fitting.type]}</span>
							</td>
							<td class="px-3 py-2">
								<input
									type="number"
									value={fitting.quantity}
									min={1}
									max={99}
									onchange={(e) => updateFitting(index, 'quantity', parseInt((e.target as HTMLInputElement).value) || 1)}
									aria-label="Quantity for {FITTING_TYPE_LABELS[fitting.type]}"
									class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
								/>
							</td>
							<td class="px-3 py-2">
								<input
									type="number"
									value={fitting.k_factor_override ?? ''}
									placeholder="auto"
									min={0}
									step={0.1}
									onchange={(e) => {
										const val = (e.target as HTMLInputElement).value;
										updateFitting(index, 'k_factor_override', val ? parseFloat(val) : undefined);
									}}
									aria-label="K-factor for {FITTING_TYPE_LABELS[fitting.type]}"
									class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
								/>
							</td>
							<td class="px-3 py-2">
								<div class="flex gap-1">
									<button
										type="button"
										onclick={() => duplicateFitting(index)}
										class="text-[var(--color-text-subtle)] hover:text-[var(--color-text)]"
										title="Duplicate"
									>
										<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
										</svg>
									</button>
									<button
										type="button"
										onclick={() => removeFitting(index)}
										class="text-[var(--color-text-subtle)] hover:text-[var(--color-error)]"
										title="Remove"
									>
										<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
										</svg>
									</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="text-xs text-[var(--color-text-muted)]">
			K-Factor: Leave blank to use standard values based on diameter
		</p>
	{/if}
</div>
