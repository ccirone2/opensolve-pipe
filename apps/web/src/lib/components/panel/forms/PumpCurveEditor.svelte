<!--
	A pump curve in the project's pump library (PRD §3.4): name, head points (at least 3), and
	optional efficiency and NPSHr curves (at least 2 points each), and the manufacturer's data the
	opt-in design checks read (allowable operating region, minimum flows, motor rating; D19). With no curve yet (`curve`
	undefined), the curve `curveId` is created once 3 complete head points are entered, and the
	pump is set to use it.
-->
<script lang="ts">
	import type { Project, Pump, PumpCurve } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { setPumpCurve, updateComponent } from '$lib/utils/edit';
	import { withOptional } from '$lib/utils/piping';
	import { schemaBounds, stringLimits } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import PointsTable, { type Point } from '../PointsTable.svelte';

	interface Props {
		pump: Pump;
		/** The curve to edit; undefined to create curve `curveId`. */
		curve: PumpCurve | undefined;
		curveId: string;
		/** Called after a new curve was created. */
		oncreated?: () => void;
	}

	let { pump, curve, curveId, oncreated }: Props = $props();
	const ws = useWorkspace();
	let newName = $derived(`Pump curve ${curveId}`);
	let showEfficiency = $state(false);
	let showNpshr = $state(false);

	/** An allowable region with one end entered: kept here until the other is (the API needs both). */
	let regionDraft = $state<{ flowMin: number | null; flowMax: number | null }>({
		flowMin: null,
		flowMax: null
	});
	const region = $derived(
		curve?.allowableOperatingRegion || regionDraft.flowMin !== null || regionDraft.flowMax !== null
			? {
					flowMin: curve?.allowableOperatingRegion?.flowMin ?? regionDraft.flowMin,
					flowMax: curve?.allowableOperatingRegion?.flowMax ?? regionDraft.flowMax
				}
			: null
	);
	const regionError = $derived(
		region && (region.flowMin === null || region.flowMax === null)
			? 'Enter both ends of the allowable operating region.'
			: null
	);
	/** An end refused for its order (the API's x-ordered-fields), until the next edit. */
	let regionOrder = $state<'flowMin' | 'flowMax' | null>(null);
	const regionErrorAt = (end: 'flowMin' | 'flowMax') =>
		regionOrder === end
			? end === 'flowMin'
				? 'Enter a flow below the highest flow.'
				: 'Enter a flow above the lowest flow.'
			: regionError && region?.[end] === null
				? regionError
				: null;

	function setRegion(end: 'flowMin' | 'flowMax', value: number | null): boolean {
		const next = {
			flowMin: region?.flowMin ?? null,
			flowMax: region?.flowMax ?? null,
			[end]: value
		};
		regionOrder = null;
		if (next.flowMin !== null && next.flowMax !== null) {
			if (!(next.flowMin < next.flowMax)) {
				regionOrder = end;
				return false;
			}
			regionDraft = { flowMin: null, flowMax: null };
			return save('change allowable operating region', (c) => ({
				...c,
				allowableOperatingRegion: { flowMin: next.flowMin!, flowMax: next.flowMax! }
			}));
		}
		regionDraft = next;
		if (curve?.allowableOperatingRegion)
			save('remove allowable operating region', (c) =>
				withOptional(c, 'allowableOperatingRegion', null)
			);
		return true;
	}

	type ManufacturerField = 'minimumContinuousStableFlow' | 'minimumThermalFlow' | 'motorRatedPower';
	function setManufacturer(field: ManufacturerField, value: number | null, label: string) {
		return save(label, (c) => withOptional(c, field, value));
	}

	const flowAxis = {
		label: 'Flow',
		category: 'flow' as const,
		bounds: schemaBounds('FlowHeadPoint', 'flow')
	};
	const nameLimits = stringLimits('PumpCurve', 'name');

	function save(label: string, change: (curve: PumpCurve) => PumpCurve): boolean {
		if (!curve) return false;
		const current = curve;
		return ws.edit((p) => setPumpCurve(p, change(structuredClone(current))), label);
	}

	function create(points: Point[]): boolean {
		const created: PumpCurve = {
			id: curveId,
			name: newName,
			points: points.map((p) => ({ flow: p.x, head: p.y }))
		};
		const ok = ws.edit(
			(p: Project) =>
				updateComponent(setPumpCurve(p, created), pump.id, (c) => ({ ...c, curveId }) as Pump),
			'add pump curve'
		);
		if (ok) oncreated?.();
		return ok;
	}
</script>

{#if !curve}
	<div class="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
		<p class="flex items-start gap-2 text-sm text-amber-900">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
			<span>
				This pump needs a curve. Enter at least 3 points of head against flow from the pump's data
				sheet (at rated speed); the curve is saved to the project's pump library as “{curveId}”.
			</span>
		</p>
		<TextField
			label="Curve name"
			value={newName}
			required
			maxlength={nameLimits.maxLength}
			onchange={(v) => {
				if (v) newName = v;
			}}
		/>
		<PointsTable
			caption="Head curve"
			rows={[]}
			x={flowAxis}
			y={{ label: 'Head', category: 'head', bounds: schemaBounds('FlowHeadPoint', 'head') }}
			units={ws.units}
			minRows={3}
			onchange={create}
		/>
	</div>
{:else}
	<div class="space-y-4">
		<TextField
			label="Curve name"
			value={curve.name}
			required
			maxlength={nameLimits.maxLength}
			onchange={(v) => !!v && save('rename pump curve', (c) => ({ ...c, name: v }))}
		/>
		<div class="grid gap-3 sm:grid-cols-2">
			<TextField
				label="Manufacturer"
				value={curve.manufacturer}
				maxlength={stringLimits('PumpCurve', 'manufacturer').maxLength}
				onchange={(v) => save('change pump manufacturer', (c) => ({ ...c, manufacturer: v }))}
			/>
			<TextField
				label="Model"
				value={curve.model}
				maxlength={stringLimits('PumpCurve', 'model').maxLength}
				onchange={(v) => save('change pump model', (c) => ({ ...c, model: v }))}
			/>
		</div>
		<PointsTable
			caption="Head curve (at rated speed)"
			rows={curve.points.map((p) => ({ x: p.flow, y: p.head }))}
			x={flowAxis}
			y={{ label: 'Head', category: 'head', bounds: schemaBounds('FlowHeadPoint', 'head') }}
			units={ws.units}
			minRows={3}
			onchange={(rows) =>
				save('edit pump curve', (c) => ({
					...c,
					points: rows.map((r) => ({ flow: r.x, head: r.y }))
				}))}
		/>

		{#if curve.efficiencyCurve || showEfficiency}
			<div>
				<PointsTable
					caption="Efficiency curve (optional)"
					rows={(curve.efficiencyCurve ?? []).map((p) => ({ x: p.flow, y: p.efficiency }))}
					x={flowAxis}
					y={{
						label: 'Efficiency',
						category: 'fraction',
						bounds: schemaBounds('FlowEfficiencyPoint', 'efficiency')
					}}
					units={ws.units}
					minRows={2}
					onchange={(rows) =>
						save('edit efficiency curve', (c) => ({
							...c,
							efficiencyCurve: rows.map((r) => ({ flow: r.x, efficiency: r.y }))
						}))}
				/>
				{#if !ws.inScenario}<button
						type="button"
						class="btn btn-quiet mt-1 text-red-800"
						onclick={() => {
							showEfficiency = false;
							if (curve?.efficiencyCurve)
								save('remove efficiency curve', (c) => withOptional(c, 'efficiencyCurve', null));
						}}
					>
						<Icon name="trash" class="size-4" /> Remove efficiency curve
					</button>{/if}
			</div>
		{:else if !ws.inScenario}
			<button type="button" class="btn" onclick={() => (showEfficiency = true)}>
				<Icon name="plus" class="size-4" /> Add efficiency curve
			</button>
		{/if}

		{#if curve.npshrCurve || showNpshr}
			<div>
				<PointsTable
					caption="NPSH required (optional)"
					rows={(curve.npshrCurve ?? []).map((p) => ({ x: p.flow, y: p.npshr }))}
					x={flowAxis}
					y={{ label: 'NPSHr', category: 'head', bounds: schemaBounds('FlowNpshrPoint', 'npshr') }}
					units={ws.units}
					minRows={2}
					onchange={(rows) =>
						save('edit NPSHr curve', (c) => ({
							...c,
							npshrCurve: rows.map((r) => ({ flow: r.x, npshr: r.y }))
						}))}
				/>
				{#if !ws.inScenario}<button
						type="button"
						class="btn btn-quiet mt-1 text-red-800"
						onclick={() => {
							showNpshr = false;
							if (curve?.npshrCurve)
								save('remove NPSHr curve', (c) => withOptional(c, 'npshrCurve', null));
						}}
					>
						<Icon name="trash" class="size-4" /> Remove NPSHr curve
					</button>{/if}
			</div>
		{:else if !ws.inScenario}
			<button type="button" class="btn" onclick={() => (showNpshr = true)}>
				<Icon name="plus" class="size-4" /> Add NPSHr curve
			</button>
		{/if}
		<details
			class="group"
			open={!!(
				region ||
				curve.minimumContinuousStableFlow ||
				curve.minimumThermalFlow ||
				curve.motorRatedPower
			)}
		>
			<summary class="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-medium">
				<span
					class="text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
					aria-hidden="true">▸</span
				>
				Manufacturer data (optional)
			</summary>
			<p class="hint mb-2">
				From the pump's datasheet, at rated speed. Read only by the opt-in pump operating region
				check (Settings → Design checks); the solve does not use them.
			</p>
			<div class="grid gap-3 sm:grid-cols-2">
				<NumberField
					label="Allowable operating region, lowest flow"
					value={region?.flowMin}
					category="flow"
					units={ws.units}
					optional
					placeholder="Not given"
					bounds={schemaBounds('AllowableOperatingRegion', 'flowMin')}
					error={regionErrorAt('flowMin')}
					oninput={() => (regionOrder = null)}
					onchange={(v) => setRegion('flowMin', v)}
				/>
				<NumberField
					label="Allowable operating region, highest flow"
					value={region?.flowMax}
					category="flow"
					units={ws.units}
					optional
					placeholder="Not given"
					bounds={schemaBounds('AllowableOperatingRegion', 'flowMax')}
					error={regionErrorAt('flowMax')}
					oninput={() => (regionOrder = null)}
					onchange={(v) => setRegion('flowMax', v)}
				/>
				<NumberField
					label="Minimum continuous stable flow"
					value={curve.minimumContinuousStableFlow}
					category="flow"
					units={ws.units}
					optional
					placeholder="Not given"
					bounds={schemaBounds('PumpCurve', 'minimumContinuousStableFlow')}
					onchange={(v) =>
						setManufacturer('minimumContinuousStableFlow', v, 'change minimum stable flow')}
				/>
				<NumberField
					label="Minimum thermal flow"
					value={curve.minimumThermalFlow}
					category="flow"
					units={ws.units}
					optional
					placeholder="Not given"
					bounds={schemaBounds('PumpCurve', 'minimumThermalFlow')}
					onchange={(v) => setManufacturer('minimumThermalFlow', v, 'change minimum thermal flow')}
				/>
				<NumberField
					label="Motor rated power"
					value={curve.motorRatedPower}
					category="power"
					units={ws.units}
					optional
					placeholder="Not given"
					bounds={schemaBounds('PumpCurve', 'motorRatedPower')}
					onchange={(v) => setManufacturer('motorRatedPower', v, 'change motor rated power')}
				/>
			</div>
		</details>
		<p class="hint">
			Curves are fitted with a monotone piecewise cubic through the points. The NPSHr curve gives
			the NPSH margin in the results.
		</p>
	</div>
{/if}
