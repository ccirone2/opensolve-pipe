<!--
	Project settings: description, fluid, site (elevation and atmospheric pressure), display
	units, the opt-in design checks and solver options. Unit preferences change only what is shown; stored values are SI.
	In a scenario, the fluid is a scenario value; the description and units are shared by every
	case; the site, design checks and solver settings are the same in every case (locked). Opened from the
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
	import DesignChecksSettings from './DesignChecksSettings.svelte';

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

	/** The design checks switched on (they are opt-in, CLAUDE.md D19). */
	const checksOn = $derived(Object.keys(settings.designChecks ?? {}).length);
	/** "Length ft, flow gpm, …": what the per-quantity units are, said while they are closed. */
	const unitsText = $derived(
		PREFERENCE_CATEGORIES.map((c) => unitLabel(c, settings.units[c])).join(', ')
	);

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

<!--
	Condensed (proposal build-density.md §13): the units first, as one SI / US customary choice,
	since they are what people reach for; each section a short title; reference text and values
	(calculated fluid properties and their sources, the per-quantity units, the design checks,
	the convergence options) one disclosure away, each saying what it holds.
-->
<Dialog title="Project settings" wide {onclose}>
	<div class="dense space-y-5">
		{#if ws.activeScenario}
			<p class="flex items-start gap-2 text-sm text-teal-950">
				<Icon name="layers" class="mt-0.5 size-4 shrink-0 text-teal-700" />
				<span>
					<strong>Scenario: {ws.activeScenario.name}.</strong> The fluid set here is this scenario's;
					the rest is the same in every case.
				</span>
			</p>
		{/if}

		<section aria-labelledby="settings-units" class="space-y-2">
			<div class="flex flex-wrap items-center gap-x-3 gap-y-2">
				<h3 id="settings-units" class="section-title">Units</h3>
				<div
					role="group"
					aria-label="Unit presets"
					class="flex overflow-hidden rounded-md border border-slate-300"
				>
					<button
						type="button"
						class={[
							'min-h-ctl px-4 text-sm font-medium',
							preset === 'si'
								? 'bg-blue-700 text-white'
								: 'bg-white text-slate-800 hover:bg-slate-50'
						]}
						aria-pressed={preset === 'si'}
						onclick={() => setUnits({ ...SI_UNITS }, 'use SI units')}>SI</button
					>
					<button
						type="button"
						class={[
							'min-h-ctl border-l border-slate-300 px-4 text-sm font-medium',
							preset === 'imperial'
								? 'bg-blue-700 text-white'
								: 'bg-white text-slate-800 hover:bg-slate-50'
						]}
						aria-pressed={preset === 'imperial'}
						onclick={() => setUnits({ ...IMPERIAL_UNITS }, 'use US customary units')}
						>US customary</button
					>
				</div>
				{#if preset === 'mixed'}<span class="text-sm text-slate-600">Mixed</span>{/if}
			</div>
			<p class="text-xs text-slate-600">
				What is shown and typed; the project is stored in SI. Pressures are gauge unless marked
				absolute.
			</p>
			<details class="group" open={preset === 'mixed'}>
				<summary class="more-summary">
					<Icon
						name="right"
						class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
					/>
					<span class="min-w-0 flex-1"
						>Per quantity<span class="font-normal text-slate-600">: {unitsText}</span></span
					>
				</summary>
				<div class="fields fields-pairs pt-1 pb-2">
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
			</details>
		</section>

		<section aria-labelledby="settings-fluid" class="space-y-2">
			<h3 id="settings-fluid" class="section-title">Fluid</h3>
			<FluidSettings />
		</section>

		<section aria-labelledby="settings-site" class="space-y-2">
			<h3 id="settings-site" class="section-title">Site</h3>
			<div class="fields fields-pairs">
				<NumberField
					label="Site elevation"
					value={settings.siteElevation}
					category="length"
					units={settings.units}
					bounds={schemaBounds('ProjectSettings', 'siteElevation')}
					help="Above sea level. Sets the atmospheric pressure (standard atmosphere). Component elevations are measured from the project datum."
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
					help="Blank uses the standard atmosphere at the site elevation."
					onchange={(v) =>
						ws.edit((p) => {
							if (v === null) delete p.settings.atmosphericPressure;
							else p.settings.atmosphericPressure = v;
						}, 'change atmospheric pressure')}
				/>
			</div>
		</section>

		<section aria-labelledby="settings-project" class="space-y-2">
			<h3 id="settings-project" class="section-title">Project</h3>
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

		<section aria-labelledby="settings-solver" class="space-y-2">
			<h3 id="settings-solver" class="section-title">Solver</h3>
			<div class="fields">
				<SelectField
					label="Friction factor"
					value={settings.solverOptions.frictionMethod}
					options={[
						{ value: 'colebrook', label: FRICTION_METHOD_LABELS.colebrook },
						{ value: 'swamee_jain', label: FRICTION_METHOD_LABELS.swamee_jain }
					]}
					help="Darcy–Weisbach friction. Swamee–Jain is the explicit approximation EPANET uses, for like-for-like comparisons."
					onchange={(v) => setSolver('frictionMethod', v)}
				/>
			</div>
			<details class="group">
				<summary class="more-summary">
					<Icon
						name="right"
						class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
					/>
					<span class="min-w-0 flex-1"
						>Convergence (advanced)<span class="font-normal text-slate-600"
							>: {settings.solverOptions.maxIterations} iterations, tolerance {settings
								.solverOptions.tolerance}</span
						></span
					>
				</summary>
				<div class="fields fields-pairs pt-1 pb-2">
					<NumberField
						label="Maximum iterations"
						value={settings.solverOptions.maxIterations}
						category="dimensionless"
						units={settings.units}
						integer
						bounds={schemaBounds('SolverOptions', 'maxIterations')}
						help="Newton iterations per network solve."
						onchange={(v) => v !== null && setSolver('maxIterations', v)}
					/>
					<NumberField
						label="Tolerance"
						value={settings.solverOptions.tolerance}
						category="dimensionless"
						units={settings.units}
						bounds={schemaBounds('SolverOptions', 'tolerance')}
						help="Largest flow change relative to the largest flow."
						onchange={(v) => v !== null && setSolver('tolerance', v)}
					/>
				</div>
			</details>
		</section>

		<details class="group" open={checksOn > 0}>
			<summary class="more-summary">
				<Icon
					name="right"
					class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
				/>
				<h3 id="settings-checks" class="section-title">Design checks</h3>
				<span class="font-normal text-slate-600"
					>{checksOn ? `${checksOn} on` : 'opt-in, all off'}</span
				>
			</summary>
			<section aria-labelledby="settings-checks" class="space-y-2 pt-1 pb-2">
				<DesignChecksSettings />
			</section>
		</details>
	</div>
	{#snippet footer()}
		<button type="button" class="btn btn-primary" onclick={onclose}>Done</button>
	{/snippet}
</Dialog>
