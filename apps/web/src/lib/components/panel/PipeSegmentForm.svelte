<!--
	One pipe segment of a connection: a library pipe (material, schedule, nominal size; inner
	diameter and roughness resolved from the cited library, with optional overrides), a custom
	pipe (inner diameter and roughness entered by the user), or a pipe spec of the project library
	(CLAUDE.md D21: its values shown read-only, with its source and "Edit in the library", since an
	edit there changes every pipe that uses it), and its length. The Material list holds the
	project's specs under "Project specs", and "New pipe spec…" (in the base case: the library is
	the same in every case) opens the library's new spec form, whose spec this pipe then uses (when
	the library holds as many specs as a project may, it is offered disabled, saying so).
	"Use a pipe spec for…" uses a spec for this pipe, every pipe of its size and material, or every
	pipe of this connection, as one undo step after a confirmation that states the count. In a
	scenario the material, schedule, size and the bore and roughness (or a custom pipe's, or the
	spec it uses) are one change, noted under the pipe's heading, and the length is another.

	Its velocity at the last solve of the case shown is the size's hint (a custom pipe's inner
	diameter's, a spec pipe's values'), where it is needed when sizing, marked out of date after
	edits. It is this pipe's own, found by identity through the edits since (utils/results.ts
	solvedPipe), with the sign of the connection's direction now (the other sign after a reversal);
	a pipe added since, or one whose direction is not known, has none.
-->
<script lang="ts">
	import type { PipeConnection, PipeDefinition } from '$lib/api/types';
	import ChangeNote from '$lib/components/ui/ChangeNote.svelte';
	import { hasChangeNote } from '$lib/components/ui/field-mode';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField, { type SelectOption } from '$lib/components/ui/SelectField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { componentById } from '$lib/utils/graph';
	import { npsLabel } from '$lib/utils/labels';
	import {
		CUSTOM_MATERIAL_ID,
		removePipe,
		resolvedPipe,
		updatePipe,
		withMaterial,
		withOptional,
		withSchedule
	} from '$lib/utils/piping';
	import {
		applyPipeSpec,
		pipeSpecOf,
		pipeSpecs,
		specPipe,
		withSpec
	} from '$lib/utils/project-library';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { formatValue } from '$lib/utils/units';
	import { Formatter, solvedPipe } from '$lib/utils/results';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import NominalSizeField from './NominalSizeField.svelte';
	import { libraryFull, newOptionLabel } from '$lib/components/workspace/library/limits';
	import UsePipeSpecDialog from './UsePipeSpecDialog.svelte';

	interface Props {
		connection: PipeConnection;
		index: number;
		pipe: PipeDefinition;
	}

	let { connection, index, pipe }: Props = $props();
	const ws = useWorkspace();
	const lib = ws.library;
	const headingId = $props.id();

	/** The project library spec the pipe refers to (its id), if any. */
	const specId = $derived(pipe.specId ?? null);
	const libSpec = $derived(specId === null ? undefined : pipeSpecOf(ws.project, specId));
	const specs = $derived(pipeSpecs(ws.project));
	/** The library holds as many specs as a project may: no new one. */
	const specsFull = $derived(libraryFull(ws.project, 'pipe'));
	const custom = $derived(specId === null && pipe.materialId === CUSTOM_MATERIAL_ID);
	const material = $derived(specId === null ? lib.material(pipe.materialId) : undefined);
	const schedule = $derived(lib.schedule(pipe.materialId, pipe.schedule));
	const size = $derived(lib.size(pipe.materialId, pipe.schedule, pipe.nominalSize));
	/** What the solver uses: overrides, else the size entry (roughness is per size). */
	const resolved = $derived(resolvedPipe(pipe, size));
	/** The same for any pipe, a spec's included (its own values), as far as the browser knows. */
	const resolution = $derived(lib.resolvePipe(ws.project, pipe));
	const count = $derived(connection.piping.pipes.length);
	/** "Velocity at the last solve: 3.981 m/s", or nothing (no converged solve with this pipe). */
	const velocityHint = $derived.by(() => {
		const results = ws.store.results;
		const solved = results.response?.solvedState;
		if (!solved || !results.response?.success || !solved.converged) return undefined;
		if (results.error && !results.errorStale) return undefined;
		// The stored project's pipes carry their identity (a scenario's case project copies them).
		const found = solvedPipe(ws.store.project, solved, connection.id, index);
		if (!found) return undefined;
		const value = new Formatter(ws.displayUnits).value(
			found.sign * found.segment.velocity,
			'velocity'
		);
		return `Velocity at the last solve: ${value}${results.stale ? ' (out of date)' : ''}.`;
	});
	/** The pipe's size and material, and its length: scenario values (one change each). */
	const specChange = $derived(ws.pipeChange(connection.id, index, 'spec'));
	const lengthChange = $derived(ws.pipeChange(connection.id, index, 'length'));
	/** The group's note, which describes each of its inputs (they show none of their own). */
	const specNote = $derived(hasChangeNote(specChange) ? `${headingId}-spec` : undefined);

	const SPEC_PREFIX = 'spec:';
	const NEW_SPEC = 'new-spec';
	const SPECS_GROUP = 'Project specs';
	const materialValue = $derived(
		specId !== null ? `${SPEC_PREFIX}${specId}` : (pipe.materialId ?? '')
	);
	const materialOptions = $derived.by((): SelectOption<string>[] => {
		const options: SelectOption<string>[] = lib.materials.map((m) => ({
			value: m.id,
			label: m.name
		}));
		if (specId === null && !custom && !material && pipe.materialId) {
			options.push({
				value: pipe.materialId,
				label:
					lib.libraryStatus === 'ready'
						? `${pipe.materialId} (not in the library)`
						: `${pipe.materialId} (library unavailable)`
			});
		}
		options.push({
			value: CUSTOM_MATERIAL_ID,
			label: 'Custom (enter inner diameter and roughness)'
		});
		for (const s of specs) {
			options.push({ value: `${SPEC_PREFIX}${s.id}`, label: s.name, group: SPECS_GROUP });
		}
		if (specId !== null && !libSpec) {
			options.push({
				value: `${SPEC_PREFIX}${specId}`,
				label: `${specId} (not in the project library)`,
				group: SPECS_GROUP
			});
		}
		if (!ws.inScenario)
			options.push({
				value: NEW_SPEC,
				label: newOptionLabel('New pipe spec…', specsFull, 'pipe'),
				disabled: specsFull,
				group: SPECS_GROUP
			});
		return options;
	});

	/** "pipe 2 of Tank → Pump": this pipe in an undo label. */
	const pipeWords = $derived.by(() => {
		const name = (id: string) => componentById(ws.project, id)?.name ?? id;
		return `pipe ${index + 1} of ${name(connection.fromComponentId)} → ${name(connection.toComponentId)}`;
	});

	function edit(label: string, change: (pipe: PipeDefinition) => PipeDefinition): boolean {
		return ws.editConnection(connection.id, label, (c) => ({
			...c,
			piping: updatePipe(c.piping, index, change)
		}));
	}

	/**
	 * A pipe as its own values: a pipe of a spec the project has is the pipe the spec stands for,
	 * with the spec's nominal size (so a library material starts from the nearest size).
	 */
	function ownValues(p: PipeDefinition): PipeDefinition {
		const spec = p.specId == null ? undefined : pipeSpecOf(ws.project, p.specId);
		if (!spec) return p;
		const own = specPipe(p, spec);
		if (spec.nominalSize != null) own.nominalSize = spec.nominalSize;
		return own;
	}

	function setMaterial(value: string) {
		if (value === materialValue) return;
		if (value === NEW_SPEC) {
			if (specsFull) return;
			const connectionId = connection.id;
			const pipeIndex = index;
			ws.openLibrary({
				list: 'pipe',
				create: true,
				use: {
					label: pipeWords,
					apply: (project, id) =>
						applyPipeSpec(project, id, { kind: 'pipe', connectionId, pipeIndex }).project
				}
			});
			return;
		}
		if (value.startsWith(SPEC_PREFIX)) {
			const id = value.slice(SPEC_PREFIX.length);
			edit('use pipe spec', (p) => withSpec(p, id));
			return;
		}
		// Start from the values the solver used, so a switch to Custom alone changes no result.
		const from = { ...resolution };
		if (value === CUSTOM_MATERIAL_ID) {
			edit('change pipe material', (p) => withMaterial(ownValues(p), CUSTOM_MATERIAL_ID, from));
			return;
		}
		const next = lib.material(value);
		if (next) edit('change pipe material', (p) => withMaterial(ownValues(p), next, from));
	}

	const fmt = (si: number) => formatValue(si, 'diameter', ws.units, 4);
	let using = $state(false);
</script>

<section class="card space-y-3 p-3" aria-labelledby={headingId}>
	<div class="flex min-h-11 items-center justify-between gap-2">
		<h4 id={headingId} class="font-medium">Pipe {index + 1}{count > 1 ? ` of ${count}` : ''}</h4>
		{#if count > 1 && !ws.inScenario}
			<button
				type="button"
				class="btn btn-quiet text-red-800"
				onclick={() =>
					ws.editConnection(connection.id, 'remove pipe', (c) => ({
						...c,
						piping: removePipe(c.piping, index)
					}))}
			>
				<Icon name="trash" class="size-4" /> Remove pipe
			</button>
		{/if}
	</div>

	<ChangeNote change={specChange} id="{headingId}-spec" />

	<div class="grid gap-3 sm:grid-cols-2">
		<SelectField
			label="Material"
			value={materialValue}
			options={materialOptions}
			class="sm:col-span-2"
			change={specChange}
			changeNote={false}
			describedby={specNote}
			onchange={setMaterial}
		/>

		{#if specId === null && !custom}
			{#if material}
				<SelectField
					label="Schedule"
					value={pipe.schedule ?? ''}
					options={[
						...(schedule
							? []
							: [
									{
										value: pipe.schedule ?? '',
										label: pipe.schedule ? `${pipe.schedule} (not in the library)` : 'Choose…'
									}
								]),
						...material.schedules.map((s) => ({ value: s.id, label: s.id }))
					]}
					change={specChange}
					changeNote={false}
					describedby={specNote}
					onchange={(id) => {
						const next = material.schedules.find((s) => s.id === id);
						if (next) edit('change pipe schedule', (p) => withSchedule(p, next));
					}}
				/>
			{:else}
				<TextField
					label="Schedule"
					value={pipe.schedule}
					hint="Schedule designation, e.g. 40 or 10S."
					change={specChange}
					onchange={(v) => edit('change pipe schedule', (p) => withOptional(p, 'schedule', v))}
				/>
			{/if}
			<NominalSizeField
				label="Size"
				value={pipe.nominalSize}
				sizes={schedule?.sizes ?? []}
				units={ws.units}
				hint={velocityHint}
				change={specChange}
				describedby={specNote}
				onchange={(nominalSize) => edit('change pipe size', (p) => ({ ...p, nominalSize }))}
			/>
		{/if}

		<NumberField
			label="Length"
			value={pipe.length}
			category="length"
			units={ws.units}
			bounds={schemaBounds('PipeDefinition', 'length')}
			change={lengthChange}
			onchange={(v) => v !== null && edit('change pipe length', (p) => ({ ...p, length: v }))}
		/>

		{#if custom}
			<NumberField
				label="Inner diameter"
				value={pipe.innerDiameter}
				category="diameter"
				units={ws.units}
				optional
				bounds={schemaBounds('PipeDefinition', 'innerDiameter')}
				hint={velocityHint}
				change={specChange}
				changeNote={false}
				describedby={specNote}
				warning={pipe.innerDiameter == null ? 'Required for a custom pipe.' : null}
				onchange={(v) => edit('change inner diameter', (p) => withOptional(p, 'innerDiameter', v))}
			/>
			<NumberField
				label="Roughness"
				value={pipe.roughness}
				category="diameter"
				units={ws.units}
				optional
				bounds={schemaBounds('PipeDefinition', 'roughness')}
				change={specChange}
				changeNote={false}
				describedby={specNote}
				warning={pipe.roughness == null ? 'Required for a custom pipe.' : null}
				hint="Absolute roughness of the pipe wall."
				onchange={(v) => edit('change roughness', (p) => withOptional(p, 'roughness', v))}
			/>
		{/if}
	</div>

	{#if specId !== null}
		<div class="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700" data-pipe-spec>
			{#if libSpec}
				<p>
					Project library pipe spec <strong class="break-words">{libSpec.name}</strong>
					<span class="font-mono text-xs text-slate-600">{libSpec.id}</span>
				</p>
				<dl class="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5">
					<dt class="text-slate-600">Material</dt>
					<dd class="break-words">
						{libSpec.materialId === CUSTOM_MATERIAL_ID
							? 'Custom'
							: (lib.material(libSpec.materialId)?.name ?? libSpec.materialId)}
					</dd>
					{#if libSpec.nominalSize != null}
						<dt class="text-slate-600">Nominal size</dt>
						<dd>{npsLabel(libSpec.nominalSize, lib.nominalSizes)}</dd>
					{/if}
					<dt class="text-slate-600">Inner diameter</dt>
					<dd><strong>{fmt(libSpec.innerDiameter)}</strong></dd>
					<dt class="text-slate-600">Roughness</dt>
					<dd class="break-words">
						{#if libSpec.roughness != null}
							<strong>{fmt(libSpec.roughness)}</strong>
						{:else}
							the material's at this bore (Farshad &amp; Rieke 2006), computed by the calculation
							server when solving
						{/if}
					</dd>
					{#if libSpec.outerDiameter != null}
						<dt class="text-slate-600">Outer diameter</dt>
						<dd>{fmt(libSpec.outerDiameter)}</dd>
					{/if}
				</dl>
				<p class="mt-1 text-xs break-words text-slate-600">Source: {libSpec.source}</p>
				{#if velocityHint}<p class="mt-1 text-xs text-slate-600">{velocityHint}</p>{/if}
				<button
					type="button"
					class="btn btn-quiet -ml-3 px-3 text-blue-800"
					aria-label="{ws.inScenario ? 'Show' : 'Edit'} {libSpec.name} in the library"
					onclick={() => ws.openLibrary({ list: 'pipe', edit: libSpec.id })}
				>
					{ws.inScenario ? 'Show in the library' : 'Edit in the library'}
				</button>
			{:else}
				<p class="flex items-start gap-1 text-amber-800">
					<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
					<span
						>Pipe spec {specId} is not in the project library: the calculation server reports it. Choose
						a material or another spec.</span
					>
				</p>
			{/if}
		</div>
	{:else if !custom}
		<div class="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
			{#if lib.libraryStatus === 'ready' && material && size}
				<p>
					Inner diameter <strong>{fmt(pipe.innerDiameter ?? size.innerDiameter)}</strong>
					{#if pipe.innerDiameter != null}(override; library {fmt(size.innerDiameter)}){/if}
				</p>
				<p class="text-xs text-slate-600">{material.dimensionsSource}</p>
				<p class="mt-1">
					{#if resolved.roughness != null}
						Roughness <strong>{fmt(resolved.roughness)}</strong>
						{#if pipe.roughness != null && pipe.innerDiameter == null}
							(override; library {fmt(size.roughness)})
						{:else if pipe.roughness != null}
							(override)
						{/if}
					{:else}
						Roughness: evaluated at the override inner diameter when solving
					{/if}
				</p>
				<p class="text-xs text-slate-600">{material.roughnessSource}</p>
			{:else if lib.libraryStatus === 'loading' || lib.libraryStatus === 'idle'}
				<p>Loading pipe data…</p>
			{:else if lib.libraryStatus === 'ready'}
				<p>
					This material, schedule and size are not in the pipe library: choose them from the lists,
					enter overrides below, use a custom pipe, or a pipe spec of the project library.
				</p>
			{:else}
				<p>
					The pipe library is not available right now, so the inner diameter and roughness cannot be
					shown. The calculation server resolves them when solving; to set them yourself, enter
					overrides below or use a custom pipe.
				</p>
			{/if}
		</div>
		<details class="group" open={pipe.innerDiameter != null || pipe.roughness != null}>
			<summary
				class="flex min-h-11 cursor-pointer list-none items-center gap-1 text-sm font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
			>
				<Icon name="right" class="size-4 shrink-0 transition-transform group-open:rotate-90" />
				Overrides (optional)
			</summary>
			<div class="grid gap-3 pt-2 sm:grid-cols-2">
				<NumberField
					label="Inner diameter override"
					value={pipe.innerDiameter}
					category="diameter"
					units={ws.units}
					optional
					placeholder="From the library"
					bounds={schemaBounds('PipeDefinition', 'innerDiameter')}
					change={specChange}
					changeNote={false}
					describedby={specNote}
					onchange={(v) =>
						edit('change inner diameter', (p) => withOptional(p, 'innerDiameter', v))}
				/>
				<NumberField
					label="Roughness override"
					value={pipe.roughness}
					category="diameter"
					units={ws.units}
					optional
					placeholder="From the library"
					bounds={schemaBounds('PipeDefinition', 'roughness')}
					change={specChange}
					changeNote={false}
					describedby={specNote}
					onchange={(v) => edit('change roughness', (p) => withOptional(p, 'roughness', v))}
				/>
			</div>
		</details>
	{/if}

	<!-- Several pipes at once (proposal project-library.md §6.2): in the base case always (the
		dialog can define a new spec), in a scenario when the project has specs to choose. -->
	{#if !ws.inScenario || specs.length}
		<button
			type="button"
			class="btn btn-quiet -ml-3 px-3 text-blue-800"
			aria-haspopup="dialog"
			aria-label="Use a pipe spec for pipe {index + 1} or more pipes"
			onclick={() => (using = true)}
		>
			<Icon name="book" class="size-4" /> Use a pipe spec for…
		</button>
	{/if}
</section>

{#if using}
	<UsePipeSpecDialog {connection} {index} onclose={() => (using = false)} />
{/if}
