<!--
	Inline fittings of a connection: type (from the library list, with its source), quantity, the
	pipe it sits in (its diameter is the K reference), its loss coefficient, and the angle or
	radius ratio when the type needs them (left empty and flagged until entered, never guessed).

	The loss coefficient is the type's cited K (the fitting library; none for a custom fitting), a
	K entered here (a fitting's kOverride), or an entry of the project library (CLAUDE.md D21: a K
	at the bore it is stated at, a Cv or a Kv, with its source; the fitting's resistanceId), shown
	read-only with "Edit in the library" since an edit there changes every element that uses it.
	"New entry…" (in the base case) opens the library's new entry form, whose entry the fitting then
	uses (offered disabled, saying so, when the library holds as many entries as a project may).
	Choosing "K entered here" shows an empty field until a K is entered; the cited K applies
	meanwhile (a custom fitting is flagged). "K source" names the source of the K the solve uses:
	the type's cited K, or user data for a K entered here; an entry's source is in its block.
-->
<script lang="ts">
	import type { Fitting, PipeConnection } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import {
		DEFAULT_ENTRANCE,
		DEFAULT_EXIT,
		hasReservoirLoss,
		updateConnection
	} from '$lib/utils/edit';
	import { componentById } from '$lib/utils/graph';
	import { fittingFallbackName } from '$lib/utils/labels';
	import {
		addFitting,
		isReducer,
		maxPipeIndex,
		newFitting,
		removeFitting,
		updateFitting,
		withOptional
	} from '$lib/utils/piping';
	import {
		entryKAtBore,
		entryName,
		entryValueText,
		resistanceEntries,
		setFittingResistance
	} from '$lib/utils/project-library';
	import { fittingTypes, schemaBounds } from '$lib/utils/schema-bounds';
	import { formatValue } from '$lib/utils/units';
	import { ENTRANCE_TYPES, EXIT_TYPES, FITTING_PARAMETERS } from '$lib/utils/model-rules';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { libraryFull, newOptionLabel } from '$lib/components/workspace/library/limits';

	let { connection }: { connection: PipeConnection } = $props();
	const ws = useWorkspace();
	const lib = ws.library;
	const id = $props.id();

	type Param = 'angle' | 'radiusRatio';

	const types = $derived(
		lib.fittings.length
			? lib.fittings.map((f) => ({ value: f.type as Fitting['type'], label: f.name }))
			: fittingTypes().map((t) => ({ value: t as Fitting['type'], label: fittingFallbackName(t) }))
	);
	let newType = $state<Fitting['type']>('elbow_90_lr');
	const pipes = $derived(connection.piping.pipes.length);
	const fittings = $derived(connection.piping.fittings);

	function nameOf(type: string): string {
		return lib.fitting(type)?.name ?? fittingFallbackName(type);
	}

	/** Fields the type uses: required ones (API model rules) and any the library lists. */
	function params(type: string): Param[] {
		const used = new Set<string>([
			...(FITTING_PARAMETERS[type] ?? []),
			...(lib.fitting(type)?.parameters ?? [])
		]);
		return (['angle', 'radiusRatio'] as const).filter((p) => used.has(p));
	}

	function required(type: string, field: 'angle' | 'radiusRatio' | 'kOverride'): boolean {
		return (FITTING_PARAMETERS[type] ?? []).includes(field);
	}

	/**
	 * Where a fitting's K comes from: the type's cited K, a K entered here, or a project library
	 * entry; "new-entry" opens the library's new entry form.
	 */
	type KChoice = 'cited' | 'entered' | `entry:${string}` | 'new-entry';
	const entries = $derived(resistanceEntries(ws.project));
	/** The library holds as many resistance entries as a project may: no new one. */
	const entriesFull = $derived(libraryFull(ws.project, 'resistance'));
	/** Fittings (by index) whose "K entered here" was chosen with no K entered yet. */
	let entering = $state<number[]>([]);

	function kChoice(fitting: Fitting, index: number): KChoice {
		if (fitting.resistanceId) return `entry:${fitting.resistanceId}`;
		if (fitting.kOverride != null || required(fitting.type, 'kOverride')) return 'entered';
		return entering.includes(index) ? 'entered' : 'cited';
	}

	function kOptions(fitting: Fitting) {
		const group = 'From the project library';
		const options: { value: KChoice; label: string; group?: string; disabled?: boolean }[] = [];
		if (!required(fitting.type, 'kOverride')) {
			options.push({ value: 'cited', label: 'Cited K of this fitting type' });
		}
		options.push({ value: 'entered', label: 'K entered here' });
		for (const e of entries) {
			options.push({
				value: `entry:${e.id}`,
				label: `${entryName(e)} (${entryValueText(e, ws.units, 4)})`,
				group
			});
		}
		if (fitting.resistanceId && !entries.some((e) => e.id === fitting.resistanceId)) {
			options.push({
				value: `entry:${fitting.resistanceId}`,
				label: `${fitting.resistanceId} (not in the project library)`,
				group
			});
		}
		if (!ws.inScenario) {
			options.push({
				value: 'new-entry',
				label: newOptionLabel('New entry…', entriesFull, 'resistance'),
				disabled: entriesFull,
				group
			});
		}
		return options;
	}

	function useEntry(index: number, entryId: string | null, label: string) {
		ws.editConnection(connection.id, label, (c) => ({
			...c,
			piping: setFittingResistance(c.piping, index, entryId)
		}));
	}

	function chooseK(fitting: Fitting, index: number, next: KChoice) {
		const current = kChoice(fitting, index);
		if (next === current) return;
		if (next === 'new-entry') {
			if (entriesFull) return;
			const connectionId = connection.id;
			ws.openLibrary({
				list: 'resistance',
				create: true,
				use: {
					label: `fitting ${index + 1} of ${connectionName}`,
					apply: (project, id) =>
						updateConnection(project, connectionId, (c) => ({
							...c,
							piping: setFittingResistance(c.piping, index, id)
						}))
				}
			});
			return;
		}
		entering = entering.filter((i) => i !== index);
		if (next.startsWith('entry:')) {
			useEntry(index, next.slice('entry:'.length), 'use resistance entry');
			return;
		}
		if (next === 'entered') entering = [...entering, index];
		// Neither an entry nor a K until one is entered: the cited K (or a custom fitting's flag).
		if (fitting.resistanceId || fitting.kOverride != null) {
			useEntry(index, null, next === 'cited' ? 'use cited fitting K' : 'change fitting K');
		}
	}

	/** "Tank → Pump": this connection in an undo label. */
	const connectionName = $derived.by(() => {
		const name = (cid: string) => componentById(ws.project, cid)?.name ?? cid;
		return `${name(connection.fromComponentId)} → ${name(connection.toComponentId)}`;
	});

	/** A pipe's inner diameter as far as the browser knows it (a K entry is moved to it). */
	function boreOf(pipeIndex: number): number | undefined {
		const pipe = connection.piping.pipes[pipeIndex];
		return pipe ? lib.resolvePipe(ws.project, pipe).innerDiameter : undefined;
	}

	function edit(index: number, label: string, change: (fitting: Fitting) => Fitting) {
		return ws.editConnection(connection.id, label, (c) => ({
			...c,
			piping: updateFitting(c.piping, index, change)
		}));
	}

	function changeType(index: number, type: Fitting['type']) {
		edit(index, 'change fitting type', (f) => {
			let next: Fitting = { ...f, type };
			for (const p of ['angle', 'radiusRatio'] as const) {
				if (!params(type).includes(p)) next = withOptional(next, p, null);
			}
			next.pipeIndex = Math.min(next.pipeIndex, maxPipeIndex(next, pipes));
			return next;
		});
	}

	function pipeOptions(fitting: Fitting) {
		const last = maxPipeIndex(fitting, pipes);
		return Array.from({ length: last + 1 }, (_, i) => ({
			value: String(i),
			label: isReducer(fitting) ? `Between pipes ${i + 1} and ${i + 2}` : `Pipe ${i + 1}`
		}));
	}

	function add() {
		ws.editConnection(connection.id, 'add fitting', (c) => ({
			...c,
			piping: addFitting(c.piping, newFitting(newType, 0, c.piping.pipes.length))
		}));
	}

	/**
	 * Ends of this connection at a reservoir. The loss where a pipe meets a body of liquid is an
	 * entrance or exit fitting; without one none is applied there (the reservoir is quiescent and
	 * the pipe's velocity head is not charged), so each such end says so and offers the fitting.
	 */
	const reservoirEnds = $derived(
		(['from', 'to'] as const).flatMap((end) => {
			const id = end === 'from' ? connection.fromComponentId : connection.toComponentId;
			const component = componentById(ws.project, id);
			return component?.type === 'reservoir' ? [{ end, name: component.name }] : [];
		})
	);
	const entrances = $derived(fittings.filter((f) => ENTRANCE_TYPES.has(f.type)).length);
	const exits = $derived(fittings.filter((f) => EXIT_TYPES.has(f.type)).length);
	/** Reservoir ends with no entrance or exit fitting for them. */
	const bareEnds = $derived(
		reservoirEnds.length === 1
			? hasReservoirLoss(connection.piping)
				? []
				: reservoirEnds
			: reservoirEnds.filter((e) => (e.end === 'from' ? entrances : exits) === 0)
	);

	/** "Default where flow leaves Reservoir R1" for an entrance or exit at a reservoir end. */
	function reservoirRole(fitting: Fitting): string | null {
		const from = reservoirEnds.find((e) => e.end === 'from');
		const to = reservoirEnds.find((e) => e.end === 'to');
		if (ENTRANCE_TYPES.has(fitting.type) && from) {
			return `Entrance loss where flow leaves ${from.name} into this pipe (a reservoir connection gets a sharp-edged entrance by default; remove it if not wanted).`;
		}
		if (EXIT_TYPES.has(fitting.type) && to) {
			return `Exit loss where flow leaves this pipe into ${to.name} (a reservoir connection gets an exit by default; remove it if not wanted).`;
		}
		return null;
	}

	function addReservoirLoss(type: Fitting['type'], end: 'from' | 'to') {
		ws.editConnection(connection.id, 'add fitting', (c) => ({
			...c,
			piping: addFitting(
				c.piping,
				newFitting(type, end === 'from' ? 0 : c.piping.pipes.length - 1, c.piping.pipes.length)
			)
		}));
	}
</script>

<section aria-labelledby="{id}-title" class="space-y-3">
	<h3 id="{id}-title" class="section-title">Fittings</h3>
	{#each bareEnds as reservoir (reservoir.end)}
		<div class="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
			<p>
				No entrance or exit loss is applied where this piping meets {reservoir.name}{ws.inScenario
					? ', in every case.'
					: ': add the fitting for the way the flow goes.'}
			</p>
			<div class={['mt-2 flex flex-wrap gap-2', ws.inScenario && 'hidden']}>
				<button
					type="button"
					class="btn py-1.5 text-left whitespace-normal"
					onclick={() => addReservoirLoss(DEFAULT_ENTRANCE, reservoir.end)}
				>
					<Icon name="plus" class="size-4" /> Sharp-edged entrance (flow leaves {reservoir.name})
				</button>
				<button
					type="button"
					class="btn py-1.5 text-left whitespace-normal"
					onclick={() => addReservoirLoss(DEFAULT_EXIT, reservoir.end)}
				>
					<Icon name="plus" class="size-4" /> Exit (flow enters {reservoir.name})
				</button>
			</div>
		</div>
	{/each}
	{#if lib.libraryStatus === 'unavailable'}
		<p class="hint">
			The fitting library is not available right now: types are listed by name only, and their K
			values and sources are shown in the results after solving.
		</p>
	{/if}
	{#if fittings.length}
		<ul class="space-y-3">
			{#each fittings as fitting, i (i)}
				{@const info = lib.fitting(fitting.type)}
				{@const choice = kChoice(fitting, i)}
				<li class="card space-y-3 p-3">
					<div class="flex items-start gap-2">
						<SelectField
							label="Fitting {i + 1} type"
							value={fitting.type}
							options={types.some((t) => t.value === fitting.type)
								? types
								: [{ value: fitting.type, label: nameOf(fitting.type) }, ...types]}
							class="flex-1"
							onchange={(t) => changeType(i, t)}
						/>
						<button
							type="button"
							class={['btn btn-quiet btn-icon mt-6 text-red-800', ws.inScenario && 'hidden']}
							aria-label="Remove fitting {i + 1}"
							onclick={() => {
								entering = [];
								ws.editConnection(connection.id, 'remove fitting', (c) => ({
									...c,
									piping: removeFitting(c.piping, i)
								}));
							}}
						>
							<Icon name="trash" />
						</button>
					</div>
					{#if reservoirRole(fitting)}
						<p class="text-xs text-slate-700">{reservoirRole(fitting)}</p>
					{/if}
					<!-- The source of the K the solve uses: a library entry's is in its block below; a
						K entered here is user data; else the type's cited K (also while a K is being
						entered: it applies until then). -->
					{#if choice === 'entered' && fitting.kOverride != null}
						<p class="text-xs text-slate-600">K source: the K entered here (user data).</p>
					{:else if info && !choice.startsWith('entry:')}
						<p class="text-xs text-slate-600">K source: {info.source}</p>
					{/if}
					<div class="grid grid-cols-2 gap-3">
						<NumberField
							label="Quantity"
							value={fitting.quantity}
							category="dimensionless"
							units={ws.units}
							integer
							bounds={schemaBounds('Fitting', 'quantity')}
							onchange={(v) =>
								v !== null && edit(i, 'change fitting quantity', (f) => ({ ...f, quantity: v }))}
						/>
						{#if pipes > 1 || isReducer(fitting)}
							<SelectField
								label={isReducer(fitting) ? 'Position' : 'In pipe'}
								value={String(fitting.pipeIndex)}
								options={pipeOptions(fitting)}
								onchange={(v) => edit(i, 'move fitting', (f) => ({ ...f, pipeIndex: Number(v) }))}
							/>
						{/if}
						<div class="col-span-2">
							<SelectField
								label="Fitting {i + 1} loss coefficient"
								value={choice}
								options={kOptions(fitting)}
								onchange={(v) => chooseK(fitting, i, v)}
							/>
						</div>
						{#if choice === 'entered'}
							<NumberField
								label={required(fitting.type, 'kOverride') ? 'K' : 'K override'}
								value={fitting.kOverride}
								category="dimensionless"
								units={ws.units}
								optional
								placeholder={required(fitting.type, 'kOverride') ? '' : 'Cited K'}
								bounds={schemaBounds('Fitting', 'kOverride')}
								warning={required(fitting.type, 'kOverride') && fitting.kOverride == null
									? 'Required for a custom fitting.'
									: fitting.kOverride == null
										? 'Enter K to use it; until then the cited K applies.'
										: null}
								onchange={(v) => {
									entering = entering.filter((x) => x !== i);
									return edit(i, 'change fitting K', (f) => withOptional(f, 'kOverride', v));
								}}
							/>
						{:else if fitting.resistanceId}
							{@const entry = entries.find((e) => e.id === fitting.resistanceId)}
							<div
								class="col-span-2 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700"
								data-library-entry
							>
								{#if entry}
									{@const bore = boreOf(fitting.pipeIndex)}
									{@const k = entryKAtBore(entry, bore)}
									<p>
										<strong class="break-words">{entry.name}</strong>
										<span class="font-mono text-xs text-slate-600">{entry.id}</span>
									</p>
									<p>{entryValueText(entry, ws.units)}</p>
									<p class="text-xs text-slate-600">
										{#if entry.kind === 'K'}
											Moved to the bore D of pipe {fitting.pipeIndex + 1} when solving, K = K₀ (D/d₀)⁴{#if k !== null && bore !== undefined}:
												K {formatValue(k, 'dimensionless', ws.units, 4)} at {formatValue(
													bore,
													'diameter',
													ws.units,
													4
												)}{/if}.
										{:else}
											Converted to K at the bore of pipe {fitting.pipeIndex + 1} when solving (ISA-75.01.01).
										{/if}
									</p>
									<p class="mt-1 text-xs break-words text-slate-600">Source: {entry.source}</p>
									<button
										type="button"
										class="btn btn-quiet -ml-3 px-3 text-blue-800"
										aria-label="{ws.inScenario ? 'Show' : 'Edit'} {entry.name} in the library"
										onclick={() => ws.openLibrary({ list: 'resistance', edit: entry.id })}
									>
										{ws.inScenario ? 'Show in the library' : 'Edit in the library'}
									</button>
								{:else}
									<p class="flex items-start gap-1 text-amber-800">
										<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
										<span
											>Resistance entry {fitting.resistanceId} is not in the project library: the calculation
											server reports it. Choose another loss coefficient.</span
										>
									</p>
								{/if}
							</div>
						{/if}
						{#each params(fitting.type) as param (param)}
							<NumberField
								label={param === 'angle' ? 'Angle' : 'Radius ratio (r/D)'}
								value={fitting[param]}
								category={param === 'angle' ? 'angle' : 'dimensionless'}
								units={ws.units}
								optional
								bounds={schemaBounds('Fitting', param)}
								warning={required(fitting.type, param) && fitting[param] == null
									? 'Required for this fitting type.'
									: null}
								onchange={(v) =>
									edit(i, `change fitting ${param === 'angle' ? 'angle' : 'radius ratio'}`, (f) =>
										withOptional(f, param, v)
									)}
							/>
						{/each}
					</div>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="text-sm text-slate-600">No fittings.</p>
	{/if}
	<div class={['flex items-end gap-2', ws.inScenario && 'hidden']}>
		<SelectField
			label="Add a fitting"
			value={newType}
			options={types}
			class="flex-1"
			onchange={(t) => (newType = t)}
		/>
		<button type="button" class="btn" onclick={add}>
			<Icon name="plus" class="size-4" /> Add
		</button>
	</div>
</section>
