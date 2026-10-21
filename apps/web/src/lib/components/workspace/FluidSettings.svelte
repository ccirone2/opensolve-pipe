<!--
	The project fluid: a built-in fluid at an operating temperature (and concentration, for
	glycol solutions), with its calculated properties shown for checking and optional overrides;
	or a custom fluid with fixed properties (PRD §3.5).
-->
<script lang="ts">
	import type {
		BuiltinFluid,
		BuiltinFluidId,
		CustomFluid,
		FluidOverrides,
		FluidProperties
	} from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { createEmptyProject } from '$lib/utils/factory';
	import { concentrationRangeText } from '$lib/utils/issue-text';
	import { FLUID_FALLBACK_NAMES, humanize } from '$lib/utils/labels';
	import { schemaBounds, stringLimits } from '$lib/utils/schema-bounds';
	import { formatValue, type UnitCategory } from '$lib/utils/units';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	const ws = useWorkspace();
	const lib = ws.library;
	const BUILTIN: readonly BuiltinFluidId[] = ['water', 'ethylene_glycol', 'propylene_glycol'];
	/** Names of the calculated properties, by their key in FluidProperties.sources. */
	const PROPERTY_LABELS: Readonly<Record<string, string>> = {
		density: 'Density',
		dynamicViscosity: 'Dynamic viscosity',
		kinematicViscosity: 'Kinematic viscosity',
		vaporPressure: 'Vapor pressure'
	};
	/** Below this mass fraction (1 %) a glycol entry is most likely a fraction typed as percent. */
	const LOW_CONCENTRATION = 0.01;
	type Choice = BuiltinFluidId | 'custom';

	const fluid = $derived(ws.project.fluid);
	const choice = $derived<Choice>(fluid.kind === 'custom' ? 'custom' : fluid.fluidId);
	const info = $derived(fluid.kind === 'builtin' ? lib.fluid(fluid.fluidId) : undefined);
	/** The library's concentration range in the display unit, e.g. "0 to 60 %". */
	const range = $derived(concentrationRangeText(info, ws.units));

	/** A custom fluid being entered: kept here until density and viscosity are given. */
	let draft = $state<{ name: string; density: number | null; viscosity: number | null } | null>(
		null
	);

	// Calculated properties of the built-in fluid, for checking (PRD §3.5.3).
	let properties = $state.raw<FluidProperties | null>(null);
	let propertiesError = $state<string | null>(null);
	/** A glycol solution needs its concentration before its properties can be calculated. */
	const needsConcentration = $derived(
		fluid.kind === 'builtin' && fluid.fluidId !== 'water' && fluid.concentration == null
	);
	$effect(() => {
		if (fluid.kind !== 'builtin' || needsConcentration) {
			properties = null;
			propertiesError = null;
			return;
		}
		const { fluidId, temperature, concentration } = fluid;
		let cancelled = false;
		const timer = setTimeout(() => {
			lib
				.fluidProperties(fluidId, temperature, concentration)
				.then((p) => {
					if (cancelled) return;
					properties = p;
					propertiesError = null;
				})
				.catch((error: unknown) => {
					if (cancelled) return;
					properties = null;
					propertiesError =
						error instanceof Error ? error.message : 'The properties could not be calculated.';
				});
		}, 300);
		return () => {
			cancelled = true;
			clearTimeout(timer);
		};
	});

	function nameOf(id: BuiltinFluidId): string {
		return lib.fluid(id)?.name ?? FLUID_FALLBACK_NAMES[id] ?? id;
	}

	function setFluid(next: BuiltinFluid | CustomFluid, label = 'change fluid'): boolean {
		return ws.edit((p) => {
			p.fluid = next;
		}, label);
	}

	function choose(next: Choice) {
		if (next === 'custom') {
			if (fluid.kind === 'custom') return;
			// Start from what the project uses: the user's overrides, else the calculated values.
			draft = {
				name: 'Custom fluid',
				density: fluid.overrides?.density ?? properties?.density ?? null,
				viscosity: fluid.overrides?.dynamicViscosity ?? properties?.dynamicViscosity ?? null
			};
			commitDraft();
			return;
		}
		draft = null;
		const temperature =
			fluid.kind === 'builtin'
				? fluid.temperature
				: (fluid.temperature ?? (createEmptyProject().fluid as BuiltinFluid).temperature);
		const builtin: BuiltinFluid = { kind: 'builtin', fluidId: next, temperature };
		if (next !== 'water' && fluid.kind === 'builtin' && fluid.concentration != null) {
			builtin.concentration = fluid.concentration;
		}
		setFluid(builtin);
	}

	function commitDraft() {
		if (!draft || draft.density === null || draft.viscosity === null) return;
		const custom: CustomFluid = {
			kind: 'custom',
			name: draft.name,
			density: draft.density,
			dynamicViscosity: draft.viscosity
		};
		if (fluid.kind === 'builtin') {
			custom.temperature = fluid.temperature;
			const vaporPressure = fluid.overrides?.vaporPressure ?? properties?.vaporPressure;
			if (vaporPressure != null) custom.vaporPressure = vaporPressure;
		}
		if (setFluid(custom)) draft = null;
	}

	function editBuiltin(label: string, change: (f: BuiltinFluid) => BuiltinFluid) {
		if (fluid.kind === 'builtin') setFluid(change({ ...fluid }), label);
	}

	function editCustom(label: string, change: (f: CustomFluid) => CustomFluid) {
		if (fluid.kind === 'custom') setFluid(change({ ...fluid }), label);
	}

	function setOverride(key: keyof FluidOverrides, value: number | null) {
		editBuiltin('change fluid override', (f) => {
			const overrides: FluidOverrides = { ...(f.overrides ?? {}) };
			if (value === null) delete overrides[key];
			else overrides[key] = value;
			const next: BuiltinFluid = { ...f, overrides };
			if (!Object.values(overrides).some((v) => v != null)) delete next.overrides;
			return next;
		});
	}

	function setOptional<K extends 'temperature' | 'vaporPressure'>(key: K, value: number | null) {
		editCustom(
			key === 'temperature' ? 'change fluid temperature' : 'change vapor pressure',
			(f) => {
				const next = { ...f };
				if (value === null) delete next[key];
				else next[key] = value;
				return next;
			}
		);
	}

	function rangeWarning(
		value: number | null | undefined,
		range: { min: number; max: number } | null | undefined,
		category: UnitCategory
	): string | null {
		if (value == null || !range) return null;
		if (value >= range.min && value <= range.max) return null;
		return `Outside the library's range for this fluid (${formatValue(range.min, category, ws.units)} to ${formatValue(range.max, category, ws.units)}).`;
	}

	function show(si: number | null | undefined, category: UnitCategory, absolute = false): string {
		return formatValue(si, category, ws.units, 4, { absolute });
	}
</script>

<div class="space-y-4">
	<SelectField
		label="Fluid"
		value={draft ? 'custom' : choice}
		options={[
			...BUILTIN.map((id) => ({ value: id, label: nameOf(id) })),
			{ value: 'custom', label: 'Custom fluid (enter its properties)' }
		]}
		onchange={choose}
	/>

	{#if draft}
		<div class="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
			<p class="text-sm text-amber-900">
				Enter the density and viscosity to use a custom fluid. Until then the project keeps its
				current fluid.
			</p>
			<TextField
				label="Name"
				value={draft.name}
				required
				onchange={(v) => {
					if (draft && v) draft.name = v;
				}}
			/>
			<NumberField
				label="Density"
				value={draft.density}
				category="density"
				units={ws.units}
				optional
				bounds={schemaBounds('CustomFluid', 'density')}
				onchange={(v) => {
					if (draft) draft.density = v;
					commitDraft();
				}}
			/>
			<NumberField
				label="Dynamic viscosity"
				value={draft.viscosity}
				category="viscosity"
				units={ws.units}
				optional
				bounds={schemaBounds('CustomFluid', 'dynamicViscosity')}
				onchange={(v) => {
					if (draft) draft.viscosity = v;
					commitDraft();
				}}
			/>
			<button type="button" class="btn" onclick={() => (draft = null)}>Cancel</button>
		</div>
	{:else if fluid.kind === 'builtin'}
		<NumberField
			label="Operating temperature"
			value={fluid.temperature}
			category="temperature"
			units={ws.units}
			bounds={schemaBounds('BuiltinFluid', 'temperature')}
			warning={rangeWarning(fluid.temperature, info?.temperatureRange, 'temperature')}
			onchange={(v) =>
				v !== null && editBuiltin('change fluid temperature', (f) => ({ ...f, temperature: v }))}
		/>
		{#if fluid.fluidId !== 'water'}
			<NumberField
				label="Glycol concentration"
				value={fluid.concentration}
				category="fraction"
				units={ws.units}
				optional
				bounds={schemaBounds('BuiltinFluid', 'concentration')}
				hint={`Percentage of glycol in the solution, by mass${range ? ` (the property library covers ${range})` : ''}.`}
				warning={fluid.concentration == null
					? `Required for a glycol solution: a percentage by mass${range ? `, ${range}` : ''}.`
					: (rangeWarning(fluid.concentration, info?.concentrationRange, 'fraction') ??
						(fluid.concentration > 0 && fluid.concentration < LOW_CONCENTRATION
							? `${show(fluid.concentration, 'fraction')} is almost water. This field is in percent: enter 30 for a 30 % solution.`
							: null))}
				onchange={(v) =>
					editBuiltin('change glycol concentration', (f) => {
						const next = { ...f };
						if (v === null) delete next.concentration;
						else next.concentration = v;
						return next;
					})}
			/>
		{/if}

		<div class="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
			{#if needsConcentration}
				<p>Enter the glycol concentration to calculate the properties.</p>
			{:else if properties}
				<p class="font-medium">Calculated properties</p>
				<dl class="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
					<dt>Density</dt>
					<dd>{show(properties.density, 'density')}</dd>
					<dt>Dynamic viscosity</dt>
					<dd>{show(properties.dynamicViscosity, 'viscosity')}</dd>
					<dt>Vapor pressure</dt>
					<dd>{show(properties.vaporPressure, 'pressure', true)}</dd>
				</dl>
				{#each Object.entries(properties.sources) as [key, source] (key)}
					<p class="mt-1 text-xs text-slate-600">
						{PROPERTY_LABELS[key] ?? humanize(key)}: {source.citation}
					</p>
				{/each}
			{:else if propertiesError}
				<p>Calculated properties cannot be shown right now. {propertiesError}</p>
				<p class="mt-1">The solver calculates them when the project is solved.</p>
			{:else}
				<p>Calculating properties…</p>
			{/if}
			{#if info}<p class="mt-1 text-xs text-slate-600">Source: {info.source}</p>{/if}
		</div>

		<details class="group" open={!!fluid.overrides}>
			<summary
				class="flex min-h-11 cursor-pointer list-none items-center gap-1 text-sm font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
			>
				<Icon name="right" class="size-4 shrink-0 transition-transform group-open:rotate-90" />
				Override calculated properties (optional)
			</summary>
			<div class="space-y-3 pt-2">
				<NumberField
					label="Density override"
					value={fluid.overrides?.density}
					category="density"
					units={ws.units}
					optional
					placeholder="Calculated"
					bounds={schemaBounds('FluidOverrides', 'density')}
					onchange={(v) => setOverride('density', v)}
				/>
				<NumberField
					label="Dynamic viscosity override"
					value={fluid.overrides?.dynamicViscosity}
					category="viscosity"
					units={ws.units}
					optional
					placeholder="Calculated"
					bounds={schemaBounds('FluidOverrides', 'dynamicViscosity')}
					onchange={(v) => setOverride('dynamicViscosity', v)}
				/>
				<NumberField
					label="Vapor pressure override"
					value={fluid.overrides?.vaporPressure}
					category="pressure"
					absolute
					units={ws.units}
					optional
					placeholder="Calculated"
					bounds={schemaBounds('FluidOverrides', 'vaporPressure')}
					onchange={(v) => setOverride('vaporPressure', v)}
				/>
			</div>
		</details>
	{:else}
		<TextField
			label="Name"
			value={fluid.name}
			required
			maxlength={stringLimits('CustomFluid', 'name').maxLength}
			onchange={(v) => !!v && editCustom('rename fluid', (f) => ({ ...f, name: v }))}
		/>
		<NumberField
			label="Density"
			value={fluid.density}
			category="density"
			units={ws.units}
			bounds={schemaBounds('CustomFluid', 'density')}
			onchange={(v) => v !== null && editCustom('change density', (f) => ({ ...f, density: v }))}
		/>
		<NumberField
			label="Dynamic viscosity"
			value={fluid.dynamicViscosity}
			category="viscosity"
			units={ws.units}
			bounds={schemaBounds('CustomFluid', 'dynamicViscosity')}
			onchange={(v) =>
				v !== null && editCustom('change viscosity', (f) => ({ ...f, dynamicViscosity: v }))}
		/>
		<NumberField
			label="Vapor pressure"
			value={fluid.vaporPressure}
			category="pressure"
			absolute
			units={ws.units}
			optional
			bounds={schemaBounds('CustomFluid', 'vaporPressure')}
			hint="Absolute. Needed for NPSH available; without it NPSH is not calculated."
			onchange={(v) => setOptional('vaporPressure', v)}
		/>
		<NumberField
			label="Temperature"
			value={fluid.temperature}
			category="temperature"
			units={ws.units}
			optional
			bounds={schemaBounds('CustomFluid', 'temperature')}
			hint="For the record only: a custom fluid's properties are fixed."
			onchange={(v) => setOptional('temperature', v)}
		/>
	{/if}
</div>
