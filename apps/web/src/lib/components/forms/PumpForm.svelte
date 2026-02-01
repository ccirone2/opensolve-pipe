<script lang="ts">
	import type {
		PumpComponent,
		PumpCurve,
		FlowHeadPoint,
		FlowEfficiencyPoint,
		NPSHRPoint,
		PumpOperatingMode,
		PumpStatus
	} from '$lib/models';
	import { PUMP_OPERATING_MODE_LABELS, PUMP_STATUS_LABELS } from '$lib/models';
	import { pumpLibrary, projectStore } from '$lib/stores';
	import NumberInput from './NumberInput.svelte';

	interface Props {
		/** The pump component to edit. */
		component: PumpComponent;
		/** Callback when a field value changes. */
		onUpdate: (field: string, value: unknown) => void;
	}

	let { component, onUpdate }: Props = $props();

	let showCurveEditor = $state(false);
	let editingCurve = $state<PumpCurve | null>(null);
	let newPoint = $state({ flow: 0, head: 0 });
	let newEfficiencyPoint = $state({ flow: 0, efficiency: 0 });
	let newNpshrPoint = $state({ flow: 0, npsh_required: 0 });

	// Focus trap for modal
	let modalRef = $state<HTMLDivElement | null>(null);
	let previousActiveElement: Element | null = null;

	// Focus trap effect
	$effect(() => {
		if (showCurveEditor && modalRef) {
			// Store the previously focused element
			previousActiveElement = document.activeElement;

			// Focus the first focusable element in the modal
			const focusableElements = modalRef.querySelectorAll<HTMLElement>(
				'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
			);
			if (focusableElements.length > 0) {
				focusableElements[0].focus();
			}
		} else if (!showCurveEditor && previousActiveElement) {
			// Restore focus when modal closes
			(previousActiveElement as HTMLElement).focus?.();
			previousActiveElement = null;
		}
	});

	function handleModalKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			cancelCurveEdit();
			return;
		}

		if (event.key !== 'Tab' || !modalRef) return;

		const focusableElements = modalRef.querySelectorAll<HTMLElement>(
			'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
		);
		const firstElement = focusableElements[0];
		const lastElement = focusableElements[focusableElements.length - 1];

		if (event.shiftKey) {
			// Shift + Tab: if on first element, go to last
			if (document.activeElement === firstElement) {
				event.preventDefault();
				lastElement.focus();
			}
		} else {
			// Tab: if on last element, go to first
			if (document.activeElement === lastElement) {
				event.preventDefault();
				firstElement.focus();
			}
		}
	}

	// Get the selected curve
	let selectedCurve = $derived($pumpLibrary.find((c) => c.id === component.curve_id));

	function startNewCurve() {
		editingCurve = {
			id: crypto.randomUUID(),
			name: 'New Pump Curve',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 50, head: 90 },
				{ flow: 100, head: 75 },
				{ flow: 150, head: 50 }
			]
		};
		showCurveEditor = true;
	}

	function editExistingCurve() {
		if (selectedCurve) {
			editingCurve = JSON.parse(JSON.stringify(selectedCurve));
			showCurveEditor = true;
		}
	}

	function saveCurve() {
		if (!editingCurve) return;

		// Sort points by flow
		editingCurve.points.sort((a, b) => a.flow - b.flow);

		// Sort efficiency curve by flow if present
		if (editingCurve.efficiency_curve) {
			editingCurve.efficiency_curve.sort((a, b) => a.flow - b.flow);
		}

		// Sort NPSHr curve by flow if present
		if (editingCurve.npshr_curve) {
			editingCurve.npshr_curve.sort((a, b) => a.flow - b.flow);
		}

		// Create a plain object copy to avoid Svelte proxy issues with structuredClone
		const curveToSave: PumpCurve = {
			id: editingCurve.id,
			name: editingCurve.name,
			points: editingCurve.points.map((p) => ({ flow: p.flow, head: p.head })),
			efficiency_curve: editingCurve.efficiency_curve?.map((p) => ({
				flow: p.flow,
				efficiency: p.efficiency
			})),
			npshr_curve: editingCurve.npshr_curve?.map((p) => ({
				flow: p.flow,
				npsh_required: p.npsh_required
			}))
		};

		// Check if curve already exists
		const existingIndex = $pumpLibrary.findIndex((c) => c.id === editingCurve!.id);
		if (existingIndex >= 0) {
			projectStore.updatePumpCurve(curveToSave.id, {
				name: curveToSave.name,
				points: curveToSave.points,
				efficiency_curve: curveToSave.efficiency_curve,
				npshr_curve: curveToSave.npshr_curve
			});
		} else {
			projectStore.addPumpCurve(curveToSave);
		}

		// Select the curve for this pump
		onUpdate('curve_id', curveToSave.id);

		showCurveEditor = false;
		editingCurve = null;
	}

	function cancelCurveEdit() {
		showCurveEditor = false;
		editingCurve = null;
	}

	function addPoint() {
		if (!editingCurve) return;
		editingCurve.points = [...editingCurve.points, { ...newPoint }];
		newPoint = { flow: 0, head: 0 };
	}

	function removePoint(index: number) {
		if (!editingCurve) return;
		editingCurve.points = editingCurve.points.filter((_, i) => i !== index);
	}

	function updatePoint(index: number, field: keyof FlowHeadPoint, value: number) {
		if (!editingCurve) return;
		const newPoints = [...editingCurve.points];
		newPoints[index] = { ...newPoints[index], [field]: value };
		editingCurve.points = newPoints;
	}

	// Efficiency curve functions
	function addEfficiencyPoint() {
		if (!editingCurve) return;
		const efficiencyDecimal = newEfficiencyPoint.efficiency / 100; // Convert % to decimal
		editingCurve.efficiency_curve = [
			...(editingCurve.efficiency_curve || []),
			{ flow: newEfficiencyPoint.flow, efficiency: efficiencyDecimal }
		];
		newEfficiencyPoint = { flow: 0, efficiency: 0 };
	}

	function removeEfficiencyPoint(index: number) {
		if (!editingCurve || !editingCurve.efficiency_curve) return;
		editingCurve.efficiency_curve = editingCurve.efficiency_curve.filter((_, i) => i !== index);
		if (editingCurve.efficiency_curve.length === 0) {
			editingCurve.efficiency_curve = undefined;
		}
	}

	function updateEfficiencyPoint(index: number, field: keyof FlowEfficiencyPoint, value: number) {
		if (!editingCurve || !editingCurve.efficiency_curve) return;
		const newPoints = [...editingCurve.efficiency_curve];
		if (field === 'efficiency') {
			// Convert % to decimal
			newPoints[index] = { ...newPoints[index], efficiency: value / 100 };
		} else {
			newPoints[index] = { ...newPoints[index], [field]: value };
		}
		editingCurve.efficiency_curve = newPoints;
	}

	// NPSHr curve functions
	function addNpshrPoint() {
		if (!editingCurve) return;
		editingCurve.npshr_curve = [
			...(editingCurve.npshr_curve || []),
			{ ...newNpshrPoint }
		];
		newNpshrPoint = { flow: 0, npsh_required: 0 };
	}

	function removeNpshrPoint(index: number) {
		if (!editingCurve || !editingCurve.npshr_curve) return;
		editingCurve.npshr_curve = editingCurve.npshr_curve.filter((_, i) => i !== index);
		if (editingCurve.npshr_curve.length === 0) {
			editingCurve.npshr_curve = undefined;
		}
	}

	function updateNpshrPoint(index: number, field: keyof NPSHRPoint, value: number) {
		if (!editingCurve || !editingCurve.npshr_curve) return;
		const newPoints = [...editingCurve.npshr_curve];
		newPoints[index] = { ...newPoints[index], [field]: value };
		editingCurve.npshr_curve = newPoints;
	}
</script>

<div class="space-y-4">
	<NumberInput
		id="elevation"
		label="Elevation"
		value={component.elevation}
		unit="ft"
		onchange={(value) => onUpdate('elevation', value)}
	/>

	<!-- Pump Curve Selection -->
	<div>
		<label for="curve_id" class="block text-sm font-medium text-[var(--color-text)]">Pump Curve</label>
		<div class="mt-1 flex gap-2">
			<select
				id="curve_id"
				value={component.curve_id}
				onchange={(e) => onUpdate('curve_id', (e.target as HTMLSelectElement).value)}
				class="block flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] shadow-sm focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
			>
				<option value="">Select a curve...</option>
				{#each $pumpLibrary as curve}
					<option value={curve.id}>{curve.name}</option>
				{/each}
			</select>
			<button
				type="button"
				onclick={startNewCurve}
				class="rounded-md bg-[var(--color-surface-elevated)] px-3 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-border)]"
				title="Create new curve"
			>
				+
			</button>
			{#if selectedCurve}
				<button
					type="button"
					onclick={editExistingCurve}
					class="rounded-md bg-[var(--color-surface-elevated)] px-3 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-border)]"
					title="Edit selected curve"
				>
					Edit
				</button>
			{/if}
		</div>
	</div>

	<!-- Curve Preview -->
	{#if selectedCurve}
		<div class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
			<p class="text-xs font-medium text-[var(--color-text-muted)]">Curve Points</p>
			<div class="mt-1 flex flex-wrap gap-2">
				{#each selectedCurve.points as point}
					<span class="rounded bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-text)] shadow-sm">
						{point.flow} GPM @ {point.head} ft
					</span>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Operating Mode -->
	<div>
		<label for="operating_mode" class="block text-sm font-medium text-[var(--color-text)]">
			Operating Mode
		</label>
		<select
			id="operating_mode"
			value={component.operating_mode}
			onchange={(e) => {
				const mode = (e.target as HTMLSelectElement).value as PumpOperatingMode;
				onUpdate('operating_mode', mode);
				// Auto-set status when mode is 'off'
				if (mode === 'off' && component.status === 'running') {
					onUpdate('status', 'off_check');
				}
				// Auto-set status to running when switching from off to a running mode
				if (mode !== 'off' && (component.status === 'off_check' || component.status === 'off_no_check')) {
					onUpdate('status', 'running');
				}
			}}
			class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] shadow-sm focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
		>
			{#each Object.entries(PUMP_OPERATING_MODE_LABELS) as [value, label]}
				<option {value}>{label}</option>
			{/each}
		</select>
	</div>

	<!-- Speed Ratio (only for fixed_speed and variable_speed modes) -->
	{#if component.operating_mode === 'fixed_speed' || component.operating_mode === 'variable_speed'}
		<NumberInput
			id="speed"
			label="Speed Ratio"
			value={component.speed * 100}
			unit="%"
			min={0}
			max={150}
			step={1}
			onchange={(value) => onUpdate('speed', value / 100)}
			hint="100% = design speed (0-150%)"
		/>
	{/if}

	<!-- Pressure Setpoint (only for controlled_pressure mode) -->
	{#if component.operating_mode === 'controlled_pressure'}
		<NumberInput
			id="control_setpoint"
			label="Pressure Setpoint"
			value={component.control_setpoint ?? 50}
			unit="psi"
			min={0}
			step={1}
			onchange={(value) => onUpdate('control_setpoint', value)}
			hint="Target discharge pressure"
		/>
	{/if}

	<!-- Flow Setpoint (only for controlled_flow mode) -->
	{#if component.operating_mode === 'controlled_flow'}
		<NumberInput
			id="control_setpoint"
			label="Flow Setpoint"
			value={component.control_setpoint ?? 100}
			unit="GPM"
			min={0}
			step={1}
			onchange={(value) => onUpdate('control_setpoint', value)}
			hint="Target flow rate"
		/>
	{/if}

	<!-- Viscosity Correction -->
	<div class="flex items-start gap-2">
		<input
			type="checkbox"
			id="viscosity_correction"
			checked={component.viscosity_correction_enabled}
			onchange={(e) => onUpdate('viscosity_correction_enabled', (e.target as HTMLInputElement).checked)}
			class="mt-1 h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
		/>
		<div>
			<label for="viscosity_correction" class="text-sm font-medium text-[var(--color-text)]">
				Apply viscosity correction
			</label>
			<p class="text-xs text-[var(--color-text-muted)]">
				Automatically correct pump performance for viscous fluids per ANSI/HI 9.6.7
			</p>
		</div>
	</div>

	<!-- Advanced Section (collapsible) -->
	<details class="rounded-md border border-[var(--color-border)]">
		<summary class="cursor-pointer px-3 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-elevated)]">
			Advanced
		</summary>
		<div class="border-t border-[var(--color-border)] p-3">
			<label for="status" class="block text-sm font-medium text-[var(--color-text)]">Status</label>
			<select
				id="status"
				value={component.status}
				onchange={(e) => onUpdate('status', (e.target as HTMLSelectElement).value as PumpStatus)}
				class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] shadow-sm focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
			>
				{#each Object.entries(PUMP_STATUS_LABELS) as [value, label]}
					<option {value}>{label}</option>
				{/each}
			</select>
			<p class="mt-1 text-xs text-[var(--color-text-muted)]">
				{#if component.status === 'off_check'}
					Pump is off but check valve prevents backflow
				{:else if component.status === 'off_no_check'}
					Pump is off and allows backflow
				{:else if component.status === 'locked_out'}
					Pump is locked out and cannot operate
				{:else}
					Pump is running normally
				{/if}
			</p>
		</div>
	</details>
</div>

<!-- Curve Editor Modal -->
{#if showCurveEditor && editingCurve}
	<!-- svelte-ignore a11y_interactive_supports_focus -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
		role="dialog"
		aria-modal="true"
		aria-labelledby="modal-title"
		onkeydown={handleModalKeydown}
	>
		<div
			bind:this={modalRef}
			class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-[var(--color-surface)] p-6 shadow-xl"
		>
			<h3 id="modal-title" class="text-lg font-semibold text-[var(--color-text)]">Edit Pump Curve</h3>

			<div class="mt-4 space-y-4">
				<div>
					<label for="curve_name" class="block text-sm font-medium text-[var(--color-text)]">Curve Name</label>
					<input
						type="text"
						id="curve_name"
						value={editingCurve.name}
						oninput={(e) => {
							if (editingCurve) editingCurve.name = (e.target as HTMLInputElement).value;
						}}
						class="mt-1 block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
					/>
				</div>

				<!-- Points Table -->
				<div>
					<p class="text-sm font-medium text-[var(--color-text)]">Flow-Head Points</p>
					<div class="mt-2 overflow-hidden rounded-md border border-[var(--color-border)]">
						<table class="min-w-full divide-y divide-[var(--color-border)]">
							<thead class="bg-[var(--color-surface-elevated)]">
								<tr>
									<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
										Flow (GPM)
									</th>
									<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
										Head (ft)
									</th>
									<th class="w-12 px-3 py-2"></th>
								</tr>
							</thead>
							<tbody class="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
								{#each editingCurve.points as point, index}
									<tr>
										<td class="px-3 py-2">
											<input
												type="number"
												value={point.flow}
												min={0}
												oninput={(e) =>
													updatePoint(index, 'flow', parseFloat((e.target as HTMLInputElement).value) || 0)}
												class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
											/>
										</td>
										<td class="px-3 py-2">
											<input
												type="number"
												value={point.head}
												min={0}
												oninput={(e) =>
													updatePoint(index, 'head', parseFloat((e.target as HTMLInputElement).value) || 0)}
												class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
											/>
										</td>
										<td class="px-3 py-2">
											<button
												type="button"
												onclick={() => removePoint(index)}
												class="text-[var(--color-error)] hover:opacity-80"
												disabled={editingCurve.points.length <= 2}
												aria-label="Remove point"
											>
												<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
												</svg>
											</button>
										</td>
									</tr>
								{/each}
								<!-- Add new point row -->
								<tr class="bg-[var(--color-surface-elevated)]">
									<td class="px-3 py-2">
										<input
											type="number"
											placeholder="Flow"
											bind:value={newPoint.flow}
											min={0}
											class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
										/>
									</td>
									<td class="px-3 py-2">
										<input
											type="number"
											placeholder="Head"
											bind:value={newPoint.head}
											min={0}
											class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
										/>
									</td>
									<td class="px-3 py-2">
										<button
											type="button"
											onclick={addPoint}
											class="text-[var(--color-accent)] hover:opacity-80"
											aria-label="Add point"
										>
											<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
											</svg>
										</button>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
					<p class="mt-1 text-xs text-[var(--color-text-muted)]">Minimum 2 points required</p>
				</div>

				<!-- Efficiency Curve Table (optional) -->
				<div>
					<p class="text-sm font-medium text-[var(--color-text)]">Efficiency Curve (optional)</p>
					<p class="text-xs text-[var(--color-text-muted)]">Used to determine Best Efficiency Point (BEP)</p>
					<div class="mt-2 overflow-hidden rounded-md border border-[var(--color-border)]">
						<table class="min-w-full divide-y divide-[var(--color-border)]">
							<thead class="bg-[var(--color-surface-elevated)]">
								<tr>
									<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
										Flow (GPM)
									</th>
									<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
										Efficiency (%)
									</th>
									<th class="w-12 px-3 py-2"></th>
								</tr>
							</thead>
							<tbody class="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
								{#if editingCurve.efficiency_curve}
									{#each editingCurve.efficiency_curve as point, index}
										<tr>
											<td class="px-3 py-2">
												<input
													type="number"
													value={point.flow}
													min={0}
													oninput={(e) =>
														updateEfficiencyPoint(index, 'flow', parseFloat((e.target as HTMLInputElement).value) || 0)}
													class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
												/>
											</td>
											<td class="px-3 py-2">
												<input
													type="number"
													value={Math.round(point.efficiency * 100)}
													min={0}
													max={100}
													oninput={(e) =>
														updateEfficiencyPoint(index, 'efficiency', parseFloat((e.target as HTMLInputElement).value) || 0)}
													class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
												/>
											</td>
											<td class="px-3 py-2">
												<button
													type="button"
													onclick={() => removeEfficiencyPoint(index)}
													class="text-[var(--color-error)] hover:opacity-80"
													aria-label="Remove efficiency point"
												>
													<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
													</svg>
												</button>
											</td>
										</tr>
									{/each}
								{/if}
								<!-- Add new efficiency point row -->
								<tr class="bg-[var(--color-surface-elevated)]">
									<td class="px-3 py-2">
										<input
											type="number"
											placeholder="Flow"
											bind:value={newEfficiencyPoint.flow}
											min={0}
											class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
										/>
									</td>
									<td class="px-3 py-2">
										<input
											type="number"
											placeholder="Efficiency"
											bind:value={newEfficiencyPoint.efficiency}
											min={0}
											max={100}
											class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
										/>
									</td>
									<td class="px-3 py-2">
										<button
											type="button"
											onclick={addEfficiencyPoint}
											class="text-[var(--color-accent)] hover:opacity-80"
											aria-label="Add efficiency point"
										>
											<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
											</svg>
										</button>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>

				<!-- NPSH Required Curve Table (optional) -->
				<div>
					<p class="text-sm font-medium text-[var(--color-text)]">NPSH Required Curve (optional)</p>
					<p class="text-xs text-[var(--color-text-muted)]">Used for cavitation margin calculations</p>
					<div class="mt-2 overflow-hidden rounded-md border border-[var(--color-border)]">
						<table class="min-w-full divide-y divide-[var(--color-border)]">
							<thead class="bg-[var(--color-surface-elevated)]">
								<tr>
									<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
										Flow (GPM)
									</th>
									<th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
										NPSHr (ft)
									</th>
									<th class="w-12 px-3 py-2"></th>
								</tr>
							</thead>
							<tbody class="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
								{#if editingCurve.npshr_curve}
									{#each editingCurve.npshr_curve as point, index}
										<tr>
											<td class="px-3 py-2">
												<input
													type="number"
													value={point.flow}
													min={0}
													oninput={(e) =>
														updateNpshrPoint(index, 'flow', parseFloat((e.target as HTMLInputElement).value) || 0)}
													class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
												/>
											</td>
											<td class="px-3 py-2">
												<input
													type="number"
													value={point.npsh_required}
													min={0}
													oninput={(e) =>
														updateNpshrPoint(index, 'npsh_required', parseFloat((e.target as HTMLInputElement).value) || 0)}
													class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
												/>
											</td>
											<td class="px-3 py-2">
												<button
													type="button"
													onclick={() => removeNpshrPoint(index)}
													class="text-[var(--color-error)] hover:opacity-80"
													aria-label="Remove NPSHr point"
												>
													<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
													</svg>
												</button>
											</td>
										</tr>
									{/each}
								{/if}
								<!-- Add new NPSHr point row -->
								<tr class="bg-[var(--color-surface-elevated)]">
									<td class="px-3 py-2">
										<input
											type="number"
											placeholder="Flow"
											bind:value={newNpshrPoint.flow}
											min={0}
											class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
										/>
									</td>
									<td class="px-3 py-2">
										<input
											type="number"
											placeholder="NPSHr"
											bind:value={newNpshrPoint.npsh_required}
											min={0}
											class="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm text-[var(--color-text)]"
										/>
									</td>
									<td class="px-3 py-2">
										<button
											type="button"
											onclick={addNpshrPoint}
											class="text-[var(--color-accent)] hover:opacity-80"
											aria-label="Add NPSHr point"
										>
											<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
											</svg>
										</button>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>

			<div class="mt-6 flex justify-end gap-3">
				<button
					type="button"
					onclick={cancelCurveEdit}
					class="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-elevated)]"
				>
					Cancel
				</button>
				<button
					type="button"
					onclick={saveCurve}
					disabled={editingCurve.points.length < 2}
					class="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-[var(--color-accent-text)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
				>
					Save Curve
				</button>
			</div>
		</div>
	</div>
{/if}
