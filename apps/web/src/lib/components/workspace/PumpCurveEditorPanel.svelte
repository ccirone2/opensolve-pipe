<script lang="ts">
	import { pumpLibrary, projectStore, workspaceStore } from '$lib/stores';
	import type { PumpCurve, FlowHeadPoint, FlowEfficiencyPoint, NPSHRPoint, FlowPowerPoint, DesignPoint } from '$lib/models';
	import { generatePumpBestFitCurve, generateEfficiencyBestFitCurve, calculateBEP } from '$lib/models';

	interface Props {
		curveId: string;
	}

	let { curveId }: Props = $props();

	// Find the curve from the library
	let sourceCurve = $derived($pumpLibrary.find((c) => c.id === curveId));

	// Local editable state — reset when curveId changes
	let name = $state('');
	let manufacturer = $state('');
	let model = $state('');
	let ratedSpeed = $state<number | null>(null);
	let impellerDiameter = $state<number | null>(null);
	let stages = $state<number | null>(null);
	let minImpellerDiameter = $state<number | null>(null);
	let maxImpellerDiameter = $state<number | null>(null);
	let inletOutlet = $state('');
	let notes = $state('');
	let designPointFlow = $state<number | null>(null);
	let designPointHead = $state<number | null>(null);
	let designPointSpeed = $state<number | null>(null);
	let headPoints = $state<FlowHeadPoint[]>([]);
	let efficiencyPoints = $state<FlowEfficiencyPoint[]>([]);
	let npshPoints = $state<NPSHRPoint[]>([]);
	let powerPoints = $state<FlowPowerPoint[]>([]);

	let isDirty = $state(false);
	let activeTab = $state<'info' | 'data' | 'preview'>('info');
	let activeDataTab = $state<'head' | 'efficiency' | 'npsh' | 'power'>('head');
	let pendingDelete = $state(false);

	// Load curve data when curveId or sourceCurve changes
	$effect(() => {
		if (sourceCurve) {
			loadFromCurve(sourceCurve);
		}
	});

	function loadFromCurve(c: PumpCurve) {
		name = c.name;
		manufacturer = c.manufacturer ?? '';
		model = c.model ?? '';
		ratedSpeed = c.rated_speed ?? null;
		impellerDiameter = c.impeller_diameter ?? null;
		stages = c.stages ?? null;
		minImpellerDiameter = c.min_impeller_diameter ?? null;
		maxImpellerDiameter = c.max_impeller_diameter ?? null;
		inletOutlet = c.inlet_outlet ?? '';
		notes = c.notes ?? '';
		designPointFlow = c.design_point?.flow ?? null;
		designPointHead = c.design_point?.head ?? null;
		designPointSpeed = c.design_point?.speed ?? null;
		headPoints = c.points.map((p) => ({ ...p }));
		efficiencyPoints = (c.efficiency_curve ?? []).map((p) => ({ ...p }));
		npshPoints = (c.npshr_curve ?? []).map((p) => ({ ...p }));
		powerPoints = (c.power_curve ?? []).map((p) => ({ ...p }));
		isDirty = false;
		pendingDelete = false;
	}

	function markDirty() {
		isDirty = true;
	}

	// === Actions ===

	function handleSave() {
		const sorted = [...headPoints].sort((a, b) => a.flow - b.flow);
		const sortedEff = [...efficiencyPoints].sort((a, b) => a.flow - b.flow);
		const sortedNpsh = [...npshPoints].sort((a, b) => a.flow - b.flow);
		const sortedPower = [...powerPoints].sort((a, b) => a.flow - b.flow);

		const dp: DesignPoint | undefined = designPointFlow != null && designPointHead != null
			? { flow: designPointFlow, head: designPointHead, speed: designPointSpeed ?? undefined }
			: undefined;

		projectStore.updatePumpCurve(curveId, {
			name: name.trim() || 'Untitled',
			manufacturer: manufacturer.trim() || undefined,
			model: model.trim() || undefined,
			rated_speed: ratedSpeed ?? undefined,
			impeller_diameter: impellerDiameter ?? undefined,
			min_impeller_diameter: minImpellerDiameter ?? undefined,
			max_impeller_diameter: maxImpellerDiameter ?? undefined,
			stages: stages ?? undefined,
			inlet_outlet: inletOutlet.trim() || undefined,
			notes: notes.trim() || undefined,
			design_point: dp,
			points: sorted.length >= 2 ? sorted : headPoints,
			efficiency_curve: sortedEff.length > 0 ? sortedEff : undefined,
			npshr_curve: sortedNpsh.length > 0 ? sortedNpsh : undefined,
			power_curve: sortedPower.length > 0 ? sortedPower : undefined
		});
		isDirty = false;
	}

	function handleDuplicate() {
		if (!sourceCurve) return;
		const newId = `curve_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
		const copy: PumpCurve = {
			...sourceCurve,
			id: newId,
			name: `${sourceCurve.name} (Copy)`
		};
		projectStore.addPumpCurve(copy);
		workspaceStore.setEditingPumpCurve(newId);
	}

	function handleDelete() {
		if (!pendingDelete) {
			pendingDelete = true;
			return;
		}
		projectStore.removePumpCurve(curveId);
		// Select next curve or close editor
		const remaining = $pumpLibrary.filter((c) => c.id !== curveId);
		if (remaining.length > 0) {
			workspaceStore.setEditingPumpCurve(remaining[0].id);
		} else {
			workspaceStore.setEditingPumpCurve(null);
		}
	}

	function handleClose() {
		workspaceStore.setEditingPumpCurve(null);
	}

	// === Data table helpers ===

	function addHeadPoint() {
		const last = headPoints[headPoints.length - 1];
		headPoints = [...headPoints, { flow: last ? last.flow + 50 : 0, head: last ? Math.max(0, last.head - 10) : 100 }];
		markDirty();
	}

	function removeHeadPoint(i: number) {
		headPoints = headPoints.filter((_, idx) => idx !== i);
		markDirty();
	}

	function addEfficiencyPoint() {
		const last = efficiencyPoints[efficiencyPoints.length - 1];
		efficiencyPoints = [...efficiencyPoints, { flow: last ? last.flow + 50 : 0, efficiency: last ? last.efficiency : 0.7 }];
		markDirty();
	}

	function removeEfficiencyPoint(i: number) {
		efficiencyPoints = efficiencyPoints.filter((_, idx) => idx !== i);
		markDirty();
	}

	function addNpshPoint() {
		const last = npshPoints[npshPoints.length - 1];
		npshPoints = [...npshPoints, { flow: last ? last.flow + 50 : 0, npsh_required: last ? last.npsh_required : 5 }];
		markDirty();
	}

	function removeNpshPoint(i: number) {
		npshPoints = npshPoints.filter((_, idx) => idx !== i);
		markDirty();
	}

	function addPowerPoint() {
		const last = powerPoints[powerPoints.length - 1];
		powerPoints = [...powerPoints, { flow: last ? last.flow + 50 : 0, power: last ? last.power : 10 }];
		markDirty();
	}

	function removePowerPoint(i: number) {
		powerPoints = powerPoints.filter((_, idx) => idx !== i);
		markDirty();
	}

	// === Chart data for preview ===
	let showHeadCurve = $state(true);
	let showEffCurve = $state(true);
	let showPowerCurve = $state(false);

	// Build a temporary PumpCurve for chart utilities
	let previewCurve = $derived<PumpCurve>({
		id: curveId,
		name,
		points: headPoints,
		efficiency_curve: efficiencyPoints.length > 0 ? efficiencyPoints : undefined,
		npshr_curve: npshPoints.length > 0 ? npshPoints : undefined,
		power_curve: powerPoints.length > 0 ? powerPoints : undefined
	});

	let headBestFit = $derived(showHeadCurve ? generatePumpBestFitCurve(previewCurve) : null);
	let effBestFit = $derived(showEffCurve ? generateEfficiencyBestFitCurve(previewCurve) : null);
	let bepData = $derived(calculateBEP(previewCurve));

	// Primary tabs
	const primaryTabs = [
		{ id: 'info' as const, label: 'Pump Information', icon: 'info' },
		{ id: 'data' as const, label: 'Curve Data', icon: 'data' },
		{ id: 'preview' as const, label: 'Curve Preview', icon: 'chart' }
	];

	// Data sub-tab counts
	let headCount = $derived(headPoints.length);
	let effCount = $derived(efficiencyPoints.length);
	let npshCount = $derived(npshPoints.length);
	let powerCount = $derived(powerPoints.length);

	const dataTabDefs = [
		{ id: 'head' as const, label: 'Head' },
		{ id: 'efficiency' as const, label: 'Efficiency' },
		{ id: 'npsh' as const, label: 'NPSH' },
		{ id: 'power' as const, label: 'Power' }
	] as const;

	function getDataTabCount(id: 'head' | 'efficiency' | 'npsh' | 'power'): number {
		if (id === 'head') return headCount;
		if (id === 'efficiency') return effCount;
		if (id === 'npsh') return npshCount;
		return powerCount;
	}

	// === Chart helpers ===

	/** Generate nice tick values for an axis range */
	function niceAxisTicks(min: number, max: number, count: number = 5): number[] {
		if (max <= min) return [0];
		const range = max - min;
		const roughStep = range / count;
		const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
		const residual = roughStep / magnitude;
		let niceStep: number;
		if (residual <= 1.5) niceStep = magnitude;
		else if (residual <= 3) niceStep = 2 * magnitude;
		else if (residual <= 7) niceStep = 5 * magnitude;
		else niceStep = 10 * magnitude;

		const niceMin = Math.floor(min / niceStep) * niceStep;
		const niceMax = Math.ceil(max / niceStep) * niceStep;
		const ticks: number[] = [];
		for (let v = niceMin; v <= niceMax + niceStep * 0.01; v += niceStep) {
			ticks.push(Math.round(v * 1e6) / 1e6);
		}
		return ticks;
	}

	/** Shared flow domain across all curves for consistent x-axis */
	let allFlows = $derived.by(() => {
		const flows: number[] = [];
		if (headPoints.length > 0) flows.push(...headPoints.map(p => p.flow));
		if (efficiencyPoints.length > 0) flows.push(...efficiencyPoints.map(p => p.flow));
		if (npshPoints.length > 0) flows.push(...npshPoints.map(p => p.flow));
		if (powerPoints.length > 0) flows.push(...powerPoints.map(p => p.flow));
		if (designPointFlow != null) flows.push(designPointFlow);
		return flows;
	});

	let flowMax = $derived(allFlows.length > 0 ? Math.max(...allFlows) : 1);
	let flowTicks = $derived(niceAxisTicks(0, flowMax));
	let flowAxisMax = $derived(flowTicks.length > 0 ? flowTicks[flowTicks.length - 1] : 1);
</script>

{#if !sourceCurve}
	<div class="flex h-full items-center justify-center">
		<p class="text-sm text-[var(--color-text-subtle)]">Pump curve not found</p>
	</div>
{:else}
	<div class="flex h-full flex-col bg-[var(--color-surface)]">
		<!-- Top Bar: Breadcrumb + Actions -->
		<div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2">
			<!-- Breadcrumb -->
			<div class="flex items-center gap-1 text-xs">
				<button
					type="button"
					onclick={handleClose}
					class="text-[var(--color-accent)] hover:underline"
				>Library</button>
				<span class="text-[var(--color-text-subtle)]">/</span>
				<button
					type="button"
					onclick={handleClose}
					class="text-[var(--color-accent)] hover:underline"
				>Pump Curves</button>
				<span class="text-[var(--color-text-subtle)]">/</span>
				<span class="font-medium text-[var(--color-text)]">{name || 'Untitled'}</span>
			</div>

			<!-- Actions -->
			<div class="flex items-center gap-2">
				{#if pendingDelete}
					<span class="text-xs text-[var(--color-error)]">Confirm delete?</span>
					<button
						type="button"
						onclick={handleDelete}
						class="rounded bg-[var(--color-error)] px-2.5 py-1 text-xs font-medium text-white"
					>Delete</button>
					<button
						type="button"
						onclick={() => pendingDelete = false}
						class="rounded border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-text-muted)]"
					>Cancel</button>
				{:else}
					<button
						type="button"
						onclick={handleDelete}
						class="rounded border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-error)] transition-colors hover:bg-[var(--color-error)] hover:text-white"
					>Delete</button>
					<button
						type="button"
						onclick={handleDuplicate}
						class="rounded border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)]"
					>Duplicate</button>
					<button
						type="button"
						onclick={handleSave}
						class="relative rounded bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-[var(--color-accent-text)] transition-colors hover:opacity-90"
					>
						Save
						{#if isDirty}
							<span class="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-[var(--color-warning)]"></span>
						{/if}
					</button>
				{/if}
			</div>
		</div>

		<!-- Primary Tabs -->
		<div class="flex border-b border-[var(--color-border)]">
			{#each primaryTabs as tab}
				<button
					type="button"
					onclick={() => activeTab = tab.id}
					class="flex items-center gap-1.5 border-b-2 px-4 py-2 text-xs font-medium transition-colors
						{activeTab === tab.id
						? 'border-[var(--color-accent)] text-[var(--color-accent)]'
						: 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]'}"
				>
					{#if tab.icon === 'info'}
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
						</svg>
					{:else if tab.icon === 'data'}
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125" />
						</svg>
					{:else}
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
						</svg>
					{/if}
					{tab.label}
				</button>
			{/each}
		</div>

		<!-- Tab Content -->
		<div class="min-h-0 flex-1 overflow-y-auto">
			{#if activeTab === 'info'}
			<!-- Pump Information Tab -->
			<div class="mx-auto max-w-2xl space-y-4 p-6">
				<div>
					<label for="curve-name" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Curve Name *</label>
					<input id="curve-name" type="text" bind:value={name} oninput={markDirty} class="form-input" placeholder="e.g. Grundfos CR 32-2" />
				</div>

				<div class="grid grid-cols-3 gap-4">
					<div>
						<label for="curve-mfr" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Manufacturer</label>
						<input id="curve-mfr" type="text" bind:value={manufacturer} oninput={markDirty} class="form-input" placeholder="Optional" />
					</div>
					<div>
						<label for="curve-model" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Model</label>
						<input id="curve-model" type="text" bind:value={model} oninput={markDirty} class="form-input" placeholder="Optional" />
					</div>
					<div>
						<label for="curve-speed" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Curve Speed (RPM)</label>
						<input id="curve-speed" type="number" value={ratedSpeed ?? ''} oninput={(e) => { ratedSpeed = parseFloat(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" />
					</div>
				</div>

				<div class="grid grid-cols-3 gap-4">
					<div>
						<label for="curve-impeller" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Impeller Dia. (Selected Trim)</label>
						<input id="curve-impeller" type="number" value={impellerDiameter ?? ''} oninput={(e) => { impellerDiameter = parseFloat(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" />
					</div>
					<div>
						<label for="curve-min-impeller" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Min Impeller Dia.</label>
						<input id="curve-min-impeller" type="number" value={minImpellerDiameter ?? ''} oninput={(e) => { minImpellerDiameter = parseFloat(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" />
					</div>
					<div>
						<label for="curve-max-impeller" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Max Impeller Dia.</label>
						<input id="curve-max-impeller" type="number" value={maxImpellerDiameter ?? ''} oninput={(e) => { maxImpellerDiameter = parseFloat(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" />
					</div>
				</div>

				<div class="grid grid-cols-3 gap-4">
					<div>
						<label for="curve-stages" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Stages</label>
						<input id="curve-stages" type="number" min="1" value={stages ?? ''} oninput={(e) => { stages = parseInt(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" />
					</div>
					<div>
						<label for="curve-io" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Inlet / Outlet</label>
						<input id="curve-io" type="text" bind:value={inletOutlet} oninput={markDirty} class="form-input" placeholder='e.g. 2" / 2"' />
					</div>
				</div>

				<!-- Design Point -->
				<fieldset class="rounded-md border border-[var(--color-border)] p-4">
					<legend class="section-heading px-1 text-[var(--color-text-subtle)]">Design Point</legend>
					<div class="grid grid-cols-3 gap-4">
						<div>
							<label for="dp-flow" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Flow</label>
							<input id="dp-flow" type="number" value={designPointFlow ?? ''} oninput={(e) => { designPointFlow = parseFloat(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" min="0" step="any" />
						</div>
						<div>
							<label for="dp-head" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Head</label>
							<input id="dp-head" type="number" value={designPointHead ?? ''} oninput={(e) => { designPointHead = parseFloat(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" min="0" step="any" />
						</div>
						<div>
							<label for="dp-speed" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Speed (RPM)</label>
							<input id="dp-speed" type="number" value={designPointSpeed ?? ''} oninput={(e) => { designPointSpeed = parseFloat(e.currentTarget.value) || null; markDirty(); }} class="form-input mono-value" placeholder="Optional" min="0" step="any" />
						</div>
					</div>
				</fieldset>

				<div>
					<label for="curve-notes" class="mb-1 block section-heading text-[var(--color-text-subtle)]">Notes</label>
					<textarea id="curve-notes" bind:value={notes} oninput={markDirty} rows="3" class="form-input resize-y" placeholder="Free-form notes..."></textarea>
				</div>
			</div>

			{:else if activeTab === 'data'}
			<!-- Curve Data Tab -->
			<div class="flex h-full flex-col">
				<!-- Data Sub-Tabs -->
				<div class="flex gap-1 border-b border-[var(--color-border)] px-4 py-1.5">
					{#each dataTabDefs as dt}
					{@const count = getDataTabCount(dt.id)}
						<button
							type="button"
							onclick={() => activeDataTab = dt.id}
							class="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors
								{activeDataTab === dt.id
								? 'bg-[var(--color-accent)] text-[var(--color-accent-text)]'
								: 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]'}"
						>
							{dt.label}
							<span class="rounded-full bg-black/10 px-1.5 py-0.5 text-[0.5625rem] {count === 0 ? 'opacity-40' : ''}">
								{count}
							</span>
						</button>
					{/each}
				</div>

				<!-- Data Table -->
				<div class="min-h-0 flex-1 overflow-y-auto p-4">
					{#if activeDataTab === 'head'}
						{#if headPoints.length === 0}
							<div class="flex flex-col items-center gap-3 py-12 text-center">
								<p class="text-sm text-[var(--color-text-subtle)]">No head data yet.</p>
								<button type="button" onclick={addHeadPoint} class="rounded bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-[var(--color-accent-text)]">Add Data</button>
							</div>
						{:else}
							<div class="mx-auto max-w-lg">
								<div class="sticky top-0 z-10 grid grid-cols-[2rem_1fr_1fr_2rem] gap-2 bg-[var(--color-surface)] pb-1 text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-text-subtle)]">
									<span>#</span><span>Flow (GPM)</span><span>Head (ft)</span><span></span>
								</div>
								{#each headPoints as point, i}
									<div class="group grid grid-cols-[2rem_1fr_1fr_2rem] items-center gap-2 py-0.5">
										<span class="text-[0.625rem] text-[var(--color-text-subtle)]">{i + 1}</span>
										<input type="number" value={point.flow} oninput={(e) => { headPoints[i] = { ...headPoints[i], flow: parseFloat(e.currentTarget.value) || 0 }; headPoints = headPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" step="any" />
										<input type="number" value={point.head} oninput={(e) => { headPoints[i] = { ...headPoints[i], head: parseFloat(e.currentTarget.value) || 0 }; headPoints = headPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" step="any" />
										<button type="button" onclick={() => removeHeadPoint(i)} class="flex h-full items-center justify-center rounded text-[var(--color-text-subtle)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-[var(--color-error)]" title="Remove">
											<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</button>
									</div>
								{/each}
								<button type="button" onclick={addHeadPoint} class="mt-2 flex items-center gap-1 rounded px-2 py-1 text-xs text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-muted)]">
									<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" /></svg>
									Add Row
								</button>
							</div>
						{/if}

					{:else if activeDataTab === 'efficiency'}
						{#if efficiencyPoints.length === 0}
							<div class="flex flex-col items-center gap-3 py-12 text-center">
								<p class="text-sm text-[var(--color-text-subtle)]">No efficiency data yet.</p>
								<button type="button" onclick={addEfficiencyPoint} class="rounded bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-[var(--color-accent-text)]">Add Data</button>
							</div>
						{:else}
							<div class="mx-auto max-w-lg">
								<div class="sticky top-0 z-10 grid grid-cols-[2rem_1fr_1fr_2rem] gap-2 bg-[var(--color-surface)] pb-1 text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-text-subtle)]">
									<span>#</span><span>Flow (GPM)</span><span>Efficiency (%)</span><span></span>
								</div>
								{#each efficiencyPoints as point, i}
									<div class="group grid grid-cols-[2rem_1fr_1fr_2rem] items-center gap-2 py-0.5">
										<span class="text-[0.625rem] text-[var(--color-text-subtle)]">{i + 1}</span>
										<input type="number" value={point.flow} oninput={(e) => { efficiencyPoints[i] = { ...efficiencyPoints[i], flow: parseFloat(e.currentTarget.value) || 0 }; efficiencyPoints = efficiencyPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" step="any" />
										<input type="number" value={point.efficiency * 100} oninput={(e) => { efficiencyPoints[i] = { ...efficiencyPoints[i], efficiency: (parseFloat(e.currentTarget.value) || 0) / 100 }; efficiencyPoints = efficiencyPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" max="100" step="any" />
										<button type="button" onclick={() => removeEfficiencyPoint(i)} class="flex h-full items-center justify-center rounded text-[var(--color-text-subtle)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-[var(--color-error)]" title="Remove">
											<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</button>
									</div>
								{/each}
								<button type="button" onclick={addEfficiencyPoint} class="mt-2 flex items-center gap-1 rounded px-2 py-1 text-xs text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-muted)]">
									<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" /></svg>
									Add Row
								</button>
							</div>
						{/if}

					{:else if activeDataTab === 'npsh'}
						{#if npshPoints.length === 0}
							<div class="flex flex-col items-center gap-3 py-12 text-center">
								<p class="text-sm text-[var(--color-text-subtle)]">No NPSH data yet.</p>
								<button type="button" onclick={addNpshPoint} class="rounded bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-[var(--color-accent-text)]">Add Data</button>
							</div>
						{:else}
							<div class="mx-auto max-w-lg">
								<div class="sticky top-0 z-10 grid grid-cols-[2rem_1fr_1fr_2rem] gap-2 bg-[var(--color-surface)] pb-1 text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-text-subtle)]">
									<span>#</span><span>Flow (GPM)</span><span>NPSH (ft)</span><span></span>
								</div>
								{#each npshPoints as point, i}
									<div class="group grid grid-cols-[2rem_1fr_1fr_2rem] items-center gap-2 py-0.5">
										<span class="text-[0.625rem] text-[var(--color-text-subtle)]">{i + 1}</span>
										<input type="number" value={point.flow} oninput={(e) => { npshPoints[i] = { ...npshPoints[i], flow: parseFloat(e.currentTarget.value) || 0 }; npshPoints = npshPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" step="any" />
										<input type="number" value={point.npsh_required} oninput={(e) => { npshPoints[i] = { ...npshPoints[i], npsh_required: parseFloat(e.currentTarget.value) || 0 }; npshPoints = npshPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" step="any" />
										<button type="button" onclick={() => removeNpshPoint(i)} class="flex h-full items-center justify-center rounded text-[var(--color-text-subtle)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-[var(--color-error)]" title="Remove">
											<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</button>
									</div>
								{/each}
								<button type="button" onclick={addNpshPoint} class="mt-2 flex items-center gap-1 rounded px-2 py-1 text-xs text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-muted)]">
									<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" /></svg>
									Add Row
								</button>
							</div>
						{/if}

					{:else if activeDataTab === 'power'}
						{#if powerPoints.length === 0}
							<div class="flex flex-col items-center gap-3 py-12 text-center">
								<p class="text-sm text-[var(--color-text-subtle)]">No power data yet.</p>
								<button type="button" onclick={addPowerPoint} class="rounded bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-[var(--color-accent-text)]">Add Data</button>
							</div>
						{:else}
							<div class="mx-auto max-w-lg">
								<div class="sticky top-0 z-10 grid grid-cols-[2rem_1fr_1fr_2rem] gap-2 bg-[var(--color-surface)] pb-1 text-[0.625rem] font-semibold uppercase tracking-wider text-[var(--color-text-subtle)]">
									<span>#</span><span>Flow (GPM)</span><span>Power (HP)</span><span></span>
								</div>
								{#each powerPoints as point, i}
									<div class="group grid grid-cols-[2rem_1fr_1fr_2rem] items-center gap-2 py-0.5">
										<span class="text-[0.625rem] text-[var(--color-text-subtle)]">{i + 1}</span>
										<input type="number" value={point.flow} oninput={(e) => { powerPoints[i] = { ...powerPoints[i], flow: parseFloat(e.currentTarget.value) || 0 }; powerPoints = powerPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" step="any" />
										<input type="number" value={point.power} oninput={(e) => { powerPoints[i] = { ...powerPoints[i], power: parseFloat(e.currentTarget.value) || 0 }; powerPoints = powerPoints; markDirty(); }} class="form-input mono-value text-xs" min="0" step="any" />
										<button type="button" onclick={() => removePowerPoint(i)} class="flex h-full items-center justify-center rounded text-[var(--color-text-subtle)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-[var(--color-error)]" title="Remove">
											<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</button>
									</div>
								{/each}
								<button type="button" onclick={addPowerPoint} class="mt-2 flex items-center gap-1 rounded px-2 py-1 text-xs text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-muted)]">
									<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" /></svg>
									Add Row
								</button>
							</div>
						{/if}
					{/if}
				</div>
			</div>

			{:else if activeTab === 'preview'}
			<!-- Curve Preview Tab -->
			<div class="flex flex-col gap-3 p-4">
				<!-- Toggle Buttons -->
				<div class="flex flex-wrap gap-2">
					<button
						type="button"
						onclick={() => showHeadCurve = !showHeadCurve}
						class="rounded px-3 py-1.5 text-xs font-medium transition-colors
							{showHeadCurve ? 'bg-blue-500 text-white' : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'}
							{headPoints.length === 0 ? 'opacity-40 cursor-not-allowed' : ''}"
						disabled={headPoints.length === 0}
					>Head</button>
					<button
						type="button"
						onclick={() => showEffCurve = !showEffCurve}
						class="rounded px-3 py-1.5 text-xs font-medium transition-colors
							{showEffCurve ? 'bg-green-500 text-white' : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'}
							{efficiencyPoints.length === 0 ? 'opacity-40 cursor-not-allowed' : ''}"
						disabled={efficiencyPoints.length === 0}
					>Efficiency</button>
					<button
						type="button"
						onclick={() => showPowerCurve = !showPowerCurve}
						class="rounded px-3 py-1.5 text-xs font-medium transition-colors
							{showPowerCurve ? 'bg-purple-500 text-white' : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'}
							{powerPoints.length === 0 ? 'opacity-40 cursor-not-allowed' : ''}"
						disabled={powerPoints.length === 0}
					>Power</button>
				</div>

				<!-- Main Chart: Head + Efficiency + Power -->
				<div class="rounded border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-2">
					{#if headPoints.length === 0 && efficiencyPoints.length === 0 && powerPoints.length === 0}
						<div class="flex h-full items-center justify-center">
							<p class="text-sm text-[var(--color-text-subtle)]">Add curve data to see a preview.</p>
						</div>
					{:else}
						{@const chartLeft = 55}
						{@const chartRight = 470}
						{@const chartTop = 25}
						{@const chartBottom = 250}
						{@const chartW = chartRight - chartLeft}
						{@const chartH = chartBottom - chartTop}
						{@const maxHead = headPoints.length > 0 ? Math.max(...headPoints.map(p => p.head)) : 100}
						{@const headTicks = niceAxisTicks(0, maxHead)}
						{@const headAxisMax = headTicks[headTicks.length - 1] || 1}
						{@const scaleX = (flow: number) => chartLeft + (flow / flowAxisMax) * chartW}
						{@const scaleY = (head: number) => chartBottom - (head / headAxisMax) * chartH}
						<svg viewBox="0 0 500 280" class="w-full">
							<!-- Grid lines -->
							{#each headTicks as tick}
								<line x1={chartLeft} y1={scaleY(tick)} x2={chartRight} y2={scaleY(tick)} stroke="var(--color-border)" stroke-width="0.5" />
							{/each}
							{#each flowTicks as tick}
								<line x1={scaleX(tick)} y1={chartTop} x2={scaleX(tick)} y2={chartBottom} stroke="var(--color-border)" stroke-width="0.5" />
							{/each}

							<!-- Axes -->
							<line x1={chartLeft} y1={chartTop} x2={chartLeft} y2={chartBottom} stroke="var(--color-text-subtle)" stroke-width="1" />
							<line x1={chartLeft} y1={chartBottom} x2={chartRight} y2={chartBottom} stroke="var(--color-text-subtle)" stroke-width="1" />

							<!-- X-axis tick labels (flow) -->
							{#each flowTicks as tick}
								<text x={scaleX(tick)} y={chartBottom + 14} text-anchor="middle" fill="var(--color-text-muted)" font-size="8">{tick}</text>
							{/each}
							<text x={(chartLeft + chartRight) / 2} y={chartBottom + 26} text-anchor="middle" fill="var(--color-text-muted)" font-size="9">Flow (GPM)</text>

							<!-- Y-axis tick labels (head) -->
							{#each headTicks as tick}
								<text x={chartLeft - 5} y={scaleY(tick) + 3} text-anchor="end" fill="var(--color-text-muted)" font-size="8">{tick}</text>
							{/each}
							<text x="12" y={(chartTop + chartBottom) / 2} text-anchor="middle" fill="var(--color-text-muted)" font-size="9" transform="rotate(-90, 12, {(chartTop + chartBottom) / 2})">Head (ft)</text>

							<!-- Head curve (blue) -->
							{#if showHeadCurve && headBestFit && headBestFit.length > 0}
								<polyline
									points={headBestFit.map(p => `${scaleX(p.flow)},${scaleY(p.head)}`).join(' ')}
									fill="none"
									stroke="#3b82f6"
									stroke-width="2"
								/>
								{#each headPoints as p}
									<circle cx={scaleX(p.flow)} cy={scaleY(p.head)} r="3" fill="#3b82f6" />
								{/each}
							{:else if showHeadCurve && headPoints.length >= 2}
								{@const sorted = [...headPoints].sort((a, b) => a.flow - b.flow)}
								<polyline
									points={sorted.map(p => `${scaleX(p.flow)},${scaleY(p.head)}`).join(' ')}
									fill="none"
									stroke="#3b82f6"
									stroke-width="2"
								/>
								{#each sorted as p}
									<circle cx={scaleX(p.flow)} cy={scaleY(p.head)} r="3" fill="#3b82f6" />
								{/each}
							{/if}

							<!-- Efficiency curve (green, right y-axis scaled 0-100%) -->
							{#if showEffCurve && effBestFit && effBestFit.length > 0}
								<polyline
									points={effBestFit.map(p => `${scaleX(p.flow)},${chartBottom - p.efficiency * chartH}`).join(' ')}
									fill="none"
									stroke="#22c55e"
									stroke-width="2"
									stroke-dasharray="6 3"
								/>
								{#each efficiencyPoints as p}
									<circle cx={scaleX(p.flow)} cy={chartBottom - p.efficiency * chartH} r="3" fill="#22c55e" />
								{/each}
							{:else if showEffCurve && efficiencyPoints.length >= 2}
								{@const sorted = [...efficiencyPoints].sort((a, b) => a.flow - b.flow)}
								<polyline
									points={sorted.map(p => `${scaleX(p.flow)},${chartBottom - p.efficiency * chartH}`).join(' ')}
									fill="none"
									stroke="#22c55e"
									stroke-width="2"
									stroke-dasharray="6 3"
								/>
								{#each sorted as p}
									<circle cx={scaleX(p.flow)} cy={chartBottom - p.efficiency * chartH} r="3" fill="#22c55e" />
								{/each}
							{/if}

							<!-- Right Y-axis labels (efficiency %) -->
							{#if efficiencyPoints.length > 0}
								{#each [0, 25, 50, 75, 100] as pct}
									<text x={chartRight + 5} y={chartBottom - (pct / 100) * chartH + 3} text-anchor="start" fill="#22c55e" font-size="8">{pct}%</text>
								{/each}
							{/if}

							<!-- Power curve (purple) -->
							{#if showPowerCurve && powerPoints.length >= 2}
								{@const maxPower = Math.max(...powerPoints.map(p => p.power), 1)}
								{@const sorted = [...powerPoints].sort((a, b) => a.flow - b.flow)}
								<polyline
									points={sorted.map(p => `${scaleX(p.flow)},${chartBottom - (p.power / maxPower) * chartH * 0.8}`).join(' ')}
									fill="none"
									stroke="#a855f7"
									stroke-width="2"
									stroke-dasharray="8 4"
								/>
								{#each sorted as p}
									<circle cx={scaleX(p.flow)} cy={chartBottom - (p.power / maxPower) * chartH * 0.8} r="3" fill="#a855f7" />
								{/each}
							{/if}

							<!-- Design Point right-angle marker -->
							{#if designPointFlow != null && designPointHead != null}
								{@const dpX = scaleX(designPointFlow)}
								{@const dpY = scaleY(designPointHead)}
								{@const arm = 22}
								<path
									d="M {dpX - arm} {dpY} L {dpX} {dpY} L {dpX} {dpY + arm}"
									fill="none"
									stroke="#1a1a1a"
									stroke-width="2.5"
									stroke-linecap="square"
									stroke-linejoin="miter"
								/>
							{/if}

							<!-- BEP marker -->
							{#if bepData}
								{@const bepX = scaleX(bepData.flow)}
								{@const bepY = scaleY(bepData.head)}
								<circle cx={bepX} cy={bepY} r="5" fill="none" stroke="#f59e0b" stroke-width="2" />
								<text x={bepX + 8} y={bepY - 4} fill="#f59e0b" font-size="8" font-weight="bold">BEP</text>
							{/if}
						</svg>
					{/if}
				</div>

				<!-- NPSH Subplot (separate chart below main) -->
				{#if npshPoints.length >= 2}
					<div class="rounded border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-2">
					{#if true}
						{@const chartLeft = 55}
						{@const chartRight = 470}
						{@const chartTop = 15}
						{@const chartBottom = 115}
						{@const chartW = chartRight - chartLeft}
						{@const chartH = chartBottom - chartTop}
						{@const maxNpsh = Math.max(...npshPoints.map(p => p.npsh_required), 1)}
						{@const npshTicks = niceAxisTicks(0, maxNpsh)}
						{@const npshAxisMax = npshTicks[npshTicks.length - 1] || 1}
						{@const scaleX = (flow: number) => chartLeft + (flow / flowAxisMax) * chartW}
						{@const scaleY = (npsh: number) => chartBottom - (npsh / npshAxisMax) * chartH}
						<svg viewBox="0 0 500 140" class="w-full">
							<!-- Grid -->
							{#each npshTicks as tick}
								<line x1={chartLeft} y1={scaleY(tick)} x2={chartRight} y2={scaleY(tick)} stroke="var(--color-border)" stroke-width="0.5" />
							{/each}
							{#each flowTicks as tick}
								<line x1={scaleX(tick)} y1={chartTop} x2={scaleX(tick)} y2={chartBottom} stroke="var(--color-border)" stroke-width="0.5" />
							{/each}

							<!-- Axes -->
							<line x1={chartLeft} y1={chartTop} x2={chartLeft} y2={chartBottom} stroke="var(--color-text-subtle)" stroke-width="1" />
							<line x1={chartLeft} y1={chartBottom} x2={chartRight} y2={chartBottom} stroke="var(--color-text-subtle)" stroke-width="1" />

							<!-- X-axis ticks -->
							{#each flowTicks as tick}
								<text x={scaleX(tick)} y={chartBottom + 12} text-anchor="middle" fill="var(--color-text-muted)" font-size="8">{tick}</text>
							{/each}
							<text x={(chartLeft + chartRight) / 2} y={chartBottom + 24} text-anchor="middle" fill="var(--color-text-muted)" font-size="9">Flow (GPM)</text>

							<!-- Y-axis ticks -->
							{#each npshTicks as tick}
								<text x={chartLeft - 5} y={scaleY(tick) + 3} text-anchor="end" fill="var(--color-text-muted)" font-size="8">{tick}</text>
							{/each}
							<text x="12" y={(chartTop + chartBottom) / 2} text-anchor="middle" fill="#f97316" font-size="9" transform="rotate(-90, 12, {(chartTop + chartBottom) / 2})">NPSHr (ft)</text>

							<!-- NPSH curve -->
							<polyline
								points={[...npshPoints].sort((a, b) => a.flow - b.flow).map(p => `${scaleX(p.flow)},${scaleY(p.npsh_required)}`).join(' ')}
								fill="none"
								stroke="#f97316"
								stroke-width="2"
							/>
							{#each [...npshPoints].sort((a, b) => a.flow - b.flow) as p}
								<circle cx={scaleX(p.flow)} cy={scaleY(p.npsh_required)} r="3" fill="#f97316" />
							{/each}

							<!-- Design Point right-angle marker on NPSH curve -->
							{#if designPointFlow != null}
								{@const dpNpshX = scaleX(designPointFlow)}
								{@const sortedNpsh = [...npshPoints].sort((a, b) => a.flow - b.flow)}
								{@const dpNpshY = (() => {
									const pts = sortedNpsh;
									const f = designPointFlow;
									if (pts.length < 2 || f <= pts[0].flow) return scaleY(pts[0]?.npsh_required ?? 0);
									if (f >= pts[pts.length - 1].flow) return scaleY(pts[pts.length - 1].npsh_required);
									for (let i = 1; i < pts.length; i++) {
										if (f <= pts[i].flow) {
											const t = (f - pts[i-1].flow) / (pts[i].flow - pts[i-1].flow);
											return scaleY(pts[i-1].npsh_required + t * (pts[i].npsh_required - pts[i-1].npsh_required));
										}
									}
									return scaleY(0);
								})()}
								{@const arm = 16}
								<path
									d="M {dpNpshX - arm} {dpNpshY} L {dpNpshX} {dpNpshY} L {dpNpshX} {dpNpshY + arm}"
									fill="none"
									stroke="#1a1a1a"
									stroke-width="2.5"
									stroke-linecap="square"
									stroke-linejoin="miter"
								/>
							{/if}
						</svg>
					{/if}
					</div>
				{/if}

				<!-- Legend -->
				<div class="flex flex-wrap gap-4 text-xs text-[var(--color-text-muted)]">
					{#if headPoints.length > 0}
						<span class="flex items-center gap-1.5"><span class="h-0.5 w-4 bg-blue-500"></span> Head (ft)</span>
					{/if}
					{#if efficiencyPoints.length > 0}
						<span class="flex items-center gap-1.5"><span class="h-0.5 w-4 border-t-2 border-dashed border-green-500"></span> Efficiency (%)</span>
					{/if}
					{#if powerPoints.length > 0}
						<span class="flex items-center gap-1.5"><span class="h-0.5 w-4 border-t-2 border-dashed border-purple-500"></span> Power (HP)</span>
					{/if}
					{#if npshPoints.length > 0}
						<span class="flex items-center gap-1.5"><span class="h-0.5 w-4 bg-orange-500"></span> NPSHr (ft)</span>
					{/if}
					{#if designPointFlow != null && designPointHead != null}
						<span class="flex items-center gap-1.5"><svg class="h-3 w-3" viewBox="0 0 12 12"><path d="M 1 4 L 7 4 L 7 11" fill="none" stroke="#1a1a1a" stroke-width="2" stroke-linecap="square" stroke-linejoin="miter" /></svg> Design Point</span>
					{/if}
					{#if bepData}
						<span class="flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-full border-2 border-amber-500"></span> BEP</span>
					{/if}
				</div>
			</div>
			{/if}
		</div>
	</div>
{/if}
