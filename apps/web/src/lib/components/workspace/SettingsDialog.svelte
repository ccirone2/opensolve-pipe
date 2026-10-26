<!--
	Project settings: description, fluid, site (elevation and atmospheric pressure), display
	units and solver options. Unit preferences change only what is shown; stored values are SI.
	In a scenario, the fluid is a scenario value; the description and units are shared by every
	case; the site and solver settings are the same in every case (locked). Opened from the
	header's fluid chip, it shows the Fluid section with the focus on its first field.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import type { SolverOptions, UnitPreferences } from '$lib/api/types';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { FRICTION_METHOD_LABELS } from '$lib/utils/labels';
	import { schemaBounds, stringLimits } from '$lib/utils/schema-bounds';
	import {
		CATEGORY_UNITS,
		IMPERIAL_UNITS,
		PREFERENCE_CATEGORIES,
		SI_UNITS,
		unitLabel,
		type PreferenceCategory
	} from '$lib/utils/units';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import FluidSettings from './FluidSettings.svelte';

	let { onclose }: { onclose: () => void } = $props();
	const ws = useWorkspace();
	const settings = $derived(ws.project.settings);

	const CATEGORY_LABELS: Record<PreferenceCategory, string> = {
		length: 'Length and elevation',
		diameter: 'Pipe diameter and roughness',
		pressure: 'Pressure',
		head: 'Head',
		flow: 'Flow',
		velocity: 'Velocity',
		temperature: 'Temperature',
		density: 'Density',
		viscosity: 'Viscosity'
	};

	const same = (a: UnitPreferences, b: Readonly<UnitPreferences>) =>
		PREFERENCE_CATEGORIES.every((c) => a[c] === b[c]);
	const preset = $derived(
		same(settings.units, SI_UNITS)
			? 'si'
			: same(settings.units, IMPERIAL_UNITS)
				? 'imperial'
				: 'mixed'
	);

	// Opened on a section (the fluid chip): after the dialog has placed the focus, move it there.
	$effect(() => {
		if (ws.settingsSection !== 'fluid') return;
		ws.settingsSection = null;
		void tick().then(() => {
			const section = document.getElementById('settings-fluid')?.closest('section');
			section?.scrollIntoView?.({ block: 'start' });
			section?.querySelector<HTMLElement>('select, input, textarea, button')?.focus();
		});
	});

	function setUnits(units: UnitPreferences, label = 'change units') {
		ws.edit((p) => {
			p.settings.units = { ...units };
		}, label);
	}

	function setSolver<K extends keyof SolverOptions>(key: K, value: SolverOptions[K]) {
		ws.edit((p) => {
			p.settings.solverOptions[key] = value;
		}, 'change solver options');
	}
</script>

<Dialog title="Project settings" wide {onclose}>
	<div class="space-y-8">
		{#if ws.activeScenario}
			<p
				class="flex items-start gap-2 rounded-md border border-l-4 border-teal-600 bg-teal-50 p-3 text-sm text-teal-950"
			>
				<Icon name="layers" class="mt-0.5 size-4 shrink-0 text-teal-700" />
				<span>
					<strong>Scenario: {ws.activeScenario.name}.</strong> The fluid you set here is recorded in this
					scenario. The description and units are shared by every case; the site and solver settings are
					the same in every case.
				</span>
			</p>
		{/if}
		<section aria-labelledby="settings-project" class="space-y-3">
			<h3 id="settings-project" class="text-base font-semibold">Project</h3>
			<TextField
				label="Description"
				multiline
				value={ws.project.metadata.description}
				maxlength={stringLimits('ProjectMetadata', 'description').maxLength}
				shared
				onchange={(v) =>
					ws.edit((p) => {
						if (v === null) delete p.metadata.description;
						else p.metadata.description = v;
					}, 'change description')}
			/>
		</section>

		<section aria-labelledby="settings-fluid" class="space-y-3">
			<h3 id="settings-fluid" class="text-base font-semibold">Fluid</h3>
			<FluidSettings />
		</section>

		<section aria-labelledby="settings-site" class="space-y-3">
			<h3 id="settings-site" class="text-base font-semibold">Site</h3>
			<div class="grid gap-3 sm:grid-cols-2">
				<NumberField
					label="Site elevation"
					value={settings.siteElevation}
					category="length"
					units={settings.units}
					bounds={schemaBounds('ProjectSettings', 'siteElevation')}
					hint="Above sea level. Sets the atmospheric pressure (standard atmosphere). Component elevations are measured from the project datum."
					onchange={(v) =>
						v !== null &&
						ws.edit((p) => {
							p.settings.siteElevation = v;
						}, 'change site elevation')}
				/>
				<NumberField
					label="Atmospheric pressure override"
					value={settings.atmosphericPressure}
					category="pressure"
					absolute
					units={settings.units}
					optional
					placeholder="From the site elevation"
					bounds={schemaBounds('ProjectSettings', 'atmosphericPressure')}
					hint="Blank uses the standard atmosphere at the site elevation."
					onchange={(v) =>
						ws.edit((p) => {
							if (v === null) delete p.settings.atmosphericPressure;
							else p.settings.atmosphericPressure = v;
						}, 'change atmospheric pressure')}
				/>
			</div>
		</section>

		<section aria-labelledby="settings-units" class="space-y-3">
			<h3 id="settings-units" class="text-base font-semibold">Units</h3>
			<p class="text-sm text-slate-700">
				Units change only what is shown and typed; the project is always stored in SI. Pressures are
				gauge unless marked absolute.
			</p>
			<div role="group" aria-label="Unit presets" class="flex flex-wrap gap-2">
				<button
					type="button"
					class={['btn', preset === 'si' && 'border-blue-700 bg-blue-50']}
					aria-pressed={preset === 'si'}
					onclick={() => setUnits({ ...SI_UNITS }, 'use SI units')}>SI</button
				>
				<button
					type="button"
					class={['btn', preset === 'imperial' && 'border-blue-700 bg-blue-50']}
					aria-pressed={preset === 'imperial'}
					onclick={() => setUnits({ ...IMPERIAL_UNITS }, 'use US customary units')}
					>US customary</button
				>
				{#if preset === 'mixed'}<span class="self-center text-sm text-slate-600">Mixed</span>{/if}
			</div>
			<div class="grid gap-3 sm:grid-cols-3">
				{#each PREFERENCE_CATEGORIES as category (category)}
					<SelectField
						label={CATEGORY_LABELS[category]}
						value={settings.units[category]}
						options={CATEGORY_UNITS[category].map((u) => ({
							value: u,
							label: unitLabel(category, u)
						}))}
						shared
						onchange={(u) => setUnits({ ...settings.units, [category]: u } as UnitPreferences)}
					/>
				{/each}
			</div>
		</section>

		<section aria-labelledby="settings-solver" class="space-y-3">
			<h3 id="settings-solver" class="text-base font-semibold">Solver</h3>
			<SelectField
				label="Friction factor"
				value={settings.solverOptions.frictionMethod}
				options={[
					{ value: 'colebrook', label: FRICTION_METHOD_LABELS.colebrook },
					{ value: 'swamee_jain', label: FRICTION_METHOD_LABELS.swamee_jain }
				]}
				hint="Darcy–Weisbach friction. Swamee–Jain is the explicit approximation EPANET uses, for like-for-like comparisons."
				onchange={(v) => setSolver('frictionMethod', v)}
			/>
			<details class="group">
				<summary
					class="flex min-h-11 cursor-pointer list-none items-center gap-1 text-sm font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
				>
					<Icon name="right" class="size-4 shrink-0 transition-transform group-open:rotate-90" />
					Convergence (advanced)
				</summary>
				<div class="grid gap-3 pt-2 sm:grid-cols-2">
					<NumberField
						label="Maximum iterations"
						value={settings.solverOptions.maxIterations}
						category="dimensionless"
						units={settings.units}
						integer
						bounds={schemaBounds('SolverOptions', 'maxIterations')}
						hint="Newton iterations per network solve."
						onchange={(v) => v !== null && setSolver('maxIterations', v)}
					/>
					<NumberField
						label="Tolerance"
						value={settings.solverOptions.tolerance}
						category="dimensionless"
						units={settings.units}
						bounds={schemaBounds('SolverOptions', 'tolerance')}
						hint="Largest flow change relative to the largest flow."
						onchange={(v) => v !== null && setSolver('tolerance', v)}
					/>
				</div>
			</details>
		</section>
	</div>
	{#snippet footer()}
		<button type="button" class="btn btn-primary" onclick={onclose}>Done</button>
	{/snippet}
</Dialog>
