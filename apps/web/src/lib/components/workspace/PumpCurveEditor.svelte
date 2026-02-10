<script lang="ts">
	import type { PumpCurve, FlowHeadPoint } from '$lib/models';

	interface Props {
		curve: PumpCurve;
		onSave: (curve: PumpCurve) => void;
		onCancel: () => void;
	}

	let { curve, onSave, onCancel }: Props = $props();

	// Local editable copy - intentionally captures initial value
	// svelte-ignore state_referenced_locally
	let name = $state(curve.name);
	// svelte-ignore state_referenced_locally
	let manufacturer = $state(curve.manufacturer ?? '');
	// svelte-ignore state_referenced_locally
	let model = $state(curve.model ?? '');
	// svelte-ignore state_referenced_locally
	let points = $state<FlowHeadPoint[]>(curve.points.map((p) => ({ ...p })));
	let error = $state<string | null>(null);

	function addPoint() {
		const lastPoint = points[points.length - 1];
		const newFlow = lastPoint ? lastPoint.flow + 50 : 0;
		const newHead = lastPoint ? Math.max(0, lastPoint.head - 10) : 100;
		points = [...points, { flow: newFlow, head: newHead }];
	}

	function removePoint(index: number) {
		if (points.length <= 2) {
			error = 'Minimum 2 data points required';
			return;
		}
		points = points.filter((_, i) => i !== index);
		error = null;
	}

	function updatePoint(index: number, field: 'flow' | 'head', value: number) {
		points = points.map((p, i) => (i === index ? { ...p, [field]: value } : p));
	}

	function handleSave() {
		if (!name.trim()) {
			error = 'Name is required';
			return;
		}
		if (points.length < 2) {
			error = 'Minimum 2 data points required';
			return;
		}

		// Sort points by flow
		const sorted = [...points].sort((a, b) => a.flow - b.flow);

		// Check for negative values
		for (const p of sorted) {
			if (p.flow < 0 || p.head < 0) {
				error = 'Flow and head values must be non-negative';
				return;
			}
		}

		error = null;
		onSave({
			...curve,
			name: name.trim(),
			manufacturer: manufacturer.trim() || undefined,
			model: model.trim() || undefined,
			points: sorted
		});
	}
</script>

<div class="flex flex-col gap-3 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
	<!-- Name -->
	<div>
		<label class="mb-1 block text-[0.6875rem] font-medium text-[var(--color-text-muted)]">
			Name
			<input
				type="text"
				bind:value={name}
				class="form-input"
				placeholder="Pump curve name"
			/>
		</label>
	</div>

	<!-- Manufacturer / Model (inline) -->
	<div class="grid grid-cols-2 gap-2">
		<label class="block text-[0.6875rem] font-medium text-[var(--color-text-muted)]">
			Manufacturer
			<input
				type="text"
				bind:value={manufacturer}
				class="form-input mt-1"
				placeholder="Optional"
			/>
		</label>
		<label class="block text-[0.6875rem] font-medium text-[var(--color-text-muted)]">
			Model
			<input
				type="text"
				bind:value={model}
				class="form-input mt-1"
				placeholder="Optional"
			/>
		</label>
	</div>

	<!-- Data Points -->
	<div>
		<div class="mb-1 flex items-center justify-between">
			<span class="text-[0.6875rem] font-medium text-[var(--color-text-muted)]">
				Curve Points ({points.length})
			</span>
			<button
				type="button"
				onclick={addPoint}
				class="rounded px-1.5 py-0.5 text-[0.625rem] font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-muted)]"
			>
				+ Add Point
			</button>
		</div>

		<!-- Header -->
		<div class="grid grid-cols-[1fr_1fr_2rem] gap-1 text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-text-subtle)]">
			<span class="px-1">Flow</span>
			<span class="px-1">Head</span>
			<span></span>
		</div>

		<!-- Points -->
		<div class="flex max-h-48 flex-col gap-0.5 overflow-y-auto">
			{#each points as point, i}
				<div class="grid grid-cols-[1fr_1fr_2rem] gap-1">
					<input
						type="number"
						value={point.flow}
						oninput={(e) => updatePoint(i, 'flow', parseFloat(e.currentTarget.value) || 0)}
						class="form-input mono-value text-xs"
						min="0"
						step="any"
						aria-label="Flow point {i + 1}"
					/>
					<input
						type="number"
						value={point.head}
						oninput={(e) => updatePoint(i, 'head', parseFloat(e.currentTarget.value) || 0)}
						class="form-input mono-value text-xs"
						min="0"
						step="any"
						aria-label="Head point {i + 1}"
					/>
					<button
						type="button"
						onclick={() => removePoint(i)}
						class="flex h-full items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:text-[var(--color-error)]"
						title="Remove point"
					>
						<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
			{/each}
		</div>
	</div>

	<!-- Error -->
	{#if error}
		<p class="text-[0.6875rem] text-[var(--color-error)]">{error}</p>
	{/if}

	<!-- Actions -->
	<div class="flex items-center justify-end gap-2">
		<button
			type="button"
			onclick={onCancel}
			class="rounded border border-[var(--color-border)] px-3 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)]"
		>
			Cancel
		</button>
		<button
			type="button"
			onclick={handleSave}
			class="rounded bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-[var(--color-accent-text)] transition-colors hover:opacity-90"
		>
			Save
		</button>
	</div>
</div>
