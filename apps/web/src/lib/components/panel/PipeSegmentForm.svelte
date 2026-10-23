<!--
	One pipe segment of a connection: a library pipe (material, schedule, nominal size; inner
	diameter and roughness resolved from the cited library, with optional overrides) or a custom
	pipe (inner diameter and roughness entered by the user), and its length.
-->
<script lang="ts">
	import type { PipeConnection, PipeDefinition } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import {
		CUSTOM_MATERIAL_ID,
		removePipe,
		resolvedPipe,
		updatePipe,
		withMaterial,
		withOptional,
		withSchedule
	} from '$lib/utils/piping';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { formatValue } from '$lib/utils/units';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import NominalSizeField from './NominalSizeField.svelte';

	interface Props {
		connection: PipeConnection;
		index: number;
		pipe: PipeDefinition;
	}

	let { connection, index, pipe }: Props = $props();
	const ws = useWorkspace();
	const lib = ws.library;
	const headingId = $props.id();

	const custom = $derived(pipe.materialId === CUSTOM_MATERIAL_ID);
	const material = $derived(lib.material(pipe.materialId));
	const schedule = $derived(lib.schedule(pipe.materialId, pipe.schedule));
	const size = $derived(lib.size(pipe.materialId, pipe.schedule, pipe.nominalSize));
	/** What the solver uses: overrides, else the size entry (roughness is per size). */
	const resolved = $derived(resolvedPipe(pipe, size));
	const count = $derived(connection.piping.pipes.length);

	const materialOptions = $derived([
		...lib.materials.map((m) => ({ value: m.id, label: m.name })),
		...(!custom && !material
			? [
					{
						value: pipe.materialId,
						label:
							lib.libraryStatus === 'ready'
								? `${pipe.materialId} (not in the library)`
								: `${pipe.materialId} (library unavailable)`
					}
				]
			: []),
		{ value: CUSTOM_MATERIAL_ID, label: 'Custom (enter inner diameter and roughness)' }
	]);

	function edit(label: string, change: (pipe: PipeDefinition) => PipeDefinition): boolean {
		return ws.editConnection(connection.id, label, (c) => ({
			...c,
			piping: updatePipe(c.piping, index, change)
		}));
	}

	function setMaterial(id: string) {
		if (id === pipe.materialId) return;
		if (id === CUSTOM_MATERIAL_ID) {
			// Start from the values the solver used, so the switch alone changes no result.
			edit('change pipe material', (p) => withMaterial(p, CUSTOM_MATERIAL_ID, resolved));
			return;
		}
		const next = lib.material(id);
		if (next) edit('change pipe material', (p) => withMaterial(p, next));
	}

	const fmt = (si: number) => formatValue(si, 'diameter', ws.units, 4);
</script>

<section class="card space-y-3 p-3" aria-labelledby={headingId}>
	<div class="flex min-h-11 items-center justify-between gap-2">
		<h4 id={headingId} class="font-medium">Pipe {index + 1}{count > 1 ? ` of ${count}` : ''}</h4>
		{#if count > 1}
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

	<div class="grid gap-3 sm:grid-cols-2">
		<SelectField
			label="Material"
			value={pipe.materialId}
			options={materialOptions}
			class="sm:col-span-2"
			onchange={setMaterial}
		/>

		{#if !custom}
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
					onchange={(v) => edit('change pipe schedule', (p) => withOptional(p, 'schedule', v))}
				/>
			{/if}
			<NominalSizeField
				label="Size"
				value={pipe.nominalSize}
				sizes={schedule?.sizes ?? []}
				units={ws.units}
				onchange={(nominalSize) => edit('change pipe size', (p) => ({ ...p, nominalSize }))}
			/>
		{/if}

		<NumberField
			label="Length"
			value={pipe.length}
			category="length"
			units={ws.units}
			bounds={schemaBounds('PipeDefinition', 'length')}
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
				warning={pipe.roughness == null ? 'Required for a custom pipe.' : null}
				hint="Absolute roughness of the pipe wall."
				onchange={(v) => edit('change roughness', (p) => withOptional(p, 'roughness', v))}
			/>
		{/if}
	</div>

	{#if !custom}
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
					enter overrides below, or use a custom pipe.
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
					onchange={(v) => edit('change roughness', (p) => withOptional(p, 'roughness', v))}
				/>
			</div>
		</details>
	{/if}
</section>
