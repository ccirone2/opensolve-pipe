<!--
	Design checks (CLAUDE.md D19; proposal design-checks.md §5): opt-in design practice, off by
	default. A switch per check; when on, its limits (empty: not set) and the cited presets the API
	publishes, which fill the limits and label them with their source. A limit typed by hand makes
	the source "user". The checks travel with the project (its link); a check never changes a
	result, and failures are listed under Results → Checks. They are the same in every case, as the
	site and solver settings are: in a scenario they are shown, locked.
-->
<script lang="ts">
	import type { DesignChecks } from '$lib/api/types';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import {
		designCheckPresets,
		intersectBounds,
		pairBounds,
		schemaOrderedFields,
		type DesignCheckPreset
	} from '$lib/utils/model-rules';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	const ws = useWorkspace();
	const settings = $derived(ws.project.settings);
	const checks = $derived(settings.designChecks ?? {});
	const id = $props.id();

	type CheckKey = 'npshMargin' | 'operatingRegion' | 'pipeVelocity';
	const CHECKS: readonly { key: CheckKey; label: string; description: string }[] = [
		{
			key: 'npshMargin',
			label: 'NPSH margin',
			description:
				"Each running pump's NPSHa at least NPSHr plus a margin, and at least a ratio times NPSHr (the limits set; the greater applies)."
		},
		{
			key: 'operatingRegion',
			label: 'Pump operating region',
			description:
				"Each running pump's flow as a fraction of its best efficiency flow; with it, the pump curve's manufacturer data (allowable region, minimum flows, motor rating)."
		},
		{
			key: 'pipeVelocity',
			label: 'Pipe velocity',
			description: "Every pipe segment's velocity within the limits set."
		}
	];

	/** Edit the design checks: one undo step; none on leaves the project without the field. */
	function setChecks(update: (c: DesignChecks) => void, label: string) {
		ws.edit((p) => {
			const next: DesignChecks = structuredClone($state.snapshot(p.settings.designChecks) ?? {});
			update(next);
			const on = (Object.keys(next) as CheckKey[]).filter((k) => next[k]);
			if (on.length) p.settings.designChecks = next;
			else delete p.settings.designChecks;
		}, label);
	}

	function toggle(key: CheckKey, on: boolean, label: string) {
		setChecks(
			(c) => {
				if (on) c[key] = { source: { kind: 'user' } };
				else delete c[key];
			},
			`${on ? 'turn on' : 'turn off'} the ${label.toLowerCase()} check`
		);
	}

	/** A limit typed by hand: the source becomes "user". */
	function setLimit(key: CheckKey, field: string, value: number | null, label: string) {
		setChecks((c) => {
			const check = c[key] as Record<string, unknown> | undefined;
			if (!check) return;
			if (value === null) delete check[field];
			else check[field] = value;
			check.source = { kind: 'user' };
		}, `change the ${label.toLowerCase()} check`);
	}

	function applyPreset(key: CheckKey, preset: DesignCheckPreset, label: string) {
		setChecks((c) => {
			// The preset's own values and nothing else: the API refuses a preset source on others.
			(c as Record<CheckKey, unknown>)[key] = {
				...preset.values,
				source: { kind: 'preset', preset: preset.id }
			};
		}, `use a preset for the ${label.toLowerCase()} check`);
	}

	/**
	 * A limit's bounds: its own (the schema's) and, for an ordered pair, the other end's as
	 * stored (x-ordered-fields, read from the API's schema): a pair out of order is refused by
	 * the field, which says why, and its message goes when the stored value changes.
	 */
	function boundsOf(schemaName: string, check: unknown, field: string) {
		return intersectBounds(
			schemaBounds(schemaName, field),
			pairBounds(schemaOrderedFields(schemaName), check ?? {}, field)
		);
	}

	function presetOf(key: CheckKey): DesignCheckPreset | null {
		const source = checks[key]?.source;
		if (!source || source.kind !== 'preset') return null;
		return designCheckPresets().find((p) => p.id === source.preset) ?? null;
	}
</script>

<p class="text-sm text-slate-700">
	Off by default. Design practice, not physics: a check never changes a result or raises a flag. Its
	results are listed under Results → Checks, and the limits travel with the project's link.
	{#if ws.inScenario}They are the same in every case: change them in the base case.{/if}
</p>
<div class="space-y-4">
	{#each CHECKS as check (check.key)}
		{@const on = !!checks[check.key]}
		{@const preset = presetOf(check.key)}
		<div class="space-y-2 rounded-md border border-slate-200 p-3">
			<label class="flex min-h-11 items-center gap-3">
				<input
					type="checkbox"
					class="size-4"
					checked={on}
					disabled={ws.inScenario}
					aria-describedby="{id}-{check.key}-about"
					onchange={(e) => toggle(check.key, e.currentTarget.checked, check.label)}
				/>
				<span class="font-medium">{check.label}</span>
			</label>
			<p id="{id}-{check.key}-about" class="text-xs text-slate-600">{check.description}</p>
			{#if on}
				<div class="grid gap-3 sm:grid-cols-2">
					{#if check.key === 'npshMargin'}
						<NumberField
							label="Minimum margin NPSHa − NPSHr"
							value={checks.npshMargin?.minimumMargin}
							category="head"
							units={settings.units}
							optional
							placeholder="Not set"
							bounds={schemaBounds('NpshMarginCheck', 'minimumMargin')}
							onchange={(v) => setLimit('npshMargin', 'minimumMargin', v, check.label)}
						/>
						<NumberField
							label="Minimum ratio NPSHa / NPSHr"
							value={checks.npshMargin?.minimumRatio}
							category="dimensionless"
							units={settings.units}
							optional
							placeholder="Not set"
							bounds={schemaBounds('NpshMarginCheck', 'minimumRatio')}
							onchange={(v) => setLimit('npshMargin', 'minimumRatio', v, check.label)}
						/>
					{:else if check.key === 'operatingRegion'}
						<NumberField
							label="Lowest flow, of BEP flow"
							value={checks.operatingRegion?.preferredMin}
							category="fraction"
							units={settings.units}
							optional
							placeholder="Not set"
							bounds={boundsOf('OperatingRegionCheck', checks.operatingRegion, 'preferredMin')}
							onchange={(v) => setLimit('operatingRegion', 'preferredMin', v, check.label)}
						/>
						<NumberField
							label="Highest flow, of BEP flow"
							value={checks.operatingRegion?.preferredMax}
							category="fraction"
							units={settings.units}
							optional
							placeholder="Not set"
							bounds={boundsOf('OperatingRegionCheck', checks.operatingRegion, 'preferredMax')}
							onchange={(v) => setLimit('operatingRegion', 'preferredMax', v, check.label)}
						/>
					{:else}
						<NumberField
							label="Minimum velocity"
							value={checks.pipeVelocity?.minimum}
							category="velocity"
							units={settings.units}
							optional
							placeholder="Not set"
							bounds={boundsOf('PipeVelocityCheck', checks.pipeVelocity, 'minimum')}
							onchange={(v) => setLimit('pipeVelocity', 'minimum', v, check.label)}
						/>
						<NumberField
							label="Maximum velocity"
							value={checks.pipeVelocity?.maximum}
							category="velocity"
							units={settings.units}
							optional
							placeholder="Not set"
							bounds={boundsOf('PipeVelocityCheck', checks.pipeVelocity, 'maximum')}
							onchange={(v) => setLimit('pipeVelocity', 'maximum', v, check.label)}
						/>
					{/if}
				</div>
				{#if ws.inScenario}
					<!-- Locked in a scenario, as the fields are: no preset to apply. -->
				{:else if check.key !== 'pipeVelocity'}
					<div class="flex flex-wrap items-center gap-2">
						{#each designCheckPresets(check.key as DesignCheckPreset['check']) as p (p.id)}
							<button
								type="button"
								class="btn px-3 text-sm"
								aria-describedby="{id}-{p.id}-citation"
								onclick={() => applyPreset(check.key, p, check.label)}
								>{p.id === 'api610_por' ? 'Use API 610' : 'Use HI 9.6.1-2012 (general)'}</button
							>
							<span id="{id}-{p.id}-citation" class="sr-only">{p.citation}</span>
						{/each}
					</div>
				{:else}
					<p class="text-xs text-slate-600">
						No preset: no source read gives velocity limits that suit every fluid and use.
					</p>
				{/if}
				<p class="text-xs text-slate-700">
					<span class="font-medium">Source:</span>
					{preset ? preset.citation : 'your values'}
				</p>
			{/if}
		</div>
	{/each}
</div>
